import pytest
from models import db, Medicine, User, Order
from services.order_service import (
    create_order,
    accept_order,
    start_preparing_order,
    mark_ready_for_loading,
    assign_robot,
    confirm_medicines_loaded,
    confirm_box_secured,
    complete_and_dispatch_order,
    cancel_order,
    OrderWorkflowError,
)
from services.inventory_service import InventoryError


def test_b_zero_stock_cannot_be_ordered():
    """
    Test B: A medicine with zero available stock is shown as UNAVAILABLE and cannot be ordered.
    """
    m_zero = Medicine.query.filter_by(name="Morphine 10mg").first()
    assert m_zero.available_quantity == 0
    assert m_zero.stock_status == "UNAVAILABLE"
    assert not m_zero.is_available

    user = User.query.filter_by(username="emergency").first()

    with pytest.raises(InventoryError) as exc_info:
        create_order(
            user=user,
            room_name="Emergency Ward / OT",
            items_data=[{"medicine_id": m_zero.id, "quantity": 1}],
        )

    assert "Insufficient stock" in str(exc_info.value)


def test_c_stock_reservation_limit():
    """
    Test C: If only five units are available, two simultaneous/consecutive orders
    cannot reserve four units each.
    """
    m_lim = Medicine.query.filter_by(name="Limited Drug").first()
    assert m_lim.available_quantity == 5

    user_ward1 = User.query.filter_by(username="ward1").first()
    user_ward2 = User.query.filter_by(username="ward2").first()

    # First order: reserves 4 units
    order1 = create_order(
        user=user_ward1,
        room_name="General Ward 1",
        items_data=[{"medicine_id": m_lim.id, "quantity": 4}],
    )
    assert order1 is not None

    m_lim = Medicine.query.filter_by(name="Limited Drug").first()
    assert m_lim.reserved_quantity == 4
    assert m_lim.available_quantity == 1

    # Second order: attempts to reserve 4 units (only 1 available) -> must fail
    with pytest.raises(InventoryError) as exc_info:
        create_order(
            user=user_ward2,
            room_name="General Ward 2",
            items_data=[{"medicine_id": m_lim.id, "quantity": 4}],
        )

    assert "Insufficient stock" in str(exc_info.value)
    # Ensure reservations did not get corrupted
    m_lim = Medicine.query.filter_by(name="Limited Drug").first()
    assert m_lim.reserved_quantity == 4
    assert m_lim.available_quantity == 1


def test_h_and_i_dispatch_inventory_deduction_and_duplicate_protection():
    """
    Test H: When the manager clicks Complete to confirm dispatch, stock is deducted exactly once.
    Test I: Double-clicking Complete or repeating same dispatch request does not deduct stock twice.
    """
    med = Medicine.query.filter_by(name="Epinephrine 1mg").first()
    initial_physical = med.physical_stock  # 50
    user = User.query.filter_by(username="emergency").first()
    mgr = User.query.filter_by(username="manager").first()

    order = create_order(
        user=user,
        room_name="Emergency Ward / OT",
        items_data=[{"medicine_id": med.id, "quantity": 5}],
    )

    med = db.session.get(Medicine, med.id)
    assert med.physical_stock == initial_physical
    assert med.reserved_quantity == 5
    assert med.available_quantity == initial_physical - 5

    # Progress through lifecycle:
    accept_order(order.id, mgr.id)
    start_preparing_order(order.id, mgr.id)
    mark_ready_for_loading(order.id, mgr.id)
    assign_robot(order.id, robot_id=1, user_id=mgr.id)
    confirm_medicines_loaded(order.id, mgr.id)
    confirm_box_secured(order.id, mgr.id)

    # Dispatch: Complete
    dispatched_order = complete_and_dispatch_order(order.id, mgr.id)
    assert dispatched_order.status == "DISPATCHED"

    # Verify inventory deducted exactly once
    med = db.session.get(Medicine, med.id)
    assert med.physical_stock == initial_physical - 5
    assert med.reserved_quantity == 0
    assert med.available_quantity == initial_physical - 5

    # Test I: Duplicate dispatch request protection
    with pytest.raises(OrderWorkflowError) as exc_info:
        complete_and_dispatch_order(order.id, mgr.id)

    assert "already been dispatched" in str(exc_info.value).lower()
    # Physical stock must remain 45, not 40
    med = db.session.get(Medicine, med.id)
    assert med.physical_stock == initial_physical - 5


def test_j_cancellation_releases_reservation_without_physical_deduction():
    """
    Test J: Cancelling an eligible pre-dispatch order releases its reservation
    without deducting physical stock.
    """
    med = Medicine.query.filter_by(name="Normal Saline 500ml").first()
    initial_physical = med.physical_stock
    user = User.query.filter_by(username="ward1").first()

    order = create_order(
        user=user,
        room_name="General Ward 1",
        items_data=[{"medicine_id": med.id, "quantity": 10}],
    )

    med = db.session.get(Medicine, med.id)
    assert med.reserved_quantity == 10
    assert med.available_quantity == initial_physical - 10

    # Cancel order
    cancel_order(order.id, user_id=user.id, reason="Doctor cancelled order")

    # Verify reservation is released
    med = db.session.get(Medicine, med.id)
    assert med.physical_stock == initial_physical
    assert med.reserved_quantity == 0
    assert med.available_quantity == initial_physical
    assert order.status == "CANCELLED"
