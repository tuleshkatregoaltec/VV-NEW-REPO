<script lang="ts">
import StandardDropdown from '../dropdowns/StandardDropdown.svelte'
import FilterToggle from './FilterToggle.svelte'
import { propertyType, timeframe } from './globalFilters.svelte'

const timeframes = ['Last Week', 'Last Month', 'Last 3 Months', 'Last 6 Months', 'Last Year']
</script>

<div class="mx-auto max-w-7xl px-3 sm:px-4 lg:px-1">
	<div class="flex flex-col items-start gap-3 border-b border-border py-3 sm:flex-row sm:items-center">
		<div class="flex-shrink-0">
			<FilterToggle options={['Residential', 'Commercial']} bind:selected={propertyType.current} />
		</div>

		<div class="flex w-full flex-col gap-3 sm:ml-auto sm:w-auto sm:flex-row">
			<div class="w-full sm:w-48">
				<StandardDropdown
					id="filterbar-timeframe"
					ariaLabel="Timeframe"
					options={timeframes}
					bind:value={timeframe.current}
				/>
			</div>
		</div>
	</div>
</div>
