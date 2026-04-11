export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        quantum: {
          bg: '#050816',
          panel: '#0b1020',
          line: '#18203a',
          glow: '#5eead4',
          danger: '#fb7185',
          violet: '#8b5cf6'
        }
      },
      boxShadow: {
        glow: '0 0 24px rgba(94,234,212,0.25)',
        danger: '0 0 24px rgba(251,113,133,0.25)'
      }
    }
  },
  plugins: []
}
