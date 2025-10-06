// Live Chart Dashboard - Shows price with whale events
let priceChart = null;
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

// Initialize chart
function initChart() {
    const ctx = document.getElementById('priceChart').getContext('2d');

    priceChart = new Chart(ctx, {
        type: 'line',
        data: {
            datasets: [
                {
                    label: 'Price',
                    data: [],
                    borderColor: 'rgb(88, 166, 255)',
                    backgroundColor: 'rgba(88, 166, 255, 0.1)',
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.1,
                    yAxisID: 'y'
                },
                {
                    label: 'Market Buys',
                    data: [],
                    backgroundColor: 'rgb(88, 166, 255)',
                    borderColor: 'rgb(88, 166, 255)',
                    pointRadius: 8,
                    pointStyle: 'circle',
                    showLine: false,
                    yAxisID: 'y'
                },
                {
                    label: 'Market Sells',
                    data: [],
                    backgroundColor: 'rgb(204, 102, 153)',
                    borderColor: 'rgb(204, 102, 153)',
                    pointRadius: 8,
                    pointStyle: 'circle',
                    showLine: false,
                    yAxisID: 'y'
                },
                {
                    label: 'Bid Events',
                    data: [],
                    backgroundColor: 'rgb(63, 185, 80)',
                    borderColor: 'rgb(63, 185, 80)',
                    pointRadius: 6,
                    pointStyle: 'triangle',
                    showLine: false,
                    yAxisID: 'y'
                },
                {
                    label: 'Ask Events',
                    data: [],
                    backgroundColor: 'rgb(248, 81, 73)',
                    borderColor: 'rgb(248, 81, 73)',
                    pointRadius: 6,
                    pointStyle: 'triangle',
                    rotation: 180,
                    showLine: false,
                    yAxisID: 'y'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: '#c9d1d9'
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.parsed.y !== null) {
                                label += '$' + context.parsed.y.toFixed(6);
                            }
                            return label;
                        }
                    }
                }
            },
            scales: {
                x: {
                    type: 'time',
                    time: {
                        displayFormats: {
                            second: 'HH:mm:ss',
                            minute: 'HH:mm'
                        }
                    },
                    grid: {
                        color: '#30363d'
                    },
                    ticks: {
                        color: '#8b949e'
                    }
                },
                y: {
                    grid: {
                        color: '#30363d'
                    },
                    ticks: {
                        color: '#8b949e',
                        callback: function(value) {
                            return '$' + value.toFixed(4);
                        }
                    }
                }
            }
        }
    });
}

// Fetch price history
async function fetchPriceHistory() {
    try {
        const response = await fetch(`/api/live/price-history?symbol=${config.symbol}&lookback=${config.lookback}`);
        const data = await response.json();

        if (data.error) {
            console.error('Error fetching price history:', data.error);
            return;
        }

        priceData = data.data || [];
        updateChart();
    } catch (error) {
        console.error('Error fetching price history:', error);
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
            console.error('Error fetching whale events:', data.error);
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

        updateChart();
        updateEventList();
        updateStats();
    } catch (error) {
        console.error('Error fetching whale events:', error);
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
        default: return 5 * 60 * 1000; // default 5 minutes
    }
}

// Update chart with latest data
function updateChart() {
    if (!priceChart) return;

    // Update price line
    priceChart.data.datasets[0].data = priceData.map(d => ({
        x: new Date(d.time),
        y: d.price
    }));

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

    // Map events to chart points (use mid price at that time)
    function mapEventsToPrice(events) {
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

            return closestPrice ? { x: eventTime, y: closestPrice } : null;
        }).filter(p => p !== null);
    }

    // Update event datasets
    priceChart.data.datasets[1].data = mapEventsToPrice(topMarketBuys);
    priceChart.data.datasets[2].data = mapEventsToPrice(topMarketSells);
    priceChart.data.datasets[3].data = mapEventsToPrice(topBids);
    priceChart.data.datasets[4].data = mapEventsToPrice(topAsks);

    priceChart.update('none'); // Update without animation for smoother live updates
}

// Update event list
function updateEventList() {
    const eventListEl = document.getElementById('eventList');

    // Get all events and sort by time (most recent first)
    const allEvents = [...whaleEvents].sort((a, b) => new Date(b.time) - new Date(a.time));

    // Take top 20
    const topEvents = allEvents.slice(0, 20);

    eventListEl.innerHTML = topEvents.map(e => {
        const time = new Date(e.time).toLocaleTimeString();
        let eventClass = '';
        let eventLabel = '';

        if (e.event_type === 'market_buy' || e.side === 'buy') {
            eventClass = 'event-buy';
            eventLabel = 'BUY';
        } else if (e.event_type === 'market_sell' || e.side === 'sell') {
            eventClass = 'event-sell';
            eventLabel = 'SELL';
        } else if (e.side === 'bid') {
            eventClass = 'event-bid';
            eventLabel = 'BID+';
        } else if (e.side === 'ask') {
            eventClass = 'event-ask';
            eventLabel = 'ASK+';
        }

        return `
            <div class="event-item ${eventClass}">
                <span style="color: #8b949e">${time}</span>
                <strong style="margin-left: 1rem">${eventLabel}</strong>
                <span style="margin-left: 1rem">$${e.usd_value.toLocaleString()}</span>
                <span style="margin-left: 1rem; color: #8b949e">@ $${e.price.toFixed(2)}</span>
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

    const buyVolume = marketBuys.reduce((sum, e) => sum + e.usd_value, 0);
    const sellVolume = marketSells.reduce((sum, e) => sum + e.usd_value, 0);
    const netFlow = buyVolume - sellVolume;

    // Update DOM
    document.getElementById('currentPrice').textContent = '$' + currentPrice.toFixed(6);

    const priceChangeEl = document.getElementById('priceChange');
    const changeClass = priceChange >= 0 ? 'positive' : 'negative';
    priceChangeEl.className = 'stat-value ' + changeClass;
    priceChangeEl.textContent = (priceChange >= 0 ? '+' : '') + priceChange.toFixed(6) +
                                 ' (' + (priceChange >= 0 ? '+' : '') + priceChangePct.toFixed(2) + '%)';

    document.getElementById('totalEvents').textContent = whaleEvents.length.toLocaleString();

    const netFlowEl = document.getElementById('netFlow');
    const flowClass = netFlow >= 0 ? 'positive' : 'negative';
    netFlowEl.className = 'stat-value ' + flowClass;
    netFlowEl.textContent = (netFlow >= 0 ? '+' : '') + '$' + netFlow.toLocaleString();
}

// Refresh data
async function refreshData(incremental = false) {
    await Promise.all([
        fetchPriceHistory(),
        fetchWhaleEvents(incremental)
    ]);
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initChart();

    // Load initial data
    refreshData(false);

    // Set up auto-refresh
    updateInterval = setInterval(() => {
        refreshData(true);
    }, config.refreshInterval);

    // Event listeners
    document.getElementById('symbolSelect').addEventListener('change', (e) => {
        config.symbol = e.target.value;
        lastUpdateTime = null;
        refreshData(false);
    });

    document.getElementById('lookbackSelect').addEventListener('change', (e) => {
        config.lookback = e.target.value;
        lastUpdateTime = null;
        refreshData(false);
    });

    document.getElementById('minUsdInput').addEventListener('change', (e) => {
        config.minUsd = parseFloat(e.target.value) || 5000;
        lastUpdateTime = null;
        refreshData(false);
    });

    document.getElementById('refreshBtn').addEventListener('click', () => {
        lastUpdateTime = null;
        refreshData(false);
    });
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (updateInterval) {
        clearInterval(updateInterval);
    }
});
