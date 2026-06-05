"""
企业级运维控制台
子模块：
  1) 资产管理      - 主机分组、增删改查、批量导入
  2) 实时监控      - CPU/内存/磁盘/网络/负载 实时折线图
  3) 日志分析      - 远端日志 tail、关键字高亮
  4) 进程管理      - top-like 进程列表
  5) 服务可用性    - HTTP/TCP 健康检查、告警
  6) 批量执行      - 多主机并发执行命令

持久化资产数据：~/.aiinlink/assets.json
"""

import csv
import json
import os
import time
from collections import deque
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal, QSize, QPoint
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QComboBox,
    QSpinBox, QFormLayout, QGroupBox, QMessageBox, QDialog, QDialogButtonBox,
    QPlainTextEdit, QListWidget, QListWidgetItem, QSplitter, QTextEdit,
    QCheckBox, QTreeWidget, QTreeWidgetItem, QAbstractItemView,
    QGridLayout, QFrame, QSizePolicy, QToolButton, QMenu, QInputDialog,
    QFileDialog, QApplication,
)

from app.workers import (
    SSHMetricsWorker, SSHCommandWorker, LogTailWorker,
    ServiceHealthCheckWorker, BatchSSHCommandWorker,
)
from app.theme import (
    BG_DEEP, BG_PANEL, BG_PANEL_HOVER, BG_INPUT,
    FG_PRIMARY, FG_SECONDARY, FG_TERTIARY, FG_DISABLED,
    PRIMARY, SUCCESS, WARN, DANGER, BORDER, BORDER_LIGHT, BORDER_FOCUS,
    FONT_FAMILY, FONT_SIZE_BASE, FONT_SIZE_SM, FONT_SIZE_MD,
    RADIUS_SM, RADIUS_MD, RADIUS_LG, CHART_PALETTE,
)


ASSETS_DIR = os.path.join(os.path.expanduser("~"), ".aiinlink")
ASSETS_FILE = os.path.join(ASSETS_DIR, "assets.json")


# ============================================================
# 资产持久化
# ============================================================

def _load_assets() -> dict:
    if not os.path.exists(ASSETS_FILE):
        return {"groups": [{"name": "默认分组", "hosts": []}]}
    try:
        with open(ASSETS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "groups" not in data or not data["groups"]:
            data["groups"] = [{"name": "默认分组", "hosts": []}]
        return data
    except Exception:
        return {"groups": [{"name": "默认分组", "hosts": []}]}


def _save_assets(data: dict):
    try:
        os.makedirs(ASSETS_DIR, exist_ok=True)
        with open(ASSETS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存资产失败: {e}")


# ============================================================
# 主机编辑对话框
# ============================================================

class HostEditDialog(QDialog):
    """添加/编辑主机"""

    def __init__(self, host: Optional[dict] = None, groups: Optional[list] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑主机" if host else "添加主机")
        self.setMinimumWidth(440)
        self._groups = groups or ["默认分组"]

        layout = QFormLayout(self)

        self._name = QLineEdit()
        self._name.setPlaceholderText("主机别名（便于识别）")
        layout.addRow("名称:", self._name)

        self._host = QLineEdit()
        self._host.setPlaceholderText("IP 或域名")
        layout.addRow("主机:", self._host)

        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(22)
        layout.addRow("SSH 端口:", self._port)

        self._user = QLineEdit()
        self._user.setText("root")
        layout.addRow("用户名:", self._user)

        self._auth = QComboBox()
        self._auth.addItems(["密码", "密钥"])
        self._auth.currentIndexChanged.connect(self._on_auth)
        layout.addRow("认证方式:", self._auth)

        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.Password)
        layout.addRow("密码:", self._password)

        self._key = QLineEdit()
        self._key.setPlaceholderText("私钥文件绝对路径")
        self._key.setVisible(False)
        layout.addRow("私钥路径:", self._key)

        self._group = QComboBox()
        self._group.addItems(self._groups)
        self._group.setEditable(True)
        layout.addRow("所属分组:", self._group)

        self._tags = QLineEdit()
        self._tags.setPlaceholderText("逗号分隔，如: prod,mysql,核心")
        layout.addRow("标签:", self._tags)

        self._note = QLineEdit()
        self._note.setPlaceholderText("备注")
        layout.addRow("备注:", self._note)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        if host:
            self._name.setText(host.get("name", ""))
            self._host.setText(host.get("host", ""))
            self._port.setValue(host.get("port", 22))
            self._user.setText(host.get("username", "root"))
            if host.get("auth_type") == "key":
                self._auth.setCurrentIndex(1)
                self._key.setText(host.get("key_path", ""))
            else:
                self._password.setText(host.get("password", ""))
            g = host.get("group", "默认分组")
            if g in self._groups:
                self._group.setCurrentText(g)
            else:
                self._group.setEditText(g)
            self._tags.setText(",".join(host.get("tags") or []))
            self._note.setText(host.get("note", ""))

    def _on_auth(self, idx: int):
        is_key = idx == 1
        self._password.setVisible(not is_key)
        self._key.setVisible(is_key)

    def get_data(self) -> dict:
        return {
            "name": self._name.text().strip() or self._host.text().strip(),
            "host": self._host.text().strip(),
            "port": self._port.value(),
            "username": self._user.text().strip() or "root",
            "auth_type": "key" if self._auth.currentIndex() == 1 else "password",
            "password": self._password.text(),
            "key_path": self._key.text().strip(),
            "key_passphrase": "",
            "group": self._group.currentText().strip() or "默认分组",
            "tags": [t.strip() for t in self._tags.text().split(",") if t.strip()],
            "note": self._note.text().strip(),
            "created_at": int(time.time()),
        }


# ============================================================
# 简易折线图
# ============================================================

class LineChart(QWidget):
    """渐变填充的实时折线图，支持多条曲线、网格、图例、平滑曲线"""

    def __init__(self, max_points: int = 120, y_range: tuple = (0, 100),
                 title: str = "", parent=None):
        super().__init__(parent)
        self._max_points = max_points
        self._y_min, self._y_max = y_range
        self._title = title
        self._series: Dict[str, deque] = {}
        self._colors: Dict[str, str] = {}
        self._palette = CHART_PALETTE
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def add_series(self, name: str, color: Optional[str] = None):
        if name not in self._series:
            self._series[name] = deque(maxlen=self._max_points)
            self._colors[name] = color or self._palette[len(self._colors) % len(self._palette)]

    def push(self, name: str, value: float):
        if name not in self._series:
            self.add_series(name)
        if value is None or value < 0:
            return
        self._series[name].append((time.time(), float(value)))
        self.update()

    def set_y_range(self, y_min: float, y_max: float):
        self._y_min, self._y_max = y_min, y_max
        self.update()

    def paintEvent(self, event):
        from PySide6.QtGui import QPainterPath, QLinearGradient
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        margin_l, margin_r, margin_t, margin_b = 40, 14, 24, 22

        # 背景
        p.fillRect(self.rect(), QColor(BG_DEEP))

        # 标题
        if self._title:
            p.setPen(QColor(FG_PRIMARY))
            p.setFont(QFont(FONT_FAMILY, 10, QFont.DemiBold))
            p.drawText(margin_l, 16, self._title)

        # 坐标网格
        chart_top = margin_t
        chart_bottom = h - margin_b
        chart_left = margin_l
        chart_right = w - margin_r

        # 水平网格
        for i in range(5):
            y = chart_top + (chart_bottom - chart_top) * i / 4
            p.setPen(QPen(QColor(BORDER_LIGHT), 1, Qt.DashLine))
            p.drawLine(chart_left, int(y), chart_right, int(y))
            # Y 轴刻度
            val = self._y_max - (self._y_max - self._y_min) * i / 4
            p.setPen(QColor(FG_TERTIARY))
            p.setFont(QFont(FONT_FAMILY, 9))
            p.drawText(4, int(y) + 4, f"{val:.0f}")

        # 垂直网格（更淡）
        n_vlines = 6
        for i in range(1, n_vlines):
            x = chart_left + (chart_right - chart_left) * i / n_vlines
            p.setPen(QPen(QColor(BORDER), 1, Qt.DotLine))
            p.drawLine(int(x), chart_top, int(x), chart_bottom)

        if not self._series:
            p.setPen(QColor(FG_TERTIARY))
            p.setFont(QFont(FONT_FAMILY, 10))
            p.drawText(chart_left + 10, (chart_top + chart_bottom) // 2, "暂无数据")
            return

        # 时间范围
        now = time.time()
        x_left = now - self._max_points
        x_right = now

        def map_xy(ts: float, val: float) -> tuple:
            x_ratio = (ts - x_left) / (x_right - x_left) if x_right > x_left else 0
            y_ratio = (val - self._y_min) / (self._y_max - self._y_min) if self._y_max > self._y_min else 0
            x = chart_left + x_ratio * (chart_right - chart_left)
            y = chart_bottom - y_ratio * (chart_bottom - chart_top)
            return int(x), int(y)

        # 绘制每条曲线
        for name, data in self._series.items():
            if len(data) < 2:
                continue
            color = QColor(self._colors.get(name, PRIMARY))

            # 1) 渐变填充区域
            fill = QPainterPath()
            pts = [map_xy(ts, val) for ts, val in data if x_left <= ts <= x_right]
            if len(pts) < 2:
                continue
            fill.moveTo(pts[0][0], chart_bottom)
            for x, y in pts:
                fill.lineTo(x, y)
            fill.lineTo(pts[-1][0], chart_bottom)
            fill.closeSubpath()

            grad = QLinearGradient(0, chart_top, 0, chart_bottom)
            grad.setColorAt(0, QColor(color.red(), color.green(), color.blue(), 90))
            grad.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
            p.fillPath(fill, QBrush(grad))

            # 2) 折线
            p.setPen(QPen(color, 2))
            p.setBrush(Qt.NoBrush)
            line = QPainterPath()
            line.moveTo(pts[0][0], pts[0][1])
            for x, y in pts[1:]:
                line.lineTo(x, y)
            p.drawPath(line)

            # 3) 最新点发光
            last_x, last_y = pts[-1]
            # 外发光
            for radius, alpha in [(10, 30), (7, 60), (4, 120)]:
                glow = QColor(color)
                glow.setAlpha(alpha)
                p.setPen(Qt.NoPen)
                p.setBrush(glow)
                p.drawEllipse(QPoint(last_x, last_y), radius, radius)
            # 实心点
            p.setBrush(color)
            p.drawEllipse(QPoint(last_x, last_y), 3, 3)

        # 图例
        legend_x = chart_left + 6
        legend_y = chart_top + 4
        for i, (name, data) in enumerate(self._series.items()):
            color = QColor(self._colors.get(name, PRIMARY))
            p.setPen(color)
            p.setBrush(color)
            p.drawRoundedRect(legend_x, legend_y + i * 14, 10, 10, 2, 2)
            p.setPen(QColor(FG_PRIMARY))
            last_val = f"{data[-1][1]:.1f}" if data else "--"
            p.setFont(QFont(FONT_FAMILY, 9))
            p.drawText(legend_x + 16, legend_y + i * 14 + 9,
                       f"{name}  {last_val}")


# ============================================================
# 资产卡片 / 状态徽章
# ============================================================

class StatusBadge(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(20)
        self.setMinimumWidth(60)
        self.setAlignment(Qt.AlignCenter)
        self.setProperty("role", "badge")
        self.setStyleSheet("""
            QLabel {
                color: white;
                border-radius: 9px;
                padding: 0 8px;
                font-size: 11px;
                font-weight: bold;
            }
        """)
        self.set_status("unknown", "未知")

    def set_status(self, kind: str, text: Optional[str] = None):
        colors = {
            "ok": "#2d8f5b",
            "warn": "#c08a2a",
            "fail": "#c75252",
            "unknown": "#555",
        }
        labels = {
            "ok": "正常",
            "warn": "告警",
            "fail": "异常",
            "unknown": "未知",
        }
        bg = colors.get(kind, "#555")
        self.setText(text or labels.get(kind, "未知"))
        self.setStyleSheet(self.styleSheet().replace(
            "border-radius: 9px;", f"background-color: {bg}; border-radius: 9px;"
        ))


class MetricCard(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setProperty("role", "card")
        self.setStyleSheet("""
            QFrame {
                background-color: #1c2029;
                border: 1px solid #262b35;
                border-radius: 6px;
            }
        """)
        self._title = QLabel(title)
        self._title.setProperty("role", "caption")
        self._title.setStyleSheet("color:#a8b0bf; font-size:11px; background: transparent;")
        self._value = QLabel("--")
        self._value.setProperty("role", "value")
        self._value.setStyleSheet("color:#4ecdc4; font-size:20px; font-weight:bold; background: transparent;")
        self._sub = QLabel("")
        self._sub.setProperty("role", "muted")
        self._sub.setStyleSheet("color:#a8b0bf; font-size:11px; background: transparent;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(2)
        lay.addWidget(self._title)
        lay.addWidget(self._value)
        lay.addWidget(self._sub)

    def update_value(self, value: str, sub: str = "", color: Optional[str] = None):
        self._value.setText(value)
        self._sub.setText(sub)
        if color:
            self._value.setStyleSheet(
                f"color:{color}; font-size:20px; font-weight:bold;")


# ============================================================
# 子模块 1：资产管理
# ============================================================

class AssetManagerWidget(QWidget):
    host_double_clicked = Signal(dict)  # 通知其他模块

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = _load_assets()
        self._selected_group: Optional[str] = None
        self._selected_host: Optional[dict] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # 左侧分组树
        left = QFrame()
        left.setFixedWidth(220)
        left.setStyleSheet("QFrame { background-color: #252526; border: 1px solid #3c3c3c; border-radius: 4px; }")
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(6, 6, 6, 6)
        left_lay.addWidget(QLabel("分组"))
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setStyleSheet("QTreeWidget { background:#1e1e1e; color:#ccc; border:none; }"
                                 "QTreeWidget::item:selected { background:#094771; }")
        self._tree.itemSelectionChanged.connect(self._on_group_select)
        left_lay.addWidget(self._tree, 1)

        grp_btn_lay = QHBoxLayout()
        b1 = QPushButton("+ 分组")
        b1.clicked.connect(self._add_group)
        b2 = QPushButton("−")
        b2.setFixedWidth(28)
        b2.clicked.connect(self._del_group)
        grp_btn_lay.addWidget(b1)
        grp_btn_lay.addWidget(b2)
        left_lay.addLayout(grp_btn_lay)

        layout.addWidget(left)

        # 右侧主机表
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(6)

        bar = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("搜索主机名/IP/标签")
        self._search.textChanged.connect(self._refresh_table)
        bar.addWidget(self._search, 1)
        b_add = QPushButton("+ 主机")
        b_add.clicked.connect(self._add_host)
        bar.addWidget(b_add)
        b_edit = QPushButton("编辑")
        b_edit.clicked.connect(self._edit_host)
        bar.addWidget(b_edit)
        b_dup = QPushButton("复制")
        b_dup.setToolTip("复制当前选中的主机（用于快速创建相似主机）")
        b_dup.clicked.connect(self._duplicate_host)
        bar.addWidget(b_dup)
        b_del = QPushButton("删除")
        b_del.clicked.connect(self._del_host)
        bar.addWidget(b_del)
        b_test = QPushButton("测试连接")
        b_test.clicked.connect(self._test_host)
        bar.addWidget(b_test)
        right_lay.addLayout(bar)

        # 标签云过滤
        tag_bar = QHBoxLayout()
        tag_bar.setSpacing(4)
        tag_bar.addWidget(QLabel("🏷 标签:"))
        self._tag_cloud_host = QWidget()
        self._tag_cloud_layout = QHBoxLayout(self._tag_cloud_host)
        self._tag_cloud_layout.setContentsMargins(0, 0, 0, 0)
        self._tag_cloud_layout.setSpacing(4)
        self._tag_cloud_layout.addStretch()
        self._active_tag: Optional[str] = None
        self._tag_buttons: Dict[str, QPushButton] = {}
        tag_bar.addWidget(self._tag_cloud_host, 1)
        b_clear_tag = QPushButton("清除筛选")
        b_clear_tag.clicked.connect(self._clear_tag_filter)
        tag_bar.addWidget(b_clear_tag)
        b_refresh_tag = QPushButton("🔄")
        b_refresh_tag.setToolTip("刷新标签云")
        b_refresh_tag.clicked.connect(self._refresh_tag_cloud)
        tag_bar.addWidget(b_refresh_tag)
        right_lay.addLayout(tag_bar)

        # 第二行操作
        bar2 = QHBoxLayout()
        b_import = QPushButton("📥 导入")
        b_import.setToolTip("从 CSV 或 JSON 文件批量导入主机")
        b_import.clicked.connect(self._import_hosts)
        bar2.addWidget(b_import)
        b_export = QPushButton("📤 导出")
        b_export.setToolTip("导出主机到 CSV 或 JSON")
        b_export.clicked.connect(self._export_hosts)
        bar2.addWidget(b_export)
        b_tpl = QPushButton("📋 下载模板")
        b_tpl.setToolTip("下载 CSV 导入模板")
        b_tpl.clicked.connect(self._download_template)
        bar2.addWidget(b_tpl)
        bar2.addStretch()
        right_lay.addLayout(bar2)

        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            ["名称", "主机", "端口", "用户", "认证", "分组", "标签"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.doubleClicked.connect(self._on_table_dbl)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_menu)
        right_lay.addWidget(self._table, 1)

        # 统计
        self._summary = QLabel("0 台主机")
        self._summary.setStyleSheet("color:#888;")
        right_lay.addWidget(self._summary)

        layout.addWidget(right, 1)
        self._refresh_tree()
        self._refresh_tag_cloud()
        self._refresh_table()

    # ---- 数据 ----
    def _save(self):
        _save_assets(self._data)

    def all_hosts(self) -> List[dict]:
        out = []
        for g in self._data.get("groups", []):
            for h in g.get("hosts", []):
                out.append(h)
        return out

    def get_host(self, name: str) -> Optional[dict]:
        for h in self.all_hosts():
            if h.get("name") == name:
                return h
        return None

    def _refresh_tree(self):
        self._tree.clear()
        all_grp = QTreeWidgetItem(["全部主机"])
        all_grp.setData(0, Qt.UserRole, "__ALL__")
        self._tree.addTopLevelItem(all_grp)
        for g in self._data.get("groups", []):
            gname = g.get("name", "")
            item = QTreeWidgetItem([f"{gname} ({len(g.get('hosts', []))})"])
            item.setData(0, Qt.UserRole, gname)
            self._tree.addTopLevelItem(item)
        # 默认选中第一项
        if self._tree.topLevelItemCount() > 0:
            self._tree.setCurrentItem(self._tree.topLevelItem(0))

    def _refresh_table(self):
        self._table.setRowCount(0)
        kw = self._search.text().strip().lower()
        all_hosts = self.all_hosts()
        if self._selected_group and self._selected_group != "__ALL__":
            hosts = [h for h in all_hosts if h.get("group") == self._selected_group]
        else:
            hosts = all_hosts
        if kw:
            hosts = [h for h in hosts if
                     kw in h.get("name", "").lower()
                     or kw in h.get("host", "").lower()
                     or any(kw in t.lower() for t in h.get("tags", []))]
        if self._active_tag:
            hosts = [h for h in hosts
                     if self._active_tag in (h.get("tags") or [])]
        for h in hosts:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(h.get("name", "")))
            self._table.setItem(row, 1, QTableWidgetItem(h.get("host", "")))
            self._table.setItem(row, 2, QTableWidgetItem(str(h.get("port", 22))))
            self._table.setItem(row, 3, QTableWidgetItem(h.get("username", "")))
            self._table.setItem(row, 4, QTableWidgetItem(
                "密钥" if h.get("auth_type") == "key" else "密码"))
            self._table.setItem(row, 5, QTableWidgetItem(h.get("group", "")))
            self._table.setItem(row, 6, QTableWidgetItem(",".join(h.get("tags", []))))
        self._summary.setText(
            f"共 {len(hosts)} 台主机（总计 {len(all_hosts)} 台）"
            + (f"  标签: {self._active_tag}" if self._active_tag else ""))

    def _refresh_tag_cloud(self):
        """根据当前所有主机的标签重新渲染标签云"""
        # 统计标签出现次数
        tag_count: Dict[str, int] = {}
        for h in self.all_hosts():
            for t in h.get("tags") or []:
                tag_count[t] = tag_count.get(t, 0) + 1

        # 清空旧按钮（保留最后的 stretch）
        for btn in self._tag_buttons.values():
            self._tag_cloud_layout.removeWidget(btn)
            btn.deleteLater()
        self._tag_buttons.clear()
        # 移除占位 stretch
        for i in range(self._tag_cloud_layout.count() - 1, -1, -1):
            item = self._tag_cloud_layout.itemAt(i)
            if item and item.spacerItem():
                self._tag_cloud_layout.removeItem(item)
                break

        # 按使用次数降序
        for tag, cnt in sorted(tag_count.items(), key=lambda x: -x[1]):
            btn = QPushButton(f"{tag} ({cnt})")
            btn.setCheckable(True)
            btn.setChecked(self._active_tag == tag)
            btn.setCursor(Qt.PointingHandCursor)
            # 标签颜色：基于使用频率调整深浅
            opacity = min(1.0, 0.55 + cnt * 0.1)
            if self._active_tag == tag:
                bg = f"rgba(78, 205, 196, {opacity})"
                color = "#fff"
                border = "#4ecdc4"
            else:
                bg = f"rgba(78, 205, 196, {opacity * 0.4:.2f})"
                color = "#cfd8dc"
                border = "rgba(78, 205, 196, 0.5)"
            btn.setStyleSheet(
                f"QPushButton {{ background:{bg}; color:{color}; border:1px solid {border};"
                f" border-radius:10px; padding:2px 10px; font-size:11px; }}"
                f"QPushButton:hover {{ background:rgba(78,205,196,0.7); color:#fff; }}"
            )
            btn.clicked.connect(lambda checked=False, t=tag: self._toggle_tag(t))
            self._tag_cloud_layout.addWidget(btn)
            self._tag_buttons[tag] = btn
        # 末尾补一个 stretch
        self._tag_cloud_layout.addStretch()

    def _toggle_tag(self, tag: str):
        if self._active_tag == tag:
            self._active_tag = None
        else:
            self._active_tag = tag
        self._refresh_tag_cloud()
        self._refresh_table()

    def _clear_tag_filter(self):
        if self._active_tag is None:
            return
        self._active_tag = None
        self._refresh_tag_cloud()
        self._refresh_table()

    # ---- 事件 ----
    def _on_group_select(self):
        item = self._tree.currentItem()
        if not item:
            return
        self._selected_group = item.data(0, Qt.UserRole)
        self._refresh_table()

    def _on_table_dbl(self, idx):
        self._edit_host()

    def _add_group(self):
        name, ok = QInputDialog.getText(self, "新增分组", "分组名称:")
        if ok and name.strip():
            self._data.setdefault("groups", []).append({"name": name.strip(), "hosts": []})
            self._save()
            self._refresh_tree()

    def _del_group(self):
        item = self._tree.currentItem()
        if not item:
            return
        g = item.data(0, Qt.UserRole)
        if g in (None, "__ALL__"):
            return
        if QMessageBox.question(
            self, "删除分组",
            f"确定删除分组 [{g}] 及其全部主机？"
        ) == QMessageBox.Yes:
            self._data["groups"] = [g for g2 in self._data["groups"] if g2.get("name") != g]
            self._save()
            self._refresh_tree()
            self._refresh_table()

    def _add_host(self):
        groups = [g.get("name", "") for g in self._data.get("groups", [])]
        dlg = HostEditDialog(groups=groups, parent=self)
        if dlg.exec() == QDialog.Accepted:
            h = dlg.get_data()
            if not h["host"]:
                QMessageBox.warning(self, "错误", "主机不能为空")
                return
            gname = h["group"]
            grp = next((g for g in self._data["groups"] if g.get("name") == gname), None)
            if not grp:
                grp = {"name": gname, "hosts": []}
                self._data["groups"].append(grp)
            grp.setdefault("hosts", []).append(h)
            self._save()
            self._refresh_tree()
            self._refresh_tag_cloud()
            self._refresh_table()

    def _edit_host(self):
        row = self._table.currentRow()
        if row < 0:
            return
        name = self._table.item(row, 0).text()
        host = self.get_host(name)
        if not host:
            return
        groups = [g.get("name", "") for g in self._data.get("groups", [])]
        dlg = HostEditDialog(host=host, groups=groups, parent=self)
        if dlg.exec() == QDialog.Accepted:
            new = dlg.get_data()
            for g in self._data["groups"]:
                if name in [h.get("name") for h in g.get("hosts", [])]:
                    g["hosts"] = [new if h.get("name") == name else h
                                  for h in g.get("hosts", [])]
                    break
            self._save()
            self._refresh_tree()
            self._refresh_tag_cloud()
            self._refresh_table()

    def _del_host(self):
        row = self._table.currentRow()
        if row < 0:
            return
        name = self._table.item(row, 0).text()
        if QMessageBox.question(
            self, "删除主机", f"确定删除主机 [{name}]？"
        ) == QMessageBox.Yes:
            for g in self._data["groups"]:
                g["hosts"] = [h for h in g.get("hosts", []) if h.get("name") != name]
            self._save()
            self._refresh_tree()
            self._refresh_tag_cloud()
            self._refresh_table()

    def _duplicate_host(self):
        """复制当前选中主机（用于快速创建相似主机）"""
        row = self._table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先在表格中选中要复制的主机")
            return
        name = self._table.item(row, 0).text()
        host = self.get_host(name)
        if not host:
            return
        # 深拷贝并改名为 "<name>_副本"，端口号 +1
        import copy
        new = copy.deepcopy(host)
        new["name"] = self._gen_unique_name(f"{host.get('name')}_副本")
        try:
            new["port"] = int(host.get("port", 22)) + 1
        except Exception:
            pass
        new["created_at"] = int(time.time())
        new["note"] = (host.get("note", "") + " [复制自 " + name + "]").strip()
        gname = host.get("group", "默认分组")
        grp = next((g for g in self._data["groups"] if g.get("name") == gname), None)
        if not grp:
            grp = {"name": gname, "hosts": []}
            self._data["groups"].append(grp)
        grp.setdefault("hosts", []).append(new)
        self._save()
        self._refresh_tree()
        self._refresh_tag_cloud()
        self._refresh_table()
        # 选中新行
        for r in range(self._table.rowCount()):
            if self._table.item(r, 0).text() == new["name"]:
                self._table.setCurrentCell(r, 0)
                break
        try:
            from app.audit_log import audit
            audit("asset.duplicate", target=name, details={"new_name": new["name"]})
        except Exception:
            pass

    def _gen_unique_name(self, base: str) -> str:
        existing = {h.get("name") for g in self._data["groups"]
                    for h in g.get("hosts", [])}
        if base not in existing:
            return base
        for i in range(2, 1000):
            cand = f"{base}_{i}"
            if cand not in existing:
                return cand
        return f"{base}_{int(time.time())}"

    def _on_table_menu(self, pos):
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        self._table.selectRow(row)
        menu = QMenu(self)
        act_edit = menu.addAction("✏ 编辑")
        act_dup = menu.addAction("📋 复制主机")
        act_test = menu.addAction("🔌 测试连接")
        menu.addSeparator()
        act_copy = menu.addAction("📑 复制选中行")
        act_del = menu.addAction("🗑 删除")
        act = menu.exec(self._table.viewport().mapToGlobal(pos))
        if act == act_edit:
            self._edit_host()
        elif act == act_dup:
            self._duplicate_host()
        elif act == act_test:
            self._test_host()
        elif act == act_copy:
            self._copy_row_to_clipboard(row)
        elif act == act_del:
            self._del_host()

    def _copy_row_to_clipboard(self, row: int):
        """将指定行的内容复制到剪贴板（制表符分隔，方便粘到 Excel）"""
        cols = []
        for c in range(self._table.columnCount()):
            item = self._table.item(row, c)
            cols.append(item.text() if item else "")
        text = "\t".join(cols)
        QApplication.clipboard().setText(text)
        self._summary.setText(f"已复制到剪贴板: {cols[0] if cols else ''}")

    def _import_hosts(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择主机文件",
            os.path.expanduser("~"),
            "CSV 文件 (*.csv);;JSON 文件 (*.json);;所有文件 (*)")
        if not path:
            return
        try:
            if path.lower().endswith(".json"):
                hosts = self._read_json_hosts(path)
            else:
                hosts = self._read_csv_hosts(path)
        except Exception as e:
            QMessageBox.critical(self, "导入失败", str(e))
            return
        if not hosts:
            QMessageBox.information(self, "提示", "文件中未发现可导入的主机")
            return
        # 询问：追加 vs 覆盖同名
        existing_names = {h.get("name") for g in self._data["groups"]
                          for h in g.get("hosts", [])}
        conflict = [h["name"] for h in hosts if h.get("name") in existing_names]
        overwrite = False
        if conflict:
            choice = QMessageBox.question(
                self, "冲突处理",
                f"检测到 {len(conflict)} 个主机名与现有冲突：\n"
                f"{', '.join(conflict[:10])}{'...' if len(conflict) > 10 else ''}\n\n"
                "选择 [是] 覆盖，[否] 跳过冲突，[取消] 终止导入。",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if choice == QMessageBox.Cancel:
                return
            if choice == QMessageBox.No:
                hosts = [h for h in hosts if h.get("name") not in existing_names]
                overwrite = False
            else:
                overwrite = True

        added = 0
        replaced = 0
        for h in hosts:
            if not h.get("host"):
                continue
            name = h["name"]
            target_group = h.get("group", "默认分组")
            grp = next((g for g in self._data["groups"] if g.get("name") == target_group), None)
            if not grp:
                grp = {"name": target_group, "hosts": []}
                self._data["groups"].append(grp)
            if overwrite and any(hh.get("name") == name for hh in grp.get("hosts", [])):
                grp["hosts"] = [hh for hh in grp["hosts"] if hh.get("name") != name]
                replaced += 1
            grp.setdefault("hosts", []).append(h)
            added += 1
        self._save()
        self._refresh_tree()
        self._refresh_tag_cloud()
        self._refresh_table()
        try:
            from app.audit_log import audit
            audit("asset.import", target=path,
                  details={"added": added, "replaced": replaced, "total_in_file": len(hosts)})
        except Exception:
            pass
        QMessageBox.information(
            self, "导入完成",
            f"新增: {added}  覆盖: {replaced}  文件总数: {len(hosts)}\n\n文件: {path}")

    def _read_csv_hosts(self, path: str) -> List[dict]:
        out: List[dict] = []
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not row:
                    continue
                # 跳过空行
                if not any((v or "").strip() for v in row.values()):
                    continue
                name = (row.get("name") or row.get("名称") or "").strip()
                host = (row.get("host") or row.get("主机") or row.get("IP") or "").strip()
                if not host:
                    continue
                port_s = (row.get("port") or row.get("端口") or "22").strip()
                try:
                    port = int(port_s) if port_s else 22
                except ValueError:
                    port = 22
                username = (row.get("username") or row.get("用户") or row.get("用户名") or "root").strip()
                auth_type = (row.get("auth_type") or row.get("认证") or "password").strip().lower()
                if "密钥" in auth_type or "key" in auth_type:
                    auth_type = "key"
                else:
                    auth_type = "password"
                password = row.get("password") or row.get("密码") or ""
                key_path = (row.get("key_path") or row.get("私钥") or "").strip()
                group = (row.get("group") or row.get("分组") or "导入分组").strip()
                tags_s = (row.get("tags") or row.get("标签") or "").strip()
                tags = [t.strip() for t in tags_s.replace(";", ",").split(",") if t.strip()]
                note = (row.get("note") or row.get("备注") or "").strip()
                out.append({
                    "name": name or host,
                    "host": host,
                    "port": port,
                    "username": username or "root",
                    "auth_type": auth_type,
                    "password": password,
                    "key_path": key_path,
                    "key_passphrase": "",
                    "group": group or "导入分组",
                    "tags": tags,
                    "note": note,
                    "created_at": int(time.time()),
                })
        return out

    def _read_json_hosts(self, path: str) -> List[dict]:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        out: List[dict] = []
        # 支持两种 JSON 格式：
        #  1) {"groups": [{"name":..., "hosts":[...]}]}
        #  2) [{"name":..., "host":..., ...}, ...]
        if isinstance(data, dict) and "groups" in data:
            for g in data.get("groups", []):
                for h in g.get("hosts", []):
                    if h.get("host"):
                        out.append(self._normalize_imported_host(h))
        elif isinstance(data, list):
            for h in data:
                if isinstance(h, dict) and h.get("host"):
                    out.append(self._normalize_imported_host(h))
        return out

    @staticmethod
    def _normalize_imported_host(h: dict) -> dict:
        return {
            "name": (h.get("name") or h.get("host", "")).strip(),
            "host": (h.get("host") or "").strip(),
            "port": int(h.get("port", 22) or 22),
            "username": (h.get("username") or "root").strip(),
            "auth_type": "key" if (h.get("auth_type") == "key") else "password",
            "password": h.get("password") or "",
            "key_path": h.get("key_path") or "",
            "key_passphrase": h.get("key_passphrase") or "",
            "group": (h.get("group") or "导入分组").strip(),
            "tags": list(h.get("tags") or []),
            "note": h.get("note") or "",
            "created_at": int(h.get("created_at") or time.time()),
        }

    def _export_hosts(self):
        hosts = self.all_hosts()
        if not hosts:
            QMessageBox.information(self, "提示", "没有主机可导出")
            return
        path, sel = QFileDialog.getSaveFileName(
            self, "导出主机",
            os.path.join(os.path.expanduser("~"), "hosts_export.csv"),
            "CSV 文件 (*.csv);;JSON 文件 (*.json)")
        if not path:
            return
        try:
            if "json" in sel.lower() or path.lower().endswith(".json"):
                # 导出分组结构
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, ensure_ascii=False, indent=2)
            else:
                if not path.lower().endswith(".csv"):
                    path += ".csv"
                self._write_csv_hosts(path, hosts)
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))
            return
        try:
            from app.audit_log import audit
            audit("asset.export", target=path, details={"count": len(hosts)})
        except Exception:
            pass
        QMessageBox.information(self, "导出成功",
                                f"已导出 {len(hosts)} 台主机到:\n{path}")

    @staticmethod
    def _write_csv_hosts(path: str, hosts: List[dict]):
        fields = ["name", "host", "port", "username", "auth_type",
                  "password", "key_path", "group", "tags", "note"]
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for h in hosts:
                row = {k: h.get(k, "") for k in fields}
                # tags 转字符串
                if isinstance(row["tags"], list):
                    row["tags"] = ",".join(row["tags"])
                writer.writerow(row)

    def _download_template(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "保存模板",
            os.path.join(os.path.expanduser("~"), "host_template.csv"),
            "CSV 文件 (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(
                    f, fieldnames=["name", "host", "port", "username",
                                   "auth_type", "password", "key_path",
                                   "group", "tags", "note"])
                w.writeheader()
                w.writerow({
                    "name": "示例-Web1", "host": "192.168.1.10", "port": 22,
                    "username": "root", "auth_type": "password",
                    "password": "", "key_path": "",
                    "group": "Web 服务器", "tags": "web,prod",
                    "note": "示例备注"
                })
                w.writerow({
                    "name": "示例-DB1", "host": "192.168.1.20", "port": 22,
                    "username": "root", "auth_type": "key",
                    "password": "", "key_path": "/path/to/key",
                    "group": "数据库", "tags": "db,mysql",
                    "note": "使用密钥登录"
                })
            QMessageBox.information(self, "成功", f"模板已保存到:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "失败", str(e))

    def _test_host(self):
        row = self._table.currentRow()
        if row < 0:
            return
        name = self._table.item(row, 0).text()
        host = self.get_host(name)
        if not host:
            return
        self._tester = SSHCommandWorker(
            host=host["host"], port=host.get("port", 22),
            username=host.get("username", "root"),
            command="echo __PONG__; uname -a; uptime",
            auth_type=host.get("auth_type", "password"),
            password=host.get("password", ""),
            key_path=host.get("key_path", ""),
            key_passphrase=host.get("key_passphrase", ""),
        )
        self._tester.result_ready.connect(
            lambda h, o, e: self._on_test_result(name, h, o, e))
        self._tester.start()

    def _on_test_result(self, name: str, host: str, output: str, err: str):
        if err and "__PONG__" not in output:
            QMessageBox.critical(self, "连接失败", f"{name} ({host}):\n{err}")
        else:
            lines = output.splitlines()[:6]
            QMessageBox.information(
                self, "连接成功",
                f"{name} ({host})\n\n" + "\n".join(lines))


# ============================================================
# 子模块 2：实时监控
# ============================================================

class MonitorWidget(QWidget):
    def __init__(self, asset: AssetManagerWidget, parent=None):
        super().__init__(parent)
        self._asset = asset
        self._workers: Dict[str, SSHMetricsWorker] = {}
        self._history: Dict[str, Dict[str, deque]] = {}  # host -> {metric -> deque}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # 控制栏
        bar = QHBoxLayout()
        bar.addWidget(QLabel("主机:"))
        self._host_combo = QComboBox()
        self._host_combo.setMinimumWidth(200)
        self._refresh_host_combo()
        bar.addWidget(self._host_combo)
        b_refresh = QPushButton("刷新列表")
        b_refresh.clicked.connect(self._refresh_host_combo)
        bar.addWidget(b_refresh)

        bar.addWidget(QLabel("采样间隔:"))
        self._interval = QSpinBox()
        self._interval.setRange(2, 60)
        self._interval.setValue(3)
        self._interval.setSuffix(" 秒")
        bar.addWidget(self._interval)

        self._btn_start = QPushButton("▶ 开始监控")
        self._btn_start.clicked.connect(self._start_monitoring)
        bar.addWidget(self._btn_start)
        self._btn_stop = QPushButton("■ 停止")
        self._btn_stop.clicked.connect(self._stop_monitoring)
        self._btn_stop.setEnabled(False)
        bar.addWidget(self._btn_stop)
        bar.addStretch()
        layout.addLayout(bar)

        # 状态徽章
        self._badge = StatusBadge()
        bar.addWidget(self._badge)

        # 指标卡片
        cards = QGridLayout()
        self._card_cpu = MetricCard("CPU 使用率")
        self._card_mem = MetricCard("内存使用率")
        self._card_disk = MetricCard("磁盘使用率")
        self._card_load = MetricCard("系统负载 (1/5/15)")
        cards.addWidget(self._card_cpu, 0, 0)
        cards.addWidget(self._card_mem, 0, 1)
        cards.addWidget(self._card_disk, 0, 2)
        cards.addWidget(self._card_load, 0, 3)
        layout.addLayout(cards)

        # 主机信息
        info_lay = QHBoxLayout()
        self._host_info = QLabel("未连接")
        self._host_info.setStyleSheet("color:#888;")
        info_lay.addWidget(self._host_info)
        info_lay.addStretch()
        layout.addLayout(info_lay)

        # 折线图
        self._chart_cpu = LineChart(max_points=120, y_range=(0, 100), title="CPU %")
        self._chart_mem = LineChart(max_points=120, y_range=(0, 100), title="内存 %")
        self._chart_net = LineChart(max_points=120, y_range=(0, 100), title="网卡流量 KB/s")

        charts = QHBoxLayout()
        charts.addWidget(self._chart_cpu, 1)
        charts.addWidget(self._chart_mem, 1)
        layout.addLayout(charts, 3)

        layout.addWidget(self._chart_net, 2)

        self._last_net = None  # (rx, tx, ts) for KB/s 计算

    def _refresh_host_combo(self):
        cur = self._host_combo.currentText()
        self._host_combo.clear()
        for h in self._asset.all_hosts():
            self._host_combo.addItem(f"{h.get('name','')} ({h.get('host','')})", h.get("name"))
        if cur:
            idx = self._host_combo.findText(cur)
            if idx >= 0:
                self._host_combo.setCurrentIndex(idx)

    def _start_monitoring(self):
        self._stop_monitoring()
        name = self._host_combo.currentData()
        host = self._asset.get_host(name) if name else None
        if not host:
            QMessageBox.warning(self, "提示", "请先在资产管理中添加主机")
            return
        if not host.get("host"):
            QMessageBox.warning(self, "错误", "主机地址为空")
            return

        self._host_info.setText(
            f"主机: {host.get('name')}  |  地址: {host.get('host')}:{host.get('port')}  |  "
            f"用户: {host.get('username')}")

        worker = SSHMetricsWorker(
            host=host["host"], port=host.get("port", 22),
            username=host.get("username", "root"),
            auth_type=host.get("auth_type", "password"),
            password=host.get("password", ""),
            key_path=host.get("key_path", ""),
            key_passphrase=host.get("key_passphrase", ""),
            interval=float(self._interval.value()),
        )
        worker.metrics_ready.connect(self._on_metrics)
        worker.sample.connect(self._on_metrics)
        self._workers[host["host"]] = worker
        self._history[host["host"]] = {
            "cpu": deque(maxlen=120), "mem": deque(maxlen=120),
            "net_in": deque(maxlen=120), "net_out": deque(maxlen=120),
        }
        self._chart_cpu = self._chart_cpu  # 保持引用
        # 重置图表曲线
        for chart, names in [
            (self._chart_cpu, ["CPU"]),
            (self._chart_mem, ["内存"]),
            (self._chart_net, ["入站", "出站"]),
        ]:
            chart._series.clear()
            for n in names:
                chart.add_series(n)
        self._last_net = None

        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._badge.set_status("unknown", "采集中")
        worker.start()

    def _stop_monitoring(self):
        for w in self._workers.values():
            try:
                w.stop()
                w.wait(2000)
            except Exception:
                pass
        self._workers.clear()
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._badge.set_status("unknown", "已停止")

    def _on_metrics(self, info: dict):
        host = info.get("host", "")
        if not info.get("ok"):
            self._badge.set_status("fail", "连接失败")
            self._host_info.setText(self._host_info.text() + f"  [错误: {info.get('error', '')}]")
            return

        self._badge.set_status("ok", "采集中")

        # 更新卡片
        cpu = info.get("cpu_percent", -1)
        if cpu >= 0:
            self._card_cpu.update_value(f"{cpu:.1f}%", "CPU 占用", self._color_for(cpu))
            self._chart_cpu.push("CPU", cpu)

        mp = info.get("mem_percent")
        if mp is not None:
            self._card_mem.update_value(f"{mp:.1f}%",
                                        f"{info.get('mem_used_mb', 0):.0f} / {info.get('mem_total_mb', 0):.0f} MB",
                                        self._color_for(mp))
            self._chart_mem.push("内存", mp)

        dp = info.get("disk_percent")
        if dp is not None:
            self._card_disk.update_value(f"{dp:.1f}%",
                                         f"{info.get('disk_used_gb', 0):.1f} / {info.get('disk_total_gb', 0):.1f} GB",
                                         self._color_for(dp))

        l1 = info.get("load1")
        l5 = info.get("load5")
        l15 = info.get("load15")
        if l1 is not None:
            self._card_load.update_value(
                f"{l1:.2f}",
                f"5min: {l5:.2f}  15min: {l15:.2f}")

        # 网卡流量（差值）
        rx = info.get("net_rx_bytes")
        tx = info.get("net_tx_bytes")
        ts = info.get("timestamp", 0)
        if rx is not None and tx is not None and self._last_net is not None:
            prx, ptx, pts = self._last_net
            dt = max(ts - pts, 0.001)
            in_kbps = max(rx - prx, 0) / 1024.0 / dt
            out_kbps = max(tx - ptx, 0) / 1024.0 / dt
            self._chart_net.push("入站", in_kbps)
            self._chart_net.push("出站", out_kbps)
            # 自适应 Y 轴
            top = max(50.0, in_kbps * 1.3, out_kbps * 1.3)
            self._chart_net.set_y_range(0, top)
        self._last_net = (rx or 0, tx or 0, ts)

        # 主机名
        hn = info.get("hostname")
        up = info.get("uptime_sec")
        if hn:
            uptxt = ""
            if up:
                days, rem = divmod(up, 86400)
                hours = rem // 3600
                uptxt = f"  |  主机: {hn}  |  运行: {int(days)}d {int(hours)}h"
            self._host_info.setText(self._host_info.text() + uptxt)

    @staticmethod
    def _color_for(percent: float) -> str:
        if percent >= 85:
            return "#ff6b6b"
        if percent >= 70:
            return "#ffaa00"
        return "#4ecdc4"

    def stop(self):
        self._stop_monitoring()


# ============================================================
# 子模块 3：日志分析
# ============================================================

class LogAnalyzerWidget(QWidget):
    def __init__(self, asset: AssetManagerWidget, parent=None):
        super().__init__(parent)
        self._asset = asset
        self._worker: Optional[LogTailWorker] = None
        self._max_lines = 5000

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("主机:"))
        self._host_combo = QComboBox()
        self._host_combo.setMinimumWidth(200)
        self._refresh_hosts()
        bar.addWidget(self._host_combo)
        bar.addWidget(QLabel("日志路径:"))
        self._path = QLineEdit()
        self._path.setPlaceholderText("/var/log/syslog  或  C:\\Windows\\Logs\\...")
        bar.addWidget(self._path, 1)
        bar.addWidget(QLabel("关键字:"))
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("可选, ERROR/Failed/异常 ...")
        self._filter.textChanged.connect(self._apply_filter)
        bar.addWidget(self._filter, 1)
        self._auto_scroll = QCheckBox("自动滚动")
        self._auto_scroll.setChecked(True)
        bar.addWidget(self._auto_scroll)
        self._btn_start = QPushButton("▶ 开始")
        self._btn_start.clicked.connect(self._start)
        bar.addWidget(self._btn_start)
        self._btn_stop = QPushButton("■ 停止")
        self._btn_stop.clicked.connect(self._stop)
        self._btn_stop.setEnabled(False)
        bar.addWidget(self._btn_stop)
        b_clear = QPushButton("清屏")
        b_clear.clicked.connect(lambda: self._viewer.clear())
        bar.addWidget(b_clear)
        b_save = QPushButton("导出")
        b_save.clicked.connect(self._export)
        bar.addWidget(b_save)
        layout.addLayout(bar)

        self._badge = StatusBadge()
        bar.addWidget(self._badge)
        self._status = QLabel("未开始")
        self._status.setStyleSheet("color:#888;")
        layout.addWidget(self._status)

        self._viewer = QPlainTextEdit()
        self._viewer.setReadOnly(True)
        self._viewer.setMaximumBlockCount(self._max_lines)
        self._viewer.setStyleSheet("""
            QPlainTextEdit {
                background:#1e1e1e; color:#ccc;
                font-family: Consolas, 'Courier New', monospace; font-size: 12px;
            }
        """)
        layout.addWidget(self._viewer, 1)

        # 预置常用路径
        self._presets = [
            ("/var/log/syslog", "Linux syslog"),
            ("/var/log/messages", "Linux messages"),
            ("/var/log/auth.log", "Linux 认证日志"),
            ("/var/log/nginx/access.log", "Nginx access"),
            ("/var/log/nginx/error.log", "Nginx error"),
            ("/var/log/apache2/access.log", "Apache access"),
            ("/var/log/mysql/error.log", "MySQL error"),
            ("C:\\Windows\\System32\\winevt\\Logs\\System.evtx", "Windows System"),
            ("C:\\Windows\\System32\\LogFiles\\Firewall\\pfirewall.log", "Windows 防火墙"),
        ]
        preset_btn = QPushButton("📋 常用路径")
        preset_menu = QMenu(self)
        for path, desc in self._presets:
            act = preset_menu.addAction(f"{desc}  →  {path}")
            act.triggered.connect(lambda checked=False, p=path: self._path.setText(p))
        preset_btn.setMenu(preset_menu)
        bar.addWidget(preset_btn)

        # 关键字预设
        kw_btn = QPushButton("🔍 关键字")
        kw_menu = QMenu(self)
        for kw in ["ERROR", "WARN", "Failed", "Exception", "denied", "panic"]:
            act = kw_menu.addAction(kw)
            act.triggered.connect(lambda checked=False, k=kw: self._filter.setText(k))
        kw_btn.setMenu(kw_menu)
        bar.addWidget(kw_btn)

    def _refresh_hosts(self):
        self._host_combo.clear()
        for h in self._asset.all_hosts():
            self._host_combo.addItem(f"{h.get('name','')} ({h.get('host','')})", h.get("name"))

    def _start(self):
        if self._worker and self._worker.isRunning():
            return
        name = self._host_combo.currentData()
        host = self._asset.get_host(name) if name else None
        path = self._path.text().strip()
        if not host or not path:
            QMessageBox.warning(self, "提示", "请选择主机并填写日志路径")
            return
        self._stop()
        self._viewer.clear()
        self._badge.set_status("unknown", "连接中")
        self._status.setText(f"连接 {host['host']} ...")

        w = LogTailWorker(
            host=host["host"], port=host.get("port", 22),
            username=host.get("username", "root"),
            log_path=path,
            auth_type=host.get("auth_type", "password"),
            password=host.get("password", ""),
            key_path=host.get("key_path", ""),
            key_passphrase=host.get("key_passphrase", ""),
        )
        w.line_received.connect(self._on_line)
        w.status.connect(self._on_status)
        w.error.connect(self._on_error)
        self._worker = w
        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        w.start()

    def _stop(self):
        if self._worker:
            try:
                self._worker.stop()
                self._worker.wait(2000)
            except Exception:
                pass
            self._worker = None
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)

    def _on_status(self, host: str, ok: bool):
        if ok:
            self._badge.set_status("ok", "运行中")
            self._status.setText(f"已连接到 {host}, 等待日志输出...")
        else:
            self._badge.set_status("unknown", "已停止")
            self._status.setText("日志流已结束")

    def _on_error(self, host: str, err: str):
        self._badge.set_status("fail", "错误")
        self._status.setText(f"错误: {err}")
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)

    def _apply_filter(self):
        # 仅修改占位颜色提示；实际显示通过后续新行匹配
        self._viewer.setStyleSheet(self._viewer.styleSheet())

    def _on_line(self, host: str, line: str):
        kw = self._filter.text().strip()
        if kw and kw.lower() not in line.lower():
            return
        # 关键字高亮
        html = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if kw:
            import re
            try:
                html = re.sub(f"({re.escape(kw)})", r'<span style="background:#c08a2a; color:#fff;">\1</span>',
                              html, flags=re.IGNORECASE)
            except Exception:
                pass
        if "ERROR" in line.upper() or "FATAL" in line.upper() or "EXCEPTION" in line.upper():
            html = f'<span style="color:#ff6b6b;">{html}</span>'
        elif "WARN" in line.upper():
            html = f'<span style="color:#ffaa00;">{html}</span>'
        self._viewer.appendHtml(html)
        if self._auto_scroll.isChecked():
            sb = self._viewer.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _export(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "导出日志", "log.txt", "文本文件 (*.txt);;所有文件 (*)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self._viewer.toPlainText())
                QMessageBox.information(self, "成功", f"已保存到 {path}")
            except Exception as e:
                QMessageBox.critical(self, "失败", str(e))

    def stop(self):
        self._stop()


# ============================================================
# 子模块 4：进程管理
# ============================================================

class ProcessManagerWidget(QWidget):
    def __init__(self, asset: AssetManagerWidget, parent=None):
        super().__init__(parent)
        self._asset = asset
        self._worker: Optional[SSHCommandWorker] = None
        self._kill_worker: Optional[SSHCommandWorker] = None
        self._all_rows: List[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("主机:"))
        self._host_combo = QComboBox()
        self._host_combo.setMinimumWidth(200)
        self._refresh_hosts()
        bar.addWidget(self._host_combo)
        bar.addWidget(QLabel("排序:"))
        self._sort = QComboBox()
        self._sort.addItems(["CPU 占用", "内存占用", "PID"])
        bar.addWidget(self._sort)
        bar.addWidget(QLabel("关键字:"))
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("按进程名过滤")
        self._filter.textChanged.connect(self._render)
        bar.addWidget(self._filter, 1)
        self._top_n = QSpinBox()
        self._top_n.setRange(20, 500)
        self._top_n.setValue(50)
        bar.addWidget(QLabel("TOP"))
        bar.addWidget(self._top_n)
        self._btn_refresh = QPushButton("🔄 刷新")
        self._btn_refresh.clicked.connect(self._refresh)
        bar.addWidget(self._btn_refresh)
        self._auto = QCheckBox("自动刷新(5s)")
        self._auto.toggled.connect(self._toggle_auto)
        bar.addWidget(self._auto)
        self._badge = StatusBadge()
        bar.addWidget(self._badge)
        layout.addLayout(bar)

        # 第二行：进程操作
        bar2 = QHBoxLayout()
        bar2.addWidget(QLabel("PID:"))
        self._pid_input = QLineEdit()
        self._pid_input.setPlaceholderText("输入要结束的进程 PID")
        self._pid_input.setMaximumWidth(180)
        bar2.addWidget(self._pid_input)
        self._signal_combo = QComboBox()
        self._signal_combo.addItems(["SIGTERM (15, 优雅)", "SIGKILL (9, 强制)",
                                       "SIGHUP (1, 重读配置)"])
        bar2.addWidget(self._signal_combo)
        self._btn_kill_pid = QPushButton("💀 按 PID 结束")
        self._btn_kill_pid.setToolTip("向指定 PID 发送信号结束进程")
        self._btn_kill_pid.clicked.connect(self._kill_by_pid)
        bar2.addWidget(self._btn_kill_pid)
        self._btn_kill_sel = QPushButton("💀 结束选中")
        self._btn_kill_sel.setToolTip("结束表格中选中的进程")
        self._btn_kill_sel.clicked.connect(self._kill_selected)
        bar2.addWidget(self._btn_kill_sel)
        bar2.addStretch()
        layout.addLayout(bar2)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["PID", "用户", "CPU%", "内存%", "命令"])
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_menu)
        self._table.doubleClicked.connect(self._on_table_dbl)
        layout.addWidget(self._table, 1)

        self._status_label = QLabel("提示：右键表格行可结束进程；自动刷新时请勿频繁杀进程")
        self._status_label.setStyleSheet("color:#888; font-size:11px;")
        layout.addWidget(self._status_label)

        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._refresh)
        self._auto_timer.setInterval(5000)

    def _refresh_hosts(self):
        self._host_combo.clear()
        for h in self._asset.all_hosts():
            self._host_combo.addItem(f"{h.get('name','')} ({h.get('host','')})", h.get("name"))

    def _toggle_auto(self, on: bool):
        if on:
            self._auto_timer.start()
        else:
            self._auto_timer.stop()

    def _refresh(self):
        name = self._host_combo.currentData()
        host = self._asset.get_host(name) if name else None
        if not host:
            return
        if self._worker and self._worker.isRunning():
            return
        # 跨平台：Linux 用 ps，Windows 用 Get-Process
        is_windows = False
        if host.get("host", "").lower() in ("localhost", "127.0.0.1") and \
                os.name == "nt":
            is_windows = True
        if is_windows:
            cmd = (
                "powershell -NoProfile -Command "
                "\"Get-Process | Sort-Object CPU -Descending | "
                "Select-Object -First 100 Id,ProcessName,@{n='CPU';e={[math]::Round($_.CPU,1)}}, "
                "@{n='WS_MB';e={[math]::Round($_.WorkingSet/1MB,1)}},@{n='User';e='-'} | "
                "Format-Table -AutoSize | Out-String -Width 4096\""
            )
        else:
            cmd = (
                "ps -eo pid,user,pcpu,pmem,comm,args --sort=-pcpu | head -n 200"
            )
        self._badge.set_status("unknown", "采集中")
        self._worker = SSHCommandWorker(
            host=host["host"], port=host.get("port", 22),
            username=host.get("username", "root"),
            command=cmd,
            auth_type=host.get("auth_type", "password"),
            password=host.get("password", ""),
            key_path=host.get("key_path", ""),
            key_passphrase=host.get("key_passphrase", ""),
        )
        self._worker.result_ready.connect(self._on_result)
        self._worker.start()

    def _on_result(self, host: str, output: str, err: str):
        self._badge.set_status("ok" if output else "warn", "已刷新")
        rows = []
        for raw in output.splitlines():
            line = raw.strip()
            if not line:
                continue
            parts = line.split(None, 4)
            if len(parts) < 5:
                continue
            try:
                pid = int(parts[0])
            except ValueError:
                continue
            rows.append({
                "pid": pid,
                "user": parts[1],
                "cpu": float(parts[2]) if self._is_float(parts[2]) else 0.0,
                "mem": float(parts[3]) if self._is_float(parts[3]) else 0.0,
                "cmd": parts[4][:200],
            })
        self._all_rows = rows
        self._render()

    @staticmethod
    def _is_float(s: str) -> bool:
        try:
            float(s)
            return True
        except ValueError:
            return False

    def _render(self):
        rows = list(self._all_rows)
        kw = self._filter.text().strip().lower()
        if kw:
            rows = [r for r in rows if kw in r["cmd"].lower() or kw in r["user"].lower()]

        sort_idx = self._sort.currentIndex()
        if sort_idx == 0:
            rows.sort(key=lambda r: r["cpu"], reverse=True)
        elif sort_idx == 1:
            rows.sort(key=lambda r: r["mem"], reverse=True)
        else:
            rows.sort(key=lambda r: r["pid"])

        rows = rows[:self._top_n.value()]
        self._table.setRowCount(0)
        for r in rows:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(str(r["pid"])))
            self._table.setItem(row, 1, QTableWidgetItem(r["user"]))
            cpu_item = QTableWidgetItem(f"{r['cpu']:.1f}")
            if r["cpu"] >= 50:
                cpu_item.setForeground(QColor("#ff6b6b"))
            elif r["cpu"] >= 20:
                cpu_item.setForeground(QColor("#ffaa00"))
            self._table.setItem(row, 2, cpu_item)
            mem_item = QTableWidgetItem(f"{r['mem']:.1f}")
            if r["mem"] >= 30:
                mem_item.setForeground(QColor("#ff6b6b"))
            elif r["mem"] >= 10:
                mem_item.setForeground(QColor("#ffaa00"))
            self._table.setItem(row, 3, mem_item)
            self._table.setItem(row, 4, QTableWidgetItem(r["cmd"]))

    def stop(self):
        self._auto_timer.stop()
        if self._worker and self._worker.isRunning():
            self._worker.wait(1000)

    def _on_table_dbl(self, idx):
        """双击行：把 PID 填到输入框"""
        row = idx.row()
        if row < 0:
            return
        pid_item = self._table.item(row, 0)
        if pid_item:
            self._pid_input.setText(pid_item.text())

    def _on_table_menu(self, pos):
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        self._table.selectRow(row)
        menu = QMenu(self)
        act_pid = menu.addAction("📋 复制 PID")
        act_kill_term = menu.addAction("💀 结束 (SIGTERM)")
        act_kill_kill = menu.addAction("☠ 强制结束 (SIGKILL)")
        menu.addSeparator()
        act_refresh = menu.addAction("🔄 立即刷新")
        act = menu.exec(self._table.viewport().mapToGlobal(pos))
        if act == act_pid:
            QApplication.clipboard().setText(self._table.item(row, 0).text())
        elif act == act_kill_term:
            self._signal_combo.setCurrentIndex(0)
            self._kill_selected()
        elif act == act_kill_kill:
            self._signal_combo.setCurrentIndex(1)
            self._kill_selected()
        elif act == act_refresh:
            self._refresh()

    def _selected_pid(self) -> Optional[int]:
        row = self._table.currentRow()
        if row < 0:
            return None
        try:
            return int(self._table.item(row, 0).text())
        except (ValueError, AttributeError):
            return None

    def _selected_row_info(self) -> Optional[dict]:
        row = self._table.currentRow()
        if row < 0:
            return None
        return {
            "pid": self._table.item(row, 0).text(),
            "user": self._table.item(row, 1).text() if self._table.item(row, 1) else "",
            "cmd": self._table.item(row, 4).text() if self._table.item(row, 4) else "",
        }

    def _signal_code(self) -> int:
        idx = self._signal_combo.currentIndex()
        return [15, 9, 1][idx] if 0 <= idx < 3 else 15

    def _current_host(self) -> Optional[dict]:
        name = self._host_combo.currentData()
        if not name:
            return None
        return self._asset.get_host(name)

    def _is_windows_host(self, host: dict) -> bool:
        return (host.get("host", "").lower() in ("localhost", "127.0.0.1")
                and os.name == "nt")

    def _kill_by_pid(self):
        pid_text = self._pid_input.text().strip()
        if not pid_text:
            QMessageBox.information(self, "提示", "请先输入 PID")
            return
        try:
            pid = int(pid_text)
        except ValueError:
            QMessageBox.warning(self, "错误", "PID 必须是整数")
            return
        if pid <= 0:
            QMessageBox.warning(self, "错误", "PID 必须为正整数")
            return
        host = self._current_host()
        if not host:
            QMessageBox.warning(self, "提示", "请先选择主机")
            return
        if pid in (1, 0):
            if QMessageBox.warning(
                self, "危险操作",
                f"目标 PID={pid} 是关键系统进程，结束可能导致系统异常。\n确定继续吗？"
            ) != QMessageBox.Yes:
                return
        sig = self._signal_code()
        self._do_kill(host, pid, sig, extra_info=None)

    def _kill_selected(self):
        pid = self._selected_pid()
        if pid is None:
            QMessageBox.information(self, "提示", "请先在表格中选择一行")
            return
        info = self._selected_row_info() or {}
        cmd_preview = (info.get("cmd") or "")[:60]
        sig = self._signal_code()
        sig_name = {15: "SIGTERM", 9: "SIGKILL", 1: "SIGHUP"}.get(sig, str(sig))
        if QMessageBox.question(
            self, "确认结束进程",
            f"确定在 [{self._host_combo.currentText()}] 上结束以下进程吗？\n\n"
            f"PID:    {pid}\n"
            f"用户:   {info.get('user', '-')}\n"
            f"命令:   {cmd_preview}\n"
            f"信号:   {sig_name}\n",
        ) != QMessageBox.Yes:
            return
        host = self._current_host()
        if not host:
            return
        self._do_kill(host, pid, sig, extra_info=info)

    def _do_kill(self, host: dict, pid: int, sig: int, extra_info: Optional[dict]):
        if self._kill_worker and self._kill_worker.isRunning():
            QMessageBox.information(self, "提示", "上一次结束操作尚未完成，请稍候")
            return
        is_win = self._is_windows_host(host)
        if is_win:
            # Windows 下用 taskkill（忽略 sig）
            if sig == 9:
                cmd = f"taskkill /F /PID {pid}"
            else:
                cmd = f"taskkill /PID {pid}"
        else:
            # Linux/Unix 用 kill
            if sig in (15, 1):
                cmd = f"kill -s {sig} {pid} 2>&1; echo exit=$?"
            else:
                cmd = f"kill -{sig} {pid} 2>&1; echo exit=$?"
        self._status_label.setText(f"正在结束 PID={pid} ...")
        self._badge.set_status("unknown", "执行中")
        self._kill_worker = SSHCommandWorker(
            host=host["host"], port=host.get("port", 22),
            username=host.get("username", "root"),
            command=cmd,
            auth_type=host.get("auth_type", "password"),
            password=host.get("password", ""),
            key_path=host.get("key_path", ""),
            key_passphrase=host.get("key_passphrase", ""),
        )
        self._kill_worker.result_ready.connect(
            lambda h, o, e: self._on_kill_result(pid, sig, h, o, e, extra_info))
        self._kill_worker.start()

    def _on_kill_result(self, pid: int, sig: int, host: str, output: str,
                        err: str, extra_info: Optional[dict]):
        # 记录审计
        try:
            from app.audit_log import audit
            audit(
                "process.kill",
                target=host,
                details={"pid": pid, "signal": sig, "cmd": (extra_info or {}).get("cmd", "")},
                result="success" if (not err or "exit=0" in output) else "fail",
            )
        except Exception:
            pass
        # 反馈
        if err and "exit=0" not in output:
            self._status_label.setText(f"PID={pid} 结束失败: {err.strip()[:120]}")
            self._badge.set_status("fail", "失败")
            QMessageBox.critical(
                self, "结束失败",
                f"主机: {host}\nPID: {pid}\n信号: {sig}\n\n错误: {err[:300]}")
        else:
            tail = output.strip().splitlines()[-1] if output.strip() else "ok"
            self._status_label.setText(f"PID={pid} 已结束 ({tail})")
            self._badge.set_status("ok", "已结束")
            # 自动刷新一次
            QTimer.singleShot(800, self._refresh)


# ============================================================
# 子模块 5：服务可用性监控
# ============================================================

class ServiceMonitorWidget(QWidget):
    # Webhook 配置文件路径
    SERVICE_CONFIG_FILE = os.path.join(ASSETS_DIR, "service_monitor.json")

    def __init__(self, asset: AssetManagerWidget, parent=None):
        super().__init__(parent)
        self._asset = asset
        self._worker: Optional[ServiceHealthCheckWorker] = None
        self._targets: List[dict] = []
        self._last_cycle: Dict[str, dict] = {}
        self._uptime: Dict[str, int] = {}      # 连续成功次数
        self._downtime: Dict[str, int] = {}    # 连续失败次数
        self._total_checks: Dict[str, int] = {}
        self._total_fail: Dict[str, int] = {}
        # 告警状态：每个 key 上次是否已发送（避免重复）
        self._alerted: Dict[str, str] = {}     # key -> "down" / "recovered" / None
        # 告警历史（最近 100 条）
        self._alert_history: List[dict] = []
        # 告警设置
        self._fail_threshold = 2      # 连续失败 N 次才告警
        self._recover_threshold = 2   # 连续成功 N 次才发恢复
        self._webhook_url = ""
        self._webhook_method = "POST"
        self._webhook_headers = ""
        self._load_config()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("检查间隔:"))
        self._interval = QSpinBox()
        self._interval.setRange(5, 600)
        self._interval.setValue(30)
        self._interval.setSuffix(" 秒")
        bar.addWidget(self._interval)
        bar.addWidget(QLabel("超时:"))
        self._timeout = QSpinBox()
        self._timeout.setRange(1, 30)
        self._timeout.setValue(5)
        self._timeout.setSuffix(" 秒")
        bar.addWidget(self._timeout)
        self._btn_start = QPushButton("▶ 开始监控")
        self._btn_start.clicked.connect(self._start)
        bar.addWidget(self._btn_start)
        self._btn_stop = QPushButton("■ 停止")
        self._btn_stop.clicked.connect(self._stop)
        self._btn_stop.setEnabled(False)
        bar.addWidget(self._btn_stop)
        b_add = QPushButton("+ 添加目标")
        b_add.clicked.connect(self._add_target)
        bar.addWidget(b_add)
        b_del = QPushButton("删除选中")
        b_del.clicked.connect(self._del_target)
        bar.addWidget(b_del)
        b_alert = QPushButton("🔔 告警设置")
        b_alert.clicked.connect(self._open_alert_settings)
        bar.addWidget(b_alert)
        b_history = QPushButton("📜 告警历史")
        b_history.clicked.connect(self._show_alert_history)
        bar.addWidget(b_history)
        bar.addStretch()
        self._badge = StatusBadge()
        bar.addWidget(self._badge)
        layout.addLayout(bar)

        # 概览
        self._overview = QLabel("尚未开始监控")
        self._overview.setStyleSheet("color:#888; padding: 4px;")
        layout.addWidget(self._overview)

        # 目标表
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["名称", "类型", "目标", "状态", "延迟(ms)", "可用率"])
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.doubleClicked.connect(self._on_table_dbl)
        layout.addWidget(self._table, 1)

        # 默认示例目标
        self._targets = [
            {"name": "百度", "type": "http", "target": "https://www.baidu.com",
             "expect_status": 200, "method": "GET"},
            {"name": "本地网关", "type": "tcp", "target": "127.0.0.1:80"},
        ]
        self._render_table({})

    def _load_config(self):
        try:
            if os.path.exists(self.SERVICE_CONFIG_FILE):
                with open(self.SERVICE_CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self._fail_threshold = int(cfg.get("fail_threshold", 2))
                self._recover_threshold = int(cfg.get("recover_threshold", 2))
                self._webhook_url = cfg.get("webhook_url", "") or ""
                self._webhook_method = cfg.get("webhook_method", "POST") or "POST"
                self._webhook_headers = cfg.get("webhook_headers", "") or ""
        except Exception:
            pass

    def _save_config(self):
        try:
            os.makedirs(ASSETS_DIR, exist_ok=True)
            with open(self.SERVICE_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "fail_threshold": self._fail_threshold,
                    "recover_threshold": self._recover_threshold,
                    "webhook_url": self._webhook_url,
                    "webhook_method": self._webhook_method,
                    "webhook_headers": self._webhook_headers,
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存服务监控配置失败: {e}")

    def _open_alert_settings(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("服务监控告警设置")
        dlg.setMinimumWidth(480)
        f = QFormLayout(dlg)

        sp_fail = QSpinBox()
        sp_fail.setRange(1, 20)
        sp_fail.setValue(self._fail_threshold)
        sp_fail.setToolTip("连续失败多少次才触发告警")
        f.addRow("连续失败次数(告警阈值):", sp_fail)

        sp_rec = QSpinBox()
        sp_rec.setRange(1, 20)
        sp_rec.setValue(self._recover_threshold)
        sp_rec.setToolTip("连续成功多少次才发送恢复通知")
        f.addRow("连续成功次数(恢复阈值):", sp_rec)

        f.addRow(QLabel("—— Webhook 通知（可选）——"))
        edit_url = QLineEdit(self._webhook_url)
        edit_url.setPlaceholderText("https://oapi.dingtalk.com/robot/send?access_token=xxx")
        f.addRow("Webhook URL:", edit_url)

        cmb_method = QComboBox()
        cmb_method.addItems(["POST", "PUT", "GET"])
        cmb_method.setCurrentText(self._webhook_method)
        f.addRow("HTTP 方法:", cmb_method)

        edit_headers = QLineEdit(self._webhook_headers)
        edit_headers.setPlaceholderText("可选 JSON: {\"X-Token\": \"abc\"}")
        f.addRow("自定义 Header(JSON):", edit_headers)

        info = QLabel(
            "告警内容以 JSON 格式 POST：\n"
            "  {\n"
            "    \"event\": \"down\" | \"recovered\",\n"
            "    \"target\": \"目标名称\",\n"
            "    \"type\": \"http|tcp\",\n"
            "    \"url\": \"目标URL/host:port\",\n"
            "    \"error\": \"错误信息\",\n"
            "    \"timestamp\": \"2024-01-01 12:00:00\"\n"
            "  }"
        )
        info.setStyleSheet(
            "background:#2d2d2d; color:#bbb; padding:8px; "
            "border:1px solid #3c3c3c; border-radius:4px; font-family: Consolas; font-size: 11px;")
        f.addRow(info)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        f.addRow(bb)
        if dlg.exec() == QDialog.Accepted:
            self._fail_threshold = sp_fail.value()
            self._recover_threshold = sp_rec.value()
            self._webhook_url = edit_url.text().strip()
            self._webhook_method = cmb_method.currentText()
            self._webhook_headers = edit_headers.text().strip()
            self._save_config()
            QMessageBox.information(self, "已保存", "告警设置已保存")

    def _show_alert_history(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("告警历史")
        dlg.resize(720, 400)
        v = QVBoxLayout(dlg)
        info = QLabel(
            f"共 {len(self._alert_history)} 条  |  告警阈值: 连续失败 {self._fail_threshold} 次  |  "
            f"恢复阈值: 连续成功 {self._recover_threshold} 次"
        )
        info.setStyleSheet("color:#888;")
        v.addWidget(info)
        tb = QTableWidget(0, 5)
        tb.setHorizontalHeaderLabels(["时间", "事件", "目标", "类型", "详情"])
        tb.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        tb.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for ev in reversed(self._alert_history[-200:]):
            r = tb.rowCount()
            tb.insertRow(r)
            tb.setItem(r, 0, QTableWidgetItem(ev.get("ts_str", "")))
            ev_item = QTableWidgetItem(ev.get("event", ""))
            color = "#ff6b6b" if ev.get("event") == "down" else "#4ecdc4"
            ev_item.setForeground(QColor(color))
            tb.setItem(r, 1, ev_item)
            tb.setItem(r, 2, QTableWidgetItem(ev.get("target", "")))
            tb.setItem(r, 3, QTableWidgetItem(ev.get("type", "")))
            tb.setItem(r, 4, QTableWidgetItem(ev.get("details", "")))
        v.addWidget(tb, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        bb.accepted.connect(dlg.accept)
        v.addWidget(bb)
        dlg.exec()

    def _on_table_dbl(self, idx):
        """双击行：对该目标进行单次检查"""
        row = idx.row()
        if row < 0 or row >= len(self._targets):
            return
        # 简单反馈：当前已通过周期检查，可让用户查看详情
        k = self._key(self._targets[row])
        v = self._last_cycle.get(k, {})
        if not v:
            QMessageBox.information(self, "提示", "该目标尚无检查结果")
            return
        msg = f"目标: {self._targets[row].get('name')}\n"
        msg += f"类型: {self._targets[row].get('type')}\n"
        msg += f"地址: {self._targets[row].get('target')}\n"
        msg += f"状态: {'正常' if v.get('ok') else '异常'}\n"
        if v.get("status"):
            msg += f"HTTP 状态: {v.get('status')}\n"
        if v.get("latency_ms") is not None:
            msg += f"延迟: {v.get('latency_ms'):.1f} ms\n"
        if v.get("error"):
            msg += f"错误: {v.get('error')}\n"
        QMessageBox.information(self, "目标详情", msg)

    def _add_target(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("添加监控目标")
        dlg.setMinimumWidth(360)
        f = QFormLayout(dlg)
        name = QLineEdit()
        ttype = QComboBox()
        ttype.addItems(["http", "tcp"])
        target = QLineEdit()
        target.setPlaceholderText("http://...  或  host:port")
        method = QComboBox()
        method.addItems(["GET", "HEAD", "POST"])
        expect = QSpinBox()
        expect.setRange(0, 999)
        expect.setValue(200)
        f.addRow("名称:", name)
        f.addRow("类型:", ttype)
        f.addRow("目标:", target)
        f.addRow("方法:", method)
        f.addRow("期望状态码:", expect)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        f.addRow(bb)
        if dlg.exec() == QDialog.Accepted and target.text().strip():
            self._targets.append({
                "name": name.text().strip() or target.text().strip(),
                "type": ttype.currentText(),
                "target": target.text().strip(),
                "expect_status": expect.value(),
                "method": method.currentText(),
            })
            self._render_table({})

    def _del_target(self):
        row = self._table.currentRow()
        if row < 0 or row >= len(self._targets):
            return
        del self._targets[row]
        self._render_table({})

    def _start(self):
        if not self._targets:
            QMessageBox.warning(self, "提示", "请先添加监控目标")
            return
        if self._worker and self._worker.isRunning():
            return
        self._stop()
        self._total_checks = {self._key(t): 0 for t in self._targets}
        self._total_fail = {self._key(t): 0 for t in self._targets}
        self._uptime = {self._key(t): 0 for t in self._targets}
        self._downtime = {self._key(t): 0 for t in self._targets}
        self._alerted = {self._key(t): None for t in self._targets}
        self._worker = ServiceHealthCheckWorker(
            targets=self._targets,
            interval=float(self._interval.value()),
            timeout=float(self._timeout.value()),
        )
        self._worker.cycle_done.connect(self._on_cycle)
        self._badge.set_status("unknown", "监控中")
        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._worker.start()

    def _stop(self):
        if self._worker:
            try:
                self._worker.stop()
                self._worker.wait(2000)
            except Exception:
                pass
            self._worker = None
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._badge.set_status("unknown", "已停止")

    @staticmethod
    def _key(t: dict) -> str:
        return f"{t.get('name','')}|{t.get('type','tcp')}|{t.get('target','')}"

    def _on_cycle(self, cycle: dict):
        self._last_cycle = cycle
        # 找对应的 target 对象
        key_to_target = {self._key(t): t for t in self._targets}
        for k, v in cycle.items():
            self._total_checks[k] = self._total_checks.get(k, 0) + 1
            if not v.get("ok"):
                self._total_fail[k] = self._total_fail.get(k, 0) + 1
                self._downtime[k] = self._downtime.get(k, 0) + 1
                self._uptime[k] = 0
            else:
                self._uptime[k] = self._uptime.get(k, 0) + 1
                self._downtime[k] = 0
            # 检查是否触发告警
            self._maybe_alert(k, v, key_to_target.get(k, {}))
        self._render_table(cycle)
        # 概览
        total = len(self._targets)
        ok_cnt = sum(1 for t in self._targets
                     if self._last_cycle.get(self._key(t), {}).get("ok"))
        alerted = sum(1 for t in self._targets
                      if self._alerted.get(self._key(t)) == "down")
        self._overview.setText(
            f"目标数: {total}  |  当前正常: {ok_cnt}  |  异常: {total - ok_cnt}  |  "
            f"已告警: {alerted}  |  最近一次扫描: {time.strftime('%H:%M:%S')}"
        )

    def _maybe_alert(self, key: str, last_result: dict, target: dict):
        """根据连续失败/成功次数判断是否触发告警或恢复"""
        if not target:
            return
        prev_state = self._alerted.get(key)  # None / "down" / "recovered"
        fail_n = self._downtime.get(key, 0)
        ok_n = self._uptime.get(key, 0)
        ts_str = time.strftime("%Y-%m-%d %H:%M:%S")

        # 触发 DOWN 告警
        if last_result.get("ok") is False and fail_n >= self._fail_threshold \
                and prev_state != "down":
            self._alerted[key] = "down"
            payload = {
                "event": "down",
                "target": target.get("name", ""),
                "type": target.get("type", ""),
                "url": target.get("target", ""),
                "error": last_result.get("error", ""),
                "timestamp": ts_str,
                "consecutive_fails": fail_n,
            }
            self._emit_alert(target, payload)
            return

        # 触发 RECOVERED 通知
        if last_result.get("ok") is True and ok_n >= self._recover_threshold \
                and prev_state == "down":
            self._alerted[key] = "recovered"
            payload = {
                "event": "recovered",
                "target": target.get("name", ""),
                "type": target.get("type", ""),
                "url": target.get("target", ""),
                "timestamp": ts_str,
                "consecutive_oks": ok_n,
            }
            self._emit_alert(target, payload)
            return

        # 恢复后第一次成功：清除标记但不再发通知
        if last_result.get("ok") is True and prev_state == "recovered":
            self._alerted[key] = None

    def _emit_alert(self, target: dict, payload: dict):
        """发出告警：写审计 + 触发 Webhook + 系统通知 + 历史记录"""
        # 1) 写审计日志
        try:
            from app.audit_log import audit
            audit(
                f"service.alert.{payload.get('event')}",
                target=payload.get("url", ""),
                details=payload,
                result="success",
            )
        except Exception:
            pass

        # 2) 通知 alert_center
        try:
            from app.alert_center import emit_alert
            emit_alert(
                source="service_monitor",
                severity="critical" if payload.get("event") == "down" else "info",
                title=f"[服务] {payload.get('target')}: {payload.get('event')}",
                message=payload.get("error") or "服务已恢复",
                details=payload,
            )
        except Exception:
            pass

        # 3) Webhook
        if self._webhook_url:
            self._send_webhook_async(payload)

        # 4) 历史
        entry = {
            "ts_str": payload.get("timestamp", ""),
            "event": payload.get("event", ""),
            "target": payload.get("target", ""),
            "type": payload.get("type", ""),
            "details": (payload.get("error")
                        or f"连续成功 {payload.get('consecutive_oks', 0)} 次"),
        }
        self._alert_history.append(entry)
        if len(self._alert_history) > 200:
            self._alert_history = self._alert_history[-200:]

        # 5) 顶部徽章提示
        if payload.get("event") == "down":
            self._badge.set_status("fail", "有告警")
        else:
            self._badge.set_status("ok", "已恢复")

    def _send_webhook_async(self, payload: dict):
        """在后台线程中发送 Webhook 请求（避免阻塞 UI）"""
        from PySide6.QtCore import QThread
        url = self._webhook_url
        method = self._webhook_method or "POST"
        headers_str = self._webhook_headers or ""
        body = json.dumps(payload, ensure_ascii=False)

        class WebhookWorker(QThread):
            def run(_self):
                try:
                    import urllib.request
                    import urllib.error
                    req = urllib.request.Request(url, data=body.encode("utf-8"),
                                                 method=method)
                    req.add_header("Content-Type", "application/json; charset=utf-8")
                    # 解析自定义 header
                    if headers_str:
                        try:
                            hdrs = json.loads(headers_str)
                            for k, v in (hdrs or {}).items():
                                req.add_header(str(k), str(v))
                        except Exception:
                            pass
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        _ = resp.read()  # consume
                except Exception as e:
                    print(f"Webhook 发送失败: {e}")

        w = WebhookWorker(self)
        w.start()

    def _render_table(self, cycle: dict):
        self._table.setRowCount(0)
        for t in self._targets:
            k = self._key(t)
            v = cycle.get(k, {})
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(t.get("name", "")))
            self._table.setItem(row, 1, QTableWidgetItem(t.get("type", "").upper()))
            self._table.setItem(row, 2, QTableWidgetItem(t.get("target", "")))
            status_item = QTableWidgetItem("--")
            alerted = self._alerted.get(k)
            if v:
                if v.get("ok"):
                    text = f"正常 ({v.get('status')})"
                    if alerted == "recovered":
                        text += " ✅ 已恢复"
                        status_item.setForeground(QColor("#4ecdc4"))
                    else:
                        status_item.setForeground(QColor("#4ecdc4"))
                    status_item.setText(text)
                else:
                    err = v.get("error", "失败")
                    if len(err) > 30:
                        err = err[:30] + "..."
                    text = f"异常: {err}"
                    if alerted == "down":
                        text += " 🔔"
                        status_item.setForeground(QColor("#ff6b6b"))
                    else:
                        status_item.setForeground(QColor("#ffaa00"))
                    status_item.setText(text)
            self._table.setItem(row, 3, status_item)
            self._table.setItem(row, 4, QTableWidgetItem(
                f"{v.get('latency_ms', 0):.1f}" if v.get("latency_ms") is not None else "--"))
            total = self._total_checks.get(k, 0)
            fail = self._total_fail.get(k, 0)
            rate = ((total - fail) / total * 100) if total else 0
            rate_item = QTableWidgetItem(f"{rate:.1f}%")
            if rate >= 99:
                rate_item.setForeground(QColor("#4ecdc4"))
            elif rate >= 95:
                rate_item.setForeground(QColor("#ffaa00"))
            else:
                rate_item.setForeground(QColor("#ff6b6b"))
            self._table.setItem(row, 5, rate_item)

    def stop(self):
        self._stop()


# ============================================================
# 子模块 6：批量命令执行
# ============================================================

class BatchExecWidget(QWidget):
    # 模板和历史持久化路径
    TEMPLATES_FILE = os.path.join(ASSETS_DIR, "batch_templates.json")
    HISTORY_FILE = os.path.join(ASSETS_DIR, "batch_history.json")
    MAX_HISTORY = 50

    def __init__(self, asset: AssetManagerWidget, parent=None):
        super().__init__(parent)
        self._asset = asset
        self._worker: Optional[BatchSSHCommandWorker] = None
        self._results: Dict[str, tuple] = {}  # host -> (output, error, status)
        self._host_status: Dict[str, dict] = {}  # host -> auth data
        self._templates: List[dict] = self._load_templates()  # [{"name":..., "cmd":...}]
        self._history: List[dict] = self._load_history()      # [{"ts":..., "cmd":..., "success":int, "total":int}]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # 主机选择区
        split = QSplitter(Qt.Horizontal)

        # 左：主机清单
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        lbar = QHBoxLayout()
        lbar.addWidget(QLabel("主机 (可多选)"))
        b_all = QPushButton("全选")
        b_all.clicked.connect(lambda: self._select_all(True))
        b_none = QPushButton("全不选")
        b_none.clicked.connect(lambda: self._select_all(False))
        lbar.addStretch()
        lbar.addWidget(b_all)
        lbar.addWidget(b_none)
        ll.addLayout(lbar)
        self._host_list = QListWidget()
        self._host_list.setSelectionMode(QAbstractItemView.MultiSelection)
        ll.addWidget(self._host_list, 1)
        grp_bar = QHBoxLayout()
        grp_bar.addWidget(QLabel("按分组筛选:"))
        self._grp_filter = QComboBox()
        self._grp_filter.currentTextChanged.connect(self._refresh_host_list)
        grp_bar.addWidget(self._grp_filter)
        ll.addLayout(grp_bar)

        # 右：命令与结果
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)

        cmd_bar = QHBoxLayout()
        cmd_bar.addWidget(QLabel("命令:"))
        b_save_tpl = QPushButton("💾 存为模板")
        b_save_tpl.setToolTip("将当前命令保存为模板，下次一键使用")
        b_save_tpl.clicked.connect(self._save_as_template)
        cmd_bar.addWidget(b_save_tpl)
        b_manage_tpl = QPushButton("📑 模板管理")
        b_manage_tpl.setToolTip("管理已保存的命令模板")
        b_manage_tpl.clicked.connect(self._manage_templates)
        cmd_bar.addWidget(b_manage_tpl)
        b_history = QPushButton("🕘 历史")
        b_history.setToolTip("查看/重用最近执行过的命令")
        b_history.clicked.connect(self._show_history)
        cmd_bar.addWidget(b_history)
        rl.addLayout(cmd_bar)
        self._cmd = QPlainTextEdit()
        self._cmd.setMaximumHeight(110)
        self._cmd.setPlaceholderText("例如:\n  uptime\n  df -h\n  systemctl status nginx\n  free -m")
        rl.addWidget(self._cmd)

        # 预设命令（带模板下拉）
        preset_bar = QHBoxLayout()
        preset_bar.addWidget(QLabel("预设:"))
        for name, cmd in [
            ("uptime", "uptime"),
            ("磁盘 df -h", "df -h"),
            ("内存 free -m", "free -m"),
            ("CPU 核数", "nproc"),
            ("内核版本", "uname -a"),
            ("系统时间", "date"),
            ("最近登录", "last -n 10"),
            ("Top10 进程", "ps -eo pid,user,pcpu,pmem,comm --sort=-pcpu | head -n 11"),
            ("网络连接", "ss -tunap | head -n 30"),
            ("重启历史", "last reboot | head -n 10"),
        ]:
            b = QPushButton(name)
            b.clicked.connect(lambda checked=False, c=cmd: self._cmd.setPlainText(c))
            preset_bar.addWidget(b)
        # 模板下拉
        preset_bar.addWidget(QLabel("  |  模板:"))
        self._tpl_combo = QComboBox()
        self._tpl_combo.setMinimumWidth(180)
        self._refresh_tpl_combo()
        preset_bar.addWidget(self._tpl_combo, 1)
        b_use_tpl = QPushButton("使用")
        b_use_tpl.clicked.connect(self._use_template)
        preset_bar.addWidget(b_use_tpl)
        b_del_tpl = QPushButton("删除")
        b_del_tpl.clicked.connect(self._delete_template)
        preset_bar.addWidget(b_del_tpl)
        rl.addLayout(preset_bar)

        opt_bar = QHBoxLayout()
        opt_bar.addWidget(QLabel("并发:"))
        self._concurrency = QSpinBox()
        self._concurrency.setRange(1, 20)
        self._concurrency.setValue(5)
        opt_bar.addWidget(self._concurrency)
        opt_bar.addWidget(QLabel("超时:"))
        self._timeout = QSpinBox()
        self._timeout.setRange(5, 120)
        self._timeout.setValue(20)
        self._timeout.setSuffix(" 秒")
        opt_bar.addWidget(self._timeout)
        self._btn_run = QPushButton("▶ 执行")
        self._btn_run.clicked.connect(self._run)
        opt_bar.addWidget(self._btn_run)
        self._btn_stop = QPushButton("■ 中止")
        self._btn_stop.clicked.connect(self._stop)
        self._btn_stop.setEnabled(False)
        opt_bar.addWidget(self._btn_stop)
        opt_bar.addStretch()
        self._badge = StatusBadge()
        opt_bar.addWidget(self._badge)
        self._progress = QLabel("")
        self._progress.setStyleSheet("color:#888;")
        opt_bar.addWidget(self._progress)
        rl.addLayout(opt_bar)

        # 结果区
        result_split = QSplitter(Qt.Horizontal)
        self._result_list = QListWidget()
        self._result_list.currentRowChanged.connect(self._on_result_select)
        self._result_view = QPlainTextEdit()
        self._result_view.setReadOnly(True)
        self._result_view.setStyleSheet(
            "QPlainTextEdit{background:#1e1e1e;color:#ccc;font-family:Consolas,monospace;}")
        result_split.addWidget(self._result_list)
        result_split.addWidget(self._result_view)
        result_split.setSizes([220, 600])
        rl.addWidget(result_split, 1)

        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([280, 720])
        layout.addWidget(split, 1)

        self._refresh_host_list()

    # ---- 模板持久化 ----
    def _load_templates(self) -> List[dict]:
        try:
            if os.path.exists(self.TEMPLATES_FILE):
                with open(self.TEMPLATES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return [t for t in data if t.get("name") and t.get("cmd")]
        except Exception:
            pass
        return []

    def _save_templates_file(self):
        try:
            os.makedirs(ASSETS_DIR, exist_ok=True)
            with open(self.TEMPLATES_FILE, "w", encoding="utf-8") as f:
                json.dump(self._templates, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存模板失败: {e}")

    def _load_history(self) -> List[dict]:
        try:
            if os.path.exists(self.HISTORY_FILE):
                with open(self.HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
        return []

    def _save_history_file(self):
        try:
            os.makedirs(ASSETS_DIR, exist_ok=True)
            with open(self.HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self._history[-self.MAX_HISTORY:], f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存历史失败: {e}")

    def _refresh_tpl_combo(self):
        self._tpl_combo.clear()
        self._tpl_combo.addItem("— 选择模板 —", None)
        for t in self._templates:
            self._tpl_combo.addItem(t.get("name", ""), t.get("name"))

    def _save_as_template(self):
        cmd = self._cmd.toPlainText().strip()
        if not cmd:
            QMessageBox.information(self, "提示", "请先输入要保存的命令")
            return
        name, ok = QInputDialog.getText(
            self, "保存为模板", "模板名称:",
            text=cmd.splitlines()[0][:30] if cmd else "")
        if not ok or not name.strip():
            return
        name = name.strip()
        # 去重：同名则覆盖
        self._templates = [t for t in self._templates if t.get("name") != name]
        self._templates.append({
            "name": name,
            "cmd": cmd,
            "created_at": int(time.time()),
        })
        self._save_templates_file()
        self._refresh_tpl_combo()
        # 自动选中新模板
        for i in range(self._tpl_combo.count()):
            if self._tpl_combo.itemData(i) == name:
                self._tpl_combo.setCurrentIndex(i)
                break
        self._status_toast(f"已保存模板: {name}")

    def _use_template(self):
        name = self._tpl_combo.currentData()
        if not name:
            QMessageBox.information(self, "提示", "请先选择一个模板")
            return
        for t in self._templates:
            if t.get("name") == name:
                self._cmd.setPlainText(t.get("cmd", ""))
                self._status_toast(f"已加载模板: {name}")
                return

    def _delete_template(self):
        name = self._tpl_combo.currentData()
        if not name:
            QMessageBox.information(self, "提示", "请先选择一个模板")
            return
        if QMessageBox.question(
            self, "删除模板", f"确定删除模板 [{name}]？"
        ) == QMessageBox.Yes:
            self._templates = [t for t in self._templates if t.get("name") != name]
            self._save_templates_file()
            self._refresh_tpl_combo()
            self._status_toast(f"已删除模板: {name}")

    def _manage_templates(self):
        """模板管理对话框：列表 + 编辑/删除 + 导入/导出"""
        dlg = QDialog(self)
        dlg.setWindowTitle("命令模板管理")
        dlg.resize(640, 480)
        v = QVBoxLayout(dlg)

        info = QLabel(f"已保存 {len(self._templates)} 个模板  |  存储位置: {self.TEMPLATES_FILE}")
        info.setStyleSheet("color:#888;")
        v.addWidget(info)

        tb = QTableWidget(0, 3)
        tb.setHorizontalHeaderLabels(["名称", "命令", "创建时间"])
        tb.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        tb.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tb.setSelectionBehavior(QAbstractItemView.SelectRows)
        for t in self._templates:
            r = tb.rowCount()
            tb.insertRow(r)
            tb.setItem(r, 0, QTableWidgetItem(t.get("name", "")))
            tb.setItem(r, 1, QTableWidgetItem(t.get("cmd", "")[:200]))
            tb.setItem(r, 2, QTableWidgetItem(time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(t.get("created_at", 0)))))
        tb.doubleClicked.connect(lambda idx: self._edit_template_in_dialog(tb, idx, dlg))
        v.addWidget(tb, 1)

        bar = QHBoxLayout()
        b_edit = QPushButton("✏ 编辑")
        b_edit.clicked.connect(lambda: self._edit_template_in_dialog(
            tb, None, dlg))
        b_del = QPushButton("🗑 删除")
        b_del.clicked.connect(lambda: self._del_template_in_dialog(tb))
        b_imp = QPushButton("📥 导入")
        b_imp.clicked.connect(lambda: self._import_templates(tb))
        b_exp = QPushButton("📤 导出")
        b_exp.clicked.connect(lambda: self._export_templates())
        bar.addWidget(b_edit)
        bar.addWidget(b_del)
        bar.addStretch()
        bar.addWidget(b_imp)
        bar.addWidget(b_exp)
        v.addLayout(bar)

        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        bb.accepted.connect(dlg.accept)
        v.addWidget(bb)
        dlg.exec()
        self._refresh_tpl_combo()

    def _edit_template_in_dialog(self, tb, idx, parent_dlg):
        if idx is not None:
            row = idx.row()
        else:
            row = tb.currentRow()
        if row < 0:
            QMessageBox.information(parent_dlg, "提示", "请先选择一行")
            return
        old_name = tb.item(row, 0).text()
        target = next((t for t in self._templates if t.get("name") == old_name), None)
        if not target:
            return
        edit_dlg = QDialog(parent_dlg)
        edit_dlg.setWindowTitle(f"编辑模板 - {old_name}")
        edit_dlg.resize(560, 280)
        f = QVBoxLayout(edit_dlg)
        form = QFormLayout()
        name_edit = QLineEdit(target.get("name", ""))
        form.addRow("名称:", name_edit)
        f.addLayout(form)
        cmd_edit = QPlainTextEdit(target.get("cmd", ""))
        cmd_edit.setStyleSheet("font-family:Consolas,monospace;")
        f.addWidget(QLabel("命令:"))
        f.addWidget(cmd_edit, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(edit_dlg.accept)
        bb.rejected.connect(edit_dlg.reject)
        f.addWidget(bb)
        if edit_dlg.exec() == QDialog.Accepted:
            new_name = name_edit.text().strip() or old_name
            # 改名：检查冲突
            if new_name != old_name and any(t.get("name") == new_name for t in self._templates):
                QMessageBox.warning(edit_dlg, "冲突", f"已存在同名模板: {new_name}")
                return
            # 移除旧条目
            self._templates = [t for t in self._templates if t.get("name") != old_name]
            self._templates.append({
                "name": new_name,
                "cmd": cmd_edit.toPlainText(),
                "created_at": target.get("created_at", int(time.time())),
            })
            self._save_templates_file()
            # 刷新表格
            tb.setItem(row, 0, QTableWidgetItem(new_name))
            tb.setItem(row, 1, QTableWidgetItem(cmd_edit.toPlainText()[:200]))
            QMessageBox.information(edit_dlg, "成功", "已更新")

    def _del_template_in_dialog(self, tb):
        row = tb.currentRow()
        if row < 0:
            return
        name = tb.item(row, 0).text()
        if QMessageBox.question(
            tb.parent(), "删除", f"确定删除模板 [{name}]？"
        ) == QMessageBox.Yes:
            self._templates = [t for t in self._templates if t.get("name") != name]
            self._save_templates_file()
            tb.removeRow(row)

    def _import_templates(self, tb):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入模板", os.path.expanduser("~"),
            "JSON 文件 (*.json);;所有文件 (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("JSON 根节点必须是数组")
            added = 0
            for t in data:
                if not isinstance(t, dict) or not t.get("name") or not t.get("cmd"):
                    continue
                # 去重：同名覆盖
                self._templates = [x for x in self._templates
                                   if x.get("name") != t["name"]]
                self._templates.append({
                    "name": t["name"],
                    "cmd": t["cmd"],
                    "created_at": int(t.get("created_at") or time.time()),
                })
                added += 1
            self._save_templates_file()
            # 刷新表格
            tb.setRowCount(0)
            for t in self._templates:
                r = tb.rowCount()
                tb.insertRow(r)
                tb.setItem(r, 0, QTableWidgetItem(t.get("name", "")))
                tb.setItem(r, 1, QTableWidgetItem(t.get("cmd", "")[:200]))
                tb.setItem(r, 2, QTableWidgetItem(time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(t.get("created_at", 0)))))
            QMessageBox.information(self, "完成", f"已导入 {added} 个模板")
        except Exception as e:
            QMessageBox.critical(self, "失败", str(e))

    def _export_templates(self):
        if not self._templates:
            QMessageBox.information(self, "提示", "没有模板可导出")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出模板",
            os.path.join(os.path.expanduser("~"), "batch_templates_export.json"),
            "JSON 文件 (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._templates, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "成功",
                                    f"已导出 {len(self._templates)} 个模板到:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "失败", str(e))

    def _show_history(self):
        """显示命令历史"""
        dlg = QDialog(self)
        dlg.setWindowTitle("命令执行历史")
        dlg.resize(720, 480)
        v = QVBoxLayout(dlg)
        info = QLabel(
            f"最近 {len(self._history)} 条  |  存储位置: {self.HISTORY_FILE}  |  "
            "双击一行可重新填充到命令框")
        info.setStyleSheet("color:#888;")
        v.addWidget(info)
        tb = QTableWidget(0, 5)
        tb.setHorizontalHeaderLabels(["时间", "命令", "主机数", "成功", "状态"])
        tb.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        tb.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tb.setSelectionBehavior(QAbstractItemView.SelectRows)
        for h in reversed(self._history):
            r = tb.rowCount()
            tb.insertRow(r)
            ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(h.get("ts", 0)))
            tb.setItem(r, 0, QTableWidgetItem(ts_str))
            tb.setItem(r, 1, QTableWidgetItem((h.get("cmd") or "")[:200]))
            tb.setItem(r, 2, QTableWidgetItem(str(h.get("total", 0))))
            tb.setItem(r, 3, QTableWidgetItem(str(h.get("success", 0))))
            status_item = QTableWidgetItem(h.get("status", ""))
            color = {"ok": "#4ecdc4", "warn": "#ffaa00", "fail": "#ff6b6b"}.get(
                h.get("status", ""), "#888")
            status_item.setForeground(QColor(color))
            tb.setItem(r, 4, status_item)
        v.addWidget(tb, 1)
        tb.doubleClicked.connect(lambda idx: self._reuse_history(tb, idx, dlg))

        bar = QHBoxLayout()
        b_reuse = QPushButton("🔁 填入命令框")
        b_reuse.clicked.connect(lambda: self._reuse_history(tb, None, dlg))
        b_clear = QPushButton("🗑 清空历史")
        b_clear.clicked.connect(lambda: self._clear_history(tb, dlg))
        bar.addWidget(b_reuse)
        bar.addWidget(b_clear)
        bar.addStretch()
        v.addLayout(bar)

        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        bb.accepted.connect(dlg.accept)
        v.addWidget(bb)
        dlg.exec()

    def _reuse_history(self, tb, idx, parent_dlg):
        if idx is not None:
            row = idx.row()
        else:
            row = tb.currentRow()
        if row < 0:
            QMessageBox.information(parent_dlg, "提示", "请先选择一行")
            return
        # 反向索引：表格是倒序显示的
        real_idx = len(self._history) - 1 - row
        if 0 <= real_idx < len(self._history):
            cmd = self._history[real_idx].get("cmd", "")
            self._cmd.setPlainText(cmd)
            parent_dlg.accept()
            self._status_toast("已从历史填充命令")

    def _clear_history(self, tb, parent_dlg):
        if QMessageBox.question(
            parent_dlg, "清空历史", "确定清空所有执行历史？"
        ) == QMessageBox.Yes:
            self._history.clear()
            self._save_history_file()
            tb.setRowCount(0)

    def _record_history(self, cmd: str, total: int, success: int, status: str):
        entry = {
            "ts": time.time(),
            "cmd": cmd,
            "total": total,
            "success": success,
            "status": status,
        }
        self._history.append(entry)
        if len(self._history) > self.MAX_HISTORY:
            self._history = self._history[-self.MAX_HISTORY:]
        self._save_history_file()

    def _status_toast(self, msg: str):
        """简单状态提示（写入进度标签）"""
        try:
            self._progress.setText(msg)
            QTimer.singleShot(2500, lambda: self._progress.setText(""))
        except Exception:
            pass

    def _refresh_host_list(self):
        self._host_list.clear()
        groups = sorted({h.get("group", "默认分组") for h in self._asset.all_hosts()})
        self._grp_filter.blockSignals(True)
        self._grp_filter.clear()
        self._grp_filter.addItem("全部分组")
        self._grp_filter.addItems(groups)
        self._grp_filter.blockSignals(False)

        cur_grp = self._grp_filter.currentText()
        self._host_status.clear()
        for h in self._asset.all_hosts():
            if cur_grp != "全部分组" and h.get("group") != cur_grp:
                continue
            item = QListWidgetItem(f"{h.get('name','')}  -  {h.get('host','')}")
            item.setData(Qt.UserRole, h.get("name"))
            self._host_list.addItem(item)
            self._host_status[h.get("name")] = h

    def _select_all(self, sel: bool):
        for i in range(self._host_list.count()):
            item = self._host_list.item(i)
            item.setSelected(sel)

    def _run(self):
        if self._worker and self._worker.isRunning():
            return
        cmd = self._cmd.toPlainText().strip()
        if not cmd:
            QMessageBox.warning(self, "提示", "请输入要执行的命令")
            return
        sel_names = [it.data(Qt.UserRole) for it in self._host_list.selectedItems()]
        if not sel_names:
            QMessageBox.warning(self, "提示", "请先在左侧选择目标主机")
            return
        hosts = [self._host_status[n] for n in sel_names if n in self._host_status]
        if not hosts:
            return
        self._result_list.clear()
        self._result_view.clear()
        self._results.clear()
        for h in hosts:
            item = QListWidgetItem(f"⏳ {h.get('name')} ({h.get('host')})")
            item.setData(Qt.UserRole, h.get("name"))
            self._result_list.addItem(item)
        self._badge.set_status("unknown", "执行中")
        self._progress.setText(f"0/{len(hosts)}")
        self._btn_run.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._worker = BatchSSHCommandWorker(
            hosts=hosts, command=cmd,
            concurrency=self._concurrency.value(),
            timeout=self._timeout.value(),
        )
        # 记下当前命令用于历史
        self._last_cmd = cmd
        self._last_total = len(hosts)
        self._worker.result_ready.connect(self._on_result)
        self._worker.progress.connect(lambda c, t: self._progress.setText(f"{c}/{t}"))
        self._worker.finished_all.connect(self._on_finished)
        self._worker.start()
        # 审计：发起批量执行
        try:
            from app.audit_log import audit
            audit("batch.execute",
                  target=f"{len(hosts)} 主机",
                  details={"cmd": cmd[:200], "concurrency": self._concurrency.value()})
        except Exception:
            pass

    def _stop(self):
        if self._worker:
            self._worker.stop()
            self._worker.wait(2000)
            self._worker = None
        self._btn_run.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._badge.set_status("unknown", "已中止")

    def _on_result(self, host: str, output: str, err: str, status: str):
        self._results[host] = (output, err, status)
        for i in range(self._result_list.count()):
            item = self._result_list.item(i)
            name = item.data(Qt.UserRole)
            h = self._host_status.get(name, {})
            if h.get("host") == host or name == host:
                color = {"ok": "#4ecdc4", "warn": "#ffaa00", "fail": "#ff6b6b"}.get(status, "#888")
                icon = {"ok": "✓", "warn": "!", "fail": "✗"}.get(status, "?")
                item.setText(f"{icon} {name}  [{status.upper()}]")
                item.setForeground(QColor(color))
                if self._result_list.currentItem() is None:
                    self._result_list.setCurrentItem(item)
                break

    def _on_result_select(self, idx: int):
        if idx < 0:
            return
        item = self._result_list.item(idx)
        name = item.data(Qt.UserRole)
        h = self._host_status.get(name, {})
        host = h.get("host", name)
        out, err, status = self._results.get(host, ("", "", "pending"))
        body = ""
        if out:
            body += f"--- stdout ---\n{out}\n"
        if err:
            body += f"--- stderr ---\n{err}\n"
        if not body:
            body = "(等待结果...)"
        self._result_view.setPlainText(f"主机: {name} ({host})\n状态: {status}\n\n{body}")

    def _on_finished(self, success: int, total: int):
        self._btn_run.setEnabled(True)
        self._btn_stop.setEnabled(False)
        status = "ok" if success == total else ("fail" if success == 0 else "warn")
        self._badge.set_status(status, f"完成 {success}/{total}")
        self._progress.setText(f"完成: {success}/{total}")
        # 记录历史
        cmd = getattr(self, "_last_cmd", "")
        if cmd:
            self._record_history(cmd, total, success, status)

    def stop(self):
        self._stop()


# ============================================================
# 顶级面板
# ============================================================

class EnterpriseOpsWidget(QWidget):
    """企业级运维控制台（容器）"""

    def __init__(self, asset_manager: AssetManagerWidget, parent=None):
        super().__init__(parent)
        self._asset = asset_manager

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("🛠  企业级运维控制台")
        title.setStyleSheet(
            "color:#4ecdc4; font-size:14px; font-weight:bold; padding: 6px 10px; "
            "background:#252526; border-bottom: 1px solid #3c3c3c;")
        layout.addWidget(title)

        self._tabs = QTabWidget()
        self._tabs.setTabPosition(QTabWidget.North)
        self._tabs.setDocumentMode(True)

        # 核心子模块
        self._monitor = MonitorWidget(self._asset)
        self._log = LogAnalyzerWidget(self._asset)
        self._process = ProcessManagerWidget(self._asset)
        self._service = ServiceMonitorWidget(self._asset)
        self._batch = BatchExecWidget(self._asset)

        # 扩展模块（延迟导入，避免循环依赖与启动慢）
        self._audit_log = None
        self._alert_center = None
        self._file_dist = None
        self._sched_tasks = None
        try:
            from app.audit_log import AuditLogWidget
            self._audit_log = AuditLogWidget()
        except Exception as e:
            print(f"[WARN] 审计日志模块加载失败: {e}")
        try:
            from app.alert_center import AlertCenterWidget
            self._alert_center = AlertCenterWidget()
        except Exception as e:
            print(f"[WARN] 告警中心模块加载失败: {e}")
        try:
            from app.file_distribution import FileDistributionWidget
            self._file_dist = FileDistributionWidget(self._asset)
        except Exception as e:
            print(f"[WARN] 文件分发模块加载失败: {e}")
        try:
            from app.scheduled_tasks import ScheduledTasksWidget
            self._sched_tasks = ScheduledTasksWidget(self._asset)
        except Exception as e:
            print(f"[WARN] 定时任务模块加载失败: {e}")

        self._tabs.addTab(self._monitor, "📊 实时监控")
        self._tabs.addTab(self._log, "📜 日志分析")
        self._tabs.addTab(self._process, "⚙ 进程管理")
        self._tabs.addTab(self._service, "💓 服务可用性")
        self._tabs.addTab(self._batch, "🚀 批量执行")
        if self._file_dist is not None:
            self._tabs.addTab(self._file_dist, "📤 文件分发")
        if self._sched_tasks is not None:
            self._tabs.addTab(self._sched_tasks, "⏰ 定时任务")
        if self._alert_center is not None:
            self._tabs.addTab(self._alert_center, "🔔 告警中心")
        if self._audit_log is not None:
            self._tabs.addTab(self._audit_log, "📝 审计日志")

        # 在第一个 tab 前插入资产管理
        self._tabs.insertTab(0, self._asset, "🗂 资产管理")
        self._tabs.setCurrentIndex(0)

        layout.addWidget(self._tabs, 1)

    def stop_all(self):
        """关闭时停掉所有后台任务"""
        try:
            self._monitor.stop()
            self._log.stop()
            self._process.stop()
            self._service.stop()
            self._batch.stop()
        except Exception:
            pass
        try:
            if self._alert_center and hasattr(self._alert_center, "stop"):
                self._alert_center.stop()
        except Exception:
            pass
        try:
            if self._sched_tasks and hasattr(self._sched_tasks, "stop"):
                self._sched_tasks.stop()
        except Exception:
            pass
        try:
            if self._file_dist and hasattr(self._file_dist, "stop"):
                self._file_dist.stop()
        except Exception:
            pass

    @property
    def asset_manager(self) -> AssetManagerWidget:
        return self._asset

    @property
    def audit_log_widget(self):
        return self._audit_log

    @property
    def alert_center_widget(self):
        return self._alert_center

    @property
    def file_distribution_widget(self):
        return self._file_dist

    @property
    def scheduled_tasks_widget(self):
        return self._sched_tasks


def open_enterprise_ops(parent=None) -> EnterpriseOpsWidget:
    """工厂方法：在主窗口中使用"""
    asset = AssetManagerWidget()
    return EnterpriseOpsWidget(asset, parent=parent)
