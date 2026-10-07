import os
import json
import uuid
from datetime import datetime
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, HTMLResponse, JSONResponse
from upstash_redis import Redis
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
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
OWNERS = [p.strip() for p in OWNER_PHONE.split(",") if p.strip()] if OWNER_PHONE else []
GOOGLE_SHEET_URL = os.getenv("GOOGLE_SHEET_URL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "estrop2026")

ROOMS = {
    "sala1": {"name": "Sala 1 (Planta Baja)", "min_spend": 300, "options": {
        "s1_12": {"title": "2 Consumiciones (12€)", "price": 12, "description": "2 consumiciones en barra"},
        "s1_22": {"title": "Barra Libre (22€)", "price": 22, "description": "Vino, cerveza, cava, refrescos y agua ilimitados"},
        "s1_32": {"title": "Libre Combinados (32€)", "price": 32, "description": "Vino, cerveza, cava, refrescos, agua y combinados ilimitados"}
    }},
    "sala2": {"name": "Sala 2 (Planta Superior)", "min_spend": 500, "options": {
        "s2_15": {"title": "2 Consumiciones (15€)", "price": 15, "description": "2 consumiciones en barra"},
        "s2_25": {"title": "Barra Libre (25€)", "price": 25, "description": "Vino, cerveza, cava, refrescos y agua ilimitados"},
        "s2_35": {"title": "Libre Combinados (35€)", "price": 35, "description": "Vino, cerveza, cava, refrescos, agua y combinados ilimitados"}
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

def extract_body(data: dict) -> str:
    if data.get("type") == "text":
        return data.get("text", {}).get("body", "")
    elif data.get("type") == "interactive":
        inter = data.get("interactive", {})
        body = inter.get("body", {}).get("text", "")
        if inter.get("type") == "button":
            btns = [b.get("reply", {}).get("title", "") for b in inter.get("action", {}).get("buttons", [])]
            if btns:
                body += f"\n[Botones: {' | '.join(btns)}]"
        elif inter.get("type") == "list":
            body += "\n[Menú de salas y precios]"
        return body
    return ""

def log_chat_message(phone: str, sender: str, text: str):
    if not phone or not text:
        return
    try:
        redis.sadd("bot_clients", phone)
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        msg_obj = json.dumps({"sender": sender, "text": text, "time": now_str})
        redis.rpush(f"chat:{phone}", msg_obj)
        redis.ltrim(f"chat:{phone}", -60, -1)
        redis.expire(f"chat:{phone}", 2592000)
        redis.set(f"last_activity:{phone}", now_str)
    except Exception as e:
        print(f"Error logging chat: {e}")

async def send_wa(to: str, data: dict):
    # Registrar en el historial si es para un cliente
    text_content = extract_body(data)
    if text_content and (not OWNERS or to not in OWNERS):
        log_chat_message(to, "bot", text_content)

    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print(f"MOCK -> {to}: {data}")
        return
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to, **data}
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(url, headers=headers, json=payload)
        print(f"Meta API -> {r.status_code}: {r.text[:200]}")

async def sync_to_google_sheets(payload: dict):
    if not GOOGLE_SHEET_URL:
        print("GOOGLE_SHEET_URL not set, skipping Google Sheets sync.")
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(GOOGLE_SHEET_URL, json=payload, follow_redirects=True)
            print(f"Google Sheets sync: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"Error syncing to Google Sheets: {e}")

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

async def send_confirmed_reservations(owner_phone: str):
    keys = redis.keys("conf:*")
    if not keys:
        await send_text(owner_phone, "📅 No hay reservas confirmadas activas para los próximos 30 días.")
        return
    
    reservations = []
    for k in keys:
        raw = redis.get(k)
        if raw:
            try:
                res_id = k.split(":")[1]
                data = json.loads(raw)
                data["id"] = res_id
                reservations.append(data)
            except Exception:
                pass
                
    if not reservations:
        await send_text(owner_phone, "📅 No hay reservas confirmadas activas para los próximos 30 días.")
        return
        
    msg = "📅 *LISTADO DE RESERVAS CONFIRMADAS*\n\n"
    for idx, r in enumerate(reservations, 1):
        msg += (
            f"*{idx}. Reserva {r['id']}*\n"
            f"👥 Personas: {r['people']}\n"
            f"📅 Fecha: {r['date']}\n"
            f"📍 Sala: {r['room_name']} — {r['option_title']}\n"
            f"👤 Cliente: +{r['client_phone']}\n"
            f"📝 Notas: {r.get('notes', 'Ninguna')}\n\n"
        )
    msg += "💡 Escribe *cancelar <ID>* (ejemplo: *cancelar A1B2C3*) para eliminar alguna de la lista."
    await send_text(owner_phone, msg)

async def process(phone: str, text: str, interactive: dict = None):
    # Comandos especiales del dueño
    if OWNERS and phone in OWNERS and text:
        cleaned_text = text.lower().strip()
        if cleaned_text in ["reservas", "reserva", "ver reservas", "listado"]:
            await send_confirmed_reservations(phone)
            return
        elif cleaned_text.startswith("cancelar ") or cleaned_text.startswith("eliminar "):
            parts = text.split()
            if len(parts) >= 2:
                res_id = parts[1].upper()
                raw_res = redis.get(f"conf:{res_id}")
                if raw_res:
                    res_data = json.loads(raw_res)
                    client_phone = res_data.get("client_phone")
                    
                    # Eliminar de Redis
                    redis.delete(f"conf:{res_id}")
                    
                    # Sincronizar cancelación con Google Sheets
                    sheet_payload = {
                        "action": "cancel",
                        "res_id": res_id
                    }
                    await sync_to_google_sheets(sheet_payload)
                    
                    # Notificar al dueño
                    await send_text(phone, f"✅ Reserva *{res_id}* de +{client_phone} eliminada y cliente notificado.")
                    
                    # Notificar al cliente
                    if client_phone:
                        client_msg = (
                            f"Hola. Te informamos que tu reserva con código *{res_id}* para el **{res_data['date']}** ha sido **CANCELADA**.\n\n"
                            f"Si crees que es un error o deseas reprogramar, por favor ponte en contacto con nosotros. ¡Gracias!"
                        )
                        await send_text(client_phone, client_msg)
                else:
                    await send_text(phone, f"⚠️ No se encontró ninguna reserva confirmada con el ID *{res_id}*.")
            else:
                await send_text(phone, "⚠️ Formato incorrecto. Escribe: *cancelar <ID>* (ejemplo: *cancelar A1B2C3*).")
            return

    user = get_state(phone)
    state = user["state"]
    data = user["data"]

    if text and text.lower().strip() in ["cancelar", "reiniciar", "hola", "inicio"]:
        user = {"state": "START", "data": {}}
        state = "START"

    if state == "START":
        start_msg = (
            "¡Hola! 👋 Soy el asistente virtual de *Estrop Bar Musical*. "
            "Te ayudaré a tomar los datos iniciales de tu reserva de forma rápida. 🤖\n\n"
            "📸 Si aún no conoces nuestras instalaciones o quieres ver fotos y vídeos de las salas, puedes visitar nuestra web:\n"
            "🌐 https://estropbadalona.com\n\n"
            "👥 ¿Para cuántas personas buscas reserva aproximadamente? "
            "(El número es *orientativo* y se podrá ajustar después).\n\n"
            "Escribe solo el número (ejemplo: 12):"
        )
        await send_text(phone, start_msg)
        save_state(phone, {"state": "WAITING_PEOPLE", "data": {}})

    elif state == "WAITING_PEOPLE":
        if not text.strip().isdigit():
            await send_text(phone, "Por favor, escribe solo el número (ejemplo: 12).")
            return
        data["people"] = int(text.strip())
        date_msg = (
            "¿Para qué día y hora quieres reservar aproximadamente? "
            "(También se podrá modificar si lo necesitas).\n\n"
            "Ejemplo: *Sábado 25/10 a las 19:30*"
        )
        await send_text(phone, date_msg)
        save_state(phone, {"state": "WAITING_DATE", "data": data})

    elif state == "WAITING_DATE":
        data["date"] = text.strip()
        sections = [{"title": r["name"][:24], "rows": [
            {"id": oid, "title": o["title"][:24], "description": o.get("description", f"{o['price']}€/pers")[:72]}
            for oid, o in r["options"].items()
        ]} for r in ROOMS.values()]
        
        list_body = (
            f"Perfecto, ~{data['people']} personas el {data['date']}.\n\n"
            "💡 Ten en cuenta que las salas y ofertas son *modificables pero sujetas a disponibilidad*.\n\n"
            "Pulsa el botón desplegable para elegir sala y tipo de acceso:"
        )
        await send_list(phone, list_body, sections)
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
               f"👥 ~{data['people']} personas (aprox.) → Total estimado: *{data['total']}€*\n"
               f"⚠️ Consumo mínimo de la sala: *{room['min_spend']}€*\n\n"
               "💡 *Recordatorio:* Esta propuesta es modificable (sujeta a disponibilidad).\n"
               "📌 Horario de sala privada: 18:30–23:00h (a las 23h abrimos al público pero la fiesta sigue 🕺).\n"
               "🚫 No se permite bebida del exterior.\n\n"
               "¿Tienes alguna petición especial (cumpleaños, decoración, dudas...)? Escríbela o di *Ninguna*.")
        await send_text(phone, msg)
        save_state(phone, {"state": "WAITING_NOTES", "data": data})

    elif state == "WAITING_NOTES":
        data["notes"] = text.strip()
        summary = (f"Revisa tu solicitud orientativa:\n\n"
                   f"👥 Personas: {data['people']} (orientativo)\n"
                   f"📅 Fecha: {data['date']}\n"
                   f"📍 Sala: {data['room_name']} — {data['option_title']}\n"
                   f"📝 Notas: {data['notes']}\n\n"
                   "👤 *Atención personalizada:* Al enviar la solicitud, tu reserva pasará a ser gestionada de forma personalizada por una persona real de nuestro equipo.\n\n"
                   "¿Enviamos la solicitud?")
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
                f"👥 *Personas:* {res_data['people']} (aprox.)\n"
                f"📅 *Fecha:* {res_data['date']}\n"
                f"📍 *Sala:* {res_data['room_name']} — {res_data['option_title']}\n"
                f"💰 *Total estimado:* {res_data['total']}€ (Consumo Mínimo: {res_data['min_spend']}€)\n"
                f"📝 *Notas:* {res_data['notes']}\n\n"
                f"¿Deseas confirmar esta solicitud?"
            )
            
            if OWNERS:
                for owner in OWNERS:
                    await send_buttons(owner, owner_msg, [
                        {"id": f"accept_{res_id}", "title": "Confirmar Reserva"},
                        {"id": f"reject_{res_id}", "title": "Rechazar"}
                    ])
            else:
                print(f"MOCK OWNER -> {OWNER_PHONE}: {owner_msg}")
                
            # Limpiar estado del cliente e informarles del envío + enlace directo al teléfono del dueño
            clear_state(phone)
            client_final_msg = (
                "✅ *¡Solicitud enviada con éxito!* 🎉\n\n"
                "👤 Tu reserva ha sido asignada a nuestro equipo para atención personalizada. "
                "A partir de este momento estás en contacto directo con una persona real.\n\n"
                "📞 Si quieres hablar directamente con el encargado o consultarle cualquier cosa por WhatsApp, puedes escribirle aquí:\n"
                "👉 https://wa.me/34626599664\n\n"
                "¡Te responderemos lo antes posible para confirmar todos los detalles!"
            )
            await send_text(phone, client_final_msg)

async def process_owner_response(owner_phone: str, btn_id: str):
    # Descomponer acción e ID de la reserva
    parts = btn_id.split("_")
    action = parts[0] # accept o reject
    res_id = parts[1]
    
    # Obtener detalles de la reserva desde Redis
    raw_res = redis.get(f"res:{res_id}")
    if not raw_res:
        await send_text(owner_phone, f"⚠️ La reserva *{res_id}* ya ha sido procesada (confirmada o rechazada) por otro administrador.")
        return
        
    res_data = json.loads(raw_res)
    client_phone = res_data["client_phone"]
    
    if action == "accept":
        # Guardar en listado de confirmadas (expira en 30 días para autolimpieza)
        redis.setex(f"conf:{res_id}", 2592000, json.dumps(res_data))

        # Sincronizar con Google Sheets
        sheet_payload = {
            "action": "confirm",
            "res_id": res_id,
            "client_phone": client_phone,
            "people": res_data.get("people"),
            "date": res_data.get("date"),
            "room_name": res_data.get("room_name"),
            "option_title": res_data.get("option_title"),
            "total": res_data.get("total"),
            "notes": res_data.get("notes", "Ninguna")
        }
        await sync_to_google_sheets(sheet_payload)

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
        
        # Registrar mensaje entrante del cliente en el historial si no es del dueño
        client_msg_text = text
        if not client_msg_text and interactive:
            if interactive.get("type") == "button_reply":
                client_msg_text = f"[Botón]: {interactive.get('button_reply', {}).get('title', '')}"
            elif interactive.get("type") == "list_reply":
                client_msg_text = f"[Opción]: {interactive.get('list_reply', {}).get('title', '')}"
        
        if client_msg_text and (not OWNERS or phone not in OWNERS):
            log_chat_message(phone, "client", client_msg_text)

        # Si es una respuesta de botón y proviene del dueño, procesar aprobación
        if interactive and interactive.get("type") == "button_reply":
            btn_id = interactive["button_reply"]["id"]
            if btn_id.startswith("accept_") or btn_id.startswith("reject_"):
                # Si está configurado OWNER_PHONE, verificar remitente
                if not OWNERS or phone in OWNERS:
                    await process_owner_response(phone, btn_id)
                    return {"status": "ok"}
        
        await process(phone, text, interactive)
    except Exception as e:
        print(f"Error: {e}")
    return {"status": "ok"}

@app.get("/api/admin/data")
def get_admin_data(key: str = ""):
    if key != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")
    
    # Obtener todos los teléfonos registrados
    client_set = set()
    raw_members = redis.smembers("bot_clients")
    if raw_members:
        client_set.update(raw_members)
    
    # También escanear claves de estado
    state_keys = redis.keys("state:*") or []
    for sk in state_keys:
        p = sk.split(":")[1]
        if not OWNERS or p not in OWNERS:
            client_set.add(p)
            
    # Reservas confirmadas
    conf_keys = redis.keys("conf:*") or []
    confirmed_list = []
    for ck in conf_keys:
        raw = redis.get(ck)
        if raw:
            try:
                data = json.loads(raw)
                data["id"] = ck.split(":")[1]
                confirmed_list.append(data)
                if data.get("client_phone"):
                    client_set.add(data["client_phone"])
            except Exception:
                pass

    # Solicitudes pendientes
    res_keys = redis.keys("res:*") or []
    pending_list = []
    for rk in res_keys:
        raw = redis.get(rk)
        if raw:
            try:
                data = json.loads(raw)
                data["id"] = rk.split(":")[1]
                pending_list.append(data)
                if data.get("client_phone"):
                    client_set.add(data["client_phone"])
            except Exception:
                pass

    clients_data = []
    for cp in client_set:
        st = get_state(cp)
        last_act = redis.get(f"last_activity:{cp}") or "Reciente"
        
        # Historial de mensajes
        raw_msgs = redis.lrange(f"chat:{cp}", 0, -1) or []
        history = []
        for rm in raw_msgs:
            try:
                history.append(json.loads(rm))
            except Exception:
                pass
                
        clients_data.append({
            "phone": cp,
            "state": st.get("state", "START"),
            "data": st.get("data", {}),
            "last_activity": last_act,
            "history": history
        })

    clients_data.sort(key=lambda x: len(x["history"]), reverse=True)

    return {
        "clients": clients_data,
        "confirmed": confirmed_list,
        "pending": pending_list
    }

@app.post("/api/admin/action")
async def admin_action(request: Request):
    body = await request.json()
    key = body.get("key")
    if key != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    action = body.get("action")
    res_id = body.get("id")
    
    if action == "cancel":
        raw = redis.get(f"conf:{res_id}")
        if raw:
            res_data = json.loads(raw)
            client_phone = res_data.get("client_phone")
            redis.delete(f"conf:{res_id}")
            if client_phone:
                await send_text(client_phone, f"Hola. Te informamos que tu reserva con código *{res_id}* para el {res_data.get('date')} ha sido cancelada por el equipo de Estrop.")
            await sync_to_google_sheets({"action": "cancel", "res_id": res_id})
            return {"status": "ok", "message": f"Reserva {res_id} cancelada"}
    elif action in ["accept", "reject"]:
        btn_id = f"{action}_{res_id}"
        await process_owner_response(OWNERS[0] if OWNERS else "admin", btn_id)
        return {"status": "ok", "message": f"Solicitud {res_id} procesada como {action}"}
        
    return {"status": "error", "message": "Acción no reconocida"}

@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    html_content = """<!DOCTYPE html>
<html lang="es" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Estrop 44 - Panel de Control & Chats</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            brand: { gold: '#eab308', dark: '#0b0f19', card: '#161e2e', border: '#253248' }
          }
        }
      }
    }
  </script>
  <style>
    body { background-color: #0b0f19; color: #f3f4f6; font-family: ui-sans-serif, system-ui, sans-serif; }
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: #0b0f19; }
    ::-webkit-scrollbar-thumb { background: #253248; border-radius: 4px; }
    .chat-bubble-client { background-color: #065f46; border-radius: 14px 14px 2px 14px; }
    .chat-bubble-bot { background-color: #1f2937; border-radius: 14px 14px 14px 2px; }
  </style>
</head>
<body class="min-h-screen flex flex-col">

  <!-- LOGIN OVERLAY -->
  <div id="login-modal" class="fixed inset-0 bg-black/90 z-50 flex items-center justify-center p-4">
    <div class="bg-brand-card border border-brand-border rounded-2xl p-8 max-w-md w-full shadow-2xl text-center">
      <div class="inline-flex p-4 rounded-full bg-yellow-500/10 text-yellow-400 mb-4 text-3xl">
        <i class="fa-solid fa-lock"></i>
      </div>
      <h2 class="text-2xl font-bold text-white mb-2">Panel de Control Estrop</h2>
      <p class="text-sm text-gray-400 mb-6">Introduce la clave de acceso del administrador</p>
      <input type="password" id="admin-pass" placeholder="Contraseña..." class="w-full bg-brand-dark border border-brand-border rounded-xl px-4 py-3 text-white mb-4 focus:outline-none focus:border-yellow-400 text-center text-lg">
      <button onclick="login()" class="w-full bg-yellow-500 hover:bg-yellow-400 text-black font-bold py-3 rounded-xl transition duration-200">
        Entrar al Panel
      </button>
      <p id="login-error" class="text-red-400 text-sm mt-3 hidden">Contraseña incorrecta</p>
    </div>
  </div>

  <!-- MAIN APP -->
  <div id="app" class="flex-1 flex flex-col hidden">
    <!-- NAVBAR -->
    <header class="bg-brand-card/90 border-b border-brand-border px-6 py-4 flex flex-wrap items-center justify-between gap-4 sticky top-0 z-20 backdrop-blur-md">
      <div class="flex items-center gap-3">
        <div class="h-10 w-10 rounded-xl bg-gradient-to-tr from-yellow-600 to-yellow-400 flex items-center justify-center font-black text-black text-xl shadow-lg shadow-yellow-500/20">
          E44
        </div>
        <div>
          <h1 class="font-black text-lg text-white tracking-wider">ESTROP 44</h1>
          <p class="text-xs text-green-400 flex items-center gap-1.5">
            <span class="h-2 w-2 rounded-full bg-green-400 animate-pulse"></span> Bot en línea (+34 631 55 76 70)
          </p>
        </div>
      </div>

      <!-- TABS -->
      <div class="flex items-center bg-brand-dark p-1 rounded-xl border border-brand-border">
        <button onclick="switchTab('chats')" id="tab-btn-chats" class="tab-btn px-4 py-2 rounded-lg text-sm font-semibold flex items-center gap-2 transition bg-yellow-500 text-black">
          <i class="fa-solid fa-comments"></i> Conversaciones
          <span id="badge-chats" class="bg-black/20 text-xs px-2 py-0.5 rounded-full font-bold">0</span>
        </button>
        <button onclick="switchTab('confirmed')" id="tab-btn-confirmed" class="tab-btn px-4 py-2 rounded-lg text-sm font-semibold flex items-center gap-2 transition text-gray-400 hover:text-white">
          <i class="fa-solid fa-calendar-check"></i> Reservas
          <span id="badge-confirmed" class="bg-brand-border text-xs px-2 py-0.5 rounded-full font-bold">0</span>
        </button>
        <button onclick="switchTab('pending')" id="tab-btn-pending" class="tab-btn px-4 py-2 rounded-lg text-sm font-semibold flex items-center gap-2 transition text-gray-400 hover:text-white">
          <i class="fa-solid fa-bell"></i> Pendientes
          <span id="badge-pending" class="bg-brand-border text-xs px-2 py-0.5 rounded-full font-bold">0</span>
        </button>
      </div>

      <div class="flex items-center gap-3">
        <button onclick="loadData()" class="px-3 py-2 rounded-lg bg-brand-border hover:bg-gray-700 text-sm font-medium flex items-center gap-2 transition">
          <i class="fa-solid fa-rotate-right"></i> <span class="hidden sm:inline">Actualizar</span>
        </button>
        <button onclick="logout()" class="px-3 py-2 rounded-lg bg-red-950 hover:bg-red-900 text-red-300 text-sm font-medium transition">
          <i class="fa-solid fa-arrow-right-from-bracket"></i>
        </button>
      </div>
    </header>

    <!-- CONTENT -->
    <main class="flex-1 flex overflow-hidden">
      <!-- TAB 1: CHATS -->
      <section id="tab-chats" class="tab-content flex-1 flex w-full">
        <!-- CLIENTS LIST -->
        <div class="w-full md:w-80 lg:w-96 border-r border-brand-border flex flex-col bg-brand-dark/50">
          <div class="p-3 border-b border-brand-border">
            <input type="text" id="client-search" oninput="filterClients()" placeholder="Buscar por teléfono..." class="w-full bg-brand-card border border-brand-border rounded-xl px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-yellow-400">
          </div>
          <div id="clients-list" class="flex-1 overflow-y-auto divide-y divide-brand-border/40">
            <!-- Dynamic clients -->
          </div>
        </div>

        <!-- CHAT DETAIL -->
        <div id="chat-detail" class="hidden md:flex flex-1 flex-col bg-brand-dark">
          <div id="chat-empty" class="flex-1 flex items-center justify-center text-center p-8 text-gray-500">
            <div>
              <i class="fa-solid fa-message text-5xl mb-4 opacity-40"></i>
              <p class="text-lg">Selecciona un cliente de la lista para ver su conversación</p>
            </div>
          </div>
          <div id="chat-view" class="flex-1 flex flex-col hidden h-full">
            <!-- HEADER -->
            <div class="p-4 bg-brand-card border-b border-brand-border flex flex-wrap items-center justify-between gap-4">
              <div class="flex items-center gap-3">
                <div class="h-10 w-10 rounded-full bg-green-600/30 text-green-400 flex items-center justify-center font-bold text-lg">
                  <i class="fa-solid fa-user"></i>
                </div>
                <div>
                  <h3 id="chat-client-phone" class="font-bold text-lg text-white"></h3>
                  <p id="chat-client-status" class="text-xs text-yellow-400 font-medium"></p>
                </div>
              </div>
              <div class="flex items-center gap-2">
                <a id="chat-wa-direct-link" href="#" target="_blank" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-bold flex items-center gap-2 shadow-lg shadow-emerald-600/20 transition">
                  <i class="fa-brands fa-whatsapp text-sm"></i> Chatear en WhatsApp
                </a>
              </div>
            </div>

            <!-- RESERVATION SUMMARY BAR -->
            <div id="chat-data-banner" class="bg-brand-card/60 border-b border-brand-border px-4 py-3 flex flex-wrap gap-4 text-xs text-gray-300"></div>

            <!-- MESSAGES CONTAINER -->
            <div id="chat-messages" class="flex-1 p-6 overflow-y-auto space-y-4"></div>
          </div>
        </div>
      </section>

      <!-- TAB 2: CONFIRMED RESERVATIONS -->
      <section id="tab-confirmed" class="tab-content flex-1 p-6 overflow-y-auto hidden">
        <div class="max-w-6xl mx-auto">
          <div class="flex items-center justify-between mb-6">
            <h2 class="text-xl font-bold text-white flex items-center gap-2">
              <i class="fa-solid fa-calendar-check text-yellow-400"></i> Reservas Confirmadas
            </h2>
            <span class="text-xs text-gray-400">Próximos 30 días</span>
          </div>
          <div id="confirmed-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"></div>
        </div>
      </section>

      <!-- TAB 3: PENDING REQUESTS -->
      <section id="tab-pending" class="tab-content flex-1 p-6 overflow-y-auto hidden">
        <div class="max-w-6xl mx-auto">
          <div class="flex items-center justify-between mb-6">
            <h2 class="text-xl font-bold text-white flex items-center gap-2">
              <i class="fa-solid fa-bell text-yellow-400"></i> Solicitudes Pendientes de Aprobación
            </h2>
            <span class="text-xs text-gray-400">Esperando respuesta del dueño</span>
          </div>
          <div id="pending-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"></div>
        </div>
      </section>
    </main>
  </div>

  <script>
    let adminKey = localStorage.getItem('estrop_admin_key') || '';
    let globalData = { clients: [], confirmed: [], pending: [] };
    let selectedClient = null;

    if (adminKey) {
      document.getElementById('login-modal').classList.add('hidden');
      document.getElementById('app').classList.remove('hidden');
      loadData();
    }

    async function login() {
      const pass = document.getElementById('admin-pass').value.trim();
      if (!pass) return;
      try {
        const res = await fetch(`/api/admin/data?key=${encodeURIComponent(pass)}`);
        if (res.ok) {
          adminKey = pass;
          localStorage.setItem('estrop_admin_key', pass);
          document.getElementById('login-modal').classList.add('hidden');
          document.getElementById('app').classList.remove('hidden');
          const data = await res.json();
          renderData(data);
        } else {
          document.getElementById('login-error').classList.remove('hidden');
        }
      } catch (err) {
        document.getElementById('login-error').classList.remove('hidden');
      }
    }

    function logout() {
      localStorage.removeItem('estrop_admin_key');
      location.reload();
    }

    async function loadData() {
      if (!adminKey) return;
      try {
        const res = await fetch(`/api/admin/data?key=${encodeURIComponent(adminKey)}`);
        if (res.ok) {
          const data = await res.json();
          renderData(data);
        } else if (res.status === 401) {
          logout();
        }
      } catch (err) {
        console.error('Error fetching data:', err);
      }
    }

    function renderData(data) {
      globalData = data;
      document.getElementById('badge-chats').textContent = data.clients.length;
      document.getElementById('badge-confirmed').textContent = data.confirmed.length;
      document.getElementById('badge-pending').textContent = data.pending.length;

      renderClientsList(data.clients);
      renderConfirmed(data.confirmed);
      renderPending(data.pending);

      if (selectedClient) {
        const updated = data.clients.find(c => c.phone === selectedClient.phone);
        if (updated) selectClient(updated);
      }
    }

    function renderClientsList(clients) {
      const container = document.getElementById('clients-list');
      if (!clients.length) {
        container.innerHTML = `<div class="p-8 text-center text-gray-500 text-sm">No hay conversaciones registradas todavía</div>`;
        return;
      }
      container.innerHTML = clients.map(c => {
        const lastMsg = c.history.length ? c.history[c.history.length - 1].text : 'Sin mensajes';
        const isSelected = selectedClient && selectedClient.phone === c.phone;
        return `
          <div onclick="onSelectClientPhone('${c.phone}')" class="p-4 cursor-pointer transition ${isSelected ? 'bg-brand-card border-l-4 border-yellow-400' : 'hover:bg-brand-card/40'}">
            <div class="flex items-center justify-between mb-1">
              <span class="font-bold text-sm text-white flex items-center gap-1.5">
                <i class="fa-solid fa-phone text-xs text-gray-400"></i> +${c.phone}
              </span>
              <span class="text-[10px] text-gray-400 font-mono">${c.last_activity}</span>
            </div>
            <p class="text-xs text-gray-400 truncate mb-2">${lastMsg}</p>
            <div class="flex items-center justify-between text-[11px]">
              <span class="px-2 py-0.5 rounded-full bg-yellow-500/10 text-yellow-400 font-medium">${c.state}</span>
              ${c.data && c.data.people ? `<span class="text-gray-400">👥 ~${c.data.people} pers</span>` : ''}
            </div>
          </div>
        `;
      }).join('');
    }

    function onSelectClientPhone(phone) {
      const c = globalData.clients.find(x => x.phone === phone);
      if (c) selectClient(c);
    }

    function selectClient(c) {
      selectedClient = c;
      renderClientsList(globalData.clients);
      document.getElementById('chat-empty').classList.add('hidden');
      document.getElementById('chat-view').classList.remove('hidden');

      document.getElementById('chat-client-phone').textContent = `+${c.phone}`;
      document.getElementById('chat-client-status').textContent = `Estado: ${c.state}`;
      document.getElementById('chat-wa-direct-link').href = `https://wa.me/${c.phone}`;

      // Summary banner
      const banner = document.getElementById('chat-data-banner');
      if (c.data && (c.data.people || c.data.date || c.data.room_name)) {
        banner.classList.remove('hidden');
        banner.innerHTML = `
          ${c.data.people ? `<span class="bg-brand-dark px-2.5 py-1 rounded-md border border-brand-border"><strong class="text-yellow-400">👥 Personas:</strong> ~${c.data.people}</span>` : ''}
          ${c.data.date ? `<span class="bg-brand-dark px-2.5 py-1 rounded-md border border-brand-border"><strong class="text-yellow-400">📅 Fecha:</strong> ${c.data.date}</span>` : ''}
          ${c.data.room_name ? `<span class="bg-brand-dark px-2.5 py-1 rounded-md border border-brand-border"><strong class="text-yellow-400">📍 Sala:</strong> ${c.data.room_name} (${c.data.option_title || ''})</span>` : ''}
          ${c.data.total ? `<span class="bg-brand-dark px-2.5 py-1 rounded-md border border-brand-border"><strong class="text-yellow-400">💰 Total:</strong> ${c.data.total}€</span>` : ''}
          ${c.data.notes ? `<span class="bg-brand-dark px-2.5 py-1 rounded-md border border-brand-border"><strong class="text-yellow-400">📝 Notas:</strong> ${c.data.notes}</span>` : ''}
        `;
      } else {
        banner.classList.add('hidden');
      }

      // Render messages
      const msgBox = document.getElementById('chat-messages');
      if (!c.history || !c.history.length) {
        msgBox.innerHTML = `<div class="p-8 text-center text-gray-500 text-sm">No hay mensajes registrados aún en este chat.</div>`;
      } else {
        msgBox.innerHTML = c.history.map(m => {
          const isClient = m.sender === 'client';
          return `
            <div class="flex flex-col ${isClient ? 'items-end' : 'items-start'}">
              <div class="max-w-[80%] p-3 text-sm shadow-md whitespace-pre-wrap ${isClient ? 'chat-bubble-client text-white' : 'chat-bubble-bot text-gray-200'}">
                ${m.text}
              </div>
              <span class="text-[10px] text-gray-500 mt-1 px-1 font-mono">${m.time} • ${isClient ? 'Cliente' : 'Bot'}</span>
            </div>
          `;
        }).join('');
        msgBox.scrollTop = msgBox.scrollHeight;
      }
    }

    function renderConfirmed(confirmed) {
      const grid = document.getElementById('confirmed-grid');
      if (!confirmed.length) {
        grid.innerHTML = `<div class="col-span-full p-12 text-center text-gray-500">No hay reservas confirmadas activas</div>`;
        return;
      }
      grid.innerHTML = confirmed.map(r => `
        <div class="bg-brand-card border border-brand-border rounded-2xl p-5 shadow-lg flex flex-col justify-between">
          <div>
            <div class="flex items-center justify-between mb-3">
              <span class="font-mono text-xs px-2.5 py-1 rounded-lg bg-yellow-500/10 text-yellow-400 font-bold">#${r.id}</span>
              <span class="text-xs text-green-400 font-bold bg-green-500/10 px-2 py-0.5 rounded-full">Confirmada</span>
            </div>
            <h4 class="font-bold text-white text-base mb-1">+${r.client_phone}</h4>
            <div class="space-y-1.5 text-xs text-gray-300 mt-3">
              <p><strong class="text-gray-400">📅 Fecha:</strong> ${r.date}</p>
              <p><strong class="text-gray-400">👥 Personas:</strong> ${r.people}</p>
              <p><strong class="text-gray-400">📍 Sala:</strong> ${r.room_name} — ${r.option_title}</p>
              <p><strong class="text-gray-400">💰 Total estimado:</strong> ${r.total}€</p>
              <p><strong class="text-gray-400">📝 Notas:</strong> ${r.notes || 'Ninguna'}</p>
            </div>
          </div>
          <div class="mt-5 pt-4 border-t border-brand-border/60 flex items-center justify-between gap-2">
            <a href="https://wa.me/${r.client_phone}" target="_blank" class="px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold flex items-center gap-1.5 transition">
              <i class="fa-brands fa-whatsapp"></i> Chat
            </a>
            <button onclick="cancelReservation('${r.id}')" class="px-3 py-1.5 rounded-xl bg-red-950 hover:bg-red-900 text-red-300 text-xs font-semibold transition">
              Cancelar
            </button>
          </div>
        </div>
      `).join('');
    }

    function renderPending(pending) {
      const grid = document.getElementById('pending-grid');
      if (!pending.length) {
        grid.innerHTML = `<div class="col-span-full p-12 text-center text-gray-500">No hay solicitudes pendientes en este momento</div>`;
        return;
      }
      grid.innerHTML = pending.map(r => `
        <div class="bg-brand-card border border-brand-border rounded-2xl p-5 shadow-lg flex flex-col justify-between">
          <div>
            <div class="flex items-center justify-between mb-3">
              <span class="font-mono text-xs px-2.5 py-1 rounded-lg bg-blue-500/10 text-blue-400 font-bold">#${r.id}</span>
              <span class="text-xs text-yellow-400 font-bold bg-yellow-500/10 px-2 py-0.5 rounded-full">Pendiente</span>
            </div>
            <h4 class="font-bold text-white text-base mb-1">+${r.client_phone}</h4>
            <div class="space-y-1.5 text-xs text-gray-300 mt-3">
              <p><strong class="text-gray-400">📅 Fecha:</strong> ${r.date}</p>
              <p><strong class="text-gray-400">👥 Personas:</strong> ${r.people}</p>
              <p><strong class="text-gray-400">📍 Sala:</strong> ${r.room_name} — ${r.option_title}</p>
              <p><strong class="text-gray-400">💰 Total:</strong> ${r.total}€</p>
              <p><strong class="text-gray-400">📝 Notas:</strong> ${r.notes || 'Ninguna'}</p>
            </div>
          </div>
          <div class="mt-5 pt-4 border-t border-brand-border/60 flex items-center gap-2">
            <button onclick="handleAction('accept', '${r.id}')" class="flex-1 py-2 rounded-xl bg-green-600 hover:bg-green-500 text-white text-xs font-bold transition">
              Confirmar
            </button>
            <button onclick="handleAction('reject', '${r.id}')" class="flex-1 py-2 rounded-xl bg-red-950 hover:bg-red-900 text-red-300 text-xs font-bold transition">
              Rechazar
            </button>
          </div>
        </div>
      `).join('');
    }

    async function cancelReservation(id) {
      if (!confirm(`¿Seguro que deseas cancelar la reserva #${id}? Se notificará al cliente por WhatsApp.`)) return;
      await handleAction('cancel', id);
    }

    async function handleAction(action, id) {
      try {
        const res = await fetch('/api/admin/action', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key: adminKey, action, id })
        });
        if (res.ok) {
          loadData();
        } else {
          alert('Error procesando la solicitud');
        }
      } catch (err) {
        alert('Error conectando con el servidor');
      }
    }

    function switchTab(tab) {
      document.querySelectorAll('.tab-btn').forEach(b => {
        b.classList.remove('bg-yellow-500', 'text-black');
        b.classList.add('text-gray-400');
      });
      document.querySelectorAll('.tab-content').forEach(c => c.classList.add('hidden'));

      const activeBtn = document.getElementById(`tab-btn-${tab}`);
      activeBtn.classList.add('bg-yellow-500', 'text-black');
      activeBtn.classList.remove('text-gray-400');

      document.getElementById(`tab-${tab}`).classList.remove('hidden');
    }

    function filterClients() {
      const q = document.getElementById('client-search').value.toLowerCase().trim();
      const filtered = globalData.clients.filter(c => c.phone.includes(q));
      renderClientsList(filtered);
    }

    // Auto refresh cada 12 segundos
    setInterval(loadData, 12000);
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)

