# 3. Severity (A / S / T / P / Z)

Note: if there is no person (P = 0), the highest possible R is only 80.

### TBD-SEV-01: A
**What's missing:** the proposal never says what A is.
**Zhenjie's guess:** fire extent (how big the fire is compared to the hazard area), because section 3.2 talks about knowing the "scope" of the fire. But I really am not sure.
**Need from team:** what is A? If my guess is right, what size counts as 1.0? **[measure]**
**Jiabao's proposed idea:** I suggest we use the **Pixel Ratio** method. `A` is calculated by dividing the pixel count of the fire/smoke area by the total pixel count of the hazard zone polygon. We can start by using the YOLO Bounding Box area for the fire, and upgrade to pixel segmentation later if needed. The actual physical pixel boundaries still need to be measured in the sandbox.

### TBD-SEV-02: Severity S
**What's missing:** whether this is the same S as in fusion.
**Zhenjie's idea:** just reuse the fusion S so we only keep one normalization.
**Jiabao's proposed idea:** We should **NOT** reuse the fusion S. If we do, temperature gets double-counted in the final severity formula. I propose we redefine `S` in the Severity module strictly as the **pure smoke score (MQ-2)**. My suggested normalization baseline based on testing is: normal = 500, alarm = 2000.

### TBD-SEV-03: Severity T
**What's missing:** exact meaning.
**Zhenjie's idea:** use the temperature score (how hot), not the temporal T from fusion. I think we should rename them in code (like `T_heat` and `T_temporal`) so nobody gets confused. (B) Under Option B they are the same T.
**Jiabao's proposed idea:** I agree. To prevent collision with the temporal `T` in Fire Fusion, we should officially rename this variable to **`T_heat`**. It will represent the pure temperature score (DHT22). My suggested normalization baseline is: normal = 30°C, alarm = 50°C.

### TBD-SEV-04: P, hazard zone
**What's missing:** the hazard zone shape, and the rule when a person is on the edge.
**Zhenjie's idea:** draw the hazard zone as a polygon around each building ROI on the camera image. P = 1 if the center of the person's bounding box is inside the polygon (edge counts as inside). The proposal says Critical "immediately", so one frame would be enough, but that may cause false alarms.
**Need from team:** the polygon coordinates **[measure]**. One frame or several frames?
**Jiabao's proposed idea:** I agree with using the center of the bounding box and 1 frame for the Critical override. However, to prevent false alarms from just 1 frame, I propose we set a strict **YOLO confidence threshold of 0.50** for a valid person detection. Polygon coordinates still need physical measurement.

### TBD-SEV-05: Z
**What's missing:** the proposal never says what Z is.
**Zhenjie's guess:** how sensitive the zone is, like a fixed value for each building type (residential higher, empty lot lower). Not sure at all.
**Need from team:** what is Z, and what are the values?
**Jiabao's proposed idea:** Yes, it is the Zone Vulnerability Score. For the prototype code, I propose we hardcode the initial values as: Low-risk = 0.30, Normal-risk = 0.60, and High-risk = 1.00. We can adjust these later during physical testing.

### TBD-SEV-06: Severity bands
**What's missing:** the score ranges for Low, Medium, High, Critical.
**Zhenjie's rough idea (not calibrated):** Low below 30, Medium 30 to 55, High 55 to 75, Critical 75 and above, or P = 1. I picked these because the max without a person is 80, so Critical is still reachable. Please don't treat this as final.
**Also:** if R can't be calculated, I think the operator should choose the severity manually instead of us picking a default.
**Jiabao's proposed idea:** Let's use the following initial bands for the code implementation: Low (0–29), Medium (30–49), High (50–69), and Critical (70–80). These will act as our baseline in the code, pending physical fire testing for final calibration.