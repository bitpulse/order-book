from pydantic_settings import BaseSettings
from pydantic import Field, validator
from typing import List, Dict, Optional
from pathlib import Path
import os


class Settings(BaseSettings):
    # InfluxDB Configuration
    influxdb_url: str = Field(default="http://localhost:8086")
    influxdb_token: str = Field(default="")
    influxdb_org: str = Field(default="bitpulse")
    influxdb_bucket: str = Field(default="orderbook")

    # MongoDB Configuration
    mongodb_url: str = Field(default="mongodb://localhost:27017")
    mongodb_database: str = Field(default="orderbook_analytics")

    # MEXC Configuration
    mexc_websocket_url: str = Field(default="wss://contract.mexc.com/edge")

    # Trading Pairs - stored as string in env, parsed to list
    trading_pairs: Optional[str] = Field(default="BTC_USDT,ETH_USDT")

    # Whale Detection Thresholds
    whale_threshold_btc_large: float = Field(default=100000)
    whale_threshold_btc_huge: float = Field(default=500000)
    whale_threshold_btc_mega: float = Field(default=1000000)

    whale_threshold_eth_large: float = Field(default=50000)
    whale_threshold_eth_huge: float = Field(default=250000)
    whale_threshold_eth_mega: float = Field(default=500000)

    whale_threshold_default_large: float = Field(default=50000)
    whale_threshold_default_huge: float = Field(default=250000)
    whale_threshold_default_mega: float = Field(default=500000)

    # Order Book Configuration
    order_book_depth: int = Field(default=20)

    # Logging
    log_level: str = Field(default="INFO")
    log_file: str = Field(default="logs/orderbook_collector.log")

    # Telegram Configuration
    telegram_bot_token: Optional[str] = Field(default=None)
    telegram_chat_id: Optional[str] = Field(default=None)

    # Performance
    batch_size: int = Field(default=100)
    batch_timeout: float = Field(default=1.0)

    def get_trading_pairs_list(self) -> List[str]:
        """Get trading pairs as a list"""
        if self.trading_pairs:
            return [pair.strip() for pair in self.trading_pairs.split(",") if pair.strip()]
        return ["BTC_USDT", "ETH_USDT"]

    def get_whale_thresholds(self, symbol: str) -> Dict[str, float]:
        """Get whale thresholds for a specific trading pair"""
        if "BTC" in symbol:
            return {
                "large": self.whale_threshold_btc_large,
                "huge": self.whale_threshold_btc_huge,
                "mega": self.whale_threshold_btc_mega,
            }
        elif "ETH" in symbol:
            return {
                "large": self.whale_threshold_eth_large,
                "huge": self.whale_threshold_eth_huge,
                "mega": self.whale_threshold_eth_mega,
            }
        else:
            return {
                "large": self.whale_threshold_default_large,
                "huge": self.whale_threshold_default_huge,
                "mega": self.whale_threshold_default_mega,
            }

    def ensure_log_directory(self):
        """Ensure log directory exists"""
        log_path = Path(self.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


def get_settings() -> Settings:
    """Get application settings"""
    settings = Settings()
    settings.ensure_log_directory()
    return settings