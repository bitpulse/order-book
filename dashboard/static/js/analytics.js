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
    const startPrice = intervalData.start_price;
    const endPrice = intervalData.end_price;
    const priceChange = ((endPrice - startPrice) / startPrice) * 100;
    const absPriceChange = Math.abs(priceChange);

    // Severity badge - use standardized thresholds
    const severity = getPriceChangeSeverity(priceChange);
    const severityEl = document.getElementById('spike-severity');
    severityEl.textContent = severity.level;
    severityEl.className = `context-card-badge ${severity.badge}`;
    severityEl.title = `${absPriceChange.toFixed(2)}% price change (threshold: ${priceChange >= 0 ? '+' : ''}${absPriceChange.toFixed(2)}%)`;

    // Trigger Analysis - use standardized thresholds
    const marketOrders = whaleEvents.filter(e => e.event_type.includes('market'));
    const largeOrders = whaleEvents.filter(e => e.usd_value >= ANALYTICS_CONFIG.THRESHOLDS.LARGE_ORDER);
    const megaWhales = whaleEvents.filter(e => e.usd_value >= ANALYTICS_CONFIG.THRESHOLDS.MEGA_WHALE);

    let trigger = 'Normal market activity';
    let triggerCalc = {
        formula: 'Event pattern analysis',
        inputs: {
            'Market Orders': `${marketOrders.length} orders`,
            'Large Orders (>$100K)': `${largeOrders.length} orders`,
            'Total Events': `${whaleEvents.length} events`
        }
    };

    if (marketOrders.length >= ANALYTICS_CONFIG.PATTERN_DETECTION.CASCADE_ORDERS) {
        trigger = `<strong>Market order cascade</strong> - ${marketOrders.length} aggressive orders executed rapidly`;
        triggerCalc.interpretation = `${marketOrders.length} market orders exceeds cascade threshold (${ANALYTICS_CONFIG.PATTERN_DETECTION.CASCADE_ORDERS}+). Indicates aggressive execution.`;
    } else if (megaWhales.length >= 3) {
        const totalMegaVolume = megaWhales.reduce((sum, e) => sum + e.usd_value, 0);
        trigger = `<strong>Mega whale activity</strong> - ${megaWhales.length} orders over $${ANALYTICS_CONFIG.THRESHOLDS.MEGA_WHALE / 1000000}M (total: ${formatLargeNumber(totalMegaVolume)})`;
        triggerCalc.interpretation = `${megaWhales.length} mega-whale orders (>$${ANALYTICS_CONFIG.THRESHOLDS.MEGA_WHALE/1000000}M each) detected. Exceptional institutional activity.`;
    } else if (largeOrders.length >= ANALYTICS_CONFIG.PATTERN_DETECTION.LARGE_WHALE_GROUP) {
        trigger = `<strong>Large order placement</strong> - ${largeOrders.length} whale orders placed`;
        triggerCalc.interpretation = `${largeOrders.length} large orders exceeds whale group threshold (${ANALYTICS_CONFIG.PATTERN_DETECTION.LARGE_WHALE_GROUP}+). Coordinated whale activity.`;
    } else if (whaleEvents.length >= ANALYTICS_CONFIG.PATTERN_DETECTION.HIGH_ACTIVITY_SPIKE) {
        trigger = `<strong>High activity spike</strong> - ${whaleEvents.length} events in interval`;
        triggerCalc.interpretation = `${whaleEvents.length} events exceeds high-activity threshold (${ANALYTICS_CONFIG.PATTERN_DETECTION.HIGH_ACTIVITY_SPIKE}+). Unusual market attention.`;
    } else {
        triggerCalc.interpretation = `Activity levels within normal ranges. No exceptional patterns detected.`;
    }

    document.getElementById('spike-trigger').innerHTML = trigger;
    document.getElementById('spike-trigger').setAttribute('data-calc', JSON.stringify(triggerCalc));

    // Pattern Recognition - use standardized dominance thresholds
    const buyEvents = whaleEvents.filter(e => e.event_type === 'market_buy' || e.event_type.includes('bid'));
    const sellEvents = whaleEvents.filter(e => e.event_type === 'market_sell' || e.event_type.includes('ask'));
    const buyVolume = buyEvents.reduce((sum, e) => sum + e.usd_value, 0);
    const sellVolume = sellEvents.reduce((sum, e) => sum + e.usd_value, 0);
    const totalVolume = buyVolume + sellVolume;

    let pattern = 'Balanced market activity';
    let patternCalc = {
        formula: 'Buy Volume / Sell Volume',
        inputs: {
            'Buy Volume': formatLargeNumber(buyVolume),
            'Sell Volume': formatLargeNumber(sellVolume),
            'Buy Events': `${buyEvents.length} orders`,
            'Sell Events': `${sellEvents.length} orders`
        }
    };

    if (sellVolume > 0) {
        const buyRatio = buyVolume / sellVolume;
        patternCalc.steps = [`Ratio = ${formatLargeNumber(buyVolume)} / ${formatLargeNumber(sellVolume)} = ${buyRatio.toFixed(2)}x`];

        if (buyRatio >= ANALYTICS_CONFIG.DOMINANCE.STRONG) {
            pattern = `<strong>Accumulation pattern</strong> - Strong buying pressure (${buyRatio.toFixed(1)}x)`;
            patternCalc.interpretation = `Buy volume is ${buyRatio.toFixed(1)}x sell volume. Strong dominance (threshold: ${ANALYTICS_CONFIG.DOMINANCE.STRONG}x+). Bullish accumulation pattern.`;
        } else if (buyVolume / sellVolume >= ANALYTICS_CONFIG.DOMINANCE.MODERATE) {
            pattern = `<strong>Buying pressure</strong> - Moderate accumulation (${buyRatio.toFixed(1)}x)`;
            patternCalc.interpretation = `Buy volume is ${buyRatio.toFixed(1)}x sell volume. Moderate bullish bias.`;
        }
    }

    if (buyVolume > 0) {
        const sellRatio = sellVolume / buyVolume;
        if (sellRatio >= ANALYTICS_CONFIG.DOMINANCE.STRONG) {
            pattern = `<strong>Distribution pattern</strong> - Strong selling pressure (${sellRatio.toFixed(1)}x)`;
            patternCalc.steps = [`Ratio = ${formatLargeNumber(sellVolume)} / ${formatLargeNumber(buyVolume)} = ${sellRatio.toFixed(2)}x`];
            patternCalc.interpretation = `Sell volume is ${sellRatio.toFixed(1)}x buy volume. Strong dominance (threshold: ${ANALYTICS_CONFIG.DOMINANCE.STRONG}x+). Bearish distribution pattern.`;
        } else if (sellRatio >= ANALYTICS_CONFIG.DOMINANCE.MODERATE) {
            pattern = `<strong>Selling pressure</strong> - Moderate distribution (${sellRatio.toFixed(1)}x)`;
            patternCalc.steps = [`Ratio = ${formatLargeNumber(sellVolume)} / ${formatLargeNumber(buyVolume)} = ${sellRatio.toFixed(2)}x`];
            patternCalc.interpretation = `Sell volume is ${sellRatio.toFixed(1)}x buy volume. Moderate bearish bias.`;
        }
    }

    if (absPriceChange >= ANALYTICS_CONFIG.PRICE_CHANGE.HIGH && Math.abs(buyVolume - sellVolume) / totalVolume < 0.3) {
        pattern = '<strong>Volatility breakout</strong> - Large price movement with mixed flows';
        patternCalc.interpretation = `${absPriceChange.toFixed(2)}% price change but volumes nearly balanced. High volatility, unclear direction.`;
    }

    if (totalVolume === 0) {
        pattern = 'No significant volume activity';
        patternCalc.interpretation = 'Minimal whale activity detected during interval.';
    }

    document.getElementById('spike-pattern').innerHTML = pattern;
    document.getElementById('spike-pattern').setAttribute('data-calc', JSON.stringify(patternCalc));

    // Follow-through Score - improved calculation
    // Use combination of price persistence and volume continuation
    const followScore = Math.min(100, (whaleEvents.length / ANALYTICS_CONFIG.ACTIVITY.VERY_HIGH) * Math.min(absPriceChange * 20, 100));
    const followLevel = getFollowThroughLevel(followScore);

    let followText = `<strong>${followLevel.level} follow-through</strong> - ${followLevel.description}`;
    const followCalc = {
        formula: '(Event Count / Activity Threshold) × Price Change Impact',
        inputs: {
            'Event Count': `${whaleEvents.length} events`,
            'Activity Threshold': `${ANALYTICS_CONFIG.ACTIVITY.VERY_HIGH} (very high)`,
            'Price Change': `${absPriceChange.toFixed(2)}%`
        },
        steps: [
            `Activity ratio = ${whaleEvents.length} / ${ANALYTICS_CONFIG.ACTIVITY.VERY_HIGH} = ${(whaleEvents.length / ANALYTICS_CONFIG.ACTIVITY.VERY_HIGH).toFixed(2)}`,
            `Price impact = min(${absPriceChange.toFixed(2)}% × 20, 100) = ${Math.min(absPriceChange * 20, 100).toFixed(1)}`,
            `Score = ${(whaleEvents.length / ANALYTICS_CONFIG.ACTIVITY.VERY_HIGH).toFixed(2)} × ${Math.min(absPriceChange * 20, 100).toFixed(1)} = ${followScore.toFixed(1)}%`
        ],
        result: `${followScore.toFixed(0)}% follow-through score`,
        interpretation: `Score ${followScore.toFixed(0)}% indicates ${followLevel.level.toLowerCase()} follow-through. ${followLevel.description}.`
    };

    document.getElementById('spike-followthrough').innerHTML = followText;
    document.getElementById('spike-followthrough').setAttribute('data-calc', JSON.stringify(followCalc));
}

/**
 * Update Whale Behavior Card
 */
function updateWhaleContext(whaleEvents) {
    // Activity level badge - use standardized thresholds
    const activity = getActivityLevel(whaleEvents.length);
    const activityEl = document.getElementById('whale-activity');
    activityEl.textContent = activity.level;
    activityEl.className = `context-card-badge ${activity.badge}`;
    activityEl.title = `${whaleEvents.length} whale events (thresholds: Low<${ANALYTICS_CONFIG.ACTIVITY.MEDIUM}, Medium<${ANALYTICS_CONFIG.ACTIVITY.HIGH}, High<${ANALYTICS_CONFIG.ACTIVITY.VERY_HIGH}, Very High≥${ANALYTICS_CONFIG.ACTIVITY.VERY_HIGH})`;

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

    // Coordination score - clearer calculation
    const buyEvents = whaleEvents.filter(e => e.event_type.includes('buy') || e.event_type.includes('bid'));
    const sellEvents = whaleEvents.filter(e => e.event_type.includes('sell') || e.event_type.includes('ask'));

    const buyPct = whaleEvents.length > 0 ? (buyEvents.length / whaleEvents.length) * 100 : 50;
    const sellPct = 100 - buyPct;
    const imbalance = Math.abs(buyPct - sellPct);

    const coordLevel = getCoordinationLevel(imbalance);
    let coordText = `<strong>${coordLevel.level} coordination (${imbalance.toFixed(0)}% imbalance)</strong> - ${coordLevel.description}`;

    const coordCalc = {
        formula: '|Buy% - Sell%|',
        inputs: {
            'Buy Events': `${buyEvents.length} (${buyPct.toFixed(1)}%)`,
            'Sell Events': `${sellEvents.length} (${sellPct.toFixed(1)}%)`,
            'Total Events': `${whaleEvents.length}`
        },
        steps: [
            `Buy% = ${buyEvents.length} / ${whaleEvents.length} × 100 = ${buyPct.toFixed(1)}%`,
            `Sell% = 100% - ${buyPct.toFixed(1)}% = ${sellPct.toFixed(1)}%`,
            `Imbalance = |${buyPct.toFixed(1)}% - ${sellPct.toFixed(1)}%| = ${imbalance.toFixed(1)}%`
        ],
        result: `${imbalance.toFixed(0)}% directional imbalance`,
        interpretation: `${imbalance.toFixed(0)}% imbalance toward ${buyPct > sellPct ? 'buying' : 'selling'}. ${coordLevel.description}. Threshold: High≥${ANALYTICS_CONFIG.COORDINATION.HIGH}%, Moderate≥${ANALYTICS_CONFIG.COORDINATION.MODERATE}%.`,
        baseline: `Balanced market: 0-${ANALYTICS_CONFIG.COORDINATION.MODERATE}% imbalance. Current: ${coordLevel.level}`
    };

    document.getElementById('whale-coordination').innerHTML = coordText;
    document.getElementById('whale-coordination').setAttribute('data-calc', JSON.stringify(coordCalc));
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

    // Liquidity quality - use standardized thresholds
    const totalOrderValue = whaleEvents.reduce((sum, e) => sum + e.usd_value, 0);
    const avgOrderSize = whaleEvents.length > 0 ? totalOrderValue / whaleEvents.length : 0;

    const liquidity = getLiquidityQuality(avgOrderSize);
    let liquidityText = `<strong>${liquidity.level}</strong> - Avg order: ${formatLargeNumber(avgOrderSize)}`;

    const liquidityCalc = {
        formula: 'Total Volume / Event Count',
        inputs: {
            'Total Volume': formatLargeNumber(totalOrderValue),
            'Event Count': `${whaleEvents.length} orders`
        },
        steps: [
            `Avg = ${formatLargeNumber(totalOrderValue)} / ${whaleEvents.length} = ${formatLargeNumber(avgOrderSize)}`
        ],
        result: `${formatLargeNumber(avgOrderSize)} average order size`,
        interpretation: `${liquidity.description}. Thresholds: Deep≥$${ANALYTICS_CONFIG.LIQUIDITY.DEEP/1000}K, Good≥$${ANALYTICS_CONFIG.LIQUIDITY.GOOD/1000}K, Average≥$${ANALYTICS_CONFIG.LIQUIDITY.AVERAGE/1000}K, Thin<$${ANALYTICS_CONFIG.LIQUIDITY.AVERAGE/1000}K.`,
        baseline: `Professional/institutional orders typically >$${ANALYTICS_CONFIG.THRESHOLDS.INSTITUTIONAL/1000}K. Current: ${liquidity.level}`
    };

    document.getElementById('structure-liquidity').innerHTML = liquidityText;
    document.getElementById('structure-liquidity').setAttribute('data-calc', JSON.stringify(liquidityCalc));
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

/**
 * Initialize calculation explanation tooltips
 * Adds click handlers to show calculation breakdowns
 */
function initializeCalculationTooltips() {
    // Add click handlers to all elements with data-calc attribute
    document.addEventListener('click', (e) => {
        const target = e.target.closest('[data-calc]');
        if (!target) return;

        const calcData = target.getAttribute('data-calc');
        if (!calcData) return;

        try {
            const calculation = JSON.parse(calcData);
            showCalculationModal(target.textContent, calculation);
        } catch (err) {
            console.error('Failed to parse calculation data:', err);
        }
    });

    // Add visual indicator that elements are clickable
    const style = document.createElement('style');
    style.textContent = `
        [data-calc] {
            cursor: help;
            position: relative;
        }
        [data-calc]::after {
            content: '🔍';
            font-size: 0.7em;
            opacity: 0.4;
            margin-left: 0.3em;
            transition: opacity 0.2s;
        }
        [data-calc]:hover::after {
            opacity: 0.8;
        }
    `;
    document.head.appendChild(style);
}

/**
 * Show calculation breakdown in a modal/tooltip
 * @param {string} metricName - Name of the metric
 * @param {object} calculation - Calculation details object
 */
function showCalculationModal(metricName, calculation) {
    // Remove existing modal if any
    const existingModal = document.getElementById('calc-modal');
    if (existingModal) {
        existingModal.remove();
    }

    // Create modal
    const modal = document.createElement('div');
    modal.id = 'calc-modal';
    modal.style.cssText = `
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        background: linear-gradient(135deg, rgba(20, 20, 20, 0.98), rgba(15, 15, 15, 0.98));
        border: 1px solid rgba(0, 194, 255, 0.3);
        border-radius: 12px;
        padding: 1.5rem;
        max-width: 600px;
        max-height: 80vh;
        overflow-y: auto;
        z-index: 10000;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.8), 0 0 0 1px rgba(0, 194, 255, 0.2);
        backdrop-filter: blur(20px);
    `;

    let html = `
        <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 1rem;">
            <h3 style="margin: 0; color: #00d9ff; font-size: 1.1rem;">📊 How is this calculated?</h3>
            <button id="close-calc-modal" style="background: none; border: none; color: #fff; font-size: 1.5rem; cursor: pointer; padding: 0; line-height: 1;">&times;</button>
        </div>
        <div style="margin-bottom: 1rem; padding-bottom: 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.1);">
            <strong style="color: #00ffa3;">Metric:</strong> <span style="color: #fff;">${metricName}</span>
        </div>
    `;

    if (calculation.formula) {
        html += `<div style="margin-bottom: 1rem;">
            <strong style="color: #00d9ff;">📐 Formula:</strong><br/>
            <code style="background: rgba(0,194,255,0.1); padding: 0.5rem; border-radius: 4px; display: inline-block; margin-top: 0.5rem; color: #00d9ff;">${calculation.formula}</code>
        </div>`;
    }

    if (calculation.inputs) {
        html += `<div style="margin-bottom: 1rem;">
            <strong style="color: #00d9ff;">📊 Inputs:</strong>
            <ul style="margin: 0.5rem 0; padding-left: 1.5rem; color: #ccc;">`;
        for (const [key, value] of Object.entries(calculation.inputs)) {
            html += `<li><span style="color: #aaa;">${key}:</span> <strong style="color: #fff;">${value}</strong></li>`;
        }
        html += `</ul></div>`;
    }

    if (calculation.steps && calculation.steps.length > 0) {
        html += `<div style="margin-bottom: 1rem;">
            <strong style="color: #00d9ff;">🔢 Calculation Steps:</strong>
            <ol style="margin: 0.5rem 0; padding-left: 1.5rem; color: #ccc;">`;
        calculation.steps.forEach(step => {
            html += `<li style="margin: 0.3rem 0;">${step}</li>`;
        });
        html += `</ol></div>`;
    }

    if (calculation.result) {
        html += `<div style="margin-bottom: 1rem; padding: 0.75rem; background: rgba(0,255,163,0.1); border-left: 3px solid #00ffa3; border-radius: 4px;">
            <strong style="color: #00ffa3;">✅ Result:</strong> <span style="color: #fff;">${calculation.result}</span>
        </div>`;
    }

    if (calculation.interpretation) {
        html += `<div style="margin-bottom: 1rem; padding: 0.75rem; background: rgba(255,255,255,0.03); border-radius: 4px;">
            <strong style="color: #ffaa00;">💡 What this means:</strong><br/>
            <span style="color: #ddd; line-height: 1.6;">${calculation.interpretation}</span>
        </div>`;
    }

    if (calculation.baseline) {
        html += `<div style="padding: 0.75rem; background: rgba(0,194,255,0.05); border-radius: 4px;">
            <strong style="color: #00c2ff;">📈 Context / Baseline:</strong><br/>
            <span style="color: #ddd; line-height: 1.6;">${calculation.baseline}</span>
        </div>`;
    }

    modal.innerHTML = html;
    document.body.appendChild(modal);

    // Add backdrop
    const backdrop = document.createElement('div');
    backdrop.id = 'calc-modal-backdrop';
    backdrop.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.7);
        z-index: 9999;
        backdrop-filter: blur(5px);
    `;
    document.body.appendChild(backdrop);

    // Close handlers
    const closeModal = () => {
        modal.remove();
        backdrop.remove();
    };

    document.getElementById('close-calc-modal').addEventListener('click', closeModal);
    backdrop.addEventListener('click', closeModal);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeModal();
    }, { once: true });
}

// Initialize tooltips when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeCalculationTooltips);
} else {
    initializeCalculationTooltips();
}
