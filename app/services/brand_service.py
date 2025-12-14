"""
Brand Analytics Service - Track impressions, clicks, funnel metrics
"""
from ..database import get_db
import json
from datetime import datetime, timedelta

def record_impression(brand_id, bar_id, placement, impression_type='screen_view', estimated_viewers=1):
    """Record a brand impression."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO brand_impressions 
                      (brand_id, bar_id, placement, impression_type, estimated_viewers)
                      VALUES (?, ?, ?, ?, ?)''',
                   (brand_id, bar_id, placement, impression_type, estimated_viewers))
    conn.commit()
    conn.close()

def record_click(brand_id, bar_id, user_id, placement):
    """Record a brand click."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO brand_clicks (brand_id, bar_id, user_id, placement)
                      VALUES (?, ?, ?, ?)''',
                   (brand_id, bar_id, user_id, placement))
    conn.commit()
    conn.close()

def get_brand_metrics(brand_id, start_date, end_date):
    """Get brand performance metrics for a period."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Total impressions
    cursor.execute('''SELECT COUNT(*), SUM(estimated_viewers) FROM brand_impressions 
                      WHERE brand_id = ? AND occurred_at BETWEEN ? AND ?''',
                   (brand_id, start_date, end_date))
    imp_row = cursor.fetchone()
    impressions = imp_row[0] or 0
    reach = imp_row[1] or 0
    
    # Total clicks
    cursor.execute('''SELECT COUNT(*) FROM brand_clicks 
                      WHERE brand_id = ? AND occurred_at BETWEEN ? AND ?''',
                   (brand_id, start_date, end_date))
    clicks = cursor.fetchone()[0] or 0
    
    # CTR
    ctr = (clicks / impressions * 100) if impressions > 0 else 0
    
    # Top bars
    cursor.execute('''SELECT b.name, COUNT(*) as cnt 
                      FROM brand_impressions bi
                      JOIN bars b ON bi.bar_id = b.id
                      WHERE bi.brand_id = ? AND bi.occurred_at BETWEEN ? AND ?
                      GROUP BY bi.bar_id ORDER BY cnt DESC LIMIT 5''',
                   (brand_id, start_date, end_date))
    top_bars = [{'name': r[0], 'impressions': r[1]} for r in cursor.fetchall()]
    
    # Impressions by placement
    cursor.execute('''SELECT placement, COUNT(*) FROM brand_impressions 
                      WHERE brand_id = ? AND occurred_at BETWEEN ? AND ?
                      GROUP BY placement''',
                   (brand_id, start_date, end_date))
    by_placement = {r[0]: r[1] for r in cursor.fetchall()}
    
    # Time distribution
    cursor.execute('''SELECT strftime('%H', occurred_at) as hour, COUNT(*) 
                      FROM brand_impressions 
                      WHERE brand_id = ? AND occurred_at BETWEEN ? AND ?
                      GROUP BY hour ORDER BY hour''',
                   (brand_id, start_date, end_date))
    by_hour = {r[0]: r[1] for r in cursor.fetchall()}
    
    conn.close()
    
    return {
        'impressions': impressions,
        'estimated_reach': reach,
        'clicks': clicks,
        'ctr': round(ctr, 2),
        'top_bars': top_bars,
        'by_placement': by_placement,
        'by_hour': by_hour
    }

def get_all_brands_summary(start_date, end_date):
    """Get summary for all brands."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT b.id, b.name, b.category,
               COUNT(DISTINCT bi.id) as impressions,
               COUNT(DISTINCT bc.id) as clicks
        FROM brands b
        LEFT JOIN brand_impressions bi ON b.id = bi.brand_id 
            AND bi.occurred_at BETWEEN ? AND ?
        LEFT JOIN brand_clicks bc ON b.id = bc.brand_id 
            AND bc.occurred_at BETWEEN ? AND ?
        WHERE b.is_active = 1
        GROUP BY b.id
        ORDER BY impressions DESC
    ''', (start_date, end_date, start_date, end_date))
    
    brands = []
    for r in cursor.fetchall():
        ctr = (r[4] / r[3] * 100) if r[3] > 0 else 0
        brands.append({
            'id': r[0],
            'name': r[1],
            'category': r[2],
            'impressions': r[3],
            'clicks': r[4],
            'ctr': round(ctr, 2)
        })
    
    conn.close()
    return brands
