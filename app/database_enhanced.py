"""
import sqlite3
Database extensions for enhanced data collection and features
- Bar addresses and Google review links
- Category-based bar ratings
- User favorites
- Player home bars
- Activity tracking for analytics
"""
from .database import get_db
from datetime import datetime

def init_enhanced_db():
    """Initialize enhanced data collection tables."""
    conn = get_db()
    cursor = conn.cursor()
    
    # ============================================
    # BARS TABLE EXTENSIONS
    # ============================================
    bar_migrations = [
        'ALTER TABLE bars ADD COLUMN address TEXT',
        'ALTER TABLE bars ADD COLUMN city TEXT',
        'ALTER TABLE bars ADD COLUMN state TEXT',
        'ALTER TABLE bars ADD COLUMN zip_code TEXT',
        'ALTER TABLE bars ADD COLUMN lat REAL',
        'ALTER TABLE bars ADD COLUMN lng REAL',
        'ALTER TABLE bars ADD COLUMN google_review_url TEXT',
        'ALTER TABLE bars ADD COLUMN phone TEXT',
        'ALTER TABLE bars ADD COLUMN website TEXT',
        'ALTER TABLE bars ADD COLUMN hours TEXT',
        'ALTER TABLE bars ADD COLUMN table_count INTEGER DEFAULT 1',
        'ALTER TABLE bars ADD COLUMN avg_rating REAL DEFAULT 0',
        'ALTER TABLE bars ADD COLUMN total_ratings INTEGER DEFAULT 0',
        'ALTER TABLE bars ADD COLUMN player_count INTEGER DEFAULT 0',  # Players who claim this as home bar
    ]
    for sql in bar_migrations:
        try:
            cursor.execute(sql)
        except sqlite3.OperationalError: pass  # Column/table already exists
    
    # ============================================
    # BAR RATINGS (Category-based)
    # ============================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bar_ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            felt_rating INTEGER CHECK(felt_rating >= 1 AND felt_rating <= 5),
            stick_rating INTEGER CHECK(stick_rating >= 1 AND stick_rating <= 5),
            lighting_rating INTEGER CHECK(lighting_rating >= 1 AND lighting_rating <= 5),
            atmosphere_rating INTEGER CHECK(atmosphere_rating >= 1 AND atmosphere_rating <= 5),
            price_rating INTEGER CHECK(price_rating >= 1 AND price_rating <= 5),
            overall_rating REAL,
            review_text TEXT,
            google_reviewed INTEGER DEFAULT 0,
            tokens_earned INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bar_id) REFERENCES bars(id),
            FOREIGN KEY (player_id) REFERENCES players(id),
            UNIQUE(bar_id, player_id)
        )
    ''')
    
    # ============================================
    # USER FAVORITES
    # ============================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            bar_id INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id),
            FOREIGN KEY (bar_id) REFERENCES bars(id),
            UNIQUE(player_id, bar_id)
        )
    ''')
    
    # ============================================
    # PLAYER HOME BAR
    # ============================================
    player_migrations = [
        'ALTER TABLE players ADD COLUMN home_bar_id INTEGER',
        'ALTER TABLE players ADD COLUMN last_lat REAL',
        'ALTER TABLE players ADD COLUMN last_lng REAL',
        'ALTER TABLE players ADD COLUMN last_location_at DATETIME',
        'ALTER TABLE players ADD COLUMN push_token TEXT',
        'ALTER TABLE players ADD COLUMN notifications_enabled INTEGER DEFAULT 1',
        # DEMOGRAPHICS & PROFILE
        'ALTER TABLE players ADD COLUMN age_range TEXT',  # '21-25', '26-30', '31-40', '41-50', '50+'
        'ALTER TABLE players ADD COLUMN gender TEXT',
        'ALTER TABLE players ADD COLUMN zip_code TEXT',
        'ALTER TABLE players ADD COLUMN preferred_game TEXT DEFAULT "8-ball"',  # 8-ball, 9-ball, 10-ball
        'ALTER TABLE players ADD COLUMN preferred_rules TEXT DEFAULT "bar"',  # bar, apa, bca
        'ALTER TABLE players ADD COLUMN skill_self_rating INTEGER',  # 1-10 self assessment
        # PLAY PATTERNS
        'ALTER TABLE players ADD COLUMN first_game_at DATETIME',
        'ALTER TABLE players ADD COLUMN last_game_at DATETIME',
        'ALTER TABLE players ADD COLUMN total_sessions INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN avg_session_minutes REAL',
        'ALTER TABLE players ADD COLUMN favorite_day TEXT',  # Mon, Tue, Wed...
        'ALTER TABLE players ADD COLUMN favorite_hour INTEGER',  # 0-23
        'ALTER TABLE players ADD COLUMN peak_play_window TEXT',  # 'afternoon', 'evening', 'night', 'late_night'
        'ALTER TABLE players ADD COLUMN bars_visited INTEGER DEFAULT 0',
        # WIN/LOSS PATTERNS
        'ALTER TABLE players ADD COLUMN current_streak INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN best_streak INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN worst_streak INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN avg_game_duration_seconds INTEGER',
        'ALTER TABLE players ADD COLUMN games_as_challenger INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN games_as_defender INTEGER DEFAULT 0',
        # TOKEN & SHOP BEHAVIOR
        'ALTER TABLE players ADD COLUMN total_tokens_earned INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN total_tokens_spent INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN shop_visits INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN shop_product_views INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN shop_purchases INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN wishlist_count INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN avg_shop_time_seconds INTEGER',
        'ALTER TABLE players ADD COLUMN favorite_merch_category TEXT',
        # ENGAGEMENT METRICS
        'ALTER TABLE players ADD COLUMN surveys_completed INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN google_reviews_left INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN ratings_given INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN referrals_sent INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN referrals_converted INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN challenges_sent INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN challenges_accepted INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN challenges_declined INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN pool_nights_attended INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN pool_nights_hosted INTEGER DEFAULT 0',
        # SOCIAL METRICS
        'ALTER TABLE players ADD COLUMN friends_count INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN doubles_games INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN doubles_win_rate REAL',
        'ALTER TABLE players ADD COLUMN most_played_partner_id INTEGER',
        'ALTER TABLE players ADD COLUMN rivalries_count INTEGER DEFAULT 0',
        # APP USAGE
        'ALTER TABLE players ADD COLUMN app_opens INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN avg_session_length_seconds INTEGER',
        'ALTER TABLE players ADD COLUMN notification_clicks INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN notification_dismisses INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN device_type TEXT',  # iOS, Android, Web
        'ALTER TABLE players ADD COLUMN app_version TEXT',
        'ALTER TABLE players ADD COLUMN last_app_open DATETIME',
        # COHORT FLAGS (computed)
        'ALTER TABLE players ADD COLUMN cohort_frequency TEXT',  # daily, regular, weekend, casual
        'ALTER TABLE players ADD COLUMN cohort_time TEXT',  # early_bird, happy_hour, night_owl, late_night
        'ALTER TABLE players ADD COLUMN cohort_spending TEXT',  # high, medium, low, none
        'ALTER TABLE players ADD COLUMN cohort_social TEXT',  # social, solo
        'ALTER TABLE players ADD COLUMN cohort_loyalty TEXT',  # loyalist, hopper
        'ALTER TABLE players ADD COLUMN churn_risk_score INTEGER',  # 0-100
        'ALTER TABLE players ADD COLUMN lifetime_value_score INTEGER',  # 0-100
    ]
    for sql in player_migrations:
        try:
            cursor.execute(sql)
        except sqlite3.OperationalError: pass  # Column/table already exists
    
    # ============================================
    # ACTIVITY/EVENTS TABLE (Analytics)
    # ============================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER,
            event_type TEXT NOT NULL,
            event_data TEXT,
            bar_id INTEGER,
            lat REAL,
            lng REAL,
            device_info TEXT,
            session_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id),
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        )
    ''')
    
    # Index for fast activity queries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_activity_type ON user_activity(event_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_activity_player ON user_activity(player_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_activity_bar ON user_activity(bar_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_activity_date ON user_activity(created_at)')
    
    # ============================================
    # PLAYER BAR RANKINGS (Rank at each bar)
    # ============================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_bar_rankings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            bar_id INTEGER NOT NULL,
            rating INTEGER DEFAULT 1000,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            games_played INTEGER DEFAULT 0,
            division TEXT DEFAULT 'Bronze',
            last_played_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id),
            FOREIGN KEY (bar_id) REFERENCES bars(id),
            UNIQUE(player_id, bar_id)
        )
    ''')
    
    # ============================================
    # NOTIFICATIONS QUEUE
    # ============================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            title TEXT,
            message TEXT,
            data TEXT,
            read INTEGER DEFAULT 0,
            sent INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            read_at DATETIME,
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    ''')
    
    # ============================================
    # CHALLENGES TABLE
    # ============================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            challenger_id INTEGER NOT NULL,
            challenged_id INTEGER NOT NULL,
            bar_id INTEGER,
            mode TEXT DEFAULT 'ranked',
            status TEXT DEFAULT 'pending',
            message TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            responded_at DATETIME,
            played_at DATETIME,
            winner_id INTEGER,
            FOREIGN KEY (challenger_id) REFERENCES players(id),
            FOREIGN KEY (challenged_id) REFERENCES players(id),
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        )
    ''')
    
    # ============================================
    # FRIENDS TABLE
    # ============================================
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
    
    # ============================================
    # SHOP INTERACTIONS (Detailed Tracking)
    # ============================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shop_interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER,
            session_id TEXT,
            action TEXT NOT NULL,
            product_id TEXT,
            product_name TEXT,
            product_category TEXT,
            product_brand TEXT,
            token_price INTEGER,
            time_on_product_seconds INTEGER,
            added_to_wishlist INTEGER DEFAULT 0,
            purchased INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    ''')
    
    # ============================================
    # SURVEY RESPONSES
    # ============================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS survey_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            survey_id TEXT NOT NULL,
            survey_type TEXT,
            question_id TEXT,
            question_text TEXT,
            answer_value TEXT,
            answer_text TEXT,
            completion_time_seconds INTEGER,
            tokens_earned INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    ''')
    
    # ============================================
    # PLAYER SESSIONS (App Usage Tracking)
    # ============================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER,
            session_id TEXT NOT NULL,
            device_type TEXT,
            device_model TEXT,
            os_version TEXT,
            app_version TEXT,
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            ended_at DATETIME,
            duration_seconds INTEGER,
            pages_viewed INTEGER DEFAULT 0,
            actions_taken INTEGER DEFAULT 0,
            games_played INTEGER DEFAULT 0,
            tokens_earned INTEGER DEFAULT 0,
            tokens_spent INTEGER DEFAULT 0,
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    ''')
    
    # ============================================
    # AD IMPRESSIONS & CLICKS
    # ============================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ad_impressions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER,
            session_id TEXT,
            ad_placement TEXT NOT NULL,
            ad_id TEXT,
            ad_brand TEXT,
            impression_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            clicked INTEGER DEFAULT 0,
            clicked_at DATETIME,
            view_duration_seconds INTEGER,
            bar_id INTEGER,
            FOREIGN KEY (player_id) REFERENCES players(id),
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        )
    ''')
    
    # ============================================
    # PLAYER PREFERENCES (Survey-derived)
    # ============================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL UNIQUE,
            favorite_beer_brand TEXT,
            favorite_liquor_brand TEXT,
            favorite_game_type TEXT,
            visit_frequency TEXT,
            avg_spend_per_visit TEXT,
            plays_in_league INTEGER DEFAULT 0,
            league_name TEXT,
            interested_in_tournaments INTEGER DEFAULT 0,
            interested_in_lessons INTEGER DEFAULT 0,
            preferred_music_type TEXT,
            food_preference TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    ''')
    
    # ============================================
    # POOL NIGHTS TABLE
    # ============================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pool_nights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id INTEGER NOT NULL,
            host_id INTEGER NOT NULL,
            title TEXT,
            event_date DATE NOT NULL,
            start_time TEXT,
            end_time TEXT,
            game_type TEXT DEFAULT 'ranked',
            access_type TEXT DEFAULT 'open',
            description TEXT,
            max_players INTEGER,
            status TEXT DEFAULT 'pending',
            approved_at DATETIME,
            cancelled_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bar_id) REFERENCES bars(id),
            FOREIGN KEY (host_id) REFERENCES players(id)
        )
    ''')
    
    # ============================================
    # POOL NIGHT RSVPS
    # ============================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pool_night_rsvps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pool_night_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            status TEXT DEFAULT 'going',
            rsvp_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            checked_in INTEGER DEFAULT 0,
            checked_in_at DATETIME,
            no_show INTEGER DEFAULT 0,
            no_show_marked_at DATETIME,
            cancelled INTEGER DEFAULT 0,
            cancelled_at DATETIME,
            FOREIGN KEY (pool_night_id) REFERENCES pool_nights(id),
            FOREIGN KEY (player_id) REFERENCES players(id),
            UNIQUE(pool_night_id, player_id)
        )
    ''')
    
    # ============================================
    # PLAYER RSVP STATS (Aggregated reliability)
    # ============================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_rsvp_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL UNIQUE,
            total_rsvps INTEGER DEFAULT 0,
            total_attended INTEGER DEFAULT 0,
            total_no_shows INTEGER DEFAULT 0,
            total_cancellations INTEGER DEFAULT 0,
            show_rate REAL DEFAULT 100.0,
            reliability_score INTEGER DEFAULT 100,
            last_rsvp_at DATETIME,
            last_attended_at DATETIME,
            last_no_show_at DATETIME,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    ''')
    
    # ============================================
    # MONTHLY RANKINGS (For plaques)
    # ============================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS monthly_rankings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            borough TEXT NOT NULL,
            month TEXT NOT NULL,
            year INTEGER NOT NULL,
            place INTEGER NOT NULL,
            games_played INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            final_elo INTEGER,
            tokens_awarded INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    ''')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_monthly_player ON monthly_rankings(player_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_monthly_borough ON monthly_rankings(borough)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_rsvp_player ON pool_night_rsvps(player_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_rsvp_night ON pool_night_rsvps(pool_night_id)')
    
    conn.commit()
    conn.close()


# ============================================
# ACTIVITY TRACKING FUNCTIONS
# ============================================

def log_activity(player_id, event_type, event_data=None, bar_id=None, lat=None, lng=None, device_info=None, session_id=None):
    """Log user activity for analytics."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO user_activity (player_id, event_type, event_data, bar_id, lat, lng, device_info, session_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (player_id, event_type, event_data, bar_id, lat, lng, device_info, session_id))
    conn.commit()
    conn.close()


# Event types for activity tracking
EVENT_TYPES = {
    'app_open': 'User opened app',
    'page_view': 'User viewed a page',
    'bar_view': 'User viewed bar details',
    'bar_favorite': 'User favorited a bar',
    'bar_unfavorite': 'User unfavorited a bar',
    'bar_rating': 'User rated a bar',
    'google_review_click': 'User clicked Google review link',
    'queue_join': 'User joined queue',
    'queue_leave': 'User left queue',
    'game_start': 'Game started',
    'game_end': 'Game ended',
    'challenge_sent': 'User sent challenge',
    'challenge_received': 'User received challenge',
    'challenge_accepted': 'Challenge accepted',
    'challenge_declined': 'Challenge declined',
    'friend_request': 'Friend request sent',
    'friend_accept': 'Friend request accepted',
    'notification_received': 'Notification received',
    'notification_clicked': 'Notification clicked',
    'token_earned': 'Tokens earned',
    'token_spent': 'Tokens spent',
    'location_update': 'Location updated',
    'search': 'User searched',
}


# ============================================
# BAR FUNCTIONS
# ============================================

def get_bars_with_distance(lat, lng, limit=50):
    """Get bars sorted by distance from user location."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Haversine formula in SQL for distance calculation
    cursor.execute('''
        SELECT *,
            (6371 * acos(cos(radians(?)) * cos(radians(lat)) * cos(radians(lng) - radians(?)) + sin(radians(?)) * sin(radians(lat)))) AS distance
        FROM bars
        WHERE is_active = 1 AND lat IS NOT NULL AND lng IS NOT NULL
        ORDER BY distance ASC
        LIMIT ?
    ''', (lat, lng, lat, limit))
    
    bars = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return bars


def get_bars_by_popularity(limit=50):
    """Get bars sorted by player count (popularity)."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM bars WHERE is_active = 1
        ORDER BY player_count DESC, avg_rating DESC
        LIMIT ?
    ''', (limit,))
    bars = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return bars


def get_bars_with_friends(player_id, limit=50):
    """Get bars where user's friends play."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT b.*, COUNT(DISTINCT p.id) as friend_count
        FROM bars b
        JOIN players p ON p.home_bar_id = b.id
        JOIN friendships f ON (f.friend_id = p.id AND f.player_id = ? AND f.status = 'accepted')
                           OR (f.player_id = p.id AND f.friend_id = ? AND f.status = 'accepted')
        WHERE b.is_active = 1
        GROUP BY b.id
        ORDER BY friend_count DESC
        LIMIT ?
    ''', (player_id, player_id, limit))
    bars = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return bars


# ============================================
# FAVORITES FUNCTIONS
# ============================================

def add_favorite(player_id, bar_id):
    """Add a bar to user's favorites."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO user_favorites (player_id, bar_id) VALUES (?, ?)', (player_id, bar_id))
        conn.commit()
        log_activity(player_id, 'bar_favorite', bar_id=bar_id)
    except Exception:
        pass  # Already favorited
    conn.close()


def remove_favorite(player_id, bar_id):
    """Remove a bar from user's favorites."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM user_favorites WHERE player_id = ? AND bar_id = ?', (player_id, bar_id))
    conn.commit()
    log_activity(player_id, 'bar_unfavorite', bar_id=bar_id)
    conn.close()


def get_favorites(player_id):
    """Get user's favorite bars."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT b.* FROM bars b
        JOIN user_favorites f ON b.id = f.bar_id
        WHERE f.player_id = ?
        ORDER BY f.created_at DESC
    ''', (player_id,))
    bars = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return bars


def is_favorite(player_id, bar_id):
    """Check if bar is in user's favorites."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM user_favorites WHERE player_id = ? AND bar_id = ?', (player_id, bar_id))
    result = cursor.fetchone() is not None
    conn.close()
    return result


# ============================================
# BAR RATING FUNCTIONS
# ============================================

def rate_bar(player_id, bar_id, felt, stick, lighting, atmosphere, price, review_text=None):
    """Rate a bar with category ratings."""
    conn = get_db()
    cursor = conn.cursor()
    
    overall = (felt + stick + lighting + atmosphere + price) / 5.0
    tokens = 50  # Tokens earned for rating
    
    cursor.execute('''
        INSERT OR REPLACE INTO bar_ratings 
        (bar_id, player_id, felt_rating, stick_rating, lighting_rating, atmosphere_rating, price_rating, overall_rating, review_text, tokens_earned)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (bar_id, player_id, felt, stick, lighting, atmosphere, price, overall, review_text, tokens))
    
    # Update bar's average rating
    cursor.execute('''
        UPDATE bars SET 
            avg_rating = (SELECT AVG(overall_rating) FROM bar_ratings WHERE bar_id = ?),
            total_ratings = (SELECT COUNT(*) FROM bar_ratings WHERE bar_id = ?)
        WHERE id = ?
    ''', (bar_id, bar_id, bar_id))
    
    # Award tokens
    cursor.execute('UPDATE user_tokens SET balance = balance + ?, lifetime_earned = lifetime_earned + ? WHERE player_id = ?', 
                   (tokens, tokens, player_id))
    
    conn.commit()
    log_activity(player_id, 'bar_rating', str(overall), bar_id=bar_id)
    conn.close()
    
    return {'tokens_earned': tokens, 'overall_rating': overall}


def mark_google_reviewed(player_id, bar_id):
    """Mark that user completed Google review (bonus tokens)."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('UPDATE bar_ratings SET google_reviewed = 1 WHERE player_id = ? AND bar_id = ?', (player_id, bar_id))
    
    bonus_tokens = 100
    cursor.execute('UPDATE user_tokens SET balance = balance + ?, lifetime_earned = lifetime_earned + ? WHERE player_id = ?',
                   (bonus_tokens, bonus_tokens, player_id))
    
    conn.commit()
    log_activity(player_id, 'google_review_click', bar_id=bar_id)
    conn.close()
    
    return {'bonus_tokens': bonus_tokens}


def get_bar_ratings(bar_id):
    """Get category ratings for a bar."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 
            AVG(felt_rating) as felt,
            AVG(stick_rating) as stick,
            AVG(lighting_rating) as lighting,
            AVG(atmosphere_rating) as atmosphere,
            AVG(price_rating) as price,
            AVG(overall_rating) as overall,
            COUNT(*) as count
        FROM bar_ratings WHERE bar_id = ?
    ''', (bar_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row and row['count'] > 0:
        return {
            'felt': round(row['felt'] or 0, 1),
            'stick': round(row['stick'] or 0, 1),
            'lighting': round(row['lighting'] or 0, 1),
            'atmosphere': round(row['atmosphere'] or 0, 1),
            'price': round(row['price'] or 0, 1),
            'overall': round(row['overall'] or 0, 1),
            'count': row['count']
        }
    return None


# ============================================
# PLAYER BAR RANKINGS
# ============================================

def get_player_bar_rankings(player_id):
    """Get player's rank at each bar they've played."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT pbr.*, b.name as bar_name, b.address, b.city,
            (SELECT COUNT(*) + 1 FROM player_bar_rankings pbr2 
             WHERE pbr2.bar_id = pbr.bar_id AND pbr2.rating > pbr.rating) as rank
        FROM player_bar_rankings pbr
        JOIN bars b ON pbr.bar_id = b.id
        WHERE pbr.player_id = ?
        ORDER BY pbr.rating DESC
    ''', (player_id,))
    rankings = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rankings


def get_bar_leaderboard(bar_id, limit=50):
    """Get leaderboard for a specific bar."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT pbr.*, p.nickname, p.division as global_division
        FROM player_bar_rankings pbr
        JOIN players p ON pbr.player_id = p.id
        WHERE pbr.bar_id = ? AND pbr.games_played >= 3
        ORDER BY pbr.rating DESC
        LIMIT ?
    ''', (bar_id, limit))
    
    players = []
    for i, row in enumerate(cursor.fetchall(), 1):
        players.append({
            'rank': i,
            'player_id': row['player_id'],
            'nickname': row['nickname'],
            'rating': row['rating'],
            'wins': row['wins'],
            'losses': row['losses'],
            'games': row['games_played'],
            'division': row['division']
        })
    conn.close()
    return players


# ============================================
# CHALLENGES FUNCTIONS
# ============================================

def send_challenge(challenger_id, challenged_id, bar_id=None, mode='ranked', message=None):
    """Send a challenge to another player."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO challenges (challenger_id, challenged_id, bar_id, mode, message)
        VALUES (?, ?, ?, ?, ?)
    ''', (challenger_id, challenged_id, bar_id, mode, message))
    challenge_id = cursor.lastrowid
    
    # Create notification
    cursor.execute('''
        INSERT INTO notifications (player_id, type, title, message, data)
        VALUES (?, 'challenge', 'New Challenge!', 'You have been challenged to a game', ?)
    ''', (challenged_id, str(challenge_id)))
    
    conn.commit()
    log_activity(challenger_id, 'challenge_sent', str(challenged_id))
    conn.close()
    return challenge_id


def respond_to_challenge(challenge_id, accepted):
    """Accept or decline a challenge."""
    conn = get_db()
    cursor = conn.cursor()
    status = 'accepted' if accepted else 'declined'
    cursor.execute('UPDATE challenges SET status = ?, responded_at = CURRENT_TIMESTAMP WHERE id = ?', (status, challenge_id))
    conn.commit()
    conn.close()


def get_pending_challenges(player_id):
    """Get pending challenges for a player."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.*, p.nickname as challenger_name, b.name as bar_name
        FROM challenges c
        JOIN players p ON c.challenger_id = p.id
        LEFT JOIN bars b ON c.bar_id = b.id
        WHERE c.challenged_id = ? AND c.status = 'pending'
        ORDER BY c.created_at DESC
    ''', (player_id,))
    challenges = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return challenges


# ============================================
# FRIENDS FUNCTIONS
# ============================================

def send_friend_request(player_id, friend_id):
    """Send a friend request."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO friendships (player_id, friend_id) VALUES (?, ?)', (player_id, friend_id))
        
        # Create notification
        cursor.execute('''
            INSERT INTO notifications (player_id, type, title, message, data)
            VALUES (?, 'friend_request', 'Friend Request', 'Someone wants to be your friend!', ?)
        ''', (friend_id, str(player_id)))
        
        conn.commit()
        log_activity(player_id, 'friend_request', str(friend_id))
    except Exception:
        pass
    conn.close()


def respond_to_friend_request(friendship_id, accepted):
    """Accept or decline a friend request."""
    conn = get_db()
    cursor = conn.cursor()
    if accepted:
        cursor.execute('UPDATE friendships SET status = "accepted", accepted_at = CURRENT_TIMESTAMP WHERE id = ?', (friendship_id,))
    else:
        cursor.execute('DELETE FROM friendships WHERE id = ?', (friendship_id,))
    conn.commit()
    conn.close()


def get_friends(player_id):
    """Get all friends for a player."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.*, 
            CASE WHEN f.player_id = ? THEN f.friend_id ELSE f.player_id END as friend_player_id
        FROM friendships f
        JOIN players p ON p.id = CASE WHEN f.player_id = ? THEN f.friend_id ELSE f.player_id END
        WHERE (f.player_id = ? OR f.friend_id = ?) AND f.status = 'accepted'
    ''', (player_id, player_id, player_id, player_id))
    friends = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return friends


def get_friend_requests(player_id):
    """Get pending friend requests for a player."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT f.*, p.nickname as requester_name
        FROM friendships f
        JOIN players p ON f.player_id = p.id
        WHERE f.friend_id = ? AND f.status = 'pending'
    ''', (player_id,))
    requests = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return requests


# ============================================
# NOTIFICATIONS
# ============================================

def create_notification(player_id, notif_type, title, message, data=None):
    """Create a notification for a player."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO notifications (player_id, type, title, message, data)
        VALUES (?, ?, ?, ?, ?)
    ''', (player_id, notif_type, title, message, data))
    notif_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return notif_id


def get_unread_notifications(player_id):
    """Get unread notifications for a player."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM notifications WHERE player_id = ? AND read = 0
        ORDER BY created_at DESC
    ''', (player_id,))
    notifs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return notifs


def notify_next_up(player_id, bar_id):
    """Notify player they're up next in queue."""
    create_notification(
        player_id, 
        'queue_next',
        "You're Up Next!",
        "Get ready - you're the next challenger!",
        str(bar_id)
    )


# ============================================
# ANALYTICS AGGREGATION
# ============================================

def get_activity_summary(days=30):
    """Get activity summary for analytics dashboard."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT event_type, COUNT(*) as count, COUNT(DISTINCT player_id) as unique_users
        FROM user_activity
        WHERE created_at >= datetime('now', ?)
        GROUP BY event_type
        ORDER BY count DESC
    ''', (f'-{days} days',))
    
    summary = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return summary


def get_bar_analytics(bar_id, days=30):
    """Get analytics for a specific bar."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            COUNT(*) as total_events,
            COUNT(DISTINCT player_id) as unique_visitors,
            SUM(CASE WHEN event_type = 'queue_join' THEN 1 ELSE 0 END) as queue_joins,
            SUM(CASE WHEN event_type = 'bar_rating' THEN 1 ELSE 0 END) as ratings,
            SUM(CASE WHEN event_type = 'bar_favorite' THEN 1 ELSE 0 END) as favorites
        FROM user_activity
        WHERE bar_id = ? AND created_at >= datetime('now', ?)
    ''', (bar_id, f'-{days} days'))
    
    result = dict(cursor.fetchone())
    conn.close()
    return result



# ============================================
# TASTEMAKER SYSTEM
# ============================================

def init_tastemaker_tables():
    """Initialize tastemaker-related tables."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Add tastemaker columns to players if not exists
    try:
        cursor.execute('''ALTER TABLE players ADD COLUMN is_tastemaker INTEGER DEFAULT 0''')
    except Exception:
        pass
    try:
        cursor.execute('''ALTER TABLE players ADD COLUMN tastemaker_since TEXT''')
    except Exception:
        pass
    try:
        cursor.execute('''ALTER TABLE players ADD COLUMN tastemaker_granted_by INTEGER''')
    except Exception:
        pass
    try:
        cursor.execute('''ALTER TABLE players ADD COLUMN tastemaker_slots_used INTEGER DEFAULT 0''')
    except Exception:
        pass
    try:
        cursor.execute('''ALTER TABLE players ADD COLUMN last_tastemaker_transfer TEXT''')
    except Exception:
        pass
    
    # Tastemaker transfer history
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tastemaker_transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_player_id INTEGER,
            to_player_id INTEGER NOT NULL,
            transferred_at TEXT DEFAULT CURRENT_TIMESTAMP,
            granted_by_admin INTEGER DEFAULT 0,
            notes TEXT,
            FOREIGN KEY (from_player_id) REFERENCES players(id),
            FOREIGN KEY (to_player_id) REFERENCES players(id)
        )
    ''')
    
    # Tastemaker signups (people added to queue by tastemakers)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tastemaker_signups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tastemaker_id INTEGER NOT NULL,
            signed_up_name TEXT NOT NULL,
            signed_up_player_id INTEGER,
            bar_id INTEGER NOT NULL,
            queue_position INTEGER,
            signup_type TEXT DEFAULT 'random',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tastemaker_id) REFERENCES players(id),
            FOREIGN KEY (signed_up_player_id) REFERENCES players(id),
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        )
    ''')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tastemaker_signups ON tastemaker_signups(tastemaker_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tastemaker_transfers ON tastemaker_transfers(to_player_id)')
    
    conn.commit()
    conn.close()


def grant_tastemaker(player_id, granted_by_admin=True, notes=None):
    """Grant tastemaker status to a player."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE players 
        SET is_tastemaker = 1, 
            tastemaker_since = CURRENT_TIMESTAMP,
            tastemaker_granted_by = ?,
            tastemaker_slots_used = 0
        WHERE id = ?
    ''', (1 if granted_by_admin else 0, player_id))
    
    # Log the transfer/grant
    cursor.execute('''
        INSERT INTO tastemaker_transfers (from_player_id, to_player_id, granted_by_admin, notes)
        VALUES (NULL, ?, ?, ?)
    ''', (player_id, 1 if granted_by_admin else 0, notes))
    
    conn.commit()
    conn.close()
    return True


def revoke_tastemaker(player_id):
    """Revoke tastemaker status from a player."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE players 
        SET is_tastemaker = 0, 
            tastemaker_since = NULL,
            tastemaker_granted_by = NULL,
            tastemaker_slots_used = 0
        WHERE id = ?
    ''', (player_id,))
    
    conn.commit()
    conn.close()
    return True


def transfer_tastemaker(from_player_id, to_player_id):
    """Transfer tastemaker status to another player (30-day cooldown)."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if sender is tastemaker
    cursor.execute('SELECT is_tastemaker, last_tastemaker_transfer FROM players WHERE id = ?', (from_player_id,))
    sender = cursor.fetchone()
    if not sender or not sender[0]:
        conn.close()
        return {'success': False, 'error': 'You are not a tastemaker'}
    
    # Check 30-day cooldown
    if sender[1]:
        cursor.execute('''
            SELECT julianday('now') - julianday(?) as days_since
        ''', (sender[1],))
        days = cursor.fetchone()[0]
        if days < 30:
            conn.close()
            return {'success': False, 'error': f'Must wait {int(30 - days)} more days to transfer'}
    
    # Check recipient isn't already a tastemaker
    cursor.execute('SELECT is_tastemaker FROM players WHERE id = ?', (to_player_id,))
    recipient = cursor.fetchone()
    if recipient and recipient[0]:
        conn.close()
        return {'success': False, 'error': 'Recipient is already a tastemaker'}
    
    # Perform transfer
    cursor.execute('''
        UPDATE players 
        SET is_tastemaker = 0, 
            last_tastemaker_transfer = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (from_player_id,))
    
    cursor.execute('''
        UPDATE players 
        SET is_tastemaker = 1, 
            tastemaker_since = CURRENT_TIMESTAMP,
            tastemaker_granted_by = ?,
            tastemaker_slots_used = 0
        WHERE id = ?
    ''', (from_player_id, to_player_id))
    
    # Log transfer
    cursor.execute('''
        INSERT INTO tastemaker_transfers (from_player_id, to_player_id, granted_by_admin, notes)
        VALUES (?, ?, 0, 'Player transfer')
    ''', (from_player_id, to_player_id))
    
    conn.commit()
    conn.close()
    return {'success': True}


def tastemaker_signup(tastemaker_id, bar_id, name=None, friend_player_id=None):
    """Tastemaker signs up someone to the queue (max 5 per day)."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if tastemaker
    cursor.execute('SELECT is_tastemaker, tastemaker_slots_used FROM players WHERE id = ?', (tastemaker_id,))
    tm = cursor.fetchone()
    if not tm or not tm[0]:
        conn.close()
        return {'success': False, 'error': 'Not a tastemaker'}
    
    # Check daily limit (5 signups)
    cursor.execute('''
        SELECT COUNT(*) FROM tastemaker_signups 
        WHERE tastemaker_id = ? AND DATE(created_at) = DATE('now')
    ''', (tastemaker_id,))
    today_count = cursor.fetchone()[0]
    if today_count >= 5:
        conn.close()
        return {'success': False, 'error': 'Daily signup limit reached (5)'}
    
    # Determine signup type
    signup_type = 'friend' if friend_player_id else 'random'
    signed_up_name = name
    
    if friend_player_id:
        cursor.execute('SELECT name FROM players WHERE id = ?', (friend_player_id,))
        friend = cursor.fetchone()
        if friend:
            signed_up_name = friend[0]
    
    # Create signup record
    cursor.execute('''
        INSERT INTO tastemaker_signups (tastemaker_id, signed_up_name, signed_up_player_id, bar_id, signup_type)
        VALUES (?, ?, ?, ?, ?)
    ''', (tastemaker_id, signed_up_name, friend_player_id, bar_id, signup_type))
    
    conn.commit()
    conn.close()
    return {'success': True, 'name': signed_up_name, 'remaining': 5 - today_count - 1}


def get_bar_tastemakers(bar_id):
    """Get tastemakers for a specific bar (home bar)."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, tastemaker_since
        FROM players 
        WHERE is_tastemaker = 1 AND home_bar_id = ?
        ORDER BY tastemaker_since DESC
    ''', (bar_id,))
    
    tastemakers = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return tastemakers


def get_all_tastemakers():
    """Get all tastemakers across all bars."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT p.id, p.name, p.tastemaker_since, p.home_bar_id, b.name as bar_name
        FROM players p
        LEFT JOIN bars b ON p.home_bar_id = b.id
        WHERE p.is_tastemaker = 1
        ORDER BY p.tastemaker_since DESC
    ''')
    
    tastemakers = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return tastemakers


# Initialize tastemaker tables on import
try:
    init_tastemaker_tables()
except Exception:
    pass
