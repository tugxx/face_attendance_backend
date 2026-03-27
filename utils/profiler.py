import logging
import time

logger = logging.getLogger(__name__)


class TimeProfiler:
    """Công cụ đo thời gian chạy của một block code cực Clean"""

    def __init__(self, block_name):
        self.block_name = block_name

    def __enter__(self):
        self.start_time = time.perf_counter()  # perf_counter đo chính xác đến mili-giây
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed_time = time.perf_counter() - self.start_time
        logger.info(f"⏱️ [PROFILER] {self.block_name} mất: {elapsed_time:.4f} giây")
