import os

import cv2
import numpy as np


class FaceQualityAssessor:
    """
    Module chấm điểm chất lượng ảnh khuôn mặt.
    Ưu tiên dùng AI (LightQNet). Nếu không có, tự động chuyển sang Toán học (OpenCV).
    """

    def __init__(self, model_path="models/lightqnet-dm100.pb"):
        self.use_ai = False
        self.net = None
        self.assessor_name = "opencv_math"

        # Kiểm tra xem file AI có tồn tại không
        if model_path and os.path.exists(model_path):
            try:
                self.net = cv2.dnn.readNetFromTensorflow(model_path)
                self.use_ai = True
                self.assessor_name = os.path.basename(model_path).replace(".pb", "")
                print("✅ Đã kích hoạt AI Quality Model (LightQNet) thành công!")
            except Exception as e:
                print(
                    f"⚠️ Lỗi load AI Model: {e}. Hệ thống sẽ dùng Toán học để dự phòng."
                )
        else:
            print(
                "⚠️ Không tìm thấy file AI Model. Hệ thống sẽ dùng Toán học (Fallback)."
            )

    def assess(self, cropped_face, landmarks):
        """
        Giao diện chấm điểm thống nhất. Trả về điểm float từ 0.0 -> 1.0.
        """
        if self.use_ai:
            return self._assess_by_ai(cropped_face)
        else:
            return self._assess_by_math(cropped_face, landmarks)

    def _assess_by_ai(self, cropped_face):
        """
        Input: Ảnh khuôn mặt đã được cắt (của InsightFace/SCRFD)
        Output: Điểm chất lượng (0.0 -> 1.0)
        """
        img_resized = cv2.resize(cropped_face, (96, 96))
        img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
        img_normalized = (img_rgb.astype(np.float32) - 128.0) / 128.0
        blob = cv2.dnn.blobFromImage(img_normalized)
        self.net.setInput(blob)
        out = self.net.forward()
        return float(out[0][0])

    def _assess_by_math(self, img_bgr, kps):
        """
        Fallback: Đánh giá bằng Toán học (OpenCV).
        Đã được chuẩn hóa về thang điểm 0.0 -> 1.0 để khớp với AI.
        """
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        total_score = 0.0

        # 1. Blur Detection (Max 0.4 điểm)
        gray_std = cv2.resize(gray, (112, 112))
        laplacian_var = cv2.Laplacian(gray_std, cv2.CV_64F).var()

        blur_score = min(0.4, (laplacian_var / 300.0) * 0.4)
        total_score += blur_score

        # 2. Exposure (Max 0.3 điểm)
        mean_intensity = np.mean(gray)
        if mean_intensity < 40 or mean_intensity > 210:
            exposure_score = 0.0
        else:
            diff = abs(mean_intensity - 128.0)
            exposure_score = 0.3 * (1.0 - (diff / 128.0))
        total_score += exposure_score

        # 3. Head Pose (Max 0.3 điểm)
        model_points_3D = np.array(
            [
                [-22.5, -17.0, -13.5],
                [22.5, -17.0, -13.5],
                [0.0, 0.0, 0.0],
                [-15.0, 17.0, -13.5],
                [15.0, 17.0, -13.5],
            ],
            dtype=np.float64,
        )
        h, w = img_bgr.shape[:2]
        camera_matrix = np.array(
            [[w, 0, w / 2], [0, w, h / 2], [0, 0, 1]], dtype="double"
        )
        dist_coeffs = np.zeros((4, 1))

        success, rotation_vector, _ = cv2.solvePnP(
            model_points_3D,
            kps.astype(np.float64),
            camera_matrix,
            dist_coeffs,
            flags=cv2.SOLVEPNP_SQPNP,
        )

        if success:
            rmat, _ = cv2.Rodrigues(rotation_vector)
            proj_matrix = np.hstack((rmat, np.zeros((3, 1))))
            _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(proj_matrix)
            pitch, yaw, roll = euler_angles.flatten()

            max_angle = max(abs(pitch), abs(yaw), abs(roll))
            pose_score = (
                0.3 if max_angle < 5 else max(0.0, 0.3 * (1.0 - max_angle / 30.0))
            )
            total_score += pose_score
        else:
            total_score += 0.15  # Điểm vớt nếu lỗi hình học

        return float(total_score)
