"""
MongoDB Service Layer
Handles all MongoDB operations for the dashboard
"""

import sys
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path


class MongoDBService:
    """Service for MongoDB operations"""

    def __init__(self):
        """Initialize MongoDB service"""
        self._setup_python_path()

    def _setup_python_path(self):
        """Setup Python path to import src.mongodb_storage"""
        from utils.paths import BASE_DIR

        parent_dir = str(BASE_DIR)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)

        # Also add src directory for Docker environments
        src_dir = os.path.join(parent_dir, 'src')
        if os.path.exists(src_dir) and src_dir not in sys.path:
            sys.path.insert(0, src_dir)

    def get_analyses(self, collection_name: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get analyses from MongoDB

        Args:
            collection_name: Name of the MongoDB collection
            limit: Maximum number of analyses to return

        Returns:
            List of analysis metadata dictionaries
        """
        analyses = []

        try:
            from src.mongodb_storage import get_mongodb_storage

            mongo = get_mongodb_storage()
            if mongo:
                results = mongo.get_analyses(collection_name, limit=limit)
                for analysis in results:
                    # Handle created_at - could be datetime or string
                    created_at = analysis.get('created_at')
                    if created_at:
                        if isinstance(created_at, datetime):
                            created_at_iso = created_at.isoformat()
                            created_at_ts = created_at.timestamp()
                        else:
                            created_at_iso = created_at
                            try:
                                created_at_ts = datetime.fromisoformat(
                                    created_at.replace('Z', '+00:00')
                                ).timestamp()
                            except:
                                created_at_ts = 0
                    else:
                        created_at_iso = None
                        created_at_ts = 0

                    analyses.append({
                        'id': analysis['_id'],
                        'filename': analysis.get('metadata', {}).get('filename', 'N/A'),
                        'symbol': analysis.get('symbol'),
                        'created_at': created_at_iso,
                        'created_at_ts': created_at_ts,
                        'source': 'mongodb'
                    })
                mongo.close()

                # Sort by creation time (newest first)
                analyses.sort(key=lambda x: x.get('created_at_ts', 0), reverse=True)

        except Exception as e:
            import traceback
            print(f"MongoDB query failed for {collection_name}: {e}")
            print(traceback.format_exc())

        return analyses

    def get_analysis_by_id(self, collection_name: str, analysis_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific analysis from MongoDB by ID

        Args:
            collection_name: Name of the MongoDB collection
            analysis_id: MongoDB document ID

        Returns:
            Analysis data dictionary or None if not found
        """
        try:
            from src.mongodb_storage import get_mongodb_storage

            mongo = get_mongodb_storage()
            if mongo:
                analysis = mongo.get_analysis_by_id(collection_name, analysis_id)
                mongo.close()
                if analysis:
                    return analysis['data']

        except Exception as e:
            import traceback
            print(f"MongoDB query failed: {e}")
            print(traceback.format_exc())

        return None

    def save_analysis(
        self,
        collection_name: str,
        analysis_data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Save analysis to MongoDB

        Args:
            collection_name: Name of the MongoDB collection
            analysis_data: The analysis data to save
            metadata: Optional metadata

        Returns:
            MongoDB document ID or None if save failed
        """
        try:
            from src.mongodb_storage import get_mongodb_storage

            mongo = get_mongodb_storage()
            if mongo:
                analysis_id = mongo.save_analysis(collection_name, analysis_data, metadata)
                mongo.close()
                return analysis_id

        except Exception as e:
            import traceback
            print(f"Failed to save to MongoDB: {e}")
            print(traceback.format_exc())

        return None

    def delete_analysis(self, collection_name: str, analysis_id: str) -> bool:
        """
        Delete an analysis from MongoDB

        Args:
            collection_name: Name of the MongoDB collection
            analysis_id: MongoDB document ID

        Returns:
            True if deleted, False otherwise
        """
        try:
            from src.mongodb_storage import get_mongodb_storage

            mongo = get_mongodb_storage()
            if mongo:
                success = mongo.delete_analysis(collection_name, analysis_id)
                mongo.close()
                return success

        except Exception as e:
            import traceback
            print(f"Failed to delete from MongoDB: {e}")
            print(traceback.format_exc())

        return False

    def get_latest_analysis(self, collection_name: str, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent analysis for a symbol

        Args:
            collection_name: Name of the MongoDB collection
            symbol: Trading symbol

        Returns:
            Analysis data dictionary or None if not found
        """
        try:
            from src.mongodb_storage import get_mongodb_storage

            mongo = get_mongodb_storage()
            if mongo:
                analysis = mongo.get_latest_analysis(collection_name, symbol)
                mongo.close()
                if analysis:
                    return analysis['data']

        except Exception as e:
            import traceback
            print(f"Failed to get latest analysis: {e}")
            print(traceback.format_exc())

        return None
