# Battery Box Sniffer

STM32F103C8T6 firmware and notes for reverse-engineering the charger/display three-wire interface and forwarding decoded status to ELF.

Important files:

- `ELF_READ_STM32_CHARGER_STATUS.md`
  - Handoff for writing the ELF-side GPIO reader.
- `stm32_three_wire_usb_cdc/src/main.c`
  - Current STM32 USB CDC debug + GPIO-to-ELF relay firmware.
- `stm32_three_wire_sniffer/src/main.c`
  - Earlier capture/sniffer firmware.

Current wiring memory:

```text
Charger S -> STM32 PA0
Charger V -> STM32 PA1
Charger G -> STM32 PA2

STM32 PB0  -> ELF_DATA
STM32 PB1  -> ELF_CLK
STM32 PB10 -> ELF_LATCH
STM32 GND  -> ELF GND
```

Local build dependency:

- `third_party/libopencm3/`

`third_party/libopencm3/` is ignored by Git. Fetch or place libopencm3 locally before building the STM32 firmware.

Generated build outputs and binary capture files are ignored by Git.
