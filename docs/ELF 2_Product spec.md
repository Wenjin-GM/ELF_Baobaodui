# ELF 2 开发板产品规格书

> **产品型号**：ELF 2（嵌入式学习型开发板）  
> **主控芯片**：Rockchip RK3588  
> **版本日期**：2026/04/09  
> **厂商**：飞凌嵌入式（Forlinx Embedded）  
> **官网**：www.forlinx.com / www.elfboard.com

---

## 一、产品概述

ELF 2 是飞凌嵌入式（Forlinx）推出的一款基于瑞芯微 **RK3588** 高性能 AIoT 处理器的嵌入式学习型开发板。采用 8nm 先进制程，集成四核 Cortex-A76 + 四核 Cortex-A55 八核 CPU、6 TOPS 算力 NPU、Mali-G610 MP4 GPU，支持 8K 视频编解码，面向 AI 边缘计算、工业控制、多媒体处理、嵌入式学习等应用场景。

开发板采用 **核心板 + 底板** 的模块化设计，核心板尺寸仅 **50mm × 68mm**，通过 4×100pin 板对板连接器与底板连接，方便用户进行二次开发和产品化定制。

---

## 二、核心硬件参数

### 2.1 处理器（SoC）

| 参数 | 规格 |
|------|------|
| **型号** | Rockchip RK3588 |
| **制程** | 8nm |
| **CPU** | 八核 64 位，4×Cortex-A76 @ 2.4GHz + 4×Cortex-A55 @ 1.8GHz |
| **NPU** | 6 TOPS 算力，三核架构，支持 INT4/INT8/INT16/FP16 |
| **GPU** | Mali-G610 MP4，支持 OpenGL ES 1.1/2.0/3.2，OpenCL 2.2，Vulkan 1.2 |
| **VPU 解码** | H.265/VP9/AVS2 最高 8K@60fps；H.264 最高 8K@30fps；AV1 最高 4K@60fps；JPEG 1920×1088@200fps |
| **VPU 编码** | H.265/H.264 最高 8K@30fps；VP8 1920×1088@30fps |

### 2.2 内存与存储

| 参数 | 规格 |
|------|------|
| **RAM** | 4GB / 8GB LPDDR4（可选） |
| **ROM** | 32GB / 64GB eMMC（可选） |
| **扩展存储** | TF Card（SDR104，最高 150MHz） |

### 2.3 机械规格

| 参数 | 规格 |
|------|------|
| **核心板尺寸** | 50mm × 68mm |
| **底板尺寸** | 120mm × 75mm |
| **核心板连接器** | 4×100pin，0.4mm 间距，1.5mm 高度 |
| **GPIO 扩展** | 40pin 兼容树莓派 GPIO 排针 |

### 2.4 电源

| 参数 | 规格 |
|------|------|
| **供电方式** | DC 12V（5.5×2.1mm 电源插座） |
| **Type-C PD** | 支持 USB PD 供电（CH224 PD 受电控制器 + FUSB302B 协议芯片） |
| **峰值功耗** | ≤ 18W（整机） |

---

## 三、接口规格详表

### 3.1 显示接口

| 接口 | 数量 | 规格 |
|------|------|------|
| **MIPI DSI** | 1 路 | 4-lane，最高 4K@60Hz；支持 7 寸 MIPI 屏（1024×600@30fps） |
| **HDMI TX** | 1 路 | HDMI 2.1，最高 7680×4320@60Hz（8K@60fps），支持 HDCP 2.3 |
| **eDP** | 1 路 | 最高 4K@60Hz，支持 1.62/2.7/5.4Gbps，HDCP 1.3 |
| **DP TX** | 1 路 | DisplayPort 1.4a，最高 7680×4320@30Hz（8K@30fps），支持 USB Type-C DP Alt Mode |
| **MIPI DCPHY** | 2 组 | 支持 MIPI DSI / MIPI CSI 复用 |

### 3.2 摄像头接口

| 接口 | 数量 | 规格 |
|------|------|------|
| **MIPI CSI DPHY** | 2 路 | MIPI DPHY V2.0，4-lane，每 lane 4.5Gbps，26Pin FPC 连接器；默认配套 OV13855（1300万像素） |
| **MIPI CSI DPHY** | 1 路 | MIPI DPHY V1.2，2-lane，每 lane 2.5Gbps，15Pin FPC 连接器 |
| **DVP** | 1 路 | 8/10/12/16-bit，最高 150MHz，支持 BT.601/BT.656/BT.1120 |

### 3.3 音频接口

| 接口 | 数量 | 规格 |
|------|------|------|
| **I2S** | 4 路 | TDM 模式，支持 I2C 配置 |
| **SPDIF** | 1 路 | IEC60958-1 / AES-3 格式 |
| **PDM** | 2 路 | 8 通道，16~24bit，最高 192KHz |
| **DSM PWM** | 1 路 | PCM 转 1bit PWM 输出 |
| **板载音频** | 1 组 | NAU88C22YG 音频编解码器，支持 MIC 输入、Speaker 输出、耳机输出 |

### 3.4 网络与通信

| 接口 | 数量 | 规格 |
|------|------|------|
| **千兆以太网** | 1 路 | RJ45，RTL8211FS PHY，支持 10/100/1000 Mbps，RGMII/RMII 接口 |
| **WiFi & 蓝牙** | 1 组 | M.2 E-KEY 插槽，默认支持 Intel AX200NGW（WiFi 6 + BT 5.2），通过 PCIe 2.0 或 USB 2.0 连接 |

### 3.5 USB 接口

| 接口 | 数量 | 规格 |
|------|------|------|
| **USB 3.1 Gen1 OTG** | 1 路 | Type-C，5Gbps，支持 DP Alt Mode，可作为 Device/Host |
| **USB 3.0 Host** | 1 路 | Type-A |
| **USB 2.0 Host** | 2 路 | Type-A，通过 FE1.1s USB HUB 扩展，支持 480/12/1.5 Mbps |

### 3.6 高速扩展接口

| 接口 | 数量 | 规格 |
|------|------|------|
| **PCIe 3.0** | 1 路 | 最高 8Gbps，支持 RC/EP 模式，可配置为 1×4、2×2、1×2+2×1、2×1+1×2 等 |
| **PCIe 2.0** | 2 路 | 每路 1-lane，5Gbps；M.2 M-KEY 2280（接 NVMe SSD）、M.2 E-KEY（接 WiFi） |
| **SATA 3.0** | 3 路 | 通过 PCIe 2.0 / USB_HOST2 / PIPE PHY 复用，支持 eSATA，6Gbps |

### 3.7 低速外设接口

| 接口 | 数量 | 规格 |
|------|------|------|
| **UART** | 10 路 | 5 路支持 64 字节 FIFO，最高 4Mbps；其中 UART9 引出至 40Pin |
| **I2C** | 9 路 | 支持标准模式（100kHz）和快速模式（400kHz）；I2C4、I2C7 引出至 40Pin |
| **SPI** | 5 路 | SPI4 引出至 40Pin |
| **PWM** | 16 路 | 其中 PWM2、PWM4 引出至 20Pin |
| **ADC** | 8 路 | 12bit SAR-ADC，1MS/s 采样率；其中 4 路引出至 20Pin |
| **SDMMC** | 1 路 | 支持 SD/MMC V4.51 |
| **SDIO** | 1 路 | SDIO 3.0 |

### 3.8 其他接口

| 接口 | 数量 | 规格 |
|------|------|------|
| **Debug UART** | 1 路 | Type-C 接口，CP2102N USB 转 UART 桥接，波特率 115200 |
| **RTC** | 1 路 | RX8010SJ 实时时钟芯片，板载纽扣电池座 |
| **TF Card** | 1 路 | Micro SD，支持 SDR104 模式，150MHz |
| **40Pin GPIO** | 1 组 | 兼容树莓派 40Pin，支持 GPIO/SPI/I2C/UART，含 5V/3.3V 电源 |
| **20Pin GPIO** | 1 组 | 支持 GPIO/ADC/PWM，含 5V/3.3V 电源 |

---

## 四、软件支持

### 4.1 操作系统

| 系统 | 版本 | 说明 |
|------|------|------|
| **Linux** | 5.10.209 | 飞凌定制分支（ELF2），长期维护 |
| **Ubuntu / Debian Desktop** | 22.04 (Jammy) | 带 Xfce 桌面环境，预装 Wayland/Weston |
| **Buildroot** | 202x.x | 精简嵌入式 Linux，启动速度快 |
| **Yocto** | - | 支持自定义构建 |

### 4.2 AI 与多媒体软件栈

| 组件 | 版本/说明 |
|------|----------|
| **NPU 驱动** | RKNPU 0.9.8 |
| **RKNN-Toolkit2** | v1.6.0（PC端模型转换） |
| **RKNN-Toolkit-Lite2** | v2.3.2（板端推理） |
| **MPP** | Rockchip 多媒体处理平台（视频编解码中间件） |
| **GStreamer** | 带 Rockchip 硬件加速插件 |
| **RKAIQ** | V5.x，ISP 3A 算法（自动曝光/白平衡/对焦） |
| **Qt** | Qt 5.15.10（GPU 硬件加速渲染） |

---

## 五、产品型号配置

| 型号 | CPU | RAM | ROM | 说明 |
|------|-----|-----|-----|------|
| ELF2+244GSE32GCCxxxxx:xx | 4×A76+4×A55 | 4GB | 32GB | 标准配置 |
| ELF2+248GSE64GCCxxxxx:xx | 4×A76+4×A55 | 8GB | 64GB | 高配配置 |

> **命名规则**：ELF2 + [RAM][ROM][功能配置][版本]

---

## 六、物理尺寸与结构

### 6.1 核心板尺寸

```
         68mm
    ┌─────────────┐
    │             │
    │   RK3588    │  50mm
    │   核心板    │
    │             │
    └─────────────┘
      4×100pin B2B
```

### 6.2 底板尺寸

```
         120mm
    ┌─────────────────┐
    │  [接口布局区域]  │
    │                 │  75mm
    │   核心板插槽    │
    │                 │
    └─────────────────┘
```

### 6.3 结构资料

开发板配套亚克力外壳结构件，详见 `05-结构资料/`：
- 2D 加工图纸（DXF/PDF）
- 3D 装配模型（STEP）

---

## 七、订购信息

### 7.1 标准配件清单

| 配件 | 数量 | 说明 |
|------|------|------|
| ELF 2 开发板（核心板+底板） | 1 块 | 根据型号配置 RAM/ROM |
| 12V/3A 电源适配器 | 1 个 | DC 5.5×2.1mm |
| Type-C 数据线 | 1 条 | USB 3.1 Gen1，用于调试/烧录 |
| USB 转 Type-A 线 | 1 条 | USB 2.0，1m |
| 散热片/导热垫 | 1 套 | 核心板散热 |
| M3×10mm 铜柱 | 4 根 | 固定用 |
| M3×6mm 螺丝 | 4 颗 | GB/T818-2016 |
| 快速使用手册 | 1 份 | 纸质/电子版 |

### 7.2 可选配件

| 配件 | 接口 | 说明 |
|------|------|------|
| WiFi & 蓝牙模块 | M.2 E-KEY | Intel AX200NGW 或兼容模块 |
| 7 寸 MIPI 显示屏 | MIPI DSI | LCD070CM+，1024×600 分辨率 |
| MIPI 摄像头 | MIPI CSI | OV13855，1300 万像素 |
| 光照传感器 | I2C | GY-30（BH1750） |
| 六轴传感器 | I2C | MPU-6050（加速度+陀螺仪） |
| 语音识别模块 | UART | LD3320 |
| 32GB TF 卡 | TF Card | Class 10，120MB/s |
| USB 读卡器 | USB 3.0 | 支持 SD/TF 卡 |
| 散热风扇 | 20×20×6mm | 5V 有源风扇 |

---

## 八、技术支持

| 渠道 | 联系方式 |
|------|---------|
| **官方网站** | www.forlinx.com / www.elfboard.com |
| **技术论坛** | bbs.elfboard.com |
| **技术支持电话** | 0312-3102665 |
| **QQ 交流群** | 474552704 |

---

## 九、相关文档索引

| 需求 | 路径 |
|------|------|
| 快速使用手册 | `01-教程文档/ELF 2开发板快速使用手册/ELF 2开发板快速使用手册.pdf` |
| Linux SDK 源码 | `02-Linux源代码/ELF2-linux-source.tar.bz2.0*` |
| 硬件原理图 | `04-硬件资料/ELF 2 V1.2_硬件资料/00-PDF原理图/ELF 2 V1.2原理图.PDF` |
| 引脚分配表 | `04-硬件资料/04-管脚分配表/ELF 2引脚复用表20250603.xlsx` |
| 结构件图纸 | `05-结构资料/` |
| RK3588 TRM | `07-RK原厂资料/Rockchip RK3588 TRM V1.0-Part1/Part2.pdf` |
| RK 软件开发指南 | `07-RK原厂资料/cn/Rockchip_Developer_Guide_Linux_Software_CN.pdf` |

---

> **版权声明**：Copyright © 2007-2026 Forlinx Embedded Technology Co. Ltd. All Rights Reserved.
