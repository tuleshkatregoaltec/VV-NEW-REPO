import { sveltekit } from '@sveltejs/kit/vite'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vitest/config'

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],

	server: {
		allowedHosts: ['demo.vitevue.com', 'frontend', 'localhost', '127.0.0.1'],
		proxy: {
			'/api': {
				target: process.env.VITEVUE_REMOTE_API_PROXY ?? 'http://127.0.0.1:18000',
				changeOrigin: true
			},
			'/auth-proxy': {
				target: process.env.VITEVUE_REMOTE_AUTH_PROXY ?? 'http://127.0.0.1:19999',
				changeOrigin: true,
				rewrite: (path) => path.replace(/^\/auth-proxy/, '')
			}
		}
	},

	test: {
		environment: 'node',
		include: ['tests/**/*.test.ts']
	},

	build: {
		rollupOptions: {
			output: {
				manualChunks(id) {
					if (id.includes('node_modules/posthog-js')) return 'vendor-posthog'
					if (id.includes('node_modules/maplibre-gl')) return 'vendor-maplibre'
					if (id.includes('node_modules')) return 'vendor'
				}
			}
		}
	}
})
