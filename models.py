from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


def utc_now():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False)  # admin, medicine_manager, emergency, general_1, general_2
    room_name = db.Column(db.String(100), nullable=False)  # e.g., "Emergency Ward / OT", "General Ward 1", "General Ward 2", "Medicine Room", "Administration"
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    orders = db.relationship("Order", back_populates="user", lazy=True)
    audit_logs = db.relationship("AuditLog", back_populates="user", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        return self.active

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "room_name": self.room_name,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Medicine(db.Model):
    __tablename__ = "medicines"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False, index=True)
    category = db.Column(db.String(80), nullable=False, default="General")
    description = db.Column(db.Text, nullable=True)
    unit = db.Column(db.String(30), nullable=False, default="strips")  # strips, bottles, packets, ampoules, units
    physical_stock = db.Column(db.Integer, default=0, nullable=False)
    reserved_quantity = db.Column(db.Integer, default=0, nullable=False)
    reorder_threshold = db.Column(db.Integer, default=10, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    order_items = db.relationship("OrderItem", back_populates="medicine", lazy=True)
    transactions = db.relationship("InventoryTransaction", back_populates="medicine", lazy=True)

    @property
    def available_quantity(self):
        return max(0, self.physical_stock - self.reserved_quantity)

    @property
    def is_available(self):
        return self.active and self.available_quantity > 0

    @property
    def is_low_stock(self):
        return self.active and (0 < self.available_quantity <= self.reorder_threshold)

    @property
    def stock_status(self):
        if not self.active or self.available_quantity == 0:
            return "UNAVAILABLE"
        if self.available_quantity <= self.reorder_threshold:
            return "LOW STOCK"
        return "AVAILABLE"

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description or "",
            "unit": self.unit,
            "physical_stock": self.physical_stock,
            "reserved_quantity": self.reserved_quantity,
            "available_quantity": self.available_quantity,
            "reorder_threshold": self.reorder_threshold,
            "status": self.stock_status,
            "active": self.active,
        }


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(40), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    room_name = db.Column(db.String(100), nullable=False)
    priority = db.Column(db.Integer, nullable=False, default=2)  # 1: Emergency, 2: Gen 1, 3: Gen 2
    status = db.Column(db.String(40), nullable=False, default="PENDING")
    robot_id = db.Column(db.Integer, db.ForeignKey("robots.id"), nullable=True)
    manager_notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    loaded_at = db.Column(db.DateTime, nullable=True)
    dispatched_at = db.Column(db.DateTime, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    returned_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", back_populates="orders")
    robot = db.relationship("Robot", foreign_keys=[robot_id], back_populates="assigned_orders")
    items = db.relationship("OrderItem", back_populates="order", cascade="all, delete-orphan", lazy=True)
    transactions = db.relationship("InventoryTransaction", back_populates="order", lazy=True)

    @property
    def total_items_count(self):
        return sum(item.quantity for item in self.items)

    @property
    def items_summary(self):
        return ", ".join([f"{item.medicine.name} ({item.quantity} {item.unit})" for item in self.items if item.medicine])

    def to_dict(self):
        return {
            "id": self.id,
            "order_number": self.order_number,
            "user_id": self.user_id,
            "room_name": self.room_name,
            "priority": self.priority,
            "status": self.status,
            "robot_id": self.robot_id,
            "robot_name": self.robot.display_name if self.robot else None,
            "manager_notes": self.manager_notes or "",
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
            "accepted_at": self.accepted_at.strftime("%Y-%m-%d %H:%M:%S") if self.accepted_at else None,
            "loaded_at": self.loaded_at.strftime("%Y-%m-%d %H:%M:%S") if self.loaded_at else None,
            "dispatched_at": self.dispatched_at.strftime("%Y-%m-%d %H:%M:%S") if self.dispatched_at else None,
            "delivered_at": self.delivered_at.strftime("%Y-%m-%d %H:%M:%S") if self.delivered_at else None,
            "returned_at": self.returned_at.strftime("%Y-%m-%d %H:%M:%S") if self.returned_at else None,
            "total_items_count": self.total_items_count,
            "items_summary": self.items_summary,
            "items": [item.to_dict() for item in self.items],
        }


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    medicine_id = db.Column(db.Integer, db.ForeignKey("medicines.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit = db.Column(db.String(30), nullable=False)

    order = db.relationship("Order", back_populates="items")
    medicine = db.relationship("Medicine", back_populates="order_items")

    def to_dict(self):
        return {
            "id": self.id,
            "medicine_id": self.medicine_id,
            "medicine_name": self.medicine.name if self.medicine else "Unknown",
            "quantity": self.quantity,
            "unit": self.unit,
        }


class Robot(db.Model):
    __tablename__ = "robots"

    id = db.Column(db.Integer, primary_key=True)
    robot_code = db.Column(db.String(30), unique=True, nullable=False, index=True)  # R1, R2
    display_name = db.Column(db.String(80), nullable=False)  # "Delivery Robot 1 (R1)"
    active = db.Column(db.Boolean, default=True, nullable=False)
    status = db.Column(db.String(40), default="AVAILABLE", nullable=False)
    current_order_id = db.Column(db.Integer, db.ForeignKey("orders.id", use_alter=True, name="fk_robots_current_order_id"), nullable=True)
    last_location = db.Column(db.String(100), default="Medicine Room", nullable=True)
    last_seen = db.Column(db.DateTime, default=utc_now, nullable=True)
    battery_percentage = db.Column(db.Integer, nullable=True)  # 0 - 100, nullable

    assigned_orders = db.relationship("Order", foreign_keys=[Order.robot_id], back_populates="robot")
    current_order = db.relationship("Order", foreign_keys=[current_order_id], post_update=True)

    @property
    def is_assignable(self):
        return self.active and self.status == "AVAILABLE" and self.current_order_id is None

    def to_dict(self):
        return {
            "id": self.id,
            "robot_code": self.robot_code,
            "display_name": self.display_name,
            "active": self.active,
            "status": self.status,
            "current_order_id": self.current_order_id,
            "current_order_number": self.current_order.order_number if self.current_order else None,
            "destination": self.current_order.room_name if self.current_order else None,
            "last_location": self.last_location,
            "last_seen": self.last_seen.strftime("%Y-%m-%d %H:%M:%S") if self.last_seen else None,
            "battery_percentage": self.battery_percentage,
            "is_assignable": self.is_assignable,
        }


class InventoryTransaction(db.Model):
    __tablename__ = "inventory_transactions"

    id = db.Column(db.Integer, primary_key=True)
    medicine_id = db.Column(db.Integer, db.ForeignKey("medicines.id"), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    transaction_type = db.Column(db.String(50), nullable=False)  # STOCK_IN, STOCK_ADJUST, DISPATCH_DEDUCTION, CORRECTION
    quantity_change = db.Column(db.Integer, nullable=False)  # e.g., +50, -10
    reason = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    medicine = db.relationship("Medicine", back_populates="transactions")
    order = db.relationship("Order", back_populates="transactions")
    user = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "medicine_id": self.medicine_id,
            "medicine_name": self.medicine.name if self.medicine else "Unknown",
            "order_id": self.order_id,
            "order_number": self.order.order_number if self.order else None,
            "user_id": self.user_id,
            "username": self.user.username if self.user else "System",
            "transaction_type": self.transaction_type,
            "quantity_change": self.quantity_change,
            "reason": self.reason,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }


class SystemSetting(db.Model):
    __tablename__ = "system_settings"

    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(80), unique=True, nullable=False, index=True)
    setting_value = db.Column(db.String(255), nullable=False)

    @classmethod
    def get_value(cls, key, default=None):
        setting = cls.query.filter_by(setting_key=key).first()
        return setting.setting_value if setting else default

    @classmethod
    def set_value(cls, key, value):
        setting = cls.query.filter_by(setting_key=key).first()
        if setting:
            setting.setting_value = str(value)
        else:
            setting = cls(setting_key=key, setting_value=str(value))
            db.session.add(setting)
        db.session.commit()
        return setting


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)  # None if system/anonymous
    action = db.Column(db.String(100), nullable=False)  # e.g., ORDER_CREATE, ORDER_DISPATCH, STOCK_ADJUST
    entity_type = db.Column(db.String(50), nullable=False)  # Order, Medicine, Robot, User, Settings
    entity_id = db.Column(db.String(50), nullable=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    user = db.relationship("User", back_populates="audit_logs")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.user.username if self.user else "System",
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "details": self.details,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }
