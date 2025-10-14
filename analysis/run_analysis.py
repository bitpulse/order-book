#!/usr/bin/env python3
"""
Advanced Order Book Analysis - Main Runner

Coordinates all analysis modules and generates comprehensive reports.

Usage:
    python analysis/run_analysis.py --symbol BTC_USDT --lookback 24
"""

import asyncio
import sys
from pathlib import Path
import argparse
from datetime import datetime
import json
from collections import defaultdict
import pandas as pd
from loguru import logger

# Import all analysis modules
from data_extractor import DataExtractor
from ofi_calculator import OFICalculator
from pattern_detectors import IcebergDetector, SpoofingDetector, LayeringDetector
from liquidity_analyzer import LiquidityAnalyzer
from microstructure import MicrostructureCalculator
from statistical_analyzer import StatisticalAnalyzer
from signal_generator import SignalGenerator
from anomaly_detector import AnomalyDetector
from data_models import TradingSignal, PatternDetection


class AdvancedAnalysisRunner:
    """Main runner for comprehensive order book analysis"""

    def __init__(self, influx_timeout: int = 120000):
        """
        Initialize analysis runner

        Args:
            influx_timeout: InfluxDB query timeout in milliseconds (default: 120s)
        """
        # Initialize all modules
        self.data_extractor = DataExtractor(timeout=influx_timeout)
        self.ofi_calculator = OFICalculator()
        self.iceberg_detector = IcebergDetector()
        self.spoofing_detector = SpoofingDetector()
        self.layering_detector = LayeringDetector()
        self.liquidity_analyzer = LiquidityAnalyzer()
        self.microstructure = MicrostructureCalculator()
        self.statistical_analyzer = StatisticalAnalyzer()
        self.signal_generator = SignalGenerator()
        self.anomaly_detector = AnomalyDetector()

    async def run(self, symbol: str = "BTC_USDT", lookback_hours: int = 24):
        """
        Run complete advanced analysis

        Args:
            symbol: Trading pair symbol
            lookback_hours: Hours of historical data to analyze
        """
        try:
            logger.info(f"=" * 100)
            logger.info(f"Starting Advanced Order Book Analysis for {symbol}")
            logger.info(f"Lookback: {lookback_hours} hours")
            logger.info(f"=" * 100)

            # === STEP 1: DATA EXTRACTION ===
            logger.info("\n[STEP 1/8] Extracting data from InfluxDB...")
            price_df = self.data_extractor.query_price_data(symbol, lookback_hours)
            events_df = self.data_extractor.query_whale_events(symbol, lookback_hours)

            if price_df.empty or events_df.empty:
                logger.warning("Insufficient data for analysis")
                return

            # === STEP 2: ORDER FLOW IMBALANCE ===
            logger.info("\n[STEP 2/8] Calculating Order Flow Imbalance...")
            ofi_df = self.ofi_calculator.calculate(events_df, window='5s')

            # === STEP 3: PATTERN DETECTION ===
            logger.info("\n[STEP 3/8] Detecting patterns...")
            icebergs = self.iceberg_detector.detect(events_df)
            spoofs = self.spoofing_detector.detect(events_df)
            layers = self.layering_detector.detect(events_df)
            all_patterns = icebergs + spoofs + layers

            # === STEP 4: LIQUIDITY ANALYSIS ===
            logger.info("\n[STEP 4/8] Analyzing liquidity...")
            liquidity_clusters = self.liquidity_analyzer.analyze_clustering(events_df)
            liquidity_ratio = self.liquidity_analyzer.calculate_liquidity_ratio(events_df)
            liquidity_holes = self.liquidity_analyzer.detect_liquidity_holes(events_df)

            # === STEP 5: MICROSTRUCTURE INDICATORS ===
            logger.info("\n[STEP 5/8] Calculating microstructure indicators...")
            micro_df = self.microstructure.calculate_all(price_df, events_df)
            price_impacts = self.microstructure.calculate_price_impact(events_df, price_df)
            regime_changes = self.microstructure.detect_regime_changes(micro_df)

            # === STEP 6: STATISTICAL ANALYSIS ===
            logger.info("\n[STEP 6/8] Performing statistical analysis...")
            correlations = self.statistical_analyzer.analyze_correlations(ofi_df, micro_df)
            distributions = self.statistical_analyzer.analyze_distributions(ofi_df, events_df)
            predictive_power = self.statistical_analyzer.test_ofi_predictive_power(ofi_df, price_df)

            # === STEP 7: ANOMALY DETECTION ===
            logger.info("\n[STEP 7/8] Detecting anomalies...")
            anomalies = self.anomaly_detector.detect_all(events_df, ofi_df, micro_df)
            anomaly_score = self.anomaly_detector.calculate_anomaly_score(anomalies)

            # === STEP 8: SIGNAL GENERATION ===
            logger.info("\n[STEP 8/8] Generating trading signals...")
            signals = self.signal_generator.generate(ofi_df, micro_df, all_patterns, liquidity_clusters)
            backtest_results = self.signal_generator.backtest_signals(signals, price_df) if signals else {}

            # === COMPILE RESULTS ===
            results = {
                'metadata': {
                    'symbol': symbol,
                    'lookback_hours': lookback_hours,
                    'analysis_timestamp': datetime.now().isoformat(),
                    'data_points': {
                        'price_records': len(price_df),
                        'whale_events': len(events_df),
                        'ofi_windows': len(ofi_df),
                        'microstructure_points': len(micro_df)
                    }
                },
                'ofi_summary': self._summarize_ofi(ofi_df),
                'patterns': {
                    'icebergs': len(icebergs),
                    'spoofs': len(spoofs),
                    'layering': len(layers),
                    'total': len(all_patterns),
                    'details': [p.to_dict() for p in all_patterns]
                },
                'liquidity': {
                    'clusters': liquidity_clusters,
                    'ratio': liquidity_ratio,
                    'holes': liquidity_holes
                },
                'microstructure': {
                    'regime_changes': len(regime_changes),
                    'price_impacts': len(price_impacts)
                },
                'statistics': {
                    'correlations': correlations,
                    'distributions': distributions,
                    'predictive_power': predictive_power
                },
                'anomalies': {
                    'count': len(anomalies),
                    'score': anomaly_score,
                    'details': [a.to_dict() for a in anomalies[:20]]  # Top 20
                },
                'signals': {
                    'count': len(signals),
                    'buy_signals': len([s for s in signals if s.signal_type == 'BUY']),
                    'sell_signals': len([s for s in signals if s.signal_type == 'SELL']),
                    'backtest': backtest_results,
                    'details': [s.to_dict() for s in signals]
                }
            }

            # === SAVE & DISPLAY ===
            output_path = self._save_results(symbol, results, price_df, ofi_df, micro_df, signals, all_patterns)
            self._print_summary(results)

            logger.info(f"\n{'='*100}")
            logger.info(f"Analysis complete! Results saved to: {output_path}")
            logger.info(f"{'='*100}\n")

        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            self.data_extractor.close()

    def _summarize_ofi(self, ofi_df: pd.DataFrame) -> dict:
        """Summarize OFI metrics"""
        if ofi_df.empty:
            return {}

        return {
            'mean': float(ofi_df['ofi'].mean()),
            'std': float(ofi_df['ofi'].std()),
            'min': float(ofi_df['ofi'].min()),
            'max': float(ofi_df['ofi'].max()),
            'median': float(ofi_df['ofi'].median()),
            'positive_periods': int((ofi_df['ofi'] > 0).sum()),
            'negative_periods': int((ofi_df['ofi'] < 0).sum()),
            'avg_depth_imbalance': float(ofi_df['depth_imbalance'].mean()) if 'depth_imbalance' in ofi_df.columns else 0
        }

    def _save_results(self, symbol: str, results: dict, price_df: pd.DataFrame,
                     ofi_df: pd.DataFrame, micro_df: pd.DataFrame,
                     signals: list, patterns: list) -> Path:
        """Save analysis results to files"""
        output_dir = Path("analysis_output")
        output_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"analysis_{symbol}_{timestamp}"

        # Main JSON report
        json_path = output_dir / f"{base_name}.json"
        with open(json_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"Saved main report: {json_path}")

        # Signals CSV
        if signals:
            signals_df = pd.DataFrame([s.to_dict() for s in signals])
            csv_path = output_dir / f"{base_name}_signals.csv"
            signals_df.to_csv(csv_path, index=False)
            logger.info(f"Saved signals CSV: {csv_path}")

        # Patterns CSV
        if patterns:
            patterns_df = pd.DataFrame([p.to_dict() for p in patterns])
            csv_path = output_dir / f"{base_name}_patterns.csv"
            patterns_df.to_csv(csv_path, index=False)
            logger.info(f"Saved patterns CSV: {csv_path}")

        # OFI time series
        if not ofi_df.empty:
            csv_path = output_dir / f"{base_name}_ofi.csv"
            ofi_df.to_csv(csv_path, index=False)
            logger.info(f"Saved OFI CSV: {csv_path}")

        # Microstructure time series
        if not micro_df.empty:
            csv_path = output_dir / f"{base_name}_microstructure.csv"
            micro_df.to_csv(csv_path, index=False)
            logger.info(f"Saved microstructure CSV: {csv_path}")

        return json_path

    def _print_summary(self, results: dict):
        """Print comprehensive analysis summary"""
        print("\n" + "=" * 100)
        print("ADVANCED ORDER BOOK ANALYSIS SUMMARY")
        print("=" * 100 + "\n")

        # Metadata
        meta = results['metadata']
        print(f"Symbol: {meta['symbol']}")
        print(f"Lookback: {meta['lookback_hours']} hours")
        print(f"Data Points: {meta['data_points']['price_records']:,} price records, "
              f"{meta['data_points']['whale_events']:,} events")
        print("\n" + "-" * 100)

        # OFI Summary
        ofi = results['ofi_summary']
        if ofi:
            print("\nORDER FLOW IMBALANCE:")
            print(f"  Mean: {ofi['mean']:.2f} | Std: {ofi['std']:.2f}")
            print(f"  Range: [{ofi['min']:.2f}, {ofi['max']:.2f}]")
            print(f"  Bullish periods: {ofi['positive_periods']} | Bearish periods: {ofi['negative_periods']}")
            print(f"  Avg depth imbalance: {ofi['avg_depth_imbalance']:.3f}")

        # Patterns
        patterns = results['patterns']
        print(f"\nPATTERNS DETECTED: {patterns['total']}")
        print(f"  Icebergs: {patterns['icebergs']}")
        print(f"  Spoofing: {patterns['spoofs']}")
        print(f"  Layering: {patterns['layering']}")

        # Liquidity
        liq = results['liquidity']
        if liq.get('ratio'):
            print(f"\nLIQUIDITY ANALYSIS:")
            print(f"  {liq['ratio']['interpretation']}")
            print(f"  Bid/Ask ratio: {liq['ratio']['bid_ratio']:.2%} / {liq['ratio']['ask_ratio']:.2%}")
            print(f"  Total liquidity: ${liq['ratio']['total_liquidity_usd']:,.0f}")

        # Correlations
        corrs = results['statistics'].get('correlations', {})
        if corrs:
            print(f"\nKEY CORRELATIONS:")
            for horizon in ['1s', '5s', '30s', '60s']:
                key = f'ofi_vs_return_{horizon}'
                if key in corrs:
                    r2 = corrs[key]['ofi_r_squared']
                    sig = "✓" if corrs[key]['significant'] else "✗"
                    print(f"  OFI vs {horizon} return: R²={r2:.3f} {sig}")

        # Signals
        sigs = results['signals']
        print(f"\nTRADING SIGNALS: {sigs['count']}")
        print(f"  BUY: {sigs['buy_signals']} | SELL: {sigs['sell_signals']}")

        if sigs.get('backtest'):
            bt = sigs['backtest']
            print(f"\n  Backtest Results:")
            print(f"    Win rate: {bt['win_rate']:.1%}")
            print(f"    Avg P&L: {bt['avg_pnl_pct']:.3f}%")
            print(f"    Sharpe: {bt['sharpe_ratio']:.2f}")
            print(f"    Total P&L: {bt['total_pnl_pct']:.2f}%")

        # Top signals
        if sigs['details']:
            top_signals = sorted(sigs['details'], key=lambda x: x['confidence'], reverse=True)[:5]
            print(f"\n  Top 5 Signals:")
            for i, sig in enumerate(top_signals, 1):
                print(f"    {i}. {sig['signal_type']} @ ${sig['price']:.2f} "
                      f"({sig['confidence']:.1%} confidence)")
                print(f"       Reasons: {', '.join(sig['reasons'][:2])}")

        # Anomalies
        anom = results['anomalies']
        print(f"\nANOMALIES:")
        print(f"  Total: {anom['count']}")
        print(f"  Score: {anom['score']['anomaly_score']:.1f}/100 - {anom['score']['interpretation']}")

        if anom['score'].get('by_type'):
            print(f"  By type:")
            for atype, count in anom['score']['by_type'].items():
                print(f"    {atype}: {count}")

        print("\n" + "=" * 100 + "\n")


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Advanced Order Book Analysis - Detect patterns and generate trading signals'
    )
    parser.add_argument('--symbol', default='BTC_USDT', help='Trading symbol (default: BTC_USDT)')
    parser.add_argument('--lookback', type=int, default=24, help='Hours of data to analyze (default: 24)')

    args = parser.parse_args()

    # Setup logging
    logger.remove()
    logger.add(sys.stdout, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>")

    runner = AdvancedAnalysisRunner()
    await runner.run(symbol=args.symbol, lookback_hours=args.lookback)


if __name__ == "__main__":
    asyncio.run(main())
