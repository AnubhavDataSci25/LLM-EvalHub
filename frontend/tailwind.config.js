/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        // Source Serif 4 everywhere, per the design system.
        sans: ['"Source Serif 4"', 'Source Serif Pro', 'Georgia', 'Cambria', 'serif'],
        serif: ['"Source Serif 4"', 'Source Serif Pro', 'Georgia', 'serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      colors: {
        // Beige paper + olive ink. Values are CSS variables so light/dark swap
        // without re-declaring every utility.
        sand: {
          50: '#FBF8F1', 100: '#F5F0E4', 200: '#EBE3D2', 300: '#DED3BB',
          400: '#CDBE9D', 500: '#B8A47C', 600: '#9C8862', 700: '#7C6B4E',
          800: '#5C4F3B', 900: '#3D342A', 950: '#221D17',
        },
        olive: {
          50: '#F4F6EC', 100: '#E6EBD4', 200: '#CED8AC', 300: '#B2C081',
          400: '#97A75E', 500: '#7C8C46', 600: '#606F36', 700: '#4A562C',
          800: '#3A4425', 900: '#2F3720', 950: '#171C0F',
        },
        clay: { 400: '#C97B5A', 500: '#B4633F', 600: '#96502F' },
        surface: 'rgb(var(--surface) / <alpha-value>)',
        elevated: 'rgb(var(--elevated) / <alpha-value>)',
        overlay: 'rgb(var(--overlay) / <alpha-value>)',
        line: 'rgb(var(--line) / <alpha-value>)',
        ink: 'rgb(var(--ink) / <alpha-value>)',
        muted: 'rgb(var(--muted) / <alpha-value>)',
        faint: 'rgb(var(--faint) / <alpha-value>)',
        accent: 'rgb(var(--accent) / <alpha-value>)',
        'accent-soft': 'rgb(var(--accent-soft) / <alpha-value>)',
        'accent-ink': 'rgb(var(--accent-ink) / <alpha-value>)',
      },
      borderRadius: { xl: '0.875rem', '2xl': '1.125rem', '3xl': '1.5rem' },
      boxShadow: {
        card: '0 1px 2px rgb(61 52 42 / 0.04), 0 8px 24px -12px rgb(61 52 42 / 0.14)',
        lift: '0 2px 4px rgb(61 52 42 / 0.05), 0 18px 40px -16px rgb(61 52 42 / 0.22)',
        inset: 'inset 0 1px 0 rgb(255 255 255 / 0.5)',
      },
      keyframes: {
        'fade-up': { '0%': { opacity: 0, transform: 'translateY(8px)' }, '100%': { opacity: 1, transform: 'none' } },
        shimmer: { '100%': { transform: 'translateX(100%)' } },
        'pulse-ring': {
          '0%': { boxShadow: '0 0 0 0 rgb(var(--accent) / 0.35)' },
          '70%': { boxShadow: '0 0 0 10px rgb(var(--accent) / 0)' },
          '100%': { boxShadow: '0 0 0 0 rgb(var(--accent) / 0)' },
        },
        'slide-in': { '0%': { opacity: 0, transform: 'translateX(12px)' }, '100%': { opacity: 1, transform: 'none' } },
      },
      animation: {
        'fade-up': 'fade-up 0.45s cubic-bezier(0.22, 1, 0.36, 1) both',
        shimmer: 'shimmer 1.6s infinite',
        'pulse-ring': 'pulse-ring 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'slide-in': 'slide-in 0.35s cubic-bezier(0.22, 1, 0.36, 1) both',
      },
      transitionTimingFunction: { spring: 'cubic-bezier(0.22, 1, 0.36, 1)' },
    },
  },
  plugins: [],
}
