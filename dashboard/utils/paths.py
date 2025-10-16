"""
Path Utilities
Handles path resolution for different environments (local dev vs Docker)
"""

import os
from pathlib import Path


def is_docker_env() -> bool:
    """
    Check if running in Docker environment

    Returns:
        bool: True if running in Docker, False otherwise
    """
    return bool(os.getenv('DOCKER_ENV'))


def get_base_dir() -> Path:
    """
    Get the base directory path

    In Docker: /app
    In local dev: parent of dashboard directory

    Returns:
        Path: Base directory path
    """
    if is_docker_env():
        return Path('/app')
    else:
        # Get parent directory of dashboard
        return Path(__file__).parent.parent.parent


def get_data_dir() -> Path:
    """
    Get the data directory path

    Returns:
        Path: Data directory path
    """
    return get_base_dir() / 'data'


def get_live_dir() -> Path:
    """
    Get the live scripts directory path

    Returns:
        Path: Live directory path
    """
    return get_base_dir() / 'live'


# Module-level constants for convenience
BASE_DIR = get_base_dir()
DATA_DIR = get_data_dir()
LIVE_DIR = get_live_dir()
