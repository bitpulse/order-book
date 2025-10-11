// Whale Activity Dashboard - Chart and Events Handler (Apache ECharts)

let chart = null;
let currentData = null;
let currentInterval = null;
let minUsdFilter = 0; // Global filter for minimum USD value

// Event type filters (matching live chart)
let filters = {
    price: true,
    marketBuy: true,
    marketSell: true,
    newBid: true,
    newAsk: true,
    bidIncrease: true,
    askIncrease: true
};

// Initialize dashboard on load
document.addEventListener('DOMContentLoaded', async () => {
    await loadFileList();
    setupEventListeners();
    showLoading(false);
});

// Load available top market orders data files
async function loadFileList() {
    try {
        const response = await fetch('/api/top-market-orders-files');
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
            selector.innerHTML = '<option value="">No analyses found</option>';
        }
    } catch (error) {
        console.error('Error loading analysis list:', error);
        showError('Failed to load analyses: ' + error.message);
    }
}

// Load data from selected analysis
async function loadDataFile(analysisId) {
    if (!analysisId) return;

    showLoading(true);

    try {
        const response = await fetch(`/api/top-market-orders-data/${analysisId}`);
        let data = await response.json();

        console.log('Loaded whale activity data:', data);

        if (data.error) {
            throw new Error(data.error);
        }

        // Handle JSON format with metadata (intervals format)
        let intervals = data.intervals || [];
        let metadata = data.metadata;

        console.log('Loaded intervals:', intervals.length);
        console.log('Metadata:', metadata);

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

        // Get the main order event type
        const mainEvent = interval.whale_events && interval.whale_events[0];
        const eventType = mainEvent ? mainEvent.event_type : '';
        const eventSymbol = eventType === 'market_buy' ? '▲' : eventType === 'market_sell' ? '▼' : '●';
        const eventLabel = eventType === 'market_buy' ? 'BUY' : eventType === 'market_sell' ? 'SELL' : '';

        option.textContent = `#${interval.rank} ${eventSymbol} ${eventLabel} $${(interval.total_usd_volume || 0).toLocaleString()} @ ${startTime}`;
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

    // Show the exact order time
    const mainEvent = data.whale_events && data.whale_events[0];
    if (mainEvent) {
        const orderTime = new Date(mainEvent.time).toLocaleTimeString();
        document.getElementById('stat-time').textContent = orderTime;
    } else {
        document.getElementById('stat-time').textContent = '-';
    }

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

    // Main price line (respect filter)
    series.push({
        name: 'Price',
        type: 'line',
        data: filters.price ? chartData.map(d => [d.time, d.value]) : [],
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

    // SPIKE marker (skip START/END for individual orders)
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

    // Update chart series - rebuild price series to avoid stale references
    const currentOption = chart.getOption();

    // Get price data from first series (it should still have the data)
    const existingPriceData = currentOption.series[0]?.data || [];

    // Recreate price series from scratch with current filter state
    const priceSeries = {
        name: 'Price',
        type: 'line',
        data: filters.price ? existingPriceData : [],
        lineStyle: {
            color: '#00c2ff',
            width: 2.5,
            shadowBlur: 4,
            shadowColor: 'rgba(0, 194, 255, 0.3)'
        },
        areaStyle: {
            color: {
                type: 'linear',
                x: 0, y: 0, x2: 0, y2: 1,
                colorStops: [
                    { offset: 0, color: 'rgba(0, 194, 255, 0.15)' },
                    { offset: 1, color: 'rgba(0, 194, 255, 0.01)' }
                ]
            }
        },
        symbol: 'none',
        smooth: 0.3,
        sampling: 'lttb',
        z: 1
    };

    // Use replaceMerge to completely replace the series array (not merge)
    chart.setOption({
        series: [priceSeries, ...whaleEventSeries]
    }, {
        replaceMerge: ['series']
    });

    // Update event statistics
    updateEventStats(duringEvents, beforeEvents, afterEvents);

    // Setup click handler for whale events
    chart.off('click'); // Remove old handlers
    chart.on('click', function(params) {
        // Check if this is an event marker (scatter series with custom data)
        if (params.componentType === 'series' && params.seriesType === 'scatter' && params.data && params.data[2]) {
            const eventData = params.data[2]; // Custom data attached to point
            if (eventData && eventData.originalEvent) {
                showSingleEventModal(eventData.originalEvent, eventData.period);
            }
        }
    });
}

// Create whale event marker series (matching live_chart.js categorization)
function createWhaleEventSeries(duringEvents, beforeEvents, afterEvents, intervalData) {
    const series = [];

    // Helper to create series for a set of events
    const createSeriesForPeriod = (events, period, baseOpacity = 1) => {
        // Categorize events EXACTLY like live_chart.js (lines 729-742)
        const marketBuys = events.filter(e => e.event_type === 'market_buy');
        const marketSells = events.filter(e => e.event_type === 'market_sell');
        const newBids = events.filter(e => e.event_type === 'new_bid' || (e.side === 'bid' && !e.event_type.includes('increase') && !e.event_type.includes('decrease')));
        const newAsks = events.filter(e => e.event_type === 'new_ask' || (e.side === 'ask' && !e.event_type.includes('increase') && !e.event_type.includes('decrease')));

        // Volume changes (ambiguous events)
        const bidIncreases = events.filter(e => e.event_type === 'increase' && e.side === 'bid');
        const askIncreases = events.filter(e => e.event_type === 'increase' && e.side === 'ask');
        const askDecreases = events.filter(e => e.event_type === 'decrease' && e.side === 'ask');
        const bidDecreases = events.filter(e => e.event_type === 'decrease' && e.side === 'bid');

        // Combine for ambiguous categories (support/resistance building)
        const bidIncreasesAll = [...bidIncreases, ...askDecreases]; // Support building
        const askIncreasesAll = [...askIncreases, ...bidDecreases]; // Resistance building

        // Calculate GLOBAL min/max USD across ALL events for consistent sizing
        const allUsdValues = events.map(e => e.usd_value || 0);
        const globalMinUsd = allUsdValues.length > 0 ? Math.min(...allUsdValues) : 0;
        const globalMaxUsd = allUsdValues.length > 0 ? Math.max(...allUsdValues) : 0;

        // Create series for each category with EXACT live chart colors
        const categories = [
            { name: 'Market Buy', events: marketBuys, color: '#00c2ff', symbol: 'circle', filterKey: 'marketBuy' },
            { name: 'Market Sell', events: marketSells, color: '#ff00ff', symbol: 'circle', filterKey: 'marketSell' },
            { name: 'New Bid', events: newBids, color: '#00ff88', symbol: 'triangle', filterKey: 'newBid' },
            { name: 'New Ask', events: newAsks, color: '#ff4444', symbol: 'triangle', filterKey: 'newAsk' },
            { name: 'Bid Increase', events: bidIncreasesAll, color: '#88cc88', symbol: 'diamond', filterKey: 'bidIncrease' },
            { name: 'Ask Increase', events: askIncreasesAll, color: '#cc8888', symbol: 'diamond', filterKey: 'askIncrease' }
        ];

        categories.forEach(({ name, events: typeEvents, color, symbol, filterKey }) => {
            // Skip if filtered out or no events
            if (!filters[filterKey] || typeEvents.length === 0) return;

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

                // Calculate marker size based on USD value (EXACT same as live_chart.js)
                // Use GLOBAL min/max so all events are sized relative to each other
                const baseSize = 12;
                const minSize = 8;
                const maxSize = 24;
                let size;

                if (globalMaxUsd === globalMinUsd) {
                    // All values are the same
                    size = baseSize;
                } else {
                    // Logarithmic scaling for better distribution (matches live_chart.js lines 686-700)
                    const normalizedValue = (Math.log(event.usd_value + 1) - Math.log(globalMinUsd + 1)) /
                                          (Math.log(globalMaxUsd + 1) - Math.log(globalMinUsd + 1));
                    size = minSize + (maxSize - minSize) * normalizedValue;
                }

                // Adjust size for period (make before/after slightly smaller)
                if (period !== 'during') {
                    size = size * 0.75;
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
                name: `${name} (${period})`,
                type: 'scatter',
                data: dataPoints,
                symbolSize: function(data) {
                    return data[2].size;
                },
                symbol: symbol,
                itemStyle: {
                    color: color,
                    borderColor: color,
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

    // Event type breakdown (matching live chart categorization)
    const marketBuys = allEvents.filter(e => e.event_type === 'market_buy').length;
    const marketSells = allEvents.filter(e => e.event_type === 'market_sell').length;
    const newBids = allEvents.filter(e => e.event_type === 'new_bid' || (e.side === 'bid' && !e.event_type.includes('increase') && !e.event_type.includes('decrease'))).length;
    const newAsks = allEvents.filter(e => e.event_type === 'new_ask' || (e.side === 'ask' && !e.event_type.includes('increase') && !e.event_type.includes('decrease'))).length;
    const bidIncreases = allEvents.filter(e => e.event_type === 'increase' && e.side === 'bid').length;
    const askIncreases = allEvents.filter(e => e.event_type === 'increase' && e.side === 'ask').length;
    const askDecreases = allEvents.filter(e => e.event_type === 'decrease' && e.side === 'ask').length;
    const bidDecreases = allEvents.filter(e => e.event_type === 'decrease' && e.side === 'bid').length;

    const breakdown = [
        `Buy: ${marketBuys}`,
        `Sell: ${marketSells}`,
        `NewBid: ${newBids}`,
        `NewAsk: ${newAsks}`,
        `Bid↑: ${bidIncreases + askDecreases}`,
        `Ask↑: ${askIncreases + bidDecreases}`
    ].filter(s => !s.endsWith(': 0')).join(' | ');

    document.getElementById('event-stat-market').textContent = breakdown || 'None';

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

    modal.style.display = 'flex';
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
        document.getElementById('new-analysis-modal').style.display = 'flex';
    });

    // Zero state button
    document.getElementById('zero-state-new-analysis').addEventListener('click', () => {
        document.getElementById('new-analysis-modal').style.display = 'flex';
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

    // Filter checkboxes
    document.getElementById('filter-price').addEventListener('change', (e) => {
        filters.price = e.target.checked;
        if (currentInterval) loadWhaleEvents(currentInterval);
    });

    document.getElementById('filter-market-buy').addEventListener('change', (e) => {
        filters.marketBuy = e.target.checked;
        if (currentInterval) loadWhaleEvents(currentInterval);
    });

    document.getElementById('filter-market-sell').addEventListener('change', (e) => {
        filters.marketSell = e.target.checked;
        if (currentInterval) loadWhaleEvents(currentInterval);
    });

    document.getElementById('filter-new-bid').addEventListener('change', (e) => {
        filters.newBid = e.target.checked;
        if (currentInterval) loadWhaleEvents(currentInterval);
    });

    document.getElementById('filter-new-ask').addEventListener('change', (e) => {
        filters.newAsk = e.target.checked;
        if (currentInterval) loadWhaleEvents(currentInterval);
    });

    document.getElementById('filter-bid-increase').addEventListener('change', (e) => {
        filters.bidIncrease = e.target.checked;
        if (currentInterval) loadWhaleEvents(currentInterval);
    });

    document.getElementById('filter-ask-increase').addEventListener('change', (e) => {
        filters.askIncrease = e.target.checked;
        if (currentInterval) loadWhaleEvents(currentInterval);
    });

    // Keyboard shortcuts (matching live_chart.js)
    document.addEventListener('keydown', (e) => {
        // ESC key: close modal first, then exit fullscreen
        if (e.key === 'Escape') {
            // First check if any modal is open
            const newAnalysisModal = document.getElementById('new-analysis-modal');
            const eventDetailsModal = document.getElementById('event-details-modal');

            if (newAnalysisModal && newAnalysisModal.style.display === 'flex') {
                newAnalysisModal.style.display = 'none';
            } else if (eventDetailsModal && eventDetailsModal.style.display === 'flex') {
                eventDetailsModal.style.display = 'none';
            } else {
                // If no modal, exit fullscreen if active
                const wrapper = document.querySelector('.chart-wrapper');
                if (wrapper.classList.contains('fullscreen')) {
                    toggleFullscreen();
                }
            }
        }
        // F for fullscreen toggle
        if (e.key === 'f' || e.key === 'F') {
            // Only if not typing in an input field
            if (!['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
                toggleFullscreen();
            }
        }
    });
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

        // Reload file list and select new file
        await loadFileList();

        if (result.filename) {
            document.getElementById('file-selector').value = result.filename;
            await loadDataFile(result.filename);
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

// Toggle fullscreen mode for chart (EXACT match with live_chart.js)
function toggleFullscreen() {
    const wrapper = document.querySelector('.chart-wrapper');
    const btn = document.getElementById('fullscreen-btn');

    if (wrapper.classList.contains('fullscreen')) {
        // Exit fullscreen
        wrapper.classList.remove('fullscreen');
        btn.textContent = '⛶';
        btn.title = 'Toggle Fullscreen';
    } else {
        // Enter fullscreen
        wrapper.classList.add('fullscreen');
        btn.textContent = '⛶';
        btn.title = 'Exit Fullscreen';
    }

    // Resize chart to fit new container size
    if (chart) {
        // Use longer timeout to ensure CSS transition completes
        setTimeout(() => {
            chart.resize();
        }, 350);
    }
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
