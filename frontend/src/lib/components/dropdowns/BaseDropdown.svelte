<script module lang="ts">
let nextId = 0
</script>

<script lang="ts">
	import { getContext, tick } from 'svelte'
	import { fly, fade } from 'svelte/transition'
	import { quintOut } from 'svelte/easing'
	import type { Snippet } from 'svelte'

	type DropdownVariant = 'field' | 'inverse' | 'icon'

	let {
		id = `dropdown-${nextId++}`,
		ariaLabel,
		displayValue,
		align = 'left',
		variant = 'field',
		button,
		buttonClass = '',
		menuClass = '',
		focusOnOpen = false,
		children,
		onOpen,
		onClose
	}: {
		id?: string
		ariaLabel: string
		displayValue: string
		align?: 'left' | 'right'
		variant?: DropdownVariant
		button?: Snippet<[{ isOpen: boolean }]>
		buttonClass?: string
		menuClass?: string
		focusOnOpen?: boolean
		children: Snippet<[{ close: () => void }]>
		onOpen?: () => void
		onClose?: () => void
	} = $props()

	let localState = $state<string | null>(null)
	let triggerNode = $state<HTMLButtonElement | null>(null)
	let menuNode = $state<HTMLDivElement | null>(null)
	let openDropdownIdContext = getContext<{ value: string | null }>('openDropdownId') ?? {
		get value() {
			return localState
		},
		set value(v: string | null) {
			localState = v
		}
	}

	let isOpen = $derived(openDropdownIdContext.value === id)
	let resolvedButtonClass = $derived(buttonClass || getButtonClass(variant))
	let resolvedMenuClass = $derived(menuClass || getMenuClass(variant))

	let wasOpen = $state(false)

	$effect(() => {
		if (isOpen && !wasOpen) {
			onOpen?.()
			wasOpen = true
		} else if (!isOpen && wasOpen) {
			onClose?.()
			wasOpen = false
		}
	})

	$effect(() => {
		if (!isOpen || !focusOnOpen) return

		tick().then(() => {
			window.setTimeout(() => {
				if (!isOpen) return
				menuNode
					?.querySelector<HTMLElement>(
						'[data-dropdown-initial-focus], input, button, [tabindex]:not([tabindex="-1"])'
					)
					?.focus()
			}, 50)
		})
	})

	function toggle() {
		if (isOpen) {
			close({ restoreFocus: true })
			return
		}
		openDropdownIdContext.value = id
	}

	function close({ restoreFocus = false }: { restoreFocus?: boolean } = {}) {
		openDropdownIdContext.value = null
		if (restoreFocus) {
			tick().then(() => getTriggerNode()?.focus())
		}
	}

	function getTriggerNode(): HTMLButtonElement | null {
		return triggerNode ?? (document.getElementById(`${id}-button`) as HTMLButtonElement | null)
	}

	function getButtonClass(v: DropdownVariant) {
		if (v === 'inverse') {
			return 'flex h-10 w-full cursor-pointer items-center justify-between rounded-md border border-bone/15 bg-bone/10 px-3 text-left text-sm font-semibold text-bone transition-colors duration-200 hover:bg-bone/15 focus:outline-none focus:ring-2 focus:ring-bone/30'
		}
		if (v === 'icon') {
			return 'ui-button relative h-10 cursor-pointer gap-2 px-3 text-sm font-medium'
		}
		return 'ui-field flex h-10 w-full cursor-pointer items-center justify-between px-3 text-left text-sm'
	}

	function getMenuClass(v: DropdownVariant) {
		if (v === 'inverse') {
			return 'ui-menu absolute z-50 mt-2 overflow-hidden'
		}
		return 'ui-menu absolute z-50 mt-2 overflow-hidden'
	}

	function handleTriggerKeydown(event: KeyboardEvent) {
		if (event.key === 'Enter' || event.key === ' ') {
			event.preventDefault()
			toggle()
		}

		if (event.key === 'ArrowDown') {
			event.preventDefault()
			openDropdownIdContext.value = id
		}
	}

	function handleWindowKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape' && isOpen) {
			event.preventDefault()
			close({ restoreFocus: true })
		}
	}

	// Reusable click outside action
	function clickOutside(node: HTMLElement, callback: () => void) {
		function handleClick(event: MouseEvent) {
			if (!node.contains(event.target as Node)) {
				callback()
			}
		}

		document.addEventListener('mousedown', handleClick, true)

		return {
			destroy() {
				document.removeEventListener('mousedown', handleClick, true)
			}
		}
	}
</script>

<svelte:window onkeydown={handleWindowKeydown} />

<div
	id="dropdown-container-{id}"
	use:clickOutside={() => {
		if (isOpen) close({ restoreFocus: false })
	}}
>
	<div class="relative">
		{#if button}
			<button
				bind:this={triggerNode}
				id="{id}-button"
				type="button"
				class={resolvedButtonClass}
				onclick={toggle}
				onkeydown={handleTriggerKeydown}
				aria-label={ariaLabel}
				aria-haspopup="true"
				aria-expanded={isOpen}
				aria-controls="{id}-menu"
			>
				{@render button({ isOpen })}
			</button>
		{:else}
			<button
				bind:this={triggerNode}
				id="{id}-button"
				type="button"
				class={resolvedButtonClass}
				onclick={toggle}
				onkeydown={handleTriggerKeydown}
				aria-label={ariaLabel}
				aria-haspopup="true"
				aria-expanded={isOpen}
				aria-controls="{id}-menu"
			>
				<span class={!displayValue ? 'text-fg-5' : ''}>
					{displayValue || 'Select...'}
				</span>
				<svg
					class="h-4 w-4 text-fg-4 transition-transform duration-200"
					class:rotate-180={isOpen}
					fill="none"
					stroke="currentColor"
					stroke-width="2"
					viewBox="0 0 24 24"
				>
					<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
				</svg>
			</button>
		{/if}

		{#if isOpen}
			<div
				bind:this={menuNode}
				id="{id}-menu"
				class="{resolvedMenuClass} {align === 'right' ? 'right-0' : 'left-0'}"
				style={align === 'right' ? 'min-width: 200px;' : 'width: 100%;'}
				in:fly={{ y: -10, duration: 200, easing: quintOut }}
				out:fade={{ duration: 150 }}
			>
				{@render children({ close })}
			</div>
		{/if}
	</div>
</div>
