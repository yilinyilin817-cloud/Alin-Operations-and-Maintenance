"""端口扫描增强 - AiinLink 内置插件
增强版端口扫描工具，支持快速模式
"""
import socket
from typing import List, Dict, Optional


def scan_ports(host: str, ports: Optional[List[int]] = None, fast_mode: bool = False) -> Dict:
    """增强版端口扫描"""
    results = []
    if ports is None:
        ports = list(range(1, 1001))
    timeout = 0.2 if fast_mode else 1.0
    for port in ports:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            if sock.connect_ex((host, port)) == 0:
                results.append(port)
            sock.close()
        except Exception:
            pass
    return {"host": host, "open_ports": results, "count": len(results), "fast_mode": fast_mode}


def quick_scan(host: str) -> Dict:
    """快速扫描常用端口"""
    common = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 3306, 3389, 5432, 6379, 8080, 8443, 9200, 27017]
    return scan_ports(host, common, fast_mode=True)


if __name__ == "__main__":
    print(scan_ports("127.0.0.1"))
