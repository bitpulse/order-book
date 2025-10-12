"""
Data models for analysis results

Defines common data structures used across all analysis modules.
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict, Optional


@dataclass
class TradingSignal:
    """Trading signal with confidence and reasoning"""
    timestamp: datetime
    signal_type: str  # 'BUY', 'SELL', 'NEUTRAL'
    confidence: float  # 0.0 to 1.0
    price: float
    reasons: List[str]
    indicators: Dict[str, float]
    risk_reward_ratio: Optional[float] = None
    suggested_entry: Optional[float] = None
    suggested_stop: Optional[float] = None
    suggested_target: Optional[float] = None

    def to_dict(self):
        return asdict(self)


@dataclass
class PatternDetection:
    """Detected pattern in order book"""
    pattern_type: str
    timestamp: datetime
    price_level: float
    confidence: float
    metrics: Dict[str, float]
    description: str

    def to_dict(self):
        return asdict(self)
