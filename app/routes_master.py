"""
Master Dashboard routes - Owner control panel for all bars, players, ads
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from functools import wraps
from datetime import datetime
from werkzeug.security import generate_password_hash
from .database import get_db
from .database_league import (get_master_stats, get_all_players_ranked, get_pending_reports,
                               ban_player, get_leaderboard, get_current_season)
# Import location service for borough/geo handling
from .services.location_service import (
    NYC_BOROUGHS, BOROUGH_NORMALIZE, normalize_borough, 
    get_location_analytics, auto_populate_borough, is_nyc_location
)
import os
import glob

master_bp = Blueprint('master', __name__, url_prefix='/master')

ADS_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'ads')

# NOTE: NYC_BOROUGHS and BOROUGH_NORMALIZE are now imported from location_service
# This ensures a single source of truth for location data

# Legacy alias for backward compatibility (imported above)
# NYC_BOROUGHS = ('Manhattan', 'Brooklyn', 'Queens', 'The Bronx', 'Staten Island')
# BOROUGH_NORMALIZE = { ... } - see location_service.py
# normalize_borough() - see location_service.py


def admin_required(f):
    """Decorator to require admin login for master routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('setup.admin_login'))
        return f(*args, **kwargs)
    return decorated_function


@master_bp.route('/')
@admin_required
def dashboard():
    """Main master dashboard - command center."""
    print("[MASTER] Dashboard loaded")
    conn = get_db()
    cursor = conn.cursor()
    
    stats = {}
    
    # Active bars count
    cursor.execute('SELECT COUNT(*) FROM bars WHERE is_active = 1')
    stats['active_bars'] = cursor.fetchone()[0] or 0
    
    # Total players
    cursor.execute('SELECT COUNT(*) FROM players')
    stats['total_players'] = cursor.fetchone()[0] or 0
    
    # Total games
    cursor.execute('SELECT COUNT(*) FROM game_history')
    stats['total_games'] = cursor.fetchone()[0] or 0
    
    # Games today
    cursor.execute("SELECT COUNT(*) FROM game_history WHERE date(played_at) = date('now')")
    stats['games_today'] = cursor.fetchone()[0] or 0
    
    # Active campaigns
    try:
        cursor.execute("SELECT COUNT(*) FROM campaigns WHERE status = 'active' AND (end_date IS NULL OR end_date >= date('now'))")
        stats['active_campaigns'] = cursor.fetchone()[0] or 0
    except:
        stats['active_campaigns'] = 0
    
    # Pending pool nights
    stats['pending_nights'] = 0
    try:
        cursor.execute("SELECT COUNT(*) FROM pool_nights WHERE status = 'pending'")
        stats['pending_nights'] = cursor.fetchone()[0] or 0
    except:
        pass
    
    # Bars for dashboard - top 5 active bars with player and queue counts
    cursor.execute('''
        SELECT b.id, b.name, b.is_active,
               (SELECT COUNT(*) FROM players p WHERE p.home_bar_id = b.id) as player_count,
               (SELECT COUNT(*) FROM queue q WHERE q.bar_id = b.id) as queue_count
        FROM bars b
        WHERE b.is_active = 1
        ORDER BY player_count DESC
        LIMIT 5
    ''')
    bars_for_dashboard = []
    for r in cursor.fetchall():
        bars_for_dashboard.append({
            'id': r[0],
            'name': r[1],
            'is_active': r[2],
            'player_count': r[3] or 0,
            'queue_count': r[4] or 0
        })
    
    # Recent players with bar name (from most recent queue activity) and games played
    cursor.execute('''
        SELECT p.id, p.nickname, 
               COALESCE(
                   (SELECT b.name FROM queue_usage_log qul 
                    JOIN bars b ON qul.bar_id = b.id 
                    WHERE qul.player_id = p.id 
                    ORDER BY qul.created_at DESC LIMIT 1),
                   (SELECT b.name FROM game_history gh
                    JOIN bars b ON gh.bar_id = b.id
                    WHERE gh.winner_id = p.id OR gh.loser_id = p.id
                    ORDER BY gh.played_at DESC LIMIT 1),
                   (SELECT b.name FROM bars b WHERE b.id = p.home_bar_id)
               ) as bar_name,
               (SELECT COUNT(*) FROM game_history g WHERE g.winner_id = p.id OR g.loser_id = p.id) as games_played
        FROM players p
        ORDER BY p.created_at DESC
        LIMIT 5
    ''')
    recent_players = []
    for r in cursor.fetchall():
        recent_players.append({
            'id': r[0],
            'nickname': r[1],
            'bar_name': r[2] or '-',
            'games_played': r[3] or 0
        })
    
    # Campaigns for dashboard with impressions and CTR (using ad_events table)
    campaigns_for_dashboard = []
    try:
        cursor.execute('''
            SELECT c.id, c.name, a.name as advertiser_name,
                   (SELECT COUNT(*) FROM ad_events ae WHERE ae.campaign_id = c.id AND ae.event_type = 'impression') as impressions,
                   (SELECT COUNT(*) FROM ad_events ae WHERE ae.campaign_id = c.id AND ae.event_type = 'click') as clicks
            FROM campaigns c
            LEFT JOIN advertisers a ON c.advertiser_id = a.id
            WHERE c.status = 'active' AND (c.end_date IS NULL OR c.end_date >= date('now'))
            ORDER BY impressions DESC
            LIMIT 5
        ''')
        for r in cursor.fetchall():
            impressions = r[3] or 0
            clicks = r[4] or 0
            ctr = round((clicks / impressions * 100), 1) if impressions > 0 else 0.0
            campaigns_for_dashboard.append({
                'id': r[0],
                'name': r[1],
                'advertiser': r[2] or 'Unknown',
                'impressions': impressions,
                'ctr': ctr
            })
    except Exception as e:
        print(f"[DASHBOARD] Campaign query error: {e}")
    
    # Leaderboard - top players by wins with win rate
    cursor.execute('''
        SELECT p.id, p.nickname, p.wins, p.losses
        FROM players p
        WHERE p.wins > 0 OR p.losses > 0
        ORDER BY p.wins DESC, p.rating DESC
        LIMIT 5
    ''')
    leaderboard = []
    for r in cursor.fetchall():
        wins = r[2] or 0
        losses = r[3] or 0
        total = wins + losses
        win_rate = round((wins / total * 100)) if total > 0 else 0
        leaderboard.append({
            'id': r[0],
            'nickname': r[1],
            'wins': wins,
            'win_rate': win_rate
        })
    
    # Recent activity feed
    activity = []
    try:
        cursor.execute('''
            SELECT 'game' as type, p.nickname, g.played_at
            FROM game_history g
            JOIN players p ON g.winner_id = p.id
            ORDER BY g.played_at DESC
            LIMIT 6
        ''')
        for r in cursor.fetchall():
            activity.append({
                'icon': '🎱',
                'text': f'<b>{r[1]}</b> won a game',
                'time': r[2][:16] if r[2] else 'Recently'
            })
    except:
        pass
    
    # Weekly revenue (from POS data - last 7 days)
    stats['weekly_revenue'] = 0
    try:
        cursor.execute('''
            SELECT COALESCE(SUM(total_amount), 0) as revenue
            FROM pos_checks 
            WHERE business_date >= date('now', '-7 days')
        ''')
        row = cursor.fetchone()
        stats['weekly_revenue'] = round(row[0], 0) if row and row[0] else 0
    except:
        pass
    
    # Avg session time (from game durations)
    stats['avg_session'] = '-'
    try:
        cursor.execute('''
            SELECT AVG(duration_seconds) as avg_duration
            FROM game_history 
            WHERE duration_seconds > 0 
              AND duration_seconds < 7200
              AND played_at >= datetime('now', '-30 days')
        ''')
        row = cursor.fetchone()
        if row and row[0]:
            avg_mins = int(row[0] / 60)
            stats['avg_session'] = f'{avg_mins}m'
    except:
        pass
    
    # Upcoming events
    stats['upcoming_events'] = 0
    try:
        cursor.execute("SELECT COUNT(*) FROM pool_nights WHERE status = 'approved' AND event_date >= date('now')")
        stats['upcoming_events'] = cursor.fetchone()[0] or 0
    except:
        pass
    
    # Pool nights for dashboard (real data)
    pool_nights = []
    pending_count = 0
    try:
        # Get pending count
        cursor.execute("SELECT COUNT(*) FROM pool_nights WHERE status = 'pending'")
        pending_count = cursor.fetchone()[0] or 0
        
        # Get recent pool nights (pending first, then upcoming approved)
        cursor.execute('''
            SELECT pn.id, pn.name, pn.event_date, pn.status, b.name as bar_name
            FROM pool_nights pn
            LEFT JOIN bars b ON pn.bar_id = b.id
            WHERE pn.status IN ('pending', 'approved') AND pn.event_date >= date('now', '-7 days')
            ORDER BY 
                CASE pn.status WHEN 'pending' THEN 0 ELSE 1 END,
                pn.event_date ASC
            LIMIT 3
        ''')
        for r in cursor.fetchall():
            pool_nights.append({
                'id': r[0],
                'name': r[1],
                'event_date': r[2],
                'status': r[3],
                'bar_name': r[4] or 'Unknown Bar',
                'icon': '🏆' if 'tournament' in (r[1] or '').lower() else '🎱'
            })
    except:
        pass
    
    conn.close()
    
    # Check if this is an embed request (for app shell)
    embed = request.args.get('embed', '0') == '1'
    
    return render_template('master/dashboard.html', 
                         active_page='dashboard',
                         bars=bars_for_dashboard,
                         recent_players=recent_players,
                         campaigns=campaigns_for_dashboard,
                         leaderboard=leaderboard,
                         activity=activity,
                         pool_nights=pool_nights,
                         pending_nights_count=pending_count,
                         embed=embed,
                         **stats)

@master_bp.route('/data')
@admin_required
def data_intelligence():
    """Redirect to analytics - data intelligence consolidated."""
    return redirect(url_for('master.analytics'))

@master_bp.route('/players')
@admin_required
def players():
    """All players management."""
    print("[MASTER] Players page loaded")
    include_inactive = request.args.get('include_inactive', '0') == '1'
    players = get_all_players_ranked(include_inactive=include_inactive)
    embed = request.args.get('embed', '0') == '1'
    return render_template('master/players.html', players=players, active_page='players', embed=embed, include_inactive=include_inactive)

@master_bp.route('/player/<int:player_id>')
@admin_required
def player_detail(player_id):
    """Detailed view of a single player with all data."""
    from .database import find_potential_duplicates, get_admin_audit_log, get_player_detailed_stats, get_player_tier
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get player with calculated stats from game_history
    cursor.execute('''
        SELECT p.*,
               COALESCE((SELECT COUNT(*) FROM game_history WHERE winner_id = p.id), 0) as calc_wins,
               COALESCE((SELECT COUNT(*) FROM game_history WHERE loser_id = p.id), 0) as calc_losses,
               COALESCE((SELECT COUNT(*) FROM game_history WHERE winner_id = p.id OR loser_id = p.id), 0) as games_played,
               b.name as home_bar_name
        FROM players p
        LEFT JOIN bars b ON p.home_bar_id = b.id
        WHERE p.id = ?
    ''', (player_id,))
    player_row = cursor.fetchone()
    
    if player_row:
        player = dict(player_row)
        # Use calculated stats as source of truth
        player['wins'] = player.get('calc_wins', 0) or 0
        player['losses'] = player.get('calc_losses', 0) or 0
        player['games_played'] = player.get('games_played', 0) or 0
        player['total_games'] = player['games_played']
        
        # Calculate win rate
        total = player['wins'] + player['losses']
        player['win_rate'] = round((player['wins'] / total * 100) if total > 0 else 0)
        
        # Get detailed stats (ranked vs unranked + calculated play frequency)
        detailed_stats = get_player_detailed_stats(player_id)
        
        # Get player tier (percentile-based ranking)
        tier = get_player_tier(player_id)
        
        # Get recent game history with formatted data
        cursor.execute('''
            SELECT g.*, 
                   pw.nickname as winner_name, 
                   pl.nickname as loser_name,
                   bar.name as bar_name
            FROM game_history g
            LEFT JOIN players pw ON g.winner_id = pw.id
            LEFT JOIN players pl ON g.loser_id = pl.id
            LEFT JOIN bars bar ON g.bar_id = bar.id
            WHERE g.winner_id = ? OR g.loser_id = ?
            ORDER BY g.played_at DESC
            LIMIT 20
        ''', (player_id, player_id))
        
        games = []
        for row in cursor.fetchall():
            game = dict(row)
            game['won'] = game['winner_id'] == player_id
            game['opponent_id'] = game['loser_id'] if game['won'] else game['winner_id']
            game['opponent_name'] = game['loser_name'] if game['won'] else game['winner_name']
            games.append(game)
        
        # Get potential duplicates
        duplicates = find_potential_duplicates(player_id)
        
        # Get audit log for this player
        audit_log = get_admin_audit_log(target_user_id=player_id, limit=10)
        
        # Get all bars for home bar dropdown
        cursor.execute('SELECT id, name FROM bars WHERE is_active = 1 ORDER BY name')
        bars = [dict(row) for row in cursor.fetchall()]
    else:
        player = {'id': player_id, 'nickname': 'Unknown Player', 'wins': 0, 'losses': 0, 'games_played': 0}
        games = []
        duplicates = []
        audit_log = []
        bars = []
        detailed_stats = None
        tier = None
    
    conn.close()
    return render_template('master/player_detail.html', 
                           player=player, 
                           games=games, 
                           duplicates=duplicates,
                           audit_log=audit_log,
                           bars=bars,
                           detailed_stats=detailed_stats,
                           tier=tier,
                           active_page='players')


@master_bp.route('/player/<int:player_id>/edit', methods=['POST'])
@admin_required
def player_edit(player_id):
    """Edit player profile fields from master dashboard."""
    from .database import update_player_admin
    
    updates = {
        'display_name': request.form.get('display_name') or None,
        'home_bar_id': request.form.get('home_bar_id', type=int) or None,
        'play_frequency': request.form.get('play_frequency') or None,
        'marketing_opt_in': 1 if request.form.get('marketing_opt_in') else 0,
        'preferred_contact_method': request.form.get('preferred_contact_method') or 'email'
    }
    
    admin_id = session.get('player_id')  # Assuming master admins are logged in as players
    ip = request.remote_addr
    
    success, message = update_player_admin(player_id, updates, admin_user_id=admin_id, ip_address=ip)
    
    if success:
        flash('Player updated successfully', 'success')
    else:
        flash(f'Error: {message}', 'error')
    
    return redirect(url_for('master.player_detail', player_id=player_id))


@master_bp.route('/player/<int:player_id>/deactivate', methods=['POST'])
@admin_required
def player_deactivate(player_id):
    """Deactivate a player account."""
    from .database import deactivate_player
    
    reason = request.form.get('reason', 'Deactivated by admin')
    admin_id = session.get('player_id')
    ip = request.remote_addr
    
    success, message = deactivate_player(player_id, admin_user_id=admin_id, reason=reason, ip_address=ip)
    
    if success:
        flash('Account deactivated', 'success')
    else:
        flash(f'Error: {message}', 'error')
    
    return redirect(url_for('master.player_detail', player_id=player_id))


@master_bp.route('/player/<int:player_id>/reactivate', methods=['POST'])
@admin_required
def player_reactivate(player_id):
    """Reactivate a player account."""
    from .database import reactivate_player
    
    reason = request.form.get('reason', 'Reactivated by admin')
    admin_id = session.get('player_id')
    ip = request.remote_addr
    
    success, message = reactivate_player(player_id, admin_user_id=admin_id, reason=reason, ip_address=ip)
    
    if success:
        flash('Account reactivated', 'success')
    else:
        flash(f'Error: {message}', 'error')
    
    return redirect(url_for('master.player_detail', player_id=player_id))


@master_bp.route('/player/<int:player_id>/delete-permanent', methods=['POST'])
@admin_required
def player_delete_permanent(player_id):
    """Permanently delete a player account. Only for inactive accounts."""
    from .database import get_db
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check player exists and is inactive
    cursor.execute('SELECT id, nickname, is_active, email FROM players WHERE id = ?', (player_id,))
    player = cursor.fetchone()
    
    if not player:
        conn.close()
        flash('Player not found', 'error')
        return redirect(url_for('master.players'))
    
    player = dict(player)
    
    # Safety check - only delete inactive accounts
    if player.get('is_active', 1) == 1:
        conn.close()
        flash('Cannot delete active accounts. Deactivate first.', 'error')
        return redirect(url_for('master.player_detail', player_id=player_id))
    
    nickname = player['nickname']
    
    # Delete related records first (foreign key cleanup)
    cursor.execute('DELETE FROM queue WHERE player_id = ?', (player_id,))
    cursor.execute('DELETE FROM token_transactions WHERE player_id = ?', (player_id,))
    cursor.execute('DELETE FROM game_history WHERE winner_id = ? OR loser_id = ?', (player_id, player_id))
    
    # Try to delete from other tables (may not exist, so ignore errors)
    for table in ['player_friendships', 'friend_requests', 'challenges', 'pool_night_rsvps', 
                  'active_matches', 'player_reports', 'post_session_surveys']:
        try:
            cursor.execute(f'DELETE FROM {table} WHERE player_id = ?', (player_id,))
        except:
            pass
        try:
            cursor.execute(f'DELETE FROM {table} WHERE reported_player_id = ?', (player_id,))
        except:
            pass
    
    # Delete the player
    cursor.execute('DELETE FROM players WHERE id = ?', (player_id,))
    conn.commit()
    conn.close()
    
    flash(f'Permanently deleted account: {nickname}', 'success')
    return redirect(url_for('master.players'))


@master_bp.route('/player/<int:player_id>/reset-password', methods=['POST'])
@admin_required
def player_reset_password(player_id):
    """Reset a player's password from the admin panel."""
    from .database import get_db
    from werkzeug.security import generate_password_hash
    
    new_password = request.form.get('new_password', '').strip()
    
    if len(new_password) < 6:
        flash('Password must be at least 6 characters', 'error')
        return redirect(url_for('master.player_detail', player_id=player_id))
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get player's account_id
    cursor.execute('SELECT account_id, nickname FROM players WHERE id = ?', (player_id,))
    player = cursor.fetchone()
    
    if not player:
        conn.close()
        flash('Player not found', 'error')
        return redirect(url_for('master.players'))
    
    player = dict(player)
    account_id = player.get('account_id')
    
    if not account_id:
        conn.close()
        flash('Player does not have an account (guest player)', 'error')
        return redirect(url_for('master.player_detail', player_id=player_id))
    
    # Update password in accounts table
    password_hash = generate_password_hash(new_password, method='scrypt')
    cursor.execute('UPDATE accounts SET password_hash = ? WHERE id = ?', (password_hash, account_id))
    conn.commit()
    conn.close()
    
    flash(f'Password reset for {player["nickname"]}', 'success')
    return redirect(url_for('master.player_detail', player_id=player_id))


@master_bp.route('/leaderboard')
@admin_required
def leaderboard():
    """Global leaderboard."""
    players = get_leaderboard(100)
    season = get_current_season()
    return render_template('master/leaderboard.html', players=players, season=season)

@master_bp.route('/reports')
@admin_required
def reports():
    """Player reports management."""
    print("[MASTER] Reports page loaded")
    pending = get_pending_reports()
    embed = request.args.get('embed', '0') == '1'
    return render_template('master/reports.html', reports=pending, active_page='reports', embed=embed)


# ============================================
# POOL NIGHTS MANAGEMENT
# ============================================

@master_bp.route('/pool-nights')
@admin_required
def pool_nights():
    """Pool nights management - view, approve, reject submissions."""
    print("[MASTER] Pool nights page loaded")
    
    # Get filter params - default to 'upcoming' if not specified
    status_filter = request.args.get('status', 'upcoming')
    bar_id = request.args.get('bar_id', type=int)
    
    # Import helper functions
    from .database import get_pool_nights_events, get_pool_nights_stats
    
    # Get real stats
    stats = get_pool_nights_stats()
    
    # Convert 'all' to None for the query (get all events)
    query_status = None if status_filter == 'all' else status_filter
    
    # Get pool night events from database
    events = get_pool_nights_events(status=query_status, bar_id=bar_id)
    
    # Get list of bars for the create form
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM bars WHERE is_active = 1 ORDER BY name')
    bars = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return render_template('master/pool_nights.html',
                           events=events,
                           bars=bars,
                           total_nights=stats['total_nights'],
                           pending_count=stats['pending_count'],
                           accepted_count=stats['accepted_count'],
                           rejected_count=stats['rejected_count'],
                           cancelled_count=stats['cancelled_count'],
                           upcoming_count=stats['upcoming_count'],
                           current_filter=status_filter,
                           active_page='pool_nights')

@master_bp.route('/pool-nights/create', methods=['POST'])
@admin_required
def create_pool_night():
    """Create a new pool night event."""
    bar_id = request.form.get('bar_id', type=int)
    event_date = request.form.get('event_date')
    start_time = request.form.get('start_time')
    title = request.form.get('name', '').strip()
    game_type = request.form.get('game_type', 'ranked')
    description = request.form.get('rules', '').strip()
    max_players = request.form.get('max_players', type=int)
    entry_fee = request.form.get('entry_fee', type=float) or 0.00
    
    # Tournament fields
    event_style = request.form.get('event_style', 'casual')
    elimination_type = request.form.get('elimination_type', 'single')
    seeding_method = request.form.get('seeding_method', 'random')
    bracket_size = request.form.get('bracket_size', type=int)
    registration_deadline = request.form.get('registration_deadline')
    race_to = request.form.get('race_to', type=int) or 1
    is_ranked = request.form.get('is_ranked', '0') == '1'
    
    if not bar_id or not event_date:
        flash('Bar and date are required', 'error')
        return redirect(url_for('master.pool_nights'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO pool_nights (bar_id, host_id, title, event_date, start_time, game_type, 
                                 description, max_players, entry_fee, status, created_at,
                                 format, elimination_type, seeding_method, bracket_size, 
                                 registration_deadline, race_to, ranked_required)
        VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?, 'approved', datetime('now'),
                ?, ?, ?, ?, ?, ?, ?)
    ''', (bar_id, title or 'Pool Night', event_date, start_time, game_type, description, 
          max_players, entry_fee, event_style, elimination_type, seeding_method, 
          bracket_size, registration_deadline, race_to, 1 if is_ranked else 0))
    
    pool_night_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    flash('Pool night created successfully!', 'success')
    
    # Redirect to tournament detail if it's a tournament
    if event_style == 'tournament':
        return redirect(url_for('master.tournament_detail', night_id=pool_night_id))
    
    return redirect(url_for('master.pool_nights'))

@master_bp.route('/pool-nights/<int:night_id>/accept', methods=['POST'])
@admin_required
def accept_pool_night(night_id):
    """Accept a pool night submission."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE pool_nights SET status = 'approved', approved_at = datetime('now')
        WHERE id = ?
    ''', (night_id,))
    conn.commit()
    conn.close()
    
    flash('Pool night accepted!', 'success')
    return redirect(url_for('master.pool_nights'))


@master_bp.route('/pool-nights/<int:night_id>/set-ranked', methods=['POST'])
@admin_required
def set_pool_night_ranked(night_id):
    """Toggle ranked requirement for a pool night."""
    from .database import set_pool_night_ranked as db_set_ranked
    
    ranked = request.form.get('ranked', '0') == '1'
    db_set_ranked(night_id, ranked)
    
    flash(f'Pool night {"marked as ranked-required" if ranked else "set to optional ranking"}', 'success')
    return redirect(url_for('master.pool_nights'))


@master_bp.route('/pool-nights/<int:night_id>/reject', methods=['POST'])
@admin_required
def reject_pool_night(night_id):
    """Reject a pool night submission."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE pool_nights SET status = 'rejected'
        WHERE id = ?
    ''', (night_id,))
    conn.commit()
    conn.close()
    
    flash('Pool night rejected.', 'info')
    return redirect(url_for('master.pool_nights'))


@master_bp.route('/pool-nights/<int:night_id>/cancel', methods=['POST'])
@admin_required
def cancel_pool_night(night_id):
    """Cancel an approved pool night."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if pool night exists
    cursor.execute('SELECT id, status FROM pool_nights WHERE id = ?', (night_id,))
    night = cursor.fetchone()
    
    if not night:
        conn.close()
        flash('Pool night not found.', 'error')
        return redirect(url_for('master.pool_nights'))
    
    # Update to cancelled status
    cursor.execute('''
        UPDATE pool_nights 
        SET status = 'cancelled', cancelled_at = datetime('now')
        WHERE id = ?
    ''', (night_id,))
    conn.commit()
    conn.close()
    
    flash('Pool night cancelled.', 'info')
    return redirect(url_for('master.pool_nights'))


@master_bp.route('/pool-nights/<int:night_id>')
@admin_required
def pool_night_detail(night_id):
    """View details for a specific pool night."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get pool night with bar name
    cursor.execute('''
        SELECT pn.*, b.name as bar_name
        FROM pool_nights pn
        LEFT JOIN bars b ON pn.bar_id = b.id
        WHERE pn.id = ?
    ''', (night_id,))
    night = cursor.fetchone()
    
    if not night:
        conn.close()
        flash('Pool night not found.', 'error')
        return redirect(url_for('master.pool_nights'))
    
    night = dict(night)
    event_date = night.get('event_date')
    bar_id = night.get('bar_id')
    
    # Get RSVP list with player names and payment status
    cursor.execute('''
        SELECT r.*, p.nickname, p.email
        FROM pool_night_rsvps r
        JOIN players p ON r.player_id = p.id
        WHERE r.pool_night_id = ? AND r.cancelled = 0
        ORDER BY r.rsvp_at ASC
    ''', (night_id,))
    rsvps = [dict(row) for row in cursor.fetchall()]
    
    # Get RSVPs with paid status counts
    paid_count = sum(1 for r in rsvps if r.get('paid'))
    total_collected = sum(float(r.get('amount_paid', 0) or 0) for r in rsvps if r.get('paid'))
    
    # Get existing payouts
    cursor.execute('''
        SELECT pp.*, p.nickname
        FROM pool_night_payouts pp
        JOIN players p ON pp.player_id = p.id
        WHERE pp.pool_night_id = ?
        ORDER BY pp.placement ASC
    ''', (night_id,))
    payouts = [dict(row) for row in cursor.fetchall()]
    
    # Get games stats for that night at that bar
    games_stats = {'games_count': 0, 'unique_players': 0}
    try:
        cursor.execute('''
            SELECT 
                COUNT(*) as games_count,
                COUNT(DISTINCT winner_id) + COUNT(DISTINCT loser_id) as player_appearances
            FROM game_history
            WHERE bar_id = ? AND date(played_at) = ?
        ''', (bar_id, event_date))
        row = cursor.fetchone()
        if row:
            games_stats['games_count'] = row['games_count'] or 0
            games_stats['unique_players'] = row['player_appearances'] or 0
    except Exception as e:
        print(f"[POOL_NIGHT_DETAIL] Error getting games stats: {e}")
    
    # Get POS stats for that night at that bar
    pos_stats = {'checks_count': 0, 'total_revenue': 0, 'avg_check_amount': 0}
    try:
        # Check if pos_checks table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pos_checks'")
        if cursor.fetchone():
            cursor.execute('''
                SELECT 
                    COUNT(*) as checks_count,
                    COALESCE(SUM(total_amount), 0) as total_revenue,
                    COALESCE(AVG(total_amount), 0) as avg_check_amount
                FROM pos_checks
                WHERE bar_id = ? AND business_date = ?
            ''', (bar_id, event_date))
            row = cursor.fetchone()
            if row:
                pos_stats['checks_count'] = row['checks_count'] or 0
                pos_stats['total_revenue'] = round(row['total_revenue'] or 0, 2)
                pos_stats['avg_check_amount'] = round(row['avg_check_amount'] or 0, 2)
    except Exception as e:
        print(f"[POOL_NIGHT_DETAIL] Error getting POS stats: {e}")
    
    conn.close()
    
    return render_template('master/pool_night_detail.html',
                           night=night,
                           rsvps=rsvps,
                           paid_count=paid_count,
                           total_collected=total_collected,
                           payouts=payouts,
                           games_stats=games_stats,
                           pos_stats=pos_stats,
                           active_page='pool_nights')


# ==============================================================================
# TOURNAMENT MANAGEMENT
# ==============================================================================

@master_bp.route('/tournament/<int:night_id>')
@admin_required
def tournament_detail(night_id):
    """View and manage a tournament bracket."""
    from .database import get_tournament_bracket, get_tournament_participants
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get pool night with bar name
    cursor.execute('''
        SELECT pn.*, b.name as bar_name
        FROM pool_nights pn
        LEFT JOIN bars b ON pn.bar_id = b.id
        WHERE pn.id = ?
    ''', (night_id,))
    night = cursor.fetchone()
    
    if not night:
        conn.close()
        flash('Tournament not found.', 'error')
        return redirect(url_for('master.pool_nights'))
    
    night = dict(night)
    conn.close()
    
    # Get participants and bracket
    participants = get_tournament_participants(night_id)
    bracket_data = get_tournament_bracket(night_id)
    
    # Get list of all players for add participant modal
    conn2 = get_db()
    cursor2 = conn2.cursor()
    cursor2.execute('''
        SELECT id, nickname, rating FROM players 
        WHERE account_id IS NOT NULL AND (is_active = 1 OR is_active IS NULL)
        ORDER BY nickname ASC
    ''')
    all_players = [dict(row) for row in cursor2.fetchall()]
    conn2.close()
    
    # Filter out already registered participants
    registered_ids = {p['player_id'] for p in participants}
    available_players = [p for p in all_players if p['id'] not in registered_ids]
    
    return render_template('master/tournament_detail.html',
                           night=night,
                           participants=participants,
                           bracket=bracket_data,
                           available_players=available_players,
                           active_page='pool_nights')


@master_bp.route('/tournament/<int:night_id>/generate-bracket', methods=['POST'])
@admin_required
def generate_bracket(night_id):
    """Generate the tournament bracket from registered participants."""
    from .database import generate_tournament_bracket
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT seeding_method FROM pool_nights WHERE id = ?', (night_id,))
    row = cursor.fetchone()
    conn.close()
    
    seeding = row['seeding_method'] if row else 'random'
    result = generate_tournament_bracket(night_id, seeding)
    
    if result['success']:
        flash(f'Bracket generated! {result["bracket_size"]} slots, {result["num_rounds"]} rounds.', 'success')
    else:
        flash(f'Error: {result.get("error", "Unknown error")}', 'error')
    
    return redirect(url_for('master.tournament_detail', night_id=night_id))


@master_bp.route('/tournament/<int:night_id>/start', methods=['POST'])
@admin_required
def start_tournament(night_id):
    """Start the tournament."""
    from .database import start_tournament as db_start_tournament
    
    result = db_start_tournament(night_id)
    if result['success']:
        flash('Tournament started!', 'success')
    else:
        flash('Could not start tournament.', 'error')
    
    return redirect(url_for('master.tournament_detail', night_id=night_id))


@master_bp.route('/tournament/<int:night_id>/add-participant', methods=['POST'])
@admin_required
def add_tournament_participant(night_id):
    """Add a player to the tournament."""
    from .database import register_tournament_participant
    
    player_id = request.form.get('player_id', type=int)
    if not player_id:
        flash('Player ID required.', 'error')
        return redirect(url_for('master.tournament_detail', night_id=night_id))
    
    result = register_tournament_participant(night_id, player_id)
    if result['success']:
        flash('Player added to tournament.', 'success')
    else:
        flash(f'Error: {result.get("error", "Unknown error")}', 'error')
    
    return redirect(url_for('master.tournament_detail', night_id=night_id))


@master_bp.route('/tournament/match/<int:match_id>/result', methods=['POST'])
@admin_required
def record_match_result(match_id):
    """Record the result of a tournament match."""
    from .database import record_tournament_match_result
    
    winner_id = request.form.get('winner_id', type=int)
    player1_score = request.form.get('player1_score', type=int) or 0
    player2_score = request.form.get('player2_score', type=int) or 0
    forfeit = request.form.get('forfeit') == '1'
    forfeit_player_id = request.form.get('forfeit_player_id', type=int)
    
    if not winner_id:
        flash('Winner must be selected.', 'error')
        return redirect(request.referrer or url_for('master.pool_nights'))
    
    result = record_tournament_match_result(match_id, winner_id, player1_score, player2_score, forfeit, forfeit_player_id)
    
    if result['success']:
        flash('Match result recorded!', 'success')
    else:
        flash(f'Error: {result.get("error", "Unknown error")}', 'error')
    
    # Get the pool_night_id to redirect back
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT pool_night_id FROM tournament_matches WHERE id = ?', (match_id,))
    row = cursor.fetchone()
    conn.close()
    
    night_id = row['pool_night_id'] if row else None
    if night_id:
        return redirect(url_for('master.tournament_detail', night_id=night_id))
    return redirect(url_for('master.pool_nights'))


@master_bp.route('/tournament/match/<int:match_id>/forfeit', methods=['POST'])
@admin_required
def forfeit_match(match_id):
    """Handle a forfeit in a tournament match."""
    from .database import record_tournament_match_result
    
    forfeit_player_id = request.form.get('forfeit_player_id', type=int)
    
    # Get match details
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tournament_matches WHERE id = ?', (match_id,))
    match = cursor.fetchone()
    conn.close()
    
    if not match:
        flash('Match not found.', 'error')
        return redirect(url_for('master.pool_nights'))
    
    match = dict(match)
    
    # Winner is the other player
    if forfeit_player_id == match['player1_id']:
        winner_id = match['player2_id']
    else:
        winner_id = match['player1_id']
    
    result = record_tournament_match_result(match_id, winner_id, forfeit=True, forfeit_player_id=forfeit_player_id)
    
    if result['success']:
        flash('Forfeit recorded.', 'info')
    else:
        flash(f'Error: {result.get("error")}', 'error')
    
    return redirect(url_for('master.tournament_detail', night_id=match['pool_night_id']))


@master_bp.route('/api/tournament/<int:night_id>/bracket')
@admin_required
def api_tournament_bracket(night_id):
    """API endpoint for tournament bracket data (for live updates)."""
    from .database import get_tournament_bracket
    
    bracket_data = get_tournament_bracket(night_id)
    return jsonify(bracket_data)


@master_bp.route('/reports/<int:report_id>/resolve', methods=['POST'])
@admin_required
def resolve_report(report_id):
    """Resolve a player report."""
    action = request.form.get('action')
    
    conn = get_db()
    cursor = conn.cursor()
    
    if action == 'ban':
        days = request.form.get('days', type=int)
        cursor.execute('SELECT reported_player_id FROM player_reports WHERE id = ?', (report_id,))
        row = cursor.fetchone()
        if row:
            ban_player(row['reported_player_id'], 'Banned due to report', days)
    
    cursor.execute('''UPDATE player_reports SET status = ?, resolved_at = CURRENT_TIMESTAMP, action_taken = ?
                      WHERE id = ?''', ('resolved', action, report_id))
    conn.commit()
    conn.close()


# ==============================================================================
# POOL NIGHT PAYOUTS
# ==============================================================================

@master_bp.route('/pool-nights/<int:night_id>/record-payout', methods=['POST'])
@admin_required
def record_pool_night_payout(night_id):
    """Record a payout/winnings for a pool night participant."""
    from .database import record_pool_night_payout
    
    player_id = request.form.get('player_id', type=int)
    amount = request.form.get('amount', type=float)
    placement = request.form.get('placement', type=int) or 0
    
    if not player_id or not amount:
        flash('Player and amount are required', 'error')
        return redirect(url_for('master.pool_night_detail', night_id=night_id))
    
    if amount <= 0:
        flash('Amount must be positive', 'error')
        return redirect(url_for('master.pool_night_detail', night_id=night_id))
    
    success, message = record_pool_night_payout(night_id, player_id, amount, placement)
    
    if success:
        flash(f'Payout of ${amount:.2f} recorded successfully!', 'success')
    else:
        flash(f'Error: {message}', 'error')
    
    return redirect(url_for('master.pool_night_detail', night_id=night_id))
    
    flash(f'Report resolved: {action}', 'success')
    return redirect(url_for('master.reports'))

@master_bp.route('/bars')
@admin_required
def bars():
    """All bars management."""
    print("[MASTER] Bars page loaded")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM bars ORDER BY name')
    all_bars = [dict(row) for row in cursor.fetchall()]
    conn.close()
    embed = request.args.get('embed', '0') == '1'
    return render_template('master/bars.html', bars=all_bars, active_page='bars', embed=embed)

@master_bp.route('/bars/add', methods=['POST'])
@admin_required
def add_bar():
    """Add a new bar."""
    name = request.form.get('name')
    phone = request.form.get('phone', '')
    email = request.form.get('email', '')
    address = request.form.get('address', '')
    borough_raw = request.form.get('borough', '')
    # Normalize borough to canonical form (e.g., "brooklyn" -> "Brooklyn")
    borough = normalize_borough(borough_raw) or borough_raw
    neighborhood = request.form.get('neighborhood', '')
    zip_code = request.form.get('zip', '')
    tables = request.form.get('tables', 2)
    table_type = request.form.get('table_type', 'bar')
    venue_type = request.form.get('venue_type', 'bar')
    open_time = request.form.get('open_time', '16:00')
    close_time = request.form.get('close_time', '02:00')
    contact_name = request.form.get('contact_name', '')
    contact_phone = request.form.get('contact_phone', '')
    contact_email = request.form.get('contact_email', '')
    website = request.form.get('website', '')
    instagram = request.form.get('instagram', '')
    google_review_url = request.form.get('google_review_url', '')
    notes = request.form.get('notes', '')
    
    # Set city/state based on borough (NYC bars)
    city = 'New York'
    state = 'NY'
    
    # Generate unique bar code
    import random
    import string
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO bars (name, code, phone, email, address, city, state, borough, neighborhood, 
                         zip_code, table_count, table_type, venue_type, open_time, close_time,
                         contact_name, contact_phone, contact_email, website, 
                         instagram, google_review_url, notes, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
    ''', (name, code, phone, email, address, city, state, borough, neighborhood, zip_code,
          tables, table_type, venue_type, open_time, close_time, contact_name,
          contact_phone, contact_email, website, instagram, google_review_url, notes))
    bar_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # Create table records with unique QR codes for each table
    from .database import ensure_bar_tables
    ensure_bar_tables(bar_id, int(tables) if tables else 1)
    
    flash(f'Added bar: {name}', 'success')
    return redirect(url_for('master.bars'))

@master_bp.route('/bars/<int:bar_id>/toggle', methods=['POST'])
@admin_required
def toggle_bar(bar_id):
    """Toggle bar active status."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE bars SET is_active = NOT is_active WHERE id = ?', (bar_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('master.bars'))

@master_bp.route('/bar/<int:bar_id>/edit', methods=['POST'])
@admin_required
def edit_bar(bar_id):
    """Edit bar details."""
    name = request.form.get('name')
    phone = request.form.get('phone', '')
    email = request.form.get('email', '')
    address = request.form.get('address', '')
    borough = request.form.get('borough', '')
    neighborhood = request.form.get('neighborhood', '')
    zip_code = request.form.get('zip', '')
    table_count = request.form.get('tables', 2)
    table_type = request.form.get('table_type', 'bar')
    venue_type = request.form.get('venue_type', 'bar')
    open_time = request.form.get('open_time', '16:00')
    close_time = request.form.get('close_time', '02:00')
    contact_name = request.form.get('contact_name', '')
    contact_phone = request.form.get('contact_phone', '')
    contact_email = request.form.get('contact_email', '')
    website = request.form.get('website', '')
    instagram = request.form.get('instagram', '')
    notes = request.form.get('notes', '')
    is_active = 1 if request.form.get('is_active') else 0
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE bars SET 
            name = ?, phone = ?, email = ?, address = ?, borough = ?,
            neighborhood = ?, zip = ?, table_count = ?, table_type = ?,
            venue_type = ?, open_time = ?, close_time = ?, 
            contact_name = ?, contact_phone = ?, contact_email = ?,
            website = ?, instagram = ?, notes = ?, is_active = ?
        WHERE id = ?
    ''', (name, phone, email, address, borough, neighborhood, zip_code, 
          table_count, table_type, venue_type, open_time, close_time,
          contact_name, contact_phone, contact_email, website, instagram, 
          notes, is_active, bar_id))
    conn.commit()
    conn.close()
    
    # Update table records (create new ones, deactivate excess)
    from .database import ensure_bar_tables
    ensure_bar_tables(bar_id, int(table_count) if table_count else 1)
    
    flash(f'Updated bar: {name}', 'success')
    return redirect(url_for('master.bar_detail', bar_id=bar_id))


@master_bp.route('/managers')
@admin_required
def all_managers():
    """View all bar managers across all bars."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT bm.*, b.name as bar_name 
        FROM bar_managers bm
        LEFT JOIN bars b ON bm.bar_id = b.id
        ORDER BY b.name, bm.name
    ''')
    managers = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute('SELECT id, name FROM bars ORDER BY name')
    bars = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return render_template('master/managers.html', managers=managers, bars=bars)


@master_bp.route('/managers/add', methods=['POST'])
@admin_required
def add_manager():
    """Add a new bar manager."""
    from werkzeug.security import generate_password_hash
    
    bar_id = request.form.get('bar_id')
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '').strip()
    
    if not all([bar_id, name, email, password]):
        flash('All fields are required', 'error')
        return redirect(url_for('master.all_managers'))
    
    if len(password) < 6:
        flash('Password must be at least 6 characters', 'error')
        return redirect(url_for('master.all_managers'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if email already exists
    cursor.execute('SELECT id FROM bar_managers WHERE email = ?', (email,))
    if cursor.fetchone():
        conn.close()
        flash('Email already registered as a manager', 'error')
        return redirect(url_for('master.all_managers'))
    
    password_hash = generate_password_hash(password, method='scrypt')
    cursor.execute('''
        INSERT INTO bar_managers (bar_id, email, password_hash, name, role, is_active)
        VALUES (?, ?, ?, ?, 'manager', 1)
    ''', (bar_id, email, password_hash, name))
    conn.commit()
    conn.close()
    
    flash(f'Manager {name} added successfully', 'success')
    return redirect(url_for('master.all_managers'))


@master_bp.route('/managers/<int:manager_id>/reset-password', methods=['POST'])
@admin_required
def manager_reset_password(manager_id):
    """Reset a manager's password."""
    from werkzeug.security import generate_password_hash
    
    new_password = request.form.get('new_password', '').strip()
    
    if len(new_password) < 6:
        flash('Password must be at least 6 characters', 'error')
        return redirect(url_for('master.all_managers'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT name FROM bar_managers WHERE id = ?', (manager_id,))
    manager = cursor.fetchone()
    
    if not manager:
        conn.close()
        flash('Manager not found', 'error')
        return redirect(url_for('master.all_managers'))
    
    password_hash = generate_password_hash(new_password, method='scrypt')
    cursor.execute('UPDATE bar_managers SET password_hash = ? WHERE id = ?', (password_hash, manager_id))
    conn.commit()
    conn.close()
    
    flash(f'Password reset for {manager["name"]}', 'success')
    return redirect(url_for('master.all_managers'))


@master_bp.route('/managers/<int:manager_id>/toggle', methods=['POST'])
@admin_required
def toggle_manager(manager_id):
    """Toggle manager active status."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT is_active, name FROM bar_managers WHERE id = ?', (manager_id,))
    manager = cursor.fetchone()
    
    if not manager:
        conn.close()
        flash('Manager not found', 'error')
        return redirect(url_for('master.all_managers'))
    
    new_status = 0 if manager['is_active'] else 1
    cursor.execute('UPDATE bar_managers SET is_active = ? WHERE id = ?', (new_status, manager_id))
    conn.commit()
    conn.close()
    
    status_text = 'activated' if new_status else 'deactivated'
    flash(f'{manager["name"]} {status_text}', 'success')
    return redirect(url_for('master.all_managers'))


@master_bp.route('/managers/<int:manager_id>/delete', methods=['POST'])
@admin_required
def delete_manager(manager_id):
    """Delete a bar manager."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT name FROM bar_managers WHERE id = ?', (manager_id,))
    manager = cursor.fetchone()
    
    if not manager:
        conn.close()
        flash('Manager not found', 'error')
        return redirect(url_for('master.all_managers'))
    
    cursor.execute('DELETE FROM bar_managers WHERE id = ?', (manager_id,))
    conn.commit()
    conn.close()
    
    flash(f'Manager {manager["name"]} deleted', 'success')
    return redirect(url_for('master.all_managers'))


@master_bp.route('/bar/<int:bar_id>/delete-permanent', methods=['POST'])
@admin_required
def delete_bar_permanent(bar_id):
    """Permanently delete a bar and all associated data."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get bar name for flash message
    cursor.execute('SELECT name FROM bars WHERE id = ?', (bar_id,))
    bar = cursor.fetchone()
    bar_name = bar['name'] if bar else 'Unknown'
    
    # Delete all associated data
    # 1. Queue entries for this bar
    cursor.execute('DELETE FROM queue WHERE bar_id = ?', (bar_id,))
    
    # 2. Game history for this bar
    cursor.execute('DELETE FROM game_history WHERE bar_id = ?', (bar_id,))
    
    # 3. Queue usage logs for this bar
    cursor.execute('DELETE FROM queue_usage_log WHERE bar_id = ?', (bar_id,))
    
    # 4. Auto invites for this bar
    cursor.execute('DELETE FROM auto_invites WHERE bar_id = ?', (bar_id,))
    
    # 5. Bar tables
    cursor.execute('DELETE FROM bar_tables WHERE bar_id = ?', (bar_id,))
    
    # 6. Bar ranked windows
    cursor.execute('DELETE FROM bar_ranked_windows WHERE bar_id = ?', (bar_id,))
    
    # 7. Settings for this bar
    cursor.execute('DELETE FROM settings WHERE bar_id = ?', (bar_id,))
    
    # 8. Game rules for this bar
    cursor.execute('DELETE FROM game_rules WHERE bar_id = ?', (bar_id,))
    
    # 9. Finally, delete the bar itself
    cursor.execute('DELETE FROM bars WHERE id = ?', (bar_id,))
    
    conn.commit()
    conn.close()
    
    flash(f'Permanently deleted bar: {bar_name}', 'success')
    return redirect(url_for('master.bars'))


# ============================================================================
# BAR MANAGER ACCOUNTS
# ============================================================================

@master_bp.route('/bar/<int:bar_id>/managers')
@admin_required
def bar_managers(bar_id):
    """Manage bar manager accounts for a specific bar."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM bars WHERE id = ?', (bar_id,))
    bar = cursor.fetchone()
    if not bar:
        flash('Bar not found', 'error')
        return redirect(url_for('master.bars'))
    
    cursor.execute('SELECT * FROM bar_managers WHERE bar_id = ? ORDER BY created_at DESC', (bar_id,))
    managers = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return render_template('master/bar_managers.html', bar=dict(bar), managers=managers)


@master_bp.route('/bar/<int:bar_id>/managers/add', methods=['POST'])
@admin_required
def add_bar_manager(bar_id):
    """Create a new bar manager account."""
    from werkzeug.security import generate_password_hash
    
    email = request.form.get('email', '').strip().lower()
    name = request.form.get('name', '').strip()
    password = request.form.get('password', '')
    role = request.form.get('role', 'manager')
    
    if not email or not password:
        flash('Email and password required', 'error')
        return redirect(url_for('master.bar_managers', bar_id=bar_id))
    
    if len(password) < 8:
        flash('Password must be at least 8 characters', 'error')
        return redirect(url_for('master.bar_managers', bar_id=bar_id))
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if email already exists
    cursor.execute('SELECT id FROM bar_managers WHERE email = ?', (email,))
    if cursor.fetchone():
        conn.close()
        flash('Email already in use', 'error')
        return redirect(url_for('master.bar_managers', bar_id=bar_id))
    
    cursor.execute('''
        INSERT INTO bar_managers (bar_id, email, password_hash, name, role)
        VALUES (?, ?, ?, ?, ?)
    ''', (bar_id, email, generate_password_hash(password), name, role))
    conn.commit()
    conn.close()
    
    flash(f'Bar manager account created for {email}', 'success')
    return redirect(url_for('master.bar_managers', bar_id=bar_id))


@master_bp.route('/bar-manager/<int:manager_id>/delete', methods=['POST'])
@admin_required
def delete_bar_manager(manager_id):
    """Delete a bar manager account."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT bar_id, email FROM bar_managers WHERE id = ?', (manager_id,))
    manager = cursor.fetchone()
    if not manager:
        flash('Manager not found', 'error')
        return redirect(url_for('master.bars'))
    
    bar_id = manager['bar_id']
    cursor.execute('DELETE FROM bar_managers WHERE id = ?', (manager_id,))
    conn.commit()
    conn.close()
    
    flash(f'Deleted manager: {manager["email"]}', 'success')
    return redirect(url_for('master.bar_managers', bar_id=bar_id))


@master_bp.route('/bar/<int:bar_id>/managers/<int:manager_id>/toggle', methods=['POST'])
@admin_required
def toggle_bar_manager(bar_id, manager_id):
    """Activate or deactivate a bar manager."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT is_active FROM bar_managers WHERE id = ? AND bar_id = ?', (manager_id, bar_id))
    manager = cursor.fetchone()
    
    if not manager:
        conn.close()
        flash('Manager not found', 'error')
        return redirect(url_for('master.bar_managers', bar_id=bar_id))
    
    new_status = 0 if manager['is_active'] else 1
    cursor.execute('UPDATE bar_managers SET is_active = ? WHERE id = ?', (new_status, manager_id))
    conn.commit()
    conn.close()
    
    flash(f'Manager {"activated" if new_status else "deactivated"}', 'success')
    return redirect(url_for('master.bar_managers', bar_id=bar_id))


@master_bp.route('/bar/<int:bar_id>/managers/<int:manager_id>/reset-password', methods=['POST'])
@admin_required
def reset_bar_manager_password(bar_id, manager_id):
    """Reset a bar manager's password."""
    new_password = request.form.get('password', '')
    
    if len(new_password) < 8:
        flash('Password must be at least 8 characters', 'error')
        return redirect(url_for('master.bar_managers', bar_id=bar_id))
    
    conn = get_db()
    cursor = conn.cursor()
    
    password_hash = generate_password_hash(new_password, method='scrypt')
    cursor.execute('UPDATE bar_managers SET password_hash = ? WHERE id = ? AND bar_id = ?', 
                   (password_hash, manager_id, bar_id))
    conn.commit()
    conn.close()
    
    flash('Password reset successfully', 'success')
    return redirect(url_for('master.bar_managers', bar_id=bar_id))


@master_bp.route('/ads')
@admin_required
def ads():
    """Redirect old ads page to new advertisers system."""
    return redirect(url_for('master.advertisers'))

@master_bp.route('/ads/delete/<filename>', methods=['POST'])
@admin_required
def delete_ad(filename):
    """Delete an ad."""
    filepath = os.path.join(ADS_FOLDER, filename)
    if os.path.exists(filepath):
        os.remove(filepath)
        flash(f'Deleted: {filename}', 'success')
    return redirect(url_for('master.ads'))

@master_bp.route('/players/<int:player_id>/ban', methods=['POST'])
@admin_required
def ban_player_route(player_id):
    """Ban a player."""
    reason = request.form.get('reason', 'Banned by admin')
    days = request.form.get('days', type=int)
    ban_player(player_id, reason, days)
    flash('Player banned', 'success')
    return redirect(url_for('master.players'))

@master_bp.route('/players/<int:player_id>/unban', methods=['POST'])
@admin_required
def unban_player(player_id):
    """Unban a player."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM player_flags WHERE player_id = ?', (player_id,))
    conn.commit()
    conn.close()
    flash('Player unbanned', 'success')
    return redirect(url_for('master.players'))

@master_bp.route('/api/stats')
@admin_required
def api_stats():
    """JSON stats for real-time dashboard updates."""
    return jsonify(get_master_stats())

@master_bp.route('/analytics')
@admin_required
def analytics():
    """Analytics - Platform metrics and insights."""
    print("[MASTER] Analytics loaded")
    
    from datetime import date, timedelta, datetime as dt
    from .services.pos_analytics import (
        get_pos_summary_overall, get_brand_totals, 
        get_core_activity_summary, get_ad_summary,
        get_games_by_date, get_pos_by_date
    )
    
    # Date range - accept from request or default to last 30 days
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    # Parse user-provided dates safely
    start_param = request.args.get('start_date', '')
    end_param = request.args.get('end_date', '')
    
    if start_param:
        try:
            start_date = dt.strptime(start_param, '%Y-%m-%d').date()
        except ValueError:
            pass  # Keep default
    
    if end_param:
        try:
            end_date = dt.strptime(end_param, '%Y-%m-%d').date()
        except ValueError:
            pass  # Keep default
    
    # Ensure start <= end
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    
    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')
    
    # Optional bar_id filter
    bar_id = request.args.get('bar_id', type=int)
    
    # Get structured data from helper functions
    core = get_core_activity_summary(start_date_str, end_date_str, bar_id=bar_id)
    pos = get_pos_summary_overall(start_date_str, end_date_str, bar_id=bar_id)
    brands = get_brand_totals(start_date_str, end_date_str, bar_id=bar_id)
    ads = get_ad_summary(start_date_str, end_date_str, bar_id=bar_id)
    
    # Get time-series data for charts
    games_ts = get_games_by_date(start_date_str, end_date_str, bar_id=bar_id)
    pos_ts = get_pos_by_date(start_date_str, end_date_str, bar_id=bar_id)
    
    conn = get_db()
    cursor = conn.cursor()
    
    a = {}  # analytics dict
    
    # Structured data block
    a['date_range'] = {
        'start': start_date_str,
        'end': end_date_str
    }
    a['core'] = core
    a['pos'] = pos
    a['ads_summary'] = ads
    a['brands'] = brands
    
    # Time-series data for charts
    a['games_by_date'] = games_ts
    a['pos_by_date'] = pos_ts
    
    # ============================================
    # AD METRICS - Per Campaign, Per Bar, Per Placement
    # ============================================
    a['ad_campaigns'] = []
    a['ad_by_bar'] = []
    a['ad_by_placement'] = []
    
    try:
        # Check if ad_events table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ad_events'")
        has_ad_events = cursor.fetchone() is not None
        
        if has_ad_events:
            # Per-campaign ad metrics
            bar_filter = "AND ae.bar_id = ?" if bar_id else ""
            params = [start_date_str, end_date_str]
            if bar_id:
                params.append(bar_id)
            
            cursor.execute(f'''
                SELECT 
                    ae.campaign_id,
                    c.name as campaign_name,
                    adv.name as advertiser_name,
                    c.status,
                    c.start_date,
                    c.end_date,
                    SUM(CASE WHEN ae.event_type = 'impression' THEN 1 ELSE 0 END) as impressions,
                    SUM(CASE WHEN ae.event_type = 'click' THEN 1 ELSE 0 END) as clicks,
                    COUNT(DISTINCT ae.player_id) as unique_players
                FROM ad_events ae
                LEFT JOIN campaigns c ON ae.campaign_id = c.id
                LEFT JOIN advertisers adv ON ae.advertiser_id = adv.id
                WHERE date(ae.created_at) BETWEEN ? AND ?
                {bar_filter}
                GROUP BY ae.campaign_id
                ORDER BY impressions DESC
                LIMIT 20
            ''', params)
            
            for row in cursor.fetchall():
                impressions = row['impressions'] or 0
                clicks = row['clicks'] or 0
                ctr = round((clicks / impressions * 100), 1) if impressions > 0 else 0
                a['ad_campaigns'].append({
                    'campaign_id': row['campaign_id'],
                    'campaign_name': row['campaign_name'] or 'Unknown',
                    'advertiser_name': row['advertiser_name'] or 'Unknown',
                    'status': row['status'] or 'active',
                    'start_date': row['start_date'],
                    'end_date': row['end_date'],
                    'impressions': impressions,
                    'clicks': clicks,
                    'ctr': ctr,
                    'unique_players': row['unique_players'] or 0
                })
            
            # Per-bar ad metrics
            cursor.execute(f'''
                SELECT 
                    ae.bar_id,
                    b.name as bar_name,
                    SUM(CASE WHEN ae.event_type = 'impression' THEN 1 ELSE 0 END) as impressions,
                    SUM(CASE WHEN ae.event_type = 'click' THEN 1 ELSE 0 END) as clicks
                FROM ad_events ae
                LEFT JOIN bars b ON ae.bar_id = b.id
                WHERE date(ae.created_at) BETWEEN ? AND ?
                GROUP BY ae.bar_id
                ORDER BY impressions DESC
                LIMIT 10
            ''', (start_date_str, end_date_str))
            
            for row in cursor.fetchall():
                impressions = row['impressions'] or 0
                clicks = row['clicks'] or 0
                ctr = round((clicks / impressions * 100), 1) if impressions > 0 else 0
                a['ad_by_bar'].append({
                    'bar_id': row['bar_id'],
                    'bar_name': row['bar_name'] or 'Unknown',
                    'impressions': impressions,
                    'clicks': clicks,
                    'ctr': ctr
                })
            
            # Per-placement ad metrics
            cursor.execute(f'''
                SELECT 
                    ae.placement,
                    SUM(CASE WHEN ae.event_type = 'impression' THEN 1 ELSE 0 END) as impressions,
                    SUM(CASE WHEN ae.event_type = 'click' THEN 1 ELSE 0 END) as clicks,
                    COUNT(DISTINCT date(ae.created_at)) as active_days
                FROM ad_events ae
                WHERE date(ae.created_at) BETWEEN ? AND ?
                {bar_filter}
                GROUP BY ae.placement
                ORDER BY impressions DESC
            ''', params)
            
            for row in cursor.fetchall():
                impressions = row['impressions'] or 0
                clicks = row['clicks'] or 0
                active_days = row['active_days'] or 1
                ctr = round((clicks / impressions * 100), 1) if impressions > 0 else 0
                avg_per_day = round(impressions / active_days, 1) if active_days > 0 else 0
                a['ad_by_placement'].append({
                    'placement': row['placement'] or 'unknown',
                    'impressions': impressions,
                    'clicks': clicks,
                    'ctr': ctr,
                    'avg_per_day': avg_per_day
                })
    except Exception as e:
        print(f"[ANALYTICS] Ad metrics query error: {e}")
    
    # Player stats
    cursor.execute('SELECT COUNT(*) FROM players')
    a['players_total'] = cursor.fetchone()[0] or 0
    
    # Active in last 30 days (players with games in last 30 days)
    cursor.execute('''
        SELECT COUNT(DISTINCT p.id) FROM players p
        JOIN game_history g ON g.winner_id = p.id OR g.loser_id = p.id
        WHERE g.played_at >= datetime('now', '-30 days')
    ''')
    a['players_active_30d'] = cursor.fetchone()[0] or 0
    
    # Total games
    cursor.execute('SELECT COUNT(*) FROM game_history')
    a['games_total'] = cursor.fetchone()[0] or 0
    
    # Games per player avg
    a['games_per_player'] = round(a['games_total'] / a['players_total'], 1) if a['players_total'] > 0 else 0
    
    # Ad impressions and clicks (use ad_events table - already computed in ads_summary)
    # These are fallback values if ads_summary failed
    a['impressions_total'] = ads.get('total_impressions', 0) if ads else 0
    a['clicks_total'] = ads.get('total_clicks', 0) if ads else 0
    a['ctr_overall'] = ads.get('ctr', 0) if ads else 0
    
    # Survey responses
    try:
        cursor.execute('SELECT COUNT(*) FROM survey_responses')
        a['survey_responses_total'] = cursor.fetchone()[0] or 0
    except:
        a['survey_responses_total'] = 0
    
    # Avg spend per session from post_session_surveys
    a['avg_spend_per_session'] = 0.0
    try:
        cursor.execute('SELECT AVG(spend_amount) FROM post_session_surveys WHERE spend_amount IS NOT NULL AND spend_amount > 0')
        avg_spend = cursor.fetchone()[0]
        a['avg_spend_per_session'] = avg_spend or 0.0
    except:
        pass
    
    # Avg spend per bar breakdown
    a['avg_spend_per_bar'] = {}
    try:
        cursor.execute('''
            SELECT b.name, AVG(pss.spend_amount) as avg_spend
            FROM post_session_surveys pss
            JOIN bars b ON pss.bar_id = b.id
            WHERE pss.spend_amount IS NOT NULL AND pss.spend_amount > 0
            GROUP BY pss.bar_id
            ORDER BY avg_spend DESC
        ''')
        for r in cursor.fetchall():
            a['avg_spend_per_bar'][r[0]] = round(r[1], 2) if r[1] else 0
    except:
        pass
    
    # Demographics - gender breakdown from players table
    a['gender_breakdown'] = {'male': 0, 'female': 0, 'other': 0}
    a['gender_total'] = 0
    try:
        cursor.execute("SELECT gender, COUNT(*) FROM players WHERE gender IS NOT NULL AND gender != '' AND (is_active = 1 OR is_active IS NULL) GROUP BY gender")
        rows = cursor.fetchall()
        total_gender = sum(r[1] for r in rows)
        a['gender_total'] = total_gender
        if total_gender > 0:
            for r in rows:
                gender = (r[0] or '').lower()
                if gender in ['male', 'm']:
                    a['gender_breakdown']['male'] = round(r[1] / total_gender * 100)
                elif gender in ['female', 'f']:
                    a['gender_breakdown']['female'] = round(r[1] / total_gender * 100)
                else:
                    a['gender_breakdown']['other'] += round(r[1] / total_gender * 100)
    except:
        pass
    
    # Age distribution from birthday field (more accurate than age_range)
    a['age_distribution'] = {'18-24': 0, '25-34': 0, '35-44': 0, '45+': 0}
    a['median_age'] = None
    a['age_total'] = 0
    try:
        # Calculate ages from birthday field
        cursor.execute('''
            SELECT 
                CAST((julianday('now') - julianday(birthday)) / 365.25 AS INTEGER) as age
            FROM players 
            WHERE birthday IS NOT NULL 
              AND birthday != '' 
              AND length(birthday) >= 10
              AND (is_active = 1 OR is_active IS NULL)
            ORDER BY age
        ''')
        ages = [r[0] for r in cursor.fetchall() if r[0] and r[0] >= 18 and r[0] <= 120]
        
        if ages:
            a['age_total'] = len(ages)
            # Calculate median
            mid = len(ages) // 2
            if len(ages) % 2 == 0:
                a['median_age'] = (ages[mid - 1] + ages[mid]) // 2
            else:
                a['median_age'] = ages[mid]
            
            # Bucket into age groups
            buckets = {'18-24': 0, '25-34': 0, '35-44': 0, '45+': 0}
            for age in ages:
                if age <= 24:
                    buckets['18-24'] += 1
                elif age <= 34:
                    buckets['25-34'] += 1
                elif age <= 44:
                    buckets['35-44'] += 1
                else:
                    buckets['45+'] += 1
            
            # Convert to percentages
            total = len(ages)
            for k in buckets:
                a['age_distribution'][k] = round(buckets[k] / total * 100) if total > 0 else 0
    except Exception as e:
        print(f"[ANALYTICS] Age calculation error: {e}")
        pass
    
    # Borough distribution - uses normalize_borough for consistent naming
    # NOTE: NYC has exactly 5 boroughs - this is enforced via NYC_BOROUGHS tuple
    a['borough_distribution'] = {boro: 0 for boro in NYC_BOROUGHS}
    a['borough_total'] = 0
    a['active_boroughs'] = 0  # Count of boroughs with at least 1 player (max 5)
    a['bars_by_borough'] = {boro: 0 for boro in NYC_BOROUGHS}  # Bar count per borough
    a['total_boroughs'] = 5  # NYC always has exactly 5 boroughs - this is a constant
    try:
        # Players by borough (from home_bar)
        cursor.execute('''
            SELECT b.borough, COUNT(DISTINCT p.id) 
            FROM players p 
            JOIN bars b ON p.home_bar_id = b.id 
            WHERE b.borough IS NOT NULL AND b.borough != ''
              AND (p.is_active = 1 OR p.is_active IS NULL)
            GROUP BY b.borough
        ''')
        rows = cursor.fetchall()
        total = 0
        boroughs_with_players = set()
        for r in rows:
            # Normalize the borough name to canonical form
            boro = normalize_borough(r[0])
            if boro and boro in a['borough_distribution']:
                a['borough_distribution'][boro] += r[1]
                total += r[1]
                boroughs_with_players.add(boro)
        a['borough_total'] = total
        # SAFETY: active_boroughs can never exceed 5 (the number of NYC boroughs)
        a['active_boroughs'] = min(len(boroughs_with_players), 5)
        
        # Bars by borough
        cursor.execute('''
            SELECT borough, COUNT(*) 
            FROM bars 
            WHERE is_active = 1 AND borough IS NOT NULL AND borough != ''
            GROUP BY borough
        ''')
        for r in cursor.fetchall():
            boro = normalize_borough(r[0])
            if boro and boro in a['bars_by_borough']:
                a['bars_by_borough'][boro] += r[1]
    except Exception as e:
        print(f"[ANALYTICS] Borough distribution error: {e}")
    
    # Borough growth (month-over-month player increase) - uses normalize_borough
    a['borough_growth'] = {boro: {'current': 0, 'previous': 0, 'growth': 0} for boro in NYC_BOROUGHS}
    try:
        # Current month players by borough
        cursor.execute('''
            SELECT b.borough, COUNT(DISTINCT p.id) 
            FROM players p 
            JOIN bars b ON p.home_bar_id = b.id 
            WHERE b.borough IS NOT NULL AND b.borough != ''
              AND (p.is_active = 1 OR p.is_active IS NULL)
              AND p.created_at >= date('now', 'start of month')
            GROUP BY b.borough
        ''')
        for r in cursor.fetchall():
            boro = normalize_borough(r[0])
            if boro and boro in a['borough_growth']:
                a['borough_growth'][boro]['current'] += r[1]
        
        # Previous month players by borough
        cursor.execute('''
            SELECT b.borough, COUNT(DISTINCT p.id) 
            FROM players p 
            JOIN bars b ON p.home_bar_id = b.id 
            WHERE b.borough IS NOT NULL AND b.borough != ''
              AND (p.is_active = 1 OR p.is_active IS NULL)
              AND p.created_at >= date('now', 'start of month', '-1 month')
              AND p.created_at < date('now', 'start of month')
            GROUP BY b.borough
        ''')
        for r in cursor.fetchall():
            boro = normalize_borough(r[0])
            if boro and boro in a['borough_growth']:
                a['borough_growth'][boro]['previous'] += r[1]
        
        # Calculate growth percentages
        for boro in NYC_BOROUGHS:
            current = a['borough_growth'][boro]['current']
            previous = a['borough_growth'][boro]['previous']
            if previous > 0:
                a['borough_growth'][boro]['growth'] = round((current - previous) / previous * 100)
            elif current > 0:
                a['borough_growth'][boro]['growth'] = 100  # New growth from 0
    except Exception as e:
        print(f"[ANALYTICS] Borough growth error: {e}")
        pass
    
    # Neighborhood breakdown - top neighborhoods from bar locations
    a['neighborhoods'] = []
    try:
        cursor.execute('''
            SELECT b.neighborhood, COUNT(DISTINCT p.id) as player_count
            FROM players p 
            JOIN bars b ON p.home_bar_id = b.id 
            WHERE b.neighborhood IS NOT NULL AND b.neighborhood != '' 
              AND (p.is_active = 1 OR p.is_active IS NULL)
            GROUP BY b.neighborhood
            ORDER BY player_count DESC
            LIMIT 4
        ''')
        a['neighborhoods'] = [{'name': r[0], 'count': r[1]} for r in cursor.fetchall()]
    except:
        pass
    
    # ============================================
    # GEO ANALYTICS - Comprehensive Location Stats
    # ============================================
    a['geo'] = {
        'total_states': 0,
        'total_cities': 0,
        'states': [],      # [{state, bar_count, player_count, game_count}]
        'cities': [],      # [{city, state, bar_count, player_count}]
        'zip_codes': [],   # [{zip, neighborhood, bar_count, player_count}]
    }
    try:
        # Count unique states
        cursor.execute('SELECT COUNT(DISTINCT state) FROM bars WHERE state IS NOT NULL AND state != "" AND is_active = 1')
        a['geo']['total_states'] = cursor.fetchone()[0] or 0
        
        # Count unique cities
        cursor.execute('SELECT COUNT(DISTINCT city) FROM bars WHERE city IS NOT NULL AND city != "" AND is_active = 1')
        a['geo']['total_cities'] = cursor.fetchone()[0] or 0
        
        # Stats by state
        cursor.execute('''
            SELECT 
                b.state,
                COUNT(DISTINCT b.id) as bar_count,
                COUNT(DISTINCT p.id) as player_count,
                (SELECT COUNT(*) FROM game_history gh WHERE gh.bar_id IN (SELECT id FROM bars WHERE state = b.state)) as game_count
            FROM bars b
            LEFT JOIN players p ON p.home_bar_id = b.id AND (p.is_active = 1 OR p.is_active IS NULL)
            WHERE b.state IS NOT NULL AND b.state != '' AND b.is_active = 1
            GROUP BY b.state
            ORDER BY bar_count DESC
            LIMIT 10
        ''')
        a['geo']['states'] = [{'state': r[0], 'bar_count': r[1], 'player_count': r[2] or 0, 'game_count': r[3] or 0} for r in cursor.fetchall()]
        
        # Stats by city (for non-NYC, or NYC as a whole)
        cursor.execute('''
            SELECT 
                b.city,
                b.state,
                COUNT(DISTINCT b.id) as bar_count,
                COUNT(DISTINCT p.id) as player_count
            FROM bars b
            LEFT JOIN players p ON p.home_bar_id = b.id AND (p.is_active = 1 OR p.is_active IS NULL)
            WHERE b.city IS NOT NULL AND b.city != '' AND b.is_active = 1
            GROUP BY b.city, b.state
            ORDER BY bar_count DESC
            LIMIT 10
        ''')
        a['geo']['cities'] = [{'city': r[0], 'state': r[1], 'bar_count': r[2], 'player_count': r[3] or 0} for r in cursor.fetchall()]
        
        # Stats by ZIP code
        cursor.execute('''
            SELECT 
                b.zip_code,
                b.neighborhood,
                COUNT(DISTINCT b.id) as bar_count,
                COUNT(DISTINCT p.id) as player_count
            FROM bars b
            LEFT JOIN players p ON p.home_bar_id = b.id AND (p.is_active = 1 OR p.is_active IS NULL)
            WHERE b.zip_code IS NOT NULL AND b.zip_code != '' AND b.is_active = 1
            GROUP BY b.zip_code
            ORDER BY bar_count DESC
            LIMIT 10
        ''')
        a['geo']['zip_codes'] = [{'zip': r[0], 'neighborhood': r[1] or '', 'bar_count': r[2], 'player_count': r[3] or 0} for r in cursor.fetchall()]
        
    except Exception as e:
        print(f"[ANALYTICS] Geo stats error: {e}")
    
    # Skill distribution by rating tiers - only active players
    a['skill_distribution'] = {'diamond': 0, 'platinum': 0, 'gold': 0, 'silver': 0, 'bronze': 0}
    try:
        cursor.execute('SELECT rating FROM players WHERE rating IS NOT NULL AND (is_active = 1 OR is_active IS NULL)')
        for (rating,) in cursor.fetchall():
            if rating >= 1400:
                a['skill_distribution']['diamond'] += 1
            elif rating >= 1300:
                a['skill_distribution']['platinum'] += 1
            elif rating >= 1200:
                a['skill_distribution']['gold'] += 1
            elif rating >= 1100:
                a['skill_distribution']['silver'] += 1
            else:
                a['skill_distribution']['bronze'] += 1
    except:
        pass
    
    # Activity heatmap - real game data by day of week and hour (converted to local time)
    a['activity_heatmap'] = [[0]*24 for _ in range(7)]  # 7 days x 24 hours
    a['peak_activity'] = {'day': '', 'hour': 0, 'count': 0}
    try:
        # Convert UTC timestamps to local time for accurate heatmap display
        cursor.execute('''
            SELECT 
                CAST(strftime('%w', datetime(played_at, 'localtime')) AS INTEGER) as day_of_week,
                CAST(strftime('%H', datetime(played_at, 'localtime')) AS INTEGER) as hour,
                COUNT(*) as game_count
            FROM game_history
            WHERE played_at >= datetime('now', '-30 days')
            GROUP BY day_of_week, hour
        ''')
        max_count = 0
        for row in cursor.fetchall():
            day = row[0]  # 0=Sun, 6=Sat
            hour = row[1]
            count = row[2]
            a['activity_heatmap'][day][hour] = count
            if count > max_count:
                max_count = count
                days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
                a['peak_activity'] = {'day': days[day], 'hour': hour, 'count': count}
    except:
        pass
    
    # Play frequency distribution from players table
    a['frequency_distribution'] = {'weekly_plus': 0, 'biweekly': 0, 'monthly': 0, 'occasional': 0}
    try:
        cursor.execute('''
            SELECT play_frequency, COUNT(*) 
            FROM players 
            WHERE play_frequency IS NOT NULL AND (is_active = 1 OR is_active IS NULL)
            GROUP BY play_frequency
        ''')
        for r in cursor.fetchall():
            freq = r[0]
            if freq in ['daily', 'multiple_weekly']:
                a['frequency_distribution']['weekly_plus'] += r[1]
            elif freq == 'weekly':
                a['frequency_distribution']['biweekly'] += r[1]
            elif freq == 'rarely':
                a['frequency_distribution']['occasional'] += r[1]
        
        # Also calculate from actual game data for players without play_frequency set
        cursor.execute('''
            WITH player_game_counts AS (
                SELECT 
                    p.id,
                    COUNT(g.id) as games_30d
                FROM players p
                LEFT JOIN game_history g ON (g.winner_id = p.id OR g.loser_id = p.id)
                    AND g.played_at >= datetime('now', '-30 days')
                WHERE p.play_frequency IS NULL AND (p.is_active = 1 OR p.is_active IS NULL)
                GROUP BY p.id
            )
            SELECT 
                CASE 
                    WHEN games_30d >= 8 THEN 'weekly_plus'
                    WHEN games_30d >= 4 THEN 'biweekly'
                    WHEN games_30d >= 1 THEN 'monthly'
                    ELSE 'occasional'
                END as freq_bucket,
                COUNT(*) as cnt
            FROM player_game_counts
            GROUP BY freq_bucket
        ''')
        for r in cursor.fetchall():
            if r[0] in a['frequency_distribution']:
                a['frequency_distribution'][r[0]] += r[1]
    except Exception as e:
        print(f"[ANALYTICS] Frequency distribution error: {e}")
        pass
    
    # Games per week for chart (last 12 weeks)
    a['games_per_week'] = {'labels': [], 'values': []}
    try:
        cursor.execute('''
            SELECT strftime('%W', played_at) as week, COUNT(*) as cnt
            FROM game_history
            WHERE played_at >= datetime('now', '-84 days')
            GROUP BY week
            ORDER BY week
            LIMIT 12
        ''')
        rows = cursor.fetchall()
        for i, r in enumerate(rows):
            a['games_per_week']['labels'].append(f'W{i+1}')
            a['games_per_week']['values'].append(r[1])
    except:
        pass
    # Fill with zeros if no data
    if not a['games_per_week']['labels']:
        a['games_per_week'] = {'labels': [f'W{i}' for i in range(1, 13)], 'values': [0]*12}
    
    # Retention data - computed from real game history
    # For each cohort milestone, calculate % of players who returned
    a['retention_data'] = {'labels': ['D1', 'D7', 'D14', 'D30'], 'values': [0, 0, 0, 0], 'cohort_size': 0}
    try:
        # Get players with at least 2 games (to measure return)
        cursor.execute('''
            WITH player_first_game AS (
                SELECT 
                    CASE WHEN winner_id IS NOT NULL THEN winner_id ELSE loser_id END as player_id,
                    MIN(played_at) as first_game
                FROM game_history
                WHERE played_at < datetime('now', '-30 days')
                GROUP BY player_id
            ),
            player_returns AS (
                SELECT 
                    pfg.player_id,
                    pfg.first_game,
                    MIN(CASE 
                        WHEN g.played_at > pfg.first_game 
                        AND julianday(g.played_at) - julianday(pfg.first_game) <= 1 
                        THEN 1 ELSE 0 END) as returned_d1,
                    MIN(CASE 
                        WHEN g.played_at > pfg.first_game 
                        AND julianday(g.played_at) - julianday(pfg.first_game) <= 7 
                        THEN 1 ELSE 0 END) as returned_d7,
                    MIN(CASE 
                        WHEN g.played_at > pfg.first_game 
                        AND julianday(g.played_at) - julianday(pfg.first_game) <= 14 
                        THEN 1 ELSE 0 END) as returned_d14,
                    MIN(CASE 
                        WHEN g.played_at > pfg.first_game 
                        AND julianday(g.played_at) - julianday(pfg.first_game) <= 30 
                        THEN 1 ELSE 0 END) as returned_d30
                FROM player_first_game pfg
                LEFT JOIN game_history g ON (g.winner_id = pfg.player_id OR g.loser_id = pfg.player_id)
                GROUP BY pfg.player_id
            )
            SELECT 
                COUNT(*) as cohort_size,
                SUM(returned_d1) as d1,
                SUM(returned_d7) as d7,
                SUM(returned_d14) as d14,
                SUM(returned_d30) as d30
            FROM player_returns
        ''')
        row = cursor.fetchone()
        if row and row[0] and row[0] > 0:
            cohort = row[0]
            a['retention_data']['cohort_size'] = cohort
            a['retention_data']['values'] = [
                round((row[1] or 0) / cohort * 100),
                round((row[2] or 0) / cohort * 100),
                round((row[3] or 0) / cohort * 100),
                round((row[4] or 0) / cohort * 100)
            ]
    except Exception as e:
        print(f"[ANALYTICS] Retention calculation error: {e}")
        # Leave as zeros if calculation fails
    
    # Bar performance stats
    cursor.execute('''
        SELECT b.name, COUNT(DISTINCT p.id) as player_count
        FROM bars b
        LEFT JOIN players p ON p.home_bar_id = b.id
        WHERE b.is_active = 1
        GROUP BY b.id
        ORDER BY player_count DESC
        LIMIT 5
    ''')
    bar_rows = cursor.fetchall()
    max_players = bar_rows[0][1] if bar_rows and bar_rows[0][1] > 0 else 1
    bar_stats = [{'name': r[0], 'player_count': r[1], 'percentage': round(r[1] / max_players * 100)} for r in bar_rows]
    
    # Top bars by name
    a['top_bars'] = [{'name': r[0], 'players': r[1]} for r in bar_rows]
    
    # Live stats
    cursor.execute('SELECT COUNT(*) FROM queue')
    a['queue_count'] = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT COUNT(*) FROM bars WHERE is_active = 1')
    a['active_bars'] = cursor.fetchone()[0] or 0
    
    # ============================================
    # PLAYER COHORTS - Behavioral Segments (Real Data)
    # ============================================
    a['cohorts'] = {
        'weekend_warriors': 0,
        'ranked_grinders': 0,
        'bar_loyalists': 0,
        'bar_hoppers': 0,
        'big_spenders': 0,
        'hot_streakers': 0,
        'tastemakers': 0,
        'at_risk': 0
    }
    try:
        # Weekend Warriors - players who primarily play Fri-Sun
        cursor.execute('''
            WITH player_games AS (
                SELECT 
                    CASE WHEN winner_id IS NOT NULL THEN winner_id ELSE loser_id END as player_id,
                    CAST(strftime('%w', played_at) AS INTEGER) as dow
                FROM game_history
                WHERE played_at >= datetime('now', '-30 days')
            ),
            player_weekend_pct AS (
                SELECT player_id,
                       SUM(CASE WHEN dow IN (0, 5, 6) THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as weekend_pct
                FROM player_games
                GROUP BY player_id
                HAVING COUNT(*) >= 3
            )
            SELECT COUNT(*) FROM player_weekend_pct WHERE weekend_pct >= 70
        ''')
        a['cohorts']['weekend_warriors'] = cursor.fetchone()[0] or 0
        
        # Ranked Grinders - players with 5+ ranked games in last 30 days
        cursor.execute('''
            SELECT COUNT(DISTINCT player_id) FROM (
                SELECT winner_id as player_id FROM game_history 
                WHERE is_ranked = 1 AND played_at >= datetime('now', '-30 days')
                UNION ALL
                SELECT loser_id as player_id FROM game_history 
                WHERE is_ranked = 1 AND played_at >= datetime('now', '-30 days')
            ) GROUP BY player_id HAVING COUNT(*) >= 5
        ''')
        a['cohorts']['ranked_grinders'] = len(cursor.fetchall())
        
        # Bar Loyalists - players who play at the same bar 80%+ of time
        cursor.execute('''
            WITH player_bar_games AS (
                SELECT 
                    CASE WHEN winner_id IS NOT NULL THEN winner_id ELSE loser_id END as player_id,
                    bar_id
                FROM game_history
                WHERE played_at >= datetime('now', '-30 days')
            ),
            player_bar_counts AS (
                SELECT player_id, bar_id, COUNT(*) as cnt,
                       SUM(COUNT(*)) OVER (PARTITION BY player_id) as total
                FROM player_bar_games
                GROUP BY player_id, bar_id
            )
            SELECT COUNT(DISTINCT player_id) 
            FROM player_bar_counts 
            WHERE total >= 3 AND (cnt * 100.0 / total) >= 80
        ''')
        a['cohorts']['bar_loyalists'] = cursor.fetchone()[0] or 0
        
        # Bar Hoppers - players with games at 3+ different bars
        cursor.execute('''
            SELECT COUNT(*) FROM (
                SELECT CASE WHEN winner_id IS NOT NULL THEN winner_id ELSE loser_id END as player_id
                FROM game_history
                WHERE played_at >= datetime('now', '-30 days')
                GROUP BY player_id
                HAVING COUNT(DISTINCT bar_id) >= 3
            )
        ''')
        a['cohorts']['bar_hoppers'] = cursor.fetchone()[0] or 0
        
        # Big Spenders - players with avg spend >= $65 from post_session_surveys
        try:
            cursor.execute('''
                SELECT COUNT(DISTINCT player_id) 
                FROM post_session_surveys 
                WHERE spend_amount >= 65 
                AND created_at >= datetime('now', '-30 days')
            ''')
            a['cohorts']['big_spenders'] = cursor.fetchone()[0] or 0
        except:
            pass
        
        # Hot Streakers - players with current win streak >= 4
        cursor.execute('''
            SELECT COUNT(*) FROM players 
            WHERE current_streak >= 4 AND (is_active = 1 OR is_active IS NULL)
        ''')
        a['cohorts']['hot_streakers'] = cursor.fetchone()[0] or 0
        
        # At Risk - players who haven't played in 14+ days but were active before
        cursor.execute('''
            WITH last_played AS (
                SELECT player_id, MAX(played_at) as last_game
                FROM (
                    SELECT winner_id as player_id, played_at FROM game_history
                    UNION ALL
                    SELECT loser_id as player_id, played_at FROM game_history
                )
                GROUP BY player_id
            )
            SELECT COUNT(*) FROM last_played lp
            JOIN players p ON lp.player_id = p.id
            WHERE lp.last_game < datetime('now', '-14 days')
            AND lp.last_game >= datetime('now', '-60 days')
            AND (p.is_active = 1 OR p.is_active IS NULL)
        ''')
        a['cohorts']['at_risk'] = cursor.fetchone()[0] or 0
        
    except Exception as e:
        print(f"[ANALYTICS] Cohort calculation error: {e}")
    
    # Get bars for filter dropdown
    cursor.execute('SELECT id, name FROM bars WHERE is_active = 1 ORDER BY name')
    bars = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    # Get auto-invite funnel analytics
    from .database import get_auto_invite_analytics
    auto_invite_stats = get_auto_invite_analytics(start_date_str, end_date_str, bar_id=bar_id)
    a['auto_invites'] = auto_invite_stats
    
    # Check if this is an embed request (for app shell)
    embed = request.args.get('embed', '0') == '1'
    
    return render_template('master/analytics.html', 
                           analytics=a, 
                           bar_stats=bar_stats, 
                           bars=bars,
                           selected_bar_id=bar_id,
                           active_page='analytics',
                           embed=embed)


@master_bp.route('/brand-analytics')
@admin_required
def brand_analytics():
    """Redirect to main analytics page."""
    return redirect(url_for('master.analytics'))


@master_bp.route('/bar-reports')
@admin_required
def bar_reports():
    """All bars comprehensive reports."""
    return render_template('master/bar_reports.html')


@master_bp.route('/bar-reports/<int:bar_id>')
@admin_required
def bar_report_detail(bar_id):
    """Detailed report for a specific bar."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM bars WHERE id = ?', (bar_id,))
    bar = cursor.fetchone()
    conn.close()
    
    if not bar:
        bar = {'id': bar_id, 'name': f'Bar {bar_id}', 'address': 'Address TBD'}
    else:
        bar = dict(bar)
    
    return render_template('master/bar_report_detail.html', bar=bar)


@master_bp.route('/brand-report')
@admin_required
def brand_report():
    """Redirect to main analytics page."""
    return redirect(url_for('master.analytics'))


@master_bp.route('/brand/<brand_name>')
@admin_required
def brand_report_detail(brand_name):
    """Redirect to main analytics page."""
    return redirect(url_for('master.analytics'))

@master_bp.route('/bar/<int:bar_id>')
@admin_required
def bar_detail(bar_id):
    """Bar detail page with real stats from database."""
    print(f"[MASTER] Bar detail page loaded for bar {bar_id}")
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get bar info
    cursor.execute('SELECT * FROM bars WHERE id = ?', (bar_id,))
    bar_row = cursor.fetchone()
    
    if not bar_row:
        conn.close()
        return "Bar not found", 404
    
    bar = dict(bar_row)
    
    # Build bar_summary with real data
    summary = {'bar': bar}
    
    # Total games at this bar
    cursor.execute('''
        SELECT COUNT(*) FROM game_history 
        WHERE bar_id = ?
    ''', (bar_id,))
    row = cursor.fetchone()
    summary['total_games'] = row[0] if row else 0
    
    # Games today
    cursor.execute('''
        SELECT COUNT(*) FROM game_history 
        WHERE bar_id = ? AND date(played_at) = date('now')
    ''', (bar_id,))
    row = cursor.fetchone()
    summary['games_today'] = row[0] if row else 0
    
    # Unique players (home bar or played here)
    cursor.execute('''
        SELECT COUNT(DISTINCT player_id) FROM (
            SELECT winner_id as player_id FROM game_history WHERE bar_id = ?
            UNION
            SELECT loser_id as player_id FROM game_history WHERE bar_id = ?
            UNION
            SELECT id as player_id FROM players WHERE home_bar_id = ?
        )
    ''', (bar_id, bar_id, bar_id))
    row = cursor.fetchone()
    summary['unique_players'] = row[0] if row else 0
    
    # Players with home_bar set to this bar
    cursor.execute('SELECT COUNT(*) FROM players WHERE home_bar_id = ?', (bar_id,))
    row = cursor.fetchone()
    summary['registered_players'] = row[0] if row else 0
    
    # Current queue count
    cursor.execute('SELECT COUNT(*) FROM queue WHERE bar_id = ?', (bar_id,))
    row = cursor.fetchone()
    summary['queue_count'] = row[0] if row else 0
    
    # Total pool nights (distinct dates with games)
    cursor.execute('''
        SELECT COUNT(DISTINCT date(played_at)) FROM game_history 
        WHERE bar_id = ?
    ''', (bar_id,))
    row = cursor.fetchone()
    summary['total_pool_nights'] = row[0] if row else 0
    
    # POS stats (last 30 days)
    summary['pos_total_revenue'] = None
    summary['pos_avg_tab'] = None
    summary['pos_checks_count'] = 0
    try:
        cursor.execute('''
            SELECT COUNT(*) as checks, 
                   COALESCE(SUM(total_amount), 0) as revenue,
                   COALESCE(AVG(total_amount), 0) as avg_tab
            FROM pos_checks 
            WHERE bar_id = ? 
              AND business_date >= date('now', '-30 days')
        ''', (bar_id,))
        row = cursor.fetchone()
        if row and row['checks'] > 0:
            summary['pos_checks_count'] = row['checks']
            summary['pos_total_revenue'] = round(row['revenue'], 2)
            summary['pos_avg_tab'] = round(row['avg_tab'], 2)
    except:
        pass
    
    # Ad impressions and revenue (last 30 days)
    summary['impressions'] = 0
    summary['clicks'] = 0
    summary['ad_revenue'] = 0
    summary['ctr'] = 0
    try:
        cursor.execute('''
            SELECT COUNT(*) as impressions,
                   SUM(CASE WHEN clicked = 1 THEN 1 ELSE 0 END) as clicks
            FROM ad_impressions 
            WHERE bar_id = ? 
              AND created_at >= datetime('now', '-30 days')
        ''', (bar_id,))
        row = cursor.fetchone()
        if row:
            summary['impressions'] = row['impressions'] or 0
            summary['clicks'] = row['clicks'] or 0
            if summary['impressions'] > 0:
                summary['ctr'] = round(summary['clicks'] / summary['impressions'] * 100, 1)
    except:
        pass
    
    # Active campaigns for this bar
    summary['campaigns'] = []
    try:
        cursor.execute('''
            SELECT c.id, c.name, a.company_name as advertiser_name,
                   (SELECT COUNT(*) FROM ad_impressions ai WHERE ai.campaign_id = c.id) as impressions,
                   (SELECT COUNT(*) FROM ad_impressions ai WHERE ai.campaign_id = c.id AND ai.clicked = 1) as clicks
            FROM campaigns c
            JOIN advertisers a ON c.advertiser_id = a.id
            WHERE c.status = 'active' 
              AND c.end_date >= date('now')
              AND (c.bar_id = ? OR c.bar_id IS NULL)
            ORDER BY impressions DESC
            LIMIT 5
        ''', (bar_id,))
        for row in cursor.fetchall():
            impressions = row['impressions'] or 0
            clicks = row['clicks'] or 0
            ctr = round(clicks / impressions * 100, 1) if impressions > 0 else 0
            summary['campaigns'].append({
                'id': row['id'],
                'name': row['name'],
                'advertiser_name': row['advertiser_name'],
                'impressions': impressions,
                'clicks': clicks,
                'ctr': ctr
            })
    except:
        pass
    
    # Top players at this bar
    summary['top_players'] = []
    try:
        cursor.execute('''
            SELECT p.id, p.nickname, p.wins, p.losses, p.rating
            FROM players p
            WHERE p.home_bar_id = ?
            ORDER BY p.wins DESC, p.rating DESC
            LIMIT 5
        ''', (bar_id,))
        for row in cursor.fetchall():
            wins = row['wins'] or 0
            losses = row['losses'] or 0
            total = wins + losses
            win_rate = round(wins / total * 100) if total > 0 else 0
            summary['top_players'].append({
                'id': row['id'],
                'nickname': row['nickname'],
                'wins': wins,
                'losses': losses,
                'rating': row['rating'] or 1000,
                'win_rate': win_rate
            })
    except:
        pass
    
    # Recent games at this bar
    summary['recent_games'] = []
    try:
        cursor.execute('''
            SELECT g.id, g.played_at, g.duration_seconds,
                   w.nickname as winner_name, l.nickname as loser_name
            FROM game_history g
            LEFT JOIN players w ON g.winner_id = w.id
            LEFT JOIN players l ON g.loser_id = l.id
            WHERE g.bar_id = ?
            ORDER BY g.played_at DESC
            LIMIT 10
        ''', (bar_id,))
        for row in cursor.fetchall():
            summary['recent_games'].append({
                'id': row['id'],
                'played_at': row['played_at'],
                'duration': row['duration_seconds'],
                'winner': row['winner_name'] or 'Unknown',
                'loser': row['loser_name'] or 'Unknown'
            })
    except:
        pass
    
    # Player demographics at this bar
    summary['skill_distribution'] = {'diamond': 0, 'platinum': 0, 'gold': 0, 'silver': 0, 'bronze': 0}
    try:
        cursor.execute('SELECT rating FROM players WHERE home_bar_id = ? AND rating IS NOT NULL', (bar_id,))
        for (rating,) in cursor.fetchall():
            if rating >= 1400:
                summary['skill_distribution']['diamond'] += 1
            elif rating >= 1300:
                summary['skill_distribution']['platinum'] += 1
            elif rating >= 1200:
                summary['skill_distribution']['gold'] += 1
            elif rating >= 1100:
                summary['skill_distribution']['silver'] += 1
            else:
                summary['skill_distribution']['bronze'] += 1
    except:
        pass
    
    # Age distribution - calculated from birthday field (consistent with main analytics)
    summary['age_distribution'] = {'18-24': 0, '25-34': 0, '35-44': 0, '45+': 0}
    summary['age_total'] = 0
    try:
        cursor.execute('''
            SELECT 
                CAST((julianday('now') - julianday(birthday)) / 365.25 AS INTEGER) as age
            FROM players 
            WHERE home_bar_id = ? 
              AND birthday IS NOT NULL 
              AND birthday != '' 
              AND length(birthday) >= 10
              AND (is_active = 1 OR is_active IS NULL)
        ''', (bar_id,))
        ages = [r[0] for r in cursor.fetchall() if r[0] and r[0] >= 18 and r[0] <= 120]
        
        if ages:
            summary['age_total'] = len(ages)
            buckets = {'18-24': 0, '25-34': 0, '35-44': 0, '45+': 0}
            for age in ages:
                if age <= 24:
                    buckets['18-24'] += 1
                elif age <= 34:
                    buckets['25-34'] += 1
                elif age <= 44:
                    buckets['35-44'] += 1
                else:
                    buckets['45+'] += 1
            # Convert to percentages
            total = len(ages)
            for k in buckets:
                summary['age_distribution'][k] = round(buckets[k] / total * 100) if total > 0 else 0
    except:
        pass
    
    # Live queue for this bar
    summary['queue'] = []
    try:
        cursor.execute('''
            SELECT q.id, q.position, q.status, q.created_at, q.wins_on_table,
                   p.id as player_id, p.nickname
            FROM queue q
            JOIN players p ON q.player_id = p.id
            WHERE q.bar_id = ?
            ORDER BY q.position ASC
        ''', (bar_id,))
        for i, row in enumerate(cursor.fetchall()):
            summary['queue'].append({
                'id': row['id'],
                'position': i + 1,  # Recalculate display position (1, 2, 3...)
                'status': row['status'],
                'wins_on_table': row['wins_on_table'] or 0,
                'player_id': row['player_id'],
                'nickname': row['nickname'],
                'created_at': row['created_at']
            })
    except:
        pass
    
    # Recent activity feed (games + queue joins)
    summary['activity'] = []
    try:
        # Recent games as activity
        cursor.execute('''
            SELECT 'game' as type, g.played_at as time, w.nickname as actor, l.nickname as target
            FROM game_history g
            LEFT JOIN players w ON g.winner_id = w.id
            LEFT JOIN players l ON g.loser_id = l.id
            WHERE g.bar_id = ?
            ORDER BY g.played_at DESC
            LIMIT 10
        ''', (bar_id,))
        for row in cursor.fetchall():
            summary['activity'].append({
                'type': 'game',
                'icon': '🎱',
                'text': f"<b>{row['actor'] or 'Unknown'}</b> beat {row['target'] or 'Unknown'}",
                'time': row['time'][:16] if row['time'] else ''
            })
    except:
        pass
    
    # Weekly games data for charts (last 4 weeks)
    summary['weekly_games'] = [0, 0, 0, 0]
    try:
        cursor.execute('''
            SELECT 
                CAST((julianday('now') - julianday(played_at)) / 7 AS INT) as weeks_ago,
                COUNT(*) as games
            FROM game_history 
            WHERE bar_id = ? 
              AND played_at >= datetime('now', '-28 days')
            GROUP BY weeks_ago
            ORDER BY weeks_ago DESC
        ''', (bar_id,))
        rows = cursor.fetchall()
        # Fill in weeks (0=this week, 1=last week, etc.) into W1-W4 format
        for row in rows:
            weeks_ago = row['weeks_ago']
            if 0 <= weeks_ago < 4:
                # W1 is oldest (3 weeks ago), W4 is current week
                idx = 3 - weeks_ago
                summary['weekly_games'][idx] = row['games']
    except:
        pass
    
    # Weekly revenue data for charts (last 4 weeks from POS)
    summary['weekly_revenue'] = [0, 0, 0, 0]
    try:
        cursor.execute('''
            SELECT 
                CAST((julianday('now') - julianday(business_date)) / 7 AS INT) as weeks_ago,
                COALESCE(SUM(total_amount), 0) as revenue
            FROM pos_checks 
            WHERE bar_id = ? 
              AND business_date >= date('now', '-28 days')
            GROUP BY weeks_ago
            ORDER BY weeks_ago DESC
        ''', (bar_id,))
        rows = cursor.fetchall()
        for row in rows:
            weeks_ago = row['weeks_ago']
            if 0 <= weeks_ago < 4:
                idx = 3 - weeks_ago
                summary['weekly_revenue'][idx] = round(row['revenue'], 0)
    except:
        pass
    
    conn.close()
    
    # Get ranked windows for this bar
    from .database import get_ranked_windows
    ranked_windows = get_ranked_windows(bar_id)
    
    # Get tastemakers for this bar
    tastemakers = []
    home_bar_players = []
    try:
        conn2 = get_db()
        cursor2 = conn2.cursor()
        
        # Create table if it doesn't exist
        cursor2.execute('''
            CREATE TABLE IF NOT EXISTS bar_tastemakers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bar_id INTEGER NOT NULL,
                player_id INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(bar_id, player_id),
                FOREIGN KEY (bar_id) REFERENCES bars(id),
                FOREIGN KEY (player_id) REFERENCES players(id)
            )
        ''')
        conn2.commit()
        
        # Get current tastemakers
        cursor2.execute('''
            SELECT p.id, p.nickname, p.rating,
                   COALESCE(pbr.wins, 0) as wins_at_bar,
                   COALESCE(pbr.losses, 0) as losses_at_bar
            FROM bar_tastemakers bt
            JOIN players p ON bt.player_id = p.id
            LEFT JOIN player_bar_rankings pbr ON p.id = pbr.player_id AND pbr.bar_id = ?
            WHERE bt.bar_id = ?
            ORDER BY bt.created_at DESC
        ''', (bar_id, bar_id))
        for row in cursor2.fetchall():
            wins = row['wins_at_bar'] or 0
            losses = row['losses_at_bar'] or 0
            total = wins + losses
            tastemakers.append({
                'id': row['id'],
                'nickname': row['nickname'],
                'rating': row['rating'] or 1000,
                'games_at_bar': total,
                'win_rate': round(wins / total * 100) if total > 0 else 0
            })
        
        # Get players who have this as home bar but aren't tastemakers yet
        cursor2.execute('''
            SELECT p.id, p.nickname,
                   COALESCE(pbr.wins, 0) + COALESCE(pbr.losses, 0) as games_at_bar
            FROM players p
            LEFT JOIN player_bar_rankings pbr ON p.id = pbr.player_id AND pbr.bar_id = ?
            WHERE p.home_bar_id = ?
              AND p.id NOT IN (SELECT player_id FROM bar_tastemakers WHERE bar_id = ?)
            ORDER BY games_at_bar DESC
        ''', (bar_id, bar_id, bar_id))
        for row in cursor2.fetchall():
            home_bar_players.append({
                'id': row['id'],
                'nickname': row['nickname'],
                'games_at_bar': row['games_at_bar'] or 0
            })
        
        conn2.close()
    except Exception as e:
        print(f"[MASTER] Error loading tastemakers: {e}")
    
    return render_template('master/bar_detail.html', bar=bar, summary=summary, ranked_windows=ranked_windows, 
                           tastemakers=tastemakers, home_bar_players=home_bar_players, active_page='bars')


@master_bp.route('/bar/<int:bar_id>/ranked-window', methods=['POST'])
@admin_required
def create_bar_ranked_window(bar_id):
    """Create a ranked window for a bar."""
    from .database import create_ranked_window
    
    title = request.form.get('title', 'Ranked Period')
    start_datetime = request.form.get('start_datetime')
    end_datetime = request.form.get('end_datetime')
    
    if not start_datetime or not end_datetime:
        flash('Start and end times are required', 'error')
        return redirect(url_for('master.bar_detail', bar_id=bar_id))
    
    success, result = create_ranked_window(bar_id, start_datetime, end_datetime, title)
    
    if success:
        flash('Ranked window created successfully', 'success')
    else:
        flash(f'Error: {result}', 'error')
    
    return redirect(url_for('master.bar_detail', bar_id=bar_id))


@master_bp.route('/bar/<int:bar_id>/ranked-window/<int:window_id>/delete', methods=['POST'])
@admin_required
def delete_bar_ranked_window(bar_id, window_id):
    """Delete a ranked window."""
    from .database import delete_ranked_window
    
    if delete_ranked_window(window_id):
        flash('Ranked window deleted', 'success')
    else:
        flash('Error deleting ranked window', 'error')
    
    return redirect(url_for('master.bar_detail', bar_id=bar_id))


@master_bp.route('/bar/<int:bar_id>/queue/add', methods=['POST'])
@admin_required
def bar_add_to_queue(bar_id):
    """Add a player to this bar's queue."""
    from .models import Player, Queue
    
    nickname = request.form.get('nickname', '').strip()
    
    if not nickname:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'Please enter a name'})
        flash('Please enter a name', 'error')
        return redirect(url_for('master.bar_detail', bar_id=bar_id))
    
    # Find or create player
    player = Player.find_or_create(nickname)
    
    # Check if already in queue at this bar
    if Queue.is_player_in_queue(player['id'], bar_id):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': f'{nickname} is already in queue'})
        flash(f'{nickname} is already in queue', 'error')
        return redirect(url_for('master.bar_detail', bar_id=bar_id))
    
    # Add to queue
    queue_id, session_token = Queue.add_player(player['id'], bar_id=bar_id)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'queue_id': queue_id, 'nickname': nickname})
    
    flash(f'Added {nickname} to queue', 'success')
    return redirect(url_for('master.bar_detail', bar_id=bar_id))


@master_bp.route('/bar/<int:bar_id>/queue/<int:queue_id>/remove', methods=['POST'])
@admin_required
def bar_remove_from_queue(bar_id, queue_id):
    """Remove a player from queue."""
    from .models import Queue
    
    entry = Queue.remove(queue_id)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})
    
    if entry:
        flash(f'Removed {entry.get("nickname", "player")} from queue', 'success')
    return redirect(url_for('master.bar_detail', bar_id=bar_id))


@master_bp.route('/api/bar/<int:bar_id>/queue')
@admin_required
def api_bar_queue(bar_id):
    """API endpoint for bar queue - used for live refresh."""
    from .models import Queue
    
    queue = Queue.get_all_for_bar(bar_id)
    # Recalculate display positions (1, 2, 3...) instead of stored positions
    for i, q in enumerate(queue):
        q['position'] = i + 1
    return jsonify({'queue': queue})


@master_bp.route('/api/bar/<int:bar_id>/match/result', methods=['POST'])
@admin_required
def api_bar_match_result(bar_id):
    """API endpoint to record match result from bar detail page."""
    from .models import Queue
    from .database import record_game
    
    try:
        data = request.get_json() or {}
        winner = data.get('winner')  # 'king' or 'challenger'
        
        if winner not in ['king', 'challenger']:
            return jsonify({'success': False, 'error': 'Invalid winner specified'})
        
        queue = Queue.get_all_for_bar(bar_id)
        if len(queue) < 2:
            return jsonify({'success': False, 'error': 'Not enough players in queue'})
        
        king = queue[0]  # Position 1 = shot caller
        challenger = queue[1]  # Position 2 = challenger
        
        if winner == 'king':
            winner_id = king['player_id']
            loser_id = challenger['player_id']
            # King stays, challenger goes to back
            Queue.remove(challenger['id'])
            Queue.add_player(challenger['player_id'], bar_id=bar_id)
            # Increment king's wins on table
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('UPDATE queue SET wins_on_table = wins_on_table + 1 WHERE id = ?', (king['id'],))
            conn.commit()
            conn.close()
        else:
            winner_id = challenger['player_id']
            loser_id = king['player_id']
            # Challenger becomes new king, old king goes to back
            Queue.remove(king['id'])
            Queue.add_player(king['player_id'], bar_id=bar_id)
            # New king starts with 0 wins on table (default)
        
        # Record the game
        record_game(winner_id, loser_id, bar_id=bar_id)
        
        return jsonify({'success': True, 'message': 'Match recorded successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@master_bp.route('/api/bar/<int:bar_id>/queue/make-king', methods=['POST'])
@admin_required
def api_make_king(bar_id):
    """Move a player to position 1 (shot caller)."""
    try:
        data = request.get_json() or {}
        queue_id = data.get('queue_id')
        
        if not queue_id:
            return jsonify({'success': False, 'error': 'No queue_id provided'})
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Get all queue entries for this bar ordered by position
        cursor.execute('''
            SELECT id, position FROM queue 
            WHERE bar_id = ? AND status IN ('waiting', 'playing')
            ORDER BY position ASC
        ''', (bar_id,))
        queue_entries = cursor.fetchall()
        
        # Find the target entry
        target_idx = None
        for i, entry in enumerate(queue_entries):
            if entry['id'] == queue_id:
                target_idx = i
                break
        
        if target_idx is None:
            conn.close()
            return jsonify({'success': False, 'error': 'Player not found in queue'})
        
        if target_idx == 0:
            conn.close()
            return jsonify({'success': True, 'message': 'Already shot caller'})
        
        # Move target to position 1, shift others down
        # Set target to position 0 temporarily
        cursor.execute('UPDATE queue SET position = 0 WHERE id = ?', (queue_id,))
        
        # Shift everyone from position 1 to target's old position down by 1
        for i in range(target_idx):
            cursor.execute('UPDATE queue SET position = position + 1 WHERE id = ?', (queue_entries[i]['id'],))
        
        # Set target to position 1
        cursor.execute('UPDATE queue SET position = 1, wins_on_table = 0 WHERE id = ?', (queue_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Player is now shot caller'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@master_bp.route('/bar/<int:bar_id>/tastemaker/add', methods=['POST'])
@admin_required
def add_tastemaker(bar_id):
    """Add a player as a tastemaker for this bar."""
    player_id = request.form.get('player_id', type=int)
    
    if not player_id:
        flash('No player selected', 'error')
        return redirect(url_for('master.bar_detail', bar_id=bar_id))
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if already a tastemaker
    cursor.execute('SELECT id FROM bar_tastemakers WHERE bar_id = ? AND player_id = ?', (bar_id, player_id))
    if cursor.fetchone():
        flash('Player is already a tastemaker', 'info')
        conn.close()
        return redirect(url_for('master.bar_detail', bar_id=bar_id))
    
    # Add as tastemaker
    cursor.execute('INSERT INTO bar_tastemakers (bar_id, player_id, created_at) VALUES (?, ?, datetime("now"))', 
                   (bar_id, player_id))
    conn.commit()
    conn.close()
    
    flash('Tastemaker added successfully', 'success')
    return redirect(url_for('master.bar_detail', bar_id=bar_id))


@master_bp.route('/bar/<int:bar_id>/tastemaker/<int:player_id>/remove', methods=['POST'])
@admin_required
def remove_tastemaker(bar_id, player_id):
    """Remove a tastemaker from this bar."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM bar_tastemakers WHERE bar_id = ? AND player_id = ?', (bar_id, player_id))
    conn.commit()
    conn.close()
    
    flash('Tastemaker removed', 'success')
    return redirect(url_for('master.bar_detail', bar_id=bar_id))


@master_bp.route('/bar/<int:bar_id>/report')
@admin_required
def bar_report(bar_id):
    """Bar performance report with real data."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM bars WHERE id = ?', (bar_id,))
    bar = cursor.fetchone()
    
    if not bar:
        conn.close()
        flash('Bar not found', 'error')
        return redirect(url_for('master.bars'))
    
    bar = dict(bar)
    
    # Get real report data
    from datetime import datetime, timedelta
    today = datetime.now()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    # Games this week
    cursor.execute('''
        SELECT COUNT(*) as count FROM game_history 
        WHERE bar_id = ? AND played_at >= ?
    ''', (bar_id, week_ago.strftime('%Y-%m-%d')))
    games_week = cursor.fetchone()['count']
    
    # Games this month
    cursor.execute('''
        SELECT COUNT(*) as count FROM game_history 
        WHERE bar_id = ? AND played_at >= ?
    ''', (bar_id, month_ago.strftime('%Y-%m-%d')))
    games_month = cursor.fetchone()['count']
    
    # Total games all time
    cursor.execute('SELECT COUNT(*) as count FROM game_history WHERE bar_id = ?', (bar_id,))
    games_total = cursor.fetchone()['count']
    
    # Unique players this week
    cursor.execute('''
        SELECT COUNT(DISTINCT winner_id) + COUNT(DISTINCT loser_id) as count 
        FROM game_history WHERE bar_id = ? AND played_at >= ?
    ''', (bar_id, week_ago.strftime('%Y-%m-%d')))
    players_week = cursor.fetchone()['count'] // 2  # Approximate unique
    
    # Queue entries this week
    cursor.execute('''
        SELECT COUNT(*) as count FROM queue_usage_log 
        WHERE bar_id = ? AND created_at >= ?
    ''', (bar_id, week_ago.strftime('%Y-%m-%d')))
    queue_entries_week = cursor.fetchone()['count']
    
    # Top players at this bar (by games played)
    cursor.execute('''
        SELECT p.id, p.nickname, 
               COUNT(*) as games,
               SUM(CASE WHEN gh.winner_id = p.id THEN 1 ELSE 0 END) as wins
        FROM players p
        JOIN game_history gh ON (gh.winner_id = p.id OR gh.loser_id = p.id)
        WHERE gh.bar_id = ?
        GROUP BY p.id
        ORDER BY games DESC
        LIMIT 10
    ''', (bar_id,))
    top_players = [dict(r) for r in cursor.fetchall()]
    
    # Recent games
    cursor.execute('''
        SELECT gh.*, 
               pw.nickname as winner_name,
               pl.nickname as loser_name
        FROM game_history gh
        LEFT JOIN players pw ON gh.winner_id = pw.id
        LEFT JOIN players pl ON gh.loser_id = pl.id
        WHERE gh.bar_id = ?
        ORDER BY gh.played_at DESC
        LIMIT 20
    ''', (bar_id,))
    recent_games = [dict(r) for r in cursor.fetchall()]
    
    conn.close()
    
    # Build report object
    report = {
        'period': f"Weekly Report - {week_ago.strftime('%b %d')} - {today.strftime('%b %d, %Y')}",
        'created_at': today.strftime('%Y-%m-%d %H:%M'),
        'games_week': games_week,
        'games_month': games_month,
        'games_total': games_total,
        'players_week': players_week,
        'queue_entries_week': queue_entries_week
    }
    
    return render_template('master/bar_report.html', bar=bar, report=report, 
                          top_players=top_players, recent_games=recent_games)


# ============================================
# API ENDPOINTS FOR DATA ACCESS
# ============================================

@master_bp.route('/api/v1/players')
@admin_required
def api_players():
    """API: Get all players with filtering."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Query params
    bar_id = request.args.get('bar_id', type=int)
    cohort = request.args.get('cohort')
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    query = 'SELECT * FROM players WHERE (is_active = 1 OR is_active IS NULL)'
    params = []
    
    if bar_id:
        query += ' AND home_bar_id = ?'
        params.append(bar_id)
    if cohort:
        query += ' AND cohort_frequency = ?'
        params.append(cohort)
    
    query += ' ORDER BY rating DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    players = [dict(row) for row in cursor.fetchall()]
    
    # Get total count
    cursor.execute('SELECT COUNT(*) FROM players')
    total = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'success': True,
        'data': players,
        'total': total,
        'limit': limit,
        'offset': offset
    })

@master_bp.route('/api/v1/activity')
@admin_required
def api_activity():
    """API: Get user activity events."""
    conn = get_db()
    cursor = conn.cursor()
    
    player_id = request.args.get('player_id', type=int)
    event_type = request.args.get('event_type')
    bar_id = request.args.get('bar_id', type=int)
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    query = 'SELECT * FROM user_activity WHERE 1=1'
    params = []
    
    if player_id:
        query += ' AND player_id = ?'
        params.append(player_id)
    if event_type:
        query += ' AND event_type = ?'
        params.append(event_type)
    if bar_id:
        query += ' AND bar_id = ?'
        params.append(bar_id)
    if date_from:
        query += ' AND created_at >= ?'
        params.append(date_from)
    if date_to:
        query += ' AND created_at <= ?'
        params.append(date_to)
    
    query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    activities = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({
        'success': True,
        'data': activities,
        'limit': limit,
        'offset': offset
    })

@master_bp.route('/api/v1/games')
@admin_required
def api_games():
    """API: Get game history."""
    conn = get_db()
    cursor = conn.cursor()
    
    player_id = request.args.get('player_id', type=int)
    bar_id = request.args.get('bar_id', type=int)
    winner_id = request.args.get('winner_id', type=int)
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    query = 'SELECT * FROM game_history WHERE 1=1'
    params = []
    
    if player_id:
        query += ' AND (player1_id = ? OR player2_id = ?)'
        params.extend([player_id, player_id])
    if bar_id:
        query += ' AND bar_id = ?'
        params.append(bar_id)
    if winner_id:
        query += ' AND winner_id = ?'
        params.append(winner_id)
    
    query += ' ORDER BY played_at DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    games = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({
        'success': True,
        'data': games,
        'limit': limit,
        'offset': offset
    })

@master_bp.route('/api/v1/cohorts')
@admin_required
def api_cohorts():
    """API: Get cohort data."""
    bar_id = request.args.get('bar_id', type=int)
    cohort_type = request.args.get('cohort_type')  # frequency, time, spending, skill
    include_players = request.args.get('include_players', 'false') == 'true'
    
    conn = get_db()
    cursor = conn.cursor()
    
    cohorts = {}
    
    # Frequency cohorts
    if not cohort_type or cohort_type == 'frequency':
        query = 'SELECT cohort_frequency, COUNT(*) as count FROM players WHERE cohort_frequency IS NOT NULL'
        if bar_id:
            query += ' AND home_bar_id = ?'
            cursor.execute(query + ' GROUP BY cohort_frequency', [bar_id] if bar_id else [])
        else:
            cursor.execute(query + ' GROUP BY cohort_frequency')
        cohorts['frequency'] = {row[0]: row[1] for row in cursor.fetchall()}
    
    # Time cohorts
    if not cohort_type or cohort_type == 'time':
        query = 'SELECT cohort_time, COUNT(*) as count FROM players WHERE cohort_time IS NOT NULL'
        if bar_id:
            query += ' AND home_bar_id = ?'
            cursor.execute(query + ' GROUP BY cohort_time', [bar_id] if bar_id else [])
        else:
            cursor.execute(query + ' GROUP BY cohort_time')
        cohorts['time'] = {row[0]: row[1] for row in cursor.fetchall()}
    
    # Spending cohorts
    if not cohort_type or cohort_type == 'spending':
        query = 'SELECT cohort_spending, COUNT(*) as count FROM players WHERE cohort_spending IS NOT NULL'
        if bar_id:
            query += ' AND home_bar_id = ?'
            cursor.execute(query + ' GROUP BY cohort_spending', [bar_id] if bar_id else [])
        else:
            cursor.execute(query + ' GROUP BY cohort_spending')
        cohorts['spending'] = {row[0]: row[1] for row in cursor.fetchall()}
    
    conn.close()
    
    return jsonify({
        'success': True,
        'data': cohorts,
        'bar_id': bar_id
    })

@master_bp.route('/api/v1/shop/interactions')
@admin_required
def api_shop_interactions():
    """API: Get shop interaction data."""
    conn = get_db()
    cursor = conn.cursor()
    
    player_id = request.args.get('player_id', type=int)
    product_id = request.args.get('product_id')
    action = request.args.get('action')
    category = request.args.get('category')
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    query = 'SELECT * FROM shop_interactions WHERE 1=1'
    params = []
    
    if player_id:
        query += ' AND player_id = ?'
        params.append(player_id)
    if product_id:
        query += ' AND product_id = ?'
        params.append(product_id)
    if action:
        query += ' AND action = ?'
        params.append(action)
    if category:
        query += ' AND product_category = ?'
        params.append(category)
    
    query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    interactions = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({
        'success': True,
        'data': interactions,
        'limit': limit,
        'offset': offset
    })

@master_bp.route('/api/v1/ads/impressions')
@admin_required
def api_ad_impressions():
    """API: Get ad impression data."""
    conn = get_db()
    cursor = conn.cursor()
    
    placement = request.args.get('placement')
    brand = request.args.get('brand')
    bar_id = request.args.get('bar_id', type=int)
    clicked = request.args.get('clicked')
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    query = 'SELECT * FROM ad_impressions WHERE 1=1'
    params = []
    
    if placement:
        query += ' AND ad_placement = ?'
        params.append(placement)
    if brand:
        query += ' AND ad_brand = ?'
        params.append(brand)
    if bar_id:
        query += ' AND bar_id = ?'
        params.append(bar_id)
    if clicked is not None:
        query += ' AND clicked = ?'
        params.append(1 if clicked == 'true' else 0)
    
    query += ' ORDER BY impression_at DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    impressions = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({
        'success': True,
        'data': impressions,
        'limit': limit,
        'offset': offset
    })

@master_bp.route('/api/v1/pool-nights')
@admin_required
def api_pool_nights():
    """API: Get pool night events."""
    conn = get_db()
    cursor = conn.cursor()
    
    bar_id = request.args.get('bar_id', type=int)
    host_id = request.args.get('host_id', type=int)
    status = request.args.get('status')
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    query = 'SELECT * FROM pool_nights WHERE 1=1'
    params = []
    
    if bar_id:
        query += ' AND bar_id = ?'
        params.append(bar_id)
    if host_id:
        query += ' AND host_id = ?'
        params.append(host_id)
    if status:
        query += ' AND status = ?'
        params.append(status)
    
    query += ' ORDER BY event_date DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    events = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({
        'success': True,
        'data': events,
        'limit': limit,
        'offset': offset
    })

@master_bp.route('/api/v1/rsvp-stats')
@admin_required
def api_rsvp_stats():
    """API: Get RSVP reliability stats."""
    conn = get_db()
    cursor = conn.cursor()
    
    player_id = request.args.get('player_id', type=int)
    min_show_rate = request.args.get('min_show_rate', type=float)
    
    query = 'SELECT * FROM player_rsvp_stats WHERE 1=1'
    params = []
    
    if player_id:
        query += ' AND player_id = ?'
        params.append(player_id)
    if min_show_rate:
        query += ' AND show_rate >= ?'
        params.append(min_show_rate)
    
    query += ' ORDER BY show_rate DESC'
    
    cursor.execute(query, params)
    stats = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({
        'success': True,
        'data': stats
    })

@master_bp.route('/api/v1/monthly-rankings')
@admin_required
def api_monthly_rankings():
    """API: Get monthly ranking history (plaques)."""
    conn = get_db()
    cursor = conn.cursor()
    
    player_id = request.args.get('player_id', type=int)
    bar_id = request.args.get('bar_id', type=int)
    place = request.args.get('place', type=int)
    year = request.args.get('year', type=int)
    
    query = 'SELECT * FROM monthly_rankings WHERE 1=1'
    params = []
    
    if player_id:
        query += ' AND player_id = ?'
        params.append(player_id)
    if bar_id:
        query += ' AND bar_id = ?'
        params.append(bar_id)
    if place:
        query += ' AND place = ?'
        params.append(place)
    if year:
        query += ' AND year = ?'
        params.append(year)
    
    query += ' ORDER BY year DESC, month DESC'
    
    cursor.execute(query, params)
    rankings = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({
        'success': True,
        'data': rankings
    })

@master_bp.route('/api/v1/export/<data_type>')
@admin_required
def api_export(data_type):
    """API: Export data as CSV or JSON."""
    format = request.args.get('format', 'json')
    
    conn = get_db()
    cursor = conn.cursor()
    
    table_map = {
        'players': 'players',
        'activity': 'user_activity',
        'games': 'game_history',
        'shop': 'shop_interactions',
        'ads': 'ad_impressions',
        'pool_nights': 'pool_nights',
        'rsvps': 'pool_night_rsvps',
        'monthly_rankings': 'monthly_rankings'
    }
    
    if data_type not in table_map:
        return jsonify({'success': False, 'error': 'Invalid data type'}), 400
    
    cursor.execute(f'SELECT * FROM {table_map[data_type]} LIMIT 10000')
    data = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    if format == 'csv':
        import csv
        import io
        from flask import Response
        
        if not data:
            return Response('No data', mimetype='text/csv')
        
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
        
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={data_type}.csv'}
        )
    
    return jsonify({
        'success': True,
        'data': data,
        'count': len(data)
    })



# ============================================
# TASTEMAKER API ENDPOINTS
# ============================================

@master_bp.route('/api/tastemaker/grant', methods=['POST'])
@admin_required
def api_grant_tastemaker():
    """Grant tastemaker status to a player."""
    try:
        from .database_enhanced import grant_tastemaker
        data = request.json or {}
        player_id = data.get('player_id')
        
        if not player_id:
            return jsonify({'success': False, 'error': 'player_id required'}), 400
        
        result = grant_tastemaker(player_id, granted_by_admin=True, notes='Granted via admin panel')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@master_bp.route('/api/tastemaker/revoke', methods=['POST'])
@admin_required
def api_revoke_tastemaker():
    """Revoke tastemaker status from a player."""
    try:
        from .database_enhanced import revoke_tastemaker
        data = request.json or {}
        player_id = data.get('player_id')
        
        if not player_id:
            return jsonify({'success': False, 'error': 'player_id required'}), 400
        
        result = revoke_tastemaker(player_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@master_bp.route('/api/tastemaker/list')
@admin_required
def api_list_tastemakers():
    """Get all tastemakers."""
    try:
        from .database_enhanced import get_all_tastemakers
        tastemakers = get_all_tastemakers()
        return jsonify({'success': True, 'tastemakers': tastemakers})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@master_bp.route('/api/tastemaker/bar/<int:bar_id>')
@admin_required
def api_bar_tastemakers(bar_id):
    """Get tastemakers for a specific bar."""
    try:
        from .database_enhanced import get_bar_tastemakers
        tastemakers = get_bar_tastemakers(bar_id)
        return jsonify({'success': True, 'tastemakers': tastemakers})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# =========================================================================
# BRAND ANALYTICS API - For alcohol marketing intelligence
# =========================================================================

@master_bp.route('/api/brand/win-loss-performance')
@admin_required
def api_brand_win_loss():
    """Get brand CTR breakdown by win/loss game context."""
    try:
        brand = request.args.get('brand')
        days = request.args.get('days', 30, type=int)
        
        try:
            from . import database_v2 as db2
            data = db2.get_brand_win_loss_performance(brand, days)
        except ImportError:
            # Return empty data - no mock data, only real data from actual campaigns
            data = []
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@master_bp.route('/api/brand/attribution')
@admin_required
def api_brand_attribution():
    """Get drink attribution data for brands."""
    try:
        brand = request.args.get('brand')
        days = request.args.get('days', 30, type=int)
        
        try:
            from . import database_v2 as db2
            data = db2.get_drink_attribution_report(brand, days)
        except ImportError:
            # Return empty data - no mock data, only real data from actual campaigns
            data = []
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@master_bp.route('/api/brand/compare')
@admin_required
def api_brand_compare():
    """Compare multiple brands head-to-head."""
    try:
        brands = request.args.getlist('brands')
        days = request.args.get('days', 30, type=int)
        
        # Return empty if no brands specified (no fake defaults)
        if not brands:
            return jsonify({'success': True, 'data': []})
        
        try:
            from . import database_v2 as db2
            data = db2.get_brand_comparison(brands, days)
        except ImportError:
            # Return empty data - no mock data, only real data from actual campaigns
            data = []
        
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



# ============ ADVERTISER MANAGEMENT ============

@master_bp.route('/advertisers')
@admin_required
def advertisers():
    """Advertiser management page with campaign metrics."""
    print("[MASTER] Advertisers page loaded")
    from .advertiser_system import get_all_advertisers, AD_CATEGORIES, PLACEMENT_TYPES, init_advertiser_tables
    from datetime import date, timedelta, datetime as dt
    
    # Ensure tables exist
    init_advertiser_tables()
    
    # Parse filters
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    start_param = request.args.get('start_date', '')
    end_param = request.args.get('end_date', '')
    status_filter = request.args.get('status', 'all')
    advertiser_filter = request.args.get('advertiser_id', type=int)
    
    if start_param:
        try:
            start_date = dt.strptime(start_param, '%Y-%m-%d').date()
        except ValueError:
            pass
    
    if end_param:
        try:
            end_date = dt.strptime(end_param, '%Y-%m-%d').date()
        except ValueError:
            pass
    
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    
    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')
    
    # Get all advertisers for the dropdown
    all_advertisers = get_all_advertisers()
    
    # Get campaigns with real ad metrics
    conn = get_db()
    cursor = conn.cursor()
    
    campaigns = []
    try:
        # Build WHERE clause for campaigns
        where_parts = []
        params = []
        
        if status_filter == 'cancelled':
            # When viewing cancelled, show all (including from inactive advertisers)
            where_parts.append("c.status = 'cancelled'")
        elif status_filter and status_filter != 'all':
            where_parts.append("c.status = ?")
            where_parts.append("a.is_active = 1")  # Only active advertisers
            params.append(status_filter)
        else:
            # Default: exclude cancelled, only active advertisers
            where_parts.append("c.status != 'cancelled'")
            where_parts.append("a.is_active = 1")
        
        if advertiser_filter:
            where_parts.append("c.advertiser_id = ?")
            params.append(advertiser_filter)
        
        where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""
        
        # Get all campaigns with basic info
        cursor.execute(f'''
            SELECT c.id, c.name, c.status, c.start_date, c.end_date, c.budget,
                   a.id as advertiser_id, a.name as advertiser_name
            FROM campaigns c
            LEFT JOIN advertisers a ON c.advertiser_id = a.id
            {where_clause}
            ORDER BY c.created_at DESC
        ''', params)
        
        campaign_rows = cursor.fetchall()
        
        # For each campaign, get ad metrics
        for row in campaign_rows:
            campaign_id = row['id']
            
            # Get impressions, clicks, unique players from ad_events
            cursor.execute('''
                SELECT 
                    SUM(CASE WHEN event_type = 'impression' THEN 1 ELSE 0 END) as impressions,
                    SUM(CASE WHEN event_type = 'click' THEN 1 ELSE 0 END) as clicks,
                    COUNT(DISTINCT player_id) as unique_players
                FROM ad_events
                WHERE campaign_id = ?
                  AND date(created_at) BETWEEN ? AND ?
            ''', (campaign_id, start_date_str, end_date_str))
            
            metrics = cursor.fetchone()
            impressions = metrics['impressions'] or 0 if metrics else 0
            clicks = metrics['clicks'] or 0 if metrics else 0
            unique_players = metrics['unique_players'] or 0 if metrics else 0
            ctr = round((clicks / impressions * 100), 1) if impressions > 0 else 0
            
            # Get top 3 bars by impressions
            cursor.execute('''
                SELECT b.name, COUNT(*) as imp_count
                FROM ad_events ae
                LEFT JOIN bars b ON ae.bar_id = b.id
                WHERE ae.campaign_id = ?
                  AND ae.event_type = 'impression'
                  AND date(ae.created_at) BETWEEN ? AND ?
                  AND b.name IS NOT NULL
                GROUP BY ae.bar_id
                ORDER BY imp_count DESC
                LIMIT 3
            ''', (campaign_id, start_date_str, end_date_str))
            
            top_bars = [r['name'] for r in cursor.fetchall()]
            top_bars_str = ", ".join(top_bars) if top_bars else "-"
            
            campaigns.append({
                'id': campaign_id,
                'name': row['name'],
                'advertiser_id': row['advertiser_id'],
                'advertiser_name': row['advertiser_name'] or 'Unknown',
                'status': row['status'] or 'draft',
                'start_date': row['start_date'],
                'end_date': row['end_date'],
                'budget': row['budget'] or 0,
                'impressions': impressions,
                'clicks': clicks,
                'ctr': ctr,
                'unique_players': unique_players,
                'top_bars': top_bars_str
            })
        
        # Compute per-advertiser totals
        advertiser_totals = {}
        for camp in campaigns:
            adv_id = camp['advertiser_id']
            if adv_id not in advertiser_totals:
                advertiser_totals[adv_id] = {
                    'impressions': 0,
                    'clicks': 0,
                    'unique_players': 0
                }
            advertiser_totals[adv_id]['impressions'] += camp['impressions']
            advertiser_totals[adv_id]['clicks'] += camp['clicks']
            advertiser_totals[adv_id]['unique_players'] += camp['unique_players']
        
        # Calculate CTR for each advertiser
        for adv_id, totals in advertiser_totals.items():
            totals['ctr'] = round((totals['clicks'] / totals['impressions'] * 100), 1) if totals['impressions'] > 0 else 0
    
    except Exception as e:
        print(f"[ADVERTISERS] Error fetching campaign metrics: {e}")
        advertiser_totals = {}
    
    conn.close()
    
    # Calculate global totals
    total_impressions = sum(c['impressions'] for c in campaigns)
    total_clicks = sum(c['clicks'] for c in campaigns)
    total_ctr = round((total_clicks / total_impressions * 100), 1) if total_impressions > 0 else 0
    
    embed = request.args.get('embed', '0') == '1'
    return render_template('master/advertisers.html', 
                           advertisers=all_advertisers,
                           advertiser_totals=advertiser_totals,
                           campaigns=campaigns,
                           categories=AD_CATEGORIES,
                           placements=PLACEMENT_TYPES,
                           # Filter state
                           start_date=start_date_str,
                           end_date=end_date_str,
                           status_filter=status_filter,
                           advertiser_filter=advertiser_filter,
                           # Totals
                           total_impressions=total_impressions,
                           total_clicks=total_clicks,
                           total_ctr=total_ctr,
                           total_campaigns=len(campaigns),
                           active_page='advertisers',
                           embed=embed)


@master_bp.route('/advertisers/export')
@admin_required
def export_campaigns_csv():
    """Export campaign metrics to CSV."""
    from datetime import date, timedelta, datetime as dt
    import csv
    import io
    
    # Parse filters (same as advertisers route)
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    start_param = request.args.get('start_date', '')
    end_param = request.args.get('end_date', '')
    status_filter = request.args.get('status', 'all')
    advertiser_filter = request.args.get('advertiser_id', type=int)
    
    if start_param:
        try:
            start_date = dt.strptime(start_param, '%Y-%m-%d').date()
        except ValueError:
            pass
    
    if end_param:
        try:
            end_date = dt.strptime(end_param, '%Y-%m-%d').date()
        except ValueError:
            pass
    
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    
    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')
    
    conn = get_db()
    cursor = conn.cursor()
    
    campaigns = []
    try:
        # Build WHERE clause
        where_parts = []
        params = []
        
        if status_filter and status_filter != 'all':
            where_parts.append("c.status = ?")
            params.append(status_filter)
        
        if advertiser_filter:
            where_parts.append("c.advertiser_id = ?")
            params.append(advertiser_filter)
        
        where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""
        
        cursor.execute(f'''
            SELECT c.id, c.name, c.status, c.start_date, c.end_date, c.total_budget,
                   a.id as advertiser_id, a.company_name as advertiser_name
            FROM campaigns c
            LEFT JOIN advertisers a ON c.advertiser_id = a.id
            {where_clause}
            ORDER BY a.company_name, c.name
        ''', params)
        
        campaign_rows = cursor.fetchall()
        
        for row in campaign_rows:
            campaign_id = row['id']
            
            # Get metrics
            cursor.execute('''
                SELECT 
                    SUM(CASE WHEN event_type = 'impression' THEN 1 ELSE 0 END) as impressions,
                    SUM(CASE WHEN event_type = 'click' THEN 1 ELSE 0 END) as clicks,
                    COUNT(DISTINCT player_id) as unique_players
                FROM ad_events
                WHERE campaign_id = ?
                  AND date(created_at) BETWEEN ? AND ?
            ''', (campaign_id, start_date_str, end_date_str))
            
            metrics = cursor.fetchone()
            impressions = metrics['impressions'] or 0 if metrics else 0
            clicks = metrics['clicks'] or 0 if metrics else 0
            unique_players = metrics['unique_players'] or 0 if metrics else 0
            ctr = round((clicks / impressions * 100), 2) if impressions > 0 else 0
            
            # Get top 3 bars
            cursor.execute('''
                SELECT b.name, COUNT(*) as imp_count
                FROM ad_events ae
                LEFT JOIN bars b ON ae.bar_id = b.id
                WHERE ae.campaign_id = ?
                  AND ae.event_type = 'impression'
                  AND date(ae.created_at) BETWEEN ? AND ?
                  AND b.name IS NOT NULL
                GROUP BY ae.bar_id
                ORDER BY imp_count DESC
                LIMIT 3
            ''', (campaign_id, start_date_str, end_date_str))
            
            top_bars = "; ".join([r['name'] for r in cursor.fetchall()]) or "-"
            
            campaigns.append({
                'campaign_id': campaign_id,
                'campaign_name': row['name'],
                'advertiser_name': row['advertiser_name'] or 'Unknown',
                'status': row['status'] or 'draft',
                'start_date': row['start_date'] or '',
                'end_date': row['end_date'] or '',
                'impressions': impressions,
                'clicks': clicks,
                'ctr': ctr,
                'unique_players': unique_players,
                'top_bars': top_bars
            })
    
    except Exception as e:
        print(f"[CSV EXPORT] Error: {e}")
    
    conn.close()
    
    # Generate CSV
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        'campaign_id', 'campaign_name', 'advertiser_name', 'status',
        'start_date', 'end_date', 'impressions', 'clicks', 'ctr',
        'unique_players', 'top_bars'
    ])
    writer.writeheader()
    writer.writerows(campaigns)
    
    # Create response
    output.seek(0)
    filename = f"campaigns_{start_date_str}_to_{end_date_str}.csv"
    
    from flask import Response
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@master_bp.route('/advertiser/add', methods=['POST'])
@admin_required
def add_advertiser():
    """Add a new advertiser."""
    from .advertiser_system import add_advertiser as create_advertiser
    
    name = request.form.get('name')
    category = request.form.get('category')
    contact_name = request.form.get('contact_name')
    contact_email = request.form.get('contact_email')
    website = request.form.get('website')
    notes = request.form.get('notes')
    
    if not name:
        flash('Advertiser name is required', 'error')
        return redirect(url_for('master.advertisers'))
    
    advertiser_id = create_advertiser(
        name=name,
        category=category,
        contact_name=contact_name,
        contact_email=contact_email,
        website=website,
        notes=notes
    )
    
    if advertiser_id:
        flash(f'{name} added successfully', 'success')
    else:
        flash('Could not add advertiser', 'error')
    
    return redirect(url_for('master.advertisers'))


@master_bp.route('/advertiser/<int:advertiser_id>/edit', methods=['GET'])
@admin_required
def edit_advertiser_form(advertiser_id):
    """Show advertisers page with a specific advertiser loaded for editing."""
    from .advertiser_system import get_all_advertisers, get_advertiser_by_id, AD_CATEGORIES, PLACEMENT_TYPES, init_advertiser_tables
    
    init_advertiser_tables()
    
    editing_advertiser = get_advertiser_by_id(advertiser_id)
    if not editing_advertiser:
        flash('Advertiser not found', 'error')
        return redirect(url_for('master.advertisers'))
    
    advertisers = get_all_advertisers()
    embed = request.args.get('embed', '0') == '1'
    return render_template('master/advertisers.html',
                           advertisers=advertisers,
                           categories=AD_CATEGORIES,
                           placements=PLACEMENT_TYPES,
                           editing_advertiser=editing_advertiser,
                           active_page='advertisers',
                           embed=embed)


@master_bp.route('/advertiser/<int:advertiser_id>/edit', methods=['POST'])
@admin_required
def edit_advertiser_save(advertiser_id):
    """Save edits to an existing advertiser."""
    from .advertiser_system import update_advertiser
    
    name = request.form.get('name')
    category = request.form.get('category')
    contact_email = request.form.get('email')
    notes = request.form.get('notes')
    
    if not name:
        flash('Advertiser name is required', 'error')
        return redirect(url_for('master.edit_advertiser_form', advertiser_id=advertiser_id))
    
    success = update_advertiser(advertiser_id, name, category, contact_email, notes)
    
    if success:
        flash(f'{name} updated successfully', 'success')
    else:
        flash('Could not update advertiser', 'error')
    
    return redirect(url_for('master.advertisers'))


@master_bp.route('/advertiser/<int:advertiser_id>/delete', methods=['POST'])
@admin_required
def delete_advertiser(advertiser_id):
    """Deactivate an advertiser (soft delete)."""
    from .advertiser_system import deactivate_advertiser, get_advertiser_by_id
    
    advertiser = get_advertiser_by_id(advertiser_id)
    if not advertiser:
        flash('Advertiser not found', 'error')
        return redirect(url_for('master.advertisers'))
    
    success, message = deactivate_advertiser(advertiser_id)
    
    if success:
        flash(f'{advertiser["name"]} deactivated', 'success')
    else:
        flash(message, 'error')
    
    return redirect(url_for('master.advertisers'))


@master_bp.route('/advertiser/<int:advertiser_id>')
@admin_required
def advertiser_detail(advertiser_id):
    """View advertiser details with active/past campaigns and revenue."""
    from .advertiser_system import get_advertiser_details
    from datetime import date
    
    details = get_advertiser_details(advertiser_id)
    if not details:
        flash('Advertiser not found', 'error')
        return redirect(url_for('master.advertisers'))
    
    # Get real ad stats from ad_events table
    conn = get_db()
    cursor = conn.cursor()
    
    # Query ad_events for this advertiser's totals
    total_impressions = 0
    total_clicks = 0
    try:
        cursor.execute('''
            SELECT 
                SUM(CASE WHEN event_type = 'impression' THEN 1 ELSE 0 END) as impressions,
                SUM(CASE WHEN event_type = 'click' THEN 1 ELSE 0 END) as clicks
            FROM ad_events
            WHERE advertiser_id = ?
        ''', (advertiser_id,))
        row = cursor.fetchone()
        if row:
            total_impressions = row['impressions'] or 0
            total_clicks = row['clicks'] or 0
    except:
        pass
    
    # Calculate CTR
    avg_ctr = round((total_clicks / total_impressions * 100), 1) if total_impressions > 0 else 0
    
    # Separate active and past campaigns
    today = date.today().isoformat()
    campaigns = details.get('campaigns') or []
    active_campaigns = []
    past_campaigns = []
    total_revenue = 0
    
    for c in campaigns:
        campaign = dict(c) if hasattr(c, 'keys') else {
            'id': c[0], 'name': c[1], 'start_date': c[2], 'end_date': c[3],
            'status': c[4] if len(c) > 4 else 'active',
            'impressions': 0, 'clicks': 0, 'revenue': 0, 'ctr': 0, 'placements': ''
        }
        
        # Get real impressions/clicks for this campaign from ad_events
        campaign_id = campaign.get('id')
        if campaign_id:
            try:
                cursor.execute('''
                    SELECT 
                        SUM(CASE WHEN event_type = 'impression' THEN 1 ELSE 0 END) as impressions,
                        SUM(CASE WHEN event_type = 'click' THEN 1 ELSE 0 END) as clicks
                    FROM ad_events
                    WHERE campaign_id = ?
                ''', (campaign_id,))
                row = cursor.fetchone()
                if row:
                    campaign['impressions'] = row['impressions'] or 0
                    campaign['clicks'] = row['clicks'] or 0
            except:
                pass
        
        # Calculate revenue (CPM of $8.50)
        impressions = campaign.get('impressions') or 0
        campaign['revenue'] = (impressions / 1000) * 8.50
        total_revenue += campaign['revenue']
        
        # Calculate CTR
        clicks = campaign.get('clicks') or 0
        campaign['ctr'] = round((clicks / impressions * 100), 1) if impressions > 0 else 0
        
        # Determine if active or past
        end_date = campaign.get('end_date')
        status = campaign.get('status', 'active')
        
        if status == 'cancelled':
            past_campaigns.append(campaign)
        elif end_date and end_date < today:
            past_campaigns.append(campaign)
        else:
            active_campaigns.append(campaign)
    
    conn.close()
    
    # Calculate total spend (based on impressions at $8.50 CPM)
    total_spend = round((total_impressions / 1000) * 8.50, 2)
    
    return render_template('master/advertiser_detail.html',
                           advertiser=details['advertiser'],
                           campaigns=active_campaigns + past_campaigns,
                           active_campaigns=active_campaigns,
                           past_campaigns=past_campaigns,
                           creatives=details['creatives'],
                           surveys=details['surveys'],
                           questions=details.get('surveys') or [],
                           stats=details['stats'],
                           total_impressions=total_impressions,
                           total_clicks=total_clicks,
                           avg_ctr=avg_ctr,
                           total_spend=total_spend,
                           total_revenue=total_revenue,
                           avg_cpm=8.50,
                           active_page='advertisers')


@master_bp.route('/campaign/add', methods=['POST'])
@admin_required
def add_campaign():
    """Add a new campaign for an advertiser."""
    from .advertiser_system import create_campaign, add_survey_question
    
    advertiser_id = request.form.get('advertiser_id', type=int)
    name = request.form.get('name')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    placements = request.form.getlist('placements')
    surveys = request.form.getlist('surveys')
    custom_surveys = request.form.getlist('custom_survey')
    
    if not advertiser_id or not name:
        flash('Campaign name is required', 'error')
        return redirect(url_for('master.advertisers'))
    
    campaign_id = create_campaign(
        advertiser_id=advertiser_id,
        name=name,
        start_date=start_date or None,
        end_date=end_date or None
    )
    
    # Add survey questions
    all_surveys = surveys + [s for s in custom_surveys if s.strip()]
    for question in all_surveys:
        if question.strip():
            add_survey_question(
                advertiser_id=advertiser_id,
                campaign_id=campaign_id,
                question_text=question
            )
    
    flash(f'Campaign "{name}" created', 'success')
    return redirect(url_for('master.advertiser_detail', advertiser_id=advertiser_id))


@master_bp.route('/api/survey-suggestions')
@admin_required
def api_survey_suggestions():
    """Get AI-suggested survey questions for a category."""
    from .advertiser_system import get_suggested_questions
    
    category = request.args.get('category', 'default')
    brand = request.args.get('brand', '{brand}')
    
    questions = get_suggested_questions(brand, category)
    
    # Add mock effectiveness scores (in future, calculate from actual data)
    suggestions = []
    scores = [85, 78, 72, 65]  # Decreasing effectiveness
    for i, q in enumerate(questions):
        suggestions.append({
            'question': q,
            'effectiveness': scores[i] if i < len(scores) else 60,
            'ai_suggested': True
        })
    
    return jsonify({'success': True, 'suggestions': suggestions})


# ============ AD PLACEMENTS ============

@master_bp.route('/placements')
@admin_required
def placements():
    """Redirect to advertisers - ad placements managed through campaigns."""
    return redirect(url_for('master.advertisers'))


@master_bp.route('/api/placements/<int:slot_id>/availability')
@admin_required
def api_slot_availability(slot_id):
    """Get time slot availability for a placement."""
    from .ad_placement import get_available_time_slots
    
    advertiser_id = request.args.get('advertiser_id', type=int)
    availability = get_available_time_slots(slot_id, advertiser_id)
    
    return jsonify({'success': True, 'slots': availability})


@master_bp.route('/api/placements/<int:slot_id>/ads')
@admin_required
def api_slot_ads(slot_id):
    """Get scheduled ads for a placement."""
    from .ad_placement import get_slot_details
    
    details = get_slot_details(slot_id)
    ads = []
    for ad in details.get('scheduled_ads', []):
        ads.append({
            'id': ad['id'],
            'advertiser': ad['advertiser_name'],
            'campaign': ad['campaign_name'],
            'file': ad['file_name'],
            'schedule_type': ad['schedule_type'],
            'start_time': ad['start_time'],
            'end_time': ad['end_time']
        })
    
    return jsonify({'success': True, 'ads': ads})


@master_bp.route('/api/placements/schedule', methods=['POST'])
@admin_required
def api_schedule_ad():
    """Schedule an ad to a placement."""
    from .ad_placement import schedule_ad
    from .advertiser_system import add_creative, create_campaign
    import os
    
    slot_id = request.form.get('slot_id', type=int)
    advertiser_id = request.form.get('advertiser_id', type=int)
    schedule_type = request.form.get('schedule_type', 'all_day')
    start_time = request.form.get('start_time')
    end_time = request.form.get('end_time')
    
    # Handle file upload
    creative_file = request.files.get('creative')
    if not creative_file:
        return jsonify({'success': False, 'error': 'No creative file uploaded'})
    
    # Save file
    ads_folder = os.path.join(os.path.dirname(__file__), 'static', 'ads')
    os.makedirs(ads_folder, exist_ok=True)
    
    filename = f"ad_{advertiser_id}_{int(datetime.now().timestamp())}_{creative_file.filename}"
    filepath = os.path.join(ads_folder, filename)
    creative_file.save(filepath)
    
    # Create a campaign if needed (or use existing)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM campaigns WHERE advertiser_id = ? ORDER BY id DESC LIMIT 1', (advertiser_id,))
    campaign = cursor.fetchone()
    
    if campaign:
        campaign_id = campaign['id']
    else:
        campaign_id = create_campaign(advertiser_id, 'Default Campaign')
    
    # Create creative record
    creative_id = add_creative(campaign_id, advertiser_id, filename, label=creative_file.filename)
    
    # Schedule the ad
    result = schedule_ad(
        slot_id=slot_id,
        creative_id=creative_id,
        campaign_id=campaign_id,
        advertiser_id=advertiser_id,
        schedule_type=schedule_type,
        start_time=start_time if schedule_type == 'specific_times' else None,
        end_time=end_time if schedule_type == 'specific_times' else None
    )
    
    conn.close()
    return jsonify(result)


@master_bp.route('/api/placements/remove/<int:scheduled_id>', methods=['POST'])
@admin_required
def api_remove_scheduled_ad(scheduled_id):
    """Remove a scheduled ad."""
    from .ad_placement import remove_scheduled_ad
    
    remove_scheduled_ad(scheduled_id)
    return jsonify({'success': True})


@master_bp.route('/advertiser/<int:advertiser_id>/campaign/new')
@master_bp.route('/campaign/new')
@admin_required
def new_campaign(advertiser_id=None):
    """Campaign creation page with interactive ad placement."""
    from .advertiser_system import get_advertiser_details, get_suggested_questions, AD_CATEGORIES, get_all_advertisers
    from .ad_scheduling import PLACEMENT_INFO, init_ad_scheduling_tables, get_time_slot_availability, get_best_time_slots
    from .services.pos_analytics import get_campaign_estimates
    
    init_ad_scheduling_tables()
    
    # Get all advertisers for dropdown
    all_advertisers = get_all_advertisers()
    
    # Get specific advertiser if provided
    advertiser = None
    suggested_questions = []
    if advertiser_id:
        details = get_advertiser_details(advertiser_id)
        if details:
            advertiser = details['advertiser']
            category = advertiser['category'] if advertiser else 'default'
            # Get suggested questions
            suggested = get_suggested_questions(advertiser['name'], category)
            suggested_questions = [{'question': q, 'effectiveness': 85 - (i * 7)} for i, q in enumerate(suggested)]
    
    # Get efficiency data for each placement
    efficiency = {}
    for code in PLACEMENT_INFO.keys():
        best = get_best_time_slots(code, 1)
        efficiency[code] = best[0]['efficiency'] if best else 50
    
    # Get real estimates based on historical data
    estimates = get_campaign_estimates()
    
    # Get list of bars for targeting
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, borough FROM bars WHERE is_active = 1 ORDER BY borough, name')
    bars = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    # Define objectives
    objectives = [
        {'value': 'awareness', 'label': 'Brand Awareness', 'desc': 'Maximize impressions'},
        {'value': 'clicks', 'label': 'Drive Clicks', 'desc': 'Optimize for CTR'},
        {'value': 'engagement', 'label': 'Engagement', 'desc': 'Surveys & interactions'}
    ]
    
    return render_template('master/campaign_create.html',
                           advertiser=advertiser,
                           all_advertisers=all_advertisers,
                           placements=PLACEMENT_INFO,
                           suggested_questions=suggested_questions,
                           efficiency=efficiency,
                           objectives=objectives,
                           estimates=estimates,
                           bars=bars,
                           active_page='advertisers')


@master_bp.route('/campaign/create', methods=['POST'])
@admin_required
def create_campaign_full():
    """Handle campaign creation with placements and targeting."""
    import os
    import json
    
    # Get form data
    advertiser_id = request.form.get('advertiser_id', type=int)
    name = request.form.get('name', '').strip()
    objective = request.form.get('objective', 'awareness')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    budget = request.form.get('budget', type=float)
    click_url = request.form.get('click_url', '').strip()
    headline = request.form.get('headline', '').strip()
    cta_text = request.form.get('cta_text', '').strip()
    
    # Get targeting arrays
    target_bars = request.form.getlist('target_bars')
    target_placements = request.form.getlist('placements')
    
    # Validation
    errors = []
    if not advertiser_id:
        errors.append('Advertiser is required')
    if not name:
        errors.append('Campaign name is required')
    if start_date and end_date and start_date > end_date:
        errors.append('Start date must be before end date')
    if not target_bars:
        errors.append('Select at least one bar')
    if not target_placements:
        errors.append('Select at least one placement')
    if click_url and not (click_url.startswith('http://') or click_url.startswith('https://')):
        errors.append('Click URL must start with http:// or https://')
    
    if errors:
        for err in errors:
            flash(err, 'error')
        return redirect(request.referrer or url_for('master.advertisers'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Create campaign with new fields
        cursor.execute('''
            INSERT INTO campaigns (advertiser_id, name, objective, start_date, end_date, 
                                   budget, target_bars, target_placements, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')
        ''', (
            advertiser_id, 
            name, 
            objective, 
            start_date or None, 
            end_date or None,
            budget,
            json.dumps(target_bars) if target_bars else None,
            json.dumps(target_placements) if target_placements else None
        ))
        campaign_id = cursor.lastrowid
        
        # Handle creative file upload
        creative_file = request.files.get('creative')
        if creative_file and creative_file.filename:
            # Save file
            ads_folder = os.path.join(os.path.dirname(__file__), 'static', 'ads')
            os.makedirs(ads_folder, exist_ok=True)
            
            # Sanitize filename
            safe_filename = f"{advertiser_id}_{campaign_id}_{creative_file.filename}"
            filepath = os.path.join(ads_folder, safe_filename)
            creative_file.save(filepath)
            
            # Create creative record
            cursor.execute('''
                INSERT INTO ad_creatives (campaign_id, advertiser_id, file_name, click_url, headline, cta_text)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (campaign_id, advertiser_id, safe_filename, click_url or None, headline or None, cta_text or None))
        
        # Handle survey questions
        questions = request.form.getlist('questions')
        custom_question = request.form.get('custom_question', '').strip()
        if custom_question:
            questions.append(custom_question)
        
        for question in questions:
            if question.strip():
                cursor.execute('''
                    INSERT INTO advertiser_surveys (advertiser_id, campaign_id, question_text)
                    VALUES (?, ?, ?)
                ''', (advertiser_id, campaign_id, question.strip()))
        
        conn.commit()
        flash(f'Campaign "{name}" created successfully!', 'success')
        return redirect(url_for('master.advertiser_detail', advertiser_id=advertiser_id))
    
    except Exception as e:
        conn.rollback()
        flash(f'Error creating campaign: {str(e)}', 'error')
        return redirect(request.referrer or url_for('master.advertisers'))
    finally:
        conn.close()


@master_bp.route('/api/placement-efficiency/<placement>')
@admin_required
def api_placement_efficiency(placement):
    """Get efficiency data for a placement."""
    from .ad_scheduling import get_best_time_slots, get_time_slot_availability
    
    best_slots = get_best_time_slots(placement, 8)
    taken = get_time_slot_availability(placement)
    
    return jsonify({
        'success': True,
        'best_slots': best_slots,
        'taken_slots': [dict(s) for s in taken] if taken else []
    })


@master_bp.route('/campaign/cancel', methods=['POST'])
@admin_required
def cancel_campaign():
    """Cancel an active campaign."""
    campaign_id = request.form.get('campaign_id', type=int)
    advertiser_id = request.form.get('advertiser_id', type=int)
    
    if not campaign_id:
        flash('Campaign ID required', 'error')
        return redirect(url_for('master.advertisers'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Update campaign status
    cursor.execute('''
        UPDATE campaigns SET status = 'cancelled' WHERE id = ?
    ''', (campaign_id,))
    
    # Deactivate associated ad placements
    cursor.execute('''
        UPDATE ad_time_slots SET is_active = 0 WHERE campaign_id = ?
    ''', (campaign_id,))
    
    conn.commit()
    conn.close()
    
    flash('Campaign cancelled successfully', 'success')
    
    if advertiser_id:
        return redirect(url_for('master.advertiser_detail', advertiser_id=advertiser_id))
    return redirect(url_for('master.advertisers'))


@master_bp.route('/campaign/pause', methods=['POST'])
@admin_required
def pause_campaign():
    """Pause an active campaign (can be resumed later)."""
    campaign_id = request.form.get('campaign_id', type=int)
    advertiser_id = request.form.get('advertiser_id', type=int)
    
    if not campaign_id:
        flash('Campaign ID required', 'error')
        return redirect(url_for('master.advertisers'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT status FROM campaigns WHERE id = ?', (campaign_id,))
    row = cursor.fetchone()
    current_status = row['status'] if row else None
    
    # Toggle between paused and active
    if current_status == 'paused':
        new_status = 'active'
        msg = 'Campaign resumed'
    else:
        new_status = 'paused'
        msg = 'Campaign paused'
    
    cursor.execute('UPDATE campaigns SET status = ? WHERE id = ?', (new_status, campaign_id))
    conn.commit()
    conn.close()
    
    flash(msg, 'success')
    
    if advertiser_id:
        return redirect(url_for('master.advertiser_detail', advertiser_id=advertiser_id))
    return redirect(url_for('master.advertisers'))


@master_bp.route('/campaign/<int:campaign_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_campaign(campaign_id):
    """Edit an existing campaign."""
    import json
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get campaign
    cursor.execute('''
        SELECT c.*, a.name as advertiser_name 
        FROM campaigns c
        JOIN advertisers a ON a.id = c.advertiser_id
        WHERE c.id = ?
    ''', (campaign_id,))
    campaign = cursor.fetchone()
    
    if not campaign:
        conn.close()
        flash('Campaign not found', 'error')
        return redirect(url_for('master.advertisers'))
    
    campaign = dict(campaign)
    
    if request.method == 'POST':
        # Update campaign
        name = request.form.get('name', '').strip()
        start_date = request.form.get('start_date') or None
        end_date = request.form.get('end_date') or None
        budget = request.form.get('budget', type=float)
        target_bars = request.form.getlist('target_bars')
        target_placements = request.form.getlist('placements')
        
        cursor.execute('''
            UPDATE campaigns 
            SET name = ?, start_date = ?, end_date = ?, budget = ?,
                target_bars = ?, target_placements = ?
            WHERE id = ?
        ''', (
            name, start_date, end_date, budget,
            json.dumps(target_bars) if target_bars else None,
            json.dumps(target_placements) if target_placements else None,
            campaign_id
        ))
        
        conn.commit()
        conn.close()
        flash('Campaign updated successfully', 'success')
        return redirect(url_for('master.advertiser_detail', advertiser_id=campaign['advertiser_id']))
    
    # GET - show edit form
    cursor.execute('SELECT id, name, neighborhood FROM bars WHERE is_active = 1 ORDER BY name')
    bars = [dict(row) for row in cursor.fetchall()]
    
    # Get creatives for this campaign
    cursor.execute('SELECT * FROM ad_creatives WHERE campaign_id = ?', (campaign_id,))
    creatives = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    # Parse JSON fields
    try:
        campaign['target_bars_list'] = json.loads(campaign['target_bars']) if campaign.get('target_bars') else []
    except:
        campaign['target_bars_list'] = []
    
    try:
        campaign['target_placements_list'] = json.loads(campaign['target_placements']) if campaign.get('target_placements') else []
    except:
        campaign['target_placements_list'] = []
    
    from .ad_scheduling import PLACEMENT_INFO
    
    return render_template('master/campaign_edit.html',
                           campaign=campaign,
                           bars=bars,
                           creatives=creatives,
                           placements=PLACEMENT_INFO,
                           active_page='advertisers')



# ============ POS INTEGRATION MANAGEMENT ============

@master_bp.route('/bars/<int:bar_id>/integrations', methods=['GET'])
@admin_required
def bar_integrations(bar_id):
    """View and manage POS integrations for a bar."""
    print(f"[MASTER] Bar {bar_id} integrations page loaded")
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get bar info
    cursor.execute('SELECT * FROM bars WHERE id = ?', (bar_id,))
    bar = cursor.fetchone()
    if not bar:
        conn.close()
        return "Bar not found", 404
    bar = dict(bar)
    
    # Get existing credentials
    cursor.execute('''
        SELECT * FROM pos_credentials 
        WHERE bar_id = ? 
        ORDER BY updated_at DESC 
        LIMIT 1
    ''', (bar_id,))
    cred_row = cursor.fetchone()
    credentials = dict(cred_row) if cred_row else None
    
    conn.close()
    
    from .pos_connectors import PROVIDER_NAMES
    
    return render_template('master/bar_integrations.html',
                          bar=bar,
                          credentials=credentials,
                          providers=PROVIDER_NAMES,
                          active_page='bars')


@master_bp.route('/bars/<int:bar_id>/integrations', methods=['POST'])
@admin_required
def save_bar_integrations(bar_id):
    """Save POS integration settings for a bar."""
    print(f"[MASTER] Saving bar {bar_id} integrations")
    
    provider = request.form.get('pos_provider', '').strip() or None
    location_id = request.form.get('pos_location_id', '').strip() or None
    api_key = request.form.get('api_key', '').strip() or None
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Update bar
    if provider and location_id and api_key:
        # Set as active
        cursor.execute('''
            UPDATE bars SET 
                pos_provider = ?,
                pos_location_id = ?,
                pos_integration_status = 'active'
            WHERE id = ?
        ''', (provider, location_id, bar_id))
        
        # Upsert credentials
        cursor.execute('''
            INSERT INTO pos_credentials (bar_id, provider, access_token, created_at, updated_at)
            VALUES (?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(bar_id, provider) DO UPDATE SET
                access_token = excluded.access_token,
                updated_at = datetime('now')
        ''', (bar_id, provider, api_key))
        
        flash(f'{provider.title()} integration activated', 'success')
    else:
        # Clear integration
        cursor.execute('''
            UPDATE bars SET 
                pos_provider = NULL,
                pos_location_id = NULL,
                pos_integration_status = 'not_configured'
            WHERE id = ?
        ''', (bar_id,))
        flash('POS integration cleared', 'info')
    
    conn.commit()
    conn.close()
    
    return redirect(url_for('master.bar_integrations', bar_id=bar_id))


@master_bp.route('/bars/<int:bar_id>/sync_pos_test', methods=['POST'])
@admin_required
def sync_pos_test(bar_id):
    """Test POS sync for a bar (last 7 days)."""
    print(f"[MASTER] Testing POS sync for bar {bar_id}")
    
    from .services.pos_sync import sync_bar_pos
    
    result = sync_bar_pos(bar_id)
    
    return jsonify(result)



# ============================================
# AUTO-INVITE SETTINGS & ROUTES
# ============================================

@master_bp.route('/settings')
@admin_required
def master_settings():
    """Global app settings page."""
    from .database import get_setting, get_invite_stats, get_auto_invite_threshold
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get counts for system info
    cursor.execute('SELECT COUNT(*) as count FROM bars')
    bar_count = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM players WHERE is_active = 1 OR is_active IS NULL')
    player_count = cursor.fetchone()['count']
    
    conn.close()
    
    # Load all app settings
    settings = {
        'auto_invites_global_enabled': get_setting('auto_invites_global_enabled', '0') == '1',
        'auto_invite_threshold': get_auto_invite_threshold(),
        'display_refresh_ms': get_setting('display_refresh_ms', '2000'),
        'base_match_minutes': get_setting('base_match_minutes', '8'),
        'confirmation_timeout_sec': get_setting('confirmation_timeout_sec', '60'),
        'auto_join_on_qr': get_setting('auto_join_on_qr', '1'),
        'collect_guest_phone': get_setting('collect_guest_phone', '1'),
        'winner_tokens': get_setting('winner_tokens', '50'),
        'loser_tokens': get_setting('loser_tokens', '10'),
    }
    
    invite_stats = get_invite_stats()
    
    return render_template('master/settings.html',
                           settings=settings,
                           invite_stats=invite_stats,
                           bar_count=bar_count,
                           player_count=player_count,
                           active_page='settings')


@master_bp.route('/settings/update', methods=['POST'])
@admin_required
def update_setting():
    """Update a single app setting."""
    from .database import update_settings, set_setting
    
    key = request.form.get('key')
    value = request.form.get('value')
    
    if key and value is not None:
        # Settings that are columns in the main settings table
        settings_table_keys = ['display_refresh_ms', 'ad_rotation_seconds', 'base_match_minutes', 
                               'bar_name', 'table_name', 'address', 'city', 'state', 'zip_code',
                               'google_review_url', 'board_style', 'display_theme', 'permanent_rules']
        
        if key in settings_table_keys:
            # Convert to int for numeric fields
            if key in ['display_refresh_ms', 'ad_rotation_seconds', 'base_match_minutes', 'permanent_rules']:
                try:
                    value = int(value)
                except ValueError:
                    pass
            update_settings(**{key: value})
        else:
            # Other settings go to app_settings key-value table
            set_setting(key, value)
        
        flash(f'Setting updated', 'success')
    
    return redirect(url_for('master.master_settings'))


@master_bp.route('/settings/toggle', methods=['POST'])
@admin_required
def toggle_setting():
    """Toggle a boolean app setting."""
    from .database import get_setting, set_setting
    
    key = request.form.get('key')
    if key:
        current = get_setting(key, '1')
        new_value = '0' if current == '1' else '1'
        set_setting(key, new_value)
        flash(f'Setting toggled', 'success')
    
    return redirect(url_for('master.master_settings'))


@master_bp.route('/settings/clear-queues', methods=['POST'])
@admin_required
def clear_all_queues():
    """Clear all queue entries."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM queue')
    conn.commit()
    conn.close()
    flash('All queues cleared', 'success')
    return redirect(url_for('master.master_settings'))


@master_bp.route('/settings/reset-demo', methods=['POST'])
@admin_required
def reset_demo_data():
    """Reset demo/test data while preserving real accounts."""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # 1. Clear all queues
        cursor.execute('DELETE FROM queue')
        
        # 2. Clear ad events (test impressions/clicks)
        cursor.execute('DELETE FROM ad_events')
        
        # 3. Remove cancelled campaigns
        cursor.execute("DELETE FROM campaigns WHERE status = 'cancelled'")
        
        # 4. Remove inactive advertisers
        cursor.execute('DELETE FROM advertisers WHERE is_active = 0')
        
        # 5. Reset beta marketer credits
        cursor.execute("UPDATE marketer_accounts SET credits_balance = 100 WHERE contact_email LIKE '%beta%'")
        
        conn.commit()
        flash('Demo data reset successfully', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Error resetting demo data: {str(e)}', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('master.master_settings'))


@master_bp.route('/settings/wipe-players', methods=['POST'])
@admin_required
def wipe_all_players():
    """
    DANGER: Wipe all player accounts.
    
    This preserves:
    - Superadmin accounts (admin_accounts with is_superadmin = 1)
    - Admin accounts (admin_accounts table)
    - Bar manager accounts (bar_managers table)
    - Marketer accounts (marketer_accounts table)
    - Bars and their configuration
    - Advertisers and campaigns
    
    This deletes:
    - All players
    - All game history
    - All queues
    - All friend relationships
    - All challenges
    """
    confirm = request.form.get('confirm', '')
    if confirm != 'WIPE ALL PLAYERS':
        flash('You must type "WIPE ALL PLAYERS" to confirm', 'error')
        return redirect(url_for('master.master_settings'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Get count before deletion
        cursor.execute('SELECT COUNT(*) FROM players')
        player_count = cursor.fetchone()[0]
        
        # Delete related data first (foreign key safety)
        tables_to_clear = [
            'queue',
            'game_history', 
            'friendships',
            'challenges',
            'player_reports',
            'player_flags',
            'pool_night_rsvps',
            'token_transactions',
            'active_matches',
            'ranked_match_requests',
            'post_session_surveys',
            'phone_verification_codes'
        ]
        
        for table in tables_to_clear:
            try:
                cursor.execute(f'DELETE FROM {table}')
            except:
                pass  # Table might not exist
        
        # Delete all players
        cursor.execute('DELETE FROM players')
        
        conn.commit()
        flash(f'Wiped {player_count} player accounts. Admin accounts preserved.', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'Error wiping players: {str(e)}', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('master.master_settings'))


@master_bp.route('/settings/auto_invites', methods=['POST'])
@admin_required
def toggle_auto_invites_global():
    """Toggle global auto-invites setting."""
    from .database import get_setting, set_setting
    
    current = get_setting('auto_invites_global_enabled', '0')
    new_value = '0' if current == '1' else '1'
    set_setting('auto_invites_global_enabled', new_value)
    
    status = 'enabled' if new_value == '1' else 'disabled'
    flash(f'Auto-invites globally {status}', 'success')
    
    # Redirect back to auto-invites page (where settings now live)
    return redirect(url_for('master.auto_invites'))


@master_bp.route('/settings/auto_invite_threshold', methods=['POST'])
@admin_required
def set_auto_invite_threshold_route():
    """Update the auto-invite threshold setting."""
    from .database import set_auto_invite_threshold
    
    threshold = request.form.get('threshold', 3, type=int)
    
    # Validate range
    if threshold < 1:
        threshold = 1
    elif threshold > 30:
        threshold = 30
    
    set_auto_invite_threshold(threshold)
    
    flash(f'Auto-invite threshold updated to {threshold} days', 'success')
    # Redirect back to auto-invites page (where settings now live)
    return redirect(url_for('master.auto_invites'))


@master_bp.route('/bars/<int:bar_id>/auto_invites', methods=['POST'])
@admin_required
def toggle_bar_auto_invites(bar_id):
    """Toggle auto-invites for a specific bar."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT auto_invites_enabled FROM bars WHERE id = ?', (bar_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        flash('Bar not found', 'error')
        return redirect(url_for('master.bars'))
    
    current = row['auto_invites_enabled'] or 0
    new_value = 0 if current else 1
    
    cursor.execute('UPDATE bars SET auto_invites_enabled = ? WHERE id = ?', (new_value, bar_id))
    conn.commit()
    conn.close()
    
    status = 'enabled' if new_value else 'disabled'
    flash(f'Auto-invites {status} for this bar', 'success')
    
    # Redirect back to bar detail or integrations page
    return redirect(url_for('master.bar_detail', bar_id=bar_id))


@master_bp.route('/bars/<int:bar_id>/run_auto_invites', methods=['POST'])
@admin_required
def run_auto_invites(bar_id):
    """Manually run auto-invite pipeline for a bar (test endpoint)."""
    from .database import create_auto_invites_for_bar
    
    min_days = request.form.get('min_days', 3, type=int)
    result = create_auto_invites_for_bar(bar_id, min_days=min_days)
    
    return jsonify(result)


@master_bp.route('/invites')
@admin_required
def invites_list():
    """View all pending invites."""
    from .database import get_pending_invites, get_invite_stats
    
    bar_id = request.args.get('bar_id', type=int)
    invites = get_pending_invites(bar_id=bar_id)
    stats = get_invite_stats()
    
    # Get bars for filter dropdown
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM bars WHERE is_active = 1 ORDER BY name')
    bars = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return render_template('master/invites.html',
                           invites=invites,
                           stats=stats,
                           bars=bars,
                           selected_bar_id=bar_id,
                           active_page='invites')


@master_bp.route('/auto-invites')
@admin_required
def auto_invites_dashboard():
    """Dedicated Auto-Invites dashboard with comprehensive analytics."""
    from .database import get_comprehensive_auto_invite_analytics
    
    analytics = get_comprehensive_auto_invite_analytics()
    
    return render_template('master/auto_invites.html',
                           analytics=analytics,
                           active_page='auto_invites')


# =============================================================================
# CAMPAIGN APPROVAL (Admin)
# =============================================================================

@master_bp.route('/campaigns/pending')
@admin_required
def pending_campaigns():
    """View campaigns pending approval."""
    from .marketer_system import get_pending_campaigns
    
    campaigns = get_pending_campaigns()
    
    return render_template('master/pending_campaigns.html',
                           campaigns=campaigns,
                           active_page='advertisers')


@master_bp.route('/campaign/<int:campaign_id>/approve', methods=['POST'])
@admin_required
def approve_campaign(campaign_id):
    """Approve a pending campaign."""
    from .marketer_system import approve_campaign as do_approve
    
    reviewer = session.get('admin_name', 'Admin')
    success = do_approve(campaign_id, reviewer)
    
    if success:
        flash('Campaign approved and activated!', 'success')
    else:
        flash('Could not approve campaign', 'error')
    
    return redirect(url_for('master.pending_campaigns'))


@master_bp.route('/campaign/<int:campaign_id>/reject', methods=['POST'])
@admin_required
def reject_campaign(campaign_id):
    """Reject a pending campaign."""
    from .marketer_system import reject_campaign as do_reject
    
    reviewer = session.get('admin_name', 'Admin')
    reason = request.form.get('reason', 'Did not meet guidelines')
    
    success = do_reject(campaign_id, reviewer, reason)
    
    if success:
        flash('Campaign rejected', 'warning')
    else:
        flash('Could not reject campaign', 'error')
    
    return redirect(url_for('master.pending_campaigns'))



# =============================================================================
# REPORT MANAGEMENT API
# =============================================================================

@master_bp.route('/api/resolve-report', methods=['POST'])
@admin_required
def api_resolve_report():
    """Resolve a player report."""
    data = request.json or {}
    report_id = data.get('report_id')
    status = data.get('status', 'resolved')
    action_taken = data.get('action_taken', 'no_action')
    
    if not report_id:
        return jsonify({'error': 'report_id required'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE player_reports 
        SET status = ?, action_taken = ?, resolved_at = CURRENT_TIMESTAMP 
        WHERE id = ?
    ''', (status, action_taken, report_id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})


@master_bp.route('/api/warn-player', methods=['POST'])
@admin_required
def api_warn_player():
    """Send a warning to a player."""
    data = request.json or {}
    player_id = data.get('player_id')
    message = data.get('message', 'Please follow community guidelines')
    report_id = data.get('report_id')
    
    if not player_id:
        return jsonify({'error': 'player_id required'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Add warning flag
    cursor.execute('''
        INSERT INTO player_flags (player_id, flag_type, reason, created_at)
        VALUES (?, 'warning', ?, CURRENT_TIMESTAMP)
    ''', (player_id, message))
    
    # Resolve report if provided
    if report_id:
        cursor.execute('''
            UPDATE player_reports 
            SET status = 'resolved', action_taken = 'warned', resolved_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (report_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})


@master_bp.route('/api/suspend-player', methods=['POST'])
@admin_required
def api_suspend_player():
    """Suspend a player for a specified number of days."""
    data = request.json or {}
    player_id = data.get('player_id')
    days = data.get('days', 7)
    reason = data.get('reason', 'Violation of community guidelines')
    report_id = data.get('report_id')
    
    if not player_id:
        return jsonify({'error': 'player_id required'}), 400
    
    from datetime import datetime, timedelta
    banned_until = datetime.now() + timedelta(days=days)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Add ban flag with expiration
    cursor.execute('''
        INSERT OR REPLACE INTO player_flags (player_id, flag_type, reason, banned_until, created_at)
        VALUES (?, 'suspended', ?, ?, CURRENT_TIMESTAMP)
    ''', (player_id, reason, banned_until.isoformat()))
    
    # Remove from queue
    cursor.execute('DELETE FROM queue WHERE player_id = ?', (player_id,))
    
    # Resolve report if provided
    if report_id:
        cursor.execute('''
            UPDATE player_reports 
            SET status = 'resolved', action_taken = ?, resolved_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (f'suspended_{days}_days', report_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})


@master_bp.route('/api/ban-player', methods=['POST'])
@admin_required
def api_ban_player():
    """Permanently ban a player."""
    data = request.json or {}
    player_id = data.get('player_id')
    reason = data.get('reason', 'Severe violation of community guidelines')
    report_id = data.get('report_id')
    
    if not player_id:
        return jsonify({'error': 'player_id required'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Add permanent ban flag
    cursor.execute('''
        INSERT OR REPLACE INTO player_flags (player_id, flag_type, reason, banned_until, created_at)
        VALUES (?, 'banned', ?, NULL, CURRENT_TIMESTAMP)
    ''', (player_id, reason))
    
    # Remove from queue
    cursor.execute('DELETE FROM queue WHERE player_id = ?', (player_id,))
    
    # Resolve report if provided
    if report_id:
        cursor.execute('''
            UPDATE player_reports 
            SET status = 'resolved', action_taken = 'banned', resolved_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (report_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})


@master_bp.route('/api/remove-from-queue', methods=['POST'])
@admin_required
def api_remove_from_queue():
    """Remove a player from the queue."""
    data = request.json or {}
    player_id = data.get('player_id')
    
    if not player_id:
        return jsonify({'error': 'player_id required'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM queue WHERE player_id = ?', (player_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})
