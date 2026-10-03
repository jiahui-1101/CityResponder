## Routing Production Calibration

**Formula:** `edge_cost = distance_cm * (1 + 4 * (0.70O + 0.20L + 0.10C_routing))`. Blocked or conflicted edges are removed from the graph.

**Marks:** **[measure]** = must be measured on the real model. **[confirm]** = the team must confirm it.

### TBD-ROUTE-01: Conversion of Segmentation Evidence into Routing `O`
*   **Definition:** `O` = obstacle mask pixels / road ROI pixels (0 to 1). It is used in the cost.
*   **Smoothing:** use the median of 3 frames (about 1.5 s). The proposal uses a median (Figure 7.2, step 8). The 3 frames are our choice.
*   **`O_ir`:** the same calculation, but only in the small zone around the IR beam. It is used only for the camera state in ROUTE-06. It is **not** used in the cost.
*   **Camera BLOCKED:** `O_ir` ≥ 0.80 **or** whole-road `O` ≥ 0.80.
*   **Stale limit:** if the newest frame is older than 1.0 s, the camera data is stale (`SENSOR_STALE`).
*   **[measure]** the real segmentation delay. If the newest frame is often close to 1.0 s, change the stale limit in the Routing, Fusion and Severity files together.

### TBD-ROUTE-02: Routing `L` Meaning and Normalization
*   **Meaning [confirm]:** Figure 6 shows "L_e (Length)" next to O_e. `L` is the obstacle length. The road length is already `distance_cm`.
*   **Formula:** `L = min(obstacle length / road length, 1.0)`.
*   **How to measure:** the longest side of the mask along the road. Pixels are converted to cm with the ArUco markers.

### TBD-ROUTE-03: Routing `C`, Distinct from Fire Confidence `C`
*   **Name:** the routing term is `C_routing`, so it is never mixed up with the fire confidence `C`.
*   **Meaning [confirm]:** the proposal does not define it. We assume it is road condition (potholes).
*   **Formula:** `C_routing = pothole mask area / road ROI area`, maximum 1.0.
*   **Rule:** keep the pothole mask and the obstacle mask separate, so the same pixels are not counted twice.

### TBD-ROUTE-04: IR Polarity, Debounce/Noise Handling, and Edge Mapping
*   **Edge mapping [confirm]:** there are exactly 2 IR modules. `IR-A` watches Route A. `IR-B` watches Route B. Mount each one at the narrowest point of its road.
*   **Polarity [measure]:** test the real module. Is the output HIGH or LOW when blocked? Write in the firmware what "BLOCKED" means.
*   **Debounce:** see ROUTE-05.
*   **Noise and reflection:** tune the sensitivity knob and test on the real road. Paper and shiny tape can reflect IR light.
*   **Prop rule:** every test obstacle must be tall and big enough for the IR to see it, and it must be inside the `O_ir` zone. No flat or low items (for example tape on the road).
*   **Demo rule:** no hands or tools on the road.

### TBD-ROUTE-05: Exact IR Sample Timing/Support Rule
*   **Blocked:** 5 blocked samples in a row (proposal: "5 IR samples"). One clear sample resets the count to 0.
*   **Unblock:** 5 clear samples in a row, so the road does not flicker.
*   **Sample time:** one sample every 200 ms.
*   **Stale limit:** an IR sample older than 400 ms is stale (`SENSOR_STALE`). The time used in checks is the time of the newest of the 5 samples.

### TBD-ROUTE-06: All Production Camera/IR Conflict Cases and Operator Resolution
*   **Camera states (median of 3 frames):**
    *   `BLOCKED`: `O_ir` ≥ 0.80 or whole-road `O` ≥ 0.80.
    *   `CLEAR`: `O_ir` < 0.20 and whole-road `O` < 0.20. Test the 0.20 limit with real masks **[measure]**.
    *   `MIDDLE`: anything else.
*   **All cases:**

| Camera | IR blocked | IR clear |
|---|---|---|
| BLOCKED | **BLOCKED** | **SENSOR_CONFLICT** |
| MIDDLE | passable, extra cost only | passable, extra cost only |
| CLEAR | **SENSOR_CONFLICT** | **OPEN** |

*   **Why MIDDLE is not a conflict [confirm]:** IR is only yes or no, so any object in the beam makes it "blocked". The camera says the object covers only part of the road. Both agree something is there, so the cost formula handles it. If the team wants the safer rule, make "MIDDLE + IR blocked" a conflict. The price: every partial obstacle removes the road.
*   **Time rules:**
    *   Both sensors use the server clock. Measure the real delay **[measure]**.
    *   The check uses the newest camera frame and the newest IR sample.
    *   Time gap > 750 ms: `TIME_MISMATCH`.
    *   Camera older than 1.0 s, or IR sample older than 400 ms: `SENSOR_STALE`.
    *   The two sensors disagree: wait 1.5 s. If they still disagree: `SENSOR_CONFLICT`.
*   **Action on `SENSOR_STALE`, `TIME_MISMATCH` or `SENSOR_CONFLICT`:**
    *   Remove the edge, alert the Operator once, and wait for review (proposal, Figure 7.2, step 7).
    *   Save the code with the source ID (`CAM`, `IR-A`, `IR-B`) and the edge ID in the log.
    *   Check quietly afterwards. Alert again only if the situation changes.
    *   Do not use the other sensor alone. A wrong route is more dangerous than a missing evidence channel.
    *   If Route A and Route B are both removed: `NO_SAFE_ROUTE`, and the incident goes to failsafe.
*   **Recovery:**
    *   **Auto:** both sensors agree again (IR 5 samples, camera 3 frames), there is no stale or time problem, and the edge has been removed for at least 5 s. The 5 s stops the route from flipping.
    *   **Operator "verified clear":** needs a written reason. It expires after 60 s, or at once if a new conflict appears. It works only for `SENSOR_CONFLICT`, `SENSOR_STALE` and `TIME_MISMATCH`. It cannot override a road where both sensors agree it is BLOCKED.
*   **Test cases to add:** one sensor unplugged, both roads blocked, and a wide low obstacle outside the IR zone (expected: `SENSOR_CONFLICT`).

### TBD-ROUTE-07: Production Node/Edge Topology, Physical Distances, ROI/IR Mapping, and Source/Destination Mapping
*   **Topology [confirm]:** Figure 7.2 uses "S0 to A1". We assume `S0` is the fire station (source) and `A1` is Building A (destination). Both routes go from `S0` to `A1`.
*   **Mapping table [measure]:** measure these on the real model and fix them in the config file.

| Edge ID | From | To | Distance (cm) | Road ROI (pixels) | IR zone (pixels) | IR sensor |
|---|---|---|---|---|---|---|
| Route A | S0 | A1 | [measure] | [measure] | [measure] | IR-A |
| Route B | S0 | A1 | [measure] | [measure] | [measure] | IR-B |

### TBD-ROUTE-08: ETA Speed, Scale, Units, and Delay Assumptions
*   **ETA is removed.** The prototype has no moving vehicle and no speed model, so an ETA would be an invented number.
*   **Difference from the proposal:** the proposal shows ETA (Figure 7.1 and Figure 7.2, step 10). Write this in the report as a known difference, with the reason above.
*   **Display:** the dashboard and the Firefighter view show the route length (cm) and the route cost. Route ID and route version are still shown.
*   **Budget:** section 8.2 lists a "miniature vehicle". If there is no car, update that line.
*   **Replan delay:** the proposal goal is a new A* path within 1.0 s of a confirmed persistent blockage or incident alert.
    *   The 1.0 s starts when the blockage is confirmed.
    *   It does not include the sensors' own decision time: IR about 1.0 s, camera about 0.5 to 1.0 s, and a 1.5 s wait when the sensors disagree.
    *   It ends when the new route and its version are saved.
    *   The graph is very small (2 routes), so A* takes only milliseconds. Log the real time **[measure]**.
    *   Write the sensor decision time in the report, so nobody thinks the whole system reacts in 1.0 s.
