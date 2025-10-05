// Live Order Book Dashboard - Real-time data from InfluxDB

let chart = null;
let refreshInterval = null;
let isAutoRefresh = true;
let currentSymbol = 'SPX_USDT';
let currentLookback = '30m';
let lastPriceData = [];
let lastWhaleEvents = [];
let lastWhaleEventTimestamp = null;  // Track latest event timestamp for incremental updates
let isInitialLoad = true;

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    initializeChart();
    setupEventListeners();
    loadAllData();
    startAutoRefresh();
});

// Setup event listeners
function setupEventListeners() {
    // Symbol selector
    document.getElementById('symbol-selector').addEventListener('change', (e) => {
        currentSymbol = e.target.value;
        // Reset incremental loading when symbol changes
        lastWhaleEventTimestamp = null;
        isInitialLoad = true;
        lastWhaleEvents = [];
        loadAllData();
    });

    // Lookback selector
    document.getElementById('lookback-selector').addEventListener('change', (e) => {
        currentLookback = e.target.value;
        // Reset incremental loading when lookback changes
        lastWhaleEventTimestamp = null;
        isInitialLoad = true;
        lastWhaleEvents = [];
        loadAllData();
    });

    // Auto-refresh toggle
    document.getElementById('refresh-toggle').addEventListener('click', () => {
        isAutoRefresh = !isAutoRefresh;
        updateRefreshButton();
        if (isAutoRefresh) {
            startAutoRefresh();
        } else {
            stopAutoRefresh();
        }
    });

    // Manual refresh
    document.getElementById('refresh-now').addEventListener('click', () => {
        loadAllData();
    });

    // Chart fullscreen
    document.getElementById('chart-fullscreen').addEventListener('click', () => {
        toggleFullscreen();
    });

    // Min USD filter
    document.getElementById('min-usd-filter').addEventListener('change', () => {
        loadWhaleEvents();
    });

    // Event type filter
    document.getElementById('event-type-filter').addEventListener('change', () => {
        filterEvents();
    });
}

// Initialize ECharts
function initializeChart() {
    const container = document.getElementById('price-chart');
    if (!container) {
        console.error('Chart container not found');
        return;
    }

    chart = echarts.init(container, 'dark');

    // Resize handler
    window.addEventListener('resize', () => {
        if (chart) {
            chart.resize();
        }
    });
}

// Load all data
async function loadAllData() {
    updateStatus('loading');
    await Promise.all([
        loadPriceHistory(),
        loadWhaleEvents(),
        loadOrderBook(),
        loadStats()
    ]);
    updateStatus('live');
    updateLastUpdateTime();
}

// Load price history
async function loadPriceHistory() {
    try {
        const response = await fetch(`/api/live/price-history?symbol=${currentSymbol}&lookback=${currentLookback}`);
        const data = await response.json();

        if (data.error) {
            console.error('Error loading price history:', data.error);
            return;
        }

        lastPriceData = data.data;
        renderPriceChart(data.data);
        updatePriceStats(data.data);

    } catch (error) {
        console.error('Error loading price history:', error);
    }
}

// Render price chart
function renderPriceChart(priceData) {
    if (!chart) {
        console.warn('Chart not initialized');
        return;
    }

    if (!priceData || priceData.length === 0) {
        console.warn('No price data available');
        // Show no data message
        const loading = document.getElementById('chart-loading');
        if (loading) {
            loading.innerHTML = '<div class="spinner"></div><p>No price data available. Make sure orderbook_tracker.py is running.</p>';
            loading.style.display = 'flex';
        }
        return;
    }

    const chartData = priceData.map(point => ({
        time: new Date(point.time),
        value: point.price
    }));

    const option = {
        backgroundColor: 'transparent',
        animation: false,
        tooltip: {
            trigger: 'axis',
            axisPointer: {
                type: 'cross'
            },
            backgroundColor: 'rgba(10, 10, 10, 0.95)',
            borderColor: 'rgba(0, 255, 163, 0.2)',
            borderWidth: 1,
            textStyle: {
                color: '#ffffff'
            },
            formatter: function(params) {
                if (!params || params.length === 0) return '';
                const point = params[0];
                const time = new Date(point.value[0]).toLocaleTimeString();
                const price = point.value[1];
                return `${time}<br/>Price: $${price.toFixed(6)}`;
            }
        },
        grid: {
            left: '2%',
            right: '3%',
            bottom: '10%',
            top: '5%',
            containLabel: true
        },
        xAxis: {
            type: 'time',
            boundaryGap: false,
            axisLine: {
                lineStyle: {
                    color: 'rgba(255, 255, 255, 0.1)'
                }
            },
            axisLabel: {
                color: '#808080',
                formatter: function(value) {
                    return new Date(value).toLocaleTimeString('en-US', {
                        hour: '2-digit',
                        minute: '2-digit'
                    });
                }
            }
        },
        yAxis: {
            type: 'value',
            scale: true,
            axisLine: {
                lineStyle: {
                    color: 'rgba(255, 255, 255, 0.1)'
                }
            },
            splitLine: {
                lineStyle: {
                    color: 'rgba(255, 255, 255, 0.05)',
                    type: 'dashed'
                }
            },
            axisLabel: {
                color: '#808080',
                formatter: function(value) {
                    return '$' + value.toFixed(6);
                }
            }
        },
        series: [
            {
                name: 'Price',
                type: 'line',
                data: chartData.map(d => [d.time, d.value]),
                lineStyle: {
                    color: '#00c2ff',
                    width: 2
                },
                itemStyle: {
                    color: '#00c2ff'
                },
                symbol: 'none',
                smooth: 0.3,
                areaStyle: {
                    color: {
                        type: 'linear',
                        x: 0,
                        y: 0,
                        x2: 0,
                        y2: 1,
                        colorStops: [
                            { offset: 0, color: 'rgba(0, 194, 255, 0.2)' },
                            { offset: 1, color: 'rgba(0, 194, 255, 0.01)' }
                        ]
                    }
                },
                z: 1
            },
            // Whale events scatter
            ...prepareWhaleScatterSeries(lastWhaleEvents)
        ]
    };

    chart.setOption(option);

    // Add click handler for whale event markers
    chart.off('click'); // Remove previous handlers
    chart.on('click', function(params) {
        if (params.componentType === 'series' && params.seriesName === 'Whale Events') {
            const eventData = params.data[2];
            if (eventData && eventData.originalEvent) {
                showEventDetailsModal(eventData.originalEvent);
            }
        }
    });

    // Hide loading indicator
    const loading = document.getElementById('chart-loading');
    if (loading) {
        loading.style.display = 'none';
    }
}

// Update price statistics
function updatePriceStats(priceData) {
    if (!priceData || priceData.length === 0) return;

    const latest = priceData[priceData.length - 1];
    const first = priceData[0];
    const latestPrice = latest.price;
    const firstPrice = first.price;
    const change = ((latestPrice - firstPrice) / firstPrice) * 100;

    document.getElementById('stat-price').textContent = '$' + latestPrice.toFixed(6);

    const changeElem = document.getElementById('stat-price-change');
    changeElem.textContent = (change >= 0 ? '+' : '') + change.toFixed(3) + '%';
    changeElem.className = 'stat-subvalue ' + (change >= 0 ? 'positive' : 'negative');
}

// Load whale events (with incremental update support)
async function loadWhaleEvents() {
    try {
        const minUsd = document.getElementById('min-usd-filter').value || 5000;

        // Build API URL
        let url = `/api/live/whale-events?symbol=${currentSymbol}&lookback=${currentLookback}&min_usd=${minUsd}`;

        // Add last_timestamp for incremental updates (if not initial load)
        if (lastWhaleEventTimestamp && !isInitialLoad) {
            // Properly encode the timestamp to preserve the + sign
            url += `&last_timestamp=${encodeURIComponent(lastWhaleEventTimestamp)}`;
        }

        const response = await fetch(url);
        const data = await response.json();

        if (data.error) {
            console.error('Error loading whale events:', data.error);
            return;
        }

        if (data.is_incremental && data.events.length > 0) {
            // Incremental update - append new events
            console.log(`Received ${data.count} new whale event(s)`);

            // Add new events to the beginning of the array (they're already sorted oldest first from API)
            lastWhaleEvents = [...lastWhaleEvents, ...data.events];

            // Keep only last 100 events to avoid memory issues
            if (lastWhaleEvents.length > 100) {
                lastWhaleEvents = lastWhaleEvents.slice(-100);
            }

            // Prepend new events to the feed (newest at top)
            prependWhaleEventsToFeed(data.events);

            // Update last timestamp
            const newestEvent = data.events[data.events.length - 1];
            lastWhaleEventTimestamp = newestEvent.time;

        } else if (!data.is_incremental) {
            // Initial load - replace all events
            console.log(`Initial load: ${data.count} whale events`);
            lastWhaleEvents = data.events;
            renderWhaleEvents(data.events);

            // Set initial timestamp (from newest event since they're sorted desc)
            if (data.events.length > 0) {
                lastWhaleEventTimestamp = data.events[0].time;
            }

            isInitialLoad = false;
        }

        // Update chart with whale event markers
        if (lastPriceData.length > 0) {
            renderPriceChart(lastPriceData);
        }

    } catch (error) {
        console.error('Error loading whale events:', error);
    }
}

// Render whale events (full replacement)
function renderWhaleEvents(events) {
    const feed = document.getElementById('events-feed');

    if (!events || events.length === 0) {
        feed.innerHTML = '<div class="no-events">No whale events found</div>';
        return;
    }

    feed.innerHTML = '';

    events.forEach(event => {
        const eventElem = createEventElement(event);
        feed.appendChild(eventElem);
    });
}

// Prepend new whale events to feed (for incremental updates)
function prependWhaleEventsToFeed(newEvents) {
    const feed = document.getElementById('events-feed');

    // Remove "no events" message if present
    const noEventsMsg = feed.querySelector('.no-events');
    if (noEventsMsg) {
        noEventsMsg.remove();
    }

    // Prepend new events in reverse order (so newest is at top)
    newEvents.reverse().forEach(event => {
        const eventElem = createEventElement(event);

        // Add animation class for visual feedback
        eventElem.classList.add('new-event-animation');

        // Insert at the beginning
        feed.insertBefore(eventElem, feed.firstChild);

        // Remove animation class after it completes
        setTimeout(() => {
            eventElem.classList.remove('new-event-animation');
        }, 1000);
    });

    // Keep only last 50 events in the DOM to avoid performance issues
    while (feed.children.length > 50) {
        feed.removeChild(feed.lastChild);
    }
}

// Create event element
function createEventElement(event) {
    const div = document.createElement('div');
    div.className = 'event-item ' + (event.side || '');

    const time = new Date(event.time).toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });

    // Determine event color based on type
    let eventColor = '#808080';
    if (event.event_type === 'market_buy') eventColor = '#00c2ff';
    else if (event.event_type === 'market_sell') eventColor = '#ff00ff';
    else if (event.event_type === 'increase' && event.side === 'bid') eventColor = '#88cc88';
    else if (event.event_type === 'increase' && event.side === 'ask') eventColor = '#cc8888';
    else if (event.event_type === 'decrease' && event.side === 'bid') eventColor = '#cc8888';
    else if (event.event_type === 'decrease' && event.side === 'ask') eventColor = '#88cc88';
    else if (event.side === 'bid') eventColor = '#00ff88';
    else if (event.side === 'ask') eventColor = '#ff4444';

    const usdValue = event.usd_value || (event.price * event.volume);

    div.innerHTML = `
        <div class="event-header-inline">
            <span class="event-type-badge" style="background-color: ${eventColor};">
                ${formatEventType(event.event_type)}
            </span>
            <span class="event-time-inline">${time}</span>
            <span class="event-usd-badge">${formatUsd(usdValue)}</span>
        </div>
        <div class="event-details-inline">
            <span>Price: $${(event.price || 0).toFixed(6)}</span>
            <span>Vol: ${formatNumber(event.volume || 0)}</span>
            <span>Dist: ${(event.distance_from_mid_pct || 0).toFixed(2)}%</span>
        </div>
    `;

    // Click to show details
    div.addEventListener('click', () => {
        showEventDetailsModal(event);
    });

    return div;
}

// Format event type
function formatEventType(type) {
    const typeMap = {
        'market_buy': 'Market Buy',
        'market_sell': 'Market Sell',
        'increase': 'Increase',
        'decrease': 'Decrease',
        'new_bid': 'New Bid',
        'new_ask': 'New Ask',
        'entered_top': 'Entered Top',
        'left_top': 'Left Top'
    };
    return typeMap[type] || type;
}

// Format USD value
function formatUsd(value) {
    if (value >= 1000000) {
        return '$' + (value / 1000000).toFixed(2) + 'M';
    } else if (value >= 1000) {
        return '$' + (value / 1000).toFixed(1) + 'K';
    } else {
        return '$' + value.toFixed(0);
    }
}

// Format number
function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(2) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    } else {
        return num.toFixed(2);
    }
}

// Load order book
async function loadOrderBook() {
    try {
        const response = await fetch(`/api/live/orderbook?symbol=${currentSymbol}`);
        const data = await response.json();

        if (data.error) {
            console.error('Error loading order book:', data.error);
            return;
        }

        renderOrderBook(data);
        updateSpreadStats(data);

    } catch (error) {
        console.error('Error loading order book:', error);
    }
}

// Render order book
function renderOrderBook(orderbook) {
    const bidsList = document.getElementById('bids-list');
    const asksList = document.getElementById('asks-list');

    if (!orderbook.best_bid || !orderbook.best_ask) {
        bidsList.innerHTML = '<div class="no-data">No bid data</div>';
        asksList.innerHTML = '<div class="no-data">No ask data</div>';
        return;
    }

    // For now, just show best bid/ask (since we only get that from orderbook_price)
    bidsList.innerHTML = `
        <div class="orderbook-row">
            <span class="order-price">${orderbook.best_bid.toFixed(6)}</span>
            <span class="order-label">Best Bid</span>
        </div>
    `;

    asksList.innerHTML = `
        <div class="orderbook-row">
            <span class="order-price">${orderbook.best_ask.toFixed(6)}</span>
            <span class="order-label">Best Ask</span>
        </div>
    `;

    // Update time
    if (orderbook.timestamp) {
        const time = new Date(orderbook.timestamp).toLocaleTimeString();
        document.getElementById('orderbook-time').textContent = time;
    }
}

// Update spread stats
function updateSpreadStats(orderbook) {
    if (!orderbook.best_bid || !orderbook.best_ask) return;

    const spread = orderbook.spread || (orderbook.best_ask - orderbook.best_bid);
    const spreadPct = (spread / orderbook.mid_price) * 100;

    document.getElementById('stat-spread').textContent = spread.toFixed(6);
    document.getElementById('spread-value').innerHTML = `
        ${spread.toFixed(6)}<br/>
        <span style="font-size: 0.8em; color: #808080;">(${spreadPct.toFixed(3)}%)</span>
    `;
}

// Load statistics
async function loadStats() {
    try {
        const response = await fetch(`/api/live/stats?symbol=${currentSymbol}&lookback=1h`);
        const data = await response.json();

        if (data.error) {
            console.error('Error loading stats:', data.error);
            return;
        }

        updateStatsDisplay(data);

    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

// Update stats display
function updateStatsDisplay(stats) {
    document.getElementById('stat-events').textContent = stats.total_events || 0;
    document.getElementById('stat-volume').textContent = formatUsd(stats.total_volume || 0);

    // Event breakdown
    const counts = stats.event_counts || {};
    const breakdown = Object.entries(counts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 3)
        .map(([type, count]) => `${formatEventType(type)}: ${count}`)
        .join(' • ');

    document.getElementById('stat-events-breakdown').textContent = breakdown || 'No events';
}

// Filter events
function filterEvents() {
    const typeFilter = document.getElementById('event-type-filter').value;
    const eventItems = document.querySelectorAll('.event-item');

    eventItems.forEach(item => {
        const typeMatch = !typeFilter || item.querySelector('.event-type-badge').textContent.toLowerCase().includes(typeFilter.replace('_', ' '));
        item.style.display = typeMatch ? 'block' : 'none';
    });
}

// Show event details modal
function showEventDetailsModal(event) {
    const modal = document.getElementById('event-modal');
    const body = document.getElementById('modal-body');

    const time = new Date(event.time).toLocaleString();
    const usdValue = event.usd_value || (event.price * event.volume);

    body.innerHTML = `
        <div class="event-modal-content">
            <div class="modal-stat">
                <div class="modal-stat-label">Event Type</div>
                <div class="modal-stat-value">${formatEventType(event.event_type)}</div>
            </div>
            <div class="modal-stat">
                <div class="modal-stat-label">Side</div>
                <div class="modal-stat-value">${event.side}</div>
            </div>
            <div class="modal-stat">
                <div class="modal-stat-label">Time</div>
                <div class="modal-stat-value">${time}</div>
            </div>
            <div class="modal-stat">
                <div class="modal-stat-label">Price</div>
                <div class="modal-stat-value">$${(event.price || 0).toFixed(6)}</div>
            </div>
            <div class="modal-stat">
                <div class="modal-stat-label">Volume</div>
                <div class="modal-stat-value">${formatNumber(event.volume || 0)}</div>
            </div>
            <div class="modal-stat">
                <div class="modal-stat-label">USD Value</div>
                <div class="modal-stat-value">${formatUsd(usdValue)}</div>
            </div>
            <div class="modal-stat">
                <div class="modal-stat-label">Distance from Mid</div>
                <div class="modal-stat-value">${(event.distance_from_mid_pct || 0).toFixed(3)}%</div>
            </div>
        </div>
    `;

    modal.style.display = 'flex';

    // Close on background click
    modal.onclick = (e) => {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    };
}

// Update status
function updateStatus(status) {
    const statusElem = document.getElementById('stat-status');
    if (status === 'live') {
        statusElem.textContent = '● LIVE';
        statusElem.className = 'stat-value status-live';
    } else if (status === 'loading') {
        statusElem.textContent = '● Loading...';
        statusElem.className = 'stat-value status-loading';
    } else {
        statusElem.textContent = '● Paused';
        statusElem.className = 'stat-value status-paused';
    }
}

// Update last update time
function updateLastUpdateTime() {
    const now = new Date().toLocaleTimeString();
    document.getElementById('stat-last-update').textContent = `Updated: ${now}`;
}

// Prepare whale event scatter series
function prepareWhaleScatterSeries(events) {
    if (!events || events.length === 0) return [];

    // Group events by type for color coding
    const scatterData = events.map(event => {
        const isMarketBuy = event.event_type === 'market_buy';
        const isMarketSell = event.event_type === 'market_sell';
        const isIncrease = event.event_type === 'increase';
        const isDecrease = event.event_type === 'decrease';
        const isBid = event.side === 'bid' || event.event_type.includes('bid');
        const isAsk = event.side === 'ask' || event.event_type.includes('ask');

        let color, symbol, labelPosition;

        // Definitive events - bright colors
        if (isMarketBuy) {
            color = '#00c2ff'; // Bright cyan
            symbol = 'circle';
            labelPosition = 'bottom';
        } else if (isMarketSell) {
            color = '#ff00ff'; // Bright magenta
            symbol = 'circle';
            labelPosition = 'top';
        }
        // Volume changes - muted colors
        else if (isIncrease && isBid) {
            color = '#88cc88'; // Muted green
            symbol = 'diamond';
            labelPosition = 'bottom';
        } else if (isIncrease && isAsk) {
            color = '#cc8888'; // Muted red
            symbol = 'diamond';
            labelPosition = 'top';
        } else if (isDecrease && isBid) {
            color = '#cc8888'; // Muted red
            symbol = 'diamond';
            labelPosition = 'top';
        } else if (isDecrease && isAsk) {
            color = '#88cc88'; // Muted green
            symbol = 'diamond';
            labelPosition = 'bottom';
        }
        // New orders - bright colors
        else if (isBid) {
            color = '#00ff88'; // Bright green
            symbol = 'triangle';
            labelPosition = 'bottom';
        } else if (isAsk) {
            color = '#ff4444'; // Bright red
            symbol = 'triangle';
            labelPosition = 'top';
        } else {
            color = '#ffaa00'; // Orange
            symbol = 'circle';
            labelPosition = 'top';
        }

        const usdValue = event.usd_value || (event.price * event.volume);
        const label = usdValue >= 1000 ? `$${(usdValue / 1000).toFixed(1)}K` : '';

        return {
            time: new Date(event.time),
            price: event.price,
            color: color,
            symbol: symbol,
            size: Math.min(Math.max(usdValue / 1000, 8), 24),
            label: label,
            labelPosition: labelPosition,
            originalEvent: event
        };
    });

    // Create single scatter series
    return [{
        name: 'Whale Events',
        type: 'scatter',
        data: scatterData.map(e => [e.time, e.price, e]),
        symbolSize: function(data) {
            return data[2].size;
        },
        itemStyle: {
            color: function(params) {
                return params.data[2].color;
            }
        },
        symbol: function(data) {
            return data[2].symbol;
        },
        label: {
            show: true,
            formatter: function(params) {
                return params.data[2].label;
            },
            position: function(params) {
                return params.data[2].labelPosition;
            },
            fontSize: 9,
            color: '#e0e0e0'
        },
        z: 5
    }];
}

// Update refresh button
function updateRefreshButton() {
    const btn = document.getElementById('refresh-toggle');
    const icon = document.getElementById('refresh-icon');

    if (isAutoRefresh) {
        icon.textContent = '⏸';
        btn.classList.add('btn-primary');
        btn.classList.remove('btn-secondary');
    } else {
        icon.textContent = '▶';
        btn.classList.add('btn-secondary');
        btn.classList.remove('btn-primary');
    }
}

// Start auto-refresh
function startAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }

    refreshInterval = setInterval(() => {
        if (isAutoRefresh) {
            loadAllData();
        }
    }, 5000); // Refresh every 5 seconds
}

// Stop auto-refresh
function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

// Toggle fullscreen
function toggleFullscreen() {
    const wrapper = document.querySelector('.chart-panel');
    const container = document.getElementById('price-chart');

    if (wrapper.classList.contains('fullscreen')) {
        wrapper.classList.remove('fullscreen');
    } else {
        wrapper.classList.add('fullscreen');
    }

    // Resize chart
    if (chart) {
        setTimeout(() => {
            chart.resize();
        }, 300);
    }
}
