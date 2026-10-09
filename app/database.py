import os
import pymongo
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

_mongo_client = None
_db = None

def init_db(app):
    """
    Initialize MongoDB database connection and ensure indexes.
    Connects to live MongoDB URI if available; otherwise falls back to mongomock for testing/offline development.
    """
    global _mongo_client, _db
    
    uri = app.config.get('MONGODB_URI', 'mongodb://localhost:27017/medivault_db')
    db_name = app.config.get('MONGODB_DATABASE', 'medivault_db')
    
    # Try connecting to live MongoDB cluster or server
    use_mock = False
    try:
        if app.config.get('TESTING') or uri.startswith('mongomock://'):
            import mongomock
            _mongo_client = mongomock.MongoClient()
            _db = _mongo_client[db_name]
        else:
            client = MongoClient(uri, serverSelectionTimeoutMS=2000)
            # Force a ping check
            client.admin.command('ping')
            _mongo_client = client
            _db = _mongo_client[db_name]
    except Exception as e:
        # Fallback gracefully to mongomock so app runs locally without MongoDB server requirement
        import mongomock
        _mongo_client = mongomock.MongoClient()
        _db = _mongo_client[db_name]
        use_mock = True

    # Setup collection indexes
    setup_indexes(_db)
    return _db

def get_db():
    """Retrieve the current MongoDB database instance."""
    global _db
    if _db is None:
        import mongomock
        _db = mongomock.MongoClient()['medivault_db']
        setup_indexes(_db)
    return _db

def setup_indexes(db):
    """
    Create MongoDB indexes for:
    - Unique user emails
    - Ownership user_id queries
    - Search date ranges and categories
    - AI Chat sessions and messages
    - In-app and scheduled notifications
    - Telephony voice call logs
    """
    try:
        # 1. Users collection
        db.users.create_index([('email', ASCENDING)], unique=True)
        db.users.create_index([('phone_number', ASCENDING)], sparse=True)
        db.users.create_index([('reset_token', ASCENDING)])
        
        # 1b. OTP and Registration verification collections
        db.pending_registrations.create_index([('session_token', ASCENDING)], unique=True)
        db.pending_registrations.create_index([('expires_at', ASCENDING)])
        db.otp_verifications.create_index([('session_token', ASCENDING)], unique=True)
        db.otp_verifications.create_index([('expires_at', ASCENDING)])
        
        # 2. Medical Records collection
        db.medical_records.create_index([('user_id', ASCENDING), ('report_date', DESCENDING)])
        db.medical_records.create_index([('user_id', ASCENDING), ('category', ASCENDING)])
        db.medical_records.create_index([('user_id', ASCENDING), ('title', ASCENDING)])
        
        # 3. Prescriptions collection
        db.prescriptions.create_index([('user_id', ASCENDING), ('prescription_date', DESCENDING)])
        db.prescriptions.create_index([('user_id', ASCENDING), ('is_archived', ASCENDING)])
        
        # 4. Appointments collection
        db.appointments.create_index([('user_id', ASCENDING), ('appointment_date', ASCENDING)])
        db.appointments.create_index([('user_id', ASCENDING), ('status', ASCENDING)])
        
        # 5. Activity Logs collection
        db.activity_logs.create_index([('user_id', ASCENDING), ('created_at', DESCENDING)])
        
        # 6. AI Chat Sessions & Messages collections
        db.chat_sessions.create_index([('user_id', ASCENDING), ('updated_at', DESCENDING)])
        db.chat_messages.create_index([('session_id', ASCENDING), ('created_at', ASCENDING)])
        db.chat_messages.create_index([('user_id', ASCENDING), ('created_at', DESCENDING)])
        
        # 7. Notifications collection
        db.notifications.create_index([('user_id', ASCENDING), ('is_read', ASCENDING), ('created_at', DESCENDING)])
        
        # 8. Telephony & Voice Call Logs collection
        db.voice_call_logs.create_index([('user_id', ASCENDING), ('created_at', DESCENDING)])
        db.voice_call_logs.create_index([('appointment_id', ASCENDING)])
        db.voice_call_logs.create_index([('call_sid', ASCENDING)])
        
        # 9. Idempotent Reminder Logs (Prevents duplicate notifications)
        db.reminder_logs.create_index([
            ('appointment_id', ASCENDING), 
            ('reminder_type', ASCENDING), 
            ('lead_time', ASCENDING)
        ], unique=True)
        
    except Exception:
        pass
