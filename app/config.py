"""
Pool Cue - Configuration Manager

Loads configuration from environment variables with sensible defaults.
Usage:
    from app.config import config
    
    if config.ENABLE_ADS:
        show_ads()
    
    print(f"Running in {config.ENV} mode")
"""
import os
from dataclasses import dataclass
from typing import Optional


def get_bool(key: str, default: bool = False) -> bool:
    """Get boolean from environment variable."""
    value = os.environ.get(key, str(default)).lower()
    return value in ('true', '1', 'yes', 'on')


def get_int(key: str, default: int = 0) -> int:
    """Get integer from environment variable."""
    try:
        return int(os.environ.get(key, default))
    except (ValueError, TypeError):
        return default


@dataclass
class Config:
    """Application configuration loaded from environment."""
    
    # ===================
    # CORE
    # ===================
    ENV: str = os.environ.get('FLASK_ENV', 'development')
    DEBUG: bool = get_bool('FLASK_DEBUG', True)
    SECRET_KEY: str = os.environ.get('SECRET_KEY', 'dev-insecure-key')
    HOST: str = os.environ.get('HOST', '0.0.0.0')
    PORT: int = get_int('PORT', 5002)
    
    # ===================
    # DATABASE
    # ===================
    DATABASE_URL: str = os.environ.get('DATABASE_URL', 'sqlite:///app/db/pool_queue.db')
    
    # ===================
    # FEATURE FLAGS
    # ===================
    ENABLE_NEW_QUEUE_UI: bool = get_bool('ENABLE_NEW_QUEUE_UI', True)
    ENABLE_ADS: bool = get_bool('ENABLE_ADS', True)
    ENABLE_RANKINGS: bool = get_bool('ENABLE_RANKINGS', True)
    ENABLE_SMS_NOTIFICATIONS: bool = get_bool('ENABLE_SMS_NOTIFICATIONS', False)
    ENABLE_STRIPE_PAYMENTS: bool = get_bool('ENABLE_STRIPE_PAYMENTS', False)
    ENABLE_QUEUE_CONFIRMATION: bool = get_bool('ENABLE_QUEUE_CONFIRMATION', False)
    
    # ===================
    # ACCESS CONTROL
    # ===================
    ALLOW_BETA_LOGIN: bool = get_bool('ALLOW_BETA_LOGIN', True)
    
    # ===================
    # EXTERNAL SERVICES
    # ===================
    TWILIO_ACCOUNT_SID: Optional[str] = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN: Optional[str] = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER: Optional[str] = os.environ.get('TWILIO_PHONE_NUMBER')
    
    STRIPE_PUBLIC_KEY: Optional[str] = os.environ.get('STRIPE_PUBLIC_KEY')
    STRIPE_SECRET_KEY: Optional[str] = os.environ.get('STRIPE_SECRET_KEY')
    STRIPE_WEBHOOK_SECRET: Optional[str] = os.environ.get('STRIPE_WEBHOOK_SECRET')
    
    # ===================
    # LOGGING
    # ===================
    LOG_LEVEL: str = os.environ.get('LOG_LEVEL', 'DEBUG')
    LOG_TO_FILE: bool = get_bool('LOG_TO_FILE', False)
    
    # ===================
    # COMPUTED PROPERTIES
    # ===================
    @property
    def is_production(self) -> bool:
        return self.ENV == 'production'
    
    @property
    def is_development(self) -> bool:
        return self.ENV == 'development'
    
    @property
    def is_staging(self) -> bool:
        return self.ENV == 'staging'
    
    @property
    def twilio_configured(self) -> bool:
        return all([self.TWILIO_ACCOUNT_SID, self.TWILIO_AUTH_TOKEN, self.TWILIO_PHONE_NUMBER])
    
    @property
    def stripe_configured(self) -> bool:
        return all([self.STRIPE_PUBLIC_KEY, self.STRIPE_SECRET_KEY])
    
    def __repr__(self):
        return f"<Config env={self.ENV} debug={self.DEBUG}>"


# Global config instance - import this in your app
config = Config()


# Validation on import
def validate_config():
    """Warn about missing critical config in production."""
    if config.is_production:
        warnings = []
        
        if config.SECRET_KEY == 'dev-insecure-key':
            warnings.append("SECRET_KEY is using default value!")
        
        if config.ALLOW_BETA_LOGIN:
            warnings.append("ALLOW_BETA_LOGIN is enabled in production!")
        
        if config.DEBUG:
            warnings.append("DEBUG mode is enabled in production!")
        
        if warnings:
            print("\n" + "="*50)
            print("⚠️  PRODUCTION CONFIG WARNINGS:")
            for w in warnings:
                print(f"   - {w}")
            print("="*50 + "\n")


# Run validation when module loads
validate_config()
