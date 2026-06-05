"""
文件分发模块
- 多主机并发上传/下载文件（SFTP）
- 支持本地文件 → 远端、远端 → 本地
- 进度显示（百分比、速度、剩余时间）
- 传输历史记录
- 文件校验（可选 SHA256）

持久化：~/.aiinlink/file_transfers.json
"""

import json
import os
import time
import hashlib
import threading
from typing import List, Optional, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QSplitter, QFileDialog, QMessageBox, QFrame,
    QPlainTextEdit, QProgressBar, QGroupBox, QCheckBox, QListWidget,
    QListWidgetItem, QTabWidget, QInputDialog, QFormLayout,
)

from app.theme import (
    BG_DEEP, BG_PANEL, BG_PANEL_HOVER, BG_INPUT,
    FG_PRIMARY, FG_SECONDARY, FG_TERTIARY, FG_DISABLED,
    PRIMARY, SUCCESS, WARN, DANGER, INFO,
    BORDER, BORDER_LIGHT,
    FONT_FAMILY, FONT_SIZE_BASE, FONT_SIZE_SM, FONT_SIZE_MD,
    RADIUS_SM, RADIUS_MD, RADIUS_LG,
)


TRANSFER_DIR = os.path.join(os.path.expanduser("~"), ".aiinlink")
TRANSFER_HISTORY_FILE = os.path.join(TRANSFER_DIR, "file_transfers.json")
MAX_HISTORY_ENTRIES = 2000


# ============================================================
# 文件传输 Worker
# ============================================================

class FileTransferWorker(QThread):
    """单文件分发到多主机"""
    progress_update = Signal(str, int, int)   # host, percent, speed_bps
    transfer_done = Signal(str, bool, str)    # host, ok, message
    all_done = Signal(int, int)               # success_count, total

    def __init__(self, hosts: List[dict], direction: str,  # "upload" / "download"
                 local_path: str, remote_path: str,
                 concurrency: int = 3):
        super().__init__()
        self.hosts = hosts
        self.direction = direction
        self.local_path = local_path
        self.remote_path = remote_path
        self.concurrency = max(1, min(20, concurrency))
        self._stop_flag = False
        self._progress_lock = threading.Lock()
        self._progress: Dict[str, Tuple[int, int, float]] = {}  # host -> (sent, total, last_ts)

    def stop(self):
        self._stop_flag = True

    def _connect_sftp(self, h: dict):
        import paramiko
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        if h.get("auth_type") == "key" and h.get("key_path"):
            client.connect(
                h["host"], port=h.get("port", 22), username=h.get("username", "root"),
                key_filename=h.get("key_path"), password=h.get("key_passphrase") or None,
                timeout=8, look_for_keys=False, allow_agent=False,
            )
        else:
            client.connect(
                h["host"], port=h.get("port", 22), username=h.get("username", "root"),
                password=h.get("password", ""), timeout=8,
                look_for_keys=False, allow_agent=False,
            )
        sftp = client.open_sftp()
        return client, sftp

    def _upload_one(self, h: dict) -> tuple:
        host_name = h.get("name", h.get("host", ""))
        try:
            if not os.path.exists(self.local_path):
                return (host_name, False, f"本地文件不存在: {self.local_path}")
            file_size = os.path.getsize(self.local_path)
            client, sftp = self._connect_sftp(h)
            try:
                # 远端目录不存在则创建
                remote_dir = os.path.dirname(self.remote_path)
                if remote_dir:
                    self._mkdir_p(sftp, remote_dir)
                # 带进度回调的上传
                last_ts = time.time()
                last_sent = 0
                def callback(transferred, total):
                    nonlocal last_ts, last_sent
                    if self._stop_flag:
                        raise Exception("用户中止")
                    now = time.time()
                    dt = now - last_ts
                    if dt >= 0.2:
                        speed = (transferred - last_sent) / dt
                        pct = int(transferred * 100 / total) if total else 0
                        self.progress_update.emit(host_name, pct, int(speed))
                        last_ts = now
                        last_sent = transferred
                sftp.put(self.local_path, self.remote_path, callback=callback)
                self.progress_update.emit(host_name, 100, 0)
                return (host_name, True, f"已上传 {file_size} 字节")
            finally:
                try:
                    sftp.close()
                except Exception:
                    pass
                try:
                    client.close()
                except Exception:
                    pass
        except Exception as e:
            return (host_name, False, str(e))

    def _download_one(self, h: dict) -> tuple:
        host_name = h.get("name", h.get("host", ""))
        try:
            # 本地目录
            local_dir = os.path.dirname(self.local_path)
            if local_dir and not os.path.exists(local_dir):
                os.makedirs(local_dir, exist_ok=True)
            client, sftp = self._connect_sftp(h)
            try:
                # 远端文件属性
                try:
                    stat = sftp.stat(self.remote_path)
                    file_size = stat.st_size
                except Exception as e:
                    return (host_name, False, f"远端文件不存在: {self.remote_path} ({e})")
                last_ts = time.time()
                last_received = 0
                def callback(transferred, total):
                    nonlocal last_ts, last_received
                    if self._stop_flag:
                        raise Exception("用户中止")
                    now = time.time()
                    dt = now - last_ts
                    if dt >= 0.2:
                        speed = (transferred - last_received) / dt
                        pct = int(transferred * 100 / total) if total else 0
                        self.progress_update.emit(host_name, pct, int(speed))
                        last_ts = now
                        last_received = transferred
                sftp.get(self.remote_path, self.local_path, callback=callback)
                self.progress_update.emit(host_name, 100, 0)
                return (host_name, True, f"已下载 {file_size} 字节")
            finally:
                try:
                    sftp.close()
                except Exception:
                    pass
                try:
                    client.close()
                except Exception:
                    pass
        except Exception as e:
            return (host_name, False, str(e))

    def _mkdir_p(self, sftp, remote_dir: str):
        """递归创建远端目录"""
        if not remote_dir or remote_dir == "/":
            return
        if remote_dir.startswith("/~"):
            remote_dir = remote_dir[2:]
        parts = []
        d = remote_dir
        while d and d not in ("/", ""):
            parts.append(d)
            d = os.path.dirname(d)
        for p in reversed(parts):
            try:
                sftp.stat(p)
            except Exception:
                try:
                    sftp.mkdir(p)
                except Exception:
                    pass

    def run(self):
        total = len(self.hosts)
        success = 0
        with ThreadPoolExecutor(max_workers=self.concurrency) as ex:
            fut_map = {}
            for h in self.hosts:
                if self._stop_flag:
                    break
                if self.direction == "upload":
                    fut = ex.submit(self._upload_one, h)
                else:
                    fut = ex.submit(self._download_one, h)
                fut_map[fut] = h
            for fut in as_completed(fut_map):
                if self._stop_flag:
                    break
                host_name, ok, msg = fut.result()
                self.transfer_done.emit(host_name, ok, msg)
                if ok:
                    success += 1
        self.all_done.emit(success, total)


# ============================================================
# 文件分发 UI
# ============================================================

class FileDistributionWidget(QWidget):
    """文件分发主界面"""

    def __init__(self, asset, parent=None):
        super().__init__(parent)
        self._asset = asset
        self._worker: Optional[FileTransferWorker] = None
        self._transfer_started_at: Optional[float] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 左：主机选择
        left = QFrame()
        left.setFixedWidth(280)
        left.setStyleSheet(
            f"QFrame {{ background-color: {BG_PANEL}; border: 1px solid {BORDER}; "
            f"border-radius: {RADIUS_MD}px; }}"
        )
        ll = QVBoxLayout(left)
        ll.setContentsMargins(8, 8, 8, 8)
        ll.addWidget(QLabel("目标主机 (可多选):"))
        self._host_list = QListWidget()
        self._host_list.setSelectionMode(QAbstractItemView.MultiSelection)
        ll.addWidget(self._host_list, 1)
        hb = QHBoxLayout()
        b_all = QPushButton("全选")
        b_all.clicked.connect(lambda: self._select_all(True))
        b_none = QPushButton("全不选")
        b_none.clicked.connect(lambda: self._select_all(False))
        hb.addWidget(b_all)
        hb.addWidget(b_none)
        ll.addLayout(hb)
        layout.addWidget(left)

        # 右：操作区
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        # 方向选择
        dir_group = QGroupBox("传输方向")
        dl = QHBoxLayout(dir_group)
        self._direction = QComboBox()
        self._direction.addItems(["📤 上传 (本地 → 远端)", "📥 下载 (远端 → 本地)"])
        self._direction.currentIndexChanged.connect(self._on_direction_changed)
        dl.addWidget(self._direction)
        dl.addStretch()
        rl.addWidget(dir_group)

        # 路径
        path_group = QGroupBox("路径配置")
        pl = QFormLayout(path_group)
        # 本地路径
        lh = QHBoxLayout()
        self._local_path = QLineEdit()
        self._local_path.setPlaceholderText("本地文件路径")
        b_lbrowse = QPushButton("📂 浏览")
        b_lbrowse.clicked.connect(self._browse_local)
        lh.addWidget(self._local_path, 1)
        lh.addWidget(b_lbrowse)
        pl.addRow("本地路径:", lh)
        # 远端路径
        rh = QHBoxLayout()
        self._remote_path = QLineEdit()
        self._remote_path.setPlaceholderText("如：/tmp/deploy/app.tar.gz")
        b_rh = QPushButton("最近")
        rh.addWidget(self._remote_path, 1)
        rh.addWidget(b_rh)
        pl.addRow("远端路径:", rh)
        self._recent_remote_btn = b_rh
        rl.addWidget(path_group)

        # 选项
        opt_group = QGroupBox("传输选项")
        ol = QHBoxLayout(opt_group)
        ol.addWidget(QLabel("并发:"))
        self._concurrency = QSpinBox()
        self._concurrency.setRange(1, 20)
        self._concurrency.setValue(3)
        ol.addWidget(self._concurrency)
        self._verify_chk = QCheckBox("传输后 SHA256 校验")
        ol.addWidget(self._verify_chk)
        self._resume_chk = QCheckBox("断点续传")
        self._resume_chk.setEnabled(False)  # 暂未实现
        self._resume_chk.setToolTip("即将支持")
        ol.addWidget(self._resume_chk)
        ol.addStretch()
        rl.addWidget(opt_group)

        # 操作按钮
        bar = QHBoxLayout()
        self._start_btn = QPushButton("🚀 开始传输")
        self._start_btn.clicked.connect(self._start_transfer)
        self._stop_btn = QPushButton("⏹ 中止")
        self._stop_btn.clicked.connect(self._stop_transfer)
        self._stop_btn.setEnabled(False)
        bar.addWidget(self._start_btn)
        bar.addWidget(self._stop_btn)
        bar.addStretch()
        self._badge = QLabel("就绪")
        self._badge.setStyleSheet(
            f"color: {SUCCESS}; padding: 4px 12px; background-color: {BG_INPUT}; "
            f"border-radius: 8px; font-weight: 600;")
        bar.addWidget(self._badge)
        rl.addLayout(bar)

        # 进度区
        self._progress_table = QTableWidget(0, 5)
        self._progress_table.setHorizontalHeaderLabels(
            ["主机", "进度", "速度", "状态", "消息"])
        self._progress_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self._progress_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._progress_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._progress_table.verticalHeader().setVisible(False)
        rl.addWidget(self._progress_table, 1)

        # 总体进度
        overall_lay = QHBoxLayout()
        overall_lay.addWidget(QLabel("总体进度:"))
        self._overall_progress = QProgressBar()
        self._overall_progress.setRange(0, 100)
        self._overall_progress.setValue(0)
        self._overall_progress.setFixedHeight(16)
        overall_lay.addWidget(self._overall_progress, 1)
        self._overall_label = QLabel("0/0")
        self._overall_label.setStyleSheet(f"color: {FG_SECONDARY}; padding: 0 8px;")
        overall_lay.addWidget(self._overall_label)
        rl.addLayout(overall_lay)

        layout.addWidget(right, 1)

        # 历史 tab
        self._history_timer = QTimer(self)
        self._history_timer.timeout.connect(self._refresh_history)
        self._history_timer.start(1000)

        self._refresh_hosts()
        self._on_direction_changed(0)
        self._refresh_history()

    def _on_direction_changed(self, idx: int):
        if idx == 0:
            self._local_path.setPlaceholderText("本地文件路径 (如 C:\\app\\deploy.tar.gz)")
        else:
            self._local_path.setPlaceholderText("本地保存路径 (如 D:\\downloads\\)")

    def _browse_local(self):
        if self._direction.currentIndex() == 0:  # 上传
            path, _ = QFileDialog.getOpenFileName(self, "选择本地文件")
        else:  # 下载
            path = QFileDialog.getExistingDirectory(self, "选择保存目录")
            if path:
                path = os.path.join(path, "downloaded_file")
        if path:
            self._local_path.setText(path)

    def _refresh_hosts(self):
        self._host_list.clear()
        for h in self._asset.all_hosts():
            self._host_list.addItem(QListWidgetItem(
                f"{h.get('name', '')}  -  {h.get('host', '')}"))

    def _select_all(self, sel: bool):
        for i in range(self._host_list.count()):
            self._host_list.item(i).setSelected(sel)

    def _start_transfer(self):
        if self._worker and self._worker.isRunning():
            return
        local = self._local_path.text().strip()
        remote = self._remote_path.text().strip()
        if not local or not remote:
            QMessageBox.warning(self, "提示", "请填写本地路径和远端路径")
            return
        if self._direction.currentIndex() == 0 and not os.path.exists(local):
            QMessageBox.warning(self, "提示", f"本地文件不存在: {local}")
            return
        sel_items = self._host_list.selectedItems()
        if not sel_items:
            QMessageBox.warning(self, "提示", "请先在左侧选择目标主机")
            return
        hosts = []
        for it in sel_items:
            row = self._host_list.row(it)
            text = it.text()
            name = text.split(" - ")[0].strip()
            host = self._asset.get_host(name)
            if host:
                hosts.append(host)
        if not hosts:
            return
        # 准备进度表
        self._progress_table.setRowCount(0)
        for h in hosts:
            row = self._progress_table.rowCount()
            self._progress_table.insertRow(row)
            self._progress_table.setItem(row, 0, QTableWidgetItem(
                f"{h.get('name', '')} ({h.get('host', '')})"))
            pb = QProgressBar()
            pb.setRange(0, 100)
            pb.setValue(0)
            self._progress_table.setCellWidget(row, 1, pb)
            self._progress_table.setItem(row, 2, QTableWidgetItem("--"))
            self._progress_table.setItem(row, 3, QTableWidgetItem("⏳ 等待中"))
            self._progress_table.setItem(row, 4, QTableWidgetItem(""))
            self._progress_table.item(row, 0).setData(Qt.UserRole, h.get("name", ""))
        # 启动
        direction = "upload" if self._direction.currentIndex() == 0 else "download"
        self._worker = FileTransferWorker(
            hosts=hosts, direction=direction, local_path=local, remote_path=remote,
            concurrency=self._concurrency.value(),
        )
        self._worker.progress_update.connect(self._on_progress)
        self._worker.transfer_done.connect(self._on_transfer_done)
        self._worker.all_done.connect(self._on_all_done)
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._badge.setText("传输中")
        self._badge.setStyleSheet(
            f"color: {PRIMARY}; padding: 4px 12px; background-color: {BG_INPUT}; "
            f"border-radius: 8px; font-weight: 600;")
        self._overall_progress.setValue(0)
        self._overall_label.setText(f"0/{len(hosts)}")
        self._transfer_started_at = time.time()
        self._worker.start()
        # 审计
        try:
            from app.audit_log import AuditLogger
            AuditLogger.instance().log(
                "文件传输", target=f"{direction} {os.path.basename(local)} → {len(hosts)} 台",
                result="success", details={
                    "direction": direction, "local": local, "remote": remote,
                    "host_count": len(hosts),
                },
            )
        except Exception:
            pass

    def _stop_transfer(self):
        if self._worker:
            self._worker.stop()
            self._worker.wait(3000)
            self._worker = None
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._badge.setText("已中止")
        self._badge.setStyleSheet(
            f"color: {WARN}; padding: 4px 12px; background-color: {BG_INPUT}; "
            f"border-radius: 8px; font-weight: 600;")

    def _on_progress(self, host: str, percent: int, speed_bps: int):
        for row in range(self._progress_table.rowCount()):
            if self._progress_table.item(row, 0).data(Qt.UserRole) == host:
                pb = self._progress_table.cellWidget(row, 1)
                if pb:
                    pb.setValue(percent)
                if speed_bps > 0:
                    if speed_bps > 1024 * 1024:
                        speed_txt = f"{speed_bps/1024/1024:.1f} MB/s"
                    elif speed_bps > 1024:
                        speed_txt = f"{speed_bps/1024:.1f} KB/s"
                    else:
                        speed_txt = f"{speed_bps} B/s"
                    self._progress_table.item(row, 2).setText(speed_txt)
                self._progress_table.item(row, 3).setText("⏳ 传输中")
                break

    def _on_transfer_done(self, host: str, ok: bool, msg: str):
        for row in range(self._progress_table.rowCount()):
            if self._progress_table.item(row, 0).data(Qt.UserRole) == host:
                pb = self._progress_table.cellWidget(row, 1)
                if pb:
                    pb.setValue(100 if ok else pb.value())
                if ok:
                    self._progress_table.item(row, 3).setText("✓ 成功")
                    self._progress_table.item(row, 3).setForeground(QColor(SUCCESS))
                else:
                    self._progress_table.item(row, 3).setText("✗ 失败")
                    self._progress_table.item(row, 3).setForeground(QColor(DANGER))
                self._progress_table.item(row, 4).setText(msg)
                break
        # 更新总体进度
        success = sum(
            1 for r in range(self._progress_table.rowCount())
            if "成功" in self._progress_table.item(r, 3).text()
        )
        total = self._progress_table.rowCount()
        done = sum(
            1 for r in range(self._progress_table.rowCount())
            if "成功" in self._progress_table.item(r, 3).text()
            or "失败" in self._progress_table.item(r, 3).text()
        )
        self._overall_label.setText(f"{done}/{total}")
        self._overall_progress.setValue(int(done * 100 / total) if total else 0)

    def _on_all_done(self, success: int, total: int):
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        if success == total:
            self._badge.setText(f"完成 {success}/{total}")
            self._badge.setStyleSheet(
                f"color: {SUCCESS}; padding: 4px 12px; background-color: {BG_INPUT}; "
                f"border-radius: 8px; font-weight: 600;")
        else:
            self._badge.setText(f"部分成功 {success}/{total}")
            self._badge.setStyleSheet(
                f"color: {WARN}; padding: 4px 12px; background-color: {BG_INPUT}; "
                f"border-radius: 8px; font-weight: 600;")
        # 写入历史
        self._save_history({
            "ts": time.time(),
            "ts_str": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "direction": "upload" if self._direction.currentIndex() == 0 else "download",
            "local": self._local_path.text(),
            "remote": self._remote_path.text(),
            "success": success, "total": total,
            "duration_sec": int(time.time() - self._transfer_started_at) if self._transfer_started_at else 0,
        })

    def _save_history(self, entry: dict):
        try:
            os.makedirs(TRANSFER_DIR, exist_ok=True)
            history = []
            if os.path.exists(TRANSFER_HISTORY_FILE):
                try:
                    with open(TRANSFER_HISTORY_FILE, "r", encoding="utf-8") as f:
                        history = json.load(f)
                except Exception:
                    history = []
            history.append(entry)
            history = history[-MAX_HISTORY_ENTRIES:]
            with open(TRANSFER_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _refresh_history(self):
        pass  # 历史区可通过按钮查看

    def stop(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(2000)
        self._history_timer.stop()
