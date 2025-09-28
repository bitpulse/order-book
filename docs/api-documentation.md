# Order Book Analytics API Documentation

## Overview

The Order Book Analytics API provides REST endpoints for querying real-time and historical order book data collected from MEXC futures markets. Built with FastAPI, it offers automatic documentation, high performance, and easy integration.

## Quick Start

### Starting the API

```bash
# Install dependencies
pip install -r requirements.txt

# Start the API server
python run_api.py

# API will be available at:
# http://localhost:8000
```

### Documentation URLs

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI Schema**: http://localhost:8000/openapi.json

## Base URL

```
http://localhost:8000/api/v1
```

## Endpoints

### Order Book Endpoints

#### Get Current Order Book
```http
GET /api/v1/orderbook/{symbol}
```

Returns the full 20-level order book with bids and asks.

**Parameters:**
- `symbol` (path): Trading pair symbol (e.g., "WIF_USDT")

**Response:**
```json
{
  "symbol": "WIF_USDT",
  "timestamp": "2025-09-28T16:50:20.150Z",
  "bids": [
    {"price": 0.7124, "volume": 24608, "total_value": 17530.74},
    ...
  ],
  "asks": [
    {"price": 0.7125, "volume": 31205, "total_value": 22233.56},
    ...
  ],
  "best_bid": 0.7124,
  "best_ask": 0.7125,
  "spread": 0.0001,
  "spread_percentage": 0.014
}
```

#### Get Best Prices
```http
GET /api/v1/orderbook/{symbol}/best
```

Lightweight endpoint for current top of book.

**Response:**
```json
{
  "symbol": "WIF_USDT",
  "timestamp": "2025-09-28T16:50:20.150Z",
  "best_bid": 0.7124,
  "best_ask": 0.7125,
  "mid_price": 0.71245,
  "spread": 0.0001,
  "spread_percentage": 0.014
}
```

#### Get Order Book Statistics
```http
GET /api/v1/orderbook/{symbol}/stats
```

Returns comprehensive order book metrics.

**Response:**
```json
{
  "symbol": "WIF_USDT",
  "timestamp": "2025-09-28T16:50:20.150Z",
  "best_bid": 0.7124,
  "best_ask": 0.7125,
  "spread": 0.0001,
  "spread_percentage": 0.014,
  "mid_price": 0.71245,
  "bid_volume_total": 1543210,
  "ask_volume_total": 1678432,
  "bid_value_total": 1098567.43,
  "ask_value_total": 1195789.56,
  "imbalance": -0.125,
  "depth_10_bid": 876543,
  "depth_10_ask": 923456
}
```

#### Get Spread History
```http
GET /api/v1/orderbook/{symbol}/spread/history
```

**Query Parameters:**
- `start` (optional): Time range, default "-1h" (e.g., "-24h", "-7d")
- `interval` (optional): Aggregation interval, default "1m" (e.g., "5m", "1h")

**Response:**
```json
[
  {
    "timestamp": "2025-09-28T16:00:00Z",
    "spread": 0.0001,
    "spread_percentage": 0.014
  },
  ...
]
```

#### Get Market Depth
```http
GET /api/v1/orderbook/{symbol}/depth
```

**Query Parameters:**
- `percentage` (optional): Specific depth percentage (e.g., "0.1%", "1%", "5%")

**Response:**
```json
[
  {
    "depth_percentage": "0.1%",
    "timestamp": "2025-09-28T16:50:20Z",
    "bid_volume": 150000,
    "ask_volume": 175000,
    "bid_orders": 45,
    "ask_orders": 52,
    "bid_value": 106500,
    "ask_value": 124475
  },
  ...
]
```

#### Get Imbalance History
```http
GET /api/v1/orderbook/{symbol}/imbalance/history
```

**Query Parameters:**
- `start` (optional): Time range, default "-1h"
- `interval` (optional): Aggregation interval, default "1m"

**Response:**
```json
[
  {
    "timestamp": "2025-09-28T16:00:00Z",
    "imbalance": -0.125
  },
  ...
]
```

### Whale Tracking Endpoints

#### Get Recent Whale Orders
```http
GET /api/v1/whales/recent
```

**Query Parameters:**
- `limit` (optional): Max results (1-1000), default 100
- `min_value` (optional): Minimum USD value, default 50000
- `symbol` (optional): Filter by symbol

**Response:**
```json
[
  {
    "symbol": "WIF_USDT",
    "timestamp": "2025-09-28T16:50:20Z",
    "side": "bid",
    "price": 0.713,
    "volume": 500000,
    "value_usdt": 356500,
    "level": 5,
    "distance_from_mid": 0.14
  },
  ...
]
```

#### Get Symbol-Specific Whales
```http
GET /api/v1/whales/{symbol}
```

Returns whale orders for a specific trading pair.

#### Get Whale Statistics
```http
GET /api/v1/whales/stats/summary
```

**Query Parameters:**
- `symbol` (optional): Filter by symbol
- `period` (optional): Time period, default "-24h"

**Response:**
```json
{
  "period": "-24h",
  "symbol": "WIF_USDT",
  "total_count": 156,
  "bid_count": 82,
  "ask_count": 74,
  "average_value": 125000
}
```

#### Get Active Whale Alerts
```http
GET /api/v1/whales/alerts/active
```

**Query Parameters:**
- `threshold` (optional): Alert threshold in USD, default 100000
- `max_distance` (optional): Max % distance from mid-price, default 1.0

**Response:**
```json
[
  {
    "alert_type": "whale_wall",
    "symbol": "WIF_USDT",
    "side": "bid",
    "price": 0.712,
    "value_usdt": 500000,
    "distance_from_mid": 0.5,
    "timestamp": "2025-09-28T16:50:20Z",
    "severity": "high"
  },
  ...
]
```

#### Get Whale Distribution
```http
GET /api/v1/whales/categories/distribution
```

**Query Parameters:**
- `symbol` (optional): Filter by symbol
- `period` (optional): Time period, default "-24h"

**Response:**
```json
{
  "period": "-24h",
  "symbol": "WIF_USDT",
  "total_whales": 156,
  "total_value": 15600000,
  "categories": {
    "standard": {
      "count": 100,
      "total_value": 7500000,
      "range": "$50K-$100K",
      "count_percentage": 64.1,
      "value_percentage": 48.1
    },
    "large": {
      "count": 40,
      "total_value": 5000000,
      "range": "$100K-$500K",
      "count_percentage": 25.6,
      "value_percentage": 32.1
    },
    ...
  }
}
```

### Health & System Endpoints

#### Health Check
```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "influxdb_connected": true,
  "uptime_seconds": 3600
}
```

#### Root Information
```http
GET /
```

**Response:**
```json
{
  "name": "Order Book Analytics API",
  "version": "1.0.0",
  "status": "running",
  "documentation": "/docs",
  "endpoints": {
    "orderbook": "/api/v1/orderbook/{symbol}",
    "whales": "/api/v1/whales/recent",
    "health": "/health"
  }
}
```

## Error Responses

All endpoints return standard error responses:

```json
{
  "error": "Not Found",
  "detail": "No order book data found for INVALID_SYMBOL",
  "status_code": 404
}
```

## Rate Limiting

Default rate limit: 60 requests per minute per IP address (configurable)

## Time Ranges

Supported time range formats for `start` parameter:
- `-1m`: Last minute
- `-5m`: Last 5 minutes
- `-1h`: Last hour
- `-24h`: Last 24 hours
- `-7d`: Last 7 days
- `-30d`: Last 30 days

## Aggregation Intervals

Supported intervals for data aggregation:
- `1s`: 1 second
- `10s`: 10 seconds
- `1m`: 1 minute
- `5m`: 5 minutes
- `15m`: 15 minutes
- `1h`: 1 hour
- `1d`: 1 day

## WebSocket Support (Coming Soon)

WebSocket endpoints for real-time streaming:
- `ws://localhost:8000/ws/orderbook/{symbol}` - Live order book updates
- `ws://localhost:8000/ws/whales` - Real-time whale alerts

## Environment Configuration

Configure the API via `.env` file:

```env
# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_PREFIX=/api/v1

# InfluxDB Configuration
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=your-token
INFLUXDB_ORG=bitpulse
INFLUXDB_BUCKET=trading_data

# Optional Redis Cache
REDIS_URL=redis://localhost:6379
CACHE_TTL=5

# Rate Limiting
RATE_LIMIT_PER_MINUTE=60
```

## Docker Deployment

```dockerfile
# Add to docker-compose.yml
api:
  build: .
  ports:
    - "8000:8000"
  environment:
    - INFLUXDB_URL=http://influxdb:8086
  depends_on:
    - influxdb
```

## Client Examples

### Python
```python
import requests

# Get current order book
response = requests.get("http://localhost:8000/api/v1/orderbook/WIF_USDT")
orderbook = response.json()

# Get recent whales
response = requests.get(
    "http://localhost:8000/api/v1/whales/recent",
    params={"limit": 10, "min_value": 100000}
)
whales = response.json()
```

### JavaScript
```javascript
// Get best prices
fetch('http://localhost:8000/api/v1/orderbook/WIF_USDT/best')
  .then(response => response.json())
  .then(data => console.log(data));

// Get spread history
fetch('http://localhost:8000/api/v1/orderbook/WIF_USDT/spread/history?start=-24h&interval=1h')
  .then(response => response.json())
  .then(data => console.log(data));
```

### cURL
```bash
# Get order book stats
curl http://localhost:8000/api/v1/orderbook/WIF_USDT/stats

# Get whale statistics
curl "http://localhost:8000/api/v1/whales/stats/summary?symbol=WIF_USDT&period=-7d"
```

## Performance

- Async request handling with FastAPI
- Connection pooling for InfluxDB
- Optional Redis caching for frequently accessed data
- Typical response times: < 100ms for cached data, < 500ms for database queries

## Security

- CORS configuration for web clients
- Rate limiting to prevent abuse
- Input validation on all parameters
- SQL injection protection via parameterized queries

## Monitoring

- Health endpoint for uptime monitoring
- Structured logging with loguru
- Metrics exposed for Prometheus (optional)

## Support

For issues or questions:
- Check the automatic documentation at `/docs`
- Review error messages which include detailed information
- Check InfluxDB connectivity if seeing 500 errors