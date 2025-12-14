"""
Ad Tracking Routes - Click tracking and impression logging API
"""
from flask import Blueprint, redirect, request, jsonify, session
from .ad_events import log_impression, log_click, get_creative_click_url
import logging

logger = logging.getLogger(__name__)

ad_tracking_bp = Blueprint('ad_tracking', __name__, url_prefix='/ad')


def is_safe_url(url):
    """
    SECURITY: Validate redirect URL to prevent open redirect attacks.
    Only allow URLs from the database or relative URLs.
    """
    if not url:
        return False
    if url.startswith('/'):
        return True
    if not url.startswith(('http://', 'https://')):
        return False
    if url.lower().startswith(('javascript:', 'data:', 'vbscript:')):
        return False
    return True


@ad_tracking_bp.route('/click/<path:ad_filename>')
def track_click(ad_filename):
    """
    Track an ad click and redirect to the destination URL.
    
    Usage: /ad/click/my-ad-image.jpg?placement=player_home&bar_id=1
    
    SECURITY: Only redirects to URLs from the database (trusted).
    Query parameter URLs are no longer accepted to prevent open redirect attacks.
    """
    # Get optional parameters
    placement = request.args.get('placement', 'unknown')
    bar_id = request.args.get('bar_id', type=int)
    table_id = request.args.get('table_id', type=int)
    player_id = session.get('player_id')
    session_token = session.get('session_token')
    
    # Get the click URL from the database ONLY (trusted source)
    click_url = get_creative_click_url(ad_filename)
    
    # SECURITY: Removed query param fallback - was open redirect vulnerability
    
    # Validate the URL before redirecting
    if click_url and not is_safe_url(click_url):
        logger.warning(f"Blocked unsafe redirect URL: {click_url}")
        click_url = None
    
    # Log the click
    log_click(
        placement=placement,
        ad_filename=ad_filename,
        click_url=click_url,
        bar_id=bar_id,
        table_id=table_id,
        player_id=player_id,
        session_token=session_token,
        user_agent=request.headers.get('User-Agent'),
        ip_address=request.remote_addr,
        referrer=request.referrer
    )
    
    logger.info(f"Ad click: {ad_filename} at {placement}, redirecting to {click_url}")
    
    # Redirect to the destination or home if no URL
    if click_url:
        return redirect(click_url)
    else:
        return redirect('/')


@ad_tracking_bp.route('/impression', methods=['POST'])
def track_impression():
    """
    API endpoint to log an ad impression.
    Used by JavaScript on the board display for client-side tracking.
    
    POST JSON body:
    {
        "ad_filename": "my-ad.jpg",
        "placement": "board_main",
        "bar_id": 1,
        "table_id": 1
    }
    """
    data = request.get_json() or {}
    
    ad_filename = data.get('ad_filename')
    placement = data.get('placement', 'unknown')
    bar_id = data.get('bar_id')
    table_id = data.get('table_id')
    player_id = session.get('player_id')
    session_token = data.get('session_token') or session.get('session_token')
    
    if not ad_filename:
        return jsonify({'error': 'ad_filename required'}), 400
    
    event_id = log_impression(
        placement=placement,
        ad_filename=ad_filename,
        bar_id=bar_id,
        table_id=table_id,
        player_id=player_id,
        session_token=session_token,
        user_agent=request.headers.get('User-Agent'),
        ip_address=request.remote_addr
    )
    
    return jsonify({
        'success': True,
        'event_id': event_id
    })


@ad_tracking_bp.route('/batch-impressions', methods=['POST'])
def track_batch_impressions():
    """
    API endpoint to log multiple ad impressions at once.
    Useful for board displays showing multiple ads in rotation.
    
    POST JSON body:
    {
        "impressions": [
            {"ad_filename": "ad1.jpg", "placement": "board_main"},
            {"ad_filename": "ad2.jpg", "placement": "board_main"}
        ],
        "bar_id": 1,
        "table_id": 1
    }
    """
    data = request.get_json() or {}
    
    impressions = data.get('impressions', [])
    bar_id = data.get('bar_id')
    table_id = data.get('table_id')
    player_id = session.get('player_id')
    session_token = data.get('session_token')
    
    logged_count = 0
    for imp in impressions:
        ad_filename = imp.get('ad_filename')
        placement = imp.get('placement', 'board_main')
        
        if ad_filename:
            log_impression(
                placement=placement,
                ad_filename=ad_filename,
                bar_id=bar_id,
                table_id=table_id,
                player_id=player_id,
                session_token=session_token,
                user_agent=request.headers.get('User-Agent'),
                ip_address=request.remote_addr
            )
            logged_count += 1
    
    return jsonify({
        'success': True,
        'logged_count': logged_count
    })


@ad_tracking_bp.route('/stats')
def get_stats():
    """
    Get ad stats summary. For internal/admin use.
    
    Query params:
    - advertiser_id: Filter by advertiser
    - campaign_id: Filter by campaign
    - days: Number of days (default 30)
    """
    from .ad_events import get_ad_stats, get_ad_stats_by_placement
    
    advertiser_id = request.args.get('advertiser_id', type=int)
    campaign_id = request.args.get('campaign_id', type=int)
    days = request.args.get('days', 30, type=int)
    
    stats = get_ad_stats(
        advertiser_id=advertiser_id,
        campaign_id=campaign_id,
        days=days
    )
    
    by_placement = get_ad_stats_by_placement(
        advertiser_id=advertiser_id,
        campaign_id=campaign_id,
        days=days
    )
    
    return jsonify({
        'summary': stats,
        'by_placement': by_placement
    })
