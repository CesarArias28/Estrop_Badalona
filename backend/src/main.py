import os
import httpx
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Estrop 44 WhatsApp Bot API")

# Diccionario en memoria para almacenar el estado del bot por número de teléfono
# Formato: { "34600000000": { "state": "WAITING_PEOPLE", "data": {} } }
user_states = {}

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

async def send_whatsapp_message(to: str, data: dict):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print(f"MOCK SEND to {to}: {data}")
        return
    
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        **data
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            print(f"Error sending message: {response.text}")

async def send_text(to: str, text: str):
    await send_whatsapp_message(to, {"type": "text", "text": {"body": text}})

async def send_interactive_list(to: str, text: str, button_text: str, sections: list):
    await send_whatsapp_message(to, {
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": text},
            "action": {
                "button": button_text,
                "sections": sections
            }
        }
    })

async def send_interactive_buttons(to: str, text: str, buttons: list):
    await send_whatsapp_message(to, {
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": text},
            "action": {
                "buttons": [{"type": "reply", "reply": {"id": b["id"], "title": b["title"]}} for b in buttons]
            }
        }
    })

async def process_message(phone: str, text: str, interactive: dict = None):
    # Initialize state if new user
    if phone not in user_states:
        user_states[phone] = {"state": "START", "data": {}}

    state = user_states[phone]["state"]
    data = user_states[phone]["data"]

    # Comando global para reiniciar
    if text and text.lower().strip() in ["cancelar", "reiniciar", "hola"]:
        user_states[phone] = {"state": "START", "data": {}}
        state = "START"

    if state == "START":
        await send_text(phone, "¡Hola! 👋 Soy el asistente de Estrop 44. Vamos a gestionar tu reserva rápido. 🥳\n\n¿Para cuántas personas buscas sala? (Escribe solo el número)")
        user_states[phone]["state"] = "WAITING_PEOPLE"
        
    elif state == "WAITING_PEOPLE":
        if not text.isdigit():
            await send_text(phone, "Por favor, escribe solo el número (ejemplo: 12).")
            return
        data["people"] = int(text)
        await send_text(phone, "¿Para qué día y hora quieres reservar? Usa este formato: DD/MM a las HH:MM. (Ejemplo: Sábado 25/05 a las 19:30).")
        user_states[phone]["state"] = "WAITING_DATE"
        
    elif state == "WAITING_DATE":
        data["date"] = text.strip()
        
        # Build Interactive List format for WhatsApp
        sections = []
        for room_id, room_data in ROOMS.items():
            rows = []
            for opt_id, opt_data in room_data["options"].items():
                rows.append({
                    "id": opt_id,
                    "title": opt_data["title"][:24], # WhatsApp limits title to 24 chars
                    "description": f"Precio: {opt_data['price']}€/pers"
                })
            sections.append({
                "title": room_data["name"][:24],
                "rows": rows
            })
            
        await send_interactive_list(
            phone, 
            f"Perfecto. Aquí tienes las opciones disponibles para tus {data['people']} invitados. Pulsa el botón para ver detalles de cada sala y elegir tu tipo de acceso:",
            "Ver Salas y Tickets",
            sections
        )
        user_states[phone]["state"] = "WAITING_ROOM"
        
    elif state == "WAITING_ROOM":
        if not interactive or interactive.get("type") != "list_reply":
            await send_text(phone, "Por favor, selecciona una opción usando el botón de 'Ver Salas y Tickets'.")
            return
            
        selected_id = interactive["list_reply"]["id"]
        
        room_id = selected_id.split('_')[0]
        full_room_id = "sala1" if room_id == "s1" else "sala2"
        room = ROOMS[full_room_id]
        option = room["options"][selected_id]
        
        data["room_name"] = room["name"]
        data["option_title"] = option["title"]
        
        total_price = option["price"] * data["people"]
        data["total"] = total_price
        data["min_spend"] = room["min_spend"]
        
        msg = f"Has elegido *{room['name']}* con *{option['title']}*.\n\n"
        msg += f"Para {data['people']} personas, el total de tickets es *{total_price}€*.\n"
        msg += f"⚠️ Recuerda que el consumo mínimo de esta sala es de *{room['min_spend']}€* (puedes completarlo con consumiciones extra o servicios de la sala).\n\n"
        msg += "IMPORTANTE: El horario de sala privada es de 18:30 a 23:00. A las 23h abrimos al público, recogemos pero la fiesta sigue 🕺. No se permite bebida del exterior.\n\n"
        msg += "¿Celebras algo especial (como un cumpleaños) o tienes alguna petición especial? Escríbelo ahora o responde 'Ninguna'."
        
        await send_text(phone, msg)
        user_states[phone]["state"] = "WAITING_NOTES"
        
    elif state == "WAITING_NOTES":
        data["notes"] = text.strip()
        
        summary = "¡Entendido! Revisa los datos de tu solicitud:\n\n"
        summary += f"👥 Personas: {data['people']}\n"
        summary += f"📅 Fecha/Hora: {data['date']}\n"
        summary += f"📍 Sala y Ticket: {data['room_name']}, {data['option_title']}\n"
        summary += f"📝 Notas: {data['notes']}\n\n"
        summary += "¿Confirmamos el envío?"
        
        await send_interactive_buttons(phone, summary, [
            {"id": "confirm", "title": "Confirmar Reserva"},
            {"id": "edit", "title": "Editar Solicitud"}
        ])
        user_states[phone]["state"] = "WAITING_CONFIRMATION"
        
    elif state == "WAITING_CONFIRMATION":
        if not interactive or interactive.get("type") != "button_reply":
            await send_text(phone, "Por favor, usa los botones para Confirmar o Editar.")
            return
            
        btn_id = interactive["button_reply"]["id"]
        if btn_id == "edit":
            del user_states[phone]
            await send_text(phone, "¡Vale! Empecemos de nuevo. Escribe 'Hola' para arrancar.")
        else:
            await send_text(phone, "✅ Tu solicitud ha sido enviada.\n\nEl equipo de Estrop 44 revisará la disponibilidad y te confirmará la reserva y el método de pago por este mismo chat en breve. ¡Gracias!")
            # Al llegar a este punto la reserva está captada.
            # Se podría añadir un envío a un grupo de Telegram de administradores aquí.
            del user_states[phone]

@app.get("/webhook/whatsapp")
def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return int(challenge)
        else:
            raise HTTPException(status_code=403, detail="Verification failed")
    raise HTTPException(status_code=400, detail="Invalid request")

@app.post("/webhook/whatsapp")
async def handle_whatsapp_message(request: Request, background_tasks: BackgroundTasks):
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
                
            # Procesar el mensaje en segundo plano para devolver el 200 OK de inmediato a Meta
            background_tasks.add_task(process_message, phone, text, interactive)
            
    except Exception as e:
        print(f"Error processing webhook: {e}")
        
    return {"status": "success"}
