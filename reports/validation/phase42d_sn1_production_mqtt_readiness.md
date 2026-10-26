# CityResponder Phase 4.2D — SN1 production MQTT readiness

Date: 2026-10-26 (Asia/Singapore)

## Scope and current gate

- Work remains isolated in `<LOCAL_USER_PROFILE>/OneDrive/Documents/ChatGPT/CityResponder-sn1` (`feature/sn1-hardware-validation`) and `<LOCAL_USER_PROFILE>/OneDrive/Documents/ChatGPT/CityResponder-sn1-main-integration` (`codex/sn1-main-integration-preview`, based on `origin/main` `492b233`). Both trees contain earlier uncommitted work and were preserved. Nothing was committed, pushed, merged, reset, or cleaned.
- AC1 servo testing is still active per the Phase 4.2D user decision. No shared broker/backend change, production restart/reload, COM access, firmware upload, production database access, or real AC1 command was performed.
- Production Mosquitto configuration and ACL were read only. The password file contents were not read. No production MQTT connection was made.
- SN1 remains on `sn1-bringup/1.1.0`; no deployment-intended network image was built or uploaded because `firmware/sn1_mqtt/include/secrets.h` is absent. The Phase 4.2C image used ephemeral test credentials and must not be reused.

## Production broker audit

- Windows service: `mosquitto`, running, automatic start. Installed broker version: **2.1.2**. The matching `mosquitto_signal.exe` helper is present.
- Config: `<MOSQUITTO_CONFIG_FILE>`. It has anonymous access disabled, password and ACL files configured, and listeners on `127.0.0.1:1883` and `<PRIVATE_LAN_IP>:1883`.
- ACL: `<MOSQUITTO_ACL_FILE>`. Existing redacted-user rules include AC1 command/ACK permissions and backend sensor/vision permissions. There is no SN1 publisher ACL block. Existing rules were not changed.
- Password file: `<MOSQUITTO_PASSWORD_FILE>`. Its contents and whether a username is already present were not inspected. A preflight must check for the dedicated username without displaying password hashes before any authorized change.
- There is no TLS listener. The SN1 firmware currently uses plain `WiFiClient` MQTT. MQTT username/password are not encrypted in transit by this configuration, so a trusted isolated network or a separately planned TLS endpoint is required before safe device deployment on an untrusted/shared network.

## Exact proposed ACL change — not applied

Append this new user block to the ACL file. Leave every existing line unchanged:

```diff
user sn1_sensor_pub
topic write city/sensors/dht22
topic write city/sensors/ir_a
topic write city/sensors/ir_b
```

This grants SN1 write access only to its three active sensor topics. It gives no read access and no access to wildcard topics, MQ2, button, vision, ACK, or AC1 commands. The backend already has sensor read access; no new backend-reader ACL is required. The implementation subscribes to exactly `city/sensors/dht22`, `city/sensors/ir_a`, and `city/sensors/ir_b` for this SN1 path, while established vision, road, and ACK subscriptions remain separate.

### Firmware publisher coverage check

The firmware source was checked in both worktrees; matching SHA-256 values are `src/main.cpp` = `3F610CE40825B5E2CCB7E38A03F56C466086E65D2DE49E9648C1942F4B8FF7CD` and `platformio.ini` = `B1B58484393B95EF4DF5B80386C576EEE3E9890928529D7E29041D479BB18B0F`. Every active `publishSensorEvent` call uses one of the three ACL topics above: `city/sensors/dht22`, `city/sensors/ir_a`, or `city/sensors/ir_b`. `publishJson` is the single MQTT publish helper and sets retain to `false`. The PlatformIO `esp32dev` environment explicitly compiles with `CITYRESPONDER_SN1_ENABLE_MQ2_TELEMETRY=0` and `CITYRESPONDER_SN1_ENABLE_BUTTON_TELEMETRY=0`; the only MQ2 and button publish calls are inside those disabled compile-time branches. There are no status-topic or command-topic publishers in the current firmware. Therefore, the proposed exact topic permissions fully cover the current default firmware publisher behavior without wildcard access. If either disabled flag is ever changed, stop and review the ACL and backend safety path before building or uploading.

## Credential provisioning and isolated validation

1. At an approved maintenance point, check whether `sn1_sensor_pub` already exists in the password file without printing file lines or hashes. If it exists, do not overwrite/reset it; stop and choose a unique SN1-only principal.
2. Copy the ACL and password files to timestamped, access-restricted backups. Record SHA-256 hashes and preserve their NTFS permissions. Stage edits on copies; never use `mosquitto_passwd -c` against the existing password file because `-c` creates/replaces a file.
3. Add a high-entropy SN1-only password interactively with `mosquitto_passwd.exe` against the staged password file. Do not put the password in command arguments, shell history, logs, this report, or chat. Keep it in the approved local secret store.
4. Validate the staged ACL/password pair with a separate loopback Mosquitto broker on an ephemeral port. The existing automated test already exercises the exact three write grants and confirms denial for MQ2, button, and `city/commands/AC1`.
5. After explicit approval, replace only the production ACL and password files as one coordinated staged update, preserving file permissions. Verify both files are in place before issuing one targeted `config-reload` signal to the verified Mosquitto service PID. Do not use a service restart for these file-only changes.
6. Verify the reload result in broker logs and by read-only inspection of the new ACL block. Do not publish synthetic production sensor values. Later telemetry verification must use real SN1 DHT22/IR readings after separately approved firmware deployment.

Rollback: restore both timestamped files and their original NTFS permissions, verify their recorded hashes, then issue the same targeted `config-reload`. If the SN1 account was newly created, restoring the original password-file backup removes it. Do not remove or rewrite any existing account. No backup was taken because production changes are not authorized.

## Reload and AC1 session impact

- Mosquitto 2.1.2 supports a Windows `config-reload` signal through `mosquitto_signal.exe`; changing only `acl_file` and `password_file` does not require a service restart. The official Mosquitto documentation says ACLs reload on a reload signal and existing subscriptions are affected afterward. Password data also reloads, and already-connected clients are not disconnected by that password-file reload. Sources: [Mosquitto configuration manual](https://mosquitto.org/man/mosquitto-conf-5.html) and [mosquitto_signal manual](https://mosquitto.org/man/mosquitto_signal-1.html).
- The proposed block is additive and leaves AC1 ACL lines unchanged, so AC1 sessions are expected to remain connected with their existing rights. Because ACL reload re-evaluates subscriptions, a brief delivery delay or unexpected subscription change cannot be ruled out. Apply only at an AC1-safe maintenance point; stop and restore the backups if broker logs, AC1 connectivity, or ACK behavior changes unexpectedly.
- No approval is being requested while AC1 servo testing remains active.

## Backend settings and integration dependency

The backend reads runtime configuration outside the repository, normally `%LOCALAPPDATA%/CityResponder/config/.env` (or the explicit `CITYRESPONDER_CONFIG_FILE` override). That file and its secrets were not read or changed. If review finds a setting missing, merge only the needed keys; do not replace the runtime file or change the existing backend reader credentials.

| Setting | Required value/handling |
| --- | --- |
| `MQTT_HOST`, `MQTT_PORT` | Keep the existing backend broker endpoint and port; service listens on 1883. Do not substitute the SN1 publisher identity for the backend reader identity. |
| `MQTT_USERNAME`, `MQTT_PASSWORD` | Preserve the existing backend reader account and secret. Broker ACL already grants sensor reads. |
| `SENSOR_MQTT_TOPIC_PREFIX` | `city/sensors` |
| `SENSOR_ALLOWED_NODE_IDS` | Include `SN1` while preserving any other currently configured IDs. |
| `SENSOR_DHT22_STALE_AFTER_SECONDS` | 3 seconds for the 2-second DHT publish interval. |
| `SENSOR_DIGITAL_STALE_AFTER_SECONDS` | 2 seconds for 1-second IR updates. |
| `SENSOR_MQ2_STALE_AFTER_SECONDS` | Leave unchanged; MQ2 remains deferred and disabled. |

The source changes have been tested in both worktrees. Loading them into the active FastAPI process requires integrating the reviewed source and a controlled FastAPI restart; that is deferred while AC1 testing is active and requires separate approval. No production runtime configuration was changed.

## Local SN1 secret provisioning and firmware status

- `firmware/sn1_mqtt/include/secrets.example.h` documents the required local-only settings: Wi-Fi SSID/password, broker host/port, and the dedicated SN1 MQTT username/password. The real `include/secrets.h` is ignored by Git and currently absent.
- Do not send secrets in chat. Use the approved local secret store to create the ignored header, verify with `git check-ignore` without printing its contents, and never reuse AC1 credentials. The embedded password can be extracted from device firmware; use a unique, revocable SN1 password.
- The current firmware transport is unencrypted MQTT. Secret-at-rest handling does not encrypt network traffic. Do not deploy over an untrusted/shared network. A TLS broker listener plus TLS-capable firmware would be a separate reviewed security change; neither exists now.
- Phase 4.2C recorded a successful `esp32dev` network compile only with ephemeral test credentials, plus a successful no-network bring-up build. Its temporary image and hash are not a production artifact. No new production image hash exists. Build the actual deployment image only after the real local secrets and transport/network decision are ready, then obtain separate upload approval.

## Deployment checklist — pending; do not execute while AC1 testing is active

- [ ] Add the reviewed additive SN1-only ACL block; keep all current AC1 rules unchanged.
- [ ] Provision dedicated SN1 MQTT credentials without exposing them in source control, logs, or chat.
- [ ] Provision SN1-only Wi-Fi credentials locally and confirm a restricted trusted WLAN or approved TLS transport.
- [ ] Take permission-preserving production backups and verify the rollback files and hashes.
- [ ] After the authorized reload, verify AC1 broker connection and ACK behavior before proceeding.
- [ ] Build a fresh deployment image from the reviewed source using the real local credentials, then record its SHA-256. Do not reuse the test-only image.
- [ ] Obtain separate explicit approval before uploading to re-identified COM6.
- [ ] After authorized deployment, validate real SN1 MQTT → backend → sensor state → dashboard for DHT22, IR_A, and IR_B; keep button disabled and MQ2 deferred.

The post-reload AC1 check must confirm its broker connection and ACK behavior before SN1 validation continues.

## Verification and isolated test repair

- SN1 backend full suite: **209 passed**.
- Integration-preview backend full suite: **236 passed**.
- Both suites used `CITYRESPONDER_TEST_DATA_ROOT` pointing read-only to the existing development artifacts under `nexus/CityResponder`; pytest used a unique temporary SQLite state directory, and MQTT integration tests used an isolated loopback broker. No production database or broker was used.
- The rerun exposed a race in the E2E test: it polled an in-memory SQLite database while the Paho callback was still writing. The test now waits for all three ingestion callbacks to finish before querying the database. Both worktrees pass after this change.
- Frontend `npm test`, `npm run typecheck`, and `npm run build`: **PASS** in both worktrees.
- Firmware build evidence remains the Phase 4.2C result; no deployment build was attempted without real secrets.
- `git diff --check` is required after this report update.

## Maintenance review package (no approval requested during AC1 servo testing)

1. **Files/settings to modify:** append only the SN1 block to `<MOSQUITTO_ACL_FILE>`; add one dedicated account to `<MOSQUITTO_PASSWORD_FILE>`; later provision ignored `firmware/sn1_mqtt/include/secrets.h`; review, but do not replace, backend runtime settings outside the repository.
2. **ACL entries:** the exact four-line diff above; no wildcard, read, button, MQ2, vision, ACK, or AC1 command permissions.
3. **AC1 impact:** no broker restart is needed; targeted config reload is expected to keep connected clients up, and AC1 grants remain unchanged. Existing subscriptions are re-evaluated. Any unexpected AC1 impact means stop and restore both backups.
4. **Backup/rollback:** procedure is prepared above; backups have not been taken and no production change has been applied.
5. **Security verification:** exact ACL passed an isolated authenticated Mosquitto test, including denied writes to MQ2/button/AC1 command topics. Production password presence is unverified, production auth was not tested, and the current listener has no TLS.
6. **Operator actions:** finish AC1 servo testing; approve a coordinated ACL/password-file change and targeted reload; provide SN1-only Wi-Fi and broker secrets through the approved local secret store (not chat); decide on TLS or a trusted isolated WLAN; later review the real image hash and give separate upload approval. A shared FastAPI restart also needs a separate AC1-safe approval.

## Final status

```text
SN1_SOFTWARE=PASS (READY_FOR_DEPLOYMENT baseline; production gates remain)
SN1_ISOLATED_MQTT=PASS
SN1_PRODUCTION_ACL=BLOCKED (reviewed diff ready; not applied; AC1 servo testing active)
SN1_DEDICATED_CREDENTIALS=NOT_PROVISIONED
SN1_NETWORK_IMAGE=NOT_READY (real secrets absent; fresh deployment build and SHA-256 pending)
SN1_DEPLOYMENT_FIRMWARE=BLOCKED (real secrets absent; no production image built)
SN1_REAL_WIFI=NOT_VERIFIED
SN1_REAL_MQTT=NOT_VERIFIED
SN1_BACKEND_INGESTION=PASS (isolated loopback broker and temporary SQLite only)
SN1_LIVE_DASHBOARD=NOT_VERIFIED (UI/API contract and builds pass; no real MQTT values)
SN1_DASHBOARD_LIVE=NOT_VERIFIED (UI/API contract and builds pass; no real MQTT values)
DHT22_LIVE=NOT_VERIFIED over MQTT (serial reading verified in Phase 4.2B)
IR_A_LIVE=NOT_VERIFIED over MQTT (physical polarity verified in Phase 4.2B)
IR_B_LIVE=NOT_VERIFIED over MQTT (physical polarity verified in Phase 4.2B)
BUTTON=DISABLED
MQ2=DEFERRED_BY_USER
AC1=DO_NOT_DISTURB
AC1_PRESERVED=PASS (no COM5, broker, runtime, command, or database mutation)
PRODUCTION_DATABASE_PRESERVED=PASS (tests used temporary SQLite only)
FULL_BACKEND_TESTS=PASS (209 SN1; 236 integration preview)
FRONTEND_TESTS=PASS (tests, typecheck, and production builds in both worktrees)
REMAINING_BLOCKERS=AC1 servo test completion; explicit production ACL approval; SN1-only local secrets; TLS or trusted-network decision; separate firmware-upload approval; separate FastAPI restart approval
```

## Phase 4.2D changed files

- SN1 worktree: `backend/tests/test_sn1_sensor_integration.py`; this report.
- Integration preview: `backend/tests/test_sn1_sensor_integration.py`.
- Earlier Phase 4.2C work in both worktrees remains preserved and uncommitted.
