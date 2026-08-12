@echo off
REM SmartCommute AI 一键本地启动脚本（Windows）
REM 用法：双击运行，或命令行 scripts\dev.bat
setlocal

set ROOT_DIR=%~dp0..
cd /d "%ROOT_DIR%"

set BACKEND_PORT=8000
set FRONTEND_PORT=5173

echo ==^> SmartCommute AI 启动中...
echo     后端: http://localhost:%BACKEND_PORT%
echo     前端: http://localhost:%FRONTEND_PORT%

if exist ".venv\Scripts\python.exe" (
    set PY=.venv\Scripts\python.exe
) else (
    echo [错误] 未找到 .venv，请先创建虚拟环境并安装依赖：
    echo        python -m venv .venv ^&^& .venv\Scripts\pip install -r backend\requirements.txt
    pause
    exit /b 1
)

echo ==^> 启动后端 (uvicorn, port %BACKEND_PORT%)...
set PYTHONUTF8=1
start "SmartCommute Backend" cmd /k ""%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port %BACKEND_PORT% --app-dir backend"

echo ==^> 等待后端就绪...
timeout /t 4 /nobreak >nul

echo ==^> 启动前端 (vite, port %FRONTEND_PORT%)...
cd frontend
if not exist node_modules (
    echo [提示] 首次运行，正在安装前端依赖...
    call npm install
)
set VITE_PORT=%FRONTEND_PORT%
start "SmartCommute Frontend" cmd /k "npm run dev"

echo.
echo ==^> 已启动。后端窗口 + 前端窗口已在独立终端中打开。
echo    浏览器访问 http://localhost:%FRONTEND_PORT%
echo    关闭对应终端窗口即可停止服务。
endlocal
