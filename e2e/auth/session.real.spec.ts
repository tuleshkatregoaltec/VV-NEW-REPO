import { expect, test } from '@playwright/test';

test('stale cached user without a live auth session is redirected to /auth', async ({ page }) => {
	await page.addInitScript(() => {
		window.localStorage.removeItem('authentication');
	});

	await page.goto('/dashboard');
	await expect(page).toHaveURL(/\/auth\?next=%2Fdashboard$/);
});
