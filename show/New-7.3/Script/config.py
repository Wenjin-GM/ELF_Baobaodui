#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系统配置文件

用于存储系统参数、阈值、工具配置等
"""

# ========== 显示配置 ==========
DISPLAY_CONFIG = {
    "default_width": 1024,
    "default_height": 600,
    "fullscreen": False,  # 设置为 True 启用全屏
}

# ========== 环境阈值配置 ==========
ENVIRONMENT_CONFIG = {
    "temp_min": 5.0,        # 温度下限 (℃)
    "temp_max": 40.0,       # 温度上限 (℃)
    "humidity_max": 60.0,   # 湿度上限 (%RH)

    # 风扇控制
    "fan_on_humidity": 55.0,    # 湿度超过此值开启风扇
    "fan_off_humidity": 50.0,   # 湿度低于此值关闭风扇
    "fan_on_temp": 35.0,        # 温度超过此值开启风扇
    "fan_off_temp": 30.0,       # 温度低于此值关闭风扇

    "auto_fan_control": True,   # 自动风扇控制
}

# ========== 工具区域配置 ==========
ZONES_CONFIG = [
    {
        "zone_id": 1,
        "zone_name": "电池盒充电区",
        "tool_type": "battery_box",
        "registered_count": 1,
        "requires_charging": True,
    },
    {
        "zone_id": 2,
        "zone_name": "钳子区",
        "tool_type": "pliers",
        "registered_count": 2,
        "requires_charging": False,
    },
    {
        "zone_id": 3,
        "zone_name": "测温枪区",
        "tool_type": "temperature_gun",
        "registered_count": 2,
        "requires_charging": False,
    },
    {
        "zone_id": 4,
        "zone_name": "万用表区",
        "tool_type": "multimeter",
        "registered_count": 2,
        "requires_charging": False,
    },
    {
        "zone_id": 5,
        "zone_name": "绝缘手套区",
        "tool_type": "insulating_glove",
        "registered_count": 2,
        "requires_charging": False,
    },
]

# ========== 充电控制配置 ==========
CHARGING_CONFIG = {
    "auto_charging": True,      # 自动充电控制
    "battery_slots": 4,         # 电池位数量
    "charge_timeout": 7200,     # 充电超时时间 (秒)
}

# ========== 认证配置 ==========
AUTH_CONFIG = {
    "nfc_enabled": True,        # NFC 认证启用
    "face_enabled": True,       # 人脸识别启用
    "auth_timeout": 30,         # 认证超时 (秒)
    "session_timeout": 3600,    # 会话超时 (秒)
}

# ========== 硬件接口配置 ==========
HARDWARE_CONFIG = {
    # I2C
    "sht30_bus": 4,             # SHT30 I2C 总线 (I2C4 一主多从: PN532 0x24 + SHT30 0x44)
    "sht30_addr": 0x44,         # SHT30 I2C 地址
    "pn532_bus": 4,             # PN532 I2C 总线 (I2C4 一主多从)
    "pn532_addr": 0x24,         # PN532 I2C 地址

    # GPIO (需要根据实际板卡配置)
    "lock_relay_gpio": 0,       # 电磁锁继电器 GPIO
    "fan_relay_gpio": 1,        # 风扇继电器 GPIO
    "charging_relay_gpio": 2,   # 充电继电器 GPIO
    "alarm_gpio": 3,            # 报警器 GPIO

    # 摄像头
    "auth_camera_dev": "/dev/video11",      # 认证摄像头
    "cabinet_camera_dev": "/dev/video21",   # 柜内摄像头

    # STM32 串口
    "stm32_serial_port": "/dev/ttyUSB0",    # STM32 串口
    "stm32_baudrate": 115200,               # 波特率
}

# ========== YOLO 模型配置 ==========
YOLO_CONFIG = {
    "model_path": "models/yolo26n.rknn",    # RKNN 模型路径
    "confidence_threshold": 0.5,             # 置信度阈值
    "nms_threshold": 0.4,                    # NMS 阈值
    "input_size": (640, 640),                # 输入尺寸

    # 目标类别
    "classes": [
        "wrench",
        "coil",
        "insulating_glove",
        "temperature_gun",
    ],
}

# ========== 数据库配置 ==========
DATABASE_CONFIG = {
    "db_path": "data/cabinet.db",           # SQLite 数据库路径
    "enable_logging": True,                  # 启用日志记录
}

# ========== 日志配置 ==========
LOG_CONFIG = {
    "log_dir": "logs",                      # 日志目录
    "log_level": "INFO",                    # 日志级别
    "max_log_size": 10 * 1024 * 1024,      # 单个日志文件最大尺寸 (10MB)
    "backup_count": 5,                      # 日志备份数量
}
