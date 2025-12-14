"""
Extended Database - Brands, Tokens, Surveys, Analytics
"""
from .database import get_db

def init_extended_db():
    """Initialize extended tables for data products."""
    conn = get_db()
    cursor = conn.cursor()
    
    # ============ BRANDS & ADS ============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS brands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            logo_path TEXT,
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ad_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id INTEGER,
            placement TEXT NOT NULL,
            brand_id INTEGER,
            image_path TEXT,
            label TEXT,
            click_url TEXT,
            is_active INTEGER DEFAULT 1,
            priority INTEGER DEFAULT 0,
            FOREIGN KEY (bar_id) REFERENCES bars(id),
            FOREIGN KEY (brand_id) REFERENCES brands(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS brand_impressions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_id INTEGER,
            bar_id INTEGER,
            placement TEXT,
            impression_type TEXT,
            estimated_viewers INTEGER DEFAULT 1,
            occurred_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (brand_id) REFERENCES brands(id),
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS brand_clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_id INTEGER,
            bar_id INTEGER,
            user_id INTEGER,
            placement TEXT,
            occurred_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (brand_id) REFERENCES brands(id)
        )
    ''')
    
    # ============ PLAYER COHORTS ============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_cohorts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            cohort_tags_json TEXT DEFAULT '[]',
            last_computed_at DATETIME,
            FOREIGN KEY (user_id) REFERENCES user_accounts(id)
        )
    ''')
    
    # ============ BAR ENGAGEMENT ============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bar_engagement_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id INTEGER,
            date DATE,
            unique_players INTEGER DEFAULT 0,
            matches_played INTEGER DEFAULT 0,
            ranked_matches INTEGER DEFAULT 0,
            casual_matches INTEGER DEFAULT 0,
            avg_matches_per_player REAL,
            return_rate_7d REAL,
            challenges_sent INTEGER DEFAULT 0,
            engagement_score INTEGER DEFAULT 0,
            peak_hour INTEGER,
            UNIQUE(bar_id, date),
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        )
    ''')
    
    # ============ SURVEYS ============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS survey_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_id INTEGER,
            text TEXT NOT NULL,
            response_type TEXT DEFAULT 'single_choice',
            options_json TEXT,
            token_reward INTEGER DEFAULT 10,
            is_active INTEGER DEFAULT 1,
            weight INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (brand_id) REFERENCES brands(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS survey_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER,
            user_id INTEGER,
            bar_id INTEGER,
            answer_json TEXT,
            answered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (question_id) REFERENCES survey_questions(id),
            FOREIGN KEY (user_id) REFERENCES user_accounts(id)
        )
    ''')

    # ============ TOKENS ============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            balance INTEGER DEFAULT 0,
            lifetime_earned INTEGER DEFAULT 0,
            lifetime_spent INTEGER DEFAULT 0,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES user_accounts(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS token_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            delta INTEGER,
            reason TEXT,
            meta_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES user_accounts(id)
        )
    ''')
    
    # ============ BRAND REPORTS ============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS brand_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_id INTEGER,
            period_start DATE,
            period_end DATE,
            generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            file_path TEXT,
            summary_json TEXT,
            FOREIGN KEY (brand_id) REFERENCES brands(id)
        )
    ''')
    
    # ============ SEASONS & STANDINGS ============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS seasons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            start_date DATE,
            end_date DATE,
            is_active INTEGER DEFAULT 0,
            sponsor_brand_id INTEGER,
            FOREIGN KEY (sponsor_brand_id) REFERENCES brands(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS season_standings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_id INTEGER,
            user_id INTEGER,
            bar_id INTEGER,
            games_played INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            rating INTEGER DEFAULT 1000,
            division TEXT DEFAULT 'Bronze',
            last_updated_at DATETIME,
            UNIQUE(season_id, user_id, bar_id),
            FOREIGN KEY (season_id) REFERENCES seasons(id),
            FOREIGN KEY (user_id) REFERENCES user_accounts(id)
        )
    ''')
    
    # ============ ACHIEVEMENTS ============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS achievements_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            name TEXT NOT NULL,
            description TEXT,
            icon TEXT,
            condition_type TEXT,
            condition_value INTEGER,
            token_reward INTEGER DEFAULT 0,
            xp_reward INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            achievement_id INTEGER,
            unlocked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, achievement_id),
            FOREIGN KEY (user_id) REFERENCES user_accounts(id),
            FOREIGN KEY (achievement_id) REFERENCES achievements_catalog(id)
        )
    ''')
    
    # ============ NIGHTLY AWARDS ============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS nightly_awards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id INTEGER,
            date DATE,
            award_type TEXT,
            user_id INTEGER,
            value TEXT,
            sponsor_brand_id INTEGER,
            FOREIGN KEY (bar_id) REFERENCES bars(id),
            FOREIGN KEY (user_id) REFERENCES user_accounts(id),
            FOREIGN KEY (sponsor_brand_id) REFERENCES brands(id)
        )
    ''')
    
    # ============ RIVALRIES (proper) ============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rivalries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user1_id INTEGER,
            user2_id INTEGER,
            total_matches INTEGER DEFAULT 0,
            user1_wins INTEGER DEFAULT 0,
            user2_wins INTEGER DEFAULT 0,
            rivalry_score INTEGER DEFAULT 0,
            last_match_at DATETIME,
            UNIQUE(user1_id, user2_id),
            FOREIGN KEY (user1_id) REFERENCES user_accounts(id),
            FOREIGN KEY (user2_id) REFERENCES user_accounts(id)
        )
    ''')
    
    # ============ PLAYER BAR STATS ============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_bar_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            bar_id INTEGER,
            games_played INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            rating INTEGER DEFAULT 1000,
            last_seen_at DATETIME,
            UNIQUE(user_id, bar_id),
            FOREIGN KEY (user_id) REFERENCES user_accounts(id),
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        )
    ''')
    
    # ============ HEATMAP DATA ============
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activity_heatmap (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id INTEGER,
            day_of_week INTEGER,
            hour INTEGER,
            match_count INTEGER DEFAULT 0,
            player_count INTEGER DEFAULT 0,
            week_start DATE,
            UNIQUE(bar_id, day_of_week, hour, week_start),
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        )
    ''')
    
    conn.commit()
    
    # Seed initial data
    _seed_initial_data(conn)
    conn.close()


def _seed_initial_data(conn):
    """Seed achievements and survey questions. Brands are NOT pre-seeded - they come from actual ads."""
    cursor = conn.cursor()
    
    # NOTE: Brands are NOT pre-seeded. They are created when ads are uploaded.
    # This ensures analytics only shows data for actual advertising campaigns.
    
    # Seed achievements
    cursor.execute('SELECT COUNT(*) FROM achievements_catalog')
    if cursor.fetchone()[0] == 0:
        achievements = [
            ('FIRST_WIN', 'First Blood', 'Win your first game', '🎯', 'lifetime_wins', 1, 10, 50),
            ('FIVE_WINS', 'Getting Started', 'Win 5 games', '⭐', 'lifetime_wins', 5, 20, 100),
            ('TEN_WINS', 'Competitor', 'Win 10 games', '🏅', 'lifetime_wins', 10, 30, 150),
            ('FIFTY_WINS', 'Veteran', 'Win 50 games', '🎖️', 'lifetime_wins', 50, 100, 500),
            ('KING_FIVE', 'Hot Streak', 'Hold the table 5 games in a row', '🔥', 'king_streak', 5, 50, 200),
            ('KING_TEN', 'Dynasty', 'Hold the table 10 games in a row', '🏰', 'king_streak', 10, 100, 500),
            ('HOT_STREAK', 'Hot Hand', 'Win 5 games in one night', '🔥', 'daily_wins', 5, 50, 200),
            ('NIGHT_OWL', 'Night Owl', 'Win a game after midnight', '🌙', 'late_win', 1, 20, 50),
            ('REGULAR', 'Regular', 'Play 20 games at one bar', '🏠', 'bar_games', 20, 50, 200),
            ('BAR_HOPPER', 'Bar Hopper', 'Play at 5 different bars', '🍺', 'unique_bars', 5, 50, 200),
            ('RANKED_GRINDER', 'Ranked Grinder', 'Play 20 ranked games', '🏆', 'ranked_games', 20, 50, 200),
            ('SILVER_DIVISION', 'Silver Status', 'Reach Silver division', '🥈', 'division', 1100, 30, 100),
            ('GOLD_DIVISION', 'Gold Status', 'Reach Gold division', '🥇', 'division', 1300, 50, 200),
            ('PLATINUM_DIVISION', 'Platinum Status', 'Reach Platinum division', '🏆', 'division', 1500, 100, 500),
            ('DIAMOND_DIVISION', 'Diamond Status', 'Reach Diamond division', '💎', 'division', 1700, 200, 1000),
            ('SOCIAL_BUTTERFLY', 'Social Butterfly', 'Add 10 friends', '🦋', 'friends', 10, 30, 100),
            ('CHALLENGER', 'Challenger', 'Send 10 challenges', '⚔️', 'challenges_sent', 10, 30, 100),
        ]
        cursor.executemany('''INSERT INTO achievements_catalog 
            (code, name, description, icon, condition_type, condition_value, token_reward, xp_reward) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', achievements)
    
    # Seed survey questions
    cursor.execute('SELECT COUNT(*) FROM survey_questions')
    if cursor.fetchone()[0] == 0:
        questions = [
            (None, "What's your go-to drink when playing pool?", 'single_choice', 
             '["Beer", "Whiskey", "Vodka", "Tequila", "Seltzer", "Wine", "Non-alcoholic"]', 15),
            (None, "How often do you visit bars to play pool?", 'single_choice',
             '["Weekly", "2-3 times a month", "Monthly", "Occasionally"]', 10),
            (None, "What matters most when choosing a bar?", 'single_choice',
             '["Pool table quality", "Drink prices", "Atmosphere", "Friends go there", "Location"]', 15),
            (1, "How often do you order Guinness?", 'single_choice',
             '["Never", "Rarely", "Sometimes", "Often", "Almost every time"]', 20),
            (None, "Do promotions on screens influence what you order?", 'single_choice',
             '["Yes, often", "Sometimes", "Rarely", "Never"]', 15),
            (None, "Which hard seltzers do you like?", 'multi_choice',
             '["White Claw", "Truly", "High Noon", "Topo Chico", "None/Don\'t drink seltzer"]', 20),
            (None, "Would you try a new drink if the Shot Caller recommends it?", 'single_choice',
             '["Definitely", "Probably", "Maybe", "Probably not", "No"]', 15),
            (None, "What time do you usually start playing pool?", 'single_choice',
             '["Before 6pm", "6-8pm", "8-10pm", "After 10pm"]', 10),
            (3, "When choosing whiskey, what matters most?", 'single_choice',
             '["Taste", "Price", "Brand reputation", "Recommendation", "On special"]', 20),
            (None, "How likely are you to join a pool league?", 'scale',
             '{"min": 1, "max": 5, "labels": ["Not likely", "Very likely"]}', 15),
        ]
        cursor.executemany('''INSERT INTO survey_questions 
            (brand_id, text, response_type, options_json, token_reward) 
            VALUES (?, ?, ?, ?, ?)''', questions)
    
    # Seed current season
    cursor.execute('SELECT COUNT(*) FROM seasons WHERE is_active = 1')
    if cursor.fetchone()[0] == 0:
        import datetime
        today = datetime.date.today()
        start = today.replace(day=1)
        if today.month == 12:
            end = today.replace(year=today.year+1, month=1, day=1) - datetime.timedelta(days=1)
        else:
            end = today.replace(month=today.month+1, day=1) - datetime.timedelta(days=1)
        
        cursor.execute('''INSERT INTO seasons (name, start_date, end_date, is_active) 
                          VALUES (?, ?, ?, 1)''', 
                       (f"{today.strftime('%B %Y')} Season", start, end))
    
    conn.commit()
