from models import db, Robot, Order, utc_now
from services.audit_service import log_audit


class RobotError(Exception):
    pass


def get_all_robots():
    return Robot.query.order_by(Robot.id.asc()).all()


def get_available_robots():
    """
    Returns robots that are active, status == 'AVAILABLE', and have no current_order_id.
    """
    return Robot.query.filter_by(active=True, status="AVAILABLE", current_order_id=None).all()


def assign_robot_to_order(robot_id, order, user_id=None):
    """
    Assign an available robot to an eligible order.
    """
    robot = db.session.get(Robot, robot_id)
    if not robot:
        raise RobotError(f"Robot with ID {robot_id} not found.")

    if not robot.active:
        raise RobotError(f"Robot {robot.robot_code} is inactive and cannot be assigned.")

    if robot.status != "AVAILABLE" or robot.current_order_id is not None:
        raise RobotError(
            f"Robot {robot.robot_code} ({robot.display_name}) is currently {robot.status} (Busy) and cannot be assigned."
        )

    # Validate order eligibility
    if order.status not in ["ACCEPTED", "PREPARING", "READY_FOR_LOADING"]:
        raise RobotError(
            f"Order {order.order_number} is in status '{order.status}' and cannot be assigned to a robot."
        )

    if order.robot_id and order.robot_id != robot.id:
        # Unassign previous robot if any and reset its status
        prev_robot = db.session.get(Robot, order.robot_id)
        if prev_robot:
            prev_robot.status = "AVAILABLE"
            prev_robot.current_order_id = None

    robot.status = "ASSIGNED"
    robot.current_order_id = order.id
    order.robot_id = robot.id

    log_audit(
        action="ROBOT_ASSIGNED",
        entity_type="Robot",
        entity_id=robot.robot_code,
        details=f"Assigned {robot.display_name} to Order {order.order_number} for {order.room_name}",
        user_id=user_id,
    )
    return robot


def unassign_robot(robot_id, user_id=None):
    """
    Unassign robot if order is cancelled or re-assigned before dispatch.
    """
    robot = db.session.get(Robot, robot_id)
    if robot:
        robot.status = "AVAILABLE"
        robot.current_order_id = None
        log_audit(
            action="ROBOT_UNASSIGNED",
            entity_type="Robot",
            entity_id=robot.robot_code,
            details=f"Unassigned {robot.display_name}",
            user_id=user_id,
        )


def confirm_robot_return(robot_id, user_id=None):
    """
    Confirm robot has returned to the Medicine Room.
    Marks robot AVAILABLE, clears current_order_id, updates location.
    """
    robot = db.session.get(Robot, robot_id)
    if not robot:
        raise RobotError(f"Robot with ID {robot_id} not found.")

    robot.status = "AVAILABLE"
    robot.last_location = "Medicine Room"
    robot.last_seen = utc_now()
    order_id = robot.current_order_id
    robot.current_order_id = None

    log_audit(
        action="ROBOT_RETURNED_CONFIRMED",
        entity_type="Robot",
        entity_id=robot.robot_code,
        details=f"{robot.display_name} confirmed returned to Medicine Room and is now AVAILABLE",
        user_id=user_id,
    )
    return robot


def update_robot_telemetry(robot_code, status=None, location=None, battery=None):
    """
    Helper for future ESP32 robot heartbeat / status updates.
    """
    robot = Robot.query.filter_by(robot_code=robot_code).first()
    if not robot:
        raise RobotError(f"Robot code '{robot_code}' not found.")

    if status:
        robot.status = status
    if location:
        robot.last_location = location
    if battery is not None:
        try:
            robot.battery_percentage = max(0, min(100, int(battery)))
        except (ValueError, TypeError):
            pass
    robot.last_seen = utc_now()
    db.session.commit()
    return robot
