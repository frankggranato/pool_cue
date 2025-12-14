"""
RBAC - Role-Based Access Control Helpers
Unified permission checking for Pool Cue
"""

from functools import wraps
from flask import session, redirect, url_for, flash, request, g
from .database import get_db


# ============================================
# PERMISSION CHECKING
# ============================================

def get_user_permissions(user_id, venue_id=None):
    """
    Get all permissions for a user at a specific venue (or globally).
    Returns a set of permission names.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Get permissions from roles assigned to this user for this venue OR globally
    cursor.execute('''
        SELECT DISTINCT p.name
        FROM user_venue_roles uvr
        JOIN role_permissions rp ON uvr.role_id = rp.role_id
        JOIN permissions p ON rp.permission_id = p.id
        WHERE uvr.user_id = ?
        AND (uvr.venue_id = ? OR uvr.venue_id IS NULL)
    ''', (user_id, venue_id))
    
    permissions = {row['name'] for row in cursor.fetchall()}
    conn.close()
    return permissions


def user_has_permission(user_id, permission, venue_id=None):
    """Check if a user has a specific permission."""
    # Superadmins have all permissions
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT is_superadmin FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if user and user['is_superadmin']:
        return True
    
    permissions = get_user_permissions(user_id, venue_id)
    return permission in permissions


def get_user_roles(user_id, venue_id=None):
    """Get all roles for a user at a specific venue."""
    conn = get_db()
    cursor = conn.cursor()
    
    if venue_id:
        cursor.execute('''
            SELECT r.name, r.level
            FROM user_venue_roles uvr
            JOIN roles r ON uvr.role_id = r.id
            WHERE uvr.user_id = ?
            AND (uvr.venue_id = ? OR uvr.venue_id IS NULL)
            ORDER BY r.level DESC
        ''', (user_id, venue_id))
    else:
        cursor.execute('''
            SELECT r.name, r.level, uvr.venue_id
            FROM user_venue_roles uvr
            JOIN roles r ON uvr.role_id = r.id
            WHERE uvr.user_id = ?
            ORDER BY r.level DESC
        ''', (user_id,))
    
    roles = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return roles


def get_user_venues(user_id):
    """Get all venues a user has access to."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT DISTINCT b.id, b.name, r.name as role_name, r.level
        FROM user_venue_roles uvr
        JOIN bars b ON uvr.venue_id = b.id
        JOIN roles r ON uvr.role_id = r.id
        WHERE uvr.user_id = ?
        ORDER BY b.name
    ''', (user_id,))
    
    venues = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return venues


def get_highest_role(user_id, venue_id=None):
    """Get the highest-level role a user has at a venue."""
    roles = get_user_roles(user_id, venue_id)
    if roles:
        return roles[0]  # Already sorted by level DESC
    return None


# ============================================
# DECORATORS FOR ROUTE PROTECTION
# ============================================

def login_required(f):
    """Require any authenticated user."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue', 'error')
            return redirect(url_for('auth.unified_login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def permission_required(permission, venue_id_param='venue_id'):
    """
    Require a specific permission. 
    venue_id can come from URL param, session, or be None for global perms.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to continue', 'error')
                return redirect(url_for('auth.unified_login', next=request.url))
            
            user_id = session['user_id']
            
            # Try to get venue_id from kwargs, request args, or session
            venue_id = kwargs.get(venue_id_param) or \
                       request.args.get(venue_id_param) or \
                       session.get('current_venue_id')
            
            if not user_has_permission(user_id, permission, venue_id):
                flash('You do not have permission to access this page', 'error')
                return redirect(url_for('auth.portal'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def role_required(*role_names, venue_id_param='venue_id'):
    """Require one of the specified roles."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to continue', 'error')
                return redirect(url_for('auth.unified_login', next=request.url))
            
            user_id = session['user_id']
            venue_id = kwargs.get(venue_id_param) or \
                       request.args.get(venue_id_param) or \
                       session.get('current_venue_id')
            
            roles = get_user_roles(user_id, venue_id)
            user_role_names = {r['name'] for r in roles}
            
            # Check superadmin
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('SELECT is_superadmin FROM users WHERE id = ?', (user_id,))
            user = cursor.fetchone()
            conn.close()
            
            if user and user['is_superadmin']:
                return f(*args, **kwargs)
            
            if not user_role_names.intersection(set(role_names)):
                flash('You do not have the required role to access this page', 'error')
                return redirect(url_for('auth.portal'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def superadmin_required(f):
    """Require superadmin access."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue', 'error')
            return redirect(url_for('auth.unified_login', next=request.url))
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT is_superadmin FROM users WHERE id = ?', (session['user_id'],))
        user = cursor.fetchone()
        conn.close()
        
        if not user or not user['is_superadmin']:
            flash('Superadmin access required', 'error')
            return redirect(url_for('auth.portal'))
        
        return f(*args, **kwargs)
    return decorated_function


# ============================================
# ROLE MANAGEMENT FUNCTIONS
# ============================================

def assign_role(user_id, role_name, venue_id=None, assigned_by=None):
    """Assign a role to a user for a venue."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM roles WHERE name = ?', (role_name,))
    role = cursor.fetchone()
    if not role:
        conn.close()
        return False, f"Role '{role_name}' not found"
    
    try:
        cursor.execute('''
            INSERT INTO user_venue_roles (user_id, venue_id, role_id, assigned_by)
            VALUES (?, ?, ?, ?)
        ''', (user_id, venue_id, role['id'], assigned_by))
        conn.commit()
        conn.close()
        return True, "Role assigned"
    except Exception as e:
        conn.close()
        return False, str(e)


def remove_role(user_id, role_name, venue_id=None):
    """Remove a role from a user."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM roles WHERE name = ?', (role_name,))
    role = cursor.fetchone()
    if not role:
        conn.close()
        return False, f"Role '{role_name}' not found"
    
    cursor.execute('''
        DELETE FROM user_venue_roles 
        WHERE user_id = ? AND role_id = ? AND (venue_id = ? OR (venue_id IS NULL AND ? IS NULL))
    ''', (user_id, role['id'], venue_id, venue_id))
    conn.commit()
    conn.close()
    return True, "Role removed"


def get_all_roles():
    """Get all available roles."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM roles ORDER BY level DESC')
    roles = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return roles


def get_all_permissions():
    """Get all available permissions."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM permissions ORDER BY category, name')
    permissions = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return permissions


# ============================================
# CONTEXT PROCESSOR FOR TEMPLATES
# ============================================

def inject_rbac_context():
    """Add RBAC info to template context."""
    context = {
        'current_user': None,
        'user_permissions': set(),
        'user_roles': [],
        'user_venues': [],
    }
    
    if 'user_id' in session:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            context['current_user'] = dict(user)
            venue_id = session.get('current_venue_id')
            context['user_permissions'] = get_user_permissions(session['user_id'], venue_id)
            context['user_roles'] = get_user_roles(session['user_id'], venue_id)
            context['user_venues'] = get_user_venues(session['user_id'])
    
    return context
