import json
import os
import re
import shutil
import time
import zipfile

import cv2
import numpy as np
from django.core.management.base import BaseCommand
from django.utils import timezone

from tools.management.commands.ai_service import (
    FaceEmbedderTFLite,
)
from tools.management.commands.face_quality import FaceQualityAssessor


class Command(BaseCommand):
    help = "Xử lý file Zip ảnh, đánh giá chất lượng model và lưu Face Embeddings vào DB"

    def _log_histogram_ascii(self, intra_sims, inter_sims):
        """
        Vẽ biểu đồ ASCII Histogram thể hiện Phân phối Độ tương đồng (Similarity Distribution).
        Đây là công cụ trực quan để đánh giá sức mạnh phân biệt của Model AI.

        Cách đọc biểu đồ:
        - [R] Inter-similarity (Khác người): Sự tương đồng giữa các khuôn mặt của NHỮNG NGƯỜI KHÁC NHAU.
          => Lý tưởng: Càng thấp càng tốt (Tập trung ở khoảng 0.0 -> 0.4).
        - [B] Intra-similarity (Cùng người): Sự tương đồng giữa các khuôn mặt của CÙNG MỘT NGƯỜI.
          => Lý tưởng: Càng cao càng tốt (Tập trung ở khoảng 0.6 -> 1.0).

        Đánh giá Model:
        - Model TỐT: Đám [R] và đám [B] tách biệt hoàn toàn, ở giữa là khoảng trống. Dễ dàng chọn Ngưỡng (Threshold).
        - Model XẤU: Đám [R] và [B] tràn vào nhau (Ví dụ: Khác người mà giống > 0.5, Cùng người mà giống < 0.5).
          Gây ra hiện tượng Nhận vơ (False Accept) hoặc Từ chối sai (False Reject).

        Args:
            intra_sims (list/array): Danh sách điểm số so sánh các ảnh của Cùng 1 người.
            inter_sims (list/array): Danh sách điểm số so sánh chéo các ảnh Khác người.
        """

        self.stdout.write(
            "\n📊 BIỂU ĐỒ PHÂN PHỐI ĐỘ TƯƠNG ĐỒNG (SIMILARITY DISTRIBUTION)"
        )
        self.stdout.write(
            f"{'Khoảng điểm':<13} | {'[R] Khác người (Inter)':<25} | [B] Cùng người (Intra)"
        )
        self.stdout.write("-" * 75)

        bins = np.linspace(0, 1, 11)
        inter_hist, _ = np.histogram(inter_sims, bins=bins)
        intra_hist, _ = np.histogram(intra_sims, bins=bins)

        max_count = max(
            np.max(inter_hist) if len(inter_sims) > 0 else 0,
            np.max(intra_hist) if len(intra_sims) > 0 else 0,
        )
        scale = 25.0 / max_count if max_count > 0 else 1.0

        for i in range(len(bins) - 1):
            label = f"{bins[i]:.1f} - {bins[i+1]:.1f}"

            inter_len = int(inter_hist[i] * scale)
            intra_len = int(intra_hist[i] * scale)

            if inter_hist[i] > 0 and inter_len == 0:
                inter_len = 1
            if intra_hist[i] > 0 and intra_len == 0:
                intra_len = 1

            inter_bar = "R" * inter_len
            intra_bar = "B" * intra_len

            inter_display = (
                f"{inter_bar} ({inter_hist[i]})" if inter_hist[i] > 0 else ""
            )
            intra_display = (
                f"{intra_bar} ({intra_hist[i]})" if intra_hist[i] > 0 else ""
            )

            line_text = f"{label:13} | {inter_display:<30} | {intra_display}"

            # Cảnh báo màu vàng/đỏ cho các khoảng điểm rủi ro cao (Chồng lấn / Nhận vơ)
            if bins[i] >= 0.4 and inter_hist[i] > 0:
                self.stdout.write(
                    self.style.ERROR(line_text)
                )  # Khác người mà điểm cao -> Lỗi nghiêm trọng
            elif bins[i] < 0.5 and intra_hist[i] > 0:
                self.stdout.write(
                    self.style.WARNING(line_text)
                )  # Cùng người mà điểm thấp -> Cảnh báo
            else:
                self.stdout.write(line_text)

        self.stdout.write("-" * 75)
        self.stdout.write(
            "💡 Ghi chú: Ký tự [R] đại diện cho False Accept (Rủi ro), [B] đại diện cho True Accept.\n"
        )

    def _get_best_shot(self, user_data_list):
        """
        Tìm ảnh tốt nhất làm image_ref.
        Dữ liệu đã được đánh giá chất lượng từ Bước 1 (AI hoặc Toán học).
        """
        if not user_data_list:
            return None, 0.0

        # Lọc ra tấm ảnh có điểm 'quality' cao nhất chỉ bằng 1 dòng code
        best_item = max(user_data_list, key=lambda x: x.get("quality", 0.0))

        return best_item["img_name"], float(best_item.get("quality", 0.0))

    def _parse_username(self, parse_mode, root, img_name):
        """Trích xuất tên đăng nhập dựa trên cấu trúc thư mục hoặc tên file."""
        if parse_mode == "folder":
            username = os.path.basename(root)
            if username == "__MACOSX" or username.startswith("."):
                return None
            return username
        else:
            match = re.match(r"^(.*?)_\d+", img_name)
            return match.group(1) if match else None

    def _process_single_image(
        self, embedder, quality_assessor, img_path, username, img_name
    ):
        """
        Đọc ảnh từ ổ cứng, gọi AI tạo vector và chấm điểm chất lượng.
        Bắt gọn toàn bộ lỗi I/O để không làm chết cả vòng lặp lớn.
        Returns:
            dict chứa vector và điểm quality, hoặc None nếu thất bại.
        """
        try:
            img_array = np.fromfile(img_path, dtype=np.uint8)
            image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

            if image is None:
                return None

            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            vector = embedder.process_image(
                img_path
            )  # LƯU Ý: Nếu process_image của bạn hỗ trợ nhận image_rgb thì nên truyền vào cho nhanh

            if vector is not None:
                quality_score = quality_assessor.assess(
                    embedder.last_cropped_face, embedder.last_kps
                )

                if quality_assessor.assessor_name == "opencv_math":
                    min_threshold = 0.60  # Toán học cần ngưỡng khắt khe hơn
                else:
                    min_threshold = 0.40  # AI LightQNet (Hoặc model AI khác)

                if quality_score < min_threshold:
                    self.stdout.write(
                        self.style.WARNING(
                            f"📉 Ảnh quá mờ/xấu (Điểm: {quality_score:.2f} < {min_threshold}): {username} -> {img_name}"
                        )
                    )
                    return None

                return {"vector": np.array(vector), "quality": quality_score}

            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"🟠 AI không tìm thấy mặt: {username} -> {img_name}"
                    )
                )
                return None

        except FileNotFoundError:
            self.stdout.write(
                self.style.ERROR(
                    f"❌ Không tìm thấy file gốc: {username} -> {img_name}"
                )
            )
        except TypeError as e:
            # Bắt chính xác lỗi file rác (đã bị OpenCV từ chối decode)
            self.stdout.write(
                self.style.ERROR(
                    f"❌ File hỏng/Rác: {username} -> {img_name} | {str(e)}"
                )
            )
        except Exception as e:
            # Bắt các lỗi dị thường khác (hết RAM, Numpy lỗi...)
            self.stdout.write(
                self.style.ERROR(
                    f"❌ Lỗi hệ thống: {username} -> {img_name} | {str(e)}"
                )
            )

    def _calculate_quality_metrics(self, temp_map_embeddings):
        """
        Xử lý toàn bộ logic Toán học về Khoảng cách Vector (Cosine Similarity).
        Tuyệt đối không chứa lệnh in (print/stdout) để đảm bảo tính tái sử dụng.

        Trả về một Dictionary chứa:
        - means: Vector trung bình của từng người
        - intra_sim_dict, soft_margin_dict: Thống kê cá nhân
        - Các chỉ số toàn cục (Hard Margin, Avg Soft Margin, ...)
        """
        metrics = {
            "means": {},
            "intra_sim_dict": {},
            "soft_margin_dict": {},
            "all_intra_sims": [],
            "all_inter_sims": [],
            "dangerous_pairs": [],
        }

        # --- A. TÍNH TOÁN NỘI BỘ (INTRA-SIMILARITY) ---
        for name, data_list in temp_map_embeddings.items():
            vectors_only = [item["vector"] for item in data_list]
            vec_stack = np.array(vectors_only)

            # Vector trung bình & Chuẩn hóa L2
            mean_vec = np.mean(vec_stack, axis=0)
            norm = np.linalg.norm(mean_vec, ord=2)
            metrics["means"][name] = mean_vec / (norm if norm > 0 else 1e-10)

            if len(vectors_only) < 2:
                continue

            # Tính ma trận tương đồng nội bộ
            intra_sim_matrix = np.dot(vec_stack, vec_stack.T)
            triu_idx = np.triu_indices(len(vectors_only), k=1)
            person_sims = intra_sim_matrix[triu_idx]

            metrics["all_intra_sims"].extend(person_sims)
            metrics["intra_sim_dict"][name] = np.mean(person_sims)

        # --- B. TÍNH TOÁN CHÉO (INTER-SIMILARITY) ---
        names = list(metrics["means"].keys())
        max_inter_per_person = {name: 0.0 for name in names}

        if len(names) >= 2:
            matrix = np.array([metrics["means"][n] for n in names])
            inter_sim_matrix = np.dot(matrix, matrix.T)

            for i in range(len(names)):
                for j in range(len(names)):
                    if (
                        i != j
                        and inter_sim_matrix[i, j] > max_inter_per_person[names[i]]
                    ):
                        max_inter_per_person[names[i]] = inter_sim_matrix[i, j]

            triu_idx = np.triu_indices(len(names), k=1)
            metrics["all_inter_sims"] = inter_sim_matrix[triu_idx].tolist()

            # Lọc Top 10 cặp nguy hiểm (Giống nhau > 0.4)
            top_indices = np.argsort(metrics["all_inter_sims"])[-10:][::-1]
            for idx in top_indices:
                s = metrics["all_inter_sims"][idx]
                if s > 0.4:
                    i, j = triu_idx[0][idx], triu_idx[1][idx]
                    metrics["dangerous_pairs"].append((names[i], names[j], s))

        # --- C. TÍNH TOÁN CÁC BIÊN ĐỘ (MARGINS) ---
        total_soft_margin, soft_margin_count = 0.0, 0
        min_soft_margin, worst_person = 1.0, ""

        for name in names:
            if name in metrics["intra_sim_dict"]:
                margin = metrics["intra_sim_dict"][name] - max_inter_per_person.get(
                    name, 0.0
                )
                metrics["soft_margin_dict"][name] = margin
                total_soft_margin += margin
                soft_margin_count += 1

                if margin < min_soft_margin:
                    min_soft_margin = margin
                    worst_person = name

        # Đóng gói số liệu thống kê tổng
        metrics["avg_intra"] = (
            np.mean(metrics["all_intra_sims"]) if metrics["all_intra_sims"] else 0.0
        )
        metrics["avg_inter"] = (
            np.mean(metrics["all_inter_sims"]) if metrics["all_inter_sims"] else 0.0
        )
        metrics["min_intra"] = (
            np.min(metrics["all_intra_sims"]) if metrics["all_intra_sims"] else 0.0
        )
        metrics["max_inter"] = (
            np.max(metrics["all_inter_sims"]) if metrics["all_inter_sims"] else 0.0
        )

        metrics["margin"] = metrics["avg_intra"] - metrics["avg_inter"]
        metrics["real_margin"] = metrics["min_intra"] - metrics["max_inter"]
        metrics["avg_soft_margin"] = (
            (total_soft_margin / soft_margin_count) if soft_margin_count > 0 else 0.0
        )
        metrics["min_soft_margin"] = min_soft_margin
        metrics["worst_person"] = worst_person

        return metrics

    def _print_quality_report(self, metrics):
        """
        Nhận số liệu từ hàm tính toán và hiển thị Dashboard ra Console.
        """
        # 1. In chi tiết Intra-sim (Nếu số người ít)
        if len(metrics["means"]) < 50:
            for name, avg_sim in metrics["intra_sim_dict"].items():
                quality = (
                    "✅ Tốt"
                    if avg_sim > 0.8
                    else ("⚠️ Tạm" if avg_sim > 0.6 else "❌ XẤU")
                )
                self.stdout.write(
                    f"👤 {name}: Avg Intra-Sim = {avg_sim:.3f} -> {quality}"
                )

        self.stdout.write(
            f"\n=> Sai số nội bộ trung bình (Intra): {metrics['avg_intra']:.3f}"
        )

        # 2. In cảnh báo các cặp nguy hiểm
        self.stdout.write("\n--- ⚔️ KIỂM TRA PHÂN BIỆT GIỮA CÁC NGƯỜI DÙNG ---")
        if metrics["dangerous_pairs"]:
            self.stdout.write("🔍 Các cặp giống nhau nhất (Tiềm ẩn rủi ro nhận vơ):")
            for name1, name2, score in metrics["dangerous_pairs"]:
                self.stdout.write(
                    self.style.WARNING(f"  - {name1} vs {name2}: {score:.3f}")
                )

        # 3. Gọi hàm vẽ Histogram (Mã ASCII bạn đã có sẵn)
        self._log_histogram_ascii(metrics["all_intra_sims"], metrics["all_inter_sims"])

        # 4. In bảng Tổng kết Margins
        self.stdout.write("-" * 50)
        self.stdout.write(
            f"=> [Trung bình] Cùng người: {metrics['avg_intra']:.3f} | Khác người: {metrics['avg_inter']:.3f}"
        )
        self.stdout.write(
            f"=> [Thực tế] Min Cùng người: {metrics['min_intra']:.3f} | Max Khác người: {metrics['max_inter']:.3f}"
        )
        self.stdout.write(f"=> Margin (Độ tách biệt): {metrics['margin']:.3f}")
        self.stdout.write(
            f"=> HARD MARGIN (Độ an toàn tuyệt đối): {metrics['real_margin']:.3f}"
        )
        self.stdout.write(
            f"=> SOFT MARGIN (Trung bình cá nhân): {metrics['avg_soft_margin']:.3f}"
        )

        if metrics["worst_person"]:
            self.stdout.write(
                f"=> Cá nhân tệ nhất: [{metrics['worst_person']}] có Soft Margin = {metrics['min_soft_margin']:.3f}"
            )

        # 5. Đánh giá chất lượng cuối cùng
        self.stdout.write("-" * 50)
        real_margin = metrics["real_margin"]
        if real_margin > 0.1:
            self.stdout.write(
                self.style.SUCCESS(
                    f"🌟 TỔNG KẾT: Model CỰC KỲ AN TOÀN! (Hard Margin: {real_margin:.2f})"
                )
            )
        elif real_margin > 0.0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ TỔNG KẾT: Model an toàn. (Hard Margin: {real_margin:.2f})"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"❌ NGUY HIỂM: Chồng lấn dữ liệu! (Hard Margin: {real_margin:.2f})"
                )
            )

        min_soft_margin = metrics["min_soft_margin"]
        if min_soft_margin > 0.1:
            self.stdout.write(
                self.style.SUCCESS(
                    f"🌟 CÁ NHÂN: Hoàn toàn an toàn! (Worst Soft Margin: {min_soft_margin:.2f})"
                )
            )
        elif min_soft_margin <= 0.0 and metrics["worst_person"]:
            self.stdout.write(
                self.style.WARNING(
                    f"❌ NGUY HIỂM: [{metrics['worst_person']}] rủi ro cao! (Soft Margin: {min_soft_margin:.2f})"
                )
            )
        self.stdout.write("-" * 50)

    def _export_to_json(
        self,
        metrics,
        temp_map_embeddings,
        detector_name,
        extractor_name,
        assessor_name,
        zip_path,
    ):
        """
        Giai đoạn 3: Đóng gói dữ liệu Vector và Metadata tốt nhất, sau đó xuất ra file JSON.

        Quy trình:
        1. Lấy Mean Vector và điểm số đánh giá từ metrics.
        2. Dùng `_get_best_shot` để nhặt ra ảnh đại diện (Best Shot) từ temp_map_embeddings.
        3. Map dữ liệu chuẩn với cấu trúc bảng FaceTemplate.
        4. Lưu ra thư mục định sẵn.
        """
        self.stdout.write("\n📦 Đang đóng gói dữ liệu ra file JSON...")

        export_data = []

        for folder_name, mean_vector in metrics["means"].items():
            intra_score = metrics["intra_sim_dict"].get(folder_name, None)
            margin_score = metrics["soft_margin_dict"].get(folder_name, None)

            user_data_list = temp_map_embeddings.get(folder_name, [])
            sample_cnt = len(user_data_list)

            vector_list = mean_vector.tolist()
            vector_dim = len(vector_list)

            best_image_name, best_quality = self._get_best_shot(user_data_list)

            enrollment_samples = []
            for item in user_data_list:
                img_name = item["img_name"]
                is_best = img_name == best_image_name

                enrollment_samples.append(
                    {
                        "image_filename": f"{folder_name}/{img_name}",  # Tên file để script Import dùng đọc ảnh vật lý
                        "quality_score": item["quality"],  # Điểm FIQA
                        "is_best_shot": is_best,  # Đánh dấu cờ True/False
                        "vector_json": item[
                            "vector"
                        ].tolist(),  # Vector lẻ để tính toán
                    }
                )

            template_record = {
                "identity_code": folder_name,
                "detector_model": detector_name,
                "extractor_model": extractor_name,
                "quality_assessor": assessor_name,
                "vector_dimension": vector_dim,
                "template_type": "primary",
                "vector_json": vector_list,  # Vector gộp (Mean)
                "image_ref": f"{folder_name}/{best_image_name}",  # Tên ảnh đại diện (Có thể bỏ nếu chỉ muốn truy xuất từ EnrollmentSample)
                "face_quality_score": best_quality,
                "is_active": True,
                "sample_count": sample_cnt,
                "intra_sim_score": intra_score,
                "soft_margin": margin_score,
                "source": "zip_seed",
                "extracted_at": timezone.now().isoformat(),
                "raw_samples": enrollment_samples,
            }
            export_data.append(template_record)

        # Xử lý đường dẫn và lưu file
        zip_filename_only = os.path.basename(zip_path).replace(".zip", "")
        output_filename = f"{zip_filename_only}_face_vectors.json"

        output_dir = os.path.join("tools", "management", "data", "exports")
        os.makedirs(output_dir, exist_ok=True)  # Đảm bảo thư mục tồn tại

        output_path = os.path.join(output_dir, output_filename)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=4)

        self.stdout.write(
            self.style.SUCCESS(
                f"🎉 Đã xuất thành công {len(export_data)} records ra file: {output_path}"
            )
        )

    def add_arguments(self, parser):
        parser.add_argument("zip_path", type=str, help="Đường dẫn tới dataset.zip")
        parser.add_argument("model_path", type=str, help="Đường dẫn tới file .tflite")
        parser.add_argument(
            "--parse-mode",
            type=str,
            default="folder",
            choices=["folder", "filename"],
            help='Cách lấy ID: "folder" (Tên thư mục) hoặc "filename" (Cắt từ tên file)',
        )
        parser.add_argument(
            "--quality_model",
            type=str,
            default="lightqnet-dm100.pb",
            help="Đường dẫn tới model AI chấm điểm (LightQNet)",
        )

    def handle(self, *args, **options):
        """
        Luồng hoạt động:
        [GIAI ĐOẠN 1: TRÍCH XUẤT DỮ LIỆU]
        1. Khởi tạo AI (Embedder, Assessor) và không gian tạm (tmpdirname).
        2. Giải nén ZIP và duyệt đệ quy qua từng file ảnh.
        3. Dùng `_process_single_image` để lấy Vector và Điểm IQA, lưu vào bộ nhớ.
        4. Dọn dẹp rác ổ cứng (shutil.rmtree).

        [GIAI ĐOẠN 2: KIỂM TOÁN TOÁN HỌC]
        5. Gọi `_calculate_quality_metrics` để tính toán Intra-sim, Inter-sim và các Biên độ an toàn (Margins).
        6. Gọi `_print_quality_report` để in Dashboard phân tích rủi ro ra màn hình.

        [GIAI ĐOẠN 3: XUẤT DỮ LIỆU]
        7. Đóng gói Vector trung bình (Mean Vector) và Metadata tốt nhất ra file JSON.
        """

        zip_path = options["zip_path"]
        model_path = options["model_path"]
        quality_model_path = options["quality_model"]

        if not os.path.exists(zip_path) or not os.path.exists(model_path):
            self.stdout.write(
                self.style.ERROR("❌ Không tìm thấy file Zip hoặc Model!")
            )
            return

        # model_name = os.path.basename(model_path).replace(".tflite", "")  # noqa: F841
        embedder = FaceEmbedderTFLite(model_path)
        quality_assessor = FaceQualityAssessor(model_path=quality_model_path)

        detector_model_name = embedder.detector_name
        extractor_model_name = embedder.extractor_name

        temp_map_embeddings = {}
        total_processed = 0
        parse_mode = options.get("parse_mode", "folder")
        tmpdirname = os.path.join(os.getcwd(), "tmp_extract_data")

        self.stdout.write("📦 Đang giải nén và xử lý ảnh...")
        start_time = time.time()

        # Xóa nếu nó đã tồn tại từ lần chạy trước bị lỗi
        if os.path.exists(tmpdirname):
            shutil.rmtree(tmpdirname)
        os.makedirs(tmpdirname)

        try:
            # 2. Giải nén vào thư mục này
            self.stdout.write(f"📦 Đang giải nén vào: {tmpdirname}")
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(tmpdirname)

            for root, _dirs, files in os.walk(tmpdirname):
                for img_name in files:
                    if not img_name.lower().endswith((".png", ".jpg", ".jpeg")):
                        continue

                    username = self._parse_username(parse_mode, root, img_name)
                    if not username:
                        self.stdout.write(
                            self.style.WARNING(f"⚠️ Bỏ qua file sai format: {img_name}")
                        )
                        continue

                    if username not in temp_map_embeddings:
                        temp_map_embeddings[username] = []

                    img_path = os.path.join(root, img_name)

                    result = self._process_single_image(
                        embedder, quality_assessor, img_path, username, img_name
                    )

                    if result:
                        temp_map_embeddings[username].append(
                            {
                                "vector": result["vector"],
                                "img_name": img_name,
                                "quality": result["quality"],
                            }
                        )
                        total_processed += 1
                        self.stdout.write(f"   + Đã xử lý: {username} -> {img_name}")
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f"🟠 Không tìm thấy/Lỗi mặt: {username} -> {img_name}"
                            )
                        )

        finally:
            if os.path.exists(tmpdirname):
                self.stdout.write("🧹 Đang dọn dẹp thư mục tạm...")
                shutil.rmtree(tmpdirname)

        total_time_ms = int((time.time() - start_time) * 1000)

        temp_map_embeddings = {
            k: v for k, v in temp_map_embeddings.items() if len(v) > 0
        }

        if not temp_map_embeddings:
            self.stdout.write(
                self.style.ERROR("❌ Không trích xuất được khuôn mặt nào!")
            )
            return

        # ==========================================
        # 2. KIỂM TRA CHẤT LƯỢNG (VALIDATE DATA QUALITY)
        # ==========================================
        self.stdout.write("\n--- 🕵️ BẮT ĐẦU KIỂM TRA CHẤT LƯỢNG DỮ LIỆU ---")

        metrics = self._calculate_quality_metrics(temp_map_embeddings)
        self._print_quality_report(metrics)

        # ==========================================
        # 3. XUẤT DỮ LIỆU RA FILE JSON (ĐỂ IMPORT SAU)
        # ==========================================
        self._export_to_json(
            metrics=metrics,
            temp_map_embeddings=temp_map_embeddings,
            detector_name=detector_model_name,
            assessor_name=quality_assessor.assessor_name,
            extractor_name=extractor_model_name,
            zip_path=zip_path,
        )

        # 4. BÁO CÁO TỔNG QUAN
        avg_time = total_time_ms / total_processed if total_processed > 0 else 0
        self.stdout.write("\n📊 BÁO CÁO HIỆU NĂNG:")
        self.stdout.write(f"- Tổng số ảnh xử lý : {total_processed}")
        self.stdout.write(f"- Tổng thời gian    : {total_time_ms} ms")
        self.stdout.write(f"- Tốc độ trung bình : {avg_time:.1f} ms/ảnh")
