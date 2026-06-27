# AGENTS.md — 宝宝队项目开发指南（ELF 2 / RK3588）

> **项目**：基于 RK3588 的电网运维智能安全工具柜系统  
> **参赛赛道**：瑞芯微赛道  
> **硬件平台**：飞凌嵌入式 ELF 2 开发板（Rockchip RK3588）  
> **资料包版本**：ELF 2 官方资料包（2026年4月版）  
> **生成日期**：2026-05-15

---

## 一、项目概述

本项目为**宝宝队**参加瑞芯微赛道的参赛作品，依托飞凌 ELF 2 开发板（RK3588）打造一套面向电力运维场景的**全本地化、工业级智能安全工具柜系统**。

### 1.1 核心功能

| 功能模块 | 技术实现 | 关键指标 |
|---------|---------|---------|
| **AI 视觉五区盘点** | YOLO26 + RKNN INT8 量化 + 三核 NPU 并行 | 识别准确率 ≥96%，单帧 32fps |
| **双模式身份认证** | NFC（PN532）+ 人脸识别（MIPI CSI 摄像头） | 响应 ≤0.4s |
| **智能充电管控** | GPIO 控制 8 路继电器 + 视觉触发 + 过充保护 | 响应 ≤0.5s |
| **温湿度自动调控** | SHT30（I2C）+ GPIO 控制加热/除湿/风扇 | 精度 ±0.3℃/±2%RH |
| **人机交互界面** | PyQt5 + GPU 硬件加速 + SQLite 数据记录 | 界面流畅，数据不丢失 |

### 1.2 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│  人机交互层：PyQt5 触摸屏 + SQLite 本地数据库                  │
├─────────────────────────────────────────────────────────────┤
│  边缘计算层：RK3588 (Ubuntu 22.04)                           │
│             ├── NPU: YOLO26 工具检测 + 人脸识别推理           │
│             ├── CPU A76×4: 业务逻辑 / 充电控制 / 温湿度调节   │
│             ├── CPU A55×4: 系统后台任务                       │
│             └── GPU Mali-G610: PyQt5 界面渲染 / 摄像头画面显示 │
├─────────────────────────────────────────────────────────────┤
│  感知层：MIPI CSI 柜内/柜外摄像头 + PN532 NFC 读卡器(UART)   │
│          + SHT30 温湿度传感器(I2C)                            │
├─────────────────────────────────────────────────────────────┤
│  控制执行层：GPIO 电磁锁(5路) + 充电继电器(8路) + 声光报警    │
│             + 加热模块 / 除湿模块 / 散热风扇                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、官方资料包导航

本资料包已生成 **8 个 .md 导读文件**，按目录组织如下：

| 目录 | 导读文件 | 核心内容 |
|------|---------|---------|
| `00-使用前必读/` | `00-使用前必读.md` | 学习路线技能树、资料完整性检查 |
| `01-教程文档/` | `01-教程文档.md` | 10 份分层教程 + 配套源码索引 |
| `02-Linux源代码/` | `02-Linux源代码.md` | SDK 分卷解压、Git 版本、编译指南 |
| `04-硬件资料/` | `04-硬件资料.md` | 原理图、芯片手册、引脚复用表、Altium 源文件 |
| `05-结构资料/` | `05-结构资料.md` | 亚克力 2D/3D 图纸、装配说明 |
| `07-RK原厂资料/` | `07-RK原厂资料.md` | TRM 手册、RKNN 文档、实时补丁、30+模块开发指南 |
| 根目录 | `ELF 2_Product spec.md` | 开发板完整硬件规格书（接口/参数/配件） |
| 根目录 | `宝宝队申报书.md` | 项目申报书 Markdown 版 |
| 根目录 | `宝宝队申报书_分析.md` | 项目分析报告（问题诊断 + 改进建议） |

---

## 三、项目需求 ↔ 官方资料对应矩阵

### 3.1 按功能模块对应

| 项目功能 | 需要用到的官方资料 | 具体路径/文件 |
|---------|------------------|--------------|
| **YOLO26 模型训练** | AI 模型训练到部署教程 | `01-教程文档/进阶篇之-基于RK3588的AI模型训练到部署/基于RK3588的AI模型训练到部署.pdf` |
| **RKNN 模型转换/量化** | AI 例程源码 + RKNN 工具链 | `01-教程文档/进阶篇之-基于RK3588的AI模型训练到部署/AI例程源码/` |
| **NPU 推理部署** | RK 原厂 NPU 文档 | `07-RK原厂资料.md` → NPU / RKNN 章节 |
| **RGA 图像预处理** | RK 原厂 RGA 文档 | `07-RK原厂资料.md` → RGA 章节 |
| **PyQt5 人机交互界面** | Qt 应用编程教程（参考）+ PyQt5 开发 | `01-教程文档/应用篇之-Qt应用编程/` |
| **SQLite 数据库** | 系统应用编程教程 | `01-教程文档/应用篇之-系统应用编程.pdf` |
| **GPIO 控制（电磁锁/继电器）** | 快速使用手册 GPIO 章节 + 命令行例程 | `01-教程文档/ELF 2开发板快速使用手册/` |
| **I2C 通信（SHT30）** | 快速使用手册 I2C 章节 + 嵌入式接口通识 | `01-教程文档/ELF 2开发板快速使用手册/`、`基础篇之-嵌入式接口通识.pdf` |
| **UART 通信（PN532 NFC）** | 快速使用手册 UART 章节 | `01-教程文档/ELF 2开发板快速使用手册/` |
| **MIPI CSI 摄像头** | 快速使用手册摄像头章节 + RK ISP 文档 | `01-教程文档/ELF 2开发板快速使用手册/`、`07-RK原厂资料.md` → ISP/Camera |
| **系统烧录/部署** | 快速使用手册第5章 + SDK 编译 | `01-教程文档/ELF 2开发板快速使用手册.pdf`、`02-Linux源代码.md` |
| **硬件接口调试** | 硬件原理图 + 引脚复用表 + 芯片数据手册 | `04-硬件资料.md` |
| **外壳结构设计** | 亚克力 2D/3D 图纸 + DXF | `05-结构资料.md`、`04-硬件资料/03-DXF文件/` |
| **内核/驱动定制** | 软件系统开发教程 + SDK 源码 | `01-教程文档/进阶篇之-ELF 2开发板软件系统开发教程/`、`02-Linux源代码.md` |
| **多媒体（视频记录）** | MPP/GStreamer 文档 + VPU 规格 | `07-RK原厂资料.md` → Multimedia / MPP |
| **离线语音（扩展）** | RK 原厂 Audio 文档 | `07-RK原厂资料.md` → Audio / 离线语音 SDK |

### 3.2 按开发阶段对应

```
阶段1：环境搭建
├── 双系统 Ubuntu 22.04 安装 → 00-使用前必读.md → 学习路线
├── Ubuntu 22.04 配置 → 01-教程文档.md → 快速使用手册第6章
├── 交叉编译器安装 → 02-Linux源代码.md → SDK prebuilts/
├── PyQt5 环境配置 → 01-教程文档.md → Python应用编程/Qt应用编程参考
└── RKNN 环境安装 → 01-教程文档.md → AI模型训练到部署

阶段2：AI 模型开发
├── 数据集采集/标注 → 01-教程文档.md → AI教程 + 数据集划分.py
├── YOLO26 训练 → 01-教程文档.md → ultralytics_yolov26-main.zip
├── ONNX 导出 → 项目代码
├── RKNN 转换/量化 → 01-教程文档.md → AI例程源码 + RKNN-Toolkit2
├── 板端推理测试 → 01-教程文档.md → RKNN-Toolkit-Lite2 v2.3.2
└── RGA 预处理优化 → 07-RK原厂资料.md → RGA 文档

阶段3：应用软件开发
├── PyQt5 界面设计 → 项目代码
├── SQLite 数据库 → 系统应用编程.pdf / Python应用编程
├── GPIO 控制模块 → 01-教程文档.md → 命令行例程源码
├── I2C/SHT30 驱动 → 快速使用手册 + 嵌入式接口通识
├── UART/PN532 通信 → 快速使用手册 UART 章节
├── 摄像头采集 → 快速使用手册 + MPP/GStreamer 文档
└── 业务逻辑整合 → 系统应用编程.pdf

阶段4：系统联调与部署
├── 功能联调 → 快速使用手册第3-4章（外设测试命令）
├── 性能优化 → 07-RK原厂资料.md → PERF / NPU / RGA
├── 固件编译 → 02-Linux源代码.md → build.sh
├── 系统烧录 → 01-教程文档.md → 快速使用手册第5章
└── 演示视频录制 → 项目自备
```

---

## 四、技术栈与关键版本

### 4.1 硬件平台

| 组件 | 型号/规格 | 项目用途 |
|------|----------|---------|
| SoC | Rockchip RK3588 | 核心控制单元 |
| CPU | 4×A76@2.4GHz + 4×A55@1.8GHz | 业务逻辑、后台任务 |
| NPU | 6 TOPS，三核，INT8 | YOLO26 推理、人脸识别 |
| GPU | Mali-G610 MP4 | PyQt5 界面渲染 |
| RAM | 4GB/8GB LPDDR4 | 运行时内存 |
| ROM | 32GB/64GB eMMC | 系统 + 数据存储 |
| 核心板尺寸 | 50mm × 68mm | 嵌入工具柜 |
| 底板尺寸 | 120mm × 75mm | 接口扩展 |

### 4.2 软件栈

| 层级 | 组件 | 版本 | 说明 |
|------|------|------|------|
| OS | Ubuntu Desktop | 22.04 (Jammy) | Xfce 桌面，预装 Wayland/Weston |
| Kernel | Linux | 5.10.209 | 飞凌定制分支 ELF2 |
| NPU Driver | RKNPU | 0.9.8 | NPU 硬件驱动 |
| AI Toolchain | RKNN-Toolkit2 | v1.6.0 | PC 端模型转换 |
| AI Runtime | RKNN-Toolkit-Lite2 | v2.3.2 | 板端推理（Python 3.10） |
| AI Model | YOLO26 | Ultralytics | 轻量级目标检测 |
| GUI Framework | PyQt5 | 5.15+ | 人机交互界面 |
| Database | SQLite | 3.x | 本地数据存储 |
| Multimedia | GStreamer + MPP | SDK 内置 | 摄像头采集、视频编码 |
| Image Preprocessing | RGA | SDK 内置 | 硬件图像缩放/格式转换 |
| Cross Compiler | gcc-arm | 10.3-2021.07 | aarch64-none-linux-gnu |

### 4.3 外设模块

| 外设 | 接口 | 芯片/型号 | 项目用途 |
|------|------|----------|---------|
| 柜内摄像头 | MIPI CSI | OV13855 (1300万像素) | AI 视觉盘点 |
| 柜外摄像头 | MIPI CSI / USB | 兼容模块 | 人脸识别 |
| NFC 读卡器 | UART | PN532 | 刷卡身份认证 |
| 温湿度传感器 | I2C | SHT30 | 环境监测 |
| 电磁锁 | GPIO | 5 路 | 柜门控制 |
| 充电继电器 | GPIO | 8 路 | 智能充电 |
| 声光报警器 | GPIO | 1 路 | 异常报警 |
| 加热/除湿/风扇 | GPIO/PWM | 多路 | 温湿度调节 |
| 触摸屏 | MIPI DSI / HDMI | 7 寸 1024×600 | PyQt5 界面显示 |

---

## 五、开发环境搭建速查

### 5.1 宿主机环境（双系统 Ubuntu 22.04）

```bash
# 1. 安装基础依赖
sudo apt-get update
sudo apt-get install -y openssh-server vim git make gcc g++ libssl-dev \
  liblz4-tool expect patchelf chrpath gawk texinfo cmake bison flex \
  unzip device-tree-compiler ncurses-dev python-is-python3 python2

# 2. 安装 ncurses（menuconfig 需要）
sudo apt-get install libncurses*

# 3. 安装网络工具
sudo apt-get install net-tools
```

### 5.2 SDK 源码解压

```bash
cd 02-Linux源代码/
cat ELF2-linux-source.tar.bz2.0* > ELF2-linux-source.tar.bz2
tar -xjf ELF2-linux-source.tar.bz2 -C /home/elf/work/
```

### 5.3 交叉编译工具链

```bash
# 方式1：使用 SDK 内置工具链
export CROSS_COMPILE=/home/elf/work/ELF2-linux-source/prebuilts/gcc/linux-x86/aarch64/gcc-arm-10.3-2021.07-x86_64-aarch64-none-linux-gnu/bin/aarch64-none-linux-gnu-

# 方式2：使用 AI 教程包中的独立工具链（解压到 ~/）
tar -xvf gcc-arm-10.2-2020.11-x86_64-aarch64-none-linux-gnu.tar.xz -C ~/
export PATH=~/gcc-arm-10.2-2020.11-x86_64-aarch64-none-linux-gnu/bin:$PATH
```

### 5.4 PyQt5 环境配置

```bash
# 在 Python 虚拟环境中安装 PyQt5
source ~/elf2_ai_env/bin/activate
pip install PyQt5

# 如需 PyQt5 工具（Qt Designer 等）
pip install pyqt5-tools
```

### 5.5 RKNN 环境

```bash
# PC 端（模型转换）
pip install rknn-toolkit2==1.6.0

# 板端（推理运行）
pip install rknn_toolkit_lite2-2.3.2-cp310-cp310-manylinux_2_17_aarch64.whl
```

---

## 六、核心模块开发指南

### 6.1 AI 视觉模块（YOLO26 → RKNN）

**开发流程**：

```
数据集采集（柜内五区工具照片）
    ↓
数据标注（LabelImg / Labelme，6类工具）
    ↓
数据集划分（训练集/验证集/测试集）← 使用 数据集划分.py
    ↓
YOLO26 训练（PC 端 GPU）
    ↓
导出 ONNX → 使用 RKNN-Toolkit2 转换为 RKNN
    ├── INT8 量化（减少精度损失）
    ├── 算子融合（Conv+BN+ReLU）
    ├── 算子替换（SiLU → ReLU）
    └── 三核 NPU 并行配置
    ↓
板端部署（RKNN-Lite2 + RGA 预处理）
    ↓
五区工具在位检测 + 错放/缺失判断
```

**关键代码片段**（三核 NPU 并行）：

```python
from rknnlite.api import RKNNLite

rknn_lite = RKNNLite()
rknn_lite.load_rknn('yolov26_tools.rknn')

# 启用三核 NPU 并行
rknn_lite.init_runtime(core_mask=RKNNLite.NPU_CORE_0_1_2)

# 推理
outputs = rknn_lite.inference(inputs=[img])
```

**参考资源**：
- 教程：`01-教程文档/进阶篇之-基于RK3588的AI模型训练到部署/`
- 例程：`AI例程源码/ultralytics_yolov26-main.zip`
- 文档：`07-RK原厂资料.md` → NPU / RGA 章节

---

### 6.2 PyQt5 人机交互模块

**技术要点**：
- 使用 PyQt5，依托 RK3588 GPU 硬件加速渲染
- 主界面布局：五区工具状态网格 + 充电信息面板 + 温湿度显示 + 系统日志
- 多线程：UI 主线程 + 摄像头采集线程 + AI 推理线程 + 传感器轮询线程
- 数据库：SQLite 异步写入，避免阻塞 UI
- 开发便捷：Python 直接开发，无需交叉编译，源码复制到板端即可运行

**运行方式**：

```bash
# PC 端开发调试
python main.py

# 板端直接运行（Ubuntu Desktop 自带 PyQt5 或 pip 安装）
scp *.py elf@192.168.0.233:/home/elf/
ssh elf@192.168.0.233
python3 main.py
```

**参考资源**：
- 教程（参考）：`01-教程文档/应用篇之-Qt应用编程/`
- Qt 例程源码（C++ 参考，可对照移植为 PyQt5）：`Qt例程源码/`

---

### 6.3 GPIO 控制模块（电磁锁 / 继电器 / 报警器）

**⚠️ 重要：不要使用 RPi.GPIO！**

RK3588 平台应使用 `gpiod` 库或 `sysfs`：

```python
# 方案一：gpiod（推荐）
import gpiod

chip = gpiod.Chip('gpiochip0')
line = chip.get_line(10)
line.request(consumer="lock_ctl", type=gpiod.LINE_REQ_DIR_OUT)
line.set_value(1)  # 开锁
line.set_value(0)  # 关锁

# 方案二：sysfs（无需额外库）
import os

# 导出 GPIO
with open("/sys/class/gpio/export", "w") as f:
    f.write("10")

# 设置方向
with open("/sys/class/gpio/gpio10/direction", "w") as f:
    f.write("out")

# 控制电平
with open("/sys/class/gpio/gpio10/value", "w") as f:
    f.write("1")  # 高电平
```

**参考资源**：
- 教程：`01-教程文档/ELF 2开发板快速使用手册/` GPIO 章节
- 引脚定义：`04-硬件资料/04-管脚分配表/ELF 2引脚复用表20250603.xlsx`
- 原理图：`04-硬件资料/ELF 2 V1.2_硬件资料/00-PDF原理图/`

---

### 6.4 I2C 通信模块（SHT30 温湿度传感器）

```python
import smbus2
import time

bus = smbus2.SMBus(4)  # 使用 I2C4（40Pin 引出）
SHT30_ADDR = 0x44

# 单次测量命令（高精度）
bus.write_i2c_block_data(SHT30_ADDR, 0x2C, [0x06])
time.sleep(0.015)

# 读取 6 字节数据
data = bus.read_i2c_block_data(SHT30_ADDR, 0x00, 6)

# 解析温度和湿度
temp_raw = data[0] << 8 | data[1]
hum_raw = data[3] << 8 | data[4]
temp = -45 + 175 * temp_raw / 65535
hum = 100 * hum_raw / 65535
```

**参考资源**：
- 教程：`01-教程文档/ELF 2开发板快速使用手册/` I2C 测试章节
- 接口通识：`01-教程文档/基础篇之-嵌入式接口通识.pdf`

---

### 6.5 UART 通信模块（PN532 NFC）

```python
import serial

# UART9（40Pin 引出，默认 115200）
ser = serial.Serial('/dev/ttyS9', 115200, timeout=1)

# PN532 唤醒帧
wake = bytes([0x55, 0x55, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
              0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0x03, 0xFD,
              0xD4, 0x14, 0x01, 0x17, 0x00])
ser.write(wake)
response = ser.read(256)
```

**参考资源**：
- 教程：`01-教程文档/ELF 2开发板快速使用手册/` UART 章节
- 规格书：`ELF 2_Product spec.md` → UART 接口规格

---

### 6.6 MIPI CSI 摄像头采集

```python
# 使用 GStreamer + OpenCV
cap = cv2.VideoCapture(
    'v4l2src device=/dev/video-camera0 ! '
    'video/x-raw,format=NV12,width=1920,height=1080 ! '
    'videoconvert ! appsink',
    cv2.CAP_GSTREAMER
)
```

**参考资源**：
- 教程：`01-教程文档/ELF 2开发板快速使用手册/` 摄像头测试章节
- 文档：`07-RK原厂资料.md` → Camera / ISP / Multimedia

---

## 七、项目已知问题与修正方案

### 问题 1：申报书附录 GPIO 代码错误（严重）

**问题**：申报书附录 A 使用了 `import RPi.GPIO as GPIO`，这是树莓派专用库，RK3588 上无法运行。

**修正**：使用 `gpiod` 或 `sysfs` 方式（详见 6.3 节）。

### 问题 2：第三部分 "完成情况及性能参数" 空白

**问题**：申报书该章节完全空白，是评委重点查看部分。

**建议补充**：
- 实物照片（工具柜整体、内部五区、RK3588 接线）
- 实际测试数据表格（与 1.4 指标一一对应）
- 功能演示视频（NFC/人脸开柜 → 取放工具 → AI 盘点 → 异常报警）

### 问题 3：人脸识别算法未明确

**问题**：申报书提到人脸识别但未说明具体算法。

**建议方案**：
- 方案 A：YOLO26 人脸检测 + MobileFaceNet（转 RKNN 部署）
- 方案 B：瑞芯微官方人脸识别 SDK（如有提供）
- 方案 C：使用 InsightFace 轻量模型转 RKNN

### 问题 4：NFC 技术细节不足

**问题**：未说明 PN532 的 UART 波特率、通信协议、libnfc 使用方式。

**建议补充**：UART 波特率 115200，可使用 `pyserial` 直接发送 PN532 命令帧，或移植 `libnfc` 库。

---

## 八、代码规范与提交规范

### 8.1 代码风格

- **Python**：PEP 8，4 空格缩进，函数注释使用 docstring
- **C/C++**：Linux 内核编码风格（缩进使用 Tab）
- **PyQt5**：遵循 Qt 官方命名规范（类名大写开头，变量小写开头）

### 8.2 Git 提交规范（参考 SDK 惯例）

```
#编号 : 模块 : 具体描述

示例：
#001 : ai_model : add YOLO26 tool detection model, INT8 quantized
#002 : qt_ui : implement main dashboard with five-zone status display
#003 : gpio_ctrl : add electromagnetic lock and relay control driver
```

### 8.3 项目目录建议

```
project/
├── ai_model/               # AI 模型相关
│   ├── dataset/            # 数据集
│   ├── training/           # 训练脚本
│   ├── conversion/         # RKNN 转换脚本
│   └── board_inference/    # 板端推理代码
├── qt_app/                 # PyQt5 应用程序
│   ├── src/                # Python 源码
│   ├── ui/                 # 界面文件（.ui 或纯代码布局）
│   └── resources/          # 资源文件
├── drivers/                # 硬件驱动/控制
│   ├── gpio_control.py     # GPIO 控制
│   ├── i2c_sht30.py        # SHT30 温湿度
│   ├── uart_pn532.py       # PN532 NFC
│   └── camera_capture.py   # 摄像头采集
├── database/               # 数据库
│   ├── schema.sql          # 表结构
│   └── db_manager.py       # 数据库管理
├── docs/                   # 项目文档
│   └── ...
└── tests/                  # 测试脚本
    └── ...
```

---

## 九、常用命令速查

### 9.1 开发板常用命令

```bash
# 查看系统信息
cat /proc/version
uname -a
cat /etc/issue

# 查看 NPU 版本
cat /sys/class/rknpu/version

# 网络配置
ifconfig eth0 192.168.0.233
udhcpc -i eth0

# WiFi 连接
cmddemo_wifi.sh -i wlP4p65s0 -s <SSID> -p <PASSWORD>

# 蓝牙配对
bluetoothctl

# GPIO 测试（sysfs）
echo 10 > /sys/class/gpio/export
echo out > /sys/class/gpio/gpio10/direction
echo 1 > /sys/class/gpio/gpio10/value

# I2C 扫描
i2cdetect -y 4

# 摄像头测试
gst-launch-1.0 v4l2src device=/dev/video-camera0 ! videoconvert ! autovideosink

# NPU 推理测试（使用 MPP 测试工具）
mpi_dec_test -t 7 -i test.h265 -w 1920 -h 1080
```

### 9.2 SDK 编译命令

```bash
# 一键全编译
./build.sh

# 单独编译
./build.sh kernel
./build.sh uboot
./build.sh rootfs
./build.sh updateimg

# 清理
./build.sh cleanall
```

### 9.3 RKNN 转换命令

```python
from rknn.api import RKNN

rknn = RKNN()
rknn.load_onnx(model='yolov26.onnx')
rknn.build(do_quantization=True, target_platform='rk3588')
rknn.export_rknn('yolov26_tools.rknn')
```

---

## 十、技术支持与社区资源

| 渠道 | 链接/联系方式 |
|------|--------------|
| 飞凌官网 | www.forlinx.com / www.elfboard.com |
| 技术论坛 | bbs.elfboard.com |
| 技术支持电话 | 0312-3102665 |
| QQ 交流群 | 474552704 |
| RKNN 官方仓库 | https://github.com/airockchip/rknn-toolkit2 |
| YOLO26 官方文档 | https://docs.ultralytics.com/ |

---

## 十一、文件变更记录

| 日期 | 变更内容 |
|------|---------|
| 2026-05-15 | 生成根目录 AGENTS.md，整合项目需求与官方资料包 |

---

> **提示**：本 AGENTS.md 面向 AI 编程助手，旨在建立项目开发的全局上下文。具体的技术细节（如寄存器定义、API 接口）请参考对应的官方文档和代码注释。所有基于源码的修改、构建和调试均需先合并解压 `02-Linux源代码/` 中的压缩包。
