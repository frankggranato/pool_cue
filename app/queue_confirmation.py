"""
Queue Confirmation SMS System

Handles SMS notifications for players reaching position #3 in queue.
- Sends confirmation request when player reaches #3 (queue must have 4+ people)
- Processes Y/N replies via Twilio webhook
- Bumps unconfirmed players after timeout
- Removes players who don't confirm after being bumped
"""
import logging
from datetime import datetime, timedelta
from .database import get_db

logger = logging.getLogger(__name__)

# Configuration
CONFIRM_TIMEOUT_MINUTES = 5  # Time to confirm at position #3
BUMP_TIMEOUT_MINUTES = 5     # Time before removal after being bumped to #4
MIN_QUEUE_SIZE = 4           # Minimum queue size to require confirmation


def get_players_needing_sms(bar_id=None):
    """
    Find players at position #3 who need confirmation SMS.
    
    Criteria:
    - Position = 3
    - Queue has 4+ players
    - SMS not yet sent (sms_sent = 0)
    - Has a phone number
    
    Returns list of dicts with player info and bar details.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        bar_filter = "AND q.bar_id = ?" if bar_id else ""
        params = (bar_id,) if bar_id else ()
        
        cursor.execute(f'''
            SELECT 
                q.id as queue_id,
                q.player_id,
                q.bar_id,
                q.position,
                p.phone_number,
                p.nickname,
                p.display_name,
                b.name as bar_name,
                (SELECT COUNT(*) FROM queue WHERE bar_id = q.bar_id AND status = 'waiting') as queue_size
            FROM queue q
            JOIN players p ON q.player_id = p.id
            JOIN bars b ON q.bar_id = b.id
            WHERE q.position = 3
              AND q.status = 'waiting'
              AND q.sms_sent = 0
              AND q.confirmed = 0
              AND p.phone_number IS NOT NULL
              AND p.phone_number != ''
              {bar_filter}
        ''', params)
        
        results = []
        for row in cursor.fetchall():
            if row['queue_size'] >= MIN_QUEUE_SIZE:
                results.append(dict(row))
        
        return results
    finally:
        conn.close()


def send_confirmation_sms(queue_id):
    """
    Send confirmation SMS to player at position #3.
    
    Returns dict with success status and message.
    """
    from .services.sms_service import send_sms
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Get player and bar info
        cursor.execute('''
            SELECT 
                q.id, q.player_id, q.bar_id,
                p.phone_number, p.nickname, p.display_name,
                b.name as bar_name
            FROM queue q
            JOIN players p ON q.player_id = p.id
            JOIN bars b ON q.bar_id = b.id
            WHERE q.id = ?
        ''', (queue_id,))
        
        entry = cursor.fetchone()
        if not entry:
            return {'success': False, 'error': 'Queue entry not found'}
        
        if not entry['phone_number']:
            return {'success': False, 'error': 'No phone number'}
        
        # Build message
        player_name = entry['display_name'] or entry['nickname'] or 'Player'
        bar_name = entry['bar_name']
        message = f"You're up next at {bar_name}! Reply Y to confirm 🎱"
        
        # Send SMS
        result = send_sms(entry['phone_number'], message)
        
        if result.get('success'):
            # Mark SMS as sent
            cursor.execute('''
                UPDATE queue 
                SET sms_sent = 1, 
                    needs_confirmation = 1,
                    confirmation_requested_at = datetime('now')
                WHERE id = ?
            ''', (queue_id,))
            conn.commit()
            
            logger.info(f"Confirmation SMS sent to {player_name} for {bar_name}")
            return {'success': True, 'message': 'SMS sent'}
        else:
            logger.error(f"Failed to send SMS: {result.get('error')}")
            return result
            
    except Exception as e:
        logger.error(f"Error sending confirmation SMS: {e}")
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()


def process_sms_reply(from_number, body):
    """
    Process incoming SMS reply (Y/N).
    
    Args:
        from_number: Phone number that sent the reply (E.164 format)
        body: Message body
    
    Returns dict with action taken.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Normalize phone number for lookup
        digits = ''.join(c for c in from_number if c.isdigit())
        if len(digits) == 11 and digits[0] == '1':
            digits = digits[1:]  # Remove country code for matching
        
        # Find player with this phone number who has pending confirmation
        cursor.execute('''
            SELECT q.id as queue_id, q.player_id, q.bar_id, q.position,
                   p.nickname, p.display_name, b.name as bar_name
            FROM queue q
            JOIN players p ON q.player_id = p.id
            JOIN bars b ON q.bar_id = b.id
            WHERE (p.phone_number LIKE ? OR p.phone_number LIKE ?)
              AND q.sms_sent = 1
              AND q.confirmed = 0
              AND q.status = 'waiting'
            ORDER BY q.confirmation_requested_at DESC
            LIMIT 1
        ''', (f'%{digits}', f'%{digits[-10:]}'))
        
        entry = cursor.fetchone()
        
        if not entry:
            logger.warning(f"SMS reply from {from_number} - no pending confirmation found")
            return {'success': False, 'error': 'No pending confirmation'}
        
        body_upper = body.strip().upper()
        player_name = entry['display_name'] or entry['nickname']
        
        if body_upper in ['Y', 'YES', 'YEA', 'YEAH', 'YUP', 'YEP']:
            # Confirm the player
            cursor.execute('''
                UPDATE queue 
                SET confirmed = 1, needs_confirmation = 0
                WHERE id = ?
            ''', (entry['queue_id'],))
            conn.commit()
            
            logger.info(f"{player_name} confirmed at {entry['bar_name']}")
            return {
                'success': True, 
                'action': 'confirmed',
                'message': f"You're confirmed at {entry['bar_name']}! Get ready 🎱"
            }
            
        elif body_upper in ['N', 'NO', 'NAH', 'NOPE']:
            # Remove from queue
            cursor.execute('DELETE FROM queue WHERE id = ?', (entry['queue_id'],))
            
            # Reorder remaining queue
            cursor.execute('''
                UPDATE queue 
                SET position = position - 1 
                WHERE bar_id = ? AND position > ?
            ''', (entry['bar_id'], entry['position']))
            conn.commit()
            
            logger.info(f"{player_name} declined, removed from queue at {entry['bar_name']}")
            return {
                'success': True,
                'action': 'removed',
                'message': "Got it! You've been removed from the queue."
            }
        else:
            return {
                'success': False,
                'action': 'unknown',
                'message': "Reply Y to confirm or N to leave the queue."
            }
            
    except Exception as e:
        logger.error(f"Error processing SMS reply: {e}")
        return {'success': False, 'error': str(e)}
    finally:
        conn.close()


def check_confirmation_timeouts():
    """
    Check for players who haven't confirmed in time.
    
    - Position #3, no confirm in 5 min → bump to #4
    - Position #4 (already bumped), no confirm in 5 min → remove
    
    Returns dict with counts of actions taken.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    bumped = 0
    removed = 0
    
    try:
        now = datetime.now()
        confirm_cutoff = now - timedelta(minutes=CONFIRM_TIMEOUT_MINUTES)
        bump_cutoff = now - timedelta(minutes=BUMP_TIMEOUT_MINUTES)
        
        # Find players at #3 who need to be bumped
        cursor.execute('''
            SELECT q.id, q.bar_id, q.position, q.player_id,
                   p.nickname, p.display_name
            FROM queue q
            JOIN players p ON q.player_id = p.id
            WHERE q.position = 3
              AND q.sms_sent = 1
              AND q.confirmed = 0
              AND q.pushed_down_at IS NULL
              AND q.confirmation_requested_at <= ?
              AND q.status = 'waiting'
        ''', (confirm_cutoff.strftime('%Y-%m-%d %H:%M:%S'),))
        
        to_bump = cursor.fetchall()
        
        for entry in to_bump:
            # Swap position 3 and 4
            cursor.execute('''
                UPDATE queue SET position = 3 
                WHERE bar_id = ? AND position = 4 AND status = 'waiting'
            ''', (entry['bar_id'],))
            
            cursor.execute('''
                UPDATE queue 
                SET position = 4, 
                    pushed_down_at = datetime('now'),
                    push_count = push_count + 1
                WHERE id = ?
            ''', (entry['id'],))
            
            bumped += 1
            player_name = entry['display_name'] or entry['nickname']
            logger.info(f"Bumped {player_name} to #4 (no confirmation)")
        
        # Find players at #4 who were bumped and need removal
        cursor.execute('''
            SELECT q.id, q.bar_id, q.position, q.player_id,
                   p.nickname, p.display_name
            FROM queue q
            JOIN players p ON q.player_id = p.id
            WHERE q.position = 4
              AND q.sms_sent = 1
              AND q.confirmed = 0
              AND q.pushed_down_at IS NOT NULL
              AND q.pushed_down_at <= ?
              AND q.status = 'waiting'
        ''', (bump_cutoff.strftime('%Y-%m-%d %H:%M:%S'),))
        
        to_remove = cursor.fetchall()
        
        for entry in to_remove:
            cursor.execute('DELETE FROM queue WHERE id = ?', (entry['id'],))
            
            # Reorder queue
            cursor.execute('''
                UPDATE queue 
                SET position = position - 1 
                WHERE bar_id = ? AND position > 4
            ''', (entry['bar_id'],))
            
            removed += 1
            player_name = entry['display_name'] or entry['nickname']
            logger.info(f"Removed {player_name} from queue (no confirmation after bump)")
        
        if bumped or removed:
            conn.commit()
        
        return {'bumped': bumped, 'removed': removed}
        
    except Exception as e:
        logger.error(f"Error checking confirmation timeouts: {e}")
        conn.rollback()
        return {'error': str(e)}
    finally:
        conn.close()


def confirm_player_by_board(queue_id):
    """
    Confirm a player via board interaction (QR tap, position check).
    
    Returns success status.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE queue 
            SET confirmed = 1, needs_confirmation = 0
            WHERE id = ? AND sms_sent = 1
        ''', (queue_id,))
        conn.commit()
        
        return cursor.rowcount > 0
    finally:
        conn.close()


def confirm_player_by_staff(queue_id):
    """
    Staff manually confirms a player is present.
    
    Returns success status.
    """
    return confirm_player_by_board(queue_id)  # Same logic


def run_confirmation_cycle():
    """
    Run a full confirmation check cycle.
    
    1. Find players needing SMS at position #3
    2. Send SMS to those players
    3. Check for timeouts and bump/remove as needed
    
    Call this every 30 seconds from a background task.
    """
    results = {
        'sms_sent': 0,
        'bumped': 0,
        'removed': 0,
        'errors': []
    }
    
    # Send SMS to new #3 players
    players_needing_sms = get_players_needing_sms()
    for player in players_needing_sms:
        result = send_confirmation_sms(player['queue_id'])
        if result.get('success'):
            results['sms_sent'] += 1
        else:
            results['errors'].append(result.get('error'))
    
    # Check timeouts
    timeout_results = check_confirmation_timeouts()
    results['bumped'] = timeout_results.get('bumped', 0)
    results['removed'] = timeout_results.get('removed', 0)
    
    if timeout_results.get('error'):
        results['errors'].append(timeout_results['error'])
    
    return results


# ============================================
# Legacy compatibility functions
# Used by routes_public.py
# ============================================

CONFIRM_TIMEOUT_SECONDS = CONFIRM_TIMEOUT_MINUTES * 60
REMOVAL_TIMEOUT_SECONDS = BUMP_TIMEOUT_MINUTES * 60


def confirm_ready(player_id=None, session_token=None):
    """
    Mark a player as confirmed/ready.
    Called when player interacts with their status page or clicks confirm button.
    Works for position 3 players regardless of SMS status.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        if session_token:
            # First try to update by session token - allow confirmation for any position 3 player
            cursor.execute('''
                UPDATE queue SET confirmed = 1, needs_confirmation = 0
                WHERE session_token = ?
            ''', (session_token,))
        elif player_id:
            cursor.execute('''
                UPDATE queue SET confirmed = 1, needs_confirmation = 0
                WHERE player_id = ?
            ''', (player_id,))
        
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def check_and_enforce_timeouts():
    """
    Check for confirmation timeouts and take action.
    Returns dict of actions taken.
    """
    return check_confirmation_timeouts()


def get_queue_with_confirmation_status(bar_id=None):
    """
    Get queue with confirmation status for each player.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        bar_filter = "AND q.bar_id = ?" if bar_id else ""
        params = (bar_id,) if bar_id else ()
        
        cursor.execute(f'''
            SELECT q.*, p.nickname, p.display_name,
                   CASE 
                       WHEN q.confirmed = 1 THEN 'confirmed'
                       WHEN q.sms_sent = 1 AND q.pushed_down_at IS NOT NULL THEN 'bumped'
                       WHEN q.sms_sent = 1 THEN 'pending'
                       ELSE 'waiting'
                   END as confirmation_status,
                   q.confirmation_requested_at,
                   q.pushed_down_at
            FROM queue q
            JOIN players p ON q.player_id = p.id
            WHERE q.status IN ('waiting', 'playing')
            {bar_filter}
            ORDER BY q.position ASC
        ''', params)
        
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def on_game_end(bar_id=None):
    """
    Called when a game ends to trigger confirmation for new positions.
    The background task handles this automatically, but this can force a check.
    """
    # Run a confirmation cycle to send SMS to new #3
    run_confirmation_cycle()


def request_confirmation(queue_id):
    """
    Request confirmation from a specific player.
    """
    return send_confirmation_sms(queue_id)
