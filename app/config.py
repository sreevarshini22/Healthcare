import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

class Config:
    """Application configuration settings for MediVault with MongoDB and AI/Telephony services."""
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY') or os.environ.get('SECRET_KEY') or 'medivault-super-secret-classical-key-2026'
    
    # MongoDB Database Configuration
    MONGODB_URI = os.environ.get('MONGODB_URI') or 'mongodb://localhost:27017/medivault_db'
    MONGODB_DATABASE = os.environ.get('MONGODB_DATABASE') or 'medivault_db'
    
    # File Uploads / Private Storage Settings
    STORAGE_FOLDER = os.environ.get('STORAGE_FOLDER') or (
        '/tmp/storage' if os.environ.get('VERCEL') else os.path.join(BASE_DIR, 'storage')
    )
    UPLOAD_FOLDER = STORAGE_FOLDER  # Alias for backward compatibility
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload size
    ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'webp'}
    
    # Session & Security Settings
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    REMEMBER_COOKIE_DURATION = timedelta(days=14)
    REMEMBER_COOKIE_HTTPONLY = True
    
    # AI Services Configuration (OpenAI, Google Gemini, Anthropic, or Local Clinical NLP)
    AI_PROVIDER = os.environ.get('AI_PROVIDER', 'auto')  # 'auto', 'openai', 'gemini', 'local'
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    AI_MODEL = os.environ.get('AI_MODEL', 'gpt-4o-mini')
    
    # Telephony & Voice Agent Settings (Twilio)
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')
    VOICE_CALLBACK_BASE_URL = os.environ.get('VOICE_CALLBACK_BASE_URL', 'http://127.0.0.1:5000')
    
    # Notification & Email Settings
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'notifications@medivault-health.org')
    
    # Scheduler Settings
    SCHEDULER_ENABLED = os.environ.get('SCHEDULER_ENABLED', 'false' if os.environ.get('VERCEL') else 'true').lower() == 'true'
    SCHEDULER_INTERVAL_MINUTES = int(os.environ.get('SCHEDULER_INTERVAL_MINUTES', 5))
    
    # Application Meta
    APP_NAME = "MediVault"
    APP_TAGLINE = "Personal Health Record Manager"
