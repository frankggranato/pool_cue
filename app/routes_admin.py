"""
Admin routes - Analytics, Board Control, Ads Management
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from .models import Queue, Player
from .database import get_settings, update_settings, get_last_removal, get_game_rules, get_average_game_time
from datetime import datetime
import os
import glob
import json

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Ads folder structure
ADS_BASE = os.path.join(os.path.dirname(__file__), 'static', 'ads')
AD_PLACEMENTS = ['display', 'join', 'shotcaller', 'player']

def get_ads_folder(placement):
    """Get folder for specific ad placement."""
    folder = os.path.join(ADS_BASE, placement)
    os.makedirs(folder, exist_ok=True)
    return folder

def get_ads_config_file():
    """Get path to ads config JSON."""
    return os.path.join(ADS_BASE, 'config.json')

def load_ads_config():
    """Load ads configuration."""
    config_file = get_ads_config_file()
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except:
            pass
    return {'disabled': {}}

def save_ads_config(config):
    """Save ads configuration."""
    os.makedirs(ADS_BASE, exist_ok=True)
    with open(get_ads_config_file(), 'w') as f:
        json.dump(config, f)

def get_ads_for_placement(placement):
    """Get all ads for a placement with active status."""
    folder = get_ads_folder(placement)
    config = load_ads_config()
    disabled = config.get('disabled', {}).get(placement, [])
    
    extensions = ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.webp', '*.JPG', '*.JPEG', '*.PNG']
    files = []
    for ext in extensions:
        files.extend(glob.glob(os.path.join(folder, ext)))
    
    ads = []
    for f in sorted(set(files)):
        filename = os.path.basename(f)
        ads.append({
            'filename': filename,
            'active': filename not in disabled
        })
    return ads

@admin_bp.route('/')
def dashboard():
    """Admin dashboard with analytics."""
    settings = get_settings()
    queue = Queue.get_all()
    last_removal = get_last_removal()
    rules = get_game_rules()
    avg_time = get_average_game_time()
    
    # Get shot caller (first in queue)
    shot_caller = queue[0] if queue else None
    
    # Get ranked status for this bar
    from .database import check_ranked_requirement
    bar_id = queue[0].get('bar_id', 1) if queue else 1
    is_event_ranked, ranked_source, ranked_info = check_ranked_requirement(bar_id)
    ranked_status = {
        'is_event_ranked': is_event_ranked,
        'ranked_source': ranked_source,
        'ranked_info': ranked_info
    }
    
    # Try to get analytics (may fail if tables don't exist yet)
    try:
        from .database_player import get_analytics_summary
        analytics = get_analytics_summary()
    except:
        analytics = {
            'total_users': 0,
            'active_today': 0,
            'total_games': 0,
            'games_today': 0,
            'peak_hours': [],
            'avg_duration_minutes': round(avg_time / 60, 1) if avg_time else 0,
            'top_players': []
        }
    
    # Get permanent rules setting
    settings = get_settings()
    permanent_rules = settings.get('permanent_rules', 0)
    
    return render_template('admin/admin.html',
                           settings=settings,
                           queue=queue,
                           last_removal=last_removal,
                           rules=rules.get('game_type', 'singles'),
                           permanent_rules=permanent_rules,
                           shot_caller=shot_caller,
                           ranked_status=ranked_status,
                           analytics=analytics)

@admin_bp.route('/add_player', methods=['POST'])
def add_to_queue():
    """Add a player to queue from admin panel."""
    nickname = request.form.get('nickname', '').strip()
    partner = request.form.get('partner', '').strip() or None
    
    if not nickname:
        flash('Please enter a name', 'error')
        return redirect(url_for('admin.dashboard'))
    
    player = Player.find_or_create(nickname)
    if Queue.is_player_in_queue(player['id']):
        flash(f'{nickname} is already in queue', 'error')
        return redirect(url_for('admin.dashboard'))
    
    Queue.add_player(player['id'], partner)
    flash(f'Added {nickname} to queue', 'success')
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/remove_player', methods=['POST'])
def remove_player():
    """Remove a player from queue."""
    queue_id = request.form.get('queue_id', type=int)
    if queue_id:
        Queue.remove(queue_id)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/undo', methods=['POST'])
def undo():
    """Undo last removal."""
    result = Queue.undo_last_removal()
    if result:
        flash(f'Restored {result["player_nickname"]} to queue', 'success')
    else:
        flash('Nothing to undo', 'info')
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/make_king', methods=['POST'])
def make_king():
    """Give someone the table (make them shot caller)."""
    queue_id = request.form.get('queue_id', type=int)
    if queue_id:
        Queue.make_king(queue_id)
        flash('Player is now Shot Caller', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/confirm_player', methods=['POST'])
def confirm_player():
    """Staff confirms a player is present (no SMS needed)."""
    from .queue_confirmation import confirm_player_by_staff
    
    queue_id = request.form.get('queue_id', type=int)
    if queue_id:
        if confirm_player_by_staff(queue_id):
            flash('Player confirmed', 'success')
        else:
            flash('Could not confirm player', 'error')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/clear_queue', methods=['POST'])
def clear_queue():
    """Clear entire queue."""
    Queue.clear_all()
    flash('Queue cleared', 'success')
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/seed_demo', methods=['POST'])
def seed_demo():
    """Add 15 demo players to the queue."""
    demo_names = [
        'Mike "8-Ball" Rodriguez',
        'Sarah Chen',
        'Big Tony',
        'Lucky Lou',
        'Jen Martinez',
        'The Shark',
        'Danny Two-Stroke',
        'Rosa Valdez',
        'Slim Jim',
        'Katie O\'Brien',
        'Fast Eddie',
        'Marcus "Combo" King',
        'Ashley Park',
        'Vinnie Hustle',
        'Pocket Queen'
    ]
    
    added = 0
    for name in demo_names:
        player = Player.find_or_create(name)
        if not Queue.is_player_in_queue(player['id']):
            Queue.add_player(player['id'])
            added += 1
    
    flash(f'Added {added} demo players to queue', 'success')
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/settings')
def settings_page():
    """Settings page."""
    settings = get_settings()
    return render_template('admin/admin_settings.html', settings=settings)

@admin_bp.route('/settings', methods=['POST'])
def settings_save():
    """Save settings."""
    bar_name = request.form.get('bar_name', 'Pool Cue')
    address = request.form.get('address', '')
    city = request.form.get('city', '')
    state = request.form.get('state', '')
    zip_code = request.form.get('zip_code', '')
    table_count = request.form.get('table_count', 1, type=int)
    google_review_url = request.form.get('google_review_url', '')
    ad_rotation = request.form.get('ad_rotation_seconds', 10, type=int)
    base_match_minutes = request.form.get('base_match_minutes', 8, type=int)
    board_style = request.form.get('board_style', 'classic')
    
    update_settings(
        bar_name=bar_name,
        address=address,
        city=city,
        state=state,
        zip_code=zip_code,
        table_count=table_count,
        google_review_url=google_review_url,
        ad_rotation_seconds=ad_rotation,
        base_match_minutes=base_match_minutes,
        board_style=board_style
    )
    flash('Settings saved!', 'success')
    return redirect(url_for('admin.settings_page'))

@admin_bp.route('/ads')
def ads_page():
    """Ads management page with multiple placements."""
    settings = get_settings()
    
    return render_template('admin/admin_ads.html',
        ads_folder=ADS_BASE,
        settings=settings,
        display_ads=get_ads_for_placement('display'),
        join_ads=get_ads_for_placement('join'),
        shotcaller_ads=get_ads_for_placement('shotcaller'),
        player_ads=get_ads_for_placement('player')
    )

@admin_bp.route('/ads/image/<placement>/<filename>')
def serve_ad_image(placement, filename):
    """Serve ad image from placement folder or main ads folder (for campaign ads)."""
    if placement not in AD_PLACEMENTS:
        return '', 404
    folder = get_ads_folder(placement)
    # Check placement folder first
    file_path = os.path.join(folder, filename)
    if os.path.exists(file_path):
        return send_from_directory(folder, filename)
    # Fall back to main ads folder (for campaign creatives)
    main_folder = os.path.join(os.path.dirname(__file__), 'static', 'ads')
    main_path = os.path.join(main_folder, filename)
    if os.path.exists(main_path):
        return send_from_directory(main_folder, filename)
    return '', 404

@admin_bp.route('/ads/upload', methods=['POST'])
def upload_ad():
    """Upload new ad images."""
    placement = request.form.get('placement')
    if placement not in AD_PLACEMENTS:
        return jsonify({'error': 'Invalid placement'}), 400
    
    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'No files'}), 400
    
    folder = get_ads_folder(placement)
    count = 0
    for f in files:
        if f and f.filename:
            # Secure the filename
            filename = f.filename.replace('/', '_').replace('\\', '_')
            f.save(os.path.join(folder, filename))
            count += 1
    
    return jsonify({'success': True, 'count': count})

@admin_bp.route('/ads/toggle', methods=['POST'])
def toggle_ad():
    """Toggle ad active status."""
    data = request.json or {}
    placement = data.get('placement')
    filename = data.get('filename')
    
    if placement not in AD_PLACEMENTS:
        return jsonify({'error': 'Invalid placement'}), 400
    
    config = load_ads_config()
    if 'disabled' not in config:
        config['disabled'] = {}
    if placement not in config['disabled']:
        config['disabled'][placement] = []
    
    if filename in config['disabled'][placement]:
        config['disabled'][placement].remove(filename)
        active = True
    else:
        config['disabled'][placement].append(filename)
        active = False
    
    save_ads_config(config)
    return jsonify({'success': True, 'active': active})

@admin_bp.route('/ads/delete', methods=['POST'])
def delete_ad():
    """Delete an ad image."""
    data = request.json or {}
    placement = data.get('placement')
    filename = data.get('filename')
    
    if placement not in AD_PLACEMENTS:
        return jsonify({'error': 'Invalid placement'}), 400
    
    folder = get_ads_folder(placement)
    filepath = os.path.join(folder, filename)
    
    if os.path.exists(filepath):
        os.remove(filepath)
    
    # Also remove from disabled list if present
    config = load_ads_config()
    if placement in config.get('disabled', {}):
        if filename in config['disabled'][placement]:
            config['disabled'][placement].remove(filename)
            save_ads_config(config)
    
    return jsonify({'success': True})

@admin_bp.route('/api/stats')
def api_stats():
    """JSON stats endpoint for real-time updates."""
    queue = Queue.get_all()
    try:
        from .database_player import get_analytics_summary
        analytics = get_analytics_summary()
    except:
        analytics = {}
    
    return jsonify({
        'queue_length': len(queue),
        'king': queue[0]['nickname'] if queue else None,
        'challenger': queue[1]['nickname'] if len(queue) > 1 else None,
        'analytics': analytics
    })

@admin_bp.route('/brands')
def brands_page():
    """Brand Intelligence dashboard - redirect to dedicated blueprint."""
    return render_template('admin/admin_brands.html')

@admin_bp.route('/scheduled-rules')
def scheduled_rules():
    """Manage scheduled rules."""
    from .database import get_scheduled_rules
    rules = get_scheduled_rules(bar_id=1)
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    return render_template('admin/admin_scheduled_rules.html', rules=rules, days=days)

@admin_bp.route('/scheduled-rules/add', methods=['POST'])
def add_scheduled_rule():
    """Add a new scheduled rule."""
    from .database import add_scheduled_rule
    
    day = int(request.form.get('day_of_week', 0))
    start = request.form.get('start_time', '19:00')
    end = request.form.get('end_time', '23:00')
    game_type = request.form.get('game_type', 'singles')
    rule_type = request.form.get('rule_type', 'bar_rules')
    
    add_scheduled_rule(1, day, start, end, game_type, rule_type)
    return redirect(url_for('admin.scheduled_rules'))

@admin_bp.route('/scheduled-rules/delete/<int:rule_id>', methods=['POST'])
def delete_scheduled_rule_route(rule_id):
    """Delete a scheduled rule."""
    from .database import delete_scheduled_rule
    delete_scheduled_rule(rule_id)
    return redirect(url_for('admin.scheduled_rules'))

# ============================================
# POOL NIGHTS MANAGEMENT (Bar Manager)
# ============================================

@admin_bp.route('/pool-nights')
def pool_nights():
    """Pool nights management page for bar managers."""
    from .database import get_db
    from flask import session
    
    bar_id = session.get('bar_id', 1)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get pool nights for this bar
    cursor.execute('''
        SELECT pn.*, 
               p.nickname as host_name,
               (SELECT COUNT(*) FROM pool_night_rsvps WHERE pool_night_id = pn.id AND cancelled = 0) as rsvp_count
        FROM pool_nights pn
        LEFT JOIN players p ON pn.host_id = p.id
        WHERE pn.bar_id = ?
        ORDER BY pn.event_date DESC, pn.start_time DESC
    ''', (bar_id,))
    
    nights = [dict(row) for row in cursor.fetchall()]
    
    # Get stats
    total = len(nights)
    pending = sum(1 for n in nights if n['status'] == 'pending')
    approved = sum(1 for n in nights if n['status'] == 'approved')
    upcoming = sum(1 for n in nights if n['status'] == 'approved' and n['event_date'] >= str(datetime.now().date()))
    
    conn.close()
    
    return render_template('admin/pool_nights.html',
                           nights=nights,
                           total_nights=total,
                           pending_count=pending,
                           approved_count=approved,
                           upcoming_count=upcoming,
                           bar_id=bar_id)

@admin_bp.route('/pool-nights/create', methods=['POST'])
def create_pool_night():
    """Create a new pool night for this bar."""
    from .database import get_db
    from flask import session
    
    bar_id = session.get('bar_id', 1)
    
    # Get form data
    title = request.form.get('title', '').strip() or 'Pool Night'
    event_date = request.form.get('event_date')
    start_time = request.form.get('start_time', '19:00')
    end_time = request.form.get('end_time')
    entry_fee = float(request.form.get('entry_fee', 0) or 0)
    max_players = request.form.get('max_players')
    max_players = int(max_players) if max_players else None
    ranked_required = 1 if request.form.get('ranked_required') else 0
    description = request.form.get('description', '').strip()
    game_type = request.form.get('game_type', 'singles')
    
    if not event_date:
        flash('Date is required', 'error')
        return redirect(url_for('admin.pool_nights'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Create pool night with status 'pending' (requires master approval)
    cursor.execute('''
        INSERT INTO pool_nights 
        (bar_id, host_id, title, event_date, start_time, end_time, game_type, 
         entry_fee, max_players, ranked_required, description, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', datetime('now'))
    ''', (bar_id, 0, title, event_date, start_time, end_time, game_type, 
          entry_fee, max_players, ranked_required, description))
    
    conn.commit()
    conn.close()
    
    flash(f'Pool Night "{title}" created! Awaiting approval.', 'success')
    return redirect(url_for('admin.pool_nights'))

@admin_bp.route('/pool-nights/<int:night_id>')
def pool_night_detail(night_id):
    """View pool night details and RSVPs."""
    from .database import get_db
    from flask import session
    
    bar_id = session.get('bar_id', 1)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get pool night
    cursor.execute('''
        SELECT pn.*, p.nickname as host_name
        FROM pool_nights pn
        LEFT JOIN players p ON pn.host_id = p.id
        WHERE pn.id = ? AND pn.bar_id = ?
    ''', (night_id, bar_id))
    
    night = cursor.fetchone()
    if not night:
        conn.close()
        flash('Pool night not found', 'error')
        return redirect(url_for('admin.pool_nights'))
    
    night = dict(night)
    
    # Get RSVPs
    cursor.execute('''
        SELECT r.*, p.nickname, p.email, p.phone_number,
               (SELECT AVG(show_rate) FROM player_rsvp_stats WHERE player_id = r.player_id) as show_rate
        FROM pool_night_rsvps r
        JOIN players p ON r.player_id = p.id
        WHERE r.pool_night_id = ? AND r.cancelled = 0
        ORDER BY r.rsvp_at ASC
    ''', (night_id,))
    
    rsvps = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return render_template('admin/pool_night_detail.html',
                           night=night,
                           rsvps=rsvps)

@admin_bp.route('/pool-nights/<int:night_id>/cancel', methods=['POST'])
def cancel_pool_night(night_id):
    """Cancel a pool night."""
    from .database import get_db
    from flask import session
    
    bar_id = session.get('bar_id', 1)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Verify this night belongs to the bar
    cursor.execute('SELECT id, status FROM pool_nights WHERE id = ? AND bar_id = ?', (night_id, bar_id))
    night = cursor.fetchone()
    
    if not night:
        conn.close()
        flash('Pool night not found', 'error')
        return redirect(url_for('admin.pool_nights'))
    
    # Update status
    cursor.execute('''
        UPDATE pool_nights 
        SET status = 'cancelled', cancelled_at = datetime('now')
        WHERE id = ?
    ''', (night_id,))
    
    conn.commit()
    conn.close()
    
    flash('Pool night cancelled', 'success')
    return redirect(url_for('admin.pool_nights'))

