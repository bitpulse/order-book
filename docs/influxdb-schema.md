# InfluxDB Schema Documentation

## Overview

The MEXC Order Book Collector stores data in InfluxDB 2.x using four distinct measurements. Each measurement is optimized for specific queries and analysis patterns.

## Measurements

### 1. `order_book_snapshot`

Stores the complete order book state at each timestamp, capturing all 20 levels of bids and asks.

#### Tags (Indexed Fields)
| Tag | Type | Values | Description |
|-----|------|--------|-------------|
| `symbol` | string | "WIF_USDT", "BTC_USDT", etc. | Trading pair identifier |
| `exchange` | string | "MEXC" | Exchange name |
| `side` | string | "bid" \| "ask" | Order side |
| `level` | string | "1" to "20" | Depth level (1 = best price) |

#### Fields (Data Values)
| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `price` | float64 | Price at this level | 0.7124 |
| `volume` | float64 | Token volume at this price | 24608.0 |
| `order_count` | int64 | Number of orders at this level | 3 |
| `total_value` | float64 | price × volume in USDT | 17530.74 |

#### Line Protocol Example
```
order_book_snapshot,symbol=WIF_USDT,exchange=MEXC,side=bid,level=1 price=0.7124,volume=24608,order_count=1,total_value=17530.74 1759063868116000000
```

#### Storage Pattern
- **Frequency**: Every second
- **Points per update**: 40 (20 bid levels + 20 ask levels)
- **Retention**: 30 days (configurable)

---

### 2. `order_book_stats`

Aggregated statistics calculated from the order book snapshot.

#### Tags (Indexed Fields)
| Tag | Type | Values | Description |
|-----|------|--------|-------------|
| `symbol` | string | "WIF_USDT", etc. | Trading pair identifier |
| `exchange` | string | "MEXC" | Exchange name |

#### Fields (Data Values)
| Field | Type | Description | Range/Example |
|-------|------|-------------|---------------|
| `best_bid` | float64 | Highest bid price | 0.7124 |
| `best_ask` | float64 | Lowest ask price | 0.7125 |
| `spread` | float64 | ask - bid | 0.0001 |
| `spread_percentage` | float64 | (spread/ask) × 100 | 0.014 |
| `mid_price` | float64 | (bid + ask) / 2 | 0.71245 |
| `bid_volume_total` | float64 | Sum of all bid volumes | 1543210.0 |
| `ask_volume_total` | float64 | Sum of all ask volumes | 1678432.0 |
| `bid_value_total` | float64 | Total USDT on bid side | 1098567.43 |
| `ask_value_total` | float64 | Total USDT on ask side | 1195789.56 |
| `imbalance` | float64 | (bid_vol - ask_vol) / (bid_vol + ask_vol) | -0.125 to 1.0 |
| `depth_10_bid` | float64 | Volume in top 10 bid levels | 876543.0 |
| `depth_10_ask` | float64 | Volume in top 10 ask levels | 923456.0 |

#### Line Protocol Example
```
order_book_stats,symbol=WIF_USDT,exchange=MEXC best_bid=0.7124,best_ask=0.7125,spread=0.0001,spread_percentage=0.014,mid_price=0.71245,bid_volume_total=1543210,ask_volume_total=1678432,bid_value_total=1098567.43,ask_value_total=1195789.56,imbalance=-0.125,depth_10_bid=876543,depth_10_ask=923456 1759063868116000000
```

#### Storage Pattern
- **Frequency**: Every second
- **Points per update**: 1 (all fields in single point)
- **Use cases**: Spread analysis, market health monitoring, imbalance detection

---

### 3. `market_depth`

Volume distribution at various percentage distances from the mid-price.

#### Tags (Indexed Fields)
| Tag | Type | Values | Description |
|-----|------|--------|-------------|
| `symbol` | string | "WIF_USDT", etc. | Trading pair identifier |
| `exchange` | string | "MEXC" | Exchange name |
| `depth_percentage` | string | "0.1%", "0.5%", "1%", "2%", "5%" | Distance from mid-price |

#### Fields (Data Values)
| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `bid_volume` | float64 | Total volume within X% below mid | 150000.0 |
| `ask_volume` | float64 | Total volume within X% above mid | 175000.0 |
| `bid_orders` | int64 | Order count within X% below mid | 45 |
| `ask_orders` | int64 | Order count within X% above mid | 52 |
| `bid_value` | float64 | Total USDT within X% below mid | 106500.0 |
| `ask_value` | float64 | Total USDT within X% above mid | 124475.0 |

#### Line Protocol Example
```
market_depth,symbol=WIF_USDT,exchange=MEXC,depth_percentage=1% bid_volume=150000,ask_volume=175000,bid_orders=45,ask_orders=52,bid_value=106500,ask_value=124475 1759063868116000000
```

#### Storage Pattern
- **Frequency**: Every second
- **Points per update**: 5 (one per depth percentage)
- **Use cases**: Support/resistance analysis, liquidity profiling

---

### 4. `whale_orders`

Large orders that exceed configurable thresholds (default: $50,000).

#### Tags (Indexed Fields)
| Tag | Type | Values | Description |
|-----|------|--------|-------------|
| `symbol` | string | "WIF_USDT", etc. | Trading pair identifier |
| `exchange` | string | "MEXC" | Exchange name |
| `side` | string | "bid" \| "ask" | Order side |

#### Fields (Data Values)
| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `price` | float64 | Order price | 0.713 |
| `volume` | float64 | Order volume in tokens | 86205.0 |
| `value_usdt` | float64 | Order value in USDT | 61444.0 |
| `level` | int64 | Position in order book | 5 |
| `distance_from_mid` | float64 | % distance from mid-price | 0.14 |
| `distance_from_mid_abs` | float64 | Absolute price distance | 0.001 |

#### Whale Detection Thresholds
| Trading Pair | Minimum Value |
|-------------|---------------|
| BTC_USDT | $100,000 |
| ETH_USDT | $50,000 |
| Others | $50,000 |

#### Line Protocol Example
```
whale_orders,symbol=WIF_USDT,exchange=MEXC,side=ask price=0.713,volume=86205,value_usdt=61444,level=5,distance_from_mid=0.14,distance_from_mid_abs=0.001 1759063868116000000
```

#### Query Examples for Analysis
```sql
-- Categorize whales by value in queries
SELECT
  CASE
    WHEN value_usdt >= 1000000 THEN 'mega'
    WHEN value_usdt >= 500000 THEN 'huge'
    WHEN value_usdt >= 100000 THEN 'large'
    ELSE 'standard'
  END as category,
  COUNT(*) as count
FROM whale_orders
WHERE time > now() - 1h
GROUP BY category
```

#### Storage Pattern
- **Frequency**: Only when detected
- **Points per update**: Variable (0-50+ depending on market)
- **Use cases**: Whale tracking, manipulation detection, large order analysis

---

## Data Flow

```
MEXC WebSocket (1/sec)
        ↓
   Parse Message
        ↓
  Create Snapshot ──→ order_book_snapshot (40 points)
        ↓
 Calculate Stats ──→ order_book_stats (1 point)
        ↓
 Calculate Depth ──→ market_depth (5 points)
        ↓
  Detect Whales ──→ whale_orders (0-N points)
        ↓
   Batch Write
        ↓
    InfluxDB
```

## Storage Estimates

For a single trading pair with average activity:

| Measurement | Points/Second | Points/Day | Storage/Day |
|-------------|---------------|------------|-------------|
| order_book_snapshot | 40 | 3,456,000 | ~276 MB |
| order_book_stats | 1 | 86,400 | ~10 MB |
| market_depth | 5 | 432,000 | ~35 MB |
| whale_orders | ~0.1 | ~8,640 | ~1 MB |
| **Total** | **~46** | **~4M** | **~322 MB** |

Note: whale_orders storage is minimal since we only store orders > $50K without categorization.

## Query Performance

### Optimized Queries
- Filter by tags (symbol, exchange, side, level)
- Time range queries with range()
- Last value queries with last()

### Example Efficient Query
```flux
from(bucket: "trading_data")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "order_book_stats")
  |> filter(fn: (r) => r.symbol == "WIF_USDT")
  |> filter(fn: (r) => r._field == "spread_percentage")
  |> aggregateWindow(every: 1m, fn: mean)
```

## Best Practices

1. **Use Tags for Filtering**: Tags are indexed and provide fast lookups
2. **Minimize Cardinality**: Keep tag values finite and predictable
3. **Batch Writes**: Group multiple points together (we use 100 points or 1 second)
4. **Set Retention Policies**: Configure based on storage capacity and analysis needs
5. **Use Continuous Queries**: For downsampling historical data

## Retention Policies

Recommended setup:

```sql
-- Raw data (7 days)
CREATE RETENTION POLICY "7d_raw" ON "trading_data" DURATION 7d REPLICATION 1 DEFAULT

-- 1-minute aggregates (30 days)
CREATE RETENTION POLICY "30d_1m" ON "trading_data" DURATION 30d REPLICATION 1

-- 1-hour aggregates (1 year)
CREATE RETENTION POLICY "1y_1h" ON "trading_data" DURATION 365d REPLICATION 1
```