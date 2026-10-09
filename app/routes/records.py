import os
from datetime import datetime
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for, 
    send_from_directory, abort, current_app
)
from flask_login import login_required, current_user
from app.models import MedicalRecord
from app.utils.security import save_user_file, delete_user_file, get_storage_path
from app.utils.helpers import log_activity, DOCUMENT_CATEGORIES

records_bp = Blueprint('records', __name__)

@records_bp.route('/')
@login_required
def index():
    """List medical records with category filtering, search, and date sorting."""
    category = request.args.get('category', '').strip()
    search_query = request.args.get('q', '').strip()
    sort_order = request.args.get('sort', 'newest')  # newest, oldest, title_asc, title_desc
    
    records = MedicalRecord.find_by_user(
        user_id=current_user.id,
        category=category,
        search=search_query,
        sort=sort_order
    )
    
    return render_template(
        'records/index.html',
        records=records,
        categories=DOCUMENT_CATEGORIES,
        selected_category=category,
        search_query=search_query,
        selected_sort=sort_order,
        total_count=len(records)
    )


@records_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    """Upload a new medical record."""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        category = request.form.get('category', '').strip()
        report_date_str = request.form.get('report_date', '').strip()
        doctor_facility = request.form.get('doctor_or_facility', '').strip()
        notes = request.form.get('notes', '').strip()
        
        # File handling
        if 'document_file' not in request.files:
            flash("Please choose a medical document file to upload.", "danger")
            return render_template('records/add.html', categories=DOCUMENT_CATEGORIES, **request.form)
            
        file = request.files['document_file']
        if file.filename == '':
            flash("No file was selected for upload.", "danger")
            return render_template('records/add.html', categories=DOCUMENT_CATEGORIES, **request.form)
            
        # Validate required text inputs
        if not title or not category or not report_date_str:
            flash("Title, Category, and Report Date are required fields.", "danger")
            return render_template('records/add.html', categories=DOCUMENT_CATEGORIES, **request.form)
            
        try:
            report_date = datetime.strptime(report_date_str, '%Y-%m-%d').date()
            report_date_val = report_date_str
        except ValueError:
            flash("Invalid date format. Please use YYYY-MM-DD.", "danger")
            return render_template('records/add.html', categories=DOCUMENT_CATEGORIES, **request.form)
            
        # Save file securely in isolated user directory
        try:
            file_info = save_user_file(file, current_user.id)
            
            new_record = MedicalRecord.create(
                user_id=current_user.id,
                title=title,
                category=category,
                report_date=report_date_val,
                doctor_or_facility=doctor_facility or None,
                file_info=file_info,
                notes=notes or None
            )
            
            log_activity(current_user.id, "Uploaded Record", f"Added '{title}' ({category})")
            flash(f"Medical document '{title}' was securely uploaded and archived.", "success")
            return redirect(url_for('records.view_record', record_id=new_record.id))
            
        except ValueError as ve:
            flash(str(ve), "danger")
            return render_template('records/add.html', categories=DOCUMENT_CATEGORIES, **request.form)
        except Exception as e:
            flash("An unexpected error occurred while saving your record. Please try again.", "danger")
            return render_template('records/add.html', categories=DOCUMENT_CATEGORIES, **request.form)

    return render_template('records/add.html', categories=DOCUMENT_CATEGORIES)


@records_bp.route('/<record_id>')
@login_required
def view_record(record_id):
    """View details of a specific medical record."""
    record = MedicalRecord.get_by_id(record_id)
    if not record:
        abort(404)
        
    # Strictly enforce ownership
    if str(record.user_id) != str(current_user.id):
        abort(403)
        
    return render_template('records/view.html', record=record)


@records_bp.route('/<record_id>/file')
@login_required
def download_file(record_id):
    """
    Secure file streaming endpoint.
    Strictly checks that the file belongs to current_user.
    Can be previewed inline (default) or downloaded with ?download=1
    """
    record = MedicalRecord.get_by_id(record_id)
    if not record:
        abort(404)
        
    # Strictly enforce ownership
    if str(record.user_id) != str(current_user.id):
        abort(403)
        
    storage_root = get_storage_path()
    user_dir = os.path.join(storage_root, f"user_{current_user.id}")
    as_attachment = request.args.get('download', '0') == '1'
    
    return send_from_directory(
        user_dir,
        record.stored_filename,
        as_attachment=as_attachment,
        download_name=record.original_filename,
        mimetype=record.file_mime
    )


@records_bp.route('/<record_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_record(record_id):
    """Edit record metadata or replace the document."""
    record = MedicalRecord.get_by_id(record_id)
    if not record:
        abort(404)
        
    # Strictly enforce ownership
    if str(record.user_id) != str(current_user.id):
        abort(403)
        
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        category = request.form.get('category', '').strip()
        report_date_str = request.form.get('report_date', '').strip()
        doctor_facility = request.form.get('doctor_or_facility', '').strip()
        notes = request.form.get('notes', '').strip()
        
        if not title or not category or not report_date_str:
            flash("Title, Category, and Report Date are required fields.", "danger")
            return render_template('records/edit.html', record=record, categories=DOCUMENT_CATEGORIES)
            
        try:
            datetime.strptime(report_date_str, '%Y-%m-%d')
            report_date_val = report_date_str
        except ValueError:
            flash("Invalid date format. Please use YYYY-MM-DD.", "danger")
            return render_template('records/edit.html', record=record, categories=DOCUMENT_CATEGORIES)
            
        file_info = None
        # Optional document replacement
        if 'document_file' in request.files and request.files['document_file'].filename:
            file = request.files['document_file']
            try:
                # Save new file
                file_info = save_user_file(file, current_user.id)
                # Delete old file
                if record.stored_filename:
                    delete_user_file(record.stored_filename, current_user.id)
            except ValueError as ve:
                flash(str(ve), "danger")
                return render_template('records/edit.html', record=record, categories=DOCUMENT_CATEGORIES)

        updated_record = MedicalRecord.update(
            record_id=record.id,
            user_id=current_user.id,
            title=title,
            category=category,
            report_date=report_date_val,
            doctor_or_facility=doctor_facility or None,
            notes=notes or None,
            file_info=file_info
        )
        
        log_activity(current_user.id, "Updated Record", f"Edited '{title}'")
        flash("Medical record details updated successfully.", "success")
        return redirect(url_for('records.view_record', record_id=record.id))

    return render_template('records/edit.html', record=record, categories=DOCUMENT_CATEGORIES)


@records_bp.route('/<record_id>/delete', methods=['POST'])
@login_required
def delete_record(record_id):
    """Delete record and remove file from disk."""
    record = MedicalRecord.get_by_id(record_id)
    if not record:
        abort(404)
        
    # Strictly enforce ownership
    if str(record.user_id) != str(current_user.id):
        abort(403)
        
    title = record.title
    stored_name = record.stored_filename
    
    try:
        if stored_name:
            delete_user_file(stored_name, current_user.id)
        MedicalRecord.delete(record.id, current_user.id)
        
        log_activity(current_user.id, "Deleted Record", f"Removed '{title}'")
        flash(f"Record '{title}' and its associated file were permanently removed.", "info")
    except Exception as e:
        flash("An error occurred while deleting the record.", "danger")
        
    return redirect(url_for('records.index'))
