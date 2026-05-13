/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['IBM Plex Mono', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        soft:     '0 1px 2px rgba(15,23,42,.045), 0 1px 0 rgba(15,23,42,.025)',
        'soft-h': '0 2px 8px rgba(15,23,42,.06),  0 1px 0 rgba(15,23,42,.025)',
        card:     '0 1px 2px rgba(15,23,42,.04),  0 0 0 1px rgba(15,23,42,.05)',
      },
      transitionDuration: {
        '120': '120ms',
      },
    },
  },
  plugins: [],
}
