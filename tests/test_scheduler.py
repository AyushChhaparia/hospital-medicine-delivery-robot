import time
from datetime import timedelta
from models import db, Medicine, User, Order, utc_now
from services.order_service import create_order
from services.scheduler_service import get_active_orders_queue


def test_d_priority_ordering():
    """
    Test D: If an Emergency Ward order, a General Ward 1 order and a General Ward 2 order
    are all eligible and waiting, the Emergency Ward order is prioritized first (pos 1),
    then General Ward 1 (pos 2), then General Ward 2 (pos 3).
    """
    med = Medicine.query.filter_by(name="Normal Saline 500ml").first()
    u_emerg = User.query.filter_by(username="emergency").first()
    u_ward1 = User.query.filter_by(username="ward1").first()
    u_ward2 = User.query.filter_by(username="ward2").first()

    # Create General Ward 2 order first in time
    ord_w2 = create_order(u_ward2, "General Ward 2", [{"medicine_id": med.id, "quantity": 1}])
    # Create General Ward 1 order second
    ord_w1 = create_order(u_ward1, "General Ward 1", [{"medicine_id": med.id, "quantity": 1}])
    # Create Emergency Ward order third (latest in time)
    ord_em = create_order(u_emerg, "Emergency Ward / OT", [{"medicine_id": med.id, "quantity": 1}])

    queue = get_active_orders_queue()
    assert len(queue) == 3

    # Position 1 must be Emergency Ward (Priority 1)
    assert queue[0]["order_number"] == ord_em.order_number
    assert queue[0]["priority"] == 1
    assert queue[0]["position"] == 1

    # Position 2 must be General Ward 1 (Priority 2)
    assert queue[1]["order_number"] == ord_w1.order_number
    assert queue[1]["priority"] == 2
    assert queue[1]["position"] == 2

    # Position 3 must be General Ward 2 (Priority 3)
    assert queue[2]["order_number"] == ord_w2.order_number
    assert queue[2]["priority"] == 3
    assert queue[2]["position"] == 3


def test_e_fifo_tie_breaking_same_room():
    """
    Test E: Two eligible orders from the same room are processed in creation order (FIFO).
    """
    med = Medicine.query.filter_by(name="Normal Saline 500ml").first()
    u_ward1 = User.query.filter_by(username="ward1").first()

    ord1 = create_order(u_ward1, "General Ward 1", [{"medicine_id": med.id, "quantity": 1}])
    # Force created_at offset to simulate time order
    ord1.created_at = utc_now() - timedelta(minutes=5)
    db.session.commit()

    ord2 = create_order(u_ward1, "General Ward 1", [{"medicine_id": med.id, "quantity": 2}])
    ord2.created_at = utc_now()
    db.session.commit()

    queue = get_active_orders_queue()

    # Find the positions of ord1 and ord2 in the queue
    positions = {q["order_number"]: q["position"] for q in queue}

    assert positions[ord1.order_number] < positions[ord2.order_number]
