"""
SSH 连接配置管理器
负责连接信息持久化、SSH密钥管理、登录日志记录
"""

import os
import json
import time
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".aiinlink")
CONNECTIONS_FILE = os.path.join(CONFIG_DIR, "connections.json")
KEYS_DIR = os.path.join(CONFIG_DIR, "keys")
LOG_FILE = os.path.join(CONFIG_DIR, "ssh_log.json")


@dataclass
class SSHConnectionProfile:
    """SSH 连接配置"""
    name: str = ""                      # 连接名称（自定义）
    host: str = ""
    port: int = 22
    username: str = "root"
    auth_type: str = "password"         # "password" | "key"
    password: str = ""                  # 密码（可加密存储）
    key_path: str = ""                  # 私钥文件路径
    key_passphrase: str = ""            # 私钥密码
    last_connected: float = 0.0         # 上次连接时间戳
    connect_count: int = 0              # 连接次数
    last_error: str = ""                # 上次错误信息
    tags: List[str] = field(default_factory=list)  # 标签

    @property
    def display_name(self) -> str:
        """显示名称"""
        if self.name:
            return self.name
        return f"{self.username}@{self.host}:{self.port}"


@dataclass
class SSHLogEntry:
    """SSH 连接日志条目"""
    timestamp: float = 0.0
    host: str = ""
    port: int = 22
    username: str = ""
    success: bool = False
    error_message: str = ""
    auth_type: str = "password"
    duration_ms: int = 0  # 连接耗时（毫秒）


class SSHConfigManager:
    """SSH 配置管理器"""

    def __init__(self):
        self._connections: Dict[str, SSHConnectionProfile] = {}
        self._log: List[SSHLogEntry] = []
        self._ensure_dirs()
        self._load()

    def _ensure_dirs(self):
        """确保配置目录存在"""
        os.makedirs(CONFIG_DIR, exist_ok=True)
        os.makedirs(KEYS_DIR, exist_ok=True)

    def _load(self):
        """加载配置"""
        # 加载连接配置
        if os.path.exists(CONNECTIONS_FILE):
            try:
                with open(CONNECTIONS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for key, values in data.items():
                    self._connections[key] = SSHConnectionProfile(**values)
            except Exception:
                pass

        # 加载日志
        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._log = [SSHLogEntry(**entry) for entry in data]
            except Exception:
                pass

    def save(self):
        """保存配置"""
        try:
            data = {key: asdict(profile) for key, profile in self._connections.items()}
            with open(CONNECTIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def save_log(self):
        """保存日志"""
        try:
            # 只保留最近 500 条日志
            recent_log = self._log[-500:] if len(self._log) > 500 else self._log
            data = [asdict(entry) for entry in recent_log]
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---- 连接配置管理 ----

    def get_all_connections(self) -> List[SSHConnectionProfile]:
        """获取所有连接配置（按最近连接时间排序）"""
        return sorted(
            self._connections.values(),
            key=lambda x: x.last_connected,
            reverse=True
        )

    def get_connection(self, key: str) -> Optional[SSHConnectionProfile]:
        """获取指定连接配置"""
        return self._connections.get(key)

    def save_connection(self, profile: SSHConnectionProfile) -> str:
        """保存连接配置，返回唯一键"""
        # 生成唯一键
        key = f"{profile.username}@{profile.host}:{profile.port}"
        existing = self._connections.get(key)
        if existing:
            # 保留历史数据
            profile.connect_count = existing.connect_count
            profile.last_connected = existing.last_connected
            profile.last_error = existing.last_error
        self._connections[key] = profile
        self.save()
        return key

    def delete_connection(self, key: str):
        """删除连接配置"""
        if key in self._connections:
            del self._connections[key]
            self.save()

    def update_connect_result(self, key: str, success: bool, error: str = ""):
        """更新连接结果"""
        profile = self._connections.get(key)
        if profile:
            profile.last_connected = time.time()
            profile.connect_count += 1
            if not success:
                profile.last_error = error
            else:
                profile.last_error = ""
            self.save()

    # ---- SSH 密钥管理 ----

    def import_key(self, key_path: str, name: str = "") -> str:
        """
        导入 SSH 密钥到管理目录
        返回新的密钥路径
        """
        if not os.path.exists(key_path):
            raise FileNotFoundError(f"密钥文件不存在: {key_path}")

        # 确定新路径
        if not name:
            name = os.path.basename(key_path)
        new_path = os.path.join(KEYS_DIR, name)

        # 复制文件
        with open(key_path, "r", encoding="utf-8") as f:
            content = f.read()
        with open(new_path, "w", encoding="utf-8") as f:
            f.write(content)

        # 设置权限（仅限 Unix 系统）
        try:
            os.chmod(new_path, 0o600)
        except (OSError, AttributeError):
            pass  # Windows 不支持

        return new_path

    def list_keys(self) -> List[str]:
        """列出已导入的密钥"""
        if not os.path.exists(KEYS_DIR):
            return []
        return [f for f in os.listdir(KEYS_DIR) if os.path.isfile(os.path.join(KEYS_DIR, f))]

    def delete_key(self, name: str):
        """删除密钥"""
        path = os.path.join(KEYS_DIR, name)
        if os.path.exists(path):
            os.remove(path)

    # ---- 日志管理 ----

    def add_log(self, entry: SSHLogEntry):
        """添加日志条目"""
        self._log.append(entry)
        self.save_log()

    def log_connect(self, profile: SSHConnectionProfile, success: bool,
                    error: str = "", duration_ms: int = 0):
        """记录连接日志"""
        entry = SSHLogEntry(
            timestamp=time.time(),
            host=profile.host,
            port=profile.port,
            username=profile.username,
            success=success,
            error_message=error,
            auth_type=profile.auth_type,
            duration_ms=duration_ms,
        )
        self.add_log(entry)
        self.update_connect_result(
            f"{profile.username}@{profile.host}:{profile.port}",
            success, error
        )

    def get_log(self, limit: int = 50) -> List[SSHLogEntry]:
        """获取最近日志"""
        return list(reversed(self._log[-limit:]))

    def get_error_log(self, limit: int = 50) -> List[SSHLogEntry]:
        """获取错误日志"""
        errors = [e for e in self._log if not e.success]
        return list(reversed(errors[-limit:]))
