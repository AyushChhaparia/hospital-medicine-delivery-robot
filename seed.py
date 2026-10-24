import os
import secrets

from models import db, User, Medicine, Robot, SystemSetting
from config import Config
from app import create_app
from services.audit_service import log_audit


def demo_password(username):
    environment_name = f"DEMO_{username.upper()}_PASSWORD"
    password = os.environ.get(environment_name) or secrets.token_urlsafe(12)
    print(f"Demo password for {username}: {password}")
    return password


def seed_all():
    print("Seeding database...")

    # 1. System Settings for Room Priorities
    priorities = [
        ("priority_emergency", "1"),
        ("priority_general_1", "2"),
        ("priority_general_2", "3"),
    ]
    for key, val in priorities:
        if not SystemSetting.query.filter_by(setting_key=key).first():
            setting = SystemSetting(setting_key=key, setting_value=val)
            db.session.add(setting)

    # 2. User Accounts
    users_data = [
        {
            "username": "admin",
            "password": demo_password("admin"),
            "role": "admin",
            "room_name": "Hospital Administration",
        },
        {
            "username": "manager",
            "password": demo_password("manager"),
            "role": "medicine_manager",
            "room_name": "Central Medicine Room",
        },
        {
            "username": "emergency",
            "password": demo_password("emergency"),
            "role": "emergency",
            "room_name": "Emergency Ward / OT",
        },
        {
            "username": "ward1",
            "password": demo_password("ward1"),
            "role": "general_1",
            "room_name": "General Ward 1",
        },
        {
            "username": "ward2",
            "password": demo_password("ward2"),
            "role": "general_2",
            "room_name": "General Ward 2",
        },
    ]

    for u_info in users_data:
        existing = User.query.filter_by(username=u_info["username"]).first()
        if not existing:
            user = User(
                username=u_info["username"],
                role=u_info["role"],
                room_name=u_info["room_name"],
                active=True,
            )
            user.set_password(u_info["password"])
            db.session.add(user)
            print(f"Created user: {user.username} ({user.role})")

    # 3. Two Initial Robots R1 & R2
    robots_data = [
        {
            "robot_code": "R1",
            "display_name": "Autonomous Robot R1 (Primary)",
            "active": True,
            "status": "AVAILABLE",
            "last_location": "Medicine Room",
            "battery_percentage": 96,
        },
        {
            "robot_code": "R2",
            "display_name": "Autonomous Robot R2 (Secondary)",
            "active": True,
            "status": "AVAILABLE",
            "last_location": "Medicine Room",
            "battery_percentage": 88,
        },
    ]

    for r_info in robots_data:
        existing_bot = Robot.query.filter_by(robot_code=r_info["robot_code"]).first()
        if not existing_bot:
            bot = Robot(
                robot_code=r_info["robot_code"],
                display_name=r_info["display_name"],
                active=r_info["active"],
                status=r_info["status"],
                last_location=r_info["last_location"],
                battery_percentage=r_info["battery_percentage"],
            )
            db.session.add(bot)
            print(f"Created robot: {bot.robot_code} - {bot.display_name}")

    # 4. Hospital Medicines Catalogue
    medicines_data = [
        {
            "name": "Epinephrine (Adrenaline) 1mg/ml",
            "category": "Emergency & Critical Care",
            "description": "Essential emergency medication for cardiac arrest and anaphylaxis.",
            "unit": "ampoules",
            "physical_stock": 50,
            "reserved_quantity": 0,
            "reorder_threshold": 10,
        },
        {
            "name": "Atropine Sulfate 0.6mg/ml",
            "category": "Emergency & Critical Care",
            "description": "Indicated in bradycardia and organophosphate poisoning.",
            "unit": "ampoules",
            "physical_stock": 35,
            "reserved_quantity": 0,
            "reorder_threshold": 10,
        },
        {
            "name": "Normal Saline (0.9% NaCl) 500ml",
            "category": "IV Fluids",
            "description": "Sterile isotonic crystalloid fluid for resuscitation and hydration.",
            "unit": "bottles",
            "physical_stock": 100,
            "reserved_quantity": 0,
            "reorder_threshold": 25,
        },
        {
            "name": "Dextrose 5% in Water 500ml",
            "category": "IV Fluids",
            "description": "Hypotonic hydration solution and carbohydrate calorie source.",
            "unit": "bottles",
            "physical_stock": 80,
            "reserved_quantity": 0,
            "reorder_threshold": 20,
        },
        {
            "name": "Paracetamol 1000mg/100ml IV",
            "category": "Analgesics & Antipyretics",
            "description": "Fast-acting IV antipyretic and analgesic for postoperative pain.",
            "unit": "bottles",
            "physical_stock": 60,
            "reserved_quantity": 0,
            "reorder_threshold": 15,
        },
        {
            "name": "Tramadol 50mg/ml Injection",
            "category": "Analgesics & Antipyretics",
            "description": "Moderate to severe pain management.",
            "unit": "ampoules",
            "physical_stock": 30,
            "reserved_quantity": 0,
            "reorder_threshold": 10,
        },
        {
            "name": "Amoxicillin / Clavulanate 1.2g IV",
            "category": "Antibiotics",
            "description": "Broad-spectrum co-amoxiclav for bacterial infections.",
            "unit": "vials",
            "physical_stock": 45,
            "reserved_quantity": 0,
            "reorder_threshold": 12,
        },
        {
            "name": "Ceftriaxone 1g Injection",
            "category": "Antibiotics",
            "description": "Third-generation cephalosporin for severe systemic infections.",
            "unit": "vials",
            "physical_stock": 50,
            "reserved_quantity": 0,
            "reorder_threshold": 15,
        },
        {
            "name": "Furosemide 20mg/2ml Injection",
            "category": "Cardiovascular",
            "description": "Potent loop diuretic for acute pulmonary edema and fluid overload.",
            "unit": "ampoules",
            "physical_stock": 40,
            "reserved_quantity": 0,
            "reorder_threshold": 10,
        },
        {
            "name": "Salbutamol 2.5mg Respirator Nebules",
            "category": "Respiratory",
            "description": "Bronchodilator for acute asthma and bronchospasm.",
            "unit": "packets",
            "physical_stock": 55,
            "reserved_quantity": 0,
            "reorder_threshold": 12,
        },
        {
            "name": "Heparin Sodium 5000 IU/ml",
            "category": "Anticoagulants",
            "description": "Injectable anticoagulant for thrombosis prevention.",
            "unit": "vials",
            "physical_stock": 4,  # Below threshold 10 -> tests LOW STOCK status
            "reserved_quantity": 0,
            "reorder_threshold": 10,
        },
        {
            "name": "Morphine Sulfate 10mg/ml",
            "category": "Controlled Narcotics",
            "description": "Potent narcotic analgesic. Currently out of stock.",
            "unit": "ampoules",
            "physical_stock": 0,  # Zero stock -> tests UNAVAILABLE status
            "reserved_quantity": 0,
            "reorder_threshold": 5,
        },
    ]

    for m_info in medicines_data:
        existing_med = Medicine.query.filter_by(name=m_info["name"]).first()
        if not existing_med:
            med = Medicine(
                name=m_info["name"],
                category=m_info["category"],
                description=m_info["description"],
                unit=m_info["unit"],
                physical_stock=m_info["physical_stock"],
                reserved_quantity=m_info["reserved_quantity"],
                reorder_threshold=m_info["reorder_threshold"],
                active=True,
            )
            db.session.add(med)
            print(f"Created medicine: {med.name} ({med.physical_stock} {med.unit})")

    db.session.commit()
    log_audit("SYSTEM_INITIALIZED", "System", "1", "Database seeded with default demo data and accounts.")
    print("Database seeding completed successfully.")


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
        seed_all()
