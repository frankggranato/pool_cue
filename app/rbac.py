"""
RBAC - Role-Based Access Control Helpers (v2)
Simplified permission checking for Pool Cue

Roles: owner, manager, staff, analyst
- owner: Full venue access, can manage staff, view financials
- manager: Can manage staff, queue, view analytics
- staff: Can operate board/queue only
- analyst: Read-only analytics access
"""

from functools import wraps
from flask import session, redirect, url_for, flash, request, g
from .database import get_db


# ============================================
# ROLE PERMISSIONS MAPPING
# ============================================

ROLE_PERMISSIONS = {
    'owner': [
        'manage_staff', 'view_staff', 'view_analytics', 'export_data',
        'manage_queue', 'operate_board', 'edit_settings', 'view_financials',
        'manage_events', 'manage_tournaments'
    ],
    'manager': [
        'manage_staff', 'view_staff', 'view_analytics', 'export_data',
        'manage_queue', 'operate_board', 'manage_events', 'manage_tournaments'
    ],
    'staff': [
        'view_staff', 'manage_queue', 'operate_board'
    ],
    'analyst': [
        'view_staff', 'view_analytics', 'export_data'
    ],
}

ROLE_HIERARCHY = {
    'owner': 100,
    'manager': 70,
    'staff': 50,
    'analyst': 30,
}


# ============================================
# PERMISSION CHECKING
# ============================================

def get_user_permissions(user_id, venue_id=None):
    """
    Get all permissions for a user at a specific venue.
    Returns a set of permission names.
    """
    # Superadmins have all permissions
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT is_superadmin FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    
    if user and user['is_superadmin']:
        conn.close()
        # Return all possible permissions
        all_perms = set()
        for perms in ROLE_PERMISSIONS.values():
            all_perms.update(perms)
        all_perms.add('access_master')  # Superadmin-only
        all_perms.add('manage_venues')
        all_perms.add('manage_all_users')
        return all_perms
    
    if not venue_id:
        conn.close()
        return set()
    
    # Get role for this venue
    cursor.execute('''
        SELECT role FROM user_venue_roles_v2
        WHERE user_id = ? AND venue_id = ?
    ''', (user_id, venue_id))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return set()
    
    return set(ROLE_PERMISSIONS.get(row['role'], []))


def user_has_permission(user_id, permission, venue_id=None):
    """Check if a user has a specific permission."""
    permissions = get_user_permissions(user_id, venue_id)
    return permission in permissions


def get_user_role(user_id, venue_id):
    """Get user's role at a specific venue."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT role FROM user_venue_roles_v2
        WHERE user_id = ? AND venue_id = ?
    ''', (user_id, venue_id))
    row = cursor.fetchone()
    conn.close()
    return row['role'] if row else None


def get_user_venues(user_id):
    """Get all venues a user has access to."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT b.id, b.name, uvr.role
        FROM user_venue_roles_v2 uvr
        JOIN bars b ON uvr.venue_id = b.id
        WHERE uvr.user_id = ?
        ORDER BY b.name
    ''', (user_id,))
    venues = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return venues


def is_superadmin(user_id):
    """Check if user is a superadmin."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT is_superadmin FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user and user['is_superadmin']


# ============================================
# DECORATORS
# ============================================

def login_required(f):
    """Require any authenticated user."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please log in', 'error')
            return redirect(url_for('unified_auth.unified_login'))
        return f(*args, **kwargs)
    return decorated_function


def superadmin_required(f):
    """Require superadmin access."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            flash('Please log in', 'error')
            return redirect(url_for('unified_auth.unified_login'))
        
        if not is_superadmin(user_id):
            flash('Superadmin access required', 'error')
            return redirect(url_for('unified_auth.portal'))
        
        return f(*args, **kwargs)
    return decorated_function


def permission_required(permission, venue_id_param='venue_id'):
    """
    Decorator to check for a specific permission.
    Uses venue_id from session or URL param.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = session.get('user_id')
            if not user_id:
                flash('Please log in', 'error')
                return redirect(url_for('unified_auth.unified_login'))
            
            # Get venue_id from kwargs, session, or request
            venue_id = kwargs.get(venue_id_param) or \
                       session.get('current_venue_id') or \
                       request.args.get('venue_id')
            
            if not user_has_permission(user_id, permission, venue_id):
                flash('Permission denied', 'error')
                return redirect(url_for('unified_auth.portal'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def role_required(*role_names):
    """
    Decorator to require one of the specified roles.
    Checks current venue from session.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = session.get('user_id')
            if not user_id:
                flash('Please log in', 'error')
                return redirect(url_for('unified_auth.unified_login'))
            
            # Superadmins pass all role checks
            if is_superadmin(user_id):
                return f(*args, **kwargs)
            
            venue_id = session.get('current_venue_id')
            if not venue_id:
                flash('No venue selected', 'error')
                return redirect(url_for('unified_auth.portal'))
            
            role = get_user_role(user_id, venue_id)
            if role not in role_names:
                flash('Access denied for your role', 'error')
                return redirect(url_for('bar_manager.dashboard'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ============================================
# ROLE MANAGEMENT
# ============================================

def assign_role(user_id, role, venue_id, assigned_by):
    """Assign a role to a user at a venue."""
    if role not in ROLE_PERMISSIONS:
        raise ValueError(f"Invalid role: {role}")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO user_venue_roles_v2 (user_id, venue_id, role, assigned_by)
        VALUES (?, ?, ?, ?)
    ''', (user_id, venue_id, role, assigned_by))
    conn.commit()
    conn.close()
    
    # Log to audit
    from .email_service import log_audit
    log_audit(assigned_by, 'role_assigned', user_id, venue_id, {'role': role})


def remove_role(user_id, venue_id, removed_by):
    """Remove a user's role at a venue."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get current role for audit
    cursor.execute('SELECT role FROM user_venue_roles_v2 WHERE user_id = ? AND venue_id = ?', 
                   (user_id, venue_id))
    current = cursor.fetchone()
    old_role = current['role'] if current else None
    
    cursor.execute('DELETE FROM user_venue_roles_v2 WHERE user_id = ? AND venue_id = ?', 
                   (user_id, venue_id))
    conn.commit()
    conn.close()
    
    # Log to audit
    from .email_service import log_audit
    log_audit(removed_by, 'role_removed', user_id, venue_id, {'old_role': old_role})


def change_role(user_id, new_role, venue_id, changed_by):
    """Change a user's role at a venue."""
    if new_role not in ROLE_PERMISSIONS:
        raise ValueError(f"Invalid role: {new_role}")
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get current role for audit
    cursor.execute('SELECT role FROM user_venue_roles_v2 WHERE user_id = ? AND venue_id = ?', 
                   (user_id, venue_id))
    current = cursor.fetchone()
    old_role = current['role'] if current else None
    
    cursor.execute('UPDATE user_venue_roles_v2 SET role = ? WHERE user_id = ? AND venue_id = ?', 
                   (new_role, user_id, venue_id))
    conn.commit()
    conn.close()
    
    # Log to audit
    from .email_service import log_audit
    log_audit(changed_by, 'role_changed', user_id, venue_id, {
        'old_role': old_role,
        'new_role': new_role
    })


# ============================================
# TEMPLATE CONTEXT
# ============================================

def inject_rbac_context():
    """
    Context processor to inject RBAC info into templates.
    Call this in app.py context_processor.
    """
    user_id = session.get('user_id')
    venue_id = session.get('current_venue_id')
    
    context = {
        'current_user_id': user_id,
        'current_venue_id': venue_id,
        'is_superadmin': False,
        'user_role': None,
        'user_permissions': set(),
    }
    
    if user_id:
        context['is_superadmin'] = is_superadmin(user_id)
        if venue_id:
            context['user_role'] = get_user_role(user_id, venue_id)
            context['user_permissions'] = get_user_permissions(user_id, venue_id)
    
    return context


def get_all_roles():
    """Get list of all available roles."""
    return list(ROLE_PERMISSIONS.keys())


def get_role_permissions(role):
    """Get permissions for a specific role."""
    return ROLE_PERMISSIONS.get(role, [])
