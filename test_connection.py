#!/usr/bin/env python3
"""
Test script to verify MEXC WebSocket and InfluxDB connections
"""

import asyncio
import json
import websockets
from influxdb_client import InfluxDBClient
from loguru import logger
import sys
from src.config import get_settings


async def test_mexc_websocket():
    """Test MEXC WebSocket connection"""
    logger.info("Testing MEXC WebSocket connection...")

    try:
        url = "wss://contract.mexc.com/edge"
        async with websockets.connect(url) as ws:
            logger.success(f"✅ Connected to MEXC WebSocket: {url}")

            # Subscribe to BTC_USDT depth
            subscription = {
                "method": "sub.depth",
                "param": {
                    "symbol": "BTC_USDT",
                    "limit": 5
                }
            }

            await ws.send(json.dumps(subscription))
            logger.info("Sent subscription request for BTC_USDT depth")

            # Wait for response
            response = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(response)
            logger.info(f"Received response: {data}")

            # Wait for depth data
            for i in range(3):
                response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(response)

                if data.get("channel") == "push.depth":
                    logger.success("✅ Received depth data successfully!")
                    logger.info(f"Best bid: {data['data']['bids'][0] if data['data'].get('bids') else 'N/A'}")
                    logger.info(f"Best ask: {data['data']['asks'][0] if data['data'].get('asks') else 'N/A'}")
                    break

            return True

    except asyncio.TimeoutError:
        logger.error("❌ Timeout waiting for WebSocket response")
        return False
    except Exception as e:
        logger.error(f"❌ WebSocket test failed: {e}")
        return False


def test_influxdb_connection():
    """Test InfluxDB connection"""
    logger.info("Testing InfluxDB connection...")

    try:
        settings = get_settings()

        # Skip if no token configured
        if not settings.influxdb_token:
            logger.warning("⚠️  No InfluxDB token configured in .env file")
            logger.info("Please set INFLUXDB_TOKEN in your .env file")
            return False

        client = InfluxDBClient(
            url=settings.influxdb_url,
            token=settings.influxdb_token,
            org=settings.influxdb_org
        )

        # Test health
        health = client.health()

        if health.status == "pass":
            logger.success(f"✅ InfluxDB connection successful: {settings.influxdb_url}")
            logger.info(f"Organization: {settings.influxdb_org}")
            logger.info(f"Bucket: {settings.influxdb_bucket}")
            return True
        else:
            logger.error(f"❌ InfluxDB health check failed: {health.message}")
            return False

    except Exception as e:
        logger.error(f"❌ InfluxDB test failed: {e}")
        logger.info("Make sure InfluxDB is running and credentials are correct")
        return False


async def main():
    """Run all tests"""
    logger.remove()
    logger.add(sys.stdout, format="{time:HH:mm:ss} | {level: <8} | {message}", colorize=True)

    logger.info("=" * 60)
    logger.info("MEXC Order Book Collector - Connection Test")
    logger.info("=" * 60)

    # Test MEXC WebSocket
    ws_result = await test_mexc_websocket()

    # Test InfluxDB
    influx_result = test_influxdb_connection()

    # Summary
    logger.info("=" * 60)
    logger.info("Test Results:")
    logger.info(f"  MEXC WebSocket: {'✅ PASSED' if ws_result else '❌ FAILED'}")
    logger.info(f"  InfluxDB:       {'✅ PASSED' if influx_result else '❌ FAILED'}")
    logger.info("=" * 60)

    if ws_result and influx_result:
        logger.success("All tests passed! Ready to run the collector.")
    else:
        logger.warning("Some tests failed. Please check your configuration.")


if __name__ == "__main__":
    asyncio.run(main())