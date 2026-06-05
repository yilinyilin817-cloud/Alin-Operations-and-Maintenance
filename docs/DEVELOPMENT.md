# Alin 运维工具 — 开发文档

> 本文档面向参与本项目二次开发与维护的工程师，详细说明项目设计理念、模块划分、关键流程与扩展方法。

---

## 目录

1. [项目愿景](#1-项目愿景)
2. [开发环境搭建](#2-开发环境搭建)
3. [代码组织与命名规范](#3-代码组织与命名规范)
4. [核心设计模式](#4-核心设计模式)
5. [UI 框架与主题系统](#5-ui-框架与主题系统)
6. [异步任务系统（QThread + Signal）](#6-异步任务系统qthread--signal)
7. [网络检测 Worker 总览](#7-网络检测-worker-总览)
8. [运维控制台实现细节](#8-运维控制台实现细节)
9. [持久化与数据流](#9-持久化与数据流)
10. [审计与告警体系](#10-审计与告警体系)
11. [AI 引擎](#11-ai-引擎)
12. [插件机制](#12-插件机制)
13. [扩展开发指南](#13-扩展开发指南)
14. [测试与调试](#14-测试与调试)
15. [打包与发布](#15-打包与发布)
16. [常见坑与注意事项](#16-常见坑与注意事项)

---

## 1. 项目愿景

打造一个**零外部运行时依赖**、**完全离线可用**（除 AI 模块）、**覆盖网络/安全/运维全场景**的桌面端工具集。

- **目标用户**：DevOps 工程师、渗透测试人员、网络管理员、技术支持
- **核心原则**：
  1. **本地优先**：所有数据落地 JSON 文件，不依赖数据库
  2. **异步无阻塞**：所有 I/O 密集型操作通过 QThread 异步执行
  3. **审计先行**：任何可能影响生产的操作都留痕
  4. **故障隔离**：单个模块崩溃不影响主界面

---

## 2. 开发环境搭建

### 2.1 推荐工具

| 工具       | 推荐版本       |
| ---------- | -------------- |
| Python     | 3.11.x         |
| VSCode     | 最新版         |
| PyCharm    | 2024+（可选）  |
| Git        | 2.40+          |
| Qt Designer| PySide6 自带   |

### 2.2 Python 依赖

参见 `requirements.txt`：

```
PySide6>=6.5.0
paramiko>=3.0
cryptography>=41.0
bcrypt>=4.0
PyNaCl>=1.5
psutil>=5.9
invoke>=2.0
```

### 2.3 IDE 配置建议

**VSCode `settings.json`**：

```json
{
  "python.analysis.typeCheckingMode": "basic",
  "editor.formatOnSave": true,
  "[python]": {
    "editor.defaultFormatter": "ms-python.black-formatter",
    "editor.tabSize": 4
  }
}
```

### 2.4 调试模式启动

```bash
# 设置 Qt 调试环境变量
export QT_DEBUG_PLUGINS=1
export QT_LOGGING_RULES="*.debug=true"

python main.py
```

---

## 3. 代码组织与命名规范

### 3.1 目录划分

```
app/                # 核心代码（业务实现）
  ├── 工具模块        # 与 UI 直接绑定的 Qt 控件
  ├── 业务模块        # 通用业务逻辑
  ├── 异步 Worker     # 后台任务（QThread 子类）
  ├── 插件           # 可热加载的扩展点
  └── resources/      # 静态资源

main.py             # 入口
build.spec          # PyInstaller 打包
docs/               # 文档
```

### 3.2 命名约定

| 类型          | 规范                      | 示例                            |
| ------------- | ------------------------- | ------------------------------- |
| 类名          | PascalCase                | `AssetManagerWidget`            |
| 公开方法      | snake_case                | `connect_host`                  |
| 私有方法      | _snake_case               | `_refresh_table`                |
| 槽函数        | _on_xxx_yyy               | `_on_table_dbl`                 |
| 工具方法      | _tool_xxx                 | `_tool_ping`                    |
| 回调方法      | _on_xxx_result            | `_on_ping_result`               |
| Qt Signal     | snake_case                | `result_ready`                  |
| 私有变量      | _snake_case               | `_asset_manager`                |
| 常量          | UPPER_SNAKE               | `MAX_HISTORY`                   |
| 布尔判断方法  | is_ / has_ / should_      | `is_connected`                  |

### 3.3 注释规范

- **模块顶部**：说明模块职责
- **类**：说明业务含义与典型用法
- **复杂函数**：使用多行注释解释算法或业务原因
- **TODO/FIXME**：标注待办或已知问题

```python
def _calculate_jitter(samples: list) -> float:
    """
    计算网络抖动（RFC 3550 简化实现）
    抖动 = 相邻延迟差值的平均绝对值
    """
    if len(samples) < 2:
        return 0
    diffs = [abs(samples[i] - samples[i-1]) for i in range(1, len(samples))]
    return sum(diffs) / len(diffs)
```

---

## 4. 核心设计模式

### 4.1 Worker-Object 模式

所有后台任务都遵循：

```python
class XxxWorker(QThread):
    # 定义 Signal（UI 端通过 connect 接收）
    result_ready = Signal(dict)
    progress = Signal(int, int)  # current, total
    error_occurred = Signal(str)

    def __init__(self, **kwargs):
        super().__init__()
        # 保存参数

    def run(self):
        try:
            # 业务逻辑
            for item in items:
                if self._is_cancelled:
                    return
                result = do_work(item)
                self.result_ready.emit(result)
        except Exception as e:
            self.error_occurred.emit(str(e))
```

### 4.2 工厂方法 + 容器 Widget

`enterprise_ops.py` 中的 `EnterpriseOpsWidget` 是典型容器：

```python
class EnterpriseOpsWidget(QWidget):
    def __init__(self, asset_manager, parent=None):
        super().__init__(parent)
        self._tabs = QTabWidget()
        # 延迟导入
        try:
            from app.audit_log import AuditLogWidget
            self._audit = AuditLogWidget()
            self._tabs.addTab(self._audit, "📝 审计日志")
        except Exception as e:
            print(f"[WARN] 审计日志模块加载失败: {e}")
```

**优势**：模块加载失败时不影响整体功能。

### 4.3 Observer 模式（Signal/Slot）

所有跨层通信都通过 Qt Signal：

```python
# 定义
class AuditLogger:
    entry_added = Signal(dict)

# 订阅
audit_logger.entry_added.connect(self._refresh_table)

# 触发
audit_logger.entry_added.emit(entry)
```

### 4.4 单例模式

`AuditLogger`、`AlertCenter` 等需要全局共享的组件使用模块级单例：

```python
_instance = None
def get_logger():
    global _instance
    if _instance is None:
        _instance = AuditLogger()
    return _instance
```

---

## 5. UI 框架与主题系统

### 5.1 主窗口结构

```
┌─────────────────────────────────────────────────────┐
│  TitleBar（自定义标题栏，渐变 + 控件）                │
├──────────┬──────────────────────────────────────────┤
│          │                                          │
│          │  MainTabs（QTabWidget）                  │
│ SideNav  │  ┌────────────────────────────────────┐  │
│（分类）  │  │  Tab 1                              │  │
│          │  │  Tab 2                              │  │
│          │  │  Tab 3                              │  │
│          │  └────────────────────────────────────┘  │
│          │                                          │
├──────────┴──────────────────────────────────────────┤
│  StatusBar                                          │
└─────────────────────────────────────────────────────┘
```

### 5.2 主题常量

`app/theme.py` 集中管理所有颜色、字体、尺寸：

```python
COLORS = {
    "primary": "#4ecdc4",
    "danger": "#ff6b6b",
    "warning": "#ffaa00",
    "success": "#4ecdc4",
    "bg_dark": "#1e1e1e",
    "bg_panel": "#252526",
    "border": "#3c3c3c",
    "text_primary": "#ffffff",
    "text_secondary": "#cccccc",
    "text_muted": "#888888",
}
```

### 5.3 样式表（QSS）

`app/resources/style.qss` 定义全局样式。所有自定义控件都通过 `setStyleSheet` 局部覆盖。

### 5.4 添加新页面

1. 创建继承 `QWidget` 的类
2. 在 `MainWindow.__init__` 中实例化并 `addTab`
3. 必要时在 `_show_tool_category` 注册入口

---

## 6. 异步任务系统（QThread + Signal）

### 6.1 标准 Worker 模板

```python
from PySide6.QtCore import QThread, Signal

class PingWorker(QThread):
    """Ping 探测 Worker"""
    result_ready = Signal(str, float, str)  # host, latency_ms, status
    progress = Signal(int, int)              # current, total
    finished_all = Signal()

    def __init__(self, host: str, count: int = 4, timeout: float = 2.0):
        super().__init__()
        self.host = host
        self.count = count
        self.timeout = timeout
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        import subprocess
        for i in range(self.count):
            if self._is_cancelled:
                return
            # 调用系统 ping
            r = subprocess.run(
                ["ping", "-n", "1", "-w", str(int(self.timeout * 1000)), self.host],
                capture_output=True, text=True, timeout=self.timeout + 3
            )
            # 解析结果
            self.result_ready.emit(self.host, latency, "ok" if r.returncode == 0 else "fail")
            self.progress.emit(i + 1, self.count)
        self.finished_all.emit()
```

### 6.2 Worker 在 UI 端的使用

```python
# 1. 实例化（保持引用避免被 GC）
self._ping_worker = PingWorker("www.baidu.com")

# 2. 连接信号
self._ping_worker.result_ready.connect(self._on_ping_result)
self._ping_worker.finished_all.connect(self._on_ping_finished)

# 3. 启动
self._ping_worker.start()

# 4. 关闭时清理
def closeEvent(self, event):
    if self._ping_worker and self._ping_worker.isRunning():
        self._ping_worker.cancel()
        self._ping_worker.wait(3000)  # 最多等 3 秒
```

### 6.3 批量 Worker 模式

对于"对多个目标执行相同操作"的场景，使用 `ThreadPoolExecutor` + 主线程聚合：

```python
class BatchWorker(QThread):
    result_ready = Signal(str, bool, str)   # target, ok, message
    all_done = Signal(int, int)             # success, total

    def run(self):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=5) as ex:
            fut_map = {ex.submit(self._work, t): t for t in self.targets}
            for fut in as_completed(fut_map):
                t = fut_map[fut]
                try:
                    ok, msg = fut.result()
                except Exception as e:
                    ok, msg = False, str(e)
                self.result_ready.emit(t, ok, msg)
        self.all_done.emit(self.success, len(self.targets))
```

---

## 7. 网络检测 Worker 总览

参见 `README.md` 中的清单。每个 Worker 都有以下约定：

- **构造**：仅接收业务参数，**不**接收 UI 控件
- **Signal**：通过 `Signal` 返回结果，**不**直接调用 UI 方法
- **取消**：支持 `cancel()` / `_is_cancelled` 检查
- **超时**：内部使用 `timeout` 参数，**不**依赖外部信号
- **异常**：捕获后 emit 错误信息，**不**抛出到 UI 线程

### 7.1 新增 Worker 检查清单

- [ ] 继承 `QThread`
- [ ] 至少一个 `Signal` 用于回传结果
- [ ] 支持 `cancel()`
- [ ] 内部异常被捕获
- [ ] 设置合理超时
- [ ] 单元测试（mock socket）
- [ ] 文档字符串

---

## 8. 运维控制台实现细节

### 8.1 资产数据模型

```json
{
  "groups": [
    {
      "name": "Web 服务器",
      "hosts": [
        {
          "name": "web-prod-01",
          "host": "192.168.1.10",
          "port": 22,
          "username": "root",
          "auth_type": "key",          // password | key
          "password": "",
          "key_path": "/path/to/key",
          "key_passphrase": "",
          "group": "Web 服务器",
          "tags": ["web", "prod", "nginx"],
          "note": "主站",
          "created_at": 1234567890
        }
      ]
    }
  ]
}
```

存储路径：`assets/hosts.json`（运行期生成，已在 `.gitignore`）。

### 8.2 标签云算法

```python
def _refresh_tag_cloud(self):
    tag_count = {}
    for host in self.all_hosts():
        for t in host.get("tags", []):
            tag_count[t] = tag_count.get(t, 0) + 1

    for btn in self._tag_buttons.values():
        btn.deleteLater()
    self._tag_buttons.clear()

    for tag, cnt in sorted(tag_count.items(), key=lambda x: -x[1]):
        btn = QPushButton(f"{tag} ({cnt})")
        btn.setCheckable(True)
        # 按使用次数调整颜色
        opacity = min(1.0, 0.55 + cnt * 0.1)
        btn.setStyleSheet(f"background: rgba(78,205,196,{opacity}); ...")
        btn.clicked.connect(lambda checked=False, t=tag: self._toggle_tag(t))
        self._tag_cloud_layout.addWidget(btn)
        self._tag_buttons[tag] = btn
```

### 8.3 杀进程流程

```python
def _do_kill(self, host, pid, sig):
    # 1. Windows / Linux 区分命令
    if self._is_windows_host(host):
        cmd = f"taskkill /F /PID {pid}" if sig == 9 else f"taskkill /PID {pid}"
    else:
        cmd = f"kill -s {sig} {pid}"

    # 2. 通过 SSH 执行
    self._kill_worker = SSHCommandWorker(
        host=host["host"], port=host.get("port", 22),
        username=host.get("username", "root"),
        command=cmd, ...
    )
    self._kill_worker.result_ready.connect(self._on_kill_result)
    self._kill_worker.start()

    # 3. 写审计
    audit("process.kill", target=host["name"],
          details={"pid": pid, "signal": sig})

    # 4. 完成后自动刷新
    QTimer.singleShot(800, self._refresh)
```

### 8.4 批量执行并发控制

```python
class BatchSSHCommandWorker(QThread):
    def run(self):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=self.concurrency) as ex:
            futures = {ex.submit(self._ssh_exec, h): h for h in self.hosts}
            for fut in as_completed(futures):
                host = futures[fut]
                try:
                    output, error = fut.result()
                    self.result_ready.emit(host, output, error)
                except Exception as e:
                    self.result_ready.emit(host, "", str(e))
        self.finished_all.emit(success_count, total_count)
```

### 8.5 定时任务（cron 解析）

使用简化的 5 段标准 cron 表达式：

```
┌──────────── 分钟 (0 - 59)
│ ┌────────── 小时 (0 - 23)
│ │ ┌──────── 日 (1 - 31)
│ │ │ ┌────── 月 (1 - 12)
│ │ │ │ ┌──── 星期 (0 - 6, 0=周日)
│ │ │ │ │
* * * * *
```

支持特殊字符：`*` `,` `-` `/`。

```python
class CronExpression:
    def matches(self, dt: datetime) -> bool:
        return (
            dt.minute in self.minute and
            dt.hour in self.hour and
            dt.day in self.day and
            dt.month in self.month and
            dt.weekday() in self.weekday
        )

    def next_after(self, dt: datetime) -> datetime:
        # 步进到下一次匹配时间
        ...
```

---

## 9. 持久化与数据流

### 9.1 存储约定

| 数据             | 路径                          | 格式  |
| ---------------- | ----------------------------- | ----- |
| 主机资产         | `assets/hosts.json`           | JSON  |
| 审计日志         | `assets/audit.log.json`       | JSON  |
| 告警规则         | `assets/alerts.json`          | JSON  |
| 服务监控配置     | `assets/service_monitor.json` | JSON  |
| 批量命令模板     | `assets/batch_templates.json` | JSON  |
| 批量执行历史     | `assets/batch_history.json`   | JSON  |
| 定时任务         | `assets/scheduled_tasks.json` | JSON  |
| 用户设置         | `assets/settings.json`        | JSON  |

> ⚠️ 上述文件全部已加入 `.gitignore`，**不要**提交到仓库。

### 9.2 数据流示例：杀进程

```
[用户在 ProcessManagerWidget 双击行]
   ↓
[_kill_selected()]
   ↓ QMessageBox 确认
[_do_kill(host, pid, sig)]
   ├→ 创建 SSHCommandWorker
   │     └→ 异步执行 taskkill / kill
   ├→ audit("process.kill", details={...})
   │     └→ 写入 assets/audit.log.json
   └→ [SSHCommandWorker 完成]
        └→ result_ready 信号
            └→ _on_kill_result()
                 ├→ 状态栏更新
                 └→ QTimer.singleShot(800, self._refresh)
```

---

## 10. 审计与告警体系

### 10.1 审计 Logger

```python
# 全局单例
_logger = AuditLogger.get_instance()

# 调用
from app.audit_log import audit
audit(
    action="process.kill",
    target="web-prod-01",
    result="success",
    details={"pid": 1234, "signal": 9}
)

# 订阅
_logger.entry_added.connect(my_widget._refresh)
```

### 10.2 告警规则

```python
{
    "name": "CPU 高负载",
    "metric": "cpu",       # cpu / mem / disk / service / log_keyword
    "op": ">",             # > / < / == / != / contains
    "threshold": 90,
    "duration": 60,        # 持续 60 秒
    "severity": "critical",
    "channels": ["system", "sound", "webhook_xxx"],
    "hosts": ["web-prod-01", "web-prod-02"],
    "enabled": True
}
```

### 10.3 告警生命周期

```
指标采样 → 命中规则 → 持续时间未到 → 抑制
                          ↓
                    持续时间到 → 触发告警 → 通知渠道
                          ↓
                    指标恢复 → 抑制窗口 → 发送恢复通知
```

### 10.4 Webhook 推送

```python
# 默认告警 Payload
{
    "event": "down",          # down | recovered
    "target": "web-prod-01",
    "type": "cpu",
    "value": 95.3,
    "threshold": 90,
    "duration": 60,
    "timestamp": "2024-01-01 12:00:00",
    "consecutive_breaches": 5
}
```

支持钉钉、飞书、企业微信、Slack、自定义 Webhook。

---

## 11. AI 引擎

### 11.1 架构

```
用户输入自然语言
   ↓
[AiEngine.query()]
   ↓ 构造 Prompt
[LLM API]
   ↓ 返回命令
[风险评估]
   ↓
[UI 展示 + 一键执行]
```

### 11.2 Prompt 模板

```
你是一个 Linux 系统管理员。用户会用自然语言描述需求，
请输出可执行的 shell 命令（多条用 \n 分隔），
并对每条命令给出 1-5 的风险评分（5=最危险）。

用户当前主机：{hostname}
用户当前路径：{pwd}

需求：{user_input}
```

### 11.3 风险关键词词典

```python
RISKY_PATTERNS = [
    (r"rm\s+-rf", 5),
    (r"dd\s+if=", 4),
    (r"mkfs", 5),
    (r"fdisk", 4),
    (r"chmod\s+777", 3),
    (r"curl.*\|\s*sh", 5),
    (r"wget.*\|\s*bash", 5),
    (r"iptables\s+-F", 4),
    (r"kill\s+-9\s+1", 5),
    (r"systemctl\s+(stop|disable)\s+\S+", 2),
]
```

---

## 12. 插件机制

### 12.1 插件目录

`app/plugins/` 下每个 `.py` 文件即一个插件。

### 12.2 插件协议

```python
# app/plugins/my_plugin.py
PLUGIN_INFO = {
    "name": "My Plugin",
    "version": "1.0.0",
    "author": "Your Name",
    "description": "插件说明",
    "category": "network",   # network / security / utility
}

def run(host: str, **kwargs) -> dict:
    """插件入口"""
    return {"result": "ok", "data": ...}
```

### 12.3 加载流程

```python
import importlib
import os

def load_plugins():
    plugins = {}
    plugins_dir = "app/plugins"
    for fname in os.listdir(plugins_dir):
        if fname.startswith("_") or not fname.endswith(".py"):
            continue
        mod_name = f"app.plugins.{fname[:-3]}"
        try:
            mod = importlib.import_module(mod_name)
            if hasattr(mod, "PLUGIN_INFO") and hasattr(mod, "run"):
                plugins[mod.PLUGIN_INFO["name"]] = mod
        except Exception as e:
            print(f"加载插件 {fname} 失败: {e}")
    return plugins
```

---

## 13. 扩展开发指南

### 13.1 添加新的检测工具

**步骤**：

1. **创建 Worker**：在 `app/network_probe.py` 添加 `QThread` 子类
2. **导入**：在 `app/main_window.py` 导入
3. **添加工具方法**：
   ```python
   def _tool_my_check(self):
       host, ok = QInputDialog.getText(self, "My Check", "目标:")
       if ok and host:
           w = QTextEdit_style()
           self._main_tabs.addTab(w, f"My: {host}")
           self._my_worker = MyWorker(host)
           self._my_worker.result_ready.connect(
               lambda r: self._on_my_result(w, r))
           self._my_worker.start()

   def _on_my_result(self, w, result):
       w.append(f'<span style="color:#4ecdc4;">{result}</span>')
   ```
4. **注册到面板**：在 `_show_tool_category` 中添加入口

### 13.2 添加新的运维控制台标签

1. 在 `app/enterprise_ops.py` 创建 Widget
2. 在 `EnterpriseOpsWidget.__init__` 中延迟加载

### 13.3 添加新的告警渠道

1. 在 `app/alert_center.py` 的 `NotificationDispatcher` 中添加新方法
2. 注册渠道 ID 与发送函数

### 13.4 添加新的审计动作类型

- 不需要改代码，只在调用时使用有意义的 `action` 字符串
- 建议使用 `module.action` 形式，如 `process.kill`、`file.upload`

---

## 14. 测试与调试

### 14.1 单元测试

测试 Worker 时 mock socket：

```python
import unittest
from unittest.mock import patch, MagicMock

class TestPingWorker(unittest.TestCase):
    @patch("subprocess.run")
    def test_ping_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="...time=10ms...")
        worker = PingWorker("1.1.1.1", count=1)
        results = []
        worker.result_ready.connect(lambda h, l, s: results.append((h, l, s)))
        worker.run()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][2], "ok")
```

### 14.2 调试日志

```python
# 启用详细日志
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
```

### 14.3 Qt Designer

使用 `pyside6-designer` 打开 `.ui` 文件进行可视化设计：

```bash
pyside6-designer app/resources/main_window.ui
```

### 14.4 性能分析

```python
import cProfile
cProfile.run("main()", "profile.out")
import pstats
pstats.Stats("profile.out").sort_stats("cumulative").print_stats(20)
```

---

## 15. 打包与发布

### 15.1 PyInstaller

`build.spec` 关键项：

```python
a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('app/resources', 'app/resources'),
    ],
    hiddenimports=[
        'app.plugins.port_scan_enhanced',
        'app.plugins.security_audit',
        'app.plugins.traffic_analyzer',
        'app.plugins.vuln_scanner',
        'cryptography',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy'],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='AlinOps',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,    # GUI 应用
    icon='app/resources/icon.ico',
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=True, upx_exclude=[], name='AlinOps',
)
```

### 15.2 构建命令

```bash
# 单文件模式
pyinstaller --onefile --windowed --name AlinOps --icon=app/resources/icon.ico main.py

# 目录模式（推荐）
pyinstaller build.spec
```

### 15.3 跨平台

- **Windows**：在 Windows 上构建 `.exe`
- **macOS**：在 macOS 上构建 `.app`
- **Linux**：在 Linux 上构建 AppImage

---

## 16. 常见坑与注意事项

### 16.1 QThread 内存泄漏

**症状**：Worker 完成后 UI 不刷新
**原因**：Worker 实例被 GC
**解决**：在父 Widget 中持有引用（`self._worker = ...`）

### 16.2 Signal 在子线程 emit

✅ **正确**：所有 `Signal.emit()` 都可在子线程调用，Qt 自动跨线程

❌ **错误**：直接操作 UI 控件（`widget.setText()`）从子线程

### 16.3 中文编码

确保所有文件保存为 **UTF-8**（无 BOM）。建议 IDE 设置：

```json
"files.encoding": "utf8"
```

### 16.4 subprocess 超时

```python
# ✅ 推荐
r = subprocess.run(cmd, timeout=10)

# ⚠️ 旧 API
r = subprocess.call(cmd, timeout=10)  # 无 stdout
```

### 16.5 路径处理

```python
# ✅ 使用 os.path 或 pathlib
from pathlib import Path
data_file = Path("assets") / "hosts.json"

# ❌ 硬编码反斜杠
data_file = "assets\\hosts.json"  # 仅 Windows
```

### 16.6 高 DPI

`main.py` 中需启用：

```python
QApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
)
```

### 16.7 SSH 私钥权限（Linux）

Linux/macOS 严格要求私钥权限 600：

```python
import os, stat
key_path = "/home/user/.ssh/id_rsa"
os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)  # 600
```

### 16.8 防火墙与 ICMP

- Windows 防火墙默认**阻止** ICMP 入站
- Linux 使用 `iptables -A INPUT -p icmp -j ACCEPT` 放行
- ICMP 被阻时使用 **TCP Ping** 替代

### 16.9 大量并发

`ThreadPoolExecutor` 线程数不要超过 `cpu_count() * 4`：

```python
import os
max_workers = min(20, (os.cpu_count() or 1) * 4)
```

### 16.10 内存占用

定时任务、批量执行历史、审计日志都应**定期清理**，避免内存泄漏：

```python
# 审计日志
if len(self._entries) > 10000:
    self._entries = self._entries[-10000:]
```

---

## 附录 A：常用命令速查

```bash
# 启动
python main.py

# 语法检查
python -m py_compile app/*.py

# 单元测试
python -m pytest tests/

# 打包
pyinstaller build.spec

# 清理
find . -name __pycache__ -exec rm -rf {} +
```

## 附录 B：术语表

| 术语       | 含义                                    |
| ---------- | --------------------------------------- |
| Worker     | 后台线程任务（QThread 子类）            |
| Signal     | Qt 信号，跨线程安全                     |
| 资产       | 被管理的主机（含 SSH 信息）             |
| 告警       | 命中规则后触发的通知                    |
| 审计       | 对操作的可追溯记录                      |
| 模板       | 预保存的命令，可重复使用                |
| Webhook    | HTTP 回调，用于跨系统通知               |
| OUI        | MAC 地址前 3 字节，标识厂商             |

## 附录 C：参考资源

- [PySide6 官方文档](https://doc.qt.io/qtforpython-6/)
- [paramiko 文档](http://docs.paramiko.org/)
- [RFC 3550 - RTP（抖动算法）](https://datatracker.ietf.org/doc/html/rfc3550)
- [RFC 7231 - HTTP 方法](https://datatracker.ietf.org/doc/html/rfc7231)
- [cron 表达式规范](https://en.wikipedia.org/wiki/Cron)

---

<p align="center">
  <em>本文档随项目演进持续更新。如有疑问请提交 Issue。</em>
</p>
