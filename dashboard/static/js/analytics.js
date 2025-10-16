// Market Analytics Calculator - Hero Metrics

/**
 * Calculate and update Hero Analytics Bar metrics
 * @param {Object} intervalData - Current interval data
 * @param {Array} whaleEvents - All whale events for this interval
 * @param {Array} priceData - Price data points
 */
function updateHeroAnalytics(intervalData, whaleEvents, priceData) {
    if (!intervalData || !whaleEvents || !priceData || priceData.length === 0) {
        document.getElementById('hero-analytics-bar').style.display = 'none';
        return;
    }

    document.getElementById('hero-analytics-bar').style.display = 'block';
    document.getElementById('analysis-info').style.display = 'flex';

    // 1. Symbol Price & Change
    const startPrice = intervalData.start_price;
    const endPrice = intervalData.end_price;
    const priceChange = ((endPrice - startPrice) / startPrice) * 100;
    const currentPrice = priceData[priceData.length - 1]?.value || endPrice;

    updateHeroMetric('price', {
        value: `$${currentPrice.toFixed(4)}`,
        change: `${priceChange >= 0 ? '+' : ''}${priceChange.toFixed(2)}%`,
        changeDirection: priceChange >= 0 ? 'up' : 'down',
        sentiment: priceChange > 0 ? 'positive' : priceChange < 0 ? 'negative' : 'neutral'
    });

    // 2. Price Change Percentage
    const changeAbsolute = Math.abs(priceChange);
    let changeBadge = 'Neutral';
    let changeSentiment = 'neutral';

    if (changeAbsolute > 5) {
        changeBadge = 'Extreme';
        changeSentiment = priceChange > 0 ? 'positive' : 'negative';
    } else if (changeAbsolute > 2) {
        changeBadge = 'High';
        changeSentiment = priceChange > 0 ? 'positive' : 'negative';
    } else if (changeAbsolute > 0.5) {
        changeBadge = 'Moderate';
        changeSentiment = priceChange > 0 ? 'positive' : 'negative';
    } else if (changeAbsolute > 0.1) {
        changeBadge = 'Low';
    }

    updateHeroMetric('change', {
        value: `${priceChange >= 0 ? '+' : ''}${priceChange.toFixed(2)}%`,
        badge: changeBadge,
        sentiment: changeSentiment
    });

    // 3. Market Sentiment Score (0-100)
    const sentiment = calculateMarketSentiment(whaleEvents, priceChange);
    updateHeroMetric('sentiment', {
        value: sentiment.score.toString(),
        badge: sentiment.label,
        sentiment: sentiment.sentiment
    });

    // 4. Whale Pressure (Net buying/selling)
    const pressure = calculateWhalePressure(whaleEvents);
    updateHeroMetric('pressure', {
        value: pressure.value > 0 ? `+${pressure.value}` : pressure.value.toString(),
        badge: pressure.label,
        sentiment: pressure.sentiment
    });

    // 5. Liquidity Delta
    const liquidity = calculateLiquidityDelta(whaleEvents);
    updateHeroMetric('liquidity', {
        value: formatLargeNumber(liquidity.value),
        change: `${liquidity.change >= 0 ? '+' : ''}${liquidity.change.toFixed(0)}%`,
        changeDirection: liquidity.change >= 0 ? 'up' : 'down',
        sentiment: liquidity.change > 0 ? 'positive' : liquidity.change < 0 ? 'negative' : 'neutral'
    });

    // 6. Volatility Index
    const volatility = calculateVolatility(priceData);
    updateHeroMetric('volatility', {
        value: volatility.score.toFixed(1),
        badge: volatility.label,
        sentiment: volatility.sentiment
    });
}

/**
 * Calculate market sentiment from whale activity and price action
 */
function calculateMarketSentiment(whaleEvents, priceChange) {
    let score = 50; // Start neutral

    // Weight by event type
    const weights = {
        'market_buy': 8,
        'new_bid': 5,
        'increase_bid': 2,
        'decrease_ask': 3,
        'market_sell': -8,
        'new_ask': -5,
        'increase_ask': -2,
        'decrease_bid': -3
    };

    whaleEvents.forEach(event => {
        const eventType = event.event_type;
        const side = event.side;
        let weight = 0;

        if (eventType === 'market_buy') weight = weights.market_buy;
        else if (eventType === 'market_sell') weight = weights.market_sell;
        else if (eventType === 'increase') {
            weight = side === 'bid' ? weights.increase_bid : weights.increase_ask;
        } else if (eventType === 'decrease') {
            weight = side === 'bid' ? weights.decrease_bid : weights.decrease_ask;
        } else if (eventType.includes('bid')) {
            weight = weights.new_bid;
        } else if (eventType.includes('ask')) {
            weight = weights.new_ask;
        }

        // Scale by USD value
        const usdScale = Math.min(event.usd_value / 100000, 3); // Cap at 3x
        score += weight * usdScale;
    });

    // Factor in price action
    score += priceChange * 5;

    // Clamp to 0-100
    score = Math.max(0, Math.min(100, score));

    let label, sentiment;
    if (score >= 75) {
        label = 'Very Bullish';
        sentiment = 'positive';
    } else if (score >= 60) {
        label = 'Bullish';
        sentiment = 'positive';
    } else if (score >= 40) {
        label = 'Neutral';
        sentiment = 'neutral';
    } else if (score >= 25) {
        label = 'Bearish';
        sentiment = 'negative';
    } else {
        label = 'Very Bearish';
        sentiment = 'negative';
    }

    return { score: Math.round(score), label, sentiment };
}

/**
 * Calculate whale buying/selling pressure
 */
function calculateWhalePressure(whaleEvents) {
    let buyPressure = 0;
    let sellPressure = 0;

    whaleEvents.forEach(event => {
        const value = event.usd_value;
        const eventType = event.event_type;
        const side = event.side;

        if (eventType === 'market_buy') {
            buyPressure += value;
        } else if (eventType === 'market_sell') {
            sellPressure += value;
        } else if (eventType === 'increase') {
            if (side === 'bid') buyPressure += value * 0.5;
            else sellPressure += value * 0.5;
        } else if (eventType.includes('bid') && !eventType.includes('decrease')) {
            buyPressure += value * 0.7;
        } else if (eventType.includes('ask') && !eventType.includes('decrease')) {
            sellPressure += value * 0.7;
        }
    });

    const netPressure = buyPressure - sellPressure;
    const totalPressure = buyPressure + sellPressure;
    const pressureRatio = totalPressure > 0 ? (netPressure / totalPressure) * 100 : 0;

    let label, sentiment;
    if (pressureRatio > 30) {
        label = 'Strong Buy';
        sentiment = 'positive';
    } else if (pressureRatio > 10) {
        label = 'Buy';
        sentiment = 'positive';
    } else if (pressureRatio > -10) {
        label = 'Balanced';
        sentiment = 'neutral';
    } else if (pressureRatio > -30) {
        label = 'Sell';
        sentiment = 'negative';
    } else {
        label = 'Strong Sell';
        sentiment = 'negative';
    }

    return {
        value: Math.round(pressureRatio),
        label,
        sentiment
    };
}

/**
 * Calculate liquidity delta from order book changes
 */
function calculateLiquidityDelta(whaleEvents) {
    let addedLiquidity = 0;
    let removedLiquidity = 0;

    whaleEvents.forEach(event => {
        const value = event.usd_value;
        const eventType = event.event_type;

        if (eventType.includes('increase') || (eventType.includes('new') && !eventType.includes('market'))) {
            addedLiquidity += value;
        } else if (eventType.includes('decrease') || eventType.includes('market')) {
            removedLiquidity += value;
        }
    });

    const netLiquidity = addedLiquidity - removedLiquidity;
    const changePercent = addedLiquidity > 0 ? ((netLiquidity) / addedLiquidity) * 100 : 0;

    return {
        value: netLiquidity,
        change: changePercent
    };
}

/**
 * Calculate volatility index from price movements
 */
function calculateVolatility(priceData) {
    if (priceData.length < 2) {
        return { score: 0, label: 'N/A', sentiment: 'neutral' };
    }

    // Calculate price changes
    const changes = [];
    for (let i = 1; i < priceData.length; i++) {
        const change = Math.abs((priceData[i].value - priceData[i-1].value) / priceData[i-1].value) * 100;
        changes.push(change);
    }

    // Standard deviation of changes
    const mean = changes.reduce((a, b) => a + b, 0) / changes.length;
    const variance = changes.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / changes.length;
    const volatility = Math.sqrt(variance) * 100; // Scale up

    let label, sentiment;
    if (volatility > 50) {
        label = 'Extreme';
        sentiment = 'negative';
    } else if (volatility > 20) {
        label = 'High';
        sentiment = 'negative';
    } else if (volatility > 10) {
        label = 'Moderate';
        sentiment = 'neutral';
    } else if (volatility > 5) {
        label = 'Low';
        sentiment = 'positive';
    } else {
        label = 'Very Low';
        sentiment = 'positive';
    }

    return {
        score: volatility,
        label,
        sentiment
    };
}

/**
 * Update a specific hero metric
 */
function updateHeroMetric(metricId, data) {
    const metric = document.getElementById(`hero-${metricId}`);
    if (!metric) return;

    // Update value
    if (data.value !== undefined) {
        const valueEl = document.getElementById(`hero-${metricId}-value`);
        if (valueEl) {
            valueEl.textContent = data.value;
            valueEl.classList.add('counting');
            setTimeout(() => valueEl.classList.remove('counting'), 500);
        }
    }

    // Update change
    if (data.change !== undefined) {
        const changeEl = document.getElementById(`hero-${metricId}-change`);
        if (changeEl) {
            const iconEl = changeEl.querySelector('.hero-metric-change-icon');
            const textEl = changeEl.querySelector('span:last-child');
            if (iconEl && textEl) {
                iconEl.textContent = data.changeDirection === 'up' ? '▲' : '▼';
                textEl.textContent = data.change;
                changeEl.className = `hero-metric-change ${data.changeDirection}`;
            }
        }
    }

    // Update badge
    if (data.badge !== undefined) {
        const badgeEl = document.getElementById(`hero-${metricId}-badge`);
        if (badgeEl) {
            badgeEl.textContent = data.badge;
            badgeEl.className = 'hero-metric-badge';
            if (data.sentiment) {
                badgeEl.classList.add(data.sentiment === 'positive' ? 'bullish' :
                                      data.sentiment === 'negative' ? 'bearish' : 'neutral');
            }
        }
    }

    // Update metric sentiment class
    if (data.sentiment !== undefined) {
        metric.className = `hero-metric ${data.sentiment}`;
    }
}

/**
 * Format large numbers (K, M, B)
 */
function formatLargeNumber(num) {
    const abs = Math.abs(num);
    const sign = num < 0 ? '-' : '';

    if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
    if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(2)}M`;
    if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(1)}K`;
    return `${sign}$${abs.toFixed(0)}`;
}

/**
 * Update enhanced stats summary panel
 */
function updateEnhancedStats(intervalData, whaleEvents) {
    if (!intervalData || !whaleEvents) return;

    // Whale Count (unique large events)
    const whaleCount = whaleEvents.filter(e => e.usd_value > 50000).length;
    document.getElementById('stat-whale-count').textContent = whaleCount;

    // Order Flow Imbalance
    const buyEvents = whaleEvents.filter(e =>
        e.event_type === 'market_buy' || (e.event_type.includes('bid') && !e.event_type.includes('decrease'))
    );
    const sellEvents = whaleEvents.filter(e =>
        e.event_type === 'market_sell' || (e.event_type.includes('ask') && !e.event_type.includes('decrease'))
    );

    const buyVolume = buyEvents.reduce((sum, e) => sum + e.usd_value, 0);
    const sellVolume = sellEvents.reduce((sum, e) => sum + e.usd_value, 0);
    const imbalance = buyVolume + sellVolume > 0 ? ((buyVolume - sellVolume) / (buyVolume + sellVolume)) * 100 : 0;

    const imbalanceEl = document.getElementById('stat-imbalance');
    imbalanceEl.textContent = `${imbalance >= 0 ? '+' : ''}${imbalance.toFixed(0)}%`;
    imbalanceEl.className = 'stat-value';
    if (imbalance > 20) imbalanceEl.classList.add('stat-bullish');
    else if (imbalance < -20) imbalanceEl.classList.add('stat-bearish');

    // Event Density (events per minute)
    const duration = (new Date(intervalData.end_time) - new Date(intervalData.start_time)) / 1000 / 60; // minutes
    const density = whaleEvents.length / duration;
    document.getElementById('stat-density').textContent = `${density.toFixed(1)}/min`;

    // Dominant Side
    const dominantEl = document.getElementById('stat-dominant');
    if (buyVolume > sellVolume * 1.5) {
        dominantEl.textContent = 'Bullish';
        dominantEl.className = 'stat-value stat-bullish';
    } else if (sellVolume > buyVolume * 1.5) {
        dominantEl.textContent = 'Bearish';
        dominantEl.className = 'stat-value stat-bearish';
    } else {
        dominantEl.textContent = 'Neutral';
        dominantEl.className = 'stat-value';
    }

    // Impact Score (weighted by USD and event type)
    let impactScore = 0;
    whaleEvents.forEach(e => {
        const baseScore = e.usd_value / 10000; // $10k = 1 point
        const multiplier = e.event_type.includes('market') ? 2 : 1;
        impactScore += baseScore * multiplier;
    });
    document.getElementById('stat-impact').textContent = Math.round(impactScore);

    // Total Volume
    const totalVolume = whaleEvents.reduce((sum, e) => sum + e.usd_value, 0);
    document.getElementById('stat-volume').textContent = formatLargeNumber(totalVolume);
}

/**
 * Toggle context card expansion
 */
function toggleContextCard(cardType) {
    const card = document.getElementById(`${cardType}-context-card`);
    if (card) {
        card.classList.toggle('expanded');
    }
}

/**
 * Update market context cards
 */
function updateContextCards(intervalData, whaleEvents, priceData) {
    if (!intervalData || !whaleEvents || !priceData) {
        document.getElementById('context-cards-container').style.display = 'none';
        return;
    }

    document.getElementById('context-cards-container').style.display = 'flex';

    // 1. Spike Context Card
    updateSpikeContext(intervalData, whaleEvents, priceData);

    // 2. Whale Behavior Card
    updateWhaleContext(whaleEvents);

    // 3. Market Structure Card
    updateStructureContext(intervalData, whaleEvents, priceData);
}

/**
 * Update Spike Context Card
 */
function updateSpikeContext(intervalData, whaleEvents, priceData) {
    const priceChange = Math.abs(((intervalData.end_price - intervalData.start_price) / intervalData.start_price) * 100);

    // Severity badge
    const severityEl = document.getElementById('spike-severity');
    if (priceChange > 5) {
        severityEl.textContent = 'Extreme';
        severityEl.className = 'context-card-badge high';
    } else if (priceChange > 2) {
        severityEl.textContent = 'High';
        severityEl.className = 'context-card-badge high';
    } else if (priceChange > 0.5) {
        severityEl.textContent = 'Medium';
        severityEl.className = 'context-card-badge medium';
    } else {
        severityEl.textContent = 'Low';
        severityEl.className = 'context-card-badge low';
    }

    // Trigger Analysis
    const marketOrders = whaleEvents.filter(e => e.event_type.includes('market'));
    const largeOrders = whaleEvents.filter(e => e.usd_value > 100000);

    let trigger = 'Normal market activity';
    if (marketOrders.length > 10) {
        trigger = `<strong>Market order cascade</strong> - ${marketOrders.length} aggressive orders executed rapidly`;
    } else if (largeOrders.length > 5) {
        trigger = `<strong>Large order placement</strong> - ${largeOrders.length} whale orders placed`;
    } else if (whaleEvents.length > 50) {
        trigger = `<strong>High activity spike</strong> - ${whaleEvents.length} events in interval`;
    }
    document.getElementById('spike-trigger').innerHTML = trigger;

    // Pattern Recognition
    const buyVolume = whaleEvents.filter(e => e.event_type === 'market_buy' || e.event_type.includes('bid')).reduce((sum, e) => sum + e.usd_value, 0);
    const sellVolume = whaleEvents.filter(e => e.event_type === 'market_sell' || e.event_type.includes('ask')).reduce((sum, e) => sum + e.usd_value, 0);

    let pattern = 'Balanced market activity';
    if (buyVolume > sellVolume * 2) {
        pattern = '<strong>Accumulation pattern</strong> - Strong buying pressure detected';
    } else if (sellVolume > buyVolume * 2) {
        pattern = '<strong>Distribution pattern</strong> - Strong selling pressure detected';
    } else if (priceChange > 2) {
        pattern = '<strong>Volatility breakout</strong> - Large price movement with mixed flows';
    }
    document.getElementById('spike-pattern').innerHTML = pattern;

    // Follow-through Score
    const followThrough = Math.min(100, (whaleEvents.length / 10) * priceChange);
    let followText = 'Weak follow-through - spike may reverse';
    if (followThrough > 70) {
        followText = '<strong>Strong follow-through</strong> - sustained movement likely';
    } else if (followThrough > 40) {
        followText = '<strong>Moderate follow-through</strong> - watch for confirmation';
    }
    document.getElementById('spike-followthrough').innerHTML = followText;
}

/**
 * Update Whale Behavior Card
 */
function updateWhaleContext(whaleEvents) {
    // Activity level badge
    const activityEl = document.getElementById('whale-activity');
    if (whaleEvents.length > 50) {
        activityEl.textContent = 'Very High';
        activityEl.className = 'context-card-badge high';
    } else if (whaleEvents.length > 30) {
        activityEl.textContent = 'High';
        activityEl.className = 'context-card-badge medium';
    } else if (whaleEvents.length > 15) {
        activityEl.textContent = 'Medium';
        activityEl.className = 'context-card-badge medium';
    } else {
        activityEl.textContent = 'Low';
        activityEl.className = 'context-card-badge low';
    }

    // Top whale action
    const sortedBySize = [...whaleEvents].sort((a, b) => b.usd_value - a.usd_value);
    const topWhale = sortedBySize[0];

    if (topWhale) {
        const action = topWhale.event_type === 'market_buy' ? 'Aggressive Buy' :
                      topWhale.event_type === 'market_sell' ? 'Aggressive Sell' :
                      topWhale.event_type.includes('bid') ? 'Bid Placement' :
                      'Ask Placement';
        document.getElementById('whale-top-action').innerHTML =
            `<strong>${formatLargeNumber(topWhale.usd_value)}</strong> ${action} at $${topWhale.price.toFixed(4)}`;
    }

    // Unusual patterns
    const timeGaps = [];
    for (let i = 1; i < whaleEvents.length; i++) {
        const gap = new Date(whaleEvents[i].time) - new Date(whaleEvents[i-1].time);
        timeGaps.push(gap);
    }
    const avgGap = timeGaps.reduce((a, b) => a + b, 0) / timeGaps.length / 1000; // seconds

    let patternsText = 'Normal distribution of whale activity';
    if (avgGap < 2) {
        patternsText = '<strong>Rapid-fire orders</strong> - Coordinated or algorithmic activity detected';
    } else if (whaleEvents.filter(e => e.usd_value > 200000).length > 3) {
        patternsText = '<strong>Multiple mega-whales</strong> - Institutional-level activity';
    }
    document.getElementById('whale-patterns').innerHTML = patternsText;

    // Coordination score
    const buyEvents = whaleEvents.filter(e => e.event_type.includes('buy') || e.event_type.includes('bid'));
    const sellEvents = whaleEvents.filter(e => e.event_type.includes('sell') || e.event_type.includes('ask'));

    const buyConcentration = buyEvents.length / whaleEvents.length;
    const coordinationScore = Math.abs(buyConcentration - 0.5) * 200; // 0-100

    let coordText = 'Mixed activity - No clear coordination';
    if (coordinationScore > 70) {
        coordText = `<strong>High coordination (${Math.round(coordinationScore)}%)</strong> - Whales moving in same direction`;
    } else if (coordinationScore > 40) {
        coordText = `<strong>Moderate coordination (${Math.round(coordinationScore)}%)</strong> - Some directional bias`;
    }
    document.getElementById('whale-coordination').innerHTML = coordText;
}

/**
 * Update Market Structure Card
 */
function updateStructureContext(intervalData, whaleEvents, priceData) {
    // Quality badge
    const qualityEl = document.getElementById('structure-quality');
    const liquidityScore = whaleEvents.length * 2;
    if (liquidityScore > 80) {
        qualityEl.textContent = 'Excellent';
        qualityEl.className = 'context-card-badge low';
    } else if (liquidityScore > 40) {
        qualityEl.textContent = 'Good';
        qualityEl.className = 'context-card-badge medium';
    } else {
        qualityEl.textContent = 'Fair';
        qualityEl.className = 'context-card-badge high';
    }

    // Key levels
    const startPrice = intervalData.start_price;
    const endPrice = intervalData.end_price;
    const highPrice = Math.max(startPrice, endPrice);
    const lowPrice = Math.min(startPrice, endPrice);

    document.getElementById('structure-levels').innerHTML =
        `Support: <strong>$${lowPrice.toFixed(4)}</strong> | Resistance: <strong>$${highPrice.toFixed(4)}</strong>`;

    // Order book imbalance
    const bidVolume = whaleEvents.filter(e => e.side === 'bid').reduce((sum, e) => sum + e.usd_value, 0);
    const askVolume = whaleEvents.filter(e => e.side === 'ask').reduce((sum, e) => sum + e.usd_value, 0);
    const imbalance = bidVolume + askVolume > 0 ? ((bidVolume - askVolume) / (bidVolume + askVolume)) * 100 : 0;

    let imbalanceText = 'Balanced';
    if (imbalance > 30) {
        imbalanceText = `<strong>+${imbalance.toFixed(0)}% Bid side</strong> - Strong support`;
    } else if (imbalance < -30) {
        imbalanceText = `<strong>${imbalance.toFixed(0)}% Ask side</strong> - Strong resistance`;
    } else {
        imbalanceText = `<strong>${imbalance >= 0 ? '+' : ''}${imbalance.toFixed(0)}%</strong> - Relatively balanced`;
    }
    document.getElementById('structure-imbalance').innerHTML = imbalanceText;

    // Liquidity quality
    const avgOrderSize = whaleEvents.reduce((sum, e) => sum + e.usd_value, 0) / whaleEvents.length;
    let liquidityText = 'Average liquidity depth';
    if (avgOrderSize > 150000) {
        liquidityText = `<strong>Deep liquidity</strong> - Avg order: ${formatLargeNumber(avgOrderSize)}`;
    } else if (avgOrderSize > 75000) {
        liquidityText = `<strong>Good liquidity</strong> - Avg order: ${formatLargeNumber(avgOrderSize)}`;
    } else {
        liquidityText = `<strong>Thin liquidity</strong> - Avg order: ${formatLargeNumber(avgOrderSize)}`;
    }
    document.getElementById('structure-liquidity').innerHTML = liquidityText;
}

/**
 * Animate number counter effect
 */
function animateCounter(element, start, end, duration = 500) {
    const range = end - start;
    const increment = range / (duration / 16);
    let current = start;

    const timer = setInterval(() => {
        current += increment;
        if ((increment > 0 && current >= end) || (increment < 0 && current <= end)) {
            current = end;
            clearInterval(timer);
        }
        element.textContent = Math.round(current).toString();
    }, 16);
}
