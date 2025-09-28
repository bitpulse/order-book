"""
Order Book API Routes
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional
from datetime import datetime

from ..models.responses import (
    OrderBookResponse,
    OrderBookStats,
    SpreadHistory,
    MarketDepth,
    ImbalanceHistory,
    ErrorResponse
)
from ..services.influxdb_service import InfluxDBService

router = APIRouter(prefix="/orderbook", tags=["Order Book"])


def get_db_service():
    """Dependency to get InfluxDB service"""
    return InfluxDBService()


@router.get("/{symbol}", response_model=OrderBookResponse)
async def get_orderbook(
    symbol: str,
    db: InfluxDBService = Depends(get_db_service)
):
    """
    Get current order book for a symbol

    Returns full 20-level order book with bids and asks
    """
    try:
        orderbook = await db.get_current_orderbook(symbol)

        if not orderbook['bids'] and not orderbook['asks']:
            raise HTTPException(status_code=404, detail=f"No order book data found for {symbol}")

        # Add best bid/ask to response
        if orderbook['bids'] and len(orderbook['bids']) > 0:
            orderbook['best_bid'] = orderbook['bids'][0].get('price')
        if orderbook['asks'] and len(orderbook['asks']) > 0:
            orderbook['best_ask'] = orderbook['asks'][0].get('price')

        if orderbook.get('best_bid') and orderbook.get('best_ask'):
            orderbook['spread'] = orderbook['best_ask'] - orderbook['best_bid']
            orderbook['spread_percentage'] = (orderbook['spread'] / orderbook['best_ask']) * 100

        return orderbook
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/stats", response_model=OrderBookStats)
async def get_stats(
    symbol: str,
    db: InfluxDBService = Depends(get_db_service)
):
    """
    Get current order book statistics

    Includes spread, imbalance, volumes, and other metrics
    """
    try:
        stats = await db.get_current_stats(symbol)

        if not stats or 'timestamp' not in stats:
            raise HTTPException(status_code=404, detail=f"No statistics found for {symbol}")

        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/spread/history", response_model=List[SpreadHistory])
async def get_spread_history(
    symbol: str,
    start: str = Query("-1h", description="Time range (e.g., -1h, -24h, -7d)"),
    interval: str = Query("1m", description="Aggregation interval (e.g., 1m, 5m, 1h)"),
    db: InfluxDBService = Depends(get_db_service)
):
    """
    Get historical spread data

    Returns spread and spread percentage over time
    """
    try:
        history = await db.get_spread_history(symbol, start, interval)

        if not history:
            raise HTTPException(status_code=404, detail=f"No spread history found for {symbol}")

        return history
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/depth", response_model=List[MarketDepth])
async def get_market_depth(
    symbol: str,
    percentage: Optional[str] = Query(None, description="Specific depth percentage (e.g., 0.1%, 1%, 5%)"),
    db: InfluxDBService = Depends(get_db_service)
):
    """
    Get market depth at various percentages from mid-price

    Shows volume distribution around the mid-price
    """
    try:
        depth = await db.get_market_depth(symbol, percentage)

        if not depth:
            raise HTTPException(status_code=404, detail=f"No market depth data found for {symbol}")

        return depth
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/imbalance/history", response_model=List[ImbalanceHistory])
async def get_imbalance_history(
    symbol: str,
    start: str = Query("-1h", description="Time range"),
    interval: str = Query("1m", description="Aggregation interval"),
    db: InfluxDBService = Depends(get_db_service)
):
    """
    Get historical order book imbalance

    Imbalance ranges from -1 (all sells) to +1 (all buys)
    """
    try:
        history = await db.get_imbalance_history(symbol, start, interval)

        if not history:
            raise HTTPException(status_code=404, detail=f"No imbalance history found for {symbol}")

        return history
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/best", response_model=dict)
async def get_best_prices(
    symbol: str,
    db: InfluxDBService = Depends(get_db_service)
):
    """
    Get just the best bid and ask prices

    Lightweight endpoint for current top of book
    """
    try:
        stats = await db.get_current_stats(symbol)

        if not stats:
            raise HTTPException(status_code=404, detail=f"No data found for {symbol}")

        return {
            "symbol": symbol,
            "timestamp": stats.get('timestamp'),
            "best_bid": stats.get('best_bid'),
            "best_ask": stats.get('best_ask'),
            "mid_price": stats.get('mid_price'),
            "spread": stats.get('spread'),
            "spread_percentage": stats.get('spread_percentage')
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))