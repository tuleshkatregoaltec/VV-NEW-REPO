<script lang="ts">
import { createInfiniteQuery, createQuery } from '@tanstack/svelte-query'
import { Activity, Building2, Sparkles } from 'lucide-svelte'
import { goto } from '$app/navigation'
import { type ConversationListResponse, chat } from '$lib/api/chat'
import CompactChatInput from '$lib/components/dashboard/CompactChatInput.svelte'
import CompleteProfileModal from '$lib/components/dashboard/CompleteProfileModal.svelte'
import CustomizableKpiGrid from '$lib/components/dashboard/CustomizableKpiGrid.svelte'
import FullWidthMarketChart from '$lib/components/dashboard/FullWidthMarketChart.svelte'
import AppFrame from '$lib/components/layout/AppFrame.svelte'
import PageContainer from '$lib/components/layout/PageContainer.svelte'
import NewsCard from '$lib/components/news/NewsCard.svelte'
import { chatKeys } from '$lib/queries/chat'
import { getQueryClient } from '$lib/queries/client'
import { newsQueries } from '$lib/queries/news'
import { currentUser } from '$lib/stores/user.svelte'

const queryClient = getQueryClient()

let username = $derived(currentUser.data?.first_name ?? '')
let newsSection = $state<HTMLElement>()
let newsSectionVisible = $state(false)
let sentinel = $state<HTMLDivElement>()

const LIMIT = 10

const newsQuery = createInfiniteQuery(() => newsQueries.listInfinite('dashboard', LIMIT))
const newsSummaryQuery = createQuery(() => newsQueries.summary())
const newsArticles = $derived(newsQuery.data?.pages.flatMap((page) => page.articles) ?? [])

async function handleChatSubmit(message: string) {
	try {
		const conversation = await chat.createConversation({ title: message.slice(0, 50) })
		queryClient.setQueryData<ConversationListResponse>(chatKeys.conversations(), (current) => {
			const conversations = [
				conversation,
				...(current?.conversations ?? []).filter((item) => item.id !== conversation.id)
			]
			return { conversations, total: conversations.length }
		})
		goto('/chat', {
			state: { conversationId: conversation.id, initialMessage: message }
		})
	} catch (error) {
		console.error('Failed to create conversation:', error)
		throw error
	}
}

$effect(() => {
	if (!newsSection) return
	const observer = new IntersectionObserver(
		(entries) => {
			entries.forEach((entry) => {
				if (entry.isIntersecting) newsSectionVisible = true
			})
		},
		{ threshold: 0.1 }
	)
	observer.observe(newsSection)
	return () => observer.disconnect()
})

$effect(() => {
	if (!sentinel) return
	const observer = new IntersectionObserver(
		(entries) => {
			if (entries[0].isIntersecting && newsQuery.hasNextPage && !newsQuery.isFetchingNextPage) {
				newsQuery.fetchNextPage()
			}
		},
		{ threshold: 0.1, rootMargin: '200px' }
	)
	observer.observe(sentinel)
	return () => observer.disconnect()
})

const SUGGESTIONS = [
	'What are 2BR yields in Dubai Marina this quarter?',
	'Compare JBR vs Palm Jumeirah price trends',
	'Which sub-markets have the highest YoY growth?'
]
</script>

<AppFrame stableScrollGutter>
	<PageContainer variant="standard">
			<!-- Page Header -->
			<div class="py-8 pb-6">
				<p class="font-mono text-[11px] uppercase tracking-[0.06em] text-fg-4 mb-2">
					Workspace / <span class="text-fg-1">Dubai market</span>
				</p>
				<h1 class="text-2xl font-semibold tracking-normal text-fg-1">
					{username ? `${username}'s workspace` : 'Market overview'}
				</h1>
				<p class="mt-1.5 text-sm text-fg-3">
					DLD market data · ask anything below or browse the latest transactions.
				</p>
			</div>

			<CustomizableKpiGrid />

			<!-- Two-col: Chart + AI -->
			<div class="grid grid-cols-1 gap-3 mb-3 lg:grid-cols-[1.6fr_1fr]">

				<!-- Market Chart Card -->
				<div class="ui-surface p-6">
					<FullWidthMarketChart />
				</div>

				<!-- Vitevue AI Card -->
				<div class="ui-surface flex flex-col p-6">
					<div class="flex items-center justify-between mb-4">
						<h3 class="text-sm font-semibold text-fg-1">Vitevue AI</h3>
						<span class="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.08em] text-success">
							<span class="inline-block h-1.5 w-1.5 rounded-full bg-success shadow-[0_0_0_3px_rgba(17,122,72,0.18)]"></span>
							Live
						</span>
					</div>

					<CompactChatInput
						placeholder="Ask anything about Dubai real estate…"
						onSubmit={handleChatSubmit}
					/>

					<div class="mt-4 flex flex-col gap-2">
						{#each SUGGESTIONS as s (s)}
							<button
								type="button"
								onclick={() => handleChatSubmit(s)}
								class="w-full rounded-md border border-border bg-card px-3 py-2 text-left text-xs text-fg-2 transition-colors hover:border-strong hover:bg-elevated"
							>
								→ {s}
							</button>
						{/each}
					</div>
				</div>
			</div>

			<!-- News Section -->
			<div class="mb-12" bind:this={newsSection}>
				<div class="mb-4 flex items-center justify-between border-b border-border pb-4">
					<div>
						<p class="font-mono text-[11px] uppercase tracking-[0.08em] text-fg-4">Latest news</p>
						<h2 class="mt-1 text-2xl font-semibold text-fg-1">Dubai real estate</h2>
					</div>
				</div>

				<div class="mb-4 overflow-hidden rounded-lg border border-border bg-card shadow-[var(--shadow-sm)]">
					<div class="grid grid-cols-1 lg:grid-cols-[220px_1fr]">
						<div
							class="flex flex-row items-center justify-between gap-3 border-b border-border bg-panel px-4 py-3 lg:flex-col lg:items-start lg:justify-start lg:border-b-0 lg:border-r"
						>
							<div class="flex items-center gap-3">
								<div class="flex h-8 w-8 items-center justify-center rounded-md bg-navy text-on-navy">
									<Sparkles class="h-4 w-4" />
								</div>
								<div>
									<p class="text-sm font-semibold text-fg-1">Market brief</p>
									<p class="text-xs text-fg-4">AI-filtered signal</p>
								</div>
							</div>
							{#if newsSummaryQuery.data}
								<span
									class="inline-flex items-center gap-1.5 rounded-md bg-card px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.08em] text-fg-4 ring-1 ring-border"
								>
									<span class="h-1.5 w-1.5 rounded-full bg-success"></span>
									{newsSummaryQuery.data.article_count} headlines
								</span>
							{/if}
						</div>

						<div class="grid grid-cols-1 lg:grid-cols-2 lg:divide-x lg:divide-border">
						{#if newsSummaryQuery.isPending}
							<div class="p-4">
								<div class="mb-4 flex items-center gap-3">
									<div class="h-8 w-8 animate-pulse rounded-md bg-panel"></div>
									<div class="h-3 w-20 animate-pulse rounded bg-panel"></div>
								</div>
								<div class="space-y-2">
									<div class="h-3 w-full animate-pulse rounded bg-panel"></div>
									<div class="h-3 w-11/12 animate-pulse rounded bg-panel"></div>
									<div class="h-3 w-4/5 animate-pulse rounded bg-panel"></div>
								</div>
							</div>
							<div class="border-t border-border p-4 lg:border-t-0">
								<div class="mb-4 flex items-center gap-3">
									<div class="h-8 w-8 animate-pulse rounded-md bg-panel"></div>
									<div class="h-3 w-24 animate-pulse rounded bg-panel"></div>
								</div>
								<div class="space-y-2">
									<div class="h-3 w-full animate-pulse rounded bg-panel"></div>
									<div class="h-3 w-10/12 animate-pulse rounded bg-panel"></div>
									<div class="h-3 w-5/6 animate-pulse rounded bg-panel"></div>
								</div>
							</div>
						{:else if newsSummaryQuery.data}
							{@const summary = newsSummaryQuery.data}
							<section class="p-4">
								<div class="mb-3 flex items-center gap-2.5">
									<div
										class="flex h-7 w-7 items-center justify-center rounded-md bg-info-bg text-info ring-1 ring-border"
									>
										<Activity class="h-3.5 w-3.5" />
									</div>
									<div>
										<h3 class="text-sm font-semibold leading-none text-fg-1">
											{summary.macro.title}
										</h3>
										<p class="mt-1 text-[11px] text-fg-4">Rates, oil, policy, capital flows</p>
									</div>
								</div>
								<ul class="space-y-2">
									{#each (summary.macro.bullets ?? []).slice(0, 3) as bullet (bullet)}
										<li class="grid grid-cols-[auto_1fr] gap-2 text-[13px] leading-5 text-fg-2">
											<span class="mt-2 h-1.5 w-1.5 rounded-full bg-mark"></span>
											<span>{bullet}</span>
										</li>
									{/each}
								</ul>
							</section>
							<section class="border-t border-border p-4 lg:border-t-0">
								<div class="mb-3 flex items-center gap-2.5">
									<div
										class="flex h-7 w-7 items-center justify-center rounded-md bg-warning-bg text-warning ring-1 ring-border"
									>
										<Building2 class="h-3.5 w-3.5" />
									</div>
									<div>
										<h3 class="text-sm font-semibold leading-none text-fg-1">
											{summary.real_estate.title}
										</h3>
										<p class="mt-1 text-[11px] text-fg-4">Projects, sales, infrastructure</p>
									</div>
								</div>
								<ul class="space-y-2">
									{#each (summary.real_estate.bullets ?? []).slice(0, 3) as bullet (bullet)}
										<li class="grid grid-cols-[auto_1fr] gap-2 text-[13px] leading-5 text-fg-2">
											<span class="mt-2 h-1.5 w-1.5 rounded-full bg-warning"></span>
											<span>{bullet}</span>
										</li>
									{/each}
								</ul>
							</section>
						{:else if newsSummaryQuery.isError}
							<div
								class="border-dashed border-border p-4 text-sm text-fg-4 lg:col-span-2"
							>
								Market brief unavailable
							</div>
						{/if}
						</div>
					</div>
				</div>

				<div
					class="transition-opacity duration-700 {newsSectionVisible ? 'opacity-100' : 'opacity-0'}"
				>
					{#if newsQuery.isPending}
						<div class="py-8 text-center text-sm text-fg-4">Loading…</div>
					{:else if newsQuery.isError}
						<div class="py-8 text-center text-sm text-error">Error loading news</div>
					{:else if newsArticles.length === 0}
						<div class="py-8 text-center text-sm text-fg-4">No articles available</div>
					{:else}
						<div class="space-y-3">
							{#each newsArticles as article (article.id)}
								<NewsCard {article} />
							{/each}
							{#if newsQuery.isFetchingNextPage}
								<div class="py-4 text-center text-sm text-fg-4">Loading more…</div>
							{/if}
							<div bind:this={sentinel} class="h-4"></div>
						</div>
					{/if}
				</div>
			</div>

	</PageContainer>

	{#if currentUser.data && (!currentUser.data.first_name || !currentUser.data.last_name)}
		<CompleteProfileModal />
	{/if}
</AppFrame>
