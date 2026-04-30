import { getPermalink } from './utils/permalinks';

export const headerData = {
  links: [
    {
      text: 'Salas',
      href: getPermalink('/#salas'),
    },
    {
      text: 'Experiencia',
      href: getPermalink('/#social'),
    },
    {
      text: 'Reservas',
      href: getPermalink('/#reservas'),
    },
  ],
  actions: [
    { 
      text: 'RESERVAR AHORA', 
      href: 'https://wa.me/15556389717?text=Hola%2C%20quiero%20reservar%20en%20Estrop%2044', 
      target: '_blank',
      variant: 'primary',
      id: 'nav-whatsapp-btn',
      class: 'animate-heartbeat bg-green-500 hover:bg-green-600 border-none shadow-[0_0_15px_rgba(34,197,94,0.5)]'
    }
  ],
};

export const footerData = {
  links: [
    {
      title: 'Estrop 44',
      links: [
        { text: 'Inicio', href: getPermalink('/') },
        { text: 'Nosotros', href: getPermalink('/#features') },
        { text: 'Salas', href: getPermalink('/#salas') },
        { text: 'Reservas', href: getPermalink('/#reservas') },
      ],
    },
    {
      title: 'Legal',
      links: [
        { text: 'Términos y Condiciones', href: '#' },
        { text: 'Política de Privacidad', href: '#' },
      ],
    },
  ],
  secondaryLinks: [],
  socialLinks: [
    { ariaLabel: 'Instagram', icon: 'tabler:brand-instagram', href: 'https://www.instagram.com/estropbadalona/?hl=es', target: '_blank' },
    { ariaLabel: 'Facebook', icon: 'tabler:brand-facebook', href: '#' },
  ],
  footNote: `
    © 2026 Estrop 44 Bar Musical · Todos los derechos reservados.
  `,
};
