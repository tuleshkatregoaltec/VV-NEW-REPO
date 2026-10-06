<script lang="ts">
import { onMount } from 'svelte'
import { goto } from '$app/navigation'
import { resolve } from '$app/paths'
import { get_session, update_password } from '$lib/api/auth'
import AccountContextBar from '$lib/components/auth/AccountContextBar.svelte'
import AuthFlowShell from '$lib/components/auth/AuthFlowShell.svelte'
import PasswordInput from '$lib/components/auth/PasswordInput.svelte'
import { refreshUser } from '$lib/stores/user.svelte'

let newPassword = $state('')
let confirmPassword = $state('')
let loading = $state(false)
let error = $state('')
let success = $state(false)
let hasValidSession = $state(false)
let email = $state<string | null>(null)

let fieldErrors = $state({
	newPassword: '',
	confirmPassword: ''
})

onMount(async () => {
	const session = await get_session()
	if (!session) {
		error = 'Invalid or expired reset link. Please request a new password reset.'
		return
	}

	hasValidSession = true
	email = session.user.email ?? null
})

function validateForm(): boolean {
	fieldErrors = {
		newPassword: '',
		confirmPassword: ''
	}

	let isValid = true

	if (!newPassword) {
		fieldErrors.newPassword = 'Password is required'
		isValid = false
	} else if (newPassword.length < 8) {
		fieldErrors.newPassword = 'Password must be at least 8 characters'
		isValid = false
	}

	if (!confirmPassword) {
		fieldErrors.confirmPassword = 'Please confirm your password'
		isValid = false
	} else if (newPassword !== confirmPassword) {
		fieldErrors.confirmPassword = 'Passwords do not match'
		isValid = false
	}

	return isValid
}

async function handleResetPassword() {
	if (!validateForm()) return

	loading = true
	error = ''

	try {
		const result = await update_password(newPassword)
		if (result.success) {
			await refreshUser()
			success = true
			setTimeout(() => {
				goto(resolve('/dashboard'))
			}, 2000)
		} else {
			error = result.error || 'Failed to update password'
		}
	} finally {
		loading = false
	}
}
</script>

<svelte:head>
	<title>Reset Password - Vitevue</title>
</svelte:head>

<AuthFlowShell
	title={success
		? 'Password updated'
		: hasValidSession
			? 'Create a new password'
			: 'Reset link unavailable'}
	description={success
		? 'Your password has been updated. We’ll send you back to your workspace.'
		: hasValidSession
			? 'Choose a new password for this account.'
			: error}
	eyebrow="Password recovery"
	sideAccent="Account recovery"
	sideTitle="Secure account recovery for the same workspace flow."
	sideCopy="Choose a new password once the recovery session is valid, then return to the guarded workspace."
>
	<svelte:fragment slot="account">
		{#if email}
			<AccountContextBar {email} redirectTo="/auth" />
		{/if}
	</svelte:fragment>

	<svelte:fragment slot="side">
		<div class="space-y-4 rounded-lg border border-[rgba(246,241,231,0.14)] bg-[color:rgba(246,241,231,0.05)] p-5">
			<div class="rounded-lg border border-[rgba(246,241,231,0.14)] bg-[color:rgba(246,241,231,0.05)] p-4">
				<p class="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">
					Recovery flow
				</p>
				<p class="mt-3 text-2xl font-semibold text-white">Secure reset</p>
				<p class="mt-2 text-sm leading-6 text-slate-300">
					Once the password changes, you return to the same guarded application flow as any other
					authenticated session.
				</p>
			</div>
		</div>
	</svelte:fragment>

	{#if success}
		<div class="rounded-lg border border-[rgba(17,122,72,0.2)] bg-success-bg p-6 text-center">
			<p class="text-lg font-semibold text-success">Password updated successfully</p>
			<p class="mt-2 text-sm text-success">Redirecting you to the dashboard now.</p>
		</div>
	{:else if !hasValidSession && error}
		<div class="space-y-5">
			<div class="rounded-lg border border-[rgba(163,36,36,0.2)] bg-error-bg p-6">
				<p class="text-sm font-semibold text-error">Reset link is no longer valid</p>
				<p class="mt-2 text-sm leading-6 text-error">{error}</p>
			</div>
			<a
				href={resolve('/auth')}
				class="inline-flex rounded-md bg-navy px-5 py-3 text-sm font-semibold text-bone transition hover:bg-primary-light"
			>
				Return to sign in
			</a>
		</div>
	{:else}
		{#if error}
			<div class="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
				{error}
			</div>
		{/if}

		<form
			onsubmit={(event) => {
				event.preventDefault();
				handleResetPassword();
			}}
			class="space-y-5"
		>
			<PasswordInput
				label="New password"
				bind:value={newPassword}
				placeholder="Create a new password"
				error={fieldErrors.newPassword}
				required
				autocomplete="new-password"
				showStrength={true}
			/>

			<PasswordInput
				label="Confirm password"
				bind:value={confirmPassword}
				placeholder="Confirm your new password"
				error={fieldErrors.confirmPassword}
				required
				autocomplete="new-password"
			/>

			<button
				type="submit"
				disabled={loading}
				class="w-full rounded-md bg-navy px-4 py-3.5 text-sm font-semibold text-bone transition hover:bg-primary-light disabled:cursor-not-allowed disabled:opacity-50"
			>
				{loading ? 'Updating password...' : 'Update password'}
			</button>
		</form>
	{/if}
</AuthFlowShell>
