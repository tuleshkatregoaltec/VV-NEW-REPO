import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:5173';

export default defineConfig({
	testDir: '.',
	fullyParallel: true,
	forbidOnly: !!process.env.CI,
	retries: process.env.CI ? 2 : 0,
	reporter: 'html',

	use: {
		baseURL,
		trace: 'on-first-retry'
	},

	projects: [
		{
			name: 'setup',
			testMatch: /auth\.setup\.ts/
		},
		{
			name: 'chromium',
			use: {
				...devices['Desktop Chrome'],
				storageState: '.auth/user.json'
			},
			dependencies: ['setup'],
			testIgnore: [/.*\.unauth\.spec\.ts/, /.*\.real\.spec\.ts/, /guards\/.*\.spec\.ts/]
		},
		{
			name: 'real-auth',
			use: { ...devices['Desktop Chrome'] },
			testMatch: /.*\.real\.spec\.ts/
		},
		{
			name: 'unauthenticated',
			use: { ...devices['Desktop Chrome'] },
			testMatch: /.*\.unauth\.spec\.ts/
		},
		{
			name: 'mocked-guards',
			use: { ...devices['Desktop Chrome'] },
			testMatch: /guards\/.*\.spec\.ts/
		}
	],

	webServer: {
		command: 'cd ../frontend && bun run dev -- --host 127.0.0.1',
		url: 'http://localhost:5173',
		reuseExistingServer: !process.env.CI,
		timeout: 120_000
	}
});
