# SN1 hardware bring-up

This isolated PlatformIO project is for raw, local SN1 observation only. It does not use Wi-Fi, MQTT, CityResponder APIs, production thresholds, or AC1 pins.

Hardware mapping follows `docs/hardware/CityResponder_GPIO_Breadboard_Reference.md`:

- MQ-2 AO → GPIO34 through the final 20k/10k divider (20k upper / 10k lower)
- DHT22 DATA → GPIO4
- IR1 OUT → GPIO32
- IR2 OUT → GPIO33
- Push button → GPIO27 with `INPUT_PULLUP`

The serial monitor is configured for 115200 on COM5. The firmware prints raw MQ-2 ADC and raw digital states; it does not interpret IR polarity or classify sensor readings.
