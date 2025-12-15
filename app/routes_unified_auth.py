"""
Unified Auth Routes - Email-based authentication
Replaces SMS verification with email verification
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
from .database import get_db
from .email_service import (
    send_verification_email, verify_email_token,
    send_password_reset_email, verify_reset_token, clear_reset_token,
    create_staff_invite, log_audit
)

unified_auth_bp = Blueprint('unified_auth', __name__, url_prefix='/auth')


# ============================================
# LOGIN
# ============================================

@unified_auth_bp.route('/login', methods=['GET', 'POST'])
def unified_login():
    """Single login for all user types - staff (users table) AND players (players table)."""
    if 'user_id' in session:
        return redirect(url_for('unified_auth.portal'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        if not email or not password:
            return render_template('auth/unified_login.html', error='Email and password required')
        
        conn = get_db()
        cursor = conn.cursor()
        
        # First check users table (staff/admin accounts)
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        
        if user:
            user = dict(user)
            
            # Check status
            if user.get('status') == 'suspended':
                conn.close()
                return render_template('auth/unified_login.html', error='Account suspended. Contact support.')
            
            if not check_password_hash(user['password_hash'], password):
                conn.close()
                return render_template('auth/unified_login.html', error='Invalid email or password')
            
            # Update last login
            cursor.execute('UPDATE users SET last_login = ? WHERE id = ?', (datetime.now().isoformat(), user['id']))
            conn.commit()
            
            # Set session for staff user
            session['user_id'] = user['id']
            session['user_email'] = user['email']
            session['user_name'] = user['name']
            session['is_superadmin'] = user.get('is_superadmin', 0)
            session['email_verified'] = user.get('email_verified', 0)
            session.permanent = True
            
            # Link to player profile if exists
            cursor.execute('SELECT id, nickname FROM players WHERE user_id = ?', (user['id'],))
            player = cursor.fetchone()
            if player:
                session['player_id'] = player['id']
                session['player_nickname'] = player['nickname']
            conn.close()
            
            # Log audit
            log_audit(user['id'], 'login', user['id'], None, {'method': 'password'}, request.remote_addr)
            
            return redirect(url_for('unified_auth.portal'))
        
        # If not in users table, check players table (player accounts)
        cursor.execute('SELECT id, nickname, email, password_hash, is_active FROM players WHERE email = ?', (email,))
        player = cursor.fetchone()
        
        if player:
            player = dict(player)
            
            if not player.get('is_active', True):
                conn.close()
                return render_template('auth/unified_login.html', error='Account deactivated. Contact support.')
            
            if not player.get('password_hash') or not check_password_hash(player['password_hash'], password):
                conn.close()
                return render_template('auth/unified_login.html', error='Invalid email or password')
            
            # Set session for player (no user_id, just player_id)
            session['player_id'] = player['id']
            session['player_nickname'] = player['nickname']
            session['player_email'] = player['email']
            session.permanent = True
            conn.close()
            
            # Redirect players to player home
            return redirect(url_for('player.home'))
        
        conn.close()
        return render_template('auth/unified_login.html', error='Invalid email or password')
    
    return render_template('auth/unified_login.html')


# ============================================
# SIGNUP (with email verification)
# ============================================

@unified_auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    """Create new account with email verification."""
    if 'user_id' in session:
        return redirect(url_for('unified_auth.portal'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        name = request.form.get('name', '').strip()
        
        errors = []
        if not email:
            errors.append('Email is required')
        if not password or len(password) < 6:
            errors.append('Password must be at least 6 characters')
        if not name:
            errors.append('Name is required')
        
        if errors:
            return render_template('auth/signup.html', error=', '.join(errors))
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Check if email exists
        cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
        if cursor.fetchone():
            conn.close()
            return render_template('auth/signup.html', error='Email already registered')
        
        # Create user (status=pending until email verified)
        password_hash = generate_password_hash(password, method='scrypt')
        cursor.execute('''
            INSERT INTO users (email, password_hash, name, status, email_verified)
            VALUES (?, ?, ?, 'pending', 0)
        ''', (email, password_hash, name))
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Send verification email
        success, error = send_verification_email(user_id, email)
        
        if success:
            log_audit(user_id, 'signup', user_id, None, {'email': email})
            return render_template('auth/verify_sent.html', email=email)
        else:
            return render_template('auth/signup.html', error=error or 'Failed to send verification email')
    
    return render_template('auth/signup.html')


@unified_auth_bp.route('/verify-email')
def verify_email():
    """Handle email verification link."""
    token = request.args.get('token')
    
    if not token:
        flash('Invalid verification link', 'error')
        return redirect(url_for('unified_auth.unified_login'))
    
    success, result = verify_email_token(token)
    
    if success:
        user_id = result
        # Activate the account
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET status = 'active' WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        
        log_audit(user_id, 'email_verified', user_id)
        flash('Email verified! You can now log in.', 'success')
    else:
        flash(result, 'error')
    
    return redirect(url_for('unified_auth.unified_login'))


@unified_auth_bp.route('/resend-verification', methods=['POST'])
def resend_verification():
    """Resend verification email."""
    email = request.form.get('email', '').strip().lower()
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE email = ? AND email_verified = 0', (email,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        send_verification_email(user['id'], email)
    
    # Always show success (don't reveal if email exists)
    flash('If that email exists, a new verification link has been sent.', 'success')
    return redirect(url_for('unified_auth.unified_login'))


# ============================================
# PASSWORD RESET
# ============================================

@unified_auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Request password reset."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        
        success, error = send_password_reset_email(email)
        
        # Always show success (don't reveal if email exists)
        flash('If that email exists, a password reset link has been sent.', 'success')
        return redirect(url_for('unified_auth.unified_login'))
    
    return render_template('auth/forgot_password.html')


@unified_auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    """Handle password reset."""
    token = request.args.get('token') or request.form.get('token')
    
    if not token:
        flash('Invalid reset link', 'error')
        return redirect(url_for('unified_auth.forgot_password'))
    
    # Verify token
    success, result = verify_reset_token(token)
    
    if not success:
        flash(result, 'error')
        return redirect(url_for('unified_auth.forgot_password'))
    
    user_id = result
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        
        if len(password) < 6:
            return render_template('auth/reset_password.html', token=token, error='Password must be at least 6 characters')
        
        if password != confirm:
            return render_template('auth/reset_password.html', token=token, error='Passwords do not match')
        
        # Update password
        password_hash = generate_password_hash(password, method='scrypt')
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (password_hash, user_id))
        conn.commit()
        conn.close()
        
        # Clear token
        clear_reset_token(user_id)
        
        # Invalidate all sessions for this user
        invalidate_user_sessions(user_id)
        
        log_audit(user_id, 'password_reset', user_id)
        flash('Password updated! You can now log in.', 'success')
        return redirect(url_for('unified_auth.unified_login'))
    
    return render_template('auth/reset_password.html', token=token)


def invalidate_user_sessions(user_id):
    """Invalidate all sessions for a user."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE user_sessions SET is_valid = 0 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()


# ============================================
# PORTAL & NAVIGATION
# ============================================

@unified_auth_bp.route('/portal')
def portal():
    """After login, show user their options based on roles."""
    if 'user_id' not in session:
        return redirect(url_for('unified_auth.unified_login'))
    
    user_id = session['user_id']
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get user info
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    if not user:
        session.clear()
        return redirect(url_for('unified_auth.unified_login'))
    user = dict(user)
    
    # Get venues with roles
    cursor.execute('''
        SELECT b.id, b.name, uvr.role
        FROM venue_staff uvr
        JOIN bars b ON uvr.venue_id = b.id
        WHERE uvr.user_id = ?
        ORDER BY b.name
    ''', (user_id,))
    venues = [dict(row) for row in cursor.fetchall()]
    
    # Check if user is a player
    cursor.execute('SELECT id FROM players WHERE user_id = ?', (user_id,))
    player = cursor.fetchone()
    is_player = player is not None
    
    is_superadmin = user.get('is_superadmin', 0)
    
    conn.close()
    
    # Superadmins go straight to master dashboard
    if is_superadmin:
        return redirect('/master/')
    
    # Smart routing for simple cases
    if not venues and is_player and not is_superadmin:
        # Player only - go straight to player app
        return redirect(url_for('player.home'))
    
    if len(venues) == 1 and not is_superadmin:
        # Single venue - go straight there
        session['current_venue_id'] = venues[0]['id']
        session['current_venue_name'] = venues[0]['name']
        session['current_venue_role'] = venues[0]['role']
        return redirect(url_for('bar_manager.dashboard'))
    
    return render_template('auth/portal.html',
                           user=user,
                           venues=venues,
                           is_player=is_player,
                           is_superadmin=is_superadmin)


@unified_auth_bp.route('/select-venue/<int:venue_id>')
def select_venue(venue_id):
    """Select a venue to manage."""
    if 'user_id' not in session:
        return redirect(url_for('unified_auth.unified_login'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Verify user has access
    cursor.execute('''
        SELECT b.name, uvr.role
        FROM venue_staff uvr
        JOIN bars b ON uvr.venue_id = b.id
        WHERE uvr.user_id = ? AND uvr.venue_id = ?
    ''', (session['user_id'], venue_id))
    venue = cursor.fetchone()
    conn.close()
    
    if not venue:
        flash('You do not have access to that venue', 'error')
        return redirect(url_for('unified_auth.portal'))
    
    venue = dict(venue)
    session['current_venue_id'] = venue_id
    session['current_venue_name'] = venue['name']
    session['current_venue_role'] = venue['role']
    
    # Route based on role
    if venue['role'] in ['owner', 'manager']:
        return redirect(url_for('bar_manager.dashboard'))
    elif venue['role'] == 'staff':
        return redirect(url_for('board.view'))
    elif venue['role'] == 'analyst':
        return redirect(url_for('bar_manager.analytics'))
    
    return redirect(url_for('bar_manager.dashboard'))


@unified_auth_bp.route('/logout')
def logout():
    """Logout and clear session."""
    if 'user_id' in session:
        log_audit(session['user_id'], 'logout', session['user_id'])
    session.clear()
    flash('You have been logged out', 'success')
    return redirect(url_for('unified_auth.unified_login'))


# ============================================
# INVITE ACCEPTANCE
# ============================================

@unified_auth_bp.route('/accept-invite', methods=['GET', 'POST'])
def accept_invite():
    """Accept staff invite and set up account."""
    token = request.args.get('token') or request.form.get('token')
    
    if not token:
        flash('Invalid invite link', 'error')
        return redirect(url_for('unified_auth.unified_login'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get invite
    cursor.execute('''
        SELECT it.*, b.name as venue_name
        FROM invite_tokens it
        JOIN bars b ON it.venue_id = b.id
        WHERE it.token = ? AND it.status = 'pending'
    ''', (token,))
    invite = cursor.fetchone()
    
    if not invite:
        conn.close()
        flash('Invalid or expired invite', 'error')
        return redirect(url_for('unified_auth.unified_login'))
    
    invite = dict(invite)
    
    # Check expiration
    if datetime.fromisoformat(invite['expires_at']) < datetime.now():
        cursor.execute("UPDATE invite_tokens SET status = 'expired' WHERE id = ?", (invite['id'],))
        conn.commit()
        conn.close()
        flash('This invite has expired', 'error')
        return redirect(url_for('unified_auth.unified_login'))
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        password = request.form.get('password', '')
        
        if len(password) < 6:
            return render_template('auth/accept_invite.html', invite=invite, token=token, 
                                   error='Password must be at least 6 characters')
        
        # Check if user already exists
        cursor.execute('SELECT id FROM users WHERE email = ?', (invite['email'],))
        existing = cursor.fetchone()
        
        if existing:
            user_id = existing['id']
        else:
            # Create new user
            password_hash = generate_password_hash(password, method='scrypt')
            cursor.execute('''
                INSERT INTO users (email, password_hash, name, status, email_verified)
                VALUES (?, ?, ?, 'active', 1)
            ''', (invite['email'], password_hash, name or invite['email']))
            user_id = cursor.lastrowid
        
        # Add venue role
        cursor.execute('''
            INSERT OR REPLACE INTO venue_staff (user_id, venue_id, role, assigned_by)
            VALUES (?, ?, ?, ?)
        ''', (user_id, invite['venue_id'], invite['role'], invite['invited_by']))
        
        # Mark invite as accepted
        cursor.execute('''
            UPDATE invite_tokens SET status = 'accepted', accepted_at = ? WHERE id = ?
        ''', (datetime.now().isoformat(), invite['id']))
        
        conn.commit()
        conn.close()
        
        log_audit(user_id, 'invite_accepted', user_id, invite['venue_id'], {
            'role': invite['role'],
            'invited_by': invite['invited_by']
        })
        
        flash(f'Welcome to {invite["venue_name"]}! You can now log in.', 'success')
        return redirect(url_for('unified_auth.unified_login'))
    
    conn.close()
    return render_template('auth/accept_invite.html', invite=invite, token=token)
