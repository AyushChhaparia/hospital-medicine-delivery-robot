# Hospital Medicine Ordering and Robot Delivery System

This repository contains a Flask web application for hospital medicine ordering,
inventory management, dispatch coordination, and audit logging, together with
two ESP32 firmware sketches for autonomous medicine-delivery robots.

## Overview

Ward staff create medicine orders. The medicine-room manager reviews orders,
prepares and loads medicines, assigns a robot, secures the cargo box, and
dispatches the delivery. The application reserves stock when an order is
created and deducts physical stock only when dispatch is confirmed. The
administrator manages users, medicines, robots, priorities, and audit records.

The firmware polls the robot API, follows a line using two digital IR sensors,
uses RFID waypoints and recipient cards, controls the cargo-box servo, and
reports telemetry to the Flask application.

## Architecture

```text
Ward browser
    |
    v
Flask routes and services  <-->  SQLite database
    |
    v
Authenticated ESP32 robot API
    |
    +--> R1: General Ward 1 and General Ward 2
    +--> R2: Emergency Ward / Operation Theatre
```

The application is organized as follows:

| Path | Responsibility |
| --- | --- |
| `app.py`, `config.py` | Flask application factory and configuration |
| `models.py` | SQLAlchemy models |
| `routes/` | Authentication, ward, manager, administrator, and robot API routes |
| `services/` | Inventory, order workflow, robot, scheduler, and audit logic |
| `templates/`, `static/` | Server-rendered pages and browser assets |
| `firmware/` | The two Arduino sketches and secret-header examples |
| `tests/` | Pytest coverage for authentication, inventory, scheduling, robots, and audit/API behavior |
| `docs/` | Detailed setup and firmware notes |

## Roles

| Role code | Station | Main capabilities |
| --- | --- | --- |
| `emergency` | Emergency Ward / Operation Theatre | Create and track priority-1 orders |
| `general_1` | General Ward 1 | Create and track priority-2 orders |
| `general_2` | General Ward 2 | Create and track priority-3 orders |
| `medicine_manager` | Central Medicine Room | Review orders, prepare medicines, assign robots, dispatch, and receive returns |
| `admin` | Hospital Administration | Manage users, medicines, robots, priorities, inventory adjustments, and audit records |

Priority is configured by the application and defaults to emergency, General
Ward 1, then General Ward 2.

## Technology stack

- Python 3.10 or newer
- Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF, python-dotenv
- SQLite
- Vanilla HTML, CSS, and JavaScript
- ESP32 Arduino firmware using WiFi, HTTPClient, ArduinoJson, ILI9341,
  Adafruit GFX, MFRC522, and ESP32Servo libraries

## Setup

Detailed platform-specific instructions are in [`docs/setup.md`](docs/setup.md).
The short version is:

1. Create and activate a virtual environment.
2. Install `requirements.txt`.
3. Copy `.env.example` to `.env`.
4. Set a real `SECRET_KEY` and `ROBOT_API_TOKEN` in `.env`.
5. Run `python seed.py` to create the local database and generate demo
   passwords.
6. Run `python app.py` and open `http://127.0.0.1:5000`.

`instance/*.db`, `.env`, and firmware `secrets.h` files are local-only and are
ignored by Git. `seed.py` accepts `DEMO_ADMIN_PASSWORD`,
`DEMO_MANAGER_PASSWORD`, `DEMO_EMERGENCY_PASSWORD`, `DEMO_WARD1_PASSWORD`,
and `DEMO_WARD2_PASSWORD`; when a variable is absent, it generates a password
at runtime and prints it once for that seed run.

## Firmware

The Arduino folder rule is intentional: each sketch is in a folder with the
same name as its `.ino` file.

| Robot | Sketch | Service area |
| --- | --- | --- |
| R1 | `firmware/bot_general/bot_general.ino` | General Ward 1 and General Ward 2 |
| R2 | `firmware/bot_emergency/bot_emergency.ino` | Emergency Ward / Operation Theatre |

For each robot:

1. Copy `secrets.h.example` to `secrets.h` in the same folder.
2. Set the Wi-Fi SSID, Wi-Fi password, server URL, and robot token.
3. Keep `SERVER_BASE_URL` in the form `http://host:port`.
4. Install the required Arduino libraries and select an ESP32 board.
5. Upload the sketch from its same-named folder.

Never commit `secrets.h`. See [`docs/firmware.md`](docs/firmware.md) for wiring,
sensor behavior, and the firmware/API sequence.

## Robot API

All robot endpoints are under `/api/robot/<robot_code>` and require the
`X-Robot-Token` header. A `Bearer` prefix is also accepted by the server.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/assignment` | Return the robot's current order and medicine manifest |
| `POST` | `/heartbeat` | Record status, location, and battery telemetry |
| `POST` | `/rfid_node` | Record an RFID waypoint |
| `POST` | `/arrived` | Report arrival at the destination |
| `POST` | `/box_closed_delivered` | Confirm recipient delivery and begin return |
| `POST` | `/returned` | Confirm docking and reset the robot to available |

The current API returns an assignment whenever `current_order` exists. The
dispatch and assignment behavior is listed as an open limitation below.

## Order and robot states

The application order workflow includes `PENDING`, `ACCEPTED`, `PREPARING`,
`READY_FOR_LOADING`, `LOADED`, `READY_FOR_DISPATCH`, `DISPATCHED`,
`IN_TRANSIT`, `AWAITING_RECIPIENT`, `DELIVERED`, `RETURNING`, `RETURNED`,
`REJECTED`, and `CANCELLED`.

Robots normally move through `AVAILABLE`, `ASSIGNED`, `LOADING`, `READY`,
`DISPATCHED`, `DELIVERING`, `AWAITING_RECIPIENT`, and `RETURNING`.

## Running tests

From the repository root:

```powershell
python -m pytest -q
```

```bash
python -m pytest -q
```

The repository currently contains 14 collected pytest functions across the
files in `tests/`. Do not rely on the historical “13 tests” or “14 scenarios”
claims in the legacy documentation.

## Known limitations and reconciliation notes

The following discrepancies were found while comparing the legacy documents
with the code. They are recorded here rather than silently choosing a
behavior:

| Source | Claim | Code or current documentation |
| --- | --- | --- |
| `README.md` and `docs/setup.md` | Demo passwords are fixed values | `seed.py` now reads `DEMO_*_PASSWORD` variables or generates passwords at runtime |
| Legacy `README.md` | 13 acceptance scenarios | There are currently 14 collected pytest functions |
| Legacy `docs/setup.md` | 14 tests | There are currently 14 collected pytest functions, but they are not the same A–N scenario list |
| Legacy `docs/setup.md` | Ward URLs use `/room/<code>` | `routes/room_routes.py` registers `/ward/<ward_code>` |
| Legacy `README.md` | Firmware sketches are future integration | The ESP32 API and sketches are present and implemented |
| Legacy `docs/firmware.md` | Sketches and secrets are at the old root paths and values live in `.ino` files | Sketches are under `firmware/<bot>/`; settings belong in ignored `secrets.h` files |
| Legacy firmware text | Eight-channel IR sensor | Both sketches read two digital inputs: GPIO 13 and GPIO 27 |
| Legacy firmware sequence | Servo locks at 0 degrees | Both sketches use 45 degrees locked and 90 degrees open |
| Legacy firmware sequence | Stock is deducted while the order is `READY_FOR_DISPATCH` | `services/order_service.py` deducts stock during the transition to `DISPATCHED` |
| Legacy firmware sequence | The robot should depart for `READY_FOR_DISPATCH` | Both sketches currently treat `READY_FOR_DISPATCH` and `DISPATCHED` as assignment states; this is an open safety issue |

## Open behavioral issues

These are documented observations, not changes made in this preparation pass:

- The assignment endpoint uses `robot.current_order`, and the firmware accepts
  `READY_FOR_DISPATCH` before dispatch. This can allow departure before the
  manager's dispatch action.
- Robot assignment does not currently enforce that R1 receives only general
  ward orders or R2 only emergency orders.
- The selected motor pins include UART0 pins and a boot-strapping pin.
- Firmware battery values are constants, and some heartbeat states are
  reported as `AVAILABLE`.
- A `has_assignment: false` poll does not reset the local firmware state after
  cancellation.

## License

No license has been selected for this repository yet.
