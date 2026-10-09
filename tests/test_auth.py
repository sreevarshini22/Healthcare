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
    """Test full registration workflow: submit email+phone -> enter OTPs -> user created."""
    # Step 1: Submit email and phone number
    resp = client.post('/auth/register', data={
        'email': 'welby@hospital.org',
        'phone_number': '+1 (617) 555-0188'
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert b"Verify Identity" in resp.data

    # Retrieve pending OTPs from MongoDB
    with app.app_context():
        db = get_db()
        pending = db.pending_registrations.find_one({'email': 'welby@hospital.org'})
        assert pending is not None
        email_otp = pending['email_otp']
        sms_otp = pending['sms_otp']
        token = pending['session_token']

    # Step 2: Verify OTPs
    verify_resp = client.post(f'/auth/verify-registration?token={token}', data={
        'email_otp': email_otp,
        'sms_otp': sms_otp
    }, follow_redirects=True)

    assert verify_resp.status_code == 200
    assert b"Welcome to MediVault" in verify_resp.data

    # Step 3: Check user in MongoDB
    with app.app_context():
        user = User.get_by_email('welby@hospital.org')
        assert user is not None
        assert user.email == 'welby@hospital.org'
        assert user.phone_number is not None

def test_register_invalid_email_and_phone(client):
    """Test validation errors for malformed email and short phone numbers."""
    # Invalid email
    resp1 = client.post('/auth/register', data={
        'email': 'invalid-email-string',
        'phone_number': '555-0100'
    }, follow_redirects=True)
    assert b"valid email address" in resp1.data

    # Short phone
    resp2 = client.post('/auth/register', data={
        'email': 'valid@example.com',
        'phone_number': '123'
    }, follow_redirects=True)
    assert b"at least 7 digits" in resp2.data

def test_register_duplicate_email_and_phone(client, user_a):
    """Test that duplicate email or phone number is rejected with warning."""
    # Duplicate email
    resp1 = client.post('/auth/register', data={
        'email': 'alice@example.com',
        'phone_number': '+1-555-9999'
    }, follow_redirects=True)
    assert b"already exists" in resp1.data

    # Duplicate phone
    resp2 = client.post('/auth/register', data={
        'email': 'brandnew@example.com',
        'phone_number': '555-0100' # Alice's phone
    }, follow_redirects=True)
    assert b"already exists" in resp2.data

def test_register_invalid_otp(client, app):
    """Test rejection when entered OTPs do not match."""
    client.post('/auth/register', data={
        'email': 'otpcheck@example.com',
        'phone_number': '555-0199'
    }, follow_redirects=True)

    with app.app_context():
        db = get_db()
        pending = db.pending_registrations.find_one({'email': 'otpcheck@example.com'})
        token = pending['session_token']

    # Submit incorrect OTPs
    resp = client.post(f'/auth/verify-registration?token={token}', data={
        'email_otp': '000000',
        'sms_otp': '000000'
    }, follow_redirects=True)

    assert b"Both Email and SMS verification codes are incorrect" in resp.data

def test_login_with_email_success(client, user_a, app):
    """Test login via registered Email and OTP verification."""
    # Step 1: Submit email
    resp = client.post('/auth/login', data={
        'identifier': 'alice@example.com'
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert b"Enter Verification Code" in resp.data

    # Retrieve generated login OTP
    with app.app_context():
        db = get_db()
        verification = db.otp_verifications.find_one({'channel': 'email'})
        assert verification is not None
        otp_code = verification['otp_code']
        token = verification['session_token']

    # Step 2: Submit valid OTP
    verify_resp = client.post(f'/auth/verify-login?token={token}', data={
        'otp_code': otp_code
    }, follow_redirects=True)

    assert verify_resp.status_code == 200
    assert b"Welcome back, Alice Johnson" in verify_resp.data

def test_login_with_phone_success(client, user_a, app):
    """Test login via registered Phone Number and OTP verification."""
    # Step 1: Submit phone number
    resp = client.post('/auth/login', data={
        'identifier': '555-0100'
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert b"Enter Verification Code" in resp.data

    # Retrieve generated login OTP
    with app.app_context():
        db = get_db()
        verification = db.otp_verifications.find_one({'channel': 'sms'})
        assert verification is not None
        otp_code = verification['otp_code']
        token = verification['session_token']

    # Step 2: Submit valid OTP
    verify_resp = client.post(f'/auth/verify-login?token={token}', data={
        'otp_code': otp_code
    }, follow_redirects=True)

    assert verify_resp.status_code == 200
    assert b"Welcome back, Alice Johnson" in verify_resp.data

def test_login_nonexistent_account(client):
    """Test error message when trying to log in with an unregistered identifier."""
    resp = client.post('/auth/login', data={
        'identifier': 'nobody@hospital.org'
    }, follow_redirects=True)

    assert b"No account found matching this email address or phone number" in resp.data

def test_login_invalid_otp(client, user_a, app):
    """Test rejection of incorrect login OTP."""
    client.post('/auth/login', data={
        'identifier': 'alice@example.com'
    }, follow_redirects=True)

    with app.app_context():
        db = get_db()
        verification = db.otp_verifications.find_one({'channel': 'email'})
        token = verification['session_token']

    resp = client.post(f'/auth/verify-login?token={token}', data={
        'otp_code': '999999'
    }, follow_redirects=True)

    assert b"Invalid verification code" in resp.data

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

def test_login_otp_max_attempts_lockout(client, user_a, app):
    """Test that 5 consecutive incorrect OTP submissions lock out the session."""
    client.post('/auth/login', data={'identifier': 'alice@example.com'}, follow_redirects=True)

    with app.app_context():
        db = get_db()
        verification = db.otp_verifications.find_one({'channel': 'email'})
        token = verification['session_token']

    # Submit 5 wrong OTPs
    for i in range(4):
        resp = client.post(f'/auth/verify-login?token={token}', data={'otp_code': '000000'}, follow_redirects=True)
        assert b"Invalid verification code" in resp.data

    # 5th attempt should trigger lockout message
    resp5 = client.post(f'/auth/verify-login?token={token}', data={'otp_code': '000000'}, follow_redirects=True)
    assert b"Too many failed attempts" in resp5.data

    # Verify session is deleted from MongoDB
    with app.app_context():
        assert LoginOTP.get_by_token(token) is None

def test_registration_otp_max_attempts_lockout(client, app):
    """Test that 5 consecutive incorrect registration OTPs lock out the registration session."""
    client.post('/auth/register', data={'email': 'lockout@example.com', 'phone_number': '555-0333'}, follow_redirects=True)

    with app.app_context():
        db = get_db()
        pending = db.pending_registrations.find_one({'email': 'lockout@example.com'})
        token = pending['session_token']

    for i in range(4):
        resp = client.post(f'/auth/verify-registration?token={token}', data={'email_otp': '000000', 'sms_otp': '000000'}, follow_redirects=True)
        assert b"incorrect" in resp.data

    # 5th attempt
    resp5 = client.post(f'/auth/verify-registration?token={token}', data={'email_otp': '000000', 'sms_otp': '000000'}, follow_redirects=True)
    assert b"Too many failed attempts" in resp5.data

    with app.app_context():
        assert PendingRegistration.get_by_token(token) is None

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

def test_register_with_credentials_name_email_phone_password(client, app):
    """Test registration with full name, email, phone number, and password credentials."""
    resp = client.post('/auth/register', data={
        'name': 'Dr. Marcus Welby',
        'email': 'marcus.welby@medivault.health',
        'phone_number': '+1 (415) 555-0199',
        'password': 'StrongPassword123!'
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert b"Verify Identity" in resp.data

    with app.app_context():
        db = get_db()
        pending = db.pending_registrations.find_one({'email': 'marcus.welby@medivault.health'})
        assert pending is not None
        assert pending['full_name'] == 'Dr. Marcus Welby'
        assert pending['password_hash'] != ""
        email_otp = pending['email_otp']
        sms_otp = pending['sms_otp']
        token = pending['session_token']

    # Complete OTP verification
    verify_resp = client.post(f'/auth/verify-registration?token={token}', data={
        'email_otp': email_otp,
        'sms_otp': sms_otp
    }, follow_redirects=True)

    assert verify_resp.status_code == 200
    assert b"Welcome to MediVault, Dr. Marcus Welby!" in verify_resp.data

    # Verify user was saved with password and full name in MongoDB
    with app.app_context():
        user = User.get_by_email('marcus.welby@medivault.health')
        assert user is not None
        assert user.full_name == 'Dr. Marcus Welby'
        assert user.check_password('StrongPassword123!') is True

def test_login_with_direct_password(client, app):
    """Test direct password sign-in without needing OTP when password is provided."""
    # Create user with password
    with app.app_context():
        User.create_user(
            full_name='Clara Barton',
            email='clara.barton@redcross.org',
            phone_number='+1 (202) 555-0177',
            password='SecureClaraPassword456!'
        )

    # Login with correct password
    resp = client.post('/auth/login', data={
        'identifier': 'clara.barton@redcross.org',
        'password': 'SecureClaraPassword456!'
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert b"Welcome back, Clara Barton!" in resp.data

    # Login with wrong password
    bad_resp = client.post('/auth/login', data={
        'identifier': 'clara.barton@redcross.org',
        'password': 'WrongPassword123'
    }, follow_redirects=True)

    assert bad_resp.status_code == 200
    assert b"Incorrect password" in bad_resp.data


