========================================================================================
HOSPITAL MEDICINE ORDERING & AUTONOMOUS ROBOT DELIVERY MANAGEMENT SYSTEM
NEW PC SETUP & INSTALLATION GUIDE
========================================================================================

Follow these step-by-step instructions to set up and run the entire system on a new PC
or laptop from scratch.

----------------------------------------------------------------------------------------
SECTION 1: SOFTWARE PREREQUISITES
----------------------------------------------------------------------------------------
Before starting, ensure the new PC has the following installed:

1. Python (Version 3.10, 3.11, or 3.12)
   - Download from: https://www.python.org/downloads/
   - IMPORTANT: During installation, make sure to check the box:
     [x] "Add Python to PATH"

2. Arduino IDE (Version 2.0 or higher)
   - Download from: https://www.arduino.cc/en/software

3. CP2102 or CH340 USB-to-UART Driver (if ESP32 COM port is not recognized)
   - Most Windows 10/11 PCs detect it automatically upon plugging in the ESP32.

----------------------------------------------------------------------------------------
SECTION 2: PYTHON BACKEND & DATABASE SETUP
----------------------------------------------------------------------------------------
1. Copy or extract the project folder onto the new PC (e.g., Desktop or C:\Projects).
2. Open Windows PowerShell or Command Prompt (CMD).
3. Navigate into the project directory:
   cd "c:\path\to\hospital medicine transport bot"

4. Create a fresh Python virtual environment:
   python -m venv .venv

5. Activate the virtual environment:
   - On Windows PowerShell:
     .\.venv\Scripts\Activate.ps1
     (Note: If PowerShell shows an Execution Policy error, run:
      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
      and then run the activate command again).
   - On Command Prompt (CMD):
     .venv\Scripts\activate.bat

6. Install all required dependencies:
   pip install -r requirements.txt

7. Verify installation by running automated test suite:
   pytest -v
   (All 14 tests should show green PASSED).

8. Seed initial demo users, medicine inventory, and robot fleet:
   python seed.py
   (This creates the database at 'instance/hospital.db' with all demo accounts).

----------------------------------------------------------------------------------------
SECTION 3: FINDING YOUR LAPTOP WI-FI IP ADDRESS
----------------------------------------------------------------------------------------
Both your laptop and your ESP32 robots MUST be connected to the SAME Wi-Fi network
(or mobile hotspot).

1. In PowerShell or Command Prompt, run:
   ipconfig

2. Look under "Wireless LAN adapter Wi-Fi":
   IPv4 Address . . . . . . . . . . . : 192.168.X.X
   (Note this IP down! For example: 192.168.1.10)

----------------------------------------------------------------------------------------
SECTION 4: STARTING THE WEB SERVER
----------------------------------------------------------------------------------------
1. Inside the project folder with virtual environment activated, run:
   python app.py

2. You will see:
   * Hospital Medicine Delivery System running on http://0.0.0.0:5000
   * Accessible on Wi-Fi at http://<your-laptop-ip>:5000

3. Keep this terminal window OPEN while using the system.

----------------------------------------------------------------------------------------
SECTION 5: ARDUINO IDE SETUP FOR ESP32 BOTS
----------------------------------------------------------------------------------------
1. Add ESP32 Board Support:
   - Open Arduino IDE -> File -> Preferences.
   - In "Additional Boards Manager URLs", add:
     https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   - Go to Tools -> Board -> Boards Manager...
   - Search for "esp32" by Espressif Systems and click "Install".

2. Install Required Arduino Libraries:
   In Arduino IDE, go to Sketch -> Include Library -> Manage Libraries...
   Search and install each of these 5 libraries:
   a) "Adafruit ILI9341" by Adafruit (for SPI TFT Display)
   b) "Adafruit GFX Library" by Adafruit
   c) "MFRC522" by GithubCommunity (for RC522 RFID reader)
   d) "ESP32Servo" by Kevin Harrington (for servo cargo lock)
   e) "ArduinoJson" by Benoit Blanchon (version 6.x or 7.x)

----------------------------------------------------------------------------------------
SECTION 6: CONFIGURING & UPLOADING FIRMWARE TO BOTS
----------------------------------------------------------------------------------------
There are two firmware sketches in the project:
  - bot_general/bot_general.ino       (Robot 1: General Ward 1 & General Ward 2)
  - bot_emergency/bot_emergency.ino   (Robot 2: Dedicated Emergency Ward / OT)

Before uploading to an ESP32:
1. Open the sketch in Arduino IDE (e.g., bot_general/bot_general.ino).
2. At the top of the file, update lines 27 to 31 with your Wi-Fi details:

   const char* WIFI_SSID     = "Your_WiFi_Name";        // Your Wi-Fi / Hotspot SSID
   const char* WIFI_PASSWORD = "Your_WiFi_Password";    // Your Wi-Fi Password
   const char* SERVER_BASE_URL = "http://192.168.X.X:5000"; // Laptop IP from Section 3

3. Connect your ESP32 board to the PC via USB cable.
4. In Arduino IDE:
   - Tools -> Board -> "ESP32 Dev Module"
   - Tools -> Port -> Select your ESP32 COM Port (e.g. COM3, COM4, COM5)
5. Click "Upload" (Ctrl + U).
6. Repeat the same for Bot 2 (bot_emergency/bot_emergency.ino) if using both robots.

----------------------------------------------------------------------------------------
SECTION 7: HARDWARE PINOUT QUICK REFERENCE
----------------------------------------------------------------------------------------
Both robots use the exact same tested hardware pin configuration:

- 2-Channel IR Line Sensors:
    Left IR Sensor   -> GPIO 13
    Right IR Sensor  -> GPIO 27

- Servo Cargo Lock:
    Signal Pin       -> GPIO 15  (Closed/Locked = 45 deg, Open/Unlocked = 90 deg)

- RC522 RFID Reader:
    SDA / SS         -> GPIO 5
    RST              -> GPIO 26
    SCK              -> GPIO 18 (Shared SPI)
    MISO             -> GPIO 19 (Shared SPI)
    MOSI             -> GPIO 23 (Shared SPI)
    VCC              -> 3.3V (Do not connect to 5V!)

- ILI9341 2.8"/2.4" SPI TFT LCD:
    CS               -> GPIO 21
    DC               -> GPIO 22
    RESET            -> GPIO 2
    SCK              -> GPIO 18 (Shared SPI)
    MISO             -> GPIO 19 (Shared SPI)
    MOSI             -> GPIO 23 (Shared SPI)

- L298N Motor Driver:
    ENA (Speed Left) -> GPIO 3 (RX0)
    ENB (Speed Right)-> GPIO 1 (TX0)
    IN1              -> GPIO 17
    IN2              -> GPIO 16
    IN3              -> GPIO 14
    IN4              -> GPIO 12

----------------------------------------------------------------------------------------
SECTION 8: DEFAULT DEMO LOGIN CREDENTIALS
----------------------------------------------------------------------------------------
Access URL: http://localhost:5000 (or http://<laptop-ip>:5000 on mobile devices)

+-----------------------+---------------+---------------+-----------------------------------+
| Role / Station        | Username      | Password      | Accessible Interface              |
+-----------------------+---------------+---------------+-----------------------------------+
| System Administrator  | admin         | admin123      | /admin (Full management console)  |
| Medicine Room Manager | manager       | manager123    | /manager (Queue & Dispatch board) |
| Emergency Ward / OT   | emergency     | emergency123  | /room/emergency (Priority 1 cart) |
| General Ward 1        | ward1         | ward1123      | /room/general_1 (Priority 2 cart) |
| General Ward 2        | ward2         | ward2123      | /room/general_2 (Priority 3 cart) |
+-----------------------+---------------+---------------+-----------------------------------+

* TIP FOR TESTING MULTIPLE ROLES ON ONE LAPTOP:
  - Normal Browser Tab  : Log in as 'manager'
  - Incognito Window    : Log in as 'ward1' or 'ward2'
  - Different Browser   : Log in as 'admin' or 'emergency'
  (Or open http://<laptop-ip>:5000 on your smartphone to test as a mobile nurse tablet!)

----------------------------------------------------------------------------------------
SECTION 9: STEP-BY-STEP OPERATION WORKFLOW
----------------------------------------------------------------------------------------
1. ORDERING:
   - Nurse logs in as 'ward1' or 'ward2' (or 'emergency').
   - Adds medicines to cart and clicks "Place Order".
   - Stock is automatically reserved in the database.

2. PREPARATION & LOADING (Medicine Room):
   - Pharmacy Manager opens the Manager Dashboard.
   - Order appears in the priority queue (Emergency = P1, Ward 1 = P2, Ward 2 = P3).
   - Manager clicks "Accept Order".
   - Manager scans the Universal Manager Card on the robot RFID reader:
     * Scan 1: Cargo box unlocks and opens (90 deg) -> TFT displays "BOX: OPEN".
     * Manager loads the medicines into the cargo box.
     * Scan 2: Cargo box closes and locks (45 deg) -> TFT displays "BOX: CLOSED".
   - Manager checks "Confirm Medicines Loaded", assigns Robot 1 (R1), and clicks "Dispatch Robot".

3. AUTONOMOUS ROBOT DELIVERY:
   - ESP32 polls the server over Wi-Fi, detects status DISPATCHED, and displays the
     Order ID, Destination Ward, and Medicines manifest on its TFT screen.
   - Bot steps off the base and begins line tracking.
   - At "Stop for decision" intersection:
     * If destination is Ward 1: Pauses, continues straight across intersection.
     * If destination is Ward 2: Pauses, turns 90 degrees right into Ward 2 path.
   - Robot reaches Ward destination marker and halts. Webhook marks status as "ARRIVED".

4. HANDOVER & COMPLETION:
   - Ward nurse taps their Ward RFID card on the robot:
     * Scan 1: Box lid unlocks and opens (90 deg). Nurse removes medicines.
     * Scan 2: Box lid locks (45 deg). Order marked COMPLETE!
   - Robot takes a 180-degree in-place turn at the same spot.
   - Robot travels back towards Medical Room:
     * If returning from Ward 1: Ignores the decision point stop and passes straight through.
     * If returning from Ward 2: Turns 90 degrees left towards Medical Room.
   - Robot hits Medical Room dock marker and stops. Notifies server as "RETURNED".
   - Robot becomes AVAILABLE for next queued order!

----------------------------------------------------------------------------------------
SECTION 10: TROUBLESHOOTING & COMMON ISSUES
----------------------------------------------------------------------------------------
Issue 1: Bot TFT screen shows "WIFI: OFF" in Red
  - Solution: Ensure the laptop and ESP32 are both connected to a 2.4 GHz Wi-Fi network.
    ESP32 does NOT support 5 GHz Wi-Fi. Double check WIFI_SSID and WIFI_PASSWORD spelling.

Issue 2: Bot connects to Wi-Fi but doesn't get orders
  - Solution: Verify SERVER_BASE_URL has your laptop's actual IPv4 address (e.g. 192.168.1.10)
    and NOT 127.0.0.1 or localhost. Ensure port :5000 is included.
  - Test from your phone browser: Open http://<laptop-ip>:5000. If it opens, the bot can
    reach it too.

Issue 3: Windows Firewall blocks incoming connection
  - Solution: In Windows Defender Firewall -> "Allow an app through firewall" -> ensure
    "python.exe" is checked for both Private and Public networks.

Issue 4: Arduino IDE upload fails ("Failed to connect to ESP32")
  - Solution: When Arduino IDE displays "Connecting........_____", press and hold the "BOOT"
    button on the ESP32 board for 2 seconds until the upload starts.
========================================================================================