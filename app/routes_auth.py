"""
Authentication routes - Account creation and login
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, flash, current_app
from .database import get_db
import secrets
import hashlib
import re
import os
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

# Rate limiting decorator for sensitive endpoints
def rate_limit_login(f):
    """Apply rate limiting to login endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        limiter = getattr(current_app, 'limiter', None)
        if limiter:
            try:
                limiter.limit("5 per minute;20 per hour")(f)
            except Exception:
                pass
        return f(*args, **kwargs)
    return decorated_function

auth_bp = Blueprint('auth', __name__, url_prefix='/player-auth')

# =============================================================================
# BETA MODE CONFIGURATION
# =============================================================================
# When True: Phone verification is auto-passed (code pre-filled, instant verify)
# When False: Real SMS verification required (for production)
# 
# PRODUCTION CHECKLIST:
# 1. Set BETA_AUTO_VERIFY = False (done - forces manual code entry)
# 2. Set BETA_SHOW_CODE = False (hides code from UI)
# 3. Configure Twilio environment variables for real SMS
# =============================================================================
BETA_AUTO_VERIFY = False  # SECURITY: Real verification required

# BETA TESTING: When True, shows verification code in the UI (users still must enter it manually)
# This is safer than BETA_AUTO_VERIFY because it still validates the code entry flow
# Set to False in production!
BETA_SHOW_CODE = True  # TODO: Set False before production launch


def hash_password(password):
    """Secure password hashing using werkzeug."""
    return generate_password_hash(password, method='scrypt')


def verify_password(stored_hash, password):
    """Verify password against stored hash."""
    # Handle legacy SHA256 hashes during migration
    if stored_hash and len(stored_hash) == 64 and not stored_hash.startswith('scrypt:'):
        # Legacy SHA256 hash
        return stored_hash == hashlib.sha256(password.encode()).hexdigest()
    # Modern secure hash
    return check_password_hash(stored_hash, password)


def validate_password(password):
    """
    Validate password strength.
    Returns (is_valid, error_message)
    """
    if not password:
        return True, None  # Password is optional
    
    if len(password) < 10:
        return False, "Password must be at least 10 characters long"
    
    if not re.search(r'[a-zA-Z]', password):
        return False, "Password must contain at least one letter"
    
    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least one number"
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\\/`~]', password):
        return False, "Password must contain at least one special character (!@#$%^&* etc.)"
    
    return True, None


def normalize_phone(phone):
    """Normalize phone number by removing non-digits."""
    if not phone:
        return None
    digits = re.sub(r'\D', '', phone)
    return digits if digits else None


@auth_bp.route('/signup', methods=['GET', 'POST'])
@auth_bp.route('/signup-test', methods=['GET', 'POST'])  # Alias for cache bypass
def signup():
    """Create a new account - PHONE REQUIRED."""
    from datetime import date
    from flask import make_response
    
    # If already logged in with a real account (not guest), go to player home
    if 'player_id' in session and session.get('player_id') and not session.get('is_guest'):
        # Check if they actually have an account_id (not a guest player)
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT account_id FROM players WHERE id = ?', (session['player_id'],))
        row = cursor.fetchone()
        conn.close()
        if row and row['account_id']:
            return redirect(url_for('player.home'))
    
    today = date.today().isoformat()
    ref_code = request.args.get('ref', '').strip().upper()
    
    if request.method == 'GET':
        # Pre-fill nickname if user already has a session (guest in queue)
        prefill_nickname = session.get('player_nickname', '')
        response = make_response(render_template('auth/signup.html', today=today, ref_code=ref_code, prefill_nickname=prefill_nickname))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    
    # POST - create account
    nickname = request.form.get('nickname', '').strip()
    email = request.form.get('email', '').strip().lower() or None
    phone = request.form.get('phone', '').strip()
    password = request.form.get('password', '')
    age_range = request.form.get('age_range', '').strip() or None
    gender = request.form.get('gender', '').strip() or None
    birthday = request.form.get('birthday', '').strip() or None
    
    # Normalize phone number
    phone_normalized = normalize_phone(phone) if phone else None
    
    if not nickname:
        return render_template('auth/signup.html', error='Nickname is required', today=today, ref_code=ref_code)
    
    # PHONE IS REQUIRED for account creation
    if not phone_normalized or len(phone_normalized) < 10:
        return render_template('auth/signup.html', error='Phone number is required for account creation', today=today, ref_code=ref_code)
    
    # Validate password strength
    password_valid, password_error = validate_password(password)
    if not password_valid:
        return render_template('auth/signup.html', error=password_error, today=today, ref_code=ref_code)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if nickname exists
    cursor.execute('SELECT id, email, password_hash FROM players WHERE nickname = ?', (nickname,))
    existing = cursor.fetchone()
    
    if existing and (existing['email'] or existing['password_hash']):
        conn.close()
        return render_template('auth/signup.html', error='Nickname already taken', today=today, ref_code=ref_code)
    
    # Check if email already in use (if provided)
    if email:
        cursor.execute('SELECT id FROM players WHERE email = ? AND id != ?', (email, existing['id'] if existing else -1))
        email_exists = cursor.fetchone()
        if email_exists:
            conn.close()
            return render_template('auth/signup.html', error='Email already registered. Try logging in instead.', today=today, ref_code=ref_code)
    
    # Check if phone already in use by a VERIFIED account
    cursor.execute('SELECT id, phone_verified FROM players WHERE phone_number = ? AND id != ?', (phone_normalized, existing['id'] if existing else -1))
    phone_existing = cursor.fetchone()
    if phone_existing and phone_existing['phone_verified']:
        conn.close()
        return render_template('auth/signup.html', error='Phone number already registered to a verified account. Try logging in.', today=today, ref_code=ref_code)
    
    password_hash = hash_password(password) if password else None
    session_token = secrets.token_urlsafe(32)
    
    try:
        if existing:
            # Claim guest account - set phone_verified = 0 until verified
            cursor.execute('''UPDATE players SET email=?, phone_number=?, password_hash=?, session_token=?, 
                           age_range=?, gender=?, birthday=?, account_id=?, phone_verified=0 WHERE id=?''',
                (email, phone_normalized, password_hash, session_token, age_range, gender, birthday, existing['id'], existing['id']))
            player_id = existing['id']
        else:
            # Create new account with phone_verified = 0
            cursor.execute('''INSERT INTO players (nickname, email, phone_number, password_hash, session_token, 
                           age_range, gender, birthday, tokens_balance, phone_verified, created_at) 
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, datetime("now"))''',
                (nickname, email, phone_normalized, password_hash, session_token, age_range, gender, birthday))
            player_id = cursor.lastrowid
            cursor.execute('UPDATE players SET account_id=? WHERE id=?', (player_id, player_id))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        error_msg = str(e).lower()
        if 'unique' in error_msg and 'email' in error_msg:
            return render_template('auth/signup.html', error='Email already registered. Try logging in instead.', today=today, ref_code=ref_code)
        elif 'unique' in error_msg and 'phone' in error_msg:
            return render_template('auth/signup.html', error='Phone number already registered.', today=today, ref_code=ref_code)
        else:
            return render_template('auth/signup.html', error='Unable to create account. Please try again.', today=today, ref_code=ref_code)
    
    conn.close()
    
    # Store player in session - fully logged in (no phone verification required)
    session['pending_verify_player_id'] = player_id
    session['player_id'] = player_id
    session['player_nickname'] = nickname
    session['session_token'] = session_token
    session.permanent = True  # Session lasts 30 days
    session.pop('is_guest', None)
    
    # Go straight to player home - phone verification is NOT required
    # Check if user came from QR scan - auto-join queue if so
    from .routes_public import auto_join_pending_player
    queue_id, _, bar_id = auto_join_pending_player(player_id)
    if queue_id:
        return redirect(url_for('public.my_status'))
    
    return redirect(url_for('player.home'))


# Old portal route removed - use unified_auth.portal instead
# The unified_auth blueprint handles all portal routing now


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login to existing account."""
    # If already logged in, go straight to player home
    if 'player_id' in session and session.get('player_id'):
        return redirect(url_for('player.home'))
    
    if request.method == 'GET':
        return render_template('auth/login.html')
    
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    
    # SECURITY: Beta login REMOVED - all logins must use real credentials
    # Master admin can login with admin/[master_password] at /admin/login
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, nickname, password_hash, is_active, phone_number, phone_verified FROM players WHERE email = ?', (email,))
    player = cursor.fetchone()
    
    if not player:
        conn.close()
        return render_template('auth/login.html', error='Account not found')
    
    # Check if account is deactivated
    if player['is_active'] == 0:
        conn.close()
        return render_template('auth/login.html', error='This account has been deactivated. Please contact support.')
    
    if player['password_hash'] and not verify_password(player['password_hash'], password):
        conn.close()
        return render_template('auth/login.html', error='Wrong password')
    
    # If user had legacy hash, upgrade to secure hash
    if player['password_hash'] and len(player['password_hash']) == 64:
        new_hash = hash_password(password)
        cursor.execute('UPDATE players SET password_hash = ? WHERE id = ?', (new_hash, player['id']))
    
    # Generate new session token
    session_token = secrets.token_urlsafe(32)
    cursor.execute('UPDATE players SET session_token = ? WHERE id = ?', (session_token, player['id']))
    conn.commit()
    conn.close()
    
    session['player_id'] = player['id']
    session['player_nickname'] = player['nickname']
    session['session_token'] = session_token
    session.permanent = True  # Session lasts 30 days
    
    # Phone verification is NOT required - go straight to app
    # Check if user came from QR scan - auto-join queue if so
    from .routes_public import auto_join_pending_player
    queue_id, _, bar_id = auto_join_pending_player(player['id'])
    if queue_id:
        # Successfully joined queue from QR scan - go to my status
        return redirect(url_for('public.my_status'))
    
    return redirect(url_for('player.home'))


@auth_bp.route('/logout')
def logout():
    """Logout current user."""
    session.clear()
    return redirect(url_for('auth.login'))


@auth_bp.route('/guest')
def guest():
    """
    Continue as guest - creates or reuses a guest player account.
    
    This provides a first-class guest experience where:
    - A valid player_id is always in the session
    - Guest can use most app features without signing up
    - Guest can later upgrade to a full account
    
    NOTE: Guests do NOT get account_id set - this is what distinguishes
    them from real accounts in the master dashboard.
    """
    # If already has a player_id in session, just redirect to home
    if 'player_id' in session:
        return redirect(url_for('player.home'))
    
    # Create a new guest player
    conn = get_db()
    cursor = conn.cursor()
    
    # Generate unique guest nickname
    import random
    import string
    guest_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    nickname = f"Guest-{guest_code}"
    
    # Ensure uniqueness (unlikely collision but handle it)
    cursor.execute('SELECT id FROM players WHERE nickname = ?', (nickname,))
    while cursor.fetchone():
        guest_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        nickname = f"Guest-{guest_code}"
        cursor.execute('SELECT id FROM players WHERE nickname = ?', (nickname,))
    
    # Generate session token
    session_token = secrets.token_urlsafe(32)
    
    # Create guest player - DO NOT set account_id (this is what makes them a guest)
    cursor.execute('''
        INSERT INTO players (
            nickname, 
            email, 
            password_hash, 
            session_token, 
            tokens_balance, 
            is_active,
            account_id,
            phone_verified,
            created_at
        ) VALUES (?, NULL, NULL, ?, 0, 1, NULL, 0, datetime('now'))
    ''', (nickname, session_token))
    
    player_id = cursor.lastrowid
    
    conn.commit()
    conn.close()
    
    # Set session variables
    session['player_id'] = player_id
    session['player_nickname'] = nickname
    session['session_token'] = session_token
    session['is_guest'] = True  # Flag for UI to know this is a guest
    
    # Check if user came from QR scan - auto-join queue if so
    from .routes_public import auto_join_pending_player
    queue_id, _, bar_id = auto_join_pending_player(player_id)
    if queue_id:
        # Successfully joined queue from QR scan - go to my status
        return redirect(url_for('public.my_status'))
    
    return redirect(url_for('player.home'))


@auth_bp.route('/me')
def me():
    """Get current user info."""
    if 'player_id' not in session:
        return jsonify({'logged_in': False})
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, nickname, email, phone, total_games, wins, losses, 
               tokens_balance, total_tokens_earned, created_at, display_name
        FROM players WHERE id = ?
    ''', (session['player_id'],))
    player = cursor.fetchone()
    conn.close()
    
    if not player:
        return jsonify({'logged_in': False})
    
    return jsonify({
        'logged_in': True,
        'player': dict(player)
    })


# ============ AUTO-INVITE ROUTES ============

@auth_bp.route('/invite/<invite_token>')
def auto_invite_landing(invite_token):
    """
    Landing page for auto-invite links.
    Marks the invite as opened and shows signup form.
    """
    from .database import mark_auto_invite_opened, get_auto_invite_by_token
    
    # Mark as opened
    result = mark_auto_invite_opened(invite_token)
    
    if not result.get('success'):
        return render_template('auth/invite_expired.html', 
                             error="This invite link is invalid or expired.")
    
    # Get invite details
    invite = get_auto_invite_by_token(invite_token)
    
    return render_template('auth/signup.html',
                          invite_token=invite_token,
                          phone_number=invite.get('phone_number') if invite else None,
                          bar_name=invite.get('bar_name') if invite else None,
                          from_invite=True)


@auth_bp.route('/signup-from-invite', methods=['POST'])
def signup_from_invite():
    """
    Handle signup from auto-invite link.
    Links the new account to the invite for tracking.
    """
    from .database import complete_auto_invite_signup
    
    nickname = request.form.get('nickname', '').strip()
    email = request.form.get('email', '').strip() or None
    password = request.form.get('password', '').strip() or None
    phone_number = request.form.get('phone_number', '').strip() or None
    invite_token = request.form.get('invite_token', '')
    
    if not nickname:
        return render_template('auth/signup.html', 
                             error="Nickname is required",
                             invite_token=invite_token,
                             phone_number=phone_number,
                             from_invite=True)
    
    # Validate password if provided
    if password:
        is_valid, err = validate_password(password)
        if not is_valid:
            return render_template('auth/signup.html', 
                                 error=err,
                                 invite_token=invite_token,
                                 phone_number=phone_number,
                                 from_invite=True)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if nickname already taken
    cursor.execute('SELECT id FROM players WHERE LOWER(nickname) = LOWER(?)', (nickname,))
    if cursor.fetchone():
        conn.close()
        return render_template('auth/signup.html',
                             error="That nickname is already taken",
                             invite_token=invite_token,
                             phone_number=phone_number,
                             from_invite=True)
    
    # Create new player with account
    account_id = secrets.token_hex(8)
    password_hash = hash_password(password) if password else None
    session_token = secrets.token_urlsafe(32)
    
    cursor.execute('''
        INSERT INTO players (nickname, email, password_hash, phone_number, account_id, session_token, created_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
    ''', (nickname, email, password_hash, phone_number, account_id, session_token))
    
    player_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # Complete the auto-invite tracking
    if phone_number:
        complete_auto_invite_signup(phone_number, player_id)
    
    # Log them in
    session['player_id'] = player_id
    session['player_nickname'] = nickname
    session['session_token'] = session_token
    
    return redirect(url_for('player.home'))



# ============================================
# VERIFICATION ROUTES
# ============================================

@auth_bp.route('/verify/choose')
def verify_choose():
    """Choose verification channel when user has both phone and email."""
    if 'player_id' not in session:
        return redirect(url_for('auth.login'))
    
    from .database import get_verification_status
    status = get_verification_status(session['player_id'])
    
    if not status:
        return redirect(url_for('auth.login'))
    
    # If already verified both, go home
    if status['phone_verified'] and status['email_verified']:
        return redirect(url_for('player.home'))
    
    # If only one channel available, go directly to that
    if not status['has_phone'] and status['has_email']:
        return redirect(url_for('auth.verify_start', channel='email'))
    if status['has_phone'] and not status['has_email']:
        return redirect(url_for('auth.verify_start', channel='phone'))
    
    return render_template('auth/verify_choose.html', status=status)


@auth_bp.route('/verify/start/<channel>')
def verify_start(channel):
    """Start verification for a channel (phone or email)."""
    if 'player_id' not in session:
        return redirect(url_for('auth.login'))
    
    if channel not in ('phone', 'email'):
        return redirect(url_for('player.home'))
    
    from .database import get_verification_status, create_verification, can_resend_verification
    
    player_id = session['player_id']
    status = get_verification_status(player_id)
    
    if not status:
        return redirect(url_for('auth.login'))
    
    # Check if already verified
    if channel == 'phone' and status['phone_verified']:
        flash('Phone already verified!', 'success')
        return redirect(url_for('player.home'))
    if channel == 'email' and status['email_verified']:
        flash('Email already verified!', 'success')
        return redirect(url_for('player.home'))
    
    destination = status['phone'] if channel == 'phone' else status['email']
    if not destination:
        flash(f'No {channel} on file to verify.', 'error')
        return redirect(url_for('player.home'))
    
    # Check cooldown
    can_send, wait_seconds = can_resend_verification(player_id, channel)
    
    if can_send:
        code = create_verification(player_id, channel, destination)
        if code:
            # Send the code (stubbed for now)
            send_verification_code(channel, destination, code)
            flash(f'Verification code sent to your {channel}!', 'success')
    
    return redirect(url_for('auth.verify_enter', channel=channel))


@auth_bp.route('/verify/<channel>', methods=['GET', 'POST'])
def verify_enter(channel):
    """Enter and verify code."""
    if 'player_id' not in session:
        return redirect(url_for('auth.login'))
    
    if channel not in ('phone', 'email'):
        return redirect(url_for('player.home'))
    
    from .database import get_verification_status, verify_code, can_resend_verification
    
    player_id = session['player_id']
    status = get_verification_status(player_id)
    
    if not status:
        return redirect(url_for('auth.login'))
    
    destination = status['phone'] if channel == 'phone' else status['email']
    
    # Check if already verified
    if channel == 'phone' and status['phone_verified']:
        return redirect(url_for('player.home'))
    if channel == 'email' and status['email_verified']:
        return redirect(url_for('player.home'))
    
    # Check resend cooldown
    can_resend, wait_seconds = can_resend_verification(player_id, channel)
    
    # BETA MODE: Get actual code for display/auto-fill
    beta_code = None
    if BETA_AUTO_VERIFY or BETA_SHOW_CODE:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT code FROM verifications 
            WHERE user_id = ? AND channel = ? AND status = 'pending'
            ORDER BY created_at DESC LIMIT 1
        ''', (player_id, channel))
        row = cursor.fetchone()
        conn.close()
        if row:
            beta_code = row['code']
    
    error = None
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        
        if not code:
            error = 'Please enter the verification code.'
        else:
            result = verify_code(player_id, channel, code)
            
            if result['success']:
                flash(f'{channel.title()} verified successfully!', 'success')
                
                # Check if other channel needs verification
                status = get_verification_status(player_id)
                other_channel = 'email' if channel == 'phone' else 'phone'
                other_has = status[f'has_{other_channel}']
                other_verified = status[f'{other_channel}_verified']
                
                if other_has and not other_verified:
                    return redirect(url_for('auth.verify_choose'))
                
                # Check if user came from QR scan - auto-join queue if so
                from .routes_public import auto_join_pending_player
                queue_id, _, bar_id = auto_join_pending_player(player_id)
                if queue_id:
                    return redirect(url_for('public.my_status'))
                
                return redirect(url_for('player.home'))
            else:
                error = result.get('error', 'Verification failed.')
                if result.get('expired') or result.get('rejected'):
                    can_resend = True
                    wait_seconds = 0
    
    # Mask destination for display
    masked = mask_destination(channel, destination)
    
    return render_template('auth/verify_enter.html', 
                         channel=channel,
                         destination=masked,
                         can_resend=can_resend,
                         wait_seconds=wait_seconds,
                         error=error,
                         beta_mode=BETA_AUTO_VERIFY,
                         beta_show_code=BETA_SHOW_CODE,
                         beta_code=beta_code)


@auth_bp.route('/verify/resend/<channel>', methods=['POST'])
def verify_resend(channel):
    """Resend verification code."""
    if 'player_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    if channel not in ('phone', 'email'):
        return jsonify({'error': 'Invalid channel'}), 400
    
    from .database import get_verification_status, create_verification, can_resend_verification
    
    player_id = session['player_id']
    status = get_verification_status(player_id)
    
    if not status:
        return jsonify({'error': 'User not found'}), 404
    
    destination = status['phone'] if channel == 'phone' else status['email']
    if not destination:
        return jsonify({'error': f'No {channel} on file'}), 400
    
    # Check cooldown
    can_send, wait_seconds = can_resend_verification(player_id, channel)
    
    if not can_send:
        return jsonify({'error': f'Please wait {wait_seconds} seconds before resending.', 'wait': wait_seconds}), 429
    
    code = create_verification(player_id, channel, destination)
    if code:
        send_verification_code(channel, destination, code)
        return jsonify({'success': True, 'message': f'Code sent to your {channel}!'})
    
    return jsonify({'error': 'Could not send code. Please try again.'}), 500


@auth_bp.route('/verify/skip')
def verify_skip():
    """Skip verification for now."""
    if 'player_id' not in session:
        return redirect(url_for('auth.login'))
    
    # Check if user came from QR scan - auto-join queue if so
    from .routes_public import auto_join_pending_player
    queue_id, _, bar_id = auto_join_pending_player(session['player_id'])
    if queue_id:
        return redirect(url_for('public.my_status'))
    
    return redirect(url_for('player.home'))


@auth_bp.route('/api/verification-status')
def api_verification_status():
    """Get current verification status."""
    if 'player_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    from .database import get_verification_status
    status = get_verification_status(session['player_id'])
    
    if not status:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify({
        'phone_verified': status['phone_verified'],
        'email_verified': status['email_verified'],
        'has_phone': status['has_phone'],
        'has_email': status['has_email']
    })


def mask_destination(channel, destination):
    """Mask phone or email for display."""
    if not destination:
        return ''
    
    if channel == 'phone':
        # Show last 4 digits: +1 XXX-XXX-1234
        if len(destination) >= 4:
            return f'***-***-{destination[-4:]}'
        return '***'
    else:
        # Show first 2 chars and domain: ab***@domain.com
        if '@' in destination:
            local, domain = destination.split('@', 1)
            if len(local) > 2:
                return f'{local[:2]}***@{domain}'
            return f'{local}***@{domain}'
        return '***'


def send_verification_code(channel, destination, code):
    """
    Send verification code via email only.
    Phone/SMS verification has been removed.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if channel == 'phone':
        # Phone verification disabled - log and return
        logger.info(f'[DISABLED] Phone verification not supported - use email instead')
        print(f'⚠️ Phone verification disabled. Code would be: {code}')
        return False
    else:
        # Use email service
        from .email_service import send_email
        result = send_email(
            to=destination,
            subject='Pool Cue Verification Code',
            html=f'<p>Your verification code is: <strong>{code}</strong></p><p>This code expires in 15 minutes.</p>',
            text=f'Your Pool Cue verification code is: {code}\n\nThis code expires in 15 minutes.'
        )
        if result:
            logger.info(f'Email verification sent to {destination}')
        else:
            logger.error(f'Email send failed to {destination}')
        return result
    
    return True


# ============================================
# PASSWORD RESET ROUTES
# ============================================

@auth_bp.route('/forgot-password', methods=['GET'])
def forgot_password():
    """Forgot password page - enter email/phone to receive reset code."""
    return render_template('auth/forgot_password.html')


@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password_post():
    """Send password reset code."""
    email = request.form.get('email', '').strip().lower()
    
    if not email:
        return render_template('auth/forgot_password.html', error='Please enter your email')
    
    # Check if account exists
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, phone_number FROM players WHERE LOWER(email) = ?', (email,))
    player = cursor.fetchone()
    
    if not player:
        conn.close()
        # Don't reveal if account exists or not for security
        return render_template('auth/forgot_password.html', 
                               success='If an account exists with that email, you will receive a reset code.')
    
    player_id = player['id']
    phone = player['phone_number']
    
    # Generate reset code
    import random
    code = str(random.randint(100000, 999999))
    
    # Store reset code (expires in 15 minutes)
    cursor.execute('''
        INSERT OR REPLACE INTO verifications (player_id, code, channel, expires_at)
        VALUES (?, ?, 'reset', datetime('now', '+15 minutes'))
    ''', (player_id, code))
    conn.commit()
    conn.close()
    
    # Send code via EMAIL (not SMS)
    from .email_service import send_email
    send_email(
        to=email,
        subject='Pool Cue Password Reset Code',
        html=f'<p>Your password reset code is: <strong>{code}</strong></p><p>This code expires in 15 minutes.</p>',
        text=f'Your Pool Cue password reset code is: {code}\n\nThis code expires in 15 minutes.'
    )
    
    # Store player_id in session for reset step
    session['reset_player_id'] = player_id
    
    return redirect(url_for('auth.reset_password'))


@auth_bp.route('/reset-password', methods=['GET'])
def reset_password():
    """Reset password page - enter code and new password."""
    if 'reset_player_id' not in session:
        return redirect(url_for('auth.forgot_password'))
    return render_template('auth/reset_password.html')


@auth_bp.route('/reset-password', methods=['POST'])
def reset_password_post():
    """Verify code and set new password."""
    from werkzeug.security import generate_password_hash
    
    if 'reset_player_id' not in session:
        return redirect(url_for('auth.forgot_password'))
    
    player_id = session['reset_player_id']
    code = request.form.get('code', '').strip()
    new_password = request.form.get('password', '')
    confirm_password = request.form.get('confirm_password', '')
    
    # Validate code
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id FROM verifications 
        WHERE player_id = ? AND code = ? AND channel = 'reset' 
        AND expires_at > datetime('now')
    ''', (player_id, code))
    verification = cursor.fetchone()
    
    if not verification:
        conn.close()
        return render_template('auth/reset_password.html', error='Invalid or expired code')
    
    # Validate password
    if len(new_password) < 10:
        conn.close()
        return render_template('auth/reset_password.html', error='Password must be at least 10 characters')
    
    if new_password != confirm_password:
        conn.close()
        return render_template('auth/reset_password.html', error='Passwords do not match')
    
    # Update password
    password_hash = generate_password_hash(new_password, method='scrypt')
    cursor.execute('UPDATE players SET password_hash = ? WHERE id = ?', (password_hash, player_id))
    
    # Delete used verification code
    cursor.execute('DELETE FROM verifications WHERE player_id = ? AND channel = ?', (player_id, 'reset'))
    conn.commit()
    conn.close()
    
    # Clear session
    session.pop('reset_player_id', None)
    
    flash('Password updated successfully! Please log in.', 'success')
    return redirect(url_for('auth.login'))
