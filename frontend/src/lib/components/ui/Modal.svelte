<script lang="ts">
import type { Snippet } from 'svelte'

let {
	open = false,
	onClose,
	title,
	size = 'lg',
	children
}: {
	open: boolean
	onClose: () => void
	title: string
	size?: 'md' | 'lg' | 'xl'
	children?: Snippet
} = $props()

// Handle ESC key
function handleKeydown(event: KeyboardEvent) {
	if (event.key === 'Escape' && open) {
		onClose()
	}
}

// Handle backdrop click
function handleBackdropClick(event: MouseEvent) {
	if (event.target === event.currentTarget) {
		onClose()
	}
}

// Prevent body scroll when modal is open
$effect(() => {
	if (open) {
		document.body.style.overflow = 'hidden'
	} else {
		document.body.style.overflow = ''
	}

	return () => {
		document.body.style.overflow = ''
	}
})

const sizeClasses = {
	md: 'max-w-2xl',
	lg: 'max-w-4xl',
	xl: 'max-w-6xl'
}
</script>

<svelte:window onkeydown={handleKeydown} />

{#if open}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50  animate-fade-in"
		onclick={handleBackdropClick}
		role="presentation"
	>
		<div
			class="bg-white rounded-lg border border-border shadow-xl w-full {sizeClasses[
				size
			]} max-h-[90vh] overflow-hidden animate-scale-in"
			role="dialog"
			aria-modal="true"
			aria-labelledby="modal-title"
		>
			<!-- Header -->
			<div
				class="flex items-center justify-between px-6 py-4 border-b border-border bg-white"
			>
				<h2 id="modal-title" class="text-2xl font-semibold text-fg-1">{title}</h2>
				<button
					onclick={onClose}
					class="p-2 rounded-lg hover:bg-slate-100 transition-colors"
					aria-label="Close modal"
				>
					<svg class="w-6 h-6 text-fg-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M6 18L18 6M6 6l12 12"
						/>
					</svg>
				</button>
			</div>

			<!-- Content -->
			<div class="overflow-y-auto max-h-[calc(90vh-80px)] px-6 py-6">
				{@render children?.()}
			</div>
		</div>
	</div>
{/if}

<style>
	@keyframes fade-in {
		from {
			opacity: 0;
		}
		to {
			opacity: 1;
		}
	}

	@keyframes scale-in {
		from {
			opacity: 0;
			transform: scale(0.95);
		}
		to {
			opacity: 1;
			transform: scale(1);
		}
	}

	.animate-fade-in {
		animation: fade-in 0.2s ease-out;
	}

	.animate-scale-in {
		animation: scale-in 0.2s ease-out;
	}
</style>
