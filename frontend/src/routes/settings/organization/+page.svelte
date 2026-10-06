<script lang="ts">
import { createQuery } from '@tanstack/svelte-query'
import {
	deleteOrganizationInvitation,
	getCustomerPortalUrl,
	inviteUserByEmail,
	removeOrganizationMember
} from '$lib/api/organization'
import { getQueryClient } from '$lib/queries/client'
import { organizationKeys, organizationQueries } from '$lib/queries/organization'
import { currentUser as userStore } from '$lib/stores/user.svelte'

let currentUser = $derived(userStore.data)
let isOwner = $derived(currentUser?.is_owner === true)
const queryClient = getQueryClient()

let showInviteModal = $state(false)
let inviteEmail = $state('')
let inviteLoading = $state(false)
let inviteError = $state('')
let inviteSuccess = $state(false)
let resendingEmail = $state('')
let cancelingInvitationId = $state('')

const membersQuery = createQuery(() => organizationQueries.members(isOwner))

const subscriptionQuery = createQuery(() => organizationQueries.subscription(isOwner))

const invitationsQuery = createQuery(() => organizationQueries.invitations(isOwner))

const members = $derived(membersQuery.data ?? [])
const invitations = $derived(invitationsQuery.data ?? [])
const subscription = $derived(subscriptionQuery.data)
const availableSeats = $derived(subscription?.available_seats ?? 0)
const hasExcessUsers = $derived((subscription?.excess_users ?? 0) > 0)
const withinPaidPeriod = $derived(subscription?.within_paid_period ?? false)

function normalizeInviteEmail(email: string): string {
	return email.trim().toLowerCase()
}

function validateInviteEmail(email: string): string | null {
	if (!email) return 'Email is required'
	if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return 'Invalid email format'
	return null
}

async function sendInvite(email: string): Promise<void> {
	await inviteUserByEmail(email)
}

async function invalidateOrganizationQueries(keys: ReadonlyArray<readonly unknown[]>) {
	await Promise.all(keys.map((queryKey) => queryClient.invalidateQueries({ queryKey })))
}

async function handleManageSubscription() {
	try {
		const result = await getCustomerPortalUrl()
		window.location.href = result.url
	} catch (err: any) {
		alert(err.message || 'Failed to open subscription management')
	}
}

async function handleRemoveMember(userId: string, userName: string) {
	if (!confirm(`Remove ${userName} from this organization?`)) return
	try {
		await removeOrganizationMember(userId)
		await invalidateOrganizationQueries([
			organizationKeys.members(),
			organizationKeys.subscription()
		])
	} catch (err: any) {
		alert(err.message || 'Failed to remove member')
	}
}

async function handleResendInvitation(email: string) {
	resendingEmail = email
	try {
		await sendInvite(email)
		await invalidateOrganizationQueries([
			organizationKeys.invitations(),
			organizationKeys.subscription()
		])
		alert(`Invitation resent to ${email}`)
	} catch (err: any) {
		alert(err.message || 'Failed to resend invitation')
	} finally {
		resendingEmail = ''
	}
}

async function handleCancelInvitation(invitationId: string, email: string) {
	if (!confirm(`Cancel the pending invitation for ${email}?`)) return
	cancelingInvitationId = invitationId
	try {
		await deleteOrganizationInvitation(invitationId)
		await invalidateOrganizationQueries([
			organizationKeys.invitations(),
			organizationKeys.subscription()
		])
	} catch (err: any) {
		alert(err.message || 'Failed to cancel invitation')
	} finally {
		cancelingInvitationId = ''
	}
}

async function handleInviteUser() {
	inviteError = ''
	inviteSuccess = false
	const email = normalizeInviteEmail(inviteEmail)

	const validationError = validateInviteEmail(email)
	if (validationError) {
		inviteError = validationError
		return
	}

	if (subscription && availableSeats <= 0) {
		inviteError = 'No available seats. Please upgrade your subscription first.'
		return
	}

	inviteLoading = true

	try {
		await sendInvite(email)
		await invalidateOrganizationQueries([
			organizationKeys.invitations(),
			organizationKeys.subscription()
		])
		inviteSuccess = true
		inviteEmail = ''
		setTimeout(() => {
			showInviteModal = false
			inviteSuccess = false
		}, 2000)
	} catch (err: any) {
		inviteError = err.message || 'Failed to send invitation'
	} finally {
		inviteLoading = false
	}
}

function formatDate(dateString: string): string {
	return new Date(dateString).toLocaleDateString('en-US', {
		year: 'numeric',
		month: 'long',
		day: 'numeric'
	})
}

function roleLabel(role: string): string {
	return role === 'owner' ? 'Owner' : 'Member'
}
</script>

<svelte:head>
	<title>Organization Settings - Vitevue</title>
</svelte:head>

		<!-- Header -->
		<section class="mb-5 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
			<div class="bg-navy px-5 py-5 text-bone">
				<p class="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Settings</p>
				<h1 class="mt-2 font-display text-3xl leading-tight tracking-[var(--tracking-display)] text-bone">
					Organization settings
				</h1>
				<p class="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
					Manage workspace seats, billing access, members, and pending invitations.
				</p>
			</div>
		</section>

		{#if !isOwner}
			<div class="rounded-lg border border-border bg-white p-8 text-center shadow-sm">
				<svg
					class="mx-auto mb-4 h-14 w-14 text-slate-300"
					fill="none"
					stroke="currentColor"
					viewBox="0 0 24 24"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
					></path>
				</svg>
				<h2 class="mb-2 text-xl font-semibold text-slate-900">Access restricted</h2>
				<p class="text-slate-600">Only the organization owner can access these settings.</p>
			</div>
		{:else}
			<!-- Subscription Info -->
			<div class="mb-5 rounded-lg border border-border bg-card shadow-sm">
				<div class="border-b border-border p-5">
					<h2 class="text-xl font-semibold text-fg-1">Subscription</h2>
				</div>
				<div class="p-5">
					{#if subscriptionQuery.isLoading}
						<div class="animate-pulse space-y-3">
							<div class="h-4 bg-panel rounded w-1/3"></div>
							<div class="h-4 bg-panel rounded w-1/2"></div>
						</div>
					{:else if subscription}
						<div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
							<div>
								<p class="text-sm text-fg-3 mb-1">Status</p>
								<p class="text-lg font-semibold text-fg-1 capitalize">{subscription.status}</p>
							</div>
							<div>
								<p class="text-sm text-fg-3 mb-1">Seats used</p>
								<p class="text-lg font-semibold text-fg-1">
									{subscription.current_members} / {subscription.seats} used
								</p>
							</div>
							<div>
								<p class="text-sm text-fg-3 mb-1">Billing period ends</p>
								<p class="text-lg font-semibold text-fg-1">
									{formatDate(subscription.current_period_end)}
								</p>
							</div>
						</div>

						{#if hasExcessUsers && withinPaidPeriod}
							<div class="mb-6 rounded-lg border border-[rgba(165,90,19,0.2)] bg-warning-bg p-4">
								<div class="flex items-start gap-3">
									<svg
										class="mt-0.5 h-5 w-5 flex-shrink-0 text-warning"
										fill="none"
										stroke="currentColor"
										viewBox="0 0 24 24"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											stroke-width="2"
											d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
										></path>
									</svg>
									<div>
										<p class="mb-1 font-medium text-warning">
											Action required after billing period
										</p>
										<p class="mb-2 text-sm text-warning">
											You have {subscription?.excess_users} too many users for your subscription ({subscription?.current_members}
											users, {subscription?.seats} seats).
										</p>
										<p class="text-sm text-warning">
											All users will remain active until {new Date(
												subscription?.current_period_end || ''
											).toLocaleDateString()}. After this date, you must either remove {subscription?.excess_users}
											{subscription?.excess_users === 1 ? 'member' : 'members'} or upgrade your subscription.
										</p>
									</div>
								</div>
							</div>
						{:else if hasExcessUsers && !withinPaidPeriod}
							<div class="mb-6 rounded-lg border border-[rgba(163,36,36,0.2)] bg-error-bg p-4">
								<div class="flex items-start gap-3">
									<svg
										class="mt-0.5 h-5 w-5 flex-shrink-0 text-error"
										fill="none"
										stroke="currentColor"
										viewBox="0 0 24 24"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											stroke-width="2"
											d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
										></path>
									</svg>
									<div>
										<p class="mb-1 font-medium text-error">Immediate action required</p>
										<p class="mb-2 text-sm text-error">
											You have {subscription?.excess_users} too many users ({subscription?.current_members}
											users, {subscription?.seats} seats). Your billing period has ended.
										</p>
										<p class="text-sm text-error">
											Please remove {subscription?.excess_users}
											{subscription?.excess_users === 1 ? 'member' : 'members'} immediately or upgrade
											your subscription to prevent service disruption.
										</p>
									</div>
								</div>
							</div>
						{:else if availableSeats > 0}
							<div class="mb-6 rounded-lg border border-[rgba(17,122,72,0.2)] bg-success-bg p-4">
								<div class="flex items-center gap-3">
									<svg
										class="h-5 w-5 text-success"
										fill="none"
										stroke="currentColor"
										viewBox="0 0 24 24"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											stroke-width="2"
											d="M5 13l4 4L19 7"
										></path>
									</svg>
									<p class="text-sm text-success">
										You have {availableSeats} available {availableSeats === 1 ? 'seat' : 'seats'}.
										Invite new members!
									</p>
								</div>
							</div>
						{/if}

						<button
							onclick={handleManageSubscription}
							class="rounded-md bg-navy px-5 py-2.5 text-sm font-semibold text-bone transition-colors hover:bg-primary-light"
						>
							Manage subscription
						</button>
					{:else}
						<p class="text-fg-3">No subscription information available</p>
					{/if}
				</div>
			</div>

			<!-- Team Members -->
			<div class="rounded-lg border border-border bg-card shadow-sm">
				<div class="flex items-center justify-between border-b border-border p-5">
					<h2 class="text-xl font-semibold text-fg-1">Team members</h2>
					<button
						onclick={() => (showInviteModal = true)}
						disabled={subscription !== undefined && availableSeats <= 0}
						class="rounded-md bg-navy px-4 py-2 text-sm font-semibold text-bone transition-colors hover:bg-primary-light disabled:cursor-not-allowed disabled:opacity-50"
					>
						Invite member
					</button>
				</div>
				<div class="p-5">
					{#if membersQuery.isLoading}
						<div class="animate-pulse space-y-4">
							{#each [1, 2, 3] as skeleton (skeleton)}
								<div class="h-16 bg-panel rounded"></div>
							{/each}
						</div>
					{:else if members.length > 0}
						<div class="space-y-3">
							{#each members as member (member.id)}
								<div
									class="flex items-center justify-between rounded-lg border border-border p-4 transition-colors hover:bg-app"
								>
									<div class="flex items-center gap-4">
										<div
											class="flex h-10 w-10 items-center justify-center rounded-md bg-info-bg"
										>
											<span class="font-semibold text-info">
												{member.first_name?.[0]}{member.last_name?.[0]}
											</span>
										</div>
										<div>
											<p class="font-medium text-fg-1">
												{member.first_name}
												{member.last_name}
											</p>
											<p class="text-sm text-fg-3">{member.email}</p>
										</div>
									</div>
									<div class="flex items-center gap-3">
										<span
											class="rounded-sm border border-[rgba(17,122,72,0.2)] bg-success-bg px-3 py-1 text-xs font-semibold text-success"
										>
											Active
										</span>
										<span
											class="rounded-sm border border-border bg-panel px-3 py-1 text-xs font-semibold capitalize text-fg-3"
										>
											{roleLabel(member.role)}
										</span>
										{#if member.id !== currentUser?.id && member.role !== 'owner'}
											<button
												onclick={() =>
													handleRemoveMember(member.id, `${member.first_name} ${member.last_name}`)}
												class="{hasExcessUsers && !withinPaidPeriod
													? 'bg-error-bg text-error hover:opacity-90'
													: 'text-error hover:opacity-80'} rounded-md px-3 py-1 text-sm font-medium transition-colors"
											>
												Remove
											</button>
										{/if}
									</div>
								</div>
							{/each}
						</div>
					{:else}
						<p class="text-fg-3 text-center py-8">No team members found</p>
					{/if}
				</div>
			</div>

			<!-- Pending Invitations -->
			<div class="mt-5 rounded-lg border border-border bg-card shadow-sm">
				<div class="border-b border-border p-5">
					<h2 class="text-xl font-semibold text-fg-1">Pending invitations</h2>
				</div>
				<div class="p-5">
					{#if invitationsQuery.isLoading}
						<div class="animate-pulse space-y-4">
							{#each [1, 2] as skeleton (skeleton)}
								<div class="h-16 bg-panel rounded"></div>
							{/each}
						</div>
					{:else if invitations.length > 0}
						<div class="space-y-3">
							{#each invitations as invitation (invitation.id)}
								<div
									class="flex items-center justify-between rounded-lg border border-border p-4"
								>
									<div>
										<p class="font-medium text-fg-1">{invitation.email}</p>
										<p class="text-sm text-fg-3">
											Expires {formatDate(invitation.expires_at)}
										</p>
									</div>
									<div class="flex items-center gap-3">
										<span
											class="rounded-sm border border-[rgba(165,90,19,0.2)] bg-warning-bg px-3 py-1 text-xs font-semibold text-warning"
										>
											Pending
										</span>
										<button
											onclick={() => handleResendInvitation(invitation.email)}
											disabled={resendingEmail === invitation.email ||
												cancelingInvitationId === invitation.id}
											class="text-sm font-medium text-info hover:text-fg-1 disabled:cursor-not-allowed disabled:opacity-50"
										>
											{resendingEmail === invitation.email ? 'Sending...' : 'Resend invite'}
										</button>
										<button
											onclick={() => handleCancelInvitation(invitation.id, invitation.email)}
											disabled={cancelingInvitationId === invitation.id ||
												resendingEmail === invitation.email}
											class="text-sm font-medium text-error hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-50"
										>
											{cancelingInvitationId === invitation.id ? 'Canceling...' : 'Cancel invite'}
										</button>
									</div>
								</div>
							{/each}
						</div>
					{:else}
						<p class="text-fg-3 text-center py-8">No pending invitations</p>
					{/if}
				</div>
			</div>
		{/if}

<!-- Invite Modal -->
{#if showInviteModal}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4"
		role="presentation"
		onkeydown={(e) => e.key === 'Escape' && (showInviteModal = false)}
		onclick={() => (showInviteModal = false)}
	>
		<div
			class="w-full max-w-md rounded-lg border border-border bg-white p-6 shadow-xl"
			role="dialog"
			aria-modal="true"
			tabindex="-1"
			onkeydown={(e) => e.key === 'Escape' && (showInviteModal = false)}
			onclick={(e) => e.stopPropagation()}
		>
			<div class="flex items-center justify-between mb-4">
				<h3 class="text-xl font-semibold text-slate-900">Invite team member</h3>
				<button
					onclick={() => (showInviteModal = false)}
					aria-label="Close invite modal"
					class="rounded-md p-1 text-slate-400 transition hover:bg-slate-50 hover:text-slate-600"
				>
					<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M6 18L18 6M6 6l12 12"
						></path>
					</svg>
				</button>
			</div>

			{#if inviteSuccess}
				<div class="mb-4 rounded-lg border border-[rgba(17,122,72,0.2)] bg-success-bg p-4">
					<p class="text-sm text-success">Invitation sent successfully!</p>
				</div>
			{/if}

			{#if inviteError}
				<div class="mb-4 rounded-lg border border-[rgba(163,36,36,0.2)] bg-error-bg p-4">
					<p class="text-sm text-error">{inviteError}</p>
				</div>
			{/if}

			<form
				onsubmit={(e) => {
					e.preventDefault();
					handleInviteUser();
				}}
			>
				<div class="mb-4">
					<label for="inviteEmail" class="mb-2 block text-sm font-medium text-slate-700">
						Email address
					</label>
					<input
						id="inviteEmail"
						type="email"
						bind:value={inviteEmail}
						placeholder="colleague@company.com"
						class="w-full rounded-md border border-slate-300 px-4 py-2 focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/10"
						required
					/>
				</div>

				<div class="flex gap-3">
					<button
						type="submit"
						disabled={inviteLoading}
						class="flex-1 rounded-md bg-navy px-4 py-2 font-semibold text-bone transition-colors hover:bg-primary-light disabled:cursor-not-allowed disabled:opacity-50"
					>
						{inviteLoading ? 'Sending...' : 'Send invitation'}
					</button>
					<button
						type="button"
						onclick={() => (showInviteModal = false)}
						class="rounded-md border border-slate-300 px-4 py-2 font-semibold text-slate-700 transition-colors hover:bg-slate-50"
					>
						Cancel
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}
