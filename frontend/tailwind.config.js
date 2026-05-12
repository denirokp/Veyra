/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        fact: '#1e3a5f',
        hypothesis: '#3b2f5e',
        warn: '#5e3b1e',
      },
    },
  },
  plugins: [],
}
