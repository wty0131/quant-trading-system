# ====================================
# 量化系统 — Jupyter 一键启动（右键 PowerShell 运行）
# 如果双击不行，右键 → "使用 PowerShell 运行"
# ====================================

$PROJECT_DIR = "C:\Users\wty0131\quant_system"

Set-Location $PROJECT_DIR
if (-not $?) {
    Write-Host "[错误] 无法进入项目目录: $PROJECT_DIR" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  量化交易系统 — Jupyter Notebook" -ForegroundColor Cyan
Write-Host "  项目目录: $PROJECT_DIR" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

& "$PROJECT_DIR\.venv\Scripts\Activate.ps1"
jupyter notebook "$PROJECT_DIR\notebooks\00_data_exploration.ipynb" --no-browser --port=8889
