import ai_edge_litert.interpreter as tflite
import cv2
import numpy as np
from insightface.app import FaceAnalysis

# from insightface.utils import face_align


class FaceEmbedderTFLite:
    def __init__(self, model_path):
        # 1. Load model TFLite
        self.interpreter = tflite.Interpreter(model_path=model_path)
        self.interpreter.allocate_tensors()

        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()

        self.input_shape = self.input_details[0]["shape"]
        self.input_dtype = self.input_details[0]["dtype"]

        # 2. KHỞI TẠO INSIGHTFACE (Mô hình SCRFD)
        # allowed_modules=['detection']: Chỉ load mô hình dò mặt để lấy Bounding Box và 5 Landmarks
        # providers: Dùng CPU. Nếu server bạn có GPU Nvidia, đổi thành ['CUDAExecutionProvider']
        self.face_app = FaceAnalysis(
            allowed_modules=["detection"], providers=["CPUExecutionProvider"]
        )

        # det_size=(640, 640) là độ phân giải nội bộ chuẩn của SCRFD, bắt mặt nhỏ cực tốt
        self.face_app.prepare(ctx_id=0, det_size=(640, 640))

    # def process_image(self, image_path):
    #     """Đọc ảnh và trả về mảng vector (List[float])"""
    #     try:
    #         # InsightFace khuyên dùng trực tiếp hệ màu BGR gốc của OpenCV
    #         img_bgr = cv2.imread(image_path)
    #         if img_bgr is None:
    #             return None
    #     except Exception as e:
    #         print(f"Lỗi đọc file {image_path}: {e}")
    #         return None

    #     # 3. Tìm khuôn mặt bằng mạng SCRFD
    #     faces = self.face_app.get(img_bgr)

    #     if not faces:
    #         print(f"⚠️ Bỏ qua: Không tìm thấy khuôn mặt trong {image_path}")
    #         return None

    #     # 4. Tìm mặt to nhất (Tính diện tích Bounding Box)
    #     # Bbox có format: [x1, y1, x2, y2]
    #     largest_face = max(
    #         faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])
    #     )

    #     # 5. CĂN CHỈNH 5 ĐIỂM (UMEYAMA ALGORITHM)
    #     # kps (Keypoints) chứa 5 điểm: Mắt trái, Mắt phải, Mũi, Mép trái, Mép phải
    #     kps = largest_face.kps

    #     # 🔥 MAGIC Ở ĐÂY: norm_crop tự động tính ma trận Umeyama bù trừ cúi/ngửa/nghiêng
    #     # và crop ra đúng khung 112x112 chuẩn cho hệ thống nhận diện
    #     aligned_face_bgr = face_align.norm_crop(img_bgr, landmark=kps, image_size=112)

    #     # Chuyển về RGB để đưa vào model TFLite (MobileFaceNet được train trên RGB)
    #     aligned_face_rgb = cv2.cvtColor(aligned_face_bgr, cv2.COLOR_BGR2RGB)

    #     # 6. Normalize (-1.0 -> 1.0)
    #     img_array = aligned_face_rgb.astype(self.input_dtype)
    #     img_array = (img_array - 127.5) / 128.0
    #     input_data = np.expand_dims(img_array, axis=0)

    #     # 7. Chạy TFLite
    #     self.interpreter.set_tensor(self.input_details[0]["index"], input_data)
    #     self.interpreter.invoke()

    #     output_data = self.interpreter.get_tensor(self.output_details[0]["index"])
    #     raw_embedding = output_data[0]

    #     return self._l2_normalize(raw_embedding).tolist()

    def process_image(self, img_input):
        # 0. BỘ LỌC ĐẦU VÀO ĐA NĂNG
        if isinstance(img_input, str):
            # Nếu đầu vào là đường dẫn (string), dùng cách đọc chống lỗi Unicode
            try:
                with open(img_input, "rb") as f:
                    img_bytes = f.read()
                img_array = np.asarray(bytearray(img_bytes), dtype=np.uint8)
                if img_array is None or len(img_array) == 0:
                    raise ValueError("File rỗng (0 bytes).")
                img_bgr = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                if img_bgr is None:
                    raise TypeError("OpenCV không thể giải mã.")
            except Exception:
                return None
        elif isinstance(img_input, np.ndarray):
            # Nếu đầu vào đã là ma trận ảnh (từ file seed truyền vào), dùng luôn
            img_bgr = img_input.copy()
        else:
            return None

        if img_bgr is None:
            return None

        height, width, _ = img_bgr.shape
        if height < 60 or width < 60:
            # Ném thẳng lỗi để nó lọt vào vòng except "Lỗi hệ thống" in ra màn hình
            raise ValueError(
                f"Ảnh quá nhỏ ({width}x{height}px), không đủ tiêu chuẩn nhận diện."
            )

        max_dim = max(height, width)
        if max_dim > 1280:
            scale = 1280 / max_dim
            new_width = int(width * scale)
            new_height = int(height * scale)
            # Dùng INTER_AREA để resize ảnh nhỏ lại giữ chi tiết tốt nhất
            img_bgr = cv2.resize(
                img_bgr, (new_width, new_height), interpolation=cv2.INTER_AREA
            )
            height, width = img_bgr.shape[:2]  # Cập nhật lại width/height mới

        max_limit = 640
        im_ratio = float(width) / height

        if im_ratio > 1:
            new_width = max_limit
            new_height = int(new_width / im_ratio)
        else:
            new_height = max_limit
            new_width = int(new_height * im_ratio)

        # Ép về bội số của 32 để tránh lỗi "Broadcast shape (18,) (32,)"
        det_width = int(np.round(new_width / 32.0) * 32)
        det_height = int(np.round(new_height / 32.0) * 32)

        # Chạy InsightFace nhưng không dùng __init__ mặc định mà chèn det_size toán học này vào!
        # Điều này thay thế cho cái det_size tĩnh lúc đầu
        self.face_app.det_model.input_size = (det_width, det_height)
        print("det", det_width, det_height)
        faces = self.face_app.get(img_bgr)

        if not faces:
            return None

        # 1. Lọc mặt nhỏ 10% y hệt Dart
        min_face_width = width * 0.09
        valid_faces = [f for f in faces if (f.bbox[2] - f.bbox[0]) >= min_face_width]
        if not valid_faces:
            biggest = max([(f.bbox[2] - f.bbox[0]) for f in faces])
            print(
                f" -> Mặt quá bé: lớn nhất là {biggest:.1f}px, yêu cầu {min_face_width:.1f}px"
            )
            return None

        largest_face = max(
            valid_faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])
        )

        # # 2. Lấy 2 mắt từ InsightFace
        # # kps: 0: left_eye, 1: right_eye
        # eye_l = largest_face.kps[0]
        # eye_r = largest_face.kps[1]

        # 3. CHẠY THUẬT TOÁN 2 ĐIỂM Y HỆT C++ (Dùng Numpy để nhanh)
        input_data = self._align_and_normalize_face_sync_mobile(
            img_bgr, largest_face.kps
        )

        # 4. Chạy TFLite
        self.interpreter.set_tensor(self.input_details[0]["index"], input_data)
        self.interpreter.invoke()
        return self._l2_normalize(
            self.interpreter.get_tensor(self.output_details[0]["index"])[0]
        ).tolist()

    def _align_and_normalize_face_sync_mobile(self, img_bgr, kps):
        """
        Đồng bộ 100% với hàm process_file_affine_raw trong C++
        Sử dụng đúng REF_X, REF_Y và thuật toán 2 điểm mắt.
        """
        # 1. Chuyển sang RGB (Vì TFLite nhận RGB)
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        height, width, _ = img_rgb.shape

        # 2. Lấy tọa độ 2 mắt từ Keypoints của InsightFace
        # Index 0: Mắt trái, Index 1: Mắt phải
        eye_l = kps[0]
        eye_r = kps[1]

        # 3. Tính toán tâm và góc xoay (Y hệt code C++ của bạn)
        src_eye_x = (eye_l[0] + eye_r[0]) / 2.0
        src_eye_y = (eye_l[1] + eye_r[1]) / 2.0
        dx, dy = eye_r[0] - eye_l[0], eye_r[1] - eye_l[1]
        src_dist = np.sqrt(dx * dx + dy * dy)
        src_angle = np.arctan2(dy, dx)

        # Tọa độ đích (Lấy từ bộ REF_X, REF_Y của bạn)
        # REF_X[0]=38.2946, REF_X[1]=73.5318, REF_Y[0]=51.6963
        dst_eye_x = (38.2946 + 73.5318) / 2.0
        dst_eye_y = 51.6963
        dst_dist = 73.5318 - 38.2946

        # Tính toán ma trận
        scale = dst_dist / src_dist if src_dist > 0 else 1.0
        angle_diff = 0.0 - src_angle  # dst_angle luôn = 0 trong code C++
        cosR, sinR = np.cos(angle_diff) * scale, np.sin(angle_diff) * scale

        tx = dst_eye_x - (src_eye_x * cosR - src_eye_y * sinR)
        ty = dst_eye_y - (src_eye_x * sinR + src_eye_y * cosR)

        # Ma trận nghịch đảo (Inverse Mapping)
        det = cosR * cosR + sinR * sinR
        idet = 1.0 / det if det != 0 else 1.0
        A, B, C = cosR * idet, sinR * idet, (-sinR * ty - cosR * tx) * idet
        D, E, F = -sinR * idet, cosR * idet, (sinR * tx - cosR * ty) * idet

        # 4. Warp & Normalize thủ công (Mô phỏng (int)srcX của C++)
        targetSize = 112
        y_coords, x_coords = np.mgrid[0:targetSize, 0:targetSize]

        srcX = (x_coords * A + y_coords * B + C).astype(np.int32)
        srcY = (x_coords * D + y_coords * E + F).astype(np.int32)

        srcX = np.clip(srcX, 0, width - 1)
        srcY = np.clip(srcY, 0, height - 1)

        aligned_face = img_rgb[srcY, srcX]

        # 5. Normalize (-1.0 -> 1.0) y hệt C++: (val - 127.5) / 128.0
        img_array = (aligned_face.astype(np.float32) - 127.5) / 128.0
        return np.expand_dims(img_array, axis=0)

    def _l2_normalize(self, vector):
        """Hàm chuẩn hóa vector (đưa độ dài vector về 1)"""
        norm = np.linalg.norm(vector, ord=2)
        if norm == 0:
            norm = 1e-10
        return vector / norm
