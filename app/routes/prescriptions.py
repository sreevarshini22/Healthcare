import os
from datetime import datetime
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for, 
    send_from_directory, abort, current_app
)
from flask_login import login_required, current_user
from app.models import Prescription, user_id_filter
from app.database import get_db
from app.utils.security import save_user_file, delete_user_file, get_storage_path
from app.utils.helpers import log_activity

prescriptions_bp = Blueprint('prescriptions', __name__)

@prescriptions_bp.route('/')
@login_required
def index():
    """List prescriptions with active/archived toggle and search."""
    show_archived = request.args.get('archived', '0') == '1'
    search_query = request.args.get('q', '').strip()
    
    prescriptions = Prescription.find_by_user(
        user_id=current_user.id,
        is_archived=show_archived,
        search=search_query
    )
    
    db = get_db()
    u_filter = user_id_filter(current_user.id)
    active_count = db.prescriptions.count_documents({'user_id': u_filter, 'is_archived': False})
    archived_count = db.prescriptions.count_documents({'user_id': u_filter, 'is_archived': True})
    
    return render_template(
        'prescriptions/index.html',
        prescriptions=prescriptions,
        show_archived=show_archived,
        search_query=search_query,
        active_count=active_count,
        archived_count=archived_count
    )


@prescriptions_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    """Add a new prescription record."""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        date_str = request.form.get('date', '').strip()
        doctor_name = request.form.get('doctor_name', '').strip()
        medications_info = request.form.get('medications_info', '').strip()
        notes = request.form.get('notes', '').strip()
        
        if not title or not date_str:
            flash("Prescription Title and Date are required.", "danger")
            return render_template('prescriptions/add.html', **request.form)
            
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            rx_date_val = date_str
        except ValueError:
            flash("Invalid date format. Please use YYYY-MM-DD.", "danger")
            return render_template('prescriptions/add.html', **request.form)
            
        file_info = None
        # Optional file attachment
        if 'document_file' in request.files and request.files['document_file'].filename:
            file = request.files['document_file']
            try:
                file_info = save_user_file(file, current_user.id)
            except ValueError as ve:
                flash(str(ve), "danger")
                return render_template('prescriptions/add.html', **request.form)
                
        try:
            new_rx = Prescription.create(
                user_id=current_user.id,
                title=title,
                date_val=rx_date_val,
                doctor_name=doctor_name or None,
                medications_info=medications_info or None,
                file_info=file_info,
                notes=notes or None
            )
            
            log_activity(current_user.id, "Added Prescription", f"Recorded '{title}'")
            flash(f"Prescription '{title}' was saved successfully.", "success")
            return redirect(url_for('prescriptions.index'))
            
        except Exception as e:
            flash("An error occurred while saving the prescription.", "danger")
            return render_template('prescriptions/add.html', **request.form)

    return render_template('prescriptions/add.html')


@prescriptions_bp.route('/<prescription_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(prescription_id):
    """Edit existing prescription details or replace prescription file."""
    rx = Prescription.get_by_id(prescription_id)
    if not rx:
        abort(404)
        
    if str(rx.user_id) != str(current_user.id):
        abort(403)
        
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        date_str = request.form.get('date', '').strip()
        doctor_name = request.form.get('doctor_name', '').strip()
        medications_info = request.form.get('medications_info', '').strip()
        notes = request.form.get('notes', '').strip()
        
        if not title or not date_str:
            flash("Prescription Title and Date are required.", "danger")
            return render_template('prescriptions/edit.html', prescription=rx)
            
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            rx_date_val = date_str
        except ValueError:
            flash("Invalid date format. Please use YYYY-MM-DD.", "danger")
            return render_template('prescriptions/edit.html', prescription=rx)
            
        file_info = None
        # Optional document replacement
        if 'document_file' in request.files and request.files['document_file'].filename:
            file = request.files['document_file']
            try:
                file_info = save_user_file(file, current_user.id)
                if rx.stored_filename:
                    delete_user_file(rx.stored_filename, current_user.id)
            except ValueError as ve:
                flash(str(ve), "danger")
                return render_template('prescriptions/edit.html', prescription=rx)

        Prescription.update(
            rx_id=rx.id,
            user_id=current_user.id,
            title=title,
            date_val=rx_date_val,
            doctor_name=doctor_name or None,
            medications_info=medications_info or None,
            notes=notes or None,
            file_info=file_info
        )

        log_activity(current_user.id, "Updated Prescription", f"Edited '{title}'")
        flash("Prescription updated successfully.", "success")
        return redirect(url_for('prescriptions.index'))

    return render_template('prescriptions/edit.html', prescription=rx)


@prescriptions_bp.route('/<prescription_id>/toggle-archive', methods=['POST'])
@login_required
def toggle_archive(prescription_id):
    """Toggle between active and archived status."""
    rx = Prescription.get_by_id(prescription_id)
    if not rx:
        abort(404)
        
    if str(rx.user_id) != str(current_user.id):
        abort(403)
        
    updated_rx = Prescription.toggle_archive(rx.id, current_user.id)
    
    status_str = "archived" if updated_rx.is_archived else "restored to active"
    log_activity(current_user.id, "Archived Prescription", f"Marked '{rx.title}' as {status_str}")
    flash(f"Prescription '{rx.title}' has been {status_str}.", "info")
    
    return redirect(url_for('prescriptions.index', archived='1' if updated_rx.is_archived else '0'))


@prescriptions_bp.route('/<prescription_id>/file')
@login_required
def download_file(prescription_id):
    """Securely stream prescription document."""
    rx = Prescription.get_by_id(prescription_id)
    if not rx or not rx.stored_filename:
        abort(404)
        
    if str(rx.user_id) != str(current_user.id):
        abort(403)
        
    storage_root = get_storage_path()
    user_dir = os.path.join(storage_root, f"user_{current_user.id}")
    as_attachment = request.args.get('download', '0') == '1'
    
    return send_from_directory(
        user_dir,
        rx.stored_filename,
        as_attachment=as_attachment,
        download_name=rx.original_filename or "prescription_document",
        mimetype=rx.file_mime
    )


@prescriptions_bp.route('/<prescription_id>/delete', methods=['POST'])
@login_required
def delete(prescription_id):
    """Permanently delete prescription."""
    rx = Prescription.get_by_id(prescription_id)
    if not rx:
        abort(404)
        
    if str(rx.user_id) != str(current_user.id):
        abort(403)
        
    title = rx.title
    if rx.stored_filename:
        delete_user_file(rx.stored_filename, current_user.id)
        
    try:
        Prescription.delete(rx.id, current_user.id)
        log_activity(current_user.id, "Deleted Prescription", f"Removed '{title}'")
        flash(f"Prescription '{title}' was deleted successfully.", "info")
    except Exception:
        flash("An error occurred while deleting the prescription.", "danger")
        
    return redirect(url_for('prescriptions.index'))
