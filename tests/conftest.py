import os
import shutil
import tempfile
import pytest
from app import create_app
from app.models import User, LoginOTP
from app.database import get_db
from app.config import Config

@pytest.fixture
def app():
    # Create a temporary directory for uploaded test files and storage
    temp_dir = tempfile.mkdtemp()
    
    class RuntimeTestConfig(Config):
        TESTING = True
        MONGODB_URI = "mongomock://localhost/test_medivault_db"
        MONGODB_DATABASE = "test_medivault_db"
        WTF_CSRF_ENABLED = False
        SECRET_KEY = "test-secret-key-123"
        STORAGE_FOLDER = os.path.join(temp_dir, 'storage')
        UPLOAD_FOLDER = STORAGE_FOLDER

    app = create_app(RuntimeTestConfig)
    app.login_manager.session_protection = None

    with app.app_context():
        db = get_db()
        yield app
        # Clean collections
        db.users.delete_many({})
        db.medical_records.delete_many({})
        db.prescriptions.delete_many({})
        db.appointments.delete_many({})
        db.activity_logs.delete_many({})
        db.chat_sessions.delete_many({})
        db.chat_messages.delete_many({})
        db.notifications.delete_many({})
        db.voice_call_logs.delete_many({})
        db.reminder_logs.delete_many({})
        db.pending_registrations.delete_many({})
        db.otp_verifications.delete_many({})

    # Cleanup temporary directory after test run
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def runner(app):
    return app.test_cli_runner()

@pytest.fixture
def user_a(app):
    """Create test user A."""
    with app.app_context():
        user = User.create_user(
            full_name="Alice Johnson",
            email="alice@example.com",
            password="SecurePass123",
            phone_number="555-0100",
            blood_group="O+",
            theme_preference="light"
        )
        return user.id

@pytest.fixture
def user_b(app):
    """Create test user B."""
    with app.app_context():
        user = User.create_user(
            full_name="Bob Smith",
            email="bob@example.com",
            password="AnotherSecure456",
            phone_number="555-0200",
            blood_group="A-",
            theme_preference="dark"
        )
        return user.id

@pytest.fixture
def login_as(app):
    """Helper to authenticate a test client as a specific user."""
    def _login(c, user_id):
        with app.app_context():
            user = User.get_by_id(user_id)
            token = LoginOTP.create(user.id, 'email', user.email, "123456")
        c.post(f'/auth/verify-login?token={token}', data={'otp_code': '123456'}, follow_redirects=True)
        return c
    return _login

@pytest.fixture
def auth_client_a(app, user_a, login_as):
    """Client authenticated as Alice."""
    c = app.test_client()
    login_as(c, user_a)
    return c

@pytest.fixture
def auth_client_b(app, user_b, login_as):
    """Client authenticated as Bob."""
    c = app.test_client()
    login_as(c, user_b)
    return c
