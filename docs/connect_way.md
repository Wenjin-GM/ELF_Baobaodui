# 最新硬件接线说明

> 本文件记录当前宝宝队智能安全工具柜的最新版硬件接线。  
> 后续调试硬件、修改 `main.py` 引脚常量、同步主控板代码时，以本文件为准。

## 一、接线总表

| 模块 | ELF 2 接口/排针标号 | 官方/软件含义 | 外设连接 | 当前状态 |
|------|----------------------|---------------|----------|----------|
| 温湿度传感器 SHT30 | `SDA.1` | `I2C4_SDA` | SHT30 `SDA` | 已接 |
| 温湿度传感器 SHT30 | `SCL.1` | `I2C4_SCL` | SHT30 `SCL` | 已接 |
| NFC 模块 PN532 | `SDA.0` | `I2C5_I2C7_SDA` | PN532 `SDA` | 已接 |
| NFC 模块 PN532 | `SCL.0` | `I2C5_I2C7_SCL` | PN532 `SCL` | 已接 |
| 风扇控制 | `GPIO.28` | `GPIO2_D3--GPIO3_B1` | 二号继电器输入端 | 已接 |
| 门锁控制 | `GPIO.25` | `GPIO2_C1--GPIO3_A3` | 三号继电器输入端 | 已接 |
| 蜂鸣器 | `GPIO.23` | `GPIO2_C5--GPIO3_A4` | 蜂鸣器控制端 | 已接 |
| 电池充电模块 | 未连接 | 8 路充电继电器待分配 | 暂无 | 未接 |

> 电源和 GND 未在本次说明中重新定义。接线时仍需确保所有外设与开发板共地，并按模块额定电压供电。

## 二、I2C 总线说明

### SHT30 温湿度传感器

最新版接线为：

```text
ELF 2 SDA.1  -> SHT30 SDA
ELF 2 SCL.1  -> SHT30 SCL
```

按项目资料和官方引脚复用表，`SDA.1/SCL.1` 对应 `I2C4`：

```python
I2C_BUS_SHT30 = 4
I2C_ADDR_SHT30 = 0x44
```

板端验证命令：

```bash
sudo i2cdetect -y 4
```

期望能看到 `0x44`。

### PN532 NFC 模块

最新版接线为：

```text
ELF 2 SDA.0  -> PN532 SDA
ELF 2 SCL.0  -> PN532 SCL
```

当前项目文档中曾出现两种历史写法：

| 历史来源 | PN532 总线写法 |
|----------|----------------|
| `NFC_I2C测试指南.md` 和部分 PN532 测试脚本 | `I2C4` |
| `README.md`、`MAIN_README.md`、`env_nfc_relay_control.py` 早期说明 | `I2C7` |

本次硬件已改为 `SDA.0/SCL.0`，总表中标注为 `I2C5_I2C7_SDA/SCL`。结合旧项目资料中 PN532 曾按 `I2C7` 调通的记录，软件侧优先按 `I2C7` 验证；若板端扫描结果与此不一致，再检查 `I2C5`。

建议验证：

```bash
sudo i2cdetect -y 7
sudo i2cdetect -y 5
sudo i2cdetect -y 4
```

PN532 默认 I2C 地址为 `0x24`。确认在哪条总线上扫到 `0x24` 后，再同步修改代码中的 NFC 总线常量。

## 三、GPIO 与 gpiod 映射

RK3588 Linux 侧使用 `gpiod`，不要使用 `RPi.GPIO`。

根据现有项目脚本和官方引脚表，GPIO line 的换算规则可按当前 `gpiochip3` 分组理解：

```text
GPIO3_A0 -> gpiochip3 line 0
GPIO3_A3 -> gpiochip3 line 3
GPIO3_A4 -> gpiochip3 line 4
GPIO3_B1 -> gpiochip3 line 9
```

### 当前控制映射

| 功能 | 接线标号 | 芯片复用名 | Linux 建议映射 | 触发逻辑 |
|------|----------|------------|----------------|----------|
| 风扇 | `GPIO.28` | `GPIO2_D3--GPIO3_B1` | `gpiochip3 line 9` | 继电器通常低电平有效 |
| 门锁 | `GPIO.25` | `GPIO2_C1--GPIO3_A3` | `gpiochip3 line 3` | 继电器通常低电平有效 |
| 蜂鸣器 | `GPIO.23` | `GPIO2_C5--GPIO3_A4` | `gpiochip3 line 4` | 高电平触发：`1` 响，`0` 静音 |

蜂鸣器说明：`workspace/charging/test_buzzer.py` 仍是旧测试脚本，现有记录为 `GPIO3_B5 = gpiochip3 line 13`。最新版接线已改为 `GPIO.23 = GPIO2_C5--GPIO3_A4`，后续测试脚本需要同步改为 `gpiochip3 line 4`。

## 四、建议代码常量

确认硬件扫描结果后，`main.py` 顶部常量建议调整为：

```python
# I2C
I2C_BUS_SHT30 = 4
I2C_ADDR_SHT30 = 0x44

# PN532: 最新接线为 SDA.0/SCL.0，标注为 I2C5_I2C7，优先按 I2C7 验证
I2C_BUS_NFC = 7
I2C_ADDR_NFC = 0x24

# GPIO
GPIO_CHIP = "gpiochip3"
GPIO_FAN_LINE = 9    # GPIO.28 / GPIO3_B1 / 二号继电器 / 风扇
GPIO_LOCK_LINE = 3   # GPIO.25 / GPIO3_A3 / 三号继电器 / 门锁
GPIO_BUZZER_LINE = 4  # GPIO.23 / GPIO3_A4 / 蜂鸣器
```

注意：当前 `main.py` 仍使用旧的门锁/风扇 GPIO：

```python
GPIO_LOCK_LINE = 12
GPIO_FAN_LINE = 2
```

后续联调前需要按本文件更新。

## 五、板端验证命令

### 查看 I2C 设备

```bash
ls /dev/i2c-*
sudo i2cdetect -y 4
sudo i2cdetect -y 5
sudo i2cdetect -y 7
```

期望：

```text
SHT30 -> 0x44
PN532 -> 0x24
```

### 查看 GPIO 信息

```bash
gpioinfo gpiochip3
```

重点确认：

```text
line 3   -> GPIO3_A3 / 门锁三号继电器
line 4   -> GPIO3_A4 / 蜂鸣器
line 9   -> GPIO3_B1 / 风扇二号继电器
```

### 临时测试继电器

继电器按低电平有效处理，测试时先保持高电平安全态，再短暂拉低。

```bash
# 风扇二号继电器：GPIO.28 -> gpiochip3 line 9
sudo gpioset gpiochip3 9=1
sudo gpioset gpiochip3 9=0
sudo gpioset gpiochip3 9=1

# 门锁三号继电器：GPIO.25 -> gpiochip3 line 3
sudo gpioset gpiochip3 3=1
sudo gpioset gpiochip3 3=0
sudo gpioset gpiochip3 3=1
```

门锁测试时拉低时间应尽量短，避免长时间通电。

### 临时测试蜂鸣器

蜂鸣器已实测为高电平触发。短时测试命令如下：

```bash
# 蜂鸣器：GPIO.23 -> gpiochip3 line 4
sudo gpioset gpiochip3 4=0
sudo gpioset gpiochip3 4=1
sudo gpioset gpiochip3 4=0
```

## 六、旧资料冲突记录

以下旧信息已不再作为最新接线依据：

| 文件 | 旧说法 | 最新修正 |
|------|--------|----------|
| `README.md` | PN532 为 `I2C7`，电磁锁 Pin13，风扇 Pin15 | PN532 接 `SDA.0/SCL.0`；门锁为 `GPIO.25` 三号继电器；风扇为 `GPIO.28` 二号继电器 |
| `MAIN_README.md` | 电磁锁 `gpiochip3 line 12`，风扇 `gpiochip3 line 2` | 门锁 `gpiochip3 line 3`，风扇 `gpiochip3 line 9` |
| `env_nfc_relay_control.py` 注释 | SHT30 `I2C4`，PN532 `I2C7`，Pin13/Pin15 继电器 | 需按本文件更新后再作为集成脚本使用 |
| `NFC_I2C测试指南.md` | PN532 接 `I2C4` | 最新接线为 `SDA.0/SCL.0`，优先按 `I2C7` 扫描确认 |
| `charging/test_buzzer.py` | 蜂鸣器 `gpiochip3 line 13` | 最新接线为 `GPIO.23 = GPIO3_A4 = gpiochip3 line 4` |

## 七、待确认项

1. PN532 在 `SDA.0/SCL.0` 接线下最终出现于 `/dev/i2c-7` 还是 `/dev/i2c-5`。
2. 蜂鸣器已确认高电平触发：`gpiochip3 line 4 = 1` 响，`0` 静音。
3. 二号、三号继电器是否均为低电平有效；若继电器板型号变化，需要实测确认。
4. 电池充电模块尚未连接，8 路充电继电器 GPIO 暂不分配。
