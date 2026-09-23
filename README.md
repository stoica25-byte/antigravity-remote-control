# 🛸 Antigravity Remote Control Center

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-00a393.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A secure, high-performance web dashboard for accessing the Antigravity IDE and Obsidian Second Brain from mobile devices and remote locations. It creates HTTPS tunnels for secure access on the go.

## ✨ Features
- 🚀 **IDE Remote Access**: Auto-discovers IDE port, proxies gRPC-Web streaming, and rewrites JS/HTML for mobile compatibility.
- 🧠 **Second Brain Integration**: Quick Capture notes directly into Obsidian, with offline resilience, cached fallbacks, and Git sync.
- 🤖 **Agent Session Browser**: Browse Antigravity agent sessions and artifacts seamlessly.
- 🕶️ **Cyber-Noir HUD UI**: A sleek, tactical console design with dark aesthetics.
- 🔑 **JWT Authentication**: Secure login system with built-in rate limiting to prevent abuse.
- ⚙️ **Windows Automation**: One-click launch scripts to start the backend, frontend, and tunnels effortlessly.
- 🌐 **Tunnel Management**: Seamless Cloudflare/Ngrok integration for instant HTTPS access from anywhere.

## 📸 Screenshots

<!-- Add your own screenshots here! Replace the paths below with your actual screenshots -->
<!-- Tip: Press Win+Shift+S to capture, save to docs/screenshots/, then uncomment the lines below -->

<!-- ![Dashboard HUD](docs/screenshots/dashboard.png) -->
<!-- ![Mobile View](docs/screenshots/mobile.png) -->

## 🛠️ Tech Stack

| Component | Technology |
| --- | --- |
| Backend | Python, FastAPI, Uvicorn, httpx (gRPC-Web Proxy) |
| Frontend | Vanilla JS SPA, CSS (Cyber-Noir theme) |
| Authentication | PyJWT |
| Tunnels | Cloudflare Tunnel / Ngrok |

## 📋 Prerequisites
- Windows OS (designed for local hosting)
- Python 3.8+
- Node.js (optional, for some frontend tooling)
- Cloudflare `cloudflared` or `ngrok` installed

## 🚀 Quick Start
```bash
# Clone the repository
git clone https://github.com/stoica25-byte/antigravity-remote-control.git
cd antigravity-remote-control

# Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy example environment file and configure
cp .env.example .env

# Run the backend
uvicorn api.main:app --reload
```

## 📖 Usage Guide
- **Start the app:** Use the provided Windows `.bat` scripts to start the server and tunnels.
- **Log in:** Access the provided HTTPS tunnel URL and log in with your configured JWT credentials.
- **Remote Access:** Use the dashboard to monitor IDE sessions, capture notes, and manage your agent workflows.

## 📂 Project Structure
```text
antigravity-remote-control/
├── api/                  # FastAPI backend
├── frontend/             # Vanilla JS SPA and assets
├── scripts/              # Windows automation (.bat) scripts
├── configs/              # Configurations for tunnels and proxy
├── .env.example          # Environment variables template
├── requirements.txt      # Python dependencies
└── README.md             # This file
```
> **Note:** The `vercel.json` file is experimental. The app requires system access and is primarily designed for local deployment.

## 🔒 Security Considerations
> [!WARNING]
> This application exposes local system services (IDE, file system) to the internet via tunnels. It is intended for **personal, local usage only**. Do not share your tunnel URLs or JWT secrets. Ensure strong passwords and keep your dependencies updated.

## 🤝 Contributing
Contributions are welcome! Please see our [Contributing Guide](CONTRIBUTING.md) for more details.

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👤 Author
**Alex Andrei Stoica**
GitHub: [@stoica25-byte](https://github.com/stoica25-byte)

---

## 🇪🇸 Español

# 🛸 Centro de Control Remoto Antigravity

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-00a393.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Un panel de control web seguro y de alto rendimiento para acceder al IDE Antigravity y al Segundo Cerebro de Obsidian desde dispositivos móviles y ubicaciones remotas. Crea túneles HTTPS para un acceso seguro desde cualquier lugar.

## ✨ Características
- 🚀 **Acceso Remoto al IDE**: Descubre automáticamente el puerto del IDE, actúa como proxy para gRPC-Web y reescribe JS/HTML para compatibilidad móvil.
- 🧠 **Integración con Segundo Cerebro**: Captura rápida de notas directamente en Obsidian, resiliencia sin conexión, alternativas en caché y sincronización con Git.
- 🤖 **Navegador de Sesiones de Agentes**: Explora sesiones y artefactos de los agentes de Antigravity sin problemas.
- 🕶️ **Interfaz Cyber-Noir**: Diseño de consola táctica y elegante con estética oscura.
- 🔑 **Autenticación JWT**: Sistema de inicio de sesión seguro con limitación de tasa integrada para prevenir abusos.
- ⚙️ **Automatización en Windows**: Scripts de lanzamiento con un clic para iniciar el backend, frontend y túneles sin esfuerzo.
- 🌐 **Gestión de Túneles**: Integración perfecta con Cloudflare/Ngrok para acceso HTTPS instantáneo desde cualquier lugar.

## 📸 Capturas de pantalla

<!-- ¡Añade tus propias capturas de pantalla aquí! Reemplaza las rutas con tus capturas reales -->
<!-- Consejo: Pulsa Win+Shift+S para capturar, guarda en docs/screenshots/, y descomenta las siguientes líneas -->

<!-- ![Dashboard HUD](docs/screenshots/dashboard.png) -->
<!-- ![Vista Móvil](docs/screenshots/mobile.png) -->

## 🛠️ Tecnologías

| Componente | Tecnología |
| --- | --- |
| Backend | Python, FastAPI, Uvicorn, httpx (Proxy gRPC-Web) |
| Frontend | Vanilla JS SPA, CSS (Tema Cyber-Noir) |
| Autenticación | PyJWT |
| Túneles | Cloudflare Tunnel / Ngrok |

## 📋 Requisitos previos
- Sistema Operativo Windows (diseñado para alojamiento local)
- Python 3.8+
- Node.js (opcional, para algunas herramientas del frontend)
- Cloudflare `cloudflared` o `ngrok` instalado

## 🚀 Inicio Rápido
```bash
# Clonar el repositorio
git clone https://github.com/stoica25-byte/antigravity-remote-control.git
cd antigravity-remote-control

# Crear y activar un entorno virtual
python -m venv venv
venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Copiar el archivo de entorno de ejemplo y configurar
cp .env.example .env

# Ejecutar el backend
uvicorn api.main:app --reload
```

## 📖 Guía de Uso
- **Iniciar la aplicación:** Utiliza los scripts `.bat` de Windows proporcionados para iniciar el servidor y los túneles.
- **Iniciar sesión:** Accede a la URL del túnel HTTPS proporcionada e inicia sesión con tus credenciales JWT configuradas.
- **Acceso Remoto:** Usa el panel para monitorizar sesiones del IDE, capturar notas y gestionar los flujos de trabajo de tus agentes.

## 📂 Estructura del Proyecto
```text
antigravity-remote-control/
├── api/                  # Backend FastAPI
├── frontend/             # SPA Vanilla JS y recursos
├── scripts/              # Scripts de automatización (.bat) para Windows
├── configs/              # Configuraciones para túneles y proxy
├── .env.example          # Plantilla de variables de entorno
├── requirements.txt      # Dependencias de Python
└── README.md             # Este archivo
```
> **Nota:** El archivo `vercel.json` es experimental. La aplicación requiere acceso al sistema y está diseñada principalmente para despliegue local.

## 🔒 Consideraciones de Seguridad
> [!WARNING]
> Esta aplicación expone servicios locales del sistema (IDE, sistema de archivos) a internet a través de túneles. Está destinada **únicamente para uso personal y local**. No compartas tus URLs de los túneles ni tus secretos JWT. Asegura contraseñas fuertes y mantén tus dependencias actualizadas.

## 🤝 Contribuciones
¡Las contribuciones son bienvenidas! Por favor, consulta nuestra [Guía de Contribución](CONTRIBUTING.md) para más detalles.

## 📄 Licencia
Este proyecto está licenciado bajo la Licencia MIT - consulta el archivo [LICENSE](LICENSE) para más detalles.

## 👤 Autor
**Alex Andrei Stoica**
GitHub: [@stoica25-byte](https://github.com/stoica25-byte)
