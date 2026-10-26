# CityResponder Phase 4.1B — AC1 connectivity and real ACK readiness

**Date:** 2026-10-26
**Branch:** `integration/cityresponder-phase2-phase36`
**Physical commands, firmware uploads, and service starts during this audit:** none
**Serial sessions:** one user-authorized, receive-only COM5 observation at 115200 baud for 18 seconds, DTR=0/RTS=0

## Acceptance status

```text
MQTT_BROKER_STATUS=FAIL
BROKER_AUTHENTICATION=FAIL
MQTT_ACL=FAIL
BROKER_LAN_REACHABILITY=FAIL
AC1_SERIAL_PORT=PASS
AC1_WIFI_CONNECTION=PARTIAL
AC1_MQTT_CONNECTION=FAIL
AC1_SUBSCRIPTION=NOT_VERIFIED
FIRMWARE_CONFIGURATION=BLOCKED
FIRMWARE_BUILD=PASS
FIRMWARE_UPLOAD=DEFERRED
PASSIVE_DEVICE_MONITORING=PASS
REAL_COMMAND_RECEIVED=DEFERRED
REAL_ACK_RECEIVED=DEFERRED
REAL_AC1_ACK=DEFERRED
BACKEND_ACK_VALIDATION=NOT_VERIFIED
PHYSICAL_OUTPUT_FEEDBACK=NOT_VERIFIED
ACK_LATENCY=NOT_VERIFIED
PRODUCTION_SAFETY=PARTIAL
```

`AC1_SERIAL_PORT=PASS` is based on the user's physical confirmation, current USB enumeration, and live AC1-specific serial logs from COM5. `AC1_WIFI_CONNECTION=PARTIAL` is an inference from MQTT connection attempts: the matching firmware source enters that code only when Wi-Fi reports connected, but no current IP/RSSI line was captured. `BACKEND_ACK_VALIDATION=NOT_VERIFIED` refers to a real device ACK. The isolated backend validation still passes. The firmware build is a compile-check image with placeholder AC1 credentials, **not an upload-ready image**.

## 2026-10-26 serial identity correction

```text
SN1_PHYSICALLY_CONNECTED=NO
AC1_PHYSICALLY_CONNECTED=USER_CONFIRMED
AC1_CANDIDATE_PORT=COM5
AC1_SERIAL_IDENTITY=PASS
AC1_SERIAL_MONITOR=PASS
AC1_INSTALLED_FIRMWARE_VERSION=NOT_VERIFIED
AC1_PLATFORMIO_CONFIGURATION=PASS
MQTT_CONNECTION=FAIL
REAL_ACK=DEFERRED
```

The user confirms SN1 is disconnected and AC1 is the only ESP32 physically connected. Windows PnP and `platformio device list --json-output` both identify COM5 as the sole USB serial port: Silicon Labs CP2102 USB-to-UART bridge, `VID_10C4:PID_EA60`, instance `USB\VID_10C4&PID_EA60\0001`. COM3/COM4 are Bluetooth links and COM7 is absent. A process-name/command-line inventory showed no other process explicitly naming COM5; the subsequent authorized open succeeded. The AC1-specific serial output confirms the device on COM5.

Earlier records assigned the `...\0001` USB instance to SN1 while both boards were connected, but later 2026-10-04 records explicitly say AC1 was identified and its production MQTT firmware restored on COM5. The previous conclusion that COM5 was currently SN1 was incorrect. The current physical connection statement takes precedence over that historical assignment.

Both AC1 PlatformIO projects now keep `board=esp32dev` and `monitor_speed=115200` without a fixed upload/monitor COM port. A port must be selected explicitly for each approved hardware session. The installed firmware version remains unknown: the `AC1_ACK_V2_AUTH_20261026` marker exists only in the newly compiled, unflashed image, and no startup/version banner appeared during the single passive observation. That absence does not disprove AC1 identity or identify the exact installed image.

The current and historically restored AC1 MQTT source initializes all six traffic LED outputs LOW, sets the buzzer OFF, and leaves GPIO18 servo unattached during startup. Opening a CP2102 serial port may toggle DTR/RTS and reset the ESP32; reset could change active outputs or move a powered servo under an unknown installed image. Before monitoring, the user confirmed the servo was unpowered or secured and lights/buzzer could safely reset, then explicitly authorized one passive COM5 session. The port was opened with DTR=0 and RTS=0, read for 18 seconds without transmitting data, and closed. No actuation-command log appeared. Afterward, the user directly reported **no unexpected change** in the gate, traffic lights, or buzzer. This observation addresses the serial-monitor safety check; it is not physical feedback for an ACK test.

Sanitized serial evidence: COM5 produced 235 bytes across seven lines, including repeated `AC1 MQTT connecting broker=<PRIVATE_LAN_IP>:1883` and `AC1 MQTT failed state=-2`. The PubSubClient header defines `-2` as `MQTT_CONNECT_FAILED`. No SN1 marker, startup/version banner, successful MQTT subscription, or ACK appeared. The Mosquitto service remained stopped with no port-1883 listener. AC1 identity is confirmed; MQTT connection is currently failing. The serial evidence does not establish the installed ACK protocol version.

## Broker diagnosis

- Mosquitto 2.1.2 is installed as the `mosquitto` Windows service. Its start mode is Automatic, but its observed state was Stopped. No process or TCP listener occupied port 1883. TCP connection attempts to both `127.0.0.1:1883` and `<PRIVATE_LAN_IP>:1883` failed. The reason the service stopped was not established by the available service/event evidence.
- The service registration is `<MOSQUITTO_INSTALL_PATH> run`. The installed Windows README says service mode reads `mosquitto.conf` from `%MOSQUITTO_DIR%`, which currently points to `<MOSQUITTO_INSTALL_PATH>`.
- That installed config requests `listener 1883 127.0.0.1` and `listener 1883 <PRIVATE_LAN_IP>`, plus `allow_anonymous true`. No active `password_file`, `acl_file`, or authentication plugin directive exists. These are configured addresses; **neither listener was active** during the audit. The separate repository `mosquitto-dev.conf` also allows anonymous access and was not used to restore production service.
- The PC's current Wi-Fi address is `<PRIVATE_LAN_IP>/28`, matching the historical broker address in earlier hardware logs. Backend `127.0.0.1:1883` is appropriate only when the broker runs on the same PC. AC1 is configured to use the current Wi-Fi address and attempted that connection during serial observation. The broker path currently fails because no listener is active; independent Wi-Fi/LAN packet reachability has not been measured.
- Inbound Windows Firewall currently has two broad Mosquitto program allow rules on the Public profile with any remote address, and a separate TCP/1883 rule scoped to the historical SN1 address `<PRIVATE_LAN_IP>`. Upstream port forwarding/public Internet exposure was not observable. Port 1883 was not opened by this audit.
- The backend MQTT client supports username/password, but the inspected runtime environment and repository-local environment files provide neither. It publishes `city/commands/AC1` at QoS 1 and subscribes to `city/acks/#` at QoS 1. Production command/ACK traffic must not be resumed on the current anonymous broker configuration.

## Device and firmware diagnosis

- COM5 is confirmed as AC1 by user physical identification and live AC1-specific serial output. The installed firmware version was not exposed in this bounded session. MQTT connection attempts failed with state `-2`; Wi-Fi connection is inferred from the firmware's MQTT guard but no current Wi-Fi IP was printed.
- The AC1 PlatformIO target is `esp32dev`, with `monitor_speed=115200` and no longer has a fixed upload/monitor port. Firmware source confirms node `AC1`, command topic `city/commands/AC1`, ACK topic `city/acks/AC1`, reconnect handling, a QoS 1 command subscription, and QoS 0 ACK publication. It emits `RECEIVED` after validation and a terminal `ACK` after issuing the output call. No non-actuating ACK test command or passive heartbeat/status publish exists.
- `firmware/ac1_mqtt/include/secrets.h` is absent. An ignored SN1 secrets file exists and holds a broker host of `<PRIVATE_LAN_IP>`, but has no MQTT username/password. Before this audit AC1 source could inherit that file and attempt an anonymous connection. That fallback has been removed. AC1 now requires its own ignored local Wi-Fi/broker configuration and MQTT credentials; missing or placeholder credentials prevent MQTT connection. Serial startup prints `ack_protocol_version=AC1_ACK_V2_AUTH_20261026` and configuration-presence flags without disclosing credentials.
- Current compile-check image: `firmware/ac1_mqtt/.pio/build/esp32dev/firmware.bin`, 803,984 bytes, SHA-256 `F9872E8C8DE3875DB4C41BCBF908647A938606B3AC93C37004EEF10299FA3A36`. The binary contains the protocol marker and placeholder AC1 username; it does not contain the historical LAN host. It must be rebuilt after the operator supplies AC1-specific secrets and before any approved upload.

## Repairs and verification

AC1 firmware gained authenticated MQTT connection support, stopped silently borrowing SN1's local secrets, refuses broker connection when AC1 credentials are absent, and prints a serial protocol version marker. The AC1 secrets example and firmware README now describe distinct broker identities and minimum AC1 topic permissions. No installed Mosquitto config, firewall rule, backend runtime secret, production SQLite data, or other device firmware was changed.

- AC1 MQTT and isolated bring-up PlatformIO compile: **PASS** for both `esp32dev` projects after removal of fixed COM ports; images were built without upload. The AC1 MQTT compile-check image retained the SHA-256 value shown above.
- Isolated ACK regression: **27 passed**; no broker, hardware, or production topic publication.
- Full backend regression: **198 passed**, one existing Starlette/httpx deprecation warning, using a fresh temp base under the ignored local `.venv`. An initial run had 17 setup errors because Windows denied access to pytest's default temp root; its remaining 181 tests passed. The rerun with the local temp base passed all 198.
- Passive checks: service/process/listener inspection, local TCP probes, Wi-Fi address, firewall rules, USB PnP inventory, ignored-file presence, firmware source/build inspection, historical records, and the one authorized COM5 serial observation. A real AC1 serial session was observed; no real MQTT ACK was observed.

## Exact remaining operator actions

1. **Broker:** provision separate authorized AC1 and backend MQTT identities through the existing private credential process. Replace the installed anonymous setting with authenticated service configuration and an ACL. Minimum AC1 rights are read `city/commands/AC1` and write `city/acks/AC1`; backend rights are write `city/commands/AC1` and read `city/acks/#`. Preserve other existing clients' required permissions when integrating the ACL. Restrict the firewall's Mosquitto rules to the intended private LAN and verify no router forwards 1883 to the public Internet. Start the service only after the secure configuration is valid; verify authenticated local and LAN connections and sanitized logs.
2. **Firmware:** fill the ignored AC1 `include/secrets.h` from `include/secrets.example.h` with operator-supplied Wi-Fi, current broker LAN host/port, and AC1 MQTT identity. Configure the backend MQTT identity privately. Rebuild the image, record its new hash, and verify COM5 remains the intended board/port. Obtain explicit approval before uploading. After an authorized upload, monitor serial at 115200 for the protocol marker, Wi-Fi address, MQTT connection, and successful `city/commands/AC1` subscription. Do not infer these states from the compile result.
3. **One controlled ACK test:** only after secure broker and passive device checks pass, obtain explicit operator approval for one supervised `TRAFFIC/ALL_RED` command with an emergency stop/power disconnect available. Use the one-shot command publisher path, avoiding the automatic retry executor. Generate one fresh `command_id` for node `AC1`; record the broker publish confirmation, AC1 `RECEIVED`, terminal ACK/failure on `city/acks/AC1`, backend command-bound validation and persisted projection, and elapsed latency. Do not manually or automatically resend on a missing ACK. Confirm any physical light state by direct observation; an ACK alone is not physical feedback. Do not command the gate for this test.

Historical Oct. 3–4 ACKs and physical observations belong to older firmware. They do not establish the installed version or validate this newly compiled image. The real ACK status remains deferred until a specifically authorized command produces a correlated ACK from the observed AC1. Broker authentication and service startup remain separate from the COM5 identity correction.
