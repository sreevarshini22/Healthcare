from flask import Blueprint, render_template, request, Response, flash, redirect, url_for, abort, jsonify
from flask_login import login_required, current_user
from app.models import Appointment, VoiceCallLog, User
from app.services.voice_service import (
    initiate_voice_reminder_call, 
    generate_twiml_reminder_xml, 
    generate_twiml_response_xml
)
from app.utils.helpers import log_activity

voice_bp = Blueprint('voice', __name__)

# --- Patient Dashboard & Control Routes ---

@voice_bp.route('/voice/logs')
@login_required
def logs():
    """View history of automated appointment voice calls and IVR outcomes."""
    call_logs = VoiceCallLog.get_user_call_logs(current_user.id, limit=30)
    upcoming_appointments = Appointment.find_by_user(current_user.id, status_filter='upcoming')
    
    return render_template(
        'voice/logs.html',
        call_logs=call_logs,
        upcoming_appointments=upcoming_appointments
    )


@voice_bp.route('/voice/trigger/<appointment_id>', methods=['POST'])
@login_required
def trigger_call(appointment_id):
    """Manually initiate or test an automated voice reminder call for an appointment."""
    appointment = Appointment.get_by_id(appointment_id, current_user.id)
    if not appointment:
        abort(404)
        
    if str(appointment.user_id) != str(current_user.id):
        abort(403)
        
    success, msg = initiate_voice_reminder_call(appointment.id, current_user.id)
    if success:
        log_activity(current_user.id, "Voice Reminder Initiated", f"For visit with {appointment.doctor_hospital_name}")
        flash(f"Automated voice call reminder initiated: {msg}", "success")
    else:
        flash(f"Voice call could not be started: {msg}", "warning")
        
    return redirect(url_for('voice.logs'))


# --- Twilio Telephony Webhook Endpoints ---

@voice_bp.route('/api/voice/twiml/<log_id>', methods=['GET', 'POST'])
def twiml_reminder(log_id):
    """
    Twilio Webhook: Returns TwiML XML instructions to speak the appointment details
    and gather keypad / voice response from the patient.
    """
    call_log = VoiceCallLog.get_by_id(log_id)
    if not call_log:
        return Response("<Response><Say>Call session expired. Goodbye.</Say></Response>", mimetype='application/xml')
        
    appointment = Appointment.get_by_id(call_log.appointment_id)
    user = User.get_by_id(call_log.user_id)
    
    if not appointment or not user:
        return Response("<Response><Say>Appointment record not found. Goodbye.</Say></Response>", mimetype='application/xml')
        
    twiml_xml = generate_twiml_reminder_xml(appointment, user, call_log.id)
    return Response(twiml_xml, mimetype='application/xml')


@voice_bp.route('/api/voice/gather/<log_id>', methods=['POST'])
def gather_response(log_id):
    """
    Twilio Webhook: Captures DTMF keypad digits or speech recognition transcript from patient.
    """
    call_log = VoiceCallLog.get_by_id(log_id)
    if not call_log:
        return Response("<Response><Say>Session expired. Goodbye.</Say></Response>", mimetype='application/xml')
        
    appointment = Appointment.get_by_id(call_log.appointment_id)
    user = User.get_by_id(call_log.user_id)
    
    digits = request.form.get('Digits')
    speech_result = request.form.get('SpeechResult')
    
    twiml_xml, outcome = generate_twiml_response_xml(
        digits=digits,
        speech_text=speech_result,
        appointment=appointment,
        user=user,
        call_log=call_log
    )
    
    return Response(twiml_xml, mimetype='application/xml')


@voice_bp.route('/api/voice/status/<log_id>', methods=['POST'])
def status_callback(log_id):
    """
    Twilio Webhook: Receives real-time call lifecycle updates (ringing, answered, completed, failed).
    """
    call_status = request.form.get('CallStatus', 'completed')
    call_sid = request.form.get('CallSid')
    error_msg = request.form.get('ErrorMessage')
    
    if call_sid:
        VoiceCallLog.update_status(call_sid, call_status.capitalize(), error_message=error_msg)
        
    return ('', 204)
