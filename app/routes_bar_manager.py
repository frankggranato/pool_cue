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
    """Decorator to require bar manager login (unified auth only)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check unified auth with venue selected
        if session.get('user_id') and session.get('current_venue_id'):
            return f(*args, **kwargs)
        # Redirect to unified login
        return redirect(url_for('unified_auth.unified_login'))
    return decorated_function


def get_manager_bar():
    """Get the bar associated with the logged-in manager."""
    venue_id = session.get('current_venue_id')
    if not venue_id:
        return None
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id as bar_id, name as bar_name FROM bars WHERE id = ?', (venue_id,))
    result = cursor.fetchone()
    conn.close()
    return dict(result) if result else None


# ============================================================================
# AUTH ROUTES (Redirects to Unified Auth)
# ============================================================================

@bar_manager_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Redirect to unified login."""
    return redirect(url_for('unified_auth.unified_login'))


@bar_manager_bp.route('/logout')
def logout():
    """Redirect to unified logout."""
    return redirect(url_for('unified_auth.logout'))


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



# ============================================================================
# STAFF & PERMISSIONS (RBAC)
# ============================================================================

def get_current_venue_id():
    """Get current venue ID from session (supports both old and new format)."""
    return session.get('current_venue_id') or session.get('bar_manager_bar_id')


def venue_permission_required(permission):
    """Decorator to check permission for current venue."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = session.get('user_id')
            venue_id = get_current_venue_id()
            
            if not user_id or not venue_id:
                flash('Please log in', 'error')
                return redirect(url_for('unified_auth.unified_login'))
            
            # Check if superadmin
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('SELECT is_superadmin FROM users WHERE id = ?', (user_id,))
            user = cursor.fetchone()
            if user and user['is_superadmin']:
                conn.close()
                return f(*args, **kwargs)
            
            # Check venue role
            cursor.execute('''
                SELECT role FROM venue_staff 
                WHERE user_id = ? AND venue_id = ?
            ''', (user_id, venue_id))
            role = cursor.fetchone()
            conn.close()
            
            if not role:
                flash('No access to this venue', 'error')
                return redirect(url_for('unified_auth.portal'))
            
            # Permission mapping
            role_permissions = {
                'owner': ['manage_staff', 'view_staff', 'view_analytics', 'manage_queue', 'edit_settings'],
                'manager': ['manage_staff', 'view_staff', 'view_analytics', 'manage_queue'],
                'staff': ['view_staff', 'manage_queue'],
                'analyst': ['view_staff', 'view_analytics'],
            }
            
            if permission in role_permissions.get(role['role'], []):
                return f(*args, **kwargs)
            
            flash('Permission denied', 'error')
            return redirect(url_for('bar_manager.dashboard'))
        return decorated_function
    return decorator


@bar_manager_bp.route('/staff')
@bar_manager_required
def staff_list():
    """View and manage venue staff."""
    venue_id = get_current_venue_id()
    user_id = session.get('user_id')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get venue info
    cursor.execute('SELECT name FROM bars WHERE id = ?', (venue_id,))
    venue = cursor.fetchone()
    venue_name = venue['name'] if venue else 'Unknown'
    
    # Get staff members
    cursor.execute('''
        SELECT u.id, u.name, u.email, u.status, u.last_login, uvr.role, uvr.created_at as assigned_at
        FROM venue_staff uvr
        JOIN users u ON uvr.user_id = u.id
        WHERE uvr.venue_id = ?
        ORDER BY 
            CASE uvr.role 
                WHEN 'owner' THEN 1 
                WHEN 'manager' THEN 2 
                WHEN 'staff' THEN 3 
                WHEN 'analyst' THEN 4 
            END,
            u.name
    ''', (venue_id,))
    staff = [dict(row) for row in cursor.fetchall()]
    
    # Get pending invites
    cursor.execute('''
        SELECT * FROM invite_tokens 
        WHERE venue_id = ? AND status = 'pending'
        ORDER BY created_at DESC
    ''', (venue_id,))
    invites = [dict(row) for row in cursor.fetchall()]
    
    # Check current user's role (for permissions)
    cursor.execute('SELECT role FROM venue_staff WHERE user_id = ? AND venue_id = ?', (user_id, venue_id))
    my_role = cursor.fetchone()
    can_manage = my_role and my_role['role'] in ['owner', 'manager']
    
    # Check if superadmin
    cursor.execute('SELECT is_superadmin FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    is_superadmin = user and user['is_superadmin']
    
    conn.close()
    
    return render_template('bar_manager/staff.html',
                           staff=staff,
                           invites=invites,
                           venue_name=venue_name,
                           venue_id=venue_id,
                           can_manage=can_manage or is_superadmin)


@bar_manager_bp.route('/staff/invite', methods=['POST'])
@bar_manager_required
def invite_staff():
    """Invite a new staff member."""
    from .email_service import create_staff_invite, log_audit
    
    venue_id = get_current_venue_id()
    user_id = session.get('user_id')
    
    email = request.form.get('email', '').strip().lower()
    role = request.form.get('role', 'staff')
    
    if not email:
        flash('Email is required', 'error')
        return redirect(url_for('bar_manager.staff_list'))
    
    if role not in ['owner', 'manager', 'staff', 'analyst']:
        flash('Invalid role', 'error')
        return redirect(url_for('bar_manager.staff_list'))
    
    success, result = create_staff_invite(email, venue_id, role, user_id)
    
    if success:
        flash(f'Invite sent to {email}', 'success')
    else:
        flash(result, 'error')
    
    return redirect(url_for('bar_manager.staff_list'))


@bar_manager_bp.route('/staff/<int:target_user_id>/change-role', methods=['POST'])
@bar_manager_required
def change_staff_role(target_user_id):
    """Change a staff member's role."""
    from .email_service import log_audit
    
    venue_id = get_current_venue_id()
    user_id = session.get('user_id')
    new_role = request.form.get('role')
    
    if new_role not in ['owner', 'manager', 'staff', 'analyst']:
        flash('Invalid role', 'error')
        return redirect(url_for('bar_manager.staff_list'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get current role
    cursor.execute('SELECT role FROM venue_staff WHERE user_id = ? AND venue_id = ?', 
                   (target_user_id, venue_id))
    current = cursor.fetchone()
    old_role = current['role'] if current else None
    
    # Update role
    cursor.execute('''
        UPDATE venue_staff SET role = ? WHERE user_id = ? AND venue_id = ?
    ''', (new_role, target_user_id, venue_id))
    conn.commit()
    conn.close()
    
    log_audit(user_id, 'role_changed', target_user_id, venue_id, {
        'old_role': old_role,
        'new_role': new_role
    })
    
    flash(f'Role updated to {new_role.title()}', 'success')
    return redirect(url_for('bar_manager.staff_list'))


@bar_manager_bp.route('/staff/<int:target_user_id>/remove', methods=['POST'])
@bar_manager_required
def remove_staff(target_user_id):
    """Remove staff member from this venue only."""
    from .email_service import log_audit
    
    venue_id = get_current_venue_id()
    user_id = session.get('user_id')
    
    # Can't remove yourself
    if target_user_id == user_id:
        flash("You can't remove yourself", 'error')
        return redirect(url_for('bar_manager.staff_list'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get user info for audit
    cursor.execute('SELECT email FROM users WHERE id = ?', (target_user_id,))
    target = cursor.fetchone()
    target_email = target['email'] if target else 'unknown'
    
    # Delete venue role
    cursor.execute('DELETE FROM venue_staff WHERE user_id = ? AND venue_id = ?', 
                   (target_user_id, venue_id))
    conn.commit()
    conn.close()
    
    log_audit(user_id, 'removed_from_venue', target_user_id, venue_id, {
        'email': target_email
    })
    
    flash('Staff member removed from venue', 'success')
    return redirect(url_for('bar_manager.staff_list'))


@bar_manager_bp.route('/staff/<int:target_user_id>/deactivate', methods=['POST'])
@bar_manager_required
def deactivate_staff(target_user_id):
    """Deactivate a user globally (suspends all access)."""
    from .email_service import log_audit
    
    venue_id = get_current_venue_id()
    user_id = session.get('user_id')
    
    # Can't deactivate yourself
    if target_user_id == user_id:
        flash("You can't deactivate yourself", 'error')
        return redirect(url_for('bar_manager.staff_list'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Can't deactivate superadmins
    cursor.execute('SELECT is_superadmin, email FROM users WHERE id = ?', (target_user_id,))
    target = cursor.fetchone()
    if not target:
        conn.close()
        flash('User not found', 'error')
        return redirect(url_for('bar_manager.staff_list'))
    
    if target['is_superadmin']:
        conn.close()
        flash("Can't deactivate superadmins", 'error')
        return redirect(url_for('bar_manager.staff_list'))
    
    # Deactivate user
    cursor.execute("UPDATE users SET status = 'suspended' WHERE id = ?", (target_user_id,))
    
    # Invalidate all sessions
    cursor.execute('UPDATE user_sessions SET is_valid = 0 WHERE user_id = ?', (target_user_id,))
    
    conn.commit()
    conn.close()
    
    log_audit(user_id, 'user_deactivated', target_user_id, venue_id, {
        'email': target['email']
    })
    
    flash('User deactivated globally', 'success')
    return redirect(url_for('bar_manager.staff_list'))


@bar_manager_bp.route('/staff/<int:target_user_id>/reactivate', methods=['POST'])
@bar_manager_required
def reactivate_staff(target_user_id):
    """Reactivate a suspended user."""
    from .email_service import log_audit
    
    venue_id = get_current_venue_id()
    user_id = session.get('user_id')
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT email FROM users WHERE id = ?', (target_user_id,))
    target = cursor.fetchone()
    
    cursor.execute("UPDATE users SET status = 'active' WHERE id = ?", (target_user_id,))
    conn.commit()
    conn.close()
    
    log_audit(user_id, 'user_reactivated', target_user_id, venue_id, {
        'email': target['email'] if target else 'unknown'
    })
    
    flash('User reactivated', 'success')
    return redirect(url_for('bar_manager.staff_list'))


@bar_manager_bp.route('/staff/<int:target_user_id>/send-reset', methods=['POST'])
@bar_manager_required
def send_staff_reset(target_user_id):
    """Send password reset email to staff member."""
    from .email_service import send_password_reset_email, log_audit
    
    venue_id = get_current_venue_id()
    user_id = session.get('user_id')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT email FROM users WHERE id = ?', (target_user_id,))
    target = cursor.fetchone()
    conn.close()
    
    if not target:
        flash('User not found', 'error')
        return redirect(url_for('bar_manager.staff_list'))
    
    success, error = send_password_reset_email(target['email'])
    
    log_audit(user_id, 'password_reset_sent', target_user_id, venue_id, {
        'email': target['email']
    })
    
    flash(f'Password reset sent to {target["email"]}', 'success')
    return redirect(url_for('bar_manager.staff_list'))


@bar_manager_bp.route('/staff/invite/<int:invite_id>/revoke', methods=['POST'])
@bar_manager_required
def revoke_invite(invite_id):
    """Revoke a pending invite."""
    from .email_service import log_audit
    
    venue_id = get_current_venue_id()
    user_id = session.get('user_id')
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT email FROM invite_tokens WHERE id = ? AND venue_id = ?', (invite_id, venue_id))
    invite = cursor.fetchone()
    
    cursor.execute("UPDATE invite_tokens SET status = 'revoked' WHERE id = ? AND venue_id = ?", 
                   (invite_id, venue_id))
    conn.commit()
    conn.close()
    
    log_audit(user_id, 'invite_revoked', None, venue_id, {
        'email': invite['email'] if invite else 'unknown'
    })
    
    flash('Invite revoked', 'success')
    return redirect(url_for('bar_manager.staff_list'))
