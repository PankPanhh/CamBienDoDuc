#include <Arduino.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// Pin definitions
#define SENSOR_PIN A0
#define ALERT_PIN 8
#define LCD_ADDR 0x27
#define LCD_COLS 16
#define LCD_ROWS 2

// Sensor parameters
const float U0 = 3600.0; // Reference voltage at 0 NTU (mV)
const float VCC = 5000.0; // Arduino supply voltage (mV)
const float ADC_MAX_COUNT = 1023.0; // ADC resolution

// Timing
unsigned long lastReading = 0;
const unsigned long READING_INTERVAL = 1000; // Update every 1 second
const unsigned long STARTUP_DELAY = 100; // Sensor startup time (ms)

// Initialize I2C LCD
LiquidCrystal_I2C lcd(LCD_ADDR, LCD_COLS, LCD_ROWS);

// Read average voltage to reduce noise
float readSensorVoltage(uint16_t samples = 15, uint16_t delayMs = 5) {
  uint32_t sum = 0;
  for (uint16_t i = 0; i < samples; i++) {
    sum += analogRead(SENSOR_PIN);
    delay(delayMs);
  }
  float avg = sum / (float)samples;
  return (avg / ADC_MAX_COUNT) * VCC; // Convert to mV
}

// Convert voltage to NTU based on sample code calibration
float voltageToNTU(float voltage) {
  float f = voltage / U0;
  float ntu;
  if (f >= 0.98 && f <= 1.0) {
    ntu = 0.0; // Clear water or no water
  } else {
    ntu = map(f * 100, 0, 100, 1000, 0); // Map to 0–1000 NTU
  }
  if (ntu < 0.0) ntu = 0.0;
  if (ntu > 1000.0) ntu = 1000.0; // Constrain to sensor range
  return ntu;
}

void setup() {
  // Initialize pins
  pinMode(SENSOR_PIN, INPUT);
  pinMode(ALERT_PIN, OUTPUT);
  digitalWrite(ALERT_PIN, LOW);

  // Initialize Serial
  Serial.begin(9600);
  
  // Initialize LCD
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("Cam bien do duc nuoc");
  lcd.setCursor(0, 1);
  lcd.print("Khoi dong...");
  delay(STARTUP_DELAY);
  lcd.clear();
  
  // Không in thông báo khởi động để tránh làm nhiễu dữ liệu
}

void loop() {
  // Handle incoming serial commands from PC
  if (Serial.available() > 0) {
    char cmd = (char)Serial.read();
    if (cmd == 'A') {
      digitalWrite(ALERT_PIN, HIGH);
      Serial.println("ACK:A");
    } else if (cmd == 'S') {
      digitalWrite(ALERT_PIN, LOW);
      Serial.println("ACK:S");
    }
  }

  if (millis() - lastReading >= READING_INTERVAL) {
    // Read sensor voltage
    float voltage = readSensorVoltage(15, 5);
    float ntu = voltageToNTU(voltage);
    
    // Send data to Python GUI (Chỉ gửi 1 dòng này)
    Serial.print("Vôn:");
    Serial.print(voltage, 0); // Send voltage in mV (integer)
    Serial.print(",Độ đục:");
    Serial.println(ntu, 2);
    
    // Update LCD
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("V: ");
    lcd.print(voltage / 1000.0, 2); // Display in V
    lcd.print(" V   ");
    lcd.setCursor(0, 1);
    lcd.print("NTU: ");
    lcd.print(ntu, 1);
    lcd.print("    ");
    
    lastReading = millis();
  }
  
  // delay(100) này không ảnh hưởng nhiều, có thể giữ lại
  delay(100); // Prevent overwhelming serial
}