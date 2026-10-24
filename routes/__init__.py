from functools import wraps
from flask import abort, redirect, url_for, flash
from flask_login import current_user


def role_required(*allowed_roles):
    """
    Decorator to restrict access to users with specified roles.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if current_user.role not in allowed_roles:
                flash("Access denied: You do not have permission to access this interface.", "danger")
                # Redirect to appropriate home page based on role
                if current_user.role == "admin":
                    return redirect(url_for("admin.overview"))
                elif current_user.role == "medicine_manager":
                    return redirect(url_for("manager.dashboard"))
                elif current_user.role in ["emergency", "general_1", "general_2"]:
                    return redirect(url_for("room.ward_view", ward_code=current_user.role))
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator
