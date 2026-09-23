# ============================================================
# Control Remoto - Script de Inicio Automatico
# Ejecuta esto con doble clic o agrega a Inicio de Windows
# ============================================================

$ProjectDir = $PSScriptRoot

# --- Cargar configuracion desde .env ---
$EnvFile = "$ProjectDir\.env"
$TunnelMethod = "cloudflare_quick"
$CloudflareToken = ""
$NgrokDomain = ""
$PersistentUrl = ""

if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            $parts = $line.Split('=', 2)
            if ($parts.Count -eq 2) {
                $key = $parts[0].Trim()
                $val = $parts[1].Trim()
                if ($key -eq "TUNNEL_METHOD") { $TunnelMethod = $val }
                elseif ($key -eq "CLOUDFLARE_TOKEN") { $CloudflareToken = $val }
                elseif ($key -eq "NGROK_DOMAIN") { $NgrokDomain = $val }
                elseif ($key -eq "PERSISTENT_URL") { $PersistentUrl = $val }
            }
        }
    }
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " CONTROL REMOTO - Iniciando servicios..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# --- Matar procesos anteriores si existen ---
Write-Host "[1/3] Limpiando procesos anteriores..." -ForegroundColor Yellow
Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
    $_.MainWindowTitle -like "*uvicorn*" -or $_.CommandLine -like "*8080*"
} | Stop-Process -Force -ErrorAction SilentlyContinue

Get-Process -Name "cloudflared", "ngrok" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

Remove-Item -Path "$ProjectDir\cloudflared.log" -ErrorAction SilentlyContinue
Remove-Item -Path "$ProjectDir\tunnel_url.txt" -ErrorAction SilentlyContinue

Start-Sleep -Seconds 1

# --- Iniciar FastAPI en ventana separada ---
Write-Host "[2/3] Iniciando servidor FastAPI (puerto 8080)..." -ForegroundColor Yellow
$fastapiArgs = @{
    FilePath         = "cmd.exe"
    ArgumentList     = "/c title CONTROL-REMOTO-API && cd /d `"$ProjectDir`" && venv\Scripts\python -m uvicorn api.index:app --host 0.0.0.0 --port 8080"
    WindowStyle      = "Minimized"
    PassThru         = $true
}
$apiProcess = Start-Process @fastapiArgs
Write-Host "   -> FastAPI PID: $($apiProcess.Id)" -ForegroundColor Green

Start-Sleep -Seconds 3

# --- Iniciar Tunel en ventana separada ---
Write-Host "[3/3] Iniciando tunel ($TunnelMethod)..." -ForegroundColor Yellow
$TunnelCmd = ""
if ($TunnelMethod -eq "cloudflare_token") {
    $TunnelCmd = "cloudflared.exe tunnel run --token $CloudflareToken"
} elseif ($TunnelMethod -eq "ngrok") {
    $TunnelCmd = "ngrok.exe http 8080 --domain=$NgrokDomain"
} else {
    $TunnelCmd = "cloudflared.exe tunnel --url http://localhost:8080 --logfile cloudflared.log"
}

$cfArgs = @{
    FilePath         = "cmd.exe"
    ArgumentList     = "/c title CONTROL-REMOTO-TUNNEL && cd /d `"$ProjectDir`" && $TunnelCmd"
    WindowStyle      = "Minimized"
    PassThru         = $true
}
$cfProcess = Start-Process @cfArgs
Write-Host "   -> Tunel PID: $($cfProcess.Id)" -ForegroundColor Green

# --- Obtener URL del tunel ---
$tunnelUrl = ""
if ($TunnelMethod -eq "cloudflare_token" -or $TunnelMethod -eq "ngrok") {
    $tunnelUrl = $PersistentUrl
} else {
    Write-Host ""
    Write-Host "Esperando URL del tunel (puede tardar ~10 segundos)..." -ForegroundColor Yellow
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Path "$ProjectDir\cloudflared.log") {
            $content = Get-Content "$ProjectDir\cloudflared.log" -Raw -ErrorAction SilentlyContinue
            $match = [regex]::Match($content, 'https://[a-z0-9\-]+\.trycloudflare\.com')
            if ($match.Success) {
                # Tomar el ultimo match
                $allMatches = [regex]::Matches($content, 'https://[a-z0-9\-]+\.trycloudflare\.com')
                $tunnelUrl = $allMatches[$allMatches.Count - 1].Value
                break
            }
        }
    }
}

# --- Guardar URL en archivo ---
if ($tunnelUrl) {
    $tunnelUrl | Out-File -FilePath "$ProjectDir\tunnel_url.txt" -Encoding utf8 -NoNewline
    
    # Autodetectar IP y Hostname
    $LocalIP = "127.0.0.1"
    try {
        $LocalIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } | Select-Object -First 1).IPAddress
    } catch {}
    $Hostname = $env:COMPUTERNAME.ToLower()

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host " SERVICIOS ACTIVOS" -ForegroundColor Green  
    Write-Host "========================================" -ForegroundColor Green
    Write-Host " URL Publica (movil):" -ForegroundColor White
    Write-Host " $tunnelUrl" -ForegroundColor Cyan
    Write-Host ""
    Write-Host " URL Local (misma red WiFi):" -ForegroundColor White
    Write-Host " http://$LocalIP:8080" -ForegroundColor Cyan
    Write-Host " http://$Hostname.local:8080 (URL Estatica Local)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host " Pagina de estado (guarda en favoritos):" -ForegroundColor White
    Write-Host " http://$LocalIP:8080/status" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Green
} else {
    Write-Host "ADVERTENCIA: No se pudo detectar la URL del tunel." -ForegroundColor Red
    Write-Host "Revisa cloudflared.log o la configuracion de tu tunel." -ForegroundColor Red
}

Write-Host ""
Write-Host "Puedes cerrar esta ventana. Los servidores siguen en segundo plano." -ForegroundColor Gray
Read-Host "Presiona ENTER para cerrar"
