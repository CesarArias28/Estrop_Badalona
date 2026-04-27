Estrop 44 - Bar Musical & Eventos

Plataforma integral (Landing Page + WhatsApp Webhook) para **Estrop 44**, diseñada para optimizar la conversión de reservas y eventos privados.

Este proyecto utiliza una arquitectura de Monorepo desacoplada, priorizando el rendimiento extremo en el cliente y la automatización de reservas en el servidor.

---

Arquitectura y Stack Tecnológico

El proyecto está dividido en dos microservicios principales:

1. Frontend 
Una Landing Page estática ultrarrápida (SSG) diseñada para capturar la atención y dirigir al usuario hacia la reserva.
- **Framework:** [Astro](https://astro.build/)
- **Estilos:** Tailwind CSS + Glassmorphism y diseño Neón.
- **Interactividad:** React & Vanilla JS.
- **Features clave:** Lightbox In-Page para Instagram Reels, Showroom de experiencias dinámico, botón de WhatsApp flotante inteligente (Mobile).

2. Backend
Servidor ligero y asíncrono para gestionar las comunicaciones oficiales con Meta.
- **Framework:** [FastAPI](https://fastapi.tiangolo.com/) (Python 3)
- **Servidor:** Uvicorn
- **Features clave:** Endpoint de validación Webhook de Meta, enrutador de mensajes entrantes de WhatsApp Cloud API.

---

Entorno de Desarrollo Local

Para levantar el proyecto en tu máquina, abre dos terminales separadas:

### Terminal 1: Iniciar el Frontend (Web)
```bash
cd frontend
npm install
npm run dev
```
La web estará disponible en `http://localhost:4321`.

### Terminal 2: Iniciar el Backend (Bot de WhatsApp)
```bash
cd backend
python -m venv venv
venv\Scripts\activate   # Activar entorno virtual en Windows
pip install -r requirements.txt
python -m uvicorn src.main:app --reload
```
El servidor de validación estará en `http://localhost:8000`.

### Terminal 3: Túnel para Meta (Solo testing local)
```bash
ngrok http 8000
```
Copia la URL segura `https://....ngrok-free.app/webhook` y pégala en la configuración de la Meta Developer App.

---

Guía de Despliegue en Producción

Debido a las naturalezas distintas de los servicios (Estático vs Proceso Continuo), se despliegan en infraestructuras separadas:

### 1. Desplegar Frontend (Recomendado: Vercel)
1. Conecta el repositorio de GitHub a Vercel.
2. En la configuración, establece el **Root Directory** como `frontend`.
3. Selecciona **Astro** como framework.
4. Deploy.

### 2. Desplegar Backend (Recomendado: Render)
1. Crea un Web Service en Render conectado a GitHub.
2. Configura el **Root Directory** como `backend`.
3. **Runtime:** `Python 3`
4. **Build Command:** `pip install -r requirements.txt`
5. **Start Command:** `uvicorn src.main:app --host 0.0.0.0 --port $PORT`
6. Añade las variables de entorno (`WHATSAPP_VERIFY_TOKEN`, etc.).
7. Deploy. Una vez levantado, usa la nueva URL en Meta.

---

Notas sobre el Feed de Instagram
La sección "Live from Estrop" (`LiveFromEstrop.astro`) está configurada para renderizar de manera asimétrica un **Bento Grid** o **Carrusel** con soporte para vídeo In-Page.
Actualmente cuenta con un Mock estructural. Para habilitar la sincronización real con la cuenta del bar:
1. Configura el puente API vía **Behold.so**.
2. Descomenta las líneas de `fetch` en el archivo `.astro` y pega la URL proporcionada.

