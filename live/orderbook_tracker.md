# Order Book Tracker - Real-time Large Order Monitor

## What Does This Tool Do?

Monitors MEXC Futures order book in real-time and displays significant order flow events - when large buy/sell orders appear, increase, or decrease at different price levels.

## Quick Start

```bash
# Basic usage - show all large orders
python live/orderbook_tracker.py BTC_USDT --min-usd 100000

# Filter by USD value range
python live/orderbook_tracker.py WIF_USDT --min-usd 50000 --max-usd 500000

# Filter by distance from mid-price
python live/orderbook_tracker.py BTC_USDT --min-usd 100000 --max-distance 0.5

# Combine filters
python live/orderbook_tracker.py BTC_USDT --min-usd 50000 --max-usd 1000000 --max-distance 0.2
```

## Understanding the Display

### Event Types

- **BID** (green) - Large buy order appeared at a new price level
- **BID ↑** (green) - Buy order volume increased at existing price
- **BID ↓** (dim) - Buy order volume decreased (partial fill/cancel)
- **ASK** (red) - Large sell order appeared at a new price level
- **ASK ↑** (red) - Sell order volume increased at existing price
- **ASK ↓** (dim) - Sell order volume decreased (partial fill/cancel)

### Output Columns

```
Time         Type         Price        Volume       Value        Distance   Total
22:14:12.222 BID          117026.90    42.1k        $4.9b        +0.000%    42.1k
22:14:13.271 BID ↑        117026.90    +2.8k        $330.6m      +0.000%    44.9k
22:14:14.500 BID ↓        117026.90    -10.5k       $1.2b        +0.000%    34.4k
```

- **Time**: Timestamp of the event
- **Type**: Event type (BID, ASK, BID ↑, ASK ↑, BID ↓, ASK ↓)
- **Price**: Price level where event occurred
- **Volume**: Contract volume (shows change for ↑/↓ events)
- **Value**: Notional USD value (price × volume)
- **Distance**: Distance from mid-price as percentage
- **Total**: Total volume remaining at this price level after the change

### Volume Notation

- `42.1k` = 42,100 contracts
- `2.5m` = 2,500,000 contracts
- Format uses one decimal place (e.g., `7.5k` not `7.99k`)

### Understanding "Value" for Futures

For BTC futures, the USD values represent **notional exposure**:
- Volume `42.1k` = 42,100 contracts
- Price `$117,026.90`
- Notional value = `42,100 × $117,026.90 = $4.9 billion`

This is normal for derivatives - it shows the total value controlled by those contracts.

## Command Line Options

### Required
- `SYMBOL` - Trading pair (e.g., BTC_USDT, ETH_USDT, WIF_USDT)

### Optional Filters

**Volume Filter:**
```bash
--min-volume CONTRACTS    # Minimum contract volume to display
```

**USD Value Range:**
```bash
--min-usd DOLLARS        # Minimum USD value (default: 0)
--max-usd DOLLARS        # Maximum USD value (default: no limit)
```

**Distance from Mid-Price Range:**
```bash
--min-distance PERCENT   # Minimum distance from mid-price (e.g., 0.1 = 0.1%)
--max-distance PERCENT   # Maximum distance from mid-price (e.g., 0.5 = 0.5%)
```

**Order Book Depth:**
```bash
--limit [5|10|20]        # Number of price levels to monitor (default: 10)
```

## Example Use Cases

### 1. Track Large Whale Orders ($100k+)
```bash
python live/orderbook_tracker.py BTC_USDT --min-usd 100000
```
Shows only orders worth $100k or more.

### 2. Monitor Specific Size Range
```bash
python live/orderbook_tracker.py WIF_USDT --min-usd 50000 --max-usd 500000
```
Shows only orders between $50k and $500k (filters out noise and mega-whales).

### 3. Watch Orders Near Market Price
```bash
python live/orderbook_tracker.py BTC_USDT --min-usd 100000 --max-distance 0.2
```
Shows large orders within 0.2% of mid-price (likely to execute soon).

### 4. Find Far Support/Resistance
```bash
python live/orderbook_tracker.py BTC_USDT --min-usd 1000000 --min-distance 1.0
```
Shows massive orders (>$1M) that are far from current price (>1% away).

### 5. Precision Range Scanning
```bash
python live/orderbook_tracker.py WIF_USDT --min-usd 100000 --min-distance 0.1 --max-distance 0.5
```
Shows orders $100k+ that are between 0.1% and 0.5% from mid-price.

## What the Data Shows

### Price Level Changes (Not Individual Orders)

The tool tracks **aggregated volume at each price level**, not individual orders:

**What you see:**
- Price $117,026.90 has 42.1k contracts total
- Volume at this price increased by 2.8k
- This price level disappeared from the book

**What you DON'T see:**
- Individual order IDs
- Who placed the orders
- Whether volume decrease was fill vs. cancel
- Individual order sizes within a price level

### Why Orders Appear/Disappear

**BID/ASK (new level):**
- New orders placed at this price
- Or price level moved into top N snapshot window

**BID ↑ / ASK ↑ (volume increase):**
- New orders added at existing price
- Net result of adds minus cancels

**BID ↓ / ASK ↓ (volume decrease):**
- Partial fills (orders executed)
- Partial cancellations
- Multiple small orders filled/cancelled
- Cannot distinguish between these!

**Level disappeared completely:**
- All orders filled
- All orders cancelled
- Price moved out of top N snapshot window

## CSV Data Logging

When you exit (Ctrl+C), all events are saved to:
```
logs/orderbook_{SYMBOL}_{TIMESTAMP}.csv
```

**CSV Columns:**
- timestamp - ISO datetime when event occurred
- type - Event type (new, increase, decrease)
- side - bid or ask
- price - Price level
- volume - Volume amount (or change for increase/decrease)
- usd_value - USD value of volume
- distance_from_mid_pct - Distance from mid-price as %
- best_bid - Best bid at time of event
- best_ask - Best ask at time of event
- spread - Spread at time of event
- info - Additional context (e.g., "total:42100")

## Trading Patterns to Watch

### Pattern 1: Wall Building (Support/Resistance)
```
22:14:00 BID      117000.00  100.0k  $11.7b
22:14:05 BID ↑    117000.00  +50.0k  $5.9b   (total: 150.0k)
22:14:10 BID ↑    117000.00  +80.0k  $9.4b   (total: 230.0k)
```
Someone is stacking buy orders at $117k - strong support building.

### Pattern 2: Spoofing (Fake Wall)
```
22:14:00 ASK      118000.00  500.0k  $59.0b
22:14:02 ASK ↓    118000.00  -500.0k $59.0b  (total: 0)
```
Large sell wall appeared and vanished 2 seconds later - likely manipulation.

### Pattern 3: Absorption (Orders Being Filled)
```
22:14:00 BID ↓    117000.00  -50.0k  $5.9b   (total: 100.0k)
22:14:01 BID ↓    117000.00  -30.0k  $3.5b   (total: 70.0k)
22:14:02 BID ↓    117000.00  -70.0k  $8.2b   (total: 0)
```
Buy orders being eaten by sellers - support breaking down.

### Pattern 4: Accumulation Ladder
```
22:14:00 BID      116500.00  50.0k   $5.8b   (+0.5%)
22:14:05 BID      116000.00  75.0k   $8.7b   (+1.0%)
22:14:10 BID      115500.00  100.0k  $11.6b  (+1.5%)
```
Whale placing ladder of buy orders below market - waiting to accumulate on dips.

## Technical Details

### Data Source
- **Exchange**: MEXC Futures
- **WebSocket**: `wss://contract.mexc.com/edge`
- **Channel**: `sub.depth.full` (full snapshots)
- **Update Rate**: 30-50 snapshots per second
- **Data Format**: `[price, volume, order_count]`

### Data Level
**Level 2 (L2) - Aggregated Order Book:**
- Total volume at each price level
- Order count at each price level
- Cannot track individual orders
- This is what MEXC provides

**Level 3 (L3) - Individual Orders (not available):**
- Individual order IDs
- Track specific orders from placement to fill
- Available on: Coinbase Pro, Bitstamp (not MEXC)

### How It Works

**Snapshot Comparison Algorithm:**

1. Receive order book snapshot from MEXC
2. Compare with previous snapshot:
   - New price level? → Show BID/ASK
   - Volume increased? → Show BID ↑ / ASK ↑
   - Volume decreased? → Show BID ↓ / ASK ↓
3. Apply all filters (volume, USD, distance)
4. Display events that pass filters
5. Log to CSV file
6. Update previous snapshot
7. Wait for next update (20-50ms later)

## Statistics Display

Every 100 updates, you see:
```
────────────────────────────────────────────────────────────────────────────────
Summary after 100 updates:
  New Bids: 45 (Volume: 1.2m)
  New Asks: 52 (Volume: 1.5m)
  Removed: 38 bids, 45 asks
────────────────────────────────────────────────────────────────────────────────
```

**Interpretation:**
- More new ask levels (52) than bid levels (45) = selling pressure
- More ask volume (1.5m) than bid volume (1.2m) = bearish imbalance

## Tips for Effective Use

1. **Start with high USD filters** - Use `--min-usd 100000` to see only significant orders
2. **Use ranges for precision** - Combine `--min-usd` and `--max-usd` to target specific order sizes
3. **Watch near-price action** - Use `--max-distance 0.5` to see orders likely to execute soon
4. **Find support/resistance** - Use `--min-distance 1.0` to see far orders that might act as levels
5. **Monitor volume decreases** - BID ↓ / ASK ↓ shows orders being filled or pulled
6. **Look for patterns** - Repeated behavior often signals bots or specific trading strategies
7. **Compare bid vs ask flow** - More/larger bids than asks = bullish pressure

## Common Questions

**Q: What's the difference between BID and BID ↑?**
A: **BID** = new price level appeared. **BID ↑** = more volume added to existing price level.

**Q: Why do I see volume decrease (↓) events?**
A: These show when orders are partially filled or cancelled. Helps you see when support/resistance is being tested.

**Q: Can I see individual order IDs?**
A: No, MEXC provides Level 2 data (aggregated by price). Individual orders are not trackable.

**Q: Why do values show billions for BTC?**
A: The USD value shows **notional exposure** for futures contracts. 42.1k contracts × $117k = $4.9 billion in notional value controlled.

**Q: How do I know if volume decrease was fill vs cancel?**
A: You can't tell from order book data alone. Both look identical (volume goes down).

**Q: What's a good filter for BTC?**
A: Try `--min-usd 100000` to see orders $100k+. For very active periods, increase to `--min-usd 500000`.

**Q: What's a good filter for altcoins like WIF?**
A: Try `--min-usd 50000` to start. Adjust based on typical order sizes you observe.

**Q: The output is too fast!**
A: Increase `--min-usd` threshold or use `--max-distance 0.5` to only see orders near market price.

**Q: Why does the same price flash multiple times?**
A: High frequency trading and order churning. Bots constantly add/remove/modify orders.

## Exit and Cleanup

Press **Ctrl+C** to stop.

You'll see final statistics:
```
================================================================================
Final Statistics - Runtime: 300s
================================================================================
Total Updates: 250
Total New Bids: 45 (Volume: 1.2m)
Total New Asks: 52 (Volume: 1.5m)

Data saved to: logs/orderbook_BTC_USDT_20251001_221530.csv
```

All events are saved to the CSV file for later analysis.
