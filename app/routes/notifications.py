from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app.models import Notification
from app.utils.helpers import log_activity

notifications_bp = Blueprint('notifications', __name__, url_prefix='/notifications')

@notifications_bp.route('/')
@login_required
def index():
    """Notification Center showing recent appointment alerts, security events, and AI summaries."""
    notifications = Notification.get_user_notifications(current_user.id, limit=50)
    unread_count = Notification.get_unread_count(current_user.id)
    
    return render_template(
        'notifications/index.html',
        notifications=notifications,
        unread_count=unread_count
    )


@notifications_bp.route('/unread-count')
@login_required
def unread_count():
    """AJAX endpoint for polling unread notification badge."""
    count = Notification.get_unread_count(current_user.id)
    return jsonify({'unread_count': count})


@notifications_bp.route('/<notif_id>/read', methods=['POST'])
@login_required
def mark_read(notif_id):
    """Mark single notification as read."""
    Notification.mark_as_read(notif_id, current_user.id)
    if request.is_json:
        return jsonify({'success': True})
    return redirect(url_for('notifications.index'))


@notifications_bp.route('/read-all', methods=['POST'])
@login_required
def mark_all_read():
    """Mark all notifications as read."""
    Notification.mark_all_read(current_user.id)
    if request.is_json:
        return jsonify({'success': True})
    flash("All notifications marked as read.", "info")
    return redirect(url_for('notifications.index'))


@notifications_bp.route('/<notif_id>/delete', methods=['POST'])
@login_required
def delete(notif_id):
    """Delete a single notification."""
    Notification.delete(notif_id, current_user.id)
    flash("Notification removed.", "info")
    return redirect(url_for('notifications.index'))


@notifications_bp.route('/preferences', methods=['POST'])
@login_required
def update_preferences():
    """Update multi-channel reminder preferences (Email, SMS, Voice, Lead Times)."""
    email_enabled = request.form.get('reminder_email') == '1'
    sms_enabled = request.form.get('reminder_sms') == '1'
    voice_enabled = request.form.get('reminder_voice') == '1'
    voice_opt_in = request.form.get('voice_opt_in') == '1'
    
    lead_times = request.form.getlist('lead_times')
    if not lead_times:
        lead_times = ['24h', '2h']
        
    current_user.update_reminder_preferences(
        email=email_enabled,
        sms=sms_enabled,
        voice=voice_enabled,
        lead_times=lead_times,
        voice_opt_in=voice_opt_in
    )
    
    log_activity(current_user.id, "Reminder Preferences Updated", "Updated notification and voice alert settings.")
    flash("Reminder and notification preferences saved successfully.", "success")
    return redirect(url_for('notifications.index'))
