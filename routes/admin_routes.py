from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, User, Medicine, Order, Robot, InventoryTransaction, SystemSetting, AuditLog
from routes import role_required
from services.audit_service import log_audit
from services.inventory_service import adjust_physical_stock, InventoryError
from services.order_service import cancel_order, OrderWorkflowError

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("")
@admin_bp.route("/overview")
@login_required
@role_required("admin")
def overview():
    total_medicines = Medicine.query.count()
    medicines = Medicine.query.all()
    total_available_units = sum(m.available_quantity for m in medicines)
    low_stock_medicines = sum(1 for m in medicines if m.is_low_stock)
    unavailable_medicines = sum(1 for m in medicines if m.stock_status == "UNAVAILABLE")

    orders = Order.query.all()
    orders_pending = sum(1 for o in orders if o.status == "PENDING")
    orders_in_progress = sum(1 for o in orders if o.status in [
        "ACCEPTED", "PREPARING", "READY_FOR_LOADING", "LOADED", "READY_FOR_DISPATCH", "DISPATCHED", "IN_TRANSIT", "AWAITING_RECIPIENT"
    ])
    orders_completed = sum(1 for o in orders if o.status in ["DELIVERED", "RETURNED"])

    r1 = Robot.query.filter_by(robot_code="R1").first()
    r2 = Robot.query.filter_by(robot_code="R2").first()

    recent_audits = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(10).all()

    return render_template(
        "admin/overview.html",
        total_medicines=total_medicines,
        total_available_units=total_available_units,
        low_stock_medicines=low_stock_medicines,
        unavailable_medicines=unavailable_medicines,
        orders_pending=orders_pending,
        orders_in_progress=orders_in_progress,
        orders_completed=orders_completed,
        r1=r1,
        r2=r2,
        recent_audits=recent_audits,
    )


@admin_bp.route("/users", methods=["GET", "POST"])
@login_required
@role_required("admin")
def users_management():
    if request.method == "POST":
        action = request.form.get("action")

        if action == "create":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            role = request.form.get("role", "")
            room_name = request.form.get("room_name", "").strip()

            if not username or not password or not role:
                flash("Username, password, and role are required.", "danger")
            elif User.query.filter_by(username=username).first():
                flash(f"Username '{username}' already exists.", "danger")
            else:
                user = User(
                    username=username,
                    role=role,
                    room_name=room_name or role.replace("_", " ").title(),
                    active=True,
                )
                user.set_password(password)
                db.session.add(user)
                db.session.commit()
                log_audit("USER_CREATED", "User", user.username, f"Created user {user.username} with role {user.role}", current_user.id)
                flash(f"User account '{username}' created successfully.", "success")

        elif action == "toggle_active":
            user_id = request.form.get("user_id")
            user = db.session.get(User, user_id)
            if user:
                if user.id == current_user.id:
                    flash("You cannot deactivate your own account.", "warning")
                else:
                    user.active = not user.active
                    db.session.commit()
                    status_text = "activated" if user.active else "deactivated"
                    log_audit("USER_STATUS_TOGGLED", "User", user.username, f"Account {status_text}", current_user.id)
                    flash(f"User '{user.username}' {status_text}.", "info")

        elif action == "reset_password":
            user_id = request.form.get("user_id")
            new_password = request.form.get("new_password", "")
            user = db.session.get(User, user_id)
            if user and new_password:
                user.set_password(new_password)
                db.session.commit()
                log_audit("USER_PASSWORD_RESET", "User", user.username, "Password reset by admin", current_user.id)
                flash(f"Password reset for '{user.username}'.", "success")

        return redirect(url_for("admin.users_management"))

    users = User.query.order_by(User.role.asc(), User.username.asc()).all()
    return render_template("admin/users.html", users=users)


@admin_bp.route("/medicines", methods=["GET", "POST"])
@login_required
@role_required("admin")
def medicines_management():
    if request.method == "POST":
        action = request.form.get("action")

        if action == "create":
            name = request.form.get("name", "").strip()
            category = request.form.get("category", "General").strip()
            description = request.form.get("description", "").strip()
            unit = request.form.get("unit", "strips").strip()
            physical_stock = int(request.form.get("physical_stock", 0))
            reorder_threshold = int(request.form.get("reorder_threshold", 10))

            if Medicine.query.filter_by(name=name).first():
                flash(f"Medicine with name '{name}' already exists.", "danger")
            else:
                med = Medicine(
                    name=name,
                    category=category,
                    description=description,
                    unit=unit,
                    physical_stock=max(0, physical_stock),
                    reserved_quantity=0,
                    reorder_threshold=max(0, reorder_threshold),
                    active=True,
                )
                db.session.add(med)
                db.session.commit()
                log_audit("MEDICINE_CREATED", "Medicine", med.name, f"Added medicine with {physical_stock} {unit}", current_user.id)
                flash(f"Medicine '{name}' created successfully.", "success")

        elif action == "edit":
            med_id = request.form.get("medicine_id")
            med = db.session.get(Medicine, med_id)
            if med:
                med.name = request.form.get("name", med.name).strip()
                med.category = request.form.get("category", med.category).strip()
                med.description = request.form.get("description", "").strip()
                med.unit = request.form.get("unit", med.unit).strip()
                med.reorder_threshold = max(0, int(request.form.get("reorder_threshold", med.reorder_threshold)))
                db.session.commit()
                log_audit("MEDICINE_EDITED", "Medicine", med.name, f"Updated medicine details", current_user.id)
                flash(f"Medicine '{med.name}' updated.", "success")

        elif action == "toggle_active":
            med_id = request.form.get("medicine_id")
            med = db.session.get(Medicine, med_id)
            if med:
                med.active = not med.active
                db.session.commit()
                status_text = "activated" if med.active else "deactivated"
                log_audit("MEDICINE_STATUS_TOGGLED", "Medicine", med.name, f"Medicine {status_text}", current_user.id)
                flash(f"Medicine '{med.name}' {status_text}.", "info")

        return redirect(url_for("admin.medicines_management"))

    medicines = Medicine.query.order_by(Medicine.name.asc()).all()
    return render_template("admin/medicines.html", medicines=medicines)


@admin_bp.route("/inventory", methods=["GET", "POST"])
@login_required
@role_required("admin")
def inventory_management():
    if request.method == "POST":
        med_id = request.form.get("medicine_id")
        qty_change = int(request.form.get("quantity_change", 0))
        reason = request.form.get("reason", "Admin stock adjustment").strip()

        try:
            med = adjust_physical_stock(
                medicine_id=int(med_id),
                quantity_change=qty_change,
                reason=reason,
                user_id=current_user.id,
                transaction_type="STOCK_ADJUST" if qty_change < 0 else "STOCK_IN",
            )
            flash(f"Adjusted stock for '{med.name}' by {qty_change:+d}. New physical stock: {med.physical_stock}.", "success")
        except (ValueError, TypeError, InventoryError) as e:
            flash(f"Stock adjustment failed: {str(e)}", "danger")

        return redirect(url_for("admin.inventory_management"))

    medicines = Medicine.query.order_by(Medicine.name.asc()).all()
    transactions = InventoryTransaction.query.order_by(InventoryTransaction.created_at.desc()).limit(100).all()
    return render_template("admin/inventory.html", medicines=medicines, transactions=transactions)


@admin_bp.route("/orders", methods=["GET", "POST"])
@login_required
@role_required("admin")
def orders_management():
    if request.method == "POST":
        action = request.form.get("action")
        order_id = request.form.get("order_id")
        reason = request.form.get("reason", "Cancelled by administrator")

        if action == "cancel":
            try:
                cancel_order(order_id, user_id=current_user.id, reason=reason)
                flash(f"Order cancelled successfully and reserved stock released.", "warning")
            except (OrderWorkflowError, InventoryError) as e:
                flash(f"Failed to cancel order: {str(e)}", "danger")

        return redirect(url_for("admin.orders_management"))

    # Filtering
    room_filter = request.args.get("room", "")
    status_filter = request.args.get("status", "")
    priority_filter = request.args.get("priority", "")

    query = Order.query
    if room_filter:
        query = query.filter(Order.room_name == room_filter)
    if status_filter:
        query = query.filter(Order.status == status_filter)
    if priority_filter:
        query = query.filter(Order.priority == int(priority_filter))

    orders = query.order_by(Order.created_at.desc()).all()
    rooms = [r[0] for r in db.session.query(Order.room_name).distinct().all()]

    return render_template(
        "admin/orders.html",
        orders=orders,
        rooms=rooms,
        selected_room=room_filter,
        selected_status=status_filter,
        selected_priority=priority_filter,
    )


@admin_bp.route("/robots", methods=["GET", "POST"])
@login_required
@role_required("admin")
def robots_management():
    if request.method == "POST":
        robot_id = request.form.get("robot_id")
        action = request.form.get("action")
        robot = db.session.get(Robot, robot_id)

        if robot:
            if action == "toggle_active":
                if robot.current_order_id:
                    flash(f"Cannot deactivate {robot.robot_code} while it has an assigned order.", "danger")
                else:
                    robot.active = not robot.active
                    db.session.commit()
                    status_text = "activated" if robot.active else "deactivated"
                    log_audit("ROBOT_ACTIVE_TOGGLED", "Robot", robot.robot_code, f"{robot.display_name} {status_text}", current_user.id)
                    flash(f"{robot.display_name} {status_text}.", "info")

            elif action == "set_maintenance":
                if robot.current_order_id:
                    flash(f"Cannot put {robot.robot_code} into maintenance while it is on a delivery.", "danger")
                else:
                    robot.status = "MAINTENANCE" if robot.status != "MAINTENANCE" else "AVAILABLE"
                    db.session.commit()
                    log_audit("ROBOT_MAINTENANCE_TOGGLED", "Robot", robot.robot_code, f"Status changed to {robot.status}", current_user.id)
                    flash(f"{robot.display_name} status updated to {robot.status}.", "info")

        return redirect(url_for("admin.robots_management"))

    robots = Robot.query.order_by(Robot.robot_code.asc()).all()
    return render_template("admin/robots.html", robots=robots)


@admin_bp.route("/priority", methods=["GET", "POST"])
@login_required
@role_required("admin")
def priority_configuration():
    if request.method == "POST":
        p_emerg = request.form.get("priority_emergency", "1").strip()
        p_gen1 = request.form.get("priority_general_1", "2").strip()
        p_gen2 = request.form.get("priority_general_2", "3").strip()

        try:
            e_val = int(p_emerg)
            g1_val = int(p_gen1)
            g2_val = int(p_gen2)

            if len({e_val, g1_val, g2_val}) != 3:
                flash("Each ward must have a unique priority rank.", "danger")
            else:
                SystemSetting.set_value("priority_emergency", e_val)
                SystemSetting.set_value("priority_general_1", g1_val)
                SystemSetting.set_value("priority_general_2", g2_val)
                log_audit("PRIORITY_CONFIG_UPDATED", "Settings", "Priority", f"Emergency: {e_val}, Gen1: {g1_val}, Gen2: {g2_val}", current_user.id)
                flash("Room priority configuration saved successfully.", "success")
        except ValueError:
            flash("Priorities must be integer numbers.", "danger")

        return redirect(url_for("admin.priority_configuration"))

    priority_emergency = SystemSetting.get_value("priority_emergency", "1")
    priority_general_1 = SystemSetting.get_value("priority_general_1", "2")
    priority_general_2 = SystemSetting.get_value("priority_general_2", "3")

    return render_template(
        "admin/priority.html",
        priority_emergency=priority_emergency,
        priority_general_1=priority_general_1,
        priority_general_2=priority_general_2,
    )


@admin_bp.route("/audit_logs")
@login_required
@role_required("admin")
def audit_logs():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(200).all()
    return render_template("admin/audit_logs.html", logs=logs)
