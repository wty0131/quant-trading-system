# 量化系统 — 启动 Jupyter + 自动打开浏览器
# 用法: powershell -ExecutionPolicy Bypass -File start.ps1
#   或 在项目目录直接执行:  .\start.ps1

$port = 8889
$dir  = $PSScriptRoot
$venv = "$dir\.venv\Scripts\Activate.ps1"

Set-Location $dir

# 激活虚拟环境
. $venv

# 先杀掉占用端口的旧进程
$existing = netstat -ano 2>$null | Select-String ":$port " | Select-String "LISTENING"
if ($existing) {
    $pidStr = ($existing -split '\s+')[-1]
    Write-Host "[清理] 关闭旧进程 PID:$pidStr..." -ForegroundColor Yellow
    Stop-Process -Id $pidStr -Force -ErrorAction SilentlyContinue
    Start-Sleep 1
}

# 启动 Jupyter（后台）
$jupyter = Start-Process -FilePath "jupyter" `
    -ArgumentList "notebook", "$dir\notebooks", "--no-browser", "--port=$port" `
    -PassThru `
    -WindowStyle Hidden

Start-Sleep 3

# 找 token
$tokenLine = netstat -ano 2>$null | Select-String ":$port " | Select-String "LISTENING"
$url = "http://localhost:$port/tree"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  量化交易系统 已启动" -ForegroundColor Cyan
Write-Host "  地址: $url" -ForegroundColor White
Write-Host "  PID : $($jupyter.Id)" -ForegroundColor DarkGray
Write-Host "  按 Ctrl+C 或关闭此窗口来停止" -ForegroundColor DarkGray
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 打开浏览器
Start-Process $url

# 保持运行，等用户 Ctrl+C
try {
    while ($true) { Start-Sleep 1 }
}
finally {
    Write-Host "[停止] 正在关闭 Jupyter..." -ForegroundColor Yellow
    Stop-Process -Id $jupyter.Id -Force -ErrorAction SilentlyContinue
}
