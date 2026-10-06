/** @type {import('tailwindcss').Config} */
export default {
	content: ['./src/lib/**/*.{js,jsx,ts,tsx,svelte}', './src/routes/**/*.{js,jsx,ts,tsx,svelte}'],
	theme: {
		extend: {
			fontFamily: {
				sans: [
					'Inter',
					'ui-sans-serif',
					'system-ui',
					'-apple-system',
					'BlinkMacSystemFont',
					'Segoe UI',
					'Roboto',
					'Helvetica Neue',
					'Arial',
					'Noto Sans',
					'sans-serif'
				],
				landing: [
					'General Sans Landing',
					'ui-sans-serif',
					'system-ui',
					'-apple-system',
					'BlinkMacSystemFont',
					'Segoe UI',
					'Roboto',
					'Helvetica Neue',
					'Arial',
					'sans-serif'
				],
				display: ['Fraunces Landing', 'General Sans Landing', 'ui-serif', 'Georgia', 'serif']
			},
			colors: {
				bone: {
					50: '#f6f1e7',
					100: '#ede5d3',
					200: '#ddd2bc',
					300: '#c5b89d'
				},
				navy: {
					950: '#050d18',
					900: '#0b1b2b',
					800: '#122739',
					700: '#1c344a',
					600: '#2a4660'
				},
				ink: {
					1: '#0a1422',
					2: '#334155',
					3: '#475569',
					4: '#64748b',
					5: '#94a3b8'
				},
				mark: {
					mid: '#3a8fad'
				},
				'landing-success': {
					DEFAULT: '#117a48',
					bg: '#eaf3ed'
				}
			},
			boxShadow: {
				'landing-md': '0 4px 12px rgba(15, 23, 42, 0.06), 0 2px 4px rgba(15, 23, 42, 0.04)',
				'landing-lg': '0 12px 28px rgba(15, 23, 42, 0.08)',
				'landing-xl': '0 24px 60px rgba(15, 23, 42, 0.10)'
			},
			animation: {
				float: 'float 8s ease-in-out infinite',
				'float-delayed': 'float-delayed 10s ease-in-out infinite',
				'float-slow': 'float-slow 12s ease-in-out infinite',
				'bounce-slow': 'bounce-slow 3s ease-in-out infinite',
				'pulse-slow': 'pulse-slow 6s ease-in-out infinite'
			},
			keyframes: {
				float: {
					'0%, 100%': { transform: 'translate(0, 0) scale(1)' },
					'33%': { transform: 'translate(30px, -30px) scale(1.1)' },
					'66%': { transform: 'translate(-20px, 20px) scale(0.9)' }
				},
				'float-delayed': {
					'0%, 100%': { transform: 'translate(0, 0) scale(1)' },
					'33%': { transform: 'translate(-30px, 30px) scale(1.1)' },
					'66%': { transform: 'translate(20px, -20px) scale(0.9)' }
				},
				'float-slow': {
					'0%, 100%': { transform: 'translate(0, 0) scale(1)' },
					'50%': { transform: 'translate(40px, 40px) scale(1.15)' }
				},
				'bounce-slow': {
					'0%, 100%': { transform: 'translateY(0)', opacity: '0.4' },
					'50%': { transform: 'translateY(-20px)', opacity: '0.8' }
				},
				'pulse-slow': {
					'0%, 100%': { opacity: '0.3', transform: 'translate(-50%, -50%) scale(1)' },
					'50%': { opacity: '0.5', transform: 'translate(-50%, -50%) scale(1.05)' }
				}
			}
		}
	}
};
