import { test, expect } from '@playwright/test';

/**
 * Tests for the feasibility wizard. Runs with authenticated session.
 */

test('feasibility page loads without redirecting', async ({ page }) => {
	await page.goto('/feasibility');
	await expect(page).not.toHaveURL(/\/auth/);
});

test('feasibility page shows the saved studies workspace on load', async ({ page }) => {
	await page.goto('/feasibility');
	await expect(page.getByRole('heading', { name: 'Saved studies workspace' })).toBeVisible({
		timeout: 10_000
	});
	await expect(page.getByRole('button', { name: 'New study' }).first()).toBeVisible();
});

test('feasibility new-study flow exposes plot search', async ({ page }) => {
	await page.goto('/feasibility');
	await page.getByRole('button', { name: 'New study' }).first().click();
	await expect(page.getByRole('heading', { name: 'Set up the underwriting workspace' })).toBeVisible({
		timeout: 10_000
	});
	await page.getByRole('button', { name: 'Select plot' }).click();
	await expect(page.getByPlaceholder('Plot, project, community')).toBeVisible({ timeout: 10_000 });
});

test('feasibility new-study setup shows core workflow controls', async ({ page }) => {
	await page.goto('/feasibility');
	await page.getByRole('button', { name: 'New study' }).first().click();
	await expect(page.getByLabel('Study name')).toBeVisible({
		timeout: 10_000
	});
	await expect(page.getByRole('button', { name: 'Build to sell' })).toBeVisible();
	await expect(page.getByRole('button', { name: 'Select plot' })).toBeVisible();
	await expect(page.getByRole('button', { name: 'Create study' })).toBeDisabled();
});
