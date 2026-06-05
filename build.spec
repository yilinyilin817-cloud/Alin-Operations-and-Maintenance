# AI-NetDiagnoser 打包配置
# 使用 PyInstaller 打包为独立可执行文件

# 打包命令:
# pyinstaller --noconsole --onefile --icon=app.ico --name=AI-NetDiagnoser main.py
#
# 参数说明:
# --noconsole   : 隐藏控制台窗口
# --onefile     : 打包为单个 exe 文件
# --icon        : 设置程序图标
# --name        : 设置输出文件名

# 如果需要包含额外的数据文件（如 style.qss），使用 --add-data:
# pyinstaller --noconsole --onefile --icon=app.ico --name=AI-NetDiagnoser --add-data "app/resources;app/resources" main.py
