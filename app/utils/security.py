import os
import uuid
import re
import mimetypes
import shutil
from werkzeug.utils import secure_filename
from flask import current_app

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'webp'}
MIME_MAP = {
    'pdf': 'application/pdf',
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'webp': 'image/webp'
}

def allowed_file(filename):
    """Check if the filename has an allowed extension."""
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS

import secrets

def generate_otp_code():
    """Generate a cryptographically secure 6-digit numeric OTP."""
    return f"{secrets.randbelow(1000000):06d}"

def validate_email(email_str):
    """
    Validate and normalize email address format.
    Returns (is_valid: bool, cleaned_email: str, error_message: str).
    """
    if not email_str:
        return False, "", "Email address is required."
    email_clean = email_str.strip().lower()
    email_pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    if not re.match(email_pattern, email_clean):
        return False, email_clean, "Please enter a valid email address (e.g., user@example.com)."
    try:
        from email_validator import validate_email as ev_validate, EmailNotValidError
        validated = ev_validate(email_clean, check_deliverability=False)
        email_clean = validated.normalized
    except Exception:
        pass
    return True, email_clean, ""

def normalize_phone(phone_str):
    """Normalize phone number to digits with optional leading '+'."""
    if not phone_str:
        return ""
    phone = phone_str.strip()
    has_plus = phone.startswith('+')
    digits = re.sub(r'\D', '', phone)
    if has_plus:
        return f"+{digits}"
    return digits

def validate_phone(phone_str):
    """
    Validate and normalize phone number.
    Returns (is_valid: bool, cleaned_phone: str, error_message: str).
    """
    if not phone_str:
        return False, "", "Phone number is required."
    raw = phone_str.strip()
    digits = re.sub(r'\D', '', raw)
    if len(digits) < 7:
        return False, raw, "Phone number must contain at least 7 digits."
    if len(digits) > 15:
        return False, raw, "Phone number must not exceed 15 digits."
    
    # Standard format: if raw starts with +, keep +; else format cleanly
    normalized = f"+{digits}" if raw.startswith('+') else digits
    return True, normalized, ""

def mask_email(email):
    """Mask email for privacy, e.g. j***n@example.com."""
    if not email or '@' not in email:
        return email or ""
    parts = email.split('@', 1)
    username, domain = parts[0], parts[1]
    if len(username) <= 2:
        masked_user = username[0] + "***"
    else:
        masked_user = username[0] + "***" + username[-1]
    return f"{masked_user}@{domain}"

def mask_phone(phone):
    """Mask phone for privacy, e.g. (***) ***-1234."""
    if not phone:
        return ""
    digits = re.sub(r'\D', '', phone)
    if len(digits) <= 4:
        return "***-" + digits
    last_four = digits[-4:]
    return f"(***) ***-{last_four}"

def validate_password_strength(password):
    """
    Validate password strength:
    - At least 8 characters
    - Contains at least one digit
    - Contains at least one letter
    """
    if not password or len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"\d", password):
        return False, "Password must include at least one number."
    if not re.search(r"[a-zA-Z]", password):
        return False, "Password must include at least one letter."
    return True, "Password is strong."

def validate_file_content(file_stream, ext):
    """Inspect file header magic bytes to verify genuine file type."""
    current_pos = file_stream.tell()
    file_stream.seek(0)
    header = file_stream.read(16)
    file_stream.seek(current_pos)
    
    if ext == 'pdf':
        if not header.startswith(b'%PDF'):
            return False, "Invalid PDF header detected."
    elif ext in ['jpg', 'jpeg']:
        if not header.startswith(b'\xff\xd8\xff'):
            return False, "Invalid JPEG image format."
    elif ext == 'png':
        if not header.startswith(b'\x89PNG\r\n\x1a\n'):
            return False, "Invalid PNG image format."
    elif ext == 'webp':
        if len(header) >= 12 and header[0:4] == b'RIFF' and header[8:12] == b'WEBP':
            return True, "Valid WebP image."
        return False, "Invalid WebP image format."
    return True, "Valid file format."

def get_storage_path():
    """Retrieve the configured private storage folder."""
    return current_app.config.get('STORAGE_FOLDER') or current_app.config.get('UPLOAD_FOLDER')

def save_user_file(file, user_id):
    """
    Saves an uploaded file to private user storage with a sanitized UUID name.
    Returns file_reference dictionary: {stored_filename, original_filename, file_size, mime_type}
    """
    if not file or not file.filename:
        raise ValueError("No file provided.")
        
    original_filename = secure_filename(file.filename)
    if not original_filename:
        original_filename = "document"
        
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"File extension '.{ext}' is not supported. Allowed: PDF, PNG, JPG, JPEG, WEBP.")

    # Validate header magic bytes
    is_valid, msg = validate_file_content(file.stream, ext)
    if not is_valid:
        raise ValueError(f"Security validation failed: {msg}")

    # Generate unique filename to prevent overwriting and traversal attacks
    stored_filename = f"{uuid.uuid4().hex}.{ext}"
    
    # User-specific directory in private storage
    storage_root = get_storage_path()
    user_dir = os.path.join(storage_root, f"user_{user_id}")
    os.makedirs(user_dir, exist_ok=True)
    
    file_path = os.path.join(user_dir, stored_filename)
    file.save(file_path)
    
    file_size = os.path.getsize(file_path)
    mime_type = MIME_MAP.get(ext) or mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
    
    return {
        'stored_filename': stored_filename,
        'original_filename': original_filename,
        'file_size': file_size,
        'mime_type': mime_type
    }

def delete_user_file(stored_filename, user_id):
    """Safely deletes an isolated user file from disk."""
    if not stored_filename:
        return
    safe_name = os.path.basename(stored_filename)
    storage_root = get_storage_path()
    user_dir = os.path.join(storage_root, f"user_{user_id}")
    file_path = os.path.join(user_dir, safe_name)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass

def delete_all_user_files(user_id):
    """Purges entire user private storage directory upon account deletion."""
    storage_root = get_storage_path()
    user_dir = os.path.join(storage_root, f"user_{user_id}")
    if os.path.exists(user_dir):
        try:
            shutil.rmtree(user_dir)
        except OSError:
            pass
