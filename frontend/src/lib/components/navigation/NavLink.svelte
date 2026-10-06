<script lang="ts">
import { page } from '$app/state'

let {
	href,
	label,
	activePrefix = href
}: { href: string; label: string; activePrefix?: string } = $props()

const isActive = $derived(
	page.url.pathname === href ||
		page.url.pathname.startsWith(`${href}/`) ||
		page.url.pathname === activePrefix ||
		page.url.pathname.startsWith(`${activePrefix}/`)
)
</script>

<a
	{href}
class="rounded-md px-3 py-2 text-[13px] font-medium transition-colors duration-150 {isActive
		? 'bg-info-bg text-info font-semibold'
		: 'text-fg-3 hover:bg-panel hover:text-fg-1'}"
	aria-current={isActive ? 'page' : undefined}
>
	{label}
</a>
