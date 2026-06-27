#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
人脸识别核心引擎 — InsightFace 官方方案
- 检测: RetinaFace (自带 5 点 landmarks)
- 对齐: InsightFace 内部对齐
- 特征: MobileFaceNet 512D (InsightFace 训练版)
- 分类: k-NN 最近邻
"""
import cv2
import numpy as np
from pathlib import Path
from sklearn.neighbors import NearestNeighbors

# 陌生人阈值
STRANGER_THRESHOLD = 0.40


class FaceRecognizer:
    """人脸识别器: InsightFace 检测+对齐+特征 + k-NN分类"""

    def __init__(self, face_db_dir="face_db"):
        # 延迟导入，避免启动时太慢
        from insightface.app import FaceAnalysis

        self.app = FaceAnalysis(name="buffalo_s", root="~/.insightface")
        self.app.prepare(ctx_id=0, det_size=(320, 320))

        self.face_db_dir = Path(face_db_dir)
        self.knn = NearestNeighbors(n_neighbors=1, metric="cosine")
        self.person_names = []
        self.all_features = []
        self._load_face_db()

    def _load_face_db(self):
        """从 .npy 文件加载已注册的人脸特征"""
        features, names = [], []
        for npy_file in sorted(self.face_db_dir.glob("*.npy")):
            feat = np.load(npy_file)
            features.append(feat)
            names.append(npy_file.stem)
        if features:
            self.all_features = np.vstack(features)
            self.person_names = names
            self.all_names = sorted(set(n.split('_')[0] for n in names))
            self.knn.fit(self.all_features)
            print(f"📂 人脸库加载: {len(self.all_names)} 人, {len(names)} 条特征")
            for name in self.all_names:
                count = sum(1 for n in names if n.split('_')[0] == name)
                print(f"   {name}: {count} 张标准照")
        else:
            self.all_names = []
            print("⚠️ 人脸库为空，请先注册人脸")

    def detect_face(self, image):
        """
        检测人脸，返回 InsightFace Face 对象列表中的最佳人脸
        """
        faces = self.app.get(image)
        if not faces:
            return None
        # 取检测得分最高的人脸
        best = max(faces, key=lambda f: f.det_score)
        return best

    def extract_feature(self, face_obj):
        """
        从 InsightFace Face 对象提取 L2 归一化特征
        face_obj.embedding 已经是 512D 特征，但未归一化
        """
        feat = face_obj.embedding.copy()
        norm = np.linalg.norm(feat)
        if norm > 0:
            feat = feat / norm
        return feat

    def recognize(self, face_feat):
        """
        k-NN 识别，返回 (name, confidence)
        """
        if len(self.all_features) == 0:
            return "陌生人", 0.0

        distances, indices = self.knn.kneighbors([face_feat])
        dist = distances[0][0]  # cosine distance
        idx = indices[0][0]
        confidence = 1.0 - dist

        if confidence < STRANGER_THRESHOLD:
            return "陌生人", confidence

        name = self.person_names[idx]
        real_name = name.split("_")[0]
        return real_name, confidence

    def add_person(self, name, image_paths):
        """
        注册新人，从图片提取特征保存为 .npy
        """
        count = 0
        for img_path in image_paths:
            image = cv2.imread(str(img_path))
            if image is None:
                print(f"  ⚠️ 无法读取图片: {img_path}")
                continue

            face = self.detect_face(image)
            if face is None:
                print(f"  ⚠️ 未检测到人脸: {Path(img_path).name}")
                continue

            feat = self.extract_feature(face)
            save_path = self.face_db_dir / f"{name}_{count:03d}.npy"
            np.save(save_path, feat)
            print(f"  ✅ [{name}] 第 {count+1} 张特征已保存 → {save_path.name} (det_score={face.det_score:.3f})")
            count += 1

        # 重新加载人脸库
        self._load_face_db()
        return count


def main_test():
    import sys
    recognizer = FaceRecognizer()

    if len(sys.argv) > 1:
        img_path = sys.argv[1]
        image = cv2.imread(img_path)
        if image is None:
            print(f"❌ 无法读取图片: {img_path}")
            return

        face = recognizer.detect_face(image)
        if face is None:
            print("❌ 未检测到人脸")
            return

        feat = recognizer.extract_feature(face)
        name, conf = recognizer.recognize(feat)

        x1, y1, x2, y2 = face.bbox.astype(int)
        color = (0, 255, 0) if name != "陌生人" else (0, 0, 255)
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        label = f"{name} ({conf:.2f})"
        cv2.putText(image, label, (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        save_path = f"result_{Path(img_path).name}"
        cv2.imwrite(save_path, image)
        print(f"🎯 识别结果: {name} (置信度: {conf:.2%})")
        print(f"💾 结果图已保存: {save_path}")
    else:
        print("用法: python face_recognition_core.py <图片路径>")


if __name__ == "__main__":
    main_test()
