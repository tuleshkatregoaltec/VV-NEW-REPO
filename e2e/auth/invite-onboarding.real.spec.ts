import { expect, test, type APIRequestContext } from '@playwright/test';

import {
	createActiveOrganization,
	createOrganizationInvitation,
	extractOtp,
	loginUser,
	loginViaUi,
	seedBrowserSession,
	signupUser,
	uniqueEmail,
	verifyOtp,
	waitForNextMailboxMessage
} from '../fixtures/real-auth';

const OWNER_PASSWORD = 'OwnerPassword123!';
const MEMBER_PASSWORD = 'MemberPassword123!';
const WRONG_PASSWORD = 'WrongPassword123!';
const ADMIN_EMAIL = process.env.FIRST_SUPERUSER ?? 'admin@example.com';
const ADMIN_PASSWORD = process.env.FIRST_SUPERUSER_PASSWORD ?? 'admin123';

async function createOwnerWithActiveOrganization(request: APIRequestContext) {
	const ownerEmail = uniqueEmail('owner');

	const adminSession = await loginUser(request, ADMIN_EMAIL, ADMIN_PASSWORD);
	const ownerSession = await signupUser(request, {
		email: ownerEmail,
		password: OWNER_PASSWORD,
		firstName: 'Owner',
		lastName: 'User'
	});

	const { organizationId } = await createActiveOrganization(
		request,
		ownerSession.access_token,
		adminSession.access_token,
		'Invite Test Org',
		3
	);

	return { ownerEmail, ownerSession, organizationId };
}

test('new invitee can authenticate from the invite page, complete their profile, and join', async ({
	page,
	request
}) => {
	const { ownerSession } = await createOwnerWithActiveOrganization(request);
	const inviteeEmail = uniqueEmail('invitee');
	const inviteToken = await createOrganizationInvitation(
		request,
		ownerSession.access_token,
		inviteeEmail
	);
	const initialInviteMessage = await waitForNextMailboxMessage(request, inviteeEmail);

	await page.context().clearCookies();
	await page.goto('/');
	await page.evaluate(() => window.localStorage.clear());

	await page.goto(`/invite?token=${inviteToken}`);
	await expect(page).toHaveURL(/\/auth\?next=/, { timeout: 10_000 });
	const verificationSession = await verifyOtp(
		request,
		inviteeEmail,
		extractOtp(initialInviteMessage),
		'magiclink'
	);
	await seedBrowserSession(page, verificationSession);
	await page.goto(`/invite?token=${inviteToken}`);

	await expect(page.getByRole('heading', { name: 'Complete your profile' })).toBeVisible({
		timeout: 10_000
	});
	await page.getByLabel('First Name').fill('Invited');
	await page.getByLabel('Last Name').fill('Member');
	await page.getByRole('button', { name: 'Join Invite Test Org' }).click();

	await expect(page).toHaveURL(/\/dashboard$/, { timeout: 10_000 });
});

test('existing invitee with a complete profile can accept directly from the invite page', async ({
	page,
	request
}) => {
	const { ownerSession } = await createOwnerWithActiveOrganization(request);
	const inviteeEmail = uniqueEmail('member');

	await signupUser(request, {
		email: inviteeEmail,
		password: MEMBER_PASSWORD,
		firstName: 'Existing',
		lastName: 'Member'
	});

	const inviteToken = await createOrganizationInvitation(
		request,
		ownerSession.access_token,
		inviteeEmail
	);

	await page.context().clearCookies();
	await page.goto('/');
	await page.evaluate(() => window.localStorage.clear());
	await loginViaUi(page, inviteeEmail, MEMBER_PASSWORD);
	await expect(page).toHaveURL(/\/setup|\/dashboard/, {
		timeout: 10_000
	});

	await page.goto(`/invite?token=${inviteToken}`);
	await expect(page.getByRole('heading', { name: 'Join Invite Test Org' })).toBeVisible({
		timeout: 10_000
	});
	await expect(page.getByRole('button', { name: 'Join Invite Test Org' })).toBeVisible();
	await expect(page.getByLabel('First Name')).toHaveCount(0);
	await page.getByRole('button', { name: 'Join Invite Test Org' }).click();

	await expect(page).toHaveURL(/\/dashboard$/, { timeout: 10_000 });
});

test('invite page rejects a logged-in user whose email does not match the invitation', async ({
	page,
	request
}) => {
	const { ownerSession } = await createOwnerWithActiveOrganization(request);
	const inviteeEmail = uniqueEmail('member');
	const wrongEmail = uniqueEmail('wrong');

	await signupUser(request, {
		email: wrongEmail,
		password: WRONG_PASSWORD,
		firstName: 'Wrong',
		lastName: 'User'
	});

	const inviteToken = await createOrganizationInvitation(
		request,
		ownerSession.access_token,
		inviteeEmail
	);
	const wrongSession = await loginUser(request, wrongEmail, WRONG_PASSWORD);

	await page.context().clearCookies();
	await page.goto('/');
	await page.evaluate(() => window.localStorage.clear());
	await seedBrowserSession(page, wrongSession);
	await page.goto(`/invite?token=${inviteToken}`);

	await expect(page.getByText('Wrong account')).toBeVisible({
		timeout: 10_000
	});
	await expect(page.getByText(inviteeEmail, { exact: true })).toBeVisible();
	await expect(page.getByRole('button', { name: 'Join Invite Test Org' })).toHaveCount(0);
});

test('invalid invite token shows the unavailable state', async ({ page }) => {
	await page.goto('/invite?token=invalid-token');

	await expect(page.getByRole('heading', { name: 'Invitation unavailable' })).toBeVisible({
		timeout: 10_000
	});
	await expect(page.getByRole('link', { name: 'Return to sign in' })).toBeVisible();
});
