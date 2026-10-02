# SN1 MQTT firmware

This is the production-bound SN1 transport project. It is intentionally separate from `firmware/sn1_bringup`, which remains the validated raw hardware diagnostic firmware.

The firmware publishes the existing CityResponder sensor contract at one-second cadence:

- `city/sensors/mq2` — `MQ2`, raw GPIO34 ADC, unit `raw`
- `city/sensors/dht22` — `DHT22`, temperature in °C, with humidity and `dht_ok` fields
- `city/sensors/ir_a` — `IR_A`, boolean `value=true` when the verified IR1 signal is LOW/blocked
- `city/sensors/ir_b` — `IR_B`, boolean `value=true` when the verified IR2 signal is LOW/blocked
- `city/sensors/button` — `BUTTON`, boolean `value=true` when the verified button signal is LOW/pressed

Every event contains `sensor_type`, `value`, UTC ISO-8601 `timestamp`, and `node_id=SN1`. Events are non-retained; the existing backend does not define a publisher QoS requirement, so PubSubClient publishes QoS 0. No MQ-2 thresholds or classifications are applied.

Copy `include/secrets.example.h` to ignored `include/secrets.h` and provide the local Wi-Fi SSID/password. Set the laptop LAN address in `CITYRESPONDER_MQTT_HOST`; the currently discovered active Wi-Fi address is `192.168.1.33`.
