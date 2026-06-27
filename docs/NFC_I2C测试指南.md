# PN532 I2C 测试完整指南

> **适用硬件**：Elechouse PN532 V3（I2C 模式）+ 飞凌 ELF 2（RK3588）  
> **测试环境**：RK3588 Ubuntu 22.04  
> **文件位置**：本项目 `PN532/drivers/`、`PN532/tests/` 目录下

---

## 一、硬件接线

### 1.1 PN532 → RK3588 ELF 2（40Pin 排针）

用你手头的 **4 根母对母杜邦线** 连接：

| PN532 右侧排针 | RK3588 40Pin | 颜色建议 |
|---------------|-------------|---------|
| **GND** | Pin 6 (GND) | 黑色 |
| **VCC** | Pin 1 (3.3V) | 红色 |
| **SDA** | Pin 3 (I2C4_SDA) | 白色/灰色 |
| **SCL** | Pin 5 (I2C4_SCL) | 灰色/白色 |

> ⚠️ **重要**：VCC 必须接 **3.3V**（Pin 1），千万别接 5V！

### 1.2 接线示意图

```
    PN532 V3 (Top View)
    ┌─────────────────┐
    │    [Antenna]    │
    │                 │
    │  SCL ○          │  ←── 灰色 ──→ RK3588 Pin 5 (I2C4_SCL)
    │  SDA ○          │  ←── 白色 ──→ RK3588 Pin 3 (I2C4_SDA)
    │  VCC ○          │  ←── 红色 ──→ RK3588 Pin 1 (3.3V)
    │  GND ○          │  ←── 黑色 ──→ RK3588 Pin 6 (GND)
    └─────────────────┘
```

### 1.3 RK3588 40Pin 引脚图（ relevant pins ）

```
 3.3V  (Pin 1)  ●────●  (Pin 2)  5V      ← 千万别接这里！
 SDA   (Pin 3)  ●────●  (Pin 4)  5V
 SCL   (Pin 5)  ●────●  (Pin 6)  GND
               ...
```

---

## 二、软件环境准备

### 2.1 安装 smbus2 库

SSH 登录 RK3588，执行：

```bash
# 安装 smbus2（如果还没装）
pip3 install smbus2

# 或者用 apt（如果可用）
sudo apt-get install -y python3-smbus2
```

### 2.2 验证 I2C 总线

```bash
# 查看可用的 I2C 设备
ls /dev/i2c-*

# 应该能看到 /dev/i2c-4
# 如果没有，检查设备树是否启用了 I2C4
```

### 2.3 扫描 I2C 设备（确认 PN532 在线）

```bash
sudo i2cdetect -y 4
```

**期望输出**（能看到 `24`）：

```
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:          -- -- -- -- -- -- -- -- -- -- -- -- --
10: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
20: -- -- -- -- 24 -- -- -- -- -- -- -- -- -- -- --  ← ✅ PN532 at 0x24
30: -- -- -- -- 44 -- -- -- -- -- -- -- -- -- -- --  ← SHT30 at 0x44 (如有)
```

如果看不到 `24`：
- 检查接线（SDA/SCL 是否接反）
- 检查 VCC 是否为 3.3V
- 检查杜邦线是否接触不良
- 确认模块上电（有些模块需要等几秒）

### 2.4 确认拨码开关（关键！）

Elechouse PN532 V3 左上角的 **4 位拨码开关** 决定模块工作模式：

| 开关 | 功能 | I2C 模式 |
|-----|------|---------|
| **1** | SCL / TX | **OFF** |
| **2** | SDA / RX | **OFF** |
| 3 | 地址 Bit0 | OFF（地址=0x24）|
| 4 | 保留 | OFF |

> ⚠️ **铁律**：开关 **1 和 2 必须都是 OFF**。只要有一个是 ON，模块就工作在 UART 模式——此时 `i2cdetect` 能扫到地址，但 Python 驱动通信一定超时！
>
> 调完拨码开关后务必**断电 5 秒重新上电**，模块只在启动时读取拨码开关状态。

---

## 三、运行测试

### 3.1 基础测试（推荐首次运行）

```bash
cd ~/smart_tool_cabinet/PN532
sudo python3 tests/test_nfc_basic.py
```

**测试内容**：
1. PN532 通信检测（读固件版本）
2. SAM 配置
3. 刷卡检测（等待你把卡放上去，读 UID）

**期望输出**：
```
==================================================
PN532 I2C Basic Test
==================================================

[INIT] Initializing PN532...
[INFO] PN532 detected: IC=0x32, Firmware v1.6, Support=0x07
[INFO] PN532 initialized successfully.

[TEST 1] Reading firmware version...
  ✓ IC Version: 0x32
  ✓ Firmware:   v1.6
  ✓ Support:    0x07

[TEST 2] Configuring SAM...
  ✓ SAM configured successfully

[TEST 3] Polling for NFC card...
  → Place your card/keyfob on the PN532 antenna
  → Waiting up to 10 seconds...
  ✓ Card detected!
  ✓ UID: A1 B2 C3 D4 (len=4)

==================================================
Test Summary
==================================================
  [PASS] Firmware Version
  [PASS] SAM Configuration
  [PASS] Card Detection
==================================================
✓ All tests passed! PN532 is working correctly.
==================================================
```

### 3.2 M1 卡高级测试（认证 + 读写）

用你手上的 **M1 卡** 或 **空白卡** 测试读写功能：

```bash
cd ~/smart_tool_cabinet/PN532
sudo python3 tests/test_nfc_m1card.py
```

**测试内容**：
1. 检测卡片并读 UID
2. 用默认密钥 `FF FF FF FF FF FF` 认证扇区 0
3. 读取扇区 0 的 3 个数据块
4. 写入测试数据到 Block 1，读回验证，然后恢复原数据
5. 模拟项目认证流程（读 UID → 查授权列表）

> ⚠️ **注意**：此测试会短暂改写 Block 1 数据，测试结束后会自动恢复。请用空白卡测试，不要刷重要卡片。
>
> 实际测试输出示例（UID 已脱敏为 `A1B2C3D4`）：
> ```
> [PASS] Card Detection
> [PASS] Authentication
> [PASS] Block Reading
> [PASS] Write/Verify
> [PASS] Auth Simulation
> ✓ All tests passed!
> ```

---

## 四、常见问题排查

### Q1: `i2cdetect` 扫不到 `0x24`

| 可能原因 | 解决方法 |
|---------|---------|
| SDA/SCL 接反 | 交换这两根线 |
| VCC 接成 5V | 改接到 Pin 1 (3.3V) |
| GND 没接好 | 检查黑色杜邦线 |
| 模块没上电 | 观察模块上是否有 LED 亮起 |
| I2C4 没启用 | `sudo apt-get install i2c-tools` 后重试 |
| 杜邦线接触不良 | 重新插紧或换线测试 |

### Q2: 能读到固件版本，但检测不到卡片

- 卡片要**紧贴**天线区域（白色方形区域正上方）
- M1 卡和空白卡都试试
- 卡片离天线距离不要超过 2cm
- 检查卡片是否为 Mifare Classic 1K（UID 4 字节）

### Q3: 认证失败（M1 卡测试）

- 卡片可能使用了非默认密钥（不是 `FF FF FF FF FF FF`）
- 尝试用你手头的另一张卡
- 空白卡通常是默认密钥，可以试试

### Q4: 权限错误 `/dev/i2c-4 Permission denied`

```bash
# 临时方案：sudo 运行
cd ~/smart_tool_cabinet/PN532
sudo python3 tests/test_nfc_basic.py

# 永久方案：将当前用户加入 i2c 组
sudo usermod -aG i2c $USER
# 然后重新登录或 reboot
```

### Q5: `i2cdetect` 能扫到 `0x24`，但脚本报 `Cannot communicate with PN532`

这是最常见的坑，原因通常是以下之一：

| 可能原因 | 排查方法 |
|---------|---------|
| **拨码开关不是 I2C 模式** | 确认开关 1=OFF、2=OFF，调完断电重上电 |
| **I2C 权限不足** | 用 `sudo` 运行脚本，或加入 i2c 组 |
| **smbus2 未安装（root 环境）** | `sudo pip3 install smbus2` |
| **PN532 处于 Power Down** | 驱动已内置唤醒序列，如仍失败断电 10 秒再试 |
| **SDA/SCL 接反** | 交换两根线试试 |

> 调试命令：`sudo python3 tests/debug_pn532.py`（会打印原始 I2C 收发数据）

---

## 五、项目集成

### 5.1 替换原来的 UART 驱动

你原来的项目设计是 `uart_pn532.py`（串口），现在需要替换为 `PN532/drivers/i2c_pn532.py`（I2C）。

**修改前后的接口对比**：

| 功能 | 原来 (UART) | 现在 (I2C) |
|------|------------|-----------|
| 初始化 | `serial.Serial('/dev/ttyS9', 115200)` | `PN532_I2C(bus=4)` |
| 读卡号 | 自定义串口协议 | `nfc.read_passive_target_id()` |
| 认证 | 自定义实现 | `nfc.mifare_authenticate_block(...)` |

### 5.2 项目身份认证模块示例

在 `PN532/` 目录内使用时：

```python
from drivers.i2c_pn532 import PN532_I2C

class NFCAuth:
    def __init__(self, authorized_uids=None):
        self.nfc = PN532_I2C(bus=4)
        self.nfc.begin()
        self.authorized_uids = authorized_uids or set()
    
    def poll_and_auth(self, timeout=5.0):
        """Poll for card and check authorization."""
        uid = self.nfc.read_passive_target_id(timeout=timeout)
        if uid is None:
            return None, False
        
        uid_str = ''.join(f'{b:02X}' for b in uid)
        is_auth = uid_str in self.authorized_uids
        return uid_str, is_auth

# 使用
auth = NFCAuth(authorized_uids={"A1B2C3D4", "12345678"})
uid, allowed = auth.poll_and_auth()
if allowed:
    print(f"Authorized user: {uid}")
    # TODO: Open electromagnetic lock
```

如果在项目根目录（`smart_tool_cabinet/`）使用，import 改为：

```python
from PN532.drivers.i2c_pn532 import PN532_I2C
```

---

## 六、文件清单

| 文件 | 说明 |
|------|------|
| `PN532/drivers/i2c_pn532.py` | PN532 I2C 驱动（核心） |
| `PN532/tests/test_nfc_basic.py` | 基础通信 + 刷卡测试 |
| `PN532/tests/test_nfc_m1card.py` | M1 卡认证 + 读写测试 |
| `NFC_I2C测试指南.md` | 本文档 |

---

## 七、下一步

1. ✅ 按本指南接线并运行 `test_nfc_basic.py`
2. ✅ 如果基础测试通过，运行 `test_nfc_m1card.py`
3. ✅ 记录你的卡片 UID，加入项目授权数据库
4. ⏳ 把 `i2c_pn532.py` 集成到你的 PyQt5 主程序中

遇到问题随时发日志给我！
