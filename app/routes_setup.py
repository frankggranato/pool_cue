"""
Pool Cue - Setup Wizard & Admin Authentication
Handles first-time setup and master admin login.
"""
import os
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import check_password_hash
from .database_production import (
    get_db, init_production_db, is_setup_complete, mark_setup_complete,
    create_admin_account, create_first_bar
)

setup_bp = Blueprint('setup', __name__)


def admin_required(f):
    """Decorator to require admin login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('setup.admin_login'))
        return f(*args, **kwargs)
    return decorated_function


def setup_required(f):
    """Decorator to check if setup is complete, redirect to wizard if not."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_setup_complete():
            return redirect(url_for('setup.wizard'))
        return f(*args, **kwargs)
    return decorated_function


@setup_bp.route('/setup')
def wizard():
    """First-time setup wizard."""
    if is_setup_complete():
        return redirect(url_for('public.join'))
    return render_template('setup/wizard.html')


@setup_bp.route('/setup/complete', methods=['POST'])
def complete_setup():
    """Complete the setup process."""
    # Get form data
    admin_username = request.form.get('admin_username', 'admin')
    admin_password = request.form.get('admin_password')
    bar_name = request.form.get('bar_name')
    bar_address = request.form.get('bar_address', '')
    bar_city = request.form.get('bar_city', '')
    bar_state = request.form.get('bar_state', '')
    bar_zip = request.form.get('bar_zip', '')
    
    # SECURITY: Enforce strong password policy
    if not admin_password or len(admin_password) < 12:
        flash('Admin password must be at least 12 characters', 'error')
        return redirect(url_for('setup.wizard'))
    
    import re
    if not re.search(r'[A-Z]', admin_password):
        flash('Admin password must contain at least one uppercase letter', 'error')
        return redirect(url_for('setup.wizard'))
    if not re.search(r'[a-z]', admin_password):
        flash('Admin password must contain at least one lowercase letter', 'error')
        return redirect(url_for('setup.wizard'))
    if not re.search(r'[0-9]', admin_password):
        flash('Admin password must contain at least one number', 'error')
        return redirect(url_for('setup.wizard'))
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', admin_password):
        flash('Admin password must contain at least one special character', 'error')
        return redirect(url_for('setup.wizard'))
    
    if not bar_name:
        flash('Bar name is required', 'error')
        return redirect(url_for('setup.wizard'))
    
    # Initialize database
    init_production_db()
    
    # Create admin account
    if not create_admin_account(admin_username, admin_password):
        flash('Could not create admin account', 'error')
        return redirect(url_for('setup.wizard'))
    
    # Create first bar
    bar_id = create_first_bar(bar_name, bar_address, bar_city, bar_state, bar_zip)
    
    # Mark setup complete
    mark_setup_complete()
    
    # Log admin in
    session['admin_logged_in'] = True
    session['admin_username'] = admin_username
    
    flash(f'Setup complete! {bar_name} is ready to go.', 'success')
    return redirect(url_for('master.dashboard'))


@setup_bp.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Master admin login."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # SECURITY: Beta backdoor only works from localhost OR with env var
        # This is your emergency access if you forget your password
        allow_beta = os.environ.get('ALLOW_BETA_LOGIN', 'false').lower() == 'true'
        is_localhost = request.remote_addr in ('127.0.0.1', '::1', 'localhost')
        
        if username == 'beta' and password == 'beta' and (allow_beta or is_localhost):
            session['admin_logged_in'] = True
            session['admin_id'] = 0
            session['admin_username'] = 'BetaAdmin'
            session['is_superadmin'] = True  # Beta has full access
            session['is_beta'] = True
            return redirect(url_for('master.dashboard'))
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id, password_hash, is_superadmin FROM admin_accounts WHERE username = ? AND is_active = 1', (username,))
        admin = cursor.fetchone()
        conn.close()
        
        if admin and check_password_hash(admin['password_hash'], password):
            session['admin_logged_in'] = True
            session['admin_id'] = admin['id']
            session['admin_username'] = username
            session['is_superadmin'] = bool(admin['is_superadmin'])
            
            # Update last login
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('UPDATE admin_accounts SET last_login = datetime("now") WHERE id = ?', (admin['id'],))
            conn.commit()
            conn.close()
            
            return redirect(url_for('master.dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('setup/admin_login.html')


@setup_bp.route('/admin/logout')
def admin_logout():
    """Log out admin."""
    session.pop('admin_logged_in', None)
    session.pop('admin_id', None)
    session.pop('admin_username', None)
    session.pop('is_superadmin', None)
    session.pop('is_beta', None)
    return redirect(url_for('setup.admin_login'))
