"""
API Routes - Surveys, Tokens, Brands
"""
from flask import Blueprint, request, jsonify, session
from datetime import datetime, timedelta
from functools import wraps
import logging

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')

# Admin authentication decorator
def admin_required(f):
    """Decorator to require admin authentication for API endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function

# SECURITY: Helper to validate user access
def validate_user_access(user_id):
    """Validate that the current user can access this user_id's data."""
    if session.get('admin_logged_in'):
        return True
    session_user_id = session.get('player_id')
    if session_user_id and session_user_id == user_id:
        return True
    if not session_user_id:
        return True  # Backward compatibility
    return False

# ============ TOKENS ============

@api_bp.route('/tokens/balance')
def tokens_balance():
    """Get user's token balance."""
    user_id = request.args.get('user_id', type=int)
    if not user_id:
        user_id = session.get('player_id')
    if not user_id:
        return jsonify({'error': 'user_id required or must be logged in'}), 400
    if not validate_user_access(user_id):
        return jsonify({'error': 'Access denied'}), 403
    try:
        from .tokens import get_balance
        balance = get_balance(user_id)
        return jsonify({'balance': balance, 'user_id': user_id})
    except Exception as e:
        logger.exception('API error')
        return jsonify({'error': 'Internal server error'}), 500

@api_bp.route('/tokens/history')
def tokens_history():
    """Get token transaction history."""
    user_id = request.args.get('user_id', type=int)
    limit = request.args.get('limit', 20, type=int)
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    try:
        from .tokens import get_history
        history = get_history(user_id, limit)
        return jsonify({'history': history, 'user_id': user_id})
    except Exception as e:
        logger.exception('API error')
        return jsonify({'error': 'Internal server error'}), 500

@api_bp.route('/tokens/transactions')
def tokens_transactions():
    """Get recent token transactions."""
    user_id = request.args.get('user_id', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    try:
        from .tokens import get_history
        transactions = get_history(user_id, limit)
        return jsonify({'transactions': transactions})
    except Exception as e:
        logger.exception('API error')
        return jsonify({'error': 'Internal server error'}), 500

@api_bp.route('/tokens/award-survey', methods=['POST'])
def tokens_award_survey():
    """Award tokens for completing a survey."""
    data = request.get_json() or {}
    user_id = data.get('user_id')
    survey_type = data.get('survey_type', 'general')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    try:
        from .tokens import award_survey
        result = award_survey(user_id, survey_type)
        return jsonify(result)
    except Exception as e:
        logger.exception('API error')
        return jsonify({'error': 'Internal server error'}), 500

# ============ NICKNAME GENERATOR ============

@api_bp.route('/generate-nickname')
def generate_nickname():
    """Generate a unique funny pool-pun nickname."""
    import random
    from .database import get_db
    
    # Funny pool puns and bar-style nicknames
    pun_names = [
        # Classic puns
        'CueLater', 'BallsBDeep', 'ScratchThat', 'RackCity', 'ChalkItUp',
        'PocketRocket', 'BankOnIt', 'BreakBad', 'FeltUp', 'RailTales',
        'CueTip', 'NiceCues', 'CueAnon', 'TheCueWhisperer', 'CuePid',
        'PoolFool', 'PoolOfLies', 'DeadPool', 'CarPool', 'CessPool',
        'BehindThe8Ball', 'CornerPocket', 'SideHustle', 'RackEmUp',
        'ChalkWalk', 'FeltTips', 'GreenMachine', 'TableManners',
        
        # Bar vibes
        'LastCall', 'HappyHour', 'BarFly', 'TwoForOne', 'OnTheRocks',
        'NeatShot', 'BottomsUp', 'LastRound', 'TabsOpen', 'CashOnly',
        'JukeboxHero', 'DartBoard', 'BarBack', 'TipJar', 'HouseRules',
        
        # Hustler style
        'FastEddie', 'MinnesotaFats', 'MosconiKid', 'TheSharpe',
        'SlickWillie', 'StraightShooter', 'MoneyMaker', 'BetOnIt',
        'AllInAl', 'DoubleDown', 'SideBets', 'RoadPlayer', 'ActionJack',
        
        # Funny descriptive
        'MissedIt', 'AlmostPro', 'LuckyScrath', 'OopsMyBad', 'CloseEnough',
        'NailedIt', 'SendIt', 'WatchThis', 'HoldMyBeer', 'NoLookShot',
        'YoloShot', 'TrickShot', 'ShowOff', 'Beginner', 'ProBono',
        'TableHog', 'CoinWaiter', 'NextGame', 'Runnin', 'OnFire',
        
        # Wordplay
        'Sir Scratch', 'Captain Miscue', 'Baron Von Bank', 'Duke of Draw',
        'Earl of English', 'Count Combo', 'Lord Lag', 'Sir Spin',
        'MasseMaster', 'JumpMan', 'SafetyFirst', 'DefensiveD',
        
        # Pop culture pool
        'Pool Bunyan', 'Pool McCartney', 'Billie Eilish Ball',
        'Post Mahogany', 'Dua Cue', 'Harry Sticks', 'Lizzo Ball',
        'The Weeknd Warrior', 'Childish Gamballer', 'Kendrick Lamarck',
        
        # NYC themed
        'BrooklynBreak', 'QueensCue', 'BronxBanker', 'ManhattanMasse',
        'StatenSlam', 'SubwayShooter', 'TimesSquared', 'CentralPark',
        'EastSideShot', 'WestSideWin', 'UpTown', 'DownTown', 'CrossTown',
        
        # Self-deprecating
        'ScratchKing', 'MissQueen', 'ChokeMaster', 'Whiffer',
        'TableRenter', 'CoinFeeder', 'PracticePro', 'YouTube U',
        'AllTalk', 'BigTalk', 'NextTime', 'WarmingUp', 'StillLearning',
        
        # Confident
        'EasyMoney', 'CleanSweep', 'RunOut', 'Undefeated', 'TopShelf',
        'FirstTry', 'NoMercy', 'Ruthless', 'Flawless', 'ByeByeBalls'
    ]
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Shuffle and try each pun name
    random.shuffle(pun_names)
    for name in pun_names:
        cursor.execute('SELECT id FROM players WHERE LOWER(nickname) = LOWER(?)', (name,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'nickname': name})
    
    # All puns taken - add numbers to random puns
    for attempt in range(100):
        base = random.choice(pun_names)
        name = base + str(random.randint(1, 99))
        cursor.execute('SELECT id FROM players WHERE LOWER(nickname) = LOWER(?)', (name,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'nickname': name})
    
    conn.close()
    return jsonify({'error': 'Could not generate unique name'}), 500

# ============ SURVEYS ============

@api_bp.route('/surveys/available')
def surveys_available():
    """Get available survey questions for user."""
    user_id = request.args.get('user_id', 1, type=int)
    try:
        from .services import survey_service
        questions = survey_service.get_available_questions(user_id, limit=3)
        return jsonify({'questions': questions})
    except Exception as e:
        logger.exception('API error')
        return jsonify({'error': 'Internal server error'}), 500

@api_bp.route('/surveys/answer', methods=['POST'])
def surveys_answer():
    """Submit survey answer."""
    data = request.get_json() or {}
    user_id = data.get('user_id', 1)
    question_id = data.get('question_id')
    answer = data.get('answer')
    bar_id = data.get('bar_id')
    
    if not question_id or answer is None:
        return jsonify({'error': 'question_id and answer required'}), 400
    
    try:
        from .services import survey_service
        result = survey_service.submit_answer(user_id, question_id, answer, bar_id)
        return jsonify(result)
    except Exception as e:
        logger.exception('API error')
        return jsonify({'error': 'Internal server error'}), 500

# ============ BRANDS ============

@api_bp.route('/admin/brands')
@admin_required
def brands_list():
    """Get all brands with metrics."""
    start = request.args.get('start', (datetime.now().replace(day=1)).strftime('%Y-%m-%d'))
    end = request.args.get('end', datetime.now().strftime('%Y-%m-%d'))
    
    try:
        from .services import brand_service
        brands = brand_service.get_all_brands_summary(start, end)
        return jsonify({'brands': brands})
    except Exception as e:
        logger.exception('API error')
        return jsonify({'error': 'Internal server error'}), 500

@api_bp.route('/admin/brands/<int:brand_id>/summary')
@admin_required
def brand_summary(brand_id):
    """Get brand metrics summary."""
    start = request.args.get('start', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end = request.args.get('end', datetime.now().strftime('%Y-%m-%d'))
    
    try:
        from .services import brand_service
        metrics = brand_service.get_brand_metrics(brand_id, start, end)
        return jsonify(metrics)
    except Exception as e:
        logger.exception('API error')
        return jsonify({'error': 'Internal server error'}), 500

@api_bp.route('/admin/brands/<int:brand_id>/generate_report', methods=['POST'])
@admin_required
def generate_brand_report(brand_id):
    """Generate brand report."""
    data = request.get_json() or {}
    start = data.get('period_start', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end = data.get('period_end', datetime.now().strftime('%Y-%m-%d'))
    
    try:
        from .services import reports_service
        result = reports_service.generate_brand_report(brand_id, start, end)
        if result:
            return jsonify(result)
        return jsonify({'error': 'Brand not found'}), 404
    except Exception as e:
        logger.exception('API error')
        return jsonify({'error': 'Internal server error'}), 500

@api_bp.route('/admin/brands/reports')
@admin_required
def brand_reports_list():
    """Get list of generated reports."""
    brand_id = request.args.get('brand_id', type=int)
    try:
        from .services import reports_service
        reports = reports_service.get_all_reports(brand_id)
        return jsonify({'reports': reports})
    except Exception as e:
        logger.exception('API error')
        return jsonify({'error': 'Internal server error'}), 500

# ============ COHORTS ============

@api_bp.route('/admin/cohorts')
@admin_required
def cohorts_breakdown():
    """Get cohort breakdown."""
    try:
        from .services import cohort_service
        breakdown = cohort_service.get_cohort_breakdown()
        return jsonify({'cohorts': breakdown})
    except Exception as e:
        logger.exception('API error')
        return jsonify({'error': 'Internal server error'}), 500

@api_bp.route('/admin/cohorts/recompute', methods=['POST'])
@admin_required
def recompute_cohorts():
    """Recompute all player cohorts."""
    try:
        from .services import cohort_service
        results = cohort_service.batch_compute_cohorts()
        return jsonify({'success': True, 'users_processed': len(results)})
    except Exception as e:
        logger.exception('API error')
        return jsonify({'error': 'Internal server error'}), 500

# ============ STATS ============

@api_bp.route('/admin/heatmap')
@admin_required
def activity_heatmap():
    """Get activity heatmap data."""
    bar_id = request.args.get('bar_id', type=int)
    weeks = request.args.get('weeks', 4, type=int)
    
    try:
        from .services import stats_service
        heatmap = stats_service.get_activity_heatmap(bar_id, weeks)
        return jsonify({'heatmap': heatmap})
    except Exception as e:
        logger.exception('API error')
        return jsonify({'error': 'Internal server error'}), 500

@api_bp.route('/admin/league_metrics')
@admin_required
def league_metrics():
    """Get league replacement metrics."""
    bar_id = request.args.get('bar_id', type=int)
    days = request.args.get('days', 30, type=int)
    
    try:
        from .services import stats_service
        metrics = stats_service.get_league_metrics(bar_id, days)
        return jsonify(metrics)
    except Exception as e:
        logger.exception('API error')
        return jsonify({'error': 'Internal server error'}), 500

# ============ BRAND TRACKING ============

@api_bp.route('/brands/<int:brand_id>/impression', methods=['POST'])
def record_impression(brand_id):
    """Record a brand impression."""
    data = request.get_json() or {}
    bar_id = data.get('bar_id')
    placement = data.get('placement', 'unknown')
    impression_type = data.get('type', 'screen_view')
    viewers = data.get('viewers', 1)
    
    try:
        from .services import brand_service
        brand_service.record_impression(brand_id, bar_id, placement, impression_type, viewers)
        return jsonify({'success': True})
    except Exception as e:
        logger.exception('API error')
        return jsonify({'error': 'Internal server error'}), 500

@api_bp.route('/brands/<int:brand_id>/click', methods=['POST'])
def record_click(brand_id):
    """Record a brand click."""
    data = request.get_json() or {}
    bar_id = data.get('bar_id')
    user_id = data.get('user_id')
    placement = data.get('placement', 'unknown')
    
    try:
        from .services import brand_service
        brand_service.record_click(brand_id, bar_id, user_id, placement)
        return jsonify({'success': True})
    except Exception as e:
        logger.exception('API error')
        return jsonify({'error': 'Internal server error'}), 500
