from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import current_user

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    return render_template('index.html')

@main_bp.route('/about')
def about():
    return render_template('about.html')

@main_bp.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()

        if not name or not email or not message:
            flash("Please fill in all required fields (Name, Email, and Message).", "danger")
            return render_template('contact.html', name=name, email=email, subject=subject, message=message)

        # In production this could send email or store support ticket
        flash("Thank you for contacting MediVault support. Your message has been received and our team will respond within 24-48 business hours.", "success")
        return redirect(url_for('main.contact'))

    return render_template('contact.html')

@main_bp.route('/privacy')
def privacy():
    return render_template('privacy.html')

@main_bp.route('/terms')
def terms():
    return render_template('terms.html')
