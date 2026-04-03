// js/app.js
const MOCK_DATA = {
    'MU': {
        spot: 363.31,
        expMove: 18.17,
        metrics: { pop: '72%', rr: '1:3.5', mos: '6.5%', spread: '$0.15' },
        chartData: [[320,-9],[336.1,-9],[345.1,3.5],[381.5,3.5],[390.6,-9],[410,-9]]
    },
    'LULU': {
        spot: 157.15,
        expMove: 7.86,
        metrics: { pop: '68%', rr: '1:4', mos: '5.2%', spread: '$0.10' },
        chartData: [[130,-3.9],[145.4,-3.9],[149.3,1.5],[165.0,1.5],[168.9,-3.9],[180,-3.9]]
    }
};

let payoffChart, ivChart;

function initCharts() {
    payoffChart = echarts.init(document.getElementById('payoffChart'));
    ivChart = echarts.init(document.getElementById('ivChart'));
    window.addEventListener('resize', () => { payoffChart.resize(); ivChart.resize(); });
}

function renderDashboard(ticker) {
    const data = MOCK_DATA[ticker];
    const isDark = document.documentElement.classList.contains('dark');
    const textColor = isDark ? '#e5e7eb' : '#374151';
    const splitLineColor = isDark ? '#374151' : '#e5e7eb';

    document.getElementById('metricsPanel').innerHTML = `
        <div class="bg-white dark:bg-gray-800 p-4 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
            <div class="text-sm text-gray-500 dark:text-gray-400">Current Spot</div>
            <div class="text-2xl font-bold text-gray-900 dark:text-white">$${data.spot}</div>
            <div class="text-xs text-indigo-500 mt-1">±$${data.expMove} Exp. Move</div>
        </div>
        <div class="bg-white dark:bg-gray-800 p-4 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
            <div class="text-sm text-gray-500 dark:text-gray-400">Probability of Profit (PoP)</div>
            <div class="text-2xl font-bold text-green-500">${data.metrics.pop}</div>
        </div>
        <div class="bg-white dark:bg-gray-800 p-4 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
            <div class="text-sm text-gray-500 dark:text-gray-400">Risk/Reward</div>
            <div class="text-2xl font-bold text-yellow-500">${data.metrics.rr}</div>
        </div>
        <div class="bg-white dark:bg-gray-800 p-4 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
            <div class="text-sm text-gray-500 dark:text-gray-400">Margin of Safety</div>
            <div class="text-2xl font-bold text-blue-500">${data.metrics.mos}</div>
        </div>
        <div class="bg-white dark:bg-gray-800 p-4 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
            <div class="text-sm text-gray-500 dark:text-gray-400">Bid-Ask Spread</div>
            <div class="text-2xl font-bold text-gray-900 dark:text-white">${data.metrics.spread}</div>
        </div>
    `;

    payoffChart.setOption({
        grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'value', min: 'dataMin', max: 'dataMax', axisLabel: { color: textColor }, splitLine: { show: false } },
        yAxis: { type: 'value', axisLabel: { color: textColor }, splitLine: { lineStyle: { color: splitLineColor } } },
        series: [{
            name: 'P&L', type: 'line', data: data.chartData,
            markLine: { data: [{ yAxis: 0 }], lineStyle: { color: isDark ? '#9ca3af' : '#6b7280', type: 'dashed' }, symbol: ['none', 'none'] },
            areaStyle: {
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: 'rgba(34, 197, 94, 0.3)' },
                    { offset: 1, color: 'rgba(239, 68, 68, 0.3)' }
                ])
            },
            lineStyle: { color: '#3b82f6', width: 3 }
        }]
    });

    ivChart.setOption({
        grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
        xAxis: { type: 'category', data: ['Next Week', 'Next Month', '3 Months'], axisLabel: { color: textColor } },
        yAxis: { type: 'value', max: 100, axisLabel: { color: textColor }, splitLine: { lineStyle: { color: splitLineColor } } },
        series: [{
            data: ticker === 'MU' ? [85, 60, 45] : [75, 55, 40], type: 'bar',
            itemStyle: { color: function(params) { return params.value > 70 ? '#ef4444' : (params.value > 50 ? '#f59e0b' : '#3b82f6'); } }
        }]
    });
}

const themeBtn = document.getElementById('darkModeToggle');
const themeIcon = document.getElementById('themeIcon');
themeBtn.addEventListener('click', () => {
    document.documentElement.classList.toggle('dark');
    themeIcon.textContent = document.documentElement.classList.contains('dark') ? '☀️' : '🌙';
    renderDashboard(document.getElementById('tickerSelect').value);
});

document.getElementById('tickerSelect').addEventListener('change', (e) => renderDashboard(e.target.value));
window.onload = () => { initCharts(); renderDashboard('MU'); };