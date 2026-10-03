# AC1 hardware bring-up

This isolated PlatformIO project provides manual, serial-controlled validation of the real AC1 actuator node on COM7. It does not use Wi-Fi, MQTT, backend commands, ACKs, or automatic actuator sequences.

Authoritative GPIO mapping:

- Traffic Light 1: red GPIO25, yellow GPIO26, green GPIO27
- Traffic Light 2: red GPIO14, yellow GPIO13, green GPIO23
- Buzzer signal: GPIO19; physical trigger polarity is unverified
- SG90 signal: GPIO18; the firmware never attaches or moves the servo

At startup, all six LED outputs are LOW. The buzzer and servo pins remain inputs. Actuators change only after an explicit serial command at 115200 baud. `SERVO_SET_30` and `SERVO_SET_90` are bounded movement checks, not open/closed calibration values; `SERVO_RELEASE` detaches the servo.
