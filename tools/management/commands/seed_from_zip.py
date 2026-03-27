import json
import os
import re
import shutil
import time
import zipfile

import cv2
import numpy as np
from django.core.management.base import BaseCommand
from django.db import transaction  # noqa: F401
from django.utils import timezone

from custom_account.models import (  # noqa: F401
    BiometricCredential,
    FaceTemplate,
    Profile,
)
from tools.management.commands.ai_service import (
    FaceEmbedderTFLite,
)


class Command(BaseCommand):
    help = "Xử lý file Zip ảnh, đánh giá chất lượng model và lưu Face Embeddings vào DB"

    def _log_histogram_ascii(self, intra_sims, inter_sims):
        """Hiển thị phân phối độ tương đồng dưới dạng văn bản (ASCII Histogram)"""
        self.stdout.write(
            "\n📊 BIỂU ĐỒ PHÂN PHỐI ĐỘ TƯƠNG ĐỒNG (SIMILARITY DISTRIBUTION)"
        )
        self.stdout.write(
            "Khoảng giá trị | [Khác người (Inter)]  vs  [Cùng người (Intra)]"
        )
        self.stdout.write("-" * 65)

        # Định nghĩa các khoảng bins (ví dụ: 0.1, 0.2, ..., 1.0)
        bins = np.linspace(0, 1, 11)
        inter_hist, _ = np.histogram(inter_sims, bins=bins)
        intra_hist, _ = np.histogram(intra_sims, bins=bins)

        # Chuẩn hóa để vẽ thanh (độ dài max là 30 ký tự)
        max_val = (
            max(np.max(inter_hist), np.max(intra_hist)) if len(inter_sims) > 0 else 1
        )
        scale = 25 / max_val if max_val > 0 else 1

        for i in range(len(bins) - 1):
            label = f"{bins[i]:.1f} - {bins[i+1]:.1f}"

            # Vẽ thanh cho Inter (Khác người)
            inter_bar = "R" * int(inter_hist[i] * scale)
            # Vẽ thanh cho Intra (Cùng người)
            intra_bar = "B" * int(intra_hist[i] * scale)

            # Format dòng log
            line = f"{label:11} | {inter_bar:25} | {intra_bar}"

            # Tô màu nhẹ cho dễ nhìn nếu dùng self.style
            if bins[i] >= 0.5:  # Khu vực nhạy cảm
                self.stdout.write(self.style.WARNING(line))
            else:
                self.stdout.write(line)

        self.stdout.write("-" * 65)
        self.stdout.write("Ghi chú: [R] = Khác người (Red), [B] = Cùng người (Blue)\n")

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
            "--pre-cropped",
            action="store_true",
            help="Bật nếu file zip chứa ảnh đã crop sẵn (Bỏ qua InsightFace)",
        )

    def handle(self, *args, **options):
        zip_path = options["zip_path"]
        model_path = options["model_path"]

        if not os.path.exists(zip_path) or not os.path.exists(model_path):
            self.stdout.write(
                self.style.ERROR("❌ Không tìm thấy file Zip hoặc Model!")
            )
            return

        model_name = os.path.basename(model_path).replace(".tflite", "")  # noqa: F841
        embedder = FaceEmbedderTFLite(model_path)

        temp_map_embeddings = {}
        total_images_processed = 0

        self.stdout.write("📦 Đang giải nén và xử lý ảnh...")
        start_time = time.time()

        tmpdirname = os.path.join(os.getcwd(), "tmp_extract_data")

        # Xóa nếu nó đã tồn tại từ lần chạy trước bị lỗi
        if os.path.exists(tmpdirname):
            shutil.rmtree(tmpdirname)
        os.makedirs(tmpdirname)

        parse_mode = options.get("parse_mode", "folder")

        try:
            # 2. Giải nén vào thư mục này
            self.stdout.write(f"📦 Đang giải nén vào: {tmpdirname}")
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(tmpdirname)

            # 3. Duyệt qua các thư mục (Giữ nguyên logic của bạn)
            for root, _dirs, files in os.walk(tmpdirname):
                for img_name in files:
                    if not img_name.lower().endswith((".png", ".jpg", ".jpeg")):
                        continue

                    if img_name.startswith("._") or img_name == ".DS_Store":
                        continue

                    if parse_mode == "folder":
                        username = os.path.basename(root)
                        if username == "__MACOSX" or username.startswith("."):
                            continue
                    else:  # parse_mode == 'filename'
                        # Dùng Regex để cắt mọi thứ trước cụm gạch dưới + chữ số (VD: _000028)
                        # Bui_Hoang_Danh_000028_png... -> Bui_Hoang_Danh
                        match = re.match(r"^(.*?)_\d+", img_name)
                        if match:
                            username = match.group(1)
                        else:
                            # Nếu có file nào đặt tên không đúng format, báo lỗi rồi bỏ qua
                            self.stdout.write(
                                self.style.WARNING(
                                    f"⚠️ Bỏ qua file không đúng định dạng tên: {img_name}"
                                )
                            )
                            continue

                    if username not in temp_map_embeddings:
                        temp_map_embeddings[username] = []

                    img_path = os.path.join(root, img_name)

                    try:
                        img_array = np.fromfile(img_path, dtype=np.uint8)

                        # 3. Dùng OpenCV giải mã từ mảng RAM thay vì đọc từ ổ cứng
                        image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

                        if image is None:
                            raise TypeError(
                                "OpenCV không thể giải mã (File rác hoặc sai định dạng ảnh)."
                            )

                        # # Đảm bảo ảnh luôn ở hệ màu RGB (nếu model của bạn yêu cầu)
                        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

                        # Gọi AI Service xử lý
                        vector = embedder.process_image(img_path)

                        if vector is not None:
                            temp_map_embeddings[username].append(np.array(vector))
                            total_images_processed += 1
                            self.stdout.write(
                                f"   + Đã xử lý: {username} -> {img_name}"
                            )
                        else:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"🟠 AI không tìm thấy mặt: {username} -> {img_name}"
                                )
                            )

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

        finally:
            # 4. QUAN TRỌNG: Dọn dẹp sau khi xong (giống như TemporaryDirectory đã làm)
            if os.path.exists(tmpdirname):
                self.stdout.write("🧹 Đang dọn dẹp thư mục tạm...")
                shutil.rmtree(
                    tmpdirname
                )  # Bạn có thể comment dòng này nếu muốn giữ lại để debug

        total_time_ms = int((time.time() - start_time) * 1000)

        # Lọc bỏ những user không có ảnh nào thành công
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

        # A. INTRA-SIMILARITY (Độ ổn định của 1 người)
        all_intra_sims = []
        means = {}

        for name, vectors in temp_map_embeddings.items():
            vec_stack = np.array(vectors)  # Shape: (Số ảnh, 512)

            # Tính vector trung bình và chuẩn hóa để dùng cho so sánh chéo
            mean_vec = np.mean(vec_stack, axis=0)
            norm = np.linalg.norm(mean_vec, ord=2)
            means[name] = mean_vec / (norm if norm > 0 else 1e-10)

            if len(vectors) < 2:
                continue

            # Tính Intra-similarity bằng ma trận (Tất cả cặp trong 1 người)
            # Dot product của matrix với chính nó chuyển vị
            intra_sim_matrix = np.dot(vec_stack, vec_stack.T)
            # Lấy các giá trị tam giác trên (loại bỏ đường chéo chính)
            triu_idx = np.triu_indices(len(vectors), k=1)
            person_sims = intra_sim_matrix[triu_idx]

            avg_sim = np.mean(person_sims)
            all_intra_sims.extend(person_sims)

            if len(temp_map_embeddings) < 50:  # Chỉ in chi tiết nếu số lượng người ít
                quality = (
                    "✅ Tốt"
                    if avg_sim > 0.8
                    else ("⚠️ Tạm" if avg_sim > 0.6 else "❌ XẤU")
                )
                self.stdout.write(
                    f"👤 {name}: Avg Intra-Sim = {avg_sim:.3f} -> {quality}"
                )

        avg_intra = np.mean(all_intra_sims) if all_intra_sims else 0.0
        self.stdout.write(f"\n=> Sai số nội bộ trung bình (Intra): {avg_intra:.3f}")

        # B. INTER-SIMILARITY (Độ phân biệt giữa các người)
        self.stdout.write("\n--- ⚔️ KIỂM TRA PHÂN BIỆT GIỮA CÁC NGƯỜI DÙNG ---")

        names = list(means.keys())
        max_inter = 0.0

        if len(names) >= 2:
            matrix = np.array([means[name] for name in names])  # Shape: (N, 512)
            # Nhân ma trận khổng lồ: (N, 512) x (512, N) -> (N, N)
            inter_sim_matrix = np.dot(matrix, matrix.T)

            max_inter_per_person = {name: 0.0 for name in names}
            for i in range(len(names)):
                for j in range(len(names)):
                    if i != j:
                        sim = inter_sim_matrix[i, j]
                        if sim > max_inter_per_person[names[i]]:
                            max_inter_per_person[names[i]] = sim

            triu_idx = np.triu_indices(len(names), k=1)
            all_inter_sims = inter_sim_matrix[triu_idx]

            avg_inter = np.mean(all_inter_sims)
            max_inter = np.max(all_inter_sims)

            total_soft_margin = 0.0
            soft_margin_count = 0
            min_soft_margin = 1.0
            worst_person = ""
            intra_sim_dict = {}
            soft_margin_dict = {}

            for name in names:
                # Nếu người này có > 1 ảnh, lấy Avg Intra của họ. Nếu chỉ có 1 ảnh, bỏ qua việc tính Soft Margin
                if name in temp_map_embeddings and len(temp_map_embeddings[name]) > 1:
                    vec_stack = np.array(temp_map_embeddings[name])
                    intra_sim_matrix_person = np.dot(vec_stack, vec_stack.T)
                    person_triu_idx = np.triu_indices(len(vec_stack), k=1)
                    person_avg_intra = np.mean(intra_sim_matrix_person[person_triu_idx])

                    person_max_inter = max_inter_per_person[name]
                    person_margin = person_avg_intra - person_max_inter

                    intra_sim_dict[name] = person_avg_intra
                    soft_margin_dict[name] = person_margin

                    total_soft_margin += person_margin
                    soft_margin_count += 1

                    if person_margin < min_soft_margin:
                        min_soft_margin = person_margin
                        worst_person = name

            # Tìm Top 10 cặp nguy hiểm nhất
            top_indices = np.argsort(all_inter_sims)[-10:][::-1]
            self.stdout.write("🔍 Top 10 cặp giống nhau nhất (Tiềm ẩn rủi ro):")
            for idx in top_indices:
                i, j = triu_idx[0][idx], triu_idx[1][idx]
                s = all_inter_sims[idx]
                if s > 0.4:
                    self.stdout.write(
                        self.style.WARNING(f"  - {names[i]} vs {names[j]}: {s:.3f}")
                    )

            # Vẽ biểu đồ Histogram
            self._log_histogram_ascii(all_intra_sims, all_inter_sims)

            min_intra = np.min(all_intra_sims) if all_intra_sims else 0.0
            avg_soft_margin = (
                (total_soft_margin / soft_margin_count)
                if soft_margin_count > 0
                else 0.0
            )
            margin = avg_intra - avg_inter

            real_margin = min_intra - max_inter
            self.stdout.write("-" * 50)
            self.stdout.write(
                f"=> [Trung bình] Cùng người: {avg_intra:.3f} | Khác người: {avg_inter:.3f}"
            )
            self.stdout.write(
                f"=> [Thực tế] Min Cùng người: {min_intra:.3f} | Max Khác người: {max_inter:.3f}"
            )
            self.stdout.write(f"=> Margin (Độ tách biệt): {margin:.3f}")
            self.stdout.write(
                f"=> HARD MARGIN (Độ an toàn tuyệt đối): {real_margin:.3f}"
            )
            self.stdout.write(
                f"=> SOFT MARGIN (Trung bình cá nhân): {avg_soft_margin:.3f}"
            )
            self.stdout.write(
                f"=> Cá nhân tệ nhất: [{worst_person}] có Soft Margin = {min_soft_margin:.3f}"
            )

        if real_margin > 0.1:
            self.stdout.write(
                self.style.SUCCESS(
                    f"🌟 TỔNG KẾT: Model CỰC KỲ AN TOÀN! Không có điểm mù. (Hard Margin: {real_margin:.2f})"
                )
            )
        elif real_margin > 0.0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ TỔNG KẾT: Model an toàn, có thể set ngưỡng phân chia. (Hard Margin: {real_margin:.2f})"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"❌ NGUY HIỂM: Có sự chồng lấn! Nguy cơ nhận nhầm cực cao. (Hard Margin: {real_margin:.2f})"
                )
            )
        self.stdout.write("-" * 50)

        if min_soft_margin > 0.1:
            self.stdout.write(
                self.style.SUCCESS(
                    f"🌟 TỔNG KẾT: Model CỰC KỲ AN TOÀN! (Worst Soft Margin: {min_soft_margin:.2f})"
                )
            )
        elif min_soft_margin > 0.0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ TỔNG KẾT: Model an toàn cho TẤT CẢ mọi người. (Worst Soft Margin: {min_soft_margin:.2f})"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"❌ NGUY HIỂM: [{worst_person}] có nguy cơ bị nhận nhầm cao! (Soft Margin: {min_soft_margin:.2f})"
                )
            )
        self.stdout.write("-" * 50)

        if margin > 0.4:
            self.stdout.write(
                self.style.SUCCESS(
                    f"🌟 TỔNG KẾT: Model phân biệt RẤT TỐT! (Margin: {margin:.2f})"
                )
            )
        elif margin > 0.2:
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ TỔNG KẾT: Model hoạt động ỔN. (Margin: {margin:.2f})"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"⚠️ TỔNG KẾT: Cảnh báo, dữ liệu khó phân biệt. (Margin: {margin:.2f})"
                )
            )
        self.stdout.write("-" * 50)

        # # ==========================================
        # # 3. LƯU DATABASE (DÙNG VECTOR TRUNG BÌNH)
        # # ==========================================
        # self.stdout.write("\n💾 Đang lưu vector trung bình vào Database...")
        # db_saved_count = 0

        # with transaction.atomic():
        #     # 1. Lấy TẤT CẢ Profile liên quan trong 1 query duy nhất
        #     profiles = Profile.objects.filter(
        #         identity_code__in=means.keys()
        #     ).select_related("user")
        #     profile_map = {p.identity_code: p for p in profiles}

        #     # Báo cáo những user không tồn tại trong hệ thống
        #     missing_codes = set(means.keys()) - set(profile_map.keys())
        #     for code in missing_codes:
        #         self.stdout.write(
        #             self.style.WARNING(f'⚠️ DB Bỏ qua: User "{code}" không tồn tại.')
        #         )

        #     if not profile_map:
        #         self.stdout.write(
        #             self.style.ERROR("❌ Không có user nào hợp lệ để lưu Database!")
        #         )
        #         return

        #     # Danh sách user_ids hợp lệ
        #     user_ids = [p.user_id for p in profile_map.values()]

        #     # BƯỚC 2: Xử lý BiometricCredential (Bulk Create nếu chưa có)
        #     existing_bios = BiometricCredential.objects.filter(user_id__in=user_ids)
        #     bio_map = {bio.user_id: bio for bio in existing_bios}

        #     bios_to_create = []
        #     for uid in user_ids:
        #         if uid not in bio_map:
        #             bios_to_create.append(BiometricCredential(user_id=uid))

        #     if bios_to_create:
        #         BiometricCredential.objects.bulk_create(bios_to_create)
        #         # Fetch lại để lấy ID (do DB sinh ra)
        #         existing_bios = BiometricCredential.objects.filter(user_id__in=user_ids)
        #         bio_map = {bio.user_id: bio for bio in existing_bios}

        #     # BƯỚC 3: Xử lý FaceTemplate (Bulk Upsert cho PostgreSQL)
        #     templates_to_upsert = []
        #     for folder_name, mean_vector in means.items():
        #         if folder_name not in profile_map:
        #             continue

        #         user_id = profile_map[folder_name].user_id
        #         bio = bio_map[user_id]

        #         templates_to_upsert.append(
        #             FaceTemplate(
        #                 biometric_id=bio.id,
        #                 model_name=model_name,
        #                 template_type="primary",
        #                 vector=mean_vector.tolist(),
        #             )
        #         )

        #     if templates_to_upsert:
        #         # Tính năng ON CONFLICT của PostgreSQL (Siêu nhanh)
        #         FaceTemplate.objects.bulk_create(
        #             templates_to_upsert,
        #             update_conflicts=True,  # Nếu trùng lặp thì sẽ Update thay vì văng lỗi
        #             unique_fields=[
        #                 "biometric",
        #                 "model_name",
        #                 "template_type",
        #             ],  # Bộ key để xác định sự trùng lặp
        #             update_fields=[
        #                 "vector"
        #             ],  # Nếu trùng thì chỉ đè dữ liệu mới vào cột vector này
        #         )
        #         db_saved_count += len(templates_to_upsert)

        #     self.stdout.write(
        #         self.style.SUCCESS(
        #             f"🎉 Đã nạp thành công {db_saved_count} users vào Database!"
        #         )
        #     )

        #     if True:
        #         # Ép PostgreSQL hoàn tác toàn bộ các lệnh bulk_create vừa chạy ở trên!
        #         transaction.set_rollback(True)
        #         self.stdout.write(
        #             self.style.WARNING(
        #                 "🔄 ĐÃ CHẠY ROLLBACK: Không có dữ liệu nào được lưu thật vào DB."
        #             )
        #         )

        # ==========================================
        # 3. XUẤT DỮ LIỆU RA FILE JSON (ĐỂ IMPORT SAU)
        # ==========================================
        self.stdout.write("\n📦 Đang đóng gói dữ liệu ra file JSON...")

        export_data = []

        for folder_name, mean_vector in means.items():
            # Lấy các thông số chất lượng từ Bước 2 (Nếu người đó chỉ có 1 ảnh thì mặc định điểm là None/0)
            intra_score = intra_sim_dict.get(folder_name, None)
            margin_score = soft_margin_dict.get(folder_name, None)
            sample_cnt = len(temp_map_embeddings.get(folder_name, []))

            # Tạo dictionary đúng chuẩn các field của model FaceTemplate
            template_record = {
                "identity_code": folder_name,  # Giữ cái này làm khóa ngoại giả (Pseudo-Foreign Key)
                "model_name": model_name,
                "template_type": "primary",
                "vector": mean_vector.tolist(),
                "is_active": True,
                "sample_count": sample_cnt,
                "intra_sim_score": intra_score,
                "soft_margin": margin_score,
                "source": "zip_seed",
                "extracted_at": timezone.now().isoformat(),  # Lưu lại thời điểm chạy script
            }
            export_data.append(template_record)

        zip_filename_only = os.path.basename(zip_path).replace(".zip", "")

        # Lưu ra file JSON trong cùng thư mục data
        output_filename = f"{zip_filename_only}_face_vectors.json"
        output_dir = os.path.join("tools", "management", "data", "exports")
        os.makedirs(output_dir, exist_ok=True)  # Đảm bảo thư mục tồn tại

        output_path = os.path.join(output_dir, output_filename)

        with open(output_path, "w", encoding="utf-8") as f:
            # Ghi ra file JSON (indent=4 để format đẹp, dễ đọc bằng mắt người)
            json.dump(export_data, f, ensure_ascii=False, indent=4)

        self.stdout.write(
            self.style.SUCCESS(
                f"🎉 Đã xuất thành công {len(export_data)} records ra file: {output_path}"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                "=> Chạy xong hoàn toàn! Bạn có thể cất file JSON này đi."
            )
        )

        # 4. BÁO CÁO TỔNG QUAN
        avg_time = (
            total_time_ms / total_images_processed if total_images_processed > 0 else 0
        )
        self.stdout.write("\n📊 BÁO CÁO HIỆU NĂNG:")
        self.stdout.write(f"- Tổng số ảnh xử lý : {total_images_processed}")
        self.stdout.write(f"- Tổng thời gian    : {total_time_ms} ms")
        self.stdout.write(f"- Tốc độ trung bình : {avg_time:.1f} ms/ảnh")
        # self.stdout.write(
        #     self.style.SUCCESS(
        #         f"🎉 Đã nạp thành công {db_saved_count} users vào Database!"
        #     )
        # )
