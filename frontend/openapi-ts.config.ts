import { defineConfig } from '@hey-api/openapi-ts'

export default defineConfig({
	input: './openapi.json',
	output: './src/lib/api/generated/hey-api',
	plugins: ['@hey-api/typescript']
})
