"""
原生网络探针模块
支持 ICMP/ARP 探测、端口扫描、路由追踪
"""

import subprocess
import socket
import re
import platform
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional

from PySide6.QtCore import QThread, Signal


class PingWorker(QThread):
    """ICMP Ping 探测工作线程"""
    result_ready = Signal(str, bool, float, str)  # host, reachable, latency_ms, output

    def __init__(self, host: str, count: int = 4, timeout: int = 5):
        super().__init__()
        self.host = host
        self.count = count
        self.timeout = timeout

    def run(self):
        try:
            param = "-n" if platform.system() == "Windows" else "-c"
            timeout_param = "-w" if platform.system() == "Windows" else "-W"
            cmd = ["ping", param, str(self.count), timeout_param, str(self.timeout), self.host]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout + self.count * 2
            )
            output = result.stdout

            # 解析延迟
            latency = -1.0
            if platform.system() == "Windows":
                match = re.search(r"平均 = (\d+)ms", output)
                if match:
                    latency = float(match.group(1))
            else:
                match = re.search(r"rtt min/avg/max/mdev = [\d.]+/([\d.]+)", output)
                if match:
                    latency = float(match.group(1))

            reachable = result.returncode == 0
            self.result_ready.emit(self.host, reachable, latency, output)
        except Exception as e:
            self.result_ready.emit(self.host, False, -1.0, str(e))


class PortScanWorker(QThread):
    """端口连通性扫描工作线程"""
    progress = Signal(int, int)  # current, total
    result_ready = Signal(str, dict)  # host, {port: open}
    error = Signal(str)  # error message

    def __init__(self, host: str, ports: List[int] = None, timeout: float = 1.0):
        super().__init__()
        self.host = host
        self.ports = ports or [21, 22, 23, 25, 53, 80, 110, 143, 443, 445,
                               993, 995, 1433, 3306, 3389, 5432, 5900, 6379,
                               8080, 8443, 9200, 27017]
        self.timeout = timeout

    def _scan_port(self, port: int) -> int:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            result = sock.connect_ex((self.host, port))
            return port if result == 0 else None
        except Exception:
            return None
        finally:
            if sock:
                sock.close()

    def run(self):
        results = {}
        total = len(self.ports)
        try:
            with ThreadPoolExecutor(max_workers=100) as executor:
                futures = {executor.submit(self._scan_port, p): p for p in self.ports}
                for i, future in enumerate(as_completed(futures)):
                    port = futures[future]
                    open_port = future.result()
                    if open_port is not None:
                        results[open_port] = True
                    else:
                        results[port] = False
                    self.progress.emit(i + 1, total)
            self.result_ready.emit(self.host, results)
        except Exception as e:
            self.error.emit(str(e))


class TracerouteWorker(QThread):
    """路由追踪工作线程"""
    hop_found = Signal(int, str, float)  # hop_num, ip, latency
    finished_signal = Signal(bool)  # success

    def __init__(self, host: str, max_hops: int = 30):
        super().__init__()
        self.host = host
        self.max_hops = max_hops

    def run(self):
        try:
            if platform.system() == "Windows":
                cmd = ["tracert", "-d", "-h", str(self.max_hops), self.host]
            else:
                cmd = ["traceroute", "-n", "-m", str(self.max_hops), self.host]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            output = result.stdout

            # 解析每一跳
            if platform.system() == "Windows":
                # Windows tracert 输出格式:
                #   1    <1 ms    <1 ms    <1 ms  192.168.1.1
                pattern = re.compile(
                    r"^\s*(\d+)\s+"
                    r"(?:<\d+\s+ms|\*\s*\*\s*\*|\d+\s+ms)\s+"
                    r"(?:<\d+\s+ms|\*\s*\*\s*\*|\d+\s+ms)\s+"
                    r"(?:<\d+\s+ms|\*\s*\*\s*\*|\d+\s+ms)\s+"
                    r"([\d.]+|超时请求|\*)",
                    re.MULTILINE
                )
                for match in pattern.finditer(output):
                    hop_num = int(match.group(1))
                    ip = match.group(2)
                    latency = 0.0
                    # 尝试提取延迟
                    lat_match = re.search(r"(\d+)\s*ms", match.group(0))
                    if lat_match:
                        latency = float(lat_match.group(1))
                    self.hop_found.emit(hop_num, ip, latency)
            else:
                # Linux traceroute 输出格式:
                # 1  192.168.1.1  0.543 ms  0.412 ms  0.398 ms
                pattern = re.compile(
                    r"^\s*(\d+)\s+([\d.]+)\s+([\d.]+)\s+ms",
                    re.MULTILINE
                )
                for match in pattern.finditer(output):
                    hop_num = int(match.group(1))
                    ip = match.group(2)
                    latency = float(match.group(3))
                    self.hop_found.emit(hop_num, ip, latency)

            self.finished_signal.emit(True)
        except Exception as e:
            self.hop_found.emit(0, str(e), -1.0)
            self.finished_signal.emit(False)


class ArpScanWorker(QThread):
    """ARP 扫描工作线程，检测IP冲突和局域网设备"""
    result_ready = Signal(list)  # [(ip, mac, interface)]

    def run(self):
        entries = []
        try:
            if platform.system() == "Windows":
                result = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=10)
                # Windows 格式:
                #   192.168.1.1   aa-bb-cc-dd-ee-ff   动态
                pattern = re.compile(
                    r"([\d.]+)\s+([\da-fA-F-]+)\s+(\S+)"
                )
                for match in pattern.finditer(result.stdout):
                    ip = match.group(1)
                    mac = match.group(2).replace("-", ":").upper()
                    iface = match.group(3)
                    entries.append((ip, mac, iface))
            else:
                result = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=10)
                # Linux 格式:
                #   ? (192.168.1.1) at aa:bb:cc:dd:ee:ff [ether] on eth0
                pattern = re.compile(
                    r"\(([\d.]+)\)\s+at\s+([\da-fA-F:]+)\s+\S+\s+on\s+(\S+)"
                )
                for match in pattern.finditer(result.stdout):
                    ip = match.group(1)
                    mac = match.group(2).upper()
                    iface = match.group(3)
                    entries.append((ip, mac, iface))

            # 检测 IP 冲突（同一IP出现多个MAC）
            ip_count: Dict[str, List[str]] = {}
            for ip, mac, iface in entries:
                if ip not in ip_count:
                    ip_count[ip] = []
                ip_count[ip].append(mac)

            conflict_ips = [ip for ip, macs in ip_count.items() if len(set(macs)) > 1]
            if conflict_ips:
                for ip in conflict_ips:
                    macs = ip_count[ip]
                    for mac in macs:
                        entries.append((ip, mac, "IP冲突!"))

        except Exception as e:
            entries.append(("ERROR", str(e), ""))

        self.result_ready.emit(entries)


class NetworkInterfaceWorker(QThread):
    """获取本地网卡信息工作线程"""
    result_ready = Signal(list)  # [(name, ip, netmask, status)]

    def run(self):
        interfaces = []
        try:
            import psutil
            stats = psutil.net_if_stats()
            addrs = psutil.net_if_addrs()

            for name, stat in stats.items():
                ip_addr = ""
                netmask = ""
                if name in addrs:
                    for addr in addrs[name]:
                        if addr.family == socket.AF_INET:
                            ip_addr = addr.address
                            netmask = addr.netmask
                            break
                interfaces.append((
                    name,
                    ip_addr,
                    netmask,
                    "UP" if stat.isup else "DOWN",
                    stat.speed,
                ))
        except ImportError:
            # 如果 psutil 不可用，使用系统命令
            try:
                if platform.system() == "Windows":
                    result = subprocess.run(
                        ["ipconfig"], capture_output=True, text=True, timeout=10
                    )
                    # 简单解析
                    current_name = ""
                    for line in result.stdout.split("\n"):
                        if "适配器" in line or "adapter" in line:
                            current_name = line.strip()
                        elif "IPv4" in line:
                            ip_match = re.search(r"([\d.]+)", line)
                            if ip_match:
                                interfaces.append((current_name, ip_match.group(1), "", "UP", 0))
            except Exception:
                pass

        self.result_ready.emit(interfaces)


def get_common_ports_description() -> Dict[int, str]:
    """返回常用端口及描述"""
    return {
        21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP",
        53: "DNS", 80: "HTTP", 110: "POP3", 143: "IMAP",
        443: "HTTPS", 445: "SMB", 993: "IMAPS", 995: "POP3S",
        1433: "MSSQL", 3306: "MySQL", 3389: "RDP", 5432: "PostgreSQL",
        5900: "VNC", 6379: "Redis", 8080: "HTTP-Alt", 8443: "HTTPS-Alt",
        9200: "Elasticsearch", 27017: "MongoDB",
    }


class DnsLookupWorker(QThread):
    """DNS 查询工作线程"""
    result_ready = Signal(str, list, str)  # host, records, error

    def __init__(self, host: str):
        super().__init__()
        self.host = host

    def run(self):
        records = []
        error = ""
        try:
            # A 记录
            addr_info = socket.getaddrinfo(self.host, None, socket.AF_INET)
            ips = set()
            for info in addr_info:
                ip = info[4][0]
                if ip not in ips:
                    ips.add(ip)
                    records.append(("A", ip))
        except Exception as e:
            error = str(e)

        try:
            # AAAA 记录
            addr_info6 = socket.getaddrinfo(self.host, None, socket.AF_INET6)
            ips6 = set()
            for info in addr_info6:
                ip = info[4][0]
                if ip not in ips6:
                    ips6.add(ip)
                    records.append(("AAAA", ip))
        except Exception:
            pass

        self.result_ready.emit(self.host, records, error)


class HttpCheckWorker(QThread):
    """HTTP/HTTPS 状态检测工作线程"""
    result_ready = Signal(str, int, str, str)  # url, status_code, headers, error

    def __init__(self, url: str, timeout: int = 10):
        super().__init__()
        self.url = url
        self.timeout = timeout

    def run(self):
        try:
            import urllib.request
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(
                self.url,
                headers={"User-Agent": "AiinLink/1.0"},
                method="HEAD"
            )
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                status = resp.status
                headers = dict(resp.headers)
                header_text = "\n".join(f"{k}: {v}" for k, v in headers.items())
                self.result_ready.emit(self.url, status, header_text, "")
        except Exception as e:
            self.result_ready.emit(self.url, 0, "", str(e))


class WhoisWorker(QThread):
    """WHOIS 查询工作线程"""
    result_ready = Signal(str, str, str)  # domain, output, error

    def __init__(self, domain: str):
        super().__init__()
        self.domain = domain

    def run(self):
        try:
            if platform.system() == "Windows":
                # Windows 通常没有 whois 命令，使用 socket 查询 whois.iana.org 或 whois.cnnic.cn
                result = self._whois_socket(self.domain)
            else:
                result = subprocess.run(
                    ["whois", self.domain],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode == 0:
                    output = result.stdout
                else:
                    output = result.stderr or result.stdout
                    if not output.strip():
                        output = self._whois_socket(self.domain)
            self.result_ready.emit(self.domain, output, "")
        except FileNotFoundError:
            output = self._whois_socket(self.domain)
            self.result_ready.emit(self.domain, output, "")
        except Exception as e:
            self.result_ready.emit(self.domain, "", str(e))

    def _whois_socket(self, domain: str) -> str:
        """通过 socket 查询 whois"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(10)
            s.connect(("whois.iana.org", 43))
            s.sendall((domain + "\r\n").encode())
            data = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
            s.close()
            return data.decode("utf-8", errors="replace")
        except Exception as e:
            return f"WHOIS 查询失败: {e}"


class SSLCheckerWorker(QThread):
    """SSL/TLS 证书检测工作线程"""
    result_ready = Signal(str, dict, str)  # host, cert_info, error

    def __init__(self, host: str, port: int = 443):
        super().__init__()
        self.host = host
        self.port = port

    def run(self):
        try:
            from app.security_tools import get_ssl_certificate
            cert = get_ssl_certificate(self.host, self.port)
            self.result_ready.emit(self.host, cert.to_dict(), "")
        except Exception as e:
            self.result_ready.emit(self.host, {}, str(e))


class GeoLocationWorker(QThread):
    """IP 地理位置查询工作线程"""
    result_ready = Signal(str, dict, str)  # ip, location_info, error

    def __init__(self, ip: str):
        super().__init__()
        self.ip = ip

    def run(self):
        try:
            from app.security_tools import get_ip_geolocation
            result = get_ip_geolocation(self.ip)
            self.result_ready.emit(self.ip, result, "")
        except Exception as e:
            self.result_ready.emit(self.ip, {}, str(e))


class VulnerablePortScanWorker(QThread):
    """危险端口扫描工作线程"""
    progress = Signal(int, int)  # current, total
    result_ready = Signal(str, list, str)  # host, results, error

    def __init__(self, host: str):
        super().__init__()
        self.host = host

    def run(self):
        try:
            from app.security_tools import scan_vulnerable_ports
            results = scan_vulnerable_ports(self.host)
            self.result_ready.emit(self.host, results, "")
        except Exception as e:
            self.result_ready.emit(self.host, [], str(e))


class ServiceIdentifyWorker(QThread):
    """服务识别工作线程"""
    progress = Signal(int, int)  # current, total
    result_ready = Signal(str, list, str)  # host, results, error

    def __init__(self, host: str, ports: List[int] = None):
        super().__init__()
        self.host = host
        self.ports = ports or [21, 22, 23, 25, 53, 80, 110, 143, 443, 445,
                               993, 995, 1433, 3306, 3389, 5432, 5900, 6379,
                               8080, 8443, 9200, 27017]

    def run(self):
        results = []
        try:
            from app.security_tools import get_service_banner, identify_service_by_port, is_port_open
            
            total = len(self.ports)
            for i, port in enumerate(self.ports):
                if is_port_open(self.host, port, timeout=1.0):
                    banner = get_service_banner(self.host, port)
                    service = identify_service_by_port(port, banner)
                    results.append((port, service, banner))
                self.progress.emit(i + 1, total)
            
            self.result_ready.emit(self.host, results, "")
        except Exception as e:
            self.result_ready.emit(self.host, results, str(e))


class SecurityHeadersWorker(QThread):
    """HTTP 安全头分析工作线程"""
    result_ready = Signal(str, dict, str)  # url, headers_info, error

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            from app.security_tools import analyze_http_security_headers
            results = analyze_http_security_headers(self.url)
            self.result_ready.emit(self.url, results, "")
        except Exception as e:
            self.result_ready.emit(self.url, {}, str(e))


class PasswordStrengthWorker(QThread):
    """密码强度检测工作线程"""
    result_ready = Signal(str, int, str, list)  # password, score, level, suggestions

    def __init__(self, password: str):
        super().__init__()
        self.password = password

    def run(self):
        try:
            from app.security_tools import check_password_strength
            score, level, suggestions = check_password_strength(self.password)
            self.result_ready.emit(self.password, score, level, suggestions)
        except Exception as e:
            self.result_ready.emit(self.password, 0, "错误", [str(e)])


class PasswordGeneratorWorker(QThread):
    """密码生成工作线程"""
    result_ready = Signal(str)  # password

    def __init__(self, length: int = 16, include_special: bool = True):
        super().__init__()
        self.length = length
        self.include_special = include_special

    def run(self):
        try:
            from app.security_tools import generate_password
            password = generate_password(self.length, self.include_special)
            self.result_ready.emit(password)
        except Exception:
            self.result_ready.emit("")


# ================================================
# 渗透测试工作线程
# ================================================

class SQLInjectionDetectWorker(QThread):
    """SQL注入检测工作线程"""
    result_ready = Signal(str, list, str)  # url, results, error
    progress = Signal(int, int)  # current, total

    def __init__(self, url: str, param_name: str):
        super().__init__()
        self.url = url
        self.param_name = param_name

    def run(self):
        try:
            from app.security_tools import detect_sql_injection
            results = detect_sql_injection(self.url, self.param_name)
            self.result_ready.emit(self.url, results, "")
        except Exception as e:
            self.result_ready.emit(self.url, [], str(e))


class XSSDetectWorker(QThread):
    """XSS检测工作线程"""
    result_ready = Signal(str, list, str)  # url, results, error

    def __init__(self, url: str, param_name: str):
        super().__init__()
        self.url = url
        self.param_name = param_name

    def run(self):
        try:
            from app.security_tools import detect_xss
            results = detect_xss(self.url, self.param_name)
            self.result_ready.emit(self.url, results, "")
        except Exception as e:
            self.result_ready.emit(self.url, [], str(e))


class DirectoryBusterWorker(QThread):
    """目录爆破工作线程"""
    result_ready = Signal(str, list, str)  # url, results, error
    progress = Signal(int, int)  # current, total

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            from app.security_tools import directory_buster, COMMON_PATHS
            results = directory_buster(self.url, COMMON_PATHS)
            self.result_ready.emit(self.url, results, "")
        except Exception as e:
            self.result_ready.emit(self.url, [], str(e))


class SubdomainEnumerationWorker(QThread):
    """子域名枚举工作线程"""
    result_ready = Signal(str, list, str)  # domain, results, error

    def __init__(self, domain: str):
        super().__init__()
        self.domain = domain

    def run(self):
        try:
            from app.security_tools import subdomain_enumeration, COMMON_SUBDOMAINS
            results = subdomain_enumeration(self.domain, COMMON_SUBDOMAINS)
            self.result_ready.emit(self.domain, results, "")
        except Exception as e:
            self.result_ready.emit(self.domain, [], str(e))


# ================================================
# 压力测试工作线程
# ================================================

class HttpLoadTestWorker(QThread):
    """HTTP压力测试工作线程"""
    result_ready = Signal(str, dict, str)  # url, results, error

    def __init__(self, url: str, requests: int, concurrent: int = 10):
        super().__init__()
        self.url = url
        self.requests = requests
        self.concurrent = concurrent

    def run(self):
        try:
            from app.security_tools import http_load_test
            results = http_load_test(self.url, self.requests, self.concurrent)
            self.result_ready.emit(self.url, results, "")
        except Exception as e:
            self.result_ready.emit(self.url, {}, str(e))


class TCPFloodTestWorker(QThread):
    """TCP洪水测试工作线程"""
    result_ready = Signal(str, int, dict, str)  # host, port, results, error

    def __init__(self, host: str, port: int, duration: int = 10):
        super().__init__()
        self.host = host
        self.port = port
        self.duration = duration

    def run(self):
        try:
            from app.security_tools import tcp_flood_test
            results = tcp_flood_test(self.host, self.port, self.duration)
            self.result_ready.emit(self.host, self.port, results, "")
        except Exception as e:
            self.result_ready.emit(self.host, self.port, {}, str(e))


# ================================================
# 服务器测试工作线程
# ================================================

class FTPAnonymousWorker(QThread):
    """FTP匿名登录检测工作线程"""
    result_ready = Signal(str, dict, str)  # host, result, error

    def __init__(self, host: str, port: int = 21):
        super().__init__()
        self.host = host
        self.port = port

    def run(self):
        try:
            from app.security_tools import check_ftp_anonymous
            result = check_ftp_anonymous(self.host, self.port)
            self.result_ready.emit(self.host, result, "")
        except Exception as e:
            self.result_ready.emit(self.host, {}, str(e))


class SMBEnumerationWorker(QThread):
    """SMB服务枚举工作线程"""
    result_ready = Signal(str, list, str)  # host, results, error

    def __init__(self, host: str):
        super().__init__()
        self.host = host

    def run(self):
        try:
            from app.security_tools import smb_enumeration
            results = smb_enumeration(self.host)
            self.result_ready.emit(self.host, results, "")
        except Exception as e:
            self.result_ready.emit(self.host, [], str(e))


class SSHWeakPasswordWorker(QThread):
    """SSH弱密码检测工作线程"""
    result_ready = Signal(str, dict, str)  # host, result, error

    def __init__(self, host: str, port: int = 22, username: str = "root"):
        super().__init__()
        self.host = host
        self.port = port
        self.username = username

    def run(self):
        try:
            from app.security_tools import check_ssh_weak_password
            result = check_ssh_weak_password(self.host, self.port, self.username)
            self.result_ready.emit(self.host, result, "")
        except Exception as e:
            self.result_ready.emit(self.host, {}, str(e))


class BannerGrabWorker(QThread):
    """服务横幅获取工作线程"""
    result_ready = Signal(str, int, dict, str)  # host, port, result, error

    def __init__(self, host: str, port: int):
        super().__init__()
        self.host = host
        self.port = port

    def run(self):
        try:
            from app.security_tools import grab_banner
            result = grab_banner(self.host, self.port)
            self.result_ready.emit(self.host, self.port, result, "")
        except Exception as e:
            self.result_ready.emit(self.host, self.port, {}, str(e))


class ServerInfoWorker(QThread):
    """服务器信息收集工作线程"""
    result_ready = Signal(str, dict, str)  # host, info, error

    def __init__(self, host: str):
        super().__init__()
        self.host = host

    def run(self):
        try:
            from app.security_tools import collect_server_info
            result = collect_server_info(self.host)
            self.result_ready.emit(self.host, result, "")
        except Exception as e:
            self.result_ready.emit(self.host, {}, str(e))


class PortEnumerationWorker(QThread):
    """端口枚举工作线程"""
    result_ready = Signal(str, list, str)  # host, results, error

    def __init__(self, host: str, start_port: int = 1, end_port: int = 1000):
        super().__init__()
        self.host = host
        self.start_port = start_port
        self.end_port = end_port

    def run(self):
        try:
            from app.security_tools import enumerate_open_ports
            results = enumerate_open_ports(self.host, self.start_port, self.end_port)
            self.result_ready.emit(self.host, results, "")
        except Exception as e:
            self.result_ready.emit(self.host, [], str(e))


# ================================================
# 插件管理工作线程
# ================================================

class PluginDownloadWorker(QThread):
    """插件下载工作线程"""
    result_ready = Signal(bool, str)  # success, message

    def __init__(self, repo_url: str, plugin_name: str):
        super().__init__()
        self.repo_url = repo_url
        self.plugin_name = plugin_name

    def run(self):
        try:
            from app.security_tools import download_plugin_from_github
            success = download_plugin_from_github(self.repo_url, self.plugin_name)
            if success:
                self.result_ready.emit(True, f"插件 {self.plugin_name} 下载成功")
            else:
                self.result_ready.emit(False, f"插件 {self.plugin_name} 下载失败")
        except Exception as e:
            self.result_ready.emit(False, str(e))


# =====================================================================
# 以下为新增的检测 Worker（更丰富的检测内容和更深入的分析）
# =====================================================================

class TCPPingWorker(QThread):
    """TCP Ping - 通过 TCP 握手测试连通性（当 ICMP 被防火墙拦截时使用）"""
    result_ready = Signal(str, int, float, str)  # host, port, latency_ms, status

    def __init__(self, host: str, ports: List[int] = None, timeout: float = 3.0):
        super().__init__()
        self.host = host
        self.ports = ports or [80, 443, 22, 21, 3389, 8080]
        self.timeout = timeout

    def run(self):
        import time as _t
        for port in self.ports:
            sock = None
            start = _t.time()
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.timeout)
                result = sock.connect_ex((self.host, port))
                latency = (_t.time() - start) * 1000.0
                if result == 0:
                    self.result_ready.emit(self.host, port, latency, "open")
                else:
                    self.result_ready.emit(self.host, port, -1, "closed/filtered")
            except socket.timeout:
                self.result_ready.emit(self.host, port, -1, "timeout")
            except Exception as e:
                self.result_ready.emit(self.host, port, -1, f"err:{e}")
            finally:
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass


class HTTPResponseHeadersWorker(QThread):
    """HTTP 响应头详细信息检测"""
    result_ready = Signal(str, dict, str)  # url, headers, error

    def __init__(self, url: str, method: str = "GET", timeout: float = 8.0,
                 follow_redirects: bool = True):
        super().__init__()
        self.url = url
        self.method = method.upper()
        self.timeout = timeout
        self.follow_redirects = follow_redirects

    def run(self):
        try:
            import urllib.request
            import urllib.error
            req = urllib.request.Request(self.url, method=self.method)
            req.add_header("User-Agent", "AiinLink-Probe/1.0")
            # 自定义：不跟随重定向
            class _NoRedirect(urllib.request.HTTPRedirectHandler):
                def http_error_302(_s, *a, **k): return None
                http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302

            if self.follow_redirects:
                opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
            else:
                opener = urllib.request.build_opener(_NoRedirect())
            with opener.open(req, timeout=self.timeout) as resp:
                # 收集响应头
                headers = {k: v for k, v in resp.headers.items()}
                headers["__status__"] = str(resp.status)
                headers["__reason__"] = resp.reason
                self.result_ready.emit(self.url, headers, "")
        except urllib.error.HTTPError as e:
            headers = {k: v for k, v in (e.headers.items() if e.headers else [])}
            headers["__status__"] = str(e.code)
            headers["__reason__"] = e.reason or ""
            self.result_ready.emit(self.url, headers, f"HTTP {e.code}")
        except Exception as e:
            self.result_ready.emit(self.url, {}, str(e))


class DNSRecordsWorker(QThread):
    """扩展 DNS 记录查询（A / AAAA / MX / NS / TXT / CNAME / SOA / SRV）"""
    result_ready = Signal(str, list, str)  # host, records, error

    # 常见服务记录
    SRV_SERVICES = [
        ("_sip._tcp", "SIP"),
        ("_sip._udp", "SIP"),
        ("_xmpp-client._tcp", "XMPP"),
        ("_xmpp-server._tcp", "XMPP"),
        ("_ldap._tcp", "LDAP"),
        ("_kerberos._tcp", "Kerberos"),
        ("_caldav._tcp", "CalDAV"),
        ("_carddav._tcp", "CardDAV"),
    ]

    def __init__(self, host: str, include_srv: bool = False, timeout: float = 4.0):
        super().__init__()
        self.host = host
        self.include_srv = include_srv
        self.timeout = timeout

    def run(self):
        records: list = []
        error = ""
        # 1) A 记录
        try:
            infos = socket.getaddrinfo(self.host, None, socket.AF_INET)
            ips = set()
            for info in infos:
                ip = info[4][0]
                if ip not in ips:
                    ips.add(ip)
                    records.append(("A", ip))
        except Exception as e:
            error = f"A:{e} "
        # 2) AAAA 记录
        try:
            infos6 = socket.getaddrinfo(self.host, None, socket.AF_INET6)
            ips6 = set()
            for info in infos6:
                ip = info[4][0]
                if ip not in ips6:
                    ips6.add(ip)
                    records.append(("AAAA", ip))
        except Exception:
            pass
        # 3) MX / NS / TXT / SOA / CNAME: 尝试使用系统 nslookup/dig
        if hasattr(subprocess, "run"):
            binary = None
            for cand in ("dig", "nslookup", "host"):
                try:
                    r = subprocess.run([cand, "--version"],
                                       capture_output=True, timeout=1)
                    if r.returncode == 0 or cand == "nslookup":
                        binary = cand
                        break
                except Exception:
                    continue
            if binary is None:
                # Windows 自带 nslookup
                import platform as _pf
                if _pf.system() == "Windows":
                    binary = "nslookup"

            if binary == "nslookup":
                # 简化的 nslookup 调用
                for rtype in ("MX", "NS", "TXT", "CNAME", "SOA"):
                    try:
                        r = subprocess.run(
                            ["nslookup", "-type=" + rtype, self.host],
                            capture_output=True, text=True, timeout=self.timeout
                        )
                        if r.returncode == 0:
                            out = r.stdout
                            if rtype == "MX":
                                for line in out.splitlines():
                                    m = re.search(
                                        r"mail exchanger\s*=\s*(\S+)", line, re.I)
                                    if m:
                                        pref_m = re.search(
                                            r"preference\s*=\s*(\d+)", line)
                                        pref = pref_m.group(1) if pref_m else "10"
                                        records.append((f"{rtype}({pref})", m.group(1)))
                            elif rtype == "NS":
                                for line in out.splitlines():
                                    if "nameserver" in line.lower():
                                        parts = line.split("=")
                                        if len(parts) >= 2:
                                            ns = parts[-1].strip()
                                            if ns and ns != self.host:
                                                records.append((rtype, ns))
                            elif rtype == "TXT":
                                txt_chunks = []
                                for line in out.splitlines():
                                    line = line.strip()
                                    if line.startswith('"') and line.endswith('"'):
                                        txt_chunks.append(line.strip('"'))
                                    elif "text =" in line.lower():
                                        txt_chunks.append(line.split("=", 1)[1].strip())
                                if txt_chunks:
                                    records.append(
                                        (rtype, " | ".join(txt_chunks)[:200]))
                            elif rtype == "CNAME":
                                m = re.search(r"canonical name\s*=\s*(\S+)", out, re.I)
                                if m:
                                    records.append((rtype, m.group(1)))
                            elif rtype == "SOA":
                                m = re.search(
                                    r"origin\s*=\s*(\S+)", out, re.I)
                                if m:
                                    records.append((rtype, m.group(1)))
                    except Exception:
                        pass
            elif binary == "dig":
                for rtype in ("MX", "NS", "TXT", "CNAME", "SOA"):
                    try:
                        r = subprocess.run(
                            ["dig", "+short", "+time=2", self.host, rtype],
                            capture_output=True, text=True, timeout=self.timeout
                        )
                        for line in r.stdout.splitlines():
                            line = line.strip()
                            if line:
                                records.append((rtype, line[:200]))
                    except Exception:
                        pass
        # 4) SRV
        if self.include_srv:
            import platform as _pf
            binary = "nslookup" if _pf.system() == "Windows" else "dig"
            for prefix, name in self.SRV_SERVICES:
                target = f"{prefix}.{self.host}"
                try:
                    if binary == "nslookup":
                        r = subprocess.run(
                            ["nslookup", "-type=SRV", target],
                            capture_output=True, text=True, timeout=self.timeout)
                        m = re.search(r"host\s*=\s*(\S+)", r.stdout)
                        p_m = re.search(r"port\s*=\s*(\d+)", r.stdout)
                        if m:
                            records.append(
                                (f"SRV-{name}", f"{m.group(1)}:{p_m.group(1) if p_m else '?'}"))
                    else:
                        r = subprocess.run(
                            ["dig", "+short", "SRV", target],
                            capture_output=True, text=True, timeout=self.timeout)
                        for line in r.stdout.splitlines():
                            if line.strip():
                                parts = line.split()
                                if len(parts) >= 4:
                                    rec = f"{parts[3]}:{parts[2]}"
                                    records.append((f"SRV-{name}", rec))
                except Exception:
                    pass
        self.result_ready.emit(self.host, records, error.strip())


class IPv6SupportWorker(QThread):
    """IPv6 连通性检测"""
    result_ready = Signal(str, bool, str, str)  # host, has_ipv6, ipv6_addr, error

    def __init__(self, host: str, timeout: float = 4.0):
        super().__init__()
        self.host = host
        self.timeout = timeout

    def run(self):
        try:
            infos = socket.getaddrinfo(self.host, None, socket.AF_INET6)
            if infos:
                self.result_ready.emit(self.host, True, infos[0][4][0], "")
            else:
                self.result_ready.emit(self.host, False, "", "无 AAAA 记录")
        except socket.gaierror as e:
            self.result_ready.emit(self.host, False, "", str(e))
        except Exception as e:
            self.result_ready.emit(self.host, False, "", str(e))


class MailServerWorker(QThread):
    """邮件服务器检测（SMTP/POP3/IMAP）"""
    result_ready = Signal(str, dict)  # host, {protocol: {banner, supports_tls, capabilities}}

    def __init__(self, host: str, timeout: float = 5.0):
        super().__init__()
        self.host = host
        self.timeout = timeout

    def _probe(self, port: int, banner_cmd: bytes = b"") -> dict:
        sock = None
        info: dict = {"port": port, "reachable": False, "banner": "", "starttls": False}
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((self.host, port))
            info["reachable"] = True
            # 接收 banner
            sock.settimeout(2.0)
            try:
                banner = sock.recv(1024).decode("utf-8", errors="ignore").strip()
                info["banner"] = banner[:200]
            except socket.timeout:
                pass
            # 发送命令（如 EHLO）
            if banner_cmd:
                try:
                    sock.send(banner_cmd)
                    sock.settimeout(2.0)
                    resp = sock.recv(4096).decode("utf-8", errors="ignore")
                    if "STARTTLS" in resp.upper():
                        info["starttls"] = True
                except Exception:
                    pass
        except Exception as e:
            info["error"] = str(e)
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
        return info

    def run(self):
        results: dict = {}
        results["SMTP(25)"] = self._probe(25, b"EHLO test\r\n")
        results["SMTP-Sub(587)"] = self._probe(587, b"EHLO test\r\n")
        results["SMTPS(465)"] = self._probe(465)
        results["POP3(110)"] = self._probe(110)
        results["POP3S(995)"] = self._probe(995)
        results["IMAP(143)"] = self._probe(143)
        results["IMAPS(993)"] = self._probe(993)
        self.result_ready.emit(self.host, results)


class CORSWorker(QThread):
    """CORS 配置错误检测"""
    result_ready = Signal(str, dict, str)  # url, cors_info, error

    def __init__(self, url: str, timeout: float = 8.0):
        super().__init__()
        self.url = url
        self.timeout = timeout

    def run(self):
        import urllib.request
        info: dict = {
            "vulnerabilities": [],
            "headers": {},
        }
        try:
            # 测试 1: 普通请求
            req = urllib.request.Request(self.url, method="GET")
            req.add_header("User-Agent", "AiinLink-CORS/1.0")
            req.add_header("Origin", "https://evil.example.com")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                acao = resp.headers.get("Access-Control-Allow-Origin", "")
                acac = resp.headers.get("Access-Control-Allow-Credentials", "")
                info["headers"]["Access-Control-Allow-Origin"] = acao
                info["headers"]["Access-Control-Allow-Credentials"] = acac
                if acao == "*":
                    info["vulnerabilities"].append("ACAO 设置为通配符 *，任何源都可访问")
                if acao and acao != "null":
                    # 反射 Origin：检查是否原样返回
                    if "evil.example.com" in acao:
                        info["vulnerabilities"].append(
                            f"Origin 被反射回响应头 ({acao})，可能存在 CORS 绕过")
                    if acac.lower() == "true" and (acao == "*" or "evil" in acao):
                        info["vulnerabilities"].append(
                            "Access-Control-Allow-Credentials: true 与反射 Origin 结合，"
                            "允许跨域携带凭据")
            # 测试 2: 预检 OPTIONS
            try:
                req2 = urllib.request.Request(self.url, method="OPTIONS")
                req2.add_header("User-Agent", "AiinLink-CORS/1.0")
                req2.add_header("Origin", "https://evil.example.com")
                req2.add_header("Access-Control-Request-Method", "POST")
                req2.add_header("Access-Control-Request-Headers", "X-Test")
                with urllib.request.urlopen(req2, timeout=self.timeout) as resp2:
                    methods = resp2.headers.get("Access-Control-Allow-Methods", "")
                    headers_allow = resp2.headers.get("Access-Control-Allow-Headers", "")
                    info["headers"]["Access-Control-Allow-Methods"] = methods
                    info["headers"]["Access-Control-Allow-Headers"] = headers_allow
                    if "*" in methods or "*" in headers_allow:
                        info["vulnerabilities"].append(
                            f"预检响应允许所有方法/头: methods={methods}, headers={headers_allow}")
            except Exception as e:
                info["preflight_error"] = str(e)
            self.result_ready.emit(self.url, info, "")
        except Exception as e:
            self.result_ready.emit(self.url, info, str(e))


class CDNWAFWorker(QThread):
    """CDN / WAF 检测"""
    # 常见 CDN/WAF 特征
    CDN_HEADERS = {
        "CF-Ray": "Cloudflare",
        "CF-Cache-Status": "Cloudflare",
        "X-CDN": "Generic CDN",
        "X-Cache": "Varnish/Squid CDN",
        "X-Served-By": "Fastly",
        "X-Amz-Cf-Id": "Amazon CloudFront",
        "X-Amz-Cf-Pop": "Amazon CloudFront",
        "X-Edge-Location": "Akamai",
        "X-Akamai-Request-ID": "Akamai",
        "X-Forwarded-For": "Proxy/CDN",
        "Via": "Proxy/CDN",
        "X-CDN-Provider": "Generic",
        "X-CCDN": "Generic",
        "Server-Timing": "Generic",
        "X-Worker-Region": "Cloudflare Worker",
        "X-Country-Code": "CDN Geo",
        "X-Request-ID": "Generic",
        "X-Content-Type-Options": "Security",
        "X-Frame-Options": "Security",
    }
    WAF_BODY_PATTERNS = [
        (r"cloudflare", "Cloudflare"),
        (r"incapsula", "Imperva Incapsula"),
        (r"imperva", "Imperva"),
        (r"akamai", "Akamai"),
        (r"aws.*waf", "AWS WAF"),
        (r"f5[-\s]*big[-\s]*ip", "F5 BIG-IP"),
        (r"barracuda", "Barracuda"),
        (r"forti(web|gate)", "Fortinet"),
        (r"sucuri", "Sucuri"),
        (r"wordfence", "Wordfence"),
        (r"<title>.*attention required.*</title>", "Generic WAF"),
    ]

    def __init__(self, host: str, port: int = 443, use_https: bool = True,
                 timeout: float = 6.0):
        super().__init__()
        self.host = host
        self.port = port
        self.use_https = use_https
        self.timeout = timeout

    def run(self):
        import urllib.request
        import ssl
        result: dict = {
            "cdn": [],
            "waf": [],
            "headers_matched": [],
            "ip": "",
            "asn": "",
            "geo_hint": "",
        }
        try:
            url = (f"{'https' if self.use_https else 'http'}://"
                   f"{self.host}:{self.port}/")
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "Mozilla/5.0 (compatible; AiinLink-CDNDetect/1.0)")
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                hdrs = {k: v for k, v in resp.headers.items()}
                body_sample = ""
                try:
                    body_sample = resp.read(8192).decode("utf-8", errors="ignore")
                except Exception:
                    pass
                for hk, hv in hdrs.items():
                    for marker, name in self.CDN_HEADERS.items():
                        if hk.lower() == marker.lower():
                            result["headers_matched"].append(f"{hk}: {hv}  -> {name}")
                            if name not in result["cdn"]:
                                result["cdn"].append(name)
                for pat, name in self.WAF_BODY_PATTERNS:
                    if re.search(pat, body_sample, re.I):
                        if name not in result["waf"]:
                            result["waf"].append(name)
                # 一些特殊状态码也提示
                if resp.status in (403, 429, 503):
                    result["waf"].append(
                        f"HTTP {resp.status} (可能存在 WAF 拦截)")
            # 解析 IP
            try:
                result["ip"] = socket.gethostbyname(self.host)
            except Exception:
                pass
            self.result_ready.emit(self.host, result, "")
        except Exception as e:
            self.result_ready.emit(self.host, result, str(e))


class WebSocketWorker(QThread):
    """WebSocket 握手测试"""
    result_ready = Signal(str, dict, str)  # url, info, error

    def __init__(self, url: str, timeout: float = 6.0):
        super().__init__()
        self.url = url
        self.timeout = timeout

    def run(self):
        import urllib.request
        import base64
        import os as _os
        import hashlib
        info: dict = {}
        try:
            # 生成随机 Sec-WebSocket-Key
            key = base64.b64encode(_os.urandom(16)).decode()
            req = urllib.request.Request(self.url, method="GET")
            req.add_header("Upgrade", "websocket")
            req.add_header("Connection", "Upgrade")
            req.add_header("Sec-WebSocket-Key", key)
            req.add_header("Sec-WebSocket-Version", "13")
            req.add_header("User-Agent", "AiinLink-WSProbe/1.0")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status = resp.status
                accept = resp.headers.get("Sec-WebSocket-Accept", "")
                # 验证 Accept
                expected = base64.b64encode(
                    hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
                                 .encode()).digest()).decode()
                info["status"] = status
                info["Sec-WebSocket-Accept"] = accept
                info["accept_match"] = (accept == expected)
                info["headers"] = {k: v for k, v in resp.headers.items()}
                if status == 101:
                    info["status_text"] = "101 Switching Protocols (握手成功)"
                else:
                    info["status_text"] = f"{status} (非 101，可能未升级)"
                self.result_ready.emit(self.url, info, "")
        except urllib.error.HTTPError as e:
            info["status"] = e.code
            info["status_text"] = f"HTTP {e.code} {e.reason}"
            self.result_ready.emit(self.url, info, f"HTTP {e.code}")
        except Exception as e:
            self.result_ready.emit(self.url, info, str(e))


class PublicIPWorker(QThread):
    """公网 IP 检测"""
    result_ready = Signal(str, str, str)  # service, ip, error

    SERVICES = [
        ("api.ipify.org", "https://api.ipify.org"),
        ("ifconfig.me", "https://ifconfig.me/ip"),
        ("icanhazip.com", "https://icanhazip.com"),
        ("ip.sb", "https://ip.sb"),
    ]

    def __init__(self, timeout: float = 5.0):
        super().__init__()
        self.timeout = timeout

    def run(self):
        import urllib.request
        import ssl
        ctx = ssl.create_default_context()
        for name, url in self.SERVICES:
            try:
                req = urllib.request.Request(url)
                req.add_header("User-Agent", "curl/8.0")
                with urllib.request.urlopen(req, timeout=self.timeout,
                                            context=ctx) as resp:
                    ip = resp.read().decode("utf-8", errors="ignore").strip()
                    if re.match(r"^[\d.:a-fA-F]+$", ip):
                        self.result_ready.emit(name, ip, "")
                        return
            except Exception as e:
                self.result_ready.emit(name, "", str(e))
        # 所有服务都失败时再用 socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(2)
            try:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                self.result_ready.emit("local", ip, "")
            finally:
                s.close()
        except Exception as e:
            self.result_ready.emit("local", "", str(e))


class MACVendorWorker(QThread):
    """MAC 地址厂商查询 (OUI 前 3 字节)"""
    # 简化版 OUI 数据库（常见厂商），生产环境建议使用完整 IEEE 数据库
    OUI_DATABASE = {
        "00:1A:2B": "Ayecom Technology",
        "00:50:56": "VMware",
        "00:0C:29": "VMware",
        "00:05:69": "VMware",
        "00:1C:14": "VMware",
        "00:1D:0F": "Pace Micro Technology",
        "00:1E:58": "D-Link Corporation",
        "00:1F:33": "Belkin",
        "00:1B:2F": "Broadcom",
        "00:24:01": "D-Link",
        "00:26:5A": "D-Link",
        "00:50:F2": "Microsoft",
        "3C:D9:2B": "HP",
        "00:23:7D": "Hewlett Packard",
        "00:1E:0B": "Hewlett Packard",
        "00:21:5A": "Hewlett Packard",
        "00:22:64": "Hewlett Packard",
        "B4:B5:2F": "Hewlett Packard",
        "F4:CE:46": "Hewlett Packard",
        "00:1A:A0": "Dell",
        "00:1D:09": "Dell",
        "00:1E:C9": "Dell",
        "00:25:64": "Dell",
        "B0:83:FE": "Dell",
        "B8:2A:72": "Dell",
        "00:18:71": "Dell",
        "00:19:B9": "Dell",
        "00:1C:23": "Dell",
        "00:22:19": "Dell",
        "EC:F4:BB": "Dell",
        "00:1D:72": "Wistron",
        "00:1F:29": "Hewlett Packard",
        "E4:11:5B": "Hewlett Packard",
        "00:18:F3": "Asustek",
        "AC:22:0B": "Asustek",
        "F0:2F:A8": "Apple",
        "3C:07:54": "Apple",
        "A8:5C:2C": "Apple",
        "AC:CF:5C": "Apple",
        "8C:85:90": "Apple",
        "70:CD:60": "Apple",
        "60:33:4B": "Apple",
        "A4:5E:60": "Apple",
        "C8:69:CD": "Apple",
        "DC:9B:9C": "Apple",
        "00:19:E3": "Apple",
        "00:1F:F3": "Apple",
        "00:23:6C": "Apple",
        "00:25:4B": "Apple",
        "00:26:BB": "Apple",
        "04:0C:CE": "Apple",
        "04:15:52": "Apple",
        "04:1E:64": "Apple",
        "04:26:65": "Apple",
        "10:DD:B1": "Apple",
        "20:78:F0": "Apple",
        "24:A2:E1": "Apple",
        "28:CF:DA": "Apple",
        "34:36:3B": "Apple",
        "3C:AB:8E": "Apple",
        "40:6C:8F": "Apple",
        "44:00:10": "Apple",
        "48:60:BC": "Apple",
        "50:7A:55": "Apple",
        "5C:97:F3": "Apple",
        "60:C5:47": "Apple",
        "64:B9:E8": "Apple",
        "68:9C:70": "Apple",
        "6C:40:08": "Apple",
        "70:73:CB": "Apple",
        "74:E1:B6": "Apple",
        "78:31:C1": "Apple",
        "7C:11:BE": "Apple",
        "84:38:35": "Apple",
        "88:1F:A1": "Apple",
        "8C:7C:92": "Apple",
        "90:27:E4": "Apple",
        "98:01:A7": "Apple",
        "9C:04:EB": "Apple",
        "A4:B1:97": "Apple",
        "AC:DE:48": "Apple",
        "B4:F0:AB": "Apple",
        "B8:17:C2": "Apple",
        "B8:78:2E": "Apple",
        "C8:1E:E7": "Apple",
        "C8:6F:1D": "Apple",
        "D0:23:DB": "Apple",
        "D4:9A:20": "Apple",
        "DC:2B:61": "Apple",
        "E0:B9:BA": "Apple",
        "E4:8B:7F": "Apple",
        "E4:C6:3D": "Apple",
        "E4:CE:8F": "Apple",
        "EC:35:86": "Apple",
        "F0:B4:79": "Apple",
        "F4:0F:24": "Apple",
        "F4:5C:89": "Apple",
        "F4:F1:5A": "Apple",
        "F4:F9:51": "Apple",
        "F8:1E:DF": "Apple",
        "FC:25:3F": "Apple",
        "00:15:5D": "Microsoft Hyper-V",
        "00:03:FF": "Microsoft Hyper-V",
        "00:0D:3A": "Microsoft",
        "00:12:5A": "Microsoft",
        "00:17:F2": "Microsoft",
        "00:1D:D8": "Microsoft",
        "00:22:48": "Microsoft",
        "00:25:AE": "Microsoft",
        "7C:1E:52": "Microsoft",
        "7C:ED:8D": "Microsoft",
        "98:5F:D3": "Microsoft",
        "B8:31:B5": "Microsoft",
        "BC:83:85": "Microsoft",
        "E4:F0:42": "Google",
        "F4:F5:E8": "Google",
        "F8:8F:CA": "Google",
        "00:1A:11": "Google",
        "3C:5A:B4": "Google",
        "6C:AD:F8": "Google",
        "A4:77:33": "Google",
        "DA:A1:19": "Google",
        "F4:F5:D8": "Google",
        "00:04:4B": "Nvidia",
        "00:1B:DE": "Nvidia",
        "00:25:90": "Super Micro",
        "AC:1F:6B": "Super Micro",
    }

    def __init__(self, mac: str):
        super().__init__()
        self.mac = mac

    @staticmethod
    def _normalize(mac: str) -> str:
        """统一为 XX:XX:XX 形式"""
        m = re.sub(r"[^0-9A-Fa-f]", "", mac)
        if len(m) < 6:
            return mac.upper()
        return ":".join(m[i:i + 2] for i in range(0, 6, 2)).upper()

    def run(self):
        norm = self._normalize(self.mac)
        oui = norm[:8]
        vendor = self.OUI_DATABASE.get(oui, "未知 / 私有 / 未在本地数据库")
        self.result_ready.emit(self.mac, {"oui": oui, "vendor": vendor, "raw": norm}, "")


class NetworkQualityWorker(QThread):
    """网络质量测试：延迟、抖动、丢包率"""
    result_ready = Signal(str, dict)  # host, {latency, jitter, loss, samples}

    def __init__(self, host: str, count: int = 20, interval_ms: int = 100,
                 timeout: int = 2):
        super().__init__()
        self.host = host
        self.count = count
        self.interval = interval_ms / 1000.0
        self.timeout = timeout

    def run(self):
        import time as _t
        param = "-n" if platform.system() == "Windows" else "-c"
        timeout_param = "-w" if platform.system() == "Windows" else "-W"
        samples: list = []
        success = 0
        for i in range(self.count):
            cmd = ["ping", param, "1", timeout_param, str(self.timeout), self.host]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True,
                                   timeout=self.timeout + 3)
                if r.returncode == 0:
                    success += 1
                    out = r.stdout
                    if platform.system() == "Windows":
                        m = re.search(r"时间[=<](\d+)\s*ms", out, re.I)
                        if not m:
                            m = re.search(r"(\d+)\s*ms", out)
                    else:
                        m = re.search(r"time[=<](\d+(?:\.\d+)?)\s*ms", out, re.I)
                    if m:
                        samples.append(float(m.group(1)))
                    else:
                        samples.append(0)
                else:
                    samples.append(None)
            except Exception:
                samples.append(None)
            if i < self.count - 1:
                _t.sleep(self.interval)
        # 统计
        valid = [s for s in samples if s is not None]
        loss = (self.count - len(valid)) / self.count * 100
        if valid:
            avg = sum(valid) / len(valid)
            mn = min(valid)
            mx = max(valid)
            # 抖动：相邻差值的均值
            if len(valid) > 1:
                diffs = [abs(valid[i] - valid[i - 1]) for i in range(1, len(valid))]
                jitter = sum(diffs) / len(diffs)
            else:
                jitter = 0
        else:
            avg = mn = mx = jitter = 0
        self.result_ready.emit(self.host, {
            "host": self.host,
            "sent": self.count,
            "received": len(valid),
            "loss_pct": loss,
            "avg_ms": avg,
            "min_ms": mn,
            "max_ms": mx,
            "jitter_ms": jitter,
            "samples": samples,
        })


class CookieSecurityWorker(QThread):
    """Cookie 安全属性检测（HttpOnly/Secure/SameSite/Path/Domain/Expires）"""
    result_ready = Signal(str, dict, str)  # url, cookies_info, error

    def __init__(self, url: str, timeout: float = 8.0):
        super().__init__()
        self.url = url
        self.timeout = timeout

    def run(self):
        import urllib.request
        import http.cookiejar
        info: dict = {"cookies": [], "vulnerabilities": []}
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cj))
        try:
            with opener.open(self.url, timeout=self.timeout) as resp:
                for c in cj:
                    flags = []
                    if c.secure:
                        flags.append("Secure")
                    # HttpOnly 在标准 CookieJar 中没有直接属性
                    if not c.domain.startswith("."):
                        flags.append("HostOnly")
                    info["cookies"].append({
                        "name": c.name,
                        "domain": c.domain,
                        "path": c.path,
                        "secure": c.secure,
                        "expires": c.expires,
                        "flags": flags,
                    })
            # 尝试从 Set-Cookie 头分析 SameSite / HttpOnly
            req = urllib.request.Request(self.url)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp2:
                set_cookies = resp2.headers.get_all("Set-Cookie") or []
                for sc in set_cookies:
                    sc_l = sc.lower()
                    vuln = []
                    if "httponly" not in sc_l and any(
                            kw in sc.lower() for kw in
                            ("session", "token", "auth", "sid", "csrf")):
                        vuln.append("疑似会话/鉴权 Cookie 缺少 HttpOnly")
                    if "secure" not in sc_l and self.url.startswith("https"):
                        vuln.append("HTTPS 站点 Set-Cookie 缺少 Secure")
                    if "samesite" not in sc_l:
                        vuln.append("缺少 SameSite 属性（可能存在 CSRF 风险）")
                    info["vulnerabilities"].extend(vuln)
            self.result_ready.emit(self.url, info, "")
        except Exception as e:
            self.result_ready.emit(self.url, info, str(e))


class HTTPMethodsWorker(QThread):
    """允许的 HTTP 方法检测"""
    result_ready = Signal(str, list, str)  # url, methods, error

    def __init__(self, url: str, timeout: float = 6.0):
        super().__init__()
        self.url = url
        self.timeout = timeout

    def run(self):
        import urllib.request
        results = []
        try:
            # OPTIONS
            try:
                req = urllib.request.Request(self.url, method="OPTIONS")
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    allow = resp.headers.get("Allow", "")
                    if allow:
                        results.append({
                            "method": "OPTIONS",
                            "status": resp.status,
                            "Allow": allow,
                        })
            except Exception as e:
                results.append({"method": "OPTIONS", "error": str(e)})
            # 常见方法逐一探测
            for m in ("GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "TRACE"):
                try:
                    req = urllib.request.Request(self.url, method=m,
                                                 data=b"" if m == "POST" else None)
                    with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                        results.append({"method": m, "status": resp.status, "ok": True})
                except urllib.error.HTTPError as e:
                    results.append({
                        "method": m,
                        "status": e.code,
                        "ok": (e.code not in (403, 405)),
                    })
                except Exception as e:
                    results.append({"method": m, "error": str(e)})
            self.result_ready.emit(self.url, results, "")
        except Exception as e:
            self.result_ready.emit(self.url, results, str(e))


class RDPWorker(QThread):
    """RDP / VNC 远程桌面检测"""
    result_ready = Signal(str, dict)  # host, {protocol: {port, banner, ok}}

    def __init__(self, host: str, timeout: float = 4.0):
        super().__init__()
        self.host = host
        self.timeout = timeout

    def _probe(self, port: int, send_data: bytes = b"") -> dict:
        sock = None
        info = {"port": port, "reachable": False, "banner": ""}
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((self.host, port))
            info["reachable"] = True
            if send_data:
                sock.send(send_data)
            sock.settimeout(2.0)
            try:
                data = sock.recv(1024)
                info["banner"] = data[:64].hex() if data else ""
                if port == 3389 and data:
                    # RDP 协商响应通常以 0x03 0x00 0x00 开头
                    if data[:2] == b"\x03\x00":
                        info["banner"] = "RDP 协议响应 (TPKT)"
            except socket.timeout:
                pass
        except Exception as e:
            info["error"] = str(e)
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
        return info

    def run(self):
        results = {
            "RDP(3389)": self._probe(3389, b"\x03\x00\x00\x13\x0e\xe0\x00\x00\x00\x00\x00\x01\x00\x08\x00\x00\x00\x00\x00"),
            "VNC(5900)": self._probe(5900),
            "VNC(5901)": self._probe(5901),
            "X11(6000)": self._probe(6000),
        }
        self.result_ready.emit(self.host, results)


class TLSInspectionWorker(QThread):
    """TLS 握手与 SNI 检测"""
    result_ready = Signal(str, dict, str)  # host, info, error

    def __init__(self, host: str, port: int = 443, sni: Optional[str] = None,
                 timeout: float = 6.0):
        super().__init__()
        self.host = host
        self.port = port
        self.sni = sni or host
        self.timeout = timeout

    def run(self):
        import ssl
        import struct
        info: dict = {
            "tls_version": "",
            "cipher": "",
            "alpn": "",
            "cert_subject": "",
            "cert_issuer": "",
            "cert_san": [],
            "cert_serial": "",
            "cert_notbefore": "",
            "cert_notafter": "",
            "cert_days_left": 0,
        }
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ctx.set_alpn_protocols(["h2", "http/1.1"])
            with socket.create_connection(
                    (self.host, self.port), timeout=self.timeout) as raw_sock:
                with ctx.wrap_socket(raw_sock, server_hostname=self.sni) as ssock:
                    info["tls_version"] = ssock.version() or ""
                    info["cipher"] = ssock.cipher()[0] if ssock.cipher() else ""
                    info["alpn"] = ssock.selected_alpn_protocol() or ""
                    # 获取证书二进制
                    der = ssock.getpeercert(binary_form=True)
                    if der:
                        try:
                            from cryptography import x509
                            from cryptography.hazmat.backends import default_backend
                            cert = x509.load_der_x509_certificate(
                                der, default_backend())
                            info["cert_subject"] = cert.subject.rfc4514_string()
                            info["cert_issuer"] = cert.issuer.rfc4514_string()
                            info["cert_serial"] = str(cert.serial_number)
                            info["cert_notbefore"] = cert.not_valid_before.isoformat()
                            info["cert_notafter"] = cert.not_valid_after.isoformat()
                            import datetime as _dt
                            days = (cert.not_valid_after - _dt.datetime.utcnow()).days
                            info["cert_days_left"] = days
                            san_ext = cert.extensions.get_extension_for_class(
                                x509.SubjectAlternativeName)
                            if san_ext:
                                names = [str(n) for n in san_ext.value]
                                info["cert_san"] = names[:20]
                        except ImportError:
                            # cryptography 不可用时回退到 ssl 的纯文本解析
                            try:
                                cert_text = ssock.getpeercert()
                                if cert_text:
                                    subj = cert_text.get("subject", [])
                                    iss = cert_text.get("issuer", [])
                                    info["cert_subject"] = ", ".join(
                                        "=".join(x) for x in subj) if subj else ""
                                    info["cert_issuer"] = ", ".join(
                                        "=".join(x) for x in iss) if iss else ""
                                    san = cert_text.get("subjectAltName", [])
                                    info["cert_san"] = [v for _, v in san]
                                    nbefore = cert_text.get("notBefore", "")
                                    nafter = cert_text.get("notAfter", "")
                                    info["cert_notbefore"] = str(nbefore)
                                    info["cert_notafter"] = str(nafter)
                            except Exception:
                                pass
            self.result_ready.emit(self.host, info, "")
        except Exception as e:
            self.result_ready.emit(self.host, info, str(e))


class MTRLikeWorker(QThread):
    """类 MTR 持续路由追踪：周期性发出 ICMP 探测每个节点"""
    result_ready = Signal(str, dict)  # host, {hop, ip, latency, loss_pct, samples}

    def __init__(self, host: str, max_hops: int = 20, cycles: int = 3,
                 timeout: int = 2):
        super().__init__()
        self.host = host
        self.max_hops = max_hops
        self.cycles = cycles
        self.timeout = timeout

    def run(self):
        import time as _t
        is_win = platform.system() == "Windows"
        # 收集每跳若干次
        hop_data: dict = {}
        for cycle in range(self.cycles):
            for ttl in range(1, self.max_hops + 1):
                if is_win:
                    cmd = ["ping", "-n", "1", "-w", str(self.timeout * 1000),
                           "-h", str(ttl), self.host]
                else:
                    cmd = ["ping", "-c", "1", "-W", str(self.timeout),
                           "-t", str(ttl), self.host]
                start = _t.time()
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True,
                                       timeout=self.timeout + 3)
                    elapsed = (_t.time() - start) * 1000
                    out = r.stdout
                    if is_win:
                        ip_m = re.search(r"来自\s*([\d.]+)", out)
                        if not ip_m:
                            ip_m = re.search(r"Reply from\s*([\d.]+)", out, re.I)
                        time_m = re.search(r"时间[=<](\d+)\s*ms", out, re.I)
                        if not time_m:
                            time_m = re.search(r"(\d+)\s*ms", out)
                    else:
                        ip_m = re.search(r"\((\d+\.\d+\.\d+\.\d+)\)", out)
                        if not ip_m:
                            ip_m = re.search(r"from\s+(\d+\.\d+\.\d+\.\d+)", out)
                        time_m = re.search(r"time[=<](\d+(?:\.\d+)?)\s*ms", out, re.I)
                    if ip_m:
                        ip = ip_m.group(1)
                        lat = float(time_m.group(1)) if time_m else elapsed
                        d = hop_data.setdefault(ttl, {
                            "hop": ttl, "ip": ip, "samples": [], "ok": 0, "total": 0
                        })
                        d["samples"].append(lat)
                        d["ok"] += 1
                        d["total"] += 1
                    elif r.returncode != 0 and "100%" not in out:
                        # 不可达但未完全失败
                        d = hop_data.setdefault(ttl, {
                            "hop": ttl, "ip": "*", "samples": [], "ok": 0, "total": 0
                        })
                        d["total"] += 1
                    else:
                        d = hop_data.setdefault(ttl, {
                            "hop": ttl, "ip": "*", "samples": [], "ok": 0, "total": 0
                        })
                        d["total"] += 1
                except Exception:
                    d = hop_data.setdefault(ttl, {
                        "hop": ttl, "ip": "*", "samples": [], "ok": 0, "total": 0
                    })
                    d["total"] += 1
                # 命中目标
                if ip_m and ip_m.group(1) == socket.gethostbyname(self.host):
                    self.result_ready.emit(self.host, d)
                    return
        # 输出最后一跳
        if hop_data:
            last_hop = max(hop_data.keys())
            self.result_ready.emit(self.host, hop_data[last_hop])
        else:
            self.result_ready.emit(self.host, {"hop": 0, "ip": "*", "samples": [],
                                               "ok": 0, "total": 0})


class NTPTimeWorker(QThread):
    """NTP 时间服务器检测"""
    result_ready = Signal(str, dict)  # host, {offset_ms, delay_ms, ntp_time}

    NTP_EPOCH = 2208988800  # 1900-1970

    def __init__(self, host: str = "time.windows.com", port: int = 123,
                 timeout: float = 4.0):
        super().__init__()
        self.host = host
        self.port = port
        self.timeout = timeout

    def run(self):
        import struct as _st
        import time as _t
        info: dict = {"host": self.host, "ok": False}
        try:
            # NTP 客户端请求包：LI=0, VN=4, Mode=3 -> 0x23
            pkt = b"\x23" + 47 * b"\0"
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)
            try:
                t1 = _t.time()
                sock.sendto(pkt, (self.host, self.port))
                data, _ = sock.recvfrom(1024)
                t4 = _t.time()
                if len(data) >= 48:
                    # 解析 Transmit Timestamp（第 40-47 字节）
                    secs, frac = _st.unpack(">II", data[40:48])
                    ntp_ts = secs + frac / 2 ** 32
                    unix_ts = ntp_ts - self.NTP_EPOCH
                    # 估算本地时间与 NTP 时间的差
                    rtt = (t4 - t1)
                    offset = unix_ts - (t1 + rtt / 2)
                    info.update({
                        "ok": True,
                        "ntp_time": time.strftime(
                            "%Y-%m-%d %H:%M:%S", time.gmtime(unix_ts)),
                        "offset_ms": offset * 1000,
                        "rtt_ms": rtt * 1000,
                    })
            finally:
                sock.close()
        except Exception as e:
            info["error"] = str(e)
        self.result_ready.emit(self.host, info)


class SNMPWorker(QThread):
    """SNMP 服务检测与基础 community 探测"""
    result_ready = Signal(str, dict)  # host, {reachable, sysDescr, communities}

    COMMON_COMMUNITIES = ["public", "private", "manager", "monitor", "admin", "cisco"]

    def __init__(self, host: str, port: int = 161, timeout: float = 3.0):
        super().__init__()
        self.host = host
        self.port = port
        self.timeout = timeout

    def _build_get_request(self, community: str) -> bytes:
        import struct as _st
        # 简化的 SNMPv1 GET-REQUEST (BER 编码)
        # 请求 ID = 1, error = 0, error-index = 0
        # OID 1.3.6.1.2.1.1.1.0 (sysDescr)
        oid = bytes([0x06, 0x09,
                     0x2b, 0x06, 0x01, 0x02, 0x01, 0x01, 0x01, 0x00])
        # value NULL
        value_null = bytes([0x05, 0x00])
        # varbind
        varbind = bytes([0x30]) + self._encode_len(
            len(oid) + len(value_null)) + oid + value_null
        # varbind list
        varbind_list = bytes([0x30]) + self._encode_len(len(varbind)) + varbind
        # request id, error, error index
        req_id = _st.pack(">i", 1) + _st.pack(">i", 0) + _st.pack(">i", 0)
        pdu_data = req_id + varbind_list
        pdu = bytes([0xa0]) + self._encode_len(len(pdu_data)) + pdu_data
        # version 0 (SNMPv1)
        version = bytes([0x02, 0x01, 0x00])
        # community string
        comm_bytes = community.encode()
        community_tlv = bytes([0x04, len(comm_bytes)]) + comm_bytes
        payload = version + community_tlv + pdu
        msg = bytes([0x30]) + self._encode_len(len(payload)) + payload
        return msg

    @staticmethod
    def _encode_len(length: int) -> bytes:
        if length < 128:
            return bytes([length])
        # 长形式
        n_bytes = []
        while length > 0:
            n_bytes.insert(0, length & 0xFF)
            length >>= 8
        return bytes([0x80 | len(n_bytes)] + n_bytes)

    def run(self):
        info: dict = {
            "reachable": False,
            "communities_found": [],
            "sysDescr": "",
        }
        # 先用空 UDP 探测端口是否开放
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)
            for comm in self.COMMON_COMMUNITIES:
                try:
                    pkt = self._build_get_request(comm)
                    sock.sendto(pkt, (self.host, self.port))
                    data, _ = sock.recvfrom(4096)
                    if data and len(data) > 0:
                        info["reachable"] = True
                        # 简单识别：响应中包含 OID 1.3.6.1.2.1.1.1.0
                        if b"\x2b\x06\x01\x02\x01\x01\x01\x00" in data:
                            info["communities_found"].append(comm)
                except socket.timeout:
                    continue
                except Exception:
                    continue
        except Exception as e:
            info["error"] = str(e)
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
        # 如未通过 SNMP 协议识别出 community，再做一次 TCP 端口可达性探测
        if not info["reachable"]:
            try:
                ts = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                ts.settimeout(self.timeout)
                ts.connect((self.host, self.port))
                info["reachable"] = True
                ts.close()
            except Exception:
                pass
        self.result_ready.emit(self.host, info)
