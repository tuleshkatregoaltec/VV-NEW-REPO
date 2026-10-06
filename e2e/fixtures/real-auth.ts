import { expect, type APIRequestContext, type Page } from '@playwright/test';

const AUTH_BASE_URL = process.env.PLAYWRIGHT_AUTH_BASE_URL ?? 'http://127.0.0.1:9999';
const API_BASE_URL = process.env.PLAYWRIGHT_API_BASE_URL ?? 'http://127.0.0.1:8000';
const INBUCKET_BASE_URL =
	process.env.PLAYWRIGHT_INBUCKET_BASE_URL ?? 'http://127.0.0.1:9000';
export const DEFAULT_PASSWORD = 'Password123!';

type AuthSession = {
	access_token: string;
	refresh_token: string;
	expires_at: number;
	expires_in: number;
	token_type: string;
	user: {
		id: string;
		email: string;
		[key: string]: unknown;
	};
};

type MailMessage = {
	id: string;
	subject: string;
	body?: {
		text?: string;
		html?: string;
	};
};

type MailboxMessageSummary = {
	id: string;
	subject: string;
};

export function uniqueEmail(prefix: string): string {
	return `${prefix}_${Date.now()}_${Math.floor(Math.random() * 100000)}@example.com`;
}

export async function signupUser(
	request: APIRequestContext,
	options: {
		email: string;
		password?: string;
		firstName?: string;
		lastName?: string;
	}
): Promise<AuthSession> {
	const response = await request.post(`${AUTH_BASE_URL}/signup`, {
		data: {
			email: options.email,
			password: options.password ?? DEFAULT_PASSWORD,
			data: {
				first_name: options.firstName ?? 'Test',
				last_name: options.lastName ?? 'User'
			}
		}
	});

	expect(response.ok()).toBeTruthy();
	return (await response.json()) as AuthSession;
}

export async function loginUser(
	request: APIRequestContext,
	email: string,
	password = DEFAULT_PASSWORD
): Promise<AuthSession> {
	const response = await request.post(`${AUTH_BASE_URL}/token?grant_type=password`, {
		data: {
			email,
			password
		}
	});

	expect(response.ok()).toBeTruthy();
	return (await response.json()) as AuthSession;
}

export async function verifyOtp(
	request: APIRequestContext,
	email: string,
	token: string,
	type: 'signup' | 'magiclink' | 'recovery' | 'email_change'
): Promise<AuthSession> {
	const response = await request.post(`${AUTH_BASE_URL}/verify`, {
		data: {
			email,
			token,
			type
		}
	});

	expect(response.ok()).toBeTruthy();
	return (await response.json()) as AuthSession;
}

export async function backendPost(
	request: APIRequestContext,
	path: string,
	token: string,
	data?: unknown
) {
	return request.post(`${API_BASE_URL}${path}`, {
		headers: {
			Authorization: `Bearer ${token}`
		},
		data
	});
}

export async function backendPatch(
	request: APIRequestContext,
	path: string,
	token: string,
	data?: unknown
) {
	return request.patch(`${API_BASE_URL}${path}`, {
		headers: {
			Authorization: `Bearer ${token}`
		},
		data
	});
}

export async function waitForMailboxMessage(
	request: APIRequestContext,
	email: string,
	subject: string
): Promise<MailMessage> {
	const mailbox = email.split('@')[0];
	const deadline = Date.now() + 20_000;

	while (Date.now() < deadline) {
		const messages = await listMailboxMessages(request, mailbox);
		if (messages.length > 0) {
			const latest = messages.find((message) => message.subject === subject);
			if (latest) {
				return getMailboxMessage(request, mailbox, latest.id);
			}
		}

		await new Promise((resolve) => setTimeout(resolve, 500));
	}

	throw new Error(`Timed out waiting for "${subject}" email for ${email}`);
}

export async function waitForNextMailboxMessage(
	request: APIRequestContext,
	email: string,
	knownMessageIds: string[] = []
): Promise<MailMessage> {
	const mailbox = email.split('@')[0];
	const deadline = Date.now() + 20_000;
	const knownIds = new Set(knownMessageIds);

	while (Date.now() < deadline) {
		const messages = await listMailboxMessages(request, mailbox);
		const nextMessage = messages.find((message) => !knownIds.has(message.id));
		if (nextMessage) {
			return getMailboxMessage(request, mailbox, nextMessage.id);
		}

		await new Promise((resolve) => setTimeout(resolve, 500));
	}

	throw new Error(`Timed out waiting for next email for ${email}`);
}

async function listMailboxMessages(
	request: APIRequestContext,
	mailbox: string
): Promise<MailboxMessageSummary[]> {
	const response = await request.get(`${INBUCKET_BASE_URL}/api/v1/mailbox/${mailbox}`);
	if (!response.ok()) {
		return [];
	}

	return (await response.json()) as MailboxMessageSummary[];
}

async function getMailboxMessage(
	request: APIRequestContext,
	mailbox: string,
	messageId: string
): Promise<MailMessage> {
	const response = await request.get(`${INBUCKET_BASE_URL}/api/v1/mailbox/${mailbox}/${messageId}`);
	expect(response.ok()).toBeTruthy();
	return (await response.json()) as MailMessage;
}

export function extractOtp(message: MailMessage): string {
	const body = message.body?.text ?? '';
	const match = body.match(/enter the code:\s*(\d{6})/i);
	if (!match) {
		throw new Error(`Could not find OTP in email body: ${body}`);
	}
	return match[1];
}

export function extractFirstUrl(message: MailMessage): string {
	const body = message.body?.text ?? '';
	const match = body.match(/https?:\/\/[^\s)]+/);
	if (!match) {
		throw new Error(`Could not find URL in email body: ${body}`);
	}
	return match[0];
}

export function extractQueryParam(url: string, key: string): string {
	const parsed = new URL(url);
	const value = parsed.searchParams.get(key);
	if (!value) {
		throw new Error(`Could not find "${key}" in URL: ${url}`);
	}
	return value;
}

export function extractRedirectUrl(message: MailMessage): string {
	const authUrl = extractFirstUrl(message);
	const redirectUrl =
		new URL(authUrl).searchParams.get('redirect_to') ??
		new URL(authUrl).searchParams.get('redirectTo');

	if (!redirectUrl) {
		throw new Error(`Could not find redirect target in email URL: ${authUrl}`);
	}

	return decodeURIComponent(redirectUrl);
}

export function extractInvitationToken(message: MailMessage): string {
	const body = `${message.body?.text ?? ''}\n${message.body?.html ?? ''}`;
	const match = body.match(/token=([A-Za-z0-9_-]+)/);
	if (!match) {
		throw new Error(`Could not find invitation token in email body: ${body}`);
	}
	return match[1];
}

export function rewriteEmailLink(url: string, redirectTo: string): string {
	const rewritten = url
		.replace('https://demo-auth.vitevue.com', AUTH_BASE_URL)
		.replace('http://localhost:9999', AUTH_BASE_URL)
		.replace('https://demo.vitevue.com', redirectTo)
		.replace('http://localhost:5173', redirectTo)
		.replace('http://127.0.0.1:5173', redirectTo);

	return rewritten;
}

export async function seedBrowserSession(page: Page, session: AuthSession) {
	await page.addInitScript((authSession) => {
		window.localStorage.setItem('authentication', JSON.stringify(authSession));
	}, session);
}

export async function loginViaUi(page: Page, email: string, password = DEFAULT_PASSWORD) {
	await page.goto('/auth');
	await page.getByLabel('Email').fill(email);
	await page.getByLabel('Password').fill(password);
	await page.locator('form').getByRole('button', { name: 'Sign in', exact: true }).click();
}

export async function createActiveOrganization(
	request: APIRequestContext,
	ownerToken: string,
	adminToken: string,
	name: string,
	maxUsers = 3
): Promise<{ organizationId: string }> {
	const createResponse = await backendPost(request, '/api/v1/organization/create', ownerToken, {
		name,
		max_users: maxUsers
	});
	expect(createResponse.ok()).toBeTruthy();
	const createJson = (await createResponse.json()) as { organization_id: string };

	const activateResponse = await backendPatch(
		request,
		`/api/v1/admin/organizations/${createJson.organization_id}/subscription`,
		adminToken,
		{ status: 'active' }
	);
	expect(activateResponse.ok()).toBeTruthy();

	return { organizationId: createJson.organization_id };
}

export async function createOrganizationInvitation(
	request: APIRequestContext,
	ownerToken: string,
	email: string
): Promise<string> {
	const response = await backendPost(request, '/api/v1/organization/invite-user', ownerToken, {
		email
	});
	expect(response.ok()).toBeTruthy();
	const json = (await response.json()) as { invitation_token: string };
	return json.invitation_token;
}
