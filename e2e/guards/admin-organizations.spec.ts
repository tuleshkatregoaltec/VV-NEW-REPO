import { expect, test } from '../fixtures/guards';

test('admin organizations page renders organization data', async ({ page, usePersona }) => {
	await usePersona('admin');

	await page.route('**/api/v1/admin/organizations', async (route) => {
		await route.fulfill({
			status: 200,
			contentType: 'application/json',
			body: JSON.stringify([
				{
					id: 'org-1',
					name: 'Acme Holdings',
					owner_email: 'owner@example.com',
					user_count: 2,
					max_users: 5,
					subscription_status: 'active',
					created_at: '2026-03-01T00:00:00Z'
				}
			])
		});
	});

	await page.goto('/admin/organizations');

	await expect(page.getByRole('heading', { name: 'Organizations' })).toBeVisible();
	await expect(page.getByRole('button', { name: 'Create user' })).toBeVisible();
	await expect(page.getByText('Acme Holdings')).toBeVisible();
	await expect(page.getByText('owner@example.com')).toBeVisible();
});
