"""
Brand Intelligence Admin Routes
"""
from flask import Blueprint, render_template, request, jsonify
from .database import get_db
from .services import brand_service, stats_service, reports_service
from .services import cohort_service
import json
from datetime import datetime, timedelta

brand_admin_bp = Blueprint('brand_admin', __name__, url_prefix='/admin/brands')

@brand_admin_bp.route('/')
def brand_dashboard():
    """Brand Intelligence main dashboard."""
    return render_template('admin/brand_intelligence.html')

@brand_admin_bp.route('/api/overview')
def api_overview():
    """Get network-level overview stats."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Date range (current month)
    today = datetime.now()
    start = today.replace(day=1).strftime('%Y-%m-%d')
    end = today.strftime('%Y-%m-%d')
    
    # Total active players this month
    cursor.execute('''SELECT COUNT(DISTINCT winner_id) FROM game_history 
                      WHERE played_at >= ?''', (start,))
    active_players = cursor.fetchone()[0] or 0
    
    # Total matches this month
    cursor.execute('SELECT COUNT(*) FROM game_history WHERE played_at >= ?', (start,))
    total_matches = cursor.fetchone()[0] or 0
    
    # Top bars by engagement
    cursor.execute('''SELECT bar_id, engagement_score FROM bar_engagement_daily 
                      WHERE date >= ? ORDER BY engagement_score DESC LIMIT 10''', (start,))
    top_bars = [{'bar_id': r[0], 'score': r[1]} for r in cursor.fetchall()]
    
    conn.close()
    
    # Top brands
    brands = brand_service.get_all_brands_summary(start, end)[:5]
    
    return jsonify({
        'active_players': active_players,
        'total_matches': total_matches,
        'top_bars': top_bars,
        'top_brands': brands,
        'period': {'start': start, 'end': end}
    })

@brand_admin_bp.route('/api/brands')
def api_brands():
    """Get all brands with metrics."""
    today = datetime.now()
    start = today.replace(day=1).strftime('%Y-%m-%d')
    end = today.strftime('%Y-%m-%d')
    
    brands = brand_service.get_all_brands_summary(start, end)
    return jsonify(brands)

@brand_admin_bp.route('/api/brands/<int:brand_id>')
def api_brand_detail(brand_id):
    """Get detailed metrics for a brand."""
    start = request.args.get('start', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end = request.args.get('end', datetime.now().strftime('%Y-%m-%d'))
    
    metrics = brand_service.get_brand_metrics(brand_id, start, end)
    return jsonify(metrics)

@brand_admin_bp.route('/api/brands/<int:brand_id>/generate_report', methods=['POST'])
def api_generate_report(brand_id):
    """Generate monthly brand report."""
    data = request.json or {}
    start = data.get('start', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end = data.get('end', datetime.now().strftime('%Y-%m-%d'))
    
    result = reports_service.generate_brand_report(brand_id, start, end)
    return jsonify(result)

@brand_admin_bp.route('/api/engagement')
def api_engagement():
    """Get bar engagement data."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get recent engagement data
    cursor.execute('''SELECT bar_id, date, unique_players, matches_played, 
                             engagement_score, peak_hour
                      FROM bar_engagement_daily 
                      ORDER BY date DESC, engagement_score DESC LIMIT 50''')
    
    data = []
    for r in cursor.fetchall():
        data.append({
            'bar_id': r[0],
            'date': r[1],
            'unique_players': r[2],
            'matches': r[3],
            'engagement_score': r[4],
            'peak_hour': r[5],
            'heat_label': stats_service.get_heat_label(r[4] or 0)
        })
    
    conn.close()
    return jsonify(data)

@brand_admin_bp.route('/api/cohorts')
def api_cohorts():
    """Get cohort breakdown."""
    breakdown = cohort_service.get_cohort_breakdown()
    return jsonify(breakdown)

@brand_admin_bp.route('/api/cohorts/recompute', methods=['POST'])
def api_recompute_cohorts():
    """Trigger cohort recomputation."""
    results = cohort_service.batch_compute_cohorts()
    return jsonify({'users_processed': len(results)})

@brand_admin_bp.route('/api/reports')
def api_reports():
    """Get list of generated reports."""
    reports = reports_service.get_all_reports(limit=30)
    return jsonify(reports)

@brand_admin_bp.route('/api/heatmap')
def api_heatmap():
    """Get activity heatmap."""
    bar_id = request.args.get('bar_id', type=int)
    heatmap = stats_service.get_activity_heatmap(bar_id)
    return jsonify(heatmap)

@brand_admin_bp.route('/api/league_metrics')
def api_league_metrics():
    """Get league replacement metrics."""
    metrics = stats_service.get_league_metrics()
    return jsonify(metrics)
