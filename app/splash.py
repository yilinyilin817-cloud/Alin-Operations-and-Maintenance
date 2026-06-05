"""
启动闪屏 (SplashScreen)
带动画进度条和动态状态文字
"""

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Signal
from PySide6.QtGui import QColor, QPainter, QFont, QLinearGradient, QPen, QBrush
from PySide6.QtWidgets import QSplashScreen, QProgressBar, QLabel, QVBoxLayout, QWidget

from app.theme import (
    BG_DEEP, BG_BASE, PRIMARY, PRIMARY_HOVER, PRIMARY_DARK,
    FG_PRIMARY, FG_SECONDARY, FONT_FAMILY, FONT_SIZE_LG, FONT_SIZE_BASE,
)


class AnimatedSplash(QSplashScreen):
    """带动画效果的启动屏幕"""

    progress_changed = Signal(int)

    def __init__(self):
        # 启动画面尺寸
        pix = self._render_pixmap(560, 340)
        super().__init__(pix, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        # 内嵌控件
        container = QWidget(self)
        container.setGeometry(0, 0, 560, 340)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 32, 36, 28)
        layout.setSpacing(0)

        # 标题
        layout.addStretch(1)
        self._title = QLabel("AiinLink")
        self._title.setProperty("role", "heroTitle")
        self._title.setStyleSheet(
            f"color: {PRIMARY}; font-size: 38px; font-weight: 800; "
            f"font-family: {FONT_FAMILY}; letter-spacing: 2px; background: transparent;")
        self._title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._title)

        self._subtitle = QLabel("智能网络与服务器诊断工作站")
        self._subtitle.setProperty("role", "heroSubtitle")
        self._subtitle.setStyleSheet(
            f"color: {FG_SECONDARY}; font-size: 13px; "
            f"font-family: {FONT_FAMILY}; margin-top: 6px; background: transparent;")
        self._subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._subtitle)

        layout.addStretch(2)

        # 状态文字
        self._status = QLabel("正在初始化...")
        self._status.setProperty("role", "muted")
        self._status.setStyleSheet(
            f"color: {FG_SECONDARY}; font-size: 12px; "
            f"font-family: {FONT_FAMILY}; background: transparent;")
        self._status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._status)

        layout.addSpacing(8)

        # 进度条
        self._bar = QProgressBar()
        self._bar.setMaximum(100)
        self._bar.setValue(0)
        self._bar.setFixedHeight(6)
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #232734;
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {PRIMARY_DARK}, stop:0.5 {PRIMARY}, stop:1 {PRIMARY_HOVER});
                border-radius: 3px;
            }}
        """)
        layout.addWidget(self._bar)

        layout.addSpacing(6)

        self._version = QLabel("v1.0.0  ·  Enterprise Edition")
        self._version.setProperty("role", "muted")
        self._version.setStyleSheet(
            f"color: #5a6273; font-size: 10px; font-family: {FONT_FAMILY}; background: transparent;")
        self._version.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._version)

        # 模拟进度
        self._target = 0
        self._current = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def _render_pixmap(self, w: int, h: int):
        """预渲染背景 pixmap（含渐变和圆角）"""
        from PySide6.QtGui import QPixmap
        pix = QPixmap(w, h)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        # 圆角矩形背景渐变
        gradient = QLinearGradient(0, 0, 1, 1)
        gradient.setCoordinateMode(QLinearGradient.ObjectBoundingMode)
        gradient.setColorAt(0, QColor("#0f1320"))
        gradient.setColorAt(0.5, QColor("#161a26"))
        gradient.setColorAt(1, QColor("#0d1a1f"))
        p.setBrush(QBrush(gradient))
        p.setPen(QPen(QColor("#2a4a48"), 1))
        from PySide6.QtCore import QRectF
        p.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 14, 14)
        p.end()
        return pix

    def _tick(self):
        if self._current < self._target:
            self._current = min(self._target, self._current + 2)
            self._bar.setValue(self._current)
        elif self._target >= 100:
            # 完成后停止
            self._timer.stop()

    def set_progress(self, value: int, status: str = ""):
        """设置进度 0-100，可选状态文字"""
        self._target = max(0, min(100, value))
        if status:
            self._status.setText(status)

    def show_message(self, message: str, color: str = None):
        """兼容 QSplashScreen.show_message 的接口"""
        self._status.setText(message)

    def finish_with_fade(self, widget):
        """淡出关闭"""
        self._timer.stop()
        self._target = 100
        self._current = 100
        self._bar.setValue(100)

        # 透明度动画
        anim = QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(280)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.InOutQuad)
        anim.start()
        # 防止动画被回收
        self._fade_anim = anim

        def _finish():
            try:
                self.finish(widget)
            except Exception:
                pass

        QTimer.singleShot(280, _finish)
