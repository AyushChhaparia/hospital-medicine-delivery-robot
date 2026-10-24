from models import db, Order, SystemSetting


# Default priorities
DEFAULT_ROOM_PRIORITIES = {
    "Emergency Ward / OT": 1,
    "General Ward 1": 2,
    "General Ward 2": 3,
}

# Roles to room mapping
ROLE_TO_ROOM = {
    "emergency": "Emergency Ward / OT",
    "general_1": "General Ward 1",
    "general_2": "General Ward 2",
}


def get_room_priority(room_name):
    """
    Get configured priority for a room.
    Lower number = higher priority (1 is highest).
    """
    if "Emergency" in room_name:
        val = SystemSetting.get_value("priority_emergency", "1")
    elif "General Ward 1" in room_name:
        val = SystemSetting.get_value("priority_general_1", "2")
    elif "General Ward 2" in room_name:
        val = SystemSetting.get_value("priority_general_2", "3")
    else:
        val = DEFAULT_ROOM_PRIORITIES.get(room_name, 2)

    try:
        return int(val)
    except (ValueError, TypeError):
        return 2


def get_active_orders_queue():
    """
    Returns ordered queue of active waiting/processing orders before dispatch.
    Orders with status in: PENDING, ACCEPTED, PREPARING, READY_FOR_LOADING, LOADED, READY_FOR_DISPATCH.
    Ordered by:
      1. Priority ascending (1 is highest priority)
      2. created_at ascending (FIFO)
      3. id ascending (deterministic tie-breaker)
    """
    active_statuses = [
        "PENDING",
        "ACCEPTED",
        "PREPARING",
        "READY_FOR_LOADING",
        "LOADED",
        "READY_FOR_DISPATCH",
    ]

    orders = Order.query.filter(Order.status.in_(active_statuses)).all()

    # Deterministic sorting function in Python
    # Priority (lower number first), then created_at (earliest first), then id (lowest first)
    def sort_key(order):
        return (
            order.priority,
            order.created_at,
            order.id,
        )

    sorted_orders = sorted(orders, key=sort_key)

    # Attach queue position to each order dict/object
    queue_list = []
    for position, order in enumerate(sorted_orders, start=1):
        queue_list.append({
            "position": position,
            "order": order,
            "id": order.id,
            "order_number": order.order_number,
            "room_name": order.room_name,
            "priority": order.priority,
            "status": order.status,
            "created_at": order.created_at,
            "robot_name": order.robot.display_name if order.robot else None,
            "robot_code": order.robot.robot_code if order.robot else None,
            "items_count": order.total_items_count,
            "items_summary": order.items_summary,
        })

    return queue_list


def get_next_dispatchable_order():
    """
    Selects the highest priority, earliest order that is READY_FOR_DISPATCH and has a robot assigned.
    """
    ready_orders = Order.query.filter_by(status="READY_FOR_DISPATCH").all()
    if not ready_orders:
        return None

    def sort_key(order):
        return (order.priority, order.created_at, order.id)

    sorted_ready = sorted(ready_orders, key=sort_key)
    return sorted_ready[0]


def get_next_order_for_robot_assignment():
    """
    Selects the highest priority order that needs robot assignment
    (i.e., status in ACCEPTED, PREPARING, READY_FOR_LOADING without robot_id).
    """
    unassigned = Order.query.filter(
        Order.status.in_(["ACCEPTED", "PREPARING", "READY_FOR_LOADING"]),
        Order.robot_id.is_(None),
    ).all()

    if not unassigned:
        return None

    def sort_key(order):
        return (order.priority, order.created_at, order.id)

    sorted_unassigned = sorted(unassigned, key=sort_key)
    return sorted_unassigned[0]
