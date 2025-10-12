# Analysis Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     InfluxDB Database                            │
│  ┌────────────────────┐     ┌──────────────────────┐           │
│  │ orderbook_price    │     │ orderbook_whale_events│           │
│  │ - best_bid/ask     │     │ - event_type          │           │
│  │ - mid_price        │     │ - volume, usd_value   │           │
│  │ - spread           │     │ - distance_from_mid   │           │
│  └────────────────────┘     └──────────────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────┐
│                   Data Extractor Module                          │
│  • Query time-series data from InfluxDB                         │
│  • Align price and event data on common time grid               │
│  • Filter by symbol, time range, event types                    │
└─────────────────────────────────────────────────────────────────┘
                               ↓
        ┌──────────────────────┴───────────────────────┐
        ↓                                               ↓
┌──────────────────┐                          ┌─────────────────┐
│  Price Data (DF) │                          │ Events Data (DF)│
│  • Continuous    │                          │ • Discrete      │
│  • 1s intervals  │                          │ • Event-driven  │
└──────────────────┘                          └─────────────────┘
        ↓                                               ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Analysis Pipeline                             │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 1. OFI Calculator                                       │   │
│  │    • Order Flow Imbalance per time window              │   │
│  │    • Depth imbalance ratio                             │   │
│  │    • Z-score normalization                              │   │
│  │    Output: ofi_df (time series)                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           ↓                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 2. Pattern Detectors                                    │   │
│  │    • Iceberg Detector → Hidden large orders            │   │
│  │    • Spoofing Detector → Fake orders                   │   │
│  │    • Layering Detector → Coordinated orders            │   │
│  │    Output: List[PatternDetection]                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           ↓                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 3. Liquidity Analyzer                                   │   │
│  │    • DBSCAN clustering → Support/resistance            │   │
│  │    • Depth profiling → Liquidity distribution          │   │
│  │    • Liquidity holes → Thin zones                       │   │
│  │    • Bid/ask ratio → Imbalance                         │   │
│  │    Output: Dict with clusters, ratios, holes            │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           ↓                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 4. Microstructure Calculator                            │   │
│  │    • Spread metrics (bps, Z-score, relative)           │   │
│  │    • Volatility (realized, Parkinson, rolling)         │   │
│  │    • Price dynamics (velocity, acceleration)            │   │
│  │    • Trade intensity (per minute)                       │   │
│  │    Output: micro_df (time series)                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           ↓                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 5. Statistical Analyzer                                 │   │
│  │    • Correlations (OFI vs returns, spread vs vol)      │   │
│  │    • Distributions (normality tests, skewness)          │   │
│  │    • Predictive modeling (linear regression)            │   │
│  │    • Sharpe ratio calculation                           │   │
│  │    Output: Dict with statistical metrics                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           ↓                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 6. Anomaly Detector                                     │   │
│  │    • Volume outliers (Z-score > 3)                     │   │
│  │    • OFI extremes (unusual pressure)                    │   │
│  │    • Spread anomalies (spikes)                          │   │
│  │    • Event clusters (burst activity)                    │   │
│  │    Output: List[PatternDetection] + anomaly_score       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           ↓                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 7. Signal Generator                                     │   │
│  │    • Multi-indicator scoring (-100 to +100)            │   │
│  │    • Confidence calculation (0.0 to 1.0)               │   │
│  │    • Entry/stop/target suggestions                      │   │
│  │    • Backtesting with holding period                    │   │
│  │    Output: List[TradingSignal] + backtest results       │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────┐
│                     Output Generation                            │
│                                                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌───────────┐│
│  │ Main JSON  │  │ Signals CSV│  │Patterns CSV│  │ OFI CSV   ││
│  │ Report     │  │            │  │            │  │           ││
│  └────────────┘  └────────────┘  └────────────┘  └───────────┘│
│                                                                  │
│  ┌────────────┐  ┌────────────────────────────────────────────┐│
│  │Micro CSV   │  │ Terminal Summary Output                    ││
│  │            │  │ • OFI summary                               ││
│  └────────────┘  │ • Pattern counts                            ││
│                  │ • Signal performance                        ││
│                  │ • Correlation metrics                       ││
│                  └────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow

### Input → Processing → Output

```
InfluxDB
   ↓
[Data Extractor]
   ↓
price_df + events_df
   ↓
[Parallel Processing]
   ├─→ [OFI Calculator] ────────────→ ofi_df
   ├─→ [Pattern Detectors] ─────────→ patterns[]
   ├─→ [Liquidity Analyzer] ────────→ clusters{}
   └─→ [Microstructure] ────────────→ micro_df
         ↓
[Statistical Analysis]
   ├─→ correlations{}
   ├─→ distributions{}
   └─→ predictive_power{}
         ↓
[Anomaly Detection] ──────────────→ anomalies[]
         ↓
[Signal Generation] ───────────────→ signals[]
         ↓
[Output Files + Summary]
```

## Module Dependencies

```
run_analysis.py (Main)
    │
    ├─→ data_extractor.py
    │       └─→ src.config (Settings)
    │
    ├─→ ofi_calculator.py
    │       └─→ None (standalone)
    │
    ├─→ pattern_detectors.py
    │       ├─→ IcebergDetector
    │       ├─→ SpoofingDetector
    │       └─→ LayeringDetector
    │       └─→ data_models (PatternDetection)
    │
    ├─→ liquidity_analyzer.py
    │       └─→ sklearn.cluster (DBSCAN)
    │
    ├─→ microstructure.py
    │       └─→ None (standalone)
    │
    ├─→ statistical_analyzer.py
    │       └─→ scipy.stats
    │
    ├─→ signal_generator.py
    │       └─→ data_models (TradingSignal)
    │
    └─→ anomaly_detector.py
            └─→ data_models (PatternDetection)
```

## Signal Generation Flow

```
┌──────────────────────────────────────────────────────────┐
│              Multi-Indicator Scoring                      │
│                                                           │
│  OFI Signal (40%)         ────────→  ±40 points         │
│  • OFI Z-score > 2: Strong                               │
│  • OFI Z-score > 1: Moderate                             │
│                                                           │
│  Depth Imbalance (20%)    ────────→  ±20 points         │
│  • > 0.3: Bid dominance                                  │
│  • < -0.3: Ask dominance                                 │
│                                                           │
│  Spread Dynamics (15%)    ────────→  ±15 points         │
│  • Tight spread: Bullish                                 │
│  • Wide spread: Bearish                                  │
│                                                           │
│  Pattern Confirm (15%)    ────────→  ±15 points         │
│  • Iceberg support/resistance                            │
│  • Spoofing detected                                     │
│                                                           │
│  Volatility Adj (10%)     ────────→  × 0.7-1.1          │
│  • High vol: Reduce confidence                           │
│  • Low vol: Increase confidence                          │
│                                                           │
│  Total Score: -100 to +100                               │
│                                                           │
│  IF |score| >= 20:                                       │
│    → Generate TradingSignal                              │
│    → Calculate confidence (score/100)                    │
│    → Suggest entry/stop/target levels                    │
│    → Add reasons list                                    │
└──────────────────────────────────────────────────────────┘
```

## Pattern Detection Logic

### Iceberg Detection

```
For each price level:
  1. Count decrease → increase cycles
  2. Check time window (<30s)
  3. Calculate total volume cycled
  4. IF refills >= 3:
     → Pattern detected
     → Confidence = min(refills/10, 0.95)
```

### Spoofing Detection

```
For each large new order (>$100k):
  1. Track order lifetime
  2. Measure fill percentage
  3. IF lifetime < 5s AND fills < 10%:
     → Potential spoof
     → Confidence = (1 - fills) × (1 - lifetime/5)
```

### Layering Detection

```
For each new order:
  1. Find orders in 2s window, same side
  2. Calculate price interval consistency
  3. IF layers >= 3 AND regular intervals:
     → Layering detected
     → Confidence = min(layers/10, 0.85) × (1 - CV)
```

## Statistical Analysis

### Correlation Analysis

```
OFI ←→ Future Returns (1s, 5s, 30s, 60s)
  • Pearson correlation
  • R² (coefficient of determination)
  • p-value (significance test)
  Expected: R² ~0.5 for short horizons

Spread ←→ Volatility
  • Pearson correlation
  • R² (coefficient of determination)
  Expected: R² >0.9 (research-backed)

OFI Autocorrelation (persistence)
  • Lag 1, 5, 10, 20
  • Measures momentum
```

## Performance Characteristics

| Operation | Time Complexity | Space Complexity |
|-----------|----------------|------------------|
| Data Extraction | O(n) | O(n) |
| OFI Calculation | O(n) | O(w) where w=windows |
| Pattern Detection | O(n²) worst case | O(p) where p=patterns |
| DBSCAN Clustering | O(n log n) | O(n) |
| Microstructure | O(n) | O(n) |
| Statistical Analysis | O(n) | O(1) |
| Signal Generation | O(n × w) | O(s) where s=signals |

**Typical Performance** (24h data):
- Data extraction: 5-10s
- OFI calculation: 1-2s
- Pattern detection: 3-5s
- Clustering: 2-3s
- Microstructure: 2-3s
- Statistics: 1-2s
- Signal generation: 2-3s
- **Total: 15-30s**

## Research Foundation

### Implemented Research Papers

1. **Order Flow Imbalance**
   - Source: Dean Markwick (2022)
   - Finding: R² ~50% correlation with returns
   - Implementation: `ofi_calculator.py`

2. **Spread-Volatility Relationship**
   - Source: Market microstructure literature
   - Finding: R² >90% correlation
   - Implementation: `microstructure.py`

3. **Iceberg Detection**
   - Source: Bookmap, industry practice
   - Method: Refill cycle tracking
   - Implementation: `pattern_detectors.py`

4. **DBSCAN Clustering**
   - Source: Density-based spatial clustering
   - Application: Liquidity level identification
   - Implementation: `liquidity_analyzer.py`

## Extension Points

### Adding New Detectors

```python
# In pattern_detectors.py
class NewPatternDetector:
    def __init__(self, threshold: float):
        self.threshold = threshold

    def detect(self, events_df: pd.DataFrame) -> List[PatternDetection]:
        patterns = []
        # Your detection logic here
        return patterns
```

### Adding New Indicators

```python
# In microstructure.py
class MicrostructureCalculator:
    def calculate_new_indicator(self, df: pd.DataFrame) -> pd.Series:
        # Your indicator calculation
        return df['new_indicator']
```

### Customizing Signal Weights

```python
# In signal_generator.py
generator = SignalGenerator(
    ofi_weight=0.5,        # Increase OFI importance
    depth_weight=0.2,
    spread_weight=0.15,
    pattern_weight=0.10,   # Decrease pattern importance
    volatility_weight=0.05
)
```

## Error Handling

```
┌─────────────────────────────────────┐
│ Try-Except at Each Module Level    │
│                                     │
│ DataExtractor.query_*()            │
│   → Empty DataFrame on error        │
│                                     │
│ Calculator/Detector.detect()       │
│   → Empty list on error             │
│   → Log warning                     │
│                                     │
│ Main Runner                         │
│   → Check data availability         │
│   → Skip module if dependencies fail│
│   → Continue with available data    │
└─────────────────────────────────────┘
```

---

For implementation details, see individual module files and `README.md`.
