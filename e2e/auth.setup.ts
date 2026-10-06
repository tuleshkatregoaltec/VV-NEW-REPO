import { test as setup, expect } from '@playwright/test';
import path from 'path';
import {
	createActiveOrganization,
	loginUser,
	signupUser,
	uniqueEmail
} from './fixtures/real-auth';

const authFile = path.join(__dirname, '.auth/user.json');
const DEFAULT_ADMIN_EMAIL = process.env.FIRST_SUPERUSER ?? 'admin@example.com';
const DEFAULT_ADMIN_PASSWORD = process.env.FIRST_SUPERUSER_PASSWORD ?? 'admin123';
const SETUP_PASSWORD = 'PlaywrightOwner123!';

/**
 * Runs once before other tests to provision an active owner account and save
 * its browser session state for the authenticated chromium project.
 *
 * Run with:
 *   TEST_EMAIL=you@example.com TEST_PASSWORD=yourpassword bunx playwright test --project=setup
 */
setup('authenticate', async ({ page, request }) => {
	const adminEmail = process.env.TEST_EMAIL ?? DEFAULT_ADMIN_EMAIL;
	const adminPassword = process.env.TEST_PASSWORD ?? DEFAULT_ADMIN_PASSWORD;
	const ownerEmail = uniqueEmail('playwright_owner');

	const adminSession = await loginUser(request, adminEmail, adminPassword);
	const ownerSession = await signupUser(request, {
		email: ownerEmail,
		password: SETUP_PASSWORD,
		firstName: 'Playwright',
		lastName: 'Owner'
	});
	await createActiveOrganization(
		request,
		ownerSession.access_token,
		adminSession.access_token,
		`Playwright Org ${Date.now()}`,
		3
	);

	await page.goto('/auth');
	await expect(page.getByRole('heading', { name: 'Sign in to Vitevue' })).toBeVisible();
	await page.getByLabel('Email').fill(ownerEmail);
	await page.getByLabel('Password').fill(SETUP_PASSWORD);
	await page.locator('form').getByRole('button', { name: 'Sign in', exact: true }).click();

	await page.waitForURL(/\/dashboard/, { timeout: 15_000 });

	// Save auth state (cookies + localStorage)
	await page.context().storageState({ path: authFile });
});
