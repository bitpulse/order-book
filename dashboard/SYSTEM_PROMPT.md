# Context

I'm analyzing high-frequency order book data from crypto markets. The data includes:

- Price movements with bid/ask spreads
- Whale order events (large orders entering, increasing, decreasing)
- Event types: entered_top, increase, decrease, market_buy/sell
- Distance from mid-price (as percentage)
- USD volume and quantity for each event
- Sub-second timestamps

# Data Structure

[See attached JSON file]

# Analysis Request

## 1. Market Microstructure Analysis

- Identify order flow imbalances (buy vs sell pressure)
- Detect liquidity walls and their impact
- Analyze spread dynamics during volatility
- Find patterns in whale order placement/cancellation

## 2. Price Action Signals

- What triggered the price movement? (aggressive buying, liquidity removal, etc.)
- Were large orders absorbed or avoided?
- Did price respect or break through key liquidity zones?
- Identify false breakouts vs genuine momentum

## 3. Timing Analysis

- When did smart money position themselves (before/during/after move)?
- What was the sequence of events? (e.g., bids accumulate → asks clear → price rises)
- How long did orders stay in the book before being filled/cancelled?

## 4. Strategy Development

Based on this data, suggest:

- Entry/exit criteria (specific order flow patterns)
- Risk parameters (stop-loss placement relative to liquidity)
- Position sizing based on order book depth
- Time horizons (scalp vs swing based on volatility observed)

## 5. Risk Assessment

- What are the dangers of trading this pattern?
- Could this be spoofing or wash trading?
- What confirmation would you need before acting?
- What could invalidate the strategy?

# Constraints

- Assume I'm using this for backtesting, not live trading
- Focus on repeatable patterns, not one-off events
- Be specific about thresholds (e.g., "when volume exceeds X")
- Include false positive scenarios

# Output Format

Provide:

1. Executive summary (2-3 sentences)
2. Key findings (bullet points)
3. Actionable strategy with specific rules
4. Risk warnings and limitations
