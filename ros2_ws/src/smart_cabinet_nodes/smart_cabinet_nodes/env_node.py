from __future__ import annotations

import json
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String

from .common import json_text, now_iso


class SHT30Reader:
    def __init__(self, bus: int, address: int):
        import smbus2

        self.address = address
        self.bus = smbus2.SMBus(bus)

    @staticmethod
    def _crc8(data):
        crc = 0xFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = ((crc << 1) ^ 0x31) & 0xFF
                else:
                    crc = (crc << 1) & 0xFF
        return crc

    def read(self):
        self.bus.write_i2c_block_data(self.address, 0x2C, [0x06])
        time.sleep(0.02)
        data = self.bus.read_i2c_block_data(self.address, 0x00, 6)
        if self._crc8(data[0:2]) != data[2]:
            raise RuntimeError("temperature CRC check failed")
        if self._crc8(data[3:5]) != data[5]:
            raise RuntimeError("humidity CRC check failed")

        temp_raw = (data[0] << 8) | data[1]
        humid_raw = (data[3] << 8) | data[4]
        temperature = -45.0 + 175.0 * temp_raw / 65535.0
        humidity = 100.0 * humid_raw / 65535.0
        return round(temperature, 2), round(humidity, 2)

    def close(self):
        self.bus.close()


class EnvNode(Node):
    def __init__(self):
        super().__init__("env_node")
        self.declare_parameter("bus", 4)
        self.declare_parameter("address", 0x44)
        self.declare_parameter("period_sec", 1.0)
        self.declare_parameter("dry_run", False)

        self.publisher = self.create_publisher(String, "/env/state", 10)
        self.reader = None
        self.dry_run = bool(self.get_parameter("dry_run").value)

        if not self.dry_run:
            bus = int(self.get_parameter("bus").value)
            address = int(self.get_parameter("address").value)
            self.reader = SHT30Reader(bus, address)
            self.get_logger().info(f"SHT30 reader ready on i2c-{bus}, addr=0x{address:02X}")
        else:
            self.get_logger().info("dry_run enabled; publishing mock environment data")

        period = float(self.get_parameter("period_sec").value)
        self.timer = self.create_timer(period, self.publish_env)
        self.mock_temp = 25.0
        self.mock_humidity = 50.0

    def publish_env(self):
        try:
            if self.dry_run:
                self.mock_temp += 0.1
                if self.mock_temp > 26.0:
                    self.mock_temp = 25.0
                temperature = round(self.mock_temp, 2)
                humidity = round(self.mock_humidity, 2)
            else:
                temperature, humidity = self.reader.read()
            payload = {
                "temperature": temperature,
                "humidity": humidity,
                "valid": True,
                "timestamp": now_iso(),
            }
        except Exception as exc:
            self.get_logger().warning(f"SHT30 read failed: {exc}")
            payload = {
                "temperature": 0.0,
                "humidity": 0.0,
                "valid": False,
                "error": str(exc),
                "timestamp": now_iso(),
            }

        self.publisher.publish(String(data=json_text(payload)))

    def destroy_node(self):
        if self.reader is not None:
            self.reader.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = EnvNode()
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
