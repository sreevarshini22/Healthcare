from datetime import datetime, date
from flask import request, url_for
from app.models import MedicalRecord, Prescription, Appointment, ActivityLog
from app.database import get_db

def safe_url_for(endpoint, **values):
    """Safely build URLs even when outside an active HTTP request context."""
    try:
        return url_for(endpoint, **values)
    except Exception:
        # Fallback to standard relative route path
        clean_ep = endpoint.replace('.', '/')
        if clean_ep == 'appointments/index':
            return '/appointments/'
        elif clean_ep == 'records/index':
            return '/records/'
        elif clean_ep == 'prescriptions/index':
            return '/prescriptions/'
        elif clean_ep == 'ai/chat':
            return '/ai/chat'
        return f"/{clean_ep}"

DOCUMENT_CATEGORIES = [
    "Laboratory & Blood Tests",
    "Prescriptions & Medications",
    "Imaging & Radiology (X-Ray/MRI/CT)",
    "Discharge Summaries & Hospital Records",
    "Vaccination & Immunization",
    "Cardiology & ECG Reports",
    "General Health Checkup",
    "Insurance & Claim Documents",
    "Other Medical Records"
]

def format_bytes(size_bytes):
    """Format bytes into readable string (KB, MB)."""
    if size_bytes is None:
        return "0 KB"
    try:
        size = float(size_bytes)
    except (ValueError, TypeError):
        return "0 KB"
        
    if size < 1024:
        return f"{int(size)} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / (1024 * 1024):.2f} MB"

def log_activity(user_id, action, details=None):
    """Record an audit trail event for the user."""
    ip = request.remote_addr if request else None
    ActivityLog.log(user_id=user_id, action=action, details=details, ip_address=ip)

def get_dashboard_stats(user_id):
    """Compute summary statistics for user dashboard from MongoDB collections."""
    db = get_db()
    from app.models import user_id_filter
    u_filter = user_id_filter(user_id)
    
    total_records = db.medical_records.count_documents({'user_id': u_filter})
    total_prescriptions = db.prescriptions.count_documents({'user_id': u_filter})
    active_prescriptions = db.prescriptions.count_documents({'user_id': u_filter, 'is_archived': False})
    
    today_str = date.today().isoformat()
    upcoming_appointments_count = db.appointments.count_documents({
        'user_id': u_filter,
        'appointment_date': {'$gte': today_str},
        'status': 'Upcoming'
    })
    
    total_appointments = db.appointments.count_documents({'user_id': u_filter})
    
    # Recent items
    recent_records_cur = db.medical_records.find({'user_id': u_filter})\
        .sort([('report_date', -1), ('created_at', -1)]).limit(5)
    recent_records = [MedicalRecord(d) for d in recent_records_cur]
    
    upcoming_cur = db.appointments.find({
        'user_id': u_filter,
        'appointment_date': {'$gte': today_str},
        'status': 'Upcoming'
    }).sort([('appointment_date', 1), ('appointment_time', 1)]).limit(4)
    upcoming_appointments = [Appointment(d) for d in upcoming_cur]
    
    recent_rx_cur = db.prescriptions.find({'user_id': u_filter, 'is_archived': False})\
        .sort('prescription_date', -1).limit(4)
    recent_prescriptions = [Prescription(d) for d in recent_rx_cur]
    
    recent_activity = ActivityLog.get_recent(user_id, limit=6)
    
    return {
        'total_records': total_records,
        'total_prescriptions': total_prescriptions,
        'active_prescriptions': active_prescriptions,
        'upcoming_appointments_count': upcoming_appointments_count,
        'total_appointments': total_appointments,
        'recent_records': recent_records,
        'upcoming_appointments': upcoming_appointments,
        'recent_prescriptions': recent_prescriptions,
        'recent_activity': recent_activity
    }
