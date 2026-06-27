@echo off
REM 智能安全工具柜界面启动脚本 (Windows)

echo ========================================
echo   智能安全工具柜触摸屏界面
echo   宝宝队 ELF 2 / RK3588
echo ========================================
echo.

REM 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: 未找到 Python，请先安装
    pause
    exit /b 1
)

REM 检查 PyQt5
python -c "import PyQt5" >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: 未找到 PyQt5
    echo 请运行: pip install PyQt5
    pause
    exit /b 1
)

echo 环境检查通过
echo 启动界面程序...
echo.

REM 进入脚本目录
cd /d "%~dp0"

REM 启动程序
python main.py

echo.
echo 程序已退出
pause
