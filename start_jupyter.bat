@echo off
:: ====================================
:: 量化系统 — Jupyter 一键启动（双击运行）
:: ====================================

set PROJECT_DIR=C:\Users\wty0131\quant_system

cd /d "%PROJECT_DIR%"
if %errorlevel% neq 0 (
    echo [错误] 无法进入项目目录: %PROJECT_DIR%
    pause
    exit /b 1
)

echo ========================================
echo   量化交易系统 — Jupyter Notebook
echo   项目目录: %PROJECT_DIR%
echo ========================================
echo.

call "%PROJECT_DIR%\.venv\Scripts\activate.bat"
if %errorlevel% neq 0 (
    echo [错误] 虚拟环境激活失败，请确认已执行过安装步骤
    pause
    exit /b 1
)

echo [启动] 正在启动 Jupyter Notebook...
echo [提示] 请将下面打印的 http://localhost 链接复制到浏览器打开
echo [提示] 按 Ctrl+C 可停止服务
echo.

jupyter notebook "%PROJECT_DIR%\notebooks\00_data_exploration.ipynb" --no-browser --port=8889

pause
