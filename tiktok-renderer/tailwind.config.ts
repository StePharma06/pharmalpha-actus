import type {Config} from 'tailwindcss';

export default {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'pharmalpha-dark': '#0f1117',
        'pharmalpha-primary': '#1a3a5c',
        'pharmalpha-accent': '#f97316',
      },
      fontFamily: {
        sans: ['"Oswald"', '"Inter"', 'sans-serif'],
      },
    },
  },
} satisfies Config;
