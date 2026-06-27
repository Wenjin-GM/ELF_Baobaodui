#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能安全工具柜 - 主控程序 V1.1
集成：NFC认证 + 温湿度监测 + 人脸识别 + GPIO继电器控制

运行方式：
    sudo python3 main.py

功能特性：
    - 双模式身份认证（NFC刷卡 + 人脸识别）
    - 实时温湿度监测与环境自动调控
    - 电磁锁门禁控制
    - 操作记录存储
    - 异常报警
    - 多线程事件驱动NFC读卡（V1.1新增）
"""

import sys
import time
import signal
import logging
import threading
import queue
from pathlib import Path
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime

# 添加用户site-packages到路径
def add_user_site_packages():
    for path in (
        Path("/home/elf/.local/lib/python3.10/site-packages"),
        Path.home() / ".local/lib/python3.10/site-packages",
    ):
        if path.exists() and str(path) not in sys.path:
            sys.path.insert(0, str(path))

add_user_site_packages()

# 导入硬件控制模块
try:
    from PN532.drivers.i2c_pn532 import PN532_I2C
    import gpiod
    import smbus2
except ImportError as e:
    print(f"错误：缺少必要的依赖库 - {e}")
    print("请安装：pip install smbus2 gpiod")
    sys.exit(1)


# ==================== 配置常量 ====================

# I2C配置，见 docs/connect_way.md
I2C_BUS_NFC = 7      # PN532: SDA.0/SCL.0, 优先按 I2C7 验证
I2C_BUS_SHT30 = 4    # SHT30: SDA.1/SCL.1, I2C4
I2C_ADDR_NFC = 0x24
I2C_ADDR_SHT30 = 0x44

# GPIO配置
GPIO_CHIP = "gpiochip3"
GPIO_LOCK_LINE = 3    # GPIO.25 / GPIO3_A3 / 三号继电器 / 门锁
GPIO_FAN_LINE = 9     # GPIO.28 / GPIO3_B1 / 二号继电器 / 风扇
GPIO_BUZZER_LINE = 4  # GPIO.23 / GPIO3_A4 / 蜂鸣器（预留）

# 温湿度阈值
TEMP_MIN = 5.0        # 最低温度 (°C)
TEMP_MAX = 40.0       # 最高温度 (°C)
HUMIDITY_MAX = 70.0   # 最高湿度 (%RH) - 提高阈值避免误报

# 认证配置
AUTH_TIMEOUT = 10.0   # 认证超时时间(秒)
LOCK_OPEN_TIME = 5.0  # 门锁开启时间(秒)
NFC_READ_TIMEOUT = 1.0  # NFC读卡超时时间(秒) - 增加超时时间

# 环境监测配置
ENV_CHECK_INTERVAL = 5.0  # 环境监测间隔(秒) - 降低CPU占用

# 数据库文件
DB_FILE = Path("tool_cabinet.db")
CARD_DB_FILE = Path("authorized_cards.json")


# ==================== 系统状态定义 ====================

class SystemState(Enum):
    """系统状态枚举"""
    IDLE = "待机"              # 等待用户认证
    AUTHENTICATING = "认证中"  # 正在进行身份认证
    AUTHORIZED = "已授权"      # 认证成功，门已开启
    OPERATING = "操作中"       # 用户正在存取工具
    MONITORING = "监测中"      # 门关闭后盘点工具
    ALARMING = "报警中"        # 检测到异常
    ERROR = "错误"            # 系统错误


@dataclass
class AuthResult:
    """认证结果"""
    success: bool
    method: str           # "NFC" 或 "FACE"
    user_id: str
    user_name: str
    timestamp: datetime


@dataclass
class EnvironmentData:
    """环境数据"""
    temperature: float
    humidity: float
    timestamp: datetime

    def is_normal(self) -> bool:
        """检查环境是否正常"""
        return (TEMP_MIN <= self.temperature <= TEMP_MAX and
                self.humidity <= HUMIDITY_MAX)


# ==================== 硬件抽象层 ====================

class NFCReader:
    """NFC读卡器封装 - 多线程事件驱动版本"""

    def __init__(self, bus: int = I2C_BUS_NFC):
        self.nfc = PN532_I2C(bus=bus, address=I2C_ADDR_NFC)
        self.nfc.begin()
        logging.info(f"NFC读卡器初始化成功 (I2C{bus}, 0x{I2C_ADDR_NFC:02X})")

        # 事件驱动相关
        self.event_queue = queue.Queue(maxsize=10)  # 卡片事件队列
        self.running = False
        self.polling_thread = None
        self.last_uid = None  # 记录上次读到的卡号，防止重复
        self.last_read_time = 0  # 上次读卡时间

    def start_polling(self):
        """启动后台轮询线程"""
        if self.running:
            logging.warning("NFC轮询线程已在运行")
            return

        self.running = True
        self.polling_thread = threading.Thread(
            target=self._polling_worker,
            name="NFC-Polling",
            daemon=True
        )
        self.polling_thread.start()
        logging.info("NFC后台轮询线程已启动")

    def _polling_worker(self):
        """后台轮询工作线程"""
        logging.info("NFC轮询线程开始工作")

        loop_count = 0  # 循环计数器

        while self.running:
            try:
                # 每100次循环输出一次心跳日志
                loop_count += 1
                if loop_count % 100 == 0:
                    logging.debug(f"[NFC线程] 心跳检查 - 循环次数: {loop_count}")

                # 读取NFC卡（短超时，避免阻塞）
                uid = self.nfc.read_passive_target_id(timeout=0.5)

                if uid:
                    uid_str = ''.join(f'{b:02X}' for b in uid)
                    current_time = time.time()

                    # 防止重复读取同一张卡（2秒内）
                    if uid_str != self.last_uid or (current_time - self.last_read_time) > 2.0:
                        self.last_uid = uid_str
                        self.last_read_time = current_time

                        # 将卡号放入事件队列
                        try:
                            self.event_queue.put_nowait(uid_str)
                            logging.info(f"[NFC线程] 检测到卡片: {uid_str}")  # 改为INFO级别
                        except queue.Full:
                            logging.warning("NFC事件队列已满，丢弃事件")

                    # 检测到卡后短暂延迟，避免连续读取
                    time.sleep(0.5)
                else:
                    # 未检测到卡，短暂休眠降低CPU占用
                    time.sleep(0.1)

            except Exception as e:
                logging.error(f"NFC轮询线程错误: {e}", exc_info=True)  # 添加详细堆栈
                time.sleep(1.0)  # 出错后延迟，避免错误循环

        logging.info("NFC轮询线程已停止")

    def wait_for_card(self, timeout: Optional[float] = None) -> Optional[str]:
        """
        等待卡片事件（阻塞调用，但不占用CPU）

        Args:
            timeout: 超时时间(秒)，None表示无限等待

        Returns:
            卡号字符串，超时返回None
        """
        try:
            return self.event_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def read_card(self, timeout: float = 2.0) -> Optional[str]:
        """
        读取NFC卡（兼容旧接口）
        实际上是等待后台线程的事件
        """
        return self.wait_for_card(timeout=timeout)

    def stop_polling(self):
        """停止后台轮询线程"""
        if not self.running:
            return

        logging.info("正在停止NFC轮询线程...")
        self.running = False

        if self.polling_thread and self.polling_thread.is_alive():
            self.polling_thread.join(timeout=3.0)

        logging.info("NFC轮询线程已停止")


class TemperatureHumiditySensor:
    """SHT30温湿度传感器封装"""

    def __init__(self, bus: int = I2C_BUS_SHT30, address: int = I2C_ADDR_SHT30):
        self.bus_num = bus
        self.address = address
        self.bus = smbus2.SMBus(bus)
        logging.info(f"SHT30传感器初始化成功 (I2C{bus}, 0x{address:02X})")

    @staticmethod
    def _crc8(data):
        """CRC8校验"""
        crc = 0xFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = ((crc << 1) ^ 0x31) & 0xFF
                else:
                    crc = (crc << 1) & 0xFF
        return crc

    def read(self) -> EnvironmentData:
        """读取温湿度"""
        try:
            # 发送测量命令
            self.bus.write_i2c_block_data(self.address, 0x2C, [0x06])
            time.sleep(0.02)

            # 读取数据
            data = self.bus.read_i2c_block_data(self.address, 0x00, 6)

            # CRC校验
            if self._crc8(data[0:2]) != data[2]:
                raise RuntimeError("温度CRC校验失败")
            if self._crc8(data[3:5]) != data[5]:
                raise RuntimeError("湿度CRC校验失败")

            # 转换数据
            temp_raw = (data[0] << 8) | data[1]
            humid_raw = (data[3] << 8) | data[4]
            temperature = -45.0 + 175.0 * temp_raw / 65535.0
            humidity = 100.0 * humid_raw / 65535.0

            return EnvironmentData(
                temperature=temperature,
                humidity=humidity,
                timestamp=datetime.now()
            )
        except Exception as e:
            logging.error(f"SHT30读取错误: {e}")
            # 返回默认值
            return EnvironmentData(25.0, 50.0, datetime.now())

    def close(self):
        """关闭传感器"""
        self.bus.close()


class RelayController:
    """继电器控制器（低电平有效）"""

    def __init__(self, chip_name: str, line: int, name: str):
        self.chip_name = chip_name
        self.line_offset = line
        self.name = name
        self.chip = gpiod.Chip(chip_name)
        self.line_obj = self.chip.get_line(line)

        # 初始化为高电平（继电器断开）
        try:
            self.line_obj.request(
                consumer=f"cabinet_{name}",
                type=gpiod.LINE_REQ_DIR_OUT,
                default_vals=[1]
            )
        except TypeError:
            self.line_obj.request(
                consumer=f"cabinet_{name}",
                type=gpiod.LINE_REQ_DIR_OUT
            )
            self.line_obj.set_value(1)

        logging.info(f"{name}继电器初始化成功 ({chip_name} line {line})")

    def turn_on(self):
        """打开继电器（低电平）"""
        self.line_obj.set_value(0)
        logging.info(f"{self.name} 已打开")

    def turn_off(self):
        """关闭继电器（高电平）"""
        self.line_obj.set_value(1)
        logging.info(f"{self.name} 已关闭")

    def pulse(self, duration: float):
        """脉冲控制"""
        self.turn_on()
        time.sleep(duration)
        self.turn_off()

    def close(self):
        """释放GPIO资源"""
        self.turn_off()
        self.line_obj.release()
        self.chip.close()


# ==================== 业务逻辑层 ====================

class AuthenticationManager:
    """身份认证管理器"""

    def __init__(self, card_db_path: Path):
        self.card_db_path = card_db_path
        self.authorized_cards = self._load_card_db()
        self.face_recognizer = None  # 人脸识别器（可选）

    def _load_card_db(self) -> Dict[str, Dict[str, Any]]:
        """加载授权卡数据库"""
        import json
        try:
            if self.card_db_path.exists():
                with open(self.card_db_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    cards = data.get('cards', {})
                    logging.info(f"已加载 {len(cards)} 张授权卡")
                    return cards
        except Exception as e:
            logging.error(f"加载卡数据库失败: {e}")
        return {}

    def authenticate_nfc(self, uid: str) -> Optional[AuthResult]:
        """NFC卡认证"""
        if uid in self.authorized_cards:
            card_info = self.authorized_cards[uid]
            return AuthResult(
                success=True,
                method="NFC",
                user_id=uid,
                user_name=card_info.get('name', 'Unknown'),
                timestamp=datetime.now()
            )
        return None

    def authenticate_face(self, image) -> Optional[AuthResult]:
        """人脸识别认证（预留接口）"""
        # TODO: 集成 USB/face_auth/face_recognition_core.py
        if self.face_recognizer is None:
            return None
        # 实现人脸识别逻辑
        return None


class EnvironmentController:
    """环境控制器"""

    def __init__(self, sensor: TemperatureHumiditySensor, fan: RelayController):
        self.sensor = sensor
        self.fan = fan
        self.last_data = None
        self.fan_running = False  # 记录风扇状态，避免重复操作

    def monitor_and_adjust(self) -> EnvironmentData:
        """监测并自动调节环境"""
        data = self.sensor.read()
        self.last_data = data

        # 温湿度控制逻辑
        if data.temperature > TEMP_MAX or data.humidity > HUMIDITY_MAX:
            if not self.fan_running:  # 只在风扇未启动时执行
                self.fan.turn_on()
                self.fan_running = True
                logging.warning(f"环境异常 - 温度: {data.temperature:.1f}°C, 湿度: {data.humidity:.1f}%RH - 启动风扇")
        elif data.temperature < TEMP_MIN:
            # TODO: 启动加热器
            if self.fan_running:  # 如果风扇在运行，先关闭
                self.fan.turn_off()
                self.fan_running = False
            logging.warning(f"温度过低: {data.temperature:.1f}°C - 需要加热")
        else:
            if self.fan_running:  # 只在风扇运行时关闭
                self.fan.turn_off()
                self.fan_running = False
                logging.info(f"环境恢复正常 - 温度: {data.temperature:.1f}°C, 湿度: {data.humidity:.1f}%RH - 关闭风扇")

        return data


# ==================== 主控制器 ====================

class ToolCabinetController:
    """智能工具柜主控制器"""

    def __init__(self):
        self.state = SystemState.IDLE
        self.running = True
        self.last_env_check = 0  # 上次环境检测时间戳

        # 初始化硬件
        logging.info("=" * 60)
        logging.info("智能安全工具柜系统启动中...")
        logging.info("=" * 60)

        try:
            self.nfc_reader = NFCReader(bus=I2C_BUS_NFC)
            self.temp_sensor = TemperatureHumiditySensor(bus=I2C_BUS_SHT30)
            self.lock = RelayController(GPIO_CHIP, GPIO_LOCK_LINE, "电磁锁")
            self.fan = RelayController(GPIO_CHIP, GPIO_FAN_LINE, "风扇")

            self.auth_manager = AuthenticationManager(CARD_DB_FILE)
            self.env_controller = EnvironmentController(self.temp_sensor, self.fan)

            logging.info("所有硬件模块初始化成功")

            # 启动NFC后台轮询线程
            self.nfc_reader.start_polling()

        except Exception as e:
            logging.error(f"硬件初始化失败: {e}")
            raise

    def change_state(self, new_state: SystemState):
        """状态转换"""
        old_state = self.state
        self.state = new_state
        logging.info(f"状态转换: {old_state.value} -> {new_state.value}")

    def handle_idle_state(self):
        """处理待机状态"""
        # 定时检测环境（每ENV_CHECK_INTERVAL秒执行一次）
        current_time = time.time()
        if current_time - self.last_env_check >= ENV_CHECK_INTERVAL:
            env_data = self.env_controller.monitor_and_adjust()
            self.last_env_check = current_time

        # 等待NFC事件（阻塞等待，但CPU完全空闲）
        # 使用较短超时，以便定时检查环境
        uid = self.nfc_reader.wait_for_card(timeout=1.0)
        if uid:
            logging.info(f"检测到NFC卡: {uid}")
            self.change_state(SystemState.AUTHENTICATING)
            return uid

        return None

    def handle_authentication(self, uid: str):
        """处理认证"""
        auth_result = self.auth_manager.authenticate_nfc(uid)

        if auth_result and auth_result.success:
            logging.info(f"认证成功: {auth_result.user_name} ({auth_result.method})")
            self.change_state(SystemState.AUTHORIZED)

            # 开门
            logging.info(f"开启电磁锁 {LOCK_OPEN_TIME} 秒")
            self.lock.turn_on()
            time.sleep(LOCK_OPEN_TIME)
            self.lock.turn_off()
            logging.info("电磁锁已关闭")

            self.change_state(SystemState.OPERATING)
            return auth_result
        else:
            logging.warning(f"认证失败: 卡号 {uid} 未授权")
            self.change_state(SystemState.IDLE)
            return None

    def handle_operation(self):
        """处理用户操作"""
        # 等待用户完成工具存取
        logging.info("等待用户操作...")
        time.sleep(2)

        # TODO: 检测门状态，判断是否关闭
        # 目前简化为固定延时

        self.change_state(SystemState.MONITORING)

    def handle_monitoring(self):
        """处理监测"""
        logging.info("开始盘点工具...")

        # TODO: 触发视觉识别模块
        # 目前简化处理

        time.sleep(1)
        logging.info("盘点完成")

        self.change_state(SystemState.IDLE)

    def run(self):
        """主事件循环"""
        logging.info("系统进入运行状态")
        logging.info("等待用户刷卡...")

        try:
            while self.running:
                if self.state == SystemState.IDLE:
                    uid = self.handle_idle_state()
                    if uid:
                        self.handle_authentication(uid)

                elif self.state == SystemState.OPERATING:
                    self.handle_operation()

                elif self.state == SystemState.MONITORING:
                    self.handle_monitoring()

                else:
                    time.sleep(0.1)

        except KeyboardInterrupt:
            logging.info("收到中断信号，正在关闭...")
        except Exception as e:
            logging.error(f"运行错误: {e}", exc_info=True)
        finally:
            self.shutdown()

    def shutdown(self):
        """系统关闭"""
        logging.info("系统关闭中...")

        try:
            # 停止NFC后台线程
            self.nfc_reader.stop_polling()

            # 关闭硬件资源
            self.lock.close()
            self.fan.close()
            self.temp_sensor.close()
            logging.info("所有硬件资源已释放")
        except Exception as e:
            logging.error(f"关闭错误: {e}")

        logging.info("系统已安全退出")


# ==================== 主入口 ====================

def setup_logging():
    """配置日志系统"""
    logging.basicConfig(
        level=logging.DEBUG,  # 改为DEBUG级别，显示NFC线程详细日志
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler('tool_cabinet.log', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )


def main():
    """主函数"""
    setup_logging()

    # 检查权限
    import os
    if os.geteuid() != 0:
        logging.error("错误：需要root权限运行")
        logging.error("请使用: sudo python3 main.py")
        sys.exit(1)

    # 创建并运行主控制器
    controller = ToolCabinetController()

    # 注册信号处理
    def signal_handler(sig, frame):
        logging.info("收到终止信号")
        controller.running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 启动主循环
    controller.run()


if __name__ == '__main__':
    main()
