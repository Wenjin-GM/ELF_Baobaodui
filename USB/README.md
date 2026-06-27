# 人脸识别模块 — 使用说明

## 技术方案
- **检测**: InsightFace RetinaFace
- **特征提取**: MobileFaceNet 512D
- **分类**: k-NN (cosine distance)
- **阈值**: 0.40 (低于此值为陌生人)

## 环境依赖

```bash
pip install insightface==0.7.3 onnxruntime-gpu opencv-python PyQt5 numpy scikit-learn pillow
```

> 首次运行会自动下载 `buffalo_s` 模型到 `~/.insightface/models/`

## 文件说明

| 文件 | 作用 |
|------|------|
| `face_recognition_core.py` | 核心引擎：检测/提取/识别/注册 |
| `face_camera_gui.py` | PyQt5 实时摄像头 GUI |
| `face_db/` | 人脸特征库（高硕 16 个特征 + 赵增辉 11 个特征） |

## 运行方式

### 1. 实时摄像头识别
```bash
python face_camera_gui.py
```
- 点击 "📷 打开摄像头" 启动
- 点击 "🔍 立即识别" 手动触发
- 支持保存截图

### 2. 注册新人员（代码方式）
```python
from face_recognition_core import FaceRecognizer

fr = FaceRecognizer(face_db_dir="face_db")
fr.register_person("张三", ["photo1.jpg", "photo2.jpg", ...])
```

## 关键参数

```python
# face_recognition_core.py 中可调整
self.STRANGER_THRESHOLD = 0.40   # 陌生人阈值
self.app.prepare(ctx_id=0, det_size=(320, 320))  # GPU加速，检测分辨率
```

## 板端部署注意

1. **RK3588 上需安装 ONNX Runtime**: `pip install onnxruntime`
   - 如 GPU 不可用会自动 fallback 到 CPU
2. **中文显示**: 需要 `NotoSansCJK-Regular.ttc` 字体
   - 路径: `/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`
3. **摄像头**: 默认 `/dev/video0`
   - 如被占用，用 `fuser /dev/video0` 查看并 `kill -9 PID`

## 性能指标（已验证）

- 同一人 cosine distance: ~0.63 (avg)
- 不同人 cosine distance: ~0.16 (avg)
- 识别延迟: < 0.2s (GPU) / < 0.5s (CPU)
- 准确率: 高硕/赵增辉/陌生人 正确区分
