import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app
from app.models import Notification, Appointment, User, utc_now
from app.database import get_db
from app.utils.helpers import safe_url_for

def send_in_app_notification(user_id, title, message, notif_type='general', link=None):
    """Creates a persistent in-app notification in MongoDB."""
    return Notification.create(
        user_id=user_id,
        title=title,
        message=message,
        notif_type=notif_type,
        link=link
    )

def send_email_notification(to_email, subject, body_html):
    """
    Sends an email notification via configured SMTP server.
    Logs gracefully if SMTP is not configured or in testing environment.
    """
    mail_server = current_app.config.get('MAIL_SERVER')
    mail_port = current_app.config.get('MAIL_PORT', 587)
    mail_user = current_app.config.get('MAIL_USERNAME')
    mail_pass = current_app.config.get('MAIL_PASSWORD')
    default_sender = current_app.config.get('MAIL_DEFAULT_SENDER', 'notifications@medivault-health.org')
    
    if not mail_user or not mail_pass:
        # Gracefully simulated / logged in development
        return True, "Email notification queued (Development mode)."
        
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = default_sender
        msg['To'] = to_email
        msg.attach(MIMEText(body_html, 'html'))
        
        with smtplib.SMTP(mail_server, mail_port, timeout=10) as server:
            if current_app.config.get('MAIL_USE_TLS', True):
                server.starttls()
            server.login(mail_user, mail_pass)
            server.sendmail(default_sender, [to_email], msg.as_string())
            
        return True, "Email sent successfully."
    except Exception as e:
        return False, str(e)

def send_sms_notification(to_phone, message_text):
    """
    Sends an SMS notification via Twilio if configured.
    """
    account_sid = current_app.config.get('TWILIO_ACCOUNT_SID')
    auth_token = current_app.config.get('TWILIO_AUTH_TOKEN')
    from_number = current_app.config.get('TWILIO_PHONE_NUMBER')
    
    if not account_sid or not auth_token or not from_number:
        # Development mode simulation
        return True, "SMS reminder simulated (Twilio credentials not configured in .env)."
        
    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        message = client.messages.create(
            body=message_text,
            from_=from_number,
            to=to_phone
        )
        return True, message.sid
    except Exception as e:
        return False, str(e)

def dispatch_appointment_reminder(appointment, user, lead_time_label="24 hours"):
    """
    Dispatches multi-channel appointment reminder (In-App, Email, SMS)
    with strict idempotency to prevent duplicate notifications.
    """
    db = get_db()
    apt_id_str = str(appointment.id)
    reminder_key = f"{apt_id_str}_{lead_time_label}"
    
    # Check if this exact reminder was already sent
    existing_log = db.reminder_logs.find_one({
        'appointment_id': appointment._id,
        'reminder_type': 'multi_channel',
        'lead_time': lead_time_label
    })
    if existing_log:
        return False, "Reminder already sent for this lead time."
        
    title = f"Reminder: Upcoming Visit with {appointment.doctor_hospital_name}"
    message = (
        f"You have an appointment scheduled with {appointment.doctor_hospital_name} on "
        f"{appointment.appointment_date} at {appointment.appointment_time} ({appointment.location}). "
        f"Purpose: {appointment.purpose}."
    )
    
    # 1. In-app notification
    send_in_app_notification(
        user_id=user.id,
        title=title,
        message=message,
        notif_type='appointment_reminder',
        link=safe_url_for('appointments.index')
    )
    
    # 2. Email Notification if enabled
    prefs = user.reminder_preferences or {}
    if prefs.get('email', True) and user.email:
        email_html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
            <h2 style="color: #0f2942; border-bottom: 2px solid #1e6091; padding-bottom: 10px;">MediVault Appointment Reminder</h2>
            <p>Dear {user.full_name},</p>
            <p>This is a reminder that you have an upcoming clinical appointment scheduled:</p>
            <div style="background-color: #f8f9fa; padding: 15px; border-radius: 6px; margin: 15px 0;">
                <p><strong>Doctor / Facility:</strong> {appointment.doctor_hospital_name}</p>
                <p><strong>Date & Time:</strong> {appointment.appointment_date} at {appointment.appointment_time}</p>
                <p><strong>Location:</strong> {appointment.location}</p>
                <p><strong>Purpose:</strong> {appointment.purpose}</p>
            </div>
            <p style="color: #666; font-size: 0.9em;">Please log in to your MediVault portal to view or manage your appointments.</p>
        </div>
        """
        send_email_notification(user.email, title, email_html)
        
    # 3. SMS Notification if enabled and phone number exists
    if prefs.get('sms', False) and user.phone_number:
        sms_text = f"MediVault Reminder: Appointment with {appointment.doctor_hospital_name} on {appointment.appointment_date} at {appointment.appointment_time}."
        send_sms_notification(user.phone_number, sms_text)
        
    # Record idempotency log in MongoDB
    try:
        db.reminder_logs.insert_one({
            'appointment_id': appointment._id,
            'user_id': user._id,
            'reminder_type': 'multi_channel',
            'lead_time': lead_time_label,
            'sent_at': utc_now()
        })
    except Exception:
        pass
        
    return True, "Reminder dispatched successfully."
