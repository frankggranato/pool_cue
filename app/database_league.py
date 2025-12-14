"""
Database extensions for League System - Phase 1
Ranked/Casual, ELO, Divisions, Seasons, Reports
"""
from .database import get_db
from datetime import datetime, date

def init_league_db():
    """Initialize league system tables."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Extend players table with rating fields
    try:
        cursor.execute('ALTER TABLE players ADD COLUMN rating INTEGER DEFAULT 1000')
    except: pass
    try:
        cursor.execute('ALTER TABLE players ADD COLUMN division TEXT DEFAULT "Bronze"')
    except: pass
    try:
        cursor.execute('ALTER TABLE players ADD COLUMN ranked_wins INTEGER DEFAULT 0')
    except: pass
    try:
        cursor.execute('ALTER TABLE players ADD COLUMN ranked_losses INTEGER DEFAULT 0')
    except: pass
    try:
        cursor.execute('ALTER TABLE players ADD COLUMN is_ranked_player INTEGER DEFAULT 0')
    except: pass
    
    # Extend game_history with mode
    try:
        cursor.execute('ALTER TABLE game_history ADD COLUMN mode TEXT DEFAULT "casual"')
    except: pass
    try:
        cursor.execute('ALTER TABLE game_history ADD COLUMN season_id INTEGER')
    except: pass
    try:
        cursor.execute('ALTER TABLE game_history ADD COLUMN rating_change INTEGER DEFAULT 0')
    except: pass
    
    # Seasons table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS seasons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Season standings
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS season_standings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_id INTEGER,
            player_id INTEGER,
            bar_id INTEGER DEFAULT 1,
            games_played INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            rating INTEGER DEFAULT 1000,
            division TEXT DEFAULT 'Bronze',
            last_updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (season_id) REFERENCES seasons(id),
            FOREIGN KEY (player_id) REFERENCES players(id),
            UNIQUE(season_id, player_id, bar_id)
        )
    ''')
    
    # Player reports (for reporting cheaters/gamers)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reported_player_id INTEGER,
            reporter_player_id INTEGER,
            reason TEXT,
            details TEXT,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            resolved_at DATETIME,
            resolved_by TEXT,
            action_taken TEXT,
            FOREIGN KEY (reported_player_id) REFERENCES players(id),
            FOREIGN KEY (reporter_player_id) REFERENCES players(id)
        )
    ''')
    
    # Banned/flagged players
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_flags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER UNIQUE,
            flag_type TEXT DEFAULT 'warning',
            reason TEXT,
            banned_until DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    ''')
    
    # Ensure current season exists
    cursor.execute('SELECT COUNT(*) FROM seasons WHERE is_active = 1')
    if cursor.fetchone()[0] == 0:
        today = date.today()
        # Create monthly season
        month_name = today.strftime('%B %Y')
        start = today.replace(day=1)
        if today.month == 12:
            end = today.replace(year=today.year + 1, month=1, day=1)
        else:
            end = today.replace(month=today.month + 1, day=1)
        cursor.execute('''INSERT INTO seasons (name, start_date, end_date, is_active)
                          VALUES (?, ?, ?, 1)''', (month_name, start, end))
    
    conn.commit()
    conn.close()

def get_current_season():
    """Get the current active season."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM seasons WHERE is_active = 1 ORDER BY id DESC LIMIT 1')
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def get_division(rating):
    """Get division name from rating."""
    if rating >= 1700:
        return 'Diamond'
    elif rating >= 1500:
        return 'Platinum'
    elif rating >= 1300:
        return 'Gold'
    elif rating >= 1100:
        return 'Silver'
    return 'Bronze'

def get_division_emoji(division):
    """Get emoji for division."""
    return {
        'Bronze': '🥉',
        'Silver': '🥈', 
        'Gold': '🥇',
        'Platinum': '💎',
        'Diamond': '👑'
    }.get(division, '🎱')


def calculate_elo_change(winner_rating, loser_rating):
    """Calculate ELO rating change. Returns (winner_gain, loser_loss)."""
    diff = loser_rating - winner_rating
    
    # K-factor based on rating difference
    if diff >= 200:  # Big upset
        k = 16
    elif diff >= 100:  # Moderate upset
        k = 12
    elif diff >= 0:  # Expected or close
        k = 10
    else:  # Favorite won
        k = 8
    
    return k, k

def update_ratings_after_match(winner_id, loser_id, bar_id=1):
    """Update ratings after a ranked match."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get current ratings
    cursor.execute('SELECT rating FROM players WHERE id = ?', (winner_id,))
    winner_row = cursor.fetchone()
    cursor.execute('SELECT rating FROM players WHERE id = ?', (loser_id,))
    loser_row = cursor.fetchone()
    
    if not winner_row or not loser_row:
        conn.close()
        return None
    
    winner_rating = winner_row['rating'] or 1000
    loser_rating = loser_row['rating'] or 1000
    
    # Calculate change
    gain, loss = calculate_elo_change(winner_rating, loser_rating)
    
    new_winner_rating = winner_rating + gain
    new_loser_rating = max(loser_rating - loss, 100)  # Floor at 100
    
    # Update players
    winner_div = get_division(new_winner_rating)
    loser_div = get_division(new_loser_rating)
    
    cursor.execute('''UPDATE players SET 
                      rating = ?, division = ?, ranked_wins = ranked_wins + 1, is_ranked_player = 1
                      WHERE id = ?''', (new_winner_rating, winner_div, winner_id))
    cursor.execute('''UPDATE players SET
                      rating = ?, division = ?, ranked_losses = ranked_losses + 1, is_ranked_player = 1
                      WHERE id = ?''', (new_loser_rating, loser_div, loser_id))
    
    # Update season standings
    season = get_current_season()
    if season:
        for player_id, won in [(winner_id, True), (loser_id, False)]:
            cursor.execute('''SELECT id FROM season_standings 
                              WHERE season_id = ? AND player_id = ?''', (season['id'], player_id))
            if cursor.fetchone():
                if won:
                    cursor.execute('''UPDATE season_standings SET 
                                      games_played = games_played + 1, wins = wins + 1,
                                      rating = rating + ?, last_updated_at = CURRENT_TIMESTAMP
                                      WHERE season_id = ? AND player_id = ?''', 
                                   (gain, season['id'], player_id))
                else:
                    cursor.execute('''UPDATE season_standings SET
                                      games_played = games_played + 1, losses = losses + 1,
                                      rating = MAX(rating - ?, 100), last_updated_at = CURRENT_TIMESTAMP
                                      WHERE season_id = ? AND player_id = ?''',
                                   (loss, season['id'], player_id))
            else:
                rating = 1000 + gain if won else 1000 - loss
                cursor.execute('''INSERT INTO season_standings 
                                  (season_id, player_id, bar_id, games_played, wins, losses, rating, division)
                                  VALUES (?, ?, ?, 1, ?, ?, ?, ?)''',
                               (season['id'], player_id, bar_id, 1 if won else 0, 0 if won else 1, 
                                rating, get_division(rating)))
    
    conn.commit()
    conn.close()
    
    return {
        'winner_gain': gain,
        'loser_loss': loss,
        'winner_new_rating': new_winner_rating,
        'loser_new_rating': new_loser_rating,
        'winner_division': winner_div,
        'loser_division': loser_div
    }

def get_leaderboard(limit=50, bar_id=None, season_only=True):
    """Get ranked leaderboard."""
    conn = get_db()
    cursor = conn.cursor()
    
    season = get_current_season()
    
    if season_only and season:
        cursor.execute('''
            SELECT p.id, p.nickname, ss.rating, ss.wins, ss.losses, ss.games_played,
                   p.division, p.account_id
            FROM season_standings ss
            JOIN players p ON ss.player_id = p.id
            WHERE ss.season_id = ? AND ss.games_played >= 3 AND (p.is_active = 1 OR p.is_active IS NULL)
            ORDER BY ss.rating DESC
            LIMIT ?
        ''', (season['id'], limit))
    else:
        cursor.execute('''
            SELECT id, nickname, rating, ranked_wins as wins, ranked_losses as losses,
                   (ranked_wins + ranked_losses) as games_played, division, account_id
            FROM players
            WHERE is_ranked_player = 1 AND (ranked_wins + ranked_losses) >= 3 AND (is_active = 1 OR is_active IS NULL)
            ORDER BY rating DESC
            LIMIT ?
        ''', (limit,))
    
    players = []
    for i, row in enumerate(cursor.fetchall(), 1):
        players.append({
            'rank': i,
            'id': row['id'],
            'nickname': row['nickname'],
            'rating': row['rating'],
            'wins': row['wins'],
            'losses': row['losses'],
            'games': row['games_played'],
            'division': row['division'],
            'division_emoji': get_division_emoji(row['division']),
            'account_id': row['account_id'],
            'is_guest': row['account_id'] is None
        })
    
    conn.close()
    return players

def report_player(reported_id, reporter_id, reason, details=''):
    """Report a player for cheating/gaming the system."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO player_reports 
                      (reported_player_id, reporter_player_id, reason, details)
                      VALUES (?, ?, ?, ?)''',
                   (reported_id, reporter_id, reason, details))
    conn.commit()
    report_id = cursor.lastrowid
    conn.close()
    return report_id

def get_pending_reports():
    """Get all pending player reports."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT pr.*, 
               rp.nickname as reported_name, rp.rating as reported_rating,
               rep.nickname as reporter_name
        FROM player_reports pr
        JOIN players rp ON pr.reported_player_id = rp.id
        LEFT JOIN players rep ON pr.reporter_player_id = rep.id
        WHERE pr.status = 'pending'
        ORDER BY pr.created_at DESC
    ''')
    reports = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return reports

def ban_player(player_id, reason, days=None):
    """Ban or flag a player."""
    conn = get_db()
    cursor = conn.cursor()
    
    banned_until = None
    if days:
        from datetime import timedelta
        banned_until = datetime.now() + timedelta(days=days)
    
    cursor.execute('''INSERT OR REPLACE INTO player_flags 
                      (player_id, flag_type, reason, banned_until)
                      VALUES (?, 'banned', ?, ?)''',
                   (player_id, reason, banned_until))
    conn.commit()
    conn.close()

def get_all_players_ranked(include_inactive=False):
    """Get all players with accurate stats from game_history."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Build WHERE clause based on include_inactive
    # False = only active, True = only inactive
    if include_inactive:
        active_filter = "WHERE p.is_active = 0"
    else:
        active_filter = "WHERE (p.is_active = 1 OR p.is_active IS NULL)"
    
    # Get all players (not just ranked) with calculated stats from game_history
    # Include password_hash for account status determination
    cursor.execute(f'''
        SELECT p.*, p.password_hash,
               pf.flag_type, pf.reason as flag_reason, pf.banned_until,
               (SELECT COUNT(*) FROM player_reports WHERE reported_player_id = p.id AND status = 'pending') as pending_reports,
               COALESCE((SELECT COUNT(*) FROM game_history WHERE winner_id = p.id), 0) as calc_wins,
               COALESCE((SELECT COUNT(*) FROM game_history WHERE loser_id = p.id), 0) as calc_losses,
               COALESCE((SELECT COUNT(*) FROM game_history WHERE winner_id = p.id OR loser_id = p.id), 0) as games_played,
               b.name as home_bar
        FROM players p
        LEFT JOIN player_flags pf ON p.id = pf.player_id
        LEFT JOIN bars b ON p.home_bar_id = b.id
        {active_filter}
        ORDER BY 
            CASE WHEN p.phone_verified = 1 THEN 0 WHEN p.account_id IS NOT NULL THEN 1 ELSE 2 END,
            COALESCE((SELECT COUNT(*) FROM game_history WHERE winner_id = p.id), 0) DESC,
            p.rating DESC
    ''')
    
    players = []
    for row in cursor.fetchall():
        player = dict(row)
        player['is_guest'] = player.get('account_id') is None
        
        # Use calculated stats from game_history as source of truth
        player['wins'] = player.get('calc_wins', 0) or 0
        player['losses'] = player.get('calc_losses', 0) or 0
        player['games_played'] = player.get('games_played', 0) or 0
        
        # Calculate win rate
        total = player['wins'] + player['losses']
        player['win_rate'] = round((player['wins'] / total * 100) if total > 0 else 0)
        
        players.append(player)
    
    conn.close()
    return players


def calculate_elo_change(winner_rating, loser_rating):
    """Calculate ELO rating change. Returns (winner_gain, loser_loss)."""
    diff = loser_rating - winner_rating
    
    if diff >= 200:  # Big upset
        k = 16
    elif diff >= 100:  # Moderate upset
        k = 12
    elif diff >= 0:  # Expected or close
        k = 10
    else:  # Favorite won
        k = 8
    
    return k, k

def update_ratings_after_match(winner_id, loser_id, bar_id=1):
    """Update ratings after a ranked match."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT rating FROM players WHERE id = ?', (winner_id,))
    winner_row = cursor.fetchone()
    cursor.execute('SELECT rating FROM players WHERE id = ?', (loser_id,))
    loser_row = cursor.fetchone()
    
    if not winner_row or not loser_row:
        conn.close()
        return None
    
    winner_rating = winner_row['rating'] or 1000
    loser_rating = loser_row['rating'] or 1000
    
    gain, loss = calculate_elo_change(winner_rating, loser_rating)
    
    new_winner_rating = winner_rating + gain
    new_loser_rating = max(loser_rating - loss, 100)
    
    winner_div = get_division(new_winner_rating)
    loser_div = get_division(new_loser_rating)
    
    cursor.execute('''UPDATE players SET 
                      rating = ?, division = ?, ranked_wins = ranked_wins + 1, is_ranked_player = 1
                      WHERE id = ?''', (new_winner_rating, winner_div, winner_id))
    cursor.execute('''UPDATE players SET
                      rating = ?, division = ?, ranked_losses = ranked_losses + 1, is_ranked_player = 1
                      WHERE id = ?''', (new_loser_rating, loser_div, loser_id))
    
    conn.commit()
    conn.close()
    
    return {'winner_gain': gain, 'loser_loss': loss, 'winner_new_rating': new_winner_rating,
            'loser_new_rating': new_loser_rating, 'winner_division': winner_div, 'loser_division': loser_div}

def get_leaderboard(limit=50):
    """Get ranked leaderboard."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, nickname, rating, ranked_wins as wins, ranked_losses as losses,
               (ranked_wins + ranked_losses) as games_played, division
        FROM players WHERE is_ranked_player = 1 AND (ranked_wins + ranked_losses) >= 3 AND (is_active = 1 OR is_active IS NULL)
        ORDER BY rating DESC LIMIT ?
    ''', (limit,))
    
    players = []
    for i, row in enumerate(cursor.fetchall(), 1):
        players.append({
            'rank': i, 'id': row['id'], 'nickname': row['nickname'], 'rating': row['rating'],
            'wins': row['wins'], 'losses': row['losses'], 'games': row['games_played'],
            'division': row['division'], 'division_emoji': get_division_emoji(row['division'])
        })
    conn.close()
    return players

def report_player(reported_id, reporter_id, reason, details=''):
    """Report a player for cheating."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO player_reports (reported_player_id, reporter_player_id, reason, details)
                      VALUES (?, ?, ?, ?)''', (reported_id, reporter_id, reason, details))
    conn.commit()
    conn.close()

def get_pending_reports():
    """Get all pending player reports with player stats."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT pr.*, 
               rp.nickname as reported_player, 
               rp.total_games as games_played,
               rep.nickname as reporter,
               (SELECT COUNT(*) FROM player_reports pr2 WHERE pr2.reported_player_id = pr.reported_player_id) as total_reports
        FROM player_reports pr
        JOIN players rp ON pr.reported_player_id = rp.id
        LEFT JOIN players rep ON pr.reporter_id = rep.id
        WHERE pr.status = 'pending' 
        ORDER BY pr.created_at DESC
    ''')
    reports = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return reports

def ban_player(player_id, reason, days=None):
    """Ban or flag a player."""
    conn = get_db()
    cursor = conn.cursor()
    banned_until = None
    if days:
        from datetime import timedelta
        banned_until = datetime.now() + timedelta(days=days)
    cursor.execute('INSERT OR REPLACE INTO player_flags (player_id, flag_type, reason, banned_until) VALUES (?, "banned", ?, ?)',
                   (player_id, reason, banned_until))
    conn.commit()
    conn.close()

# Note: get_all_players_ranked() is defined earlier in this file with full game_history stats

def get_master_stats():
    """Get stats for master dashboard."""
    conn = get_db()
    cursor = conn.cursor()
    
    stats = {}
    
    # Total players
    cursor.execute('SELECT COUNT(*) FROM players')
    stats['total_players'] = cursor.fetchone()[0]
    
    # Ranked players
    cursor.execute('SELECT COUNT(*) FROM players WHERE is_ranked_player = 1')
    stats['ranked_players'] = cursor.fetchone()[0]
    
    # Total games
    cursor.execute('SELECT COUNT(*) FROM game_history')
    stats['total_games'] = cursor.fetchone()[0]
    
    # Games today
    cursor.execute("SELECT COUNT(*) FROM game_history WHERE date(played_at) = date('now')")
    stats['games_today'] = cursor.fetchone()[0]
    
    # Pending reports
    cursor.execute("SELECT COUNT(*) FROM player_reports WHERE status = 'pending'")
    stats['pending_reports'] = cursor.fetchone()[0]
    
    # Banned players
    cursor.execute("SELECT COUNT(*) FROM player_flags WHERE flag_type = 'banned'")
    stats['banned_players'] = cursor.fetchone()[0]
    
    # Division breakdown
    cursor.execute('''SELECT division, COUNT(*) as count FROM players 
                      WHERE is_ranked_player = 1 GROUP BY division''')
    stats['divisions'] = {row['division']: row['count'] for row in cursor.fetchall()}
    
    # Active bars
    cursor.execute('SELECT COUNT(*) FROM bars WHERE is_active = 1')
    stats['active_bars'] = cursor.fetchone()[0]
    
    # Active campaigns
    try:
        cursor.execute("SELECT COUNT(*) FROM campaigns WHERE status = 'active' AND end_date >= date('now')")
        stats['active_campaigns'] = cursor.fetchone()[0]
    except:
        stats['active_campaigns'] = 0
    
    conn.close()
    return stats


def sync_player_stats_with_game_history():
    """
    Sync players table wins/losses/total_games with actual game_history records.
    This is the source of truth fix - updates cached columns to match reality.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Update all players' wins based on game_history
    cursor.execute('''
        UPDATE players SET wins = (
            SELECT COUNT(*) FROM game_history WHERE winner_id = players.id
        )
    ''')
    
    # Update all players' losses based on game_history
    cursor.execute('''
        UPDATE players SET losses = (
            SELECT COUNT(*) FROM game_history WHERE loser_id = players.id
        )
    ''')
    
    # Update total_games
    cursor.execute('''
        UPDATE players SET total_games = (
            SELECT COUNT(*) FROM game_history 
            WHERE winner_id = players.id OR loser_id = players.id
        )
    ''')
    
    conn.commit()
    conn.close()
    print("[SYNC] Player stats synchronized with game_history")
