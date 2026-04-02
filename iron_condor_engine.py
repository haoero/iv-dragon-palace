import os
import datetime
import logging
import yfinance as yf
import pandas as pd
from typing import List, Optional, Dict, Any
from finvizfinance.screener.overview import Overview
import subprocess

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("IronCondorEngineV2")

# ==========================================
# 1. Data Provider
# ==========================================
class DataProvider:
    @staticmethod
    def fetch_earnings_tickers(limit: int = 50) -> pd.DataFrame:
        logger.info("Fetching this week's earnings tickers dynamically using finviz...")
        try:
            foverview = Overview()
            filters_dict = {
                'Earnings Date': 'This Week',
                'Option/Short': 'Optionable',
                'Average Volume': 'Over 500K',
                'Country': 'USA'
            }
            foverview.set_filter(signal='', filters_dict=filters_dict)
            df = foverview.screener_view()
            
            if df.empty:
                logger.warning("Finviz returned no tickers for this week's earnings.")
                return pd.DataFrame()
                
            return df
        except Exception as e:
            logger.error(f"Error fetching earnings calendar from finviz: {e}")
            return pd.DataFrame()

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
            if atm_call.empty: return None
            
            implied_vol = atm_call['impliedVolatility'].values[0] if 'impliedVolatility' in atm_call else 0.5
            
            bid = atm_call['bid'].values[0]
            ask = atm_call['ask'].values[0]
            if ask == 0: return None
            
            spread_pct = (ask - bid) / ask
            
            return {
                "symbol": symbol,
                "price": current_price,
                "expiration": expiration,
                "calls": calls,
                "puts": puts,
                "implied_vol": implied_vol,
                "spread_pct": spread_pct
            }
        except Exception as e:
            # logger.error(f"Error fetching options for {symbol}: {e}")
            return None

# ==========================================
# 2. Engine Models
# ==========================================
class IronCondorOrder:
    def __init__(self, symbol: str, price: float, expiration: str, implied_move: float, legs: Dict[str, float], implied_vol: float, spread_pct: float, market_cap: float):
        self.symbol = symbol
        self.price = price
        self.expiration = expiration
        self.implied_move = implied_move
        self.legs = legs
        self.implied_vol = implied_vol
        self.spread_pct = spread_pct
        self.market_cap = market_cap

class IronCondorPricer:
    @staticmethod
    def calculate_implied_move(price: float, calls: pd.DataFrame, puts: pd.DataFrame) -> float:
        atm_call = calls.iloc[(calls['strike'] - price).abs().argsort()[:1]]
        atm_put = puts.iloc[(puts['strike'] - price).abs().argsort()[:1]]
        if atm_call.empty or atm_put.empty: return price * 0.05 
            
        call_price = (atm_call['bid'].values[0] + atm_call['ask'].values[0]) / 2
        put_price = (atm_put['bid'].values[0] + atm_put['ask'].values[0]) / 2
        
        implied_move = call_price + put_price
        return implied_move * 0.85

    @staticmethod
    def select_legs(price: float, calls: pd.DataFrame, puts: pd.DataFrame, implied_move: float) -> Dict[str, float]:
        wing_width = max(implied_move * 0.2, 1.0) 
        
        short_call_strike = price + implied_move
        short_put_strike = price - implied_move
        
        def nearest_strike(df, target):
            return df.iloc[(df['strike'] - target).abs().argsort()[:1]]['strike'].values[0]
        
        actual_short_call = nearest_strike(calls, short_call_strike)
        actual_long_call = nearest_strike(calls, short_call_strike + wing_width)
        actual_short_put = nearest_strike(puts, short_put_strike)
        actual_long_put = nearest_strike(puts, short_put_strike - wing_width)
        
        return {
            "long_call": actual_long_call,
            "short_call": actual_short_call,
            "short_put": actual_short_put,
            "long_put": actual_long_put
        }

# ==========================================
# 3. HTML Builder
# ==========================================
class HTMLBuilder:
    def __init__(self, version_name: str):
        self.version_name = version_name
        self.html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Iron Condor Engine {version_name}</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-50 p-8 font-sans">
    <div class="max-w-5xl mx-auto">
        <div class="text-center mb-10">
            <h1 class="text-4xl font-extrabold text-slate-800 tracking-tight">🐉 Iron Condor Opportunities v2.0</h1>
            <p class="text-slate-500 mt-2">Automated Volatility Premium Screener - <span class="font-bold text-indigo-600">Top 5 Picks</span></p>
            <p class="text-xs text-slate-400 mt-1">Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
"""

    def add_order(self, order: IronCondorOrder):
        move_pct = (order.implied_move / order.price) * 100
        card = f"""
            <div class="bg-white p-6 rounded-xl shadow-lg border border-slate-200 hover:shadow-xl transition-shadow">
                <div class="flex justify-between items-center mb-4">
                    <h2 class="text-2xl font-bold text-indigo-600">{order.symbol}</h2>
                    <span class="bg-indigo-100 text-indigo-800 text-xs font-semibold px-2.5 py-0.5 rounded">Exp: {order.expiration}</span>
                </div>
                
                <div class="mb-2 text-slate-600 flex justify-between text-sm">
                    <span>Spot Price: <strong class="text-slate-800">${order.price:.2f}</strong></span>
                    <span>Expected Move: <strong class="text-rose-500">±${order.implied_move:.2f} ({move_pct:.1f}%)</strong></span>
                </div>
                
                <div class="mb-4 text-slate-500 flex flex-wrap gap-2 text-xs">
                    <span class="bg-slate-100 px-2 py-1 rounded">IV: {order.implied_vol*100:.1f}%</span>
                    <span class="bg-slate-100 px-2 py-1 rounded">Spread: {order.spread_pct*100:.1f}%</span>
                    <span class="bg-slate-100 px-2 py-1 rounded">Mkt Cap: {order.market_cap}</span>
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

    def save(self, filename: str):
        self.html += """
        </div>
        <div class="mt-10 text-center text-sm text-slate-400">
            Iron Condor Engine v2.0 • Dragon Palace
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
    df_tickers = DataProvider.fetch_earnings_tickers()
    if df_tickers.empty:
        logger.error("No tickers to process. Exiting.")
        return

    # Process and rank candidates
    candidates = []
    
    for _, row in df_tickers.iterrows():
        sym = row['Ticker']
        mkt_cap = row.get('Market Cap', 0)
        
        data = DataProvider.fetch_options_data(sym)
        if not data: 
            continue
            
        # Basic liquidity filter
        if data['spread_pct'] > 0.5: # Spread too wide
            continue
            
        implied_move = IronCondorPricer.calculate_implied_move(data['price'], data['calls'], data['puts'])
        legs = IronCondorPricer.select_legs(data['price'], data['calls'], data['puts'], implied_move)
        
        candidates.append(IronCondorOrder(
            symbol=sym,
            price=data['price'],
            expiration=data['expiration'],
            implied_move=implied_move,
            legs=legs,
            implied_vol=data['implied_vol'],
            spread_pct=data['spread_pct'],
            market_cap=mkt_cap
        ))

    # Sort candidates: IV descending, Spread ascending
    # We want highest IV, but decent liquidity
    candidates.sort(key=lambda x: (x.implied_vol, -x.spread_pct), reverse=True)
    
    # Pick Top 5
    top_5 = candidates[:5]
    logger.info(f"Top 5 Selected Stocks: {[o.symbol for o in top_5]}")
    
    if not top_5:
        logger.error("No valid candidates after filtering.")
        return

    # Generate versioned HTML
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    versioned_filename = f"index_v2.0_{date_str}.html"
    
    builder = HTMLBuilder(f"v2.0_{date_str}")
    for order in top_5:
        builder.add_order(order)
    builder.save(versioned_filename)
    logger.info(f"Saved versioned dashboard to {versioned_filename}")
    
    # Generate index.html redirect
    redirect_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="refresh" content="0; url={versioned_filename}" />
    <title>Redirecting to Latest Version...</title>
</head>
<body>
    <p>If you are not redirected, <a href="{versioned_filename}">click here</a>.</p>
</body>
</html>"""
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(redirect_html)
    logger.info("Updated index.html to redirect to latest version.")

    # Git Operations
    try:
        logger.info("Committing and pushing to git...")
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "Auto-deploy v2.0 earnings strategy"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        logger.info("Git push successful.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Git operation failed: {e}")

if __name__ == "__main__":
    main()
