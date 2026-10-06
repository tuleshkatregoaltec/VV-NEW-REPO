import type {
	AuthChangeEvent,
	AuthOtpResponse,
	AuthResponse,
	AuthTokenResponsePassword,
	Session,
	UserResponse
} from '@supabase/auth-js'
import { AuthClient } from '@supabase/auth-js'
import { browser } from '$app/environment'
import { env } from '$env/dynamic/public'
import { client } from './client'
import type { AuthMeResponse, UpdateProfileResponse } from './generated/hey-api/types.gen'

export type { AuthMeResponse, UpdateProfileResponse }
export type AuthenticatedUser = AuthMeResponse

export const authClient = new AuthClient({
	url: env.PUBLIC_AUTH_BASE_URL,
	storageKey: 'authentication',
	detectSessionInUrl: true,
	persistSession: true
})

const authSearchParams = ['code', 'state', 'provider_token', 'provider_refresh_token', 'error']

authClient.onAuthStateChange((event: AuthChangeEvent) => {
	if (!browser) return

	if (event === 'SIGNED_IN' || event === 'TOKEN_REFRESHED') {
		const url = new URL(window.location.href)
		authSearchParams.forEach((param) => {
			url.searchParams.delete(param)
		})
		window.history.replaceState({}, '', url)
	}
})

export type AuthResult<T = unknown> = {
	success: boolean
	error?: string
	data?: T
}

type AuthResultData<T extends { data?: unknown | null }> = NonNullable<T['data']>

function toAuthResult<
	TResponse extends { error: { message?: string } | null; data?: unknown | null }
>(res: TResponse, fallbackMessage: string): AuthResult<AuthResultData<TResponse>> {
	if (!res.error) {
		return res.data !== undefined
			? { success: true, data: (res.data ?? undefined) as AuthResultData<TResponse> | undefined }
			: { success: true }
	}

	return { success: false, error: res.error.message || fallbackMessage }
}

export async function get_access_token(): Promise<string | undefined> {
	const res = await authClient.getSession()

	if (res.data && !res.error) {
		return res.data.session?.access_token
	}
}

/** Login with email/password. */
export async function login_with_email_pass(
	email: string,
	password: string
): Promise<AuthResult<AuthResultData<AuthTokenResponsePassword>>> {
	const res = await authClient.signInWithPassword({ email, password })
	return toAuthResult(res, 'Login failed')
}

/** Sign up with email/password and optional metadata. */
export async function sign_up_with_password(
	email: string,
	password: string,
	firstName: string,
	lastName: string,
	redirectPath = '/setup'
): Promise<AuthResult<AuthResultData<AuthResponse>>> {
	const res = await authClient.signUp({
		email,
		password,
		options: {
			data: {
				first_name: firstName,
				last_name: lastName
			},
			emailRedirectTo: `${window.location.origin}${redirectPath}`
		}
	})

	return toAuthResult(res, 'Sign up failed')
}

/** Send a passwordless sign-in code or magic link. */
export async function sign_in_with_magic_link(
	email: string
): Promise<AuthResult<AuthResultData<AuthOtpResponse>>> {
	return sign_in_with_magic_link_to(email)
}

export async function sign_in_with_magic_link_to(
	email: string,
	redirectPath = '/dashboard'
): Promise<AuthResult<AuthResultData<AuthOtpResponse>>> {
	const res = await authClient.signInWithOtp({
		email,
		options: {
			emailRedirectTo: `${window.location.origin}${redirectPath}`
		}
	})

	return toAuthResult(res, 'Failed to send magic link')
}

/** Send a passwordless sign-up flow with optional metadata. */
export async function sign_up_with_magic_link(
	email: string,
	firstName: string,
	lastName: string,
	redirectPath = '/dashboard'
): Promise<AuthResult<AuthResultData<AuthOtpResponse>>> {
	const res = await authClient.signInWithOtp({
		email,
		options: {
			data: {
				first_name: firstName,
				last_name: lastName
			},
			emailRedirectTo: `${window.location.origin}${redirectPath}`
		}
	})

	return toAuthResult(res, 'Failed to send magic link')
}

/** Verify an email OTP code. */
export async function verify_otp(
	email: string,
	token: string,
	type: 'signup' | 'magiclink' | 'recovery' | 'email_change' = 'signup'
): Promise<AuthResult<AuthResultData<AuthResponse>>> {
	const res = await authClient.verifyOtp({
		email,
		token,
		type
	})

	return toAuthResult(res, 'OTP verification failed')
}

/** Resend an OTP code. */
export async function resend_otp(
	email: string,
	type: 'signup' | 'email_change' = 'signup'
): Promise<AuthResult> {
	const res = await authClient.resend({
		email,
		type
	})

	return toAuthResult(res, 'Failed to resend OTP')
}

/** Request a password reset email. */
export async function request_password_reset(email: string): Promise<AuthResult> {
	const res = await authClient.resetPasswordForEmail(email, {
		redirectTo: `${window.location.origin}/reset`
	})

	return toAuthResult(res, 'Failed to send reset email')
}

/** Update the current user's password. */
export async function update_password(
	newPassword: string
): Promise<AuthResult<AuthResultData<UserResponse>>> {
	const res = await authClient.updateUser({
		password: newPassword
	})

	return toAuthResult(res, 'Failed to update password')
}

/** Get the current auth session. */
export async function get_session(): Promise<Session | null> {
	const res = await authClient.getSession()
	return res.data?.session || null
}

/** Listen to auth state changes. */
export function on_auth_state_change(
	callback: (event: AuthChangeEvent, session: Session | null) => void
): { data: { subscription: { unsubscribe: () => void } } } {
	return authClient.onAuthStateChange(callback)
}

/** Get current user info from the backend. */
export async function me(): Promise<AuthMeResponse> {
	return client.get<AuthMeResponse>('/api/v1/auth/me')
}

/** Update current user's profile through the backend API. */
export async function update_user_profile(
	firstName: string,
	lastName: string
): Promise<UpdateProfileResponse> {
	return client.post<UpdateProfileResponse>('/api/v1/auth/update-profile', {
		first_name: firstName,
		last_name: lastName
	})
}

/** Sign out the current user and redirect. */
export async function logout(redirectTo = '/'): Promise<void> {
	try {
		const res = await authClient.signOut()
		if (res.error) {
			console.error('Supabase logout error:', res.error.message)
		}
	} catch (e) {
		console.error('Supabase logout error:', e)
	}

	const { clearUser } = await import('$lib/stores/user.svelte')
	clearUser()

	window.location.href = redirectTo
}
