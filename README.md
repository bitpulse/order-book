# MEXC Order Book Collector

A high-performance Python application for collecting real-time order book data from MEXC futures markets and storing it in InfluxDB. Features whale order detection, market depth analysis, and comprehensive metrics tracking.

## Features

- 🚀 Real-time WebSocket connection to MEXC futures
- 📊 Full order book depth tracking (20 levels)
- 🐋 Whale order detection with configurable thresholds
- 📈 Market depth analysis at multiple percentage levels
- 💾 Efficient batch storage to InfluxDB
- 🔄 Automatic reconnection and error handling
- 📝 Comprehensive logging and monitoring
- 🐳 Docker support for easy deployment

## Data Collected

1. **Order Book Snapshots**: All bid/ask levels with price, volume, and order counts
2. **Aggregated Statistics**: Best bid/ask, spread, mid-price, imbalance, total volumes
3. **Market Depth**: Volume distribution at 0.1%, 0.5%, 1%, 2%, and 5% from mid-price
4. **Whale Orders**: Large orders categorized as large/huge/mega with detailed metrics

## Quick Start

### Prerequisites

- Python 3.11+
- InfluxDB 2.x
- Docker & Docker Compose (optional)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/order-book.git
cd order-book
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment:
```bash
cp .env.example .env
# Edit .env with your InfluxDB credentials and preferences
```

### Running Locally

```bash
python run.py
```

### Running with Docker

```bash
# Start InfluxDB and the collector
docker-compose up -d

# View logs
docker-compose logs -f orderbook-collector

# Stop services
docker-compose down
```

## Configuration

Edit `.env` file to customize:

- **InfluxDB**: Connection URL, token, organization, and bucket
- **Trading Pairs**: Comma-separated list (e.g., `BTC_USDT,ETH_USDT,SOL_USDT`)
- **Whale Thresholds**: USD values for large/huge/mega order detection
- **Performance**: Batch size and timeout for InfluxDB writes
- **Logging**: Log level and file location

## InfluxDB Queries

### Find Recent Whale Orders
```sql
SELECT * FROM whale_orders
WHERE symbol = 'BTC_USDT'
  AND time > now() - 1h
ORDER BY value_usdt DESC
```

### Check Current Spread
```sql
SELECT last(spread_percentage) as spread,
       last(best_bid) as bid,
       last(best_ask) as ask
FROM order_book_stats
WHERE symbol = 'BTC_USDT'
```

### Analyze Market Depth
```sql
SELECT mean(bid_volume) as avg_bid_volume,
       mean(ask_volume) as avg_ask_volume
FROM market_depth
WHERE symbol = 'BTC_USDT'
  AND depth_percentage = '1%'
  AND time > now() - 15m
```

## Architecture

```
┌─────────────┐     WebSocket      ┌──────────────┐
│    MEXC     │◄──────────────────►│   Collector  │
│   Futures   │                    │              │
└─────────────┘                    └──────┬───────┘
                                          │
                                    Process Data
                                          │
                                          ▼
                              ┌─────────────────────┐
                              │   Order Book        │
                              │   Processor         │
                              │ • Parse messages    │
                              │ • Detect whales     │
                              │ • Calculate depth   │
                              └──────────┬──────────┘
                                        │
                                   Store Batch
                                        │
                                        ▼
                              ┌─────────────────────┐
                              │     InfluxDB        │
                              │   Time Series DB    │
                              └─────────────────────┘
```

## Monitoring

The application logs important events:

- 📊 Real-time order book updates with spreads and imbalance
- 🐋 Whale order detections with price and value
- ⚠️ Connection issues and reconnection attempts
- ✅ Successful data batch writes to InfluxDB

## Performance

- Processes ~1 update per second per trading pair
- Batches writes to InfluxDB for efficiency
- Automatic reconnection on connection loss
- Memory-efficient with streaming data processing

## License

MIT
