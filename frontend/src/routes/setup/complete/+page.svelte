<script lang="ts">
import { onMount } from 'svelte'
import { goto } from '$app/navigation'
import { resolve } from '$app/paths'
import { page } from '$app/stores'
import { syncAfterCheckout } from '$lib/api/billing'
import { ApiError } from '$lib/api/client'
import { inviteUserByEmail } from '$lib/api/organization'
import AccountContextBar from '$lib/components/auth/AccountContextBar.svelte'
import AuthFlowShell from '$lib/components/auth/AuthFlowShell.svelte'
import { currentUser, refreshUser } from '$lib/stores/user.svelte'

let status = $state<'syncing' | 'completed' | 'failed'>('syncing')
let seats = $state(0)
let inviteEmails = $state<string[]>([''])
let invitationErrors = $state<string[]>([])
let sendingInvites = $state(false)
let error = $state('')

const currentEmail = $derived(currentUser.data?.email ?? null)

onMount(async () => {
	const sessionId = $page.url.searchParams.get('session_id')
	if (!sessionId) {
		error = 'Invalid payment session.'
		status = 'failed'
		return
	}

	try {
		const result = await syncAfterCheckout(sessionId)
		if (result.status === 'active' || result.status === 'trialing') {
			seats = result.seats
			await refreshUser()
			if (result.seats <= 1) {
				goto(resolve('/dashboard'))
				return
			}
			status = 'completed'
			return
		}

		status = 'failed'
		error = `Subscription status: ${result.status}. Please contact support if this persists.`
	} catch (err: unknown) {
		status = 'failed'
		error =
			err instanceof Error ? err.message : 'Failed to sync subscription. Please contact support.'
	}
})

function addEmailField() {
	inviteEmails = [...inviteEmails, '']
}

function removeEmailField(index: number) {
	inviteEmails = inviteEmails.filter((_, i) => i !== index)
}

function validateEmail(email: string): boolean {
	return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
}

async function handleSendInvitations() {
	invitationErrors = []
	const validEmails = inviteEmails.map((email) => email.trim()).filter(Boolean)

	if (validEmails.length === 0) {
		goto(resolve('/dashboard'))
		return
	}

	const invalidEmails = validEmails.filter((email) => !validateEmail(email))
	if (invalidEmails.length > 0) {
		invitationErrors = invalidEmails.map((email) => `Invalid email format: ${email}`)
		return
	}

	sendingInvites = true
	const results = await Promise.all(
		validEmails.map(async (email) => {
			try {
				await inviteUserByEmail(email)
				return { email, success: true }
			} catch (err: unknown) {
				return {
					email,
					success: false,
					error:
						err instanceof ApiError || err instanceof Error
							? err.message
							: 'Failed to send invitation'
				}
			}
		})
	)

	const errors = results
		.filter((result) => !result.success)
		.map((result) => `${result.email}: ${result.error}`)

	if (errors.length > 0) {
		invitationErrors = errors
		sendingInvites = false
		return
	}

	goto(resolve('/dashboard'))
}
</script>

<svelte:head>
	<title>Setup Complete - Vitevue</title>
</svelte:head>

<AuthFlowShell
	title={status === 'syncing'
		? 'Activating your workspace'
		: status === 'failed'
			? 'We could not finish setup'
			: 'Invite your team'}
	description={status === 'syncing'
		? 'We are confirming your subscription and preparing the organization you just created.'
		: status === 'failed'
			? 'Your payment returned, but we could not finish syncing the subscription automatically.'
			: 'Your workspace is active. Add teammates now or skip and invite them later from organization settings.'}
	eyebrow="Workspace setup"
	step="3"
	totalSteps={3}
	stepLabel="Finish"
	sideAccent="Activation complete"
	sideTitle="Billing is done. This final step is just about getting the right people in."
	sideCopy="You can skip invites entirely and do them later. We only ask now because it is the most convenient moment to set up the team."
>
	<svelte:fragment slot="account">
		<AccountContextBar email={currentEmail} label="Owner account" redirectTo="/auth" />
	</svelte:fragment>

	<svelte:fragment slot="side">
		<div class="space-y-4 rounded-lg border border-[rgba(246,241,231,0.14)] bg-[color:rgba(246,241,231,0.05)] p-5">
			<div class="rounded-lg border border-[rgba(17,122,72,0.2)] bg-[rgba(17,122,72,0.12)] p-5">
				<p class="text-xs font-semibold uppercase tracking-[0.22em] text-emerald-200">
					Workspace ready
				</p>
				<p class="mt-3 text-3xl font-semibold text-white">
					{seats || '1'}
					{seats === 1 ? ' seat' : ' seats'}
				</p>
				<p class="mt-2 text-sm leading-6 text-slate-300">Available immediately after activation.</p>
			</div>
			<p class="text-sm leading-6 text-slate-300">
				If you skip this step, your workspace is still live and you can invite people later from
				settings.
			</p>
		</div>
	</svelte:fragment>

	{#if status === 'syncing'}
		<div class="rounded-lg border border-slate-200 bg-slate-50/80 p-8 text-center">
			<div
				class="mx-auto h-14 w-14 animate-spin rounded-full border-4 border-slate-200 border-t-navy"
			></div>
			<p class="mt-6 text-lg font-semibold text-fg-1">Confirming payment</p>
			<p class="mt-2 text-sm text-slate-600">This usually takes only a moment.</p>
		</div>
	{:else if status === 'failed'}
		<div class="space-y-5">
			<div class="rounded-lg border border-[rgba(163,36,36,0.2)] bg-error-bg p-6">
				<p class="text-sm font-semibold text-error">
					Setup could not be completed automatically
				</p>
				<p class="mt-2 text-sm leading-6 text-error">
					{error || 'Something went wrong with your payment return.'}
				</p>
			</div>
			<div class="flex flex-col gap-3 sm:flex-row">
				<a
					href={resolve('/setup')}
					class="flex-1 rounded-md bg-navy px-5 py-3 text-center text-sm font-semibold text-bone transition hover:bg-primary-light"
				>
					Return to setup
				</a>
				<a
					href="mailto:contact@vitevue.com"
					class="rounded-md border border-slate-300 px-5 py-3 text-center text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
				>
					Contact support
				</a>
			</div>
		</div>
	{:else}
		{#if invitationErrors.length > 0}
			<div class="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
				<p class="font-semibold text-rose-900">Some invitations failed</p>
				<div class="mt-2 space-y-1">
					{#each invitationErrors as invitationError (invitationError)}
						<p>{invitationError}</p>
					{/each}
				</div>
			</div>
		{/if}

		<div class="rounded-lg border border-slate-200 bg-white p-5">
			<div class="flex items-center justify-between gap-4">
				<div>
					<p class="text-sm font-semibold text-slate-900">Invite teammates</p>
					<p class="mt-1 text-sm text-slate-500">
						We’ll email each invitee a secure sign-in link and onboarding flow.
					</p>
				</div>
				<div
					class="rounded-md bg-slate-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-slate-600"
				>
					Optional
				</div>
			</div>

			<div class="mt-5 space-y-3">
				{#each inviteEmails as email, index (index)}
					<div class="flex items-center gap-2">
						<input
							type="email"
							bind:value={inviteEmails[index]}
							placeholder={index === 0 ? 'colleague@company.com' : `Invite ${index + 1}`}
							aria-label={`Invite email ${index + 1}${email ? `: ${email}` : ''}`}
							class="flex-1 rounded-md border border-slate-300 px-4 py-3 focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/10"
						/>
						{#if inviteEmails.length > 1}
							<button
								type="button"
								onclick={() => removeEmailField(index)}
								aria-label="Remove email field"
								class="rounded-md border border-slate-300 px-3 py-3 text-slate-500 transition hover:bg-slate-50 hover:text-error"
							>
								Remove
							</button>
						{/if}
					</div>
				{/each}
			</div>

			<button
				type="button"
				onclick={addEmailField}
				class="mt-4 text-sm font-medium text-slate-600 transition hover:text-slate-900"
			>
				+ Add another email
			</button>
		</div>

		<div class="flex flex-col gap-3 sm:flex-row">
			<button
				type="button"
				onclick={handleSendInvitations}
				disabled={sendingInvites}
				class="flex-1 rounded-md bg-navy px-5 py-3 text-sm font-semibold text-bone transition hover:bg-primary-light disabled:cursor-not-allowed disabled:opacity-50"
			>
				{sendingInvites ? 'Sending invitations...' : 'Send invitations'}
			</button>
			<button
				type="button"
				onclick={() => goto(resolve('/dashboard'))}
				disabled={sendingInvites}
				class="rounded-md border border-slate-300 px-5 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
			>
				Skip for now
			</button>
		</div>
	{/if}
</AuthFlowShell>
