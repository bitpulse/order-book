"""
API Blueprints Package
Registers all Flask blueprints for the dashboard
"""

def register_blueprints(app):
    """
    Register all API blueprints with the Flask app

    Args:
        app: Flask application instance
    """
    # Import blueprints
    from .price_changes import price_changes_bp
    from .market_orders import market_orders_bp
    from .whale_activity import whale_activity_bp
    from .whale_monitor import whale_monitor_bp
    from .live_data import live_data_bp
    from .historical_chart import historical_chart_bp

    # Register blueprints
    app.register_blueprint(price_changes_bp)
    app.register_blueprint(market_orders_bp)
    app.register_blueprint(whale_activity_bp)
    app.register_blueprint(whale_monitor_bp)
    app.register_blueprint(live_data_bp)
    app.register_blueprint(historical_chart_bp)

    print("✓ All blueprints registered successfully")
