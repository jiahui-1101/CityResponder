# CityResponder ESP32 GPIO & Breadboard Reference

> Purpose: prompt-ready hardware reference for future coding / Codex work.  
> Prototype: CityResponder smart-city fire detection and rerouting demo.  
> Board: 2 × ESP32 DevKit V1  
> Breadboard: MB102, columns A-J, rows 0-60  
> Current design: SN1 = sensing, AC1 = actuation

---

## 1. System Split

### ESP32 #1 — SN1 Sensor Node
Responsible for:
- MQ-2 smoke / gas sensing
- DHT22 temperature sensing
- IR Sensor 1 — main route blockage
- IR Sensor 2 — alternate route blockage
- Manual push button

### ESP32 #2 — AC1 Actuator Node
Responsible for:
- Traffic Light 1 — Red / Yellow / Green
- Traffic Light 2 — Red / Yellow / Green
- Active buzzer
- SG90 servo gate

The two ESP32 boards do **not** require direct jumper wiring between them if they communicate through Wi-Fi / backend.

---

## 2. FINAL GPIO MAP

### SN1 — ESP32 #1

| Component | Signal | ESP32 Pin | Power | Ground |
|---|---|---:|---|---|
| MQ-2 | AO via voltage divider | GPIO34 | VIN / 5V | GND rail |
| DHT22 | DATA | GPIO4 | 3.3V | GND rail |
| IR Sensor 1 | OUT | GPIO32 | 3.3V | GND rail |
| IR Sensor 2 | OUT | GPIO33 | 3.3V | GND rail |
| Push Button | Signal | GPIO27 | No VCC needed | GND |
| MQ-2 | DO | Not used | - | - |

### AC1 — ESP32 #2

| Component | Signal | ESP32 Pin |
|---|---|---:|
| Traffic Light 1 Red | LED signal | GPIO25 |
| Traffic Light 1 Yellow | LED signal | GPIO26 |
| Traffic Light 1 Green | LED signal | GPIO27 |
| Traffic Light 2 Red | LED signal | GPIO14 |
| Traffic Light 2 Yellow | LED signal | GPIO13 |
| Traffic Light 2 Green | LED signal | GPIO23 |
| Buzzer | SIG / IN | GPIO19 |
| SG90 Servo | PWM / Signal | GPIO18 |

---

## 3. Power Rules

### SN1
Use Breadboard 1 rails:
- `+ rail` = 3.3V
- `- rail` = GND

```text
ESP32 SN1 3V3 -> Breadboard 1 + rail
ESP32 SN1 GND -> Breadboard 1 - rail
```

Use the 3.3V rail for:
- DHT22 VCC
- IR1 VCC
- IR2 VCC

Use the GND rail for:
- MQ-2 GND
- DHT22 GND
- IR1 GND
- IR2 GND
- Push button GND
- MQ-2 voltage-divider bottom resistor

MQ-2 VCC:
```text
MQ-2 VCC -> ESP32 VIN / 5V
```

Do **not** connect MQ-2 VCC to the 3.3V rail.

### AC1
Recommended Breadboard 2 rail assignment:

```text
Top + rail    = 3.3V
Top - rail    = GND

Bottom + rail = VIN / 5V
Bottom - rail = GND
```

Connections:

```text
ESP32 AC1 3V3 -> Top + rail
ESP32 AC1 GND -> Top - rail
ESP32 AC1 VIN -> Bottom + rail
Top - rail -> Bottom - rail
```

Use:
- 3.3V rail for buzzer only if the buzzer module supports 3.3V
- 5V rail for SG90 servo
- GND rail for all AC1 components

Important:
- SG90 signal -> GPIO18
- Servo VCC -> 5V / VIN rail
- Servo GND -> AC1 GND rail
- If servo causes ESP32 reset / brownout, use an external 5V servo supply later and connect its GND to AC1 GND.

---

## 4. MQ-2 Voltage Divider

Use this divider:

```text
MQ-2 AO
  |
  20kΩ
  |
  +----> GPIO34
  |
  10kΩ
  |
  GND
```

Recommended resistor values:
- Upper resistor: 20kΩ
- Lower resistor: 10kΩ

---

## 5. Breadboard 1 — SN1 Exact Layout

Breadboard type:
- MB102
- Columns A-J
- Rows 0-60

Internal connection rule:
- A-B-C-D-E on the same row are connected
- F-G-H-I-J on the same row are connected
- E and F are separated by the center gap
- Some MB102 power rails may be split in the middle; bridge them if needed

### SN1 Power Rail

```text
ESP32 3V3 -> Breadboard 1 + rail
ESP32 GND -> Breadboard 1 - rail
```

If the rail is split near the middle:

```text
+ rail near row 29 -> + rail near row 31
- rail near row 29 -> - rail near row 31
```

### MQ-2 on Breadboard 1

```text
MQ-2 VCC -> ESP32 VIN / 5V
MQ-2 GND -> Breadboard 1 GND rail
MQ-2 AO  -> A10
MQ-2 DO  -> not used
```

Divider placement:

```text
20kΩ resistor:
C10 -> C15

GPIO34 jumper:
A15 -> ESP32 GPIO34

10kΩ resistor:
D15 -> D20

GND jumper:
A20 -> Breadboard GND rail
```

Equivalent circuit:

```text
A10 row = MQ-2 AO
   |
 20kΩ
   |
A15 row = divider node
   |----> GPIO34
   |
 10kΩ
   |
A20 row
   |
 GND rail
```

---

## 6. DHT22 — SN1

For a 3-pin DHT22 module:

```text
DHT22 VCC  -> Breadboard 1 + rail (3.3V)
DHT22 GND  -> Breadboard 1 - rail
DHT22 DATA -> ESP32 GPIO4
```

If using a bare 4-pin DHT22 instead of a 3-pin module, the pull-up arrangement may be different.

---

## 7. IR Sensors — SN1

### IR1 — Main Route

```text
IR1 VCC -> 3.3V rail
IR1 GND -> GND rail
IR1 OUT -> GPIO32
```

### IR2 — Alternate Route

```text
IR2 VCC -> 3.3V rail
IR2 GND -> GND rail
IR2 OUT -> GPIO33
```

Typical IR modules often output LOW when an obstacle is detected, but firmware must verify the actual module behavior during testing.

---

## 8. Push Button — SN1 Breadboard Layout

Use internal pull-up in firmware.

GPIO:
```text
Button -> GPIO27
```

Recommended exact placement:

```text
Button legs:
E48
E50
F48
F50
```

The button straddles the center gap.

Connections:

```text
A48 -> ESP32 GPIO27
J48 -> Breadboard GND rail
```

Firmware:

```cpp
pinMode(27, INPUT_PULLUP);
```

Expected behavior:

```text
Not pressed = HIGH
Pressed     = LOW
```

The button:
- does not need 3.3V
- does not need an external resistor

---

## 9. Breadboard 2 — AC1 Power Layout

```text
Top + rail    -> ESP32 3V3
Top - rail    -> ESP32 GND

Bottom + rail -> ESP32 VIN / 5V
Bottom - rail -> GND
```

Bridge GND rails:

```text
Top - rail -> Bottom - rail
```

If rails are split, bridge both halves.

---

## 10. Traffic Light LEDs — AC1

Each LED must have its own resistor.

Recommended:
- 220Ω to 330Ω
- use 220Ω if that is what is available

General circuit:

```text
ESP32 GPIO -> resistor -> LED long leg / anode
LED short leg / cathode -> GND rail
```

### Traffic Light 1

#### Red — GPIO25

```text
GPIO25 -> A5
220Ω: C5 -> C8
LED long leg  -> A8
LED short leg -> A10
B10 -> GND rail
```

#### Yellow — GPIO26

```text
GPIO26 -> A13
220Ω: C13 -> C16
LED long leg  -> A16
LED short leg -> A18
B18 -> GND rail
```

#### Green — GPIO27

```text
GPIO27 -> A21
220Ω: C21 -> C24
LED long leg  -> A24
LED short leg -> A26
B26 -> GND rail
```

### Traffic Light 2

#### Red — GPIO14

```text
GPIO14 -> F31
220Ω: H31 -> H34
LED long leg  -> F34
LED short leg -> F36
G36 -> GND rail
```

#### Yellow — GPIO13

```text
GPIO13 -> F39
220Ω: H39 -> H42
LED long leg  -> F42
LED short leg -> F44
G44 -> GND rail
```

#### Green — GPIO23

```text
GPIO23 -> F49
220Ω: H49 -> H52
LED long leg  -> F52
LED short leg -> F54
G54 -> GND rail
```

LED orientation:

```text
long leg  = Anode (+)
short leg = Cathode (-)
```

---

## 11. Buzzer — AC1

Current planned signal pin:

```text
Buzzer SIG / IN -> GPIO19
```

If using a 3-pin active buzzer module:

```text
Buzzer VCC -> 3.3V rail
Buzzer GND -> GND rail
Buzzer SIG -> GPIO19
```

Important:
- actual active-buzzer trigger polarity must be tested
- some modules are active LOW
- if module labeling says 5V-only, revise VCC before final wiring

---

## 12. SG90 Servo — AC1

GPIO:

```text
Servo signal -> GPIO18
```

Temporary USB-powered setup:

```text
Servo VCC red       -> VIN / 5V rail
Servo GND brown     -> GND rail
Servo signal orange -> GPIO18
```

If the ESP32 resets when the servo moves:
- likely power brownout / current issue
- use an external regulated 5V supply for servo
- external supply GND must connect to AC1 GND

---

## 13. Webcam

Webcam is NOT connected to either ESP32.

```text
USB Webcam -> Laptop / Central Server
```

Purpose:
- Building A ROI
- fire / smoke / person detection
- road obstacle segmentation
- full-board overhead view

Current physical board:
- about 40 cm × 41 cm

Recommended starting webcam height:
- about 50 cm above board surface
- adjust within about 45-55 cm
- goal is for the entire 40 × 41 cm board to fill most of the camera frame

---

## 14. Current Route Logic

### Main Route
- monitored by IR1
- IR1 OUT -> GPIO32
- preferred because it has fewer turns

### Alternate Route
- used when main route is blocked
- monitored by IR2
- IR2 OUT -> GPIO33

### Servo Gate
- placed on the alternate route
- opens when the alternate route is selected / safe-entry action is triggered

---

## 15. Recommended Test Order

### SN1
1. Connect ESP32 by USB
2. Test 3.3V and GND rails
3. Test DHT22
4. Test IR1
5. Test IR2
6. Test push button
7. Test MQ-2 last
8. Log serial values
9. Tune normal baseline
10. Tune fire-condition readings

### AC1
1. Connect ESP32 by USB
2. Test one LED first
3. Test all 6 LEDs individually
4. Test buzzer
5. Test SG90 servo last
6. Check for brownout / ESP32 resets
7. Test traffic-light states
8. Test route-dependent actuator behavior

---

## 16. Prompt-Ready Summary for Codex

```text
Hardware: CityResponder prototype using two ESP32 DevKit V1 boards.

ESP32 #1 = SN1 Sensor Node
- MQ-2 AO -> GPIO34 through the final 20k/10k voltage divider (20k upper / 10k lower)
- MQ-2 VCC -> VIN / 5V
- MQ-2 GND -> SN1 GND rail
- DHT22 DATA -> GPIO4
- DHT22 VCC -> 3.3V
- DHT22 GND -> GND
- IR Sensor 1 OUT -> GPIO32
- IR Sensor 1 VCC -> 3.3V
- IR Sensor 1 GND -> GND
- IR Sensor 2 OUT -> GPIO33
- IR Sensor 2 VCC -> 3.3V
- IR Sensor 2 GND -> GND
- Push button -> GPIO27 and GND
- Push button uses INPUT_PULLUP

ESP32 #2 = AC1 Actuator Node
Traffic Light 1:
- Red -> GPIO25 through 220-330Ω resistor
- Yellow -> GPIO26 through 220-330Ω resistor
- Green -> GPIO27 through 220-330Ω resistor

Traffic Light 2:
- Red -> GPIO14 through 220-330Ω resistor
- Yellow -> GPIO13 through 220-330Ω resistor
- Green -> GPIO23 through 220-330Ω resistor

Other AC1:
- Active buzzer SIG -> GPIO19
- SG90 servo signal -> GPIO18
- Servo VCC -> VIN / 5V
- Servo GND -> AC1 GND

Breadboard:
- MB102, A-J, rows 0-60
- Breadboard 1 is SN1
- Breadboard 2 is AC1
- Use GND rails as shared ground buses
- Use SN1 3.3V rail for DHT22 + IR1 + IR2
- Use AC1 5V rail for servo
- Every LED has its own resistor
- Webcam connects to laptop, not ESP32

Route logic:
- IR1 monitors main route
- IR2 monitors alternate route
- if main route is blocked, system reroutes to alternate route
- SG90 gate is on the alternate route
- traffic lights are controlled by AC1

Do not change GPIO assignments unless explicitly requested.
```

---

## 17. Important Caveats

- Always trust the physical labels printed on the actual ESP32 board, not image-generated pin placement.
- GPIO34 is input-only, which is fine for MQ-2 ADC input.
- IR module output polarity should be measured during testing.
- Buzzer trigger polarity should be measured during testing.
- MQ-2 needs warm-up and baseline calibration.
- MQ-2 fire detection should use calibrated readings, not an arbitrary hard-coded threshold.
- Servo current may cause ESP32 brownout when powered from USB/VIN.
- Some MB102 power rails are split in the center; bridge them if necessary.
- If a breadboard rail is used as GND, only one ESP32 GND jumper is needed to create many usable GND points.
