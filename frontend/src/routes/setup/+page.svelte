<script lang="ts">
import { onMount } from 'svelte'
import { page } from '$app/stores'
import { update_user_profile } from '$lib/api/auth'
import { createCheckoutSession } from '$lib/api/billing'
import { createOrganization } from '$lib/api/organization'
import AccountContextBar from '$lib/components/auth/AccountContextBar.svelte'
import AuthFlowShell from '$lib/components/auth/AuthFlowShell.svelte'
import TextInput from '$lib/components/auth/TextInput.svelte'
import { currentUser, refreshUser } from '$lib/stores/user.svelte'
import { clearSelectedTier, type PlanTier, readSelectedTier } from '$lib/utils/onboarding'

let firstName = $state('')
let lastName = $state('')
let organizationName = $state('')
let seats = $state(3)
let loading = $state(false)
let loadingStep = $state<'profile' | 'organization' | 'checkout' | null>(null)
let error = $state('')
let selectedTier = $state<PlanTier>('tier1')
let manualStep = $state<'profile' | 'organization' | null>(null)

let profileErrors = $state({
	firstName: '',
	lastName: ''
})

const plans = {
	tier1: {
		name: 'Starter',
		price: 199
	},
	tier2: {
		name: 'Professional',
		price: 499
	}
} satisfies Record<PlanTier, { name: string; price: number }>

const user = $derived(currentUser.data)
const needsProfile = $derived(!user?.first_name || !user?.last_name)
const visibleStep = $derived(manualStep ?? (needsProfile ? 'profile' : 'organization'))
const currentStep = $derived(visibleStep === 'profile' ? 1 : 2)
const activePlan = $derived(plans[selectedTier])
const totalMonthly = $derived(seats * activePlan.price)
const currentEmail = $derived(user?.email ?? null)
const ownerName = $derived(user?.first_name || 'Your')

onMount(() => {
	const tierParam = $page.url.searchParams.get('tier')
	const storedTier = readSelectedTier()

	if (tierParam === 'tier1' || tierParam === 'tier2') {
		selectedTier = tierParam
	} else if (storedTier) {
		selectedTier = storedTier
	}

	clearSelectedTier()
})

$effect(() => {
	if (!firstName) {
		firstName = user?.first_name ?? ''
	}
	if (!lastName) {
		lastName = user?.last_name ?? ''
	}
	if (!organizationName && user?.first_name) {
		organizationName = `${user.first_name}'s Organization`
	}
})

function setVisibleStep(step: 'profile' | 'organization') {
	manualStep = step
	error = ''
}

function updateSeatCount(nextSeats: number) {
	seats = Math.max(1, nextSeats)
}

async function handleProfileSubmit() {
	profileErrors.firstName = ''
	profileErrors.lastName = ''
	error = ''

	if (!firstName.trim()) {
		profileErrors.firstName = 'First name is required'
	}
	if (!lastName.trim()) {
		profileErrors.lastName = 'Last name is required'
	}
	if (profileErrors.firstName || profileErrors.lastName) {
		return
	}

	loading = true
	loadingStep = 'profile'

	try {
		await update_user_profile(firstName.trim(), lastName.trim())
		await refreshUser()
		manualStep = 'organization'
	} catch (err: unknown) {
		error = err instanceof Error ? err.message : 'Failed to save your profile.'
	} finally {
		loading = false
		loadingStep = null
	}
}

async function handleOrganizationSubmit() {
	error = ''

	if (!organizationName.trim()) {
		error = 'Organization name is required'
		return
	}

	if (seats < 1) {
		error = 'Please select at least one seat.'
		return
	}

	loading = true
	loadingStep = 'organization'

	try {
		const organization = await createOrganization(organizationName.trim(), seats)
		loadingStep = 'checkout'
		const checkout = await createCheckoutSession(organization.organization_id, seats, selectedTier)

		if (!checkout.checkout_url) {
			throw new Error('No checkout URL returned from the server.')
		}

		window.location.href = checkout.checkout_url
	} catch (err: unknown) {
		const message = err instanceof Error ? err.message : 'Please try again.'
		error =
			loadingStep === 'checkout'
				? `Failed to prepare checkout: ${message}`
				: `Failed to create organization: ${message}`
		loading = false
		loadingStep = null
	}
}
</script>

<svelte:head>
	<title>Workspace Setup - Vitevue</title>
</svelte:head>

<AuthFlowShell
	title={visibleStep === 'profile' ? 'Tell us who you are' : 'Create your organization'}
	description={visibleStep === 'profile'
		? 'Add your name before you create a workspace and start subscription setup.'
		: 'Choose your plan, set your team size, and continue to Stripe to activate your workspace.'}
	eyebrow="Workspace setup"
	step={String(currentStep)}
	totalSteps={3}
	stepLabel={visibleStep === 'profile' ? 'Profile' : 'Organization'}
	sideAccent={visibleStep === 'profile' ? 'Welcome aboard' : 'Owner setup'}
	sideTitle={visibleStep === 'profile'
		? 'Vitevue keeps market signals, feasibility work, and commercial context in one place.'
		: 'Shared market view, structured analysis, cleaner collaboration.'}
	sideCopy={visibleStep === 'profile'
		? 'Track transactions, compare opportunities, structure analysis, and keep the team aligned without scattering the work across disconnected tools.'
		: 'Choose the plan and seat count that fit how you work today. You can adjust both later once the workspace is live.'}
	sectionWidthClass="lg:max-w-[46rem] xl:max-w-[48rem]"
	contentWidthClass="max-w-[46rem]"
	cardClass="lg:p-6 xl:p-6"
>
	<svelte:fragment slot="account">
		<AccountContextBar
			email={currentEmail}
			label={visibleStep === 'profile' ? 'Signed in as' : 'Owner account'}
			redirectTo="/auth"
			compact={visibleStep === 'organization'}
		/>
	</svelte:fragment>

	<svelte:fragment slot="side">
		<div class="space-y-4 rounded-lg border border-[rgba(246,241,231,0.14)] bg-[color:rgba(246,241,231,0.05)] p-5">
			{#if visibleStep === 'profile'}
				<div class="grid gap-3">
					<div class="rounded-md border border-[rgba(246,241,231,0.12)] bg-[color:rgba(246,241,231,0.04)] px-4 py-3">
						<p class="text-sm font-semibold text-white">Market clarity</p>
						<p class="mt-1 text-sm leading-6 text-slate-300">
							See transactions, pricing signals, and commercial context in one workspace.
						</p>
					</div>
					<div class="rounded-md border border-[rgba(246,241,231,0.12)] bg-[color:rgba(246,241,231,0.04)] px-4 py-3">
						<p class="text-sm font-semibold text-white">Feasibility workflow</p>
						<p class="mt-1 text-sm leading-6 text-slate-300">
							Move from raw site inputs to structured analysis with less spreadsheet overhead.
						</p>
					</div>
					<div class="rounded-md border border-[rgba(246,241,231,0.12)] bg-[color:rgba(246,241,231,0.04)] px-4 py-3">
						<p class="text-sm font-semibold text-white">Team coordination</p>
						<p class="mt-1 text-sm leading-6 text-slate-300">
							Keep ownership, access, and commercial decisions aligned from the start.
						</p>
					</div>
				</div>
			{:else}
				<div class="rounded-lg border border-[rgba(246,241,231,0.14)] bg-[color:rgba(246,241,231,0.05)] p-5">
					<p class="text-xs font-semibold uppercase tracking-[0.22em] text-bone/70">
						Vitevue workspace
					</p>
					<p class="mt-3 text-[1.4rem] font-semibold leading-tight text-white">
						{ownerName} will own billing, access, and the team from one place.
					</p>
					<p class="mt-3 text-sm leading-6 text-slate-300">
						Choose a plan, set your initial team size, and continue to Stripe. Everything can be
						adjusted later.
					</p>
					<div class="mt-4 space-y-2 text-sm text-slate-200">
						<p>Market context, transactions, and analysis in one workspace.</p>
						<p>Structured access and billing from day one.</p>
					</div>
				</div>
			{/if}
		</div>
	</svelte:fragment>

	{#if error}
		<div class="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
			{error}
		</div>
	{/if}

	{#if visibleStep === 'profile'}
		<form
			onsubmit={(event) => {
				event.preventDefault();
				handleProfileSubmit();
			}}
			class="space-y-5"
		>
			<div class="grid gap-5 sm:grid-cols-2">
				<TextInput
					label="First name"
					bind:value={firstName}
					placeholder="John"
					error={profileErrors.firstName}
					required
					autocomplete="given-name"
				/>
				<TextInput
					label="Last name"
					bind:value={lastName}
					placeholder="Doe"
					error={profileErrors.lastName}
					required
					autocomplete="family-name"
				/>
			</div>

			<button
				type="submit"
				disabled={loading}
				class="w-full rounded-md bg-navy px-6 py-3.5 text-base font-semibold text-bone transition hover:bg-primary-light disabled:cursor-not-allowed disabled:opacity-50"
			>
				{loading ? 'Saving profile...' : 'Continue'}
			</button>

			<div
				class="rounded-lg border border-slate-200 bg-slate-50/80 px-4 py-3 text-sm text-slate-600"
			>
				Next up: choose your plan, set your seat count, and continue to Stripe.
			</div>
		</form>
	{:else}
		<form
			onsubmit={(event) => {
				event.preventDefault();
				handleOrganizationSubmit();
			}}
			class="space-y-2"
		>
			<div class="rounded-lg border border-slate-200 bg-white p-4">
				<div class="space-y-4">
					<div class="flex items-center justify-between gap-4">
						<p class="text-sm font-semibold text-slate-900">Workspace details</p>
						<button
							type="button"
							onclick={() => setVisibleStep('profile')}
							class="inline-flex items-center gap-2 text-sm font-medium text-slate-500 transition hover:text-slate-900"
						>
							<span aria-hidden="true">←</span>
							Edit profile
						</button>
					</div>

					<div>
						<label for="orgName" class="block text-sm font-semibold text-slate-900">
							Organization name
						</label>
						<input
							id="orgName"
							type="text"
							bind:value={organizationName}
							placeholder="Your company name"
							class="mt-2 w-full rounded-md border border-slate-300 bg-white px-4 py-3 text-slate-900 shadow-sm focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/10"
							required
						/>
					</div>

					<div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_13rem] lg:items-end">
						<div></div>

						<div>
							<label for="seatCount" class="block text-sm font-semibold text-slate-900">
								Team size
							</label>
						</div>
					</div>

					<div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_13rem] lg:items-start">
						<div>
							<p class="text-sm font-semibold text-slate-900">Choose your plan</p>
							<div class="mt-2 grid gap-2 sm:grid-cols-2">
								{#each Object.entries(plans) as [tier, plan] (tier)}
									<button
										type="button"
										onclick={() => (selectedTier = tier as PlanTier)}
										class="rounded-md border px-4 py-2.5 text-left transition {selectedTier ===
										tier
											? 'border-navy bg-navy text-bone shadow-sm'
											: 'border-slate-200 bg-slate-50 text-slate-800 hover:border-slate-300'}"
									>
										<div class="flex items-center justify-between gap-3">
											<p class="text-sm font-semibold">{plan.name}</p>
											<p class="text-sm font-semibold">
												{plan.price}
												<span class="text-xs font-medium opacity-80">AED/seat</span>
											</p>
										</div>
									</button>
								{/each}
							</div>
						</div>

						<div>
							<p class="text-sm text-slate-500">How many people need access right now.</p>
							<input
								id="seatCount"
								type="number"
								min="1"
								bind:value={seats}
								oninput={(event) =>
									updateSeatCount(
										parseInt((event.currentTarget as HTMLInputElement).value || '1', 10)
									)}
								class="mt-2 w-full rounded-md border border-slate-300 bg-white px-4 py-3 text-lg font-semibold text-slate-900 shadow-sm focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy/10"
								aria-label="Seat count"
							/>
							<p class="mt-2 text-xs leading-5 text-slate-500">You can change seats later.</p>
						</div>
					</div>

					<div
						class="flex flex-col gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
					>
						<div class="min-w-0">
							<p class="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
								Monthly total
							</p>
							<div class="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
								<p class="text-[2rem] font-semibold tracking-tight text-fg-1">
									{totalMonthly} AED
								</p>
								<p class="text-sm text-slate-500">
									{activePlan.name} · {activePlan.price} AED per seat · {seats} seats
								</p>
							</div>
							<p class="mt-1 text-xs leading-5 text-slate-500">
								Billed monthly in Stripe. You will return to Vitevue to invite teammates after
								checkout.
							</p>
						</div>

						<button
							type="submit"
							disabled={loading}
							class="shrink-0 rounded-md bg-navy px-6 py-3 text-base font-semibold text-bone transition hover:bg-primary-light disabled:cursor-not-allowed disabled:opacity-50"
						>
							{#if loading}
								{loadingStep === 'organization'
									? 'Creating organization...'
									: loadingStep === 'checkout'
										? 'Preparing checkout...'
										: 'Processing...'}
							{:else}
								Continue to payment
							{/if}
						</button>
					</div>
				</div>
			</div>
		</form>
	{/if}
</AuthFlowShell>
