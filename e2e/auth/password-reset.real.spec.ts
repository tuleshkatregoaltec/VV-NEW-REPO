import { expect, test } from '@playwright/test';

import {
	DEFAULT_PASSWORD,
	extractOtp,
	loginViaUi,
	seedBrowserSession,
	signupUser,
	uniqueEmail,
	verifyOtp,
	waitForMailboxMessage
} from '../fixtures/real-auth';

test('user can reset password from the emailed recovery link and sign in with the new password', async ({
	page,
	request,
	browser
}) => {
	const email = uniqueEmail('reset');
	const newPassword = 'NewPassword123!';

	await signupUser(request, {
		email,
		password: DEFAULT_PASSWORD,
		firstName: 'Reset',
		lastName: 'User'
	});

	await page.goto('/auth');
	await page.getByRole('button', { name: 'Forgot password?' }).click();
	await page.getByLabel('Email').fill(email);
	await page.getByRole('button', { name: 'Send reset email' }).click();
	await expect(page.getByRole('heading', { name: 'Check your inbox' })).toBeVisible();

	const message = await waitForMailboxMessage(request, email, 'Reset Your Password');
	const recoverySession = await verifyOtp(request, email, extractOtp(message), 'recovery');

	await seedBrowserSession(page, recoverySession);
	await page.goto('/reset');
	await expect(page.getByRole('heading', { name: 'Create a new password' })).toBeVisible();
	await page.getByLabel('New password').fill(newPassword);
	await page.getByLabel('Confirm password').fill(newPassword);
	await page.getByRole('button', { name: 'Update password' }).click();

	await expect(page.getByText('Password updated successfully')).toBeVisible();
	await expect(page).toHaveURL(/\/setup$/, { timeout: 10_000 });

	const freshContext = await browser.newContext();
	const freshPage = await freshContext.newPage();

	await freshPage.goto('/auth');
	await freshPage.getByLabel('Email').fill(email);
	await freshPage.getByLabel('Password').fill(DEFAULT_PASSWORD);
	await freshPage.locator('form').getByRole('button', { name: 'Sign in', exact: true }).click();
	await expect(freshPage.getByText('Invalid login credentials')).toBeVisible();

	await loginViaUi(freshPage, email, newPassword);
	await expect(freshPage).toHaveURL(/\/setup|\/dashboard/);

	await freshContext.close();
});
