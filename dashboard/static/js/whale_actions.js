/**
 * Whale Actions Analysis Dashboard - Client-side JavaScript
 * Visualizes whale order book events and market actions
 */

// Global state
let chart = null;
let currentData = null;
let currentFilter = 'all';

// Dummy data for demonstration
const DUMMY_DATA = {
    symbol: 'BANANA_USDT',
    timeframe: 'Last 1 hour',
    start_time: new Date(Date.now() - 3600000).toISOString(),
    end_time: new Date().toISOString(),
    events: generateDummyEvents(),
    stats: {
        whale_bids: 18,
        whale_asks: 24,
        avg_size_usd: 57000,
        largest_order_usd: 145000,
        total_volume_usd: 2400000,
        total_events: 42
    }
};

/**
 * Generate dummy whale events for demonstration
 */
function generateDummyEvents() {
    const events = [];
    const now = Date.now();
    const hourAgo = now - 3600000;

    const eventTypes = [
        { type: 'new_bid', side: 'bid', color: '#00ff88' },
        { type: 'new_ask', side: 'ask', color: '#ff4444' },
        { type: 'increase', side: 'bid', color: '#88cc88' },
        { type: 'increase', side: 'ask', color: '#cc8888' },
        { type: 'decrease', side: 'bid', color: '#cc8888' },
        { type: 'decrease', side: 'ask', color: '#88cc88' },
        { type: 'market_buy', side: 'bid', color: '#00c2ff' },
        { type: 'market_sell', side: 'ask', color: '#ff00ff' },
        { type: 'entered_top', side: 'bid', color: '#666' },
        { type: 'entered_top', side: 'ask', color: '#666' },
        { type: 'left_top', side: 'bid', color: '#444' },
        { type: 'left_top', side: 'ask', color: '#444' }
    ];

    // Generate 42 random events
    for (let i = 0; i < 42; i++) {
        const eventConfig = eventTypes[Math.floor(Math.random() * eventTypes.length)];
        const timestamp = hourAgo + (Math.random() * 3600000);
        const price = 50 + (Math.random() * 10); // Price between 50-60
        const usd_volume = 20000 + (Math.random() * 125000); // Between $20k-$145k

        events.push({
            timestamp: new Date(timestamp).toISOString(),
            event_type: eventConfig.type,
            side: eventConfig.side,
            price: price.toFixed(2),
            quantity: (usd_volume / price).toFixed(2),
            usd_volume: usd_volume.toFixed(2),
            distance_from_mid: ((Math.random() - 0.5) * 2).toFixed(3), // -1% to +1%
            color: eventConfig.color,
            period: 'during'
        });
    }

    // Sort by timestamp
    events.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

    return events;
}

/**
 * Initialize the dashboard
 */
function initDashboard() {
    console.log('Initializing Whale Actions Dashboard...');

    // Initialize chart
    initChart();

    // Load dummy data
    loadData();

    // Setup event listeners
    setupEventListeners();

    console.log('Dashboard initialized');
}

/**
 * Initialize the ECharts instance
 */
function initChart() {
    const chartContainer = document.getElementById('main-chart');
    chart = echarts.init(chartContainer);

    // Show loading
    chart.showLoading({
        text: 'Loading whale events...',
        color: '#00c2ff',
        textColor: '#fff',
        maskColor: 'rgba(0, 0, 0, 0.8)'
    });
}

/**
 * Load and display data
 */
function loadData() {
    console.log('Loading dummy data...');
    currentData = DUMMY_DATA;

    // Update info section
    updateInfoSection();

    // Update stats
    updateStats();

    // Update chart
    updateChart();

    // Update events list
    updateEventsList();
}

/**
 * Update analysis info section
 */
function updateInfoSection() {
    document.getElementById('info-symbol').textContent = currentData.symbol;
    document.getElementById('info-timeframe').textContent = currentData.timeframe;
    document.getElementById('info-whale-count').textContent = `${currentData.stats.total_events} whale events`;
    document.getElementById('info-total-volume').textContent = `$${(currentData.stats.total_volume_usd / 1000000).toFixed(1)}M total volume`;
}

/**
 * Update statistics summary
 */
function updateStats() {
    document.getElementById('whale-bids').textContent = currentData.stats.whale_bids;
    document.getElementById('whale-asks').textContent = currentData.stats.whale_asks;
    document.getElementById('avg-size').textContent = `$${(currentData.stats.avg_size_usd / 1000).toFixed(0)}K`;
    document.getElementById('largest-order').textContent = `$${(currentData.stats.largest_order_usd / 1000).toFixed(0)}K`;
}

/**
 * Update the main chart with whale events
 */
function updateChart() {
    if (!currentData || !currentData.events) {
        console.error('No data to display');
        return;
    }

    chart.hideLoading();

    // Prepare data for candlestick (dummy price data)
    const timeData = [];
    const priceData = [];
    const volumeData = [];

    // Generate dummy candlestick data
    const basePrice = 55;
    const startTime = new Date(currentData.start_time).getTime();
    const endTime = new Date(currentData.end_time).getTime();
    const interval = 60000; // 1 minute intervals

    for (let t = startTime; t <= endTime; t += interval) {
        const open = basePrice + (Math.random() - 0.5) * 2;
        const close = open + (Math.random() - 0.5) * 0.5;
        const high = Math.max(open, close) + Math.random() * 0.3;
        const low = Math.min(open, close) - Math.random() * 0.3;

        timeData.push(new Date(t).toISOString());
        priceData.push([open.toFixed(2), close.toFixed(2), low.toFixed(2), high.toFixed(2)]);
        volumeData.push((Math.random() * 100000).toFixed(0));
    }

    // Prepare whale events as scatter points
    const whaleMarkers = currentData.events.map(event => ({
        value: [
            event.timestamp,
            parseFloat(event.price),
            event.usd_volume,
            event.event_type,
            event.side
        ],
        itemStyle: {
            color: event.color,
            borderColor: '#000',
            borderWidth: 1
        },
        symbol: getEventSymbol(event.event_type),
        symbolSize: getEventSize(parseFloat(event.usd_volume))
    }));

    // Chart configuration
    const option = {
        backgroundColor: 'transparent',
        tooltip: {
            trigger: 'axis',
            axisPointer: {
                type: 'cross'
            },
            backgroundColor: 'rgba(0, 0, 0, 0.9)',
            borderColor: '#00c2ff',
            borderWidth: 1,
            textStyle: {
                color: '#fff'
            }
        },
        legend: {
            data: ['Price', 'Volume', 'Whale Events'],
            textStyle: {
                color: '#fff'
            },
            top: 10
        },
        grid: [
            {
                left: '5%',
                right: '5%',
                top: '15%',
                height: '50%'
            },
            {
                left: '5%',
                right: '5%',
                top: '70%',
                height: '15%'
            }
        ],
        xAxis: [
            {
                type: 'category',
                data: timeData,
                axisLabel: {
                    color: '#888',
                    formatter: function(value) {
                        const date = new Date(value);
                        return date.toLocaleTimeString('en-US', {
                            hour: '2-digit',
                            minute: '2-digit'
                        });
                    }
                },
                axisLine: {
                    lineStyle: {
                        color: '#333'
                    }
                }
            },
            {
                type: 'category',
                gridIndex: 1,
                data: timeData,
                axisLabel: {
                    show: false
                },
                axisLine: {
                    lineStyle: {
                        color: '#333'
                    }
                }
            }
        ],
        yAxis: [
            {
                type: 'value',
                name: 'Price (USDT)',
                nameTextStyle: {
                    color: '#888'
                },
                axisLabel: {
                    color: '#888',
                    formatter: '${value}'
                },
                axisLine: {
                    lineStyle: {
                        color: '#333'
                    }
                },
                splitLine: {
                    lineStyle: {
                        color: '#222'
                    }
                }
            },
            {
                type: 'value',
                gridIndex: 1,
                name: 'Volume',
                nameTextStyle: {
                    color: '#888'
                },
                axisLabel: {
                    color: '#888',
                    formatter: function(value) {
                        return (value / 1000).toFixed(0) + 'K';
                    }
                },
                axisLine: {
                    lineStyle: {
                        color: '#333'
                    }
                },
                splitLine: {
                    show: false
                }
            }
        ],
        series: [
            {
                name: 'Price',
                type: 'candlestick',
                data: priceData,
                itemStyle: {
                    color: '#00ff88',
                    color0: '#ff4444',
                    borderColor: '#00ff88',
                    borderColor0: '#ff4444'
                }
            },
            {
                name: 'Whale Events',
                type: 'scatter',
                data: whaleMarkers,
                symbolSize: function(data) {
                    return getEventSize(data[2]);
                },
                emphasis: {
                    scale: 1.5
                }
            },
            {
                name: 'Volume',
                type: 'bar',
                xAxisIndex: 1,
                yAxisIndex: 1,
                data: volumeData,
                itemStyle: {
                    color: 'rgba(0, 194, 255, 0.3)'
                }
            }
        ]
    };

    chart.setOption(option);

    // Add click handler for whale events
    chart.on('click', function(params) {
        if (params.seriesName === 'Whale Events') {
            const eventIndex = params.dataIndex;
            showEventDetails(currentData.events[eventIndex]);
        }
    });
}

/**
 * Get symbol for event type
 */
function getEventSymbol(eventType) {
    if (eventType.includes('market')) return 'circle';
    if (eventType.includes('increase')) return 'diamond';
    if (eventType.includes('decrease')) return 'triangle';
    if (eventType.includes('new')) return 'circle';
    return 'rect';
}

/**
 * Get marker size based on USD volume
 */
function getEventSize(usdVolume) {
    // Scale size based on volume: $20K = size 8, $145K = size 20
    const minSize = 8;
    const maxSize = 20;
    const minVolume = 20000;
    const maxVolume = 145000;

    const ratio = (usdVolume - minVolume) / (maxVolume - minVolume);
    return minSize + (ratio * (maxSize - minSize));
}

/**
 * Update events list in right panel
 */
function updateEventsList() {
    const listContainer = document.getElementById('events-list');
    listContainer.innerHTML = '';

    // Filter events based on current filter
    const filteredEvents = filterEvents(currentData.events, currentFilter);

    if (filteredEvents.length === 0) {
        listContainer.innerHTML = '<div class="no-events">No events match the current filter</div>';
        return;
    }

    // Create event cards
    filteredEvents.forEach(event => {
        const eventCard = createEventCard(event);
        listContainer.appendChild(eventCard);
    });
}

/**
 * Filter events based on selected filter
 */
function filterEvents(events, filter) {
    if (filter === 'all') return events;
    if (filter === 'bids') return events.filter(e => e.side === 'bid');
    if (filter === 'asks') return events.filter(e => e.side === 'ask');
    if (filter === 'market') return events.filter(e => e.event_type.includes('market'));
    return events;
}

/**
 * Create event card element
 */
function createEventCard(event) {
    const card = document.createElement('div');
    card.className = 'event-card';
    card.style.borderLeftColor = event.color;

    const time = new Date(event.timestamp).toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });

    const eventTypeLabel = formatEventType(event.event_type);
    const sideLabel = event.side.toUpperCase();
    const sideClass = event.side === 'bid' ? 'badge-bullish' : 'badge-bearish';

    card.innerHTML = `
        <div class="event-card-header">
            <span class="event-time">${time}</span>
            <span class="event-badge ${sideClass}">${sideLabel}</span>
        </div>
        <div class="event-card-body">
            <div class="event-type">${eventTypeLabel}</div>
            <div class="event-details">
                <div class="event-detail-item">
                    <span class="detail-label">Price:</span>
                    <span class="detail-value">$${parseFloat(event.price).toFixed(2)}</span>
                </div>
                <div class="event-detail-item">
                    <span class="detail-label">Volume:</span>
                    <span class="detail-value">$${(parseFloat(event.usd_volume) / 1000).toFixed(1)}K</span>
                </div>
                <div class="event-detail-item">
                    <span class="detail-label">Distance:</span>
                    <span class="detail-value">${(parseFloat(event.distance_from_mid) * 100).toFixed(2)}%</span>
                </div>
            </div>
        </div>
    `;

    // Add click handler
    card.addEventListener('click', () => showEventDetails(event));

    return card;
}

/**
 * Format event type for display
 */
function formatEventType(eventType) {
    return eventType
        .split('_')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
}

/**
 * Show event details modal
 */
function showEventDetails(event) {
    const modal = document.getElementById('event-details-modal');
    const modalTitle = document.getElementById('modal-title');
    const modalBody = document.getElementById('modal-body');

    modalTitle.textContent = formatEventType(event.event_type);

    const time = new Date(event.timestamp).toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        fractionalSecondDigits: 3
    });

    modalBody.innerHTML = `
        <div class="event-detail-grid">
            <div class="detail-row">
                <span class="detail-label">Timestamp:</span>
                <span class="detail-value">${time}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Event Type:</span>
                <span class="detail-value" style="color: ${event.color}">${formatEventType(event.event_type)}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Side:</span>
                <span class="detail-value">${event.side.toUpperCase()}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Price:</span>
                <span class="detail-value">$${parseFloat(event.price).toFixed(2)}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Quantity:</span>
                <span class="detail-value">${parseFloat(event.quantity).toFixed(2)}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">USD Volume:</span>
                <span class="detail-value">$${parseFloat(event.usd_volume).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Distance from Mid:</span>
                <span class="detail-value">${(parseFloat(event.distance_from_mid) * 100).toFixed(3)}%</span>
            </div>
        </div>
    `;

    modal.style.display = 'flex';
}

/**
 * Setup event listeners
 */
function setupEventListeners() {
    // Refresh button
    document.getElementById('refresh-btn').addEventListener('click', () => {
        loadData();
    });

    // Export button
    document.getElementById('export-data-btn').addEventListener('click', exportData);

    // Filter buttons
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            // Update active state
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            // Update filter
            currentFilter = this.dataset.filter;
            updateEventsList();
        });
    });

    // Fullscreen toggle
    document.getElementById('fullscreen-btn').addEventListener('click', toggleFullscreen);

    // ESC key handler
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            const modal = document.getElementById('event-details-modal');
            const isModalOpen = modal && modal.style.display === 'flex';

            if (isModalOpen) {
                modal.style.display = 'none';
            } else {
                const wrapper = document.querySelector('.chart-wrapper');
                if (wrapper && wrapper.classList.contains('fullscreen')) {
                    toggleFullscreen();
                }
            }
        }
    });

    // Window resize handler
    window.addEventListener('resize', () => {
        if (chart) {
            chart.resize();
        }
    });
}

/**
 * Toggle fullscreen mode
 */
function toggleFullscreen() {
    const wrapper = document.querySelector('.chart-wrapper');
    wrapper.classList.toggle('fullscreen');

    if (chart) {
        setTimeout(() => chart.resize(), 100);
    }
}

/**
 * Export current data as JSON
 */
function exportData() {
    if (!currentData) {
        alert('No data to export');
        return;
    }

    const filename = `whale_actions_${currentData.symbol}_${new Date().toISOString().replace(/[:.]/g, '-')}.json`;

    const jsonData = JSON.stringify(currentData, null, 2);
    const blob = new Blob([jsonData], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initDashboard);
