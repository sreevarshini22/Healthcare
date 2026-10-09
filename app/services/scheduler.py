from datetime import datetime, date, timedelta
import threading
import time
from flask import current_app
from app.models import Appointment, User, utc_now
from app.services.notification_service import dispatch_appointment_reminder
from app.services.voice_service import initiate_voice_reminder_call
from app.database import get_db

_scheduler_running = False
_scheduler_thread = None

def check_and_send_due_reminders(app):
    """
    Background job scanning upcoming appointments and triggering due notifications.
    Executes within the Flask application context.
    """
    with app.app_context():
        try:
            db = get_db()
            today = date.today()
            today_str = today.isoformat()
            tomorrow_str = (today + timedelta(days=1)).isoformat()
            
            # Find upcoming appointments within the next 48 hours
            cursor = db.appointments.find({
                'status': 'Upcoming',
                'appointment_date': {'$gte': today_str, '$lte': (today + timedelta(days=2)).isoformat()}
            })
            
            for doc in cursor:
                apt = Appointment(doc)
                user = User.get_by_id(apt.user_id)
                if not user:
                    continue
                    
                apt_date_str = str(apt.appointment_date)
                
                # Check lead time: 24h before
                if apt_date_str == tomorrow_str:
                    dispatch_appointment_reminder(apt, user, lead_time_label="24h")
                    # If voice reminders enabled, initiate voice call
                    if user.voice_opt_in or (user.reminder_preferences and user.reminder_preferences.get('voice')):
                        # Check if voice call already initiated for this appointment
                        existing_call = db.voice_call_logs.find_one({'appointment_id': apt._id})
                        if not existing_call:
                            initiate_voice_reminder_call(apt.id, user.id)
                            
                # Check lead time: Same day (today)
                elif apt_date_str == today_str:
                    dispatch_appointment_reminder(apt, user, lead_time_label="same_day")
                    
        except Exception:
            pass


def _background_worker(app, interval_seconds=300):
    """Background worker loop executing the reminder check at regular intervals."""
    global _scheduler_running
    while _scheduler_running:
        check_and_send_due_reminders(app)
        # Sleep in short increments to allow graceful shutdown
        for _ in range(interval_seconds):
            if not _scheduler_running:
                break
            time.sleep(1)


def init_scheduler(app):
    """
    Initializes and starts the background reminder scheduler thread.
    """
    global _scheduler_running, _scheduler_thread
    
    if app.config.get('TESTING'):
        # Do not start background threads during automated test runs
        return
        
    if not app.config.get('SCHEDULER_ENABLED', True):
        return
        
    if _scheduler_thread is not None and _scheduler_thread.is_alive():
        return
        
    _scheduler_running = True
    interval = app.config.get('SCHEDULER_INTERVAL_MINUTES', 5) * 60
    _scheduler_thread = threading.Thread(
        target=_background_worker,
        args=(app, interval),
        daemon=True,
        name="MediVault-ReminderScheduler"
    )
    _scheduler_thread.start()


def stop_scheduler():
    """Gracefully stops the background scheduler thread."""
    global _scheduler_running
    _scheduler_running = False
