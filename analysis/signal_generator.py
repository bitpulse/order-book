"""
Trading Signal Generator Module

Generates trading signals based on multiple indicators:
- OFI signals
- Pattern confirmations
- Liquidity analysis
- Microstructure indicators

Multi-indicator scoring system with confidence levels.
"""

import pandas as pd
import numpy as np
from datetime import timedelta
from typing import List
from loguru import logger

try:
    from .data_models import TradingSignal, PatternDetection
except ImportError:
    from data_models import TradingSignal, PatternDetection


class SignalGenerator:
    """Generate trading signals from multiple indicators"""

    def __init__(self,
                 ofi_weight: float = 0.4,
                 depth_weight: float = 0.2,
                 spread_weight: float = 0.15,
                 pattern_weight: float = 0.15,
                 volatility_weight: float = 0.1):
        """
        Initialize signal generator with indicator weights

        Args:
            ofi_weight: Weight for OFI indicator (0-1)
            depth_weight: Weight for depth imbalance
            spread_weight: Weight for spread dynamics
            pattern_weight: Weight for pattern confirmations
            volatility_weight: Weight for volatility adjustment
        """
        total_weight = ofi_weight + depth_weight + spread_weight + pattern_weight + volatility_weight
        self.ofi_weight = ofi_weight / total_weight
        self.depth_weight = depth_weight / total_weight
        self.spread_weight = spread_weight / total_weight
        self.pattern_weight = pattern_weight / total_weight
        self.volatility_weight = volatility_weight / total_weight

    def generate(self, ofi_df: pd.DataFrame,
                 micro_df: pd.DataFrame,
                 patterns: List[PatternDetection],
                 liquidity_clusters: dict) -> List[TradingSignal]:
        """
        Generate trading signals

        Args:
            ofi_df: DataFrame with OFI metrics
            micro_df: DataFrame with microstructure indicators
            patterns: List of detected patterns
            liquidity_clusters: Dict with liquidity clustering results

        Returns:
            List of trading signals
        """
        logger.info("Generating trading signals...")

        if ofi_df.empty or micro_df.empty:
            return []

        signals = []

        # Merge OFI with microstructure
        ofi_df = ofi_df.set_index('time')
        micro_df = micro_df.set_index('time')

        combined = pd.merge_asof(
            ofi_df.sort_index(),
            micro_df.sort_index(),
            left_index=True,
            right_index=True,
            direction='nearest'
        ).dropna()

        if combined.empty:
            return []

        # Generate signals for each time point
        for idx, row in combined.iterrows():
            score = 0  # -100 to +100
            reasons = []
            indicators = {}

            # === 1. OFI SIGNAL (40% weight) ===
            if 'ofi_zscore' in row and pd.notna(row['ofi_zscore']):
                ofi_z = row['ofi_zscore']
                indicators['ofi_zscore'] = ofi_z

                ofi_score = np.clip(ofi_z * 20, -40, 40)  # Scale to ±40
                score += ofi_score * (self.ofi_weight / 0.4)

                if ofi_z > 2.0:
                    reasons.append(f"Strong buy pressure (OFI: {ofi_z:.1f}σ)")
                elif ofi_z > 1.0:
                    reasons.append(f"Moderate buy pressure (OFI: {ofi_z:.1f}σ)")
                elif ofi_z < -2.0:
                    reasons.append(f"Strong sell pressure (OFI: {ofi_z:.1f}σ)")
                elif ofi_z < -1.0:
                    reasons.append(f"Moderate sell pressure (OFI: {ofi_z:.1f}σ)")

            # === 2. DEPTH IMBALANCE (20% weight) ===
            if 'depth_imbalance' in row and pd.notna(row['depth_imbalance']):
                depth_imb = row['depth_imbalance']
                indicators['depth_imbalance'] = depth_imb

                depth_score = depth_imb * 20  # Scale to ±20
                score += depth_score * (self.depth_weight / 0.2)

                if depth_imb > 0.3:
                    reasons.append(f"Bid depth dominance ({depth_imb:.2f})")
                elif depth_imb < -0.3:
                    reasons.append(f"Ask depth dominance ({depth_imb:.2f})")

            # === 3. SPREAD DYNAMICS (15% weight) ===
            if 'spread_bps' in row and 'spread_ma' in row:
                if pd.notna(row['spread_bps']) and pd.notna(row['spread_ma']):
                    spread_ratio = row['spread_bps'] / row['spread_ma'] if row['spread_ma'] > 0 else 1
                    indicators['spread_ratio'] = spread_ratio

                    # Tight spread = bullish (more confident), wide spread = bearish (less confident)
                    if spread_ratio < 0.7:
                        spread_score = 15
                        reasons.append("Tight spread (high liquidity)")
                    elif spread_ratio > 1.5:
                        spread_score = -15
                        reasons.append("Wide spread (low liquidity)")
                    else:
                        spread_score = 0

                    score += spread_score * (self.spread_weight / 0.15)

            # === 4. PATTERN CONFIRMATIONS (15% weight) ===
            pattern_window = timedelta(seconds=30)
            recent_patterns = [p for p in patterns if abs((p.timestamp - idx).total_seconds()) <= 30]

            pattern_score = 0
            for pattern in recent_patterns:
                if pattern.pattern_type == 'iceberg_order':
                    side = pattern.metrics.get('side', '')
                    if side == 'bid' and score > 0:
                        pattern_score += 10
                        reasons.append(f"Iceberg support at ${pattern.price_level:.2f}")
                    elif side == 'ask' and score < 0:
                        pattern_score += 10
                        reasons.append(f"Iceberg resistance at ${pattern.price_level:.2f}")

                elif pattern.pattern_type == 'potential_spoof':
                    # Spoofing is bearish signal (manipulation)
                    pattern_score -= 5
                    reasons.append(f"Spoofing detected (caution)")

            score += pattern_score * (self.pattern_weight / 0.15)

            # === 5. VOLATILITY ADJUSTMENT (10% weight) ===
            if 'volatility_1m' in row and pd.notna(row['volatility_1m']):
                vol = row['volatility_1m']
                indicators['volatility_1m'] = vol

                # High volatility = reduce confidence
                if vol > 0.05:  # High volatility threshold
                    vol_factor = 0.7  # Reduce score by 30%
                    score = score * vol_factor
                    reasons.append(f"High volatility ({vol:.3f}) - reduced confidence")
                elif vol < 0.01:  # Low volatility
                    vol_factor = 1.1  # Increase confidence slightly
                    score = score * vol_factor

            # === GENERATE SIGNAL IF SIGNIFICANT ===
            if abs(score) >= 20:  # Threshold for signal generation
                if score > 0:
                    signal_type = 'BUY'
                elif score < 0:
                    signal_type = 'SELL'
                else:
                    signal_type = 'NEUTRAL'

                confidence = min(abs(score) / 100.0, 0.95)
                price = row['mid_price']

                # Calculate suggested levels
                spread = row.get('spread', price * 0.0001)
                if signal_type == 'BUY':
                    suggested_entry = price - spread
                    suggested_stop = price - (spread * 3)
                    suggested_target = price + (spread * 5)
                    risk_reward = 5.0 / 3.0
                elif signal_type == 'SELL':
                    suggested_entry = price + spread
                    suggested_stop = price + (spread * 3)
                    suggested_target = price - (spread * 5)
                    risk_reward = 5.0 / 3.0
                else:
                    suggested_entry = None
                    suggested_stop = None
                    suggested_target = None
                    risk_reward = None

                signals.append(TradingSignal(
                    timestamp=idx,
                    signal_type=signal_type,
                    confidence=confidence,
                    price=price,
                    reasons=reasons[:5],  # Top 5 reasons
                    indicators=indicators,
                    risk_reward_ratio=risk_reward,
                    suggested_entry=suggested_entry,
                    suggested_stop=suggested_stop,
                    suggested_target=suggested_target
                ))

        # Filter to significant signals only
        significant_signals = [s for s in signals if s.confidence >= 0.5]

        # Remove duplicate signals too close in time
        filtered_signals = self._filter_duplicate_signals(significant_signals, min_gap_seconds=30)

        logger.info(f"Generated {len(filtered_signals)} significant trading signals")
        return filtered_signals

    def _filter_duplicate_signals(self, signals: List[TradingSignal],
                                  min_gap_seconds: int = 30) -> List[TradingSignal]:
        """
        Filter out duplicate signals that are too close in time

        Args:
            signals: List of signals
            min_gap_seconds: Minimum gap between signals

        Returns:
            Filtered list of signals
        """
        if not signals:
            return []

        # Sort by confidence (keep highest confidence)
        signals = sorted(signals, key=lambda x: x.confidence, reverse=True)

        filtered = []
        for signal in signals:
            # Check if too close to any existing signal
            too_close = False
            for existing in filtered:
                time_diff = abs((signal.timestamp - existing.timestamp).total_seconds())
                if time_diff < min_gap_seconds:
                    too_close = True
                    break

            if not too_close:
                filtered.append(signal)

        # Sort by time
        filtered = sorted(filtered, key=lambda x: x.timestamp)

        return filtered

    def backtest_signals(self, signals: List[TradingSignal],
                        price_df: pd.DataFrame,
                        holding_period: int = 60) -> dict:
        """
        Simple backtest of generated signals

        Args:
            signals: List of trading signals
            price_df: DataFrame with price data
            holding_period: Seconds to hold position

        Returns:
            Dict with backtest results
        """
        logger.info(f"Backtesting {len(signals)} signals...")

        if not signals or price_df.empty:
            return {}

        price_df = price_df.set_index('time')
        results = []

        for signal in signals:
            # Get entry price
            entry_time = signal.timestamp
            entry_price = signal.price

            # Get exit price
            exit_time = entry_time + timedelta(seconds=holding_period)
            exit_prices = price_df[price_df.index >= exit_time]['mid_price']

            if len(exit_prices) == 0:
                continue

            exit_price = exit_prices.iloc[0]

            # Calculate return
            if signal.signal_type == 'BUY':
                pnl = exit_price - entry_price
                pnl_pct = (pnl / entry_price) * 100
            elif signal.signal_type == 'SELL':
                pnl = entry_price - exit_price
                pnl_pct = (pnl / entry_price) * 100
            else:
                continue

            results.append({
                'signal_type': signal.signal_type,
                'confidence': signal.confidence,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'win': pnl > 0
            })

        if not results:
            return {}

        df = pd.DataFrame(results)

        # Calculate metrics
        total_trades = len(df)
        wins = df['win'].sum()
        losses = total_trades - wins
        win_rate = wins / total_trades if total_trades > 0 else 0

        avg_pnl = df['pnl_pct'].mean()
        avg_win = df[df['win']]['pnl_pct'].mean() if wins > 0 else 0
        avg_loss = df[~df['win']]['pnl_pct'].mean() if losses > 0 else 0

        sharpe = (df['pnl_pct'].mean() / df['pnl_pct'].std()) if df['pnl_pct'].std() > 0 else 0

        return {
            'total_trades': int(total_trades),
            'wins': int(wins),
            'losses': int(losses),
            'win_rate': float(win_rate),
            'avg_pnl_pct': float(avg_pnl),
            'avg_win_pct': float(avg_win),
            'avg_loss_pct': float(avg_loss),
            'sharpe_ratio': float(sharpe),
            'total_pnl_pct': float(df['pnl_pct'].sum()),
            'max_win_pct': float(df['pnl_pct'].max()),
            'max_loss_pct': float(df['pnl_pct'].min())
        }
