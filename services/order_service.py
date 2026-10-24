import uuid
from models import db, Order, OrderItem, Medicine, Robot, utc_now
from services.inventory_service import (
    reserve_stock_for_order,
    release_order_reservation,
    deduct_dispatched_stock,
    InventoryError,
)
from services.scheduler_service import get_room_priority
from services.robot_service import assign_robot_to_order, unassign_robot, confirm_robot_return, RobotError
from services.audit_service import log_audit


class OrderWorkflowError(Exception):
    pass


def generate_order_number():
    now_str = utc_now().strftime("%Y%m%d")
    short_uuid = uuid.uuid4().hex[:6].upper()
    return f"ORD-{now_str}-{short_uuid}"


def create_order(user, room_name, items_data, notes=None):
    """
    Create a new medicine order from a ward room.
    Reserves stock atomically.
    items_data: [{'medicine_id': 1, 'quantity': 2}, ...]
    """
    if not items_data:
        raise OrderWorkflowError("Order must contain at least one medicine item.")

    priority = get_room_priority(room_name)
    order_number = generate_order_number()

    try:
        # Atomic stock reservation check
        reserved_items = reserve_stock_for_order(items_data)

        order = Order(
            order_number=order_number,
            user_id=user.id,
            room_name=room_name,
            priority=priority,
            status="PENDING",
            manager_notes=notes,
            created_at=utc_now(),
        )
        db.session.add(order)
        db.session.flush()  # Obtain order.id

        for medicine, qty in reserved_items:
            order_item = OrderItem(
                order_id=order.id,
                medicine_id=medicine.id,
                quantity=qty,
                unit=medicine.unit,
            )
            db.session.add(order_item)

        db.session.commit()

        log_audit(
            action="ORDER_CREATED",
            entity_type="Order",
            entity_id=order.order_number,
            details=f"Order created by {user.username} for {room_name} with {len(reserved_items)} items. Priority: {priority}",
            user_id=user.id,
        )
        return order
    except Exception as e:
        db.session.rollback()
        raise e


def accept_order(order_id, user_id):
    order = db.session.get(Order, order_id)
    if not order:
        raise OrderWorkflowError("Order not found.")
    if order.status != "PENDING":
        raise OrderWorkflowError(f"Cannot accept order in status '{order.status}'.")

    order.status = "ACCEPTED"
    order.accepted_at = utc_now()
    db.session.commit()

    log_audit("ORDER_ACCEPTED", "Order", order.order_number, f"Order accepted by manager", user_id)
    return order


def reject_order(order_id, user_id, reason="Rejected by manager"):
    order = db.session.get(Order, order_id)
    if not order:
        raise OrderWorkflowError("Order not found.")
    if order.status != "PENDING":
        raise OrderWorkflowError(f"Cannot reject order in status '{order.status}'.")

    # Release reservations
    release_order_reservation(order, user_id=user_id, reason=reason)
    order.status = "REJECTED"
    order.manager_notes = (order.manager_notes or "") + f" [Rejection Reason: {reason}]"
    db.session.commit()

    log_audit("ORDER_REJECTED", "Order", order.order_number, f"Order rejected: {reason}", user_id)
    return order


def start_preparing_order(order_id, user_id):
    order = db.session.get(Order, order_id)
    if not order:
        raise OrderWorkflowError("Order not found.")
    if order.status != "ACCEPTED":
        raise OrderWorkflowError(f"Cannot start preparation for order in status '{order.status}'.")

    order.status = "PREPARING"
    db.session.commit()

    log_audit("ORDER_PREPARING", "Order", order.order_number, "Started medicine preparation", user_id)
    return order


def mark_ready_for_loading(order_id, user_id):
    order = db.session.get(Order, order_id)
    if not order:
        raise OrderWorkflowError("Order not found.")
    if order.status != "PREPARING":
        raise OrderWorkflowError(f"Cannot mark ready for loading for order in status '{order.status}'.")

    order.status = "READY_FOR_LOADING"
    db.session.commit()

    log_audit("ORDER_READY_LOADING", "Order", order.order_number, "Medicines prepared and ready to load", user_id)
    return order


def assign_robot(order_id, robot_id, user_id):
    order = db.session.get(Order, order_id)
    if not order:
        raise OrderWorkflowError("Order not found.")
    if order.status not in ["ACCEPTED", "PREPARING", "READY_FOR_LOADING"]:
        raise OrderWorkflowError(f"Cannot assign robot for order in status '{order.status}'.")

    robot = assign_robot_to_order(robot_id, order, user_id)
    db.session.commit()
    return order, robot


def confirm_medicines_loaded(order_id, user_id):
    order = db.session.get(Order, order_id)
    if not order:
        raise OrderWorkflowError("Order not found.")
    if order.status != "READY_FOR_LOADING":
        raise OrderWorkflowError(f"Cannot confirm loading for order in status '{order.status}'. Must be READY_FOR_LOADING.")

    if not order.robot_id:
        raise OrderWorkflowError("Cannot confirm loading: No robot is assigned to this order yet.")

    robot = db.session.get(Robot, order.robot_id)
    if not robot:
        raise OrderWorkflowError("Assigned robot not found.")

    order.status = "LOADED"
    order.loaded_at = utc_now()
    robot.status = "LOADING"
    db.session.commit()

    log_audit("ORDER_LOADED", "Order", order.order_number, f"Medicines confirmed loaded into {robot.display_name}", user_id)
    return order


def confirm_box_secured(order_id, user_id):
    order = db.session.get(Order, order_id)
    if not order:
        raise OrderWorkflowError("Order not found.")
    if order.status != "LOADED":
        raise OrderWorkflowError(f"Cannot confirm box secured for order in status '{order.status}'. Must be LOADED.")

    if not order.robot_id:
        raise OrderWorkflowError("Cannot secure box: No robot assigned.")

    robot = db.session.get(Robot, order.robot_id)
    order.status = "READY_FOR_DISPATCH"
    if robot:
        robot.status = "READY"
    db.session.commit()

    log_audit("ORDER_BOX_SECURED", "Order", order.order_number, "Robot cargo box locked and ready for dispatch", user_id)
    return order


def complete_and_dispatch_order(order_id, user_id):
    order = db.session.get(Order, order_id)
    if not order:
        raise OrderWorkflowError("Order not found.")

    if order.status == "DISPATCHED":
        raise OrderWorkflowError(f"Order {order.order_number} has already been dispatched.")

    if order.status != "READY_FOR_DISPATCH":
        raise OrderWorkflowError(
            f"Cannot dispatch order in status '{order.status}'. Order must be in 'READY_FOR_DISPATCH' with medicines loaded and box secured."
        )

    if not order.robot_id:
        raise OrderWorkflowError("Cannot dispatch: No robot is assigned.")

    robot = db.session.get(Robot, order.robot_id)
    if not robot or not robot.active:
        raise OrderWorkflowError("Cannot dispatch: Assigned robot is invalid or inactive.")

    try:
        # Atomic inventory deduction
        deduct_dispatched_stock(order, user_id)

        order.status = "DISPATCHED"
        order.dispatched_at = utc_now()

        robot.status = "DISPATCHED"
        robot.last_location = "Medicine Room (Dispatched)"
        robot.last_seen = utc_now()

        db.session.commit()

        log_audit(
            action="ORDER_DISPATCHED",
            entity_type="Order",
            entity_id=order.order_number,
            details=f"Order {order.order_number} dispatched with {robot.display_name} to {order.room_name}. Physical stock deducted.",
            user_id=user_id,
        )
        return order
    except Exception as e:
        db.session.rollback()
        raise e


# Subsequent simulation / robot workflow steps
def transit_delivery(order_id, user_id=None):
    order = db.session.get(Order, order_id)
    if not order or order.status != "DISPATCHED":
        raise OrderWorkflowError(f"Cannot transition to in-transit from status '{order.status if order else None}'.")

    order.status = "IN_TRANSIT"
    if order.robot:
        order.robot.status = "DELIVERING"
        order.robot.last_location = f"En Route to {order.room_name}"
        order.robot.last_seen = utc_now()
    db.session.commit()
    log_audit("ORDER_IN_TRANSIT", "Order", order.order_number, f"Robot en route to {order.room_name}", user_id)
    return order


def arrive_at_destination(order_id, user_id=None):
    order = db.session.get(Order, order_id)
    if not order or order.status != "IN_TRANSIT":
        raise OrderWorkflowError(f"Cannot transition to awaiting recipient from status '{order.status if order else None}'.")

    order.status = "AWAITING_RECIPIENT"
    if order.robot:
        order.robot.status = "AWAITING_RECIPIENT"
        order.robot.last_location = order.room_name
        order.robot.last_seen = utc_now()
    db.session.commit()
    log_audit("ORDER_ARRIVED", "Order", order.order_number, f"Robot arrived at {order.room_name}, awaiting recipient collection", user_id)
    return order


def confirm_recipient_delivered(order_id, user_id=None):
    order = db.session.get(Order, order_id)
    if not order or order.status != "AWAITING_RECIPIENT":
        raise OrderWorkflowError(f"Cannot confirm delivery from status '{order.status if order else None}'.")

    order.status = "DELIVERED"
    order.delivered_at = utc_now()
    if order.robot:
        order.robot.status = "RETURNING"
        order.robot.last_location = f"Leaving {order.room_name}"
        order.robot.last_seen = utc_now()
    db.session.commit()
    log_audit("ORDER_DELIVERED", "Order", order.order_number, f"Medicines collected by recipient at {order.room_name}. Box closed.", user_id)
    return order


def start_returning_trip(order_id, user_id=None):
    order = db.session.get(Order, order_id)
    if not order or order.status != "DELIVERED":
        raise OrderWorkflowError(f"Cannot set returning from status '{order.status if order else None}'.")

    order.status = "RETURNING"
    if order.robot:
        order.robot.status = "RETURNING"
        order.robot.last_location = "Corridor (Returning to Medicine Room)"
        order.robot.last_seen = utc_now()
    db.session.commit()
    log_audit("ORDER_RETURNING", "Order", order.order_number, "Robot returning to Medicine Room", user_id)
    return order


def confirm_returned_trip(order_id, user_id=None):
    order = db.session.get(Order, order_id)
    if not order or order.status != "RETURNING":
        raise OrderWorkflowError(f"Cannot confirm returned from status '{order.status if order else None}'.")

    order.status = "RETURNED"
    order.returned_at = utc_now()
    if order.robot:
        confirm_robot_return(order.robot.id, user_id=user_id)
    db.session.commit()
    log_audit("ORDER_RETURNED", "Order", order.order_number, "Robot safely returned to Medicine Room. Delivery cycle complete.", user_id)
    return order


def cancel_order(order_id, user_id, reason="Cancelled"):
    order = db.session.get(Order, order_id)
    if not order:
        raise OrderWorkflowError("Order not found.")

    if order.status in ["DISPATCHED", "IN_TRANSIT", "AWAITING_RECIPIENT", "DELIVERED", "RETURNING", "RETURNED"]:
        raise OrderWorkflowError("Cannot cancel an order that has already been dispatched. Stock has already been deducted.")

    if order.status in ["REJECTED", "CANCELLED"]:
        raise OrderWorkflowError(f"Order is already {order.status.lower()}.")

    # Release reservations
    release_order_reservation(order, user_id=user_id, reason=reason)

    # Unassign robot if one was assigned
    if order.robot_id:
        unassign_robot(order.robot_id, user_id=user_id)
        order.robot_id = None

    order.status = "CANCELLED"
    order.manager_notes = (order.manager_notes or "") + f" [Cancellation Reason: {reason}]"
    db.session.commit()

    log_audit("ORDER_CANCELLED", "Order", order.order_number, f"Order cancelled: {reason}", user_id)
    return order
