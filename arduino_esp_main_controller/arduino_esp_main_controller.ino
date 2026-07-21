/*
 * ARDUINO - MAIN CONTROLLER cho AIoT Smart Trash Bin (TÍCH HỢP ESP32-CAM & LED CHỚP LỖI TOÀN DIỆN)
 * * * Sơ đồ cắm dây thực tế:
 * - Cảm biến siêu âm HC-SR04: Trig -> Pin 9, Echo -> Pin 8, VCC -> 5V, GND -> GND
 * - Servo 1 (HỮU CƠ):        Tín hiệu -> Pin 10
 * - Servo 2 (GIẤY):          Tín hiệu -> Pin 11
 * - Servo 3 (NHỰA):          Tín hiệu -> Pin 7
 * - LED báo hiệu:            Chân (+) -> Pin 6 (qua trở 220 ohm), Chân (-) -> GND
 * * * Kết nối truyền thông chân chéo với ESP32-CAM:
 * - Arduino Pin 3 (TX giả lập) -> ESP32-CAM U0R (RX) [Gửi lệnh kích hoạt "1"]
 * - Arduino Pin 2 (RX giả lập) -> ESP32-CAM U0T (TX) [Nhận kết quả 0, 1, 2, 3]
 * - Nguồn: Chân 5V & GND của ESP32-CAM nối chung vào hàng Busline nguồn của Mtiny.
 */

//#define TEST_MODE   // <-- THÊM dấu // ở đầu dòng này khi bạn kết nối nối với ESP32-CAM thật

#include <Servo.h>
#if !defined(TEST_MODE)
#include <SoftwareSerial.h>
#endif

// ==== Cấu hình Cảm biến siêu âm ====
const int TRIG_PIN = 9;   
const int ECHO_PIN = 8;   
const int THRESHOLD_CM = 10; 

// ==== Cấu hình LED báo hiệu ====
const int LED_PIN = 6; 

// ==== Cấu hình Chân Servo ====
Servo servoHuuCo, servoGiay, servoNhua;
const int PIN_SERVO_HUUCO = 10; 
const int PIN_SERVO_GIAY  = 11; 
const int PIN_SERVO_NHUA  = 7;  

const int ANGLE_CLOSE = 0;
const int ANGLE_OPEN  = 90;
const unsigned long OPEN_DURATION_MS = 2500; 

// ==== Cấu hình Thời gian kiểm soát luồng ====
const unsigned long LABEL_TIMEOUT_MS = 8000; 
const unsigned long COOLDOWN_MS = 3000;      
const unsigned long ERROR_BLINK_MS = 3000;   // Đèn nhấp nháy lỗi trong 3 giây

#if !defined(TEST_MODE)
const int PIN_RX = 2;
const int PIN_TX = 3;
SoftwareSerial espSerial(PIN_RX, PIN_TX);
#endif

enum State { STATE_IDLE, STATE_WAIT_LABEL, STATE_ERROR_BLINK, STATE_COOLDOWN };
State currentState = STATE_IDLE;
unsigned long stateStartTime = 0;

void setup() {
  Serial.begin(115200); 
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW); 

#if !defined(TEST_MODE)
  espSerial.begin(9600);
#endif

  servoHuuCo.attach(PIN_SERVO_HUUCO);
  servoGiay.attach(PIN_SERVO_GIAY);
  servoNhua.attach(PIN_SERVO_NHUA);
  closeAll();

#if defined(TEST_MODE)
  Serial.println("=== TEST MODE: cam bien that, label gia lap qua Serial Monitor ===");
  Serial.println("Quy uoc test: 1->NHUA, 2->GIAY, 3->HUUCO. Nhap so khac (vd: 0) -> CHỚP ĐÈN LỖI");
#else
  Serial.println("--- KHOI DONG CHE DO CHAY THAT VỚI ESP32-CAM ---");
#endif
}

void loop() {
  switch (currentState) {

    case STATE_IDLE: {
      long d = measureDistanceCM();
      
      if (d > 0) {
        Serial.print("Khoang cach hien tai: "); Serial.print(d); Serial.println(" cm");
      }

      if (d > 0 && d < THRESHOLD_CM) {
        Serial.println("\n[!] -> KICH HOAT THANH CONG!");
        
        // Xóa sạch dữ liệu thừa bám trong bộ đệm Serial trước khi đợi lệnh mới
        clearSerialBuffer(); 
        
        sendTrigger(); // Gửi tín hiệu số "1" sang ESP32-CAM và BẬT LED sáng đứng
        stateStartTime = millis();
        currentState = STATE_WAIT_LABEL;
      }
      delay(250); 
      break;
    }

    case STATE_WAIT_LABEL: {
      String label = checkForLabel();
      
      if (label.length() > 0) {
        // Kiểm tra tính hợp lệ của nhãn nhận diện
        if (label == "1" || label == "2" || label == "3") {
          digitalWrite(LED_PIN, LOW); // Tắt LED ngay vì nhận diện thành công
          handleLabel(label);         // Kích hoạt mở Servo tương ứng
          stateStartTime = millis();
          currentState = STATE_COOLDOWN;
        } 
        // TRƯỜNG HỢP: Nhận kết quả khác 3 số trên (Ví dụ: "0" hoặc ký tự rác do lỗi nhiễu)
        else {
          Serial.print("[!] He thong bao LOI NHAN DIEN. Nhan chuoi la: ");
          Serial.println(label);
          stateStartTime = millis();
          currentState = STATE_ERROR_BLINK; // Chuyển sang chế độ nhấp nháy đèn lỗi
        }
      } 
      // TRƯỜNG HỢP: Quá 8 giây phản hồi mà ESP32-CAM không gửi gì về
      else if (millis() - stateStartTime > LABEL_TIMEOUT_MS) {
        Serial.println("[!] Timeout: Quang thoi gian cho ket thuc. LOI KET NOI!");
        stateStartTime = millis();
        currentState = STATE_ERROR_BLINK; // Chuyển sang chế độ nhấp nháy đèn lỗi
      }
      break;
    }

    case STATE_ERROR_BLINK: {
      blinkLED(200); // Đèn nhấp nháy liên tục chu kỳ 200ms bằng kỹ thuật non-blocking

      if (millis() - stateStartTime > ERROR_BLINK_MS) {
        digitalWrite(LED_PIN, LOW); // Đảm bảo tắt hẳn LED sau khi kết thúc chớp lỗi
        stateStartTime = millis();
        currentState = STATE_COOLDOWN; 
      }
      break;
    }

    case STATE_COOLDOWN: {
      if (millis() - stateStartTime > COOLDOWN_MS) {
        currentState = STATE_IDLE;
        Serial.println("--- System Ready: San sang cho lan tiep theo ---\n");
      }
      break;
    }
  }
}

// Hàm đo khoảng cách bằng sóng âm của HC-SR04
long measureDistanceCM() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  
  long duration = pulseIn(ECHO_PIN, HIGH, 30000); 
  if (duration == 0) return -1; 
  return duration / 58; 
}

// Phát tín hiệu kích hoạt chụp ảnh
void sendTrigger() {
  digitalWrite(LED_PIN, HIGH); // BẬT ĐÈN LED sáng đứng chờ phản hồi
#if defined(TEST_MODE)
  Serial.println("[GIA LAP] Da gui tin hieu '1' sang ESP32-CAM.");
  Serial.println("Nhap LABEL SO va Nhan Enter (1: NHUA / 2: GIAY / 3: HUUCO / 0: LOI):");
#else
  Serial.println("Gui tin hieu '1' sang ESP32-CAM qua chan D3...");
  espSerial.println("1"); // Gửi số 1 duy nhất kèm ký tự kết thúc dòng
#endif
}

// Xóa bộ đệm Serial
void clearSerialBuffer() {
#if defined(TEST_MODE)
  while (Serial.available() > 0) {
    Serial.read(); 
  }
#else
  while (espSerial.available() > 0) {
    espSerial.read(); 
  }
#endif
}

// Hàm xử lý nhấp nháy LED không gây treo mạch
void blinkLED(int interval) {
  unsigned long currentMillis = millis();
  if ((currentMillis / interval) % 2 == 0) {
    digitalWrite(LED_PIN, HIGH);
  } else {
    digitalWrite(LED_PIN, LOW);
  }
}

// Kiểm tra tín hiệu Serial
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

// Xử lý mở Servo chính xác theo nhãn số
void handleLabel(String label) {
  Serial.print("-> Nhan diện hop le: ");
  if (label == "1") {
    openBin(servoNhua, "NHUA (Pin D7)");
  } else if (label == "2") {
    openBin(servoGiay, "GIAY (Pin D11)");
  } else if (label == "3") {
    openBin(servoHuuCo, "HUUCO (Pin D10)");
  }
}

// Hàm mở góc Servo
void openBin(Servo &s, const char* name) {
  Serial.print("-> Dang mo ngan thung rac: ");
  Serial.println(name);
  s.write(ANGLE_OPEN);
  delay(OPEN_DURATION_MS);
  s.write(ANGLE_CLOSE);
}

// Đóng toàn bộ nắp thùng rac
void closeAll() {
  servoHuuCo.write(ANGLE_CLOSE);
  servoGiay.write(ANGLE_CLOSE);
  servoNhua.write(ANGLE_CLOSE);
}