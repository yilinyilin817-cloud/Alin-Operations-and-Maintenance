"""
联网数据实时抓取与查看模块
- 连接级实时监控（基于 psutil，无需管理员权限）
- 进程流量统计
- 实时带宽曲线
- 可选原始包捕获（依赖 scapy，Windows 需要 npcap）
"""

import time
import socket
from collections import deque
from typing import List, Dict, Optional

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QLabel, QSpinBox, QLineEdit, QTableWidget,
    QTableWidgetItem, QTextEdit, QHeaderView, QGroupBox,
    QTabWidget, QAbstractItemView,
)

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


# ============================================================
# 工作线程
# ============================================================

class ConnectionMonitorWorker(QThread):
    """实时连接监控线程（基于 psutil.net_connections）"""
    connections_update = Signal(list)  # List[dict]
    error = Signal(str)

    def __init__(self, interval: float = 2.0):
        super().__init__()
        self.interval = max(0.5, interval)
        self._running = True
        self._known_keys = set()
        self._counter = 0

    def run(self):
        if not HAS_PSUTIL:
            self.error.emit("psutil 未安装，无法抓取连接")
            return

        while self._running:
            try:
                current_keys = set()
                items: List[dict] = []
                try:
                    connections = psutil.net_connections(kind="inet")
                except (psutil.AccessDenied, OSError) as e:
                    self.error.emit(f"无权限访问网络连接: {e}")
                    time.sleep(self.interval)
                    continue

                for c in connections:
                    laddr = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else ""
                    raddr = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else ""
                    proto = "TCP" if c.type == socket.SOCK_STREAM else "UDP" if c.type == socket.SOCK_DGRAM else "?"
                    if not c.status:
                        status = "LISTEN" if proto == "TCP" and not raddr else "ESTABLISHED"
                    else:
                        status = c.status
                    key = (c.pid, c.fd, laddr, raddr, status)
                    current_keys.add(key)

                    process_name = "System"
                    if c.pid:
                        try:
                            process_name = psutil.Process(c.pid).name()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            process_name = f"PID:{c.pid}"

                    items.append({
                        "id": self._counter,
                        "family": "IPv4" if c.family == socket.AF_INET else "IPv6" if c.family == socket.AF_INET6 else "?",
                        "type": proto,
                        "laddr": laddr,
                        "raddr": raddr,
                        "status": status,
                        "pid": c.pid or 0,
                        "process": process_name,
                        "timestamp": time.time(),
                        "is_new": key not in self._known_keys,
                    })
                    self._counter += 1

                # 检测关闭的连接
                closed_keys = self._known_keys - current_keys
                for key in closed_keys:
                    pid, fd, laddr, raddr, status = key
                    items.append({
                        "id": self._counter,
                        "family": "?",
                        "type": "?",
                        "laddr": laddr,
                        "raddr": raddr,
                        "status": "CLOSED",
                        "pid": pid or 0,
                        "process": "-",
                        "timestamp": time.time(),
                        "is_closed": True,
                    })
                    self._counter += 1

                self.connections_update.emit(items)
                self._known_keys = current_keys
            except Exception as e:
                self.error.emit(str(e))

            time.sleep(self.interval)

    def stop(self):
        self._running = False


class BandwidthMonitorWorker(QThread):
    """实时带宽监控线程（基于 psutil.net_io_counters）"""
    bandwidth_update = Signal(dict)  # {iface: {bytes_sent, bytes_recv, packets_sent, packets_recv}}
    summary_update = Signal(float, float)  # total_up_kbps, total_down_kbps
    error = Signal(str)

    def __init__(self, interval: float = 1.0):
        super().__init__()
        self.interval = max(0.5, interval)
        self._running = True
        self._prev: Optional[object] = None

    def run(self):
        if not HAS_PSUTIL:
            self.error.emit("psutil 未安装，无法监控带宽")
            return

        prev = psutil.net_io_counters(pernic=True)
        while self._running:
            time.sleep(self.interval)
            if not self._running:
                break
            try:
                now = psutil.net_io_counters(pernic=True)
                result = {}
                total_up = 0.0
                total_down = 0.0
                for iface, cur in now.items():
                    old = prev.get(iface)
                    if old is None:
                        d_sent = d_recv = d_psent = d_precv = 0
                    else:
                        d_sent = max(0, cur.bytes_sent - old.bytes_sent)
                        d_recv = max(0, cur.bytes_recv - old.bytes_recv)
                        d_psent = max(0, cur.packets_sent - old.packets_sent)
                        d_precv = max(0, cur.packets_recv - old.packets_recv)
                    result[iface] = {
                        "bytes_sent": cur.bytes_sent,
                        "bytes_recv": cur.bytes_recv,
                        "packets_sent": cur.packets_sent,
                        "packets_recv": cur.packets_recv,
                        "speed_up_kbps": d_sent / self.interval / 1024,
                        "speed_down_kbps": d_recv / self.interval / 1024,
                        "pps_up": d_psent / self.interval,
                        "pps_down": d_precv / self.interval,
                    }
                    total_up += result[iface]["speed_up_kbps"]
                    total_down += result[iface]["speed_down_kbps"]
                self.bandwidth_update.emit(result)
                self.summary_update.emit(total_up, total_down)
                prev = now
            except Exception as e:
                self.error.emit(str(e))

    def stop(self):
        self._running = False


# ============================================================
# 自绘组件
# ============================================================

class TrafficChartWidget(QWidget):
    """实时上行/下行流量曲线图"""

    def __init__(self, color_up: str = "#ff6b6b", color_down: str = "#4ecdc4", parent=None):
        super().__init__(parent)
        self.color_up = color_up
        self.color_down = color_down
        self._upload_data = deque(maxlen=60)
        self._download_data = deque(maxlen=60)
        self._max_value = 1024.0  # KB/s
        self.setMinimumHeight(160)

    def add_point(self, upload_kbps: float, download_kbps: float):
        self._upload_data.append(upload_kbps)
        self._download_data.append(download_kbps)
        peak = max(
            max(self._upload_data, default=0),
            max(self._download_data, default=0),
            100,
        )
        if peak > self._max_value * 0.8:
            self._max_value = peak * 1.2
        self.update()

    def reset_max(self):
        self._max_value = 1024.0

    def _format_value(self, v: float) -> str:
        if v >= 1024 * 1024:
            return f"{v / 1024 / 1024:.1f}GB/s"
        if v >= 1024:
            return f"{v / 1024:.1f}MB/s"
        return f"{v:.0f}KB/s"

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        ml, mr, mt, mb = 60, 12, 12, 28
        cw = max(1, w - ml - mr)
        ch = max(1, h - mt - mb)

        painter.fillRect(0, 0, w, h, QColor("#1e1e1e"))

        # 网格 + Y 轴
        painter.setPen(QPen(QColor("#2d2d2d"), 1))
        painter.setPen(QColor("#666"))
        for i in range(5):
            y = mt + ch * i / 4
            painter.drawLine(ml, int(y), w - mr, int(y))
            v = self._max_value * (4 - i) / 4
            painter.drawText(4, int(y + 4), self._format_value(v))

        # X 轴
        painter.setPen(QColor("#666"))
        painter.drawText(ml, h - 8, "-60s")
        painter.drawText(w - mr - 30, h - 8, "现在")

        def draw_line(data, color):
            if len(data) < 2:
                return
            path = QPainterPath()
            step_x = cw / (self._upload_data.maxlen - 1)
            offset = self._upload_data.maxlen - len(data)
            for i, v in enumerate(data):
                x = ml + (i + offset) * step_x
                y = mt + ch - min(1.0, v / self._max_value) * ch
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            painter.setPen(QPen(QColor(color), 1.6))
            painter.drawPath(path)

        draw_line(self._upload_data, self.color_up)
        draw_line(self._download_data, self.color_down)

        # 图例
        painter.setPen(QColor(self.color_up))
        painter.drawText(ml, mt - 2, "↑ 上行")
        painter.setPen(QColor(self.color_down))
        painter.drawText(ml + 50, mt - 2, "↓ 下行")


# ============================================================
# 主标签页
# ============================================================

class NetworkCaptureTab(QWidget):
    """联网数据实时抓取与查看标签页"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._conn_worker: Optional[ConnectionMonitorWorker] = None
        self._bw_worker: Optional[BandwidthMonitorWorker] = None
        self._all_connections: List[dict] = []
        self._iface_stats: Dict[str, dict] = {}

        self._setup_ui()
        if not HAS_PSUTIL:
            self._set_status("error", "psutil 未安装，无法启动抓取")
            self._start_btn.setEnabled(False)

    def _set_status(self, kind: str, text: str):
        """根据 kind 切换状态标签样式：idle/ok/warn/error"""
        mapping = {
            "idle": "statusIdle",
            "ok": "statusOk",
            "warn": "statusWarn",
            "error": "statusError",
        }
        self._status_label.setObjectName(mapping.get(kind, "statusIdle"))
        # 刷新样式表让 objectName 生效
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)
        self._status_label.setText(text)

    # ---- UI 构造 ----

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        layout.addLayout(self._build_control_bar())

        # 流量曲线 + 摘要
        chart_group = QGroupBox("实时流量曲线（KB/s）")
        chart_layout = QVBoxLayout(chart_group)
        self._summary_label = QLabel("总上行: 0 KB/s   |   总下行: 0 KB/s   |   活跃连接: 0")
        self._summary_label.setObjectName("summaryLabel")
        chart_layout.addWidget(self._summary_label)
        self._traffic_chart = TrafficChartWidget()
        chart_layout.addWidget(self._traffic_chart)
        layout.addWidget(chart_group)

        # 主分割：连接表 / 详情
        splitter = QSplitter(Qt.Horizontal)

        # 连接表
        conn_group = QGroupBox("实时连接列表")
        conn_layout = QVBoxLayout(conn_group)
        self._conn_table = QTableWidget()
        self._conn_table.setColumnCount(8)
        self._conn_table.setHorizontalHeaderLabels(
            ["协议", "本地地址", "远程地址", "状态", "PID", "进程", "新建", "时间"]
        )
        self._conn_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._conn_table.horizontalHeader().setStretchLastSection(True)
        self._conn_table.verticalHeader().setVisible(False)
        self._conn_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._conn_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._conn_table.setAlternatingRowColors(True)
        self._conn_table.setShowGrid(False)
        self._conn_table.itemSelectionChanged.connect(self._on_connection_selected)
        conn_layout.addWidget(self._conn_table)
        splitter.addWidget(conn_group)

        # 右侧 tab：详情 / 网卡
        right_tabs = QTabWidget()

        self._detail_view = QTextEdit()
        self._detail_view.setReadOnly(True)
        self._detail_view.setObjectName("detailView")
        self._detail_view.setPlaceholderText("选中一条连接查看详细信息...")
        right_tabs.addTab(self._detail_view, "详情")

        iface_group = QGroupBox("网卡接口流量")
        iface_layout = QVBoxLayout(iface_group)
        self._iface_table = QTableWidget()
        self._iface_table.setColumnCount(6)
        self._iface_table.setHorizontalHeaderLabels(
            ["接口", "总发送", "总接收", "发包", "收包", "实时速率"]
        )
        self._iface_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._iface_table.horizontalHeader().setStretchLastSection(True)
        self._iface_table.verticalHeader().setVisible(False)
        self._iface_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._iface_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._iface_table.setAlternatingRowColors(True)
        iface_layout.addWidget(self._iface_table)
        right_tabs.addTab(iface_group, "网卡")

        splitter.addWidget(right_tabs)
        splitter.setSizes([620, 380])
        layout.addWidget(splitter, 1)

    def _build_control_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.addWidget(QLabel("连接采样间隔(秒):"))
        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(1, 10)
        self._interval_spin.setValue(2)
        bar.addWidget(self._interval_spin)

        self._start_btn = QPushButton("▶ 开始抓取")
        self._start_btn.setObjectName("primaryButton")
        self._start_btn.clicked.connect(self._on_start)
        bar.addWidget(self._start_btn)

        self._stop_btn = QPushButton("■ 停止")
        self._stop_btn.setObjectName("dangerButton")
        self._stop_btn.clicked.connect(self._on_stop)
        self._stop_btn.setEnabled(False)
        bar.addWidget(self._stop_btn)

        bar.addWidget(QLabel("过滤:"))
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("按进程/IP/端口/状态过滤...")
        self._filter_edit.setClearButtonEnabled(True)
        self._filter_edit.textChanged.connect(self._apply_filter)
        bar.addWidget(self._filter_edit, 1)

        self._status_label = QLabel("就绪")
        self._status_label.setObjectName("statusIdle")
        bar.addWidget(self._status_label)
        return bar

    # ---- 抓取控制 ----

    def _on_start(self):
        if self._conn_worker is not None and self._conn_worker.isRunning():
            return

        interval = float(self._interval_spin.value())

        self._conn_worker = ConnectionMonitorWorker(interval=interval)
        self._conn_worker.connections_update.connect(self._on_connections_update)
        self._conn_worker.error.connect(self._on_worker_error)
        self._conn_worker.start()

        self._bw_worker = BandwidthMonitorWorker(interval=1.0)
        self._bw_worker.bandwidth_update.connect(self._on_bandwidth_update)
        self._bw_worker.summary_update.connect(self._on_summary_update)
        self._bw_worker.error.connect(self._on_worker_error)
        self._bw_worker.start()

        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._interval_spin.setEnabled(False)
        self._set_status("ok", "正在抓取...")

    def _on_stop(self):
        for w in (self._conn_worker, self._bw_worker):
            if w is not None:
                w.stop()
                if w.isRunning():
                    w.wait(2000)
        self._conn_worker = None
        self._bw_worker = None
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._interval_spin.setEnabled(True)
        self._set_status("idle", "已停止")

    # ---- 数据回调 ----

    def _on_worker_error(self, msg: str):
        self._set_status("error", f"错误: {msg}")

    def _on_connections_update(self, conns: List[dict]):
        self._all_connections = conns
        self._apply_filter()

        active = sum(1 for c in conns if not c.get("is_closed"))
        new_count = sum(1 for c in conns if c.get("is_new"))
        closed_count = sum(1 for c in conns if c.get("is_closed"))
        if new_count or closed_count:
            self._set_status(
                "ok",
                f"抓取中... 新建:{new_count} 关闭:{closed_count} 活跃:{active}"
            )
        else:
            self._set_status("ok", f"抓取中... 活跃连接: {active}")

    def _apply_filter(self):
        keyword = self._filter_edit.text().strip().lower()
        if keyword:
            conns = [
                c for c in self._all_connections
                if not c.get("is_closed")
                and (
                    keyword in (c.get("process", "") or "").lower()
                    or keyword in (c.get("laddr", "") or "").lower()
                    or keyword in (c.get("raddr", "") or "").lower()
                    or keyword in (c.get("status", "") or "").lower()
                    or keyword in (c.get("type", "") or "").lower()
                )
            ]
        else:
            conns = [c for c in self._all_connections if not c.get("is_closed")]

        self._conn_table.setRowCount(len(conns))
        for row, c in enumerate(conns):
            proto = c.get("type", "")
            status = c.get("status", "")
            if proto == "TCP" and not c.get("raddr"):
                proto_color = QColor("#ffaa00")
            elif status == "ESTABLISHED":
                proto_color = QColor("#4ecdc4")
            elif status in ("TIME_WAIT", "CLOSE_WAIT", "FIN_WAIT"):
                proto_color = QColor("#888")
            elif status == "LISTEN":
                proto_color = QColor("#ffaa00")
            else:
                proto_color = QColor("#ccc")

            items = [
                QTableWidgetItem(proto),
                QTableWidgetItem(c.get("laddr", "")),
                QTableWidgetItem(c.get("raddr", "") or "-"),
                QTableWidgetItem(status),
                QTableWidgetItem(str(c.get("pid", 0))),
                QTableWidgetItem(c.get("process", "")),
                QTableWidgetItem("●" if c.get("is_new") else ""),
            ]
            items[0].setForeground(proto_color)
            if status in ("ESTABLISHED",):
                items[3].setForeground(QColor("#4ecdc4"))
            elif status in ("LISTEN",):
                items[3].setForeground(QColor("#ffaa00"))
            elif status in ("TIME_WAIT", "CLOSE_WAIT", "FIN_WAIT"):
                items[3].setForeground(QColor("#888"))
            if c.get("is_new"):
                items[6].setForeground(QColor("#4ecdc4"))
            ts = time.strftime("%H:%M:%S", time.localtime(c.get("timestamp", time.time())))
            items.append(QTableWidgetItem(ts))
            for col, it in enumerate(items):
                self._conn_table.setItem(row, col, it)

    def _on_connection_selected(self):
        items = self._conn_table.selectedItems()
        if not items:
            return
        row = items[0].row()

        def cell(col):
            it = self._conn_table.item(row, col)
            return it.text() if it else ""

        proto = cell(0)
        laddr = cell(1)
        raddr = cell(2)
        status = cell(3)
        pid_str = cell(4)
        process = cell(5)

        details = (
            "=== 连接详情 ===\n\n"
            f"协议:   {proto}\n"
            f"本地:   {laddr}\n"
            f"远端:   {raddr}\n"
            f"状态:   {status}\n"
            f"PID:    {pid_str}\n"
            f"进程:   {process}\n"
        )

        try:
            pid_int = int(pid_str)
            if pid_int > 0 and HAS_PSUTIL:
                p = psutil.Process(pid_int)
                with p.oneshot():
                    details += "\n=== 进程信息 ===\n"
                    details += f"命令行:    {' '.join(p.cmdline()) if p.cmdline() else '-'}\n"
                    try:
                        details += f"可执行文件: {p.exe()}\n"
                    except (psutil.AccessDenied, OSError):
                        details += "可执行文件: (无权限)\n"
                    try:
                        details += f"工作目录:  {p.cwd()}\n"
                    except (psutil.AccessDenied, OSError):
                        details += "工作目录:  (无权限)\n"
                    details += f"用户名:    {p.username()}\n"
                    details += (
                        f"创建时间:  {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(p.create_time()))}\n"
                    )
                    try:
                        details += f"内存:      {p.memory_info().rss / 1024 / 1024:.1f} MB\n"
                    except Exception:
                        pass
                    try:
                        # 该进程相关的所有连接
                        child_conns = p.net_connections(kind="inet")
                        details += f"\n该进程所有连接: {len(child_conns)} 条\n"
                        for cc in child_conns[:10]:
                            la = f"{cc.laddr.ip}:{cc.laddr.port}" if cc.laddr else "-"
                            ra = f"{cc.raddr.ip}:{cc.raddr.port}" if cc.raddr else "-"
                            details += f"  [{cc.type == socket.SOCK_STREAM and 'TCP' or 'UDP'}] {la} -> {ra}  {cc.status}\n"
                    except (psutil.AccessDenied, OSError):
                        details += "\n(无权限枚举该进程的所有连接)"
        except Exception as e:
            details += f"\n(获取进程详情失败: {e})"

        self._detail_view.setPlainText(details)

    def _on_bandwidth_update(self, iface_data: Dict[str, dict]):
        self._iface_stats = iface_data
        # 网卡表
        self._iface_table.setRowCount(len(iface_data))
        for row, (iface, stats) in enumerate(iface_data.items()):
            rate = (
                f"↑{stats['speed_up_kbps']:.1f}  ↓{stats['speed_down_kbps']:.1f} KB/s"
            )
            cells = [
                QTableWidgetItem(iface),
                QTableWidgetItem(self._format_bytes(stats["bytes_sent"])),
                QTableWidgetItem(self._format_bytes(stats["bytes_recv"])),
                QTableWidgetItem(str(stats["packets_sent"])),
                QTableWidgetItem(str(stats["packets_recv"])),
                QTableWidgetItem(rate),
            ]
            cells[0].setForeground(QColor("#4ecdc4"))
            cells[5].setForeground(QColor("#ffaa00"))
            for col, it in enumerate(cells):
                self._iface_table.setItem(row, col, it)
        self._iface_table.resizeColumnsToContents()
        self._iface_table.horizontalHeader().setStretchLastSection(True)

    def _on_summary_update(self, up_kbps: float, down_kbps: float):
        self._traffic_chart.add_point(up_kbps, down_kbps)
        active = sum(1 for c in self._all_connections if not c.get("is_closed"))
        self._summary_label.setText(
            f'↑ 上行 <b>{self._format_rate(up_kbps)}</b>    '
            f'↓ 下行 <b>{self._format_rate(down_kbps)}</b>    '
            f'● 活跃连接 <b>{active}</b>'
        )

    # ---- 辅助 ----

    @staticmethod
    def _format_bytes(n: int) -> str:
        units = ["B", "KB", "MB", "GB", "TB"]
        v = float(n)
        for u in units:
            if v < 1024:
                return f"{v:.1f} {u}"
            v /= 1024
        return f"{v:.1f} PB"

    @staticmethod
    def _format_rate(kbps: float) -> str:
        if kbps >= 1024 * 1024:
            return f"{kbps / 1024 / 1024:.2f} GB/s"
        if kbps >= 1024:
            return f"{kbps / 1024:.2f} MB/s"
        return f"{kbps:.1f} KB/s"

    # ---- 资源清理 ----

    def cleanup(self):
        self._on_stop()


def open_capture_tab(main_window) -> None:
    """
    工具栏"工具→实时抓取"入口
    打开一个新的独立抓取标签页（多次点击会创建多个实例）
    """
    tab = NetworkCaptureTab(main_window)
    idx = main_window._main_tabs.addTab(tab, "📡 实时抓取")
    main_window._main_tabs.setCurrentIndex(idx)
    main_window._status_label.setText("已打开实时抓取标签页")
    # 关闭时自动清理
    try:
        tab.destroyed.connect(lambda: tab.cleanup())
    except Exception:
        pass
