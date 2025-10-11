"""
MongoDB Storage Module
Handles storage and retrieval of analysis results
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from pymongo import MongoClient, DESCENDING, ASCENDING
from pymongo.collection import Collection
from pymongo.errors import PyMongoError
from loguru import logger
import os


class MongoDBStorage:
    """Handles storage of analysis results to MongoDB"""

    def __init__(self, mongodb_url: str, database_name: str):
        """
        Initialize MongoDB storage

        Args:
            mongodb_url: MongoDB connection URL
            database_name: Database name
        """
        self.mongodb_url = mongodb_url
        self.database_name = database_name

        try:
            self.client = MongoClient(mongodb_url, serverSelectionTimeoutMS=5000)
            # Test connection
            self.client.server_info()
            self.db = self.client[database_name]

            # Initialize collections with indexes
            self._setup_collections()

            logger.info(f"Connected to MongoDB at {mongodb_url}, database: {database_name}")
        except PyMongoError as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    def _setup_collections(self):
        """Setup collections and create indexes"""
        collections = [
            'price_changes',
            'top_market_orders',
            'market_orders_intervals',
            'whale_activity',
            'whale_monitor'
        ]

        for collection_name in collections:
            collection = self.db[collection_name]

            # Create indexes for efficient queries
            collection.create_index([("symbol", ASCENDING)])
            collection.create_index([("created_at", DESCENDING)])
            collection.create_index([("analysis_timestamp", DESCENDING)])
            collection.create_index([("symbol", ASCENDING), ("created_at", DESCENDING)])

        logger.info(f"MongoDB collections and indexes initialized")

    def save_analysis(self,
                     collection_name: str,
                     analysis_data: Dict[str, Any],
                     metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Save analysis results to MongoDB

        Args:
            collection_name: Name of the collection to save to
            analysis_data: The analysis data to save
            metadata: Optional metadata (parameters used, etc.)

        Returns:
            str: ID of the inserted document
        """
        try:
            collection = self.db[collection_name]

            # Prepare document
            document = {
                'created_at': datetime.utcnow(),
                'data': analysis_data,
                'metadata': metadata or {}
            }

            # Extract common fields for easier querying
            if 'analysis' in analysis_data:
                document['symbol'] = analysis_data['analysis'].get('symbol')
                document['lookback'] = analysis_data['analysis'].get('lookback')
                document['analysis_timestamp'] = analysis_data['analysis'].get('timestamp')

            result = collection.insert_one(document)

            logger.info(f"Saved analysis to {collection_name}, ID: {result.inserted_id}")
            return str(result.inserted_id)

        except PyMongoError as e:
            logger.error(f"Failed to save analysis to MongoDB: {e}")
            raise

    def get_analyses(self,
                    collection_name: str,
                    symbol: Optional[str] = None,
                    limit: int = 50,
                    skip: int = 0,
                    sort_by: str = 'created_at',
                    sort_order: int = DESCENDING) -> List[Dict[str, Any]]:
        """
        Get analyses from MongoDB

        Args:
            collection_name: Name of the collection
            symbol: Optional symbol filter
            limit: Maximum number of results
            skip: Number of results to skip (for pagination)
            sort_by: Field to sort by
            sort_order: Sort order (DESCENDING or ASCENDING)

        Returns:
            List of analysis documents
        """
        try:
            collection = self.db[collection_name]

            # Build query
            query = {}
            if symbol:
                query['symbol'] = symbol

            # Execute query
            cursor = collection.find(query).sort(sort_by, sort_order).skip(skip).limit(limit)

            results = []
            for doc in cursor:
                # Convert ObjectId to string
                doc['_id'] = str(doc['_id'])
                results.append(doc)

            return results

        except PyMongoError as e:
            logger.error(f"Failed to get analyses from MongoDB: {e}")
            return []

    def get_analysis_by_id(self, collection_name: str, analysis_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific analysis by ID

        Args:
            collection_name: Name of the collection
            analysis_id: ID of the analysis

        Returns:
            Analysis document or None
        """
        try:
            from bson import ObjectId
            collection = self.db[collection_name]

            doc = collection.find_one({'_id': ObjectId(analysis_id)})

            if doc:
                doc['_id'] = str(doc['_id'])
                return doc

            return None

        except Exception as e:
            logger.error(f"Failed to get analysis by ID: {e}")
            return None

    def get_latest_analysis(self, collection_name: str, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent analysis for a symbol

        Args:
            collection_name: Name of the collection
            symbol: Trading symbol

        Returns:
            Latest analysis document or None
        """
        try:
            collection = self.db[collection_name]

            doc = collection.find_one(
                {'symbol': symbol},
                sort=[('created_at', DESCENDING)]
            )

            if doc:
                doc['_id'] = str(doc['_id'])
                return doc

            return None

        except PyMongoError as e:
            logger.error(f"Failed to get latest analysis: {e}")
            return None

    def get_analyses_count(self, collection_name: str, symbol: Optional[str] = None) -> int:
        """
        Get count of analyses

        Args:
            collection_name: Name of the collection
            symbol: Optional symbol filter

        Returns:
            Count of documents
        """
        try:
            collection = self.db[collection_name]

            query = {}
            if symbol:
                query['symbol'] = symbol

            return collection.count_documents(query)

        except PyMongoError as e:
            logger.error(f"Failed to count analyses: {e}")
            return 0

    def delete_analysis(self, collection_name: str, analysis_id: str) -> bool:
        """
        Delete an analysis by ID

        Args:
            collection_name: Name of the collection
            analysis_id: ID of the analysis to delete

        Returns:
            True if deleted, False otherwise
        """
        try:
            from bson import ObjectId
            collection = self.db[collection_name]

            result = collection.delete_one({'_id': ObjectId(analysis_id)})

            if result.deleted_count > 0:
                logger.info(f"Deleted analysis {analysis_id} from {collection_name}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to delete analysis: {e}")
            return False

    def close(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")


def get_mongodb_storage(mongodb_url: Optional[str] = None,
                       database_name: Optional[str] = None) -> Optional[MongoDBStorage]:
    """
    Get MongoDB storage instance (helper function)

    Args:
        mongodb_url: Optional MongoDB URL (reads from env if not provided)
        database_name: Optional database name (reads from env if not provided)

    Returns:
        MongoDBStorage instance or None if connection fails
    """
    try:
        if not mongodb_url:
            mongodb_url = os.getenv('MONGODB_URL', 'mongodb://localhost:27017')

        if not database_name:
            database_name = os.getenv('MONGODB_DATABASE', 'orderbook_analytics')

        return MongoDBStorage(mongodb_url, database_name)

    except Exception as e:
        logger.warning(f"Could not connect to MongoDB: {e}")
        return None
