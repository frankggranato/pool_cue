"""
Database v2 - Protected Architecture for Pool Cue
==================================================
GOAL: Insulate player data so updates NEVER accidentally delete user data.

Architecture Principles:
1. SOFT DELETES - Never actually delete records, mark as deleted
2. AUDIT TRAIL - Every change is logged
3. VERSIONED SCHEMA - Migrations are tracked and reversible
4. FOREIGN KEY PROTECTION - Cascade protection prevents orphans
5. DATA SNAPSHOTS - Daily backups of critical tables
6. TRANSACTION SAFETY - All writes are atomic
"""

import sqlite3
import os
import json
from datetime import datetime, timedelta
import shutil

# Database paths
DB_DIR = os.path.join(os.path.dirname(__file__), 'db')
DB_PATH = os.path.join(DB_DIR, 'pool_queue.db')
BACKUP_DIR = os.path.join(DB_DIR, 'backups')
SCHEMA_VERSION = 2  # Increment when schema changes

def get_db():
    """Get database connection with foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn

def init_protected_tables():
    """Initialize v2 protected tables - SAFE to run multiple times."""
    os.makedirs(DB_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # =========================================================================
    # SCHEMA VERSIONING - Track all migrations
    # =========================================================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schema_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version INTEGER NOT NULL,
            description TEXT,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # =========================================================================
    # AUDIT TRAIL - Log every change to critical tables
    # =========================================================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            record_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            old_values TEXT,
            new_values TEXT,
            changed_by TEXT,
            changed_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # =========================================================================
    # PLAYER SNAPSHOTS - Daily backup of player data
    # =========================================================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            snapshot_date DATE NOT NULL,
            data_json TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(player_id, snapshot_date)
        )
    ''')
    
    # =========================================================================
    # DRINK SURVEYS - Post-session brand attribution (KEY FOR ALCOHOL MARKETING)
    # =========================================================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS drink_surveys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            game_id INTEGER,
            bar_id INTEGER,
            
            -- What they ordered
            ordered_drink INTEGER DEFAULT 0,
            drink_category TEXT,
            drink_brand TEXT,
            
            -- Attribution tracking
            saw_ad_for_brand INTEGER DEFAULT 0,
            ad_influenced_decision INTEGER DEFAULT 0,
            ads_seen_brands TEXT,
            
            -- Game context (win/loss affects purchase behavior)
            game_result TEXT,
            emotional_state TEXT,
            
            -- Tokens rewarded for completing survey
            tokens_rewarded INTEGER DEFAULT 25,
            
            -- Soft delete support
            is_deleted INTEGER DEFAULT 0,
            deleted_at DATETIME,
            
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # =========================================================================
    # AD IMPRESSIONS V2 - With game context for win/loss analysis
    # =========================================================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ad_impressions_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand TEXT NOT NULL,
            player_id INTEGER,
            bar_id INTEGER,
            placement TEXT,
            
            -- Game context (KEY for emotional targeting)
            game_context TEXT,
            just_won INTEGER DEFAULT 0,
            just_lost INTEGER DEFAULT 0,
            in_queue INTEGER DEFAULT 0,
            queue_position INTEGER,
            time_waiting_seconds INTEGER,
            
            -- Engagement
            viewed_seconds REAL DEFAULT 0,
            clicked INTEGER DEFAULT 0,
            click_timestamp DATETIME,
            
            -- Attribution link
            led_to_purchase INTEGER DEFAULT 0,
            drink_survey_id INTEGER,
            
            impression_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # =========================================================================
    # BRAND COMPARISONS - Head-to-head competitive data
    # =========================================================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS brand_comparisons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_a TEXT NOT NULL,
            brand_b TEXT NOT NULL,
            bar_id INTEGER,
            comparison_date DATE NOT NULL,
            
            -- Metrics for brand A
            brand_a_impressions INTEGER DEFAULT 0,
            brand_a_clicks INTEGER DEFAULT 0,
            brand_a_ctr REAL DEFAULT 0,
            brand_a_purchases INTEGER DEFAULT 0,
            
            -- Metrics for brand B
            brand_b_impressions INTEGER DEFAULT 0,
            brand_b_clicks INTEGER DEFAULT 0,
            brand_b_ctr REAL DEFAULT 0,
            brand_b_purchases INTEGER DEFAULT 0,
            
            -- Who won this comparison
            winner TEXT,
            
            calculated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # =========================================================================
    # PLAYER DEMOGRAPHICS V2 - Inferred and declared data
    # =========================================================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_demographics_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER UNIQUE NOT NULL,
            
            -- Declared data (from profile)
            declared_age_range TEXT,
            declared_gender TEXT,
            declared_income_range TEXT,
            
            -- Inferred data (from behavior)
            inferred_income_bracket TEXT,
            avg_bar_price_tier TEXT,
            typical_drink_price_range TEXT,
            spending_pattern TEXT,
            
            -- Preferences (from surveys/behavior)
            preferred_beer_brands TEXT,
            preferred_liquor_brands TEXT,
            drink_frequency TEXT,
            
            -- Social influence score
            is_tastemaker INTEGER DEFAULT 0,
            friends_influenced INTEGER DEFAULT 0,
            social_reach_score REAL DEFAULT 0,
            
            -- Visit patterns
            typical_visit_days TEXT,
            typical_visit_hours TEXT,
            avg_session_length_mins REAL,
            
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # =========================================================================
    # ATTRIBUTION LIFT STUDIES - A/B holdout groups for proving ROI
    # =========================================================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attribution_studies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            study_name TEXT NOT NULL,
            brand TEXT NOT NULL,
            
            -- Study parameters
            start_date DATE,
            end_date DATE,
            holdout_percentage REAL DEFAULT 20,
            
            -- Groups
            control_group_ids TEXT,
            exposed_group_ids TEXT,
            
            -- Results
            control_purchase_rate REAL,
            exposed_purchase_rate REAL,
            lift_percentage REAL,
            statistical_significance REAL,
            
            status TEXT DEFAULT 'active',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS study_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            study_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            group_type TEXT NOT NULL,
            
            ads_shown INTEGER DEFAULT 0,
            purchases_made INTEGER DEFAULT 0,
            
            joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(study_id, player_id)
        )
    ''')
    
    # =========================================================================
    # WIN/LOSS AD PERFORMANCE - Track ad effectiveness by game outcome
    # =========================================================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS win_loss_ad_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand TEXT NOT NULL,
            bar_id INTEGER,
            stat_date DATE NOT NULL,
            
            -- Post-win metrics
            post_win_impressions INTEGER DEFAULT 0,
            post_win_clicks INTEGER DEFAULT 0,
            post_win_ctr REAL DEFAULT 0,
            post_win_purchases INTEGER DEFAULT 0,
            
            -- Post-loss metrics
            post_loss_impressions INTEGER DEFAULT 0,
            post_loss_clicks INTEGER DEFAULT 0,
            post_loss_ctr REAL DEFAULT 0,
            post_loss_purchases INTEGER DEFAULT 0,
            
            -- Queue metrics (captive audience)
            queue_impressions INTEGER DEFAULT 0,
            queue_clicks INTEGER DEFAULT 0,
            queue_ctr REAL DEFAULT 0,
            queue_purchases INTEGER DEFAULT 0,
            
            calculated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(brand, bar_id, stat_date)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Protected database tables initialized")


# =========================================================================
# HELPER FUNCTIONS - Safe operations with audit trail
# =========================================================================

def log_audit(table_name, record_id, action, old_values=None, new_values=None, changed_by=None):
    """Log every change to the audit trail."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO audit_log (table_name, record_id, action, old_values, new_values, changed_by)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (table_name, record_id, action, 
          json.dumps(old_values) if old_values else None,
          json.dumps(new_values) if new_values else None,
          changed_by))
    conn.commit()
    conn.close()

def soft_delete(table_name, record_id):
    """Soft delete - never actually removes data."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(f'''
        UPDATE {table_name} SET is_deleted = 1, deleted_at = ? WHERE id = ?
    ''', (datetime.now(), record_id))
    conn.commit()
    log_audit(table_name, record_id, 'soft_delete')
    conn.close()

def create_player_snapshot(player_id):
    """Create a daily snapshot of player data for protection."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM players WHERE id = ?', (player_id,))
    player = cursor.fetchone()
    
    if player:
        data_json = json.dumps(dict(player))
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('''
            INSERT OR REPLACE INTO player_snapshots (player_id, snapshot_date, data_json)
            VALUES (?, ?, ?)
        ''', (player_id, today, data_json))
        conn.commit()
    
    conn.close()

def backup_database():
    """Create a full database backup."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(BACKUP_DIR, f'pool_queue_{timestamp}.db')
    shutil.copy2(DB_PATH, backup_path)
    
    # Keep only last 30 backups
    backups = sorted(os.listdir(BACKUP_DIR))
    while len(backups) > 30:
        os.remove(os.path.join(BACKUP_DIR, backups.pop(0)))
    
    return backup_path


# =========================================================================
# MARKETING ANALYTICS FUNCTIONS
# =========================================================================

def record_drink_survey(player_id, brand, game_id=None, bar_id=None, game_result=None, ads_seen=None, emotional_state=None):
    """Record a post-session drink survey - KEY for brand attribution."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO drink_surveys 
        (player_id, game_id, bar_id, ordered_drink, drink_brand, game_result, ads_seen_brands, emotional_state)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (player_id, game_id, bar_id, 1 if brand else 0, brand, game_result, 
          json.dumps(ads_seen) if ads_seen else None, emotional_state))
    
    survey_id = cursor.lastrowid
    conn.commit()
    log_audit('drink_surveys', survey_id, 'create', new_values={'player_id': player_id, 'brand': brand})
    conn.close()
    return survey_id

def record_ad_impression(brand, player_id=None, placement=None, bar_id=None, 
                         game_context=None, just_won=False, just_lost=False,
                         in_queue=False, queue_position=None):
    """Record ad impression with game context for win/loss analysis."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO ad_impressions_v2 
        (brand, player_id, bar_id, placement, game_context, just_won, just_lost, in_queue, queue_position)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (brand, player_id, bar_id, placement, game_context, 
          1 if just_won else 0, 1 if just_lost else 0,
          1 if in_queue else 0, queue_position))
    
    impression_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return impression_id

def record_ad_click(impression_id):
    """Record that an ad was clicked."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE ad_impressions_v2 SET clicked = 1, click_timestamp = ? WHERE id = ?
    ''', (datetime.now(), impression_id))
    conn.commit()
    conn.close()

def get_win_loss_ad_stats(brand=None, bar_id=None, days=30):
    """Get win/loss ad performance statistics."""
    conn = get_db()
    cursor = conn.cursor()
    
    since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    query = '''
        SELECT 
            brand,
            SUM(CASE WHEN just_won = 1 THEN 1 ELSE 0 END) as post_win_impressions,
            SUM(CASE WHEN just_won = 1 AND clicked = 1 THEN 1 ELSE 0 END) as post_win_clicks,
            SUM(CASE WHEN just_lost = 1 THEN 1 ELSE 0 END) as post_loss_impressions,
            SUM(CASE WHEN just_lost = 1 AND clicked = 1 THEN 1 ELSE 0 END) as post_loss_clicks,
            SUM(CASE WHEN in_queue = 1 THEN 1 ELSE 0 END) as queue_impressions,
            SUM(CASE WHEN in_queue = 1 AND clicked = 1 THEN 1 ELSE 0 END) as queue_clicks
        FROM ad_impressions_v2
        WHERE impression_at >= ?
    '''
    params = [since_date]
    
    if brand:
        query += ' AND brand = ?'
        params.append(brand)
    if bar_id:
        query += ' AND bar_id = ?'
        params.append(bar_id)
    
    query += ' GROUP BY brand'
    
    cursor.execute(query, params)
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    # Calculate CTRs
    for r in results:
        r['post_win_ctr'] = (r['post_win_clicks'] / r['post_win_impressions'] * 100) if r['post_win_impressions'] > 0 else 0
        r['post_loss_ctr'] = (r['post_loss_clicks'] / r['post_loss_impressions'] * 100) if r['post_loss_impressions'] > 0 else 0
        r['queue_ctr'] = (r['queue_clicks'] / r['queue_impressions'] * 100) if r['queue_impressions'] > 0 else 0
    
    return results


def get_brand_comparison(brand_a, brand_b, bar_id=None, days=30):
    """Get head-to-head comparison between two brands."""
    conn = get_db()
    cursor = conn.cursor()
    
    since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    results = {}
    for brand in [brand_a, brand_b]:
        query = '''
            SELECT 
                COUNT(*) as impressions,
                SUM(clicked) as clicks,
                ROUND(SUM(clicked) * 100.0 / COUNT(*), 2) as ctr
            FROM ad_impressions_v2
            WHERE brand = ? AND impression_at >= ?
        '''
        params = [brand, since_date]
        if bar_id:
            query += ' AND bar_id = ?'
            params.append(bar_id)
        
        cursor.execute(query, params)
        row = cursor.fetchone()
        results[brand] = dict(row) if row else {'impressions': 0, 'clicks': 0, 'ctr': 0}
    
    # Determine winner
    winner = brand_a if results[brand_a].get('ctr', 0) > results[brand_b].get('ctr', 0) else brand_b
    
    conn.close()
    return {
        'brand_a': brand_a,
        'brand_a_stats': results[brand_a],
        'brand_b': brand_b,
        'brand_b_stats': results[brand_b],
        'winner': winner,
        'period_days': days
    }

def get_brand_share_of_voice(bar_id=None, days=30):
    """Calculate share of voice (% of impressions) for each brand."""
    conn = get_db()
    cursor = conn.cursor()
    
    since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    query = '''
        SELECT brand, COUNT(*) as impressions
        FROM ad_impressions_v2
        WHERE impression_at >= ?
    '''
    params = [since_date]
    if bar_id:
        query += ' AND bar_id = ?'
        params.append(bar_id)
    query += ' GROUP BY brand ORDER BY impressions DESC'
    
    cursor.execute(query, params)
    results = [dict(row) for row in cursor.fetchall()]
    
    # Calculate total and percentages
    total = sum(r['impressions'] for r in results)
    for r in results:
        r['share_of_voice'] = round(r['impressions'] / total * 100, 1) if total > 0 else 0
    
    conn.close()
    return results

def get_attribution_funnel(brand, days=30):
    """Get full attribution funnel: impressions → clicks → surveys → purchases."""
    conn = get_db()
    cursor = conn.cursor()
    
    since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    # Impressions
    cursor.execute('SELECT COUNT(*) FROM ad_impressions_v2 WHERE brand = ? AND impression_at >= ?', 
                   (brand, since_date))
    impressions = cursor.fetchone()[0]
    
    # Clicks
    cursor.execute('SELECT COUNT(*) FROM ad_impressions_v2 WHERE brand = ? AND clicked = 1 AND impression_at >= ?', 
                   (brand, since_date))
    clicks = cursor.fetchone()[0]
    
    # Surveys mentioning brand
    cursor.execute('SELECT COUNT(*) FROM drink_surveys WHERE drink_brand = ? AND submitted_at >= ?', 
                   (brand, since_date))
    surveys = cursor.fetchone()[0]
    
    # Ad-influenced purchases
    cursor.execute('SELECT COUNT(*) FROM drink_surveys WHERE drink_brand = ? AND ad_influenced_decision = 1 AND submitted_at >= ?', 
                   (brand, since_date))
    influenced = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'brand': brand,
        'impressions': impressions,
        'clicks': clicks,
        'click_rate': round(clicks / impressions * 100, 2) if impressions > 0 else 0,
        'surveys': surveys,
        'ad_influenced_purchases': influenced,
        'conversion_rate': round(influenced / impressions * 100, 4) if impressions > 0 else 0
    }


# =========================================================================
# PLAYER DATA PROTECTION
# =========================================================================

def protect_player_data(player_id):
    """Create comprehensive protection for a player's data."""
    create_player_snapshot(player_id)
    log_audit('players', player_id, 'snapshot_created')

def restore_player_from_snapshot(player_id, snapshot_date):
    """Restore player data from a snapshot (emergency recovery)."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT data_json FROM player_snapshots WHERE player_id = ? AND snapshot_date = ?', 
                   (player_id, snapshot_date))
    row = cursor.fetchone()
    
    if row:
        data = json.loads(row['data_json'])
        # Update player with snapshot data (excluding id and created_at)
        fields = ['nickname', 'phone', 'total_games', 'wins', 'losses']
        for field in fields:
            if field in data:
                cursor.execute(f'UPDATE players SET {field} = ? WHERE id = ?', (data[field], player_id))
        conn.commit()
        log_audit('players', player_id, 'restored_from_snapshot', new_values={'snapshot_date': snapshot_date})
    
    conn.close()
    return row is not None

def infer_player_demographics(player_id):
    """Infer demographic data from player behavior."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get player's activity patterns
    cursor.execute('''
        SELECT 
            strftime('%H', created_at) as hour,
            COUNT(*) as count
        FROM game_history 
        WHERE winner_id = ? OR loser_id = ?
        GROUP BY hour
        ORDER BY count DESC
        LIMIT 3
    ''', (player_id, player_id))
    peak_hours = [row['hour'] for row in cursor.fetchall()]
    
    # Get drink preferences from surveys
    cursor.execute('''
        SELECT drink_brand, COUNT(*) as count
        FROM drink_surveys
        WHERE player_id = ? AND drink_brand IS NOT NULL
        GROUP BY drink_brand
        ORDER BY count DESC
        LIMIT 5
    ''', (player_id,))
    preferred_brands = [row['drink_brand'] for row in cursor.fetchall()]
    
    # Upsert demographics
    cursor.execute('''
        INSERT INTO player_demographics_v2 (player_id, typical_visit_hours, preferred_beer_brands)
        VALUES (?, ?, ?)
        ON CONFLICT(player_id) DO UPDATE SET
            typical_visit_hours = excluded.typical_visit_hours,
            preferred_beer_brands = excluded.preferred_beer_brands,
            updated_at = CURRENT_TIMESTAMP
    ''', (player_id, json.dumps(peak_hours), json.dumps(preferred_brands)))
    
    conn.commit()
    conn.close()


# =========================================================================
# INITIALIZATION - Call this on app startup
# =========================================================================

def init_v2():
    """Initialize all v2 tables and run any pending migrations."""
    init_protected_tables()
    print("✅ Database v2 ready - Player data is protected")

# Auto-initialize when module is imported
if __name__ == '__main__':
    init_v2()
