"""
Pool Cue - Ad Events Tracking System
Handles logging of ad impressions and clicks for real analytics.
"""
import sqlite3
from datetime import datetime
from .database import get_db
import logging

logger = logging.getLogger(__name__)


def init_ad_events_table():
    """Create the ad_events table for tracking impressions and clicks."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Main ad_events table - comprehensive event tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ad_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            ad_id INTEGER,
            ad_filename TEXT,
            campaign_id INTEGER,
            advertiser_id INTEGER,
            bar_id INTEGER,
            table_id INTEGER,
            player_id INTEGER,
            placement TEXT NOT NULL,
            session_token TEXT,
            user_agent TEXT,
            ip_address TEXT,
            referrer TEXT,
            click_url TEXT,
            metadata TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ad_id) REFERENCES ad_creatives(id),
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
            FOREIGN KEY (advertiser_id) REFERENCES advertisers(id),
            FOREIGN KEY (bar_id) REFERENCES bars(id),
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    ''')
    
    # Indexes for efficient querying
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ad_events_type ON ad_events(event_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ad_events_created ON ad_events(created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ad_events_advertiser ON ad_events(advertiser_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ad_events_campaign ON ad_events(campaign_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ad_events_placement ON ad_events(placement)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ad_events_bar ON ad_events(bar_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ad_events_filename ON ad_events(ad_filename)')
    
    conn.commit()
    conn.close()
    
    logger.info("ad_events table initialized")


def log_ad_event(event_type, placement, ad_filename=None, ad_id=None, campaign_id=None,
                 advertiser_id=None, bar_id=None, table_id=None, player_id=None,
                 session_token=None, user_agent=None, ip_address=None, referrer=None,
                 click_url=None, metadata=None):
    """
    Log an ad event (impression or click).
    
    Args:
        event_type: 'impression' or 'click'
        placement: Where the ad was shown (e.g., 'board_main', 'player_home', 'join_success')
        ad_filename: The filename of the ad image
        ad_id: ID from ad_creatives table (if known)
        campaign_id: ID from campaigns table (if known)
        advertiser_id: ID from advertisers table (if known)
        bar_id: Which bar (if applicable)
        table_id: Which table (if applicable)
        player_id: Which player viewed/clicked (if known)
        session_token: Queue session token (if applicable)
        user_agent: Browser user agent
        ip_address: Client IP (for fraud detection)
        referrer: HTTP referrer
        click_url: Destination URL (for clicks)
        metadata: JSON string of additional data
    
    Returns:
        The event ID or None if failed
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # If we have a filename but no advertiser_id, try to look it up
        if ad_filename and not advertiser_id:
            cursor.execute('''
                SELECT id, campaign_id, advertiser_id, click_url
                FROM ad_creatives 
                WHERE file_name = ? AND is_active = 1
            ''', (ad_filename,))
            creative = cursor.fetchone()
            if creative:
                ad_id = creative['id']
                campaign_id = creative['campaign_id']
                advertiser_id = creative['advertiser_id']
                if not click_url:
                    click_url = creative['click_url']
        
        cursor.execute('''
            INSERT INTO ad_events (
                event_type, ad_id, ad_filename, campaign_id, advertiser_id,
                bar_id, table_id, player_id, placement, session_token,
                user_agent, ip_address, referrer, click_url, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            event_type, ad_id, ad_filename, campaign_id, advertiser_id,
            bar_id, table_id, player_id, placement, session_token,
            user_agent, ip_address, referrer, click_url, metadata
        ))
        
        event_id = cursor.lastrowid
        conn.commit()
        
        logger.debug(f"Logged ad event: {event_type} for {ad_filename or ad_id} at {placement}")
        return event_id
        
    except Exception as e:
        logger.error(f"Failed to log ad event: {e}")
        return None
    finally:
        conn.close()


def log_impression(placement, ad_filename=None, **kwargs):
    """
    Convenience function to log an ad impression.
    
    Args:
        placement: Where the ad was shown
        ad_filename: The filename of the ad
        **kwargs: Additional fields (bar_id, player_id, etc.)
    """
    return log_ad_event('impression', placement, ad_filename=ad_filename, **kwargs)


def log_click(placement, ad_filename=None, click_url=None, **kwargs):
    """
    Convenience function to log an ad click.
    
    Args:
        placement: Where the ad was clicked
        ad_filename: The filename of the ad
        click_url: Where the user is being redirected
        **kwargs: Additional fields (bar_id, player_id, etc.)
    """
    return log_ad_event('click', placement, ad_filename=ad_filename, click_url=click_url, **kwargs)


def get_ad_stats(advertiser_id=None, campaign_id=None, days=30, placement=None):
    """
    Get aggregated ad statistics.
    
    Args:
        advertiser_id: Filter by advertiser
        campaign_id: Filter by campaign
        days: Number of days to look back
        placement: Filter by placement type
    
    Returns:
        Dictionary with impressions, clicks, CTR, etc.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    where_clauses = ["created_at >= datetime('now', ?)" ]
    params = [f'-{days} days']
    
    if advertiser_id:
        where_clauses.append('advertiser_id = ?')
        params.append(advertiser_id)
    if campaign_id:
        where_clauses.append('campaign_id = ?')
        params.append(campaign_id)
    if placement:
        where_clauses.append('placement = ?')
        params.append(placement)
    
    where_sql = ' AND '.join(where_clauses)
    
    # Get totals
    cursor.execute(f'''
        SELECT 
            COUNT(CASE WHEN event_type = 'impression' THEN 1 END) as impressions,
            COUNT(CASE WHEN event_type = 'click' THEN 1 END) as clicks,
            COUNT(DISTINCT player_id) as unique_viewers,
            COUNT(DISTINCT bar_id) as bars_reached
        FROM ad_events
        WHERE {where_sql}
    ''', params)
    
    totals = cursor.fetchone()
    
    impressions = totals['impressions'] or 0
    clicks = totals['clicks'] or 0
    ctr = (clicks / impressions * 100) if impressions > 0 else 0
    
    conn.close()
    
    return {
        'impressions': impressions,
        'clicks': clicks,
        'ctr': round(ctr, 2),
        'unique_viewers': totals['unique_viewers'] or 0,
        'bars_reached': totals['bars_reached'] or 0,
        'days': days
    }


def get_ad_stats_by_placement(advertiser_id=None, campaign_id=None, days=30):
    """Get ad stats broken down by placement type."""
    conn = get_db()
    cursor = conn.cursor()
    
    where_clauses = ["created_at >= datetime('now', ?)" ]
    params = [f'-{days} days']
    
    if advertiser_id:
        where_clauses.append('advertiser_id = ?')
        params.append(advertiser_id)
    if campaign_id:
        where_clauses.append('campaign_id = ?')
        params.append(campaign_id)
    
    where_sql = ' AND '.join(where_clauses)
    
    cursor.execute(f'''
        SELECT 
            placement,
            COUNT(CASE WHEN event_type = 'impression' THEN 1 END) as impressions,
            COUNT(CASE WHEN event_type = 'click' THEN 1 END) as clicks
        FROM ad_events
        WHERE {where_sql}
        GROUP BY placement
        ORDER BY impressions DESC
    ''', params)
    
    results = []
    for row in cursor.fetchall():
        impressions = row['impressions'] or 0
        clicks = row['clicks'] or 0
        ctr = (clicks / impressions * 100) if impressions > 0 else 0
        results.append({
            'placement': row['placement'],
            'impressions': impressions,
            'clicks': clicks,
            'ctr': round(ctr, 2)
        })
    
    conn.close()
    return results


def get_ad_stats_daily(advertiser_id=None, campaign_id=None, days=30):
    """Get ad stats broken down by day."""
    conn = get_db()
    cursor = conn.cursor()
    
    where_clauses = ["created_at >= datetime('now', ?)" ]
    params = [f'-{days} days']
    
    if advertiser_id:
        where_clauses.append('advertiser_id = ?')
        params.append(advertiser_id)
    if campaign_id:
        where_clauses.append('campaign_id = ?')
        params.append(campaign_id)
    
    where_sql = ' AND '.join(where_clauses)
    
    cursor.execute(f'''
        SELECT 
            DATE(created_at) as date,
            COUNT(CASE WHEN event_type = 'impression' THEN 1 END) as impressions,
            COUNT(CASE WHEN event_type = 'click' THEN 1 END) as clicks
        FROM ad_events
        WHERE {where_sql}
        GROUP BY DATE(created_at)
        ORDER BY date ASC
    ''', params)
    
    results = []
    for row in cursor.fetchall():
        impressions = row['impressions'] or 0
        clicks = row['clicks'] or 0
        ctr = (clicks / impressions * 100) if impressions > 0 else 0
        results.append({
            'date': row['date'],
            'impressions': impressions,
            'clicks': clicks,
            'ctr': round(ctr, 2)
        })
    
    conn.close()
    return results


def get_ad_stats_by_creative(advertiser_id=None, campaign_id=None, days=30):
    """Get ad stats broken down by creative/ad file."""
    conn = get_db()
    cursor = conn.cursor()
    
    where_clauses = ["created_at >= datetime('now', ?)" ]
    params = [f'-{days} days']
    
    if advertiser_id:
        where_clauses.append('advertiser_id = ?')
        params.append(advertiser_id)
    if campaign_id:
        where_clauses.append('campaign_id = ?')
        params.append(campaign_id)
    
    where_sql = ' AND '.join(where_clauses)
    
    cursor.execute(f'''
        SELECT 
            COALESCE(ad_filename, 'Unknown') as ad_name,
            ad_id,
            COUNT(CASE WHEN event_type = 'impression' THEN 1 END) as impressions,
            COUNT(CASE WHEN event_type = 'click' THEN 1 END) as clicks
        FROM ad_events
        WHERE {where_sql}
        GROUP BY COALESCE(ad_filename, ad_id)
        ORDER BY impressions DESC
    ''', params)
    
    results = []
    for row in cursor.fetchall():
        impressions = row['impressions'] or 0
        clicks = row['clicks'] or 0
        ctr = (clicks / impressions * 100) if impressions > 0 else 0
        results.append({
            'ad_name': row['ad_name'],
            'ad_id': row['ad_id'],
            'impressions': impressions,
            'clicks': clicks,
            'ctr': round(ctr, 2)
        })
    
    conn.close()
    return results


def get_top_performing_ads(days=30, limit=10):
    """Get the top performing ads by CTR (with minimum impressions)."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            COALESCE(ad_filename, 'Unknown') as ad_name,
            ad_id,
            advertiser_id,
            COUNT(CASE WHEN event_type = 'impression' THEN 1 END) as impressions,
            COUNT(CASE WHEN event_type = 'click' THEN 1 END) as clicks
        FROM ad_events
        WHERE created_at >= datetime('now', ?)
        GROUP BY COALESCE(ad_filename, ad_id)
        HAVING impressions >= 10
        ORDER BY (clicks * 1.0 / impressions) DESC
        LIMIT ?
    ''', (f'-{days} days', limit))
    
    results = []
    for row in cursor.fetchall():
        impressions = row['impressions'] or 0
        clicks = row['clicks'] or 0
        ctr = (clicks / impressions * 100) if impressions > 0 else 0
        results.append({
            'ad_name': row['ad_name'],
            'ad_id': row['ad_id'],
            'advertiser_id': row['advertiser_id'],
            'impressions': impressions,
            'clicks': clicks,
            'ctr': round(ctr, 2)
        })
    
    conn.close()
    return results


# Placement type constants
PLACEMENTS = {
    'board_main': 'Board Display - Main rotation',
    'board_idle': 'Board Display - Queue idle',
    'board_between_games': 'Board Display - Between games',
    'board_winner': 'Board Display - Winner screen',
    'board_loser': 'Board Display - Loser screen',
    'player_home': 'Player App - Home screen',
    'player_queue': 'Player App - Queue status',
    'player_profile': 'Player App - Profile',
    'player_tokens': 'Player App - Tokens page',
    'join_page': 'Join Queue - Landing page',
    'join_success': 'Join Queue - Success confirmation',
    'match_result': 'Match Result - Post-game',
}


def get_creative_click_url(ad_filename):
    """Get the click URL for an ad creative by filename."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT click_url FROM ad_creatives 
        WHERE file_name = ? AND is_active = 1
    ''', (ad_filename,))
    
    result = cursor.fetchone()
    conn.close()
    
    return result['click_url'] if result else None
