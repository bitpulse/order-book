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

    // Handle click events on whale events
    chart.on('click', function(params) {
        // Only handle clicks on scatter series (whale events)
        if (params.componentType === 'series' && params.seriesType === 'scatter') {
            const eventData = params.data[2]; // Third element contains metadata
            if (eventData && eventData.originalEvent) {
                showEventModal(eventData.originalEvent, params.seriesName);
            }
        }
    });

    // Change cursor on hover over whale events
    chart.on('mouseover', function(params) {
        if (params.componentType === 'series' && params.seriesType === 'scatter') {
            chartContainer.style.cursor = 'pointer';
        }
    });

    chart.on('mouseout', function(params) {
        chartContainer.style.cursor = 'default';
    });

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
            // Price line
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
                },
                z: 1
            },
            // DEFINITIVE EVENTS (Bright colors) - High certainty of whale action
            // Market Buy - Aggressive buy order executed immediately
            {
                name: 'Market Buy',
                type: 'scatter',
                data: [],
                symbol: 'circle',
                symbolSize: function(data) {
                    return data[2]?.size || 12;
                },
                itemStyle: {
                    color: function(params) {
                        return params.data[2]?.color || '#00c2ff';
                    }
                },
                z: 10
            },
            // Market Sell - Aggressive sell order executed immediately
            {
                name: 'Market Sell',
                type: 'scatter',
                data: [],
                symbol: 'circle',
                symbolSize: function(data) {
                    return data[2]?.size || 12;
                },
                itemStyle: {
                    color: function(params) {
                        return params.data[2]?.color || '#ff00ff';
                    }
                },
                z: 10
            },
            // New Bid - Fresh buy order placed (never seen this price before)
            {
                name: 'New Bid',
                type: 'scatter',
                data: [],
                symbol: 'triangle',
                symbolSize: function(data) {
                    return data[2]?.size || 10;
                },
                itemStyle: {
                    color: function(params) {
                        return params.data[2]?.color || '#00ff88';
                    }
                },
                z: 9
            },
            // New Ask - Fresh sell order placed (never seen this price before)
            {
                name: 'New Ask',
                type: 'scatter',
                data: [],
                symbol: 'triangle',
                symbolSize: function(data) {
                    return data[2]?.size || 10;
                },
                itemStyle: {
                    color: function(params) {
                        return params.data[2]?.color || '#ff4444';
                    }
                },
                z: 9
            },
            // AMBIGUOUS EVENTS (Muted colors) - Could be modifications, cancellations, or fills
            // Bid Increase / Ask Decrease - Potential support building
            {
                name: 'Bid Increase',
                type: 'scatter',
                data: [],
                symbol: 'diamond',
                symbolSize: function(data) {
                    return data[2]?.size || 8;
                },
                itemStyle: {
                    color: function(params) {
                        return params.data[2]?.color || '#88cc88';
                    }
                },
                z: 6
            },
            // Ask Increase / Bid Decrease - Potential resistance building
            {
                name: 'Ask Increase',
                type: 'scatter',
                data: [],
                symbol: 'diamond',
                symbolSize: function(data) {
                    return data[2]?.size || 8;
                },
                itemStyle: {
                    color: function(params) {
                        return params.data[2]?.color || '#cc8888';
                    }
                },
                z: 6
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

        // Check if this is an event with metadata (third element in array)
        if (param.data && param.data[2] && param.data[2].originalEvent) {
            const event = param.data[2].originalEvent;
            html += `
                <div style="border-left: 3px solid ${color}; padding-left: 8px; margin: 8px 0;">
                    <div style="font-weight: bold; color: ${color}; margin-bottom: 4px;">${param.seriesName}</div>
                    <div style="margin: 2px 0;"><strong>Price:</strong> $${event.price.toFixed(6)}</div>
                    <div style="margin: 2px 0;"><strong>Volume:</strong> ${event.volume.toFixed(4)}</div>
                    <div style="margin: 2px 0;"><strong>USD Value:</strong> $${event.usd_value.toLocaleString()}</div>
                    <div style="margin: 2px 0; color: #00ffa3; font-size: 0.85rem;">Click for details</div>
                </div>
            `;
        } else {
            // Regular price point
            html += `
                <div style="display: flex; align-items: center; margin: 4px 0;">
                    <span style="display: inline-block; width: 10px; height: 10px; background: ${color}; border-radius: 50%; margin-right: 8px;"></span>
                    <span>${param.seriesName}: <strong>$${value.toFixed(6)}</strong></span>
                </div>
            `;
        }
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

// Prepare whale event scatter data (matching chart.js pattern)
function prepareWhaleScatterData(events) {
    if (!events || events.length === 0) return [];

    // Sort by time
    const sortedEvents = [...events].sort((a, b) => new Date(a.time) - new Date(b.time));

    // Find min and max USD values for scaling
    const usdValues = sortedEvents.map(e => e.usd_value);
    const minUsd = Math.min(...usdValues);
    const maxUsd = Math.max(...usdValues);

    return sortedEvents.map(event => {
        const isMarketBuy = event.event_type === 'market_buy';
        const isMarketSell = event.event_type === 'market_sell';
        const isNewBid = event.event_type === 'new_bid';
        const isNewAsk = event.event_type === 'new_ask';
        const isIncrease = event.event_type === 'increase';
        const isDecrease = event.event_type === 'decrease';
        const isBid = event.side === 'bid' || event.event_type.includes('bid');
        const isAsk = event.side === 'ask' || event.event_type.includes('ask');

        let color, symbol;

        // DEFINITIVE EVENTS - Bright colors
        if (isMarketBuy) {
            color = '#00c2ff'; // Bright cyan/blue
            symbol = 'circle';
        } else if (isMarketSell) {
            color = '#ff00ff'; // Bright magenta/pink
            symbol = 'circle';
        } else if (isNewBid || (isBid && !isIncrease && !isDecrease)) {
            color = '#00ff88'; // Bright green
            symbol = 'triangle';
        } else if (isNewAsk || (isAsk && !isIncrease && !isDecrease)) {
            color = '#ff4444'; // Bright red
            symbol = 'triangle';
        }
        // AMBIGUOUS EVENTS - Muted colors (volume changes)
        else if (isIncrease && isBid) {
            color = '#88cc88'; // Muted green (potential support)
            symbol = 'diamond';
        } else if (isIncrease && isAsk) {
            color = '#cc8888'; // Muted red (potential resistance)
            symbol = 'diamond';
        } else if (isDecrease && isBid) {
            color = '#cc8888'; // Muted red (support weakening)
            symbol = 'diamond';
        } else if (isDecrease && isAsk) {
            color = '#88cc88'; // Muted green (resistance weakening)
            symbol = 'diamond';
        } else {
            // Fallback for other event types
            color = '#ffaa00'; // Orange (unknown)
            symbol = 'circle';
        }

        // Calculate size based on USD value (logarithmic scale)
        const baseSize = 12;
        const minSize = 8;
        const maxSize = 24;

        let size;
        if (maxUsd === minUsd) {
            // All values are the same
            size = baseSize;
        } else {
            // Logarithmic scaling for better distribution
            const normalizedValue = (Math.log(event.usd_value + 1) - Math.log(minUsd + 1)) /
                                   (Math.log(maxUsd + 1) - Math.log(minUsd + 1));
            size = minSize + (maxSize - minSize) * normalizedValue;
        }

        const eventTime = new Date(event.time);

        return {
            time: eventTime,
            price: event.price,
            color: color,
            symbol: symbol,
            size: size,
            originalEvent: event
        };
    });
}

// Update chart with latest data
function updateChart() {
    if (!chart || priceData.length === 0) return;

    // Prepare price data
    const chartData = priceData.map(p => [new Date(p.time), p.price]);

    // Categorize events by type
    const marketBuys = whaleEvents.filter(e => e.event_type === 'market_buy');
    const marketSells = whaleEvents.filter(e => e.event_type === 'market_sell');
    const newBids = whaleEvents.filter(e => e.event_type === 'new_bid' || (e.side === 'bid' && !e.event_type.includes('increase') && !e.event_type.includes('decrease')));
    const newAsks = whaleEvents.filter(e => e.event_type === 'new_ask' || (e.side === 'ask' && !e.event_type.includes('increase') && !e.event_type.includes('decrease')));

    // Volume changes (ambiguous events)
    const bidIncreases = whaleEvents.filter(e => e.event_type === 'increase' && e.side === 'bid');
    const askIncreases = whaleEvents.filter(e => e.event_type === 'increase' && e.side === 'ask');
    const askDecreases = whaleEvents.filter(e => e.event_type === 'decrease' && e.side === 'ask');
    const bidDecreases = whaleEvents.filter(e => e.event_type === 'decrease' && e.side === 'bid');

    // Combine for ambiguous categories
    const bidIncreasesAll = [...bidIncreases, ...askDecreases]; // Support building
    const askIncreasesAll = [...askIncreases, ...bidDecreases]; // Resistance building

    // Prepare scatter data
    const scatterMarketBuys = prepareWhaleScatterData(marketBuys);
    const scatterMarketSells = prepareWhaleScatterData(marketSells);
    const scatterNewBids = prepareWhaleScatterData(newBids);
    const scatterNewAsks = prepareWhaleScatterData(newAsks);
    const scatterBidIncreases = prepareWhaleScatterData(bidIncreasesAll);
    const scatterAskIncreases = prepareWhaleScatterData(askIncreasesAll);

    // Update chart using the same data structure as chart.js: [time, price, metadata]
    chart.setOption({
        series: [
            { data: chartData }, // Price line
            { data: scatterMarketBuys.map(e => [e.time, e.price, e]) }, // Market Buy
            { data: scatterMarketSells.map(e => [e.time, e.price, e]) }, // Market Sell
            { data: scatterNewBids.map(e => [e.time, e.price, e]) }, // New Bid
            { data: scatterNewAsks.map(e => [e.time, e.price, e]) }, // New Ask
            { data: scatterBidIncreases.map(e => [e.time, e.price, e]) }, // Bid Increase
            { data: scatterAskIncreases.map(e => [e.time, e.price, e]) } // Ask Increase
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
        let eventColor = '';
        let eventLabel = '';
        let eventSymbol = '';

        // Match the chart categorization
        const isMarketBuy = e.event_type === 'market_buy';
        const isMarketSell = e.event_type === 'market_sell';
        const isNewBid = e.event_type === 'new_bid';
        const isNewAsk = e.event_type === 'new_ask';
        const isIncrease = e.event_type === 'increase';
        const isDecrease = e.event_type === 'decrease';
        const isBid = e.side === 'bid';
        const isAsk = e.side === 'ask';

        if (isMarketBuy) {
            eventColor = '#00c2ff';
            eventLabel = 'MARKET BUY';
            eventSymbol = '●';
        } else if (isMarketSell) {
            eventColor = '#ff00ff';
            eventLabel = 'MARKET SELL';
            eventSymbol = '●';
        } else if (isNewBid || (isBid && !isIncrease && !isDecrease)) {
            eventColor = '#00ff88';
            eventLabel = 'NEW BID';
            eventSymbol = '▲';
        } else if (isNewAsk || (isAsk && !isIncrease && !isDecrease)) {
            eventColor = '#ff4444';
            eventLabel = 'NEW ASK';
            eventSymbol = '▼';
        } else if (isIncrease && isBid) {
            eventColor = '#88cc88';
            eventLabel = 'BID INCREASE';
            eventSymbol = '◆';
        } else if (isIncrease && isAsk) {
            eventColor = '#cc8888';
            eventLabel = 'ASK INCREASE';
            eventSymbol = '◆';
        } else if (isDecrease && isBid) {
            eventColor = '#cc8888';
            eventLabel = 'BID DECREASE';
            eventSymbol = '◆';
        } else if (isDecrease && isAsk) {
            eventColor = '#88cc88';
            eventLabel = 'ASK DECREASE';
            eventSymbol = '◆';
        } else {
            eventColor = '#ffaa00';
            eventLabel = e.event_type.toUpperCase().replace('_', ' ');
            eventSymbol = '●';
        }

        return `
            <div class="whale-event-item" style="border-left: 3px solid ${eventColor};">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <span style="color: #808080; font-size: 0.9rem;">${time}</span>
                        <strong style="margin-left: 1rem; color: ${eventColor};">${eventSymbol} ${eventLabel}</strong>
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

    // Calculate market flow using proper categorization
    const marketBuys = whaleEvents.filter(e => e.event_type === 'market_buy');
    const marketSells = whaleEvents.filter(e => e.event_type === 'market_sell');
    const newBids = whaleEvents.filter(e => e.event_type === 'new_bid' || (e.side === 'bid' && !e.event_type.includes('increase') && !e.event_type.includes('decrease')));
    const newAsks = whaleEvents.filter(e => e.event_type === 'new_ask' || (e.side === 'ask' && !e.event_type.includes('increase') && !e.event_type.includes('decrease')));
    const bidIncreases = whaleEvents.filter(e => e.event_type === 'increase' && e.side === 'bid');
    const askIncreases = whaleEvents.filter(e => e.event_type === 'increase' && e.side === 'ask');

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

    // Event stats - matching new categorization
    document.getElementById('event-stat-buys').textContent = marketBuys.length;
    document.getElementById('event-stat-sells').textContent = marketSells.length;
    document.getElementById('event-stat-bids').textContent = newBids.length + bidIncreases.length;
    document.getElementById('event-stat-asks').textContent = newAsks.length + askIncreases.length;

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

// Show event detail modal (matching chart.js styling)
function showEventModal(event, seriesName) {
    // Create modal if it doesn't exist
    let modal = document.getElementById('event-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'event-modal';
        modal.innerHTML = `
            <div class="modal-backdrop" onclick="document.getElementById('event-modal').style.display='none'"></div>
            <div class="modal-content">
                <div class="modal-header">
                    <h3 id="modal-title">Whale Event Details</h3>
                    <button class="modal-close" onclick="document.getElementById('event-modal').style.display='none'">&times;</button>
                </div>
                <div class="modal-body" id="modal-body"></div>
            </div>
        `;
        document.body.appendChild(modal);
    }

    // Determine event color and label
    const isMarketBuy = event.event_type === 'market_buy';
    const isMarketSell = event.event_type === 'market_sell';
    const isBid = event.side === 'bid';
    const isAsk = event.side === 'ask';

    let sideColor = '#00c2ff';
    if (isMarketBuy) sideColor = '#00c2ff';
    else if (isMarketSell) sideColor = '#ff00ff';
    else if (isBid) sideColor = '#00ff88';
    else if (isAsk) sideColor = '#ff4444';

    const time = new Date(event.time).toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    });

    function formatNumber(num) {
        if (num >= 1000000) return (num / 1000000).toFixed(2) + 'M';
        if (num >= 1000) return (num / 1000).toFixed(2) + 'K';
        return num.toFixed(2);
    }

    // Format modal content (matching chart.js exactly)
    const modalBody = document.getElementById('modal-body');
    modalBody.innerHTML = `
        <div style="background: rgba(255, 255, 255, 0.03); padding: 1.5rem; border-radius: 8px; border-left: 4px solid ${sideColor};">
            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 1.5rem;">
                <div>
                    <div style="color: #808080; font-size: 0.75rem; text-transform: uppercase; margin-bottom: 0.5rem;">Event Type</div>
                    <div style="color: ${sideColor}; font-size: 1.1rem; font-weight: 600; text-transform: uppercase;">${event.event_type.replace('_', ' ')}</div>
                </div>
                <div>
                    <div style="color: #808080; font-size: 0.75rem; text-transform: uppercase; margin-bottom: 0.5rem;">Time</div>
                    <div style="color: #e0e0e0; font-size: 1.1rem; font-family: 'Courier New', monospace;">${time}</div>
                </div>
                <div>
                    <div style="color: #808080; font-size: 0.75rem; text-transform: uppercase; margin-bottom: 0.5rem;">Price</div>
                    <div style="color: #e0e0e0; font-size: 1.1rem; font-weight: 600;">$${event.price.toFixed(6)}</div>
                </div>
                <div>
                    <div style="color: #808080; font-size: 0.75rem; text-transform: uppercase; margin-bottom: 0.5rem;">Volume</div>
                    <div style="color: #e0e0e0; font-size: 1.1rem; font-weight: 600;">${formatNumber(event.volume)}</div>
                </div>
                <div>
                    <div style="color: #808080; font-size: 0.75rem; text-transform: uppercase; margin-bottom: 0.5rem;">USD Value</div>
                    <div style="color: ${sideColor}; font-size: 1.3rem; font-weight: 700;">$${formatNumber(event.usd_value)}</div>
                </div>
                ${event.distance_from_mid_pct !== undefined ? `
                <div>
                    <div style="color: #808080; font-size: 0.75rem; text-transform: uppercase; margin-bottom: 0.5rem;">Distance from Mid</div>
                    <div style="color: #e0e0e0; font-size: 1.1rem; font-weight: 600;">${event.distance_from_mid_pct.toFixed(3)}%</div>
                </div>
                ` : ''}
            </div>
        </div>
    `;

    // Show modal
    modal.style.display = 'flex';
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
