import os
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Estrop 44 WhatsApp Bot API")

class WhatsAppMessage(BaseModel):
    # Minimal schema for WhatsApp webhook payload
    object: str
    entry: list

@app.get("/")
def read_root():
    return {"message": "Estrop 44 Backend is running. Webhook ready."}

@app.get("/webhook/whatsapp")
def verify_webhook(request: Request):
    """
    Endpoint para verificación del Webhook de Meta (WhatsApp Cloud API)
    """
    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "mock_token_123")
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == verify_token:
            return int(challenge)
        else:
            raise HTTPException(status_code=403, detail="Verification failed")
    
    raise HTTPException(status_code=400, detail="Invalid request")

@app.post("/webhook/whatsapp")
async def handle_whatsapp_message(payload: WhatsAppMessage):
    """
    Endpoint para recibir mensajes de WhatsApp.
    En la fase inicial (mock), solo loguea el mensaje y retorna 200 OK.
    """
    # Aquí iría la lógica para interactuar con Meta API y procesar las intenciones
    print(f"Mock: Mensaje recibido. Payload: {payload.model_dump()}")
    return {"status": "success", "message": "Message received in mock mode"}
