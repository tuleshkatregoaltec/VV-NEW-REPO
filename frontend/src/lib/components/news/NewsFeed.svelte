<script lang="ts">
import { createInfiniteQuery } from '@tanstack/svelte-query'
import { onMount } from 'svelte'
import { newsQueries } from '$lib/queries/news'
import NewsCard from './NewsCard.svelte'

const LIMIT = 20

const newsQuery = createInfiniteQuery(() => newsQueries.listInfinite('feed', LIMIT))

let sentinel = $state<HTMLDivElement | undefined>()

onMount(() => {
	const observer = new IntersectionObserver((entries) => {
		if (entries[0].isIntersecting && newsQuery.hasNextPage && !newsQuery.isFetchingNextPage) {
			newsQuery.fetchNextPage()
		}
	})

	if (sentinel) observer.observe(sentinel)
	return () => observer.disconnect()
})

const allArticles = $derived(newsQuery.data?.pages.flatMap((page) => page.articles) ?? [])
</script>

<div class="flex flex-col gap-4">
	{#if newsQuery.isPending}
		<div class="text-fg-4">Loading news...</div>
	{:else if newsQuery.isError}
		<div class="text-error">Error loading news</div>
	{:else}
		{#each allArticles as article (article.id)}
			<NewsCard {article} />
		{/each}

		<div bind:this={sentinel}></div>

		{#if newsQuery.isFetchingNextPage}
			<div class="py-4 text-center text-fg-4">Loading more...</div>
		{/if}
	{/if}
</div>
