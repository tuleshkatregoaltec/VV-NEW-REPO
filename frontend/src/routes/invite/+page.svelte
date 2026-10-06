<script lang="ts">
import { onMount } from 'svelte'
import { goto } from '$app/navigation'
import { resolve } from '$app/paths'
import { authClient, get_session, update_user_profile } from '$lib/api/auth'
import { ApiError } from '$lib/api/client'
import {
	acceptInvite,
	type InviteConflictResponse,
	type ValidateInviteTokenResponse,
	validateInviteToken
} from '$lib/api/organization'
import AccountContextBar from '$lib/components/auth/AccountContextBar.svelte'
import AuthFlowShell from '$lib/components/auth/AuthFlowShell.svelte'
import TextInput from '$lib/components/auth/TextInput.svelte'
import { clearUser, refreshUser } from '$lib/stores/user.svelte'

type Step = 'loading' | 'profile' | 'accept' | 'mismatch' | 'error'

let step = $state<Step>('loading')
let inviteToken = $state('')
let inviteDetails = $state<ValidateInviteTokenResponse | null>(null)
let firstName = $state('')
let lastName = $state('')
let currentEmail = $state('')
let loading = $state(false)
let error = $state('')
let conflictMessage = $state('')

let fieldErrors = $state({
	firstName: '',
	lastName: ''
})

onMount(async () => {
	inviteToken = new URL(window.location.href).searchParams.get('token') || ''
	await syncInviteState()
})

function getAuthPath() {
	return `${resolve('/auth')}?next=${encodeURIComponent(`/invite?token=${inviteToken}`)}`
}

function resetMessages() {
	error = ''
	conflictMessage = ''
	fieldErrors.firstName = ''
	fieldErrors.lastName = ''
}

function setProfileStep(first: string, last: string) {
	firstName = first
	lastName = last
	step = first && last ? 'accept' : 'profile'
}

function getTitle() {
	switch (step) {
		case 'loading':
			return 'Checking your invitation'
		case 'profile':
			return 'Complete your profile'
		case 'accept':
			return `Join ${inviteDetails?.organization_name}`
		case 'mismatch':
			return 'This invite is for a different account'
		case 'error':
			return 'Invitation unavailable'
	}
}

function getDescription() {
	switch (step) {
		case 'loading':
			return 'We are validating the invitation and checking your current session.'
		case 'profile':
			return `Add your name, then we’ll finish joining ${inviteDetails?.organization_name}.`
		case 'accept':
			return `You’re signed in as the invited email and ready to join ${inviteDetails?.organization_name}.`
		case 'mismatch':
			return `This invite is for ${inviteDetails?.email}, but your current session belongs to ${currentEmail}.`
		case 'error':
			return error || 'The invitation link is invalid or expired.'
	}
}

async function syncInviteState() {
	resetMessages()

	if (!inviteToken) {
		error = 'Invitation token is missing.'
		step = 'error'
		return
	}

	step = 'loading'

	try {
		inviteDetails = await validateInviteToken(inviteToken)
	} catch (err: unknown) {
		error =
			err instanceof Error
				? err.message
				: 'Invalid invitation link. Please contact your administrator.'
		step = 'error'
		return
	}

	const session = await get_session()
	if (!session?.user?.email) {
		// eslint-disable-next-line svelte/no-navigation-without-resolve
		await goto(getAuthPath())
		return
	}

	currentEmail = session.user.email
	if (session.user.email.toLowerCase() !== inviteDetails.email.toLowerCase()) {
		step = 'mismatch'
		return
	}

	const user = await refreshUser()
	setProfileStep(
		user?.first_name ?? (session.user.user_metadata?.first_name as string) ?? '',
		user?.last_name ?? (session.user.user_metadata?.last_name as string) ?? ''
	)
}

async function joinOrganization() {
	resetMessages()

	if (step === 'profile') {
		if (!firstName.trim()) {
			fieldErrors.firstName = 'First name is required'
		}
		if (!lastName.trim()) {
			fieldErrors.lastName = 'Last name is required'
		}
		if (fieldErrors.firstName || fieldErrors.lastName) {
			return
		}
	}

	loading = true
	try {
		if (step === 'profile') {
			await update_user_profile(firstName.trim(), lastName.trim())
		}

		const result = await acceptInvite(inviteToken)
		if ('conflict' in result && result.conflict) {
			conflictMessage = getConflictMessage(result)
			return
		}

		await refreshUser()
		goto(resolve('/dashboard'))
	} catch (err: unknown) {
		if (
			err instanceof ApiError &&
			err.status === 409 &&
			err.details &&
			typeof err.details === 'object' &&
			'detail' in err.details
		) {
			conflictMessage = getConflictMessage(
				(err.details as { detail: InviteConflictResponse }).detail
			)
			return
		}
		error = err instanceof Error ? err.message : 'Failed to join organization. Please try again.'
	} finally {
		loading = false
	}
}

async function switchAccount() {
	await authClient.signOut()
	clearUser()
	// eslint-disable-next-line svelte/no-navigation-without-resolve
	await goto(getAuthPath())
}

function getConflictMessage(conflict: InviteConflictResponse): string {
	if (conflict.current_role === 'owner') {
		return `You already own ${conflict.current_org_name}. Transfer ownership or cancel that organization before joining another one.`
	}

	return `You are already a member of ${conflict.current_org_name}. Leave that organization before joining another one.`
}
</script>

<svelte:head>
	<title>Organization Invite - Vitevue</title>
</svelte:head>

<AuthFlowShell
	title={getTitle()}
	description={getDescription()}
	eyebrow="Organization invite"
	sideAccent="Guided join flow"
	sideTitle="Join the right workspace with the right account."
	sideCopy="Vitevue keeps the invite flow narrow: authenticate first, confirm the invited email, add your name if needed, then join the organization."
>
	<svelte:fragment slot="account">
		{#if currentEmail}
			<AccountContextBar email={currentEmail} redirectTo={getAuthPath()} />
		{/if}
	</svelte:fragment>

	<svelte:fragment slot="side">
		<div class="space-y-4 rounded-lg border border-[rgba(246,241,231,0.14)] bg-[color:rgba(246,241,231,0.05)] p-5">
			{#if inviteDetails}
				<div class="rounded-lg border border-[rgba(246,241,231,0.14)] bg-[color:rgba(246,241,231,0.05)] p-4">
					<p class="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Invitation</p>
					<p class="mt-3 text-2xl font-semibold text-white">{inviteDetails.organization_name}</p>
					<p class="mt-2 text-sm leading-6 text-slate-300">Invited email: {inviteDetails.email}</p>
				</div>
			{/if}
			<div class="grid gap-3">
				<div class="rounded-md border border-[rgba(246,241,231,0.12)] bg-[color:rgba(246,241,231,0.04)] px-4 py-3 text-sm text-slate-200">
					Authenticate with the invited account first
				</div>
				<div class="rounded-md border border-[rgba(246,241,231,0.12)] bg-[color:rgba(246,241,231,0.04)] px-4 py-3 text-sm text-slate-200">
					Add your name only if it is still missing
				</div>
				<div class="rounded-md border border-[rgba(246,241,231,0.12)] bg-[color:rgba(246,241,231,0.04)] px-4 py-3 text-sm text-slate-200">
					Join the workspace and let the normal guard flow take over
				</div>
			</div>
		</div>
	</svelte:fragment>

	{#if error && step !== 'error'}
		<div class="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
			{error}
		</div>
	{/if}

	{#if conflictMessage}
		<div class="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
			{conflictMessage}
		</div>
	{/if}

	{#if step === 'loading'}
		<div class="rounded-lg border border-slate-200 bg-slate-50/80 p-8 text-center">
			<div
				class="mx-auto h-14 w-14 animate-spin rounded-full border-4 border-slate-200 border-t-navy"
			></div>
			<p class="mt-6 text-lg font-semibold text-fg-1">Loading invitation</p>
			<p class="mt-2 text-sm text-slate-600">This should only take a moment.</p>
		</div>
	{:else if step === 'error'}
		<div class="space-y-5">
			<div class="rounded-lg border border-[rgba(163,36,36,0.2)] bg-error-bg p-6">
				<p class="text-sm font-semibold text-error">Invitation unavailable</p>
				<p class="mt-2 text-sm leading-6 text-error">{error}</p>
			</div>
			<a
				href={resolve('/auth')}
				class="inline-flex rounded-md bg-navy px-5 py-3 text-sm font-semibold text-bone transition hover:bg-primary-light"
			>
				Return to sign in
			</a>
		</div>
	{:else if step === 'mismatch'}
		<div class="space-y-5">
			<div class="rounded-lg border border-[rgba(165,90,19,0.2)] bg-warning-bg p-6">
				<p class="text-sm font-semibold text-warning">Wrong account</p>
				<p class="mt-2 text-sm leading-6 text-warning">
					You are signed in as <span class="font-semibold">{currentEmail}</span>, but this invite is
					for <span class="font-semibold">{inviteDetails?.email}</span>.
				</p>
			</div>
			<div class="flex flex-col gap-3 sm:flex-row">
				<button
					type="button"
					onclick={switchAccount}
					class="flex-1 rounded-md bg-navy px-5 py-3 text-sm font-semibold text-bone transition hover:bg-primary-light"
				>
					Use the invited account instead
				</button>
				<a
					href={resolve('/dashboard')}
					class="rounded-md border border-slate-300 px-5 py-3 text-center text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
				>
					Go to current workspace
				</a>
			</div>
		</div>
	{:else if step === 'profile'}
		<form
			onsubmit={(event) => {
				event.preventDefault();
				joinOrganization();
			}}
			class="space-y-5"
		>
			<div class="grid gap-5 sm:grid-cols-2">
				<TextInput
					label="First name"
					bind:value={firstName}
					error={fieldErrors.firstName}
					placeholder="John"
					autocomplete="given-name"
				/>
				<TextInput
					label="Last name"
					bind:value={lastName}
					error={fieldErrors.lastName}
					placeholder="Doe"
					autocomplete="family-name"
				/>
			</div>
			<button
				type="submit"
				disabled={loading}
				class="w-full rounded-md bg-navy px-5 py-3 text-sm font-semibold text-bone transition hover:bg-primary-light disabled:cursor-not-allowed disabled:opacity-50"
			>
				{loading ? 'Joining organization...' : `Join ${inviteDetails?.organization_name}`}
			</button>
		</form>
	{:else}
		<div class="space-y-5">
			<div class="rounded-lg border border-slate-200 bg-slate-50/80 p-6">
				<p class="text-sm font-semibold text-slate-900">Ready to join</p>
				<p class="mt-2 text-sm leading-6 text-slate-600">
					You are signed in as the invited user and your profile is complete.
				</p>
			</div>
			<button
				type="button"
				onclick={joinOrganization}
				disabled={loading}
				class="w-full rounded-md bg-navy px-5 py-3 text-sm font-semibold text-bone transition hover:bg-primary-light disabled:cursor-not-allowed disabled:opacity-50"
			>
				{loading ? 'Joining organization...' : `Join ${inviteDetails?.organization_name}`}
			</button>
		</div>
	{/if}
</AuthFlowShell>
