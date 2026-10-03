## CityResponder Hardware Source of Truth

Before modifying any ESP32 firmware, GPIO assignments, sensor logic,
actuator logic, calibration code, or hardware integration, read:

`docs/hardware/CityResponder_GPIO_Breadboard_Reference.md`

Important rules:
- Do not change GPIO assignments unless explicitly approved by the user.
- ESP32 #1 is SN1, the Sensor Node.
- ESP32 #2 is AC1, the Actuator Node.
- SN1 and AC1 are separate ESP32 boards and communicate through Wi-Fi/backend.
- Do not assume image-generated diagrams are electrically authoritative.
- Use the Markdown hardware reference as the authoritative wiring specification.
- If firmware and the hardware reference disagree, STOP and report the mismatch before changing anything.
- Hardware calibration values such as MQ-2 thresholds, IR polarity,
  buzzer polarity, and servo angles are NOT fixed until measured on the real prototype.
- Never silently change pin assignments to make code compile.
- Preserve the two-node architecture.
