"""
AI Copilot 面板
右侧浮动辅助区：智能诊断台 + 快捷指令库 + 服务商管理
"""

import html

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QTreeWidget, QTreeWidgetItem, QComboBox,
    QSplitter, QLineEdit, QInputDialog, QMessageBox,
    QDialog, QFormLayout, QDialogButtonBox, QGroupBox,
    QTabWidget, QCheckBox, QStatusBar,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor

from app.ai_engine import (
    AIEngine, AIChatWorker, ModelFetchWorker,
    OllamaProvider, OpenAICompatibleProvider, PRESET_PROVIDERS,
)


# 预置快捷指令库
QUICK_COMMANDS = {
    "Nginx 排障": [
        ("查看连接数", "ss -s"),
        ("查看Nginx进程", "ps aux | grep nginx"),
        ("查看Nginx配置测试", "nginx -t"),
        ("查看访问日志(最后50行)", "tail -50 /var/log/nginx/access.log"),
        ("查看错误日志(最后50行)", "tail -50 /var/log/nginx/error.log"),
        ("重载Nginx配置", "nginx -s reload"),
        ("查看Nginx版本", "nginx -v"),
        ("测试虚拟主机配置", "nginx -T"),
    ],
    "系统监控": [
        ("查看CPU使用率", "top -bn1 | head -20"),
        ("查看内存使用", "free -h"),
        ("查看磁盘使用", "df -h"),
        ("查看IO状态", "iostat -x 1 3"),
        ("查看系统负载", "uptime"),
        ("查看进程树", "ps auxf | head -30"),
        ("查看登录用户", "who"),
        ("查看系统日志(最后30行)", "journalctl -n 30 --no-pager"),
        ("查看定时任务", "crontab -l"),
        ("查看环境变量", "env | sort"),
    ],
    "网络排障": [
        ("查看监听端口", "ss -tulnp"),
        ("查看TCP连接状态", "ss -s"),
        ("查看路由表", "ip route show"),
        ("查看DNS解析", "nslookup "),
        ("抓包(HTTP)", "tcpdump -i any port 80 -c 100"),
        ("查看防火墙规则", "iptables -L -n"),
        ("查看网卡配置", "ip addr show"),
        ("测试端口连通性", "nc -zv "),
        ("查看ARP缓存", "ip neigh show"),
        ("持续Ping测试", "ping -c 100 "),
    ],
    "Docker 排障": [
        ("查看容器列表", "docker ps -a"),
        ("查看容器日志", "docker logs --tail 100 "),
        ("查看容器资源使用", "docker stats --no-stream"),
        ("查看镜像列表", "docker images"),
        ("重启容器", "docker restart "),
        ("查看Docker网络", "docker network ls"),
        ("查看Docker卷", "docker volume ls"),
        ("查看容器详情", "docker inspect "),
        ("清理未使用资源", "docker system prune -f"),
        ("进入容器Shell", "docker exec -it  /bin/bash"),
    ],
    "数据库排障": [
        ("MySQL进程列表", "mysql -e 'SHOW PROCESSLIST;'"),
        ("MySQL状态", "mysql -e 'SHOW STATUS;'"),
        ("Redis连接数", "redis-cli info clients"),
        ("Redis内存使用", "redis-cli info memory"),
        ("Redis键数量", "redis-cli DBSIZE"),
        ("MySQL慢查询日志", "mysql -e \"SELECT * FROM mysql.slow_log ORDER BY start_time DESC LIMIT 20;\""),
        ("Redis慢查询", "redis-cli SLOWLOG GET 10"),
        ("PostgreSQL活动查询", "psql -c 'SELECT * FROM pg_stat_activity;'"),
        ("MongoDB状态", "mongo --eval 'db.serverStatus()'"),
    ],
    "Kubernetes 排障": [
        ("查看节点状态", "kubectl get nodes -o wide"),
        ("查看Pod状态", "kubectl get pods --all-namespaces"),
        ("查看Pod日志", "kubectl logs --tail=100 "),
        ("查看服务列表", "kubectl get svc --all-namespaces"),
        ("查看事件", "kubectl get events --sort-by='.lastTimestamp'"),
        ("查看部署状态", "kubectl get deployments --all-namespaces"),
        ("进入Pod容器", "kubectl exec -it  -- /bin/sh"),
        ("查看资源使用", "kubectl top nodes"),
    ],
    "Windows 排障": [
        ("查看系统信息", "systeminfo"),
        ("查看进程列表", "tasklist"),
        ("查看网络连接", "netstat -ano"),
        ("查看路由表", "route print"),
        ("查看防火墙状态", "netsh advfirewall show currentprofile"),
        ("查看服务状态", "sc query"),
        ("查看磁盘空间", "wmic logicaldisk get size,freespace,caption"),
        ("查看环境变量", "set"),
        ("查看ARP缓存", "arp -a"),
        ("查看IP配置", "ipconfig /all"),
    ],
    "安全审计": [
        ("查看最近登录失败", "lastb | head -20"),
        ("查看SSH登录记录", "cat /var/log/secure | grep sshd | tail -30"),
        ("查看 sudo 使用记录", "cat /var/log/auth.log | tail -30"),
        ("查找SUID文件", "find / -perm -4000 -type f 2>/dev/null"),
        ("查找SGID文件", "find / -perm -2000 -type f 2>/dev/null"),
        ("查看开放端口", "ss -tulnp"),
        ("查看计划任务", "crontab -l"),
        ("查看用户列表", "cat /etc/passwd"),
        ("查看组列表", "cat /etc/group"),
        ("检查文件完整性", "rpm -Va 2>/dev/null || dpkg -V 2>/dev/null"),
        ("查看当前登录用户", "w"),
        ("查看历史命令", "history | tail -30"),
        ("检查定时任务目录", "ls -la /etc/cron.*"),
        ("检查SSH密钥权限", "ls -la ~/.ssh/"),
        ("查看系统账户", "awk -F: '$3 < 1000 {print $1}' /etc/passwd"),
    ],
    "漏洞扫描": [
        ("检查系统更新", "apt update && apt list --upgradable 2>/dev/null || yum check-update 2>/dev/null"),
        ("CVE 检查", "grep -r CVE /var/log/apt/history.log 2>/dev/null | head -10"),
        ("检查已知漏洞", "lsb_release -a 2>/dev/null || cat /etc/os-release"),
        ("OpenSSL版本", "openssl version"),
        ("检查SSL证书到期", "openssl s_client -connect localhost:443 2>/dev/null | openssl x509 -noout -dates 2>/dev/null"),
    ],
    "防火墙管理": [
        ("查看防火墙状态", "ufw status 2>/dev/null || firewall-cmd --state 2>/dev/null"),
        ("查看UFW规则", "ufw status numbered 2>/dev/null"),
        ("查看iptables规则", "iptables -S"),
        ("查看ip6tables规则", "ip6tables -S"),
        ("允许SSH", "ufw allow ssh 2>/dev/null || firewall-cmd --add-service=ssh 2>/dev/null"),
        ("允许HTTP", "ufw allow http 2>/dev/null || firewall-cmd --add-service=http 2>/dev/null"),
        ("允许HTTPS", "ufw allow https 2>/dev/null || firewall-cmd --add-service=https 2>/dev/null"),
        ("禁止所有入站", "ufw default deny incoming 2>/dev/null"),
    ],
}


# ============================================================
# 服务商配置对话框
# ============================================================

class ProviderConfigDialog(QDialog):
    """服务商配置对话框 - 支持选择预设/自定义、自动获取模型、API Key 管理"""

    def __init__(self, ai_engine: AIEngine, parent=None):
        super().__init__(parent)
        self._ai_engine = ai_engine
        self._model_fetch_worker = None
        self._fetched_models = {}  # key -> [models]

        self.setWindowTitle("AI 服务商管理")
        self.setMinimumSize(640, 560)

        main_layout = QVBoxLayout(self)

        # ---- 服务商选择 ----
        select_group = QGroupBox("选择服务商")
        select_layout = QFormLayout(select_group)

        self._provider_combo = QComboBox()
        self._load_provider_list()
        self._provider_combo.currentIndexChanged.connect(self._on_provider_selected)
        select_layout.addRow("服务商:", self._provider_combo)

        # 状态指示
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("font-size: 11px;")
        select_layout.addRow("状态:", self._status_label)

        main_layout.addWidget(select_group)

        # ---- 配置区域（使用 Tab 切换 Ollama / 云端 API） ----
        self._config_tabs = QTabWidget()

        # Ollama 配置页
        ollama_page = QWidget()
        ollama_layout = QFormLayout(ollama_page)
        self._ollama_url = QLineEdit("http://localhost:11434")
        ollama_layout.addRow("Ollama 地址:", self._ollama_url)

        ollama_model_bar = QHBoxLayout()
        self._ollama_model_combo = QComboBox()
        self._ollama_model_combo.setEditable(True)
        self._ollama_model_combo.setMinimumWidth(220)
        ollama_model_bar.addWidget(self._ollama_model_combo, 1)

        self._btn_fetch_ollama = QPushButton("获取模型")
        self._btn_fetch_ollama.setMinimumWidth(90)
        self._btn_fetch_ollama.setMinimumHeight(28)
        self._btn_fetch_ollama.clicked.connect(self._fetch_ollama_models)
        ollama_model_bar.addWidget(self._btn_fetch_ollama)
        ollama_layout.addRow("模型:", ollama_model_bar)

        self._config_tabs.addTab(ollama_page, "Ollama (本地)")

        # 云端 API 配置页
        cloud_page = QWidget()
        cloud_layout = QFormLayout(cloud_page)

        self._api_url = QLineEdit()
        self._api_url.setPlaceholderText("https://api.example.com/v1")
        cloud_layout.addRow("API 地址:", self._api_url)

        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.Password)
        self._api_key.setPlaceholderText("sk-xxxxxxxxxxxxxxxx")
        cloud_layout.addRow("API Key:", self._api_key)

        # API Key 显示/隐藏
        key_toggle_bar = QHBoxLayout()
        self._btn_show_key = QPushButton("显示 Key")
        self._btn_show_key.setMinimumWidth(90)
        self._btn_show_key.setMinimumHeight(28)
        self._btn_show_key.setCheckable(True)
        self._btn_show_key.clicked.connect(self._toggle_key_visibility)
        key_toggle_bar.addWidget(self._btn_show_key)

        self._btn_test_key = QPushButton("测试连接")
        self._btn_test_key.setMinimumWidth(90)
        self._btn_test_key.setMinimumHeight(28)
        self._btn_test_key.clicked.connect(self._test_api_connection)
        key_toggle_bar.addWidget(self._btn_test_key)
        key_toggle_bar.addStretch()
        cloud_layout.addRow("", key_toggle_bar)

        model_bar = QHBoxLayout()
        self._cloud_model_combo = QComboBox()
        self._cloud_model_combo.setEditable(True)
        self._cloud_model_combo.setMinimumWidth(220)
        model_bar.addWidget(self._cloud_model_combo, 1)

        self._btn_fetch_cloud = QPushButton("获取模型")
        self._btn_fetch_cloud.setMinimumWidth(90)
        self._btn_fetch_cloud.setMinimumHeight(28)
        self._btn_fetch_cloud.clicked.connect(self._fetch_cloud_models)
        model_bar.addWidget(self._btn_fetch_cloud)
        cloud_layout.addRow("模型:", model_bar)

        self._config_tabs.addTab(cloud_page, "云端 API")

        main_layout.addWidget(self._config_tabs)

        # ---- 按钮 ----
        btn_bar = QHBoxLayout()
        btn_bar.addStretch()

        self._btn_save = QPushButton("保存配置")
        self._btn_save.setMinimumWidth(110)
        self._btn_save.setMinimumHeight(32)
        self._btn_save.setProperty("role", "primary")
        self._btn_save.clicked.connect(self._save_and_accept)
        btn_bar.addWidget(self._btn_save)

        cancel_btn = QPushButton("取消")
        cancel_btn.setMinimumWidth(90)
        cancel_btn.setMinimumHeight(32)
        cancel_btn.clicked.connect(self.reject)
        btn_bar.addWidget(cancel_btn)

        main_layout.addLayout(btn_bar)

        # 初始加载
        self._on_provider_selected(0)

    def _load_provider_list(self):
        """加载服务商列表到下拉框"""
        self._provider_combo.clear()
        for key, cfg in PRESET_PROVIDERS.items():
            name = cfg["name"]
            ptype = cfg.get("type", "")
            tag = "[本地]" if ptype == "ollama" else "[云端]"
            self._provider_combo.addItem(f"{tag} {name}", key)

    def _on_provider_selected(self, index: int):
        """切换服务商时加载对应配置"""
        if index < 0:
            return

        key = self._provider_combo.itemData(index)
        cfg = self._ai_engine.get_config(key) or PRESET_PROVIDERS.get(key, {})

        provider_type = cfg.get("type", "openai_compatible")

        if provider_type == "ollama":
            self._config_tabs.setCurrentIndex(0)
            self._ollama_url.setText(cfg.get("base_url", "http://localhost:11434"))

            # 填充模型下拉框
            self._ollama_model_combo.clear()
            current_model = cfg.get("model", "qwen2.5:7b")
            self._ollama_model_combo.addItem(current_model)

            self._status_label.setText("本地模型，无需 API Key")
            self._status_label.setStyleSheet("color: #4ecdc4; font-size: 11px;")
        else:
            self._config_tabs.setCurrentIndex(1)
            self._api_url.setText(cfg.get("base_url", ""))
            self._api_key.setText(cfg.get("api_key", ""))

            # 填充模型下拉框
            self._cloud_model_combo.clear()
            current_model = cfg.get("model", "")
            if current_model:
                self._cloud_model_combo.addItem(current_model)

            has_key = bool(cfg.get("api_key", ""))
            if has_key:
                self._status_label.setText("API Key 已配置")
                self._status_label.setStyleSheet("color: #4ecdc4; font-size: 11px;")
            else:
                self._status_label.setText("未配置 API Key")
                self._status_label.setStyleSheet("color: #ff6b6b; font-size: 11px;")

    def _toggle_key_visibility(self):
        """切换 API Key 显示/隐藏"""
        if self._btn_show_key.isChecked():
            self._api_key.setEchoMode(QLineEdit.Normal)
            self._btn_show_key.setText("隐藏 Key")
        else:
            self._api_key.setEchoMode(QLineEdit.Password)
            self._btn_show_key.setText("显示 Key")

    def _fetch_ollama_models(self):
        """获取 Ollama 模型列表"""
        self._btn_fetch_ollama.setEnabled(False)
        self._btn_fetch_ollama.setText("获取中...")
        self._status_label.setText("正在连接 Ollama...")
        self._status_label.setStyleSheet("color: #ffaa00; font-size: 11px;")

        key = self._provider_combo.currentData()
        # 临时创建 provider 用当前 URL
        temp_provider = OllamaProvider(
            base_url=self._ollama_url.text(),
            model="",
        )
        self._model_fetch_worker = ModelFetchWorker(key, temp_provider)
        self._model_fetch_worker.models_fetched.connect(self._on_ollama_models_fetched)
        self._model_fetch_worker.fetch_error.connect(self._on_fetch_error)
        self._model_fetch_worker.start()

    def _on_ollama_models_fetched(self, key: str, models: list):
        """Ollama 模型列表获取完成"""
        self._btn_fetch_ollama.setEnabled(True)
        self._btn_fetch_ollama.setText("获取模型")

        if models:
            current = self._ollama_model_combo.currentText()
            self._ollama_model_combo.clear()
            self._ollama_model_combo.addItems(models)
            # 恢复之前选中的模型
            idx = self._ollama_model_combo.findText(current)
            if idx >= 0:
                self._ollama_model_combo.setCurrentIndex(idx)

            self._status_label.setText(f"已获取 {len(models)} 个模型")
            self._status_label.setStyleSheet("color: #4ecdc4; font-size: 11px;")
        else:
            self._status_label.setText("未找到模型，请确认 Ollama 正在运行")
            self._status_label.setStyleSheet("color: #ff6b6b; font-size: 11px;")

    def _fetch_cloud_models(self):
        """获取云端 API 模型列表"""
        api_key = self._api_key.text().strip()
        base_url = self._api_url.text().strip()

        if not api_key:
            self._status_label.setText("请先输入 API Key")
            self._status_label.setStyleSheet("color: #ff6b6b; font-size: 11px;")
            return

        if not base_url:
            self._status_label.setText("请先输入 API 地址")
            self._status_label.setStyleSheet("color: #ff6b6b; font-size: 11px;")
            return

        self._btn_fetch_cloud.setEnabled(False)
        self._btn_fetch_cloud.setText("获取中...")
        self._status_label.setText("正在获取模型列表...")
        self._status_label.setStyleSheet("color: #ffaa00; font-size: 11px;")

        key = self._provider_combo.currentData()
        temp_provider = OpenAICompatibleProvider(
            api_key=api_key,
            base_url=base_url,
            model="",
            name="temp",
        )
        self._model_fetch_worker = ModelFetchWorker(key, temp_provider)
        self._model_fetch_worker.models_fetched.connect(self._on_cloud_models_fetched)
        self._model_fetch_worker.fetch_error.connect(self._on_fetch_error)
        self._model_fetch_worker.start()

    def _on_cloud_models_fetched(self, key: str, models: list):
        """云端模型列表获取完成"""
        self._btn_fetch_cloud.setEnabled(True)
        self._btn_fetch_cloud.setText("获取模型")

        if models:
            current = self._cloud_model_combo.currentText()
            self._cloud_model_combo.clear()
            self._cloud_model_combo.addItems(models)
            # 恢复之前选中的模型
            idx = self._cloud_model_combo.findText(current)
            if idx >= 0:
                self._cloud_model_combo.setCurrentIndex(idx)

            self._status_label.setText(f"已获取 {len(models)} 个模型")
            self._status_label.setStyleSheet("color: #4ecdc4; font-size: 11px;")
        else:
            self._status_label.setText("未获取到模型，请检查 API Key 和地址")
            self._status_label.setStyleSheet("color: #ff6b6b; font-size: 11px;")

    def _on_fetch_error(self, key: str, error: str):
        """模型获取失败"""
        self._btn_fetch_ollama.setEnabled(True)
        self._btn_fetch_ollama.setText("获取模型")
        self._btn_fetch_cloud.setEnabled(True)
        self._btn_fetch_cloud.setText("获取模型")
        self._status_label.setText(f"获取失败: {error}")
        self._status_label.setStyleSheet("color: #ff6b6b; font-size: 11px;")

    def _test_api_connection(self):
        """测试 API 连接"""
        api_key = self._api_key.text().strip()
        base_url = self._api_url.text().strip()
        model = self._cloud_model_combo.currentText().strip()

        if not api_key or not base_url:
            self._status_label.setText("请先填写 API Key 和地址")
            self._status_label.setStyleSheet("color: #ff6b6b; font-size: 11px;")
            return

        self._btn_test_key.setEnabled(False)
        self._btn_test_key.setText("测试中...")
        self._status_label.setText("正在测试连接...")
        self._status_label.setStyleSheet("color: #ffaa00; font-size: 11px;")

        # 使用一个简单的 chat 请求测试
        temp_provider = OpenAICompatibleProvider(
            api_key=api_key,
            base_url=base_url,
            model=model or "gpt-4o-mini",
            name="test",
        )
        result = temp_provider.chat([{"role": "user", "content": "Hi"}])

        self._btn_test_key.setEnabled(True)
        self._btn_test_key.setText("测试连接")

        if "[API" in result or "[连接" in result:
            self._status_label.setText(f"连接失败: {result[:80]}")
            self._status_label.setStyleSheet("color: #ff6b6b; font-size: 11px;")
        else:
            self._status_label.setText("连接成功!")
            self._status_label.setStyleSheet("color: #4ecdc4; font-size: 11px;")

    def _save_and_accept(self):
        """保存配置并关闭"""
        key = self._provider_combo.currentData()
        if not key:
            return

        preset = PRESET_PROVIDERS.get(key, {})
        provider_type = preset.get("type", "openai_compatible")

        if provider_type == "ollama":
            cfg = {
                "name": preset.get("name", "Ollama"),
                "type": "ollama",
                "base_url": self._ollama_url.text().strip(),
                "api_key": "",
                "model": self._ollama_model_combo.currentText().strip(),
            }
        else:
            cfg = {
                "name": preset.get("name", "Cloud API"),
                "type": "openai_compatible",
                "base_url": self._api_url.text().strip(),
                "api_key": self._api_key.text().strip(),
                "model": self._cloud_model_combo.currentText().strip(),
            }

        self._ai_engine.update_config(key, cfg)
        self.accept()


# ============================================================
# AI Copilot 面板
# ============================================================

class AICopilotPanel(QWidget):
    """AI Copilot 右侧面板"""

    send_command = Signal(str)  # 发送命令到终端
    request_completion = Signal(str, str)  # context, current_input

    def __init__(self, ai_engine: AIEngine, ssh_config=None, parent=None):
        super().__init__(parent)
        self._ai_engine = ai_engine
        self._ssh_config = ssh_config
        self._chat_history = []
        self._chat_worker = None

        self.setMinimumWidth(320)
        self.setMaximumWidth(500)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # ---- AI 引擎选择栏 ----
        provider_bar = QHBoxLayout()
        provider_label = QLabel("AI 引擎:")
        provider_label.setStyleSheet("color: #aaa;")
        provider_bar.addWidget(provider_label)

        self._provider_combo = QComboBox()
        self._refresh_provider_combo()
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        provider_bar.addWidget(self._provider_combo, 1)

        # 模型显示
        self._model_label = QLabel("")
        self._model_label.setStyleSheet("color: #888; font-size: 11px;")
        self._model_label.setMinimumWidth(60)
        provider_bar.addWidget(self._model_label)

        self._btn_config = QPushButton("管理")
        self._btn_config.setFixedWidth(50)
        self._btn_config.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 3px 8px;
            }
            QPushButton:hover { background-color: #1a8ae8; }
        """)
        self._btn_config.clicked.connect(self._show_config_dialog)
        provider_bar.addWidget(self._btn_config)

        layout.addLayout(provider_bar)

        # ---- 分割：诊断台 + 快捷指令 ----
        splitter = QSplitter(Qt.Vertical)

        # 智能诊断台
        chat_group = QWidget()
        chat_layout = QVBoxLayout(chat_group)
        chat_layout.setContentsMargins(0, 0, 0, 0)

        chat_title = QLabel("智能诊断台")
        chat_title.setStyleSheet("color: #4ecdc4; font-weight: bold; font-size: 13px;")
        chat_layout.addWidget(chat_title)

        # 对话显示区
        self._chat_display = QTextEdit()
        self._chat_display.setReadOnly(True)
        self._chat_display.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a2e;
                color: #e0e0e0;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
            }
        """)
        chat_layout.addWidget(self._chat_display)

        # 状态标签（显示"正在思考..."）
        self._status_label_thinking = QLabel("")
        self._status_label_thinking.setStyleSheet("color: #888; font-size: 11px; padding: 2px 4px;")
        self._status_label_thinking.setAlignment(Qt.AlignRight)
        chat_layout.addWidget(self._status_label_thinking)

        # 工具栏：AI 辅助操作
        tools_bar = QHBoxLayout()
        self._btn_analyze_ssh = QPushButton("分析SSH日志")
        self._btn_analyze_ssh.setStyleSheet("""
            QPushButton {
                background-color: #3d3d3d;
                color: #cccccc;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 4px 10px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #0078d4; color: white; }
        """)
        self._btn_analyze_ssh.clicked.connect(self._analyze_ssh_logs)
        tools_bar.addWidget(self._btn_analyze_ssh)
        tools_bar.addStretch()
        chat_layout.addLayout(tools_bar)

        # 输入区
        input_bar = QHBoxLayout()
        self._chat_input = QLineEdit()
        self._chat_input.setPlaceholderText("输入问题或描述故障现象...")
        self._chat_input.setStyleSheet("""
            QLineEdit {
                background-color: #2d2d2d;
                color: #cccccc;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        self._chat_input.returnPressed.connect(self._send_chat)
        input_bar.addWidget(self._chat_input)

        self._btn_send = QPushButton("发送")
        self._btn_send.setFixedWidth(60)
        self._btn_send.clicked.connect(self._send_chat)
        input_bar.addWidget(self._btn_send)

        chat_layout.addLayout(input_bar)
        splitter.addWidget(chat_group)

        # 快捷指令库
        cmd_group = QWidget()
        cmd_layout = QVBoxLayout(cmd_group)
        cmd_layout.setContentsMargins(0, 0, 0, 0)

        cmd_title = QLabel("快捷指令库 (双击发送到终端)")
        cmd_title.setStyleSheet("color: #ff6b6b; font-weight: bold; font-size: 13px;")
        cmd_layout.addWidget(cmd_title)

        self._cmd_tree = QTreeWidget()
        self._cmd_tree.setHeaderHidden(True)
        self._cmd_tree.setIndentation(16)
        self._cmd_tree.setWordWrap(True)
        self._cmd_tree.setTextElideMode(Qt.ElideNone)
        self._cmd_tree.setUniformRowHeights(False)
        self._cmd_tree.setColumnCount(1)
        self._cmd_tree.setColumnWidth(0, 200)
        self._cmd_tree.setStyleSheet("""
            QTreeWidget {
                background-color: #1e1e1e;
                color: #cccccc;
                border: 1px solid #333;
                border-radius: 4px;
                font-family: Consolas;
                font-size: 12px;
            }
            QTreeWidget::item {
                padding: 2px 0px;
                min-height: 18px;
            }
            QTreeWidget::item:selected {
                background-color: #2d5a8a;
            }
            QTreeWidget::item:hover {
                background-color: #2d2d2d;
            }
            QTreeWidget::branch:has-children {
                padding-left: 4px;
            }
        """)
        self._cmd_tree.itemDoubleClicked.connect(self._on_command_double_clicked)
        self._load_quick_commands()
        cmd_layout.addWidget(self._cmd_tree)

        splitter.addWidget(cmd_group)

        # 设置分割比例
        splitter.setSizes([400, 300])
        layout.addWidget(splitter)

        # 初始更新模型显示
        self._update_model_label()

    def _refresh_provider_combo(self):
        """刷新服务商下拉框"""
        self._provider_combo.blockSignals(True)
        self._provider_combo.clear()

        providers = self._ai_engine.list_providers()
        current_key = self._ai_engine.get_current_provider_key()

        select_idx = 0
        for i, (key, name) in enumerate(providers.items()):
            cfg = self._ai_engine.get_config(key)
            ptype = cfg.get("type", "") if cfg else ""
            tag = "[本地]" if ptype == "ollama" else "[云端]"

            # 显示是否已配置 API Key
            has_key = bool(cfg.get("api_key", "")) if cfg else True
            status = "" if has_key or ptype == "ollama" else " (未配置)"

            self._provider_combo.addItem(f"{tag} {name}{status}", key)
            if key == current_key:
                select_idx = i

        self._provider_combo.setCurrentIndex(select_idx)
        self._provider_combo.blockSignals(False)

    def _on_provider_changed(self, index: int):
        """切换服务商"""
        key = self._provider_combo.itemData(index)
        if key:
            self._ai_engine.set_current_provider(key)
            self._update_model_label()

    def _update_model_label(self):
        """更新当前模型显示"""
        provider = self._ai_engine.get_current_provider()
        if provider:
            model = getattr(provider, "model", "")
            self._model_label.setText(model[:20] if model else "")
            self._model_label.setToolTip(model)
        else:
            self._model_label.setText("")

    def _show_config_dialog(self):
        """显示服务商配置对话框"""
        dialog = ProviderConfigDialog(self._ai_engine, self)
        if dialog.exec() == QDialog.Accepted:
            self._refresh_provider_combo()
            self._update_model_label()

    def _load_quick_commands(self):
        """加载预置快捷指令"""
        for category, commands in QUICK_COMMANDS.items():
            cat_item = QTreeWidgetItem(self._cmd_tree, [category])
            cat_item.setExpanded(True)
            for name, cmd in commands:
                cmd_item = QTreeWidgetItem(cat_item, [name])
                cmd_item.setData(0, Qt.UserRole, cmd)
                cmd_item.setToolTip(0, cmd)

    def _on_command_double_clicked(self, item: QTreeWidgetItem, column: int):
        """双击快捷指令，发送到终端"""
        cmd = item.data(0, Qt.UserRole)
        if cmd:
            self.send_command.emit(cmd)

    def _send_chat(self):
        """发送对话到AI"""
        text = self._chat_input.text().strip()
        if not text:
            return

        self._chat_input.clear()

        # 显示用户消息（HTML转义防止特殊字符破坏显示）
        self._append_chat_message("用户", text, "#4ecdc4")

        # 添加到历史
        self._chat_history.append({"role": "user", "content": text})

        # 禁用输入，显示状态
        self._chat_input.setEnabled(False)
        self._btn_send.setEnabled(False)
        self._status_label_thinking.setText("正在思考...")

        # 启动AI工作线程
        messages = [{"role": "system", "content": "你是一个专业的网络与服务器诊断助手。使用中文回答，给出具体的命令时用代码块包裹。"}]
        messages.extend(self._chat_history[-10:])

        self._chat_worker = AIChatWorker(self._ai_engine, messages)
        self._chat_worker.response_ready.connect(self._on_chat_response)
        self._chat_worker.error_occurred.connect(self._on_chat_error)
        self._chat_worker.start()

    def _on_chat_response(self, response: str):
        """AI响应回调"""
        self._chat_input.setEnabled(True)
        self._btn_send.setEnabled(True)
        self._status_label_thinking.setText("")

        self._append_chat_message("AI", response, "#ff6b6b")
        self._chat_history.append({"role": "assistant", "content": response})

    def _on_chat_error(self, error: str):
        """AI错误回调"""
        self._chat_input.setEnabled(True)
        self._btn_send.setEnabled(True)
        self._status_label_thinking.setText("")
        self._append_chat_message("错误", error, "#ff0000")

    def _append_chat_message(self, sender: str, text: str, color: str):
        """追加聊天消息（自动HTML转义）"""
        safe_text = html.escape(text).replace("\n", "<br>")
        self._chat_display.append(
            f'<span style="color:{color}; font-weight:bold;">[{sender}]</span> '
            f'<span style="color:#e0e0e0;">{safe_text}</span>'
        )

    def show_diagnosis(self, context: str):
        """从仪表盘触发的AI诊断"""
        self._append_chat_message("系统", "检测到网络异常，正在自动诊断...", "#ffaa00")
        self._chat_input.setEnabled(False)
        self._status_label_thinking.setText("正在诊断...")

        messages = [
            {"role": "system", "content": "你是一个专业的网络与服务器诊断助手。使用中文回答，简洁明了。"},
            {"role": "user", "content": f"一键体检发现以下异常，请诊断原因并给出修复建议：\n\n{context}"},
        ]

        self._chat_worker = AIChatWorker(self._ai_engine, messages)
        self._chat_worker.response_ready.connect(self._on_chat_response)
        self._chat_worker.error_occurred.connect(self._on_chat_error)
        self._chat_worker.start()

    def _analyze_ssh_logs(self):
        """将SSH连接日志发送给AI分析"""
        if not self._ssh_config:
            self._append_chat_message("系统", "SSH配置管理器未初始化，无法读取日志", "#ffaa00")
            return

        logs = self._ssh_config.get_error_log(20)
        if not logs:
            self._append_chat_message("系统", "暂无SSH错误日志", "#4ecdc4")
            return

        # 构建日志上下文
        lines = ["以下是最新的SSH连接错误日志，请分析原因并给出排查建议：\n"]
        import time
        for entry in logs:
            time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.timestamp))
            lines.append(
                f"[{time_str}] {entry.username}@{entry.host}:{entry.port} "
                f"(认证方式: {entry.auth_type}, 耗时: {entry.duration_ms}ms) - 错误: {entry.error_message}"
            )

        context = "\n".join(lines)

        self._append_chat_message("系统", "正在将SSH错误日志发送给AI分析...", "#ffaa00")
        self._chat_input.setEnabled(False)
        self._btn_send.setEnabled(False)
        self._status_label_thinking.setText("正在分析SSH日志...")

        messages = [
            {"role": "system", "content": "你是一个专业的SSH与服务器连接诊断助手。使用中文回答，分析SSH连接失败的可能原因并给出具体的修复建议。"},
            {"role": "user", "content": context},
        ]

        self._chat_worker = AIChatWorker(self._ai_engine, messages)
        self._chat_worker.response_ready.connect(self._on_chat_response)
        self._chat_worker.error_occurred.connect(self._on_chat_error)
        self._chat_worker.start()
