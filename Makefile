.PHONY: help install test run docker-build docker-up docker-down logs clean

help:
	@echo "Available commands:"
	@echo "  make install       - Install Python dependencies"
	@echo "  make test         - Test connections to MEXC and InfluxDB"
	@echo "  make run          - Run the order book collector"
	@echo "  make docker-build - Build Docker image"
	@echo "  make docker-up    - Start services with Docker Compose"
	@echo "  make docker-down  - Stop Docker services"
	@echo "  make logs         - View collector logs"
	@echo "  make clean        - Clean up cache files"

install:
	pip install -r requirements.txt

test:
	python test_connection.py

run:
	python run.py

docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

logs:
	docker-compose logs -f orderbook-collector

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
	rm -rf .mypy_cache