#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模拟后端数据模块

第一阶段使用模拟数据，不依赖实际硬件
"""

import random
from datetime import datetime
from PyQt5.QtCore import QObject, QTimer, pyqtSignal


class MockBackend(QObject):
    """模拟后端，定期发送模拟数据"""

    # 信号定义
    env_updated = pyqtSignal(dict)          # 环境数据更新
    auth_updated = pyqtSignal(dict)         # 认证数据更新
    tools_updated = pyqtSignal(dict)        # 工具状态更新
    charging_updated = pyqtSignal(dict)     # 充电状态更新
    system_state_changed = pyqtSignal(str)  # 系统状态变化
    event_added = pyqtSignal(dict)          # 新事件添加
    alarm_raised = pyqtSignal(dict)         # 报警触发

    def __init__(self):
        super().__init__()

        # 定时器
        self.env_timer = QTimer()
        self.env_timer.timeout.connect(self._update_env_data)

        self.tools_timer = QTimer()
        self.tools_timer.timeout.connect(self._update_tools_data)

        self.charging_timer = QTimer()
        self.charging_timer.timeout.connect(self._update_charging_data)

        # 模拟数据状态
        self.current_temp = 25.0
        self.current_humidity = 50.0
        self.fan_on = False

        self.battery_slots = [True, False, True, True]
        self.relay_on = False

    def start(self):
        """启动模拟后端"""
        print("[MockBackend] 启动模拟数据服务")
        self.env_timer.start(1000)      # 每秒更新环境数据
        self.tools_timer.start(2000)     # 每2秒更新工具状态
        self.charging_timer.start(3000)  # 每3秒更新充电状态

        # 初始数据推送
        self._update_env_data()
        self._update_tools_data()
        self._update_charging_data()

    def stop(self):
        """停止模拟后端"""
        print("[MockBackend] 停止模拟数据服务")
        self.env_timer.stop()
        self.tools_timer.stop()
        self.charging_timer.stop()

    def _update_env_data(self):
        """模拟环境数据更新"""
        # 温度在 20-30 度之间波动
        self.current_temp += random.uniform(-0.3, 0.3)
        self.current_temp = max(20.0, min(30.0, self.current_temp))

        # 湿度在 45-65% 之间波动
        self.current_humidity += random.uniform(-1.0, 1.0)
        self.current_humidity = max(45.0, min(65.0, self.current_humidity))

        # 湿度 > 55% 时自动开风扇
        if self.current_humidity > 55.0 and not self.fan_on:
            self.fan_on = True
        elif self.current_humidity <= 50.0 and self.fan_on:
            self.fan_on = False

        env_data = {
            "temperature": round(self.current_temp, 1),
            "humidity": round(self.current_humidity, 1),
            "fan_on": self.fan_on,
            "fan_purpose": "除湿" if self.fan_on else "待机",
            "alarm_on": False,
            "timestamp": datetime.now().isoformat()
        }

        self.env_updated.emit(env_data)

    def _update_tools_data(self):
        """模拟工具状态更新"""
        # 五区工具状态：正常/借出/错放
        zones = [
            {
                "zone_id": 1,
                "zone_name": "电池盒充电区",
                "registered": 1,
                "current": 1,
                "borrowed": 0,
                "status": "正常"  # 正常/借出/错放
            },
            {
                "zone_id": 2,
                "zone_name": "钳子区",
                "registered": 2,
                "current": random.choice([2, 1, 2]),
                "borrowed": 0,
                "status": random.choice(["正常", "正常", "借出"])
            },
            {
                "zone_id": 3,
                "zone_name": "测温枪区",
                "registered": 2,
                "current": 2,
                "borrowed": 0,
                "status": "正常"
            },
            {
                "zone_id": 4,
                "zone_name": "万用表区",
                "registered": 2,
                "current": 2,
                "borrowed": 0,
                "status": "正常"
            },
            {
                "zone_id": 5,
                "zone_name": "绝缘手套区",
                "registered": 2,
                "current": random.choice([2, 2, 1]),
                "borrowed": 0,
                "status": random.choice(["正常", "正常", "借出"])
            }
        ]

        for zone in zones:
            zone["borrowed"] = zone["registered"] - zone["current"]
            if zone["current"] < zone["registered"]:
                zone["status"] = "借出"
            elif zone["current"] > zone["registered"]:
                zone["status"] = "错放"

        tools_data = {
            "zones": zones,
            "last_check_time": datetime.now().isoformat(),
            "checking": False
        }

        self.tools_updated.emit(tools_data)

    def _update_charging_data(self):
        """模拟充电状态更新"""
        # 随机模拟电池位变化
        if random.random() < 0.1:  # 10% 概率变化
            idx = random.randint(0, 3)
            self.battery_slots[idx] = not self.battery_slots[idx]

        # 模拟充电控制逻辑
        box_present = any(self.battery_slots)
        if box_present and not self.relay_on:
            if random.random() < 0.2:  # 20% 概率开启充电
                self.relay_on = True
        elif not box_present and self.relay_on:
            self.relay_on = False

        charging_data = {
            "module_online": True,
            "status_valid": True,
            "box_present": box_present,
            "relay_on": self.relay_on,
            "slots": self.battery_slots.copy(),
            "timestamp": datetime.now().isoformat()
        }

        self.charging_updated.emit(charging_data)

    def simulate_auth_success(self, user_name: str = "赵增辉", role: str = "admin"):
        """模拟认证成功"""
        auth_data = {
            "success": True,
            "user_name": user_name,
            "role": role,
            "method": "NFC" if random.random() > 0.5 else "人脸识别",
            "card_uid": "04A1B2C3D4" if random.random() > 0.5 else None,
            "confidence": round(random.uniform(0.85, 0.98), 2),
            "timestamp": datetime.now().isoformat()
        }
        self.auth_updated.emit(auth_data)

        # 添加认证事件
        event = {
            "type": "认证",
            "content": f"{user_name} 通过{auth_data['method']}认证成功",
            "level": "info",
            "timestamp": datetime.now().isoformat()
        }
        self.event_added.emit(event)

    def request_manual_fan(self, on: bool, reason: str = "ui_button"):
        """模拟手动风扇控制"""
        self.fan_on = bool(on)
        self.env_updated.emit({
            "temperature": round(self.current_temp, 1),
            "humidity": round(self.current_humidity, 1),
            "fan_on": self.fan_on,
            "fan_purpose": "手动" if self.fan_on else "待机",
            "alarm_on": False,
            "timestamp": datetime.now().isoformat()
        })
        event = {
            "type": "环境",
            "content": f"手动{'开启' if self.fan_on else '关闭'}风扇",
            "level": "info",
            "timestamp": datetime.now().isoformat()
        }
        self.event_added.emit(event)

    def simulate_auth_failed(self):
        """模拟认证失败"""
        auth_data = {
            "success": False,
            "user_name": None,
            "role": None,
            "method": "NFC",
            "card_uid": "FF000000",
            "timestamp": datetime.now().isoformat()
        }
        self.auth_updated.emit(auth_data)

        # 添加事件
        event = {
            "type": "认证",
            "content": "未授权卡尝试刷卡",
            "level": "warning",
            "timestamp": datetime.now().isoformat()
        }
        self.event_added.emit(event)

    def simulate_door_opened(self):
        """模拟开门"""
        event = {
            "type": "开柜",
            "content": "柜门已打开",
            "level": "info",
            "timestamp": datetime.now().isoformat()
        }
        self.event_added.emit(event)

    def simulate_door_closed(self):
        """模拟关门"""
        event = {
            "type": "关柜",
            "content": "柜门已关闭，开始盘点",
            "level": "info",
            "timestamp": datetime.now().isoformat()
        }
        self.event_added.emit(event)

    def simulate_alarm(self, alarm_type: str = "工具借出"):
        """模拟报警"""
        alarm_data = {
            "type": alarm_type,
            "level": "warning",
            "message": f"检测到{alarm_type}，请管理员处理",
            "timestamp": datetime.now().isoformat()
        }
        self.alarm_raised.emit(alarm_data)

        event = {
            "type": "报警",
            "content": alarm_data["message"],
            "level": "warning",
            "timestamp": datetime.now().isoformat()
        }
        self.event_added.emit(event)
