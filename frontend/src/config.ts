// Centralized configuration parameters for Estrop Badalona Web
// The number for the old/manual system (active before November 2026)
export const WHATSAPP_NUMBER_OLD = "34626599664";

// The number for the bot system (active from November 2026 onwards)
export const WHATSAPP_NUMBER_BOT = "34626599664";

// Switch automatically based on the date or override to activate bot immediately
const useBot = true;
export const WHATSAPP_NUMBER = useBot ? WHATSAPP_NUMBER_BOT : WHATSAPP_NUMBER_OLD;
