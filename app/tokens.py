"""
Token System - Earn and spend tokens
"""
from datetime import datetime
from .database import get_db

# Token amounts
TOKENS_WIN = 50          # Win a game
TOKENS_LOSE = 10         # Lose a game (still get something for playing)
TOKENS_SURVEY = 25       # Answer a survey question
TOKENS_SIGNUP = 0        # Start with zero
TOKENS_REFERRAL = 100    # Refer a friend who signs up
TOKENS_STREAK_BONUS = 25 # Bonus per win in streak (3+ wins)

# =============================================================================
# ANTI-SPAM SETTINGS - Prevent token farming from fake quick games
# =============================================================================
MIN_GAME_DURATION_SECONDS = 60       # Games under 60 seconds = no tokens
RAPID_GAME_COOLDOWN_SECONDS = 30     # Must wait 30s between game completions
MAX_GAMES_PER_HOUR = 20              # Max games that can award tokens per hour
SPAM_TRACKING_WINDOW_SECONDS = 3600  # 1 hour window for tracking


def check_game_eligible_for_tokens(player_id, game_duration_seconds, bar_id=None):
    """
    Check if a game qualifies for token awards based on anti-spam rules.
    
    Returns: (eligible: bool, reason: str)
    """
    # Rule 1: Minimum game duration
    if game_duration_seconds < MIN_GAME_DURATION_SECONDS:
        return False, f'game_too_short:{game_duration_seconds}s<{MIN_GAME_DURATION_SECONDS}s'
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Rule 2: Check rapid game cooldown (time since last game ended)
        cursor.execute('''
            SELECT played_at FROM game_history 
            WHERE (winner_id = ? OR loser_id = ?)
            ORDER BY played_at DESC LIMIT 1
        ''', (player_id, player_id))
        row = cursor.fetchone()
        
        if row and row['played_at']:
            last_game_time = datetime.fromisoformat(row['played_at'].replace('Z', '+00:00').split('+')[0])
            seconds_since_last = (datetime.now() - last_game_time).total_seconds()
            if seconds_since_last < RAPID_GAME_COOLDOWN_SECONDS:
                return False, f'rapid_game_cooldown:{seconds_since_last:.0f}s<{RAPID_GAME_COOLDOWN_SECONDS}s'
        
        # Rule 3: Check games per hour limit
        cursor.execute('''
            SELECT COUNT(*) FROM game_history 
            WHERE (winner_id = ? OR loser_id = ?)
              AND played_at >= datetime('now', '-1 hour')
        ''', (player_id, player_id))
        games_last_hour = cursor.fetchone()[0] or 0
        
        if games_last_hour >= MAX_GAMES_PER_HOUR:
            return False, f'hourly_limit_reached:{games_last_hour}>={MAX_GAMES_PER_HOUR}'
    
    finally:
        conn.close()
    
    return True, 'eligible'


def log_blocked_token_award(player_id, reason, would_have_earned, bar_id=None):
    """Log when tokens are blocked due to anti-spam rules (for admin visibility)."""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Try to create table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blocked_token_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                would_have_earned INTEGER,
                bar_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            INSERT INTO blocked_token_log (player_id, reason, would_have_earned, bar_id)
            VALUES (?, ?, ?, ?)
        ''', (player_id, reason, would_have_earned, bar_id))
        
        conn.commit()
        print(f"[TOKEN ANTI-SPAM] Blocked {would_have_earned} tokens for player {player_id}: {reason}")
    except Exception as e:
        print(f"[TOKEN ANTI-SPAM] Log error: {e}")
    finally:
        conn.close()


def award_tokens(player_id, amount, reason, details=None):
    """Award tokens to a player and log the transaction."""
    if amount == 0:
        return {'success': True, 'amount': 0, 'new_balance': get_balance(player_id)}
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Update player balance
    cursor.execute('''
        UPDATE players 
        SET tokens_balance = COALESCE(tokens_balance, 0) + ?,
            tokens_earned = COALESCE(tokens_earned, 0) + ?
        WHERE id = ?
    ''', (amount, max(0, amount), player_id))
    
    # Log transaction
    cursor.execute('''
        INSERT INTO token_transactions (player_id, amount, reason, details)
        VALUES (?, ?, ?, ?)
    ''', (player_id, amount, reason, details))
    
    # Get new balance
    cursor.execute('SELECT tokens_balance FROM players WHERE id = ?', (player_id,))
    row = cursor.fetchone()
    new_balance = row[0] if row else 0
    
    conn.commit()
    conn.close()
    
    return {
        'success': True,
        'amount': amount,
        'reason': reason,
        'new_balance': new_balance
    }


def spend_tokens(player_id, amount, reason, details=None):
    """Spend tokens (returns False if insufficient balance)."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Check balance
    cursor.execute('SELECT tokens_balance FROM players WHERE id = ?', (player_id,))
    row = cursor.fetchone()
    balance = row[0] if row else 0
    
    if balance < amount:
        conn.close()
        return {'success': False, 'error': 'Insufficient tokens', 'balance': balance}
    
    # Deduct tokens
    cursor.execute('''
        UPDATE players 
        SET tokens_balance = tokens_balance - ?,
            tokens_spent = COALESCE(tokens_spent, 0) + ?
        WHERE id = ?
    ''', (amount, amount, player_id))
    
    # Log transaction (negative amount)
    cursor.execute('''
        INSERT INTO token_transactions (player_id, amount, reason, details)
        VALUES (?, ?, ?, ?)
    ''', (player_id, -amount, reason, details))
    
    conn.commit()
    conn.close()
    
    return {
        'success': True,
        'spent': amount,
        'new_balance': balance - amount
    }


def get_balance(player_id):
    """Get player's token balance."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT tokens_balance FROM players WHERE id = ?', (player_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row and row[0] else 0


def get_history(player_id, limit=20):
    """Get player's token transaction history."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT amount, reason, details, created_at 
        FROM token_transactions 
        WHERE player_id = ? 
        ORDER BY created_at DESC 
        LIMIT ?
    ''', (player_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def award_game_result(player_id, won, streak=0, game_duration_seconds=None, bar_id=None):
    """
    Award tokens for a game result.
    
    Args:
        player_id: The player to award tokens to
        won: Whether the player won
        streak: Current win streak (for bonus calculation)
        game_duration_seconds: Duration of the game (for anti-spam check)
        bar_id: Bar where game was played (for logging)
    
    Returns:
        dict with success status, amount awarded, and new balance
    """
    # Calculate what would be awarded
    if won:
        base = TOKENS_WIN
        reason = 'game_win'
        if streak >= 3:
            bonus = TOKENS_STREAK_BONUS * (streak - 2)
            base += bonus
            details = f'Win #{streak} (+{bonus} streak bonus)'
        else:
            details = f'Win #{streak}' if streak else 'Game won'
    else:
        base = TOKENS_LOSE
        reason = 'game_loss'
        details = 'Thanks for playing'
    
    # Anti-spam check (only if duration provided)
    if game_duration_seconds is not None:
        eligible, block_reason = check_game_eligible_for_tokens(
            player_id, game_duration_seconds, bar_id
        )
        if not eligible:
            # Log the blocked award for admin visibility
            log_blocked_token_award(player_id, block_reason, base, bar_id)
            return {
                'success': True,  # Game still counts, just no tokens
                'amount': 0,
                'reason': 'blocked',
                'block_reason': block_reason,
                'new_balance': get_balance(player_id)
            }
    
    return award_tokens(player_id, base, reason, details)


def award_survey(player_id, survey_type='general'):
    """Award tokens for completing a survey."""
    return award_tokens(player_id, TOKENS_SURVEY, 'survey', survey_type)


def award_referral(player_id, referred_nickname):
    """Award tokens for referring a new player."""
    return award_tokens(player_id, TOKENS_REFERRAL, 'referral', f'Referred {referred_nickname}')
