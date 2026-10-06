<script lang="ts">
// TTS/BIWS financial modeling color legend
// Blue = hardcoded input, Black = formula / ordinary values, Green = cross-sheet link,
// Amber = caution / threshold watch, Red = error / broken check only.
// Parentheses indicate negatives / outflows.
</script>

<div class="flex items-center gap-4 text-[10px] tracking-wide">
	<span class="flex items-center gap-1">
		<span class="inline-block w-2.5 h-2.5 rounded-sm bg-[#1565C0]"></span>
		<span class="text-slate-500">Input</span>
	</span>
	<span class="flex items-center gap-1">
		<span class="inline-block w-2.5 h-2.5 rounded-sm bg-slate-800"></span>
		<span class="text-slate-500">Formula</span>
	</span>
	<span class="flex items-center gap-1">
		<span class="inline-block w-2.5 h-2.5 rounded-sm bg-emerald-700"></span>
		<span class="text-slate-500">Cross-ref</span>
	</span>
	<span class="flex items-center gap-1">
		<span class="inline-block w-2.5 h-2.5 rounded-sm bg-amber-500"></span>
		<span class="text-slate-500">Watch item</span>
	</span>
	<span class="flex items-center gap-1">
		<span class="inline-block w-2.5 h-2.5 rounded-sm bg-rose-600"></span>
		<span class="text-slate-500">Error / broken check</span>
	</span>
	<span class="text-slate-400">( ) = outflow / negative value</span>
</div>
