import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const scanAll = process.argv.includes('--all')

const strictEntries = [
	'src/lib/components/layout',
	'src/lib/components/navigation',
	'src/lib/components/dropdowns',
	'src/lib/components/filters',
	'src/lib/components/transactions/DataPanel.svelte',
	'src/lib/components/dashboard/DashboardCard.svelte',
	'src/lib/components/dashboard/CompactChatInput.svelte',
	'src/lib/components/dashboard/FullWidthMarketChart.svelte',
	'src/lib/components/feasibility/NewStudySetup.svelte',
	'src/lib/components/feasibility/LoadingState.svelte',
	'src/lib/components/feasibility/Workspace.svelte',
	'src/lib/components/feasibility/ChatPanel.svelte',
	'src/routes/dashboard/+page.svelte',
	'src/routes/analytics/+page.svelte',
	'src/routes/transactions',
	'src/routes/feasibility',
	'src/routes/profile/+page.svelte'
]

const skippedFragments = [
	'/src/lib/components/feasibility/sheets/',
	'/src/lib/components/feasibility/WorkbookPanel.svelte',
	'/src/lib/components/landing/',
	'/src/routes/landing-new/',
	'/src/routes/landing2/'
]

const checks = [
	{
		name: 'raw CSS variable utility',
		pattern: /\b(?:[\w-]+:)*(?:text|bg|border|divide|accent|placeholder)-\[var\(/g
	},
	{
		name: 'raw focus rgba ring',
		pattern: /\bfocus:ring-\[rgba\(11,27,43,0\.12\)\]/g
	},
	{
		name: 'raw slate/blue/white palette utility',
		pattern:
			/\b(?:bg-white(?:\/\d+)?|bg-slate-\d{2,3}(?:\/\d+)?|text-slate-\d{2,3}(?:\/\d+)?|border-slate-\d{2,3}(?:\/\d+)?|bg-blue-\d{2,3}(?:\/\d+)?|text-blue-\d{2,3}(?:\/\d+)?)\b/g
	},
	{
		name: 'large radius utility',
		pattern: /\brounded-(?:xl|2xl|3xl)\b/g
	},
	{
		name: 'large shadow utility',
		pattern: /\bshadow-(?:xl|2xl)\b/g
	},
	{
		name: 'gradient background utility',
		pattern: /\bbg-gradient(?:-[\w/]+)?\b/g
	}
]

function shouldSkip(filePath) {
	const normalized = filePath.split(path.sep).join('/')
	return skippedFragments.some((fragment) => normalized.includes(fragment))
}

function collectFiles(entry) {
	if (!existsSync(entry) || shouldSkip(entry)) return []
	const stats = statSync(entry)
	if (stats.isFile()) return /\.(svelte|ts|js|css)$/.test(entry) ? [entry] : []
	return readdirSync(entry).flatMap((name) => collectFiles(path.join(entry, name)))
}

const roots = scanAll ? ['src'] : strictEntries
const files = roots.flatMap((entry) => collectFiles(path.join(root, entry)))
const findings = []

for (const file of files) {
	const relative = path.relative(root, file)
	const lines = readFileSync(file, 'utf8').split('\n')

	lines.forEach((line, index) => {
		for (const check of checks) {
			check.pattern.lastIndex = 0
			if (check.pattern.test(line)) {
				findings.push({ file: relative, line: index + 1, check: check.name, text: line.trim() })
			}
		}
	})
}

if (findings.length > 0) {
	console.error(`Style audit found ${findings.length} issue(s):`)
	for (const finding of findings) {
		console.error(`${finding.file}:${finding.line} ${finding.check}`)
		console.error(`  ${finding.text}`)
	}
	process.exit(1)
}

console.log(`Style audit passed for ${scanAll ? 'all non-exempt frontend files' : 'strict app UI surfaces'}.`)
