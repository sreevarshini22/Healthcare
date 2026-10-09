from datetime import datetime, date
from flask import Blueprint, render_template, request, flash, redirect, url_for, abort
from flask_login import login_required, current_user
from app.models import Appointment, user_id_filter
from app.database import get_db
from app.utils.helpers import log_activity

appointments_bp = Blueprint('appointments', __name__)

@appointments_bp.route('/')
@login_required
def index():
    """List appointments with status tab filters and search."""
    status_filter = request.args.get('status', 'all').lower()
    search_query = request.args.get('q', '').strip()
    
    appointments = Appointment.find_by_user(
        user_id=current_user.id,
        status_filter=status_filter,
        search=search_query
    )
    
    today_str = date.today().isoformat()
    db = get_db()
    u_filter = user_id_filter(current_user.id)
    
    total_count = db.appointments.count_documents({'user_id': u_filter})
    upcoming_count = db.appointments.count_documents({
        'user_id': u_filter,
        'status': 'Upcoming',
        'appointment_date': {'$gte': today_str}
    })
    completed_count = db.appointments.count_documents({'user_id': u_filter, 'status': 'Completed'})
    cancelled_count = db.appointments.count_documents({'user_id': u_filter, 'status': 'Cancelled'})
    
    return render_template(
        'appointments/index.html',
        appointments=appointments,
        status_filter=status_filter,
        search_query=search_query,
        total_count=total_count,
        upcoming_count=upcoming_count,
        completed_count=completed_count,
        cancelled_count=cancelled_count,
        today=date.today()
    )


@appointments_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    """Schedule a new appointment."""
    if request.method == 'POST':
        doctor_hospital = request.form.get('doctor_hospital_name', '').strip()
        date_str = request.form.get('appointment_date', '').strip()
        time_str = request.form.get('appointment_time', '').strip()
        location = request.form.get('location', '').strip()
        purpose = request.form.get('purpose', '').strip()
        status = request.form.get('status', 'Upcoming')
        notes = request.form.get('notes', '').strip()
        
        if not doctor_hospital or not date_str or not time_str or not location or not purpose:
            flash("Please complete all required fields (Doctor/Hospital, Date, Time, Location, Purpose).", "danger")
            return render_template('appointments/add.html', **request.form)
            
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            apt_date_val = date_str
        except ValueError:
            flash("Invalid date format. Please use YYYY-MM-DD.", "danger")
            return render_template('appointments/add.html', **request.form)
            
        try:
            new_apt = Appointment.create(
                user_id=current_user.id,
                doctor_hospital_name=doctor_hospital,
                appointment_date=apt_date_val,
                appointment_time=time_str,
                location=location,
                purpose=purpose,
                status=status,
                notes=notes or None
            )
            
            log_activity(current_user.id, "Scheduled Appointment", f"With {doctor_hospital} on {date_str}")
            flash(f"Appointment with {doctor_hospital} has been scheduled for {date_str}.", "success")
            return redirect(url_for('appointments.index'))
            
        except Exception:
            flash("An error occurred while saving the appointment. Please try again.", "danger")
            return render_template('appointments/add.html', **request.form)

    return render_template('appointments/add.html')


@appointments_bp.route('/<appointment_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(appointment_id):
    """Edit appointment details."""
    apt = Appointment.get_by_id(appointment_id)
    if not apt:
        abort(404)
        
    if str(apt.user_id) != str(current_user.id):
        abort(403)
        
    if request.method == 'POST':
        doctor_hospital = request.form.get('doctor_hospital_name', '').strip()
        date_str = request.form.get('appointment_date', '').strip()
        time_str = request.form.get('appointment_time', '').strip()
        location = request.form.get('location', '').strip()
        purpose = request.form.get('purpose', '').strip()
        status = request.form.get('status', 'Upcoming')
        notes = request.form.get('notes', '').strip()
        
        if not doctor_hospital or not date_str or not time_str or not location or not purpose:
            flash("Please complete all required fields.", "danger")
            return render_template('appointments/edit.html', appointment=apt)
            
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            apt_date_val = date_str
        except ValueError:
            flash("Invalid date format. Please use YYYY-MM-DD.", "danger")
            return render_template('appointments/edit.html', appointment=apt)
            
        Appointment.update(
            apt_id=apt.id,
            user_id=current_user.id,
            doctor_hospital_name=doctor_hospital,
            appointment_date=apt_date_val,
            appointment_time=time_str,
            location=location,
            purpose=purpose,
            status=status,
            notes=notes or None
        )

        log_activity(current_user.id, "Updated Appointment", f"Modified appointment with {doctor_hospital}")
        flash("Appointment updated successfully.", "success")
        return redirect(url_for('appointments.index'))

    return render_template('appointments/edit.html', appointment=apt)


@appointments_bp.route('/<appointment_id>/status', methods=['POST'])
@login_required
def update_status(appointment_id):
    """Quickly update appointment status (e.g. Cancel or Complete)."""
    apt = Appointment.get_by_id(appointment_id)
    if not apt:
        abort(404)
        
    if str(apt.user_id) != str(current_user.id):
        abort(403)
        
    new_status = request.form.get('status')
    if new_status in ['Upcoming', 'Completed', 'Cancelled']:
        Appointment.update_status(apt.id, current_user.id, new_status)
        log_activity(current_user.id, "Changed Appointment Status", f"Set appointment with {apt.doctor_hospital_name} to {new_status}")
        flash(f"Appointment marked as {new_status}.", "info")
    else:
        flash("Invalid status selected.", "danger")
        
    return redirect(url_for('appointments.index'))


@appointments_bp.route('/<appointment_id>/delete', methods=['POST'])
@login_required
def delete(appointment_id):
    """Delete an appointment entry."""
    apt = Appointment.get_by_id(appointment_id)
    if not apt:
        abort(404)
        
    if str(apt.user_id) != str(current_user.id):
        abort(403)
        
    doctor_name = apt.doctor_hospital_name
    try:
        Appointment.delete(apt.id, current_user.id)
        log_activity(current_user.id, "Deleted Appointment", f"Removed appointment with {doctor_name}")
        flash(f"Appointment with {doctor_name} was removed.", "info")
    except Exception:
        flash("An error occurred while deleting the appointment.", "danger")
        
    return redirect(url_for('appointments.index'))
