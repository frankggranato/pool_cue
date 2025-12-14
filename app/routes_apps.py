"""
App Routes - Entry points for the 4 main Pool Cue applications
"""
from flask import Blueprint, render_template, redirect, send_from_directory, request
import os

apps_bp = Blueprint('apps', __name__, url_prefix='/app')

# Icons folder path - now in static folder
ICONS_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'icons')

@apps_bp.route('/icons/<filename>')
def serve_icon(filename):
    """Serve app icons from the icons folder."""
    return send_from_directory(ICONS_FOLDER, filename)

@apps_bp.route('/')
def launcher():
    """App launcher - redirects to master dashboard."""
    return redirect('/master')

@apps_bp.route('/board')
@apps_bp.route('/board/<int:bar_id>')
def board_app(bar_id=None):
    """Board App - redirects to display for now, will have wrapper."""
    from .database import get_db, get_settings
    
    # Get bar_id from URL param or query string
    if bar_id is None:
        bar_id = request.args.get('bar_id', type=int)
    
    # Get list of bars for selection
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM bars WHERE is_active = 1 ORDER BY name')
    bars = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    # If no bar_id and only one bar, use it
    if bar_id is None and len(bars) == 1:
        bar_id = bars[0]['id']
    
    # Get settings for refresh rate
    settings = get_settings()
    
    return render_template('apps/app_board.html', bar_id=bar_id, bars=bars, settings=settings)

@apps_bp.route('/player')
def player_app():
    """Player App - mobile app wrapper."""
    return render_template('apps/app_player.html')

@apps_bp.route('/manager')
def manager_app():
    """Bar Manager App - mobile app wrapper."""
    return render_template('apps/app_manager.html')

@apps_bp.route('/analytics')
def analytics_app():
    """Analytics App - master dashboard wrapper with sidebar navigation."""
    return render_template('apps/app_analytics.html')
