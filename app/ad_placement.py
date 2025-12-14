"""
Ad Placement & Scheduling System
Handles ad slot management, time-based scheduling, and efficiency ratings.
"""
import sqlite3
from datetime import datetime, timedelta
from .database import get_db


def init_placement_tables():
    """Create tables for ad placement scheduling."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if we need to migrate ad_slots
    cursor.execute("PRAGMA table_info(ad_slots)")
    cols = [c[1] for c in cursor.fetchall()]
    
    if 'placement_type' not in cols:
        # Drop old table and recreate with new schema
        cursor.execute('DROP TABLE IF EXISTS ad_slots')
    
    # Ad slots - specific placement locations
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ad_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            placement_type TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            preview_image TEXT,
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    # Scheduled ads - ads assigned to slots with time rules
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scheduled_ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_id INTEGER NOT NULL,
            creative_id INTEGER NOT NULL,
            campaign_id INTEGER NOT NULL,
            advertiser_id INTEGER NOT NULL,
            bar_id INTEGER,
            schedule_type TEXT DEFAULT 'all_day',
            start_time TIME,
            end_time TIME,
            days_of_week TEXT,
            priority INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (slot_id) REFERENCES ad_slots(id),
            FOREIGN KEY (creative_id) REFERENCES ad_creatives(id),
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
            FOREIGN KEY (advertiser_id) REFERENCES advertisers(id)
        )
    ''')
    
    # Slot efficiency ratings - adaptive based on performance
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS slot_efficiency (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_id INTEGER NOT NULL,
            hour_of_day INTEGER,
            day_of_week INTEGER,
            impressions INTEGER DEFAULT 0,
            clicks INTEGER DEFAULT 0,
            conversions INTEGER DEFAULT 0,
            efficiency_score REAL DEFAULT 50.0,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (slot_id) REFERENCES ad_slots(id)
        )
    ''')
    
    # Seed default ad slots if empty
    cursor.execute('SELECT COUNT(*) FROM ad_slots')
    if cursor.fetchone()[0] == 0:
        default_slots = [
            ('board_rotation', 'Board Display', 'Main TV display between games', '/static/previews/board.png'),
            ('winner_screen', 'Winner Screen', 'Shows to winning player after victory', '/static/previews/winner.png'),
            ('loser_screen', 'Loser Screen', 'Shows to losing player after defeat', '/static/previews/loser.png'),
            ('queue_idle', 'Queue Idle', 'Display when queue has no activity', '/static/previews/idle.png'),
            ('player_app_home', 'Player App - Home', 'Banner in player app home screen', '/static/previews/app_home.png'),
            ('player_app_queue', 'Player App - Queue', 'Banner on queue status page', '/static/previews/app_queue.png'),
        ]
        cursor.executemany('''
            INSERT INTO ad_slots (placement_type, name, description, preview_image)
            VALUES (?, ?, ?, ?)
        ''', default_slots)
        
        # Initialize efficiency data for each slot (24 hours x 7 days)
        cursor.execute('SELECT id FROM ad_slots')
        slot_ids = cursor.fetchall()
        for slot_id in slot_ids:
            for hour in range(24):
                for day in range(7):
                    # Base efficiency varies by time (higher during bar hours)
                    base = 50
                    if 17 <= hour <= 23:  # Evening hours
                        base = 75
                    if day >= 4:  # Weekend boost
                        base += 10
                    cursor.execute('''
                        INSERT INTO slot_efficiency (slot_id, hour_of_day, day_of_week, efficiency_score)
                        VALUES (?, ?, ?, ?)
                    ''', (slot_id[0], hour, day, base))
    
    conn.commit()
    conn.close()


def get_all_slots():
    """Get all ad slots with their current status."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT s.*, 
               COUNT(DISTINCT sa.id) as active_ads,
               GROUP_CONCAT(DISTINCT a.name) as advertisers
        FROM ad_slots s
        LEFT JOIN scheduled_ads sa ON sa.slot_id = s.id AND sa.is_active = 1
        LEFT JOIN advertisers a ON a.id = sa.advertiser_id
        GROUP BY s.id
        ORDER BY s.id
    ''')
    slots = cursor.fetchall()
    conn.close()
    return slots


def get_slot_details(slot_id):
    """Get detailed info for a slot including scheduled ads and efficiency."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get slot info
    cursor.execute('SELECT * FROM ad_slots WHERE id = ?', (slot_id,))
    slot = cursor.fetchone()
    
    # Get scheduled ads for this slot
    cursor.execute('''
        SELECT sa.*, c.file_name, a.name as advertiser_name, camp.name as campaign_name
        FROM scheduled_ads sa
        JOIN ad_creatives c ON c.id = sa.creative_id
        JOIN advertisers a ON a.id = sa.advertiser_id
        JOIN campaigns camp ON camp.id = sa.campaign_id
        WHERE sa.slot_id = ? AND sa.is_active = 1
        ORDER BY sa.priority DESC, sa.start_time
    ''', (slot_id,))
    scheduled = cursor.fetchall()
    
    # Get efficiency by hour for today
    today_dow = datetime.now().weekday()
    cursor.execute('''
        SELECT hour_of_day, efficiency_score
        FROM slot_efficiency
        WHERE slot_id = ? AND day_of_week = ?
        ORDER BY hour_of_day
    ''', (slot_id, today_dow))
    efficiency = cursor.fetchall()
    
    conn.close()
    return {
        'slot': slot,
        'scheduled_ads': scheduled,
        'efficiency': efficiency
    }


def get_slot_schedule(slot_id):
    """Get the full schedule for a slot showing which times are taken."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get all scheduled ads
    cursor.execute('''
        SELECT sa.*, a.name as advertiser_name, c.file_name
        FROM scheduled_ads sa
        JOIN advertisers a ON a.id = sa.advertiser_id
        JOIN ad_creatives c ON c.id = sa.creative_id
        WHERE sa.slot_id = ? AND sa.is_active = 1
        ORDER BY sa.start_time
    ''', (slot_id,))
    scheduled = cursor.fetchall()
    
    # Build time slot availability (hourly blocks)
    schedule = []
    for hour in range(24):
        hour_start = f"{hour:02d}:00"
        hour_end = f"{(hour+1) % 24:02d}:00"
        
        # Check if any ad covers this hour
        covering_ads = []
        for ad in scheduled:
            if ad['schedule_type'] == 'all_day':
                covering_ads.append(ad)
            elif ad['start_time'] and ad['end_time']:
                if ad['start_time'] <= hour_start < ad['end_time']:
                    covering_ads.append(ad)
        
        schedule.append({
            'hour': hour,
            'time_label': hour_start,
            'is_taken': len(covering_ads) > 0,
            'ads': covering_ads
        })
    
    conn.close()
    return schedule


def schedule_ad(slot_id, creative_id, campaign_id, advertiser_id, schedule_type='all_day', 
                start_time=None, end_time=None, days_of_week=None, bar_id=None):
    """Schedule an ad to run in a specific slot."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Check for conflicts if not all_day
    if schedule_type == 'specific_times' and start_time and end_time:
        cursor.execute('''
            SELECT id FROM scheduled_ads 
            WHERE slot_id = ? AND is_active = 1
            AND (schedule_type = 'all_day' 
                 OR (start_time < ? AND end_time > ?))
        ''', (slot_id, end_time, start_time))
        conflicts = cursor.fetchall()
        if conflicts:
            conn.close()
            return {'success': False, 'error': 'Time slot conflict with existing ad'}
    
    cursor.execute('''
        INSERT INTO scheduled_ads 
        (slot_id, creative_id, campaign_id, advertiser_id, schedule_type, start_time, end_time, days_of_week, bar_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (slot_id, creative_id, campaign_id, advertiser_id, schedule_type, start_time, end_time, days_of_week, bar_id))
    
    scheduled_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return {'success': True, 'scheduled_id': scheduled_id}


def remove_scheduled_ad(scheduled_id):
    """Remove a scheduled ad."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE scheduled_ads SET is_active = 0 WHERE id = ?', (scheduled_id,))
    conn.commit()
    conn.close()


def get_available_time_slots(slot_id, advertiser_id=None):
    """Get available time slots for a placement, optionally for a specific advertiser."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get all scheduled ads
    cursor.execute('''
        SELECT schedule_type, start_time, end_time, advertiser_id
        FROM scheduled_ads
        WHERE slot_id = ? AND is_active = 1
    ''', (slot_id,))
    scheduled = cursor.fetchall()
    
    # Check each hour
    available = []
    for hour in range(24):
        hour_start = f"{hour:02d}:00"
        hour_end = f"{(hour+1) % 24:02d}:00"
        
        is_available = True
        taken_by = None
        
        for ad in scheduled:
            if ad['schedule_type'] == 'all_day':
                is_available = False
                taken_by = ad['advertiser_id']
                break
            elif ad['start_time'] and ad['end_time']:
                if ad['start_time'] <= hour_start < ad['end_time']:
                    is_available = False
                    taken_by = ad['advertiser_id']
                    break
        
        # Get efficiency for this hour
        cursor.execute('''
            SELECT efficiency_score FROM slot_efficiency
            WHERE slot_id = ? AND hour_of_day = ? AND day_of_week = ?
        ''', (slot_id, hour, datetime.now().weekday()))
        eff = cursor.fetchone()
        efficiency = eff['efficiency_score'] if eff else 50
        
        available.append({
            'hour': hour,
            'time': hour_start,
            'available': is_available,
            'taken_by': taken_by,
            'efficiency': efficiency
        })
    
    conn.close()
    return available


def update_efficiency(slot_id, hour, day, impression=False, click=False, conversion=False):
    """Update efficiency ratings based on actual performance."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Update counts
    updates = []
    if impression:
        updates.append('impressions = impressions + 1')
    if click:
        updates.append('clicks = clicks + 1')
    if conversion:
        updates.append('conversions = conversions + 1')
    
    if updates:
        cursor.execute(f'''
            UPDATE slot_efficiency 
            SET {', '.join(updates)}, last_updated = CURRENT_TIMESTAMP
            WHERE slot_id = ? AND hour_of_day = ? AND day_of_week = ?
        ''', (slot_id, hour, day))
    
    # Recalculate efficiency score
    cursor.execute('''
        SELECT impressions, clicks, conversions FROM slot_efficiency
        WHERE slot_id = ? AND hour_of_day = ? AND day_of_week = ?
    ''', (slot_id, hour, day))
    stats = cursor.fetchone()
    
    if stats and stats['impressions'] > 0:
        # Weighted score: CTR (40%) + Conversion rate (60%)
        ctr = (stats['clicks'] / stats['impressions']) * 100
        conv_rate = (stats['conversions'] / stats['impressions']) * 100 if stats['impressions'] > 0 else 0
        new_score = min(100, (ctr * 10 * 0.4) + (conv_rate * 20 * 0.6) + 30)  # Base 30 + performance
        
        cursor.execute('''
            UPDATE slot_efficiency SET efficiency_score = ?
            WHERE slot_id = ? AND hour_of_day = ? AND day_of_week = ?
        ''', (new_score, slot_id, hour, day))
    
    conn.commit()
    conn.close()


def get_current_ad_for_slot(slot_id, bar_id=None):
    """Get the ad that should currently be displayed for a slot."""
    conn = get_db()
    cursor = conn.cursor()
    
    now = datetime.now()
    current_time = now.strftime('%H:%M')
    current_dow = now.weekday()
    
    # Find matching scheduled ad
    cursor.execute('''
        SELECT sa.*, c.file_name, a.name as advertiser_name
        FROM scheduled_ads sa
        JOIN ad_creatives c ON c.id = sa.creative_id
        JOIN advertisers a ON a.id = sa.advertiser_id
        WHERE sa.slot_id = ? AND sa.is_active = 1
        AND (sa.bar_id IS NULL OR sa.bar_id = ?)
        AND (sa.schedule_type = 'all_day' 
             OR (sa.start_time <= ? AND sa.end_time > ?))
        ORDER BY sa.priority DESC
        LIMIT 1
    ''', (slot_id, bar_id, current_time, current_time))
    
    ad = cursor.fetchone()
    conn.close()
    return ad
