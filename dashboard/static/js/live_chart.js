// Live Chart Dashboard - ECharts-based real-time price chart with whale events

let chart = null;
let updateInterval = null;
let lastUpdateTime = null;

// Chart data
let priceData = [];
let whaleEvents = [];

// Configuration
const config = {
    symbol: 'SPX_USDT',
    lookback: '5m',
    minUsd: 5000,
    refreshInterval: 2000 // 2 seconds
};

// Initialize dashboard
document.addEventListener('DOMContentLoaded', async () => {
    await initChart();
    setupEventListeners();

    // Load initial data
    await refreshData(false);

    // Set up auto-refresh
    updateInterval = setInterval(() => {
        refreshData(true);
    }, config.refreshInterval);

    // Hide loading
    showLoading(false);
});

// Initialize ECharts
async function initChart() {
    const chartContainer = document.getElementById('chart-container');
    chart = echarts.init(chartContainer);

    // Set default option
    const option = getChartOption();
    chart.setOption(option);

    // Handle window resize
    window.addEventListener('resize', () => {
        chart.resize();
    });
}

// Get ECharts option
function getChartOption() {
    return {
        backgroundColor: 'transparent',
        animation: false,
        tooltip: {
            trigger: 'axis',
            axisPointer: {
                type: 'cross',
                crossStyle: {
                    color: 'rgba(0, 255, 163, 0.3)',
                    width: 1
                },
                lineStyle: {
                    color: 'rgba(0, 255, 163, 0.3)',
                    width: 1
                }
            },
            backgroundColor: 'rgba(10, 10, 10, 0.95)',
            borderColor: 'rgba(0, 255, 163, 0.2)',
            borderWidth: 1,
            textStyle: {
                color: '#ffffff',
                fontSize: 13
            },
            formatter: formatTooltip,
            padding: [12, 16],
            shadowBlur: 20,
            shadowColor: 'rgba(0, 255, 163, 0.1)'
        },
        grid: {
            left: '2%',
            right: '3%',
            bottom: '10%',
            top: '8%',
            containLabel: true
        },
        dataZoom: [
            {
                type: 'inside',
                start: 0,
                end: 100
            },
            {
                type: 'slider',
                start: 0,
                end: 100,
                backgroundColor: 'rgba(17, 17, 17, 0.8)',
                dataBackground: {
                    lineStyle: { color: '#00c2ff', width: 1.5 },
                    areaStyle: { color: 'rgba(0, 194, 255, 0.1)' }
                },
                selectedDataBackground: {
                    lineStyle: { color: '#00c2ff', width: 2 },
                    areaStyle: { color: 'rgba(0, 194, 255, 0.3)' }
                },
                fillerColor: 'rgba(0, 194, 255, 0.15)',
                borderColor: 'rgba(255, 255, 255, 0.1)',
                handleStyle: {
                    color: '#00c2ff',
                    borderColor: '#00c2ff',
                    shadowBlur: 8,
                    shadowColor: 'rgba(0, 194, 255, 0.5)'
                },
                textStyle: { color: '#b0b0b0' }
            }
        ],
        xAxis: {
            type: 'time',
            boundaryGap: false,
            axisLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.1)', width: 1 } },
            axisTick: { lineStyle: { color: 'rgba(255, 255, 255, 0.1)' } },
            axisLabel: {
                color: '#808080',
                fontSize: 11,
                formatter: function(value) {
                    const date = new Date(value);
                    return date.toLocaleTimeString('en-US', {
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit'
                    });
                }
            }
        },
        yAxis: {
            type: 'value',
            scale: true,
            axisLine: { show: false },
            axisTick: { show: false },
            splitLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.05)', width: 1 } },
            axisLabel: {
                color: '#808080',
                fontSize: 11,
                formatter: function(value) {
                    return '$' + value.toFixed(4);
                }
            }
        },
        series: [
            {
                name: 'Price',
                type: 'line',
                data: [],
                smooth: false,
                symbol: 'none',
                lineStyle: { color: '#00c2ff', width: 2 },
                areaStyle: {
                    color: {
                        type: 'linear',
                        x: 0, y: 0, x2: 0, y2: 1,
                        colorStops: [
                            { offset: 0, color: 'rgba(0, 194, 255, 0.3)' },
                            { offset: 1, color: 'rgba(0, 194, 255, 0)' }
                        ]
                    }
                }
            },
            {
                name: 'Market Buy',
                type: 'scatter',
                data: [],
                symbol: 'circle',
                symbolSize: 12,
                itemStyle: {
                    color: '#00c2ff',
                    shadowBlur: 10,
                    shadowColor: 'rgba(0, 194, 255, 0.5)'
                }
            },
            {
                name: 'Market Sell',
                type: 'scatter',
                data: [],
                symbol: 'circle',
                symbolSize: 12,
                itemStyle: {
                    color: '#cc6699',
                    shadowBlur: 10,
                    shadowColor: 'rgba(204, 102, 153, 0.5)'
                }
            },
            {
                name: 'Bid Event',
                type: 'scatter',
                data: [],
                symbol: 'triangle',
                symbolSize: 10,
                itemStyle: {
                    color: '#00ff88',
                    shadowBlur: 8,
                    shadowColor: 'rgba(0, 255, 136, 0.4)'
                }
            },
            {
                name: 'Ask Event',
                type: 'scatter',
                data: [],
                symbol: 'triangle',
                symbolRotate: 180,
                symbolSize: 10,
                itemStyle: {
                    color: '#ff4444',
                    shadowBlur: 8,
                    shadowColor: 'rgba(255, 68, 68, 0.4)'
                }
            }
        ]
    };
}

// Format tooltip
function formatTooltip(params) {
    if (!params || params.length === 0) return '';

    const time = new Date(params[0].value[0]).toLocaleTimeString();
    let html = `<div style="font-weight: bold; margin-bottom: 8px;">${time}</div>`;

    params.forEach(param => {
        const value = param.value[1];
        const color = param.color;
        html += `
            <div style="display: flex; align-items: center; margin: 4px 0;">
                <span style="display: inline-block; width: 10px; height: 10px; background: ${color}; border-radius: 50%; margin-right: 8px;"></span>
                <span>${param.seriesName}: <strong>$${value.toFixed(6)}</strong></span>
            </div>
        `;
    });

    return html;
}

// Fetch price history
async function fetchPriceHistory() {
    try {
        const response = await fetch(`/api/live/price-history?symbol=${config.symbol}&lookback=${config.lookback}`);
        const data = await response.json();

        if (data.error) {
            showError('Error fetching price history: ' + data.error);
            return;
        }

        priceData = data.data || [];
    } catch (error) {
        console.error('Error fetching price history:', error);
        showError('Failed to fetch price history');
    }
}

// Fetch whale events
async function fetchWhaleEvents(incremental = false) {
    try {
        let url = `/api/live/whale-events?symbol=${config.symbol}&lookback=${config.lookback}&min_usd=${config.minUsd}`;

        if (incremental && lastUpdateTime) {
            url += `&last_timestamp=${encodeURIComponent(lastUpdateTime)}`;
        }

        const response = await fetch(url);
        const data = await response.json();

        if (data.error) {
            showError('Error fetching whale events: ' + data.error);
            return;
        }

        if (data.is_incremental) {
            // Append new events
            whaleEvents = whaleEvents.concat(data.events || []);

            // Remove old events outside lookback window
            const cutoffTime = new Date(Date.now() - parseLookback(config.lookback));
            whaleEvents = whaleEvents.filter(e => new Date(e.time) > cutoffTime);
        } else {
            // Full reload
            whaleEvents = data.events || [];
        }

        // Update last timestamp
        if (whaleEvents.length > 0) {
            const times = whaleEvents.map(e => new Date(e.time));
            lastUpdateTime = new Date(Math.max(...times)).toISOString();
        }
    } catch (error) {
        console.error('Error fetching whale events:', error);
        showError('Failed to fetch whale events');
    }
}

// Parse lookback string to milliseconds
function parseLookback(lookback) {
    const unit = lookback.slice(-1);
    const value = parseInt(lookback.slice(0, -1));

    switch(unit) {
        case 's': return value * 1000;
        case 'm': return value * 60 * 1000;
        case 'h': return value * 60 * 60 * 1000;
        case 'd': return value * 24 * 60 * 60 * 1000;
        default: return 5 * 60 * 1000;
    }
}

// Update chart with latest data
function updateChart() {
    if (!chart || priceData.length === 0) return;

    // Prepare price data
    const chartData = priceData.map(p => [new Date(p.time), p.price]);

    // Categorize events
    const marketBuys = whaleEvents.filter(e => e.event_type === 'market_buy' || e.side === 'buy');
    const marketSells = whaleEvents.filter(e => e.event_type === 'market_sell' || e.side === 'sell');
    const bidEvents = whaleEvents.filter(e => e.side === 'bid');
    const askEvents = whaleEvents.filter(e => e.side === 'ask');

    // Sort by USD value and take top events
    const topMarketBuys = marketBuys.sort((a, b) => b.usd_value - a.usd_value).slice(0, 10);
    const topMarketSells = marketSells.sort((a, b) => b.usd_value - a.usd_value).slice(0, 10);
    const topBids = bidEvents.sort((a, b) => b.usd_value - a.usd_value).slice(0, 20);
    const topAsks = askEvents.sort((a, b) => b.usd_value - a.usd_value).slice(0, 20);

    // Map events to price points
    function mapEventsToChart(events) {
        return events.map(e => {
            const eventTime = new Date(e.time);
            // Find closest price point
            let closestPrice = null;
            let minDiff = Infinity;

            for (const p of priceData) {
                const diff = Math.abs(new Date(p.time) - eventTime);
                if (diff < minDiff && diff < 5000) { // Within 5 seconds
                    minDiff = diff;
                    closestPrice = p.price;
                }
            }

            return closestPrice ? [eventTime, closestPrice] : null;
        }).filter(p => p !== null);
    }

    // Update chart
    chart.setOption({
        series: [
            { data: chartData },
            { data: mapEventsToChart(topMarketBuys) },
            { data: mapEventsToChart(topMarketSells) },
            { data: mapEventsToChart(topBids) },
            { data: mapEventsToChart(topAsks) }
        ]
    });
}

// Update event list
function updateEventList() {
    const eventListEl = document.getElementById('event-list');
    if (!eventListEl) return;

    // Get all events and sort by time (most recent first)
    const allEvents = [...whaleEvents].sort((a, b) => new Date(b.time) - new Date(a.time));

    // Take top 30
    const topEvents = allEvents.slice(0, 30);

    if (topEvents.length === 0) {
        eventListEl.innerHTML = '<div style="padding: 2rem; text-align: center; color: #808080;">No whale events found</div>';
        return;
    }

    eventListEl.innerHTML = topEvents.map(e => {
        const time = new Date(e.time).toLocaleTimeString();
        let eventClass = 'whale-event-item';
        let eventColor = '';
        let eventLabel = '';

        if (e.event_type === 'market_buy' || e.side === 'buy') {
            eventColor = '#00c2ff';
            eventLabel = 'BUY';
        } else if (e.event_type === 'market_sell' || e.side === 'sell') {
            eventColor = '#cc6699';
            eventLabel = 'SELL';
        } else if (e.side === 'bid') {
            eventColor = '#00ff88';
            eventLabel = 'BID+';
        } else if (e.side === 'ask') {
            eventColor = '#ff4444';
            eventLabel = 'ASK+';
        }

        return `
            <div class="${eventClass}" style="border-left: 3px solid ${eventColor};">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <span style="color: #808080; font-size: 0.9rem;">${time}</span>
                        <strong style="margin-left: 1rem; color: ${eventColor};">${eventLabel}</strong>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-weight: bold;">$${e.usd_value.toLocaleString()}</div>
                        <div style="color: #808080; font-size: 0.85rem;">@ $${e.price.toFixed(4)}</div>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// Update stats
function updateStats() {
    if (priceData.length === 0) return;

    const currentPrice = priceData[priceData.length - 1].price;
    const firstPrice = priceData[0].price;
    const priceChange = currentPrice - firstPrice;
    const priceChangePct = (priceChange / firstPrice) * 100;

    // Calculate market flow
    const marketBuys = whaleEvents.filter(e => e.event_type === 'market_buy' || e.side === 'buy');
    const marketSells = whaleEvents.filter(e => e.event_type === 'market_sell' || e.side === 'sell');
    const bidEvents = whaleEvents.filter(e => e.side === 'bid');
    const askEvents = whaleEvents.filter(e => e.side === 'ask');

    const buyVolume = marketBuys.reduce((sum, e) => sum + e.usd_value, 0);
    const sellVolume = marketSells.reduce((sum, e) => sum + e.usd_value, 0);
    const netFlow = buyVolume - sellVolume;

    // Update DOM
    document.getElementById('stat-current-price').textContent = '$' + currentPrice.toFixed(6);

    const changeEl = document.getElementById('stat-price-change');
    changeEl.textContent = (priceChange >= 0 ? '+' : '') + priceChange.toFixed(6) +
                          ' (' + (priceChange >= 0 ? '+' : '') + priceChangePct.toFixed(2) + '%)';
    changeEl.style.color = priceChange >= 0 ? '#00ffa3' : '#ff3b69';

    document.getElementById('stat-total-events').textContent = whaleEvents.length.toLocaleString();

    const flowEl = document.getElementById('stat-net-flow');
    flowEl.textContent = (netFlow >= 0 ? '+' : '') + '$' + netFlow.toLocaleString();
    flowEl.style.color = netFlow >= 0 ? '#00ffa3' : '#ff3b69';

    document.getElementById('stat-data-points').textContent = priceData.length.toLocaleString();
    document.getElementById('stat-last-update').textContent = new Date().toLocaleTimeString();

    // Event stats
    document.getElementById('event-stat-buys').textContent = marketBuys.length;
    document.getElementById('event-stat-sells').textContent = marketSells.length;
    document.getElementById('event-stat-bids').textContent = bidEvents.length;
    document.getElementById('event-stat-asks').textContent = askEvents.length;

    // Update info panel
    document.getElementById('info-symbol').textContent = config.symbol;
    document.getElementById('info-lookback').textContent = `Last ${config.lookback}`;
    document.getElementById('info-min-usd').textContent = `Min: $${config.minUsd.toLocaleString()}`;
}

// Refresh data
async function refreshData(incremental = false) {
    await Promise.all([
        fetchPriceHistory(),
        fetchWhaleEvents(incremental)
    ]);

    updateChart();
    updateEventList();
    updateStats();
}

// Setup event listeners
function setupEventListeners() {
    // Symbol selector
    document.getElementById('symbol-select').addEventListener('change', (e) => {
        config.symbol = e.target.value;
        lastUpdateTime = null;
        refreshData(false);
    });

    // Lookback selector
    document.getElementById('lookback-select').addEventListener('change', (e) => {
        config.lookback = e.target.value;
        lastUpdateTime = null;
        refreshData(false);
    });

    // Min USD input
    document.getElementById('min-usd-input').addEventListener('change', (e) => {
        config.minUsd = parseFloat(e.target.value) || 5000;
        lastUpdateTime = null;
        refreshData(false);
    });

    // Refresh button
    document.getElementById('refresh-btn').addEventListener('click', () => {
        lastUpdateTime = null;
        refreshData(false);
    });

    // Fullscreen toggle
    document.getElementById('fullscreen-btn').addEventListener('click', () => {
        const wrapper = document.querySelector('.chart-wrapper');
        if (!document.fullscreenElement) {
            wrapper.requestFullscreen().then(() => {
                chart.resize();
            });
        } else {
            document.exitFullscreen().then(() => {
                chart.resize();
            });
        }
    });
}

// Show/hide loading
function showLoading(show) {
    const loading = document.getElementById('loading');
    if (loading) {
        loading.style.display = show ? 'flex' : 'none';
    }
}

// Show error toast
function showError(message) {
    const toast = document.getElementById('error-toast');
    const messageEl = document.getElementById('error-message');

    messageEl.textContent = message;
    toast.style.display = 'flex';

    setTimeout(() => {
        toast.style.display = 'none';
    }, 5000);
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (updateInterval) {
        clearInterval(updateInterval);
    }
    if (chart) {
        chart.dispose();
    }
});
