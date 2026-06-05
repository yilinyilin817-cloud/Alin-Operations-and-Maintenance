"""
AiinLink - 智能网络与服务器诊断工作站
入口文件
"""

import sys
import os
import traceback


def _global_exception_handler(exc_type, exc_value, exc_tb):
    """全局异常处理，避免闪退"""
    # 忽略 KeyboardInterrupt
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return

    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))

    # 写入日志文件
    try:
        log_path = os.path.join(os.path.dirname(__file__), "crash.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"时间: {__import__('time').strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(msg)
            f.write(f"{'='*60}\n")
    except Exception:
        pass

    # 打印到控制台
    sys.stderr.write(msg)

    # 尝试弹出错误框（仅在没有 Qt 时静默忽略）
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance()
        if app:
            QMessageBox.critical(
                None, "AiinLink 发生错误",
                f"程序遇到错误：\n\n{exc_value}\n\n详细日志已写入 crash.log"
            )
    except Exception:
        pass


# 设置全局异常钩子
sys.excepthook = _global_exception_handler

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from app.main_window import MainWindow


def load_stylesheet(app: QApplication):
    """加载QSS样式表"""
    qss_path = os.path.join(os.path.dirname(__file__), "app", "resources", "style.qss")
    if os.path.exists(qss_path):
        try:
            with open(qss_path, "r", encoding="utf-8") as f:
                app.setStyleSheet(f.read())
        except Exception as e:
            print(f"加载样式表失败: {e}")


def main():
    # 高DPI支持
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("AiinLink")
    app.setApplicationDisplayName("AiinLink - 智能网络与服务器诊断工作站")

    # 使用 Fusion 风格保证深色主题跨平台一致
    try:
        app.setStyle("Fusion")
    except Exception:
        pass

    # 设置全局默认字体（更小的基础字号，标题等通过 QSS role 控制）
    try:
        font = QFont("Microsoft YaHei", 9)
        font.setStyleStrategy(QFont.PreferAntialias)
        app.setFont(font)
    except Exception:
        pass

    # 设置应用图标（任务栏/窗口标题）
    try:
        from app.icon_loader import set_app_icon
        set_app_icon(app)
    except Exception as e:
        print(f"应用图标加载失败: {e}")

    # 加载样式表
    load_stylesheet(app)

    # 显示启动闪屏（在主窗口创建前）
    splash = None
    try:
        from app.splash import AnimatedSplash
        splash = AnimatedSplash()
        splash.show()
        app.processEvents()
        splash.set_progress(15, "正在初始化应用...")
    except Exception as e:
        print(f"闪屏加载失败: {e}")

    def _update_splash(value: int, text: str):
        if splash is not None:
            try:
                splash.set_progress(value, text)
                app.processEvents()
            except Exception:
                pass

    _update_splash(35, "加载主题资源...")
    _update_splash(55, "初始化核心引擎...")

    try:
        _update_splash(75, "构建主窗口...")
        window = MainWindow()
        window.show()
        _update_splash(100, "就绪")
    except Exception as e:
        traceback.print_exc()
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "启动失败", f"主窗口创建失败：\n{e}")
        return 1

    # 淡出关闭闪屏
    if splash is not None:
        try:
            splash.finish_with_fade(window)
        except Exception:
            try:
                splash.finish(window)
            except Exception:
                pass

    return app.exec()


if __name__ == "__main__":
    sys.exit(main() or 0)

