"""
Pool Cue - Self-Serve Marketer/Advertiser System

This module handles:
- Marketer account management (separate from players)
- Self-serve campaign creation with approval workflow
- Pricing models for board ads (CPM-based)
- Billing stubs for future payment integration

ROLES:
- Player: Regular app user (players table)
- Marketer: Business account for ad buyers (marketer_accounts table)
- Admin: Pool Cue staff (uses master dashboard)
"""
import sqlite3
import secrets
import hashlib
from datetime import datetime, timedelta
from .database import get_db


# =============================================================================
# PRICING CONFIGURATION
# =============================================================================

# CPM (Cost Per Mille / 1000 impressions) by placement type
# Board ads are non-clickable, so priced purely on impressions + estimated reach
PLACEMENT_CPM = {
    'board_main': 15.00,          # $15 per 1000 impressions - premium TV placement
    'board_idle': 10.00,          # $10 per 1000 - idle screen, less attention
    'board_between_games': 20.00, # $20 per 1000 - high attention moment
    'board_winner': 25.00,        # $25 per 1000 - winner sees, high engagement
    'board_loser': 12.00,         # $12 per 1000 - loser screen
    'player_home': 8.00,          # $8 per 1000 - in-app banner
    'player_queue': 6.00,         # $6 per 1000 - queue status page
    'join_page': 5.00,            # $5 per 1000 - join landing
    'join_success': 10.00,        # $10 per 1000 - confirmation, good attention
    'match_result': 15.00,        # $15 per 1000 - post-game, engaged audience
}

# Estimated viewers per impression for board placements
# Used to calculate "reach" - how many eyeballs per logged impression
ESTIMATED_VIEWERS_PER_IMPRESSION = {
    'board_main': 3.0,            # Avg 3 people watching the board
    'board_idle': 2.0,
    'board_between_games': 4.0,   # More attention between games
    'board_winner': 2.0,
    'board_loser': 1.5,
    'player_home': 1.0,           # Personal device = 1 viewer
    'player_queue': 1.0,
    'join_page': 1.0,
    'join_success': 1.0,
    'match_result': 1.5,          # Sometimes shown to opponent too
}

# Flat package pricing (alternative to CPM)
PACKAGE_PRICING = {
    'bar_daily': 50.00,           # $50/day at one bar, all placements
    'bar_weekly': 250.00,         # $250/week at one bar
    'bar_monthly': 800.00,        # $800/month at one bar
    'network_daily': 200.00,      # $200/day across all bars
    'network_weekly': 1000.00,    # $1000/week across all bars
    'network_monthly': 3500.00,   # $3500/month across all bars
}

# Campaign approval states
CAMPAIGN_STATUS = {
    'draft': 'Draft - Not submitted',
    'pending_review': 'Pending Review - Awaiting approval',
    'approved': 'Approved - Ready to run',
    'active': 'Active - Currently running',
    'paused': 'Paused - Temporarily stopped',
    'rejected': 'Rejected - Did not pass review',
    'completed': 'Completed - Campaign ended',
}


# =============================================================================
# DATABASE INITIALIZATION
# =============================================================================

def init_marketer_tables():
    """
    Create tables for the self-serve marketer system.
    
    This creates:
    - marketer_accounts: Business accounts (separate from players)
    - Extends campaigns table with approval/pricing fields
    - billing_transactions: Stub for payment tracking
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Marketer accounts - businesses/advertisers who can self-serve
    # Separate from players table to keep concerns separated
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS marketer_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            
            -- Business info
            business_name TEXT NOT NULL,
            business_category TEXT,
            website TEXT,
            
            -- Contact info
            contact_name TEXT NOT NULL,
            contact_email TEXT UNIQUE NOT NULL,
            contact_phone TEXT,
            
            -- Auth
            password_hash TEXT NOT NULL,
            session_token TEXT,
            
            -- Billing (stub for future Stripe integration)
            stripe_customer_id TEXT,
            billing_email TEXT,
            credits_balance REAL DEFAULT 0.0,
            
            -- Status
            is_verified INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            verification_token TEXT,
            
            -- Timestamps
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_login_at DATETIME,
            
            -- Link to advertisers table (for campaigns)
            advertiser_id INTEGER,
            FOREIGN KEY (advertiser_id) REFERENCES advertisers(id)
        )
    ''')
    
    # Add approval fields to campaigns if not exists
    try:
        cursor.execute('ALTER TABLE campaigns ADD COLUMN approval_status TEXT DEFAULT "draft"')
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    try:
        cursor.execute('ALTER TABLE campaigns ADD COLUMN submitted_at DATETIME')
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute('ALTER TABLE campaigns ADD COLUMN reviewed_at DATETIME')
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute('ALTER TABLE campaigns ADD COLUMN reviewed_by TEXT')
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute('ALTER TABLE campaigns ADD COLUMN rejection_reason TEXT')
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute('ALTER TABLE campaigns ADD COLUMN pricing_model TEXT DEFAULT "cpm"')
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute('ALTER TABLE campaigns ADD COLUMN total_spend REAL DEFAULT 0.0')
    except sqlite3.OperationalError:
        pass
    
    # Billing transactions - stub for payment tracking
    # TODO: Integrate with Stripe when ready
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS billing_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            marketer_id INTEGER NOT NULL,
            campaign_id INTEGER,
            
            -- Transaction details
            transaction_type TEXT NOT NULL,  -- 'charge', 'refund', 'credit_add', 'credit_use'
            amount REAL NOT NULL,
            currency TEXT DEFAULT 'USD',
            description TEXT,
            
            -- Payment processor info (stub)
            stripe_payment_id TEXT,
            stripe_invoice_id TEXT,
            
            -- Status
            status TEXT DEFAULT 'pending',  -- pending, completed, failed, refunded
            
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            
            FOREIGN KEY (marketer_id) REFERENCES marketer_accounts(id),
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
        )
    ''')
    
    # Indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_marketer_email ON marketer_accounts(contact_email)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_marketer_session ON marketer_accounts(session_token)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_billing_marketer ON billing_transactions(marketer_id)')
    
    conn.commit()
    conn.close()


# =============================================================================
# MARKETER ACCOUNT MANAGEMENT
# =============================================================================

def hash_password(password):
    """Secure password hashing using scrypt."""
    from werkzeug.security import generate_password_hash
    return generate_password_hash(password, method='scrypt')


def verify_password(stored_hash, password):
    """Verify password against stored hash (supports legacy SHA256 and new scrypt)."""
    from werkzeug.security import check_password_hash
    # Try scrypt first (new format)
    if stored_hash.startswith('scrypt:'):
        return check_password_hash(stored_hash, password)
    # Fall back to legacy SHA256 for old accounts
    return stored_hash == hashlib.sha256(password.encode()).hexdigest()


def create_marketer_account(business_name, contact_name, contact_email, password, 
                            business_category=None, website=None, contact_phone=None):
    """
    Create a new marketer account.
    Also creates a linked advertiser record for campaign management.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # First create an advertiser record (for campaign linking)
        cursor.execute('''
            INSERT INTO advertisers (name, category, contact_name, contact_email, website)
            VALUES (?, ?, ?, ?, ?)
        ''', (business_name, business_category, contact_name, contact_email, website))
        advertiser_id = cursor.lastrowid
        
        # Create the marketer account
        verification_token = secrets.token_urlsafe(32)
        cursor.execute('''
            INSERT INTO marketer_accounts 
            (business_name, business_category, website, contact_name, contact_email, 
             contact_phone, password_hash, verification_token, advertiser_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (business_name, business_category, website, contact_name, contact_email,
              contact_phone, hash_password(password), verification_token, advertiser_id))
        
        marketer_id = cursor.lastrowid
        conn.commit()
        
        return {
            'success': True,
            'marketer_id': marketer_id,
            'advertiser_id': advertiser_id,
            'verification_token': verification_token
        }
    except sqlite3.IntegrityError as e:
        return {'success': False, 'error': 'Email already registered'}
    finally:
        conn.close()


def authenticate_marketer(email, password):
    """
    Authenticate a marketer and create a session.
    Returns session token on success.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, password_hash, is_active, is_verified, business_name, advertiser_id
        FROM marketer_accounts WHERE contact_email = ?
    ''', (email,))
    account = cursor.fetchone()
    
    if not account:
        conn.close()
        return {'success': False, 'error': 'Invalid email or password'}
    
    if not verify_password(account['password_hash'], password):
        conn.close()
        return {'success': False, 'error': 'Invalid email or password'}
    
    if not account['is_active']:
        conn.close()
        return {'success': False, 'error': 'Account is deactivated'}
    
    # Create session token
    session_token = secrets.token_urlsafe(32)
    cursor.execute('''
        UPDATE marketer_accounts 
        SET session_token = ?, last_login_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (session_token, account['id']))
    conn.commit()
    conn.close()
    
    return {
        'success': True,
        'session_token': session_token,
        'marketer_id': account['id'],
        'advertiser_id': account['advertiser_id'],
        'business_name': account['business_name'],
        'is_verified': account['is_verified']
    }


def get_marketer_by_session(session_token):
    """Get marketer account from session token."""
    if not session_token:
        return None
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM marketer_accounts WHERE session_token = ? AND is_active = 1
    ''', (session_token,))
    account = cursor.fetchone()
    conn.close()
    return dict(account) if account else None


def get_marketer_by_id(marketer_id):
    """Get marketer account by ID."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM marketer_accounts WHERE id = ?', (marketer_id,))
    account = cursor.fetchone()
    conn.close()
    return dict(account) if account else None


def logout_marketer(session_token):
    """Clear session token to log out."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE marketer_accounts SET session_token = NULL WHERE session_token = ?', 
                   (session_token,))
    conn.commit()
    conn.close()


# =============================================================================
# CAMPAIGN MANAGEMENT (SELF-SERVE)
# =============================================================================

def create_self_serve_campaign(advertiser_id, name, placements, bar_ids=None,
                               start_date=None, end_date=None, budget=None,
                               pricing_model='cpm'):
    """
    Create a new campaign in DRAFT status.
    Marketer can edit until they submit for review.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO campaigns 
        (advertiser_id, name, start_date, end_date, budget, status, approval_status, pricing_model)
        VALUES (?, ?, ?, ?, ?, 'draft', 'draft', ?)
    ''', (advertiser_id, name, start_date, end_date, budget, pricing_model))
    
    campaign_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return campaign_id


def submit_campaign_for_review(campaign_id):
    """
    Submit a campaign for admin approval.
    Changes status from 'draft' to 'pending_review'.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Verify campaign has at least one creative
    cursor.execute('SELECT COUNT(*) as cnt FROM ad_creatives WHERE campaign_id = ?', (campaign_id,))
    if cursor.fetchone()['cnt'] == 0:
        conn.close()
        return {'success': False, 'error': 'Campaign must have at least one creative'}
    
    cursor.execute('''
        UPDATE campaigns 
        SET approval_status = 'pending_review', submitted_at = CURRENT_TIMESTAMP
        WHERE id = ? AND approval_status = 'draft'
    ''', (campaign_id,))
    
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    
    return {'success': updated, 'error': None if updated else 'Campaign not in draft status'}


def approve_campaign(campaign_id, reviewer_name):
    """Admin approves a campaign. It can now go live."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE campaigns 
        SET approval_status = 'approved', status = 'active',
            reviewed_at = CURRENT_TIMESTAMP, reviewed_by = ?
        WHERE id = ? AND approval_status = 'pending_review'
    ''', (reviewer_name, campaign_id))
    
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    
    return updated


def reject_campaign(campaign_id, reviewer_name, reason):
    """Admin rejects a campaign with a reason."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE campaigns 
        SET approval_status = 'rejected', status = 'paused',
            reviewed_at = CURRENT_TIMESTAMP, reviewed_by = ?,
            rejection_reason = ?
        WHERE id = ? AND approval_status = 'pending_review'
    ''', (reviewer_name, reason, campaign_id))
    
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    
    return updated


def get_pending_campaigns():
    """Get all campaigns pending admin review."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT c.*, a.name as advertiser_name, a.contact_email,
               COUNT(DISTINCT ac.id) as creative_count
        FROM campaigns c
        JOIN advertisers a ON a.id = c.advertiser_id
        LEFT JOIN ad_creatives ac ON ac.campaign_id = c.id
        WHERE c.approval_status = 'pending_review'
        GROUP BY c.id
        ORDER BY c.submitted_at ASC
    ''')
    
    campaigns = cursor.fetchall()
    conn.close()
    return campaigns


def get_marketer_campaigns(advertiser_id):
    """Get all campaigns for a marketer's advertiser account."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT c.*,
               COUNT(DISTINCT ac.id) as creative_count,
               COALESCE(SUM(ae.impressions), 0) as total_impressions,
               COALESCE(SUM(ae.clicks), 0) as total_clicks
        FROM campaigns c
        LEFT JOIN ad_creatives ac ON ac.campaign_id = c.id
        LEFT JOIN (
            SELECT campaign_id,
                   COUNT(CASE WHEN event_type = 'impression' THEN 1 END) as impressions,
                   COUNT(CASE WHEN event_type = 'click' THEN 1 END) as clicks
            FROM ad_events
            GROUP BY campaign_id
        ) ae ON ae.campaign_id = c.id
        WHERE c.advertiser_id = ?
        GROUP BY c.id
        ORDER BY c.created_at DESC
    ''', (advertiser_id,))
    
    campaigns = cursor.fetchall()
    conn.close()
    return campaigns


# =============================================================================
# PRICING & BILLING
# =============================================================================

def calculate_campaign_cost(campaign_id):
    """
    Calculate the cost of a campaign based on impressions delivered.
    
    For board ads (non-clickable), we charge based on:
    - CPM (cost per 1000 impressions) by placement type
    - Estimated reach (impressions × viewers per impression)
    
    Returns detailed breakdown for transparency.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Get impressions by placement
    cursor.execute('''
        SELECT placement, COUNT(*) as impressions
        FROM ad_events
        WHERE campaign_id = ? AND event_type = 'impression'
        GROUP BY placement
    ''', (campaign_id,))
    
    placement_data = cursor.fetchall()
    conn.close()
    
    breakdown = []
    total_cost = 0.0
    total_impressions = 0
    total_reach = 0
    
    for row in placement_data:
        placement = row['placement']
        impressions = row['impressions']
        
        cpm = PLACEMENT_CPM.get(placement, 5.00)  # Default $5 CPM
        viewers_per = ESTIMATED_VIEWERS_PER_IMPRESSION.get(placement, 1.0)
        
        cost = (impressions / 1000) * cpm
        reach = int(impressions * viewers_per)
        
        breakdown.append({
            'placement': placement,
            'impressions': impressions,
            'cpm': cpm,
            'cost': round(cost, 2),
            'estimated_reach': reach
        })
        
        total_cost += cost
        total_impressions += impressions
        total_reach += reach
    
    return {
        'breakdown': breakdown,
        'total_impressions': total_impressions,
        'total_estimated_reach': total_reach,
        'total_cost': round(total_cost, 2),
        'currency': 'USD'
    }


def get_placement_pricing():
    """Get current pricing for all placements (for display to marketers)."""
    pricing = []
    for placement, cpm in PLACEMENT_CPM.items():
        viewers = ESTIMATED_VIEWERS_PER_IMPRESSION.get(placement, 1.0)
        
        # Determine if this is a board placement (non-clickable)
        is_board = placement.startswith('board_')
        
        pricing.append({
            'placement': placement,
            'display_name': placement.replace('_', ' ').title(),
            'cpm': cpm,
            'estimated_viewers': viewers,
            'is_clickable': not is_board,
            'description': _get_placement_description(placement)
        })
    
    return pricing


def _get_placement_description(placement):
    """Get human-readable description for a placement."""
    descriptions = {
        'board_main': 'Main TV/projector display rotation - visible to everyone at the table',
        'board_idle': 'Shown when queue is empty or inactive',
        'board_between_games': 'Premium placement between games when attention is highest',
        'board_winner': 'Shown to the winning player - positive association',
        'board_loser': 'Shown to the losing player after defeat',
        'player_home': 'Banner on player app home screen',
        'player_queue': 'Shown while player is waiting in queue',
        'join_page': 'Landing page when scanning QR code to join',
        'join_success': 'Confirmation screen after joining queue',
        'match_result': 'Post-game result screen in player app',
    }
    return descriptions.get(placement, '')


def get_package_pricing():
    """Get flat-rate package options."""
    packages = []
    for package_id, price in PACKAGE_PRICING.items():
        parts = package_id.split('_')
        scope = parts[0]  # 'bar' or 'network'
        duration = parts[1]  # 'daily', 'weekly', 'monthly'
        
        packages.append({
            'id': package_id,
            'scope': scope,
            'duration': duration,
            'price': price,
            'display_name': f"{'Single Bar' if scope == 'bar' else 'Full Network'} - {duration.title()}",
            'description': f"All placements at {'one bar' if scope == 'bar' else 'all bars'} for {'1 day' if duration == 'daily' else '1 week' if duration == 'weekly' else '1 month'}"
        })
    
    return packages


# =============================================================================
# BILLING STUBS (TODO: Integrate with Stripe)
# =============================================================================

def add_credits(marketer_id, amount, description='Credit purchase'):
    """
    Add credits to a marketer's account.
    
    TODO: This should be called after successful Stripe payment.
    For now, just updates the balance.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Record transaction
    cursor.execute('''
        INSERT INTO billing_transactions 
        (marketer_id, transaction_type, amount, description, status)
        VALUES (?, 'credit_add', ?, ?, 'completed')
    ''', (marketer_id, amount, description))
    
    # Update balance
    cursor.execute('''
        UPDATE marketer_accounts 
        SET credits_balance = credits_balance + ?
        WHERE id = ?
    ''', (amount, marketer_id))
    
    conn.commit()
    conn.close()
    
    return True


def charge_campaign(campaign_id):
    """
    Charge a marketer for campaign impressions.
    
    TODO: Integrate with Stripe for real payments.
    For now, deducts from credits balance.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Get campaign cost
    cost_data = calculate_campaign_cost(campaign_id)
    amount = cost_data['total_cost']
    
    # Get marketer ID
    cursor.execute('''
        SELECT ma.id as marketer_id, ma.credits_balance, c.advertiser_id
        FROM campaigns c
        JOIN advertisers a ON a.id = c.advertiser_id
        JOIN marketer_accounts ma ON ma.advertiser_id = a.id
        WHERE c.id = ?
    ''', (campaign_id,))
    
    result = cursor.fetchone()
    if not result:
        conn.close()
        return {'success': False, 'error': 'Campaign not found'}
    
    marketer_id = result['marketer_id']
    balance = result['credits_balance']
    
    if balance < amount:
        conn.close()
        return {'success': False, 'error': f'Insufficient credits. Need ${amount:.2f}, have ${balance:.2f}'}
    
    # Deduct credits
    cursor.execute('''
        UPDATE marketer_accounts 
        SET credits_balance = credits_balance - ?
        WHERE id = ?
    ''', (amount, marketer_id))
    
    # Record transaction
    cursor.execute('''
        INSERT INTO billing_transactions 
        (marketer_id, campaign_id, transaction_type, amount, description, status)
        VALUES (?, ?, 'credit_use', ?, ?, 'completed')
    ''', (marketer_id, campaign_id, amount, f'Campaign charges: {cost_data["total_impressions"]} impressions'))
    
    # Update campaign spend
    cursor.execute('UPDATE campaigns SET total_spend = total_spend + ? WHERE id = ?', (amount, campaign_id))
    
    conn.commit()
    conn.close()
    
    return {'success': True, 'amount_charged': amount}


def get_marketer_billing_history(marketer_id, limit=50):
    """Get billing transaction history for a marketer."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT bt.*, c.name as campaign_name
        FROM billing_transactions bt
        LEFT JOIN campaigns c ON c.id = bt.campaign_id
        WHERE bt.marketer_id = ?
        ORDER BY bt.created_at DESC
        LIMIT ?
    ''', (marketer_id, limit))
    
    transactions = cursor.fetchall()
    conn.close()
    return transactions


# =============================================================================
# MARKETER ANALYTICS
# =============================================================================

def get_marketer_dashboard_stats(advertiser_id, days=30):
    """
    Get dashboard statistics for a marketer.
    Shows impressions, estimated reach, spend, and performance by placement.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    # Overall stats
    cursor.execute('''
        SELECT 
            COUNT(CASE WHEN event_type = 'impression' THEN 1 END) as impressions,
            COUNT(CASE WHEN event_type = 'click' THEN 1 END) as clicks,
            COUNT(DISTINCT player_id) as unique_viewers,
            COUNT(DISTINCT bar_id) as bars_reached
        FROM ad_events
        WHERE advertiser_id = ? AND DATE(created_at) >= ?
    ''', (advertiser_id, since))
    
    totals = cursor.fetchone()
    
    # Calculate estimated reach and cost
    cursor.execute('''
        SELECT placement, COUNT(*) as impressions
        FROM ad_events
        WHERE advertiser_id = ? AND event_type = 'impression' AND DATE(created_at) >= ?
        GROUP BY placement
    ''', (advertiser_id, since))
    
    placement_stats = cursor.fetchall()
    
    total_reach = 0
    total_cost = 0.0
    by_placement = []
    
    for row in placement_stats:
        placement = row['placement']
        impressions = row['impressions']
        viewers = ESTIMATED_VIEWERS_PER_IMPRESSION.get(placement, 1.0)
        cpm = PLACEMENT_CPM.get(placement, 5.0)
        
        reach = int(impressions * viewers)
        cost = (impressions / 1000) * cpm
        
        total_reach += reach
        total_cost += cost
        
        by_placement.append({
            'placement': placement,
            'display_name': placement.replace('_', ' ').title(),
            'impressions': impressions,
            'estimated_reach': reach,
            'cost': round(cost, 2)
        })
    
    # Daily trend
    cursor.execute('''
        SELECT DATE(created_at) as date,
               COUNT(CASE WHEN event_type = 'impression' THEN 1 END) as impressions,
               COUNT(CASE WHEN event_type = 'click' THEN 1 END) as clicks
        FROM ad_events
        WHERE advertiser_id = ? AND DATE(created_at) >= ?
        GROUP BY DATE(created_at)
        ORDER BY date ASC
    ''', (advertiser_id, since))
    
    daily_data = cursor.fetchall()
    
    # Campaign breakdown
    cursor.execute('''
        SELECT c.id, c.name, c.status, c.approval_status,
               COUNT(CASE WHEN ae.event_type = 'impression' THEN 1 END) as impressions,
               COUNT(CASE WHEN ae.event_type = 'click' THEN 1 END) as clicks
        FROM campaigns c
        LEFT JOIN ad_events ae ON ae.campaign_id = c.id AND DATE(ae.created_at) >= ?
        WHERE c.advertiser_id = ?
        GROUP BY c.id
        ORDER BY impressions DESC
    ''', (since, advertiser_id))
    
    campaigns = cursor.fetchall()
    
    conn.close()
    
    impressions = totals['impressions'] or 0
    clicks = totals['clicks'] or 0
    
    return {
        'period_days': days,
        'impressions': impressions,
        'clicks': clicks,
        'ctr': round((clicks / impressions * 100) if impressions > 0 else 0, 2),
        'estimated_reach': total_reach,
        'estimated_cost': round(total_cost, 2),
        'unique_viewers': totals['unique_viewers'] or 0,
        'bars_reached': totals['bars_reached'] or 0,
        'by_placement': by_placement,
        'daily_data': [dict(row) for row in daily_data],
        'campaigns': [dict(row) for row in campaigns]
    }


def get_campaign_detail_stats(campaign_id, days=30):
    """Get detailed stats for a single campaign."""
    conn = get_db()
    cursor = conn.cursor()
    
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    # Campaign info
    cursor.execute('''
        SELECT c.*, a.name as advertiser_name
        FROM campaigns c
        JOIN advertisers a ON a.id = c.advertiser_id
        WHERE c.id = ?
    ''', (campaign_id,))
    campaign = cursor.fetchone()
    
    if not campaign:
        conn.close()
        return None
    
    # Stats by bar
    cursor.execute('''
        SELECT b.id, b.name,
               COUNT(CASE WHEN ae.event_type = 'impression' THEN 1 END) as impressions,
               COUNT(CASE WHEN ae.event_type = 'click' THEN 1 END) as clicks,
               COUNT(DISTINCT ae.player_id) as unique_viewers
        FROM ad_events ae
        JOIN bars b ON b.id = ae.bar_id
        WHERE ae.campaign_id = ? AND DATE(ae.created_at) >= ?
        GROUP BY b.id
        ORDER BY impressions DESC
    ''', (campaign_id, since))
    by_bar = cursor.fetchall()
    
    # Stats by creative
    cursor.execute('''
        SELECT ac.id, ac.file_name, ac.label,
               COUNT(CASE WHEN ae.event_type = 'impression' THEN 1 END) as impressions,
               COUNT(CASE WHEN ae.event_type = 'click' THEN 1 END) as clicks
        FROM ad_creatives ac
        LEFT JOIN ad_events ae ON ae.ad_id = ac.id AND DATE(ae.created_at) >= ?
        WHERE ac.campaign_id = ?
        GROUP BY ac.id
        ORDER BY impressions DESC
    ''', (since, campaign_id))
    by_creative = cursor.fetchall()
    
    # Hourly distribution
    cursor.execute('''
        SELECT strftime('%H', created_at) as hour,
               COUNT(*) as impressions
        FROM ad_events
        WHERE campaign_id = ? AND event_type = 'impression' AND DATE(created_at) >= ?
        GROUP BY strftime('%H', created_at)
        ORDER BY hour
    ''', (campaign_id, since))
    by_hour = cursor.fetchall()
    
    conn.close()
    
    # Calculate costs
    cost_data = calculate_campaign_cost(campaign_id)
    
    return {
        'campaign': dict(campaign),
        'by_bar': [dict(row) for row in by_bar],
        'by_creative': [dict(row) for row in by_creative],
        'by_hour': [dict(row) for row in by_hour],
        'cost_breakdown': cost_data
    }


# =============================================================================
# PLACEMENT TYPES & AD FORMATS
# =============================================================================

# All supported placements with metadata
ALL_PLACEMENTS = {
    # Board placements (non-clickable, TV/projector)
    'board_main': {
        'name': 'Board Main Rotation',
        'type': 'board',
        'clickable': False,
        'formats': ['image'],
        'dimensions': '1920x1080',
        'description': 'Main display rotation visible to everyone at the table'
    },
    'board_idle': {
        'name': 'Board Idle Screen',
        'type': 'board',
        'clickable': False,
        'formats': ['image'],
        'dimensions': '1920x1080',
        'description': 'Shown when queue is empty'
    },
    'board_between_games': {
        'name': 'Between Games',
        'type': 'board',
        'clickable': False,
        'formats': ['image'],
        'dimensions': '1920x1080',
        'description': 'Premium placement when game ends'
    },
    'board_winner': {
        'name': 'Winner Screen',
        'type': 'board',
        'clickable': False,
        'formats': ['image'],
        'dimensions': '1920x1080',
        'description': 'Shown to winning player'
    },
    'board_loser': {
        'name': 'Loser Screen',
        'type': 'board',
        'clickable': False,
        'formats': ['image'],
        'dimensions': '1920x1080',
        'description': 'Shown to losing player'
    },
    
    # In-app placements (clickable)
    'player_home': {
        'name': 'Player App Home',
        'type': 'app',
        'clickable': True,
        'formats': ['image', 'text'],
        'dimensions': '320x100',
        'description': 'Banner on player home screen'
    },
    'player_queue': {
        'name': 'Queue Status',
        'type': 'app',
        'clickable': True,
        'formats': ['image', 'text'],
        'dimensions': '320x100',
        'description': 'Shown while waiting in queue'
    },
    'join_page': {
        'name': 'Join Page',
        'type': 'web',
        'clickable': True,
        'formats': ['image', 'text'],
        'dimensions': '320x100',
        'description': 'QR code landing page'
    },
    'join_success': {
        'name': 'Join Success',
        'type': 'web',
        'clickable': True,
        'formats': ['image', 'text'],
        'dimensions': '320x250',
        'description': 'Queue join confirmation'
    },
    'match_result': {
        'name': 'Match Result',
        'type': 'app',
        'clickable': True,
        'formats': ['image', 'text'],
        'dimensions': '320x250',
        'description': 'Post-game result screen'
    },
}


def get_all_placements():
    """Get all available placements with their details."""
    return ALL_PLACEMENTS
