from datetime import datetime, date, timezone, timedelta
import secrets
import re
from bson import ObjectId
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.database import get_db

def utc_now():
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)

def parse_object_id(id_val):
    """Safely convert string or ObjectId into ObjectId."""
    if not id_val:
        return None
    if isinstance(id_val, ObjectId):
        return id_val
    try:
        return ObjectId(str(id_val))
    except Exception:
        return id_val

def user_id_filter(user_id):
    """Generate MongoDB query filter that matches both ObjectId and string representation of user_id."""
    try:
        oid = ObjectId(str(user_id))
        return {'$in': [oid, str(user_id)]}
    except Exception:
        return str(user_id)


class User(UserMixin):
    """User model wrapping a MongoDB 'users' document for Flask-Login."""
    def __init__(self, doc):
        self.doc = doc or {}
        self._id = self.doc.get('_id')
        self.id = str(self._id) if self._id else None
        self.full_name = self.doc.get('full_name', '')
        self.email = self.doc.get('email', '')
        self.password_hash = self.doc.get('password_hash', '')
        self.phone_number = self.doc.get('phone_number')
        self.blood_group = self.doc.get('blood_group')
        self.emergency_contact = self.doc.get('emergency_contact')
        self.theme_preference = self.doc.get('theme_preference', 'light')
        self.reset_token = self.doc.get('reset_token')
        self.reset_token_expiry = self.doc.get('reset_token_expiry')
        self.ai_consent = self.doc.get('ai_consent', False)
        self.voice_opt_in = self.doc.get('voice_opt_in', False)
        
        # Notification preferences
        prefs = self.doc.get('reminder_preferences') or {}
        self.reminder_preferences = {
            'email': prefs.get('email', True),
            'sms': prefs.get('sms', False),
            'voice': prefs.get('voice', False),
            'lead_times': prefs.get('lead_times', ['24h', '2h'])
        }
        
        self.created_at = self.doc.get('created_at')
        self.updated_at = self.doc.get('updated_at')

    @property
    def is_active(self):
        return bool(self.doc.get('is_active', True))

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def set_password(self, new_password):
        db = get_db()
        new_hash = generate_password_hash(new_password)
        self.password_hash = new_hash
        self.doc['password_hash'] = new_hash
        db.users.update_one(
            {'_id': self._id},
            {'$set': {'password_hash': new_hash, 'updated_at': utc_now()}}
        )

    def get_id(self):
        return self.id

    def generate_reset_token(self):
        db = get_db()
        token = secrets.token_urlsafe(32)
        expiry = utc_now() + timedelta(hours=2)
        db.users.update_one(
            {'_id': self._id},
            {'$set': {'reset_token': token, 'reset_token_expiry': expiry}}
        )
        self.reset_token = token
        self.reset_token_expiry = expiry
        return token

    def verify_reset_token(self, token):
        if not self.reset_token or self.reset_token != token:
            return False
        if not self.reset_token_expiry:
            return False
        expiry = self.reset_token_expiry
        if hasattr(expiry, 'tzinfo') and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return expiry >= utc_now()

    def clear_reset_token(self):
        db = get_db()
        db.users.update_one(
            {'_id': self._id},
            {'$set': {'reset_token': None, 'reset_token_expiry': None, 'updated_at': utc_now()}}
        )
        self.reset_token = None
        self.reset_token_expiry = None

    def update_profile(self, full_name=None, phone_number=None, blood_group=None, 
                       emergency_contact=None, theme_preference=None):
        db = get_db()
        updates = {'updated_at': utc_now()}
        if full_name is not None:
            self.full_name = full_name.strip()
            updates['full_name'] = self.full_name
        if phone_number is not None:
            self.phone_number = phone_number.strip() if phone_number else None
            updates['phone_number'] = self.phone_number
        if blood_group is not None:
            self.blood_group = blood_group.strip() if blood_group else None
            updates['blood_group'] = self.blood_group
        if emergency_contact is not None:
            self.emergency_contact = emergency_contact.strip() if emergency_contact else None
            updates['emergency_contact'] = self.emergency_contact
        if theme_preference in ['light', 'dark']:
            self.theme_preference = theme_preference
            updates['theme_preference'] = self.theme_preference

        db.users.update_one({'_id': self._id}, {'$set': updates})

    def update_ai_consent(self, consent: bool):
        db = get_db()
        self.ai_consent = bool(consent)
        db.users.update_one(
            {'_id': self._id},
            {'$set': {'ai_consent': self.ai_consent, 'updated_at': utc_now()}}
        )

    def update_reminder_preferences(self, email=True, sms=False, voice=False, lead_times=None, voice_opt_in=False):
        db = get_db()
        lead_times = lead_times or ['24h', '2h']
        self.reminder_preferences = {
            'email': bool(email),
            'sms': bool(sms),
            'voice': bool(voice),
            'lead_times': lead_times
        }
        self.voice_opt_in = bool(voice_opt_in)
        db.users.update_one(
            {'_id': self._id},
            {'$set': {
                'reminder_preferences': self.reminder_preferences,
                'voice_opt_in': self.voice_opt_in,
                'updated_at': utc_now()
            }}
        )

    @classmethod
    def get_by_id(cls, user_id):
        if not user_id:
            return None
        db = get_db()
        try:
            doc = db.users.find_one({'_id': parse_object_id(user_id)})
            return cls(doc) if doc else None
        except Exception:
            return None

    @classmethod
    def get_by_email(cls, email):
        if not email:
            return None
        db = get_db()
        doc = db.users.find_one({'email': email.strip().lower()})
        return cls(doc) if doc else None

    @classmethod
    def get_by_phone(cls, phone_number):
        if not phone_number:
            return None
        db = get_db()
        phone_clean = phone_number.strip()
        # Try direct match
        doc = db.users.find_one({'phone_number': phone_clean})
        if doc:
            return cls(doc)
            
        # Try matching normalized digits
        digits = re.sub(r'\D', '', phone_clean)
        if digits:
            # Query for documents where digits match
            cursor = db.users.find({'phone_number': {'$exists': True, '$ne': None}})
            for u in cursor:
                u_phone = u.get('phone_number') or ''
                if re.sub(r'\D', '', u_phone) == digits:
                    return cls(u)
        return None

    @classmethod
    def get_by_identifier(cls, identifier):
        """Lookup user by either email or phone number."""
        if not identifier:
            return None
        ident = identifier.strip()
        if '@' in ident:
            return cls.get_by_email(ident)
        return cls.get_by_phone(ident)

    @classmethod
    def create_user(cls, *args, **kwargs):
        db = get_db()
        
        # Parse arguments gracefully whether positional or keyword
        full_name = kwargs.get('full_name')
        email = kwargs.get('email')
        phone_number = kwargs.get('phone_number')
        password = kwargs.get('password')
        
        if len(args) == 1:
            if '@' in str(args[0]):
                email = args[0]
            else:
                full_name = args[0]
        elif len(args) == 2:
            if '@' in str(args[0]):
                email, phone_number = args[0], args[1]
            else:
                full_name, email = args[0], args[1]
        elif len(args) >= 3:
            full_name, email, password = args[0], args[1], args[2]
            if len(args) >= 4:
                phone_number = args[3]
                
        # If email was passed in full_name by mistake
        if not email and full_name and '@' in str(full_name):
            email = full_name
            full_name = None
            
        email_clean = str(email or '').strip().lower()
        if not full_name:
            username_part = email_clean.split('@')[0].replace('.', ' ').replace('_', ' ').title() if email_clean else "Patient"
            full_name = username_part if username_part else "Patient"
        else:
            full_name = str(full_name).strip()
            
        password_hash = generate_password_hash(password) if password else ""
        now = utc_now()
        
        user_doc = {
            'full_name': full_name,
            'email': email_clean,
            'password_hash': password_hash,
            'phone_number': str(phone_number).strip() if phone_number else kwargs.get('phone_number'),
            'blood_group': kwargs.get('blood_group'),
            'emergency_contact': kwargs.get('emergency_contact'),
            'theme_preference': kwargs.get('theme_preference', 'light'),
            'is_active': True,
            'email_verified': kwargs.get('email_verified', True),
            'phone_verified': kwargs.get('phone_verified', True),
            'ai_consent': kwargs.get('ai_consent', False),
            'voice_opt_in': kwargs.get('voice_opt_in', False),
            'reminder_preferences': kwargs.get('reminder_preferences', {
                'email': True,
                'sms': False,
                'voice': False,
                'lead_times': ['24h', '2h']
            }),
            'reset_token': None,
            'reset_token_expiry': None,
            'created_at': now,
            'updated_at': now
        }
        
        result = db.users.insert_one(user_doc)
        user_doc['_id'] = result.inserted_id
        return cls(user_doc)

    @classmethod
    def delete_user(cls, user_id):
        """Cascade deletes user and all their associated records, chats, notifications, and logs."""
        db = get_db()
        u_filter = user_id_filter(user_id)
        db.medical_records.delete_many({'user_id': u_filter})
        db.prescriptions.delete_many({'user_id': u_filter})
        db.appointments.delete_many({'user_id': u_filter})
        db.activity_logs.delete_many({'user_id': u_filter})
        db.chat_sessions.delete_many({'user_id': u_filter})
        db.chat_messages.delete_many({'user_id': u_filter})
        db.notifications.delete_many({'user_id': u_filter})
        db.voice_call_logs.delete_many({'user_id': u_filter})
        db.users.delete_one({'_id': parse_object_id(user_id)})

    def __repr__(self):
        return f"<User {self.email} (ID: {self.id})>"


class PendingRegistration:
    """Manages pending multi-factor OTP registration records in MongoDB."""
    @classmethod
    def create(cls, email, phone_number, email_otp, sms_otp, expires_minutes=10):
        db = get_db()
        token = secrets.token_urlsafe(32)
        now = utc_now()
        expires_at = now + timedelta(minutes=expires_minutes)
        
        # Remove any previous pending registration for this email or phone
        db.pending_registrations.delete_many({
            '$or': [{'email': email.strip().lower()}, {'phone_number': phone_number.strip()}]
        })
        
        doc = {
            'session_token': token,
            'email': email.strip().lower(),
            'phone_number': phone_number.strip(),
            'email_otp': str(email_otp).strip(),
            'sms_otp': str(sms_otp).strip(),
            'expires_at': expires_at,
            'attempts': 0,
            'created_at': now
        }
        db.pending_registrations.insert_one(doc)
        return token

    @classmethod
    def get_by_token(cls, token):
        if not token:
            return None
        db = get_db()
        doc = db.pending_registrations.find_one({'session_token': token})
        if not doc:
            return None
        expires_at = doc.get('expires_at')
        if hasattr(expires_at, 'tzinfo') and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at and expires_at < utc_now():
            return None
        return doc

    @classmethod
    def verify_otps(cls, token, entered_email_otp, entered_sms_otp):
        if not token:
            return False, "Verification session expired. Please start over.", None
        db = get_db()
        doc = db.pending_registrations.find_one({'session_token': token})
        if not doc:
            return False, "Verification session not found or expired. Please submit registration again.", None
        
        expires_at = doc.get('expires_at')
        if hasattr(expires_at, 'tzinfo') and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at and expires_at < utc_now():
            db.pending_registrations.delete_one({'_id': doc['_id']})
            return False, "Verification codes have expired. Please request new codes.", None
        
        attempts = doc.get('attempts', 0)
        expected_email_otp = str(doc.get('email_otp', '')).strip()
        expected_sms_otp = str(doc.get('sms_otp', '')).strip()
        
        clean_email_otp = str(entered_email_otp or '').strip()
        clean_sms_otp = str(entered_sms_otp or '').strip()
        
        email_match = (clean_email_otp == expected_email_otp)
        sms_match = (clean_sms_otp == expected_sms_otp)
        
        if not (email_match and sms_match):
            new_attempts = attempts + 1
            if new_attempts >= 5:
                db.pending_registrations.delete_one({'_id': doc['_id']})
                return False, "Too many failed attempts. Please register again.", None
            db.pending_registrations.update_one({'_id': doc['_id']}, {'$set': {'attempts': new_attempts}})
            if not email_match and not sms_match:
                return False, "Both Email and SMS verification codes are incorrect.", None
            elif not email_match:
                return False, "Invalid Email verification code. Please check your inbox.", None
            elif not sms_match:
                return False, "Invalid SMS verification code. Please check your text messages.", None
        
        # Valid verification!
        db.pending_registrations.delete_one({'_id': doc['_id']})
        return True, "", doc

    @classmethod
    def resend(cls, token, new_email_otp, new_sms_otp, expires_minutes=10):
        db = get_db()
        doc = db.pending_registrations.find_one({'session_token': token})
        if not doc:
            return False, None
        now = utc_now()
        expires_at = now + timedelta(minutes=expires_minutes)
        db.pending_registrations.update_one(
            {'_id': doc['_id']},
            {'$set': {
                'email_otp': str(new_email_otp).strip(),
                'sms_otp': str(new_sms_otp).strip(),
                'expires_at': expires_at,
                'attempts': 0
            }}
        )
        doc['email_otp'] = str(new_email_otp).strip()
        doc['sms_otp'] = str(new_sms_otp).strip()
        return True, doc


class LoginOTP:
    """Manages passwordless login OTP verification records in MongoDB."""
    @classmethod
    def create(cls, user_id, channel, target, otp_code, expires_minutes=10):
        db = get_db()
        token = secrets.token_urlsafe(32)
        now = utc_now()
        expires_at = now + timedelta(minutes=expires_minutes)
        
        # Remove any previous active OTP for this user
        db.otp_verifications.delete_many({'user_id': parse_object_id(user_id)})
        
        doc = {
            'session_token': token,
            'user_id': parse_object_id(user_id),
            'channel': channel,
            'target': target,
            'otp_code': str(otp_code).strip(),
            'expires_at': expires_at,
            'attempts': 0,
            'created_at': now
        }
        db.otp_verifications.insert_one(doc)
        return token

    @classmethod
    def get_by_token(cls, token):
        if not token:
            return None
        db = get_db()
        doc = db.otp_verifications.find_one({'session_token': token})
        if not doc:
            return None
        expires_at = doc.get('expires_at')
        if hasattr(expires_at, 'tzinfo') and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at and expires_at < utc_now():
            return None
        return doc

    @classmethod
    def verify_code(cls, token, entered_code):
        if not token:
            return False, "Login session expired. Please start over.", None
        db = get_db()
        doc = db.otp_verifications.find_one({'session_token': token})
        if not doc:
            return False, "Verification session expired. Please request a new code.", None
            
        expires_at = doc.get('expires_at')
        if hasattr(expires_at, 'tzinfo') and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at and expires_at < utc_now():
            db.otp_verifications.delete_one({'_id': doc['_id']})
            return False, "Verification code has expired. Please request a new one.", None
            
        attempts = doc.get('attempts', 0)
        expected_code = str(doc.get('otp_code', '')).strip()
        clean_code = str(entered_code or '').strip()
        
        if clean_code != expected_code:
            new_attempts = attempts + 1
            if new_attempts >= 5:
                db.otp_verifications.delete_one({'_id': doc['_id']})
                return False, "Too many failed attempts. Please request a new login code.", None
            db.otp_verifications.update_one({'_id': doc['_id']}, {'$set': {'attempts': new_attempts}})
            return False, "Invalid verification code. Please check and try again.", None
            
        user_id = doc.get('user_id')
        db.otp_verifications.delete_one({'_id': doc['_id']})
        return True, "", str(user_id)

    @classmethod
    def resend(cls, token, new_otp_code, expires_minutes=10):
        db = get_db()
        doc = db.otp_verifications.find_one({'session_token': token})
        if not doc:
            return False, None
        now = utc_now()
        expires_at = now + timedelta(minutes=expires_minutes)
        db.otp_verifications.update_one(
            {'_id': doc['_id']},
            {'$set': {
                'otp_code': str(new_otp_code).strip(),
                'expires_at': expires_at,
                'attempts': 0
            }}
        )
        doc['otp_code'] = str(new_otp_code).strip()
        return True, doc


class MedicalRecord:
    """Medical record model wrapping a MongoDB 'medical_records' document."""
    def __init__(self, doc):
        self.doc = doc or {}
        self._id = self.doc.get('_id')
        self.id = str(self._id) if self._id else None
        self.user_id = str(self.doc.get('user_id')) if self.doc.get('user_id') else None
        self.title = self.doc.get('title', '')
        self.category = self.doc.get('category', '')
        self.report_date = self.doc.get('report_date')
        self.doctor_or_facility = self.doc.get('doctor_or_facility') or self.doc.get('clinician_or_hospital') or ''
        self.notes = self.doc.get('notes', '')
        
        file_ref = self.doc.get('file_reference') or {}
        self.stored_filename = self.doc.get('stored_filename') or file_ref.get('stored_filename', '')
        self.original_filename = self.doc.get('original_filename') or file_ref.get('original_filename', 'document')
        self.file_size = self.doc.get('file_size') or file_ref.get('file_size', 0)
        self.file_mime = self.doc.get('file_mime') or file_ref.get('mime_type', 'application/octet-stream')
        self.file_reference = file_ref or {
            'stored_filename': self.stored_filename,
            'original_filename': self.original_filename,
            'file_size': self.file_size,
            'mime_type': self.file_mime
        }
        
        # AI Summarization fields
        self.ai_summary = self.doc.get('ai_summary')
        self.ai_summary_date = self.doc.get('ai_summary_date')
        self.extracted_text = self.doc.get('extracted_text')
        
        self.created_at = self.doc.get('created_at')
        self.updated_at = self.doc.get('updated_at')

    @property
    def is_pdf(self):
        return self.file_mime == 'application/pdf' or (self.stored_filename and self.stored_filename.lower().endswith('.pdf'))

    @property
    def is_image(self):
        if self.file_mime and self.file_mime.startswith('image/'):
            return True
        if self.stored_filename:
            return any(self.stored_filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp'])
        return False

    @classmethod
    def create(cls, user_id, title, category, report_date, doctor_or_facility=None, file_info=None, notes=None, extracted_text=None):
        db = get_db()
        now = utc_now()
        file_info = file_info or {}
        
        doc = {
            'user_id': parse_object_id(user_id),
            'title': title.strip(),
            'category': category.strip(),
            'report_date': report_date,
            'doctor_or_facility': doctor_or_facility.strip() if doctor_or_facility else None,
            'notes': notes.strip() if notes else None,
            'stored_filename': file_info.get('stored_filename', ''),
            'original_filename': file_info.get('original_filename', ''),
            'file_size': file_info.get('file_size', 0),
            'file_mime': file_info.get('mime_type', 'application/octet-stream'),
            'file_reference': {
                'stored_filename': file_info.get('stored_filename', ''),
                'original_filename': file_info.get('original_filename', ''),
                'file_size': file_info.get('file_size', 0),
                'mime_type': file_info.get('mime_type', 'application/octet-stream')
            },
            'ai_summary': None,
            'ai_summary_date': None,
            'extracted_text': extracted_text,
            'created_at': now,
            'updated_at': now
        }
        
        res = db.medical_records.insert_one(doc)
        doc['_id'] = res.inserted_id
        return cls(doc)

    @classmethod
    def get_by_id(cls, record_id, user_id=None):
        if not record_id:
            return None
        db = get_db()
        try:
            query = {'_id': parse_object_id(record_id)}
            if user_id:
                query['user_id'] = user_id_filter(user_id)
            doc = db.medical_records.find_one(query)
            return cls(doc) if doc else None
        except Exception:
            return None

    @classmethod
    def find_by_user(cls, user_id, category=None, search=None, sort='newest'):
        db = get_db()
        query = {'user_id': user_id_filter(user_id)}
        
        if category and category != 'All':
            query['category'] = category
            
        if search:
            rx = re.compile(re.escape(search), re.IGNORECASE)
            query['$or'] = [
                {'title': rx},
                {'doctor_or_facility': rx},
                {'notes': rx},
                {'original_filename': rx},
                {'category': rx}
            ]
            
        sort_field = [('report_date', -1), ('created_at', -1)]
        if sort == 'oldest':
            sort_field = [('report_date', 1), ('created_at', 1)]
        elif sort == 'title_asc':
            sort_field = [('title', 1)]
        elif sort == 'title_desc':
            sort_field = [('title', -1)]
            
        cursor = db.medical_records.find(query).sort(sort_field)
        return [cls(d) for d in cursor]

    @classmethod
    def update(cls, record_id, user_id, title=None, category=None, report_date=None, 
               doctor_or_facility=None, notes=None, file_info=None):
        db = get_db()
        updates = {'updated_at': utc_now()}
        
        if title is not None:
            updates['title'] = title.strip()
        if category is not None:
            updates['category'] = category.strip()
        if report_date is not None:
            updates['report_date'] = report_date
        if doctor_or_facility is not None:
            updates['doctor_or_facility'] = doctor_or_facility.strip() if doctor_or_facility else None
        if notes is not None:
            updates['notes'] = notes.strip() if notes else None
            
        if file_info:
            updates['stored_filename'] = file_info.get('stored_filename', '')
            updates['original_filename'] = file_info.get('original_filename', '')
            updates['file_size'] = file_info.get('file_size', 0)
            updates['file_mime'] = file_info.get('mime_type', 'application/octet-stream')
            updates['file_reference'] = {
                'stored_filename': file_info.get('stored_filename', ''),
                'original_filename': file_info.get('original_filename', ''),
                'file_size': file_info.get('file_size', 0),
                'mime_type': file_info.get('mime_type', 'application/octet-stream')
            }
            # Reset summary if file replaced
            updates['ai_summary'] = None
            updates['ai_summary_date'] = None
            
        db.medical_records.update_one(
            {'_id': parse_object_id(record_id), 'user_id': user_id_filter(user_id)},
            {'$set': updates}
        )
        return cls.get_by_id(record_id, user_id)

    @classmethod
    def update_ai_summary(cls, record_id, user_id, summary_text, extracted_text=None):
        """Update AI summary and extracted text on a medical record document."""
        db = get_db()
        updates = {
            'ai_summary': summary_text,
            'ai_summary_date': utc_now(),
            'updated_at': utc_now()
        }
        if extracted_text is not None:
            updates['extracted_text'] = extracted_text
            
        db.medical_records.update_one(
            {'_id': parse_object_id(record_id), 'user_id': user_id_filter(user_id)},
            {'$set': updates}
        )
        return cls.get_by_id(record_id, user_id)

    @classmethod
    def delete(cls, record_id, user_id):
        db = get_db()
        result = db.medical_records.delete_one({
            '_id': parse_object_id(record_id),
            'user_id': user_id_filter(user_id)
        })
        return result.deleted_count > 0


class Prescription:
    """Prescription model wrapping a MongoDB 'prescriptions' document."""
    def __init__(self, doc):
        self.doc = doc or {}
        self._id = self.doc.get('_id')
        self.id = str(self._id) if self._id else None
        self.user_id = str(self.doc.get('user_id')) if self.doc.get('user_id') else None
        self.title = self.doc.get('title', '')
        self.prescription_date = self.doc.get('prescription_date') or self.doc.get('date')
        self.date = self.prescription_date
        self.clinician_name = self.doc.get('clinician_name') or self.doc.get('doctor_name', '')
        self.doctor_name = self.clinician_name
        self.medication_notes = self.doc.get('medication_notes') or self.doc.get('medications_info', '')
        self.medications_info = self.medication_notes
        self.is_archived = self.doc.get('is_archived', False)
        self.notes = self.doc.get('notes', '')
        
        file_ref = self.doc.get('file_reference') or {}
        self.stored_filename = self.doc.get('stored_filename') or file_ref.get('stored_filename', '')
        self.original_filename = self.doc.get('original_filename') or file_ref.get('original_filename', '')
        self.file_size = self.doc.get('file_size') or file_ref.get('file_size', 0)
        self.file_mime = self.doc.get('file_mime') or file_ref.get('mime_type', 'application/octet-stream')
        self.file_reference = file_ref or {
            'stored_filename': self.stored_filename,
            'original_filename': self.original_filename,
            'file_size': self.file_size,
            'mime_type': self.file_mime
        }
        
        self.created_at = self.doc.get('created_at')
        self.updated_at = self.doc.get('updated_at')

    @classmethod
    def create(cls, user_id, title, date_val, doctor_name=None, medications_info=None, file_info=None, notes=None):
        db = get_db()
        now = utc_now()
        file_info = file_info or {}
        
        doc = {
            'user_id': parse_object_id(user_id),
            'title': title.strip(),
            'prescription_date': date_val,
            'date': date_val,
            'clinician_name': doctor_name.strip() if doctor_name else None,
            'doctor_name': doctor_name.strip() if doctor_name else None,
            'medication_notes': medications_info.strip() if medications_info else None,
            'medications_info': medications_info.strip() if medications_info else None,
            'is_archived': False,
            'notes': notes.strip() if notes else None,
            'stored_filename': file_info.get('stored_filename', ''),
            'original_filename': file_info.get('original_filename', ''),
            'file_size': file_info.get('file_size', 0),
            'file_mime': file_info.get('mime_type', 'application/octet-stream'),
            'file_reference': {
                'stored_filename': file_info.get('stored_filename', ''),
                'original_filename': file_info.get('original_filename', ''),
                'file_size': file_info.get('file_size', 0),
                'mime_type': file_info.get('mime_type', 'application/octet-stream')
            } if file_info.get('stored_filename') else None,
            'created_at': now,
            'updated_at': now
        }
        
        res = db.prescriptions.insert_one(doc)
        doc['_id'] = res.inserted_id
        return cls(doc)

    @classmethod
    def get_by_id(cls, rx_id, user_id=None):
        if not rx_id:
            return None
        db = get_db()
        try:
            query = {'_id': parse_object_id(rx_id)}
            if user_id:
                query['user_id'] = user_id_filter(user_id)
            doc = db.prescriptions.find_one(query)
            return cls(doc) if doc else None
        except Exception:
            return None

    @classmethod
    def find_by_user(cls, user_id, is_archived=False, search=None):
        db = get_db()
        query = {'user_id': user_id_filter(user_id), 'is_archived': bool(is_archived)}
        
        if search:
            rx = re.compile(re.escape(search), re.IGNORECASE)
            query['$or'] = [
                {'title': rx},
                {'clinician_name': rx},
                {'doctor_name': rx},
                {'medication_notes': rx},
                {'medications_info': rx},
                {'notes': rx}
            ]
            
        cursor = db.prescriptions.find(query).sort('prescription_date', -1)
        return [cls(d) for d in cursor]

    @classmethod
    def toggle_archive(cls, rx_id, user_id):
        db = get_db()
        rx = cls.get_by_id(rx_id, user_id)
        if not rx:
            return None
        new_status = not rx.is_archived
        db.prescriptions.update_one(
            {'_id': parse_object_id(rx_id), 'user_id': user_id_filter(user_id)},
            {'$set': {'is_archived': new_status, 'updated_at': utc_now()}}
        )
        rx.is_archived = new_status
        return rx

    @classmethod
    def update(cls, rx_id, user_id, title=None, date_val=None, doctor_name=None, 
               medications_info=None, notes=None, file_info=None):
        db = get_db()
        updates = {'updated_at': utc_now()}
        
        if title is not None:
            updates['title'] = title.strip()
        if date_val is not None:
            updates['prescription_date'] = date_val
            updates['date'] = date_val
        if doctor_name is not None:
            val = doctor_name.strip() if doctor_name else None
            updates['clinician_name'] = val
            updates['doctor_name'] = val
        if medications_info is not None:
            val = medications_info.strip() if medications_info else None
            updates['medication_notes'] = val
            updates['medications_info'] = val
        if notes is not None:
            updates['notes'] = notes.strip() if notes else None
            
        if file_info:
            updates['stored_filename'] = file_info.get('stored_filename', '')
            updates['original_filename'] = file_info.get('original_filename', '')
            updates['file_size'] = file_info.get('file_size', 0)
            updates['file_mime'] = file_info.get('mime_type', 'application/octet-stream')
            updates['file_reference'] = {
                'stored_filename': file_info.get('stored_filename', ''),
                'original_filename': file_info.get('original_filename', ''),
                'file_size': file_info.get('file_size', 0),
                'mime_type': file_info.get('mime_type', 'application/octet-stream')
            }
            
        db.prescriptions.update_one(
            {'_id': parse_object_id(rx_id), 'user_id': user_id_filter(user_id)},
            {'$set': updates}
        )
        return cls.get_by_id(rx_id, user_id)

    @classmethod
    def delete(cls, rx_id, user_id):
        db = get_db()
        result = db.prescriptions.delete_one({
            '_id': parse_object_id(rx_id),
            'user_id': user_id_filter(user_id)
        })
        return result.deleted_count > 0


class Appointment:
    """Appointment model wrapping a MongoDB 'appointments' document."""
    def __init__(self, doc):
        self.doc = doc or {}
        self._id = self.doc.get('_id')
        self.id = str(self._id) if self._id else None
        self.user_id = str(self.doc.get('user_id')) if self.doc.get('user_id') else None
        self.clinician_or_hospital = self.doc.get('clinician_or_hospital') or self.doc.get('doctor_hospital_name', '')
        self.doctor_hospital_name = self.clinician_or_hospital
        self.appointment_date = self.doc.get('appointment_date')
        self.appointment_time = self.doc.get('appointment_time', '')
        self.appointment_datetime = self.doc.get('appointment_datetime')
        self.location = self.doc.get('location', '')
        self.purpose = self.doc.get('purpose', '')
        self.status = self.doc.get('status', 'Upcoming')
        self.notes = self.doc.get('notes', '')
        self.created_at = self.doc.get('created_at')
        self.updated_at = self.doc.get('updated_at')

    @classmethod
    def create(cls, user_id, doctor_hospital_name, appointment_date, appointment_time, 
               location, purpose, status='Upcoming', notes=None):
        db = get_db()
        now = utc_now()
        
        apt_datetime = None
        try:
            if isinstance(appointment_date, (datetime, date)):
                d_str = appointment_date.strftime('%Y-%m-%d')
            else:
                d_str = str(appointment_date)
            apt_datetime = datetime.strptime(f"{d_str} {appointment_time}", "%Y-%m-%d %I:%M %p")
        except Exception:
            try:
                apt_datetime = datetime.strptime(f"{d_str} {appointment_time}", "%Y-%m-%d %H:%M")
            except Exception:
                pass
                
        doc = {
            'user_id': parse_object_id(user_id),
            'clinician_or_hospital': doctor_hospital_name.strip(),
            'doctor_hospital_name': doctor_hospital_name.strip(),
            'appointment_date': appointment_date,
            'appointment_time': appointment_time.strip(),
            'appointment_datetime': apt_datetime,
            'location': location.strip(),
            'purpose': purpose.strip(),
            'status': status.strip() if status else 'Upcoming',
            'notes': notes.strip() if notes else None,
            'created_at': now,
            'updated_at': now
        }
        
        res = db.appointments.insert_one(doc)
        doc['_id'] = res.inserted_id
        return cls(doc)

    @classmethod
    def get_by_id(cls, apt_id, user_id=None):
        if not apt_id:
            return None
        db = get_db()
        try:
            query = {'_id': parse_object_id(apt_id)}
            if user_id:
                query['user_id'] = user_id_filter(user_id)
            doc = db.appointments.find_one(query)
            return cls(doc) if doc else None
        except Exception:
            return None

    @classmethod
    def find_by_user(cls, user_id, status_filter=None, search=None):
        db = get_db()
        query = {'user_id': user_id_filter(user_id)}
        today_str = date.today().isoformat()
        
        if status_filter == 'upcoming':
            query['status'] = 'Upcoming'
            query['appointment_date'] = {'$gte': today_str}
        elif status_filter == 'completed':
            query['status'] = 'Completed'
        elif status_filter == 'cancelled':
            query['status'] = 'Cancelled'
        elif status_filter == 'past':
            query['$or'] = [
                {'appointment_date': {'$lt': today_str}},
                {'status': 'Completed'}
            ]
            
        if search:
            rx = re.compile(re.escape(search), re.IGNORECASE)
            query['$or'] = [
                {'clinician_or_hospital': rx},
                {'doctor_hospital_name': rx},
                {'location': rx},
                {'purpose': rx},
                {'notes': rx}
            ]
            
        cursor = db.appointments.find(query).sort([('appointment_date', 1), ('appointment_time', 1)])
        return [cls(d) for d in cursor]

    @classmethod
    def update(cls, apt_id, user_id, doctor_hospital_name=None, appointment_date=None, 
               appointment_time=None, location=None, purpose=None, status=None, notes=None):
        db = get_db()
        updates = {'updated_at': utc_now()}
        
        if doctor_hospital_name is not None:
            updates['clinician_or_hospital'] = doctor_hospital_name.strip()
            updates['doctor_hospital_name'] = doctor_hospital_name.strip()
        if appointment_date is not None:
            updates['appointment_date'] = appointment_date
        if appointment_time is not None:
            updates['appointment_time'] = appointment_time.strip()
        if location is not None:
            updates['location'] = location.strip()
        if purpose is not None:
            updates['purpose'] = purpose.strip()
        if status is not None:
            updates['status'] = status.strip()
        if notes is not None:
            updates['notes'] = notes.strip() if notes else None
            
        db.appointments.update_one(
            {'_id': parse_object_id(apt_id), 'user_id': user_id_filter(user_id)},
            {'$set': updates}
        )
        return cls.get_by_id(apt_id, user_id)

    @classmethod
    def update_status(cls, apt_id, user_id, new_status):
        db = get_db()
        db.appointments.update_one(
            {'_id': parse_object_id(apt_id), 'user_id': user_id_filter(user_id)},
            {'$set': {'status': new_status, 'updated_at': utc_now()}}
        )

    @classmethod
    def delete(cls, apt_id, user_id):
        db = get_db()
        result = db.appointments.delete_one({
            '_id': parse_object_id(apt_id),
            'user_id': user_id_filter(user_id)
        })
        return result.deleted_count > 0


class ActivityLog:
    """Activity log audit trail model wrapping a MongoDB 'activity_logs' document."""
    def __init__(self, doc):
        self.doc = doc or {}
        self._id = self.doc.get('_id')
        self.id = str(self._id) if self._id else None
        self.user_id = str(self.doc.get('user_id')) if self.doc.get('user_id') else None
        self.action = self.doc.get('action', '')
        self.details = self.doc.get('details', '')
        self.ip_address = self.doc.get('ip_address')
        self.created_at = self.doc.get('created_at')

    @classmethod
    def log(cls, user_id, action, details=None, ip_address=None):
        try:
            db = get_db()
            doc = {
                'user_id': parse_object_id(user_id),
                'action': action,
                'details': details,
                'ip_address': ip_address,
                'created_at': utc_now()
            }
            db.activity_logs.insert_one(doc)
        except Exception:
            pass

    @classmethod
    def get_recent(cls, user_id, limit=6):
        try:
            db = get_db()
            cursor = db.activity_logs.find({'user_id': user_id_filter(user_id)})\
                                     .sort('created_at', -1)\
                                     .limit(limit)
            return [cls(d) for d in cursor]
        except Exception:
            return []


class ChatSession:
    """AI Chat Session model for persistent patient medical Q&A."""
    def __init__(self, doc):
        self.doc = doc or {}
        self._id = self.doc.get('_id')
        self.id = str(self._id) if self._id else None
        self.user_id = str(self.doc.get('user_id')) if self.doc.get('user_id') else None
        self.title = self.doc.get('title', 'Medical Records Q&A')
        self.created_at = self.doc.get('created_at')
        self.updated_at = self.doc.get('updated_at')

    @classmethod
    def create(cls, user_id, title='Medical Records Q&A'):
        db = get_db()
        now = utc_now()
        doc = {
            'user_id': parse_object_id(user_id),
            'title': title.strip(),
            'created_at': now,
            'updated_at': now
        }
        res = db.chat_sessions.insert_one(doc)
        doc['_id'] = res.inserted_id
        return cls(doc)

    @classmethod
    def get_by_id(cls, session_id, user_id=None):
        if not session_id:
            return None
        db = get_db()
        try:
            query = {'_id': parse_object_id(session_id)}
            if user_id:
                query['user_id'] = user_id_filter(user_id)
            doc = db.chat_sessions.find_one(query)
            return cls(doc) if doc else None
        except Exception:
            return None

    @classmethod
    def get_user_sessions(cls, user_id):
        db = get_db()
        cursor = db.chat_sessions.find({'user_id': user_id_filter(user_id)}).sort('updated_at', -1)
        return [cls(d) for d in cursor]

    @classmethod
    def delete(cls, session_id, user_id):
        db = get_db()
        db.chat_messages.delete_many({
            'session_id': parse_object_id(session_id),
            'user_id': user_id_filter(user_id)
        })
        res = db.chat_sessions.delete_one({
            '_id': parse_object_id(session_id),
            'user_id': user_id_filter(user_id)
        })
        return res.deleted_count > 0


class ChatMessage:
    """Individual message in an AI medical chat session with source citations."""
    def __init__(self, doc):
        self.doc = doc or {}
        self._id = self.doc.get('_id')
        self.id = str(self._id) if self._id else None
        self.session_id = str(self.doc.get('session_id')) if self.doc.get('session_id') else None
        self.user_id = str(self.doc.get('user_id')) if self.doc.get('user_id') else None
        self.sender = self.doc.get('sender', 'user')  # 'user' or 'assistant'
        self.content = self.doc.get('content', '')
        self.citations = self.doc.get('citations') or []
        self.created_at = self.doc.get('created_at')

    @classmethod
    def create(cls, session_id, user_id, sender, content, citations=None):
        db = get_db()
        now = utc_now()
        doc = {
            'session_id': parse_object_id(session_id),
            'user_id': parse_object_id(user_id),
            'sender': sender,
            'content': content,
            'citations': citations or [],
            'created_at': now
        }
        res = db.chat_messages.insert_one(doc)
        doc['_id'] = res.inserted_id
        
        # Touch parent session updated_at
        db.chat_sessions.update_one(
            {'_id': parse_object_id(session_id)},
            {'$set': {'updated_at': now}}
        )
        return cls(doc)

    @classmethod
    def get_session_messages(cls, session_id, user_id):
        db = get_db()
        cursor = db.chat_messages.find({
            'session_id': parse_object_id(session_id),
            'user_id': user_id_filter(user_id)
        }).sort('created_at', 1)
        return [cls(d) for d in cursor]


class Notification:
    """In-app notification and delivery tracker model."""
    def __init__(self, doc):
        self.doc = doc or {}
        self._id = self.doc.get('_id')
        self.id = str(self._id) if self._id else None
        self.user_id = str(self.doc.get('user_id')) if self.doc.get('user_id') else None
        self.title = self.doc.get('title', '')
        self.message = self.doc.get('message', '')
        self.type = self.doc.get('type', 'general')  # appointment_reminder, ai_summary, voice_call, security
        self.link = self.doc.get('link')
        self.is_read = self.doc.get('is_read', False)
        self.created_at = self.doc.get('created_at')

    @classmethod
    def create(cls, user_id, title, message, notif_type='general', link=None):
        db = get_db()
        now = utc_now()
        doc = {
            'user_id': parse_object_id(user_id),
            'title': title.strip(),
            'message': message.strip(),
            'type': notif_type,
            'link': link,
            'is_read': False,
            'created_at': now
        }
        res = db.notifications.insert_one(doc)
        doc['_id'] = res.inserted_id
        return cls(doc)

    @classmethod
    def get_user_notifications(cls, user_id, limit=30, unread_only=False):
        db = get_db()
        query = {'user_id': user_id_filter(user_id)}
        if unread_only:
            query['is_read'] = False
        cursor = db.notifications.find(query).sort('created_at', -1).limit(limit)
        return [cls(d) for d in cursor]

    @classmethod
    def get_unread_count(cls, user_id):
        db = get_db()
        return db.notifications.count_documents({
            'user_id': user_id_filter(user_id),
            'is_read': False
        })

    @classmethod
    def mark_as_read(cls, notif_id, user_id):
        db = get_db()
        db.notifications.update_one(
            {'_id': parse_object_id(notif_id), 'user_id': user_id_filter(user_id)},
            {'$set': {'is_read': True}}
        )

    @classmethod
    def mark_all_read(cls, user_id):
        db = get_db()
        db.notifications.update_many(
            {'user_id': user_id_filter(user_id), 'is_read': False},
            {'$set': {'is_read': True}}
        )

    @classmethod
    def delete(cls, notif_id, user_id):
        db = get_db()
        res = db.notifications.delete_one({
            '_id': parse_object_id(notif_id),
            'user_id': user_id_filter(user_id)
        })
        return res.deleted_count > 0


class VoiceCallLog:
    """Voice Call Reminder Log tracking Twilio telephony sessions and patient IVR responses."""
    def __init__(self, doc):
        self.doc = doc or {}
        self._id = self.doc.get('_id')
        self.id = str(self._id) if self._id else None
        self.user_id = str(self.doc.get('user_id')) if self.doc.get('user_id') else None
        self.appointment_id = str(self.doc.get('appointment_id')) if self.doc.get('appointment_id') else None
        self.call_sid = self.doc.get('call_sid', '')
        self.to_phone = self.doc.get('to_phone', '')
        self.status = self.doc.get('status', 'Initiated')
        self.user_response = self.doc.get('user_response')  # 'Confirmed Attendance', 'Reschedule Requested', 'Opted Out', etc.
        self.speech_transcript = self.doc.get('speech_transcript')
        self.digits_pressed = self.doc.get('digits_pressed')
        self.error_message = self.doc.get('error_message')
        self.created_at = self.doc.get('created_at')
        self.updated_at = self.doc.get('updated_at')

    @classmethod
    def create(cls, user_id, appointment_id, to_phone, call_sid=None, status='Initiated'):
        db = get_db()
        now = utc_now()
        doc = {
            'user_id': parse_object_id(user_id),
            'appointment_id': parse_object_id(appointment_id),
            'to_phone': to_phone,
            'call_sid': call_sid or f"mock_call_{secrets.token_hex(8)}",
            'status': status,
            'user_response': None,
            'speech_transcript': None,
            'digits_pressed': None,
            'error_message': None,
            'created_at': now,
            'updated_at': now
        }
        res = db.voice_call_logs.insert_one(doc)
        doc['_id'] = res.inserted_id
        return cls(doc)

    @classmethod
    def get_by_id(cls, log_id, user_id=None):
        if not log_id:
            return None
        db = get_db()
        try:
            query = {'_id': parse_object_id(log_id)}
            if user_id:
                query['user_id'] = user_id_filter(user_id)
            doc = db.voice_call_logs.find_one(query)
            return cls(doc) if doc else None
        except Exception:
            return None

    @classmethod
    def get_by_call_sid(cls, call_sid):
        if not call_sid:
            return None
        db = get_db()
        doc = db.voice_call_logs.find_one({'call_sid': call_sid})
        return cls(doc) if doc else None

    @classmethod
    def update_response(cls, call_sid, user_response, digits_pressed=None, transcript=None, status=None):
        db = get_db()
        updates = {'updated_at': utc_now()}
        if user_response:
            updates['user_response'] = user_response
        if digits_pressed:
            updates['digits_pressed'] = digits_pressed
        if transcript:
            updates['speech_transcript'] = transcript
        if status:
            updates['status'] = status
            
        db.voice_call_logs.update_one({'call_sid': call_sid}, {'$set': updates})

    @classmethod
    def update_status(cls, call_sid, status, error_message=None):
        db = get_db()
        updates = {'status': status, 'updated_at': utc_now()}
        if error_message:
            updates['error_message'] = error_message
        db.voice_call_logs.update_one({'call_sid': call_sid}, {'$set': updates})

    @classmethod
    def get_user_call_logs(cls, user_id, limit=20):
        db = get_db()
        cursor = db.voice_call_logs.find({'user_id': user_id_filter(user_id)})\
                                   .sort('created_at', -1)\
                                   .limit(limit)
        return [cls(d) for d in cursor]
