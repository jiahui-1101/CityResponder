# 3. Severity (A / S_smoke / T_heat / P / Z)

**Formula:** `R = 100 * (0.30A + 0.20 S_smoke + 0.20 T_heat + 0.20P + 0.10Z)`

---

### TBD-SEV-01: `A` meaning, source, normalization, and missing behavior
*   **Meaning & Source:** `A` represents the fire extent using the Pixel Ratio method, calculated as `fire bounding box area / hazard zone polygon area`. It uses the YOLO bounding box for the **fire** only, excluding smoke to prevent double-counting with `S_smoke`.
*   **Normalization:** The maximum value is capped at 1.0.
*   **Missing Behavior:** If `A` is unavailable, `R` cannot be calculated. The system does not pick a default severity; the Operator must manually choose the severity.

### TBD-SEV-02: Severity S

* **Decision:** Severity does not reuse the Fusion `S_fusion` score, because `S_fusion` already includes temperature information, which would cause temperature to be counted twice.
* **Definition:** Severity uses `S_smoke`, representing the pure MQ-2 smoke score.
* **Normalization:** Normal baseline = 500; alarm threshold = 2000.
* **Range:** `S_smoke` is normalized to 0–1.

### TBD-SEV-03: Severity T

* **Decision:** Severity does not use the Fusion `T_temporal` score.
* **Definition:** Severity uses `T_heat`, representing the pure DHT22 temperature score.
* **Normalization:** Normal baseline = 30°C; demo alarm threshold = 40°C. Readings at or above 40°C produce the maximum heat score.
* **Range:** `T_heat` is normalized to 0–1.

### TBD-SEV-04: Production hazard-zone geometry and boundary rule
*   **Geometry:** The hazard zone is a polygon. The coordinates must be physically measured in the sandbox.
*   **Boundary Rule:** `P = 1` if the center of the person's bounding box is inside the hazard zone polygon.
*   **Trigger Rule:** Requires a minimum YOLO confidence of 0.50. Only **1 frame** of detection is needed to trigger `P = 1` because smoke can hide a person quickly (life safety prioritized).

### TBD-SEV-05: `Z` meaning, source, normalization, and missing behavior
*   **Meaning & Source:** `Z` is the Zone Vulnerability Score.
*   **Normalization:** It uses fixed values defined in the configuration file for each building zone. Prototype values are: Low = 0.30, Normal = 0.60, High = 1.00.
*   **Missing Behavior:** As it is a fixed configuration value per zone, it is never missing.

### TBD-SEV-06: Low/Medium/High/Critical numeric boundaries
*   **Numeric Boundaries (when P = 0):**
    *   Low: 0–29
    *   Medium: 30–49
    *   High: 50–69
    *   Critical: 70–80
*   **Critical Override:** If `P = 1`, the severity is always Critical.
*   **Operator Override & Floor Rule:**
    *   A manual dispatch uses `R` if it exists; it does not automatically default to Critical.
    *   If `R` cannot be calculated, the Operator chooses the severity.
    *   When `R` exists, `R` decides. An Operator-chosen severity acts as a **floor**—if `R` later becomes available and indicates a higher severity, the higher severity takes over automatically (per the Incident lock rule).
