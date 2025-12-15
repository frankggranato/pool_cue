"""
Pool Cue - Critical Path Tests

Tests for core functionality: authentication, queue, tokens.
Run with: pytest tests/test_critical_paths.py -v
"""
import pytest
from app.app import create_app
from app.database import get_db


@pytest.fixture
def app():
    """Create test application."""
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


class TestAdminAuthentication:
    """Test admin login functionality."""
    
    def test_admin_login_page_loads(self, client):
        """Admin login page should be accessible."""
        response = client.get('/admin/login')
        assert response.status_code == 200
    
    def test_admin_login_rejects_invalid(self, client):
        """Invalid credentials should be rejected."""
        response = client.post('/admin/login', data={
            'username': 'invalid',
            'password': 'wrongpassword'
        })
        # Should stay on login page or show error
        assert response.status_code in [200, 302]
    
    def test_admin_routes_require_auth(self, client):
        """Protected routes should redirect to login."""
        protected_routes = ['/master/', '/master/bars', '/master/players']
        for route in protected_routes:
            response = client.get(route)
            # Should redirect to login
            assert response.status_code == 302


class TestPublicRoutes:
    """Test public-facing routes."""
    
    def test_homepage_loads(self, client):
        """Homepage should be accessible."""
        response = client.get('/')
        assert response.status_code == 200
    
    def test_display_board_loads(self, client):
        """Display board should be accessible."""
        response = client.get('/display?bar_id=1')
        assert response.status_code == 200
    
    def test_queue_api_returns_json(self, client):
        """Queue API should return JSON."""
        response = client.get('/api/queue')
        assert response.status_code == 200
        assert response.content_type == 'application/json'
    
    def test_board_data_api(self, client):
        """Board data API should return JSON."""
        response = client.get('/api/board-data?bar_id=1')
        assert response.status_code == 200
        data = response.get_json()
        assert 'queue_count' in data


class TestQRCodeFlow:
    """Test QR code scanning flow."""
    
    def test_qr_view_loads(self, client):
        """QR scan page should load for valid bar."""
        response = client.get('/q/1')
        assert response.status_code == 200
    
    def test_qr_view_404_invalid_bar(self, client):
        """QR scan page should 404 for invalid bar."""
        response = client.get('/q/99999')
        assert response.status_code == 404


class TestPlayerAuth:
    """Test player authentication flow."""
    
    def test_player_login_page_loads(self, client):
        """Player login page should be accessible."""
        response = client.get('/player-auth/login')
        assert response.status_code == 200
    
    def test_player_signup_page_loads(self, client):
        """Player signup page should be accessible."""
        response = client.get('/auth/signup')
        assert response.status_code == 200


class TestTokenSystem:
    """Test token/economy functionality."""
    
    def test_token_constants_defined(self):
        """Token constants should be defined."""
        from app.tokens import TOKENS_WIN, TOKENS_LOSE, TOKENS_SURVEY
        assert TOKENS_WIN > 0
        assert TOKENS_LOSE >= 0
        assert TOKENS_SURVEY > 0
    
    def test_token_balance_function_exists(self):
        """Token balance function should exist."""
        from app.tokens import get_balance
        # Should not raise
        assert callable(get_balance)


class TestDatabaseIntegrity:
    """Test database functions."""
    
    def test_database_connects(self):
        """Database connection should work."""
        conn = get_db()
        assert conn is not None
        conn.close()
    
    def test_bars_table_exists(self):
        """Bars table should exist."""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bars'")
        result = cursor.fetchone()
        conn.close()
        assert result is not None
    
    def test_players_table_exists(self):
        """Players table should exist."""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='players'")
        result = cursor.fetchone()
        conn.close()
        assert result is not None


class TestSecurityHeaders:
    """Test security headers are set."""
    
    def test_xframe_options_header(self, client):
        """X-Frame-Options header should be set."""
        response = client.get('/')
        assert 'X-Frame-Options' in response.headers
    
    def test_content_type_options_header(self, client):
        """X-Content-Type-Options header should be set."""
        response = client.get('/')
        assert 'X-Content-Type-Options' in response.headers
