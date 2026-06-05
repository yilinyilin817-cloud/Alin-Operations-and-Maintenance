"""
左侧侧边栏导航
现代化图标 + 标签导航
可折叠（图标模式 / 完整模式）
带平滑动画、渐变效果、用户头像区
"""

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QSize, QRectF, Property
from PySide6.QtGui import QFont, QPainter, QColor, QLinearGradient, QPen, QBrush, QFontMetrics
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QButtonGroup, QSizePolicy, QToolButton, QGraphicsDropShadowEffect
)

from app.theme import (
    BG_DEEP, BG_PANEL, BG_PANEL_HOVER, BG_RAISED,
    FG_PRIMARY, FG_SECONDARY, FG_TERTIARY, FG_DISABLED,
    PRIMARY, PRIMARY_HOVER, PRIMARY_DARK,
    BORDER, BORDER_LIGHT,
    FONT_FAMILY, FONT_SIZE_BASE, FONT_SIZE_SM,
    RADIUS_SM, RADIUS_MD, SIDEBAR_WIDTH, SIDEBAR_WIDTH_EXPANDED,
    ANIM_NORMAL, ANIM_SLOW,
)


class GradientTextLabel(QLabel):
    """带渐变色文字效果的标签"""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self._gradient_colors = [PRIMARY, PRIMARY_HOVER, "#a8edea"]

    def set_gradient_colors(self, colors: list[str]):
        self._gradient_colors = colors
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        gradient = QLinearGradient(0, 0, self.width(), 0)
        for i, color in enumerate(self._gradient_colors):
            gradient.setColorAt(i / max(1, len(self._gradient_colors) - 1), QColor(color))

        font = self.font()
        painter.setFont(font)
        painter.setPen(QPen(QBrush(gradient), 0))

        opt = self.alignment()
        fm = QFontMetrics(font)
        text_rect = fm.boundingRect(self.text())
        x = 0
        if opt & Qt.AlignHCenter:
            x = (self.width() - text_rect.width()) // 2
        elif opt & Qt.AlignRight:
            x = self.width() - text_rect.width()
        y = (self.height() + text_rect.height()) // 2 - fm.descent()

        painter.drawText(x, y, self.text())
        painter.end()


class AvatarWidget(QWidget):
    """圆形用户头像占位组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(32, 32)
        self._initials = "U"
        self._bg_color = QColor(PRIMARY_DARK)
        self._fg_color = QColor("#0a1f1d")

    def set_initials(self, text: str):
        self._initials = text[:2].upper() if text else "U"
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 圆形背景
        painter.setBrush(QBrush(self._bg_color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(1, 1, self.width() - 2, self.height() - 2)

        # 外圈微光
        glow_gradient = QLinearGradient(0, 0, self.width(), self.height())
        glow_gradient.setColorAt(0, QColor(PRIMARY))
        glow_gradient.setColorAt(1, QColor(PRIMARY_HOVER))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QBrush(glow_gradient), 1.5))
        painter.drawEllipse(1, 1, self.width() - 2, self.height() - 2)

        # 首字母
        font = QFont(FONT_FAMILY, 12, QFont.Bold)
        painter.setFont(font)
        painter.setPen(self._fg_color)
        painter.drawText(QRectF(0, 0, self.width(), self.height()), Qt.AlignCenter, self._initials)
        painter.end()


class NavButton(QPushButton):
    """侧边栏导航按钮 - 选中时带左侧高亮条 + 圆角 + 渐变背景 + 发光效果"""

    def __init__(self, icon: str, label: str, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._label = label
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(label)
        self.setMinimumHeight(44)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._apply_style(False, False)

    def set_expanded(self, expanded: bool):
        self._apply_style(self.isChecked(), expanded)

    def _apply_style(self, checked: bool, expanded: bool):
        # 文本对齐
        if expanded:
            self.setText(f"  {self._icon}    {self._label}")
            self.setFont(QFont(FONT_FAMILY, 12))
        else:
            self.setText(self._icon)
            self.setFont(QFont(FONT_FAMILY, 18))

        # 颜色 - 选中态：渐变背景 + 左侧高亮条 + 发光；非选中：透明
        if checked:
            bg = (
                f"qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                f"stop:0 rgba(78, 205, 196, 25), stop:1 rgba(78, 205, 196, 8))"
            )
            fg = PRIMARY
            font_w = 600
            border_l = f"4px solid {PRIMARY}"
            margin_l = "2px"
            padding_h = "0 14px"
            glow = (
                f"QPushButton {{ "
                f"background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                f"stop:0 rgba(78, 205, 196, 25), stop:1 rgba(78, 205, 196, 8)); "
                f"box-shadow: 0 0 12px rgba(78, 205, 196, 0.15); }}"
            )
        else:
            bg = "transparent"
            fg = FG_SECONDARY
            font_w = 500
            border_l = "4px solid transparent"
            margin_l = "2px"
            padding_h = "0 14px"
            glow = ""

        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                color: {fg};
                border: none;
                border-left: {border_l};
                border-radius: 0 {RADIUS_MD}px {RADIUS_MD}px 0;
                padding: {padding_h};
                margin-left: {margin_l};
                margin-right: 6px;
                text-align: {'left' if expanded else 'center'};
                font-weight: {font_w};
                font-family: {FONT_FAMILY};
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(78, 205, 196, 30), stop:1 rgba(78, 205, 196, 10));
                color: {PRIMARY_HOVER if not checked else PRIMARY};
                border-left: 4px solid {PRIMARY_HOVER if not checked else PRIMARY};
            }}
            QPushButton:checked {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(78, 205, 196, 25), stop:1 rgba(78, 205, 196, 8));
            }}
        """)

    def setChecked(self, checked: bool):
        super().setChecked(checked)
        # 找到父对象判断是否展开
        parent = self.parent()
        while parent and not isinstance(parent, SideNav):
            parent = parent.parent()
        if isinstance(parent, SideNav):
            self._apply_style(checked, parent.is_expanded())


class SideNav(QFrame):
    """左侧侧边栏 - 现代化导航（带动画与渐变效果）"""

    nav_changed = Signal(int)  # 导航索引变化

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SideNav")
        self.setFixedWidth(SIDEBAR_WIDTH_EXPANDED)
        self._expanded = True
        self._buttons: list[NavButton] = []
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)

        # 动画
        self._anim = QPropertyAnimation(self, b"maximumWidth")
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._anim.setDuration(ANIM_SLOW)

        # 右侧阴影/发光效果
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(24)
        self._shadow.setOffset(4, 0)
        self._shadow.setColor(QColor(0, 0, 0, 60))
        self.setGraphicsEffect(self._shadow)

        # 整体样式：深色背景 + 右侧渐变分隔线
        self.setStyleSheet(f"""
            QFrame#SideNav {{
                background-color: {BG_DEEP};
                border-right: 1px solid {BORDER};
                border-top: none;
                border-bottom: none;
                border-left: none;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ====== 顶部 Logo 区域（带渐变背景 + SVG 图标）======
        self._logo_container = QWidget()
        self._logo_container.setFixedHeight(72)
        self._logo_container.setAttribute(Qt.WA_StyledBackground, True)
        self._logo_container.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(78, 205, 196, 12), stop:1 {BG_DEEP});
                border: none;
            }}
        """)
        logo_layout = QHBoxLayout(self._logo_container)
        logo_layout.setContentsMargins(16, 12, 16, 12)
        logo_layout.setSpacing(12)

        # SVG 图标
        from app.icon_loader import get_icon_pixmap
        self._logo_icon = QLabel()
        self._logo_icon.setFixedSize(32, 32)
        self._logo_icon.setAlignment(Qt.AlignCenter)
        self._logo_icon.setPixmap(get_icon_pixmap(32))
        self._logo_icon.setStyleSheet("background: transparent;")
        logo_layout.addWidget(self._logo_icon)

        # 标题文字 - 渐变色
        self._logo_text = GradientTextLabel("AiinLink")
        self._logo_text.setFont(QFont(FONT_FAMILY, 17, QFont.ExtraBold))
        self._logo_text.setStyleSheet("background: transparent;")
        logo_layout.addWidget(self._logo_text)

        logo_layout.addStretch()

        # 底部分隔线（青蓝色渐变）
        self._logo_line = QWidget()
        self._logo_line.setFixedHeight(1)
        self._logo_line.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {PRIMARY}, stop:0.4 {PRIMARY}60, stop:1 transparent);
        """)
        layout.addWidget(self._logo_container)
        layout.addWidget(self._logo_line)

        # ====== 工作区分组 ======
        self._sec1_title = self._create_section_title("工作区")
        layout.addWidget(self._sec1_title)

        # 工作区导航项
        self._add_nav("📊", "仪表盘", layout, 0)
        self._add_nav("🛠", "运维控制台", layout, 1)
        self._add_nav("📡", "实时抓取", layout, 2)

        # ====== 工具分组 ======
        self._sec2_title = self._create_section_title("工具")
        layout.addWidget(self._sec2_title)

        self._add_nav("🔍", "网络工具", layout, 3)
        self._add_nav("🛡", "安全工具", layout, 4)

        layout.addStretch(1)

        # ====== 用户头像/资料区域 ======
        self._profile_container = QWidget()
        self._profile_container.setAttribute(Qt.WA_StyledBackground, True)
        self._profile_container.setFixedHeight(52)
        self._profile_container.setStyleSheet(f"""
            QWidget {{
                background: transparent;
                border: none;
            }}
        """)
        profile_layout = QHBoxLayout(self._profile_container)
        profile_layout.setContentsMargins(14, 6, 14, 6)
        profile_layout.setSpacing(10)

        self._avatar = AvatarWidget()
        profile_layout.addWidget(self._avatar)

        self._profile_name = QLabel("User")
        self._profile_name.setStyleSheet(f"""
            color: {FG_PRIMARY};
            font-size: 12px;
            font-weight: 600;
            font-family: {FONT_FAMILY};
            background: transparent;
        """)
        profile_layout.addWidget(self._profile_name)

        self._profile_status = QLabel()
        self._profile_status.setFixedSize(8, 8)
        self._profile_status.setStyleSheet(f"""
            background-color: #3ecf8e;
            border-radius: 4px;
        """)
        profile_layout.addWidget(self._profile_status)

        profile_layout.addStretch()
        layout.addWidget(self._profile_container)

        # ====== 底部分隔线 ======
        self._bottom_line = QWidget()
        self._bottom_line.setFixedHeight(1)
        self._bottom_line.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 transparent, stop:0.3 {BORDER_LIGHT}, stop:0.7 {BORDER_LIGHT}, stop:1 transparent);
        """)
        layout.addWidget(self._bottom_line)

        # ====== 折叠按钮 ======
        self._btn_collapse = QPushButton("◁  收起")
        self._btn_collapse.setCursor(Qt.PointingHandCursor)
        self._btn_collapse.setFixedHeight(36)
        self._btn_collapse.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {FG_TERTIARY};
                border: none;
                border-top: 1px solid qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 transparent, stop:0.3 {BORDER_LIGHT}, stop:0.7 {BORDER_LIGHT}, stop:1 transparent);
                font-family: {FONT_FAMILY};
                font-size: 11px;
                font-weight: 500;
                padding: 0 14px;
                border-radius: 0;
            }}
            QPushButton:hover {{
                color: {PRIMARY};
                background-color: rgba(78, 205, 196, 0.06);
            }}
        """)
        self._btn_collapse.clicked.connect(self.toggle)
        layout.addWidget(self._btn_collapse)

        # 版本号
        self._version = QLabel("v1.0.0")
        self._version.setAlignment(Qt.AlignCenter)
        self._version.setStyleSheet(
            f"color: {FG_DISABLED}; font-size: 9px; padding: 2px 0 6px 0; background: transparent;")
        layout.addWidget(self._version)

    def _create_section_title(self, text: str) -> QLabel:
        """创建带装饰线的分组标题"""
        label = QLabel(f"─  {text}")
        label.setFixedHeight(36)
        label.setStyleSheet(
            f"color: {FG_TERTIARY}; font-size: 10px; font-weight: 600; "
            f"letter-spacing: 2px; padding: 10px 0 4px 14px; background: transparent;")
        return label

    def _add_nav(self, icon: str, label: str, layout: QVBoxLayout, idx: int):
        btn = NavButton(icon, label)
        btn.clicked.connect(lambda checked=False, i=idx: self._on_nav_clicked(i))
        self._button_group.addButton(btn)
        self._buttons.append(btn)
        layout.addWidget(btn)
        return btn

    def _on_nav_clicked(self, idx: int):
        self.nav_changed.emit(idx)

    def select(self, idx: int):
        if 0 <= idx < len(self._buttons):
            self._buttons[idx].setChecked(True)

    def is_expanded(self) -> bool:
        return self._expanded

    def toggle(self):
        if self._expanded:
            self.collapse()
        else:
            self.expand()

    def expand(self):
        if self._expanded:
            return
        self._expanded = True
        self._animate_width(SIDEBAR_WIDTH_EXPANDED)
        for b in self._buttons:
            b.set_expanded(True)
        self._sec1_title.setVisible(True)
        self._sec2_title.setVisible(True)
        self._logo_text.setVisible(True)
        self._logo_line.setVisible(True)
        self._profile_name.setVisible(True)
        self._profile_status.setVisible(True)
        self._btn_collapse.setText("◁  收起")

    def collapse(self):
        if not self._expanded:
            return
        self._expanded = False
        self._animate_width(SIDEBAR_WIDTH)
        for b in self._buttons:
            b.set_expanded(False)
        self._sec1_title.setVisible(False)
        self._sec2_title.setVisible(False)
        self._logo_text.setVisible(False)
        self._logo_line.setVisible(False)
        self._profile_name.setVisible(False)
        self._profile_status.setVisible(False)
        self._btn_collapse.setText("▷")

    def _animate_width(self, target_width: int):
        """平滑动画过渡侧边栏宽度"""
        self._anim.stop()
        self._anim.setStartValue(self.width())
        self._anim.setEndValue(target_width)
        self._anim.finished.connect(lambda: self.setFixedWidth(target_width))
        self.setMinimumWidth(SIDEBAR_WIDTH)
        self.setMaximumWidth(SIDEBAR_WIDTH_EXPANDED)
        self._anim.start()

    def selected_index(self) -> int:
        for i, b in enumerate(self._buttons):
            if b.isChecked():
                return i
        return -1
