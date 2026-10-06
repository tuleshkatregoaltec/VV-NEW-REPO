<script lang="ts">
import { Calendar } from 'lucide-svelte'

interface Props {
	startDate?: string
	endDate?: string
	onchange?: (dates: { start: string | null; end: string | null }) => void
	label?: string
}

let { startDate = '', endDate = '', onchange, label = 'Date Range' }: Props = $props()

let localStart = $state(startDate)
let localEnd = $state(endDate)

function handleChange() {
	if (onchange) {
		onchange({
			start: localStart || null,
			end: localEnd || null
		})
	}
}

function clearDates() {
	localStart = ''
	localEnd = ''
	handleChange()
}

// Get today's date in YYYY-MM-DD format
const today = new Date().toISOString().split('T')[0]
</script>

<div class="date-range-picker">
	{#if label}
		<label class="label">
			<Calendar size={16} color="var(--text-tertiary, #9ca3af)" />
			<span>{label}</span>
		</label>
	{/if}

	<div class="inputs-container">
		<div class="input-group">
			<label for="start-date" class="input-label">From</label>
			<input
				id="start-date"
				type="date"
				bind:value={localStart}
				onchange={handleChange}
				max={localEnd || today}
				class="date-input"
			/>
		</div>

		<div class="separator">to</div>

		<div class="input-group">
			<label for="end-date" class="input-label">To</label>
			<input
				id="end-date"
				type="date"
				bind:value={localEnd}
				onchange={handleChange}
				min={localStart}
				max={today}
				class="date-input"
			/>
		</div>

		{#if localStart || localEnd}
			<button type="button" onclick={clearDates} class="clear-btn" title="Clear dates"> × </button>
		{/if}
	</div>
</div>

<style>
	.date-range-picker {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.label {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--text-secondary, #6b7280);
	}

	.inputs-container {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.input-group {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		flex: 1;
		min-width: 140px;
	}

	.input-label {
		font-size: 0.75rem;
		color: var(--text-tertiary, #9ca3af);
		font-weight: 500;
	}

	.date-input {
		padding: 0.5rem 0.75rem;
		border: 1px solid var(--border-color, #e5e7eb);
		border-radius: 0.375rem;
		font-size: 0.875rem;
		background: var(--bg-primary, white);
		color: var(--text-primary, #111827);
		transition: all 0.15s ease;
	}

	.date-input:hover {
		border-color: var(--border-hover, #d1d5db);
	}

	.date-input:focus {
		outline: none;
		border-color: var(--primary-color, #3b82f6);
		box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
	}

	.separator {
		font-size: 0.875rem;
		color: var(--text-tertiary, #9ca3af);
		padding-top: 1.25rem;
	}

	.clear-btn {
		padding: 0.5rem 0.75rem;
		margin-top: 1.25rem;
		background: var(--bg-secondary, #f3f4f6);
		border: 1px solid var(--border-color, #e5e7eb);
		border-radius: 0.375rem;
		color: var(--text-secondary, #6b7280);
		font-size: 1.25rem;
		cursor: pointer;
		transition: all 0.15s ease;
		line-height: 1;
	}

	.clear-btn:hover {
		background: var(--bg-tertiary, #e5e7eb);
		color: var(--text-primary, #111827);
	}
</style>
