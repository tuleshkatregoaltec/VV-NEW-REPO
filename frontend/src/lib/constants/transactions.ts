// Property usage types
export const PROPERTY_USAGE = {
	RESIDENTIAL: 'Residential',
	COMMERCIAL: 'Commercial'
} as const

// Column type definition
export type ColumnDefinition = {
	id: string
	label: string
	align?: 'left' | 'center' | 'right'
	format?: (value: any, row?: any) => string
	badge?: boolean
	highlighted?: boolean
	defaultVisible?: boolean // If false, column is hidden by default but can be toggled on
}

// Column definitions for sales transactions table
export const RESIDENTIAL_COLUMNS: ColumnDefinition[] = [
	{ id: 'date', label: 'Date', align: 'left', defaultVisible: true },
	{ id: 'area_name', label: 'Area', align: 'left', defaultVisible: false },
	{ id: 'project', label: 'Project', align: 'left', defaultVisible: true },
	{ id: 'building', label: 'Building', align: 'left', defaultVisible: true },
	{ id: 'propertyType', label: 'Property Type', align: 'left', defaultVisible: true },
	{ id: 'bedrooms', label: 'Bedrooms', align: 'left', badge: true, defaultVisible: true },
	{
		id: 'area',
		label: 'Area (sq.m)',
		align: 'right',
		format: (val: number) => val.toLocaleString(),
		defaultVisible: true
	},
	{
		id: 'price',
		label: 'Price (AED)',
		align: 'right',
		format: (val: number) => val.toLocaleString(),
		defaultVisible: true
	},
	{
		id: 'pricePerSqM',
		label: 'Price/sq.m',
		align: 'right',
		highlighted: true,
		format: (val: number) => val.toLocaleString(),
		defaultVisible: true
	},
	{ id: 'registration', label: 'Registration', align: 'left', defaultVisible: false },
	{ id: 'trans_group', label: 'Group', align: 'left', defaultVisible: false },
	{ id: 'procedure_name', label: 'Procedure', align: 'left', defaultVisible: false },
	{ id: 'landmark', label: 'Landmark', align: 'left', defaultVisible: false },
	{ id: 'metro', label: 'Nearest Metro', align: 'left', defaultVisible: false },
	{ id: 'mall', label: 'Nearest Mall', align: 'left', defaultVisible: false }
]

export const COMMERCIAL_COLUMNS: ColumnDefinition[] = [
	{ id: 'date', label: 'Date', align: 'left', defaultVisible: true },
	{ id: 'area_name', label: 'Area', align: 'left', defaultVisible: false },
	{ id: 'project', label: 'Project', align: 'left', defaultVisible: true },
	{ id: 'building', label: 'Building', align: 'left', defaultVisible: true },
	{ id: 'propertyType', label: 'Property Type', align: 'left', defaultVisible: true },
	{ id: 'propertySubType', label: 'Sub Type', align: 'left', defaultVisible: true },
	{
		id: 'area',
		label: 'Area (sq.m)',
		align: 'right',
		format: (val: number) => val.toLocaleString(),
		defaultVisible: true
	},
	{
		id: 'price',
		label: 'Price (AED)',
		align: 'right',
		format: (val: number) => val.toLocaleString(),
		defaultVisible: true
	},
	{
		id: 'pricePerSqM',
		label: 'Price/sq.m',
		align: 'right',
		highlighted: true,
		format: (val: number) => val.toLocaleString(),
		defaultVisible: true
	},
	{ id: 'registration', label: 'Registration', align: 'left', defaultVisible: false },
	{ id: 'trans_group', label: 'Group', align: 'left', defaultVisible: false },
	{ id: 'procedure_name', label: 'Procedure', align: 'left', defaultVisible: false },
	{ id: 'landmark', label: 'Landmark', align: 'left', defaultVisible: false },
	{ id: 'metro', label: 'Nearest Metro', align: 'left', defaultVisible: false },
	{ id: 'mall', label: 'Nearest Mall', align: 'left', defaultVisible: false }
]

// Timeframe to days conversion
export const TIMEFRAME_MAPPING: Record<string, number> = {
	'Last Week': 7,
	'Last Month': 30,
	'Last 3 Months': 90,
	'Last 6 Months': 180,
	'Last Year': 365
}

// Pagination
export const DEFAULT_ITEMS_PER_PAGE = 30
export const MAX_VISIBLE_PAGES = 7
