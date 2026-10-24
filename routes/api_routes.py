from functools import wraps
from flask import Blueprint, request, jsonify, current_app
from models import db, Robot, Order, utc_now
from services.robot_service import update_robot_telemetry, confirm_robot_return
from services.order_service import (
    transit_delivery,
    arrive_at_destination,
    confirm_recipient_delivered,
    confirm_returned_trip,
    OrderWorkflowError,
)
from services.audit_service import log_audit

api_bp = Blueprint("api", __name__, url_prefix="/api/robot")


def robot_auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-Robot-Token") or request.headers.get("Authorization")
        if token and token.startswith("Bearer "):
            token = token.split(" ", 1)[1]

        expected_token = current_app.config["ROBOT_API_TOKEN"]
        if not token or token != expected_token:
            return jsonify({
                "status": "error",
                "message": "Unauthorized: Invalid or missing robot authentication token."
            }), 401
        return f(*args, **kwargs)
    return decorated


@api_bp.route("/<robot_code>/assignment", methods=["GET"])
@robot_auth_required
def get_assignment(robot_code):
    """
    ESP32 query: Robot requests its current assignment, destination, and medicine manifest.
    """
    robot = Robot.query.filter_by(robot_code=robot_code).first()
    if not robot:
        return jsonify({"status": "error", "message": f"Robot {robot_code} not found."}), 404

    robot.last_seen = utc_now()
    db.session.commit()

    if not robot.current_order:
        return jsonify({
            "status": "idle",
            "robot_code": robot.robot_code,
            "state": robot.status,
            "has_assignment": False,
            "message": "No active order assigned to this robot.",
        })

    order = robot.current_order
    items = [{
        "medicine": item.medicine.name,
        "quantity": item.quantity,
        "unit": item.unit
    } for item in order.items]

    return jsonify({
        "status": "assigned",
        "robot_code": robot.robot_code,
        "state": robot.status,
        "has_assignment": True,
        "order": {
            "order_id": order.id,
            "order_number": order.order_number,
            "destination_room": order.room_name,
            "priority": order.priority,
            "status": order.status,
            "items": items,
        }
    })


@api_bp.route("/<robot_code>/heartbeat", methods=["POST"])
@robot_auth_required
def heartbeat(robot_code):
    """
    ESP32 telemetry report: battery percentage, status, location node.
    """
    data = request.get_json() or {}
    status = data.get("status")
    location = data.get("location")
    battery = data.get("battery")

    try:
        robot = update_robot_telemetry(robot_code, status=status, location=location, battery=battery)
        return jsonify({
            "status": "success",
            "robot_code": robot.robot_code,
            "acknowledged_state": robot.status,
            "battery": robot.battery_percentage,
            "last_location": robot.last_location,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@api_bp.route("/<robot_code>/rfid_node", methods=["POST"])
@robot_auth_required
def report_rfid_node(robot_code):
    """
    ESP32 reports RFID-confirmed waypoint node during line following navigation.
    """
    data = request.get_json() or {}
    node_id = data.get("node_id", "Unknown Node")
    node_label = data.get("node_label", node_id)

    robot = Robot.query.filter_by(robot_code=robot_code).first()
    if not robot:
        return jsonify({"status": "error", "message": "Robot not found"}), 404

    robot.last_location = f"Node {node_label}"
    robot.last_seen = utc_now()
    db.session.commit()

    return jsonify({"status": "success", "node_recorded": node_label})


@api_bp.route("/<robot_code>/arrived", methods=["POST"])
@robot_auth_required
def report_arrival(robot_code):
    """
    ESP32 reports physical arrival at destination ward RFID waypoint.
    """
    robot = Robot.query.filter_by(robot_code=robot_code).first()
    if not robot or not robot.current_order:
        return jsonify({"status": "error", "message": "Robot has no current delivery order."}), 400

    order = robot.current_order
    try:
        if order.status == "DISPATCHED":
            transit_delivery(order.id, user_id=None)
        if order.status in ["DISPATCHED", "IN_TRANSIT"]:
            arrive_at_destination(order.id, user_id=None)

        return jsonify({
            "status": "success",
            "message": f"Arrival acknowledged at {order.room_name}.",
            "order_status": order.status,
        })
    except OrderWorkflowError as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@api_bp.route("/<robot_code>/box_closed_delivered", methods=["POST"])
@robot_auth_required
def report_box_closed(robot_code):
    """
    ESP32 reports recipient has entered unlock code, removed medicines, and latched box.
    """
    robot = Robot.query.filter_by(robot_code=robot_code).first()
    if not robot or not robot.current_order:
        return jsonify({"status": "error", "message": "Robot has no active order."}), 400

    order = robot.current_order
    try:
        confirm_recipient_delivered(order.id, user_id=None)
        return jsonify({
            "status": "success",
            "message": "Delivery confirmed. Return trip initiated.",
            "order_status": order.status,
        })
    except OrderWorkflowError as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@api_bp.route("/<robot_code>/returned", methods=["POST"])
@robot_auth_required
def report_returned(robot_code):
    """
    ESP32 reports arrival back at Medicine Room docking station.
    """
    robot = Robot.query.filter_by(robot_code=robot_code).first()
    if not robot:
        return jsonify({"status": "error", "message": "Robot not found."}), 404

    order = robot.current_order
    if order and order.status in ["DELIVERED", "RETURNING"]:
        confirm_returned_trip(order.id, user_id=None)
    else:
        confirm_robot_return(robot.id, user_id=None)

    return jsonify({
        "status": "success",
        "message": f"Robot {robot.robot_code} safely docked and reset to AVAILABLE.",
        "robot_status": robot.status,
    })
