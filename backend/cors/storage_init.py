"""存储初始化模块 - 缓存、文件、临时文件"""
import os
import sys
import time
import hashlib
import tempfile
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from loguru import logger
from config import settings
from backend.cors.log_init import get_logger


class StorageManager:
    """存储管理器"""

    def __init__(self):
        self.root = Path(settings.STORAGE_ROOT).resolve()
        self.cache_dir = self.root / settings.CACHE_DIR
        self.sessions_dir = self.root / settings.SESSIONS_DIR
        self.uploads_dir = self.root / settings.UPLOADS_DIR
        self.downloads_dir = self.root / settings.DOWNLOADS_DIR
        self.exports_dir = self.root / settings.EXPORTS_DIR
        self.temp_dir = self.root / settings.TEMP_DIR

        # 确保所有目录存在
        for d in [
            self.cache_dir,
            self.sessions_dir,
            self.uploads_dir,
            self.downloads_dir,
            self.exports_dir,
            self.temp_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def cache_set(self, key: str, data: bytes, ttl: int = None) -> str:
        """设置缓存"""
        ttl = ttl or settings.CACHE_TTL
        cache_key = hashlib.md5(key.encode()).hexdigest()
        cache_file = self.cache_dir / f"{cache_key}.cache"

        expire_at = int(time.time()) + ttl
        with open(cache_file, "wb") as f:
            f.write(expire_at.to_bytes(8, "big"))
            f.write(data)

        logger.debug(f"Cache set: {key}")
        return str(cache_file)

    def cache_get(self, key: str) -> Optional[bytes]:
        """获取缓存，过期返回 None"""
        cache_key = hashlib.md5(key.encode()).hexdigest()
        cache_file = self.cache_dir / f"{cache_key}.cache"

        if not cache_file.exists():
            return None

        with open(cache_file, "rb") as f:
            expire_at = int.from_bytes(f.read(8), "big")
            if time.time() > expire_at:
                cache_file.unlink()
                return None
            return f.read()

    def cache_delete(self, key: str) -> bool:
        """删除缓存"""
        cache_key = hashlib.md5(key.encode()).hexdigest()
        cache_file = self.cache_dir / f"{cache_key}.cache"
        if cache_file.exists():
            cache_file.unlink()
            return True
        return False

    def cache_clear(self) -> int:
        """清空所有缓存"""
        global_log = get_logger("global")
        count = sum(1 for f in self.cache_dir.glob("*.cache") if f.unlink() is None or True)
        global_log.info(f"Cache cleared: {count} files")
        return count

    def save_upload(self, file_content: bytes, filename: str) -> str:
        """保存上传文件"""
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {ext}")

        unique_name = f"{int(time.time())}_{filename}"
        filepath = self.uploads_dir / unique_name

        with open(filepath, "wb") as f:
            f.write(file_content)

        global_log = get_logger("global")
        global_log.info(f"File uploaded: {filepath}")
        return str(filepath)

    def create_temp(self, prefix: str = "tmp", suffix: str = "") -> Path:
        """创建临时文件"""
        fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=str(self.temp_dir))
        os.close(fd)
        return Path(path)

    def cleanup_temp(self, max_age: int = None) -> int:
        """清理过期临时文件"""
        global_log = get_logger("global")
        
        max_age = max_age or settings.TEMP_MAX_AGE
        now = time.time()
        count = 0

        for f in self.temp_dir.iterdir():
            if f.is_file() and (now - f.stat().st_mtime) > max_age:
                f.unlink()
                count += 1

        if count:
            global_log.info(f"Temp cleanup: {count} files")
        return count

    def save_export(self, content: bytes, filename: str) -> str:
        """保存导出文件"""
        global_log = get_logger("global")
        
        filepath = self.exports_dir / filename
        with open(filepath, "wb") as f:
            f.write(content)
        global_log.info(f"Export saved: {filepath}")
        return str(filepath)


# 全局单例
_storage = None


def get_storage() -> StorageManager:
    """获取存储管理器单例"""
    global _storage
    if _storage is None:
        _storage = StorageManager()
    return _storage


def init_storage():
    """初始化存储模块（创建目录）"""
    return get_storage()
