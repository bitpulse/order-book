#!/bin/bash

# Dashboard Deployment Script
# Usage: ./deploy.sh [up|down|restart|logs]

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Default action
ACTION="${1:-up}"

# Use standard docker-compose file
COMPOSE_FILE="docker-compose.yml"
echo -e "${GREEN}Starting dashboard with docker-compose.yml${NC}"

# Execute action
case "$ACTION" in
    up)
        echo -e "${GREEN}Starting dashboard...${NC}"
        docker-compose -f "$COMPOSE_FILE" up -d
        echo -e "${GREEN}Dashboard started!${NC}"
        echo -e "Access at: ${YELLOW}http://localhost:5000${NC}"
        ;;
    down)
        echo -e "${YELLOW}Stopping dashboard...${NC}"
        docker-compose -f "$COMPOSE_FILE" down
        echo -e "${GREEN}Dashboard stopped!${NC}"
        ;;
    restart)
        echo -e "${YELLOW}Restarting dashboard...${NC}"
        docker-compose -f "$COMPOSE_FILE" restart
        echo -e "${GREEN}Dashboard restarted!${NC}"
        ;;
    rebuild)
        echo -e "${YELLOW}Rebuilding and restarting dashboard...${NC}"
        docker-compose -f "$COMPOSE_FILE" down
        docker-compose -f "$COMPOSE_FILE" up -d --build
        echo -e "${GREEN}Dashboard rebuilt and started!${NC}"
        ;;
    logs)
        docker-compose -f "$COMPOSE_FILE" logs -f
        ;;
    status)
        echo -e "${GREEN}Dashboard status:${NC}"
        docker-compose -f "$COMPOSE_FILE" ps
        echo ""
        echo -e "${GREEN}Checking health...${NC}"
        curl -s http://localhost:5000/api/stats | python3 -m json.tool || echo -e "${RED}Dashboard not responding${NC}"
        ;;
    *)
        echo -e "${RED}Usage: $0 [up|down|restart|rebuild|logs|status]${NC}"
        echo ""
        echo "Examples:"
        echo "  $0 up        - Start dashboard"
        echo "  $0 rebuild   - Rebuild and restart dashboard"
        echo "  $0 logs      - View logs"
        echo "  $0 status    - Check status"
        exit 1
        ;;
esac
