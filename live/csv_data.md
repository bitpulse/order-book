# Order Book CSV Data Format

## Overview
The `orderbook_tracker.py` script logs all order book events to CSV files in the `logs/` directory for later analysis.

## File Naming
`logs/orderbook_{SYMBOL}_{TIMESTAMP}.csv`

Example: `logs/orderbook_WIF_USDT_20251001_214530.csv`

## CSV Columns

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | ISO datetime | When the event occurred (e.g., `2025-10-01T21:42:50.632+00:00`) |
| `type` | string | Event type: `new`, `increase`, or `removed` |
| `side` | string | Order side: `bid` or `ask` |
| `price` | float | Order price level |
| `volume` | float | Volume at this price (for `new`) or volume change (for `increase`/`removed`) |
| `usd_value` | float | USD value = price × volume |
| `distance_from_mid_pct` | float | Distance from mid-price as percentage (negative = below mid, positive = above mid) |
| `best_bid` | float | Best bid price at the time of event |
| `best_ask` | float | Best ask price at the time of event |
| `spread` | float | Spread (best_ask - best_bid) at the time of event |
| `info` | string | Additional context: `BEST` (if at best bid/ask), `total:X` (total volume after increase), or empty |

## Event Types

### 1. `new` - New Order Appeared
A new order appeared at a price level that didn't exist before.
- `volume`: Total volume at this new price level
- `usd_value`: Total USD value of the new order
- `info`: `BEST` if this is at the best bid/ask, otherwise empty

### 2. `increase` - Volume Increased
Volume increased significantly at an existing price level.
- `volume`: The increase amount (delta)
- `usd_value`: USD value of the increase only
- `info`: `total:X` where X is the total volume after the increase

### 3. `removed` - Order Removed
An order was completely removed from the book.
- `volume`: The volume that was removed
- `usd_value`: USD value of the removed volume
- `info`: Empty

## Filtering

Only events that pass both filters are logged:
- `--min-volume`: Minimum volume threshold
- `--min-usd`: Minimum USD value threshold

Both filters apply to:
- New orders (checks total volume/USD)
- Volume increases (checks increase delta)
- Removed orders (checks removed volume/USD)

## Example Rows

```csv
timestamp,type,side,price,volume,usd_value,distance_from_mid_pct,best_bid,best_ask,spread,info
2025-10-01T21:42:50.632+00:00,new,bid,0.7508,89700.0,67348.16,0.06,0.7508,0.7515,0.0007,BEST
2025-10-01T21:42:52.782+00:00,increase,bid,0.7507,72100.0,54125.47,0.06,0.7508,0.7515,0.0007,total:170200.0
2025-10-01T21:42:56.990+00:00,removed,ask,0.7518,77500.0,58270.0,0.0,0.7508,0.7519,0.0011,
```

## Use Cases

This CSV data enables analysis of:
- Large order flow patterns (whale activity)
- Order book liquidity changes over time
- Price level support/resistance based on order accumulation
- Spread dynamics and market depth
- Correlation between large orders and price movements
- Market maker behavior at different price levels
