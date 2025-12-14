"""
Token Service - Manage player token balances
"""
from ..database import get_db

def get_balance(user_id):
    """Get user's current token balance."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT tokens FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

def earn_tokens(user_id, amount, source_type, metadata=None):
    """Add tokens to user's balance."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Update balance
    cursor.execute('UPDATE users SET tokens = COALESCE(tokens, 0) + ? WHERE id = ?', 
                   (amount, user_id))
    
    # Get new balance
    cursor.execute('SELECT tokens FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    new_balance = row[0] if row else amount
    
    conn.commit()
    conn.close()
    return new_balance

def spend_tokens(user_id, amount, item_type, metadata=None):
    """Deduct tokens from user's balance."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Check balance
    cursor.execute('SELECT tokens FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    if not row or row[0] < amount:
        conn.close()
        return {'success': False, 'error': 'Insufficient tokens'}
    
    # Update balance
    cursor.execute('UPDATE users SET tokens = tokens - ? WHERE id = ?', (amount, user_id))
    new_balance = row[0] - amount
    
    conn.commit()
    conn.close()
    return {'success': True, 'new_balance': new_balance}
