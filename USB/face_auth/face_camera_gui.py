#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyQt5 实时摄像头人脸识别 GUI — k-NN 分类器版
"""
import os
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = "/home/gaoshuo/anaconda3/envs/toolcab/lib/python3.10/site-packages/PyQt5/Qt5/plugins"
os.environ["QT_QPA_PLATFORM"] = "xcb"

from PyQt5.QtCore import QCoreApplication
QCoreApplication.setLibraryPaths([
    "/home/gaoshuo/anaconda3/envs/toolcab/lib/python3.10/site-packages/PyQt5/Qt5/plugins"
])

import sys
import numpy as np
import cv2
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

from face_recognition_core import FaceRecognizer

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QWidget, QTextEdit
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QImage, QPixmap, QFont

BASE_DIR = Path(__file__).parent.parent


class CameraThread(QThread):
    frame_ready = pyqtSignal(np.ndarray)
    result_ready = pyqtSignal(str, float)
    log_msg = pyqtSignal(str)

    def __init__(self, recognizer, device_id=0):
        super().__init__()
        self.recognizer = recognizer
        self.device_id = device_id
        self.running = False
        self.do_recognize = False
        self.last_box = None
        self.last_name = None
        self.last_score = None

    def _draw_chinese(self, img, text, pos, color=(0, 255, 0), font_size=22):
        """用 PIL 绘制中文标签到 OpenCV 图像上"""
        img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img_pil)
        try:
            font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", font_size)
        except Exception:
            font = ImageFont.load_default()
        draw.text(pos, text, font=font, fill=color[::-1])
        return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

    def run(self):
        cap = cv2.VideoCapture(self.device_id, cv2.CAP_V4L2)
        if not cap.isOpened():
            self.log_msg.emit("❌ 无法打开摄像头")
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        self.running = True
        self.log_msg.emit("📹 摄像头已启动")

        frame_count = 0
        cached_face = None

        while self.running:
            ret, frame = cap.read()
            if not ret:
                continue

            frame_count += 1
            box = None
            name, score = "", 0.0

            # 每 5 帧检测一次，中间复用缓存（更流畅）
            if frame_count % 5 == 1 or cached_face is None:
                cached_face = self.recognizer.detect_face(frame)

            face_obj = cached_face

            if face_obj is not None:
                x1, y1, x2, y2 = face_obj.bbox.astype(int)
                box = (x1, y1, x2, y2)

                if self.do_recognize:
                    feat = self.recognizer.extract_feature(face_obj)
                    name, score = self.recognizer.recognize(feat)
                    self.last_box = box
                    self.last_name = name
                    self.last_score = score
                    self.result_ready.emit(name, score)
                    self.log_msg.emit(f"识别结果: {name} (置信度: {score:.4f})")
                    self.do_recognize = False

            display = frame.copy()
            if box:
                x1, y1, x2, y2 = box
                if self.last_box and self._iou(box, self.last_box) > 0.5:
                    color = (0, 255, 0) if self.last_name != "陌生人" else (0, 0, 255)
                    cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)
                    if self.last_name:
                        label = f"{self.last_name} ({self.last_score:.2f})"
                        display = self._draw_chinese(display, label, (x1, y1 - 30), color=color)
                else:
                    cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 255), 2)

            self.frame_ready.emit(display)

        cap.release()
        self.log_msg.emit("📹 摄像头已关闭")

    def _iou(self, a, b):
        x1 = max(a[0], b[0])
        y1 = max(a[1], b[1])
        x2 = min(a[2], b[2])
        y2 = min(a[3], b[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area_a = (a[2] - a[0]) * (a[3] - a[1])
        area_b = (b[2] - b[0]) * (b[3] - b[1])
        return inter / (area_a + area_b - inter + 1e-6)

    def recognize_now(self):
        self.do_recognize = True

    def stop(self):
        self.running = False
        self.wait(2000)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("人脸识别实时验证 - k-NN版")
        self.setGeometry(100, 100, 900, 600)

        self.recognizer = FaceRecognizer()
        self.cam_thread = None

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        left = QVBoxLayout()
        self.video_label = QLabel("点击「打开摄像头」开始")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(640, 480)
        self.video_label.setStyleSheet("background-color: #1a1a1a; color: #888; font-size: 18px;")
        left.addWidget(self.video_label)

        btn_layout = QHBoxLayout()
        self.btn_open = QPushButton("📷 打开摄像头")
        self.btn_open.setStyleSheet("font-size: 16px; padding: 10px;")
        self.btn_open.clicked.connect(self.toggle_camera)

        self.btn_recog = QPushButton("🔍 立即识别")
        self.btn_recog.setStyleSheet("font-size: 16px; padding: 10px;")
        self.btn_recog.setEnabled(False)
        self.btn_recog.clicked.connect(self.recognize_now)

        self.btn_save = QPushButton("💾 保存当前帧")
        self.btn_save.setStyleSheet("font-size: 16px; padding: 10px;")
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self.save_frame)

        btn_layout.addWidget(self.btn_open)
        btn_layout.addWidget(self.btn_recog)
        btn_layout.addWidget(self.btn_save)
        left.addLayout(btn_layout)

        layout.addLayout(left, stretch=2)

        right = QVBoxLayout()

        people = self.recognizer.all_names
        self.info_label = QLabel()
        self.info_label.setAlignment(Qt.AlignTop)
        self.info_label.setText(
            f"<b>🔐 人脸识别验证系统 (k-NN)</b><br><br>"
            f"📂 人脸库: {len(people)} 人<br>"
            f"{'<br>'.join(people)}<br><br>"
            f"<b>操作说明:</b><br>"
            f"1. 点击「打开摄像头」<br>"
            f"2. 人脸对准摄像头<br>"
            f"3. 点击「立即识别」<br>"
        )
        self.info_label.setStyleSheet("font-size: 14px; padding: 10px;")
        right.addWidget(self.info_label)

        self.result_label = QLabel("等待识别...")
        self.result_label.setAlignment(Qt.AlignCenter)
        self.result_label.setStyleSheet(
            "font-size: 28px; font-weight: bold; color: #333; "
            "background-color: #f0f0f0; padding: 20px; border-radius: 10px;"
        )
        right.addWidget(self.result_label)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet("font-size: 12px;")
        self.log_box.setPlaceholderText("运行日志...")
        right.addWidget(self.log_box, stretch=1)

        layout.addLayout(right, stretch=1)

        self.current_frame = None

    def toggle_camera(self):
        if self.cam_thread is None or not self.cam_thread.isRunning():
            self.cam_thread = CameraThread(self.recognizer, device_id='/dev/video21')
            self.cam_thread.frame_ready.connect(self.update_frame)
            self.cam_thread.result_ready.connect(self.update_result)
            self.cam_thread.log_msg.connect(self.append_log)
            self.cam_thread.start()
            self.btn_open.setText("⏹ 关闭摄像头")
            self.btn_recog.setEnabled(True)
            self.btn_save.setEnabled(True)
        else:
            self.cam_thread.stop()
            self.cam_thread = None
            self.btn_open.setText("📷 打开摄像头")
            self.btn_recog.setEnabled(False)
            self.btn_save.setEnabled(False)
            self.video_label.setText("点击「打开摄像头」开始")
            self.video_label.setStyleSheet("background-color: #1a1a1a; color: #888; font-size: 18px;")

    def update_frame(self, frame):
        self.current_frame = frame.copy()
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qt_image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image)
        self.video_label.setPixmap(pixmap.scaled(
            self.video_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))

    def update_result(self, name, score):
        if name == "陌生人":
            self.result_label.setText(f"❌ {name}\n相似度: {score:.4f}")
            self.result_label.setStyleSheet(
                "font-size: 28px; font-weight: bold; color: #c00; "
                "background-color: #ffe0e0; padding: 20px; border-radius: 10px;"
            )
        else:
            self.result_label.setText(f"✅ {name}\n相似度: {score:.4f}")
            self.result_label.setStyleSheet(
                "font-size: 28px; font-weight: bold; color: #0a0; "
                "background-color: #e0ffe0; padding: 20px; border-radius: 10px;"
            )

    def recognize_now(self):
        if self.cam_thread:
            self.cam_thread.recognize_now()
            self.append_log("🔍 触发识别...")

    def save_frame(self):
        if self.current_frame is not None:
            save_dir = Path.home() / "Desktop" / "实验"
            save_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%H%M%S")
            path = save_dir / f"gui_cam_{ts}.jpg"
            cv2.imwrite(str(path), self.current_frame)
            self.append_log(f"💾 已保存: {path}")

    def append_log(self, msg):
        self.log_box.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def closeEvent(self, event):
        if self.cam_thread and self.cam_thread.isRunning():
            self.cam_thread.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    font = QFont("Noto Sans CJK SC", 10)
    app.setFont(font)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
