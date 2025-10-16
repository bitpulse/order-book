// Price Change Analyzer Dashboard - Chart and Events Handler (Apache ECharts)

let chart = null;
let currentData = null;
let currentInterval = null;
let minUsdFilter = 0; // Global filter for minimum USD value

// Filter state for legend toggles
let filters = {
    price: true,
    marketBuy: true,
    marketSell: true,
    newBid: false,
    newAsk: false,
    bidIncrease: false,
    askIncrease: false
};

// Initialize dashboard on load
document.addEventListener('DOMContentLoaded', async () => {
    await loadFileList();
    setupEventListeners();
    setupFilterListeners();
    // Hide loading spinner initially (show zero state instead)
    showLoading(false);
});

// Load available analyses from MongoDB
async function loadFileList() {
    try {
        const response = await fetch('/api/files');
        const data = await response.json();

        const selector = document.getElementById('file-selector');
        selector.innerHTML = '<option value="">Select an analysis...</option>';

        if (data.files && data.files.length > 0) {
            data.files.forEach(file => {
                const option = document.createElement('option');
                option.value = file.id;  // Use MongoDB ID instead of filename
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
        const response = await fetch(`/api/data/${analysisId}`);
        let data = await response.json();

        console.log('Loaded data:', data);

        if (data.error) {
            throw new Error(data.error);
        }

        // Handle MongoDB format: {analysis: {...}, intervals: [...]}
        let intervals, analysis;
        if (Array.isArray(data)) {
            // Legacy format
            intervals = data;
            analysis = null;
        } else {
            intervals = data.intervals;
            analysis = data.analysis;
        }

        console.log('Intervals:', intervals);
        console.log('Analysis:', analysis);

        currentData = intervals;

        // Extract and display analysis metadata
        updateAnalysisInfo(analysisId, intervals, analysis);

        // If multiple intervals, show selector
        if (intervals.length > 1) {
            showIntervalSelector(intervals);
        } else {
            document.getElementById('interval-selector-container').style.display = 'none';
        }

        // Load first interval
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
function updateAnalysisInfo(analysisId, intervals, analysis) {
    const infoElement = document.getElementById('analysis-info');

    if (analysis && analysis.symbol) {
        document.getElementById('info-symbol').textContent = analysis.symbol || 'N/A';
        document.getElementById('info-interval').textContent = analysis.interval || 'N/A';
        document.getElementById('info-lookback').textContent = analysis.lookback || 'N/A';
        document.getElementById('info-threshold').textContent = analysis.min_change ? `${analysis.min_change}%` : 'N/A';
        infoElement.style.display = 'flex';
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
        option.textContent = `#${interval.rank} - ${interval.change_pct.toFixed(3)}% @ ${startTime}`;
        selector.appendChild(option);
    });

    container.style.display = 'block';
}

// Load specific interval data
async function loadInterval(intervalData) {
    currentInterval = intervalData;

    // Hide zero state and show chart
    showZeroState(false);

    // Add loading state to stats
    const statsContainer = document.getElementById('stats-summary');
    statsContainer.classList.add('loading');

    // Check if this is new format (with time_windows) or old format (with embedded data)
    const isNewFormat = intervalData.time_windows && !intervalData.price_data;

    if (isNewFormat) {
        // New format: Fetch data on-demand from InfluxDB
        await loadIntervalWithLazyLoading(intervalData);
    } else {
        // Old format: Use embedded data
        loadIntervalWithEmbeddedData(intervalData);
    }
}

// Load interval with embedded data (old format)
function loadIntervalWithEmbeddedData(intervalData) {
    // Update stats
    updateStats(intervalData);

    // Initialize or update chart
    if (!chart) {
        initializeChart();
    }

    // Load price data
    loadPriceData(intervalData);

    // Load whale events
    loadWhaleEvents(intervalData);

    // Update analytics panels (skip hero and enhanced stats - they were removed)
    const allWhaleEvents = [
        ...(intervalData.whale_events_before || []),
        ...(intervalData.whale_events || []),
        ...(intervalData.whale_events_after || [])
    ];
    updateContextCards(intervalData, allWhaleEvents, intervalData.price_data);

    // Update event type statistics panel
    updateEventStatsPanel(
        intervalData,
        intervalData.whale_events_before,
        intervalData.whale_events,
        intervalData.whale_events_after
    );
}

// Load interval with lazy loading (new format)
async function loadIntervalWithLazyLoading(intervalData) {
    // Update stats from pre-computed statistics
    updateStatsFromStatistics(intervalData);

    // Initialize or update chart
    if (!chart) {
        initializeChart();
    }

    // Show loading indicator
    showDetailedDataLoading(true);

    try {
        // Fetch raw price data on-demand from InfluxDB
        const priceDataResponse = await fetch(`/api/price-data?` + new URLSearchParams({
            symbol: intervalData.symbol || currentData[0].symbol, // Get symbol from interval or first interval
            start: intervalData.time_windows.extended_start,
            end: intervalData.time_windows.extended_end
        }));

        if (!priceDataResponse.ok) {
            throw new Error(`Failed to fetch price data: ${priceDataResponse.statusText}`);
        }

        const priceResult = await priceDataResponse.json();

        // Fetch raw whale events on-demand from InfluxDB
        const whaleEventsResponse = await fetch(`/api/whale-events?` + new URLSearchParams({
            symbol: intervalData.symbol || currentData[0].symbol,
            start: intervalData.time_windows.extended_start,
            end: intervalData.time_windows.extended_end
        }));

        if (!whaleEventsResponse.ok) {
            throw new Error(`Failed to fetch whale events: ${whaleEventsResponse.statusText}`);
        }

        const whaleResult = await whaleEventsResponse.json();

        // Separate events by period
        const startTime = new Date(intervalData.start_time).getTime();
        const endTime = new Date(intervalData.end_time).getTime();

        // Add fetched data to interval (for rendering)
        intervalData.price_data = priceResult.price_data;
        intervalData.whale_events_before = whaleResult.whale_events.filter(e =>
            new Date(e.time).getTime() < startTime
        );
        intervalData.whale_events = whaleResult.whale_events.filter(e => {
            const t = new Date(e.time).getTime();
            return t >= startTime && t <= endTime;
        });
        intervalData.whale_events_after = whaleResult.whale_events.filter(e =>
            new Date(e.time).getTime() > endTime
        );

        console.log(`Loaded ${priceResult.price_data.length} price points, ${whaleResult.whale_events.length} whale events`);

        // Load price data into chart
        loadPriceData(intervalData);

        // Load whale events
        loadWhaleEvents(intervalData);

        // Update analytics panels (skip hero and enhanced stats - they were removed)
        const allWhaleEvents = [
            ...intervalData.whale_events_before,
            ...intervalData.whale_events,
            ...intervalData.whale_events_after
        ];
        updateContextCards(intervalData, allWhaleEvents, intervalData.price_data);

        // Update event type statistics panel
        updateEventStatsPanel(
            intervalData,
            intervalData.whale_events_before,
            intervalData.whale_events,
            intervalData.whale_events_after
        );

        showDetailedDataLoading(false);

    } catch (error) {
        console.error('Error loading interval details:', error);
        showError('Failed to load detailed data: ' + error.message);
        showDetailedDataLoading(false);
    }
}

// New function to update stats from pre-computed statistics
function updateStatsFromStatistics(data) {
    // Remove loading state
    const statsContainer = document.getElementById('stats-summary');
    statsContainer.classList.remove('loading');

    document.getElementById('stat-rank').textContent = `#${data.rank}`;

    const changeElem = document.getElementById('stat-change');
    changeElem.textContent = `${data.change_pct.toFixed(3)}%`;
    changeElem.className = 'stat-value ' + (data.change_pct > 0 ? 'positive' : 'negative');

    const startTime = new Date(data.start_time).toLocaleTimeString();
    const endTime = new Date(data.end_time).toLocaleTimeString();
    document.getElementById('stat-time').textContent = `${startTime} → ${endTime}`;

    document.getElementById('stat-price').textContent = `$${data.start_price.toFixed(6)} → $${data.end_price.toFixed(6)}`;
}

function showDetailedDataLoading(show) {
    const chartContainer = document.getElementById('chart-container');
    let loader = document.getElementById('detail-loader');

    if (show) {
        if (!loader) {
            loader = document.createElement('div');
            loader.id = 'detail-loader';
            loader.style.cssText = 'position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); ' +
                                  'background: rgba(0, 0, 0, 0.8); padding: 20px 40px; border-radius: 8px; ' +
                                  'color: #00ffa3; font-size: 16px; z-index: 1000;';
            loader.textContent = 'Loading detailed data...';
            chartContainer.appendChild(loader);
        }
        loader.style.display = 'block';
    } else {
        if (loader) {
            loader.style.display = 'none';
        }
    }
}

// Update statistics display
function updateStats(data) {
    // Remove loading state
    const statsContainer = document.getElementById('stats-summary');
    statsContainer.classList.remove('loading');

    document.getElementById('stat-rank').textContent = `#${data.rank}`;

    const changeElem = document.getElementById('stat-change');
    changeElem.textContent = `${data.change_pct.toFixed(3)}%`;
    changeElem.className = 'stat-value ' + (data.change_pct > 0 ? 'positive' : 'negative');

    const startTime = new Date(data.start_time).toLocaleTimeString();
    const endTime = new Date(data.end_time).toLocaleTimeString();
    document.getElementById('stat-time').textContent = `${startTime} → ${endTime}`;

    document.getElementById('stat-price').textContent = `$${data.start_price.toFixed(6)} → $${data.end_price.toFixed(6)}`;
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
        showError('Invalid price data format');
        return;
    }

    const chartData = data.price_data.map(point => ({
        time: new Date(point.time),
        value: point.mid_price || point.price  // Support both field names
    }));

    console.log('Chart data sample:', chartData.slice(0, 5));
    console.log('Total price points:', chartData.length);

    // Filter events by USD
    const filteredBefore = filterWhaleEventsByUsd(data.whale_events_before || []);
    const filteredDuring = filterWhaleEventsByUsd(data.whale_events || []);
    const filteredAfter = filterWhaleEventsByUsd(data.whale_events_after || []);

    // Prepare whale event scatter data with artificial offsets for same timestamps
    const whaleScatterBefore = prepareWhaleScatterData(filteredBefore, 'before');
    const whaleScatterDuring = prepareWhaleScatterData(filteredDuring, 'during');
    const whaleScatterAfter = prepareWhaleScatterData(filteredAfter, 'after');

    // Get interval boundaries
    const startTime = new Date(data.start_time);
    const endTime = new Date(data.end_time);

    // ECharts option
    const option = {
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
            formatter: function(params) {
                return formatTooltip(params, data);
            },
            padding: [12, 16],
            shadowBlur: 20,
            shadowColor: 'rgba(0, 255, 163, 0.1)'
        },
        legend: {
            show: true,
            top: '2%',
            left: 'center',
            data: ['Price', 'Whale (Before)', 'Whale (During)', 'Whale (After)'],
            textStyle: {
                color: '#b0b0b0',
                fontSize: 12
            },
            itemWidth: 20,
            itemHeight: 12,
            itemGap: 20,
            selectedMode: true,
            inactiveColor: '#404040',
            selected: {
                'Price': true,
                'Whale (Before)': true,
                'Whale (During)': true,
                'Whale (After)': true
            }
        },
        grid: {
            left: '2%',
            right: '3%',
            bottom: '10%',
            top: '12%',
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
                    lineStyle: {
                        color: '#00c2ff',
                        width: 1.5
                    },
                    areaStyle: {
                        color: 'rgba(0, 194, 255, 0.1)'
                    }
                },
                selectedDataBackground: {
                    lineStyle: {
                        color: '#00c2ff',
                        width: 2
                    },
                    areaStyle: {
                        color: 'rgba(0, 194, 255, 0.3)'
                    }
                },
                fillerColor: 'rgba(0, 194, 255, 0.15)',
                borderColor: 'rgba(255, 255, 255, 0.1)',
                handleStyle: {
                    color: '#00c2ff',
                    borderColor: '#00c2ff',
                    shadowBlur: 8,
                    shadowColor: 'rgba(0, 194, 255, 0.5)'
                },
                textStyle: {
                    color: '#b0b0b0'
                },
                emphasis: {
                    handleStyle: {
                        shadowBlur: 12,
                        shadowColor: 'rgba(0, 194, 255, 0.8)'
                    }
                }
            }
        ],
        xAxis: {
            type: 'time',
            boundaryGap: false,
            axisLine: {
                lineStyle: {
                    color: 'rgba(255, 255, 255, 0.1)',
                    width: 1
                }
            },
            axisTick: {
                lineStyle: {
                    color: 'rgba(255, 255, 255, 0.1)'
                }
            },
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
            axisLine: {
                lineStyle: {
                    color: 'rgba(255, 255, 255, 0.1)',
                    width: 1
                }
            },
            splitLine: {
                lineStyle: {
                    color: 'rgba(255, 255, 255, 0.05)',
                    type: 'dashed'
                }
            },
            axisTick: {
                lineStyle: {
                    color: 'rgba(255, 255, 255, 0.1)'
                }
            },
            axisLabel: {
                color: '#808080',
                fontSize: 11,
                formatter: function(value) {
                    if (value == null) return '$0';
                    return '$' + value.toFixed(6);
                }
            }
        },
        series: [
            // Main price line
            filters.price ? {
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
                emphasis: {
                    lineStyle: {
                        width: 3.5,
                        shadowBlur: 8,
                        shadowColor: 'rgba(0, 194, 255, 0.5)'
                    }
                },
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
            } : null,
            // START marker
            {
                name: 'START',
                type: 'scatter',
                data: [[startTime, data.start_price]],
                symbolSize: 10,
                itemStyle: {
                    color: '#ffd60a',
                    shadowBlur: 4,
                    shadowColor: 'rgba(255, 214, 10, 0.3)',
                    borderWidth: 1,
                    borderColor: 'rgba(255, 214, 10, 0.5)'
                },
                label: {
                    show: true,
                    formatter: 'START',
                    position: 'top',
                    color: '#ffd60a',
                    fontSize: 9,
                    fontWeight: 'normal',
                    shadowBlur: 2,
                    shadowColor: 'rgba(255, 214, 10, 0.3)'
                },
                z: 7
            },
            // END marker
            {
                name: 'END',
                type: 'scatter',
                data: [[endTime, data.end_price]],
                symbolSize: 10,
                itemStyle: {
                    color: '#ffd60a',
                    shadowBlur: 4,
                    shadowColor: 'rgba(255, 214, 10, 0.3)',
                    borderWidth: 1,
                    borderColor: 'rgba(255, 214, 10, 0.5)'
                },
                label: {
                    show: true,
                    formatter: 'END',
                    position: 'top',
                    color: '#ffd60a',
                    fontSize: 9,
                    fontWeight: 'normal',
                    shadowBlur: 2,
                    shadowColor: 'rgba(255, 214, 10, 0.3)'
                },
                z: 7
            },
            // Whale events - BEFORE (semi-transparent blue)
            {
                name: 'Whale (Before)',
                type: 'scatter',
                data: whaleScatterBefore.map(e => [e.time, e.price, e]),
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
            },
            // Whale events - DURING (full opacity)
            {
                name: 'Whale (During)',
                type: 'scatter',
                data: whaleScatterDuring.map(e => [e.time, e.price, e]),
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
                z: 8
            },
            // Whale events - AFTER (semi-transparent red)
            {
                name: 'Whale (After)',
                type: 'scatter',
                data: whaleScatterAfter.map(e => [e.time, e.price, e]),
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
            }
        ].filter(s => s !== null)
    };

    chart.setOption(option);

    // Add click handler for single event details modal
    chart.on('click', function(params) {
        if (params.componentType === 'series' && params.seriesName.includes('Whale')) {
            const eventData = params.data[2];
            if (eventData && eventData.originalEvent) {
                showSingleEventModal(eventData.originalEvent, eventData.period);
            }
        }
    });
}

// Prepare whale event scatter data with offset for overlapping timestamps
function prepareWhaleScatterData(events, period) {
    if (!events || events.length === 0) return [];

    // Filter events based on legend filters
    const filteredEvents = events.filter(event => {
        const isMarketBuy = event.event_type === 'market_buy';
        const isMarketSell = event.event_type === 'market_sell';
        const isIncrease = event.event_type === 'increase';
        const isDecrease = event.event_type === 'decrease';
        const isBid = event.side === 'bid' || event.event_type.includes('bid');
        const isAsk = event.side === 'ask' || event.event_type.includes('ask');
        const isNewBid = !isMarketBuy && !isMarketSell && !isIncrease && !isDecrease && isBid;
        const isNewAsk = !isMarketBuy && !isMarketSell && !isIncrease && !isDecrease && isAsk;

        // Apply filters
        if (isMarketBuy && !filters.marketBuy) return false;
        if (isMarketSell && !filters.marketSell) return false;
        if (isNewBid && !filters.newBid) return false;
        if (isNewAsk && !filters.newAsk) return false;
        if ((isIncrease && isBid) && !filters.bidIncrease) return false;
        if ((isIncrease && isAsk) && !filters.askIncrease) return false;
        if ((isDecrease && isBid) && !filters.askIncrease) return false; // bid decrease = resistance building
        if ((isDecrease && isAsk) && !filters.bidIncrease) return false; // ask decrease = support building

        return true;
    });

    // Sort by time
    const sortedEvents = [...filteredEvents].sort((a, b) => new Date(a.time) - new Date(b.time));

    // Find min and max USD values for scaling
    const usdValues = sortedEvents.map(e => e.usd_value);
    const minUsd = Math.min(...usdValues);
    const maxUsd = Math.max(...usdValues);

    // Track offsets for same timestamps
    const timeOffsets = new Map();

    return sortedEvents.map(event => {
        const isMarketBuy = event.event_type === 'market_buy';
        const isMarketSell = event.event_type === 'market_sell';
        const isIncrease = event.event_type === 'increase';
        const isDecrease = event.event_type === 'decrease';
        const isBid = event.side === 'bid' || event.event_type.includes('bid');
        const isAsk = event.side === 'ask' || event.event_type.includes('ask');

        let color, symbol, labelPosition;

        // Definitive events - bright colors
        if (isMarketBuy) {
            color = period === 'during' ? '#00c2ff' : 'rgba(0, 194, 255, 0.3)'; // Bright cyan/blue
            symbol = 'circle';
            labelPosition = 'bottom';
        } else if (isMarketSell) {
            color = period === 'during' ? '#ff00ff' : 'rgba(255, 0, 255, 0.3)'; // Bright magenta/pink
            symbol = 'circle';
            labelPosition = 'top';
        }
        // Volume changes - muted colors (ambiguous: could be cancellation or modification)
        else if (isIncrease && isBid) {
            color = period === 'during' ? '#88cc88' : 'rgba(136, 204, 136, 0.3)'; // Muted green (potential support)
            symbol = 'diamond';
            labelPosition = 'bottom';
        } else if (isIncrease && isAsk) {
            color = period === 'during' ? '#cc8888' : 'rgba(204, 136, 136, 0.3)'; // Muted red (potential resistance)
            symbol = 'diamond';
            labelPosition = 'top';
        } else if (isDecrease && isBid) {
            color = period === 'during' ? '#cc8888' : 'rgba(204, 136, 136, 0.3)'; // Muted red (support weakening)
            symbol = 'diamond';
            labelPosition = 'top';
        } else if (isDecrease && isAsk) {
            color = period === 'during' ? '#88cc88' : 'rgba(136, 204, 136, 0.3)'; // Muted green (resistance weakening)
            symbol = 'diamond';
            labelPosition = 'bottom';
        }
        // New orders - bright colors
        else if (isBid) {
            color = period === 'during' ? '#00ff88' : 'rgba(0, 255, 136, 0.3)'; // Bright green
            symbol = 'triangle';
            labelPosition = 'bottom';
        } else if (isAsk) {
            color = period === 'during' ? '#ff4444' : 'rgba(255, 68, 68, 0.3)'; // Bright red
            symbol = 'triangle';
            labelPosition = 'top';
        } else {
            color = period === 'during' ? '#ffaa00' : 'rgba(255, 170, 0, 0.3)'; // Orange (unknown)
            symbol = 'circle';
            labelPosition = 'top';
        }

        // Calculate offset for overlapping times
        let eventTime = new Date(event.time);
        const timeKey = Math.floor(eventTime.getTime() / 10); // Group by 10ms

        if (timeOffsets.has(timeKey)) {
            const offset = timeOffsets.get(timeKey);
            eventTime = new Date(eventTime.getTime() + offset * 10); // Add 10ms per collision
            timeOffsets.set(timeKey, offset + 1);
        } else {
            timeOffsets.set(timeKey, 1);
        }

        // Calculate size based on USD value (logarithmic scale for better visualization)
        // All periods use the same size scale for consistency
        const baseSize = 12;
        const minSize = 8;
        const maxSize = 24;

        let size;
        if (maxUsd === minUsd) {
            // All values are the same
            size = baseSize;
        } else {
            // Linear scaling for proportional size difference
            const normalizedValue = (event.usd_value - minUsd) / (maxUsd - minUsd);
            size = minSize + (maxSize - minSize) * normalizedValue;
        }

        const usdValue = event.usd_value / 1000;
        const label = usdValue >= 1 ? `${usdValue.toFixed(1)}K` : '';

        return {
            time: eventTime,
            price: event.price,
            color: color,
            symbol: symbol,
            size: size,
            label: label,
            labelPosition: labelPosition,
            originalEvent: event,
            period: period
        };
    });
}

// Format tooltip
function formatTooltip(params, intervalData) {
    if (!params || params.length === 0) return '';

    let html = '';

    // Find the time from the first param
    const time = new Date(params[0].value[0]);
    const timeStr = time.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        fractionalSecondDigits: 3
    });

    html += `<strong>${timeStr}</strong><br/>`;

    // Show price
    params.forEach(param => {
        if (param.seriesName === 'Price' && param.value && param.value[1] != null) {
            const price = param.value[1];
            const changeFromStart = ((price - intervalData.start_price) / intervalData.start_price) * 100;
            const changeColor = changeFromStart >= 0 ? '#00ff88' : '#ff4444';
            html += `Price: $${price.toFixed(6)}<br/>`;
            html += `<span style="color: ${changeColor}">Change: ${changeFromStart.toFixed(3)}%</span><br/>`;
        }
    });

    // Find nearby whale events
    const timeWindow = 1000; // 1 second
    const allEvents = [
        ...filterWhaleEventsByUsd(intervalData.whale_events_before || []),
        ...filterWhaleEventsByUsd(intervalData.whale_events || []),
        ...filterWhaleEventsByUsd(intervalData.whale_events_after || [])
    ];

    const nearbyEvents = allEvents.filter(event => {
        const eventTime = new Date(event.time);
        return Math.abs(eventTime - time) <= timeWindow;
    });

    if (nearbyEvents.length > 0) {
        const bidEvents = nearbyEvents.filter(e => e.side === 'bid' || e.event_type.includes('bid'));
        const askEvents = nearbyEvents.filter(e => e.side === 'ask' || e.event_type.includes('ask'));
        const marketEvents = nearbyEvents.filter(e => e.event_type.includes('market'));

        const bidVolume = bidEvents.reduce((sum, e) => sum + (e.usd_value || 0), 0);
        const askVolume = askEvents.reduce((sum, e) => sum + (e.usd_value || 0), 0);
        const marketVolume = marketEvents.reduce((sum, e) => sum + (e.usd_value || 0), 0);

        html += '<br/><strong>Whale Events:</strong><br/>';
        if (bidEvents.length > 0) html += `<span style="color: #00ff88">Bids: ${bidEvents.length} ($${formatNumber(bidVolume)})</span><br/>`;
        if (askEvents.length > 0) html += `<span style="color: #ff4444">Asks: ${askEvents.length} ($${formatNumber(askVolume)})</span><br/>`;
        if (marketEvents.length > 0) html += `<span style="color: #ffaa00">Market: ${marketEvents.length} ($${formatNumber(marketVolume)})</span><br/>`;
    }

    return html;
}

// Load whale events into the events panel
function loadWhaleEvents(data) {
    // Calculate statistics for all three periods (apply USD filter)
    const beforeEvents = filterWhaleEventsByUsd(data.whale_events_before || []);
    const duringEvents = filterWhaleEventsByUsd(data.whale_events || []);
    const afterEvents = filterWhaleEventsByUsd(data.whale_events_after || []);

    const beforeCount = beforeEvents.length;
    const duringCount = duringEvents.length;
    const afterCount = afterEvents.length;

    const beforeVolume = beforeEvents.reduce((sum, e) => sum + (e.usd_value || 0), 0);
    const duringVolume = duringEvents.reduce((sum, e) => sum + (e.usd_value || 0), 0);
    const afterVolume = afterEvents.reduce((sum, e) => sum + (e.usd_value || 0), 0);

    const totalEvents = beforeCount + duringCount + afterCount;
    const totalVolume = beforeVolume + duringVolume + afterVolume;

    // Find biggest whale events
    const allEvents = [...beforeEvents, ...duringEvents, ...afterEvents];
    const biggestWhale = allEvents.length > 0 ?
        allEvents.reduce((max, e) => e.usd_value > max.usd_value ? e : max, allEvents[0]) : null;

    const biggestDuringWhale = duringEvents.length > 0 ?
        duringEvents.reduce((max, e) => e.usd_value > max.usd_value ? e : max, duringEvents[0]) : null;

    // Update event statistics with comparison
    const avgCount = (beforeCount + afterCount) / 2;
    const countChange = avgCount > 0 ? ((duringCount - avgCount) / avgCount * 100) : 0;
    const changeSign = countChange >= 0 ? '+' : '';
    const changeColor = countChange >= 0 ? '#00ff88' : '#ff4444';

    document.getElementById('event-stat-total').innerHTML = `
        <span style="color: #b0b0b0; font-size: 0.8rem;">${beforeCount}</span>
        <span style="color: white; font-weight: 600;"> ${duringCount} </span>
        <span style="color: #b0b0b0; font-size: 0.8rem;">${afterCount}</span>
        <span style="color: ${changeColor}; font-size: 0.75rem; margin-left: 4px;">${changeSign}${countChange.toFixed(0)}%</span>
    `;

    document.getElementById('event-stat-volume').textContent = `$${formatNumber(totalVolume)}`;

    // Update biggest whale stats
    if (biggestWhale) {
        const whaleColor = biggestWhale.side === 'bid' ? '#00ff88' : biggestWhale.side === 'ask' ? '#ff4444' : '#ffaa00';
        document.getElementById('event-stat-biggest').innerHTML = `
            <span style="color: ${whaleColor}; font-weight: 600;">$${formatNumber(biggestWhale.usd_value)}</span>
            <div style="font-size: 0.7rem; color: #b0b0b0; margin-top: 2px;">${biggestWhale.event_type.replace('_', ' ')}</div>
        `;
    } else {
        document.getElementById('event-stat-biggest').textContent = '$0';
    }

    if (biggestDuringWhale) {
        const whaleColor = biggestDuringWhale.side === 'bid' ? '#00ff88' : biggestDuringWhale.side === 'ask' ? '#ff4444' : '#ffaa00';
        document.getElementById('event-stat-biggest-during').innerHTML = `
            <span style="color: ${whaleColor}; font-weight: 600;">$${formatNumber(biggestDuringWhale.usd_value)}</span>
            <div style="font-size: 0.7rem; color: #b0b0b0; margin-top: 2px;">${biggestDuringWhale.event_type.replace('_', ' ')}</div>
        `;
    } else {
        document.getElementById('event-stat-biggest-during').textContent = '$0';
    }

    // Generate analytical insights
    generateInsights(data, beforeEvents, duringEvents, afterEvents, beforeVolume, duringVolume, afterVolume);
}

// Generate analytical insights from whale activity patterns
function generateInsights(data, beforeEvents, duringEvents, afterEvents, beforeVolume, duringVolume, afterVolume) {
    const insights = [];
    const insightsPanel = document.getElementById('insights-panel');
    const insightsContent = document.getElementById('insights-content');

    if (duringEvents.length === 0) {
        insightsPanel.style.display = 'none';
        return;
    }

    // Insight 1: Activity density change
    const avgCount = (beforeEvents.length + afterEvents.length) / 2;
    const countChange = avgCount > 0 ? ((duringEvents.length - avgCount) / avgCount * 100) : 0;

    if (Math.abs(countChange) > 20) {
        const type = countChange > 0 ? 'positive' : 'negative';
        const verb = countChange > 0 ? 'increased' : 'decreased';
        insights.push({
            type: type,
            icon: countChange > 0 ? '📈' : '📉',
            text: `Activity ${verb} by ${Math.abs(countChange).toFixed(0)}% during spike`
        });
    }

    // Insight 2: Timing - find first significant whale event before spike
    if (beforeEvents.length > 0) {
        const startTime = new Date(data.start_time).getTime();
        const firstSignificantEvent = beforeEvents
            .filter(e => e.usd_value > 1000)
            .sort((a, b) => new Date(b.time) - new Date(a.time))[0];

        if (firstSignificantEvent) {
            const eventTime = new Date(firstSignificantEvent.time).getTime();
            const timeDiff = (startTime - eventTime) / 1000;

            if (timeDiff < 10) {
                insights.push({
                    type: 'warning',
                    icon: '⏱️',
                    text: `Large ${firstSignificantEvent.side} order ${timeDiff.toFixed(1)}s before spike`,
                    value: `$${formatNumber(firstSignificantEvent.usd_value)}`
                });
            }
        }
    }

    // Insight 3: Volume concentration
    const totalVolume = beforeVolume + duringVolume + afterVolume;
    const duringPct = totalVolume > 0 ? (duringVolume / totalVolume * 100) : 0;

    if (duringPct > 40) {
        insights.push({
            type: 'positive',
            icon: '💰',
            text: `${duringPct.toFixed(0)}% of total volume occurred during spike`
        });
    }

    // Insight 4: Bid vs Ask dominance
    const duringBids = duringEvents.filter(e => e.side === 'bid' || e.event_type.includes('bid'));
    const duringAsks = duringEvents.filter(e => e.side === 'ask' || e.event_type.includes('ask'));
    const bidVolume = duringBids.reduce((sum, e) => sum + e.usd_value, 0);
    const askVolume = duringAsks.reduce((sum, e) => sum + e.usd_value, 0);

    const priceChange = data.change_pct;
    if (bidVolume > askVolume * 1.5 && priceChange > 0) {
        const ratio = (bidVolume / askVolume).toFixed(1);
        insights.push({
            type: 'positive',
            icon: '🐂',
            text: `Strong buying pressure (${ratio}x more bids) aligned with price rise`
        });
    } else if (askVolume > bidVolume * 1.5 && priceChange < 0) {
        const ratio = (askVolume / bidVolume).toFixed(1);
        insights.push({
            type: 'negative',
            icon: '🐻',
            text: `Strong selling pressure (${ratio}x more asks) aligned with price drop`
        });
    } else if (bidVolume > askVolume * 1.5 && priceChange < 0) {
        insights.push({
            type: 'warning',
            icon: '⚠️',
            text: 'Buying pressure during price drop - possible support level'
        });
    } else if (askVolume > bidVolume * 1.5 && priceChange > 0) {
        insights.push({
            type: 'warning',
            icon: '⚠️',
            text: 'Selling pressure during price rise - possible resistance level'
        });
    }

    // Display insights
    if (insights.length > 0) {
        insightsContent.innerHTML = insights.map(insight => `
            <div class="insight-item ${insight.type}">
                <span class="insight-icon">${insight.icon}</span>
                <span class="insight-text">${insight.text}</span>
                ${insight.value ? `<span class="insight-value">${insight.value}</span>` : ''}
            </div>
        `).join('');
        insightsPanel.style.display = 'block';
    } else {
        insightsPanel.style.display = 'none';
    }
}

// Load events into a specific list
function loadEventsList(section, events) {
    const listElement = document.getElementById(`events-${section}-list`);
    listElement.innerHTML = '';

    if (!events || events.length === 0) {
        listElement.innerHTML = '<p style="color: #707070; text-align: center; padding: 2rem;">No events</p>';
        return;
    }

    events.forEach(event => {
        const eventItem = createEventItem(event);
        listElement.appendChild(eventItem);
    });
}

// Create event item HTML element
function createEventItem(event) {
    const div = document.createElement('div');
    div.className = 'event-item ' + event.side;

    const time = new Date(event.time).toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        fractionalSecondDigits: 3
    });

    div.innerHTML = `
        <div class="event-header">
            <span class="event-type ${event.side}">${event.event_type.replace('_', ' ')}</span>
            <span class="event-time">${time}</span>
        </div>
        <div class="event-details">
            <div class="event-detail">
                <span class="event-detail-label">Price</span>
                <span class="event-detail-value">$${event.price.toFixed(6)}</span>
            </div>
            <div class="event-detail">
                <span class="event-detail-label">Volume</span>
                <span class="event-detail-value">${formatNumber(event.volume)}</span>
            </div>
            <div class="event-detail">
                <span class="event-detail-label">USD Value</span>
                <span class="event-detail-value">$${formatNumber(event.usd_value)}</span>
            </div>
            <div class="event-detail">
                <span class="event-detail-label">Distance</span>
                <span class="event-detail-value">${event.distance_from_mid_pct.toFixed(3)}%</span>
            </div>
        </div>
    `;

    // Add click handler to show modal
    div.addEventListener('click', () => {
        showEventDetailsModal(new Date(event.time), currentInterval);
    });

    return div;
}

// Show single event details modal
function showSingleEventModal(event, period) {
    const modal = document.getElementById('event-details-modal');
    const modalTitle = document.getElementById('modal-title');
    const modalBody = document.getElementById('modal-body');

    // Determine period info
    let periodBadge = '';
    let periodColor = '';

    if (period === 'before') {
        periodBadge = '⬅ BEFORE';
        periodColor = '#2962ff';
    } else if (period === 'during') {
        periodBadge = '◆ DURING';
        periodColor = '#ffaa00';
    } else {
        periodBadge = '➡ AFTER';
        periodColor = '#ff6b6b';
    }

    const time = new Date(event.time).toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    });

    const sideColor = event.side === 'bid' ? '#00ff88' : event.side === 'ask' ? '#ff4444' : '#ffaa00';
    const sideIcon = event.side === 'bid' ? '▲' : event.side === 'ask' ? '▼' : '●';

    // Check if this is a market order
    const isMarketOrder = event.event_type === 'market_buy' || event.event_type === 'market_sell';

    // Determine title color based on period
    const titleIcon = event.period === 'during' ? '◆' : (event.period === 'before' ? '⬅' : '➡');

    modalTitle.innerHTML = `${titleIcon} Whale Event Details <span style="color: ${periodColor}; margin-left: 8px; font-size: 0.9rem; text-transform: uppercase; font-weight: 600;">${periodBadge}</span>`;

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
                ${isMarketOrder && event.distance_from_mid_pct !== undefined ? `
                <div>
                    <div style="color: #808080; font-size: 0.75rem; text-transform: uppercase; margin-bottom: 0.5rem;">Distance from Mid</div>
                    <div style="color: ${event.distance_from_mid_pct >= 0 ? '#00ff88' : '#ff4444'}; font-size: 1.1rem; font-weight: 600;">${event.distance_from_mid_pct >= 0 ? '+' : ''}${event.distance_from_mid_pct.toFixed(3)}%</div>
                </div>
                ` : ''}
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

// Show event details modal (multiple events at a time)
function showEventDetailsModal(clickedTime, intervalData) {
    const modal = document.getElementById('event-details-modal');
    const modalTitle = document.getElementById('modal-title');
    const modalBody = document.getElementById('modal-body');

    // Get all events from all periods (apply USD filter)
    const allEvents = [
        ...filterWhaleEventsByUsd(intervalData.whale_events_before || []).map(e => ({ ...e, period: 'before' })),
        ...filterWhaleEventsByUsd(intervalData.whale_events || []).map(e => ({ ...e, period: 'during' })),
        ...filterWhaleEventsByUsd(intervalData.whale_events_after || []).map(e => ({ ...e, period: 'after' }))
    ];

    // Find events within ±2 seconds of clicked time
    const timeWindow = 2000; // 2 seconds
    const eventsAtTime = allEvents.filter(event => {
        const eventTime = new Date(event.time);
        return Math.abs(eventTime - clickedTime) <= timeWindow;
    });

    // Sort events by time
    eventsAtTime.sort((a, b) => new Date(a.time) - new Date(b.time));

    // Update modal title with time
    const timeStr = clickedTime.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        fractionalSecondDigits: 3
    });

    // Determine which period
    const startTime = new Date(intervalData.start_time).getTime();
    const endTime = new Date(intervalData.end_time).getTime();
    const clickedTimeMs = clickedTime.getTime();

    let periodLabel = '';
    let periodColor = '';
    if (clickedTimeMs < startTime) {
        periodLabel = '⬅ BEFORE';
        periodColor = '#2962ff';
    } else if (clickedTimeMs >= startTime && clickedTimeMs <= endTime) {
        periodLabel = '◆ DURING';
        periodColor = '#ffaa00';
    } else {
        periodLabel = '➡ AFTER';
        periodColor = '#ff6b6b';
    }

    modalTitle.innerHTML = `Whale Events at ${timeStr} <span style="color: ${periodColor}; margin-left: 8px;">${periodLabel}</span>`;

    // Build modal content
    if (eventsAtTime.length === 0) {
        modalBody.innerHTML = '<p style="text-align: center; color: #888; padding: 2rem;">No whale events found within ±2s of this time</p>';
    } else {
        // Calculate summary statistics
        const bidEvents = eventsAtTime.filter(e => e.side === 'bid' || e.event_type.includes('bid'));
        const askEvents = eventsAtTime.filter(e => e.side === 'ask' || e.event_type.includes('ask'));
        const tradeEvents = eventsAtTime.filter(e => e.event_type.includes('market'));

        const bidVolume = bidEvents.reduce((sum, e) => sum + e.usd_value, 0);
        const askVolume = askEvents.reduce((sum, e) => sum + e.usd_value, 0);
        const tradeVolume = tradeEvents.reduce((sum, e) => sum + e.usd_value, 0);
        const totalVolume = bidVolume + askVolume + tradeVolume;

        // Calculate net pressure
        let pressureText = 'Neutral';
        if (bidVolume > askVolume * 1.2) {
            const ratio = (bidVolume / askVolume).toFixed(1);
            pressureText = `<span style="color: #00ff88;">${ratio}x more bids</span>`;
        } else if (askVolume > bidVolume * 1.2) {
            const ratio = (askVolume / bidVolume).toFixed(1);
            pressureText = `<span style="color: #ff4444;">${ratio}x more asks</span>`;
        }

        modalBody.innerHTML = `
            <div class="modal-summary">
                <div class="modal-summary-item">
                    <div class="modal-summary-label">Total Events</div>
                    <div class="modal-summary-value">${eventsAtTime.length}</div>
                </div>
                <div class="modal-summary-item">
                    <div class="modal-summary-label">Total Volume</div>
                    <div class="modal-summary-value">$${formatNumber(totalVolume)}</div>
                </div>
                <div class="modal-summary-item">
                    <div class="modal-summary-label">Bids</div>
                    <div class="modal-summary-value" style="color: #00ff88;">
                        ${bidEvents.length}
                        <div style="font-size: 0.75rem; color: #00ff88; margin-top: 2px;">$${formatNumber(bidVolume)}</div>
                    </div>
                </div>
                <div class="modal-summary-item">
                    <div class="modal-summary-label">Asks</div>
                    <div class="modal-summary-value" style="color: #ff4444;">
                        ${askEvents.length}
                        <div style="font-size: 0.75rem; color: #ff4444; margin-top: 2px;">$${formatNumber(askVolume)}</div>
                    </div>
                </div>
                <div class="modal-summary-item">
                    <div class="modal-summary-label">Trades</div>
                    <div class="modal-summary-value" style="color: #ffaa00;">
                        ${tradeEvents.length}
                        <div style="font-size: 0.75rem; color: #ffaa00; margin-top: 2px;">$${formatNumber(tradeVolume)}</div>
                    </div>
                </div>
                <div class="modal-summary-item">
                    <div class="modal-summary-label">Net Pressure</div>
                    <div class="modal-summary-value">${pressureText}</div>
                </div>
            </div>
            <div class="modal-events-list">
                ${eventsAtTime.map(event => createModalEventItem(event, startTime, endTime)).join('')}
            </div>
        `;
    }

    modal.style.display = 'flex';

    // Close on background click
    modal.onclick = (e) => {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    };
}

// Create modal event item
function createModalEventItem(event, intervalStart, intervalEnd) {
    const eventTime = new Date(event.time).getTime();
    let periodBadge = '';
    let periodColor = '';

    if (event.period === 'before') {
        periodBadge = '⬅ BEFORE';
        periodColor = '#2962ff';
    } else if (event.period === 'during') {
        periodBadge = '◆ DURING';
        periodColor = '#ffaa00';
    } else {
        periodBadge = '➡ AFTER';
        periodColor = '#ff6b6b';
    }

    const time = new Date(event.time).toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        fractionalSecondDigits: 3
    });

    // Use same color logic as chart markers
    let eventColor;
    const isMarketBuy = event.event_type === 'market_buy';
    const isMarketSell = event.event_type === 'market_sell';
    const isIncrease = event.event_type === 'increase';
    const isDecrease = event.event_type === 'decrease';
    const isBid = event.side === 'bid';
    const isAsk = event.side === 'ask';

    if (isMarketBuy) {
        eventColor = '#00c2ff'; // Bright cyan
    } else if (isMarketSell) {
        eventColor = '#ff00ff'; // Bright magenta
    } else if (isIncrease && isBid) {
        eventColor = '#88cc88'; // Muted green (potential support)
    } else if (isIncrease && isAsk) {
        eventColor = '#cc8888'; // Muted red (potential resistance)
    } else if (isDecrease && isBid) {
        eventColor = '#cc8888'; // Muted red (support weakening)
    } else if (isDecrease && isAsk) {
        eventColor = '#88cc88'; // Muted green (resistance weakening)
    } else if (isBid) {
        eventColor = '#00ff88'; // Bright green (new bid)
    } else if (isAsk) {
        eventColor = '#ff4444'; // Bright red (new ask)
    } else {
        eventColor = '#ffaa00'; // Orange (unknown)
    }

    return `
        <div class="modal-event-item ${event.side}">
            <div class="modal-event-header">
                <span class="modal-event-type" style="background-color: ${eventColor};">${event.event_type.replace('_', ' ')}</span>
                <span class="modal-event-period" style="color: ${periodColor};">${periodBadge}</span>
                <span class="modal-event-time">${time}</span>
            </div>
            <div class="modal-event-details">
                <div class="modal-event-detail">
                    <span class="modal-event-detail-label">Price</span>
                    <span class="modal-event-detail-value">$${event.price.toFixed(6)}</span>
                </div>
                <div class="modal-event-detail">
                    <span class="modal-event-detail-label">Volume</span>
                    <span class="modal-event-detail-value">${formatNumber(event.volume)}</span>
                </div>
                <div class="modal-event-detail">
                    <span class="modal-event-detail-label">USD Value</span>
                    <span class="modal-event-detail-value">$${formatNumber(event.usd_value)}</span>
                </div>
                <div class="modal-event-detail">
                    <span class="modal-event-detail-label">Distance from Mid</span>
                    <span class="modal-event-detail-value">${event.distance_from_mid_pct.toFixed(3)}%</span>
                </div>
            </div>
        </div>
    `;
}

// Export current interval as JSON
function exportCurrentInterval() {
    if (!currentInterval) {
        alert('No interval data loaded');
        return;
    }

    // Create filename with symbol and timestamp
    const symbol = currentInterval.symbol || 'UNKNOWN';
    const startTime = new Date(currentInterval.start_time);
    const filename = `interval_${symbol}_rank${currentInterval.rank}_${startTime.toISOString().replace(/[:.]/g, '-')}.json`;

    // Create JSON blob
    const jsonData = JSON.stringify(currentInterval, null, 2);
    const blob = new Blob([jsonData], { type: 'application/json' });

    // Create download link
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();

    // Cleanup
    setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }, 100);

    console.log('Exported interval:', filename);
}

// Setup event listeners
function setupEventListeners() {
    // New Analysis button
    document.getElementById('new-analysis-btn').addEventListener('click', () => {
        document.getElementById('new-analysis-modal').style.display = 'flex';
    });

    // Zero state new analysis button
    const zeroStateBtn = document.getElementById('zero-state-new-analysis');
    if (zeroStateBtn) {
        zeroStateBtn.addEventListener('click', () => {
            document.getElementById('new-analysis-modal').style.display = 'flex';
        });
    }

    // Analysis form submit
    document.getElementById('analysis-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        await runAnalysis();
    });

    // File selector change
    document.getElementById('file-selector').addEventListener('change', (e) => {
        const deleteBtn = document.getElementById('delete-btn');
        if (e.target.value) {
            deleteBtn.style.display = 'inline-block';
        } else {
            deleteBtn.style.display = 'none';
        }
        loadDataFile(e.target.value);
    });

    // Delete button
    document.getElementById('delete-btn').addEventListener('click', () => {
        const selector = document.getElementById('file-selector');
        const analysisId = selector.value;
        if (analysisId) {
            showDeleteConfirmation(analysisId);
        }
    });

    // Confirm delete button
    document.getElementById('confirm-delete-btn').addEventListener('click', async () => {
        const selector = document.getElementById('file-selector');
        const analysisId = selector.value;
        if (analysisId) {
            await deleteAnalysis(analysisId);
        }
    });

    // Interval selector change
    document.getElementById('interval-selector').addEventListener('change', (e) => {
        const index = parseInt(e.target.value);
        if (currentData && currentData[index]) {
            loadInterval(currentData[index]);
        }
    });

    // Refresh button
    document.getElementById('refresh-btn').addEventListener('click', async () => {
        await loadFileList();
    });

    // Export interval button
    document.getElementById('export-interval-btn').addEventListener('click', () => {
        exportCurrentInterval();
    });

    // Fullscreen toggle
    document.getElementById('fullscreen-btn').addEventListener('click', () => {
        toggleFullscreen();
    });

    // Event search
    document.getElementById('event-search').addEventListener('input', (e) => {
        filterEvents(e.target.value, document.getElementById('event-type-filter').value);
    });

    // Event type filter
    document.getElementById('event-type-filter').addEventListener('change', (e) => {
        filterEvents(document.getElementById('event-search').value, e.target.value);
    });

    // USD filter - apply on Enter key
    document.getElementById('min-usd-filter').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            minUsdFilter = parseFloat(e.target.value) || 0;
            // Reload the current interval with new filter
            if (currentInterval) {
                loadInterval(currentInterval);
            }
        }
    });

    // Also apply on blur (when clicking outside)
    document.getElementById('min-usd-filter').addEventListener('blur', (e) => {
        const newValue = parseFloat(e.target.value) || 0;
        if (newValue !== minUsdFilter) {
            minUsdFilter = newValue;
            // Reload the current interval with new filter
            if (currentInterval) {
                loadInterval(currentInterval);
            }
        }
    });

    // Modal close button
    const closeBtn = document.querySelector('.modal-close');
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            document.getElementById('event-details-modal').style.display = 'none';
        });
    }


    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // ESC key: close modal first, then exit fullscreen
        if (e.key === 'Escape') {
            // First check if any modal is open
            const modal = document.getElementById('event-details-modal');
            const isModalOpen = modal && modal.style.display === 'flex';

            if (isModalOpen) {
                // Close the modal
                modal.style.display = 'none';
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

// Filter whale events by USD value
function filterWhaleEventsByUsd(events) {
    if (minUsdFilter <= 0) {
        return events;
    }
    return events.filter(event => event.usd_value >= minUsdFilter);
}

// Filter events based on search and type
function filterEvents(searchTerm, eventType) {
    const allEvents = document.querySelectorAll('.event-item');

    allEvents.forEach(item => {
        const typeElement = item.querySelector('.event-type');
        const typeText = typeElement.textContent.toLowerCase();
        const matchesSearch = !searchTerm || typeText.includes(searchTerm.toLowerCase());
        const matchesType = !eventType || typeText.includes(eventType.replace('_', ' '));

        item.style.display = (matchesSearch && matchesType) ? 'block' : 'none';
    });
}

// Show/hide loading indicator
function showLoading(show) {
    const loading = document.getElementById('loading');
    const zeroState = document.getElementById('zero-state');

    if (loading) {
        loading.style.display = show ? 'flex' : 'none';
    }

    // Hide zero state when loading
    if (zeroState && show) {
        zeroState.style.display = 'none';
    }
}

function showZeroState(show) {
    const zeroState = document.getElementById('zero-state');
    const loading = document.getElementById('loading');

    if (zeroState) {
        zeroState.style.display = show ? 'block' : 'none';
    }

    // Hide loading when showing zero state
    if (loading && show) {
        loading.style.display = 'none';
    }
}

// Show error message
function showError(message) {
    alert(message);
}

// Toggle fullscreen mode for chart
function toggleFullscreen() {
    const wrapper = document.querySelector('.chart-wrapper');
    const container = document.getElementById('chart-container');
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

// Format number with K/M suffixes
function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(2) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(2) + 'K';
    } else {
        return num.toFixed(2);
    }
}

// Run new analysis
async function runAnalysis() {
    const form = document.getElementById('analysis-form');
    const statusDiv = document.getElementById('analysis-status');
    const statusMsg = document.getElementById('status-message');

    // Get form values
    const params = {
        symbol: document.getElementById('symbol-input').value,
        lookback: document.getElementById('lookback-input').value,
        interval: document.getElementById('interval-input').value,
        top: parseInt(document.getElementById('top-input').value),
        min_change: parseFloat(document.getElementById('min-change-input').value)
    };

    // Show status
    form.style.display = 'none';
    statusDiv.style.display = 'flex';
    statusMsg.textContent = `Running analysis for ${params.symbol}...`;

    try {
        const response = await fetch('/api/run-analysis', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(params)
        });

        const result = await response.json();

        // Log full response for debugging
        console.log('Analysis response:', result);

        if (result.error) {
            // Log detailed error information
            console.error('Analysis error details:', {
                error: result.error,
                stdout: result.stdout,
                stderr: result.stderr,
                hint: result.hint
            });

            // Show detailed error message
            let errorMsg = result.error;
            if (result.stderr) {
                errorMsg += `\n\nScript error output:\n${result.stderr}`;
            }
            if (result.hint) {
                errorMsg += `\n\nHint: ${result.hint}`;
            }

            throw new Error(errorMsg);
        }

        // Success - reload file list and select new file
        statusMsg.textContent = 'Analysis complete! Loading results...';

        await loadFileList();

        // Select the new analysis by MongoDB ID
        const selector = document.getElementById('file-selector');
        if (result.id) {
            const option = Array.from(selector.options).find(opt => opt.value === result.id);
            if (option) {
                selector.value = result.id;
                await loadDataFile(result.id);
            }
        }

        // Close modal
        setTimeout(() => {
            document.getElementById('new-analysis-modal').style.display = 'none';
            form.style.display = 'block';
            statusDiv.style.display = 'none';
        }, 1000);

    } catch (error) {
        console.error('Analysis error:', error);

        // Show error message (truncate if too long for display)
        let displayMsg = error.message;
        if (displayMsg.length > 200) {
            displayMsg = displayMsg.substring(0, 200) + '... (see console for full error)';
        }

        statusMsg.textContent = `Error: ${displayMsg}`;
        statusMsg.style.color = 'var(--red)';

        // Keep error visible longer (5 seconds instead of 3)
        setTimeout(() => {
            form.style.display = 'block';
            statusDiv.style.display = 'none';
            statusMsg.style.color = 'var(--green)';
        }, 5000);
    }
}

// Setup filter checkbox listeners
function setupFilterListeners() {
    // Price line toggle
    document.getElementById('filter-price').addEventListener('change', (e) => {
        filters.price = e.target.checked;
        updateChartFilters();
    });

    // Market Buy toggle
    document.getElementById('filter-market-buy').addEventListener('change', (e) => {
        filters.marketBuy = e.target.checked;
        updateChartFilters();
    });

    // Market Sell toggle
    document.getElementById('filter-market-sell').addEventListener('change', (e) => {
        filters.marketSell = e.target.checked;
        updateChartFilters();
    });

    // New Bid toggle
    document.getElementById('filter-new-bid').addEventListener('change', (e) => {
        filters.newBid = e.target.checked;
        updateChartFilters();
    });

    // New Ask toggle
    document.getElementById('filter-new-ask').addEventListener('change', (e) => {
        filters.newAsk = e.target.checked;
        updateChartFilters();
    });

    // Bid Increase toggle
    document.getElementById('filter-bid-increase').addEventListener('change', (e) => {
        filters.bidIncrease = e.target.checked;
        updateChartFilters();
    });

    // Ask Increase toggle
    document.getElementById('filter-ask-increase').addEventListener('change', (e) => {
        filters.askIncrease = e.target.checked;
        updateChartFilters();
    });
}

// Update chart based on filter state
function updateChartFilters() {
    if (!chart || !currentInterval) return;

    // Reload the data with current filters applied
    loadPriceData(currentInterval);
}

// Show delete confirmation modal
function showDeleteConfirmation(analysisId) {
    document.getElementById('delete-modal').style.display = 'flex';
}

// Delete analysis
async function deleteAnalysis(analysisId) {
    const confirmBtn = document.getElementById('confirm-delete-btn');
    const originalText = confirmBtn.textContent;

    try {
        // Show loading state
        confirmBtn.textContent = 'Deleting...';
        confirmBtn.disabled = true;

        const response = await fetch(`/api/delete/${analysisId}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (response.ok && result.success) {
            // Close modal
            document.getElementById('delete-modal').style.display = 'none';

            // Clear current data
            currentData = null;
            currentInterval = null;

            // Hide delete button
            document.getElementById('delete-btn').style.display = 'none';

            // Clear chart
            if (chart) {
                chart.clear();
            }

            // Reset file selector
            const selector = document.getElementById('file-selector');
            selector.value = '';

            // Show zero state
            const zeroState = document.getElementById('zero-state');
            if (zeroState) {
                zeroState.style.display = 'flex';
            }

            // Hide analysis info
            const analysisInfo = document.getElementById('analysis-info');
            if (analysisInfo) {
                analysisInfo.style.display = 'none';
            }

            // Hide interval selector
            const intervalSelector = document.getElementById('interval-selector-container');
            if (intervalSelector) {
                intervalSelector.style.display = 'none';
            }

            // Reload file list
            await loadFileList();

            // Show success message
            console.log('Analysis deleted successfully');
        } else {
            throw new Error(result.error || 'Failed to delete analysis');
        }
    } catch (error) {
        console.error('Delete error:', error);
        showError('Failed to delete analysis: ' + error.message);
    } finally {
        // Reset button state
        confirmBtn.textContent = originalText;
        confirmBtn.disabled = false;
        document.getElementById('delete-modal').style.display = 'none';
    }
}
