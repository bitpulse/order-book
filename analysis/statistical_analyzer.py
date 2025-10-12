"""
Statistical Analysis Module

Performs statistical analysis on order book data:
- Correlation analysis (OFI vs returns, spread vs volatility)
- Predictive modeling metrics
- Distribution analysis
- Hypothesis testing

Research Reference:
- OFI-return correlation: R² ~50%
- Spread-volatility: R² >90%
- Statistical significance testing
"""

import pandas as pd
import numpy as np
from scipy import stats
from typing import Dict, Tuple
from loguru import logger


class StatisticalAnalyzer:
    """Statistical analysis of order book patterns"""

    def __init__(self):
        pass

    def analyze_correlations(self, ofi_df: pd.DataFrame,
                            micro_df: pd.DataFrame) -> Dict:
        """
        Comprehensive correlation analysis

        Args:
            ofi_df: DataFrame with OFI metrics
            micro_df: DataFrame with microstructure indicators

        Returns:
            Dict with correlation results
        """
        logger.info("Analyzing statistical correlations...")

        if ofi_df.empty or micro_df.empty:
            return {}

        # Merge datasets
        ofi_df = ofi_df.set_index('time')
        micro_df = micro_df.set_index('time')

        # Check available columns in micro_df
        available_cols = []
        for col in ['mid_price', 'returns', 'spread_bps', 'volatility_1m']:
            if col in micro_df.columns:
                available_cols.append(col)

        if not available_cols:
            logger.warning("No microstructure columns available for correlation analysis")
            return {}

        combined = pd.merge_asof(
            ofi_df.sort_index(),
            micro_df[available_cols].sort_index(),
            left_index=True,
            right_index=True,
            direction='nearest'
        ).dropna()

        if combined.empty:
            return {}

        correlations = {}

        # === OFI CORRELATIONS WITH FUTURE RETURNS ===
        if 'mid_price' in combined.columns:
            for seconds in [1, 5, 30, 60]:
                combined[f'future_return_{seconds}s'] = combined['mid_price'].shift(-seconds).pct_change()
        else:
            logger.warning("mid_price not available, skipping future return calculations")
            return correlations

        for seconds in [1, 5, 30, 60]:
            col = f'future_return_{seconds}s'
            if col in combined.columns:
                valid = combined[['ofi', 'ofi_with_trades', 'depth_imbalance', col]].dropna()

                if len(valid) > 10:
                    # Pearson correlation
                    ofi_corr, ofi_pval = stats.pearsonr(valid['ofi'], valid[col])
                    ofi_trades_corr, ofi_trades_pval = stats.pearsonr(valid['ofi_with_trades'], valid[col])
                    depth_corr, depth_pval = stats.pearsonr(valid['depth_imbalance'], valid[col])

                    correlations[f'ofi_vs_return_{seconds}s'] = {
                        'ofi_correlation': float(ofi_corr),
                        'ofi_pvalue': float(ofi_pval),
                        'ofi_r_squared': float(ofi_corr ** 2),
                        'ofi_with_trades_correlation': float(ofi_trades_corr),
                        'ofi_with_trades_pvalue': float(ofi_trades_pval),
                        'ofi_with_trades_r_squared': float(ofi_trades_corr ** 2),
                        'depth_imbalance_correlation': float(depth_corr),
                        'depth_imbalance_pvalue': float(depth_pval),
                        'depth_imbalance_r_squared': float(depth_corr ** 2),
                        'sample_size': len(valid),
                        'significant': ofi_pval < 0.05
                    }

        # === SPREAD-VOLATILITY CORRELATION ===
        spread_vol = combined[['spread_bps', 'volatility_1m']].dropna()
        if len(spread_vol) > 10:
            corr, pval = stats.pearsonr(spread_vol['spread_bps'], spread_vol['volatility_1m'])
            correlations['spread_vs_volatility'] = {
                'correlation': float(corr),
                'pvalue': float(pval),
                'r_squared': float(corr ** 2),
                'sample_size': len(spread_vol),
                'significant': pval < 0.05
            }

        # === OFI AUTOCORRELATION (PERSISTENCE) ===
        if len(combined) > 20:
            ofi_values = combined['ofi'].values

            autocorrs = {}
            for lag in [1, 5, 10, 20]:
                if len(ofi_values) > lag:
                    autocorr = np.corrcoef(ofi_values[:-lag], ofi_values[lag:])[0, 1]
                    autocorrs[f'lag_{lag}'] = float(autocorr)

            correlations['ofi_autocorrelation'] = autocorrs

        # === MARKET BUY/SELL IMBALANCE VS RETURNS ===
        if 'market_buy_volume' in combined.columns and 'market_sell_volume' in combined.columns:
            combined['trade_imbalance'] = (
                (combined['market_buy_volume'] - combined['market_sell_volume']) /
                (combined['market_buy_volume'] + combined['market_sell_volume'] + 1e-9)
            )

            for seconds in [1, 5, 30]:
                col = f'future_return_{seconds}s'
                if col in combined.columns:
                    valid = combined[['trade_imbalance', col]].dropna()
                    if len(valid) > 10:
                        corr, pval = stats.pearsonr(valid['trade_imbalance'], valid[col])
                        correlations[f'trade_imbalance_vs_return_{seconds}s'] = {
                            'correlation': float(corr),
                            'pvalue': float(pval),
                            'r_squared': float(corr ** 2),
                            'sample_size': len(valid),
                            'significant': pval < 0.05
                        }

        logger.info(f"Calculated {len(correlations)} correlation sets")
        return correlations

    def analyze_distributions(self, ofi_df: pd.DataFrame,
                             events_df: pd.DataFrame) -> Dict:
        """
        Analyze statistical distributions

        Args:
            ofi_df: DataFrame with OFI metrics
            events_df: DataFrame with whale events

        Returns:
            Dict with distribution statistics
        """
        logger.info("Analyzing distributions...")

        distributions = {}

        # === OFI DISTRIBUTION ===
        if not ofi_df.empty and 'ofi' in ofi_df.columns:
            ofi_values = ofi_df['ofi'].dropna()

            if len(ofi_values) > 0:
                # Test for normality
                _, normality_pval = stats.normaltest(ofi_values)

                # Skewness and kurtosis
                skew = stats.skew(ofi_values)
                kurt = stats.kurtosis(ofi_values)

                distributions['ofi'] = {
                    'mean': float(ofi_values.mean()),
                    'std': float(ofi_values.std()),
                    'median': float(ofi_values.median()),
                    'min': float(ofi_values.min()),
                    'max': float(ofi_values.max()),
                    'skewness': float(skew),
                    'kurtosis': float(kurt),
                    'normality_pvalue': float(normality_pval),
                    'is_normal': normality_pval > 0.05,
                    'percentile_25': float(ofi_values.quantile(0.25)),
                    'percentile_75': float(ofi_values.quantile(0.75)),
                    'percentile_95': float(ofi_values.quantile(0.95)),
                    'percentile_99': float(ofi_values.quantile(0.99))
                }

        # === ORDER SIZE DISTRIBUTION ===
        if not events_df.empty and 'usd_value' in events_df.columns:
            usd_values = events_df['usd_value'].dropna()

            if len(usd_values) > 0:
                # Log transform for power law analysis
                log_usd = np.log10(usd_values + 1)

                distributions['order_size'] = {
                    'mean_usd': float(usd_values.mean()),
                    'median_usd': float(usd_values.median()),
                    'std_usd': float(usd_values.std()),
                    'max_usd': float(usd_values.max()),
                    'percentile_90': float(usd_values.quantile(0.90)),
                    'percentile_95': float(usd_values.quantile(0.95)),
                    'percentile_99': float(usd_values.quantile(0.99)),
                    'skewness': float(stats.skew(usd_values)),
                    'kurtosis': float(stats.kurtosis(usd_values))
                }

        logger.info(f"Analyzed {len(distributions)} distributions")
        return distributions

    def test_ofi_predictive_power(self, ofi_df: pd.DataFrame,
                                  price_df: pd.DataFrame,
                                  forecast_horizon: int = 5) -> Dict:
        """
        Test predictive power of OFI for future returns

        Uses simple linear regression: return_t+h = α + β*OFI_t + ε

        Args:
            ofi_df: DataFrame with OFI metrics
            price_df: DataFrame with price data
            forecast_horizon: Seconds ahead to forecast

        Returns:
            Dict with regression statistics
        """
        logger.info(f"Testing OFI predictive power ({forecast_horizon}s horizon)...")

        if ofi_df.empty or price_df.empty:
            return {}

        # Merge data
        ofi_df = ofi_df.set_index('time')
        price_df = price_df.set_index('time')

        combined = pd.merge_asof(
            ofi_df[['ofi', 'ofi_with_trades', 'depth_imbalance']].sort_index(),
            price_df[['mid_price']].sort_index(),
            left_index=True,
            right_index=True,
            direction='nearest'
        )

        # Calculate future returns
        combined['future_return'] = combined['mid_price'].shift(-forecast_horizon).pct_change()
        valid = combined.dropna()

        if len(valid) < 30:
            return {}

        results = {}

        # Test each OFI variant
        for predictor in ['ofi', 'ofi_with_trades', 'depth_imbalance']:
            if predictor not in valid.columns:
                continue

            X = valid[predictor].values
            y = valid['future_return'].values

            # Linear regression
            slope, intercept, r_value, p_value, std_err = stats.linregress(X, y)

            # Calculate residuals
            y_pred = intercept + slope * X
            residuals = y - y_pred
            mse = np.mean(residuals ** 2)
            rmse = np.sqrt(mse)

            # Information criterion (AIC approximation)
            n = len(y)
            aic = n * np.log(mse) + 2 * 2  # 2 parameters (slope, intercept)

            results[predictor] = {
                'slope': float(slope),
                'intercept': float(intercept),
                'r_value': float(r_value),
                'r_squared': float(r_value ** 2),
                'p_value': float(p_value),
                'std_error': float(std_err),
                'rmse': float(rmse),
                'aic': float(aic),
                'sample_size': int(n),
                'significant': p_value < 0.05
            }

        logger.info(f"Tested {len(results)} predictors")
        return results

    def calculate_sharpe_ratio(self, signals_df: pd.DataFrame,
                              returns_col: str = 'future_return_5s',
                              signal_col: str = 'ofi_zscore',
                              threshold: float = 1.0) -> Dict:
        """
        Calculate Sharpe ratio of a simple trading strategy based on signals

        Args:
            signals_df: DataFrame with signals and returns
            returns_col: Column name for returns
            signal_col: Column name for signal
            threshold: Signal threshold for entry

        Returns:
            Dict with performance metrics
        """
        logger.info("Calculating Sharpe ratio...")

        if signals_df.empty or returns_col not in signals_df.columns or signal_col not in signals_df.columns:
            return {}

        df = signals_df.copy()

        # Generate trading signals
        df['position'] = 0
        df.loc[df[signal_col] > threshold, 'position'] = 1  # Long
        df.loc[df[signal_col] < -threshold, 'position'] = -1  # Short

        # Calculate strategy returns
        df['strategy_return'] = df['position'].shift(1) * df[returns_col]
        df = df.dropna()

        if len(df) == 0 or df['strategy_return'].std() == 0:
            return {}

        # Performance metrics
        total_return = df['strategy_return'].sum()
        mean_return = df['strategy_return'].mean()
        std_return = df['strategy_return'].std()
        sharpe = mean_return / std_return if std_return > 0 else 0

        # Annualized (assuming 5-second returns)
        periods_per_day = (24 * 60 * 60) / 5
        sharpe_annualized = sharpe * np.sqrt(periods_per_day)

        # Win rate
        wins = (df['strategy_return'] > 0).sum()
        losses = (df['strategy_return'] < 0).sum()
        win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0

        # Maximum drawdown
        cumulative = (1 + df['strategy_return']).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min()

        return {
            'sharpe_ratio': float(sharpe),
            'sharpe_ratio_annualized': float(sharpe_annualized),
            'total_return': float(total_return),
            'mean_return': float(mean_return),
            'std_return': float(std_return),
            'win_rate': float(win_rate),
            'num_trades': int(wins + losses),
            'num_wins': int(wins),
            'num_losses': int(losses),
            'max_drawdown': float(max_drawdown),
            'sample_size': len(df)
        }
