// Historical Chart Dashboard - Enhanced version matching live_chart.js quality
// ECharts-based historical price chart with whale events for timestamp ±5min window

let chart = null;
let priceData = [];
let whaleEvents = [];
let currentSymbol = 'TAO_USDT';
let currentTimestamp = null;

// Filter state - default to only market buy/sell
let filters = {
    price: true,
    marketBuy: true,
    marketSell: true,
    newBid: false,
    newAsk: false,
    bidIncrease: false,
    askIncrease: false
};

// Get URL parameters
function getUrlParams() {
    const urlParams = new URLSearchParams(window.location.search);
    return {
        symbol: urlParams.get('symbol'),
        timestamp: urlParams.get('timestamp'),
        minUsd: urlParams.get('min_usd') || urlParams.get('minUsd')
    };
}

// Update URL with current parameters
function updateUrl() {
    const params = new URLSearchParams();
    if (currentSymbol) params.set('symbol', currentSymbol);
    if (currentTimestamp) params.set('timestamp', currentTimestamp);
    const minUsd = document.getElementById('min-usd-input')?.value;
    if (minUsd) params.set('min_usd', minUsd);

    const newUrl = `${window.location.pathname}?${params.toString()}`;
    window.history.replaceState({}, '', newUrl);
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    await loadSymbols();
    setupEventListeners();
    initializeChart();

    // Check for URL parameters
    const urlParams = getUrlParams();

    if (urlParams.symbol) {
        currentSymbol = urlParams.symbol;
        document.getElementById('symbol-select').value = urlParams.symbol;
    }

    if (urlParams.timestamp) {
        // Parse timestamp and set input
        try {
            const timestamp = new Date(urlParams.timestamp);
            document.getElementById('timestamp-input').value =
                timestamp.toISOString().slice(0, 16);

            // Show loading state while auto-loading
            showLoading(true, 'Loading data from URL...');

            // Auto-load data if timestamp is provided
            setTimeout(() => loadChartData(), 100);
        } catch (error) {
            console.error('Invalid timestamp in URL:', error);
            setDefaultTimestamp();
            showLoading(false);
        }
    } else {
        setDefaultTimestamp();
    }
});

// Set default timestamp to current time
function setDefaultTimestamp() {
    const now = new Date();
    // Round down to nearest minute
    now.setSeconds(0);
    now.setMilliseconds(0);
    document.getElementById('timestamp-input').value =
        now.toISOString().slice(0, 16);
}

// Load available symbols
async function loadSymbols() {
    try {
        const response = await fetch('/api/config/symbols');
        const data = await response.json();

        const select = document.getElementById('symbol-select');
        select.innerHTML = data.symbols.map(symbol =>
            `<option value="${symbol}" ${symbol === 'TAO_USDT' ? 'selected' : ''}>
              ${symbol}
            </option>`
        ).join('');

        currentSymbol = 'TAO_USDT';
    } catch (error) {
        showError('Failed to load symbols: ' + error.message);
    }
}

// Setup event listeners
function setupEventListeners() {
    document.getElementById('symbol-select').addEventListener('change', (e) => {
        currentSymbol = e.target.value;
    });

    document.getElementById('load-btn').addEventListener('click', loadChartData);

    document.getElementById('download-chart-btn').addEventListener('click', exportChartData);

    document.getElementById('fullscreen-btn').addEventListener('click', toggleFullscreen);

    // Filter checkboxes
    ['filter-price', 'filter-new-bid', 'filter-new-ask', 'filter-market-buy',
     'filter-market-sell', 'filter-bid-increase', 'filter-ask-increase'].forEach(id => {
        document.getElementById(id).addEventListener('change', (e) => {
            const filterName = id.replace('filter-', '').replace(/-([a-z])/g, (g) => g[1].toUpperCase());
            filters[filterName] = e.target.checked;
            updateChart();
        });
    });

    const eventTypeFilter = document.getElementById('event-type-filter');
    if (eventTypeFilter) {
        eventTypeFilter.addEventListener('change', filterEvents);
    }

    // Preset button handlers - update immediately on click
    document.querySelectorAll('.usd-preset-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const value = parseInt(this.getAttribute('data-value'));

            // Update input field
            const chartInput = document.getElementById('chart-min-usd-filter');
            if (chartInput) chartInput.value = value;

            // Update active state
            document.querySelectorAll('.usd-preset-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            // Update status text
            const statusEl = document.getElementById('usd-filter-status');
            if (statusEl) {
                const statusText = value === 0 ? 'Showing all events' : `Filtering: ≥ $${safeFixed(value / 1000, 0)}K`;
                statusEl.textContent = statusText;
            }

            // Update chart IMMEDIATELY on button click
            if (whaleEvents.length > 0) {
                updateChart();
                updateEventsList(whaleEvents);
            }
        });
    });

    // Legend input - apply on Enter key
    const chartMinUsdFilter = document.getElementById('chart-min-usd-filter');
    if (chartMinUsdFilter) {
        chartMinUsdFilter.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                const value = parseInt(this.value) || 0;

                // Update active state on preset buttons
                document.querySelectorAll('.usd-preset-btn').forEach(btn => {
                    if (parseInt(btn.getAttribute('data-value')) === value) {
                        btn.classList.add('active');
                    } else {
                        btn.classList.remove('active');
                    }
                });

                // Update status text
                const statusEl = document.getElementById('usd-filter-status');
                if (statusEl) {
                    const statusText = value === 0 ? 'Showing all events' : `Filtering: ≥ $${safeFixed(value / 1000, 0)}K`;
                    statusEl.textContent = statusText;
                }

                // Update chart
                if (whaleEvents.length > 0) {
                    updateChart();
                    updateEventsList(whaleEvents);
                }
            }
        });
    }
}

// Get ECharts configuration (matching live_chart.js)
function getChartOption() {
    return {
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
            formatter: formatTooltip,
            padding: [12, 16],
            shadowBlur: 20,
            shadowColor: 'rgba(0, 255, 163, 0.1)'
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
                end: 100,
                zoomLock: false,
                moveOnMouseMove: true,
                moveOnMouseWheel: true,
                preventDefaultMouseMove: true
            },
            {
                type: 'slider',
                start: 0,
                end: 100,
                backgroundColor: 'rgba(17, 17, 17, 0.8)',
                dataBackground: {
                    lineStyle: { color: '#00c2ff', width: 1.5 },
                    areaStyle: { color: 'rgba(0, 194, 255, 0.1)' }
                },
                selectedDataBackground: {
                    lineStyle: { color: '#00c2ff', width: 2 },
                    areaStyle: { color: 'rgba(0, 194, 255, 0.3)' }
                },
                fillerColor: 'rgba(0, 194, 255, 0.15)',
                borderColor: 'rgba(255, 255, 255, 0.1)',
                handleStyle: {
                    color: '#00c2ff',
                    borderColor: '#00c2ff',
                    shadowBlur: 8,
                    shadowColor: 'rgba(0, 194, 255, 0.5)'
                },
                textStyle: { color: '#b0b0b0' },
                zoomLock: false
            }
        ],
        xAxis: {
            type: 'time',
            boundaryGap: false,
            axisLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.1)', width: 1 } },
            axisTick: { lineStyle: { color: 'rgba(255, 255, 255, 0.1)' } },
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
            axisLine: { show: false },
            axisTick: { show: false },
            splitLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.05)', width: 1 } },
            axisLabel: {
                color: '#808080',
                fontSize: 11,
                formatter: function(value) {
                    return '$' + safeFixed(value, 4);
                }
            }
        },
        series: [
            // Price line with area fill
            {
                name: 'Price',
                type: 'line',
                data: [],
                smooth: false,
                symbol: 'none',
                lineStyle: { color: '#00c2ff', width: 2 },
                areaStyle: {
                    color: {
                        type: 'linear',
                        x: 0, y: 0, x2: 0, y2: 1,
                        colorStops: [
                            { offset: 0, color: 'rgba(0, 194, 255, 0.3)' },
                            { offset: 1, color: 'rgba(0, 194, 255, 0)' }
                        ]
                    }
                },
                z: 1
            },
            // Market Buy - Aggressive buy order executed immediately
            {
                name: 'Market Buy',
                type: 'scatter',
                data: [],
                symbol: 'circle',
                symbolSize: function(data) {
                    return data[2]?.size || 12;
                },
                itemStyle: {
                    color: function(params) {
                        return params.data[2]?.color || '#00c2ff';
                    }
                },
                label: {
                    show: true,
                    formatter: function(params) {
                        return params.data[2]?.label || '';
                    },
                    position: function(params) {
                        return params.data[2]?.labelPosition || 'bottom';
                    },
                    fontSize: 9,
                    color: '#e0e0e0'
                },
                z: 10
            },
            // Market Sell - Aggressive sell order executed immediately
            {
                name: 'Market Sell',
                type: 'scatter',
                data: [],
                symbol: 'circle',
                symbolSize: function(data) {
                    return data[2]?.size || 12;
                },
                itemStyle: {
                    color: function(params) {
                        return params.data[2]?.color || '#ff00ff';
                    }
                },
                label: {
                    show: true,
                    formatter: function(params) {
                        return params.data[2]?.label || '';
                    },
                    position: function(params) {
                        return params.data[2]?.labelPosition || 'top';
                    },
                    fontSize: 9,
                    color: '#e0e0e0'
                },
                z: 10
            },
            // New Bid - Fresh buy order placed
            {
                name: 'New Bid',
                type: 'scatter',
                data: [],
                symbol: 'triangle',
                symbolSize: function(data) {
                    return data[2]?.size || 10;
                },
                itemStyle: {
                    color: function(params) {
                        return params.data[2]?.color || '#00ff88';
                    }
                },
                label: {
                    show: true,
                    formatter: function(params) {
                        return params.data[2]?.label || '';
                    },
                    position: function(params) {
                        return params.data[2]?.labelPosition || 'bottom';
                    },
                    fontSize: 9,
                    color: '#e0e0e0'
                },
                z: 9
            },
            // New Ask - Fresh sell order placed
            {
                name: 'New Ask',
                type: 'scatter',
                data: [],
                symbol: 'triangle',
                symbolSize: function(data) {
                    return data[2]?.size || 10;
                },
                itemStyle: {
                    color: function(params) {
                        return params.data[2]?.color || '#ff4444';
                    }
                },
                label: {
                    show: true,
                    formatter: function(params) {
                        return params.data[2]?.label || '';
                    },
                    position: function(params) {
                        return params.data[2]?.labelPosition || 'top';
                    },
                    fontSize: 9,
                    color: '#e0e0e0'
                },
                z: 9
            },
            // Bid Increase / Ask Decrease - Potential support building
            {
                name: 'Bid Increase',
                type: 'scatter',
                data: [],
                symbol: 'diamond',
                symbolSize: function(data) {
                    return data[2]?.size || 8;
                },
                itemStyle: {
                    color: function(params) {
                        return params.data[2]?.color || '#88cc88';
                    }
                },
                label: {
                    show: true,
                    formatter: function(params) {
                        return params.data[2]?.label || '';
                    },
                    position: function(params) {
                        return params.data[2]?.labelPosition || 'bottom';
                    },
                    fontSize: 9,
                    color: '#e0e0e0'
                },
                z: 6
            },
            // Ask Increase / Bid Decrease - Potential resistance building
            {
                name: 'Ask Increase',
                type: 'scatter',
                data: [],
                symbol: 'diamond',
                symbolSize: function(data) {
                    return data[2]?.size || 8;
                },
                itemStyle: {
                    color: function(params) {
                        return params.data[2]?.color || '#cc8888';
                    }
                },
                label: {
                    show: true,
                    formatter: function(params) {
                        return params.data[2]?.label || '';
                    },
                    position: function(params) {
                        return params.data[2]?.labelPosition || 'top';
                    },
                    fontSize: 9,
                    color: '#e0e0e0'
                },
                z: 6
            }
        ]
    };
}

// Format tooltip (matching live_chart.js)
function formatTooltip(params) {
    if (!params || params.length === 0) return '';

    const time = new Date(params[0].value[0]).toLocaleTimeString();
    let html = `<div style="font-weight: bold; margin-bottom: 8px;">${time}</div>`;

    params.forEach(param => {
        const value = param.value[1];
        const color = param.color;

        // Check if this is an event with metadata
        if (param.data && param.data[2] && param.data[2].originalEvent) {
            const event = param.data[2].originalEvent;
            const isMarketOrder = event.event_type === 'market_buy' || event.event_type === 'market_sell';

            html += `
                <div style="border-left: 3px solid ${color}; padding-left: 8px; margin: 8px 0;">
                    <div style="font-weight: bold; color: ${color}; margin-bottom: 4px;">${param.seriesName}</div>
                    <div style="margin: 2px 0;"><strong>Price:</strong> $${safeFixed(event.price, 6)}</div>
                    <div style="margin: 2px 0;"><strong>Volume:</strong> ${safeFixed(event.volume, 4)}</div>
                    <div style="margin: 2px 0;"><strong>USD Value:</strong> $${event.usd_value ? event.usd_value.toLocaleString() : '0'}</div>
            `;

            // Show distance from mid for market orders
            if (isMarketOrder && event.distance_from_mid_pct !== undefined) {
                const distanceColor = event.distance_from_mid_pct >= 0 ? '#00ff88' : '#ff4444';
                html += `<div style="margin: 2px 0;"><strong>Distance from Mid:</strong> <span style="color: ${distanceColor};">${event.distance_from_mid_pct >= 0 ? '+' : ''}${safeFixed(event.distance_from_mid_pct, 3)}%</span></div>`;
            }

            html += `
                    <div style="margin: 2px 0; color: #00ffa3; font-size: 0.85rem;">Click for details</div>
                </div>
            `;
        } else {
            // Regular price point
            html += `
                <div style="display: flex; align-items: center; margin: 4px 0;">
                    <span style="display: inline-block; width: 10px; height: 10px; background: ${color}; border-radius: 50%; margin-right: 8px;"></span>
                    <span>${param.seriesName}: <strong>$${safeFixed(value, 6)}</strong></span>
                </div>
            `;
        }
    });

    return html;
}

// Prepare whale event scatter data with dynamic sizing and labels
function prepareWhaleScatterData(events) {
    if (!events || events.length === 0) return [];

    // Sort by time
    const sortedEvents = [...events].sort((a, b) => new Date(a.time) - new Date(b.time));

    // Find min and max USD values for scaling
    const usdValues = sortedEvents.map(e => e.usd_value);
    const minUsd = Math.min(...usdValues);
    const maxUsd = Math.max(...usdValues);

    return sortedEvents.map(event => {
        const isMarketBuy = event.event_type === 'market_buy';
        const isMarketSell = event.event_type === 'market_sell';
        const isNewBid = event.event_type === 'new_bid';
        const isNewAsk = event.event_type === 'new_ask';
        const isIncrease = event.event_type === 'increase' || event.event_type.includes('increase');
        const isDecrease = event.event_type === 'decrease' || event.event_type.includes('decrease');
        const isBid = event.side === 'bid' || event.event_type.includes('bid');
        const isAsk = event.side === 'ask' || event.event_type.includes('ask');

        let color, symbol, labelPosition;

        // DEFINITIVE EVENTS - Bright colors
        if (isMarketBuy) {
            color = '#00c2ff'; // Bright cyan/blue
            symbol = 'circle';
            labelPosition = 'bottom';
        } else if (isMarketSell) {
            color = '#ff00ff'; // Bright magenta/pink
            symbol = 'circle';
            labelPosition = 'top';
        } else if (isNewBid || (isBid && !isIncrease && !isDecrease)) {
            color = '#00ff88'; // Bright green
            symbol = 'triangle';
            labelPosition = 'bottom';
        } else if (isNewAsk || (isAsk && !isIncrease && !isDecrease)) {
            color = '#ff4444'; // Bright red
            symbol = 'triangle';
            labelPosition = 'top';
        }
        // AMBIGUOUS EVENTS - Muted colors (volume changes)
        else if (isIncrease && isBid) {
            color = '#88cc88'; // Muted green (potential support)
            symbol = 'diamond';
            labelPosition = 'bottom';
        } else if (isIncrease && isAsk) {
            color = '#cc8888'; // Muted red (potential resistance)
            symbol = 'diamond';
            labelPosition = 'top';
        } else if (isDecrease && isBid) {
            color = '#cc8888'; // Muted red (support weakening)
            symbol = 'diamond';
            labelPosition = 'top';
        } else if (isDecrease && isAsk) {
            color = '#88cc88'; // Muted green (resistance weakening)
            symbol = 'diamond';
            labelPosition = 'bottom';
        } else {
            // Fallback for other event types
            color = '#ffaa00'; // Orange (unknown)
            symbol = 'circle';
            labelPosition = 'top';
        }

        // Calculate size based on USD value (logarithmic scale)
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

        const eventTime = new Date(event.time);

        // Calculate label (show USD value in K/M format)
        let label = '';
        const usdValue = event.usd_value;
        if (usdValue >= 1000000) {
            label = `${safeFixed(usdValue / 1000000, 1)}M`;
        } else if (usdValue >= 1000) {
            label = `${safeFixed(usdValue / 1000, 1)}K`;
        }

        return {
            time: eventTime,
            price: event.price,
            color: color,
            symbol: symbol,
            size: size,
            label: label,
            labelPosition: labelPosition,
            originalEvent: event
        };
    });
}

// Initialize ECharts
function initializeChart() {
    const container = document.getElementById('chart-container');
    chart = echarts.init(container, 'dark');

    const option = getChartOption();
    chart.setOption(option);

    // Add click handler for event details modal
    chart.on('click', function(params) {
        if (params.seriesType === 'scatter' && params.data && params.data[2] && params.data[2].originalEvent) {
            showEventModal(params.data[2].originalEvent, params.seriesName);
        }
    });

    // Change cursor on hover over events
    chart.on('mouseover', function(params) {
        if (params.seriesType === 'scatter') {
            container.style.cursor = 'pointer';
        }
    });

    chart.on('mouseout', function() {
        container.style.cursor = 'default';
    });

    // Responsive resize
    window.addEventListener('resize', () => {
        chart.resize();
    });
}

// Load chart data
async function loadChartData() {
    const timestampInput = document.getElementById('timestamp-input').value;
    const interval = parseInt(document.getElementById('interval-select').value) || 5;
    const minUsd = 5000; // Fixed min USD for backend queries

    if (!timestampInput) {
        showError('Please select a timestamp');
        return;
    }

    // Convert to ISO format
    currentTimestamp = new Date(timestampInput).toISOString();

    const totalMinutes = interval * 2;
    const timeLabel = totalMinutes >= 60 ? `${totalMinutes / 60} hour${totalMinutes / 60 > 1 ? 's' : ''}` : `${totalMinutes} min`;
    showLoading(true, `Loading ${currentSymbol} data for ${timeLabel} window...`);

    try {
        // Fetch price history and whale events in parallel
        const [priceResponse, eventsResponse, statsResponse] = await Promise.all([
            fetch(`/api/historical/price-history?symbol=${currentSymbol}&timestamp=${currentTimestamp}&interval=${interval}`),
            fetch(`/api/historical/whale-events?symbol=${currentSymbol}&timestamp=${currentTimestamp}&interval=${interval}&min_usd=${minUsd}`),
            fetch(`/api/historical/stats?symbol=${currentSymbol}&timestamp=${currentTimestamp}&interval=${interval}&min_usd=${minUsd}`)
        ]);

        const priceResult = await priceResponse.json();
        const eventsResult = await eventsResponse.json();
        const statsResult = await statsResponse.json();

        if (priceResult.error) throw new Error(priceResult.error);
        if (eventsResult.error) throw new Error(eventsResult.error);
        if (statsResult.error) throw new Error(statsResult.error);

        priceData = priceResult.data;
        whaleEvents = eventsResult.events;

        updateInfo(priceResult, eventsResult);
        updateStats(statsResult);
        updateChart();
        updateEventsList(whaleEvents);

        // Update URL with current parameters for shareable link
        updateUrl();

    } catch (error) {
        showError('Failed to load data: ' + error.message);
    } finally {
        showLoading(false);
    }
}

// Helper function to safely set text content
function safeSetText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

// Helper function to safely format numbers
function safeFixed(value, decimals) {
    return (value != null && !isNaN(value)) ? value.toFixed(decimals) : '0';
}

// Update info panel
function updateInfo(priceResult, eventsResult) {
    safeSetText('info-symbol', currentSymbol);
    safeSetText('info-window',
        `${new Date(priceResult.start_time).toLocaleTimeString()} - ${new Date(priceResult.end_time).toLocaleTimeString()}`);
    safeSetText('info-min-usd', `Min: $${eventsResult.min_usd.toLocaleString()}`);
    safeSetText('info-status', `${priceResult.count} price points, ${eventsResult.count} events`);
}

// Update stats panel
function updateStats(stats) {
    // Price stats
    if (stats.current_price) {
        safeSetText('stat-current-price', `$${safeFixed(stats.current_price, 2)}`);

        const changeEl = document.getElementById('stat-price-change');
        if (changeEl) {
            const change = stats.price_change || 0;
            const changePct = stats.price_change_pct || 0;
            changeEl.textContent = `${change >= 0 ? '+' : ''}$${safeFixed(change, 2)} (${safeFixed(changePct, 2)}%)`;
            changeEl.className = 'stat-value ' + (change >= 0 ? 'stat-bullish' : 'stat-bearish');
        }
    }

    // Average sizes
    safeSetText('stat-avg-buy', stats.avg_buy_size ? `$${stats.avg_buy_size.toLocaleString(undefined, {maximumFractionDigits: 0})}` : '-');
    safeSetText('stat-avg-sell', stats.avg_sell_size ? `$${stats.avg_sell_size.toLocaleString(undefined, {maximumFractionDigits: 0})}` : '-');

    // Largest orders
    safeSetText('stat-largest-buy', stats.max_buy_size ? `$${stats.max_buy_size.toLocaleString(undefined, {maximumFractionDigits: 0})}` : '-');
    safeSetText('stat-largest-sell', stats.max_sell_size ? `$${stats.max_sell_size.toLocaleString(undefined, {maximumFractionDigits: 0})}` : '-');

    // Volumes
    safeSetText('stat-buy-volume', stats.total_buy_volume ? `$${stats.total_buy_volume.toLocaleString(undefined, {maximumFractionDigits: 0})}` : '-');
    safeSetText('stat-sell-volume', stats.total_sell_volume ? `$${stats.total_sell_volume.toLocaleString(undefined, {maximumFractionDigits: 0})}` : '-');

    // Flow and ratio
    const netFlow = stats.net_flow || 0;
    const netFlowEl = document.getElementById('stat-net-flow');
    if (netFlowEl) {
        netFlowEl.textContent = `${netFlow >= 0 ? '+' : ''}$${netFlow.toLocaleString(undefined, {maximumFractionDigits: 0})}`;
        netFlowEl.className = 'stat-value ' + (netFlow >= 0 ? 'stat-bullish' : 'stat-bearish');
    }

    const ratio = stats.buy_sell_ratio || 0;
    const ratioEl = document.getElementById('stat-buy-sell-ratio');
    if (ratioEl) {
        ratioEl.textContent = ratio === Infinity ? '∞' : safeFixed(ratio, 2);
        ratioEl.className = 'stat-value ' + (ratio > 1 ? 'stat-bullish' : ratio < 1 ? 'stat-bearish' : '');
    }

    // Event counts
    const counts = stats.event_counts || {};
    safeSetText('stat-new-bids', (counts.new_bid || 0) + (counts.bid_increase || 0));
    safeSetText('stat-new-asks', (counts.new_ask || 0) + (counts.ask_increase || 0));
    safeSetText('stat-total-events', stats.total_events || 0);

    // Dynamic time range based on interval
    const interval = parseInt(document.getElementById('interval-select')?.value || 5);
    const totalMinutes = interval * 2;
    const timeLabel = totalMinutes >= 60 ? `${totalMinutes / 60}h` : `${totalMinutes}m`;
    safeSetText('stat-time-range', timeLabel);

    // Event stats
    safeSetText('event-stat-buys', counts.market_buy || 0);
    safeSetText('event-stat-sells', counts.market_sell || 0);
    safeSetText('event-stat-bids', (counts.new_bid || 0) + (counts.bid_increase || 0) + (counts.bid_decrease || 0));
    safeSetText('event-stat-asks', (counts.new_ask || 0) + (counts.ask_increase || 0) + (counts.ask_decrease || 0));
}

// Update chart visualization
function updateChart() {
    if (!chart || priceData.length === 0) return;

    // Prepare price data
    const chartData = priceData.map(p => [new Date(p.time), p.mid_price]);

    // Get current Min USD filter value from legend input
    const chartMinUsdFilter = document.getElementById('chart-min-usd-filter');
    const minUsd = chartMinUsdFilter ? (parseFloat(chartMinUsdFilter.value) || 0) : 0;

    // Filter events by Min USD value
    const filteredEvents = whaleEvents.filter(e => e.usd_value >= minUsd);

    // Categorize events by type (enhanced logic matching live_chart.js)
    const marketBuys = filteredEvents.filter(e => e.event_type === 'market_buy');
    const marketSells = filteredEvents.filter(e => e.event_type === 'market_sell');
    const newBids = filteredEvents.filter(e =>
        e.event_type === 'new_bid' ||
        (e.side === 'bid' && !e.event_type.includes('increase') && !e.event_type.includes('decrease'))
    );
    const newAsks = filteredEvents.filter(e =>
        e.event_type === 'new_ask' ||
        (e.side === 'ask' && !e.event_type.includes('increase') && !e.event_type.includes('decrease'))
    );

    // Volume changes (ambiguous events)
    const bidIncreases = filteredEvents.filter(e =>
        (e.event_type === 'increase' || e.event_type === 'bid_increase') && e.side === 'bid'
    );
    const askIncreases = filteredEvents.filter(e =>
        (e.event_type === 'increase' || e.event_type === 'ask_increase') && e.side === 'ask'
    );
    const askDecreases = filteredEvents.filter(e =>
        (e.event_type === 'decrease' || e.event_type === 'ask_decrease') && e.side === 'ask'
    );
    const bidDecreases = filteredEvents.filter(e =>
        (e.event_type === 'decrease' || e.event_type === 'bid_decrease') && e.side === 'bid'
    );

    // Combine for ambiguous categories (matching live_chart.js logic)
    const bidIncreasesAll = [...bidIncreases, ...askDecreases]; // Support building
    const askIncreasesAll = [...askIncreases, ...bidDecreases]; // Resistance building

    // Prepare scatter data with dynamic sizing
    const scatterMarketBuys = prepareWhaleScatterData(marketBuys);
    const scatterMarketSells = prepareWhaleScatterData(marketSells);
    const scatterNewBids = prepareWhaleScatterData(newBids);
    const scatterNewAsks = prepareWhaleScatterData(newAsks);
    const scatterBidIncreases = prepareWhaleScatterData(bidIncreasesAll);
    const scatterAskIncreases = prepareWhaleScatterData(askIncreasesAll);

    // Apply filters - hide series data if filter is unchecked
    const updateOptions = {
        series: [
            { data: filters.price ? chartData : [] }, // Price line
            { data: filters.marketBuy ? scatterMarketBuys.map(e => [e.time, e.price, e]) : [] }, // Market Buy
            { data: filters.marketSell ? scatterMarketSells.map(e => [e.time, e.price, e]) : [] }, // Market Sell
            { data: filters.newBid ? scatterNewBids.map(e => [e.time, e.price, e]) : [] }, // New Bid
            { data: filters.newAsk ? scatterNewAsks.map(e => [e.time, e.price, e]) : [] }, // New Ask
            { data: filters.bidIncrease ? scatterBidIncreases.map(e => [e.time, e.price, e]) : [] }, // Bid Increase
            { data: filters.askIncrease ? scatterAskIncreases.map(e => [e.time, e.price, e]) : [] } // Ask Increase
        ]
    };

    chart.setOption(updateOptions);
}

// Update events list
function updateEventsList(events) {
    const eventsList = document.getElementById('event-list');
    if (!eventsList) return;

    const filterEl = document.getElementById('event-type-filter');
    const filter = filterEl ? filterEl.value : '';

    const chartMinUsdFilter = document.getElementById('chart-min-usd-filter');
    const minUsd = chartMinUsdFilter ? (parseFloat(chartMinUsdFilter.value) || 0) : 0;

    // First filter by Min USD
    let filteredEvents = events.filter(e => e.usd_value >= minUsd);

    // Then filter by event type if selected
    if (filter) {
        if (filter === 'bid' || filter === 'ask') {
            filteredEvents = filteredEvents.filter(e => e.side === filter);
        } else {
            filteredEvents = filteredEvents.filter(e => e.event_type === filter);
        }
    }

    // Sort by time descending
    filteredEvents.sort((a, b) => new Date(b.time) - new Date(a.time));

    eventsList.innerHTML = filteredEvents.map(event => {
        const isBullish = event.side === 'bid' || event.event_type === 'market_buy';
        const badgeClass = isBullish ? 'badge-bullish' : 'badge-bearish';
        const eventIcon = getEventIcon(event.event_type);

        return `
            <div class="whale-event-item">
                <div class="event-header">
                    <span class="event-type ${badgeClass}">${eventIcon} ${event.event_type.replace('_', ' ')}</span>
                    <span class="event-time">${new Date(event.time).toLocaleTimeString()}</span>
                </div>
                <div class="event-details">
                    <div class="event-detail">
                        <span class="detail-label">USD Value:</span>
                        <span class="detail-value ${badgeClass}">$${event.usd_value.toLocaleString(undefined, {maximumFractionDigits: 0})}</span>
                    </div>
                    <div class="event-detail">
                        <span class="detail-label">Price:</span>
                        <span class="detail-value">$${safeFixed(event.price, 2)}</span>
                    </div>
                    <div class="event-detail">
                        <span class="detail-label">Volume:</span>
                        <span class="detail-value">${safeFixed(event.volume, 2)}</span>
                    </div>
                    <div class="event-detail">
                        <span class="detail-label">Distance:</span>
                        <span class="detail-value">${safeFixed(event.distance_from_mid_pct, 2)}%</span>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// Get event icon
function getEventIcon(eventType) {
    const icons = {
        'new_bid': '🔺',
        'new_ask': '🔻',
        'market_buy': '💰',
        'market_sell': '💸',
        'bid_increase': '⬆️',
        'ask_increase': '⬆️',
        'bid_decrease': '⬇️',
        'ask_decrease': '⬇️'
    };
    return icons[eventType] || '●';
}

// Filter events
function filterEvents() {
    updateEventsList(whaleEvents);
}

// Show event modal (matching live_chart.js)
function showEventModal(event, seriesName) {
    // Create modal if it doesn't exist
    let modal = document.getElementById('event-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'event-modal';
        modal.innerHTML = `
            <div class="modal-backdrop" onclick="document.getElementById('event-modal').style.display='none'"></div>
            <div class="modal-content">
                <div class="modal-header">
                    <h3 id="modal-title">Whale Event Details</h3>
                    <button class="modal-close" onclick="document.getElementById('event-modal').style.display='none'">&times;</button>
                </div>
                <div class="modal-body" id="modal-body"></div>
            </div>
        `;
        document.body.appendChild(modal);

        // ESC key to close
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && modal.style.display === 'flex') {
                modal.style.display = 'none';
            }
        });
    }

    // Determine event color and label
    const isMarketBuy = event.event_type === 'market_buy';
    const isMarketSell = event.event_type === 'market_sell';
    const isMarketOrder = isMarketBuy || isMarketSell;
    const isBid = event.side === 'bid';
    const isAsk = event.side === 'ask';

    let sideColor = '#00c2ff';
    if (isMarketBuy) sideColor = '#00c2ff';
    else if (isMarketSell) sideColor = '#ff00ff';
    else if (isBid) sideColor = '#00ff88';
    else if (isAsk) sideColor = '#ff4444';

    const time = new Date(event.time).toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    });

    function formatNumber(num) {
        if (num >= 1000000) return safeFixed(num / 1000000, 2) + 'M';
        if (num >= 1000) return safeFixed(num / 1000, 2) + 'K';
        return safeFixed(num, 2);
    }

    // Format modal content (matching live_chart.js exactly)
    const modalBody = document.getElementById('modal-body');
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
                    <div style="color: #e0e0e0; font-size: 1.1rem; font-weight: 600;">$${safeFixed(event.price, 6)}</div>
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
                    <div style="color: ${event.distance_from_mid_pct >= 0 ? '#00ff88' : '#ff4444'}; font-size: 1.1rem; font-weight: 600;">${event.distance_from_mid_pct >= 0 ? '+' : ''}${safeFixed(event.distance_from_mid_pct, 3)}%</div>
                </div>
                ` : ''}
            </div>
        </div>
    `;

    // Show modal
    modal.style.display = 'flex';
}

// Export chart data as JSON
function exportChartData() {
    if (!priceData || priceData.length === 0 || !whaleEvents || whaleEvents.length === 0) {
        alert('No data loaded to export');
        return;
    }

    // Get current filter value
    const chartMinUsdFilter = document.getElementById('chart-min-usd-filter');
    const minUsd = chartMinUsdFilter ? (parseFloat(chartMinUsdFilter.value) || 0) : 0;

    // Filter events by active filters
    function filterEventsByActiveFilters(events) {
        if (!events || events.length === 0) return [];

        return events.filter(event => {
            // Apply USD filter
            if (event.usd_value < minUsd) return false;

            // Apply event type filters (matching chart rendering logic)
            const eventType = event.event_type || '';
            const side = event.side || '';

            const isMarketBuy = eventType === 'market_buy';
            const isMarketSell = eventType === 'market_sell';
            const isNewBid = eventType === 'new_bid';
            const isNewAsk = eventType === 'new_ask';
            const isIncrease = eventType === 'increase' || eventType.includes('increase');
            const isDecrease = eventType === 'decrease' || eventType.includes('decrease');
            const isBid = side === 'bid' || eventType.includes('bid');
            const isAsk = side === 'ask' || eventType.includes('ask');

            // Check filters
            if (isMarketBuy && !filters.marketBuy) return false;
            if (isMarketSell && !filters.marketSell) return false;
            if (isNewBid && !filters.newBid) return false;
            if (isNewAsk && !filters.newAsk) return false;

            // Bid Increase filter includes: bid increases AND ask decreases (both muted green)
            if ((isIncrease && isBid) && !filters.bidIncrease) return false;
            if ((isDecrease && isAsk) && !filters.bidIncrease) return false;

            // Ask Increase filter includes: ask increases AND bid decreases (both muted red)
            if ((isIncrease && isAsk) && !filters.askIncrease) return false;
            if ((isDecrease && isBid) && !filters.askIncrease) return false;

            return true;
        });
    }

    // Get start and end times from price data
    const startTime = priceData.length > 0 ? priceData[0][0] : null;
    const endTime = priceData.length > 0 ? priceData[priceData.length - 1][0] : null;

    // Build export data
    const exportData = {
        _README: {
            title: "Historical Whale Events - Filtered Chart Data Export",
            description: "This file contains historical order book events and price data filtered according to your selected criteria.",
            data_source: "InfluxDB - Historical MEXC Futures WebSocket Data",
            important_notes: [
                "L2 data is AGGREGATED by price level - individual orders not visible",
                "Increase/Decrease events are AMBIGUOUS - cannot distinguish fills from cancellations",
                "Market Buy/Sell events are DEFINITIVE - we see actual trade executions",
                "USD values are NOTIONAL (futures contracts with leverage) - not actual capital spent",
                "All timestamps are in ISO 8601 format (UTC)",
                "Filters were active during export - this is NOT the complete dataset"
            ]
        },
        metadata: {
            symbol: currentSymbol,
            timestamp: currentTimestamp,
            interval_minutes: parseInt(document.getElementById('interval-select').value) || 5,
            start_time: startTime,
            end_time: endTime,
            exported_at: new Date().toISOString(),
            active_filters: {
                market_buy: filters.marketBuy,
                market_sell: filters.marketSell,
                new_bid: filters.newBid,
                new_ask: filters.newAsk,
                bid_increase: filters.bidIncrease,
                ask_increase: filters.askIncrease,
                min_usd: minUsd
            }
        },
        field_definitions: {
            price: "Price level where event occurred",
            volume: "Contracts quantity",
            usd_value: "Notional value = price × volume",
            distance_from_mid_pct: "Distance from mid-price as percentage",
            level: "Position in order book depth",
            side: "bid = buy orders, ask = sell orders",
            event_type: "Type of whale event",
            time: "Event timestamp in ISO 8601 format (UTC)"
        },
        price_data: priceData || [],
        whale_events: filterEventsByActiveFilters(whaleEvents)
    };

    // Add statistics
    exportData.statistics = {
        total_events: exportData.whale_events.length,
        total_volume_usd: exportData.whale_events.reduce((sum, e) => sum + (e.usd_value || 0), 0),
        price_points: exportData.price_data.length
    };

    // Create filename
    const timestamp = new Date(currentTimestamp);
    const filterSuffix = minUsd > 0 ? `_min${minUsd}usd` : '';
    const filename = `historical_${currentSymbol}_${timestamp.toISOString().replace(/[:.]/g, '-')}${filterSuffix}_filtered.json`;

    // Create and download JSON blob
    const jsonData = JSON.stringify(exportData, null, 2);
    const blob = new Blob([jsonData], { type: 'application/json' });
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

    console.log('Exported filtered chart data:', {
        filename,
        total_events: exportData.statistics.total_events,
        price_points: exportData.statistics.price_points,
        filters: exportData.metadata.active_filters
    });
}

// Toggle fullscreen
function toggleFullscreen() {
    const chartWrapper = document.querySelector('.chart-wrapper');
    if (!document.fullscreenElement) {
        chartWrapper.requestFullscreen();
    } else {
        document.exitFullscreen();
    }
}

// Show/hide loading
function showLoading(show, message = 'Loading chart data...') {
    const loading = document.getElementById('loading');
    if (show) {
        loading.style.display = 'flex';
        const loadingText = loading.querySelector('p');
        if (loadingText) {
            loadingText.textContent = message;
        }
    } else {
        loading.style.display = 'none';
    }
}

// Show error toast
function showError(message) {
    const toast = document.getElementById('error-toast');
    document.getElementById('error-message').textContent = message;
    toast.style.display = 'flex';
    setTimeout(() => {
        toast.style.display = 'none';
    }, 5000);
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (chart) {
        chart.dispose();
    }
});
