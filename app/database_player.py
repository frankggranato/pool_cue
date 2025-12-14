"""
Database extensions for Player App
"""
import sqlite3
from datetime import datetime, timedelta
from .database import get_db, DB_PATH
import os

def init_player_db():
    """Initialize player app tables."""
    conn = get_db()
    cursor = conn.cursor()
    
    # User accounts
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            phone TEXT UNIQUE,
            password_hash TEXT,
            nickname TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_login_at DATETIME,
            default_mode TEXT DEFAULT 'casual',
            home_bar_id INTEGER,
            show_rating INTEGER DEFAULT 1,
            show_history INTEGER DEFAULT 1
        )
    ''')
    
    # Player profiles (ratings & stats)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            global_rating INTEGER DEFAULT 1000,
            global_wins INTEGER DEFAULT 0,
            global_losses INTEGER DEFAULT 0,
            division TEXT DEFAULT 'Bronze',
            achievements_json TEXT DEFAULT '[]',
            FOREIGN KEY (user_id) REFERENCES user_accounts(id)
        )
    ''')
    
    # Devices for push notifications
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            device_type TEXT DEFAULT 'web',
            push_token TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen_at DATETIME,
            notifications_prefs_json TEXT DEFAULT '{"queue_status":true,"promos":true,"league":true,"challenges":true}',
            FOREIGN KEY (user_id) REFERENCES user_accounts(id)
        )
    ''')
    
    # Bars table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            address TEXT,
            phone TEXT,
            hours TEXT,
            lat REAL,
            lng REAL,
            promo_text TEXT,
            league_night TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    ''')

    # Favorite bars
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS favorite_bars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            bar_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES user_accounts(id),
            FOREIGN KEY (bar_id) REFERENCES bars(id)
        )
    ''')
    
    # Friends
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS friends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            friend_user_id INTEGER,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            accepted_at DATETIME,
            FOREIGN KEY (user_id) REFERENCES user_accounts(id),
            FOREIGN KEY (friend_user_id) REFERENCES user_accounts(id),
            UNIQUE(user_id, friend_user_id)
        )
    ''')
    
    # Challenges
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            challenger_user_id INTEGER,
            challenged_user_id INTEGER,
            bar_id INTEGER,
            requested_mode TEXT DEFAULT 'casual',
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            responded_at DATETIME,
            linked_match_id INTEGER,
            FOREIGN KEY (challenger_user_id) REFERENCES user_accounts(id),
            FOREIGN KEY (challenged_user_id) REFERENCES user_accounts(id)
        )
    ''')
    
    # Analytics events
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS analytics_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            user_id INTEGER,
            bar_id INTEGER,
            data_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Session tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            session_token TEXT UNIQUE,
            device_info TEXT,
            ip_address TEXT,
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_active_at DATETIME,
            ended_at DATETIME,
            FOREIGN KEY (user_id) REFERENCES user_accounts(id)
        )
    ''')
    
    # Insert default bar if none exists
    cursor.execute('SELECT COUNT(*) FROM bars')
    if cursor.fetchone()[0] == 0:
        cursor.execute('''INSERT INTO bars (name, address, promo_text) 
                          VALUES ('Demo Bar', '123 Main St', 'Happy Hour 5-7pm!')''')
    
    # Migrations
    for sql in [
        'ALTER TABLE challenges ADD COLUMN message TEXT',
    ]:
        try:
            cursor.execute(sql)
        except:
            pass
    
    conn.commit()
    conn.close()


def log_analytics(event_type, user_id=None, bar_id=None, data=None):
    """Log analytics event for data insights."""
    import json
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO analytics_events (event_type, user_id, bar_id, data_json)
                      VALUES (?, ?, ?, ?)''', 
                   (event_type, user_id, bar_id, json.dumps(data) if data else None))
    conn.commit()
    conn.close()

def get_analytics_summary():
    """Get analytics data for admin dashboard."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Total users
    cursor.execute('SELECT COUNT(*) FROM user_accounts')
    total_users = cursor.fetchone()[0]
    
    # Active today
    cursor.execute('''SELECT COUNT(DISTINCT user_id) FROM user_sessions 
                      WHERE last_active_at > datetime('now', '-1 day')''')
    active_today = cursor.fetchone()[0]
    
    # Total games played
    cursor.execute('SELECT COUNT(*) FROM game_history')
    total_games = cursor.fetchone()[0]
    
    # Games today
    cursor.execute('''SELECT COUNT(*) FROM game_history 
                      WHERE played_at > datetime('now', '-1 day')''')
    games_today = cursor.fetchone()[0]
    
    # Peak hours
    cursor.execute('''SELECT strftime('%H', played_at) as hour, COUNT(*) as cnt 
                      FROM game_history GROUP BY hour ORDER BY cnt DESC LIMIT 5''')
    peak_hours = [{'hour': r[0], 'count': r[1]} for r in cursor.fetchall()]
    
    # Average game duration
    cursor.execute('SELECT AVG(duration_seconds) FROM game_history WHERE duration_seconds > 30')
    avg_duration = cursor.fetchone()[0] or 0
    
    # Top players
    cursor.execute('''SELECT p.nickname, pp.global_rating, pp.global_wins, pp.global_losses
                      FROM player_profiles pp 
                      JOIN players p ON pp.user_id = p.id
                      ORDER BY pp.global_rating DESC LIMIT 10''')
    top_players = [{'name': r[0], 'rating': r[1], 'wins': r[2], 'losses': r[3]} for r in cursor.fetchall()]
    
    conn.close()
    
    return {
        'total_users': total_users,
        'active_today': active_today,
        'total_games': total_games,
        'games_today': games_today,
        'peak_hours': peak_hours,
        'avg_duration_minutes': round(avg_duration / 60, 1) if avg_duration else 0,
        'top_players': top_players
    }

def get_friends_at_bars(user_id):
    """Get friends who are currently in queue at any bar."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get accepted friends who are in a queue
    cursor.execute('''
        SELECT u.id, u.nickname, b.name as bar_name, b.id as bar_id, q.position
        FROM friends f
        JOIN user_accounts u ON (f.friend_user_id = u.id OR f.user_id = u.id)
        JOIN players p ON p.nickname = u.nickname
        JOIN queue q ON q.player_id = p.id
        JOIN bars b ON b.id = 1
        WHERE f.status = 'accepted'
        AND (f.user_id = ? OR f.friend_user_id = ?)
        AND u.id != ?
        ORDER BY b.name, q.position
    ''', (user_id, user_id, user_id))
    
    friends = []
    for row in cursor.fetchall():
        friends.append({
            'id': row[0],
            'nickname': row[1],
            'bar_name': row[2],
            'bar_id': row[3],
            'position': row[4]
        })
    
    conn.close()
    return friends
