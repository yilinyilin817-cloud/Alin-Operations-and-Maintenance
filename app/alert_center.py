"""
告警中心模块
- 告警规则：CPU/内存/磁盘/服务状态/关键字日志等触发条件
- 通知渠道：系统通知、声音、Webhook（飞书/钉钉/Slack/企业微信）
- 告警历史：触发时间、恢复时间、持续时长
- 静默期：避免重复告警轰炸

持久化：~/.aiinlink/alerts.json
"""

import json
import os
import time
import threading
import urllib.request
import urllib.parse
import urllib.error
from typing import List, Optional, Dict, Callable
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
    QPlainTextEdit, QCheckBox, QSplitter, QMessageBox, QTabWidget,
    QListWidget, QListWidgetItem, QFrame, QSizePolicy,
)

from app.theme import (
    BG_DEEP, BG_PANEL, BG_PANEL_HOVER, BG_INPUT,
    FG_PRIMARY, FG_SECONDARY, FG_TERTIARY, FG_DISABLED,
    PRIMARY, SUCCESS, WARN, DANGER, INFO,
    BORDER, BORDER_LIGHT,
    FONT_FAMILY, FONT_SIZE_BASE, FONT_SIZE_SM, FONT_SIZE_MD,
    RADIUS_SM, RADIUS_MD, RADIUS_LG,
)


ALERT_DIR = os.path.join(os.path.expanduser("~"), ".aiinlink")
ALERT_RULES_FILE = os.path.join(ALERT_DIR, "alert_rules.json")
ALERT_HISTORY_FILE = os.path.join(ALERT_DIR, "alert_history.json")
MAX_HISTORY_ENTRIES = 5000


# ============================================================
# 告警事件
# ============================================================

class AlertEvent:
    """单次告警事件"""

    def __init__(self, rule_id: str, rule_name: str, host: str,
                 metric: str, value: float, threshold: float, severity: str = "warn",
                 message: str = ""):
        self.id = f"{int(time.time()*1000)}_{rule_id}_{host}"
        self.rule_id = rule_id
        self.rule_name = rule_name
        self.host = host
        self.metric = metric
        self.value = value
        self.threshold = threshold
        self.severity = severity  # info / warn / critical
        self.message = message
        self.fired_at = time.time()
        self.fired_at_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        self.recovered_at: Optional[float] = None
        self.recovered_at_str: Optional[str] = None
        self.notified = False
        self.acknowledged = False
        self.acknowledged_by: Optional[str] = None
        self.ack_time_str: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "rule_id": self.rule_id, "rule_name": self.rule_name,
            "host": self.host, "metric": self.metric, "value": self.value,
            "threshold": self.threshold, "severity": self.severity,
            "message": self.message, "fired_at": self.fired_at,
            "fired_at_str": self.fired_at_str, "recovered_at": self.recovered_at,
            "recovered_at_str": self.recovered_at_str, "notified": self.notified,
            "acknowledged": self.acknowledged, "acknowledged_by": self.acknowledged_by,
            "ack_time_str": self.ack_time_str,
        }

    @staticmethod
    def from_dict(d: dict) -> "AlertEvent":
        e = AlertEvent(
            d.get("rule_id", ""), d.get("rule_name", ""), d.get("host", ""),
            d.get("metric", ""), d.get("value", 0), d.get("threshold", 0),
            d.get("severity", "warn"), d.get("message", ""),
        )
        e.id = d.get("id", e.id)
        e.fired_at = d.get("fired_at", e.fired_at)
        e.fired_at_str = d.get("fired_at_str", e.fired_at_str)
        e.recovered_at = d.get("recovered_at")
        e.recovered_at_str = d.get("recovered_at_str")
        e.notified = d.get("notified", False)
        e.acknowledged = d.get("acknowledged", False)
        e.acknowledged_by = d.get("acknowledged_by")
        e.ack_time_str = d.get("ack_time_str")
        return e

    def duration_str(self) -> str:
        end = self.recovered_at or time.time()
        d = int(end - self.fired_at)
        if d < 60:
            return f"{d}秒"
        if d < 3600:
            return f"{d//60}分{d%60}秒"
        if d < 86400:
            return f"{d//3600}小时{(d%3600)//60}分"
        return f"{d//86400}天{(d%86400)//3600}小时"


# ============================================================
# 告警规则
# ============================================================

class AlertRule:
    """告警规则"""

    def __init__(self, name: str, metric: str, op: str, threshold: float,
                 duration: int = 0, severity: str = "warn",
                 channels: Optional[List[str]] = None, enabled: bool = True,
                 hosts: Optional[List[str]] = None, description: str = ""):
        self.id = f"rule_{int(time.time()*1000)}"
        self.name = name
        self.metric = metric  # cpu / mem / disk / service / log_keyword / net_in / net_out
        self.op = op          # > / < / == / != / contains
        self.threshold = threshold
        self.duration = duration  # 持续多少秒才告警（0=立即）
        self.severity = severity
        self.channels = channels or []  # 通知渠道：system / sound / webhook_*
        self.enabled = enabled
        self.hosts = hosts or []  # 空=全部
        self.description = description
        self.created_at = time.time()
        # 跟踪状态
        self._state: Dict[str, dict] = {}  # host -> {triggered_at, last_value, fired_event_id}

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "metric": self.metric,
            "op": self.op, "threshold": self.threshold, "duration": self.duration,
            "severity": self.severity, "channels": self.channels, "enabled": self.enabled,
            "hosts": self.hosts, "description": self.description,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(d: dict) -> "AlertRule":
        r = AlertRule(
            d.get("name", ""), d.get("metric", "cpu"), d.get("op", ">"),
            d.get("threshold", 0), d.get("duration", 0), d.get("severity", "warn"),
            d.get("channels", []), d.get("enabled", True),
            d.get("hosts", []), d.get("description", ""),
        )
        r.id = d.get("id", r.id)
        r.created_at = d.get("created_at", r.created_at)
        return r


# ============================================================
# 通知渠道
# ============================================================

class NotificationChannel:
    """通知渠道 - 抽象基类"""

    def send(self, event: AlertEvent, config: dict) -> bool:
        raise NotImplementedError


class WebhookChannel:
    """Webhook 通知渠道 - 支持飞书/钉钉/Slack/企业微信/自定义"""

    @staticmethod
    def send(event: AlertEvent, config: dict) -> bool:
        url = config.get("url", "").strip()
        if not url:
            return False
        title = f"[{event.severity.upper()}] {event.rule_name}"
        text = (
            f"**告警**: {event.rule_name}\n"
            f"**主机**: {event.host}\n"
            f"**指标**: {event.metric} = {event.value}\n"
            f"**阈值**: {event.op} {event.threshold}\n"
            f"**时间**: {event.fired_at_str}\n"
            f"**消息**: {event.message}"
        )
        # 根据 platform 选择格式
        platform = config.get("platform", "custom")
        try:
            if platform == "feishu":
                payload = {
                    "msg_type": "interactive",
                    "card": {
                        "header": {"title": {"tag": "plain_text", "content": title}},
                        "elements": [{"tag": "markdown", "content": text}],
                    }
                }
            elif platform == "dingtalk":
                payload = {
                    "msgtype": "markdown",
                    "markdown": {"title": title, "text": text.replace("**", "**")},
                }
            elif platform == "wecom":
                payload = {
                    "msgtype": "markdown",
                    "markdown": {"content": f"## {title}\n{text}"},
                }
            elif platform == "slack":
                payload = {"text": f"*{title}*\n{text}"}
            else:  # custom
                payload = {
                    "title": title, "text": text, "host": event.host,
                    "metric": event.metric, "value": event.value,
                    "threshold": event.threshold, "severity": event.severity,
                    "fired_at": event.fired_at_str,
                }

            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return 200 <= resp.status < 300
        except Exception as e:
            print(f"Webhook 通知失败: {e}")
            return False


class SoundChannel:
    """系统声音通知"""

    @staticmethod
    def send(event: AlertEvent, config: dict) -> bool:
        try:
            if event.severity == "critical":
                # 连续响 3 次
                for _ in range(3):
                    try:
                        if os.name == "nt":
                            import winsound
                            winsound.MessageBeep(winsound.MB_ICONHAND)
                        else:
                            print("\a", end="", flush=True)
                    except Exception:
                        pass
            else:
                if os.name == "nt":
                    import winsound
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                else:
                    print("\a", end="", flush=True)
            return True
        except Exception:
            return False


class SystemTrayChannel:
    """系统托盘气泡通知"""

    @staticmethod
    def send(event: AlertEvent, config: dict) -> bool:
        try:
            from PySide6.QtWidgets import QSystemTrayIcon
            from PySide6.QtGui import QIcon
            app = config.get("app")
            if not app or not hasattr(app, "tray"):
                return False
            tray: QSystemTrayIcon = app.tray
            if tray and tray.isSystemTrayAvailable():
                icon = QMessageBox.Critical if event.severity == "critical" else QMessageBox.Warning
                tray.showMessage(
                    event.rule_name, event.message,
                    icon, 5000,
                )
                return True
        except Exception:
            pass
        return False


# ============================================================
# 告警中心（核心引擎）
# ============================================================

class AlertCenter(QObject if False else object):
    """告警中心核心 - 接收指标样本、匹配规则、触发告警"""

    _instance: Optional["AlertCenter"] = None
    rule_added = None
    rule_removed = None
    event_fired = None
    event_recovered = None

    def __init__(self):
        self._rules: List[AlertRule] = []
        self._history: List[AlertEvent] = []
        self._active_events: Dict[str, AlertEvent] = {}  # key: rule_id|host
        self._silenced_until: Dict[str, float] = {}  # rule_id|host -> timestamp
        self._webhook_configs: Dict[str, dict] = {}  # name -> config
        self._app = None
        self._lock = threading.Lock()
        self._ensure_dir()
        self._load()

    @classmethod
    def instance(cls) -> "AlertCenter":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_app(self, app):
        self._app = app

    def _ensure_dir(self):
        try:
            os.makedirs(ALERT_DIR, exist_ok=True)
        except Exception:
            pass

    def _load(self):
        if os.path.exists(ALERT_RULES_FILE):
            try:
                with open(ALERT_RULES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._rules = [AlertRule.from_dict(d) for d in data.get("rules", [])]
                    self._webhook_configs = data.get("webhooks", {})
            except Exception:
                pass
        if os.path.exists(ALERT_HISTORY_FILE):
            try:
                with open(ALERT_HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._history = [AlertEvent.from_dict(d) for d in data.get("events", [])]
                    # 重新构建 active_events
                    for e in self._history:
                        if e.recovered_at is None and not e.acknowledged:
                            key = f"{e.rule_id}|{e.host}"
                            self._active_events[key] = e
            except Exception:
                pass

    def _save(self):
        try:
            with open(ALERT_RULES_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "rules": [r.to_dict() for r in self._rules],
                    "webhooks": self._webhook_configs,
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存告警规则失败: {e}")
        try:
            with open(ALERT_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "events": [e.to_dict() for e in self._history[-MAX_HISTORY_ENTRIES:]]
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存告警历史失败: {e}")

    # ---- 规则管理 ----
    def add_rule(self, rule: AlertRule):
        with self._lock:
            self._rules.append(rule)
            self._save()

    def update_rule(self, rule: AlertRule):
        with self._lock:
            for i, r in enumerate(self._rules):
                if r.id == rule.id:
                    self._rules[i] = rule
                    self._save()
                    return True
        return False

    def delete_rule(self, rule_id: str):
        with self._lock:
            self._rules = [r for r in self._rules if r.id != rule_id]
            self._save()

    def get_rules(self) -> List[AlertRule]:
        return list(self._rules)

    def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        for r in self._rules:
            if r.id == rule_id:
                return r
        return None

    def set_webhook_config(self, name: str, config: dict):
        self._webhook_configs[name] = config
        self._save()

    def get_webhook_configs(self) -> dict:
        return dict(self._webhook_configs)

    # ---- 样本评估 ----
    def evaluate_metrics(self, host: str, metrics: dict):
        """对一台主机的指标样本评估所有适用的规则"""
        for rule in self._rules:
            if not rule.enabled:
                continue
            if rule.hosts and host not in rule.hosts:
                continue
            self._evaluate_rule(rule, host, metrics)

    def evaluate_service(self, host: str, service_name: str, ok: bool,
                          latency_ms: float = 0):
        for rule in self._rules:
            if not rule.enabled:
                continue
            if rule.metric != "service":
                continue
            if rule.hosts and host not in rule.hosts:
                continue
            if rule.metric == "service" and service_name in rule.name:
                # 简单匹配
                if not ok and rule.op == "==":
                    self._trigger(rule, host, service_name, 0, rule.threshold,
                                  f"服务 {service_name} 不可用")
                elif ok and rule.op == "!=":
                    self._trigger(rule, host, service_name, 0, rule.threshold,
                                  f"服务 {service_name} 异常（延迟 {latency_ms}ms）")

    def _evaluate_rule(self, rule: AlertRule, host: str, metrics: dict):
        """评估单条规则"""
        # 提取指标值
        val = None
        metric_name = rule.metric
        if rule.metric == "cpu":
            val = metrics.get("cpu_percent")
        elif rule.metric == "mem":
            val = metrics.get("mem_percent")
        elif rule.metric == "disk":
            val = metrics.get("disk_percent")
        elif rule.metric == "load":
            val = metrics.get("load1")
        elif rule.metric == "net_in":
            val = metrics.get("net_in_kbps")
        elif rule.metric == "net_out":
            val = metrics.get("net_out_kbps")
        if val is None:
            return

        # 评估条件
        triggered = False
        try:
            if rule.op == ">":
                triggered = val > rule.threshold
            elif rule.op == ">=":
                triggered = val >= rule.threshold
            elif rule.op == "<":
                triggered = val < rule.threshold
            elif rule.op == "<=":
                triggered = val <= rule.threshold
            elif rule.op == "==":
                triggered = abs(val - rule.threshold) < 0.01
            elif rule.op == "!=":
                triggered = abs(val - rule.threshold) >= 0.01
        except Exception:
            return

        key = f"{rule.id}|{host}"
        state = rule._state.setdefault(host, {
            "triggered_at": None, "fired_event_id": None, "value": None,
        })

        if triggered:
            # 静默期检查
            silenced_until = self._silenced_until.get(key, 0)
            if time.time() < silenced_until:
                return
            if state["triggered_at"] is None:
                state["triggered_at"] = time.time()
                state["value"] = val
            # 持续时长检查
            if rule.duration <= 0 or (time.time() - state["triggered_at"]) >= rule.duration:
                if key not in self._active_events:
                    self._fire(rule, host, metric_name, val, state["triggered_at"])
        else:
            # 恢复
            if key in self._active_events:
                self._recover(key)
            state["triggered_at"] = None
            state["fired_event_id"] = None
            state["value"] = None

    def _fire(self, rule: AlertRule, host: str, metric: str, value: float, triggered_at: float):
        """触发告警"""
        ev = AlertEvent(
            rule_id=rule.id, rule_name=rule.name, host=host,
            metric=metric, value=value, threshold=rule.threshold,
            severity=rule.severity,
            message=f"主机 {host} 的 {metric} = {value} {rule.op} {rule.threshold}",
        )
        ev.fired_at = triggered_at
        ev.fired_at_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(triggered_at))
        key = f"{rule.id}|{host}"
        with self._lock:
            self._active_events[key] = ev
            self._history.append(ev)
            if len(self._history) > MAX_HISTORY_ENTRIES:
                self._history = self._history[-MAX_HISTORY_ENTRIES:]
            self._save()
        # 通知
        self._notify(ev, rule)
        return ev

    def _recover(self, key: str):
        ev = self._active_events.pop(key, None)
        if not ev:
            return
        ev.recovered_at = time.time()
        ev.recovered_at_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        # 设置静默期（恢复后再触发需等待 60 秒）
        self._silenced_until[key] = time.time() + 60
        with self._lock:
            self._save()

    def _trigger(self, rule, host, metric, value, threshold, message):
        """服务告警直接触发"""
        key = f"{rule.id}|{host}"
        if key in self._active_events:
            return
        ev = AlertEvent(
            rule_id=rule.id, rule_name=rule.name, host=host,
            metric=metric, value=value, threshold=threshold,
            severity=rule.severity, message=message,
        )
        with self._lock:
            self._active_events[key] = ev
            self._history.append(ev)
            self._save()
        self._notify(ev, rule)

    def _notify(self, event: AlertEvent, rule: AlertRule):
        """发送通知"""
        event.notified = True
        for ch in rule.channels:
            try:
                if ch == "sound":
                    SoundChannel.send(event, {})
                elif ch == "system":
                    SystemTrayChannel.send(event, {"app": self._app})
                elif ch.startswith("webhook:"):
                    wh_name = ch.split(":", 1)[1]
                    cfg = self._webhook_configs.get(wh_name, {})
                    WebhookChannel.send(event, cfg)
            except Exception as e:
                print(f"通知失败 {ch}: {e}")
        # 同时写入审计
        try:
            from app.audit_log import AuditLogger
            AuditLogger.instance().log(
                "触发告警", target=f"{event.rule_name}@{event.host}",
                result="warn", details={
                    "metric": event.metric, "value": event.value,
                    "threshold": event.threshold, "severity": event.severity,
                },
            )
        except Exception:
            pass

    # ---- 历史查询 ----
    def get_history(self, limit: int = 200, severity: str = "",
                    host: str = "", only_active: bool = False) -> List[AlertEvent]:
        out = list(self._history)
        if severity and severity != "全部":
            out = [e for e in out if e.severity == severity]
        if host:
            out = [e for e in out if e.host == host]
        if only_active:
            out = [e for e in self._active_events.values()]
        return out[-limit:][::-1]

    def get_active_events(self) -> List[AlertEvent]:
        return list(self._active_events.values())

    def acknowledge(self, event_id: str, user: str = "admin"):
        for ev in self._history:
            if ev.id == event_id:
                ev.acknowledged = True
                ev.acknowledged_by = user
                ev.ack_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                key = f"{ev.rule_id}|{ev.host}"
                self._active_events.pop(key, None)
                self._save()
                return True
        return False

    def get_stats(self) -> dict:
        active = len(self._active_events)
        total = len(self._history)
        critical = sum(1 for e in self._active_events.values() if e.severity == "critical")
        warn = sum(1 for e in self._active_events.values() if e.severity == "warn")
        last_24h = sum(1 for e in self._history if time.time() - e.fired_at < 86400)
        return {
            "active": active, "total": total, "critical": critical,
            "warn": warn, "last_24h": last_24h,
        }


# ============================================================
# 告警编辑对话框
# ============================================================

class AlertRuleEditDialog(QDialog):
    """添加/编辑告警规则"""

    def __init__(self, rule: Optional[AlertRule] = None, available_hosts: List[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑告警规则" if rule else "添加告警规则")
        self.setMinimumWidth(500)
        self._rule = rule

        f = QFormLayout(self)

        self._name = QLineEdit()
        self._name.setPlaceholderText("如：CPU 高负载")
        f.addRow("规则名称:", self._name)

        self._metric = QComboBox()
        self._metric.addItems([
            "cpu (CPU 使用率 %)", "mem (内存使用率 %)", "disk (磁盘使用率 %)",
            "load (系统负载 1min)", "net_in (入站流量 KB/s)",
            "net_out (出站流量 KB/s)",
        ])
        f.addRow("监控指标:", self._metric)

        self._op = QComboBox()
        self._op.addItems([">", ">=", "<", "<=", "==", "!="])
        f.addRow("比较运算符:", self._op)

        self._threshold = QLineEdit()
        self._threshold.setPlaceholderText("如：80")
        f.addRow("阈值:", self._threshold)

        self._duration = QSpinBox()
        self._duration.setRange(0, 3600)
        self._duration.setSuffix(" 秒 (0=立即)")
        f.addRow("持续时长:", self._duration)

        self._severity = QComboBox()
        self._severity.addItems(["info", "warn", "critical"])
        f.addRow("严重程度:", self._severity)

        # 通知渠道
        ch_group = QGroupBox("通知渠道")
        ch_lay = QVBoxLayout(ch_group)
        self._ch_sound = QCheckBox("🔊 声音")
        self._ch_system = QCheckBox("💬 系统通知")
        ch_lay.addWidget(self._ch_sound)
        ch_lay.addWidget(self._ch_system)
        self._webhook_chks: Dict[str, QCheckBox] = {}
        for wh in AlertCenter.instance().get_webhook_configs().keys():
            cb = QCheckBox(f"🌐 Webhook: {wh}")
            ch_lay.addWidget(cb)
            self._webhook_chks[wh] = cb
        f.addRow(ch_group)

        # 主机范围
        self._hosts = QLineEdit()
        self._hosts.setPlaceholderText("留空=全部主机，逗号分隔")
        if available_hosts:
            self._hosts.setToolTip(f"可用: {', '.join(available_hosts[:5])}...")
        f.addRow("主机范围:", self._hosts)

        self._desc = QLineEdit()
        self._desc.setPlaceholderText("可选")
        f.addRow("描述:", self._desc)

        self._enabled = QCheckBox("启用此规则")
        self._enabled.setChecked(True)
        f.addRow("", self._enabled)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

        if rule:
            self._name.setText(rule.name)
            for i in range(self._metric.count()):
                if self._metric.itemText(i).startswith(rule.metric + " ") or self._metric.itemText(i).startswith(rule.metric + "("):
                    self._metric.setCurrentIndex(i)
                    break
            self._op.setCurrentText(rule.op)
            self._threshold.setText(str(rule.threshold))
            self._duration.setValue(rule.duration)
            self._severity.setCurrentText(rule.severity)
            self._ch_sound.setChecked("sound" in rule.channels)
            self._ch_system.setChecked("system" in rule.channels)
            for wh_name, cb in self._webhook_chks.items():
                cb.setChecked(f"webhook:{wh_name}" in rule.channels)
            self._hosts.setText(",".join(rule.hosts))
            self._desc.setText(rule.description)
            self._enabled.setChecked(rule.enabled)

    def _on_accept(self):
        try:
            threshold = float(self._threshold.text().strip())
        except ValueError:
            QMessageBox.warning(self, "错误", "阈值必须是数字")
            return
        if not self._name.text().strip():
            QMessageBox.warning(self, "错误", "请填写规则名称")
            return
        self.accept()

    def get_rule(self) -> AlertRule:
        metric_text = self._metric.currentText()
        metric = metric_text.split(" ")[0]
        channels = []
        if self._ch_sound.isChecked():
            channels.append("sound")
        if self._ch_system.isChecked():
            channels.append("system")
        for wh_name, cb in self._webhook_chks.items():
            if cb.isChecked():
                channels.append(f"webhook:{wh_name}")
        hosts_text = self._hosts.text().strip()
        hosts = [h.strip() for h in hosts_text.split(",") if h.strip()] if hosts_text else []
        try:
            threshold = float(self._threshold.text().strip())
        except ValueError:
            threshold = 0
        if self._rule:
            rule = self._rule
            rule.name = self._name.text().strip()
            rule.metric = metric
            rule.op = self._op.currentText()
            rule.threshold = threshold
            rule.duration = self._duration.value()
            rule.severity = self._severity.currentText()
            rule.channels = channels
            rule.hosts = hosts
            rule.description = self._desc.text().strip()
            rule.enabled = self._enabled.isChecked()
            return rule
        else:
            return AlertRule(
                name=self._name.text().strip(), metric=metric,
                op=self._op.currentText(), threshold=threshold,
                duration=self._duration.value(), severity=self._severity.currentText(),
                channels=channels, enabled=self._enabled.isChecked(),
                hosts=hosts, description=self._desc.text().strip(),
            )


# ============================================================
# Webhook 配置对话框
# ============================================================

class WebhookConfigDialog(QDialog):
    """配置 Webhook 通知渠道"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Webhook 通知配置")
        self.setMinimumSize(560, 480)
        self._configs = AlertCenter.instance().get_webhook_configs()
        self._current_name: Optional[str] = None

        layout = QHBoxLayout(self)

        # 左侧列表
        left = QFrame()
        left.setFixedWidth(170)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(6, 6, 6, 6)
        self._list = QListWidget()
        self._list.itemSelectionChanged.connect(self._on_select)
        ll.addWidget(self._list, 1)
        bl = QHBoxLayout()
        b_add = QPushButton("+ 新建")
        b_add.clicked.connect(self._new_webhook)
        b_del = QPushButton("删除")
        b_del.clicked.connect(self._del_webhook)
        bl.addWidget(b_add)
        bl.addWidget(b_del)
        ll.addLayout(bl)
        layout.addWidget(left)

        # 右侧表单
        right = QFrame()
        rl = QFormLayout(right)
        rl.setContentsMargins(8, 8, 8, 8)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("如：飞书生产告警")
        rl.addRow("名称:", self._name_edit)
        self._platform = QComboBox()
        self._platform.addItems(["custom (通用)", "feishu (飞书)", "dingtalk (钉钉)",
                                  "wecom (企业微信)", "slack"])
        rl.addRow("平台:", self._platform)
        self._url = QLineEdit()
        self._url.setPlaceholderText("https://...")
        rl.addRow("URL:", self._url)
        self._test_btn = QPushButton("发送测试消息")
        self._test_btn.clicked.connect(self._test)
        rl.addRow("", self._test_btn)
        self._save_btn = QPushButton("保存")
        self._save_btn.clicked.connect(self._save)
        rl.addRow("", self._save_btn)
        layout.addWidget(right, 1)

        self._refresh_list()
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _refresh_list(self):
        self._list.clear()
        for name in self._configs.keys():
            self._list.addItem(QListWidgetItem(name))

    def _on_select(self):
        items = self._list.selectedItems()
        if not items:
            return
        self._current_name = items[0].text()
        cfg = self._configs.get(self._current_name, {})
        self._name_edit.setText(self._current_name)
        self._platform.setCurrentText(cfg.get("platform", "custom"))
        self._url.setText(cfg.get("url", ""))

    def _new_webhook(self):
        name, ok = QLineEdit().text(), False
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "新建 Webhook", "Webhook 名称:")
        if ok and name.strip():
            self._configs[name.strip()] = {"platform": "custom", "url": ""}
            self._current_name = name.strip()
            self._refresh_list()
            self._name_edit.setText(name.strip())
            self._platform.setCurrentText("custom (通用)")
            self._url.setText("")

    def _del_webhook(self):
        if not self._current_name:
            return
        if QMessageBox.question(self, "确认", f"删除 Webhook [{self._current_name}]？") == QMessageBox.Yes:
            self._configs.pop(self._current_name, None)
            self._current_name = None
            self._refresh_list()

    def _save(self):
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请填写名称")
            return
        url = self._url.text().strip()
        platform_text = self._platform.currentText()
        platform = platform_text.split(" ")[0]
        self._configs[name] = {"platform": platform, "url": url}
        if self._current_name and self._current_name != name:
            self._configs.pop(self._current_name, None)
        self._current_name = name
        AlertCenter.instance().set_webhook_config(name, self._configs[name])
        self._refresh_list()
        QMessageBox.information(self, "成功", f"已保存 Webhook: {name}")

    def _test(self):
        name = self._name_edit.text().strip()
        url = self._url.text().strip()
        if not url:
            QMessageBox.warning(self, "错误", "请先填写 URL")
            return
        platform_text = self._platform.currentText()
        platform = platform_text.split(" ")[0]
        test_event = AlertEvent(
            rule_id="test", rule_name="测试告警", host="测试主机",
            metric="cpu", value=85.5, threshold=80, severity="warn",
            message="这是一条来自 AiinLink 的测试告警",
        )
        ok = WebhookChannel.send(test_event, {"platform": platform, "url": url})
        if ok:
            QMessageBox.information(self, "成功", "测试消息已发送")
        else:
            QMessageBox.warning(self, "失败", "测试消息发送失败，请检查 URL 与平台配置")


# ============================================================
# 告警中心 UI
# ============================================================

class AlertCenterWidget(QWidget):
    """告警中心主界面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._center = AlertCenter.instance()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_all)
        self._refresh_timer.start(3000)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 顶部概览卡片
        stats_lay = QHBoxLayout()
        self._stat_active = self._make_stat_card("🔴 活动告警", "0", DANGER)
        self._stat_critical = self._make_stat_card("⛔ 严重", "0", DANGER)
        self._stat_warn = self._make_stat_card("⚠ 警告", "0", WARN)
        self._stat_24h = self._make_stat_card("🕐 24h 内", "0", PRIMARY)
        self._stat_total = self._make_stat_card("📊 总计", "0", FG_SECONDARY)
        for w in (self._stat_active, self._stat_critical, self._stat_warn,
                  self._stat_24h, self._stat_total):
            stats_lay.addWidget(w)
        layout.addLayout(stats_lay)

        # 标签页
        self._tabs = QTabWidget()

        # Tab 1: 活动告警 + 历史
        events_widget = QWidget()
        el = QVBoxLayout(events_widget)
        el.setContentsMargins(4, 4, 4, 4)
        bar1 = QHBoxLayout()
        self._sev_filter = QComboBox()
        self._sev_filter.addItems(["全部", "critical", "warn", "info"])
        self._sev_filter.currentTextChanged.connect(self._refresh_events)
        bar1.addWidget(QLabel("严重程度:"))
        bar1.addWidget(self._sev_filter)
        self._only_active = QCheckBox("仅活动告警")
        self._only_active.toggled.connect(self._refresh_events)
        bar1.addWidget(self._only_active)
        bar1.addStretch()
        b_ack = QPushButton("✓ 确认选中")
        b_ack.clicked.connect(self._ack_selected)
        bar1.addWidget(b_ack)
        el.addLayout(bar1)
        self._event_table = QTableWidget(0, 6)
        self._event_table.setHorizontalHeaderLabels(
            ["状态", "时间", "规则", "主机", "指标值", "持续时间"])
        self._event_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._event_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._event_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        el.addWidget(self._event_table, 1)
        self._tabs.addTab(events_widget, "📋 告警事件")

        # Tab 2: 告警规则
        rules_widget = QWidget()
        rl = QVBoxLayout(rules_widget)
        rl.setContentsMargins(4, 4, 4, 4)
        bar2 = QHBoxLayout()
        b_add = QPushButton("+ 添加规则")
        b_add.clicked.connect(self._add_rule)
        b_edit = QPushButton("编辑")
        b_edit.clicked.connect(self._edit_rule)
        b_del = QPushButton("删除")
        b_del.clicked.connect(self._del_rule)
        b_toggle = QPushButton("启用/禁用")
        b_toggle.clicked.connect(self._toggle_rule)
        b_wh = QPushButton("🌐 Webhook 配置")
        b_wh.clicked.connect(self._config_webhook)
        bar2.addWidget(b_add)
        bar2.addWidget(b_edit)
        bar2.addWidget(b_del)
        bar2.addWidget(b_toggle)
        bar2.addStretch()
        bar2.addWidget(b_wh)
        rl.addLayout(bar2)
        self._rule_table = QTableWidget(0, 6)
        self._rule_table.setHorizontalHeaderLabels(
            ["启用", "名称", "指标", "条件", "通知渠道", "主机范围"])
        self._rule_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._rule_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._rule_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._rule_table.doubleClicked.connect(self._edit_rule)
        rl.addWidget(self._rule_table, 1)
        self._tabs.addTab(rules_widget, "⚙ 告警规则")

        layout.addWidget(self._tabs, 1)

        self._refresh_all()

    def _make_stat_card(self, title: str, value: str, color: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background-color: {BG_PANEL}; border: 1px solid {BORDER}; "
            f"border-radius: {RADIUS_MD}px; }}"
        )
        card.setMinimumHeight(70)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 8, 12, 8)
        t = QLabel(title)
        t.setStyleSheet(f"color: {FG_SECONDARY}; font-size: 11px;")
        v = QLabel(value)
        v.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: 700;")
        v.setObjectName("stat_value")
        lay.addWidget(t)
        lay.addWidget(v)
        lay.addStretch()
        # 存储引用
        card.value_label = v
        return card

    def _refresh_all(self):
        stats = self._center.get_stats()
        self._stat_active.value_label.setText(str(stats["active"]))
        self._stat_critical.value_label.setText(str(stats["critical"]))
        self._stat_warn.value_label.setText(str(stats["warn"]))
        self._stat_24h.value_label.setText(str(stats["last_24h"]))
        self._stat_total.value_label.setText(str(stats["total"]))
        self._refresh_events()
        self._refresh_rules()

    def _refresh_events(self):
        sev = self._sev_filter.currentText()
        only_active = self._only_active.isChecked()
        events = self._center.get_history(limit=500, severity=sev, only_active=only_active)
        self._event_table.setRowCount(0)
        for ev in events:
            row = self._event_table.rowCount()
            self._event_table.insertRow(row)
            # 状态
            if ev.recovered_at is None and not ev.acknowledged:
                state_text = "🔥 活动"
                state_color = DANGER
            elif ev.acknowledged:
                state_text = "✓ 已确认"
                state_color = FG_TERTIARY
            else:
                state_text = "✓ 已恢复"
                state_color = SUCCESS
            si = QTableWidgetItem(state_text)
            si.setForeground(QColor(state_color))
            self._event_table.setItem(row, 0, si)
            # 时间
            ti = QTableWidgetItem(ev.fired_at_str)
            if ev.recovered_at_str:
                ti.setText(f"{ev.fired_at_str}\n→ {ev.recovered_at_str}")
            self._event_table.setItem(row, 1, ti)
            # 规则
            self._event_table.setItem(row, 2, QTableWidgetItem(ev.rule_name))
            # 主机
            self._event_table.setItem(row, 3, QTableWidgetItem(ev.host))
            # 指标值
            metric_item = QTableWidgetItem(
                f"{ev.metric}={ev.value:.1f} ({ev.op} {ev.threshold})")
            severity_color = {"critical": DANGER, "warn": WARN, "info": INFO}.get(ev.severity, FG_PRIMARY)
            metric_item.setForeground(QColor(severity_color))
            self._event_table.setItem(row, 4, metric_item)
            # 持续
            self._event_table.setItem(row, 5, QTableWidgetItem(ev.duration_str()))
            # 存 ID
            self._event_table.item(row, 0).setData(Qt.UserRole, ev.id)

    def _refresh_rules(self):
        rules = self._center.get_rules()
        self._rule_table.setRowCount(0)
        for r in rules:
            row = self._rule_table.rowCount()
            self._rule_table.insertRow(row)
            # 启用
            en_item = QTableWidgetItem("✓" if r.enabled else "✗")
            en_item.setForeground(QColor(SUCCESS if r.enabled else FG_DISABLED))
            en_item.setTextAlignment(Qt.AlignCenter)
            self._rule_table.setItem(row, 0, en_item)
            self._rule_table.setItem(row, 1, QTableWidgetItem(r.name))
            self._rule_table.setItem(row, 2, QTableWidgetItem(r.metric))
            cond = f"{r.op} {r.threshold}" + (f" (持续{r.duration}s)" if r.duration else "")
            self._rule_table.setItem(row, 3, QTableWidgetItem(cond))
            ch_text = ", ".join(c.replace("webhook:", "🌐") for c in r.channels) or "无"
            self._rule_table.setItem(row, 4, QTableWidgetItem(ch_text))
            self._rule_table.setItem(row, 5, QTableWidgetItem(
                "全部" if not r.hosts else ", ".join(r.hosts)))
            self._rule_table.item(row, 1).setData(Qt.UserRole, r.id)

    def _add_rule(self):
        dlg = AlertRuleEditDialog(parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._center.add_rule(dlg.get_rule())
            self._refresh_rules()

    def _edit_rule(self):
        row = self._rule_table.currentRow()
        if row < 0:
            return
        rule_id = self._rule_table.item(row, 1).data(Qt.UserRole)
        rule = self._center.get_rule(rule_id)
        if not rule:
            return
        dlg = AlertRuleEditDialog(rule=rule, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self._center.update_rule(dlg.get_rule())
            self._refresh_rules()

    def _del_rule(self):
        row = self._rule_table.currentRow()
        if row < 0:
            return
        rule_id = self._rule_table.item(row, 1).data(Qt.UserRole)
        rule = self._center.get_rule(rule_id)
        if rule and QMessageBox.question(
            self, "确认", f"删除规则 [{rule.name}]？"
        ) == QMessageBox.Yes:
            self._center.delete_rule(rule_id)
            self._refresh_rules()

    def _toggle_rule(self):
        row = self._rule_table.currentRow()
        if row < 0:
            return
        rule_id = self._rule_table.item(row, 1).data(Qt.UserRole)
        rule = self._center.get_rule(rule_id)
        if rule:
            rule.enabled = not rule.enabled
            self._center.update_rule(rule)
            self._refresh_rules()

    def _config_webhook(self):
        dlg = WebhookConfigDialog(self)
        dlg.exec()
        self._refresh_rules()

    def _ack_selected(self):
        row = self._event_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选择要确认的告警")
            return
        ev_id = self._event_table.item(row, 0).data(Qt.UserRole)
        if self._center.acknowledge(ev_id):
            self._refresh_all()
            QMessageBox.information(self, "成功", "已确认告警")

    def stop(self):
        self._refresh_timer.stop()
