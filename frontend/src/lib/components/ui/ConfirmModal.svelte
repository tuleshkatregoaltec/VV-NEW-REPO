<script lang="ts">
let {
	open = false,
	title,
	message,
	confirmText = 'Confirm',
	cancelText = 'Cancel',
	confirmVariant = 'danger',
	onConfirm,
	onCancel
}: {
	open: boolean
	title: string
	message: string
	confirmText?: string
	cancelText?: string
	confirmVariant?: 'danger' | 'primary'
	onConfirm: () => void
	onCancel: () => void
} = $props()

// Handle ESC key
function handleKeydown(event: KeyboardEvent) {
	if (event.key === 'Escape' && open) {
		onCancel()
	}
}

// Handle backdrop click
function handleBackdropClick(event: MouseEvent) {
	if (event.target === event.currentTarget) {
		onCancel()
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

const confirmButtonClasses =
	confirmVariant === 'danger'
		? 'bg-error hover:bg-[#8a1f1f] text-on-navy'
		: 'bg-navy hover:bg-primary-hover text-on-navy'
</script>

<svelte:window onkeydown={handleKeydown} />

{#if open}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-[color:rgba(5,13,24,0.45)] p-4"
		onclick={handleBackdropClick}
		role="presentation"
	>
		<div
			class="w-full max-w-md rounded-xl border border-border bg-white shadow-xl"
			role="dialog"
			aria-modal="true"
			aria-labelledby="confirm-title"
		>
			<!-- Header -->
			<div class="border-b border-border px-6 py-4">
				<h3 id="confirm-title" class="text-lg font-semibold text-fg-1">{title}</h3>
			</div>

			<!-- Content -->
			<div class="px-6 py-4">
				<p class="text-fg-3">{message}</p>
			</div>

			<!-- Actions -->
			<div class="flex justify-end gap-3 border-t border-border px-6 py-4">
				{#if cancelText}
					<button
						onclick={onCancel}
						class="rounded-md border border-border bg-white px-4 py-2 text-sm font-medium text-fg-2 transition hover:bg-slate-50"
					>
						{cancelText}
					</button>
				{/if}
				<button
					onclick={onConfirm}
					class="rounded-md px-4 py-2 text-sm font-medium transition {confirmButtonClasses}"
				>
					{confirmText}
				</button>
			</div>
		</div>
	</div>
{/if}
