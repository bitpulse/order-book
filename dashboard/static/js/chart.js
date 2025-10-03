// Price Change Analyzer Dashboard - Chart and Events Handler

let chart = null;
let lineSeries = null;
let currentData = null;
let currentInterval = null;

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

            // Auto-select the first (newest) file
            selector.selectedIndex = 1;
            await loadDataFile(data.files[0].filename);
        } else {
            showError('No data files found. Please run the price change analyzer first.');
        }
    } catch (error) {
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

        currentData = intervals;

        // Extract and display analysis metadata
        updateAnalysisInfo(filename, intervals, metadata);

        // If multiple intervals, show selector
        if (intervals.length > 1) {
            showIntervalSelector(intervals);
        } else {
            document.getElementById('interval-selector-container').style.display = 'none';
        }

        // Load first interval by default
        if (intervals.length > 0) {
            loadInterval(intervals[0]);
        }

        showLoading(false);
    } catch (error) {
        showLoading(false);
        showError('Failed to load data: ' + error.message);
    }
}

// Show interval selector if multiple intervals
function showIntervalSelector(data) {
    const container = document.getElementById('interval-selector-container');
    const selector = document.getElementById('interval-selector');

    container.style.display = 'flex';
    selector.innerHTML = '';

    data.forEach((interval, index) => {
        const option = document.createElement('option');
        option.value = index;
        option.textContent = `#${interval.rank}: ${interval.change_pct.toFixed(3)}% @ ${new Date(interval.start_time).toLocaleTimeString()}`;
        selector.appendChild(option);
    });

    selector.selectedIndex = 0;
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
    loadPriceData(intervalData.price_data);

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

    const totalEvents = data.whale_events.length +
                       (data.whale_events_before?.length || 0) +
                       (data.whale_events_after?.length || 0);
    document.getElementById('stat-events').textContent = totalEvents;
}

// Initialize TradingView chart
function initializeChart() {
    const container = document.getElementById('chart-container');

    // Clear loading spinner
    const loading = document.getElementById('loading');
    if (loading) {
        loading.style.display = 'none';
    }

    chart = LightweightCharts.createChart(container, {
        width: container.clientWidth,
        height: container.clientHeight,
        layout: {
            background: { color: '#2d2d2d' },
            textColor: '#e0e0e0',
        },
        grid: {
            vertLines: { color: '#404040' },
            horzLines: { color: '#404040' },
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal,
        },
        rightPriceScale: {
            borderColor: '#404040',
        },
        timeScale: {
            borderColor: '#404040',
            timeVisible: true,
            secondsVisible: true,
        },
    });

    lineSeries = chart.addLineSeries({
        color: '#2962ff',
        lineWidth: 2,
    });

    // Create tooltip element
    const tooltip = document.createElement('div');
    tooltip.id = 'chart-tooltip';
    tooltip.style.cssText = `
        position: absolute;
        display: none;
        padding: 8px;
        box-sizing: border-box;
        font-size: 12px;
        text-align: left;
        z-index: 1000;
        top: 12px;
        left: 12px;
        pointer-events: none;
        background: rgba(45, 45, 45, 0.95);
        border: 1px solid #404040;
        border-radius: 4px;
        color: #e0e0e0;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    `;
    container.appendChild(tooltip);

    // Subscribe to crosshair move
    chart.subscribeCrosshairMove((param) => {
        if (!param.time || !param.point || !currentInterval) {
            tooltip.style.display = 'none';
            return;
        }

        const price = param.seriesData.get(lineSeries);
        if (!price) {
            tooltip.style.display = 'none';
            return;
        }

        const timeStr = new Date(param.time * 1000).toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });

        // Calculate change from start
        const changeFromStart = ((price.value - currentInterval.start_price) / currentInterval.start_price) * 100;
        const changeColor = changeFromStart >= 0 ? '#00ff88' : '#ff4444';

        // Calculate dynamic time window based on interval size
        const intervalDuration = (new Date(currentInterval.end_time) - new Date(currentInterval.start_time));
        // Use 10% of interval duration or minimum 1 second
        const timeWindow = Math.max(1000, intervalDuration * 0.1);

        // Find whale events near this time
        const currentTime = new Date(param.time * 1000);

        let nearbyEvents = [];
        if (currentInterval.whale_events) {
            nearbyEvents = currentInterval.whale_events.filter(event => {
                const eventTime = new Date(event.time);
                return Math.abs(eventTime - currentTime) <= timeWindow;
            });
        }

        // Count event types and calculate volumes
        const bidEvents = nearbyEvents.filter(e => e.side === 'bid' || e.event_type.includes('bid'));
        const askEvents = nearbyEvents.filter(e => e.side === 'ask' || e.event_type.includes('ask'));
        const marketEvents = nearbyEvents.filter(e => e.event_type.includes('market'));

        const bidVolume = bidEvents.reduce((sum, e) => sum + (e.usd_value || 0), 0);
        const askVolume = askEvents.reduce((sum, e) => sum + (e.usd_value || 0), 0);
        const marketVolume = marketEvents.reduce((sum, e) => sum + (e.usd_value || 0), 0);
        const totalVolume = bidVolume + askVolume + marketVolume;

        // Build whale events section
        let whaleSection = '';
        if (nearbyEvents.length > 0) {
            const windowSec = (timeWindow / 1000).toFixed(0);
            whaleSection = `
                <div style="margin-top: 6px; padding-top: 6px; border-top: 1px solid #404040;">
                    <div style="font-size: 11px; margin-bottom: 3px; color: #b0b0b0;">Whale Events (±${windowSec}s):</div>
                    ${bidEvents.length > 0 ? `<div style="font-size: 11px;"><span style="color: #00ff88;">▲</span> ${bidEvents.length} Bid${bidEvents.length > 1 ? 's' : ''} ($${formatNumber(bidVolume)})</div>` : ''}
                    ${askEvents.length > 0 ? `<div style="font-size: 11px;"><span style="color: #ff4444;">▼</span> ${askEvents.length} Ask${askEvents.length > 1 ? 's' : ''} ($${formatNumber(askVolume)})</div>` : ''}
                    ${marketEvents.length > 0 ? `<div style="font-size: 11px;"><span style="color: #ffaa00;">●</span> ${marketEvents.length} Trade${marketEvents.length > 1 ? 's' : ''} ($${formatNumber(marketVolume)})</div>` : ''}
                    <div style="font-size: 11px; margin-top: 2px; font-weight: 600;">Total: <span style="color: #2962ff;">$${formatNumber(totalVolume)}</span></div>
                </div>
            `;
        }

        tooltip.style.display = 'block';
        tooltip.innerHTML = `
            <div style="margin-bottom: 4px; font-weight: 600;">${timeStr}</div>
            <div>Price: <span style="color: #2962ff;">$${price.value.toFixed(6)}</span></div>
            <div>Change: <span style="color: ${changeColor};">${changeFromStart >= 0 ? '+' : ''}${changeFromStart.toFixed(3)}%</span></div>
            <div style="margin-top: 6px; padding-top: 6px; border-top: 1px solid #404040; color: #b0b0b0;">
                <div style="font-size: 11px;">Interval: ${currentInterval.start_price.toFixed(6)} → ${currentInterval.end_price.toFixed(6)}</div>
                <div style="font-size: 11px;">Total: <span style="color: ${currentInterval.change_pct >= 0 ? '#00ff88' : '#ff4444'};">${currentInterval.change_pct >= 0 ? '+' : ''}${currentInterval.change_pct.toFixed(3)}%</span></div>
            </div>
            ${whaleSection}
        `;
    });

    // Handle window resize
    window.addEventListener('resize', () => {
        chart.applyOptions({
            width: container.clientWidth,
            height: container.clientHeight
        });
    });
}

// Load price data into chart
function loadPriceData(priceData) {
    if (!lineSeries || !priceData) return;

    // Convert price data to chart format
    const chartData = priceData.map(point => ({
        time: new Date(point.time).getTime() / 1000, // Convert to Unix timestamp
        value: point.mid_price
    }));

    // Sort by time
    chartData.sort((a, b) => a.time - b.time);

    lineSeries.setData(chartData);

    // Get interval boundaries first
    const startTime = currentInterval ? new Date(currentInterval.start_time).getTime() / 1000 : 0;
    const endTime = currentInterval ? new Date(currentInterval.end_time).getTime() / 1000 : 0;

    // Find the spike point ONLY within the interval (between START and END)
    let maxChangeIdx = -1;
    let maxChange = 0;
    for (let i = 1; i < chartData.length; i++) {
        const currentTime = chartData[i].time;

        // Only consider points within the analyzed interval
        if (currentTime >= startTime && currentTime <= endTime) {
            const change = Math.abs(chartData[i].value - chartData[i - 1].value);
            if (change > maxChange) {
                maxChange = change;
                maxChangeIdx = i;
            }
        }
    }

    // Create markers for whale events and spike
    const allMarkers = [];

    // Add whale event markers
    if (currentInterval && currentInterval.whale_events) {
        const whaleMarkers = createWhaleMarkers(currentInterval.whale_events);
        allMarkers.push(...whaleMarkers);
    }

    // Add interval boundary markers
    if (currentInterval) {

        // Start of interval marker
        allMarkers.push({
            time: startTime,
            position: 'aboveBar',
            color: '#ffaa00',
            shape: 'square',
            text: '▼START',
            size: 2
        });

        // End of interval marker
        allMarkers.push({
            time: endTime,
            position: 'aboveBar',
            color: '#ffaa00',
            shape: 'square',
            text: '▲END',
            size: 2
        });
    }

    // Add spike marker
    if (maxChangeIdx > 0) {
        const spikeTime = chartData[maxChangeIdx].time;
        const spikeValue = chartData[maxChangeIdx].value;
        const prevValue = chartData[maxChangeIdx - 1].value;
        const isUp = spikeValue > prevValue;

        allMarkers.push({
            time: spikeTime,
            position: isUp ? 'belowBar' : 'aboveBar',
            color: isUp ? '#00ff88' : '#ff4444',
            shape: 'circle',
            text: '★ SPIKE',
            size: 3
        });
    }

    lineSeries.setMarkers(allMarkers);

    // Fit content
    chart.timeScale().fitContent();
}

// Create markers for whale events
function createWhaleMarkers(events) {
    if (!events || events.length === 0) return [];

    const markers = events.map(event => {
        const isBid = event.side === 'bid' || event.event_type.includes('bid');
        const isAsk = event.side === 'ask' || event.event_type.includes('ask');
        const isMarket = event.event_type.includes('market');

        let color = '#ffaa00'; // Default yellow
        let position = 'aboveBar';
        let shape = 'circle';

        if (isBid) {
            color = '#00ff88'; // Green for bids
            position = 'belowBar';
            shape = 'arrowUp';
        } else if (isAsk) {
            color = '#ff4444'; // Red for asks
            position = 'aboveBar';
            shape = 'arrowDown';
        } else if (isMarket) {
            shape = 'circle';
            position = event.side === 'buy' ? 'belowBar' : 'aboveBar';
        }

        const usdValue = event.usd_value / 1000; // Convert to K
        const text = usdValue >= 1 ? `${usdValue.toFixed(1)}K` : '';

        return {
            time: new Date(event.time).getTime() / 1000,
            position: position,
            color: color,
            shape: shape,
            text: text,
            size: 1,
            // Store full event data for tooltip (custom implementation needed)
            _eventData: event
        };
    });

    return markers;
}

// Load whale events into the events panel
function loadWhaleEvents(data) {
    // Update event statistics
    const totalEvents = data.whale_events.length;
    const totalVolume = data.whale_events.reduce((sum, e) => sum + (e.usd_value || 0), 0);

    document.getElementById('event-stat-total').textContent = totalEvents;
    document.getElementById('event-stat-volume').textContent = `$${formatNumber(totalVolume)}`;

    // Load events into timeline
    loadEventsList('during', data.whale_events);

    if (data.whale_events_before && data.whale_events_before.length > 0) {
        document.getElementById('events-before').style.display = 'block';
        loadEventsList('before', data.whale_events_before);
    } else {
        document.getElementById('events-before').style.display = 'none';
    }

    if (data.whale_events_after && data.whale_events_after.length > 0) {
        document.getElementById('events-after').style.display = 'block';
        loadEventsList('after', data.whale_events_after);
    } else {
        document.getElementById('events-after').style.display = 'none';
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

    // Add click handler to highlight on chart
    div.addEventListener('click', () => {
        const timestamp = new Date(event.time).getTime() / 1000;
        chart.timeScale().scrollToPosition(timestamp, true);
    });

    return div;
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

    // Event search
    document.getElementById('event-search').addEventListener('input', (e) => {
        filterEvents(e.target.value, document.getElementById('event-type-filter').value);
    });

    // Event type filter
    document.getElementById('event-type-filter').addEventListener('change', (e) => {
        filterEvents(document.getElementById('event-search').value, e.target.value);
    });
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

// Show error toast
function showError(message) {
    const toast = document.getElementById('error-toast');
    const messageElement = document.getElementById('error-message');

    messageElement.textContent = message;
    toast.style.display = 'flex';

    // Auto-hide after 5 seconds
    setTimeout(() => {
        toast.style.display = 'none';
    }, 5000);
}

// Update analysis info from filename and data
function updateAnalysisInfo(filename, intervals, metadata) {
    const analysisInfo = document.getElementById('analysis-info');

    // Use metadata if available, otherwise extract from filename
    let symbol = 'Unknown';
    let lookback = 'N/A';
    let interval = 'N/A';
    let threshold = 'N/A';

    if (metadata) {
        // Use metadata from new JSON format
        symbol = metadata.symbol || 'Unknown';
        lookback = metadata.lookback || 'N/A';
        interval = metadata.interval || 'N/A';
        threshold = `${metadata.min_change}%+`;
    } else {
        // Fallback: extract from filename for old format
        console.log('Parsing filename:', filename);

        // Extract symbol from filename
        let match = filename.match(/price_changes_([A-Z0-9]+_[A-Z0-9]+)_\d+\.json/i);
        if (match) {
            symbol = match[1];
        } else {
            match = filename.match(/price_changes_(.+?)_\d{8}_\d{6}\.json/i);
            if (match) {
                symbol = match[1];
            }
        }

        // Calculate interval from first interval data
        if (intervals && intervals.length > 0) {
            const firstInterval = intervals[0];
            const startTime = new Date(firstInterval.start_time);
            const endTime = new Date(firstInterval.end_time);
            const durationMs = endTime - startTime;
            const durationSec = Math.round(durationMs / 1000);

            if (durationSec >= 3600) {
                interval = `${Math.round(durationSec / 3600)}h`;
            } else if (durationSec >= 60) {
                interval = `${Math.round(durationSec / 60)}m`;
            } else {
                interval = `${durationSec}s`;
            }

            threshold = `${Math.abs(firstInterval.change_pct).toFixed(2)}%+ detected`;
        }
    }

    console.log('Analysis info:', { symbol, lookback, interval, threshold });

    document.getElementById('info-symbol').textContent = symbol;
    document.getElementById('info-interval').textContent = interval;
    document.getElementById('info-lookback').textContent = lookback;
    document.getElementById('info-threshold').textContent = threshold;

    // Show the analysis info section
    analysisInfo.style.display = 'flex';
}
