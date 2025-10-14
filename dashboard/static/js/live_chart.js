// Live Chart Dashboard - ECharts-based real-time price chart with whale events

let chart = null;
let updateInterval = null;
let lastUpdateTime = null;

// Chart data
let priceData = [];
let whaleEvents = [];

// User interaction tracking
let userHasZoomed = false; // Track if user manually zoomed/panned
let initialDataZoom = null; // Store initial zoom state

// Filter state
let filters = {
    price: true,
    marketBuy: true,
    marketSell: true,
    newBid: true,
    newAsk: true,
    bidIncrease: true,
    askIncrease: true
};

// Sound notification state
let soundEnabled = true;
let lastEventIds = new Set(); // Track which events we've already played sounds for

// Create audio context for beep sounds
let audioContext = null;
function initAudio() {
    if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
}

// Play beep sound
function playBeep(frequency, duration) {
    if (!soundEnabled || !audioContext) return;

    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();

    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);

    oscillator.frequency.value = frequency;
    oscillator.type = 'sine';

    gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + duration);

    oscillator.start(audioContext.currentTime);
    oscillator.stop(audioContext.currentTime + duration);
}

// Get configuration from URL params, localStorage, or defaults
function getConfig() {
    const urlParams = new URLSearchParams(window.location.search);
    return {
        symbol: urlParams.get('symbol') || localStorage.getItem('live_chart_symbol') || 'SPX_USDT',
        lookback: urlParams.get('lookback') || localStorage.getItem('live_chart_lookback') || '5m',
        minUsd: parseFloat(urlParams.get('minUsd') || localStorage.getItem('live_chart_minUsd') || '5000'),
        refreshInterval: 1000 // 1000ms (1 update per second)
    };
}

// Update URL with current config
function updateURL() {
    const params = new URLSearchParams();
    params.set('symbol', config.symbol);
    params.set('lookback', config.lookback);
    params.set('minUsd', config.minUsd);
    const newURL = `${window.location.pathname}?${params.toString()}`;
    window.history.replaceState({}, '', newURL);
}

// Configuration
const config = getConfig();

// Initialize dashboard
document.addEventListener('DOMContentLoaded', async () => {
    try {
        showLoading(true);

        // Load symbols configuration first
        await loadSymbols();

        // Set UI elements to saved values
        document.getElementById('lookback-select').value = config.lookback;
        document.getElementById('min-usd-input').value = config.minUsd;

        // Update URL to reflect current config
        updateURL();

        await initChart();
        setupEventListeners();

        // Load initial data and wait for it to complete
        await refreshData(false);

        // Set up auto-refresh
        updateInterval = setInterval(() => {
            refreshData(true);
        }, config.refreshInterval);
    } catch (error) {
        console.error('Error initializing dashboard:', error);
        showError('Failed to initialize dashboard: ' + error.message);
    } finally {
        // Hide loading only after data is loaded
        showLoading(false);
    }
});

// Load symbols from API
async function loadSymbols() {
    try {
        const response = await fetch('/api/config/symbols');
        if (!response.ok) throw new Error('Failed to load symbols');

        const data = await response.json();
        const symbolSelect = document.getElementById('symbol-select');

        // Clear existing options
        symbolSelect.innerHTML = '';

        // Add symbols from API
        data.symbols.forEach(symbol => {
            const option = document.createElement('option');
            option.value = symbol;
            option.textContent = symbol;
            // Select saved symbol from localStorage, or default
            if (symbol === config.symbol) {
                option.selected = true;
            }
            symbolSelect.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading symbols:', error);
        // Fallback to hardcoded symbols
        const symbolSelect = document.getElementById('symbol-select');
        const fallbackSymbols = ['SPX_USDT', 'BANANA_USDT', 'DOGE_USDT', 'FLOKI_USDT', 'MOODENG_USDT'];
        fallbackSymbols.forEach(symbol => {
            const option = document.createElement('option');
            option.value = symbol;
            option.textContent = symbol;
            symbolSelect.appendChild(option);
        });
    }
}

// Initialize ECharts
async function initChart() {
    const chartContainer = document.getElementById('chart-container');
    chart = echarts.init(chartContainer);

    // Set default option
    const option = getChartOption();
    chart.setOption(option);

    // Handle click events on whale events
    chart.on('click', function(params) {
        // Only handle clicks on scatter series (whale events)
        if (params.componentType === 'series' && params.seriesType === 'scatter') {
            const eventData = params.data[2]; // Third element contains metadata
            if (eventData && eventData.originalEvent) {
                showEventModal(eventData.originalEvent, params.seriesName);
            }
        }
    });

    // Change cursor on hover over whale events
    chart.on('mouseover', function(params) {
        if (params.componentType === 'series' && params.seriesType === 'scatter') {
            chartContainer.style.cursor = 'pointer';
        }
    });

    chart.on('mouseout', function(params) {
        chartContainer.style.cursor = 'default';
    });

    // Detect user zoom/pan interactions
    chart.on('datazoom', function(params) {
        // Check if user is viewing the most recent data (right edge)
        const option = chart.getOption();
        const dataZoom = option.dataZoom[0];

        // If the end is at or near 100% (viewing latest data), allow auto-follow
        // Otherwise, user is viewing historical data - lock the view
        if (dataZoom && dataZoom.end !== undefined) {
            if (dataZoom.end >= 95) {
                // User is at the right edge - allow auto-follow
                userHasZoomed = false;
                console.log('User at right edge - enabling auto-follow');
            } else {
                // User is viewing historical data - lock view
                userHasZoomed = true;
                console.log('User viewing history - disabling auto-follow');
            }
        }
    });

    // Also detect mousewheel zoom
    chartContainer.addEventListener('wheel', function(e) {
        if (e.ctrlKey || e.metaKey) {
            // User is zooming with Ctrl+wheel
            userHasZoomed = true;
        }
    });

    // Detect drag/pan
    let isDragging = false;
    chartContainer.addEventListener('mousedown', function() {
        isDragging = true;
    });
    chartContainer.addEventListener('mouseup', function() {
        if (isDragging) {
            isDragging = false;
        }
    });
    chartContainer.addEventListener('mousemove', function(e) {
        if (isDragging && e.buttons === 1) {
            // User is panning
            userHasZoomed = true;
        }
    });

    // Handle window resize
    window.addEventListener('resize', () => {
        chart.resize();
    });
}

// Get ECharts option
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
                    return '$' + value.toFixed(4);
                }
            }
        },
        series: [
            // Price line
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
            // DEFINITIVE EVENTS (Bright colors) - High certainty of whale action
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
            // New Bid - Fresh buy order placed (never seen this price before)
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
            // New Ask - Fresh sell order placed (never seen this price before)
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
            // AMBIGUOUS EVENTS (Muted colors) - Could be modifications, cancellations, or fills
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

// Format tooltip
function formatTooltip(params) {
    if (!params || params.length === 0) return '';

    const time = new Date(params[0].value[0]).toLocaleTimeString();
    let html = `<div style="font-weight: bold; margin-bottom: 8px;">${time}</div>`;

    params.forEach(param => {
        const value = param.value[1];
        const color = param.color;

        // Check if this is an event with metadata (third element in array)
        if (param.data && param.data[2] && param.data[2].originalEvent) {
            const event = param.data[2].originalEvent;
            const isMarketOrder = event.event_type === 'market_buy' || event.event_type === 'market_sell';

            html += `
                <div style="border-left: 3px solid ${color}; padding-left: 8px; margin: 8px 0;">
                    <div style="font-weight: bold; color: ${color}; margin-bottom: 4px;">${param.seriesName}</div>
                    <div style="margin: 2px 0;"><strong>Price:</strong> $${event.price.toFixed(6)}</div>
                    <div style="margin: 2px 0;"><strong>Volume:</strong> ${event.volume.toFixed(4)}</div>
                    <div style="margin: 2px 0;"><strong>USD Value:</strong> $${event.usd_value.toLocaleString()}</div>
            `;

            // Show distance from mid for market orders
            if (isMarketOrder && event.distance_from_mid_pct !== undefined) {
                const distanceColor = event.distance_from_mid_pct >= 0 ? '#00ff88' : '#ff4444';
                html += `<div style="margin: 2px 0;"><strong>Distance from Mid:</strong> <span style="color: ${distanceColor};">${event.distance_from_mid_pct >= 0 ? '+' : ''}${event.distance_from_mid_pct.toFixed(3)}%</span></div>`;
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
                    <span>${param.seriesName}: <strong>$${value.toFixed(6)}</strong></span>
                </div>
            `;
        }
    });

    return html;
}

// Fetch price history
async function fetchPriceHistory() {
    try {
        const response = await fetch(`/api/live/price-history?symbol=${config.symbol}&lookback=${config.lookback}`);
        const data = await response.json();

        if (data.error) {
            showError('Error fetching price history: ' + data.error);
            return;
        }

        priceData = data.data || [];
    } catch (error) {
        console.error('Error fetching price history:', error);
        showError('Failed to fetch price history');
    }
}

// Fetch whale events
async function fetchWhaleEvents(incremental = false) {
    try {
        let url = `/api/live/whale-events?symbol=${config.symbol}&lookback=${config.lookback}&min_usd=${config.minUsd}`;

        if (incremental && lastUpdateTime) {
            url += `&last_timestamp=${encodeURIComponent(lastUpdateTime)}`;
        }

        const response = await fetch(url);
        const data = await response.json();

        if (data.error) {
            showError('Error fetching whale events: ' + data.error);
            return;
        }

        const newEvents = data.events || [];

        if (data.is_incremental && newEvents.length > 0) {
            // Check for new market buy/sell events and play sounds
            newEvents.forEach(event => {
                const eventId = `${event.time}_${event.event_type}_${event.price}_${event.volume}`;

                if (!lastEventIds.has(eventId)) {
                    lastEventIds.add(eventId);

                    // Play sound for market orders
                    if (event.event_type === 'market_buy') {
                        playBeep(880, 0.15); // High beep for buy (A5 note)
                    } else if (event.event_type === 'market_sell') {
                        playBeep(440, 0.15); // Lower beep for sell (A4 note)
                    }
                }
            });

            // Append new events
            whaleEvents = whaleEvents.concat(newEvents);

            // Remove old events outside lookback window
            const cutoffTime = new Date(Date.now() - parseLookback(config.lookback));
            whaleEvents = whaleEvents.filter(e => new Date(e.time) > cutoffTime);

            // Clean up old event IDs from tracking set
            const cutoffTimestamp = cutoffTime.getTime();
            const validEventIds = new Set();
            whaleEvents.forEach(e => {
                const eventId = `${e.time}_${e.event_type}_${e.price}_${e.volume}`;
                if (new Date(e.time).getTime() > cutoffTimestamp) {
                    validEventIds.add(eventId);
                }
            });
            lastEventIds = validEventIds;
        } else {
            // Full reload - rebuild event ID tracking
            whaleEvents = newEvents;
            lastEventIds.clear();
            whaleEvents.forEach(e => {
                const eventId = `${e.time}_${e.event_type}_${e.price}_${e.volume}`;
                lastEventIds.add(eventId);
            });
        }

        // Update last timestamp
        if (whaleEvents.length > 0) {
            const times = whaleEvents.map(e => new Date(e.time));
            lastUpdateTime = new Date(Math.max(...times)).toISOString();
        }
    } catch (error) {
        console.error('Error fetching whale events:', error);
        showError('Failed to fetch whale events');
    }
}

// Parse lookback string to milliseconds
function parseLookback(lookback) {
    const unit = lookback.slice(-1);
    const value = parseInt(lookback.slice(0, -1));

    switch(unit) {
        case 's': return value * 1000;
        case 'm': return value * 60 * 1000;
        case 'h': return value * 60 * 60 * 1000;
        case 'd': return value * 24 * 60 * 60 * 1000;
        default: return 5 * 60 * 1000;
    }
}

// Prepare whale event scatter data (matching chart.js pattern)
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
        const isIncrease = event.event_type === 'increase';
        const isDecrease = event.event_type === 'decrease';
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

        // Calculate label (show USD value in K format for >= 1K)
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
            originalEvent: event
        };
    });
}

// Update chart with latest data
function updateChart() {
    if (!chart || priceData.length === 0) return;

    // Prepare price data
    const chartData = priceData.map(p => [new Date(p.time), p.price]);

    // Categorize events by type
    const marketBuys = whaleEvents.filter(e => e.event_type === 'market_buy');
    const marketSells = whaleEvents.filter(e => e.event_type === 'market_sell');
    const newBids = whaleEvents.filter(e => e.event_type === 'new_bid' || (e.side === 'bid' && !e.event_type.includes('increase') && !e.event_type.includes('decrease')));
    const newAsks = whaleEvents.filter(e => e.event_type === 'new_ask' || (e.side === 'ask' && !e.event_type.includes('increase') && !e.event_type.includes('decrease')));

    // Volume changes (ambiguous events)
    const bidIncreases = whaleEvents.filter(e => e.event_type === 'increase' && e.side === 'bid');
    const askIncreases = whaleEvents.filter(e => e.event_type === 'increase' && e.side === 'ask');
    const askDecreases = whaleEvents.filter(e => e.event_type === 'decrease' && e.side === 'ask');
    const bidDecreases = whaleEvents.filter(e => e.event_type === 'decrease' && e.side === 'bid');

    // Combine for ambiguous categories
    const bidIncreasesAll = [...bidIncreases, ...askDecreases]; // Support building
    const askIncreasesAll = [...askIncreases, ...bidDecreases]; // Resistance building

    // Prepare scatter data
    const scatterMarketBuys = prepareWhaleScatterData(marketBuys);
    const scatterMarketSells = prepareWhaleScatterData(marketSells);
    const scatterNewBids = prepareWhaleScatterData(newBids);
    const scatterNewAsks = prepareWhaleScatterData(newAsks);
    const scatterBidIncreases = prepareWhaleScatterData(bidIncreasesAll);
    const scatterAskIncreases = prepareWhaleScatterData(askIncreasesAll);

    // Get current option state
    const currentOption = chart.getOption();

    // Prepare update options with all necessary config
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

    // If user has manually zoomed/panned, preserve their exact zoom state
    if (userHasZoomed) {
        const currentDataZoom = currentOption.dataZoom || [];
        // Lock the dataZoom to current view - use startValue/endValue (absolute time) instead of start/end (percentage)
        updateOptions.dataZoom = currentDataZoom.map(dz => {
            const dzCopy = {
                type: dz.type,
                xAxisIndex: dz.xAxisIndex,
                filterMode: 'none' // Important: Don't filter data, just zoom view
            };

            // Use absolute time values to lock the view
            if (dz.startValue !== undefined) {
                dzCopy.startValue = dz.startValue;
            }
            if (dz.endValue !== undefined) {
                dzCopy.endValue = dz.endValue;
            }

            // Copy other properties for slider
            if (dz.type === 'slider') {
                dzCopy.backgroundColor = dz.backgroundColor;
                dzCopy.dataBackground = dz.dataBackground;
                dzCopy.selectedDataBackground = dz.selectedDataBackground;
                dzCopy.fillerColor = dz.fillerColor;
                dzCopy.borderColor = dz.borderColor;
                dzCopy.handleStyle = dz.handleStyle;
                dzCopy.textStyle = dz.textStyle;
                dzCopy.zoomLock = false;
            } else {
                // Inside zoom properties
                dzCopy.zoomLock = false;
                dzCopy.moveOnMouseMove = true;
                dzCopy.moveOnMouseWheel = true;
                dzCopy.preventDefaultMouseMove = true;
            }

            return dzCopy;
        });

        console.log('Preserving zoom with values:', updateOptions.dataZoom);
    }

    // Update chart with merge mode (notMerge: false preserves other options)
    chart.setOption(updateOptions, {
        notMerge: false,
        lazyUpdate: false,
        silent: true // Silent to prevent triggering datazoom event
    });
}

// Update event list
function updateEventList() {
    const eventListEl = document.getElementById('event-list');
    if (!eventListEl) return;

    // Get all events and sort by time (most recent first)
    const allEvents = [...whaleEvents].sort((a, b) => new Date(b.time) - new Date(a.time));

    // Take top 30
    const topEvents = allEvents.slice(0, 30);

    if (topEvents.length === 0) {
        eventListEl.innerHTML = '<div style="padding: 2rem; text-align: center; color: #808080;">No whale events found</div>';
        return;
    }

    eventListEl.innerHTML = topEvents.map(e => {
        const time = new Date(e.time).toLocaleTimeString();
        let eventColor = '';
        let eventLabel = '';
        let eventSymbol = '';

        // Match the chart categorization
        const isMarketBuy = e.event_type === 'market_buy';
        const isMarketSell = e.event_type === 'market_sell';
        const isNewBid = e.event_type === 'new_bid';
        const isNewAsk = e.event_type === 'new_ask';
        const isIncrease = e.event_type === 'increase';
        const isDecrease = e.event_type === 'decrease';
        const isBid = e.side === 'bid';
        const isAsk = e.side === 'ask';

        if (isMarketBuy) {
            eventColor = '#00c2ff';
            eventLabel = 'MARKET BUY';
            eventSymbol = '●';
        } else if (isMarketSell) {
            eventColor = '#ff00ff';
            eventLabel = 'MARKET SELL';
            eventSymbol = '●';
        } else if (isNewBid || (isBid && !isIncrease && !isDecrease)) {
            eventColor = '#00ff88';
            eventLabel = 'NEW BID';
            eventSymbol = '▲';
        } else if (isNewAsk || (isAsk && !isIncrease && !isDecrease)) {
            eventColor = '#ff4444';
            eventLabel = 'NEW ASK';
            eventSymbol = '▼';
        } else if (isIncrease && isBid) {
            eventColor = '#88cc88';
            eventLabel = 'BID INCREASE';
            eventSymbol = '◆';
        } else if (isIncrease && isAsk) {
            eventColor = '#cc8888';
            eventLabel = 'ASK INCREASE';
            eventSymbol = '◆';
        } else if (isDecrease && isBid) {
            eventColor = '#cc8888';
            eventLabel = 'BID DECREASE';
            eventSymbol = '◆';
        } else if (isDecrease && isAsk) {
            eventColor = '#88cc88';
            eventLabel = 'ASK DECREASE';
            eventSymbol = '◆';
        } else {
            eventColor = '#ffaa00';
            eventLabel = e.event_type.toUpperCase().replace('_', ' ');
            eventSymbol = '●';
        }

        return `
            <div class="whale-event-item" style="border-left: 3px solid ${eventColor};">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <span style="color: #808080; font-size: 0.9rem;">${time}</span>
                        <strong style="margin-left: 1rem; color: ${eventColor};">${eventSymbol} ${eventLabel}</strong>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-weight: bold;">$${e.usd_value.toLocaleString()}</div>
                        <div style="color: #808080; font-size: 0.85rem;">@ $${e.price.toFixed(4)}</div>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// Update stats
// Format large numbers with K/M notation
function formatLargeNumber(value) {
    if (value >= 1000000) {
        return '$' + (value / 1000000).toFixed(2) + 'M';
    } else if (value >= 1000) {
        return '$' + (value / 1000).toFixed(1) + 'K';
    } else {
        return '$' + value.toFixed(0);
    }
}

function updateStats() {
    if (priceData.length === 0) return;

    const currentPrice = priceData[priceData.length - 1].price;
    const firstPrice = priceData[0].price;
    const priceChange = currentPrice - firstPrice;
    const priceChangePct = (priceChange / firstPrice) * 100;

    // Calculate market flow using proper categorization
    const marketBuys = whaleEvents.filter(e => e.event_type === 'market_buy');
    const marketSells = whaleEvents.filter(e => e.event_type === 'market_sell');
    const newBids = whaleEvents.filter(e => e.event_type === 'new_bid' || (e.side === 'bid' && !e.event_type.includes('increase') && !e.event_type.includes('decrease')));
    const newAsks = whaleEvents.filter(e => e.event_type === 'new_ask' || (e.side === 'ask' && !e.event_type.includes('increase') && !e.event_type.includes('decrease')));
    const bidIncreases = whaleEvents.filter(e => e.event_type === 'increase' && e.side === 'bid');
    const askIncreases = whaleEvents.filter(e => e.event_type === 'increase' && e.side === 'ask');

    const buyVolume = marketBuys.reduce((sum, e) => sum + e.usd_value, 0);
    const sellVolume = marketSells.reduce((sum, e) => sum + e.usd_value, 0);
    const netFlow = buyVolume - sellVolume;

    // Calculate averages
    const avgBuy = marketBuys.length > 0 ? buyVolume / marketBuys.length : 0;
    const avgSell = marketSells.length > 0 ? sellVolume / marketSells.length : 0;

    // Find largest orders
    const largestBuy = marketBuys.length > 0 ? Math.max(...marketBuys.map(e => e.usd_value)) : 0;
    const largestSell = marketSells.length > 0 ? Math.max(...marketSells.map(e => e.usd_value)) : 0;

    // Buy/Sell ratio
    const buySellRatio = sellVolume > 0 ? buyVolume / sellVolume : (buyVolume > 0 ? 999 : 0);

    // Update price info
    document.getElementById('stat-current-price').textContent = '$' + currentPrice.toFixed(6);

    const changeEl = document.getElementById('stat-price-change');
    changeEl.textContent = (priceChange >= 0 ? '+' : '') + priceChange.toFixed(6) +
                          ' (' + (priceChange >= 0 ? '+' : '') + priceChangePct.toFixed(2) + '%)';
    changeEl.style.color = priceChange >= 0 ? '#00ffa3' : '#ff3b69';

    // Update market order stats
    document.getElementById('stat-avg-buy').textContent = formatLargeNumber(avgBuy);
    document.getElementById('stat-avg-sell').textContent = formatLargeNumber(avgSell);
    document.getElementById('stat-largest-buy').textContent = formatLargeNumber(largestBuy);
    document.getElementById('stat-largest-sell').textContent = formatLargeNumber(largestSell);

    // Update volume stats
    document.getElementById('stat-buy-volume').textContent = formatLargeNumber(buyVolume);
    document.getElementById('stat-sell-volume').textContent = formatLargeNumber(sellVolume);

    const flowEl = document.getElementById('stat-net-flow');
    flowEl.textContent = (netFlow >= 0 ? '+' : '') + formatLargeNumber(Math.abs(netFlow));
    flowEl.style.color = netFlow >= 0 ? '#00ffa3' : '#ff3b69';

    // Update buy/sell ratio
    const ratioEl = document.getElementById('stat-buy-sell-ratio');
    if (buySellRatio >= 999) {
        ratioEl.textContent = '∞';
        ratioEl.style.color = '#00ffa3';
    } else if (buySellRatio === 0) {
        ratioEl.textContent = '0';
        ratioEl.style.color = '#ff3b69';
    } else {
        ratioEl.textContent = buySellRatio.toFixed(2);
        ratioEl.style.color = buySellRatio > 1 ? '#00ffa3' : '#ff3b69';
    }

    // Update order book stats
    document.getElementById('stat-new-bids').textContent = newBids.length;
    document.getElementById('stat-new-asks').textContent = newAsks.length;

    // Update general stats
    document.getElementById('stat-total-events').textContent = whaleEvents.length.toLocaleString();
    document.getElementById('stat-last-update').textContent = new Date().toLocaleTimeString();

    // Event stats - matching new categorization
    document.getElementById('event-stat-buys').textContent = marketBuys.length;
    document.getElementById('event-stat-sells').textContent = marketSells.length;
    document.getElementById('event-stat-bids').textContent = newBids.length + bidIncreases.length;
    document.getElementById('event-stat-asks').textContent = newAsks.length + askIncreases.length;

    // Update info panel
    document.getElementById('info-symbol').textContent = config.symbol;
    document.getElementById('info-lookback').textContent = `Last ${config.lookback}`;
    document.getElementById('info-min-usd').textContent = `Min: $${config.minUsd.toLocaleString()}`;
}

// Refresh data
async function refreshData(incremental = false) {
    await Promise.all([
        fetchPriceHistory(),
        fetchWhaleEvents(incremental)
    ]);

    updateChart();
    updateEventList();
    updateStats();
}

// Setup event listeners
function setupEventListeners() {
    // Copy symbol button
    document.getElementById('copy-symbol-btn').addEventListener('click', async () => {
        const symbolText = document.getElementById('info-symbol').textContent;
        const copyBtn = document.getElementById('copy-symbol-btn');
        try {
            await navigator.clipboard.writeText(symbolText);
            copyBtn.textContent = '✓';
            copyBtn.style.background = 'rgba(0, 255, 163, 0.3)';
            setTimeout(() => {
                copyBtn.textContent = '📋';
                copyBtn.style.background = 'rgba(0, 255, 163, 0.1)';
            }, 1500);
        } catch (err) {
            console.error('Failed to copy:', err);
            copyBtn.textContent = '✗';
            setTimeout(() => {
                copyBtn.textContent = '📋';
            }, 1500);
        }
    });

    // Symbol selector
    document.getElementById('symbol-select').addEventListener('change', (e) => {
        config.symbol = e.target.value;
        localStorage.setItem('live_chart_symbol', config.symbol);
        updateURL();
        lastUpdateTime = null;
        userHasZoomed = false; // Reset zoom tracking
        refreshData(false);
    });

    // Lookback selector
    document.getElementById('lookback-select').addEventListener('change', (e) => {
        config.lookback = e.target.value;
        localStorage.setItem('live_chart_lookback', config.lookback);
        updateURL();
        lastUpdateTime = null;
        userHasZoomed = false; // Reset zoom tracking
        refreshData(false);
    });

    // Min USD input
    document.getElementById('min-usd-input').addEventListener('change', (e) => {
        config.minUsd = parseFloat(e.target.value) || 5000;
        localStorage.setItem('live_chart_minUsd', config.minUsd.toString());
        updateURL();
        lastUpdateTime = null;
        userHasZoomed = false; // Reset zoom tracking
        refreshData(false);
    });

    // Refresh button - resets zoom and follows live data
    document.getElementById('refresh-btn').addEventListener('click', () => {
        lastUpdateTime = null;
        userHasZoomed = false; // Reset zoom tracking to re-enable auto-follow
        refreshData(false);
    });

    // Fullscreen toggle
    document.getElementById('fullscreen-btn').addEventListener('click', () => {
        toggleFullscreen();
    });

    // Sound toggle button
    const soundToggleBtn = document.getElementById('sound-toggle-btn');
    soundToggleBtn.addEventListener('click', () => {
        // Initialize audio context on first user interaction
        if (!audioContext) {
            initAudio();
        }

        soundEnabled = !soundEnabled;
        soundToggleBtn.textContent = soundEnabled ? '🔊 Sound ON' : '🔇 Sound OFF';
        soundToggleBtn.title = soundEnabled ? 'Disable sound notifications' : 'Enable sound notifications';
    });

    // Initialize audio context on any user interaction (required by browsers)
    document.addEventListener('click', () => {
        if (!audioContext) {
            initAudio();
        }
    }, { once: true });

    // Filter checkboxes
    document.getElementById('filter-price').addEventListener('change', (e) => {
        filters.price = e.target.checked;
        updateChart();
    });

    document.getElementById('filter-market-buy').addEventListener('change', (e) => {
        filters.marketBuy = e.target.checked;
        updateChart();
    });

    document.getElementById('filter-market-sell').addEventListener('change', (e) => {
        filters.marketSell = e.target.checked;
        updateChart();
    });

    document.getElementById('filter-new-bid').addEventListener('change', (e) => {
        filters.newBid = e.target.checked;
        updateChart();
    });

    document.getElementById('filter-new-ask').addEventListener('change', (e) => {
        filters.newAsk = e.target.checked;
        updateChart();
    });

    document.getElementById('filter-bid-increase').addEventListener('change', (e) => {
        filters.bidIncrease = e.target.checked;
        updateChart();
    });

    document.getElementById('filter-ask-increase').addEventListener('change', (e) => {
        filters.askIncrease = e.target.checked;
        updateChart();
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // ESC key: close modal first, then exit fullscreen
        if (e.key === 'Escape') {
            // First check if any modal is open
            const modal = document.getElementById('event-modal');
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

// Toggle fullscreen mode for chart
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

// Show/hide loading
function showLoading(show) {
    const loading = document.getElementById('loading');
    if (loading) {
        loading.style.display = show ? 'flex' : 'none';
    }
}

// Show error toast
function showError(message) {
    const toast = document.getElementById('error-toast');
    const messageEl = document.getElementById('error-message');

    messageEl.textContent = message;
    toast.style.display = 'flex';

    setTimeout(() => {
        toast.style.display = 'none';
    }, 5000);
}

// Show event detail modal (matching chart.js styling)
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
        if (num >= 1000000) return (num / 1000000).toFixed(2) + 'M';
        if (num >= 1000) return (num / 1000).toFixed(2) + 'K';
        return num.toFixed(2);
    }

    // Format modal content (matching chart.js exactly)
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

    // Show modal
    modal.style.display = 'flex';
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (updateInterval) {
        clearInterval(updateInterval);
    }
    if (chart) {
        chart.dispose();
    }
});
