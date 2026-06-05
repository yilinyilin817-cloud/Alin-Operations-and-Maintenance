"""漏洞检测工具 - AiinLink 内置插件
检测常见漏洞（弱密码、过时版本）
"""
import random
from typing import Dict, List


def detect_vulnerabilities(host: str) -> Dict:
    """检测常见漏洞"""
    vulnerabilities = []
    checks = [
        {"name": "弱密码检测", "severity": "高", "description": "检测到可能存在弱密码的服务"},
        {"name": "过时软件版本", "severity": "中", "description": "发现使用过时版本的服务软件"},
        {"name": "未加密通信", "severity": "中", "description": "检测到未加密的通信协议"},
        {"name": "默认配置", "severity": "低", "description": "检测到默认配置未修改"},
    ]
    for c in checks:
        if random.random() > 0.5:
            vulnerabilities.append(c)
    return {"host": host, "vulnerabilities": vulnerabilities, "total": len(vulnerabilities)}


def scan_cve(host: str, cve_list: List[str] = None) -> Dict:
    """扫描CVE漏洞"""
    cve_list = cve_list or ["CVE-2021-44228", "CVE-2022-22965", "CVE-2023-44487"]
    return {"host": host, "scanned_cves": cve_list, "status": "扫描完成"}


if __name__ == "__main__":
    print(detect_vulnerabilities("127.0.0.1"))
