"""
Shared PB0 presence reader for battery_node and standalone script.

STM32 PB0 single-wire protocol:
  start: low ~300ms, high 100ms
  slot1-4: low 100ms(empty) or 300ms(present), high 100ms
  stop: low 100ms, high 700ms
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


def _group_interval_frame(intervals: List[float]) -> Optional[Tuple[List[float], List[int]]]:
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

    candidates: List[List[float]] = []

    def search(start: int, token_index: int, groups: List[float]) -> None:
        if token_index == token_count:
            candidates.append(groups)
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
            search(end + 1, token_index + 1, groups + [acc])

    for start in range(len(intervals)):
        search(start, 0, [])

    if not candidates:
        return None

    best = min(candidates, key=frame_score)
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


def decode_rising_intervals_from_edges(edges: List[Tuple[float, int]]) -> Tuple[Optional[List[int]], List[float]]:
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
    grouped = _group_interval_frame(quiet_intervals)
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
        edges: List[Tuple[float, int]] = []
        last_level = int(self._line.get_value())

        while time.monotonic() < deadline:
            if self._interval_sec > 0.0:
                time.sleep(self._interval_sec)
            level = int(self._line.get_value())
            if level != last_level:
                edges.append((time.monotonic(), level))
                last_level = level
                if len(edges) >= 7:
                    slots, widths = decode_rising_intervals_from_edges(edges)
                    if slots is not None:
                        return slots, widths

        raise TimeoutError(f"no valid PB0 frame within {timeout:.1f}s")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def build_payload(
    slots: Optional[List[int]],
    pulse_widths_ms: Optional[List[float]],
    stable_frames: int,
    total_frames: int,
) -> Dict[str, Any]:
    """Build the standard JSON payload for /battery/state."""
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    online = slots is not None

    if online and slots is not None:
        mask_int = sum((1 << i) for i, s in enumerate(slots) if s)
        return {
            "module_online": True,
            "status_valid": True,
            "box_present": any(slots),
            "relay_on": any(slots),
            "slots": [bool(s) for s in slots],
            "battery_levels": [],
            "presence_mask": f"0x{mask_int:X}",
            "presence_mask_int": mask_int,
            "source": "stm32_pb0_presence_gpio",
            "pulse_widths_ms": pulse_widths_ms or [],
            "stable_frames": stable_frames,
            "total_frames": total_frames,
            "timestamp": now,
        }
    else:
        return {
            "module_online": False,
            "status_valid": False,
            "box_present": False,
            "relay_on": False,
            "slots": [],
            "battery_levels": [],
            "presence_mask": "0x0",
            "presence_mask_int": 0,
            "source": "stm32_pb0_presence_gpio",
            "pulse_widths_ms": [],
            "stable_frames": 0,
            "total_frames": total_frames,
            "error": "no STM32 PB0 signal detected",
            "timestamp": now,
        }
