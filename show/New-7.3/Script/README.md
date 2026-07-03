# 智能安全工具柜触摸屏界面

基于 PyQt5 的工具柜触摸屏界面程序，适用于 ELF 2 / RK3588 开发板。

## 项目结构

```
Script/
├── main.py                    # 主程序入口
├── main_window.py             # 主窗口（页面切换、导航栏）
├── state_machine.py           # 系统状态机
├── mock_backend.py            # 模拟后端数据
├── pages/                     # 页面模块
│   ├── __init__.py
│   ├── dashboard_page.py      # 总览页
│   ├── auth_page.py           # 认证页
│   ├── tools_page.py          # 工具盘点页
│   ├── charging_page.py       # 充电管理页
│   ├── environment_page.py    # 环境监控页
│   ├── records_page.py        # 记录查询页
│   ├── settings_page.py       # 设置页
│   └── debug_page.py          # 调试维护页
└── README.md                  # 本文件
```

## 功能特性

### 1. 状态机驱动的页面切换

系统使用状态机控制页面显示和跳转：

- **STANDBY**: 未认证待机 → 只能访问总览和认证页
- **USER_AUTHED**: 普通用户已认证 → 可访问总览、工具、充电、环境、记录、认证页
- **ADMIN_AUTHED**: 管理员已认证 → 可访问所有页面（包括设置页）
- **CABINET_OPEN**: 柜门打开 → 自动跳转到工具页
- **MAINTENANCE**: 维护模式 → 只能访问调试、设置、总览页

### 2. 多种交互方式

- **点击底部导航栏**: 直接跳转到目标页面
- **左右滑动**: 在当前状态允许的页面间循环切换
- **状态自动跳转**: 关键事件触发时自动切换到对应页面

### 3. 完整的页面功能

#### 总览页 (DashboardPage)
- 五区工具状态可视化
- 环境数据卡片（温湿度、风扇）
- 充电状态概览
- 最近事件流

#### 认证页 (AuthPage)
- NFC 刷卡状态显示
- 人脸识别结果
- 用户权限显示
- 模拟认证功能（演示用）
- 申请开柜按钮
- 退出登录

#### 工具盘点页 (ToolsPage)
- 五区工具表格显示
- 登记数量 vs 当前数量
- 缺失/错放状态标识
- 立即盘点按钮

#### 充电管理页 (ChargingPage)
- 电池盒在位检测
- 4 个电池位状态显示
- 充电电源开关状态
- 充电检测模块在线状态
- 手动充电控制（管理员）

#### 环境监控页 (EnvironmentPage)
- 实时温湿度显示
- 风扇/报警器状态
- 合规阈值显示
- 最近趋势提示
- 手动风扇控制（管理员）

#### 记录查询页 (RecordsPage)
- 所有操作记录表格
- 按类型筛选（认证/开柜/盘点/充电/环境/报警）
- 导出 CSV 功能
- 实时事件追加

#### 设置页 (SettingsPage)
- 环境阈值设置
- 自动控制开关
- 进入维护模式
- 危险操作区（临时开锁、清空记录、重置系统）

#### 调试维护页 (DebugPage)
- 硬件在线状态检查
- 单模块测试按钮
- 运行日志实时显示
- 系统信息展示

## 运行环境

### 依赖

```bash
sudo apt update
sudo apt install python3-pyqt5 python3-pip -y
```

或使用 pip 安装：

```bash
pip3 install PyQt5
```

### 运行

```bash
cd Show/Script
python3 main.py
```

### 全屏模式

在 `main_window.py` 中取消注释以下行：

```python
# self.showFullScreen()  # 可以根据需要启用全屏
```

## 开发阶段

### 第一阶段：Mock 数据（当前）

当前使用 `MockBackend` 模拟所有硬件数据：

- 每 1 秒更新环境数据（温度、湿度、风扇状态）
- 每 2 秒更新工具状态（随机模拟缺失）
- 每 3 秒更新充电状态（随机模拟电池位变化）
- 支持手动触发认证、开柜、报警等事件

**优点**: 不需要实际硬件，可以在 PC 上开发和演示界面

### 第二阶段：硬件对接

后续接入板端硬件时：

1. 创建 `hardware_backend.py` 替代 `mock_backend.py`
2. 实现相同的信号接口：
   ```python
   env_updated = pyqtSignal(dict)
   auth_updated = pyqtSignal(dict)
   tools_updated = pyqtSignal(dict)
   charging_updated = pyqtSignal(dict)
   event_added = pyqtSignal(dict)
   ```
3. 在 `main_window.py` 中切换后端：
   ```python
   # from mock_backend import MockBackend
   from hardware_backend import HardwareBackend
   
   # self.backend = MockBackend()
   self.backend = HardwareBackend()
   ```

## 设计规范

### 色彩系统

按照 `design_sense` 设计规范：

- **背景**: `#F7F4EF` (温暖奶油色)
- **卡片**: `#FFFFFF`, `#FBF9F5`
- **边框**: `#E7E1D7` (温暖发际线)
- **文字**: `#1F2421` (主色), `#5C635D` (次要)
- **强调色**: `#C4612F` (陶土色), hover `#A94E22`
- **深色区域**: `#1F2421` (顶部栏、摄像头预览)

### 触摸优化

- 所有主要按钮高度 ≥ 56px
- 底部导航栏固定显示
- 关键报警使用颜色块和图标，不依赖小字
- 页面不堆砌文字，重点数据大字号显示

### 状态颜色

- **正常/在位**: 绿色调 `#5C635D`
- **待归还/离位**: 黄色调
- **错放/异常/超限**: 红色调 `#C4612F`
- **未连接/未启用**: 灰色
- **充电中**: 蓝色调

## 演示流程

1. 启动程序 → 进入总览页（STANDBY 状态）
2. 切换到认证页 → 点击"模拟管理员认证"
3. 认证成功 → 自动返回总览页（ADMIN_AUTHED 状态）
4. 点击"申请开柜" → 自动跳转到工具页（CABINET_OPEN 状态）
5. 观察工具状态表格、充电页、环境页的实时数据更新
6. 进入设置页 → 调整阈值、进入维护模式
7. 在调试页 → 测试各个硬件模块
8. 退出维护模式 → 返回正常状态

## 下一步工作

- [ ] 实现 `HardwareBackend`，接入实际硬件
- [ ] 连接 SHT30 温湿度传感器（I2C4）
- [ ] 连接 PN532 NFC 读卡器（I2C7）
- [ ] 连接摄像头，实现实时预览
- [ ] 接入 YOLO26 模型推理结果
- [ ] 接入 STM32 充电检测模块
- [ ] 实现 SQLite 数据库持久化
- [ ] 实现记录导出 CSV 功能
- [ ] 优化页面加载性能
- [ ] 添加页面切换动画

## 注意事项

1. **不要覆盖申报书**: `Plan/宝宝队申报书(7).docx` 除非明确要求
2. **Git 策略**: 代码和文档入库，临时文件和缓存不入库
3. **编码问题**: Windows PowerShell 下中文文件名需注意 UTF-8 编码
4. **状态约束**: 危险操作（开锁、清空记录）受状态机和权限双重约束
5. **模拟数据**: 第一阶段使用 Mock 数据，第二阶段才对接硬件

## 联系信息

项目：宝宝队 ELF 2 / RK3588 智能安全工具柜  
日期：2026-06-21  
框架：PyQt5 触摸屏界面（第一版）
