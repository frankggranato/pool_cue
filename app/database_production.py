"""
Pool Cue - Production Database Initialization
Creates all necessary tables for a fresh deployment.
"""
import os
import sqlite3
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'db', 'pool_queue.db')


def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_production_db():
    """Initialize all tables for production use."""
    conn = get_db()
    cursor = conn.cursor()
    
    # ============ CORE TABLES ============
    
    # Players - main user table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE,
            password_hash TEXT,
            phone TEXT,
            total_games INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            tokens_balance INTEGER DEFAULT 100,
            tokens_earned INTEGER DEFAULT 0,
            tokens_spent INTEGER DEFAULT 0,
            current_streak INTEGER DEFAULT 0,
            best_streak INTEGER DEFAULT 0,
            win_streak INTEGER DEFAULT 0,
            rating INTEGER DEFAULT 1000,
            division TEXT DEFAULT 'Bronze',
            home_bar_id INTEGER,
            privacy_mode INTEGER DEFAULT 0,
            last_opponent_id INTEGER,
            last_game_result TEXT,
            last_daily_bonus DATE,
            referral_code TEXT,
            referred_by INTEGER,
            session_token TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Bars - pool halls/venues
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            address TEXT,
            city TEXT,
            state TEXT,
            zip_code TEXT,
            phone TEXT,
            website TEXT,
            hours TEXT,
            lat REAL,
            lng REAL,
            table_count INTEGER DEFAULT 1,
            google_review_url TEXT,
            promo_text TEXT,
            league_night TEXT,
            avg_rating REAL DEFAULT 0,
            total_ratings INTEGER DEFAULT 0,
            player_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Queue - current players waiting
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            bar_id INTEGER DEFAULT 1,
            position INTEGER NOT NULL,
            status TEXT DEFAULT 'waiting',
            wins_on_table INTEGER DEFAULT 0,
            session_token TEXT,
            partner_name TEXT,
            needs_confirmation INTEGER DEFAULT 0,
            confirmed INTEGER DEFAULT 0,
            confirmation_requested_at DATETIME,
            pushed_down_at DATETIME,
            push_count INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id),
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        )
    ''')
    
    # Game rules per bar/table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS game_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id INTEGER DEFAULT 1,
            rule_type TEXT DEFAULT 'bar_rules',
            game_type TEXT DEFAULT 'singles',
            custom_note TEXT,
            set_by_player_id INTEGER,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        )
    ''')
    
    # Game history
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS game_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            winner_id INTEGER,
            loser_id INTEGER,
            bar_id INTEGER,
            duration_seconds INTEGER,
            mode TEXT DEFAULT 'casual',
            played_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (winner_id) REFERENCES players(id),
            FOREIGN KEY (loser_id) REFERENCES players(id),
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        )
    ''')
    
    # Settings per bar
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id INTEGER UNIQUE,
            bar_name TEXT DEFAULT 'Pool Cue',
            table_name TEXT DEFAULT 'Table 1',
            address TEXT,
            city TEXT,
            state TEXT,
            zip_code TEXT,
            table_count INTEGER DEFAULT 1,
            google_review_url TEXT,
            ad_rotation_seconds INTEGER DEFAULT 10,
            board_style TEXT DEFAULT 'classic',
            display_theme TEXT DEFAULT 'default',
            current_game_start DATETIME,
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        )
    ''')
    
    # ============ SOCIAL TABLES ============
    
    # Friendships
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS friendships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            friend_id INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            accepted_at DATETIME,
            FOREIGN KEY (player_id) REFERENCES players(id),
            FOREIGN KEY (friend_id) REFERENCES players(id),
            UNIQUE(player_id, friend_id)
        )
    ''')
    
    # Challenges
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            challenger_user_id INTEGER NOT NULL,
            challenged_user_id INTEGER NOT NULL,
            bar_id INTEGER,
            message TEXT,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            responded_at DATETIME,
            FOREIGN KEY (challenger_user_id) REFERENCES players(id),
            FOREIGN KEY (challenged_user_id) REFERENCES players(id)
        )
    ''')
    
    # Notifications
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            title TEXT,
            message TEXT,
            data TEXT,
            read INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            read_at DATETIME,
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    ''')

    # ============ TOKEN & REWARDS TABLES ============
    
    # Token transactions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS token_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            reason TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    ''')
    
    # Player stats (aggregated)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_stats (
            player_id INTEGER PRIMARY KEY,
            total_games INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            elo_rating INTEGER DEFAULT 1200,
            token_balance INTEGER DEFAULT 0,
            friend_count INTEGER DEFAULT 0,
            pool_nights_attended INTEGER DEFAULT 0,
            last_calculated DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    ''')
    
    # ============ MODERATION TABLES ============
    
    # Player reports
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_id INTEGER,
            reported_player_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            details TEXT,
            bar_id INTEGER,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            resolved_at DATETIME,
            resolved_by INTEGER,
            resolution_notes TEXT,
            FOREIGN KEY (reporter_id) REFERENCES players(id),
            FOREIGN KEY (reported_player_id) REFERENCES players(id)
        )
    ''')
    
    # Action history (for undo)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS action_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT NOT NULL,
            player_id INTEGER,
            player_nickname TEXT,
            partner_name TEXT,
            queue_id INTEGER,
            position INTEGER,
            wins_on_table INTEGER,
            details TEXT,
            expires_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            undone INTEGER DEFAULT 0
        )
    ''')
    
    # ============ ADMIN TABLES ============
    
    # Master admin accounts
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'admin',
            is_active INTEGER DEFAULT 1,
            last_login DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Ads
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id INTEGER,
            file_name TEXT NOT NULL,
            label TEXT,
            slot TEXT DEFAULT 'general',
            active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        )
    ''')
    
    # ============ SURVEY TABLES ============
    
    # Drink surveys
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS drink_surveys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            game_id INTEGER,
            bar_id INTEGER,
            brand_selected TEXT,
            brand_category TEXT,
            survey_type TEXT DEFAULT 'post_game',
            game_result TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    ''')
    
    # ============ SETUP FLAG ============
    
    # Track if initial setup is complete
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS app_config (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✓ All production tables created")


def is_setup_complete():
    """Check if initial setup has been completed."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT value FROM app_config WHERE key = 'setup_complete'")
        row = cursor.fetchone()
        return row and row[0] == '1'
    except Exception:
        return False
    finally:
        conn.close()


def mark_setup_complete():
    """Mark initial setup as complete."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO app_config (key, value) VALUES ('setup_complete', '1')")
    conn.commit()
    conn.close()


def create_admin_account(username, password, is_superadmin=False):
    """Create a master admin account."""
    conn = get_db()
    cursor = conn.cursor()
    password_hash = generate_password_hash(password)
    try:
        cursor.execute('''
            INSERT INTO admin_accounts (username, password_hash, role, is_superadmin)
            VALUES (?, ?, 'master', ?)
        ''', (username, password_hash, 1 if is_superadmin else 0))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # Username already exists
    finally:
        conn.close()


def can_delete_admin(admin_id):
    """
    Check if an admin account can be deleted.
    Returns (can_delete: bool, reason: str)
    
    Rules:
    - Cannot delete superadmin accounts
    - Must always have at least one active admin
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if this admin is a superadmin
    cursor.execute('SELECT is_superadmin, username FROM admin_accounts WHERE id = ?', (admin_id,))
    admin = cursor.fetchone()
    
    if not admin:
        conn.close()
        return False, "Admin not found"
    
    if admin['is_superadmin']:
        conn.close()
        return False, "Cannot delete superadmin accounts. Use reset_admin.py to manage superadmins."
    
    # Check if this would leave us with no admins
    cursor.execute('SELECT COUNT(*) FROM admin_accounts WHERE is_active = 1 AND id != ?', (admin_id,))
    remaining = cursor.fetchone()[0]
    conn.close()
    
    if remaining < 1:
        return False, "Cannot delete the last admin account"
    
    return True, "OK"


def deactivate_admin(admin_id, deactivated_by=None):
    """
    Safely deactivate an admin account (soft delete).
    Cannot deactivate superadmins.
    """
    can_delete, reason = can_delete_admin(admin_id)
    if not can_delete:
        return False, reason
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE admin_accounts SET is_active = 0 WHERE id = ?', (admin_id,))
    conn.commit()
    conn.close()
    return True, "Admin deactivated"


def create_first_bar(name, address='', city='', state='', zip_code=''):
    """Create the first bar/venue."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO bars (name, address, city, state, zip_code)
        VALUES (?, ?, ?, ?, ?)
    ''', (name, address, city, state, zip_code))
    bar_id = cursor.lastrowid
    
    # Create default settings for this bar
    cursor.execute('''
        INSERT INTO settings (bar_id, bar_name) VALUES (?, ?)
    ''', (bar_id, name))
    
    # Create default game rules
    cursor.execute('''
        INSERT INTO game_rules (bar_id) VALUES (?)
    ''', (bar_id,))
    
    conn.commit()
    conn.close()
    return bar_id


if __name__ == '__main__':
    init_production_db()
