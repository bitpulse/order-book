# Quick Start Guide - Advanced Order Book Analysis

## Installation

```bash
cd /home/luka/bitpulse/order-book
pip install pandas numpy scipy scikit-learn influxdb-client loguru
```

## Basic Usage

### 1. Run Full Analysis

```bash
# Analyze BTC for last 24 hours
python analysis/run_analysis.py --symbol BTC_USDT --lookback 24

# Analyze TAO for last 48 hours
python analysis/run_analysis.py --symbol TAO_USDT --lookback 48
```

### 2. Using Individual Modules

```python
from analysis.data_extractor import DataExtractor
from analysis.ofi_calculator import OFICalculator
from analysis.pattern_detectors import IcebergDetector

# Extract data
extractor = DataExtractor()
price_df = extractor.query_price_data("BTC_USDT", 24)
events_df = extractor.query_whale_events("BTC_USDT", 24)

# Calculate OFI
ofi_calc = OFICalculator()
ofi_df = ofi_calc.calculate(events_df, window='5s')

# Detect patterns
iceberg_detector = IcebergDetector()
icebergs = iceberg_detector.detect(events_df)

print(f"Found {len(icebergs)} iceberg orders")
extractor.close()
```

## Output Files

All outputs saved to `analysis_output/`:

```
analysis_output/
├── analysis_BTC_USDT_20250112_223045.json          # Main report
├── analysis_BTC_USDT_20250112_223045_signals.csv   # Trading signals
├── analysis_BTC_USDT_20250112_223045_patterns.csv  # Detected patterns
├── analysis_BTC_USDT_20250112_223045_ofi.csv       # OFI time series
└── analysis_BTC_USDT_20250112_223045_microstructure.csv
```

## Module Overview

| Module | Purpose | Key Output |
|--------|---------|------------|
| `data_extractor.py` | Query InfluxDB | DataFrames with price/events |
| `ofi_calculator.py` | Order Flow Imbalance | OFI metrics, Z-scores |
| `pattern_detectors.py` | Pattern detection | Icebergs, spoofing, layering |
| `liquidity_analyzer.py` | Liquidity analysis | Clusters, depth, holes |
| `microstructure.py` | Microstructure indicators | Spread, volatility, momentum |
| `statistical_analyzer.py` | Statistical tests | Correlations, R², p-values |
| `signal_generator.py` | Trading signals | BUY/SELL with confidence |
| `anomaly_detector.py` | Anomaly detection | Volume/OFI/spread anomalies |

## Key Metrics Explained

### Order Flow Imbalance (OFI)
- **Positive OFI**: More buying pressure (bullish)
- **Negative OFI**: More selling pressure (bearish)
- **Z-score > 2**: Strong signal
- **R² ~50%** correlation with short-term returns

### Trading Signal Confidence
- **0.5-0.6**: Moderate confidence
- **0.7-0.8**: High confidence
- **0.9+**: Very high confidence

### Anomaly Score
- **0-20**: Normal
- **20-40**: Mild unusual activity
- **40-60**: Moderate unusual activity
- **60-80**: High unusual activity
- **80+**: Extreme unusual activity

## Example Workflows

### 1. Find Strong Buy Signals

```python
import asyncio
from analysis.run_analysis import AdvancedAnalysisRunner

async def find_buy_signals():
    runner = AdvancedAnalysisRunner()
    results = await runner.run("BTC_USDT", 24)

    # Filter high-confidence buy signals
    buy_signals = [
        s for s in results['signals']['details']
        if s['signal_type'] == 'BUY' and s['confidence'] > 0.7
    ]

    for signal in buy_signals[:5]:
        print(f"BUY @ ${signal['price']:.2f} - {signal['confidence']:.1%}")
        print(f"  Reasons: {', '.join(signal['reasons'])}")

asyncio.run(find_buy_signals())
```

### 2. Detect Manipulation Patterns

```python
from analysis.data_extractor import DataExtractor
from analysis.pattern_detectors import SpoofingDetector, LayeringDetector

extractor = DataExtractor()
events_df = extractor.query_whale_events("BTC_USDT", 24)

# Find spoofing
spoof_detector = SpoofingDetector(min_usd_value=100000)
spoofs = spoof_detector.detect(events_df)

# Find layering
layer_detector = LayeringDetector()
layers = layer_detector.detect(events_df)

print(f"Spoofing patterns: {len(spoofs)}")
print(f"Layering patterns: {len(layers)}")

extractor.close()
```

### 3. Analyze Liquidity

```python
from analysis.data_extractor import DataExtractor
from analysis.liquidity_analyzer import LiquidityAnalyzer

extractor = DataExtractor()
events_df = extractor.query_whale_events("BTC_USDT", 24)

analyzer = LiquidityAnalyzer()

# Find support/resistance clusters
clusters = analyzer.analyze_clustering(events_df)
print(f"Bid clusters: {len(clusters.get('bid', []))}")
print(f"Ask clusters: {len(clusters.get('ask', []))}")

# Check liquidity ratio
ratio = analyzer.calculate_liquidity_ratio(events_df)
print(f"\nLiquidity: {ratio['interpretation']}")
print(f"Bid: {ratio['bid_ratio']:.1%} | Ask: {ratio['ask_ratio']:.1%}")

extractor.close()
```

## Troubleshooting

### No data returned
```python
# Check if data exists in InfluxDB
from analysis.data_extractor import DataExtractor

extractor = DataExtractor()
price_df = extractor.query_price_data("BTC_USDT", 24)
print(f"Price records: {len(price_df)}")

events_df = extractor.query_whale_events("BTC_USDT", 24)
print(f"Event records: {len(events_df)}")
```

### Import errors
```bash
# Make sure you're in the correct directory
cd /home/luka/bitpulse/order-book

# Run with Python path
PYTHONPATH=. python analysis/run_analysis.py --symbol BTC_USDT --lookback 24
```

### Slow performance
- Reduce `--lookback` hours (try 6-12 instead of 24)
- Filter event types when querying
- Increase time window for OFI (use '10s' instead of '5s')

## Next Steps

1. **Read full documentation**: See `analysis/README.md`
2. **Customize strategies**: Modify `signal_generator.py` weights
3. **Add new patterns**: Create detector in `pattern_detectors.py`
4. **Backtest signals**: Use `signal_generator.backtest_signals()`

## Research References

- **OFI**: Dean Markwick - "Order Flow Imbalance: A High Frequency Trading Signal"
- **Patterns**: Bookmap - "Advanced Order Flow Trading"
- **Microstructure**: Academic papers on spread-volatility relationships

---

For detailed documentation, see `analysis/README.md`
