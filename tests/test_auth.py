import pytest
from app.models import User, PendingRegistration, LoginOTP
from app.database import get_db

def test_minimal_homepage(client):
    """Test that homepage renders minimal branding and no promotional sections."""
    response = client.get('/')
    assert response.status_code == 200
    assert b"Medi" in response.data
    assert b"Vault" in response.data
    assert b"Login" in response.data
    assert b"Create Account" in response.data
    # Verify removed promotional sections are not present
    assert b"Confidential &amp; Secure Healthcare Record Keeping" not in response.data
    assert b"Patient Quick Portal" not in response.data
    assert b"Simple Three-Step Health Management" not in response.data
    assert b"Designed for Clarity, Security, and Reliability" not in response.data

def test_register_flow_success(client, app):
    """Test direct registration workflow: submit name, email, phone, password -> user created and logged in."""
    resp = client.post('/auth/register', data={
        'name': 'Dr. Welby',
        'email': 'welby@hospital.org',
        'phone_number': '+1 (617) 555-0188',
        'password': 'SecureWelbyPassword123!'
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert b"Welcome to MediVault" in resp.data

    # Check user in MongoDB
    with app.app_context():
        user = User.get_by_email('welby@hospital.org')
        assert user is not None
        assert user.email == 'welby@hospital.org'
        assert user.full_name == 'Dr. Welby'
        assert user.phone_number is not None
        assert user.check_password('SecureWelbyPassword123!') is True

def test_register_invalid_email_and_phone(client):
    """Test validation errors for malformed email and short phone numbers."""
    # Invalid email
    resp1 = client.post('/auth/register', data={
        'name': 'Test User',
        'email': 'invalid-email-string',
        'phone_number': '555-0100',
        'password': 'ValidPassword123'
    }, follow_redirects=True)
    assert b"valid email address" in resp1.data

    # Short phone
    resp2 = client.post('/auth/register', data={
        'name': 'Test User',
        'email': 'valid@example.com',
        'phone_number': '123',
        'password': 'ValidPassword123'
    }, follow_redirects=True)
    assert b"at least 7 digits" in resp2.data

def test_register_duplicate_email_and_phone(client, user_a):
    """Test that duplicate email or phone number is rejected with warning."""
    # Duplicate email
    resp1 = client.post('/auth/register', data={
        'name': 'Alice Dupe',
        'email': 'alice@example.com',
        'phone_number': '+1-555-9999',
        'password': 'ValidPassword123'
    }, follow_redirects=True)
    assert b"already exists" in resp1.data

    # Duplicate phone
    resp2 = client.post('/auth/register', data={
        'name': 'Alice Dupe Phone',
        'email': 'brandnew@example.com',
        'phone_number': '555-0100', # Alice's phone
        'password': 'ValidPassword123'
    }, follow_redirects=True)
    assert b"already exists" in resp2.data

def test_login_with_email_success(client, user_a, app):
    """Test direct login via registered Email and password."""
    resp = client.post('/auth/login', data={
        'identifier': 'alice@example.com',
        'password': 'SecurePass123'
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert b"Welcome back, Alice Johnson" in resp.data

def test_login_with_phone_success(client, user_a, app):
    """Test direct login via registered Phone Number and password."""
    resp = client.post('/auth/login', data={
        'identifier': '555-0100',
        'password': 'SecurePass123'
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert b"Welcome back, Alice Johnson" in resp.data

def test_login_nonexistent_account(client):
    """Test error message when trying to log in with an unregistered identifier."""
    resp = client.post('/auth/login', data={
        'identifier': 'nobody@hospital.org',
        'password': 'AnyPassword123'
    }, follow_redirects=True)

    assert b"No account found matching this email address or phone number" in resp.data

def test_login_wrong_password(client, user_a):
    """Test error message when submitting an incorrect password."""
    resp = client.post('/auth/login', data={
        'identifier': 'alice@example.com',
        'password': 'WrongPassword999'
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert b"Incorrect password" in resp.data

def test_logout(auth_client_a):
    """Test user logout."""
    response = auth_client_a.get('/auth/logout', follow_redirects=True)
    assert response.status_code == 200
    assert b"signed out securely" in response.data

def test_delete_account(auth_client_a, app, user_a):
    """Test account deletion with confirmation and database purge."""
    response = auth_client_a.post('/auth/delete-account', data={
        'confirmation_text': 'DELETE MY ACCOUNT',
        'confirm_delete_password': 'SecurePass123'
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b"permanently deleted" in response.data

    with app.app_context():
        user = User.get_by_id(user_a)
        assert user is None

def test_theme_toggle_ajax(auth_client_a, app, user_a):
    """Test switching user theme preference between light and dark via AJAX."""
    resp = auth_client_a.post('/auth/toggle-theme')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'success'
    assert data['theme'] == 'dark'

    with app.app_context():
        user = User.get_by_id(user_a)
        assert user.theme_preference == 'dark'

def test_profile_update(auth_client_a, app, user_a):
    """Test updating user profile details."""
    resp = auth_client_a.post('/auth/profile', data={
        'action': 'update_info',
        'full_name': 'Alice J. Johnson, MD',
        'phone_number': '555-9988',
        'blood_group': 'AB+',
        'emergency_contact': 'Dr. Robert (555-0011)',
        'theme_preference': 'dark'
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Profile information updated successfully" in resp.data

    with app.app_context():
        user = User.get_by_id(user_a)
        assert user.full_name == 'Alice J. Johnson, MD'
        assert user.blood_group == 'AB+'
        assert user.emergency_contact == 'Dr. Robert (555-0011)'


