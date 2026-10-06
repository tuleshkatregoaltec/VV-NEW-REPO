import { test as base } from '@playwright/test';

import { personas, type TestPersona } from './personas';

type GuardFixtures = {
	usePersona: (persona: TestPersona) => Promise<void>;
	useAnonymous: () => Promise<void>;
};

function makeSession(email: string) {
	const now = Math.floor(Date.now() / 1000);

	return {
		access_token: `mock-access-token-${email}`,
		token_type: 'bearer',
		expires_in: 3600,
		expires_at: now + 3600,
		refresh_token: `mock-refresh-token-${email}`,
		user: {
			id: `mock-user-${email}`,
			aud: '',
			role: 'user',
			email,
			email_confirmed_at: new Date().toISOString(),
			phone: '',
			confirmed_at: new Date().toISOString(),
			last_sign_in_at: new Date().toISOString(),
			app_metadata: {
				provider: 'email',
				providers: ['email']
			},
			user_metadata: {
				email,
				email_verified: true
			},
			identities: [],
			created_at: new Date().toISOString(),
			updated_at: new Date().toISOString(),
			is_anonymous: false
		}
	};
}

export const test = base.extend<GuardFixtures>({
	usePersona: async ({ page }, use) => {
		await use(async (persona: TestPersona) => {
			const user = personas[persona];
			const session = makeSession(user.email);

			await page.route('**/api/v1/auth/me', async (route) => {
				await route.fulfill({
					status: 200,
					contentType: 'application/json',
					body: JSON.stringify(user)
				});
			});

			await page.addInitScript(
				({ authSession }) => {
					window.localStorage.setItem('authentication', JSON.stringify(authSession));
				},
				{ authSession: session }
			);
		});
	},
	useAnonymous: async ({ page }, use) => {
		await use(async () => {
			await page.addInitScript(() => {
				window.localStorage.removeItem('authentication');
			});
		});
	},
});

export { expect } from '@playwright/test';
