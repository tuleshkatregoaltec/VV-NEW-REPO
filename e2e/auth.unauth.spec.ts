import { test, expect } from '@playwright/test';

/**
 * Tests that run without an authenticated session.
 * Verifies that protected routes redirect unauthenticated users correctly.
 */

test('unauthenticated user visiting /dashboard is redirected to /auth', async ({ page }) => {
	await page.goto('/dashboard');
	await expect(page).toHaveURL(/\/auth/);
});

test('unauthenticated user visiting /feasibility is redirected to /auth', async ({ page }) => {
	await page.goto('/feasibility');
	await expect(page).toHaveURL(/\/auth/);
});

test('unauthenticated user visiting /transactions/sales is redirected to /auth', async ({ page }) => {
	await page.goto('/transactions/sales');
	await expect(page).toHaveURL(/\/auth/);
});

test('unauthenticated user visiting /admin is redirected to /auth', async ({ page }) => {
	await page.goto('/admin');
	await expect(page).toHaveURL(/\/auth/);
});

test('/auth page renders sign in form', async ({ page }) => {
	await page.goto('/auth');
	await expect(page.getByRole('heading', { name: 'Sign in to Vitevue' })).toBeVisible();
	await expect(page.getByLabel('Email')).toBeVisible();
	await expect(page.getByLabel('Password')).toBeVisible();
	await expect(
		page.locator('form').getByRole('button', { name: 'Sign in', exact: true })
	).toBeVisible();
});

test('sign in with wrong credentials shows error', async ({ page }) => {
	await page.goto('/auth');
	await page.getByLabel('Email').fill('wrong@example.com');
	await page.getByLabel('Password').fill('wrongpassword');
	await page.locator('form').getByRole('button', { name: 'Sign in', exact: true }).click();

	// Should stay on /auth and show an error
	await expect(page).toHaveURL(/\/auth/);
	await expect(page.getByText('Invalid login credentials')).toBeVisible({ timeout: 10_000 });
});

test('switching to signup view shows create account form', async ({ page }) => {
	await page.goto('/auth');
	await page.getByRole('button', { name: 'Create account' }).click();
	await expect(page.getByRole('heading', { name: 'Create your account' })).toBeVisible();
});

test('forgot password flow shows reset form', async ({ page }) => {
	await page.goto('/auth');
	await page.getByRole('button', { name: 'Forgot password?' }).click();
	await expect(page.getByRole('heading', { name: 'Reset your password' })).toBeVisible();
	await expect(page.getByRole('button', { name: 'Send reset email' })).toBeVisible();
});
