# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
This repository collects order book data from MEXC futures and saves it to InfluxDB.

## Project Structure
- `src/` - Main source code directory for the order book data collection system
- `.env` - Environment variables (excluded from git)

## Technology Stack
- Python - Primary programming language
- InfluxDB - Time series database for storing order book data
- MEXC Futures API - Source of order book data

## Development Setup
Since this is a new project without established dependencies yet, when implementing features:
1. Create a `requirements.txt` file for Python dependencies as needed
2. Consider using virtual environments (venv) for dependency isolation
3. Add configuration for MEXC API credentials and InfluxDB connection in `.env`

## Common Development Tasks
When implementing the order book collector:
- Use async programming (asyncio) for efficient WebSocket connections
- Implement proper error handling for API disconnections
- Consider data batching for efficient InfluxDB writes
- Add logging for monitoring data collection status