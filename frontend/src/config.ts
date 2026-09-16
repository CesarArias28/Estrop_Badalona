// Centralized configuration parameters for Estrop Badalona Web
// The number for the old/manual system (owner's personal number)
export const WHATSAPP_NUMBER_OLD = "34626599664";

// The number for the automated bot system
export const WHATSAPP_NUMBER_BOT = "34609550930";

// Switch automatically or override to activate bot immediately
const useBot = true;
export const WHATSAPP_NUMBER = useBot ? WHATSAPP_NUMBER_BOT : WHATSAPP_NUMBER_OLD;
