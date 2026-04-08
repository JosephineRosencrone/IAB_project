// Electrode placement:
// White on mastoid bone, red on left temple, white on right temple
// Pins: GND (black), 3.3V (red), signal (purple → A0)

const int eogPin = A0;
const int emgPin = A1;

// --- EOG ---
float eogFiltered = 0;

// --- EMG ---
float emgEnvelope = 0;
int emgBaseline = 512;

void setup() {
  Serial.begin(115200);

  // Optional: better baseline initialization
  emgBaseline = analogRead(emgPin);
}

void loop() {
  int eogRaw = analogRead(eogPin);
  int emgRaw = analogRead(emgPin);

  // ===== EOG smoothing =====
  eogFiltered = 0.9 * eogFiltered + 0.1 * eogRaw;

  // ===== EMG envelope =====
  int centered = emgRaw - emgBaseline;
  float rectified = abs(centered);
  emgEnvelope = 0.9 * emgEnvelope + 0.1 * rectified;

  // ===== Baseline tracking (only when relaxed) =====
  if (emgEnvelope < 10) {
    emgBaseline = 0.999 * emgBaseline + 0.001 * emgRaw;
  }

  // ===== SERIAL OUTPUT (IMPORTANT FORMAT) =====
  Serial.print("EOG:");
  Serial.print(eogFiltered);
  Serial.print(",EMG:");
  Serial.println(emgEnvelope);

  delay(20); // 
}