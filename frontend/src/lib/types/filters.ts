export interface FilterDefinition {
	id: string
	label: string
	type: 'searchable' | 'standard' | 'price-range' | 'checkbox' | string
	options?: string[]
	placeholderMin?: string
	placeholderMax?: string
	optional?: boolean
}
