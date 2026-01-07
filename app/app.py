"""
Pool Queue App - Main Flask Application
"""
from flask import Flask
import os
from .logging_config import setup_logging, get_logger

# Initialize logger
logger = get_logger('app')

# Rate limiting setup (install with: pip install flask-limiter)
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    RATE_LIMITING_AVAILABLE = True
except ImportError:
    RATE_LIMITING_AVAILABLE = False
    logger.warning("flask-limiter not installed. Rate limiting disabled.")

# CSRF protection setup (install with: pip install flask-wtf)
try:
    from flask_wtf.csrf import CSRFProtect
    CSRF_AVAILABLE = True
except ImportError:
    CSRF_AVAILABLE = False
    logger.warning("flask-wtf not installed. CSRF protection disabled.")

def create_app():
    app = Flask(__name__)
    # SECURITY: Use environment variable for secret key
    app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(32)
    
    # SECURITY: Session cookie settings
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,    # Prevent JavaScript access to session cookie
        SESSION_COOKIE_SAMESITE='Lax',   # CSRF protection
        PERMANENT_SESSION_LIFETIME=2592000  # 30 day sessions (was 24 hours)
    )
    # Note: SESSION_COOKIE_SECURE=True should be enabled in production with HTTPS
    
    # SECURITY: Initialize rate limiter
    if RATE_LIMITING_AVAILABLE:
        limiter = Limiter(
            get_remote_address,
            app=app,
            default_limits=["200 per day", "50 per hour"],
            storage_uri="memory://",
        )
        app.limiter = limiter
    else:
        app.limiter = None
    
    # SECURITY: Initialize CSRF protection
    # DISABLED for local development - enable for production
    if False and CSRF_AVAILABLE:
        csrf = CSRFProtect(app)
        app.csrf = csrf
        # Exempt API endpoints from CSRF (they use session/token auth)
        csrf.exempt('public.api_queue')
        csrf.exempt('public.api_queue_join')
        csrf.exempt('public.api_king_wins')
        csrf.exempt('public.api_challenger_wins')
        csrf.exempt('display.board_data')
        csrf.exempt('api.api_queue_status')
        csrf.exempt('social.api_token_balance')
        csrf.exempt('ad_tracking.track_impression')
        csrf.exempt('ad_tracking.track_click')
        # Exempt auth routes during development (forms need CSRF tokens added)
        csrf.exempt('auth')
        csrf.exempt('unified_auth')
        csrf.exempt('public')
        csrf.exempt('admin')
        csrf.exempt('master')
        csrf.exempt('player')
        csrf.exempt('bar_manager')
        csrf.exempt('market')
        csrf.exempt('setup')
        csrf.exempt('board')
        csrf.exempt('apps')
    else:
        app.csrf = None
    
    # SECURITY: Add security headers to all responses
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response
    
    # Initialize databases
    from .database import init_db
    init_db()
    
    # Initialize player app tables
    try:
        from .database_player import init_player_db
        init_player_db()
    except Exception as e:
        logger.debug(f"Player DB init: {e}")
    
    # Initialize league system tables
    try:
        from .database_league import init_league_db
        init_league_db()
    except Exception as e:
        logger.debug(f"League DB init: {e}")
    
    # Initialize extended tables (brands, tokens, surveys)
    try:
        from .database_extended import init_extended_db
        init_extended_db()
    except Exception as e:
        logger.debug(f"Extended DB init: {e}")
    
    # Initialize enhanced data collection tables
    try:
        from .database_enhanced import init_enhanced_db
        init_enhanced_db()
    except Exception as e:
        logger.debug(f"Enhanced DB init: {e}")
    
    # Initialize v2 protected database (marketing analytics + data protection)
    try:
        from .database_v2 import init_v2
        init_v2()
    except Exception as e:
        logger.debug(f"Database v2 init: {e}")
    
    # Initialize social/token system
    try:
        from .database_social import init_social_db
        init_social_db()
    except Exception as e:
        logger.debug(f"Social DB init: {e}")
    
    # Initialize social & tokens system
    try:
        from .database_social import init_social_db
        init_social_db()
    except Exception as e:
        logger.debug(f"Social DB init: {e}")
    
    # Initialize ad events tracking table
    try:
        from .ad_events import init_ad_events_table
        init_ad_events_table()
    except Exception as e:
        logger.debug(f"Ad events DB init: {e}")
    
    # Initialize self-serve marketer system
    try:
        from .marketer_system import init_marketer_tables
        init_marketer_tables()
    except Exception as e:
        logger.debug(f"Marketer DB init: {e}")
    
    # Register blueprints
    from .routes_public import public_bp
    from .routes_display import display_bp
    from .routes_admin import admin_bp
    from .routes_player import player_bp
    from .routes_master import master_bp
    from .routes_brand_admin import brand_admin_bp
    from .routes_api import api_bp
    from .routes_apps import apps_bp
    from .routes_auth import auth_bp
    from .routes_social import social_bp
    from .routes_setup import setup_bp
    from .routes_board import board_bp
    from .routes_ad_tracking import ad_tracking_bp
    from .routes_market import market_bp
    from .routes_twilio import twilio_bp
    from .routes_bar_manager import bar_manager_bp
    from .routes_unified_auth import unified_auth_bp
    from .rbac import inject_rbac_context
    
    app.register_blueprint(public_bp)
    app.register_blueprint(display_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(player_bp)
    app.register_blueprint(master_bp)
    app.register_blueprint(brand_admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(apps_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(social_bp)
    app.register_blueprint(setup_bp)
    app.register_blueprint(board_bp)
    app.register_blueprint(ad_tracking_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(twilio_bp)
    app.register_blueprint(bar_manager_bp)
    app.register_blueprint(unified_auth_bp)
    
    # Add RBAC context to all templates
    app.context_processor(inject_rbac_context)
    
    # Background tasks disabled for now - enable when Twilio is configured
    # from .background_tasks import start_background_tasks
    # start_background_tasks(app)
    
    return app

# For running directly
app = create_app()

if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true', port=5000)
