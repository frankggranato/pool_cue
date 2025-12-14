"""
Board Control Routes - Anti-tampering system for queue/match management.

Server is the source of truth. Board is just a display/control surface.
Ranked and paid matches have extra protection and audit logging.
"""
from flask import Blueprint, render_template, request, jsonify, session
from functools import wraps
from .database import (
    get_db, get_settings,
    validate_board_session, create_board_session, revoke_board_session,
    create_active_match, get_active_match, record_match_result,
    confirm_match_result, cancel_active_match, log_match_action,
    get_match_audit_log, get_pending_confirmations,
    check_ranked_requirement, determine_match_ranked_status
)
from .models import Queue

board_bp = Blueprint('board', __name__, url_prefix='/board')


def get_request_info():
    """Get IP and user agent for audit logging."""
    return {
        'ip_address': request.remote_addr,
        'user_agent': request.headers.get('User-Agent', '')[:500]
    }


def require_board_auth(f):
    """Decorator requiring authorized board session for control actions."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Check for board session token
        board_token = request.headers.get('X-Board-Token') or request.cookies.get('board_session')
        bar_id = kwargs.get('bar_id') or request.args.get('bar_id') or request.json.get('bar_id') if request.is_json else None
        
        board_session = validate_board_session(board_token, bar_id)
        
        if not board_session or not board_session.get('can_control'):
            return jsonify({'error': 'Unauthorized - valid board session required', 'code': 'AUTH_REQUIRED'}), 401
        
        # Attach session to request context
        request.board_session = board_session
        return f(*args, **kwargs)
    return decorated


def require_host_auth(f):
    """Decorator requiring bar host/staff authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Check for logged in user who is a bar host
        user_id = session.get('player_id') or session.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'Authentication required', 'code': 'LOGIN_REQUIRED'}), 401
        
        # TODO: Check if user is bar host/staff for this bar
        # For now, any logged in user can act as host
        request.host_user_id = user_id
        return f(*args, **kwargs)
    return decorated


# ============================================
# READ-ONLY DISPLAY ROUTES (No auth required)
# ============================================

@board_bp.route('/state/<int:bar_id>')
def get_board_state(bar_id):
    """
    Get current board state from server (source of truth).
    This is READ-ONLY - anyone can view, but only authorized sessions can control.
    Board should poll this to stay in sync with server.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Get queue from database
    cursor.execute('''
        SELECT q.*, p.nickname, p.id as player_id
        FROM queue q 
        JOIN players p ON q.player_id = p.id 
        WHERE q.bar_id = ? AND q.status IN ('waiting', 'playing')
        ORDER BY q.position ASC
    ''', (bar_id,))
    queue = [dict(row) for row in cursor.fetchall()]
    
    # If no bar_id filter, get all queue entries (legacy support)
    if not queue:
        cursor.execute('''
            SELECT q.*, p.nickname, p.id as player_id
            FROM queue q 
            JOIN players p ON q.player_id = p.id 
            WHERE q.status IN ('waiting', 'playing')
            ORDER BY q.position ASC
        ''')
        queue = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    # Get active match if any
    active_match = get_active_match(bar_id)
    
    # Get ranked status
    is_event_ranked, ranked_source, ranked_info = check_ranked_requirement(bar_id)
    
    # Determine king and challenger
    king = queue[0] if queue else None
    challenger = queue[1] if len(queue) > 1 else None
    waiting = queue[2:] if len(queue) > 2 else []
    
    # Check if current match is ranked (event or player-requested)
    match_is_ranked = is_event_ranked
    if king and not match_is_ranked:
        is_ranked, source = determine_match_ranked_status(bar_id, king['id'])
        match_is_ranked = is_ranked
    
    return jsonify({
        'queue': queue,
        'king': king,
        'challenger': challenger,
        'waiting': waiting,
        'active_match': active_match,
        'ranked_status': {
            'is_event_ranked': is_event_ranked,
            'match_is_ranked': match_is_ranked,
            'ranked_source': ranked_source,
            'ranked_info': ranked_info
        },
        'queue_count': len(queue),
        'server_time': str(datetime.now())
    })


@board_bp.route('/display/<int:bar_id>')
def display_board_readonly(bar_id):
    """
    Read-only display view for TVs/monitors.
    No control buttons - just shows queue state from server.
    Refreshes from server periodically.
    """
    return render_template('board/display_readonly.html', bar_id=bar_id)


@board_bp.route('/tournament/<int:night_id>')
def tournament_display(night_id):
    """
    Public tournament bracket display for TVs/monitors.
    Shows live bracket with auto-refresh during active tournaments.
    """
    from .database import get_tournament_bracket, get_tournament_participants, get_db
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get pool night info
    cursor.execute('''
        SELECT pn.*, b.name as bar_name
        FROM pool_nights pn
        LEFT JOIN bars b ON pn.bar_id = b.id
        WHERE pn.id = ? AND pn.format = 'tournament'
    ''', (night_id,))
    night = cursor.fetchone()
    
    if not night:
        conn.close()
        return "Tournament not found", 404
    
    night = dict(night)
    
    # Get champion if tournament is complete
    champion = None
    if night['tournament_status'] == 'completed':
        cursor.execute('''
            SELECT p.* FROM tournament_participants tp
            JOIN players p ON tp.player_id = p.id
            WHERE tp.pool_night_id = ? AND tp.final_placement = 1
        ''', (night_id,))
        champ_row = cursor.fetchone()
        if champ_row:
            champion = dict(champ_row)
    
    conn.close()
    
    bracket_data = get_tournament_bracket(night_id)
    participants = get_tournament_participants(night_id)
    
    return render_template('board/tournament_display.html',
                           night=night,
                           bracket=bracket_data,
                           participants=participants,
                           champion=champion)


# Need datetime import
from datetime import datetime


# ============================================
# AUTHORIZED CONTROL ROUTES (Board session required)
# ============================================

@board_bp.route('/auth/create-session', methods=['POST'])
@require_host_auth
def create_session():
    """Create a new board control session. Requires bar host login."""
    data = request.json or {}
    bar_id = data.get('bar_id')
    device_name = data.get('device_name', 'Board')
    hours_valid = data.get('hours_valid', 24)
    
    if not bar_id:
        return jsonify({'error': 'bar_id required'}), 400
    
    session_id, session_token = create_board_session(
        bar_id, 
        authorized_by_user_id=request.host_user_id,
        device_name=device_name,
        hours_valid=hours_valid
    )
    
    log_match_action('board_session_created', bar_id=bar_id,
                     details=f"Device: {device_name}",
                     performed_by_user_id=request.host_user_id,
                     performed_by_type='host')
    
    return jsonify({
        'success': True,
        'session_id': session_id,
        'session_token': session_token,
        'message': f'Board session created for {hours_valid} hours'
    })


@board_bp.route('/auth/revoke-session', methods=['POST'])
@require_host_auth
def revoke_session():
    """Revoke a board control session."""
    data = request.json or {}
    session_token = data.get('session_token')
    
    if not session_token:
        return jsonify({'error': 'session_token required'}), 400
    
    revoke_board_session(session_token)
    
    return jsonify({'success': True, 'message': 'Session revoked'})


@board_bp.route('/control/<int:bar_id>')
@require_board_auth
def control_board(bar_id):
    """
    Control view for authorized board sessions.
    Has buttons for queue management and match recording.
    """
    return render_template('board/control.html', bar_id=bar_id)


# ============================================
# QUEUE CONTROL API (Board session required)
# ============================================

@board_bp.route('/api/queue/clear', methods=['POST'])
@require_board_auth
def api_clear_queue():
    """Clear entire queue. Requires board authorization."""
    data = request.json or {}
    bar_id = data.get('bar_id', 1)
    
    # Check for active ranked/paid match
    active_match = get_active_match(bar_id)
    if active_match and (active_match['is_ranked'] or active_match['pool_night_id']):
        return jsonify({
            'error': 'Cannot clear queue during ranked/paid match',
            'code': 'PROTECTED_MATCH'
        }), 403
    
    Queue.clear_all()
    
    log_match_action('queue_cleared', bar_id=bar_id,
                     performed_by_user_id=request.board_session.get('authorized_by_user_id'),
                     performed_by_type='board',
                     **get_request_info())
    
    return jsonify({'success': True, 'message': 'Queue cleared'})


@board_bp.route('/api/queue/remove/<int:queue_id>', methods=['POST'])
@require_board_auth
def api_remove_from_queue(queue_id):
    """Remove specific player from queue."""
    data = request.json or {}
    bar_id = data.get('bar_id', 1)
    
    # Get player info before removal for logging
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT q.*, p.nickname FROM queue q JOIN players p ON q.player_id = p.id WHERE q.id = ?', (queue_id,))
    entry = cursor.fetchone()
    conn.close()
    
    if not entry:
        return jsonify({'error': 'Player not in queue'}), 404
    
    entry = dict(entry)
    
    # Check if this player is in an active ranked/paid match
    if entry['position'] <= 2:
        active_match = get_active_match(bar_id)
        if active_match and (active_match['is_ranked'] or active_match['pool_night_id']):
            return jsonify({
                'error': 'Cannot remove player during ranked/paid match',
                'code': 'PROTECTED_MATCH'
            }), 403
    
    Queue.remove(queue_id)
    
    log_match_action('player_removed_from_queue', bar_id=bar_id,
                     details=f"Player: {entry['nickname']} (pos {entry['position']})",
                     performed_by_user_id=request.board_session.get('authorized_by_user_id'),
                     performed_by_type='board',
                     **get_request_info())
    
    return jsonify({'success': True, 'removed': entry['nickname']})


# ============================================
# MATCH CONTROL API (Board session required)
# ============================================

@board_bp.route('/api/match/start', methods=['POST'])
@require_board_auth
def api_start_match():
    """Start a new match between king and challenger."""
    data = request.json or {}
    bar_id = data.get('bar_id', 1)
    
    # Get current queue
    queue = Queue.get_all()
    if len(queue) < 2:
        return jsonify({'error': 'Need at least 2 players in queue'}), 400
    
    king = queue[0]
    challenger = queue[1]
    
    # Check for existing active match
    existing = get_active_match(bar_id)
    if existing:
        return jsonify({
            'error': 'Match already in progress',
            'active_match': existing
        }), 400
    
    # Determine if ranked
    is_event_ranked, ranked_source, _ = check_ranked_requirement(bar_id)
    is_ranked = is_event_ranked
    
    if not is_ranked:
        is_ranked, ranked_source = determine_match_ranked_status(bar_id, king['id'])
    
    # Check for pool night
    pool_night_id = None
    entry_fee = 0
    # TODO: Get active pool night for this bar if any
    
    # Create active match record
    match_id = create_active_match(
        bar_id=bar_id,
        player1_id=king['player_id'],
        player2_id=challenger['player_id'],
        player1_queue_id=king['id'],
        player2_queue_id=challenger['id'],
        is_ranked=is_ranked,
        ranked_source=ranked_source,
        pool_night_id=pool_night_id,
        entry_fee=entry_fee,
        created_by_user_id=request.board_session.get('authorized_by_user_id')
    )
    
    return jsonify({
        'success': True,
        'match_id': match_id,
        'king': king['nickname'],
        'challenger': challenger['nickname'],
        'is_ranked': is_ranked,
        'ranked_source': ranked_source
    })


@board_bp.route('/api/match/result', methods=['POST'])
@require_board_auth
def api_record_result():
    """Record match result. King wins or challenger wins."""
    data = request.json or {}
    bar_id = data.get('bar_id', 1)
    winner = data.get('winner')  # 'king' or 'challenger'
    
    if winner not in ['king', 'challenger']:
        return jsonify({'error': 'winner must be "king" or "challenger"'}), 400
    
    queue = Queue.get_all()
    if len(queue) < 2:
        return jsonify({'error': 'Need king and challenger'}), 400
    
    king = queue[0]
    challenger = queue[1]
    
    winner_id = king['player_id'] if winner == 'king' else challenger['player_id']
    
    # Check for active match
    active_match = get_active_match(bar_id)
    
    if active_match:
        # Record result in active_matches table
        success, message = record_match_result(
            active_match['id'],
            winner_id,
            recorded_by_user_id=request.board_session.get('authorized_by_user_id'),
            recorded_by_type='board'
        )
        
        if not success:
            return jsonify({'error': message}), 400
        
        # For non-protected matches, also update queue immediately
        if not active_match['is_ranked'] and not active_match['pool_night_id']:
            if winner == 'king':
                Queue.king_wins()
            else:
                Queue.challenger_wins()
            
            return jsonify({
                'success': True,
                'message': 'Result recorded and applied',
                'match_id': active_match['id'],
                'needs_confirmation': False
            })
        else:
            return jsonify({
                'success': True,
                'message': message,
                'match_id': active_match['id'],
                'needs_confirmation': True,
                'awaiting': 'Player confirmations or host override'
            })
    else:
        # No active match record - legacy behavior, just update queue
        if winner == 'king':
            Queue.king_wins()
        else:
            Queue.challenger_wins()
        
        log_match_action('result_recorded_legacy', bar_id=bar_id,
                         details=f"Winner: {winner} (no active match record)",
                         performed_by_user_id=request.board_session.get('authorized_by_user_id'),
                         performed_by_type='board',
                         **get_request_info())
        
        return jsonify({
            'success': True,
            'message': 'Result recorded (legacy mode)',
            'needs_confirmation': False
        })


@board_bp.route('/api/match/confirm', methods=['POST'])
def api_confirm_result():
    """Player confirms a match result."""
    player_id = session.get('player_id')
    if not player_id:
        return jsonify({'error': 'Login required'}), 401
    
    data = request.json or {}
    match_id = data.get('match_id')
    
    if not match_id:
        return jsonify({'error': 'match_id required'}), 400
    
    success, message = confirm_match_result(match_id, confirming_player_id=player_id)
    
    if success and 'locked' in message:
        # Result is now locked - apply to queue
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM active_matches WHERE id = ?', (match_id,))
        match = cursor.fetchone()
        conn.close()
        
        if match:
            # Determine winner and update queue
            queue = Queue.get_all()
            if len(queue) >= 2:
                king = queue[0]
                if match['result_winner_id'] == king['player_id']:
                    Queue.king_wins()
                else:
                    Queue.challenger_wins()
    
    return jsonify({'success': success, 'message': message})


@board_bp.route('/api/match/host-confirm', methods=['POST'])
@require_host_auth
def api_host_confirm_result():
    """Host confirms/overrides match result."""
    data = request.json or {}
    match_id = data.get('match_id')
    
    if not match_id:
        return jsonify({'error': 'match_id required'}), 400
    
    success, message = confirm_match_result(match_id, confirming_host_id=request.host_user_id)
    
    if success and 'locked' in message:
        # Result is now locked - apply to queue
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM active_matches WHERE id = ?', (match_id,))
        match = cursor.fetchone()
        conn.close()
        
        if match:
            queue = Queue.get_all()
            if len(queue) >= 2:
                king = queue[0]
                if match['result_winner_id'] == king['player_id']:
                    Queue.king_wins()
                else:
                    Queue.challenger_wins()
    
    return jsonify({'success': success, 'message': message})


@board_bp.route('/api/match/cancel', methods=['POST'])
@require_host_auth
def api_cancel_match():
    """Cancel an active match. Host only for protected matches."""
    data = request.json or {}
    match_id = data.get('match_id')
    bar_id = data.get('bar_id', 1)
    reason = data.get('reason', '')
    
    if not match_id:
        # Try to get active match for bar
        active = get_active_match(bar_id)
        if active:
            match_id = active['id']
        else:
            return jsonify({'error': 'No active match to cancel'}), 400
    
    success, message = cancel_active_match(
        match_id,
        cancelled_by_user_id=request.host_user_id,
        cancelled_by_type='host',
        reason=reason
    )
    
    return jsonify({'success': success, 'message': message})


# ============================================
# AUDIT & STATUS ROUTES
# ============================================

@board_bp.route('/api/audit/<int:bar_id>')
@require_host_auth
def api_get_audit_log(bar_id):
    """Get audit log for a bar. Host only."""
    limit = request.args.get('limit', 100, type=int)
    logs = get_match_audit_log(bar_id=bar_id, limit=limit)
    return jsonify({'logs': logs})


@board_bp.route('/api/pending-confirmations')
def api_pending_confirmations():
    """Get matches awaiting current player's confirmation."""
    player_id = session.get('player_id')
    if not player_id:
        return jsonify({'pending': []})
    
    pending = get_pending_confirmations(player_id)
    return jsonify({'pending': pending})


@board_bp.route('/api/match/status/<int:bar_id>')
def api_match_status(bar_id):
    """Get current match status for a bar."""
    active = get_active_match(bar_id)
    
    if not active:
        return jsonify({'has_active_match': False})
    
    return jsonify({
        'has_active_match': True,
        'match': {
            'id': active['id'],
            'player1': active['player1_name'],
            'player2': active['player2_name'],
            'is_ranked': bool(active['is_ranked']),
            'is_paid': bool(active['pool_night_id'] or active['entry_fee']),
            'status': active['status'],
            'result_pending': active['result_winner_id'] and not active['result_locked'],
            'result_locked': bool(active['result_locked'])
        }
    })


# ============================================
# VISUAL BADGES FOR PROTECTED MATCHES
# ============================================

@board_bp.route('/api/match/badges/<int:bar_id>')
def api_match_badges(bar_id):
    """Get visual badge info for current match."""
    active = get_active_match(bar_id)
    is_event_ranked, _, ranked_info = check_ranked_requirement(bar_id)
    
    badges = []
    
    if is_event_ranked:
        badges.append({
            'type': 'ranked',
            'label': '⭐ RANKED',
            'color': '#f59e0b',
            'info': ranked_info
        })
    
    if active:
        if active['is_ranked'] and not is_event_ranked:
            badges.append({
                'type': 'ranked',
                'label': '⭐ RANKED',
                'color': '#f59e0b',
                'info': 'Player-requested ranked match'
            })
        
        if active['pool_night_id']:
            badges.append({
                'type': 'event',
                'label': '🌙 POOL NIGHT',
                'color': '#8b5cf6',
                'info': 'Pool Night event match'
            })
        
        if active['entry_fee'] and active['entry_fee'] > 0:
            badges.append({
                'type': 'paid',
                'label': f'💰 ${active["entry_fee"]:.2f}',
                'color': '#22c55e',
                'info': 'Paid entry match'
            })
        
        if active['result_winner_id'] and not active['result_locked']:
            badges.append({
                'type': 'pending',
                'label': '⏳ CONFIRMING',
                'color': '#ef4444',
                'info': 'Awaiting result confirmation'
            })
        
        if active['result_locked']:
            badges.append({
                'type': 'locked',
                'label': '🔒 LOCKED',
                'color': '#6b7280',
                'info': 'Result confirmed and locked'
            })
    
    return jsonify({'badges': badges})
