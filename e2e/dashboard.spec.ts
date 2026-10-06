import { test, expect } from '@playwright/test';

/**
 * Tests for the main dashboard. Runs with authenticated session.
 */

test('dashboard loads and shows navigation', async ({ page }) => {
	await page.goto('/dashboard');
	await expect(page).toHaveURL(/\/dashboard/);
	// Navbar should be present
	await expect(page.locator('nav')).toBeVisible();
});

test('dashboard does not redirect to /auth', async ({ page }) => {
	await page.goto('/dashboard');
	await expect(page).not.toHaveURL(/\/auth/);
});
