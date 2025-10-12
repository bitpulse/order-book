"""
Market Microstructure Indicators Module

Calculates key microstructure indicators:
- Bid-ask spread dynamics
- Volatility measures (realized, GARCH-style)
- Price velocity and momentum
- Volume-weighted metrics
- Trade intensity

Research Reference:
- Spread-volatility correlation: R² > 0.9
- Microstructure noise impacts short-term price discovery
"""

import pandas as pd
import numpy as np
from loguru import logger


class MicrostructureCalculator:
    """Calculate market microstructure indicators"""

    def __init__(self):
        pass

    def calculate_all(self, price_df: pd.DataFrame, events_df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate all microstructure indicators

        Args:
            price_df: DataFrame with price data
            events_df: DataFrame with whale events

        Returns:
            DataFrame with microstructure indicators
        """
        logger.info("Calculating microstructure indicators...")

        if price_df.empty:
            return pd.DataFrame()

        df = price_df.copy().set_index('time')

        # Resample to regular 1-second intervals
        df_1s = df.resample('1s').last().ffill()

        # === RETURNS ===
        df_1s['returns'] = df_1s['mid_price'].pct_change()
        df_1s['log_returns'] = np.log(df_1s['mid_price'] / df_1s['mid_price'].shift(1))

        # === SPREAD METRICS ===
        df_1s['spread_bps'] = (df_1s['spread'] / df_1s['mid_price']) * 10000  # Basis points
        df_1s['spread_ma'] = df_1s['spread_bps'].rolling(60, min_periods=1).mean()
        df_1s['spread_std'] = df_1s['spread_bps'].rolling(60, min_periods=1).std()
        df_1s['spread_zscore'] = (df_1s['spread_bps'] - df_1s['spread_ma']) / (df_1s['spread_std'] + 1e-9)

        # Relative spread (current vs recent average)
        df_1s['relative_spread'] = df_1s['spread_bps'] / (df_1s['spread_ma'] + 1e-9)

        # === VOLATILITY ===
        # Rolling standard deviation (1-minute and 5-minute)
        df_1s['volatility_1m'] = df_1s['returns'].rolling(60, min_periods=10).std() * np.sqrt(60)
        df_1s['volatility_5m'] = df_1s['returns'].rolling(300, min_periods=30).std() * np.sqrt(300)

        # Realized volatility (sum of squared returns)
        df_1s['realized_vol_1m'] = np.sqrt((df_1s['returns'] ** 2).rolling(60, min_periods=10).sum())
        df_1s['realized_vol_5m'] = np.sqrt((df_1s['returns'] ** 2).rolling(300, min_periods=30).sum())

        # Parkinson volatility estimator (uses high-low range)
        # Note: We use bid-ask as proxy for high-low
        df_1s['parkinson_vol'] = np.sqrt(
            ((np.log(df_1s['best_ask'] / df_1s['best_bid']) ** 2) / (4 * np.log(2)))
            .rolling(60, min_periods=10).mean()
        )

        # === PRICE DYNAMICS ===
        # Price velocity (rate of change)
        df_1s['price_velocity_1s'] = df_1s['mid_price'].diff(1)
        df_1s['price_velocity_5s'] = df_1s['mid_price'].diff(5) / 5
        df_1s['price_velocity_30s'] = df_1s['mid_price'].diff(30) / 30

        # Price acceleration (second derivative)
        df_1s['price_acceleration'] = df_1s['price_velocity_1s'].diff()

        # Price momentum (rolling return)
        df_1s['momentum_1m'] = df_1s['mid_price'].pct_change(60)
        df_1s['momentum_5m'] = df_1s['mid_price'].pct_change(300)

        # === MICROSTRUCTURE NOISE ===
        # Roll's measure (estimate of bid-ask bounce)
        df_1s['rolls_measure'] = np.sqrt(-df_1s['returns'].rolling(60, min_periods=10).cov(df_1s['returns'].shift(1)))

        # Effective spread (estimated from price changes)
        df_1s['effective_spread'] = 2 * abs(df_1s['returns'])

        # === TRADING INTENSITY ===
        if not events_df.empty:
            trade_intensity = self._calculate_trade_intensity(events_df)
            df_1s = pd.merge_asof(
                df_1s.sort_index(),
                trade_intensity.set_index('time').sort_index(),
                left_index=True,
                right_index=True,
                direction='nearest'
            )

        logger.info(f"Calculated microstructure indicators for {len(df_1s)} time points")
        return df_1s.reset_index()

    def _calculate_trade_intensity(self, events_df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate trade intensity metrics

        Args:
            events_df: DataFrame with whale events

        Returns:
            DataFrame with trade intensity per second
        """
        # Filter trade events
        trades = events_df[events_df['event_type'].isin(['market_buy', 'market_sell'])].copy()

        if trades.empty:
            return pd.DataFrame()

        # Resample to 1-second intervals
        trades = trades.set_index('time')

        intensity = trades.resample('1s').agg({
            'volume': 'sum',
            'usd_value': 'sum',
            'event_type': 'count'
        }).rename(columns={'event_type': 'trade_count'})

        # Rolling trade intensity
        intensity['trade_intensity_1m'] = intensity['trade_count'].rolling(60, min_periods=1).sum()
        intensity['volume_intensity_1m'] = intensity['volume'].rolling(60, min_periods=1).sum()
        intensity['usd_intensity_1m'] = intensity['usd_value'].rolling(60, min_periods=1).sum()

        # Buy/sell imbalance
        buys = trades[trades['event_type'] == 'market_buy'].resample('1s')['volume'].sum()
        sells = trades[trades['event_type'] == 'market_sell'].resample('1s')['volume'].sum()

        intensity['buy_volume'] = buys
        intensity['sell_volume'] = sells
        intensity['trade_imbalance'] = (buys - sells) / (buys + sells + 1e-9)

        return intensity.reset_index()

    def calculate_spread_volatility_correlation(self, micro_df: pd.DataFrame,
                                               window: int = 300) -> pd.DataFrame:
        """
        Calculate rolling correlation between spread and volatility

        Research shows R² > 0.9 relationship

        Args:
            micro_df: DataFrame with microstructure indicators
            window: Rolling window in seconds

        Returns:
            DataFrame with correlation metrics
        """
        logger.info("Calculating spread-volatility correlation...")

        if micro_df.empty or 'spread_bps' not in micro_df.columns or 'volatility_1m' not in micro_df.columns:
            return pd.DataFrame()

        df = micro_df.set_index('time')

        # Rolling correlation
        df['spread_vol_corr'] = df['spread_bps'].rolling(window).corr(df['volatility_1m'])

        # Rolling R²
        df['spread_vol_r2'] = df['spread_vol_corr'] ** 2

        result = df[['spread_vol_corr', 'spread_vol_r2']].reset_index()
        logger.info(f"Calculated correlation for {len(result)} time points")
        return result

    def detect_regime_changes(self, micro_df: pd.DataFrame,
                             volatility_threshold: float = 2.0) -> pd.DataFrame:
        """
        Detect market regime changes (low vol -> high vol, etc.)

        Args:
            micro_df: DataFrame with microstructure indicators
            volatility_threshold: Z-score threshold for regime change

        Returns:
            DataFrame with regime change events
        """
        logger.info("Detecting market regime changes...")

        if micro_df.empty or 'volatility_1m' not in micro_df.columns:
            return pd.DataFrame()

        df = micro_df.copy()

        # Calculate volatility Z-score
        vol_mean = df['volatility_1m'].rolling(300, min_periods=30).mean()
        vol_std = df['volatility_1m'].rolling(300, min_periods=30).std()
        df['vol_zscore'] = (df['volatility_1m'] - vol_mean) / (vol_std + 1e-9)

        # Detect regime changes
        df['regime'] = 'normal'
        df.loc[df['vol_zscore'] > volatility_threshold, 'regime'] = 'high_volatility'
        df.loc[df['vol_zscore'] < -volatility_threshold, 'regime'] = 'low_volatility'

        # Detect transitions
        df['regime_change'] = (df['regime'] != df['regime'].shift(1))

        regime_changes = df[df['regime_change'] == True][
            ['time', 'regime', 'vol_zscore', 'volatility_1m', 'mid_price']
        ].copy()

        logger.info(f"Detected {len(regime_changes)} regime changes")
        return regime_changes

    def calculate_price_impact(self, events_df: pd.DataFrame, price_df: pd.DataFrame,
                              time_window: int = 5) -> pd.DataFrame:
        """
        Estimate price impact of large orders

        Args:
            events_df: DataFrame with whale events
            price_df: DataFrame with price data
            time_window: Seconds to measure impact

        Returns:
            DataFrame with price impact analysis
        """
        logger.info("Calculating price impact...")

        if events_df.empty or price_df.empty:
            return pd.DataFrame()

        # Focus on large market orders
        large_trades = events_df[
            (events_df['event_type'].isin(['market_buy', 'market_sell'])) &
            (events_df['usd_value'] > events_df['usd_value'].quantile(0.75))
        ].copy()

        if large_trades.empty:
            return pd.DataFrame()

        price_df = price_df.set_index('time')
        impacts = []

        for idx, trade in large_trades.iterrows():
            trade_time = trade['time']
            trade_price = trade['price']

            # Get price before and after
            price_before = price_df[price_df.index <= trade_time]['mid_price'].iloc[-1] if len(price_df[price_df.index <= trade_time]) > 0 else None
            price_after = price_df[price_df.index >= trade_time + pd.Timedelta(seconds=time_window)]['mid_price'].iloc[0] if len(price_df[price_df.index >= trade_time + pd.Timedelta(seconds=time_window)]) > 0 else None

            if price_before and price_after:
                price_change = price_after - price_before
                price_change_pct = (price_change / price_before) * 100

                impacts.append({
                    'time': trade_time,
                    'event_type': trade['event_type'],
                    'trade_price': trade_price,
                    'trade_volume': trade['volume'],
                    'trade_usd_value': trade['usd_value'],
                    'price_before': price_before,
                    'price_after': price_after,
                    'price_impact': price_change,
                    'price_impact_pct': price_change_pct,
                    'expected_direction': 1 if trade['event_type'] == 'market_buy' else -1,
                    'impact_match': np.sign(price_change) == (1 if trade['event_type'] == 'market_buy' else -1)
                })

        impact_df = pd.DataFrame(impacts)

        if not impact_df.empty:
            logger.info(f"Calculated impact for {len(impact_df)} large trades")
            logger.info(f"Impact alignment rate: {impact_df['impact_match'].mean()*100:.1f}%")

        return impact_df
