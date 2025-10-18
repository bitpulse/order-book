"""
Entry Range Analyzer

Analyzes entry quality for manual trading strategies:
- How far was entry from ideal (dump low)?
- What % of theoretical profit was captured?
- How would different entry timings perform?
- Visualize acceptable entry ranges
"""

from typing import List, Dict, Any, Optional
import pandas as pd
from datetime import datetime
from loguru import logger


class EntryRangeAnalyzer:
    """
    Analyzes entry quality and acceptable entry ranges for manual trading

    Helps answer questions like:
    - "If I entered 1% above the bottom, how much profit did I miss?"
    - "What's the acceptable entry window for this strategy?"
    - "How sensitive is performance to entry timing?"
    """

    def __init__(self):
        """Initialize entry range analyzer"""
        self.analysis_results = []

    def analyze_entry_quality(self,
                              trades: List[Any],
                              strategy_stats: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze entry quality for completed trades

        Args:
            trades: List of Trade objects from backtest
            strategy_stats: Strategy statistics with entry_range_analysis

        Returns:
            Dict with entry quality metrics
        """
        if not trades:
            logger.warning("No trades to analyze")
            return {
                'total_trades': 0,
                'entry_quality_metrics': {}
            }

        analysis = {
            'total_trades': len(trades),
            'entry_quality_metrics': {},
            'missed_profit_analysis': {},
            'entry_timing_sensitivity': {}
        }

        # Get entry range data from strategy stats
        entry_data = strategy_stats.get('entry_range_analysis', [])

        if entry_data:
            # Calculate entry quality metrics
            distances = [e['distance_from_low_pct'] for e in entry_data]
            avg_distance = sum(distances) / len(distances)
            min_distance = min(distances)
            max_distance = max(distances)

            analysis['entry_quality_metrics'] = {
                'avg_distance_from_low_pct': avg_distance,
                'min_distance_from_low_pct': min_distance,
                'max_distance_from_low_pct': max_distance,
                'entries_within_1pct': sum(1 for d in distances if d <= 1.0),
                'entries_within_2pct': sum(1 for d in distances if d <= 2.0),
                'entries_beyond_2pct': sum(1 for d in distances if d > 2.0)
            }

        # Analyze profit impact
        if trades:
            winning_trades = [t for t in trades if t.pnl > 0]
            losing_trades = [t for t in trades if t.pnl <= 0]

            analysis['missed_profit_analysis'] = {
                'winning_trades': len(winning_trades),
                'losing_trades': len(losing_trades),
                'avg_win_pnl_pct': sum(t.pnl_pct for t in winning_trades) / len(winning_trades) if winning_trades else 0,
                'avg_loss_pnl_pct': sum(t.pnl_pct for t in losing_trades) / len(losing_trades) if losing_trades else 0
            }

            # Estimate missed profit from entry timing
            if entry_data and winning_trades:
                total_missed_profit_pct = 0
                for i, trade in enumerate(winning_trades):
                    if i < len(entry_data):
                        entry_dist = entry_data[i]['distance_from_low_pct']
                        # Rough estimate: missed profit ≈ entry distance
                        # (if entered at bottom, would've gained extra %)
                        total_missed_profit_pct += entry_dist

                analysis['missed_profit_analysis']['estimated_missed_profit_pct'] = (
                    total_missed_profit_pct / len(winning_trades) if winning_trades else 0
                )

        return analysis

    def calculate_acceptable_entry_range(self,
                                        dump_low: float,
                                        target_profit_pct: float,
                                        min_acceptable_profit_pct: float) -> Dict[str, float]:
        """
        Calculate acceptable entry price range

        Args:
            dump_low: Dump low price (ideal entry)
            target_profit_pct: Target profit percentage (e.g., 3.0 = 3%)
            min_acceptable_profit_pct: Minimum acceptable profit (e.g., 2.0 = 2%)

        Returns:
            Dict with price ranges
        """
        # Calculate max acceptable entry price
        # If target is 3% and min acceptable is 2%, can enter up to 1% above low
        max_entry_distance_pct = target_profit_pct - min_acceptable_profit_pct

        max_entry_price = dump_low * (1 + max_entry_distance_pct / 100)

        return {
            'ideal_entry': dump_low,
            'max_acceptable_entry': max_entry_price,
            'entry_range_pct': max_entry_distance_pct,
            'target_profit_pct': target_profit_pct,
            'min_acceptable_profit_pct': min_acceptable_profit_pct
        }

    def simulate_entry_timing_scenarios(self,
                                       dump_low: float,
                                       dump_high: float,
                                       exit_price: float,
                                       num_scenarios: int = 10) -> pd.DataFrame:
        """
        Simulate different entry timing scenarios

        Shows P&L for entries at different points during dump

        Args:
            dump_low: Lowest price during dump
            dump_high: Highest price before dump
            exit_price: Actual exit price
            num_scenarios: Number of entry price scenarios to test

        Returns:
            DataFrame with scenario analysis
        """
        scenarios = []

        # Create entry prices from dump high to dump low
        price_range = dump_high - dump_low
        step = price_range / (num_scenarios - 1) if num_scenarios > 1 else 0

        for i in range(num_scenarios):
            entry_price = dump_high - (step * i)
            profit_pct = ((exit_price - entry_price) / entry_price) * 100
            distance_from_low_pct = ((entry_price - dump_low) / dump_low) * 100

            scenarios.append({
                'scenario': f"Entry #{i+1}",
                'entry_price': entry_price,
                'distance_from_low_pct': distance_from_low_pct,
                'profit_pct': profit_pct,
                'profit_usd_per_1k': profit_pct * 10  # Profit on $1000
            })

        df = pd.DataFrame(scenarios)

        return df

    def generate_entry_timing_report(self,
                                    trades: List[Any],
                                    strategy_stats: Dict[str, Any]) -> str:
        """
        Generate human-readable entry timing report

        Args:
            trades: List of Trade objects
            strategy_stats: Strategy statistics

        Returns:
            Formatted report string
        """
        analysis = self.analyze_entry_quality(trades, strategy_stats)

        report = []
        report.append("=" * 80)
        report.append("ENTRY TIMING QUALITY REPORT")
        report.append("=" * 80)

        if analysis['total_trades'] == 0:
            report.append("\nNo trades to analyze.")
            return "\n".join(report)

        # Entry quality metrics
        if analysis['entry_quality_metrics']:
            metrics = analysis['entry_quality_metrics']
            report.append("\nENTRY DISTANCE FROM DUMP LOW:")
            report.append(f"  Average: {metrics['avg_distance_from_low_pct']:.2f}%")
            report.append(f"  Best:    {metrics['min_distance_from_low_pct']:.2f}%")
            report.append(f"  Worst:   {metrics['max_distance_from_low_pct']:.2f}%")
            report.append(f"\nENTRY TIMING DISTRIBUTION:")
            report.append(f"  Within 1% of low: {metrics['entries_within_1pct']} trades")
            report.append(f"  Within 2% of low: {metrics['entries_within_2pct']} trades")
            report.append(f"  Beyond 2% of low: {metrics['entries_beyond_2pct']} trades")

        # Missed profit analysis
        if analysis['missed_profit_analysis']:
            missed = analysis['missed_profit_analysis']
            report.append(f"\nPROFIT IMPACT:")
            report.append(f"  Winning trades: {missed['winning_trades']}")
            report.append(f"  Losing trades:  {missed['losing_trades']}")
            if 'estimated_missed_profit_pct' in missed:
                report.append(f"\n  Estimated missed profit from entry timing:")
                report.append(f"    ~{missed['estimated_missed_profit_pct']:.2f}% per winning trade")
                report.append(f"    (if entries were at exact dump low)")

        # Recommendations
        report.append("\n" + "=" * 80)
        report.append("RECOMMENDATIONS")
        report.append("=" * 80)

        if analysis['entry_quality_metrics']:
            avg_dist = analysis['entry_quality_metrics']['avg_distance_from_low_pct']

            if avg_dist < 0.5:
                report.append("\n✅ EXCELLENT: Your entries are very close to dump lows!")
                report.append("   Continue current execution method.")
            elif avg_dist < 1.0:
                report.append("\n👍 GOOD: Your entries are within 1% of dump lows")
                report.append("   This is realistic for manual trading.")
            elif avg_dist < 2.0:
                report.append("\n⚠️  FAIR: Your entries average 1-2% above dump lows")
                report.append("   Consider using limit order ladders for better fills.")
            else:
                report.append("\n❌ POOR: Your entries are >2% above dump lows")
                report.append("   Recommendation:")
                report.append("   1. Use limit orders instead of market orders")
                report.append("   2. Place orders DURING the dump, not after")
                report.append("   3. Reduce entry delay (faster execution)")

        return "\n".join(report)

    def create_entry_range_visualization_data(self,
                                             dump_low: float,
                                             dump_high: float,
                                             target_profit_pct: float = 3.0) -> Dict[str, Any]:
        """
        Create data for visualizing acceptable entry range

        Args:
            dump_low: Dump low price
            dump_high: Dump high before dump
            target_profit_pct: Target profit percentage

        Returns:
            Dict with visualization data
        """
        # Calculate zones
        ideal_entry = dump_low
        good_entry = dump_low * 1.01      # Within 1%
        acceptable_entry = dump_low * 1.02  # Within 2%
        poor_entry = dump_low * 1.03      # Beyond 2%

        # Calculate profit at each level
        exit_target = dump_low * (1 + target_profit_pct / 100)

        viz_data = {
            'zones': {
                'ideal': {
                    'price': ideal_entry,
                    'label': 'Ideal (Dump Low)',
                    'color': 'green',
                    'profit_at_target': target_profit_pct
                },
                'good': {
                    'price': good_entry,
                    'label': 'Good (Within 1%)',
                    'color': 'lightgreen',
                    'profit_at_target': ((exit_target - good_entry) / good_entry) * 100
                },
                'acceptable': {
                    'price': acceptable_entry,
                    'label': 'Acceptable (Within 2%)',
                    'color': 'yellow',
                    'profit_at_target': ((exit_target - acceptable_entry) / acceptable_entry) * 100
                },
                'poor': {
                    'price': poor_entry,
                    'label': 'Poor (Beyond 2%)',
                    'color': 'red',
                    'profit_at_target': ((exit_target - poor_entry) / poor_entry) * 100
                }
            },
            'dump_range': {
                'high': dump_high,
                'low': dump_low,
                'drop_pct': ((dump_high - dump_low) / dump_high) * 100
            },
            'target_exit': exit_target
        }

        return viz_data
