#!/usr/bin/env python3
"""
Scenario player for ROS2 node testing.

Roles (``mode`` parameter):
  - ``face_action_client``   — call /auth/authenticate_face, verify result.
  - ``fake_face_action_server`` — provide a fake /auth/authenticate_face server.

Usage::

    # Test face_node dry-run success
    ros2 run smart_cabinet_nodes scenario_player \\
      --ros-args -p mode:=face_action_client \\
      -p timeout_sec:=3.0 -p min_confidence:=0.45 \\
      -p expect_success:=true -p expect_user_name:=TestUser -p expect_role:=admin

    # Fake face server for cabinet_logic_node testing
    ros2 run smart_cabinet_nodes scenario_player \\
      --ros-args -p mode:=fake_face_action_server \\
      -p result_delay_sec:=1.0 -p result_success:=true \\
      -p result_user_name:=TestUser -p result_role:=admin

Exit codes: 0 = all assertions passed, 1 = failure.
"""

from __future__ import annotations

import time
import sys

import rclpy
from rclpy.action import ActionServer, ActionClient, GoalResponse, CancelResponse
from rclpy.node import Node

from smart_cabinet_interfaces.action import AuthenticateFace


# ── face action client ────────────────────────────────────────────────

class FaceActionClient(Node):
    """Node that sends one AuthenticateFace goal and checks the result."""

    def __init__(self):
        super().__init__("face_action_client")

        self.declare_parameter("action_name", "/auth/authenticate_face")
        self.declare_parameter("timeout_sec", 3.0)
        self.declare_parameter("min_confidence", 0.45)
        self.declare_parameter("wait_for_server_timeout_sec", 10.0)
        self.declare_parameter("expect_goal_accepted", True)
        self.declare_parameter("expect_success", True)
        self.declare_parameter("expect_user_name", "")
        self.declare_parameter("expect_role", "")
        self.declare_parameter("expect_message", "")

        self._passed = False
        self._done = False
        self._client = ActionClient(
            self,
            AuthenticateFace,
            str(self.get_parameter("action_name").value),
        )

    def run(self):
        action_name = str(self.get_parameter("action_name").value)
        wait_to = float(self.get_parameter("wait_for_server_timeout_sec").value)

        self.get_logger().info(f"waiting for action server {action_name} ({wait_to:.0f}s) …")
        if not self._client.wait_for_server(timeout_sec=wait_to):
            self.get_logger().error(f"action server {action_name} not available")
            self._done = True
            return

        goal = AuthenticateFace.Goal()
        goal.timeout_sec = float(self.get_parameter("timeout_sec").value)
        goal.min_confidence = float(self.get_parameter("min_confidence").value)

        self.get_logger().info(
            f"sending goal: timeout={goal.timeout_sec:.1f}s min_conf={goal.min_confidence:.2f}"
        )
        future = self._client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future)
        goal_handle = future.result()
        expect_goal_accepted = bool(self.get_parameter("expect_goal_accepted").value)

        if goal_handle is None or not goal_handle.accepted:
            if expect_goal_accepted:
                self.get_logger().error("goal was REJECTED")
            else:
                self.get_logger().info("goal was REJECTED as expected")
                self._passed = True
            self._done = True
            return

        if not expect_goal_accepted:
            self.get_logger().error("FAIL: goal was ACCEPTED but expected rejection")
            self._done = True
            return

        self.get_logger().info("goal ACCEPTED")

        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)
        response = result_future.result()

        if response is None:
            self.get_logger().error("no result received")
            self._done = True
            return

        result: AuthenticateFace.Result = response.result
        self.get_logger().info(
            f"result: success={result.success} user={result.user_name!r} "
            f"role={result.role!r} conf={result.confidence:.3f} "
            f"msg={result.message!r}"
        )

        # ── assertions ──
        ok = True
        expect_success = bool(self.get_parameter("expect_success").value)
        expect_user = str(self.get_parameter("expect_user_name").value)
        expect_role = str(self.get_parameter("expect_role").value)
        expect_msg = str(self.get_parameter("expect_message").value)

        if result.success != expect_success:
            self.get_logger().error(
                f"FAIL: success={result.success} expected={expect_success}"
            )
            ok = False
        if expect_user and result.user_name != expect_user:
            self.get_logger().error(
                f"FAIL: user_name={result.user_name!r} expected={expect_user!r}"
            )
            ok = False
        if expect_role and result.role != expect_role:
            self.get_logger().error(
                f"FAIL: role={result.role!r} expected={expect_role!r}"
            )
            ok = False
        if expect_msg and expect_msg not in (result.message or ""):
            self.get_logger().error(
                f"FAIL: message={result.message!r} expected_contains={expect_msg!r}"
            )
            ok = False

        if ok:
            self.get_logger().info("✓ all assertions passed")
            self._passed = True
        else:
            self.get_logger().error("✗ some assertions FAILED")

        self._done = True

    def is_done(self) -> bool:
        return self._done

    def passed(self) -> bool:
        return self._passed


# ── fake face action server ───────────────────────────────────────────

class FakeFaceServer(Node):
    """Fake /auth/authenticate_face server, configurable via parameters."""

    def __init__(self):
        super().__init__("fake_face_action_server")

        self.declare_parameter("action_name", "/auth/authenticate_face")
        self.declare_parameter("result_delay_sec", 1.5)
        self.declare_parameter("result_success", True)
        self.declare_parameter("result_user_name", "TestUser")
        self.declare_parameter("result_role", "admin")
        self.declare_parameter("result_confidence", 0.91)
        self.declare_parameter("result_message", "scenario face authenticated")

        action_name = str(self.get_parameter("action_name").value)

        self._server = ActionServer(
            self,
            AuthenticateFace,
            action_name,
            execute_callback=self._execute,
            goal_callback=self._goal_callback,
        )
        self.get_logger().info(
            f"fake face action server ready on {action_name}"
        )

    def _goal_callback(self, goal_request):
        self.get_logger().info(
            f"goal received: timeout={goal_request.timeout_sec:.1f}s"
        )
        return GoalResponse.ACCEPT

    def _execute(self, goal_handle):
        delay = float(self.get_parameter("result_delay_sec").value)
        self.get_logger().info(f"sleeping {delay:.1f}s before result …")
        time.sleep(delay)

        result = AuthenticateFace.Result()
        result.success = bool(self.get_parameter("result_success").value)
        result.user_name = str(self.get_parameter("result_user_name").value)
        result.role = str(self.get_parameter("result_role").value)
        result.confidence = float(self.get_parameter("result_confidence").value)
        result.message = str(self.get_parameter("result_message").value)

        self.get_logger().info(
            f"returning: success={result.success} user={result.user_name!r} "
            f"role={result.role!r} conf={result.confidence:.3f}"
        )
        goal_handle.succeed()
        return result


# ── main ──────────────────────────────────────────────────────────────

def main(args=None):
    rclpy.init(args=args)

    # Determine mode from ROS parameters (already parsed from CLI)
    temp = Node("_scenario_tmp")
    temp.declare_parameter("mode", "face_action_client")
    mode = str(temp.get_parameter("mode").value).strip()
    temp.destroy_node()

    if mode == "face_action_client":
        node = FaceActionClient()
        exit_code = _spin_client(node)
    elif mode == "fake_face_action_server":
        node = FakeFaceServer()
        try:
            rclpy.spin(node)
        except KeyboardInterrupt:
            pass
        finally:
            node.destroy_node()
        exit_code = 0
    else:
        print(f"[ERROR] unknown mode: {mode!r}", file=sys.stderr)
        print("  valid: face_action_client | fake_face_action_server", file=sys.stderr)
        exit_code = 1

    if rclpy.ok():
        rclpy.shutdown()
    sys.exit(exit_code)


def _spin_client(node: FaceActionClient) -> int:
    """Run the client node once; return 0 on success, 1 on failure."""
    try:
        node.run()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()

    return 0 if node.passed() else 1


if __name__ == "__main__":
    main()
