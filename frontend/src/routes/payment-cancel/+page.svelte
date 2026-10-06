<script lang="ts">
import { resolve } from '$app/paths'
import AuthFlowShell from '$lib/components/auth/AuthFlowShell.svelte'
</script>

<svelte:head>
	<title>Payment cancelled - Vitevue</title>
</svelte:head>

<AuthFlowShell
	title="Payment cancelled"
	description="No charges were made. You can return to workspace setup and start checkout again when you are ready."
	eyebrow="Workspace setup"
	sideAccent="Billing setup"
	sideTitle="Your workspace is still waiting for activation."
	sideCopy="Return to setup to choose your plan and seat count again, or contact support if Stripe did not behave as expected."
	contentWidthClass="max-w-xl"
	sectionWidthClass="lg:max-w-xl"
>
	<svelte:fragment slot="side">
		<div class="rounded-lg border border-[rgba(246,241,231,0.14)] bg-[color:rgba(246,241,231,0.05)] p-5">
			<p class="font-mono text-[10px] font-medium uppercase tracking-[0.16em] text-on-navy-muted">
				No payment captured
			</p>
			<p class="mt-3 text-sm leading-6 text-on-navy-muted">
				The organization setup flow stays available until checkout completes successfully.
			</p>
		</div>
	</svelte:fragment>

	<div class="space-y-5">
		<div class="rounded-lg border border-[rgba(165,90,19,0.2)] bg-warning-bg p-5">
			<p class="text-sm font-semibold text-warning">Checkout was cancelled</p>
			<p class="mt-2 text-sm leading-6 text-warning">
				No subscription was activated and no charge was made to your account.
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
</AuthFlowShell>
