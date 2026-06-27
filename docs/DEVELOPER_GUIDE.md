# 智能安全工具柜 — 集成开发手册

> **项目**：电网运维智能安全工具柜系统  
> **硬件**：飞凌 ELF 2（Rockchip RK3588）  
> **队伍**：宝宝队  
> **最后更新**：2026-05-19

---

## 一、系统架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                    PyQt5 人机交互界面                        │
│         (五区状态 | 温湿度 | 充电状态 | 身份认证)            │
└──────────────────────────┬──────────────────────────────────┘
                           │ SQLite
┌──────────────────────────▼──────────────────────────────────┐
│                      主控调度层 (main.py)                    │
│              状态机 + 事件调度 + 异常处理                     │
└──┬────────────┬────────────┬────────────┬───────────────────┘
   │            │            │            │
┌──▼──┐   ┌───▼────┐   ┌──▼───┐   ┌────▼────┐   ┌──────────┐
│视觉 │   │  NFC   │   │ 环境 │   │  充电   │   │  数据库  │
│vision│   │ PN532  │   │ SHT30│   │ GPIO×8  │   │ SQLite   │
│YOLO26│   │ I2C    │   │ I2C  │   │ 继电器  │   │          │
└──┬──┘   └────────┘   └──────┘   └─────────┘   └──────────┘
   │
┌──▼─────────────────────────────────────────────────────────┐
│              RK3588 硬件接口层                               │
│    I2C4  │  GPIO  │  MIPI CSI  │  MIPI DSI  │  UART       │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、硬件接口矩阵

### 2.1 I2C4 总线（/dev/i2c-4）

| 设备 | 地址 | 功能 | 驱动位置 | 状态 |
|------|------|------|---------|------|
| **PN532** | `0x24` | NFC 读卡 | `PN532/drivers/i2c_pn532.py` | ✅ 已完成 |
| **SHT30** | `0x44` | 温湿度 | `sht30_test/sht31-d.c` | ✅ 已完成 |

> 两设备地址不冲突，可安全共用 I2C4。

**驱动使用示例：**

```python
# PN532 (Python)
from PN532.drivers.i2c_pn532 import PN532_I2C
nfc = PN532_I2C(bus=4)
nfc.begin()
uid = nfc.read_passive_target_id(timeout=2.0)
```

```bash
# SHT30 (C，需编译)
cd sht30_test && make
sudo ./sht31-d p    # 打印温湿度
sudo ./sht31-d s    # 打印状态
```

### 2.2 GPIO 分配

| 功能 | gpiochip | line | 物理引脚 | 备注 | 状态 |
|------|----------|------|---------|------|------|
| **蜂鸣器** | `gpiochip3` | 13 | Pin 11 (GPIO3_B5) | 声光报警 | ✅ 已测试 |
| **电磁锁 1** | 待定义 | — | — | 工具柜门锁 | ❌ 未实现 |
| **电磁锁 2-5** | 待定义 | — | — | 分区锁 | ❌ 未实现 |
| **充电继电器 1-8** | 待定义 | — | — | 8 路充电控制 | ❌ 未实现 |
| **加热器** | 待定义 | — | — | 环境调控 | ❌ 未实现 |
| **除湿器** | 待定义 | — | — | 环境调控 | ❌ 未实现 |
| **风扇** | 待定义 | — | — | 环境调控 | ❌ 未实现 |

**GPIO 编程规范（必须使用 gpiod，禁止 RPi.GPIO）：**

```python
import gpiod

chip = gpiod.Chip('gpiochip3')
line = chip.get_line(13)
line.request(consumer='buzzer', type=gpiod.LINE_REQ_DIR_OUT)
line.set_value(1)   # 高电平
line.set_value(0)   # 低电平
```

> 参考：`charging/test_buzzer.py`

### 2.3 摄像头 / 显示

| 设备 | 接口 | 分辨率 | 用途 | 状态 |
|------|------|--------|------|------|
| **柜内摄像头** | MIPI CSI | — | 五区工具在位检测 | ❌ 未实现 |
| **柜外摄像头** | MIPI CSI | — | 人脸识别 | ❌ 未实现 |
| **触摸屏** | MIPI DSI | 1024×600 | PyQt5 界面 | ❌ 未实现 |

---

## 三、子系统开发指南

### 3.1 NFC 身份认证（`PN532/`）— ✅ 已完成

**负责人**：已调通  
**接口**：I2C4，地址 `0x24`  
**关键注意点**：
- 拨码开关 **1=OFF, 2=OFF** 才是 I2C 模式
- 需要 `sudo` 运行（或加入 `i2c` 组后重新登录）
- 驱动已内置上电唤醒序列

**集成接口：**
```python
from PN532.drivers.i2c_pn532 import PN532_I2C

class NFCAuth:
    def __init__(self):
        self.nfc = PN532_I2C(bus=4)
        self.nfc.begin()
    
    def poll(self, timeout=2.0):
        uid = self.nfc.read_passive_target_id(timeout=timeout)
        if uid:
            return ''.join(f'{b:02X}' for b in uid)
        return None
```

---

### 3.2 温湿度传感（`sht30_test/`）— ✅ 已完成

**负责人**：C 驱动已编译  
**接口**：I2C4，地址 `0x44`  
**关键注意点**：
- C 驱动基于 `i2c-dev`，需要 `sudo` 运行
- 考虑封装 Python 绑定（ctypes / subprocess）供主程序调用

**封装建议：**
```python
import subprocess

def read_sht30():
    result = subprocess.run(
        ['./sht30_test/sht31-d', 'p'],
        capture_output=True, text=True
    )
    # 解析输出提取温度、湿度
    # TODO: 根据实际输出格式解析
```

---

### 3.3 智能充电控制（`charging/`）— ❌ 待开发

**需求**：8 路 GPIO 继电器控制，支持过充保护  
**触发条件**：工具放入 + 视觉确认在位 → 启动对应充电位  
**安全机制**：
- 定时检测（如 4 小时自动断电）
- 温度异常时强制断电
- 充满检测（电流下降或时间阈值）

**待实现文件：**
```
charging/
├── __init__.py
├── charge_controller.py      # 充电控制主类
├── relay_driver.py           # GPIO 继电器驱动（8路）
└── safety_monitor.py         # 过充/过温保护逻辑
```

**继电器 GPIO 分配（待硬件确认后填入）：**

| 充电位 | gpiochip | line | 引脚 |
|--------|----------|------|------|
| 位 1 | 待定义 | 待定义 | 待定义 |
| 位 2-8 | 待定义 | 待定义 | 待定义 |

---

### 3.4 环境调控（`environment/`）— ❌ 待开发

**需求**：根据 SHT30 读数自动控制加热/除湿/风扇  
**策略建议**：

| 条件 | 动作 |
|------|------|
| 温度 < 5°C | 启动加热器 |
| 温度 > 35°C | 启动风扇 |
| 湿度 > 80% RH | 启动除湿器 |
| 正常范围 | 关闭所有调控设备 |

**待实现文件：**
```
environment/
├── __init__.py
├── climate_controller.py     # 温控主类
├── thresholds.py             # 阈值配置
└── actuator_driver.py        # GPIO 驱动（加热/除湿/风扇）
```

---

### 3.5 AI 视觉盘点（`vision/`）— ❌ 待开发

**需求**：YOLOv8 训练 → RKNN INT8 量化 → 三核 NPU 推理  
**检测目标**：五区工具在位状态  
**技术栈**：
- 训练：YOLOv8n + 自定义数据集
- 转换：`rknn-toolkit2` 导出 `.rknn`
- 推理：`rknn-toolkit-lite2` Python API
- 摄像头：`OpenCV` / `GStreamer` + V4L2

**待实现文件：**
```
vision/
├── __init__.py
├── camera.py                 # 摄像头采集（MIPI CSI）
├── rknn_detector.py          # RKNN 推理引擎
├── zone_classifier.py        # 五区在位判断
├── models/
│   ├── tool_yolov8n.rknn     # 量化后的模型
│   └── labels.txt            # 类别标签
└── test_vision.py            # 视觉测试脚本
```

**RKNN 推理伪代码：**
```python
from rknnlite.api import RKNNLite

rknn = RKNNLite()
rknn.load_rknn('vision/models/tool_yolov8n.rknn')
rknn.init_runtime(core_mask=RKNNLite.NPU_CORE_0)

# 输入图像 → 输出检测结果
outputs = rknn.inference(inputs=[img])
```

---

### 3.6 人脸识别（柜外摄像头）— ❌ 待开发

**需求**：双模式认证（NFC + 人脸）  
**可选方案**：
- 方案 A：MobileFaceNet + RKNN 量化
- 方案 B：瑞芯微官方 `rknpu2` 人脸 SDK
- 方案 C：使用 `face_recognition` 库（CPU，慢但简单）

**建议**：比赛时间有限，优先用 **NFC 单模式** 保证功能完整，人脸作为加分项。

---

### 3.7 人机交互界面（`display/`）— ❌ 待开发

**需求**：PyQt5 界面，显示五区状态 / 温湿度 / 充电 / 身份  
**硬件**：7 寸 MIPI DSI 触摸屏（1024×600）  
**建议架构**：

```
display/
├── __init__.py
├── main_window.py            # 主窗口
├── widgets/
│   ├── zone_widget.py        # 五区状态显示
│   ├── env_widget.py         # 温湿度显示
│   ├── charge_widget.py      # 充电状态
│   └── auth_widget.py        # 身份认证提示
└── resources/
    └── icons/                # UI 图标资源
```

---

## 四、主程序框架（`main.py`）

当前 `main.py` 是空文件，建议按以下结构实现：

```python
#!/usr/bin/env python3
import sys
import time
import signal
from PyQt5.QtWidgets import QApplication

# 子系统导入
sys.path.insert(0, 'PN532')
from PN532.drivers.i2c_pn532 import PN532_I2C

# TODO: 导入其他子系统
# from display.main_window import MainWindow
# from environment.climate_controller import ClimateController
# from charging.charge_controller import ChargeController
# from vision.rknn_detector import VisionDetector

class ToolCabinetSystem:
    def __init__(self):
        self.running = True
        
        # 初始化各子系统
        self.nfc = PN532_I2C(bus=4)
        self.nfc.begin()
        
        # TODO: 初始化其他模块
        # self.vision = VisionDetector()
        # self.charge = ChargeController()
        # self.climate = ClimateController()
        
        # 信号处理
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)
    
    def run(self):
        """主循环"""
        while self.running:
            # 1. 轮询 NFC 读卡
            uid = self.nfc.read_passive_target_id(timeout=0.5)
            if uid:
                self.handle_auth(uid)
            
            # 2. 环境调控（每 30 秒）
            # self.climate.check_and_adjust()
            
            # 3. 视觉盘点（每分钟或触发时）
            # self.vision.scan_zones()
            
            time.sleep(0.1)
    
    def handle_auth(self, uid):
        """处理身份认证"""
        uid_str = ''.join(f'{b:02X}' for b in uid)
        print(f"[AUTH] Card detected: {uid_str}")
        # TODO: 查授权数据库 → 开锁/拒绝
    
    def shutdown(self, signum, frame):
        print("\n[SHUTDOWN] Cleaning up...")
        self.running = False

if __name__ == '__main__':
    app = QApplication(sys.argv)
    system = ToolCabinetSystem()
    
    # TODO: 启动 PyQt5 界面
    # window = MainWindow(system)
    # window.show()
    
    # 后台线程跑主循环
    # threading.Thread(target=system.run).start()
    
    # sys.exit(app.exec_())
    
    # 临时：无界面模式
    try:
        system.run()
    except KeyboardInterrupt:
        system.shutdown(None, None)
```

---

## 五、开发规范

### 5.1 代码风格

| 语言 | 缩进 | 行宽 | 命名规范 |
|------|------|------|---------|
| Python | 4 空格 | ≤120 | snake_case，类名 CamelCase |
| C/C++ | Tab | ≤120 | 小写 + 下划线，结构体后缀 `_t` |

### 5.2 硬件访问规范

- **GPIO**：必须使用 `gpiod` 库，禁止 `RPi.GPIO`
- **I2C**：使用 `smbus2`（Python）或 `i2c-dev` ioctl（C）
- **摄像头**：优先 GStreamer pipeline，备选 OpenCV V4L2
- **权限**：I2C/GPIO 需要 root 或加入对应用户组

### 5.3 目录规范

```
smart_tool_cabinet/
├── main.py                 # 唯一入口
├── AGENTS.md               # AI 开发指南
├── DEVELOPER_GUIDE.md      # 本手册
├── <subsystem>/            # 各子系统目录
│   ├── __init__.py
│   ├── <driver>.py         # 硬件驱动
│   └── <module>.py         # 业务逻辑
└── utils/                  # 公共工具
    ├── database.py         # SQLite 封装
    ├── logger.py           # 日志
    └── config.py           # 配置管理
```

---

## 六、调试工具清单

| 工具 | 用途 | 示例 |
|------|------|------|
| `i2cdetect` | 扫描 I2C 设备 | `sudo i2cdetect -y 4` |
| `i2cdump` | 读取 I2C 寄存器 | `sudo i2cdump -y 4 0x24` |
| `i2cset` / `i2cget` | 读写 I2C 单字节 | `sudo i2cset -y 4 0x44 0x2C 0x06` |
| `gpioinfo` | 查看 GPIO 占用 | `gpioinfo` |
| `gpioset` | 临时设置 GPIO | `gpioset gpiochip3 13=1` |
| `v4l2-ctl` | 摄像头信息 | `v4l2-ctl --list-devices` |
| `dmesg` | 内核日志 | `dmesg | grep -i i2c` |

---

## 七、已知问题与 TODO

| # | 问题 | 优先级 | 负责人 |
|---|------|--------|--------|
| 1 | `main.py` 为空，无系统入口 | 🔴 高 | 待分配 |
| 2 | 充电继电器 GPIO 未分配 | 🔴 高 | 待硬件确认 |
| 3 | 电磁锁 GPIO 未分配 | 🔴 高 | 待硬件确认 |
| 4 | PyQt5 界面未开始 | 🔴 高 | 待分配 |
| 5 | YOLOv8 数据集未采集 | 🟡 中 | 待分配 |
| 6 | RKNN 模型未训练/量化 | 🟡 中 | 待分配 |
| 7 | SHT30 需封装 Python 接口 | 🟡 中 | 待分配 |
| 8 | SQLite 数据库表结构未设计 | 🟡 中 | 待分配 |
| 9 | 人脸识别方案未确定 | 🟢 低 | 可选 |

---

## 八、参考文档

| 文档 | 位置 | 说明 |
|------|------|------|
| AI 开发指南 | `AGENTS.md` | 面向 Kimi 等 AI 助手的详细指南 |
| 硬件规格书 | `ELF 2_Product spec.md` | RK3588 接口详细参数 |
| 项目申报书 | `shenbaoshu.md` | 比赛申报材料 |
| NFC 测试指南 | `NFC_I2C测试指南.md` | PN532 I2C 详细测试步骤 |
| 本手册 | `DEVELOPER_GUIDE.md` | 集成开发总览 |

---

> 本手册随项目进展持续更新。新增子系统或修改硬件接口后，请同步更新此文档。
