"""
Shared STM32 battery-box presence readers for battery_node and scripts.

Current protocol:
  PB0 = DATA, PB1 = FRAME_ACTIVE.
  PB1 low means idle; ignore PB0.
  PB1 high means a frame is active. PB0 outputs slot1..slot4, each held
  for about 500 ms. ELF samples at 250/750/1250/1750 ms after PB1 rising.

The older PB0 single-wire and PB0/PB1 clocked readers remain below for
rollback/debug only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


SHORT_LOW_MS = (60.0, 180.0)
LONG_LOW_MS = (220.0, 420.0)
NORMAL_HIGH_MS = (50.0, 190.0)
IDLE_HIGH_MIN_MS = 450.0
PRESENT_THRESHOLD_MS = 200.0
SHORT_INTERVAL_MS = (130.0, 285.0)
LONG_INTERVAL_MS = (300.0, 560.0)
FRAME_GAP_INTERVAL_MS = (580.0, 1300.0)
INTERVAL_PRESENT_THRESHOLD_MS = 300.0
MAX_INTERVAL_GROUP_MS = 1150.0
NOISE_INTERVAL_MAX_MS = 50.0
MIN_POLL_CAPTURE_SEC = 2.6
MAX_FRAME_SCORE_MS = 90.0
TWOWIRE_SYNC = 0xA5
TWOWIRE_BITS = 32
TWOWIRE_FRAME_GAP_RESET_MS = 150.0
GATED_SAMPLE_OFFSETS_SEC = (0.25, 0.75, 1.25, 1.75)
GATED_FRAME_MIN_SEC = 1.5
GATED_FRAME_MAX_SEC = 2.5


@dataclass(frozen=True)
class LowPulse:
    low_ms: float
    high_after_ms: Optional[float]


def _in_range(value: Optional[float], bounds: Tuple[float, float]) -> bool:
    return value is not None and bounds[0] <= value <= bounds[1]


def _is_short_low(value: float) -> bool:
    return SHORT_LOW_MS[0] <= value <= SHORT_LOW_MS[1]


def _is_long_low(value: float) -> bool:
    return LONG_LOW_MS[0] <= value <= LONG_LOW_MS[1]


def _is_data_low(value: float) -> bool:
    return _is_short_low(value) or _is_long_low(value)


def _is_short_interval(value: float) -> bool:
    return SHORT_INTERVAL_MS[0] <= value <= SHORT_INTERVAL_MS[1]


def _is_long_interval(value: float) -> bool:
    return LONG_INTERVAL_MS[0] <= value <= LONG_INTERVAL_MS[1]


def _is_data_interval(value: float) -> bool:
    return _is_short_interval(value) or _is_long_interval(value)


def _is_gap_interval(value: float) -> bool:
    return FRAME_GAP_INTERVAL_MS[0] <= value <= FRAME_GAP_INTERVAL_MS[1]


def _edge_timestamp(event: Any) -> float:
    sec = getattr(event, "sec", None)
    nsec = getattr(event, "nsec", None)
    if sec is not None and nsec is not None:
        return float(sec) + float(nsec) / 1_000_000_000.0
    return time.monotonic()


def pulses_from_edges(edges: List[Tuple[float, int]]) -> List[LowPulse]:
    """Convert raw edges to low pulses.

    Edges are (timestamp_sec, edge_level_after_transition), where 0 means
    falling edge and 1 means rising edge.
    """
    pulses: List[LowPulse] = []
    i = 0
    while i < len(edges) - 1:
        if edges[i][1] != 0:
            i += 1
            continue

        rise_idx = None
        for j in range(i + 1, len(edges)):
            if edges[j][1] == 1:
                rise_idx = j
                break
            if edges[j][1] == 0:
                i = j
                break
        if rise_idx is None:
            if i < len(edges) and edges[i][1] == 0:
                i += 1
            continue

        low_ms = (edges[rise_idx][0] - edges[i][0]) * 1000.0
        high_after_ms = None
        for k in range(rise_idx + 1, len(edges)):
            if edges[k][1] == 0:
                high_after_ms = (edges[k][0] - edges[rise_idx][0]) * 1000.0
                break
        pulses.append(LowPulse(low_ms=low_ms, high_after_ms=high_after_ms))
        i = rise_idx + 1
    return pulses


def decode_pulses_from_edges(edges: List[Tuple[float, int]]) -> Tuple[Optional[List[int]], List[float]]:
    """Decode slot presence from raw edges.

    The decoder validates a whole PB0 frame instead of treating any 300ms low
    pulse as a start pulse. This is important because a present slot is also a
    300ms low pulse.
    """
    pulses = pulses_from_edges(edges)
    widths = [pulse.low_ms for pulse in pulses]
    if len(pulses) < 6:
        return decode_rising_intervals_from_edges(edges)

    for start_idx in range(0, len(pulses) - 5):
        start = pulses[start_idx]
        if not _is_long_low(start.low_ms):
            continue
        if not _in_range(start.high_after_ms, NORMAL_HIGH_MS):
            continue

        slots_and_stop = pulses[start_idx + 1:start_idx + 6]
        slot_pulses = slots_and_stop[:4]
        stop = slots_and_stop[4]

        if not all(_is_data_low(pulse.low_ms) for pulse in slot_pulses):
            continue
        if not all(_in_range(pulse.high_after_ms, NORMAL_HIGH_MS) for pulse in slot_pulses):
            continue
        if not _is_short_low(stop.low_ms):
            continue

        prev_idle = start_idx > 0 and (pulses[start_idx - 1].high_after_ms or 0.0) >= IDLE_HIGH_MIN_MS
        next_idle = stop.high_after_ms is not None and stop.high_after_ms >= IDLE_HIGH_MIN_MS
        if not (prev_idle or next_idle):
            continue

        slots = [1 if pulse.low_ms >= PRESENT_THRESHOLD_MS else 0 for pulse in slot_pulses]
        frame_widths = [pulse.low_ms for pulse in pulses[start_idx:start_idx + 6]]
        return slots, frame_widths

    interval_slots, intervals = decode_rising_intervals_from_edges(edges)
    if interval_slots is not None:
        return interval_slots, intervals

    return None, widths or intervals


def _group_interval_frame(
    intervals: List[float],
    prefer_latest: bool = False,
) -> Optional[Tuple[List[float], List[int]]]:
    """Find one logical PB0 frame from possibly fragmented rising intervals.

    Important: afternoon board validation showed the first logical interval is
    the frame start, not slot1. A valid frame is:
      start, slot1, slot2, slot3, slot4, gap
    Therefore slot states are decoded from groups[1:5].
    """
    token_count = 6  # start, slot1, slot2, slot3, slot4, gap

    def valid_token(index: int, value: float) -> bool:
        if index == 0:
            return _is_long_interval(value)
        if 1 <= index <= 4:
            return _is_data_interval(value)
        return _is_gap_interval(value)

    def frame_score(groups: List[float]) -> float:
        targets = [400.0]
        targets.extend(400.0 if value >= INTERVAL_PRESENT_THRESHOLD_MS else 200.0 for value in groups[1:5])
        targets.append(800.0)
        return sum(abs(value - target) for value, target in zip(groups, targets))

    candidates: List[Tuple[int, int, List[float]]] = []

    def search(
        frame_start: int,
        start: int,
        token_index: int,
        groups: List[float],
    ) -> None:
        if token_index == token_count:
            candidates.append((frame_start, start, groups))
            return
        if start >= len(intervals):
            return

        acc = 0.0
        # A logical 400 ms interval may be split into many small pieces by
        # microsecond-low separators, so group several adjacent intervals.
        for end in range(start, min(len(intervals), start + 24)):
            acc += intervals[end]
            if acc > MAX_INTERVAL_GROUP_MS:
                break
            if not valid_token(token_index, acc):
                continue
            search(frame_start, end + 1, token_index + 1, groups + [acc])

    for start in range(len(intervals)):
        search(start, start, 0, [])

    if not candidates:
        return None

    if prefer_latest:
        latest_start = max(start for start, _end, _groups in candidates)
        latest_candidates = [
            groups for start, _end, groups in candidates if start == latest_start
        ]
        best = min(latest_candidates, key=frame_score)
    else:
        best = min((groups for _start, _end, groups in candidates), key=frame_score)
    if frame_score(best) > MAX_FRAME_SCORE_MS:
        return None
    slots = [1 if value >= INTERVAL_PRESENT_THRESHOLD_MS else 0 for value in best[1:5]]
    return best, slots


def _quiet_intervals(intervals: List[float]) -> List[float]:
    """Merge noisy short intervals into the next meaningful interval."""
    quiet: List[float] = []
    acc = 0.0
    for value in intervals:
        acc += value
        if acc < NOISE_INTERVAL_MAX_MS:
            continue
        quiet.append(acc)
        acc = 0.0
    if acc and quiet:
        quiet[-1] += acc
    elif acc:
        quiet.append(acc)
    return quiet


def decode_rising_intervals_from_edges(
    edges: List[Tuple[float, int]],
    prefer_latest: bool = False,
) -> Tuple[Optional[List[int]], List[float]]:
    """Decode boards that expose PB0 as rising-edge interval timing.

    On the current ELF board, gpiochip3 line 7 has been observed to report
    mostly rising edges, while polling sees only microsecond-low separators.
    The rising-to-rising sequence observed in the afternoon validation is:

      start interval ~= 400ms
      slot intervals ~= 200ms(empty) or 400ms(present)
      frame gap ~= 600..1300ms on the current board

    Example for slot1+slot3 present:
      400, 400, 200, 400, 200, 800 -> slots [1, 0, 1, 0]
    """
    rising_times = [timestamp for timestamp, level in edges if level == 1]
    if len(rising_times) < 7:
        return None, []

    intervals = [
        (rising_times[i] - rising_times[i - 1]) * 1000.0
        for i in range(1, len(rising_times))
    ]
    if len(intervals) < 6:
        return None, intervals

    quiet_intervals = _quiet_intervals(intervals)
    grouped = _group_interval_frame(quiet_intervals, prefer_latest=prefer_latest)
    if grouped is not None:
        frame_intervals, slots = grouped
        return slots, frame_intervals

    return None, quiet_intervals or intervals


class Pb0PresenceReader:
    """GPIO edge-event reader for STM32 PB0 single-wire presence protocol."""

    def __init__(self, chip: str = "gpiochip3", line: int = 7):
        import gpiod
        self._chip = gpiod.Chip(chip)
        self._line = self._chip.get_line(line)
        self._line.request(consumer="pb0_reader", type=gpiod.LINE_REQ_EV_BOTH_EDGES)

    def close(self):
        try:
            self._line.release()
        finally:
            close = getattr(self._chip, "close", None)
            if close:
                close()

    def read_frame(self, timeout: float = 5.0) -> Tuple[List[int], List[float]]:
        """Read one PB0 frame. Returns (slot_states, pulse_widths_ms)."""
        import gpiod
        deadline = time.monotonic() + timeout
        edges: List[Tuple[float, int]] = []

        while time.monotonic() < deadline:
            if self._line.event_wait(sec=1):
                evs = self._line.event_read_multiple()
                for ev in evs:
                    ts = _edge_timestamp(ev)
                    etype = 0 if ev.type == gpiod.LineEvent.FALLING_EDGE else 1
                    edges.append((ts, etype))

            if len(edges) >= 7:
                slots, widths = decode_pulses_from_edges(edges)
                if slots is not None:
                    return slots, widths

        raise TimeoutError(f"no valid PB0 frame within {timeout:.1f}s")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class Pb0PollingPresenceReader:
    """Polling fallback for boards where edge events are unreliable.

    On the current ELF gpiochip3 line 7 path, user-space polling observes very
    short low separators and meaningful rising-to-rising intervals. Do not run
    the low-pulse decoder first here; it can lock onto compressed low pulses
    and falsely report all slots empty under full-system load.
    """

    def __init__(self, chip: str = "gpiochip3", line: int = 7, interval_sec: float = 0.0):
        import gpiod
        self._chip = gpiod.Chip(chip)
        self._line = self._chip.get_line(line)
        self._line.request(consumer="pb0_poll_reader", type=gpiod.LINE_REQ_DIR_IN)
        self._interval_sec = max(0.0, float(interval_sec))

    def close(self):
        try:
            self._line.release()
        finally:
            close = getattr(self._chip, "close", None)
            if close:
                close()

    def read_frame(self, timeout: float = 5.0) -> Tuple[List[int], List[float]]:
        deadline = time.monotonic() + timeout
        capture_until = time.monotonic() + min(MIN_POLL_CAPTURE_SEC, timeout)
        edges: List[Tuple[float, int]] = []
        last_level = int(self._line.get_value())
        last_result: Optional[Tuple[List[int], List[float]]] = None

        while time.monotonic() < deadline:
            if self._interval_sec > 0.0:
                time.sleep(self._interval_sec)
            level = int(self._line.get_value())
            if level != last_level:
                edges.append((time.monotonic(), level))
                last_level = level
                if len(edges) >= 7:
                    slots, widths = decode_rising_intervals_from_edges(
                        edges,
                        prefer_latest=False,
                    )
                    if slots is not None:
                        last_result = (slots, widths)
                        if time.monotonic() >= capture_until:
                            return last_result

            if last_result is not None and time.monotonic() >= capture_until:
                return last_result

        raise TimeoutError(f"no valid PB0 frame within {timeout:.1f}s")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _decode_twowire_frame(frame: int) -> Tuple[int, Dict[str, Any]]:
    sync = frame & 0xFF
    mask = (frame >> 8) & 0x0F
    mask_inv = (frame >> 12) & 0x0F
    seq = (frame >> 16) & 0xFF
    checksum = (frame >> 24) & 0xFF
    expected_checksum = (sync ^ mask ^ mask_inv ^ seq) & 0xFF
    valid = (
        sync == TWOWIRE_SYNC
        and mask_inv == ((~mask) & 0x0F)
        and checksum == expected_checksum
    )
    info = {
        "frame": f"0x{frame:08X}",
        "sync": f"0x{sync:02X}",
        "mask": f"0x{mask:X}",
        "mask_inv": f"0x{mask_inv:X}",
        "seq": seq,
        "checksum": f"0x{checksum:02X}",
        "expected_checksum": f"0x{expected_checksum:02X}",
        "valid": valid,
    }
    if not valid:
        raise ValueError(f"invalid two-wire frame: {info}")
    return mask, info


class TwoWirePresenceReader:
    """GPIO reader for STM32 PB0/PB1 synchronized presence protocol."""

    def __init__(
        self,
        chip: str = "gpiochip3",
        data_line: int = 7,
        clk_line: int = 18,
        data_chip: Optional[str] = None,
        clk_chip: Optional[str] = None,
        frame_gap_reset_ms: float = TWOWIRE_FRAME_GAP_RESET_MS,
    ):
        if int(data_line) == int(clk_line):
            if (data_chip or chip) == (clk_chip or chip):
                raise ValueError("data_line and clk_line must be different on the same chip")
        import gpiod

        self._gpiod = gpiod
        self._data_chip = gpiod.Chip(data_chip or chip)
        self._clk_chip = gpiod.Chip(clk_chip or chip)
        self._data = self._data_chip.get_line(int(data_line))
        self._clk = self._clk_chip.get_line(int(clk_line))
        self._data.request(consumer="battery_tw_data", type=gpiod.LINE_REQ_DIR_IN)
        self._clk.request(consumer="battery_tw_clk", type=gpiod.LINE_REQ_EV_RISING_EDGE)
        self._frame_gap_reset_ms = max(50.0, float(frame_gap_reset_ms))

    def close(self):
        for line in (self._clk, self._data):
            try:
                line.release()
            except Exception:
                pass
        for chip in (self._clk_chip, self._data_chip):
            close = getattr(chip, "close", None)
            if close:
                close()

    def read_frame(self, timeout: float = 5.0) -> Tuple[List[int], List[float]]:
        slots, intervals, _info = self.read_frame_with_info(timeout=timeout)
        return slots, intervals

    def read_frame_with_info(self, timeout: float = 5.0) -> Tuple[List[int], List[float], Dict[str, Any]]:
        deadline = time.monotonic() + timeout
        bits: List[int] = []
        intervals_ms: List[float] = []
        last_edge_ts: Optional[float] = None
        invalid_frames = 0
        total_edges = 0

        while time.monotonic() < deadline:
            remaining = max(0.001, deadline - time.monotonic())
            wait_sec = min(1.0, remaining)
            wait_whole = int(wait_sec)
            wait_nsec = int((wait_sec - wait_whole) * 1_000_000_000)
            if not self._clk.event_wait(sec=wait_whole, nsec=wait_nsec):
                continue

            for ev in self._clk.event_read_multiple():
                now = _edge_timestamp(ev)
                total_edges += 1
                if last_edge_ts is not None:
                    interval_ms = (now - last_edge_ts) * 1000.0
                    if interval_ms > self._frame_gap_reset_ms:
                        bits = []
                        intervals_ms = []
                    else:
                        intervals_ms.append(interval_ms)
                last_edge_ts = now

                bits.append(int(self._data.get_value()))
                if len(bits) < TWOWIRE_BITS:
                    continue

                frame = 0
                for index, bit in enumerate(bits[:TWOWIRE_BITS]):
                    frame |= (int(bit) & 0x01) << index
                try:
                    mask, info = _decode_twowire_frame(frame)
                except ValueError:
                    invalid_frames += 1
                    bits = []
                    intervals_ms = []
                    continue

                slots = [1 if (mask & (1 << i)) else 0 for i in range(4)]
                info["invalid_frames"] = invalid_frames
                info["total_edges"] = total_edges
                return slots, intervals_ms[-31:], info

        raise TimeoutError(
            f"no valid STM32 PB0/PB1 two-wire frame within {timeout:.1f}s "
            f"(edges={total_edges}, invalid_frames={invalid_frames})"
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class GatedPresenceReader:
    """GPIO reader for STM32 PB0/PB1 gated four-bit presence protocol."""

    def __init__(
        self,
        chip: str = "gpiochip3",
        data_line: int = 7,
        frame_line: int = 1,
        data_chip: Optional[str] = None,
        frame_chip: Optional[str] = None,
        sample_offsets_sec: Tuple[float, float, float, float] = GATED_SAMPLE_OFFSETS_SEC,
        frame_min_sec: float = GATED_FRAME_MIN_SEC,
        frame_max_sec: float = GATED_FRAME_MAX_SEC,
    ):
        if int(data_line) == int(frame_line):
            if (data_chip or chip) == (frame_chip or chip):
                raise ValueError("data_line and frame_line must be different on the same chip")
        import gpiod

        self._gpiod = gpiod
        self._data_chip = gpiod.Chip(data_chip or chip)
        self._frame_chip = gpiod.Chip(frame_chip or chip)
        self._data = self._data_chip.get_line(int(data_line))
        self._frame = self._frame_chip.get_line(int(frame_line))
        self._data.request(consumer="battery_gated_data", type=gpiod.LINE_REQ_DIR_IN)
        self._frame.request(consumer="battery_gated_frame", type=gpiod.LINE_REQ_EV_BOTH_EDGES)
        self._sample_offsets_sec = tuple(float(v) for v in sample_offsets_sec)
        self._frame_min_sec = float(frame_min_sec)
        self._frame_max_sec = float(frame_max_sec)

    def close(self):
        for line in (self._frame, self._data):
            try:
                line.release()
            except Exception:
                pass
        for chip in (self._frame_chip, self._data_chip):
            close = getattr(chip, "close", None)
            if close:
                close()

    def _event_wait(self, timeout_sec: float) -> bool:
        timeout_sec = max(0.001, float(timeout_sec))
        whole = int(timeout_sec)
        nsec = int((timeout_sec - whole) * 1_000_000_000)
        return bool(self._frame.event_wait(sec=whole, nsec=nsec))

    def _event_is_rising(self, event: Any) -> bool:
        return event.type == self._gpiod.LineEvent.RISING_EDGE

    def _event_is_falling(self, event: Any) -> bool:
        return event.type == self._gpiod.LineEvent.FALLING_EDGE

    def read_frame(self, timeout: float = 5.0) -> Tuple[List[int], List[float]]:
        slots, timings, _info = self.read_frame_with_info(timeout=timeout)
        return slots, timings

    def read_frame_with_info(self, timeout: float = 5.0) -> Tuple[List[int], List[float], Dict[str, Any]]:
        deadline = time.monotonic() + timeout
        discarded = 0
        edges = 0

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if not self._event_wait(remaining):
                continue

            for event in self._frame.event_read_multiple():
                edges += 1
                if not self._event_is_rising(event):
                    continue

                start_mono = time.monotonic()
                start_ts = _edge_timestamp(event)
                samples: List[int] = []
                sample_times_ms: List[float] = []

                for offset in self._sample_offsets_sec:
                    target = start_mono + offset
                    delay = target - time.monotonic()
                    if delay > 0:
                        time.sleep(delay)
                    if int(self._frame.get_value()) == 0:
                        discarded += 1
                        samples = []
                        break
                    samples.append(int(self._data.get_value()))
                    sample_times_ms.append(offset * 1000.0)

                if len(samples) != 4:
                    continue

                fall_ts = None
                fall_mono = None
                while time.monotonic() < deadline:
                    wait = min(1.0, max(0.001, deadline - time.monotonic()))
                    if not self._event_wait(wait):
                        continue
                    for end_event in self._frame.event_read_multiple():
                        edges += 1
                        if self._event_is_falling(end_event):
                            fall_ts = _edge_timestamp(end_event)
                            fall_mono = time.monotonic()
                            break
                    if fall_ts is not None:
                        break

                if fall_ts is None or fall_mono is None:
                    raise TimeoutError("frame did not end before timeout")

                duration_sec = fall_ts - start_ts
                if duration_sec <= 0.0 or duration_sec > 10.0:
                    duration_sec = fall_mono - start_mono
                if not (self._frame_min_sec <= duration_sec <= self._frame_max_sec):
                    discarded += 1
                    continue

                slots = [1 if bit else 0 for bit in samples]
                mask = sum((1 << i) for i, bit in enumerate(slots) if bit)
                info = {
                    "protocol": "pb0_pb1_gated_4bit",
                    "mask": f"0x{mask:X}",
                    "duration_ms": round(duration_sec * 1000.0, 1),
                    "sample_offsets_ms": sample_times_ms,
                    "edges": edges,
                    "discarded_frames": discarded,
                }
                return slots, sample_times_ms, info

        raise TimeoutError(
            f"no valid STM32 PB0/PB1 gated frame within {timeout:.1f}s "
            f"(edges={edges}, discarded_frames={discarded})"
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def build_payload(
    slots: Optional[List[int]],
    pulse_widths_ms: Optional[List[float]],
    stable_frames: int,
    total_frames: int,
    source: str = "stm32_pb0_pb1_gated_gpio",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the standard JSON payload for /battery/state."""
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    online = slots is not None
    extra = dict(extra or {})

    if online and slots is not None:
        mask_int = sum((1 << i) for i, s in enumerate(slots) if s)
        payload = {
            "module_online": True,
            "status_valid": True,
            "box_present": any(slots),
            "relay_on": any(slots),
            "slots": [bool(s) for s in slots],
            "battery_levels": [],
            "presence_mask": f"0x{mask_int:X}",
            "presence_mask_int": mask_int,
            "source": source,
            "pulse_widths_ms": pulse_widths_ms or [],
            "stable_frames": stable_frames,
            "total_frames": total_frames,
            "timestamp": now,
        }
        payload.update(extra)
        return payload
    else:
        payload = {
            "module_online": False,
            "status_valid": False,
            "box_present": False,
            "relay_on": False,
            "slots": [],
            "battery_levels": [],
            "presence_mask": "0x0",
            "presence_mask_int": 0,
            "source": source,
            "pulse_widths_ms": [],
            "stable_frames": 0,
            "total_frames": total_frames,
            "error": "no valid STM32 battery signal detected",
            "timestamp": now,
        }
        payload.update(extra)
        return payload
