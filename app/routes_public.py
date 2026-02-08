"""
from .logging_config import get_logger
logger = get_logger(__name__)
Public routes - Join queue and player actions
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from .models import Player, Queue
from .database import get_settings, get_game_rules, set_game_rules, get_last_removal, get_average_game_time, get_db, get_current_rules, check_ranked_requirement
from .queue_confirmation import (
    confirm_ready, check_and_enforce_timeouts, get_queue_with_confirmation_status,
    on_game_end, request_confirmation, CONFIRM_TIMEOUT_SECONDS, REMOVAL_TIMEOUT_SECONDS
)
import os
import glob
import json
import random

public_bp = Blueprint('public', __name__)


def auto_join_pending_player(player_id):
    """
    If there is a pending join in the session (from a QR scan),
    join the logged-in player into that queue and clear the pending flags.
    
    Returns (queue_id, session_token, bar_id) if joined, or (None, None, None) if nothing to do.
    Safe to call multiple times - returns None if already cleared.
    """
    bar_id = session.pop('pending_join_bar_id', None)
    table_id = session.pop('pending_join_table_id', None)
    session.pop('pending_join_source', None)  # Clear source flag too
    
    if not bar_id:
        return None, None, None
    
    # Check if player already in queue at this bar
    if Queue.is_player_in_queue(player_id, bar_id=bar_id):
        # Already in queue - just return without creating duplicate
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, session_token FROM queue 
            WHERE player_id = ? AND bar_id = ? AND status IN ('waiting', 'playing')
            LIMIT 1
        """, (player_id, bar_id))
        existing = cursor.fetchone()
        conn.close()
        if existing:
            session['session_token'] = existing['session_token']
            return existing['id'], existing['session_token'], bar_id
        return None, None, None
    
    # Add player to queue
    queue_id, session_token = Queue.add_player(player_id, partner_name=None, bar_id=bar_id, table_id=table_id)
    session['session_token'] = session_token
    
    # Log queue usage for analytics (get player info)
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT nickname, phone_number, account_id FROM players WHERE id = ?', (player_id,))
        player = cursor.fetchone()
        conn.close()
        
        if player and player['phone_number']:
            from .database import log_queue_usage
            log_queue_usage(
                phone_number=player['phone_number'],
                bar_id=bar_id,
                player_id=player_id,
                nickname=player['nickname'],
                has_account=player.get('account_id') is not None
            )
    except Exception as e:
        logger.debug(f"[AUTO-JOIN] Analytics log failed: {e}")
    
    return queue_id, session_token, bar_id


@public_bp.route('/access')
def access_portal():
    """Unified access portal - choose your login type."""
    return render_template('public/access.html')


@public_bp.route('/beta')
def beta():
    """Beta tester landing page with QR codes."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        host = s.getsockname()[0]
        s.close()
    except Exception:
        host = "localhost"
    return render_template('auth/beta_invite.html', host=host)


@public_bp.route('/advertise')
def advertise():
    """Redirect to advertise landing page."""
    return redirect(url_for('market.advertise_landing'))

# Ads folder
ADS_BASE = os.path.join(os.path.dirname(__file__), 'static', 'ads')

def get_active_ad(placement):
    """Get a random active ad filename for a placement and log the impression."""
    folder = os.path.join(ADS_BASE, placement)
    if not os.path.exists(folder):
        return None
    
    # Load config to check disabled ads
    config_file = os.path.join(ADS_BASE, 'config.json')
    disabled = []
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
                disabled = config.get('disabled', {}).get(placement, [])
        except Exception:
            pass
    
    # Get all image files
    extensions = ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.webp', '*.JPG', '*.JPEG', '*.PNG']
    files = []
    for ext in extensions:
        files.extend(glob.glob(os.path.join(folder, ext)))
    
    # Filter out disabled and get active ads
    active = [os.path.basename(f) for f in files if os.path.basename(f) not in disabled]
    
    if active:
        selected_ad = random.choice(active)
        
        # Log the impression
        try:
            from .ad_events import log_impression
            from flask import session
            player_id = session.get('player_id')
            log_impression(
                placement=f'public_{placement}' if not placement.startswith('public') else placement,
                ad_filename=selected_ad,
                player_id=player_id
            )
        except Exception as e:
            # Don't break the page if logging fails
            pass
        
        return selected_ad
    return None

@public_bp.route('/scan')
def scan():
    """QR scan landing - redirects to join queue."""
    return redirect(url_for('public.join'))

@public_bp.route('/api/queue')
def api_queue():
    """Get current queue data."""
    queue = Queue.get_all()
    settings = get_settings()
    rules = get_game_rules()
    
    # Include ranked state for shot caller
    ranked_info = {}
    if queue and len(queue) >= 1:
        king = queue[0]
        ranked_info = {
            'ranked_request': king.get('ranked_request') == 1,
            'ranked_accepted': king.get('ranked_accepted'),
            'opponent_player_id': king.get('opponent_player_id')
        }
    
    response = jsonify({
        'queue': [{'id': q['id'], 'player_id': q.get('player_id'), 'nickname': q['nickname'], 
                   'partner_name': q.get('partner_name'), 'wins_on_table': q.get('wins_on_table', 0) or 0,
                   'position': i} for i, q in enumerate(queue, 1)],
        'settings': settings,
        'rules': rules,
        'bar_name': settings.get('bar_name', 'Test Bar'),
        'table_name': settings.get('table_name', 'Table 1'),
        'ranked': ranked_info
    })
    # Prevent caching so name changes show immediately
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@public_bp.route('/api/queue/join', methods=['POST'])
def api_queue_join():
    """Join queue via JSON API (for QR scan page)."""
    data = request.get_json() or {}
    
    nickname = (data.get('nickname') or '').strip()
    partner_name = (data.get('partner_name') or '').strip() or None
    bar_id = data.get('bar_id')
    table_id = data.get('table_id')
    
    if not nickname:
        return jsonify({'error': 'Name is required'}), 400
    
    # Get or default bar_id
    if not bar_id:
        settings = get_settings()
        bar_id = settings.get('bar_id', 1)
    
    # Find or create player
    player = Player.find_or_create(nickname, bar_id=bar_id)
    
    # Check if already in queue
    if Queue.is_player_in_queue(player['id'], bar_id=bar_id):
        return jsonify({'error': 'Already in queue at this bar'}), 400
    
    # Add to queue
    queue_id, session_token = Queue.add_player(player['id'], partner_name, bar_id=bar_id, table_id=table_id)
    
    # Set session so player can track their status
    session['player_id'] = player['id']
    session['player_nickname'] = nickname
    session['session_token'] = session_token
    # Mark as guest if player has no account_id (didn't sign up)
    if not player.get('account_id'):
        session['is_guest'] = True
    
    # IMPORTANT: Clear pending join flags since we just joined
    # This prevents double-joining if user later logs in
    session.pop('pending_join_bar_id', None)
    session.pop('pending_join_table_id', None)
    session.pop('pending_join_source', None)
    
    # Get position
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT COUNT(*) as pos FROM queue 
        WHERE bar_id = ? AND position <= (SELECT position FROM queue WHERE id = ?)
    ''', (bar_id, queue_id))
    position = cursor.fetchone()['pos']
    conn.close()
    
    # Estimate wait time (assume ~8 min per game)
    estimated_wait = max(0, (position - 2) * 8) if position > 2 else 0
    
    return jsonify({
        'success': True,
        'queue_id': queue_id,
        'position': position,
        'estimated_wait': estimated_wait,
        'session_token': session_token
    })

@public_bp.route('/share')
def share():
    """Shareable QR code page for beta testers."""
    bar_id = request.args.get('bar_id', type=int)
    
    # Build the share URL using request host for proper dev/prod support
    base_url = request.host_url.rstrip('/')
    if bar_id:
        share_url = f"{base_url}/q/{bar_id}"
    else:
        share_url = f"{base_url}/join"
    
    return render_template('public/share.html', share_url=share_url, bar_id=bar_id)


@public_bp.route('/join', methods=['GET'])
def join():
    """Redirect to the unified QR scan view for the appropriate bar."""
    bar_id = request.args.get('bar_id', 1, type=int)
    return redirect(url_for('public.qr_scan_view', bar_id=bar_id))

@public_bp.route('/join', methods=['POST'])
def join_post():
    """Handle queue join form submission - add player to queue."""
    nickname = request.form.get('nickname', '').strip()
    partner_name = request.form.get('partner_name', '').strip() or None
    phone_number = request.form.get('phone', '').strip() or None
    player_id = request.form.get('player_id')  # From logged-in user
    
    if not nickname:
        flash('Please enter your name', 'error')
        return redirect(url_for('public.join'))
    
    rules = get_current_rules()  # Uses scheduled rules
    if rules.get('game_type') == 'doubles' and not partner_name:
        flash('Doubles mode - enter partner name', 'error')
        return redirect(url_for('public.join'))
    
    # Determine bar_id from settings
    settings = get_settings()
    bar_id = settings.get('bar_id', 1)
    
    # Use logged-in player if available, otherwise find or create
    if player_id and 'player_id' in session and str(session['player_id']) == str(player_id):
        # Logged-in user - use their existing player record
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id, nickname, phone_number, account_id FROM players WHERE id = ?', (player_id,))
        player = cursor.fetchone()
        conn.close()
        if player:
            player = dict(player)
            # Log queue usage for logged-in user too (for tracking)
            if player.get('phone_number'):
                from .database import log_queue_usage
                log_queue_usage(
                    phone_number=player['phone_number'],
                    bar_id=bar_id,
                    player_id=player['id'],
                    nickname=player['nickname'],
                    has_account=player.get('account_id') is not None
                )
        else:
            player = Player.find_or_create(nickname, phone=phone_number, bar_id=bar_id)
    else:
        # Guest user - find or create player with phone tracking
        player = Player.find_or_create(nickname, phone=phone_number, bar_id=bar_id)
    
    if Queue.is_player_in_queue(player['id']):
        flash('Already in queue!', 'info')
        return redirect(url_for('public.my_status'))
    
    queue_id, session_token = Queue.add_player(player['id'], partner_name, bar_id=bar_id)
    session['session_token'] = session_token
    session['player_id'] = player['id']
    
    return redirect(url_for('public.my_status'))

@public_bp.route('/my-status')
def my_status():
    """Display player's current queue status and position."""
    session_token = session.get('session_token')
    player_id = session.get('player_id')
    
    # Try to find queue entry by session token or player_id
    entry = None
    if session_token:
        entry = Queue.get_by_session(session_token)
    
    # If no entry by session token, try by player_id
    if not entry and player_id:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT q.*, p.nickname, b.name as bar_name 
            FROM queue q 
            JOIN players p ON q.player_id = p.id
            LEFT JOIN bars b ON q.bar_id = b.id
            WHERE q.player_id = ? AND q.status IN ('waiting', 'playing')
            LIMIT 1
        """, (player_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            entry = dict(row)
            # Update session token
            session['session_token'] = entry['session_token']
    
    # If still no entry, show "not in queue" page
    if not entry:
        # Pass bar_id from session so user can return to QR scan page
        last_bar_id = session.get('pending_join_bar_id')
        return render_template('public/not_in_queue.html', bar_id=last_bar_id)
    
    # Auto-confirm if player views their status (proves they're present)
    if entry.get('sms_sent') and not entry.get('confirmed'):
        from .queue_confirmation import confirm_player_by_board
        confirm_player_by_board(entry['id'])
        entry['confirmed'] = 1  # Update local copy
    
    queue = Queue.get_all()
    rules = get_game_rules()
    
    position = next((i for i, q in enumerate(queue, 1) if q['id'] == entry['id']), 0)
    is_king = position == 1
    is_challenger = position == 2
    king = queue[0] if queue else None
    challenger = queue[1] if len(queue) > 1 else None
    
    # Get ranked status
    bar_id = entry.get('bar_id', 1)
    event_ranked, _, _ = check_ranked_requirement(bar_id)
    
    # Check for ranked request from shot caller (if we're the challenger)
    ranked_request = False
    ranked_accepted = None
    if is_challenger and king:
        ranked_request = king.get('ranked_request') == 1
        ranked_accepted = king.get('ranked_accepted')
        # If opponent player id doesn't match us, ignore
        if king.get('opponent_player_id') != entry.get('player_id'):
            ranked_request = False
    
    # Check if user has an actual account (not a guest)
    # Guests have is_guest=True in session
    has_account = False
    if 'player_id' in session and session.get('player_id'):
        if not session.get('is_guest'):
            # Not a guest - check if they have an account_id in database
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('SELECT account_id FROM players WHERE id = ?', (session['player_id'],))
            player_row = cursor.fetchone()
            conn.close()
            if player_row and player_row['account_id']:
                has_account = True
    
    return render_template('public/player_status.html',
        entry=entry, position=position, is_king=is_king, is_challenger=is_challenger,
        king=king, challenger=challenger, queue=queue, rules=rules,
        ranked_request=ranked_request, ranked_accepted=ranked_accepted, event_ranked=event_ranked,
        has_account=has_account
    )


@public_bp.route('/api/king-wins', methods=['POST'])
def api_king_wins():
    """King wins - swipe challenger off."""
    data = request.json or {}
    bar_id = data.get('bar_id') or request.args.get('bar_id')
    if bar_id:
        bar_id = int(bar_id)
    
    if Queue.king_wins(bar_id=bar_id):
        on_game_end()  # Request confirmation from new challenger
        return jsonify({'success': True})
    return jsonify({'error': 'Need king and challenger'}), 400

@public_bp.route('/api/challenger-wins', methods=['POST'])
def api_challenger_wins():
    """Challenger wins - swipe king off."""
    data = request.json or {}
    bar_id = data.get('bar_id') or request.args.get('bar_id')
    if bar_id:
        bar_id = int(bar_id)
    
    if Queue.challenger_wins(bar_id=bar_id):
        on_game_end()  # Request confirmation from new position 1 and 2
        return jsonify({'success': True})
    return jsonify({'error': 'Need king and challenger'}), 400

@public_bp.route('/api/set-rules', methods=['POST'])
def api_set_rules():
    """Only king can set rules."""
    session_token = session.get('session_token')
    if not session_token:
        return jsonify({'error': 'Not authenticated'}), 401
    
    entry = Queue.get_by_session(session_token)
    queue = Queue.get_all()
    
    if not queue or entry['id'] != queue[0]['id']:
        return jsonify({'error': 'Only king can set rules'}), 403
    
    data = request.json or {}
    set_game_rules(data.get('rule_type', 'bar_rules'), data.get('game_type', 'singles'),
                   data.get('custom_note', ''), entry['player_id'])
    return jsonify({'success': True})

@public_bp.route('/api/leave', methods=['POST'])
def api_leave():
    """Leave queue - API version for AJAX calls."""
    session_token = session.get('session_token')
    player_id = session.get('player_id')
    
    if session_token:
        Queue.leave_queue(session_token)
        session.pop('session_token', None)
        return jsonify({'success': True})
    elif player_id:
        # Try to find and remove by player_id for logged-in players
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT session_token FROM queue 
            WHERE player_id = ? AND status IN ('waiting', 'playing')
            LIMIT 1
        """, (player_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            Queue.leave_queue(row['session_token'])
            return jsonify({'success': True})
    
    return jsonify({'success': True})  # Return success even if not in queue

@public_bp.route('/leave-queue', methods=['POST'])
def leave_queue():
    """Leave queue - form POST version for my_status.html."""
    session_token = session.get('session_token')
    player_id = session.get('player_id')
    
    if session_token:
        Queue.leave_queue(session_token)
        session.pop('session_token', None)
    elif player_id:
        # Try to find and remove by player_id
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT session_token FROM queue 
            WHERE player_id = ? AND status IN ('waiting', 'playing')
            LIMIT 1
        """, (player_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            Queue.leave_queue(row['session_token'])
    
    # Redirect to player home or not_in_queue
    if player_id:
        return redirect(url_for('player.home'))
    return redirect(url_for('public.join'))

@public_bp.route('/api/undo', methods=['POST'])
def api_undo():
    """Undo the last player removal from queue."""
    result = Queue.undo_last_removal()
    if result:
        return jsonify({'success': True, 'restored': result['player_nickname']})
    return jsonify({'error': 'Nothing to undo'}), 400


# ============================================
# QUEUE CONFIRMATION SYSTEM
# ============================================

@public_bp.route('/api/confirm-ready', methods=['POST'])
def api_confirm_ready():
    """Player confirms they're ready to play."""
    player_id = session.get('player_id')
    session_token = session.get('session_token')
    
    if not player_id and not session_token:
        return jsonify({'error': 'Not in queue'}), 401
    
    success = confirm_ready(player_id=player_id, session_token=session_token)
    
    if success:
        return jsonify({'success': True, 'message': 'Ready confirmed!'})
    return jsonify({'error': 'Could not confirm - not in queue'}), 400


@public_bp.route('/api/queue/check-timeouts', methods=['POST'])
def api_check_timeouts():
    """Check and enforce confirmation timeouts. Called periodically by display board."""
    actions = check_and_enforce_timeouts()
    return jsonify({
        'success': True,
        'actions': actions,
        'actions_taken': len(actions)
    })


@public_bp.route('/api/queue/confirmation-status')
def api_confirmation_status():
    """Get queue with confirmation status for each player."""
    queue = get_queue_with_confirmation_status()
    
    # Also run timeout check
    actions = check_and_enforce_timeouts()
    
    # If actions were taken, refresh queue data
    if actions:
        queue = get_queue_with_confirmation_status()
    
    return jsonify({
        'queue': queue,
        'confirm_timeout_seconds': CONFIRM_TIMEOUT_SECONDS,
        'removal_timeout_seconds': REMOVAL_TIMEOUT_SECONDS,
        'recent_actions': actions
    })


@public_bp.route('/api/queue/my-status')
def api_my_queue_status():
    """
    Get current player's queue status including confirmation needs.
    
    Confirmation Logic:
    - Position 1 (Shot Caller): Never needs to confirm
    - Position 2 (Challenger): Never needs to confirm
    - Position 3 (Next Up): ONLY one who needs to confirm
    - Position 4+: No confirmation needed
    """
    player_id = session.get('player_id')
    session_token = session.get('session_token')
    
    if not player_id and not session_token:
        return jsonify({'in_queue': False})
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Find player's queue entry
    if player_id:
        cursor.execute('''
            SELECT q.*, p.nickname,
                   (SELECT COUNT(*) FROM queue q2 WHERE q2.id < q.id) + 1 as position
            FROM queue q
            JOIN players p ON q.player_id = p.id
            WHERE q.player_id = ?
        ''', (player_id,))
    else:
        cursor.execute('''
            SELECT q.*, p.nickname,
                   (SELECT COUNT(*) FROM queue q2 WHERE q2.id < q.id) + 1 as position
            FROM queue q
            JOIN players p ON q.player_id = p.id
            WHERE q.session_token = ?
        ''', (session_token,))
    
    entry = cursor.fetchone()
    conn.close()
    
    if not entry:
        return jsonify({'in_queue': False})
    
    entry = dict(entry)
    position = entry['position']
    
    # Calculate time remaining
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # UTC to match SQLite datetime('now')
    
    confirm_remaining = None
    removal_remaining = None
    
    # ONLY position 3 (next up) needs to confirm
    # Positions 1-2 are already playing, positions 4+ wait their turn
    is_next_up = position == 3
    needs_confirmation = is_next_up and entry['needs_confirmation'] and not entry['confirmed']
    
    if needs_confirmation and entry['confirmation_requested_at']:
        requested_at = datetime.strptime(entry['confirmation_requested_at'], '%Y-%m-%d %H:%M:%S')
        elapsed = (now - requested_at).total_seconds()
        confirm_remaining = max(0, CONFIRM_TIMEOUT_SECONDS - elapsed)
    
    if entry['pushed_down_at'] and not entry['confirmed']:
        pushed_at = datetime.strptime(entry['pushed_down_at'], '%Y-%m-%d %H:%M:%S')
        elapsed = (now - pushed_at).total_seconds()
        removal_remaining = max(0, REMOVAL_TIMEOUT_SECONDS - elapsed)
    
    # Determine role
    if position == 1:
        role = 'shot_caller'
    elif position == 2:
        role = 'challenger'
    elif position == 3:
        role = 'next_up'
    else:
        role = 'waiting'
    
    return jsonify({
        'in_queue': True,
        'position': position,
        'role': role,
        'needs_confirmation': needs_confirmation,
        'confirmed': bool(entry['confirmed']),
        'confirm_seconds_remaining': confirm_remaining if needs_confirmation else None,
        'removal_seconds_remaining': removal_remaining,
        'pushed_down': bool(entry['pushed_down_at']),
        'push_count': entry['push_count'] or 0
    })


@public_bp.route('/api/player-app-data')
def api_player_app_data():
    """
    Comprehensive data endpoint for player app soft refresh.
    Returns full queue state so the app can update without page reload.
    """
    player_id = session.get('player_id')
    session_token = session.get('session_token')
    bar_id = session.get('bar_id')
    
    if not player_id and not session_token:
        return jsonify({'in_queue': False})
    
    # Get full queue
    if bar_id:
        queue = Queue.get_all_for_bar(bar_id)
    else:
        queue = Queue.get_all()
    
    # Find this player's position
    my_position = None
    my_entry = None
    for i, entry in enumerate(queue):
        if (player_id and entry.get('player_id') == player_id) or \
           (session_token and entry.get('session_token') == session_token):
            my_position = i + 1
            my_entry = entry
            break
    
    if not my_entry:
        return jsonify({'in_queue': False})
    
    # Build queue list for display (excluding king/challenger)
    king = queue[0] if queue else None
    challenger = queue[1] if len(queue) > 1 else None
    queue_list = []
    for i, p in enumerate(queue[2:], start=3):
        queue_list.append({
            'position': i,
            'nickname': p.get('nickname', 'Player'),
            'partner_name': p.get('partner_name'),
            'player_id': p.get('player_id'),
            'confirmed': bool(p.get('confirmed')),
            'is_me': (player_id and p.get('player_id') == player_id) or \
                     (session_token and p.get('session_token') == session_token)
        })
    
    # Determine role
    if my_position == 1:
        role = 'shot_caller'
    elif my_position == 2:
        role = 'challenger'
    elif my_position == 3:
        role = 'next_up'
    else:
        role = 'waiting'
    
    return jsonify({
        'in_queue': True,
        'position': my_position,
        'role': role,
        'confirmed': bool(my_entry.get('confirmed')),
        'king': {
            'nickname': king.get('nickname') if king else None,
            'partner_name': king.get('partner_name') if king else None,
            'wins_on_table': king.get('wins_on_table', 0) if king else 0
        } if king else None,
        'challenger': {
            'nickname': challenger.get('nickname') if challenger else None,
            'partner_name': challenger.get('partner_name') if challenger else None
        } if challenger else None,
        'queue_list': queue_list,
        'total_in_queue': len(queue)
    })


@public_bp.route('/api/confirm-player/<int:player_id>', methods=['POST'])
def api_confirm_player(player_id):
    """Shot caller can confirm another player who forgot to confirm."""
    session_token = session.get('session_token')
    requester_player_id = session.get('player_id')
    
    if not session_token and not requester_player_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    # Check if requester is the shot caller (position 1)
    queue = Queue.get_all()
    if not queue:
        return jsonify({'error': 'Queue is empty'}), 400
    
    # Allow either session token match or player_id match to verify shot caller
    is_shot_caller = False
    if session_token:
        requester_entry = Queue.get_by_session(session_token)
        if requester_entry and requester_entry['id'] == queue[0]['id']:
            is_shot_caller = True
    
    if not is_shot_caller and requester_player_id:
        if queue[0].get('player_id') == requester_player_id:
            is_shot_caller = True
    
    if not is_shot_caller:
        return jsonify({'error': 'Only the Shot Caller can confirm other players'}), 403
    
    # Confirm the specified player
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE queue SET 
            confirmed = 1, 
            needs_confirmation = 0,
            pushed_down_at = NULL,
            push_count = 0
        WHERE player_id = ?
    ''', (player_id,))
    
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({'error': 'Player not found in queue'}), 404
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Player confirmed by Shot Caller'})


@public_bp.route('/api/request-ranked', methods=['POST', 'DELETE'])
def api_request_ranked():
    """Shot caller requests or cancels a ranked match."""
    from .database import request_ranked_match, check_ranked_requirement
    
    player_id = session.get('player_id')
    if not player_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    queue = Queue.get_all()
    if not queue:
        return jsonify({'error': 'Queue is empty'}), 400
    
    # Verify requester is shot caller
    if queue[0].get('player_id') != player_id:
        return jsonify({'error': 'Only the Shot Caller can manage ranked matches'}), 403
    
    shot_caller_queue_id = queue[0]['id']
    
    # Handle DELETE - cancel ranked request
    if request.method == 'DELETE':
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE queue SET ranked_request = 0, ranked_accepted = NULL, opponent_player_id = NULL
            WHERE id = ?
        ''', (shot_caller_queue_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Ranked request cancelled'})
    
    # POST - request ranked match
    # Check if there's a challenger
    if len(queue) < 2:
        return jsonify({'error': 'No challenger to play against'}), 400
    
    challenger = queue[1]
    bar_id = queue[0].get('bar_id', 1)
    
    # Check if already in a ranked-required window
    is_event_ranked, _, info = check_ranked_requirement(bar_id)
    if is_event_ranked:
        return jsonify({
            'success': True, 
            'auto_ranked': True,
            'message': f'Match is automatically ranked: {info}'
        })
    
    # Check if challenger has an account
    challenger_player_id = challenger.get('player_id')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT account_id FROM players WHERE id = ?', (challenger_player_id,))
    challenger_data = cursor.fetchone()
    conn.close()
    
    has_account = challenger_data and challenger_data['account_id']
    
    if not has_account:
        return jsonify({
            'success': False,
            'message': 'Opponent does not have an account. Ranked matches require both players to have accounts.'
        })
    
    # Request ranked match
    request_ranked_match(shot_caller_queue_id, challenger_player_id)
    
    return jsonify({
        'success': True,
        'pending': True,
        'message': 'Ranked match requested. Waiting for opponent to accept.'
    })


@public_bp.route('/api/respond-ranked', methods=['POST'])
def api_respond_ranked():
    """Opponent responds to a ranked match request."""
    from .database import respond_ranked_request, get_pending_ranked_request
    
    player_id = session.get('player_id')
    if not player_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.json or {}
    accept = data.get('accept', False)
    
    # Find the pending request for this player
    pending = get_pending_ranked_request(player_id)
    if not pending:
        return jsonify({'error': 'No pending ranked request found'}), 404
    
    respond_ranked_request(pending['id'], accept)
    
    return jsonify({
        'success': True,
        'accepted': accept,
        'message': 'Ranked match accepted!' if accept else 'Match will be unranked.'
    })


@public_bp.route('/api/ranked-status')
def api_ranked_status():
    """Get current ranked status for the active game."""
    from .database import check_ranked_requirement, get_pending_ranked_request
    
    player_id = session.get('player_id')
    queue = Queue.get_all()
    
    if not queue:
        return jsonify({'queue_empty': True})
    
    bar_id = queue[0].get('bar_id', 1)
    
    # Check event-based ranking
    is_event_ranked, source, info = check_ranked_requirement(bar_id)
    
    response = {
        'is_event_ranked': is_event_ranked,
        'ranked_source': source,
        'ranked_info': info,
        'pending_request': None
    }
    
    # Check for pending ranked request for this player
    if player_id:
        pending = get_pending_ranked_request(player_id)
        if pending:
            response['pending_request'] = {
                'from': pending['shot_caller_name'],
                'queue_id': pending['id']
            }
    
    # If shot caller, check if they have a pending request
    if player_id and len(queue) > 0 and queue[0].get('player_id') == player_id:
        shot_caller = queue[0]
        if shot_caller.get('ranked_request') == 1:
            response['my_request_pending'] = shot_caller.get('ranked_accepted') is None
            response['my_request_accepted'] = shot_caller.get('ranked_accepted') == 1
    
    return jsonify(response)


@public_bp.route('/api/report-player', methods=['POST'])
def api_report_player():
    """Report a player for misconduct."""
    data = request.json or {}
    reported_player_id = data.get('player_id')
    reason = data.get('reason')
    details = data.get('details', '')
    
    if not reported_player_id or not reason:
        return jsonify({'error': 'Player ID and reason required'}), 400
    
    valid_reasons = [
        'unsportsmanlike',
        'harassment', 
        'cheating',
        'no_show',
        'rating_manipulation',
        'inappropriate_behavior',
        'fake_account',
        'intoxication',
        'other'
    ]
    
    if reason not in valid_reasons:
        return jsonify({'error': 'Invalid reason'}), 400
    
    reporter_id = session.get('player_id')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if reported player exists
    cursor.execute('SELECT id, nickname FROM players WHERE id = ?', (reported_player_id,))
    reported_player = cursor.fetchone()
    if not reported_player:
        conn.close()
        return jsonify({'error': 'Player not found'}), 404
    
    # Insert report
    cursor.execute('''
        INSERT INTO player_reports (reporter_id, reported_player_id, reason, details, created_at)
        VALUES (?, ?, ?, ?, datetime('now'))
    ''', (reporter_id, reported_player_id, reason, details))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True, 
        'message': 'Report submitted. Thank you for helping keep Pool Cue fair and fun.'
    })


@public_bp.route('/report/<int:player_id>')
def report_player_page(player_id):
    """Page to report a player."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, nickname FROM players WHERE id = ?', (player_id,))
    player = cursor.fetchone()
    conn.close()
    
    if not player:
        return redirect(url_for('public.join'))
    
    return render_template('player/report_player.html', player=dict(player))

@public_bp.route('/api/queue-status')
def api_queue_status():
    """API endpoint to get current queue status for live updates."""
    queue = Queue.get_all()
    rules = get_game_rules()
    last_removal = get_last_removal()
    avg_time = get_average_game_time()
    
    return jsonify({
        'queue': [{'id': q['id'], 'nickname': q['nickname'], 'partner_name': q.get('partner_name'),
                   'wins_on_table': q.get('wins_on_table', 0) or 0, 'position': i
                  } for i, q in enumerate(queue, 1)],
        'rules': rules,
        'can_undo': last_removal is not None,
        'last_removed': last_removal['player_nickname'] if last_removal else None,
        'avg_game_seconds': avg_time
    })

@public_bp.route('/join/confirm')
def join_confirm():
    """Redirect to status page after joining queue."""
    return redirect(url_for('public.my_status'))

@public_bp.route('/player-demo')
def player_demo():
    """Demo player status page for developer view."""
    return render_template('player/player_demo.html')


@public_bp.route('/api/table/rules', methods=['POST'])
def api_table_rules():
    """Update table rules (singles/doubles and APA/BCA/Bar). When switching to singles, drop partners."""
    data = request.json or {}
    new_type = data.get('rules', 'singles')
    rules_type = data.get('rulesType', 'bar')  # APA, BCA, or bar
    
    # Map rulesType to rule_type format
    rule_type_map = {'bar': 'bar_rules', 'apa': 'apa', 'bca': 'bca'}
    rule_type = rule_type_map.get(rules_type, 'bar_rules')
    
    # Get current rules
    current_rules = get_game_rules()
    old_type = current_rules.get('game_type', 'singles')
    
    # If switching from doubles to singles, drop partners from queue entries
    if old_type == 'doubles' and new_type == 'singles':
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('UPDATE queue SET partner_name = NULL WHERE partner_name IS NOT NULL')
            conn.commit()
            conn.close()
        except Exception:
            pass
    
    # Update game rules
    set_game_rules(
        rule_type,
        new_type,
        current_rules.get('custom_note', ''),
        None
    )
    
    return jsonify({'success': True, 'game_type': new_type, 'rule_type': rule_type})


@public_bp.route('/api/table/permanent', methods=['POST'])
def api_table_permanent():
    """Toggle permanent/locked rules (bar controls only vs shot caller can change)."""
    data = request.json or {}
    permanent = data.get('permanent', False)
    
    # Store in settings
    from .database import update_settings
    update_settings(permanent_rules=permanent)
    
    return jsonify({'success': True, 'permanent': permanent})


# ============================================
# APP LAUNCHERS
# ============================================

@public_bp.route('/apps')
def apps_hub():
    """Redirect legacy apps hub to master dashboard."""
    return redirect('/master')

# NOTE: /app/board and /app/player are now handled by routes_apps.py
# Keeping /app/bar as legacy route for now

@public_bp.route('/app/bar')
def app_bar():
    """Bar Manager app launcher with phone preview (legacy route)."""
    return render_template('apps/app_bar.html')

# NOTE: /app/analytics is now handled by routes_apps.py (renders app_analytics.html)


# ============================================
# TABLE-SPECIFIC QR CODE ROUTES
# ============================================

@public_bp.route('/t/<table_token>')
def table_qr_scan(table_token):
    """
    Table-specific QR code scan view.
    Each table has a unique token for its QR code.
    This is the preferred method for table-specific scanning.
    """
    from .database import get_db, get_table_by_token, log_queue_usage
    
    table = get_table_by_token(table_token)
    
    if not table:
        return "Table not found or inactive", 404
    
    bar_id = table['bar_id']
    table_id = table['id']
    
    conn = get_db()
    cursor = conn.cursor()
    
    # If user is logged in, auto-join them to the queue
    player_id = session.get('player_id')
    if player_id:
        # Check if already in queue at this bar
        if not Queue.is_player_in_queue(player_id, bar_id=bar_id):
            # Join them to the queue
            queue_id, session_token = Queue.add_player(player_id, partner_name=None, 
                                                        bar_id=bar_id, table_id=table_id)
            session['session_token'] = session_token
            
            # Log analytics
            cursor.execute('SELECT phone_number, nickname FROM players WHERE id = ?', (player_id,))
            player_row = cursor.fetchone()
            if player_row and player_row['phone_number']:
                log_queue_usage(
                    phone_number=player_row['phone_number'],
                    bar_id=bar_id,
                    player_id=player_id,
                    nickname=player_row['nickname'],
                    has_account=True
                )
        
        conn.close()
        # Redirect to status page
        return redirect(url_for('public.my_status'))
    
    # Not logged in - set pending join flags for auto-join after login/signup
    session['pending_join_bar_id'] = bar_id
    session['pending_join_table_id'] = table_id
    session['pending_join_source'] = 'qr'
    
    # Get queue count for this specific table
    cursor.execute('SELECT COUNT(*) FROM queue WHERE bar_id = ? AND (table_id = ? OR table_id IS NULL)', (bar_id, table_id))
    queue_count = cursor.fetchone()[0] or 0
    
    # Get queue entries for this table
    cursor.execute('''
        SELECT q.*, p.nickname as player_name
        FROM queue q
        LEFT JOIN players p ON q.player_id = p.id
        WHERE q.bar_id = ? AND (q.table_id = ? OR q.table_id IS NULL)
        ORDER BY q.position ASC
    ''', (bar_id, table_id))
    queue = [dict(row) for row in cursor.fetchall()]
    
    # Get ranked info from shot caller for initial render
    ranked_info = {}
    if queue and len(queue) >= 1:
        king = queue[0]
        ranked_info = {
            'ranked_request': king.get('ranked_request') == 1,
            'ranked_accepted': king.get('ranked_accepted'),
            'opponent_player_id': king.get('opponent_player_id')
        }
    
    conn.close()
    
    bar_data = {
        'id': bar_id,
        'name': table['bar_name']
    }
    
    table_data = {
        'id': table_id,
        'table_number': table['table_number'],
        'table_name': table['table_name'] or f"Table {table['table_number']}",
        'token': table_token
    }
    
    return render_template('public/qr_view.html', 
                           bar_id=bar_id,
                           bar=bar_data,
                           table=table_data,
                           queue_count=queue_count,
                           queue=queue,
                           ranked=ranked_info)


@public_bp.route('/q/<int:bar_id>/<int:table_id>')
def qr_scan_view_with_table(bar_id, table_id):
    """
    Bar + Table specific QR scan view.
    Alternative to token-based routing.
    """
    from .database import get_db, get_table_by_id, log_queue_usage
    
    table = get_table_by_id(table_id)
    
    if not table or table['bar_id'] != bar_id:
        return "Table not found", 404
    
    conn = get_db()
    cursor = conn.cursor()
    
    # If user is logged in, auto-join them to the queue
    player_id = session.get('player_id')
    if player_id:
        # Check if already in queue at this bar
        if not Queue.is_player_in_queue(player_id, bar_id=bar_id):
            # Join them to the queue
            queue_id, session_token = Queue.add_player(player_id, partner_name=None, 
                                                        bar_id=bar_id, table_id=table_id)
            session['session_token'] = session_token
            
            # Log analytics
            cursor.execute('SELECT phone_number, nickname FROM players WHERE id = ?', (player_id,))
            player_row = cursor.fetchone()
            if player_row and player_row['phone_number']:
                log_queue_usage(
                    phone_number=player_row['phone_number'],
                    bar_id=bar_id,
                    player_id=player_id,
                    nickname=player_row['nickname'],
                    has_account=True
                )
        
        conn.close()
        # Redirect to status page
        return redirect(url_for('public.my_status'))
    
    # Not logged in - set pending join flags for auto-join after login/signup
    session['pending_join_bar_id'] = bar_id
    session['pending_join_table_id'] = table_id
    session['pending_join_source'] = 'qr'
    
    # Get queue count for this specific table
    cursor.execute('SELECT COUNT(*) FROM queue WHERE bar_id = ? AND (table_id = ? OR table_id IS NULL)', (bar_id, table_id))
    queue_count = cursor.fetchone()[0] or 0
    
    # Get queue entries for this table
    cursor.execute('''
        SELECT q.*, p.nickname as player_name
        FROM queue q
        LEFT JOIN players p ON q.player_id = p.id
        WHERE q.bar_id = ? AND (q.table_id = ? OR q.table_id IS NULL)
        ORDER BY q.position ASC
    ''', (bar_id, table_id))
    queue = [dict(row) for row in cursor.fetchall()]
    
    # Get ranked info from shot caller for initial render
    ranked_info = {}
    if queue and len(queue) >= 1:
        king = queue[0]
        ranked_info = {
            'ranked_request': king.get('ranked_request') == 1,
            'ranked_accepted': king.get('ranked_accepted'),
            'opponent_player_id': king.get('opponent_player_id')
        }
    
    conn.close()
    
    bar_data = {
        'id': bar_id,
        'name': table['bar_name']
    }
    
    table_data = {
        'id': table_id,
        'table_number': table['table_number'],
        'table_name': table['table_name'] or f"Table {table['table_number']}",
        'token': table['qr_code_token']
    }
    
    return render_template('public/qr_view.html', 
                           bar_id=bar_id,
                           bar=bar_data,
                           table=table_data,
                           queue_count=queue_count,
                           queue=queue,
                           ranked=ranked_info)


# ============================================
# QR CODE SCAN VIEW (Public - No Account Required)
# ============================================

@public_bp.route('/q/<int:bar_id>')
def qr_scan_view(bar_id):
    """
    Unified QR code scan view - what people see when they scan QR at bar.
    Shows queue + shot caller tabs. If logged in, auto-joins them.
    """
    from .database import get_db, log_queue_usage
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get bar info
    cursor.execute('SELECT id, name FROM bars WHERE id = ?', (bar_id,))
    bar = cursor.fetchone()
    
    if not bar:
        conn.close()
        return "Bar not found", 404
    
    bar_data = dict(bar)
    
    # If user is logged in, auto-join them to the queue
    player_id = session.get('player_id')
    if player_id:
        # Check if already in queue at this bar
        if not Queue.is_player_in_queue(player_id, bar_id=bar_id):
            # Join them to the queue
            queue_id, session_token = Queue.add_player(player_id, partner_name=None, 
                                                        bar_id=bar_id, table_id=None)
            session['session_token'] = session_token
            
            # Log analytics
            cursor.execute('SELECT phone_number, nickname FROM players WHERE id = ?', (player_id,))
            player_row = cursor.fetchone()
            if player_row and player_row['phone_number']:
                log_queue_usage(
                    phone_number=player_row['phone_number'],
                    bar_id=bar_id,
                    player_id=player_id,
                    nickname=player_row['nickname'],
                    has_account=True
                )
        
        conn.close()
        # Redirect to status page
        return redirect(url_for('public.my_status'))
    
    # Not logged in - set pending join flags for auto-join after login/signup
    session['pending_join_bar_id'] = bar_id
    session['pending_join_table_id'] = None
    session['pending_join_source'] = 'qr'
    
    # Get queue count
    cursor.execute('SELECT COUNT(*) FROM queue WHERE bar_id = ?', (bar_id,))
    queue_count = cursor.fetchone()[0] or 0
    
    # Get queue entries
    cursor.execute('''
        SELECT q.*, p.nickname as player_name
        FROM queue q
        LEFT JOIN players p ON q.player_id = p.id
        WHERE q.bar_id = ?
        ORDER BY q.position ASC
    ''', (bar_id,))
    queue = [dict(row) for row in cursor.fetchall()]
    
    # Get ranked info from shot caller for initial render
    ranked_info = {}
    if queue and len(queue) >= 1:
        king = queue[0]
        ranked_info = {
            'ranked_request': king.get('ranked_request') == 1,
            'ranked_accepted': king.get('ranked_accepted'),
            'opponent_player_id': king.get('opponent_player_id')
        }
    
    conn.close()
    
    return render_template('public/qr_view.html', 
                           bar_id=bar_id, 
                           bar=bar_data,
                           queue_count=queue_count,
                           queue=queue,
                           ranked=ranked_info)

# Legacy routes redirect to new unified view
@public_bp.route('/queue/<int:bar_id>')
def public_queue(bar_id):
    """Legacy route - redirect to unified QR scan view."""
    return redirect(url_for('public.qr_scan_view', bar_id=bar_id))

@public_bp.route('/shot-caller/<int:bar_id>')
def public_shot_caller(bar_id):
    """Legacy route - redirect to unified QR scan view."""
    return redirect(url_for('public.qr_scan_view', bar_id=bar_id))

@public_bp.route('/visitor/bar/<int:bar_id>')
def visitor_bar(bar_id):
    """Legacy route - redirect to unified QR scan view."""
    return redirect(url_for('public.qr_scan_view', bar_id=bar_id))

@public_bp.route('/visitor/shot-caller/<int:bar_id>')
def visitor_shot_caller(bar_id):
    """Legacy route - redirect to unified QR scan view."""
    return redirect(url_for('public.qr_scan_view', bar_id=bar_id))


# ============================================
# PWA MANIFEST & SERVICE WORKER
# ============================================

@public_bp.route('/manifest.json')
def manifest():
    """PWA manifest for Add to Home Screen."""
    return jsonify({
        "name": "Pool Cue",
        "short_name": "Pool Cue",
        "description": "Track pool games, earn tokens, challenge friends",
        "start_url": "/player/home",
        "display": "standalone",
        "background_color": "#111111",
        "theme_color": "#111111",
        "orientation": "portrait",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"}
        ]
    }), {'Content-Type': 'application/json'}


@public_bp.route('/sw.js')
def service_worker():
    """Service worker for PWA."""
    js = '''
const CACHE = 'pool-cue-v1';
const ASSETS = ['/player/home', '/auth/signup', '/join'];

self.addEventListener('install', e => {
    e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)));
});

self.addEventListener('fetch', e => {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});

self.addEventListener('push', e => {
    const data = e.data ? e.data.json() : {};
    self.registration.showNotification(data.title || 'Pool Cue', {
        body: data.body || "You're up next!",
        icon: '/static/icon-192.png',
        badge: '/static/icon-192.png'
    });
});
'''
    return js, {'Content-Type': 'application/javascript'}


# ============ BUG REPORTS ============

@public_bp.route('/api/bug-report', methods=['POST'])
def api_submit_bug_report():
    """Submit a bug report."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Ensure bug_reports table exists
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bug_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER,
            bug_type TEXT,
            description TEXT NOT NULL,
            page TEXT,
            email TEXT,
            user_agent TEXT,
            screen_size TEXT,
            url TEXT,
            status TEXT DEFAULT 'new',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            resolved_at DATETIME,
            resolution_notes TEXT
        )
    ''')
    
    # Get form data
    bug_type = request.form.get('bug_type', 'other')
    description = request.form.get('description', '').strip()
    page = request.form.get('page', '')
    email = request.form.get('email', '')
    player_id = request.form.get('player_id') or session.get('player_id')
    user_agent = request.form.get('user_agent', '')
    screen_size = request.form.get('screen_size', '')
    url = request.form.get('url', '')
    
    if not description:
        return jsonify({'success': False, 'error': 'Please describe the issue'}), 400
    
    cursor.execute('''
        INSERT INTO bug_reports (player_id, bug_type, description, page, email, user_agent, screen_size, url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (player_id, bug_type, description, page, email, user_agent, screen_size, url))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Bug report submitted. Thank you!'})
