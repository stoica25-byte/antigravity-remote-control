import os
import secrets as _secrets
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional; env vars can be set externally
import json
import time
import jwt
import requests
import asyncio
import re
import hashlib
import httpx
from typing import List, Optional, Dict, Any

def hash_password(plain_password: str) -> str:
    return hashlib.sha256(plain_password.encode("utf-8")).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if len(hashed_password) != 64:
        # Backward compatibility for plain text passwords (e.g., initial admin123)
        return plain_password == hashed_password
    return hash_password(plain_password) == hashed_password
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Response, HTTPException, Depends, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

# Configuration
SECRET_KEY = os.getenv("JWT_SECRET", _secrets.token_hex(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120

# Default Second Brain URL (local instance)
DEFAULT_SECONDBRAIN_URL = os.getenv("SECONDBRAIN_URL", "http://127.0.0.1:8000")
X_INGEST_TOKEN = os.getenv("INGEST_TOKEN", "")

# Default Antigravity URL (local instance)
# Port is dynamic - Antigravity picks a random high port each launch
DEFAULT_ANTIGRAVITY_URL = os.getenv("ANTIGRAVITY_LS_ADDRESS", "http://127.0.0.1:56523")
if not DEFAULT_ANTIGRAVITY_URL.startswith(("http://", "https://")):
    DEFAULT_ANTIGRAVITY_URL = f"http://{DEFAULT_ANTIGRAVITY_URL}"

# Cache for auto-discovered Antigravity URL (TTL 60s)
_ag_cache: Dict[str, Any] = {"url": "", "ts": 0.0}

def _get_listening_ports() -> List[int]:
    """Get all local TCP ports in LISTENING state using netstat."""
    import subprocess
    ports = []
    try:
        # Run netstat -ano
        res = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=2.0)
        for line in res.stdout.splitlines():
            if "LISTENING" in line:
                # Local address is usually the second token
                parts = line.split()
                if len(parts) >= 2:
                    local_addr = parts[1]
                    if ":" in local_addr:
                        port_str = local_addr.split(":")[-1]
                        try:
                            ports.append(int(port_str))
                        except ValueError:
                            pass
    except Exception:
        pass
    return list(set(ports))

def _find_antigravity_url() -> str:
    """Auto-discover the Antigravity IDE HTTP server.
    Scans only active listening ports to be extremely fast and generic.
    Result is cached for 60 seconds to avoid repeated scans.
    """
    import socket as _socket
    now = time.time()
    # Return cache if fresh
    if _ag_cache["url"] and (now - _ag_cache["ts"]) < 60:
        return _ag_cache["url"]

    # Priority list: try last known port and common ones first
    priority = []
    if _ag_cache["url"]:
        try:
            p = int(_ag_cache["url"].split(":")[-1])
            priority.append(p)
        except Exception:
            pass
    priority += [56523, 58113, 58197, 58203, 58254, 58112, 49702]

    # Get active ports from system to scan
    active_ports = _get_listening_ports()
    # Filter candidate ports (exclude low system ports)
    candidate_ports = [p for p in active_ports if p > 1024]
    
    # Order candidates with priority ports first
    ordered = priority + [p for p in candidate_ports if p not in priority]

    for port in ordered:
        try:
            s = _socket.create_connection(("127.0.0.1", port), timeout=0.15)
            s.close()
        except Exception:
            continue
        try:
            res = requests.get(f"http://127.0.0.1:{port}", timeout=1.0, verify=False)
            text = res.text
            if res.status_code == 200 and ("__APP_CONFIG__" in text or ("Antigravity" in text and "main.js" in text)):
                url = f"http://127.0.0.1:{port}"
                _ag_cache["url"] = url
                _ag_cache["ts"] = now
                return url
        except Exception:
            continue

    # Fallback to last cached URL or default
    return _ag_cache["url"] or DEFAULT_ANTIGRAVITY_URL

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "db_dashboard.json")
CACHE_PATH = os.path.join(BASE_DIR, "db_secondbrain_cache.json")
CLOUDFLARED_LOG = os.path.join(BASE_DIR, "cloudflared.log")
TUNNEL_URL_FILE = os.path.join(BASE_DIR, "tunnel_url.txt")

# Create parent directories if they don't exist
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

app = FastAPI(title="Antigravity Remote Control Backend")

# Enable CORS for cross-origin frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Rate Limiting (Throttling) Middleware
# ---------------------------------------------------------------------------
# Simple in-memory rate limiting: 60 requests per minute per IP
ip_request_history: Dict[str, List[float]] = {}

@app.middleware("http")
async def rate_limiting_middleware(request: Request, call_next):
    # Bypass static files, proxies and gRPC routes to avoid throttling IDE/SecondBrain traffic
    if (request.url.path.startswith(("/frontend", "/api/antigravity/proxy", "/api/secondbrain/proxy", "/exa.language_server_pb.LanguageServerService")) or 
            request.url.path.endswith((".html", ".css", ".js", ".ico", ".png", ".js.map"))):
        return await call_next(request)
        
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    
    # Clean up history older than 60 seconds
    if client_ip in ip_request_history:
        ip_request_history[client_ip] = [t for t in ip_request_history[client_ip] if now - t < 60]
    else:
        ip_request_history[client_ip] = []
        
    # Check limit
    if len(ip_request_history[client_ip]) >= 100:  # 100 requests per minute
        return Response(
            content=json.dumps({"detail": "Rate limit exceeded. Maximum 100 requests per minute."}),
            status_code=429,
            media_type="application/json"
        )
        
    ip_request_history[client_ip].append(now)
    return await call_next(request)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class UserLogin(BaseModel):
    username: str
    password: str

class WidgetConfig(BaseModel):
    id: str
    title: str
    type: str
    settings: Dict[str, Any] = {}
    position: Dict[str, int] = {}

class DashboardConfig(BaseModel):
    widgets: List[WidgetConfig] = []
    theme: str = "cyber-noir"
    log_capture_enabled: bool = False
    workspace_path: Optional[str] = ""

# ---------------------------------------------------------------------------
# Helper functions for Local DB & Cache
# ---------------------------------------------------------------------------
def load_db() -> Dict[str, Any]:
    if not os.path.exists(DB_PATH):
        # Default layout configuration
        default_db = {
            "dashboard": {
                "widgets": [
                    {"id": "w-telemetry", "title": "Telemetría de Grafo", "type": "telemetry", "settings": {}, "position": {"row": 0, "col": 0}},
                    {"id": "w-recent", "title": "Notas Recientes", "type": "recent_notes", "settings": {}, "position": {"row": 0, "col": 1}},
                    {"id": "w-capture", "title": "Captura Rápida", "type": "capture", "settings": {}, "position": {"row": 1, "col": 0}}
                ],
                "theme": "cyber-noir",
                "log_capture_enabled": False,
                "workspace_path": ""
            },
            "users": {
                "admin": {
                    "username": "admin",
                    "password_hash": hash_password(os.getenv("ADMIN_PASSWORD", "admin")),
                    "name": "Administrador Antigravity",
                    "role": "admin"
                }
            }
        }
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump(default_db, f, indent=2)
        return default_db
        
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        # Migration: dynamically remove SCoA debate widget if present in database
        if "dashboard" in data and "widgets" in data["dashboard"]:
            orig_len = len(data["dashboard"]["widgets"])
            data["dashboard"]["widgets"] = [w for w in data["dashboard"]["widgets"] if w.get("id") != "w-debate" and w.get("type") != "scoadebate"]
            if len(data["dashboard"]["widgets"]) != orig_len:
                # Re-align position of w-capture to occupy col 0 if it was col 1
                for w in data["dashboard"]["widgets"]:
                    if w.get("id") == "w-capture" and w.get("position", {}).get("col") == 1:
                        w["position"]["col"] = 0
                # Save migrated database
                with open(DB_PATH, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
        return data
    except Exception:
        return {"dashboard": {"widgets": [], "theme": "cyber-noir"}, "users": {}}

def save_db(data: Dict[str, Any]):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def load_cache() -> Dict[str, Any]:
    if not os.path.exists(CACHE_PATH):
        return {}
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_cache(cache_data: Dict[str, Any]):
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, indent=2)

# ---------------------------------------------------------------------------
# Auth Dependencies
# ---------------------------------------------------------------------------
def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    if not authorization or authorization.strip() in ("", "Bearer"):
        # Fallback for easier demonstration without JWT block
        return {"username": "admin", "role": "admin"}
        
    try:
        token = authorization.split(" ")[1] if " " in authorization else authorization
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Could not validate credentials")
        return {"username": username, "role": payload.get("role", "user")}
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token is invalid or expired")

# ---------------------------------------------------------------------------
# Endpoints: Tunnel URL discovery
# ---------------------------------------------------------------------------
def get_local_ip() -> str:
    import socket
    try:
        # Create a dummy connection to a public IP to find the preferred local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"

def get_tunnel_url_from_log() -> str:
    """Read cloudflared.log and extract the most recent tunnel URL."""
    # First check if tunnel_url.txt contains a custom persistent (non-trycloudflare) URL
    if os.path.exists(TUNNEL_URL_FILE):
        try:
            with open(TUNNEL_URL_FILE, "r", encoding="utf-8-sig") as f:
                url = f.read().strip()
                if url.startswith("https://") and ".trycloudflare.com" not in url:
                    return url
        except Exception:
            pass

    # Parse cloudflared.log first since it's the real-time log of the running tunnel
    if os.path.exists(CLOUDFLARED_LOG):
        try:
            with open(CLOUDFLARED_LOG, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            import re as _re
            matches = _re.findall(r'https://[a-z0-9\-]+\.trycloudflare\.com', content)
            if matches:
                latest_url = matches[-1]
                # Update tunnel_url.txt dynamically so we cache it
                try:
                    with open(TUNNEL_URL_FILE, "w", encoding="utf-8") as tf:
                        tf.write(latest_url)
                except Exception:
                    pass
                return latest_url
        except Exception:
            pass
            
    # Fallback: try the tunnel_url.txt shortcut
    if os.path.exists(TUNNEL_URL_FILE):
        try:
            with open(TUNNEL_URL_FILE, "r", encoding="utf-8-sig") as f:
                url = f.read().strip()
                if url.startswith("https://"):
                    return url
        except Exception:
            pass
    return ""

@app.get("/api/tunnel-url")
async def api_tunnel_url():
    url = get_tunnel_url_from_log()
    local_ip = get_local_ip()
    return {"tunnel_url": url, "local_url": f"http://{local_ip}:8080"}

@app.get("/status", response_class=Response)
async def status_page():
    tunnel_url = get_tunnel_url_from_log()
    ag_port_open = False
    try:
        import socket
        s = socket.create_connection(("127.0.0.1", 56523), timeout=0.5)
        s.close()
        ag_port_open = True
    except Exception:
        pass

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Control Remoto — Estado del Servidor</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0b0c10; color: #f1f3f9; padding: 32px 20px; max-width: 500px; margin: 0 auto; }}
    h1 {{ font-size: 1.4rem; font-weight: 800; margin-bottom: 6px; }}
    .sub {{ color: #64748b; font-size: 0.85rem; margin-bottom: 32px; font-family: monospace; }}
    .card {{ background: #151824; border: 1px solid #1e2235; border-radius: 12px;
              padding: 20px; margin-bottom: 16px; }}
    .label {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: 1px;
               color: #64748b; margin-bottom: 8px; font-weight: 700; }}
    .url-box {{ background: #090a0f; border: 1px solid #1e2235; border-radius: 8px;
                 padding: 14px; font-family: monospace; font-size: 0.85rem;
                 word-break: break-all; color: #7aa2f7; }}
    .open-btn {{ display: block; background: linear-gradient(135deg, #8b5cf6, #3b82f6);
                  color: white; text-align: center; padding: 14px;
                  border-radius: 10px; font-weight: 700; text-decoration: none;
                  font-size: 1rem; margin-top: 12px;
                  box-shadow: 0 0 16px rgba(139,92,246,0.3); }}
    .dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%;
             margin-right: 8px; }}
    .online {{ background: #10b981; box-shadow: 0 0 6px #10b981; }}
    .offline {{ background: #ef4444; box-shadow: 0 0 6px #ef4444; }}
    .status-row {{ display: flex; align-items: center; font-size: 0.85rem;
                    color: #94a3b8; margin-top: 4px; }}
    .note {{ font-size: 0.75rem; color: #475569; margin-top: 10px; text-align: center; }}
  </style>
</head>
<body>
  <h1>🚀 Control Remoto</h1>
  <div class="sub">Antigravity + Second Brain HUD</div>

  <div class="card">
    <div class="label">🌐 URL Pública (Cloudflare Tunnel)</div>
    <div class="url-box">{tunnel_url or "⚠️ Túnel no activo — ejecuta cloudflared"}</div>
    {f'<a class="open-btn" href="{tunnel_url}"  rel="noopener">Abrir Dashboard →</a>' if tunnel_url else ''}
  </div>

  <div class="card">
    <div class="label">Estado de Servicios</div>
    <div class="status-row">
      <span class="dot online"></span> FastAPI Dashboard (puerto 8080) — ONLINE
    </div>
    <div class="status-row" style="margin-top: 8px;">
      <span class="dot {'online' if ag_port_open else 'offline'}"></span>
      Antigravity IDE (puerto 56523) — {'ONLINE' if ag_port_open else 'OFFLINE — abre el editor en el PC'}
    </div>
  </div>

  <div class="note">Guarda esta página en favoritos: <br><code>http://{get_local_ip()}:8080/status</code></div>
</body>
</html>"""
    return Response(content=html, media_type="text/html")

# ---------------------------------------------------------------------------
# Endpoints: Auth
# ---------------------------------------------------------------------------
class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

@app.post("/api/auth/login")
async def login(credentials: UserLogin):
    db = load_db()
    users = db.get("users", {})
    user = users.get(credentials.username)
    
    if not user or not verify_password(credentials.password, user.get("password_hash")):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
        
    # Generate Token
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    token_data = {
        "sub": credentials.username,
        "role": user.get("role", "user"),
        "exp": expire
    }
    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "username": credentials.username,
            "name": user.get("name"),
            "role": user.get("role")
        }
    }

@app.get("/api/auth/profile")
async def profile(current_user: Dict[str, Any] = Depends(get_current_user)):
    db = load_db()
    user = db.get("users", {}).get(current_user["username"], {})
    return {
        "username": current_user["username"],
        "name": user.get("name", "Usuario"),
        "role": current_user["role"]
    }

@app.post("/api/auth/change-password")
async def change_password(req: ChangePasswordRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    db = load_db()
    users = db.get("users", {})
    username = current_user["username"]
    user = users.get(username)
    
    if not user or not verify_password(req.old_password, user.get("password_hash")):
        raise HTTPException(status_code=400, detail="Contraseña actual incorrecta")
        
    db["users"][username]["password_hash"] = hash_password(req.new_password)
    save_db(db)
    return {"status": "success", "message": "Contraseña actualizada correctamente"}

# ---------------------------------------------------------------------------
# Endpoints: Dashboard Layout Configurations
# ---------------------------------------------------------------------------
@app.get("/api/dashboard/config")
async def get_dashboard_config(current_user: Dict[str, Any] = Depends(get_current_user)):
    db = load_db()
    cfg = db.get("dashboard", {})
    # Ensure all keys exist
    if "widgets" not in cfg: cfg["widgets"] = []
    if "theme" not in cfg: cfg["theme"] = "cyber-noir"
    if "log_capture_enabled" not in cfg: cfg["log_capture_enabled"] = False
    if "workspace_path" not in cfg: cfg["workspace_path"] = ""
    return cfg

@app.post("/api/dashboard/config")
async def save_dashboard_config(config: DashboardConfig, current_user: Dict[str, Any] = Depends(get_current_user)):
    db = load_db()
    db["dashboard"] = config.dict()
    save_db(db)
    return {"status": "success", "message": "Configuración guardada"}

# ---------------------------------------------------------------------------
# Endpoints: Agent Sessions & Workspace Files (Artifacts Browser)
# ---------------------------------------------------------------------------
@app.get("/api/antigravity/sessions")
async def get_antigravity_sessions(current_user: Dict[str, Any] = Depends(get_current_user)):
    """List agent sessions from the Antigravity brain directory."""
    brain_dir = os.getenv("ANTIGRAVITY_BRAIN_PATH", os.path.join(os.path.expanduser("~"), ".gemini", "antigravity", "brain"))
    if not os.path.exists(brain_dir):
        return []
    
    sessions = []
    try:
        for folder_name in os.listdir(brain_dir):
            folder_path = os.path.join(brain_dir, folder_name)
            if not os.path.isdir(folder_path) or folder_name == "tempmediaStorage":
                continue
            
            # Gather files in this session
            files = []
            # List files at the root of the folder
            for entry in os.scandir(folder_path):
                if entry.is_file():
                    # Check size and update time
                    stat = entry.stat()
                    files.append({
                        "name": entry.name,
                        "path": entry.name,
                        "size": stat.st_size,
                        "updated_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                    })
            
            # List scratch directory files if exists
            scratch_path = os.path.join(folder_path, "scratch")
            if os.path.exists(scratch_path) and os.path.isdir(scratch_path):
                for entry in os.scandir(scratch_path):
                    if entry.is_file():
                        stat = entry.stat()
                        files.append({
                            "name": f"scratch/{entry.name}",
                            "path": f"scratch/{entry.name}",
                            "size": stat.st_size,
                            "updated_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                        })
            
            # Check modification time of folder or files
            folder_stat = os.stat(folder_path)
            folder_mtime = folder_stat.st_mtime
            
            # Find newest file time
            newest_time = folder_mtime
            if files:
                newest_time = max(os.path.getmtime(os.path.join(folder_path, f["path"])) for f in files)
            
            sessions.append({
                "id": folder_name,
                "updated_at_ts": newest_time,
                "updated_at": datetime.fromtimestamp(newest_time).strftime("%Y-%m-%d %H:%M:%S"),
                "files": files
            })
            
        # Sort sessions by mtime descending (newest first)
        sessions.sort(key=lambda s: s["updated_at_ts"], reverse=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al leer sesiones: {e}")
        
    return sessions

@app.get("/api/antigravity/artifact")
async def get_antigravity_artifact(
    session_id: str, 
    path: str, 
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Retrieve content of an artifact file."""
    # Safety checks
    if ".." in session_id or ".." in path or path.startswith("/") or path.startswith("\\"):
        raise HTTPException(status_code=400, detail="Path inválido")
        
    brain_dir = os.getenv("ANTIGRAVITY_BRAIN_PATH", os.path.join(os.path.expanduser("~"), ".gemini", "antigravity", "brain"))
    file_path = os.path.abspath(os.path.join(brain_dir, session_id, path))
    
    # Ensure it resides inside the brain_dir
    if not file_path.startswith(os.path.abspath(brain_dir)):
        raise HTTPException(status_code=403, detail="Acceso denegado")
        
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
        
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return {
            "name": os.path.basename(file_path),
            "path": path,
            "content": content,
            "size": len(content),
            "updated_at": datetime.fromtimestamp(os.path.getmtime(file_path)).strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/workspace/files")
async def get_workspace_files(
    workspace: Optional[str] = None, 
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """List text and source code files in the workspace project."""
    db = load_db()
    # Determine workspace folder
    ws_path = workspace or db.get("dashboard", {}).get("workspace_path", "")
    if not ws_path or ws_path.strip() == "":
        ws_path = BASE_DIR
        
    ws_path = os.path.abspath(ws_path)
    if not os.path.exists(ws_path) or not os.path.isdir(ws_path):
        ws_path = os.path.abspath(BASE_DIR)
        
    exclude_dirs = {".git", "node_modules", "venv", ".gemini", "__pycache__", ".obsidian", "brain"}
    exclude_files = {".gitignore", "api_server.log", "cloudflared.log", "cloudflared.exe", "db_dashboard.json", "db_secondbrain_cache.json", "tunnel_url.txt"}
    valid_exts = {".html", ".css", ".js", ".py", ".json", ".md", ".txt", ".bat", ".ps1", ".yml", ".yaml", ".sh", ".ini", ".conf", ".vbs", ".txt"}
    
    files = []
    try:
        for root, dirs, filenames in os.walk(ws_path):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for f in filenames:
                if f in exclude_files:
                    continue
                ext = os.path.splitext(f)[1].lower()
                if ext in valid_exts:
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, ws_path).replace("\\", "/")
                    stat = os.stat(full_path)
                    files.append({
                        "name": f,
                        "path": rel_path,
                        "size": stat.st_size,
                        "updated_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                    })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    return {"workspace": ws_path, "files": files}

@app.get("/api/workspace/file/content")
async def get_workspace_file_content(
    path: str, 
    workspace: Optional[str] = None, 
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get content of a file in the workspace."""
    if ".." in path or path.startswith("/") or path.startswith("\\"):
        raise HTTPException(status_code=400, detail="Path inválido")
        
    db = load_db()
    ws_path = workspace or db.get("dashboard", {}).get("workspace_path", "")
    if not ws_path or ws_path.strip() == "":
        ws_path = BASE_DIR
        
    ws_path = os.path.abspath(ws_path)
    file_path = os.path.abspath(os.path.join(ws_path, path))
    
    if not file_path.startswith(ws_path):
        raise HTTPException(status_code=403, detail="Acceso denegado")
        
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
        
    valid_exts = {".html", ".css", ".js", ".py", ".json", ".md", ".txt", ".bat", ".ps1", ".yml", ".yaml", ".sh", ".ini", ".conf", ".vbs", ".txt"}
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in valid_exts:
        raise HTTPException(status_code=400, detail="Tipo de archivo no permitido")
        
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return {
            "name": os.path.basename(file_path),
            "path": path,
            "content": content,
            "size": len(content),
            "updated_at": datetime.fromtimestamp(os.path.getmtime(file_path)).strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Endpoints: Second Brain & Antigravity Proxy & Status
# ---------------------------------------------------------------------------
@app.get("/api/secondbrain/status")
async def get_second_brain_status(target_url: str = Query(DEFAULT_SECONDBRAIN_URL)):
    try:
        # Ping the Second Brain local API
        res = requests.get(f"{target_url}/api/index", timeout=2.0)
        if res.status_code == 200:
            return {"status": "ONLINE", "url": target_url}
    except Exception:
        pass
    return {"status": "OFFLINE", "url": target_url}

class DebugLog(BaseModel):
    message: str
    error: Optional[str] = None

client_logs_memory: List[Dict[str, Any]] = []

@app.post("/api/debug/log")
async def receive_debug_log(log: DebugLog):
    db = load_db()
    is_enabled = db.get("dashboard", {}).get("log_capture_enabled", False)
    if not is_enabled:
        return {"status": "disabled"}
        
    import logging
    logging.getLogger("uvicorn").error(f"[CLIENT DEBUG LOG] Message: {log.message} | Error: {log.error}")
    
    # Store in memory
    log_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "message": log.message,
        "error": log.error
    }
    client_logs_memory.append(log_entry)
    if len(client_logs_memory) > 100:
        client_logs_memory.pop(0)
        
    return {"status": "ok"}

@app.get("/api/debug/logs")
async def get_client_logs(current_user: Dict[str, Any] = Depends(get_current_user)):
    db = load_db()
    is_enabled = db.get("dashboard", {}).get("log_capture_enabled", False)
    return {"logs": client_logs_memory, "enabled": is_enabled}

@app.delete("/api/debug/logs")
async def clear_client_logs(current_user: Dict[str, Any] = Depends(get_current_user)):
    global client_logs_memory
    client_logs_memory = []
    return {"status": "success", "message": "Logs de cliente limpiados"}

@app.get("/diff_worker.js")
async def get_diff_worker(target_url: str = Query(DEFAULT_ANTIGRAVITY_URL)):
    real_url = _find_antigravity_url()
    if real_url:
        target_url = real_url
    try:
        res = requests.get(f"{target_url}/diff_worker.js", verify=False)
        return Response(content=res.content, media_type="application/javascript")
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

@app.get("/audio_processor.js")
async def get_audio_processor(target_url: str = Query(DEFAULT_ANTIGRAVITY_URL)):
    real_url = _find_antigravity_url()
    if real_url:
        target_url = real_url
    try:
        res = requests.get(f"{target_url}/audio_processor.js", verify=False)
        return Response(content=res.content, media_type="application/javascript")
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

@app.get("/api/antigravity/discover")
async def discover_antigravity():
    """Auto-discover the current Antigravity IDE port. Call on page load."""
    url = _find_antigravity_url()
    return {"url": url, "port": int(url.split(":")[-1]) if url else None}

@app.get("/api/antigravity/status")
async def get_antigravity_status(target_url: str = Query(DEFAULT_ANTIGRAVITY_URL)):
    # Always try auto-discovery first - the client sends a stale URL
    real_url = _find_antigravity_url()
    # If discovery found something different, use that instead
    if real_url and real_url != target_url:
        target_url = real_url
    try:
        res = requests.get(target_url, timeout=2.0)
        if res.status_code == 200:
            match = re.search(r'window\.__APP_CONFIG__\s*=\s*(\{.*?\});', res.text)
            config_data = {}
            if match:
                try:
                    config_data = json.loads(match.group(1))
                except Exception:
                    pass
            return {
                "status": "ONLINE",
                "url": target_url,
                "config": config_data
            }
    except Exception:
        pass
    return {"status": "OFFLINE", "url": target_url, "config": {}}

@app.api_route("/api/antigravity/proxy/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def antigravity_proxy(path: str, request: Request, response: Response, target_url: str = Query(DEFAULT_ANTIGRAVITY_URL)):
    # Always use auto-discovered URL for proxy requests
    real_url = _find_antigravity_url()
    if real_url:
        target_url = real_url
    url = f"{target_url}/{path}"
    method = request.method
    
    # Forward client headers, clean up Host and Content-Length to avoid proxy issues
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    
    # Ensure X-CSRF-Token is present for authentication bypass
    if "x-csrf-token" not in {k.lower() for k in headers}:
        headers["X-CSRF-Token"] = os.getenv("ANTIGRAVITY_CSRF_TOKEN", _secrets.token_hex(16))
    
    body = None
    if method in ("POST", "PATCH", "PUT"):
        try:
            body = await request.body()
        except Exception:
            body = None

    try:
        # Forward request to local Antigravity server (disable ssl verification for dynamic dev servers)
        res = requests.request(
            method=method,
            url=url,
            params=dict(request.query_params),
            headers=headers,
            data=body,
            timeout=10.0,
            verify=False
        )
        
        content_type = res.headers.get("Content-Type", "")
        
        # 1. Intercept index HTML and rewrite absolute script paths to relative so they load through this proxy
        if path in ("", "index.html") and "text/html" in content_type:
            html_content = res.text
            v_cache = str(int(time.time()))
            
            # Browser debugging, URL redirection faking & Native Storage bridge emulation script
            debug_script = """<script>
            (function() {
                var prefix = '/api/antigravity/proxy';
                
                // 1. Crear fake location Proxy
                window.__fakeLocation = new Proxy(window.location, {
                    get: function(target, prop) {
                        if (prop === 'pathname') {
                            var val = target.pathname;
                            if (val.indexOf(prefix) === 0) {
                                var subPath = val.substring(prefix.length);
                                return subPath === '' ? '/' : subPath;
                            }
                            return val;
                        }
                        var value = Reflect.get(target, prop);
                        if (typeof value === 'function' && !value.prototype) {
                            return value.bind(target);
                        }
                        return value;
                    },
                    set: function(target, prop, value) {
                        return Reflect.set(target, prop, value);
                    }
                });

                // 2. Crear fake window Proxy
                window.__fakeWindow = new Proxy(window, {
                    get: function(target, prop) {
                        if (prop === 'location') {
                            return window.__fakeLocation;
                        }
                        if (prop === 'window' || prop === 'globalThis' || prop === 'self') {
                            return window.__fakeWindow;
                        }
                        var value = Reflect.get(target, prop);
                        if (typeof value === 'function' && !value.prototype) {
                            return value.bind(target);
                        }
                        return value;
                    },
                    set: function(target, prop, value) {
                        return Reflect.set(target, prop, value);
                    }
                });

                // 3. Fake Location.prototype.pathname como fallback general
                try {
                    var proto = Object.getPrototypeOf(window.location) || window.Location.prototype;
                    var originalToString = proto.toString;
                    
                    Object.defineProperty(proto, 'pathname', {
                        get: function() {
                            var fullUrl = originalToString.call(this);
                            var urlObj = new URL(fullUrl);
                            var val = urlObj.pathname;
                            if (val.indexOf(prefix) === 0) {
                                var subPath = val.substring(prefix.length);
                                return subPath === '' ? '/' : subPath;
                            }
                            return val;
                        },
                        configurable: true
                    });
                } catch(e) {
                    console.error('Failed to patch Location.prototype.pathname:', e);
                }


                try {
                    var originalPushState = window.history.pushState;
                    window.history.pushState = function(state, unused, url) {
                        if (url && typeof url === 'string') {
                            if (url.indexOf(prefix) !== 0 && !url.match(/^(https?:)?\/\//)) {
                                url = prefix + (url.indexOf('/') === 0 ? url : '/' + url);
                            }
                        }
                        return originalPushState.apply(this, arguments);
                    };

                    var originalReplaceState = window.history.replaceState;
                    window.history.replaceState = function(state, unused, url) {
                        if (url && typeof url === 'string') {
                            if (url.indexOf(prefix) !== 0 && !url.match(/^(https?:)?\/\//)) {
                                url = prefix + (url.indexOf('/') === 0 ? url : '/' + url);
                            }
                        }
                        return originalReplaceState.apply(this, arguments);
                    };
                } catch(e) {
                    console.error('Failed to patch History API:', e);
                }

                // 1. Emulate native storage bridge for browser context
                if (!window.nativeStorage) {
                    window.nativeStorage = {
                        getItems: function() {
                            return new Promise(function(resolve) {
                                var items = {};
                                for (var i = 0; i < localStorage.length; i++) {
                                    var k = localStorage.key(i);
                                    if (k && k.indexOf('ag_ns_') === 0) {
                                        var realKey = k.replace('ag_ns_', '');
                                        try {
                                            items[realKey] = JSON.parse(localStorage.getItem(k));
                                        } catch(e) {
                                            items[realKey] = localStorage.getItem(k);
                                        }
                                    }
                                }
                                resolve(items);
                            });
                        },
                        updateItems: function(changes) {
                            return new Promise(function(resolve) {
                                for (var k in changes) {
                                    var v = changes[k];
                                    var storageKey = 'ag_ns_' + k;
                                    if (v === null || v === undefined) {
                                        localStorage.removeItem(storageKey);
                                    } else {
                                        localStorage.setItem(storageKey, JSON.stringify(v));
                                    }
                                }
                                resolve(true);
                            });
                        },
                        onChanged: function(callback) {
                            window.addEventListener('storage', function(e) {
                                if (e.key && e.key.indexOf('ag_ns_') === 0) {
                                    var k = e.key.replace('ag_ns_', '');
                                    var changes = {};
                                    try {
                                        changes[k] = JSON.parse(e.newValue);
                                    } catch(err) {
                                        changes[k] = e.newValue;
                                    }
                                    callback(changes);
                                }
                            });
                            return function() {};
                        }
                    };
                }

                // 2. Browser error overlay debugging
                var div = document.createElement('div');
                div.style.position = 'fixed'; div.style.top = '0'; div.style.left = '0';
                div.style.width = '100%'; div.style.background = 'rgba(220,38,38,0.95)';
                div.style.color = 'white'; div.style.padding = '12px 30px 12px 12px'; div.style.fontFamily = 'monospace';
                div.style.fontSize = '12px'; div.style.zIndex = '999999'; div.style.maxHeight = '150px';
                div.style.overflowY = 'auto'; div.style.display = 'none'; div.id = 'dbg-overlay';
                div.style.pointerEvents = 'none'; // Evitar que bloquee clicks/scrolls en la interfaz
                
                var closeBtn = document.createElement('button');
                closeBtn.innerText = '✕';
                closeBtn.style.position = 'absolute'; closeBtn.style.right = '10px'; closeBtn.style.top = '10px';
                closeBtn.style.background = 'none'; closeBtn.style.border = 'none'; closeBtn.style.color = 'white';
                closeBtn.style.fontSize = '16px'; closeBtn.style.cursor = 'pointer'; closeBtn.style.fontWeight = 'bold';
                closeBtn.style.pointerEvents = 'auto'; // Permitir hacer click en cerrar
                closeBtn.onclick = function() {
                    div.style.display = 'none';
                    // Reset overlay content except the close button
                    div.innerHTML = '';
                    div.appendChild(closeBtn);
                };
                div.appendChild(closeBtn);
                
                function showErr(msg, stack) {
                    if (!msg) return;
                    var msgStr = String(msg);
                    var msgLower = msgStr.toLowerCase();
                    // Filter out standard stream connection drop logs (suspend/resume, background sleep)
                    // and non-critical permission/command/grill-me errors that shouldn't display a red overlay
                    if (msgStr.indexOf('stream error') !== -1 || 
                        msgStr.indexOf('missing trailer') !== -1 || 
                        msgStr.indexOf('Failed to fetch') !== -1 || 
                        msgStr.indexOf('ConnectError') !== -1 ||
                        msgStr.indexOf('Failed to load resource') !== -1 ||
                        msgLower.indexOf('permission') !== -1 ||
                        msgLower.indexOf('denied') !== -1 ||
                        msgLower.indexOf('rejected') !== -1 ||
                        msgLower.indexOf('abort') !== -1 ||
                        msgLower.indexOf('cancel') !== -1 ||
                        msgLower.indexOf('grill') !== -1 ||
                        msgLower.indexOf('command') !== -1 ||
                        msgLower.indexOf('execute') !== -1 ||
                        msgLower.indexOf('run') !== -1 ||
                        msgLower.indexOf('notification') !== -1 ||
                        msgLower.indexOf('languageserverservice') !== -1) {
                        return;
                    }
                    div.style.display = 'block';
                    var p = document.createElement('p');
                    p.innerText = '[ERR] ' + msg + (stack ? ' | Stack: ' + stack : '');
                    div.appendChild(p);
                    fetch('/api/debug/log', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: msg, error: stack })
                    }).catch(function(){});
                }
                
                window.onerror = function(msg, src, line, col, err) {
                    showErr(msg + ' (' + src + ':' + line + ':' + col + ')', err ? err.stack : null);
                    return false;
                };
                window.onunhandledrejection = function(e) {
                    showErr('Unhandled Rejection: ' + e.reason, e.reason ? e.reason.stack : null);
                };
                var _err = console.error;
                console.error = function() {
                    _err.apply(console, arguments);
                    showErr(Array.prototype.slice.call(arguments).join(' '), null);
                };
                
                // Inject style to disable double-tap zoom inside the iframe and prevent auto-zoom on input focus in iOS Safari
                var cssRules = 'html, body, * { touch-action: manipulation !important; } @media screen and (max-width: 768px) { input, select, textarea, [contenteditable], .monaco-editor textarea { font-size: 16px !important; } }';
                if (document.head) {
                    var style = document.createElement('style');
                    style.innerHTML = cssRules;
                    document.head.appendChild(style);
                } else {
                    document.addEventListener('DOMContentLoaded', function() {
                        var style = document.createElement('style');
                        style.innerHTML = cssRules;
                        document.head.appendChild(style);
                    });
                }
                
                document.addEventListener('DOMContentLoaded', function() {
                    document.body.appendChild(div);
                });
            })();
            </script>"""
            
            # Inject debug script right after <head>
            html_content = html_content.replace('<head>', f'<head>{debug_script}')
            
            html_content = html_content.replace('href="/jetbox.css"', f'href="jetbox.css?v={v_cache}"')
            html_content = html_content.replace('src="/tailwindcss.min.js"', f'src="tailwindcss.min.js?v={v_cache}"')
            html_content = html_content.replace('src="/tailwind-config.js"', f'src="tailwind-config.js?v={v_cache}"')
            html_content = html_content.replace('src="/main.js"', f'src="main.js?v={v_cache}"')
            
            response_headers = {
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0"
            }
            return Response(content=html_content, media_type="text/html", status_code=res.status_code, headers=response_headers)
            
        # 2. Intercept main.js and rewrite the hardcoded baseUrl from 127.0.0.1 to window.location.origin
        if path == "main.js" or path.endswith("main.js"):
            js_content = res.text
            
            # Wrap the entire main.js bundle inside an IIFE that shadows location, window, globalThis, and self
            js_content = f"""(function(location, window, globalThis, self) {{
{js_content}
}})(window.__fakeLocation, window.__fakeWindow, window.__fakeWindow, window.__fakeWindow);"""
            
            target_str = "get baseUrl(){return`https://127.0.0.1:${this.port}`}"
            replacement_str = "get baseUrl(){return`${window.location.origin}/api/antigravity/proxy`}"

            
            if target_str in js_content:
                js_content = js_content.replace(target_str, replacement_str)
            else:
                # RegEx replacement fallback
                js_content = re.sub(
                    r'get\s+baseUrl\s*\(\s*\)\s*\{\s*return\s*[`"\']https?://127\.0\.0\.1:?[`"\']\s*\+\s*this\.port\s*\}',
                    replacement_str,
                    js_content
                )
                js_content = re.sub(
                    r'get\s+baseUrl\s*\(\s*\)\s*\{\s*return\s*[`"\']https?://127\.0\.0\.1:\$\{this\.port\}[`"\']\s*\}',
                    replacement_str,
                    js_content
                )
            
            response_headers = {
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0"
            }
            return Response(content=js_content, media_type="application/javascript", status_code=res.status_code, headers=response_headers)

        # 3. Intercept jetbox.css and comment out the raw Tailwind CSS v4 import to prevent browser warnings
        if (path == "jetbox.css" or path.endswith("/jetbox.css") or "jetbox.css" in path) and "text/css" in content_type:
            css_content = res.text
            css_content = css_content.replace('@import "tailwindcss";', '/* @import "tailwindcss"; */')
            
            response_headers = {
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0"
            }
            return Response(content=css_content, media_type="text/css", status_code=res.status_code, headers=response_headers)

        # 4. For any other request, output raw content (prevents image/asset corruption)
        exclude_headers = ("content-encoding", "content-length", "transfer-encoding", "connection")
        res_headers = {k: v for k, v in res.headers.items() if k.lower() not in exclude_headers}
        
        return Response(content=res.content, status_code=res.status_code, media_type=content_type, headers=res_headers)
        
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Servidor local de Antigravity está desconectado ({e})."
        )

@app.api_route("/api/secondbrain/proxy/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def second_brain_proxy(path: str, request: Request, response: Response, target_url: str = Query(DEFAULT_SECONDBRAIN_URL)):
    url = f"{target_url}/api/{path}"
    
    # Query parameters
    params = dict(request.query_params)
    if "target_url" in params:
        del params["target_url"] # Clean parameter used for proxy routing
        
    method = request.method
    headers = {
        "Content-Type": "application/json"
    }
    
    # Read body for POST/PATCH
    body = None
    if method in ("POST", "PATCH", "PUT"):
        try:
            body = await request.json()
        except Exception:
            body = None

    try:
        # Try requesting the actual Second Brain
        if method == "GET":
            res = requests.get(url, params=params, headers=headers, timeout=4.0)
        elif method == "POST":
            # Aumentar timeout para sincronización remota con GitHub
            t_out = 60.0 if "git/sync" in path else 5.0
            res = requests.post(url, params=params, json=body, headers=headers, timeout=t_out)
        elif method == "PATCH":
            res = requests.patch(url, params=params, json=body, headers=headers, timeout=5.0)
        elif method == "DELETE":
            res = requests.delete(url, params=params, headers=headers, timeout=4.0)
        else:
            raise HTTPException(status_code=405, detail="Method not allowed")
            
        # If response was successful, cache it (for GET requests only)
        if res.status_code == 200 and method == "GET":
            cache = load_cache()
            cache[path] = {
                "timestamp": time.time(),
                "data": res.json()
            }
            save_cache(cache)
            
        # Return response
        response.status_code = res.status_code
        return res.json()

    except Exception as e:
        # FALLBACK OBLIGATORIO: If disconnected/failed, search in local cache
        if method == "GET":
            cache = load_cache()
            if path in cache:
                cached_item = cache[path]
                response.headers["X-Offline-Fallback"] = "True"
                response.headers["Cache-Control"] = "no-cache"
                return {
                    "is_cached": True,
                    "cached_at": datetime.fromtimestamp(cached_item["timestamp"]).strftime("%Y-%m-%d %H:%M:%S"),
                    "data": cached_item["data"]
                }
                
        # If no cache or writing request, return error
        raise HTTPException(
            status_code=503,
            detail=f"Second Brain local está desconectado ({e}). No hay datos en caché para esta ruta."
        )



# ---------------------------------------------------------------------------
# gRPC-Web Proxy for Antigravity Language Server Service
# ---------------------------------------------------------------------------
@app.api_route("/exa.language_server_pb.LanguageServerService/{path:path}", methods=["POST", "OPTIONS"])
async def antigravity_grpc_proxy(path: str, request: Request, response: Response, target_url: str = Query(DEFAULT_ANTIGRAVITY_URL)):
    real_url = _find_antigravity_url()
    if real_url:
        target_url = real_url
    url = f"{target_url}/exa.language_server_pb.LanguageServerService/{path}"
    method = request.method
    
    # Forward headers (removing host)
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    
    # Read raw body
    body = await request.body()
    
    try:
        # Use httpx.AsyncClient with timeout=None to prevent premature read timeouts on streaming subscriptions.
        # We stream the response content chunk-by-chunk without buffering using aiter_bytes().
        client = httpx.AsyncClient(timeout=None, verify=False)
        req = client.build_request(
            method=method,
            url=url,
            headers=headers,
            content=body
        )
        res = await client.send(req, stream=True)
        
        exclude_headers = ("content-encoding", "content-length", "transfer-encoding", "connection")
        res_headers = {k: v for k, v in res.headers.items() if k.lower() not in exclude_headers}
        
        # Explicitly expose gRPC-Web headers via CORS so the browser connect/grpc-web library can read status codes and trailers
        res_headers["Access-Control-Expose-Headers"] = "grpc-status, grpc-message, grpc-status-details-bin"
        
        async def stream_response():
            try:
                async for chunk in res.aiter_bytes():
                    if chunk:
                        yield chunk
            except Exception:
                pass
            finally:
                await res.aclose()
                await client.aclose()
                
        return StreamingResponse(
            stream_response(),
            status_code=res.status_code,
            media_type=res.headers.get("Content-Type"),
            headers=res_headers
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Error al conectar con el servicio gRPC local de Antigravity ({e})."
        )

# ---------------------------------------------------------------------------
# Serve Static Frontend Files
# ---------------------------------------------------------------------------
# Serve static frontend files
frontend_path = os.path.join(BASE_DIR, "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
