# 2. Fire Fusion (S / T / V / H)

**Formula:** `C = 100 * (0.30 S_fusion + 0.20 T_temporal + 0.35 V + 0.15 H)`[cite: 18]

## 1. S_fusion (Sensor Normalization)
The `S_fusion` score represents the maximum value between normalized smoke and heat levels[cite: 18]. 
*   **DHT22 (Temperature):** The normal baseline is 30°C, and the alarm threshold is 50°C[cite: 18]. Data becomes stale after 3.0 s[cite: 18].
*   **MQ-2 (Smoke):** The normal baseline is 500, and the alarm threshold is 2000 on a 0–4095 analog scale[cite: 18]. Data becomes stale after 2.0 s[cite: 18].
*   **Calculation:** Each sensor's reading is normalized to a 0–1 scale and clamped[cite: 18]. `S_fusion = max(s_smoke, s_heat)`[cite: 18]. 
*   **Fallback:** If one sensor is stale, the system uses the remaining available sensor[cite: 18]. If both are stale, `S_fusion` is unavailable and the `C` score is not calculated[cite: 18].

## 2. T_temporal (Temporal Consistency)
The `T_temporal` score measures the persistence of the hazard over time[cite: 18].
*   **Calculation:** It is calculated as the number of windows with valid evidence divided by 3, analyzing the last 3 one-second windows[cite: 18].
*   **Evidence Threshold:** A window contains valid evidence if `S_fusion ≥ 0.20`, `V ≥ 0.50`, or the manual button is pressed[cite: 18]. 
*   **Note:** This confidence metric operates independently from the strict "3-window rule" required for final automatic confirmation[cite: 18].

## 3. V (Vision Normalization)
The `V` score relies on the YOLO model's evaluation of the building's Region of Interest (ROI)[cite: 18].
*   **Calculation:** `V = max(fire confidence, smoke confidence)`[cite: 18].
*   **Constraints:** The minimum accepted YOLO confidence is 0.50[cite: 18]. Overlapping bounding boxes are not added together[cite: 18]. Person detection is excluded from this metric as it is handled by the Severity module[cite: 18]. 
*   **Stale Limit:** Camera frames older than 1.0 s render `V` unavailable[cite: 18].

## 4. H (Historical Baseline)
The `H` score accounts for the 180-day verified historical risk of the area[cite: 18].
*   **Calculation:** `H = Area Risk Score / 100`, sourced from operator-verified incidents in the SQLite database[cite: 18].
*   **Cold Start:** If there is no history, `H = 0` and the log records "no_history" (an exception to the standard "no zero fill" rule)[cite: 18].

## 5. Event Confirmation & Channels
Automatic dispatch requires a strong, sustained signal across multiple physical sources[cite: 18].
*   **Auto-Confirmation Gate:** The system automatically confirms an incident when `C ≥ 40` for 3 consecutive windows, supported by at least 2 independent channels[cite: 18].
*   **Supporting Channels:** Valid channels include Smoke (`s_smoke ≥ 0.30`), Heat (`s_heat ≥ 0.30`), Camera (`V ≥ 0.30`), and the Manual Button (score = 1.0)[cite: 18].
*   **Manual Button Workflow:** Pressing the button instantly creates an `ALERT` state on the dashboard and acts as one supporting channel, but it does not bypass the 3-window rule for automatic confirmation[cite: 18].
*   **Manual Override & Race Conditions:** If the Operator manually confirms the alert, the "2 physical sensors" requirement is skipped[cite: 18]. However, if the automatic gate passes before the Operator confirms, the system's automated confirmation takes precedence, and the Operator's confirmation is ignored (lock rule)[cite: 18]. 

## 6. Hardware & Stale Data Rules
*   **Stale Data Handling:** A reading is marked unavailable (and logged as `SENSOR_STALE` with its source ID, e.g., `MQ2`, `CAM`) if the read fails, returns NaN, falls outside the sensor range, or exceeds its specific stale time limit[cite: 18]. 
*   **DHT22 Polling:** Because the DHT22 updates approximately every 2 seconds, its last value is held across the 1-second fusion windows, which is covered by its 3.0 s stale limit[cite: 18].
*   **MQ-2 Warm-Up:** The MQ-2 sensor requires a 60-second warm-up period after power-on to stabilize[cite: 18]. During this time, smoke data is marked unavailable, and `S_fusion` relies solely on heat[cite: 18]. 
*   **Wiring:** The MQ-2 analog output must be connected to an ESP32 ADC1 pin using a voltage divider to reduce its 5V output to the ESP32's 3.3V maximum[cite: 18].