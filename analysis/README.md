# Advanced Order Book Analysis

Comprehensive modular toolkit for analyzing cryptocurrency order book data, detecting patterns, and generating data-driven trading signals.

## Overview

This analysis package provides research-backed tools to analyze order book microstructure, detect whale activity, identify manipulation patterns, and generate actionable trading signals.

### Key Features

- **Order Flow Imbalance (OFI)** - Measure buying/selling pressure (R² ~50% correlation with returns)
- **Pattern Detection** - Iceberg orders, spoofing, layering
- **Liquidity Analysis** - Clustering, depth profiling, liquidity holes
- **Market Microstructure** - Spread dynamics, volatility measures (R² >90% spread-volatility correlation)
- **Statistical Analysis** - Correlations, distributions, predictive modeling
- **Trading Signals** - Multi-indicator scoring with confidence levels
- **Anomaly Detection** - Volume outliers, OFI extremes, unusual patterns

## Project Structure

```
analysis/
├── __init__.py                  # Package initialization
├── data_models.py               # Core data structures (TradingSignal, PatternDetection)
├── data_extractor.py            # InfluxDB data extraction & time-series alignment
├── ofi_calculator.py            # Order Flow Imbalance calculator
├── pattern_detectors.py         # Iceberg, spoofing, layering detectors
├── liquidity_analyzer.py        # Liquidity clustering & depth analysis
├── microstructure.py            # Market microstructure indicators
├── statistical_analyzer.py      # Statistical analysis & correlations
├── signal_generator.py          # Trading signal generation & backtesting
├── anomaly_detector.py          # Anomaly detection (Z-score, clustering)
├── run_analysis.py              # Main analysis runner
├── advanced_orderbook_analyzer.py  # Legacy monolithic version
└── README.md                    # This file
```

## Installation & Dependencies

Requires Python 3.8+ with the following packages:

```bash
pip install pandas numpy scipy scikit-learn influxdb-client loguru
```

## Quick Start

### Basic Usage

```bash
# Analyze BTC_USDT for last 24 hours
python analysis/run_analysis.py --symbol BTC_USDT --lookback 24

# Analyze specific symbol for 48 hours
python analysis/run_analysis.py --symbol ETH_USDT --lookback 48
```

### Programmatic Usage

```python
from analysis.run_analysis import AdvancedAnalysisRunner
import asyncio

async def run():
    runner = AdvancedAnalysisRunner()
    await runner.run(symbol="BTC_USDT", lookback_hours=24)

asyncio.run(run())
```

## Module Documentation

### 1. Data Extractor (`data_extractor.py`)

Queries InfluxDB for price and event data.

**Key Methods:**
- `query_price_data(symbol, lookback_hours)` - Get continuous price data
- `query_whale_events(symbol, lookback_hours, event_types)` - Get order book events
- `align_timeseries(price_df, events_df, window)` - Align data on time grid

**Example:**
```python
from analysis.data_extractor import DataExtractor

extractor = DataExtractor()
price_df = extractor.query_price_data("BTC_USDT", 24)
events_df = extractor.query_whale_events("BTC_USDT", 24)
extractor.close()
```

### 2. OFI Calculator (`ofi_calculator.py`)

Calculates Order Flow Imbalance - key microstructure indicator.

**Formula:**
```
OFI = (Bid Volume + Bid Increases) - (Ask Volume + Ask Increases)
Depth Imbalance = (Bid Depth - Ask Depth) / (Bid Depth + Ask Depth)
```

**Key Methods:**
- `calculate(events_df, window)` - Calculate OFI for time windows
- `get_ofi_interpretation(ofi_zscore)` - Human-readable interpretation
- `calculate_ofi_divergence(ofi_df, price_df)` - Detect divergences

**Example:**
```python
from analysis.ofi_calculator import OFICalculator

calculator = OFICalculator()
ofi_df = calculator.calculate(events_df, window='5s')

# OFI Z-score > 2 = strong bullish pressure
# OFI Z-score < -2 = strong bearish pressure
```

**Research:** OFI has ~50% R² correlation with short-term returns (1s-60s)

### 3. Pattern Detectors (`pattern_detectors.py`)

Detects specific order book patterns.

#### IcebergDetector

Identifies hidden large orders via rapid refills.

**Characteristics:**
- Price stagnation despite heavy volume
- Multiple decrease-increase cycles at same price
- Institutional stealth accumulation/distribution

**Example:**
```python
from analysis.pattern_detectors import IcebergDetector

detector = IcebergDetector(min_refills=3, time_window=30)
icebergs = detector.detect(events_df)

for iceberg in icebergs:
    print(f"{iceberg.description} - Confidence: {iceberg.confidence:.1%}")
```

#### SpoofingDetector

Detects fake orders placed to manipulate price.

**Characteristics:**
- Large orders appearing and quickly disappearing
- Less than 10% filled before removal
- Short lifetime (<5 seconds)

**Example:**
```python
from analysis.pattern_detectors import SpoofingDetector

detector = SpoofingDetector(min_usd_value=100000, max_lifetime=5)
spoofs = detector.detect(events_df)
```

#### LayeringDetector

Detects coordinated orders at multiple price levels.

**Example:**
```python
from analysis.pattern_detectors import LayeringDetector

detector = LayeringDetector(time_window=2, min_layers=3)
layers = detector.detect(events_df)
```

### 4. Liquidity Analyzer (`liquidity_analyzer.py`)

Analyzes liquidity distribution and clustering.

**Key Methods:**
- `analyze_clustering(events_df, eps_pct, min_samples)` - DBSCAN clustering
- `calculate_depth_profile(events_df, price_bins)` - Liquidity by price level
- `detect_liquidity_holes(events_df, threshold_pct)` - Find thin liquidity zones
- `calculate_liquidity_ratio(events_df)` - Bid/ask liquidity imbalance

**Example:**
```python
from analysis.liquidity_analyzer import LiquidityAnalyzer

analyzer = LiquidityAnalyzer()

# Find support/resistance clusters
clusters = analyzer.analyze_clustering(events_df, eps_pct=0.5, min_samples=3)

# Bid/ask liquidity ratio
ratio = analyzer.calculate_liquidity_ratio(events_df, distance_threshold_pct=1.0)
print(f"Liquidity imbalance: {ratio['imbalance']:.2%}")
print(f"Interpretation: {ratio['interpretation']}")
```

### 5. Microstructure Calculator (`microstructure.py`)

Calculates market microstructure indicators.

**Indicators:**
- Bid-ask spread (bps, Z-score, relative)
- Volatility (realized, Parkinson estimator)
- Price dynamics (velocity, acceleration, momentum)
- Roll's measure (bid-ask bounce estimate)
- Trade intensity (per minute)

**Example:**
```python
from analysis.microstructure import MicrostructureCalculator

calc = MicrostructureCalculator()
micro_df = calc.calculate_all(price_df, events_df)

# Spread-volatility correlation (research: R² > 0.9)
corr_df = calc.calculate_spread_volatility_correlation(micro_df)

# Market regime changes
regime_changes = calc.detect_regime_changes(micro_df, volatility_threshold=2.0)

# Price impact of large orders
impacts = calc.calculate_price_impact(events_df, price_df, time_window=5)
```

### 6. Statistical Analyzer (`statistical_analyzer.py`)

Performs statistical analysis and hypothesis testing.

**Key Methods:**
- `analyze_correlations(ofi_df, micro_df)` - OFI vs returns, spread vs volatility
- `analyze_distributions(ofi_df, events_df)` - Statistical distributions
- `test_ofi_predictive_power(ofi_df, price_df)` - Linear regression analysis
- `calculate_sharpe_ratio(signals_df)` - Strategy performance metrics

**Example:**
```python
from analysis.statistical_analyzer import StatisticalAnalyzer

analyzer = StatisticalAnalyzer()

# Correlation analysis
correlations = analyzer.analyze_correlations(ofi_df, micro_df)

# Check OFI predictive power for 5-second returns
if 'ofi_vs_return_5s' in correlations:
    r2 = correlations['ofi_vs_return_5s']['ofi_r_squared']
    pval = correlations['ofi_vs_return_5s']['ofi_pvalue']
    print(f"OFI vs 5s return: R²={r2:.3f}, p-value={pval:.4f}")

# Test predictive power
predictive = analyzer.test_ofi_predictive_power(ofi_df, price_df, forecast_horizon=5)
```

### 7. Signal Generator (`signal_generator.py`)

Generates trading signals with multi-indicator scoring.

**Scoring System:**
- OFI (40% weight) - ±40 points
- Depth Imbalance (20% weight) - ±20 points
- Spread Dynamics (15% weight) - ±15 points
- Pattern Confirmations (15% weight) - ±15 points
- Volatility Adjustment (10% weight) - multiplier

**Example:**
```python
from analysis.signal_generator import SignalGenerator

generator = SignalGenerator()
signals = generator.generate(ofi_df, micro_df, patterns, liquidity_clusters)

# Filter high-confidence signals
high_conf = [s for s in signals if s.confidence >= 0.7]

for signal in high_conf:
    print(f"{signal.signal_type} @ ${signal.price:.2f}")
    print(f"  Confidence: {signal.confidence:.1%}")
    print(f"  Entry: ${signal.suggested_entry:.2f}")
    print(f"  Stop: ${signal.suggested_stop:.2f}")
    print(f"  Target: ${signal.suggested_target:.2f}")
    print(f"  Reasons: {', '.join(signal.reasons)}")

# Backtest signals
backtest = generator.backtest_signals(signals, price_df, holding_period=60)
print(f"Win rate: {backtest['win_rate']:.1%}")
print(f"Sharpe ratio: {backtest['sharpe_ratio']:.2f}")
```

### 8. Anomaly Detector (`anomaly_detector.py`)

Detects statistical anomalies using Z-score method.

**Detectors:**
- Volume anomalies (USD value outliers)
- OFI extremes (Z-score > 3)
- Spread spikes (unusual widening/tightening)
- Event clusters (unusual activity bursts)
- Price jumps (sudden movements)

**Example:**
```python
from analysis.anomaly_detector import AnomalyDetector

detector = AnomalyDetector(zscore_threshold=3.0)
anomalies = detector.detect_all(events_df, ofi_df, micro_df)

# Calculate anomaly score
score = detector.calculate_anomaly_score(anomalies)
print(f"Anomaly score: {score['anomaly_score']:.1f}/100")
print(f"Interpretation: {score['interpretation']}")
```

## Output Files

The analysis generates several output files in `analysis_output/`:

### 1. Main Report (`analysis_SYMBOL_TIMESTAMP.json`)

Comprehensive JSON report with all analysis results.

### 2. Signals CSV (`analysis_SYMBOL_TIMESTAMP_signals.csv`)

Trading signals with:
- Timestamp, signal type (BUY/SELL), confidence
- Price, entry/stop/target levels
- Reasons and indicator values

### 3. Patterns CSV (`analysis_SYMBOL_TIMESTAMP_patterns.csv`)

Detected patterns with:
- Pattern type, timestamp, price level
- Confidence, metrics, description

### 4. OFI Time Series (`analysis_SYMBOL_TIMESTAMP_ofi.csv`)

Order Flow Imbalance metrics per time window.

### 5. Microstructure Time Series (`analysis_SYMBOL_TIMESTAMP_microstructure.csv`)

Market microstructure indicators over time.

## Research References

This toolkit is based on peer-reviewed research and industry best practices:

### Order Flow Imbalance
- **Dean Markwick**: "Order Flow Imbalance - A High Frequency Trading Signal"
  - R² correlation with returns: ~50%
  - Predictive power for 1s-60s horizons

### Spread-Volatility Relationship
- **Market microstructure research**: R² > 0.9 correlation
- Adverse selection as main determinant of bid-ask spread

### Pattern Detection
- **Bookmap**: "Advanced Order Flow Trading: Spotting Hidden Liquidity & Iceberg Orders"
- **Justin Trading**: "How to Spot Iceberg Orders and Spoofing Activity"
- **CoinGlass**: Large order analysis methodologies

### Machine Learning Applications
- **Empirica**: VWAP trading strategies with ML
- **ArXiv**: "Forecasting high frequency order flow imbalance using Hawkes processes"
- **ScienceDirect**: "Deep unsupervised anomaly detection in high-frequency markets"

## Trading Strategy Development

### Example Strategy: OFI-Based Mean Reversion

```python
# 1. Extract high OFI signals
strong_buy = [s for s in signals if s.signal_type == 'BUY' and
              s.indicators.get('ofi_zscore', 0) > 2.0]

# 2. Filter by liquidity support
supported_signals = []
for signal in strong_buy:
    # Check if there's bid liquidity cluster nearby
    has_support = any(
        abs(cluster['price_level'] - signal.price) / signal.price < 0.01
        for cluster in liquidity_clusters.get('bid', [])
    )
    if has_support:
        supported_signals.append(signal)

# 3. Filter high volatility periods
low_vol_signals = [s for s in supported_signals if
                   s.indicators.get('volatility_1m', 0) < 0.03]

# 4. Execute trades
for signal in low_vol_signals:
    if signal.confidence >= 0.75:
        print(f"TRADE: {signal.signal_type} {signal.price}")
```

### Example Strategy: Iceberg Detection + OFI Confirmation

```python
# 1. Find strong iceberg support
strong_icebergs = [p for p in patterns if
                   p.pattern_type == 'iceberg_order' and
                   p.metrics.get('side') == 'bid' and
                   p.confidence > 0.7]

# 2. Check if OFI confirms
for iceberg in strong_icebergs:
    # Find OFI at this time
    ofi_at_time = ofi_df[ofi_df['time'] == iceberg.timestamp]
    if not ofi_at_time.empty:
        ofi_zscore = ofi_at_time.iloc[0]['ofi_zscore']
        if ofi_zscore > 1.5:
            print(f"SIGNAL: Iceberg + OFI confirmation at ${iceberg.price_level:.2f}")
```

## Performance Tips

1. **Reduce lookback for real-time analysis**: Use 1-6 hours for faster processing
2. **Focus on specific event types**: Filter events in `query_whale_events()`
3. **Adjust time windows**: Smaller windows (1s-2s) for scalping, larger (30s-60s) for swing trading
4. **Tune pattern thresholds**: Adjust `min_refills`, `min_usd_value` based on asset
5. **Parallel processing**: Run analysis for multiple symbols concurrently

## Limitations & Considerations

1. **Level 2 Data**: Cannot track individual order IDs or distinguish fills from cancels
2. **Historical Analysis**: Results are backward-looking; market conditions change
3. **No Execution**: This is analysis only; actual trading requires order execution logic
4. **Data Quality**: Depends on InfluxDB data completeness and accuracy
5. **Computational Cost**: Full analysis can take 30s-2min for 24h data

## Contributing

To add new analysis modules:

1. Create module in `analysis/` directory
2. Import in `run_analysis.py`
3. Add to analysis pipeline
4. Document in this README

## License

See repository LICENSE file.

## Support

For issues or questions:
- GitHub Issues: [bitpulse/order-book](https://github.com/bitpulse/order-book/issues)
- Documentation: See individual module docstrings

---

**Disclaimer**: This toolkit is for research and educational purposes. Cryptocurrency trading carries risk. Always backtest strategies thoroughly and use proper risk management.
