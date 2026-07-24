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
 * - Arduino Pin 3 (TX) -> ESP32-CAM RX (Gửi "T 1", "F nhua giay huu_co")
 * - Arduino Pin 2 (RX) -> ESP32-CAM TX (Nhận "C 0", "C 1", "C 2", "C 3", "C 4")
 */

#define TEST_MODE   // <-- THÊM/BỎ dấu // ở đầu dòng này để chuyển giữa Chế độ Test và Chế độ chạy thật với ESP32-CAM

#include <Servo.h>
#if !defined(TEST_MODE)
#include <SoftwareSerial.h>
#endif

// ==== Cấu hình Cảm biến siêu âm Cầm tay (Kích hoạt AI) ====
const int TRIG_PIN = 9;   
const int ECHO_PIN = 8;   
const int THRESHOLD_CM = 10; 

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
const unsigned long LABEL_TIMEOUT_MS = 15000; // Thời gian chờ phản hồi từ ESP32 (15s)
const unsigned long COOLDOWN_MS = 2000;       // Thời gian nghỉ giữa các lần hoạt động
const unsigned long ERROR_BLINK_MS = 3000;    // Đèn nhấp nháy chớp lỗi/đầy trong 3 giây
const unsigned long FILL_CHECK_INTERVAL_MS = 10000; // Định kỳ đo độ đầy mỗi 10s

#if !defined(TEST_MODE)
const int PIN_RX = 2;
const int PIN_TX = 3;
SoftwareSerial espSerial(PIN_RX, PIN_TX);
#endif

enum State { STATE_IDLE, STATE_WAIT_LABEL, STATE_BLINK_LED, STATE_COOLDOWN };
State currentState = STATE_IDLE;
unsigned long stateStartTime = 0;
unsigned long lastFillCheckTime = 0; 

int activeBlinkPin = -1; // Lưu chân LED cần nhấp nháy khi có lỗi hoặc báo đầy

// Biến lưu độ đầy của 3 ngăn
int fillNhua = 0, fillGiay = 0, fillHuuCo = 0;

// Khai báo các hàm
long readUltrasonicDistance(int trigPin, int echoPin);
int calculateFillPercentage(int trigPin, int echoPin);
void measureAllBins();
void sendFillDataToESP();
void openBin(Servo &s, int binLedPin, const char* name);
void closeAll();
void sendTrigger();
void clearSerialBuffer();
void setAllLEDs(bool state);
void blinkSingleLED(int pin, int interval);
String checkForLabel();
void handleLabel(String labelCode);

void setup() {
  Serial.begin(115200); 

  // Cấu hình chân cảm biến kích hoạt
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

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

  servoHuuCo.attach(PIN_SERVO_HUUCO);
  servoGiay.attach(PIN_SERVO_GIAY);
  servoNhua.attach(PIN_SERVO_NHUA);
  closeAll();

#if defined(TEST_MODE)
  Serial.println("=== CHE DO TEST MODE (SERIAL MONITOR) ===");
  Serial.println("Quy uoc nhap: 'C 1' (NHUA), 'C 2' (GIAY), 'C 3' (HUUCO), 'C 0' (LOI/KHONG PHAN LOAI)");
#else
  Serial.println("=== CHE DO CHAY THAT KET NOI ESP32-CAM ===");
#endif

  // Đo độ đầy ban đầu khi khởi động
  measureAllBins();
}

void loop() {
  // Đọc & cập nhật định kỳ độ đầy nếu đang ở trạng thái rảnh
  if (currentState == STATE_IDLE && (millis() - lastFillCheckTime >= FILL_CHECK_INTERVAL_MS)) {
    measureAllBins();
    sendFillDataToESP();
    lastFillCheckTime = millis();
  }

  switch (currentState) {

    case STATE_IDLE: {
      long d = readUltrasonicDistance(TRIG_PIN, ECHO_PIN);
      
      if (d > 0 && d < THRESHOLD_CM) {
        Serial.println("\n[!] -> PHÁT HIỆN VẬT THỂ! BẬT ĐÈN HỘC AI CHỜ CHỤP...");
        
        clearSerialBuffer(); 
        sendTrigger(); // Sáng đèn Hộc AI và gửi "T 1" sang ESP32
        stateStartTime = millis();
        currentState = STATE_WAIT_LABEL;
      }
      delay(100); 
      break;
    }

    case STATE_WAIT_LABEL: {
      String rawLabel = checkForLabel();
      
      if (rawLabel.length() > 0) {
        Serial.print("[UART] Nhan tin hieu tu ESP32: ");
        Serial.println(rawLabel);

        // Chuẩn hóa chuỗi nhận được (Loại bỏ 'C' hoặc khoảng trắng nếu có)
        String code = rawLabel;
        code.replace("C", "");
        code.trim();

        digitalWrite(LED_AI, LOW); // Tắt đèn AI

        // LUỒNG 1: Nhận C 0 (AI không nhận diện được / không phải rác) -> Chớp đèn AI
        if (code == "0") {
          Serial.println("[!] AI KHÔNG NHẬN DIỆN ĐƯỢC RÁC (C 0) -> NHẤP NHÁY ĐÈN AI");
          activeBlinkPin = LED_AI;
          stateStartTime = millis();
          currentState = STATE_BLINK_LED;
        } 
        // LUỒNG 2: Nhận C 1, C 2, C 3, C 4 (Phân loại rác) -> Kiểm tra đầy trước khi mở Servo
        else if (code == "1" || code == "2" || code == "3" || code == "4") {
          
          handleLabel(code); 

          // Sau khi hoàn thành thao tác (mở/đóng hoặc báo đầy), đo lại và gửi độ đầy F sang ESP32
          Serial.println("-> Cập nhật dung tích các ngăn...");
          measureAllBins();
          sendFillDataToESP();

          stateStartTime = millis();
          currentState = STATE_COOLDOWN;
        }
        else {
          Serial.println("[!] Ky tu khong hop le -> Nhấp nháy đèn AI báo lỗi.");
          activeBlinkPin = LED_AI;
          stateStartTime = millis();
          currentState = STATE_BLINK_LED;
        }
      } 
      // Xử lý khi quá thời gian chờ (Timeout)
      else if (millis() - stateStartTime > LABEL_TIMEOUT_MS) {
        Serial.println("[!] QUÁ THỜI GIAN CHỜ ESP32 PHẢN HỒI -> BÁO LỖI KẾT NỐI (Chớp đèn AI)!");
        digitalWrite(LED_AI, LOW);
        activeBlinkPin = LED_AI;
        stateStartTime = millis();
        currentState = STATE_BLINK_LED; 
      }
      break;
    }

    case STATE_BLINK_LED: {
      if (activeBlinkPin != -1) {
        blinkSingleLED(activeBlinkPin, 200); // Nhấp nháy LED chỉ định chu kỳ 200ms
      }

      if (millis() - stateStartTime > ERROR_BLINK_MS) {
        if (activeBlinkPin != -1) {
          digitalWrite(activeBlinkPin, LOW); // Tắt LED sau khi chớp xong
          activeBlinkPin = -1;
        }
        stateStartTime = millis();
        currentState = STATE_COOLDOWN; 
      }
      break;
    }

    case STATE_COOLDOWN: {
      if (millis() - stateStartTime > COOLDOWN_MS) {
        currentState = STATE_IDLE;
        Serial.println("--- System Ready: Sẵn sàng cho lượt tiếp theo ---\n");
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

// ==== HÀM ĐO KHOẢNG CÁCH SIÊU ÂM ====
long readUltrasonicDistance(int trigPin, int echoPin) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  
  long duration = pulseIn(echoPin, HIGH, 30000); 
  if (duration == 0) return -1; 
  return duration / 58; // Quy đổi ra cm
}

// ==== HÀM TÍNH PHẦN TRĂM ĐỘ ĐẦY THÙNG RÁC (%) ====
int calculateFillPercentage(int trigPin, int echoPin) {
  long distance = readUltrasonicDistance(trigPin, echoPin);
  
  if (distance <= 0) return 0; // Nếu cảm biến lỗi, mặc định trả về 0%
  if (distance >= BIN_HEIGHT_CM) return 0; // Trống hoàn toàn
  
  float fillPercent = ((BIN_HEIGHT_CM - (float)distance) / BIN_HEIGHT_CM) * 100.0;
  
  if (fillPercent < 0) fillPercent = 0;
  if (fillPercent > 100) fillPercent = 100;

  return (int)fillPercent;
}

// ==== ĐO ĐỘ ĐẦY CẢ 3 NGĂN ====
void measureAllBins() {
  fillNhua  = calculateFillPercentage(TRIG_NHUA, ECHO_NHUA);
  fillGiay  = calculateFillPercentage(TRIG_GIAY, ECHO_GIAY);
  fillHuuCo = calculateFillPercentage(TRIG_HUUCO, ECHO_HUUCO);
}

// ==== GỬI CHUỖI F DUNG TÍCH SANG ESP32-CAM ====
void sendFillDataToESP() {
  // Định dạng chuỗi: "F <nhua> <giay> <huu_co>"
  String fillMessage = "F " + String(fillNhua) + " " + String(fillGiay) + " " + String(fillHuuCo);
  
  Serial.print("[UART] Gui dung tich len ESP32: ");
  Serial.println(fillMessage);

#if !defined(TEST_MODE)
  espSerial.println(fillMessage); // Gửi chuỗi F sang ESP32-CAM qua SoftwareSerial
#endif
}

// ==== PHÁT TÍN HIỆU KÍCH HOẠT CHỤP CẢNH (T 1) ====
void sendTrigger() {
  digitalWrite(LED_AI, HIGH); // Bật sáng LED Hộc AI trợ sáng chụp ảnh

#if defined(TEST_MODE)
  Serial.println("[UART] Da gui lenh: 'T 1' sang ESP32-CAM.");
  Serial.println("-> Nhap ket qua test (C 1 / C 2 / C 3 / C 0) va nhan Enter:");
#else
  Serial.println("[UART] Gui 'T 1' sang ESP32-CAM...");
  espSerial.println("T 1"); // Gửi chuẩn giao thức "T 1"
#endif
}

// ==== XÓA BỘ ĐỆM SERIAL ====
void clearSerialBuffer() {
#if defined(TEST_MODE)
  while (Serial.available() > 0) Serial.read(); 
#else
  while (espSerial.available() > 0) espSerial.read(); 
#endif
}

// ==== ĐỌC CHUỖI PHẢN HỒI TỪ SERIAL ====
String checkForLabel() {
#if defined(TEST_MODE)
  if (Serial.available()) {
    String label = Serial.readStringUntil('\n');
    label.trim(); 
    return label;
  }
#else
  if (espSerial.available()) {
    String label = espSerial.readStringUntil('\n');
    label.trim(); 
    return label;
  }
#endif
  return "";
}

// ==== XỬ LÝ KIỂM TRA ĐẦY & MỞ NẮP CHO TỪNG LOẠI RÁC ====
void handleLabel(String code) {
  if (code == "1") {
    // Ngăn Nhựa
    int currentFill = calculateFillPercentage(TRIG_NHUA, ECHO_NHUA);
    Serial.print("-> Ngăn Nhựa đầy: "); Serial.print(currentFill); Serial.println("%");
    
    if (currentFill >= FULL_THRESHOLD_PERCENT) {
      Serial.println("[!] NGĂN NHỰA ĐÃ ĐẦY -> NHẤP NHÁY ĐÈN NGĂN NHỰA BÁO HIỆU!");
      activeBlinkPin = LED_NHUA;
      currentState = STATE_BLINK_LED;
    } else {
      openBin(servoNhua, LED_NHUA, "NGĂN NHỰA (Servo D7 + LED D12)");
    }
  } 
  else if (code == "2") {
    // Ngăn Giấy
    int currentFill = calculateFillPercentage(TRIG_GIAY, ECHO_GIAY);
    Serial.print("-> Ngăn Giấy đầy: "); Serial.print(currentFill); Serial.println("%");

    if (currentFill >= FULL_THRESHOLD_PERCENT) {
      Serial.println("[!] NGĂN GIẤY ĐÃ ĐẦY -> NHẤP NHÁY ĐÈN NGĂN GIẤY BÁO HIỆU!");
      activeBlinkPin = LED_GIAY;
      currentState = STATE_BLINK_LED;
    } else {
      openBin(servoGiay, LED_GIAY, "NGĂN GIẤY (Servo D11 + LED D6)");
    }
  } 
  else if (code == "3" || code == "4") {
    // Ngăn Hữu cơ
    int currentFill = calculateFillPercentage(TRIG_HUUCO, ECHO_HUUCO);
    Serial.print("-> Ngăn Hữu cơ đầy: "); Serial.print(currentFill); Serial.println("%");

    if (currentFill >= FULL_THRESHOLD_PERCENT) {
      Serial.println("[!] NGĂN HỮU CƠ ĐÃ ĐẦY -> NHẤP NHÁY ĐÈN NGĂN HỮU CƠ BÁO HIỆU!");
      activeBlinkPin = LED_HUUCO;
      currentState = STATE_BLINK_LED;
    } else {
      openBin(servoHuuCo, LED_HUUCO, "NGĂN HỮU CƠ (Servo D10 + LED D5)");
    }
  }
}

// ==== HÀM MỞ SERVO & SÁNG ĐÈN NGĂN TRONG 5 GIÂY ====
void openBin(Servo &s, int binLedPin, const char* name) {
  Serial.print("-> Dang mo: ");
  Serial.println(name);
  
  digitalWrite(binLedPin, HIGH); // Sáng đèn ngăn tương ứng
  s.write(ANGLE_OPEN);           // Mở góc 90 độ
  delay(OPEN_DURATION_MS);       // Giữ nắp mở đúng 5 giây
  
  s.write(ANGLE_CLOSE);          // Đóng nắp
  digitalWrite(binLedPin, LOW);   // Tắt đèn ngăn sau khi đóng nắp hoàn toàn
  Serial.println("-> Da dong nap thung rac.");
}

// ==== ĐÓNG TOÀN BỘ NẮP ====
void closeAll() {
  servoHuuCo.write(ANGLE_CLOSE);
  servoGiay.write(ANGLE_CLOSE);
  servoNhua.write(ANGLE_CLOSE);
}
