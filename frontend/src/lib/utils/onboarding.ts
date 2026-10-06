const SELECTED_TIER_KEY = 'selected_tier'

export type PlanTier = 'tier1' | 'tier2'

export function storeSelectedTier(tier: PlanTier) {
	if (typeof sessionStorage === 'undefined') return
	sessionStorage.setItem(SELECTED_TIER_KEY, tier)
}

export function readSelectedTier(): PlanTier | null {
	if (typeof sessionStorage === 'undefined') return null
	const value = sessionStorage.getItem(SELECTED_TIER_KEY)
	return value === 'tier1' || value === 'tier2' ? value : null
}

export function clearSelectedTier() {
	if (typeof sessionStorage === 'undefined') return
	sessionStorage.removeItem(SELECTED_TIER_KEY)
}
