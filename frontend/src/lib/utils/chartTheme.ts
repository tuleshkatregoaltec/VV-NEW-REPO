export interface ChartTheme {
	line: string
	lineAlt: string
	lineTertiary: string
	fill: string
	softFill: string
	grid: string
	axis: string
	muted: string
	foreground: string
	foregroundMuted: string
	tooltipBackground: string
	tooltipText: string
	warning: string
	success: string
	error: string
	panel: string
}

function readCssVar(name: string, fallback: string): string {
	if (typeof window === 'undefined') return fallback
	const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
	return value || fallback
}

export function getChartTheme(): ChartTheme {
	return {
		line: readCssVar('--color-chart-line', '#0b1b2b'),
		lineAlt: readCssVar('--color-chart-line-alt', '#3a8fad'),
		lineTertiary: readCssVar('--color-chart-line-tertiary', '#a55a13'),
		fill: readCssVar('--color-chart-fill', 'rgba(11, 27, 43, 0.1)'),
		softFill: readCssVar('--color-chart-soft-fill', 'rgba(42, 70, 96, 0.18)'),
		grid: readCssVar('--color-chart-grid', '#e2e8f0'),
		axis: readCssVar('--color-chart-axis', '#cbd5e1'),
		muted: readCssVar('--color-chart-muted', '#94a3b8'),
		foreground: readCssVar('--color-fg-1', '#0a1422'),
		foregroundMuted: readCssVar('--color-fg-3', '#475569'),
		tooltipBackground: readCssVar('--color-bg-inverse', '#0b1b2b'),
		tooltipText: readCssVar('--color-bg-card', '#ffffff'),
		warning: readCssVar('--color-warning', '#a55a13'),
		success: readCssVar('--color-success', '#117a48'),
		error: readCssVar('--color-error', '#a32424'),
		panel: readCssVar('--color-bg-panel', '#f1f5f9')
	}
}
