<script module lang="ts">
let nextId = 0
</script>

<script lang="ts">
	import { fly, fade } from 'svelte/transition';
	import { quintOut } from 'svelte/easing';
	import { getContext } from 'svelte';
	import { page } from '$app/state';

	type Item = { href: string; label: string };

	let {
		label,
		items
	}: {
		label: string;
		items: Item[];
	} = $props();

	const HOVER_DELAY = 150;

	// Use shared openDropdownId context so only one dropdown is open at a time
	let localState = $state<string | null>(null);
	let openDropdownIdContext = getContext<{ value: string | null }>('openDropdownId') ?? {
		get value() {
			return localState;
		},
		set value(v: string | null) {
			localState = v;
		}
	};

	const id = `nav-dropdown-${nextId++}`;
	let timeout: number | undefined;
	let isOpen = $derived(openDropdownIdContext.value === id);

	// Check if any dropdown item is active
	const isActive = $derived(
		items.some(
			(item) => page.url.pathname === item.href || page.url.pathname.startsWith(item.href + '/')
		)
	);

	function handleEnter() {
		clearTimeout(timeout);
		timeout = window.setTimeout(() => {
			openDropdownIdContext.value = id;
		}, HOVER_DELAY);
	}

	function handleLeave() {
		clearTimeout(timeout);
		timeout = window.setTimeout(() => {
			if (openDropdownIdContext.value === id) openDropdownIdContext.value = null;
		}, 200);
	}
</script>

<div class="relative" role="navigation" onmouseenter={handleEnter} onmouseleave={handleLeave}>
	<button
		class="flex items-center gap-1 rounded-md px-3 py-2 text-[13px] font-medium transition-colors duration-150 {isActive
			? 'bg-info-bg text-info font-semibold'
			: 'text-fg-3 hover:bg-panel hover:text-fg-1'}"
		aria-haspopup="true"
		aria-expanded={isOpen}
	>
		{label}
		<svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
		</svg>
	</button>

	{#if isOpen}
		<div
			class="ui-menu absolute left-0 mt-1 w-44 py-1"
			in:fly={{ y: -10, duration: 200, easing: quintOut }}
			out:fade={{ duration: 150 }}
		>
			{#each items as item (item.href)}
				<a
					href={item.href}
					class="block px-3 py-2 text-sm text-fg-3 transition-colors hover:bg-elevated hover:text-fg-1"
				>
					{item.label}
				</a>
			{/each}
		</div>
	{/if}
</div>
