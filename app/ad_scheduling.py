"""
Pool Cue - Ad Slot Scheduling System
Handles time-based ad scheduling with efficiency ratings.
"""
import sqlite3
from datetime import datetime, timedelta
from .database import get_db


def init_ad_scheduling_tables():
    """Create tables for ad scheduling and efficiency tracking."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Time slots for ad scheduling
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ad_time_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            placement_type TEXT NOT NULL,
            creative_id INTEGER,
            campaign_id INTEGER,
            advertiser_id INTEGER,
            bar_id INTEGER,
            schedule_type TEXT DEFAULT 'all_day',
            start_time TEXT,
            end_time TEXT,
            days_of_week TEXT DEFAULT 'all',
            priority INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (creative_id) REFERENCES ad_creatives(id),
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
            FOREIGN KEY (advertiser_id) REFERENCES advertisers(id)
        )
    ''')
    
    # Efficiency ratings per time slot
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS slot_efficiency (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            placement_type TEXT NOT NULL,
            hour_of_day INTEGER,
            day_of_week INTEGER,
            impressions INTEGER DEFAULT 0,
            clicks INTEGER DEFAULT 0,
            conversions INTEGER DEFAULT 0,
            efficiency_score REAL DEFAULT 0,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Seed initial efficiency data (will adapt over time)
    _seed_initial_efficiency(cursor)
    
    conn.commit()
    conn.close()


def _seed_initial_efficiency(cursor):
    """Seed initial efficiency estimates based on typical bar patterns."""
    # Check if already seeded
    cursor.execute('SELECT COUNT(*) FROM slot_efficiency')
    if cursor.fetchone()[0] > 0:
        return
    
    placements = ['board_rotation', 'between_games', 'winner_screen', 'loser_screen', 'queue_idle']
    
    # Efficiency patterns (0-100 scale)
    # Based on typical bar traffic: busy evenings, weekends
    hour_patterns = {
        # Hour: base efficiency
        0: 10, 1: 5, 2: 5, 3: 0, 4: 0, 5: 0,
        6: 0, 7: 0, 8: 0, 9: 5, 10: 10, 11: 15,
        12: 20, 13: 20, 14: 25, 15: 30, 16: 40, 17: 50,
        18: 65, 19: 80, 20: 95, 21: 100, 22: 90, 23: 60
    }
    
    # Day multipliers (0=Mon, 6=Sun)
    day_multipliers = {
        0: 0.7,  # Monday
        1: 0.75, # Tuesday
        2: 0.8,  # Wednesday
        3: 0.85, # Thursday
        4: 1.0,  # Friday
        5: 1.0,  # Saturday
        6: 0.8   # Sunday
    }
    
    for placement in placements:
        for hour in range(24):
            for day in range(7):
                base = hour_patterns[hour]
                score = round(base * day_multipliers[day], 1)
                cursor.execute('''
                    INSERT INTO slot_efficiency (placement_type, hour_of_day, day_of_week, efficiency_score)
                    VALUES (?, ?, ?, ?)
                ''', (placement, hour, day, score))


def get_slot_efficiency(placement_type, hour=None, day=None):
    """Get efficiency rating for a placement/time combination."""
    conn = get_db()
    cursor = conn.cursor()
    
    if hour is not None and day is not None:
        cursor.execute('''
            SELECT efficiency_score FROM slot_efficiency
            WHERE placement_type = ? AND hour_of_day = ? AND day_of_week = ?
        ''', (placement_type, hour, day))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 50
    
    # Return all hours for the placement
    cursor.execute('''
        SELECT hour_of_day, day_of_week, efficiency_score
        FROM slot_efficiency
        WHERE placement_type = ?
        ORDER BY day_of_week, hour_of_day
    ''', (placement_type,))
    results = cursor.fetchall()
    conn.close()
    return results


def get_time_slot_availability(placement_type, bar_id=None):
    """Get which time slots are taken and by whom."""
    conn = get_db()
    cursor = conn.cursor()
    
    query = '''
        SELECT ts.*, a.name as advertiser_name, ac.file_name
        FROM ad_time_slots ts
        LEFT JOIN advertisers a ON a.id = ts.advertiser_id
        LEFT JOIN ad_creatives ac ON ac.id = ts.creative_id
        WHERE ts.placement_type = ? AND ts.is_active = 1
    '''
    params = [placement_type]
    
    if bar_id:
        query += ' AND (ts.bar_id = ? OR ts.bar_id IS NULL)'
        params.append(bar_id)
    
    cursor.execute(query, params)
    slots = cursor.fetchall()
    conn.close()
    
    return slots


def schedule_ad(creative_id, campaign_id, advertiser_id, placement_type, 
                schedule_type='all_day', start_time=None, end_time=None, 
                days_of_week='all', bar_id=None):
    """Schedule an ad for a specific placement and time."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Check for conflicts if not all_day
    if schedule_type != 'all_day' and start_time and end_time:
        cursor.execute('''
            SELECT id FROM ad_time_slots
            WHERE placement_type = ? AND is_active = 1
            AND schedule_type = 'all_day'
            AND (bar_id = ? OR bar_id IS NULL OR ? IS NULL)
        ''', (placement_type, bar_id, bar_id))
        
        if cursor.fetchone():
            conn.close()
            return {'success': False, 'error': 'Slot has all-day ad running'}
    
    cursor.execute('''
        INSERT INTO ad_time_slots 
        (placement_type, creative_id, campaign_id, advertiser_id, bar_id,
         schedule_type, start_time, end_time, days_of_week)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (placement_type, creative_id, campaign_id, advertiser_id, bar_id,
          schedule_type, start_time, end_time, days_of_week))
    
    slot_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return {'success': True, 'slot_id': slot_id}


def update_efficiency_from_impression(placement_type, clicked=False, converted=False):
    """Update efficiency scores based on real data (adaptive learning)."""
    conn = get_db()
    cursor = conn.cursor()
    
    now = datetime.now()
    hour = now.hour
    day = now.weekday()
    
    # Update counts
    cursor.execute('''
        UPDATE slot_efficiency
        SET impressions = impressions + 1,
            clicks = clicks + ?,
            conversions = conversions + ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE placement_type = ? AND hour_of_day = ? AND day_of_week = ?
    ''', (1 if clicked else 0, 1 if converted else 0, placement_type, hour, day))
    
    # Recalculate efficiency score
    cursor.execute('''
        SELECT impressions, clicks, conversions FROM slot_efficiency
        WHERE placement_type = ? AND hour_of_day = ? AND day_of_week = ?
    ''', (placement_type, hour, day))
    
    result = cursor.fetchone()
    if result and result[0] > 10:  # Only update after enough data
        impressions, clicks, conversions = result
        # Weighted score: CTR * 50 + Conversion Rate * 50
        ctr = (clicks / impressions) * 100 if impressions > 0 else 0
        cvr = (conversions / impressions) * 100 if impressions > 0 else 0
        new_score = min(100, (ctr * 25) + (cvr * 50) + 25)  # Base 25 + performance
        
        cursor.execute('''
            UPDATE slot_efficiency
            SET efficiency_score = ?
            WHERE placement_type = ? AND hour_of_day = ? AND day_of_week = ?
        ''', (round(new_score, 1), placement_type, hour, day))
    
    conn.commit()
    conn.close()


def get_best_time_slots(placement_type, top_n=5):
    """Get the most efficient time slots for a placement."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT hour_of_day, day_of_week, efficiency_score,
               impressions, clicks
        FROM slot_efficiency
        WHERE placement_type = ?
        ORDER BY efficiency_score DESC
        LIMIT ?
    ''', (placement_type, top_n))
    
    results = cursor.fetchall()
    conn.close()
    
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    
    return [{
        'hour': r[0],
        'day': days[r[1]],
        'day_num': r[1],
        'efficiency': r[2],
        'impressions': r[3],
        'clicks': r[4],
        'time_label': f"{r[0]}:00-{r[0]+1}:00"
    } for r in results]


# Placement info with preview descriptions
PLACEMENT_INFO = {
    'board_rotation': {
        'name': 'Board Display',
        'description': 'Rotates on the main board between games',
        'preview_text': 'Shows on TV/monitor visible to entire bar',
        'icon': '📺',
        'best_for': 'Brand awareness, high visibility'
    },
    'between_games': {
        'name': 'Between Games',
        'description': 'Displays when a game ends, before next begins',
        'preview_text': 'Full screen takeover for 5-10 seconds',
        'icon': '🎯',
        'best_for': 'High attention, captive audience'
    },
    'winner_screen': {
        'name': 'Winner Screen',
        'description': 'Shows to the winning player after victory',
        'preview_text': 'Celebratory moment, positive association',
        'icon': '🏆',
        'best_for': 'Premium brands, celebration drinks'
    },
    'loser_screen': {
        'name': 'Loser Screen', 
        'description': 'Shows to the losing player after defeat',
        'preview_text': 'Consolation moment, "treat yourself"',
        'icon': '😔',
        'best_for': 'Comfort drinks, "buy the winner a round"'
    },
    'queue_idle': {
        'name': 'Queue Idle',
        'description': 'Displays when queue has no activity',
        'preview_text': 'Ambient display during slow periods',
        'icon': '⏳',
        'best_for': 'Longer-form content, specials'
    },
    'player_app': {
        'name': 'Player App',
        'description': 'Banner in the mobile player app',
        'preview_text': 'Small banner on player home screen',
        'icon': '📱',
        'best_for': 'Targeted, personalized offers'
    }
}
