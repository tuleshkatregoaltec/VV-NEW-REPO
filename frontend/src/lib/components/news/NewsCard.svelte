<script lang="ts">
import type { NewsArticleResponse } from '$lib/api/news'

let { article }: { article: NewsArticleResponse } = $props()

let imageFailed = $state(false)
const imageSrc = $derived(article.thumbnail_url || article.thumbnail_base64)
const showImage = $derived(Boolean(imageSrc) && !imageFailed)

function handleImageError() {
	imageFailed = true
}

function formatRelativeTime(dateString: string | null): string {
	if (!dateString) return ''

	const now = new Date()
	const date = new Date(dateString)
	const diffInMs = now.getTime() - date.getTime()
	const diffInMinutes = Math.floor(diffInMs / (1000 * 60))
	const diffInHours = Math.floor(diffInMs / (1000 * 60 * 60))
	const diffInDays = Math.floor(diffInMs / (1000 * 60 * 60 * 24))

	if (diffInMinutes < 60) {
		return diffInMinutes === 1 ? '1 minute ago' : `${diffInMinutes} minutes ago`
	} else if (diffInHours < 24) {
		return diffInHours === 1 ? '1 hour ago' : `${diffInHours} hours ago`
	} else {
		return diffInDays === 1 ? '1 day ago' : `${diffInDays} days ago`
	}
}

const relativeTime = $derived(formatRelativeTime(article.publish_date))
const sourceLabel = $derived.by(() => {
	try {
		return new URL(article.url).hostname.replace(/^www\./, '')
	} catch {
		return null
	}
})
</script>

<a
	href={article.url}
	target="_blank"
	rel="noopener noreferrer"
	class="group flex gap-4 p-5 bg-card border border-border rounded-lg no-underline text-inherit hover:border-strong transition-colors duration-200"
>
	{#if showImage}
		<img
			src={imageSrc}
			alt={article.headline}
			loading="lazy"
			decoding="async"
			width="144"
			height="96"
			onerror={handleImageError}
			class="w-36 h-24 object-cover rounded border border-border flex-shrink-0"
		/>
	{:else}
		<div
			aria-hidden="true"
			class="w-36 h-24 rounded border border-border bg-app flex-shrink-0 flex items-center justify-center px-2 text-xs font-semibold text-fg-4"
		>
			<span class="truncate">{sourceLabel ?? 'News'}</span>
		</div>
	{/if}
	<div class="flex flex-col gap-2 flex-1">
		<div class="flex items-center gap-2 text-xs text-fg-4">
			{#if sourceLabel}
				<span class="font-semibold text-fg-3">{sourceLabel}</span>
				<span class="text-fg-5">•</span>
			{/if}
			<time>{relativeTime}</time>
		</div>
		<h3
			class="text-base font-semibold text-fg-1 group-hover:text-primary-light line-clamp-2 transition-colors duration-200"
		>
			{article.headline}
		</h3>
	</div>
	<div class="flex items-center opacity-0 group-hover:opacity-100 transition-opacity duration-200">
		<svg class="w-5 h-5 text-fg-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
		</svg>
	</div>
</a>
