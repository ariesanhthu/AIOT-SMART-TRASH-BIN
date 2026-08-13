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

const float BIN_HEIGHT_CM = 17.0; // Độ cao thiết kế của thùng rác (cm)
// Cảm biến đặt trên nắp: chiều cao rác = chiều cao thùng - khoảng cách đo được.
// Ngưỡng đầy mặc định tương đương 10/17 cm ~= 59%, rồi ESP cập nhật từ dashboard.
const byte DEFAULT_FULL_THRESHOLD_PERCENT = 59;

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
const unsigned long OPEN_DURATION_MS = 5000; // Mở servo trong 5 giây
const unsigned long POST_CLOSE_SETTLE_MS = 1000; // Chờ 1s sau khi đóng rồi đo lần 2

// ==== Cấu hình Thời gian kiểm soát luồng ====
const unsigned long READY_PROBE_INTERVAL_MS = 3000;
const unsigned long TRIGGER_ACK_TIMEOUT_MS = 3500;
const unsigned long FILL_ACK_TIMEOUT_MS = 2000;
const unsigned long LABEL_TIMEOUT_MS = 25000;
const unsigned long SERVER_UPLOAD_TIMEOUT_MS = 30000;
const unsigned long COOLDOWN_MS = 2000;       // Thời gian nghỉ giữa các lần hoạt động
const unsigned long CLASSIFICATION_BLINK_MS = 3000; // LED ngăn được phân loại nhấp nháy trong 3 giây
const unsigned long CLASSIFICATION_LED_TOGGLE_MS = 200;
const unsigned long AI_LOADING_TOGGLE_MS = 1000;
const unsigned long AI_ERROR_TOGGLE_MS = 250;
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
  STATE_WAIT_SERVER,
  STATE_COOLDOWN
};
State currentState = STATE_WAIT_ESP_READY;

enum AiLedState {
  AI_LED_LOADING,
  AI_LED_READY,
  AI_LED_ERROR
};
AiLedState aiLedState = AI_LED_LOADING;
unsigned long stateStartTime = 0;
unsigned long lastFillCheckTime = 0; 
unsigned long blinkStartTime = 0;
unsigned long lastTriggerSampleTime = 0;
unsigned long lastTriggerStatusTime = 0;
unsigned long servoOpenedAt = 0;
unsigned long servoClosedAt = 0;
unsigned long lastTriggerPulseUs = 0;
unsigned long triggerReadCount = 0;
unsigned long triggerTimeoutCount = 0;

int activeBlinkPin = -1; // LED ngăn đang nhấp nháy để báo kết quả phân loại
byte uartAttempts = 0;
byte triggerNearSamples = 0;
byte triggerClearSamples = 0;
bool triggerSensorOccupied = false;
bool pendingTrigger = false;
bool manualTriggerPending = false;
bool triggerVerboseMonitor = false;
bool lastTriggerEchoBefore = false;
bool lastTriggerEchoAfter = false;
bool lastClassificationSucceeded = false;
bool maintenanceMode = false;
bool binFullNhua = false;
bool binFullGiay = false;
bool binFullHuuCo = false;
bool postCloseMeasurementPending = false;
Servo *activeServo = NULL;
char pendingFillMessage[16] = "";
char uartRxBuffer[24] = "";
byte uartRxLength = 0;

// Biến lưu độ đầy của 3 ngăn
int fillNhua = 0, fillGiay = 0, fillHuuCo = 0;
byte thresholdNhua = DEFAULT_FULL_THRESHOLD_PERCENT;
byte thresholdGiay = DEFAULT_FULL_THRESHOLD_PERCENT;
byte thresholdHuuCo = DEFAULT_FULL_THRESHOLD_PERCENT;

// Khai báo các hàm
long readUltrasonicDistance(int trigPin, int echoPin);
long readTriggerUltrasonicDistance();
void printTriggerSensorStatus(long distance, bool forcePrint);
int calculateFillPercentageFromDistance(long distance);
int measureBin(int trigPin, int echoPin, bool *isFull,
               const __FlashStringHelper* name, byte thresholdPercent);
void measureAllBins();
void updateBinStatusLeds();
bool parseConfigLine(const char *line);
void applyEspConfig(const char *line);
void sendFillDataToESP();
void resendFillDataToESP();
void updateTriggerSensor();
void readDebugCommands();
void handleDebugCommand(const char *command);
void startPendingTrigger();
void startOpenBin(Servo &s, const __FlashStringHelper* name);
void finishNanoProcessing();
void closeAll();
void sendReadyProbe();
void sendTrigger();
void clearSerialBuffer();
void setAllLEDs(bool state);
void setAiLedState(AiLedState state);
void updateAiLed();
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
  setAiLedState(AI_LED_LOADING);

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
  setAiLedState(AI_LED_READY);
#else
  Serial.println(F("=== CHE DO CHAY THAT KET NOI ESP32-CAM ==="));
  Serial.println(F("Dang bat tay voi ESP32-CAM..."));
  Serial.println(F("Serial Monitor: S=do sensor, M=monitor, T=ep ESP-CAM, ?=tro giup."));
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
  updateAiLed();
  updateBlink();
  updateBinStatusLeds();

  // Chỉ cập nhật cache khi rảnh. Không gửi F tự do vì F phải thuộc đúng
  // transaction vừa nhận kết quả C từ ESP32.
  if (currentState == STATE_IDLE && !pendingTrigger &&
      (millis() - lastFillCheckTime >= FILL_CHECK_INTERVAL_MS)) {
    measureAllBins();
    lastFillCheckTime = millis();
  }

  char line[24] = "";
  const bool hasLine = readEspLine(line, sizeof(line));
  if (hasLine && parseConfigLine(line)) {
    applyEspConfig(line);
    return;
  }

  switch (currentState) {

    case STATE_WAIT_ESP_READY: {
      if (hasLine && (strcmp_P(line, PSTR("R 1")) == 0 ||
                      (line[0] == 'D' && line[1] == ' ' &&
                       (line[2] == '0' || line[2] == '1') && line[3] == '\0'))) {
        Serial.println(F("[UART] ESP32 da san sang."));
        setAiLedState(AI_LED_READY);
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

      if (maintenanceMode) {
        pendingTrigger = false;
        manualTriggerPending = false;
      }

      if (!maintenanceMode &&
          ((pendingTrigger && triggerSensorOccupied) || manualTriggerPending) &&
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
      else if (millis() - stateStartTime >= TRIGGER_ACK_TIMEOUT_MS) {
        if (uartAttempts < MAX_UART_ATTEMPTS) {
          ++uartAttempts;
          Serial.print(F("[UART] Khong co ACK T, gui lai lan "));
          Serial.println(uartAttempts);
          sendTrigger();
          stateStartTime = millis();
        }
        else {
          Serial.println(F("[!] ESP khong ACK trigger; quay lai bat tay."));
          setAiLedState(AI_LED_ERROR);
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
        setAiLedState(AI_LED_ERROR);
        pendingTrigger = triggerSensorOccupied;
        sendReadyProbe();
        stateStartTime = millis();
        currentState = STATE_WAIT_ESP_READY;
      }
      break;
    }

    case STATE_NANO_PROCESSING: {
      if (hasLine && strcmp_P(line, PSTR("A T")) != 0) {
        Serial.print(F("[UART] Goi den khi Nano dang xu ly: "));
        Serial.println(line);
      }

      if (activeServo != NULL && millis() - servoOpenedAt >= OPEN_DURATION_MS) {
        activeServo->write(ANGLE_CLOSE);
        activeServo = NULL;
        servoClosedAt = millis();
        postCloseMeasurementPending = true;
        Serial.println(F("-> Da dong nap thung rac."));
        Serial.println(F("-> Cho cam bien on dinh 1 giay truoc lan do thu 2..."));
      }

      // Nếu nắp đã mở, chỉ đo lần 2 sau khi đóng và chờ ổn định đủ 1 giây.
      if (activeServo == NULL && activeBlinkPin == -1) {
        if (postCloseMeasurementPending) {
          if (millis() - servoClosedAt < POST_CLOSE_SETTLE_MS) {
            break;
          }
          Serial.println(F("[BIN] Lan 2: do lai sau khi nap da dong 1 giay..."));
          measureAllBins();
          lastFillCheckTime = millis();
          postCloseMeasurementPending = false;
        }
        finishNanoProcessing();
      }
      break;
    }

    case STATE_WAIT_FILL_ACK: {
      if (hasLine && strcmp_P(line, PSTR("A F")) == 0) {
        Serial.println(F("[UART] ESP da nhan muc day; dang gui anh toi server local..."));
        stateStartTime = millis();
        currentState = STATE_WAIT_SERVER;
      }
      else if (hasLine && line[0] == 'D' && line[1] == ' ' &&
               (line[2] == '0' || line[2] == '1') && line[3] == '\0') {
        Serial.println(strcmp_P(line, PSTR("D 1")) == 0
                           ? F("[SERVER] Da luu anh tren may.")
                           : F("[SERVER] Gui anh that bai; ESP da ranh."));
        enterCooldown();
      }
      else if (hasLine && line[0] == 'E' && line[1] == ' ') {
        Serial.print(F("[SERVER] ESP bao loi: "));
        Serial.println(line + 2);
      }
      else if (hasLine) {
        Serial.print(F("[UART] Goi khong mong doi khi cho ACK F: "));
        Serial.println(line);
      }
      else if (millis() - stateStartTime >= FILL_ACK_TIMEOUT_MS) {
        // Repeating F is safe: ESP uploads only after one accepted capture
        // transaction, and a duplicate F never starts another capture/POST.
        if (uartAttempts < MAX_UART_ATTEMPTS) {
          ++uartAttempts;
          Serial.print(F("[UART] Khong co ACK F, gui lai lan "));
          Serial.println(uartAttempts);
          resendFillDataToESP();
          stateStartTime = millis();
        }
        else {
          Serial.println(F("[UART] ESP khong ACK F; quay lai bat tay."));
          setAiLedState(AI_LED_ERROR);
          sendReadyProbe();
          stateStartTime = millis();
          currentState = STATE_WAIT_ESP_READY;
        }
      }
      break;
    }

    case STATE_WAIT_SERVER: {
      if (hasLine && line[0] == 'D' && line[1] == ' ' &&
          (line[2] == '0' || line[2] == '1') && line[3] == '\0') {
        Serial.println(strcmp_P(line, PSTR("D 1")) == 0
                           ? F("[SERVER] Anh va du lieu da luu tren may.")
                           : F("[SERVER] Gui loi; phan loai local van hoan tat."));
        enterCooldown();
      }
      else if (hasLine && line[0] == 'E' && line[1] == ' ') {
        Serial.print(F("[SERVER] ESP bao loi: "));
        Serial.println(line + 2);
      }
      else if (hasLine && strcmp_P(line, PSTR("R 1")) == 0) {
        // R 1 cannot be valid while the accepted T/F transaction is active.
        // The ESP lost its in-RAM transaction state, normally after a reset or
        // brownout, and then completed boot again.
        Serial.println(
            F("[UART] ESP da khoi dong lai khi dang gui server; transaction that bai."));
        setAiLedState(AI_LED_ERROR);
        lastClassificationSucceeded = false;
        enterCooldown();
      }
      else if (hasLine && strcmp_P(line, PSTR("A F")) != 0) {
        Serial.print(F("[UART] Goi khong mong doi khi cho server: "));
        Serial.println(line);
      }
      else if (!hasLine && millis() - stateStartTime >= SERVER_UPLOAD_TIMEOUT_MS) {
        Serial.println(F("[!] Timeout server local; bat tay lai voi ESP."));
        setAiLedState(AI_LED_ERROR);
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
        // Chỉ báo READY sau khi thời gian chờ giữa hai lượt đã kết thúc.
        // Nếu lượt trước bị lỗi, giữ nhịp ERROR cho đến khi có trigger mới.
        if (lastClassificationSucceeded) {
          setAiLedState(AI_LED_READY);
        }
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

// ==== TRANG THAI LED AI: LOADING / READY / ERROR ====
void setAiLedState(AiLedState state) {
  aiLedState = state;
  if (state == AI_LED_READY) {
    digitalWrite(LED_AI, HIGH);
  } else if (state == AI_LED_ERROR) {
    digitalWrite(LED_AI, HIGH);
  } else {
    digitalWrite(LED_AI, LOW);
  }
}

void updateAiLed() {
  if (aiLedState == AI_LED_READY) {
    digitalWrite(LED_AI, HIGH);
    return;
  }

  const unsigned long interval = aiLedState == AI_LED_LOADING
                                     ? AI_LOADING_TOGGLE_MS
                                     : AI_ERROR_TOGGLE_MS;
  blinkSingleLED(LED_AI, interval);
}

// ==== NHẤP NHÁY 1 LED CHỈ ĐỊNH KHÔNG TREO MẠCH ====
void blinkSingleLED(int pin, int interval) {
  unsigned long currentMillis = millis();
  bool state = ((currentMillis / interval) % 2 == 0);
  digitalWrite(pin, state ? HIGH : LOW);
}

void startBlink(int pin) {
  if (activeBlinkPin != -1 && activeBlinkPin != pin) {
    // Khôi phục trạng thái đầy/rỗng của LED cũ trước khi chuyển sang LED mới.
    activeBlinkPin = -1;
    updateBinStatusLeds();
  }
  activeBlinkPin = pin;
  blinkStartTime = millis();
  digitalWrite(activeBlinkPin, HIGH);
}

void updateBlink() {
  if (activeBlinkPin == -1) return;

  if (millis() - blinkStartTime >= CLASSIFICATION_BLINK_MS) {
    const int finishedBlinkPin = activeBlinkPin;
    activeBlinkPin = -1;
    digitalWrite(finishedBlinkPin, LOW);
    // Trả LED về trạng thái đã đo trước đó: đầy = sáng liên tục, rỗng = tắt.
    updateBinStatusLeds();
    return;
  }
  const bool blinkOn = (((millis() - blinkStartTime) /
                         CLASSIFICATION_LED_TOGGLE_MS) % 2UL) == 0UL;
  digitalWrite(activeBlinkPin, blinkOn ? HIGH : LOW);
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
  static char commandBuffer[8] = "";
  static byte commandLength = 0;

  while (Serial.available() > 0) {
    const int received = Serial.read();
    if (received == '\r') continue;
    if (received == '\n') {
      if (commandLength > 0) {
        commandBuffer[commandLength] = '\0';
        handleDebugCommand(commandBuffer);
      }
      commandLength = 0;
      commandBuffer[0] = '\0';
      continue;
    }

    if (received < 32 || received > 126) continue;
    if ((size_t)commandLength + 1U >= sizeof(commandBuffer)) {
      commandLength = 0;
      commandBuffer[0] = '\0';
      Serial.println(F("[TEST] Lenh Monitor qua dai; da huy."));
      continue;
    }

    commandBuffer[commandLength++] = (char)received;
    commandBuffer[commandLength] = '\0';
  }
#endif
}

void handleDebugCommand(const char *command) {
#if !defined(TEST_MODE)
  if (command == NULL) return;

  if (strcmp(command, "T") == 0 || strcmp(command, "t") == 0) {
    if (currentState == STATE_IDLE) {
      manualTriggerPending = true;
      Serial.println(F("[TEST] Da xep trigger thu cong cho ESP-CAM."));
    } else {
      Serial.println(F("[TEST] Bo qua T: transaction dang xu ly."));
    }
    return;
  }

  if (strcmp(command, "S") == 0 || strcmp(command, "s") == 0) {
    const long distance = readTriggerUltrasonicDistance();
    printTriggerSensorStatus(distance, true);
    return;
  }

  if (strcmp(command, "M") == 0 || strcmp(command, "m") == 0) {
    triggerVerboseMonitor = !triggerVerboseMonitor;
    Serial.println(triggerVerboseMonitor
                       ? F("[TEST] Monitor sensor nhanh: ON (250ms).")
                       : F("[TEST] Monitor sensor nhanh: OFF (1000ms)."));
    return;
  }

  if (strcmp(command, "?") == 0) {
    Serial.println(F("[TEST] S=do ngay, M=monitor nhanh, T=ep ESP-CAM."));
    return;
  }

  Serial.print(F("[TEST] Lenh khong hop le: "));
  Serial.println(command);
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

// ==== TÍNH PHẦN TRĂM ĐỘ ĐẦY TỪ MỘT KẾT QUẢ ĐO ====
int calculateFillPercentageFromDistance(long distance) {
  if (distance >= BIN_HEIGHT_CM) return 0; // Trống hoàn toàn
  
  float fillPercent = ((BIN_HEIGHT_CM - (float)distance) / BIN_HEIGHT_CM) * 100.0;
  
  if (fillPercent < 0) fillPercent = 0;
  if (fillPercent > 100) fillPercent = 100;

  return (int)fillPercent;
}

// ==== ĐO MỘT NGĂN VÀ SUY RA TRẠNG THÁI ĐẦY ====
int measureBin(int trigPin, int echoPin, bool *isFull,
               const __FlashStringHelper* name, byte thresholdPercent) {
  const long distance = readUltrasonicDistance(trigPin, echoPin);
  if (distance <= 0) {
    *isFull = true;
    Serial.print(F("[BIN] "));
    Serial.print(name);
    Serial.println(F(": TIMEOUT -> FULL, LED=ON"));
    return 100;
  }

  const int fillPercent = calculateFillPercentageFromDistance(distance);
  *isFull = fillPercent >= thresholdPercent;
  Serial.print(F("[BIN] "));
  Serial.print(name);
  Serial.print(F(": distance="));
  Serial.print(distance);
  Serial.print(F("cm fill="));
  Serial.print(fillPercent);
  Serial.print(F("% threshold="));
  Serial.print(thresholdPercent);
  Serial.print(F("% state="));
  Serial.println(*isFull ? F("FULL LED=ON") : F("AVAILABLE LED=LOW"));
  return fillPercent;
}

// ==== ĐO ĐỘ ĐẦY CẢ 3 NGĂN ====
void measureAllBins() {
  fillNhua = measureBin(TRIG_NHUA, ECHO_NHUA, &binFullNhua, F("NHUA"),
                        thresholdNhua);
  fillGiay = measureBin(TRIG_GIAY, ECHO_GIAY, &binFullGiay, F("GIAY"),
                        thresholdGiay);
  fillHuuCo = measureBin(TRIG_HUUCO, ECHO_HUUCO, &binFullHuuCo, F("HUU CO"),
                         thresholdHuuCo);
  updateBinStatusLeds();
}

// Trạng thái nền của LED ngăn: đầy/timeout = sáng liên tục, còn nhận rác = tắt.
// Khi đang báo kết quả phân loại, updateBlink() tạm thời toàn quyền điều khiển LED đó.
void updateBinStatusLeds() {
  if (activeBlinkPin != LED_NHUA) {
    digitalWrite(LED_NHUA, binFullNhua ? HIGH : LOW);
  }
  if (activeBlinkPin != LED_GIAY) {
    digitalWrite(LED_GIAY, binFullGiay ? HIGH : LOW);
  }
  if (activeBlinkPin != LED_HUUCO) {
    digitalWrite(LED_HUUCO, binFullHuuCo ? HIGH : LOW);
  }
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

bool parseConfigLine(const char *line) {
  if (line == NULL) return false;
  return line[0] == 'G' && line[1] == ' ';
}

void applyEspConfig(const char *line) {
  unsigned plastic = 0;
  unsigned paper = 0;
  unsigned organic = 0;
  unsigned maintenance = 0;
  char extra = '\0';
  if (sscanf(line, "G %u %u %u %u %c", &plastic, &paper, &organic,
             &maintenance, &extra) != 4 ||
      plastic > 100 || paper > 100 || organic > 100 || maintenance > 1) {
    Serial.print(F("[CONFIG] Goi config khong hop le: "));
    Serial.println(line);
    return;
  }

  thresholdNhua = (byte)plastic;
  thresholdGiay = (byte)paper;
  thresholdHuuCo = (byte)organic;
  maintenanceMode = maintenance == 1;
  Serial.print(F("[CONFIG] Dashboard -> threshold NHUA/GIAY/HUUCO="));
  Serial.print(thresholdNhua);
  Serial.print('/');
  Serial.print(thresholdGiay);
  Serial.print('/');
  Serial.print(thresholdHuuCo);
  Serial.print(F("% maintenance="));
  Serial.println(maintenanceMode ? F("ON") : F("OFF"));
  measureAllBins();
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
  // LOADING bat/tat moi 1 giay trong luc ESP chup, inference va gui server local.
  setAiLedState(AI_LED_LOADING);

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
  lastClassificationSucceeded = code >= 1 && code <= 3;

  // Lần đo thứ nhất: ESP đã trả kết quả nhưng chưa quyết định mở nắp.
  Serial.println(F("[BIN] Lan 1: do 3 ngan truoc khi mo nap..."));
  measureAllBins();
  lastFillCheckTime = millis();
  postCloseMeasurementPending = false;

  if (code == 0) {
    Serial.println(F("[!] AI khong nhan dien; khong mo ngan."));
    setAiLedState(AI_LED_ERROR);
  }
  else {
    // Van giu LOADING cho den khi ESP ket thuc mot lan gui server local.
    setAiLedState(AI_LED_LOADING);
    handleLabel(code);
  }

  // STATE_NANO_PROCESSING đợi servo đóng hoặc cảnh báo kết thúc. F tuyệt đối
  // không được gửi trước thời điểm đó.
  stateStartTime = millis();
  currentState = STATE_NANO_PROCESSING;
}

// ==== XỬ LÝ KIỂM TRA ĐẦY & MỞ NẮP CHO TỪNG LOẠI RÁC ====
void handleLabel(int code) {
  if (maintenanceMode) {
    Serial.println(F("[CONFIG] Maintenance ON -> khong mo nap."));
    return;
  }

  if (code == 1) {
    // Dùng snapshot đã đo ngay lúc trigger AI.
    Serial.print(F("-> Ngan Nhua: ")); Serial.print(fillNhua); Serial.println(F("%"));
    startBlink(LED_NHUA);

    if (binFullNhua) {
      Serial.println(F("[!] Ngan NHUA day/timeout -> khong mo nap; LED van nhap nhay bao phan loai."));
    } else {
      startOpenBin(servoNhua, F("NGAN NHUA"));
    }
  } 
  else if (code == 2) {
    Serial.print(F("-> Ngan Giay: ")); Serial.print(fillGiay); Serial.println(F("%"));
    startBlink(LED_GIAY);

    if (binFullGiay) {
      Serial.println(F("[!] Ngan GIAY day/timeout -> khong mo nap; LED van nhap nhay bao phan loai."));
    } else {
      startOpenBin(servoGiay, F("NGAN GIAY"));
    }
  } 
  else if (code == 3) {
    Serial.print(F("-> Ngan Huu co: ")); Serial.print(fillHuuCo); Serial.println(F("%"));
    startBlink(LED_HUUCO);

    if (binFullHuuCo) {
      Serial.println(F("[!] Ngan HUU CO day/timeout -> khong mo nap; LED van nhap nhay bao phan loai."));
    } else {
      startOpenBin(servoHuuCo, F("NGAN HUU CO"));
    }
  }
}

// ==== BẮT ĐẦU MỞ SERVO KHÔNG BLOCKING ====
void startOpenBin(Servo &s, const __FlashStringHelper* name) {
  Serial.print(F("-> Dang mo: "));
  Serial.println(name);

  activeServo = &s;
  postCloseMeasurementPending = false;
  servoOpenedAt = millis();
  s.write(ANGLE_OPEN);
}

void finishNanoProcessing() {
  // Nếu nắp đã mở, measureAllBins() vừa chạy sau khi đóng và chờ 1 giây.
  // Nếu không mở nắp, dùng lần đo ngay sau kết quả AI.
  Serial.println(F("-> Nano xu ly xong; gui dung tich 3 ngan..."));
  uartAttempts = 1;
  sendFillDataToESP();
  stateStartTime = millis();
  currentState = STATE_WAIT_FILL_ACK;
}

void enterCooldown() {
  // Trong cooldown hệ thống chưa nhận lượt mới: nhấp nháy chậm như LOADING.
  // Lượt phân loại lỗi tiếp tục dùng nhịp ERROR nhanh.
  setAiLedState(lastClassificationSucceeded ? AI_LED_LOADING : AI_LED_ERROR);
  stateStartTime = millis();
  currentState = STATE_COOLDOWN;
}

// ==== ĐÓNG TOÀN BỘ NẮP ====
void closeAll() {
  servoHuuCo.write(ANGLE_CLOSE);
  servoGiay.write(ANGLE_CLOSE);
  servoNhua.write(ANGLE_CLOSE);
}
