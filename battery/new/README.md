# Battery Box Sniffer

STM32F103C8T6 firmware and notes for reverse-engineering the charger/display three-wire interface and forwarding decoded battery-slot presence to the main controller.

Important files:

- `PB0_ONEWIRE_PRESENCE_PROTOCOL.md`
  - Current handoff for reading STM32 PB0 from the main controller.
- `ELF_READ_STM32_CHARGER_STATUS.md`
  - Legacy handoff for the older PB0/PB1/PB10 three-wire GPIO reader.
- `stm32_three_wire_usb_cdc/src/main.c`
  - Current STM32 USB CDC debug + PB0 one-wire presence output firmware.
- `stm32_three_wire_sniffer/src/main.c`
  - Earlier capture/sniffer firmware.

Current wiring memory:

```text
Charger S -> STM32 PA0
Charger GND -> STM32 GND

STM32 PB0 -> main-controller GPIO input
STM32 GND -> main-controller GND
```

Current firmware holds unused PA1/PA2 down internally and only decodes the charger S line on PA0.

Current output rule:

```text
slot field == 0 -> empty
slot field != 0 -> battery present
```

This avoids depending on one fixed "present" code, because the charger can use different non-zero slot codes for full, two-bar, one-bar, and similar battery states.

Latest verified state:

```text
2026-07-03: slot2 + slot3 + slot4 present
stable presence mask = 0xE
PB0 output = slot1 empty, slot2 present, slot3 present, slot4 present
```

Local build dependency:

- `third_party/libopencm3/`

`third_party/libopencm3/` is ignored by Git. Fetch or place libopencm3 locally before building the STM32 firmware.

Generated build outputs and binary capture files are ignored by Git.
