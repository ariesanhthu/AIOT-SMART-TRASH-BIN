/*
 * ARDUINO - MAIN CONTROLLER cho AIoT Smart Trash Bin 
 * (TÍCH HỢP ESP32-CAM & ĐO ĐỘ ĐẦY 3 NGĂN TỪ CẢM BIẾN CHÂN A0-A5)
 * * Sơ đồ cắm dây thực tế:
 * - Cảm biến siêu âm CẦM TAY (Kích hoạt AI): Trig -> Pin 9, Echo -> Pin 8
 * - Cảm biến siêu âm ĐO ĐỘ ĐẦY 3 NGĂN (Chiều cao thùng = 25 cm):
 * + Ngăn NHỰA:   Echo -> Pin A0, Trig -> Pin A1
 * + Ngăn GIẤY:   Echo -> Pin A2, Trig -> Pin A3
 * + Ngăn HỮU CƠ: Echo -> Pin A4, Trig -> Pin A5
 * - Servo 1 (HỮU CƠ): Tín hiệu -> Pin 10
 * - Servo 2 (GIẤY):   Tín hiệu -> Pin 11
 * - Servo 3 (NHỰA):   Tín hiệu -> Pin 7
 * * - 4 ĐÈN LED BÁO HIỆU (LẦN LƯỢT: 12, 6, 5, 4):
 * + LED Ngăn Nhựa:    Pin 12
 * + LED Ngăn Giấy:    Pin 6
 * + LED Ngăn Hữu cơ:  Pin 5
 * + LED Hộc AI:       Pin 4
 * * Kết nối truyền thông UART với ESP32-CAM:
 * - Arduino Pin 3 (TX) -> ESP32-CAM RX (Gửi "H 1", "T 1", "F nhua giay huu_co")
 * - Arduino Pin 2 (RX) -> ESP32-CAM TX (Nhận "R", "A", "C", "D")
 */

//#define TEST_MODE   // <-- THÊM/BỎ dấu // ở đầu dòng này để chuyển giữa Chế độ Test và Chế độ chạy thật với ESP32-CAM

#include <Servo.h>
#if !defined(TEST_MODE)
#include <SoftwareSerial.h>
#endif

// ==== Cấu hình Cảm biến siêu âm Cầm tay (Kích hoạt AI) ====
const int TRIG_PIN = 9;   
const int ECHO_PIN = 8;   
const int THRESHOLD_CM = 10; 
const int REARM_THRESHOLD_CM = 14; // Phải lấy vật ra khỏi hộc trước lượt mới
const unsigned long TRIGGER_SAMPLE_INTERVAL_MS = 60;
const unsigned long TRIGGER_FAULT_RETRY_INTERVAL_MS = 250;
const unsigned long TRIGGER_STATUS_INTERVAL_MS = 1000;
const unsigned long TRIGGER_VERBOSE_STATUS_INTERVAL_MS = 250;
const unsigned long TRIGGER_ECHO_TIMEOUT_US = 30000;
const byte TRIGGER_DEBOUNCE_SAMPLES = 2;

// ==== Cấu hình 3 Cảm biến siêu âm Đo Mức Đầy Thùng Rác (Chân A0 - A5) ====
const int ECHO_NHUA   = A0; 
const int TRIG_NHUA   = A1; 

const int ECHO_GIAY   = A2; 
const int TRIG_GIAY   = A3; 

const int ECHO_HUUCO  = A4; 
const int TRIG_HUUCO  = A5; 

const float BIN_HEIGHT_CM = 25.0; // Độ cao thiết kế của thùng rác (cm)
const int FULL_THRESHOLD_PERCENT = 80; // Ngưỡng báo đầy (%): >= 80% xem như đầy

// ==== Cấu hình 4 LED Báo Hiệu (12, 6, 5, 4) ====
const int LED_NHUA  = 12;  // LED ngăn Nhựa
const int LED_GIAY  = 6;   // LED ngăn Giấy
const int LED_HUUCO = 5;   // LED ngăn Hữu cơ
const int LED_AI    = 4;   // LED hộc chụp ảnh AI

// ==== Cấu hình Chân Servo ====
Servo servoHuuCo, servoGiay, servoNhua;
const int PIN_SERVO_HUUCO = 10; 
const int PIN_SERVO_GIAY  = 11; 
const int PIN_SERVO_NHUA  = 7;  

const int ANGLE_CLOSE = 0;
const int ANGLE_OPEN  = 90;
const unsigned long OPEN_DURATION_MS = 5000; // Mở Servo & Sáng đèn trong 5 giây

// ==== Cấu hình Thời gian kiểm soát luồng ====
const unsigned long READY_PROBE_INTERVAL_MS = 3000;
const unsigned long UART_ACK_TIMEOUT_MS = 1500;
const unsigned long LABEL_TIMEOUT_MS = 25000;
const unsigned long CLOUD_TIMEOUT_MS = 120000;
const unsigned long COOLDOWN_MS = 2000;       // Thời gian nghỉ giữa các lần hoạt động
const unsigned long ERROR_BLINK_MS = 3000;    // Đèn nhấp nháy chớp lỗi/đầy trong 3 giây
const unsigned long FILL_CHECK_INTERVAL_MS = 10000; // Định kỳ đo độ đầy mỗi 10s
const byte MAX_UART_ATTEMPTS = 3;

#if !defined(TEST_MODE)
const int PIN_RX = 2;
const int PIN_TX = 3;
SoftwareSerial espSerial(PIN_RX, PIN_TX);
#endif

enum State {
  STATE_WAIT_ESP_READY,
  STATE_IDLE,
  STATE_WAIT_TRIGGER_ACK,
  STATE_WAIT_LABEL,
  STATE_NANO_PROCESSING,
  STATE_WAIT_FILL_ACK,
  STATE_WAIT_CLOUD,
  STATE_COOLDOWN
};
State currentState = STATE_WAIT_ESP_READY;
unsigned long stateStartTime = 0;
unsigned long lastFillCheckTime = 0; 
unsigned long blinkStartTime = 0;
unsigned long lastTriggerSampleTime = 0;
unsigned long lastTriggerStatusTime = 0;
unsigned long servoOpenedAt = 0;
unsigned long lastTriggerPulseUs = 0;
unsigned long triggerReadCount = 0;
unsigned long triggerTimeoutCount = 0;

int activeBlinkPin = -1; // Lưu chân LED cần nhấp nháy khi có lỗi hoặc báo đầy
byte uartAttempts = 0;
byte triggerNearSamples = 0;
byte triggerClearSamples = 0;
bool triggerSensorOccupied = false;
bool pendingTrigger = false;
bool manualTriggerPending = false;
bool triggerVerboseMonitor = false;
bool lastTriggerEchoBefore = false;
bool lastTriggerEchoAfter = false;
Servo *activeServo = NULL;
int activeServoLedPin = -1;
char pendingFillMessage[16] = "";
char uartRxBuffer[16] = "";
byte uartRxLength = 0;

// Biến lưu độ đầy của 3 ngăn
int fillNhua = 0, fillGiay = 0, fillHuuCo = 0;

// Khai báo các hàm
long readUltrasonicDistance(int trigPin, int echoPin);
long readTriggerUltrasonicDistance();
void printTriggerSensorStatus(long distance, bool forcePrint);
int calculateFillPercentage(int trigPin, int echoPin);
void measureAllBins();
void sendFillDataToESP();
void resendFillDataToESP();
void updateTriggerSensor();
void readDebugCommands();
void startPendingTrigger();
void startOpenBin(Servo &s, int binLedPin, const __FlashStringHelper* name);
void finishNanoProcessing();
void closeAll();
void sendReadyProbe();
void sendTrigger();
void clearSerialBuffer();
void setAllLEDs(bool state);
void blinkSingleLED(int pin, int interval);
void startBlink(int pin);
void updateBlink();
bool readEspLine(char *output, size_t outputSize);
bool parseClassification(const char *line, int *code);
void processClassification(int code);
void handleLabel(int code);
void enterCooldown();

void setup() {
  Serial.begin(115200); 

  // Cấu hình chân cảm biến kích hoạt
  pinMode(TRIG_PIN, OUTPUT);
  digitalWrite(TRIG_PIN, LOW);
  pinMode(ECHO_PIN, INPUT);
  delay(50); // Chờ cảm biến siêu âm ổn định sau khi cấp nguồn.

  // Cấu hình chân 3 cảm biến đo độ đầy
  pinMode(TRIG_NHUA, OUTPUT);  pinMode(ECHO_NHUA, INPUT);
  pinMode(TRIG_GIAY, OUTPUT);  pinMode(ECHO_GIAY, INPUT);
  pinMode(TRIG_HUUCO, OUTPUT); pinMode(ECHO_HUUCO, INPUT);

  // Cấu hình 4 chân LED báo hiệu
  pinMode(LED_NHUA, OUTPUT);
  pinMode(LED_GIAY, OUTPUT);
  pinMode(LED_HUUCO, OUTPUT);
  pinMode(LED_AI, OUTPUT);
  
  setAllLEDs(false); // Tắt tất cả LED khi khởi động

#if !defined(TEST_MODE)
  espSerial.begin(9600);
#endif

  // Đặt góc đích trước khi attach để cả ba servo không nhảy từ xung mặc định
  // 90 độ về 0 độ cùng lúc, tránh sụt nguồn làm Nano reset khi khởi động.
  servoHuuCo.write(ANGLE_CLOSE);
  servoGiay.write(ANGLE_CLOSE);
  servoNhua.write(ANGLE_CLOSE);
  servoHuuCo.attach(PIN_SERVO_HUUCO);
  delay(150);
  servoGiay.attach(PIN_SERVO_GIAY);
  delay(150);
  servoNhua.attach(PIN_SERVO_NHUA);
  delay(150);
  closeAll();

#if defined(TEST_MODE)
  Serial.println(F("=== CHE DO TEST MODE (SERIAL MONITOR) ==="));
  Serial.println(F("Quy uoc: C 0/1/2/3, A F, D 0/1"));
  currentState = STATE_IDLE;
#else
  Serial.println(F("=== CHE DO CHAY THAT KET NOI ESP32-CAM ==="));
  Serial.println(F("Dang bat tay voi ESP32-CAM..."));
  Serial.println(F("Serial Monitor: S=do sensor ngay, M=monitor nhanh, T=ep ESP-CAM."));
#endif

  Serial.print(F("[SENSOR AI] TRIG=D9 ECHO=D8, trigger <= "));
  Serial.print(THRESHOLD_CM);
  Serial.print(F("cm, rearm >= "));
  Serial.print(REARM_THRESHOLD_CM);
  Serial.println(F("cm"));

  // Đo độ đầy ban đầu khi khởi động
  measureAllBins();

#if !defined(TEST_MODE)
  clearSerialBuffer();
  sendReadyProbe();
  stateStartTime = millis();
#endif
}

void loop() {
  // Không đo cảm biến trigger ở đây. D9/D8 chỉ được đo trong STATE_IDLE.
  // Sau khi gửi T 1, Nano dừng đo cho đến khi toàn bộ transaction hoàn tất.
  readDebugCommands();
  updateBlink();

  // Chỉ cập nhật cache khi rảnh. Không gửi F tự do vì F phải thuộc đúng
  // transaction vừa nhận kết quả C từ ESP32.
  if (currentState == STATE_IDLE && !pendingTrigger &&
      (millis() - lastFillCheckTime >= FILL_CHECK_INTERVAL_MS)) {
    measureAllBins();
    lastFillCheckTime = millis();
  }

  char line[16] = "";
  const bool hasLine = readEspLine(line, sizeof(line));

  switch (currentState) {

    case STATE_WAIT_ESP_READY: {
      if (hasLine && (strcmp_P(line, PSTR("R 1")) == 0 ||
                      (line[0] == 'D' && line[1] == ' ' &&
                       (line[2] == '0' || line[2] == '1') && line[3] == '\0'))) {
        Serial.println(F("[UART] ESP32 da san sang."));
        currentState = STATE_IDLE;
        stateStartTime = millis();
        break;
      }

      if (hasLine) {
        Serial.print(F("[UART] Bo qua khi cho ESP san sang: "));
        Serial.println(line);
      }

      if (millis() - stateStartTime >= READY_PROBE_INTERVAL_MS) {
        sendReadyProbe();
        stateStartTime = millis();
      }
      break;
    }

    case STATE_IDLE: {
      updateTriggerSensor();

      if (hasLine && strcmp_P(line, PSTR("R 1")) != 0) {
        Serial.print(F("[UART] Bo qua goi cu khi dang ranh: "));
        Serial.println(line);
      }

      if (((pendingTrigger && triggerSensorOccupied) || manualTriggerPending) &&
          activeBlinkPin == -1) {
        startPendingTrigger();
      }
      delay(2);
      break;
    }

    case STATE_WAIT_TRIGGER_ACK: {
      int code = -1;
      if (hasLine && strcmp_P(line, PSTR("A T")) == 0) {
        Serial.println(F("[UART] ESP da ACK trigger, dang chup/phan loai..."));
        stateStartTime = millis();
        currentState = STATE_WAIT_LABEL;
      }
      // Tương thích nếu C tới ngay hoặc firmware ESP cũ chưa có ACK.
      else if (hasLine && parseClassification(line, &code)) {
        processClassification(code);
      }
      else if (hasLine) {
        Serial.print(F("[UART] Goi khong mong doi khi cho ACK T: "));
        Serial.println(line);
      }
      else if (millis() - stateStartTime >= UART_ACK_TIMEOUT_MS) {
        if (uartAttempts < MAX_UART_ATTEMPTS) {
          ++uartAttempts;
          Serial.print(F("[UART] Khong co ACK T, gui lai lan "));
          Serial.println(uartAttempts);
          sendTrigger();
          stateStartTime = millis();
        }
        else {
          Serial.println(F("[!] ESP khong ACK trigger; quay lai bat tay."));
          digitalWrite(LED_AI, LOW);
          startBlink(LED_AI);
          pendingTrigger = triggerSensorOccupied;
          sendReadyProbe();
          stateStartTime = millis();
          currentState = STATE_WAIT_ESP_READY;
        }
      }
      break;
    }

    case STATE_WAIT_LABEL: {
      int code = -1;
      if (hasLine && parseClassification(line, &code)) {
        processClassification(code);
      }
      else if (hasLine && strcmp_P(line, PSTR("A T")) != 0) {
        Serial.print(F("[UART] Goi khong mong doi khi cho C: "));
        Serial.println(line);
      }
      else if (!hasLine && millis() - stateStartTime >= LABEL_TIMEOUT_MS) {
        Serial.println(F("[!] Timeout chup/phan loai; quay lai bat tay."));
        digitalWrite(LED_AI, LOW);
        startBlink(LED_AI);
        pendingTrigger = triggerSensorOccupied;
        sendReadyProbe();
        stateStartTime = millis();
        currentState = STATE_WAIT_ESP_READY;
      }
      break;
    }

    case STATE_NANO_PROCESSING: {
      if (hasLine) {
        Serial.print(F("[UART] Goi den khi Nano dang xu ly: "));
        Serial.println(line);
      }

      if (activeServo != NULL && millis() - servoOpenedAt >= OPEN_DURATION_MS) {
        activeServo->write(ANGLE_CLOSE);
        if (activeServoLedPin != -1) {
          digitalWrite(activeServoLedPin, LOW);
        }
        activeServo = NULL;
        activeServoLedPin = -1;
        Serial.println(F("-> Da dong nap thung rac."));
      }

      // Chỉ gửi F sau khi servo đã đóng hoặc chu kỳ cảnh báo đã kết thúc.
      if (activeServo == NULL && activeBlinkPin == -1) {
        finishNanoProcessing();
      }
      break;
    }

    case STATE_WAIT_FILL_ACK: {
      if (hasLine && strcmp_P(line, PSTR("A F")) == 0) {
        Serial.println(F("[UART] ESP da nhan muc day; dang sync cloud..."));
        stateStartTime = millis();
        currentState = STATE_WAIT_CLOUD;
      }
      else if (hasLine && line[0] == 'D' && line[1] == ' ' &&
               (line[2] == '0' || line[2] == '1') && line[3] == '\0') {
        Serial.println(strcmp_P(line, PSTR("D 1")) == 0
                           ? F("[CLOUD] Dong bo thanh cong.")
                           : F("[CLOUD] Dong bo that bai; ESP da ranh."));
        enterCooldown();
      }
      else if (hasLine) {
        Serial.print(F("[UART] Goi khong mong doi khi cho ACK F: "));
        Serial.println(line);
      }
      else if (millis() - stateStartTime >= UART_ACK_TIMEOUT_MS) {
        if (uartAttempts < MAX_UART_ATTEMPTS) {
          ++uartAttempts;
          Serial.print(F("[UART] Khong co ACK F, gui lai lan "));
          Serial.println(uartAttempts);
          resendFillDataToESP();
          stateStartTime = millis();
        }
        else {
          // Có thể ACK bị mất nhưng ESP đã nhận F và đang upload. Tiếp tục chờ D.
          Serial.println(F("[UART] Mat ACK F; tiep tuc cho ket qua cloud."));
          stateStartTime = millis();
          currentState = STATE_WAIT_CLOUD;
        }
      }
      break;
    }

    case STATE_WAIT_CLOUD: {
      if (hasLine && line[0] == 'D' && line[1] == ' ' &&
          (line[2] == '0' || line[2] == '1') && line[3] == '\0') {
        Serial.println(strcmp_P(line, PSTR("D 1")) == 0
                           ? F("[CLOUD] Cloudinary + Firestore thanh cong.")
                           : F("[CLOUD] Sync loi; local van hoan tat."));
        enterCooldown();
      }
      else if (hasLine && strcmp_P(line, PSTR("A F")) != 0) {
        Serial.print(F("[UART] Goi khong mong doi khi cho cloud: "));
        Serial.println(line);
      }
      else if (!hasLine && millis() - stateStartTime >= CLOUD_TIMEOUT_MS) {
        Serial.println(F("[!] Timeout cloud; bat tay lai voi ESP."));
        startBlink(LED_AI);
        sendReadyProbe();
        stateStartTime = millis();
        currentState = STATE_WAIT_ESP_READY;
      }
      break;
    }

    case STATE_COOLDOWN: {
      if (hasLine) {
        Serial.print(F("[UART] Goi den trong cooldown: "));
        Serial.println(line);
      }
      if (millis() - stateStartTime >= COOLDOWN_MS) {
        currentState = STATE_IDLE;
        Serial.println(F("--- San sang cho luot tiep theo ---\n"));
      }
      break;
    }
  }
}

// ==== BẬT / TẮT ĐỒNG THỜI CẢ 4 LED ====
void setAllLEDs(bool state) {
  digitalWrite(LED_NHUA, state ? HIGH : LOW);
  digitalWrite(LED_GIAY, state ? HIGH : LOW);
  digitalWrite(LED_HUUCO, state ? HIGH : LOW);
  digitalWrite(LED_AI, state ? HIGH : LOW);
}

// ==== NHẤP NHÁY 1 LED CHỈ ĐỊNH KHÔNG TREO MẠCH ====
void blinkSingleLED(int pin, int interval) {
  unsigned long currentMillis = millis();
  bool state = ((currentMillis / interval) % 2 == 0);
  digitalWrite(pin, state ? HIGH : LOW);
}

void startBlink(int pin) {
  if (activeBlinkPin != -1 && activeBlinkPin != pin) {
    digitalWrite(activeBlinkPin, LOW);
  }
  activeBlinkPin = pin;
  blinkStartTime = millis();
}

void updateBlink() {
  if (activeBlinkPin == -1) return;

  if (millis() - blinkStartTime >= ERROR_BLINK_MS) {
    digitalWrite(activeBlinkPin, LOW);
    activeBlinkPin = -1;
    return;
  }
  blinkSingleLED(activeBlinkPin, 200);
}

// ==== HÀM ĐO KHOẢNG CÁCH SIÊU ÂM ====
long readUltrasonicDistance(int trigPin, int echoPin) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(5);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(12);
  digitalWrite(trigPin, LOW);

  const unsigned long duration = pulseIn(echoPin, HIGH, TRIGGER_ECHO_TIMEOUT_US);
  if (duration == 0) return -1; 
  return duration / 58; // Quy đổi ra cm
}

long readTriggerUltrasonicDistance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(5);
  lastTriggerEchoBefore = digitalRead(ECHO_PIN) == HIGH;

  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(12);
  digitalWrite(TRIG_PIN, LOW);

  lastTriggerPulseUs = pulseIn(ECHO_PIN, HIGH, TRIGGER_ECHO_TIMEOUT_US);
  lastTriggerEchoAfter = digitalRead(ECHO_PIN) == HIGH;
  ++triggerReadCount;

  if (lastTriggerPulseUs == 0) {
    ++triggerTimeoutCount;
    return -1;
  }
  return (lastTriggerPulseUs + 29UL) / 58UL;
}

void printTriggerSensorStatus(long distance, bool forcePrint) {
  const unsigned long now = millis();
  const unsigned long interval = triggerVerboseMonitor
                                     ? TRIGGER_VERBOSE_STATUS_INTERVAL_MS
                                     : TRIGGER_STATUS_INTERVAL_MS;
  if (!forcePrint && now - lastTriggerStatusTime < interval) return;
  lastTriggerStatusTime = now;

  Serial.print(F("[HC-SR04 TEST D9/D8] echo_before="));
  Serial.print(lastTriggerEchoBefore ? F("HIGH") : F("LOW"));
  Serial.print(F(" pulse="));
  Serial.print(lastTriggerPulseUs);
  Serial.print(F("us echo_after="));
  Serial.print(lastTriggerEchoAfter ? F("HIGH") : F("LOW"));

  if (distance > 0) {
    Serial.print(F(" distance="));
    Serial.print(distance);
    Serial.print(F("cm"));
  } else if (lastTriggerEchoAfter) {
    Serial.print(F(" result=ECHO_STUCK_HIGH auto_trigger=BLOCKED"));
  } else {
    Serial.print(F(" result=NO_ECHO auto_trigger=BLOCKED"));
  }

  Serial.print(F(" timeout="));
  Serial.print(triggerTimeoutCount);
  Serial.print('/');
  Serial.print(triggerReadCount);
  Serial.print(F(" occupied="));
  Serial.print(triggerSensorOccupied ? 1 : 0);
  Serial.print(F(" pending="));
  Serial.print((pendingTrigger || manualTriggerPending) ? 1 : 0);
  Serial.print(F(" state="));
  Serial.println((int)currentState);
}

void updateTriggerSensor() {
  const unsigned long now = millis();
  const unsigned long sampleInterval =
      (triggerReadCount > 0 && lastTriggerPulseUs == 0)
          ? TRIGGER_FAULT_RETRY_INTERVAL_MS
          : TRIGGER_SAMPLE_INTERVAL_MS;
  if (now - lastTriggerSampleTime < sampleInterval) return;
  lastTriggerSampleTime = now;

  const long distance = readTriggerUltrasonicDistance();
  printTriggerSensorStatus(distance, false);

  if (distance > 0 && distance <= THRESHOLD_CM) {
    triggerClearSamples = 0;
    if (triggerNearSamples < TRIGGER_DEBOUNCE_SAMPLES) {
      ++triggerNearSamples;
    }

    if (!triggerSensorOccupied &&
        triggerNearSamples >= TRIGGER_DEBOUNCE_SAMPLES) {
      triggerSensorOccupied = true;
      pendingTrigger = true;
      Serial.print(F("[SENSOR] Phat hien rac o "));
      Serial.print(distance);
      Serial.println(F(" cm; da ghi nhan trigger."));
    }
    return;
  }

  if (distance >= REARM_THRESHOLD_CM) {
    triggerNearSamples = 0;
    if (triggerClearSamples < TRIGGER_DEBOUNCE_SAMPLES) {
      ++triggerClearSamples;
    }

    if (triggerSensorOccupied &&
        triggerClearSamples >= TRIGGER_DEBOUNCE_SAMPLES) {
      triggerSensorOccupied = false;
      // Nếu rác rời hộc trước khi pending được xử lý thì không chụp ảnh rỗng.
      if (pendingTrigger) {
        pendingTrigger = false;
        Serial.println(F("[SENSOR] Rac da roi hoc; huy trigger dang cho."));
      }
      Serial.println(F("[SENSOR] Hoc AI da trong, san sang nhan rac moi."));
    }
    return;
  }

  // Vùng 10..13 cm là hysteresis; timeout echo cũng không được coi là rác
  // mới hoặc là hộc đã trống.
  if (distance > 0) {
    triggerNearSamples = 0;
    triggerClearSamples = 0;
  }
}

void readDebugCommands() {
#if !defined(TEST_MODE)
  while (Serial.available() > 0) {
    const int command = Serial.read();
    if (command == 'T' || command == 't') {
      if (currentState == STATE_IDLE) {
        manualTriggerPending = true;
        Serial.println(F("[TEST] Da xep trigger thu cong cho ESP-CAM."));
      } else {
        Serial.println(F("[TEST] Bo qua T: transaction dang xu ly."));
      }
    }
    else if (command == 'S' || command == 's') {
      const long distance = readTriggerUltrasonicDistance();
      printTriggerSensorStatus(distance, true);
    }
    else if (command == 'M' || command == 'm') {
      triggerVerboseMonitor = !triggerVerboseMonitor;
      Serial.println(triggerVerboseMonitor
                         ? F("[TEST] Monitor sensor nhanh: ON (250ms).")
                         : F("[TEST] Monitor sensor nhanh: OFF (1000ms)."));
    }
    else if (command == '?') {
      Serial.println(F("[TEST] S=do ngay, M=monitor nhanh, T=ep ESP-CAM."));
    }
  }
#endif
}

void startPendingTrigger() {
  const bool isManualTrigger = manualTriggerPending;
  pendingTrigger = false;
  manualTriggerPending = false;
  Serial.println(isManualTrigger
                     ? F("\n[MANUAL TRIGGER] Yeu cau ESP chup...")
                     : F("\n[AUTO TRIGGER] Cam bien phat hien rac; yeu cau ESP chup..."));
  clearSerialBuffer();
  uartAttempts = 1;
  sendTrigger();
  stateStartTime = millis();
  currentState = STATE_WAIT_TRIGGER_ACK;
}

// ==== HÀM TÍNH PHẦN TRĂM ĐỘ ĐẦY THÙNG RÁC (%) ====
int calculateFillPercentage(int trigPin, int echoPin) {
  long distance = readUltrasonicDistance(trigPin, echoPin);
  
  if (distance <= 0) return -1; // Không coi cảm biến lỗi là ngăn trống
  if (distance >= BIN_HEIGHT_CM) return 0; // Trống hoàn toàn
  
  float fillPercent = ((BIN_HEIGHT_CM - (float)distance) / BIN_HEIGHT_CM) * 100.0;
  
  if (fillPercent < 0) fillPercent = 0;
  if (fillPercent > 100) fillPercent = 100;

  return (int)fillPercent;
}

// ==== ĐO ĐỘ ĐẦY CẢ 3 NGĂN ====
void measureAllBins() {
  const int measuredNhua = calculateFillPercentage(TRIG_NHUA, ECHO_NHUA);
  const int measuredGiay = calculateFillPercentage(TRIG_GIAY, ECHO_GIAY);
  const int measuredHuuCo = calculateFillPercentage(TRIG_HUUCO, ECHO_HUUCO);

  // Giữ giá trị hợp lệ gần nhất nếu một cảm biến tạm thời timeout.
  if (measuredNhua >= 0) fillNhua = measuredNhua;
  if (measuredGiay >= 0) fillGiay = measuredGiay;
  if (measuredHuuCo >= 0) fillHuuCo = measuredHuuCo;
}

// ==== GỬI CHUỖI F DUNG TÍCH SANG ESP32-CAM ====
void sendFillDataToESP() {
  snprintf(pendingFillMessage, sizeof(pendingFillMessage), "F %d %d %d",
           fillNhua, fillGiay, fillHuuCo);
  resendFillDataToESP();
}

void resendFillDataToESP() {
  Serial.print(F("[UART] Gui dung tich len ESP32: "));
  Serial.println(pendingFillMessage);

#if !defined(TEST_MODE)
  espSerial.println(pendingFillMessage);
#endif
}

void sendReadyProbe() {
#if defined(TEST_MODE)
  Serial.println(F("[UART] TEST: H 1"));
#else
  Serial.println(F("[UART] Kiem tra ESP san sang: H 1"));
  espSerial.println(F("H 1"));
#endif
}

// ==== PHÁT TÍN HIỆU KÍCH HOẠT CHỤP CẢNH (T 1) ====
void sendTrigger() {
  digitalWrite(LED_AI, HIGH); // Bật sáng LED Hộc AI trợ sáng chụp ảnh

#if defined(TEST_MODE)
  Serial.println(F("[UART] TEST: T 1"));
  Serial.println(F("-> Nhap C 0/1/2/3:"));
#else
  Serial.println(F("[UART] Gui T 1 sang ESP32-CAM..."));
  espSerial.println(F("T 1"));
#endif
}

// ==== XÓA BỘ ĐỆM SERIAL ====
void clearSerialBuffer() {
#if defined(TEST_MODE)
  while (Serial.available() > 0) Serial.read(); 
#else
  while (espSerial.available() > 0) espSerial.read(); 
#endif
  uartRxLength = 0;
  uartRxBuffer[0] = '\0';
}

// ==== ĐỌC MỘT DÒNG UART KHÔNG BLOCKING ====
bool readEspLine(char *output, size_t outputSize) {
  if (output == NULL || outputSize == 0) return false;

  while (true) {
    int availableBytes = 0;
#if defined(TEST_MODE)
    availableBytes = Serial.available();
#else
    availableBytes = espSerial.available();
#endif
    if (availableBytes <= 0) return false;

#if defined(TEST_MODE)
    const int received = Serial.read();
#else
    const int received = espSerial.read();
#endif

    if (received == '\r' || received == '\n') {
      if (uartRxLength == 0) continue;

      uartRxBuffer[uartRxLength] = '\0';
      strncpy(output, uartRxBuffer, outputSize - 1);
      output[outputSize - 1] = '\0';
      uartRxLength = 0;
      uartRxBuffer[0] = '\0';
      return true;
    }

    if (received < 32 || received > 126) {
      uartRxLength = 0;
      uartRxBuffer[0] = '\0';
      continue;
    }

    if ((size_t)uartRxLength + 1U >= sizeof(uartRxBuffer)) {
      uartRxLength = 0;
      uartRxBuffer[0] = '\0';
      Serial.println(F("[UART] Dong ESP qua dai, da huy."));
      continue;
    }

    uartRxBuffer[uartRxLength++] = (char)received;
    uartRxBuffer[uartRxLength] = '\0';
  }
}

bool parseClassification(const char *line, int *code) {
  if (line == NULL || code == NULL) return false;
  if (line[0] != 'C' || line[1] != ' ' || line[3] != '\0') return false;
  if (line[2] < '0' || line[2] > '3') return false;
  *code = line[2] - '0';
  return true;
}

void processClassification(int code) {
  Serial.print(F("[UART] Nhan ket qua phan loai C "));
  Serial.println(code);
  digitalWrite(LED_AI, LOW);

  if (code == 0) {
    Serial.println(F("[!] AI khong nhan dien; khong mo ngan."));
    startBlink(LED_AI);
  }
  else {
    handleLabel(code);
  }

  // STATE_NANO_PROCESSING đợi servo đóng hoặc cảnh báo kết thúc. F tuyệt đối
  // không được gửi trước thời điểm đó.
  stateStartTime = millis();
  currentState = STATE_NANO_PROCESSING;
}

// ==== XỬ LÝ KIỂM TRA ĐẦY & MỞ NẮP CHO TỪNG LOẠI RÁC ====
void handleLabel(int code) {
  if (code == 1) {
    // Ngăn Nhựa
    int currentFill = calculateFillPercentage(TRIG_NHUA, ECHO_NHUA);
    Serial.print(F("-> Ngan Nhua day: ")); Serial.print(currentFill); Serial.println(F("%"));

    if (currentFill < 0) {
      Serial.println(F("[!] Loi cam bien NHUA -> khong mo nap."));
      startBlink(LED_NHUA);
    } else if (currentFill >= FULL_THRESHOLD_PERCENT) {
      Serial.println(F("[!] Ngan NHUA da day."));
      fillNhua = currentFill;
      startBlink(LED_NHUA);
    } else {
      fillNhua = currentFill;
      startOpenBin(servoNhua, LED_NHUA, F("NGAN NHUA"));
    }
  } 
  else if (code == 2) {
    // Ngăn Giấy
    int currentFill = calculateFillPercentage(TRIG_GIAY, ECHO_GIAY);
    Serial.print(F("-> Ngan Giay day: ")); Serial.print(currentFill); Serial.println(F("%"));

    if (currentFill < 0) {
      Serial.println(F("[!] Loi cam bien GIAY -> khong mo nap."));
      startBlink(LED_GIAY);
    } else if (currentFill >= FULL_THRESHOLD_PERCENT) {
      Serial.println(F("[!] Ngan GIAY da day."));
      fillGiay = currentFill;
      startBlink(LED_GIAY);
    } else {
      fillGiay = currentFill;
      startOpenBin(servoGiay, LED_GIAY, F("NGAN GIAY"));
    }
  } 
  else if (code == 3) {
    // Ngăn Hữu cơ
    int currentFill = calculateFillPercentage(TRIG_HUUCO, ECHO_HUUCO);
    Serial.print(F("-> Ngan Huu co day: ")); Serial.print(currentFill); Serial.println(F("%"));

    if (currentFill < 0) {
      Serial.println(F("[!] Loi cam bien HUU CO -> khong mo nap."));
      startBlink(LED_HUUCO);
    } else if (currentFill >= FULL_THRESHOLD_PERCENT) {
      Serial.println(F("[!] Ngan HUU CO da day."));
      fillHuuCo = currentFill;
      startBlink(LED_HUUCO);
    } else {
      fillHuuCo = currentFill;
      startOpenBin(servoHuuCo, LED_HUUCO, F("NGAN HUU CO"));
    }
  }
}

// ==== BẮT ĐẦU MỞ SERVO KHÔNG BLOCKING ====
void startOpenBin(Servo &s, int binLedPin, const __FlashStringHelper* name) {
  Serial.print(F("-> Dang mo: "));
  Serial.println(name);

  activeServo = &s;
  activeServoLedPin = binLedPin;
  servoOpenedAt = millis();
  digitalWrite(binLedPin, HIGH);
  s.write(ANGLE_OPEN);
}

void finishNanoProcessing() {
  // Đo sau khi nắp đã đóng/cảnh báo đã xong để Firestore nhận trạng thái cuối
  // cùng của chính transaction này.
  Serial.println(F("-> Nano xu ly xong; cap nhat dung tich 3 ngan..."));
  measureAllBins();
  sendFillDataToESP();
  uartAttempts = 1;
  stateStartTime = millis();
  currentState = STATE_WAIT_FILL_ACK;
}

void enterCooldown() {
  stateStartTime = millis();
  currentState = STATE_COOLDOWN;
}

// ==== ĐÓNG TOÀN BỘ NẮP ====
void closeAll() {
  servoHuuCo.write(ANGLE_CLOSE);
  servoGiay.write(ANGLE_CLOSE);
  servoNhua.write(ANGLE_CLOSE);
}
