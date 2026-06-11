# Estrop 44 — WhatsApp Bot Backend (FastAPI + Redis)

Este es el microservicio de backend para el asistente de reservas del bar musical **Estrop 44**. Está diseñado para interactuar con la **WhatsApp Cloud API (Meta)** de forma asíncrona y gestionar la persistencia temporal de estados en **Upstash Redis**.

---

## 🛠️ Stack Tecnológico
* **Framework:** [FastAPI](https://fastapi.tiangolo.com/) (Python 3.10+)
* **Base de Datos:** [Upstash Redis](https://upstash.com/) (REST Client)
* **Servidor ASGI:** Uvicorn
* **API de WhatsApp:** Meta Cloud API (v19.0)

---

## ⚙️ Variables de Entorno (.env)
Para levantar el servidor necesitas crear un archivo `.env` en este directorio con las siguientes variables:

```env
PORT=8000
ENVIRONMENT=development

# 1. Credenciales de Upstash Redis
UPSTASH_REDIS_REST_URL="https://your-db-name.upstash.io"
UPSTASH_REDIS_REST_TOKEN="your_upstash_rest_token"

# 2. Configuración de Meta Webhook (Tú la defines en la consola de Meta Developers)
WHATSAPP_VERIFY_TOKEN="estrop44cesar"

# 3. WhatsApp Cloud API Credentials
WHATSAPP_TOKEN="EAAXXXX..." # Bearer token permanente o temporal de Meta
PHONE_NUMBER_ID="12345..." # ID del número de WhatsApp emisor en Meta

# 4. Teléfono del Administrador / Dueño para Aprobaciones
OWNER_PHONE="34600000000" # Número al que le llegará la confirmación de la reserva
```

---

## 🚀 Instalación y Servidor Local

1. **Crear y activar el entorno virtual:**
   ```bash
   python -m venv venv
   # En Windows:
   venv\Scripts\activate
   # En macOS/Linux:
   source venv/bin/activate
   ```

2. **Instalar las dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Iniciar el servidor local con recarga en vivo:**
   ```bash
   python -m uvicorn main:app --reload --port 8000
   ```
   El servidor estará disponible en `http://localhost:8000`.

---

## 🔗 Endpoints del Bot
* **`GET /`**: Endpoint de salud del servidor (Sanity Check).
* **`GET /webhook/whatsapp`**: Endpoint utilizado por Meta para verificar el Webhook (Handshake).
* **`POST /webhook/whatsapp`**: Endpoint donde se reciben todos los mensajes y clics de botones del cliente y del dueño para procesar el flujo.
