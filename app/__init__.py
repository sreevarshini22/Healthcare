import os
from datetime import datetime, date
from flask import Flask, render_template, request
from flask_login import LoginManager, current_user
from app.config import Config
from app.database import init_db
from app.models import User, Notification
from app.utils.helpers import format_bytes
from app.services.scheduler import init_scheduler

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = "Please sign in to access your personal health records."
login_manager.login_message_category = "warning"

@login_manager.user_loader
def load_user(user_id):
    return User.get_by_id(user_id)

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Ensure Storage / Uploads directory exists
    storage_path = app.config.get('STORAGE_FOLDER') or app.config.get('UPLOAD_FOLDER')
    os.makedirs(storage_path, exist_ok=True)

    # Initialize MongoDB connection & PyMongo indexes
    init_db(app)

    # Initialize Login Manager
    login_manager.init_app(app)

    # Initialize Background Reminder Scheduler
    init_scheduler(app)

    # Register Jinja Filters
    app.jinja_env.filters['format_bytes'] = format_bytes
    
    @app.template_filter('friendly_date')
    def friendly_date_filter(val):
        if not val:
            return ""
        if isinstance(val, (datetime, date)):
            return val.strftime('%b %d, %Y')
        try:
            d = datetime.strptime(str(val), '%Y-%m-%d')
            return d.strftime('%b %d, %Y')
        except Exception:
            return str(val)

    # Global template context
    @app.context_processor
    def inject_globals():
        unread_notif_count = 0
        if current_user and current_user.is_authenticated:
            try:
                unread_notif_count = Notification.get_unread_count(current_user.id)
            except Exception:
                unread_notif_count = 0
                
        return {
            'app_name': 'MediVault',
            'app_tagline': 'Personal Health Record Manager',
            'current_year': datetime.now().year,
            'today_date': date.today().isoformat(),
            'unread_notif_count': unread_notif_count
        }

    # Register Blueprints
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.records import records_bp
    from app.routes.prescriptions import prescriptions_bp
    from app.routes.appointments import appointments_bp
    from app.routes.ai import ai_bp
    from app.routes.notifications import notifications_bp
    from app.routes.voice import voice_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(records_bp, url_prefix='/records')
    app.register_blueprint(prescriptions_bp, url_prefix='/prescriptions')
    app.register_blueprint(appointments_bp, url_prefix='/appointments')
    app.register_blueprint(ai_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(voice_bp)

    # Error Handlers
    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(413)
    def request_entity_too_large(e):
        return render_template('errors/413.html'), 413

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('errors/500.html'), 500

    return app
