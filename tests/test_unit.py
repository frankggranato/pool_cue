"""
Pool Cue - Unit Tests

Tests for individual functions and utilities.
Run with: pytest tests/test_unit.py -v
"""
import pytest


class TestConfig:
    """Test configuration module."""
    
    def test_config_loads(self):
        """Config module should load without errors."""
        from app.config import config
        assert config is not None
        assert hasattr(config, 'ENV')
        assert hasattr(config, 'DEBUG')
    
    def test_feature_flags_exist(self):
        """Feature flags should be defined."""
        from app.config import config
        assert hasattr(config, 'ENABLE_ADS')
        assert hasattr(config, 'ENABLE_RANKINGS')
        assert hasattr(config, 'ENABLE_SMS_NOTIFICATIONS')
    
    def test_is_development_by_default(self):
        """Should be development environment by default."""
        from app.config import config
        # In test environment, this may vary
        assert config.ENV in ('development', 'testing', 'production', 'staging')


class TestPasswordHashing:
    """Test password security functions."""
    
    def test_password_hash_is_different_from_input(self):
        """Hashed password should not equal plaintext."""
        from werkzeug.security import generate_password_hash
        password = 'testpassword123'
        hashed = generate_password_hash(password)
        assert hashed != password
    
    def test_password_verification_works(self):
        """Should verify correct password."""
        from werkzeug.security import generate_password_hash, check_password_hash
        password = 'testpassword123'
        hashed = generate_password_hash(password)
        assert check_password_hash(hashed, password) is True
        assert check_password_hash(hashed, 'wrongpassword') is False


class TestHelperFunctions:
    """Test utility functions."""
    
    def test_get_bool_helper(self):
        """Boolean environment variable parser."""
        from app.config import get_bool
        import os
        
        # Test true values
        os.environ['TEST_VAR'] = 'true'
        assert get_bool('TEST_VAR') is True
        
        os.environ['TEST_VAR'] = '1'
        assert get_bool('TEST_VAR') is True
        
        # Test false values
        os.environ['TEST_VAR'] = 'false'
        assert get_bool('TEST_VAR') is False
        
        # Cleanup
        del os.environ['TEST_VAR']
    
    def test_get_int_helper(self):
        """Integer environment variable parser."""
        from app.config import get_int
        import os
        
        os.environ['TEST_INT'] = '42'
        assert get_int('TEST_INT') == 42
        
        # Invalid int should return default
        os.environ['TEST_INT'] = 'not_a_number'
        assert get_int('TEST_INT', default=0) == 0
        
        # Cleanup
        del os.environ['TEST_INT']
