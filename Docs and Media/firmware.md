# ESP32 firmware setup

The repository contains two ESP32 sketches. Each `.ino` file remains in a
folder with the same name because that is required by the Arduino build
layout.

| Robot | Sketch | Service area |
| --- | --- | --- |
| R1 | `firmware/bot_general/bot_general.ino` | General Ward 1 and General Ward 2 |
| R2 | `firmware/bot_emergency/bot_emergency.ino` | Emergency Ward / Operation Theatre |

## Arduino libraries

Install these libraries through the Arduino IDE Library Manager:

- Adafruit ILI9341
- Adafruit GFX Library
- MFRC522
- ESP32Servo
- ArduinoJson

Select an ESP32 board supported by the installed ESP32 Arduino core.

## Per-robot secrets

For each robot, copy the example header:

```text
firmware/bot_general/secrets.h.example -> firmware/bot_general/secrets.h
firmware/bot_emergency/secrets.h.example -> firmware/bot_emergency/secrets.h
```

Set these four values in the copied file:

```cpp
const char* WIFI_SSID = "your-wifi-name";
const char* WIFI_PASSWORD = "your-wifi-password";
const char* SERVER_BASE_URL = "http://your-server-host:5000";
const char* ROBOT_TOKEN = "your-robot-api-token";
```

`secrets.h` is ignored by Git. Never replace the placeholders in
`secrets.h.example` with real credentials.

## Wiring reference

### Shared SPI bus

| Signal | ESP32 GPIO | TFT | RC522 |
| --- | ---: | --- | --- |
| SCK | 18 | SCK | SCK |
| MISO | 19 | MISO | MISO |
| MOSI | 23 | MOSI | MOSI |
| TFT CS | 21 | CS | — |
| TFT DC | 22 | DC | — |
| TFT reset | 2 | RESET | — |
| RFID CS | 5 | — | SDA/SS |
| RFID reset | 26 | — | RST |

Use 3.3 V for the RC522 and connect all devices to a common ground.

### Motor driver

| L298N signal | ESP32 GPIO |
| --- | ---: |
| ENA | 3 |
| IN1 | 17 |
| IN2 | 16 |
| IN3 | 14 |
| IN4 | 12 |
| ENB | 1 |

GPIO 3 and GPIO 1 are UART0 pins, and GPIO 12 is a boot-strapping pin. Their
use is a known hardware limitation and should be reviewed before a production
build.

### Cargo servo

| Function | ESP32 GPIO | Firmware position |
| --- | ---: | --- |
| Servo signal | 15 | 45 degrees locked; 90 degrees open |

Power the servo from a suitable external 5 V supply and share ground with the
ESP32.

### Line sensors

The firmware uses **two digital IR sensors**, not an eight-channel array:

| Sensor | ESP32 GPIO |
| --- | ---: |
| Left | 13 |
| Right | 27 |

The sketches read both inputs with `digitalRead`. Sensor polarity is
configured by the firmware's line-detection constant. Both sensors detecting
the line is used as a marker/stop condition; one sensor detecting the line
causes a turn, and neither causes forward motion.

## Uploading

1. Copy the appropriate `secrets.h.example` to `secrets.h`.
2. Set the server URL to the host reachable by the ESP32 over Wi-Fi.
3. Open the matching `.ino` file from its same-named folder in Arduino IDE.
4. Select the ESP32 board and serial port.
5. Compile and upload.

Arduino-generated build artifacts are ignored by Git.

## API sequence

The sketches authenticate using `X-Robot-Token` and poll:

1. `GET /api/robot/<robot_code>/assignment`
2. `POST /api/robot/<robot_code>/heartbeat`
3. `POST /api/robot/<robot_code>/rfid_node` when a waypoint is read
4. `POST /api/robot/<robot_code>/arrived` at the destination
5. `POST /api/robot/<robot_code>/box_closed_delivered` after recipient retrieval
6. `POST /api/robot/<robot_code>/returned` after docking

The application currently returns an assignment whenever a robot has a
`current_order`. The firmware starts navigation for both
`READY_FOR_DISPATCH` and `DISPATCHED`; this is a known issue because stock is
deducted only by the manager's dispatch action.

## Current firmware limitations

- Battery percentages are compile-time constants rather than sensor readings.
- Heartbeats report `AVAILABLE` for local states that include loading or an
  open box.
- A poll returning `has_assignment: false` does not reset every local state
  after a cancelled order.
- R1/R2 ward eligibility is not enforced by the robot assignment service.
- Motor pin assignments conflict with UART0 and a boot-strapping pin.
