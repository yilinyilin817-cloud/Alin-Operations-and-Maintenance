"""
主窗口
IDE 风格布局：左侧工作区（仪表盘+终端标签页）+ 右侧 AI Copilot 面板
"""

import os
import time
from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QTabWidget, QWidget,
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QToolBar, QStatusBar, QInputDialog, QMessageBox,
    QMenu, QLineEdit, QSpinBox, QTextEdit, QComboBox,
    QFileDialog, QDialog, QFormLayout, QDialogButtonBox,
    QGroupBox, QRadioButton, QButtonGroup, QListWidget,
    QListWidgetItem, QTabWidget as QTabWidget2,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QFont, QIcon

from app.dashboard import DashboardWidget
from app.ssh_terminal import SSHTerminalTab
from app.ai_panel import AICopilotPanel
from app.ai_engine import AIEngine, AICompletionWorker
from app.network_probe import (
    PingWorker, PortScanWorker, TracerouteWorker,
    DnsLookupWorker, HttpCheckWorker, WhoisWorker,
    SQLInjectionDetectWorker, XSSDetectWorker,
    DirectoryBusterWorker, SubdomainEnumerationWorker,
    HttpLoadTestWorker, TCPFloodTestWorker,
    SSLCheckerWorker, GeoLocationWorker, VulnerablePortScanWorker,
    ServiceIdentifyWorker, SecurityHeadersWorker, PasswordStrengthWorker, PasswordGeneratorWorker,
    FTPAnonymousWorker, SMBEnumerationWorker, SSHWeakPasswordWorker,
    BannerGrabWorker, ServerInfoWorker, PortEnumerationWorker,
    PluginDownloadWorker,
    # 新增检测 Worker
    TCPPingWorker, HTTPResponseHeadersWorker, DNSRecordsWorker,
    IPv6SupportWorker, MailServerWorker, CORSWorker, CDNWAFWorker,
    WebSocketWorker, PublicIPWorker, MACVendorWorker,
    NetworkQualityWorker, CookieSecurityWorker, HTTPMethodsWorker,
    RDPWorker, TLSInspectionWorker, MTRLikeWorker,
    NTPTimeWorker, SNMPWorker,
)
from app.ssh_config import SSHConfigManager, SSHConnectionProfile
from app.network_capture import open_capture_tab
from app.enterprise_ops import open_enterprise_ops
from app.theme import (
    BG_BASE, BG_DEEP, BG_PANEL, BG_PANEL_HOVER, BG_INPUT, BG_RAISED,
    FG_PRIMARY, FG_SECONDARY, FG_TERTIARY, FG_DISABLED,
    BORDER, BORDER_LIGHT, BORDER_FOCUS,
    PRIMARY, PRIMARY_HOVER, PRIMARY_DARK, PRIMARY_GLOW,
    COMMON_QSS, RADIUS_SM, RADIUS_MD, RADIUS_LG,
    FONT_FAMILY, FONT_MONO, FONT_SIZE_SM, FONT_SIZE_BASE, FONT_SIZE_MD, FONT_SIZE_LG, FONT_SIZE_XL,
    SHADOW_SOFT, SHADOW_MEDIUM,
)
from app.title_bar import CustomTitleBar, FramelessResizer, WindowMover
from app.about_dialog import AboutDialog


class SSHHistoryDialog(QDialog):
    """SSH 连接历史对话框"""

    connect_requested = Signal(object)  # SSHConnectionProfile

    def __init__(self, config_manager: SSHConfigManager, parent=None):
        super().__init__(parent)
        self._config = config_manager
        self.setWindowTitle("SSH 连接历史")
        self.setMinimumSize(500, 400)

        layout = QVBoxLayout(self)

        # 连接历史列表
        self._list = QListWidget()
        self._refresh_list()
        layout.addWidget(self._list)

        # 按钮
        btn_layout = QHBoxLayout()
        self._btn_connect = QPushButton("连接")
        self._btn_connect.clicked.connect(self._on_connect)
        self._btn_delete = QPushButton("删除")
        self._btn_delete.clicked.connect(self._on_delete)
        self._btn_close = QPushButton("关闭")
        self._btn_close.clicked.connect(self.close)

        btn_layout.addWidget(self._btn_connect)
        btn_layout.addWidget(self._btn_delete)
        btn_layout.addStretch()
        btn_layout.addWidget(self._btn_close)
        layout.addLayout(btn_layout)

    def _refresh_list(self):
        """刷新列表"""
        self._list.clear()
        connections = self._config.get_all_connections()
        for profile in connections:
            item = QListWidgetItem()
            status_icon = "✓" if not profile.last_error else "✗"
            last_time = time.strftime("%Y-%m-%d %H:%M", time.localtime(profile.last_connected)) if profile.last_connected else "从未连接"
            item.setText(f"{status_icon} {profile.display_name}  |  {profile.auth_type}  |  连接 {profile.connect_count} 次  |  {last_time}")
            item.setData(Qt.UserRole, profile)
            if profile.last_error:
                item.setForeground(Qt.red)
            self._list.addItem(item)

    def _on_connect(self):
        """连接选中的配置"""
        item = self._list.currentItem()
        if item:
            profile = item.data(Qt.UserRole)
            self.connect_requested.emit(profile)
            self.close()

    def _on_delete(self):
        """删除选中的配置"""
        item = self._list.currentItem()
        if item:
            profile = item.data(Qt.UserRole)
            key = f"{profile.username}@{profile.host}:{profile.port}"
            self._config.delete_connection(key)
            self._refresh_list()


class SSHKeyImportDialog(QDialog):
    """SSH 密钥导入对话框"""

    def __init__(self, config_manager: SSHConfigManager, parent=None):
        super().__init__(parent)
        self._config = config_manager
        self.setWindowTitle("导入 SSH 密钥")
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)

        # 密钥文件选择
        file_group = QGroupBox("选择私钥文件")
        file_layout = QHBoxLayout()
        self._key_path = QLineEdit()
        self._key_path.setPlaceholderText("选择 SSH 私钥文件（id_rsa, id_ed25519 等）")
        file_layout.addWidget(self._key_path)
        self._btn_browse = QPushButton("浏览...")
        self._btn_browse.clicked.connect(self._browse_key)
        file_layout.addWidget(self._btn_browse)
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        # 密钥密码（可选）
        pass_group = QGroupBox("密钥密码（如果私钥有密码保护）")
        pass_layout = QHBoxLayout()
        self._passphrase = QLineEdit()
        self._passphrase.setEchoMode(QLineEdit.Password)
        self._passphrase.setPlaceholderText("可选")
        pass_layout.addWidget(self._passphrase)
        pass_group.setLayout(pass_layout)
        layout.addWidget(pass_group)

        # 已导入的密钥列表
        keys_group = QGroupBox("已导入的密钥")
        keys_layout = QVBoxLayout()
        self._keys_list = QListWidget()
        self._refresh_keys()
        keys_layout.addWidget(self._keys_list)

        btn_key_layout = QHBoxLayout()
        self._btn_delete_key = QPushButton("删除选中")
        self._btn_delete_key.clicked.connect(self._delete_key)
        btn_key_layout.addWidget(self._btn_delete_key)
        btn_key_layout.addStretch()
        keys_layout.addLayout(btn_key_layout)
        keys_group.setLayout(keys_layout)
        layout.addWidget(keys_group)

        # 确定/取消
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_key(self):
        """浏览选择密钥文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 SSH 私钥文件", "",
            "所有文件 (*);;PEM 文件 (*.pem);;密钥文件 (*.key)"
        )
        if path:
            self._key_path.setText(path)

    def _refresh_keys(self):
        """刷新已导入密钥列表"""
        self._keys_list.clear()
        keys = self._config.list_keys()
        for key in keys:
            self._keys_list.addItem(key)

    def _delete_key(self):
        """删除选中的密钥"""
        item = self._keys_list.currentItem()
        if item:
            self._config.delete_key(item.text())
            self._refresh_keys()

    def _on_accept(self):
        """导入密钥"""
        key_path = self._key_path.text().strip()
        if key_path and os.path.exists(key_path):
            try:
                self._config.import_key(key_path)
                self.accept()
            except Exception as e:
                QMessageBox.warning(self, "导入失败", str(e))
        else:
            self.accept()

    def get_passphrase(self) -> str:
        return self._passphrase.text()


class SSHConnectDialog(QWidget):
    """SSH 连接对话框（内嵌式）- 支持密钥登录、连接历史"""

    connect_requested = Signal(str, int, str, str, str, str, str)  # host, port, user, password, key_path, auth_type, key_passphrase

    def __init__(self, config_manager: SSHConfigManager, parent=None):
        super().__init__(parent)
        self._config = config_manager

        # 整体样式：带背景和底部边框分隔线
        self.setStyleSheet(f"""
            SSHConnectDialog {{
                background-color: {BG_DEEP};
                border-bottom: 1px solid {BORDER_LIGHT};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(6)

        # SSH 图标
        ssh_icon = QLabel("⌨")
        ssh_icon.setStyleSheet(f"""
            color: {PRIMARY};
            font-size: 16px;
            padding-right: 2px;
        """)
        layout.addWidget(ssh_icon)

        # 标签通用样式
        label_style = f"""
            color: {FG_TERTIARY};
            font-size: {FONT_SIZE_SM}px;
            font-family: {FONT_FAMILY};
            padding-right: 2px;
        """

        # 输入框通用样式
        input_style = f"""
            QLineEdit, QSpinBox, QComboBox {{
                background-color: {BG_INPUT};
                color: {FG_PRIMARY};
                border: 1px solid {BORDER_LIGHT};
                border-radius: {RADIUS_SM}px;
                padding: 4px 8px;
                font-family: {FONT_FAMILY};
                font-size: {FONT_SIZE_SM}px;
                min-height: 24px;
            }}
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
                border-color: {PRIMARY};
                box-shadow: 0 0 0 2px rgba(78, 205, 196, 0.15);
            }}
            QLineEdit::placeholder {{
                color: {FG_DISABLED};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 18px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {FG_TERTIARY};
                margin-right: 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {BG_DEEP};
                color: {FG_PRIMARY};
                border: 1px solid {BORDER_LIGHT};
                border-radius: {RADIUS_SM}px;
                selection-background-color: {PRIMARY};
                selection-color: #0a1f1d;
                padding: 2px;
            }}
        """

        # 连接历史下拉
        history_label = QLabel("历史:")
        history_label.setStyleSheet(label_style)
        layout.addWidget(history_label)
        self._history_combo = QComboBox()
        self._history_combo.setMinimumWidth(140)
        self._history_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._history_combo.currentIndexChanged.connect(self._on_history_selected)
        self._history_combo.setStyleSheet(input_style)
        layout.addWidget(self._history_combo)
        self._refresh_history()

        host_label = QLabel("主机:")
        host_label.setStyleSheet(label_style)
        layout.addWidget(host_label)
        self._host_input = QLineEdit()
        self._host_input.setPlaceholderText("IP 或域名")
        self._host_input.setFixedWidth(120)
        self._host_input.setStyleSheet(input_style)
        layout.addWidget(self._host_input)

        port_label = QLabel("端口:")
        port_label.setStyleSheet(label_style)
        layout.addWidget(port_label)
        self._port_input = QSpinBox()
        self._port_input.setRange(1, 65535)
        self._port_input.setValue(22)
        self._port_input.setFixedWidth(58)
        self._port_input.setButtonSymbols(QSpinBox.NoButtons)
        self._port_input.setStyleSheet(input_style)
        layout.addWidget(self._port_input)

        user_label = QLabel("用户:")
        user_label.setStyleSheet(label_style)
        layout.addWidget(user_label)
        self._user_input = QLineEdit()
        self._user_input.setPlaceholderText("root")
        self._user_input.setFixedWidth(72)
        self._user_input.setStyleSheet(input_style)
        layout.addWidget(self._user_input)

        # 认证方式选择
        self._auth_combo = QComboBox()
        self._auth_combo.setMinimumWidth(70)
        self._auth_combo.addItems(["密码", "密钥"])
        self._auth_combo.currentIndexChanged.connect(self._on_auth_changed)
        self._auth_combo.setStyleSheet(input_style)
        layout.addWidget(self._auth_combo)

        # 密码输入
        self._pass_input = QLineEdit()
        self._pass_input.setEchoMode(QLineEdit.Password)
        self._pass_input.setPlaceholderText("密码")
        self._pass_input.setFixedWidth(80)
        self._pass_input.setStyleSheet(input_style)
        layout.addWidget(self._pass_input)

        # 密钥选择
        self._key_combo = QComboBox()
        self._key_combo.setMinimumWidth(100)
        self._key_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._key_combo.setVisible(False)
        self._key_combo.setStyleSheet(input_style)
        self._refresh_keys()
        layout.addWidget(self._key_combo)

        self._btn_import_key = QPushButton("导入密钥")
        self._btn_import_key.setMinimumWidth(70)
        self._btn_import_key.setMinimumHeight(26)
        self._btn_import_key.setVisible(False)
        self._btn_import_key.setProperty("role", "ghost")
        self._btn_import_key.clicked.connect(self._import_key)
        layout.addWidget(self._btn_import_key)

        # 连接按钮 - 渐变背景，更突出
        self._btn_connect = QPushButton("▶ 连接")
        self._btn_connect.setMinimumWidth(72)
        self._btn_connect.setMinimumHeight(28)
        self._btn_connect.setCursor(Qt.PointingHandCursor)
        self._btn_connect.setProperty("role", "primary")
        self._btn_connect.clicked.connect(self._on_connect)
        layout.addWidget(self._btn_connect)

        # 历史按钮 - ghost/outline 风格
        self._btn_history = QPushButton("历史")
        self._btn_history.setMinimumWidth(50)
        self._btn_history.setMinimumHeight(28)
        self._btn_history.setCursor(Qt.PointingHandCursor)
        self._btn_history.setProperty("role", "ghost")
        self._btn_history.clicked.connect(self._show_history)
        layout.addWidget(self._btn_history)

        layout.addStretch()

    def _refresh_history(self):
        """刷新连接历史下拉"""
        self._history_combo.blockSignals(True)
        self._history_combo.clear()
        self._history_combo.addItem("-- 选择历史连接 --", None)
        connections = self._config.get_all_connections()
        for profile in connections[:20]:  # 只显示最近20个
            icon = "✓" if not profile.last_error else "✗"
            self._history_combo.addItem(f"{icon} {profile.display_name}", profile)
        self._history_combo.blockSignals(False)

    def _refresh_keys(self):
        """刷新密钥列表"""
        self._key_combo.clear()
        self._key_combo.addItem("-- 选择密钥 --", "")
        keys = self._config.list_keys()
        for key in keys:
            self._key_combo.addItem(key, key)

    def _on_history_selected(self, index):
        """选择历史连接"""
        profile = self._history_combo.currentData()
        if profile:
            self._host_input.setText(profile.host)
            self._port_input.setValue(profile.port)
            self._user_input.setText(profile.username)
            if profile.auth_type == "key":
                self._auth_combo.setCurrentIndex(1)
                # 查找密钥
                key_name = os.path.basename(profile.key_path) if profile.key_path else ""
                idx = self._key_combo.findText(key_name)
                if idx >= 0:
                    self._key_combo.setCurrentIndex(idx)
            else:
                self._auth_combo.setCurrentIndex(0)
                self._pass_input.setText(profile.password)

    def _on_auth_changed(self, index):
        """认证方式改变"""
        is_key = index == 1
        self._pass_input.setVisible(not is_key)
        self._key_combo.setVisible(is_key)
        self._btn_import_key.setVisible(is_key)

    def _import_key(self):
        """导入密钥"""
        dialog = SSHKeyImportDialog(self._config, self)
        if dialog.exec_() == QDialog.Accepted:
            self._refresh_keys()

    def _show_history(self):
        """显示完整历史对话框"""
        dialog = SSHHistoryDialog(self._config, self)
        dialog.connect_requested.connect(self._on_history_connect)
        dialog.exec_()

    def _on_history_connect(self, profile: SSHConnectionProfile):
        """从历史对话框连接"""
        self.connect_requested.emit(
            profile.host, profile.port, profile.username,
            profile.password, profile.key_path,
            profile.auth_type, profile.key_passphrase
        )

    def _on_connect(self):
        host = self._host_input.text().strip()
        if not host:
            return
        port = self._port_input.value()
        user = self._user_input.text().strip() or "root"
        auth_type = "key" if self._auth_combo.currentIndex() == 1 else "password"

        password = ""
        key_path = ""
        key_passphrase = ""

        if auth_type == "key":
            key_name = self._key_combo.currentData()
            if key_name:
                from app.ssh_config import KEYS_DIR
                key_path = os.path.join(KEYS_DIR, key_name)
        else:
            password = self._pass_input.text()

        # 保存连接配置
        profile = SSHConnectionProfile(
            host=host,
            port=port,
            username=user,
            auth_type=auth_type,
            password=password,
            key_path=key_path,
            key_passphrase=key_passphrase,
        )
        self._config.save_connection(profile)

        self.connect_requested.emit(host, port, user, password, key_path, auth_type, key_passphrase)
        self._refresh_history()


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("AiinLink - 智能网络与服务器诊断工作站")
        self.setMinimumSize(1200, 700)
        self.resize(1400, 800)
        # 启用无边框窗口（自定义标题栏）
        self.setWindowFlags(
            Qt.Window
            | Qt.FramelessWindowHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowMinMaxButtonsHint
        )

        # AI 引擎
        self._ai_engine = AIEngine()

        # SSH 配置管理器
        self._ssh_config = SSHConfigManager()

        # 终端标签页列表
        self._terminal_tabs = []

        # 补全工作线程
        self._completion_worker = None

        self._setup_titlebar()
        self._setup_ui()
        self._setup_menubar()
        self._setup_toolbar()
        self._setup_statusbar()

        # 无边框窗口的边缘缩放支持
        self._resizer = FramelessResizer(self)

        # 标题栏拖动支持（事件过滤器模式，不受子控件影响）
        self._mover = WindowMover(self, self._title_bar)

    def menuBar(self):
        """重写 QMainWindow.menuBar()，返回标题栏内嵌的 QMenuBar

        关键：必须先创建标题栏（_setup_titlebar）才能调用此方法，
        否则会触发 QMainWindow 默认创建新的 QMenuBar 并覆盖标题栏。
        """
        if hasattr(self, "_title_bar") and self._title_bar is not None:
            return self._title_bar.menuBar()
        return super().menuBar()

    def _setup_titlebar(self):
        """安装自定义标题栏（无边框窗口）"""
        self._title_bar = CustomTitleBar(self)
        # 标题栏放在主窗口布局中
        # 注意：使用 setMenuWidget 让标题栏在菜单栏位置
        self.setMenuWidget(self._title_bar)

    def _setup_ui(self):
        """设置主界面布局"""
        # 中央分割器
        central_splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(central_splitter)

        # 左侧工作区
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # SSH 连接栏
        self._ssh_connect_bar = SSHConnectDialog(self._ssh_config)
        self._ssh_connect_bar.connect_requested.connect(self._on_ssh_connect)
        left_layout.addWidget(self._ssh_connect_bar)

        # 主标签页 - 改进样式
        self._main_tabs = QTabWidget()
        self._main_tabs.setTabsClosable(True)
        self._main_tabs.tabCloseRequested.connect(self._on_tab_close)
        self._main_tabs.setDocumentMode(True)

        # 仪表盘标签
        self._dashboard = DashboardWidget()
        self._dashboard.request_diagnosis.connect(self._on_diagnosis_requested)
        self._main_tabs.addTab(self._dashboard, "  📊  仪表盘  ")

        left_layout.addWidget(self._main_tabs)
        central_splitter.addWidget(left_widget)

        # 右侧 AI Copilot 面板
        self._ai_panel = AICopilotPanel(self._ai_engine, self._ssh_config)
        self._ai_panel.send_command.connect(self._on_send_command_to_terminal)
        central_splitter.addWidget(self._ai_panel)

        # 设置分割比例
        central_splitter.setSizes([900, 400])
        central_splitter.setStretchFactor(0, 3)
        central_splitter.setStretchFactor(1, 1)

    def _show_tool_category(self, category: str):
        """打开工具菜单对应的工具集（弹出一个分类面板）"""
        if category == "net":
            self._open_tool_panel("🌐 网络工具", [
                ("📡 Ping 探测", self._tool_ping),
                ("🔌 TCP Ping", self._tool_tcp_ping),
                ("🔌 端口扫描", self._tool_port_scan),
                ("🗺 路由追踪", self._tool_traceroute),
                ("🛰 类MTR追踪", self._tool_mtr),
                ("🔍 DNS 查询", self._tool_dns),
                ("📑 扩展DNS记录", self._tool_dns_extended),
                ("🌐 HTTP 检测", self._tool_http),
                ("📑 HTTP响应头", self._tool_http_headers),
                ("🔧 HTTP方法检测", self._tool_http_methods),
                ("🌐 IPv6 支持", self._tool_ipv6_check),
                ("⏱ 网络质量测试", self._tool_network_quality),
                ("📡 公网 IP", self._tool_public_ip),
                ("📋 WHOIS 查询", self._tool_whois),
                ("🕒 NTP 时间", self._tool_ntp),
            ])
        elif category == "security":
            self._open_tool_panel("🛡 安全工具", [
                ("🔒 SSL 证书检测", self._tool_ssl_check),
                ("🔍 TLS 深度检测", self._tool_tls_inspect),
                ("📍 IP 地理位置", self._tool_geo_location),
                ("⚠ 危险端口扫描", self._tool_vuln_port_scan),
                ("🏷 服务识别", self._tool_service_identify),
                ("🛡 HTTP 安全头", self._tool_security_headers),
                ("🍪 Cookie 安全", self._tool_cookie_check),
                ("🌐 CORS 检测", self._tool_cors_check),
                ("🛰 CDN/WAF 检测", self._tool_cdn_waf),
                ("🔑 密码强度检测", self._tool_password_strength),
                ("✨ 生成安全密码", self._tool_password_generate),
                ("💉 SQL注入检测", self._tool_sql_injection),
                ("📄 XSS漏洞检测", self._tool_xss_detect),
                ("📂 目录爆破", self._tool_directory_buster),
                ("🌍 子域名枚举", self._tool_subdomain_enum),
                ("⚡ HTTP压力测试", self._tool_http_load_test),
                ("🌊 TCP洪水测试", self._tool_tcp_flood),
                ("🖥 服务器信息收集", self._tool_server_info),
                ("📧 邮件服务器检测", self._tool_mail_server),
                ("📡 WebSocket 测试", self._tool_websocket),
                ("💳 RDP/VNC 检测", self._tool_rdp_vnc),
                ("🔌 SNMP 检测", self._tool_snmp),
                ("📡 MAC 厂商查询", self._tool_mac_vendor),
                ("📁 FTP匿名检测", self._tool_ftp_anonymous),
                ("📦 SMB服务枚举", self._tool_smb_enum),
                ("🔐 SSH弱密码检测", self._tool_ssh_weak_password),
                ("🏴 服务横幅获取", self._tool_banner_grab),
                ("🔎 端口全量扫描", self._tool_port_enumeration),
                ("🧩 插件管理器", self._tool_plugin_manager),
            ])

    def _open_tool_panel(self, title: str, tools: list):
        """通用工具面板：以按钮网格形式展示工具"""
        # 若已存在同类面板则切换
        for i in range(self._main_tabs.count()):
            w = self._main_tabs.widget(i)
            if getattr(w, "_is_tool_panel", None) == title:
                self._main_tabs.setCurrentIndex(i)
                return
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg._is_tool_panel = title
        dlg.setMinimumSize(720, 480)
        # 渐变背景
        dlg.setStyleSheet(f"""
            QDialog {{
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {BG_DEEP}, stop:1 {BG_BASE});
            }}
        """)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)

        # 标题标签 - 更大字体 + 强调下划线
        title_container = QWidget()
        title_layout = QVBoxLayout(title_container)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(0)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"""
            color: {FG_PRIMARY};
            font-size: {FONT_SIZE_XL}px;
            font-weight: 700;
            font-family: {FONT_FAMILY};
            padding: 4px 0px 0px 0px;
        """)
        title_layout.addWidget(title_lbl)

        # 强调下划线
        accent_line = QWidget()
        accent_line.setFixedHeight(3)
        accent_line.setFixedWidth(60)
        accent_line.setStyleSheet(f"""
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {PRIMARY}, stop:1 transparent);
            border-radius: 1px;
        """)
        title_layout.addWidget(accent_line)
        title_layout.addSpacing(12)

        layout.addWidget(title_container)

        # 网格布局 - 更好的间距
        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        cols = 4

        for i, (name, fn) in enumerate(tools):
            btn = QPushButton(name)
            btn.setMinimumHeight(50)
            btn.setCursor(Qt.PointingHandCursor)
            # 卡片式按钮 + 阴影 + hover PRIMARY 边框发光
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {BG_PANEL};
                    color: {FG_PRIMARY};
                    border: 1px solid {BORDER};
                    border-radius: {RADIUS_MD}px;
                    padding: 10px 14px;
                    font-size: {FONT_SIZE_BASE}px;
                    font-family: {FONT_FAMILY};
                    text-align: left;
                    padding-left: 16px;
                }}
                QPushButton:hover {{
                    background-color: {BG_PANEL_HOVER};
                    border-color: {PRIMARY};
                    color: {PRIMARY};
                    box-shadow: {SHADOW_SOFT};
                }}
                QPushButton:pressed {{
                    background-color: {PRIMARY};
                    color: #0a1f1d;
                    border-color: {PRIMARY};
                }}
            """)
            btn.clicked.connect(lambda checked=False, f=fn: (f(), dlg.close()))
            grid.addWidget(btn, i // cols, i % cols)
        layout.addLayout(grid)
        layout.addStretch(1)

        idx = self._main_tabs.addTab(dlg, title)
        self._main_tabs.setCurrentIndex(idx)

    def _setup_menubar(self):
        """设置顶部菜单栏"""
        menubar = self.menuBar()
        tools_menu = menubar.addMenu("工具(&T)")

        capture_action = QAction("📡 实时抓取", self)
        capture_action.setShortcut("Ctrl+Shift+T")
        capture_action.setStatusTip("打开联网数据实时抓取与查看标签页")
        capture_action.triggered.connect(lambda: open_capture_tab(self))
        tools_menu.addAction(capture_action)

        tools_menu.addSeparator()

        new_term_action = QAction("新建终端", self)
        new_term_action.setShortcut("Ctrl+N")
        new_term_action.triggered.connect(self._new_terminal_tab)
        tools_menu.addAction(new_term_action)

        ops_action = QAction("🛠 企业级运维控制台", self)
        ops_action.setShortcut("Ctrl+E")
        ops_action.setStatusTip("打开资产管理、实时监控、日志分析、批量执行")
        ops_action.triggered.connect(self._open_enterprise_ops)
        tools_menu.addAction(ops_action)

        toggle_ai_action = QAction("切换 AI 面板", self)
        toggle_ai_action.setShortcut("Ctrl+I")
        toggle_ai_action.triggered.connect(self._toggle_ai_panel)
        tools_menu.addAction(toggle_ai_action)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")

        about_action = QAction("💡 关于 AiinLink", self)
        about_action.setShortcut("F1")
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_toolbar(self):
        """设置工具栏"""
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # 新建终端
        new_term_action = QAction("新建终端", self)
        new_term_action.triggered.connect(self._new_terminal_tab)
        toolbar.addAction(new_term_action)

        toolbar.addSeparator()

        # 网络工具
        net_menu = QMenu("网络工具", self)

        ping_action = net_menu.addAction("Ping 探测")
        ping_action.triggered.connect(self._tool_ping)

        port_action = net_menu.addAction("端口扫描")
        port_action.triggered.connect(self._tool_port_scan)

        trace_action = net_menu.addAction("路由追踪")
        trace_action.triggered.connect(self._tool_traceroute)

        net_menu.addSeparator()

        dns_action = net_menu.addAction("DNS 查询")
        dns_action.triggered.connect(self._tool_dns)

        http_action = net_menu.addAction("HTTP 检测")
        http_action.triggered.connect(self._tool_http)

        whois_action = net_menu.addAction("WHOIS 查询")
        whois_action.triggered.connect(self._tool_whois)

        net_btn = QPushButton("🔧  网络工具  ▾")
        net_btn.setCursor(Qt.PointingHandCursor)
        net_btn.setMinimumHeight(26)
        net_btn.setProperty("role", "dropdown")
        net_btn.setMenu(net_menu)
        toolbar.addWidget(net_btn)

        toolbar.addSeparator()

        # 安全工具
        security_menu = QMenu("安全工具", self)

        ssl_action = security_menu.addAction("SSL 证书检测")
        ssl_action.triggered.connect(self._tool_ssl_check)

        geo_action = security_menu.addAction("IP 地理位置")
        geo_action.triggered.connect(self._tool_geo_location)

        vuln_port_action = security_menu.addAction("危险端口扫描")
        vuln_port_action.triggered.connect(self._tool_vuln_port_scan)

        service_action = security_menu.addAction("服务识别")
        service_action.triggered.connect(self._tool_service_identify)

        security_menu.addSeparator()

        headers_action = security_menu.addAction("HTTP 安全头")
        headers_action.triggered.connect(self._tool_security_headers)

        pwd_strength_action = security_menu.addAction("密码强度检测")
        pwd_strength_action.triggered.connect(self._tool_password_strength)

        pwd_gen_action = security_menu.addAction("生成安全密码")
        pwd_gen_action.triggered.connect(self._tool_password_generate)

        security_menu.addSeparator()

        # 渗透测试工具
        sql_action = security_menu.addAction("SQL注入检测")
        sql_action.triggered.connect(self._tool_sql_injection)

        xss_action = security_menu.addAction("XSS漏洞检测")
        xss_action.triggered.connect(self._tool_xss_detect)

        dir_bust_action = security_menu.addAction("目录爆破")
        dir_bust_action.triggered.connect(self._tool_directory_buster)

        subdomain_action = security_menu.addAction("子域名枚举")
        subdomain_action.triggered.connect(self._tool_subdomain_enum)

        security_menu.addSeparator()

        # 压力测试工具
        http_load_action = security_menu.addAction("HTTP压力测试")
        http_load_action.triggered.connect(self._tool_http_load_test)

        tcp_flood_action = security_menu.addAction("TCP洪水测试")
        tcp_flood_action.triggered.connect(self._tool_tcp_flood)

        security_menu.addSeparator()

        # 服务器测试工具
        server_info_action = security_menu.addAction("服务器信息收集")
        server_info_action.triggered.connect(self._tool_server_info)

        ftp_anon_action = security_menu.addAction("FTP匿名检测")
        ftp_anon_action.triggered.connect(self._tool_ftp_anonymous)

        smb_action = security_menu.addAction("SMB服务枚举")
        smb_action.triggered.connect(self._tool_smb_enum)

        ssh_weak_action = security_menu.addAction("SSH弱密码检测")
        ssh_weak_action.triggered.connect(self._tool_ssh_weak_password)

        banner_action = security_menu.addAction("服务横幅获取")
        banner_action.triggered.connect(self._tool_banner_grab)

        port_enum_action = security_menu.addAction("端口全量扫描")
        port_enum_action.triggered.connect(self._tool_port_enumeration)

        security_menu.addSeparator()

        # 插件管理
        plugin_action = security_menu.addAction("插件管理器")
        plugin_action.triggered.connect(self._tool_plugin_manager)

        security_btn = QPushButton("🛡  安全工具  ▾")
        security_btn.setCursor(Qt.PointingHandCursor)
        security_btn.setMinimumHeight(26)
        security_btn.setProperty("role", "dropdown")
        security_btn.setMenu(security_menu)
        toolbar.addWidget(security_btn)

        toolbar.addSeparator()

        # 企业级运维
        ops_action_toolbar = QAction("🛠 运维控制台", self)
        ops_action_toolbar.setStatusTip("打开企业级运维控制台 (Ctrl+E)")
        ops_action_toolbar.triggered.connect(self._open_enterprise_ops)
        toolbar.addAction(ops_action_toolbar)

        toolbar.addSeparator()

        # 切换 AI 面板
        toggle_ai_action = QAction("切换AI面板", self)
        toggle_ai_action.triggered.connect(self._toggle_ai_panel)
        toolbar.addAction(toggle_ai_action)

    def _setup_statusbar(self):
        """设置状态栏"""
        self._status_label = QLabel("就绪")
        self._status_label.setProperty("role", "muted")
        self.statusBar().addWidget(self._status_label)

    # ---- SSH 终端管理 ----

    def _on_ssh_connect(self, host: str, port: int, username: str, password: str,
                        key_path: str, auth_type: str = "password", key_passphrase: str = ""):
        """SSH 连接请求"""
        tab = SSHTerminalTab(self._ssh_config)
        tab.connect_to_host(host, port, username, password, key_path, auth_type, key_passphrase)

        # 连接 Ghost Text 补全信号
        tab.terminal.completion_requested.connect(self._on_completion_requested)

        idx = self._main_tabs.addTab(tab, f"{username}@{host}")
        self._main_tabs.setCurrentIndex(idx)
        self._terminal_tabs.append(tab)

        self._status_label.setText(f"正在连接 {host}:{port}...")

    def _new_terminal_tab(self):
        """新建本地终端标签"""
        tab = SSHTerminalTab()
        tab.start_local_shell()
        idx = self._main_tabs.addTab(tab, "本地终端")
        self._main_tabs.setCurrentIndex(idx)
        self._terminal_tabs.append(tab)

    def _on_tab_close(self, index: int):
        """关闭标签页"""
        widget = self._main_tabs.widget(index)
        if widget == self._dashboard:
            return  # 不允许关闭仪表盘

        if isinstance(widget, SSHTerminalTab):
            widget.disconnect()
            if widget in self._terminal_tabs:
                self._terminal_tabs.remove(widget)

        # 关闭企业级运维控制台时停止其后台任务
        if getattr(widget, "_is_enterprise_ops", False) and hasattr(widget, "stop_all"):
            try:
                widget.stop_all()
            except Exception:
                pass

        self._main_tabs.removeTab(index)

    # ---- 网络工具 ----

    def _tool_ping(self):
        """Ping 探测"""
        host, ok = QInputDialog.getText(self, "Ping 探测", "目标主机:")
        if ok and host.strip():
            self._status_label.setText(f"正在 Ping {host}...")

            # 在新标签页中显示结果
            result_widget = QTextEdit_style()
            result_widget.setReadOnly(True)
            idx = self._main_tabs.addTab(result_widget, f"Ping: {host}")
            self._main_tabs.setCurrentIndex(idx)

            self._ping_worker = PingWorker(host.strip())
            self._ping_worker.result_ready.connect(
                lambda h, r, l, o: self._on_ping_result(result_widget, h, r, l, o)
            )
            self._ping_worker.start()

    def _on_ping_result(self, widget, host, reachable, latency, output):
        if reachable:
            widget.append(f'<span style="color:#4ecdc4;">Ping {host} 可达</span>，平均延迟: {latency:.1f}ms')
        else:
            widget.append(f'<span style="color:#ff6b6b;">Ping {host} 不可达</span>')
        widget.append(f'<pre style="color:#aaa;">{output}</pre>')
        self._status_label.setText("Ping 完成")

    def _tool_port_scan(self):
        """端口扫描"""
        host, ok = QInputDialog.getText(self, "端口扫描", "目标主机:")
        if ok and host.strip():
            self._status_label.setText(f"正在扫描 {host} 端口...")

            result_widget = QTextEdit_style()
            result_widget.setReadOnly(True)
            idx = self._main_tabs.addTab(result_widget, f"端口: {host}")
            self._main_tabs.setCurrentIndex(idx)

            self._port_worker = PortScanWorker(host.strip())
            self._port_worker.progress.connect(
                lambda c, t: self._status_label.setText(f"端口扫描进度: {c}/{t}")
            )
            self._port_worker.result_ready.connect(
                lambda h, r: self._on_port_scan_result(result_widget, h, r)
            )
            self._port_worker.error.connect(
                lambda e: self._on_port_scan_error(result_widget, e)
            )
            self._port_worker.start()

    def _on_port_scan_result(self, widget, host, results):
        from app.network_probe import get_common_ports_description
        port_desc = get_common_ports_description()

        widget.append(f'<span style="color:#4ecdc4;">端口扫描结果 - {host}</span>\n')
        open_ports = [p for p, is_open in results.items() if is_open]
        closed_ports = [p for p, is_open in results.items() if not is_open]

        for port in sorted(open_ports):
            desc = port_desc.get(port, "未知")
            widget.append(f'  <span style="color:#4ecdc4;">● {port}</span> ({desc}) - <span style="color:#4ecdc4;">开放</span>')

        widget.append(f'\n共 {len(open_ports)} 个端口开放，{len(closed_ports)} 个端口关闭')
        self._status_label.setText("端口扫描完成")

    def _on_port_scan_error(self, widget, error_msg):
        widget.append(f'<span style="color:#ff6b6b;">端口扫描出错: {error_msg}</span>')
        self._status_label.setText("端口扫描失败")

    def _tool_traceroute(self):
        """路由追踪"""
        host, ok = QInputDialog.getText(self, "路由追踪", "目标主机:")
        if ok and host.strip():
            self._status_label.setText(f"正在追踪到 {host} 的路由...")

            result_widget = QTextEdit_style()
            result_widget.setReadOnly(True)
            idx = self._main_tabs.addTab(result_widget, f"路由: {host}")
            self._main_tabs.setCurrentIndex(idx)

            self._trace_worker = TracerouteWorker(host.strip())
            self._trace_worker.hop_found.connect(
                lambda n, ip, lat: self._on_traceroute_hop(result_widget, n, ip, lat)
            )
            self._trace_worker.finished_signal.connect(
                lambda s: self._status_label.setText("路由追踪完成")
            )
            self._trace_worker.start()

    def _on_traceroute_hop(self, widget, hop_num, ip, latency):
        if latency >= 0:
            widget.append(f'  <span style="color:#aaa;">{hop_num:>3}</span>  '
                         f'<span style="color:#4ecdc4;">{ip:<18}</span>  '
                         f'<span style="color:#ffaa00;">{latency:.1f}ms</span>')
        else:
            widget.append(f'  <span style="color:#aaa;">{hop_num:>3}</span>  '
                         f'<span style="color:#ff6b6b;">{ip}</span>')

    def _tool_dns(self):
        """DNS 查询"""
        host, ok = QInputDialog.getText(self, "DNS 查询", "域名或主机:")
        if ok and host.strip():
            self._status_label.setText(f"正在查询 DNS {host}...")

            result_widget = QTextEdit_style()
            result_widget.setReadOnly(True)
            idx = self._main_tabs.addTab(result_widget, f"DNS: {host}")
            self._main_tabs.setCurrentIndex(idx)

            self._dns_worker = DnsLookupWorker(host.strip())
            self._dns_worker.result_ready.connect(
                lambda h, r, e: self._on_dns_result(result_widget, h, r, e)
            )
            self._dns_worker.start()

    def _on_dns_result(self, widget, host, records, error):
        widget.append(f'<span style="color:#4ecdc4;">DNS 查询结果 - {host}</span>\n')
        if error and not records:
            widget.append(f'<span style="color:#ff6b6b;">查询失败: {error}</span>')
        else:
            for rtype, value in records:
                widget.append(f'  <span style="color:#ffaa00;">{rtype}</span>  {value}')
        self._status_label.setText("DNS 查询完成")

    def _tool_http(self):
        """HTTP 检测"""
        url, ok = QInputDialog.getText(self, "HTTP 检测", "URL:", text="https://")
        if ok and url.strip():
            self._status_label.setText(f"正在检测 {url}...")

            result_widget = QTextEdit_style()
            result_widget.setReadOnly(True)
            idx = self._main_tabs.addTab(result_widget, f"HTTP: {url}")
            self._main_tabs.setCurrentIndex(idx)

            self._http_worker = HttpCheckWorker(url.strip())
            self._http_worker.result_ready.connect(
                lambda u, s, h, e: self._on_http_result(result_widget, u, s, h, e)
            )
            self._http_worker.start()

    def _on_http_result(self, widget, url, status, headers, error):
        widget.append(f'<span style="color:#4ecdc4;">HTTP 检测结果 - {url}</span>\n')
        if error:
            widget.append(f'<span style="color:#ff6b6b;">请求失败: {error}</span>')
        else:
            color = "#4ecdc4" if 200 <= status < 300 else "#ffaa00" if status < 400 else "#ff6b6b"
            widget.append(f'  <span style="color:{color};">状态码: {status}</span>')
            widget.append(f'\n<span style="color:#888;">响应头:</span>')
            widget.append(f'<pre style="color:#aaa;">{headers}</pre>')
        self._status_label.setText("HTTP 检测完成")

    def _tool_whois(self):
        """WHOIS 查询"""
        domain, ok = QInputDialog.getText(self, "WHOIS 查询", "域名:")
        if ok and domain.strip():
            self._status_label.setText(f"正在查询 WHOIS {domain}...")

            result_widget = QTextEdit_style()
            result_widget.setReadOnly(True)
            idx = self._main_tabs.addTab(result_widget, f"WHOIS: {domain}")
            self._main_tabs.setCurrentIndex(idx)

            self._whois_worker = WhoisWorker(domain.strip())
            self._whois_worker.result_ready.connect(
                lambda d, o, e: self._on_whois_result(result_widget, d, o, e)
            )
            self._whois_worker.start()

    def _on_whois_result(self, widget, domain, output, error):
        widget.append(f'<span style="color:#4ecdc4;">WHOIS 查询结果 - {domain}</span>\n')
        if error:
            widget.append(f'<span style="color:#ff6b6b;">查询失败: {error}</span>')
        else:
            widget.append(f'<pre style="color:#aaa;">{output}</pre>')
        self._status_label.setText("WHOIS 查询完成")

    # ---- 安全工具 ----

    def _tool_ssl_check(self):
        """SSL 证书检测"""
        host, ok = QInputDialog.getText(self, "SSL 证书检测", "目标主机:", text="example.com")
        if ok and host.strip():
            self._status_label.setText(f"正在检测 SSL 证书 {host}...")

            result_widget = QTextEdit_style()
            result_widget.setReadOnly(True)
            idx = self._main_tabs.addTab(result_widget, f"SSL: {host}")
            self._main_tabs.setCurrentIndex(idx)

            self._ssl_worker = SSLCheckerWorker(host.strip())
            self._ssl_worker.result_ready.connect(
                lambda h, info, e: self._on_ssl_check_result(result_widget, h, info, e)
            )
            self._ssl_worker.start()

    def _on_ssl_check_result(self, widget, host, cert_info, error):
        widget.append(f'<span style="color:#4ecdc4;">SSL 证书检测结果 - {host}</span>\n')
        if error:
            widget.append(f'<span style="color:#ff6b6b;">检测失败: {error}</span>')
        elif cert_info.get("errors"):
            for err in cert_info["errors"]:
                widget.append(f'<span style="color:#ff6b6b;">{err}</span>')
        else:
            subject = cert_info.get("subject", {})
            issuer = cert_info.get("issuer", {})
            
            widget.append(f'  <span style="color:#ffaa00;">版本</span>: {cert_info.get("version", "N/A")}')
            widget.append(f'  <span style="color:#ffaa00;">序列号</span>: {cert_info.get("serial_number", "N/A")}')
            widget.append(f'  <span style="color:#ffaa00;">颁发者</span>: {issuer.get("organizationName", "N/A")}')
            widget.append(f'  <span style="color:#ffaa00;">主题</span>: {subject.get("commonName", "N/A")}')
            widget.append(f'  <span style="color:#ffaa00;">有效期从</span>: {cert_info.get("not_before", "N/A")}')
            widget.append(f'  <span style="color:#ffaa00;">有效期至</span>: {cert_info.get("not_after", "N/A")}')
            widget.append(f'  <span style="color:#ffaa00;">公钥算法</span>: {cert_info.get("public_key_algorithm", "N/A")}')
            widget.append(f'  <span style="color:#ffaa00;">公钥长度</span>: {cert_info.get("public_key_size", "N/A")} bits')
            widget.append(f'  <span style="color:#ffaa00;">签名算法</span>: {cert_info.get("signature_algorithm", "N/A")}')
            widget.append(f'  <span style="color:#ffaa00;">TLS 版本</span>: {cert_info.get("tls_version", "N/A")}')
            widget.append(f'  <span style="color:#ffaa00;">密码套件</span>: {cert_info.get("cipher_suite", "N/A")}')
            
            days = cert_info.get("days_until_expiry", 0)
            if cert_info.get("expired"):
                widget.append(f'  <span style="color:#ff6b6b;">证书已过期!</span>')
            elif days < 30:
                widget.append(f'  <span style="color:#ffaa00;">证书将在 {days} 天后过期</span>')
            else:
                widget.append(f'  <span style="color:#4ecdc4;">证书有效期还有 {days} 天</span>')
        self._status_label.setText("SSL 证书检测完成")

    def _tool_geo_location(self):
        """IP 地理位置查询"""
        ip, ok = QInputDialog.getText(self, "IP 地理位置", "目标 IP 地址:", text="8.8.8.8")
        if ok and ip.strip():
            self._status_label.setText(f"正在查询 IP 地理位置 {ip}...")

            result_widget = QTextEdit_style()
            result_widget.setReadOnly(True)
            idx = self._main_tabs.addTab(result_widget, f"IP: {ip}")
            self._main_tabs.setCurrentIndex(idx)

            self._geo_worker = GeoLocationWorker(ip.strip())
            self._geo_worker.result_ready.connect(
                lambda ip, info, e: self._on_geo_result(result_widget, ip, info, e)
            )
            self._geo_worker.start()

    def _on_geo_result(self, widget, ip, info, error):
        widget.append(f'<span style="color:#4ecdc4;">IP 地理位置查询 - {ip}</span>\n')
        if error:
            widget.append(f'<span style="color:#ff6b6b;">查询失败: {error}</span>')
        elif info.get("error"):
            widget.append(f'<span style="color:#ff6b6b;">{info["error"]}</span>')
        else:
            widget.append(f'  <span style="color:#ffaa00;">国家</span>: {info.get("country", "未知")}')
            widget.append(f'  <span style="color:#ffaa00;">地区</span>: {info.get("region", "未知")}')
            widget.append(f'  <span style="color:#ffaa00;">城市</span>: {info.get("city", "未知")}')
            widget.append(f'  <span style="color:#ffaa00;">ISP</span>: {info.get("isp", "未知")}')
            widget.append(f'  <span style="color:#ffaa00;">组织</span>: {info.get("organization", "未知")}')
            if info.get("latitude") and info.get("longitude"):
                widget.append(f'  <span style="color:#ffaa00;">坐标</span>: {info["latitude"]}, {info["longitude"]}')
        self._status_label.setText("IP 地理位置查询完成")

    def _tool_vuln_port_scan(self):
        """危险端口扫描"""
        host, ok = QInputDialog.getText(self, "危险端口扫描", "目标主机:")
        if ok and host.strip():
            self._status_label.setText(f"正在扫描危险端口 {host}...")

            result_widget = QTextEdit_style()
            result_widget.setReadOnly(True)
            idx = self._main_tabs.addTab(result_widget, f"危险端口: {host}")
            self._main_tabs.setCurrentIndex(idx)

            self._vuln_worker = VulnerablePortScanWorker(host.strip())
            self._vuln_worker.result_ready.connect(
                lambda h, results, e: self._on_vuln_port_result(result_widget, h, results, e)
            )
            self._vuln_worker.start()

    def _on_vuln_port_result(self, widget, host, results, error):
        widget.append(f'<span style="color:#4ecdc4;">危险端口扫描结果 - {host}</span>\n')
        if error:
            widget.append(f'<span style="color:#ff6b6b;">扫描失败: {error}</span>')
        else:
            open_count = 0
            for port, desc, is_open in results:
                if is_open:
                    open_count += 1
                    widget.append(f'  <span style="color:#ff6b6b;">● {port}</span> {desc} - <span style="color:#ff6b6b;">开放</span>')
                else:
                    widget.append(f'  <span style="color:#aaa;">○ {port}</span> {desc} - <span style="color:#4ecdc4;">关闭</span>')
            
            if open_count > 0:
                widget.append(f'\n<span style="color:#ffaa00;">警告: 发现 {open_count} 个危险端口开放，建议关闭或限制访问</span>')
            else:
                widget.append(f'\n<span style="color:#4ecdc4;">所有危险端口均已关闭</span>')
        self._status_label.setText("危险端口扫描完成")

    def _tool_service_identify(self):
        """服务识别"""
        host, ok = QInputDialog.getText(self, "服务识别", "目标主机:")
        if ok and host.strip():
            self._status_label.setText(f"正在识别服务 {host}...")

            result_widget = QTextEdit_style()
            result_widget.setReadOnly(True)
            idx = self._main_tabs.addTab(result_widget, f"服务识别: {host}")
            self._main_tabs.setCurrentIndex(idx)

            self._service_worker = ServiceIdentifyWorker(host.strip())
            self._service_worker.progress.connect(
                lambda c, t: self._status_label.setText(f"服务识别进度: {c}/{t}")
            )
            self._service_worker.result_ready.connect(
                lambda h, results, e: self._on_service_result(result_widget, h, results, e)
            )
            self._service_worker.start()

    def _on_service_result(self, widget, host, results, error):
        widget.append(f'<span style="color:#4ecdc4;">服务识别结果 - {host}</span>\n')
        if error:
            widget.append(f'<span style="color:#ff6b6b;">识别失败: {error}</span>')
        elif not results:
            widget.append(f'<span style="color:#aaa;">未发现开放端口或无法识别服务</span>')
        else:
            for port, service, banner in results:
                widget.append(f'  <span style="color:#4ecdc4;">● {port}</span> {service}')
                if banner:
                    banner_safe = banner.replace("<", "&lt;").replace(">", "&gt;")[:100]
                    widget.append(f'    <span style="color:#888;">横幅: {banner_safe}</span>')
        self._status_label.setText("服务识别完成")

    def _tool_security_headers(self):
        """HTTP 安全头分析"""
        url, ok = QInputDialog.getText(self, "HTTP 安全头", "URL:", text="https://")
        if ok and url.strip():
            self._status_label.setText(f"正在分析安全头 {url}...")

            result_widget = QTextEdit_style()
            result_widget.setReadOnly(True)
            idx = self._main_tabs.addTab(result_widget, f"安全头: {url}")
            self._main_tabs.setCurrentIndex(idx)

            self._headers_worker = SecurityHeadersWorker(url.strip())
            self._headers_worker.result_ready.connect(
                lambda u, info, e: self._on_headers_result(result_widget, u, info, e)
            )
            self._headers_worker.start()

    def _on_headers_result(self, widget, url, headers_info, error):
        widget.append(f'<span style="color:#4ecdc4;">HTTP 安全头分析 - {url}</span>\n')
        if error:
            widget.append(f'<span style="color:#ff6b6b;">分析失败: {error}</span>')
        elif "error" in headers_info:
            widget.append(f'<span style="color:#ff6b6b;">{headers_info["error"][0]}</span>')
        else:
            present_count = 0
            missing_count = 0
            
            header_descriptions = {
                "Strict-Transport-Security": "HSTS - 强制 HTTPS",
                "X-Content-Type-Options": "防止 MIME 类型混淆",
                "X-Frame-Options": "防止点击劫持",
                "X-XSS-Protection": "XSS 防护",
                "Content-Security-Policy": "内容安全策略",
                "Referrer-Policy": "Referrer 策略",
                "Permissions-Policy": "权限策略",
                "Cross-Origin-Opener-Policy": "COOP",
                "Cross-Origin-Embedder-Policy": "COEP",
            }
            
            for header_name, (value, status) in headers_info.items():
                desc = header_descriptions.get(header_name, header_name)
                if status == "存在":
                    present_count += 1
                    widget.append(f'  <span style="color:#4ecdc4;">✓ {desc}</span>')
                else:
                    missing_count += 1
                    widget.append(f'  <span style="color:#ff6b6b;">✗ {desc}</span>')
            
            widget.append(f'\n<span style="color:#ffaa00;">检测到 {present_count} 个安全头，缺失 {missing_count} 个</span>')
            if missing_count > 0:
                widget.append(f'<span style="color:#ffaa00;">建议添加缺失的安全头以提高网站安全性</span>')
        self._status_label.setText("HTTP 安全头分析完成")

    def _tool_password_strength(self):
        """密码强度检测"""
        password, ok = QInputDialog.getText(self, "密码强度检测", "输入密码:", echo=QLineEdit.Password)
        if ok and password.strip():
            self._status_label.setText("正在分析密码强度...")

            result_widget = QTextEdit_style()
            result_widget.setReadOnly(True)
            idx = self._main_tabs.addTab(result_widget, "密码强度检测")
            self._main_tabs.setCurrentIndex(idx)

            self._pwd_worker = PasswordStrengthWorker(password.strip())
            self._pwd_worker.result_ready.connect(
                lambda p, score, level, sugg: self._on_pwd_strength_result(result_widget, score, level, sugg)
            )
            self._pwd_worker.start()

    def _on_pwd_strength_result(self, widget, score, level, suggestions):
        widget.append(f'<span style="color:#4ecdc4;">密码强度检测结果</span>\n')
        
        # 强度颜色
        if score >= 90:
            color = "#4ecdc4"
        elif score >= 70:
            color = "#ffaa00"
        elif score >= 50:
            color = "#ffcc00"
        else:
            color = "#ff6b6b"
        
        widget.append(f'  <span style="color:{color}; font-size:14px; font-weight:bold;">强度等级: {level}</span>')
        widget.append(f'  <span style="color:{color}; font-size:14px; font-weight:bold;">分数: {score}/100</span>')
        
        # 进度条
        widget.append(f'  <span style="color:#888;">进度: </span>')
        widget.append(f'  <div style="background-color:#2d2d2d; height:10px; border-radius:5px;">')
        widget.append(f'    <div style="background-color:{color}; height:100%; width:{score}%; border-radius:5px;"></div>')
        widget.append(f'  </div>')
        
        if suggestions:
            widget.append(f'\n<span style="color:#ffaa00;">建议:</span>')
            for suggestion in suggestions:
                widget.append(f'  • {suggestion}')
        else:
            widget.append(f'\n<span style="color:#4ecdc4;">密码强度良好，无需改进</span>')
        
        self._status_label.setText("密码强度检测完成")

    def _tool_password_generate(self):
        """生成安全密码"""
        length, ok = QInputDialog.getInt(self, "生成安全密码", "密码长度:", value=16, min=8, max=64)
        if ok:
            result_widget = QTextEdit_style()
            result_widget.setReadOnly(True)
            idx = self._main_tabs.addTab(result_widget, "生成密码")
            self._main_tabs.setCurrentIndex(idx)

            self._pwd_gen_worker = PasswordGeneratorWorker(length)
            self._pwd_gen_worker.result_ready.connect(
                lambda pwd: self._on_pwd_gen_result(result_widget, pwd)
            )
            self._pwd_gen_worker.start()

    def _on_pwd_gen_result(self, widget, password):
        widget.append(f'<span style="color:#4ecdc4;">生成的安全密码</span>\n')
        if password:
            widget.append(f'<span style="color:#ffaa00; font-family:Consolas; font-size:14px; font-weight:bold;">{password}</span>')
            widget.append(f'\n<span style="color:#888;">提示: 请妥善保存此密码，系统不会保存您的密码</span>')
        else:
            widget.append(f'<span style="color:#ff6b6b;">密码生成失败</span>')
        self._status_label.setText("密码生成完成")

    # ---- 渗透测试工具 ----

    def _tool_sql_injection(self):
        """SQL注入检测"""
        url, ok = QInputDialog.getText(self, "SQL注入检测", "目标URL（包含参数）:", text="http://example.com/test.php?id=")
        if ok and url.strip():
            param_name, ok2 = QInputDialog.getText(self, "SQL注入检测", "参数名:", text="id")
            if ok2 and param_name.strip():
                self._status_label.setText("正在检测SQL注入漏洞...")

                result_widget = QTextEdit_style()
                result_widget.setReadOnly(True)
                idx = self._main_tabs.addTab(result_widget, "SQL注入检测")
                self._main_tabs.setCurrentIndex(idx)

                self._sql_worker = SQLInjectionDetectWorker(url.strip(), param_name.strip())
                self._sql_worker.result_ready.connect(
                    lambda u, r, e: self._on_sql_injection_result(result_widget, u, r, e)
                )
                self._sql_worker.start()

    def _on_sql_injection_result(self, widget, url, results, error):
        widget.append(f'<span style="color:#4ecdc4;">SQL注入检测结果 - {url}</span>\n')
        if error:
            widget.append(f'<span style="color:#ff6b6b;">检测失败: {error}</span>')
        else:
            vulnerable_count = sum(1 for r in results if r.get("vulnerable"))
            widget.append(f'<span style="color:#{"#ff6b6b" if vulnerable_count else "#4ecdc4"};">'
                         f'发现 {vulnerable_count} 个可能存在SQL注入的payload</span>\n')
            
            for r in results:
                color = "#ff6b6b" if r.get("vulnerable") else "#888"
                widget.append(f'  <span style="color:{color};">{"[漏洞]" if r.get("vulnerable") else "[安全]"} '
                             f'{r.get("payload")} - 状态: {r.get("status_code")}, '
                             f'响应时间: {r.get("response_time")}, '
                             f'检测指标: {r.get("indicator")}</span>')
        self._status_label.setText("SQL注入检测完成")

    def _tool_xss_detect(self):
        """XSS漏洞检测"""
        url, ok = QInputDialog.getText(self, "XSS漏洞检测", "目标URL（包含参数）:", text="http://example.com/test.php?input=")
        if ok and url.strip():
            param_name, ok2 = QInputDialog.getText(self, "XSS漏洞检测", "参数名:", text="input")
            if ok2 and param_name.strip():
                self._status_label.setText("正在检测XSS漏洞...")

                result_widget = QTextEdit_style()
                result_widget.setReadOnly(True)
                idx = self._main_tabs.addTab(result_widget, "XSS检测")
                self._main_tabs.setCurrentIndex(idx)

                self._xss_worker = XSSDetectWorker(url.strip(), param_name.strip())
                self._xss_worker.result_ready.connect(
                    lambda u, r, e: self._on_xss_result(result_widget, u, r, e)
                )
                self._xss_worker.start()

    def _on_xss_result(self, widget, url, results, error):
        widget.append(f'<span style="color:#4ecdc4;">XSS漏洞检测结果 - {url}</span>\n')
        if error:
            widget.append(f'<span style="color:#ff6b6b;">检测失败: {error}</span>')
        else:
            vulnerable_count = sum(1 for r in results if r.get("vulnerable"))
            widget.append(f'<span style="color:#{"#ff6b6b" if vulnerable_count else "#4ecdc4"};">'
                         f'发现 {vulnerable_count} 个可能存在XSS的payload</span>\n')
            
            for r in results:
                color = "#ff6b6b" if r.get("vulnerable") else "#888"
                widget.append(f'  <span style="color:{color};">{"[漏洞]" if r.get("vulnerable") else "[安全]"} '
                             f'{r.get("payload")}</span>')
        self._status_label.setText("XSS检测完成")

    def _tool_directory_buster(self):
        """目录爆破"""
        url, ok = QInputDialog.getText(self, "目录爆破", "目标URL:", text="http://example.com/")
        if ok and url.strip():
            self._status_label.setText("正在进行目录爆破...")

            result_widget = QTextEdit_style()
            result_widget.setReadOnly(True)
            idx = self._main_tabs.addTab(result_widget, "目录爆破")
            self._main_tabs.setCurrentIndex(idx)

            self._dir_bust_worker = DirectoryBusterWorker(url.strip())
            self._dir_bust_worker.result_ready.connect(
                lambda u, r, e: self._on_directory_buster_result(result_widget, u, r, e)
            )
            self._dir_bust_worker.start()

    def _on_directory_buster_result(self, widget, url, results, error):
        widget.append(f'<span style="color:#4ecdc4;">目录爆破结果 - {url}</span>\n')
        if error:
            widget.append(f'<span style="color:#ff6b6b;">检测失败: {error}</span>')
        else:
            widget.append(f'<span style="color:#4ecdc4;">发现 {len(results)} 个有效路径</span>\n')
            
            for r in results:
                color = "#4ecdc4" if r.get("status_code") == 200 else "#ffaa00" if r.get("status_code") == 403 else "#aaa"
                widget.append(f'  <span style="color:{color};">[{r.get("status_code")}] '
                             f'{r.get("path")} - {r.get("type")}</span>')
        self._status_label.setText("目录爆破完成")

    def _tool_subdomain_enum(self):
        """子域名枚举"""
        domain, ok = QInputDialog.getText(self, "子域名枚举", "目标域名:", text="example.com")
        if ok and domain.strip():
            self._status_label.setText("正在枚举子域名...")

            result_widget = QTextEdit_style()
            result_widget.setReadOnly(True)
            idx = self._main_tabs.addTab(result_widget, "子域名枚举")
            self._main_tabs.setCurrentIndex(idx)

            self._subdomain_worker = SubdomainEnumerationWorker(domain.strip())
            self._subdomain_worker.result_ready.connect(
                lambda d, r, e: self._on_subdomain_result(result_widget, d, r, e)
            )
            self._subdomain_worker.start()

    def _on_subdomain_result(self, widget, domain, results, error):
        widget.append(f'<span style="color:#4ecdc4;">子域名枚举结果 - {domain}</span>\n')
        if error:
            widget.append(f'<span style="color:#ff6b6b;">枚举失败: {error}</span>')
        else:
            widget.append(f'<span style="color:#4ecdc4;">发现 {len(results)} 个子域名</span>\n')
            
            for r in results:
                widget.append(f'  <span style="color:#4ecdc4;">{r.get("subdomain")}</span> '
                             f'<span style="color:#888;">-> {r.get("ip")}</span>')
        self._status_label.setText("子域名枚举完成")

    # ---- 压力测试工具 ----

    def _tool_http_load_test(self):
        """HTTP压力测试"""
        url, ok = QInputDialog.getText(self, "HTTP压力测试", "目标URL:", text="http://example.com/")
        if ok and url.strip():
            requests, ok2 = QInputDialog.getInt(self, "HTTP压力测试", "请求总数:", value=100, min=10, max=1000)
            if ok2:
                concurrent, ok3 = QInputDialog.getInt(self, "HTTP压力测试", "并发数:", value=10, min=1, max=50)
                if ok3:
                    self._status_label.setText("正在进行HTTP压力测试...")

                    result_widget = QTextEdit_style()
                    result_widget.setReadOnly(True)
                    idx = self._main_tabs.addTab(result_widget, "HTTP压力测试")
                    self._main_tabs.setCurrentIndex(idx)

                    self._http_load_worker = HttpLoadTestWorker(url.strip(), requests, concurrent)
                    self._http_load_worker.result_ready.connect(
                        lambda u, r, e: self._on_http_load_result(result_widget, u, r, e)
                    )
                    self._http_load_worker.start()

    def _on_http_load_result(self, widget, url, results, error):
        widget.append(f'<span style="color:#4ecdc4;">HTTP压力测试结果 - {url}</span>\n')
        if error:
            widget.append(f'<span style="color:#ff6b6b;">测试失败: {error}</span>')
        else:
            widget.append(f'<span style="color:#4ecdc4;">总请求数: {results.get("total_requests")}</span>')
            widget.append(f'<span style="color:#4ecdc4;">成功: {results.get("success_count")}</span>')
            widget.append(f'<span style="color:#ff6b6b;">失败: {results.get("failed_count")}</span>')
            widget.append(f'<span style="color:#4ecdc4;">总耗时: {results.get("total_time")}</span>')
            widget.append(f'<span style="color:#ffaa00;">QPS: {results.get("requests_per_second")}</span>')
            widget.append(f'<span style="color:#888;">最小响应时间: {results.get("min_response_time")}</span>')
            widget.append(f'<span style="color:#888;">最大响应时间: {results.get("max_response_time")}</span>')
            widget.append(f'<span style="color:#888;">平均响应时间: {results.get("avg_response_time")}</span>')
            
            if results.get("status_codes"):
                widget.append(f'\n<span style="color:#888;">状态码分布:</span>')
                for code, count in results["status_codes"].items():
                    widget.append(f'  <span style="color:#aaa;">{code}: {count}</span>')
        self._status_label.setText("HTTP压力测试完成")

    def _tool_tcp_flood(self):
        """TCP洪水测试"""
        host, ok = QInputDialog.getText(self, "TCP洪水测试", "目标主机:", text="127.0.0.1")
        if ok and host.strip():
            port, ok2 = QInputDialog.getInt(self, "TCP洪水测试", "目标端口:", value=80, min=1, max=65535)
            if ok2:
                duration, ok3 = QInputDialog.getInt(self, "TCP洪水测试", "测试时长(秒):", value=10, min=1, max=60)
                if ok3:
                    self._status_label.setText("正在进行TCP洪水测试...")

                    result_widget = QTextEdit_style()
                    result_widget.setReadOnly(True)
                    idx = self._main_tabs.addTab(result_widget, "TCP洪水测试")
                    self._main_tabs.setCurrentIndex(idx)

                    self._tcp_flood_worker = TCPFloodTestWorker(host.strip(), port, duration)
                    self._tcp_flood_worker.result_ready.connect(
                        lambda h, p, r, e: self._on_tcp_flood_result(result_widget, h, p, r, e)
                    )
                    self._tcp_flood_worker.start()

    def _on_tcp_flood_result(self, widget, host, port, results, error):
        widget.append(f'<span style="color:#4ecdc4;">TCP洪水测试结果 - {host}:{port}</span>\n')
        if error:
            widget.append(f'<span style="color:#ff6b6b;">测试失败: {error}</span>')
        else:
            widget.append(f'<span style="color:#4ecdc4;">测试时长: {results.get("duration")}秒</span>')
            widget.append(f'<span style="color:#4ecdc4;">发送数据包: {results.get("packets_sent")}</span>')
            widget.append(f'<span style="color:#ff6b6b;">失败数据包: {results.get("packets_failed")}</span>')
            widget.append(f'<span style="color:#ffaa00;">发送速率: {results.get("packets_per_second")}/秒</span>')
        self._status_label.setText("TCP洪水测试完成")

    # ---- 服务器测试工具 ----

    def _tool_server_info(self):
        """服务器信息收集"""
        host, ok = QInputDialog.getText(self, "服务器信息收集", "目标主机:", text="127.0.0.1")
        if ok and host.strip():
            self._status_label.setText("正在收集服务器信息...")

            result_widget = QTextEdit_style()
            result_widget.setReadOnly(True)
            idx = self._main_tabs.addTab(result_widget, "服务器信息")
            self._main_tabs.setCurrentIndex(idx)

            self._server_info_worker = ServerInfoWorker(host.strip())
            self._server_info_worker.result_ready.connect(
                lambda h, r, e: self._on_server_info_result(result_widget, h, r, e)
            )
            self._server_info_worker.start()

    def _on_server_info_result(self, widget, host, info, error):
        widget.append(f'<span style="color:#4ecdc4;">服务器信息 - {host}</span>\n')
        if error:
            widget.append(f'<span style="color:#ff6b6b;">收集失败: {error}</span>')
        else:
            widget.append(f'<span style="color:#4ecdc4;">IP: {info.get("ip", "未知")}</span>')
            widget.append(f'<span style="color:#4ecdc4;">主机名: {info.get("hostname", "未知")}</span>')
            widget.append(f'<span style="color:#ffaa00;">操作系统: {info.get("os", "未知")}</span>')
            widget.append(f'\n<span style="color:#888;">开放端口:</span>')
            for service in info.get("services", []):
                widget.append(f'  <span style="color:#4ecdc4;">{service}</span>')
        self._status_label.setText("服务器信息收集完成")

    def _tool_ftp_anonymous(self):
        """FTP匿名登录检测"""
        host, ok = QInputDialog.getText(self, "FTP匿名检测", "目标主机:", text="127.0.0.1")
        if ok and host.strip():
            self._status_label.setText("正在检测FTP匿名登录...")

            result_widget = QTextEdit_style()
            result_widget.setReadOnly(True)
            idx = self._main_tabs.addTab(result_widget, "FTP匿名检测")
            self._main_tabs.setCurrentIndex(idx)

            self._ftp_worker = FTPAnonymousWorker(host.strip())
            self._ftp_worker.result_ready.connect(
                lambda h, r, e: self._on_ftp_result(result_widget, h, r, e)
            )
            self._ftp_worker.start()

    def _on_ftp_result(self, widget, host, result, error):
        widget.append(f'<span style="color:#4ecdc4;">FTP匿名登录检测 - {host}:{result.get("port", 21)}</span>\n')
        if error:
            widget.append(f'<span style="color:#ff6b6b;">检测失败: {error}</span>')
        else:
            if result.get("anonymous_login"):
                widget.append(f'<span style="color:#ff6b6b;">[危险] {result.get("message")}</span>')
            else:
                widget.append(f'<span style="color:#4ecdc4;">[安全] {result.get("message")}</span>')
        self._status_label.setText("FTP匿名检测完成")

    def _tool_smb_enum(self):
        """SMB服务枚举"""
        host, ok = QInputDialog.getText(self, "SMB服务枚举", "目标主机:", text="127.0.0.1")
        if ok and host.strip():
            self._status_label.setText("正在枚举SMB服务...")

            result_widget = QTextEdit_style()
            result_widget.setReadOnly(True)
            idx = self._main_tabs.addTab(result_widget, "SMB枚举")
            self._main_tabs.setCurrentIndex(idx)

            self._smb_worker = SMBEnumerationWorker(host.strip())
            self._smb_worker.result_ready.connect(
                lambda h, r, e: self._on_smb_result(result_widget, h, r, e)
            )
            self._smb_worker.start()

    def _on_smb_result(self, widget, host, results, error):
        widget.append(f'<span style="color:#4ecdc4;">SMB服务枚举 - {host}</span>\n')
        if error:
            widget.append(f'<span style="color:#ff6b6b;">枚举失败: {error}</span>')
        else:
            if results:
                widget.append(f'<span style="color:#ffaa00;">发现 {len(results)} 个共享资源</span>')
                for r in results:
                    widget.append(f'  <span style="color:#4ecdc4;">{r.get("share")} - {r.get("message")}</span>')
            else:
                widget.append(f'<span style="color:#4ecdc4;">未发现SMB共享或端口未开放</span>')
        self._status_label.setText("SMB枚举完成")

    def _tool_ssh_weak_password(self):
        """SSH弱密码检测"""
        host, ok = QInputDialog.getText(self, "SSH弱密码检测", "目标主机:", text="127.0.0.1")
        if ok and host.strip():
            username, ok2 = QInputDialog.getText(self, "SSH弱密码检测", "用户名:", text="root")
            if ok2 and username.strip():
                self._status_label.setText("正在检测SSH弱密码...")

                result_widget = QTextEdit_style()
                result_widget.setReadOnly(True)
                idx = self._main_tabs.addTab(result_widget, "SSH弱密码检测")
                self._main_tabs.setCurrentIndex(idx)

                self._ssh_weak_worker = SSHWeakPasswordWorker(host.strip(), 22, username.strip())
                self._ssh_weak_worker.result_ready.connect(
                    lambda h, r, e: self._on_ssh_weak_result(result_widget, h, r, e)
                )
                self._ssh_weak_worker.start()

    def _on_ssh_weak_result(self, widget, host, result, error):
        widget.append(f'<span style="color:#4ecdc4;">SSH弱密码检测 - {host}:{result.get("port", 22)}</span>\n')
        if error:
            widget.append(f'<span style="color:#ff6b6b;">检测失败: {error}</span>')
        else:
            if result.get("weak_password_found"):
                widget.append(f'<span style="color:#ff6b6b;">[危险] 发现弱密码: {result.get("password")}</span>')
            else:
                widget.append(f'<span style="color:#4ecdc4;">[安全] 未发现弱密码（尝试了{result.get("attempts")}个密码）</span>')
        self._status_label.setText("SSH弱密码检测完成")

    def _tool_banner_grab(self):
        """服务横幅获取"""
        host, ok = QInputDialog.getText(self, "服务横幅获取", "目标主机:", text="127.0.0.1")
        if ok and host.strip():
            port, ok2 = QInputDialog.getInt(self, "服务横幅获取", "端口:", value=80, min=1, max=65535)
            if ok2:
                self._status_label.setText("正在获取服务横幅...")

                result_widget = QTextEdit_style()
                result_widget.setReadOnly(True)
                idx = self._main_tabs.addTab(result_widget, f"横幅:{port}")
                self._main_tabs.setCurrentIndex(idx)

                self._banner_worker = BannerGrabWorker(host.strip(), port)
                self._banner_worker.result_ready.connect(
                    lambda h, p, r, e: self._on_banner_result(result_widget, h, p, r, e)
                )
                self._banner_worker.start()

    def _on_banner_result(self, widget, host, port, result, error):
        widget.append(f'<span style="color:#4ecdc4;">服务横幅 - {host}:{port}</span>\n')
        if error:
            widget.append(f'<span style="color:#ff6b6b;">获取失败: {error}</span>')
        else:
            widget.append(f'<span style="color:#4ecdc4;">服务: {result.get("service", "未知")}</span>')
            widget.append(f'<span style="color:#ffaa00;">版本: {result.get("version", "未知")}</span>')
            if result.get("banner"):
                widget.append(f'\n<span style="color:#888;">横幅信息:</span>')
                widget.append(f'<pre style="color:#aaa;">{result.get("banner")}</pre>')
        self._status_label.setText("服务横幅获取完成")

    def _tool_port_enumeration(self):
        """端口全量扫描"""
        host, ok = QInputDialog.getText(self, "端口全量扫描", "目标主机:", text="127.0.0.1")
        if ok and host.strip():
            start_port, ok2 = QInputDialog.getInt(self, "端口全量扫描", "起始端口:", value=1, min=1, max=65535)
            if ok2:
                end_port, ok3 = QInputDialog.getInt(self, "端口全量扫描", "结束端口:", value=1000, min=1, max=65535)
                if ok3 and end_port >= start_port:
                    self._status_label.setText("正在进行端口全量扫描...")

                    result_widget = QTextEdit_style()
                    result_widget.setReadOnly(True)
                    idx = self._main_tabs.addTab(result_widget, "端口扫描")
                    self._main_tabs.setCurrentIndex(idx)

                    self._port_enum_worker = PortEnumerationWorker(host.strip(), start_port, end_port)
                    self._port_enum_worker.result_ready.connect(
                        lambda h, r, e: self._on_port_enum_result(result_widget, h, r, e)
                    )
                    self._port_enum_worker.start()

    def _on_port_enum_result(self, widget, host, results, error):
        widget.append(f'<span style="color:#4ecdc4;">端口扫描结果 - {host}</span>\n')
        if error:
            widget.append(f'<span style="color:#ff6b6b;">扫描失败: {error}</span>')
        else:
            widget.append(f'<span style="color:#4ecdc4;">发现 {len(results)} 个开放端口</span>\n')
            for r in results:
                widget.append(f'  <span style="color:#ffaa00;">{r.get("port")}</span> '
                             f'<span style="color:#4ecdc4;">{r.get("service")}</span>')
                if r.get("banner"):
                    widget.append(f'     <span style="color:#888;">{r.get("banner")}</span>')
        self._status_label.setText("端口扫描完成")

    def _tool_plugin_manager(self):
        """插件管理器"""
        from app.security_tools import list_installed_plugins, PLUGIN_REPOS, get_builtin_plugins
        
        dialog = QDialog(self)
        dialog.setWindowTitle("插件管理器")
        dialog.setMinimumWidth(500)
        
        layout = QVBoxLayout(dialog)
        
        # 已安装插件列表
        installed_group = QGroupBox("已安装插件")
        installed_layout = QVBoxLayout(installed_group)
        
        plugins = list_installed_plugins()
        if plugins:
            for plugin in plugins:
                layout_item = QHBoxLayout()
                layout_item.addWidget(QLabel(plugin))
                remove_btn = QPushButton("卸载")
                remove_btn.clicked.connect(lambda p=plugin: self._uninstall_plugin(p))
                layout_item.addWidget(remove_btn)
                installed_layout.addLayout(layout_item)
        else:
            installed_layout.addWidget(QLabel("暂无已安装插件"))
        
        layout.addWidget(installed_group)
        
        # 内置插件（无需下载）
        builtin_group = QGroupBox("内置插件（本地安装）")
        builtin_layout = QVBoxLayout(builtin_group)
        
        builtin_plugins = get_builtin_plugins()
        for name, module_name in builtin_plugins.items():
            layout_item = QHBoxLayout()
            layout_item.addWidget(QLabel(name))
            install_btn = QPushButton("安装")
            install_btn.clicked.connect(lambda n=name, m=module_name: self._install_builtin_plugin(n, m))
            layout_item.addWidget(install_btn)
            builtin_layout.addLayout(layout_item)
        
        layout.addWidget(builtin_group)
        
        # 可下载插件（GitHub）
        available_group = QGroupBox("GitHub插件（需要网络）")
        available_layout = QVBoxLayout(available_group)
        
        for name, url in PLUGIN_REPOS.items():
            layout_item = QHBoxLayout()
            layout_item.addWidget(QLabel(name))
            layout_item.addWidget(QLabel(url, wordWrap=True))
            install_btn = QPushButton("安装")
            install_btn.clicked.connect(lambda n=name, u=url: self._install_plugin(n, u))
            layout_item.addWidget(install_btn)
            available_layout.addLayout(layout_item)
        
        layout.addWidget(available_group)
        
        # 自定义仓库输入
        custom_group = QHBoxLayout()
        custom_group.addWidget(QLabel("自定义仓库:"))
        custom_url = QLineEdit()
        custom_url.setPlaceholderText("https://github.com/username/repo")
        custom_group.addWidget(custom_url)
        install_custom_btn = QPushButton("安装")
        install_custom_btn.clicked.connect(
            lambda: self._install_plugin("custom", custom_url.text())
        )
        custom_group.addWidget(install_custom_btn)
        layout.addLayout(custom_group)
        
        dialog.exec_()

    def _install_builtin_plugin(self, name, module_name):
        """安装内置插件"""
        from app.security_tools import install_builtin_plugin, list_installed_plugins, BUILTIN_PLUGIN_DEFINITIONS

        result_widget = QTextEdit_style()
        result_widget.setReadOnly(True)
        idx = self._main_tabs.addTab(result_widget, f"插件安装: {name}")
        self._main_tabs.setCurrentIndex(idx)

        result_widget.append(f'<span style="color:#4ecdc4;">▶ 开始安装插件: {name}</span>')
        result_widget.append(f'<span style="color:#888;">  模块名: {module_name}</span>')

        # 显示描述
        info = BUILTIN_PLUGIN_DEFINITIONS.get(name, {})
        if info:
            result_widget.append(f'<span style="color:#888;">  描述: {info.get("description", "")}</span>')
            result_widget.append(f'<span style="color:#888;">  函数: {", ".join(info.get("functions", []))}</span>')

        # 检查是否已安装
        installed = list_installed_plugins()
        if module_name in installed:
            result_widget.append(f'<span style="color:#ffaa00;">  ⚠ 插件已存在，将覆盖</span>')

        # 执行安装
        success, message = install_builtin_plugin(name)

        if success:
            result_widget.append(f'<span style="color:#4ecdc4;">✓ 插件 {name} 安装成功</span>')
            result_widget.append(f'<span style="color:#888;">  状态: {message}</span>')
            result_widget.append(f'<span style="color:#888;">  位置: app/plugins/</span>')
            result_widget.append(f'<span style="color:#888;">  下次启动应用后即可使用</span>')
            result_widget.append(f'')
            result_widget.append(f'<span style="color:#4ecdc4;">使用示例:</span>')
            if name == "端口扫描增强":
                result_widget.append(f'<span style="color:#aaa;">  from app.plugins import port_scan_enhanced</span>')
                result_widget.append(f'<span style="color:#aaa;">  result = port_scan_enhanced.scan_ports("127.0.0.1")</span>')
            elif name == "漏洞检测工具":
                result_widget.append(f'<span style="color:#aaa;">  from app.plugins import vuln_scanner</span>')
                result_widget.append(f'<span style="color:#aaa;">  result = vuln_scanner.detect_vulnerabilities("127.0.0.1")</span>')
            elif name == "安全审计工具":
                result_widget.append(f'<span style="color:#aaa;">  from app.plugins import security_audit</span>')
                result_widget.append(f'<span style="color:#aaa;">  result = security_audit.audit_security("127.0.0.1")</span>')
            elif name == "网络流量分析":
                result_widget.append(f'<span style="color:#aaa;">  from app.plugins import traffic_analyzer</span>')
                result_widget.append(f'<span style="color:#aaa;">  result = traffic_analyzer.analyze_traffic("127.0.0.1")</span>')

            self._status_label.setText(f"✓ 插件 {name} 安装成功")
        else:
            result_widget.append(f'<span style="color:#ff6b6b;">✗ 插件 {name} 安装失败</span>')
            result_widget.append(f'<span style="color:#ff6b6b;">  原因: {message}</span>')
            result_widget.append(f'')
            result_widget.append(f'<span style="color:#ffaa00;">排查建议:</span>')
            result_widget.append(f'<span style="color:#aaa;">  1. 检查 app/plugins/ 目录权限</span>')
            result_widget.append(f'<span style="color:#aaa;">  2. 尝试以管理员身份运行应用</span>')
            result_widget.append(f'<span style="color:#aaa;">  3. 检查磁盘空间是否充足</span>')
            result_widget.append(f'<span style="color:#aaa;">  4. 重启应用后重试</span>')
            self._status_label.setText(f"✗ 插件 {name} 安装失败")

    def _install_plugin(self, name, url):
        """安装插件"""
        result_widget = QTextEdit_style()
        result_widget.setReadOnly(True)
        idx = self._main_tabs.addTab(result_widget, f"插件安装: {name}")
        self._main_tabs.setCurrentIndex(idx)

        self._plugin_worker = PluginDownloadWorker(url, name)
        self._plugin_worker.result_ready.connect(
            lambda success, msg: self._on_plugin_install(result_widget, success, msg)
        )
        self._plugin_worker.start()

    def _on_plugin_install(self, widget, success, message):
        if success:
            widget.append(f'<span style="color:#4ecdc4;">{message}</span>')
            widget.append(f'<span style="color:#888;">插件已安装到 app/plugins/ 目录</span>')
            widget.append(f'<span style="color:#888;">重启应用后生效</span>')
        else:
            widget.append(f'<span style="color:#ff6b6b;">{message}</span>')
            widget.append(f'\n<span style="color:#888;">可能的原因：</span>')
            widget.append(f'<span style="color:#aaa;">- GitHub仓库不存在或URL错误</span>')
            widget.append(f'<span style="color:#aaa;">- 网络连接问题（无法访问GitHub）</span>')
            widget.append(f'<span style="color:#aaa;">- 仓库没有main/master/develop分支</span>')
            widget.append(f'<span style="color:#aaa;">- 仓库中没有Python文件</span>')
            widget.append(f'\n<span style="color:#888;">解决方法：</span>')
            widget.append(f'<span style="color:#aaa;">1. 检查仓库URL是否正确</span>')
            widget.append(f'<span style="color:#aaa;">2. 确保网络可以访问GitHub</span>')
            widget.append(f'<span style="color:#aaa;">3. 尝试使用自定义仓库输入手动安装</span>')
        self._status_label.setText("插件安装完成")

    def _uninstall_plugin(self, name):
        """卸载插件"""
        import os
        plugin_path = os.path.join(os.path.dirname(__file__), "plugins", f"{name}.py")
        if os.path.exists(plugin_path):
            os.remove(plugin_path)
            QMessageBox.information(self, "成功", f"插件 {name} 已卸载")
        else:
            QMessageBox.warning(self, "错误", "插件文件不存在")

    # ---- AI 相关 ----

    def _toggle_ai_panel(self):
        """切换 AI 面板显示"""
        self._ai_panel.setVisible(not self._ai_panel.isVisible())

    def _open_enterprise_ops(self):
        """打开企业级运维控制台（作为新标签页）"""
        # 若已存在则切换
        for i in range(self._main_tabs.count()):
            w = self._main_tabs.widget(i)
            if getattr(w, "_is_enterprise_ops", False):
                self._main_tabs.setCurrentIndex(i)
                return
        widget = open_enterprise_ops(self)
        widget._is_enterprise_ops = True
        idx = self._main_tabs.addTab(widget, "🛠 运维控制台")
        self._main_tabs.setCurrentIndex(idx)

    def _show_about(self):
        """显示关于对话框"""
        dlg = AboutDialog(self)
        dlg.exec()

    def _on_diagnosis_requested(self, context: str):
        """仪表盘请求 AI 诊断"""
        self._ai_panel.show_diagnosis(context)

    def _on_send_command_to_terminal(self, command: str):
        """从 AI 面板发送命令到当前终端"""
        current = self._main_tabs.currentWidget()
        if isinstance(current, SSHTerminalTab):
            current.inject_command(command)
        else:
            self._status_label.setText("请先连接 SSH 终端")

    def _on_completion_requested(self, context: str):
        """Ghost Text 补全请求"""
        # 提取当前输入行
        lines = context.split("\n")
        current_input = lines[-1].replace("当前输入: ", "") if lines else ""

        self._completion_worker = AICompletionWorker(
            self._ai_engine, context, current_input
        )
        self._completion_worker.completion_ready.connect(self._on_completion_ready)
        self._completion_worker.start()

    def _on_completion_ready(self, completion: str):
        """Ghost Text 补全结果"""
        if not completion:
            return

        current = self._main_tabs.currentWidget()
        if isinstance(current, SSHTerminalTab):
            current.terminal.set_ghost_text(completion)

    # =================================================================
    # 新增检测工具方法
    # =================================================================

    def _tool_tcp_ping(self):
        """TCP Ping（ICMP 被防火墙阻挡时使用）"""
        host, ok = QInputDialog.getText(self, "TCP Ping", "目标主机:")
        if ok and host.strip():
            self._status_label.setText(f"TCP Ping {host}...")
            w = QTextEdit_style()
            idx = self._main_tabs.addTab(w, f"TCP Ping: {host}")
            self._main_tabs.setCurrentIndex(idx)
            self._tcp_ping_worker = TCPPingWorker(host.strip())
            self._tcp_ping_worker.result_ready.connect(
                lambda h, p, l, s: self._on_tcp_ping_result(w, h, p, l, s))
            self._tcp_ping_worker.start()

    def _on_tcp_ping_result(self, w, host, port, latency, status):
        if status == "open":
            color = "#4ecdc4"
            lat_str = f"延迟 {latency:.1f}ms" if latency >= 0 else ""
        elif status == "timeout":
            color = "#ffaa00"
            lat_str = "超时"
        else:
            color = "#ff6b6b"
            lat_str = status
        w.append(
            f'<span style="color:{color};">● 端口 {port:>5}</span>  '
            f'<span style="color:#aaa;">{host}</span>  {lat_str}')

    def _tool_http_headers(self):
        """HTTP 响应头详细检测"""
        url, ok = QInputDialog.getText(
            self, "HTTP 响应头", "目标 URL:", text="https://www.baidu.com")
        if not ok or not url.strip():
            return
        self._status_label.setText(f"获取 {url} 响应头...")
        w = QTextEdit_style()
        idx = self._main_tabs.addTab(w, f"HTTP头: {url[:40]}")
        self._main_tabs.setCurrentIndex(idx)
        self._http_hdr_worker = HTTPResponseHeadersWorker(url.strip())
        self._http_hdr_worker.result_ready.connect(
            lambda u, hdrs, err: self._on_http_headers_result(w, u, hdrs, err))
        self._http_hdr_worker.start()

    def _on_http_headers_result(self, w, url, hdrs, err):
        if not hdrs and err:
            w.append(f'<span style="color:#ff6b6b;">请求失败: {err}</span>')
            self._status_label.setText("HTTP 头获取失败")
            return
        w.append(f'<span style="color:#4ecdc4;">── {url} ──</span>')
        if err:
            w.append(f'<span style="color:#ffaa00;">{err}</span>')
        # 状态行
        status = hdrs.pop("__status__", "?")
        reason = hdrs.pop("__reason__", "")
        w.append(f'<span style="color:#4ecdc4;">HTTP/{status} {reason}</span>\n')
        w.append('<span style="color:#4ecdc4;">[ 响应头 ]</span>')
        for k in sorted(hdrs.keys()):
            w.append(f'<span style="color:#aaa;">{k}: </span>{hdrs[k]}')
        # 安全相关摘要
        w.append('\n<span style="color:#4ecdc4;">[ 安全分析 ]</span>')
        sec = {
            "Strict-Transport-Security": "HSTS - 强制 HTTPS",
            "Content-Security-Policy": "CSP - 内容安全策略",
            "X-Frame-Options": "防点击劫持",
            "X-Content-Type-Options": "防 MIME 嗅探",
            "X-XSS-Protection": "XSS 过滤器",
            "Referrer-Policy": "Referrer 策略",
            "Permissions-Policy": "权限策略",
            "Server": "服务器标识（建议隐藏）",
            "X-Powered-By": "框架标识（建议隐藏）",
        }
        for h, desc in sec.items():
            present = "✓ 已设置" if any(k.lower() == h.lower() for k in hdrs) else "✗ 缺失"
            color = "#4ecdc4" if "✓" in present else "#ff6b6b"
            w.append(
                f'  <span style="color:{color};">{present}</span>  '
                f'<span style="color:#aaa;">{h}</span>  {desc}')
        self._status_label.setText("HTTP 头获取完成")

    def _tool_dns_extended(self):
        """扩展 DNS 记录查询"""
        host, ok = QInputDialog.getText(
            self, "扩展 DNS 记录", "目标域名:",
            text="baidu.com")
        if not ok or not host.strip():
            return
        self._status_label.setText(f"查询 {host} 扩展 DNS 记录...")
        w = QTextEdit_style()
        idx = self._main_tabs.addTab(w, f"DNS记录: {host}")
        self._main_tabs.setCurrentIndex(idx)
        self._dns_ext_worker = DNSRecordsWorker(host.strip(), include_srv=False)
        self._dns_ext_worker.result_ready.connect(
            lambda h, recs, err: self._on_dns_ext_result(w, h, recs, err))
        self._dns_ext_worker.start()

    def _on_dns_ext_result(self, w, host, records, err):
        if not records:
            w.append(f'<span style="color:#ff6b6b;">未查询到记录: {err}</span>')
            self._status_label.setText("DNS 查询失败")
            return
        # 按类型分组
        types_order = ["A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA"]
        grouped: dict = {}
        for t, v in records:
            grouped.setdefault(t, []).append(v)
        for t in types_order:
            if t in grouped:
                w.append(f'<span style="color:#4ecdc4;">[ {t} ]</span>')
                for v in grouped[t]:
                    w.append(f'  <span style="color:#aaa;">{v}</span>')
        # 其他类型
        for t, v in records:
            if t not in types_order:
                grouped.setdefault(t, []).append(v)
        for t in grouped:
            if t not in types_order:
                w.append(f'<span style="color:#4ecdc4;">[ {t} ]</span>')
                for v in grouped[t]:
                    w.append(f'  <span style="color:#aaa;">{v}</span>')
        w.append(f'<span style="color:#888;">共 {len(records)} 条记录</span>')
        self._status_label.setText("DNS 扩展查询完成")

    def _tool_ipv6_check(self):
        """IPv6 连通性检测"""
        host, ok = QInputDialog.getText(
            self, "IPv6 检测", "目标域名/IPv6:",
            text="www.baidu.com")
        if not ok or not host.strip():
            return
        self._status_label.setText(f"检测 {host} 的 IPv6 支持...")
        w = QTextEdit_style()
        idx = self._main_tabs.addTab(w, f"IPv6: {host}")
        self._main_tabs.setCurrentIndex(idx)
        self._ipv6_worker = IPv6SupportWorker(host.strip())
        self._ipv6_worker.result_ready.connect(
            lambda h, ok6, addr, err: self._on_ipv6_result(w, h, ok6, addr, err))
        self._ipv6_worker.start()

    def _on_ipv6_result(self, w, host, has_ipv6, ipv6_addr, err):
        if has_ipv6:
            w.append(f'<span style="color:#4ecdc4;">✓ {host} 支持 IPv6</span>')
            w.append(f'  <span style="color:#aaa;">AAAA 记录: {ipv6_addr}</span>')
        else:
            w.append(f'<span style="color:#ff6b6b;">✗ {host} 不支持 IPv6</span>')
            if err:
                w.append(f'  <span style="color:#aaa;">{err}</span>')
        self._status_label.setText("IPv6 检测完成")

    def _tool_mail_server(self):
        """邮件服务器检测"""
        host, ok = QInputDialog.getText(
            self, "邮件服务器检测", "邮件服务器域名:",
            text="gmail.com")
        if not ok or not host.strip():
            return
        self._status_label.setText(f"探测 {host} 邮件服务...")
        w = QTextEdit_style()
        idx = self._main_tabs.addTab(w, f"邮件: {host}")
        self._main_tabs.setCurrentIndex(idx)
        self._mail_worker = MailServerWorker(host.strip())
        self._mail_worker.result_ready.connect(
            lambda h, rs: self._on_mail_result(w, h, rs))
        self._mail_worker.start()

    def _on_mail_result(self, w, host, results):
        w.append(f'<span style="color:#4ecdc4;">── 邮件服务 {host} ──</span>')
        any_open = False
        for proto, info in results.items():
            if info.get("reachable"):
                any_open = True
                color = "#4ecdc4"
                w.append(
                    f'<span style="color:{color};">● {proto}</span>  '
                    f'<span style="color:#aaa;">端口 {info.get("port")} 开放</span>')
                if info.get("banner"):
                    w.append(
                        f'    <span style="color:#aaa;">Banner: '
                        f'{info["banner"][:80]}</span>')
                if info.get("starttls"):
                    w.append('    <span style="color:#4ecdc4;">支持 STARTTLS</span>')
            else:
                w.append(
                    f'<span style="color:#ff6b6b;">○ {proto}</span>  '
                    f'<span style="color:#888;">不可达 / {info.get("error", "关闭")}</span>')
        if not any_open:
            w.append(f'<span style="color:#ffaa00;">未发现任何开放的邮件端口</span>')
        self._status_label.setText("邮件服务检测完成")

    def _tool_cors_check(self):
        """CORS 配置检测"""
        url, ok = QInputDialog.getText(
            self, "CORS 检测", "目标 URL:", text="https://www.baidu.com")
        if not ok or not url.strip():
            return
        self._status_label.setText(f"分析 {url} CORS 配置...")
        w = QTextEdit_style()
        idx = self._main_tabs.addTab(w, f"CORS: {url[:40]}")
        self._main_tabs.setCurrentIndex(idx)
        self._cors_worker = CORSWorker(url.strip())
        self._cors_worker.result_ready.connect(
            lambda u, info, err: self._on_cors_result(w, u, info, err))
        self._cors_worker.start()

    def _on_cors_result(self, w, url, info, err):
        w.append(f'<span style="color:#4ecdc4;">── CORS 配置 {url} ──</span>')
        if err and not info.get("headers"):
            w.append(f'<span style="color:#ff6b6b;">请求失败: {err}</span>')
        # 头部
        w.append('<span style="color:#4ecdc4;">[ 响应头 ]</span>')
        for k, v in info.get("headers", {}).items():
            w.append(f'  <span style="color:#aaa;">{k}: </span>{v or "(未设置)"}')
        # 漏洞
        vulns = info.get("vulnerabilities", [])
        w.append(f'\n<span style="color:#4ecdc4;">[ 风险 ]</span>')
        if not vulns:
            w.append('  <span style="color:#4ecdc4;">未发现明显 CORS 配置问题</span>')
        else:
            for v in vulns:
                w.append(f'  <span style="color:#ff6b6b;">⚠ {v}</span>')
        self._status_label.setText("CORS 检测完成")

    def _tool_cdn_waf(self):
        """CDN / WAF 检测"""
        host, ok = QInputDialog.getText(
            self, "CDN/WAF 检测", "目标域名:", text="www.cloudflare.com")
        if not ok or not host.strip():
            return
        self._status_label.setText(f"分析 {host} CDN/WAF...")
        w = QTextEdit_style()
        idx = self._main_tabs.addTab(w, f"CDN/WAF: {host}")
        self._main_tabs.setCurrentIndex(idx)
        self._cdn_waf_worker = CDNWAFWorker(host.strip())
        self._cdn_waf_worker.result_ready.connect(
            lambda h, r, e: self._on_cdn_waf_result(w, h, r, e))
        self._cdn_waf_worker.start()

    def _on_cdn_waf_result(self, w, host, result, err):
        w.append(f'<span style="color:#4ecdc4;">── CDN/WAF {host} ──</span>')
        if err and not result.get("headers_matched"):
            w.append(f'<span style="color:#ffaa00;">{err}</span>')
        if result.get("ip"):
            w.append(f'<span style="color:#aaa;">解析 IP: {result["ip"]}</span>')
        cdns = result.get("cdn", [])
        w.append('\n<span style="color:#4ecdc4;">[ CDN ]</span>')
        if cdns:
            for c in cdns:
                w.append(f'  <span style="color:#4ecdc4;">● {c}</span>')
        else:
            w.append('  <span style="color:#888;">未识别到 CDN</span>')
        wafs = result.get("waf", [])
        w.append('\n<span style="color:#4ecdc4;">[ WAF ]</span>')
        if wafs:
            for wf in wafs:
                w.append(f'  <span style="color:#ffaa00;">● {wf}</span>')
        else:
            w.append('  <span style="color:#888;">未识别到 WAF</span>')
        if result.get("headers_matched"):
            w.append('\n<span style="color:#4ecdc4;">[ 匹配特征头 ]</span>')
            for h in result["headers_matched"][:20]:
                w.append(f'  <span style="color:#aaa;">{h}</span>')
        self._status_label.setText("CDN/WAF 检测完成")

    def _tool_websocket(self):
        """WebSocket 握手测试"""
        url, ok = QInputDialog.getText(
            self, "WebSocket 测试", "WebSocket URL (ws://...):",
            text="wss://echo.websocket.org/")
        if not ok or not url.strip():
            return
        if not url.startswith(("ws://", "wss://")):
            QMessageBox.warning(self, "格式错误", "URL 必须以 ws:// 或 wss:// 开头")
            return
        self._status_label.setText(f"测试 {url} WebSocket 握手...")
        w = QTextEdit_style()
        idx = self._main_tabs.addTab(w, f"WS: {url[:40]}")
        self._main_tabs.setCurrentIndex(idx)
        self._ws_worker = WebSocketWorker(url.strip())
        self._ws_worker.result_ready.connect(
            lambda u, info, e: self._on_ws_result(w, u, info, e))
        self._ws_worker.start()

    def _on_ws_result(self, w, url, info, err):
        w.append(f'<span style="color:#4ecdc4;">── WebSocket 握手 {url} ──</span>')
        if err:
            w.append(f'<span style="color:#ff6b6b;">错误: {err}</span>')
        if not info:
            self._status_label.setText("WebSocket 测试失败")
            return
        status = info.get("status")
        status_text = info.get("status_text", "")
        color = "#4ecdc4" if status == 101 else "#ff6b6b"
        w.append(f'<span style="color:{color};">状态: {status} {status_text}</span>')
        accept = info.get("Sec-WebSocket-Accept", "")
        w.append(f'<span style="color:#aaa;">Sec-WebSocket-Accept: {accept}</span>')
        if info.get("accept_match"):
            w.append('<span style="color:#4ecdc4;">✓ Accept 校验通过</span>')
        else:
            w.append('<span style="color:#ff6b6b;">✗ Accept 校验失败</span>')
        if info.get("headers"):
            w.append('\n<span style="color:#4ecdc4;">[ 响应头 ]</span>')
            for k, v in info["headers"].items():
                w.append(f'  <span style="color:#aaa;">{k}: </span>{v}')
        self._status_label.setText("WebSocket 测试完成")

    def _tool_public_ip(self):
        """公网 IP 检测"""
        self._status_label.setText("检测公网 IP...")
        w = QTextEdit_style()
        idx = self._main_tabs.addTab(w, "公网 IP")
        self._main_tabs.setCurrentIndex(idx)
        self._pubip_worker = PublicIPWorker()
        self._pubip_worker.result_ready.connect(
            lambda s, ip, e: self._on_pubip_result(w, s, ip, e))
        self._pubip_worker.start()

    def _on_pubip_result(self, w, service, ip, err):
        if ip:
            w.append(
                f'<span style="color:#4ecdc4;">✓ 公网 IP ({service}): </span>'
                f'<span style="color:#aaa;">{ip}</span>')
        else:
            w.append(
                f'<span style="color:#ff6b6b;">✗ {service}: {err}</span>')
        self._status_label.setText("公网 IP 检测完成")

    def _tool_mac_vendor(self):
        """MAC 地址厂商查询"""
        mac, ok = QInputDialog.getText(
            self, "MAC 厂商查询", "MAC 地址 (XX:XX:XX:XX:XX:XX):",
            text="00:1A:2B:11:22:33")
        if not ok or not mac.strip():
            return
        self._status_label.setText(f"查询 {mac} 厂商...")
        w = QTextEdit_style()
        idx = self._main_tabs.addTab(w, f"MAC: {mac}")
        self._main_tabs.setCurrentIndex(idx)
        self._mac_worker = MACVendorWorker(mac.strip())
        self._mac_worker.result_ready.connect(
            lambda m, info, e: self._on_mac_result(w, m, info, e))
        self._mac_worker.start()

    def _on_mac_result(self, w, mac, info, err):
        w.append(f'<span style="color:#4ecdc4;">── MAC 厂商查询 ──</span>')
        w.append(f'  <span style="color:#aaa;">原始输入: {mac}</span>')
        w.append(f'  <span style="color:#aaa;">标准化: {info.get("raw", "")}</span>')
        w.append(f'  <span style="color:#aaa;">OUI 前缀: {info.get("oui", "")}</span>')
        vendor = info.get("vendor", "未知")
        color = "#4ecdc4" if "未知" not in vendor else "#ffaa00"
        w.append(f'  <span style="color:{color};">厂商: {vendor}</span>')
        self._status_label.setText("MAC 厂商查询完成")

    def _tool_network_quality(self):
        """网络质量测试（延迟/抖动/丢包）"""
        host, ok = QInputDialog.getText(
            self, "网络质量测试", "目标主机:", text="www.baidu.com")
        if not ok or not host.strip():
            return
        count, ok2 = QInputDialog.getInt(
            self, "探测次数", "发送包数:", value=20, minValue=4, maxValue=100)
        if not ok2:
            return
        self._status_label.setText(f"测试到 {host} 的网络质量 ({count} 包)...")
        w = QTextEdit_style()
        idx = self._main_tabs.addTab(w, f"质量: {host}")
        self._main_tabs.setCurrentIndex(idx)
        self._quality_worker = NetworkQualityWorker(host.strip(), count=count)
        self._quality_worker.result_ready.connect(
            lambda h, info: self._on_quality_result(w, h, info))
        self._quality_worker.start()

    def _on_quality_result(self, w, host, info):
        loss = info.get("loss_pct", 0)
        avg = info.get("avg_ms", 0)
        mn = info.get("min_ms", 0)
        mx = info.get("max_ms", 0)
        jit = info.get("jitter_ms", 0)
        sent = info.get("sent", 0)
        recv = info.get("received", 0)
        w.append(f'<span style="color:#4ecdc4;">── 网络质量 {host} ──</span>')
        loss_color = "#4ecdc4" if loss == 0 else ("#ffaa00" if loss < 5 else "#ff6b6b")
        w.append(f'  <span style="color:#aaa;">发送/接收: </span>'
                 f'<span style="color:#4ecdc4;">{recv}/{sent}</span>')
        w.append(f'  <span style="color:#aaa;">丢包率: </span>'
                 f'<span style="color:{loss_color};">{loss:.1f}%</span>')
        w.append(f'  <span style="color:#aaa;">平均延迟: </span>'
                 f'<span style="color:#4ecdc4;">{avg:.1f} ms</span>')
        w.append(f'  <span style="color:#aaa;">最小/最大: </span>'
                 f'<span style="color:#aaa;">{mn:.1f} / {mx:.1f} ms</span>')
        w.append(f'  <span style="color:#aaa;">抖动: </span>'
                 f'<span style="color:#4ecdc4;">{jit:.2f} ms</span>')
        # 评价
        if loss == 0 and jit < 5:
            w.append('  <span style="color:#4ecdc4;">评价: 优</span>')
        elif loss < 2 and jit < 20:
            w.append('  <span style="color:#4ecdc4;">评价: 良</span>')
        elif loss < 5:
            w.append('  <span style="color:#ffaa00;">评价: 一般</span>')
        else:
            w.append('  <span style="color:#ff6b6b;">评价: 差（可能存在网络问题）</span>')
        self._status_label.setText("网络质量测试完成")

    def _tool_cookie_check(self):
        """Cookie 安全属性检测"""
        url, ok = QInputDialog.getText(
            self, "Cookie 安全检测", "目标 URL:", text="https://www.baidu.com")
        if not ok or not url.strip():
            return
        self._status_label.setText(f"分析 {url} Cookie 安全...")
        w = QTextEdit_style()
        idx = self._main_tabs.addTab(w, f"Cookie: {url[:40]}")
        self._main_tabs.setCurrentIndex(idx)
        self._cookie_worker = CookieSecurityWorker(url.strip())
        self._cookie_worker.result_ready.connect(
            lambda u, info, e: self._on_cookie_result(w, u, info, e))
        self._cookie_worker.start()

    def _on_cookie_result(self, w, url, info, err):
        w.append(f'<span style="color:#4ecdc4;">── Cookie 安全 {url} ──</span>')
        if err and not info.get("cookies"):
            w.append(f'<span style="color:#ff6b6b;">{err}</span>')
            self._status_label.setText("Cookie 检测失败")
            return
        cookies = info.get("cookies", [])
        if cookies:
            w.append(f'\n<span style="color:#4ecdc4;">[ Cookies ({len(cookies)}) ]</span>')
            for c in cookies:
                w.append(
                    f'  <span style="color:#aaa;">{c["name"]}</span> '
                    f'<span style="color:#888;">{c["domain"]}{c["path"]}</span>')
                if c.get("flags"):
                    flags = ", ".join(c["flags"])
                    w.append(
                        f'    <span style="color:#4ecdc4;">flags: {flags}</span>')
        else:
            w.append(f'  <span style="color:#888;">(未发现 Cookie)</span>')
        vulns = info.get("vulnerabilities", [])
        w.append(f'\n<span style="color:#4ecdc4;">[ 风险 ]</span>')
        if vulns:
            for v in vulns:
                w.append(f'  <span style="color:#ff6b6b;">⚠ {v}</span>')
        else:
            w.append('  <span style="color:#4ecdc4;">未发现明显问题</span>')
        self._status_label.setText("Cookie 检测完成")

    def _tool_http_methods(self):
        """允许的 HTTP 方法检测"""
        url, ok = QInputDialog.getText(
            self, "HTTP 方法检测", "目标 URL:", text="https://www.baidu.com")
        if not ok or not url.strip():
            return
        self._status_label.setText(f"探测 {url} 允许的方法...")
        w = QTextEdit_style()
        idx = self._main_tabs.addTab(w, f"HTTP方法: {url[:40]}")
        self._main_tabs.setCurrentIndex(idx)
        self._methods_worker = HTTPMethodsWorker(url.strip())
        self._methods_worker.result_ready.connect(
            lambda u, rs, e: self._on_methods_result(w, u, rs, e))
        self._methods_worker.start()

    def _on_methods_result(self, w, url, results, err):
        w.append(f'<span style="color:#4ecdc4;">── HTTP 方法 {url} ──</span>')
        for r in results:
            m = r.get("method", "?")
            if "error" in r:
                w.append(f'  <span style="color:#888;">{m:>7}: 错误 {r["error"]}</span>')
                continue
            status = r.get("status", "?")
            ok = r.get("ok", False)
            color = "#4ecdc4" if ok and status < 400 else (
                "#ffaa00" if status in (401, 403, 405) else "#ff6b6b")
            extra = ""
            if "Allow" in r:
                extra = f'  (Allow: {r["Allow"]})'
            w.append(
                f'  <span style="color:{color};">{m:>7}: {status}</span>{extra}')
        # 风险提示
        dangerous = [r["method"] for r in results
                     if r.get("ok") and r.get("method") in ("PUT", "DELETE", "TRACE")]
        if dangerous:
            w.append(
                f'\n  <span style="color:#ff6b6b;">⚠ 危险方法开放: '
                f'{", ".join(dangerous)}</span>')
        self._status_label.setText("HTTP 方法检测完成")

    def _tool_rdp_vnc(self):
        """RDP/VNC 远程桌面检测"""
        host, ok = QInputDialog.getText(
            self, "远程桌面检测", "目标主机:", text="127.0.0.1")
        if not ok or not host.strip():
            return
        self._status_label.setText(f"探测 {host} 远程桌面服务...")
        w = QTextEdit_style()
        idx = self._main_tabs.addTab(w, f"远程桌面: {host}")
        self._main_tabs.setCurrentIndex(idx)
        self._rdp_worker = RDPWorker(host.strip())
        self._rdp_worker.result_ready.connect(
            lambda h, rs: self._on_rdp_result(w, h, rs))
        self._rdp_worker.start()

    def _on_rdp_result(self, w, host, results):
        w.append(f'<span style="color:#4ecdc4;">── 远程桌面 {host} ──</span>')
        for name, info in results.items():
            port = info.get("port")
            reachable = info.get("reachable")
            if reachable:
                w.append(
                    f'  <span style="color:#ff6b6b;">● {name} (端口 {port}) 开放</span>')
                if info.get("banner"):
                    w.append(
                        f'    <span style="color:#aaa;">{info["banner"]}</span>')
            else:
                w.append(
                    f'  <span style="color:#888;">○ {name} (端口 {port}) '
                    f'未开放 / {info.get("error", "无响应")}</span>')
        # 风险提示
        opens = [n for n, i in results.items() if i.get("reachable")]
        if opens:
            w.append(
                f'\n  <span style="color:#ff6b6b;">⚠ 暴露在公网将面临暴力破解风险，'
                f'建议限制来源 IP 或启用双因素认证</span>')
        self._status_label.setText("远程桌面检测完成")

    def _tool_tls_inspect(self):
        """TLS 握手与证书深度检测"""
        host, ok = QInputDialog.getText(
            self, "TLS 深度检测", "目标域名:", text="www.baidu.com")
        if not ok or not host.strip():
            return
        self._status_label.setText(f"分析 {host} TLS 配置...")
        w = QTextEdit_style()
        idx = self._main_tabs.addTab(w, f"TLS: {host}")
        self._main_tabs.setCurrentIndex(idx)
        self._tls_worker = TLSInspectionWorker(host.strip())
        self._tls_worker.result_ready.connect(
            lambda h, info, e: self._on_tls_result(w, h, info, e))
        self._tls_worker.start()

    def _on_tls_result(self, w, host, info, err):
        w.append(f'<span style="color:#4ecdc4;">── TLS 检测 {host} ──</span>')
        if err and not info.get("tls_version"):
            w.append(f'<span style="color:#ff6b6b;">握手失败: {err}</span>')
            self._status_label.setText("TLS 检测失败")
            return
        if err:
            w.append(f'<span style="color:#ffaa00;">{err}</span>')
        # 协议与密码
        ver = info.get("tls_version", "")
        ver_color = "#4ecdc4" if ver in ("TLSv1.2", "TLSv1.3") else "#ff6b6b"
        w.append(f'  <span style="color:#aaa;">协议版本: </span>'
                 f'<span style="color:{ver_color};">{ver or "?"}</span>')
        cipher = info.get("cipher", "")
        w.append(f'  <span style="color:#aaa;">协商密码套件: </span>'
                 f'<span style="color:#aaa;">{cipher}</span>')
        alpn = info.get("alpn", "")
        if alpn:
            w.append(f'  <span style="color:#aaa;">ALPN: </span>'
                     f'<span style="color:#4ecdc4;">{alpn}</span>')
        # 证书
        w.append('\n<span style="color:#4ecdc4;">[ 证书 ]</span>')
        if info.get("cert_subject"):
            w.append(f'  <span style="color:#aaa;">主体: </span>{info["cert_subject"]}')
        if info.get("cert_issuer"):
            w.append(f'  <span style="color:#aaa;">颁发者: </span>{info["cert_issuer"]}')
        if info.get("cert_serial"):
            w.append(f'  <span style="color:#aaa;">序列号: </span>{info["cert_serial"]}')
        if info.get("cert_notbefore"):
            w.append(f'  <span style="color:#aaa;">生效: </span>{info["cert_notbefore"]}')
        if info.get("cert_notafter"):
            w.append(f'  <span style="color:#aaa;">到期: </span>{info["cert_notafter"]}')
        days = info.get("cert_days_left", 0)
        day_color = "#4ecdc4" if days > 30 else ("#ffaa00" if days > 7 else "#ff6b6b")
        if days:
            w.append(f'  <span style="color:#aaa;">剩余天数: </span>'
                     f'<span style="color:{day_color};">{days} 天</span>')
        sans = info.get("cert_san", [])
        if sans:
            w.append(f'  <span style="color:#aaa;">SAN ({len(sans)}): </span>')
            for s in sans[:10]:
                w.append(f'    <span style="color:#888;">- {s}</span>')
        # 风险
        if days and days < 7:
            w.append(f'\n  <span style="color:#ff6b6b;">⚠ 证书即将过期！</span>')
        if ver in ("TLSv1", "TLSv1.1", "SSLv3", "SSLv2"):
            w.append(f'\n  <span style="color:#ff6b6b;">⚠ 协议版本过旧，存在安全风险</span>')
        self._status_label.setText("TLS 检测完成")

    def _tool_mtr(self):
        """类 MTR 持续路由追踪"""
        host, ok = QInputDialog.getText(
            self, "MTR 路由追踪", "目标主机:", text="www.baidu.com")
        if not ok or not host.strip():
            return
        self._status_label.setText(f"MTR 追踪到 {host}...")
        w = QTextEdit_style()
        idx = self._main_tabs.addTab(w, f"MTR: {host}")
        self._main_tabs.setCurrentIndex(idx)
        self._mtr_worker = MTRLikeWorker(host.strip(), max_hops=15, cycles=3)
        self._mtr_worker.result_ready.connect(
            lambda h, info: self._on_mtr_result(w, h, info))
        self._mtr_worker.start()

    def _on_mtr_result(self, w, host, info):
        hop = info.get("hop", 0)
        ip = info.get("ip", "*")
        total = info.get("total", 0)
        ok = info.get("ok", 0)
        samples = info.get("samples", [])
        w.append(f'<span style="color:#4ecdc4;">── 路由追踪 {host} ──</span>')
        w.append(
            f'  <span style="color:#aaa;">跳数 {hop}: </span>'
            f'<span style="color:#4ecdc4;">{ip}</span>  '
            f'<span style="color:#aaa;">({ok}/{total})</span>')
        if samples:
            avg = sum(samples) / len(samples)
            mx = max(samples)
            mn = min(samples)
            w.append(
                f'    <span style="color:#aaa;">平均/最小/最大: </span>'
                f'<span style="color:#4ecdc4;">{avg:.1f} / {mn:.1f} / {mx:.1f} ms</span>')
            w.append(f'    <span style="color:#aaa;">样本: {samples}</span>')
        if ip != "*":
            w.append(f'  <span style="color:#4ecdc4;">✓ 到达目标</span>')
        self._status_label.setText("MTR 追踪完成")

    def _tool_ntp(self):
        """NTP 时间服务器检测"""
        host, ok = QInputDialog.getText(
            self, "NTP 时间检测", "NTP 服务器:",
            text="time.windows.com")
        if not ok or not host.strip():
            return
        self._status_label.setText(f"查询 {host} NTP 时间...")
        w = QTextEdit_style()
        idx = self._main_tabs.addTab(w, f"NTP: {host}")
        self._main_tabs.setCurrentIndex(idx)
        self._ntp_worker = NTPTimeWorker(host.strip())
        self._ntp_worker.result_ready.connect(
            lambda h, info: self._on_ntp_result(w, h, info))
        self._ntp_worker.start()

    def _on_ntp_result(self, w, host, info):
        w.append(f'<span style="color:#4ecdc4;">── NTP {host} ──</span>')
        if not info.get("ok"):
            w.append(f'  <span style="color:#ff6b6b;">失败: {info.get("error", "")}</span>')
            self._status_label.setText("NTP 检测失败")
            return
        w.append(f'  <span style="color:#aaa;">NTP 时间: </span>'
                 f'<span style="color:#4ecdc4;">{info.get("ntp_time")}</span>')
        off = info.get("offset_ms", 0)
        off_color = "#4ecdc4" if abs(off) < 1000 else "#ffaa00"
        w.append(f'  <span style="color:#aaa;">本地偏移: </span>'
                 f'<span style="color:{off_color};">{off:+.1f} ms</span>')
        w.append(f'  <span style="color:#aaa;">往返时延: </span>'
                 f'<span style="color:#aaa;">{info.get("rtt_ms", 0):.1f} ms</span>')
        self._status_label.setText("NTP 检测完成")

    def _tool_snmp(self):
        """SNMP 服务检测与 community 探测"""
        host, ok = QInputDialog.getText(
            self, "SNMP 检测", "目标主机:", text="127.0.0.1")
        if not ok or not host.strip():
            return
        self._status_label.setText(f"探测 {host} SNMP...")
        w = QTextEdit_style()
        idx = self._main_tabs.addTab(w, f"SNMP: {host}")
        self._main_tabs.setCurrentIndex(idx)
        self._snmp_worker = SNMPWorker(host.strip())
        self._snmp_worker.result_ready.connect(
            lambda h, info: self._on_snmp_result(w, h, info))
        self._snmp_worker.start()

    def _on_snmp_result(self, w, host, info):
        w.append(f'<span style="color:#4ecdc4;">── SNMP {host} ──</span>')
        if info.get("reachable"):
            w.append(f'  <span style="color:#ff6b6b;">● SNMP 服务可达</span>')
            comms = info.get("communities_found", [])
            if comms:
                w.append(f'  <span style="color:#ff6b6b;">⚠ 发现默认 community: '
                         f'{", ".join(comms)}</span>')
                w.append(f'  <span style="color:#aaa;">建议立即修改默认 community 字符串</span>')
            else:
                w.append(f'  <span style="color:#888;">未识别到默认 community 字符串</span>')
        else:
            w.append(f'  <span style="color:#4ecdc4;">○ SNMP 不可达或已禁用</span>')
            if info.get("error"):
                w.append(f'    <span style="color:#888;">{info["error"]}</span>')
        self._status_label.setText("SNMP 检测完成")

    def closeEvent(self, event):
        """关闭窗口时清理资源"""
        # 停止网速监控
        try:
            self._dashboard.cleanup()
        except Exception:
            pass

        # 停止企业级运维控制台的后台任务
        try:
            for i in range(self._main_tabs.count()):
                w = self._main_tabs.widget(i)
                if getattr(w, "_is_enterprise_ops", False) and hasattr(w, "stop_all"):
                    w.stop_all()
        except Exception:
            pass

        # 清理所有后台线程
        try:
            from app.dashboard import cleanup_all_threads
            cleanup_all_threads()
        except Exception:
            pass

        # 断开所有终端
        for tab in self._terminal_tabs:
            tab.disconnect()

        event.accept()


class QTextEdit_style(QTextEdit):
    """带样式的只读文本显示控件（终端/日志风格）"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("role", "terminal")
        self.setReadOnly(True)
