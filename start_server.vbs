' ControlRemoto - Lanzador via WMI (independiente del arbol de Antigravity)
' Place in Windows Startup folder or run directly

Dim dir, sbDir, fso2
Set fso2 = CreateObject("Scripting.FileSystemObject")
dir = fso2.GetParentFolderName(WScript.ScriptFullName)
sbDir = CreateObject("WScript.Shell").ExpandEnvironmentStrings("%USERPROFILE%") & "\Downloads\seond-brain"
Set fso2 = Nothing

Dim wmi
Set wmi = GetObject("winmgmts:{impersonationLevel=impersonate}!\\.\root\cimv2")

On Error Resume Next

' Matar cloudflared anterior si existe
Dim procs
Set procs = wmi.ExecQuery("SELECT * FROM Win32_Process WHERE Name = 'cloudflared.exe'")
For Each proc In procs
    proc.Terminate()
Next

' Matar uvicorn del Second Brain anterior si existe (que ejecuta main:app)
Dim sbProcs
Set sbProcs = wmi.ExecQuery("SELECT * FROM Win32_Process WHERE Name = 'python.exe' AND CommandLine LIKE '%main:app%'")
For Each proc In sbProcs
    proc.Terminate()
Next

' Matar FastAPI del Control Remoto anterior si existe (que ejecuta api.index)
Dim crProcs
Set crProcs = wmi.ExecQuery("SELECT * FROM Win32_Process WHERE Name = 'python.exe' AND CommandLine LIKE '%api.index%'")
For Each proc In crProcs
    proc.Terminate()
Next

' Esperar 1 segundo
WScript.Sleep 1000

' Preparar inicio oculto
Dim processClass
Set processClass = wmi.Get("Win32_Process")
Dim startup
Set startup = wmi.Get("Win32_ProcessStartup")
Dim startupParams
Set startupParams = startup.SpawnInstance_()
startupParams.ShowWindow = 0 ' SW_HIDE

' 1. Lanzar FastAPI Control Remoto (puerto 8080)
Dim pid1
processClass.Create "cmd.exe /c cd /d """ & dir & """ && venv\Scripts\python -m uvicorn api.index:app --host 0.0.0.0 --port 8080 >> api_server.log 2>&1", dir, startupParams, pid1

' 2. Lanzar Second Brain (puerto 8000)
Dim pid3
processClass.Create "cmd.exe /c cd /d """ & sbDir & "\backend"" && ..\venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8000 >> ..\secondbrain_server.log 2>&1", sbDir & "\backend", startupParams, pid3

' Esperar 3 segundos antes de lanzar el túnel
WScript.Sleep 3000

' Cargar configuración desde .env
Dim tunnelMethod, cfToken, ngDomain, persUrl
tunnelMethod = "cloudflare_quick"
cfToken = ""
ngDomain = ""
persUrl = ""

Dim fso, envFile, envStream, line, parts, key, val
Set fso = CreateObject("Scripting.FileSystemObject")
envFile = dir & "\.env"
If fso.FileExists(envFile) Then
    Set envStream = fso.OpenTextFile(envFile, 1)
    Do Until envStream.AtEndOfStream
        line = Trim(envStream.ReadLine)
        If line <> "" And Left(line, 1) <> "#" Then
            If InStr(line, "=") > 0 Then
                parts = Split(line, "=", 2)
                key = Trim(parts(0))
                val = Trim(parts(1))
                If key = "TUNNEL_METHOD" Then tunnelMethod = val
                If key = "CLOUDFLARE_TOKEN" Then cfToken = val
                If key = "NGROK_DOMAIN" Then ngDomain = val
                If key = "PERSISTENT_URL" Then persUrl = val
            End If
        End If
    Loop
    envStream.Close
End If

' Escribir url persistente si es necesario
If tunnelMethod = "cloudflare_token" Or tunnelMethod = "ngrok" Then
    Dim txtStream
    Set txtStream = fso.CreateTextFile(dir & "\tunnel_url.txt", True, False)
    txtStream.Write persUrl
    txtStream.Close
End If

' 3. Lanzar Tunnel
Dim cmdLine, pid2
If tunnelMethod = "cloudflare_token" Then
    cmdLine = "cmd.exe /c cd /d """ & dir & """ && cloudflared.exe tunnel run --token " & cfToken
ElseIf tunnelMethod = "ngrok" Then
    cmdLine = "cmd.exe /c cd /d """ & dir & """ && ngrok.exe http 8080 --domain=" & ngDomain
Else
    cmdLine = "cmd.exe /c cd /d """ & dir & """ && cloudflared.exe tunnel --url http://localhost:8080 --logfile cloudflared.log"
End If

processClass.Create cmdLine, dir, startupParams, pid2

Set processClass = Nothing
Set startupParams = Nothing
Set fso = Nothing
Set wmi = Nothing
