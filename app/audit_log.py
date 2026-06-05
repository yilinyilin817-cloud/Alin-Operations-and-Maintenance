"""
审计日志模块
统一记录运维控制台中的所有操作（增删改查、命令执行、文件分发等）
支持过滤、搜索、导出

持久化：~/.aiinlink/audit_log.json（按行 JSON-Lines，最多保留 10000 条）
"""

import json
import os
import time
from typing import List, Optional, Dict

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFileDialog, QMessageBox, QFrame, QSizePolicy, QDateTimeEdit, QCheckBox,
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


AUDIT_DIR = os.path.join(os.path.expanduser("~"), ".aiinlink")
AUDIT_FILE = os.path.join(AUDIT_DIR, "audit_log.json")
MAX_AUDIT_ENTRIES = 10000


# ============================================================
# 全局审计日志记录器（单例）
# ============================================================

class AuditLogger:
    """全局审计日志记录器 - 其他模块可调用 audit() 方法记录操作"""

    _instance: Optional["AuditLogger"] = None
    new_entry = Signal(dict) if False else None  # 占位

    def __init__(self):
        self._entries: List[dict] = []
        self._ensure_dir()
        self._load()

    @classmethod
    def instance(cls) -> "AuditLogger":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _ensure_dir(self):
        try:
            os.makedirs(AUDIT_DIR, exist_ok=True)
        except Exception:
            pass

    def _load(self):
        if not os.path.exists(AUDIT_FILE):
            return
        try:
            with open(AUDIT_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        self._entries.append(json.loads(line))
                    except Exception:
                        continue
        except Exception:
            pass

    def _save(self):
        try:
            # 原子写入
            tmp = AUDIT_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                for e in self._entries:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")
            os.replace(tmp, AUDIT_FILE)
        except Exception as e:
            print(f"保存审计日志失败: {e}")

    def log(self, action: str, target: str = "", result: str = "success",
            user: str = "admin", details: Optional[dict] = None) -> dict:
        """记录一条审计日志

        Args:
            action: 操作类型（如 "添加主机", "执行命令", "上传文件"）
            target: 操作目标（主机名/路径/规则名等）
            result: 结果 - "success" / "fail" / "warn"
            user: 操作用户（当前为固定 admin）
            details: 详细参数（dict，会被转为 JSON 存储）
        """
        entry = {
            "id": int(time.time() * 1000) + len(self._entries),
            "ts": time.time(),
            "ts_str": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "action": action,
            "target": target,
            "result": result,
            "user": user,
            "details": details or {},
        }
        self._entries.append(entry)
        # 限制最大条数
        if len(self._entries) > MAX_AUDIT_ENTRIES:
            self._entries = self._entries[-MAX_AUDIT_ENTRIES:]
        self._save()
        # 通知监听者
        if AuditLogger._listeners:
            for cb in list(AuditLogger._listeners):
                try:
                    cb(entry)
                except Exception:
                    pass
        return entry

    def get_entries(self, limit: int = 1000,
                    action_filter: str = "",
                    target_filter: str = "",
                    result_filter: str = "") -> List[dict]:
        """获取日志（支持过滤）"""
        out = self._entries
        if action_filter and action_filter != "全部":
            out = [e for e in out if e.get("action") == action_filter]
        if target_filter and target_filter != "全部":
            out = [e for e in out if e.get("target") == target_filter]
        if result_filter and result_filter != "全部":
            out = [e for e in out if e.get("result") == result_filter]
        return out[-limit:][::-1]  # 倒序：最新的在前

    def get_all_actions(self) -> List[str]:
        return sorted({e.get("action", "") for e in self._entries if e.get("action")})

    def get_all_targets(self) -> List[str]:
        return sorted({e.get("target", "") for e in self._entries if e.get("target")}, key=str)[:200]

    def get_stats(self) -> dict:
        """统计信息"""
        total = len(self._entries)
        success = sum(1 for e in self._entries if e.get("result") == "success")
        fail = sum(1 for e in self._entries if e.get("result") == "fail")
        warn = sum(1 for e in self._entries if e.get("result") == "warn")
        last_24h = sum(1 for e in self._entries if time.time() - e.get("ts", 0) < 86400)
        return {
            "total": total,
            "success": success,
            "fail": fail,
            "warn": warn,
            "last_24h": last_24h,
        }

    def clear(self):
        self._entries.clear()
        self._save()


# 全局监听器（简化版，替代 Qt signal）
AuditLogger._listeners: List[callable] = []


def register_audit_listener(callback):
    """注册审计日志监听器（用于 UI 实时刷新）"""
    if callback not in AuditLogger._listeners:
        AuditLogger._listeners.append(callback)


def unregister_audit_listener(callback):
    if callback in AuditLogger._listeners:
        AuditLogger._listeners.remove(callback)


# ============================================================
# 审计日志查看器 UI
# ============================================================

class AuditLogWidget(QWidget):
    """审计日志查看器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._logger = AuditLogger.instance()
        self._auto_refresh = True
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._on_auto_refresh)
        self._refresh_timer.start(5000)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 顶部统计
        self._stats_label = QLabel()
        self._stats_label.setProperty("role", "card")
        self._stats_label.setStyleSheet(
            f"color: {FG_PRIMARY}; font-size: 12px; padding: 8px 12px; "
            f"background-color: {BG_PANEL}; border: 1px solid {BORDER}; "
            f"border-radius: {RADIUS_MD}px;")
        layout.addWidget(self._stats_label)

        # 过滤栏
        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(QLabel("操作:"))
        self._action_filter = QComboBox()
        self._action_filter.setMinimumWidth(140)
        self._action_filter.addItem("全部")
        self._action_filter.currentTextChanged.connect(self._on_filter_changed)
        bar.addWidget(self._action_filter)

        bar.addWidget(QLabel("目标:"))
        self._target_filter = QComboBox()
        self._target_filter.setMinimumWidth(160)
        self._target_filter.addItem("全部")
        self._target_filter.currentTextChanged.connect(self._on_filter_changed)
        bar.addWidget(self._target_filter)

        bar.addWidget(QLabel("结果:"))
        self._result_filter = QComboBox()
        self._result_filter.addItems(["全部", "success", "fail", "warn"])
        self._result_filter.currentTextChanged.connect(self._on_filter_changed)
        bar.addWidget(self._result_filter)

        bar.addWidget(QLabel("关键字:"))
        self._kw = QLineEdit()
        self._kw.setPlaceholderText("搜索目标/操作/详情...")
        self._kw.setMinimumWidth(180)
        self._kw.textChanged.connect(self._on_filter_changed)
        bar.addWidget(self._kw, 1)

        self._auto_chk = QCheckBox("自动刷新")
        self._auto_chk.setChecked(True)
        self._auto_chk.toggled.connect(self._on_auto_toggle)
        bar.addWidget(self._auto_chk)

        b_refresh = QPushButton("🔄 刷新")
        b_refresh.clicked.connect(self._refresh)
        bar.addWidget(b_refresh)
        b_export = QPushButton("📥 导出")
        b_export.clicked.connect(self._export)
        bar.addWidget(b_export)
        b_clear = QPushButton("🗑 清空")
        b_clear.clicked.connect(self._clear)
        bar.addWidget(b_clear)
        layout.addLayout(bar)

        # 详情区
        self._splitter_layout = QHBoxLayout()
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["时间", "操作", "目标", "结果", "详情"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.itemSelectionChanged.connect(self._on_select)

        self._detail = QLabel("（选择条目以查看详情）")
        self._detail.setWordWrap(True)
        self._detail.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._detail.setProperty("role", "caption")
        self._detail.setStyleSheet(
            f"color: {FG_SECONDARY}; padding: 10px; "
            f"background-color: {BG_PANEL}; border: 1px solid {BORDER}; "
            f"border-radius: {RADIUS_MD}px;")
        self._detail.setMinimumWidth(200)

        split = QHBoxLayout()
        split.addWidget(self._table, 3)
        # 详情面板
        detail_box = QFrame()
        detail_box.setMinimumWidth(220)
        detail_box.setProperty("role", "card")
        detail_box.setStyleSheet(
            f"background-color: {BG_PANEL}; border: 1px solid {BORDER}; "
            f"border-radius: {RADIUS_MD}px;")
        dl = QVBoxLayout(detail_box)
        dl.setContentsMargins(8, 8, 8, 8)
        detail_title = QLabel("操作详情")
        detail_title.setProperty("role", "sectionTitle")
        detail_title.setStyleSheet(f"color: {PRIMARY}; font-weight: 600; padding-bottom: 6px; "
                                  f"border-bottom: 1px solid {BORDER_LIGHT};")
        dl.addWidget(detail_title)
        dl.addWidget(self._detail, 1)
        split.addWidget(detail_box, 1)
        layout.addLayout(split, 1)

        # 注册监听
        register_audit_listener(self._on_new_entry)

        # 初始化过滤选项 + 刷新
        self._refresh_filters()
        self._refresh()

    def _on_auto_toggle(self, on: bool):
        self._auto_refresh = on
        if on:
            self._refresh_timer.start(5000)
        else:
            self._refresh_timer.stop()

    def _on_auto_refresh(self):
        if self._auto_refresh:
            self._refresh()

    def _on_new_entry(self, entry: dict):
        """收到新日志时刷新"""
        if self._auto_refresh:
            self._refresh()

    def _refresh_filters(self):
        # 记住当前值
        cur_act = self._action_filter.currentText()
        cur_tgt = self._target_filter.currentText()
        # 操作类型
        self._action_filter.blockSignals(True)
        self._action_filter.clear()
        self._action_filter.addItem("全部")
        self._action_filter.addItems(self._logger.get_all_actions())
        if cur_act in [self._action_filter.itemText(i) for i in range(self._action_filter.count())]:
            self._action_filter.setCurrentText(cur_act)
        self._action_filter.blockSignals(False)
        # 目标
        self._target_filter.blockSignals(True)
        self._target_filter.clear()
        self._target_filter.addItem("全部")
        self._target_filter.addItems(self._logger.get_all_targets())
        if cur_tgt in [self._target_filter.itemText(i) for i in range(self._target_filter.count())]:
            self._target_filter.setCurrentText(cur_tgt)
        self._target_filter.blockSignals(False)

    def _on_filter_changed(self, *_):
        self._refresh()

    def _refresh(self):
        # 更新过滤下拉（可能新增了类型）
        self._refresh_filters()
        # 统计
        stats = self._logger.get_stats()
        success_rate = (stats["success"] / stats["total"] * 100) if stats["total"] else 0
        self._stats_label.setText(
            f"📊 总计 {stats['total']} 条  |  ✓ 成功 {stats['success']}  |  "
            f"⚠ 警告 {stats['warn']}  |  ✗ 失败 {stats['fail']}  |  "
            f"🕐 24h 内 {stats['last_24h']}  |  "
            f"成功率 {success_rate:.1f}%"
        )
        # 表格
        entries = self._logger.get_entries(
            limit=2000,
            action_filter=self._action_filter.currentText(),
            target_filter=self._target_filter.currentText(),
            result_filter=self._result_filter.currentText(),
        )
        kw = self._kw.text().strip().lower()
        if kw:
            entries = [
                e for e in entries
                if kw in e.get("action", "").lower()
                or kw in e.get("target", "").lower()
                or kw in json.dumps(e.get("details", {}), ensure_ascii=False).lower()
            ]
        self._table.setRowCount(0)
        for e in entries:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(e.get("ts_str", "")))
            self._table.setItem(row, 1, QTableWidgetItem(e.get("action", "")))
            self._table.setItem(row, 2, QTableWidgetItem(e.get("target", "")))
            result_item = QTableWidgetItem(e.get("result", ""))
            r = e.get("result", "")
            if r == "success":
                result_item.setForeground(QColor(SUCCESS))
                result_item.setText("✓ " + r)
            elif r == "fail":
                result_item.setForeground(QColor(DANGER))
                result_item.setText("✗ " + r)
            elif r == "warn":
                result_item.setForeground(QColor(WARN))
                result_item.setText("⚠ " + r)
            self._table.setItem(row, 3, result_item)
            details = e.get("details", {})
            if details:
                d_text = ", ".join(f"{k}={v}" for k, v in details.items() if not isinstance(v, (dict, list)))
                if not d_text:
                    d_text = json.dumps(details, ensure_ascii=False)
            else:
                d_text = "—"
            self._table.setItem(row, 4, QTableWidgetItem(d_text[:200]))
            # 存原始数据
            self._table.item(row, 0).setData(Qt.UserRole, e)

    def _on_select(self):
        items = self._table.selectedItems()
        if not items:
            self._detail.setText("（选择条目以查看详情）")
            return
        row = items[0].row()
        entry = self._table.item(row, 0).data(Qt.UserRole)
        if not entry:
            return
        text = (
            f"<b style='color:{PRIMARY};'>操作:</b> {entry.get('action', '')}<br>"
            f"<b style='color:{PRIMARY};'>目标:</b> {entry.get('target', '')}<br>"
            f"<b style='color:{PRIMARY};'>结果:</b> {entry.get('result', '')}<br>"
            f"<b style='color:{PRIMARY};'>用户:</b> {entry.get('user', '')}<br>"
            f"<b style='color:{PRIMARY};'>时间:</b> {entry.get('ts_str', '')}<br><br>"
            f"<b style='color:{PRIMARY};'>详细信息:</b><br>"
            f"<pre style='color:{FG_SECONDARY}; white-space: pre-wrap; word-break: break-all;'>"
            f"{json.dumps(entry.get('details', {}), ensure_ascii=False, indent=2)}</pre>"
        )
        self._detail.setText(text)

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出审计日志", "audit_log.json", "JSON 文件 (*.json);;CSV (*.csv);;文本 (*.txt)")
        if not path:
            return
        try:
            entries = self._logger.get_entries(
                limit=99999,
                action_filter=self._action_filter.currentText(),
                target_filter=self._target_filter.currentText(),
                result_filter=self._result_filter.currentText(),
            )
            if path.lower().endswith(".csv"):
                import csv
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.writer(f)
                    w.writerow(["时间", "操作", "目标", "结果", "用户", "详情(JSON)"])
                    for e in entries:
                        w.writerow([
                            e.get("ts_str", ""), e.get("action", ""),
                            e.get("target", ""), e.get("result", ""),
                            e.get("user", ""),
                            json.dumps(e.get("details", {}), ensure_ascii=False),
                        ])
            else:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(entries, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "成功", f"已导出 {len(entries)} 条记录到\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "失败", str(e))

    def _clear(self):
        if QMessageBox.question(
            self, "确认", "确定清空所有审计日志？此操作不可恢复。"
        ) == QMessageBox.Yes:
            self._logger.clear()
            self._refresh()

    def stop(self):
        self._refresh_timer.stop()
        unregister_audit_listener(self._on_new_entry)
