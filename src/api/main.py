"""
FastAPI Application for Order Book Data API
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import time
from loguru import logger

from .routes import orderbook, whales
from .models.responses import HealthResponse, ErrorResponse
from .services.influxdb_service import InfluxDBService

# Track application start time
app_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    logger.info("Starting Order Book API...")
    yield
    logger.info("Shutting down Order Book API...")


# Create FastAPI app
app = FastAPI(
    title="Order Book Analytics API",
    description="Real-time order book data and whale tracking API for MEXC futures",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(orderbook.router, prefix="/api/v1")
app.include_router(whales.router, prefix="/api/v1")


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information"""
    return {
        "name": "Order Book Analytics API",
        "version": "1.0.0",
        "status": "running",
        "documentation": "/docs",
        "endpoints": {
            "orderbook": "/api/v1/orderbook/{symbol}",
            "whales": "/api/v1/whales/recent",
            "health": "/health"
        }
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint"""
    try:
        # Test InfluxDB connection
        db_service = InfluxDBService()
        db_connected = False

        try:
            # Simple query to test connection
            test_query = 'from(bucket: "trading_data") |> range(start: -1m) |> limit(n: 1)'
            db_service.query_api.query(test_query, org=db_service.org)
            db_connected = True
        except Exception as e:
            logger.error(f"InfluxDB health check failed: {e}")
        finally:
            db_service.close()

        uptime = time.time() - app_start_time

        return HealthResponse(
            status="healthy" if db_connected else "degraded",
            influxdb_connected=db_connected,
            uptime_seconds=uptime
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Custom 404 handler"""
    return JSONResponse(
        status_code=404,
        content={"error": "Not Found", "detail": "The requested resource was not found"}
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Custom 500 handler"""
    logger.error(f"Internal error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error", "detail": "An unexpected error occurred"}
    )


# WebSocket endpoint placeholder (to be implemented)
@app.get("/api/v1/ws/info", tags=["WebSocket"])
async def websocket_info():
    """Information about WebSocket endpoints"""
    return {
        "endpoints": {
            "orderbook": "ws://localhost:8000/ws/orderbook/{symbol}",
            "whales": "ws://localhost:8000/ws/whales"
        },
        "status": "WebSocket support coming soon",
        "description": "Real-time streaming of order book updates and whale alerts"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)