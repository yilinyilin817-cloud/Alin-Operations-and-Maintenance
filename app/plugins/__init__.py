# AiinLink 插件系统 - 内置插件
# 这些插件无需从GitHub下载，直接内置在应用中

import os

# 内置插件列表
BUILTIN_PLUGINS = {
    "端口扫描增强": "port_scan_enhanced",
    "漏洞检测工具": "vuln_scanner",
    "安全审计工具": "security_audit",
    "网络流量分析": "traffic_analyzer",
}

def get_builtin_plugins():
    """获取内置插件列表"""
    return BUILTIN_PLUGINS.copy()

def is_builtin_plugin(name):
    """检查是否为内置插件"""
    return name in BUILTIN_PLUGINS

def install_builtin_plugin(name):
    """安装内置插件（创建示例文件）"""
    plugin_dir = os.path.dirname(__file__)
    
    plugin_info = {
        "端口扫描增强": {
            "filename": "port_scan_enhanced.py",
            "content": '''"""端口扫描增强插件"""

def scan_ports(host, ports=None, fast_mode=False):
    """增强版端口扫描"""
    import socket
    results = []
    ports = ports or range(1, 1001)
    timeout = 0.2 if fast_mode else 1.0
    
    for port in ports:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            if result == 0:
                results.append(port)
            sock.close()
        except:
            pass
    
    return {"host": host, "open_ports": results, "count": len(results)}
'''
        },
        "漏洞检测工具": {
            "filename": "vuln_scanner.py",
            "content": '''"""漏洞检测插件"""

def detect_vulnerabilities(host):
    """检测常见漏洞"""
    vulnerabilities = []
    
    # 模拟漏洞检测结果
    import random
    if random.choice([True, False]):
        vulnerabilities.append({
            "name": "弱密码检测",
            "severity": "高",
            "description": "检测到可能存在弱密码的服务",
        })
    if random.choice([True, False]):
        vulnerabilities.append({
            "name": "过时软件版本",
            "severity": "中",
            "description": "发现使用过时版本的服务软件",
        })
    
    return {"host": host, "vulnerabilities": vulnerabilities}
'''
        },
        "安全审计工具": {
            "filename": "security_audit.py",
            "content": '''"""安全审计插件"""

def audit_security(host):
    """执行安全审计"""
    checks = []
    
    checks.append({
        "check": "端口安全",
        "result": "通过",
        "details": "未发现危险端口开放",
    })
    checks.append({
        "check": "服务版本",
        "result": "警告",
        "details": "部分服务版本较旧",
    })
    
    return {"host": host, "audit_results": checks}
'''
        },
        "网络流量分析": {
            "filename": "traffic_analyzer.py",
            "content": '''"""网络流量分析插件"""

def analyze_traffic(host, duration=10):
    """分析网络流量"""
    import time
    
    start_time = time.time()
    # 模拟流量数据收集
    time.sleep(min(duration, 2))  # 快速模拟
    
    return {
        "host": host,
        "duration": duration,
        "packets_captured": 100 + int(time.time() % 100),
        "protocols": ["TCP", "UDP", "HTTP"],
        "analysis": "流量分析完成",
    }
'''
        },
    }
    
    info = plugin_info.get(name)
    if info:
        file_path = os.path.join(plugin_dir, info["filename"])
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(info["content"])
        return True
    
    return False
