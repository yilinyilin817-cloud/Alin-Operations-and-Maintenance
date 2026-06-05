"""
定时任务模块
- Cron 表达式支持（标准 5 段：分 时 日 月 周）
- 任务类型：执行命令 / 健康检查 / 采集指标 / 文件分发
- 启用/禁用、上次执行、下次执行、运行历史
- 调度器在后台线程中每分钟检查一次

持久化：~/.aiinlink/scheduled_tasks.json
"""

import json
import os
import re
import time
import threading
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Callable

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
    QPlainTextEdit, QCheckBox, QSplitter, QMessageBox, QFrame, QListWidget,
    QListWidgetItem, QTabWidget, QDateTimeEdit, QTextEdit,
)

from PySide6.QtCore import QDateTime

from app.theme import (
    BG_DEEP, BG_PANEL, BG_PANEL_HOVER, BG_INPUT,
    FG_PRIMARY, FG_SECONDARY, FG_TERTIARY, FG_DISABLED,
    PRIMARY, SUCCESS, WARN, DANGER, INFO,
    BORDER, BORDER_LIGHT,
    FONT_FAMILY, FONT_SIZE_BASE, FONT_SIZE_SM, FONT_SIZE_MD,
    RADIUS_SM, RADIUS_MD, RADIUS_LG,
)


TASKS_DIR = os.path.join(os.path.expanduser("~"), ".aiinlink")
TASKS_FILE = os.path.join(TASKS_DIR, "scheduled_tasks.json")
TASK_RUNS_FILE = os.path.join(TASKS_DIR, "task_runs.json")
MAX_RUN_ENTRIES = 5000


# ============================================================
# Cron 表达式解析
# ============================================================

class CronExpression:
    """5 段标准 Cron 表达式解析与匹配"""

    def __init__(self, expr: str):
        self.expr = expr.strip()
        self.parts = self.expr.split()
        if len(self.parts) != 5:
            raise ValueError(f"Cron 表达式必须是 5 段: {expr}")
        self.minute = self._parse_field(self.parts[0], 0, 59)
        self.hour = self._parse_field(self.parts[1], 0, 23)
        self.day = self._parse_field(self.parts[2], 1, 31)
        self.month = self._parse_field(self.parts[3], 1, 12)
        self.weekday = self._parse_field(self.parts[4], 0, 6)

    @staticmethod
    def _parse_field(field: str, min_v: int, max_v: int) -> set:
        """解析单个字段，支持 * , - /"""
        result = set()
        for part in field.split(","):
            step = 1
            if "/" in part:
                range_part, step_str = part.split("/", 1)
                step = int(step_str)
            else:
                range_part = part
            if range_part == "*":
                start, end = min_v, max_v
            elif "-" in range_part:
                start_s, end_s = range_part.split("-", 1)
                start, end = int(start_s), int(end_s)
            else:
                v = int(range_part)
                start, end = v, v
            for x in range(start, end + 1, step):
                if min_v <= x <= max_v:
                    result.add(x)
        return result

    def matches(self, dt: datetime) -> bool:
        return (
            dt.minute in self.minute and
            dt.hour in self.hour and
            dt.day in self.day and
            dt.month in self.month and
            dt.weekday() in self.weekday
        )

    def next_run_after(self, after: datetime) -> datetime:
        """计算下一次执行时间（粗略：分钟级扫描，最多 366*24*60 次）"""
        dt = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(366 * 24 * 60):
            if self.matches(dt):
                return dt
            dt += timedelta(minutes=1)
        return after

    def human_readable(self) -> str:
        """生成可读描述"""
        def desc(field_set, name, max_v):
            if field_set == set(range(0, max_v + 1)):
                return f"每{name}"
            if len(field_set) == 1:
                v = list(field_set)[0]
                return f"{name}={v}"
            return f"{name}∈[{','.join(str(x) for x in sorted(field_set)[:3])}{'...' if len(field_set)>3 else ''}]"
        return (
            f"{desc(self.minute, '分', 59)} · {desc(self.hour, '时', 23)} · "
            f"{desc(self.day, '日', 31)} · {desc(self.month, '月', 12)} · "
            f"{desc(self.weekday, '周', 6)}"
        )


# ============================================================
# 任务定义
# ============================================================

class ScheduledTask:
    """一个定时任务"""

    def __init__(self, name: str, cron: str, action_type: str, action_params: dict,
                 enabled: bool = True, description: str = ""):
        self.id = f"task_{int(time.time()*1000)}"
        self.name = name
        self.cron = cron
        self.cron_obj = CronExpression(cron) if cron else None
        self.action_type = action_type  # command / health_check / metrics / file_sync
        self.action_params = action_params
        self.enabled = enabled
        self.description = description
        self.created_at = time.time()
        self.last_run: Optional[float] = None
        self.last_run_str: Optional[str] = None
        self.last_status: Optional[str] = None
        self.last_duration: Optional[float] = None
        self.run_count: int = 0
        self.success_count: int = 0
        self.fail_count: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "cron": self.cron,
            "action_type": self.action_type, "action_params": self.action_params,
            "enabled": self.enabled, "description": self.description,
            "created_at": self.created_at, "last_run": self.last_run,
            "last_run_str": self.last_run_str, "last_status": self.last_status,
            "last_duration": self.last_duration, "run_count": self.run_count,
            "success_count": self.success_count, "fail_count": self.fail_count,
        }

    @staticmethod
    def from_dict(d: dict) -> "ScheduledTask":
        t = ScheduledTask(
            d.get("name", ""), d.get("cron", ""), d.get("action_type", "command"),
            d.get("action_params", {}), d.get("enabled", True),
            d.get("description", ""),
        )
        t.id = d.get("id", t.id)
        t.created_at = d.get("created_at", t.created_at)
        t.last_run = d.get("last_run")
        t.last_run_str = d.get("last_run_str")
        t.last_status = d.get("last_status")
        t.last_duration = d.get("last_duration")
        t.run_count = d.get("run_count", 0)
        t.success_count = d.get("success_count", 0)
        t.fail_count = d.get("fail_count", 0)
        try:
            t.cron_obj = CronExpression(t.cron)
        except Exception:
            t.cron_obj = None
        return t

    def next_run_str(self) -> str:
        if not self.cron_obj:
            return "无效 Cron"
        nxt = self.cron_obj.next_run_after(datetime.now())
        return nxt.strftime("%Y-%m-%d %H:%M:%S")


# ============================================================
# 任务执行器
# ============================================================

class TaskExecutor:
    """执行任务的具体动作"""

    @staticmethod
    def execute(task: ScheduledTask, asset) -> tuple:
        """执行任务，返回 (status, message)"""
        status = "ok"
        message = ""
        try:
            if task.action_type == "command":
                # 执行 SSH 命令
                params = task.action_params
                target = params.get("target_host", "")
                host = asset.get_host(target) if target else None
                if not host and asset.all_hosts():
                    host = asset.all_hosts()[0]
                if not host:
                    return ("fail", "无可用主机")
                cmd = params.get("command", "")
                from app.workers import SSHCommandWorker
                w = SSHCommandWorker(
                    host=host["host"], port=host.get("port", 22),
                    username=host.get("username", "root"),
                    command=cmd,
                    auth_type=host.get("auth_type", "password"),
                    password=host.get("password", ""),
                    key_path=host.get("key_path", ""),
                    key_passphrase=host.get("key_passphrase", ""),
                    timeout=params.get("timeout", 30),
                )
                # 同步等待结果
                result_holder = []
                w.result_ready.connect(lambda h, o, e: result_holder.append((h, o, e)))
                w.start()
                w.wait(60)
                if not result_holder:
                    return ("fail", "执行超时")
                h, out, err = result_holder[0]
                if err and not out:
                    return ("fail", f"错误: {err[:200]}")
                return ("ok", f"输出: {out[:200]}")
            elif task.action_type == "health_check":
                # 检查目标主机连通性
                params = task.action_params
                target = params.get("target_host", "")
                host = asset.get_host(target) if target else None
                if not host:
                    return ("fail", "主机不存在")
                from app.workers import SSHCommandWorker
                w = SSHCommandWorker(
                    host=host["host"], port=host.get("port", 22),
                    username=host.get("username", "root"),
                    command="echo __OK__",
                    auth_type=host.get("auth_type", "password"),
                    password=host.get("password", ""),
                    key_path=host.get("key_path", ""),
                    key_passphrase=host.get("key_passphrase", ""),
                    timeout=10,
                )
                r = []
                w.result_ready.connect(lambda h, o, e: r.append((h, o, e)))
                w.start()
                w.wait(20)
                if r and "__OK__" in r[0][1]:
                    return ("ok", f"{host.get('name')} 健康")
                return ("fail", f"{host.get('name')} 不可达")
            elif task.action_type == "metrics":
                # 采集指标
                params = task.action_params
                target = params.get("target_host", "")
                host = asset.get_host(target) if target else None
                if not host:
                    return ("fail", "主机不存在")
                from app.workers import SSHMetricsWorker
                w = SSHMetricsWorker(
                    host=host["host"], port=host.get("port", 22),
                    username=host.get("username", "root"),
                    auth_type=host.get("auth_type", "password"),
                    password=host.get("password", ""),
                    key_path=host.get("key_path", ""),
                    key_passphrase=host.get("key_passphrase", ""),
                    interval=999,  # 单次采集
                )
                r = []
                w.metrics_ready.connect(lambda info: r.append(info))
                w.sample.connect(lambda info: r.append(info))
                w.start()
                w.wait(30)
                w.stop()
                if r:
                    info = r[-1]
                    if info.get("ok"):
                        cpu = info.get("cpu_percent", -1)
                        mem = info.get("mem_percent", -1)
                        return ("ok", f"CPU={cpu}%, 内存={mem}%")
                    return ("warn", f"采集失败: {info.get('error', '')[:100]}")
                return ("fail", "无数据")
            elif task.action_type == "webhook":
                params = task.action_params
                url = params.get("url", "").strip()
                if not url:
                    return ("fail", "URL 为空")
                import urllib.request
                req = urllib.request.Request(
                    url, method=params.get("method", "GET"),
                    headers={"User-Agent": "AiinLink-Scheduler/1.0"},
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return ("ok", f"HTTP {resp.status}")
            else:
                return ("fail", f"未知任务类型: {task.action_type}")
        except Exception as e:
            return ("fail", f"异常: {e}")


# ============================================================
# 调度器（后台线程）
# ============================================================

class TaskScheduler(QThread):
    """定时任务调度器 - 每分钟检查一次"""
    task_executed = Signal(str, str, str)  # task_id, status, message

    def __init__(self, asset_widget, parent=None):
        super().__init__(parent)
        self._asset = asset_widget
        self._tasks: List[ScheduledTask] = []
        self._runs: List[dict] = []
        self._stop_flag = False
        self._running_tasks: Dict[str, float] = {}  # task_id -> last_run_minute
        self._ensure_dir()
        self._load()

    def _ensure_dir(self):
        try:
            os.makedirs(TASKS_DIR, exist_ok=True)
        except Exception:
            pass

    def _load(self):
        if os.path.exists(TASKS_FILE):
            try:
                with open(TASKS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._tasks = [ScheduledTask.from_dict(d) for d in data.get("tasks", [])]
            except Exception:
                pass
        if os.path.exists(TASK_RUNS_FILE):
            try:
                with open(TASK_RUNS_FILE, "r", encoding="utf-8") as f:
                    self._runs = json.load(f)
            except Exception:
                self._runs = []

    def _save(self):
        try:
            with open(TASKS_FILE, "w", encoding="utf-8") as f:
                json.dump({"tasks": [t.to_dict() for t in self._tasks]},
                          f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存任务失败: {e}")

    def _save_runs(self):
        try:
            self._runs = self._runs[-MAX_RUN_ENTRIES:]
            with open(TASK_RUNS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._runs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存任务运行记录失败: {e}")

    def get_tasks(self) -> List[ScheduledTask]:
        return list(self._tasks)

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        for t in self._tasks:
            if t.id == task_id:
                return t
        return None

    def add_task(self, task: ScheduledTask):
        self._tasks.append(task)
        self._save()

    def update_task(self, task: ScheduledTask):
        for i, t in enumerate(self._tasks):
            if t.id == task.id:
                self._tasks[i] = task
                self._save()
                return

    def delete_task(self, task_id: str):
        self._tasks = [t for t in self._tasks if t.id != task_id]
        self._save()

    def get_runs(self, task_id: str = "", limit: int = 200) -> List[dict]:
        out = self._runs
        if task_id:
            out = [r for r in out if r.get("task_id") == task_id]
        return out[-limit:][::-1]

    def run_now(self, task_id: str):
        """立即执行一次任务"""
        task = self.get_task(task_id)
        if not task:
            return
        threading.Thread(target=self._execute_task, args=(task,), daemon=True).start()

    def _execute_task(self, task: ScheduledTask):
        start = time.time()
        status, message = TaskExecutor.execute(task, self._asset)
        duration = time.time() - start
        # 更新任务
        task.last_run = start
        task.last_run_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start))
        task.last_status = status
        task.last_duration = duration
        task.run_count += 1
        if status == "ok":
            task.success_count += 1
        else:
            task.fail_count += 1
        self._save()
        # 记录
        run = {
            "task_id": task.id,
            "task_name": task.name,
            "ts": start,
            "ts_str": task.last_run_str,
            "status": status, "message": message,
            "duration": round(duration, 2),
        }
        self._runs.append(run)
        self._save_runs()
        self.task_executed.emit(task.id, status, message)
        # 审计
        try:
            from app.audit_log import AuditLogger
            AuditLogger.instance().log(
                "定时任务执行", target=task.name,
                result="success" if status == "ok" else "fail",
                details={"status": status, "duration": duration, "message": message[:200]},
            )
        except Exception:
            pass

    def stop(self):
        self._stop_flag = True

    def run(self):
        while not self._stop_flag:
            try:
                now = datetime.now()
                current_minute = now.replace(second=0, microsecond=0)
                for task in self._tasks:
                    if not task.enabled or not task.cron_obj:
                        continue
                    if task.cron_obj.matches(current_minute):
                        # 防止同一分钟内重复触发
                        last_min = self._running_tasks.get(task.id)
                        if last_min and last_min == current_minute.timestamp():
                            continue
                        self._running_tasks[task.id] = current_minute.timestamp()
                        threading.Thread(target=self._execute_task, args=(task,), daemon=True).start()
            except Exception as e:
                print(f"调度器异常: {e}")
            # 等待到下一分钟
            time.sleep(30)


# ============================================================
# 任务编辑对话框
# ============================================================

class TaskEditDialog(QDialog):
    """添加/编辑定时任务"""

    PRESETS = [
        ("每分钟", "* * * * *"),
        ("每 5 分钟", "*/5 * * * *"),
        ("每 15 分钟", "*/15 * * * *"),
        ("每 30 分钟", "*/30 * * * *"),
        ("每小时", "0 * * * *"),
        ("每天 0 点", "0 0 * * *"),
        ("每天 8 点", "0 8 * * *"),
        ("每天 18 点", "0 18 * * *"),
        ("每周一 9 点", "0 9 * * 1"),
        ("每月 1 日 0 点", "0 0 1 * *"),
    ]

    def __init__(self, task: Optional[ScheduledTask] = None, asset=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑定时任务" if task else "添加定时任务")
        self.setMinimumWidth(540)
        self._task = task
        self._asset = asset

        f = QFormLayout(self)

        self._name = QLineEdit()
        self._name.setPlaceholderText("如：每 5 分钟检查 Nginx")
        f.addRow("任务名称:", self._name)

        # Cron
        cron_lay = QHBoxLayout()
        self._cron = QLineEdit()
        self._cron.setPlaceholderText("* * * * *")
        self._cron.textChanged.connect(self._on_cron_changed)
        cron_lay.addWidget(self._cron, 1)
        cron_lay.addWidget(QLabel("预设:"))
        self._preset = QComboBox()
        self._preset.addItem("-- 选择预设 --")
        for desc, expr in self.PRESETS:
            self._preset.addItem(f"{desc}  ({expr})", expr)
        self._preset.currentIndexChanged.connect(self._on_preset)
        cron_lay.addWidget(self._preset)
        f.addRow("Cron 表达式:", cron_lay)

        self._cron_desc = QLabel("（5段：分 时 日 月 周，支持 * , - /）")
        self._cron_desc.setStyleSheet(f"color: {FG_TERTIARY}; font-size: 11px;")
        f.addRow("", self._cron_desc)

        # 任务类型
        self._type = QComboBox()
        self._type.addItems([
            "command (SSH 执行命令)",
            "health_check (健康检查)",
            "metrics (采集指标)",
            "webhook (HTTP 请求)",
        ])
        self._type.currentIndexChanged.connect(self._on_type_changed)
        f.addRow("任务类型:", self._type)

        # 主机选择（命令/健康检查/指标）
        self._host_combo = QComboBox()
        self._refresh_hosts()
        f.addRow("目标主机:", self._host_combo)

        # 命令
        self._command = QPlainTextEdit()
        self._command.setMaximumHeight(80)
        self._command.setPlaceholderText("如: df -h | head -n 5")
        f.addRow("命令/URL:", self._command)

        # Webhook URL
        self._url = QLineEdit()
        self._url.setPlaceholderText("https://example.com/api/health")
        f.addRow("Webhook URL:", self._url)

        self._desc = QLineEdit()
        self._desc.setPlaceholderText("可选")
        f.addRow("描述:", self._desc)

        self._enabled = QCheckBox("启用")
        self._enabled.setChecked(True)
        f.addRow("", self._enabled)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

        if task:
            self._name.setText(task.name)
            self._cron.setText(task.cron)
            atype = task.action_type
            for i in range(self._type.count()):
                if self._type.itemText(i).startswith(atype + " "):
                    self._type.setCurrentIndex(i)
                    break
            if task.action_params.get("target_host"):
                idx = self._host_combo.findData(task.action_params["target_host"])
                if idx >= 0:
                    self._host_combo.setCurrentIndex(idx)
            if atype == "command":
                self._command.setPlainText(task.action_params.get("command", ""))
            elif atype == "webhook":
                self._url.setText(task.action_params.get("url", ""))
            self._desc.setText(task.description)
            self._enabled.setChecked(task.enabled)

        self._on_type_changed()

    def _refresh_hosts(self):
        self._host_combo.clear()
        self._host_combo.addItem("默认第一台", "")
        if self._asset:
            for h in self._asset.all_hosts():
                self._host_combo.addItem(
                    f"{h.get('name','')} ({h.get('host','')})", h.get("name"))

    def _on_preset(self, idx: int):
        if idx <= 0:
            return
        expr = self._preset.itemData(idx)
        if expr:
            self._cron.setText(expr)

    def _on_cron_changed(self, text: str):
        try:
            c = CronExpression(text.strip())
            self._cron_desc.setText(f"✓ {c.human_readable()}")
            self._cron_desc.setStyleSheet(f"color: {SUCCESS}; font-size: 11px;")
        except Exception as e:
            self._cron_desc.setText(f"✗ {e}")
            self._cron_desc.setStyleSheet(f"color: {DANGER}; font-size: 11px;")

    def _on_type_changed(self):
        idx = self._type.currentIndex()
        text = self._type.currentText()
        atype = text.split(" ")[0]
        is_host_needed = atype in ("command", "health_check", "metrics")
        is_command = atype == "command"
        is_url = atype == "webhook"
        # 主机 / 命令 / URL 显隐
        self._host_combo.setVisible(is_host_needed)
        for i in range(self.layout().rowCount()):
            label_item = self.layout().itemAt(i, QFormLayout.LabelRole)
            if label_item and label_item.widget() and label_item.widget().text() == "目标主机:":
                label_item.widget().setVisible(is_host_needed)
        self._command.setVisible(is_command)
        self._url.setVisible(is_url)
        for i in range(self.layout().rowCount()):
            label_item = self.layout().itemAt(i, QFormLayout.LabelRole)
            if label_item and label_item.widget() and label_item.widget().text() == "命令/URL:":
                label_item.widget().setVisible(is_command or is_url)

    def _on_accept(self):
        if not self._name.text().strip():
            QMessageBox.warning(self, "错误", "请填写任务名称")
            return
        try:
            CronExpression(self._cron.text().strip())
        except Exception as e:
            QMessageBox.warning(self, "错误", f"Cron 表达式错误: {e}")
            return
        atype = self._type.currentText().split(" ")[0]
        if atype == "command" and not self._command.toPlainText().strip():
            QMessageBox.warning(self, "错误", "请填写命令")
            return
        if atype == "webhook" and not self._url.text().strip():
            QMessageBox.warning(self, "错误", "请填写 URL")
            return
        self.accept()

    def get_task(self) -> ScheduledTask:
        atype = self._type.currentText().split(" ")[0]
        params = {}
        if atype in ("command", "health_check", "metrics"):
            params["target_host"] = self._host_combo.currentData() or ""
        if atype == "command":
            params["command"] = self._command.toPlainText().strip()
            params["timeout"] = 30
        elif atype == "webhook":
            params["url"] = self._url.text().strip()
            params["method"] = "GET"
        if self._task:
            self._task.name = self._name.text().strip()
            self._task.cron = self._cron.text().strip()
            self._task.action_type = atype
            self._task.action_params = params
            self._task.description = self._desc.text().strip()
            self._task.enabled = self._enabled.isChecked()
            try:
                self._task.cron_obj = CronExpression(self._task.cron)
            except Exception:
                self._task.cron_obj = None
            return self._task
        else:
            return ScheduledTask(
                name=self._name.text().strip(),
                cron=self._cron.text().strip(),
                action_type=atype,
                action_params=params,
                enabled=self._enabled.isChecked(),
                description=self._desc.text().strip(),
            )


# ============================================================
# 定时任务 UI
# ============================================================

class ScheduledTasksWidget(QWidget):
    """定时任务主界面"""

    def __init__(self, asset, parent=None):
        super().__init__(parent)
        self._asset = asset
        self._scheduler = TaskScheduler(asset, parent=self)
        self._scheduler.task_executed.connect(self._on_task_executed)
        self._scheduler.start()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start(5000)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 顶部状态
        status = QHBoxLayout()
        self._status_label = QLabel("⏰ 调度器运行中")
        self._status_label.setStyleSheet(
            f"color: {SUCCESS}; padding: 8px 12px; background-color: {BG_PANEL}; "
            f"border: 1px solid {BORDER}; border-radius: {RADIUS_MD}px;")
        status.addWidget(self._status_label)
        status.addStretch()
        layout.addLayout(status)

        # Tabs
        tabs = QTabWidget()

        # Tab 1: 任务列表
        tasks_widget = QWidget()
        tl = QVBoxLayout(tasks_widget)
        tl.setContentsMargins(4, 4, 4, 4)
        bar = QHBoxLayout()
        b_add = QPushButton("+ 添加任务")
        b_add.clicked.connect(self._add_task)
        b_edit = QPushButton("编辑")
        b_edit.clicked.connect(self._edit_task)
        b_del = QPushButton("删除")
        b_del.clicked.connect(self._del_task)
        b_run = QPushButton("▶ 立即执行")
        b_run.clicked.connect(self._run_now)
        b_toggle = QPushButton("启用/禁用")
        b_toggle.clicked.connect(self._toggle_task)
        bar.addWidget(b_add)
        bar.addWidget(b_edit)
        bar.addWidget(b_del)
        bar.addWidget(b_run)
        bar.addWidget(b_toggle)
        bar.addStretch()
        tl.addLayout(bar)

        self._task_table = QTableWidget(0, 7)
        self._task_table.setHorizontalHeaderLabels(
            ["启用", "名称", "Cron", "下次执行", "类型", "上次状态", "成功/失败"])
        self._task_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._task_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._task_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._task_table.doubleClicked.connect(self._edit_task)
        tl.addWidget(self._task_table, 1)
        tabs.addTab(tasks_widget, "📋 任务列表")

        # Tab 2: 执行历史
        runs_widget = QWidget()
        rl = QVBoxLayout(runs_widget)
        rl.setContentsMargins(4, 4, 4, 4)
        rbar = QHBoxLayout()
        rbar.addWidget(QLabel("任务:"))
        self._run_filter = QComboBox()
        self._run_filter.addItem("全部")
        self._run_filter.currentTextChanged.connect(self._refresh_runs)
        rbar.addWidget(self._run_filter)
        rbar.addStretch()
        b_clear_runs = QPushButton("🗑 清空历史")
        b_clear_runs.clicked.connect(self._clear_runs)
        rbar.addWidget(b_clear_runs)
        rl.addLayout(rbar)

        self._run_table = QTableWidget(0, 5)
        self._run_table.setHorizontalHeaderLabels(
            ["时间", "任务", "状态", "耗时(秒)", "消息"])
        self._run_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self._run_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._run_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        rl.addWidget(self._run_table, 1)
        tabs.addTab(runs_widget, "🕐 执行历史")

        layout.addWidget(tabs, 1)

        self._refresh()
        self._refresh_runs()

    def _add_task(self):
        dlg = TaskEditDialog(asset=self._asset, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._scheduler.add_task(dlg.get_task())
            self._refresh()

    def _edit_task(self):
        row = self._task_table.currentRow()
        if row < 0:
            return
        task_id = self._task_table.item(row, 1).data(Qt.UserRole)
        task = self._scheduler.get_task(task_id)
        if not task:
            return
        dlg = TaskEditDialog(task=task, asset=self._asset, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._scheduler.update_task(dlg.get_task())
            self._refresh()

    def _del_task(self):
        row = self._task_table.currentRow()
        if row < 0:
            return
        task_id = self._task_table.item(row, 1).data(Qt.UserRole)
        task = self._scheduler.get_task(task_id)
        if task and QMessageBox.question(
            self, "确认", f"删除任务 [{task.name}]？"
        ) == QMessageBox.Yes:
            self._scheduler.delete_task(task_id)
            self._refresh()

    def _run_now(self):
        row = self._task_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选择任务")
            return
        task_id = self._task_table.item(row, 1).data(Qt.UserRole)
        self._scheduler.run_now(task_id)
        QMessageBox.information(self, "提示", "已触发执行，结果稍后查看历史")

    def _toggle_task(self):
        row = self._task_table.currentRow()
        if row < 0:
            return
        task_id = self._task_table.item(row, 1).data(Qt.UserRole)
        task = self._scheduler.get_task(task_id)
        if task:
            task.enabled = not task.enabled
            self._scheduler.update_task(task)
            self._refresh()

    def _on_task_executed(self, task_id: str, status: str, message: str):
        self._refresh()
        self._refresh_runs()

    def _refresh(self):
        tasks = self._scheduler.get_tasks()
        self._task_table.setRowCount(0)
        cur = self._run_filter.currentText()
        self._run_filter.blockSignals(True)
        self._run_filter.clear()
        self._run_filter.addItem("全部")
        self._run_filter.addItems([t.name for t in tasks])
        if cur in [self._run_filter.itemText(i) for i in range(self._run_filter.count())]:
            self._run_filter.setCurrentText(cur)
        self._run_filter.blockSignals(False)

        for t in tasks:
            row = self._task_table.rowCount()
            self._task_table.insertRow(row)
            en_item = QTableWidgetItem("✓" if t.enabled else "✗")
            en_item.setForeground(QColor(SUCCESS if t.enabled else FG_DISABLED))
            en_item.setTextAlignment(Qt.AlignCenter)
            self._task_table.setItem(row, 0, en_item)
            self._task_table.setItem(row, 1, QTableWidgetItem(t.name))
            self._task_table.setItem(row, 2, QTableWidgetItem(t.cron))
            self._task_table.setItem(row, 3, QTableWidgetItem(t.next_run_str()))
            self._task_table.setItem(row, 4, QTableWidgetItem(t.action_type))
            status_text = t.last_status or "未运行"
            status_item = QTableWidgetItem(status_text)
            if t.last_status == "ok":
                status_item.setForeground(QColor(SUCCESS))
            elif t.last_status in ("fail", "warn"):
                status_item.setForeground(QColor(DANGER if t.last_status == "fail" else WARN))
            self._task_table.setItem(row, 5, status_item)
            self._task_table.setItem(row, 6, QTableWidgetItem(
                f"{t.success_count} / {t.fail_count} (共 {t.run_count})"))
            self._task_table.item(row, 1).setData(Qt.UserRole, t.id)

    def _refresh_runs(self):
        task_name = self._run_filter.currentText()
        task_id = ""
        if task_name and task_name != "全部":
            t = next((t for t in self._scheduler.get_tasks() if t.name == task_name), None)
            if t:
                task_id = t.id
        runs = self._scheduler.get_runs(task_id=task_id, limit=500)
        self._run_table.setRowCount(0)
        for r in runs:
            row = self._run_table.rowCount()
            self._run_table.insertRow(row)
            self._run_table.setItem(row, 0, QTableWidgetItem(r.get("ts_str", "")))
            self._run_table.setItem(row, 1, QTableWidgetItem(r.get("task_name", "")))
            status_item = QTableWidgetItem(r.get("status", ""))
            if r.get("status") == "ok":
                status_item.setForeground(QColor(SUCCESS))
            elif r.get("status") == "fail":
                status_item.setForeground(QColor(DANGER))
            elif r.get("status") == "warn":
                status_item.setForeground(QColor(WARN))
            self._run_table.setItem(row, 2, status_item)
            self._run_table.setItem(row, 3, QTableWidgetItem(f"{r.get('duration', 0):.2f}"))
            self._run_table.setItem(row, 4, QTableWidgetItem(r.get("message", "")[:300]))

    def _clear_runs(self):
        if QMessageBox.question(self, "确认", "清空所有执行历史？") == QMessageBox.Yes:
            try:
                self._scheduler._runs = []
                self._scheduler._save_runs()
                self._refresh_runs()
            except Exception as e:
                QMessageBox.critical(self, "失败", str(e))

    def stop(self):
        self._refresh_timer.stop()
        self._scheduler.stop()
        self._scheduler.wait(2000)
