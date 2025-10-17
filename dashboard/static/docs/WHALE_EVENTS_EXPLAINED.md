# Whale Events Data - Complete Technical Explanation

## Table of Contents
1. [Data Source & Collection](#data-source--collection)
2. [Event Types Explained](#event-types-explained)
3. [What Each Metric Represents](#what-each-metric-represents)
4. [Understanding the Numbers](#understanding-the-numbers)
5. [Market Buy vs Market Sell](#market-buy-vs-market-sell)
6. [Bid/Ask Events](#bidask-events)
7. [Critical Limitations](#critical-limitations)

---

## Data Source & Collection

### WebSocket API
- **Exchange**: MEXC Futures (`wss://contract.mexc.com/edge`)
- **Update Frequency**: 30-50 snapshots per second
- **Data Type**: Level 2 (L2) Order Book Data - **aggregated by price level**

### Two WebSocket Channels

#### 1. Order Book Depth (`sub.depth.full`)
Provides snapshots of the top N price levels:
```json
{
  "bids": [[price, volume, order_count], ...],
  "asks": [[price, volume, order_count], ...],
  "version": 12345,
  "ts": 1704110400000
}
```

**Fields:**
- `price`: Price level (e.g., $117,026.90)
- `volume`: **TOTAL aggregated contracts** at this price (NOT individual orders)
- `order_count`: Number of separate orders at this price
- `version`: Sequence number for packet loss detection
- `ts`: Timestamp in milliseconds

#### 2. Trade Executions (`sub.deal`)
Provides individual trade executions (market orders):
```json
{
  "p": 117026.90,    // execution price
  "v": 42100,        // volume executed
  "T": 1,            // trade type: 1=Buy, 2=Sell
  "t": 1704110400000 // timestamp
}
```

---

## Event Types Explained

### Definitive Events (100% Certain Actions)

#### 1. **MARKET_BUY**
🎯 **Source**: `sub.deal` channel, Type=1
- **What it is**: Someone aggressively **bought** at the ask price
- **Execution**: Immediate, takes liquidity from sellers
- **Market Impact**: Bullish - buyer willing to pay premium to execute NOW
- **Example**: Whale places market buy for $1M → eats through ask orders instantly

**Technical Reality:**
- This is a **taker** order (crossed the spread)
- Removed liquidity from order book
- Price moved UP (if large enough volume)
- Cannot be cancelled (already executed)

**What you SEE in data:**
```json
{
  "event_type": "market_buy",
  "side": "buy",
  "price": 117026.90,
  "volume": 42100,
  "usd_value": 4928032890.00,
  "time": "2025-01-15T10:30:45.123Z"
}
```

**What it MEANS:**
- Someone bought 42,100 contracts at $117,026.90
- They paid ~$4.9B notional value
- They executed immediately (aggressive)
- Market absorbed this buy pressure

---

#### 2. **MARKET_SELL**
🎯 **Source**: `sub.deal` channel, Type=2
- **What it is**: Someone aggressively **sold** at the bid price
- **Execution**: Immediate, takes liquidity from buyers
- **Market Impact**: Bearish - seller willing to take discount to execute NOW
- **Example**: Whale dumps $2M worth → crashes through bid orders

**Technical Reality:**
- This is a **taker** order (crossed the spread)
- Removed liquidity from order book
- Price moved DOWN (if large enough volume)
- Cannot be cancelled (already executed)

**What you SEE in data:**
```json
{
  "event_type": "market_sell",
  "side": "sell",
  "price": 116950.00,
  "volume": 18500,
  "usd_value": 2163575000.00,
  "time": "2025-01-15T10:30:47.891Z"
}
```

**What it MEANS:**
- Someone sold 18,500 contracts at $116,950.00
- They received ~$2.1B notional value
- They executed immediately (aggressive)
- Market absorbed this sell pressure

---

#### 3. **NEW_BID** / **NEW_ASK**
🎯 **Source**: `sub.depth.full` channel - price NOT in previous OR historical snapshots
- **What it is**: A completely new price level appeared that we've never seen before
- **Why definitive**: Price wasn't in ANY previous data → must be a new order
- **Market Impact**: Shows new support/resistance being placed

**Detection Logic:**
```python
# Price appears in current snapshot
if price not in previous_snapshot:
    # Check if it was EVER in our historical full book
    if price not in historical_full_book:
        # This is a NEW order placement
        event_type = "new_bid" or "new_ask"
    else:
        # Price moved into top-N window (see "entered_top" below)
        event_type = "entered_top"
```

**Example NEW_BID:**
```json
{
  "event_type": "new_bid",
  "side": "bid",
  "price": 117000.00,
  "volume": 50000,
  "usd_value": 5850000000.00,
  "order_count": 3,
  "level": 5
}
```

**What it MEANS:**
- A new buy order(s) appeared at $117,000
- Total of 50,000 contracts (could be 3 separate orders)
- This is a maker order (adds liquidity)
- Whale is setting up potential support at this level

---

### Ambiguous Events (Cannot Distinguish Cause)

#### 4. **INCREASE**
⚠️ **Source**: `sub.depth.full` - volume at existing price went UP
- **What it is**: More volume appeared at an existing price level
- **Why ambiguous**: Could be multiple causes:
  1. New orders added at same price
  2. Existing order(s) modified to increase size
  3. Multiple small orders placed
  4. Bot replacing cancelled order immediately

**Example BID INCREASE:**
```json
{
  "event_type": "increase",
  "side": "bid",
  "price": 117000.00,
  "volume": 25000,       // CHANGE amount (not total)
  "usd_value": 2925000000.00,
  "info": "total:75000"  // New total at this price
}
```

**What it MEANS:**
- Volume at $117,000 went from 50k → 75k (+25k)
- $2.9B more notional value added
- **Cannot tell if**: new whale, same whale adding more, or modification
- **Impact**: Support/resistance building (muted green/red in chart)

---

#### 5. **DECREASE**
⚠️ **Source**: `sub.depth.full` - volume at existing price went DOWN
- **What it is**: Volume disappeared from an existing price level
- **Why ambiguous**: Could be:
  1. Orders partially filled (someone bought into the bid wall)
  2. Orders cancelled (whale pulled out)
  3. Orders modified to smaller size
  4. Mix of fills and cancels

**Example ASK DECREASE:**
```json
{
  "event_type": "decrease",
  "side": "ask",
  "price": 118000.00,
  "volume": 15000,       // REDUCTION amount
  "usd_value": 1770000000.00,
  "info": "total:35000"  // Remaining volume
}
```

**What it MEANS:**
- Sell wall at $118,000 shrunk from 50k → 35k (-15k)
- $1.77B less resistance at this price
- **Cannot tell if**: whale pulled order OR buyers ate into it
- **Chart Display**: Muted colors (ambiguous nature)

**Why This Matters:**
- BID DECREASE = support weakening (could be fills or pulls)
- ASK DECREASE = resistance weakening (could be fills or pulls)

---

### Technical Events (Visibility Changes)

#### 6. **ENTERED_TOP** / **LEFT_TOP**
📊 **Source**: Price moved in/out of top-N visible window
- **What it is**: Order book snapshot only shows top N levels (10, 20)
- **Not new activity**: Price already existed, just crossed visibility threshold
- **Example**: Top 20 snapshot → order at level 21 becomes level 19

**Why This Happens:**
- We only track top N price levels (API limitation)
- When better orders appear/disappear, lower levels move into view
- This is **technical noise**, not new trading activity

**Example:**
```json
{
  "event_type": "entered_top",
  "side": "bid",
  "price": 116900.00,
  "volume": 30000,
  "info": "entered_top_20"
}
```

**What it MEANS:**
- This bid was already in the order book (we just couldn't see it)
- Now it's in top 20, so we can track it
- **NOT a new order** - just became visible
- Generally ignored in serious analysis

---

## What Each Metric Represents

### Price
```json
"price": 117026.90
```
- The **price level** where the event occurred
- For market orders: execution price
- For limit orders: resting order price

### Volume
```json
"volume": 42100
```
**For NEW_BID/NEW_ASK/MARKET:**
- **Absolute quantity** in contracts
- BTC: 1 contract = varies by exchange (often 1 BTC or 0.001 BTC)
- On MEXC: check contract specifications

**For INCREASE/DECREASE:**
- **CHANGE in volume**, not total
- Increase: `+25000` means 25k contracts added
- Decrease: `-15000` means 15k contracts removed
- See `info` field for new total

### USD Value
```json
"usd_value": 4928032890.00
```
**Calculation:** `price × volume`

**For Futures (BTC):**
- This is **NOTIONAL value**, not actual capital
- $4.9B = amount of BTC controlled by those contracts
- **Actual margin** required is much less (e.g., 10x leverage = $490M capital)

**Why So Large:**
- Futures use leverage
- 42,100 contracts × $117,026.90 per contract
- Represents total exposure, not cash spent

### Distance from Mid-Price
```json
"distance_from_mid_pct": +0.523
```
**Calculation:**
```python
mid_price = (best_bid + best_ask) / 2
distance = ((price - mid_price) / mid_price) * 100
```

**Interpretation:**
- **+0.5%**: Order is 0.5% ABOVE mid-price (ask side, resistance)
- **-0.5%**: Order is 0.5% BELOW mid-price (bid side, support)
- **Near zero**: Very close to current market → likely to execute soon
- **Large distance**: Far from market → unlikely to fill (unless price moves)

### Level
```json
"level": 3
```
- Position in order book depth
- `level: 1` = best bid/ask (top of book)
- `level: 5` = 5th best price
- Lower levels = closer to market = more likely to execute

### Order Count
```json
"order_count": 7
```
- Number of **separate orders** at this price level
- `order_count: 1` = single large order (likely whale)
- `order_count: 50` = many small orders (could be retail or bot)
- Does **NOT** reveal individual order sizes

---

## Understanding the Numbers

### Why USD Values Are Billions

**Example: BTC Futures**
- Price: $117,026.90
- Volume: 42,100 contracts
- USD Value: $4.93 billion

**This is NORMAL for derivatives:**
1. **Notional Value**: Total exposure controlled
2. **Leverage**: Traders use 10x-100x leverage
3. **Capital Required**: Much less than notional

**Actual capital for this trade (10x leverage):**
- Notional: $4.93B
- Leverage: 10x
- Margin: $493M
- Real money at risk: $493M

### Volume Notation
- `42.1k` = 42,100 contracts
- `2.5m` = 2,500,000 contracts
- Always shows one decimal place

---

## Market Buy vs Market Sell

### Market Buy (Aggressive Bullish)
**Chain of events:**
1. Trader places market buy order
2. Order **immediately executes** against best ask orders
3. Eats through ask liquidity
4. Price moves UP (if volume large enough)
5. We log as `market_buy` event
6. Cannot be cancelled (already filled)

**Indicators:**
- ✅ Definitive action (we see the execution)
- ✅ Shows buying pressure
- ✅ Price impact immediate
- ✅ Taker order (removes liquidity)

### Market Sell (Aggressive Bearish)
**Chain of events:**
1. Trader places market sell order
2. Order **immediately executes** against best bid orders
3. Eats through bid liquidity
4. Price moves DOWN (if volume large enough)
5. We log as `market_sell` event
6. Cannot be cancelled (already filled)

**Indicators:**
- ✅ Definitive action (we see the execution)
- ✅ Shows selling pressure
- ✅ Price impact immediate
- ✅ Taker order (removes liquidity)

---

## Bid/Ask Events

### New Bid (Potential Support)
- **What**: Buy limit order placed below market
- **Intent**: Trader wants to buy IF price drops to this level
- **Impact**: Adds liquidity, creates support
- **Can be cancelled**: YES (might be spoofing)

### New Ask (Potential Resistance)
- **What**: Sell limit order placed above market
- **Intent**: Trader wants to sell IF price rises to this level
- **Impact**: Adds liquidity, creates resistance
- **Can be cancelled**: YES (might be spoofing)

### Increase (Building Walls)
- **Bid Increase**: More buy orders at existing level → support building
- **Ask Increase**: More sell orders at existing level → resistance building
- **Could be**: New orders OR order modifications

### Decrease (Weakening Walls)
- **Bid Decrease**: Buy orders removed/filled → support weakening
- **Ask Decrease**: Sell orders removed/filled → resistance weakening
- **Cannot distinguish**: Fills vs Cancellations

---

## Critical Limitations

### What We CAN'T See

#### 1. Individual Orders
**L2 Data = Aggregated**
- We see total volume at each price
- We don't see individual order IDs
- Can't track specific whale orders
- Can't tell if same trader

**Example:**
```
Price: $117,000
Volume: 100,000 contracts
Order Count: 5
```
We know there are 5 orders totaling 100k, but:
- ❌ Can't see: [50k, 30k, 10k, 7k, 3k]
- ❌ Can't tell if orders related
- ❌ Can't track modifications

#### 2. Fills vs Cancellations
When volume decreases, we **cannot tell** if:
- Orders were filled (real trading)
- Orders were cancelled (whale pulled out)
- Mix of both

**This is a fundamental L2 limitation.**

#### 3. Spoofing Detection
**Spoofing**: Placing large fake orders to manipulate, then cancelling

**What we see:**
```
10:30:00  NEW_ASK  $118,000  500k contracts  $59B
10:30:02  DECREASE $118,000  -500k contracts $59B (total: 0)
```

**What we CAN'T prove:**
- Was it spoofing? (likely)
- Or a whale who changed their mind? (possible)
- Or a bot glitch? (also possible)

#### 4. Hidden Orders
**Iceberg orders**: Large orders that only show small portion
- We only see visible portion
- Rest is hidden until top portion fills
- Whales use this to hide size

---

## How Data is Logged to InfluxDB

### Measurement: `orderbook_whale_events`
**Tags:**
- `symbol`: BTC_USDT
- `event_type`: market_buy, market_sell, new_bid, new_ask, increase, decrease
- `side`: bid, ask, buy, sell

**Fields:**
- `price`: float
- `volume`: float
- `usd_value`: float
- `distance_from_mid_pct`: float
- `best_bid`: float
- `best_ask`: float
- `spread`: float
- `level`: integer
- `order_count`: integer
- `info`: string

### Measurement: `price`
**Tags:**
- `symbol`: BTC_USDT

**Fields:**
- `mid_price`: float (average of best bid/ask)
- `best_bid`: float
- `best_ask`: float
- `spread`: float

---

## Chart Display Logic

### Event Colors in Dashboard

**Definitive Events (Bright):**
- 🔵 Market Buy: Bright Cyan (#00c2ff)
- 🔴 Market Sell: Bright Magenta (#ff00ff)
- 🟢 New Bid: Bright Green (#00ff88)
- 🔴 New Ask: Bright Red (#ff4444)

**Ambiguous Events (Muted):**
- 🟢 Bid Increase: Muted Green (#88cc88)
- 🔴 Ask Increase: Muted Red (#cc8888)
- 🔴 Bid Decrease: Muted Red (#cc8888)
- 🟢 Ask Decrease: Muted Green (#88cc88)

**Opacity by Period:**
- **DURING**: Full opacity (main events)
- **BEFORE**: 30% opacity (context)
- **AFTER**: 30% opacity (follow-up)

---

## Summary

### Definitive Data ✅
1. **Market Buy/Sell**: We see actual executions
2. **New Bid/Ask**: New price levels that didn't exist before
3. **Price, Volume, USD Value**: Exact figures from exchange

### Ambiguous Data ⚠️
1. **Increase/Decrease**: Can't tell if fills or cancels
2. **Order Modifications**: Can't track individual orders
3. **Trader Identity**: No way to know who placed orders

### Not Available ❌
1. **Individual Order Tracking**: L2 data is aggregated
2. **Fill vs Cancel**: Cannot distinguish
3. **Iceberg Orders**: Hidden portions not visible
4. **Trader Intent**: Can only infer from patterns

**Use this data to:**
- Spot large order flow patterns
- Identify support/resistance building
- Track whale activity trends
- Analyze market microstructure

**Do NOT assume:**
- Volume decrease = filled orders (could be cancelled)
- Same price = same trader (could be different)
- Order count = separate whales (could be same trader)
