# AC1 hardware bring-up

This isolated PlatformIO project provides manual, serial-controlled validation of the real AC1 actuator node. COM7 is a historical port, not a fixed AC1 identity. On 2026-10-26 the user confirmed only AC1 is physically connected, and Windows/PlatformIO enumerate the sole USB serial adapter as COM5. One authorized passive COM5 session produced AC1-specific MQTT logs, confirming the device; its installed firmware version remains unknown. Select the verified port explicitly for each monitor or upload session. It does not use Wi-Fi, MQTT, backend commands, ACKs, or automatic actuator sequences.

Authoritative GPIO mapping:

- Traffic Light 1 (PRIMARY/MAIN route): red GPIO14, yellow GPIO13, green GPIO23
- Traffic Light 2 (STANDBY route): red GPIO25, yellow GPIO26, green GPIO27
- Buzzer signal: GPIO19; physical trigger polarity is unverified
- SG90 signal: GPIO18; the firmware never attaches or moves the servo

At startup, all six LED outputs are LOW. The buzzer and servo pins remain inputs. Actuators change only after an explicit serial command at 115200 baud. `SERVO_SET_30` and `SERVO_SET_90` are bounded movement checks, not open/closed calibration values; `SERVO_RELEASE` detaches the servo.

Opening an ESP32 serial port can toggle DTR/RTS and reset the board. Confirm the connected firmware and physical output power state before monitoring; obtain operator approval if a reset could move an actuator. Do not send serial commands during passive identity checks.
