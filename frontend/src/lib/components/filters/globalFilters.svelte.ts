// src/lib/components/filters/globalFilters.svelte.ts
import { browser } from '$app/environment'

function createPersisted<T>(key: string, initial: T) {
	let state = $state(initial)

	// Load from localStorage on client
	if (browser) {
		const stored = localStorage.getItem(key)
		if (stored !== null) {
			try {
				state = JSON.parse(stored)
			} catch (e) {
				console.error(`Failed to parse ${key}:`, e)
			}
		}
	}

	return {
		get current() {
			return state
		},
		set current(v: T) {
			state = v
			if (browser) {
				localStorage.setItem(key, JSON.stringify(v))
			}
		}
	}
}

// Global filters (used across app)
export const propertyType = createPersisted('filter-propertyType', 'Residential')
export const timeframe = createPersisted('filter-timeframe', 'Last Month')
