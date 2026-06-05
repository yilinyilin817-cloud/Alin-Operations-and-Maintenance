"""
主题资源包
集中管理调色板、字体、间距、阴影、动效等设计资源
所有新模块都应引用此处的常量，避免在代码中散落硬编码颜色
"""

# ============================================================
# 调色板 - 现代深色 IDE 风格
# ============================================================

# 背景层级（从最深到最浅）
BG_BASE = "#0f1115"          # 窗口底色
BG_DEEP = "#161a22"          # 侧边栏/标题栏
BG_PANEL = "#1c2029"         # 卡片/面板
BG_PANEL_HOVER = "#232834"   # 面板 hover
BG_INPUT = "#0e1116"         # 输入框
BG_RAISED = "#252a36"        # 浮起元素
BG_DISABLED = "#1a1d24"      # 禁用控件背景
BG_INPUT_DISABLED = "#14171d"  # 禁用输入框背景
BG_PRIMARY_TINT = "#1a3a3a"  # 带主色调的背景

# 文本
FG_PRIMARY = "#e6e9ef"
FG_SECONDARY = "#a8b0bf"
FG_TERTIARY = "#6b7384"
FG_DISABLED = "#4a5161"
FG_ON_PRIMARY = "#0a1f1d"    # 主色背景上的文本色

# 边框
BORDER = "#262b35"
BORDER_LIGHT = "#2f3543"
BORDER_FOCUS = "#4ecdc4"
BORDER_PRIMARY_TINT = "#2a4a48"  # 带主色调的边框

# 强调色（青蓝 - 主品牌色）
PRIMARY = "#4ecdc4"
PRIMARY_HOVER = "#62d6ce"
PRIMARY_DARK = "#3ba89f"
PRIMARY_GLOW = "rgba(78, 205, 196, 80)"

# 蓝
ACCENT_BLUE = "#3b9eff"
ACCENT_BLUE_HOVER = "#54a8ff"

# 紫
ACCENT_PURPLE = "#9b8cff"
ACCENT_PURPLE_HOVER = "#ad9fff"

# 橙
ACCENT_ORANGE = "#ff8c42"

# 粉
ACCENT_PINK = "#f06292"

# 状态色
SUCCESS = "#3ecf8e"
SUCCESS_BG = "#1c3a2e"
WARN = "#ffb547"
WARN_BG = "#3d2f17"
DANGER = "#ff6b6b"
DANGER_BG = "#3d1f23"
DANGER_HOVER = "#ff8585"
INFO = "#4ecdc4"

# 滚动条
SCROLLBAR_HANDLE = "#3a4050"
SCROLLBAR_HANDLE_HOVER = "#4a5060"

# 折线图曲线调色板
CHART_PALETTE = [
    "#4ecdc4",  # 青
    "#3b9eff",  # 蓝
    "#9b8cff",  # 紫
    "#ffb547",  # 橙
    "#ff6b6b",  # 红
    "#3ecf8e",  # 绿
    "#f06292",  # 粉
    "#ba68c8",  # 紫红
]

# ============================================================
# 渐变
# ============================================================
GRADIENT_PRIMARY = (
    "qlineargradient(x1:0, y1:0, x2:1, y2:0, "
    f"stop:0 {PRIMARY}, stop:1 {ACCENT_BLUE})"
)
GRADIENT_SIDEBAR = (
    "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
    f"stop:0 {BG_DEEP}, stop:1 {BG_BASE})"
)

# ============================================================
# 字体
# ============================================================
FONT_FAMILY = '"Microsoft YaHei", "Segoe UI", "PingFang SC", "Hiragino Sans GB", sans-serif'
FONT_MONO = '"Cascadia Code", "Fira Code", "JetBrains Mono", Consolas, "Courier New", monospace'

FONT_SIZE_XS = 10
FONT_SIZE_SM = 11
FONT_SIZE_BASE = 12
FONT_SIZE_MD = 13
FONT_SIZE_LG = 15
FONT_SIZE_XL = 18
FONT_SIZE_XXL = 22

# ============================================================
# 尺寸
# ============================================================
RADIUS_SM = 4
RADIUS_MD = 6
RADIUS_LG = 10
RADIUS_XL = 16

SIDEBAR_WIDTH = 56
SIDEBAR_WIDTH_EXPANDED = 200
TITLE_BAR_HEIGHT = 32

# ============================================================
# 阴影 / 动画
# ============================================================
SHADOW_SOFT = "0 2px 8px rgba(0, 0, 0, 0.25)"
SHADOW_MEDIUM = "0 4px 16px rgba(0, 0, 0, 0.35)"
SHADOW_SIDEBAR = "0 0 24px rgba(0, 0, 0, 0.4)"
SHADOW_GLOW = "0 0 20px rgba(78, 205, 196, 0.4)"

ANIM_FAST = 120   # ms
ANIM_NORMAL = 200
ANIM_SLOW = 350


# ============================================================
# 公共样式表 - 可被嵌入到 QApplication.setStyleSheet
# ============================================================

COMMON_QSS = f"""
/* 全局基础 */
* {{
    font-family: {FONT_FAMILY};
    color: {FG_PRIMARY};
}}

QWidget {{
    background-color: transparent;
    color: {FG_PRIMARY};
    font-size: {FONT_SIZE_BASE}px;
    outline: 0;
}}

QMainWindow {{
    background-color: {BG_BASE};
}}

/* 主标题样式（带渐变文字） */
QLabel[role="heroTitle"] {{
    font-size: {FONT_SIZE_XXL}px;
    font-weight: 700;
    color: {PRIMARY};
}}

QLabel[role="heroSubtitle"] {{
    font-size: {FONT_SIZE_SM}px;
    color: {FG_SECONDARY};
}}

/* 卡片 - 现代化设计 */
QFrame[role="card"] {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_LG}px;
}}

QFrame[role="cardElevated"] {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER_LIGHT};
    border-radius: {RADIUS_LG}px;
}}

QFrame[role="card"]:hover {{
    border-color: {BORDER_FOCUS};
}}

/* 渐变卡片 */
QFrame[role="gradientCard"] {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {BG_PANEL}, stop:1 {BG_PRIMARY_TINT});
    border: 1px solid {BORDER_PRIMARY_TINT};
    border-radius: {RADIUS_LG}px;
}}

/* 按钮 - 基础 */
QPushButton {{
    background-color: {BG_RAISED};
    color: {FG_PRIMARY};
    border: 1px solid {BORDER_LIGHT};
    border-radius: {RADIUS_MD}px;
    padding: 6px 14px;
    font-size: {FONT_SIZE_BASE}px;
    min-height: 22px;
}}

QPushButton:hover {{
    background-color: {BG_PANEL_HOVER};
    border-color: {BORDER_FOCUS};
}}

QPushButton:pressed {{
    background-color: {PRIMARY_DARK};
    border-color: {PRIMARY_DARK};
}}

QPushButton:disabled {{
    background-color: {BG_DISABLED};
    color: {FG_DISABLED};
    border-color: {BORDER};
}}

/* 主按钮 - 强调色 */
QPushButton[role="primary"] {{
    background-color: {PRIMARY};
    color: {FG_ON_PRIMARY};
    border: none;
    font-weight: 600;
}}

QPushButton[role="primary"]:hover {{
    background-color: {PRIMARY_HOVER};
}}

QPushButton[role="primary"]:pressed {{
    background-color: {PRIMARY_DARK};
}}

/* 幽灵按钮 - 描边风格 */
QPushButton[role="ghost"] {{
    background-color: transparent;
    color: {PRIMARY};
    border: 1px solid {PRIMARY};
    border-radius: {RADIUS_MD}px;
    padding: 6px 14px;
    font-size: {FONT_SIZE_BASE}px;
    min-height: 22px;
}}

QPushButton[role="ghost"]:hover {{
    background-color: {PRIMARY_GLOW};
    border-color: {PRIMARY_HOVER};
    color: {PRIMARY_HOVER};
}}

QPushButton[role="ghost"]:pressed {{
    background-color: {PRIMARY_DARK};
    color: {FG_ON_PRIMARY};
    border-color: {PRIMARY_DARK};
}}

QPushButton[role="ghost"]:disabled {{
    background-color: transparent;
    color: {FG_DISABLED};
    border-color: {BORDER};
}}

/* 危险按钮 */
QPushButton[role="danger"] {{
    background-color: {DANGER};
    color: white;
    border: none;
}}

QPushButton[role="danger"]:hover {{
    background-color: {DANGER_HOVER};
}}

/* 标签 - 文本样式 */
QLabel[role="caption"] {{
    color: {FG_SECONDARY};
    font-size: {FONT_SIZE_SM}px;
}}

QLabel[role="strong"] {{
    color: {FG_PRIMARY};
    font-weight: 600;
}}

QLabel[role="value"] {{
    color: {PRIMARY};
    font-size: {FONT_SIZE_XL}px;
    font-weight: 700;
}}

QLabel[role="valueLarge"] {{
    color: {PRIMARY};
    font-size: 28px;
    font-weight: 700;
}}

/* 状态徽章 */
QLabel[role="badge"] {{
    background-color: {PRIMARY_GLOW};
    color: {PRIMARY};
    border: 1px solid {PRIMARY};
    border-radius: 10px;
    padding: 2px 10px;
    font-size: {FONT_SIZE_XS}px;
    font-weight: 600;
}}

QLabel[role="badge"][type="success"] {{
    background-color: {SUCCESS_BG};
    color: {SUCCESS};
    border-color: {SUCCESS};
}}

QLabel[role="badge"][type="warn"] {{
    background-color: {WARN_BG};
    color: {WARN};
    border-color: {WARN};
}}

QLabel[role="badge"][type="danger"] {{
    background-color: {DANGER_BG};
    color: {DANGER};
    border-color: {DANGER};
}}

/* 菜单栏 - 现代化 */
QMenuBar {{
    background-color: {BG_DEEP};
    color: {FG_PRIMARY};
    border: none;
    padding: 2px 6px;
    font-size: {FONT_SIZE_BASE}px;
}}

QMenuBar::item {{
    background: transparent;
    padding: 5px 10px;
    margin: 1px 2px;
    border-radius: {RADIUS_SM}px;
}}

QMenuBar::item:selected {{
    background-color: {PRIMARY};
    color: {FG_ON_PRIMARY};
}}

QMenu {{
    background-color: {BG_DEEP};
    color: {FG_PRIMARY};
    border: 1px solid {BORDER_LIGHT};
    border-radius: {RADIUS_MD}px;
    padding: 6px;
}}

QMenu::item {{
    padding: 7px 22px 7px 22px;
    border-radius: {RADIUS_SM}px;
    margin: 1px;
}}

QMenu::item:selected {{
    background-color: {PRIMARY};
    color: {FG_ON_PRIMARY};
}}

QMenu::separator {{
    height: 1px;
    background: {BORDER_LIGHT};
    margin: 4px 8px;
}}

/* 工具栏 */
QToolBar {{
    background-color: {BG_DEEP};
    border: none;
    padding: 4px 6px;
    spacing: 6px;
}}

QToolBar::separator {{
    background-color: {BORDER_LIGHT};
    width: 1px;
    margin: 4px 6px;
}}

QToolBar QToolButton {{
    background-color: transparent;
    color: {FG_PRIMARY};
    border: 1px solid transparent;
    padding: 5px 10px;
    border-radius: {RADIUS_SM}px;
    font-size: {FONT_SIZE_BASE}px;
}}

QToolBar QToolButton:hover {{
    background-color: {BG_PANEL_HOVER};
    border-color: {BORDER_LIGHT};
}}

QToolBar QToolButton:pressed,
QToolBar QToolButton:checked {{
    background-color: {PRIMARY};
    color: {FG_ON_PRIMARY};
}}

/* 状态栏 */
QStatusBar {{
    background: {BG_DEEP};
    color: {FG_SECONDARY};
    border-top: 1px solid {BORDER};
}}

QStatusBar QLabel {{
    color: {FG_SECONDARY};
    padding: 0 6px;
}}

/* GroupBox - 增强版带主色顶部边框 */
QGroupBox {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-top: 2px solid {PRIMARY};
    border-radius: {RADIUS_MD}px;
    margin-top: 12px;
    padding: 12px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: {PRIMARY};
    background-color: {BG_PANEL};
}}

/* 输入控件 */
QLineEdit, QPlainTextEdit, QTextEdit {{
    background-color: {BG_INPUT};
    color: {FG_PRIMARY};
    border: 1px solid {BORDER_LIGHT};
    border-radius: {RADIUS_SM}px;
    padding: 5px 8px;
    selection-background-color: {PRIMARY};
    selection-color: {FG_ON_PRIMARY};
}}

QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: {PRIMARY};
}}

QLineEdit:disabled {{
    background-color: {BG_INPUT_DISABLED};
    color: {FG_DISABLED};
}}

/* 下拉框 */
QComboBox {{
    background-color: {BG_INPUT};
    color: {FG_PRIMARY};
    border: 1px solid {BORDER_LIGHT};
    border-radius: {RADIUS_SM}px;
    padding: 5px 8px;
    min-height: 22px;
}}

QComboBox:hover {{
    border-color: {PRIMARY};
}}

QComboBox:focus {{
    border-color: {PRIMARY};
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 24px;
    border: none;
    border-left: 1px solid {BORDER_LIGHT};
}}

QComboBox::down-arrow {{
    width: 8px;
    height: 8px;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {FG_SECONDARY};
}}

QComboBox:hover::down-arrow {{
    border-top-color: {PRIMARY};
}}

QComboBox QAbstractItemView {{
    background-color: {BG_DEEP};
    color: {FG_PRIMARY};
    border: 1px solid {BORDER_LIGHT};
    border-radius: {RADIUS_SM}px;
    selection-background-color: {PRIMARY};
    selection-color: {FG_ON_PRIMARY};
    outline: none;
}}

QComboBox:disabled {{
    background-color: {BG_INPUT_DISABLED};
    color: {FG_DISABLED};
}}

/* 数值微调框 */
QSpinBox {{
    background-color: {BG_INPUT};
    color: {FG_PRIMARY};
    border: 1px solid {BORDER_LIGHT};
    border-radius: {RADIUS_SM}px;
    padding: 5px 8px;
    min-height: 22px;
}}

QSpinBox:hover {{
    border-color: {PRIMARY};
}}

QSpinBox:focus {{
    border-color: {PRIMARY};
}}

QSpinBox::up-button, QSpinBox::down-button {{
    subcontrol-origin: border;
    width: 18px;
    border: none;
    background-color: transparent;
}}

QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background-color: {BG_PANEL_HOVER};
}}

QSpinBox::up-arrow {{
    width: 6px;
    height: 6px;
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-bottom: 4px solid {FG_SECONDARY};
}}

QSpinBox::down-arrow {{
    width: 6px;
    height: 6px;
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-top: 4px solid {FG_SECONDARY};
}}

QSpinBox::up-button:hover::up-arrow {{
    border-bottom-color: {PRIMARY};
}}

QSpinBox::down-button:hover::down-arrow {{
    border-top-color: {PRIMARY};
}}

QSpinBox:disabled {{
    background-color: {BG_INPUT_DISABLED};
    color: {FG_DISABLED};
}}

/* 选项卡 */
QTabWidget::pane {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD}px;
    top: -1px;
}}

QTabBar::tab {{
    background-color: {BG_DEEP};
    color: {FG_SECONDARY};
    border: 1px solid {BORDER};
    border-bottom: none;
    border-top-left-radius: {RADIUS_SM}px;
    border-top-right-radius: {RADIUS_SM}px;
    padding: 7px 16px;
    margin-right: 2px;
    min-width: 60px;
}}

QTabBar::tab:hover {{
    background-color: {BG_PANEL_HOVER};
    color: {FG_PRIMARY};
}}

QTabBar::tab:selected {{
    background-color: {BG_PANEL};
    color: {PRIMARY};
    border-color: {PRIMARY};
    border-bottom: 2px solid {PRIMARY};
    font-weight: 600;
}}

QTabBar::tab:!selected {{
    margin-top: 2px;
}}

/* 分割器 */
QSplitter::handle {{
    background-color: {BORDER};
}}

QSplitter::handle:horizontal {{
    width: 2px;
    margin: 4px 0;
}}

QSplitter::handle:vertical {{
    height: 2px;
    margin: 0 4px;
}}

QSplitter::handle:hover {{
    background-color: {PRIMARY};
}}

QSplitter::handle:horizontal:hover {{
    width: 3px;
}}

QSplitter::handle:vertical:hover {{
    height: 3px;
}}

/* 工具提示 */
QToolTip {{
    background-color: {BG_DEEP};
    color: {FG_PRIMARY};
    border: 1px solid {PRIMARY};
    border-radius: {RADIUS_SM}px;
    padding: 6px 10px;
    font-size: {FONT_SIZE_SM}px;
}}

/* 对话框 */
QDialog {{
    background-color: {BG_BASE};
}}

/* 列表视图 / 树视图 */
QListView, QTreeView {{
    background-color: {BG_INPUT};
    color: {FG_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px;
    outline: none;
}}

QListView::item, QTreeView::item {{
    padding: 5px 8px;
    border-radius: {RADIUS_SM}px;
    margin: 1px 2px;
}}

QListView::item:hover, QTreeView::item:hover {{
    background-color: {BG_PANEL_HOVER};
}}

QListView::item:selected, QTreeView::item:selected {{
    background-color: {PRIMARY};
    color: {FG_ON_PRIMARY};
}}

QTreeView::branch {{
    background-color: transparent;
}}

QTreeView::branch:has-children:!has-siblings:closed,
QTreeView::branch:closed:has-children:has-siblings {{
    border-image: none;
    image: none;
}}

QTreeView::branch:open:has-children:!has-siblings,
QTreeView::branch:open:has-children:has-siblings {{
    border-image: none;
    image: none;
}}

QHeaderView::section {{
    background-color: {BG_DEEP};
    color: {FG_SECONDARY};
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    padding: 6px 10px;
    font-weight: 600;
    font-size: {FONT_SIZE_SM}px;
}}

QHeaderView::section:hover {{
    background-color: {BG_PANEL_HOVER};
    color: {FG_PRIMARY};
}}

/* 进度条 */
QProgressBar {{
    background-color: {BG_INPUT};
    color: {FG_PRIMARY};
    border: none;
    border-radius: {RADIUS_SM}px;
    text-align: center;
    height: 8px;
}}

QProgressBar::chunk {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {PRIMARY}, stop:1 {PRIMARY_HOVER});
    border-radius: {RADIUS_SM}px;
}}

/* 复选框 / 单选 */
QCheckBox, QRadioButton {{
    color: {FG_PRIMARY};
    spacing: 6px;
    padding: 2px 0;
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    background-color: {BG_INPUT};
    border: 1px solid {BORDER_LIGHT};
    border-radius: 3px;
}}

QRadioButton::indicator {{
    border-radius: 8px;
}}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {PRIMARY};
}}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {PRIMARY};
    border-color: {PRIMARY};
}}

/* 滚动条 - 纤细优雅风格 */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {SCROLLBAR_HANDLE};
    border-radius: 3px;
    min-height: 30px;
    margin: 2px 0;
}}

QScrollBar::handle:vertical:hover {{
    background: {PRIMARY};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent; height: 0; border: none;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background: {SCROLLBAR_HANDLE};
    border-radius: 3px;
    min-width: 30px;
    margin: 0 2px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {PRIMARY};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent; width: 0; border: none;
}}
"""


def merge_qss(base: str, extra: str) -> str:
    """合并两份 QSS，后者覆盖前者同名规则"""
    return base + "\n" + extra
