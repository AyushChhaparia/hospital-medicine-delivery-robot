# Hospital Autonomous Medicine Delivery & Dispatch Management System

A production-grade, full-stack hospital medicine ordering and autonomous line-following robot delivery management system built with Python, Flask, Flask-SQLAlchemy, Flask-Login, SQLite, and vanilla responsive HTML5/CSS3/JavaScript.

Designed for clinical wards to order life-critical medicines, an on-duty Medicine Room Manager to prepare and dispatch deliveries via a two-robot autonomous fleet (R1 and R2), and a hospital administrator to audit operations and configure hospital-wide priority rules.

---

## 1. System Architecture & Role Permissions

The application supports five authenticated roles with strict server-enforced role-based access control (RBAC):

| Role Code | Title / Station | Scheduling Priority | Key Capabilities |
| :--- | :--- | :--- | :--- |
| `emergency` | Emergency Ward / Operation Theatre | **Priority 1 (Highest)** | Requisition emergency medicines, real-time stock availability, cart ordering, live robot tracking. |
| `general_1` | General Ward 1 | **Priority 2** | Standard medicine requisition, track order status and robot assignment. Precedes Ward 2. |
| `general_2` | General Ward 2 | **Priority 3** | Standard medicine requisition, track order status and robot assignment. Processed after Ward 1. |
| `medicine_manager` | Central Medicine Room | Station Management | Manage queue, review/accept/reject orders, prepare medicines, assign robots, confirm cargo loading, **atomic dispatch & stock deduction**, receive incoming shipments. |
| `admin` | Hospital Administration | System Superuser | Full user account management, medicine catalog, manual stock adjustment, robot registry, priority hierarchy configuration, immutable audit trail. |

---

## 2. Technology Stack

- **Backend**: Python 3.11, Flask 3.1, Flask-SQLAlchemy, Flask-Login, Flask-WTF (CSRF Protection), Werkzeug Password Hashing.
- **Database**: SQLite with ACID transactions, atomic stock reservations, and foreign key constraints.
- **Frontend**: Responsive HTML5, Modern Healthcare CSS, Vanilla JavaScript (Fetch API, dynamic in-memory cart, polling).
- **Robotics Interface**: REST API with bearer token authentication (`X-Robot-Token`) designed for future ESP32 line-following robots.

---

## 3. Quick Start & Execution Guide

### Prerequisites
- Python 3.10+ installed
- Git (optional)

### Setup & Launch Commands (PowerShell / Windows)

```powershell
# 1. Clone or navigate to the project directory
cd "c:\Users\shubh\Desktop\Techh Buddies\2026-27\hospital medicine transport bot"

# 2. Create Python virtual environment
python -m venv .venv

# 3. Activate virtual environment
.\.venv\Scripts\Activate.ps1

# 4. Install dependencies
pip install -r requirements.txt

# 5. Initialize database and seed demo data & accounts
python seed.py

# 6. Run the application
python app.py
```

Open your browser and navigate to:
**`http://127.0.0.1:5000`**

---

## 4. Default Demo Accounts

All demo accounts are pre-seeded via `seed.py`:

| Role | Username | Password | Default Landing Interface |
| :--- | :--- | :--- | :--- |
| **Administrator** | `admin` | `admin123` | `/admin/overview` |
| **Medicine Manager** | `manager` | `manager123` | `/manager` |
| **Emergency Ward / OT** | `emergency` | `emergency123` | `/ward/emergency` |
| **General Ward 1** | `ward1` | `ward123` | `/ward/general_1` |
| **General Ward 2** | `ward2` | `ward123` | `/ward/general_2` |

---

## 5. Core Business Logic & Inventory Rules

1. **Immediate Stock Reservation**:
   $$\text{Available Stock} = \text{Physical Stock} - \text{Reserved Stock}$$
   When a ward submits an order, required quantities are reserved immediately in a database transaction. If another ward attempts to order more than the remaining available stock, the order is rejected.
2. **Atomic Dispatch & Inventory Deduction**:
   When the Medicine Room Manager confirms that medicines are loaded into the assigned robot cargo box and clicks **Complete & Dispatch**:
   - The order status transitions to `DISPATCHED`.
   - Physical stock is deducted.
   - Reserved stock is released.
   - An immutable record is created in `inventory_transactions`.
   - Repeated requests or double-clicks are rejected with clear error messages.
3. **Pre-Dispatch Cancellation**:
   If an order is rejected or cancelled before dispatch, the reserved quantity is safely restored to available stock without touching physical stock.
4. **Deterministic Priority Queue**:
   Queue sorting strictly follows:
   1. `priority` (1: Emergency > 2: General Ward 1 > 3: General Ward 2)
   2. `created_at` timestamp (FIFO)
   3. `order_id` (deterministic tie-breaker)

---

## 6. Two-Robot Management (R1 & R2)

The system manages two autonomous delivery robots:
- `R1`: Primary Autonomous Delivery Robot
- `R2`: Secondary Autonomous Delivery Robot

### States:
- `AVAILABLE` &rarr; Robot docked in Medicine Room, ready for assignment.
- `ASSIGNED` &rarr; Assigned to an accepted order.
- `LOADING` &rarr; Medicines confirmed placed into cargo box.
- `READY` &rarr; Cargo box secured and latched.
- `DISPATCHED` &rarr; Order completed, departed station.
- `DELIVERING` &rarr; En route along line track.
- `AWAITING_RECIPIENT` &rarr; Arrived at destination ward, awaiting recipient PIN/RFID unlock.
- `RETURNING` &rarr; Traveling back to Central Medicine Room.
- `MAINTENANCE` &rarr; Offline for mechanical/battery servicing.

> **Safety Rule**: A robot cannot be assigned to another order until its return to the Medicine Room is verified.

---

## 7. Future ESP32 / Hardware Integration APIs

The backend exposes authenticated REST endpoints for ESP32 microcontrollers. Firmware developers authenticate using the HTTP header:
`X-Robot-Token: esp32-hospital-robot-secure-token-2026`

### Endpoints:

1. **Get Current Assignment & Manifest**:
   - `GET /api/robot/<robot_code>/assignment`
   - Returns destination ward, priority, order number, and list of medicines in the cargo box.
2. **Heartbeat & Telemetry**:
   - `POST /api/robot/<robot_code>/heartbeat`
   - Payload: `{"status": "DELIVERING", "location": "Corridor A", "battery": 92}`
3. **RFID Waypoint Checkpoint**:
   - `POST /api/robot/<robot_code>/rfid_node`
   - Payload: `{"node_id": "TAG-8821", "node_label": "Junction 3"}`
4. **Destination Arrival**:
   - `POST /api/robot/<robot_code>/arrived`
   - Triggered when robot detects destination RFID tag; notifies ward staff.
5. **Recipient Access & Box Closed**:
   - `POST /api/robot/<robot_code>/box_closed_delivered`
   - Triggered when ward staff unlocks cargo box, removes medication, and latches door.
6. **Station Docking & Return Confirmation**:
   - `POST /api/robot/<robot_code>/returned`
   - Robot docks into Medicine Room charging pad; automatically resets status to `AVAILABLE`.

---

## 8. Test Suite Verification

Run the test suite with pytest:

```powershell
.\.venv\Scripts\pytest -v
```

All 13 acceptance test scenarios (Tests A through M) are validated in `tests/`:
- **Test A**: Authentication & Ward Role Isolation
- **Test B**: Zero Stock Availability & Order Rejection
- **Test C**: Concurrent Stock Reservation Limits
- **Test D**: Priority Scheduling (Emergency > Ward 1 > Ward 2)
- **Test E**: FIFO Tie-Breaking
- **Test F**: Inactive/Busy Robot Assignment Rejection
- **Test G**: Multi-step Dispatch Gate Verification
- **Test H**: Exactly-Once Inventory Deduction on Dispatch
- **Test I**: Idempotency & Duplicate Request Protection
- **Test J**: Safe Reservation Release on Order Cancellation
- **Test K**: Mandatory Return Confirmation Before Reassignment
- **Test L**: Mobile Responsive Viewport & Controls
- **Test M**: Security & Operational Audit Trail Logging
