import { getPermalink } from './utils/permalinks';

export const headerData = {
  links: [
    {
      text: 'Salas',
      links: [
        { text: 'Sala 1 (Principal)', href: getPermalink('/#sala1') },
        { text: 'Sala 2 (Privados)', href: getPermalink('/#sala2') },
      ],
    },
    {
      text: 'Agenda',
      links: [
        { text: 'Tardeo (Viernes)', href: getPermalink('/#tardeo') },
        { text: 'DJ Nights (Sábados)', href: getPermalink('/#djs') },
      ],
    },
    {
      text: 'Experiencia',
      href: getPermalink('/#social'),
    },
    {
      text: 'Contacto',
      href: getPermalink('/#reservas'),
    },
  ],
  actions: [
    { 
      text: 'RESERVAR AHORA', 
      href: 'https://wa.me/34600000000?text=Hola,%20quiero%20reservar%20una%20mesa%20en%20Estrop%2044', 
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
        { text: 'Tardeo', href: getPermalink('/#tardeo') },
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
