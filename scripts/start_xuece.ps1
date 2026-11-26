# 学策引擎 · 一键启动
#
# 设计要点（都是被真实故障逼出来的）：
#   1) 前端和后端**并行**启动，浏览器只等前端就绪（几秒），不再串行干等 3 分钟；
#   2) 后端端口先可用、AI 引擎后台继续加载 —— 所以这里只要求端口通，
#      再用 /api/health 如实报告 AI 引擎状态，不把"引擎慢"说成"服务没起来"；
#   3) 依赖缺失、端口起不来等异常**弹窗提示**：快捷方式带 -WindowStyle Hidden，
#      控制台是看不见的，只写日志等于没有提示；
#   4) 输出到日志文件时带时间戳，配合 PYTHONUNBUFFERED=1 让后端日志实时落盘。

param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
  [int]$FrontendWaitSeconds = 75,
  [int]$BackendWaitSeconds = 90,
  [switch]$NoBrowser
)

$ErrorActionPreference = 'Continue'

$rootPath = (Resolve-Path $Root).Path
$python = Join-Path $rootPath '.venv\Scripts\python.exe'
$frontend = Join-Path $rootPath 'frontend'
$logDir = Join-Path $rootPath 'runtime\logs'
$logFile = Join-Path $logDir 'xuece-launcher.log'
$appUrl = 'http://127.0.0.1:5173/login'

New-Item -ItemType Directory -Path $logDir -Force | Out-Null

function Write-Step([string]$Message) {
  $line = "$(Get-Date -Format o) $Message"
  $line | Out-File -FilePath $logFile -Append -Encoding utf8
  Write-Host $line
}

function Show-Popup([string]$Message, [string]$Title = '学策引擎') {
  # 快捷方式是隐藏窗口启动的，出错必须用弹窗告诉用户，否则就是"点了没反应"。
  try {
    $shell = New-Object -ComObject WScript.Shell
    $shell.Popup($Message, 0, $Title, 48) | Out-Null   # 48 = 感叹号图标
  } catch {
    Write-Host $Message
  }
}

function Test-Port([int]$Port) {
  return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Wait-Port([int]$Port, [int]$TimeoutSeconds) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if (Test-Port $Port) { return $true }
    Start-Sleep -Milliseconds 600
  }
  return $false
}

function Get-AiEngineReport {
  try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8001/api/health' -TimeoutSec 8
    return "ai_engine=$($health.ai_engine_state) detail=$($health.ai_engine_detail)"
  } catch {
    return "health 接口未响应：$($_.Exception.Message)"
  }
}

Write-Step 'launcher started'

# ── 0) 依赖自检：缺什么就明说什么，不要静默失败 ───────────────
$problems = @()
if (-not (Test-Path $python)) {
  $problems += "缺少 Python 虚拟环境：$python"
}
$npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
if (-not $npm) {
  $problems += 'PATH 里找不到 npm.cmd（前端需要 Node.js，装好后重开一次）'
}
if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
  $problems += "缺少前端依赖：$frontend\node_modules（在 frontend 目录执行 npm install）"
}
if ($problems.Count -gt 0) {
  foreach ($p in $problems) { Write-Step "缺少依赖：$p" }
  Show-Popup ("学策引擎无法启动，缺少以下依赖：`n`n" + ($problems -join "`n") + "`n`n日志：$logFile") '学策引擎 · 启动失败'
  exit 1
}

# 让后端的日志立刻落盘（重定向到文件时 Python 默认会缓冲，日志空文件很难排查）
$env:PYTHONUNBUFFERED = '1'
$env:PYTHONIOENCODING = 'utf-8'

# ── 0.5) 演示账号兜底：保证第一屏一定登得进去 ─────────────────
# 真实库里历次调试留下的账号口令无人记得，演示时没有可用登录就打不开系统。
# 本脚本由你双击启动（未被沙箱限制），所以能正常写 runtime\app.db。
$seedScript = Join-Path $rootPath 'scripts\accounts\ensure_demo_account.py'
if (Test-Path $seedScript) {
  $seedOut = & $python $seedScript 2>&1
  $seedLine = ($seedOut | Where-Object { $_ -match '\S' } | Select-Object -Last 1)
  Write-Step "演示账号自检：$seedLine"
}

# ── 1) 后端与前端并行启动，谁都不等谁 ────────────────────────
#
# 注意：不能只看"端口有没有人听"。曾经出现过这样一种情况——8001 上跑着一个
# **写不了数据库**的后端进程（sqlite 报 readonly），端口是通的、/api/health 也
# 回 200，但登录/注册全部 500。脚本看到端口被占就跳过启动，于是用户永远在
# 用一个坏后端，怎么点都登不进去。
# 所以这里要做**健康校验**：能读能写的后端才算数，否则换掉它。
function Test-BackendHealthy {
  try {
    $null = Invoke-RestMethod -Uri 'http://127.0.0.1:8001/api/health' -TimeoutSec 6
  } catch {
    return $false
  }
  # 认证库必须可写：登录要写 auth_tokens，写不进去就是坏后端，必须替换。
  try {
    $body = @{ username = "__launcher_probe__"; password = "probe-not-a-real-password" } | ConvertTo-Json
    Invoke-WebRequest -Uri 'http://127.0.0.1:8001/api/auth/login' -Method POST -Body $body `
      -ContentType 'application/json' -TimeoutSec 8 -UseBasicParsing | Out-Null
  } catch {
    $code = $null
    if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
    # 401 = 后端能正常读到认证库并判定口令错误 —— 这是**健康**的表现。
    # 500 = 内部错误（典型就是数据库不可写）—— 这是坏的。
    return ($code -eq 401)
  }
  return $true
}

function Stop-PortOwner([int]$Port) {
  $pids = netstat -ano | Select-String ":$Port" |
    Where-Object { $_.Line -match 'LISTENING' } |
    ForEach-Object { ($_.Line -split '\s+')[-1] } | Sort-Object -Unique
  foreach ($procId in $pids) {
    Write-Step "停掉占用 $Port 的旧进程 pid=$procId"
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
  }
  Start-Sleep -Seconds 2
}

if (Test-Port 8001) {
  if (Test-BackendHealthy) {
    Write-Step 'backend 已在 8001 运行且通过健康校验，跳过启动'
  } else {
    Write-Step 'backend 端口被占但健康校验不通过（典型：数据库不可写，登录会 500），替换它'
    Stop-PortOwner 8001
  }
}

if (Test-Port 8001) {
  Write-Step 'backend 仍被占用，跳过启动'
} else {
  Start-Process -FilePath $python `
    -ArgumentList @('-m', 'uvicorn', 'api_server.main:app', '--host', '127.0.0.1', '--port', '8001') `
    -WorkingDirectory $rootPath -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logDir 'api_server.log') `
    -RedirectStandardError (Join-Path $logDir 'api_server.err.log')
  Write-Step 'backend 启动中（端口先就绪，AI 引擎后台加载）'
}

if (Test-Port 5173) {
  Write-Step 'frontend 已在 5173 监听，跳过启动'
} else {
  Start-Process -FilePath $npm `
    -ArgumentList @('run', 'dev', '--', '--host', '127.0.0.1') `
    -WorkingDirectory $frontend -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logDir 'frontend.log') `
    -RedirectStandardError (Join-Path $logDir 'frontend.err.log')
  Write-Step 'frontend 启动中'
}

# ── 2) 前端一就绪就打开浏览器（不等后端） ────────────────────
if (Wait-Port 5173 $FrontendWaitSeconds) {
  Write-Step "frontend 已就绪 http://127.0.0.1:5173"
  if (-not $NoBrowser) {
    Start-Process $appUrl
    Write-Step 'browser opened'
  }
} else {
  Write-Step "frontend 在 $FrontendWaitSeconds 秒内未监听 5173"
  Show-Popup ("前端没能在 $FrontendWaitSeconds 秒内启动。`n`n请看日志：`n" + (Join-Path $logDir 'frontend.err.log')) '学策引擎 · 前端启动失败'
  exit 1
}

# ── 3) 再如实报告后端/AI 引擎状态（页面已经打开了，不阻塞） ──
if (Wait-Port 8001 $BackendWaitSeconds) {
  Write-Step "backend 已就绪 `n  $(Get-AiEngineReport)"
  # 登录能不能用，是"系统能不能演示"的第一道门。这里实测一次并明确说出来，
  # 不要等到用户点登录才发现数据库不可写。
  if (Test-BackendHealthy) {
    Write-Step '登录接口自检通过（认证库可写）'
  } else {
    Write-Step '登录接口自检未通过：认证数据库可能不可写'
    Show-Popup ("后端起来了，但登录接口自检没通过——通常是数据库文件不可写。`n`n请看日志：`n" + (Join-Path $logDir 'api_server.err.log')) '学策引擎 · 登录自检未通过'
  }
} else {
  Write-Step "backend 在 $BackendWaitSeconds 秒内未监听 8001"
  Show-Popup ("后端没能在 $BackendWaitSeconds 秒内启动，页面能打开但数据/AI 功能会报错。`n`n请看日志：`n" + (Join-Path $logDir 'api_server.err.log')) '学策引擎 · 后端启动失败'
}

exit 0
