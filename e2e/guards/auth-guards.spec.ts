import { expect, test } from '../fixtures/guards';

test('anonymous user is redirected from dashboard to auth', async ({ page, useAnonymous }) => {
	await useAnonymous();
	await page.goto('/dashboard');
	await expect(page).toHaveURL(/\/auth\?next=%2Fdashboard$/);
});

test('active owner is redirected away from auth to dashboard', async ({ page, usePersona }) => {
	await usePersona('active-owner');
	await page.goto('/auth');
	await expect(page).toHaveURL(/\/dashboard$/);
});

test('pending owner is redirected from protected pages to setup', async ({ page, usePersona }) => {
	await usePersona('pending-owner');
	await page.goto('/dashboard');
	await expect(page).toHaveURL(/\/setup$/);
});

test('past-due owner is redirected from protected pages to renew', async ({ page, usePersona }) => {
	await usePersona('past-due-owner');
	await page.goto('/transactions/sales');
	await expect(page).toHaveURL(/\/renew$/);
});

test('incomplete profile is kept on setup until profile is completed', async ({ page, usePersona }) => {
	await usePersona('incomplete-profile');
	await page.goto('/setup');
	await expect(page).toHaveURL(/\/setup$/);
});

test('active users cannot open renew', async ({ page, usePersona }) => {
	await usePersona('active-owner');
	await page.goto('/renew');
	await expect(page).toHaveURL(/\/dashboard$/);
});

test('payment success requires a session id', async ({ page, usePersona }) => {
	await usePersona('active-owner');
	await page.goto('/payment-success');
	await expect(page).toHaveURL(/\/dashboard$/);
});

test('non-admin user is redirected away from /admin', async ({ page, usePersona }) => {
	await usePersona('active-owner');
	await page.goto('/admin');
	await expect(page).toHaveURL(/\/dashboard$/);
});

test('admin user can access /admin', async ({ page, usePersona }) => {
	await usePersona('admin');
	await page.goto('/admin/organizations');
	await expect(page).toHaveURL(/\/admin\/organizations$/);
});
