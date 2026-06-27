from __future__ import annotations

import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String

from smart_cabinet_interfaces.srv import Beep, OpenLock, SetFan

from .common import json_text, now_iso


RELAY_ACTIVE = 0
RELAY_INACTIVE = 1


class ActiveLowLine:
    def __init__(self, chip_name: str, line_offset: int, name: str):
        import gpiod

        self.name = name
        self.chip = gpiod.Chip(chip_name)
        self.line = self.chip.get_line(line_offset)
        try:
            self.line.request(
                consumer=f"smart_cabinet_{name}",
                type=gpiod.LINE_REQ_DIR_OUT,
                default_vals=[RELAY_INACTIVE],
            )
        except TypeError:
            self.line.request(consumer=f"smart_cabinet_{name}", type=gpiod.LINE_REQ_DIR_OUT)
            self.off()

    def on(self):
        self.line.set_value(RELAY_ACTIVE)

    def off(self):
        self.line.set_value(RELAY_INACTIVE)

    def close(self):
        try:
            self.off()
        finally:
            self.line.release()
            self.chip.close()


class DigitalLine:
    def __init__(self, chip_name: str, line_offset: int, name: str, active_high: bool = True):
        import gpiod

        self.name = name
        self.active_value = 1 if active_high else 0
        self.inactive_value = 0 if active_high else 1
        self.chip = gpiod.Chip(chip_name)
        self.line = self.chip.get_line(line_offset)
        try:
            self.line.request(
                consumer=f"smart_cabinet_{name}",
                type=gpiod.LINE_REQ_DIR_OUT,
                default_vals=[self.inactive_value],
            )
        except TypeError:
            self.line.request(consumer=f"smart_cabinet_{name}", type=gpiod.LINE_REQ_DIR_OUT)
            self.off()

    def on(self):
        self.line.set_value(self.active_value)

    def off(self):
        self.line.set_value(self.inactive_value)

    def close(self):
        try:
            self.off()
        finally:
            self.line.release()
            self.chip.close()


class ActuatorNode(Node):
    def __init__(self):
        super().__init__("actuator_node")
        self.declare_parameter("chip", "gpiochip3")
        self.declare_parameter("lock_line", 3)
        self.declare_parameter("fan_line", 9)
        self.declare_parameter("buzzer_line", 4)
        self.declare_parameter("buzzer_active_high", True)
        self.declare_parameter("dry_run", False)
        self.declare_parameter("max_lock_pulse_sec", 0.5)
        self.declare_parameter("default_lock_pulse_sec", 0.3)

        self.dry_run = bool(self.get_parameter("dry_run").value)
        self.lock = None
        self.fan = None
        self.buzzer = None
        self.fan_on = False
        self.lock_busy = False
        self.buzzer_busy = False

        if not self.dry_run:
            chip = str(self.get_parameter("chip").value)
            self.lock = ActiveLowLine(chip, int(self.get_parameter("lock_line").value), "lock")
            self.fan = ActiveLowLine(chip, int(self.get_parameter("fan_line").value), "fan")
            self.buzzer = DigitalLine(
                chip,
                int(self.get_parameter("buzzer_line").value),
                "buzzer",
                active_high=bool(self.get_parameter("buzzer_active_high").value),
            )
            self.get_logger().info(f"actuator lines ready on {chip}")
        else:
            self.get_logger().info("dry_run enabled; actuator services will not touch GPIO")

        self.state_pub = self.create_publisher(String, "/actuator/state", 10)
        self.create_service(OpenLock, "/actuator/open_lock", self.open_lock)
        self.create_service(SetFan, "/actuator/set_fan", self.set_fan)
        self.create_service(Beep, "/actuator/beep", self.beep)
        self.create_timer(1.0, self.publish_state)

    def publish_state(self):
        self.state_pub.publish(
            String(
                data=json_text(
                    {
                        "lock_busy": self.lock_busy,
                        "fan_on": self.fan_on,
                        "buzzer_busy": self.buzzer_busy,
                        "timestamp": now_iso(),
                    }
                )
            )
        )

    def open_lock(self, request, response):
        max_pulse = float(self.get_parameter("max_lock_pulse_sec").value)
        default_pulse = float(self.get_parameter("default_lock_pulse_sec").value)
        requested = float(request.pulse_sec) if request.pulse_sec > 0 else default_pulse

        if requested > max_pulse:
            response.success = False
            response.actual_pulse_sec = 0.0
            response.message = f"refused: lock pulse {requested:.3f}s exceeds {max_pulse:.3f}s"
            return response

        self.lock_busy = True
        try:
            if self.lock is not None:
                self.lock.on()
            time.sleep(requested)
            if self.lock is not None:
                self.lock.off()
            response.success = True
            response.actual_pulse_sec = requested
            response.message = f"lock pulsed for {requested:.3f}s"
        except Exception as exc:
            response.success = False
            response.actual_pulse_sec = 0.0
            response.message = str(exc)
        finally:
            if self.lock is not None:
                self.lock.off()
            self.lock_busy = False
            self.publish_state()
        return response

    def set_fan(self, request, response):
        try:
            if self.fan is not None:
                if request.on:
                    self.fan.on()
                else:
                    self.fan.off()
            self.fan_on = bool(request.on)
            response.success = True
            response.message = f"fan {'on' if request.on else 'off'}: {request.reason}"
        except Exception as exc:
            response.success = False
            response.message = str(exc)
        self.publish_state()
        return response

    def beep(self, request, response):
        times = max(0, int(request.times))
        on_sec = min(max(float(request.on_sec), 0.02), 2.0)
        off_sec = min(max(float(request.off_sec), 0.02), 2.0)
        self.buzzer_busy = True
        try:
            for index in range(times):
                if self.buzzer is not None:
                    self.buzzer.on()
                time.sleep(on_sec)
                if self.buzzer is not None:
                    self.buzzer.off()
                if index != times - 1:
                    time.sleep(off_sec)
            response.success = True
            response.message = f"beeped {times} times"
        except Exception as exc:
            response.success = False
            response.message = str(exc)
        finally:
            if self.buzzer is not None:
                self.buzzer.off()
            self.buzzer_busy = False
            self.publish_state()
        return response

    def destroy_node(self):
        for line in (self.lock, self.fan, self.buzzer):
            if line is not None:
                line.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = ActuatorNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
