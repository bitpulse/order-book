// Event Type Statistics - Period Breakdown

let currentPeriod = 'before';
let comparisonMode = false;
let periodStats = {
    before: null,
    during: null,
    after: null
};

/**
 * Initialize event stats panel listeners
 */
function initializeEventStatsPanel() {
    // Period tab listeners
    document.querySelectorAll('.period-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const period = tab.getAttribute('data-period');
            switchPeriod(period);
        });
    });

    // Comparison toggle listener
    const comparisonToggle = document.getElementById('comparison-toggle');
    if (comparisonToggle) {
        comparisonToggle.addEventListener('click', toggleComparisonMode);
    }
}

/**
 * Switch between periods
 */
function switchPeriod(period) {
    currentPeriod = period;

    // Update tab states
    document.querySelectorAll('.period-tab').forEach(tab => {
        tab.classList.toggle('active', tab.getAttribute('data-period') === period);
    });

    // Update table visibility
    document.querySelectorAll('.stats-table:not(.comparison)').forEach(table => {
        table.classList.toggle('active', table.id === `stats-table-${period}`);
    });
}

/**
 * Toggle comparison mode
 */
function toggleComparisonMode() {
    comparisonMode = !comparisonMode;

    const toggle = document.getElementById('comparison-toggle');
    const comparisonTable = document.getElementById('stats-table-comparison');
    const periodTables = document.querySelectorAll('.stats-table:not(.comparison)');

    toggle.classList.toggle('active', comparisonMode);

    if (comparisonMode) {
        comparisonTable.classList.add('active');
        periodTables.forEach(table => table.classList.remove('active'));
    } else {
        comparisonTable.classList.remove('active');
        switchPeriod(currentPeriod);
    }
}

/**
 * Update event stats panel with new data
 */
function updateEventStatsPanel(intervalData, whaleEventsBefore, whaleEventsDuring, whaleEventsAfter) {
    if (!intervalData) {
        document.getElementById('event-type-stats').style.display = 'none';
        return;
    }

    // Ensure arrays are defined
    whaleEventsBefore = whaleEventsBefore || [];
    whaleEventsDuring = whaleEventsDuring || [];
    whaleEventsAfter = whaleEventsAfter || [];

    document.getElementById('event-type-stats').style.display = 'block';

    // Calculate stats for each period
    periodStats.before = calculateEventBreakdown(whaleEventsBefore, 'before');
    periodStats.during = calculateEventBreakdown(whaleEventsDuring, 'during');
    periodStats.after = calculateEventBreakdown(whaleEventsAfter, 'after');

    // Update tab badges
    document.getElementById('before-count').textContent = whaleEventsBefore.length;
    document.getElementById('during-count').textContent = whaleEventsDuring.length;
    document.getElementById('after-count').textContent = whaleEventsAfter.length;

    // Render tables
    renderEventStatsTable(periodStats.before, 'before');
    renderEventStatsTable(periodStats.during, 'during');
    renderEventStatsTable(periodStats.after, 'after');
    renderComparisonTable(periodStats);

    // Generate and render insights
    const insights = generateEventInsights(periodStats.before, periodStats.during, periodStats.after);
    renderEventInsights(insights);
}

/**
 * Calculate event breakdown statistics
 */
function calculateEventBreakdown(events, period) {
    const stats = {
        market_buy: { count: 0, volume: 0, largest: 0, events: [] },
        market_sell: { count: 0, volume: 0, largest: 0, events: [] },
        new_bid: { count: 0, volume: 0, events: [] },
        new_ask: { count: 0, volume: 0, events: [] },
        bid_increase: { count: 0, volume: 0, events: [] },
        ask_increase: { count: 0, volume: 0, events: [] },
        bid_decrease: { count: 0, volume: 0, events: [] },
        ask_decrease: { count: 0, volume: 0, events: [] }
    };

    events.forEach(event => {
        const value = event.usd_value || 0;
        const eventType = event.event_type;
        const side = event.side;

        if (eventType === 'market_buy') {
            stats.market_buy.count++;
            stats.market_buy.volume += value;
            stats.market_buy.largest = Math.max(stats.market_buy.largest, value);
            stats.market_buy.events.push(event);
        } else if (eventType === 'market_sell') {
            stats.market_sell.count++;
            stats.market_sell.volume += value;
            stats.market_sell.largest = Math.max(stats.market_sell.largest, value);
            stats.market_sell.events.push(event);
        } else if (eventType === 'increase') {
            if (side === 'bid') {
                stats.bid_increase.count++;
                stats.bid_increase.volume += value;
                stats.bid_increase.events.push(event);
            } else {
                stats.ask_increase.count++;
                stats.ask_increase.volume += value;
                stats.ask_increase.events.push(event);
            }
        } else if (eventType === 'decrease') {
            if (side === 'bid') {
                stats.bid_decrease.count++;
                stats.bid_decrease.volume += value;
                stats.bid_decrease.events.push(event);
            } else {
                stats.ask_decrease.count++;
                stats.ask_decrease.volume += value;
                stats.ask_decrease.events.push(event);
            }
        } else if (eventType.includes('bid') || side === 'bid') {
            stats.new_bid.count++;
            stats.new_bid.volume += value;
            stats.new_bid.events.push(event);
        } else if (eventType.includes('ask') || side === 'ask') {
            stats.new_ask.count++;
            stats.new_ask.volume += value;
            stats.new_ask.events.push(event);
        }
    });

    // Calculate averages and percentages
    const totalVolume = Object.values(stats).reduce((sum, stat) => sum + stat.volume, 0);
    const totalCount = events.length;

    Object.keys(stats).forEach(key => {
        const stat = stats[key];
        stat.avg = stat.count > 0 ? stat.volume / stat.count : 0;
        stat.percent = totalCount > 0 ? (stat.count / totalCount) * 100 : 0;
    });

    stats.total = {
        count: totalCount,
        volume: totalVolume,
        avg: totalCount > 0 ? totalVolume / totalCount : 0
    };

    return stats;
}

/**
 * Render event stats table for a specific period
 */
function renderEventStatsTable(stats, period) {
    const container = document.getElementById(`stats-table-${period}`);
    if (!container || !stats) return;

    const eventTypes = [
        { key: 'market_buy', name: 'Market Buy', icon: '🔵', class: 'market-order market-buy definitive' },
        { key: 'market_sell', name: 'Market Sell', icon: '🔴', class: 'market-order market-sell definitive' },
        { key: 'new_bid', name: 'New Bid Orders', icon: '🟢', class: 'new-bid definitive' },
        { key: 'new_ask', name: 'New Ask Orders', icon: '🔴', class: 'new-ask definitive' },
        { key: 'bid_increase', name: 'Bid Increase', icon: '💎', class: 'ambiguous' },
        { key: 'ask_increase', name: 'Ask Increase', icon: '💎', class: 'ambiguous' },
        { key: 'bid_decrease', name: 'Bid Decrease', icon: '💎', class: 'ambiguous' },
        { key: 'ask_decrease', name: 'Ask Decrease', icon: '💎', class: 'ambiguous' }
    ];

    let html = `
        <table class="event-stats-table">
            <thead>
                <tr>
                    <th>Event Type</th>
                    <th>Count</th>
                    <th>Volume</th>
                    <th>Avg Size</th>
                    <th>% Total</th>
                </tr>
            </thead>
            <tbody>
    `;

    eventTypes.forEach(({ key, name, icon, class: className }) => {
        const stat = stats[key];
        const isEmpty = stat.count === 0;
        const rowClass = `event-row ${className} ${isEmpty ? 'empty' : ''}`;

        html += `
            <tr class="${rowClass}">
                <td>
                    <div class="event-type-cell">
                        <span class="event-icon">${icon}</span>
                        <span class="event-name">${name}</span>
                    </div>
                </td>
                <td class="count-cell">${stat.count}</td>
                <td class="volume-cell">${formatLargeNumber(stat.volume)}</td>
                <td class="avg-cell">${stat.count > 0 ? formatLargeNumber(stat.avg) : '-'}</td>
                <td class="percent-cell">${stat.percent.toFixed(1)}%</td>
            </tr>
        `;
    });

    // Total row
    html += `
            <tr class="event-row total">
                <td>
                    <div class="event-type-cell">
                        <span class="event-icon">📊</span>
                        <span class="event-name">TOTAL</span>
                    </div>
                </td>
                <td class="count-cell">${stats.total.count}</td>
                <td class="volume-cell">${formatLargeNumber(stats.total.volume)}</td>
                <td class="avg-cell">${formatLargeNumber(stats.total.avg)}</td>
                <td class="percent-cell">100%</td>
            </tr>
        `;

    html += `
            </tbody>
        </table>
    `;

    container.innerHTML = html;
}

/**
 * Render comparison table
 */
function renderComparisonTable(stats) {
    const container = document.getElementById('stats-table-comparison');
    if (!container) return;

    const eventTypes = [
        { key: 'market_buy', name: 'Market Buy', icon: '🔵' },
        { key: 'market_sell', name: 'Market Sell', icon: '🔴' },
        { key: 'new_bid', name: 'New Bid', icon: '🟢' },
        { key: 'new_ask', name: 'New Ask', icon: '🔴' },
        { key: 'bid_increase', name: 'Bid Inc', icon: '💎' },
        { key: 'ask_increase', name: 'Ask Inc', icon: '💎' }
    ];

    let html = `
        <table class="comparison-table">
            <thead>
                <tr>
                    <th>Event Type</th>
                    <th>🔴 Before</th>
                    <th>🎯 During</th>
                    <th>🟢 After</th>
                    <th>Total</th>
                </tr>
            </thead>
            <tbody>
    `;

    eventTypes.forEach(({ key, name, icon }) => {
        const before = stats.before[key];
        const during = stats.during[key];
        const after = stats.after[key];
        const total = {
            count: before.count + during.count + after.count,
            volume: before.volume + during.volume + after.volume
        };

        html += `
            <tr class="event-row">
                <td>
                    <div class="event-type-cell">
                        <span class="event-icon">${icon}</span>
                        <span class="event-name">${name}</span>
                    </div>
                </td>
                <td class="period-column before">${before.count} / ${formatLargeNumber(before.volume)}</td>
                <td class="period-column during">${during.count} / ${formatLargeNumber(during.volume)}</td>
                <td class="period-column after">${after.count} / ${formatLargeNumber(after.volume)}</td>
                <td class="period-column">${total.count} / ${formatLargeNumber(total.volume)}</td>
            </tr>
        `;
    });

    html += `
            <tr class="event-row total">
                <td><strong>TOTAL</strong></td>
                <td class="period-column before">${stats.before.total.count} / ${formatLargeNumber(stats.before.total.volume)}</td>
                <td class="period-column during">${stats.during.total.count} / ${formatLargeNumber(stats.during.total.volume)}</td>
                <td class="period-column after">${stats.after.total.count} / ${formatLargeNumber(stats.after.total.volume)}</td>
                <td class="period-column">${stats.before.total.count + stats.during.total.count + stats.after.total.count}</td>
            </tr>
            </tbody>
        </table>
    `;

    container.innerHTML = html;
}

/**
 * Generate insights from period comparison
 */
function generateEventInsights(before, during, after) {
    if (!before || !during || !after) return [];

    const insights = [];

    // 1. Aggressive buying/selling during spike
    const duringBuyVol = during.market_buy?.volume || 0;
    const duringSellVol = during.market_sell?.volume || 0;

    if (duringBuyVol > duringSellVol * 2 && duringSellVol > 0) {
        const ratio = duringBuyVol / duringSellVol;
        insights.push({
            type: 'bullish',
            icon: '🚀',
            text: `<strong>Aggressive Buying</strong>: ${during.market_buy?.count || 0} market buys (${formatLargeNumber(duringBuyVol)}) dominated the spike - ${ratio.toFixed(1)}x more volume than sells`
        });
    } else if (duringSellVol > duringBuyVol * 2 && duringBuyVol > 0) {
        const ratio = duringSellVol / duringBuyVol;
        insights.push({
            type: 'bearish',
            icon: '📉',
            text: `<strong>Aggressive Selling</strong>: ${during.market_sell?.count || 0} market sells (${formatLargeNumber(duringSellVol)}) dominated - ${ratio.toFixed(1)}x more than buys`
        });
    }

    // 2. Accumulation before spike
    const beforeNewBidCount = before.new_bid?.count || 0;
    const beforeNewAskCount = before.new_ask?.count || 0;
    if (beforeNewBidCount > beforeNewAskCount * 1.5 && beforeNewBidCount > 3) {
        insights.push({
            type: 'info',
            icon: '📊',
            text: `<strong>Accumulation Phase</strong>: ${beforeNewBidCount} new bid orders (${formatLargeNumber(before.new_bid?.volume || 0)}) placed before spike vs ${beforeNewAskCount} asks`
        });
    }

    // 3. Follow-through analysis
    const afterBuyVol = after.market_buy?.volume || 0;
    const buyRatio = duringBuyVol > 0 ? afterBuyVol / duringBuyVol : 0;
    const afterBuyCount = after.market_buy?.count || 0;
    const duringBuyCount = during.market_buy?.count || 0;

    if (buyRatio > 0.7 && afterBuyCount > 3) {
        insights.push({
            type: 'bullish',
            icon: '💪',
            text: `<strong>Strong Follow-Through</strong>: Market buys continued after spike at ${(buyRatio * 100).toFixed(0)}% of during-spike volume (${afterBuyCount} orders)`
        });
    } else if (buyRatio < 0.3 && duringBuyCount > 5) {
        insights.push({
            type: 'warning',
            icon: '⚠️',
            text: `<strong>Buying Exhaustion</strong>: Market buys dropped ${((1 - buyRatio) * 100).toFixed(0)}% after spike - potential reversal signal`
        });
    }

    // 4. Reversal detection
    const beforeBuyVol = before.market_buy?.volume || 0;
    const beforeSellVol = before.market_sell?.volume || 0;
    const afterSellVol = after.market_sell?.volume || 0;
    const beforeBuyDominance = beforeBuyVol > beforeSellVol * 1.5;
    const afterSellDominance = afterSellVol > afterBuyVol * 1.5;

    if (beforeBuyDominance && afterSellDominance) {
        insights.push({
            type: 'warning',
            icon: '🔄',
            text: `<strong>Reversal Pattern</strong>: Activity flipped from buying before spike to selling after - possible distribution`
        });
    }

    // 5. Institutional activity (large avg size)
    const duringBuyAvg = during.market_buy?.avg || 0;
    if (duringBuyAvg > 150000 && duringBuyCount > 5) {
        insights.push({
            type: 'info',
            icon: '🏦',
            text: `<strong>Institutional Size</strong>: Average market buy of ${formatLargeNumber(duringBuyAvg)} suggests institutional participation`
        });
    }

    // 6. Coordinated whale activity
    const duringNewBidCount = during.new_bid?.count || 0;
    const duringNewBidAvg = during.new_bid?.avg || 0;
    if (duringNewBidCount > 8 && duringNewBidAvg > 75000) {
        insights.push({
            type: 'bullish',
            icon: '🐋',
            text: `<strong>Coordinated Bids</strong>: ${duringNewBidCount} large bid orders (avg ${formatLargeNumber(duringNewBidAvg)}) placed simultaneously`
        });
    }

    return insights.slice(0, 5); // Max 5 insights
}

/**
 * Render insights
 */
function renderEventInsights(insights) {
    const container = document.getElementById('event-insights');
    if (!container) return;

    if (insights.length === 0) {
        container.innerHTML = '';
        return;
    }

    let html = `
        <div class="insights-title">
            💡 Key Insights
        </div>
    `;

    insights.forEach(insight => {
        html += `
            <div class="insight-item ${insight.type}">
                <span class="insight-icon">${insight.icon}</span>
                <div class="insight-text">${insight.text}</div>
            </div>
        `;
    });

    container.innerHTML = html;
}

/**
 * Format large numbers helper (use from analytics.js if already loaded)
 */
if (typeof formatLargeNumber === 'undefined') {
    function formatLargeNumber(num) {
        const abs = Math.abs(num);
        const sign = num < 0 ? '-' : '';

        if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
        if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(2)}M`;
        if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(1)}K`;
        return `${sign}$${abs.toFixed(0)}`;
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initializeEventStatsPanel();
});
