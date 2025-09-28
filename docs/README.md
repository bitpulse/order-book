# MEXC Order Book Collector Documentation

## 📚 Documentation Index

### Getting Started
- [Overview](./overview.md) - Project overview and features
- [Quick Start](./quickstart.md) - Get up and running in 5 minutes
- [Configuration](./configuration.md) - Environment variables and settings

### Data & Storage
- [InfluxDB Schema](./influxdb-schema.md) - Complete database schema documentation
- [Data Flow](./data-flow.md) - How data moves through the system
- [Query Examples](./queries.md) - Common InfluxDB queries and analysis

### Architecture
- [System Architecture](./architecture.md) - Component design and interactions
- [API Reference](./api-reference.md) - Module and class documentation
- [WebSocket Protocol](./websocket-protocol.md) - MEXC WebSocket implementation

### Operations
- [Deployment Guide](./deployment.md) - Production deployment instructions
- [Monitoring](./monitoring.md) - Health checks and alerting
- [Troubleshooting](./troubleshooting.md) - Common issues and solutions

### Development
- [Contributing](./contributing.md) - Development setup and guidelines
- [Testing](./testing.md) - Testing strategies and tools

---

## 🚀 Quick Links

- [InfluxDB Schema](./influxdb-schema.md) - See exactly how data is stored
- [Query Examples](./queries.md) - Ready-to-use InfluxDB queries
- [Deployment Guide](./deployment.md) - Deploy to production

## 📊 Project Overview

The MEXC Order Book Collector is a high-performance system for collecting real-time order book data from MEXC futures markets. It captures:

- Full order book depth (20 levels)
- Market statistics and metrics
- Whale order detection
- Market depth analysis

All data is stored in InfluxDB for time-series analysis.