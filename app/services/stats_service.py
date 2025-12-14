"""
Stats Service - Heatmaps, Engagement Scores, League Metrics
"""
from ..database import get_db
import json
from datetime import datetime, timedelta

def compute_bar_engagement(bar_id, date):
    """Compute engagement score for a bar on a given date."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get match data
    cursor.execute('''SELECT COUNT(*), COUNT(DISTINCT winner_user_id) 
                      FROM game_history WHERE date(played_at) = ?''', (date,))
    row = cursor.fetchone()
    matches = row[0] or 0
    unique_players = row[1] or 0
    
    # Get queue activity
    cursor.execute('''SELECT COUNT(*) FROM queue''')
    queue_size = cursor.fetchone()[0] or 0
    
    # Calculate scores (0-100)
    player_score = min(unique_players * 4, 40)  # up to 40 points
    match_score = min(matches * 3, 40)  # up to 40 points
    queue_score = min(queue_size * 2, 20)  # up to 20 points
    
    engagement_score = min(player_score + match_score + queue_score, 100)
    
    # Determine peak hour
    cursor.execute('''SELECT strftime('%H', played_at) as hour, COUNT(*) as cnt 
                      FROM game_history WHERE date(played_at) = ?
                      GROUP BY hour ORDER BY cnt DESC LIMIT 1''', (date,))
    peak_row = cursor.fetchone()
    peak_hour = int(peak_row[0]) if peak_row else None
    
    # Upsert bar_engagement_daily
    cursor.execute('''INSERT OR REPLACE INTO bar_engagement_daily 
                      (bar_id, date, unique_players, matches_played, engagement_score, peak_hour)
                      VALUES (?, ?, ?, ?, ?, ?)''',
                   (bar_id, date, unique_players, matches, engagement_score, peak_hour))
    
    conn.commit()
    conn.close()
    
    return {
        'engagement_score': engagement_score,
        'unique_players': unique_players,
        'matches': matches,
        'peak_hour': peak_hour,
        'heat_label': get_heat_label(engagement_score)
    }

def get_heat_label(score):
    """Convert engagement score to heat label."""
    if score >= 70:
        return 'Hot'
    elif score >= 40:
        return 'Warm'
    return 'Chill'

def get_activity_heatmap(bar_id=None, weeks=4):
    """Get 7x24 activity heatmap."""
    conn = get_db()
    cursor = conn.cursor()
    
    cutoff = (datetime.now() - timedelta(weeks=weeks)).strftime('%Y-%m-%d')
    
    if bar_id:
        cursor.execute('''
            SELECT strftime('%w', played_at) as dow, strftime('%H', played_at) as hour, COUNT(*)
            FROM game_history
            WHERE played_at > ?
            GROUP BY dow, hour
        ''', (cutoff,))
    else:
        cursor.execute('''
            SELECT strftime('%w', played_at) as dow, strftime('%H', played_at) as hour, COUNT(*)
            FROM game_history
            WHERE played_at > ?
            GROUP BY dow, hour
        ''', (cutoff,))
    
    # Initialize 7x24 matrix
    heatmap = [[0 for _ in range(24)] for _ in range(7)]
    max_val = 1
    
    for row in cursor.fetchall():
        dow = int(row[0])
        hour = int(row[1])
        count = row[2]
        heatmap[dow][hour] = count
        max_val = max(max_val, count)
    
    conn.close()
    
    # Normalize to 0-100
    for d in range(7):
        for h in range(24):
            heatmap[d][h] = int(heatmap[d][h] / max_val * 100)
    
    return heatmap

def get_league_metrics(bar_id=None, period_days=30):
    """Get league replacement metrics."""
    conn = get_db()
    cursor = conn.cursor()
    
    cutoff = (datetime.now() - timedelta(days=period_days)).strftime('%Y-%m-%d')
    
    # Active ranked players
    cursor.execute('''SELECT COUNT(DISTINCT winner_user_id) FROM game_history 
                      WHERE played_at > ? AND mode = 'ranked' ''', (cutoff,))
    active_ranked = cursor.fetchone()[0] or 0
    
    # Total matches
    cursor.execute('''SELECT COUNT(*), 
                      SUM(CASE WHEN mode = 'ranked' THEN 1 ELSE 0 END),
                      SUM(CASE WHEN mode = 'casual' THEN 1 ELSE 0 END)
                      FROM game_history WHERE played_at > ?''', (cutoff,))
    row = cursor.fetchone()
    total_matches = row[0] or 0
    ranked_matches = row[1] or 0
    casual_matches = row[2] or 0
    
    # Retention (players active this period who were also active prior period)
    prev_cutoff = (datetime.now() - timedelta(days=period_days*2)).strftime('%Y-%m-%d')
    cursor.execute('''
        SELECT COUNT(DISTINCT g1.winner_user_id)
        FROM game_history g1
        WHERE g1.played_at > ? 
        AND g1.winner_user_id IN (
            SELECT DISTINCT winner_user_id FROM game_history 
            WHERE played_at BETWEEN ? AND ?
        )
    ''', (cutoff, prev_cutoff, cutoff))
    retained = cursor.fetchone()[0] or 0
    
    conn.close()
    
    ranked_ratio = (ranked_matches / total_matches * 100) if total_matches > 0 else 0
    
    return {
        'active_ranked_players': active_ranked,
        'total_matches': total_matches,
        'ranked_matches': ranked_matches,
        'casual_matches': casual_matches,
        'ranked_ratio': round(ranked_ratio, 1),
        'retained_players': retained,
        'period_days': period_days
    }
