<script lang="ts">
import { workbookStore } from '$lib/feasibility/workbook/store.svelte'

function fmt(value: number | null | undefined, digits = 0) {
	if (value === null || value === undefined || !Number.isFinite(value)) return '-'
	return value.toLocaleString('en-AE', {
		minimumFractionDigits: digits,
		maximumFractionDigits: digits
	})
}

function fmtPct(value: number | null | undefined, digits = 1) {
	if (value === null || value === undefined || !Number.isFinite(value)) return '-'
	return `${fmt(value, digits)}%`
}

function setNumber(key: keyof typeof workbookStore.inputs, raw: string) {
	if (raw.trim() === '') {
		clearInput(key)
		return
	}
	const value = Number(raw)
	workbookStore.updateInputs({ [key]: Number.isFinite(value) ? value : 0 } as any)
}

function clearInput(key: keyof typeof workbookStore.inputs) {
	workbookStore.updateInputs({ [key]: undefined } as any)
}

function formLabel(value: string | null | undefined) {
	if (value === 'tower') return 'Tower'
	if (value === 'mid_rise') return 'Mid-rise'
	if (value === 'low_rise') return 'Low-rise'
	return '-'
}

const outputs = $derived(workbookStore.outputs)
const inputs = $derived(workbookStore.inputs)
const massing = $derived(outputs?.siteMassing)

const INPUT =
	'w-full text-right px-1 py-0 text-[#1565C0] bg-transparent focus:outline-none tabular-nums'
const LABEL = 'px-2 py-[3px] text-slate-800'
const VALUE = 'px-2 py-[3px] text-right tabular-nums text-slate-900'
const VALUE_BLUE = 'px-2 py-[3px] text-right tabular-nums text-[#1565C0]'
const UNIT = 'px-2 py-[3px] text-slate-500 whitespace-nowrap'
</script>

{#if !outputs || !massing}
<div class="h-full flex items-center justify-center px-6 text-sm text-slate-400">
	No massing data available.
</div>
{:else}
<div class="overflow-auto flex-1 bg-white text-[11px] font-[Calibri,'Segoe_UI',Arial,sans-serif] select-none">
	<div class="bg-[#1F3864] text-white px-4 py-2.5 flex items-start justify-between gap-4">
		<div>
			<div class="text-[13px] font-bold tracking-wide">SITE MASSING TEST-FIT</div>
			<div class="text-[10px] text-blue-200 mt-0.5">Physical capacity view - coverage, floorplate, height, and unit capacity</div>
		</div>
		<div class="text-[10px] text-right leading-5 mt-0.5 shrink-0">
			<div><span class="text-[#90CAF9] font-semibold">■</span> Blue = Input</div>
			<div><span class="text-white font-semibold">■</span> Black = Derived</div>
		</div>
	</div>

	<div class="grid grid-cols-2 xl:grid-cols-6 border-b border-[#B8C4CE] bg-[#EEF2F7]">
		<div class="px-3 py-2 border-r border-[#D9D9D9]">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Building Count</div>
			<div class="text-[13px] font-bold text-slate-900">{fmt(massing.buildingCount)}</div>
		</div>
		<div class="px-3 py-2 border-r border-[#D9D9D9]">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Applied Coverage</div>
			<div class="text-[13px] font-bold text-slate-900">{fmtPct(massing.appliedCoveragePct)}</div>
		</div>
		<div class="px-3 py-2 border-r border-[#D9D9D9]">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Gross Floorplate</div>
			<div class="text-[13px] font-bold text-slate-900">{fmt(massing.typicalGrossFloorplateSqm)} sqm</div>
		</div>
		<div class="px-3 py-2 border-r border-[#D9D9D9]">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Physical Units</div>
			<div class="text-[13px] font-bold text-slate-900">{fmt(massing.totalPhysicalUnitCapacity)}</div>
		</div>
		<div class="px-3 py-2 border-r border-[#D9D9D9]">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">GFA Utilization</div>
			<div class="text-[13px] font-bold text-slate-900">{fmtPct(massing.gfaUtilizationPct)}</div>
		</div>
		<div class="px-3 py-2">
			<div class="text-[9px] uppercase tracking-wider text-slate-500 font-semibold">Est. Height</div>
			<div class="text-[13px] font-bold text-slate-900">{fmt(massing.estimatedMaxHeightM, 1)} m</div>
		</div>
	</div>

	<table class="w-full border-collapse" style="border-spacing:0">
		<tbody>
			<tr class="bg-[#1F3864]">
				<td colspan="4" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">A.&nbsp;&nbsp;MASSING CONTROLS</td>
			</tr>
			<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
				<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Input</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Value</th>
				<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Unit</th>
				<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Basis</th>
			</tr>
			<tr class="border-b border-[#D9D9D9]">
				<td class={LABEL}>Target coverage</td>
				<td class="p-0"><input type="number" step="1" min="0" max="100" class={INPUT} value={inputs.targetCoveragePct ?? massing.appliedCoveragePct} oninput={(e) => setNumber('targetCoveragePct', e.currentTarget.value)} /></td>
				<td class={UNIT}>%</td>
				<td class="px-2 py-[3px] text-slate-500">Default follows GIS max coverage or benchmark range.</td>
			</tr>
			<tr class="border-b border-[#D9D9D9]">
				<td class={LABEL}>Target building count</td>
				<td class="p-0"><input type="number" step="1" min="0" class={INPUT} value={inputs.targetBuildingCount ?? ''} placeholder={fmt(massing.buildingCount)} oninput={(e) => setNumber('targetBuildingCount', e.currentTarget.value)} /></td>
				<td class={UNIT}>buildings</td>
				<td class="px-2 py-[3px] text-slate-500">
					<button type="button" class="text-[#1565C0] hover:underline" onclick={() => clearInput('targetBuildingCount')}>Auto-size</button>
				</td>
			</tr>
			<tr class="border-b border-[#D9D9D9]">
				<td class={LABEL}>Max efficient tower floorplate</td>
				<td class="p-0"><input type="number" step="100" min="0" class={INPUT} value={inputs.maxEfficientTowerFloorplateSqm ?? ''} placeholder="2000" oninput={(e) => setNumber('maxEfficientTowerFloorplateSqm', e.currentTarget.value)} /></td>
				<td class={UNIT}>sqm</td>
				<td class="px-2 py-[3px] text-slate-500">
					<button type="button" class="text-[#1565C0] hover:underline" onclick={() => clearInput('maxEfficientTowerFloorplateSqm')}>Auto benchmark</button>
				</td>
			</tr>
			<tr class="border-b border-[#D9D9D9]">
				<td class={LABEL}>Min efficient tower floorplate</td>
				<td class="p-0"><input type="number" step="100" min="0" class={INPUT} value={inputs.minEfficientTowerFloorplateSqm ?? ''} placeholder="700" oninput={(e) => setNumber('minEfficientTowerFloorplateSqm', e.currentTarget.value)} /></td>
				<td class={UNIT}>sqm</td>
				<td class="px-2 py-[3px] text-slate-500">
					<button type="button" class="text-[#1565C0] hover:underline" onclick={() => clearInput('minEfficientTowerFloorplateSqm')}>Auto benchmark</button>
				</td>
			</tr>
			<tr class="border-b border-[#D9D9D9]">
				<td class={LABEL}>Residential floor-to-floor height</td>
				<td class="p-0"><input type="number" step="0.1" min="0" class={INPUT} value={inputs.floorToFloorHeightM ?? 3.2} oninput={(e) => setNumber('floorToFloorHeightM', e.currentTarget.value)} /></td>
				<td class={UNIT}>m</td>
				<td class="px-2 py-[3px] text-slate-500">Used for estimated building height.</td>
			</tr>
			<tr class="border-b border-[#D9D9D9]">
				<td class={LABEL}>Podium floor-to-floor height</td>
				<td class="p-0"><input type="number" step="0.1" min="0" class={INPUT} value={inputs.podiumFloorToFloorHeightM ?? 4} oninput={(e) => setNumber('podiumFloorToFloorHeightM', e.currentTarget.value)} /></td>
				<td class={UNIT}>m</td>
				<td class="px-2 py-[3px] text-slate-500">Used for estimated podium and overall height.</td>
			</tr>
			<tr class="border-b border-[#D9D9D9]">
				<td class={LABEL}>Ground floor height</td>
				<td class="p-0"><input type="number" step="0.1" min="0" class={INPUT} value={inputs.groundFloorHeightM ?? 5} oninput={(e) => setNumber('groundFloorHeightM', e.currentTarget.value)} /></td>
				<td class={UNIT}>m</td>
				<td class="px-2 py-[3px] text-slate-500">Used for estimated overall height.</td>
			</tr>
			<tr class="border-b border-[#D9D9D9]">
				<td class={LABEL}>Roof plant allowance</td>
				<td class="p-0"><input type="number" step="0.1" min="0" class={INPUT} value={inputs.roofPlantAllowanceM ?? 6} oninput={(e) => setNumber('roofPlantAllowanceM', e.currentTarget.value)} /></td>
				<td class={UNIT}>m</td>
				<td class="px-2 py-[3px] text-slate-500">Used for estimated overall height.</td>
			</tr>

			<tr class="bg-[#1F3864]">
				<td colspan="4" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">B.&nbsp;&nbsp;SITE CAPACITY</td>
			</tr>
			<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
				<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Metric</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Value</th>
				<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Unit</th>
				<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Note</th>
			</tr>
			<tr class="border-b border-[#D9D9D9]"><td class={LABEL}>Plot area</td><td class={VALUE}>{fmt(massing.plotAreaSqm)}</td><td class={UNIT}>sqm</td><td class="px-2 py-[3px] text-slate-500">From plot file / DDA data.</td></tr>
			<tr class="border-b border-[#D9D9D9]"><td class={LABEL}>Maximum GFA</td><td class={VALUE}>{fmt(massing.maxGfaSqm)}</td><td class={UNIT}>sqm</td><td class="px-2 py-[3px] text-slate-500">Regulatory GFA used by the model.</td></tr>
			<tr class="border-b border-[#D9D9D9]"><td class={LABEL}>Building form</td><td class={VALUE}>{formLabel(massing.buildingForm)}</td><td class={UNIT}></td><td class="px-2 py-[3px] text-slate-500">Classified from max storeys.</td></tr>
			<tr class="border-b border-[#D9D9D9]"><td class={LABEL}>Covered footprint</td><td class={VALUE}>{fmt(massing.coveredFootprintSqm)}</td><td class={UNIT}>sqm</td><td class="px-2 py-[3px] text-slate-500">Plot area x applied coverage.</td></tr>
			<tr class="border-b border-[#D9D9D9]"><td class={LABEL}>Total modelled footprint</td><td class={VALUE}>{fmt(massing.totalFootprintSqm)}</td><td class={UNIT}>sqm</td><td class="px-2 py-[3px] text-slate-500">Sum of building footprints.</td></tr>
			<tr class="border-b border-[#D9D9D9]"><td class={LABEL}>Coverage utilization</td><td class={VALUE}>{fmtPct(massing.coverageUtilizationPct)}</td><td class={UNIT}></td><td class="px-2 py-[3px] text-slate-500">Modelled footprint / covered footprint.</td></tr>
			<tr class="border-b border-[#D9D9D9]"><td class={LABEL}>GFA capacity at selected floors</td><td class={VALUE}>{fmt(massing.physicalMaxGfaSqm)}</td><td class={UNIT}>sqm</td><td class="px-2 py-[3px] text-slate-500">Covered footprint x selected / capped floors.</td></tr>
			<tr class="border-b border-[#D9D9D9]"><td class={LABEL}>Required total GFA floors at coverage</td><td class={VALUE}>{fmt(massing.requiredFloorsAtCoverage)}</td><td class={UNIT}>floors</td><td class="px-2 py-[3px] text-slate-500">Maximum GFA / covered footprint.</td></tr>
			<tr class="border-b border-[#D9D9D9]"><td class={LABEL}>Required coverage at selected floors</td><td class={VALUE}>{fmtPct(massing.requiredCoverageAtMaxStoreysPct)}</td><td class={UNIT}></td><td class="px-2 py-[3px] text-slate-500">Coverage required to fit max GFA within selected / capped floors.</td></tr>
			<tr class="border-b border-[#D9D9D9]"><td class={LABEL}>GFA shortfall</td><td class={VALUE}>{fmt(massing.gfaShortfallSqm)}</td><td class={UNIT}>sqm</td><td class="px-2 py-[3px] text-slate-500">Unbuildable GFA under current coverage and selected-floor assumptions.</td></tr>
			<tr class="border-b border-[#D9D9D9]"><td class={LABEL}>Weighted average unit size</td><td class={VALUE}>{fmt(massing.weightedAvgUnitSizeSqm, 1)}</td><td class={UNIT}>sqm</td><td class="px-2 py-[3px] text-slate-500">From current unit mix.</td></tr>
			<tr class="border-b border-[#D9D9D9]"><td class={LABEL}>Target unit count</td><td class={VALUE}>{fmt(massing.targetUnitCount)}</td><td class={UNIT}>units</td><td class="px-2 py-[3px] text-slate-500">Current unit mix count.</td></tr>
			<tr class="border-b border-[#D9D9D9]"><td class={LABEL}>Required residential floors for unit mix</td><td class={VALUE}>{fmt(massing.requiredResidentialFloorsForUnits)}</td><td class={UNIT}>floors</td><td class="px-2 py-[3px] text-slate-500">Current unit GLA / total net residential floorplate.</td></tr>
			<tr class="border-b border-[#D9D9D9]"><td class={LABEL}>Physical unit capacity</td><td class={VALUE}>{fmt(massing.totalPhysicalUnitCapacity)}</td><td class={UNIT}>units</td><td class="px-2 py-[3px] text-slate-500">Estimated units that fit on typical residential floors.</td></tr>
			<tr class="border-b border-[#D9D9D9]"><td class={LABEL}>Unit capacity gap</td><td class={massing.unitCapacityGap < 0 ? 'px-2 py-[3px] text-right tabular-nums text-amber-700 font-semibold' : VALUE}>{fmt(massing.unitCapacityGap)}</td><td class={UNIT}>units</td><td class="px-2 py-[3px] text-slate-500">Physical capacity less current unit count flags an impossible unit programme.</td></tr>
			<tr class="border-b border-[#D9D9D9]"><td class={LABEL}>Allocated GFA</td><td class={VALUE}>{fmt(massing.totalAllocatedGfaSqm)}</td><td class={UNIT}>sqm</td><td class="px-2 py-[3px] text-slate-500">Gross above-grade floor area allocated to buildings.</td></tr>

			<tr class="bg-[#1F3864]">
				<td colspan="10" class="px-2 py-[4px] text-white font-bold text-[11px] tracking-wide">C.&nbsp;&nbsp;BUILDING SCHEDULE</td>
			</tr>
		</tbody>
	</table>

	<table class="w-full border-collapse" style="border-spacing:0">
		<thead>
			<tr class="bg-[#D6DCE4] border-b border-[#B8C4CE]">
				<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Building</th>
				<th class="px-2 py-[4px] text-left text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Type</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Footprint sqm</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Floorplate sqm</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Net floorplate</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">GFA sqm</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Floors</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Height m</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Units / floor</th>
				<th class="px-2 py-[4px] text-right text-[9px] font-semibold text-slate-600 uppercase tracking-wider">Units</th>
			</tr>
		</thead>
		<tbody>
			{#each massing.buildings as building (building.id)}
				<tr class="border-b border-[#D9D9D9] hover:bg-slate-50/60">
					<td class="px-2 py-[3px] text-slate-800">{building.label}</td>
					<td class="px-2 py-[3px] text-slate-600">{building.buildingType.replaceAll('_', ' ')}</td>
					<td class={VALUE}>{fmt(building.footprintSqm)}</td>
					<td class={VALUE}>{fmt(building.grossFloorplateSqm)}</td>
					<td class={VALUE}>{fmt(building.netFloorplateSqm)}</td>
					<td class={VALUE}>{fmt(building.allocatedGfaSqm)}</td>
					<td class={VALUE_BLUE}>{fmt(building.totalFloors)}</td>
					<td class={VALUE}>{fmt(building.estimatedHeightM, 1)}</td>
					<td class={VALUE}>{fmt(building.unitsPerTypicalFloor)}</td>
					<td class={VALUE}>{fmt(building.totalUnits)}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
{/if}
