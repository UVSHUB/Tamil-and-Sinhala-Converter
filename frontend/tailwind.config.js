/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'sans-serif'],
        outfit: ['Outfit', 'sans-serif'],
      },
      colors: {
        // High-end premium dark interface colors
        brand: {
          dark: '#020617',
          card: '#0f172a',
          border: '#1e293b',
          accent: '#6366f1',
          success: '#10b981',
          warning: '#f59e0b',
          error: '#ef4444'
        }
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
      }
    },
  },
  plugins: [],
}
