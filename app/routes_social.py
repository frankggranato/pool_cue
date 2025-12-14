"""
Social API routes - Friends, Challenges, Tokens, Notifications
"""
from flask import Blueprint, request, jsonify, session
from .database_social import (
    init_social_db,
    # Tokens
    award_tokens, deduct_tokens, get_token_balance, get_token_history,
    claim_daily_bonus, award_game_tokens,
    TOKENS_WIN, TOKENS_LOSE, TOKENS_SURVEY,
    # Friends
    send_friend_request, accept_friend_request, decline_friend_request,
    get_friends, get_friend_requests, search_players,
    # Challenges
    send_challenge, accept_challenge, decline_challenge, complete_challenge,
    get_pending_challenges, get_active_challenges,
    # Notifications
    get_notifications, mark_notification_read, mark_all_notifications_read, get_unread_count,
    # Activity
    update_activity, get_friends_playing
)
from .database import get_db

social_bp = Blueprint('social', __name__, url_prefix='/api/social')


def get_current_player():
    """Get current player from session."""
    player_id = session.get('player_id')
    if not player_id:
        return None
    return player_id


# ============================================
# TOKEN ENDPOINTS
# ============================================

@social_bp.route('/tokens')
def api_tokens():
    """Get token info including balance."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    balance = get_token_balance(player_id)
    return jsonify({'balance': balance, 'daily_bonus_awarded': 0})


@social_bp.route('/tokens/balance')
def api_token_balance():
    """Get current token balance."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    balance = get_token_balance(player_id)
    return jsonify({'balance': balance})


@social_bp.route('/tokens/history')
def api_token_history():
    """Get token transaction history."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    history = get_token_history(player_id)
    return jsonify({'history': history})


@social_bp.route('/tokens/daily', methods=['POST'])
def api_claim_daily():
    """Claim daily login bonus."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    success, message = claim_daily_bonus(player_id)
    return jsonify({'success': success, 'message': message})


@social_bp.route('/tokens/award', methods=['POST'])
def api_award_tokens():
    """Award tokens (for surveys, etc)."""
    player_id = request.json.get('player_id') or get_current_player()
    if not player_id:
        return jsonify({'error': 'Player ID required'}), 400
    
    amount = request.json.get('amount', TOKENS_SURVEY)
    reason = request.json.get('reason', 'survey')
    
    award_tokens(player_id, amount, reason)
    new_balance = get_token_balance(player_id)
    
    return jsonify({'success': True, 'awarded': amount, 'balance': new_balance})


@social_bp.route('/tokens/earn/survey', methods=['POST'])
def api_earn_survey():
    """Complete a survey to earn tokens."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    survey_type = request.json.get('survey_type', 'quick') if request.json else 'quick'
    
    # Award tokens based on survey type
    tokens = 25 if survey_type == 'quick' else 50
    
    award_tokens(player_id, tokens, 'survey_general')
    new_balance = get_token_balance(player_id)
    
    return jsonify({
        'success': True, 
        'tokens_earned': tokens, 
        'balance': new_balance
    })


# ============================================
# FRIEND ENDPOINTS
# ============================================

@social_bp.route('/friends')
def api_get_friends():
    """Get list of friends with requests and playing now."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    friends = get_friends(player_id)
    requests = get_friend_requests(player_id)
    playing = get_friends_playing(player_id)
    
    return jsonify({
        'friends': friends,
        'requests': requests,
        'playing_now': playing
    })


@social_bp.route('/friends/requests')
def api_friend_requests():
    """Get pending friend requests."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    requests = get_friend_requests(player_id)
    return jsonify({'requests': requests})


@social_bp.route('/friends/request', methods=['POST'])
def api_send_friend_request():
    """Send a friend request."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    friend_id = request.json.get('friend_id')
    if not friend_id:
        return jsonify({'error': 'friend_id required'}), 400
    
    success, message = send_friend_request(player_id, friend_id)
    return jsonify({'success': success, 'message': message})


@social_bp.route('/friends/accept', methods=['POST'])
def api_accept_friend():
    """Accept a friend request."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    friend_id = request.json.get('friend_id')
    success, message = accept_friend_request(player_id, friend_id)
    return jsonify({'success': success, 'message': message})


@social_bp.route('/friends/decline', methods=['POST'])
def api_decline_friend():
    """Decline a friend request."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    friend_id = request.json.get('friend_id')
    success, message = decline_friend_request(player_id, friend_id)
    return jsonify({'success': success, 'message': message})


@social_bp.route('/friends/respond', methods=['POST'])
def api_respond_friend():
    """Respond to a friend request (accept or decline)."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    requester_id = request.json.get('requester_id')
    accept = request.json.get('accept', False)
    
    if accept:
        success, message = accept_friend_request(player_id, requester_id)
    else:
        success, message = decline_friend_request(player_id, requester_id)
    
    return jsonify({'success': success, 'message': message})


@social_bp.route('/friends/playing')
def api_friends_playing():
    """Get friends who are currently playing."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    friends = get_friends_playing(player_id)
    return jsonify({'friends': friends})


@social_bp.route('/players/search')
def api_search_players():
    """Search for players."""
    player_id = get_current_player()
    query = request.args.get('q', '')
    
    if len(query) < 2:
        return jsonify({'players': []})
    
    # Get all matching players with their stats (active only)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, nickname, wins, losses, tokens_balance, email IS NOT NULL as has_account
        FROM players 
        WHERE nickname LIKE ? AND id != ? AND (is_active = 1 OR is_active IS NULL)
        ORDER BY has_account DESC, wins DESC
        LIMIT 20
    ''', (f'%{query}%', player_id or 0))
    rows = cursor.fetchall()
    conn.close()
    
    players = [dict(r) for r in rows]
    return jsonify({'players': players})


@social_bp.route('/player/<int:player_id>')
def api_get_player(player_id):
    """Get a single player's public profile."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, nickname, wins, losses, total_games, tokens_balance,
               email IS NOT NULL as has_account, created_at
        FROM players WHERE id = ?
    ''', (player_id,))
    player = cursor.fetchone()
    
    if not player:
        conn.close()
        return jsonify({'error': 'Player not found'}), 404
    
    # Check if we're friends
    current_player = get_current_player()
    is_friend = False
    friend_status = None
    
    if current_player:
        cursor.execute('''
            SELECT status FROM friendships 
            WHERE (player_id = ? AND friend_id = ?) OR (player_id = ? AND friend_id = ?)
        ''', (current_player, player_id, player_id, current_player))
        friendship = cursor.fetchone()
        if friendship:
            friend_status = friendship['status']
            is_friend = friend_status == 'accepted'
    
    conn.close()
    
    return jsonify({
        'player': dict(player),
        'is_friend': is_friend,
        'friend_status': friend_status,
        'is_me': current_player == player_id
    })


# ============================================
# CHALLENGE ENDPOINTS
# ============================================

@social_bp.route('/challenges')
def api_all_challenges():
    """Get all challenges - pending, outgoing, active, history."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    from .database_social import get_outgoing_challenges
    
    pending = get_pending_challenges(player_id)
    outgoing = get_outgoing_challenges(player_id)
    active = get_active_challenges(player_id)
    
    # Get history (completed challenges)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.*, 
               p1.nickname as challenger_name,
               p2.nickname as challenged_name
        FROM challenges c
        JOIN players p1 ON p1.id = c.challenger_user_id
        JOIN players p2 ON p2.id = c.challenged_user_id
        WHERE (c.challenger_user_id = ? OR c.challenged_user_id = ?) 
          AND c.status IN ('completed', 'declined', 'cancelled')
        ORDER BY c.responded_at DESC LIMIT 20
    ''', (player_id, player_id))
    history = [dict(r) for r in cursor.fetchall()]
    conn.close()
    
    return jsonify({
        'pending': pending,
        'outgoing': outgoing,
        'active': active,
        'history': history
    })


@social_bp.route('/challenges/pending')
def api_pending_challenges():
    """Get pending challenges."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    challenges = get_pending_challenges(player_id)
    return jsonify({'challenges': challenges})


@social_bp.route('/challenges/active')
def api_active_challenges():
    """Get active (accepted) challenges."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    challenges = get_active_challenges(player_id)
    return jsonify({'challenges': challenges})


@social_bp.route('/challenges/send', methods=['POST'])
def api_send_challenge():
    """Send a challenge to another player."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.json or {}
    challenged_id = data.get('challenged_id')
    bar_id = data.get('bar_id')
    message = data.get('message')
    stakes = int(data.get('stakes') or data.get('tokens_wager') or 0)
    scheduled_datetime = data.get('scheduled_datetime')
    location = data.get('location')
    
    if not challenged_id:
        return jsonify({'error': 'challenged_id required'}), 400
    
    success, result = send_challenge(player_id, challenged_id, bar_id, message, stakes, scheduled_datetime, location)
    
    if success:
        return jsonify({'success': True, 'challenge_id': result})
    return jsonify({'success': False, 'error': result}), 400


@social_bp.route('/challenges/<int:challenge_id>/respond', methods=['POST'])
def api_respond_challenge(challenge_id):
    """Respond to a challenge (accept or decline)."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    accept = request.json.get('accept', False)
    
    if accept:
        success, message = accept_challenge(challenge_id, player_id)
    else:
        success, message = decline_challenge(challenge_id, player_id)
    
    return jsonify({'success': success, 'message': message})


@social_bp.route('/challenges/<int:challenge_id>/cancel', methods=['POST'])
def api_cancel_challenge(challenge_id):
    """Cancel a challenge you sent."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Make sure this challenge was sent by this player and is still pending
    cursor.execute('SELECT * FROM challenges WHERE id = ? AND challenger_user_id = ? AND status = ?', 
                   (challenge_id, player_id, 'pending'))
    challenge = cursor.fetchone()
    
    if not challenge:
        conn.close()
        return jsonify({'success': False, 'error': 'Challenge not found or cannot be cancelled'}), 400
    
    cursor.execute('UPDATE challenges SET status = ? WHERE id = ?', ('cancelled', challenge_id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Challenge cancelled'})


@social_bp.route('/challenges/<int:challenge_id>/accept', methods=['POST'])
def api_accept_challenge(challenge_id):
    """Accept a challenge."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    success, message = accept_challenge(challenge_id, player_id)
    return jsonify({'success': success, 'message': message})


@social_bp.route('/challenges/<int:challenge_id>/decline', methods=['POST'])
def api_decline_challenge(challenge_id):
    """Decline a challenge."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    success, message = decline_challenge(challenge_id, player_id)
    return jsonify({'success': success, 'message': message})


@social_bp.route('/challenges/<int:challenge_id>/complete', methods=['POST'])
def api_complete_challenge(challenge_id):
    """Complete a challenge with winner."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    winner_id = request.json.get('winner_id')
    if not winner_id:
        return jsonify({'error': 'winner_id required'}), 400
    
    success, result = complete_challenge(challenge_id, winner_id)
    return jsonify({'success': success, 'result': result})


# ============================================
# NOTIFICATION ENDPOINTS
# ============================================

@social_bp.route('/notifications')
def api_notifications():
    """Get notifications."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    unread_only = request.args.get('unread') == '1'
    notifications = get_notifications(player_id, unread_only)
    return jsonify({'notifications': notifications})


@social_bp.route('/notifications/count')
def api_notification_count():
    """Get unread notification count."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'count': 0})
    
    count = get_unread_count(player_id)
    return jsonify({'count': count})


@social_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
def api_mark_read(notification_id):
    """Mark notification as read."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    mark_notification_read(notification_id, player_id)
    return jsonify({'success': True})


@social_bp.route('/notifications/read-all', methods=['POST'])
def api_mark_all_read():
    """Mark all notifications as read."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    mark_all_notifications_read(player_id)
    return jsonify({'success': True})


# ============================================
# ACTIVITY ENDPOINTS
# ============================================

@social_bp.route('/activity/update', methods=['POST'])
def api_update_activity():
    """Update player's activity status."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.json or {}
    bar_id = data.get('bar_id')
    status = data.get('status', 'online')
    
    update_activity(player_id, bar_id, status)
    return jsonify({'success': True})


# ============================================
# PROFILE/STATS ENDPOINTS
# ============================================

@social_bp.route('/profile')
def api_profile():
    """Get current player's profile."""
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, nickname, email, phone, total_games, wins, losses, 
               tokens_balance, total_tokens_earned, created_at
        FROM players WHERE id = ?
    ''', (player_id,))
    player = cursor.fetchone()
    conn.close()
    
    if not player:
        return jsonify({'error': 'Player not found'}), 404
    
    return jsonify({
        'id': player[0],
        'nickname': player[1],
        'email': player[2],
        'phone': player[3],
        'total_games': player[4] or 0,
        'wins': player[5] or 0,
        'losses': player[6] or 0,
        'tokens': player[7] or 0,
        'total_earned': player[8] or 0,
        'member_since': player[9]
    })


@social_bp.route('/profile/<int:player_id>')
def api_player_profile(player_id):
    """Get another player's public profile."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, nickname, total_games, wins, losses, created_at
        FROM players WHERE id = ?
    ''', (player_id,))
    player = cursor.fetchone()
    conn.close()
    
    if not player:
        return jsonify({'error': 'Player not found'}), 404
    
    return jsonify({
        'id': player[0],
        'nickname': player[1],
        'total_games': player[2] or 0,
        'wins': player[3] or 0,
        'losses': player[4] or 0,
        'member_since': player[5]
    })


@social_bp.route('/leaderboard')
def api_leaderboard():
    """Get leaderboard with multiple sort options."""
    conn = get_db()
    cursor = conn.cursor()
    
    # By wins
    cursor.execute('''
        SELECT id, nickname, wins, losses, tokens_balance, account_id,
               CASE WHEN (wins + losses) > 0 THEN ROUND(100.0 * wins / (wins + losses), 1) ELSE 0 END as win_rate
        FROM players 
        WHERE wins > 0
        ORDER BY wins DESC
        LIMIT 50
    ''')
    by_wins = []
    for i, row in enumerate(cursor.fetchall(), 1):
        by_wins.append({
            'rank': i,
            'id': row['id'],
            'nickname': row['nickname'],
            'wins': row['wins'] or 0,
            'losses': row['losses'] or 0,
            'tokens_balance': row['tokens_balance'] or 0,
            'win_rate': row['win_rate'] or 0,
            'account_id': row['account_id'],
            'is_guest': row['account_id'] is None
        })
    
    # By tokens
    cursor.execute('''
        SELECT id, nickname, wins, losses, tokens_balance, account_id
        FROM players 
        WHERE tokens_balance > 0
        ORDER BY tokens_balance DESC
        LIMIT 50
    ''')
    by_tokens = []
    for i, row in enumerate(cursor.fetchall(), 1):
        by_tokens.append({
            'rank': i,
            'id': row['id'],
            'nickname': row['nickname'],
            'wins': row['wins'] or 0,
            'losses': row['losses'] or 0,
            'tokens_balance': row['tokens_balance'] or 0,
            'account_id': row['account_id'],
            'is_guest': row['account_id'] is None
        })
    
    # By win rate (min 5 games)
    cursor.execute('''
        SELECT id, nickname, wins, losses, tokens_balance, account_id,
               CASE WHEN (wins + losses) > 0 THEN ROUND(100.0 * wins / (wins + losses), 1) ELSE 0 END as win_rate
        FROM players 
        WHERE (wins + losses) >= 5
        ORDER BY win_rate DESC, wins DESC
        LIMIT 50
    ''')
    by_winrate = []
    for i, row in enumerate(cursor.fetchall(), 1):
        by_winrate.append({
            'rank': i,
            'id': row['id'],
            'nickname': row['nickname'],
            'wins': row['wins'] or 0,
            'losses': row['losses'] or 0,
            'tokens_balance': row['tokens_balance'] or 0,
            'win_rate': row['win_rate'] or 0,
            'account_id': row['account_id'],
            'is_guest': row['account_id'] is None
        })
    
    conn.close()
    return jsonify({
        'by_wins': by_wins,
        'by_tokens': by_tokens,
        'by_winrate': by_winrate,
        'leaderboard': by_wins  # backwards compatibility
    })



# ============================================
# LOCATION-AWARE RANKING ENDPOINTS
# ============================================

from .services.ranking_service import (
    get_leaderboard,
    get_leaderboard_for_bar,
    get_leaderboard_for_borough,
    get_leaderboard_for_city,
    get_leaderboard_for_state,
    get_leaderboard_global,
    get_player_rankings_all_scopes,
    get_available_scopes_for_bar,
    RANKING_SCOPES,
    MIN_GAMES_BY_SCOPE
)


@social_bp.route('/rankings')
def api_rankings():
    """
    Get location-aware leaderboard.
    
    Query params:
        scope: bar|borough|city|state|global (default: global)
        bar_id: Required if scope=bar
        borough: Required if scope=borough (NYC only)
        city: Required if scope=city
        state: Required if scope=city or scope=state
        metric: wins|rating|winrate|games (default: wins)
        limit: Max results (default: 50)
    """
    scope = request.args.get('scope', 'global')
    metric = request.args.get('metric', 'wins')
    limit = min(int(request.args.get('limit', 50)), 100)
    
    # Build params based on scope
    params = {}
    if scope == 'bar':
        bar_id = request.args.get('bar_id')
        if not bar_id:
            return jsonify({'error': 'bar_id required for bar scope'}), 400
        params['bar_id'] = int(bar_id)
    elif scope == 'borough':
        borough = request.args.get('borough')
        if not borough:
            return jsonify({'error': 'borough required for borough scope'}), 400
        params['borough'] = borough
    elif scope == 'city':
        city = request.args.get('city')
        state = request.args.get('state')
        if not city or not state:
            return jsonify({'error': 'city and state required for city scope'}), 400
        params['city'] = city
        params['state'] = state
    elif scope == 'state':
        state = request.args.get('state')
        if not state:
            return jsonify({'error': 'state required for state scope'}), 400
        params['state'] = state
    
    try:
        players = get_leaderboard(scope, params, limit, metric)
        return jsonify({
            'scope': scope,
            'params': params,
            'metric': metric,
            'players': players,
            'count': len(players),
            'min_games': MIN_GAMES_BY_SCOPE.get(scope, 10)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@social_bp.route('/rankings/scopes')
def api_ranking_scopes():
    """
    Get available ranking scopes for a bar.
    Returns list of scopes player can view from that bar.
    
    Query params:
        bar_id: The bar to get scopes for
    """
    bar_id = request.args.get('bar_id')
    if not bar_id:
        # Return all possible scopes
        return jsonify({
            'scopes': [
                {'scope': 'global', 'label': 'Global', 'params': {}}
            ]
        })
    
    try:
        scopes = get_available_scopes_for_bar(int(bar_id))
        return jsonify({'scopes': scopes, 'bar_id': int(bar_id)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@social_bp.route('/rankings/player/<int:player_id>')
def api_player_rankings(player_id):
    """
    Get a player's rankings across all scopes.
    Shows how they rank at each location level.
    """
    try:
        rankings = get_player_rankings_all_scopes(player_id)
        return jsonify(rankings)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@social_bp.route('/rankings/my')
def api_my_rankings():
    """
    Get current player's rankings across all scopes.
    """
    player_id = get_current_player()
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        rankings = get_player_rankings_all_scopes(player_id)
        return jsonify(rankings)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@social_bp.route('/rankings/bar/<int:bar_id>')
def api_bar_rankings(bar_id):
    """Get leaderboard for a specific bar."""
    metric = request.args.get('metric', 'wins')
    limit = min(int(request.args.get('limit', 50)), 100)
    
    try:
        players = get_leaderboard_for_bar(bar_id, limit, metric)
        return jsonify({
            'scope': 'bar',
            'bar_id': bar_id,
            'metric': metric,
            'players': players,
            'count': len(players)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@social_bp.route('/rankings/borough/<borough>')
def api_borough_rankings(borough):
    """Get leaderboard for a NYC borough."""
    metric = request.args.get('metric', 'wins')
    limit = min(int(request.args.get('limit', 50)), 100)
    
    try:
        players = get_leaderboard_for_borough(borough, limit, metric)
        return jsonify({
            'scope': 'borough',
            'borough': borough,
            'metric': metric,
            'players': players,
            'count': len(players)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@social_bp.route('/rankings/city/<state>/<city>')
def api_city_rankings(state, city):
    """Get leaderboard for a city."""
    metric = request.args.get('metric', 'wins')
    limit = min(int(request.args.get('limit', 50)), 100)
    
    try:
        players = get_leaderboard_for_city(city, state, limit, metric)
        return jsonify({
            'scope': 'city',
            'city': city,
            'state': state,
            'metric': metric,
            'players': players,
            'count': len(players)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@social_bp.route('/rankings/state/<state>')
def api_state_rankings(state):
    """Get leaderboard for a state."""
    metric = request.args.get('metric', 'wins')
    limit = min(int(request.args.get('limit', 50)), 100)
    
    try:
        players = get_leaderboard_for_state(state, limit, metric)
        return jsonify({
            'scope': 'state',
            'state': state,
            'metric': metric,
            'players': players,
            'count': len(players)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
