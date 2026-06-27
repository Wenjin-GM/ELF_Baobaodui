## NFC调试指南 - V1.1.1

### 已添加的调试功能

1. **日志级别改为DEBUG** - 显示所有详细信息
2. **NFC线程心跳日志** - 每100次循环输出一次，确认线程在工作
3. **详细错误堆栈** - 如果出错会显示完整堆栈信息
4. **卡片检测日志改为INFO** - 检测到卡立即显示

### 重启程序步骤

**在串口终端（PuTTY）执行：**

```bash
# 1. 停止当前程序（按Ctrl+C）

# 2. 清理旧日志（可选）
rm ~/smart_tool_cabinet/tool_cabinet.log

# 3. 重新启动
cd ~/smart_tool_cabinet
sudo python3 main.py
```

### 观察启动日志

应该看到：
```
[INFO] NFC读卡器初始化成功 (I2C4, 0x24)
[INFO] NFC轮询线程开始工作
[INFO] NFC后台轮询线程已启动
[DEBUG] [NFC线程] 心跳检查 - 循环次数: 100  ← 约1分钟后出现
```

### 刷卡测试

**任意卡片靠近PN532**，应该立即看到：
```
[INFO] [NFC线程] 检测到卡片: XXXXXXXX  ← 后台线程
[INFO] 检测到NFC卡: XXXXXXXX            ← 主线程
```

如果是授权卡（示例 UID: A1B2C3D4）：
```
[INFO] 认证成功: my_card (NFC)
[INFO] 开启电磁锁 5.0 秒
```

如果是未授权卡：
```
[WARNING] 认证失败: 卡号 XXXXXXXX 未授权
```

### 如果仍然无反应

#### 检查1：确认NFC线程在工作
```bash
# 在另一个SSH窗口查看日志
tail -f ~/smart_tool_cabinet/tool_cabinet.log | grep "心跳"
```

应该每60秒左右看到一次心跳日志。

#### 检查2：手动测试PN532
```bash
cd ~/smart_tool_cabinet
sudo python3 -c "
from PN532.drivers.i2c_pn532 import PN532_I2C
import time

nfc = PN532_I2C(bus=4, address=0x24)
nfc.begin()
print('PN532已初始化，等待刷卡...')

for i in range(10):
    uid = nfc.read_passive_target_id(timeout=1.0)
    if uid:
        uid_str = ''.join(f'{b:02X}' for b in uid)
        print(f'检测到卡片: {uid_str}')
        break
    print(f'尝试 {i+1}/10...')
    time.sleep(0.5)
else:
    print('未检测到卡片')
"
```

**刷卡时这个脚本应该能检测到。**

#### 检查3：查看错误日志
```bash
grep "ERROR\|Exception\|Traceback" ~/smart_tool_cabinet/tool_cabinet.log
```

#### 检查4：PN532硬件
- 拨码开关：1=OFF, 2=OFF (I2C模式)
- 电源指示灯是否亮
- 卡片距离：贴近PN532天线（<5cm）

### 可能的问题

| 现象 | 原因 | 解决方案 |
|------|------|----------|
| 无心跳日志 | 线程崩溃 | 查看ERROR日志 |
| 有心跳，无卡片检测 | PN532无法读卡 | 手动测试PN532 |
| 能手动检测，程序不行 | 代码逻辑问题 | 检查日志详细信息 |

---

**请先重启程序，然后告诉我日志输出！**
