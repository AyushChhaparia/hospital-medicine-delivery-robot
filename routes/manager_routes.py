from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import Medicine, Order, Robot, InventoryTransaction, db
from routes import role_required
from services.scheduler_service import get_active_orders_queue
from services.robot_service import get_all_robots, get_available_robots, confirm_robot_return, RobotError
from services.inventory_service import adjust_physical_stock, InventoryError
from services.order_service import (
    accept_order,
    reject_order,
    start_preparing_order,
    mark_ready_for_loading,
    assign_robot,
    confirm_medicines_loaded,
    confirm_box_secured,
    complete_and_dispatch_order,
    transit_delivery,
    arrive_at_destination,
    confirm_recipient_delivered,
    start_returning_trip,
    confirm_returned_trip,
    OrderWorkflowError,
)

manager_bp = Blueprint("manager", __name__, url_prefix="/manager")


@manager_bp.route("")
@manager_bp.route("/")
@login_required
@role_required("medicine_manager", "admin")
def dashboard():
    # 1. Fetch priority ordered active queue
    active_queue = get_active_orders_queue()

    # 2. Fetch robots
    robots = get_all_robots()
    available_robots = get_available_robots()

    # 3. Fetch medicines
    medicines = Medicine.query.order_by(Medicine.name.asc()).all()

    # 4. Summary cards metrics
    total_pending = sum(1 for q in active_queue if q["status"] == "PENDING")
    emergency_waiting = sum(1 for q in active_queue if q["priority"] == 1 and q["status"] in ["PENDING", "ACCEPTED", "PREPARING"])
    orders_preparing = sum(1 for q in active_queue if q["status"] == "PREPARING")
    robots_available_count = len(available_robots)
    robots_in_delivery_count = sum(1 for r in robots if r.status in ["DELIVERING", "DISPATCHED", "AWAITING_RECIPIENT", "RETURNING"])
    low_stock_count = sum(1 for m in medicines if m.is_low_stock or m.stock_status == "UNAVAILABLE")

    # Recent completed/in-transit orders
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(15).all()

    return render_template(
        "medicine_manager.html",
        active_queue=active_queue,
        robots=robots,
        available_robots=available_robots,
        medicines=medicines,
        recent_orders=recent_orders,
        total_pending=total_pending,
        emergency_waiting=emergency_waiting,
        orders_preparing=orders_preparing,
        robots_available_count=robots_available_count,
        robots_in_delivery_count=robots_in_delivery_count,
        low_stock_count=low_stock_count,
    )


@manager_bp.route("/order/<int:order_id>/action", methods=["POST"])
@login_required
@role_required("medicine_manager", "admin")
def order_action(order_id):
    action = request.form.get("action")
    notes = request.form.get("notes", "").strip()

    try:
        if action == "accept":
            accept_order(order_id, user_id=current_user.id)
            flash("Order accepted successfully.", "success")

        elif action == "reject":
            reason = request.form.get("reason", "Rejected by manager")
            reject_order(order_id, user_id=current_user.id, reason=reason)
            flash("Order rejected and reserved stock released.", "warning")

        elif action == "prepare":
            start_preparing_order(order_id, user_id=current_user.id)
            flash("Order marked as PREPARING.", "info")

        elif action == "ready_loading":
            mark_ready_for_loading(order_id, user_id=current_user.id)
            flash("Order marked as READY FOR LOADING.", "info")

        elif action == "assign_robot":
            robot_id = request.form.get("robot_id")
            if not robot_id:
                flash("Please select a robot to assign.", "danger")
            else:
                assign_robot(order_id, int(robot_id), user_id=current_user.id)
                flash("Robot assigned to order successfully.", "success")

        elif action == "confirm_loaded":
            confirm_medicines_loaded(order_id, user_id=current_user.id)
            flash("Confirmed: Medicines loaded into robot cargo box.", "success")

        elif action == "secure_box":
            confirm_box_secured(order_id, user_id=current_user.id)
            flash("Confirmed: Cargo box secured and locked. Order is READY FOR DISPATCH.", "success")

        elif action == "complete_dispatch":
            # CRITICAL ATOMIC DISPATCH STEP
            order = complete_and_dispatch_order(order_id, user_id=current_user.id)
            flash(f"Order {order.order_number} DISPATCHED successfully! Stock deducted.", "success")

        elif action == "transit":
            transit_delivery(order_id, user_id=current_user.id)
            flash("Order is now IN TRANSIT towards destination ward.", "info")

        elif action == "arrive":
            arrive_at_destination(order_id, user_id=current_user.id)
            flash("Robot arrived at destination ward; awaiting recipient collection.", "info")

        elif action == "delivered":
            confirm_recipient_delivered(order_id, user_id=current_user.id)
            flash("Recipient delivery confirmed. Robot cargo closed.", "success")

        elif action == "start_return":
            start_returning_trip(order_id, user_id=current_user.id)
            flash("Robot marked as RETURNING to Medicine Room.", "info")

        elif action == "confirm_returned":
            confirm_returned_trip(order_id, user_id=current_user.id)
            flash("Robot confirmed RETURNED to Medicine Room and is now AVAILABLE.", "success")

        else:
            flash(f"Unknown action: {action}", "danger")

    except (OrderWorkflowError, RobotError, InventoryError) as e:
        flash(f"Action failed: {str(e)}", "danger")
    except Exception as e:
        flash(f"Unexpected error: {str(e)}", "danger")

    return redirect(url_for("manager.dashboard"))


@manager_bp.route("/order/<int:order_id>/details")
@login_required
@role_required("medicine_manager", "admin")
def order_details_json(order_id):
    order = Order.query.get_or_404(order_id)
    return jsonify(order.to_dict())


@manager_bp.route("/stock/receive", methods=["POST"])
@login_required
@role_required("medicine_manager", "admin")
def receive_stock():
    medicine_id = request.form.get("medicine_id")
    quantity = request.form.get("quantity")
    reason = request.form.get("reason", "Incoming medicine shipment received")

    try:
        med_id = int(medicine_id)
        qty = int(quantity)
        if qty <= 0:
            flash("Quantity received must be positive.", "danger")
            return redirect(url_for("manager.dashboard"))

        medicine = adjust_physical_stock(
            medicine_id=med_id,
            quantity_change=qty,
            reason=reason,
            user_id=current_user.id,
            transaction_type="STOCK_IN",
        )
        flash(f"Successfully recorded incoming stock of {qty} {medicine.unit} for '{medicine.name}'. Total physical: {medicine.physical_stock}.", "success")
    except (ValueError, TypeError, InventoryError) as e:
        flash(f"Failed to record stock: {str(e)}", "danger")

    return redirect(url_for("manager.dashboard"))


@manager_bp.route("/robot/<int:robot_id>/return", methods=["POST"])
@login_required
@role_required("medicine_manager", "admin")
def force_confirm_robot_return(robot_id):
    try:
        robot = confirm_robot_return(robot_id, user_id=current_user.id)
        flash(f"{robot.display_name} return confirmed. Robot is now AVAILABLE.", "success")
    except RobotError as e:
        flash(f"Failed to confirm return: {str(e)}", "danger")
    return redirect(url_for("manager.dashboard"))


@manager_bp.route("/queue_data")
@login_required
@role_required("medicine_manager", "admin")
def queue_data():
    """
    JSON polling endpoint for manager dashboard.
    """
    active_queue = get_active_orders_queue()
    robots = get_all_robots()
    return jsonify({
        "queue": [{
            "position": q["position"],
            "id": q["id"],
            "order_number": q["order_number"],
            "room_name": q["room_name"],
            "priority": q["priority"],
            "status": q["status"],
            "created_at": q["created_at"].strftime("%H:%M:%S") if q["created_at"] else "",
            "robot_name": q["robot_name"] or "None",
            "items_count": q["items_count"],
        } for q in active_queue],
        "robots": [r.to_dict() for r in robots],
    })
