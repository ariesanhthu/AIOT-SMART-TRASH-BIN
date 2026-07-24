/*
 * Test độc lập 4 cảm biến siêu âm cho Arduino Nano.
 *
 * Cảm biến kích hoạt AI: TRIG D9, ECHO D8
 * Ngăn nhựa:            TRIG A1, ECHO A0
 * Ngăn giấy:            TRIG A3, ECHO A2
 * Ngăn hữu cơ:          TRIG A5, ECHO A4
 *
 * Serial Monitor: 115200 baud.
 * Mỗi dòng kết quả được in khoảng 1 lần/giây.
 */

const byte TRIG_AI = 9;
const byte ECHO_AI = 8;

const byte TRIG_NHUA = A1;
const byte ECHO_NHUA = A0;

const byte TRIG_GIAY = A3;
const byte ECHO_GIAY = A2;

const byte TRIG_HUUCO = A5;
const byte ECHO_HUUCO = A4;

const unsigned long ECHO_TIMEOUT_US = 30000UL;
const unsigned long PRINT_INTERVAL_MS = 1000UL;
const unsigned long SENSOR_GAP_MS = 60UL;

unsigned long lastPrintTime = 0;

long measureDistanceCm(byte trigPin, byte echoPin) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(5);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(12);
  digitalWrite(trigPin, LOW);

  const unsigned long pulseUs = pulseIn(echoPin, HIGH, ECHO_TIMEOUT_US);
  if (pulseUs == 0) return -1;

  // HC-SR04: khoảng cách cm xấp xỉ pulseUs / 58.
  return (pulseUs + 29UL) / 58UL;
}

void printDistance(const __FlashStringHelper *name, long distanceCm) {
  Serial.print(name);
  Serial.print(F("="));
  if (distanceCm < 0) {
    Serial.print(F("TIMEOUT"));
  } else {
    Serial.print(distanceCm);
    Serial.print(F(" cm"));
  }
}

void setupSensor(byte trigPin, byte echoPin) {
  pinMode(trigPin, OUTPUT);
  digitalWrite(trigPin, LOW);
  pinMode(echoPin, INPUT);
}

void setup() {
  Serial.begin(115200);

  setupSensor(TRIG_AI, ECHO_AI);
  setupSensor(TRIG_NHUA, ECHO_NHUA);
  setupSensor(TRIG_GIAY, ECHO_GIAY);
  setupSensor(TRIG_HUUCO, ECHO_HUUCO);

  delay(500);
  Serial.println(F("=== TEST 4 CAM BIEN SIEU AM - ARDUINO NANO ==="));
  Serial.println(F("AI D9/D8 | NHUA A1/A0 | GIAY A3/A2 | HUUCO A5/A4"));
}

void loop() {
  const unsigned long now = millis();
  if (now - lastPrintTime < PRINT_INTERVAL_MS) return;
  lastPrintTime = now;

  // Đo lần lượt và chờ giữa các cảm biến để hạn chế nhiễu chéo siêu âm.
  const long distanceAi = measureDistanceCm(TRIG_AI, ECHO_AI);
  delay(SENSOR_GAP_MS);
  const long distanceNhua = measureDistanceCm(TRIG_NHUA, ECHO_NHUA);
  delay(SENSOR_GAP_MS);
  const long distanceGiay = measureDistanceCm(TRIG_GIAY, ECHO_GIAY);
  delay(SENSOR_GAP_MS);
  const long distanceHuuCo = measureDistanceCm(TRIG_HUUCO, ECHO_HUUCO);

  Serial.print(F("[4 SENSOR] "));
  printDistance(F("AI"), distanceAi);
  Serial.print(F(" | "));
  printDistance(F("NHUA"), distanceNhua);
  Serial.print(F(" | "));
  printDistance(F("GIAY"), distanceGiay);
  Serial.print(F(" | "));
  printDistance(F("HUUCO"), distanceHuuCo);
  Serial.println();
}
