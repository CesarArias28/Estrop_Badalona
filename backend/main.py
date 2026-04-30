import os
import json
import httpx
from fastapi import FastAPI, Request, HTTPException
from upstash_redis import Redis
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Estrop 44 WhatsApp Bot API")

redis = Redis(
    url=os.getenv("UPSTASH_REDIS_REST_URL"),
    token=os.getenv("UPSTASH_REDIS_REST_TOKEN")
)

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "mock_token_123")

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
        await send_text(phone, "¡Hola! 👋 Soy el asistente de *Estrop 44*. Vamos a gestionar tu reserva. 🥳\n\n¿Para cuántas personas buscas sala? Escribe solo el número.")
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
            clear_state(phone)
            await send_text(phone, "✅ *¡Solicitud enviada!*\n\nEl equipo de Estrop 44 te confirmará la reserva por este chat en breve. ¡Gracias! 🎉")

@app.get("/")
def root():
    return {"status": "Estrop 44 Bot running ✅"}

@app.get("/webhook/whatsapp")
def verify(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return int(challenge)
    raise HTTPException(status_code=403, detail="Forbidden")

@app.post("/webhook/whatsapp")
async def webhook(request: Request):
    payload = await request.json()
    try:
        msg = payload["entry"][0]["changes"][0]["value"]["messages"][0]
        phone = msg["from"]
        text = msg["text"]["body"] if msg.get("type") == "text" else ""
        interactive = msg.get("interactive") if msg.get("type") == "interactive" else None
        await process(phone, text, interactive)
    except Exception as e:
        print(f"Error: {e}")
    return {"status": "ok"}
