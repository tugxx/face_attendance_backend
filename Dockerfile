# Dùng bản Python nhẹ (Bạn có thể đổi thành 3.10, 3.11, 3.12 tùy máy bạn)
FROM python:3.13-slim

# Bật chế độ in log trực tiếp (không bị lưu đệm)
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copy file thư viện vào và cài đặt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Lưu ý: Không cần copy toàn bộ code vào đây vì lát nữa ta sẽ ánh xạ (mount) ổ đĩa