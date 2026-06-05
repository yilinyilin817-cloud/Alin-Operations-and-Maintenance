"""
后台工作线程集合
所有耗时操作均在此定义，确保不阻塞 UI 主线程
"""

from PySide6.QtCore import QThread, Signal
import subprocess
import time

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class SpeedMonitorWorker(QThread):
    """实时网速监控线程"""
    speed_update = Signal(float, float)  # upload_speed (KB/s), download_speed (KB/s)

    def __init__(self, interval: float = 1.0):
        super().__init__()
        self.interval = interval
        self._running = True

    def run(self):
        if not HAS_PSUTIL:
            self.speed_update.emit(0.0, 0.0)
            return

        prev_upload = psutil.net_io_counters().bytes_sent
        prev_download = psutil.net_io_counters().bytes_recv

        while self._running:
            time.sleep(self.interval)
            if not self._running:
                break

            current_upload = psutil.net_io_counters().bytes_sent
            current_download = psutil.net_io_counters().bytes_recv

            upload_speed = (current_upload - prev_upload) / self.interval / 1024
            download_speed = (current_download - prev_download) / self.interval / 1024

            self.speed_update.emit(upload_speed, download_speed)

            prev_upload = current_upload
            prev_download = current_download

    def stop(self):
        self._running = False


class SystemInfoWorker(QThread):
    """获取系统信息的工作线程"""
    info_ready = Signal(dict)

    def run(self):
        info = {}
        try:
            if HAS_PSUTIL:
                info["cpu_percent"] = psutil.cpu_percent(interval=1)
                info["memory_percent"] = psutil.virtual_memory().percent
                info["memory_used"] = psutil.virtual_memory().used
                info["memory_total"] = psutil.virtual_memory().total
                info["disk_percent"] = psutil.disk_usage("/").percent if __import__("platform").system() != "Windows" else psutil.disk_usage("C:\\").percent
                info["boot_time"] = psutil.boot_time()
                info["connections"] = len(psutil.net_connections())
            else:
                info["cpu_percent"] = 0
                info["memory_percent"] = 0
        except Exception as e:
            info["error"] = str(e)

        self.info_ready.emit(info)


class QuickDiagnosisWorker(QThread):
    """一键体检工作线程"""
    progress = Signal(str)  # 当前检查项
    result = Signal(dict)   # 检查结果

    def __init__(self, target: str = ""):
        super().__init__()
        self.target = target

    def run(self):
        import socket
        import platform

        results = {}

        # 1. 检查本地网络接口
        self.progress.emit("检查本地网络接口...")
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            results["local_ip"] = local_ip
            results["hostname"] = hostname
        except Exception as e:
            results["local_ip"] = f"获取失败: {e}"

        # 2. 检查 DNS 解析
        self.progress.emit("检查 DNS 解析...")
        try:
            socket.getaddrinfo("www.baidu.com", 80)
            results["dns"] = "正常"
        except Exception:
            results["dns"] = "异常"

        # 3. 检查网关连通性
        self.progress.emit("检查网关连通性...")
        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ["ping", "-n", "1", "-w", "3000", local_ip],
                    capture_output=True, text=True, timeout=5
                )
            else:
                result = subprocess.run(
                    ["ping", "-c", "1", "-W", "3", local_ip],
                    capture_output=True, text=True, timeout=5
                )
            results["gateway_ping"] = "正常" if result.returncode == 0 else "异常"
        except Exception:
            results["gateway_ping"] = "超时"

        # 4. 检查外网连通性
        self.progress.emit("检查外网连通性...")
        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ["ping", "-n", "1", "-w", "3000", "8.8.8.8"],
                    capture_output=True, text=True, timeout=5
                )
            else:
                result = subprocess.run(
                    ["ping", "-c", "1", "-W", "3", "8.8.8.8"],
                    capture_output=True, text=True, timeout=5
                )
            results["internet_ping"] = "正常" if result.returncode == 0 else "异常"
        except Exception:
            results["internet_ping"] = "超时"

        # 5. 检查目标主机（如果有）
        if self.target:
            self.progress.emit(f"检查目标主机 {self.target}...")
            try:
                if platform.system() == "Windows":
                    result = subprocess.run(
                        ["ping", "-n", "2", "-w", "3000", self.target],
                        capture_output=True, text=True, timeout=10
                    )
                else:
                    result = subprocess.run(
                        ["ping", "-c", "2", "-W", "3", self.target],
                        capture_output=True, text=True, timeout=10
                    )
                results["target_ping"] = "正常" if result.returncode == 0 else "异常"
            except Exception:
                results["target_ping"] = "超时"

        self.result.emit(results)


# ================================================
# 企业级运维工作线程
# ================================================

import threading as _threading
import time as _time


class SSHMetricsWorker(QThread):
    """通过 SSH 采集远端服务器 CPU/内存/磁盘/网络/负载等关键指标"""
    metrics_ready = Signal(dict)  # 含 ok / error / 各项指标
    sample = Signal(dict)        # 同上

    def __init__(self, host: str, port: int, username: str,
                 auth_type: str = "password", password: str = "",
                 key_path: str = "", key_passphrase: str = "",
                 interval: float = 3.0, max_samples: int = 120):
        super().__init__()
        self.host = host
        self.port = port
        self.username = username
        self.auth_type = auth_type
        self.password = password
        self.key_path = key_path
        self.key_passphrase = key_passphrase
        self.interval = interval
        self.max_samples = max_samples
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True

    def _connect(self):
        import paramiko
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        if self.auth_type == "key" and self.key_path:
            client.connect(
                self.host, port=self.port, username=self.username,
                key_filename=self.key_path, password=self.key_passphrase or None,
                timeout=8, look_for_keys=False, allow_agent=False,
            )
        else:
            client.connect(
                self.host, port=self.port, username=self.username,
                password=self.password, timeout=8, look_for_keys=False, allow_agent=False,
            )
        return client

    def _run_remote(self, client, cmd: str) -> str:
        stdin, stdout, stderr = client.exec_command(cmd, timeout=8)
        return stdout.read().decode("utf-8", errors="replace").strip()

    def _collect(self, client) -> dict:
        """执行远端命令采集指标，跨平台兼容"""
        is_linux = True
        try:
            uname = self._run_remote(client, "uname -s 2>/dev/null || echo Windows")
            if "Windows" in uname:
                is_linux = False
        except Exception:
            is_linux = True

        info = {"is_linux": is_linux, "timestamp": _time.time()}

        try:
            if is_linux:
                # CPU 使用率（取 1s 差值）
                cpu_cmd = (
                    "top -bn1 | grep 'Cpu(s)' | awk '{print $2+$4}' "
                    "|| grep 'cpu ' /proc/stat | awk '{u=$2+$4; t=$2+$3+$4+$5+$6+$7+$8; printf \"%.1f\", 100*u/t}'"
                )
                try:
                    info["cpu_percent"] = float(self._run_remote(client, cpu_cmd))
                except Exception:
                    info["cpu_percent"] = -1.0

                # 内存
                try:
                    mem = self._run_remote(client, "free -m | grep Mem")
                    parts = mem.split()
                    if len(parts) >= 3:
                        total = float(parts[1]); used = float(parts[2])
                        info["mem_total_mb"] = total
                        info["mem_used_mb"] = used
                        info["mem_percent"] = round(used / total * 100, 1) if total else 0
                except Exception:
                    pass

                # 磁盘（根分区）
                try:
                    df = self._run_remote(client, "df -P / | tail -1")
                    parts = df.split()
                    if len(parts) >= 5:
                        total = int(parts[1]); used = int(parts[2])
                        info["disk_total_gb"] = round(total / 1024 / 1024, 1)
                        info["disk_used_gb"] = round(used / 1024 / 1024, 1)
                        info["disk_percent"] = round(used / total * 100, 1) if total else 0
                except Exception:
                    pass

                # 负载
                try:
                    load = self._run_remote(client, "cat /proc/loadavg").split()
                    if len(load) >= 3:
                        info["load1"] = float(load[0])
                        info["load5"] = float(load[1])
                        info["load15"] = float(load[2])
                except Exception:
                    pass

                # 网卡流量（汇总）
                try:
                    rx = self._run_remote(client, "cat /proc/net/dev | awk 'NR>2 && $1!=\"lo:\" {rx+=$2} END{print rx}'")
                    tx = self._run_remote(client, "cat /proc/net/dev | awk 'NR>2 && $1!=\"lo:\" {tx+=$10} END{print tx}'")
                    info["net_rx_bytes"] = int(rx) if rx.isdigit() else 0
                    info["net_tx_bytes"] = int(tx) if tx.isdigit() else 0
                except Exception:
                    pass

                # 运行时长
                try:
                    up = self._run_remote(client, "cat /proc/uptime").split()[0]
                    info["uptime_sec"] = int(float(up))
                except Exception:
                    pass

                # 主机名
                try:
                    info["hostname"] = self._run_remote(client, "hostname")
                except Exception:
                    pass
            else:
                # Windows 远端
                ps_cmd = (
                    "powershell -NoProfile -Command "
                    "\"[math]::Round((Get-Counter '\\Processor(_Total)\\% Processor Time').CounterSamples.CookedValue,1)\""
                )
                try:
                    info["cpu_percent"] = float(self._run_remote(client, ps_cmd).strip())
                except Exception:
                    info["cpu_percent"] = -1.0

                mem_cmd = (
                    "powershell -NoProfile -Command "
                    "\"$os=Get-CimInstance Win32_OperatingSystem; "
                    "[pscustomobject]@{Total=[math]::Round($os.TotalVisibleMemorySize/1024,1); "
                    "Used=[math]::Round(($os.TotalVisibleMemorySize-$os.FreePhysicalMemory)/1024,1)} | "
                    "ConvertTo-Json -Compress\""
                )
                try:
                    import json
                    data = json.loads(self._run_remote(client, mem_cmd))
                    info["mem_total_mb"] = float(data.get("Total", 0))
                    info["mem_used_mb"] = float(data.get("Used", 0))
                    if info["mem_total_mb"]:
                        info["mem_percent"] = round(info["mem_used_mb"] / info["mem_total_mb"] * 100, 1)
                except Exception:
                    pass

                info["hostname"] = self._run_remote(client, "hostname")
        except Exception as e:
            info["error"] = str(e)

        return info

    def run(self):
        try:
            client = self._connect()
        except Exception as e:
            self.metrics_ready.emit({"ok": False, "error": f"连接失败: {e}",
                                     "host": self.host, "timestamp": _time.time()})
            return

        # 连接成功提示
        first = {"ok": True, "host": self.host, "is_first": True, "timestamp": _time.time()}
        first.update(self._collect(client))
        self.metrics_ready.emit(first)
        if self._stop_flag:
            client.close()
            return

        while not self._stop_flag:
            _time.sleep(self.interval)
            if self._stop_flag:
                break
            try:
                sample = {"ok": True, "host": self.host, "timestamp": _time.time()}
                sample.update(self._collect(client))
                self.sample.emit(sample)
            except Exception as e:
                self.sample.emit({"ok": False, "host": self.host, "error": str(e),
                                  "timestamp": _time.time()})
                break

        try:
            client.close()
        except Exception:
            pass


class SSHCommandWorker(QThread):
    """通过 SSH 在远端执行单条命令并返回结果"""
    result_ready = Signal(str, str, str)  # host, output, error

    def __init__(self, host: str, port: int, username: str, command: str,
                 auth_type: str = "password", password: str = "",
                 key_path: str = "", key_passphrase: str = "", timeout: int = 15):
        super().__init__()
        self.host = host
        self.port = port
        self.username = username
        self.command = command
        self.auth_type = auth_type
        self.password = password
        self.key_path = key_path
        self.key_passphrase = key_passphrase
        self.timeout = timeout

    def run(self):
        try:
            import paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            if self.auth_type == "key" and self.key_path:
                client.connect(
                    self.host, port=self.port, username=self.username,
                    key_filename=self.key_path, password=self.key_passphrase or None,
                    timeout=8, look_for_keys=False, allow_agent=False,
                )
            else:
                client.connect(
                    self.host, port=self.port, username=self.username,
                    password=self.password, timeout=8, look_for_keys=False, allow_agent=False,
                )
            stdin, stdout, stderr = client.exec_command(self.command, timeout=self.timeout)
            output = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            client.close()
            self.result_ready.emit(self.host, output, err)
        except Exception as e:
            self.result_ready.emit(self.host, "", str(e))


class LogTailWorker(QThread):
    """SSH 远程日志实时 tail，新行通过 signal 输出"""
    line_received = Signal(str, str)  # host, line
    status = Signal(str, bool)        # host, ok
    error = Signal(str, str)          # host, error_msg

    def __init__(self, host: str, port: int, username: str, log_path: str,
                 auth_type: str = "password", password: str = "",
                 key_path: str = "", key_passphrase: str = "",
                 lines: int = 200, follow: bool = True, interval: float = 1.0):
        super().__init__()
        self.host = host
        self.port = port
        self.username = username
        self.log_path = log_path
        self.auth_type = auth_type
        self.password = password
        self.key_path = key_path
        self.key_passphrase = key_passphrase
        self.lines = lines
        self.follow = follow
        self.interval = interval
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True

    def run(self):
        try:
            import paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            if self.auth_type == "key" and self.key_path:
                client.connect(
                    self.host, port=self.port, username=self.username,
                    key_filename=self.key_path, password=self.key_passphrase or None,
                    timeout=8, look_for_keys=False, allow_agent=False,
                )
            else:
                client.connect(
                    self.host, port=self.port, username=self.username,
                    password=self.password, timeout=8, look_for_keys=False, allow_agent=False,
                )

            is_windows = False
            try:
                test = client.exec_command("uname -s 2>/dev/null || echo Windows", timeout=5)
                if "Windows" in test[1].read().decode("utf-8", errors="replace"):
                    is_windows = True
            except Exception:
                pass

            if is_windows:
                # Windows: 使用 Get-Content -Wait
                safe_path = self.log_path.replace('"', '\\"')
                cmd = f'powershell -NoProfile -Command "Get-Content -Path \\"{safe_path}\\" -Tail {self.lines} -Wait"'
            else:
                # Linux: tail -F
                cmd = f"tail -n {self.lines} -F '{self.log_path}'"

            transport = client.get_transport()
            channel = transport.open_session()
            channel.settimeout(2)
            channel.exec_command(cmd)

            self.status.emit(self.host, True)
            buf = ""
            while not self._stop_flag:
                try:
                    if channel.recv_ready():
                        data = channel.recv(4096).decode("utf-8", errors="replace")
                        buf += data
                        while "\n" in buf:
                            line, buf = buf.split("\n", 1)
                            self.line_received.emit(self.host, line.rstrip("\r"))
                    else:
                        _time.sleep(self.interval)
                except _threading.ThreadError:
                    pass
                except Exception:
                    _time.sleep(self.interval)
                if channel.closed or channel.exit_status_ready():
                    break

            try:
                channel.close()
            except Exception:
                pass
            try:
                client.close()
            except Exception:
                pass
            self.status.emit(self.host, False)
        except Exception as e:
            self.error.emit(self.host, str(e))


class ServiceHealthCheckWorker(QThread):
    """对一组目标执行 HTTP/TCP 健康检查（周期运行）"""
    cycle_done = Signal(dict)  # {target_key: {ok, latency_ms, status, error, ts}}

    def __init__(self, targets: list, interval: float = 10.0, timeout: float = 5.0):
        """
        targets: [{"name", "type": "http"|"tcp", "target": "url" or "host:port",
                   "expect_status": 200, "method": "GET"}]
        """
        super().__init__()
        self.targets = targets
        self.interval = interval
        self.timeout = timeout
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True

    def _check_one(self, t: dict) -> dict:
        import socket
        ts = _time.time()
        result = {"name": t.get("name", ""), "type": t.get("type", "tcp"),
                  "target": t.get("target", ""), "ts": ts, "ok": False}
        try:
            if t.get("type") == "http":
                import urllib.request
                url = t.get("target", "")
                req = urllib.request.Request(
                    url, method=t.get("method", "GET"),
                    headers={"User-Agent": "AiinLink-HealthCheck/1.0"}
                )
                start = _time.time()
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    status = resp.status
                    latency = (_time.time() - start) * 1000
                result["status"] = status
                result["latency_ms"] = round(latency, 1)
                expect = t.get("expect_status", 200)
                result["ok"] = (status == expect) if expect else (200 <= status < 400)
            else:
                # TCP
                target = t.get("target", "")
                if ":" in target:
                    host, port = target.rsplit(":", 1)
                    port = int(port)
                else:
                    host, port = target, 80
                start = _time.time()
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.timeout)
                try:
                    sock.connect((host, port))
                    latency = (_time.time() - start) * 1000
                    result["ok"] = True
                    result["status"] = "open"
                    result["latency_ms"] = round(latency, 1)
                finally:
                    sock.close()
        except Exception as e:
            result["error"] = str(e)
        return result

    def run(self):
        while not self._stop_flag:
            cycle = {}
            for t in self.targets:
                if self._stop_flag:
                    break
                key = f"{t.get('name', '')}|{t.get('type', 'tcp')}|{t.get('target', '')}"
                cycle[key] = self._check_one(t)
            self.cycle_done.emit(cycle)
            # 等待下一个周期
            slept = 0.0
            while slept < self.interval and not self._stop_flag:
                _time.sleep(0.5)
                slept += 0.5


class BatchSSHCommandWorker(QThread):
    """批量在多台主机上执行同一命令"""
    result_ready = Signal(str, str, str, str)  # host, output, error, status
    finished_all = Signal(int, int)             # success_count, total
    progress = Signal(int, int)                 # current, total

    def __init__(self, hosts: list, command: str, concurrency: int = 5, timeout: int = 20):
        """
        hosts: [{"host", "port", "username", "auth_type", "password", "key_path", "key_passphrase"}]
        """
        super().__init__()
        self.hosts = hosts
        self.command = command
        self.concurrency = max(1, min(20, concurrency))
        self.timeout = timeout
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True

    def _exec_one(self, h: dict) -> tuple:
        host = h.get("host", "")
        try:
            import paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            if h.get("auth_type") == "key" and h.get("key_path"):
                client.connect(
                    host, port=h.get("port", 22), username=h.get("username", "root"),
                    key_filename=h.get("key_path"),
                    password=h.get("key_passphrase") or None,
                    timeout=8, look_for_keys=False, allow_agent=False,
                )
            else:
                client.connect(
                    host, port=h.get("port", 22), username=h.get("username", "root"),
                    password=h.get("password", ""), timeout=8,
                    look_for_keys=False, allow_agent=False,
                )
            stdin, stdout, stderr = client.exec_command(self.command, timeout=self.timeout)
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            client.close()
            status = "ok" if not err else "warn"
            return (host, out, err, status)
        except Exception as e:
            return (host, "", str(e), "fail")

    def run(self):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        total = len(self.hosts)
        success = 0
        done = 0
        with ThreadPoolExecutor(max_workers=self.concurrency) as ex:
            futures = {ex.submit(self._exec_one, h): h for h in self.hosts}
            for fut in as_completed(futures):
                if self._stop_flag:
                    break
                host, out, err, status = fut.result()
                self.result_ready.emit(host, out, err, status)
                if status == "ok":
                    success += 1
                done += 1
                self.progress.emit(done, total)
        self.finished_all.emit(success, total)
