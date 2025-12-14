"""
Location Service - Hierarchical Location Model for Pool Cue
============================================================

Provides a clean, scalable location system:
- Country → State → City/Town → Borough (NYC only) → ZIP/Neighborhood

NYC is specially handled with exactly 5 boroughs:
- Manhattan, Brooklyn, Queens, The Bronx, Staten Island

For non-NYC locations, uses state + city + zip_code as primary breakdown.
"""

from ..database import get_db

# ============================================================
# CANONICAL NYC BOROUGHS (Single Source of Truth)
# ============================================================
NYC_BOROUGHS = (
    'Manhattan',
    'Brooklyn', 
    'Queens',
    'The Bronx',
    'Staten Island'
)

# Borough normalization map - handles various input formats
BOROUGH_NORMALIZE = {
    # Lowercase variants
    'manhattan': 'Manhattan',
    'brooklyn': 'Brooklyn',
    'queens': 'Queens',
    'bronx': 'The Bronx',
    'the bronx': 'The Bronx',
    'the_bronx': 'The Bronx',
    'staten island': 'Staten Island',
    'staten_island': 'Staten Island',
    'si': 'Staten Island',
    # Title case variants
    'Manhattan': 'Manhattan',
    'Brooklyn': 'Brooklyn',
    'Queens': 'Queens',
    'Bronx': 'The Bronx',
    'The Bronx': 'The Bronx',
    'Staten Island': 'Staten Island',
    # Uppercase
    'MANHATTAN': 'Manhattan',
    'BROOKLYN': 'Brooklyn',
    'QUEENS': 'Queens',
    'BRONX': 'The Bronx',
    'THE BRONX': 'The Bronx',
    'STATEN ISLAND': 'Staten Island',
}

# NYC ZIP code to borough mapping (partial, can be extended)
NYC_ZIP_TO_BOROUGH = {
    # Manhattan (100xx-102xx)
    '10001': 'Manhattan', '10002': 'Manhattan', '10003': 'Manhattan',
    '10004': 'Manhattan', '10005': 'Manhattan', '10006': 'Manhattan',
    '10007': 'Manhattan', '10008': 'Manhattan', '10009': 'Manhattan',
    '10010': 'Manhattan', '10011': 'Manhattan', '10012': 'Manhattan',
    '10013': 'Manhattan', '10014': 'Manhattan', '10016': 'Manhattan',
    '10017': 'Manhattan', '10018': 'Manhattan', '10019': 'Manhattan',
    '10020': 'Manhattan', '10021': 'Manhattan', '10022': 'Manhattan',
    '10023': 'Manhattan', '10024': 'Manhattan', '10025': 'Manhattan',
    '10026': 'Manhattan', '10027': 'Manhattan', '10028': 'Manhattan',
    '10029': 'Manhattan', '10030': 'Manhattan', '10031': 'Manhattan',
    '10032': 'Manhattan', '10033': 'Manhattan', '10034': 'Manhattan',
    '10035': 'Manhattan', '10036': 'Manhattan', '10037': 'Manhattan',
    '10038': 'Manhattan', '10039': 'Manhattan', '10040': 'Manhattan',
    # Brooklyn (112xx)
    '11201': 'Brooklyn', '11203': 'Brooklyn', '11204': 'Brooklyn',
    '11205': 'Brooklyn', '11206': 'Brooklyn', '11207': 'Brooklyn',
    '11208': 'Brooklyn', '11209': 'Brooklyn', '11210': 'Brooklyn',
    '11211': 'Brooklyn', '11212': 'Brooklyn', '11213': 'Brooklyn',
    '11214': 'Brooklyn', '11215': 'Brooklyn', '11216': 'Brooklyn',
    '11217': 'Brooklyn', '11218': 'Brooklyn', '11219': 'Brooklyn',
    '11220': 'Brooklyn', '11221': 'Brooklyn', '11222': 'Brooklyn',
    '11223': 'Brooklyn', '11224': 'Brooklyn', '11225': 'Brooklyn',
    '11226': 'Brooklyn', '11228': 'Brooklyn', '11229': 'Brooklyn',
    '11230': 'Brooklyn', '11231': 'Brooklyn', '11232': 'Brooklyn',
    '11233': 'Brooklyn', '11234': 'Brooklyn', '11235': 'Brooklyn',
    '11236': 'Brooklyn', '11237': 'Brooklyn', '11238': 'Brooklyn',
    '11239': 'Brooklyn',
    # Queens (11xxx except 112xx)
    '11101': 'Queens', '11102': 'Queens', '11103': 'Queens',
    '11104': 'Queens', '11105': 'Queens', '11106': 'Queens',
    '11354': 'Queens', '11355': 'Queens', '11356': 'Queens',
    '11357': 'Queens', '11358': 'Queens', '11359': 'Queens',
    '11360': 'Queens', '11361': 'Queens', '11362': 'Queens',
    '11363': 'Queens', '11364': 'Queens', '11365': 'Queens',
    '11366': 'Queens', '11367': 'Queens', '11368': 'Queens',
    '11369': 'Queens', '11370': 'Queens', '11371': 'Queens',
    '11372': 'Queens', '11373': 'Queens', '11374': 'Queens',
    '11375': 'Queens', '11377': 'Queens', '11378': 'Queens',
    '11379': 'Queens', '11385': 'Queens', '11411': 'Queens',
    '11412': 'Queens', '11413': 'Queens', '11414': 'Queens',
    '11415': 'Queens', '11416': 'Queens', '11417': 'Queens',
    '11418': 'Queens', '11419': 'Queens', '11420': 'Queens',
    '11421': 'Queens', '11422': 'Queens', '11423': 'Queens',
    '11426': 'Queens', '11427': 'Queens', '11428': 'Queens',
    '11429': 'Queens', '11430': 'Queens', '11432': 'Queens',
    '11433': 'Queens', '11434': 'Queens', '11435': 'Queens',
    '11436': 'Queens', '11691': 'Queens', '11692': 'Queens',
    '11693': 'Queens', '11694': 'Queens', '11697': 'Queens',
    # The Bronx (104xx)
    '10451': 'The Bronx', '10452': 'The Bronx', '10453': 'The Bronx',
    '10454': 'The Bronx', '10455': 'The Bronx', '10456': 'The Bronx',
    '10457': 'The Bronx', '10458': 'The Bronx', '10459': 'The Bronx',
    '10460': 'The Bronx', '10461': 'The Bronx', '10462': 'The Bronx',
    '10463': 'The Bronx', '10464': 'The Bronx', '10465': 'The Bronx',
    '10466': 'The Bronx', '10467': 'The Bronx', '10468': 'The Bronx',
    '10469': 'The Bronx', '10470': 'The Bronx', '10471': 'The Bronx',
    '10472': 'The Bronx', '10473': 'The Bronx', '10474': 'The Bronx',
    '10475': 'The Bronx',
    # Staten Island (103xx)
    '10301': 'Staten Island', '10302': 'Staten Island', '10303': 'Staten Island',
    '10304': 'Staten Island', '10305': 'Staten Island', '10306': 'Staten Island',
    '10307': 'Staten Island', '10308': 'Staten Island', '10309': 'Staten Island',
    '10310': 'Staten Island', '10311': 'Staten Island', '10312': 'Staten Island',
    '10314': 'Staten Island',
}


def normalize_borough(borough_input):
    """
    Normalize borough name to canonical form.
    Returns None if not a valid NYC borough.
    
    Examples:
        normalize_borough('brooklyn') -> 'Brooklyn'
        normalize_borough('The Bronx') -> 'The Bronx'
        normalize_borough('bronx') -> 'The Bronx'
        normalize_borough('Chicago') -> None
    """
    if not borough_input:
        return None
    
    # Clean input
    cleaned = str(borough_input).strip()
    
    # Try direct lookup (case-insensitive)
    lookup_key = cleaned.lower().replace('_', ' ')
    if lookup_key in BOROUGH_NORMALIZE:
        return BOROUGH_NORMALIZE[lookup_key]
    
    # Try original input
    if cleaned in BOROUGH_NORMALIZE:
        return BOROUGH_NORMALIZE[cleaned]
    
    return None  # Not a valid NYC borough


def get_borough_from_zip(zip_code):
    """
    Determine NYC borough from ZIP code.
    Returns None if ZIP is not in NYC.
    """
    if not zip_code:
        return None
    zip_str = str(zip_code).strip()[:5]  # First 5 digits only
    return NYC_ZIP_TO_BOROUGH.get(zip_str)


def is_nyc_location(state=None, city=None, zip_code=None):
    """
    Check if a location is in NYC.
    Returns True if state is NY and city contains 'New York' or ZIP is NYC.
    """
    # Check by ZIP code first (most reliable)
    if zip_code and get_borough_from_zip(zip_code):
        return True
    
    # Check by state and city
    if state and city:
        state_upper = str(state).strip().upper()
        city_lower = str(city).strip().lower()
        if state_upper in ('NY', 'NEW YORK'):
            if 'new york' in city_lower or city_lower in ('nyc', 'manhattan', 'brooklyn', 'queens', 'bronx', 'staten island'):
                return True
    
    return False


def auto_populate_borough(zip_code=None, city=None, state=None):
    """
    Auto-determine borough based on ZIP code or city name.
    Returns canonical borough name or None.
    """
    # Try ZIP code first
    if zip_code:
        borough = get_borough_from_zip(zip_code)
        if borough:
            return borough
    
    # Try city name (might be borough name)
    if city:
        borough = normalize_borough(city)
        if borough:
            return borough
    
    return None


# ============================================================
# GEO ANALYTICS QUERIES
# ============================================================

def get_location_analytics(start_date=None, end_date=None, bar_id=None):
    """
    Compute comprehensive location analytics.
    
    Returns dict with:
    - nyc_boroughs: {borough: {bars, players, games}} for exactly 5 boroughs
    - states: [{state, bars, players, games}]
    - cities: [{city, state, bars, players}]
    - zip_codes: [{zip, neighborhood, borough, bars, players}]
    - summary: {total_states, total_cities, nyc_bar_count, non_nyc_bar_count}
    """
    conn = get_db()
    cursor = conn.cursor()
    
    result = {
        'nyc_boroughs': {boro: {'bars': 0, 'players': 0, 'games': 0} for boro in NYC_BOROUGHS},
        'active_boroughs': 0,
        'total_nyc_players': 0,
        'states': [],
        'cities': [],
        'zip_codes': [],
        'summary': {
            'total_states': 0,
            'total_cities': 0,
            'nyc_bar_count': 0,
            'non_nyc_bar_count': 0
        }
    }
    
    try:
        # Build date filter
        date_filter = ""
        date_params = []
        if start_date and end_date:
            date_filter = "AND gh.played_at BETWEEN ? AND ?"
            date_params = [start_date, end_date]
        
        bar_filter = ""
        bar_params = []
        if bar_id:
            bar_filter = "AND b.id = ?"
            bar_params = [bar_id]
        
        # NYC Borough stats
        cursor.execute(f'''
            SELECT 
                b.borough,
                COUNT(DISTINCT b.id) as bar_count,
                COUNT(DISTINCT p.id) as player_count,
                (SELECT COUNT(*) FROM game_history gh 
                 WHERE gh.bar_id = b.id {date_filter}) as game_count
            FROM bars b
            LEFT JOIN players p ON p.home_bar_id = b.id 
                AND (p.is_active = 1 OR p.is_active IS NULL)
            WHERE b.is_active = 1 
              AND b.borough IS NOT NULL AND b.borough != ''
              {bar_filter}
            GROUP BY b.borough
        ''', date_params + bar_params)
        
        active_boroughs = set()
        total_nyc_players = 0
        for row in cursor.fetchall():
            boro = normalize_borough(row[0])
            if boro and boro in result['nyc_boroughs']:
                result['nyc_boroughs'][boro]['bars'] = row[1] or 0
                result['nyc_boroughs'][boro]['players'] = row[2] or 0
                result['nyc_boroughs'][boro]['games'] = row[3] or 0
                if row[1] > 0 or row[2] > 0:
                    active_boroughs.add(boro)
                total_nyc_players += row[2] or 0
        
        result['active_boroughs'] = len(active_boroughs)
        result['total_nyc_players'] = total_nyc_players
        
        # Count bars by NYC vs non-NYC
        cursor.execute('''
            SELECT 
                CASE WHEN borough IS NOT NULL AND borough != '' THEN 'nyc' ELSE 'non_nyc' END as loc_type,
                COUNT(*) as cnt
            FROM bars
            WHERE is_active = 1
            GROUP BY loc_type
        ''')
        for row in cursor.fetchall():
            if row[0] == 'nyc':
                result['summary']['nyc_bar_count'] = row[1]
            else:
                result['summary']['non_nyc_bar_count'] = row[1]
        
        # State stats
        cursor.execute(f'''
            SELECT 
                b.state,
                COUNT(DISTINCT b.id) as bar_count,
                COUNT(DISTINCT p.id) as player_count,
                (SELECT COUNT(*) FROM game_history gh 
                 WHERE gh.bar_id IN (SELECT id FROM bars WHERE state = b.state)
                 {date_filter}) as game_count
            FROM bars b
            LEFT JOIN players p ON p.home_bar_id = b.id 
                AND (p.is_active = 1 OR p.is_active IS NULL)
            WHERE b.is_active = 1 
              AND b.state IS NOT NULL AND b.state != ''
              {bar_filter}
            GROUP BY b.state
            ORDER BY bar_count DESC
        ''', date_params + bar_params)
        
        result['states'] = [{
            'state': row[0],
            'bars': row[1] or 0,
            'players': row[2] or 0,
            'games': row[3] or 0
        } for row in cursor.fetchall()]
        result['summary']['total_states'] = len(result['states'])
        
        # City stats
        cursor.execute(f'''
            SELECT 
                b.city,
                b.state,
                COUNT(DISTINCT b.id) as bar_count,
                COUNT(DISTINCT p.id) as player_count
            FROM bars b
            LEFT JOIN players p ON p.home_bar_id = b.id 
                AND (p.is_active = 1 OR p.is_active IS NULL)
            WHERE b.is_active = 1 
              AND b.city IS NOT NULL AND b.city != ''
              {bar_filter}
            GROUP BY b.city, b.state
            ORDER BY bar_count DESC
            LIMIT 20
        ''', bar_params)
        
        cities_seen = set()
        for row in cursor.fetchall():
            city_key = f"{row[0]}, {row[1]}"
            if city_key not in cities_seen:
                cities_seen.add(city_key)
                result['cities'].append({
                    'city': row[0],
                    'state': row[1],
                    'bars': row[2] or 0,
                    'players': row[3] or 0
                })
        result['summary']['total_cities'] = len(cities_seen)
        
        # ZIP code stats
        cursor.execute(f'''
            SELECT 
                b.zip_code,
                b.neighborhood,
                b.borough,
                COUNT(DISTINCT b.id) as bar_count,
                COUNT(DISTINCT p.id) as player_count
            FROM bars b
            LEFT JOIN players p ON p.home_bar_id = b.id 
                AND (p.is_active = 1 OR p.is_active IS NULL)
            WHERE b.is_active = 1 
              AND b.zip_code IS NOT NULL AND b.zip_code != ''
              {bar_filter}
            GROUP BY b.zip_code
            ORDER BY bar_count DESC
            LIMIT 20
        ''', bar_params)
        
        result['zip_codes'] = [{
            'zip': row[0],
            'neighborhood': row[1] or '',
            'borough': normalize_borough(row[2]) or '',
            'bars': row[3] or 0,
            'players': row[4] or 0
        } for row in cursor.fetchall()]
        
    except Exception as e:
        print(f"[LOCATION_SERVICE] Analytics error: {e}")
    finally:
        conn.close()
    
    return result


def get_bar_location_summary(bar_id):
    """
    Get location summary for a specific bar.
    Returns dict with city, state, borough, neighborhood, zip, is_nyc.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT city, state, borough, neighborhood, zip_code
        FROM bars WHERE id = ?
    ''', (bar_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    return {
        'city': row[0],
        'state': row[1],
        'borough': normalize_borough(row[2]),
        'neighborhood': row[3],
        'zip': row[4],
        'is_nyc': is_nyc_location(row[1], row[0], row[4])
    }


# ============================================================
# DATABASE SETUP
# ============================================================

def ensure_locations_table():
    """
    Create the locations reference table if it doesn't exist.
    This table provides canonical location data for data integrity.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            country TEXT DEFAULT 'USA',
            state TEXT NOT NULL,
            city TEXT NOT NULL,
            borough TEXT,  -- Only for NYC, one of the 5 canonical boroughs
            zip_code TEXT,
            neighborhood TEXT,
            lat REAL,
            lng REAL,
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(state, city, borough, zip_code)
        )
    ''')
    
    # Seed NYC boroughs
    for boro in NYC_BOROUGHS:
        cursor.execute('''
            INSERT OR IGNORE INTO locations (country, state, city, borough)
            VALUES ('USA', 'NY', 'New York', ?)
        ''', (boro,))
    
    conn.commit()
    conn.close()
    
    return True
