/*
 * ======================================================================================
 * HOSPITAL MEDICINE TRANSPORT SYSTEM - AUTONOMOUS ROBOT 2: EMERGENCY WARD (bot_emergency)
 * Target Hardware: ESP32 Dev Module
 * Destination Serviced: Emergency Ward / Operation Theatre (Priority 1 Life-Critical)
 *
 * Integrated Hardware Components:
 *   1. 8-Channel IR Line Following Sensor (Proportional line tracking)
 *   2. 2.8" / 2.4" SPI TFT LCD (ILI9341 - 320x240 landscape clinical UI, Red Priority theme)
 *   3. RC522 RFID Reader (Universal Base card + Emergency Ward dedicated access card)
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

/* ============================ NETWORK CONFIGURATION ============================ */
const char* WIFI_SSID     = "YOUR_WIFI_SSID";          // Replace with your WiFi SSID
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";    // Replace with your WiFi Password

// Backend Server URL (IP of the laptop running Flask app.py)
const char* SERVER_BASE_URL = "http://192.168.1.10:5000";
const char* ROBOT_TOKEN     = "YOUR_ROBOT_TOKEN";
const char* ROBOT_CODE      = "R2";                   // Robot 2 dedicated for Emergency Ward

/* ============================ PIN ASSIGNMENTS ============================ */
// SPI Bus (Shared by TFT and RC522)
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

// Servo Cargo Lock Pin
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

// 2-Channel IR Line Following Sensors
#define IR_LEFT_PIN   13   // Left IR Sensor
#define IR_RIGHT_PIN  27   // Right IR Sensor

// IR Sensor Active Logic:
// 0 = Active LOW (Black line absorbs IR, sensor OUT = LOW - Most standard modules)
// 1 = Active HIGH (Module calibrated for active HIGH)
const int LINE_DETECTED_VAL = 0;

/* ============================ AUTHORIZED RFID CARDS ============================ */
// 1 Universal Card for Central Medicine Room (Opens both Bot 1 & Bot 2 boxes)
const String CARD_UNIVERSAL_MEDICINE_ROOM = "A1 B2 C3 D4";

// Dedicated Emergency Ward Card (OT Doctor / Emergency Nurse)
const String CARD_EMERGENCY_WARD = "99 88 77 66";

/* ============================ MOTOR & SPEED SETTINGS ============================ */
int MOTOR_SPEED = 210;
int TURN_SPEED  = 165;
const int PWM_FREQ = 1000;
const int PWM_RESOLUTION = 8;

// Navigation Calibration Timings (ms) - Adjust according to your robot chassis & battery level
const unsigned long TURN_180_TIME_MS  = 1200; // Duration to execute a 180° pivot turn
const unsigned long CROSSING_CLEAR_MS = 400;  // Duration to step forward past a cross-line marker

/* ============================ OPERATIONAL STATES ============================ */
enum RobotState {
  STATE_IDLE,                 // Docked at Medicine Room, awaiting emergency assignment
  STATE_ORDER_ASSIGNED,       // Emergency order assigned, loading in progress
  STATE_READY_DISPATCH,       // Box locked, ready for emergency departure
  STATE_IN_TRANSIT,           // Rapid transit along line track to Emergency Ward / OT
  STATE_ARRIVED_AT_WARD,      // Arrived at OT/Emergency, awaiting RFID swipe
  STATE_BOX_OPEN,             // Box unlocked for medical staff to retrieve medicines
  STATE_RETURNING,            // Returning back to Central Medicine Room
  STATE_RETURNED              // Docked back at Medicine Room
};

RobotState currentState = STATE_IDLE;

/* ============================ ORDER DATA STRUCTURE ============================ */
struct CurrentOrder {
  int orderId = 0;
  String orderNumber = "NONE";
  String destination = "Emergency Ward / OT";
  int priority = 1;
  String itemsSummary = "No items";
  bool active = false;
} currentOrder;

/* ============================ GLOBAL HARDWARE OBJECTS ============================ */
Adafruit_ILI9341 tft(TFT_CS, TFT_DC, TFT_RST);
MFRC522 rfid(RFID_SS_PIN, RFID_RST_PIN);
Servo lockServo;
bool boxIsOpen = false;

unsigned long lastPollTime = 0;
const unsigned long POLL_INTERVAL = 2000;

unsigned long lastHeartbeatTime = 0;
const unsigned long HEARTBEAT_INTERVAL = 4000;

int batteryPercentage = 98;

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
  Serial.println("[NAV] Executing 180-degree in-place turn at Emergency Ward...");
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
void updateTFTDisplay() {
  digitalWrite(RFID_SS_PIN, HIGH);
  digitalWrite(TFT_CS, LOW);

  tft.fillScreen(ILI9341_BLACK);

  tft.drawRect(2, 2, 316, 236, ILI9341_RED);
  tft.drawRect(4, 4, 312, 232, ILI9341_MAROON);

  tft.fillRect(6, 6, 308, 32, ILI9341_RED);
  tft.setTextSize(2);
  tft.setTextColor(ILI9341_WHITE);
  tft.setCursor(14, 14);
  tft.print("BOT 2: EMERGENCY WARD");

  tft.setTextSize(1);
  tft.setCursor(240, 18);
  if (WiFi.status() == WL_CONNECTED) {
    tft.setTextColor(ILI9341_GREEN);
    tft.print("WIFI: OK");
  } else {
    tft.setTextColor(ILI9341_YELLOW);
    tft.print("WIFI: OFF");
  }

  uint16_t bannerColor = ILI9341_RED;
  String stateStr = "EMERGENCY STANDBY";

  switch (currentState) {
    case STATE_IDLE:
      bannerColor = ILI9341_DARKGREEN;
      stateStr = "READY AT BASE - STANDBY";
      break;
    case STATE_ORDER_ASSIGNED:
      bannerColor = ILI9341_ORANGE;
      stateStr = "EMERGENCY ORDER ASSIGNED";
      break;
    case STATE_READY_DISPATCH:
      bannerColor = ILI9341_RED;
      stateStr = "READY FOR EMERGENCY DISPATCH";
      break;
    case STATE_IN_TRANSIT:
      bannerColor = ILI9341_RED;
      stateStr = "PRIORITY 1: EN ROUTE TO OT";
      break;
    case STATE_ARRIVED_AT_WARD:
      bannerColor = ILI9341_MAGENTA;
      stateStr = "ARRIVED OT - SCAN RFID";
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
  tft.setCursor(16, 49);
  tft.print(stateStr);

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
  tft.setTextColor(ILI9341_RED);
  tft.setTextSize(2);
  tft.print("PRIORITY 1 (CRITICAL)");

  tft.setTextSize(1);
  tft.setTextColor(ILI9341_LIGHTGREY);
  tft.setCursor(14, 150);
  tft.print("MEDICINES   : ");
  tft.setTextColor(ILI9341_CYAN);
  tft.setCursor(14, 164);
  tft.print(currentOrder.itemsSummary.substring(0, 45));

  tft.drawLine(10, 205, 310, 205, ILI9341_DARKGREY);
  tft.setCursor(14, 214);
  tft.setTextColor(ILI9341_YELLOW);
  tft.print("Universal RFID: Base | Dedicated Card: Emergency OT");

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
        Serial.printf("[POLL] Emergency assignment found! Order: %s | Status: %s\n",
                      currentOrder.orderNumber.c_str(), status.c_str());

        JsonArray items = orderObj["items"];
        String itemsStr = "";
        for (JsonObject item : items) {
          itemsStr += item["medicine"].as<String>() + " (" + String(item["quantity"].as<int>()) + "), ";
        }
        currentOrder.itemsSummary = itemsStr;

        if (status == "READY_FOR_DISPATCH" || status == "DISPATCHED") {
          if (currentState == STATE_IDLE || currentState == STATE_ORDER_ASSIGNED) {
            currentState = STATE_IN_TRANSIT;
            lockBox();
            updateTFTDisplay();
            // Step forward off the Medical Room docking line
            moveForward();
            delay(CROSSING_CLEAR_MS);
            Serial.println("[STATE] Departing on PRIORITY 1 EMERGENCY mission to " + currentOrder.destination);
          }
        } else {
          currentState = STATE_ORDER_ASSIGNED;
          updateTFTDisplay();
        }
      } else {
        Serial.println("[POLL] Connected to server: No emergency orders waiting (Robot Idle).");
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
  Serial.printf("[WEBHOOK] Notified arrival at Emergency Ward. Response: %d\n", httpCode);
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
  Serial.printf("[WEBHOOK] Notified emergency delivery completion. Response: %d\n", httpCode);
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

  if (uid == CARD_EMERGENCY_WARD) {
    Serial.println("[RFID] Emergency Ward / OT Staff Card authenticated!");
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

  // Condition 1: Both sensors detect line -> Cross-line / Destination Stop Marker!
  if (leftOnLine && rightOnLine) {
    stopMotors();
    delay(500);

    if (currentState == STATE_IN_TRANSIT) {
      currentState = STATE_ARRIVED_AT_WARD;
      notifyArrivalAtWard();
      updateTFTDisplay();
      Serial.println("[NAV] Both IR triggered: Reached Emergency Ward / OT Destination Marker!");
    } else if (currentState == STATE_RETURNING) {
      currentState = STATE_RETURNED;
      notifyReturnedToBase();
      currentOrder.active = false;
      currentState = STATE_IDLE;
      updateTFTDisplay();
      Serial.println("[NAV] Both IR triggered: Returned and docked at Central Medicine Room!");
    }
    return;
  }

  // Condition 2: Left sensor on line, Right off line -> Steer Left
  if (leftOnLine && !rightOnLine) {
    turnLeft();
    return;
  }

  // Condition 3: Right sensor on line, Left off line -> Steer Right
  if (!leftOnLine && rightOnLine) {
    turnRight();
    return;
  }

  // Condition 4: Neither sensor directly on edge -> Move straight forward
  moveForward();
}

/* ============================ MAIN SETUP & LOOP ============================ */
void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println("\n========================================================");
  Serial.println(" HOSPITAL ROBOT 2 (EMERGENCY WARD) INITIALIZING...");
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
  Serial.println("[SYSTEM] Robot 2 ready. Standing by for emergency requisitions.");
}

void loop() {
  unsigned long now = millis();

  String cardUID = readRFIDCardUID();
  if (cardUID != "") {
    Serial.println("[RFID] Scanned UID: " + cardUID);

    if (isAuthorizedCard(cardUID)) {
      if (currentState == STATE_ARRIVED_AT_WARD) {
        // 1st scan at Emergency Ward: Unlock box for doctors/nurses
        unlockBox();
        currentState = STATE_BOX_OPEN;
        updateTFTDisplay();
        Serial.println("[RFID] 1st scan at Emergency Ward: Cargo box unlocked. Staff retrieving medicines.");
      } else if (currentState == STATE_BOX_OPEN) {
        // 2nd scan at Emergency Ward: Box closed, order complete, 180° turn on the spot!
        lockBox();
        notifyBoxClosedAndDelivered();

        Serial.println("[STATE] 2nd scan at Emergency Ward: Box closed! Order complete. Executing 180 degree turn at position...");
        delay(500);
        turn180Degrees();

        currentState = STATE_RETURNING;
        updateTFTDisplay();

        // Step forward off the Emergency Ward stop marker
        moveForward();
        delay(CROSSING_CLEAR_MS);
        Serial.println("[STATE] Box closed. Returning straight back to Central Medicine Room.");
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
