#!/usr/bin/env python3
"""
Test Deep Fill Reversal Strategy - Parameter Sweep

This script runs multiple backtests with different parameter combinations:
- Market sell size thresholds: 500K, 1M, 5M, 10M, 30M
- Distance thresholds: 0.01%, 0.05%, 0.1%, 0.2%, 0.5%
- Risk management variations: Scalping, Swing, Aggressive
"""

import sys
sys.path.insert(0, '/home/luka/bitpulse/order-book')

from dotenv import load_dotenv
load_dotenv()

from backtesting import BacktestEngine, DeepFillReversalStrategy
from backtesting.core.report_generator import ReportGenerator
from loguru import logger

# Configure logging
logger.remove()
logger.add(sys.stdout, level="INFO")

def main():
    """Test deep fill reversal strategy with multiple parameter combinations"""

    logger.info("=" * 80)
    logger.info("DEEP FILL REVERSAL STRATEGY - PARAMETER SWEEP")
    logger.info("=" * 80)

    # Test period
    symbol = 'TAO_USDT'
    start = '2025-10-14T00:00:00Z'
    end = '2025-10-16T00:00:00Z'

    logger.info(f"\nTesting on {symbol}")
    logger.info(f"Period: {start} to {end} (2 days)")
    logger.info("-" * 80)

    # Define parameter combinations to test
    param_combinations = [
        # =====================================================================
        # DISTANCE THRESHOLD SWEEP - $1M minimum
        # =====================================================================
        {
            'name': '1M - Ultra Aggressive (0.01%)',
            'min_market_sell_usd': 1_000_000,
            'min_distance_from_mid_pct': 0.01,
            'stop_loss_pct': 0.015,
            'take_profit_pct': 0.030,
            'timeout_seconds': 60,
            'cooldown_seconds': 120
        },
        {
            'name': '1M - Very Aggressive (0.05%)',
            'min_market_sell_usd': 1_000_000,
            'min_distance_from_mid_pct': 0.05,
            'stop_loss_pct': 0.015,
            'take_profit_pct': 0.030,
            'timeout_seconds': 60,
            'cooldown_seconds': 120
        },
        {
            'name': '1M - Aggressive (0.1%)',
            'min_market_sell_usd': 1_000_000,
            'min_distance_from_mid_pct': 0.1,
            'stop_loss_pct': 0.015,
            'take_profit_pct': 0.030,
            'timeout_seconds': 60,
            'cooldown_seconds': 120
        },
        {
            'name': '1M - Moderate (0.2%)',
            'min_market_sell_usd': 1_000_000,
            'min_distance_from_mid_pct': 0.2,
            'stop_loss_pct': 0.015,
            'take_profit_pct': 0.030,
            'timeout_seconds': 60,
            'cooldown_seconds': 120
        },
        {
            'name': '1M - Conservative (0.5%)',
            'min_market_sell_usd': 1_000_000,
            'min_distance_from_mid_pct': 0.5,
            'stop_loss_pct': 0.015,
            'take_profit_pct': 0.030,
            'timeout_seconds': 60,
            'cooldown_seconds': 120
        },
        # =====================================================================
        # SELL SIZE SWEEP - 0.1% distance threshold
        # =====================================================================
        {
            'name': '500K - Base (0.1%)',
            'min_market_sell_usd': 500_000,
            'min_distance_from_mid_pct': 0.1,
            'stop_loss_pct': 0.015,
            'take_profit_pct': 0.030,
            'timeout_seconds': 60,
            'cooldown_seconds': 120
        },
        {
            'name': '5M - Base (0.1%)',
            'min_market_sell_usd': 5_000_000,
            'min_distance_from_mid_pct': 0.1,
            'stop_loss_pct': 0.015,
            'take_profit_pct': 0.030,
            'timeout_seconds': 60,
            'cooldown_seconds': 120
        },
        {
            'name': '10M - Base (0.1%)',
            'min_market_sell_usd': 10_000_000,
            'min_distance_from_mid_pct': 0.1,
            'stop_loss_pct': 0.015,
            'take_profit_pct': 0.030,
            'timeout_seconds': 60,
            'cooldown_seconds': 120
        },
        {
            'name': '30M - Base (0.1%)',
            'min_market_sell_usd': 30_000_000,
            'min_distance_from_mid_pct': 0.1,
            'stop_loss_pct': 0.015,
            'take_profit_pct': 0.030,
            'timeout_seconds': 60,
            'cooldown_seconds': 120
        },
        # =====================================================================
        # DISTANCE SWEEP - $5M minimum
        # =====================================================================
        {
            'name': '5M - Very Aggressive (0.05%)',
            'min_market_sell_usd': 5_000_000,
            'min_distance_from_mid_pct': 0.05,
            'stop_loss_pct': 0.015,
            'take_profit_pct': 0.030,
            'timeout_seconds': 60,
            'cooldown_seconds': 120
        },
        {
            'name': '5M - Moderate (0.2%)',
            'min_market_sell_usd': 5_000_000,
            'min_distance_from_mid_pct': 0.2,
            'stop_loss_pct': 0.015,
            'take_profit_pct': 0.030,
            'timeout_seconds': 60,
            'cooldown_seconds': 120
        },
        {
            'name': '5M - Conservative (0.5%)',
            'min_market_sell_usd': 5_000_000,
            'min_distance_from_mid_pct': 0.5,
            'stop_loss_pct': 0.015,
            'take_profit_pct': 0.030,
            'timeout_seconds': 60,
            'cooldown_seconds': 120
        },
        # =====================================================================
        # RISK MANAGEMENT VARIATIONS - $1M, 0.1% distance
        # =====================================================================
        {
            'name': '1M - Scalping (0.1%)',
            'min_market_sell_usd': 1_000_000,
            'min_distance_from_mid_pct': 0.1,
            'stop_loss_pct': 0.010,  # 1.0% tight stop
            'take_profit_pct': 0.020,  # 2.0% quick target
            'timeout_seconds': 30,
            'cooldown_seconds': 60
        },
        {
            'name': '1M - Swing (0.1%)',
            'min_market_sell_usd': 1_000_000,
            'min_distance_from_mid_pct': 0.1,
            'stop_loss_pct': 0.020,  # 2.0% wider stop
            'take_profit_pct': 0.050,  # 5.0% bigger target
            'timeout_seconds': 120,
            'cooldown_seconds': 180
        },
        {
            'name': '1M - Aggressive R:R (0.1%)',
            'min_market_sell_usd': 1_000_000,
            'min_distance_from_mid_pct': 0.1,
            'stop_loss_pct': 0.012,  # 1.2% tight
            'take_profit_pct': 0.040,  # 4.0% ambitious
            'timeout_seconds': 90,
            'cooldown_seconds': 120
        },
        # =====================================================================
        # OPTIMAL COMBINATIONS (based on expected behavior)
        # =====================================================================
        {
            'name': 'Optimal 1 - Frequent (1M, 0.05%)',
            'min_market_sell_usd': 1_000_000,
            'min_distance_from_mid_pct': 0.05,
            'stop_loss_pct': 0.015,
            'take_profit_pct': 0.030,
            'timeout_seconds': 60,
            'cooldown_seconds': 90
        },
        {
            'name': 'Optimal 2 - Balanced (5M, 0.1%)',
            'min_market_sell_usd': 5_000_000,
            'min_distance_from_mid_pct': 0.1,
            'stop_loss_pct': 0.018,
            'take_profit_pct': 0.035,
            'timeout_seconds': 75,
            'cooldown_seconds': 120
        },
        {
            'name': 'Optimal 3 - Selective (10M, 0.2%)',
            'min_market_sell_usd': 10_000_000,
            'min_distance_from_mid_pct': 0.2,
            'stop_loss_pct': 0.020,
            'take_profit_pct': 0.040,
            'timeout_seconds': 90,
            'cooldown_seconds': 180
        }
    ]

    results = []

    # Create initial engine with first strategy
    logger.info("\nInitializing backtest engine with data caching enabled...")

    initial_strategy = DeepFillReversalStrategy(
        min_distance_from_mid_pct=param_combinations[0]['min_distance_from_mid_pct'],
        min_market_sell_usd=param_combinations[0]['min_market_sell_usd'],
        stop_loss_pct=param_combinations[0]['stop_loss_pct'],
        take_profit_pct=param_combinations[0]['take_profit_pct'],
        timeout_seconds=param_combinations[0]['timeout_seconds'],
        entry_delay_seconds=2,
        cooldown_seconds=param_combinations[0]['cooldown_seconds'],
        max_spread_pct=0.05
    )

    engine = BacktestEngine(
        strategy=initial_strategy,
        initial_capital=10000,
        position_size_pct=10.0,
        max_positions=1
    )

    # Load data ONCE before running all backtests (major speedup!)
    logger.info("\n" + "=" * 80)
    logger.info("LOADING DATA (will be reused for all 18 backtests)")
    logger.info("=" * 80)

    # Force data load and cache with first run
    logger.info("Running initial data load...")
    first_result = engine.run(
        symbol=symbol,
        start=start,
        end=end,
        min_whale_usd=50000,
        window_size='1s',
        use_cache=True
    )

    # Store first result
    stats = initial_strategy.get_statistics()
    results.append({
        'name': param_combinations[0]['name'],
        'params': param_combinations[0],
        'result': first_result,
        'stats': stats
    })

    logger.info(f"✅ Data cached! Now running remaining {len(param_combinations)-1} backtests...")
    logger.info(f"   Deep Sells: {stats['deep_sells_detected']}, Trades: {first_result.num_trades}, Return: {first_result.total_return:+.2f}%")

    # Run backtests for remaining parameter combinations (much faster now!)
    for i, params in enumerate(param_combinations[1:], 1):
        logger.info("\n" + "-" * 80)
        logger.info(f"[{i+1}/{len(param_combinations)}] {params['name']}")
        logger.info(f"  Sell: ${params['min_market_sell_usd']/1e6:.1f}M | Distance: {params['min_distance_from_mid_pct']}% | "
                   f"SL: {params['stop_loss_pct']*100:.1f}% | TP: {params['take_profit_pct']*100:.1f}%")

        # Create strategy with current parameters
        strategy = DeepFillReversalStrategy(
            min_distance_from_mid_pct=params['min_distance_from_mid_pct'],
            min_market_sell_usd=params['min_market_sell_usd'],
            stop_loss_pct=params['stop_loss_pct'],
            take_profit_pct=params['take_profit_pct'],
            timeout_seconds=params['timeout_seconds'],
            entry_delay_seconds=2,
            cooldown_seconds=params['cooldown_seconds'],
            max_spread_pct=0.05
        )

        # Update engine's strategy for this run
        engine.strategy = strategy

        try:
            # Run backtest (data already cached - super fast!)
            result = engine.run(
                symbol=symbol,
                start=start,
                end=end,
                min_whale_usd=50000,
                window_size='1s',
                use_cache=True  # Will use cached data from first run
            )

            # Print brief summary on same line
            stats = strategy.get_statistics()
            sharpe_str = f"Sharpe: {result.sharpe_ratio:.2f}" if result.sharpe_ratio is not None else "Sharpe: N/A"
            logger.info(f"  ✅ Sells: {stats['deep_sells_detected']} | Trades: {result.num_trades} | "
                       f"Win: {result.win_rate:.1f}% | Return: {result.total_return:+.2f}% | {sharpe_str}")

            # Store result for comparison
            results.append({
                'name': params['name'],
                'params': params,
                'result': result,
                'stats': stats
            })

        except Exception as e:
            logger.error(f"❌ {params['name']} backtest failed: {e}")
            import traceback
            traceback.print_exc()
            continue

    # Generate comparison summary
    if results:
        logger.info("\n\n" + "=" * 80)
        logger.info("COMPARISON OF ALL STRATEGIES")
        logger.info("=" * 80)

        # Sort by total return
        sorted_results = sorted(results, key=lambda x: x['result'].total_return, reverse=True)

        logger.info(f"\n{'Strategy':<35} {'Signals':>8} {'Trades':>8} {'Win%':>8} {'Return%':>10} {'Sharpe':>8} {'MaxDD%':>8}")
        logger.info("-" * 100)

        for r in sorted_results:
            name = r['name']
            result = r['result']
            stats = r['stats']

            sharpe = f"{result.sharpe_ratio:.2f}" if result.sharpe_ratio is not None else "N/A"

            logger.info(
                f"{name:<35} "
                f"{stats['signals_generated']:>8} "
                f"{result.num_trades:>8} "
                f"{result.win_rate:>8.1f} "
                f"{result.total_return:>10.2f} "
                f"{sharpe:>8} "
                f"{result.max_drawdown:>8.2f}"
            )

        # Identify best performers
        logger.info("\n" + "=" * 80)
        logger.info("TOP 3 PERFORMERS (by Return)")
        logger.info("=" * 80)

        for i, r in enumerate(sorted_results[:3], 1):
            logger.info(f"\n{i}. {r['name']}")
            logger.info(f"   Total Return: {r['result'].total_return:+.2f}%")
            logger.info(f"   Win Rate: {r['result'].win_rate:.1f}%")
            logger.info(f"   Trades: {r['result'].num_trades}")
            logger.info(f"   Sharpe: {r['result'].sharpe_ratio:.2f}" if r['result'].sharpe_ratio else "   Sharpe: N/A")
            logger.info(f"   Signals: {r['stats']['signals_generated']}")
            logger.info(f"   Min Sell Size: ${r['params']['min_market_sell_usd']:,.0f}")
            logger.info(f"   Min Distance: {r['params']['min_distance_from_mid_pct']}%")

        # Generate comparison report
        logger.info("\n" + "=" * 80)
        logger.info("GENERATING HTML COMPARISON REPORT")
        logger.info("=" * 80)

        try:
            report_gen = ReportGenerator(output_dir="reports")
            report_path = report_gen.generate_comparison_report(
                results=results,
                symbol=symbol,
                start_time=start,
                end_time=end
            )

            logger.info(f"\n✅ Comparison report generated: {report_path}")
            logger.info(f"\nOpen in browser: file://{report_path}")

        except Exception as e:
            logger.error(f"❌ Report generation failed: {e}")

        logger.info("\n" + "=" * 80)
        logger.info("✅ All backtests completed successfully!")
        logger.info("=" * 80)

    return 0


if __name__ == '__main__':
    sys.exit(main())
