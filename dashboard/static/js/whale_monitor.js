/**
 * Simple Whale Event Monitor
 * Shows one top whale event at a time with price context
 */

let currentData = null;
let allEvents = [];
let filteredEvents = [];
let currentEventIndex = 0;
let chart = null;

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    initChart();
    loadFileList();
    setupEventListeners();
});

function initChart() {
    const chartEl = document.getElementById('main-chart');
    if (chartEl) {
        chart = echarts.init(chartEl);
        window.addEventListener('resize', () => chart && chart.resize());
    }
}

function setupEventListeners() {
    // File selector
    document.getElementById('file-selector').addEventListener('change', function() {
        if (this.value) loadWhaleData(this.value);
    });

    // Refresh
    document.getElementById('refresh-btn').addEventListener('click', () => loadFileList());

    // New monitor
    document.getElementById('new-monitor-btn').addEventListener('click', () => {
        document.getElementById('new-monitor-modal').style.display = 'block';
    });

    // Monitor form
    document.getElementById('monitor-form').addEventListener('submit', function(e) {
        e.preventDefault();
        runMonitor();
    });

    // Event selector
    document.getElementById('event-selector').addEventListener('change', function() {
        const idx = parseInt(this.value);
        if (!isNaN(idx)) showEvent(idx);
    });

    // Navigation
    document.getElementById('prev-event').addEventListener('click', () => {
        if (currentEventIndex > 0) showEvent(currentEventIndex - 1);
    });

    document.getElementById('next-event').addEventListener('click', () => {
        if (currentEventIndex < allEvents.length - 1) showEvent(currentEventIndex + 1);
    });

    // Fullscreen
    document.getElementById('fullscreen-btn').addEventListener('click', function() {
        const wrapper = document.querySelector('.chart-wrapper');
        if (!document.fullscreenElement) {
            wrapper.requestFullscreen();
        } else {
            document.exitFullscreen();
        }
    });

    // Filter event listeners
    document.getElementById('filter-market').addEventListener('change', applyFilters);
    document.getElementById('filter-increase').addEventListener('change', applyFilters);
    document.getElementById('filter-decrease').addEventListener('change', applyFilters);
    document.getElementById('filter-technical').addEventListener('change', applyFilters);

    document.getElementById('distance-slider').addEventListener('input', function() {
        document.getElementById('distance-value').textContent = (this.value / 100).toFixed(2) + '%';
        applyFilters();
    });

    document.querySelectorAll('input[name="side-filter"]').forEach(radio => {
        radio.addEventListener('change', applyFilters);
    });

    // Filter details popup - use event delegation
    document.addEventListener('click', function(e) {
        if (e.target && e.target.id === 'filtered-count') {
            showFilterDetails();
        }

        // Close popup when clicking outside
        if (e.target && e.target.id === 'filter-details-popup') {
            e.target.style.display = 'none';
        }
    });
}

async function loadFileList() {
    try {
        const res = await fetch('/api/whale-monitor-files');
        const data = await res.json();
        const selector = document.getElementById('file-selector');
        selector.innerHTML = '<option value="">Select scan...</option>';

        if (data.files && data.files.length > 0) {
            data.files.forEach(f => {
                const date = new Date(f.modified * 1000);
                const opt = document.createElement('option');
                opt.value = f.filename;
                opt.textContent = `${f.filename} (${date.toLocaleString()})`;
                selector.appendChild(opt);
            });
            selector.value = data.files[0].filename;
            loadWhaleData(data.files[0].filename);
        }
    } catch (err) {
        console.error('Error loading files:', err);
    }
}

async function loadWhaleData(filename) {
    try {
        const res = await fetch(`/api/whale-monitor-data/${filename}`);
        const data = await res.json();
        currentData = data;

        // Combine all events and sort by USD value
        allEvents = [];
        for (const cat in data.categories) {
            allEvents.push(...(data.categories[cat] || []));
        }
        allEvents.sort((a, b) => b.usd_value - a.usd_value);

        // Apply filters and populate event selector
        applyFilters();
    } catch (err) {
        console.error('Error loading data:', err);
    }
}

function showEvent(idx) {
    if (idx < 0 || idx >= filteredEvents.length) return;

    currentEventIndex = idx;
    const event = filteredEvents[idx];

    // Update UI
    document.getElementById('event-selector').value = idx;
    document.getElementById('event-rank').textContent = `Event #${idx + 1}`;

    // Navigation buttons
    document.getElementById('prev-event').disabled = (idx === 0);
    document.getElementById('next-event').disabled = (idx === filteredEvents.length - 1);

    // Event details
    const details = document.getElementById('event-details');
    details.style.display = 'block';

    document.getElementById('event-type-display').textContent = formatEventType(event.event_type, event.side);
    document.getElementById('event-usd-display').textContent = formatUSD(event.usd_value);
    document.getElementById('event-price-display').textContent = '$' + event.price.toFixed(2);
    document.getElementById('event-volume-display').textContent = event.volume.toFixed(4);
    document.getElementById('event-time-display').textContent = new Date(event.time).toLocaleString();
    document.getElementById('event-distance-display').textContent = event.distance_from_mid_pct.toFixed(2) + '%';

    // Update chart
    updateChart(event);
}

function updateChart(event) {
    if (!chart || !currentData) return;

    const eventTime = new Date(event.time);

    // Get price data around this event (±5 minutes, or whatever is available)
    const before = 5 * 60 * 1000; // 5 minutes in ms
    const after = 5 * 60 * 1000;
    let startTime = new Date(eventTime.getTime() - before);
    let endTime = new Date(eventTime.getTime() + after);

    // Get all price data
    const allPriceData = (currentData.price_data || []).map(p => ({
        time: new Date(p.time),
        value: p.mid_price
    }));

    if (allPriceData.length === 0) {
        document.getElementById('loading').innerHTML = '<p>No price data available</p>';
        return;
    }

    // Find actual data boundaries
    const dataStartTime = new Date(Math.min(...allPriceData.map(p => p.time.getTime())));
    const dataEndTime = new Date(Math.max(...allPriceData.map(p => p.time.getTime())));

    // Adjust time window to available data
    if (startTime < dataStartTime) startTime = dataStartTime;
    if (endTime > dataEndTime) endTime = dataEndTime;

    // If event is outside data range, show 10 minutes of data around the closest available time
    if (eventTime < dataStartTime || eventTime > dataEndTime) {
        const tenMinutes = 10 * 60 * 1000;
        if (eventTime < dataStartTime) {
            startTime = dataStartTime;
            endTime = new Date(Math.min(dataStartTime.getTime() + tenMinutes, dataEndTime.getTime()));
        } else {
            endTime = dataEndTime;
            startTime = new Date(Math.max(dataEndTime.getTime() - tenMinutes, dataStartTime.getTime()));
        }
    }

    // Filter price data
    const priceData = allPriceData.filter(p => {
        return p.time >= startTime && p.time <= endTime;
    });

    if (priceData.length === 0) {
        document.getElementById('loading').innerHTML = '<p>No price data for this time range</p>';
        return;
    }

    document.getElementById('loading').style.display = 'none';

    // Event marker
    let markerColor, markerSymbol;
    const etype = event.event_type;
    const side = event.side;

    if (etype === 'market_buy') {
        markerColor = '#00c2ff';
        markerSymbol = 'circle';
    } else if (etype === 'market_sell') {
        markerColor = '#ff00ff';
        markerSymbol = 'circle';
    } else if (etype === 'increase' && side === 'bid') {
        markerColor = '#88cc88';
        markerSymbol = 'diamond';
    } else if (etype === 'increase' && side === 'ask') {
        markerColor = '#cc8888';
        markerSymbol = 'diamond';
    } else if (etype === 'decrease' && side === 'bid') {
        markerColor = '#cc8888';
        markerSymbol = 'triangle';
    } else if (etype === 'decrease' && side === 'ask') {
        markerColor = '#88cc88';
        markerSymbol = 'triangle';
    } else if (side === 'bid') {
        markerColor = '#00ff88';
        markerSymbol = 'triangle';
    } else {
        markerColor = '#ff4444';
        markerSymbol = 'triangle';
    }

    const markerSize = Math.max(15, Math.min(30, event.usd_value / 5000));

    const option = {
        backgroundColor: 'transparent',
        grid: {
            left: '3%',
            right: '3%',
            bottom: '15%',
            top: '5%',
            containLabel: true
        },
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'cross' },
            backgroundColor: 'rgba(10, 14, 39, 0.9)',
            borderColor: 'rgba(0, 194, 255, 0.3)',
            textStyle: { color: '#e0e0e0' }
        },
        xAxis: {
            type: 'time',
            axisLabel: {
                color: '#888',
                formatter: (value) => new Date(value).toLocaleTimeString()
            },
            axisLine: { lineStyle: { color: '#333' } },
            splitLine: { show: false }
        },
        yAxis: {
            type: 'value',
            scale: true,
            axisLabel: {
                color: '#888',
                formatter: '${value}'
            },
            axisLine: { lineStyle: { color: '#333' } },
            splitLine: { lineStyle: { color: '#222', type: 'dashed' } }
        },
        dataZoom: [
            { type: 'inside', start: 0, end: 100 },
            {
                type: 'slider',
                start: 0,
                end: 100,
                backgroundColor: 'rgba(47, 69, 84, 0.3)',
                fillerColor: 'rgba(0, 194, 255, 0.1)',
                borderColor: 'rgba(0, 194, 255, 0.3)',
                handleStyle: { color: '#00c2ff' },
                textStyle: { color: '#888' }
            }
        ],
        series: [
            {
                name: 'Price',
                type: 'line',
                data: priceData.map(d => [d.time, d.value]),
                lineStyle: {
                    color: '#00c2ff',
                    width: 2.5,
                    shadowBlur: 4,
                    shadowColor: 'rgba(0, 194, 255, 0.3)'
                },
                itemStyle: { color: '#00c2ff' },
                symbol: 'none',
                smooth: 0.3,
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
                sampling: 'lttb',
                z: 2
            },
            {
                name: 'Whale Event',
                type: 'scatter',
                data: [[eventTime, event.price]],
                symbolSize: markerSize,
                itemStyle: {
                    color: markerColor,
                    borderColor: '#000',
                    borderWidth: 2,
                    shadowBlur: 10,
                    shadowColor: markerColor
                },
                symbol: markerSymbol,
                z: 10,
                label: {
                    show: true,
                    formatter: formatUSD(event.usd_value),
                    position: 'top',
                    color: '#fff',
                    fontSize: 12,
                    fontWeight: 'bold',
                    backgroundColor: 'rgba(0, 0, 0, 0.7)',
                    padding: [4, 8],
                    borderRadius: 4
                }
            }
        ]
    };

    chart.setOption(option);

    // Add click handler for event marker
    chart.on('click', function(params) {
        if (params.componentType === 'series' && params.seriesName === 'Whale Event') {
            showEventDetailsModal();
        }
    });
}

async function runMonitor() {
    const symbol = document.getElementById('symbol-input').value;
    const lookback = document.getElementById('lookback-input').value;
    const minUsd = document.getElementById('min-usd-input').value;
    const top = document.getElementById('top-input').value;
    const maxDistance = parseFloat(document.getElementById('distance-slider').value) / 100; // Convert to percentage

    const form = document.getElementById('monitor-form');
    const status = document.getElementById('monitor-status');
    const msg = document.getElementById('status-message');

    form.style.display = 'none';
    status.style.display = 'flex';
    msg.textContent = 'Running monitor...';

    try {
        const res = await fetch('/api/run-whale-monitor', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbol,
                lookback,
                min_usd: parseFloat(minUsd),
                top: parseInt(top),
                max_distance: maxDistance
            })
        });

        const result = await res.json();

        if (result.success) {
            msg.textContent = 'Complete! Loading...';
            await loadFileList();
            setTimeout(() => {
                document.getElementById('new-monitor-modal').style.display = 'none';
                form.style.display = 'block';
                status.style.display = 'none';
            }, 1000);
        } else {
            msg.textContent = `Error: ${result.error}`;
            setTimeout(() => {
                form.style.display = 'block';
                status.style.display = 'none';
            }, 3000);
        }
    } catch (err) {
        console.error(err);
        msg.textContent = `Error: ${err.message}`;
        setTimeout(() => {
            form.style.display = 'block';
            status.style.display = 'none';
        }, 3000);
    }
}

function formatEventType(type, side) {
    const map = {
        'market_buy': '🟢 Market Buy',
        'market_sell': '🔴 Market Sell',
        'increase': side === 'bid' ? '📈 Bid Increase' : '📉 Ask Increase',
        'decrease': side === 'bid' ? '📉 Bid Decrease' : '📈 Ask Decrease',
        'new_bid': '🆕 New Bid',
        'new_ask': '🆕 New Ask'
    };
    return map[type] || type;
}

function formatUSD(value) {
    if (value >= 1000000) return `$${(value / 1000000).toFixed(2)}M`;
    if (value >= 1000) return `$${(value / 1000).toFixed(1)}K`;
    return `$${value.toFixed(0)}`;
}

function applyFilters() {
    if (allEvents.length === 0) return;

    // Get filter values
    const filterMarket = document.getElementById('filter-market').checked;
    const filterIncrease = document.getElementById('filter-increase').checked;
    const filterDecrease = document.getElementById('filter-decrease').checked;
    const filterTechnical = document.getElementById('filter-technical').checked;
    const maxDistance = parseFloat(document.getElementById('distance-slider').value) / 100;
    const sideFilter = document.querySelector('input[name="side-filter"]:checked').value;

    // Filter events
    filteredEvents = allEvents.filter(event => {
        // Event type filter
        const eventType = event.event_type;
        const side = event.side;

        let typeAllowed = false;
        if (filterMarket && (eventType === 'market_buy' || eventType === 'market_sell')) {
            typeAllowed = true;
        }
        if (filterIncrease && eventType === 'increase') {
            typeAllowed = true;
        }
        if (filterDecrease && eventType === 'decrease') {
            typeAllowed = true;
        }
        if (filterTechnical && (eventType === 'entered_top' || eventType === 'left_top' || eventType === 'new_bid' || eventType === 'new_ask')) {
            typeAllowed = true;
        }

        if (!typeAllowed) return false;

        // Distance filter
        if (Math.abs(event.distance_from_mid_pct) > maxDistance) return false;

        // Side filter
        if (sideFilter !== 'both' && event.side !== sideFilter) return false;

        return true;
    });

    // Update event selector
    const selector = document.getElementById('event-selector');
    selector.innerHTML = '';
    filteredEvents.forEach((event, idx) => {
        const opt = document.createElement('option');
        opt.value = idx;
        opt.textContent = `#${idx + 1}: ${formatEventType(event.event_type, event.side)} - ${formatUSD(event.usd_value)}`;
        selector.appendChild(opt);
    });

    // Update filtered count
    const countEl = document.getElementById('filtered-count');
    if (filteredEvents.length === allEvents.length) {
        countEl.textContent = `Showing all ${allEvents.length} events`;
    } else {
        countEl.textContent = `Showing ${filteredEvents.length} of ${allEvents.length} events`;
    }

    document.getElementById('event-total').textContent = `of ${filteredEvents.length} events`;

    // Show first filtered event
    if (filteredEvents.length > 0) {
        selector.value = 0;
        showEvent(0);
    } else {
        document.getElementById('event-details').style.display = 'none';
        document.getElementById('loading').innerHTML = '<p>No events match the current filters</p>';
        document.getElementById('loading').style.display = 'block';
    }
}

function resetFilters() {
    // Reset checkboxes - Market and Increase checked by default
    document.getElementById('filter-market').checked = true;
    document.getElementById('filter-increase').checked = true;
    document.getElementById('filter-decrease').checked = false;
    document.getElementById('filter-technical').checked = false;

    // Reset distance slider to max (5%)
    document.getElementById('distance-slider').value = 500;
    document.getElementById('distance-value').textContent = '5.00%';

    // Reset side filter to both
    document.querySelector('input[name="side-filter"][value="both"]').checked = true;

    // Re-apply filters
    applyFilters();
}

function showEventDetailsModal() {
    if (currentEventIndex < 0 || currentEventIndex >= filteredEvents.length) return;

    const event = filteredEvents[currentEventIndex];

    // Calculate price impact (if we have price data)
    const eventTime = new Date(event.time);
    const priceData = currentData.price_data || [];

    // Find price 1min and 5min after event
    const oneMinAfter = new Date(eventTime.getTime() + 60 * 1000);
    const fiveMinAfter = new Date(eventTime.getTime() + 5 * 60 * 1000);

    let priceAfter1min = null;
    let priceAfter5min = null;

    for (const p of priceData) {
        const t = new Date(p.time);
        if (!priceAfter1min && t >= oneMinAfter) {
            priceAfter1min = p.mid_price;
        }
        if (!priceAfter5min && t >= fiveMinAfter) {
            priceAfter5min = p.mid_price;
            break;
        }
    }

    const priceChange1min = priceAfter1min ? ((priceAfter1min - event.price) / event.price * 100).toFixed(2) : 'N/A';
    const priceChange5min = priceAfter5min ? ((priceAfter5min - event.price) / event.price * 100).toFixed(2) : 'N/A';

    // Determine color based on event type and side
    let eventColor = '#00ffa3';
    if (event.event_type === 'market_buy' || (event.event_type === 'increase' && event.side === 'bid')) {
        eventColor = '#00ffa3';
    } else if (event.event_type === 'market_sell' || (event.event_type === 'increase' && event.side === 'ask')) {
        eventColor = '#ff3b69';
    }

    const html = `
        <div class="event-modal-grid">
            <div class="event-modal-section">
                <h4>Event Information</h4>
                <div class="event-modal-item">
                    <span class="event-modal-label">Type:</span>
                    <span class="event-modal-value" style="color: ${eventColor}">${formatEventType(event.event_type, event.side)}</span>
                </div>
                <div class="event-modal-item">
                    <span class="event-modal-label">USD Value:</span>
                    <span class="event-modal-value" style="color: ${eventColor}; font-size: 1.3rem; font-weight: 700;">${formatUSD(event.usd_value)}</span>
                </div>
                <div class="event-modal-item">
                    <span class="event-modal-label">Time:</span>
                    <span class="event-modal-value">${new Date(event.time).toLocaleString()}</span>
                </div>
                <div class="event-modal-item">
                    <span class="event-modal-label">Rank:</span>
                    <span class="event-modal-value">#${currentEventIndex + 1} of ${filteredEvents.length}</span>
                </div>
            </div>

            <div class="event-modal-section">
                <h4>Order Details</h4>
                <div class="event-modal-item">
                    <span class="event-modal-label">Price:</span>
                    <span class="event-modal-value">$${event.price.toFixed(2)}</span>
                </div>
                <div class="event-modal-item">
                    <span class="event-modal-label">Volume:</span>
                    <span class="event-modal-value">${event.volume.toFixed(4)}</span>
                </div>
                <div class="event-modal-item">
                    <span class="event-modal-label">Side:</span>
                    <span class="event-modal-value">${event.side === 'bid' ? '📗 Bid' : '📕 Ask'}</span>
                </div>
            </div>

            <div class="event-modal-section">
                <h4>Market Context</h4>
                <div class="event-modal-item">
                    <span class="event-modal-label">Mid Price:</span>
                    <span class="event-modal-value">$${event.mid_price.toFixed(2)}</span>
                </div>
                <div class="event-modal-item">
                    <span class="event-modal-label">Distance from Mid:</span>
                    <span class="event-modal-value">${event.distance_from_mid_pct.toFixed(2)}%</span>
                </div>
                <div class="event-modal-item">
                    <span class="event-modal-label">Best Bid:</span>
                    <span class="event-modal-value">$${event.best_bid.toFixed(2)}</span>
                </div>
                <div class="event-modal-item">
                    <span class="event-modal-label">Best Ask:</span>
                    <span class="event-modal-value">$${event.best_ask.toFixed(2)}</span>
                </div>
                <div class="event-modal-item">
                    <span class="event-modal-label">Spread:</span>
                    <span class="event-modal-value">${((event.best_ask - event.best_bid) / event.mid_price * 100).toFixed(3)}%</span>
                </div>
            </div>

            <div class="event-modal-section">
                <h4>Price Impact</h4>
                <div class="event-modal-item">
                    <span class="event-modal-label">1min After:</span>
                    <span class="event-modal-value" style="color: ${priceChange1min !== 'N/A' && parseFloat(priceChange1min) > 0 ? '#00ffa3' : priceChange1min !== 'N/A' && parseFloat(priceChange1min) < 0 ? '#ff3b69' : 'inherit'}">
                        ${priceChange1min !== 'N/A' ? (priceChange1min > 0 ? '+' : '') + priceChange1min + '%' : 'N/A'}
                    </span>
                </div>
                <div class="event-modal-item">
                    <span class="event-modal-label">5min After:</span>
                    <span class="event-modal-value" style="color: ${priceChange5min !== 'N/A' && parseFloat(priceChange5min) > 0 ? '#00ffa3' : priceChange5min !== 'N/A' && parseFloat(priceChange5min) < 0 ? '#ff3b69' : 'inherit'}">
                        ${priceChange5min !== 'N/A' ? (priceChange5min > 0 ? '+' : '') + priceChange5min + '%' : 'N/A'}
                    </span>
                </div>
            </div>
        </div>
    `;

    document.getElementById('event-modal-content').innerHTML = html;
    document.getElementById('event-details-modal').style.display = 'flex';
}
