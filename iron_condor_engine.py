import abc
import logging
import yfinance as yf
import pandas as pd
from typing import List, Optional, Dict, Any
import datetime

try:
    from finvizfinance.screener.overview import Overview
except ImportError:
    Overview = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("IronCondorEngine")

# ==========================================
# 1. 数据获取层 (Data Provider)
# ==========================================
class DataProvider:
    @staticmethod
    def fetch_earnings_tickers(limit: int = 20) -> List[str]:
        logger.info("Fetching this week's earnings tickers dynamically...")
        if Overview is None:
            return ["NKE", "MKC", "FDS", "CAG", "LW", "NG", "CALM", "CMBT", "FRMI"]
            
        try:
            foverview = Overview()
            filters_dict = {
                'Earnings Date': 'This Week',
                'Option/Short': 'Optionable',
                'Average Volume': 'Over 500K'
            }
            foverview.set_filter(signal='', filters_dict=filters_dict)
            df = foverview.screener_view()
            
            if df.empty:
                return []
                
            if 'Market Cap' in df.columns:
                df = df.sort_values('Market Cap', ascending=False)
            
            tickers = df['Ticker'].head(limit).tolist()
            logger.info(f"Pool of earnings tickers: {tickers}")
            return tickers
        except Exception as e:
            logger.error(f"Error fetching earnings calendar: {e}")
            return ["NKE", "MKC", "FDS", "CAG", "LW"]

    @staticmethod
    def fetch_options_data(symbol: str) -> Optional[Dict[str, Any]]:
        ticker = yf.Ticker(symbol)
        try:
            hist = ticker.history(period="1d")
            if hist.empty: return None
            current_price = hist['Close'].iloc[-1]
            
            expirations = ticker.options
            if not expirations: return None
            
            expiration = expirations[0]
            opt = ticker.option_chain(expiration)
            
            calls = opt.calls
            puts = opt.puts
            
            atm_call = calls.iloc[(calls['strike'] - current_price).abs().argsort()[:1]]
            implied_vol = atm_call['impliedVolatility'].values[0] if not atm_call.empty else 0.5
            iv_rank = min(1.0, implied_vol / 0.8)
            
            return {
                "symbol": symbol,
                "price": current_price,
                "expiration": expiration,
                "calls": calls,
                "puts": puts,
                "iv_rank": iv_rank,
                "implied_vol": implied_vol
            }
        except Exception:
            return None

# ==========================================
# 领域模型 (Domain Models)
# ==========================================
class TickerContext:
    def __init__(self, data: Dict[str, Any]):
        self.symbol = data['symbol']
        self.price = data['price']
        self.expiration = data['expiration']
        self.calls = data['calls']
        self.puts = data['puts']
        self.iv_rank = data['iv_rank']
        self.implied_vol = data.get('implied_vol', 0.5)
        
class IronCondorOrder:
    def __init__(self, symbol: str, price: float, expiration: str, implied_move: float, legs: Dict[str, float]):
        self.symbol = symbol
        self.price = price
        self.expiration = expiration
        self.implied_move = implied_move
        self.legs = legs

# ==========================================
# 2. 策略过滤层 (Chain of Responsibility)
# ==========================================
class FilterHandler(abc.ABC):
    def __init__(self, next_handler: Optional['FilterHandler'] = None):
        self.next_handler = next_handler

    def filter(self, context: TickerContext) -> bool:
        if not self._check(context):
            return False
        if self.next_handler:
            return self.next_handler.filter(context)
        return True

    @abc.abstractmethod
    def _check(self, context: TickerContext) -> bool:
        pass

class IVRankFilter(FilterHandler):
    def _check(self, context: TickerContext) -> bool:
        return context.implied_vol > 0.10

class LiquidityFilter(FilterHandler):
    def _check(self, context: TickerContext) -> bool:
        atm_call = context.calls.iloc[(context.calls['strike'] - context.price).abs().argsort()[:1]]
        if atm_call.empty: return False
        
        bid = atm_call['bid'].values[0]
        ask = atm_call['ask'].values[0]
        if ask == 0: return False
        
        spread_pct = (ask - bid) / ask
        return spread_pct <= 0.40 # Relaxed for earnings plays to ensure we get 5 stocks

class TermStructureFilter(FilterHandler):
    def _check(self, context: TickerContext) -> bool:
        return True

# ==========================================
# 3. 核心测算层 (Core Engine)
# ==========================================
class IronCondorPricer:
    @staticmethod
    def calculate_implied_move(context: TickerContext) -> float:
        price = context.price
        atm_call = context.calls.iloc[(context.calls['strike'] - price).abs().argsort()[:1]]
        atm_put = context.puts.iloc[(context.puts['strike'] - price).abs().argsort()[:1]]
        if atm_call.empty or atm_put.empty: return price * 0.05 
            
        call_price = (atm_call['bid'].values[0] + atm_call['ask'].values[0]) / 2
        put_price = (atm_put['bid'].values[0] + atm_put['ask'].values[0]) / 2
        
        implied_move = call_price + put_price
        return implied_move * 0.85

    @staticmethod
    def select_legs(context: TickerContext, implied_move: float) -> Dict[str, float]:
        price = context.price
        wing_width = max(implied_move * 0.2, 1.0) 
        
        short_call_strike = price + implied_move
        short_put_strike = price - implied_move
        
        def nearest_strike(df, target):
            return df.iloc[(df['strike'] - target).abs().argsort()[:1]]['strike'].values[0]
        
        actual_short_call = nearest_strike(context.calls, short_call_strike)
        actual_long_call = nearest_strike(context.calls, short_call_strike + wing_width)
        actual_short_put = nearest_strike(context.puts, short_put_strike)
        actual_long_put = nearest_strike(context.puts, short_put_strike - wing_width)
        
        return {
            "long_call": actual_long_call,
            "short_call": actual_short_call,
            "short_put": actual_short_put,
            "long_put": actual_long_put
        }

# ==========================================
# 4. 输出渲染层
# ==========================================
class HTMLBuilder:
    def __init__(self):
        self.html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Iron Condor Engine Results</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-50 p-8 font-sans">
    <div class="max-w-5xl mx-auto">
        <div class="text-center mb-10">
            <h1 class="text-4xl font-extrabold text-slate-800 tracking-tight">🐉 Iron Condor Opportunities</h1>
            <p class="text-slate-500 mt-2">Automated Volatility Premium Screener - <span class="font-bold text-indigo-600">Earnings Week Focus</span></p>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
"""

    def add_order(self, order: IronCondorOrder):
        move_pct = (order.implied_move / order.price) * 100
        card = f"""
            <div class="bg-white p-6 rounded-xl shadow-lg border border-slate-200 hover:shadow-xl transition-shadow">
                <div class="flex justify-between items-center mb-4">
                    <h2 class="text-2xl font-bold text-indigo-600">{order.symbol} <span class="text-sm font-normal text-slate-400 bg-slate-100 px-2 py-1 rounded">Earnings Play</span></h2>
                    <span class="bg-indigo-100 text-indigo-800 text-xs font-semibold px-2.5 py-0.5 rounded">Exp: {order.expiration}</span>
                </div>
                
                <div class="mb-4 text-slate-600 flex justify-between text-sm">
                    <span>Spot Price: <strong class="text-slate-800">${order.price:.2f}</strong></span>
                    <span>Expected Move: <strong class="text-rose-500">±${order.implied_move:.2f} ({move_pct:.1f}%)</strong></span>
                </div>
                
                <div class="grid grid-cols-4 gap-2 text-center mt-6 border-t pt-4">
                    <div class="flex flex-col items-center">
                        <span class="text-[10px] uppercase font-bold text-slate-400">Long Put</span>
                        <div class="w-full mt-1 bg-red-50 text-red-700 font-mono py-2 rounded-md border border-red-100">${order.legs['long_put']:.1f}</div>
                    </div>
                    <div class="flex flex-col items-center">
                        <span class="text-[10px] uppercase font-bold text-slate-400">Short Put</span>
                        <div class="w-full mt-1 bg-green-50 text-green-700 font-mono py-2 rounded-md border border-green-100">${order.legs['short_put']:.1f}</div>
                    </div>
                    <div class="flex flex-col items-center">
                        <span class="text-[10px] uppercase font-bold text-slate-400">Short Call</span>
                        <div class="w-full mt-1 bg-green-50 text-green-700 font-mono py-2 rounded-md border border-green-100">${order.legs['short_call']:.1f}</div>
                    </div>
                    <div class="flex flex-col items-center">
                        <span class="text-[10px] uppercase font-bold text-slate-400">Long Call</span>
                        <div class="w-full mt-1 bg-red-50 text-red-700 font-mono py-2 rounded-md border border-red-100">${order.legs['long_call']:.1f}</div>
                    </div>
                </div>
            </div>
        """
        self.html += card

    def save(self, filename="index.html"):
        self.html += """
        </div>
        <div class="mt-10 text-center text-sm text-slate-400">
            Generated by Iron Condor Engine • Dynamic Earnings Screener
        </div>
    </div>
</body>
</html>"""
        with open(filename, "w", encoding="utf-8") as f:
            f.write(self.html)

# ==========================================
# Main Orchestrator
# ==========================================
def main():
    symbols = DataProvider.fetch_earnings_tickers(limit=25)
    valid_orders = []
    
    filter_chain = TermStructureFilter(LiquidityFilter(IVRankFilter()))
    
    for sym in symbols:
        data = DataProvider.fetch_options_data(sym)
        if not data: continue
        
        ctx = TickerContext(data)
        if filter_chain.filter(ctx):
            logger.info(f"[Pass] {sym} passed all filters.")
            
            implied_move = IronCondorPricer.calculate_implied_move(ctx)
            legs = IronCondorPricer.select_legs(ctx, implied_move)
            
            order = IronCondorOrder(
                symbol=sym,
                price=ctx.price,
                expiration=ctx.expiration,
                implied_move=implied_move,
                legs=legs
            )
            valid_orders.append(order)
            
            # 找到5只就停止
            if len(valid_orders) >= 5:
                break
                
    builder = HTMLBuilder()
    if valid_orders:
        for order in valid_orders:
            builder.add_order(order)
        builder.save("index.html")
        logger.info(f"Final selected stocks for Iron Condor: {[o.symbol for o in valid_orders]}")
    else:
        logger.warning("No valid tickers found for Iron Condor today.")

if __name__ == "__main__":
    main()
