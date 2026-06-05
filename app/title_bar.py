"""
自定义标题栏（无边框窗口）
支持：拖动、双击最大化、最小化/最大化/关闭按钮
"""

from typing import Optional

from PySide6.QtCore import Qt, QPoint, QSize, QEvent, Signal, QObject, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QPainter, QColor, QFont, QIcon, QPixmap, QLinearGradient, QBrush, QPen, QRadialGradient
)
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QSizePolicy, QGraphicsDropShadowEffect
)

from app.theme import (
    BG_DEEP, BG_PANEL, FG_PRIMARY, FG_SECONDARY, FG_TERTIARY,
    PRIMARY, PRIMARY_HOVER, PRIMARY_DARK, PRIMARY_GLOW, DANGER, BORDER, BORDER_LIGHT,
    FONT_FAMILY, FONT_SIZE_BASE, FONT_SIZE_SM, FONT_SIZE_MD,
    RADIUS_SM, RADIUS_MD, TITLE_BAR_HEIGHT, ANIM_FAST, ANIM_NORMAL,
)


class TitleBarButton(QPushButton):
    """标题栏按钮（最小化/最大化/关闭）"""

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self._kind = kind
        self.setFixedSize(48, TITLE_BAR_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(self._base_style())
        self._apply_icon()

    def _base_style(self) -> str:
        if self._kind == "close":
            return f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    border-radius: 0;
                    color: {FG_SECONDARY};
                    font-family: {FONT_FAMILY};
                }}
                QPushButton:hover {{
                    background-color: {DANGER};
                    color: white;
                    border-radius: {RADIUS_SM}px;
                }}
                QPushButton:pressed {{
                    background-color: #e04545;
                    color: rgba(255,255,255,0.85);
                    border-radius: {RADIUS_SM}px;
                }}
            """
        return f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 0;
                color: {FG_SECONDARY};
                font-family: {FONT_FAMILY};
            }}
            QPushButton:hover {{
                background-color: rgba(255,255,255,0.08);
                color: {FG_PRIMARY};
                border-radius: {RADIUS_SM}px;
            }}
            QPushButton:pressed {{
                background-color: rgba(255,255,255,0.14);
                color: {FG_PRIMARY};
                border-radius: {RADIUS_SM}px;
            }}
        """

    def _apply_icon(self):
        # 使用 Unicode 字符作为图标（避免外部资源依赖）
        if self._kind == "min":
            self.setText("—")
            self.setFont(QFont(FONT_FAMILY, 12, QFont.Bold))
        elif self._kind == "max":
            self.setText("▢")
            self.setFont(QFont(FONT_FAMILY, 12))
        elif self._kind == "restore":
            self.setText("❐")
            self.setFont(QFont(FONT_FAMILY, 12))
        elif self._kind == "close":
            self.setText("✕")
            self.setFont(QFont(FONT_FAMILY, 12, QFont.Bold))


class StatusIndicator(QWidget):
    """带脉冲动画的状态指示器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(20)
        self._dot_radius = 3.5
        self._pulse_phase = 0.0
        self._text = "运行中"
        self._color = QColor(PRIMARY)

        # 脉冲动画定时器
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)  # ~20fps，足够平滑且不浪费 CPU

    def _tick(self):
        self._pulse_phase += 0.08
        if self._pulse_phase > 2.0:
            self._pulse_phase = 0.0
        self.update()

    def set_status(self, text: str, color: str = PRIMARY):
        self._text = text
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        w, h = self.width(), self.height()
        dot_cx = 6.0
        dot_cy = h / 2.0

        # === 脉冲光晕 ===
        pulse_alpha = int(40 + 30 * (1.0 - abs(self._pulse_phase - 1.0)))
        glow_radius = self._dot_radius + 4 + 3 * (1.0 - abs(self._pulse_phase - 1.0))
        glow_color = QColor(self._color)
        glow_color.setAlpha(pulse_alpha)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(glow_color))
        p.drawEllipse(QPoint(int(dot_cx), int(dot_cy)), int(glow_radius), int(glow_radius))

        # === 实心圆点 ===
        p.setBrush(QBrush(self._color))
        p.drawEllipse(QPoint(int(dot_cx), int(dot_cy)), int(self._dot_radius), int(self._dot_radius))

        # === 文字 ===
        p.setPen(QColor(self._color))
        p.setFont(QFont(FONT_FAMILY, FONT_SIZE_SM, QFont.Medium))
        p.drawText(int(dot_cx + 10), int(dot_cy + 4), self._text)

        p.end()

    def minimumSizeHint(self):
        fm = self.fontMetrics()
        text_w = fm.horizontalAdvance(self._text) if hasattr(fm, 'horizontalAdvance') else fm.width(self._text)
        return QSize(int(20 + text_w), 20)


class CustomTitleBar(QWidget):
    """自定义标题栏

    内部布局（垂直）：
      ┌─────────────────────────────────────────────────────────┐
      │  [图标] 标题文字                状态  [_] [□] [×]        │   <- 拖动区
      │  工具(T)  帮助(H)  ... 菜单栏 ...                        │   <- 菜单栏
      └─────────────────────────────────────────────────────────┘
    """

    MENU_BAR_HEIGHT = 28

    def __init__(self, parent_window):
        super().__init__(parent_window)
        self._parent_window = parent_window
        self.setFixedHeight(TITLE_BAR_HEIGHT + self.MENU_BAR_HEIGHT)
        self.setAttribute(Qt.WA_StyledBackground, False)
        # 关闭样式表背景，使用 paintEvent 自绘
        self.setStyleSheet("QWidget { background: transparent; border: none; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---------- 第 1 行：图标 / 标题 / 窗口控制按钮 ----------
        title_row = QWidget()
        title_row.setFixedHeight(TITLE_BAR_HEIGHT)
        title_row.setAttribute(Qt.WA_TranslucentBackground, True)
        title_row.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(title_row)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(0)

        # 应用图标 - 使用 SVG 文件
        from app.icon_loader import get_icon_pixmap
        self._icon_label = QLabel()
        self._icon_label.setFixedSize(24, 24)
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_label.setPixmap(get_icon_pixmap(24))
        self._icon_label.setStyleSheet("background: transparent;")
        layout.addSpacing(2)
        layout.addWidget(self._icon_label)

        # 标题
        self._title = QLabel("AiinLink")
        self._title.setStyleSheet(
            f"color: {FG_PRIMARY}; font-size: 14px; "
            f"font-weight: 600; padding-left: 6px; background: transparent; "
            f"letter-spacing: 1px;")
        layout.addWidget(self._title)

        # 副标题
        self._subtitle = QLabel("·  智能网络与服务器诊断工作站")
        self._subtitle.setStyleSheet(
            f"color: {FG_TERTIARY}; font-size: 11px; "
            f"font-weight: 400; padding-left: 2px; background: transparent;")
        layout.addWidget(self._subtitle)

        layout.addStretch(1)

        # 状态指示（带脉冲动画效果）
        self._status_indicator = StatusIndicator()
        self._status_indicator.setFixedWidth(80)
        self._status_indicator.setToolTip("应用运行中")
        layout.addWidget(self._status_indicator)
        layout.addSpacing(6)

        # 窗口控制按钮
        self._btn_min = TitleBarButton("min")
        self._btn_min.clicked.connect(self._on_minimize)
        layout.addWidget(self._btn_min)

        self._btn_max = TitleBarButton("max")
        self._btn_max.clicked.connect(self._on_maximize_restore)
        layout.addWidget(self._btn_max)

        self._btn_close = TitleBarButton("close")
        self._btn_close.clicked.connect(self._on_close)
        layout.addWidget(self._btn_close)

        outer.addWidget(title_row)
        self._title_row = title_row

        # 拖动状态初始化
        self._drag_pos: Optional[QPoint] = None
        self._is_dragging = False
        self.setMouseTracking(True)

        # ---------- 第 2 行：菜单栏占位容器 ----------
        self._menu_container = QWidget()
        self._menu_container.setFixedHeight(self.MENU_BAR_HEIGHT)
        self._menu_container.setStyleSheet(
            f"background-color: {BG_DEEP}; border: none;")
        outer.addWidget(self._menu_container)

        # 在标题栏内部创建一个 QMenuBar（不通过 QMainWindow.menuBar() 创建）
        # 由 MainWindow 重写 menuBar() 方法返回此对象，避免 QMainWindow 重新创建
        from PySide6.QtWidgets import QMenuBar
        self._menu_bar = QMenuBar(self._menu_container)
        self._menu_bar.setStyleSheet(f"""
            QMenuBar {{
                background-color: {BG_DEEP};
                color: {FG_SECONDARY};
                padding: 2px 6px;
                border: none;
                font-size: {FONT_SIZE_SM}px;
            }}
            QMenuBar::item {{
                background: transparent;
                padding: 4px 10px;
                border-radius: {RADIUS_SM}px;
                color: {FG_SECONDARY};
            }}
            QMenuBar::item:selected {{
                background-color: rgba(78, 205, 196, 0.12);
                color: {PRIMARY};
            }}
            QMenuBar::item:pressed {{
                background-color: {PRIMARY};
                color: #0a1f1d;
            }}
        """)
        mb_layout = QHBoxLayout(self._menu_container)
        mb_layout.setContentsMargins(4, 0, 4, 0)
        mb_layout.setSpacing(0)
        mb_layout.addWidget(self._menu_bar)
        mb_layout.addStretch(1)

    def menuBar(self):
        """返回标题栏内的 QMenuBar（被 MainWindow 覆盖）"""
        return self._menu_bar

    def set_title(self, text: str):
        self._title.setText(text)

    def paintEvent(self, event):
        """自绘标题栏背景：渐变 + 顶部高光 + 底部青蓝强调线 + 底部阴影"""
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)  # 整块矩形不需要抗锯齿

        w, h = self.width(), self.height()
        menu_h = self.MENU_BAR_HEIGHT
        title_h = h - menu_h

        # === 第 1 部分：标题行（微蓝/青色调渐变）===
        title_grad = QLinearGradient(0, 0, 0, title_h)
        title_grad.setColorAt(0.0, QColor("#1a2030"))   # 顶部 - 微蓝调
        title_grad.setColorAt(0.4, QColor("#161a24"))   # 中上
        title_grad.setColorAt(1.0, QColor("#0f1320"))   # 底部 - 深沉
        p.fillRect(0, 0, w, title_h, QBrush(title_grad))

        # === 顶部 1px 高光（增强立体感）===
        p.fillRect(0, 0, w, 1, QColor(255, 255, 255, 35))

        # === 第 2 部分：菜单行（纯色）===
        p.fillRect(0, title_h, w, menu_h, QColor(BG_DEEP))

        # === 标题行与菜单行之间：1px 分隔线 ===
        p.fillRect(0, title_h, w, 1, QColor(BORDER))

        # === 菜单行底部：2px 强调线（带发光）===
        # 先画一层柔和光晕（4px 渐变）
        glow_grad = QLinearGradient(0, 0, w, 0)
        gc0 = QColor(PRIMARY); gc0.setAlpha(0)
        gc1 = QColor(PRIMARY); gc1.setAlpha(50)
        gc2 = QColor(PRIMARY); gc2.setAlpha(0)
        glow_grad.setColorAt(0.0, gc0)
        glow_grad.setColorAt(0.3, gc1)
        glow_grad.setColorAt(0.7, gc1)
        glow_grad.setColorAt(1.0, gc2)
        p.fillRect(0, h - 4, w, 2, QBrush(glow_grad))

        # 主强调线（2px）
        accent = QLinearGradient(0, 0, w, 0)
        c0 = QColor(PRIMARY); c0.setAlpha(0)
        c1 = QColor(PRIMARY); c1.setAlpha(200)
        c2 = QColor(PRIMARY); c2.setAlpha(0)
        accent.setColorAt(0.0, c0)
        accent.setColorAt(0.2, c1)
        accent.setColorAt(0.8, c1)
        accent.setColorAt(1.0, c2)
        p.fillRect(0, h - 2, w, 2, QBrush(accent))

        # === 底部阴影（向下渐隐）===
        shadow_grad = QLinearGradient(0, h - 2, 0, h + 6)
        shadow_grad.setColorAt(0.0, QColor(0, 0, 0, 40))
        shadow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(0, h, w, 6, QBrush(shadow_grad))

        # === 图标左侧：3px 品牌色竖条（细节）===
        bar_grad = QLinearGradient(0, 0, 0, title_h)
        bar_grad.setColorAt(0.0, QColor(PRIMARY))
        bar_grad.setColorAt(1.0, QColor(PRIMARY_DARK))
        p.fillRect(0, 0, 3, title_h, QBrush(bar_grad))

        p.end()

    def _on_minimize(self):
        self._parent_window.showMinimized()

    def _on_maximize_restore(self):
        if self._parent_window.isMaximized():
            self._parent_window.showNormal()
            self._btn_max._apply_icon()  # 切回最大化图标
        else:
            self._parent_window.showMaximized()
            self._btn_max._kind = "restore"
            self._btn_max._apply_icon()

    def _on_close(self):
        self._parent_window.close()

    def mouseDoubleClickEvent(self, event):
        # 双击标题栏空白区域：最大化/还原
        if event.button() == Qt.LeftButton and event.pos().y() < TITLE_BAR_HEIGHT:
            # 仅当点中的是非按钮子控件时才触发（按钮自己处理）
            child = self.childAt(event.pos())
            if child is None or not isinstance(child, TitleBarButton):
                self._on_maximize_restore()
                event.accept()


# ============================================================
# 窗口拖动（事件过滤器模式，不受 childAt 影响）
# ============================================================

class WindowMover(QObject):
    """为主窗口添加：拖动标题栏移动窗口 + 双击标题栏最大化

    通过在主窗口安装 eventFilter 统一拦截鼠标事件，
    避免在 title_bar 子控件上点击时事件被子控件吞掉。
    """

    def __init__(self, window, title_bar):
        super().__init__(window)
        self._window = window
        self._title_bar = title_bar
        self._drag_offset = None  # QPoint, 鼠标按下点到窗口左上角的偏移
        window.setMouseTracking(True)
        window.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is not self._window:
            return False

        et = event.type()
        # 只关心鼠标事件
        if et not in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseMove,
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.MouseButtonDblClick,
        ):
            return False

        # 鼠标按下：必须在标题栏第 1 行，且不在窗口控制按钮上
        if et == QEvent.Type.MouseButtonPress and event.button() == Qt.LeftButton:
            gp = event.globalPosition().toPoint()
            local_in_tb = self._title_bar.mapFromGlobal(gp)
            if 0 <= local_in_tb.y() < TITLE_BAR_HEIGHT:
                tb_child = self._title_bar.childAt(local_in_tb)
                if not isinstance(tb_child, TitleBarButton):
                    # 记录偏移，开始拖动
                    self._drag_offset = gp - self._window.frameGeometry().topLeft()
                    return True  # 消费掉，避免触发子控件事件
            return False

        # 鼠标移动：正在拖动则移动窗口（不受位置限制）
        if et == QEvent.Type.MouseMove and self._drag_offset is not None \
                and not self._window.isMaximized():
            gp = event.globalPosition().toPoint()
            self._window.move(gp - self._drag_offset)
            return True

        # 鼠标释放：清状态
        if et == QEvent.Type.MouseButtonRelease and event.button() == Qt.LeftButton:
            if self._drag_offset is not None:
                self._drag_offset = None
                return True
            return False

        # 双击标题栏：最大化/还原
        if et == QEvent.Type.MouseButtonDblClick and event.button() == Qt.LeftButton:
            gp = event.globalPosition().toPoint()
            local_in_tb = self._title_bar.mapFromGlobal(gp)
            if 0 <= local_in_tb.y() < TITLE_BAR_HEIGHT:
                if self._window.isMaximized():
                    self._window.showNormal()
                else:
                    self._window.showMaximized()
                self._drag_offset = None
                return True

        return False


# ============================================================
# 无边框窗口边缘缩放支持
# ============================================================

class FramelessResizer(QObject):
    """为无边框窗口添加边缘拖动缩放能力"""

    BORDER = 6  # 边缘感应宽度

    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self._resizing = False
        self._resize_dir = None
        self._press_pos = None
        self._press_geo = None
        window.setMouseTracking(True)
        window.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is not self._window:
            return False
        et = event.type()

        # 鼠标移动：更新光标
        if et == QEvent.Type.MouseMove and not self._resizing:
            try:
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            except Exception:
                pos = event.pos()
            self._update_cursor(pos)
            return False

        # 鼠标按下：开始缩放
        if et == QEvent.Type.MouseButtonPress and event.button() == Qt.LeftButton:
            try:
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            except Exception:
                pos = event.pos()
            d = self._dir_at(pos)
            if d and not self._window.isMaximized():
                self._resizing = True
                self._resize_dir = d
                self._press_pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") \
                                  else event.globalPos()
                self._press_geo = self._window.geometry()
                return True
            return False

        # 鼠标移动：执行缩放
        if et == QEvent.Type.MouseMove and self._resizing:
            try:
                gp = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
            except Exception:
                gp = event.globalPos()
            self._do_resize(gp)
            return True

        # 鼠标释放
        if et == QEvent.Type.MouseButtonRelease and self._resizing:
            self._resizing = False
            self._resize_dir = None
            return True

        return False

    def _dir_at(self, pos) -> Optional[str]:
        """判断鼠标位置属于哪个缩放方向"""
        if self._window.isMaximized() or self._window.isFullScreen():
            return None
        w = self._window.width()
        h = self._window.height()
        b = self.BORDER
        left = pos.x() < b
        right = pos.x() > w - b
        top = pos.y() < b
        bottom = pos.y() > h - b
        if top and left: return "topleft"
        if top and right: return "topright"
        if bottom and left: return "bottomleft"
        if bottom and right: return "bottomright"
        if left: return "left"
        if right: return "right"
        if top: return "top"
        if bottom: return "bottom"
        return None

    def _update_cursor(self, pos):
        d = self._dir_at(pos)
        cursors = {
            "left": Qt.SizeHorCursor, "right": Qt.SizeHorCursor,
            "top": Qt.SizeVerCursor, "bottom": Qt.SizeVerCursor,
            "topleft": Qt.SizeFDiagCursor, "bottomright": Qt.SizeFDiagCursor,
            "topright": Qt.SizeBDiagCursor, "bottomleft": Qt.SizeBDiagCursor,
        }
        if d:
            self._window.setCursor(cursors[d])
        else:
            self._window.unsetCursor()

    def _do_resize(self, global_pos):
        geo = self._press_geo
        dx = global_pos.x() - self._press_pos.x()
        dy = global_pos.y() - self._press_pos.y()
        min_w = self._window.minimumWidth()
        min_h = self._window.minimumHeight()
        new_x, new_y, new_w, new_h = geo.x(), geo.y(), geo.width(), geo.height()

        d = self._resize_dir
        if "left" in d:
            new_w = max(min_w, geo.width() - dx)
            new_x = geo.x() + (geo.width() - new_w)
        if "right" in d:
            new_w = max(min_w, geo.width() + dx)
        if "top" in d:
            new_h = max(min_h, geo.height() - dy)
            new_y = geo.y() + (geo.height() - new_h)
        if "bottom" in d:
            new_h = max(min_h, geo.height() + dy)

        self._window.setGeometry(new_x, new_y, new_w, new_h)
