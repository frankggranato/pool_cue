"""
Pool Cue - Advertiser & Campaign Management System
Full advertiser onboarding with brand data, placements, and survey questions.
"""
import sqlite3
from datetime import datetime, timedelta
from .database import get_db


def init_advertiser_tables():
    """Create all advertiser-related tables."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Advertisers - the companies/brands running campaigns
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS advertisers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            category TEXT,
            contact_name TEXT,
            contact_email TEXT,
            contact_phone TEXT,
            website TEXT,
            logo_path TEXT,
            notes TEXT,
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Campaigns - specific ad campaigns for an advertiser
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            advertiser_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            start_date DATE,
            end_date DATE,
            budget REAL,
            target_impressions INTEGER,
            status TEXT DEFAULT 'active',
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (advertiser_id) REFERENCES advertisers(id)
        )
    ''')
    
    # Ad creatives - actual ad images/content
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ad_creatives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            advertiser_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            file_path TEXT,
            label TEXT,
            ad_type TEXT DEFAULT 'image',
            click_url TEXT,
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
            FOREIGN KEY (advertiser_id) REFERENCES advertisers(id)
        )
    ''')
    
    # Ad placements - where ads can appear
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ad_placements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            creative_id INTEGER,
            placement_type TEXT NOT NULL,
            bar_id INTEGER,
            priority INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
            FOREIGN KEY (creative_id) REFERENCES ad_creatives(id),
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        )
    ''')
    
    # Survey questions tied to advertisers
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS advertiser_surveys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            advertiser_id INTEGER NOT NULL,
            campaign_id INTEGER,
            question_text TEXT NOT NULL,
            question_type TEXT DEFAULT 'yes_no',
            options TEXT,
            is_active INTEGER DEFAULT 1,
            display_after TEXT DEFAULT 'game',
            ai_suggested INTEGER DEFAULT 0,
            effectiveness_score REAL,
            times_shown INTEGER DEFAULT 0,
            times_answered INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (advertiser_id) REFERENCES advertisers(id),
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
        )
    ''')
    
    # Survey responses
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS survey_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            survey_id INTEGER NOT NULL,
            player_id INTEGER,
            response TEXT,
            game_result TEXT,
            bar_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (survey_id) REFERENCES advertiser_surveys(id),
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    ''')
    
    # Ad impressions - tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ad_impressions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creative_id INTEGER,
            campaign_id INTEGER,
            advertiser_id INTEGER,
            bar_id INTEGER,
            player_id INTEGER,
            placement_type TEXT,
            view_duration_seconds INTEGER DEFAULT 0,
            clicked INTEGER DEFAULT 0,
            clicked_at DATETIME,
            impression_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (creative_id) REFERENCES ad_creatives(id),
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
            FOREIGN KEY (advertiser_id) REFERENCES advertisers(id)
        )
    ''')
    
    conn.commit()
    conn.close()


# Placement types
PLACEMENT_TYPES = [
    ('board_rotation', 'Board Display', 'Rotates during idle time'),
    ('between_games', 'Between Games', 'Shows when game ends'),
    ('winner_screen', 'Winner Screen', 'Shows to winning player'),
    ('loser_screen', 'Loser Screen', 'Shows to losing player'),
    ('queue_idle', 'Queue Idle', 'When queue has no activity'),
    ('player_app', 'Player App', 'In the mobile player app'),
]

# Ad categories
AD_CATEGORIES = [
    'Beer', 'Spirits', 'Wine', 'Seltzer', 'Non-Alcoholic',
    'Food', 'Entertainment', 'Local Business', 'Other'
]

# Suggested survey questions by category
SUGGESTED_QUESTIONS = {
    'Beer': [
        "Did you order {brand} tonight?",
        "Have you tried {brand} before?",
        "Would you recommend {brand} to a friend?",
        "Did seeing the ad make you more likely to order {brand}?",
    ],
    'Spirits': [
        "Did you order {brand} tonight?",
        "What's your go-to drink with {brand}?",
        "Would you order {brand} again?",
    ],
    'default': [
        "Did you notice the {brand} ad?",
        "Are you familiar with {brand}?",
        "Would you consider trying {brand}?",
    ]
}


def add_advertiser(name, category=None, contact_email=None, website=None, **kwargs):
    """Add a new advertiser."""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO advertisers (name, category, contact_email, website, contact_name, contact_phone, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (name, category, contact_email, website, 
              kwargs.get('contact_name'), kwargs.get('contact_phone'), kwargs.get('notes')))
        advertiser_id = cursor.lastrowid
        conn.commit()
        return advertiser_id
    except sqlite3.IntegrityError:
        cursor.execute('SELECT id FROM advertisers WHERE name = ?', (name,))
        result = cursor.fetchone()
        return result['id'] if result else None
    finally:
        conn.close()


def update_advertiser(advertiser_id, name, category=None, contact_email=None, notes=None):
    """Update an existing advertiser."""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE advertisers 
            SET name = ?, category = ?, contact_email = ?, notes = ?
            WHERE id = ?
        ''', (name, category, contact_email, notes, advertiser_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"[ADVERTISER] Error updating advertiser {advertiser_id}: {e}")
        return False
    finally:
        conn.close()


def get_advertiser_by_id(advertiser_id):
    """Get a single advertiser by ID."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM advertisers WHERE id = ?', (advertiser_id,))
    advertiser = cursor.fetchone()
    conn.close()
    return dict(advertiser) if advertiser else None


def deactivate_advertiser(advertiser_id):
    """Soft-delete an advertiser and cancel all their campaigns."""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Cancel all campaigns for this advertiser
        cursor.execute('''
            UPDATE campaigns SET status = 'cancelled' 
            WHERE advertiser_id = ? AND status IN ('active', 'paused', 'draft', 'scheduled')
        ''', (advertiser_id,))
        cancelled_count = cursor.rowcount
        
        # Deactivate the advertiser
        cursor.execute('''
            UPDATE advertisers SET is_active = 0 WHERE id = ?
        ''', (advertiser_id,))
        conn.commit()
        
        if cancelled_count > 0:
            return True, f"Advertiser deactivated, {cancelled_count} campaign(s) cancelled"
        return True, "Advertiser deactivated"
    except Exception as e:
        print(f"[ADVERTISER] Error deactivating advertiser {advertiser_id}: {e}")
        return False, str(e)
    finally:
        conn.close()


def create_campaign(advertiser_id, name, start_date=None, end_date=None, **kwargs):
    """Create a new campaign for an advertiser."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO campaigns (advertiser_id, name, start_date, end_date, budget, target_impressions, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (advertiser_id, name, start_date, end_date, 
          kwargs.get('budget'), kwargs.get('target_impressions'), kwargs.get('notes')))
    campaign_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return campaign_id


def add_creative(campaign_id, advertiser_id, file_name, label=None, click_url=None):
    """Add an ad creative to a campaign."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO ad_creatives (campaign_id, advertiser_id, file_name, label, click_url)
        VALUES (?, ?, ?, ?, ?)
    ''', (campaign_id, advertiser_id, file_name, label, click_url))
    creative_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return creative_id


def set_placements(campaign_id, creative_id, placement_types, bar_id=None):
    """Set which placements a creative should appear in."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Clear existing placements for this creative
    cursor.execute('DELETE FROM ad_placements WHERE creative_id = ?', (creative_id,))
    
    # Add new placements
    for placement in placement_types:
        cursor.execute('''
            INSERT INTO ad_placements (campaign_id, creative_id, placement_type, bar_id, is_active)
            VALUES (?, ?, ?, ?, 1)
        ''', (campaign_id, creative_id, placement, bar_id))
    
    conn.commit()
    conn.close()


def add_survey_question(advertiser_id, question_text, campaign_id=None, question_type='yes_no', 
                        options=None, ai_suggested=False, effectiveness_score=None):
    """Add a survey question for an advertiser."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO advertiser_surveys 
        (advertiser_id, campaign_id, question_text, question_type, options, ai_suggested, effectiveness_score)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (advertiser_id, campaign_id, question_text, question_type, options, 
          1 if ai_suggested else 0, effectiveness_score))
    survey_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return survey_id


def get_suggested_questions(brand_name, category):
    """Get AI-suggested survey questions for a brand."""
    questions = SUGGESTED_QUESTIONS.get(category, SUGGESTED_QUESTIONS['default'])
    return [q.format(brand=brand_name) for q in questions]


def get_all_advertisers(include_inactive=False):
    """Get all advertisers with their campaign counts."""
    conn = get_db()
    cursor = conn.cursor()
    
    where_clause = "" if include_inactive else "WHERE a.is_active = 1"
    
    cursor.execute(f'''
        SELECT a.*, 
               COUNT(DISTINCT c.id) as campaign_count,
               COUNT(DISTINCT ac.id) as creative_count,
               SUM(CASE WHEN c.status = 'active' THEN 1 ELSE 0 END) as active_campaigns
        FROM advertisers a
        LEFT JOIN campaigns c ON c.advertiser_id = a.id
        LEFT JOIN ad_creatives ac ON ac.advertiser_id = a.id
        {where_clause}
        GROUP BY a.id
        ORDER BY a.name
    ''')
    advertisers = cursor.fetchall()
    conn.close()
    return advertisers


def get_advertiser_details(advertiser_id):
    """Get full details for an advertiser including campaigns and creatives."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get advertiser
    cursor.execute('SELECT * FROM advertisers WHERE id = ?', (advertiser_id,))
    advertiser = cursor.fetchone()
    
    if not advertiser:
        conn.close()
        return None
    
    # Get campaigns
    cursor.execute('''
        SELECT c.*, COUNT(ac.id) as creative_count
        FROM campaigns c
        LEFT JOIN ad_creatives ac ON ac.campaign_id = c.id
        WHERE c.advertiser_id = ?
        GROUP BY c.id
        ORDER BY c.created_at DESC
    ''', (advertiser_id,))
    campaigns = cursor.fetchall()
    
    # Get creatives
    cursor.execute('SELECT * FROM ad_creatives WHERE advertiser_id = ?', (advertiser_id,))
    creatives = cursor.fetchall()
    
    # Get survey questions
    cursor.execute('SELECT * FROM advertiser_surveys WHERE advertiser_id = ?', (advertiser_id,))
    surveys = cursor.fetchall()
    
    # Get impression stats - join through ad_creatives if needed
    try:
        cursor.execute('''
            SELECT COUNT(*) as impressions,
                   SUM(CASE WHEN clicked = 1 THEN 1 ELSE 0 END) as clicks
            FROM ad_impressions ai
            JOIN ad_creatives ac ON ai.ad_id = ac.file_name
            WHERE ac.advertiser_id = ?
        ''', (advertiser_id,))
        stats = cursor.fetchone()
    except:
        # Fallback if tables don't match
        stats = {'impressions': 0, 'clicks': 0}
    
    conn.close()
    
    return {
        'advertiser': advertiser,
        'campaigns': campaigns,
        'creatives': creatives,
        'surveys': surveys,
        'stats': stats
    }


def get_analytics_for_advertiser(advertiser_id, days=30):
    """Get analytics data for an advertiser."""
    conn = get_db()
    cursor = conn.cursor()
    
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    # Impressions over time
    cursor.execute('''
        SELECT DATE(impression_at) as date, COUNT(*) as impressions,
               SUM(CASE WHEN clicked = 1 THEN 1 ELSE 0 END) as clicks
        FROM ad_impressions
        WHERE advertiser_id = ? AND DATE(impression_at) >= ?
        GROUP BY DATE(impression_at)
        ORDER BY date
    ''', (advertiser_id, since))
    daily_stats = cursor.fetchall()
    
    # By placement
    cursor.execute('''
        SELECT placement_type, COUNT(*) as impressions,
               SUM(CASE WHEN clicked = 1 THEN 1 ELSE 0 END) as clicks
        FROM ad_impressions
        WHERE advertiser_id = ? AND DATE(impression_at) >= ?
        GROUP BY placement_type
    ''', (advertiser_id, since))
    placement_stats = cursor.fetchall()
    
    # Survey responses
    cursor.execute('''
        SELECT s.question_text, sr.response, COUNT(*) as count
        FROM survey_responses sr
        JOIN advertiser_surveys s ON s.id = sr.survey_id
        WHERE s.advertiser_id = ? AND DATE(sr.created_at) >= ?
        GROUP BY s.id, sr.response
    ''', (advertiser_id, since))
    survey_stats = cursor.fetchall()
    
    conn.close()
    
    return {
        'daily': daily_stats,
        'by_placement': placement_stats,
        'surveys': survey_stats
    }
