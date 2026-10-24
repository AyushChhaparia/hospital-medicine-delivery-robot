import pytest
from app import create_app
from config import TestConfig
from models import db, User, Medicine, Robot, SystemSetting


@pytest.fixture
def app():
    app = create_app(TestConfig)
    return app


@pytest.fixture(autouse=True)
def app_context(app):
    with app.app_context():
        db.create_all()

        # Seed system priorities
        SystemSetting.set_value("priority_emergency", "1")
        SystemSetting.set_value("priority_general_1", "2")
        SystemSetting.set_value("priority_general_2", "3")

        # Seed users
        emergency_user = User(username="emergency", role="emergency", room_name="Emergency Ward / OT", active=True)
        emergency_user.set_password("emergency123")
        db.session.add(emergency_user)

        ward1_user = User(username="ward1", role="general_1", room_name="General Ward 1", active=True)
        ward1_user.set_password("ward123")
        db.session.add(ward1_user)

        ward2_user = User(username="ward2", role="general_2", room_name="General Ward 2", active=True)
        ward2_user.set_password("ward123")
        db.session.add(ward2_user)

        manager_user = User(username="manager", role="medicine_manager", room_name="Central Medicine Room", active=True)
        manager_user.set_password("manager123")
        db.session.add(manager_user)

        admin_user = User(username="admin", role="admin", room_name="Hospital Administration", active=True)
        admin_user.set_password("admin123")
        db.session.add(admin_user)

        # Seed robots
        r1 = Robot(robot_code="R1", display_name="Robot 1", active=True, status="AVAILABLE", last_location="Medicine Room")
        r2 = Robot(robot_code="R2", display_name="Robot 2", active=True, status="AVAILABLE", last_location="Medicine Room")
        db.session.add_all([r1, r2])

        # Seed test medicines
        m1 = Medicine(name="Epinephrine 1mg", category="Emergency", unit="ampoules", physical_stock=50, reserved_quantity=0, reorder_threshold=10, active=True)
        m2 = Medicine(name="Normal Saline 500ml", category="IV Fluids", unit="bottles", physical_stock=100, reserved_quantity=0, reorder_threshold=20, active=True)
        m_zero = Medicine(name="Morphine 10mg", category="Narcotics", unit="ampoules", physical_stock=0, reserved_quantity=0, reorder_threshold=5, active=True)
        m_limited = Medicine(name="Limited Drug", category="Special", unit="vials", physical_stock=5, reserved_quantity=0, reorder_threshold=2, active=True)

        db.session.add_all([m1, m2, m_zero, m_limited])
        db.session.commit()

        yield app

        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
