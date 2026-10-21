# Configuración y Credenciales del Bot de WhatsApp de Estrop 44

Este documento contiene toda la información técnica y credenciales necesarias para volver a activar el bot en el momento que se desee.

---

## ?? Estado Actual
- **Modo en la Web:** Pausado (todos los botones redirigen al WhatsApp directo del dueño: `+34 626 599 664`).
- **Estado del Bot:** Registrado, verificado y operativo en la nube de Meta.
- **Panel de Control:** Operativo en `https://estrop44-bot.vercel.app/admin`.

---

## ?? Credenciales de Meta WhatsApp Cloud API
- **Nombre de la App en Meta Developers:** `Estrop Bot`
- **ID de la App de Meta:** `1623464856178874`
- **WABA ID (WhatsApp Business Account):** `1092383166980432` (Estrop Badalona)
- **Número de Teléfono del Bot:** `+34 631 55 76 70`
- **Phone Number ID:** `1419799204542275`
- **Estado de Calidad en Meta:** `GREEN` (Verificado y Activo en Cloud API)
- **Token Permanente (System User Token - Sin vencimiento):**
```text
EAAXEiF4O0LoBSuSEFZBmtP5LBoyZC9oDFZCTdSY51KXmtj3cy6FfkaZAZBSAN3VEKZAJ2liWLWRjdq7lQsaxODZCj1bFAcntHEDHTZClKR3cr2HQNMTPQZCpe14H86xfc7AulVvQkubNUxu4tZB4jiBl5r6NZAaqOmZBs0qPZBcn9oPNZAcnMh1KvuGKOgFjtLDnlLYQZDZD
```

---

## ?? Configuración del Webhook en Vercel
- **URL del Webhook:** `https://estrop44-bot.vercel.app/webhook/whatsapp`
- **Token de Verificación (`hub.verify_token`):** `estrop44cesar`
- **Evento suscrito en Meta:** `messages`
- **Base de Datos:** Upstash Redis (gestiona estados, historial y reservas)

---

## ?? Panel de Control Web
- **URL del Panel:** `https://estrop44-bot.vercel.app/admin`
- **Contraseña:** `estrop2026`

---

## ?? Cómo volver a reactivar el bot en el futuro (1 solo paso)
Para volver a activar el bot en la página web en cualquier momento:
1. Abre el archivo `frontend/src/config.ts`.
2. Cambia la línea:
   ```ts
   const useBot = false;
   ```
   a:
   ```ts
   const useBot = true;
   ```
3. Guarda, haz commit y push (o redeploy en Vercel). ¡Y todos los botones de la web volverán a apuntar automáticamente al bot!
