"""
Database setup and utilities
"""
import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), 'db', 'pool_queue.db')

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=30000')
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname TEXT NOT NULL,
            phone TEXT,
            total_games INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            tokens_balance INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            partner_name TEXT,
            position INTEGER NOT NULL,
            status TEXT DEFAULT 'waiting',
            wins_on_table INTEGER DEFAULT 0,
            session_token TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS game_rules (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            rule_type TEXT DEFAULT 'bar_rules',
            game_type TEXT DEFAULT 'singles',
            custom_note TEXT,
            set_by_player_id INTEGER,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('INSERT OR IGNORE INTO game_rules (id) VALUES (1)')
    
    # Game history for timing
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS game_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            winner_id INTEGER,
            loser_id INTEGER,
            duration_seconds INTEGER,
            played_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Action history for undo
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
            expires_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            undone INTEGER DEFAULT 0
        )
    ''')
    
    # Settings
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            bar_name TEXT DEFAULT 'Pool Cue',
            ad_rotation_seconds INTEGER DEFAULT 10,
            current_game_start DATETIME
        )
    ''')
    cursor.execute('INSERT OR IGNORE INTO settings (id) VALUES (1)')

    # Token transactions for tracking all token activity
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS token_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            reason TEXT NOT NULL,
            details TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    ''')

    # Post-session surveys for spend tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS post_session_surveys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER,
            bar_id INTEGER,
            spend_amount REAL,
            rating INTEGER,
            session_duration_mins INTEGER,
            games_played INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id),
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        )
    ''')

    # POS credentials table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pos_credentials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            access_token TEXT,
            refresh_token TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(bar_id, provider),
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        )
    ''')

    # POS checks - normalized check/order data from any POS provider
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pos_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            external_check_id TEXT NOT NULL,
            opened_at TEXT,
            closed_at TEXT,
            business_date TEXT,
            total_amount REAL NOT NULL,
            subtotal_amount REAL,
            tax_amount REAL,
            tip_amount REAL,
            service_charge REAL,
            guest_count INTEGER,
            server_name TEXT,
            source TEXT,
            raw_payload TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        )
    ''')
    # Indexes for pos_checks
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_pos_checks_unique ON pos_checks(bar_id, provider, external_check_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pos_checks_business_date ON pos_checks(bar_id, business_date)')

    # POS line items - individual items within a check
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pos_line_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pos_check_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            item_category TEXT,
            item_sku TEXT,
            quantity REAL NOT NULL,
            unit_price REAL NOT NULL,
            total_price REAL NOT NULL,
            is_voided INTEGER DEFAULT 0,
            FOREIGN KEY (pos_check_id) REFERENCES pos_checks(id)
        )
    ''')
    # Indexes for pos_line_items
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pos_line_items_check ON pos_line_items(pos_check_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pos_line_items_name ON pos_line_items(item_name)')

    # POS brand mapping - map POS item names to normalized brands
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pos_brand_map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id INTEGER,
            provider TEXT,
            item_name_pattern TEXT NOT NULL,
            item_sku TEXT,
            normalized_brand TEXT NOT NULL,
            normalized_product TEXT,
            category TEXT,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        )
    ''')
    # Indexes for pos_brand_map
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pos_brand_map_brand ON pos_brand_map(normalized_brand)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pos_brand_map_bar ON pos_brand_map(bar_id, provider)')

    # POS daily summary - aggregated daily metrics per bar
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pos_day_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id INTEGER NOT NULL,
            business_date TEXT NOT NULL,
            total_checks INTEGER NOT NULL,
            total_revenue REAL NOT NULL,
            avg_check_amount REAL NOT NULL,
            total_guest_count INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        )
    ''')
    # Index for pos_day_summary
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_pos_day_summary_unique ON pos_day_summary(bar_id, business_date)')

    # App settings - global configuration key/value store
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # Player invites - track SMS/email invites to guest players
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            bar_id INTEGER NOT NULL,
            invite_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            sent_at TEXT,
            accepted_at TEXT,
            error_message TEXT,
            UNIQUE(player_id, bar_id, invite_type),
            FOREIGN KEY (player_id) REFERENCES players(id),
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_player_invites_status ON player_invites(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_player_invites_bar ON player_invites(bar_id)')

    # Cue Marketplace - players can list and buy pool cues with tokens
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cue_marketplace_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_player_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            condition TEXT DEFAULT 'Good',
            price_tokens INTEGER NOT NULL,
            status TEXT DEFAULT 'active',
            buyer_player_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            sold_at TEXT,
            FOREIGN KEY (seller_player_id) REFERENCES players(id),
            FOREIGN KEY (buyer_player_id) REFERENCES players(id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cue_marketplace_status ON cue_marketplace_listings(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cue_marketplace_seller ON cue_marketplace_listings(seller_player_id)')

    # Referrals table - for invite friends feature
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_user_id INTEGER NOT NULL,
            referred_user_id INTEGER,
            referral_code TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            reward_given INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            FOREIGN KEY (referrer_user_id) REFERENCES players(id),
            FOREIGN KEY (referred_user_id) REFERENCES players(id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_referrals_code ON referrals(referral_code)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_referrals_referred ON referrals(referred_user_id)')

    # Manual invites table - track invites sent via email/phone before signup
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS manual_invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            contact_type TEXT NOT NULL,
            contact_value TEXT NOT NULL,
            contact_name TEXT,
            referral_code TEXT NOT NULL,
            status TEXT DEFAULT 'sent',
            sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
            send_count INTEGER DEFAULT 1,
            opened_at TEXT,
            signed_up_player_id INTEGER,
            completed_at TEXT,
            FOREIGN KEY (sender_id) REFERENCES players(id),
            FOREIGN KEY (signed_up_player_id) REFERENCES players(id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_manual_invites_sender ON manual_invites(sender_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_manual_invites_contact ON manual_invites(contact_type, contact_value)')

    # Ranked windows table - bar-level time-based ranked periods
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ranked_windows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id INTEGER NOT NULL,
            title TEXT,
            start_datetime TEXT NOT NULL,
            end_datetime TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bar_id) REFERENCES bars(id),
            FOREIGN KEY (created_by) REFERENCES players(id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ranked_windows_bar ON ranked_windows(bar_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ranked_windows_datetime ON ranked_windows(start_datetime, end_datetime)')

    # Pool Nights table - organized pool events at bars
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pool_nights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id INTEGER NOT NULL,
            host_id INTEGER NOT NULL,
            title TEXT,
            event_date DATE NOT NULL,
            start_time TEXT,
            end_time TEXT,
            game_type TEXT DEFAULT 'singles',
            access_type TEXT DEFAULT 'open',
            description TEXT,
            max_players INTEGER,
            entry_fee REAL DEFAULT 0.00,
            prize_pool REAL DEFAULT 0.00,
            ranked_required INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            approved_at DATETIME,
            cancelled_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bar_id) REFERENCES bars(id),
            FOREIGN KEY (host_id) REFERENCES players(id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pool_nights_bar ON pool_nights(bar_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pool_nights_date ON pool_nights(event_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pool_nights_status ON pool_nights(status)')

    # Pool Night RSVPs/Registrations - tracks player registrations for pool nights
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pool_night_rsvps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pool_night_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            status TEXT DEFAULT 'going',
            paid INTEGER DEFAULT 0,
            amount_paid REAL DEFAULT 0.00,
            refunded INTEGER DEFAULT 0,
            refunded_at DATETIME,
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
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_rsvp_player ON pool_night_rsvps(player_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_rsvp_night ON pool_night_rsvps(pool_night_id)')

    # Player RSVP Stats - aggregated reliability tracking
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
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_rsvp_stats_player ON player_rsvp_stats(player_id)')

    # Unique indexes for account uniqueness (email and phone)
    # Using partial indexes to only enforce uniqueness when values are not null
    try:
        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_players_email_unique ON players(email) WHERE email IS NOT NULL AND email != ""')
    except Exception:
        pass
    try:
        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_players_phone_unique ON players(phone_number) WHERE phone_number IS NOT NULL AND phone_number != ""')
    except Exception:
        pass

    # Migrations
    for sql in [
        'ALTER TABLE queue ADD COLUMN wins_on_table INTEGER DEFAULT 0',
        'ALTER TABLE queue ADD COLUMN session_token TEXT',
        'ALTER TABLE queue ADD COLUMN partner_name TEXT',
        'ALTER TABLE settings ADD COLUMN current_game_start DATETIME',
        'ALTER TABLE action_history ADD COLUMN expires_at DATETIME',
        'ALTER TABLE settings ADD COLUMN board_style TEXT DEFAULT \'classic\'',
        'ALTER TABLE settings ADD COLUMN permanent_rules INTEGER DEFAULT 0',
        'ALTER TABLE settings ADD COLUMN address TEXT',
        'ALTER TABLE settings ADD COLUMN city TEXT',
        'ALTER TABLE settings ADD COLUMN state TEXT',
        'ALTER TABLE settings ADD COLUMN zip_code TEXT',
        'ALTER TABLE settings ADD COLUMN table_count INTEGER DEFAULT 1',
        'ALTER TABLE settings ADD COLUMN google_review_url TEXT',
        'ALTER TABLE settings ADD COLUMN base_match_minutes INTEGER DEFAULT 8',
        'ALTER TABLE players ADD COLUMN email TEXT',
        'ALTER TABLE players ADD COLUMN password_hash TEXT',
        'ALTER TABLE players ADD COLUMN session_token TEXT',
        'ALTER TABLE players ADD COLUMN tokens_balance INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN tokens_earned INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN tokens_spent INTEGER DEFAULT 0',
        # Guest vs Account distinction
        'ALTER TABLE players ADD COLUMN account_id INTEGER DEFAULT NULL',
        'ALTER TABLE players ADD COLUMN phone_number TEXT DEFAULT NULL',
        'ALTER TABLE players ADD COLUMN invite_opt_out INTEGER DEFAULT 0',
        # POS integration columns
        'ALTER TABLE bars ADD COLUMN pos_provider TEXT DEFAULT NULL',
        'ALTER TABLE bars ADD COLUMN pos_location_id TEXT DEFAULT NULL',
        "ALTER TABLE bars ADD COLUMN pos_integration_status TEXT DEFAULT 'not_configured'",
        # Auto-invites
        'ALTER TABLE bars ADD COLUMN auto_invites_enabled INTEGER DEFAULT 0',
        # Bar location details for demographics
        'ALTER TABLE bars ADD COLUMN borough TEXT DEFAULT NULL',
        'ALTER TABLE bars ADD COLUMN neighborhood TEXT DEFAULT NULL',
        # Birthday feature
        'ALTER TABLE players ADD COLUMN birthday TEXT',
        'ALTER TABLE players ADD COLUMN last_birthday_rewarded_at TEXT',
        'ALTER TABLE players ADD COLUMN birthday_last_changed_at TEXT',
        # Demographics for signup/personalization
        'ALTER TABLE players ADD COLUMN age_range TEXT DEFAULT NULL',
        'ALTER TABLE players ADD COLUMN gender TEXT DEFAULT NULL',
        # Referral feature
        'ALTER TABLE players ADD COLUMN referral_code TEXT',
        'ALTER TABLE players ADD COLUMN referred_by_user_id INTEGER',
        'ALTER TABLE players ADD COLUMN referral_rewards_today INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN last_referral_reward_date TEXT',
        # Ranked match feature - game_history
        'ALTER TABLE game_history ADD COLUMN is_ranked INTEGER DEFAULT 0',
        "ALTER TABLE game_history ADD COLUMN ranked_source TEXT DEFAULT NULL",
        # Ranked match feature - queue
        'ALTER TABLE queue ADD COLUMN ranked_request INTEGER DEFAULT 0',
        'ALTER TABLE queue ADD COLUMN ranked_accepted INTEGER DEFAULT NULL',
        'ALTER TABLE queue ADD COLUMN opponent_player_id INTEGER DEFAULT NULL',
        # Wallet/Balance feature - players
        'ALTER TABLE players ADD COLUMN wallet_balance REAL DEFAULT 0.00',
        'ALTER TABLE players ADD COLUMN payment_customer_id TEXT DEFAULT NULL',
        'ALTER TABLE players ADD COLUMN payout_method_id TEXT DEFAULT NULL',
        # Marketplace - price in tokens or cash
        'ALTER TABLE cue_marketplace_listings ADD COLUMN price_cash REAL DEFAULT NULL',
        "ALTER TABLE cue_marketplace_listings ADD COLUMN price_type TEXT DEFAULT 'tokens'",
        # Tournament feature - pool_nights
        "ALTER TABLE pool_nights ADD COLUMN format TEXT DEFAULT 'casual'",
        "ALTER TABLE pool_nights ADD COLUMN elimination_type TEXT DEFAULT 'single'",
        "ALTER TABLE pool_nights ADD COLUMN seeding_method TEXT DEFAULT 'random'",
        'ALTER TABLE pool_nights ADD COLUMN bracket_size INTEGER DEFAULT NULL',
        "ALTER TABLE pool_nights ADD COLUMN tournament_status TEXT DEFAULT NULL",
        'ALTER TABLE pool_nights ADD COLUMN registration_deadline DATETIME DEFAULT NULL',
        'ALTER TABLE pool_nights ADD COLUMN bracket_generated INTEGER DEFAULT 0',
        'ALTER TABLE pool_nights ADD COLUMN current_round INTEGER DEFAULT 0',
        'ALTER TABLE pool_nights ADD COLUMN race_to INTEGER DEFAULT 1',
        # Player profile enhancements for marketing/personalization
        'ALTER TABLE players ADD COLUMN display_name TEXT DEFAULT NULL',
        "ALTER TABLE players ADD COLUMN play_frequency TEXT DEFAULT NULL",
        'ALTER TABLE players ADD COLUMN marketing_opt_in INTEGER DEFAULT 1',
        "ALTER TABLE players ADD COLUMN preferred_contact_method TEXT DEFAULT 'email'",
        # Phone/email verification fields
        'ALTER TABLE players ADD COLUMN phone_verified INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN email_verified INTEGER DEFAULT 0',
        'ALTER TABLE players ADD COLUMN phone_verification_sent_at TEXT DEFAULT NULL',
        'ALTER TABLE players ADD COLUMN email_verification_sent_at TEXT DEFAULT NULL',
        # Account status for soft delete
        'ALTER TABLE players ADD COLUMN is_active INTEGER DEFAULT 1',
        'ALTER TABLE players ADD COLUMN deactivated_at TEXT DEFAULT NULL',
        'ALTER TABLE players ADD COLUMN deactivated_by INTEGER DEFAULT NULL',
    ]:
        try:
            cursor.execute(sql)
        except sqlite3.OperationalError:
            pass
    
    # Create unique indexes on email and phone_number (where not null)
    try:
        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_players_email ON players(email) WHERE email IS NOT NULL AND email != ""')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_players_phone ON players(phone_number) WHERE phone_number IS NOT NULL AND phone_number != ""')
    except sqlite3.OperationalError:
        pass
    
    # Bar tables - individual pool tables at each bar for table-specific QR codes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bar_tables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id INTEGER NOT NULL,
            table_number INTEGER NOT NULL,
            table_name TEXT,
            qr_code_token TEXT UNIQUE,
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bar_id) REFERENCES bars(id),
            UNIQUE(bar_id, table_number)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bar_tables_bar ON bar_tables(bar_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bar_tables_token ON bar_tables(qr_code_token)')
    
    # Add table_id to queue and active_matches if not exists
    for migration in [
        'ALTER TABLE queue ADD COLUMN table_id INTEGER DEFAULT NULL',
        'ALTER TABLE active_matches ADD COLUMN table_id INTEGER DEFAULT NULL',
    ]:
        try:
            cursor.execute(migration)
        except sqlite3.OperationalError:
            pass
    
    # Admin audit log table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_user_id INTEGER,
            admin_type TEXT DEFAULT 'master',
            target_user_id INTEGER,
            action TEXT NOT NULL,
            details TEXT,
            old_values TEXT,
            new_values TEXT,
            ip_address TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (admin_user_id) REFERENCES players(id),
            FOREIGN KEY (target_user_id) REFERENCES players(id)
        )
    ''')
    
    # Create wallet_transactions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS wallet_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            transaction_type TEXT NOT NULL,
            description TEXT,
            pool_night_id INTEGER DEFAULT NULL,
            game_id INTEGER DEFAULT NULL,
            stripe_payment_id TEXT DEFAULT NULL,
            balance_before REAL,
            balance_after REAL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id),
            FOREIGN KEY (pool_night_id) REFERENCES pool_nights(id)
        )
    ''')
    
    # Create pool_night_payouts table for tracking winnings distribution
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pool_night_payouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pool_night_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            placement INTEGER,
            amount REAL NOT NULL,
            paid_out INTEGER DEFAULT 0,
            paid_out_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (pool_night_id) REFERENCES pool_nights(id),
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    ''')
    
    # Verifications table for phone/email verification codes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS verifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            channel TEXT NOT NULL,
            destination TEXT NOT NULL,
            code TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            attempts INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            verified_at DATETIME DEFAULT NULL,
            expires_at DATETIME NOT NULL,
            FOREIGN KEY (user_id) REFERENCES players(id)
        )
    ''')
    
    # ========== ANTI-TAMPERING SYSTEM TABLES ==========
    
    # Active matches - Server source of truth for ongoing games
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS active_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id INTEGER NOT NULL,
            player1_id INTEGER NOT NULL,
            player2_id INTEGER NOT NULL,
            player1_queue_id INTEGER,
            player2_queue_id INTEGER,
            is_ranked INTEGER DEFAULT 0,
            ranked_source TEXT,
            pool_night_id INTEGER DEFAULT NULL,
            entry_fee REAL DEFAULT 0,
            status TEXT DEFAULT 'in_progress',
            result_winner_id INTEGER DEFAULT NULL,
            result_confirmed INTEGER DEFAULT 0,
            result_locked INTEGER DEFAULT 0,
            player1_confirmed INTEGER DEFAULT 0,
            player2_confirmed INTEGER DEFAULT 0,
            host_confirmed INTEGER DEFAULT 0,
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            ended_at DATETIME,
            created_by_user_id INTEGER,
            FOREIGN KEY (bar_id) REFERENCES bars(id),
            FOREIGN KEY (player1_id) REFERENCES players(id),
            FOREIGN KEY (player2_id) REFERENCES players(id),
            FOREIGN KEY (pool_night_id) REFERENCES pool_nights(id)
        )
    ''')
    
    # Match audit log - Track all sensitive match actions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS match_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER,
            game_history_id INTEGER,
            bar_id INTEGER,
            action TEXT NOT NULL,
            details TEXT,
            performed_by_user_id INTEGER,
            performed_by_type TEXT DEFAULT 'system',
            ip_address TEXT,
            user_agent TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (match_id) REFERENCES active_matches(id),
            FOREIGN KEY (game_history_id) REFERENCES game_history(id),
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        )
    ''')
    
    # Board sessions - Authorized controllers for bar boards
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS board_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id INTEGER NOT NULL,
            session_token TEXT NOT NULL UNIQUE,
            authorized_by_user_id INTEGER,
            device_name TEXT,
            is_active INTEGER DEFAULT 1,
            can_control INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_activity_at DATETIME,
            expires_at DATETIME,
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        )
    ''')
    
    # Tournament participants table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tournament_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pool_night_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            seed INTEGER DEFAULT 0,
            status TEXT DEFAULT 'registered',
            eliminated INTEGER DEFAULT 0,
            eliminated_round INTEGER DEFAULT NULL,
            final_placement INTEGER DEFAULT NULL,
            registered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            checked_in INTEGER DEFAULT 0,
            checked_in_at DATETIME DEFAULT NULL,
            FOREIGN KEY (pool_night_id) REFERENCES pool_nights(id),
            FOREIGN KEY (player_id) REFERENCES players(id),
            UNIQUE(pool_night_id, player_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tournament_participants_night ON tournament_participants(pool_night_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tournament_participants_player ON tournament_participants(player_id)')
    
    # Tournament matches table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tournament_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pool_night_id INTEGER NOT NULL,
            round_number INTEGER NOT NULL,
            match_number INTEGER NOT NULL,
            bracket_position TEXT DEFAULT 'winners',
            player1_id INTEGER DEFAULT NULL,
            player2_id INTEGER DEFAULT NULL,
            player1_seed INTEGER DEFAULT NULL,
            player2_seed INTEGER DEFAULT NULL,
            winner_id INTEGER DEFAULT NULL,
            loser_id INTEGER DEFAULT NULL,
            player1_score INTEGER DEFAULT 0,
            player2_score INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            scheduled_time DATETIME DEFAULT NULL,
            started_at DATETIME DEFAULT NULL,
            completed_at DATETIME DEFAULT NULL,
            next_match_id INTEGER DEFAULT NULL,
            loser_next_match_id INTEGER DEFAULT NULL,
            is_bye INTEGER DEFAULT 0,
            forfeit INTEGER DEFAULT 0,
            forfeit_player_id INTEGER DEFAULT NULL,
            game_history_id INTEGER DEFAULT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (pool_night_id) REFERENCES pool_nights(id),
            FOREIGN KEY (player1_id) REFERENCES players(id),
            FOREIGN KEY (player2_id) REFERENCES players(id),
            FOREIGN KEY (winner_id) REFERENCES players(id),
            FOREIGN KEY (next_match_id) REFERENCES tournament_matches(id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tournament_matches_night ON tournament_matches(pool_night_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tournament_matches_round ON tournament_matches(pool_night_id, round_number)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tournament_matches_status ON tournament_matches(status)')
    
    # Queue usage log - tracks every queue join by phone number
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS queue_usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT NOT NULL,
            bar_id INTEGER NOT NULL,
            player_id INTEGER,
            nickname TEXT,
            had_account INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bar_id) REFERENCES bars(id),
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_queue_usage_phone ON queue_usage_log(phone_number)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_queue_usage_bar ON queue_usage_log(bar_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_queue_usage_date ON queue_usage_log(created_at)')
    
    # Auto invites - tracks automatic invites sent to frequent queue users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS auto_invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT NOT NULL,
            bar_id INTEGER,
            threshold_met INTEGER DEFAULT 3,
            queue_count INTEGER DEFAULT 0,
            invite_token TEXT UNIQUE,
            status TEXT DEFAULT 'pending',
            invited_at DATETIME,
            opened_at DATETIME,
            signed_up_player_id INTEGER,
            signed_up_at DATETIME,
            sms_sent INTEGER DEFAULT 0,
            sms_error TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bar_id) REFERENCES bars(id),
            FOREIGN KEY (signed_up_player_id) REFERENCES players(id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_auto_invites_phone ON auto_invites(phone_number)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_auto_invites_status ON auto_invites(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_auto_invites_token ON auto_invites(invite_token)')
    
    conn.commit()
    conn.close()


# ============================================
# BAR TABLES MANAGEMENT (Table-specific QR codes)
# ============================================

def generate_table_token():
    """Generate a unique token for table QR codes."""
    import secrets
    return secrets.token_urlsafe(8)  # Short but unique

def ensure_bar_tables(bar_id, table_count=None):
    """
    Ensure a bar has the correct number of table records.
    Creates tables if missing, deactivates excess tables.
    Returns list of active tables.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Get bar's table_count if not provided
    if table_count is None:
        cursor.execute('SELECT table_count FROM bars WHERE id = ?', (bar_id,))
        row = cursor.fetchone()
        table_count = row['table_count'] if row else 1
    
    # Get existing tables
    cursor.execute('SELECT * FROM bar_tables WHERE bar_id = ? ORDER BY table_number', (bar_id,))
    existing = {t['table_number']: dict(t) for t in cursor.fetchall()}
    
    tables = []
    for num in range(1, table_count + 1):
        if num in existing:
            # Ensure active
            if not existing[num]['is_active']:
                cursor.execute('UPDATE bar_tables SET is_active = 1 WHERE id = ?', (existing[num]['id'],))
            # Ensure has token
            if not existing[num]['qr_code_token']:
                token = generate_table_token()
                cursor.execute('UPDATE bar_tables SET qr_code_token = ? WHERE id = ?', (token, existing[num]['id']))
                existing[num]['qr_code_token'] = token
            tables.append(existing[num])
        else:
            # Create new table
            token = generate_table_token()
            cursor.execute('''
                INSERT INTO bar_tables (bar_id, table_number, table_name, qr_code_token, is_active)
                VALUES (?, ?, ?, ?, 1)
            ''', (bar_id, num, f'Table {num}', token))
            tables.append({
                'id': cursor.lastrowid,
                'bar_id': bar_id,
                'table_number': num,
                'table_name': f'Table {num}',
                'qr_code_token': token,
                'is_active': 1
            })
    
    # Deactivate excess tables
    for num, table in existing.items():
        if num > table_count:
            cursor.execute('UPDATE bar_tables SET is_active = 0 WHERE id = ?', (table['id'],))
    
    conn.commit()
    conn.close()
    return tables

def get_bar_tables(bar_id, active_only=True):
    """Get all tables for a bar."""
    conn = get_db()
    cursor = conn.cursor()
    if active_only:
        cursor.execute('SELECT * FROM bar_tables WHERE bar_id = ? AND is_active = 1 ORDER BY table_number', (bar_id,))
    else:
        cursor.execute('SELECT * FROM bar_tables WHERE bar_id = ? ORDER BY table_number', (bar_id,))
    tables = [dict(t) for t in cursor.fetchall()]
    conn.close()
    return tables

def get_table_by_token(token):
    """Look up a table by its QR code token. Returns table with bar info."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT t.*, b.name as bar_name, b.address as bar_address
        FROM bar_tables t
        JOIN bars b ON t.bar_id = b.id
        WHERE t.qr_code_token = ? AND t.is_active = 1
    ''', (token,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_table_by_id(table_id):
    """Get table by ID with bar info."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT t.*, b.name as bar_name, b.address as bar_address
        FROM bar_tables t
        JOIN bars b ON t.bar_id = b.id
        WHERE t.id = ?
    ''', (table_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def regenerate_table_token(table_id):
    """Generate a new QR token for a table (if compromised)."""
    conn = get_db()
    cursor = conn.cursor()
    token = generate_table_token()
    cursor.execute('UPDATE bar_tables SET qr_code_token = ? WHERE id = ?', (token, table_id))
    conn.commit()
    conn.close()
    return token


def get_settings():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM settings WHERE id = 1')
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}

def update_settings(**kwargs):
    conn = get_db()
    cursor = conn.cursor()
    for key, value in kwargs.items():
        cursor.execute(f'UPDATE settings SET {key} = ? WHERE id = 1', (value,))
    conn.commit()
    conn.close()

def start_game_timer():
    from datetime import timezone
    conn = get_db()
    cursor = conn.cursor()
    # Use UTC to match SQLite datetime('now') and end_game_timer
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    cursor.execute('UPDATE settings SET current_game_start = ? WHERE id = 1', (now_utc,))
    conn.commit()
    conn.close()

def end_game_timer():
    """End current game and return duration in seconds."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT current_game_start FROM settings WHERE id = 1')
    row = cursor.fetchone()
    duration = None  # None means timer wasn't running, will skip anti-spam check
    if row and row['current_game_start']:
        try:
            start_str = row['current_game_start']
            # Handle both ISO format and SQLite datetime format
            if 'T' in start_str:
                start = datetime.fromisoformat(start_str.replace('Z', '+00:00').split('+')[0])
            else:
                start = datetime.fromisoformat(start_str)
            # Use UTC for comparison since SQLite datetime('now') is UTC
            from datetime import timezone
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
            duration = int((now_utc - start).total_seconds())
            # Ensure non-negative - if negative, timer was corrupted
            if duration < 0:
                duration = None  # Skip anti-spam check
        except Exception as e:
            print(f"Error parsing game timer: {e}")
            duration = None
    cursor.execute('UPDATE settings SET current_game_start = NULL WHERE id = 1')
    conn.commit()
    conn.close()
    return duration


def record_game(winner_id, loser_id, duration_seconds):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO game_history (winner_id, loser_id, duration_seconds) VALUES (?, ?, ?)',
                   (winner_id, loser_id, duration_seconds))
    
    # Update cached stats in players table (source of truth is game_history)
    cursor.execute('UPDATE players SET wins = wins + 1, total_games = total_games + 1 WHERE id = ?', (winner_id,))
    cursor.execute('UPDATE players SET losses = losses + 1, total_games = total_games + 1 WHERE id = ?', (loser_id,))
    
    conn.commit()
    conn.close()
    
    # Check if this is the first game for either player and complete their referral
    _check_first_game_referral(winner_id)
    _check_first_game_referral(loser_id)


def _check_first_game_referral(player_id):
    """Check if this is a player's first game and complete their referral if so."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Count total games for this player
    cursor.execute('''
        SELECT COUNT(*) as game_count 
        FROM game_history 
        WHERE winner_id = ? OR loser_id = ?
    ''', (player_id, player_id))
    result = cursor.fetchone()
    game_count = result['game_count'] if result else 0
    
    # Only process if this is their first game
    if game_count == 1:
        # Check for pending referral
        cursor.execute('''
            SELECT id FROM referrals 
            WHERE referred_user_id = ? AND status = 'pending' AND reward_given = 0
        ''', (player_id,))
        if cursor.fetchone():
            conn.close()
            # Complete the referral (function handles its own connection)
            complete_referral_reward(player_id)
            return
    
    conn.close()

def get_average_game_time():
    """Get average game time from last 20 games."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT AVG(duration_seconds) as avg FROM (SELECT duration_seconds FROM game_history WHERE duration_seconds > 30 ORDER BY played_at DESC LIMIT 20)')
    row = cursor.fetchone()
    conn.close()
    return int(row['avg']) if row and row['avg'] else 0

def get_game_rules():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM game_rules WHERE id = 1')
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {'rule_type': 'bar_rules', 'game_type': 'singles'}

def set_game_rules(rule_type, game_type, custom_note, player_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE game_rules SET rule_type = ?, game_type = ?, custom_note = ?, set_by_player_id = ?, updated_at = ? WHERE id = 1',
                   (rule_type, game_type, custom_note, player_id, datetime.now()))
    conn.commit()
    conn.close()

def log_action(action_type, player_id=None, player_nickname=None, partner_name=None, queue_id=None, position=None, wins_on_table=None):
    conn = get_db()
    cursor = conn.cursor()
    expires_at = datetime.now() + timedelta(minutes=1)
    cursor.execute('INSERT INTO action_history (action_type, player_id, player_nickname, partner_name, queue_id, position, wins_on_table, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                   (action_type, player_id, player_nickname, partner_name, queue_id, position, wins_on_table, expires_at))
    conn.commit()
    conn.close()

def get_last_removal():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM action_history WHERE action_type = "remove" AND undone = 0 AND expires_at > ? ORDER BY created_at DESC LIMIT 1', (datetime.now(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def mark_action_undone(action_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE action_history SET undone = 1 WHERE id = ?', (action_id,))
    conn.commit()
    conn.close()

def get_current_rules(bar_id=1):
    """Get current rules based on scheduled rules and time."""
    from datetime import datetime
    
    conn = get_db()
    cursor = conn.cursor()
    
    now = datetime.now()
    current_day = now.weekday()  # 0=Monday, 6=Sunday
    current_time = now.strftime('%H:%M')
    
    # Check for scheduled rule at this time
    cursor.execute('''
        SELECT game_type, rule_type FROM scheduled_rules
        WHERE bar_id = ? AND day_of_week = ? AND is_active = 1
        AND (
            (start_time <= end_time AND ? >= start_time AND ? < end_time)
            OR (start_time > end_time AND (? >= start_time OR ? < end_time))
        )
        ORDER BY id DESC LIMIT 1
    ''', (bar_id, current_day, current_time, current_time, current_time, current_time))
    
    scheduled = cursor.fetchone()
    
    if scheduled:
        conn.close()
        return {'game_type': scheduled[0], 'rule_type': scheduled[1], 'is_scheduled': True}
    
    # Fall back to default rules
    cursor.execute('SELECT game_type, rule_type FROM game_rules WHERE bar_id = ? ORDER BY id DESC LIMIT 1', (bar_id,))
    default = cursor.fetchone()
    conn.close()
    
    if default:
        return {'game_type': default[0], 'rule_type': default[1], 'is_scheduled': False}
    
    return {'game_type': 'singles', 'rule_type': 'bar_rules', 'is_scheduled': False}

def get_scheduled_rules(bar_id=1):
    """Get all scheduled rules for a bar."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, day_of_week, start_time, end_time, game_type, rule_type, is_active
        FROM scheduled_rules WHERE bar_id = ? ORDER BY day_of_week, start_time
    ''', (bar_id,))
    rules = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rules

def add_scheduled_rule(bar_id, day_of_week, start_time, end_time, game_type, rule_type='bar_rules'):
    """Add a scheduled rule."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO scheduled_rules (bar_id, day_of_week, start_time, end_time, game_type, rule_type)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (bar_id, day_of_week, start_time, end_time, game_type, rule_type))
    conn.commit()
    rule_id = cursor.lastrowid
    conn.close()
    return rule_id

def delete_scheduled_rule(rule_id):
    """Delete a scheduled rule."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM scheduled_rules WHERE id = ?', (rule_id,))
    conn.commit()
    conn.close()


# ============ POOL NIGHTS HELPERS ============

def get_pool_nights_summary(start_date=None, end_date=None, bar_id=None):
    """
    Get summary of pool nights activity by aggregating game_history by bar and date.
    
    Args:
        start_date: str 'YYYY-MM-DD' (optional)
        end_date: str 'YYYY-MM-DD' (optional)
        bar_id: int (optional)
        
    Returns:
        list of dicts with bar_id, bar_name, date, games_count, unique_players, total_revenue
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Build dynamic WHERE clause
    conditions = []
    params = []
    
    if start_date:
        conditions.append("date(g.played_at) >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("date(g.played_at) <= ?")
        params.append(end_date)
    if bar_id:
        conditions.append("g.bar_id = ?")
        params.append(bar_id)
    
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    # Get game activity grouped by bar and date
    query = f'''
        SELECT 
            g.bar_id,
            b.name as bar_name,
            date(g.played_at) as night_date,
            COUNT(*) as games_count,
            COUNT(DISTINCT g.winner_id) + COUNT(DISTINCT g.loser_id) as player_touches
        FROM game_history g
        LEFT JOIN bars b ON g.bar_id = b.id
        {where_clause}
        GROUP BY g.bar_id, date(g.played_at)
        ORDER BY date(g.played_at) DESC, g.bar_id
    '''
    
    cursor.execute(query, params)
    nights = []
    
    for row in cursor.fetchall():
        night = {
            'bar_id': row['bar_id'],
            'bar_name': row['bar_name'] or f"Bar #{row['bar_id']}",
            'date': row['night_date'],
            'games_count': row['games_count'],
            'unique_players': row['player_touches'],  # Approximation
            'total_revenue': None
        }
        nights.append(night)
    
    # Try to join POS revenue if pos_checks table exists
    try:
        for night in nights:
            cursor.execute('''
                SELECT COALESCE(SUM(total_amount), 0) as revenue
                FROM pos_checks
                WHERE bar_id = ? AND business_date = ?
            ''', (night['bar_id'], night['date']))
            pos_row = cursor.fetchone()
            if pos_row and pos_row['revenue'] > 0:
                night['total_revenue'] = round(pos_row['revenue'], 2)
    except Exception:
        pass  # pos_checks table might not exist
    
    conn.close()
    return nights


def get_pool_nights_events(status=None, bar_id=None, limit=50):
    """
    Get pool night events from the pool_nights table.
    
    Args:
        status: 'pending', 'approved', 'rejected', 'cancelled', 'upcoming', or None for all
        bar_id: int (optional)
        limit: max results
        
    Returns:
        list of pool night event dicts
    """
    conn = get_db()
    cursor = conn.cursor()
    
    conditions = []
    params = []
    
    if status == 'upcoming':
        # Upcoming = approved and in the future
        conditions.append("pn.status = 'approved'")
        conditions.append("pn.event_date >= date('now')")
    elif status:
        conditions.append("pn.status = ?")
        params.append(status)
    if bar_id:
        conditions.append("pn.bar_id = ?")
        params.append(bar_id)
    
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    # Sort upcoming events by date ASC, others by date DESC
    order_by = "pn.event_date ASC" if status == 'upcoming' else "pn.event_date DESC, pn.created_at DESC"
    
    query = f'''
        SELECT 
            pn.*,
            b.name as bar_name,
            p.nickname as host_name
        FROM pool_nights pn
        LEFT JOIN bars b ON pn.bar_id = b.id
        LEFT JOIN players p ON pn.host_id = p.id
        {where_clause}
        ORDER BY {order_by}
        LIMIT ?
    '''
    params.append(limit)
    
    cursor.execute(query, params)
    events = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return events


def get_pool_nights_stats():
    """
    Get aggregate stats for pool nights dashboard.
    
    Returns:
        dict with total_nights, pending_count, accepted_count, rejected_count, cancelled_count, upcoming_count
    """
    conn = get_db()
    cursor = conn.cursor()
    
    stats = {}
    
    cursor.execute("SELECT COUNT(*) FROM pool_nights")
    stats['total_nights'] = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM pool_nights WHERE status = 'pending'")
    stats['pending_count'] = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM pool_nights WHERE status = 'approved'")
    stats['accepted_count'] = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM pool_nights WHERE status = 'rejected'")
    stats['rejected_count'] = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM pool_nights WHERE status = 'cancelled'")
    stats['cancelled_count'] = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM pool_nights WHERE status = 'approved' AND event_date >= date('now')")
    stats['upcoming_count'] = cursor.fetchone()[0] or 0
    
    conn.close()
    return stats


# ============ TOURNAMENT FUNCTIONS ============

def register_tournament_participant(pool_night_id, player_id):
    """Register a player for a tournament pool night."""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO tournament_participants (pool_night_id, player_id, registered_at)
            VALUES (?, ?, datetime('now'))
        ''', (pool_night_id, player_id))
        conn.commit()
        participant_id = cursor.lastrowid
        conn.close()
        return {'success': True, 'participant_id': participant_id}
    except sqlite3.IntegrityError:
        conn.close()
        return {'success': False, 'error': 'Already registered'}


def get_tournament_participants(pool_night_id):
    """Get all participants for a tournament."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT tp.*, p.nickname, p.rating, p.wins, p.losses
        FROM tournament_participants tp
        JOIN players p ON tp.player_id = p.id
        WHERE tp.pool_night_id = ?
        ORDER BY tp.seed ASC, tp.registered_at ASC
    ''', (pool_night_id,))
    participants = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return participants


def generate_tournament_bracket(pool_night_id, seeding_method='random'):
    """Generate bracket matches for a tournament based on participants."""
    import math
    import random
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get pool night info
    cursor.execute('SELECT * FROM pool_nights WHERE id = ?', (pool_night_id,))
    pool_night = cursor.fetchone()
    if not pool_night:
        conn.close()
        return {'success': False, 'error': 'Pool night not found'}
    
    pool_night = dict(pool_night)
    elimination_type = pool_night.get('elimination_type', 'single')
    
    # Get participants
    cursor.execute('''
        SELECT tp.*, p.rating FROM tournament_participants tp
        JOIN players p ON tp.player_id = p.id
        WHERE tp.pool_night_id = ? AND tp.status = 'registered'
        ORDER BY tp.registered_at ASC
    ''', (pool_night_id,))
    participants = [dict(row) for row in cursor.fetchall()]
    
    if len(participants) < 2:
        conn.close()
        return {'success': False, 'error': 'Need at least 2 participants'}
    
    # Determine bracket size (next power of 2)
    num_players = len(participants)
    bracket_size = 2 ** math.ceil(math.log2(num_players))
    num_byes = bracket_size - num_players
    
    # Seed players
    if seeding_method == 'rating':
        participants.sort(key=lambda x: x.get('rating', 1000), reverse=True)
    else:  # random
        random.shuffle(participants)
    
    # Assign seeds
    for i, p in enumerate(participants):
        cursor.execute('UPDATE tournament_participants SET seed = ? WHERE id = ?', (i + 1, p['id']))
        participants[i]['seed'] = i + 1
    
    # Calculate number of rounds
    num_rounds = int(math.log2(bracket_size))
    
    # Create first round matches with proper seeding
    # Standard bracket seeding: 1v16, 8v9, 5v12, 4v13, 3v14, 6v11, 7v10, 2v15 for 16-player
    def get_seed_order(size):
        if size == 2:
            return [1, 2]
        smaller = get_seed_order(size // 2)
        return [item for pair in zip(smaller, [size + 1 - s for s in smaller]) for item in pair]
    
    seed_order = get_seed_order(bracket_size)
    
    # Create player lookup by seed
    player_by_seed = {p['seed']: p for p in participants}
    
    # Generate first round matches
    first_round_matches = []
    match_number = 1
    for i in range(0, bracket_size, 2):
        seed1 = seed_order[i]
        seed2 = seed_order[i + 1]
        p1 = player_by_seed.get(seed1)
        p2 = player_by_seed.get(seed2)
        
        is_bye = (p1 is None or p2 is None)
        
        cursor.execute('''
            INSERT INTO tournament_matches 
            (pool_night_id, round_number, match_number, bracket_position, 
             player1_id, player2_id, player1_seed, player2_seed, status, is_bye)
            VALUES (?, 1, ?, 'winners', ?, ?, ?, ?, ?, ?)
        ''', (
            pool_night_id, match_number, 
            p1['player_id'] if p1 else None,
            p2['player_id'] if p2 else None,
            seed1 if p1 else None,
            seed2 if p2 else None,
            'completed' if is_bye else 'pending',
            1 if is_bye else 0
        ))
        match_id = cursor.lastrowid
        
        # Auto-advance bye matches
        if is_bye:
            winner_id = p1['player_id'] if p1 else (p2['player_id'] if p2 else None)
            if winner_id:
                cursor.execute('UPDATE tournament_matches SET winner_id = ? WHERE id = ?', (winner_id, match_id))
        
        first_round_matches.append({'id': match_id, 'is_bye': is_bye})
        match_number += 1
    
    # Generate subsequent rounds
    prev_round_matches = first_round_matches
    for round_num in range(2, num_rounds + 1):
        current_round_matches = []
        match_number = 1
        
        for i in range(0, len(prev_round_matches), 2):
            cursor.execute('''
                INSERT INTO tournament_matches 
                (pool_night_id, round_number, match_number, bracket_position, status)
                VALUES (?, ?, ?, 'winners', 'pending')
            ''', (pool_night_id, round_num, match_number))
            match_id = cursor.lastrowid
            current_round_matches.append({'id': match_id})
            
            # Link previous matches to this one
            cursor.execute('UPDATE tournament_matches SET next_match_id = ? WHERE id = ?', 
                          (match_id, prev_round_matches[i]['id']))
            cursor.execute('UPDATE tournament_matches SET next_match_id = ? WHERE id = ?', 
                          (match_id, prev_round_matches[i + 1]['id']))
            
            match_number += 1
        
        prev_round_matches = current_round_matches
    
    # Update pool night
    cursor.execute('''
        UPDATE pool_nights 
        SET bracket_generated = 1, bracket_size = ?, tournament_status = 'bracket_ready', current_round = 1
        WHERE id = ?
    ''', (bracket_size, pool_night_id))
    
    conn.commit()
    
    # Advance any bye winners
    advance_bye_winners(pool_night_id, conn)
    
    conn.close()
    return {'success': True, 'bracket_size': bracket_size, 'num_rounds': num_rounds}


def advance_bye_winners(pool_night_id, conn=None):
    """Advance winners from bye matches to the next round."""
    close_conn = False
    if conn is None:
        conn = get_db()
        close_conn = True
    
    cursor = conn.cursor()
    
    # Find bye matches with winners that need to advance
    cursor.execute('''
        SELECT tm.* FROM tournament_matches tm
        WHERE tm.pool_night_id = ? AND tm.is_bye = 1 AND tm.winner_id IS NOT NULL
        AND tm.next_match_id IS NOT NULL
    ''', (pool_night_id,))
    
    for match in cursor.fetchall():
        match = dict(match)
        advance_winner_to_next_match(match['id'], match['winner_id'], conn)
    
    if close_conn:
        conn.commit()
        conn.close()


def advance_winner_to_next_match(match_id, winner_id, conn=None):
    """Advance a winner to their next match."""
    close_conn = False
    if conn is None:
        conn = get_db()
        close_conn = True
    
    cursor = conn.cursor()
    
    # Get current match and next match
    cursor.execute('SELECT * FROM tournament_matches WHERE id = ?', (match_id,))
    current_match = cursor.fetchone()
    if not current_match:
        if close_conn:
            conn.close()
        return
    
    current_match = dict(current_match)
    next_match_id = current_match.get('next_match_id')
    
    if not next_match_id:
        if close_conn:
            conn.close()
        return
    
    # Get winner's seed
    winner_seed = current_match['player1_seed'] if current_match['player1_id'] == winner_id else current_match['player2_seed']
    
    # Determine which slot in next match (based on match position)
    cursor.execute('SELECT * FROM tournament_matches WHERE id = ?', (next_match_id,))
    next_match = dict(cursor.fetchone())
    
    # Find which feeder matches lead to this match
    cursor.execute('''
        SELECT id FROM tournament_matches 
        WHERE next_match_id = ? 
        ORDER BY match_number ASC
    ''', (next_match_id,))
    feeder_matches = [row['id'] for row in cursor.fetchall()]
    
    # First feeder goes to player1, second to player2
    if match_id == feeder_matches[0]:
        cursor.execute('UPDATE tournament_matches SET player1_id = ?, player1_seed = ? WHERE id = ?',
                      (winner_id, winner_seed, next_match_id))
    else:
        cursor.execute('UPDATE tournament_matches SET player2_id = ?, player2_seed = ? WHERE id = ?',
                      (winner_id, winner_seed, next_match_id))
    
    if close_conn:
        conn.commit()
        conn.close()


def record_tournament_match_result(match_id, winner_id, player1_score=0, player2_score=0, forfeit=False, forfeit_player_id=None):
    """Record the result of a tournament match and advance the winner."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get match info
    cursor.execute('SELECT * FROM tournament_matches WHERE id = ?', (match_id,))
    match = cursor.fetchone()
    if not match:
        conn.close()
        return {'success': False, 'error': 'Match not found'}
    
    match = dict(match)
    
    if match['status'] == 'completed':
        conn.close()
        return {'success': False, 'error': 'Match already completed'}
    
    # Determine loser
    loser_id = match['player2_id'] if winner_id == match['player1_id'] else match['player1_id']
    
    # Update match
    cursor.execute('''
        UPDATE tournament_matches 
        SET winner_id = ?, loser_id = ?, player1_score = ?, player2_score = ?,
            status = 'completed', completed_at = datetime('now'),
            forfeit = ?, forfeit_player_id = ?
        WHERE id = ?
    ''', (winner_id, loser_id, player1_score, player2_score, 1 if forfeit else 0, forfeit_player_id, match_id))
    
    # Mark loser as eliminated
    cursor.execute('''
        UPDATE tournament_participants 
        SET eliminated = 1, eliminated_round = ?
        WHERE pool_night_id = ? AND player_id = ?
    ''', (match['round_number'], match['pool_night_id'], loser_id))
    
    # Advance winner to next match
    if match['next_match_id']:
        advance_winner_to_next_match(match_id, winner_id, conn)
    else:
        # This was the final match - winner is champion!
        cursor.execute('''
            UPDATE tournament_participants 
            SET final_placement = 1 
            WHERE pool_night_id = ? AND player_id = ?
        ''', (match['pool_night_id'], winner_id))
        cursor.execute('''
            UPDATE tournament_participants 
            SET final_placement = 2 
            WHERE pool_night_id = ? AND player_id = ?
        ''', (match['pool_night_id'], loser_id))
        cursor.execute('''
            UPDATE pool_nights SET tournament_status = 'completed' WHERE id = ?
        ''', (match['pool_night_id'],))
    
    # Record in game_history if pool night is ranked
    cursor.execute('SELECT * FROM pool_nights WHERE id = ?', (match['pool_night_id'],))
    pool_night = dict(cursor.fetchone())
    
    if pool_night.get('ranked_required') or pool_night.get('game_type') == 'ranked':
        cursor.execute('''
            INSERT INTO game_history (winner_id, loser_id, bar_id, is_ranked, ranked_source, played_at)
            VALUES (?, ?, ?, 1, 'tournament', datetime('now'))
        ''', (winner_id, loser_id, pool_night['bar_id']))
        game_id = cursor.lastrowid
        cursor.execute('UPDATE tournament_matches SET game_history_id = ? WHERE id = ?', (game_id, match_id))
        
        # Update player stats
        cursor.execute('UPDATE players SET wins = wins + 1, total_games = total_games + 1 WHERE id = ?', (winner_id,))
        cursor.execute('UPDATE players SET losses = losses + 1, total_games = total_games + 1 WHERE id = ?', (loser_id,))
    
    conn.commit()
    conn.close()
    
    return {'success': True, 'winner_id': winner_id, 'loser_id': loser_id}


def get_tournament_bracket(pool_night_id):
    """Get the full bracket structure for a tournament."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get all matches organized by round
    cursor.execute('''
        SELECT tm.*, 
               p1.nickname as player1_name, p1.rating as player1_rating,
               p2.nickname as player2_name, p2.rating as player2_rating,
               w.nickname as winner_name
        FROM tournament_matches tm
        LEFT JOIN players p1 ON tm.player1_id = p1.id
        LEFT JOIN players p2 ON tm.player2_id = p2.id
        LEFT JOIN players w ON tm.winner_id = w.id
        WHERE tm.pool_night_id = ?
        ORDER BY tm.round_number ASC, tm.match_number ASC
    ''', (pool_night_id,))
    
    matches = [dict(row) for row in cursor.fetchall()]
    
    # Organize by round
    rounds = {}
    for match in matches:
        round_num = match['round_number']
        if round_num not in rounds:
            rounds[round_num] = []
        rounds[round_num].append(match)
    
    # Get pool night info
    cursor.execute('SELECT * FROM pool_nights WHERE id = ?', (pool_night_id,))
    pool_night = dict(cursor.fetchone()) if cursor.fetchone else {}
    
    conn.close()
    
    return {
        'rounds': rounds,
        'matches': matches,
        'pool_night': pool_night,
        'total_rounds': len(rounds)
    }


def get_player_tournament_match(pool_night_id, player_id):
    """Get a player's current or upcoming match in a tournament."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if player is eliminated
    cursor.execute('''
        SELECT * FROM tournament_participants 
        WHERE pool_night_id = ? AND player_id = ?
    ''', (pool_night_id, player_id))
    participant = cursor.fetchone()
    
    if not participant:
        conn.close()
        return {'registered': False}
    
    participant = dict(participant)
    
    if participant['eliminated']:
        conn.close()
        return {
            'registered': True,
            'eliminated': True,
            'eliminated_round': participant['eliminated_round'],
            'final_placement': participant['final_placement']
        }
    
    # Find current/upcoming match
    cursor.execute('''
        SELECT tm.*, 
               p1.nickname as player1_name, p2.nickname as player2_name
        FROM tournament_matches tm
        LEFT JOIN players p1 ON tm.player1_id = p1.id
        LEFT JOIN players p2 ON tm.player2_id = p2.id
        WHERE tm.pool_night_id = ? 
        AND (tm.player1_id = ? OR tm.player2_id = ?)
        AND tm.status != 'completed'
        ORDER BY tm.round_number ASC
        LIMIT 1
    ''', (pool_night_id, player_id, player_id))
    
    match = cursor.fetchone()
    conn.close()
    
    if match:
        return {
            'registered': True,
            'eliminated': False,
            'current_match': dict(match),
            'seed': participant['seed']
        }
    
    return {
        'registered': True,
        'eliminated': False,
        'waiting': True,
        'seed': participant['seed']
    }


def start_tournament(pool_night_id):
    """Start a tournament - changes status to in_progress."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE pool_nights 
        SET tournament_status = 'in_progress'
        WHERE id = ? AND bracket_generated = 1
    ''', (pool_night_id,))
    
    # Update first round matches to 'scheduled'
    cursor.execute('''
        UPDATE tournament_matches 
        SET status = 'scheduled'
        WHERE pool_night_id = ? AND round_number = 1 AND status = 'pending' AND is_bye = 0
    ''', (pool_night_id,))
    
    conn.commit()
    conn.close()
    return {'success': True}

def get_setting(key, default=None):
    """Get a setting value from app_settings table."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM app_settings WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()
    return row['value'] if row else default


def set_setting(key, value):
    """Set a setting value in app_settings table."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO app_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    ''', (key, str(value)))
    conn.commit()
    conn.close()


def get_all_settings():
    """Get all settings as a dictionary."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT key, value FROM app_settings')
    settings = {row['key']: row['value'] for row in cursor.fetchall()}
    conn.close()
    return settings


# ============ AUTO-INVITE PIPELINE ============

def find_auto_invite_candidates(bar_id, min_days=3):
    """
    Find guest players who have played at this bar on multiple distinct days.
    
    Args:
        bar_id: The bar to check
        min_days: Minimum distinct days played to qualify (default: 3)
        
    Returns:
        List of player dicts with id, nickname, phone_number, distinct_days
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Find guest players (no account_id) with phone numbers
    # who have played at this bar on at least min_days distinct days
    cursor.execute('''
        SELECT 
            p.id,
            p.nickname,
            p.phone_number,
            COUNT(DISTINCT date(g.played_at)) as distinct_days
        FROM players p
        JOIN game_history g ON (g.winner_id = p.id OR g.loser_id = p.id)
        WHERE g.bar_id = ?
          AND p.account_id IS NULL
          AND p.phone_number IS NOT NULL
          AND p.phone_number != ''
          AND p.invite_opt_out = 0
        GROUP BY p.id
        HAVING COUNT(DISTINCT date(g.played_at)) >= ?
        ORDER BY distinct_days DESC
    ''', (bar_id, min_days))
    
    candidates = []
    for row in cursor.fetchall():
        candidates.append({
            'id': row['id'],
            'nickname': row['nickname'],
            'phone_number': row['phone_number'],
            'distinct_days': row['distinct_days']
        })
    
    conn.close()
    return candidates


def create_auto_invites_for_bar(bar_id, min_days=3):
    """
    Create pending SMS invites for frequent guest players at a bar.
    
    Checks global and per-bar settings before creating invites.
    Does NOT send SMS - just queues them with status='pending'.
    
    Args:
        bar_id: The bar to process
        min_days: Minimum distinct days to qualify
        
    Returns:
        dict with status, created_invites count, skipped count
    """
    # Check global setting
    global_enabled = get_setting('auto_invites_global_enabled', '0')
    if global_enabled != '1':
        return {
            'status': 'skipped',
            'reason': 'global_disabled',
            'created_invites': 0,
            'skipped': 0
        }
    
    # Check per-bar setting
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT auto_invites_enabled FROM bars WHERE id = ?', (bar_id,))
    bar_row = cursor.fetchone()
    
    if not bar_row or not bar_row['auto_invites_enabled']:
        conn.close()
        return {
            'status': 'skipped',
            'reason': 'bar_disabled',
            'created_invites': 0,
            'skipped': 0
        }
    
    # Find candidates
    candidates = find_auto_invite_candidates(bar_id, min_days)
    
    created = 0
    skipped = 0
    
    for candidate in candidates:
        # Check if invite already exists
        cursor.execute('''
            SELECT id FROM player_invites 
            WHERE player_id = ? AND bar_id = ? AND invite_type = 'sms'
        ''', (candidate['id'], bar_id))
        
        if cursor.fetchone():
            skipped += 1
            continue
        
        # Create new pending invite
        cursor.execute('''
            INSERT INTO player_invites (player_id, bar_id, invite_type, status, created_at)
            VALUES (?, ?, 'sms', 'pending', datetime('now'))
        ''', (candidate['id'], bar_id))
        created += 1
    
    conn.commit()
    conn.close()
    
    return {
        'status': 'ok',
        'created_invites': created,
        'skipped': skipped,
        'total_candidates': len(candidates)
    }


def get_pending_invites(bar_id=None, limit=100):
    """Get pending invites, optionally filtered by bar."""
    conn = get_db()
    cursor = conn.cursor()
    
    if bar_id:
        cursor.execute('''
            SELECT pi.*, p.nickname, p.phone_number, b.name as bar_name
            FROM player_invites pi
            JOIN players p ON pi.player_id = p.id
            JOIN bars b ON pi.bar_id = b.id
            WHERE pi.status = 'pending' AND pi.bar_id = ?
            ORDER BY pi.created_at DESC
            LIMIT ?
        ''', (bar_id, limit))
    else:
        cursor.execute('''
            SELECT pi.*, p.nickname, p.phone_number, b.name as bar_name
            FROM player_invites pi
            JOIN players p ON pi.player_id = p.id
            JOIN bars b ON pi.bar_id = b.id
            WHERE pi.status = 'pending'
            ORDER BY pi.created_at DESC
            LIMIT ?
        ''', (limit,))
    
    invites = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return invites


def get_invite_stats():
    """Get aggregate stats for invites."""
    conn = get_db()
    cursor = conn.cursor()
    
    stats = {}
    
    cursor.execute("SELECT COUNT(*) FROM player_invites WHERE status = 'pending'")
    stats['pending'] = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM player_invites WHERE status = 'sent'")
    stats['sent'] = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM player_invites WHERE status = 'accepted'")
    stats['accepted'] = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM player_invites WHERE status = 'rejected'")
    stats['rejected'] = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM player_invites")
    stats['total'] = cursor.fetchone()[0] or 0
    
    conn.close()
    return stats


# ============ ENHANCED AUTO-INVITE SYSTEM ============

def get_auto_invite_threshold():
    """Get the global auto-invite threshold (default 3)."""
    return int(get_setting('auto_invite_threshold', '3'))


def get_bar_auto_invite_threshold(bar_id):
    """
    Get the effective auto-invite threshold for a specific bar.
    Uses per-bar override if set, otherwise falls back to global threshold.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT auto_invite_threshold FROM bars WHERE id = ?', (bar_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row and row['auto_invite_threshold'] is not None:
        return row['auto_invite_threshold']
    
    return get_auto_invite_threshold()


def set_auto_invite_threshold(value):
    """Set the global auto-invite threshold."""
    set_setting('auto_invite_threshold', str(int(value)))


def set_bar_auto_invite_threshold(bar_id, value):
    """Set per-bar auto-invite threshold override (None to use global)."""
    conn = get_db()
    cursor = conn.cursor()
    if value is None:
        cursor.execute('UPDATE bars SET auto_invite_threshold = NULL WHERE id = ?', (bar_id,))
    else:
        cursor.execute('UPDATE bars SET auto_invite_threshold = ? WHERE id = ?', (int(value), bar_id))
    conn.commit()
    conn.close()


def log_queue_usage(phone_number, bar_id, player_id=None, nickname=None, has_account=False):
    """
    Log a queue join event for tracking auto-invite eligibility.
    
    Args:
        phone_number: The phone number used to join
        bar_id: The bar where they joined
        player_id: Optional player ID
        nickname: Optional nickname used
        has_account: Whether they have a full account
        
    Returns:
        dict with queue_count for this phone
    """
    import re
    
    if not phone_number:
        return {'queue_count': 0, 'invite_triggered': False}
    
    # Normalize phone number (keep only digits)
    phone_digits = re.sub(r'\D', '', phone_number)
    if len(phone_digits) < 10:
        return {'queue_count': 0, 'invite_triggered': False}
    
    # Use last 10 digits for consistency
    phone_normalized = phone_digits[-10:]
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Log the queue usage
    cursor.execute('''
        INSERT INTO queue_usage_log (phone_number, bar_id, player_id, nickname, had_account, created_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
    ''', (phone_normalized, bar_id, player_id, nickname, 1 if has_account else 0))
    
    conn.commit()
    
    # Count distinct days this phone has used the queue (without an account)
    cursor.execute('''
        SELECT COUNT(DISTINCT date(created_at)) as distinct_days
        FROM queue_usage_log
        WHERE phone_number = ? AND had_account = 0
    ''', (phone_normalized,))
    
    row = cursor.fetchone()
    queue_count = row['distinct_days'] if row else 0
    
    conn.close()
    
    # Check if threshold is met and no account exists
    invite_triggered = False
    if not has_account:
        result = check_and_create_auto_invite(phone_normalized, bar_id, queue_count)
        invite_triggered = result.get('created', False)
    
    return {
        'queue_count': queue_count,
        'invite_triggered': invite_triggered
    }


def check_and_create_auto_invite(phone_number, bar_id, queue_count=None):
    """
    Check if a phone number meets the threshold and create auto-invite if needed.
    
    Args:
        phone_number: Normalized phone number (10 digits)
        bar_id: The bar ID
        queue_count: Pre-computed queue count (optional)
        
    Returns:
        dict with created, invite_id, or skipped reason
    """
    import secrets
    
    # Use per-bar threshold if set, otherwise global
    threshold = get_bar_auto_invite_threshold(bar_id) if bar_id else get_auto_invite_threshold()
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if auto-invites are globally enabled
    global_enabled = get_setting('auto_invites_global_enabled', '0')
    if global_enabled != '1':
        conn.close()
        return {'created': False, 'reason': 'global_disabled'}
    
    # Get queue count if not provided
    if queue_count is None:
        cursor.execute('''
            SELECT COUNT(DISTINCT date(created_at)) as distinct_days
            FROM queue_usage_log
            WHERE phone_number = ? AND had_account = 0
        ''', (phone_number,))
        row = cursor.fetchone()
        queue_count = row['distinct_days'] if row else 0
    
    # Check threshold
    if queue_count < threshold:
        conn.close()
        return {'created': False, 'reason': 'below_threshold', 'queue_count': queue_count, 'threshold': threshold}
    
    # Check if invite already exists for this phone
    cursor.execute('''
        SELECT id, status FROM auto_invites WHERE phone_number = ?
    ''', (phone_number,))
    existing = cursor.fetchone()
    
    if existing:
        conn.close()
        return {'created': False, 'reason': 'already_exists', 'existing_id': existing['id'], 'existing_status': existing['status']}
    
    # Check if phone already has an account
    cursor.execute('''
        SELECT id FROM players WHERE phone_number LIKE ? AND account_id IS NOT NULL
    ''', (f'%{phone_number}',))
    if cursor.fetchone():
        conn.close()
        return {'created': False, 'reason': 'has_account'}
    
    # Generate unique invite token
    invite_token = secrets.token_urlsafe(16)
    
    # Create auto-invite record
    cursor.execute('''
        INSERT INTO auto_invites (phone_number, bar_id, threshold_met, queue_count, invite_token, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'pending', datetime('now'))
    ''', (phone_number, bar_id, threshold, queue_count, invite_token))
    
    invite_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return {
        'created': True,
        'invite_id': invite_id,
        'invite_token': invite_token,
        'queue_count': queue_count,
        'threshold': threshold
    }


def send_auto_invite(invite_id):
    """
    Mark an auto-invite as sent (actual SMS sending is stubbed).
    
    Args:
        invite_id: The auto_invite ID
        
    Returns:
        dict with success status
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM auto_invites WHERE id = ?', (invite_id,))
    invite = cursor.fetchone()
    
    if not invite:
        conn.close()
        return {'success': False, 'error': 'Invite not found'}
    
    invite = dict(invite)
    
    # TODO: Integrate with SMS provider (Twilio, etc.)
    # For now, just mark as sent
    # sms_result = send_sms(invite['phone_number'], message, invite_link)
    
    cursor.execute('''
        UPDATE auto_invites 
        SET status = 'sent', invited_at = datetime('now'), sms_sent = 1
        WHERE id = ?
    ''', (invite_id,))
    
    conn.commit()
    conn.close()
    
    return {
        'success': True,
        'invite_id': invite_id,
        'phone_number': invite['phone_number'],
        'invite_token': invite['invite_token']
    }


def mark_auto_invite_opened(invite_token):
    """
    Mark an auto-invite as opened when the link is clicked.
    
    Args:
        invite_token: The unique invite token
        
    Returns:
        dict with invite details or error
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM auto_invites WHERE invite_token = ?', (invite_token,))
    invite = cursor.fetchone()
    
    if not invite:
        conn.close()
        return {'success': False, 'error': 'Invalid invite token'}
    
    invite = dict(invite)
    
    # Only update if not already opened
    if not invite.get('opened_at'):
        cursor.execute('''
            UPDATE auto_invites 
            SET status = 'opened', opened_at = datetime('now')
            WHERE id = ? AND opened_at IS NULL
        ''', (invite['id'],))
        conn.commit()
    
    conn.close()
    
    return {
        'success': True,
        'invite_id': invite['id'],
        'phone_number': invite['phone_number'],
        'bar_id': invite['bar_id']
    }


def complete_auto_invite_signup(phone_number, player_id):
    """
    Mark an auto-invite as completed when signup finishes.
    
    Args:
        phone_number: The phone number that signed up
        player_id: The new player's ID
        
    Returns:
        dict with success status
    """
    import re
    
    # Normalize phone
    phone_digits = re.sub(r'\D', '', phone_number) if phone_number else ''
    if len(phone_digits) < 10:
        return {'success': False, 'error': 'Invalid phone'}
    
    phone_normalized = phone_digits[-10:]
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Find pending or opened invite for this phone
    cursor.execute('''
        SELECT id FROM auto_invites 
        WHERE phone_number = ? AND status IN ('pending', 'sent', 'opened')
        LIMIT 1
    ''', (phone_normalized,))
    
    invite = cursor.fetchone()
    
    if invite:
        cursor.execute('''
            UPDATE auto_invites 
            SET status = 'completed', signed_up_player_id = ?, signed_up_at = datetime('now')
            WHERE id = ?
        ''', (player_id, invite['id']))
        conn.commit()
        conn.close()
        return {'success': True, 'invite_id': invite['id']}
    
    conn.close()
    return {'success': False, 'error': 'No pending invite found'}


def get_auto_invite_by_token(invite_token):
    """Get auto-invite details by token."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT ai.*, b.name as bar_name
        FROM auto_invites ai
        LEFT JOIN bars b ON ai.bar_id = b.id
        WHERE ai.invite_token = ?
    ''', (invite_token,))
    
    invite = cursor.fetchone()
    conn.close()
    
    return dict(invite) if invite else None


def get_auto_invite_analytics(start_date=None, end_date=None, bar_id=None):
    """
    Get analytics for the auto-invite funnel.
    
    Args:
        start_date: Optional start date filter (YYYY-MM-DD)
        end_date: Optional end date filter (YYYY-MM-DD)
        bar_id: Optional bar filter
        
    Returns:
        dict with funnel metrics
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Build WHERE clause
    conditions = []
    params = []
    
    if start_date:
        conditions.append("created_at >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("created_at <= ?")
        params.append(end_date + ' 23:59:59')
    if bar_id:
        conditions.append("bar_id = ?")
        params.append(bar_id)
    
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    stats = {}
    
    # Total auto-invites created
    cursor.execute(f'SELECT COUNT(*) FROM auto_invites {where_clause}', params)
    stats['total_created'] = cursor.fetchone()[0] or 0
    
    # Sent (invited_at is set)
    cursor.execute(f"SELECT COUNT(*) FROM auto_invites {where_clause} {'AND' if where_clause else 'WHERE'} invited_at IS NOT NULL", params)
    stats['total_sent'] = cursor.fetchone()[0] or 0
    
    # Opened
    cursor.execute(f"SELECT COUNT(*) FROM auto_invites {where_clause} {'AND' if where_clause else 'WHERE'} opened_at IS NOT NULL", params)
    stats['total_opened'] = cursor.fetchone()[0] or 0
    
    # Completed (signed up)
    cursor.execute(f"SELECT COUNT(*) FROM auto_invites {where_clause} {'AND' if where_clause else 'WHERE'} status = 'completed'", params)
    stats['total_completed'] = cursor.fetchone()[0] or 0
    
    # Pending
    cursor.execute(f"SELECT COUNT(*) FROM auto_invites {where_clause} {'AND' if where_clause else 'WHERE'} status = 'pending'", params)
    stats['pending'] = cursor.fetchone()[0] or 0
    
    # Calculate rates
    stats['open_rate'] = round((stats['total_opened'] / stats['total_sent'] * 100), 1) if stats['total_sent'] > 0 else 0
    stats['conversion_rate'] = round((stats['total_completed'] / stats['total_sent'] * 100), 1) if stats['total_sent'] > 0 else 0
    stats['signup_from_open_rate'] = round((stats['total_completed'] / stats['total_opened'] * 100), 1) if stats['total_opened'] > 0 else 0
    
    # Queue usage stats
    cursor.execute(f'''
        SELECT COUNT(DISTINCT phone_number) as unique_phones,
               COUNT(*) as total_joins
        FROM queue_usage_log
        {where_clause.replace('created_at', 'queue_usage_log.created_at')}
    ''', params)
    usage_row = cursor.fetchone()
    stats['unique_phones'] = usage_row['unique_phones'] if usage_row else 0
    stats['total_queue_joins'] = usage_row['total_joins'] if usage_row else 0
    
    # Get current threshold
    stats['current_threshold'] = get_auto_invite_threshold()
    
    # By-bar breakdown
    cursor.execute('''
        SELECT 
            b.id as bar_id,
            b.name as bar_name,
            COUNT(*) as total_invites,
            SUM(CASE WHEN ai.status = 'completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN ai.opened_at IS NOT NULL THEN 1 ELSE 0 END) as opened
        FROM auto_invites ai
        LEFT JOIN bars b ON ai.bar_id = b.id
        GROUP BY ai.bar_id
        ORDER BY total_invites DESC
    ''')
    stats['by_bar'] = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return stats


def get_pending_auto_invites(limit=100):
    """Get pending auto-invites that need to be sent."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT ai.*, b.name as bar_name
        FROM auto_invites ai
        LEFT JOIN bars b ON ai.bar_id = b.id
        WHERE ai.status = 'pending' AND ai.sms_sent = 0
        ORDER BY ai.created_at ASC
        LIMIT ?
    ''', (limit,))
    
    invites = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return invites


def get_comprehensive_auto_invite_analytics():
    """
    Get comprehensive auto-invite analytics for the dedicated dashboard.
    Returns detailed metrics, trends, and insights.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    stats = {}
    threshold = get_auto_invite_threshold()
    stats['threshold'] = threshold
    
    # Overall counts
    cursor.execute('SELECT COUNT(*) FROM auto_invites')
    stats['total_created'] = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM auto_invites WHERE invited_at IS NOT NULL")
    stats['total_sent'] = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM auto_invites WHERE opened_at IS NOT NULL")
    stats['total_opened'] = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM auto_invites WHERE status = 'completed'")
    stats['total_completed'] = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM auto_invites WHERE status = 'pending'")
    stats['pending'] = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM auto_invites WHERE status = 'rejected'")
    stats['rejected'] = cursor.fetchone()[0] or 0
    
    # Calculate rates
    stats['open_rate'] = round((stats['total_opened'] / stats['total_sent'] * 100), 1) if stats['total_sent'] > 0 else 0
    stats['conversion_rate'] = round((stats['total_completed'] / stats['total_sent'] * 100), 1) if stats['total_sent'] > 0 else 0
    stats['signup_from_open_rate'] = round((stats['total_completed'] / stats['total_opened'] * 100), 1) if stats['total_opened'] > 0 else 0
    
    # Phones at threshold but not yet invited
    cursor.execute('''
        SELECT COUNT(DISTINCT phone_number) 
        FROM queue_usage_log 
        WHERE phone_number NOT IN (SELECT phone_number FROM auto_invites)
        AND phone_number NOT IN (SELECT phone_number FROM players WHERE phone_number IS NOT NULL)
    ''')
    at_threshold_count = cursor.fetchone()[0] or 0
    
    # Actually check how many have hit threshold
    cursor.execute(f'''
        SELECT phone_number, COUNT(DISTINCT date(created_at)) as days_played
        FROM queue_usage_log
        WHERE phone_number NOT IN (SELECT phone_number FROM auto_invites)
        AND phone_number NOT IN (SELECT phone_number FROM players WHERE phone_number IS NOT NULL AND is_active = 1)
        GROUP BY phone_number
        HAVING days_played >= ?
    ''', (threshold,))
    eligible_not_invited = cursor.fetchall()
    stats['eligible_not_invited'] = len(eligible_not_invited)
    
    # Last 7 days trend
    cursor.execute('''
        SELECT 
            date(created_at) as day,
            COUNT(*) as created,
            SUM(CASE WHEN invited_at IS NOT NULL THEN 1 ELSE 0 END) as sent,
            SUM(CASE WHEN opened_at IS NOT NULL THEN 1 ELSE 0 END) as opened,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed
        FROM auto_invites
        WHERE created_at >= date('now', '-7 days')
        GROUP BY date(created_at)
        ORDER BY day ASC
    ''')
    stats['trend_7d'] = [dict(row) for row in cursor.fetchall()]
    
    # Last 30 days trend (weekly buckets)
    cursor.execute('''
        SELECT 
            strftime('%Y-W%W', created_at) as week,
            COUNT(*) as created,
            SUM(CASE WHEN invited_at IS NOT NULL THEN 1 ELSE 0 END) as sent,
            SUM(CASE WHEN opened_at IS NOT NULL THEN 1 ELSE 0 END) as opened,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed
        FROM auto_invites
        WHERE created_at >= date('now', '-30 days')
        GROUP BY strftime('%Y-W%W', created_at)
        ORDER BY week ASC
    ''')
    stats['trend_30d'] = [dict(row) for row in cursor.fetchall()]
    
    # Per-bar performance with conversion rates
    cursor.execute('''
        SELECT 
            b.id as bar_id,
            b.name as bar_name,
            b.auto_invites_enabled,
            COUNT(*) as total_invites,
            SUM(CASE WHEN ai.invited_at IS NOT NULL THEN 1 ELSE 0 END) as sent,
            SUM(CASE WHEN ai.opened_at IS NOT NULL THEN 1 ELSE 0 END) as opened,
            SUM(CASE WHEN ai.status = 'completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN ai.status = 'rejected' THEN 1 ELSE 0 END) as rejected
        FROM auto_invites ai
        LEFT JOIN bars b ON ai.bar_id = b.id
        GROUP BY ai.bar_id
        ORDER BY completed DESC, total_invites DESC
    ''')
    bars_data = []
    for row in cursor.fetchall():
        bar = dict(row)
        bar['conversion_rate'] = round((bar['completed'] / bar['sent'] * 100), 1) if bar['sent'] > 0 else 0
        bar['open_rate'] = round((bar['opened'] / bar['sent'] * 100), 1) if bar['sent'] > 0 else 0
        bars_data.append(bar)
    stats['by_bar'] = bars_data
    
    # Top performing bar (highest conversion rate with min 5 sent)
    top_bar = None
    for bar in bars_data:
        if bar['sent'] >= 5 and (top_bar is None or bar['conversion_rate'] > top_bar['conversion_rate']):
            top_bar = bar
    stats['top_bar'] = top_bar
    
    # Recent auto-invites (last 20)
    cursor.execute('''
        SELECT ai.*, b.name as bar_name
        FROM auto_invites ai
        LEFT JOIN bars b ON ai.bar_id = b.id
        ORDER BY ai.created_at DESC
        LIMIT 20
    ''')
    stats['recent_invites'] = [dict(row) for row in cursor.fetchall()]
    
    # Global enabled status
    stats['global_enabled'] = get_setting('auto_invites_global_enabled', '0') == '1'
    
    # Count of bars with auto-invites enabled
    cursor.execute('SELECT COUNT(*) FROM bars WHERE auto_invites_enabled = 1')
    stats['bars_enabled_count'] = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT COUNT(*) FROM bars WHERE is_active = 1')
    stats['total_bars'] = cursor.fetchone()[0] or 0
    
    conn.close()
    return stats



def get_active_marketplace_listings(limit=50, exclude_seller_id=None):
    """Get all active marketplace listings."""
    conn = get_db()
    cursor = conn.cursor()
    
    if exclude_seller_id:
        cursor.execute('''
            SELECT l.*, p.nickname as seller_name
            FROM cue_marketplace_listings l
            JOIN players p ON l.seller_player_id = p.id
            WHERE l.status = 'active' AND l.seller_player_id != ?
            ORDER BY l.created_at DESC
            LIMIT ?
        ''', (exclude_seller_id, limit))
    else:
        cursor.execute('''
            SELECT l.*, p.nickname as seller_name
            FROM cue_marketplace_listings l
            JOIN players p ON l.seller_player_id = p.id
            WHERE l.status = 'active'
            ORDER BY l.created_at DESC
            LIMIT ?
        ''', (limit,))
    
    listings = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return listings


def get_my_marketplace_listings(player_id):
    """Get all listings for a specific seller."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM cue_marketplace_listings
        WHERE seller_player_id = ?
        ORDER BY created_at DESC
    ''', (player_id,))
    
    listings = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return listings


def get_marketplace_listing(listing_id):
    """Get a single listing by ID with seller info."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT l.*, p.nickname as seller_name
        FROM cue_marketplace_listings l
        JOIN players p ON l.seller_player_id = p.id
        WHERE l.id = ?
    ''', (listing_id,))
    
    listing = cursor.fetchone()
    conn.close()
    return dict(listing) if listing else None


def create_marketplace_listing(seller_id, title, description, condition, price_tokens=None, price_cash=None, price_type='tokens'):
    """Create a new cue listing with tokens or cash price."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO cue_marketplace_listings 
        (seller_player_id, title, description, condition, price_tokens, price_cash, price_type)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (seller_id, title, description, condition, price_tokens, price_cash, price_type))
    
    listing_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return listing_id


def buy_marketplace_listing(listing_id, buyer_id):
    """
    Process purchase of a listing (supports both tokens and cash).
    Returns: (success: bool, message: str)
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Get listing
        cursor.execute('SELECT * FROM cue_marketplace_listings WHERE id = ?', (listing_id,))
        listing = cursor.fetchone()
        
        if not listing:
            conn.close()
            return False, "Listing not found"
        
        if listing['status'] != 'active':
            conn.close()
            return False, "This listing is no longer available"
        
        if listing['seller_player_id'] == buyer_id:
            conn.close()
            return False, "You cannot buy your own listing"
        
        seller_id = listing['seller_player_id']
        price_type = listing['price_type'] or 'tokens'
        
        if price_type == 'cash':
            # Cash purchase - use wallet balance
            price = float(listing['price_cash'] or 0)
            
            # Check buyer wallet balance
            cursor.execute('SELECT wallet_balance FROM players WHERE id = ?', (buyer_id,))
            buyer = cursor.fetchone()
            buyer_balance = float(buyer['wallet_balance'] or 0) if buyer else 0
            
            if buyer_balance < price:
                conn.close()
                return False, f"Insufficient wallet balance. You have ${buyer_balance:.2f}, need ${price:.2f}"
            
            # Deduct from buyer wallet
            cursor.execute('''
                UPDATE players 
                SET wallet_balance = wallet_balance - ?
                WHERE id = ?
            ''', (price, buyer_id))
            
            # Credit to seller wallet
            cursor.execute('''
                UPDATE players 
                SET wallet_balance = COALESCE(wallet_balance, 0) + ?
                WHERE id = ?
            ''', (price, seller_id))
            
            # Record wallet transactions
            cursor.execute('''
                INSERT INTO wallet_transactions 
                (player_id, amount, transaction_type, description, created_at)
                VALUES (?, ?, 'marketplace_purchase', ?, datetime('now'))
            ''', (buyer_id, -price, f'Purchased: {listing["title"]}'))
            
            cursor.execute('''
                INSERT INTO wallet_transactions 
                (player_id, amount, transaction_type, description, created_at)
                VALUES (?, ?, 'marketplace_sale', ?, datetime('now'))
            ''', (seller_id, price, f'Sold: {listing["title"]}'))
            
        else:
            # Token purchase - existing logic
            price = listing['price_tokens'] or 0
            
            # Check buyer token balance
            cursor.execute('SELECT tokens_balance FROM players WHERE id = ?', (buyer_id,))
            buyer = cursor.fetchone()
            
            if not buyer or (buyer['tokens_balance'] or 0) < price:
                conn.close()
                return False, "Insufficient tokens"
            
            # Deduct from buyer
            cursor.execute('''
                UPDATE players 
                SET tokens_balance = tokens_balance - ?,
                    tokens_spent = COALESCE(tokens_spent, 0) + ?
                WHERE id = ?
            ''', (price, price, buyer_id))
            
            # Credit to seller
            cursor.execute('''
                UPDATE players 
                SET tokens_balance = COALESCE(tokens_balance, 0) + ?,
                    tokens_earned = COALESCE(tokens_earned, 0) + ?
                WHERE id = ?
            ''', (price, price, seller_id))
            
            # Record token transactions
            cursor.execute('''
                INSERT INTO token_transactions (player_id, amount, reason, created_at)
                VALUES (?, ?, ?, datetime('now'))
            ''', (buyer_id, -price, f'marketplace_purchase:{listing_id}'))
            
            cursor.execute('''
                INSERT INTO token_transactions (player_id, amount, reason, created_at)
                VALUES (?, ?, ?, datetime('now'))
            ''', (seller_id, price, f'marketplace_sale:{listing_id}'))
        
        # Mark listing as sold
        cursor.execute('''
            UPDATE cue_marketplace_listings 
            SET status = 'sold', 
                buyer_player_id = ?,
                sold_at = datetime('now'),
                updated_at = datetime('now')
            WHERE id = ?
        ''', (buyer_id, listing_id))
        
        conn.commit()
        conn.close()
        return True, "Purchase successful!"
        
    except Exception as e:
        conn.close()
        return False, f"Error: {str(e)}"


def close_marketplace_listing(listing_id, player_id):
    """Close/hide a listing (seller only)."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Verify ownership
    cursor.execute('''
        SELECT seller_player_id FROM cue_marketplace_listings WHERE id = ?
    ''', (listing_id,))
    listing = cursor.fetchone()
    
    if not listing or listing['seller_player_id'] != player_id:
        conn.close()
        return False, "Not authorized"
    
    cursor.execute('''
        UPDATE cue_marketplace_listings 
        SET status = 'closed', updated_at = datetime('now')
        WHERE id = ?
    ''', (listing_id,))
    
    conn.commit()
    conn.close()
    return True, "Listing closed"

    return True, "Listing closed"


# ============ REFERRAL HELPERS ============

def generate_referral_code(player_id):
    """Generate a unique referral code for a player."""
    import hashlib
    import time
    base = f"{player_id}-{time.time()}"
    code = hashlib.md5(base.encode()).hexdigest()[:8].upper()
    return code


def get_or_create_referral_code(player_id):
    """Get existing referral code or create a new one."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT referral_code FROM players WHERE id = ?', (player_id,))
    row = cursor.fetchone()
    
    if row and row['referral_code']:
        conn.close()
        return row['referral_code']
    
    # Generate new code
    code = generate_referral_code(player_id)
    cursor.execute('UPDATE players SET referral_code = ? WHERE id = ?', (code, player_id))
    conn.commit()
    conn.close()
    return code


def get_player_by_referral_code(code):
    """Find player by their referral code."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, nickname, email, phone_number FROM players WHERE referral_code = ?', (code.upper(),))
    player = cursor.fetchone()
    conn.close()
    return dict(player) if player else None


def record_referral(referrer_id, referred_id, code):
    """Record a new referral when someone signs up with a code."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if referral already exists
    cursor.execute('SELECT id FROM referrals WHERE referred_user_id = ?', (referred_id,))
    if cursor.fetchone():
        conn.close()
        return False, "User already has a referrer"
    
    cursor.execute('''
        INSERT INTO referrals (referrer_user_id, referred_user_id, referral_code, status)
        VALUES (?, ?, ?, 'pending')
    ''', (referrer_id, referred_id, code))
    
    # Also mark on the referred user
    cursor.execute('UPDATE players SET referred_by_user_id = ? WHERE id = ?', (referrer_id, referred_id))
    
    conn.commit()
    conn.close()
    return True, "Referral recorded"


def complete_referral_reward(referred_user_id, referrer_tokens=100, referred_tokens=50):
    """
    Complete a referral and award tokens when referred user plays their first game.
    Returns (success, message).
    """
    from datetime import date
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Find pending referral for this user
    cursor.execute('''
        SELECT r.id, r.referrer_user_id, r.status, r.reward_given
        FROM referrals r
        WHERE r.referred_user_id = ? AND r.status = 'pending' AND r.reward_given = 0
    ''', (referred_user_id,))
    referral = cursor.fetchone()
    
    if not referral:
        conn.close()
        return False, "No pending referral found"
    
    referrer_id = referral['referrer_user_id']
    today = date.today().isoformat()
    
    # Check referrer's daily limit (max 5 referral rewards per day)
    cursor.execute('''
        SELECT referral_rewards_today, last_referral_reward_date 
        FROM players WHERE id = ?
    ''', (referrer_id,))
    referrer = cursor.fetchone()
    
    daily_count = referrer['referral_rewards_today'] or 0
    last_date = referrer['last_referral_reward_date']
    
    # Reset counter if it's a new day
    if last_date != today:
        daily_count = 0
    
    if daily_count >= 5:
        conn.close()
        return False, "Referrer has reached daily reward limit"
    
    # Award tokens to referrer
    cursor.execute('''
        UPDATE players 
        SET tokens_balance = COALESCE(tokens_balance, 0) + ?,
            total_tokens_earned = COALESCE(total_tokens_earned, 0) + ?,
            referral_rewards_today = ?,
            last_referral_reward_date = ?
        WHERE id = ?
    ''', (referrer_tokens, referrer_tokens, daily_count + 1, today, referrer_id))
    
    # Award tokens to referred user
    cursor.execute('''
        UPDATE players 
        SET tokens_balance = COALESCE(tokens_balance, 0) + ?,
            total_tokens_earned = COALESCE(total_tokens_earned, 0) + ?
        WHERE id = ?
    ''', (referred_tokens, referred_tokens, referred_user_id))
    
    # Mark referral as completed
    cursor.execute('''
        UPDATE referrals 
        SET status = 'completed', reward_given = 1, completed_at = datetime('now')
        WHERE id = ?
    ''', (referral['id'],))
    
    # Record token transactions
    cursor.execute('''
        INSERT INTO token_transactions (player_id, amount, reason, created_at)
        VALUES (?, ?, 'referral_reward', datetime('now'))
    ''', (referrer_id, referrer_tokens))
    
    cursor.execute('''
        INSERT INTO token_transactions (player_id, amount, reason, created_at)
        VALUES (?, ?, 'referral_bonus', datetime('now'))
    ''', (referred_user_id, referred_tokens))
    
    conn.commit()
    conn.close()
    return True, f"Referral completed! Referrer earned {referrer_tokens} tokens, referred earned {referred_tokens} tokens"


def get_referral_stats(player_id):
    """Get referral statistics for a player."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Total referrals
    cursor.execute('SELECT COUNT(*) as total FROM referrals WHERE referrer_user_id = ?', (player_id,))
    total = cursor.fetchone()['total']
    
    # Completed referrals
    cursor.execute("SELECT COUNT(*) as completed FROM referrals WHERE referrer_user_id = ? AND status = 'completed'", (player_id,))
    completed = cursor.fetchone()['completed']
    
    # Pending referrals
    cursor.execute("SELECT COUNT(*) as pending FROM referrals WHERE referrer_user_id = ? AND status = 'pending'", (player_id,))
    pending = cursor.fetchone()['pending']
    
    # Total tokens earned from referrals
    cursor.execute('''
        SELECT COALESCE(SUM(amount), 0) as total_earned 
        FROM token_transactions 
        WHERE player_id = ? AND reason = 'referral_reward'
    ''', (player_id,))
    total_earned = cursor.fetchone()['total_earned']
    
    conn.close()
    return {
        'total': total,
        'completed': completed,
        'pending': pending,
        'tokens_earned': total_earned
    }


def get_referral_list(player_id):
    """Get list of referrals for a player."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT r.id, r.status, r.created_at, r.completed_at,
               p.nickname as referred_nickname
        FROM referrals r
        LEFT JOIN players p ON r.referred_user_id = p.id
        WHERE r.referrer_user_id = ?
        ORDER BY r.created_at DESC
        LIMIT 50
    ''', (player_id,))
    
    referrals = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return referrals



# ============ RANKED MATCH HELPERS ============

def is_ranked_window_active(bar_id):
    """Check if there's an active ranked window for a bar right now."""
    from datetime import datetime
    conn = get_db()
    cursor = conn.cursor()
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute('''
        SELECT id, title FROM ranked_windows 
        WHERE bar_id = ? AND is_active = 1
        AND start_datetime <= ? AND end_datetime >= ?
    ''', (bar_id, now, now))
    
    window = cursor.fetchone()
    conn.close()
    return dict(window) if window else None


def is_pool_night_ranked_active(bar_id):
    """Check if there's an active pool night with ranked_required for a bar right now."""
    from datetime import datetime, date
    conn = get_db()
    cursor = conn.cursor()
    
    today = date.today().isoformat()
    now_time = datetime.now().strftime('%H:%M')
    
    cursor.execute('''
        SELECT id, title, start_time, end_time FROM pool_nights 
        WHERE bar_id = ? AND status = 'approved' AND ranked_required = 1
        AND event_date = ?
        AND (start_time IS NULL OR start_time <= ?)
        AND (end_time IS NULL OR end_time >= ?)
    ''', (bar_id, today, now_time, now_time))
    
    event = cursor.fetchone()
    conn.close()
    return dict(event) if event else None


def check_ranked_requirement(bar_id):
    """
    Check if a game at this bar right now should be auto-ranked.
    Returns: (is_ranked, source, source_info) tuple
    """
    # First check ranked windows
    window = is_ranked_window_active(bar_id)
    if window:
        return True, 'event', f"Ranked Window: {window.get('title', 'Scheduled')}"
    
    # Then check pool nights with ranked_required
    pool_night = is_pool_night_ranked_active(bar_id)
    if pool_night:
        return True, 'event', f"Pool Night: {pool_night.get('title', 'Event')}"
    
    return False, None, None


def create_ranked_window(bar_id, start_datetime, end_datetime, title=None, created_by=None):
    """Create a new ranked window for a bar."""
    from datetime import datetime
    
    # Validate dates
    try:
        start = datetime.fromisoformat(start_datetime)
        end = datetime.fromisoformat(end_datetime)
        if end <= start:
            return False, "End time must be after start time"
        if start < datetime.now():
            return False, "Start time cannot be in the past"
    except ValueError:
        return False, "Invalid datetime format"
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO ranked_windows (bar_id, title, start_datetime, end_datetime, created_by)
        VALUES (?, ?, ?, ?, ?)
    ''', (bar_id, title or 'Ranked Period', start_datetime, end_datetime, created_by))
    
    window_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return True, window_id


def get_ranked_windows(bar_id, include_past=False):
    """Get ranked windows for a bar."""
    from datetime import datetime
    conn = get_db()
    cursor = conn.cursor()
    
    if include_past:
        cursor.execute('''
            SELECT rw.*, b.name as bar_name
            FROM ranked_windows rw
            LEFT JOIN bars b ON rw.bar_id = b.id
            WHERE rw.bar_id = ?
            ORDER BY rw.start_datetime DESC
        ''', (bar_id,))
    else:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            SELECT rw.*, b.name as bar_name
            FROM ranked_windows rw
            LEFT JOIN bars b ON rw.bar_id = b.id
            WHERE rw.bar_id = ? AND rw.end_datetime >= ?
            ORDER BY rw.start_datetime ASC
        ''', (bar_id, now))
    
    windows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return windows


def delete_ranked_window(window_id):
    """Delete a ranked window."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM ranked_windows WHERE id = ?', (window_id,))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def set_pool_night_ranked(pool_night_id, ranked_required):
    """Set whether a pool night requires ranked matches."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE pool_nights SET ranked_required = ? WHERE id = ?', 
                   (1 if ranked_required else 0, pool_night_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def request_ranked_match(queue_id, opponent_player_id=None):
    """Shot caller requests a ranked match."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE queue SET ranked_request = 1, opponent_player_id = ?
        WHERE id = ?
    ''', (opponent_player_id, queue_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def respond_ranked_request(queue_id, accept):
    """Opponent responds to ranked match request."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE queue SET ranked_accepted = ?
        WHERE id = ?
    ''', (1 if accept else 0, queue_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def get_pending_ranked_request(player_id):
    """Check if there's a pending ranked request for this player to respond to."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Find queue entry where this player is the opponent and ranked_request is pending
    cursor.execute('''
        SELECT q.*, p.nickname as shot_caller_name
        FROM queue q
        JOIN players p ON q.player_id = p.id
        WHERE q.opponent_player_id = ? 
        AND q.ranked_request = 1 
        AND q.ranked_accepted IS NULL
    ''', (player_id,))
    
    request = cursor.fetchone()
    conn.close()
    return dict(request) if request else None


def determine_match_ranked_status(bar_id, shot_caller_queue_id):
    """
    Determine if a match should be ranked based on:
    1. Bar/event ranked requirement (auto-ranked)
    2. Player request + acceptance
    Returns: (is_ranked, ranked_source)
    """
    # First check event/window based ranking
    is_event_ranked, source, _ = check_ranked_requirement(bar_id)
    if is_event_ranked:
        return True, 'event'
    
    # Check player-initiated ranked request
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT ranked_request, ranked_accepted, opponent_player_id
        FROM queue WHERE id = ?
    ''', (shot_caller_queue_id,))
    entry = cursor.fetchone()
    conn.close()
    
    if entry and entry['ranked_request'] == 1:
        # If opponent has no account, we can't require approval
        if entry['opponent_player_id'] is None:
            return False, None  # Guest opponent = unranked
        
        # If opponent accepted
        if entry['ranked_accepted'] == 1:
            return True, 'player'
    
    return False, None



# ============================================
# WALLET / BALANCE FUNCTIONS
# ============================================

def get_wallet_balance(player_id):
    """Get a player's current wallet balance."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT wallet_balance FROM players WHERE id = ?', (player_id,))
    row = cursor.fetchone()
    conn.close()
    return float(row['wallet_balance']) if row and row['wallet_balance'] else 0.00


def add_wallet_funds(player_id, amount, transaction_type, description=None, 
                     pool_night_id=None, game_id=None, stripe_payment_id=None):
    """
    Add funds to a player's wallet with transaction record.
    Returns (success, new_balance, transaction_id) or (False, error_message, None)
    """
    if amount <= 0:
        return False, "Amount must be positive", None
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Get current balance
        cursor.execute('SELECT wallet_balance FROM players WHERE id = ?', (player_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False, "Player not found", None
        
        balance_before = float(row['wallet_balance']) if row['wallet_balance'] else 0.00
        balance_after = balance_before + amount
        
        # Update balance
        cursor.execute('UPDATE players SET wallet_balance = ? WHERE id = ?', 
                      (balance_after, player_id))
        
        # Record transaction
        cursor.execute('''
            INSERT INTO wallet_transactions 
            (player_id, amount, transaction_type, description, pool_night_id, game_id, 
             stripe_payment_id, balance_before, balance_after)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (player_id, amount, transaction_type, description, pool_night_id, game_id,
              stripe_payment_id, balance_before, balance_after))
        
        transaction_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return True, balance_after, transaction_id
        
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, str(e), None



def deduct_wallet_funds(player_id, amount, transaction_type, description=None,
                        pool_night_id=None, game_id=None, allow_negative=False):
    """
    Deduct funds from a player's wallet with transaction record.
    Returns (success, new_balance, transaction_id) or (False, error_message, None)
    """
    if amount <= 0:
        return False, "Amount must be positive", None
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Get current balance
        cursor.execute('SELECT wallet_balance FROM players WHERE id = ?', (player_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False, "Player not found", None
        
        balance_before = float(row['wallet_balance']) if row['wallet_balance'] else 0.00
        balance_after = balance_before - amount
        
        # Check for insufficient funds
        if not allow_negative and balance_after < 0:
            conn.close()
            return False, "Insufficient funds", None
        
        # Update balance
        cursor.execute('UPDATE players SET wallet_balance = ? WHERE id = ?', 
                      (balance_after, player_id))
        
        # Record transaction (negative amount for debit)
        cursor.execute('''
            INSERT INTO wallet_transactions 
            (player_id, amount, transaction_type, description, pool_night_id, game_id,
             balance_before, balance_after)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (player_id, -amount, transaction_type, description, pool_night_id, game_id,
              balance_before, balance_after))
        
        transaction_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return True, balance_after, transaction_id
        
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, str(e), None


def get_wallet_transactions(player_id, limit=50):
    """Get a player's wallet transaction history."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT wt.*, pn.title as pool_night_title
        FROM wallet_transactions wt
        LEFT JOIN pool_nights pn ON wt.pool_night_id = pn.id
        WHERE wt.player_id = ?
        ORDER BY wt.created_at DESC
        LIMIT ?
    ''', (player_id, limit))
    transactions = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return transactions


def cashout_wallet_funds(player_id, amount):
    """
    Cash out funds from wallet to player's payout method.
    Returns (success, message, new_balance, payout_id)
    """
    if amount <= 0:
        return False, "Amount must be positive", None, None
    
    # Minimum cashout amount
    min_cashout = 10.00
    if amount < min_cashout:
        return False, f"Minimum cashout is ${min_cashout:.2f}", None, None
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Get current balance and payout method
        cursor.execute('SELECT wallet_balance, payout_method_id, payment_customer_id FROM players WHERE id = ?', (player_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False, "Player not found", None, None
        
        balance = float(row['wallet_balance']) if row['wallet_balance'] else 0.00
        
        if amount > balance:
            conn.close()
            return False, f"Insufficient balance. You have ${balance:.2f}", None, None
        
        # TODO: In production, integrate with Stripe Connect or similar:
        # 1. Verify payout_method_id exists
        # 2. Create payout via Stripe API
        # 3. Only deduct balance on successful payout initiation
        #
        # For now, we stub this and just do the accounting
        # payout_method_id = row['payout_method_id']
        # if not payout_method_id:
        #     conn.close()
        #     return False, "No payout method linked. Please add a bank account first.", None, None
        
        # Stub: Generate a fake payout reference
        import secrets
        payout_reference = f"po_stub_{secrets.token_hex(8)}"
        
        balance_after = balance - amount
        
        # Update balance
        cursor.execute('UPDATE players SET wallet_balance = ? WHERE id = ?', 
                      (balance_after, player_id))
        
        # Record transaction
        cursor.execute('''
            INSERT INTO wallet_transactions 
            (player_id, amount, transaction_type, description, stripe_payment_id, 
             balance_before, balance_after)
            VALUES (?, ?, 'cashout', ?, ?, ?, ?)
        ''', (player_id, -amount, f'Cashout to bank', payout_reference, balance, balance_after))
        
        transaction_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return True, "Cashout initiated successfully", balance_after, payout_reference
        
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, str(e), None, None



def pay_pool_night_entry_fee(player_id, pool_night_id):
    """
    Pay entry fee for a pool night from wallet balance.
    Returns (success, message, new_balance)
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Get pool night entry fee
        cursor.execute('SELECT entry_fee, title FROM pool_nights WHERE id = ?', (pool_night_id,))
        night = cursor.fetchone()
        if not night:
            conn.close()
            return False, "Pool night not found", None
        
        entry_fee = float(night['entry_fee']) if night['entry_fee'] else 0.00
        
        # If no entry fee, no payment needed
        if entry_fee <= 0:
            conn.close()
            return True, "No entry fee required", None
        
        # Check if already paid
        cursor.execute('''
            SELECT paid FROM pool_night_rsvps 
            WHERE pool_night_id = ? AND player_id = ?
        ''', (pool_night_id, player_id))
        rsvp = cursor.fetchone()
        if rsvp and rsvp['paid']:
            conn.close()
            return True, "Already paid", None
        
        conn.close()
        
        # Deduct the fee
        success, result, txn_id = deduct_wallet_funds(
            player_id, entry_fee, 'entry_fee',
            description=f"Entry fee for {night['title']}",
            pool_night_id=pool_night_id
        )
        
        if not success:
            return False, result, None
        
        # Mark RSVP as paid
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE pool_night_rsvps 
            SET paid = 1, amount_paid = ?
            WHERE pool_night_id = ? AND player_id = ?
        ''', (entry_fee, pool_night_id, player_id))
        
        # Add to prize pool
        cursor.execute('''
            UPDATE pool_nights 
            SET prize_pool = COALESCE(prize_pool, 0) + ?
            WHERE id = ?
        ''', (entry_fee, pool_night_id))
        
        conn.commit()
        conn.close()
        
        return True, "Entry fee paid successfully", result
        
    except Exception as e:
        conn.close()
        return False, str(e), None



def refund_pool_night_entry_fee(player_id, pool_night_id):
    """
    Refund entry fee for a cancelled RSVP.
    Returns (success, message, new_balance)
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Check if paid and not already refunded
        cursor.execute('''
            SELECT paid, amount_paid, refunded FROM pool_night_rsvps 
            WHERE pool_night_id = ? AND player_id = ?
        ''', (pool_night_id, player_id))
        rsvp = cursor.fetchone()
        
        if not rsvp or not rsvp['paid']:
            conn.close()
            return True, "No payment to refund", None
        
        if rsvp['refunded']:
            conn.close()
            return True, "Already refunded", None
        
        amount = float(rsvp['amount_paid']) if rsvp['amount_paid'] else 0.00
        
        # Get pool night title
        cursor.execute('SELECT title FROM pool_nights WHERE id = ?', (pool_night_id,))
        night = cursor.fetchone()
        title = night['title'] if night else f"Pool Night #{pool_night_id}"
        
        conn.close()
        
        # Add funds back
        success, result, txn_id = add_wallet_funds(
            player_id, amount, 'refund',
            description=f"Refund for {title}",
            pool_night_id=pool_night_id
        )
        
        if not success:
            return False, result, None
        
        # Mark as refunded
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE pool_night_rsvps 
            SET refunded = 1, refunded_at = CURRENT_TIMESTAMP
            WHERE pool_night_id = ? AND player_id = ?
        ''', (pool_night_id, player_id))
        
        # Subtract from prize pool
        cursor.execute('''
            UPDATE pool_nights 
            SET prize_pool = MAX(0, COALESCE(prize_pool, 0) - ?)
            WHERE id = ?
        ''', (amount, pool_night_id))
        
        conn.commit()
        conn.close()
        
        return True, "Refund processed", result
        
    except Exception as e:
        conn.close()
        return False, str(e), None


def distribute_pool_night_winnings(pool_night_id, placements):
    """
    Distribute winnings to players after a pool night.
    placements: list of dicts with {'player_id': int, 'placement': int, 'amount': float}
    Returns (success, message, payouts_made)
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Get pool night info
        cursor.execute('SELECT title, prize_pool FROM pool_nights WHERE id = ?', (pool_night_id,))
        night = cursor.fetchone()
        if not night:
            conn.close()
            return False, "Pool night not found", []
        
        title = night['title']
        payouts_made = []
        
        for placement in placements:
            player_id = placement['player_id']
            place = placement.get('placement', 0)
            amount = float(placement['amount'])
            
            if amount <= 0:
                continue
            
            # Record the payout
            cursor.execute('''
                INSERT INTO pool_night_payouts 
                (pool_night_id, player_id, placement, amount, paid_out, paid_out_at)
                VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
            ''', (pool_night_id, player_id, place, amount))
            
            conn.commit()
            conn.close()
            
            # Add to player's wallet
            place_str = f"{place}{'st' if place == 1 else 'nd' if place == 2 else 'rd' if place == 3 else 'th'} place"
            success, new_balance, txn_id = add_wallet_funds(
                player_id, amount, 'winnings',
                description=f"{place_str} winnings - {title}",
                pool_night_id=pool_night_id
            )
            
            if success:
                payouts_made.append({
                    'player_id': player_id,
                    'placement': place,
                    'amount': amount,
                    'new_balance': new_balance
                })
            
            conn = get_db()
            cursor = conn.cursor()
        
        conn.close()
        return True, f"Distributed winnings to {len(payouts_made)} players", payouts_made
        
    except Exception as e:
        conn.close()
        return False, str(e), []


def set_payment_customer_id(player_id, customer_id):
    """Store the external payment provider customer ID."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE players SET payment_customer_id = ? WHERE id = ?', 
                  (customer_id, player_id))
    conn.commit()
    conn.close()


def get_payment_customer_id(player_id):
    """Get the external payment provider customer ID."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT payment_customer_id FROM players WHERE id = ?', (player_id,))
    row = cursor.fetchone()
    conn.close()
    return row['payment_customer_id'] if row else None



def record_pool_night_payout(pool_night_id, player_id, amount, placement=0):
    """
    Record a single payout to a player for a pool night.
    Returns (success, message)
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Get pool night info
        cursor.execute('SELECT title, prize_pool FROM pool_nights WHERE id = ?', (pool_night_id,))
        night = cursor.fetchone()
        if not night:
            conn.close()
            return False, "Pool night not found"
        
        title = night['title'] or 'Pool Night'
        
        # Check if this player already has a payout for this placement
        cursor.execute('''
            SELECT id FROM pool_night_payouts 
            WHERE pool_night_id = ? AND player_id = ? AND placement = ?
        ''', (pool_night_id, player_id, placement))
        existing = cursor.fetchone()
        if existing:
            conn.close()
            return False, "Payout already recorded for this placement"
        
        # Record the payout
        cursor.execute('''
            INSERT INTO pool_night_payouts 
            (pool_night_id, player_id, placement, amount, paid_out, paid_out_at)
            VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
        ''', (pool_night_id, player_id, placement, amount))
        
        conn.commit()
        conn.close()
        
        # Add to player's wallet
        if placement > 0:
            place_str = f"{placement}{'st' if placement == 1 else 'nd' if placement == 2 else 'rd' if placement == 3 else 'th'} place"
            description = f"{place_str} winnings - {title}"
        else:
            description = f"Winnings - {title}"
        
        success, result, txn_id = add_wallet_funds(
            player_id, amount, 'winnings',
            description=description,
            pool_night_id=pool_night_id
        )
        
        if success:
            return True, f"${amount:.2f} added to player wallet"
        else:
            return False, f"Payout recorded but wallet update failed: {result}"
        
    except Exception as e:
        conn.close()
        return False, str(e)


# ============================================
# ANTI-TAMPERING SYSTEM FUNCTIONS
# ============================================

def create_board_session(bar_id, authorized_by_user_id=None, device_name=None, hours_valid=24):
    """Create an authorized board control session."""
    import secrets
    conn = get_db()
    cursor = conn.cursor()
    
    session_token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(hours=hours_valid)
    
    cursor.execute('''
        INSERT INTO board_sessions (bar_id, session_token, authorized_by_user_id, device_name, expires_at, last_activity_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
    ''', (bar_id, session_token, authorized_by_user_id, device_name, expires_at))
    
    conn.commit()
    session_id = cursor.lastrowid
    conn.close()
    
    return session_id, session_token

def validate_board_session(session_token, bar_id=None):
    """Validate a board session token. Returns session dict or None."""
    if not session_token:
        return None
    
    conn = get_db()
    cursor = conn.cursor()
    
    query = '''
        SELECT * FROM board_sessions 
        WHERE session_token = ? 
        AND is_active = 1 
        AND (expires_at IS NULL OR expires_at > datetime('now'))
    '''
    params = [session_token]
    
    if bar_id:
        query += ' AND bar_id = ?'
        params.append(bar_id)
    
    cursor.execute(query, params)
    session = cursor.fetchone()
    
    if session:
        # Update last activity
        cursor.execute('UPDATE board_sessions SET last_activity_at = datetime("now") WHERE id = ?', (session['id'],))
        conn.commit()
    
    conn.close()
    return dict(session) if session else None

def revoke_board_session(session_token):
    """Revoke a board session."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE board_sessions SET is_active = 0 WHERE session_token = ?', (session_token,))
    conn.commit()
    conn.close()


def log_match_action(action, match_id=None, game_history_id=None, bar_id=None, 
                     details=None, performed_by_user_id=None, performed_by_type='system',
                     ip_address=None, user_agent=None):
    """Log a match-related action for audit trail."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO match_audit_log 
        (match_id, game_history_id, bar_id, action, details, performed_by_user_id, 
         performed_by_type, ip_address, user_agent)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (match_id, game_history_id, bar_id, action, details, performed_by_user_id,
          performed_by_type, ip_address, user_agent))
    
    conn.commit()
    log_id = cursor.lastrowid
    conn.close()
    return log_id

def create_active_match(bar_id, player1_id, player2_id, player1_queue_id=None, player2_queue_id=None,
                        is_ranked=False, ranked_source=None, pool_night_id=None, entry_fee=0,
                        created_by_user_id=None):
    """Create an active match record (server source of truth)."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO active_matches 
        (bar_id, player1_id, player2_id, player1_queue_id, player2_queue_id,
         is_ranked, ranked_source, pool_night_id, entry_fee, created_by_user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (bar_id, player1_id, player2_id, player1_queue_id, player2_queue_id,
          1 if is_ranked else 0, ranked_source, pool_night_id, entry_fee, created_by_user_id))
    
    conn.commit()
    match_id = cursor.lastrowid
    conn.close()
    
    # Log the action
    details = f"Players: {player1_id} vs {player2_id}"
    if is_ranked:
        details += f" (Ranked: {ranked_source})"
    if pool_night_id:
        details += f" (Pool Night: {pool_night_id})"
    
    log_match_action('match_created', match_id=match_id, bar_id=bar_id, 
                     details=details, performed_by_user_id=created_by_user_id)
    
    return match_id

def get_active_match(bar_id):
    """Get the current active match for a bar."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT am.*, 
               p1.nickname as player1_name, 
               p2.nickname as player2_name
        FROM active_matches am
        LEFT JOIN players p1 ON am.player1_id = p1.id
        LEFT JOIN players p2 ON am.player2_id = p2.id
        WHERE am.bar_id = ? AND am.status = 'in_progress'
        ORDER BY am.started_at DESC
        LIMIT 1
    ''', (bar_id,))
    
    match = cursor.fetchone()
    conn.close()
    return dict(match) if match else None


def record_match_result(match_id, winner_id, recorded_by_user_id=None, recorded_by_type='system'):
    """Record a match result (pending confirmation for ranked/paid matches)."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get match details
    cursor.execute('SELECT * FROM active_matches WHERE id = ?', (match_id,))
    match = cursor.fetchone()
    
    if not match:
        conn.close()
        return False, "Match not found"
    
    if match['result_locked']:
        conn.close()
        return False, "Match result is locked and cannot be changed"
    
    # For ranked/paid matches, result needs confirmation
    needs_confirmation = match['is_ranked'] or match['pool_night_id'] is not None
    
    cursor.execute('''
        UPDATE active_matches 
        SET result_winner_id = ?, 
            result_confirmed = ?,
            ended_at = datetime('now')
        WHERE id = ?
    ''', (winner_id, 0 if needs_confirmation else 1, match_id))
    
    conn.commit()
    conn.close()
    
    # Log the action
    loser_id = match['player2_id'] if winner_id == match['player1_id'] else match['player1_id']
    details = f"Winner: {winner_id}, Loser: {loser_id}"
    if needs_confirmation:
        details += " (awaiting confirmation)"
    
    log_match_action('result_recorded', match_id=match_id, bar_id=match['bar_id'],
                     details=details, performed_by_user_id=recorded_by_user_id,
                     performed_by_type=recorded_by_type)
    
    return True, "Result recorded" + (" - awaiting confirmation" if needs_confirmation else "")

def confirm_match_result(match_id, confirming_player_id=None, confirmed_by_host=False, host_user_id=None):
    """Confirm a match result. For ranked/paid matches, needs both players OR host."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM active_matches WHERE id = ?', (match_id,))
    match = cursor.fetchone()
    
    if not match:
        conn.close()
        return False, "Match not found"
    
    if match['result_locked']:
        conn.close()
        return False, "Match already locked"
    
    if match['result_winner_id'] is None:
        conn.close()
        return False, "No result to confirm"
    
    updates = []
    params = []
    
    if confirmed_by_host:
        updates.append('host_confirmed = 1')
        updates.append('result_confirmed = 1')
        updates.append('result_locked = 1')
        updates.append("status = 'completed'")
    elif confirming_player_id:
        if confirming_player_id == match['player1_id']:
            updates.append('player1_confirmed = 1')
        elif confirming_player_id == match['player2_id']:
            updates.append('player2_confirmed = 1')
        else:
            conn.close()
            return False, "Player not in this match"
    
    if updates:
        cursor.execute(f'UPDATE active_matches SET {", ".join(updates)} WHERE id = ?', (match_id,))
        
        # Check if both players confirmed
        cursor.execute('SELECT player1_confirmed, player2_confirmed FROM active_matches WHERE id = ?', (match_id,))
        updated = cursor.fetchone()
        
        if updated['player1_confirmed'] and updated['player2_confirmed']:
            cursor.execute('''
                UPDATE active_matches 
                SET result_confirmed = 1, result_locked = 1, status = 'completed'
                WHERE id = ?
            ''', (match_id,))
        
        conn.commit()
    
    conn.close()
    
    # Log confirmation
    if confirmed_by_host:
        log_match_action('result_confirmed_by_host', match_id=match_id, bar_id=match['bar_id'],
                         performed_by_user_id=host_user_id, performed_by_type='host')
    else:
        log_match_action('result_confirmed_by_player', match_id=match_id, bar_id=match['bar_id'],
                         details=f"Player: {confirming_player_id}", performed_by_user_id=confirming_player_id,
                         performed_by_type='player')
    
    return True, "Confirmation recorded"


def get_match_audit_log(match_id=None, bar_id=None, limit=100):
    """Get audit log entries for a match or bar."""
    conn = get_db()
    cursor = conn.cursor()
    
    query = '''
        SELECT mal.*, p.nickname as performer_name
        FROM match_audit_log mal
        LEFT JOIN players p ON mal.performed_by_user_id = p.id
        WHERE 1=1
    '''
    params = []
    
    if match_id:
        query += ' AND mal.match_id = ?'
        params.append(match_id)
    if bar_id:
        query += ' AND mal.bar_id = ?'
        params.append(bar_id)
    
    query += ' ORDER BY mal.created_at DESC LIMIT ?'
    params.append(limit)
    
    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()
    return [dict(r) for r in results]

def cancel_active_match(match_id, cancelled_by_user_id=None, cancelled_by_type='system', reason=None):
    """Cancel an active match. Restricted for ranked/paid matches."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM active_matches WHERE id = ?', (match_id,))
    match = cursor.fetchone()
    
    if not match:
        conn.close()
        return False, "Match not found"
    
    if match['result_locked']:
        conn.close()
        return False, "Cannot cancel a locked match"
    
    # For ranked/paid matches, only hosts can cancel
    is_protected = match['is_ranked'] or match['pool_night_id'] is not None
    if is_protected and cancelled_by_type not in ['host', 'admin']:
        conn.close()
        return False, "Only staff can cancel ranked/paid matches"
    
    cursor.execute('''
        UPDATE active_matches 
        SET status = 'cancelled', ended_at = datetime('now')
        WHERE id = ?
    ''', (match_id,))
    
    conn.commit()
    conn.close()
    
    details = reason or "Match cancelled"
    log_match_action('match_cancelled', match_id=match_id, bar_id=match['bar_id'],
                     details=details, performed_by_user_id=cancelled_by_user_id,
                     performed_by_type=cancelled_by_type)
    
    return True, "Match cancelled"

def get_queue_state(bar_id):
    """Get full queue state for a bar (server source of truth)."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get queue entries
    cursor.execute('''
        SELECT q.*, p.nickname, p.account_id
        FROM queue q
        JOIN players p ON q.player_id = p.id
        WHERE q.bar_id = ? AND q.status IN ('waiting', 'playing')
        ORDER BY q.position ASC
    ''', (bar_id,))
    queue = [dict(r) for r in cursor.fetchall()]
    
    # Get active match if any
    cursor.execute('''
        SELECT am.*, 
               p1.nickname as player1_name, 
               p2.nickname as player2_name
        FROM active_matches am
        LEFT JOIN players p1 ON am.player1_id = p1.id
        LEFT JOIN players p2 ON am.player2_id = p2.id
        WHERE am.bar_id = ? AND am.status = 'in_progress'
        ORDER BY am.started_at DESC
        LIMIT 1
    ''', (bar_id,))
    active_match = cursor.fetchone()
    
    conn.close()
    
    return {
        'queue': queue,
        'active_match': dict(active_match) if active_match else None,
        'king': queue[0] if queue else None,
        'challenger': queue[1] if len(queue) > 1 else None,
        'waiting': queue[2:] if len(queue) > 2 else []
    }

def clear_queue_authorized(bar_id, cleared_by_user_id, cleared_by_type='host'):
    """Clear queue with authorization check. Logs the action."""
    if cleared_by_type not in ['host', 'admin']:
        return False, "Unauthorized: only staff can clear the queue"
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check for active ranked/paid matches
    cursor.execute('''
        SELECT COUNT(*) as count FROM active_matches 
        WHERE bar_id = ? AND status = 'in_progress' 
        AND (is_ranked = 1 OR pool_night_id IS NOT NULL)
    ''', (bar_id,))
    protected = cursor.fetchone()['count']
    
    if protected > 0:
        conn.close()
        return False, "Cannot clear queue: active ranked/paid match in progress"
    
    # Get count before clearing
    cursor.execute('SELECT COUNT(*) as count FROM queue WHERE bar_id = ?', (bar_id,))
    count = cursor.fetchone()['count']
    
    cursor.execute('DELETE FROM queue WHERE bar_id = ?', (bar_id,))
    conn.commit()
    conn.close()
    
    log_match_action('queue_cleared', bar_id=bar_id, details=f"Cleared {count} entries",
                     performed_by_user_id=cleared_by_user_id, performed_by_type=cleared_by_type)
    
    return True, f"Queue cleared ({count} entries removed)"


def record_match_result(match_id, winner_id, performed_by_user_id=None, performed_by_type='system'):
    """Record a match result (pending confirmation for ranked/paid)."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM active_matches WHERE id = ?', (match_id,))
    match = cursor.fetchone()
    
    if not match:
        conn.close()
        return False, "Match not found"
    
    if match['result_locked']:
        conn.close()
        return False, "Match result is locked and cannot be changed"
    
    # For ranked/paid matches, result needs confirmation
    needs_confirmation = match['is_ranked'] or match['pool_night_id'] or match['entry_fee'] > 0
    
    cursor.execute('''
        UPDATE active_matches 
        SET result_winner_id = ?, 
            result_confirmed = ?,
            ended_at = datetime('now')
        WHERE id = ?
    ''', (winner_id, 0 if needs_confirmation else 1, match_id))
    
    conn.commit()
    conn.close()
    
    # Log the action
    loser_id = match['player2_id'] if winner_id == match['player1_id'] else match['player1_id']
    details = f"Winner: {winner_id}, Loser: {loser_id}"
    if needs_confirmation:
        details += " (Pending confirmation)"
    
    log_match_action('result_recorded', match_id=match_id, bar_id=match['bar_id'],
                     details=details, performed_by_user_id=performed_by_user_id,
                     performed_by_type=performed_by_type)
    
    return True, "Result recorded" + (" (pending confirmation)" if needs_confirmation else "")

def confirm_match_result(match_id, confirming_player_id=None, is_host=False, performed_by_user_id=None):
    """Confirm a match result. Both players or host must confirm for ranked/paid."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM active_matches WHERE id = ?', (match_id,))
    match = cursor.fetchone()
    
    if not match:
        conn.close()
        return False, "Match not found"
    
    if match['result_locked']:
        conn.close()
        return False, "Match already locked"
    
    if not match['result_winner_id']:
        conn.close()
        return False, "No result to confirm"
    
    # Update confirmation status
    if is_host:
        cursor.execute('UPDATE active_matches SET host_confirmed = 1 WHERE id = ?', (match_id,))
    elif confirming_player_id == match['player1_id']:
        cursor.execute('UPDATE active_matches SET player1_confirmed = 1 WHERE id = ?', (match_id,))
    elif confirming_player_id == match['player2_id']:
        cursor.execute('UPDATE active_matches SET player2_confirmed = 1 WHERE id = ?', (match_id,))
    else:
        conn.close()
        return False, "Not a participant in this match"
    
    conn.commit()
    
    # Check if fully confirmed
    cursor.execute('SELECT * FROM active_matches WHERE id = ?', (match_id,))
    match = cursor.fetchone()
    
    is_ranked_or_paid = match['is_ranked'] or match['pool_night_id'] or match['entry_fee'] > 0
    
    # For ranked/paid: need both players OR host confirmation
    # For casual: auto-confirm
    fully_confirmed = False
    if is_ranked_or_paid:
        if match['host_confirmed']:
            fully_confirmed = True
        elif match['player1_confirmed'] and match['player2_confirmed']:
            fully_confirmed = True
    else:
        fully_confirmed = True
    
    if fully_confirmed:
        cursor.execute('''
            UPDATE active_matches 
            SET result_confirmed = 1, result_locked = 1, status = 'completed'
            WHERE id = ?
        ''', (match_id,))
        conn.commit()
        
        log_match_action('result_confirmed_locked', match_id=match_id, bar_id=match['bar_id'],
                         details=f"Winner: {match['result_winner_id']}", 
                         performed_by_user_id=performed_by_user_id)
    
    conn.close()
    return True, "Confirmed" + (" and locked" if fully_confirmed else " (awaiting other confirmation)")


def cancel_match(match_id, reason=None, performed_by_user_id=None, performed_by_type='system', force=False):
    """Cancel an active match. Cannot cancel locked matches without force."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM active_matches WHERE id = ?', (match_id,))
    match = cursor.fetchone()
    
    if not match:
        conn.close()
        return False, "Match not found"
    
    if match['result_locked'] and not force:
        conn.close()
        return False, "Cannot cancel a locked match"
    
    cursor.execute('''
        UPDATE active_matches 
        SET status = 'cancelled', ended_at = datetime('now')
        WHERE id = ?
    ''', (match_id,))
    
    conn.commit()
    conn.close()
    
    details = f"Reason: {reason}" if reason else "No reason provided"
    if force:
        details += " (FORCE OVERRIDE)"
    
    log_match_action('match_cancelled', match_id=match_id, bar_id=match['bar_id'],
                     details=details, performed_by_user_id=performed_by_user_id,
                     performed_by_type=performed_by_type)
    
    return True, "Match cancelled"

def get_match_audit_log(match_id=None, bar_id=None, limit=100):
    """Get audit log entries for matches."""
    conn = get_db()
    cursor = conn.cursor()
    
    query = 'SELECT * FROM match_audit_log WHERE 1=1'
    params = []
    
    if match_id:
        query += ' AND match_id = ?'
        params.append(match_id)
    if bar_id:
        query += ' AND bar_id = ?'
        params.append(bar_id)
    
    query += ' ORDER BY created_at DESC LIMIT ?'
    params.append(limit)
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(r) for r in rows]

def get_queue_state(bar_id):
    """Get complete queue state for a bar (server source of truth)."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get queue entries
    cursor.execute('''
        SELECT q.*, p.nickname, p.id as player_id
        FROM queue q
        JOIN players p ON q.player_id = p.id
        WHERE q.bar_id = ? AND q.status IN ('waiting', 'playing')
        ORDER BY q.position ASC
    ''', (bar_id,))
    queue = [dict(r) for r in cursor.fetchall()]
    
    # Get active match if any
    cursor.execute('''
        SELECT am.*, 
               p1.nickname as player1_name, 
               p2.nickname as player2_name
        FROM active_matches am
        LEFT JOIN players p1 ON am.player1_id = p1.id
        LEFT JOIN players p2 ON am.player2_id = p2.id
        WHERE am.bar_id = ? AND am.status = 'in_progress'
        ORDER BY am.started_at DESC
        LIMIT 1
    ''', (bar_id,))
    active_match = cursor.fetchone()
    
    conn.close()
    
    return {
        'queue': queue,
        'active_match': dict(active_match) if active_match else None,
        'king': queue[0] if queue else None,
        'challenger': queue[1] if len(queue) > 1 else None,
        'waiting': queue[2:] if len(queue) > 2 else []
    }

def clear_queue(bar_id, performed_by_user_id=None, performed_by_type='host'):
    """Clear all queue entries for a bar. Requires authorization."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get count before clearing
    cursor.execute('SELECT COUNT(*) as cnt FROM queue WHERE bar_id = ?', (bar_id,))
    count = cursor.fetchone()['cnt']
    
    cursor.execute('DELETE FROM queue WHERE bar_id = ?', (bar_id,))
    conn.commit()
    conn.close()
    
    log_match_action('queue_cleared', bar_id=bar_id,
                     details=f"Cleared {count} entries",
                     performed_by_user_id=performed_by_user_id,
                     performed_by_type=performed_by_type)
    
    return True, f"Cleared {count} queue entries"


def record_match_result(match_id, winner_id, recorded_by_user_id=None, recorded_by_type='system'):
    """Record a match result (pending confirmation for ranked/paid matches)."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM active_matches WHERE id = ?', (match_id,))
    match = cursor.fetchone()
    
    if not match:
        conn.close()
        return False, "Match not found"
    
    if match['result_locked']:
        conn.close()
        return False, "Match result is already locked"
    
    # For ranked/paid matches, result needs confirmation
    needs_confirmation = match['is_ranked'] or match['pool_night_id'] or match['entry_fee'] > 0
    
    cursor.execute('''
        UPDATE active_matches 
        SET result_winner_id = ?, 
            result_confirmed = ?,
            ended_at = CASE WHEN ? = 1 THEN datetime('now') ELSE ended_at END
        WHERE id = ?
    ''', (winner_id, 0 if needs_confirmation else 1, 0 if needs_confirmation else 1, match_id))
    
    conn.commit()
    conn.close()
    
    # Log the action
    loser_id = match['player2_id'] if winner_id == match['player1_id'] else match['player1_id']
    details = f"Winner: {winner_id}, Loser: {loser_id}"
    if needs_confirmation:
        details += " (awaiting confirmation)"
    
    log_match_action('result_recorded', match_id=match_id, bar_id=match['bar_id'],
                     details=details, performed_by_user_id=recorded_by_user_id,
                     performed_by_type=recorded_by_type)
    
    return True, "Result recorded" + (" - awaiting confirmation" if needs_confirmation else "")

def confirm_match_result(match_id, confirming_player_id=None, confirming_host_id=None):
    """Confirm a match result. For ranked/paid, needs both players or host."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM active_matches WHERE id = ?', (match_id,))
    match = cursor.fetchone()
    
    if not match:
        conn.close()
        return False, "Match not found"
    
    if match['result_locked']:
        conn.close()
        return False, "Match already locked"
    
    if not match['result_winner_id']:
        conn.close()
        return False, "No result to confirm"
    
    # Update confirmation status
    update_fields = []
    if confirming_player_id == match['player1_id']:
        update_fields.append('player1_confirmed = 1')
    elif confirming_player_id == match['player2_id']:
        update_fields.append('player2_confirmed = 1')
    
    if confirming_host_id:
        update_fields.append('host_confirmed = 1')
    
    if update_fields:
        cursor.execute(f'UPDATE active_matches SET {", ".join(update_fields)} WHERE id = ?', (match_id,))
        conn.commit()
    
    # Refresh match data
    cursor.execute('SELECT * FROM active_matches WHERE id = ?', (match_id,))
    match = dict(cursor.fetchone())
    
    # Check if fully confirmed
    is_ranked_or_paid = match['is_ranked'] or match['pool_night_id'] or match['entry_fee'] > 0
    
    if is_ranked_or_paid:
        # Need both players OR host confirmation
        both_players = match['player1_confirmed'] and match['player2_confirmed']
        has_host = match['host_confirmed']
        fully_confirmed = both_players or has_host
    else:
        fully_confirmed = True
    
    if fully_confirmed:
        cursor.execute('''
            UPDATE active_matches 
            SET result_confirmed = 1, result_locked = 1, status = 'completed', ended_at = datetime('now')
            WHERE id = ?
        ''', (match_id,))
        conn.commit()
        
        log_match_action('result_confirmed_and_locked', match_id=match_id, bar_id=match['bar_id'],
                         details=f"Winner: {match['result_winner_id']}")
    
    conn.close()
    return True, "Confirmation recorded" + (" - result locked" if fully_confirmed else "")


def cancel_active_match(match_id, cancelled_by_user_id=None, cancelled_by_type='system', reason=None):
    """Cancel an active match. Restricted for ranked/paid matches."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM active_matches WHERE id = ?', (match_id,))
    match = cursor.fetchone()
    
    if not match:
        conn.close()
        return False, "Match not found"
    
    if match['result_locked']:
        conn.close()
        return False, "Cannot cancel a locked match"
    
    # For ranked/paid, only host/admin can cancel
    is_protected = match['is_ranked'] or match['pool_night_id'] or match['entry_fee'] > 0
    if is_protected and cancelled_by_type not in ['host', 'admin']:
        conn.close()
        return False, "Only bar host or admin can cancel ranked/paid matches"
    
    cursor.execute('''
        UPDATE active_matches SET status = 'cancelled', ended_at = datetime('now')
        WHERE id = ?
    ''', (match_id,))
    
    conn.commit()
    conn.close()
    
    details = f"Reason: {reason}" if reason else "No reason provided"
    log_match_action('match_cancelled', match_id=match_id, bar_id=match['bar_id'],
                     details=details, performed_by_user_id=cancelled_by_user_id,
                     performed_by_type=cancelled_by_type)
    
    return True, "Match cancelled"

def get_match_audit_log(match_id=None, bar_id=None, limit=100):
    """Get audit log entries for matches."""
    conn = get_db()
    cursor = conn.cursor()
    
    query = '''
        SELECT mal.*, p.nickname as performed_by_name
        FROM match_audit_log mal
        LEFT JOIN players p ON mal.performed_by_user_id = p.id
        WHERE 1=1
    '''
    params = []
    
    if match_id:
        query += ' AND mal.match_id = ?'
        params.append(match_id)
    
    if bar_id:
        query += ' AND mal.bar_id = ?'
        params.append(bar_id)
    
    query += ' ORDER BY mal.created_at DESC LIMIT ?'
    params.append(limit)
    
    cursor.execute(query, params)
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return logs

def get_pending_confirmations(player_id):
    """Get matches awaiting this player's confirmation."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT am.*, 
               p1.nickname as player1_name,
               p2.nickname as player2_name,
               pw.nickname as winner_name
        FROM active_matches am
        LEFT JOIN players p1 ON am.player1_id = p1.id
        LEFT JOIN players p2 ON am.player2_id = p2.id
        LEFT JOIN players pw ON am.result_winner_id = pw.id
        WHERE am.result_winner_id IS NOT NULL
        AND am.result_locked = 0
        AND (
            (am.player1_id = ? AND am.player1_confirmed = 0)
            OR (am.player2_id = ? AND am.player2_confirmed = 0)
        )
        ORDER BY am.ended_at DESC
    ''', (player_id, player_id))
    
    matches = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return matches


# ============================================
# MANUAL INVITE SYSTEM
# ============================================

def send_manual_invite(sender_id, contact_type, contact_value, contact_name=None):
    """
    Send/record a manual invite. Rate limited to 1 per contact per 7 days.
    Returns (success, message, invite_id)
    """
    from datetime import datetime, timedelta
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Normalize contact value
    contact_value = contact_value.strip().lower()
    
    # Check for recent invite to same contact (within 7 days)
    seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
    cursor.execute('''
        SELECT id, last_sent_at, send_count, status FROM manual_invites
        WHERE sender_id = ? AND contact_type = ? AND contact_value = ?
        ORDER BY last_sent_at DESC LIMIT 1
    ''', (sender_id, contact_type, contact_value))
    existing = cursor.fetchone()
    
    if existing:
        existing = dict(existing)
        # If already completed, don't allow re-inviting
        if existing['status'] == 'joined':
            conn.close()
            return False, "This friend has already joined!", None
        
        # Check if within rate limit window
        if existing['last_sent_at'] > seven_days_ago:
            conn.close()
            return False, "You've recently invited this friend. Try again in a few days.", existing['id']
    
    # Get sender's referral code
    cursor.execute('SELECT referral_code FROM players WHERE id = ?', (sender_id,))
    player = cursor.fetchone()
    if not player or not player['referral_code']:
        # Create referral code if needed
        referral_code = get_or_create_referral_code(sender_id)
    else:
        referral_code = player['referral_code']
    
    if existing:
        # Update existing invite
        cursor.execute('''
            UPDATE manual_invites 
            SET last_sent_at = datetime('now'), 
                send_count = send_count + 1,
                contact_name = COALESCE(?, contact_name)
            WHERE id = ?
        ''', (contact_name, existing['id']))
        invite_id = existing['id']
    else:
        # Create new invite
        cursor.execute('''
            INSERT INTO manual_invites (sender_id, contact_type, contact_value, contact_name, referral_code)
            VALUES (?, ?, ?, ?, ?)
        ''', (sender_id, contact_type, contact_value, contact_name, referral_code))
        invite_id = cursor.lastrowid
    
    conn.commit()
    conn.close()
    
    return True, "Invite sent!", invite_id


def get_manual_invites(sender_id):
    """Get all manual invites sent by a user."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT mi.*, p.nickname as signed_up_nickname
        FROM manual_invites mi
        LEFT JOIN players p ON mi.signed_up_player_id = p.id
        WHERE mi.sender_id = ?
        ORDER BY mi.last_sent_at DESC
        LIMIT 100
    ''', (sender_id,))
    
    invites = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return invites


def get_manual_invite_stats(sender_id):
    """Get stats about manual invites."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            COUNT(*) as total_sent,
            SUM(CASE WHEN status = 'joined' THEN 1 ELSE 0 END) as total_joined,
            SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as total_pending
        FROM manual_invites
        WHERE sender_id = ?
    ''', (sender_id,))
    
    stats = dict(cursor.fetchone())
    conn.close()
    return stats


def check_manual_invite_on_signup(email=None, phone=None):
    """
    Check if a new signup matches any pending manual invites.
    Returns the invite record if found, or None.
    """
    if not email and not phone:
        return None
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check by email first
    if email:
        cursor.execute('''
            SELECT * FROM manual_invites 
            WHERE contact_type = 'email' AND contact_value = ? AND status = 'sent'
            ORDER BY last_sent_at DESC LIMIT 1
        ''', (email.strip().lower(),))
        invite = cursor.fetchone()
        if invite:
            conn.close()
            return dict(invite)
    
    # Check by phone
    if phone:
        # Normalize phone number (remove non-digits)
        import re
        phone_digits = re.sub(r'\D', '', phone)
        cursor.execute('''
            SELECT * FROM manual_invites 
            WHERE contact_type = 'phone' AND REPLACE(REPLACE(REPLACE(contact_value, '-', ''), ' ', ''), '+', '') LIKE ?
            AND status = 'sent'
            ORDER BY last_sent_at DESC LIMIT 1
        ''', (f'%{phone_digits[-10:]}',))  # Match last 10 digits
        invite = cursor.fetchone()
        if invite:
            conn.close()
            return dict(invite)
    
    conn.close()
    return None


def complete_manual_invite(invite_id, signed_up_player_id):
    """Mark a manual invite as completed when the invited person signs up."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE manual_invites 
        SET status = 'joined', 
            signed_up_player_id = ?, 
            completed_at = datetime('now')
        WHERE id = ?
    ''', (signed_up_player_id, invite_id))
    
    conn.commit()
    conn.close()



# ============================================
# VERIFICATION CODE FUNCTIONS
# ============================================

def generate_verification_code():
    """Generate a 6-digit verification code."""
    import random
    return str(random.randint(100000, 999999))


def create_verification(user_id, channel, destination, expires_minutes=10):
    """
    Create a verification code for phone or email.
    Returns the code if successful, None if rate-limited.
    """
    from datetime import datetime, timedelta
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check for existing pending verification within cooldown (60 seconds)
    cursor.execute('''
        SELECT id, created_at FROM verifications 
        WHERE user_id = ? AND channel = ? AND status = 'pending'
        ORDER BY created_at DESC LIMIT 1
    ''', (user_id, channel))
    existing = cursor.fetchone()
    
    if existing:
        created_at = datetime.strptime(existing['created_at'], '%Y-%m-%d %H:%M:%S')
        cooldown_end = created_at + timedelta(seconds=60)
        if datetime.now() < cooldown_end:
            conn.close()
            return None  # Rate limited
        
        # Expire the old one
        cursor.execute('UPDATE verifications SET status = ? WHERE id = ?', ('expired', existing['id']))
    
    # Generate new code
    code = generate_verification_code()
    expires_at = (datetime.now() + timedelta(minutes=expires_minutes)).strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute('''
        INSERT INTO verifications (user_id, channel, destination, code, status, expires_at)
        VALUES (?, ?, ?, ?, 'pending', ?)
    ''', (user_id, channel, destination, code, expires_at))
    
    # Update player's verification sent timestamp
    if channel == 'phone':
        cursor.execute('UPDATE players SET phone_verification_sent_at = datetime("now") WHERE id = ?', (user_id,))
    else:
        cursor.execute('UPDATE players SET email_verification_sent_at = datetime("now") WHERE id = ?', (user_id,))
    
    conn.commit()
    conn.close()
    
    return code


def verify_code(user_id, channel, code):
    """
    Verify a code for phone or email.
    Returns: {'success': True/False, 'error': 'message if failed'}
    """
    from datetime import datetime
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get pending verification
    cursor.execute('''
        SELECT id, code, expires_at, attempts FROM verifications 
        WHERE user_id = ? AND channel = ? AND status = 'pending'
        ORDER BY created_at DESC LIMIT 1
    ''', (user_id, channel))
    verification = cursor.fetchone()
    
    if not verification:
        conn.close()
        return {'success': False, 'error': 'No pending verification found. Please request a new code.'}
    
    # Check expiration
    expires_at = datetime.strptime(verification['expires_at'], '%Y-%m-%d %H:%M:%S')
    if datetime.now() > expires_at:
        cursor.execute('UPDATE verifications SET status = ? WHERE id = ?', ('expired', verification['id']))
        conn.commit()
        conn.close()
        return {'success': False, 'error': 'This code has expired. Please request a new one.', 'expired': True}
    
    # Check attempts (max 5)
    if verification['attempts'] >= 5:
        cursor.execute('UPDATE verifications SET status = ? WHERE id = ?', ('rejected', verification['id']))
        conn.commit()
        conn.close()
        return {'success': False, 'error': 'Too many failed attempts. Please request a new code.', 'rejected': True}
    
    # Verify code
    if verification['code'] != code:
        cursor.execute('UPDATE verifications SET attempts = attempts + 1 WHERE id = ?', (verification['id'],))
        conn.commit()
        remaining = 5 - verification['attempts'] - 1
        conn.close()
        return {'success': False, 'error': f'Invalid code. {remaining} attempts remaining.'}
    
    # Success - mark verified
    cursor.execute('''
        UPDATE verifications SET status = 'verified', verified_at = datetime('now') WHERE id = ?
    ''', (verification['id'],))
    
    # Update player's verified status
    if channel == 'phone':
        cursor.execute('UPDATE players SET phone_verified = 1 WHERE id = ?', (user_id,))
    else:
        cursor.execute('UPDATE players SET email_verified = 1 WHERE id = ?', (user_id,))
    
    conn.commit()
    conn.close()
    
    return {'success': True}


def get_verification_status(user_id):
    """Get verification status for a user."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT phone_number, email, phone_verified, email_verified,
               phone_verification_sent_at, email_verification_sent_at
        FROM players WHERE id = ?
    ''', (user_id,))
    player = cursor.fetchone()
    conn.close()
    
    if not player:
        return None
    
    return {
        'phone': player['phone_number'],
        'email': player['email'],
        'phone_verified': bool(player['phone_verified']),
        'email_verified': bool(player['email_verified']),
        'phone_verification_sent_at': player['phone_verification_sent_at'],
        'email_verification_sent_at': player['email_verification_sent_at'],
        'has_phone': bool(player['phone_number']),
        'has_email': bool(player['email'])
    }


def reset_verification_on_change(user_id, channel):
    """Reset verification status when phone/email changes."""
    conn = get_db()
    cursor = conn.cursor()
    
    if channel == 'phone':
        cursor.execute('UPDATE players SET phone_verified = 0 WHERE id = ?', (user_id,))
    else:
        cursor.execute('UPDATE players SET email_verified = 0 WHERE id = ?', (user_id,))
    
    # Expire any pending verifications for this channel
    cursor.execute('''
        UPDATE verifications SET status = 'expired' 
        WHERE user_id = ? AND channel = ? AND status = 'pending'
    ''', (user_id, channel))
    
    conn.commit()
    conn.close()


def can_resend_verification(user_id, channel):
    """Check if user can resend verification code (60 second cooldown)."""
    from datetime import datetime, timedelta
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT created_at FROM verifications 
        WHERE user_id = ? AND channel = ? AND status = 'pending'
        ORDER BY created_at DESC LIMIT 1
    ''', (user_id, channel))
    last = cursor.fetchone()
    conn.close()
    
    if not last:
        return True, 0
    
    created_at = datetime.strptime(last['created_at'], '%Y-%m-%d %H:%M:%S')
    cooldown_end = created_at + timedelta(seconds=60)
    now = datetime.now()
    
    if now >= cooldown_end:
        return True, 0
    
    seconds_remaining = int((cooldown_end - now).total_seconds())
    return False, seconds_remaining



# ============================================
# ADMIN USER MANAGEMENT
# ============================================

def log_admin_action(admin_user_id, target_user_id, action, details=None, old_values=None, new_values=None, ip_address=None, admin_type='master'):
    """Log an admin action to the audit table."""
    import json
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO admin_audit_log (admin_user_id, admin_type, target_user_id, action, details, old_values, new_values, ip_address)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        admin_user_id, 
        admin_type, 
        target_user_id, 
        action, 
        details,
        json.dumps(old_values) if old_values else None,
        json.dumps(new_values) if new_values else None,
        ip_address
    ))
    
    conn.commit()
    conn.close()


def check_duplicate_email(email, exclude_player_id=None):
    """Check if email is already used by another active account."""
    if not email:
        return None
    
    conn = get_db()
    cursor = conn.cursor()
    
    if exclude_player_id:
        cursor.execute('''
            SELECT id, nickname, email FROM players 
            WHERE email = ? AND id != ? AND (is_active = 1 OR is_active IS NULL)
        ''', (email.lower().strip(), exclude_player_id))
    else:
        cursor.execute('''
            SELECT id, nickname, email FROM players 
            WHERE email = ? AND (is_active = 1 OR is_active IS NULL)
        ''', (email.lower().strip(),))
    
    result = cursor.fetchone()
    conn.close()
    
    return dict(result) if result else None


def check_duplicate_phone(phone, exclude_player_id=None):
    """Check if phone is already used by another active account."""
    if not phone:
        return None
    
    # Normalize phone number
    import re
    normalized = re.sub(r'[^\d]', '', phone)
    if len(normalized) == 10:
        normalized = '1' + normalized
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Match against both normalized formats
    if exclude_player_id:
        cursor.execute('''
            SELECT id, nickname, phone_number FROM players 
            WHERE (REPLACE(REPLACE(REPLACE(REPLACE(phone_number, '-', ''), ' ', ''), '(', ''), ')', '') LIKE ? 
                   OR phone_number = ?)
            AND id != ? AND (is_active = 1 OR is_active IS NULL)
        ''', (f'%{normalized[-10:]}', phone, exclude_player_id))
    else:
        cursor.execute('''
            SELECT id, nickname, phone_number FROM players 
            WHERE (REPLACE(REPLACE(REPLACE(REPLACE(phone_number, '-', ''), ' ', ''), '(', ''), ')', '') LIKE ?
                   OR phone_number = ?)
            AND (is_active = 1 OR is_active IS NULL)
        ''', (f'%{normalized[-10:]}', phone))
    
    result = cursor.fetchone()
    conn.close()
    
    return dict(result) if result else None


def find_potential_duplicates(player_id):
    """Find potential duplicate accounts for a player."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get the target player's info
    cursor.execute('''
        SELECT id, nickname, display_name, email, phone_number 
        FROM players WHERE id = ?
    ''', (player_id,))
    player = cursor.fetchone()
    
    if not player:
        conn.close()
        return []
    
    player = dict(player)
    duplicates = []
    seen_ids = {player_id}
    
    # 1. Exact email match
    if player.get('email'):
        cursor.execute('''
            SELECT id, nickname, display_name, email, phone_number, is_active, created_at
            FROM players WHERE email = ? AND id != ?
        ''', (player['email'], player_id))
        for row in cursor.fetchall():
            if row['id'] not in seen_ids:
                d = dict(row)
                d['match_reason'] = 'Same email'
                d['match_strength'] = 'high'
                duplicates.append(d)
                seen_ids.add(row['id'])
    
    # 2. Exact phone match
    if player.get('phone_number'):
        import re
        normalized = re.sub(r'[^\d]', '', player['phone_number'])
        if len(normalized) >= 10:
            last10 = normalized[-10:]
            cursor.execute('''
                SELECT id, nickname, display_name, email, phone_number, is_active, created_at
                FROM players WHERE id != ? AND phone_number IS NOT NULL
            ''', (player_id,))
            for row in cursor.fetchall():
                if row['id'] not in seen_ids and row['phone_number']:
                    other_normalized = re.sub(r'[^\d]', '', row['phone_number'])
                    if len(other_normalized) >= 10 and other_normalized[-10:] == last10:
                        d = dict(row)
                        d['match_reason'] = 'Same phone number'
                        d['match_strength'] = 'high'
                        duplicates.append(d)
                        seen_ids.add(row['id'])
    
    # 3. Similar name with partial email/phone match
    name = (player.get('display_name') or player.get('nickname') or '').lower().strip()
    if name and len(name) >= 3:
        cursor.execute('''
            SELECT id, nickname, display_name, email, phone_number, is_active, created_at
            FROM players WHERE id != ? AND (
                LOWER(nickname) = ? OR LOWER(display_name) = ?
                OR LOWER(nickname) LIKE ? OR LOWER(display_name) LIKE ?
            )
        ''', (player_id, name, name, f'%{name}%', f'%{name}%'))
        for row in cursor.fetchall():
            if row['id'] not in seen_ids:
                d = dict(row)
                d['match_reason'] = 'Similar name'
                d['match_strength'] = 'medium'
                duplicates.append(d)
                seen_ids.add(row['id'])
    
    conn.close()
    return duplicates[:10]  # Limit to 10 potential duplicates


def deactivate_player(player_id, admin_user_id=None, reason=None, ip_address=None):
    """Soft delete a player account."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get current state for audit
    cursor.execute('SELECT nickname, email, is_active FROM players WHERE id = ?', (player_id,))
    old_player = cursor.fetchone()
    
    if not old_player:
        conn.close()
        return False, 'Player not found'
    
    old_values = dict(old_player)
    
    # Deactivate
    cursor.execute('''
        UPDATE players SET 
            is_active = 0, 
            deactivated_at = datetime('now'),
            deactivated_by = ?
        WHERE id = ?
    ''', (admin_user_id, player_id))
    
    conn.commit()
    conn.close()
    
    # Log the action
    log_admin_action(
        admin_user_id=admin_user_id,
        target_user_id=player_id,
        action='deactivate',
        details=reason,
        old_values={'is_active': old_values.get('is_active', 1)},
        new_values={'is_active': 0},
        ip_address=ip_address
    )
    
    return True, 'Account deactivated'


def reactivate_player(player_id, admin_user_id=None, reason=None, ip_address=None):
    """Reactivate a player account."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get current state
    cursor.execute('SELECT nickname, email, is_active FROM players WHERE id = ?', (player_id,))
    old_player = cursor.fetchone()
    
    if not old_player:
        conn.close()
        return False, 'Player not found'
    
    # Reactivate
    cursor.execute('''
        UPDATE players SET 
            is_active = 1, 
            deactivated_at = NULL,
            deactivated_by = NULL
        WHERE id = ?
    ''', (player_id,))
    
    conn.commit()
    conn.close()
    
    # Log the action
    log_admin_action(
        admin_user_id=admin_user_id,
        target_user_id=player_id,
        action='reactivate',
        details=reason,
        old_values={'is_active': 0},
        new_values={'is_active': 1},
        ip_address=ip_address
    )
    
    return True, 'Account reactivated'


def update_player_admin(player_id, updates, admin_user_id=None, ip_address=None):
    """Update player fields from admin dashboard."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get current values for audit
    cursor.execute('SELECT * FROM players WHERE id = ?', (player_id,))
    old_player = cursor.fetchone()
    
    if not old_player:
        conn.close()
        return False, 'Player not found'
    
    old_values = dict(old_player)
    
    # Build update query for allowed fields only
    # Note: play_frequency is now auto-calculated from game_history, not editable
    allowed_fields = ['display_name', 'home_bar_id', 
                      'marketing_opt_in', 'preferred_contact_method']
    
    set_parts = []
    params = []
    changed_fields = {}
    
    for field in allowed_fields:
        if field in updates:
            set_parts.append(f'{field} = ?')
            params.append(updates[field])
            if str(updates[field]) != str(old_values.get(field)):
                changed_fields[field] = {'old': old_values.get(field), 'new': updates[field]}
    
    if not set_parts:
        conn.close()
        return False, 'No valid fields to update'
    
    params.append(player_id)
    sql = f'UPDATE players SET {", ".join(set_parts)} WHERE id = ?'
    
    cursor.execute(sql, params)
    conn.commit()
    conn.close()
    
    # Log the action
    if changed_fields:
        log_admin_action(
            admin_user_id=admin_user_id,
            target_user_id=player_id,
            action='update_fields',
            details=f'Updated: {", ".join(changed_fields.keys())}',
            old_values={k: v['old'] for k, v in changed_fields.items()},
            new_values={k: v['new'] for k, v in changed_fields.items()},
            ip_address=ip_address
        )
    
    return True, 'Player updated'


def get_admin_audit_log(target_user_id=None, limit=50):
    """Get admin audit log entries."""
    conn = get_db()
    cursor = conn.cursor()
    
    if target_user_id:
        cursor.execute('''
            SELECT a.*, p.nickname as admin_name, t.nickname as target_name
            FROM admin_audit_log a
            LEFT JOIN players p ON a.admin_user_id = p.id
            LEFT JOIN players t ON a.target_user_id = t.id
            WHERE a.target_user_id = ?
            ORDER BY a.created_at DESC LIMIT ?
        ''', (target_user_id, limit))
    else:
        cursor.execute('''
            SELECT a.*, p.nickname as admin_name, t.nickname as target_name
            FROM admin_audit_log a
            LEFT JOIN players p ON a.admin_user_id = p.id
            LEFT JOIN players t ON a.target_user_id = t.id
            ORDER BY a.created_at DESC LIMIT ?
        ''', (limit,))
    
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results



# ============================================
# PLAYER STATS - RANKED VS UNRANKED SEPARATION
# ============================================

def get_player_detailed_stats(player_id):
    """
    Get comprehensive player stats with ranked vs unranked separation.
    Returns dict with overall stats plus ranked and unranked breakdowns.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    stats = {
        'overall': {'wins': 0, 'losses': 0, 'total': 0, 'win_rate': 0},
        'ranked': {'wins': 0, 'losses': 0, 'total': 0, 'win_rate': 0, 'rating': 1000},
        'unranked': {'wins': 0, 'losses': 0, 'total': 0, 'win_rate': 0},
        'play_frequency': 'unknown',
        'play_frequency_label': 'Unknown',
        'avg_games_per_week': 0,
        'last_played': None,
        'current_streak': 0,
        'best_streak': 0
    }
    
    # Get overall stats
    cursor.execute('''
        SELECT 
            COALESCE(SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END), 0) as wins,
            COALESCE(SUM(CASE WHEN loser_id = ? THEN 1 ELSE 0 END), 0) as losses
        FROM game_history
        WHERE winner_id = ? OR loser_id = ?
    ''', (player_id, player_id, player_id, player_id))
    row = cursor.fetchone()
    if row:
        stats['overall']['wins'] = row['wins']
        stats['overall']['losses'] = row['losses']
        stats['overall']['total'] = row['wins'] + row['losses']
        if stats['overall']['total'] > 0:
            stats['overall']['win_rate'] = round((row['wins'] / stats['overall']['total']) * 100)
    
    # Get ranked stats (is_ranked = 1)
    cursor.execute('''
        SELECT 
            COALESCE(SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END), 0) as wins,
            COALESCE(SUM(CASE WHEN loser_id = ? THEN 1 ELSE 0 END), 0) as losses
        FROM game_history
        WHERE (winner_id = ? OR loser_id = ?) AND is_ranked = 1
    ''', (player_id, player_id, player_id, player_id))
    row = cursor.fetchone()
    if row:
        stats['ranked']['wins'] = row['wins']
        stats['ranked']['losses'] = row['losses']
        stats['ranked']['total'] = row['wins'] + row['losses']
        if stats['ranked']['total'] > 0:
            stats['ranked']['win_rate'] = round((row['wins'] / stats['ranked']['total']) * 100)
    
    # Get unranked stats (is_ranked = 0 or NULL)
    cursor.execute('''
        SELECT 
            COALESCE(SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END), 0) as wins,
            COALESCE(SUM(CASE WHEN loser_id = ? THEN 1 ELSE 0 END), 0) as losses
        FROM game_history
        WHERE (winner_id = ? OR loser_id = ?) AND (is_ranked = 0 OR is_ranked IS NULL)
    ''', (player_id, player_id, player_id, player_id))
    row = cursor.fetchone()
    if row:
        stats['unranked']['wins'] = row['wins']
        stats['unranked']['losses'] = row['losses']
        stats['unranked']['total'] = row['wins'] + row['losses']
        if stats['unranked']['total'] > 0:
            stats['unranked']['win_rate'] = round((row['wins'] / stats['unranked']['total']) * 100)
    
    # Get current rating from players table
    cursor.execute('SELECT rating, current_streak, best_streak FROM players WHERE id = ?', (player_id,))
    player_row = cursor.fetchone()
    if player_row:
        stats['ranked']['rating'] = player_row['rating'] or 1000
        stats['current_streak'] = player_row['current_streak'] or 0
        stats['best_streak'] = player_row['best_streak'] or 0
    
    # Get last played date
    cursor.execute('''
        SELECT MAX(played_at) as last_played 
        FROM game_history 
        WHERE winner_id = ? OR loser_id = ?
    ''', (player_id, player_id))
    lp_row = cursor.fetchone()
    if lp_row and lp_row['last_played']:
        stats['last_played'] = lp_row['last_played']
    
    # Calculate play frequency from actual gameplay
    freq_data = calculate_play_frequency(player_id, cursor)
    stats['play_frequency'] = freq_data['frequency']
    stats['play_frequency_label'] = freq_data['label']
    stats['avg_games_per_week'] = freq_data['avg_per_week']
    
    conn.close()
    return stats


def calculate_play_frequency(player_id, cursor=None):
    """
    Calculate play frequency from actual game_history data.
    Looks at games over the last 30 days to determine frequency.
    
    Returns:
        dict with 'frequency' (code), 'label' (display), 'avg_per_week' (number)
    """
    close_conn = False
    if cursor is None:
        conn = get_db()
        cursor = conn.cursor()
        close_conn = True
    
    result = {'frequency': 'unknown', 'label': 'Unknown', 'avg_per_week': 0}
    
    # Count games in the last 30 days
    cursor.execute('''
        SELECT COUNT(*) as game_count,
               COUNT(DISTINCT date(played_at)) as play_days
        FROM game_history
        WHERE (winner_id = ? OR loser_id = ?)
        AND played_at >= datetime('now', '-30 days')
    ''', (player_id, player_id))
    
    row = cursor.fetchone()
    if row:
        game_count = row['game_count'] or 0
        play_days = row['play_days'] or 0
        
        # Calculate average games per week (30 days ≈ 4.3 weeks)
        avg_per_week = round(game_count / 4.3, 1)
        result['avg_per_week'] = avg_per_week
        
        # Determine frequency category based on play patterns
        if game_count == 0:
            result['frequency'] = 'inactive'
            result['label'] = 'Inactive (30+ days)'
        elif play_days >= 20:  # Plays almost every day
            result['frequency'] = 'daily'
            result['label'] = f'Daily ({avg_per_week}/wk)'
        elif play_days >= 8:  # Plays multiple times per week
            result['frequency'] = 'multiple_weekly'
            result['label'] = f'Multiple per week ({avg_per_week}/wk)'
        elif play_days >= 3:  # Plays about weekly
            result['frequency'] = 'weekly'
            result['label'] = f'Weekly ({avg_per_week}/wk)'
        else:  # Plays rarely
            result['frequency'] = 'rarely'
            result['label'] = f'Rarely ({avg_per_week}/wk)'
    
    if close_conn:
        conn.close()
    
    return result


def get_player_tier(player_id):
    """
    Get player's tier/rank based on a percentile-based system.
    Uses a combination of games played, win rate, and rating.
    
    Tiers (percentile-based):
        Diamond: Top 5% of active ranked players
        Platinum: Top 15%
        Gold: Top 35%
        Silver: Top 60%
        Bronze: Everyone else
        Unranked: Less than 5 ranked games
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Get player's ranked stats
    cursor.execute('''
        SELECT 
            p.rating,
            p.ranked_wins,
            p.ranked_losses,
            (p.ranked_wins + p.ranked_losses) as ranked_games
        FROM players p
        WHERE p.id = ?
    ''', (player_id,))
    
    player = cursor.fetchone()
    if not player:
        conn.close()
        return {'tier': 'Unranked', 'emoji': '🎱', 'percentile': None}
    
    ranked_games = player['ranked_games'] or 0
    rating = player['rating'] or 1000
    
    # Need at least 5 ranked games to be ranked
    if ranked_games < 5:
        conn.close()
        return {'tier': 'Unranked', 'emoji': '🎱', 'percentile': None, 'games_needed': 5 - ranked_games}
    
    # Get all ranked players for percentile calculation
    cursor.execute('''
        SELECT COUNT(*) as total_ranked,
               SUM(CASE WHEN rating > ? THEN 1 ELSE 0 END) as players_above
        FROM players
        WHERE (ranked_wins + ranked_losses) >= 5
        AND (is_active = 1 OR is_active IS NULL)
    ''', (rating,))
    
    rank_row = cursor.fetchone()
    conn.close()
    
    total_ranked = rank_row['total_ranked'] or 1
    players_above = rank_row['players_above'] or 0
    
    # Calculate percentile (lower is better - top 5% means percentile < 5)
    percentile = round((players_above / total_ranked) * 100, 1)
    
    # Assign tier based on percentile
    if percentile <= 5:
        tier = 'Diamond'
        emoji = '💎'
    elif percentile <= 15:
        tier = 'Platinum'
        emoji = '🏆'
    elif percentile <= 35:
        tier = 'Gold'
        emoji = '🥇'
    elif percentile <= 60:
        tier = 'Silver'
        emoji = '🥈'
    else:
        tier = 'Bronze'
        emoji = '🥉'
    
    return {
        'tier': tier,
        'emoji': emoji,
        'percentile': percentile,
        'rating': rating,
        'ranked_games': ranked_games
    }


def get_player_recent_games(player_id, limit=20, ranked_only=None):
    """
    Get recent games for a player with optional ranked filter.
    
    Args:
        player_id: Player ID
        limit: Max games to return
        ranked_only: None = all, True = ranked only, False = unranked only
    """
    conn = get_db()
    cursor = conn.cursor()
    
    where_ranked = ""
    if ranked_only is True:
        where_ranked = "AND g.is_ranked = 1"
    elif ranked_only is False:
        where_ranked = "AND (g.is_ranked = 0 OR g.is_ranked IS NULL)"
    
    cursor.execute(f'''
        SELECT g.*, 
               pw.nickname as winner_name, 
               pl.nickname as loser_name,
               bar.name as bar_name
        FROM game_history g
        LEFT JOIN players pw ON g.winner_id = pw.id
        LEFT JOIN players pl ON g.loser_id = pl.id
        LEFT JOIN bars bar ON g.bar_id = bar.id
        WHERE (g.winner_id = ? OR g.loser_id = ?) {where_ranked}
        ORDER BY g.played_at DESC
        LIMIT ?
    ''', (player_id, player_id, limit))
    
    games = []
    for row in cursor.fetchall():
        game = dict(row)
        game['won'] = game['winner_id'] == player_id
        game['opponent_id'] = game['loser_id'] if game['won'] else game['winner_id']
        game['opponent_name'] = game['loser_name'] if game['won'] else game['winner_name']
        games.append(game)
    
    conn.close()
    return games
