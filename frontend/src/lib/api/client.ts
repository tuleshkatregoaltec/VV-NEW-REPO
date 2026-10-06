import { browser } from '$app/environment'
import { env } from '$env/dynamic/public'

import { get_access_token } from './auth'

interface ErrorDetail {
	code: string
	message: string
}

export class ApiError extends Error {
	constructor(
		message: string,
		public status: number,
		public code?: string,
		public details?: unknown
	) {
		super(message)
		this.name = 'ApiError'
	}
}

export interface RequestOptions {
	method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
	body?: unknown
	headers?: Record<string, string>
	returnBlob?: boolean
	signal?: AbortSignal
}

interface StreamOptions {
	method?: 'GET' | 'POST'
	body?: unknown
}

type QueryValue = string | number | boolean | null | undefined | Date
type QueryParams = Record<string, QueryValue | QueryValue[]>

async function request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
	const { method = 'GET', body, headers = {}, returnBlob = false, signal } = options

	// if access token available, add auth header.
	const access_token = await get_access_token()
	if (access_token) {
		headers.Authorization = `Bearer ${access_token}`
	}

	const config: RequestInit = {
		method,
		credentials: 'include',
		signal,
		headers: {
			...headers
		}
	}

	if (body !== undefined) {
		if (typeof FormData !== 'undefined' && body instanceof FormData) {
			config.body = body
		} else {
			config.headers = {
				'Content-Type': 'application/json',
				...config.headers
			}
			config.body = JSON.stringify(body)
		}
	}

	let res: Response
	try {
		res = await fetch(`${env.PUBLIC_API_BASE_URL}${endpoint}`, config)
	} catch (err) {
		if (err instanceof Error && err.name === 'AbortError') throw err
		throw new ApiError(
			'Could not reach the API server. Check that the backend is running and try again.',
			0,
			'network_error',
			err
		)
	}

	if (!res.ok) {
		// 401 = expired/invalid JWT — clear session and redirect to auth
		if (browser && res.status === 401) {
			const { clearUser } = await import('$lib/stores/user.svelte')
			clearUser()
			const next = `${window.location.pathname}${window.location.search}`
			window.location.href = `/auth?next=${encodeURIComponent(next)}`
			throw new ApiError('Session expired', 401)
		}

		let details: unknown
		let message = res.statusText
		let errorCode: string | undefined

		try {
			const data = await res.json()
			details = data

			// Check for structured error response
			if (data.detail && typeof data.detail === 'object' && 'code' in data.detail) {
				const errorDetail = data.detail as ErrorDetail
				errorCode = errorDetail.code
				message = errorDetail.message
			} else if (Array.isArray(data.detail)) {
				message = data.detail.map((e: { msg: string }) => e.msg).join(', ')
			} else if (typeof data.detail === 'string') {
				message = data.detail
			} else if (data.message) {
				message = data.message
			}
		} catch {
			// Response wasn't JSON, use statusText
		}

		throw new ApiError(message, res.status, errorCode, details)
	}

	if (res.status === 204) {
		return undefined as T
	}

	if (returnBlob) {
		return res.blob() as Promise<T>
	}

	return res.json()
}

export type StreamCallback = (chunk: string) => void

/**
 * Stream SSE responses using fetch with ReadableStream.
 * Supports POST requests with request bodies.
 */
async function stream(endpoint: string, onChunk: StreamCallback, options: StreamOptions = {}) {
	const { method = 'GET', body } = options

	const abortController = new AbortController()
	let terminalEventSeen = false

	// if access token available, add auth header.
	const access_token = await get_access_token()
	const headers: Record<string, string> = {}
	if (access_token) {
		headers.Authorization = `Bearer ${access_token}`
	}

	const config: RequestInit = {
		method,
		credentials: 'include',
		signal: abortController.signal,
		headers: {
			...headers
		}
	}

	if (body !== undefined) {
		config.headers = {
			'Content-Type': 'application/json',
			...config.headers
		}
		config.body = JSON.stringify(body)
	}

	// Start streaming
	fetch(`${env.PUBLIC_API_BASE_URL}${endpoint}`, config)
		.then(async (response) => {
			if (!response.ok) {
				if (response.status === 429) {
					// Token limit exceeded
					const errorData = await response.text().catch(() => 'Daily token limit exceeded')
					throw new Error(`TOKEN_LIMIT_EXCEEDED: ${errorData}`)
				}
				throw new Error(`HTTP ${response.status}: ${response.statusText}`)
			}

			const reader = response.body?.pipeThrough(new TextDecoderStream()).getReader()
			if (!reader) {
				throw new Error('Response body is not readable')
			}

			let buffer = ''

			while (true) {
				const { value, done } = await reader.read()
				if (done) break

				// Add new data to buffer
				buffer += value

				// Process complete SSE messages (separated by \n\n)
				const messages = buffer.split('\n\n')

				// Keep the last incomplete message in buffer
				buffer = messages.pop() || ''

				// Process complete messages
				for (const message of messages) {
					if (!message.trim()) continue

					// Extract data from SSE format (data: {...})
					const lines = message.split('\n')
					for (const line of lines) {
						if (line.startsWith('data: ')) {
							const data = line.slice(6) // Remove 'data: ' prefix

							// Check if stream is complete
							try {
								const parsed = JSON.parse(data)
								if (parsed.type === 'done' || parsed.type === 'error') {
									terminalEventSeen = true
								}
							} catch {
								// Not JSON, ignore
							}

							onChunk(data)
						}
					}
				}
			}

			if (buffer.trim()) {
				const lines = buffer.split('\n')
				for (const line of lines) {
					if (line.startsWith('data: ')) {
						const data = line.slice(6)
						try {
							const parsed = JSON.parse(data)
							if (parsed.type === 'done' || parsed.type === 'error') {
								terminalEventSeen = true
							}
						} catch {
							// Not JSON, ignore
						}
						onChunk(data)
					}
				}
			}

			if (!terminalEventSeen) {
				onChunk(JSON.stringify({ type: 'done' }))
			}
		})
		.catch((error) => {
			if (error.name === 'AbortError') {
				return // Stream was intentionally closed
			}

			console.error('Stream error:', error)

			// Only send error if stream wasn't completed normally
			if (!terminalEventSeen) {
				if (error.message.startsWith('TOKEN_LIMIT_EXCEEDED:')) {
					onChunk(
						JSON.stringify({ type: 'error', error: 'token_limit_exceeded', details: error.message })
					)
				} else {
					onChunk(JSON.stringify({ type: 'error', error: 'Stream connection failed' }))
				}
			}
		})

	return {
		close: () => {
			abortController.abort()
		}
	}
}

function toQueryValue(value: QueryValue): string | null {
	if (value === undefined || value === null || value === '') return null
	if (value instanceof Date) return value.toISOString()
	return String(value)
}

function withQuery(endpoint: string, params: QueryParams): string {
	const query = new URLSearchParams()

	for (const [key, rawValue] of Object.entries(params)) {
		if (Array.isArray(rawValue)) {
			for (const item of rawValue) {
				const value = toQueryValue(item)
				if (value !== null) query.append(key, value)
			}
			continue
		}

		const value = toQueryValue(rawValue)
		if (value !== null) query.append(key, value)
	}

	const search = query.toString()
	return search ? `${endpoint}?${search}` : endpoint
}

export const client = {
	request,
	get<T>(endpoint: string, options: Omit<RequestOptions, 'method' | 'body'> = {}) {
		return request<T>(endpoint, options)
	},
	post<TResponse, TBody = unknown>(
		endpoint: string,
		body?: TBody,
		options: Omit<RequestOptions, 'method' | 'body'> = {}
	) {
		return request<TResponse>(endpoint, { ...options, method: 'POST', body })
	},
	put<TResponse, TBody = unknown>(
		endpoint: string,
		body?: TBody,
		options: Omit<RequestOptions, 'method' | 'body'> = {}
	) {
		return request<TResponse>(endpoint, { ...options, method: 'PUT', body })
	},
	patch<TResponse, TBody = unknown>(
		endpoint: string,
		body?: TBody,
		options: Omit<RequestOptions, 'method' | 'body'> = {}
	) {
		return request<TResponse>(endpoint, { ...options, method: 'PATCH', body })
	},
	delete<T>(endpoint: string, options: Omit<RequestOptions, 'method' | 'body'> = {}) {
		return request<T>(endpoint, { ...options, method: 'DELETE' })
	},
	stream,
	withQuery
}
