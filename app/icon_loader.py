"""
应用图标加载工具
从 gemini-svg.svg 加载并提供多种尺寸的 QPixmap / QIcon
"""

import os
from PySide6.QtGui import QPixmap, QIcon, QPainter, QColor
from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtWidgets import QApplication


# SVG 文件路径
_ICON_SVG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gemini-svg.svg")

# 缓存
_svg_data_cache: bytes | None = None
_pixmap_cache: dict[int, QPixmap] = {}


def _load_svg_data() -> bytes:
    """读取 SVG 文件原始字节"""
    global _svg_data_cache
    if _svg_data_cache is None:
        try:
            with open(_ICON_SVG_PATH, "rb") as f:
                _svg_data_cache = f.read()
        except Exception as e:
            print(f"[icon_loader] 读取 SVG 失败: {_ICON_SVG_PATH}: {e}")
            _svg_data_cache = b""
    return _svg_data_cache


def get_icon_pixmap(size: int = 32) -> QPixmap:
    """获取指定尺寸的应用图标 QPixmap

    Qt 原生支持 SVG，可直接通过 QPixmap.loadFromData 加载并按目标尺寸渲染。
    """
    global _pixmap_cache
    if size in _pixmap_cache:
        return _pixmap_cache[size]

    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    data = _load_svg_data()
    if not data:
        _pixmap_cache[size] = pix
        return pix

    # 1) 加载原始 SVG
    src = QPixmap()
    src.loadFromData(data, "SVG")
    if src.isNull():
        _pixmap_cache[size] = pix
        return pix

    # 2) 平滑缩放到目标尺寸
    pix = src.scaled(
        size, size,
        Qt.KeepAspectRatio,
        Qt.SmoothTransformation,
    )
    _pixmap_cache[size] = pix
    return pix


def get_app_icon() -> QIcon:
    """获取 QIcon（多尺寸：16/24/32/48/64/128/256）"""
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        pm = get_icon_pixmap(s)
        if not pm.isNull():
            icon.addPixmap(pm)
    return icon


def set_app_icon(app: QApplication):
    """把应用图标设置到 QApplication（任务栏 + 窗口标题）"""
    icon = get_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
