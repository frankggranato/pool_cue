"""
Bar Manager Portal Routes

Provides bar owners/managers with access to manage their specific bar:
- Queue management
- Event scheduling  
- Player reports
- Basic analytics for their bar
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, flash
from .database import get_db
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import secrets

bar_manager_bp = Blueprint('bar_manager', __name__, url_prefix='/bar-manager')


def bar_manager_required(f):
    """Decorator to require bar manager login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('bar_manager_id'):
            return redirect(url_for('bar_manager.login'))
        return f(*args, **kwargs)
    return decorated_function


def get_manager_bar():
    """Get the bar associated with the logged-in manager."""
    manager_id = session.get('bar_manager_id')
    if not manager_id:
        return None
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT bm.*, b.name as bar_name, b.id as bar_id
        FROM bar_managers bm
        JOIN bars b ON bm.bar_id = b.id
        WHERE bm.id = ?
    ''', (manager_id,))
    result = cursor.fetchone()
    conn.close()
    return dict(result) if result else None


# ============================================================================
# AUTH ROUTES
# ============================================================================

@bar_manager_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Bar manager login page."""
    if session.get('bar_manager_id'):
        return redirect(url_for('bar_manager.dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT bm.*, b.name as bar_name 
            FROM bar_managers bm
            JOIN bars b ON bm.bar_id = b.id
            WHERE bm.email = ? AND bm.is_active = 1
        ''', (email,))
        manager = cursor.fetchone()
        
        if manager and check_password_hash(manager['password_hash'], password):
            # Update last login
            cursor.execute('UPDATE bar_managers SET last_login_at = datetime("now") WHERE id = ?', 
                          (manager['id'],))
            conn.commit()
            conn.close()
            
            session['bar_manager_id'] = manager['id']
            session['bar_manager_name'] = manager['name'] or email
            session['bar_manager_bar_id'] = manager['bar_id']
            session['bar_manager_bar_name'] = manager['bar_name']
            session.permanent = True  # Session lasts 30 days
            
            return redirect(url_for('bar_manager.dashboard'))
        
        conn.close()
        return render_template('bar_manager/login.html', error='Invalid email or password')
    
    return render_template('bar_manager/login.html')


@bar_manager_bp.route('/logout')
def logout():
    """Log out bar manager."""
    session.pop('bar_manager_id', None)
    session.pop('bar_manager_name', None)
    session.pop('bar_manager_bar_id', None)
    session.pop('bar_manager_bar_name', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('bar_manager.login'))


# ============================================================================
# DASHBOARD
# ============================================================================

@bar_manager_bp.route('/')
@bar_manager_required
def dashboard():
    """Bar manager dashboard - overview of their bar."""
    bar_id = session.get('bar_manager_bar_id')
    bar_name = session.get('bar_manager_bar_name')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get queue count
    cursor.execute('SELECT COUNT(*) FROM queue WHERE bar_id = ?', (bar_id,))
    queue_count = cursor.fetchone()[0]
    
    # Get today's games
    cursor.execute('''
        SELECT COUNT(*) FROM game_history 
        WHERE bar_id = ? AND date(played_at) = date('now')
    ''', (bar_id,))
    games_today = cursor.fetchone()[0]
    
    # Get pending reports
    cursor.execute('''
        SELECT COUNT(*) FROM player_reports 
        WHERE bar_id = ? AND status = 'pending'
    ''', (bar_id,))
    pending_reports = cursor.fetchone()[0]
    
    # Get queue
    cursor.execute('''
        SELECT q.*, p.nickname 
        FROM queue q
        JOIN players p ON q.player_id = p.id
        WHERE q.bar_id = ?
        ORDER BY q.id
    ''', (bar_id,))
    queue = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return render_template('bar_manager/dashboard.html',
                          bar_name=bar_name,
                          queue_count=queue_count,
                          games_today=games_today,
                          pending_reports=pending_reports,
                          queue=queue)


# ============================================================================
# QUEUE MANAGEMENT
# ============================================================================

@bar_manager_bp.route('/queue')
@bar_manager_required
def queue():
    """Manage the queue for this bar."""
    bar_id = session.get('bar_manager_bar_id')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT q.*, p.nickname, p.id as player_id
        FROM queue q
        JOIN players p ON q.player_id = p.id
        WHERE q.bar_id = ?
        ORDER BY q.id
    ''', (bar_id,))
    queue = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return render_template('bar_manager/queue.html', queue=queue)


@bar_manager_bp.route('/api/queue/remove/<int:queue_id>', methods=['POST'])
@bar_manager_required
def api_remove_from_queue(queue_id):
    """Remove a player from the queue."""
    bar_id = session.get('bar_manager_bar_id')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Verify this queue entry belongs to this bar
    cursor.execute('SELECT id FROM queue WHERE id = ? AND bar_id = ?', (queue_id, bar_id))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    
    cursor.execute('DELETE FROM queue WHERE id = ?', (queue_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})


# ============================================================================
# REPORTS
# ============================================================================

@bar_manager_bp.route('/reports')
@bar_manager_required
def reports():
    """View player reports for this bar."""
    bar_id = session.get('bar_manager_bar_id')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT pr.*, 
               p1.nickname as reported_name,
               p2.nickname as reporter_name
        FROM player_reports pr
        JOIN players p1 ON pr.reported_player_id = p1.id
        LEFT JOIN players p2 ON pr.reporter_player_id = p2.id
        WHERE pr.bar_id = ?
        ORDER BY pr.created_at DESC
        LIMIT 50
    ''', (bar_id,))
    reports = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return render_template('bar_manager/reports.html', reports=reports)
