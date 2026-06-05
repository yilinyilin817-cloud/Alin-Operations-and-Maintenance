"""
仪表盘页面
展示本地网卡状态、实时网速、一键体检
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QGroupBox, QProgressBar, QTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QFrame,
)
from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QFont, QColor, QRadialGradient

from app.network_probe import (
    NetworkInterfaceWorker, ArpScanWorker,
    PingWorker, PortScanWorker, TracerouteWorker,
    get_common_ports_description,
)
from app.workers import SpeedMonitorWorker, QuickDiagnosisWorker
from app.theme import (
    BG_DEEP, BG_PANEL, BG_PANEL_HOVER, BG_INPUT, BG_RAISED,
    FG_PRIMARY, FG_SECONDARY, FG_TERTIARY, FG_DISABLED,
    PRIMARY, PRIMARY_HOVER, PRIMARY_DARK,
    ACCENT_BLUE, ACCENT_BLUE_HOVER,
    SUCCESS, SUCCESS_BG, WARN, WARN_BG, DANGER, DANGER_BG,
    BORDER, BORDER_LIGHT, BORDER_FOCUS,
    FONT_FAMILY, FONT_SIZE_BASE, FONT_SIZE_SM,
    RADIUS_SM, RADIUS_MD, RADIUS_LG,
)


# 跟踪所有启动的 QThread，用于在应用退出时清理
import threading
_active_threads = []
_active_threads_lock = threading.Lock()


def _track_thread(thread):
    """记录需要清理的线程"""
    with _active_threads_lock:
        _active_threads.append(thread)
    # 线程结束后自动从列表移除
    if thread is not None:
        try:
            thread.finished.connect(lambda t=thread: _untrack_thread(t))
        except Exception:
            pass


def _untrack_thread(thread):
    """从活动线程列表移除"""
    with _active_threads_lock:
        try:
            if thread in _active_threads:
                _active_threads.remove(thread)
        except ValueError:
            pass


def cleanup_all_threads():
    """清理所有后台线程，在应用退出时调用"""
    with _active_threads_lock:
        threads = list(_active_threads)
    for t in threads:
        try:
            if hasattr(t, "stop"):
                t.stop()
            if t.isRunning():
                t.quit()
                t.wait(2000)
        except Exception:
            pass


class SpeedChart(QWidget):
    """实时网速图表 - 现代化渐变填充 + 平滑曲线 + 圆角面板 + 内阴影暗角"""

    def __init__(self, title: str, color: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.color = QColor(color)
        self._data = []
        self._max_points = 60
        self._max_value = 100.0
        self.setMinimumHeight(160)
        self.setMinimumWidth(220)
        # 卡片式背景
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {BG_PANEL};
                border: 1px solid {BORDER_LIGHT};
                border-radius: {RADIUS_LG}px;
            }}
        """)

    def add_point(self, value: float):
        self._data.append(value)
        if len(self._data) > self._max_points:
            self._data.pop(0)
        if value > self._max_value:
            self._max_value = value * 1.2
        self.update()

    def paintEvent(self, event):
        from PySide6.QtGui import (
            QPainter, QPen, QBrush, QPainterPath,
            QLinearGradient, QRadialGradient,
        )

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        margin_l = 30
        margin_r = 14
        margin_t = 38
        margin_b = 14

        # ── 标题：彩色圆点 + 更大更粗文字 ──
        dot_r = 4
        dot_x = 14
        dot_y = 14
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self.color))
        painter.drawEllipse(QPointF(dot_x + dot_r, dot_y), dot_r, dot_r)

        painter.setPen(QColor(FG_PRIMARY))
        painter.setFont(QFont(FONT_FAMILY, 11, QFont.Bold))
        painter.drawText(14 + dot_r * 2 + 6, 19, self.title)

        # ── 当前值 + 单位（更大字体，单位紧跟） ──
        if self._data:
            current = self._data[-1]
            value_font = QFont("Cascadia Code, Consolas", 18, QFont.Bold)
            painter.setFont(value_font)
            painter.setPen(QColor(self.color))
            value_text = f"{current:.1f}"
            fm = painter.fontMetrics()
            value_w = fm.horizontalAdvance(value_text)
            painter.drawText(14, 38, value_text)

            # 单位紧跟在数值后面
            painter.setFont(QFont(FONT_FAMILY, 10))
            painter.setPen(QColor(FG_TERTIARY))
            painter.drawText(14 + value_w + 4, 38, "KB/s")

        # 数据点不够时不画曲线
        if len(self._data) < 2:
            painter.end()
            return

        chart_x = margin_l
        chart_y = margin_t
        chart_w = w - margin_l - margin_r
        chart_h = h - margin_t - margin_b

        # ── 水平网格线（更低透明度） ──
        grid_color = QColor(FG_TERTIARY)
        grid_color.setAlpha(25)
        painter.setPen(QPen(grid_color, 1, Qt.SolidLine))
        for i in range(1, 5):
            y = chart_y + chart_h * i / 5
            painter.drawLine(chart_x, int(y), chart_x + chart_w, int(y))

        # 计算所有点
        step = chart_w / (self._max_points - 1)
        points = []
        for i, val in enumerate(self._data):
            x = chart_x + i * step
            y = chart_y + chart_h - (val / self._max_value * chart_h) if self._max_value > 0 else chart_y + chart_h
            points.append((x, y))

        # 平滑路径（三次贝塞尔）
        path = QPainterPath()
        if points:
            path.moveTo(points[0][0], points[0][1])
            for i in range(1, len(points)):
                x_prev, y_prev = points[i - 1]
                x_cur, y_cur = points[i]
                cx1 = x_prev + (x_cur - x_prev) * 0.5
                cy1 = y_prev
                cx2 = x_prev + (x_cur - x_prev) * 0.5
                cy2 = y_cur
                path.cubicTo(cx1, cy1, cx2, cy2, x_cur, y_cur)

        # ── 渐变填充（alpha 从 110 提升到 140） ──
        fill_path = QPainterPath(path)
        last_x = points[-1][0]
        first_x = points[0][0]
        fill_path.lineTo(last_x, chart_y + chart_h)
        fill_path.lineTo(first_x, chart_y + chart_h)
        fill_path.closeSubpath()
        grad = QLinearGradient(0, chart_y, 0, chart_y + chart_h)
        top_color = QColor(self.color); top_color.setAlpha(140)
        bottom_color = QColor(self.color); bottom_color.setAlpha(8)
        grad.setColorAt(0.0, top_color)
        grad.setColorAt(1.0, bottom_color)
        painter.fillPath(fill_path, QBrush(grad))

        # 描边
        painter.setPen(QPen(QColor(self.color), 2, Qt.SolidLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        # ── 当前点：发光效果 + 实心点 ──
        lx, ly = points[-1]
        # 外层发光
        painter.setPen(Qt.NoPen)
        glow_outer = QColor(self.color); glow_outer.setAlpha(35)
        painter.setBrush(QBrush(glow_outer))
        painter.drawEllipse(QPointF(lx, ly), 10, 10)
        # 中层发光
        glow_mid = QColor(self.color); glow_mid.setAlpha(70)
        painter.setBrush(QBrush(glow_mid))
        painter.drawEllipse(QPointF(lx, ly), 6, 6)
        # 实心点
        painter.setBrush(QBrush(self.color))
        painter.drawEllipse(QPointF(lx, ly), 3, 3)

        # ── 内阴影/暗角效果 ──
        # 四边渐变暗角，营造深度感
        vignette_alpha = 60

        # 顶部暗角
        top_vig = QLinearGradient(0, chart_y, 0, chart_y + 20)
        vig_color = QColor(BG_PANEL); vig_color.setAlpha(vignette_alpha)
        top_vig.setColorAt(0.0, vig_color)
        vig_color.setAlpha(0)
        top_vig.setColorAt(1.0, vig_color)
        painter.fillRect(QRectF(chart_x, chart_y, chart_w, 20), QBrush(top_vig))

        # 底部暗角
        bot_vig = QLinearGradient(0, chart_y + chart_h - 20, 0, chart_y + chart_h)
        c0 = QColor(BG_PANEL); c0.setAlpha(0)
        vig_color = QColor(BG_PANEL); vig_color.setAlpha(vignette_alpha)
        bot_vig.setColorAt(0.0, c0)
        bot_vig.setColorAt(1.0, vig_color)
        painter.fillRect(QRectF(chart_x, chart_y + chart_h - 20, chart_w, 20), QBrush(bot_vig))

        # 左侧暗角
        left_vig = QLinearGradient(chart_x, 0, chart_x + 16, 0)
        left_vig.setColorAt(0.0, vig_color)
        left_vig.setColorAt(1.0, c0)
        painter.fillRect(QRectF(chart_x, chart_y, 16, chart_h), QBrush(left_vig))

        # 右侧暗角
        right_vig = QLinearGradient(chart_x + chart_w - 16, 0, chart_x + chart_w, 0)
        right_vig.setColorAt(0.0, c0)
        right_vig.setColorAt(1.0, vig_color)
        painter.fillRect(QRectF(chart_x + chart_w - 16, chart_y, 16, chart_h), QBrush(right_vig))

        painter.end()


# ── 次要按钮公共样式 ──
_SECONDARY_BTN_QSS = f"""
    QPushButton {{
        background-color: {BG_PANEL};
        color: {FG_PRIMARY};
        border: 1px solid {BORDER_LIGHT};
        border-radius: {RADIUS_MD}px;
        padding: 6px 16px;
        font-family: {FONT_FAMILY};
        font-size: 12px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: {BG_PANEL_HOVER};
        border-color: {BORDER_FOCUS};
        color: {PRIMARY};
    }}
    QPushButton:pressed {{
        background-color: {BG_RAISED};
        border-color: {PRIMARY_DARK};
    }}
"""

# ── GroupBox 公共样式 ──
_GROUPBOX_QSS = f"""
    QGroupBox {{
        background-color: {BG_PANEL};
        border: 1px solid {BORDER_LIGHT};
        border-top: 2px solid {PRIMARY};
        border-radius: {RADIUS_LG}px;
        margin-top: 16px;
        padding: 18px 14px 14px 14px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 14px;
        padding: 2px 8px;
        color: {PRIMARY};
        background-color: {BG_PANEL};
        font-size: 12px;
        font-weight: 700;
    }}
"""

# ── 表格公共样式 ──
_TABLE_QSS = f"""
    QTableWidget {{
        background-color: {BG_PANEL};
        color: {FG_PRIMARY};
        border: 1px solid {BORDER_LIGHT};
        border-radius: {RADIUS_LG}px;
        gridline-color: transparent;
        font-family: {FONT_FAMILY};
        font-size: 12px;
    }}
    QTableWidget::item {{
        padding: 8px 10px;
        border-bottom: 1px solid {BORDER};
    }}
    QTableWidget::item:selected {{
        background-color: {PRIMARY_DARK};
        color: white;
    }}
    QTableWidget::item:alternate {{
        background-color: {BG_DEEP};
    }}
    QTableWidget::item:hover {{
        background-color: rgba(78, 205, 196, 25);
    }}
    QHeaderView::section {{
        background-color: {BG_DEEP};
        color: {FG_SECONDARY};
        border: none;
        border-bottom: 2px solid {PRIMARY};
        padding: 10px 12px;
        font-weight: 600;
        font-size: 11px;
        text-align: left;
    }}
"""


class DashboardWidget(QWidget):
    """仪表盘主控件"""

    request_diagnosis = Signal(str)  # 请求AI诊断

    def __init__(self, parent=None):
        super().__init__(parent)

        self._speed_monitor: SpeedMonitorWorker = None
        self._interface_worker: NetworkInterfaceWorker = None
        self._arp_worker: ArpScanWorker = None
        self._diagnosis_worker: QuickDiagnosisWorker = None
        self._threads = []  # 保存所有线程引用

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(4, 4, 4, 4)

        # ── 顶部：一键体检 ──
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        self._btn_quick_check = QPushButton("🩺  一键体检")
        self._btn_quick_check.setMinimumHeight(38)
        self._btn_quick_check.setMinimumWidth(130)
        self._btn_quick_check.setCursor(Qt.PointingHandCursor)
        self._btn_quick_check.setProperty("role", "primary")
        self._btn_quick_check.clicked.connect(self._start_quick_check)
        top_bar.addWidget(self._btn_quick_check)

        self._btn_refresh_ifaces = QPushButton("🔄  刷新网卡")
        self._btn_refresh_ifaces.setMinimumHeight(38)
        self._btn_refresh_ifaces.setMinimumWidth(110)
        self._btn_refresh_ifaces.setCursor(Qt.PointingHandCursor)
        self._btn_refresh_ifaces.setProperty("role", "secondary")
        self._btn_refresh_ifaces.clicked.connect(self._refresh_interfaces)
        top_bar.addWidget(self._btn_refresh_ifaces)

        self._btn_arp_scan = QPushButton("📡  ARP扫描")
        self._btn_arp_scan.setMinimumHeight(38)
        self._btn_arp_scan.setMinimumWidth(110)
        self._btn_arp_scan.setCursor(Qt.PointingHandCursor)
        self._btn_arp_scan.setProperty("role", "secondary")
        self._btn_arp_scan.clicked.connect(self._start_arp_scan)
        top_bar.addWidget(self._btn_arp_scan)

        top_bar.addStretch()
        layout.addLayout(top_bar)

        # ── 体检结果区 ──
        self._check_result_container = QWidget()
        check_layout = QVBoxLayout(self._check_result_container)
        check_layout.setContentsMargins(0, 0, 0, 0)
        check_layout.setSpacing(0)

        # 标题栏
        self._check_header = QLabel("📋  体检结果")
        self._check_header.setProperty("role", "sectionTitle")
        self._check_header.setStyleSheet(f"""
            QLabel {{
                background-color: {BG_DEEP};
                color: {PRIMARY};
                border: 1px solid {BORDER_LIGHT};
                border-bottom: none;
                border-top: 2px solid {PRIMARY};
                border-radius: {RADIUS_MD}px {RADIUS_MD}px 0 0;
                padding: 8px 14px;
                font-family: {FONT_FAMILY};
                font-size: 12px;
                font-weight: 700;
            }}
        """)
        check_layout.addWidget(self._check_header)

        # 结果文本
        self._check_result = QTextEdit()
        self._check_result.setReadOnly(True)
        self._check_result.setMaximumHeight(160)
        self._check_result.setProperty("role", "terminal")
        self._check_result.setStyleSheet(f"""
            QTextEdit {{
                background-color: {BG_INPUT};
                color: {FG_PRIMARY};
                border: 1px solid {BORDER_LIGHT};
                border-top: none;
                border-left: 2px solid {PRIMARY};
                border-radius: 0 0 {RADIUS_MD}px {RADIUS_MD}px;
                padding: 10px 14px;
                font-family: "Cascadia Code", Consolas, monospace;
                font-size: 12px;
                selection-background-color: {PRIMARY};
                selection-color: #0a1f1d;
            }}
        """)
        check_layout.addWidget(self._check_result)

        self._check_result_container.hide()
        layout.addWidget(self._check_result_container)

        # ── 分隔线 ──
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet(f"background-color: {BORDER}; border: none; max-height: 1px;")
        layout.addWidget(sep1)

        # ── 中间：网速图表 ──
        speed_layout = QHBoxLayout()
        speed_layout.setSpacing(12)
        self._upload_chart = SpeedChart("上行速度", DANGER)
        self._download_chart = SpeedChart("下行速度", PRIMARY)
        speed_layout.addWidget(self._upload_chart)
        speed_layout.addWidget(self._download_chart)
        layout.addLayout(speed_layout)

        # ── 分隔线 ──
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet(f"background-color: {BORDER}; border: none; max-height: 1px;")
        layout.addWidget(sep2)

        # ── 网卡信息表 ──
        iface_group = QGroupBox("🖧  网络接口")
        iface_group.setStyleSheet(_GROUPBOX_QSS)
        iface_layout = QVBoxLayout(iface_group)
        iface_layout.setContentsMargins(6, 8, 6, 6)
        self._iface_table = QTableWidget()
        self._iface_table.setColumnCount(5)
        self._iface_table.setHorizontalHeaderLabels(["接口名", "IP地址", "掩码", "状态", "速率 (Mbps)"])
        # 接口名列使用 ResizeToContents，其他列 Stretch
        self._iface_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for col in range(1, 5):
            self._iface_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Stretch)
        self._iface_table.setAlternatingRowColors(True)
        self._iface_table.setShowGrid(False)
        self._iface_table.verticalHeader().setVisible(False)
        self._iface_table.setStyleSheet(_TABLE_QSS)
        iface_layout.addWidget(self._iface_table)
        layout.addWidget(iface_group)

        # ── ARP 表 ──
        arp_group = QGroupBox("📡  ARP 缓存 / 局域网设备")
        arp_group.setStyleSheet(_GROUPBOX_QSS)
        arp_layout = QVBoxLayout(arp_group)
        arp_layout.setContentsMargins(6, 8, 6, 6)
        self._arp_table = QTableWidget()
        self._arp_table.setColumnCount(3)
        self._arp_table.setHorizontalHeaderLabels(["IP地址", "MAC地址", "接口"])
        self._arp_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._arp_table.setAlternatingRowColors(True)
        self._arp_table.setShowGrid(False)
        self._arp_table.verticalHeader().setVisible(False)
        self._arp_table.setStyleSheet(_TABLE_QSS)
        arp_layout.addWidget(self._arp_table)
        layout.addWidget(arp_group)

        # 启动网速监控
        self._start_speed_monitor()

        # 初始加载网卡信息
        self._refresh_interfaces()

    def _start_speed_monitor(self):
        self._speed_monitor = SpeedMonitorWorker(interval=1.0)
        self._speed_monitor.speed_update.connect(self._on_speed_update)
        _track_thread(self._speed_monitor)
        self._threads.append(self._speed_monitor)
        self._speed_monitor.start()

    def _on_speed_update(self, upload: float, download: float):
        self._upload_chart.add_point(upload)
        self._download_chart.add_point(download)

    def _refresh_interfaces(self):
        self._interface_worker = NetworkInterfaceWorker()
        self._interface_worker.result_ready.connect(self._on_interfaces_ready)
        _track_thread(self._interface_worker)
        self._threads.append(self._interface_worker)
        self._interface_worker.start()

    def _on_interfaces_ready(self, interfaces):
        self._iface_table.setRowCount(len(interfaces))
        for row, (name, ip, netmask, status, speed) in enumerate(interfaces):
            self._iface_table.setItem(row, 0, QTableWidgetItem(name))
            self._iface_table.setItem(row, 1, QTableWidgetItem(ip))
            self._iface_table.setItem(row, 2, QTableWidgetItem(netmask))
            # 状态徽章（药丸样式）
            status_item = QTableWidgetItem(f"  ● {status}  ")
            status_item.setTextAlignment(Qt.AlignCenter)
            if status == "UP":
                status_item.setForeground(QColor(SUCCESS))
                status_item.setBackground(QColor(SUCCESS_BG))
            else:
                status_item.setForeground(QColor(DANGER))
                status_item.setBackground(QColor(DANGER_BG))
            self._iface_table.setItem(row, 3, status_item)
            # 速率（右对齐）
            speed_item = QTableWidgetItem(f"{speed}" if speed else "—")
            speed_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._iface_table.setItem(row, 4, speed_item)

    def _start_arp_scan(self):
        self._arp_worker = ArpScanWorker()
        self._arp_worker.result_ready.connect(self._on_arp_ready)
        _track_thread(self._arp_worker)
        self._threads.append(self._arp_worker)
        self._arp_worker.start()

    def _on_arp_ready(self, entries):
        self._arp_table.setRowCount(len(entries))
        for row, (ip, mac, iface) in enumerate(entries):
            self._arp_table.setItem(row, 0, QTableWidgetItem(ip))
            self._arp_table.setItem(row, 1, QTableWidgetItem(mac))
            iface_item = QTableWidgetItem(iface)
            if "冲突" in iface:
                iface_item.setForeground(QColor("#ff0000"))
            self._arp_table.setItem(row, 2, iface_item)

    def _start_quick_check(self):
        self._check_result_container.show()
        self._check_result.setPlainText("⏳ 正在执行一键体检...\n")
        self._btn_quick_check.setEnabled(False)

        self._diagnosis_worker = QuickDiagnosisWorker()
        self._diagnosis_worker.progress.connect(self._on_check_progress)
        self._diagnosis_worker.result.connect(self._on_check_result)
        _track_thread(self._diagnosis_worker)
        self._threads.append(self._diagnosis_worker)
        self._diagnosis_worker.start()

    def _on_check_progress(self, msg: str):
        self._check_result.append(f"  ▸ {msg}")

    def _on_check_result(self, results: dict):
        self._btn_quick_check.setEnabled(True)
        self._check_result.append("\n━━━━━━━━━━━━━━━━━━━━━━━━\n")
        for key, value in results.items():
            status = ""
            if isinstance(value, str):
                if value == "正常":
                    status = "  ✅"
                elif value == "异常" or value == "超时":
                    status = "  ❌"
            self._check_result.append(f"  {key}: {value}{status}")

        # 如果有异常，请求AI诊断
        has_issue = any(v in ("异常", "超时") for v in results.values() if isinstance(v, str))
        if has_issue:
            self._check_result.append("\n⚠️  检测到异常，正在请求 AI 诊断...")
            context = "\n".join(f"{k}: {v}" for k, v in results.items())
            self.request_diagnosis.emit(context)

    def cleanup(self):
        """停止所有后台线程"""
        for t in (self._speed_monitor, self._interface_worker, self._arp_worker, self._diagnosis_worker):
            if t is None:
                continue
            try:
                if hasattr(t, "stop"):
                    t.stop()
                if t.isRunning():
                    t.quit()
                    t.wait(2000)
            except Exception:
                pass
        # 清理活动线程列表
        for t in self._threads:
            try:
                if t.isRunning():
                    t.quit()
                    t.wait(2000)
            except Exception:
                pass
        self._threads.clear()

    def closeEvent(self, event):
        """窗口关闭时清理线程"""
        self.cleanup()
        super().closeEvent(event)
