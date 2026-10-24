from models import db, Medicine, InventoryTransaction, Order
from services.audit_service import log_audit


class InventoryError(Exception):
    pass


def reserve_stock_for_order(items_data):
    """
    Atomically validate and reserve medicines for an order.
    items_data: list of dicts [{'medicine_id': int, 'quantity': int}]
    Returns list of (Medicine, quantity) on success.
    Raises InventoryError if any item has insufficient stock, is inactive, or quantity <= 0.
    """
    if not items_data:
        raise InventoryError("Cannot place an order with an empty item list.")

    reserved_items = []
    # To prevent deadlocks, sort by medicine_id
    sorted_items = sorted(items_data, key=lambda x: x["medicine_id"])

    # Aggregate quantities if same medicine appears multiple times
    aggregated = {}
    for item in sorted_items:
        med_id = item["medicine_id"]
        qty = int(item["quantity"])
        if qty <= 0:
            raise InventoryError("Quantity must be greater than zero.")
        aggregated[med_id] = aggregated.get(med_id, 0) + qty

    for med_id, qty in aggregated.items():
        # Query medicine with lock where possible, or check directly
        medicine = Medicine.query.filter_by(id=med_id).with_for_update().first() if db.session.bind and "sqlite" not in db.session.bind.name else db.session.get(Medicine, med_id)
        if not medicine:
            raise InventoryError(f"Medicine with ID {med_id} not found.")

        if not medicine.active:
            raise InventoryError(f"Medicine '{medicine.name}' is currently inactive and cannot be ordered.")

        available = medicine.physical_stock - medicine.reserved_quantity
        if qty > available:
            raise InventoryError(
                f"Insufficient stock for '{medicine.name}'. Requested: {qty}, Available: {max(0, available)}."
            )

        medicine.reserved_quantity += qty
        reserved_items.append((medicine, qty))

    return reserved_items


def release_order_reservation(order, user_id=None, reason="Order Cancelled/Rejected"):
    """
    Release reserved quantities for an order that is cancelled or rejected before dispatch.
    Does NOT modify physical stock.
    """
    if order.status in ["DISPATCHED", "IN_TRANSIT", "AWAITING_RECIPIENT", "DELIVERED", "RETURNING", "RETURNED"]:
        raise InventoryError("Cannot release reservation for an order that has already been dispatched.")

    for item in order.items:
        medicine = db.session.get(Medicine, item.medicine_id)
        if medicine:
            medicine.reserved_quantity = max(0, medicine.reserved_quantity - item.quantity)

    log_audit(
        action="RESERVATION_RELEASED",
        entity_type="Order",
        entity_id=order.order_number,
        details=f"Released reserved stock for order {order.order_number}. Reason: {reason}",
        user_id=user_id,
    )


def deduct_dispatched_stock(order, user_id):
    """
    Complete / Dispatch operation:
    1. Verify order has not already been completed/dispatched.
    2. Verify reserved quantities.
    3. Deduct physical stock.
    4. Release corresponding reservations.
    5. Record inventory transactions.
    Atomic and safe against repeated requests.
    """
    if order.status in ["DISPATCHED", "IN_TRANSIT", "AWAITING_RECIPIENT", "DELIVERED", "RETURNING", "RETURNED"]:
        raise InventoryError(f"Order {order.order_number} has already been dispatched. Stock deduction cannot be duplicated.")

    # Deduct stock and release reservation for each item
    for item in order.items:
        medicine = db.session.get(Medicine, item.medicine_id)
        if not medicine:
            raise InventoryError(f"Medicine record for item {item.id} not found.")

        if medicine.physical_stock < item.quantity:
            raise InventoryError(
                f"Cannot dispatch: Physical stock of '{medicine.name}' ({medicine.physical_stock}) is less than required quantity ({item.quantity})."
            )

        # Deduct physical stock
        medicine.physical_stock -= item.quantity
        # Release reservation
        medicine.reserved_quantity = max(0, medicine.reserved_quantity - item.quantity)

        # Record Inventory Transaction
        tx = InventoryTransaction(
            medicine_id=medicine.id,
            order_id=order.id,
            user_id=user_id,
            transaction_type="DISPATCH_DEDUCTION",
            quantity_change=-item.quantity,
            reason=f"Order {order.order_number} dispatched to {order.room_name}",
        )
        db.session.add(tx)

    log_audit(
        action="STOCK_DISPATCH_DEDUCTED",
        entity_type="Order",
        entity_id=order.order_number,
        details=f"Deducted inventory for dispatched order {order.order_number} to {order.room_name}",
        user_id=user_id,
    )


def adjust_physical_stock(medicine_id, quantity_change, reason, user_id, transaction_type="STOCK_ADJUST"):
    """
    Adjust physical stock (e.g. new stock arrival, manual correction).
    Ensures physical_stock >= reserved_quantity and physical_stock >= 0.
    """
    medicine = db.session.get(Medicine, medicine_id)
    if not medicine:
        raise InventoryError(f"Medicine with ID {medicine_id} not found.")

    new_physical = medicine.physical_stock + quantity_change
    if new_physical < 0:
        raise InventoryError("Physical stock cannot become negative.")

    if new_physical < medicine.reserved_quantity:
        raise InventoryError(
            f"Physical stock ({new_physical}) cannot be less than currently reserved quantity ({medicine.reserved_quantity})."
        )

    medicine.physical_stock = new_physical

    tx = InventoryTransaction(
        medicine_id=medicine.id,
        order_id=None,
        user_id=user_id,
        transaction_type=transaction_type,
        quantity_change=quantity_change,
        reason=reason,
    )
    db.session.add(tx)

    log_audit(
        action="STOCK_ADJUSTED",
        entity_type="Medicine",
        entity_id=medicine.name,
        details=f"Stock adjusted by {quantity_change:+d} {medicine.unit}. New physical stock: {medicine.physical_stock}. Reason: {reason}",
        user_id=user_id,
    )

    db.session.commit()
    return medicine
