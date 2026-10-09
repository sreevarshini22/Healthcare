import pytest
from datetime import date, timedelta
from app.models import Appointment, VoiceCallLog, User
from app.services.voice_service import (
    initiate_voice_reminder_call, 
    generate_twiml_reminder_xml,
    generate_twiml_response_xml
)

def test_initiate_voice_reminder_call(auth_client_a, app, user_a):
    """Test initiating an automated voice reminder call for an upcoming appointment."""
    with app.app_context():
        user = User.get_by_id(user_a)
        user.update_reminder_preferences(voice=True, voice_opt_in=True)
        
        future_date = (date.today() + timedelta(days=2)).isoformat()
        apt = Appointment.create(
            user_id=user_a,
            doctor_hospital_name="Pinehurst Dental Surgery",
            appointment_date=future_date,
            appointment_time="11:30 AM",
            location="Room 102",
            purpose="Dental checkup"
        )
        apt_id = apt.id

    # Trigger voice call via dashboard endpoint
    response = auth_client_a.post(f'/voice/trigger/{apt_id}', follow_redirects=True)
    assert response.status_code == 200
    assert b"Voice Reminder" in response.data or b"initiated" in response.data or b"queued" in response.data

    with app.app_context():
        call_logs = VoiceCallLog.get_user_call_logs(user_a)
        assert len(call_logs) >= 1
        assert call_logs[0].to_phone == "555-0100"

def test_twiml_reminder_xml_generation(app, user_a):
    """Test generating valid TwiML XML with <Gather> for speech and keypad input."""
    with app.app_context():
        user = User.get_by_id(user_a)
        apt = Appointment.create(
            user_id=user_a,
            doctor_hospital_name="Dr. Marcus Welby",
            appointment_date="2026-07-15",
            appointment_time="02:00 PM",
            location="General Hospital",
            purpose="Routine Consultation"
        )
        call_log = VoiceCallLog.create(user_id=user_a, appointment_id=apt.id, to_phone="555-0100")
        
        twiml = generate_twiml_reminder_xml(apt, user, call_log.id)
        assert "<Response>" in twiml
        assert "<Gather" in twiml
        assert "press 1 or say 'confirm'" in twiml.lower()

def test_ivr_patient_responses(app, user_a):
    """Test processing DTMF keypad and speech responses (1=Confirm, 2=Reschedule, 3=Opt out)."""
    with app.app_context():
        user = User.get_by_id(user_a)
        apt = Appointment.create(
            user_id=user_a,
            doctor_hospital_name="Boston Heart Clinic",
            appointment_date="2026-08-01",
            appointment_time="09:00 AM",
            location="Building C",
            purpose="Echocardiogram"
        )
        
        # Test 1: Confirm Attendance
        log1 = VoiceCallLog.create(user_id=user_a, appointment_id=apt.id, to_phone="555-0100")
        twiml_1, outcome_1 = generate_twiml_response_xml(
            digits="1", speech_text=None, appointment=apt, user=user, call_log=log1
        )
        assert outcome_1 == "Confirmed Attendance"
        assert "recorded that you plan to attend" in twiml_1

        # Test 2: Reschedule Requested
        log2 = VoiceCallLog.create(user_id=user_a, appointment_id=apt.id, to_phone="555-0100")
        twiml_2, outcome_2 = generate_twiml_response_xml(
            digits=None, speech_text="I need to reschedule", appointment=apt, user=user, call_log=log2
        )
        assert outcome_2 == "Reschedule Requested"
        assert "request to reschedule" in twiml_2

        # Test 3: Opt Out
        log3 = VoiceCallLog.create(user_id=user_a, appointment_id=apt.id, to_phone="555-0100")
        twiml_3, outcome_3 = generate_twiml_response_xml(
            digits="3", speech_text=None, appointment=apt, user=user, call_log=log3
        )
        assert outcome_3 == "Opted Out"
        assert "opted out of automated phone reminders" in twiml_3
