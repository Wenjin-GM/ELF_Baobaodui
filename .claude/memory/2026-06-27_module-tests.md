# 2026-06-27 Module Tests Memory

## PN532 NFC

Previously successful command:

```bash
cd ~/smart_tool_cabinet/PN532
python3 tests/test_campus_card_uid.py --bus 7 --timeout 30
```

Earlier successful UID:

```text
UID hex: 19517D20
UID hex reversed: 207D5119
UID decimal: 424770848
UID decimal LE: 545083673
UID length: 4 bytes
```

Current after restoration:

- User reported original test still failed to detect card after recent experiments.
- Driver has now been restored to original-style code.
- User should clear root-owned pycache and power-cycle PN532 before retesting.

## SHT30

User reported `sht30_test/` worked normally.

Expected:

- Bus: `/dev/i2c-4`.
- Address: `0x44`.
- Test should print valid temperature/humidity.

## USB Face Auth

Command used:

```bash
cd ~/smart_tool_cabinet/USB/face_auth
python3 check_usb_face_confidence.py /tmp/usb_camera_test
```

Observed:

- InsightFace models loaded.
- Face DB loaded: 2 persons, 27 feature records.
- Results for `usb_camera_01.jpg` to `usb_camera_05.jpg`: `no_face`.
- CPUExecutionProvider used; CUDA unavailable warning is acceptable.

Current issue:

- `face_node` fails with matplotlib import error:
  `cannot import name 'docstring' from 'matplotlib'`.

## Camera

Probe command:

```bash
cd ~/smart_tool_cabinet
python3 vision/camera/board_capture_two_photos.py --probe
```

Observed:

- `/dev/video11`: exists, opened, readable, 1920x1080.
- `/dev/video12`: exists/opened but not readable.
- `/dev/video0`: exists but not opened.
- `/dev/video21` exists and is used by face node by default.

## GPIO

Fan and door-lock test was requested:

- Fan turns 5 seconds.
- Door lock toggles 3 times.
- Door lock single energizing time must not exceed `0.5s`.

Current mapping:

- Fan: `gpiochip3 line 9`, active-low.
- Door lock: `gpiochip3 line 3`, active-low.
- Buzzer: `gpiochip3 line 4`, active-high.

## ROS Board Check

Board ROS environment passed:

- ROS Humble.
- `rclpy`, `std_msgs`, `sensor_msgs`, `launch` OK.
- `cv_bridge` OK.
- NumPy `1.26.4`.
- Demo talker/listener pub/sub OK.

Hardware permissions after udev/group setup:

- User `elf` in `i2c`, `gpio`, `video`.
- `/dev/i2c-4`, `/dev/i2c-7` group `i2c`.
- `/dev/gpiochip3` group `gpio`.
