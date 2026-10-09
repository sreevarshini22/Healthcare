import secrets
from flask import current_app
from app.models import VoiceCallLog, Appointment, User, Notification, utc_now
from app.database import get_db
from app.utils.helpers import safe_url_for

def generate_twiml_reminder_xml(appointment, user, call_log_id):
    """
    Generates TwiML XML for Twilio Text-to-Speech voice reminder and IVR response gathering.
    """
    gather_action_url = safe_url_for('voice.gather_response', log_id=call_log_id)
    
    greeting = (
        f"Hello {user.full_name}, this is an automated health appointment reminder from MediVault. "
        f"You have a scheduled medical visit with {appointment.doctor_hospital_name} on "
        f"{appointment.appointment_date} at {appointment.appointment_time}. "
        f"Please press 1 or say 'Confirm' if you plan to attend. "
        f"Press 2 or say 'Reschedule' if you need to request rescheduling. "
        f"Or press 3 to opt out of automated phone reminders."
    )
    
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech dtmf" timeout="6" numDigits="1" action="{gather_action_url}" method="POST">
        <Say voice="Polly.Joanna-Neural" language="en-US">{greeting}</Say>
    </Gather>
    <Say voice="Polly.Joanna-Neural" language="en-US">We did not receive your input. You can manage your appointments anytime by signing into MediVault. Goodbye.</Say>
</Response>"""
    return twiml


def generate_twiml_response_xml(digits, speech_text, appointment, user, call_log):
    """
    Generates TwiML response acknowledging the patient's keypad or voice choice.
    """
    digits = (digits or "").strip()
    speech = (speech_text or "").lower().strip()
    
    if digits == "1" or "confirm" in speech or "yes" in speech:
        response_status = "Confirmed Attendance"
        say_text = (
            "Thank you! We have recorded that you plan to attend your appointment. "
            "Please remember to bring any required diagnostic reports or identification. Have a wonderful day!"
        )
    elif digits == "2" or "reschedule" in speech or "change" in speech:
        response_status = "Reschedule Requested"
        say_text = (
            "We have noted your request to reschedule. "
            "Please contact the clinic directly or update your appointment through your MediVault dashboard. Goodbye!"
        )
    elif digits == "3" or "opt out" in speech or "stop" in speech:
        response_status = "Opted Out"
        # Update user opt-out preference
        user.update_reminder_preferences(voice=False, voice_opt_in=False)
        say_text = "You have been successfully opted out of automated phone reminders. Thank you, goodbye!"
    else:
        response_status = "Unrecognized Input"
        say_text = "Thank you for using MediVault. You can view all appointment details online. Goodbye!"

    # Update voice call log in MongoDB
    VoiceCallLog.update_response(
        call_sid=call_log.call_sid,
        user_response=response_status,
        digits_pressed=digits,
        transcript=speech_text,
        status="Completed"
    )
    
    # Create an in-app audit notification of the voice call outcome
    Notification.create(
        user_id=user.id,
        title=f"Voice Reminder: {response_status}",
        message=f"Automated voice call for appointment with {appointment.doctor_hospital_name} completed with outcome: '{response_status}'.",
        notif_type='voice_call',
        link=safe_url_for('appointments.index')
    )
    
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna-Neural" language="en-US">{say_text}</Say>
</Response>"""
    return twiml, response_status


def initiate_voice_reminder_call(appointment_id, user_id):
    """
    Initiates an automated voice reminder call via Twilio Voice API.
    Works with live Twilio account or graceful simulated testing mode.
    """
    appointment = Appointment.get_by_id(appointment_id, user_id)
    user = User.get_by_id(user_id)
    
    if not appointment or not user:
        return False, "Invalid appointment or user credentials."
        
    if not user.phone_number:
        return False, "User does not have a registered phone number for voice calls."
        
    # Check if voice reminders are enabled / consent granted
    if not user.voice_opt_in and not user.reminder_preferences.get('voice'):
        return False, "User has not enabled voice reminder calls."
        
    account_sid = current_app.config.get('TWILIO_ACCOUNT_SID')
    auth_token = current_app.config.get('TWILIO_AUTH_TOKEN')
    from_number = current_app.config.get('TWILIO_PHONE_NUMBER')
    
    # Create initial VoiceCallLog in MongoDB
    call_log = VoiceCallLog.create(
        user_id=user.id,
        appointment_id=appointment.id,
        to_phone=user.phone_number,
        status='Initiated'
    )
    
    # Check if live Twilio is configured
    if account_sid and auth_token and from_number:
        try:
            from twilio.rest import Client
            client = Client(account_sid, auth_token)
            
            twiml_url = url_for('voice.twiml_reminder', log_id=call_log.id, _external=True)
            status_callback_url = url_for('voice.status_callback', log_id=call_log.id, _external=True)
            
            call = client.calls.create(
                url=twiml_url,
                to=user.phone_number,
                from_=from_number,
                status_callback=status_callback_url,
                status_callback_event=['initiated', 'ringing', 'answered', 'completed']
            )
            
            # Update with actual Call SID
            db = get_db()
            db.voice_call_logs.update_one(
                {'_id': call_log._id},
                {'$set': {'call_sid': call.sid, 'status': call.status}}
            )
            
            return True, f"Voice call initiated (SID: {call.sid})"
        except Exception as e:
            VoiceCallLog.update_status(call_log.call_sid, "Failed", error_message=str(e))
            return False, f"Twilio Voice Error: {str(e)}"
    else:
        # Development / Testing Simulation Mode
        # Update log to Ringing / Simulated
        db = get_db()
        db.voice_call_logs.update_one(
            {'_id': call_log._id},
            {'$set': {'status': 'Simulated-Success', 'notes': 'Simulated automated voice call in development environment.'}}
        )
        return True, f"Voice call queued and simulated successfully (Log ID: {call_log.id})"
