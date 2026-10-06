<script lang="ts">
import { workbookStore } from '$lib/feasibility/workbook/store.svelte'

function fmt(v: number, d = 0) {
	return v.toLocaleString('en-AE', { minimumFractionDigits: d, maximumFractionDigits: d })
}
function setNumber(key: string, raw: string) {
	const v = Number(raw)
	workbookStore.updateAssumptions({ [key]: Number.isFinite(v) ? v : 0 })
}

const assumptions = $derived(workbookStore.assumptions)
const outputs = $derived(workbookStore.outputs)

const eiborRate = $derived(assumptions?.eiborRatePct ?? 0)
const landSpreadPct = $derived((assumptions?.landLoanSpreadBps ?? 0) / 100)
const conSpreadPct = $derived((assumptions?.constructionLoanSpreadBps ?? 0) / 100)
const permSpreadPct = $derived((assumptions?.btrPermDebtSpreadBps ?? 165) / 100)
const effectiveLandRate = $derived(outputs?.funding.landLoanRatePct ?? 0)
const effectiveConRate = $derived(outputs?.funding.constructionLoanRatePct ?? 0)
const effectivePermRate = $derived(eiborRate + permSpreadPct)
const totalDebtCapacity = $derived(outputs?.funding.totalDebtCapacityAed ?? 0)
const landLoanCapacity = $derived(outputs?.funding.landLoanCapacityAed ?? 0)
const blendedRate = $derived(
	totalDebtCapacity > 0 && landLoanCapacity > 0
		? (effectiveLandRate * landLoanCapacity +
				effectiveConRate * (totalDebtCapacity - landLoanCapacity)) /
				totalDebtCapacity
		: effectiveConRate
)

// Sensitivity table: EIBOR shifts
const sensitivityShifts = [-100, -50, 0, 50, 100, 200] as const

const INPUT =
	'w-full text-right px-1 py-0 text-[#1565C0] bg-transparent focus:outline-none tabular-nums text-[11px]'
const LABEL = 'px-2 py-[3px] text-slate-800'
const VALUE_BLACK = 'px-2 py-[3px] text-right tabular-nums text-slate-900'
const VALUE_BOLD = 'px-2 py-[3px] text-right tabular-nums text-slate-900 font-semibold'
const UNIT = 'px-2 py-[3px] text-slate-500 text-[10px]'
const ROW = 'border-b border-[#D9D9D9]'
</script>

<div class="overflow-auto flex-1 bg-white text-[11px] font-[Calibri,'Segoe_UI',Arial,sans-serif] select-none">

	<div class="bg-[#1F3864] text-white px-4 py-2.5 flex items-start justify-between gap-4">
		<div>
			<div class="text-[13px] font-bold tracking-wide">EIBOR RATE CURVE &amp; FINANCING COSTS</div>
			<div class="text-[10px] text-blue-200 mt-0.5">Base rate and financing spreads</div>
		</div>
	</div>

	<!-- Effective rate summary -->
	<div class="flex border-b border-[#B8C4CE] bg-[#EEF2F7] divide-x divide-[#D9D9D9]">
		<div class="px-2 py-1.5 flex-1">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">EIBOR Base Rate</div>
			<div class="text-[11px] font-bold text-[#1565C0] tabular-nums">{fmt(eiborRate, 2)}%</div>
		</div>
		<div class="px-2 py-1.5 flex-1">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Land Loan Rate</div>
			<div class="text-[11px] font-bold text-slate-900 tabular-nums">{fmt(effectiveLandRate, 2)}%</div>
		</div>
		<div class="px-2 py-1.5 flex-1">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Construction Loan Rate</div>
			<div class="text-[11px] font-bold text-slate-900 tabular-nums">{fmt(effectiveConRate, 2)}%</div>
		</div>
	</div>

	<table class="w-full border-collapse" style="border-spacing:0">
		<colgroup>
			<col style="width:2.5%">
			<col style="width:46%">
			<col style="width:28%">
			<col style="width:13%">
			<col style="width:10%">
		</colgroup>
		<tbody>

		<!-- SECTION A: EIBOR Base Rate -->
		<tr class="bg-[#1F3864]">
			<td colspan="5" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">A. &nbsp; EIBOR BASE RATE</td>
		</tr>
		<tr class={ROW}>
			<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">1</td>
			<td class={LABEL}>EIBOR Reference Rate</td>
			<td class="p-0">
				<input type="number" step="0.01" min="0" max="20" class={INPUT}
					value={assumptions?.eiborRatePct ?? 0}
					oninput={(e) => setNumber('eiborRatePct', e.currentTarget.value)} />
			</td>
			<td class={UNIT}>% p.a.</td>
			<td class="px-2 py-[3px] text-right text-[10px] text-slate-400"></td>
		</tr>

		<tr class={ROW}>
			<td class="px-1 py-[3px]"></td>
			<td class="px-2 py-[3px] text-slate-600 font-medium">Selected Base Rate</td>
			<td class="px-2 py-[3px] text-right tabular-nums text-[#1565C0] font-semibold">{fmt(eiborRate, 2)}%</td>
			<td class={UNIT}>% p.a.</td>
			<td></td>
		</tr>

		<!-- SECTION B: Spreads -->
		<tr class="bg-[#1F3864]">
			<td colspan="5" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">B. &nbsp; LOAN SPREADS / MARGINS</td>
		</tr>
		<tr class={ROW}>
			<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">2</td>
			<td class={LABEL}>Land Loan Spread</td>
			<td class="p-0">
				<input type="number" step="5" min="0" class={INPUT}
					value={assumptions?.landLoanSpreadBps ?? 0}
					oninput={(e) => setNumber('landLoanSpreadBps', e.currentTarget.value)} />
			</td>
			<td class={UNIT}>bps</td>
			<td class="px-2 py-[3px] text-right text-[10px] text-slate-500">{fmt(landSpreadPct, 2)}%</td>
		</tr>
		<tr class={ROW}>
			<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">3</td>
			<td class={LABEL}>Construction Loan Spread</td>
			<td class="p-0">
				<input type="number" step="5" min="0" class={INPUT}
					value={assumptions?.constructionLoanSpreadBps ?? 0}
					oninput={(e) => setNumber('constructionLoanSpreadBps', e.currentTarget.value)} />
			</td>
			<td class={UNIT}>bps</td>
			<td class="px-2 py-[3px] text-right text-[10px] text-slate-500">{fmt(conSpreadPct, 2)}%</td>
		</tr>
		<tr class={ROW}>
			<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">4</td>
			<td class={LABEL}>Permanent Loan Spread <span class="text-slate-400 font-normal italic">(BTR refi)</span></td>
			<td class="p-0">
				<input type="number" step="5" min="0" class={INPUT}
					value={assumptions?.btrPermDebtSpreadBps ?? 165}
					oninput={(e) => setNumber('btrPermDebtSpreadBps', e.currentTarget.value)} />
			</td>
			<td class={UNIT}>bps</td>
			<td class="px-2 py-[3px] text-right text-[10px] text-slate-500">{fmt(permSpreadPct, 2)}%</td>
		</tr>

		<!-- SECTION C: Effective Rates -->
		<tr class="bg-[#1F3864]">
			<td colspan="5" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">C. &nbsp; EFFECTIVE FINANCING RATES</td>
		</tr>
		<tr class="border-b border-[#D9D9D9] bg-[#E8F5E9]">
			<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">→</td>
			<td class="px-2 py-[3px] text-slate-800 font-medium">Land Loan Effective Rate</td>
			<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 font-bold text-[13px]">{fmt(effectiveLandRate, 2)}%</td>
			<td class={UNIT}>= EIBOR + land spread</td>
			<td class="px-2 py-[3px] text-right text-[10px] text-slate-500">{fmt(eiborRate,2)} + {fmt(landSpreadPct,2)}</td>
		</tr>
		<tr class="border-b border-[#D9D9D9] bg-[#E8F5E9]">
			<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">→</td>
			<td class="px-2 py-[3px] text-slate-800 font-medium">Construction Loan Effective Rate</td>
			<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 font-bold text-[13px]">{fmt(effectiveConRate, 2)}%</td>
			<td class={UNIT}>= EIBOR + construction spread</td>
			<td class="px-2 py-[3px] text-right text-[10px] text-slate-500">{fmt(eiborRate,2)} + {fmt(conSpreadPct,2)}</td>
		</tr>
		<tr class="border-b border-[#D9D9D9] bg-[#E8F5E9]">
			<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">→</td>
			<td class="px-2 py-[3px] text-slate-800 font-medium">Permanent Loan Effective Rate</td>
			<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 font-bold text-[13px]">{fmt(effectivePermRate, 2)}%</td>
			<td class={UNIT}>= EIBOR + permanent spread</td>
			<td class="px-2 py-[3px] text-right text-[10px] text-slate-500">{fmt(eiborRate,2)} + {fmt(permSpreadPct,2)}</td>
		</tr>
		<tr class="border-b border-[#D9D9D9] bg-[#E8F5E9]">
			<td class="px-1 py-[3px] text-slate-400 text-[10px] text-center">→</td>
			<td class="px-2 py-[3px] text-slate-800 font-medium">Blended Dev Debt Rate</td>
			<td class="px-2 py-[3px] text-right tabular-nums text-slate-900 font-bold text-[13px]">{fmt(blendedRate, 2)}%</td>
			<td class={UNIT}>weighted by tranche size</td>
			<td class="px-2 py-[3px] text-right text-[10px] text-slate-500">land / construction mix</td>
		</tr>

		<!-- SECTION D: Rate Sensitivity -->
		<tr class="bg-[#1F3864]">
			<td colspan="5" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">D. &nbsp; EIBOR SENSITIVITY — EFFECTIVE RATES</td>
		</tr>
		<!-- sensitivity table header -->
		<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
			<td colspan="2" class="px-2 py-[3px] text-slate-700 font-semibold text-[10px]">EIBOR Scenario</td>
			<td class="px-2 py-[3px] text-right text-[10px] font-semibold text-slate-700">EIBOR Rate</td>
			<td class="px-2 py-[3px] text-right text-[10px] font-semibold text-slate-700">Land Rate</td>
			<td class="px-2 py-[3px] text-right text-[10px] font-semibold text-slate-700">Con. Rate</td>
		</tr>
		{#each sensitivityShifts as shift}
			{@const scenarioEibor = eiborRate + shift / 100}
			{@const scenarioLand = scenarioEibor + landSpreadPct}
			{@const scenarioCon = scenarioEibor + conSpreadPct}
			{@const isBase = shift === 0}
			<tr class="border-b border-[#EBEBEB] {isBase ? 'bg-[#E8F5E9]' : ''}">
				<td colspan="2" class="px-2 py-[3px] text-slate-700 {isBase ? 'font-semibold' : ''}">
					{shift === 0 ? 'Base case (current)' : shift > 0 ? `+${shift} bps` : `${shift} bps`}
				</td>
				<td class="px-2 py-[3px] text-right tabular-nums {isBase ? 'font-semibold text-[#1565C0]' : 'text-slate-600'}">{fmt(scenarioEibor, 2)}%</td>
				<td class="px-2 py-[3px] text-right tabular-nums {isBase ? 'font-semibold text-slate-900' : 'text-slate-600'}">{fmt(scenarioLand, 2)}%</td>
				<td class="px-2 py-[3px] text-right tabular-nums {isBase ? 'font-semibold text-slate-900' : 'text-slate-600'}">{fmt(scenarioCon, 2)}%</td>
			</tr>
		{/each}

		<tr><td colspan="5" class="py-4"></td></tr>
		</tbody>
	</table>
</div>
