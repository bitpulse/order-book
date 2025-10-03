// Price Change Analyzer Dashboard - Chart and Events Handler (Apache ECharts)

let chart = null;
let currentData = null;
let currentInterval = null;
let minUsdFilter = 0; // Global filter for minimum USD value

// Initialize dashboard on load
document.addEventListener('DOMContentLoaded', async () => {
    await loadFileList();
    setupEventListeners();
});

// Load available data files
async function loadFileList() {
    try {
        const response = await fetch('/api/files');
        const data = await response.json();

        const selector = document.getElementById('file-selector');
        selector.innerHTML = '<option value="">Select a file...</option>';

        if (data.files && data.files.length > 0) {
            data.files.forEach(file => {
                const option = document.createElement('option');
                option.value = file.filename;
                const date = new Date(file.modified * 1000);
                option.textContent = `${file.filename} (${date.toLocaleString()})`;
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

// Load data from selected file
async function loadDataFile(filename) {
    if (!filename) return;

    showLoading(true);

    try {
        const response = await fetch(`/api/data/${filename}`);
        let data = await response.json();

        console.log('Loaded data:', data);

        if (data.error) {
            throw new Error(data.error);
        }

        // Handle new JSON format with metadata or old format (array)
        let intervals, metadata;
        if (Array.isArray(data)) {
            // Old format: array of intervals
            intervals = data;
            metadata = null;
        } else {
            // New format: {metadata: {...}, intervals: [...]}
            intervals = data.intervals;
            metadata = data.metadata;
        }

        console.log('Intervals:', intervals);
        console.log('Metadata:', metadata);

        currentData = intervals;

        // Extract and display analysis metadata
        updateAnalysisInfo(filename, intervals, metadata);

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
function updateAnalysisInfo(filename, intervals, metadata) {
    const infoElement = document.getElementById('analysis-info');

    if (metadata && metadata.symbol && metadata.interval_duration && metadata.threshold_pct != null) {
        document.getElementById('info-symbol').textContent = metadata.symbol;
        document.getElementById('info-interval').textContent = metadata.interval_duration;
        document.getElementById('info-threshold').textContent = `${metadata.threshold_pct.toFixed(3)}%`;
        document.getElementById('info-count').textContent = intervals.length;
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
        option.textContent = `#${interval.rank} - ${interval.change_pct.toFixed(3)}% @ ${startTime}`;
        selector.appendChild(option);
    });

    container.style.display = 'block';
}

// Load specific interval data
function loadInterval(intervalData) {
    currentInterval = intervalData;

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
}

// Update statistics display
function updateStats(data) {
    document.getElementById('stat-rank').textContent = `#${data.rank}`;

    const changeElem = document.getElementById('stat-change');
    changeElem.textContent = `${data.change_pct.toFixed(3)}%`;
    changeElem.className = 'stat-value ' + (data.change_pct > 0 ? 'positive' : 'negative');

    const startTime = new Date(data.start_time).toLocaleTimeString();
    const endTime = new Date(data.end_time).toLocaleTimeString();
    document.getElementById('stat-time').textContent = `${startTime} → ${endTime}`;

    document.getElementById('stat-price').textContent = `$${data.start_price.toFixed(6)} → $${data.end_price.toFixed(6)}`;

    // Apply USD filter to event counts
    const filteredDuring = filterWhaleEventsByUsd(data.whale_events || []);
    const filteredBefore = filterWhaleEventsByUsd(data.whale_events_before || []);
    const filteredAfter = filterWhaleEventsByUsd(data.whale_events_after || []);
    const totalEvents = filteredDuring.length + filteredBefore.length + filteredAfter.length;
    document.getElementById('stat-events').textContent = totalEvents;
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

    // Find spike point
    const startTime = new Date(data.start_time);
    const endTime = new Date(data.end_time);
    let maxChange = 0;
    let spikePoint = null;

    for (let i = 1; i < chartData.length; i++) {
        const currentTime = chartData[i].time;
        if (currentTime >= startTime && currentTime <= endTime) {
            const change = Math.abs(chartData[i].value - chartData[i - 1].value);
            if (change > maxChange) {
                maxChange = change;
                spikePoint = chartData[i];
            }
        }
    }

    // ECharts option
    const option = {
        backgroundColor: '#2d2d2d',
        animation: false,
        tooltip: {
            trigger: 'axis',
            axisPointer: {
                type: 'cross'
            },
            backgroundColor: 'rgba(45, 45, 45, 0.95)',
            borderColor: '#404040',
            textStyle: {
                color: '#e0e0e0'
            },
            formatter: function(params) {
                return formatTooltip(params, data);
            }
        },
        grid: {
            left: '3%',
            right: '4%',
            bottom: '8%',
            top: '10%',
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
                backgroundColor: '#2d2d2d',
                dataBackground: {
                    lineStyle: {
                        color: '#2962ff'
                    },
                    areaStyle: {
                        color: 'rgba(41, 98, 255, 0.2)'
                    }
                },
                selectedDataBackground: {
                    lineStyle: {
                        color: '#2962ff'
                    },
                    areaStyle: {
                        color: 'rgba(41, 98, 255, 0.5)'
                    }
                },
                fillerColor: 'rgba(41, 98, 255, 0.15)',
                borderColor: '#404040',
                handleStyle: {
                    color: '#2962ff'
                },
                textStyle: {
                    color: '#e0e0e0'
                }
            }
        ],
        xAxis: {
            type: 'time',
            boundaryGap: false,
            axisLine: {
                lineStyle: { color: '#404040' }
            },
            axisLabel: {
                color: '#e0e0e0',
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
                lineStyle: { color: '#404040' }
            },
            splitLine: {
                lineStyle: { color: '#404040' }
            },
            axisLabel: {
                color: '#e0e0e0',
                formatter: function(value) {
                    if (value == null) return '$0';
                    return '$' + value.toFixed(6);
                }
            }
        },
        series: [
            // Main price line
            {
                name: 'Price',
                type: 'line',
                data: chartData.map(d => [d.time, d.value]),
                lineStyle: {
                    color: '#2962ff',
                    width: 3
                },
                itemStyle: {
                    color: '#2962ff'
                },
                symbol: 'circle',
                symbolSize: 4,
                smooth: false,
                z: 2,
                emphasis: {
                    lineStyle: {
                        width: 4
                    }
                }
            },
            // START marker
            {
                name: 'START',
                type: 'scatter',
                data: [[startTime, data.start_price]],
                symbolSize: 15,
                itemStyle: {
                    color: '#ffaa00'
                },
                label: {
                    show: true,
                    formatter: '▼START',
                    position: 'top',
                    color: '#ffaa00',
                    fontSize: 10
                },
                z: 10
            },
            // END marker
            {
                name: 'END',
                type: 'scatter',
                data: [[endTime, data.end_price]],
                symbolSize: 15,
                itemStyle: {
                    color: '#ffaa00'
                },
                label: {
                    show: true,
                    formatter: '▲END',
                    position: 'top',
                    color: '#ffaa00',
                    fontSize: 10
                },
                z: 10
            },
            // SPIKE marker
            spikePoint ? {
                name: 'SPIKE',
                type: 'scatter',
                data: [[spikePoint.time, spikePoint.value]],
                symbolSize: 20,
                itemStyle: {
                    color: spikePoint.value > data.start_price ? '#00ff88' : '#ff4444'
                },
                label: {
                    show: true,
                    formatter: '★',
                    position: spikePoint.value > data.start_price ? 'bottom' : 'top',
                    fontSize: 16
                },
                z: 10
            } : null,
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
                    show: false
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
                    show: false
                },
                z: 5
            }
        ].filter(s => s !== null)
    };

    chart.setOption(option);

    // Add click handler for event details modal
    chart.on('click', function(params) {
        if (params.componentType === 'series' && params.seriesName.includes('Whale')) {
            const eventData = params.data[2];
            if (eventData && eventData.originalEvent) {
                showEventDetailsModal(new Date(eventData.time), currentInterval);
            }
        }
    });
}

// Prepare whale event scatter data with offset for overlapping timestamps
function prepareWhaleScatterData(events, period) {
    if (!events || events.length === 0) return [];

    // Sort by time
    const sortedEvents = [...events].sort((a, b) => new Date(a.time) - new Date(b.time));

    // Find min and max USD values for scaling
    const usdValues = sortedEvents.map(e => e.usd_value);
    const minUsd = Math.min(...usdValues);
    const maxUsd = Math.max(...usdValues);

    // Track offsets for same timestamps
    const timeOffsets = new Map();

    return sortedEvents.map(event => {
        const isBid = event.side === 'bid' || event.event_type.includes('bid');
        const isAsk = event.side === 'ask' || event.event_type.includes('ask');

        let color, symbol, labelPosition;

        if (isBid) {
            color = period === 'during' ? '#00ff88' : 'rgba(0, 255, 136, 0.3)';
            symbol = 'triangle';
            labelPosition = 'bottom';
        } else if (isAsk) {
            color = period === 'during' ? '#ff4444' : 'rgba(255, 68, 68, 0.3)';
            symbol = 'triangle';
            labelPosition = 'top';
        } else {
            color = period === 'during' ? '#ffaa00' : 'rgba(255, 170, 0, 0.3)';
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
        // Base size depends on period, then scale by USD value
        const baseSize = period === 'during' ? 12 : 6;
        const minSize = period === 'during' ? 8 : 4;
        const maxSize = period === 'during' ? 24 : 12;

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

    // Update section titles with counts
    const beforeSection = document.getElementById('events-before');
    const duringSection = document.getElementById('events-during');
    const afterSection = document.getElementById('events-after');

    // Update section titles
    beforeSection.querySelector('.section-title').innerHTML = `
        <span style="color: #2962ff;">⬅ Before Interval</span>
        <span style="color: #b0b0b0; font-size: 0.8rem; margin-left: 0.5rem;">(${beforeCount})</span>
    `;

    duringSection.querySelector('.section-title').innerHTML = `
        <span style="color: #ffaa00;">◆ During Interval</span>
        <span style="color: white; font-size: 0.8rem; margin-left: 0.5rem; font-weight: 600;">(${duringCount})</span>
    `;

    afterSection.querySelector('.section-title').innerHTML = `
        <span style="color: #ff6b6b;">➡ After Interval</span>
        <span style="color: #b0b0b0; font-size: 0.8rem; margin-left: 0.5rem;">(${afterCount})</span>
    `;

    // Load events into timeline
    loadEventsList('during', duringEvents);

    if (beforeEvents.length > 0) {
        beforeSection.style.display = 'block';
        loadEventsList('before', beforeEvents);
    } else {
        beforeSection.style.display = 'none';
    }

    if (afterEvents.length > 0) {
        afterSection.style.display = 'block';
        loadEventsList('after', afterEvents);
    } else {
        afterSection.style.display = 'none';
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

// Show event details modal
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

    const sideColor = event.side === 'bid' ? '#00ff88' : event.side === 'ask' ? '#ff4444' : '#ffaa00';

    return `
        <div class="modal-event-item ${event.side}">
            <div class="modal-event-header">
                <span class="modal-event-type" style="background-color: ${sideColor};">${event.event_type.replace('_', ' ')}</span>
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

// Setup event listeners
function setupEventListeners() {
    // File selector change
    document.getElementById('file-selector').addEventListener('change', (e) => {
        loadDataFile(e.target.value);
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
        // ESC to exit fullscreen
        if (e.key === 'Escape') {
            const wrapper = document.querySelector('.chart-wrapper');
            if (wrapper.classList.contains('fullscreen')) {
                toggleFullscreen();
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
    if (loading) {
        loading.style.display = show ? 'flex' : 'none';
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
        setTimeout(() => {
            chart.resize();
        }, 100);
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
