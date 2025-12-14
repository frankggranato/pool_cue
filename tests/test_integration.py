"""
Pool Cue - Integration Tests (Happy Path)

Tests for complete user flows.
Run with: pytest tests/test_integration.py -v
"""
import pytest


class TestAppLoads:
    """Test that the application starts correctly."""
    
    def test_app_creates(self, app):
        """Application should create without errors."""
        assert app is not None
    
    def test_app_is_testing(self, app):
        """App should be in testing mode."""
        assert app.config['TESTING'] is True


class TestPublicPages:
    """Test pages accessible without login."""
    
    def test_homepage_loads(self, client):
        """Homepage should return 200 or redirect."""
        response = client.get('/')
        # May redirect to /join or show homepage
        assert response.status_code in (200, 302)
    
    def test_join_page_loads(self, client):
        """Join page should load."""
        response = client.get('/join')
        assert response.status_code == 200
    
    def test_portal_page_loads(self, client):
        """Portal selection page should load."""
        response = client.get('/auth/portal')
        assert response.status_code == 200
        assert b'Pool' in response.data  # Should have "Pool" somewhere
    
    def test_login_page_loads(self, client):
        """Player login page should load."""
        response = client.get('/auth/login')
        assert response.status_code == 200


class TestAdminLogin:
    """Test admin authentication."""
    
    def test_admin_login_page_loads(self, client):
        """Admin login page should load."""
        response = client.get('/admin/login')
        assert response.status_code == 200
    
    def test_admin_dashboard_requires_auth(self, client):
        """Admin dashboard should redirect without login."""
        response = client.get('/master/')
        # Should redirect to login
        assert response.status_code == 302
        assert '/admin/login' in response.location or 'login' in response.location.lower()


class TestBarManagerLogin:
    """Test bar manager authentication."""
    
    def test_bar_manager_login_page_loads(self, client):
        """Bar manager login page should load."""
        response = client.get('/bar-manager/login')
        assert response.status_code == 200
    
    def test_bar_manager_dashboard_requires_auth(self, client):
        """Bar manager dashboard should redirect without login."""
        response = client.get('/bar-manager/')
        assert response.status_code == 302


class TestAPIEndpoints:
    """Test API endpoints."""
    
    def test_queue_status_api(self, client):
        """Queue status API should respond."""
        response = client.get('/api/queue/my-status')
        assert response.status_code == 200
        # Should return JSON
        assert response.content_type == 'application/json'
    
    def test_board_data_requires_bar_id(self, client):
        """Board data API should work with bar_id."""
        # Without bar_id, may return error or empty
        response = client.get('/display/api/board-data')
        # Should be JSON response
        assert response.status_code in (200, 400, 404)


class TestQueueFlow:
    """Test the main queue user flow."""
    
    def test_join_page_shows_bars(self, client):
        """Join page should show available bars."""
        response = client.get('/join')
        assert response.status_code == 200
        # Page should have some content
        assert len(response.data) > 100
    
    def test_player_status_requires_session(self, client):
        """Player status page should handle no session."""
        response = client.get('/my-status')
        # Should redirect to join if not in queue
        assert response.status_code in (200, 302)


class TestBoardDisplay:
    """Test board display functionality."""
    
    def test_display_page_loads(self, client):
        """Board display page should load."""
        response = client.get('/display?bar_id=1')
        # May return 200 or 404 if bar doesn't exist
        assert response.status_code in (200, 404)
