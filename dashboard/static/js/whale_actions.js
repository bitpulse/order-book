/**
 * Whale Actions Analysis Dashboard - Client-side JavaScript
 * Visualizes whale order book events and market actions
 */

// Global state
let chart = null;
let currentData = null;
let currentInterval = null;
let currentFilter = 'all';

/**
 * Initialize the dashboard
 */
function initDashboard() {
    console.log('Initializing Whale Actions Dashboard...');

    // Load file list
    loadFileList();

    // Setup event listeners
    setupEventListeners();

    console.log('Dashboard initialized');
}

/**
 * Load available whale activity files
 */
async function loadFileList() {
    try {
        const response = await fetch('/api/whale-files');
        const data = await response.json();

        const selector = document.getElementById('file-selector');

        if (!selector) {
            console.error('File selector element not found');
            return;
        }

        selector.innerHTML = '<option value="">Select a file...</option>';

        if (data.files && data.files.length > 0) {
            data.files.forEach(file => {
                const option = document.createElement('option');
                option.value = file.filename;
                const date = new Date(file.modified * 1000);
                option.textContent = `${file.filename} (${date.toLocaleString()})`;
                selector.appendChild(option);
            });

            // Auto-select first file
            if (data.files.length > 0) {
                selector.value = data.files[0].filename;
                await loadDataFile(data.files[0].filename);
            }
        } else {
            selector.innerHTML = '<option value="">No files found - Run analysis first</option>';
        }
    } catch (error) {
        console.error('Error loading file list:', error);
    }
}

/**
 * Load whale activity data from selected file
 */
async function loadDataFile(filename) {
    if (!filename) return;

    try {
        const response = await fetch(`/api/whale-data/${filename}`);
        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        // Handle new JSON format with metadata
        const intervals = data.intervals || [];
        const metadata = data.metadata || {};

        currentData = {
            metadata,
            intervals
        };

        // Update info section
        updateInfoSection();

        // Update chart and events list
        if (intervals.length > 0) {
            // Show interval selector if multiple intervals
            if (intervals.length > 1) {
                showIntervalSelector(intervals);
            }

            // Load first interval
            loadInterval(intervals[0]);
        }

    } catch (error) {
        console.error('Error loading data file:', error);
        alert('Failed to load data: ' + error.message);
    }
}

/**
 * Show interval selector dropdown
 */
function showIntervalSelector(intervals) {
    const container = document.getElementById('interval-selector-container');
    const selector = document.getElementById('interval-selector');

    if (!container || !selector) {
        console.error('Interval selector elements not found');
        return;
    }

    selector.innerHTML = '';
    intervals.forEach((interval, index) => {
        const option = document.createElement('option');
        option.value = index;
        const startTime = new Date(interval.start_time).toLocaleTimeString();
        const imbalance = (interval.order_flow_imbalance * 100).toFixed(0);
        option.textContent = `#${interval.rank} - $${(interval.total_usd_volume / 1000).toFixed(0)}K (${imbalance > 0 ? '+' : ''}${imbalance}%) @ ${startTime}`;
        selector.appendChild(option);
    });

    container.style.display = 'block';
}

/**
 * Load specific interval
 */
function loadInterval(intervalData) {
    currentInterval = intervalData;

    // Update stats
    updateStats(intervalData);

    // Initialize chart if needed
    if (!chart) {
        initChart();
    }

    // Update chart
    updateChart(intervalData);

    // Update events list
    updateEventsList(intervalData);
}

/**
 * Update analysis info section
 */
function updateInfoSection() {
    if (!currentData || !currentData.metadata) return;

    const metadata = currentData.metadata;

    document.getElementById('info-symbol').textContent = metadata.symbol || 'UNKNOWN';
    document.getElementById('info-timeframe').textContent = `Last ${metadata.lookback || '?'}`;

    const totalEvents = currentData.intervals.reduce((sum, i) => sum + i.event_count, 0);
    document.getElementById('info-whale-count').textContent = `${totalEvents} whale events`;

    const totalVolume = currentData.intervals.reduce((sum, i) => sum + i.total_usd_volume, 0);
    document.getElementById('info-total-volume').textContent = `$${(totalVolume / 1000000).toFixed(1)}M total volume`;
}

/**
 * Update statistics summary
 */
function updateStats(intervalData) {
    if (!intervalData) return;

    // Count whale bids and asks from event summary
    let whaleBids = 0;
    let whaleAsks = 0;

    Object.entries(intervalData.event_summary || {}).forEach(([eventType, stats]) => {
        if (eventType.includes('bid') || eventType === 'market_buy') {
            whaleBids += stats.count;
        } else if (eventType.includes('ask') || eventType === 'market_sell') {
            whaleAsks += stats.count;
        }
    });

    document.getElementById('whale-bids').textContent = whaleBids;
    document.getElementById('whale-asks').textContent = whaleAsks;

    const avgSize = intervalData.total_usd_volume / intervalData.event_count;
    document.getElementById('avg-size').textContent = `$${(avgSize / 1000).toFixed(0)}K`;

    // Find largest order
    const largestOrder = Math.max(...intervalData.whale_events.map(e => e.usd_value));
    document.getElementById('largest-order').textContent = `$${(largestOrder / 1000).toFixed(0)}K`;
}

/**
 * Initialize the ECharts instance
 */
function initChart() {
    const chartContainer = document.getElementById('main-chart');
    if (!chartContainer) {
        console.error('Chart container not found');
        return;
    }

    chart = echarts.init(chartContainer);
}

/**
 * Update the main chart with whale events
 */
function updateChart(intervalData) {
    if (!chart || !intervalData) return;

    // Prepare price data as continuous line (like price analyzer)
    const priceData = intervalData.price_data || [];
    const chartData = priceData.map(p => ({
        time: new Date(p.time),
        value: p.mid_price
    }));

    // Prepare whale events scatter data with proper symbols
    const whaleScatterData = intervalData.whale_events.map(event => {
        const isMarketBuy = event.event_type === 'market_buy';
        const isMarketSell = event.event_type === 'market_sell';
        const isIncrease = event.event_type === 'increase';
        const isDecrease = event.event_type === 'decrease';
        const isBid = event.side === 'bid' || event.event_type.includes('bid');
        const isAsk = event.side === 'ask' || event.event_type.includes('ask');

        let color, symbol;

        // Definitive events - bright colors
        if (isMarketBuy) {
            color = '#00c2ff';
            symbol = 'circle';
        } else if (isMarketSell) {
            color = '#ff00ff';
            symbol = 'circle';
        }
        // Volume changes - muted colors
        else if (isIncrease && isBid) {
            color = '#88cc88';
            symbol = 'diamond';
        } else if (isIncrease && isAsk) {
            color = '#cc8888';
            symbol = 'diamond';
        } else if (isDecrease && isBid) {
            color = '#cc8888';
            symbol = 'triangle';
        } else if (isDecrease && isAsk) {
            color = '#88cc88';
            symbol = 'triangle';
        }
        // New orders - bright colors
        else if (isBid) {
            color = '#00ff88';
            symbol = 'triangle';
        } else if (isAsk) {
            color = '#ff4444';
            symbol = 'triangle';
        } else {
            color = '#666';
            symbol = 'rect';
        }

        return {
            time: new Date(event.time),
            price: event.price,
            size: getEventSize(event.usd_value),
            color: color,
            symbol: symbol,
            event: event
        };
    });

    // Chart configuration (matching price analyzer style)
    const option = {
        backgroundColor: 'transparent',
        tooltip: {
            trigger: 'axis',
            axisPointer: {
                type: 'cross',
                lineStyle: {
                    color: 'rgba(0, 194, 255, 0.3)',
                    type: 'dashed'
                }
            },
            backgroundColor: 'rgba(0, 0, 0, 0.9)',
            borderColor: '#00c2ff',
            borderWidth: 1,
            textStyle: {
                color: '#fff'
            }
        },
        grid: {
            left: '3%',
            right: '3%',
            top: '10%',
            bottom: '10%',
            containLabel: true
        },
        xAxis: {
            type: 'time',
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
            },
            splitLine: {
                show: false
            }
        },
        yAxis: {
            type: 'value',
            name: 'Price (USDT)',
            scale: true,
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
                    color: '#222',
                    type: 'dashed'
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
                    width: 2.5,
                    shadowBlur: 4,
                    shadowColor: 'rgba(0, 194, 255, 0.3)'
                },
                itemStyle: {
                    color: '#00c2ff',
                    borderWidth: 0
                },
                symbol: 'none',
                smooth: 0.3,
                z: 2,
                areaStyle: {
                    color: {
                        type: 'linear',
                        x: 0,
                        y: 0,
                        x2: 0,
                        y2: 1,
                        colorStops: [
                            { offset: 0, color: 'rgba(0, 194, 255, 0.15)' },
                            { offset: 1, color: 'rgba(0, 194, 255, 0.01)' }
                        ]
                    }
                },
                sampling: 'lttb'
            },
            {
                name: 'Whale Events',
                type: 'scatter',
                data: whaleScatterData.map(e => [e.time, e.price, e]),
                symbolSize: function(data) {
                    return data[2].size;
                },
                itemStyle: {
                    color: function(params) {
                        return params.data[2].color;
                    },
                    borderColor: '#000',
                    borderWidth: 1
                },
                symbol: function(data) {
                    return data[2].symbol;
                },
                z: 5,
                emphasis: {
                    scale: 1.5
                }
            }
        ]
    };

    chart.setOption(option);

    // Add click handler for whale events
    chart.off('click'); // Remove previous handlers
    chart.on('click', function(params) {
        if (params.seriesName === 'Whale Events') {
            showEventDetails(intervalData.whale_events[params.dataIndex]);
        }
    });
}

/**
 * Get color for event type
 */
function getEventColor(eventType, side) {
    if (eventType === 'market_buy') return '#00c2ff';
    if (eventType === 'market_sell') return '#ff00ff';
    if (eventType === 'increase') return side === 'bid' ? '#88cc88' : '#cc8888';
    if (eventType === 'decrease') return side === 'bid' ? '#cc8888' : '#88cc88';
    if (eventType.includes('bid') || eventType.includes('buy')) return '#00ff88';
    if (eventType.includes('ask') || eventType.includes('sell')) return '#ff4444';
    return '#666';
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
    const minSize = 8;
    const maxSize = 20;
    const minVolume = 10000;
    const maxVolume = 100000;

    const ratio = Math.min(1, Math.max(0, (usdVolume - minVolume) / (maxVolume - minVolume)));
    return minSize + (ratio * (maxSize - minSize));
}

/**
 * Update events list in right panel
 */
function updateEventsList(intervalData) {
    if (!intervalData) return;

    const listContainer = document.getElementById('events-list');
    if (!listContainer) return;

    listContainer.innerHTML = '';

    // Filter events based on current filter
    const filteredEvents = filterEvents(intervalData.whale_events, currentFilter);

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
    if (filter === 'bids') return events.filter(e => e.side === 'bid' || e.event_type === 'market_buy');
    if (filter === 'asks') return events.filter(e => e.side === 'ask' || e.event_type === 'market_sell');
    if (filter === 'market') return events.filter(e => e.event_type.includes('market'));
    return events;
}

/**
 * Create event card element
 */
function createEventCard(event) {
    const card = document.createElement('div');
    card.className = 'event-card';
    card.style.borderLeftColor = getEventColor(event.event_type, event.side);

    const time = new Date(event.time).toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });

    const eventTypeLabel = formatEventType(event.event_type);
    const sideLabel = event.side.toUpperCase();
    const sideClass = (event.side === 'bid' || event.event_type === 'market_buy') ? 'badge-bullish' : 'badge-bearish';

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
                    <span class="detail-value">$${(parseFloat(event.usd_value) / 1000).toFixed(1)}K</span>
                </div>
                <div class="event-detail-item">
                    <span class="detail-label">Distance:</span>
                    <span class="detail-value">${(parseFloat(event.distance_from_mid_pct || 0)).toFixed(2)}%</span>
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

    const time = new Date(event.time).toLocaleString('en-US', {
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
                <span class="detail-value" style="color: ${getEventColor(event.event_type, event.side)}">${formatEventType(event.event_type)}</span>
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
                <span class="detail-value">${parseFloat(event.volume).toFixed(2)}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">USD Volume:</span>
                <span class="detail-value">$${parseFloat(event.usd_value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Distance from Mid:</span>
                <span class="detail-value">${(parseFloat(event.distance_from_mid_pct || 0)).toFixed(3)}%</span>
            </div>
        </div>
    `;

    modal.style.display = 'flex';
}

/**
 * Setup event listeners
 */
function setupEventListeners() {
    // File selector
    const fileSelector = document.getElementById('file-selector');
    if (fileSelector) {
        fileSelector.addEventListener('change', (e) => {
            loadDataFile(e.target.value);
        });
    }

    // Interval selector
    const intervalSelector = document.getElementById('interval-selector');
    if (intervalSelector) {
        intervalSelector.addEventListener('change', (e) => {
            const index = parseInt(e.target.value);
            if (currentData && currentData.intervals[index]) {
                loadInterval(currentData.intervals[index]);
            }
        });
    }

    // Refresh button
    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            loadFileList();
        });
    }

    // New analysis button
    const newAnalysisBtn = document.getElementById('new-analysis-btn');
    if (newAnalysisBtn) {
        newAnalysisBtn.addEventListener('click', () => {
            document.getElementById('new-analysis-modal').style.display = 'flex';
        });
    }

    // Analysis form
    const analysisForm = document.getElementById('analysis-form');
    if (analysisForm) {
        analysisForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            await runNewAnalysis();
        });
    }

    // Export button
    const exportBtn = document.getElementById('export-data-btn');
    if (exportBtn) {
        exportBtn.addEventListener('click', exportData);
    }

    // Filter buttons
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            // Update active state
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            // Update filter
            currentFilter = this.dataset.filter;
            if (currentInterval) {
                updateEventsList(currentInterval);
            }
        });
    });

    // Fullscreen toggle
    const fullscreenBtn = document.getElementById('fullscreen-btn');
    if (fullscreenBtn) {
        fullscreenBtn.addEventListener('click', toggleFullscreen);
    }

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
 * Run new whale analysis
 */
async function runNewAnalysis() {
    const symbol = document.getElementById('symbol-input').value;
    const lookback = document.getElementById('lookback-input').value;
    const interval = document.getElementById('interval-input').value;
    const top = parseInt(document.getElementById('top-input').value);
    const minUsd = parseFloat(document.getElementById('min-usd-input').value);
    const sortBy = document.getElementById('sort-by-input').value;

    // Show status
    const statusDiv = document.getElementById('analysis-status');
    const statusMsg = document.getElementById('status-message');
    document.getElementById('analysis-form').style.display = 'none';
    statusDiv.style.display = 'flex';
    statusMsg.textContent = 'Running whale analysis...';

    try {
        const response = await fetch('/api/run-whale-analysis', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                symbol,
                lookback,
                interval,
                top,
                min_usd: minUsd,
                sort_by: sortBy
            })
        });

        const result = await response.json();

        if (result.error) {
            throw new Error(result.error);
        }

        statusMsg.textContent = 'Analysis complete! Loading data...';

        // Reload file list and select new file
        await loadFileList();

        // Close modal
        document.getElementById('new-analysis-modal').style.display = 'none';
        document.getElementById('analysis-form').style.display = 'block';
        statusDiv.style.display = 'none';

    } catch (error) {
        statusMsg.textContent = 'Error: ' + error.message;
        document.getElementById('analysis-form').style.display = 'block';
    }
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
    if (!currentInterval) {
        alert('No interval data loaded');
        return;
    }

    const symbol = currentInterval.symbol || currentData.metadata.symbol || 'UNKNOWN';
    const startTime = new Date(currentInterval.start_time);
    const filename = `whale_interval_${symbol}_rank${currentInterval.rank}_${startTime.toISOString().replace(/[:.]/g, '-')}.json`;

    const jsonData = JSON.stringify(currentInterval, null, 2);
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
