/*
 * ======================================================================================
 * HOSPITAL MEDICINE TRANSPORT SYSTEM - AUTONOMOUS ROBOT 1: GENERAL WARDS (bot_general)
 * Target Hardware: ESP32 Dev Module
 * Destination Serviced: General Ward 1 & General Ward 2
 *
 * Integrated Hardware Components:
 *   1. 8-Channel IR Line Following Sensor (Proportional line tracking)
 *   2. 2.8" / 2.4" SPI TFT LCD (ILI9341 - 320x240 landscape clinical UI)
 *   3. RC522 RFID Reader (Universal Base card + Ward 1 & Ward 2 access cards)
 *   4. Servo Motor (Cargo box lid security lock/unlock mechanism)
 *   5. L298N Dual H-Bridge Motor Driver with PWM Speed Control
 *   6. Wi-Fi Webhook Client (Communicates with Flask Pharmacy & Scheduling Server)
 * ======================================================================================
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ILI9341.h>
#include <MFRC522.h>
#include <ESP32Servo.h>
#include "secrets.h"

/* ============================ NETWORK CONFIGURATION ============================ */
const char* ROBOT_CODE      = "R1";                   // Robot 1 for General Wards

/* ============================ PIN ASSIGNMENTS ============================ */
// Shared SPI Bus (TFT ILI9341 & RFID RC522)
#define SPI_SCK       18
#define SPI_MISO      19
#define SPI_MOSI      23

// TFT ILI9341 Display Pins
#define TFT_CS        21
#define TFT_DC        22
#define TFT_RST       2

// RFID RC522 Pins
#define RFID_SS_PIN   5
#define RFID_RST_PIN  26

// Servo Cargo Lid Lock
#define SERVO_PIN     15
#define SERVO_LOCKED_ANGLE    45    // Lid closed angle
#define SERVO_UNLOCKED_ANGLE  90    // Lid open angle

// L298N Motor Driver Pins
#define ENA           3   // RX0 / PWM Left
#define ENB           1   // TX0 / PWM Right
#define IN1           17
#define IN2           16
#define IN3           14
#define IN4           12

// 2-Channel IR Sensors
#define IR_LEFT_PIN   13   // Left IR Sensor
#define IR_RIGHT_PIN  27   // Right IR Sensor

// IR Sensor Active Logic:
// 0 = Active LOW (Black line absorbs IR, sensor OUT = LOW - Most standard modules)
// 1 = Active HIGH (Module calibrated for active HIGH)
const int LINE_DETECTED_VAL = 0;

/* ============================ AUTHORIZED RFID CARDS ============================ */
// 1 Universal Card for Central Medicine Room (Opens both Bot 1 & Bot 2 boxes)
const String CARD_UNIVERSAL_MEDICINE_ROOM = "DF 09 6A 1C";

// Dedicated Ward Patient/Staff Cards
const String CARD_GENERAL_WARD_1 = "DF 09 6A 1C";
const String CARD_GENERAL_WARD_2 = "DF 09 6A 1C";

/* ============================ MOTOR & SPEED SETTINGS ============================ */
int MOTOR_SPEED = 190;
int TURN_SPEED  = 150;
const int PWM_FREQ = 1000;
const int PWM_RESOLUTION = 8;

// Navigation Calibration Timings (ms) - Adjust according to your robot chassis & battery level
const unsigned long TURN_180_TIME_MS  = 1200; // Duration to execute a 180° pivot turn
const unsigned long TURN_90_TIME_MS   = 600;  // Duration to execute a 90° pivot turn
const unsigned long CROSSING_CLEAR_MS = 400;  // Duration to step forward past a cross-line marker

/* ============================ OPERATIONAL STATES & NAVIGATION PHASES ============================ */
enum RobotState {
  STATE_IDLE,                 // Docked at Medicine Room, awaiting assignment
  STATE_ORDER_ASSIGNED,       // Order assigned by manager, loading medicines
  STATE_READY_DISPATCH,       // Box locked, ready for departure
  STATE_IN_TRANSIT,           // Following line path towards destination ward
  STATE_ARRIVED_AT_WARD,      // Arrived at ward, waiting for authorized RFID card
  STATE_BOX_OPEN,             // Box unlocked for staff to retrieve medicines
  STATE_RETURNING,            // Returning back to Central Medicine Room
  STATE_RETURNED              // Docked back at Medicine Room
};

RobotState currentState = STATE_IDLE;

// Sub-phases for multi-segment path navigation (Medical Room <-> Decision Point <-> Ward 1 / Ward 2)
enum NavPhase {
  NAV_IDLE,                   // Robot docked at Medical Room
  NAV_OUTBOUND_TO_DECISION,   // Heading from Medical Room towards Decision Point
  NAV_OUTBOUND_TO_WARD1,      // Passed decision point, continuing straight to General Ward 1
  NAV_OUTBOUND_TO_WARD2,      // Turned right at decision point, heading to General Ward 2
  NAV_AT_WARD,                // Stopped at ward, awaiting RFID handover
  NAV_RETURN_FROM_WARD1,      // Turned 180°, heading back from Ward 1 towards Decision Point
  NAV_RETURN_FROM_WARD2,      // Turned 180°, heading back from Ward 2 towards Intersection
  NAV_RETURN_TO_BASE          // Passed decision point, heading straight to Medical Room dock
};

NavPhase navPhase = NAV_IDLE;

/* ============================ ORDER DATA STRUCTURE ============================ */
struct CurrentOrder {
  int orderId = 0;
  String orderNumber = "NONE";
  String destination = "NONE";
  int priority = 2;
  String itemsSummary = "No items";
  bool active = false;
} currentOrder;

/* ============================ GLOBAL HARDWARE OBJECTS ============================ */
Adafruit_ILI9341 tft(TFT_CS, TFT_DC, TFT_RST);
MFRC522 rfid(RFID_SS_PIN, RFID_RST_PIN);
Servo lockServo;
bool boxIsOpen = false;

unsigned long lastPollTime = 0;
const unsigned long POLL_INTERVAL = 3000;

unsigned long lastHeartbeatTime = 0;
const unsigned long HEARTBEAT_INTERVAL = 5000;

int batteryPercentage = 95;

/* ============================ MOTOR CONTROL FUNCTIONS ============================ */
void setMotorSpeed(int leftSpeed, int rightSpeed) {
  #if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
    ledcWrite(ENA, constrain(leftSpeed, 0, 255));
    ledcWrite(ENB, constrain(rightSpeed, 0, 255));
  #else
    ledcWrite(0, constrain(leftSpeed, 0, 255));
    ledcWrite(1, constrain(rightSpeed, 0, 255));
  #endif
}

void stopMotors() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
  setMotorSpeed(0, 0);
}

void moveForward() {
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
  setMotorSpeed(MOTOR_SPEED, MOTOR_SPEED);
}

void turnLeft() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
  setMotorSpeed(TURN_SPEED, TURN_SPEED);
}

void turnRight() {
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, HIGH);
  setMotorSpeed(TURN_SPEED, TURN_SPEED);
}

void turn180Degrees() {
  Serial.println("[NAV] Executing 180-degree in-place turn...");
  stopMotors();
  delay(200);

  // Pivot turn in place: Left reverse, Right forward
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
  setMotorSpeed(TURN_SPEED, TURN_SPEED);
  delay(TURN_180_TIME_MS);

  stopMotors();
  delay(200);
}

void turn90DegreesRight() {
  Serial.println("[NAV] Turning 90 degrees right at decision point...");
  stopMotors();
  delay(150);

  // Pivot right: Left forward, Right reverse
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, HIGH);
  setMotorSpeed(TURN_SPEED, TURN_SPEED);
  delay(TURN_90_TIME_MS);

  stopMotors();
  delay(200);
}

void turn90DegreesLeft() {
  Serial.println("[NAV] Turning 90 degrees left towards Medical Room...");
  stopMotors();
  delay(150);

  // Pivot left: Left reverse, Right forward
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
  setMotorSpeed(TURN_SPEED, TURN_SPEED);
  delay(TURN_90_TIME_MS);

  stopMotors();
  delay(200);
}

/* ============================ SERVO LOCK FUNCTIONS ============================ */
void lockBox() {
  lockServo.write(SERVO_LOCKED_ANGLE);
  boxIsOpen = false;
  Serial.println("[SERVO] Cargo Box LOCKED (CLOSED)");
}

void unlockBox() {
  lockServo.write(SERVO_UNLOCKED_ANGLE);
  boxIsOpen = true;
  Serial.println("[SERVO] Cargo Box UNLOCKED (OPEN)");
}

void toggleBox() {
  if (boxIsOpen) {
    lockBox();
  } else {
    unlockBox();
  }
}

/* ============================ TFT DISPLAY ROUTINES ============================ */
void showDecisionPointUI(const String& destination, const String& action) {
  digitalWrite(RFID_SS_PIN, HIGH);
  digitalWrite(TFT_CS, LOW);

  tft.fillRect(10, 44, 300, 26, ILI9341_YELLOW);
  tft.setTextSize(2);
  tft.setTextColor(ILI9341_BLACK);
  tft.setCursor(18, 49);
  tft.print("STOP: DECISION POINT");

  tft.fillRect(14, 180, 290, 24, ILI9341_DARKCYAN);
  tft.setTextSize(1);
  tft.setTextColor(ILI9341_WHITE);
  tft.setCursor(20, 186);
  tft.print("Target: " + destination + " | " + action);

  digitalWrite(TFT_CS, HIGH);
}
void updateTFTDisplay() {
  digitalWrite(RFID_SS_PIN, HIGH);
  digitalWrite(TFT_CS, LOW);

  tft.fillScreen(ILI9341_BLACK);

  tft.drawRect(2, 2, 316, 236, ILI9341_CYAN);
  tft.drawRect(4, 4, 312, 232, ILI9341_DARKCYAN);

  tft.fillRect(6, 6, 308, 32, ILI9341_NAVY);
  tft.setTextSize(2);
  tft.setTextColor(ILI9341_WHITE);
  tft.setCursor(14, 14);
  tft.print("BOT 1: GENERAL WARDS");

  tft.setTextSize(1);
  tft.setCursor(248, 18);
  if (WiFi.status() == WL_CONNECTED) {
    tft.setTextColor(ILI9341_GREEN);
    tft.print("WIFI: OK");
  } else {
    tft.setTextColor(ILI9341_RED);
    tft.print("WIFI: OFF");
  }

  uint16_t bannerColor = ILI9341_BLUE;
  String stateStr = "IDLE (DOCKED)";

  switch (currentState) {
    case STATE_IDLE:
      bannerColor = ILI9341_DARKGREEN;
      stateStr = "IDLE - READY AT BASE";
      break;
    case STATE_ORDER_ASSIGNED:
      bannerColor = ILI9341_ORANGE;
      stateStr = "ORDER ASSIGNED (LOADING)";
      break;
    case STATE_READY_DISPATCH:
      bannerColor = ILI9341_BLUE;
      stateStr = "READY FOR DISPATCH";
      break;
    case STATE_IN_TRANSIT:
      bannerColor = ILI9341_MAGENTA;
      stateStr = "EN ROUTE TO WARD";
      break;
    case STATE_ARRIVED_AT_WARD:
      bannerColor = ILI9341_RED;
      stateStr = "ARRIVED - SCAN RFID CARD";
      break;
    case STATE_BOX_OPEN:
      bannerColor = ILI9341_GREEN;
      stateStr = "BOX UNLOCKED - RETRIEVE";
      break;
    case STATE_RETURNING:
      bannerColor = ILI9341_PURPLE;
      stateStr = "RETURNING TO PHARMACY";
      break;
    case STATE_RETURNED:
      bannerColor = ILI9341_DARKGREEN;
      stateStr = "MISSION COMPLETED";
      break;
  }

  tft.fillRect(10, 44, 300, 26, bannerColor);
  tft.setTextSize(2);
  tft.setTextColor(ILI9341_WHITE);
  tft.setCursor(18, 49);
  tft.print(stateStr);

  // Line 78: Order Number (left side) & Box Lock Status Badge (right side)
  tft.setTextSize(1);
  tft.setTextColor(ILI9341_LIGHTGREY);
  tft.setCursor(14, 78);
  tft.print("ORDER ID : ");
  tft.setTextColor(ILI9341_YELLOW);
  tft.print(currentOrder.orderNumber);

  // Box Status Badge (OPEN in green, CLOSED in maroon/red)
  if (boxIsOpen) {
    tft.fillRect(206, 73, 98, 18, ILI9341_DARKGREEN);
    tft.drawRect(206, 73, 98, 18, ILI9341_GREEN);
    tft.setTextSize(1);
    tft.setTextColor(ILI9341_WHITE);
    tft.setCursor(216, 78);
    tft.print("BOX: OPEN");
  } else {
    tft.fillRect(206, 73, 98, 18, ILI9341_MAROON);
    tft.drawRect(206, 73, 98, 18, ILI9341_RED);
    tft.setTextSize(1);
    tft.setTextColor(ILI9341_WHITE);
    tft.setCursor(212, 78);
    tft.print("BOX: CLOSED");
  }

  tft.setTextSize(1);
  tft.setTextColor(ILI9341_LIGHTGREY);
  tft.setCursor(14, 100);
  tft.print("DESTINATION : ");
  tft.setTextColor(ILI9341_WHITE);
  tft.setTextSize(2);
  tft.print(currentOrder.destination);

  tft.setTextSize(1);
  tft.setTextColor(ILI9341_LIGHTGREY);
  tft.setCursor(14, 126);
  tft.print("PRIORITY    : ");
  tft.setTextColor(currentOrder.priority == 1 ? ILI9341_RED : (currentOrder.priority == 2 ? ILI9341_GREEN : ILI9341_ORANGE));
  tft.print("Priority ");
  tft.print(currentOrder.priority);

  tft.setTextColor(ILI9341_LIGHTGREY);
  tft.setCursor(14, 146);
  tft.print("MEDICINES   : ");
  tft.setTextColor(ILI9341_CYAN);
  tft.setCursor(14, 160);
  tft.print(currentOrder.itemsSummary.length() > 0 ? currentOrder.itemsSummary.substring(0, 48) : "No items");

  tft.drawLine(10, 205, 310, 205, ILI9341_DARKGREY);
  tft.setCursor(14, 214);
  tft.setTextColor(ILI9341_YELLOW);
  if (currentState == STATE_IDLE || currentState == STATE_ORDER_ASSIGNED) {
    tft.print("RFID: Tap Manager Card to Open/Close Box");
  } else if (currentState == STATE_ARRIVED_AT_WARD) {
    tft.print("RFID: Tap Ward Card to Unlock Box");
  } else {
    tft.print("Universal RFID: Base | Staff Cards: Ward 1 & 2");
  }

  digitalWrite(TFT_CS, HIGH);
}

/* ============================ WEBHOOK & HTTP API ============================ */
void pollServerAssignment() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String url = String(SERVER_BASE_URL) + "/api/robot/" + ROBOT_CODE + "/assignment";

  http.begin(url);
  http.addHeader("X-Robot-Token", ROBOT_TOKEN);

  int httpCode = http.GET();
  if (httpCode == HTTP_CODE_OK) {
    String payload = http.getString();
    StaticJsonDocument<1024> doc;
    DeserializationError error = deserializeJson(doc, payload);

    if (!error) {
      bool hasAssignment = doc["has_assignment"] | false;
      if (hasAssignment) {
        JsonObject orderObj = doc["order"];
        currentOrder.orderId = orderObj["order_id"];
        currentOrder.orderNumber = orderObj["order_number"].as<String>();
        currentOrder.destination = orderObj["destination_room"].as<String>();
        currentOrder.priority = orderObj["priority"];
        currentOrder.active = true;

        String status = orderObj["status"].as<String>();
        Serial.printf("[POLL] Active assignment found! Order: %s | Status: %s | Dest: %s\n",
                      currentOrder.orderNumber.c_str(), status.c_str(), currentOrder.destination.c_str());

        JsonArray items = orderObj["items"];
        String itemsStr = "";
        for (JsonObject item : items) {
          itemsStr += item["medicine"].as<String>() + " (" + String(item["quantity"].as<int>()) + "), ";
        }
        currentOrder.itemsSummary = itemsStr;

        if (status == "READY_FOR_DISPATCH" || status == "DISPATCHED") {
          if (currentState == STATE_IDLE || currentState == STATE_ORDER_ASSIGNED) {
            currentState = STATE_IN_TRANSIT;
            navPhase = NAV_OUTBOUND_TO_DECISION;
            lockBox();
            updateTFTDisplay();
            // Step forward off the Medical Room docking line
            moveForward();
            delay(CROSSING_CLEAR_MS);
            Serial.println("[STATE] Departing on delivery mission to " + currentOrder.destination);
          }
        } else {
          currentState = STATE_ORDER_ASSIGNED;
          updateTFTDisplay();
        }
      } else {
        Serial.println("[POLL] Connected to server: No active orders assigned (Robot Idle).");
      }
    } else {
      Serial.printf("[POLL ERROR] JSON Deserialization failed: %s\n", error.c_str());
    }
  } else {
    if (httpCode > 0) {
      Serial.printf("[POLL ERROR] Server returned HTTP %d\n", httpCode);
    } else {
      Serial.printf("[POLL ERROR] Connection failed to %s (Error: %s, code %d)\n",
                    url.c_str(), http.errorToString(httpCode).c_str(), httpCode);
    }
  }
  http.end();
}

void notifyArrivalAtWard() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String url = String(SERVER_BASE_URL) + "/api/robot/" + ROBOT_CODE + "/arrived";

  http.begin(url);
  http.addHeader("X-Robot-Token", ROBOT_TOKEN);
  http.addHeader("Content-Type", "application/json");

  int httpCode = http.POST("{}");
  Serial.printf("[WEBHOOK] Notified arrival. Response: %d\n", httpCode);
  http.end();
}

void notifyBoxClosedAndDelivered() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String url = String(SERVER_BASE_URL) + "/api/robot/" + ROBOT_CODE + "/box_closed_delivered";

  http.begin(url);
  http.addHeader("X-Robot-Token", ROBOT_TOKEN);
  http.addHeader("Content-Type", "application/json");

  int httpCode = http.POST("{}");
  Serial.printf("[WEBHOOK] Notified delivery completion. Response: %d\n", httpCode);
  http.end();
}

void notifyReturnedToBase() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String url = String(SERVER_BASE_URL) + "/api/robot/" + ROBOT_CODE + "/returned";

  http.begin(url);
  http.addHeader("X-Robot-Token", ROBOT_TOKEN);
  http.addHeader("Content-Type", "application/json");

  int httpCode = http.POST("{}");
  Serial.printf("[WEBHOOK] Notified return to base. Response: %d\n", httpCode);
  http.end();
}

void sendHeartbeat() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String url = String(SERVER_BASE_URL) + "/api/robot/" + ROBOT_CODE + "/heartbeat";

  http.begin(url);
  http.addHeader("X-Robot-Token", ROBOT_TOKEN);
  http.addHeader("Content-Type", "application/json");

  String statusText = "AVAILABLE";
  if (currentState == STATE_IN_TRANSIT) statusText = "DELIVERING";
  else if (currentState == STATE_ARRIVED_AT_WARD) statusText = "AWAITING_RECIPIENT";
  else if (currentState == STATE_RETURNING) statusText = "RETURNING";

  String body = "{\"status\":\"" + statusText + "\",\"location\":\"" +
                (currentState == STATE_IDLE ? "Medicine Room" : currentOrder.destination) +
                "\",\"battery\":" + String(batteryPercentage) + "}";

  http.POST(body);
  http.end();
}

/* ============================ RFID VALIDATION ============================ */
String readRFIDCardUID() {
  digitalWrite(TFT_CS, HIGH);
  digitalWrite(RFID_SS_PIN, LOW);

  if (!rfid.PICC_IsNewCardPresent()) {
    digitalWrite(RFID_SS_PIN, HIGH);
    return "";
  }

  if (!rfid.PICC_ReadCardSerial()) {
    digitalWrite(RFID_SS_PIN, HIGH);
    return "";
  }

  String uidStr = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uidStr += "0";
    uidStr += String(rfid.uid.uidByte[i], HEX);
    if (i < rfid.uid.size - 1) uidStr += " ";
  }
  uidStr.toUpperCase();

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
  digitalWrite(RFID_SS_PIN, HIGH);

  return uidStr;
}

bool isAuthorizedCard(String uid) {
  if (uid == CARD_UNIVERSAL_MEDICINE_ROOM) {
    Serial.println("[RFID] Master Universal Medicine Room Card authenticated!");
    return true;
  }

  if (currentOrder.destination.indexOf("Ward 1") >= 0 && uid == CARD_GENERAL_WARD_1) {
    Serial.println("[RFID] General Ward 1 Staff Card authenticated!");
    return true;
  }

  if (currentOrder.destination.indexOf("Ward 2") >= 0 && uid == CARD_GENERAL_WARD_2) {
    Serial.println("[RFID] General Ward 2 Staff Card authenticated!");
    return true;
  }

  Serial.println("[RFID] Unauthorized Card UID: " + uid);
  return false;
}

/* ============================ LINE FOLLOWING ROUTINE ============================ */
void handleLineTracking() {
  // Read the 2 IR sensors (Pins 13 and 27)
  int leftVal  = digitalRead(IR_LEFT_PIN);
  int rightVal = digitalRead(IR_RIGHT_PIN);

  bool leftOnLine  = (leftVal == LINE_DETECTED_VAL);
  bool rightOnLine = (rightVal == LINE_DETECTED_VAL);

  // ==================== CONDITION 1: BOTH SENSORS DETECT LINE (INTERSECTION / STOP MARKER) ====================
  if (leftOnLine && rightOnLine) {
    stopMotors();
    delay(200);

    // SUB-CASE A: Outbound from Medical Room -> Reached "Stop for decision" point
    if (currentState == STATE_IN_TRANSIT && navPhase == NAV_OUTBOUND_TO_DECISION) {
      Serial.println("[NAV] === ARRIVED AT DECISION POINT ===");

      if (currentOrder.destination.indexOf("Ward 1") >= 0) {
        // GENERAL WARD 1: Continue journey straight to room
        Serial.println("[NAV] Destination is General Ward 1: Continuing journey straight!");
        showDecisionPointUI("General Ward 1", "Going Straight");
        delay(800); // Brief pause at decision stop

        navPhase = NAV_OUTBOUND_TO_WARD1;
        updateTFTDisplay();

        // Drive past the intersection cross-line
        moveForward();
        delay(CROSSING_CLEAR_MS);
      } else {
        // GENERAL WARD 2: Turn right at decision point
        Serial.println("[NAV] Destination is General Ward 2: Turning right!");
        showDecisionPointUI("General Ward 2", "Turning Right 90 deg");
        delay(800); // Brief pause at decision stop

        turn90DegreesRight();
        navPhase = NAV_OUTBOUND_TO_WARD2;
        updateTFTDisplay();

        // Drive onto the Ward 2 branch line
        moveForward();
        delay(CROSSING_CLEAR_MS);
      }
      return;
    }

    // SUB-CASE B: Outbound -> Arrived at Destination Ward (Ward 1 or Ward 2)
    if (currentState == STATE_IN_TRANSIT && (navPhase == NAV_OUTBOUND_TO_WARD1 || navPhase == NAV_OUTBOUND_TO_WARD2)) {
      Serial.println("[NAV] Both IR triggered: Reached Destination Ward Marker!");
      currentState = STATE_ARRIVED_AT_WARD;
      navPhase = NAV_AT_WARD;
      notifyArrivalAtWard();
      updateTFTDisplay();
      return;
    }

    // SUB-CASE C: Returning from General Ward 1, crossing decision point
    // USER INSTRUCTION: "and then come to medical room ignoring stop of decision point"
    if (currentState == STATE_RETURNING && navPhase == NAV_RETURN_FROM_WARD1) {
      Serial.println("[NAV] Returning from Ward 1: Ignoring stop of decision point, continuing straight to Medical Room!");
      navPhase = NAV_RETURN_TO_BASE;
      // Step across intersection cross-line without stopping
      moveForward();
      delay(CROSSING_CLEAR_MS);
      return;
    }

    // SUB-CASE D: Returning from General Ward 2, reached intersection junction
    if (currentState == STATE_RETURNING && navPhase == NAV_RETURN_FROM_WARD2) {
      Serial.println("[NAV] Returning from Ward 2: Reached intersection -> Turning left towards Medical Room!");
      turn90DegreesLeft();
      navPhase = NAV_RETURN_TO_BASE;
      // Step forward onto Medical Room corridor line
      moveForward();
      delay(CROSSING_CLEAR_MS);
      return;
    }

    // SUB-CASE E: Reached Central Medical Room Dock
    if (currentState == STATE_RETURNING && navPhase == NAV_RETURN_TO_BASE) {
      Serial.println("[NAV] Both IR triggered: Successfully returned and docked at Medical Room!");
      currentState = STATE_RETURNED;
      notifyReturnedToBase();
      currentOrder.active = false;
      navPhase = NAV_IDLE;
      currentState = STATE_IDLE;
      updateTFTDisplay();
      return;
    }

    return;
  }

  // ==================== CONDITION 2: STEER LEFT ====================
  if (leftOnLine && !rightOnLine) {
    turnLeft();
    return;
  }

  // ==================== CONDITION 3: STEER RIGHT ====================
  if (!leftOnLine && rightOnLine) {
    turnRight();
    return;
  }

  // ==================== CONDITION 4: MOVE STRAIGHT ====================
  moveForward();
}

/* ============================ MAIN SETUP & LOOP ============================ */
void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println("\n========================================================");
  Serial.println(" HOSPITAL ROBOT 1 (GENERAL WARDS) INITIALIZING...");
  Serial.println("========================================================");

  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);

  #if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
    ledcAttach(ENA, PWM_FREQ, PWM_RESOLUTION);
    ledcAttach(ENB, PWM_FREQ, PWM_RESOLUTION);
  #else
    ledcSetup(0, PWM_FREQ, PWM_RESOLUTION);
    ledcSetup(1, PWM_FREQ, PWM_RESOLUTION);
    ledcAttachPin(ENA, 0);
    ledcAttachPin(ENB, 1);
  #endif
  stopMotors();

  // Initialize 2-Channel IR Sensor Pins (GPIO 13 and GPIO 27)
  pinMode(IR_LEFT_PIN, INPUT);
  pinMode(IR_RIGHT_PIN, INPUT);

  // Initialize Servo Cargo Lid Lock
  lockServo.setPeriodHertz(50);
  lockServo.attach(SERVO_PIN, 500, 2400);
  lockBox();

  pinMode(TFT_CS, OUTPUT);
  digitalWrite(TFT_CS, HIGH);
  pinMode(RFID_SS_PIN, OUTPUT);
  digitalWrite(RFID_SS_PIN, HIGH);

  SPI.begin(SPI_SCK, SPI_MISO, SPI_MOSI);

  tft.begin();
  tft.setRotation(1);
  tft.fillScreen(ILI9341_BLACK);
  updateTFTDisplay();

  rfid.PCD_Init();
  delay(50);

  Serial.print("[WIFI] Connecting to SSID: ");
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WIFI] Connected! IP Address: " + WiFi.localIP().toString());
  } else {
    Serial.println("\n[WIFI] Connection timeout. Operating in standalone mode.");
  }

  updateTFTDisplay();
  Serial.println("[SYSTEM] Robot 1 ready. Awaiting manager dispatch.");
}

void loop() {
  unsigned long now = millis();

  String cardUID = readRFIDCardUID();
  if (cardUID != "") {
    Serial.println("[RFID] Scanned UID: " + cardUID);

    if (isAuthorizedCard(cardUID)) {
      if (currentState == STATE_ARRIVED_AT_WARD) {
        // 1st scan at Ward: Unlocks box lid so staff can remove medicines
        unlockBox();
        currentState = STATE_BOX_OPEN;
        updateTFTDisplay();
        Serial.println("[RFID] 1st scan at Ward: Cargo box unlocked. Staff can retrieve medicines.");
      } else if (currentState == STATE_BOX_OPEN) {
        // 2nd scan at Ward: Medicines removed, box is closed and order considered complete!
        lockBox();
        notifyBoxClosedAndDelivered();

        Serial.println("[STATE] 2nd scan at Ward: Box closed, order complete! Executing 180 degree turn at same position...");
        delay(500);
        turn180Degrees();

        // Configure return phase based on which ward we just completed
        if (currentOrder.destination.indexOf("Ward 2") >= 0) {
          navPhase = NAV_RETURN_FROM_WARD2;
        } else {
          navPhase = NAV_RETURN_FROM_WARD1;
        }

        currentState = STATE_RETURNING;
        updateTFTDisplay();

        // Step forward off the ward stop marker
        moveForward();
        delay(CROSSING_CLEAR_MS);
        Serial.println("[STATE] Returning back to Central Medical Room.");
      } else if (currentState == STATE_ORDER_ASSIGNED || currentState == STATE_IDLE) {
        // At Medicine Room Base: Toggle box open if closed, or close if open!
        if (boxIsOpen) {
          lockBox();
          Serial.println("[RFID] Manager Card scan: Box was OPEN -> now CLOSED.");
        } else {
          unlockBox();
          Serial.println("[RFID] Manager Card scan: Box was CLOSED -> now OPEN.");
        }
        updateTFTDisplay();
        delay(800); // Debounce to allow clean card removal
      }
    }
  }

  if (currentState == STATE_IN_TRANSIT || currentState == STATE_RETURNING) {
    handleLineTracking();
  }

  if (currentState == STATE_IDLE || currentState == STATE_ORDER_ASSIGNED) {
    if (now - lastPollTime >= POLL_INTERVAL) {
      lastPollTime = now;
      pollServerAssignment();
    }
  }

  if (now - lastHeartbeatTime >= HEARTBEAT_INTERVAL) {
    lastHeartbeatTime = now;
    sendHeartbeat();
  }

  delay(20);
}
