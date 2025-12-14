"""
POS Sync Service.
Handles syncing check/order data from POS systems to Pool Cue.
"""

from datetime import datetime, timedelta
from ..database import get_db
from ..pos_connectors import get_connector


def get_bar_pos_credentials(bar_id):
    """
    Get POS credentials for a bar.
    
    Returns:
        dict with provider, access_token, refresh_token, location_id
        or None if not configured
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Get bar's POS provider and location
    cursor.execute('''
        SELECT pos_provider, pos_location_id, pos_integration_status
        FROM bars WHERE id = ?
    ''', (bar_id,))
    bar_row = cursor.fetchone()
    
    if not bar_row or not bar_row['pos_provider']:
        conn.close()
        return None
    
    provider = bar_row['pos_provider']
    location_id = bar_row['pos_location_id']
    status = bar_row['pos_integration_status']
    
    if status != 'active':
        conn.close()
        return None
    
    # Get credentials
    cursor.execute('''
        SELECT access_token, refresh_token
        FROM pos_credentials
        WHERE bar_id = ? AND provider = ?
        ORDER BY updated_at DESC
        LIMIT 1
    ''', (bar_id, provider))
    cred_row = cursor.fetchone()
    conn.close()
    
    if not cred_row:
        return None
    
    return {
        'provider': provider,
        'location_id': location_id,
        'access_token': cred_row['access_token'],
        'refresh_token': cred_row['refresh_token'],
    }


def sync_bar_pos(bar_id, start_date=None, end_date=None):
    """
    Sync POS data for a bar.
    
    Args:
        bar_id: int
        start_date: datetime (default: 7 days ago)
        end_date: datetime (default: now)
        
    Returns:
        dict with sync results
    """
    if end_date is None:
        end_date = datetime.now()
    if start_date is None:
        start_date = end_date - timedelta(days=7)
    
    # Get credentials
    credentials = get_bar_pos_credentials(bar_id)
    if not credentials:
        return {
            'success': False,
            'error': 'POS not configured or inactive',
            'checks_found': 0
        }
    
    # Get bar info
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM bars WHERE id = ?', (bar_id,))
    bar = dict(cursor.fetchone())
    conn.close()
    
    try:
        # Get connector and fetch checks
        connector = get_connector(credentials['provider'], credentials)
        checks = connector.fetch_checks(bar, start_date, end_date)
        
        print(f"[POS_SYNC] Bar {bar_id} ({credentials['provider']}): "
              f"Found {len(checks)} checks from {start_date} to {end_date}")
        
        # TODO: Store checks in database
        # For now, just return the count
        
        return {
            'success': True,
            'provider': credentials['provider'],
            'checks_found': len(checks),
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
        }
        
    except Exception as e:
        print(f"[POS_SYNC] Error syncing bar {bar_id}: {e}")
        return {
            'success': False,
            'error': str(e),
            'checks_found': 0
        }
