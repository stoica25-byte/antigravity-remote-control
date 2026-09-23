@echo off
setlocal enabledelayedexpansion
title CONTROL REMOTO - LANZADOR MULTISERVER
color 0B
echo ========================================================
echo   INICIANDO SERVICIOS - CONTROL REMOTO + SECOND BRAIN
echo ========================================================
echo.

set "ProjectDir=%~dp0"
rem Remove trailing backslash from %~dp0
if "%ProjectDir:~-1%"=="\" set "ProjectDir=%ProjectDir:~0,-1%"
rem SecondBrainDir: adjust this path to your Second Brain location
set "SecondBrainDir=%USERPROFILE%\Downloads\seond-brain"

rem --- Cargar .env si existe ---
set "TUNNEL_METHOD=cloudflare_quick"
set "CLOUDFLARE_TOKEN="
set "NGROK_DOMAIN="
set "PERSISTENT_URL="

if exist "%ProjectDir%\.env" (
    for /f "usebackq tokens=1,2* delims==" %%a in ("%ProjectDir%\.env") do (
        set "key=%%a"
        set "val=%%b"
        if not "!key:~0,1!"=="#" (
            set "key=!key: =!"
            for /f "tokens=* delims= " %%i in ("!val!") do set "val=%%i"
            if "!key!"=="TUNNEL_METHOD" set "TUNNEL_METHOD=!val!"
            if "!key!"=="CLOUDFLARE_TOKEN" set "CLOUDFLARE_TOKEN=!val!"
            if "!key!"=="NGROK_DOMAIN" set "NGROK_DOMAIN=!val!"
            if "!key!"=="PERSISTENT_URL" set "PERSISTENT_URL=!val!"
        )
    )
)

echo [1/4] Finalizando procesos anteriores...
rem Matar cloudflared
taskkill /F /IM cloudflared.exe >nul 2>&1
taskkill /F /IM ngrok.exe >nul 2>&1

if exist "%ProjectDir%\cloudflared.log" del "%ProjectDir%\cloudflared.log" >nul 2>&1
if exist "%ProjectDir%\tunnel_url.txt" del "%ProjectDir%\tunnel_url.txt" >nul 2>&1

rem Buscar y matar python.exe que ejecuten api.index o main:app
powershell -Command "Get-CimInstance -ClassName Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and ($_.CommandLine -like '*api.index*' -or $_.CommandLine -like '*main:app*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

ping 127.0.0.1 -n 3 >nul

echo [1.5/4] Verificando disponibilidad de puertos...
set "Port8080PID="
set "Port8000PID="
for /f "tokens=5" %%a in ('netstat -aon ^| findstr LISTENING ^| findstr :8080') do set "Port8080PID=%%a"
for /f "tokens=5" %%a in ('netstat -aon ^| findstr LISTENING ^| findstr :8000') do set "Port8000PID=%%a"

if not "!Port8080PID!"=="" (
    set "Port8080Name=Desconocido"
    for /f "usebackq tokens=*" %%p in (`powershell -NoProfile -Command "Get-Process -Id !Port8080PID! -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name"`) do set "Port8080Name=%%p"
    echo [ADVERTENCIA] El puerto 8080 sigue ocupado por "!Port8080Name!" [PID: !Port8080PID!].
    echo              El servidor FastAPI puede fallar al iniciar si no se liberó correctamente.
)
if not "!Port8000PID!"=="" (
    set "Port8000Name=Desconocido"
    for /f "usebackq tokens=*" %%p in (`powershell -NoProfile -Command "Get-Process -Id !Port8000PID! -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name"`) do set "Port8000Name=%%p"
    echo [ADVERTENCIA] El puerto 8000 sigue ocupado por "!Port8000Name!" [PID: !Port8000PID!].
    echo              El servidor Second Brain puede fallar al iniciar si no se liberó correctamente.
)
echo.

echo [2/4] Iniciando FastAPI Control Remoto (Puerto 8080)...
start "CONTROL-REMOTO-API" /min cmd.exe /c "cd /d %ProjectDir% && venv\Scripts\python -m uvicorn api.index:app --host 0.0.0.0 --port 8080"

echo [3/4] Iniciando Second Brain Local (Puerto 8000)...
start "SECOND-BRAIN-API" /min cmd.exe /c "cd /d %SecondBrainDir%\backend && ..\venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8000"

echo Esperando a que arranquen los servidores...
ping 127.0.0.1 -n 6 >nul

echo [4/4] Iniciando Tunel (%TUNNEL_METHOD%)...
if "%TUNNEL_METHOD%"=="cloudflare_token" (
    start "CF-TUNNEL" /min cmd.exe /c "cd /d %ProjectDir% && cloudflared.exe tunnel run --token %CLOUDFLARE_TOKEN%"
    set "TunnelURL=%PERSISTENT_URL%"
) else if "%TUNNEL_METHOD%"=="ngrok" (
    start "CF-TUNNEL" /min cmd.exe /c "cd /d %ProjectDir% && ngrok.exe http 8080 --domain=%NGROK_DOMAIN%"
    set "TunnelURL=%PERSISTENT_URL%"
) else (
    if exist "%ProjectDir%\cloudflared.log" del "%ProjectDir%\cloudflared.log" >nul 2>&1
    start "CF-TUNNEL" /min cmd.exe /c "cd /d %ProjectDir% && cloudflared.exe tunnel --url http://localhost:8080 --logfile cloudflared.log"
    echo Esperando enlace del tunel...
    ping 127.0.0.1 -n 9 >nul
    powershell -Command "Select-String -Path '%ProjectDir%\cloudflared.log' -Pattern 'https://[a-z0-9\-]+\.trycloudflare\.com' | Select-Object -Last 1 | ForEach-Object { $_.Matches.Value }" > temp_url.txt
    set /p TunnelURL=<temp_url.txt
    del temp_url.txt >nul 2>&1
)

rem Autodetectar la IP local para acceso wifi directo
set "LocalIP="
for /f "usebackq tokens=*" %%i in (`powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | Select-Object -First 1).IPAddress"`) do set "LocalIP=%%i"

echo.
echo ========================================================
echo                SERVICIOS ONLINE
echo ========================================================
echo.
echo  - FastAPI Remote Control: http://localhost:8080
if not "!LocalIP!"=="" (
    echo  - Acceso Red Local [WiFi]: http://!LocalIP!:8080
    echo  - URL Estatica Local:      http://%COMPUTERNAME%.local:8080
)
echo  - Second Brain API:      http://localhost:8000
echo.

if "!TunnelURL!"=="" goto no_tunnel
echo  - URL PUBLICA (MOVIL): !TunnelURL!
echo.
<nul set /p=!TunnelURL!> "%ProjectDir%\tunnel_url.txt"
goto end_tunnel

:no_tunnel
echo  [!] No se pudo obtener la URL publica automaticamente.
echo      Revisa '%ProjectDir%\cloudflared.log'

:end_tunnel
echo ========================================================
echo.
echo Presiona cualquier tecla para salir (los servidores seguiran en segundo plano).
pause >nul
