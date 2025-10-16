# Price Change Analyzer - Find Extreme Price Moves with Whale Activity

## What Does This Tool Do?

Analyzes historical price data from InfluxDB to find time intervals with the largest price changes, then correlates those movements with whale order book events that occurred during the same period.

**Key insight:** See exactly what large orders appeared, increased, or executed during the most volatile price movements.

## Quick Start

```bash
# Find top 10 price changes in last 24 hours using 1-minute windows
python live/price_change_analyzer.py

# Analyze 1-second intervals over last hour (high granularity)
python live/price_change_analyzer.py --interval 1s --lookback 1h

# Find movements >0.5% in last 6 hours using 5-second windows
python live/price_change_analyzer.py --interval 5s --lookback 6h --min-change 0.5 --top 20

# Different symbol
python live/price_change_analyzer.py --symbol ETH_USDT --interval 10s --lookback 12h

# Export results to JSON for further analysis
python live/price_change_analyzer.py --output json --export-path results.json

# Export to CSV for spreadsheet analysis
python live/price_change_analyzer.py --output csv --export-path analysis.csv

# Export LLM-optimized summary (90%+ smaller, perfect for AI analysis)
python live/price_change_analyzer.py --output json-summary
```

## Understanding the Output

### Terminal Display Format

```
================================================================================
Rank #1: +2.347% price change
Time: 2025-10-03 12:34:15 → 2025-10-03 12:35:15
Price: $93,245.50 → $95,433.21

Whale Activity Summary:
  market_buy      :  15 events, $4,250,000 total
  new_bid         :   8 events, $1,200,000 total
  increase        :  23 events, $3,100,000 total
  market_sell     :   3 events, $450,000 total

Event Timeline (42 events):
  12:34:18.123 market_buy       $93250.00 × 45.2500 = $4,220,625
  12:34:19.456 new_bid          $93100.00 × 10.5000 = $977,550
  12:34:21.789 increase         $93150.00 × 5.2000 = $484,380
  12:34:23.012 market_buy       $93280.00 × 8.7500 = $816,200
  ... and 38 more events
```

### What Each Section Shows

**Rank & Price Change:**
- Intervals are ranked by absolute price change percentage
- Shows both percentage change and dollar amount change
- Color coded: green for up moves, red for down moves

**Time Range:**
- Start and end timestamps of the interval
- Duration depends on your `--interval` setting

**Whale Activity Summary:**
- Aggregates all whale events by type
- Shows count of events per type
- Shows total USD volume per event type
- Helps you quickly see what dominated the interval

**Event Timeline:**
- Chronological list of whale events during the interval
- Shows first 20 events (if more, indicates how many truncated)
- Each event shows:
  - Timestamp (HH:MM:SS.mmm format)
  - Event type (color coded by side)
  - Price level
  - Volume
  - USD value

### Event Types Explained

**Market Events (Aggressive):**
- `market_buy` (green) - Large market buy order executed
- `market_sell` (red) - Large market sell order executed

**Order Book Events (Passive):**
- `new_bid` (green) - New large buy order appeared
- `new_ask` (red) - New large sell order appeared
- `increase` (cyan) - Volume added to existing order
- `decrease` (magenta) - Volume removed (filled or cancelled)
- `entered_top` - Order entered visible top N levels
- `left_top` - Order left visible top N levels

### Event Colors

- **Green**: Bullish events (bids, buys)
- **Red**: Bearish events (asks, sells)
- **Cyan**: Volume increases
- **Magenta**: Volume decreases
- **White**: Other events

## Command Line Options

### Required Arguments

None! Defaults to `BTC_USDT`, `24h` lookback, `1m` intervals.

### Optional Arguments

**Symbol:**
```bash
--symbol SYMBOL           # Trading pair (default: BTC_USDT)
```
Examples: `BTC_USDT`, `ETH_USDT`, `DOGE_USDT`, `WIF_USDT`

**Time Period:**
```bash
--lookback DURATION       # How far back to analyze (default: 24h)
```
Examples: `1h`, `6h`, `12h`, `24h`, `7d`

**Interval Size:**
```bash
--interval DURATION       # Window size for price changes (default: 1m)
```
Examples: `1s`, `5s`, `10s`, `30s`, `1m`, `5m`, `15m`, `30m`, `1h`

**Filtering:**
```bash
--min-change PERCENT      # Minimum price change % to consider (default: 0.1)
--top N                   # Number of top intervals to show (default: 10)
```

**Output Format:**
```bash
--output FORMAT           # terminal, json, json-summary, or csv (default: terminal)
--export-path PATH        # Custom export file path (auto-generated if not specified)
```

## Example Use Cases

### 1. Find Rapid Micro-Moves (1-second precision)
```bash
python live/price_change_analyzer.py --interval 1s --lookback 1h --min-change 0.05
```
**Use case:** See sub-second price spikes and what whale orders triggered them

### 2. Analyze Significant Short-Term Moves
```bash
python live/price_change_analyzer.py --interval 5s --lookback 6h --min-change 0.2
```
**Use case:** Find 5-second windows with >0.2% moves in last 6 hours

### 3. Study Medium-Term Volatility
```bash
python live/price_change_analyzer.py --interval 1m --lookback 24h --min-change 0.5 --top 20
```
**Use case:** Top 20 minute-long intervals with >0.5% price changes

### 4. Long-Form Analysis
```bash
python live/price_change_analyzer.py --interval 15m --lookback 7d --min-change 1.0
```
**Use case:** Find 15-minute periods with >1% moves over the past week

### 5. Export for Further Analysis
```bash
python live/price_change_analyzer.py --interval 5s --lookback 12h --output json
```
**Use case:** Export data as JSON for custom analysis scripts

### 6. Multi-Symbol Comparison
```bash
# Run for multiple symbols
python live/price_change_analyzer.py --symbol BTC_USDT --interval 1m --output json
python live/price_change_analyzer.py --symbol ETH_USDT --interval 1m --output json
python live/price_change_analyzer.py --symbol DOGE_USDT --interval 1m --output json
```
**Use case:** Compare which asset had most volatile intervals

### 7. LLM-Friendly Export for AI Analysis
```bash
python live/price_change_analyzer.py --symbol SPX_USDT --lookback 6h --interval 10s --output json-summary
```
**Use case:** Generate compact summaries for feeding to Claude/GPT-4 for pattern analysis, avoiding context window limits

## Trading Insights to Look For

### Pattern 1: Market Buy Cascade (Price Surge)
```
Rank #1: +1.234% price change

Whale Activity Summary:
  market_buy      :  45 events, $25,000,000 total
  market_sell     :   2 events, $500,000 total
```
**Interpretation:** Aggressive buying dominated the interval. Buyers were taking liquidity.

### Pattern 2: Wall Building Before Move
```
Rank #1: +0.856% price change

Event Timeline:
  12:00:01 new_bid    $93000.00 × 50.0000 = $4,650,000
  12:00:03 new_bid    $93050.00 × 40.0000 = $3,722,000
  12:00:05 new_bid    $93100.00 × 60.0000 = $5,586,000
  12:00:10 market_buy $93150.00 × 100.0000 = $9,315,000
```
**Interpretation:** Large bids stacked before price moved up. Possible coordinated accumulation.

### Pattern 3: Spoofing / Wall Removal
```
Rank #1: -0.932% price change

Event Timeline:
  12:05:00 new_ask     $94000.00 × 200.0000 = $18,800,000
  12:05:02 decrease    $94000.00 × 180.0000 = $16,920,000
  12:05:05 market_sell $93800.00 × 50.0000 = $4,690,000
```
**Interpretation:** Large sell wall appeared then vanished, followed by selling. Possible manipulation.

### Pattern 4: Absorption (Orders Filled)
```
Rank #1: -1.145% price change

Whale Activity Summary:
  decrease        :  67 events, $15,000,000 total
  market_sell     :  23 events, $8,500,000 total
```
**Interpretation:** Heavy selling into bids. Support levels being absorbed.

### Pattern 5: Balanced but Volatile
```
Rank #1: +0.456% price change

Whale Activity Summary:
  market_buy      :  15 events, $5,000,000 total
  market_sell     :  14 events, $4,800,000 total
  increase        :  25 events, $3,200,000 total
```
**Interpretation:** High activity but balanced. Choppy price action with no clear winner.

## Understanding the Data Source

### Prerequisites
This tool requires:
1. **InfluxDB** running with data from `orderbook_tracker.py`
2. Two measurements in InfluxDB:
   - `orderbook_price` - Price snapshots (mid_price, best_bid, best_ask, spread)
   - `orderbook_whale_events` - Filtered whale events

### Data Flow
```
orderbook_tracker.py → InfluxDB → price_change_analyzer.py
   (collects data)    (stores)      (analyzes)
```

**Important:** You must run `orderbook_tracker.py --influx` to collect data before using this analyzer.

### How It Works

1. **Query Price Data:**
   - Fetches `mid_price` from InfluxDB for the lookback period
   - Uses `aggregateWindow` to find first and last price in each interval
   - Calculates percentage change: `(end_price - start_price) / start_price * 100`

2. **Filter & Rank:**
   - Keeps only intervals with `abs(change) >= min_change`
   - Sorts by absolute change (largest moves first)
   - Returns top N intervals

3. **Correlate Whale Events:**
   - For each top interval, queries `orderbook_whale_events`
   - Fetches all events within the interval's time range
   - **Extended Context:** Shows 10x interval time before and after for comprehensive pattern analysis
   - Groups by event type and aggregates USD volume

4. **Display Results:**
   - Shows ranked intervals with price change info
   - Summarizes whale activity by type
   - Lists chronological event timeline

## Output Format Details

### Terminal Output
- Color-coded, human-readable format
- Shows event summaries and timelines
- Limited to first 20 events per interval for readability

### JSON Output
```json
[
  {
    "rank": 1,
    "start_time": "2025-10-03T12:34:15.000000Z",
    "end_time": "2025-10-03T12:35:15.000000Z",
    "start_price": 93245.5,
    "end_price": 95433.21,
    "change_pct": 2.347,
    "whale_events": [
      {
        "time": "2025-10-03T12:34:18.123000Z",
        "event_type": "market_buy",
        "side": "buy",
        "price": 93250.0,
        "volume": 45.25,
        "usd_value": 4220625.0,
        "distance_from_mid_pct": 0.005
      }
    ],
    "event_summary": {
      "market_buy": {"count": 15, "total_usd": 4250000.0},
      "new_bid": {"count": 8, "total_usd": 1200000.0}
    }
  }
]
```

### CSV Output
```csv
Rank,Start Time,End Time,Start Price,End Price,Change %,Event Count,Event Types,Total USD Volume
1,2025-10-03T12:34:15,2025-10-03T12:35:15,93245.50,95433.21,2.347,42,"market_buy, new_bid, increase",8600000
```

### JSON Summary Output (LLM-Optimized)

**NEW:** The `json-summary` format creates AI-friendly exports with **90-96% size reduction** while preserving all key insights.

**Why use it?**
- Full JSON exports can be 5-10MB+ (too large for LLM context windows)
- Summary exports are typically 50-200KB (perfect for Claude, GPT-4, etc.)
- Retains all critical information: price spikes, whale patterns, aggregate statistics
- Ideal for automated analysis, pattern recognition, or AI-assisted trading insights

**What's included:**
```json
{
  "metadata": {
    "symbol": "BANANA_USDT",
    "lookback": "3h",
    "interval": "10s",
    "format": "llm_summary",
    "note": "LLM-optimized summary with ~90% size reduction"
  },
  "summary_stats": {
    "total_intervals": 5,
    "biggest_spike_pct": 0.813,
    "biggest_spike_time": "2025-10-03T17:57:52Z",
    "avg_change_pct": 0.813,
    "price_volatility": 0.0
  },
  "intervals": [
    {
      "rank": 1,
      "start_time": "...",
      "change_pct": 0.813,
      "price_data_summary": {
        "total_points": 201,      // Original had 201 price points
        "sampled_points": 24,     // Intelligently sampled to 24 key points
        "key_prices": [...],       // Critical price movements only
        "price_range": { "min": 19.008, "max": 19.163, "avg": 19.082 }
      },
      "whale_events_summary": {
        "before": {
          "period": "before",
          "total_events": 436,
          "total_volume_usd": 4436764.44,
          "biggest_whale_usd": 398933.28,
          "event_types": { "entered_top": {"count": 183, "volume": 2182219.73}, ... },
          "sides": { "bid": {"count": 232, "volume": 3170283.48}, ... },
          "top_5_events": [...]   // Only top 5 largest whales shown
        },
        "during": { ... },        // Same structure for spike period
        "after": { ... }          // Same structure for after period
      }
    }
  ]
}
```

**How it reduces size:**

1. **Price Data Sampling (500+ → 20-30 points):**
   - Before spike: First 3 + Last 3 points
   - During spike: First + Last + 10 biggest price changes
   - After spike: First 3 + Last 3 points
   - Preserves volatility patterns while removing redundant data

2. **Whale Event Summarization:**
   - Full export: ALL whale events (often 100-500 per interval)
   - Summary: Top 5 events + aggregate statistics
   - Includes: total count, total volume, event type breakdown, side distribution

3. **Smart Aggregation:**
   - Original: Every single price tick and whale order
   - Summary: Statistical overview + critical inflection points
   - Result: 96.6% smaller (7.5MB → 61KB in real test)

**Example usage:**
```bash
# Generate summary for AI analysis
python live/price_change_analyzer.py \
  --symbol BANANA_USDT \
  --lookback 3h \
  --interval 10s \
  --top 5 \
  --min-change 0.1 \
  --output json-summary

# Output:
# Exported summary to data/price_changes_BANANA_USDT_20251003_215902_summary.json
# Size reduction: 96.6% (1,800,412 → 61,673 bytes)
```

**What you can do with summaries:**
- Feed to Claude/GPT for pattern analysis: "What whale patterns preceded the biggest spike?"
- Train ML models on price movement correlations
- Generate automated trading insights
- Build pattern recognition systems
- Share analysis without massive file transfers

## Performance Considerations

### Interval Size vs Query Speed

**Fast queries (1s - 10s intervals):**
- More granular data
- More intervals to analyze
- Suitable for short lookback periods (1h - 6h)

**Medium queries (1m - 5m intervals):**
- Balanced granularity
- Good for 12h - 24h lookback
- Recommended for most use cases

**Slow queries (15m - 1h intervals):**
- Lower granularity
- Fewer intervals
- Suitable for long lookback (7d+)

### Tips for Large Datasets

1. **Start with larger intervals** for initial exploration
2. **Narrow down time range** if specific period interests you
3. **Use min-change filter** to reduce result set
4. **Export to JSON/CSV** for heavy analysis (faster than terminal)

## Common Questions

**Q: What if no data is found?**
A: Make sure `orderbook_tracker.py --influx` is running and has collected data for your symbol and time period.

**Q: Can I analyze historical data from weeks ago?**
A: Yes, as long as the data exists in InfluxDB and hasn't been deleted by retention policies.

**Q: What's a good interval size?**
A: Start with `1m` for general analysis. Use `5s` or `10s` for high-frequency moves. Use `15m` for longer-term patterns.

**Q: Why do some intervals have no whale events?**
A: Price can move without whale activity (many small orders) or whale events may have been filtered out by tracker's min_volume/min_usd settings.

**Q: How accurate is the timing?**
A: Timestamps are precise to milliseconds. However, interval boundaries are aggregated (e.g., 1-minute window groups all events in that minute).

**Q: Can I see the raw InfluxDB queries?**
A: Yes, check the `find_price_changes()` and `get_whale_events()` methods in the source code.

**Q: Does this analyze live data?**
A: No, it analyzes historical data stored in InfluxDB. For live monitoring, use `orderbook_tracker.py` or `orderbook_monitor.py`.

**Q: What's the difference between this and orderbook_monitor.py?**
A: `orderbook_monitor.py` shows current prices and recent whale events. This tool finds and ranks the most extreme price moves.

**Q: What's the difference between `json` and `json-summary` output?**
A:
- `json`: Full export with ALL price points and whale events (5-10MB+)
- `json-summary`: Intelligent summary with sampled data (50-200KB, 90-96% smaller)
- Use `json` for complete data archival
- Use `json-summary` for AI analysis, ML training, or when file size matters

**Q: Does the summary lose important information?**
A: No! It preserves:
- All interval rankings and price changes
- Top 5 largest whale events per period
- Complete aggregate statistics (total volume, event counts, side distribution)
- Key price inflection points (spikes, reversals)
- What it removes: redundant price ticks and smaller whale events that don't affect patterns

## Tips for Effective Analysis

1. **Start broad, then narrow** - Begin with default settings, then adjust interval/lookback based on what you find

2. **Compare event summaries** - Look at ratio of market_buy vs market_sell to gauge aggressor direction

3. **Watch for patterns** - Same event types appearing before similar price moves = potential signal

4. **Cross-reference with chart** - Use exported data alongside price charts for visual confirmation

5. **Export for deeper analysis** - JSON output can be processed by other tools (Python, R, Excel)

6. **Look for imbalance** - Heavy buying or selling usually precedes continuation of the move

7. **Note the order** - Events at start of interval might have caused the move; events at end might be reaction

8. **Use summaries for LLM analysis** - Export with `--output json-summary` and feed to Claude/GPT for automated pattern detection and insights

## Exit

Press **Ctrl+C** to interrupt analysis (though most queries complete quickly).

## Related Tools

- `orderbook_tracker.py` - Collects live order book data (writes to InfluxDB)
- `orderbook_monitor.py` - Real-time dashboard display (reads from InfluxDB)
- `price_change_analyzer.py` - Historical volatility analysis (this tool)
