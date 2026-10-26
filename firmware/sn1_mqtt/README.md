# SN1 MQTT firmware

This is the network-capable SN1 transport project. It is intentionally separate from `firmware/sn1_bringup`, which remains the installed no-network diagnostic firmware. The default Phase 4.2C policy sends DHT22, IR_A, and IR_B only; MQ2 and button telemetry are compile-time disabled.

## Implemented sensors

| Sensor | GPIO | MQTT topic | Reading |
| --- | ---: | --- | --- |
| MQ-2 analog output | GPIO34 / ADC1 | disabled | Deferred by operator request; not sampled or published by the default network build |
| DHT22 | GPIO4 | `city/sensors/dht22` | Temperature °C in `value`; relative humidity percent in `humidity` |
| IR1 | GPIO32 | `city/sensors/ir_a` | Boolean blocked state; LOW is configured as blocked |
| IR2 | GPIO33 | `city/sensors/ir_b` | Boolean blocked state; LOW is configured as blocked |
| Push button | GPIO27 | disabled | Backend button readings can create a dashboard alert; keep telemetry disabled during observation-only integration |

The hardware reference labels IR1 as the main route sensor and IR2 as the alternate route sensor. That is the documented design mapping; the physical installation and each module's output polarity still require direct verification. SN1 does not publish a graph edge ID, and no production road-to-IR mapping should be inferred from the sensor names.

## Telemetry contract

Each enabled message contains `sensor_type`, `value`, timezone-aware UTC `timestamp` with millisecond precision, `node_id=SN1`, `message_id`, `firmware_version=sn1-mqtt/1.2.0`, and `protocol_version=1.1`. Messages are non-retained QoS 0. The MQTT payload buffer is set to 512 bytes. IR_A and IR_B publish each second as the node heartbeat; DHT22 is polled and published once per successful two-second reading. Its timestamp refers to the read time. A failed DHT read is omitted, so the backend ages its last valid value to stale. Temperature must be within -40 to 80 °C and humidity within 0 to 100 percent before publication.

MQ2 handling remains in the source for later work, but `CITYRESPONDER_SN1_ENABLE_MQ2_TELEMETRY` defaults to `0`; no ADC sample is used or published in this phase. Do not enable it until MQ2 validation is authorized. DHT22 fusion breakpoints remain existing project policy and are not calibrated by this transport work.

IR values use the physically verified active-low polarity and publish at the one-second telemetry interval without firmware debounce. Existing routing code has a five-consecutive-sample IR debounce helper, but it is not wired as a production MQTT route-edge assignment. Dashboard readings remain raw sensor state. No physical road mapping is published.

## Local credentials and upload safety

Copy `include/secrets.example.h` to ignored `include/secrets.h` and set SN1-specific Wi-Fi and MQTT credentials. The network target refuses to compile if the ignored secrets header is missing, and its runtime gate rejects empty or placeholder values. A non-empty MQTT username and password are both required; anonymous connections are rejected. Never reuse AC1 credentials. Serial diagnostics never print credentials. Broker transport remains MQTT over `WiFiClient` without TLS, so use only a trusted private network until a TLS broker endpoint is available.

The broker and backend accept only the configured sensor node ID, and the backend subscribes to exact enabled sensor topics. The MQTT client retries Wi-Fi and broker connections and refuses to publish sensor measurements until UTC time is synchronized. No retained telemetry or command/actuator publish exists in this firmware. PlatformIO does not pin a COM port; identify SN1's port before monitoring or upload. The network image requires separate review and explicit upload approval; approval of the no-network bring-up image does not apply.
