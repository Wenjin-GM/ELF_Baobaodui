# 智能工具柜工作空间

> 本目录是项目主工作区，需要与主控板 `elf@10.209.164.14:~/smart_tool_cabinet/` 保持同步。  
> 本地修改完成后，应同步到主控板再做硬件联调。

## 快速同步

### 上传到主控板

```bash
# Windows
sync_to_board.bat

# Linux/Mac
rsync -avz --delete workspace/ elf@10.209.164.14:~/smart_tool_cabinet/
```

### 从主控板下载

```bash
# Windows
sync_from_board.bat

# Linux/Mac
rsync -avz --delete elf@10.209.164.14:~/smart_tool_cabinet/ workspace/
```

> 当前 Windows 批处理脚本使用 `scp -r`，不能自动删除主控板上已废弃的旧文件；需要彻底同步时优先使用 `rsync --delete`，或先清理板端旧目录后再上传。

## 当前目录结构

```text
workspace/
├── main.py                         # 主程序入口：NFC + SHT30 + 门锁/风扇状态机
├── authorized_cards.json           # 授权 NFC 卡数据库
├── README.md                       # 当前工作区说明
├── docs/                           # 所有 Markdown 说明文档
│   ├── connect_way.md              # 最新硬件接线和引脚映射
│   ├── DEVELOPER_GUIDE.md          # 旧版开发指南，作参考
│   └── ...
├── scripts/                        # 板端检查/诊断脚本
│   ├── check_system.sh             # 无 sudo 基础环境检查
│   ├── test_main.sh                # sudo 硬件连通性检查
│   └── diagnose_nfc.sh             # NFC 专项诊断
├── tools/                          # 独立调试工具
│   └── env_nfc_relay_control.py    # SHT30 + PN532 + 继电器 + 人脸调试 CLI
├── PN532/                          # PN532 NFC I2C 驱动与测试
│   ├── drivers/i2c_pn532.py
│   └── tests/
├── sht30_test/                     # SHT30/SHT31 C 测试程序
├── charging/                       # GPIO 输出硬件测试脚本
├── USB/                            # USB 摄像头与人脸识别模块
│   ├── capture_usb_camera_5.py
│   └── face_auth/
└── vision/                         # 柜内摄像头/视觉相关脚本
    └── camera/
```

## 代码和脚本说明

| 路径 | 用途 | 保留原因 |
|------|------|----------|
| `main.py` | 当前主控程序，负责 NFC 后台轮询、SHT30 读取、门锁和风扇继电器控制 | 板端主入口 |
| `authorized_cards.json` | 授权卡 UID 列表 | 主程序认证依赖 |
| `PN532/drivers/i2c_pn532.py` | PN532 I2C 协议驱动 | NFC 核心驱动 |
| `PN532/tests/*.py` | PN532 固件读取、刷卡、M1 卡读写测试 | NFC 硬件调试 |
| `sht30_test/` | SHT30/SHT31 C 驱动和测试可执行文件 | 温湿度硬件调试 |
| `charging/test_buzzer.py` | 蜂鸣器 GPIO.23 测试脚本 | 蜂鸣器硬件调试 |
| `charging/test_lock.py` | 门锁 GPIO.25 继电器脉冲测试 | 门锁硬件调试 |
| `USB/capture_usb_camera_5.py` | USB 摄像头连续拍照测试 | 柜外摄像头调试 |
| `USB/face_auth/face_recognition_core.py` | InsightFace 人脸识别核心 | 后续双模式认证集成 |
| `USB/face_auth/face_camera_gui.py` | 人脸识别 PyQt GUI 测试 | 人脸模块单独调试 |
| `USB/face_auth/check_usb_face_confidence.py` | 人脸识别置信度检查 | 阈值调试 |
| `vision/camera/board_camera_live_view.py` | 板载摄像头实时预览 | 柜内摄像头调试 |
| `vision/camera/board_capture_two_photos.py` | 双摄像头拍照测试 | 摄像头定位/采样 |
| `scripts/check_system.sh` | Python 依赖和文件检查 | 快速健康检查 |
| `scripts/test_main.sh` | I2C/GPIO/主程序语法检查 | 板端硬件测试 |
| `scripts/diagnose_nfc.sh` | NFC 连接和日志检查 | NFC 故障定位 |
| `tools/env_nfc_relay_control.py` | 旧集成式 CLI，可注册卡、读 SHT30、测继电器、测人脸 | 调试工具，不作为主入口 |

## 最新硬件配置

详见 `docs/connect_way.md`。当前主程序默认值已按最新版接线调整：

```python
I2C_BUS_SHT30 = 4
I2C_BUS_NFC = 4
GPIO_LOCK_LINE = 3
GPIO_FAN_LINE = 9
GPIO_BUZZER_LINE = 4
```

其中 PN532 接在 `SDA.0/SCL.0`，资料标注为 `I2C5_I2C7`，板端需用以下命令确认实际总线：

```bash
sudo i2cdetect -y 7
sudo i2cdetect -y 5
```

## 板端常用命令

```bash
ssh elf@10.209.164.14
cd ~/smart_tool_cabinet

# 基础检查
bash scripts/check_system.sh

# 硬件检查，需要 sudo
sudo bash scripts/test_main.sh

# NFC 诊断
bash scripts/diagnose_nfc.sh

# 启动主程序
sudo python3 main.py

# 运行旧 CLI 调试工具
sudo python3 tools/env_nfc_relay_control.py read-sht30
sudo python3 tools/env_nfc_relay_control.py read-card
sudo python3 tools/env_nfc_relay_control.py test-relay fan
sudo python3 tools/env_nfc_relay_control.py test-relay lock
```

## 清理规则

工作区不保留以下内容：

- `__pycache__/`、`*.pyc`
- 编译中间文件 `*.o`
- 临时采集样本图、识别结果图
- Windows 驱动安装包
- 已过期的版本修复验证脚本

所有说明性 Markdown 文件统一放在 `docs/` 下。
