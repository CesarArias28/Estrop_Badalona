// Centralized configuration parameters for Estrop Badalona Web
// The number for manual contact (owner's personal number)
export const WHATSAPP_NUMBER_OWNER = "34626599664";
export const WHATSAPP_NUMBER_OLD = WHATSAPP_NUMBER_OWNER;

// The number for the automated bot system (preserved for future use)
export const WHATSAPP_NUMBER_BOT = "34631557670";

// Switch between bot (true) or direct owner contact (false)
const useBot = false;
export const WHATSAPP_NUMBER = useBot ? WHATSAPP_NUMBER_BOT : WHATSAPP_NUMBER_OWNER;
