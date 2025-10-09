#!/bin/bash

# run-tracker.sh - Helper script to run individual orderbook tracker containers
# Usage: ./run-tracker.sh SYMBOL [OPTIONS]
# Example: ./run-tracker.sh WIF_USDT --min-usd 20000 --telegram

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if symbol is provided
if [ $# -lt 1 ]; then
    echo -e "${RED}Error: Symbol is required${NC}"
    echo "Usage: ./run-tracker.sh SYMBOL [OPTIONS]"
    echo ""
    echo "Examples:"
    echo "  ./run-tracker.sh BTC_USDT --influx --min-usd 100000"
    echo "  ./run-tracker.sh WIF_USDT --influx --min-usd 20000 --telegram"
    echo "  ./run-tracker.sh ETH_USDT --influx --telegram"
    exit 1
fi

SYMBOL=$1
shift  # Remove first argument (symbol), rest are passed to tracker

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${RED}Error: .env file not found${NC}"
    echo "Please create .env file with required configuration"
    exit 1
fi

# Load environment variables from .env
export $(grep -v '^#' .env | xargs)

# Container name (sanitized symbol name)
CONTAINER_NAME="tracker-${SYMBOL,,}"  # Convert to lowercase

# Image name
IMAGE_NAME="orderbook-tracker"

# Determine network name (docker-compose creates with project prefix)
NETWORK_NAME="order-book_orderbook-network"
if ! docker network ls | grep -q "$NETWORK_NAME"; then
    # Fallback to simple name if compose network doesn't exist
    NETWORK_NAME="orderbook-network"
    if ! docker network ls | grep -q "$NETWORK_NAME"; then
        echo -e "${GREEN}Creating Docker network: $NETWORK_NAME${NC}"
        docker network create $NETWORK_NAME
    fi
fi

# Check if using remote or local InfluxDB
if [[ "$INFLUXDB_URL" == *"localhost"* ]] || [[ "$INFLUXDB_URL" == *"127.0.0.1"* ]] || [[ "$INFLUXDB_URL" == *"influxdb"* ]]; then
    # Local InfluxDB - check if container is running
    if ! docker ps | grep -q orderbook-influxdb; then
        echo -e "${YELLOW}Warning: InfluxDB container (orderbook-influxdb) is not running${NC}"
        echo "Starting InfluxDB with docker-compose..."
        docker-compose up -d influxdb
        echo "Waiting for InfluxDB to be ready..."
        sleep 5
    fi
else
    echo -e "${GREEN}Using remote InfluxDB: $INFLUXDB_URL${NC}"
fi

# Build image if it doesn't exist
if ! docker images | grep -q $IMAGE_NAME; then
    echo -e "${GREEN}Building Docker image...${NC}"
    docker build -t $IMAGE_NAME .
fi

# Stop and remove existing container with same name if it exists
if docker ps -a | grep -q $CONTAINER_NAME; then
    echo -e "${YELLOW}Stopping existing container: $CONTAINER_NAME${NC}"
    docker stop $CONTAINER_NAME || true
    docker rm $CONTAINER_NAME || true
fi

# Run the tracker container
echo -e "${GREEN}Starting tracker for $SYMBOL${NC}"
echo "Container name: $CONTAINER_NAME"
echo "Command: python live/orderbook_tracker.py $SYMBOL $@"
echo ""

docker run -d \
    --name $CONTAINER_NAME \
    --network $NETWORK_NAME \
    -v $(pwd)/logs:/app/logs \
    -e INFLUXDB_URL=$INFLUXDB_URL \
    -e INFLUXDB_TOKEN=$INFLUXDB_TOKEN \
    -e INFLUXDB_ORG=$INFLUXDB_ORG \
    -e INFLUXDB_BUCKET=$INFLUXDB_BUCKET \
    -e TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN \
    -e TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID \
    --restart unless-stopped \
    $IMAGE_NAME \
    python live/orderbook_tracker.py $SYMBOL "$@"

echo -e "${GREEN}✓ Tracker started successfully${NC}"
echo ""
echo "Useful commands:"
echo "  View logs:    docker logs -f $CONTAINER_NAME"
echo "  Stop tracker: docker stop $CONTAINER_NAME"
echo "  Remove:       docker rm $CONTAINER_NAME"
echo "  List all:     docker ps -a | grep tracker"

