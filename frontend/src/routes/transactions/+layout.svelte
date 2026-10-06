<script lang="ts">
import { ChevronDown } from 'lucide-svelte'
import type { Snippet } from 'svelte'
import { page } from '$app/state'
import StandardDropdown from '$lib/components/dropdowns/StandardDropdown.svelte'
import { propertyType, timeframe } from '$lib/components/filters/globalFilters.svelte'
import AppFrame from '$lib/components/layout/AppFrame.svelte'
import PageContainer from '$lib/components/layout/PageContainer.svelte'

let { children }: { children: Snippet } = $props()

const timeframes = ['Last Week', 'Last Month', 'Last 3 Months', 'Last 6 Months', 'Last Year']
let activeTab = $derived(page.url.pathname.includes('/rentals') ? 'rentals' : 'sales')
</script>

<AppFrame stableScrollGutter>
	<PageContainer variant="standard" class="gap-4">
		<section class="ui-surface relative z-30 overflow-visible">
			<div class="ui-page-header grid px-5 py-4 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-center">
				<div>
					<p class="text-xs font-semibold uppercase tracking-[0.18em] text-on-navy-muted">
						Transactions
					</p>
					<h1 class="mt-1 font-display text-2xl leading-tight tracking-[var(--tracking-display)] text-bone">
						Market evidence workspace
					</h1>
				</div>

				<div class="mt-4 flex flex-wrap items-center gap-2 xl:mt-0 xl:justify-end">
					<nav class="ui-segmented" aria-label="Transaction type">
						<a
							href="/transactions/sales"
							data-active={activeTab === 'sales'}
							class="ui-segmented-item px-3 py-1.5 text-sm"
						>
							Sales
						</a>
						<a
							href="/transactions/rentals"
							data-active={activeTab === 'rentals'}
							class="ui-segmented-item px-3 py-1.5 text-sm"
						>
							Rentals
						</a>
					</nav>

					<div class="ui-segmented" role="group" aria-label="Property usage">
						{#each ['Residential', 'Commercial'] as option}
							<button
								type="button"
								onclick={() => (propertyType.current = option)}
								aria-pressed={propertyType.current === option}
								data-active={propertyType.current === option}
								class="ui-segmented-item px-3 py-1.5 text-sm"
							>
								{option}
							</button>
						{/each}
					</div>

					<div class="w-full min-w-0 sm:w-[190px]">
						<StandardDropdown
							id="transactions-timeframe"
							ariaLabel="Timeframe"
							options={timeframes}
							bind:value={timeframe.current}
							variant="inverse"
						>
							{#snippet button({ isOpen })}
								<span>{timeframe.current}</span>
								<ChevronDown
									size={16}
									strokeWidth={1.8}
									class="text-on-navy-muted transition-transform {isOpen ? 'rotate-180' : ''}"
								/>
							{/snippet}
						</StandardDropdown>
					</div>
				</div>
			</div>
		</section>

		{@render children()}
	</PageContainer>
</AppFrame>
