// Analytics Configuration and Thresholds
// Centralized configuration for all analytics calculations

const ANALYTICS_CONFIG = {
    // USD Value Thresholds
    THRESHOLDS: {
        MEGA_WHALE: 1000000,      // $1M - Exceptional whale activity
        INSTITUTIONAL: 150000,     // $150K - Likely institutional
        LARGE_ORDER: 100000,       // $100K - Significant whale
        WHALE: 50000,              // $50K - Minimum whale threshold
        SIGNIFICANT: 10000         // $10K - Notable order
    },

    // Coordination/Imbalance Scoring
    COORDINATION: {
        HIGH: 70,      // >70% imbalance = high coordination
        MODERATE: 40,  // 40-70% imbalance = moderate coordination
        LOW: 0         // <40% imbalance = mixed/low coordination
    },

    // Follow-Through Strength
    FOLLOW_THROUGH: {
        STRONG: 70,    // >70% continuation = strong follow-through
        MODERATE: 40,  // 40-70% = moderate follow-through
        WEAK: 0        // <40% = weak follow-through
    },

    // Activity Level Thresholds (event counts)
    ACTIVITY: {
        VERY_HIGH: 50,   // >50 events = very high activity
        HIGH: 30,        // 30-50 events = high activity
        MEDIUM: 15,      // 15-30 events = medium activity
        LOW: 0           // <15 events = low activity
    },

    // Price Change Severity (percentage)
    PRICE_CHANGE: {
        EXTREME: 5,    // >5% = extreme volatility
        HIGH: 2,       // 2-5% = high volatility
        MEDIUM: 0.5,   // 0.5-2% = medium volatility
        LOW: 0         // <0.5% = low volatility
    },

    // Volume Dominance Ratios
    DOMINANCE: {
        STRONG: 2.0,    // >2x = strong dominance
        MODERATE: 1.5,  // 1.5-2x = moderate dominance
        SLIGHT: 1.2,    // 1.2-1.5x = slight dominance
        BALANCED: 1.0   // <1.2x = balanced
    },

    // Time-based Thresholds
    TIMING: {
        RAPID_FIRE: 2,        // <2 seconds avg between orders
        QUICK_SUCCESSION: 5,  // 2-5 seconds
        NORMAL: 10,           // 5-10 seconds
        SLOW: 30              // >30 seconds
    },

    // Event Count Thresholds for Pattern Detection
    PATTERN_DETECTION: {
        CASCADE_ORDERS: 10,        // >10 market orders = cascade
        LARGE_WHALE_GROUP: 5,      // >5 large orders = whale group
        HIGH_ACTIVITY_SPIKE: 50,   // >50 events = activity spike
        COORDINATED_BIDS: 8,       // >8 simultaneous bids = coordination
        INSTITUTIONAL_SIZE_COUNT: 5 // >5 institutional-sized orders
    },

    // Liquidity Quality Scoring
    LIQUIDITY: {
        DEEP: 150000,      // >$150K avg = deep liquidity
        GOOD: 75000,       // $75K-$150K avg = good liquidity
        AVERAGE: 25000,    // $25K-$75K avg = average liquidity
        THIN: 0            // <$25K avg = thin liquidity
    }
};

/**
 * Get coordination level from imbalance percentage
 * @param {number} imbalance - Percentage imbalance (0-100)
 * @returns {object} { level: string, description: string }
 */
function getCoordinationLevel(imbalance) {
    const absImbalance = Math.abs(imbalance);

    if (absImbalance >= ANALYTICS_CONFIG.COORDINATION.HIGH) {
        return {
            level: 'HIGH',
            description: 'Most whales moving in same direction',
            color: 'high'
        };
    } else if (absImbalance >= ANALYTICS_CONFIG.COORDINATION.MODERATE) {
        return {
            level: 'MODERATE',
            description: 'Some directional bias detected',
            color: 'medium'
        };
    } else {
        return {
            level: 'LOW',
            description: 'Mixed activity, no clear coordination',
            color: 'low'
        };
    }
}

/**
 * Get follow-through strength from continuation ratio
 * @param {number} ratio - Continuation ratio as percentage (0-100+)
 * @returns {object} { level: string, description: string }
 */
function getFollowThroughLevel(ratio) {
    if (ratio >= ANALYTICS_CONFIG.FOLLOW_THROUGH.STRONG) {
        return {
            level: 'STRONG',
            description: 'Sustained movement likely',
            color: 'bullish'
        };
    } else if (ratio >= ANALYTICS_CONFIG.FOLLOW_THROUGH.MODERATE) {
        return {
            level: 'MODERATE',
            description: 'Watch for confirmation',
            color: 'medium'
        };
    } else {
        return {
            level: 'WEAK',
            description: 'Spike may reverse',
            color: 'bearish'
        };
    }
}

/**
 * Get activity level from event count
 * @param {number} eventCount - Number of whale events
 * @returns {object} { level: string, badge: string }
 */
function getActivityLevel(eventCount) {
    if (eventCount >= ANALYTICS_CONFIG.ACTIVITY.VERY_HIGH) {
        return { level: 'Very High', badge: 'high' };
    } else if (eventCount >= ANALYTICS_CONFIG.ACTIVITY.HIGH) {
        return { level: 'High', badge: 'medium' };
    } else if (eventCount >= ANALYTICS_CONFIG.ACTIVITY.MEDIUM) {
        return { level: 'Medium', badge: 'medium' };
    } else {
        return { level: 'Low', badge: 'low' };
    }
}

/**
 * Get price change severity
 * @param {number} priceChange - Absolute price change percentage
 * @returns {object} { level: string, badge: string }
 */
function getPriceChangeSeverity(priceChange) {
    const absPriceChange = Math.abs(priceChange);

    if (absPriceChange >= ANALYTICS_CONFIG.PRICE_CHANGE.EXTREME) {
        return { level: 'Extreme', badge: 'high' };
    } else if (absPriceChange >= ANALYTICS_CONFIG.PRICE_CHANGE.HIGH) {
        return { level: 'High', badge: 'high' };
    } else if (absPriceChange >= ANALYTICS_CONFIG.PRICE_CHANGE.MEDIUM) {
        return { level: 'Medium', badge: 'medium' };
    } else {
        return { level: 'Low', badge: 'low' };
    }
}

/**
 * Get liquidity quality from average order size
 * @param {number} avgOrderSize - Average order size in USD
 * @returns {object} { level: string, badge: string }
 */
function getLiquidityQuality(avgOrderSize) {
    if (avgOrderSize >= ANALYTICS_CONFIG.LIQUIDITY.DEEP) {
        return { level: 'Deep liquidity', badge: 'low', description: 'Exceptionally large orders' };
    } else if (avgOrderSize >= ANALYTICS_CONFIG.LIQUIDITY.GOOD) {
        return { level: 'Good liquidity', badge: 'medium', description: 'Healthy order sizes' };
    } else if (avgOrderSize >= ANALYTICS_CONFIG.LIQUIDITY.AVERAGE) {
        return { level: 'Average liquidity', badge: 'medium', description: 'Moderate order sizes' };
    } else {
        return { level: 'Thin liquidity', badge: 'high', description: 'Small order sizes' };
    }
}

/**
 * Format calculation explanation for UI display
 * @param {object} calculation - Calculation details
 * @returns {string} HTML string for display
 */
function formatCalculationExplanation(calculation) {
    let html = '<div class="calc-explanation">';

    // Formula
    if (calculation.formula) {
        html += `<div class="calc-section">
            <strong>📐 Formula:</strong> <code>${calculation.formula}</code>
        </div>`;
    }

    // Inputs
    if (calculation.inputs) {
        html += '<div class="calc-section"><strong>📊 Inputs:</strong><ul class="calc-inputs">';
        for (const [key, value] of Object.entries(calculation.inputs)) {
            html += `<li><span class="input-label">${key}:</span> <span class="input-value">${value}</span></li>`;
        }
        html += '</ul></div>';
    }

    // Steps
    if (calculation.steps && calculation.steps.length > 0) {
        html += '<div class="calc-section"><strong>🔢 Calculation:</strong><ol class="calc-steps">';
        calculation.steps.forEach(step => {
            html += `<li>${step}</li>`;
        });
        html += '</ol></div>';
    }

    // Result
    if (calculation.result) {
        html += `<div class="calc-section calc-result">
            <strong>✅ Result:</strong> ${calculation.result}
        </div>`;
    }

    // Interpretation
    if (calculation.interpretation) {
        html += `<div class="calc-section calc-interpretation">
            <strong>💡 Meaning:</strong> ${calculation.interpretation}
        </div>`;
    }

    // Baseline/Context
    if (calculation.baseline) {
        html += `<div class="calc-section calc-baseline">
            <strong>📈 Context:</strong> ${calculation.baseline}
        </div>`;
    }

    html += '</div>';
    return html;
}
