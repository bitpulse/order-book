# Backtesting Framework for Order Book Whale Trading Strategies

A comprehensive, production-ready backtesting system designed specifically for testing trading strategies based on order book whale activity, price movements, and market microstructure signals.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Core Components](#core-components)
- [Strategy Development](#strategy-development)
- [Performance Metrics](#performance-metrics)
- [Examples](#examples)
- [Best Practices](#best-practices)
- [Roadmap](#roadmap)

---

## 🎯 Overview

This backtesting framework allows you to:

- **Test trading strategies** on historical order book and whale event data
- **Simulate realistic execution** with fees, slippage, and delays
- **Calculate comprehensive metrics** (Sharpe ratio, drawdown, win rate, etc.)
- **Optimize parameters** to find the best strategy configuration
- **Validate strategies** with walk-forward analysis to avoid overfitting

**Designed for:** Cryptocurrency whale trading strategies using InfluxDB time-series data

---

## ✨ Features

### Data Integration
- ✅ Connects to existing InfluxDB (`orderbook_price`, `orderbook_whale_events`)
- ✅ Supports MongoDB for pre-computed analysis results
- ✅ Unified timeline creation with aggregated whale metrics
- ✅ Flexible time range selection (absolute or relative)

### Realistic Execution
- ✅ MEXC fee structure (0.02% maker, 0.06% taker)
- ✅ Configurable slippage models (fixed, volume-based, order book)
- ✅ Execution delays (default: 100ms)
- ✅ Bid-ask spread modeling

### Portfolio Management
- ✅ Cash and position tracking
- ✅ Multiple position sizing methods (fixed %, risk-based)
- ✅ Unrealized P&L updates
- ✅ Equity curve generation
- ✅ Drawdown tracking

### Performance Metrics
- ✅ Standard metrics (total return, win rate, profit factor)
- ✅ Risk-adjusted returns (Sharpe ratio, Sortino ratio)
- ✅ Drawdown analysis (max drawdown, duration)
- ✅ Trade statistics (avg win/loss, streaks, duration)
- ✅ Monthly returns (for heatmap visualization)

---

## 🏗️ Architecture

```
backtesting/
├── core/
│   ├── models.py          # Data models (Order, Position, Trade, BacktestResult)
│   ├── data_loader.py     # InfluxDB/MongoDB data fetching
│   ├── portfolio.py       # Portfolio & position management
│   ├── execution.py       # Realistic execution simulation
│   ├── metrics.py         # Performance metrics calculator
│   └── engine.py          # Main backtesting engine (TODO)
│
├── strategies/
│   ├── base_strategy.py   # Abstract strategy class (TODO)
│   └── whale_following.py # Whale following strategy (TODO)
│
├── signals/               # Signal generation modules (TODO)
├── risk/                  # Risk management modules (TODO)
├── analysis/              # Visualization & reporting (TODO)
└── utils/                 # Utility functions (TODO)
```

---

## 🚀 Installation

### Prerequisites

- Python 3.11+
- InfluxDB 2.x (with historical data)
- MongoDB (optional, for analysis results)

### Install Dependencies

```bash
cd /home/luka/bitpulse/order-book

# Install backtesting requirements
pip install pandas numpy scipy influxdb-client pymongo loguru
```

### Environment Setup

Ensure your `.env` file contains:

```bash
# InfluxDB
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=your_token_here
INFLUXDB_ORG=trading
INFLUXDB_BUCKET=trading_data

# MongoDB (optional)
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=orderbook_analytics
```

---

## 🎬 Quick Start

### 1. Load Historical Data

```python
from backtesting.core import DataLoader

# Initialize loader
loader = DataLoader()

# Fetch price data
prices = loader.get_price_data(
    symbol='BTC_USDT',
    start='2025-09-01',
    end='2025-10-01'
)

# Fetch whale events
whales = loader.get_whale_events(
    symbol='BTC_USDT',
    start='2025-09-01',
    end='2025-10-01',
    min_usd=100000  # Only whales >= $100K
)

# Create unified timeline
data = loader.create_unified_timeline(prices, whales, window_size='1min')

print(f"Loaded {len(data)} data points")
print(data.head())
```

### 2. Test Execution Simulation

```python
from backtesting.core import ExecutionSimulator

# Initialize simulator with MEXC fees
sim = ExecutionSimulator(
    maker_fee_pct=0.02,
    taker_fee_pct=0.06,
    slippage_pct=0.02
)

# Simulate market buy
fill_price, commission, slippage = sim.simulate_market_buy(
    order_price=42000,
    order_size=0.1,
    timestamp=datetime.now()
)

print(f"Fill price: ${fill_price:.2f}")
print(f"Commission: ${commission:.2f}")
print(f"Slippage: ${slippage:.2f}")

# Estimate round-trip cost
costs = sim.estimate_roundtrip_cost(price=42000, size=0.1)
print(f"Total round-trip cost: ${costs['total_cost']:.2f} ({costs['cost_pct']:.3f}%)")
```

### 3. Track Portfolio

```python
from backtesting.core import Portfolio
from backtesting.core.models import PositionSide

# Initialize portfolio
portfolio = Portfolio(
    initial_capital=10000,
    position_size_pct=10.0,  # Use 10% of capital per trade
    max_risk_per_trade_pct=2.0  # Risk max 2% per trade
)

# Open position
position = portfolio.open_position(
    symbol='BTC_USDT',
    side=PositionSide.LONG,
    entry_price=42000,
    size=0.023,  # Calculated size
    timestamp=datetime.now(),
    stop_loss=41700,
    take_profit=42500,
    commission=10.50,
    slippage=2.10
)

# Update with current price
portfolio.update(current_price=42250, timestamp=datetime.now())

# Check unrealized P&L
print(f"Unrealized P&L: ${position.unrealized_pnl:.2f}")
print(f"Portfolio equity: ${portfolio.equity:.2f}")

# Close position
trade = portfolio.close_position(
    position=position,
    exit_price=42500,
    timestamp=datetime.now(),
    reason='take_profit',
    commission=10.60,
    slippage=2.15
)

print(f"Trade P&L: ${trade.pnl:.2f} ({trade.pnl_pct:.2f}%)")
```

### 4. Calculate Metrics

```python
from backtesting.core import MetricsCalculator

# Initialize calculator
calculator = MetricsCalculator(risk_free_rate=0.02)

# Calculate metrics from trades and equity curve
result = calculator.calculate(
    trades=portfolio.trades,
    equity_curve=portfolio.equity_curve,
    initial_capital=10000,
    start_time=datetime(2025, 9, 1),
    end_time=datetime(2025, 10, 1),
    symbol='BTC_USDT'
)

# Print summary
result.print_summary()
```

---

## 🧩 Core Components

### 1. DataLoader

**Purpose:** Fetch historical data from InfluxDB and MongoDB

**Key Methods:**
- `get_price_data(symbol, start, end)` - Fetch tick data
- `get_whale_events(symbol, start, end, min_usd)` - Fetch whale events
- `create_unified_timeline(prices, whales, window_size)` - Merge data sources

**Features:**
- Automatic time zone handling (UTC)
- Whale activity aggregation (buy/sell volume, imbalance)
- Derived features (price change %, spread %)

### 2. ExecutionSimulator

**Purpose:** Model realistic order execution

**Key Methods:**
- `simulate_market_buy(price, size, timestamp)` - Simulate market buy
- `simulate_market_sell(price, size, timestamp)` - Simulate market sell
- `estimate_roundtrip_cost(price, size)` - Calculate total trade cost

**Slippage Models:**
- `fixed`: Constant percentage (simple)
- `volume_based`: Increases with order size (better)
- `orderbook`: Simulates walking through levels (most realistic, TODO)

### 3. Portfolio

**Purpose:** Manage capital, positions, and trades

**Key Methods:**
- `open_position(...)` - Open new position
- `close_position(...)` - Close position and record trade
- `update(price, timestamp)` - Update unrealized P&L and equity
- `calculate_position_size(...)` - Risk-based or % -based sizing

**Features:**
- Automatic cash management
- Multi-position support (configurable limit)
- Equity curve tracking
- Drawdown monitoring

### 4. MetricsCalculator

**Purpose:** Calculate performance metrics

**Key Metrics:**
- **Returns:** Total, percentage, absolute
- **Risk-Adjusted:** Sharpe ratio, Sortino ratio
- **Drawdown:** Maximum drawdown, duration
- **Trade Stats:** Win rate, profit factor, avg win/loss

**Advanced Features:**
- Monthly returns (for heatmap)
- Win/loss streaks
- Trade duration analysis

---

## 🎯 Strategy Development

### Creating a Strategy (TODO - Framework Ready)

Strategies will inherit from `BaseStrategy` and implement:

```python
class MyWhaleStrategy(BaseStrategy):
    def on_tick(self, timestamp, market_data, portfolio):
        """Called every data point"""
        pass

    def on_whale_event(self, event):
        """Called when whale event occurs"""
        pass

    def on_order_filled(self, order):
        """Called when order executes"""
        pass
```

### Example: Whale Following Strategy (Simplified)

```python
# Pseudocode - Will be implemented in strategies/whale_following.py

class WhaleFollowingStrategy(BaseStrategy):
    def __init__(self, min_whale_usd=100000, entry_delay_sec=2):
        self.min_whale_usd = min_whale_usd
        self.entry_delay = entry_delay_sec

    def on_whale_event(self, event):
        # Detect large market orders
        if event['event_type'] == 'market_buy' and event['usd_value'] >= self.min_whale_usd:
            # Signal: Follow the whale (buy)
            return Order(
                side=OrderSide.BUY,
                type=OrderType.MARKET,
                size=self.calculate_size(),
                metadata={'whale_size': event['usd_value']}
            )
```

---

## 📊 Performance Metrics

### Standard Metrics

| Metric | Description | Good Value |
|--------|-------------|------------|
| **Total Return** | Absolute profit/loss | > 0% |
| **Sharpe Ratio** | Risk-adjusted return | > 1.0 (good), > 2.0 (great) |
| **Sortino Ratio** | Downside risk-adjusted | > 1.5 |
| **Max Drawdown** | Largest peak-to-trough decline | < 20% |
| **Win Rate** | % of winning trades | > 50% |
| **Profit Factor** | Gross profit / Gross loss | > 1.5 |
| **Avg Win / Avg Loss** | Risk/reward ratio | > 1.5 |

### Interpreting Results

**Sharpe Ratio:**
- < 1.0: Subpar (return doesn't justify risk)
- 1.0-2.0: Good (decent risk-adjusted return)
- 2.0-3.0: Excellent (strong risk-adjusted return)
- \> 3.0: Suspicious (probably overfitting)

**Max Drawdown:**
- < 10%: Conservative strategy
- 10-20%: Moderate risk
- 20-30%: Aggressive
- \> 30%: Very risky (psychological stress)

**Win Rate:**
- < 40%: Low (need large winners to compensate)
- 40-60%: Average
- \> 60%: High (consistent strategy)
- \> 80%: Suspicious (small wins, large losses?)

---

## 📝 Examples

### Example 1: Load and Inspect Data

```python
from backtesting.core import DataLoader

loader = DataLoader()

# Load 1 week of BTC data
prices = loader.get_price_data('BTC_USDT', '2025-10-01', '2025-10-08')
whales = loader.get_whale_events('BTC_USDT', '2025-10-01', '2025-10-08', min_usd=100000)

print(f"Price points: {len(prices):,}")
print(f"Whale events: {len(whales):,}")

# Check whale event types
print("\nWhale events by type:")
print(whales['event_type'].value_counts())

# Check largest whales
print("\nLargest 5 whale events:")
print(whales.nlargest(5, 'usd_value')[['timestamp', 'event_type', 'usd_value', 'price']])
```

### Example 2: Manual Trade Simulation

```python
from backtesting.core import Portfolio, ExecutionSimulator
from backtesting.core.models import PositionSide
from datetime import datetime

# Initialize
portfolio = Portfolio(initial_capital=10000)
simulator = ExecutionSimulator()

# Simulate whale market buy scenario
whale_event_price = 42000
entry_delay = 2  # seconds

# Price moved up after whale buy
current_price = 42010

# Simulate our entry (2 seconds after whale)
fill_price, commission, slippage = simulator.simulate_market_buy(
    order_price=current_price,
    order_size=0.02,
    timestamp=datetime.now()
)

# Open position
position = portfolio.open_position(
    symbol='BTC_USDT',
    side=PositionSide.LONG,
    entry_price=fill_price,
    size=0.02,
    timestamp=datetime.now(),
    stop_loss=fill_price * 0.9985,  # -0.15%
    take_profit=fill_price * 1.003,  # +0.3%
    commission=commission,
    slippage=slippage
)

print(f"Entered at ${fill_price:.2f}")
print(f"Stop loss: ${position.stop_loss:.2f}")
print(f"Take profit: ${position.take_profit:.2f}")

# Simulate price movement
test_prices = [42050, 42100, 42150, 42200]

for price in test_prices:
    portfolio.update(price, datetime.now())
    print(f"Price ${price:.2f}: Unrealized P&L = ${position.unrealized_pnl:.2f}")

    if position.should_take_profit(price):
        print(f"Take profit hit at ${price:.2f}!")
        trade = portfolio.close_position(position, price, datetime.now(), 'take_profit')
        print(f"Final P&L: ${trade.pnl:.2f} ({trade.pnl_pct:.2f}%)")
        break
```

---

## ✅ Best Practices

### 1. Always Use Realistic Costs

```python
# ❌ Bad: Ignoring fees and slippage
portfolio.open_position(..., commission=0, slippage=0)

# ✅ Good: Realistic costs
simulator = ExecutionSimulator(taker_fee_pct=0.06, slippage_pct=0.02)
fill_price, comm, slip = simulator.simulate_market_buy(...)
portfolio.open_position(..., commission=comm, slippage=slip)
```

### 2. Validate with Walk-Forward

```python
# ❌ Bad: Optimize on all data
backtest(data='2025-01-01' to '2025-10-01', optimize=True)

# ✅ Good: Train/test split
train_result = backtest(data='2025-01-01' to '2025-08-31', optimize=True)
test_result = backtest(data='2025-09-01' to '2025-10-01', params=train_result.best_params)
```

### 3. Check Data Quality

```python
# Always inspect data before backtesting
prices = loader.get_price_data(...)

print(f"Start: {prices['timestamp'].min()}")
print(f"End: {prices['timestamp'].max()}")
print(f"Points: {len(prices):,}")
print(f"Gaps: {prices['timestamp'].diff().describe()}")
print(f"Null values: {prices.isnull().sum()}")
```

### 4. Set Realistic Expectations

```python
# If backtest shows 100% annual return with Sharpe > 3.0
# → Probably overfitting!

# Reasonable targets for whale strategies:
# - Sharpe 1.0-2.0
# - Annual return 10-30%
# - Max drawdown 10-25%
# - Win rate 50-65%
```

---

## 🗺️ Roadmap

### Phase 1: Foundation ✅ (COMPLETED)
- [x] Data models (Order, Position, Trade, BacktestResult)
- [x] DataLoader (InfluxDB integration)
- [x] Portfolio management
- [x] ExecutionSimulator (fees, slippage)
- [x] MetricsCalculator (Sharpe, drawdown, etc.)

### Phase 2: Core Engine (IN PROGRESS)
- [ ] BacktestEngine implementation
- [ ] Event-driven tick-by-tick processing
- [ ] Order management system
- [ ] Position entry/exit logic

### Phase 3: Strategies (NEXT)
- [ ] BaseStrategy abstract class
- [ ] WhaleFollowingStrategy
- [ ] PriceSpikeReversalStrategy
- [ ] OrderImbalanceStrategy

### Phase 4: Optimization
- [ ] Parameter grid search
- [ ] Walk-forward validation
- [ ] Strategy comparison tools

### Phase 5: Visualization
- [ ] Equity curve charts
- [ ] Drawdown plots
- [ ] Trade distribution histograms
- [ ] HTML report generation

### Phase 6: Advanced Features
- [ ] Multi-symbol backtesting
- [ ] Portfolio of strategies
- [ ] Monte Carlo simulation
- [ ] Live trading integration

---

## 📄 License

MIT License - See main project LICENSE

---

## 🤝 Contributing

This is a private project. For questions or suggestions, contact the development team.

---

## 📚 Additional Resources

- **Project Docs:** `/home/luka/bitpulse/order-book/docs/`
- **Deep Dive:** `PRICE_CHANGE_ANALYZER_DEEP_DIVE.md`
- **Examples:** Coming soon in `examples/`

---

**Status:** Phase 1 Complete ✅ | Ready for Phase 2: BacktestEngine
