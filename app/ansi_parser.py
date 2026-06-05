"""
ANSI 颜色转义码解析器
将终端 ANSI 控制码转换为 Qt 富文本格式
"""

import re
from typing import List, Tuple

from PySide6.QtGui import QTextCharFormat, QColor, QFont


# ANSI 标准颜色映射（经典16色）
ANSI_COLORS = {
    0: "#000000",   # 黑
    1: "#800000",   # 深红
    2: "#008000",   # 绿
    3: "#808000",   # 黄
    4: "#000080",   # 深蓝
    5: "#800080",   # 紫
    6: "#008080",   # 青
    7: "#c0c0c0",   # 白（浅灰）
    8: "#808080",   # 亮黑（深灰）
    9: "#ff0000",   # 亮红
    10: "#00ff00",  # 亮绿
    11: "#ffff00",  # 亮黄
    12: "#0000ff",  # 亮蓝
    13: "#ff00ff",  # 亮紫
    14: "#00ffff",  # 亮青
    15: "#ffffff",  # 亮白
}


class AnsiParser:
    """ANSI 转义序列解析器，转换为 QTextCharFormat 列表"""

    # 匹配 ANSI 控制序列: ESC [ <params> m
    ANSI_RE = re.compile(r"\x1b\[([\d;]*)m")
    # 匹配其他控制序列（如光标移动等），直接忽略
    CONTROL_RE = re.compile(r"\x1b\[[\d;]*[A-Za-z]")

    def __init__(self, default_fg: str = "#cccccc", default_bg: str = "#1e1e1e"):
        self.default_fg = default_fg
        self.default_bg = default_bg

    def parse(self, text: str) -> List[Tuple[str, QTextCharFormat]]:
        """
        解析包含 ANSI 控制码的文本，返回 (文本片段, 格式) 的列表。
        """
        # 先移除非颜色控制序列
        text = self.CONTROL_RE.sub("", text)

        result: List[Tuple[str, QTextCharFormat]] = []
        last_end = 0

        # 当前格式状态
        fg_color = self.default_fg
        bg_color = self.default_bg
        bold = False
        italic = False
        underline = False

        for match in self.ANSI_RE.finditer(text):
            # 添加匹配前的纯文本
            plain = text[last_end:match.start()]
            if plain:
                fmt = self._make_format(fg_color, bg_color, bold, italic, underline)
                result.append((plain, fmt))

            # 解析参数
            params_str = match.group(1)
            if params_str:
                params = [int(p) for p in params_str.split(";") if p.isdigit()]
            else:
                params = [0]

            # 处理每个参数
            i = 0
            while i < len(params):
                code = params[i]
                if code == 0:
                    # 重置
                    fg_color = self.default_fg
                    bg_color = self.default_bg
                    bold = False
                    italic = False
                    underline = False
                elif code == 1:
                    bold = True
                elif code == 3:
                    italic = True
                elif code == 4:
                    underline = True
                elif 30 <= code <= 37:
                    # 前景色
                    fg_color = ANSI_COLORS.get(code - 30, self.default_fg)
                elif 40 <= code <= 47:
                    # 背景色
                    bg_color = ANSI_COLORS.get(code - 40, self.default_bg)
                elif 90 <= code <= 97:
                    # 亮前景色
                    fg_color = ANSI_COLORS.get(code - 90 + 8, self.default_fg)
                elif 100 <= code <= 107:
                    # 亮背景色
                    bg_color = ANSI_COLORS.get(code - 100 + 8, self.default_bg)
                elif code == 38 and i + 1 < len(params):
                    # 256色或真彩色
                    if params[i + 1] == 5 and i + 2 < len(params):
                        # 256色模式
                        color_idx = params[i + 2]
                        fg_color = self._color_256(color_idx)
                        i += 2
                    elif params[i + 1] == 2 and i + 4 < len(params):
                        # 真彩色模式
                        r, g, b = params[i + 2], params[i + 3], params[i + 4]
                        fg_color = f"#{r:02x}{g:02x}{b:02x}"
                        i += 4
                elif code == 48 and i + 1 < len(params):
                    if params[i + 1] == 5 and i + 2 < len(params):
                        color_idx = params[i + 2]
                        bg_color = self._color_256(color_idx)
                        i += 2
                    elif params[i + 1] == 2 and i + 4 < len(params):
                        r, g, b = params[i + 2], params[i + 3], params[i + 4]
                        bg_color = f"#{r:02x}{g:02x}{b:02x}"
                        i += 4
                elif code == 39:
                    fg_color = self.default_fg
                elif code == 49:
                    bg_color = self.default_bg
                elif code == 22:
                    bold = False
                elif code == 23:
                    italic = False
                elif code == 24:
                    underline = False
                i += 1

            last_end = match.end()

        # 添加剩余文本
        remaining = text[last_end:]
        if remaining:
            fmt = self._make_format(fg_color, bg_color, bold, italic, underline)
            result.append((remaining, fmt))

        return result

    def _make_format(self, fg: str, bg: str, bold: bool, italic: bool, underline: bool) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(fg))
        fmt.setBackground(QColor(bg))
        if bold:
            fmt.setFontWeight(QFont.Bold)
        if italic:
            fmt.setFontItalic(True)
        if underline:
            fmt.setFontUnderline(True)
        return fmt

    def _color_256(self, idx: int) -> str:
        """256色调色板映射"""
        if idx < 16:
            return ANSI_COLORS.get(idx, self.default_fg)
        elif idx < 232:
            # 6x6x6 色立方体
            idx -= 16
            b = idx % 6
            idx //= 6
            g = idx % 6
            r = idx // 6
            r_val = min(r * 51 + (0 if r == 0 else 55), 255)
            g_val = min(g * 51 + (0 if g == 0 else 55), 255)
            b_val = min(b * 51 + (0 if b == 0 else 55), 255)
            return f"#{r_val:02x}{g_val:02x}{b_val:02x}"
        else:
            # 灰度
            gray = min((idx - 232) * 10 + 8, 255)
            return f"#{gray:02x}{gray:02x}{gray:02x}"

    def strip_ansi(self, text: str) -> str:
        """移除所有 ANSI 控制码，返回纯文本"""
        text = self.CONTROL_RE.sub("", text)
        return self.ANSI_RE.sub("", text)
