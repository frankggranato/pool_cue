"""
Cohort Service - Player segmentation and personas
"""
from ..database import get_db
import json
from datetime import datetime, timedelta

COHORT_DEFINITIONS = {
    'WeekendWarrior': {
        'description': 'Plays mostly Fri/Sat',
        'check': lambda stats: stats.get('weekend_ratio', 0) > 0.6
    },
    'WeeknightRegular': {
        'description': 'Plays mostly Mon-Thu',
        'check': lambda stats: stats.get('weeknight_ratio', 0) > 0.6
    },
    'DiveBarLoyalist': {
        'description': 'Plays at 1-2 bars 80%+ of time',
        'check': lambda stats: stats.get('unique_bars', 99) <= 2 and stats.get('top_bar_ratio', 0) > 0.8
    },
    'BarHopper': {
        'description': 'Plays at 4+ different bars',
        'check': lambda stats: stats.get('unique_bars', 0) >= 4
    },
    'RankedGrinder': {
        'description': '60%+ ranked games',
        'check': lambda stats: stats.get('ranked_ratio', 0) > 0.6
    },
    'SocialCasual': {
        'description': '60%+ casual + many challenges',
        'check': lambda stats: stats.get('casual_ratio', 0) > 0.6 and stats.get('challenges', 0) > 3
    },
    'NightOwl': {
        'description': 'Plays after 10pm regularly',
        'check': lambda stats: stats.get('late_night_ratio', 0) > 0.4
    },
    'HighRoller': {
        'description': 'Diamond/Platinum division',
        'check': lambda stats: stats.get('division', '') in ['Diamond', 'Platinum']
    },
    'Newcomer': {
        'description': 'Less than 10 total games',
        'check': lambda stats: stats.get('total_games', 0) < 10
    },
    'Veteran': {
        'description': '50+ total games',
        'check': lambda stats: stats.get('total_games', 0) >= 50
    }
}

def compute_user_stats(user_id, days=90):
    """Compute stats for cohort assignment."""
    conn = get_db()
    cursor = conn.cursor()
    
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    stats = {}
    
    # Total games and wins
    cursor.execute('''SELECT COUNT(*) FROM game_history 
                      WHERE (winner_user_id = ? OR loser_user_id = ?) AND played_at > ?''',
                   (user_id, user_id, cutoff))
    stats['total_games'] = cursor.fetchone()[0] or 0
    
    # Day of week distribution
    cursor.execute('''SELECT strftime('%w', played_at) as dow, COUNT(*) 
                      FROM game_history 
                      WHERE (winner_user_id = ? OR loser_user_id = ?) AND played_at > ?
                      GROUP BY dow''', (user_id, user_id, cutoff))
    dow_counts = {int(r[0]): r[1] for r in cursor.fetchall()}
    total = sum(dow_counts.values()) or 1
    
    weekend = dow_counts.get(0, 0) + dow_counts.get(5, 0) + dow_counts.get(6, 0)
    weeknight = sum(dow_counts.get(d, 0) for d in [1, 2, 3, 4])
    stats['weekend_ratio'] = weekend / total
    stats['weeknight_ratio'] = weeknight / total
    
    # Hour distribution
    cursor.execute('''SELECT strftime('%H', played_at) as hour, COUNT(*) 
                      FROM game_history 
                      WHERE (winner_user_id = ? OR loser_user_id = ?) AND played_at > ?
                      GROUP BY hour''', (user_id, user_id, cutoff))
    hour_counts = {int(r[0]): r[1] for r in cursor.fetchall()}
    late_night = sum(hour_counts.get(h, 0) for h in range(22, 24)) + sum(hour_counts.get(h, 0) for h in range(0, 3))
    stats['late_night_ratio'] = late_night / total if total > 0 else 0
    
    # Unique bars (placeholder - would need bar_id in game_history)
    stats['unique_bars'] = 1  # Default for now
    stats['top_bar_ratio'] = 1.0
    
    # Ranked vs casual
    cursor.execute('''SELECT mode, COUNT(*) FROM game_history 
                      WHERE (winner_user_id = ? OR loser_user_id = ?) AND played_at > ?
                      GROUP BY mode''', (user_id, user_id, cutoff))
    mode_counts = {r[0]: r[1] for r in cursor.fetchall()}
    ranked = mode_counts.get('ranked', 0)
    casual = mode_counts.get('casual', 0)
    mode_total = ranked + casual or 1
    stats['ranked_ratio'] = ranked / mode_total
    stats['casual_ratio'] = casual / mode_total
    
    # Challenges
    cursor.execute('''SELECT COUNT(*) FROM challenges WHERE challenger_user_id = ? AND created_at > ?''',
                   (user_id, cutoff))
    stats['challenges'] = cursor.fetchone()[0] or 0
    
    # Division
    cursor.execute('SELECT division FROM player_profiles WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    stats['division'] = row[0] if row else 'Bronze'
    
    conn.close()
    return stats

def assign_cohorts(user_id):
    """Assign cohort tags to a user."""
    stats = compute_user_stats(user_id)
    tags = []
    
    for cohort_name, definition in COHORT_DEFINITIONS.items():
        try:
            if definition['check'](stats):
                tags.append(cohort_name)
        except:
            pass
    
    # Save to database
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''INSERT OR REPLACE INTO player_cohorts (user_id, cohort_tags_json, last_computed_at)
                      VALUES (?, ?, CURRENT_TIMESTAMP)''',
                   (user_id, json.dumps(tags)))
    conn.commit()
    conn.close()
    
    return tags

def batch_compute_cohorts():
    """Recompute cohorts for all active users."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get users with recent activity
    cutoff = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    cursor.execute('''SELECT DISTINCT winner_user_id FROM game_history WHERE played_at > ?
                      UNION SELECT DISTINCT loser_user_id FROM game_history WHERE played_at > ?''',
                   (cutoff, cutoff))
    user_ids = [r[0] for r in cursor.fetchall() if r[0]]
    conn.close()
    
    results = {}
    for user_id in user_ids:
        tags = assign_cohorts(user_id)
        results[user_id] = tags
    
    return results

def get_cohort_breakdown():
    """Get global cohort distribution."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT cohort_tags_json FROM player_cohorts')
    
    counts = {name: 0 for name in COHORT_DEFINITIONS.keys()}
    total = 0
    
    for row in cursor.fetchall():
        tags = json.loads(row[0]) if row[0] else []
        total += 1
        for tag in tags:
            if tag in counts:
                counts[tag] += 1
    
    conn.close()
    
    # Calculate percentages
    breakdown = []
    for name, count in counts.items():
        pct = (count / total * 100) if total > 0 else 0
        breakdown.append({
            'name': name,
            'description': COHORT_DEFINITIONS[name]['description'],
            'count': count,
            'percentage': round(pct, 1)
        })
    
    breakdown.sort(key=lambda x: -x['count'])
    return breakdown

def get_user_cohorts(user_id):
    """Get cohorts for a specific user."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT cohort_tags_json FROM player_cohorts WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row and row[0]:
        return json.loads(row[0])
    return []
