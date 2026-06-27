# 2026-06-27 Hardware Wiring Memory

## Latest Wiring

SHT30:

- ELF 2 `SDA.1` -> SHT30 `SDA`.
- ELF 2 `SCL.1` -> SHT30 `SCL`.
- Linux bus: `/dev/i2c-4`.
- Address: `0x44`.

PN532:

- ELF 2 `SDA.0` -> PN532 `SDA`.
- ELF 2 `SCL.0` -> PN532 `SCL`.
- Expected Linux bus: `/dev/i2c-7`.
- Address: `0x24`.

Fan:

- `GPIO.28`, official meaning `GPIO2_D3--GPIO3_B1`.
- Linux mapping: `gpiochip3 line 9`.
- Connected to relay 2.
- Relay controls fan.
- Active-low relay behavior has been used in code.

Door lock:

- `GPIO.25`, official meaning `GPIO2_C1--GPIO3_A3`.
- Linux mapping: `gpiochip3 line 3`.
- Connected to relay 3.
- Relay controls lock.
- Single energizing time must be `<= 0.5s`.

Buzzer:

- `GPIO.23`, official meaning `GPIO2_C5--GPIO3_A4`.
- Linux mapping: `gpiochip3 line 4`.
- Active-high: `1` sounds, `0` silent.

Battery charging module:

- Not connected yet.

## Useful Checks

```bash
i2cdetect -y 4
i2cdetect -y 7
gpioinfo gpiochip3
```

Expected:

- SHT30: `0x44` on bus 4.
- PN532: `0x24` on bus 7 when healthy.

## Cautions

- Do not use `RPi.GPIO` on RK3588.
- Prefer `gpiod`/`gpioinfo`/`gpioset` or Python `gpiod`.
- Door lock pulse must never exceed `0.5s`.
- PN532 currently has no software-controlled reset line. If it stops ACKing on I2C, software cannot reliably recover it.
