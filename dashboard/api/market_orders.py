"""
Market Orders Blueprint
Handles market orders analysis endpoints
"""

from flask import Blueprint, render_template, jsonify
from services import MongoDBService

# Create blueprint
market_orders_bp = Blueprint('market_orders', __name__)

# Initialize services
mongodb_service = MongoDBService()


@market_orders_bp.route('/top-market-orders')
def top_market_orders():
    """Serve the top market orders analysis page"""
    return render_template('top_market_orders.html')


@market_orders_bp.route('/market-orders-intervals')
def market_orders_intervals():
    """Serve the market orders intervals analysis page"""
    return render_template('market_orders_intervals.html')


@market_orders_bp.route('/api/top-market-orders-files')
def list_top_market_orders_files():
    """List all top market orders analyses from MongoDB"""
    analyses = mongodb_service.get_analyses('top_market_orders', limit=100)
    return jsonify(analyses)


@market_orders_bp.route('/api/market-orders-intervals-files')
def list_market_orders_intervals_files():
    """List all market orders intervals analyses from MongoDB"""
    analyses = mongodb_service.get_analyses('market_orders_intervals', limit=100)
    return jsonify(analyses)


@market_orders_bp.route('/api/top-market-orders-data/<analysis_id>')
def get_top_market_orders_data(analysis_id):
    """Get specific top market orders analysis by ID"""
    data = mongodb_service.get_analysis_by_id('top_market_orders', analysis_id)

    if data:
        return jsonify(data)
    else:
        return jsonify({'error': 'Analysis not found'}), 404


@market_orders_bp.route('/api/market-orders-intervals-data/<analysis_id>')
def get_market_orders_intervals_data(analysis_id):
    """Get specific market orders intervals analysis by ID"""
    data = mongodb_service.get_analysis_by_id('market_orders_intervals', analysis_id)

    if data:
        return jsonify(data)
    else:
        return jsonify({'error': 'Analysis not found'}), 404
