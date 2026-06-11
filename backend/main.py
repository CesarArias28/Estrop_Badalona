import os
import json
import uuid
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from upstash_redis import Redis
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Estrop WhatsApp Bot API")

redis = Redis(
    url=os.getenv("UPSTASH_REDIS_REST_URL"),
    token=os.getenv("UPSTASH_REDIS_REST_TOKEN")
)

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "estrop44cesar")
OWNER_PHONE = os.getenv("OWNER_PHONE")

ROOMS = {
    "sala1": {"name": "Sala 1", "min_spend": 300, "options": {
        "s1_12": {"title": "2 Consumiciones (12€)", "price": 12},
        "s1_22": {"title": "Libre Vi/Cerv (22€)", "price": 22},
        "s1_32": {"title": "Libre Combinados(32€)", "price": 32}
    }},
    "sala2": {"name": "Sala 2", "min_spend": 500, "options": {
        "s2_15": {"title": "2 Consumiciones (15€)", "price": 15},
        "s2_25": {"title": "Libre Vi/Cerv (25€)", "price": 25},
        "s2_35": {"title": "Libre Combinados(35€)", "price": 35}
    }}
}

def get_state(phone: str) -> dict:
    raw = redis.get(f"state:{phone}")
    if raw:
        return json.loads(raw)
    return {"state": "START", "data": {}}

def save_state(phone: str, state: dict):
    redis.setex(f"state:{phone}", 7200, json.dumps(state))

def clear_state(phone: str):
    redis.delete(f"state:{phone}")

async def send_wa(to: str, data: dict):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print(f"MOCK -> {to}: {data}")
        return
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to, **data}
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(url, headers=headers, json=payload)
        print(f"Meta API -> {r.status_code}: {r.text[:200]}")

async def send_text(to: str, text: str):
    await send_wa(to, {"type": "text", "text": {"body": text}})

async def send_list(to: str, body: str, sections: list):
    await send_wa(to, {"type": "interactive", "interactive": {
        "type": "list", "body": {"text": body},
        "action": {"button": "Ver Salas y Tickets", "sections": sections}
    }})

async def send_buttons(to: str, body: str, buttons: list):
    await send_wa(to, {"type": "interactive", "interactive": {
        "type": "button", "body": {"text": body},
        "action": {"buttons": [{"type": "reply", "reply": {"id": b["id"], "title": b["title"]}} for b in buttons]}
    }})

async def process(phone: str, text: str, interactive: dict = None):
    user = get_state(phone)
    state = user["state"]
    data = user["data"]

    if text and text.lower().strip() in ["cancelar", "reiniciar", "hola", "inicio"]:
        user = {"state": "START", "data": {}}
        state = "START"

    if state == "START":
        await send_text(phone, "¡Hola! 👋 Soy el asistente de *Estrop*. Vamos a gestionar tu reserva. 🥳\n\n¿Para cuántas personas buscas sala? Escribe solo el número.")
        save_state(phone, {"state": "WAITING_PEOPLE", "data": {}})

    elif state == "WAITING_PEOPLE":
        if not text.strip().isdigit():
            await send_text(phone, "Por favor, escribe solo el número (ejemplo: 12).")
            return
        data["people"] = int(text.strip())
        await send_text(phone, "¿Para qué día y hora quieres reservar?\n\nEjemplo: *Sábado 25/05 a las 19:30*")
        save_state(phone, {"state": "WAITING_DATE", "data": data})

    elif state == "WAITING_DATE":
        data["date"] = text.strip()
        sections = [{"title": r["name"][:24], "rows": [
            {"id": oid, "title": o["title"][:24], "description": f"{o['price']}€/pers"}
            for oid, o in r["options"].items()
        ]} for r in ROOMS.values()]
        await send_list(phone, f"Perfecto, {data['people']} personas el {data['date']}.\n\nElige sala y tipo de acceso:", sections)
        save_state(phone, {"state": "WAITING_ROOM", "data": data})

    elif state == "WAITING_ROOM":
        if not interactive or interactive.get("type") != "list_reply":
            await send_text(phone, "Usa el botón *'Ver Salas y Tickets'* para elegir.")
            return
        sid = interactive["list_reply"]["id"]
        rid = "sala1" if sid.startswith("s1") else "sala2"
        room = ROOMS[rid]
        opt = room["options"][sid]
        data.update({"room_name": room["name"], "option_title": opt["title"],
                     "total": opt["price"] * data["people"], "min_spend": room["min_spend"]})
        msg = (f"Has elegido *{room['name']}* — *{opt['title']}*\n\n"
               f"👥 {data['people']} personas → Total tickets: *{data['total']}€*\n"
               f"⚠️ Consumo mínimo: *{room['min_spend']}€*\n\n"
               "📌 Horario: 18:30–23:00h. A las 23h abrimos al público pero la fiesta sigue 🕺\n"
               "🚫 No se permite bebida del exterior.\n\n"
               "¿Tienes alguna petición especial (cumpleaños, decoración...)? Escríbela o di *Ninguna*.")
        await send_text(phone, msg)
        save_state(phone, {"state": "WAITING_NOTES", "data": data})

    elif state == "WAITING_NOTES":
        data["notes"] = text.strip()
        summary = (f"Revisa tu solicitud:\n\n"
                   f"👥 Personas: {data['people']}\n"
                   f"📅 Fecha: {data['date']}\n"
                   f"📍 Sala: {data['room_name']} — {data['option_title']}\n"
                   f"📝 Notas: {data['notes']}\n\n¿Confirmamos?")
        await send_buttons(phone, summary, [
            {"id": "confirm", "title": "Confirmar Reserva"},
            {"id": "edit", "title": "Editar"}
        ])
        save_state(phone, {"state": "WAITING_CONFIRMATION", "data": data})

    elif state == "WAITING_CONFIRMATION":
        if not interactive or interactive.get("type") != "button_reply":
            await send_text(phone, "Usa los botones para confirmar o editar.")
            return
        if interactive["button_reply"]["id"] == "edit":
            clear_state(phone)
            await send_text(phone, "¡Vale! Escribe *Hola* para empezar de nuevo. 😊")
        else:
            # Generar ID único de reserva
            res_id = uuid.uuid4().hex[:6].upper()
            
            # Guardar detalles en Redis
            res_data = {
                "client_phone": phone,
                "people": data["people"],
                "date": data["date"],
                "room_name": data["room_name"],
                "option_title": data["option_title"],
                "total": data["total"],
                "min_spend": data["min_spend"],
                "notes": data.get("notes", "Ninguna")
            }
            redis.setex(f"res:{res_id}", 172800, json.dumps(res_data)) # Expira en 48 horas
            
            # Enviar solicitud de aprobación al dueño
            owner_msg = (
                f"🔔 *NUEVA SOLICITUD DE RESERVA ({res_id})*\n\n"
                f"👤 *Cliente:* +{phone}\n"
                f"👥 *Personas:* {res_data['people']}\n"
                f"📅 *Fecha:* {res_data['date']}\n"
                f"📍 *Sala:* {res_data['room_name']} — {res_data['option_title']}\n"
                f"💰 *Total:* {res_data['total']}€ (Consumo Mínimo: {res_data['min_spend']}€)\n"
                f"📝 *Notas:* {res_data['notes']}\n\n"
                f"¿Deseas confirmar esta solicitud?"
            )
            
            if OWNER_PHONE:
                await send_buttons(OWNER_PHONE, owner_msg, [
                    {"id": f"accept_{res_id}", "title": "Confirmar Reserva"},
                    {"id": f"reject_{res_id}", "title": "Rechazar"}
                ])
            else:
                print(f"MOCK OWNER -> {OWNER_PHONE}: {owner_msg}")
                
            # Limpiar estado del cliente e informarles del envío
            clear_state(phone)
            await send_text(phone, "✅ *¡Solicitud enviada!*\n\nEl equipo de Estrop te confirmará la reserva por este chat en breve. ¡Gracias! 🎉")

async def process_owner_response(owner_phone: str, btn_id: str):
    # Descomponer acción e ID de la reserva
    parts = btn_id.split("_")
    action = parts[0] # accept o reject
    res_id = parts[1]
    
    # Obtener detalles de la reserva desde Redis
    raw_res = redis.get(f"res:{res_id}")
    if not raw_res:
        await send_text(owner_phone, f"⚠️ Error: No se encontró la reserva *{res_id}* o ya caducó.")
        return
        
    res_data = json.loads(raw_res)
    client_phone = res_data["client_phone"]
    
    if action == "accept":
        # Notificar al cliente
        client_msg = (
            f"¡Tu reserva para el **{res_data['date']}** ha sido **CONFIRMADA** por el equipo de Estrop! 🎉\n\n"
            f"📍 *Sala:* {res_data['room_name']} — {res_data['option_title']}\n"
            f"👥 *Personas:* {res_data['people']}\n\n"
            f"¡Te esperamos! 🕺"
        )
        await send_text(client_phone, client_msg)
        
        # Notificar al dueño
        await send_text(owner_phone, f"✅ Reserva *{res_id}* de +{client_phone} confirmada y notificada.")
    else:
        # Notificar al cliente
        client_msg = (
            f"Lo sentimos, el equipo de Estrop no ha podido confirmar tu reserva para el **{res_data['date']}** por motivos de aforo o disponibilidad. 😔\n\n"
            f"Por favor, ponte en contacto directo para buscar otra alternativa."
        )
        await send_text(client_phone, client_msg)
        
        # Notificar al dueño
        await send_text(owner_phone, f"❌ Reserva *{res_id}* de +{client_phone} rechazada y notificada.")
        
    # Eliminar reserva de Redis para evitar clics duplicados
    redis.delete(f"res:{res_id}")

@app.get("/")
def root():
    return {"status": "Estrop Bot running ✅"}

@app.get("/webhook/whatsapp")
def verify(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(content=challenge, status_code=200)
    raise HTTPException(status_code=403, detail="Forbidden")

@app.post("/webhook/whatsapp")
async def webhook(request: Request):
    payload = await request.json()
    try:
        msg = payload["entry"][0]["changes"][0]["value"]["messages"][0]
        phone = msg["from"]
        text = msg["text"]["body"] if msg.get("type") == "text" else ""
        interactive = msg.get("interactive") if msg.get("type") == "interactive" else None
        
        # Si es una respuesta de botón y proviene del dueño, procesar aprobación
        if interactive and interactive.get("type") == "button_reply":
            btn_id = interactive["button_reply"]["id"]
            if btn_id.startswith("accept_") or btn_id.startswith("reject_"):
                # Si está configurado OWNER_PHONE, verificar remitente
                if not OWNER_PHONE or phone == OWNER_PHONE:
                    await process_owner_response(phone, btn_id)
                    return {"status": "ok"}
        
        await process(phone, text, interactive)
    except Exception as e:
        print(f"Error: {e}")
    return {"status": "ok"}
