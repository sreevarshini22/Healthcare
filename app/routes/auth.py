from datetime import datetime, timezone, timedelta
import re
from flask import Blueprint, render_template, request, flash, redirect, url_for, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User, PendingRegistration, LoginOTP
from app.database import get_db
from app.utils.security import (
    validate_password_strength, 
    delete_all_user_files,
    validate_email,
    validate_phone,
    normalize_phone,
    mask_email,
    mask_phone,
    generate_otp_code
)
from app.services.notification_service import send_email_notification, send_sms_notification
from app.utils.helpers import log_activity

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated and request.method == 'GET':
        return redirect(url_for('dashboard.index'))
        
    if request.method == 'POST':
        raw_name = request.form.get('name', '').strip() or request.form.get('full_name', '').strip()
        raw_email = request.form.get('email', '').strip()
        raw_phone = request.form.get('phone_number', '').strip()
        raw_password = request.form.get('password', '').strip()
        
        # 1. Validate name
        if not raw_name:
            flash("Please enter your full name.", "danger")
            return render_template('auth/register.html', name=raw_name, email=raw_email, phone_number=raw_phone)
            
        # 2. Validate email
        is_email_valid, clean_email, email_err = validate_email(raw_email)
        if not is_email_valid:
            flash(email_err, "danger")
            return render_template('auth/register.html', name=raw_name, email=raw_email, phone_number=raw_phone)
            
        # 3. Validate phone
        is_phone_valid, clean_phone, phone_err = validate_phone(raw_phone)
        if not is_phone_valid:
            flash(phone_err, "danger")
            return render_template('auth/register.html', name=raw_name, email=raw_email, phone_number=raw_phone)
            
        # 4. Validate password
        if not raw_password or len(raw_password) < 6:
            flash("Password must be at least 6 characters long.", "danger")
            return render_template('auth/register.html', name=raw_name, email=raw_email, phone_number=raw_phone)
            
        # 5. Check for existing users with duplicate email
        existing_by_email = User.get_by_email(clean_email)
        if existing_by_email:
            flash("An account with this email address already exists. Please log in.", "warning")
            return redirect(url_for('auth.login', identifier=clean_email))
            
        # 6. Check for existing users with duplicate phone
        existing_by_phone = User.get_by_phone(clean_phone)
        if existing_by_phone:
            flash("An account with this phone number already exists. Please log in.", "warning")
            return redirect(url_for('auth.login', identifier=clean_phone))
            
        # 7. Create User immediately in MongoDB
        try:
            new_user = User.create_user(
                full_name=raw_name,
                email=clean_email,
                phone_number=clean_phone,
                password=raw_password,
                email_verified=True,
                phone_verified=True
            )
            
            log_activity(new_user.id, "Account Created", "User successfully registered with credentials.")
            login_user(new_user, remember=True)
            flash(f"Welcome to MediVault, {new_user.full_name}! Your personal health record manager is ready.", "success")
            return redirect(url_for('dashboard.index'))
        except Exception as e:
            flash("An error occurred creating your account. Please try again.", "danger")
            return render_template('auth/register.html', name=raw_name, email=raw_email, phone_number=raw_phone)
            
    return render_template('auth/register.html')


@auth_bp.route('/verify-registration', methods=['GET', 'POST'])
def verify_registration():
    if current_user.is_authenticated and request.method == 'GET':
        return redirect(url_for('dashboard.index'))
        
    token = request.args.get('token') or session.get('reg_session_token')
    pending = PendingRegistration.get_by_token(token) if token else None
    
    if not pending:
        if current_user.is_authenticated:
            return redirect(url_for('dashboard.index'))
        return redirect(url_for('auth.register'))
        
    masked_email = mask_email(pending.get('email'))
    masked_phone = mask_phone(pending.get('phone_number'))
    
    if request.method == 'POST':
        email_otp = request.form.get('email_otp', '').strip()
        sms_otp = request.form.get('sms_otp', '').strip()
        
        if not email_otp or not sms_otp:
            flash("Please enter both the Email OTP and the SMS OTP.", "danger")
            return render_template('auth/verify_registration.html', 
                                   token=token, 
                                   masked_email=masked_email, 
                                   masked_phone=masked_phone)
                                   
        is_valid, err_msg, reg_doc = PendingRegistration.verify_otps(token, email_otp, sms_otp)
        
        if not is_valid:
            flash(err_msg, "danger")
            still_exists = PendingRegistration.get_by_token(token)
            if not still_exists:
                return redirect(url_for('auth.register'))
            return render_template('auth/verify_registration.html', 
                                   token=token, 
                                   masked_email=masked_email, 
                                   masked_phone=masked_phone)
                                   
        # Valid! Create User in MongoDB
        try:
            new_user = User.create_user(
                full_name=reg_doc.get('full_name') or None,
                email=reg_doc['email'],
                phone_number=reg_doc['phone_number'],
                password_hash=reg_doc.get('password_hash'),
                email_verified=True,
                phone_verified=True
            )
            
            session.pop('reg_session_token', None)
            log_activity(new_user.id, "Account Created", "User successfully registered.")
            
            login_user(new_user, remember=True)
            flash(f"Welcome to MediVault, {new_user.full_name}! Your personal health record manager is ready.", "success")
            return redirect(url_for('dashboard.index'))
        except Exception as e:
            flash("An error occurred creating your account. Please try again.", "danger")
            return redirect(url_for('auth.register'))
            
    return render_template('auth/verify_registration.html', 
                           token=token, 
                           masked_email=masked_email, 
                           masked_phone=masked_phone)


@auth_bp.route('/resend-registration-otp', methods=['POST'])
def resend_registration_otp():
    token = request.form.get('token') or session.get('reg_session_token')
    if not token:
        flash("Verification session not found. Please register again.", "warning")
        return redirect(url_for('auth.register'))
        
    pending = PendingRegistration.get_by_token(token)
    if not pending:
        flash("Verification session has expired. Please register again.", "warning")
        return redirect(url_for('auth.register'))
        
    new_email_otp = generate_otp_code()
    new_sms_otp = generate_otp_code()
    
    success, updated_doc = PendingRegistration.resend(token, new_email_otp, new_sms_otp)
    if not success:
        flash("Failed to resend verification codes. Please register again.", "danger")
        return redirect(url_for('auth.register'))
        
    flash("Fresh verification codes have been sent to your email and phone number.", "info")
    return redirect(url_for('auth.verify_registration', token=token))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated and request.method == 'GET':
        return redirect(url_for('dashboard.index'))
        
    prefill_identifier = request.args.get('identifier', '')
    
    if request.method == 'POST':
        raw_identifier = request.form.get('identifier', '').strip()
        raw_password = request.form.get('password', '').strip()
        
        if not raw_identifier:
            flash("Please enter your registered Email Address or Phone Number.", "danger")
            return render_template('auth/login.html', identifier=raw_identifier)
            
        # Determine whether identifier is email or phone
        if '@' in raw_identifier:
            is_valid, clean_email, err = validate_email(raw_identifier)
            if not is_valid:
                flash(err, "danger")
                return render_template('auth/login.html', identifier=raw_identifier)
            user = User.get_by_email(clean_email)
        else:
            is_valid, clean_phone, err = validate_phone(raw_identifier)
            if not is_valid:
                flash(err, "danger")
                return render_template('auth/login.html', identifier=raw_identifier)
            user = User.get_by_phone(clean_phone)
            
        if not user:
            flash("No account found matching this email address or phone number. Please check your credentials or create an account.", "danger")
            return render_template('auth/login.html', identifier=raw_identifier)
            
        if not user.is_active:
            flash("Your account has been deactivated. Please contact support.", "danger")
            return render_template('auth/login.html', identifier=raw_identifier)
            
        # Direct password authentication
        if user.password_hash:
            if not raw_password or not user.check_password(raw_password):
                flash("Incorrect password. Please check your credentials.", "danger")
                return render_template('auth/login.html', identifier=raw_identifier)
        elif raw_password and not user.check_password(raw_password):
            flash("Incorrect password. Please check your credentials.", "danger")
            return render_template('auth/login.html', identifier=raw_identifier)

        login_user(user, remember=True)
        log_activity(user.id, "User Login", "User logged in with credentials.")
        flash(f"Welcome back, {user.full_name}!", "success")
        next_page = request.args.get('next') or request.form.get('next')
        return redirect(next_page or url_for('dashboard.index'))
        
    return render_template('auth/login.html', identifier=prefill_identifier)


@auth_bp.route('/verify-login', methods=['GET', 'POST'])
def verify_login():
    if current_user.is_authenticated and request.method == 'GET':
        return redirect(url_for('dashboard.index'))
        
    token = request.args.get('token') or session.get('login_session_token')
    login_record = LoginOTP.get_by_token(token) if token else None
    
    if not login_record:
        if current_user.is_authenticated:
            return redirect(url_for('dashboard.index'))
        return redirect(url_for('auth.login'))
        
    channel = login_record.get('channel', 'email')
    target = login_record.get('target', '')
    masked_target = mask_email(target) if channel == 'email' else mask_phone(target)
    next_page = request.args.get('next') or request.form.get('next')
    
    if request.method == 'POST':
        entered_code = request.form.get('otp_code', '').strip()
        
        if not entered_code:
            flash("Please enter the 6-digit verification code.", "danger")
            return render_template('auth/verify_login.html', 
                                   token=token, 
                                   channel=channel, 
                                   masked_target=masked_target,
                                   next=next_page)
                                   
        is_valid, err_msg, user_id = LoginOTP.verify_code(token, entered_code)
        
        if not is_valid:
            flash(err_msg, "danger")
            still_exists = LoginOTP.get_by_token(token)
            if not still_exists:
                return redirect(url_for('auth.login'))
            return render_template('auth/verify_login.html', 
                                   token=token, 
                                   channel=channel, 
                                   masked_target=masked_target,
                                   next=next_page)
                                   
        # Login user
        user = User.get_by_id(user_id)
        if not user:
            flash("User account not found. Please try again.", "danger")
            return redirect(url_for('auth.login'))
            
        session.pop('login_session_token', None)
        login_user(user, remember=True)
        log_activity(user.id, "User Login", f"Signed in successfully.")
        
        flash(f"Welcome back, {user.full_name}!", "success")
        if next_page and next_page.startswith('/'):
            return redirect(next_page)
        return redirect(url_for('dashboard.index'))
        
    return render_template('auth/verify_login.html', 
                           token=token, 
                           channel=channel, 
                           masked_target=masked_target,
                           next=next_page)



@auth_bp.route('/logout')
@login_required
def logout():
    log_activity(current_user.id, "User Logout", "Signed out securely.")
    logout_user()
    session.clear()
    flash("You have been signed out securely. Thank you for using MediVault.", "info")
    return redirect(url_for('main.index'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_info':
            full_name = request.form.get('full_name', '').strip()
            phone_number = request.form.get('phone_number', '').strip()
            blood_group = request.form.get('blood_group', '').strip()
            emergency_contact = request.form.get('emergency_contact', '').strip()
            theme_pref = request.form.get('theme_preference', 'light')
            
            if not full_name:
                flash("Full name cannot be empty.", "danger")
                return redirect(url_for('auth.profile'))
                
            current_user.update_profile(
                full_name=full_name,
                phone_number=phone_number,
                blood_group=blood_group,
                emergency_contact=emergency_contact,
                theme_preference=theme_pref
            )
            
            log_activity(current_user.id, "Profile Updated", "Personal info and preferences updated.")
            flash("Profile information updated successfully.", "success")
            return redirect(url_for('auth.profile'))
            
        elif action == 'change_password':
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_new_password = request.form.get('confirm_new_password', '')
            
            if not current_user.check_password(current_password):
                flash("Current password is incorrect.", "danger")
                return redirect(url_for('auth.profile'))
                
            if new_password != confirm_new_password:
                flash("New passwords do not match.", "danger")
                return redirect(url_for('auth.profile'))
                
            is_strong, msg = validate_password_strength(new_password)
            if not is_strong:
                flash(msg, "warning")
                return redirect(url_for('auth.profile'))
                
            current_user.set_password(new_password)
            log_activity(current_user.id, "Password Changed", "User updated account password.")
            flash("Password updated successfully.", "success")
            return redirect(url_for('auth.profile'))
            
    return render_template('auth/profile.html')


@auth_bp.route('/toggle-theme', methods=['POST'])
@login_required
def toggle_theme():
    """Toggle theme preference via AJAX or form."""
    new_theme = 'dark' if current_user.theme_preference == 'light' else 'light'
    current_user.update_profile(theme_preference=new_theme)
    return {'status': 'success', 'theme': new_theme}


@auth_bp.route('/delete-account', methods=['POST'])
@login_required
def delete_account():
    """Secure account deletion with full data and file removal."""
    password = request.form.get('confirm_delete_password', '')
    confirmation_text = request.form.get('confirmation_text', '').strip()
    
    if confirmation_text != "DELETE MY ACCOUNT":
        flash("Please type 'DELETE MY ACCOUNT' to confirm account deletion.", "danger")
        return redirect(url_for('auth.profile'))
        
    if not current_user.check_password(password):
        flash("Incorrect password. Account deletion aborted.", "danger")
        return redirect(url_for('auth.profile'))
        
    user_id = current_user.id
    
    try:
        # 1. Purge all uploaded documents from disk
        delete_all_user_files(user_id)
        
        # 2. Delete user and associated collections from MongoDB
        User.delete_user(user_id)
        logout_user()
        session.clear()
        
        flash("Your account and all associated medical data have been permanently deleted.", "info")
        return redirect(url_for('main.index'))
    except Exception as e:
        flash("An error occurred while deleting your account. Please contact support.", "danger")
        return redirect(url_for('auth.profile'))
