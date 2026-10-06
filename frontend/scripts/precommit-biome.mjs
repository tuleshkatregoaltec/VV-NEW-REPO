import { spawnSync } from 'node:child_process'

const normalizedFiles = process.argv
	.slice(2)
	.filter((file) => file.startsWith('frontend/'))
	.map((file) => file.slice('frontend/'.length))
	.filter(Boolean)

if (normalizedFiles.length === 0) {
	process.exit(0)
}

const result = spawnSync('bun', ['run', 'biome:check', '--', ...normalizedFiles], {
	stdio: 'inherit'
})

if (result.error) {
	throw result.error
}

process.exit(result.status ?? 1)
