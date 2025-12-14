"""
Unified Login Routes for RBAC
Add this to routes_auth.py or create as new blueprint
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash, generate_password_hash
from .database import get_db
from .rbac import get_user_roles, get_user_venues, get_highest_role

unified_auth_bp = Blueprint('unified_auth', __name__, url_prefix='/auth')


@unified_auth_bp.route('/login', methods=['GET', 'POST'])
def unified_login():
    """Single login for all user types."""
    
    # If already logged in with new system, redirect
    if 'user_id' in session:
        return redirect(url_for('unified_auth.portal'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        if not email or not password:
            return render_template('auth/unified_login.html', error='Email and password required')
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE email = ? AND is_active = 1', (email,))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            return render_template('auth/unified_login.html', error='Invalid email or password')
        
        user = dict(user)
        
        if not check_password_hash(user['password_hash'], password):
            return render_template('auth/unified_login.html', error='Invalid email or password')
        
        # Login successful - set session
        session['user_id'] = user['id']
        session['user_email'] = user['email']
        session['user_name'] = user['name']
        session['is_superadmin'] = user['is_superadmin']
        session.permanent = True
        
        # Also set player_id if this user has a linked player profile
        cursor = get_db().cursor()
        cursor.execute('SELECT id, nickname FROM players WHERE user_id = ?', (user['id'],))
        player = cursor.fetchone()
        if player:
            session['player_id'] = player['id']
            session['player_nickname'] = player['nickname']
        
        # Redirect to portal to choose venue/role
        return redirect(url_for('unified_auth.portal'))
    
    return render_template('auth/unified_login.html')


@unified_auth_bp.route('/portal')
def portal():
    """
    After login, show user their available venues and roles.
    They can choose which venue to manage or go to player app.
    """
    if 'user_id' not in session:
        return redirect(url_for('unified_auth.unified_login'))
    
    user_id = session['user_id']
    venues = get_user_venues(user_id)
    roles = get_user_roles(user_id)
    
    # Check if user is a player
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM players WHERE user_id = ?', (user_id,))
    player = cursor.fetchone()
    is_player = player is not None
    
    # Check if superadmin
    cursor.execute('SELECT is_superadmin FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    is_superadmin = user and user['is_superadmin']
    conn.close()
    
    return render_template('auth/portal.html',
                           venues=venues,
                           roles=roles,
                           is_player=is_player,
                           is_superadmin=is_superadmin)


@unified_auth_bp.route('/select-venue/<int:venue_id>')
def select_venue(venue_id):
    """Select a venue to manage."""
    if 'user_id' not in session:
        return redirect(url_for('unified_auth.unified_login'))
    
    # Verify user has access to this venue
    venues = get_user_venues(session['user_id'])
    venue_ids = [v['id'] for v in venues]
    
    if venue_id not in venue_ids:
        flash('You do not have access to that venue', 'error')
        return redirect(url_for('unified_auth.portal'))
    
    # Set current venue in session
    session['current_venue_id'] = venue_id
    venue = next(v for v in venues if v['id'] == venue_id)
    session['current_venue_name'] = venue['name']
    session['current_venue_role'] = venue['role_name']
    
    # Redirect based on role
    if venue['role_name'] in ['owner', 'manager']:
        return redirect(url_for('bar_manager.dashboard'))
    elif venue['role_name'] == 'staff':
        return redirect(url_for('board.view'))
    elif venue['role_name'] == 'analyst':
        return redirect(url_for('bar_manager.analytics'))
    
    return redirect(url_for('bar_manager.dashboard'))


@unified_auth_bp.route('/logout')
def logout():
    """Logout and clear session."""
    session.clear()
    flash('You have been logged out', 'success')
    return redirect(url_for('unified_auth.unified_login'))
