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

        // Find whale events near this time (from all periods: before, during, after)
        const currentTime = new Date(param.time * 1000);

        // Collect events from all three periods
        const allEvents = [
            ...(currentInterval.whale_events_before || []),
            ...(currentInterval.whale_events || []),
            ...(currentInterval.whale_events_after || [])
        ];

        let nearbyEvents = allEvents.filter(event => {
            const eventTime = new Date(event.time);
            return Math.abs(eventTime - currentTime) <= timeWindow;
        });

        // Count event types and calculate volumes
        const bidEvents = nearbyEvents.filter(e => e.side === 'bid' || e.event_type.includes('bid'));
        const askEvents = nearbyEvents.filter(e => e.side === 'ask' || e.event_type.includes('ask'));
        const marketEvents = nearbyEvents.filter(e => e.event_type.includes('market'));

        const bidVolume = bidEvents.reduce((sum, e) => sum + (e.usd_value || 0), 0);
        const askVolume = askEvents.reduce((sum, e) => sum + (e.usd_value || 0), 0);
        const marketVolume = marketEvents.reduce((sum, e) => sum + (e.usd_value || 0), 0);
        const totalVolume = bidVolume + askVolume + marketVolume;

        // Determine which period we're in
        const startTime = new Date(currentInterval.start_time).getTime();
        const endTime = new Date(currentInterval.end_time).getTime();
        const currentTimeMs = currentTime.getTime();

        let periodLabel = '';
        if (currentTimeMs < startTime) {
            periodLabel = '<span style="color: #2962ff;">⬅ BEFORE</span>';
        } else if (currentTimeMs >= startTime && currentTimeMs <= endTime) {
            periodLabel = '<span style="color: #ffaa00;">◆ DURING</span>';
        } else {
            periodLabel = '<span style="color: #ff6b6b;">➡ AFTER</span>';
        }

        // Build whale events section
        let whaleSection = '';
        if (nearbyEvents.length > 0) {
            const windowSec = (timeWindow / 1000).toFixed(0);
            whaleSection = `
                <div style="margin-top: 6px; padding-top: 6px; border-top: 1px solid #404040;">
                    <div style="font-size: 11px; margin-bottom: 3px; color: #b0b0b0;">
                        ${periodLabel} | Whale Events (±${windowSec}s):
                    </div>
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

    // Handle chart click to show detailed event information
    chart.subscribeClick((param) => {
        if (!param.time || !currentInterval) return;

        const clickedTime = new Date(param.time * 1000);
        showEventDetailsModal(clickedTime, currentInterval);
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

    // Add whale event markers - BEFORE interval (semi-transparent)
    if (currentInterval && currentInterval.whale_events_before) {
        const beforeMarkers = createWhaleMarkers(currentInterval.whale_events_before, 0.3);
        allMarkers.push(...beforeMarkers);
    }

    // Add whale event markers - DURING interval (full opacity)
    if (currentInterval && currentInterval.whale_events) {
        const duringMarkers = createWhaleMarkers(currentInterval.whale_events, 1.0);
        allMarkers.push(...duringMarkers);
    }

    // Add whale event markers - AFTER interval (semi-transparent)
    if (currentInterval && currentInterval.whale_events_after) {
        const afterMarkers = createWhaleMarkers(currentInterval.whale_events_after, 0.3);
        allMarkers.push(...afterMarkers);
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

    // Add visual boundary lines for context periods
    // Note: TradingView doesn't support vertical lines directly, but markers already show START/END
    // We could add shaded regions using additional series if needed

    // Fit content
    chart.timeScale().fitContent();
}

// Create markers for whale events
function createWhaleMarkers(events, opacity = 1.0) {
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

        // Apply opacity to color
        if (opacity < 1.0) {
            color = applyOpacity(color, opacity);
        }

        const usdValue = event.usd_value / 1000; // Convert to K
        const text = usdValue >= 1 ? `${usdValue.toFixed(1)}K` : '';

        return {
            time: new Date(event.time).getTime() / 1000,
            position: position,
            color: color,
            shape: shape,
            text: opacity === 1.0 ? text : '', // Hide text for semi-transparent markers
            size: opacity === 1.0 ? 1 : 0.5, // Smaller size for context events
            // Store full event data for tooltip (custom implementation needed)
            _eventData: event
        };
    });

    return markers;
}

// Apply opacity to hex color
function applyOpacity(hexColor, opacity) {
    // Convert hex to RGB
    const hex = hexColor.replace('#', '');
    const r = parseInt(hex.substring(0, 2), 16);
    const g = parseInt(hex.substring(2, 4), 16);
    const b = parseInt(hex.substring(4, 6), 16);

    // Return as rgba with opacity
    return `rgba(${r}, ${g}, ${b}, ${opacity})`;
}

// Load whale events into the events panel
function loadWhaleEvents(data) {
    // Calculate statistics for all three periods
    const beforeEvents = data.whale_events_before || [];
    const duringEvents = data.whale_events || [];
    const afterEvents = data.whale_events_after || [];

    const beforeCount = beforeEvents.length;
    const duringCount = duringEvents.length;
    const afterCount = afterEvents.length;

    const beforeVolume = beforeEvents.reduce((sum, e) => sum + (e.usd_value || 0), 0);
    const duringVolume = duringEvents.reduce((sum, e) => sum + (e.usd_value || 0), 0);
    const afterVolume = afterEvents.reduce((sum, e) => sum + (e.usd_value || 0), 0);

    const totalEvents = beforeCount + duringCount + afterCount;
    const totalVolume = beforeVolume + duringVolume + afterVolume;

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
    if (priceChange > 0 && bidVolume > askVolume * 1.5) {
        insights.push({
            type: 'positive',
            icon: '🟢',
            text: 'Strong buying pressure drove price up',
            value: `${(bidVolume / askVolume).toFixed(1)}x bids`
        });
    } else if (priceChange < 0 && askVolume > bidVolume * 1.5) {
        insights.push({
            type: 'negative',
            icon: '🔴',
            text: 'Heavy selling pressure pushed price down',
            value: `${(askVolume / bidVolume).toFixed(1)}x asks`
        });
    }

    // Insight 5: Market reaction (after events)
    if (afterEvents.length > duringEvents.length * 1.3) {
        insights.push({
            type: 'warning',
            icon: '⚡',
            text: 'Strong market reaction following spike',
            value: `${afterEvents.length} events after`
        });
    }

    // Render insights
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

// Show detailed event information modal when clicking on chart
function showEventDetailsModal(clickedTime, intervalData) {
    const modal = document.getElementById('event-details-modal');
    const modalTitle = document.getElementById('modal-title');
    const modalBody = document.getElementById('modal-body');

    // Get all events from all periods
    const allEvents = [
        ...(intervalData.whale_events_before || []).map(e => ({ ...e, period: 'before' })),
        ...(intervalData.whale_events || []).map(e => ({ ...e, period: 'during' })),
        ...(intervalData.whale_events_after || []).map(e => ({ ...e, period: 'after' }))
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

    modalTitle.innerHTML = `
        <span style="color: ${periodColor};">${periodLabel}</span>
        Whale Events at ${timeStr}
    `;

    if (eventsAtTime.length === 0) {
        modalBody.innerHTML = `
            <div style="text-align: center; padding: 3rem; color: #707070;">
                <div style="font-size: 3rem; margin-bottom: 1rem;">🐋</div>
                <div style="font-size: 1.1rem;">No whale events found within ±2s of this time</div>
            </div>
        `;
    } else {
        // Calculate summary statistics
        const bidEvents = eventsAtTime.filter(e => e.side === 'bid' || e.event_type.includes('bid'));
        const askEvents = eventsAtTime.filter(e => e.side === 'ask' || e.event_type.includes('ask'));
        const marketEvents = eventsAtTime.filter(e => e.event_type.includes('market'));

        const totalVolume = eventsAtTime.reduce((sum, e) => sum + (e.usd_value || 0), 0);
        const bidVolume = bidEvents.reduce((sum, e) => sum + (e.usd_value || 0), 0);
        const askVolume = askEvents.reduce((sum, e) => sum + (e.usd_value || 0), 0);

        // Build modal content
        modalBody.innerHTML = `
            <div class="modal-summary">
                <div class="modal-summary-grid">
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
                            ${marketEvents.length}
                            <div style="font-size: 0.75rem; color: #ffaa00; margin-top: 2px;">$${formatNumber(marketEvents.reduce((sum, e) => sum + (e.usd_value || 0), 0))}</div>
                        </div>
                    </div>
                    <div class="modal-summary-item">
                        <div class="modal-summary-label">Net Pressure</div>
                        <div class="modal-summary-value" style="color: ${bidVolume > askVolume ? '#00ff88' : '#ff4444'};">
                            ${bidVolume > askVolume ? '🟢 BULLISH' : '🔴 BEARISH'}
                            <div style="font-size: 0.75rem; margin-top: 2px;">
                                ${bidVolume > askVolume ?
                                    `${((bidVolume / askVolume) || 0).toFixed(1)}x more bids` :
                                    `${((askVolume / bidVolume) || 0).toFixed(1)}x more asks`}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="modal-section">
                <div class="modal-section-title">Event Details (${eventsAtTime.length} events)</div>
                ${eventsAtTime.map(event => createModalEventItem(event)).join('')}
            </div>
        `;
    }

    // Show modal
    modal.style.display = 'flex';

    // Close on background click
    modal.onclick = (e) => {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    };
}

// Create detailed event item for modal
function createModalEventItem(event) {
    const isBid = event.side === 'bid' || event.event_type.includes('bid');
    const isAsk = event.side === 'ask' || event.event_type.includes('ask');
    const isMarket = event.event_type.includes('market');

    let eventClass = '';
    if (isBid) eventClass = 'bid';
    else if (isAsk) eventClass = 'ask';
    else if (isMarket) eventClass = 'market';

    const time = new Date(event.time).toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        fractionalSecondDigits: 3
    });

    const periodBadge = event.period === 'before' ? '<span style="color: #2962ff; font-size: 0.75rem;">⬅ BEFORE</span>' :
                        event.period === 'during' ? '<span style="color: #ffaa00; font-size: 0.75rem;">◆ DURING</span>' :
                        '<span style="color: #ff6b6b; font-size: 0.75rem;">➡ AFTER</span>';

    return `
        <div class="modal-event-item ${eventClass}">
            <div class="modal-event-header">
                <div>
                    <span class="modal-event-type ${eventClass}">${event.event_type.replace('_', ' ').toUpperCase()}</span>
                    ${periodBadge}
                </div>
                <span class="modal-event-time">${time}</span>
            </div>
            <div class="modal-event-details">
                <div class="modal-event-detail">
                    <span class="modal-event-detail-label">Side</span>
                    <span class="modal-event-detail-value">${event.side.toUpperCase()}</span>
                </div>
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
