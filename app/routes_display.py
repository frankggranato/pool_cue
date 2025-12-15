"""
Display routes - TV screen view
DO NOT CHANGE BOARD STYLING
"""
from flask import Blueprint, render_template, send_file, send_from_directory, request, url_for
from .models import Queue
from .database import get_settings, get_game_rules, get_average_game_time
import qrcode
import io
import os
import socket
import glob
import json
from datetime import datetime

display_bp = Blueprint('display', __name__)

# Rate limiter for confirmation checks (run every 30 seconds max)
_last_confirmation_check = None
CONFIRMATION_CHECK_INTERVAL = 30  # seconds

# Ads folder paths - creatives are stored directly in ads folder
ADS_BASE = os.path.join(os.path.dirname(__file__), 'static', 'ads')
ADS_FOLDER = os.path.join(ADS_BASE, 'display')  # Legacy display subfolder
ADS_CAMPAIGN_FOLDER = ADS_BASE  # Campaign creatives saved here

def get_local_ip():
    """Get local IP for fallback when request context unavailable."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "localhost"

def get_join_url(bar_id=None, table_id=None, table_token=None):
    """
    Build the full join URL for QR codes.
    For local development: Always uses network IP so phones can scan QR codes.
    For production: Uses the request host (your domain).
    """
    try:
        host = request.host  # e.g., "127.0.0.1:5002" or "poolcue.com"
        
        # If accessing via localhost/127.0.0.1, use network IP instead
        # This ensures QR codes work for phones on the same WiFi
        if host.startswith('127.0.0.1') or host.startswith('localhost'):
            local_ip = get_local_ip()
            port = host.split(':')[1] if ':' in host else '5002'
            base_url = f"http://{local_ip}:{port}"
        else:
            # Production or already using network IP - use request host
            base_url = request.host_url.rstrip('/')
        
        if table_token:
            # Table-specific QR code URL (most specific)
            join_url = f"{base_url}/t/{table_token}"
        elif bar_id and table_id:
            # Bar + table specific
            join_url = f"{base_url}/q/{bar_id}/{table_id}"
        elif bar_id:
            # Bar-specific (legacy, routes to table 1 by default)
            join_url = f"{base_url}/q/{bar_id}"
        else:
            # Generic join page
            join_url = f"{base_url}/join"
        
        return join_url
    except RuntimeError:
        # No request context - fallback to local IP
        local_ip = get_local_ip()
        port = os.environ.get('PORT', '5002')
        if table_token:
            return f"http://{local_ip}:{port}/t/{table_token}"
        elif bar_id and table_id:
            return f"http://{local_ip}:{port}/q/{bar_id}/{table_id}"
        elif bar_id:
            return f"http://{local_ip}:{port}/q/{bar_id}"
        return f"http://{local_ip}:{port}/join"

def load_ads_config():
    """Load ads configuration from config.json file."""
    config_file = os.path.join(ADS_BASE, 'config.json')
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except:
            pass
    return {'disabled': {}}

def get_ads_from_folder():
    """Get list of active ad images from the display folder, excluding disabled ads."""
    if not os.path.exists(ADS_FOLDER):
        os.makedirs(ADS_FOLDER, exist_ok=True)
        return []
    
    config = load_ads_config()
    disabled = config.get('disabled', {}).get('display', [])
    
    extensions = ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.webp', '*.JPG', '*.JPEG', '*.PNG']
    ads = []
    for ext in extensions:
        ads.extend(glob.glob(os.path.join(ADS_FOLDER, ext)))
    
    # Filter out disabled ads
    active_ads = [os.path.basename(f) for f in sorted(set(ads)) if os.path.basename(f) not in disabled]
    return active_ads


def get_ads_for_board(bar_id=None):
    """
    Get ads from active campaigns that target this bar and board placements.
    Falls back to folder-based ads if no campaign ads are found.
    """
    import json
    from .database import get_db
    
    campaign_ads = []
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Get creatives from active campaigns
        cursor.execute('''
            SELECT DISTINCT ac.file_name, c.target_bars, c.target_placements
            FROM ad_creatives ac
            JOIN campaigns c ON c.id = ac.campaign_id
            WHERE c.status = 'active'
              AND ac.is_active = 1
              AND (c.start_date IS NULL OR c.start_date <= DATE('now'))
              AND (c.end_date IS NULL OR c.end_date >= DATE('now'))
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        for row in rows:
            file_name = row['file_name']
            target_bars_json = row['target_bars']
            target_placements_json = row['target_placements']
            
            # Check bar targeting
            bar_match = True
            if bar_id and target_bars_json:
                try:
                    target_bars = json.loads(target_bars_json)
                    target_bars = [str(b) for b in target_bars]
                    bar_match = str(bar_id) in target_bars
                except:
                    bar_match = True
            
            # Check placement targeting (board placements)
            placement_match = True
            if target_placements_json:
                try:
                    target_placements = json.loads(target_placements_json)
                    board_placements = ['board_rotation', 'board_main', 'between_games', 'winner_screen', 'loser_screen', 'queue_idle', 'display']
                    placement_match = any(p in target_placements for p in board_placements) or len(target_placements) == 0
                except:
                    placement_match = True
            
            if bar_match and placement_match and file_name:
                # Check file exists - campaign creatives are in ADS_CAMPAIGN_FOLDER
                file_path = os.path.join(ADS_CAMPAIGN_FOLDER, file_name)
                if os.path.exists(file_path):
                    campaign_ads.append(file_name)
                else:
                    # Also check in display subfolder for legacy ads
                    file_path = os.path.join(ADS_FOLDER, file_name)
                    if os.path.exists(file_path):
                        campaign_ads.append(file_name)
    except Exception as e:
        print(f"[AD SERVING] Error getting campaign ads: {e}")
    
    # If we found campaign ads, use those; otherwise fall back to folder
    if campaign_ads:
        return campaign_ads
    
    return get_ads_from_folder()

@display_bp.route('/ad_image/<filename>')
def serve_ad(filename):
    """Serve ad image from either campaign folder or display subfolder."""
    # Try campaign folder first
    campaign_path = os.path.join(ADS_CAMPAIGN_FOLDER, filename)
    if os.path.exists(campaign_path):
        return send_from_directory(ADS_CAMPAIGN_FOLDER, filename)
    # Fall back to display subfolder
    return send_from_directory(ADS_FOLDER, filename)

@display_bp.route('/qr_code')
def qr_code():
    """
    Generate QR code for join URL.
    Accepts optional params for table-specific QR codes:
    - bar_id: Bar ID (legacy, will use table 1)
    - table_id: Specific table ID within the bar
    - table_token: Unique table token for direct table lookup
    Uses request.host_url for proper dev/prod URL generation.
    """
    bar_id = request.args.get('bar_id', type=int)
    table_id = request.args.get('table_id', type=int)
    table_token = request.args.get('table_token')
    
    join_url = get_join_url(bar_id, table_id, table_token)
    
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    qr.add_data(join_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    return send_file(img_io, mimetype='image/png')


@display_bp.route('/qr_code/table/<table_token>')
def qr_code_for_table(table_token):
    """
    Generate QR code for a specific table using its unique token.
    This is the preferred method for generating table-specific QR codes.
    """
    from .database import get_table_by_token
    
    table = get_table_by_token(table_token)
    if not table:
        return "Table not found", 404
    
    join_url = get_join_url(table_token=table_token)
    
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    qr.add_data(join_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    return send_file(img_io, mimetype='image/png')


@display_bp.route('/share')
def share_qr():
    """Shareable QR code page for testers."""
    bar_id = request.args.get('bar_id', type=int)
    join_url = get_join_url(bar_id)
    return render_template('board/share_qr.html', join_url=join_url, bar_id=bar_id)


@display_bp.route('/api/board-data')
def board_data():
    """
    JSON endpoint for soft-refresh board updates.
    Returns current queue state without full page reload.
    """
    from flask import jsonify
    from .database import get_db, check_ranked_requirement, determine_match_ranked_status
    
    bar_id = request.args.get('bar_id', type=int)
    
    # Get bar info if bar_id specified
    bar_name = None
    if bar_id:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT name FROM bars WHERE id = ?', (bar_id,))
        bar_row = cursor.fetchone()
        bar_name = bar_row['name'] if bar_row else None
        conn.close()
    
    # Get queue - filter by bar_id if specified
    if bar_id:
        queue = Queue.get_all_for_bar(bar_id)
    else:
        queue = Queue.get_all()
    
    king = queue[0] if queue else None
    challenger = queue[1] if len(queue) > 1 else None
    queue_list = queue[2:] if len(queue) > 2 else []
    
    settings = get_settings()
    rules = get_game_rules()
    avg_game_time = get_average_game_time()
    
    # Use provided bar_id or get from king
    effective_bar_id = bar_id if bar_id else (king.get('bar_id', 1) if king else 1)
    wait_time = len(queue) * (avg_game_time // 60) if avg_game_time else len(queue) * 8
    
    # Get ranked status for display
    is_event_ranked, ranked_source, ranked_info = check_ranked_requirement(effective_bar_id)
    
    # Check player-initiated ranked status
    player_ranked = False
    if king:
        is_ranked, source = determine_match_ranked_status(effective_bar_id, king['id'])
        player_ranked = is_ranked and source == 'player'
    
    response = jsonify({
        'king': king,
        'challenger': challenger,
        'queue_list': queue_list,
        'rules': rules,
        'avg_game_time': avg_game_time,
        'wait_time': wait_time,
        'ranked_status': {
            'is_ranked': is_event_ranked or player_ranked,
            'is_event': is_event_ranked,
            'is_player': player_ranked,
            'info': ranked_info
        },
        'bar_id': effective_bar_id,
        'bar_name': bar_name,
        'queue_count': len(queue)
    })
    # Prevent caching so name changes show immediately
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@display_bp.route('/display')
@display_bp.route('/')
def display_board():
    """Queue display board - BLACK BOARD WITH BROWN FRAME - DO NOT CHANGE STYLING"""
    from flask import request
    from .database import get_db, get_table_by_id, get_bar_tables
    
    # Get bar_id and optional table_id from query parameters
    bar_id = request.args.get('bar_id', type=int)
    table_id = request.args.get('table_id', type=int)
    
    # Get bar info if bar_id specified
    bar_name = None
    table_info = None
    table_token = None
    
    if bar_id:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT name FROM bars WHERE id = ?', (bar_id,))
        bar_row = cursor.fetchone()
        bar_name = bar_row['name'] if bar_row else None
        conn.close()
        
        # Get table info - either specific table or first active table
        if table_id:
            table_info = get_table_by_id(table_id)
            if table_info and table_info.get('bar_id') == bar_id:
                table_token = table_info.get('qr_code_token')
        else:
            # Get first active table for this bar
            tables = get_bar_tables(bar_id, active_only=True)
            if tables:
                table_info = tables[0]
                table_id = table_info.get('id')
                table_token = table_info.get('qr_code_token')
    
    # Get queue - filter by bar_id if specified
    if bar_id:
        queue = Queue.get_all_for_bar(bar_id)
    else:
        queue = Queue.get_all()
    
    king = queue[0] if queue else None
    challenger = queue[1] if len(queue) > 1 else None
    queue_list = queue[2:] if len(queue) > 2 else []
    
    settings = get_settings()
    rules = get_game_rules()
    avg_game_time = get_average_game_time()
    ads = get_ads_for_board(bar_id)  # Use bar-targeted ads from campaigns
    
    # Use provided bar_id or get from king
    if not bar_id:
        bar_id = king.get('bar_id', 1) if king else 1
    
    # Build join URL - use table_token if available for table-specific QR
    join_url = get_join_url(bar_id, table_id, table_token)
    wait_time = len(queue) * (avg_game_time // 60) if avg_game_time else len(queue) * 8
    
    # Get ranked status for display
    from .database import check_ranked_requirement, determine_match_ranked_status
    is_event_ranked, ranked_source, ranked_info = check_ranked_requirement(bar_id)
    
    # Check player-initiated ranked status
    player_ranked = False
    if king:
        is_ranked, source = determine_match_ranked_status(bar_id, king['id'])
        player_ranked = is_ranked and source == 'player'
    
    ranked_status = {
        'is_ranked': is_event_ranked or player_ranked,
        'is_event': is_event_ranked,
        'is_player': player_ranked,
        'info': ranked_info
    }
    
    return render_template('board/display.html',
        king=king, challenger=challenger, queue_list=queue_list,
        settings=settings, rules=rules, join_url=join_url, wait_time=wait_time,
        avg_game_time=avg_game_time,
        ads=ads, ad_rotation=settings.get('ad_rotation_seconds', 8),
        ranked_status=ranked_status,
        bar_id=bar_id,
        bar_name=bar_name,
        table_id=table_id,
        table_token=table_token,
        table_name=table_info.get('table_name') if table_info else None
    )


@display_bp.route('/qr-codes/<int:bar_id>')
def qr_codes_for_bar(bar_id):
    """
    Display all QR codes for a bar's tables.
    Useful for printing and placing at each table.
    """
    from .database import get_db, get_bar_tables, ensure_bar_tables
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM bars WHERE id = ?', (bar_id,))
    bar = cursor.fetchone()
    conn.close()
    
    if not bar:
        return "Bar not found", 404
    
    bar = dict(bar)
    
    # Ensure tables exist with QR tokens
    tables = ensure_bar_tables(bar_id, bar.get('table_count') or bar.get('tables') or 1)
    
    # Build QR code URLs for each table
    base_url = request.host_url.rstrip('/')
    for table in tables:
        table['qr_url'] = url_for('display.qr_code_for_table', table_token=table['qr_code_token'])
        table['join_url'] = f"{base_url}/t/{table['qr_code_token']}"
        table['display_url'] = f"{base_url}/display?bar_id={bar_id}&table_id={table['id']}"
    
    return render_template('board/qr_codes.html', bar=bar, tables=tables)
