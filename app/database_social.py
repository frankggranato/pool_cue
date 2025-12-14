"""
Social features - Tokens, notifications, friends
"""
from .database import get_db

# Token rewards
TOKENS_WIN = 50      # Tokens for winning
TOKENS_LOSE = 10     # Tokens for playing (even if lost)
TOKENS_SIGNUP = 0    # Start with 0 tokens
TOKENS_SURVEY = 25   # Tokens for completing survey

def init_social_db():
    """Initialize social feature tables."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Token transactions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS token_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER,
            amount INTEGER,
            reason TEXT,
            details TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Notifications table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER,
            type TEXT,
            title TEXT,
            message TEXT,
            data TEXT,
            read INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Friendships table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS friendships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER,
            friend_id INTEGER,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(player_id, friend_id)
        )
    ''')
    
    # Challenges table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_player_id INTEGER,
            to_player_id INTEGER,
            bar_id INTEGER,
            status TEXT DEFAULT 'pending',
            message TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

# Stub functions for missing imports
def award_tokens(player_id, amount, reason='manual'):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE players SET tokens_balance = COALESCE(tokens_balance, 0) + ? WHERE id = ?', (amount, player_id))
    cursor.execute('INSERT INTO token_transactions (player_id, amount, reason) VALUES (?, ?, ?)', (player_id, amount, reason))
    conn.commit()
    conn.close()

def deduct_tokens(player_id, amount, reason='purchase'):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE players SET tokens_balance = COALESCE(tokens_balance, 0) - ? WHERE id = ?', (amount, player_id))
    cursor.execute('INSERT INTO token_transactions (player_id, amount, reason) VALUES (?, ?, ?)', (player_id, -amount, reason))
    conn.commit()
    conn.close()

def get_token_balance(player_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT COALESCE(tokens_balance, 0) FROM players WHERE id = ?', (player_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

def get_token_history(player_id, limit=20):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM token_transactions WHERE player_id = ? ORDER BY created_at DESC LIMIT ?', (player_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def claim_daily_bonus(player_id):
    award_tokens(player_id, 10, 'daily_bonus')
    return {'success': True, 'amount': 10}

def send_friend_request(from_id, to_id):
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if target player has an account (not a guest)
    cursor.execute('SELECT account_id FROM players WHERE id = ?', (to_id,))
    target = cursor.fetchone()
    if not target or not target['account_id']:
        conn.close()
        return False, 'This player doesn\'t have an account yet'
    
    # Check if already friends or pending
    cursor.execute('''
        SELECT status FROM friendships 
        WHERE (player_id = ? AND friend_id = ?) OR (player_id = ? AND friend_id = ?)
    ''', (from_id, to_id, to_id, from_id))
    existing = cursor.fetchone()
    
    if existing:
        if existing['status'] == 'accepted':
            conn.close()
            return False, 'Already friends'
        else:
            conn.close()
            return False, 'Request already pending'
    
    cursor.execute('INSERT INTO friendships (player_id, friend_id, status, created_at) VALUES (?, ?, ?, datetime("now"))', 
                   (from_id, to_id, 'pending'))
    conn.commit()
    conn.close()
    return True, 'Friend request sent'

def accept_friend_request(player_id, friend_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE friendships SET status = ? WHERE player_id = ? AND friend_id = ?', ('accepted', friend_id, player_id))
    cursor.execute('INSERT OR REPLACE INTO friendships (player_id, friend_id, status, created_at) VALUES (?, ?, ?, datetime("now"))', (player_id, friend_id, 'accepted'))
    conn.commit()
    conn.close()
    return True, 'Friend added'

def decline_friend_request(player_id, friend_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM friendships WHERE player_id = ? AND friend_id = ?', (friend_id, player_id))
    conn.commit()
    conn.close()
    return True, 'Request declined'

def get_friends(player_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.* FROM players p
        JOIN friendships f ON p.id = f.friend_id
        WHERE f.player_id = ? AND f.status = 'accepted'
    ''', (player_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_friend_requests(player_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.*, f.created_at as request_date FROM players p
        JOIN friendships f ON p.id = f.player_id
        WHERE f.friend_id = ? AND f.status = 'pending'
    ''', (player_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def search_players(query):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, nickname FROM players WHERE nickname LIKE ? AND (is_active = 1 OR is_active IS NULL) LIMIT 20', (f'%{query}%',))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def send_challenge(from_id, to_id, bar_id=None, message=None, stakes=0, scheduled_datetime=None, location=None):
    conn = get_db()
    cursor = conn.cursor()
    
    # Ensure stakes is an integer
    stakes = int(stakes) if stakes else 0
    
    # Check if target player has an account (not a guest)
    cursor.execute('SELECT account_id FROM players WHERE id = ?', (to_id,))
    target = cursor.fetchone()
    if not target or not target['account_id']:
        conn.close()
        return False, 'This player doesn\'t have an account yet'
    
    # Validate stakes if wagering tokens
    if stakes > 0:
        # Check challenger's balance
        cursor.execute('SELECT tokens_balance FROM players WHERE id = ?', (from_id,))
        challenger_balance = cursor.fetchone()
        if not challenger_balance or (challenger_balance[0] or 0) < stakes:
            conn.close()
            return False, 'You don\'t have enough tokens to wager'
        
        # Check opponent's balance
        cursor.execute('SELECT tokens_balance FROM players WHERE id = ?', (to_id,))
        opponent_balance = cursor.fetchone()
        if not opponent_balance or (opponent_balance[0] or 0) < stakes:
            conn.close()
            return False, 'Opponent doesn\'t have enough tokens to match your wager'
    
    # Check if there's already a pending challenge between these players
    cursor.execute('''
        SELECT id FROM challenges 
        WHERE challenger_user_id = ? AND challenged_user_id = ? AND status = 'pending'
    ''', (from_id, to_id))
    existing = cursor.fetchone()
    
    if existing:
        conn.close()
        return False, 'Challenge already pending'
    
    cursor.execute('''
        INSERT INTO challenges (challenger_user_id, challenged_user_id, bar_id, message, tokens_wagered, scheduled_datetime, location, status, created_at) 
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', datetime('now'))
    ''', (from_id, to_id, bar_id, message, stakes or 0, scheduled_datetime, location))
    challenge_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return True, challenge_id

def accept_challenge(challenge_id, player_id=None):
    conn = get_db()
    cursor = conn.cursor()
    
    # Get challenge details first
    cursor.execute('SELECT * FROM challenges WHERE id = ? AND status = ?', (challenge_id, 'pending'))
    challenge = cursor.fetchone()
    
    if not challenge:
        conn.close()
        return False, 'Challenge not found or already responded'
    
    challenge = dict(challenge)
    
    # Verify the player is the challenged one
    if player_id and challenge['challenged_user_id'] != player_id:
        conn.close()
        return False, 'You cannot accept this challenge'
    
    # Re-validate tokens if there's a wager
    tokens_wagered = challenge.get('tokens_wagered', 0) or 0
    if tokens_wagered > 0:
        # Check challenger still has enough
        cursor.execute('SELECT tokens_balance FROM players WHERE id = ?', (challenge['challenger_user_id'],))
        challenger_balance = cursor.fetchone()
        if not challenger_balance or (challenger_balance[0] or 0) < tokens_wagered:
            conn.close()
            return False, 'Challenger no longer has enough tokens'
        
        # Check challenged (you) still has enough
        cursor.execute('SELECT tokens_balance FROM players WHERE id = ?', (challenge['challenged_user_id'],))
        challenged_balance = cursor.fetchone()
        if not challenged_balance or (challenged_balance[0] or 0) < tokens_wagered:
            conn.close()
            return False, 'You don\'t have enough tokens to match the wager'
    
    cursor.execute('UPDATE challenges SET status = ?, responded_at = datetime("now") WHERE id = ?', ('accepted', challenge_id))
    conn.commit()
    conn.close()
    return True, 'Challenge accepted'

def decline_challenge(challenge_id, player_id=None):
    conn = get_db()
    cursor = conn.cursor()
    
    # Verify the player is the challenged one
    if player_id:
        cursor.execute('SELECT * FROM challenges WHERE id = ? AND challenged_user_id = ? AND status = ?',
                       (challenge_id, player_id, 'pending'))
        if not cursor.fetchone():
            conn.close()
            return False, 'Challenge not found or already responded'
    
    cursor.execute('UPDATE challenges SET status = ?, responded_at = datetime("now") WHERE id = ?', ('declined', challenge_id))
    conn.commit()
    conn.close()
    return True, 'Challenge declined'

def complete_challenge(challenge_id, winner_id):
    conn = get_db()
    cursor = conn.cursor()
    
    # Get challenge details
    cursor.execute('SELECT * FROM challenges WHERE id = ? AND status = ?', (challenge_id, 'accepted'))
    challenge = cursor.fetchone()
    
    if not challenge:
        conn.close()
        return {'success': False, 'error': 'Challenge not found or not active'}
    
    challenge = dict(challenge)
    challenger_id = challenge['challenger_user_id']
    challenged_id = challenge['challenged_user_id']
    tokens_wagered = challenge.get('tokens_wagered', 0) or 0
    
    # Verify winner is a participant
    if winner_id not in [challenger_id, challenged_id]:
        conn.close()
        return {'success': False, 'error': 'Invalid winner'}
    
    loser_id = challenged_id if winner_id == challenger_id else challenger_id
    
    # Transfer tokens if wagered
    if tokens_wagered > 0:
        # Deduct from loser
        cursor.execute('''
            UPDATE players SET tokens_balance = COALESCE(tokens_balance, 0) - ? WHERE id = ?
        ''', (tokens_wagered, loser_id))
        
        # Award to winner (wagered amount + base win bonus)
        total_award = tokens_wagered + 25  # 25 token bonus for winning challenge
        cursor.execute('''
            UPDATE players SET 
                tokens_balance = COALESCE(tokens_balance, 0) + ?,
                total_tokens_earned = COALESCE(total_tokens_earned, 0) + ?
            WHERE id = ?
        ''', (total_award, total_award, winner_id))
    else:
        # Award base tokens for completing challenge (no wager)
        cursor.execute('''
            UPDATE players SET 
                tokens_balance = COALESCE(tokens_balance, 0) + 25,
                total_tokens_earned = COALESCE(total_tokens_earned, 0) + 25
            WHERE id = ?
        ''', (winner_id,))
    
    # Mark challenge completed
    cursor.execute('''
        UPDATE challenges SET status = ?, winner_id = ?, completed_at = datetime('now') WHERE id = ?
    ''', ('completed', winner_id, challenge_id))
    
    conn.commit()
    conn.close()
    return {'success': True, 'tokens_won': tokens_wagered + 25 if tokens_wagered else 25}

def get_pending_challenges(player_id):
    """Get challenges sent TO this player that are pending."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.*, p.nickname as challenger_name 
        FROM challenges c
        JOIN players p ON p.id = c.challenger_user_id
        WHERE c.challenged_user_id = ? AND c.status = 'pending'
        ORDER BY c.created_at DESC
    ''', (player_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_outgoing_challenges(player_id):
    """Get challenges sent BY this player that are pending."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.*, p.nickname as challenged_name 
        FROM challenges c
        JOIN players p ON p.id = c.challenged_user_id
        WHERE c.challenger_user_id = ? AND c.status = 'pending'
        ORDER BY c.created_at DESC
    ''', (player_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_active_challenges(player_id):
    """Get accepted challenges (games ready to play)."""
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
          AND c.status = 'accepted'
        ORDER BY c.responded_at DESC
    ''', (player_id, player_id))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_notifications(player_id, limit=20):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM notifications WHERE player_id = ? ORDER BY created_at DESC LIMIT ?', (player_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def mark_notification_read(notification_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE notifications SET read = 1 WHERE id = ?', (notification_id,))
    conn.commit()
    conn.close()

def mark_all_notifications_read(player_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE notifications SET read = 1 WHERE player_id = ?', (player_id,))
    conn.commit()
    conn.close()

def get_unread_count(player_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM notifications WHERE player_id = ? AND read = 0', (player_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

def update_activity(player_id, bar_id=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE players SET last_active = datetime("now") WHERE id = ?', (player_id,))
    conn.commit()
    conn.close()

def get_friends_playing(player_id):
    # Return friends who are currently in a queue
    return []


def award_game_tokens(winner_id, loser_id):
    """Award tokens after a game - more for winning, less for losing."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Winner gets 50 tokens
    cursor.execute('''
        UPDATE players 
        SET tokens_balance = COALESCE(tokens_balance, 0) + ? 
        WHERE id = ?
    ''', (TOKENS_WIN, winner_id))
    
    # Loser gets 10 tokens (for playing)
    cursor.execute('''
        UPDATE players 
        SET tokens_balance = COALESCE(tokens_balance, 0) + ? 
        WHERE id = ?
    ''', (TOKENS_LOSE, loser_id))
    
    # Log token transactions
    cursor.execute('''
        INSERT INTO token_transactions (player_id, amount, reason, details)
        VALUES (?, ?, 'game_win', 'Won a game')
    ''', (winner_id, TOKENS_WIN))
    
    cursor.execute('''
        INSERT INTO token_transactions (player_id, amount, reason, details)
        VALUES (?, ?, 'game_loss', 'Played a game')
    ''', (loser_id, TOKENS_LOSE))
    
    conn.commit()
    conn.close()
    
    return {
        'winner_tokens': TOKENS_WIN,
        'loser_tokens': TOKENS_LOSE
    }


def get_player_tokens(player_id):
    """Get a player's token balance."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT tokens_balance FROM players WHERE id = ?', (player_id,))
    row = cursor.fetchone()
    conn.close()
    return row['tokens_balance'] if row else 0


def add_tokens(player_id, amount, reason, details=None):
    """Add tokens to a player's balance."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE players 
        SET tokens_balance = COALESCE(tokens_balance, 0) + ? 
        WHERE id = ?
    ''', (amount, player_id))
    
    cursor.execute('''
        INSERT INTO token_transactions (player_id, amount, reason, details)
        VALUES (?, ?, ?, ?)
    ''', (player_id, amount, reason, details))
    
    conn.commit()
    conn.close()


def get_token_history(player_id, limit=20):
    """Get token transaction history for a player."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM token_transactions 
        WHERE player_id = ? 
        ORDER BY created_at DESC 
        LIMIT ?
    ''', (player_id, limit))
    results = cursor.fetchall()
    conn.close()
    return [dict(r) for r in results]
