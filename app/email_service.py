"""
Email Service for Pool Cue
Handles all email sending: verification, password reset, invites
"""

import os
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from flask import url_for, current_app
from .database import get_db

# Email configuration from environment
SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
FROM_EMAIL = os.environ.get('FROM_EMAIL', 'noreply@poolcue.app')
FROM_NAME = os.environ.get('FROM_NAME', 'Pool Cue')

# For development - print emails instead of sending
DEV_MODE = os.environ.get('FLASK_ENV') == 'development' or not SMTP_USER


def generate_token(length=32):
    """Generate a secure random token."""
    return secrets.token_urlsafe(length)


def send_email(to_email, subject, html_body, text_body=None):
    """
    Send an email. In dev mode, prints to console instead.
    Returns (success, error_message)
    """
    if DEV_MODE:
        print("\n" + "=" * 50)
        print(f"📧 EMAIL (DEV MODE - NOT SENT)")
        print(f"To: {to_email}")
        print(f"Subject: {subject}")
        print("-" * 50)
        print(text_body or html_body)
        print("=" * 50 + "\n")
        return True, None
    
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{FROM_NAME} <{FROM_EMAIL}>"
        msg['To'] = to_email
        
        if text_body:
            msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))
        
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        return True, None
    except Exception as e:
        print(f"❌ Email error: {e}")
        return False, str(e)


# ============================================
# RATE LIMITING
# ============================================

# In-memory rate limit store (use Redis in production)
_rate_limits = {}

def check_rate_limit(email, action, max_attempts=3, window_minutes=15):
    """
    Check if action is rate-limited for this email.
    Returns (allowed, minutes_until_reset)
    """
    key = f"{action}:{email.lower()}"
    now = datetime.now()
    
    if key in _rate_limits:
        attempts, window_start = _rate_limits[key]
        window_end = window_start + timedelta(minutes=window_minutes)
        
        if now > window_end:
            # Window expired, reset
            _rate_limits[key] = (1, now)
            return True, 0
        elif attempts >= max_attempts:
            # Rate limited
            minutes_left = int((window_end - now).total_seconds() / 60) + 1
            return False, minutes_left
        else:
            # Increment attempts
            _rate_limits[key] = (attempts + 1, window_start)
            return True, 0
    else:
        # First attempt
        _rate_limits[key] = (1, now)
        return True, 0


# ============================================
# EMAIL VERIFICATION
# ============================================

def send_verification_email(user_id, email):
    """
    Send email verification link.
    Returns (success, error_message)
    """
    # Check rate limit
    allowed, wait_mins = check_rate_limit(email, 'verify', max_attempts=5, window_minutes=60)
    if not allowed:
        return False, f"Too many attempts. Try again in {wait_mins} minutes."
    
    # Generate token
    token = generate_token()
    expires = datetime.now() + timedelta(hours=1)
    
    # Save to database
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users 
        SET verification_token = ?, verification_token_expires = ?
        WHERE id = ?
    ''', (token, expires.isoformat(), user_id))
    conn.commit()
    conn.close()
    
    # Build verification URL
    # In production, use url_for with _external=True
    base_url = os.environ.get('APP_URL', 'http://localhost:5002')
    verify_url = f"{base_url}/auth/verify-email?token={token}"
    
    subject = "Verify your Pool Cue account"
    html_body = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #22c55e;">🎱 Welcome to Pool Cue!</h2>
        <p>Click the button below to verify your email address:</p>
        <p style="text-align: center; margin: 30px 0;">
            <a href="{verify_url}" style="background: #22c55e; color: #000; padding: 12px 30px; text-decoration: none; border-radius: 6px; font-weight: bold;">
                Verify Email
            </a>
        </p>
        <p style="color: #666; font-size: 14px;">This link expires in 1 hour.</p>
        <p style="color: #666; font-size: 14px;">If you didn't create a Pool Cue account, ignore this email.</p>
    </div>
    """
    text_body = f"Verify your Pool Cue account: {verify_url}\n\nThis link expires in 1 hour."
    
    return send_email(email, subject, html_body, text_body)


def verify_email_token(token):
    """
    Verify an email verification token.
    Returns (success, user_id or error_message)
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, email, verification_token_expires 
        FROM users 
        WHERE verification_token = ?
    ''', (token,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return False, "Invalid verification link"
    
    user = dict(user)
    expires = datetime.fromisoformat(user['verification_token_expires'])
    
    if datetime.now() > expires:
        conn.close()
        return False, "Verification link has expired"
    
    # Mark as verified
    cursor.execute('''
        UPDATE users 
        SET email_verified = 1, verification_token = NULL, verification_token_expires = NULL
        WHERE id = ?
    ''', (user['id'],))
    conn.commit()
    conn.close()
    
    return True, user['id']


# ============================================
# PASSWORD RESET
# ============================================

def send_password_reset_email(email):
    """
    Send password reset link.
    Returns (success, error_message)
    """
    # Check rate limit (stricter for password reset)
    allowed, wait_mins = check_rate_limit(email, 'reset', max_attempts=3, window_minutes=15)
    if not allowed:
        return False, f"Too many attempts. Try again in {wait_mins} minutes."
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, name FROM users WHERE email = ? AND status = ?', (email.lower(), 'active'))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        # Don't reveal if email exists
        return True, None
    
    user = dict(user)
    
    # Generate token
    token = generate_token()
    expires = datetime.now() + timedelta(minutes=30)
    
    cursor.execute('''
        UPDATE users 
        SET reset_token = ?, reset_token_expires = ?
        WHERE id = ?
    ''', (token, expires.isoformat(), user['id']))
    conn.commit()
    conn.close()
    
    # Build reset URL
    base_url = os.environ.get('APP_URL', 'http://localhost:5002')
    reset_url = f"{base_url}/auth/reset-password?token={token}"
    
    subject = "Reset your Pool Cue password"
    html_body = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #22c55e;">🎱 Password Reset</h2>
        <p>Hi {user['name'] or 'there'},</p>
        <p>Click the button below to reset your password:</p>
        <p style="text-align: center; margin: 30px 0;">
            <a href="{reset_url}" style="background: #22c55e; color: #000; padding: 12px 30px; text-decoration: none; border-radius: 6px; font-weight: bold;">
                Reset Password
            </a>
        </p>
        <p style="color: #666; font-size: 14px;">This link expires in 30 minutes.</p>
        <p style="color: #666; font-size: 14px;">If you didn't request this, ignore this email.</p>
    </div>
    """
    text_body = f"Reset your Pool Cue password: {reset_url}\n\nThis link expires in 30 minutes."
    
    return send_email(email, subject, html_body, text_body)


def verify_reset_token(token):
    """
    Verify a password reset token.
    Returns (success, user_id or error_message)
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, reset_token_expires 
        FROM users 
        WHERE reset_token = ? AND status = 'active'
    ''', (token,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return False, "Invalid or expired reset link"
    
    user = dict(user)
    expires = datetime.fromisoformat(user['reset_token_expires'])
    
    if datetime.now() > expires:
        conn.close()
        return False, "Reset link has expired"
    
    conn.close()
    return True, user['id']


def clear_reset_token(user_id):
    """Clear reset token after password is changed."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users SET reset_token = NULL, reset_token_expires = NULL WHERE id = ?
    ''', (user_id,))
    conn.commit()
    conn.close()


# ============================================
# STAFF INVITES
# ============================================

def send_staff_invite_email(email, venue_name, role, invite_token, invited_by_name):
    """
    Send staff invite email.
    Returns (success, error_message)
    """
    base_url = os.environ.get('APP_URL', 'http://localhost:5002')
    invite_url = f"{base_url}/auth/accept-invite?token={invite_token}"
    
    role_display = role.title()
    
    subject = f"You've been invited to join {venue_name} on Pool Cue"
    html_body = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #22c55e;">🎱 You're Invited!</h2>
        <p>{invited_by_name} has invited you to join <strong>{venue_name}</strong> as a <strong>{role_display}</strong> on Pool Cue.</p>
        <p>Pool Cue helps bars manage their pool table queues. As {role_display}, you'll be able to manage the queue and help run things smoothly.</p>
        <p style="text-align: center; margin: 30px 0;">
            <a href="{invite_url}" style="background: #22c55e; color: #000; padding: 12px 30px; text-decoration: none; border-radius: 6px; font-weight: bold;">
                Accept Invite
            </a>
        </p>
        <p style="color: #666; font-size: 14px;">This invite expires in 72 hours.</p>
    </div>
    """
    text_body = f"""
{invited_by_name} has invited you to join {venue_name} as a {role_display} on Pool Cue.

Accept your invite: {invite_url}

This invite expires in 72 hours.
"""
    
    return send_email(email, subject, html_body, text_body)


def create_staff_invite(email, venue_id, role, invited_by_user_id):
    """
    Create a staff invite and send email.
    Returns (success, error_or_token)
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if user already has a role at this venue
    cursor.execute('SELECT id FROM users WHERE email = ?', (email.lower(),))
    existing_user = cursor.fetchone()
    
    if existing_user:
        cursor.execute('''
            SELECT id FROM user_venue_roles_v2 
            WHERE user_id = ? AND venue_id = ?
        ''', (existing_user['id'], venue_id))
        if cursor.fetchone():
            conn.close()
            return False, "User already has a role at this venue"
    
    # Check for existing pending invite
    cursor.execute('''
        SELECT id FROM invite_tokens 
        WHERE email = ? AND venue_id = ? AND status = 'pending'
    ''', (email.lower(), venue_id))
    if cursor.fetchone():
        conn.close()
        return False, "Invite already pending for this email"
    
    # Get venue name and inviter name
    cursor.execute('SELECT name FROM bars WHERE id = ?', (venue_id,))
    venue = cursor.fetchone()
    if not venue:
        conn.close()
        return False, "Venue not found"
    venue_name = venue['name']
    
    cursor.execute('SELECT name, email FROM users WHERE id = ?', (invited_by_user_id,))
    inviter = cursor.fetchone()
    inviter_name = inviter['name'] or inviter['email'] if inviter else 'A manager'
    
    # Create invite token
    token = generate_token()
    expires = datetime.now() + timedelta(hours=72)
    
    cursor.execute('''
        INSERT INTO invite_tokens (token, email, venue_id, role, invited_by, expires_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (token, email.lower(), venue_id, role, invited_by_user_id, expires.isoformat()))
    conn.commit()
    conn.close()
    
    # Send email
    success, error = send_staff_invite_email(email, venue_name, role, token, inviter_name)
    
    if success:
        # Log to audit
        log_audit(invited_by_user_id, 'invite_sent', None, venue_id, {
            'email': email,
            'role': role
        })
        return True, token
    else:
        return False, error or "Failed to send invite email"


# ============================================
# AUDIT LOGGING
# ============================================

def log_audit(actor_user_id, action, target_user_id=None, venue_id=None, details=None, ip_address=None):
    """
    Log an action to the audit log.
    """
    import json
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO audit_log (actor_user_id, action, target_user_id, venue_id, details_json, ip_address)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        actor_user_id,
        action,
        target_user_id,
        venue_id,
        json.dumps(details) if details else None,
        ip_address
    ))
    conn.commit()
    conn.close()


def get_audit_log(user_id=None, venue_id=None, action=None, limit=50):
    """Get audit log entries with optional filters."""
    import json
    conn = get_db()
    cursor = conn.cursor()
    
    query = 'SELECT * FROM audit_log WHERE 1=1'
    params = []
    
    if user_id:
        query += ' AND (actor_user_id = ? OR target_user_id = ?)'
        params.extend([user_id, user_id])
    if venue_id:
        query += ' AND venue_id = ?'
        params.append(venue_id)
    if action:
        query += ' AND action = ?'
        params.append(action)
    
    query += ' ORDER BY timestamp DESC LIMIT ?'
    params.append(limit)
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        row = dict(row)
        if row.get('details_json'):
            row['details'] = json.loads(row['details_json'])
        results.append(row)
    
    return results
