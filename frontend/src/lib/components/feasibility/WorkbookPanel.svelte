<script lang="ts">
import type { FeasibilityStudy } from '$lib/feasibility/workbook/models'
import { workbookStore } from '$lib/feasibility/workbook/store.svelte'
import { feasibilityStudy } from '$lib/stores/feasibilityStudy.svelte'
import SpreadsheetPanel from './SpreadsheetPanel.svelte'

let loadedStudyRef = $state<FeasibilityStudy | null>(null)

$effect(() => {
	const study = feasibilityStudy.study
	if (!study) {
		loadedStudyRef = null
		workbookStore.reset()
		return
	}
	if (loadedStudyRef === study) return
	workbookStore.loadStudy({
		plotData: study.plot_data,
		assumptions: study.assumptions,
		study_context: study.study_context,
		research: study.research
	})
	loadedStudyRef = study
})
</script>

{#if feasibilityStudy.study}
	<div class="theme-light h-full overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
		<SpreadsheetPanel />
	</div>
{/if}
