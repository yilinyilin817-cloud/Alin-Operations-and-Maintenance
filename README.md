# Alin-Operations-and-Maintenance

> 企业级网络运维与安全检测一体化桌面工具
> 集成网络探测、SSH 终端、批量执行、文件分发、告警中心、审计日志、定时任务等十余项运维能力

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-4ecdc4)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Qt](https://img.shields.io/badge/PySide6-6.5%2B-green)
![License](https://img.shields.io/badge/license-MIT-orange)

---

## 📑 目录

- [功能特性](#-功能特性)
- [项目结构](#-项目结构)
- [快速开始](#-快速开始)
- [技术栈](#-技术栈)
- [架构设计](#-架构设计)
- [模块详解](#-模块详解)
- [网络/安全检测工具清单](#-网络安全检测工具清单)
- [运维控制台](#-运维控制台)
- [开发指南](#-开发指南)
- [打包发布](#-打包发布)
- [常见问题](#-常见问题)
- [版本与许可](#-版本与许可)

---

## ✨ 功能特性

### 🌐 网络探测
- 13 类网络工具：Ping / TCP Ping / 端口扫描 / 路由追踪 / 类 MTR / DNS 查询 / HTTP 检测 / WHOIS / IPv6 / 网络质量 / 公网 IP / NTP / 扩展 DNS 记录

### 🛡 安全检测
- 15+ 类安全工具：SSL/TLS 深度检测 / 危险端口扫描 / 服务识别 / HTTP 安全头 / Cookie 安全 / CORS 错误 / CDN & WAF 识别 / 密码强度 / 密码生成 / SQL 注入 / XSS / 目录爆破 / 子域名枚举 / HTTP 压力 / TCP 洪水 / 服务器信息 / 邮件服务 / WebSocket / RDP-VNC / SNMP / MAC 厂商查询 / FTP / SMB / SSH 弱密码 / 横幅获取

### 🖥 SSH 终端
- 多标签页 SSH 终端，支持连接管理、命令历史、AI 命令补全
- 集成密码 / 私钥认证

### 🛠 企业级运维控制台
- **资产管理**：分组 / 标签 / CSV·JSON 导入导出 / 复制主机 / 标签云过滤
- **实时监控**：CPU / 内存 / 磁盘 / 网络流量多指标轮询
- **日志分析**：远程日志查看、关键字搜索
- **进程管理**：Top 进程 / 按 PID 杀进程（SIGTERM / SIGKILL / SIGHUP）
- **服务可用性**：HTTP / TCP 健康检查 / 告警阈值 / Webhook
- **批量执行**：多主机并发 / 命令模板 / 执行历史
- **文件分发**：SFTP 上传下载 / 多主机并发 / 进度可视化
- **定时任务**：标准 5 段 cron 表达式 / 执行历史
- **告警中心**：告警规则 / 多渠道通知 / 抑制 / 静默
- **审计日志**：所有操作可追溯 / CSV 导出

### 🤖 AI 助手
- 命令自然语言生成
- 风险评估与解释
- 上下文相关补全

---

## 📂 项目结构

```
Alin-Operations-and-Maintenance/
├── main.py                          # 应用入口
├── requirements.txt                 # Python 依赖
├── .gitignore
├── README.md
├── build.spec                       # PyInstaller 打包配置
│
├── app/                             # 核心代码
│   ├── __init__.py
│   ├── main_window.py               # 主窗口
│   ├── side_nav.py                  # 侧边栏
│   ├── title_bar.py                 # 标题栏
│   ├── theme.py                     # 主题与样式常量
│   ├── dashboard.py                 # 仪表盘
│   ├── workers.py                   # 通用后台任务
│   │
│   ├── network_probe.py             # 33 个网络/安全检测 Worker
│   ├── network_capture.py           # 抓包模块
│   ├── security_tools.py            # 安全工具桥接
│   ├── ssh_config.py                # SSH 配置管理
│   ├── ssh_terminal.py              # SSH 终端
│   ├── ansi_parser.py               # ANSI 颜色解析
│   │
│   ├── ai_engine.py                 # AI 命令生成 / 风险评估
│   ├── ai_panel.py                  # AI 助手侧边面板
│   │
│   ├── enterprise_ops.py            # 运维控制台（10 个标签页）
│   ├── audit_log.py                 # 审计日志
│   ├── alert_center.py              # 告警中心
│   ├── file_distribution.py         # 文件分发
│   ├── scheduled_tasks.py           # 定时任务（cron 解析）
│   │
│   ├── icon_loader.py               # 图标加载
│   ├── splash.py                    # 启动屏
│   ├── about_dialog.py              # 关于对话框
│   │
│   ├── plugins/                     # 插件目录
│   │   ├── __init__.py
│   │   ├── port_scan_enhanced.py
│   │   ├── security_audit.py
│   │   ├── traffic_analyzer.py
│   │   └── vuln_scanner.py
│   │
│   └── resources/
│       └── style.qss                # 全局样式表
│
└── docs/                            # 文档
    └── DEVELOPMENT.md               # 本开发文档
```

---

## 🚀 快速开始

### 环境要求

| 项目      | 版本                  |
| --------- | --------------------- |
| Python    | 3.11 及以上           |
| 操作系统  | Windows 10/11、macOS、Linux |
| 磁盘空间  | 至少 500 MB           |

### 安装

```bash
# 1. 克隆仓库
git clone https://github.com/yilinyilin817-cloud/Alin-Operations-and-Maintenance.git
cd Alin-Operations-and-Maintenance

# 2. 创建虚拟环境（可选但推荐）
python -m venv venv
# Windows
.\venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动应用
python main.py
```

### 一键启动（Windows）

双击 `main.py` 或在终端执行：

```powershell
python main.py
```

---

## 🧰 技术栈

| 层级       | 选型                          |
| ---------- | ----------------------------- |
| GUI 框架   | PySide6（Qt 6 for Python）    |
| 异步       | QThread + Signal/Slot         |
| 网络       | socket / ssl / urllib 标准库  |
| 远程       | paramiko (SSH / SFTP)         |
| 加密       | cryptography / bcrypt / nacl |
| 数据       | JSON / CSV（无外部 DB）       |
| 打包       | PyInstaller（见 build.spec）  |

> 项目坚持**零外部运行时依赖**：核心检测功能只使用 Python 标准库；外部库仅用于 SSH 和加密。

---

## 🏗 架构设计

### 分层架构

```
┌──────────────────────────────────────────────────────┐
│  UI 层 (PySide6)                                      │
│  MainWindow / SideNav / TitleBar / Dashboard          │
│  + 工具方法（_tool_*）                                │
└──────────────┬───────────────────────────────────────┘
               │  Signal / Slot
┌──────────────┴───────────────────────────────────────┐
│  业务层                                              │
│  NetworkProbe / EnterpriseOps / AI Engine            │
│  AuditLog / AlertCenter / FileDistribution           │
│  ScheduledTasks                                      │
└──────────────┬───────────────────────────────────────┘
               │  QThread
┌──────────────┴───────────────────────────────────────┐
│  Worker 层（一次性后台任务）                          │
│  PingWorker / PortScanWorker / ...（33+ 个）         │
│  SSHCommandWorker / BatchSSHCommandWorker            │
└──────────────┬───────────────────────────────────────┘
               │
┌──────────────┴───────────────────────────────────────┐
│  基础设施层                                          │
│  socket / ssl / urllib / paramiko / subprocess       │
└──────────────────────────────────────────────────────┘
```

### 关键设计原则

1. **后台任务统一 QThread**：所有耗时操作都用 `QThread` + `Signal` 异步执行，UI 永不卡顿
2. **Worker 即插即用**：每个 Worker 都是独立类，可单独复用
3. **审计先行**：敏感操作（杀进程、批量执行、文件分发、告警）都写入 `audit_log`
4. **持久化零依赖**：所有配置 / 状态用 JSON 文件
5. **延迟加载**：大模块（AI 引擎、定时任务、文件分发）按需 import

---

## 🔍 模块详解

### `main.py` — 应用入口

```python
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Alin Ops")
    splash = SplashScreen()
    splash.show()
    window = MainWindow()
    window.show()
    splash.finish(window)
    sys.exit(app.exec())
```

### `app/main_window.py` — 主窗口

- 自定义标题栏 + 侧边栏 + 主内容区
- 网络/安全工具菜单按分类组织
- 集成 SSH 终端、AI 面板、运维控制台、设置等

### `app/network_probe.py` — 33 个检测 Worker

每种检测都对应一个 `QThread` 子类，通过 `Signal` 回调结果：

| Worker                | 说明                                 |
| --------------------- | ------------------------------------ |
| `PingWorker`          | ICMP Ping 探测                       |
| `TCPPingWorker`       | TCP 握手测连通性                     |
| `PortScanWorker`      | TCP 端口扫描                         |
| `TracerouteWorker`    | 路由追踪                             |
| `MTRLikeWorker`       | 类 MTR，每跳多次采样                 |
| `DnsLookupWorker`     | DNS 基础查询                         |
| `DNSRecordsWorker`    | A/AAAA/MX/NS/TXT/SOA/CNAME/SRV       |
| `HttpCheckWorker`     | HTTP 可用性                          |
| `HTTPResponseHeadersWorker` | 完整响应头 + 安全头分析         |
| `HTTPMethodsWorker`   | 允许的 HTTP 方法探测                 |
| `CookieSecurityWorker`| Cookie HttpOnly/Secure/SameSite 审计 |
| `CORSWorker`          | CORS 配置错误检测                    |
| `CDNWAFWorker`        | CDN / WAF 指纹识别                   |
| `WebSocketWorker`     | WebSocket 握手测试                   |
| `WhoisWorker`         | WHOIS 查询                           |
| `SSLCheckerWorker`    | SSL 证书信息                         |
| `TLSInspectionWorker` | TLS 握手 + 证书深度                  |
| `GeoLocationWorker`   | IP 地理位置                          |
| `NetworkQualityWorker`| 延迟/抖动/丢包率                     |
| `VulnerablePortScanWorker` | 危险端口扫描                    |
| `ServiceIdentifyWorker` | 服务识别                            |
| `SecurityHeadersWorker` | HTTP 安全头分析                     |
| `CookieSecurityWorker`| Cookie 安全                          |
| `PasswordStrengthWorker` | 密码强度评估                      |
| `PasswordGeneratorWorker` | 安全密码生成                     |
| `SQLInjectionDetectWorker` | SQL 注入漏洞检测                |
| `XSSDetectWorker`     | XSS 漏洞检测                         |
| `DirectoryBusterWorker` | 目录爆破                            |
| `SubdomainEnumerationWorker` | 子域名枚举                    |
| `HttpLoadTestWorker`  | HTTP 压力测试                        |
| `TCPFloodTestWorker`  | TCP 洪水测试                         |
| `FTPAnonymousWorker`  | FTP 匿名登录检测                     |
| `SMBEnumerationWorker`| SMB 服务枚举                         |
| `SSHWeakPasswordWorker`| SSH 弱密码检测                      |
| `BannerGrabWorker`    | 横幅抓取                             |
| `ServerInfoWorker`    | 服务器信息收集                       |
| `PortEnumerationWorker` | 全量端口枚举                       |
| `IPv6SupportWorker`   | IPv6 连通性                          |
| `MailServerWorker`    | SMTP/POP3/IMAP 检测                  |
| `PublicIPWorker`      | 公网 IP                              |
| `MACVendorWorker`     | MAC OUI 厂商查询                     |
| `NTPTimeWorker`       | NTP 时间同步                         |
| `RDPWorker`           | RDP / VNC 远程桌面                   |
| `SNMPWorker`          | SNMP 服务 + community 探测          |
| `PluginDownloadWorker` | 插件下载                            |

### `app/enterprise_ops.py` — 运维控制台

10 个标签页（懒加载，失败隔离）：

| #  | 标签名          | 实现                    |
| -- | --------------- | ----------------------- |
| 0  | 🗂 资产管理     | `AssetManagerWidget`    |
| 1  | 📊 实时监控     | `MonitorWidget`         |
| 2  | 📜 日志分析     | `LogAnalyzerWidget`     |
| 3  | ⚙ 进程管理     | `ProcessManagerWidget`  |
| 4  | 💓 服务可用性   | `ServiceMonitorWidget`  |
| 5  | 🚀 批量执行     | `BatchExecWidget`       |
| 6  | 📤 文件分发     | `FileDistributionWidget`|
| 7  | ⏰ 定时任务     | `ScheduledTasksWidget`  |
| 8  | 🔔 告警中心     | `AlertCenterWidget`     |
| 9  | 📝 审计日志     | `AuditLogWidget`        |

### `app/audit_log.py` — 审计日志

- 全局 `audit(action, target, result, details)` 入口
- 操作可被多模块订阅
- JSON 持久化，支持过滤 / 导出

### `app/alert_center.py` — 告警中心

- 告警规则（指标 / 阈值 / 持续时间 / 严重度）
- 通知渠道（system / sound / webhook）
- 告警抑制 / 静默
- 历史记录

### `app/scheduled_tasks.py` — 定时任务

- 标准 5 段 cron 表达式解析
- 下次执行时间计算
- 执行历史
- 与批量执行模块联动

### `app/file_distribution.py` — 文件分发

- SFTP 多主机并发上传/下载
- 实时进度条 + 速度
- 失败重试

### `app/ai_engine.py` — AI 引擎

- 命令自然语言生成（如"查看 C 盘空间"→ `df -h`）
- 命令风险评估
- 上下文相关补全

---

## 🛠 网络/安全检测工具清单

### 网络工具（15 项）

| 工具               | 入口                         |
| ------------------ | ---------------------------- |
| 📡 Ping 探测       | `_tool_ping`                 |
| 🔌 TCP Ping        | `_tool_tcp_ping`             |
| 🔌 端口扫描        | `_tool_port_scan`            |
| 🗺 路由追踪        | `_tool_traceroute`           |
| 🛰 类 MTR 追踪     | `_tool_mtr`                  |
| 🔍 DNS 查询        | `_tool_dns`                  |
| 📑 扩展 DNS 记录   | `_tool_dns_extended`         |
| 🌐 HTTP 检测       | `_tool_http`                 |
| 📑 HTTP 响应头     | `_tool_http_headers`         |
| 🔧 HTTP 方法检测   | `_tool_http_methods`         |
| 🌐 IPv6 支持       | `_tool_ipv6_check`           |
| ⏱ 网络质量测试     | `_tool_network_quality`      |
| 📡 公网 IP         | `_tool_public_ip`            |
| 📋 WHOIS 查询      | `_tool_whois`                |
| 🕒 NTP 时间        | `_tool_ntp`                  |

### 安全工具（28 项）

| 工具               | 入口                            |
| ------------------ | ------------------------------- |
| 🔒 SSL 证书检测    | `_tool_ssl_check`               |
| 🔍 TLS 深度检测    | `_tool_tls_inspect`             |
| 📍 IP 地理位置     | `_tool_geo_location`            |
| ⚠ 危险端口扫描     | `_tool_vuln_port_scan`          |
| 🏷 服务识别        | `_tool_service_identify`        |
| 🛡 HTTP 安全头     | `_tool_security_headers`        |
| 🍪 Cookie 安全     | `_tool_cookie_check`            |
| 🌐 CORS 检测       | `_tool_cors_check`              |
| 🛰 CDN/WAF 检测    | `_tool_cdn_waf`                 |
| 🔑 密码强度检测    | `_tool_password_strength`       |
| ✨ 生成安全密码    | `_tool_password_generate`       |
| 💉 SQL 注入检测    | `_tool_sql_injection`           |
| 📄 XSS 漏洞检测    | `_tool_xss_detect`              |
| 📂 目录爆破        | `_tool_directory_buster`        |
| 🌍 子域名枚举      | `_tool_subdomain_enum`          |
| ⚡ HTTP 压力测试   | `_tool_http_load_test`          |
| 🌊 TCP 洪水测试    | `_tool_tcp_flood`               |
| 🖥 服务器信息收集  | `_tool_server_info`             |
| 📧 邮件服务器检测  | `_tool_mail_server`             |
| 📡 WebSocket 测试  | `_tool_websocket`               |
| 💳 RDP/VNC 检测    | `_tool_rdp_vnc`                 |
| 🔌 SNMP 检测       | `_tool_snmp`                    |
| 📡 MAC 厂商查询    | `_tool_mac_vendor`              |
| 📁 FTP 匿名检测    | `_tool_ftp_anonymous`           |
| 📦 SMB 服务枚举    | `_tool_smb_enum`                |
| 🔐 SSH 弱密码检测  | `_tool_ssh_weak_password`       |
| 🏴 服务横幅获取    | `_tool_banner_grab`             |
| 🔎 端口全量扫描    | `_tool_port_enumeration`        |
| 🧩 插件管理器      | `_tool_plugin_manager`          |

---

## 💼 运维控制台

### 资产管理

- **分组 + 标签**：双维度组织主机
- **批量导入/导出**：CSV（含中文表头）/ JSON
- **冲突策略**：覆盖 / 跳过 / 终止
- **标签云过滤**：按使用频次着色，点击切换
- **复制主机**：深拷贝，自动命名 `<name>_副本`

### 实时监控

- CPU / 内存 / 磁盘 / 网络流量
- 自定义采样间隔
- 历史曲线

### 进程管理

- Top N 进程（按 CPU/内存排序）
- 按 PID 杀进程（SIGTERM / SIGKILL / SIGHUP）
- 自动识别 Windows / Linux
- 关键 PID 警告（1 / 0）

### 服务可用性

- HTTP / TCP 探测
- 连续失败阈值 + 恢复阈值
- Webhook 通知（支持自定义 header）
- 告警历史

### 批量执行

- 多主机并发执行
- 命令模板（导入/导出/管理）
- 执行历史（最近 50 条）
- 双击回填

### 文件分发

- SFTP 上传/下载
- 多主机并发
- 实时进度 + 速度
- 失败重试

### 定时任务

- 标准 5 段 cron 表达式
- 下次执行时间预览
- 执行历史
- 与批量执行 / 文件分发联动

### 告警中心

- 规则：指标 + 阈值 + 持续时间 + 严重度
- 渠道：系统通知 / 声音 / Webhook
- 抑制 / 静默
- 历史记录

### 审计日志

- 全局操作追踪
- 按动作 / 用户 / 时间过滤
- CSV 导出

---

## 👨‍💻 开发指南

### 添加新的检测 Worker

1. 在 `app/network_probe.py` 末尾添加新类，继承 `QThread`：

```python
class MyNewWorker(QThread):
    result_ready = Signal(str, dict)  # 自定义 Signal

    def __init__(self, host: str, **kwargs):
        super().__init__()
        self.host = host
        # 保存参数...

    def run(self):
        try:
            # 执行检测
            result = do_something(self.host)
            self.result_ready.emit(self.host, result)
        except Exception as e:
            self.result_ready.emit(self.host, {"error": str(e)})
```

2. 在 `app/main_window.py` 导入新类
3. 添加 `_tool_my_new(self)` 方法
4. 在 `_show_tool_category` 中注册入口

### 添加新的运维控制台标签页

1. 在 `app/enterprise_ops.py` 创建新 Widget
2. 在 `EnterpriseOpsWidget.__init__` 中延迟导入并 `addTab`

### 调试技巧

- 使用 `audit()` 记录关键操作
- 所有 QThread 必须在 `closeEvent` 中 `wait()` 避免僵尸线程
- Signal 名称采用 snake_case
- 异常用 `try/except` 包裹并 emit 错误信息

### 代码风格

- PEP 8 + 中文注释
- 类名 PascalCase
- 函数/变量 snake_case
- 常量 UPPER_SNAKE
- 私有方法 `_` 前缀

---

## 📦 打包发布

使用 PyInstaller：

```bash
pyinstaller build.spec
```

`build.spec` 关键配置：

```python
a = Analysis(
    ['main.py'],
    hiddenimports=['app.plugins.*', 'cryptography'],
    # ...
)
```

输出在 `dist/AlinOps/`，目录可直接分发。

---

## ❓ 常见问题

### 1. 启动报错 "ModuleNotFoundError: No module named 'PySide6'"

```bash
pip install -r requirements.txt
```

### 2. SSH 连接失败

- 确认目标主机 SSH 服务运行
- 防火墙开放 22 端口
- 检查密钥文件路径与权限（Linux: `chmod 600`）

### 3. 抓包功能不可用

部分操作系统需要管理员/root 权限。

### 4. AI 助手无响应

确认网络可达（AI 引擎需联网调用大模型 API）。

### 5. 中文显示乱码

确保终端/编辑器编码为 UTF-8：

```bash
set PYTHONIOENCODING=utf-8    # Windows
export LANG=en_US.UTF-8        # Linux/macOS
```

---

## 📜 版本与许可

- **版本**：1.0.0
- **许可**：MIT License
- **作者**：Alin 运维团队
- **仓库**：https://github.com/yilinyilin817-cloud/Alin-Operations-and-Maintenance

---

## 🤝 贡献

欢迎提交 Issue 与 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交改动 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

---

## 🗺 路线图

- [ ] 分布式 Agent 模式
- [ ] Kubernetes 集群管理
- [ ] 配置文件版本控制（Git 集成）
- [ ] 移动端远程控制 App
- [ ] 更多 AI 模型接入
- [ ] 国际化（英文/日文）

---

<p align="center">
  如果这个项目对你有帮助，请给一个 ⭐ Star！
</p>
