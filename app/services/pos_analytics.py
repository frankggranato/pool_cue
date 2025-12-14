"""
POS Analytics Service.
Helper functions for computing metrics from POS data.
"""

from ..database import get_db


# ============ BASIC POS SUMMARY FUNCTIONS ============

def get_pos_summary_overall(start_date, end_date, bar_id=None):
    """
    Get overall POS summary for a date range.
    
    Args:
        start_date: str in 'YYYY-MM-DD' format
        end_date: str in 'YYYY-MM-DD' format
        bar_id: optional int to filter to single bar
        
    Returns:
        dict with total_checks, total_revenue, avg_check_amount
    """
    conn = get_db()
    cursor = conn.cursor()
    
    if bar_id:
        cursor.execute('''
            SELECT 
                COUNT(*) as total_checks,
                COALESCE(SUM(total_amount), 0) as total_revenue,
                COALESCE(AVG(total_amount), 0) as avg_check_amount
            FROM pos_checks
            WHERE business_date BETWEEN ? AND ?
              AND bar_id = ?
        ''', (start_date, end_date, bar_id))
    else:
        cursor.execute('''
            SELECT 
                COUNT(*) as total_checks,
                COALESCE(SUM(total_amount), 0) as total_revenue,
                COALESCE(AVG(total_amount), 0) as avg_check_amount
            FROM pos_checks
            WHERE business_date BETWEEN ? AND ?
        ''', (start_date, end_date))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row or row['total_checks'] == 0:
        return {
            'total_checks': 0,
            'total_revenue': 0.0,
            'avg_check_amount': 0.0
        }
    
    return {
        'total_checks': row['total_checks'],
        'total_revenue': round(row['total_revenue'], 2),
        'avg_check_amount': round(row['avg_check_amount'], 2)
    }


def get_pos_summary_by_bar(start_date, end_date):
    """
    Get POS summary grouped by bar for a date range.
    
    Args:
        start_date: str in 'YYYY-MM-DD' format
        end_date: str in 'YYYY-MM-DD' format
        
    Returns:
        list of dicts with bar_id, total_checks, total_revenue, avg_check_amount
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            bar_id,
            COUNT(*) as total_checks,
            COALESCE(SUM(total_amount), 0) as total_revenue,
            COALESCE(AVG(total_amount), 0) as avg_check_amount
        FROM pos_checks
        WHERE business_date BETWEEN ? AND ?
        GROUP BY bar_id
        ORDER BY total_revenue DESC
    ''', (start_date, end_date))
    
    results = []
    for row in cursor.fetchall():
        results.append({
            'bar_id': row['bar_id'],
            'total_checks': row['total_checks'],
            'total_revenue': round(row['total_revenue'], 2),
            'avg_check_amount': round(row['avg_check_amount'], 2)
        })
    
    conn.close()
    return results


def get_pos_summary_by_bar_and_date(start_date, end_date, bar_id=None):
    """
    Get POS summary grouped by bar and date for charts.
    
    Args:
        start_date: str in 'YYYY-MM-DD' format
        end_date: str in 'YYYY-MM-DD' format
        bar_id: optional int to filter to single bar
        
    Returns:
        list of dicts with bar_id, business_date, total_checks, 
        total_revenue, avg_check_amount
    """
    conn = get_db()
    cursor = conn.cursor()
    
    if bar_id:
        cursor.execute('''
            SELECT 
                bar_id,
                business_date,
                COUNT(*) as total_checks,
                COALESCE(SUM(total_amount), 0) as total_revenue,
                COALESCE(AVG(total_amount), 0) as avg_check_amount
            FROM pos_checks
            WHERE business_date BETWEEN ? AND ?
              AND bar_id = ?
            GROUP BY bar_id, business_date
            ORDER BY business_date
        ''', (start_date, end_date, bar_id))
    else:
        cursor.execute('''
            SELECT 
                bar_id,
                business_date,
                COUNT(*) as total_checks,
                COALESCE(SUM(total_amount), 0) as total_revenue,
                COALESCE(AVG(total_amount), 0) as avg_check_amount
            FROM pos_checks
            WHERE business_date BETWEEN ? AND ?
            GROUP BY bar_id, business_date
            ORDER BY bar_id, business_date
        ''', (start_date, end_date))
    
    results = []
    for row in cursor.fetchall():
        results.append({
            'bar_id': row['bar_id'],
            'business_date': row['business_date'],
            'total_checks': row['total_checks'],
            'total_revenue': round(row['total_revenue'], 2),
            'avg_check_amount': round(row['avg_check_amount'], 2)
        })
    
    conn.close()
    return results


def get_pos_avg_tab(start_date, end_date, bar_id=None):
    """
    Get average tab amount for a date range.
    Convenience function for analytics display.
    
    Args:
        start_date: str in 'YYYY-MM-DD' format
        end_date: str in 'YYYY-MM-DD' format
        bar_id: optional int to filter to single bar
        
    Returns:
        float - average check amount, or 0 if no data
    """
    conn = get_db()
    cursor = conn.cursor()
    
    if bar_id:
        cursor.execute('''
            SELECT COALESCE(AVG(total_amount), 0) as avg_tab
            FROM pos_checks
            WHERE business_date BETWEEN ? AND ?
              AND bar_id = ?
        ''', (start_date, end_date, bar_id))
    else:
        cursor.execute('''
            SELECT COALESCE(AVG(total_amount), 0) as avg_tab
            FROM pos_checks
            WHERE business_date BETWEEN ? AND ?
        ''', (start_date, end_date))
    
    row = cursor.fetchone()
    conn.close()
    
    return round(row['avg_tab'], 2) if row else 0.0


# ============ BRAND SALES ANALYTICS ============

def get_brand_sales(start_date, end_date, bar_id=None):
    """
    Get brand sales data by joining line items with brand mappings.
    
    Matches items to brands by:
    1. SKU match (if pos_brand_map.item_sku is not null)
    2. Pattern match (item_name LIKE item_name_pattern)
    
    Args:
        start_date: str in 'YYYY-MM-DD' format
        end_date: str in 'YYYY-MM-DD' format
        bar_id: optional int to filter to single bar
        
    Returns:
        list of dicts with bar_id, business_date, normalized_brand,
        units_sold, revenue
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Build the query with optional bar_id filter
    bar_filter = "AND pc.bar_id = ?" if bar_id else ""
    params = [start_date, end_date]
    if bar_id:
        params.append(bar_id)
    
    # Complex join: match by SKU first, then by pattern
    # Using COALESCE to handle both match types
    query = f'''
        SELECT 
            pc.bar_id,
            pc.business_date,
            pbm.normalized_brand,
            SUM(pli.quantity) as units_sold,
            SUM(pli.total_price) as revenue
        FROM pos_line_items pli
        JOIN pos_checks pc ON pli.pos_check_id = pc.id
        JOIN pos_brand_map pbm ON (
            -- Match by SKU if available
            (pbm.item_sku IS NOT NULL AND pli.item_sku = pbm.item_sku)
            OR
            -- Otherwise match by name pattern
            (pbm.item_sku IS NULL AND pli.item_name LIKE pbm.item_name_pattern)
        )
        WHERE pc.business_date BETWEEN ? AND ?
          AND pbm.is_active = 1
          AND pli.is_voided = 0
          {bar_filter}
        GROUP BY pc.bar_id, pc.business_date, pbm.normalized_brand
        ORDER BY pc.bar_id, pc.business_date, revenue DESC
    '''
    
    try:
        cursor.execute(query, params)
        results = []
        for row in cursor.fetchall():
            results.append({
                'bar_id': row['bar_id'],
                'business_date': row['business_date'],
                'normalized_brand': row['normalized_brand'],
                'units_sold': row['units_sold'] or 0,
                'revenue': round(row['revenue'] or 0, 2)
            })
        conn.close()
        return results
    except Exception as e:
        print(f"[POS_ANALYTICS] Error in get_brand_sales: {e}")
        conn.close()
        return []


def get_brand_totals(start_date, end_date, bar_id=None):
    """
    Get total brand sales (not broken down by date).
    Useful for pie charts and rankings.
    
    Args:
        start_date: str in 'YYYY-MM-DD' format
        end_date: str in 'YYYY-MM-DD' format
        bar_id: optional int to filter to single bar
        
    Returns:
        list of dicts with normalized_brand, units_sold, revenue
        sorted by revenue descending
    """
    conn = get_db()
    cursor = conn.cursor()
    
    bar_filter = "AND pc.bar_id = ?" if bar_id else ""
    params = [start_date, end_date]
    if bar_id:
        params.append(bar_id)
    
    query = f'''
        SELECT 
            pbm.normalized_brand,
            pbm.category,
            SUM(pli.quantity) as units_sold,
            SUM(pli.total_price) as revenue
        FROM pos_line_items pli
        JOIN pos_checks pc ON pli.pos_check_id = pc.id
        JOIN pos_brand_map pbm ON (
            (pbm.item_sku IS NOT NULL AND pli.item_sku = pbm.item_sku)
            OR
            (pbm.item_sku IS NULL AND pli.item_name LIKE pbm.item_name_pattern)
        )
        WHERE pc.business_date BETWEEN ? AND ?
          AND pbm.is_active = 1
          AND pli.is_voided = 0
          {bar_filter}
        GROUP BY pbm.normalized_brand, pbm.category
        ORDER BY revenue DESC
    '''
    
    try:
        cursor.execute(query, params)
        results = []
        for row in cursor.fetchall():
            results.append({
                'normalized_brand': row['normalized_brand'],
                'category': row['category'],
                'units_sold': row['units_sold'] or 0,
                'revenue': round(row['revenue'] or 0, 2)
            })
        conn.close()
        return results
    except Exception as e:
        print(f"[POS_ANALYTICS] Error in get_brand_totals: {e}")
        conn.close()
        return []


def get_category_sales(start_date, end_date, bar_id=None):
    """
    Get sales grouped by category (Beer, Whiskey, etc.).
    
    Args:
        start_date: str in 'YYYY-MM-DD' format
        end_date: str in 'YYYY-MM-DD' format
        bar_id: optional int to filter to single bar
        
    Returns:
        list of dicts with category, units_sold, revenue
    """
    conn = get_db()
    cursor = conn.cursor()
    
    bar_filter = "AND pc.bar_id = ?" if bar_id else ""
    params = [start_date, end_date]
    if bar_id:
        params.append(bar_id)
    
    query = f'''
        SELECT 
            COALESCE(pbm.category, 'Other') as category,
            SUM(pli.quantity) as units_sold,
            SUM(pli.total_price) as revenue
        FROM pos_line_items pli
        JOIN pos_checks pc ON pli.pos_check_id = pc.id
        LEFT JOIN pos_brand_map pbm ON (
            (pbm.item_sku IS NOT NULL AND pli.item_sku = pbm.item_sku)
            OR
            (pbm.item_sku IS NULL AND pli.item_name LIKE pbm.item_name_pattern)
        )
        WHERE pc.business_date BETWEEN ? AND ?
          AND pli.is_voided = 0
          {bar_filter}
        GROUP BY category
        ORDER BY revenue DESC
    '''
    
    try:
        cursor.execute(query, params)
        results = []
        for row in cursor.fetchall():
            results.append({
                'category': row['category'],
                'units_sold': row['units_sold'] or 0,
                'revenue': round(row['revenue'] or 0, 2)
            })
        conn.close()
        return results
    except Exception as e:
        print(f"[POS_ANALYTICS] Error in get_category_sales: {e}")
        conn.close()
        return []



# ============ CORE ACTIVITY ANALYTICS ============

def get_core_activity_summary(start_date, end_date, bar_id=None):
    """
    Get core gameplay activity summary.
    
    Args:
        start_date: str in 'YYYY-MM-DD' format
        end_date: str in 'YYYY-MM-DD' format
        bar_id: optional int to filter to single bar
        
    Returns:
        dict with total_games, total_players, total_bars
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Total games in date range
        if bar_id:
            cursor.execute('''
                SELECT COUNT(*) FROM game_history 
                WHERE date(played_at) BETWEEN ? AND ?
                  AND bar_id = ?
            ''', (start_date, end_date, bar_id))
        else:
            cursor.execute('''
                SELECT COUNT(*) FROM game_history 
                WHERE date(played_at) BETWEEN ? AND ?
            ''', (start_date, end_date))
        total_games = cursor.fetchone()[0] or 0
        
        # Distinct players who played in this period
        if bar_id:
            cursor.execute('''
                SELECT COUNT(DISTINCT player_id) FROM (
                    SELECT winner_id as player_id FROM game_history 
                    WHERE date(played_at) BETWEEN ? AND ? AND bar_id = ?
                    UNION
                    SELECT loser_id as player_id FROM game_history 
                    WHERE date(played_at) BETWEEN ? AND ? AND bar_id = ?
                )
            ''', (start_date, end_date, bar_id, start_date, end_date, bar_id))
        else:
            cursor.execute('''
                SELECT COUNT(DISTINCT player_id) FROM (
                    SELECT winner_id as player_id FROM game_history 
                    WHERE date(played_at) BETWEEN ? AND ?
                    UNION
                    SELECT loser_id as player_id FROM game_history 
                    WHERE date(played_at) BETWEEN ? AND ?
                )
            ''', (start_date, end_date, start_date, end_date))
        total_players = cursor.fetchone()[0] or 0
        
        # Distinct bars with activity
        if bar_id:
            total_bars = 1  # Filtered to one bar
        else:
            cursor.execute('''
                SELECT COUNT(DISTINCT bar_id) FROM game_history 
                WHERE date(played_at) BETWEEN ? AND ?
            ''', (start_date, end_date))
            total_bars = cursor.fetchone()[0] or 0
        
        conn.close()
        return {
            'total_games': total_games,
            'total_players': total_players,
            'total_bars': total_bars
        }
    except Exception as e:
        print(f"[POS_ANALYTICS] Error in get_core_activity_summary: {e}")
        conn.close()
        return {
            'total_games': 0,
            'total_players': 0,
            'total_bars': 0
        }


def get_ad_summary(start_date, end_date, bar_id=None):
    """
    Get ad impressions and clicks summary from ad_events table.
    
    Args:
        start_date: str in 'YYYY-MM-DD' format
        end_date: str in 'YYYY-MM-DD' format
        bar_id: optional int to filter to single bar
        
    Returns:
        dict with total_impressions, total_clicks, ctr, unique_viewers
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Check if ad_events table exists (new system)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ad_events'")
        has_ad_events = cursor.fetchone() is not None
        
        if has_ad_events:
            # Use the new ad_events table
            if bar_id:
                cursor.execute('''
                    SELECT 
                        SUM(CASE WHEN event_type = 'impression' THEN 1 ELSE 0 END) as total_impressions,
                        SUM(CASE WHEN event_type = 'click' THEN 1 ELSE 0 END) as total_clicks,
                        COUNT(DISTINCT player_id) as unique_viewers
                    FROM ad_events
                    WHERE date(created_at) BETWEEN ? AND ?
                      AND bar_id = ?
                ''', (start_date, end_date, bar_id))
            else:
                cursor.execute('''
                    SELECT 
                        SUM(CASE WHEN event_type = 'impression' THEN 1 ELSE 0 END) as total_impressions,
                        SUM(CASE WHEN event_type = 'click' THEN 1 ELSE 0 END) as total_clicks,
                        COUNT(DISTINCT player_id) as unique_viewers
                    FROM ad_events
                    WHERE date(created_at) BETWEEN ? AND ?
                ''', (start_date, end_date))
            
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return {
                    'total_impressions': 0,
                    'total_clicks': 0,
                    'ctr': 0.0,
                    'unique_viewers': 0
                }
            
            total_impressions = row['total_impressions'] or 0
            total_clicks = row['total_clicks'] or 0
            unique_viewers = row['unique_viewers'] or 0
            ctr = round((total_clicks / total_impressions * 100), 2) if total_impressions > 0 else 0.0
            
            return {
                'total_impressions': total_impressions,
                'total_clicks': total_clicks,
                'ctr': ctr,
                'unique_viewers': unique_viewers
            }
        
        # Fallback to old ad_impressions table if ad_events doesn't exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ad_impressions'")
        if not cursor.fetchone():
            conn.close()
            return {
                'total_impressions': 0,
                'total_clicks': 0,
                'ctr': 0.0,
                'unique_viewers': 0
            }
        
        # Old table query
        if bar_id:
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_impressions,
                    SUM(CASE WHEN clicked = 1 THEN 1 ELSE 0 END) as total_clicks
                FROM ad_impressions
                WHERE date(impression_at) BETWEEN ? AND ?
                  AND bar_id = ?
            ''', (start_date, end_date, bar_id))
        else:
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_impressions,
                    SUM(CASE WHEN clicked = 1 THEN 1 ELSE 0 END) as total_clicks
                FROM ad_impressions
                WHERE date(impression_at) BETWEEN ? AND ?
            ''', (start_date, end_date))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row or row['total_impressions'] == 0:
            return {
                'total_impressions': 0,
                'total_clicks': 0,
                'ctr': 0.0,
                'unique_viewers': 0
            }
        
        total_impressions = row['total_impressions'] or 0
        total_clicks = row['total_clicks'] or 0
        ctr = round((total_clicks / total_impressions * 100), 2) if total_impressions > 0 else 0.0
        
        return {
            'total_impressions': total_impressions,
            'total_clicks': total_clicks,
            'ctr': ctr,
            'unique_viewers': 0  # Old table doesn't track this
        }
    except Exception as e:
        print(f"[POS_ANALYTICS] Error in get_ad_summary: {e}")
        conn.close()
        return {
            'total_impressions': 0,
            'total_clicks': 0,
            'ctr': 0.0
        }



# ============ TIME-SERIES DATA FOR CHARTS ============

def get_games_by_date(start_date, end_date, bar_id=None):
    """
    Get games count grouped by date for charts.
    
    Args:
        start_date: str in 'YYYY-MM-DD' format
        end_date: str in 'YYYY-MM-DD' format
        bar_id: optional int to filter to single bar
        
    Returns:
        list of dicts with date, games_count, unique_players
        sorted by date ascending
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        if bar_id:
            cursor.execute('''
                SELECT 
                    date(played_at) as game_date,
                    COUNT(*) as games_count,
                    COUNT(DISTINCT winner_id) + COUNT(DISTINCT loser_id) as player_appearances
                FROM game_history
                WHERE date(played_at) BETWEEN ? AND ?
                  AND bar_id = ?
                GROUP BY date(played_at)
                ORDER BY game_date ASC
            ''', (start_date, end_date, bar_id))
        else:
            cursor.execute('''
                SELECT 
                    date(played_at) as game_date,
                    COUNT(*) as games_count,
                    COUNT(DISTINCT winner_id) + COUNT(DISTINCT loser_id) as player_appearances
                FROM game_history
                WHERE date(played_at) BETWEEN ? AND ?
                GROUP BY date(played_at)
                ORDER BY game_date ASC
            ''', (start_date, end_date))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'date': row['game_date'],
                'games_count': row['games_count'] or 0,
                'unique_players': row['player_appearances'] or 0
            })
        
        conn.close()
        return results
    except Exception as e:
        print(f"[POS_ANALYTICS] Error in get_games_by_date: {e}")
        conn.close()
        return []


def get_pos_by_date(start_date, end_date, bar_id=None):
    """
    Get POS revenue grouped by date for charts.
    
    Args:
        start_date: str in 'YYYY-MM-DD' format
        end_date: str in 'YYYY-MM-DD' format
        bar_id: optional int to filter to single bar
        
    Returns:
        list of dicts with date, checks_count, total_revenue, avg_check_amount
        sorted by date ascending
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        if bar_id:
            cursor.execute('''
                SELECT 
                    business_date,
                    COUNT(*) as checks_count,
                    COALESCE(SUM(total_amount), 0) as total_revenue,
                    COALESCE(AVG(total_amount), 0) as avg_check_amount
                FROM pos_checks
                WHERE business_date BETWEEN ? AND ?
                  AND bar_id = ?
                GROUP BY business_date
                ORDER BY business_date ASC
            ''', (start_date, end_date, bar_id))
        else:
            cursor.execute('''
                SELECT 
                    business_date,
                    COUNT(*) as checks_count,
                    COALESCE(SUM(total_amount), 0) as total_revenue,
                    COALESCE(AVG(total_amount), 0) as avg_check_amount
                FROM pos_checks
                WHERE business_date BETWEEN ? AND ?
                GROUP BY business_date
                ORDER BY business_date ASC
            ''', (start_date, end_date))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'date': row['business_date'],
                'checks_count': row['checks_count'] or 0,
                'total_revenue': round(row['total_revenue'] or 0, 2),
                'avg_check_amount': round(row['avg_check_amount'] or 0, 2)
            })
        
        conn.close()
        return results
    except Exception as e:
        print(f"[POS_ANALYTICS] Error in get_pos_by_date: {e}")
        conn.close()
        return []



# ============ AD CAMPAIGN ESTIMATES ============

def get_campaign_estimates(bar_ids=None, placements=None):
    """
    Calculate realistic campaign estimates based on historical ad_events data.
    
    Args:
        bar_ids: optional list of bar IDs to filter (None = all bars)
        placements: optional list of placement codes to filter
        
    Returns:
        dict with estimated_impressions_per_week, estimated_ctr, 
        estimated_unique_players, data_quality
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Check if we have ad_events data
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ad_events'")
        if not cursor.fetchone():
            return _default_estimates()
        
        # Get stats from last 30 days
        bar_filter = ""
        placement_filter = ""
        params = []
        
        if bar_ids:
            placeholders = ','.join('?' * len(bar_ids))
            bar_filter = f"AND bar_id IN ({placeholders})"
            params.extend(bar_ids)
        
        if placements:
            placeholders = ','.join('?' * len(placements))
            placement_filter = f"AND placement IN ({placeholders})"
            params.extend(placements)
        
        # Query for 30-day stats
        cursor.execute(f'''
            SELECT 
                COUNT(*) as total_events,
                SUM(CASE WHEN event_type = 'impression' THEN 1 ELSE 0 END) as impressions,
                SUM(CASE WHEN event_type = 'click' THEN 1 ELSE 0 END) as clicks,
                COUNT(DISTINCT player_id) as unique_players,
                COUNT(DISTINCT date(created_at)) as active_days
            FROM ad_events
            WHERE created_at >= datetime('now', '-30 days')
            {bar_filter}
            {placement_filter}
        ''', params)
        
        row = cursor.fetchone()
        conn.close()
        
        if not row or row['impressions'] == 0:
            return _default_estimates()
        
        impressions_30d = row['impressions'] or 0
        clicks_30d = row['clicks'] or 0
        unique_players = row['unique_players'] or 0
        active_days = row['active_days'] or 1
        
        # Calculate weekly projections
        daily_impressions = impressions_30d / max(active_days, 1)
        weekly_impressions = round(daily_impressions * 7)
        
        # Calculate CTR
        ctr = round((clicks_30d / impressions_30d * 100), 1) if impressions_30d > 0 else 2.0
        
        # Data quality indicator
        data_quality = 'high' if impressions_30d > 1000 else ('medium' if impressions_30d > 100 else 'low')
        
        return {
            'estimated_impressions_per_week': weekly_impressions,
            'estimated_ctr': ctr,
            'estimated_unique_players': unique_players,
            'data_quality': data_quality,
            'based_on_days': active_days,
            'based_on_impressions': impressions_30d
        }
        
    except Exception as e:
        print(f"[POS_ANALYTICS] Error in get_campaign_estimates: {e}")
        conn.close()
        return _default_estimates()


def _default_estimates():
    """
    Return default estimates when no historical data is available.
    Clearly marked as estimates, not real data.
    """
    return {
        'estimated_impressions_per_week': 0,
        'estimated_ctr': 0,
        'estimated_unique_players': 0,
        'data_quality': 'no_data',
        'based_on_days': 0,
        'based_on_impressions': 0,
        'message': 'No historical data available. Estimates will improve as ads run.'
    }
