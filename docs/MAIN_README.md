# 智能安全工具柜 - 主程序说明

## 版本信息
- **版本**: V1.0
- **日期**: 2026-06-23
- **状态**: 基础集成版本

## 功能特性

### ✅ 已实现
1. **NFC身份认证** - PN532读卡器，I2C7总线
2. **温湿度监测** - SHT30传感器，I2C4总线
3. **环境自动调控** - 温度/湿度超限自动启动风扇
4. **电磁锁控制** - GPIO继电器，支持定时开门
5. **状态机架构** - 7种系统状态自动转换
6. **日志系统** - 文件和控制台双输出
7. **异常处理** - 完整的错误捕获和资源释放

### 🔶 部分实现
8. **人脸识别** - 接口预留，待集成

### ❌ 待实现
9. **AI视觉识别** - 五区工具检测
10. **SQLite数据库** - 操作记录存储
11. **PyQt5界面** - 图形化显示

## 系统架构

```
┌─────────────────────────────────────────┐
│          ToolCabinetController          │
│            (主控制器)                    │
└──────────────┬──────────────────────────┘
               │
    ┌──────────┼──────────┬──────────┐
    ▼          ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│  NFC   │ │ 温湿度  │ │继电器  │ │  认证  │
│ Reader │ │ Sensor │ │Controller│ │Manager│
└────────┘ └────────┘ └────────┘ └────────┘
```

## 状态机流程

```
IDLE (待机)
  ├─ 检测NFC卡
  └─ 监测环境
       ↓ 刷卡
AUTHENTICATING (认证中)
  ├─ 验证卡号
  └─ 查询授权
       ↓ 成功
AUTHORIZED (已授权)
  └─ 开启电磁锁
       ↓
OPERATING (操作中)
  └─ 等待用户存取工具
       ↓ 关门
MONITORING (监测中)
  └─ 盘点工具状态
       ↓
IDLE (待机)
```

## 运行说明

### 前置要求
```bash
# 确保硬件连接正确
# - PN532 NFC -> I2C7, 地址0x24
# - SHT30 传感器 -> I2C4, 地址0x44
# - 电磁锁 -> GPIO3 line 12 (Pin13)
# - 风扇 -> GPIO3 line 2 (Pin15)

# 安装依赖
pip install smbus2 gpiod
```

### 启动系统
```bash
# 进入工作目录
cd ~/smart_tool_cabinet

# 运行主程序（需要root权限）
sudo python3 main.py
```

### 停止系统
```bash
# 按 Ctrl+C 安全退出
# 或发送SIGTERM信号
sudo kill -15 <PID>
```

## 配置说明

### 硬件配置（main.py 顶部）
```python
# I2C总线
I2C_BUS_NFC = 4        # NFC读卡器 (I2C4 一主多从: PN532 0x24 + SHT30 0x44)
I2C_BUS_SHT30 = 4      # 温湿度传感器 (I2C4 一主多从)

# GPIO引脚
GPIO_CHIP = "gpiochip3"
GPIO_LOCK_LINE = 12    # 电磁锁
GPIO_FAN_LINE = 2      # 风扇

# 环境阈值
TEMP_MIN = 5.0         # 最低温度
TEMP_MAX = 40.0        # 最高温度
HUMIDITY_MAX = 60.0    # 最高湿度

# 门锁时间
LOCK_OPEN_TIME = 5.0   # 开门时长(秒)
```

### 授权卡管理
编辑 `authorized_cards.json`:
```json
{
  "cards": {
    "A1B2C3D4": {
      "name": "my_card",
      "enrolled_at": "2026-05-28 01:23:56"
    }
  }
}
```

## 日志文件

- **日志路径**: `tool_cabinet.log`
- **日志级别**: INFO
- **日志格式**: `2026-06-23 15:30:45 [INFO] 消息内容`

## 测试说明

### 测试1：NFC认证
1. 启动主程序
2. 使用授权卡刷卡
3. 观察日志：应显示"认证成功"并开门

### 测试2：温湿度监测
1. 观察日志中的温湿度读数
2. 对传感器加热或加湿
3. 观察风扇是否自动启动

### 测试3：电磁锁控制
1. 认证成功后
2. 听到继电器"咔"一声
3. 5秒后自动关闭

## 常见问题

### Q1: 提示"需要root权限"
```bash
# 必须使用sudo运行
sudo python3 main.py
```

### Q2: "Cannot import PN532 driver"
```bash
# 确保在smart_tool_cabinet目录下运行
cd ~/smart_tool_cabinet
sudo python3 main.py
```

### Q3: I2C设备找不到
```bash
# 检查I2C设备
ls /dev/i2c-*

# 扫描I2C总线
sudo i2cdetect -y 4  # SHT30
sudo i2cdetect -y 7  # PN532
```

### Q4: GPIO无法控制
```bash
# 检查GPIO状态
gpioinfo | grep gpiochip3

# 确认引脚未被占用
```

## 下一步开发计划

1. **添加SQLite数据库** - 存储操作记录
2. **集成人脸识别** - 双模式认证
3. **开发PyQt5界面** - 可视化显示
4. **集成YOLO视觉** - 五区工具检测
5. **充电控制** - 8路智能充电管理

## 技术支持

- **开发指南**: `DEVELOPER_GUIDE.md`
- **硬件规格**: `ELF 2_Product spec.md`
- **NFC测试**: `NFC_I2C测试指南.md`

---

**宝宝队** - 电网运维智能安全工具柜系统
