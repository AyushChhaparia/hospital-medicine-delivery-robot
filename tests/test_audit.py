import pytest
from models import db, AuditLog, Medicine, User, Robot
from services.inventory_service import adjust_physical_stock
from services.order_service import create_order, accept_order, assign_robot


def test_m_audit_logging_of_critical_actions():
    """
    Test M: Important stock, order, and robot assignment actions are recorded
    with responsible user and timestamp.
    """
    user_emerg = User.query.filter_by(username="emergency").first()
    user_mgr = User.query.filter_by(username="manager").first()
    med = Medicine.query.filter_by(name="Normal Saline 500ml").first()
    bot = Robot.query.filter_by(robot_code="R1").first()

    # 1. Order creation logs audit
    order = create_order(user_emerg, "Emergency Ward / OT", [{"medicine_id": med.id, "quantity": 2}])
    log_order = AuditLog.query.filter_by(action="ORDER_CREATED", entity_id=order.order_number).first()
    assert log_order is not None
    assert log_order.user_id == user_emerg.id

    # 2. Stock adjustment logs audit
    adjust_physical_stock(med.id, 10, "Shipment arrival", user_mgr.id)
    log_stock = AuditLog.query.filter_by(action="STOCK_ADJUSTED", entity_id=med.name).first()
    assert log_stock is not None
    assert log_stock.user_id == user_mgr.id
    assert "Shipment arrival" in log_stock.details

    # 3. Robot assignment logs audit
    accept_order(order.id, user_mgr.id)
    assign_robot(order.id, bot.id, user_mgr.id)
    log_robot = AuditLog.query.filter_by(action="ROBOT_ASSIGNED", entity_id=bot.robot_code).first()
    assert log_robot is not None
    assert log_robot.user_id == user_mgr.id


def test_l_responsive_ui_templates(client):
    """
    Test L: Responsive UI: Template includes responsive viewport tags, touch targets, and mobile layout.
    """
    # Login as emergency user
    client.post("/login", data={"username": "emergency", "password": "emergency123"})
    res = client.get("/ward/emergency")
    assert res.status_code == 200

    html = res.data.decode("utf-8")
    assert '<meta name="viewport" content="width=device-width, initial-scale=1.0">' in html
    assert 'ordering-grid' in html
    assert 'medicine-item-card' in html
    assert 'qty-input' in html
    assert 'submitOrderWithConfirmation' in html


def test_esp32_robot_api_integration_interface(client, app):
    """
    Test ESP32 API endpoints for future hardware integration.
    """
    token = app.config["ROBOT_API_TOKEN"]

    # 1. Unauthorized request without token
    res = client.get("/api/robot/R1/assignment")
    assert res.status_code == 401

    # 2. Authorized idle query
    res = client.get("/api/robot/R1/assignment", headers={"X-Robot-Token": token})
    assert res.status_code == 200
    data = res.get_json()
    assert data["robot_code"] == "R1"
    assert data["status"] == "idle"

    # 3. Heartbeat telemetry
    res_hb = client.post("/api/robot/R1/heartbeat", headers={"X-Robot-Token": token}, json={
        "status": "AVAILABLE",
        "location": "Node A1",
        "battery": 92
    })
    assert res_hb.status_code == 200
    hb_data = res_hb.get_json()
    assert hb_data["battery"] == 92
    assert hb_data["last_location"] == "Node A1"
