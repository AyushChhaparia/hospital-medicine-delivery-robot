import pytest
from models import db, Robot, Medicine, User, Order
from services.order_service import (
    create_order,
    accept_order,
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
from services.robot_service import assign_robot_to_order, confirm_robot_return, RobotError


def test_f_robot_eligibility_and_busy_rejection():
    """
    Test F: An order cannot be assigned to an inactive, offline, unavailable or already-busy robot.
    """
    med = Medicine.query.filter_by(name="Normal Saline 500ml").first()
    u_emerg = User.query.filter_by(username="emergency").first()
    u_ward1 = User.query.filter_by(username="ward1").first()
    mgr = User.query.filter_by(username="manager").first()

    order1 = create_order(u_emerg, "Emergency Ward / OT", [{"medicine_id": med.id, "quantity": 1}])
    order2 = create_order(u_ward1, "General Ward 1", [{"medicine_id": med.id, "quantity": 1}])

    accept_order(order1.id, mgr.id)
    accept_order(order2.id, mgr.id)

    # 1. Inactive robot rejection
    r_inactive = Robot(robot_code="R_INACTIVE", display_name="Broken Bot", active=False, status="AVAILABLE")
    db.session.add(r_inactive)
    db.session.commit()

    with pytest.raises(RobotError) as exc:
        assign_robot_to_order(r_inactive.id, order1, mgr.id)
    assert "inactive" in str(exc.value).lower()

    # 2. Assign Robot 1 to Order 1
    r1 = Robot.query.filter_by(robot_code="R1").first()
    assign_robot_to_order(r1.id, order1, mgr.id)
    assert r1.status == "ASSIGNED"
    assert r1.current_order_id == order1.id

    # 3. Attempting to assign same robot (now busy) to Order 2 must fail
    with pytest.raises(RobotError) as exc:
        assign_robot_to_order(r1.id, order2, mgr.id)
    assert "busy" in str(exc.value).lower() or "cannot be assigned" in str(exc.value).lower()


def test_g_dispatch_validation_gate():
    """
    Test G: The manager cannot dispatch an order until the medicines are confirmed loaded,
    the robot is assigned, and the box is confirmed secured.
    """
    med = Medicine.query.filter_by(name="Normal Saline 500ml").first()
    u_emerg = User.query.filter_by(username="emergency").first()
    mgr = User.query.filter_by(username="manager").first()

    order = create_order(u_emerg, "Emergency Ward / OT", [{"medicine_id": med.id, "quantity": 1}])

    # 1. Cannot dispatch directly from PENDING
    with pytest.raises(OrderWorkflowError):
        complete_and_dispatch_order(order.id, mgr.id)

    # 2. Cannot dispatch from ACCEPTED
    accept_order(order.id, mgr.id)
    with pytest.raises(OrderWorkflowError):
        complete_and_dispatch_order(order.id, mgr.id)

    # 3. Cannot dispatch from PREPARING
    start_preparing_order(order.id, mgr.id)
    with pytest.raises(OrderWorkflowError):
        complete_and_dispatch_order(order.id, mgr.id)

    # 4. Cannot dispatch from READY_FOR_LOADING without loaded confirmation
    mark_ready_for_loading(order.id, mgr.id)
    with pytest.raises(OrderWorkflowError):
        complete_and_dispatch_order(order.id, mgr.id)

    # 5. Assign robot
    r1 = Robot.query.filter_by(robot_code="R1").first()
    assign_robot(order.id, r1.id, mgr.id)

    # 6. Cannot dispatch without box secured
    confirm_medicines_loaded(order.id, mgr.id)
    with pytest.raises(OrderWorkflowError):
        complete_and_dispatch_order(order.id, mgr.id)

    # 7. Secure box -> Now READY_FOR_DISPATCH -> Dispatch succeeds!
    confirm_box_secured(order.id, mgr.id)
    dispatched = complete_and_dispatch_order(order.id, mgr.id)
    assert dispatched.status == "DISPATCHED"


def test_k_robot_cannot_accept_new_order_until_return_confirmed():
    """
    Test K: A robot cannot accept a new order until its return to the Medicine Room is confirmed.
    """
    med = Medicine.query.filter_by(name="Normal Saline 500ml").first()
    u_emerg = User.query.filter_by(username="emergency").first()
    u_ward1 = User.query.filter_by(username="ward1").first()
    mgr = User.query.filter_by(username="manager").first()

    # Order 1 through full cycle
    ord1 = create_order(u_emerg, "Emergency Ward / OT", [{"medicine_id": med.id, "quantity": 1}])
    accept_order(ord1.id, mgr.id)
    start_preparing_order(ord1.id, mgr.id)
    mark_ready_for_loading(ord1.id, mgr.id)
    r1 = Robot.query.filter_by(robot_code="R1").first()
    assign_robot(ord1.id, r1.id, mgr.id)
    confirm_medicines_loaded(ord1.id, mgr.id)
    confirm_box_secured(ord1.id, mgr.id)
    complete_and_dispatch_order(ord1.id, mgr.id)

    # Delivery steps
    transit_delivery(ord1.id, mgr.id)
    arrive_at_destination(ord1.id, mgr.id)
    confirm_recipient_delivered(ord1.id, mgr.id)
    start_returning_trip(ord1.id, mgr.id)

    # Order 2 waiting for assignment
    ord2 = create_order(u_ward1, "General Ward 1", [{"medicine_id": med.id, "quantity": 1}])
    accept_order(ord2.id, mgr.id)

    # Attempting to assign R1 while it is still returning must fail
    with pytest.raises(RobotError) as exc:
        assign_robot(ord2.id, r1.id, mgr.id)
    assert "cannot be assigned" in str(exc.value).lower() or "busy" in str(exc.value).lower()

    # Now confirm return trip
    confirm_returned_trip(ord1.id, mgr.id)
    r1 = db.session.get(Robot, r1.id)
    assert r1.status == "AVAILABLE"
    assert r1.current_order_id is None

    # Now R1 can be assigned to Order 2
    ord2, r1_assigned = assign_robot(ord2.id, r1.id, mgr.id)
    assert ord2.robot_id == r1.id
    assert r1_assigned.status == "ASSIGNED"
