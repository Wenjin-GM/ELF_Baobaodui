from __future__ import annotations

import argparse

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node

from smart_cabinet_interfaces.action import ReadNfcCard


class NfcActionClient(Node):
    def __init__(self):
        super().__init__("nfc_action_client")
        self.client = ActionClient(self, ReadNfcCard, "/auth/read_nfc_card")

    def run(self, timeout_sec: float) -> int:
        if not self.client.wait_for_server(timeout_sec=3.0):
            print("[FAIL] /auth/read_nfc_card action server not ready")
            return 1

        goal = ReadNfcCard.Goal()
        goal.timeout_sec = float(timeout_sec)
        future = self.client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future)
        goal_handle = future.result()
        if goal_handle is None or not goal_handle.accepted:
            print("[FAIL] NFC goal rejected")
            return 2

        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)
        result = result_future.result().result

        print(f"success={bool(result.success)}")
        print(f"uid={result.uid}")
        print(f"authorized={bool(result.authorized)}")
        print(f"user_name={result.user_name}")
        print(f"role={result.role}")
        print(f"message={result.message}")
        return 0 if result.success else 3


def main(argv=None):
    parser = argparse.ArgumentParser(description="Trigger /auth/read_nfc_card once.")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)

    rclpy.init(args=None)
    node = NfcActionClient()
    try:
        return node.run(args.timeout)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
