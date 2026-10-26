# CityResponder Phase 4.1D — AC1 hardware end-to-end validation

**Date:** 2026-10-26
**Branch:** `integration/cityresponder-phase2-phase36`
**Device:** AC1 ESP32, COM5 / Silicon Labs CP2102
**Physical commands sent:** five authorized traffic commands: `ALL_RED`, primary `GREEN_CORRIDOR`, `ALL_RED`, standby `GREEN_CORRIDOR`, `ALL_RED`
**Firmware upload:** one authorized COM5 upload; PlatformIO and flash data verification passed
**Production Mosquitto service start:** secure apply passed

## Acceptance snapshot

```text
SN1_PHYSICALLY_CONNECTED=NO
AC1_PHYSICALLY_CONNECTED=USER_CONFIRMED
AC1_SERIAL_PORT=PASS
AC1_SERIAL_IDENTITY=PASS
AC1_SERIAL_MONITOR=PARTIAL
AC1_PLATFORMIO_CONFIGURATION=PASS
AC1_INSTALLED_FIRMWARE_VERSION=PARTIAL
AC1_FIRMWARE_BUILD=PASS
AC1_WIFI_CONFIGURATION=PASS
AC1_BUILT_PROTOCOL_MARKER=PASS
AC1_FIRMWARE_UPLOAD=PASS
MOSQUITTO_SERVICE=PASS
MQTT_AUTHENTICATION=PASS
MQTT_ACL=PASS_CONFIG_AND_ISOLATED_TEST
MQTT_TRANSPORT_TLS=NOT_CONFIGURED
MQTT_PRODUCTION_LISTENER=PASS
RETAINED_OR_QUEUED_COMMANDS=PASS_NONE_FOUND
PERSISTENT_CLIENT_SESSIONS=PASS_NONE_FOUND
AUTO_PUBLISHER_ON_RECONNECT=PASS_NONE_FOUND
AC1_WIFI=PASS
AC1_MQTT=PASS_CONNECTED
AC1_COMMAND_SUBSCRIPTION=NOT_VERIFIED
BACKEND_MQTT=PASS_CONNECTED
BACKEND_COMMAND_PUBLISH=PASS
BROKER_CONFIRMATION=PASS
COMMAND_PUBLISHED=PASS
BROKER_ACCEPTED=PASS
AC1_RECEIVED=PASS
AC1_EXECUTION_REPORTED=PASS
AC1_RECEIVED_ACK=PASS
AC1_TERMINAL_ACK=PASS
BACKEND_ACK_VALIDATION=PASS
ACK_LATENCY=PASS_3780_MS_COMMAND_TO_TERMINAL
REAL_ACK=PASS
MAIN_ROUTE_LIGHT=PASS
ALTERNATE_ROUTE_LIGHT=PASS
ALL_RED=PASS
TRAFFIC_TRANSITION=PASS_PRIMARY_AND_STANDBY_TO_ALL_RED
BUZZER_ON=NOT_VERIFIED
BUZZER_OFF=NOT_VERIFIED
TRAFFIC_LIGHTS=PARTIAL_STATIC_STATES_PASS_CYCLE_UNTESTED
BUZZER=NOT_VERIFIED
GATE_SERVO=DEFERRED
GATE_POSITION_FEEDBACK=DEFERRED
PHYSICAL_OBSERVATION=PASS_PRIMARY_STANDBY_ALL_RED
HUMAN_OBSERVED_OUTPUT=PASS_PRIMARY_STANDBY_ALL_RED
INDEPENDENT_PHYSICAL_FEEDBACK=NOT_VERIFIED
SAFE_DEFAULT_STATE=PASS_ALL_RED
PRODUCTION_SAFETY=PARTIAL
```

`AC1_SERIAL_IDENTITY=PASS` uses the operator connection statement, COM5 CP2102 enumeration, the earlier receive-only serial log identifying AC1, and the successful COM5 flash. The reviewed image containing `AC1_ACK_V2_AUTH_20261026` was uploaded with data verification and AC1 then established an authenticated broker connection from `<PRIVATE_LAN_IP>`. The post-upload receive-only serial capture had DTR/RTS low and no transmit, but was not decodable; the runtime marker and subscription message were not observed directly. The operator reported no unexpected physical output change.

## AC1 output and command matrix

Commands use the existing `PHYSICAL_ACTION` envelope on `city/commands/AC1`; correlated device messages are expected on `city/acks/AC1`. For a valid command, the firmware sends `RECEIVED`/`received`, then `ACK`/`execution_reported` after its output call. The backend must separately confirm broker publish, validate both ACK stages against `command_id`, and update its event/projection state. An ACK is not physical feedback.

| Feature / command | MQTT topic | Expected output / electrical behavior | ACK expectation | Physical observation / safety condition | Current result |
|---|---|---|---|---|---|
| Main route — `TRAFFIC/GREEN_CORRIDOR`, `corridor=PRIMARY` | `city/commands/AC1` | TL1/MAIN R14 LOW, Y13 LOW, G23 HIGH; TL2/STANDBY R25 HIGH, Y26 LOW, G27 LOW. LEDs active-high. | `RECEIVED`, then matching `ACK`/`execution_reported`; backend broker-confirmed publish and correlated state update. | Confirm MAIN green and STANDBY red; no other green. Do not press a documented optional button on GPIO27 during output checks. | PASS: real ACK and operator observation |
| Alternative route — `TRAFFIC/GREEN_CORRIDOR`, `corridor=STANDBY` | `city/commands/AC1` | TL1/MAIN R14 HIGH, Y13 LOW, G23 LOW; TL2/STANDBY R25 LOW, Y26 LOW, G27 HIGH. LEDs active-high. | `RECEIVED`, then matching `ACK`/`execution_reported`; backend broker-confirmed publish and correlated state update. | Confirm STANDBY green and MAIN red; verify GPIO27 is not shorted by a pressed button. | PASS: real ACK and operator observation |
| All red — `TRAFFIC/ALL_RED` | `city/commands/AC1` | Red GPIO14/25 HIGH; yellow/green GPIO13/23/26/27 LOW. LEDs active-high. | `RECEIVED`, then matching `ACK`/`execution_reported`; backend broker-confirmed publish and correlated state update. | Confirm both reds on and every yellow/green off. Preferred static traffic test state; requires explicit session authorization. | PASS: real ACK and operator observation |
| Normal cycle — `TRAFFIC/NORMAL_CYCLE` | `city/commands/AC1` | PRIMARY green 4 s, PRIMARY yellow 1 s, STANDBY green 4 s, STANDBY yellow 1 s; repeats until another traffic command. LEDs active-high. | `RECEIVED`, then matching `ACK`/`execution_reported`; backend broker-confirmed publish and correlated state update. | Observe a complete cycle; it runs continuously and needs a separately authorized follow-up state command to stop. Firmware has no all-red dwell between routes. | DEFERRED |
| Traffic off — `TRAFFIC/OFF` | `city/commands/AC1` | All six LED pins LOW. LEDs active-high. | `RECEIVED`, then matching `ACK`/`execution_reported`; backend broker-confirmed publish and correlated state update. | Leaves both routes dark; excluded from physical testing and must not be treated as safe. | DEFERRED |
| Buzzer — `BUZZER/ON` | `city/commands/AC1` | GPIO19 LOW. Firmware output is active-low; module trigger polarity is unverified. | `RECEIVED`, then matching `ACK`/`execution_reported`; backend broker-confirmed publish and correlated state update. | Observe audible output. It stays on until another buzzer action; test only in an explicitly authorized supervised session with power cutoff. | NOT_VERIFIED |
| Buzzer — `BUZZER/OFF` | `city/commands/AC1` | GPIO19 HIGH; cancels pulse mode. Firmware output is active-low; module polarity is unverified. | `RECEIVED`, then matching `ACK`/`execution_reported`; backend broker-confirmed publish and correlated state update. | Confirm silence; this is the documented stop action after an authorized ON observation. | NOT_VERIFIED |
| Buzzer — `BUZZER/PULSE_500_MS` | `city/commands/AC1` | GPIO19 toggles every 500 ms. | `RECEIVED`, then matching `ACK`/`execution_reported`; backend broker-confirmed publish and correlated state update. | Repeats indefinitely until another buzzer action; excluded from physical testing. | DEFERRED |
| Gate — `GATE/OPEN` / `GATE/CLOSE` | `city/commands/AC1` | PWM on GPIO18, target 120° / 30°. No position sensor. | `RECEIVED`, then matching `ACK`/`execution_reported` with target result; backend correlation. | Servo replacement, mechanical safety, and independent feedback are not verified. Requires separate motion authorization and is excluded from this phase's light/buzzer test. | DEFERRED |

At startup the six LEDs are driven LOW (dark), the active-low buzzer is set OFF/HIGH, and the servo remains unattached. The startup state is not all-red. No non-actuating status, heartbeat, or ACK-only command exists. The source's current AC1 output pins are unique, but the hardware reference also assigns GPIO27 to an optional pushbutton and TL2 green. The production AC1 firmware does not configure that button; before the standby-green test the operator confirmed it was disconnected or not pressed/shorting GPIO27.

## Broker and security recovery

- Mosquitto 2.1.2 is running as an Automatic LocalSystem service after the Administrator secure apply. The original stop cause remains unknown.
- The installed `<MOSQUITTO_CONFIG_FILE>` matches the reviewed staged config and disables anonymous access and persistence. The two broad Public-profile Mosquitto rules are disabled; the active rule permits TCP/1883 to `<PRIVATE_LAN_IP>` only from `<PRIVATE_LAN_IP>/28`. The service listens on that address and loopback. Upstream router forwarding cannot be inspected from this session.
- Separate random AC1/backend identities, a hashed Mosquitto password file, and topic ACL are installed under `<CITYRESPONDER_RUNTIME_PATH>`. The backend `.env` and ignored AC1 `secrets.h` are local protected files; no credential is stored in the repository. AC1 and backend are now connected to the broker.
- The current AC1 and backend MQTT clients use plain TCP, so this staged username/password setup does not encrypt credentials over the Wi-Fi link. The staged listener and firewall constrain access to loopback and the current `/28` LAN; transport TLS remains a separate improvement if this LAN is not trusted.
- An isolated loopback Mosquitto test using the staged production config and credentials passed: AC1 and backend authentication; AC1 command-topic read; backend ACK/sensor/vision subscriptions; anonymous denial; no message publish. A separate synthetic test verified allowed command/ACK flows and denial of out-of-scope read/publish access. These tests did not use the production port or send any production-topic message.
- The operator ran `<CITYRESPONDER_RUNTIME_PATH>` in Administrator PowerShell. It completed and preserved a timestamped preapply config backup. The backend was restarted afterward and now has one authenticated localhost MQTT connection. Its lifespan subscribes to sensor/vision/ACK topics and has no startup command publisher. Backend command publishes are QoS 1, non-retained, and fail immediately when disconnected rather than queueing locally. AC1 uses a clean MQTT session and publishes ACKs non-retained. Mosquitto persistence is false and no persistence database was found.

## Software verification

- Isolated MQTT ACL test: PASS. Authenticated test command/ACK flow succeeded; anonymous access and out-of-scope access were denied.
- Staged production config/credentials on a separate loopback broker: PASS. AC1 and backend authentication and their required subscriptions succeeded; anonymous access failed. The probe made no publish.
- Backend ACK suite: **27 passed**.
- Full backend suite: **198 passed**, with one existing Starlette/httpx deprecation warning.
- Elevated Mosquitto apply script PowerShell syntax parse and Administrator apply: PASS.
- AC1 PlatformIO `esp32dev` build with the local Wi-Fi and unique AC1 MQTT settings: PASS. Image: `firmware/ac1_mqtt/.pio/build/esp32dev/firmware.bin`, 804,112 bytes, SHA-256 `9ADC9CA46FA5E6223CAC6A4C3DD7F70CB5E6D66264A1C77873A77032BEAF051A`. The image contains the `AC1_ACK_V2_AUTH_20261026` marker and the configured value strings; no values were printed. The ignored `.pio` build tree was restricted to the current user, SYSTEM, and Administrators because it embeds device credentials. PlatformIO emitted an obsolete Core 6.1.19 warning but completed successfully.
- The operator approved one COM5 upload with the gate secured and lights/buzzer safe to reset. PlatformIO flash verification passed for the reviewed image, whose hash remained unchanged. The new runtime marker was not captured in readable post-upload serial output.
- Frontend tests were not run; no frontend implementation was changed for this phase.

## Remaining hardware sequence

1. Establish a readable firmware startup log if needed to directly observe the runtime protocol marker and subscription. The flash data verification and live authenticated AC1 broker connection are already established.
2. `ALL_RED`, primary green, standby green, and both returns to `ALL_RED` passed with real ACKs and operator observations. Normal cycling and traffic-off remain deferred because they leave a continuously changing or dark intersection; no further traffic command is needed for static-state validation. Buzzer and gate remain untested and require separate authorization and output-specific safety checks.

## Final status

```text
AC1_SOFTWARE_READY=YES
AC1_MQTT_READY=YES_CONNECTED
AC1_REAL_ACK_VERIFIED=YES_ALL_RED
AC1_TRAFFIC_LIGHTS_VERIFIED=PASS_STATIC_STATES_CYCLE_UNTESTED
AC1_BUZZER_VERIFIED=NO
AC1_GATE_VERIFIED=DEFERRED
AC1_DEMO_READY=NO
```

Five authorized traffic commands (`ALL_RED`, primary green, `ALL_RED`, standby green, `ALL_RED`) were sent and verified with real ACKs plus operator observations. No gate or buzzer command, database reset, commit, push, or merge occurred. The secure broker was started and one authorized AC1 firmware upload was completed.

## Final secure-apply script audit (2026-10-26)

- The elevated apply script was hardened to fail closed if the old Mosquitto wildcard firewall rules remain active, if any Public-profile TCP/1883 rule applicable to Mosquitto still allows any remote, or if the resulting scoped rule differs from the reviewed program/port/address scope. The earlier broad-rule matcher was corrected after a read-only test exposed a PowerShell parameter-set error; it now finds the two existing broad Mosquitto rules and distinguishes them from unrelated Windows rules.
- Read-only verification found both existing Mosquitto rules enabled on the Public profile (TCP and UDP, any local port, any remote). The script will disable these before creating the narrow TCP/1883 rule from `<PRIVATE_LAN_IP>/28` to host `<PRIVATE_LAN_IP>`.
- The last recorded AC1 Wi-Fi address is `<PRIVATE_LAN_IP>`, which is inside `<PRIVATE_LAN_IP>/28`. Windows currently reports `.3` only as a stale neighbor; this confirms the subnet math, not a current AC1 lease.
- Script preflight revalidation covers anonymous access off, password and ACL file directives, the two locally configured hashed identities, exact per-role topic permissions, no global ACL patterns, persistence off, and no Mosquitto database file. The broker is stopped, so no in-memory retained messages or queued sessions can carry over; persistence is disabled for the new run. Source review also confirmed the backend and AC1 use clean sessions/non-retained publishes.
- PowerShell AST parse and the read-only preflight passed. The firewall helper retest found the two broad Mosquitto rules and one applicable Public any-remote TCP/1883 rule before apply. Static scan found no MQTT publish call, Git mutation, or credential-output statement in the script.
- The script backs up the installed configuration before replacement and its failure path stops the attempted service run, restores the backup, removes its scoped rule, and re-enables the prior broad rules. The administrator-only apply has not been run; production Mosquitto remains stopped with no port-1883 listener. No configuration, firewall, service, firmware, or physical-action change was made by this final audit.
- A later elevated invocation stopped at the username preflight, before the apply block. A redacted diagnostic showed the AC1 username key matched but the backend key did not match the script's original strict dotenv syntax. The script now accepts case variation, whitespace around `=`, optional `export`, and quoted values while still requiring exactly one non-empty `MQTT_USERNAME`; it gives a backend-specific error without printing values. Preflight also requires non-empty AC1 and backend MQTT password keys. A `-PreflightOnly` switch now runs all read-only checks and reports what the apply would disable, then returns before changing system state. Its local simulation passed and reported two broad Mosquitto rules and one applicable public TCP/1883 rule, with `APPLY_ACTION=NOT_RUN`. The updated ProgramData copy matches the source by SHA-256 and parses cleanly; five dotenv parser cases passed. The elevated `.env` still needs this preflight check before an apply attempt. Service remains stopped, port 1883 has no listener, and the two broad firewall rules remain enabled.
- The operator then ran `-PreflightOnly` in Administrator PowerShell; it still rejected the backend username as missing, blank, or ambiguous. This remains a read-only preflight failure with no apply action. The updated failure path now emits only username/password assignment counts and MQTT-related key names (never values) to distinguish absent, blank, duplicate, or differently named settings on the next check. The exact contents of that elevated view remain unknown, so broker application remains deferred. Mosquitto is still stopped, port 1883 has no listener, and both broad firewall rules remain enabled.
- Follow-up: the latest elevated preflight reported zero backend MQTT username/password assignments and no MQTT/BROKER-related keys in its selected default file. Backend code also permits an absolute CITYRESPONDER_CONFIG_FILE override; the apply script now honors that override and reports the selected path without values. Updated script parses cleanly and its local read-only preflight passes. Administrator preflight must still pass before apply.
- The Administrator preflight selected the default runtime file and saw zero MQTT assignments, while this user session saw one username and one password assignment at that path. A private transfer file containing only those two existing assignments was staged under ProgramData with protected SYSTEM/Administrators/User ACLs; values were not printed. An administrator-only helper now backs up the elevated runtime file, writes the two assignments in place after verifying a protected backup, verifies them, and removes the transfer file. The helper parsed cleanly but has not been executed; Mosquitto remains stopped and the broad rules remain enabled.
- The first elevated backend-config repair stopped at input validation with no backup or runtime-file mutation; its earlier cleanup removed the protected transfer file. The transfer was staged again from the existing local credentials. The helper now reports which required input path is missing and retains the protected transfer file on failure. Syntax and static checks pass; Mosquitto is still stopped.

- The elevated helper later reached File.Replace and returned ArgumentException / Win32 code 87 before changing the target; zero target MQTT assignments were observed and the protected transfer was retained. The helper now uses a backed-up in-place write with rollback on failure. A separate dummy-file write and restore probe passed; the Administrator repair has not yet been retried.
- The Administrator repair then passed at 2026-10-26 18:59 local time: one backend MQTT username and password assignment, protected target ACL, verified private backup, and transfer file removed. The reported backup is <LOCAL_USER_PROFILE>\AppData\Local\CityResponder\config\.env.pre-phase41d-mqtt-20261026-185915-839cceba41754e33a21ef2d7821379ec.bak. Read-only follow-up found the backup present, transfer absent, Mosquitto Stopped, and no port-1883 listener. Elevated Mosquitto preflight and apply are next; no firmware or physical command was sent.

- The next Administrator preflight passed, including authentication, ACL, persistence, AC1 subnet, and broad-rule checks. Apply reached `VERIFY_SCOPED_RULE`, then failed only its `REMOTE_ADDRESS` string comparison and completed rollback with service stopped. Windows Firewall event 2097 recorded the created rule's remote scope as exactly `<PRIVATE_LAN_IP>/28`, local scope `<PRIVATE_LAN_IP>-<PRIVATE_LAN_IP>`, TCP/1883, Public profile, and Mosquitto executable. The validator now requires the live firewall COM rule's remote scope to equal the reviewed `/28`, while continuing the NetSecurity checks for the other properties. Read-only follow-up found Mosquitto stopped, zero port-1883 listeners, and no scoped rule. The repaired source and ProgramData scripts match by SHA-256 and parse with zero errors; another elevated apply is pending. No MQTT command, firmware upload, or physical action occurred.

- The following elevated attempt showed both NetSecurity and the firewall COM rule render the remote scope as `<PRIVATE_LAN_IP>/255.255.255.240`; the exact-CIDR string check rejected that equivalent representation and rollback completed. The validator now requires both firewall views to report exactly one of `<PRIVATE_LAN_IP>/28` or `<PRIVATE_LAN_IP>/255.255.255.240`; `Any` and broader subnets are rejected. Parser and four scope cases passed. The source and ProgramData copies match at SHA-256 `61843153F3DDDD205F4EB9CE7C9E85CE43B6C0C9781680D06B29B89D40804079`. Read-only rollback check found service stopped, no port-1883 listener, no scoped rule, and the two old broad rules re-enabled. Secure broker apply remains pending; no MQTT or physical command was sent.

- The operator's next Administrator apply passed at 2026-10-26 19:15 local time. It reported authentication and topic ACL enforced, persistence disabled with no database, service Running, listeners at `127.0.0.1` and `<PRIVATE_LAN_IP>`, both broad Mosquitto rules disabled, no Public any-remote TCP/1883 rule, and the private LAN rule enabled. Backup: `<CITYRESPONDER_RUNTIME_PATH>`. Independent live checks confirmed the listeners, enabled scoped rule with remote `<PRIVATE_LAN_IP>/255.255.255.240`, zero enabled broad Mosquitto rules, and installed config equal to staged config. Anonymous MQTT connection was rejected; the locally configured backend and staged AC1 identities each authenticated on loopback using clean sessions with no publishes. ACL correctness was previously tested on an isolated broker; no production ACL publish test was made. The backend process started before its runtime MQTT credentials were repaired and had no broker connection; it was restarted with the backend working directory. After startup, its `/health` endpoint returned healthy and the broker had one established localhost connection. AC1's last-known `.3` Wi-Fi neighbor is Reachable, but there is no AC1 connection to broker port 1883. COM5 still enumerates as the CP210x bridge. The built image remains present at the reviewed hash, but installed firmware identity is unknown and upload remains deferred. No production MQTT publish, firmware upload, or physical output command occurred; real ACK and traffic-light validation remain deferred.

- The operator then explicitly authorized one COM5 upload and passive observation, confirming the gate servo was unpowered or secured and the lights/buzzer safe to reset. COM5 CP210x enumeration and the existing image SHA-256 `9ADC9CA46FA5E6223CAC6A4C3DD7F70CB5E6D66264A1C77873A77032BEAF051A` were rechecked. A fresh PlatformIO `esp32dev` build retained exactly that hash. The single PlatformIO COM5 upload succeeded; the flash tool reported write/hash verification and RTS reset, and the image hash remained unchanged. A 20-second receive-only serial session at 115200 opened with DTR=0 and RTS=0 and sent no bytes. It yielded a large unreadable stream and no parsed marker/startup/MQTT lines, so serial firmware identification remains partial. The operator confirmed no unexpected gate, light, or buzzer behavior. A subsequent passive broker socket check showed two established connections: backend `127.0.0.1` and AC1 `<PRIVATE_LAN_IP>`. No production MQTT publish or physical command was sent. Real ACK and traffic-light validation still require separate supervised authorization.

- The operator separately authorized one supervised `TRAFFIC/ALL_RED` command, with no retry. A live precheck found AC1 and backend MQTT connections plus healthy backend. The backend `publish_actuator_command` service sent one QoS 1 non-retained `PHYSICAL_ACTION` envelope with `action_category=TRAFFIC`, `action_type=ALL_RED`, and command ID `cd484c8c-984a-4468-b62b-ea295c7a4238`. The broker confirmed publication. The running backend stored real AC1 ACK events from `city/acks/AC1` in chronological order: `RECEIVED/received`, then `ACK/execution_reported`; both matched AC1, the command ID, and action, with no simulated flag or ACK rejection. Command-event to terminal-ACK latency was 3,780 ms. The operator observed both red LEDs on, all yellow/green LEDs off, and no gate or buzzer change. `REAL_ACK=PASS` for this command and `ALL_RED=PASS` with physical observation. No other command or automatic retry was sent. Primary/standby green, buzzer, and gate remain untested.

- The operator next authorized exactly two supervised traffic commands, primary green followed by an all-red restore, with observation between them. Prechecks showed AC1 and backend connected. The backend sent one non-retained QoS 1 `TRAFFIC/GREEN_CORRIDOR` command with `corridor=PRIMARY`, ID `2e6ca21e-e629-4a9c-9082-10db5979fffc`; broker confirmation passed, followed by real AC1 `RECEIVED/received` and `ACK/execution_reported` events with no rejection or simulation flag. Command-to-terminal latency was 726 ms. The operator observed MAIN green with MAIN red/yellow off, STANDBY red with STANDBY yellow/green off, and no gate/buzzer change. Only then did the backend send the authorized `TRAFFIC/ALL_RED` restore, ID `609ba305-5f58-457c-90e4-95b6a5489aa4`; broker confirmation and both real ACK stages passed with 566 ms command-to-terminal latency. The operator observed both reds on, all yellow/green off, and no gate/buzzer change. No application retry or other command was sent. Primary-route lights and return to all red are physically verified; standby route, buzzer, and gate remain untested.

- The operator confirmed the optional GPIO27 button was disconnected or not pressed/shorting the TL2 green output and authorized exactly two supervised commands: standby green, then all-red restore after observation. The backend and AC1 were connected at precheck. The backend published one QoS 1 non-retained `TRAFFIC/GREEN_CORRIDOR` command with `corridor=STANDBY`, ID `3e114521-c71b-4d37-b70c-3dd8ad31f139`. Broker confirmation passed and the backend accepted matching real AC1 `RECEIVED/received` and `ACK/execution_reported` events without rejection or simulation flag; command-to-terminal latency was 397 ms. The operator observed MAIN red with its yellow/green off, STANDBY green with its red/yellow off, and no gate/buzzer change. Only then was one `TRAFFIC/ALL_RED` restore published, ID `10fe8b3c-7351-44f4-9e8e-5584cda82f47`; broker confirmation and both real ACK stages passed with 363 ms command-to-terminal latency. The operator confirmed both reds on, all yellow/green off, and no gate/buzzer change. No application retry or other command occurred. Static primary, standby, and all-red traffic states are physically verified; normal cycle, traffic off, buzzer, and gate remain untested.
- The elevated secure-broker apply reported failure and completed rollback. Read-only follow-up confirmed Mosquitto Stopped, zero port-1883 listeners, the installed config restored, both broad old rules enabled, and no scoped rule. Windows Firewall events show the old rules were disabled and a LAN-scoped rule was added then removed; no Mosquitto service start event or broker log followed. The event recorded the single local broker IP as <PRIVATE_LAN_IP>-<PRIVATE_LAN_IP>. The script now accepts that Windows-normalized single-IP form, rejects broader local ranges, and reports a sanitized failure stage/reason code if another apply fails. Updated copies match; PowerShell parse and focused address checks passed. Broker verification and real ACK remain deferred.
