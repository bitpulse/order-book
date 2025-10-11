// Whale Activity Dashboard - Chart and Events Handler (Apache ECharts)

let chart = null;
let currentData = null;
let currentInterval = null;
let minUsdFilter = 0; // Global filter for minimum USD value

// Initialize dashboard on load
document.addEventListener('DOMContentLoaded', async () => {
    await loadFileList();
    setupEventListeners();
    showLoading(false);
});

// Load available whale activity data files
async function loadFileList() {
    try {
        const response = await fetch('/api/whale-files');
        const data = await response.json();

        const selector = document.getElementById('file-selector');
        selector.innerHTML = '<option value="">Select a file...</option>';

        if (data.files && data.files.length > 0) {
            data.files.forEach(file => {
                const option = document.createElement('option');
                option.value = file.id;  // Use MongoDB ID
                const date = file.created_at ? new Date(file.created_at) : new Date();
                const symbol = file.symbol || 'Unknown';
                option.textContent = `${symbol} - ${date.toLocaleString()} (${file.id.substring(0, 8)}...)`;
                selector.appendChild(option);
            });
        } else {
            selector.innerHTML = '<option value="">No files found</option>';
        }
    } catch (error) {
        console.error('Error loading file list:', error);
        showError('Failed to load file list: ' + error.message);
    }
}

// Load data from selected analysis
async function loadDataFile(analysisId) {
    if (!analysisId) return;

    showLoading(true);

    try {
        const response = await fetch(`/api/whale-data/${analysisId}`);
        let data = await response.json();

        console.log('Loaded whale activity data:', data);

        if (data.error) {
            throw new Error(data.error);
        }

        // Handle JSON format with metadata
        let intervals = data.intervals || [];
        let orders = data.orders || [];
        let metadata = data.metadata;

        console.log('Intervals:', intervals);
        console.log('Orders:', orders);
        console.log('Metadata:', metadata);

        // Detect which format: intervals (old) or orders (new)
        const isOrderFormat = metadata && metadata.analyzer === 'top_market_orders';

        if (isOrderFormat) {
            // New format: individual orders
            // Convert to pseudo-interval format for compatibility
            const pseudoInterval = {
                rank: 1,
                symbol: metadata.symbol,
                start_time: data.start_time,
                end_time: data.end_time,
                whale_events: orders,
                whale_events_before: [],
                whale_events_after: [],
                price_data: data.price_data || [],
                total_usd_volume: metadata.total_buy_volume + metadata.total_sell_volume,
                buy_volume: metadata.total_buy_volume,
                sell_volume: metadata.total_sell_volume,
                event_count: orders.length,
                order_flow_imbalance: metadata.buy_count && metadata.sell_count ?
                    (metadata.total_buy_volume - metadata.total_sell_volume) / (metadata.total_buy_volume + metadata.total_sell_volume) : 0,
                extended_start: data.start_time,
                extended_end: data.end_time
            };

            currentData = [pseudoInterval];
            updateAnalysisInfo(filename, [pseudoInterval], metadata);
            document.getElementById('interval-selector-container').style.display = 'none';
            loadInterval(pseudoInterval);
        } else {
            // Old format: intervals
            currentData = intervals;
            updateAnalysisInfo(filename, intervals, metadata);

            if (intervals.length > 1) {
                showIntervalSelector(intervals);
            } else {
                document.getElementById('interval-selector-container').style.display = 'none';
            }

            if (intervals.length > 0) {
                loadInterval(intervals[0]);
            }
        }

        showLoading(false);
    } catch (error) {
        console.error('Error loading data file:', error);
        showError('Failed to load data: ' + error.message);
        showLoading(false);
    }
}

// Update analysis metadata display
function updateAnalysisInfo(filename, intervals, metadata) {
    const infoElement = document.getElementById('analysis-info');

    if (metadata && metadata.symbol) {
        document.getElementById('info-symbol').textContent = metadata.symbol;
        document.getElementById('info-interval').textContent = metadata.interval || '-';
        document.getElementById('info-lookback').textContent = metadata.lookback || '-';
        document.getElementById('info-threshold').textContent = `Min $${(metadata.min_usd || 0).toLocaleString()}`;
        infoElement.style.display = 'grid';
    } else {
        infoElement.style.display = 'none';
    }
}

// Show interval selector with dropdown
function showIntervalSelector(intervals) {
    const container = document.getElementById('interval-selector-container');
    const selector = document.getElementById('interval-selector');

    selector.innerHTML = '';
    intervals.forEach((interval, index) => {
        const option = document.createElement('option');
        option.value = index;
        const startTime = new Date(interval.start_time).toLocaleTimeString();
        const imbalance = interval.order_flow_imbalance || 0;
        const imbalanceStr = (imbalance * 100).toFixed(0);
        option.textContent = `#${interval.rank} - $${(interval.total_usd_volume || 0).toLocaleString()} (${imbalanceStr > 0 ? '+' : ''}${imbalanceStr}%) @ ${startTime}`;
        selector.appendChild(option);
    });

    container.style.display = 'block';
}

// Load specific interval data
function loadInterval(intervalData) {
    currentInterval = intervalData;

    // Hide zero state and show chart
    showZeroState(false);

    // Update stats
    updateStats(intervalData);

    // Update order flow imbalance bar
    updateImbalanceBar(intervalData);

    // Initialize or update chart
    if (!chart) {
        initializeChart();
    }

    // Load price data
    loadPriceData(intervalData);

    // Load whale events
    loadWhaleEvents(intervalData);
}

// Update statistics display
function updateStats(data) {
    document.getElementById('stat-rank').textContent = `#${data.rank}`;

    const volumeElem = document.getElementById('stat-volume');
    volumeElem.textContent = `$${(data.total_usd_volume || 0).toLocaleString()}`;

    const imbalance = data.order_flow_imbalance || 0;
    const flowElem = document.getElementById('stat-flow');
    flowElem.textContent = `${(imbalance * 100).toFixed(0)}%`;
    flowElem.className = 'stat-value ' + (imbalance > 0.1 ? 'positive' : imbalance < -0.1 ? 'negative' : 'neutral');

    const startTime = new Date(data.start_time).toLocaleTimeString();
    const endTime = new Date(data.end_time).toLocaleTimeString();
    document.getElementById('stat-time').textContent = `${startTime} → ${endTime}`;

    // Apply USD filter to event counts
    const filteredDuring = filterWhaleEventsByUsd(data.whale_events || []);
    const filteredBefore = filterWhaleEventsByUsd(data.whale_events_before || []);
    const filteredAfter = filterWhaleEventsByUsd(data.whale_events_after || []);
    const totalEvents = filteredDuring.length + filteredBefore.length + filteredAfter.length;
    document.getElementById('stat-events').textContent = totalEvents;
}

// Update order flow imbalance bar
function updateImbalanceBar(data) {
    const container = document.getElementById('imbalance-bar-container');
    const fillElem = document.getElementById('imbalance-fill');
    const valueElem = document.getElementById('imbalance-value');
    const buyVolumeElem = document.getElementById('buy-volume-value');
    const sellVolumeElem = document.getElementById('sell-volume-value');

    const imbalance = data.order_flow_imbalance || 0;
    const buyVolume = data.buy_volume || 0;
    const sellVolume = data.sell_volume || 0;

    // Update value text
    valueElem.textContent = `${(imbalance * 100).toFixed(1)}%`;

    // Update fill width and color (0% = far left, 100% = far right, 50% = center)
    const fillPercent = ((imbalance + 1) / 2) * 100; // Convert -1..1 to 0..100
    fillElem.style.width = `${fillPercent}%`;

    // Color based on imbalance
    if (imbalance > 0.1) {
        fillElem.style.background = 'linear-gradient(90deg, #808080 0%, #00ffa3 100%)';
        valueElem.className = 'imbalance-value positive';
    } else if (imbalance < -0.1) {
        fillElem.style.background = 'linear-gradient(90deg, #ff3b69 0%, #808080 100%)';
        valueElem.className = 'imbalance-value negative';
    } else {
        fillElem.style.background = '#808080';
        valueElem.className = 'imbalance-value neutral';
    }

    // Update volume breakdown
    buyVolumeElem.textContent = `$${buyVolume.toLocaleString()}`;
    sellVolumeElem.textContent = `$${sellVolume.toLocaleString()}`;

    container.style.display = 'block';
}

// Initialize ECharts chart
function initializeChart() {
    const container = document.getElementById('chart-container');

    // Clear loading spinner
    const loading = document.getElementById('loading');
    if (loading) {
        loading.style.display = 'none';
    }

    // Initialize ECharts instance
    chart = echarts.init(container, 'dark');

    // Handle window resize
    window.addEventListener('resize', () => {
        chart.resize();
    });
}

// Load price data into chart
function loadPriceData(data) {
    if (!chart) return;

    console.log('Loading price data:', data);

    if (!data.price_data || !Array.isArray(data.price_data)) {
        console.error('Invalid price_data:', data.price_data);
        return;
    }

    // Convert price data to ECharts format
    const chartData = data.price_data.map(point => ({
        time: new Date(point.time),
        value: point.mid_price
    }));

    // Find spike point (max price change from start)
    const startPrice = data.price_data.find(p => new Date(p.time) >= new Date(data.start_time))?.mid_price || data.price_data[0]?.mid_price;
    let spikePoint = chartData[0];
    let maxChange = 0;

    for (const point of chartData) {
        const change = Math.abs((point.value - startPrice) / startPrice);
        if (change > maxChange) {
            maxChange = change;
            spikePoint = point;
        }
    }

    // Create series
    const series = [];

    // Main price line
    series.push({
        name: 'Price',
        type: 'line',
        data: chartData.map(d => [d.time, d.value]),
        lineStyle: {
            color: '#00c2ff',
            width: 2.5,
            shadowBlur: 4,
            shadowColor: 'rgba(0, 194, 255, 0.3)'
        },
        areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: 'rgba(0, 194, 255, 0.15)' },
                { offset: 1, color: 'rgba(0, 194, 255, 0.01)' }
            ])
        },
        symbol: 'none',
        smooth: 0.3,
        sampling: 'lttb',
        z: 1
    });

    // START marker
    series.push({
        name: 'START',
        type: 'scatter',
        data: [[new Date(data.start_time), startPrice]],
        symbolSize: 16,
        itemStyle: {
            color: '#ffd60a',
            shadowBlur: 10,
            shadowColor: 'rgba(255, 214, 10, 0.5)',
            borderColor: '#333',
            borderWidth: 2
        },
        label: {
            show: true,
            formatter: '▼ START',
            position: 'top',
            color: '#ffd60a',
            fontSize: 11,
            fontWeight: 'bold',
            distance: 8
        },
        z: 10
    });

    // END marker
    const endPrice = data.price_data.find(p => new Date(p.time) >= new Date(data.end_time))?.mid_price || data.price_data[data.price_data.length - 1]?.mid_price;
    series.push({
        name: 'END',
        type: 'scatter',
        data: [[new Date(data.end_time), endPrice]],
        symbolSize: 16,
        itemStyle: {
            color: '#ffd60a',
            shadowBlur: 10,
            shadowColor: 'rgba(255, 214, 10, 0.5)',
            borderColor: '#333',
            borderWidth: 2
        },
        label: {
            show: true,
            formatter: '▲ END',
            position: 'top',
            color: '#ffd60a',
            fontSize: 11,
            fontWeight: 'bold',
            distance: 8
        },
        z: 10
    });

    // SPIKE marker
    series.push({
        name: 'SPIKE',
        type: 'scatter',
        data: [[spikePoint.time, spikePoint.value]],
        symbolSize: 22,
        itemStyle: {
            color: spikePoint.value > startPrice ? '#00ffa3' : '#ff3b69',
            shadowBlur: 12,
            shadowColor: spikePoint.value > startPrice ? 'rgba(0, 255, 163, 0.6)' : 'rgba(255, 59, 105, 0.6)',
            borderColor: '#000',
            borderWidth: 2
        },
        label: {
            show: true,
            formatter: '★',
            position: 'inside',
            color: '#000',
            fontSize: 18,
            fontWeight: 'bold'
        },
        z: 10
    });

    // Configure chart options
    const option = {
        animation: false,
        backgroundColor: 'transparent',
        tooltip: {
            trigger: 'axis',
            axisPointer: {
                type: 'cross',
                crossStyle: {
                    color: 'rgba(0, 255, 163, 0.3)',
                    width: 1
                }
            },
            formatter: function(params) {
                return formatTooltip(params, data);
            },
            backgroundColor: 'rgba(0, 0, 0, 0.9)',
            borderColor: '#00c2ff',
            borderWidth: 1,
            textStyle: {
                color: '#fff'
            }
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
                show: true,
                backgroundColor: 'rgba(17, 17, 17, 0.8)',
                fillerColor: 'rgba(0, 194, 255, 0.15)',
                borderColor: 'rgba(0, 194, 255, 0.3)',
                handleStyle: {
                    color: '#00c2ff',
                    shadowBlur: 8,
                    shadowColor: 'rgba(0, 194, 255, 0.5)'
                },
                dataBackground: {
                    lineStyle: {
                        color: '#00c2ff',
                        opacity: 0.5
                    },
                    areaStyle: {
                        color: 'rgba(0, 194, 255, 0.1)'
                    }
                },
                selectedDataBackground: {
                    lineStyle: {
                        color: '#00c2ff'
                    },
                    areaStyle: {
                        color: 'rgba(0, 194, 255, 0.2)'
                    }
                }
            }
        ],
        xAxis: {
            type: 'time',
            splitLine: {
                show: true,
                lineStyle: {
                    color: 'rgba(255, 255, 255, 0.1)',
                    type: 'dashed'
                }
            },
            axisLine: {
                lineStyle: {
                    color: 'rgba(255, 255, 255, 0.3)'
                }
            },
            axisLabel: {
                color: '#808080',
                formatter: function(value) {
                    const date = new Date(value);
                    return date.toLocaleTimeString();
                }
            }
        },
        yAxis: {
            type: 'value',
            scale: true,
            splitLine: {
                show: true,
                lineStyle: {
                    color: 'rgba(255, 255, 255, 0.05)',
                    type: 'dashed'
                }
            },
            axisLine: {
                lineStyle: {
                    color: 'rgba(255, 255, 255, 0.3)'
                }
            },
            axisLabel: {
                color: '#808080',
                formatter: function(value) {
                    return '$' + value.toFixed(6);
                }
            }
        },
        series: series
    };

    chart.setOption(option, true);
}

// Load whale events as markers
function loadWhaleEvents(data) {
    if (!chart) return;

    console.log('Loading whale events');

    // Get filtered events
    const duringEvents = filterWhaleEventsByUsd(data.whale_events || []);
    const beforeEvents = filterWhaleEventsByUsd(data.whale_events_before || []);
    const afterEvents = filterWhaleEventsByUsd(data.whale_events_after || []);

    // Add whale event series
    const whaleEventSeries = createWhaleEventSeries(duringEvents, beforeEvents, afterEvents, data);

    // Get current option and append whale events
    const currentOption = chart.getOption();
    const newSeries = [...currentOption.series, ...whaleEventSeries];

    chart.setOption({
        series: newSeries
    });

    // Update event statistics
    updateEventStats(duringEvents, beforeEvents, afterEvents);

    // Setup click handler for whale events
    chart.off('click'); // Remove old handlers
    chart.on('click', function(params) {
        if (params.seriesName.includes('Whale')) {
            const eventData = params.data[2]; // Custom data attached to point
            if (eventData && eventData.originalEvent) {
                showSingleEventModal(eventData.originalEvent, eventData.period);
            }
        }
    });
}

// Create whale event marker series
function createWhaleEventSeries(duringEvents, beforeEvents, afterEvents, intervalData) {
    const series = [];

    // Helper to create series for a set of events
    const createSeriesForPeriod = (events, period, baseOpacity = 1) => {
        // Group events by type for different series
        const eventsByType = {};

        events.forEach(event => {
            const type = event.event_type || 'unknown';
            if (!eventsByType[type]) {
                eventsByType[type] = [];
            }
            eventsByType[type].push(event);
        });

        // Create a series for each event type
        Object.entries(eventsByType).forEach(([eventType, typeEvents]) => {
            const color = getEventColor(eventType, period, baseOpacity);
            const symbol = getEventSymbol(eventType);

            // Get USD value range for size scaling
            const usdValues = typeEvents.map(e => e.usd_value || 0);
            const minUsd = Math.min(...usdValues);
            const maxUsd = Math.max(...usdValues);

            // Create data points with collision handling
            const timeOffsets = new Map();
            const dataPoints = typeEvents.map(event => {
                let eventTime = new Date(event.time);

                // Handle time collisions (multiple events at same millisecond)
                const timeKey = Math.floor(eventTime.getTime() / 10);
                if (timeOffsets.has(timeKey)) {
                    const offset = timeOffsets.get(timeKey);
                    timeOffsets.set(timeKey, offset + 1);
                    eventTime = new Date(eventTime.getTime() + offset * 10);
                } else {
                    timeOffsets.set(timeKey, 1);
                }

                // Calculate marker size based on USD value (logarithmic scaling)
                const minSize = period === 'during' ? 8 : 4;
                const maxSize = period === 'during' ? 24 : 12;
                let size = minSize;

                if (maxUsd > minUsd) {
                    const normalizedValue = (Math.log(event.usd_value + 1) - Math.log(minUsd + 1)) /
                                          (Math.log(maxUsd + 1) - Math.log(minUsd + 1));
                    size = minSize + (maxSize - minSize) * normalizedValue;
                }

                // Show USD label for large events
                const usdValue = (event.usd_value || 0) / 1000;
                const label = usdValue >= 1 ? `${usdValue.toFixed(1)}K` : '';

                return [
                    eventTime,
                    event.price || 0,
                    {
                        originalEvent: event,
                        period: period,
                        size: size,
                        label: label
                    }
                ];
            });

            series.push({
                name: `Whale ${eventType} (${period})`,
                type: 'scatter',
                data: dataPoints,
                symbolSize: function(data) {
                    return data[2].size;
                },
                symbol: symbol,
                itemStyle: {
                    color: color.fill,
                    borderColor: color.border,
                    borderWidth: period === 'during' ? 1.5 : 1,
                    opacity: baseOpacity
                },
                label: {
                    show: period === 'during',
                    formatter: function(params) {
                        return params.data[2].label;
                    },
                    position: 'top',
                    color: '#fff',
                    fontSize: 9,
                    fontWeight: 'bold',
                    backgroundColor: 'rgba(0, 0, 0, 0.7)',
                    padding: [2, 4],
                    borderRadius: 3
                },
                z: period === 'during' ? 5 : 3
            });
        });
    };

    // Create series for each period
    createSeriesForPeriod(beforeEvents, 'before', 0.3);
    createSeriesForPeriod(duringEvents, 'during', 1.0);
    createSeriesForPeriod(afterEvents, 'after', 0.3);

    return series;
}

// Get event color based on type and period
function getEventColor(eventType, period, baseOpacity) {
    let baseColor;

    // Definitive events - bright colors
    if (eventType === 'market_buy') {
        baseColor = '#00c2ff'; // Cyan
    } else if (eventType === 'market_sell') {
        baseColor = '#ff00ff'; // Magenta
    } else if (eventType === 'new_bid' || eventType.includes('bid')) {
        baseColor = '#00ff88'; // Green
    } else if (eventType === 'new_ask' || eventType.includes('ask')) {
        baseColor = '#ff4444'; // Red
    } else if (eventType === 'increase') {
        baseColor = '#88cc88'; // Muted green
    } else if (eventType === 'decrease') {
        baseColor = '#cc8888'; // Muted red
    } else {
        baseColor = '#ffaa00'; // Orange for unknown
    }

    // Adjust opacity for period
    let opacity = baseOpacity;
    if (period === 'before') {
        return {
            fill: `rgba(0, 194, 255, ${0.3 * opacity})`,
            border: `rgba(0, 194, 255, ${0.5 * opacity})`
        };
    } else if (period === 'after') {
        return {
            fill: `rgba(255, 59, 105, ${0.3 * opacity})`,
            border: `rgba(255, 59, 105, ${0.5 * opacity})`
        };
    }

    // During period - use base color
    return {
        fill: baseColor,
        border: '#000'
    };
}

// Get event symbol shape
function getEventSymbol(eventType) {
    if (eventType === 'market_buy' || eventType === 'market_sell') {
        return 'circle';
    } else if (eventType === 'new_bid' || eventType.includes('bid')) {
        return 'triangle';
    } else if (eventType === 'new_ask' || eventType.includes('ask')) {
        return 'triangle'; // Will point down via rotation
    } else if (eventType === 'increase' || eventType === 'decrease') {
        return 'diamond';
    }
    return 'circle';
}

// Format tooltip content
function formatTooltip(params, intervalData) {
    if (!params || params.length === 0) return '';

    const timeParam = params[0];
    const time = new Date(timeParam.axisValue);
    const timeStr = time.toLocaleTimeString('en-US', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        fractionalSecondDigits: 3
    });

    let html = `<div style="font-weight: bold; margin-bottom: 8px;">${timeStr}</div>`;

    // Find price value
    const priceParam = params.find(p => p.seriesName === 'Price');
    if (priceParam) {
        const price = priceParam.data[1];
        const startPrice = intervalData.price_data.find(p => new Date(p.time) >= new Date(intervalData.start_time))?.mid_price || price;
        const changePercent = ((price - startPrice) / startPrice) * 100;
        const changeColor = changePercent >= 0 ? '#00ffa3' : '#ff3b69';

        html += `<div style="margin-bottom: 4px;">`;
        html += `Price: <span style="color: #00c2ff;">$${price.toFixed(6)}</span> `;
        html += `<span style="color: ${changeColor};">(${changePercent >= 0 ? '+' : ''}${changePercent.toFixed(3)}%)</span>`;
        html += `</div>`;
    }

    // Find nearby whale events (within 1 second)
    const allEvents = [
        ...(intervalData.whale_events || []).map(e => ({...e, period: 'during'})),
        ...(intervalData.whale_events_before || []).map(e => ({...e, period: 'before'})),
        ...(intervalData.whale_events_after || []).map(e => ({...e, period: 'after'}))
    ];

    const nearbyEvents = allEvents.filter(e => {
        const eventTime = new Date(e.time);
        return Math.abs(eventTime - time) < 1000; // Within 1 second
    });

    if (nearbyEvents.length > 0) {
        html += `<div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.1);">`;
        html += `<div style="font-weight: bold; margin-bottom: 4px;">Whale Events (${nearbyEvents.length}):</div>`;

        // Group by side
        const bids = nearbyEvents.filter(e => e.side === 'bid' || e.event_type === 'market_buy');
        const asks = nearbyEvents.filter(e => e.side === 'ask' || e.event_type === 'market_sell');
        const market = nearbyEvents.filter(e => e.event_type === 'market_buy' || e.event_type === 'market_sell');

        if (bids.length > 0) {
            const totalUsd = bids.reduce((sum, e) => sum + (e.usd_value || 0), 0);
            html += `<div style="color: #00ff88;">▲ Bids: ${bids.length} ($${(totalUsd/1000).toFixed(1)}K)</div>`;
        }
        if (asks.length > 0) {
            const totalUsd = asks.reduce((sum, e) => sum + (e.usd_value || 0), 0);
            html += `<div style="color: #ff4444;">▼ Asks: ${asks.length} ($${(totalUsd/1000).toFixed(1)}K)</div>`;
        }
        if (market.length > 0) {
            const totalUsd = market.reduce((sum, e) => sum + (e.usd_value || 0), 0);
            html += `<div style="color: #ffaa00;">🎯 Market: ${market.length} ($${(totalUsd/1000).toFixed(1)}K)</div>`;
        }

        html += `</div>`;
    }

    return html;
}

// Filter whale events by minimum USD value
function filterWhaleEventsByUsd(events) {
    if (minUsdFilter <= 0) return events;
    return events.filter(event => event.usd_value >= minUsdFilter);
}

// Update event statistics panel
function updateEventStats(duringEvents, beforeEvents, afterEvents) {
    const allEvents = [...duringEvents, ...beforeEvents, ...afterEvents];

    // Total events
    document.getElementById('event-stat-total').textContent = allEvents.length;

    // Total volume
    const totalVolume = allEvents.reduce((sum, e) => sum + (e.usd_value || 0), 0);
    document.getElementById('event-stat-volume').textContent = `$${totalVolume.toLocaleString()}`;

    // Market orders count
    const marketOrders = allEvents.filter(e => e.event_type === 'market_buy' || e.event_type === 'market_sell');
    document.getElementById('event-stat-market').textContent = marketOrders.length;

    // Biggest whale
    const biggestEvent = allEvents.reduce((max, e) => (e.usd_value || 0) > (max.usd_value || 0) ? e : max, { usd_value: 0 });
    document.getElementById('event-stat-biggest').textContent = `$${(biggestEvent.usd_value || 0).toLocaleString()}`;
}

// Show single event modal
function showSingleEventModal(event, period) {
    const modal = document.getElementById('event-details-modal');
    const title = document.getElementById('modal-title');
    const body = document.getElementById('modal-body');

    title.textContent = `${event.event_type} - ${period.toUpperCase()}`;

    const time = new Date(event.time).toLocaleString();
    const color = getEventColor(event.event_type, period, 1.0).fill;

    body.innerHTML = `
        <div style="background: rgba(0,0,0,0.3); padding: 1rem; border-radius: 8px; border-left: 4px solid ${color};">
            <div style="margin-bottom: 0.5rem;"><strong>Time:</strong> ${time}</div>
            <div style="margin-bottom: 0.5rem;"><strong>Type:</strong> ${event.event_type}</div>
            <div style="margin-bottom: 0.5rem;"><strong>Side:</strong> ${event.side || 'N/A'}</div>
            <div style="margin-bottom: 0.5rem;"><strong>Price:</strong> $${(event.price || 0).toFixed(6)}</div>
            <div style="margin-bottom: 0.5rem;"><strong>Volume:</strong> ${(event.volume || 0).toFixed(4)}</div>
            <div style="margin-bottom: 0.5rem;"><strong>USD Value:</strong> $${(event.usd_value || 0).toLocaleString()}</div>
            <div style="margin-bottom: 0.5rem;"><strong>Distance from Mid:</strong> ${(event.distance_from_mid_pct || 0).toFixed(3)}%</div>
        </div>
    `;

    modal.style.display = 'block';
}

// Setup event listeners
function setupEventListeners() {
    // File selector
    document.getElementById('file-selector').addEventListener('change', function() {
        loadDataFile(this.value);
    });

    // Refresh button
    document.getElementById('refresh-btn').addEventListener('click', () => {
        loadFileList();
    });

    // New analysis button
    document.getElementById('new-analysis-btn').addEventListener('click', () => {
        document.getElementById('new-analysis-modal').style.display = 'block';
    });

    // Zero state button
    document.getElementById('zero-state-new-analysis').addEventListener('click', () => {
        document.getElementById('new-analysis-modal').style.display = 'block';
    });

    // Analysis form
    document.getElementById('analysis-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        await runAnalysis();
    });

    // Interval selector
    document.getElementById('interval-selector').addEventListener('change', function() {
        const index = parseInt(this.value);
        if (!isNaN(index) && currentData && currentData[index]) {
            loadInterval(currentData[index]);
        }
    });

    // Export button
    document.getElementById('export-interval-btn').addEventListener('click', () => {
        if (currentInterval) {
            exportInterval(currentInterval);
        }
    });

    // USD filter
    document.getElementById('min-usd-filter').addEventListener('input', function() {
        minUsdFilter = parseFloat(this.value) || 0;
        if (currentInterval) {
            // Reload with new filter
            updateStats(currentInterval);
            loadWhaleEvents(currentInterval);
        }
    });

    // Fullscreen
    document.getElementById('fullscreen-btn').addEventListener('click', toggleFullscreen);
}

// Run new whale activity analysis
async function runAnalysis() {
    const form = document.getElementById('analysis-form');
    const statusDiv = document.getElementById('analysis-status');
    const statusMsg = document.getElementById('status-message');

    form.style.display = 'none';
    statusDiv.style.display = 'block';
    statusMsg.textContent = 'Running whale activity analysis...';

    try {
        const params = {
            symbol: document.getElementById('symbol-input').value,
            lookback: document.getElementById('lookback-input').value,
            top: parseInt(document.getElementById('top-input').value),
            min_usd: parseFloat(document.getElementById('min-usd-input').value),
            sort_by: document.getElementById('sort-by-input').value,
            analyzer_type: 'top_market_orders'  // Individual orders, not intervals
        };

        // Optional distance filters
        const maxDistanceInput = document.getElementById('max-distance-input');
        const minDistanceInput = document.getElementById('min-distance-input');

        if (maxDistanceInput && maxDistanceInput.value) {
            params.max_distance = parseFloat(maxDistanceInput.value);
        }
        if (minDistanceInput && minDistanceInput.value) {
            params.min_distance = parseFloat(minDistanceInput.value);
        }

        const response = await fetch('/api/run-whale-analysis', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
        });

        const result = await response.json();

        if (result.error) {
            throw new Error(result.error);
        }

        statusMsg.textContent = 'Analysis complete! Loading data...';

        // Close modal
        document.getElementById('new-analysis-modal').style.display = 'none';

        // Reload file list and select new analysis
        await loadFileList();

        if (result.id) {
            document.getElementById('file-selector').value = result.id;
            await loadDataFile(result.id);
        }

    } catch (error) {
        console.error('Analysis error:', error);
        statusMsg.textContent = 'Error: ' + error.message;
        statusMsg.style.color = '#ff3b69';
    } finally {
        setTimeout(() => {
            form.style.display = 'block';
            statusDiv.style.display = 'none';
            statusMsg.textContent = 'Running whale activity analysis...';
            statusMsg.style.color = '';
        }, 2000);
    }
}

// Export current interval
function exportInterval(interval) {
    const dataStr = JSON.stringify(interval, null, 2);
    const dataUri = 'data:application/json;charset=utf-8,' + encodeURIComponent(dataStr);

    const exportName = `whale_activity_${interval.symbol}_rank${interval.rank}_${new Date().toISOString()}.json`;

    const linkElement = document.createElement('a');
    linkElement.setAttribute('href', dataUri);
    linkElement.setAttribute('download', exportName);
    linkElement.click();
}

// Toggle fullscreen
function toggleFullscreen() {
    const wrapper = document.querySelector('.chart-wrapper');

    if (!document.fullscreenElement) {
        wrapper.requestFullscreen().catch(err => {
            console.error('Fullscreen error:', err);
        });
    } else {
        document.exitFullscreen();
    }

    // Resize chart after transition
    setTimeout(() => {
        if (chart) {
            chart.resize();
        }
    }, 350);
}

// Show/hide loading spinner
function showLoading(show) {
    const loading = document.getElementById('loading');
    if (loading) {
        loading.style.display = show ? 'flex' : 'none';
    }
}

// Show/hide zero state
function showZeroState(show) {
    const zeroState = document.getElementById('zero-state');
    if (zeroState) {
        zeroState.style.display = show ? 'flex' : 'none';
    }
}

// Show error message
function showError(message) {
    const toast = document.getElementById('error-toast');
    const messageElem = document.getElementById('error-message');

    messageElem.textContent = message;
    toast.style.display = 'flex';

    // Auto-hide after 5 seconds
    setTimeout(() => {
        toast.style.display = 'none';
    }, 5000);
}
