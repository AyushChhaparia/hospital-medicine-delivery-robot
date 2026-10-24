import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_required, current_user
from models import Medicine, Order, OrderItem
from services.order_service import create_order, cancel_order, OrderWorkflowError
from services.inventory_service import InventoryError

room_bp = Blueprint("room", __name__, url_prefix="/ward")

WARD_CONFIG = {
    "emergency": {
        "title": "Emergency Ward / Operation Theatre",
        "badge_class": "badge-danger",
        "priority_label": "High Priority (Emergency)",
    },
    "general_1": {
        "title": "General Ward 1",
        "badge_class": "badge-primary",
        "priority_label": "Standard Priority (Ward 1)",
    },
    "general_2": {
        "title": "General Ward 2",
        "badge_class": "badge-info",
        "priority_label": "Standard Priority (Ward 2)",
    },
}


@room_bp.route("/<ward_code>")
@login_required
def ward_view(ward_code):
    # Enforce strict room boundary: a user can only access their assigned ward
    if current_user.role != ward_code:
        flash(f"Unauthorized: You cannot access {ward_code.replace('_', ' ').title()}.", "danger")
        if current_user.role in WARD_CONFIG:
            return redirect(url_for("room.ward_view", ward_code=current_user.role))
        elif current_user.role == "medicine_manager":
            return redirect(url_for("manager.dashboard"))
        elif current_user.role == "admin":
            return redirect(url_for("admin.overview"))
        abort(403)

    ward_info = WARD_CONFIG.get(ward_code)
    if not ward_info:
        abort(404)

    # Fetch active medicines
    medicines = Medicine.query.filter_by(active=True).order_by(Medicine.category.asc(), Medicine.name.asc()).all()

    # Fetch orders belonging only to this room
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()

    # Calculate room summary metrics
    available_medicines_count = sum(1 for m in medicines if m.is_available)
    pending_orders_count = sum(1 for o in orders if o.status == "PENDING")
    in_progress_count = sum(1 for o in orders if o.status in [
        "ACCEPTED", "PREPARING", "READY_FOR_LOADING", "LOADED", "READY_FOR_DISPATCH", "DISPATCHED", "IN_TRANSIT", "AWAITING_RECIPIENT"
    ])
    completed_count = sum(1 for o in orders if o.status in ["DELIVERED", "RETURNED"])

    categories = sorted(list(set(m.category for m in medicines)))

    return render_template(
        "room_dashboard.html",
        ward_code=ward_code,
        ward_info=ward_info,
        medicines=medicines,
        orders=orders,
        categories=categories,
        available_medicines_count=available_medicines_count,
        pending_orders_count=pending_orders_count,
        in_progress_count=in_progress_count,
        completed_count=completed_count,
    )


@room_bp.route("/<ward_code>/order", methods=["POST"])
@login_required
def submit_order(ward_code):
    if current_user.role != ward_code:
        return jsonify({"success": False, "error": "Unauthorized access to ward ordering."}), 403

    ward_info = WARD_CONFIG.get(ward_code)
    if not ward_info:
        return jsonify({"success": False, "error": "Invalid ward."}), 400

    # Parse items either from JSON or Form
    if request.is_json:
        data = request.get_json()
        items_data = data.get("items", [])
        notes = data.get("notes", "")
    else:
        # Form submission fallback
        raw_items = request.form.get("items_json")
        notes = request.form.get("notes", "")
        try:
            items_data = json.loads(raw_items) if raw_items else []
        except Exception:
            items_data = []

    if not items_data:
        if request.is_json:
            return jsonify({"success": False, "error": "Your order cart is empty. Please select medicines to order."}), 400
        flash("Your order cart is empty. Please select medicines to order.", "danger")
        return redirect(url_for("room.ward_view", ward_code=ward_code))

    try:
        order = create_order(
            user=current_user,
            room_name=ward_info["title"],
            items_data=items_data,
            notes=notes,
        )

        msg = f"Order {order.order_number} submitted successfully! Your medicines have been reserved."
        if request.is_json:
            return jsonify({
                "success": True,
                "message": msg,
                "order": order.to_dict(),
            })
        flash(msg, "success")
        return redirect(url_for("room.ward_view", ward_code=ward_code))

    except (InventoryError, OrderWorkflowError) as e:
        if request.is_json:
            return jsonify({"success": False, "error": str(e)}), 400
        flash(f"Order submission failed: {str(e)}", "danger")
        return redirect(url_for("room.ward_view", ward_code=ward_code))
    except Exception as e:
        if request.is_json:
            return jsonify({"success": False, "error": "An unexpected error occurred while placing order."}), 500
        flash("An unexpected error occurred while placing order.", "danger")
        return redirect(url_for("room.ward_view", ward_code=ward_code))


@room_bp.route("/<ward_code>/order/<int:order_id>/cancel", methods=["POST"])
@login_required
def cancel_ward_order(ward_code, order_id):
    if current_user.role != ward_code:
        abort(403)

    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        abort(403)

    reason = request.form.get("reason", "Cancelled by room user")
    try:
        cancel_order(order_id, user_id=current_user.id, reason=reason)
        flash(f"Order {order.order_number} has been cancelled and reservations released.", "info")
    except (OrderWorkflowError, InventoryError) as e:
        flash(f"Cancellation failed: {str(e)}", "danger")

    return redirect(url_for("room.ward_view", ward_code=ward_code))


@room_bp.route("/<ward_code>/poll")
@login_required
def poll_ward_status(ward_code):
    """
    Lightweight polling endpoint for real-time status updates in ward UI.
    """
    if current_user.role != ward_code:
        return jsonify({"error": "Unauthorized"}), 403

    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).limit(20).all()
    medicines = Medicine.query.filter_by(active=True).all()

    return jsonify({
        "orders": [o.to_dict() for o in orders],
        "medicines": [{
            "id": m.id,
            "name": m.name,
            "available_quantity": m.available_quantity,
            "status": m.stock_status,
            "is_available": m.is_available,
        } for m in medicines],
    })
