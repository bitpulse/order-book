"""
File Service Layer
Handles file-based data operations (legacy support)
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from utils.paths import DATA_DIR


class FileService:
    """Service for file operations"""

    def list_json_files(self, pattern: str = "*.json") -> List[Dict[str, Any]]:
        """
        List JSON files in data directory matching pattern

        Args:
            pattern: Glob pattern to match files

        Returns:
            List of file metadata dictionaries
        """
        files = []

        try:
            if not DATA_DIR.exists():
                return files

            for filepath in DATA_DIR.glob(pattern):
                if filepath.is_file():
                    files.append({
                        'filename': filepath.name,
                        'filepath': str(filepath),
                        'size': filepath.stat().st_size,
                        'modified': filepath.stat().st_mtime,
                        'source': 'file'
                    })

            # Sort by modification time (newest first)
            files.sort(key=lambda x: x['modified'], reverse=True)

        except Exception as e:
            print(f"Error listing files: {e}")

        return files

    def read_json_file(self, filename: str) -> Optional[Dict[str, Any]]:
        """
        Read JSON file from data directory

        Args:
            filename: Name of the file to read

        Returns:
            Parsed JSON data or None if error
        """
        try:
            # Security: validate filename
            if not self.validate_filename(filename):
                print(f"Invalid filename: {filename}")
                return None

            filepath = DATA_DIR / filename

            if not filepath.exists():
                print(f"File not found: {filepath}")
                return None

            with open(filepath, 'r') as f:
                data = json.load(f)

            return data

        except json.JSONDecodeError as e:
            print(f"Invalid JSON file {filename}: {e}")
            return None
        except Exception as e:
            print(f"Error reading file {filename}: {e}")
            return None

    def validate_filename(self, filename: str) -> bool:
        """
        Validate filename for security

        Args:
            filename: Filename to validate

        Returns:
            True if valid, False otherwise
        """
        # Prevent directory traversal
        if '..' in filename or '/' in filename or '\\' in filename:
            return False

        # Only allow JSON files
        if not filename.endswith('.json'):
            return False

        # Check against allowed patterns
        allowed_patterns = [
            'price_changes_',
            'market_orders_',
            'top_market_orders_',
            'whale_activity_',
            'whale_monitor_',
        ]

        if not any(filename.startswith(pattern) for pattern in allowed_patterns):
            return False

        return True

    def get_file_metadata(self, filename: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific file

        Args:
            filename: Name of the file

        Returns:
            Metadata dictionary or None
        """
        try:
            if not self.validate_filename(filename):
                return None

            filepath = DATA_DIR / filename

            if not filepath.exists():
                return None

            stat = filepath.stat()
            return {
                'filename': filepath.name,
                'filepath': str(filepath),
                'size': stat.st_size,
                'modified': stat.st_mtime,
                'created': stat.st_ctime,
                'source': 'file'
            }

        except Exception as e:
            print(f"Error getting file metadata: {e}")
            return None

    def delete_file(self, filename: str) -> bool:
        """
        Delete a file from data directory

        Args:
            filename: Name of the file to delete

        Returns:
            True if deleted, False otherwise
        """
        try:
            if not self.validate_filename(filename):
                print(f"Invalid filename: {filename}")
                return False

            filepath = DATA_DIR / filename

            if not filepath.exists():
                print(f"File not found: {filepath}")
                return False

            filepath.unlink()
            print(f"Deleted file: {filepath}")
            return True

        except Exception as e:
            print(f"Error deleting file {filename}: {e}")
            return False
