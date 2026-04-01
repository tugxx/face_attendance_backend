import os

import ai_edge_litert.interpreter as tflite
import cv2
import numpy as np
from insightface.app import FaceAnalysis

# from insightface.utils import face_align


class FaceEmbedderTFLite:
    """
    Core AI Engine for Face Detection and Feature Extraction.
    - Detector: InsightFace SCRFD (CPU)
    - Extractor: Custom TFLite Model (e.g., MobileFaceNet)
    """

    def __init__(self, model_path):
        # 1. AI Metadata
        self.detector_name = "insightface_scrfd"
        self.extractor_name = os.path.basename(model_path).replace(".tflite", "")

        # 2. Initialize Feature Extractor (TFLite)
        self.interpreter = tflite.Interpreter(model_path=model_path)
        self.interpreter.allocate_tensors()
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()
        self.input_shape = self.input_details[0]["shape"]
        self.input_dtype = self.input_details[0]["dtype"]

        # 3. Initialize Face Detector (InsightFace)
        self.face_app = FaceAnalysis(
            allowed_modules=["detection"], providers=["CPUExecutionProvider"]
        )
        self.face_app.prepare(ctx_id=0, det_size=(640, 640))

        # Internal state
        self.last_cropped_face = None

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
        """
        Executes the complete face processing pipeline.

        Pipeline Flow:
        1. Input Validation: Accepts file path (str) or image matrix (np.ndarray). Handles Unicode paths safely.
        2. Quality Check: Rejects images smaller than 60x60px.
        3. Dynamic Rescaling: Downscales oversized images (>1280px) to prevent memory exhaustion,
           then calculates optimal dimensions (multiples of 32) for the SCRFD detector.
        4. Face Detection: Extracts bounding boxes and landmarks.
        5. Filtering: Discards faces smaller than 9% of the image width. Selects the largest valid face.
        6. State Saving: Crops and stores the raw BGR face image in `self.last_cropped_face` for external FIQA use.
        7. Alignment & Normalization: Aligns the face using 2-point affine transform (matching C++ logic).
        8. Feature Extraction: Runs the TFLite model and applies L2 Normalization.

        Args:
            img_input (str or np.ndarray): Image file path or BGR image array.
            is_pre_cropped (bool): (Reserved/Unused) Flag for pre-cropped faces.

        Returns:
            list[float] or None: A 1D list representing the L2-normalized feature vector, or None if processing fails.
        """
        self.last_cropped_face = None

        if isinstance(img_input, str):
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
            img_bgr = img_input.copy()
        else:
            return None

        if img_bgr is None:
            return None

        height, width, _ = img_bgr.shape
        if height < 60 or width < 60:
            raise ValueError(
                f"Ảnh quá nhỏ ({width}x{height}px), không đủ tiêu chuẩn nhận diện."
            )

        max_dim = max(height, width)
        if max_dim > 1280:
            scale = 1280 / max_dim
            new_width = int(width * scale)
            new_height = int(height * scale)
            img_bgr = cv2.resize(
                img_bgr, (new_width, new_height), interpolation=cv2.INTER_AREA
            )
            height, width = img_bgr.shape[:2]

        max_limit = 640
        im_ratio = float(width) / height

        if im_ratio > 1:
            new_width = max_limit
            new_height = int(new_width / im_ratio)
        else:
            new_height = max_limit
            new_width = int(new_height * im_ratio)

        det_width = int(np.round(new_width / 32.0) * 32)
        det_height = int(np.round(new_height / 32.0) * 32)

        self.face_app.det_model.input_size = (det_width, det_height)
        faces = self.face_app.get(img_bgr)

        if not faces:
            return None

        min_face_width = width * 0.09
        valid_faces = [f for f in faces if (f.bbox[2] - f.bbox[0]) >= min_face_width]

        if not valid_faces:
            biggest = max([(f.bbox[2] - f.bbox[0]) for f in faces])
            print(
                f" -> Mặt quá bé: lớn nhất là {biggest:.1f}px, yêu cầu {min_face_width:.1f}px"
            )
            return None

        largest_face = max(
            valid_faces,
            key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
        )

        box = largest_face.bbox.astype(int)
        x1, y1 = max(0, box[0]), max(0, box[1])
        x2, y2 = min(width, box[2]), min(height, box[3])

        self.last_cropped_face = img_bgr[y1:y2, x1:x2]
        self.last_kps = largest_face.kps

        input_data = self._align_and_normalize_face_sync_mobile(
            img_bgr, largest_face.kps
        )

        self.interpreter.set_tensor(self.input_details[0]["index"], input_data)
        self.interpreter.invoke()

        raw_vector = self.interpreter.get_tensor(self.output_details[0]["index"])[0]
        return self._l2_normalize(raw_vector).tolist()

    def _align_and_normalize_face_sync_mobile(self, img_bgr, kps):
        """
        Thực hiện xoay, cắt và chuẩn hóa khuôn mặt (Face Alignment) đồng bộ 100%
        với thuật toán `process_file_affine_raw` trên C++ (Edge Device).

        Luồng thuật toán (2-Point Affine Transform):

        1. Lấy tọa độ gốc: Trích xuất tọa độ (x, y) của mắt trái và mắt phải từ Keypoints.

        2. Tính thông số ảnh gốc (Source):
           - Tâm xoay (Center): Trung bình cộng tọa độ của hai mắt.
           - Khoảng cách (Distance): Chiều dài đoạn thẳng nối hai mắt (Định lý Pytago).
           - Góc nghiêng (Angle): Tính bằng hàm arctan2 dựa trên độ chênh lệch y và x của 2 mắt.

        3. Tính thông số ảnh đích (Destination) dựa trên bộ tham số nội bộ:
           - Tọa độ mắt chuẩn (REF_X): 38.2946 (trái) và 73.5318 (phải).
           - Tọa độ mắt chuẩn (REF_Y): 51.6963 (cả hai mắt nằm ngang nhau).
           - Tỷ lệ nội suy (Scale): Bằng khoảng cách 2 mắt đích chia cho khoảng cách 2 mắt gốc.

        4. Xây dựng Ma trận nghịch đảo (Inverse Matrix):
           - Tính toán bộ 6 hệ số [A, B, C, D, E, F] từ việc nghịch đảo ma trận xoay và tịnh tiến.
           - Mục đích: Để quét từng điểm ảnh trên khung 112x112 đích và tra ngược về vị trí tương ứng trên ảnh gốc.

        5. Nội suy Nearest-Neighbor (Mô phỏng ép kiểu C++):
           - Dùng ma trận lưới (Grid) 112x112 nhân với ma trận nghịch đảo để tìm tọa độ nguồn.
           - Ép kiểu mảng về số nguyên int32. Việc này mô phỏng chính xác thao tác ngắt bỏ phần thập phân
             (truncation) của biến `(int)` trong C++, giúp vector trích xuất ra hoàn toàn khớp với thiết bị.

        6. Chuẩn hóa Tensor:
           - Lấy giá trị từng pixel (0-255) trừ đi 127.5, sau đó chia cho 128.0 để dải giá trị nằm trong khoảng [-1.0, 1.0].

        Args:
            img_bgr (np.ndarray): Ma trận ảnh gốc hệ màu BGR (đọc từ OpenCV).
            kps (np.ndarray): Mảng 5 điểm mốc (Landmarks) từ InsightFace, trong đó index 0, 1 là 2 mắt.

        Returns:
            np.ndarray: Tensor kích thước (1, 112, 112, 3) dạng float32, sẵn sàng nạp thẳng vào TFLite.
        """
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        height, width, _ = img_rgb.shape

        eye_l, eye_r = kps[0], kps[1]

        src_eye_x = (eye_l[0] + eye_r[0]) / 2.0
        src_eye_y = (eye_l[1] + eye_r[1]) / 2.0
        dx, dy = eye_r[0] - eye_l[0], eye_r[1] - eye_l[1]
        src_dist = np.sqrt(dx * dx + dy * dy)
        src_angle = np.arctan2(dy, dx)

        dst_eye_x = (38.2946 + 73.5318) / 2.0
        dst_eye_y = 51.6963
        dst_dist = 73.5318 - 38.2946

        scale = dst_dist / src_dist if src_dist > 0 else 1.0
        angle_diff = 0.0 - src_angle
        cosR, sinR = np.cos(angle_diff) * scale, np.sin(angle_diff) * scale

        tx = dst_eye_x - (src_eye_x * cosR - src_eye_y * sinR)
        ty = dst_eye_y - (src_eye_x * sinR + src_eye_y * cosR)

        det = cosR * cosR + sinR * sinR
        idet = 1.0 / det if det != 0 else 1.0
        A, B, C = cosR * idet, sinR * idet, (-sinR * ty - cosR * tx) * idet
        D, E, F = -sinR * idet, cosR * idet, (sinR * tx - cosR * ty) * idet

        targetSize = 112
        y_coords, x_coords = np.mgrid[0:targetSize, 0:targetSize]

        srcX = (x_coords * A + y_coords * B + C).astype(np.int32)
        srcY = (x_coords * D + y_coords * E + F).astype(np.int32)

        srcX = np.clip(srcX, 0, width - 1)
        srcY = np.clip(srcY, 0, height - 1)

        aligned_face = img_rgb[srcY, srcX]

        img_array = (aligned_face.astype(np.float32) - 127.5) / 128.0
        return np.expand_dims(img_array, axis=0)

    def _l2_normalize(self, vector):
        """Hàm chuẩn hóa vector (đưa độ dài vector về 1)"""
        norm = np.linalg.norm(vector, ord=2)
        if norm == 0:
            norm = 1e-10
        return vector / norm
