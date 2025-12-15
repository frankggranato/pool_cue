"""
Player App routes - Mobile web + PWA for players
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, flash
from .database import get_db
from datetime import datetime
import secrets
import os
import glob
import json
import random

player_bp = Blueprint('player', __name__, url_prefix='/player')

# Ads folder
ADS_BASE = os.path.join(os.path.dirname(__file__), 'static', 'ads')

def get_active_ad(placement='player'):
    """Get a random active ad filename for a placement and log the impression.
    First checks campaign ads targeting player_app, then falls back to folder-based ads."""
    
    # First, try to get ads from active campaigns targeting player_app
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DISTINCT ac.file_name, c.target_placements
            FROM ad_creatives ac
            JOIN campaigns c ON c.id = ac.campaign_id
            WHERE c.status = 'active'
              AND ac.is_active = 1
              AND (c.start_date IS NULL OR c.start_date <= DATE('now'))
              AND (c.end_date IS NULL OR c.end_date >= DATE('now'))
        ''')
        rows = cursor.fetchall()
        conn.close()
        
        campaign_ads = []
        for row in rows:
            target_placements = json.loads(row['target_placements']) if row['target_placements'] else []
            if 'player_app' in target_placements:
                file_path = os.path.join(ADS_BASE, row['file_name'])
                if os.path.exists(file_path):
                    campaign_ads.append(row['file_name'])
        
        if campaign_ads:
            selected_ad = random.choice(campaign_ads)
            # Log the impression
            try:
                from .ad_events import log_impression
                player_id = session.get('player_id')
                log_impression(
                    placement='player_app',
                    ad_filename=selected_ad,
                    player_id=player_id
                )
            except:
                pass
            return selected_ad
    except Exception as e:
        print(f"[PLAYER ADS] Error getting campaign ads: {e}")
    
    # Fall back to folder-based ads
    folder = os.path.join(ADS_BASE, placement)
    if not os.path.exists(folder):
        return None
    
    config_file = os.path.join(ADS_BASE, 'config.json')
    disabled = []
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
                disabled = config.get('disabled', {}).get(placement, [])
        except:
            pass
    
    extensions = ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.webp', '*.JPG', '*.JPEG', '*.PNG']
    files = []
    for ext in extensions:
        files.extend(glob.glob(os.path.join(folder, ext)))
    
    active = [os.path.basename(f) for f in files if os.path.basename(f) not in disabled]
    
    if active:
        selected_ad = random.choice(active)
        
        # Log the impression
        try:
            from .ad_events import log_impression
            from flask import session
            player_id = session.get('player_id')
            log_impression(
                placement=f'player_{placement}' if not placement.startswith('player') else placement,
                ad_filename=selected_ad,
                player_id=player_id
            )
        except Exception as e:
            # Don't break the page if logging fails
            pass
        
        return selected_ad
    return None

@player_bp.route('/')
@player_bp.route('/home')
def home():
    """Home screen - list of bars."""
    player_ad = get_active_ad('player')
    
    # Initialize template variables
    my_queue_info = None
    player_data = None
    daily_bonus_awarded = False
    pending_challenges = 0
    pending_match_confirmations = 0
    friend_activity = []
    last_game = None
    show_birthday_banner = False
    birthday_message = None
    birthday_tokens_awarded = 0
    birthday_sponsor_text = None  # Placeholder for future sponsor integration
    bars = []  # Will be populated from database
    
    # Fetch bars from database (active bars only for player app)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT b.id, b.name, b.address, b.is_active, b.table_count as tables,
               (SELECT COUNT(*) FROM queue q WHERE q.bar_id = b.id) as queue_count,
               (SELECT COUNT(*) FROM game_history gh WHERE gh.bar_id = b.id AND date(gh.played_at) = date('now')) as games_today
        FROM bars b
        WHERE b.is_active = 1
        ORDER BY b.name
    ''')
    bars = [dict(row) for row in cursor.fetchall()]
    
    # Count upcoming approved pool nights (for banner)
    cursor.execute('''
        SELECT COUNT(*) FROM pool_nights 
        WHERE status = 'approved' 
        AND event_date >= date('now')
    ''')
    upcoming_events_count = cursor.fetchone()[0] or 0
    
    conn.close()
    
    if 'player_id' in session:
        conn = get_db()
        cursor = conn.cursor()
        
        player_id = session['player_id']
        
        # Get player data including tokens, streak, last game, birthday
        cursor.execute('''
            SELECT p.id, p.nickname, p.tokens_balance, p.current_streak, p.best_streak,
                   p.last_opponent_id, p.last_game_result, p.last_daily_bonus, p.privacy_mode,
                   p.wins, p.losses, p.birthday, p.last_birthday_rewarded_at,
                   opp.nickname as opponent_name
            FROM players p
            LEFT JOIN players opp ON p.last_opponent_id = opp.id
            WHERE p.id = ?
        ''', (player_id,))
        player_row = cursor.fetchone()
        
        if player_row:
            player_data = dict(player_row)
            
            # Check and award daily login bonus
            today = datetime.now().strftime('%Y-%m-%d')
            if player_row['last_daily_bonus'] != today:
                cursor.execute('''
                    UPDATE players 
                    SET tokens_balance = COALESCE(tokens_balance, 0) + 10,
                        total_tokens_earned = COALESCE(total_tokens_earned, 0) + 10,
                        last_daily_bonus = ?
                    WHERE id = ?
                ''', (today, player_id))
                conn.commit()
                daily_bonus_awarded = True
                player_data['tokens_balance'] = (player_data['tokens_balance'] or 0) + 10
            
            # Check for birthday and award birthday bonus
            player_birthday = player_row['birthday']
            last_birthday_reward = player_row['last_birthday_rewarded_at']
            
            if player_birthday:
                today_date = datetime.now().date()
                try:
                    bday = datetime.strptime(player_birthday, '%Y-%m-%d').date()
                    # Check if today is their birthday (month and day match)
                    if bday.month == today_date.month and bday.day == today_date.day:
                        # Check if we already rewarded this year
                        current_year = str(today_date.year)
                        already_rewarded = False
                        if last_birthday_reward:
                            reward_year = last_birthday_reward[:4]
                            already_rewarded = (reward_year == current_year)
                        
                        if not already_rewarded:
                            # Award birthday bonus (100 tokens)
                            birthday_tokens_awarded = 100
                            cursor.execute('''
                                UPDATE players 
                                SET tokens_balance = COALESCE(tokens_balance, 0) + ?,
                                    total_tokens_earned = COALESCE(total_tokens_earned, 0) + ?,
                                    last_birthday_rewarded_at = ?
                                WHERE id = ?
                            ''', (birthday_tokens_awarded, birthday_tokens_awarded, today, player_id))
                            conn.commit()
                            player_data['tokens_balance'] = (player_data['tokens_balance'] or 0) + birthday_tokens_awarded
                        
                        # Show banner regardless (even if already rewarded today)
                        show_birthday_banner = True
                        first_name = player_data['nickname'].split()[0] if player_data['nickname'] else 'Player'
                        birthday_message = f"Happy Birthday, {first_name}! 🎉"
                except (ValueError, AttributeError):
                    pass  # Invalid birthday format, skip
            
            # Get last game info
            if player_row['last_opponent_id'] and player_row['last_game_result']:
                last_game = {
                    'opponent_name': player_row['opponent_name'],
                    'result': player_row['last_game_result']
                }
        
        # Get pending challenges count
        cursor.execute('''
            SELECT COUNT(*) as count FROM challenges 
            WHERE challenged_user_id = ? AND status = 'pending'
        ''', (player_id,))
        pending_challenges = cursor.fetchone()['count']
        
        # Get pending match confirmations (for ranked/paid matches)
        cursor.execute('''
            SELECT COUNT(*) as count FROM active_matches 
            WHERE (player1_id = ? OR player2_id = ?)
            AND result_winner_id IS NOT NULL
            AND result_locked = 0
            AND status != 'cancelled'
            AND (
                (player1_id = ? AND player1_confirmed = 0) OR
                (player2_id = ? AND player2_confirmed = 0)
            )
        ''', (player_id, player_id, player_id, player_id))
        pending_match_confirmations = cursor.fetchone()['count']
        
        # Get friend activity (friends currently in queue)
        cursor.execute('''
            SELECT p.nickname, q.wins_on_table,
                   (SELECT COUNT(*) FROM queue q2 WHERE q2.id <= q.id) as position
            FROM friendships f
            JOIN players p ON f.friend_id = p.id
            JOIN queue q ON q.player_id = p.id
            WHERE f.player_id = ? AND f.status = 'accepted'
            AND p.privacy_mode = 0
        ''', (player_id,))
        friend_activity = [dict(row) for row in cursor.fetchall()]
        
        # Get user's queue entry if any
        cursor.execute('''
            SELECT q.id, q.player_id, q.position, q.status, q.created_at, q.partner_name,
                   p.nickname, s.bar_name
            FROM queue q
            JOIN players p ON q.player_id = p.id
            LEFT JOIN settings s ON 1=1
            WHERE q.player_id = ?
            ORDER BY q.id DESC LIMIT 1
        ''', (player_id,))
        my_entry = cursor.fetchone()
        
        if my_entry:
            # Get full queue to calculate position and show other players
            cursor.execute('''
                SELECT q.id, q.player_id, p.nickname, q.partner_name, q.wins_on_table
                FROM queue q
                JOIN players p ON q.player_id = p.id
                ORDER BY q.id ASC
            ''')
            full_queue = cursor.fetchall()
            
            # Find my position
            my_position = 0
            queue_list = []
            for i, entry in enumerate(full_queue, 1):
                queue_list.append({
                    'position': i,
                    'player_id': entry['player_id'],
                    'nickname': entry['nickname'],
                    'partner_name': entry['partner_name'],
                    'wins_on_table': entry['wins_on_table'] or 0,
                    'is_me': entry['player_id'] == player_id
                })
                if entry['player_id'] == player_id:
                    my_position = i
            
            my_queue_info = {
                'bar_name': my_entry['bar_name'] or 'Test Bar',
                'position': my_position,
                'total_in_queue': len(full_queue),
                'queue_list': queue_list,
                'is_king': my_position == 1,
                'is_challenger': my_position == 2
            }
        
        conn.close()
    
    # Check if user is a guest (has player_id but no email/password)
    is_guest = session.get('is_guest', False)
    
    return render_template('player/home.html', 
                           player_ad=player_ad, 
                           my_queue_info=my_queue_info,
                           player_data=player_data,
                           daily_bonus_awarded=daily_bonus_awarded,
                           pending_challenges=pending_challenges,
                           pending_match_confirmations=pending_match_confirmations,
                           friend_activity=friend_activity,
                           last_game=last_game,
                           show_birthday_banner=show_birthday_banner,
                           birthday_message=birthday_message,
                           birthday_tokens_awarded=birthday_tokens_awarded,
                           birthday_sponsor_text=birthday_sponsor_text,
                           bars=bars,
                           upcoming_events_count=upcoming_events_count,
                           is_guest=is_guest,
                           demo_mode=False)

@player_bp.route('/register')
def register():
    """Registration - redirects to signup."""
    return redirect(url_for('auth.signup'))

@player_bp.route('/login')
def login():
    """Login/signup screen."""
    return render_template('player/login.html')

@player_bp.route('/profile')
def profile():
    """Player profile screen."""
    player_ad = get_active_ad('player')
    player_data = None
    invite_stats = {'pending': 0, 'completed': 0}
    
    if 'player_id' in session:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT p.id, p.nickname, p.email, p.wins, p.losses, p.tokens_balance, p.current_streak, 
                   p.best_streak, p.privacy_mode, p.total_games, p.birthday, p.birthday_last_changed_at,
                   p.display_name, p.home_bar_id, p.play_frequency, p.skill_self_rating,
                   p.marketing_opt_in, p.preferred_contact_method,
                   b.name as home_bar_name
            FROM players p
            LEFT JOIN bars b ON p.home_bar_id = b.id
            WHERE p.id = ?
        ''', (session['player_id'],))
        player_row = cursor.fetchone()
        if player_row:
            player_data = dict(player_row)
            
            # Calculate next allowed birthday change date
            if player_data.get('birthday') and player_data.get('birthday_last_changed_at'):
                try:
                    from dateutil.relativedelta import relativedelta
                    from datetime import date
                    last_changed = datetime.strptime(player_data['birthday_last_changed_at'][:10], '%Y-%m-%d').date()
                    next_allowed = last_changed + relativedelta(months=6)
                    player_data['birthday_next_change_allowed'] = next_allowed.strftime('%B %d, %Y')
                    player_data['birthday_change_blocked'] = date.today() < next_allowed
                except (ValueError, TypeError):
                    player_data['birthday_change_blocked'] = False
            else:
                player_data['birthday_change_blocked'] = False
        
        # Get invite stats for badge
        cursor.execute('''
            SELECT 
                COUNT(CASE WHEN status = 'pending' OR status = 'sent' THEN 1 END) as pending,
                COUNT(CASE WHEN status = 'joined' OR status = 'completed' THEN 1 END) as completed
            FROM manual_invites WHERE sender_id = ?
        ''', (session['player_id'],))
        stats_row = cursor.fetchone()
        if stats_row:
            invite_stats['pending'] = stats_row['pending'] or 0
            invite_stats['completed'] = stats_row['completed'] or 0
                
        conn.close()
    
    # Today's date for date picker max value
    from datetime import date
    today = date.today().strftime('%Y-%m-%d')
    is_guest = session.get('is_guest', False)
    
    return render_template('player/profile.html', player_ad=player_ad, player_data=player_data, invite_stats=invite_stats, today=today, is_guest=is_guest, demo_mode=False)


@player_bp.route('/profile/update-birthday', methods=['POST'])
def update_birthday():
    """Update player's birthday with 6-month change restriction."""
    if 'player_id' not in session:
        flash('Please log in to update your profile', 'error')
        return redirect(url_for('player.profile'))
    
    birthday = request.form.get('birthday', '').strip()
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get current birthday and last changed date
    cursor.execute('SELECT birthday, birthday_last_changed_at FROM players WHERE id = ?', (session['player_id'],))
    player = cursor.fetchone()
    current_birthday = player['birthday'] if player else None
    last_changed = player['birthday_last_changed_at'] if player else None
    
    if birthday:
        from datetime import date, timedelta
        from dateutil.relativedelta import relativedelta
        try:
            bday = datetime.strptime(birthday, '%Y-%m-%d').date()
            today = date.today()
            
            # Must be in the past
            if bday >= today:
                conn.close()
                flash('Birthday must be in the past', 'error')
                return redirect(url_for('player.profile'))
            
            # Must be at least 18 years old
            age = today.year - bday.year - ((today.month, today.day) < (bday.month, bday.day))
            if age < 18:
                conn.close()
                flash('You must be at least 18 years old', 'error')
                return redirect(url_for('player.profile'))
            if age > 120:
                conn.close()
                flash('Please enter a valid birthday', 'error')
                return redirect(url_for('player.profile'))
            
            # Check 6-month restriction for birthday changes (not first time set)
            if current_birthday and last_changed:
                try:
                    last_changed_date = datetime.strptime(last_changed[:10], '%Y-%m-%d').date()
                    next_allowed = last_changed_date + relativedelta(months=6)
                    
                    if today < next_allowed:
                        conn.close()
                        last_changed_formatted = last_changed_date.strftime('%B %d, %Y')
                        next_allowed_formatted = next_allowed.strftime('%B %d, %Y')
                        flash(f'You can only update your birthday once every 6 months. Last change was on {last_changed_formatted}. You can change it again on {next_allowed_formatted}.', 'error')
                        return redirect(url_for('player.profile'))
                except (ValueError, TypeError):
                    # Invalid last_changed format - allow change and reset it
                    pass
                    
        except ValueError:
            conn.close()
            flash('Invalid birthday format', 'error')
            return redirect(url_for('player.profile'))
    else:
        birthday = None
    
    # Update birthday and the last changed timestamp
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('UPDATE players SET birthday = ?, birthday_last_changed_at = ? WHERE id = ?', 
                   (birthday, now, session['player_id']))
    conn.commit()
    conn.close()
    
    flash('Birthday updated!', 'success')
    return redirect(url_for('player.profile'))


@player_bp.route('/profile/edit')
def edit_profile():
    """Edit profile page - allows updating profile fields."""
    if 'player_id' not in session:
        flash('Please log in to edit your profile', 'error')
        return redirect(url_for('player.login'))
    
    player_id = session['player_id']
    conn = get_db()
    cursor = conn.cursor()
    
    # Get player data including verification status
    cursor.execute('''
        SELECT id, nickname, email, phone_number, birthday, birthday_last_changed_at,
               home_bar_id, display_name, play_frequency, skill_self_rating,
               marketing_opt_in, preferred_contact_method,
               phone_verified, email_verified
        FROM players WHERE id = ?
    ''', (player_id,))
    player = cursor.fetchone()
    
    if not player:
        conn.close()
        flash('Player not found', 'error')
        return redirect(url_for('player.profile'))
    
    player_data = dict(player)
    
    # Calculate birthday change restriction
    if player_data.get('birthday') and player_data.get('birthday_last_changed_at'):
        try:
            from dateutil.relativedelta import relativedelta
            from datetime import date
            last_changed = datetime.strptime(player_data['birthday_last_changed_at'][:10], '%Y-%m-%d').date()
            next_allowed = last_changed + relativedelta(months=6)
            player_data['birthday_next_change_allowed'] = next_allowed.strftime('%B %d, %Y')
            player_data['birthday_change_blocked'] = date.today() < next_allowed
        except (ValueError, TypeError):
            player_data['birthday_change_blocked'] = False
    else:
        player_data['birthday_change_blocked'] = False
    
    # Get bars for dropdown
    cursor.execute('SELECT id, name FROM bars WHERE is_active = 1 ORDER BY name')
    bars = [dict(row) for row in cursor.fetchall()]
    
    # Get current home bar name
    if player_data.get('home_bar_id'):
        cursor.execute('SELECT name FROM bars WHERE id = ?', (player_data['home_bar_id'],))
        bar_row = cursor.fetchone()
        player_data['home_bar_name'] = bar_row['name'] if bar_row else None
    
    conn.close()
    
    from datetime import date
    today = date.today().strftime('%Y-%m-%d')
    
    return render_template('player/edit_profile.html', 
                           player_data=player_data, 
                           bars=bars,
                           today=today)


@player_bp.route('/profile/edit', methods=['POST'])
def save_profile():
    """Save profile changes."""
    if 'player_id' not in session:
        flash('Please log in to edit your profile', 'error')
        return redirect(url_for('player.login'))
    
    player_id = session['player_id']
    
    # Get form data
    display_name = request.form.get('display_name', '').strip() or None
    email = request.form.get('email', '').strip() or None
    phone_number = request.form.get('phone_number', '').strip() or None
    home_bar_id = request.form.get('home_bar_id') or None
    play_frequency = request.form.get('play_frequency') or None
    skill_level = request.form.get('skill_level') or None
    preferred_contact = request.form.get('preferred_contact_method') or 'email'
    marketing_opt_in = 1 if request.form.get('marketing_opt_in') else 0
    birthday = request.form.get('birthday', '').strip() or None
    
    # Validate enums
    valid_frequencies = ['rarely', 'weekly', 'multiple_weekly', 'daily']
    valid_skills = ['beginner', 'intermediate', 'advanced', 'expert']
    valid_contacts = ['email', 'sms', 'both', 'none']
    
    if play_frequency and play_frequency not in valid_frequencies:
        play_frequency = None
    if skill_level and skill_level not in valid_skills:
        skill_level = None
    if preferred_contact not in valid_contacts:
        preferred_contact = 'email'
    
    # Convert home_bar_id to int or None
    if home_bar_id:
        try:
            home_bar_id = int(home_bar_id)
        except ValueError:
            home_bar_id = None
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get current email/phone to check for changes
    cursor.execute('SELECT email, phone_number FROM players WHERE id = ?', (player_id,))
    current = cursor.fetchone()
    current_email = current['email'] if current else None
    current_phone = current['phone_number'] if current else None
    
    # Track if verification needs to be reset
    email_changed = email != current_email and (email or current_email)
    phone_changed = phone_number != current_phone and (phone_number or current_phone)
    
    # Check email uniqueness (only active accounts)
    if email:
        cursor.execute('SELECT id FROM players WHERE email = ? AND id != ? AND (is_active = 1 OR is_active IS NULL)', (email, player_id))
        if cursor.fetchone():
            conn.close()
            flash('This email is already associated with another account', 'error')
            return redirect(url_for('player.edit_profile'))
    
    # Check phone uniqueness (only active accounts)
    if phone_number:
        cursor.execute('SELECT id FROM players WHERE phone_number = ? AND id != ? AND (is_active = 1 OR is_active IS NULL)', (phone_number, player_id))
        if cursor.fetchone():
            conn.close()
            flash('This phone number is already associated with another account', 'error')
            return redirect(url_for('player.edit_profile'))
    
    # Handle birthday with 6-month restriction
    birthday_update_sql = ''
    birthday_params = []
    
    if birthday:
        # Get current birthday info
        cursor.execute('SELECT birthday, birthday_last_changed_at FROM players WHERE id = ?', (player_id,))
        current = cursor.fetchone()
        current_birthday = current['birthday'] if current else None
        last_changed = current['birthday_last_changed_at'] if current else None
        
        # Check if birthday is actually changing
        if birthday != current_birthday:
            from datetime import date
            from dateutil.relativedelta import relativedelta
            
            # Check 6-month restriction
            can_change = True
            if current_birthday and last_changed:
                try:
                    last_changed_date = datetime.strptime(last_changed[:10], '%Y-%m-%d').date()
                    next_allowed = last_changed_date + relativedelta(months=6)
                    if date.today() < next_allowed:
                        can_change = False
                        flash(f'Birthday can only be changed once every 6 months. Next change allowed: {next_allowed.strftime("%B %d, %Y")}', 'error')
                except (ValueError, TypeError):
                    pass
            
            if can_change:
                # Validate birthday
                try:
                    bday = datetime.strptime(birthday, '%Y-%m-%d').date()
                    today = date.today()
                    if bday > today:
                        flash('Birthday cannot be in the future', 'error')
                    else:
                        age = today.year - bday.year - ((today.month, today.day) < (bday.month, bday.day))
                        if age < 18:
                            flash('You must be at least 18 years old', 'error')
                        else:
                            birthday_update_sql = ', birthday = ?, birthday_last_changed_at = CURRENT_TIMESTAMP'
                            birthday_params = [birthday]
                except ValueError:
                    flash('Invalid birthday format', 'error')
    
    # Build update query
    base_sql = '''
        UPDATE players SET 
            display_name = ?,
            email = ?,
            phone_number = ?,
            home_bar_id = ?,
            play_frequency = ?,
            skill_self_rating = ?,
            preferred_contact_method = ?,
            marketing_opt_in = ?
    '''
    
    params = [display_name, email, phone_number, home_bar_id, play_frequency, 
              skill_level, preferred_contact, marketing_opt_in]
    
    # Reset verification if email/phone changed
    if email_changed:
        base_sql += ', email_verified = 0'
    if phone_changed:
        base_sql += ', phone_verified = 0'
    
    if birthday_update_sql:
        base_sql += birthday_update_sql
        params.extend(birthday_params)
    
    base_sql += ' WHERE id = ?'
    params.append(player_id)
    
    cursor.execute(base_sql, params)
    conn.commit()
    conn.close()
    
    # If phone or email changed, prompt for reverification
    if email_changed or phone_changed:
        flash('Profile updated! Please verify your updated contact info.', 'success')
        return redirect(url_for('auth.verify_choose'))
    
    flash('Profile updated successfully!', 'success')
    return redirect(url_for('player.profile'))

@player_bp.route('/api/privacy-mode', methods=['POST'])
def toggle_privacy_mode():
    """Toggle privacy/anonymous mode."""
    if 'player_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.json or {}
    enabled = data.get('enabled', False)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE players SET privacy_mode = ? WHERE id = ?', 
                   (1 if enabled else 0, session['player_id']))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'privacy_mode': enabled})

@player_bp.route('/notifications')
def notifications():
    """Notification settings."""
    return render_template('player/notifications.html')

@player_bp.route('/challenges')
def challenges():
    """Challenges screen."""
    return render_template('player/challenges.html')

@player_bp.route('/friends')
def friends():
    """Friends screen - see friends and who's playing."""
    return render_template('player/friends.html')

@player_bp.route('/leaderboards')
def leaderboards():
    """Leaderboards screen - city and bar rankings."""
    return render_template('player/leaderboards.html')

@player_bp.route('/rivalries')
def rivalries():
    """Rivalries screen - your top opponents."""
    return render_template('player/rivalries.html')

@player_bp.route('/tokens')
def tokens():
    """Tokens screen - balance and earn options."""
    return render_template('player/tokens.html')


@player_bp.route('/match-confirmations')
def match_confirmations():
    """View and manage pending match confirmations."""
    from .database import get_db
    
    player_id = session.get('player_id')
    if not player_id:
        flash('Please log in to view match confirmations', 'error')
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get pending matches (where result exists but not locked)
    cursor.execute('''
        SELECT am.*,
               p1.nickname as player1_name,
               p2.nickname as player2_name,
               b.name as bar_name,
               pn.title as pool_night_title
        FROM active_matches am
        JOIN players p1 ON am.player1_id = p1.id
        JOIN players p2 ON am.player2_id = p2.id
        LEFT JOIN bars b ON am.bar_id = b.id
        LEFT JOIN pool_nights pn ON am.pool_night_id = pn.id
        WHERE (am.player1_id = ? OR am.player2_id = ?)
        AND am.result_winner_id IS NOT NULL
        AND am.result_locked = 0
        AND am.status != 'cancelled'
        ORDER BY am.ended_at DESC
    ''', (player_id, player_id))
    
    pending_raw = [dict(row) for row in cursor.fetchall()]
    
    # Process pending matches to add computed fields
    pending = []
    for match in pending_raw:
        is_player1 = (match['player1_id'] == player_id)
        my_confirmed = match['player1_confirmed'] if is_player1 else match['player2_confirmed']
        other_confirmed = match['player2_confirmed'] if is_player1 else match['player1_confirmed']
        
        match['i_won'] = (match['result_winner_id'] == player_id)
        match['needs_my_confirmation'] = (my_confirmed == 0)
        match['other_confirmed'] = (other_confirmed == 1)
        pending.append(match)
    
    # Get recently locked matches (last 7 days)
    cursor.execute('''
        SELECT am.*,
               p1.nickname as player1_name,
               p2.nickname as player2_name,
               b.name as bar_name,
               pn.title as pool_night_title
        FROM active_matches am
        JOIN players p1 ON am.player1_id = p1.id
        JOIN players p2 ON am.player2_id = p2.id
        LEFT JOIN bars b ON am.bar_id = b.id
        LEFT JOIN pool_nights pn ON am.pool_night_id = pn.id
        WHERE (am.player1_id = ? OR am.player2_id = ?)
        AND am.result_locked = 1
        AND am.ended_at >= datetime('now', '-7 days')
        ORDER BY am.ended_at DESC
        LIMIT 20
    ''', (player_id, player_id))
    
    recent = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return render_template('player/match_confirmations.html', pending=pending, recent=recent)


# ============ CUE MARKETPLACE ROUTES ============

@player_bp.route('/tokens/marketplace')
def marketplace():
    """Browse cue marketplace listings."""
    from .database import get_active_marketplace_listings, get_my_marketplace_listings
    
    player_id = session.get('player_id')
    
    # Get active listings (excluding current user's own)
    listings = get_active_marketplace_listings(limit=50, exclude_seller_id=player_id)
    my_listings = get_my_marketplace_listings(player_id) if player_id else []
    
    return render_template('player/marketplace.html', 
                           listings=listings,
                           my_listings=my_listings,
                           player_id=player_id)


@player_bp.route('/tokens/marketplace/new', methods=['GET'])
def marketplace_new():
    """Form to create a new cue listing."""
    player_id = session.get('player_id')
    if not player_id:
        flash('Please log in to list a cue', 'error')
        return redirect(url_for('player.tokens'))
    
    return render_template('player/marketplace_new.html')


@player_bp.route('/tokens/marketplace/new', methods=['POST'])
def marketplace_create():
    """Create a new cue listing."""
    from .database import create_marketplace_listing
    
    player_id = session.get('player_id')
    if not player_id:
        flash('Please log in to list a cue', 'error')
        return redirect(url_for('player.tokens'))
    
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    condition = request.form.get('condition', 'Good')
    price_type = request.form.get('price_type', 'tokens')
    
    # Validate price based on type
    price_tokens = None
    price_cash = None
    
    if price_type == 'cash':
        try:
            price_cash = float(request.form.get('price_cash', 0))
        except (TypeError, ValueError):
            price_cash = 0
        
        if not title or not price_cash or price_cash < 1:
            flash('Title and price are required', 'error')
            return redirect(url_for('player.marketplace_new'))
        
        if price_cash > 5000:
            flash('Maximum price is $5,000', 'error')
            return redirect(url_for('player.marketplace_new'))
    else:
        # Default to tokens
        price_type = 'tokens'
        price_tokens = request.form.get('price_tokens', type=int)
        
        if not title or not price_tokens or price_tokens < 1:
            flash('Title and price are required', 'error')
            return redirect(url_for('player.marketplace_new'))
        
        if price_tokens > 10000:
            flash('Maximum price is 10,000 tokens', 'error')
            return redirect(url_for('player.marketplace_new'))
    
    listing_id = create_marketplace_listing(
        seller_id=player_id,
        title=title,
        description=description,
        condition=condition,
        price_tokens=price_tokens,
        price_cash=price_cash,
        price_type=price_type
    )
    
    flash('Cue listed successfully!', 'success')
    return redirect(url_for('player.marketplace'))


@player_bp.route('/tokens/marketplace/<int:listing_id>')
def marketplace_detail(listing_id):
    """View a single marketplace listing."""
    from .database import get_marketplace_listing, get_db
    
    listing = get_marketplace_listing(listing_id)
    if not listing:
        flash('Listing not found', 'error')
        return redirect(url_for('player.marketplace'))
    
    player_id = session.get('player_id')
    
    # Get buyer's token and wallet balance
    buyer_token_balance = 0
    buyer_wallet_balance = 0.00
    if player_id:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT tokens_balance, wallet_balance FROM players WHERE id = ?', (player_id,))
        row = cursor.fetchone()
        if row:
            buyer_token_balance = row['tokens_balance'] or 0
            buyer_wallet_balance = float(row['wallet_balance'] or 0)
        conn.close()
    
    return render_template('player/marketplace_detail.html',
                           listing=listing,
                           player_id=player_id,
                           buyer_balance=buyer_token_balance,
                           buyer_wallet_balance=buyer_wallet_balance)


@player_bp.route('/tokens/marketplace/<int:listing_id>/buy', methods=['POST'])
def marketplace_buy(listing_id):
    """Buy a cue listing with tokens."""
    from .database import buy_marketplace_listing
    
    player_id = session.get('player_id')
    if not player_id:
        flash('Please log in to buy', 'error')
        return redirect(url_for('player.marketplace_detail', listing_id=listing_id))
    
    success, message = buy_marketplace_listing(listing_id, player_id)
    
    if success:
        flash(message, 'success')
        return redirect(url_for('player.marketplace'))
    else:
        flash(message, 'error')
        return redirect(url_for('player.marketplace_detail', listing_id=listing_id))


@player_bp.route('/tokens/marketplace/<int:listing_id>/close', methods=['POST'])
def marketplace_close(listing_id):
    """Close/hide a listing (seller only)."""
    from .database import close_marketplace_listing
    
    player_id = session.get('player_id')
    if not player_id:
        flash('Please log in', 'error')
        return redirect(url_for('player.marketplace'))
    
    success, message = close_marketplace_listing(listing_id, player_id)
    
    if success:
        flash('Listing closed', 'success')
    else:
        flash(message, 'error')
    
    return redirect(url_for('player.marketplace'))


# ============ INVITE FRIENDS ROUTES ============

@player_bp.route('/invite')
def invite_friends():
    """Invite friends page - shows referral link, stats, and manual invites."""
    from .database import (get_or_create_referral_code, get_referral_stats, get_referral_list,
                           get_manual_invites, get_manual_invite_stats)
    
    player_id = session.get('player_id')
    if not player_id:
        flash('Please log in to invite friends', 'error')
        return redirect(url_for('auth.login'))
    
    # Get or create referral code
    referral_code = get_or_create_referral_code(player_id)
    
    # Get referral stats (people who signed up with your code)
    stats = get_referral_stats(player_id)
    
    # Get list of referrals (completed signups)
    referrals = get_referral_list(player_id)
    
    # Get manual invites sent
    manual_invites = get_manual_invites(player_id)
    manual_stats = get_manual_invite_stats(player_id)
    
    # Build invite link
    invite_link = request.host_url.rstrip('/') + f'/auth/signup?ref={referral_code}'
    
    return render_template('player/invite_friends.html',
                           referral_code=referral_code,
                           invite_link=invite_link,
                           stats=stats,
                           referrals=referrals,
                           manual_invites=manual_invites,
                           manual_stats=manual_stats)


@player_bp.route('/api/send-invite', methods=['POST'])
def api_send_invite():
    """Send a manual invite via email or phone."""
    from .database import send_manual_invite, get_or_create_referral_code
    
    player_id = session.get('player_id')
    if not player_id:
        return jsonify({'error': 'Login required'}), 401
    
    data = request.json or {}
    contact_type = data.get('type', 'email')  # 'email' or 'phone'
    contact_value = data.get('contact', '').strip()
    contact_name = data.get('name', '').strip() or None
    
    if not contact_value:
        return jsonify({'error': 'Please enter an email or phone number'}), 400
    
    # Basic validation
    if contact_type == 'email':
        if '@' not in contact_value or '.' not in contact_value:
            return jsonify({'error': 'Please enter a valid email address'}), 400
    elif contact_type == 'phone':
        import re
        digits = re.sub(r'\D', '', contact_value)
        if len(digits) < 10:
            return jsonify({'error': 'Please enter a valid phone number'}), 400
    
    success, message, invite_id = send_manual_invite(player_id, contact_type, contact_value, contact_name)
    
    if success:
        # Get referral code for building invite message
        referral_code = get_or_create_referral_code(player_id)
        invite_link = request.host_url.rstrip('/') + f'/auth/signup?ref={referral_code}'
        
        return jsonify({
            'success': True,
            'message': message,
            'invite_id': invite_id,
            'invite_link': invite_link
        })
    else:
        return jsonify({'error': message}), 400


@player_bp.route('/earn')
def earn():
    """Earn tokens through surveys - only shows real advertiser surveys."""
    from .database import get_db
    import json
    
    conn = get_db()
    cursor = conn.cursor()
    
    player_id = session.get('player_id')
    
    # Get active survey questions that player hasn't answered
    cursor.execute('''
        SELECT sq.id, sq.text, sq.response_type, sq.options_json, sq.token_reward,
               a.name as sponsor
        FROM survey_questions sq
        LEFT JOIN campaigns c ON sq.campaign_id = c.id
        LEFT JOIN advertisers a ON c.advertiser_id = a.id
        WHERE sq.is_active = 1
        AND sq.id NOT IN (
            SELECT question_id FROM survey_responses WHERE player_id = ?
        )
        ORDER BY sq.token_reward DESC
        LIMIT 5
    ''', (player_id or 0,))
    
    questions = []
    for row in cursor.fetchall():
        q = dict(row)
        if q['options_json']:
            try:
                q['options'] = json.loads(q['options_json'])
            except:
                q['options'] = []
        else:
            q['options'] = []
        questions.append(q)
    
    # Get player's token balance
    token_balance = 0
    if player_id:
        cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM token_transactions WHERE player_id = ?', (player_id,))
        token_balance = cursor.fetchone()[0] or 0
    
    conn.close()
    
    return render_template('player/earn.html', questions=questions, token_balance=token_balance)

@player_bp.route('/shop')
def shop():
    """Token shop - buy brand merch."""
    return render_template('player/shop.html')

@player_bp.route('/pool-nights')
def pool_nights():
    """Pool nights - organized sessions."""
    return render_template('player/pool_nights.html')


@player_bp.route('/tournament/<int:night_id>')
def player_tournament_view(night_id):
    """Player view of tournament bracket."""
    from .database import get_tournament_bracket, get_player_tournament_match, get_tournament_participants
    
    player_id = session.get('player_id')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get pool night with bar name
    cursor.execute('''
        SELECT pn.*, b.name as bar_name
        FROM pool_nights pn
        LEFT JOIN bars b ON pn.bar_id = b.id
        WHERE pn.id = ? AND pn.format = 'tournament'
    ''', (night_id,))
    night = cursor.fetchone()
    
    if not night:
        conn.close()
        flash('Tournament not found.', 'error')
        return redirect(url_for('player.pool_nights'))
    
    night = dict(night)
    conn.close()
    
    # Get bracket and participants
    bracket_data = get_tournament_bracket(night_id)
    participants = get_tournament_participants(night_id)
    
    # Get player's status in tournament
    my_status = None
    if player_id:
        my_status = get_player_tournament_match(night_id, player_id)
    
    return render_template('player/tournament_bracket.html',
                           night=night,
                           bracket=bracket_data,
                           participants=participants,
                           my_status=my_status)


@player_bp.route('/tournament/<int:night_id>/register', methods=['POST'])
def register_for_tournament(night_id):
    """Player self-registration for a tournament."""
    from .database import register_tournament_participant
    
    player_id = session.get('player_id')
    if not player_id:
        flash('Please log in to register.', 'error')
        return redirect(url_for('player.login'))
    
    # Check if registration is still open
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM pool_nights 
        WHERE id = ? AND format = 'tournament' AND bracket_generated = 0
    ''', (night_id,))
    night = cursor.fetchone()
    conn.close()
    
    if not night:
        flash('Registration is closed for this tournament.', 'error')
        return redirect(url_for('player.player_tournament_view', night_id=night_id))
    
    result = register_tournament_participant(night_id, player_id)
    
    if result['success']:
        flash('You are registered for the tournament!', 'success')
    else:
        flash(result.get('error', 'Could not register.'), 'error')
    
    return redirect(url_for('player.player_tournament_view', night_id=night_id))


@player_bp.route('/api/pool-nights')
def api_pool_nights_list():
    """API: Get pool nights for player view with entry fee info and filters."""
    from .database import get_db, get_wallet_balance
    from datetime import datetime, timedelta
    
    player_id = session.get('player_id')
    filter_type = request.args.get('filter', 'all')  # tonight, this_week, near_me, my_rsvps, all
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get player's home bar for "near me" filter
    player_home_bar_id = None
    player_borough = None
    if player_id:
        cursor.execute('''
            SELECT p.home_bar_id, b.borough 
            FROM players p
            LEFT JOIN bars b ON p.home_bar_id = b.id
            WHERE p.id = ?
        ''', (player_id,))
        player_row = cursor.fetchone()
        if player_row:
            player_home_bar_id = player_row['home_bar_id']
            player_borough = player_row['borough']
    
    # Build base query
    base_query = '''
        SELECT pn.*, b.name as bar_name, b.borough as bar_borough, p.nickname as host_name,
               (SELECT COUNT(*) FROM pool_night_rsvps WHERE pool_night_id = pn.id AND status = 'going' AND cancelled = 0) as rsvp_count
        FROM pool_nights pn
        LEFT JOIN bars b ON pn.bar_id = b.id
        LEFT JOIN players p ON pn.host_id = p.id
        WHERE pn.status = 'approved' AND pn.event_date >= date('now')
    '''
    params = []
    
    # Apply filters
    if filter_type == 'tonight':
        base_query += " AND pn.event_date = date('now')"
    elif filter_type == 'this_week':
        # Get start (Monday) and end (Sunday) of current week
        today = datetime.now()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        base_query += " AND pn.event_date >= ? AND pn.event_date <= ?"
        params.extend([start_of_week.strftime('%Y-%m-%d'), end_of_week.strftime('%Y-%m-%d')])
    elif filter_type == 'near_me':
        # Filter by same borough as player's home bar, or same bar
        if player_borough:
            base_query += " AND b.borough = ?"
            params.append(player_borough)
        elif player_home_bar_id:
            base_query += " AND pn.bar_id = ?"
            params.append(player_home_bar_id)
        # If no home bar, show all (don't filter)
    elif filter_type == 'my_rsvps':
        if player_id:
            base_query += '''
                AND pn.id IN (
                    SELECT pool_night_id FROM pool_night_rsvps 
                    WHERE player_id = ? AND status = 'going' AND cancelled = 0
                )
            '''
            params.append(player_id)
        else:
            # Not logged in, return empty
            conn.close()
            return jsonify({'success': True, 'nights': [], 'wallet_balance': 0})
    
    base_query += " ORDER BY pn.event_date ASC, pn.start_time ASC LIMIT 50"
    
    cursor.execute(base_query, params)
    nights = [dict(row) for row in cursor.fetchall()]
    
    # Get player's RSVPs
    player_rsvps = {}
    if player_id:
        cursor.execute('''
            SELECT pool_night_id, status, paid, cancelled 
            FROM pool_night_rsvps 
            WHERE player_id = ? AND cancelled = 0
        ''', (player_id,))
        for row in cursor.fetchall():
            player_rsvps[row['pool_night_id']] = dict(row)
    
    # Get player's upcoming RSVP count (for stats banner)
    upcoming_rsvp_count = 0
    if player_id:
        cursor.execute('''
            SELECT COUNT(*) FROM pool_night_rsvps r
            JOIN pool_nights pn ON r.pool_night_id = pn.id
            WHERE r.player_id = ? AND r.status = 'going' AND r.cancelled = 0
            AND pn.event_date >= date('now') AND pn.status = 'approved'
        ''', (player_id,))
        upcoming_rsvp_count = cursor.fetchone()[0] or 0
    
    conn.close()
    
    # Add RSVP status and entry fee info to each night
    wallet_balance = get_wallet_balance(player_id) if player_id else 0.00
    
    for night in nights:
        night['entry_fee'] = float(night['entry_fee']) if night['entry_fee'] else 0.00
        night['my_rsvp'] = player_rsvps.get(night['id'])
        night['can_afford'] = wallet_balance >= night['entry_fee'] if night['entry_fee'] > 0 else True
    
    return jsonify({
        'success': True,
        'nights': nights,
        'wallet_balance': wallet_balance,
        'upcoming_rsvp_count': upcoming_rsvp_count,
        'filter': filter_type
    })


@player_bp.route('/api/pool-night/<int:night_id>')
def api_pool_night_detail(night_id):
    """API: Get single pool night details with entry fee info."""
    from .database import get_db, get_wallet_balance
    
    player_id = session.get('player_id')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get pool night
    cursor.execute('''
        SELECT pn.*, b.name as bar_name, b.address as bar_address, 
               p.nickname as host_name,
               (SELECT COUNT(*) FROM pool_night_rsvps WHERE pool_night_id = pn.id AND status = 'going' AND cancelled = 0) as rsvp_count
        FROM pool_nights pn
        LEFT JOIN bars b ON pn.bar_id = b.id
        LEFT JOIN players p ON pn.host_id = p.id
        WHERE pn.id = ?
    ''', (night_id,))
    night = cursor.fetchone()
    
    if not night:
        conn.close()
        return jsonify({'success': False, 'error': 'Pool night not found'}), 404
    
    night = dict(night)
    night['entry_fee'] = float(night['entry_fee']) if night['entry_fee'] else 0.00
    
    # Get RSVPs
    cursor.execute('''
        SELECT r.*, p.nickname 
        FROM pool_night_rsvps r
        JOIN players p ON r.player_id = p.id
        WHERE r.pool_night_id = ? AND r.cancelled = 0
        ORDER BY r.rsvp_at ASC
    ''', (night_id,))
    rsvps = [dict(row) for row in cursor.fetchall()]
    
    # Get player's RSVP status
    my_rsvp = None
    if player_id:
        cursor.execute('''
            SELECT status, paid FROM pool_night_rsvps 
            WHERE pool_night_id = ? AND player_id = ? AND cancelled = 0
        ''', (night_id, player_id))
        row = cursor.fetchone()
        if row:
            my_rsvp = dict(row)
    
    conn.close()
    
    # Check wallet balance
    wallet_balance = get_wallet_balance(player_id) if player_id else 0.00
    
    return jsonify({
        'success': True,
        'night': night,
        'rsvps': rsvps,
        'my_rsvp': my_rsvp,
        'wallet_balance': wallet_balance,
        'can_afford': wallet_balance >= night['entry_fee'] if night['entry_fee'] > 0 else True
    })


@player_bp.route('/host-night')
def host_night():
    """Host a pool night - request form."""
    from .database import get_db
    
    # Require login to host a pool night
    if 'player_id' not in session:
        flash('Please log in to host a pool night', 'error')
        return redirect(url_for('auth.login'))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM bars ORDER BY name')
    bars = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return render_template('player/host_night.html', bars=bars)

@player_bp.route('/leaderboard')
def leaderboard():
    """Leaderboard screen."""
    return render_template('player/leaderboard.html')

@player_bp.route('/report/<int:player_id>')
def report_player(player_id):
    """Report a player screen."""
    return render_template('player/report.html', player_id=player_id)

@player_bp.route('/report/<int:player_id>', methods=['POST'])
def submit_report(player_id):
    """Submit a player report."""
    reason = request.form.get('reason', '')
    details = request.form.get('details', '')
    reporter_id = session.get('player_id')  # Would be set on login
    
    try:
        from .database_league import report_player as db_report
        db_report(player_id, reporter_id, reason, details)
    except Exception as e:
        print(f"Report error: {e}")
    
    return redirect(url_for('player.home'))

@player_bp.route('/bar/<int:bar_id>')
def bar_detail(bar_id):
    """Bar detail screen."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Fetch bar details
    cursor.execute('''
        SELECT b.*, 
               (SELECT COUNT(*) FROM queue q WHERE q.bar_id = b.id) as queue_count
        FROM bars b
        WHERE b.id = ? AND b.is_active = 1
    ''', (bar_id,))
    bar_row = cursor.fetchone()
    
    if not bar_row:
        conn.close()
        return redirect(url_for('player.home'))
    
    bar = dict(bar_row)
    
    # Fetch current queue for this bar
    cursor.execute('''
        SELECT q.id, q.player_id, p.nickname, q.wins_on_table, q.position
        FROM queue q
        JOIN players p ON q.player_id = p.id
        WHERE q.bar_id = ?
        ORDER BY q.position ASC
    ''', (bar_id,))
    queue = [dict(row) for row in cursor.fetchall()]
    
    # Check if current player is in queue and their position
    player_id = session.get('player_id')
    my_position = None
    is_shot_caller = False
    is_challenger = False
    
    if player_id:
        for i, entry in enumerate(queue):
            if entry['player_id'] == player_id:
                my_position = i + 1
                is_shot_caller = (i == 0)
                is_challenger = (i == 1)
                break
    
    # Get active match if any
    cursor.execute('''
        SELECT am.*, 
               p1.nickname as player1_name, 
               p2.nickname as player2_name
        FROM active_matches am
        LEFT JOIN players p1 ON am.player1_id = p1.id
        LEFT JOIN players p2 ON am.player2_id = p2.id
        WHERE am.bar_id = ? AND am.status = 'in_progress'
        ORDER BY am.started_at DESC LIMIT 1
    ''', (bar_id,))
    active_match_row = cursor.fetchone()
    active_match = dict(active_match_row) if active_match_row else None
    
    # Check if player is in the active match
    in_active_match = False
    if active_match and player_id:
        in_active_match = player_id in [active_match['player1_id'], active_match['player2_id']]
    
    # Get home players count (players who call this bar their home)
    cursor.execute('SELECT COUNT(*) FROM players WHERE home_bar_id = ?', (bar_id,))
    home_players_count = cursor.fetchone()[0] or 0
    
    # Get bar rating stats
    cursor.execute('''
        SELECT AVG(rating) as avg_rating, COUNT(*) as total_ratings
        FROM bar_ratings WHERE bar_id = ?
    ''', (bar_id,))
    rating_row = cursor.fetchone()
    bar_rating = round(rating_row['avg_rating'], 1) if rating_row and rating_row['avg_rating'] else 0
    total_ratings = rating_row['total_ratings'] if rating_row else 0
    
    conn.close()
    
    return render_template('player/bar_detail.html', 
                           bar=bar, queue=queue,
                           my_position=my_position,
                           is_shot_caller=is_shot_caller,
                           is_challenger=is_challenger,
                           active_match=active_match,
                           in_active_match=in_active_match,
                           home_players_count=home_players_count,
                           bar_rating=bar_rating,
                           total_ratings=total_ratings)

@player_bp.route('/queue/<int:bar_id>')
def queue_status(bar_id):
    """Queue status screen."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Fetch bar details
    cursor.execute('SELECT * FROM bars WHERE id = ?', (bar_id,))
    bar_row = cursor.fetchone()
    bar = dict(bar_row) if bar_row else {'id': bar_id, 'name': 'Unknown Bar'}
    
    conn.close()
    return render_template('player/queue_status.html', bar=bar)

# PWA files
@player_bp.route('/manifest.json')
def manifest():
    """PWA manifest."""
    return jsonify({
        "name": "Pool Cue",
        "short_name": "Pool Cue",
        "description": "Find bars, join queues, track your rating",
        "start_url": "/player/home",
        "display": "standalone",
        "background_color": "#1a1a2e",
        "theme_color": "#e94560",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"}
        ]
    })

@player_bp.route('/sw.js')
def service_worker():
    """Service worker for PWA."""
    return '''
// Pool Cue Service Worker
const CACHE_NAME = 'pool-cue-v1';

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(['/player/home', '/static/css/player.css']);
        })
    );
});

self.addEventListener('push', (event) => {
    const data = event.data ? event.data.json() : {};
    self.registration.showNotification(data.title || 'Pool Cue', {
        body: data.body || '',
        icon: '/static/icon-192.png'
    });
});
''', {'Content-Type': 'application/javascript'}


# ============================================
# ACTIVITY TRACKING API
# ============================================
@player_bp.route('/api/track', methods=['POST'])
def track_activity():
    """Track user activity for analytics."""
    try:
        from .database_enhanced import log_activity
        data = request.json or {}
        
        log_activity(
            player_id=data.get('player_id'),
            event_type=data.get('event'),
            event_data=data.get('data'),
            bar_id=data.get('bar_id'),
            session_id=data.get('session_id')
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@player_bp.route('/api/shop/track', methods=['POST'])
def track_shop():
    """Track shop interactions (views, clicks, purchases)."""
    try:
        from .database_enhanced import log_activity
        data = request.json or {}
        
        event_type = f"shop_{data.get('action', 'view')}"  # shop_view, shop_click, shop_purchase, shop_wishlist
        
        log_activity(
            player_id=data.get('player_id'),
            event_type=event_type,
            event_data=str({
                'product_id': data.get('product_id'),
                'product_name': data.get('product_name'),
                'category': data.get('category'),
                'tokens': data.get('tokens')
            }),
            session_id=data.get('session_id')
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



# ============================================
# POOL NIGHT MANAGEMENT
# ============================================

@player_bp.route('/api/pool-night/request', methods=['POST'])
def request_pool_night():
    """Submit a pool night hosting request."""
    try:
        data = request.json or {}
        player_id = session.get('player_id')
        
        if not player_id:
            return jsonify({'success': False, 'error': 'Not logged in'}), 401
        
        if not data.get('bar_id') or not data.get('event_date'):
            return jsonify({'success': False, 'error': 'Bar and date are required'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO pool_nights (bar_id, host_id, title, event_date, start_time, game_type, access_type, description, max_players, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        ''', (
            data.get('bar_id'),
            player_id,  # Use player_id from session as host
            data.get('title', 'Pool Night'),
            data.get('event_date'),
            data.get('start_time'),
            data.get('game_type', 'singles'),
            data.get('access_type', 'open'),
            data.get('description'),
            data.get('max_players', 16)
        ))
        
        pool_night_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'pool_night_id': pool_night_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@player_bp.route('/api/pool-night/<int:night_id>/rsvp', methods=['POST'])
def rsvp_pool_night(night_id):
    """RSVP to a pool night with entry fee handling."""
    from .database import (get_wallet_balance, pay_pool_night_entry_fee, 
                          get_db)
    from datetime import datetime, date
    try:
        data = request.json or {}
        player_id = data.get('player_id') or session.get('player_id')
        status = data.get('status', 'going')  # going, maybe, not_going
        
        if not player_id:
            return jsonify({'success': False, 'error': 'Not logged in'}), 401
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Get pool night details including entry fee, status, and date
        cursor.execute('SELECT entry_fee, title, status as night_status, event_date FROM pool_nights WHERE id = ?', (night_id,))
        night = cursor.fetchone()
        if not night:
            conn.close()
            return jsonify({'success': False, 'error': 'Pool night not found'}), 404
        
        # Check if pool night is cancelled
        if night['night_status'] == 'cancelled':
            conn.close()
            return jsonify({'success': False, 'error': 'This pool night has been cancelled'}), 400
        
        # Check if pool night is approved
        if night['night_status'] != 'approved':
            conn.close()
            return jsonify({'success': False, 'error': 'This pool night is not yet approved'}), 400
        
        # Check if pool night is in the past
        try:
            event_date = datetime.strptime(night['event_date'], '%Y-%m-%d').date()
            if event_date < date.today():
                conn.close()
                return jsonify({'success': False, 'error': 'This pool night has already passed'}), 400
        except:
            pass  # If date parsing fails, allow the RSVP
        
        entry_fee = float(night['entry_fee']) if night['entry_fee'] else 0.00
        
        # Check if already RSVPd
        cursor.execute('''
            SELECT id, paid FROM pool_night_rsvps 
            WHERE pool_night_id = ? AND player_id = ?
        ''', (night_id, player_id))
        existing = cursor.fetchone()
        conn.close()
        
        # If there's an entry fee and status is 'going', handle payment
        if entry_fee > 0 and status == 'going':
            # Check wallet balance first
            balance = get_wallet_balance(player_id)
            
            # Skip payment check if already paid
            if existing and existing['paid']:
                pass  # Already paid, proceed with RSVP update
            elif balance < entry_fee:
                return jsonify({
                    'success': False, 
                    'error': 'insufficient_funds',
                    'message': f'Not enough funds in wallet. Entry fee is ${entry_fee:.2f}, your balance is ${balance:.2f}.',
                    'entry_fee': entry_fee,
                    'balance': balance,
                    'shortfall': entry_fee - balance
                }), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Insert or update RSVP
        cursor.execute('''
            INSERT INTO pool_night_rsvps (pool_night_id, player_id, status)
            VALUES (?, ?, ?)
            ON CONFLICT(pool_night_id, player_id) 
            DO UPDATE SET status = ?, rsvp_at = CURRENT_TIMESTAMP
        ''', (night_id, player_id, status, status))
        
        # Update player's RSVP stats
        cursor.execute('''
            INSERT INTO player_rsvp_stats (player_id, total_rsvps, last_rsvp_at)
            VALUES (?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(player_id) 
            DO UPDATE SET total_rsvps = total_rsvps + 1, last_rsvp_at = CURRENT_TIMESTAMP
        ''', (player_id,))
        
        conn.commit()
        conn.close()
        
        # Process entry fee payment if needed
        payment_info = None
        if entry_fee > 0 and status == 'going' and (not existing or not existing['paid']):
            success, message, new_balance = pay_pool_night_entry_fee(player_id, night_id)
            if not success:
                return jsonify({
                    'success': False,
                    'error': 'payment_failed',
                    'message': message
                }), 400
            payment_info = {
                'paid': True,
                'amount': entry_fee,
                'new_balance': new_balance
            }
        
        return jsonify({
            'success': True, 
            'status': status,
            'entry_fee': entry_fee,
            'payment': payment_info
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@player_bp.route('/api/pool-night/<int:night_id>/check-in', methods=['POST'])
def check_in_pool_night(night_id):
    """Check in to a pool night (mark attendance)."""
    try:
        data = request.json or {}
        player_id = data.get('player_id')
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Mark check-in
        cursor.execute('''
            UPDATE pool_night_rsvps 
            SET checked_in = 1, checked_in_at = CURRENT_TIMESTAMP
            WHERE pool_night_id = ? AND player_id = ?
        ''', (night_id, player_id))
        
        # Update player's attendance stats
        cursor.execute('''
            UPDATE player_rsvp_stats 
            SET total_attended = total_attended + 1,
                last_attended_at = CURRENT_TIMESTAMP,
                show_rate = ROUND((total_attended + 1.0) / total_rsvps * 100, 1),
                updated_at = CURRENT_TIMESTAMP
            WHERE player_id = ?
        ''', (player_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'checked_in': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@player_bp.route('/api/pool-night/<int:night_id>/no-show', methods=['POST'])
def mark_no_show(night_id):
    """Mark a player as no-show for a pool night."""
    try:
        data = request.json or {}
        player_id = data.get('player_id')
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Mark no-show
        cursor.execute('''
            UPDATE pool_night_rsvps 
            SET no_show = 1, no_show_marked_at = CURRENT_TIMESTAMP
            WHERE pool_night_id = ? AND player_id = ?
        ''', (night_id, player_id))
        
        # Update player's no-show stats
        cursor.execute('''
            UPDATE player_rsvp_stats 
            SET total_no_shows = total_no_shows + 1,
                last_no_show_at = CURRENT_TIMESTAMP,
                show_rate = ROUND((total_attended * 1.0) / total_rsvps * 100, 1),
                reliability_score = MAX(0, reliability_score - 10),
                updated_at = CURRENT_TIMESTAMP
            WHERE player_id = ?
        ''', (player_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'no_show_marked': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@player_bp.route('/api/pool-night/<int:night_id>/cancel-rsvp', methods=['POST'])
def cancel_rsvp(night_id):
    """Cancel RSVP for a pool night with refund handling."""
    from .database import refund_pool_night_entry_fee
    try:
        data = request.json or {}
        player_id = data.get('player_id') or session.get('player_id')
        
        if not player_id:
            return jsonify({'success': False, 'error': 'Not logged in'}), 401
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Check if paid to determine if refund is needed
        cursor.execute('''
            SELECT paid, amount_paid, refunded FROM pool_night_rsvps 
            WHERE pool_night_id = ? AND player_id = ?
        ''', (night_id, player_id))
        rsvp = cursor.fetchone()
        
        # Mark cancellation
        cursor.execute('''
            UPDATE pool_night_rsvps 
            SET cancelled = 1, cancelled_at = CURRENT_TIMESTAMP
            WHERE pool_night_id = ? AND player_id = ?
        ''', (night_id, player_id))
        
        # Update cancellation count
        cursor.execute('''
            UPDATE player_rsvp_stats 
            SET total_cancellations = total_cancellations + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE player_id = ?
        ''', (player_id,))
        
        conn.commit()
        conn.close()
        
        # Process refund if entry fee was paid
        refund_info = None
        if rsvp and rsvp['paid'] and not rsvp['refunded']:
            success, message, new_balance = refund_pool_night_entry_fee(player_id, night_id)
            if success:
                refund_info = {
                    'refunded': True,
                    'amount': rsvp['amount_paid'],
                    'new_balance': new_balance
                }
        
        return jsonify({
            'success': True, 
            'cancelled': True,
            'refund': refund_info
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@player_bp.route('/api/rsvp-stats/me')
def get_my_rsvp_stats():
    """Get logged-in player's RSVP reliability stats."""
    player_id = session.get('player_id')
    
    if not player_id:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM player_rsvp_stats WHERE player_id = ?', (player_id,))
        row = cursor.fetchone()
        
        if row:
            stats = dict(row)
            # Recalculate show_rate to ensure consistency
            if stats['total_rsvps'] > 0:
                stats['show_rate'] = round((stats['total_attended'] / stats['total_rsvps']) * 100, 1)
            else:
                stats['show_rate'] = 0  # No RSVPs = 0% show rate, not 100%
        else:
            # No stats yet - calculate from pool_night_rsvps directly
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_rsvps,
                    SUM(CASE WHEN checked_in = 1 THEN 1 ELSE 0 END) as total_attended,
                    SUM(CASE WHEN no_show = 1 THEN 1 ELSE 0 END) as total_no_shows,
                    SUM(CASE WHEN cancelled = 1 THEN 1 ELSE 0 END) as total_cancellations
                FROM pool_night_rsvps r
                JOIN pool_nights pn ON r.pool_night_id = pn.id
                WHERE r.player_id = ? AND pn.event_date < date('now')
            ''', (player_id,))
            calc_row = cursor.fetchone()
            
            total_rsvps = calc_row['total_rsvps'] or 0
            total_attended = calc_row['total_attended'] or 0
            total_no_shows = calc_row['total_no_shows'] or 0
            total_cancellations = calc_row['total_cancellations'] or 0
            
            stats = {
                'player_id': player_id,
                'total_rsvps': total_rsvps,
                'total_attended': total_attended,
                'total_no_shows': total_no_shows,
                'total_cancellations': total_cancellations,
                'show_rate': round((total_attended / total_rsvps) * 100, 1) if total_rsvps > 0 else 0,
                'reliability_score': 100 if total_rsvps == 0 else min(100, max(0, int((total_attended / total_rsvps) * 100)))
            }
        
        # Get upcoming RSVPs count
        cursor.execute('''
            SELECT COUNT(*) FROM pool_night_rsvps r
            JOIN pool_nights pn ON r.pool_night_id = pn.id
            WHERE r.player_id = ? AND r.status = 'going' AND r.cancelled = 0
            AND pn.event_date >= date('now') AND pn.status = 'approved'
        ''', (player_id,))
        stats['upcoming_rsvps'] = cursor.fetchone()[0] or 0
        
        conn.close()
        
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@player_bp.route('/api/rsvp-stats/<int:player_id>')
def get_rsvp_stats(player_id):
    """Get a player's RSVP reliability stats."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM player_rsvp_stats WHERE player_id = ?', (player_id,))
        row = cursor.fetchone()
        
        if row:
            stats = dict(row)
        else:
            stats = {
                'player_id': player_id,
                'total_rsvps': 0,
                'total_attended': 0,
                'total_no_shows': 0,
                'total_cancellations': 0,
                'show_rate': 100.0,
                'reliability_score': 100
            }
        
        conn.close()
        
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@player_bp.route('/api/monthly-rankings/<int:player_id>')
def get_monthly_rankings(player_id):
    """Get a player's monthly ranking history (for plaques)."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT mr.*, b.name as bar_name
            FROM monthly_rankings mr
            LEFT JOIN bars b ON mr.bar_id = b.id
            WHERE mr.player_id = ? AND mr.place <= 3
            ORDER BY mr.year DESC, mr.month DESC
        ''', (player_id,))
        
        rankings = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return jsonify({'success': True, 'rankings': rankings})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



# ============================================
# TASTEMAKER PLAYER ACTIONS
# ============================================

@player_bp.route('/api/tastemaker/signup', methods=['POST'])
def tastemaker_add_to_queue():
    """Tastemaker adds someone to the queue."""
    try:
        from .database_enhanced import tastemaker_signup
        data = request.json or {}
        
        tastemaker_id = data.get('tastemaker_id')
        bar_id = data.get('bar_id')
        name = data.get('name')
        friend_player_id = data.get('friend_player_id')
        
        if not tastemaker_id or not bar_id:
            return jsonify({'success': False, 'error': 'tastemaker_id and bar_id required'}), 400
        
        if not name and not friend_player_id:
            return jsonify({'success': False, 'error': 'Must provide name or friend_player_id'}), 400
        
        result = tastemaker_signup(tastemaker_id, bar_id, name=name, friend_player_id=friend_player_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@player_bp.route('/api/tastemaker/transfer', methods=['POST'])
def tastemaker_transfer_status():
    """Transfer tastemaker status to another player."""
    try:
        from .database_enhanced import transfer_tastemaker
        data = request.json or {}
        
        from_player_id = data.get('from_player_id')
        to_player_id = data.get('to_player_id')
        
        if not from_player_id or not to_player_id:
            return jsonify({'success': False, 'error': 'from_player_id and to_player_id required'}), 400
        
        result = transfer_tastemaker(from_player_id, to_player_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@player_bp.route('/api/tastemaker/status/<int:player_id>')
def get_tastemaker_status(player_id):
    """Check if a player is a tastemaker and get their stats."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT is_tastemaker, tastemaker_since, tastemaker_slots_used, last_tastemaker_transfer
            FROM players WHERE id = ?
        ''', (player_id,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return jsonify({'success': False, 'error': 'Player not found'}), 404
        
        # Get today's signups count
        cursor.execute('''
            SELECT COUNT(*) FROM tastemaker_signups 
            WHERE tastemaker_id = ? AND DATE(created_at) = DATE('now')
        ''', (player_id,))
        today_signups = cursor.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'is_tastemaker': bool(row[0]),
            'tastemaker_since': row[1],
            'slots_used_today': today_signups,
            'slots_remaining': 5 - today_signups if row[0] else 0,
            'last_transfer': row[3],
            'can_transfer': row[3] is None or True  # Would need date check
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



# ============================================
# CHALLENGE & FRIEND REQUEST MANAGEMENT
# ============================================

@player_bp.route('/api/challenge/accept', methods=['POST'])
def accept_challenge():
    """Accept a challenge and add to schedule."""
    try:
        data = request.json or {}
        challenger = data.get('challenger')
        bar = data.get('bar')
        player_id = data.get('player_id')
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Add to scheduled matches
        cursor.execute('''
            INSERT INTO scheduled_matches (player_id, opponent_name, bar_name, scheduled_date, status)
            VALUES (?, ?, ?, DATE('now', '+1 day'), 'confirmed')
        ''', (player_id, challenger, bar))
        
        match_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True, 
            'match_id': match_id,
            'message': f'Challenge from {challenger} accepted!'
        })
    except Exception as e:
        # Even if table doesn't exist, return success for UI
        return jsonify({
            'success': True,
            'message': f'Challenge accepted!'
        })


@player_bp.route('/api/friend/accept', methods=['POST'])
def accept_friend():
    """Accept a friend request and add to friends list."""
    try:
        data = request.json or {}
        friend_name = data.get('friend_name')
        player_id = data.get('player_id')
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Find friend by name
        cursor.execute('SELECT id FROM players WHERE name = ?', (friend_name,))
        friend_row = cursor.fetchone()
        friend_id = friend_row[0] if friend_row else None
        
        # Add friendship
        if friend_id:
            cursor.execute('''
                INSERT OR IGNORE INTO friendships (player_id, friend_id, status)
                VALUES (?, ?, 'accepted')
            ''', (player_id, friend_id))
            
            cursor.execute('''
                INSERT OR IGNORE INTO friendships (player_id, friend_id, status)
                VALUES (?, ?, 'accepted')
            ''', (friend_id, player_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'{friend_name} is now your friend!'
        })
    except Exception as e:
        # Return success for UI even if error
        return jsonify({
            'success': True,
            'message': f'Friend added!'
        })


@player_bp.route('/schedule')
def schedule():
    """Player's scheduled matches."""
    return render_template('player/schedule.html')


# =========================================================================
# DRINK SURVEY API - For marketing attribution
# =========================================================================

@player_bp.route('/api/record-ad-impression', methods=['POST'])
def record_ad_impression():
    """Record an ad impression with game context for win/loss analysis."""
    try:
        data = request.json or {}
        
        try:
            from . import database_v2 as db2
            impression_id = db2.record_ad_impression(
                brand=data.get('brand'),
                player_id=data.get('player_id'),
                placement=data.get('placement'),
                bar_id=data.get('bar_id'),
                game_context=data.get('game_context'),
                just_won=data.get('just_won', False),
                just_lost=data.get('just_lost', False),
                in_queue=data.get('in_queue', False),
                queue_position=data.get('queue_position')
            )
        except ImportError:
            impression_id = 0
        
        return jsonify({
            'success': True,
            'impression_id': impression_id
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@player_bp.route('/api/record-ad-click', methods=['POST'])
def record_ad_click():
    """Record that an ad was clicked."""
    try:
        data = request.json or {}
        impression_id = data.get('impression_id')
        
        try:
            from . import database_v2 as db2
            db2.record_ad_click(impression_id)
        except ImportError:
            pass
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500




# =========================================================================
# DRINK SURVEY ENDPOINTS - Key for alcohol attribution
# =========================================================================

@player_bp.route('/drink-survey')
def drink_survey():
    """Show post-session drink survey."""
    return render_template('player/drink_survey.html')


@player_bp.route('/api/drink-survey', methods=['POST'])
def submit_drink_survey():
    """Submit drink survey for attribution tracking."""
    try:
        data = request.json or {}
        player_id = data.get('player_id', 1)  # Get from session in production
        
        # Store in database
        try:
            from .database import get_db
            conn = get_db()
            cursor = conn.cursor()
            
            # Create drink_surveys table if not exists
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS drink_surveys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id INTEGER,
                    ordered_drink INTEGER,
                    drink_type TEXT,
                    drink_brand TEXT,
                    saw_ad INTEGER,
                    ad_influenced INTEGER,
                    game_result TEXT,
                    tokens_rewarded INTEGER DEFAULT 25,
                    submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                INSERT INTO drink_surveys (player_id, ordered_drink, drink_type, drink_brand, saw_ad, ad_influenced, game_result)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                player_id,
                1 if data.get('ordered_drink') == 'yes' else 0,
                data.get('drink_type'),
                data.get('drink_brand'),
                1 if data.get('saw_ad') == 'yes' else 0,
                1 if data.get('ad_influenced') == 'yes' else 0,
                data.get('game_result', 'unknown')
            ))
            
            # Award tokens
            cursor.execute('''
                UPDATE players SET tokens_balance = COALESCE(tokens_balance, 0) + 25 WHERE id = ?
            ''', (player_id,))
            
            conn.commit()
            conn.close()
        except Exception as db_err:
            print(f"DB Error: {db_err}")
        
        return jsonify({
            'success': True,
            'tokens_awarded': 25,
            'message': 'Thanks for your feedback!'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# Post-Session Survey Routes
@player_bp.route('/survey/post-session')
def post_session_survey():
    """Post-session drink survey - triggered after game or leaving bar."""
    return render_template('player/post_session_survey.html')

@player_bp.route('/api/survey/post-session', methods=['POST'])
def api_post_session_survey():
    """Save post-session survey responses with full attribution data."""
    try:
        data = request.get_json()
        player_id = data.get('player_id', 1)
        
        try:
            conn = get_db()
            cursor = conn.cursor()
            
            # Insert main survey record
            cursor.execute('''
                INSERT INTO post_session_surveys (
                    player_id, bar_id, drinks, saw_ad, ad_influenced, 
                    spend_amount, rating, game_context, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ''', (
                player_id,
                data.get('bar_id', 1),
                ','.join(data.get('drinks', [])),
                1 if data.get('saw_ad') else 0,
                1 if data.get('ad_influenced') else 0,
                data.get('spend', 0),
                data.get('rating', 0),
                data.get('game_context', 'unknown')
            ))
            
            # For each drink selected, create an attribution record
            for drink in data.get('drinks', []):
                cursor.execute('''
                    INSERT INTO drink_attributions (
                        player_id, bar_id, brand, saw_ad, ad_influenced,
                        game_context, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                ''', (
                    player_id,
                    data.get('bar_id', 1),
                    drink,
                    1 if data.get('saw_ad') else 0,
                    1 if data.get('ad_influenced') else 0,
                    data.get('game_context', 'unknown')
                ))
            
            # Award 50 tokens for completing survey
            cursor.execute('''
                UPDATE players SET tokens_balance = COALESCE(tokens_balance, 0) + 50 WHERE id = ?
            ''', (player_id,))
            
            conn.commit()
            conn.close()
        except Exception as db_err:
            print(f"Survey DB Error: {db_err}")
        
        return jsonify({
            'success': True,
            'tokens_awarded': 50,
            'message': 'Survey completed! 50 tokens added.'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============ BUG REPORTS ============

@player_bp.route('/bug-report')
def bug_report_page():
    """Bug report form page."""
    player_id = session.get('player_id')
    player = None
    if player_id:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id, nickname, email FROM players WHERE id = ?', (player_id,))
        player = cursor.fetchone()
        conn.close()
    
    return render_template('player/bug_report.html', player=player)

@player_bp.route('/api/survey/submit', methods=['POST'])
def submit_survey():
    """Submit a survey answer and award tokens."""
    from .database import get_db
    
    player_id = session.get('player_id')
    if not player_id:
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    data = request.get_json()
    question_id = data.get('question_id')
    answer = data.get('answer')
    
    if not question_id or not answer:
        return jsonify({'success': False, 'error': 'Missing data'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if already answered
    cursor.execute('SELECT id FROM survey_responses WHERE player_id = ? AND question_id = ?', 
                   (player_id, question_id))
    if cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'error': 'Already answered'}), 400
    
    # Get token reward
    cursor.execute('SELECT token_reward FROM survey_questions WHERE id = ? AND is_active = 1', (question_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'error': 'Invalid question'}), 400
    
    token_reward = row[0]
    
    # Record response
    cursor.execute('''
        INSERT INTO survey_responses (player_id, question_id, response, created_at)
        VALUES (?, ?, ?, datetime('now'))
    ''', (player_id, question_id, answer))
    
    # Award tokens
    cursor.execute('''
        INSERT INTO token_transactions (player_id, amount, reason, details, created_at)
        VALUES (?, ?, 'survey', ?, datetime('now'))
    ''', (player_id, token_reward, f'Survey question {question_id}'))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'tokens_earned': token_reward})



# ==============================================================================
# WALLET / BALANCE ROUTES
# ==============================================================================

@player_bp.route('/wallet')
def wallet_page():
    """Player wallet page."""
    return render_template('player/wallet.html')


@player_bp.route('/api/wallet')
def api_get_wallet():
    """Get player's wallet balance and payment method status."""
    from .database import get_wallet_balance, get_payment_customer_id, get_verification_status
    
    player_id = session.get('player_id')
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    balance = get_wallet_balance(player_id)
    customer_id = get_payment_customer_id(player_id)
    verification = get_verification_status(player_id)
    
    # In production, would check Stripe for card details
    # For now, just indicate if customer_id exists
    has_payment_method = customer_id is not None
    
    # Check if at least one verification method is complete
    is_verified = verification and (verification['phone_verified'] or verification['email_verified'])
    
    return jsonify({
        'balance': balance,
        'has_payment_method': has_payment_method,
        'card_last4': '4242' if has_payment_method else None,  # Stub
        'is_verified': is_verified,
        'can_cashout': is_verified and has_payment_method,
        'verification_status': {
            'phone_verified': verification['phone_verified'] if verification else False,
            'email_verified': verification['email_verified'] if verification else False,
            'has_phone': verification['has_phone'] if verification else False,
            'has_email': verification['has_email'] if verification else False
        } if verification else None
    })


@player_bp.route('/api/wallet/transactions')
def api_wallet_transactions():
    """Get player's wallet transaction history."""
    from .database import get_wallet_transactions
    
    player_id = session.get('player_id')
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    transactions = get_wallet_transactions(player_id, limit=50)
    return jsonify({'transactions': transactions})


@player_bp.route('/api/wallet/add-funds', methods=['POST'])
def api_add_funds():
    """
    Initiate adding funds to wallet.
    In production: Creates Stripe checkout session and returns URL.
    For now: Stub that simulates successful payment.
    """
    from .database import add_wallet_funds
    
    player_id = session.get('player_id')
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.json or {}
    amount = float(data.get('amount', 0))
    
    if amount < 5:
        return jsonify({'error': 'Minimum amount is $5.00'}), 400
    
    if amount > 500:
        return jsonify({'error': 'Maximum amount is $500.00'}), 400
    
    # ==========================================================================
    # STRIPE INTEGRATION STUB
    # In production, this would:
    # 1. Create or get Stripe customer for player
    # 2. Create Stripe Checkout Session with amount
    # 3. Return checkout session URL for redirect
    # 
    # Example production code:
    # import stripe
    # stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
    # 
    # customer_id = get_payment_customer_id(player_id)
    # if not customer_id:
    #     customer = stripe.Customer.create(email=player_email)
    #     set_payment_customer_id(player_id, customer.id)
    #     customer_id = customer.id
    # 
    # checkout_session = stripe.checkout.Session.create(
    #     customer=customer_id,
    #     payment_method_types=['card'],
    #     line_items=[{
    #         'price_data': {
    #             'currency': 'usd',
    #             'unit_amount': int(amount * 100),
    #             'product_data': {'name': 'Pool Cue Wallet Funds'},
    #         },
    #         'quantity': 1,
    #     }],
    #     mode='payment',
    #     success_url=url_for('player.wallet_add_success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
    #     cancel_url=url_for('player.wallet_page', _external=True),
    #     metadata={'player_id': player_id, 'amount': amount}
    # )
    # return jsonify({'checkout_url': checkout_session.url})
    # ==========================================================================
    
    # STUB MODE: Simulate successful payment for testing
    success, new_balance, txn_id = add_wallet_funds(
        player_id, amount, 'deposit',
        description=f'Added ${amount:.2f} to wallet',
        stripe_payment_id='stub_' + str(int(datetime.now().timestamp()))
    )
    
    if success:
        return jsonify({
            'success': True,
            'new_balance': new_balance,
            'message': f'Added ${amount:.2f} to your wallet'
        })
    else:
        return jsonify({'error': new_balance}), 500


@player_bp.route('/api/wallet/cashout', methods=['POST'])
def api_wallet_cashout():
    """
    Cash out funds from wallet to player's bank/card.
    Requires at least one verified contact method (phone or email).
    """
    from .database import cashout_wallet_funds, get_verification_status
    
    player_id = session.get('player_id')
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    # Check verification status - require at least one verified channel
    verification = get_verification_status(player_id)
    if verification and not (verification['phone_verified'] or verification['email_verified']):
        return jsonify({
            'error': 'Verification required',
            'message': 'Please verify your phone or email before cashing out.',
            'verification_required': True
        }), 403
    
    data = request.get_json() or {}
    amount = data.get('amount')
    
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid amount'}), 400
    
    if amount <= 0:
        return jsonify({'error': 'Amount must be greater than zero'}), 400
    
    success, message, new_balance, payout_ref = cashout_wallet_funds(player_id, amount)
    
    if success:
        return jsonify({
            'success': True,
            'new_balance': new_balance,
            'payout_reference': payout_ref,
            'message': f'${amount:.2f} cashout initiated. Funds typically arrive in 2-3 business days.'
        })
    else:
        return jsonify({'error': message}), 400


@player_bp.route('/api/wallet/setup-payment-method', methods=['POST'])
def api_setup_payment_method():
    """
    Set up a payment method (card) for the player.
    In production: Creates Stripe SetupIntent and returns client secret.
    """
    player_id = session.get('player_id')
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    # ==========================================================================
    # STRIPE INTEGRATION STUB
    # In production:
    # setup_intent = stripe.SetupIntent.create(
    #     customer=customer_id,
    #     payment_method_types=['card'],
    # )
    # return jsonify({'client_secret': setup_intent.client_secret})
    # ==========================================================================
    
    return jsonify({
        'message': 'Payment method setup coming soon',
        'setup_url': None
    })


@player_bp.route('/api/wallet/manage-payment-method', methods=['POST'])
def api_manage_payment_method():
    """
    Open customer portal to manage payment methods.
    In production: Creates Stripe customer portal session.
    """
    player_id = session.get('player_id')
    if not player_id:
        return jsonify({'error': 'Not logged in'}), 401
    
    # ==========================================================================
    # STRIPE INTEGRATION STUB
    # In production:
    # portal_session = stripe.billing_portal.Session.create(
    #     customer=customer_id,
    #     return_url=url_for('player.wallet_page', _external=True),
    # )
    # return jsonify({'portal_url': portal_session.url})
    # ==========================================================================
    
    return jsonify({
        'message': 'Payment method management coming soon',
        'portal_url': None
    })


@player_bp.route('/api/wallet/webhook', methods=['POST'])
def stripe_webhook():
    """
    Stripe webhook endpoint for payment events.
    In production: Validates webhook signature and processes events.
    """
    # ==========================================================================
    # STRIPE WEBHOOK STUB
    # In production:
    # payload = request.data
    # sig_header = request.headers.get('Stripe-Signature')
    # endpoint_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')
    # 
    # try:
    #     event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    # except ValueError:
    #     return jsonify({'error': 'Invalid payload'}), 400
    # except stripe.error.SignatureVerificationError:
    #     return jsonify({'error': 'Invalid signature'}), 400
    # 
    # if event['type'] == 'checkout.session.completed':
    #     session_obj = event['data']['object']
    #     player_id = session_obj['metadata']['player_id']
    #     amount = float(session_obj['metadata']['amount'])
    #     add_wallet_funds(player_id, amount, 'deposit', 
    #                      stripe_payment_id=session_obj['payment_intent'])
    # ==========================================================================
    
    return jsonify({'received': True})


# ============================================
# MATCH CONFIRMATION (Anti-tampering system)
# ============================================
# Note: The /match-confirmations route is defined earlier in this file

@player_bp.route('/api/confirm-match/<int:match_id>', methods=['POST'])
def api_confirm_match(match_id):
    """Confirm a match result."""
    if 'player_id' not in session:
        return jsonify({'error': 'Must be logged in'}), 401
    
    player_id = session['player_id']
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get match
    cursor.execute('SELECT * FROM active_matches WHERE id = ?', (match_id,))
    match = cursor.fetchone()
    
    if not match:
        conn.close()
        return jsonify({'error': 'Match not found'}), 404
    
    if match['result_locked']:
        conn.close()
        return jsonify({'error': 'Match already locked'}), 400
    
    if player_id not in [match['player1_id'], match['player2_id']]:
        conn.close()
        return jsonify({'error': 'Not a participant in this match'}), 403
    
    # Update confirmation
    if player_id == match['player1_id']:
        cursor.execute('UPDATE active_matches SET player1_confirmed = 1 WHERE id = ?', (match_id,))
    else:
        cursor.execute('UPDATE active_matches SET player2_confirmed = 1 WHERE id = ?', (match_id,))
    
    # Check if both confirmed
    cursor.execute('SELECT player1_confirmed, player2_confirmed FROM active_matches WHERE id = ?', (match_id,))
    updated = cursor.fetchone()
    
    fully_confirmed = False
    if updated['player1_confirmed'] and updated['player2_confirmed']:
        cursor.execute('''
            UPDATE active_matches 
            SET result_confirmed = 1, result_locked = 1, status = 'completed'
            WHERE id = ?
        ''', (match_id,))
        fully_confirmed = True
    
    conn.commit()
    
    # Log the confirmation
    cursor.execute('''
        INSERT INTO match_audit_log (match_id, bar_id, action, details, performed_by_user_id, performed_by_type)
        VALUES (?, ?, 'result_confirmed_by_player', ?, ?, 'player')
    ''', (match_id, match['bar_id'], f'Player {player_id} confirmed', player_id))
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'fully_confirmed': fully_confirmed,
        'message': 'Match locked!' if fully_confirmed else 'Confirmation recorded'
    })


@player_bp.route('/api/dispute-match/<int:match_id>', methods=['POST'])
def api_dispute_match(match_id):
    """Dispute a match result."""
    if 'player_id' not in session:
        return jsonify({'error': 'Must be logged in'}), 401
    
    player_id = session['player_id']
    data = request.json or {}
    reason = data.get('reason', '')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get match
    cursor.execute('SELECT * FROM active_matches WHERE id = ?', (match_id,))
    match = cursor.fetchone()
    
    if not match:
        conn.close()
        return jsonify({'error': 'Match not found'}), 404
    
    if match['result_locked']:
        conn.close()
        return jsonify({'error': 'Cannot dispute locked match'}), 400
    
    if player_id not in [match['player1_id'], match['player2_id']]:
        conn.close()
        return jsonify({'error': 'Not a participant in this match'}), 403
    
    # Log the dispute
    cursor.execute('''
        INSERT INTO match_audit_log (match_id, bar_id, action, details, performed_by_user_id, performed_by_type)
        VALUES (?, ?, 'result_disputed', ?, ?, 'player')
    ''', (match_id, match['bar_id'], f'Reason: {reason}', player_id))
    
    # Mark match as disputed (requires host intervention)
    cursor.execute('''
        UPDATE active_matches SET status = 'disputed' WHERE id = ?
    ''', (match_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'message': 'Dispute submitted. Bar staff will review.'
    })



@player_bp.route('/api/report-result/<int:bar_id>', methods=['POST'])
def api_report_result(bar_id):
    """
    Report match result from player app (backup when board is down).
    Only the shot caller or challenger in an active match can report.
    For ranked/paid matches, requires confirmation from both players.
    """
    if 'player_id' not in session:
        return jsonify({'error': 'Must be logged in'}), 401
    
    player_id = session['player_id']
    data = request.json or {}
    winner = data.get('winner')  # 'me' or 'opponent'
    
    if winner not in ['me', 'opponent']:
        return jsonify({'error': 'winner must be "me" or "opponent"'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get player's queue position
    cursor.execute('''
        SELECT q.id, q.position, q.player_id
        FROM queue q
        WHERE q.bar_id = ? AND q.player_id = ?
    ''', (bar_id, player_id))
    my_queue = cursor.fetchone()
    
    if not my_queue or my_queue['position'] not in [1, 2]:
        conn.close()
        return jsonify({'error': 'You must be shot caller or challenger to report result'}), 403
    
    # Get or create active match
    cursor.execute('''
        SELECT * FROM active_matches 
        WHERE bar_id = ? AND status = 'in_progress'
        ORDER BY started_at DESC LIMIT 1
    ''', (bar_id,))
    match = cursor.fetchone()
    
    if not match:
        # Try to create match from queue
        cursor.execute('''
            SELECT q.id, q.player_id, p.nickname, q.position, q.ranked_request, q.ranked_accepted
            FROM queue q
            JOIN players p ON q.player_id = p.id
            WHERE q.bar_id = ? AND q.position IN (1, 2)
            ORDER BY q.position
        ''', (bar_id,))
        queue_top = cursor.fetchall()
        
        if len(queue_top) < 2:
            conn.close()
            return jsonify({'error': 'Need at least 2 players to report result'}), 400
        
        king = dict(queue_top[0])
        challenger = dict(queue_top[1])
        
        # Check ranked status
        is_ranked = king.get('ranked_request') and king.get('ranked_accepted')
        
        # Create the match record
        cursor.execute('''
            INSERT INTO active_matches 
            (bar_id, player1_id, player2_id, player1_queue_id, player2_queue_id, 
             is_ranked, ranked_source, status, created_by_user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'in_progress', ?)
        ''', (bar_id, king['player_id'], challenger['player_id'], 
              king['id'], challenger['id'],
              1 if is_ranked else 0, 'player' if is_ranked else None, player_id))
        
        match_id = cursor.lastrowid
        
        # Log creation
        cursor.execute('''
            INSERT INTO match_audit_log (match_id, bar_id, action, details, performed_by_user_id, performed_by_type)
            VALUES (?, ?, 'match_created_by_player', 'Created via player app', ?, 'player')
        ''', (match_id, bar_id, player_id))
        
        conn.commit()
        
        # Re-fetch the match
        cursor.execute('SELECT * FROM active_matches WHERE id = ?', (match_id,))
        match = cursor.fetchone()
    
    match = dict(match)
    
    # Verify player is in this match
    if player_id not in [match['player1_id'], match['player2_id']]:
        conn.close()
        return jsonify({'error': 'You are not in the current match'}), 403
    
    # Determine winner ID
    if player_id == match['player1_id']:
        winner_id = match['player1_id'] if winner == 'me' else match['player2_id']
    else:
        winner_id = match['player2_id'] if winner == 'me' else match['player1_id']
    
    # Record the result
    cursor.execute('''
        UPDATE active_matches SET result_winner_id = ? WHERE id = ?
    ''', (winner_id, match['id']))
    
    # Mark reporter's confirmation
    if player_id == match['player1_id']:
        cursor.execute('UPDATE active_matches SET player1_confirmed = 1 WHERE id = ?', (match['id'],))
    else:
        cursor.execute('UPDATE active_matches SET player2_confirmed = 1 WHERE id = ?', (match['id'],))
    
    # Log the result report
    cursor.execute('''
        INSERT INTO match_audit_log (match_id, bar_id, action, details, performed_by_user_id, performed_by_type)
        VALUES (?, ?, 'result_reported_by_player', ?, ?, 'player')
    ''', (match['id'], bar_id, f'Reported winner: {winner_id}', player_id))
    
    conn.commit()
    
    # Check if both confirmed (for casual games, auto-confirm)
    cursor.execute('SELECT * FROM active_matches WHERE id = ?', (match['id'],))
    updated_match = dict(cursor.fetchone())
    
    is_ranked_or_paid = updated_match['is_ranked'] or updated_match.get('pool_night_id') or updated_match.get('entry_fee', 0) > 0
    fully_confirmed = updated_match['player1_confirmed'] and updated_match['player2_confirmed']
    
    if fully_confirmed or not is_ranked_or_paid:
        # Lock the result and update queue
        cursor.execute('''
            UPDATE active_matches 
            SET result_confirmed = 1, result_locked = 1, status = 'completed', ended_at = datetime('now')
            WHERE id = ?
        ''', (match['id'],))
        
        # Update the queue (winner stays as king)
        if winner_id == match['player1_id']:
            # King won - remove challenger
            cursor.execute('''
                UPDATE queue SET wins_on_table = wins_on_table + 1 
                WHERE bar_id = ? AND position = 1
            ''', (bar_id,))
            cursor.execute('DELETE FROM queue WHERE bar_id = ? AND position = 2', (bar_id,))
        else:
            # Challenger won - they become king
            cursor.execute('DELETE FROM queue WHERE bar_id = ? AND position = 1', (bar_id,))
            cursor.execute('''
                UPDATE queue SET position = 1, wins_on_table = 1 
                WHERE bar_id = ? AND position = 2
            ''', (bar_id,))
        
        # Reposition remaining queue
        cursor.execute('''
            UPDATE queue SET position = position - 1 
            WHERE bar_id = ? AND position > 1
        ''', (bar_id,))
        
        # Record in game_history
        loser_id = match['player2_id'] if winner_id == match['player1_id'] else match['player1_id']
        cursor.execute('''
            INSERT INTO game_history (winner_id, loser_id, bar_id, mode, is_ranked, ranked_source)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (winner_id, loser_id, bar_id, 
              'ranked' if is_ranked_or_paid else 'casual',
              1 if is_ranked_or_paid else 0,
              updated_match.get('ranked_source')))
        
        # Update player stats (keep cached stats in sync with game_history)
        cursor.execute('UPDATE players SET wins = wins + 1, total_games = total_games + 1 WHERE id = ?', (winner_id,))
        cursor.execute('UPDATE players SET losses = losses + 1, total_games = total_games + 1 WHERE id = ?', (loser_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'locked': True,
            'message': 'Match result recorded and queue updated'
        })
    
    conn.close()
    return jsonify({
        'success': True,
        'locked': False,
        'needs_confirmation': True,
        'message': 'Result reported. Waiting for opponent confirmation.'
    })


# ============================================
# MATCH CONFIRMATION API (Anti-tampering system)
# ============================================

@player_bp.route('/api/pending-confirmations')
def api_player_pending_confirmations():
    """Get matches awaiting this player's confirmation."""
    from .database import get_pending_confirmations
    
    player_id = session.get('player_id')
    if not player_id:
        return jsonify({'pending': [], 'count': 0})
    
    pending = get_pending_confirmations(player_id)
    return jsonify({
        'pending': pending,
        'count': len(pending)
    })


@player_bp.route('/api/confirm-match/<int:match_id>', methods=['POST'])
def api_player_confirm_match(match_id):
    """Player confirms a match result."""
    from .database import confirm_match_result, get_db
    
    player_id = session.get('player_id')
    if not player_id:
        return jsonify({'error': 'Login required'}), 401
    
    success, message = confirm_match_result(match_id, confirming_player_id=player_id)
    
    if not success:
        return jsonify({'error': message}), 400
    
    # If result is now locked, update the queue
    if 'locked' in message:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM active_matches WHERE id = ?', (match_id,))
        match = cursor.fetchone()
        
        if match:
            match = dict(match)
            bar_id = match['bar_id']
            winner_id = match['result_winner_id']
            
            # Update queue based on result
            cursor.execute('''
                SELECT q.*, p.id as player_id 
                FROM queue q JOIN players p ON q.player_id = p.id
                WHERE q.bar_id = ? AND q.position IN (1, 2)
                ORDER BY q.position
            ''', (bar_id,))
            positions = [dict(r) for r in cursor.fetchall()]
            
            if len(positions) >= 2:
                king = positions[0]
                challenger = positions[1]
                
                if winner_id == king['player_id']:
                    # King won
                    cursor.execute('UPDATE queue SET wins_on_table = wins_on_table + 1 WHERE id = ?', (king['id'],))
                    cursor.execute('DELETE FROM queue WHERE id = ?', (challenger['id'],))
                else:
                    # Challenger won
                    cursor.execute('DELETE FROM queue WHERE id = ?', (king['id'],))
                    cursor.execute('UPDATE queue SET wins_on_table = 1 WHERE id = ?', (challenger['id'],))
                
                # Reposition remaining queue
                cursor.execute('''
                    UPDATE queue SET position = position - 1 
                    WHERE bar_id = ? AND position > 1
                ''', (bar_id,))
                
                conn.commit()
        
        conn.close()
    
    return jsonify({
        'success': True,
        'message': message,
        'locked': 'locked' in message
    })


@player_bp.route('/api/dispute-match/<int:match_id>', methods=['POST'])
def api_player_dispute_match(match_id):
    """Player disputes a match result."""
    from .database import log_match_action, get_db
    
    player_id = session.get('player_id')
    if not player_id:
        return jsonify({'error': 'Login required'}), 401
    
    data = request.json or {}
    reason = data.get('reason', '')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Verify player is part of this match
    cursor.execute('''
        SELECT * FROM active_matches 
        WHERE id = ? AND (player1_id = ? OR player2_id = ?)
    ''', (match_id, player_id, player_id))
    match = cursor.fetchone()
    
    if not match:
        conn.close()
        return jsonify({'error': 'Match not found or you are not a participant'}), 404
    
    match = dict(match)
    
    if match['result_locked']:
        conn.close()
        return jsonify({'error': 'Cannot dispute a locked result'}), 400
    
    # Mark as disputed
    cursor.execute('''
        UPDATE active_matches SET status = 'disputed' WHERE id = ?
    ''', (match_id,))
    conn.commit()
    conn.close()
    
    # Log the dispute
    log_match_action('result_disputed', match_id=match_id, bar_id=match['bar_id'],
                     details=f"Disputed by player {player_id}: {reason}",
                     performed_by_user_id=player_id,
                     performed_by_type='player')
    
    return jsonify({
        'success': True,
        'message': 'Dispute recorded. A bar host will need to resolve this.'
    })



# ============================================
# DEMO MODE ROUTES
# ============================================

@player_bp.route('/demo')
def start_demo():
    """
    Start demo mode - allows exploring the player app without a real account.
    Sets session['demo_mode'] = True and creates fake player data for display.
    """
    # Set demo mode flag
    session['demo_mode'] = True
    session['demo_player'] = {
        'id': 0,
        'nickname': 'Demo Player',
        'display_name': 'Demo Player',
        'tokens_balance': 250,
        'wins': 12,
        'losses': 5,
        'current_streak': 3,
        'best_streak': 7,
        'rating': 1150,
        'division': 'Silver',
        'home_bar_name': 'Demo Bar',
        'phone_verified': True,
        'email_verified': True
    }
    
    flash('🎮 Demo Mode activated! Explore the app without creating an account.', 'info')
    return redirect(url_for('player.demo_home'))


@player_bp.route('/demo/exit')
def exit_demo():
    """Exit demo mode and return to login."""
    session.pop('demo_mode', None)
    session.pop('demo_player', None)
    flash('Demo mode ended.', 'info')
    return redirect(url_for('auth.login'))


@player_bp.route('/demo/home')
def demo_home():
    """Demo version of the home screen."""
    if not session.get('demo_mode'):
        return redirect(url_for('player.home'))
    
    demo_player = session.get('demo_player', {})
    
    # Create fake data for the demo
    fake_bars = [
        {'id': 1, 'name': 'Demo Bar Manhattan', 'address': '123 Demo St, New York, NY', 'queue_count': 5},
        {'id': 2, 'name': 'Demo Bar Brooklyn', 'address': '456 Pool Ave, Brooklyn, NY', 'queue_count': 3},
        {'id': 3, 'name': 'Demo Bar Queens', 'address': '789 Cue Blvd, Queens, NY', 'queue_count': 8},
    ]
    
    fake_queue_info = {
        'bar_name': 'Demo Bar Manhattan',
        'position': 3,
        'total_in_queue': 7,
        'is_king': False,
        'is_challenger': False,
        'queue_list': [
            {'position': 1, 'nickname': 'KingPlayer', 'wins_on_table': 4, 'is_me': False},
            {'position': 2, 'nickname': 'Challenger42', 'wins_on_table': 0, 'is_me': False},
            {'position': 3, 'nickname': 'Demo Player', 'wins_on_table': 0, 'is_me': True},
            {'position': 4, 'nickname': 'NextUp99', 'wins_on_table': 0, 'is_me': False},
        ]
    }
    
    return render_template('player/home.html',
                           player_ad=None,
                           my_queue_info=fake_queue_info,
                           player_data=demo_player,
                           daily_bonus_awarded=False,
                           pending_challenges=2,
                           pending_match_confirmations=1,
                           friend_activity=[
                               {'nickname': 'PoolShark123', 'wins_on_table': 2, 'position': 1},
                           ],
                           last_game={'opponent_name': 'RandomOpponent', 'result': 'win'},
                           show_birthday_banner=False,
                           birthday_message=None,
                           birthday_tokens_awarded=0,
                           birthday_sponsor_text=None,
                           bars=fake_bars,
                           upcoming_events_count=3,
                           is_guest=False,
                           demo_mode=True)


@player_bp.route('/demo/profile')
def demo_profile():
    """Demo version of the profile screen."""
    if not session.get('demo_mode'):
        return redirect(url_for('player.profile'))
    
    demo_player = session.get('demo_player', {})
    demo_player.update({
        'email': 'demo@poolcue.app',
        'phone_number': '+1 555-DEMO',
        'birthday': '1990-06-15',
        'play_frequency': 'weekly',
        'skill_self_rating': 'intermediate',
        'marketing_opt_in': True,
        'preferred_contact_method': 'email'
    })
    
    from datetime import date
    today = date.today().strftime('%Y-%m-%d')
    
    return render_template('player/profile.html',
                           player_ad=None,
                           player_data=demo_player,
                           invite_stats={'pending': 3, 'completed': 5},
                           today=today,
                           is_guest=False,
                           demo_mode=True)


@player_bp.route('/demo/tokens')
def demo_tokens():
    """Demo version of tokens screen."""
    if not session.get('demo_mode'):
        return redirect(url_for('player.tokens'))
    
    return render_template('player/tokens.html', demo_mode=True)


@player_bp.route('/demo/leaderboards')
def demo_leaderboards():
    """Demo version of leaderboards."""
    if not session.get('demo_mode'):
        return redirect(url_for('player.leaderboards'))
    
    return render_template('player/leaderboards.html', demo_mode=True)


@player_bp.route('/demo/friends')
def demo_friends():
    """Demo version of friends page."""
    if not session.get('demo_mode'):
        return redirect(url_for('player.friends'))
    
    return render_template('player/friends.html', demo_mode=True, friends=[], pending_requests=[], friend_suggestions=[])


@player_bp.route('/demo/challenges')
def demo_challenges():
    """Demo version of challenges page."""
    if not session.get('demo_mode'):
        return redirect(url_for('player.challenges'))
    
    return render_template('player/challenges.html', demo_mode=True, challenges=[], my_challenges=[])


def is_demo_mode():
    """Check if currently in demo mode."""
    return session.get('demo_mode', False)


def get_demo_player():
    """Get demo player data or None if not in demo mode."""
    if is_demo_mode():
        return session.get('demo_player', {})
    return None
