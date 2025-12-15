"""
Pool Cue - Marketer Portal Routes

Self-serve advertising portal for businesses to:
- Create and manage ad campaigns
- View performance analytics
- Upload creatives
- Purchase ad credits

Separate from player routes - marketers have their own login.
"""
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, session, flash
from functools import wraps
import os

from .marketer_system import (
    create_marketer_account, authenticate_marketer, get_marketer_by_session,
    logout_marketer, create_self_serve_campaign, submit_campaign_for_review,
    get_marketer_campaigns, get_marketer_dashboard_stats, get_campaign_detail_stats,
    get_placement_pricing, get_package_pricing, get_all_placements,
    add_credits, get_marketer_billing_history, calculate_campaign_cost
)
from .advertiser_system import add_creative, set_placements, get_advertiser_details
from .database import get_db

market_bp = Blueprint('market', __name__, url_prefix='/market')


# =============================================================================
# PUBLIC LANDING PAGE
# =============================================================================

@market_bp.route('/advertise')
def advertise_landing():
    """Public landing page for advertisers - the pitch."""
    # Get some stats to show
    conn = get_db()
    cursor = conn.cursor()
    
    stats = {'bars': 24, 'impressions': 0, 'players': 0, 'avg_dwell': '45+'}
    
    try:
        cursor.execute('SELECT COUNT(*) FROM bars WHERE is_active = 1 OR is_active IS NULL')
        stats['bars'] = cursor.fetchone()[0] or 24
        
        cursor.execute('SELECT COUNT(*) FROM ad_events WHERE created_at >= datetime("now", "-30 days")')
        stats['impressions'] = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT COUNT(*) FROM players WHERE is_active = 1 OR is_active IS NULL')
        stats['players'] = cursor.fetchone()[0] or 0
    except:
        pass
    finally:
        conn.close()
    
    return render_template('market/advertise.html', stats=stats)


# Also make it available at /advertise (without /market prefix)
# This is handled by adding a route in routes_public.py


# =============================================================================
# AUTH DECORATOR
# =============================================================================

# BETA MODE: Set to True to bypass login requirement
BETA_MODE = False  # SECURITY: Disabled for production

def marketer_required(f):
    """Decorator to require marketer authentication (bypassed in beta mode)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Beta mode - create/use a demo marketer
        if BETA_MODE:
            session_token = session.get('marketer_token')
            marketer = get_marketer_by_session(session_token) if session_token else None
            
            if not marketer:
                # Get or create a demo marketer account
                conn = get_db()
                cursor = conn.cursor()
                
                # First ensure table exists
                try:
                    from .marketer_system import init_marketer_tables
                    init_marketer_tables()
                except:
                    pass
                
                # Check for existing demo account
                cursor.execute('SELECT * FROM marketer_accounts WHERE contact_email = ?', ('demo@poolcue.nyc',))
                demo = cursor.fetchone()
                
                if not demo:
                    # Create demo account
                    cursor.execute('''
                        INSERT INTO marketer_accounts (business_name, contact_name, contact_email, password_hash, is_active, created_at)
                        VALUES (?, ?, ?, ?, 1, datetime('now'))
                    ''', ('Demo Account', 'Demo User', 'demo@poolcue.nyc', 'beta_demo'))
                    marketer_id = cursor.lastrowid
                    
                    # Create linked advertiser
                    cursor.execute('''
                        INSERT INTO advertisers (name, category, is_active, created_at)
                        VALUES (?, ?, 1, datetime('now'))
                    ''', ('Demo Account', 'Demo'))
                    advertiser_id = cursor.lastrowid
                    
                    # Link them
                    cursor.execute('UPDATE marketer_accounts SET advertiser_id = ? WHERE id = ?', (advertiser_id, marketer_id))
                    conn.commit()
                    
                    cursor.execute('SELECT * FROM marketer_accounts WHERE id = ?', (marketer_id,))
                    demo = cursor.fetchone()
                
                conn.close()
                
                marketer = dict(demo) if demo else {
                    'id': 1,
                    'business_name': 'Demo Account',
                    'contact_name': 'Demo User',
                    'contact_email': 'demo@poolcue.nyc',
                    'advertiser_id': 1,
                    'credits_balance': 0
                }
            
            return f(marketer, *args, **kwargs)
        
        # Normal auth flow
        session_token = session.get('marketer_token')
        marketer = get_marketer_by_session(session_token)
        
        if not marketer:
            return redirect(url_for('market.login'))
        
        return f(marketer, *args, **kwargs)
    return decorated


# =============================================================================
# AUTH ROUTES
# =============================================================================

@market_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Marketer login page."""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # SECURITY: Beta login REMOVED - use real credentials only
        
        result = authenticate_marketer(email, password)
        
        if result['success']:
            session['marketer_token'] = result['session_token']
            session['marketer_id'] = result['marketer_id']
            session['advertiser_id'] = result['advertiser_id']
            return redirect(url_for('market.dashboard'))
        else:
            return render_template('market/login.html', error=result['error'])
    
    return render_template('market/login.html')


@market_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    """Marketer signup page."""
    if request.method == 'POST':
        result = create_marketer_account(
            business_name=request.form.get('business_name'),
            contact_name=request.form.get('contact_name'),
            contact_email=request.form.get('email'),
            password=request.form.get('password'),
            business_category=request.form.get('category'),
            website=request.form.get('website'),
            contact_phone=request.form.get('phone')
        )
        
        if result['success']:
            # Auto-login after signup
            auth = authenticate_marketer(request.form.get('email'), request.form.get('password'))
            if auth['success']:
                session['marketer_token'] = auth['session_token']
                session['marketer_id'] = auth['marketer_id']
                session['advertiser_id'] = auth['advertiser_id']
            return redirect(url_for('market.dashboard'))
        else:
            return render_template('market/signup.html', error=result['error'])
    
    return render_template('market/signup.html')


@market_bp.route('/logout')
def logout():
    """Log out marketer."""
    token = session.get('marketer_token')
    if token:
        logout_marketer(token)
    session.pop('marketer_token', None)
    session.pop('marketer_id', None)
    session.pop('advertiser_id', None)
    return redirect(url_for('market.login'))


# =============================================================================
# DASHBOARD
# =============================================================================

@market_bp.route('/')
@market_bp.route('/dashboard')
@marketer_required
def dashboard(marketer):
    """Main marketer dashboard with performance overview."""
    days = request.args.get('days', 30, type=int)
    stats = get_marketer_dashboard_stats(marketer['advertiser_id'], days=days)
    campaigns = get_marketer_campaigns(marketer['advertiser_id'])
    
    return render_template('market/dashboard.html',
                           marketer=marketer,
                           stats=stats,
                           campaigns=campaigns,
                           days=days)


# =============================================================================
# CAMPAIGNS
# =============================================================================

@market_bp.route('/campaigns')
@marketer_required
def campaigns_list(marketer):
    """List all campaigns for this marketer."""
    campaigns = get_marketer_campaigns(marketer['advertiser_id'])
    return render_template('market/campaigns.html',
                           marketer=marketer,
                           campaigns=campaigns)


@market_bp.route('/campaign/<int:campaign_id>')
@marketer_required
def campaign_detail(marketer, campaign_id):
    """Detailed view of a single campaign."""
    stats = get_campaign_detail_stats(campaign_id)
    
    if not stats:
        flash('Campaign not found')
        return redirect(url_for('market.campaigns_list'))
    
    # Verify ownership
    if stats['campaign']['advertiser_id'] != marketer['advertiser_id']:
        flash('Access denied')
        return redirect(url_for('market.campaigns_list'))
    
    return render_template('market/campaign_detail.html',
                           marketer=marketer,
                           stats=stats)


@market_bp.route('/campaign/new', methods=['GET', 'POST'])
@marketer_required
def campaign_create(marketer):
    """Create a new campaign."""
    if request.method == 'POST':
        campaign_id = create_self_serve_campaign(
            advertiser_id=marketer['advertiser_id'],
            name=request.form.get('name'),
            placements=request.form.getlist('placements'),
            start_date=request.form.get('start_date'),
            end_date=request.form.get('end_date'),
            budget=request.form.get('budget', type=float)
        )
        
        return redirect(url_for('market.campaign_edit', campaign_id=campaign_id))
    
    # Get available bars and placements
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, neighborhood FROM bars WHERE is_active = 1 ORDER BY name')
    bars = cursor.fetchall()
    conn.close()
    
    placements = get_all_placements()
    
    return render_template('market/campaign_create.html',
                           marketer=marketer,
                           bars=bars,
                           placements=placements)


@market_bp.route('/campaign/<int:campaign_id>/edit', methods=['GET', 'POST'])
@marketer_required
def campaign_edit(marketer, campaign_id):
    """Edit campaign details and upload creatives."""
    # Get campaign
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM campaigns WHERE id = ?', (campaign_id,))
    campaign = cursor.fetchone()
    
    if not campaign or campaign['advertiser_id'] != marketer['advertiser_id']:
        flash('Campaign not found')
        return redirect(url_for('market.campaigns_list'))
    
    # Get creatives
    cursor.execute('SELECT * FROM ad_creatives WHERE campaign_id = ?', (campaign_id,))
    creatives = cursor.fetchall()
    
    # Get bars
    cursor.execute('SELECT id, name FROM bars WHERE is_active = 1')
    bars = cursor.fetchall()
    
    conn.close()
    
    placements = get_all_placements()
    
    return render_template('market/campaign_edit.html',
                           marketer=marketer,
                           campaign=campaign,
                           creatives=creatives,
                           bars=bars,
                           placements=placements)


@market_bp.route('/campaign/<int:campaign_id>/submit', methods=['POST'])
@marketer_required
def campaign_submit(marketer, campaign_id):
    """Submit campaign for admin approval."""
    result = submit_campaign_for_review(campaign_id)
    
    if result['success']:
        flash('Campaign submitted for review! We\'ll notify you once approved.')
    else:
        flash(f'Error: {result["error"]}')
    
    return redirect(url_for('market.campaign_detail', campaign_id=campaign_id))


# =============================================================================
# CREATIVE UPLOAD
# =============================================================================

# SECURITY: File upload configuration
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB max

def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_image_file(file_stream):
    """Validate file is actually an image by checking magic bytes."""
    header = file_stream.read(12)
    file_stream.seek(0)
    if header[:8] == b'\x89PNG\r\n\x1a\n':
        return True
    if header[:3] == b'\xff\xd8\xff':
        return True
    if header[:6] in (b'GIF87a', b'GIF89a'):
        return True
    if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        return True
    return False


@market_bp.route('/campaign/<int:campaign_id>/upload', methods=['POST'])
@marketer_required
def upload_creative(marketer, campaign_id):
    """Upload a creative image for a campaign."""
    if 'creative' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'})
    
    file = request.files['creative']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})
    
    # SECURITY: Validate file extension
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'error': f'Invalid file type. Allowed: {", ".join(ALLOWED_EXTENSIONS)}'})
    
    # SECURITY: Check file size
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    if file_size > MAX_FILE_SIZE:
        return jsonify({'success': False, 'error': f'File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB'})
    
    # SECURITY: Validate magic bytes
    if not validate_image_file(file.stream):
        return jsonify({'success': False, 'error': 'Invalid image file. File content does not match extension.'})
    
    # Save file
    from werkzeug.utils import secure_filename
    filename = secure_filename(file.filename)
    
    # Add timestamp to avoid collisions
    import time
    filename = f"{int(time.time())}_{filename}"
    
    upload_dir = os.path.join(os.path.dirname(__file__), 'static', 'ads')
    os.makedirs(upload_dir, exist_ok=True)
    
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)
    
    # Create creative record
    creative_id = add_creative(
        campaign_id=campaign_id,
        advertiser_id=marketer['advertiser_id'],
        file_name=filename,
        label=request.form.get('label'),
        click_url=request.form.get('click_url')
    )
    
    # Set placements if specified
    placements = request.form.getlist('placements')
    if placements:
        set_placements(campaign_id, creative_id, placements)
    
    return jsonify({'success': True, 'creative_id': creative_id, 'filename': filename})


# =============================================================================
# PRICING & BILLING
# =============================================================================

@market_bp.route('/pricing')
def pricing():
    """Public pricing page."""
    placement_pricing = get_placement_pricing()
    package_pricing = get_package_pricing()
    
    return render_template('market/pricing.html',
                           placements=placement_pricing,
                           packages=package_pricing)


@market_bp.route('/billing')
@marketer_required
def billing(marketer):
    """Billing history and add credits."""
    transactions = get_marketer_billing_history(marketer['id'])
    
    return render_template('market/billing.html',
                           marketer=marketer,
                           transactions=transactions)


@market_bp.route('/billing/add-credits', methods=['POST'])
@marketer_required
def add_credits_route(marketer):
    """
    Add credits to account.
    
    TODO: Integrate with Stripe Checkout.
    For now, this is a stub that just adds credits directly.
    """
    amount = request.form.get('amount', type=float)
    
    if not amount or amount <= 0:
        flash('Invalid amount')
        return redirect(url_for('market.billing'))
    
    # TODO: Create Stripe Checkout session here
    # stripe.checkout.Session.create(...)
    # For now, just add credits directly (REMOVE IN PRODUCTION)
    
    add_credits(marketer['id'], amount, 'Credit purchase (demo)')
    flash(f'Added ${amount:.2f} in credits')
    
    return redirect(url_for('market.billing'))


# =============================================================================
# PREVIEW
# =============================================================================

@market_bp.route('/preview/<placement>')
@marketer_required
def preview_placement(marketer, placement):
    """Preview what an ad looks like in a specific placement."""
    placements = get_all_placements()
    
    if placement not in placements:
        flash('Invalid placement')
        return redirect(url_for('market.dashboard'))
    
    placement_info = placements[placement]
    
    # Get marketer's creatives
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM ad_creatives 
        WHERE advertiser_id = ? AND is_active = 1
        ORDER BY created_at DESC
    ''', (marketer['advertiser_id'],))
    creatives = cursor.fetchall()
    conn.close()
    
    return render_template('market/preview.html',
                           marketer=marketer,
                           placement=placement,
                           placement_info=placement_info,
                           creatives=creatives)


# =============================================================================
# API ENDPOINTS
# =============================================================================

@market_bp.route('/api/stats')
@marketer_required
def api_stats(marketer):
    """API endpoint for dashboard stats (for AJAX refresh)."""
    days = request.args.get('days', 30, type=int)
    stats = get_marketer_dashboard_stats(marketer['advertiser_id'], days=days)
    return jsonify(stats)


@market_bp.route('/api/campaign/<int:campaign_id>/cost')
@marketer_required
def api_campaign_cost(marketer, campaign_id):
    """Get current cost breakdown for a campaign."""
    cost = calculate_campaign_cost(campaign_id)
    return jsonify(cost)
