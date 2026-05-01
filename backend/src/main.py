import os
import json
import asyncio
import httpx
from fastapi import FastAPI, Request, HTTPException
from upstash_redis import Redis
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Estrop WhatsApp Bot API")

# Redis para estado persistente (Upstash - free tier)
redis = Redis(
    url=os.getenv("UPSTASH_REDIS_REST_URL"),
    token=os.getenv("UPSTASH_REDIS_REST_TOKEN")
)

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "mock_token_123")

ROOMS = {
    "sala1": {
        "name": "Sala 1",
        "min_spend": 300,
        "options": {
            "s1_12": {"title": "2 Consumiciones (12€)", "price": 12},
            "s1_22": {"title": "Libre Vi/Cerv (22€)", "price": 22},
            "s1_32": {"title": "Libre Combinados(32€)", "price": 32}
        }
    },
    "sala2": {
        "name": "Sala 2",
        "min_spend": 500,
        "options": {
            "s2_15": {"title": "2 Consumiciones (15€)", "price": 15},
            "s2_25": {"title": "Libre Vi/Cerv (25€)", "price": 25},
            "s2_35": {"title": "Libre Combinados(35€)", "price": 35}
        }
    }
}

# ── Helpers de estado en Redis ──────────────────────────────────────────────

def get_state(phone: str) -> dict:
    raw = redis.get(f"state:{phone}")
    if raw:
        return json.loads(raw)
    return {"state": "START", "data": {}}

def save_state(phone: str, state: dict):
    # Conversaciones expiran en 2 horas de inactividad
    redis.setex(f"state:{phone}", 7200, json.dumps(state))

def clear_state(phone: str):
    redis.delete(f"state:{phone}")

# ── Envío de mensajes ───────────────────────────────────────────────────────

async def send_whatsapp_message(to: str, data: dict):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print(f"MOCK SEND to {to}: {data}")
        return

    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to, **data}

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            print(f"✅ Sent to {to}")
        else:
            print(f"❌ Error {response.status_code}: {response.text}")

async def send_text(to: str, text: str):
    await send_whatsapp_message(to, {"type": "text", "text": {"body": text}})

async def send_interactive_list(to: str, body: str, button_text: str, sections: list):
    await send_whatsapp_message(to, {
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body},
            "action": {"button": button_text, "sections": sections}
        }
    })

async def send_interactive_buttons(to: str, body: str, buttons: list):
    await send_whatsapp_message(to, {
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [{"type": "reply", "reply": {"id": b["id"], "title": b["title"]}} for b in buttons]
            }
        }
    })

# ── Lógica del bot ──────────────────────────────────────────────────────────

async def process_message(phone: str, text: str, interactive: dict = None):
    user = get_state(phone)
    state = user["state"]
    data = user["data"]

    # Comandos globales para reiniciar
    if text and text.lower().strip() in ["cancelar", "reiniciar", "hola", "inicio"]:
        user = {"state": "START", "data": {}}
        state = "START"

    if state == "START":
        await send_text(phone,
            "¡Hola! 👋 Soy el asistente de *Estrop*. Vamos a gestionar tu reserva rápido. 🥳\n\n"
            "¿Para cuántas personas buscas sala? Escribe solo el número."
        )
        save_state(phone, {"state": "WAITING_PEOPLE", "data": {}})

    elif state == "WAITING_PEOPLE":
        if not text.strip().isdigit():
            await send_text(phone, "Por favor, escribe solo el número (ejemplo: 12).")
            return
        data["people"] = int(text.strip())
        await send_text(phone,
            "¿Para qué día y hora quieres reservar?\n\n"
            "Usa este formato: *Sábado 25/05 a las 19:30*"
        )
        save_state(phone, {"state": "WAITING_DATE", "data": data})

    elif state == "WAITING_DATE":
        data["date"] = text.strip()
        sections = []
        for room_data in ROOMS.values():
            rows = [
                {
                    "id": opt_id,
                    "title": opt_data["title"][:24],
                    "description": f"Precio: {opt_data['price']}€/pers"
                }
                for opt_id, opt_data in room_data["options"].items()
            ]
            sections.append({"title": room_data["name"][:24], "rows": rows})

        await send_interactive_list(
            phone,
            f"Perfecto, {data['people']} invitados el {data['date']}.\n\n"
            "Aquí tienes las opciones disponibles. Pulsa el botón para elegir sala y ticket:",
            "Ver Salas y Tickets",
            sections
        )
        save_state(phone, {"state": "WAITING_ROOM", "data": data})

    elif state == "WAITING_ROOM":
        if not interactive or interactive.get("type") != "list_reply":
            await send_text(phone, "Por favor, usa el botón *'Ver Salas y Tickets'* para elegir.")
            return

        selected_id = interactive["list_reply"]["id"]
        full_room_id = "sala1" if selected_id.startswith("s1") else "sala2"
        room = ROOMS[full_room_id]
        option = room["options"][selected_id]

        data["room_name"] = room["name"]
        data["option_title"] = option["title"]
        data["total"] = option["price"] * data["people"]
        data["min_spend"] = room["min_spend"]

        msg = (
            f"Has elegido *{room['name']}* con *{option['title']}*.\n\n"
            f"Para {data['people']} personas → Total tickets: *{data['total']}€*\n"
            f"⚠️ Consumo mínimo de sala: *{room['min_spend']}€*\n\n"
            "📌 Horario sala privada: 18:30–23:00h. A las 23h abrimos al público, recogemos pero la fiesta sigue 🕺\n"
            "🚫 No se permite bebida del exterior.\n\n"
            "¿Celebras algo especial (cumpleaños, empresa...) o tienes alguna petición? "
            "Escríbelo o responde *Ninguna*."
        )
        await send_text(phone, msg)
        save_state(phone, {"state": "WAITING_NOTES", "data": data})

    elif state == "WAITING_NOTES":
        data["notes"] = text.strip()
        summary = (
            "¡Entendido! Revisa tu solicitud:\n\n"
            f"👥 Personas: {data['people']}\n"
            f"📅 Fecha/Hora: {data['date']}\n"
            f"📍 Sala: {data['room_name']} — {data['option_title']}\n"
            f"📝 Notas: {data['notes']}\n\n"
            "¿Confirmamos el envío?"
        )
        await send_interactive_buttons(phone, summary, [
            {"id": "confirm", "title": "✅ Confirmar Reserva"},
            {"id": "edit", "title": "✏️ Editar"}
        ])
        save_state(phone, {"state": "WAITING_CONFIRMATION", "data": data})

    elif state == "WAITING_CONFIRMATION":
        if not interactive or interactive.get("type") != "button_reply":
            await send_text(phone, "Por favor, usa los botones para confirmar o editar.")
            return

        btn_id = interactive["button_reply"]["id"]
        if btn_id == "edit":
            clear_state(phone)
            await send_text(phone, "¡Vale! Empecemos de nuevo. Escribe *Hola* cuando quieras. 😊")
        else:
            clear_state(phone)
            await send_text(phone,
                "✅ *¡Solicitud enviada!*\n\n"
                "El equipo de Estrop revisará la disponibilidad y te confirmará "
                "la reserva y el método de pago por este mismo chat en breve.\n\n"
                "¡Gracias y hasta pronto! 🎉"
            )

# ── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "Estrop WhatsApp Bot — Running ✅"}

@app.get("/webhook/whatsapp")
def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return int(challenge)
        raise HTTPException(status_code=403, detail="Verification failed")
    raise HTTPException(status_code=400, detail="Invalid request")

@app.post("/webhook/whatsapp")
async def handle_whatsapp_message(request: Request):
    payload = await request.json()
    try:
        entry = payload.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if messages:
            msg = messages[0]
            phone = msg.get("from")
            text = ""
            interactive = None

            if msg.get("type") == "text":
                text = msg["text"]["body"]
            elif msg.get("type") == "interactive":
                interactive = msg["interactive"]

            # Procesamos de forma síncrona (< 2s) antes de devolver el 200 OK
            await process_message(phone, text, interactive)

    except Exception as e:
        print(f"Error processing webhook: {e}")

    return {"status": "success"}
