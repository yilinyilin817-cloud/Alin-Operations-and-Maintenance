"""
关于对话框 - 美化的欢迎/关于弹窗
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTextEdit
)

from app.theme import (
    BG_DEEP, BG_PANEL, BG_PANEL_HOVER,
    FG_PRIMARY, FG_SECONDARY, FG_TERTIARY,
    PRIMARY, ACCENT_BLUE, ACCENT_PURPLE, SUCCESS, WARN, DANGER,
    BORDER, BORDER_LIGHT,
    FONT_FAMILY, FONT_SIZE_BASE, FONT_SIZE_SM, FONT_SIZE_MD, FONT_SIZE_LG,
    FONT_SIZE_XL, FONT_SIZE_XXL, RADIUS_MD, RADIUS_LG,
)


class FeatureCard(QFrame):
    """关于页面的功能卡片"""

    def __init__(self, icon: str, title: str, desc: str, color: str, parent=None):
        super().__init__(parent)
        self.setProperty("role", "card")
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_PANEL};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_MD}px;
                padding: 8px;
            }}
            QFrame:hover {{
                border-color: {color};
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"color: {color}; font-size: 28px; background: transparent;")
        icon_lbl.setFixedWidth(40)
        icon_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_lbl)

        text_lay = QVBoxLayout()
        text_lay.setSpacing(2)
        title_lbl = QLabel(title)
        title_lbl.setProperty("role", "strong")
        title_lbl.setStyleSheet(
            f"color: {FG_PRIMARY}; font-size: 13px; font-weight: 600; background: transparent;")
        text_lay.addWidget(title_lbl)
        desc_lbl = QLabel(desc)
        desc_lbl.setProperty("role", "caption")
        desc_lbl.setStyleSheet(
            f"color: {FG_SECONDARY}; font-size: 11px; background: transparent;")
        desc_lbl.setWordWrap(True)
        text_lay.addWidget(desc_lbl)
        layout.addLayout(text_lay, 1)


class AboutDialog(QDialog):
    """关于对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("关于 AiinLink")
        self.setFixedSize(560, 620)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BG_DEEP};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部 Hero 区域（渐变背景）
        hero = QFrame()
        hero.setFixedHeight(180)
        hero.setProperty("role", "hero")
        hero_lay = QVBoxLayout(hero)
        hero_lay.setContentsMargins(24, 28, 24, 16)
        hero_lay.setSpacing(4)

        app_name = QLabel("⛓  AiinLink")
        app_name.setProperty("role", "heroTitle")
        app_name.setStyleSheet(
            f"color: {PRIMARY}; font-size: 32px; font-weight: 800; "
            f"letter-spacing: 2px; background: transparent;")
        hero_lay.addWidget(app_name)

        tagline = QLabel("智能网络与服务器诊断工作站")
        tagline.setProperty("role", "heroSubtitle")
        tagline.setStyleSheet(
            f"color: {FG_PRIMARY}; font-size: 14px; font-weight: 500; "
            f"background: transparent;")
        hero_lay.addWidget(tagline)

        hero_lay.addSpacing(6)

        version_lbl = QLabel(
            "版本 1.0.0  Enterprise Edition  ·  © 2024-2026 AiinLink Team")
        version_lbl.setProperty("role", "muted")
        version_lbl.setStyleSheet(
            f"color: {FG_TERTIARY}; font-size: 11px; background: transparent;")
        hero_lay.addWidget(version_lbl)

        layout.addWidget(hero)

        # 主体内容
        body = QFrame()
        body.setStyleSheet(f"background-color: {BG_DEEP}; border: none;")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(20, 16, 20, 16)
        body_lay.setSpacing(10)

        intro = QLabel(
            "AiinLink 是一款面向企业级运维与安全诊断的桌面工作站，集成 SSH 远程终端、"
            "实时监控、日志分析、批量命令执行与多种安全检测能力，帮助运维与安全工程师"
            "在一个统一界面中完成日常诊断、巡检与应急响应工作。")
        intro.setProperty("role", "caption")
        intro.setStyleSheet(
            f"color: {FG_SECONDARY}; font-size: 12px; line-height: 1.6; background: transparent;")
        intro.setWordWrap(True)
        body_lay.addWidget(intro)

        body_lay.addSpacing(4)

        # 功能卡片
        feat_title = QLabel("核心能力")
        feat_title.setProperty("role", "sectionTitle")
        feat_title.setStyleSheet(
            f"color: {PRIMARY}; font-size: 12px; font-weight: 700; "
            f"padding: 4px 0; background: transparent;")
        body_lay.addWidget(feat_title)

        features = [
            ("📊", "实时监控", "CPU/内存/磁盘/网卡流量/系统负载实时采集与可视化", PRIMARY),
            ("📜", "日志分析", "SSH 远端 tail 实时跟踪，关键字高亮与导出", ACCENT_BLUE),
            ("🗂", "资产管理", "主机分组、标签、批量测试，集中管理服务器", ACCENT_PURPLE),
            ("🚀", "批量执行", "多主机并发执行命令，提升运维效率", WARN),
            ("💓", "服务可用性", "HTTP/TCP 周期健康检查与可用率统计", SUCCESS),
            ("🛡", "安全诊断", "漏洞扫描、弱密码检测、SQL/XSS 注入测试", DANGER),
        ]
        for icon, title, desc, color in features:
            card = FeatureCard(icon, title, desc, color)
            body_lay.addWidget(card)

        body_lay.addStretch(1)

        # 技术栈
        tech_lbl = QLabel("技术栈:  Python 3.11  ·  PySide6  ·  paramiko  ·  psutil  ·  requests")
        tech_lbl.setStyleSheet(
            f"color: {FG_TERTIARY}; font-size: 10px; padding: 4px;")
        tech_lbl.setAlignment(Qt.AlignCenter)
        body_lay.addWidget(tech_lbl)

        layout.addWidget(body, 1)

        # 底部按钮
        bottom = QFrame()
        bottom.setFixedHeight(56)
        bottom.setStyleSheet(
            f"background-color: {BG_PANEL}; border-top: 1px solid {BORDER};")
        bottom_lay = QHBoxLayout(bottom)
        bottom_lay.setContentsMargins(16, 8, 16, 8)

        bottom_lay.addStretch(1)

        btn_close = QPushButton("关闭")
        btn_close.setFixedSize(90, 32)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setProperty("role", "primary")
        btn_close.clicked.connect(self.accept)
        bottom_lay.addWidget(btn_close)

        layout.addWidget(bottom)
