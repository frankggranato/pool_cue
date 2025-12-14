"""
Ranking Service - Location-Aware Player Rankings for Pool Cue
==============================================================

Provides hierarchical, location-specific rankings:
- Bar-level: Rankings at a specific venue
- Borough-level: NYC only (Manhattan, Brooklyn, Queens, Bronx, Staten Island)
- City-level: Rankings within a city/town
- State-level: Rankings within a state
- Global: All players across all locations

This allows players to be "king of their bar" while also seeing
how they rank citywide, statewide, and nationally.
"""

from ..database import get_db
from .location_service import NYC_BOROUGHS, normalize_borough

# Ranking scopes - from most specific to broadest
RANKING_SCOPES = ['bar', 'neighborhood', 'borough', 'city', 'state', 'global']

# Minimum games required to appear on leaderboards by scope
MIN_GAMES_BY_SCOPE = {
    'bar': 3,
    'neighborhood': 5,
    'borough': 5,
    'city': 5,
    'state': 10,
    'global': 10
}


def get_leaderboard_for_bar(bar_id, limit=50, metric='wins'):
    """
    Get leaderboard for a specific bar.
    Uses player_bar_rankings for accurate per-bar stats.
    
    Args:
        bar_id: ID of the bar
        limit: Maximum players to return
        metric: 'wins', 'rating', 'winrate', or 'games'
    
    Returns:
        List of player dicts with rank, stats, and player info
    """
    conn = get_db()
    cursor = conn.cursor()
    
    min_games = MIN_GAMES_BY_SCOPE['bar']
    
    # Determine ORDER BY clause
    order_by = {
        'wins': 'pbr.wins DESC, pbr.rating DESC',
        'rating': 'pbr.rating DESC, pbr.wins DESC',
        'winrate': 'win_rate DESC, pbr.wins DESC',
        'games': 'pbr.games_played DESC, pbr.wins DESC'
    }.get(metric, 'pbr.wins DESC, pbr.rating DESC')
    
    cursor.execute(f'''
        SELECT 
            p.id,
            p.nickname,
            p.account_id,
            pbr.rating,
            pbr.wins,
            pbr.losses,
            pbr.games_played,
            pbr.division,
            CASE WHEN (pbr.wins + pbr.losses) > 0 
                 THEN ROUND(100.0 * pbr.wins / (pbr.wins + pbr.losses), 1) 
                 ELSE 0 END as win_rate,
            b.name as bar_name,
            b.city,
            b.state,
            b.borough
        FROM player_bar_rankings pbr
        JOIN players p ON pbr.player_id = p.id
        JOIN bars b ON pbr.bar_id = b.id
        WHERE pbr.bar_id = ? 
          AND pbr.games_played >= ?
          AND (p.is_active = 1 OR p.is_active IS NULL)
        ORDER BY {order_by}
        LIMIT ?
    ''', (bar_id, min_games, limit))
    
    players = []
    for i, row in enumerate(cursor.fetchall(), 1):
        players.append({
            'rank': i,
            'player_id': row['id'],
            'nickname': row['nickname'],
            'is_guest': row['account_id'] is None,
            'rating': row['rating'] or 1000,
            'wins': row['wins'] or 0,
            'losses': row['losses'] or 0,
            'games': row['games_played'] or 0,
            'win_rate': row['win_rate'] or 0,
            'division': row['division'] or 'Bronze',
            'bar_name': row['bar_name'],
            'city': row['city'],
            'state': row['state'],
            'borough': normalize_borough(row['borough'])
        })
    
    conn.close()
    return players


def get_leaderboard_for_borough(borough, limit=50, metric='wins'):
    """
    Get leaderboard for a NYC borough.
    Aggregates stats from all bars in that borough.
    
    Args:
        borough: One of the 5 NYC boroughs (normalized)
        limit: Maximum players to return
        metric: 'wins', 'rating', 'winrate', or 'games'
    
    Returns:
        List of player dicts with aggregated stats across the borough
    """
    # Normalize borough name
    boro = normalize_borough(borough)
    if not boro or boro not in NYC_BOROUGHS:
        return []
    
    conn = get_db()
    cursor = conn.cursor()
    
    min_games = MIN_GAMES_BY_SCOPE['borough']
    
    # Determine ORDER BY clause
    order_by = {
        'wins': 'total_wins DESC, avg_rating DESC',
        'rating': 'avg_rating DESC, total_wins DESC',
        'winrate': 'win_rate DESC, total_wins DESC',
        'games': 'total_games DESC, total_wins DESC'
    }.get(metric, 'total_wins DESC, avg_rating DESC')
    
    cursor.execute(f'''
        SELECT 
            p.id,
            p.nickname,
            p.account_id,
            p.rating as global_rating,
            p.division as global_division,
            SUM(pbr.wins) as total_wins,
            SUM(pbr.losses) as total_losses,
            SUM(pbr.games_played) as total_games,
            ROUND(AVG(pbr.rating), 0) as avg_rating,
            CASE WHEN SUM(pbr.wins + pbr.losses) > 0 
                 THEN ROUND(100.0 * SUM(pbr.wins) / SUM(pbr.wins + pbr.losses), 1) 
                 ELSE 0 END as win_rate,
            COUNT(DISTINCT pbr.bar_id) as bars_played
        FROM player_bar_rankings pbr
        JOIN players p ON pbr.player_id = p.id
        JOIN bars b ON pbr.bar_id = b.id
        WHERE (b.borough = ? OR b.borough = ?)
          AND b.is_active = 1
          AND (p.is_active = 1 OR p.is_active IS NULL)
        GROUP BY p.id
        HAVING total_games >= ?
        ORDER BY {order_by}
        LIMIT ?
    ''', (boro, boro.lower(), min_games, limit))
    
    players = []
    for i, row in enumerate(cursor.fetchall(), 1):
        players.append({
            'rank': i,
            'player_id': row['id'],
            'nickname': row['nickname'],
            'is_guest': row['account_id'] is None,
            'rating': int(row['avg_rating'] or 1000),
            'global_rating': row['global_rating'] or 1000,
            'wins': row['total_wins'] or 0,
            'losses': row['total_losses'] or 0,
            'games': row['total_games'] or 0,
            'win_rate': row['win_rate'] or 0,
            'division': row['global_division'] or 'Bronze',
            'bars_played': row['bars_played'] or 0,
            'scope': boro
        })
    
    conn.close()
    return players


def get_leaderboard_for_city(city, state, limit=50, metric='wins'):
    """
    Get leaderboard for a city/town.
    For NYC, this aggregates all 5 boroughs.
    
    Args:
        city: City name (e.g., 'New York', 'Los Angeles')
        state: State code (e.g., 'NY', 'CA')
        limit: Maximum players to return
        metric: 'wins', 'rating', 'winrate', or 'games'
    
    Returns:
        List of player dicts with aggregated stats across the city
    """
    conn = get_db()
    cursor = conn.cursor()
    
    min_games = MIN_GAMES_BY_SCOPE['city']
    
    # Determine ORDER BY clause
    order_by = {
        'wins': 'total_wins DESC, avg_rating DESC',
        'rating': 'avg_rating DESC, total_wins DESC',
        'winrate': 'win_rate DESC, total_wins DESC',
        'games': 'total_games DESC, total_wins DESC'
    }.get(metric, 'total_wins DESC, avg_rating DESC')
    
    cursor.execute(f'''
        SELECT 
            p.id,
            p.nickname,
            p.account_id,
            p.rating as global_rating,
            p.division as global_division,
            SUM(pbr.wins) as total_wins,
            SUM(pbr.losses) as total_losses,
            SUM(pbr.games_played) as total_games,
            ROUND(AVG(pbr.rating), 0) as avg_rating,
            CASE WHEN SUM(pbr.wins + pbr.losses) > 0 
                 THEN ROUND(100.0 * SUM(pbr.wins) / SUM(pbr.wins + pbr.losses), 1) 
                 ELSE 0 END as win_rate,
            COUNT(DISTINCT pbr.bar_id) as bars_played
        FROM player_bar_rankings pbr
        JOIN players p ON pbr.player_id = p.id
        JOIN bars b ON pbr.bar_id = b.id
        WHERE LOWER(b.city) = LOWER(?)
          AND UPPER(b.state) = UPPER(?)
          AND b.is_active = 1
          AND (p.is_active = 1 OR p.is_active IS NULL)
        GROUP BY p.id
        HAVING total_games >= ?
        ORDER BY {order_by}
        LIMIT ?
    ''', (city, state, min_games, limit))
    
    players = []
    for i, row in enumerate(cursor.fetchall(), 1):
        players.append({
            'rank': i,
            'player_id': row['id'],
            'nickname': row['nickname'],
            'is_guest': row['account_id'] is None,
            'rating': int(row['avg_rating'] or 1000),
            'global_rating': row['global_rating'] or 1000,
            'wins': row['total_wins'] or 0,
            'losses': row['total_losses'] or 0,
            'games': row['total_games'] or 0,
            'win_rate': row['win_rate'] or 0,
            'division': row['global_division'] or 'Bronze',
            'bars_played': row['bars_played'] or 0,
            'scope': f"{city}, {state}"
        })
    
    conn.close()
    return players


def get_leaderboard_for_state(state, limit=50, metric='wins'):
    """
    Get leaderboard for a state.
    Aggregates stats from all bars in that state.
    
    Args:
        state: State code (e.g., 'NY', 'CA')
        limit: Maximum players to return
        metric: 'wins', 'rating', 'winrate', or 'games'
    
    Returns:
        List of player dicts with aggregated stats across the state
    """
    conn = get_db()
    cursor = conn.cursor()
    
    min_games = MIN_GAMES_BY_SCOPE['state']
    
    # Determine ORDER BY clause
    order_by = {
        'wins': 'total_wins DESC, avg_rating DESC',
        'rating': 'avg_rating DESC, total_wins DESC',
        'winrate': 'win_rate DESC, total_wins DESC',
        'games': 'total_games DESC, total_wins DESC'
    }.get(metric, 'total_wins DESC, avg_rating DESC')
    
    cursor.execute(f'''
        SELECT 
            p.id,
            p.nickname,
            p.account_id,
            p.rating as global_rating,
            p.division as global_division,
            SUM(pbr.wins) as total_wins,
            SUM(pbr.losses) as total_losses,
            SUM(pbr.games_played) as total_games,
            ROUND(AVG(pbr.rating), 0) as avg_rating,
            CASE WHEN SUM(pbr.wins + pbr.losses) > 0 
                 THEN ROUND(100.0 * SUM(pbr.wins) / SUM(pbr.wins + pbr.losses), 1) 
                 ELSE 0 END as win_rate,
            COUNT(DISTINCT pbr.bar_id) as bars_played,
            COUNT(DISTINCT b.city) as cities_played
        FROM player_bar_rankings pbr
        JOIN players p ON pbr.player_id = p.id
        JOIN bars b ON pbr.bar_id = b.id
        WHERE UPPER(b.state) = UPPER(?)
          AND b.is_active = 1
          AND (p.is_active = 1 OR p.is_active IS NULL)
        GROUP BY p.id
        HAVING total_games >= ?
        ORDER BY {order_by}
        LIMIT ?
    ''', (state, min_games, limit))
    
    players = []
    for i, row in enumerate(cursor.fetchall(), 1):
        players.append({
            'rank': i,
            'player_id': row['id'],
            'nickname': row['nickname'],
            'is_guest': row['account_id'] is None,
            'rating': int(row['avg_rating'] or 1000),
            'global_rating': row['global_rating'] or 1000,
            'wins': row['total_wins'] or 0,
            'losses': row['total_losses'] or 0,
            'games': row['total_games'] or 0,
            'win_rate': row['win_rate'] or 0,
            'division': row['global_division'] or 'Bronze',
            'bars_played': row['bars_played'] or 0,
            'cities_played': row['cities_played'] or 0,
            'scope': state.upper()
        })
    
    conn.close()
    return players


def get_leaderboard_global(limit=50, metric='wins'):
    """
    Get global leaderboard across all locations.
    Uses aggregated player stats from players table.
    
    Args:
        limit: Maximum players to return
        metric: 'wins', 'rating', 'winrate', or 'games'
    
    Returns:
        List of player dicts with global stats
    """
    conn = get_db()
    cursor = conn.cursor()
    
    min_games = MIN_GAMES_BY_SCOPE['global']
    
    # Determine ORDER BY clause
    order_by = {
        'wins': 'p.wins DESC, p.rating DESC',
        'rating': 'p.rating DESC, p.wins DESC',
        'winrate': 'win_rate DESC, p.wins DESC',
        'games': 'total_games DESC, p.wins DESC'
    }.get(metric, 'p.wins DESC, p.rating DESC')
    
    cursor.execute(f'''
        SELECT 
            p.id,
            p.nickname,
            p.account_id,
            p.rating,
            p.division,
            p.wins,
            p.losses,
            (p.wins + p.losses) as total_games,
            CASE WHEN (p.wins + p.losses) > 0 
                 THEN ROUND(100.0 * p.wins / (p.wins + p.losses), 1) 
                 ELSE 0 END as win_rate,
            p.tokens_balance,
            (SELECT COUNT(DISTINCT bar_id) FROM player_bar_rankings WHERE player_id = p.id) as bars_played,
            (SELECT COUNT(DISTINCT b.state) FROM player_bar_rankings pbr 
             JOIN bars b ON pbr.bar_id = b.id WHERE pbr.player_id = p.id) as states_played
        FROM players p
        WHERE (p.wins + p.losses) >= ?
          AND (p.is_active = 1 OR p.is_active IS NULL)
        ORDER BY {order_by}
        LIMIT ?
    ''', (min_games, limit))
    
    players = []
    for i, row in enumerate(cursor.fetchall(), 1):
        players.append({
            'rank': i,
            'player_id': row['id'],
            'nickname': row['nickname'],
            'is_guest': row['account_id'] is None,
            'rating': row['rating'] or 1000,
            'wins': row['wins'] or 0,
            'losses': row['losses'] or 0,
            'games': row['total_games'] or 0,
            'win_rate': row['win_rate'] or 0,
            'division': row['division'] or 'Bronze',
            'tokens': row['tokens_balance'] or 0,
            'bars_played': row['bars_played'] or 0,
            'states_played': row['states_played'] or 0,
            'scope': 'Global'
        })
    
    conn.close()
    return players


def get_player_rankings_all_scopes(player_id):
    """
    Get a player's ranking in all applicable scopes.
    This shows how a player ranks locally vs regionally vs globally.
    
    Args:
        player_id: The player's ID
    
    Returns:
        Dict with rankings at each scope level the player has activity in
    """
    conn = get_db()
    cursor = conn.cursor()
    
    result = {
        'player_id': player_id,
        'rankings': {
            'bars': [],      # [{bar_id, bar_name, rank, total_players, rating, wins}]
            'boroughs': [],  # [{borough, rank, total_players, wins}]
            'cities': [],    # [{city, state, rank, total_players, wins}]
            'states': [],    # [{state, rank, total_players, wins}]
            'global': None   # {rank, total_players, wins}
        }
    }
    
    # Get player info
    cursor.execute('SELECT nickname, rating, wins, losses FROM players WHERE id = ?', (player_id,))
    player_row = cursor.fetchone()
    if not player_row:
        conn.close()
        return result
    
    result['nickname'] = player_row['nickname']
    result['global_rating'] = player_row['rating'] or 1000
    result['global_wins'] = player_row['wins'] or 0
    result['global_losses'] = player_row['losses'] or 0
    
    # Bar-level rankings
    cursor.execute('''
        SELECT 
            pbr.bar_id,
            b.name as bar_name,
            b.city,
            b.state,
            b.borough,
            pbr.rating,
            pbr.wins,
            pbr.losses,
            pbr.games_played,
            (SELECT COUNT(*) + 1 FROM player_bar_rankings pbr2 
             WHERE pbr2.bar_id = pbr.bar_id 
               AND pbr2.games_played >= 3
               AND pbr2.wins > pbr.wins) as rank,
            (SELECT COUNT(*) FROM player_bar_rankings pbr3 
             WHERE pbr3.bar_id = pbr.bar_id AND pbr3.games_played >= 3) as total_players
        FROM player_bar_rankings pbr
        JOIN bars b ON pbr.bar_id = b.id
        WHERE pbr.player_id = ?
        ORDER BY pbr.wins DESC
    ''', (player_id,))
    
    for row in cursor.fetchall():
        result['rankings']['bars'].append({
            'bar_id': row['bar_id'],
            'bar_name': row['bar_name'],
            'city': row['city'],
            'state': row['state'],
            'borough': normalize_borough(row['borough']),
            'rank': row['rank'],
            'total_players': row['total_players'],
            'rating': row['rating'] or 1000,
            'wins': row['wins'] or 0,
            'losses': row['losses'] or 0,
            'games': row['games_played'] or 0
        })
    
    # Borough-level rankings (NYC only)
    cursor.execute('''
        SELECT DISTINCT b.borough 
        FROM player_bar_rankings pbr
        JOIN bars b ON pbr.bar_id = b.id
        WHERE pbr.player_id = ? 
          AND b.borough IS NOT NULL AND b.borough != ''
    ''', (player_id,))
    
    for boro_row in cursor.fetchall():
        boro = normalize_borough(boro_row['borough'])
        if not boro:
            continue
            
        # Get player's wins in this borough
        cursor.execute('''
            SELECT SUM(pbr.wins) as total_wins, SUM(pbr.games_played) as total_games
            FROM player_bar_rankings pbr
            JOIN bars b ON pbr.bar_id = b.id
            WHERE pbr.player_id = ? AND (b.borough = ? OR b.borough = ?)
        ''', (player_id, boro, boro.lower()))
        stats = cursor.fetchone()
        player_wins = stats['total_wins'] or 0
        player_games = stats['total_games'] or 0
        
        if player_games < MIN_GAMES_BY_SCOPE['borough']:
            continue
        
        # Get rank in borough
        cursor.execute('''
            SELECT COUNT(*) + 1 as rank
            FROM (
                SELECT SUM(pbr.wins) as total_wins
                FROM player_bar_rankings pbr
                JOIN bars b ON pbr.bar_id = b.id
                JOIN players p ON pbr.player_id = p.id
                WHERE (b.borough = ? OR b.borough = ?)
                  AND (p.is_active = 1 OR p.is_active IS NULL)
                GROUP BY pbr.player_id
                HAVING SUM(pbr.games_played) >= ?
            ) AS ranked
            WHERE total_wins > ?
        ''', (boro, boro.lower(), MIN_GAMES_BY_SCOPE['borough'], player_wins))
        rank = cursor.fetchone()['rank']
        
        # Get total players in borough
        cursor.execute('''
            SELECT COUNT(DISTINCT pbr.player_id) as total
            FROM player_bar_rankings pbr
            JOIN bars b ON pbr.bar_id = b.id
            WHERE (b.borough = ? OR b.borough = ?)
            GROUP BY pbr.player_id
            HAVING SUM(pbr.games_played) >= ?
        ''', (boro, boro.lower(), MIN_GAMES_BY_SCOPE['borough']))
        total = len(cursor.fetchall())
        
        result['rankings']['boroughs'].append({
            'borough': boro,
            'rank': rank,
            'total_players': total,
            'wins': player_wins,
            'games': player_games
        })
    
    # City-level rankings
    cursor.execute('''
        SELECT DISTINCT b.city, b.state
        FROM player_bar_rankings pbr
        JOIN bars b ON pbr.bar_id = b.id
        WHERE pbr.player_id = ? 
          AND b.city IS NOT NULL AND b.city != ''
    ''', (player_id,))
    
    for city_row in cursor.fetchall():
        city = city_row['city']
        state = city_row['state']
        
        # Get player's wins in this city
        cursor.execute('''
            SELECT SUM(pbr.wins) as total_wins, SUM(pbr.games_played) as total_games
            FROM player_bar_rankings pbr
            JOIN bars b ON pbr.bar_id = b.id
            WHERE pbr.player_id = ? AND LOWER(b.city) = LOWER(?) AND UPPER(b.state) = UPPER(?)
        ''', (player_id, city, state))
        stats = cursor.fetchone()
        player_wins = stats['total_wins'] or 0
        player_games = stats['total_games'] or 0
        
        if player_games < MIN_GAMES_BY_SCOPE['city']:
            continue
        
        # Get rank in city
        cursor.execute('''
            SELECT COUNT(*) + 1 as rank
            FROM (
                SELECT SUM(pbr.wins) as total_wins
                FROM player_bar_rankings pbr
                JOIN bars b ON pbr.bar_id = b.id
                JOIN players p ON pbr.player_id = p.id
                WHERE LOWER(b.city) = LOWER(?) AND UPPER(b.state) = UPPER(?)
                  AND (p.is_active = 1 OR p.is_active IS NULL)
                GROUP BY pbr.player_id
                HAVING SUM(pbr.games_played) >= ?
            ) AS ranked
            WHERE total_wins > ?
        ''', (city, state, MIN_GAMES_BY_SCOPE['city'], player_wins))
        rank = cursor.fetchone()['rank']
        
        # Get total players in city
        cursor.execute('''
            SELECT COUNT(*) as total FROM (
                SELECT pbr.player_id
                FROM player_bar_rankings pbr
                JOIN bars b ON pbr.bar_id = b.id
                WHERE LOWER(b.city) = LOWER(?) AND UPPER(b.state) = UPPER(?)
                GROUP BY pbr.player_id
                HAVING SUM(pbr.games_played) >= ?
            )
        ''', (city, state, MIN_GAMES_BY_SCOPE['city']))
        total = cursor.fetchone()['total']
        
        result['rankings']['cities'].append({
            'city': city,
            'state': state,
            'rank': rank,
            'total_players': total,
            'wins': player_wins,
            'games': player_games
        })
    
    # State-level rankings
    cursor.execute('''
        SELECT DISTINCT b.state
        FROM player_bar_rankings pbr
        JOIN bars b ON pbr.bar_id = b.id
        WHERE pbr.player_id = ? 
          AND b.state IS NOT NULL AND b.state != ''
    ''', (player_id,))
    
    for state_row in cursor.fetchall():
        state = state_row['state']
        
        # Get player's wins in this state
        cursor.execute('''
            SELECT SUM(pbr.wins) as total_wins, SUM(pbr.games_played) as total_games
            FROM player_bar_rankings pbr
            JOIN bars b ON pbr.bar_id = b.id
            WHERE pbr.player_id = ? AND UPPER(b.state) = UPPER(?)
        ''', (player_id, state))
        stats = cursor.fetchone()
        player_wins = stats['total_wins'] or 0
        player_games = stats['total_games'] or 0
        
        if player_games < MIN_GAMES_BY_SCOPE['state']:
            continue
        
        # Get rank in state
        cursor.execute('''
            SELECT COUNT(*) + 1 as rank
            FROM (
                SELECT SUM(pbr.wins) as total_wins
                FROM player_bar_rankings pbr
                JOIN bars b ON pbr.bar_id = b.id
                JOIN players p ON pbr.player_id = p.id
                WHERE UPPER(b.state) = UPPER(?)
                  AND (p.is_active = 1 OR p.is_active IS NULL)
                GROUP BY pbr.player_id
                HAVING SUM(pbr.games_played) >= ?
            ) AS ranked
            WHERE total_wins > ?
        ''', (state, MIN_GAMES_BY_SCOPE['state'], player_wins))
        rank = cursor.fetchone()['rank']
        
        # Get total players in state
        cursor.execute('''
            SELECT COUNT(*) as total FROM (
                SELECT pbr.player_id
                FROM player_bar_rankings pbr
                JOIN bars b ON pbr.bar_id = b.id
                WHERE UPPER(b.state) = UPPER(?)
                GROUP BY pbr.player_id
                HAVING SUM(pbr.games_played) >= ?
            )
        ''', (state, MIN_GAMES_BY_SCOPE['state']))
        total = cursor.fetchone()['total']
        
        result['rankings']['states'].append({
            'state': state.upper(),
            'rank': rank,
            'total_players': total,
            'wins': player_wins,
            'games': player_games
        })
    
    # Global ranking
    total_games = (player_row['wins'] or 0) + (player_row['losses'] or 0)
    if total_games >= MIN_GAMES_BY_SCOPE['global']:
        cursor.execute('''
            SELECT COUNT(*) + 1 as rank
            FROM players
            WHERE wins > ?
              AND (wins + losses) >= ?
              AND (is_active = 1 OR is_active IS NULL)
        ''', (player_row['wins'] or 0, MIN_GAMES_BY_SCOPE['global']))
        rank = cursor.fetchone()['rank']
        
        cursor.execute('''
            SELECT COUNT(*) as total
            FROM players
            WHERE (wins + losses) >= ?
              AND (is_active = 1 OR is_active IS NULL)
        ''', (MIN_GAMES_BY_SCOPE['global'],))
        total = cursor.fetchone()['total']
        
        result['rankings']['global'] = {
            'rank': rank,
            'total_players': total,
            'wins': player_row['wins'] or 0,
            'losses': player_row['losses'] or 0,
            'games': total_games
        }
    
    conn.close()
    return result


def get_available_scopes_for_bar(bar_id):
    """
    Get available ranking scopes for a specific bar.
    Returns scope options based on the bar's location.
    
    Args:
        bar_id: The bar's ID
    
    Returns:
        List of available scope dicts with name and params
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT name, city, state, borough, neighborhood, zip_code
        FROM bars WHERE id = ?
    ''', (bar_id,))
    bar = cursor.fetchone()
    conn.close()
    
    if not bar:
        return [{'scope': 'global', 'label': 'Global', 'params': {}}]
    
    scopes = []
    
    # Bar scope
    scopes.append({
        'scope': 'bar',
        'label': f"This Bar ({bar['name']})",
        'params': {'bar_id': bar_id}
    })
    
    # Borough scope (NYC only)
    boro = normalize_borough(bar['borough'])
    if boro:
        scopes.append({
            'scope': 'borough',
            'label': f"{boro}",
            'params': {'borough': boro}
        })
    
    # City scope
    if bar['city'] and bar['state']:
        scopes.append({
            'scope': 'city',
            'label': f"{bar['city']}, {bar['state']}",
            'params': {'city': bar['city'], 'state': bar['state']}
        })
    
    # State scope
    if bar['state']:
        scopes.append({
            'scope': 'state',
            'label': bar['state'].upper(),
            'params': {'state': bar['state']}
        })
    
    # Global scope
    scopes.append({
        'scope': 'global',
        'label': 'Global',
        'params': {}
    })
    
    return scopes


def get_leaderboard(scope, params=None, limit=50, metric='wins'):
    """
    Unified leaderboard function - routes to appropriate scope handler.
    
    Args:
        scope: One of 'bar', 'borough', 'city', 'state', 'global'
        params: Dict with scope-specific parameters
        limit: Maximum players to return
        metric: 'wins', 'rating', 'winrate', or 'games'
    
    Returns:
        List of player dicts for the specified scope
    """
    params = params or {}
    
    if scope == 'bar':
        bar_id = params.get('bar_id')
        if not bar_id:
            return []
        return get_leaderboard_for_bar(bar_id, limit, metric)
    
    elif scope == 'borough':
        borough = params.get('borough')
        if not borough:
            return []
        return get_leaderboard_for_borough(borough, limit, metric)
    
    elif scope == 'city':
        city = params.get('city')
        state = params.get('state')
        if not city or not state:
            return []
        return get_leaderboard_for_city(city, state, limit, metric)
    
    elif scope == 'state':
        state = params.get('state')
        if not state:
            return []
        return get_leaderboard_for_state(state, limit, metric)
    
    else:  # global
        return get_leaderboard_global(limit, metric)
