from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from models import User
from services.audit_service import log_audit

auth_bp = Blueprint("auth", __name__)


def redirect_user_by_role(role):
    if role == "admin":
        return redirect(url_for("admin.overview"))
    elif role == "medicine_manager":
        return redirect(url_for("manager.dashboard"))
    elif role in ["emergency", "general_1", "general_2"]:
        return redirect(url_for("room.ward_view", ward_code=role))
    return redirect(url_for("auth.login"))


@auth_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect_user_by_role(current_user.role)
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect_user_by_role(current_user.role)

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Please enter both username and password.", "danger")
            return render_template("login.html")

        user = User.query.filter_by(username=username).first()

        if not user or not user.check_password(password):
            log_audit(
                action="LOGIN_FAILED",
                entity_type="User",
                entity_id=username,
                details=f"Failed login attempt for username '{username}'",
            )
            flash("Invalid username or password.", "danger")
            return render_template("login.html")

        if not user.active:
            log_audit(
                action="LOGIN_BLOCKED_INACTIVE",
                entity_type="User",
                entity_id=username,
                details=f"Blocked login attempt for inactive user '{username}'",
                user_id=user.id,
            )
            flash("This account has been deactivated. Please contact an administrator.", "danger")
            return render_template("login.html")

        login_user(user)
        log_audit(
            action="LOGIN_SUCCESS",
            entity_type="User",
            entity_id=username,
            details=f"User {user.username} ({user.role}) logged in successfully",
            user_id=user.id,
        )
        flash(f"Welcome back, {user.username}!", "success")
        return redirect_user_by_role(user.role)

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    user_id = current_user.id
    username = current_user.username
    logout_user()
    log_audit(
        action="LOGOUT",
        entity_type="User",
        entity_id=username,
        details=f"User {username} logged out",
        user_id=user_id,
    )
    flash("You have been logged out securely.", "info")
    return redirect(url_for("auth.login"))
