import pytest
from datetime import date, timedelta
from app.models import Notification, Appointment, User
from app.services.notification_service import (
    send_in_app_notification, 
    dispatch_appointment_reminder
)

def test_in_app_notifications_lifecycle(auth_client_a, app, user_a):
    """Test creating, fetching unread count, marking as read, and deleting notifications."""
    with app.app_context():
        send_in_app_notification(
            user_id=user_a,
            title="Vaccination Follow-up",
            message="Your annual flu vaccination is due this month.",
            notif_type="general"
        )
        send_in_app_notification(
            user_id=user_a,
            title="Lab Results Ready",
            message="Your CMP blood panel has been uploaded.",
            notif_type="ai_summary"
        )

    # 1. Check unread count
    resp = auth_client_a.get('/notifications/unread-count')
    assert resp.status_code == 200
    assert resp.get_json()['unread_count'] == 2

    # 2. View notification index page
    index_resp = auth_client_a.get('/notifications/')
    assert index_resp.status_code == 200
    assert b"Vaccination Follow-up" in index_resp.data
    assert b"Lab Results Ready" in index_resp.data

    # 3. Mark all as read
    read_all_resp = auth_client_a.post('/notifications/read-all', json={})
    assert read_all_resp.status_code == 200

    with app.app_context():
        assert Notification.get_unread_count(user_a) == 0

def test_reminder_dispatch_and_deduplication(app, user_a):
    """Test appointment reminder dispatching and duplicate notification prevention."""
    with app.app_context():
        user = User.get_by_id(user_a)
        future_date = (date.today() + timedelta(days=1)).isoformat()
        apt = Appointment.create(
            user_id=user_a,
            doctor_hospital_name="Dr. Eleanor Vance, MD",
            appointment_date=future_date,
            appointment_time="10:00 AM",
            location="Heart Clinic",
            purpose="Cardiovascular check"
        )

        # 1. First dispatch -> Should succeed
        success, msg = dispatch_appointment_reminder(apt, user, lead_time_label="24h")
        assert success is True
        assert Notification.get_unread_count(user_a) >= 1

        # 2. Second dispatch with same lead time -> Should be ignored / deduplicated
        success2, msg2 = dispatch_appointment_reminder(apt, user, lead_time_label="24h")
        assert success2 is False
        assert "already sent" in msg2.lower()

def test_notification_preference_updates(auth_client_a, app, user_a):
    """Test updating multi-channel notification preferences."""
    response = auth_client_a.post('/notifications/preferences', data={
        'reminder_email': '1',
        'reminder_sms': '1',
        'reminder_voice': '1',
        'voice_opt_in': '1',
        'lead_times': ['24h', '2h', '1w']
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b"preferences saved successfully" in response.data

    with app.app_context():
        user = User.get_by_id(user_a)
        assert user.reminder_preferences['email'] is True
        assert user.reminder_preferences['sms'] is True
        assert user.reminder_preferences['voice'] is True
        assert user.voice_opt_in is True
        assert '1w' in user.reminder_preferences['lead_times']
