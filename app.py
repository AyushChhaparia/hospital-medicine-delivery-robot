from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from config import Config
from models import db, User, Medicine, Robot, SystemSetting


login_manager = LoginManager()
csrf = CSRFProtect()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"

    csrf.init_app(app)
    # Exempt Robot API routes from CSRF as they use token-based auth
    from routes.api_routes import api_bp
    csrf.exempt(api_bp)

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except (ValueError, TypeError):
            return None

    # Register blueprints
    from routes.auth_routes import auth_bp
    from routes.room_routes import room_bp
    from routes.manager_routes import manager_bp
    from routes.admin_routes import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(room_bp)
    app.register_blueprint(manager_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    # Context processors and template filters
    @app.context_processor
    def inject_global_data():
        return {
            "app_name": "Hospital Autonomous Medicine Delivery",
        }

    @app.template_filter("status_badge")
    def status_badge_filter(status):
        mapping = {
            "PENDING": "badge-warning",
            "ACCEPTED": "badge-info",
            "PREPARING": "badge-primary",
            "READY_FOR_LOADING": "badge-secondary",
            "LOADED": "badge-secondary",
            "READY_FOR_DISPATCH": "badge-primary",
            "DISPATCHED": "badge-dark",
            "IN_TRANSIT": "badge-info",
            "AWAITING_RECIPIENT": "badge-warning",
            "DELIVERED": "badge-success",
            "RETURNING": "badge-secondary",
            "RETURNED": "badge-success",
            "REJECTED": "badge-danger",
            "CANCELLED": "badge-danger",
            "AVAILABLE": "badge-success",
            "ASSIGNED": "badge-primary",
            "LOADING": "badge-warning",
            "READY": "badge-info",
            "DELIVERING": "badge-info",
            "OFFLINE": "badge-danger",
            "MAINTENANCE": "badge-danger",
            "UNAVAILABLE": "badge-danger",
            "LOW STOCK": "badge-warning",
        }
        return mapping.get(status, "badge-secondary")

    @app.template_filter("priority_badge")
    def priority_badge_filter(priority):
        if priority == 1:
            return "badge-danger"
        elif priority == 2:
            return "badge-primary"
        return "badge-info"

    @app.template_filter("priority_name")
    def priority_name_filter(priority):
        if priority == 1:
            return "Priority 1 (Emergency / OT)"
        elif priority == 2:
            return "Priority 2 (General Ward 1)"
        elif priority == 3:
            return "Priority 3 (General Ward 2)"
        return f"Priority {priority}"

    return app


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
        # Auto-seed initial demo accounts if users table is empty
        if not User.query.first():
            from seed import seed_all
            seed_all()
    print("\n* Hospital Medicine Delivery System running on http://0.0.0.0:5000 (accessible on Wi-Fi at http://192.168.1.10:5000)\n")
    app.run(debug=True, host="0.0.0.0", port=5000)
