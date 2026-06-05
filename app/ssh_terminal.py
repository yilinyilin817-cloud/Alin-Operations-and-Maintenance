"""
高仿真 SSH 终端模块
包含 SSH 连接管理和终端模拟器控件
"""

import time
import threading
from typing import Optional

from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtGui import QTextCursor, QFont, QKeyEvent, QTextCharFormat, QColor
from PySide6.QtWidgets import QPlainTextEdit, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import QProcess

try:
    import paramiko
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False

from app.ansi_parser import AnsiParser
from app.ssh_config import SSHConfigManager, SSHConnectionProfile


class SSHConnectionWorker(QThread):
    """SSH 连接工作线程"""
    connected = Signal(object)   # SSHClient
    error = Signal(str)
    auth_failed = Signal(str)

    def __init__(self, host: str, port: int, username: str,
                 password: str = "", key_path: str = "",
                 auth_type: str = "password", key_passphrase: str = ""):
        super().__init__()
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key_path = key_path
        self.auth_type = auth_type
        self.key_passphrase = key_passphrase
        self._start_time = 0

    def run(self):
        if not HAS_PARAMIKO:
            self.error.emit("Paramiko 未安装，请运行: pip install paramiko")
            return

        self._start_time = time.time()
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs = {
                "hostname": self.host,
                "port": self.port,
                "username": self.username,
                "timeout": 10,
            }

            if self.auth_type == "key" and self.key_path:
                connect_kwargs["key_filename"] = self.key_path
                if self.key_passphrase:
                    connect_kwargs["passphrase"] = self.key_passphrase
                connect_kwargs["look_for_keys"] = False
                connect_kwargs["allow_agent"] = False
            elif self.password:
                connect_kwargs["password"] = self.password
                connect_kwargs["look_for_keys"] = False
                connect_kwargs["allow_agent"] = False
            else:
                connect_kwargs["look_for_keys"] = True

            client.connect(**connect_kwargs)
            self.connected.emit(client)
        except paramiko.AuthenticationException as e:
            self.auth_failed.emit(f"认证失败: {e}")
        except paramiko.SSHException as e:
            self.error.emit(f"SSH 错误: {e}")
        except Exception as e:
            self.error.emit(f"连接失败: {e}")

    def get_duration_ms(self) -> int:
        """获取连接耗时（毫秒）"""
        return int((time.time() - self._start_time) * 1000) if self._start_time else 0


class ShellReaderThread(QThread):
    """SSH Shell 数据读取线程"""
    data_received = Signal(str)
    connection_closed = Signal()

    def __init__(self, channel):
        super().__init__()
        self.channel = channel
        self._running = True

    def run(self):
        while self._running:
            try:
                if self.channel.recv_ready():
                    data = self.channel.recv(4096)
                    if not data:
                        self.connection_closed.emit()
                        break
                    self.data_received.emit(data.decode("utf-8", errors="replace"))
                elif self.channel.exit_status_ready():
                    self.connection_closed.emit()
                    break
                else:
                    self.msleep(10)
            except Exception:
                self.connection_closed.emit()
                break

    def stop(self):
        self._running = False


class TerminalWidget(QPlainTextEdit):
    """
    自定义终端控件
    - 支持ANSI颜色渲染
    - 拦截键盘事件并发送到SSH通道
    - 支持Ghost Text补全
    """

    # 信号：用户输入的命令（用于Ghost Text和AI分析）
    command_entered = Signal(str)
    # 信号：请求AI补全
    completion_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        # 终端外观
        self.setFont(QFont("Consolas", 11))
        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #cccccc;
                border: none;
                padding: 4px;
            }
        """)

        # ANSI 解析器
        self.ansi_parser = AnsiParser()

        # SSH 通道
        self._channel = None
        self._reader_thread: Optional[ShellReaderThread] = None

        # 本地进程终端
        self._process: Optional[QProcess] = None
        self._is_local = False

        # 命令历史
        self._command_history = []
        self._history_index = -1
        self._current_input = ""

        # Ghost Text 相关
        self._ghost_text = ""
        self._ghost_format = QTextCharFormat()
        self._ghost_format.setForeground(QColor("#555555"))

        # 防抖定时器
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(500)
        self._debounce_timer.timeout.connect(self._on_debounce_timeout)

        # 终端状态
        self._is_connected = False
        self._prompt_detected = False

        self.setReadOnly(False)
        self.setCursorWidth(8)

    def set_channel(self, channel):
        """设置SSH通道并启动读取线程"""
        self._channel = channel
        self._is_connected = True
        self._is_local = False

        if self._channel:
            self._reader_thread = ShellReaderThread(self._channel)
            self._reader_thread.data_received.connect(self._on_data_received)
            self._reader_thread.connection_closed.connect(self._on_connection_closed)
            self._reader_thread.start()

    def start_local_shell(self):
        """启动本地 shell 进程（Windows: cmd, Linux/macOS: bash）"""
        import platform
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_local_output)
        self._process.finished.connect(self._on_local_finished)

        if platform.system() == "Windows":
            self._process.start("cmd.exe", ["/Q", "/K", "echo 本地终端已启动"])
        else:
            self._process.start("/bin/bash", ["-i"])

        if self._process.state() == QProcess.NotRunning:
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.End)
            fmt = QTextCharFormat()
            fmt.setForeground(QColor("#ff0000"))
            cursor.insertText("\n[无法启动本地终端]\n", fmt)
            self.setTextCursor(cursor)
            return False

        self._is_local = True
        self._is_connected = True
        return True

    def _on_local_output(self):
        """处理本地 shell 输出"""
        if not self._process:
            return
        data = self._process.readAllStandardOutput().data()
        if not data:
            return
        text = data.decode("utf-8", errors="replace")
        self._on_data_received(text)

    def _on_local_finished(self):
        """本地 shell 进程结束"""
        self._is_local = False
        self._is_connected = False
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#ff0000"))
        cursor.insertText("\n[本地终端已退出]\n", fmt)
        self.setTextCursor(cursor)

    def _on_data_received(self, data: str):
        """处理从SSH通道收到的数据"""
        # 清除Ghost Text
        self._clear_ghost_text()

        # 解析ANSI并追加到终端
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        segments = self.ansi_parser.parse(data)
        for text, fmt in segments:
            cursor.insertText(text, fmt)

        self.setTextCursor(cursor)
        self.ensureCursorVisible()

        # 检测命令提示符（简单启发式）
        self._prompt_detected = data.strip().endswith(("$", "#", ">", "~"))

    def _on_connection_closed(self):
        """连接关闭处理"""
        self._is_connected = False
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#ff0000"))
        cursor.insertText("\n[连接已关闭]\n", fmt)
        self.setTextCursor(cursor)

    def keyPressEvent(self, event: QKeyEvent):
        """键盘事件劫持：将按键转换为VT100字节码发送到SSH通道或本地进程"""
        if not self._is_connected:
            super().keyPressEvent(event)
            return

        # 本地进程模式
        if self._is_local and self._process:
            self._handle_local_key(event)
            return

        # SSH 模式
        if self._channel:
            self._handle_ssh_key(event)
            return

        super().keyPressEvent(event)

    def _handle_local_key(self, event: QKeyEvent):
        """处理本地进程按键"""
        key = event.key()
        text = event.text()
        modifiers = event.modifiers()

        if key == Qt.Key_Return or key == Qt.Key_Enter:
            self._process.write(b"\r\n")
            # 本地回显换行
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.End)
            cursor.insertText("\n")
            self.setTextCursor(cursor)
        elif key == Qt.Key_Backspace:
            self._process.write(b"\b")
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, 1)
            cursor.deleteChar()
            self.setTextCursor(cursor)
        elif key == Qt.Key_Tab:
            self._process.write(b"\t")
        elif modifiers & Qt.ControlModifier and key == Qt.Key_C:
            self._process.write(b"\x03")
        elif modifiers & Qt.ControlModifier and key == Qt.Key_D:
            self._process.write(b"\x04")
        elif modifiers & Qt.ControlModifier and key == Qt.Key_Z:
            self._process.write(b"\x1a")
        elif text and not (modifiers & Qt.ControlModifier):
            self._process.write(text.encode("utf-8", errors="replace"))
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.End)
            cursor.insertText(text)
            self.setTextCursor(cursor)
        else:
            super().keyPressEvent(event)

    def _handle_ssh_key(self, event: QKeyEvent):
        """处理 SSH 通道按键"""
        key = event.key()
        text = event.text()
        modifiers = event.modifiers()

        # 处理Ghost Text确认
        if self._ghost_text and key == Qt.Key_Right:
            self._accept_ghost_text()
            return

        # 清除Ghost Text
        if self._ghost_text and key not in (Qt.Key_Right,):
            self._clear_ghost_text()

        # 特殊按键映射到VT100序列
        bytes_to_send = b""

        if key == Qt.Key_Return or key == Qt.Key_Enter:
            bytes_to_send = b"\r"
            # 记录命令
            current_line = self._get_current_line()
            if current_line.strip():
                self._command_history.append(current_line.strip())
                self._history_index = len(self._command_history)
                self.command_entered.emit(current_line.strip())
        elif key == Qt.Key_Backspace:
            bytes_to_send = b"\x7f"
        elif key == Qt.Key_Tab:
            bytes_to_send = b"\t"
        elif key == Qt.Key_Up:
            bytes_to_send = b"\x1b[A"
            # 命令历史导航
            if self._command_history and self._history_index > 0:
                self._history_index -= 1
        elif key == Qt.Key_Down:
            bytes_to_send = b"\x1b[B"
            if self._history_index < len(self._command_history) - 1:
                self._history_index += 1
        elif key == Qt.Key_Right:
            bytes_to_send = b"\x1b[C"
        elif key == Qt.Key_Left:
            bytes_to_send = b"\x1b[D"
        elif key == Qt.Key_Home:
            bytes_to_send = b"\x1b[H"
        elif key == Qt.Key_End:
            bytes_to_send = b"\x1b[F"
        elif key == Qt.Key_Delete:
            bytes_to_send = b"\x1b[3~"
        elif key == Qt.Key_PageUp:
            bytes_to_send = b"\x1b[5~"
        elif key == Qt.Key_PageDown:
            bytes_to_send = b"\x1b[6~"
        elif modifiers & Qt.ControlModifier:
            # Ctrl 组合键
            if key == Qt.Key_C:
                bytes_to_send = b"\x03"
            elif key == Qt.Key_D:
                bytes_to_send = b"\x04"
            elif key == Qt.Key_Z:
                bytes_to_send = b"\x1a"
            elif key == Qt.Key_L:
                bytes_to_send = b"\x0c"
            elif key == Qt.Key_A:
                bytes_to_send = b"\x01"
            elif key == Qt.Key_E:
                bytes_to_send = b"\x05"
            elif key == Qt.Key_W:
                bytes_to_send = b"\x17"
            elif key == Qt.Key_U:
                bytes_to_send = b"\x15"
            elif key == Qt.Key_K:
                bytes_to_send = b"\x0b"
            else:
                # 其他Ctrl组合：转换为控制字符
                if 0x41 <= key <= 0x5A:
                    bytes_to_send = bytes([key - 0x40])
        elif modifiers & Qt.AltModifier:
            # Alt 组合键
            if text:
                bytes_to_send = b"\x1b" + text.encode("utf-8")
        else:
            # 普通字符
            if text:
                bytes_to_send = text.encode("utf-8")
                # 触发防抖（用于Ghost Text）
                self._debounce_timer.start()

        if bytes_to_send:
            try:
                self._channel.send(bytes_to_send)
            except Exception:
                pass
        else:
            super().keyPressEvent(event)

    def _get_current_line(self) -> str:
        """获取当前光标所在行的文本（去除提示符）"""
        cursor = self.textCursor()
        cursor.select(QTextCursor.LineUnderCursor)
        line = cursor.selectedText()
        return line

    def get_context_lines(self, n: int = 20) -> str:
        """获取最近 n 行的终端文本（用于AI上下文）"""
        doc = self.document()
        total_lines = doc.lineCount()
        start = max(0, total_lines - n)
        lines = []
        for i in range(start, total_lines):
            lines.append(doc.findBlockByLineNumber(i).text())
        return "\n".join(lines)

    # ---- Ghost Text 相关 ----

    def set_ghost_text(self, text: str):
        """设置Ghost Text（灰色预测文本）"""
        self._clear_ghost_text()
        if not text:
            return

        self._ghost_text = text
        cursor = self.textCursor()
        cursor.insertText(text, self._ghost_format)
        # 将光标移回Ghost Text之前
        cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, len(text))
        self.setTextCursor(cursor)

    def _accept_ghost_text(self):
        """接受Ghost Text（按右方向键确认）"""
        if not self._ghost_text:
            return

        # 将Ghost Text转为正式文本
        ghost = self._ghost_text
        self._ghost_text = ""

        # 重新设置格式为正常
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(ghost))
        normal_fmt = QTextCharFormat()
        normal_fmt.setForeground(QColor("#cccccc"))
        cursor.setCharFormat(normal_fmt)

        # 发送到SSH通道
        if self._channel:
            try:
                self._channel.send(ghost.encode("utf-8"))
            except Exception:
                pass

    def _clear_ghost_text(self):
        """清除Ghost Text"""
        if not self._ghost_text:
            return

        cursor = self.textCursor()
        # 选中并删除Ghost Text
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(self._ghost_text))
        cursor.removeSelectedText()
        self._ghost_text = ""

    def _on_debounce_timeout(self):
        """防抖超时，触发补全请求"""
        current_line = self._get_current_line()
        context = self.get_context_lines(10)
        self.completion_requested.emit(f"{context}\n当前输入: {current_line}")

    def send_text(self, text: str):
        """向SSH通道发送文本（用于快捷指令注入）"""
        if self._channel and self._is_connected:
            try:
                self._channel.send(text.encode("utf-8"))
            except Exception:
                pass

    def disconnect(self):
        """断开SSH连接或本地进程"""
        self._is_connected = False
        if self._reader_thread:
            self._reader_thread.stop()
            self._reader_thread.wait(2000)
        if self._channel:
            try:
                self._channel.close()
            except Exception:
                pass
        if self._process:
            try:
                self._process.terminate()
                if not self._process.waitForFinished(2000):
                    self._process.kill()
            except Exception:
                pass
            self._process = None
        self._is_local = False


class SSHTerminalTab(QWidget):
    """SSH 终端标签页（包含终端控件和连接状态栏）"""

    connection_status = Signal(str)  # 状态消息

    def __init__(self, config_manager: SSHConfigManager = None, parent=None):
        super().__init__(parent)

        self._config = config_manager
        self._client = None
        self._channel = None
        self._current_profile = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 状态栏
        self._status_bar = QHBoxLayout()
        self._status_label = QLabel("未连接")
        self._status_label.setStyleSheet("color: #888; padding: 2px 8px; background: #2d2d2d;")
        self._status_bar.addWidget(self._status_label)

        # 认证类型显示
        self._auth_label = QLabel("")
        self._auth_label.setStyleSheet("color: #666; padding: 2px 8px; background: #2d2d2d;")
        self._status_bar.addWidget(self._auth_label)

        self._status_bar.addStretch()

        # 错误日志按钮
        self._btn_error_log = QPushButton("错误日志")
        self._btn_error_log.setFixedWidth(70)
        self._btn_error_log.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #888;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 2px 6px;
                font-size: 11px;
            }
            QPushButton:hover { color: #ffaa00; border-color: #ffaa00; }
        """)
        self._btn_error_log.clicked.connect(self._show_error_log)
        self._btn_error_log.setVisible(False)
        self._status_bar.addWidget(self._btn_error_log)

        layout.addLayout(self._status_bar)

        # 终端控件
        self.terminal = TerminalWidget()
        layout.addWidget(self.terminal)

    def connect_to_host(self, host: str, port: int, username: str,
                        password: str = "", key_path: str = "",
                        auth_type: str = "password", key_passphrase: str = ""):
        """发起SSH连接"""
        self._status_label.setText(f"正在连接 {username}@{host}:{port}...")
        self._status_label.setStyleSheet("color: #ffaa00; padding: 2px 8px; background: #2d2d2d;")
        self._auth_label.setText(f"认证: {auth_type}")

        # 保存当前连接配置
        self._current_profile = SSHConnectionProfile(
            host=host,
            port=port,
            username=username,
            auth_type=auth_type,
            password=password,
            key_path=key_path,
            key_passphrase=key_passphrase,
        )

        self._worker = SSHConnectionWorker(host, port, username, password, key_path, auth_type, key_passphrase)
        self._worker.connected.connect(self._on_connected)
        self._worker.error.connect(self._on_error)
        self._worker.auth_failed.connect(self._on_auth_failed)
        self._worker.start()

    def _on_connected(self, client):
        """SSH连接成功"""
        self._client = client
        try:
            self._channel = client.invoke_shell(
                term="xterm-256color",
                width=120,
                height=40,
            )
            self.terminal.set_channel(self._channel)
            self._status_label.setText(f"已连接 - {client.get_transport().getpeername()[0]}")
            self._status_label.setStyleSheet("color: #00ff00; padding: 2px 8px; background: #2d2d2d;")
            self.connection_status.emit("connected")

            # 记录日志
            if self._config and self._current_profile:
                self._config.log_connect(
                    self._current_profile,
                    success=True,
                    duration_ms=self._worker.get_duration_ms()
                )
        except Exception as e:
            self._status_label.setText(f"Shell 启动失败: {e}")
            self._status_label.setStyleSheet("color: #ff0000; padding: 2px 8px; background: #2d2d2d;")
            self._btn_error_log.setVisible(True)

            # 记录日志
            if self._config and self._current_profile:
                self._config.log_connect(
                    self._current_profile,
                    success=False,
                    error=str(e),
                    duration_ms=self._worker.get_duration_ms()
                )

    def _on_error(self, msg: str):
        """连接错误"""
        self._status_label.setText(f"连接失败: {msg}")
        self._status_label.setStyleSheet("color: #ff0000; padding: 2px 8px; background: #2d2d2d;")
        self.connection_status.emit("error")
        self._btn_error_log.setVisible(True)

        # 记录日志
        if self._config and self._current_profile:
            self._config.log_connect(
                self._current_profile,
                success=False,
                error=msg,
                duration_ms=self._worker.get_duration_ms()
            )

    def _on_auth_failed(self, msg: str):
        """认证失败"""
        self._status_label.setText(f"认证失败: {msg}")
        self._status_label.setStyleSheet("color: #ff0000; padding: 2px 8px; background: #2d2d2d;")
        self.connection_status.emit("auth_failed")
        self._btn_error_log.setVisible(True)

        # 记录日志
        if self._config and self._current_profile:
            self._config.log_connect(
                self._current_profile,
                success=False,
                error=msg,
                duration_ms=self._worker.get_duration_ms()
            )

    def _show_error_log(self):
        """显示错误日志"""
        if not self._config:
            return

        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout

        dialog = QDialog(self)
        dialog.setWindowTitle("SSH 连接错误日志")
        dialog.setMinimumSize(500, 400)

        layout = QVBoxLayout(dialog)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #cccccc;
                font-family: Consolas;
                font-size: 12px;
            }
        """)

        # 获取错误日志
        error_log = self._config.get_error_log(30)
        for entry in error_log:
            time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.timestamp))
            text_edit.append(f'<span style="color:#ff6b6b;">[{time_str}]</span>')
            text_edit.append(f'  <span style="color:#ffaa00;">主机:</span> {entry.username}@{entry.host}:{entry.port}')
            text_edit.append(f'  <span style="color:#ffaa00;">认证:</span> {entry.auth_type}')
            text_edit.append(f'  <span style="color:#ff0000;">错误:</span> {entry.error_message}')
            text_edit.append(f'  <span style="color:#888;">耗时:</span> {entry.duration_ms}ms')
            text_edit.append("")

        layout.addWidget(text_edit)

        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(dialog.close)
        layout.addWidget(btn_close)

        dialog.exec_()

    def inject_command(self, command: str):
        """向终端注入命令（用于快捷指令）"""
        self.terminal.send_text(command + "\n")

    def start_local_shell(self):
        """启动本地终端"""
        self._status_label.setText("本地终端")
        self._status_label.setStyleSheet("color: #4ecdc4; padding: 2px 8px; background: #2d2d2d;")
        self._auth_label.setText("本地")
        self.terminal.start_local_shell()

    def disconnect(self):
        """断开连接"""
        self.terminal.disconnect()
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        self._status_label.setText("已断开连接")
        self._status_label.setStyleSheet("color: #888; padding: 2px 8px; background: #2d2d2d;")
