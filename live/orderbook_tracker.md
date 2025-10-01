# Order Book Tracker - Simple Guide

## What Does This Tool Do?

The order book tracker watches a cryptocurrency exchange (MEXC) in real-time and shows you when people place or cancel large buy/sell orders. Think of it like watching a live scoreboard of who wants to buy or sell, and at what prices.

## Why Is This Useful?

- **Spot whales**: See when someone places a huge order (like $50,000 worth)
- **Find support/resistance**: See where big buyers/sellers are waiting
- **Detect manipulation**: Notice if someone places then quickly cancels large orders
- **Track momentum**: See if more people are trying to buy vs sell

## How to Use It

### Basic Command
```bash
python orderbook_tracker.py WIF_USDT
```

### Filter Out Small Orders (Recommended)
```bash
# Only show orders bigger than 10,000 contracts
python orderbook_tracker.py WIF_USDT --min-volume 10000
```

### Watch More Price Levels
```bash
# See top 20 price levels instead of 10
python orderbook_tracker.py WIF_USDT --limit 20
```

## Understanding the Output

### Color Coding
- **🟢 Green** = New BUY orders (bids)
- **🔴 Red** = New SELL orders (asks)
- **⚪ Gray** = Orders removed (filled or canceled)

### Example Output Explained

```
Time         Type         Price        Volume       Value        Distance   Info
--------------------------------------------------------------------------------
21:28:19.714 NEW BID      0.750900     76.02K       $57          +0.033%
```

**Translation:** At 9:28pm, someone placed a buy order for 76,020 contracts at $0.7509 each (worth $57,000 total). This price is 0.033% below the current market price.

```
21:28:22.350 BID ↑        0.750900     +30.01K      $23          (total: 79.69K)
```

**Translation:** More buyers joined! Someone added another 30,010 contracts at the same price. Now there's a total of 79,690 contracts waiting to buy at $0.7509.

```
21:28:22.350 BID REMOVED  0.750200     -61.64K      $46
```

**Translation:** A large buy order for 61,640 contracts at $0.7502 just disappeared. Either it was filled by sellers, or the buyer canceled it.

## Real-World Examples

### Example 1: Whale Buy Signal
```
21:30:15.123 NEW BID      0.750000     500.00K      $375K        BEST
```
**What this means:** Someone just placed a MASSIVE buy order for $375,000 at the best price. This could be a whale accumulating, or trying to push the price up.

### Example 2: Support Building
```
21:30:15.456 NEW BID      0.740000     100.00K      $74K
21:30:16.789 BID ↑        0.740000     +50.00K      $37K         (total: 150K)
21:30:18.012 BID ↑        0.740000     +75.00K      $56K         (total: 225K)
```
**What this means:** Multiple buyers are stacking orders at $0.74. This price level is becoming strong support.

### Example 3: Possible Spoofing
```
21:30:20.000 NEW ASK      0.760000     1000.00K     $760K
21:30:22.500 ASK REMOVED  0.760000     -1000.00K    $760K
```
**What this means:** Someone placed a huge sell wall ($760K), then removed it 2.5 seconds later without it being filled. This could be spoofing (trying to scare buyers).

### Example 4: Liquidation Cascade
```
21:30:25.100 BID REMOVED  0.745000     -50.00K      $37K
21:30:25.150 BID REMOVED  0.744000     -75.00K      $56K
21:30:25.200 BID REMOVED  0.743000     -100.00K     $74K
21:30:25.250 BID REMOVED  0.742000     -120.00K     $89K
```
**What this means:** Buy orders are disappearing rapidly down the order book. This could indicate a liquidation event or panic selling.

## Important Data Format

MEXC sends order book data in this format: **`[price, volume, order_count]`**

Example: `[0.7505, 30150, 2]` means:
- **Price:** $0.7505
- **Volume:** 30,150 contracts
- **Order count:** 2 orders at this price

So there are **2 orders** totaling **30,150 contracts** at **$0.7505**.

## What You CAN Track

✅ **Total volume at each price level** (e.g., 76,020 contracts at $0.7509)
✅ **Number of orders at each price** (e.g., 3 orders totaling 76K contracts)
✅ **When new price levels appear** (someone placed orders at a new price)
✅ **When price levels disappear** (orders filled or canceled)
✅ **Volume increases at existing prices** (more orders added)
✅ **Large whale orders** (filter with --min-volume)
✅ **Order book imbalance** (more buy pressure vs sell pressure)

## What You CANNOT Track

❌ **Individual order IDs** - You can't follow a specific order
❌ **Who placed the order** - All traders are anonymous
❌ **Individual order sizes** - If there are 3 orders totaling 30K, you don't know if it's 10K+10K+10K or 1K+1K+28K
❌ **Why an order was removed** - Could be filled, canceled, or just moved out of view
❌ **Orders inside a price level** - If 3 orders exist at $0.75, you can't track when 1 of them gets canceled (you'd just see the total drop)

## How The Tracker Works (Simple Explanation)

Think of the order book like a **constantly updating restaurant menu** where prices and portions keep changing. Our tracker takes **photos** of this menu every split second and compares them to see what changed.

### The Snapshot Method

Every time MEXC sends us new data (30-50 times per second!), we:

**1. Take a Photo (Snapshot)**
```
Current Menu:
  Buy $0.7510 → 61,640 burgers available
  Buy $0.7509 → 50,000 burgers available
  Buy $0.7508 → 30,000 burgers available
```

**2. Compare with Previous Photo**
```
Old Menu (0.5 seconds ago):
  Buy $0.7510 → 61,640 burgers available
  Buy $0.7509 → 50,000 burgers available
  Buy $0.7507 → 20,000 burgers available  ← different price!
```

**3. Spot the Differences**

We check 4 things:

### ✅ NEW ORDERS (New Price Level Appears)
```python
# In the code (line 175-176):
if price not in self.previous_bids:
    # This is a NEW order at a new price!
```

**Example:**
- Previous: No one wanted to buy at $0.7508
- Current: Someone placed 30,000 contracts at $0.7508
- **Display:** `NEW BID  $0.7508  30.0k  $23k`

### ⬆️ VOLUME INCREASED (More Orders at Same Price)
```python
# In the code (line 205-207):
elif self.previous_bids[price] < volume:
    increase = volume - self.previous_bids[price]
    # More orders added at this price!
```

**Example:**
- Previous: 61,640 contracts at $0.7510
- Current: 91,650 contracts at $0.7510 (30,010 more!)
- **Display:** `BID ↑  $0.7510  +30.0k  $23k  (total: 91.7k)`

### ❌ ORDERS REMOVED (Price Level Disappears)
```python
# In the code (line 225-226):
for price, volume in self.previous_bids.items():
    if price not in current_bids:
        # Price level is gone!
```

**Example:**
- Previous: 30,000 contracts at $0.7508
- Current: $0.7508 doesn't exist anymore
- **Display:** `BID REMOVED  $0.7508  -30.0k  $23k`

### 🤷 Why Did Orders Get Removed?

The tracker **cannot tell** why they're gone. Could be:

1. **Someone bought them all** (market order ate the limit orders)
2. **Trader canceled** (changed their mind)
3. **Pushed out of view** (we only see top 10/20 levels, might have dropped to #21)

**Important:** We don't know which! We just know the price level vanished.

### 📊 What About Volume Decreases?

**We DON'T show volume decreases!** Here's why:

```python
# The code ONLY shows increases (line 205):
elif self.previous_bids[price] < volume:  # Only if NEW volume > OLD volume
```

If volume goes from 30,000 → 20,000, we **stay silent** because:
- Could be partial fills (good to know, but noisy)
- Could be someone canceled part of their order
- Creates too much spam in the output

We only care about:
- ✅ NEW levels appearing (big news!)
- ✅ Volume INCREASING (more interest!)
- ✅ Levels completely DISAPPEARING (support/resistance gone!)

### Real Example Walkthrough

**Snapshot #1 (21:30:00.000)**
```
Bids: $0.7510 → 50,000 | $0.7509 → 30,000 | $0.7508 → 20,000
Asks: $0.7511 → 40,000 | $0.7512 → 25,000 | $0.7513 → 15,000
```
*Tracker saves this and waits...*

**Snapshot #2 (21:30:00.327) - 327ms later**
```
Bids: $0.7510 → 80,000 | $0.7509 → 30,000 | $0.7507 → 10,000
Asks: $0.7511 → 40,000 | $0.7512 → 35,000 | $0.7513 → 15,000
```

**Tracker thinks:**
1. ✅ "Bid at $0.7510 increased from 50k → 80k (+30k)" → Show `BID ↑`
2. ✅ "Bid at $0.7509 stayed same (30k)" → Ignore
3. ❌ "Bid at $0.7508 is gone!" → Show `BID REMOVED`
4. ✅ "Bid at $0.7507 is new (wasn't here before)" → Show `NEW BID`
5. ✅ "Ask at $0.7512 increased from 25k → 35k (+10k)" → Show `ASK ↑`

**Output to screen:**
```
21:30:00.327 BID ↑        0.751000     +30.0k       $23k         (total: 80.0k)
21:30:00.327 BID REMOVED  0.750800     -20.0k       $15k
21:30:00.327 NEW BID      0.750700     10.0k        $8k
21:30:00.327 ASK ↑        0.751200     +10.0k       $8k          (total: 35.0k)
```

### How We Store Data

```python
# Current state (what we just received)
current_bids = {
    0.7510: 80000,
    0.7509: 30000,
    0.7507: 10000
}

# Previous state (from last snapshot)
self.previous_bids = {
    0.7510: 50000,
    0.7509: 30000,
    0.7508: 20000
}

# After comparison, current becomes previous
self.previous_bids = current_bids.copy()  # Line 321
```

This is like saying: "What I'm seeing NOW becomes what I saw BEFORE for the next comparison."

### Filters: Reducing Noise

Without filters, you'd see EVERY tiny change (even 1 contract). That's too noisy!

```python
# Line 168-173: Volume filter
if volume < self.min_volume:
    continue  # Skip if too small

# Line 171-173: USD value filter
usd_value = price * volume
if usd_value < self.min_usd:
    continue  # Skip if dollar value too low
```

**Example with `--min-volume 10000`:**
- ❌ Skip: 500 contract order ($375)
- ❌ Skip: 5,000 contract order ($3,750)
- ✅ Show: 15,000 contract order ($11,250)
- ✅ Show: 100,000 contract order ($75,000)

### Summary: The Simple Algorithm

```
Every 0.02 to 1 second:
  1. Receive new data from MEXC
  2. Convert to simple format: {price: volume}
  3. Compare with previous snapshot:
     - New price? → "NEW BID/ASK"
     - Price gone? → "REMOVED"
     - Volume up? → "BID/ASK ↑"
     - Volume same/down? → Stay quiet
  4. Apply filters (skip if too small)
  5. Print colored output to screen
  6. Save current as previous
  7. Wait for next update...
```

That's it! No complex math, no AI, just **comparing two lists** over and over very quickly.

## Technical Details (For Developers)

### WebSocket Connection
- **Endpoint:** `wss://contract.mexc.com/edge`
- **Subscription:** `sub.depth.full` (full snapshots)
- **Update frequency:** 30-50 snapshots per second during active trading
- **Data format:** JSON with `[price, volume, order_count]` arrays

### Data Structure
```python
{
  "channel": "push.depth.full",
  "symbol": "WIF_USDT",
  "data": {
    "bids": [
      [0.7505, 30150, 2],  # price, volume, orders
      [0.7504, 12603, 1],
      ...
    ],
    "asks": [
      [0.7506, 20235, 1],
      [0.7507, 43060, 2],
      ...
    ],
    "version": 2481000062  # sequence number
  },
  "ts": 1759339392631  # timestamp
}
```

### Algorithm
1. Store current order book state (previous_bids, previous_asks)
2. Receive new snapshot from WebSocket
3. Compare new vs previous:
   - **New price level** → Report as "NEW BID" or "NEW ASK"
   - **Price level gone** → Report as "REMOVED"
   - **Volume increased** → Report as "BID ↑" or "ASK ↑"
4. Update state (current becomes previous)
5. Repeat

### Level 2 vs Level 3 Data

**MEXC provides Level 2 (L2) data:**
- Aggregated by price level
- Shows total volume at each price
- Shows order count at each price
- **Cannot** track individual orders

**Level 3 (L3) data (not available on MEXC):**
- Individual order IDs
- Track specific orders from placement to fill/cancel
- See exact order sizes
- Available on: Coinbase Pro, Bitstamp, Bitfinex

## Statistics Tracking

The tracker keeps running statistics:

```
================================================================================
Final Statistics - Runtime: 300s
================================================================================
Total Updates: 250
Total New Bids: 45 (Volume: 1.2M)
Total New Asks: 52 (Volume: 1.5M)
Removed Orders - Bids: 38 | Asks: 45
```

**Interpretation:**
- In 5 minutes (300s), received 250 order book updates
- 45 new buy price levels appeared (1.2M contracts total)
- 52 new sell price levels appeared (1.5M contracts total)
- 38 buy levels and 45 sell levels disappeared
- More sell pressure than buy pressure (1.5M vs 1.2M)

## Output Files

When you stop the tracker (Ctrl+C), it saves:
```
order_history_WIF_USDT_20251001_212407.json
```

This JSON file contains all detected events for later analysis.

## Common Trading Patterns

### Pattern 1: Wall Building
```
NEW BID  $0.75  100K  ($75K)
BID ↑    $0.75  +50K  (total: 150K)
BID ↑    $0.75  +80K  (total: 230K)
```
**Meaning:** Someone is building a "buy wall" at $0.75 to prevent price from dropping below.

### Pattern 2: Wall Pulling
```
NEW ASK  $0.80  500K  ($400K)
(2 seconds later)
ASK REMOVED  $0.80  -500K
```
**Meaning:** Fake sell wall to scare buyers. Removed before execution.

### Pattern 3: Support Break
```
BID REMOVED  $0.75  -230K
BID REMOVED  $0.749 -180K
BID REMOVED  $0.748 -150K
```
**Meaning:** Support levels being eaten by sellers. Price likely dropping.

### Pattern 4: Accumulation
```
NEW BID  $0.745  50K   (+0.5% below market)
NEW BID  $0.744  75K   (+0.6% below market)
NEW BID  $0.743  100K  (+0.7% below market)
```
**Meaning:** Whale placing multiple buy orders below market, waiting to accumulate on dips.

## Tips for Using the Tracker

1. **Use volume filters:** `--min-volume 10000` to ignore small noise
2. **Watch best bid/ask:** Lines marked "BEST" show the market price
3. **Look for imbalances:** More green (bids) than red (asks) = bullish
4. **Notice patterns:** Repeating behavior can signal bots or whales
5. **Combine with price action:** Order book + price chart = full picture
6. **Be patient:** Watch for 5-10 minutes to understand normal patterns

## Frequently Asked Questions

**Q: Why do I see mostly 1-3 contract volumes?**
A: You're looking at the order_count (3rd number), not volume (2nd number). The format is `[price, volume, order_count]`.

**Q: Can I see who placed the order?**
A: No, all order book data is anonymous.

**Q: If an order is removed, was it filled or canceled?**
A: You can't tell from order book data alone. You'd need to cross-reference with trade data.

**Q: Why do price levels flicker on and off?**
A: Low liquidity pairs have unstable order books. Orders get filled/canceled quickly.

**Q: Can I track my own order?**
A: Not with this tool. This watches the public order book. Your own order is just one of many at a price level.

**Q: What's a good min-volume filter?**
A: For WIF_USDT, try `--min-volume 10000` (10K contracts ≈ $7-8K USD). Adjust based on the asset.

**Q: The output is too fast!**
A: Increase `--min-volume` to filter out more noise, or reduce `--limit` to watch fewer price levels.

## Advanced: InfluxDB Integration (Future)

Future versions will export to InfluxDB for time-series analysis:

```python
# Example query
SELECT volume, price
FROM orderbook
WHERE side = 'bid'
AND volume > 100000
AND time > now() - 1h
```

This will enable:
- Historical order book reconstruction
- Pattern recognition via ML
- Correlation with price movements
- Alert systems for whale activity

## Command Reference

```bash
# Basic usage
python orderbook_tracker.py SYMBOL

# With filters
python orderbook_tracker.py SYMBOL --limit [5|10|20] --min-volume CONTRACTS

# Examples
python orderbook_tracker.py BTC_USDT --limit 20
python orderbook_tracker.py ETH_USDT --min-volume 5000
python orderbook_tracker.py WIF_USDT --limit 5 --min-volume 10000
```

### Arguments
- `SYMBOL`: Trading pair (e.g., BTC_USDT, WIF_USDT, ETH_USDT)
- `--limit`: Order book depth to monitor (5, 10, or 20 levels)
- `--min-volume`: Minimum volume to display (filters noise)

## Understanding Market Impact

### Small Order (No Impact)
```
NEW BID  $0.75  100 contracts  ($75)
```
**Impact:** Negligible. Won't move market.

### Medium Order (Minor Impact)
```
NEW BID  $0.75  10,000 contracts  ($7,500)
```
**Impact:** Noticeable. Might influence short-term price.

### Large Order (Significant Impact)
```
NEW BID  $0.75  100,000 contracts  ($75,000)
```
**Impact:** Major. Could create support level or signal big buyer.

### Whale Order (Market Moving)
```
NEW BID  $0.75  1,000,000 contracts  ($750,000)
```
**Impact:** Huge. Likely to affect price. Watch closely.

## Conclusion

The order book tracker is a powerful tool for understanding market microstructure. While it can't track individual orders (that requires L3 data), it provides valuable insights into:

- Where whales are placing orders
- Support and resistance levels forming
- Order flow imbalances
- Potential manipulation attempts
- Market momentum shifts

Use it alongside price charts and trade data for complete market awareness.
