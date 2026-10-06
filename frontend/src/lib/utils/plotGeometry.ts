export interface LngLatPoint {
	lng: number
	lat: number
}

export interface SvgPoint {
	x: number
	y: number
}

export interface LngLatBounds {
	minLng: number
	maxLng: number
	minLat: number
	maxLat: number
}

export interface SvgBounds {
	minX: number
	maxX: number
	minY: number
	maxY: number
	w: number
	h: number
}

export function clamp(value: number, min: number, max: number) {
	return Math.min(Math.max(value, min), max)
}

export function parseCoordinatePair(pair: number[]): LngLatPoint | null {
	if (pair.length < 2) return null
	const [a, b] = pair
	if (!Number.isFinite(a) || !Number.isFinite(b)) return null
	if (Math.abs(a) > 35 && Math.abs(b) <= 35) return { lng: a, lat: b }
	if (Math.abs(b) > 35 && Math.abs(a) <= 35) return { lng: b, lat: a }
	return { lng: a, lat: b }
}

export function normalizeCoordinates(
	coordinates: Array<Array<number>> | null | undefined
): LngLatPoint[] {
	if (!Array.isArray(coordinates)) return []
	return coordinates.map(parseCoordinatePair).filter((point) => point !== null)
}

export function coordinateBounds(points: LngLatPoint[]): LngLatBounds | null {
	if (points.length === 0) return null
	const lngs = points.map((point) => point.lng)
	const lats = points.map((point) => point.lat)
	return {
		minLng: Math.min(...lngs),
		maxLng: Math.max(...lngs),
		minLat: Math.min(...lats),
		maxLat: Math.max(...lats)
	}
}

export function coordinateSetBounds(coordinateSets: LngLatPoint[][]): LngLatBounds | null {
	const bounds = coordinateSets.map(coordinateBounds).filter((candidate) => candidate !== null)
	if (bounds.length === 0) return null
	return {
		minLng: Math.min(...bounds.map((item) => item.minLng)),
		maxLng: Math.max(...bounds.map((item) => item.maxLng)),
		minLat: Math.min(...bounds.map((item) => item.minLat)),
		maxLat: Math.max(...bounds.map((item) => item.maxLat))
	}
}

export function createCoordinateProjector(
	coordinateSets: LngLatPoint[][],
	width: number,
	height: number,
	pad: number
) {
	const bounds = coordinateSetBounds(coordinateSets)
	if (!bounds) return null
	const lngRange = bounds.maxLng - bounds.minLng || 1
	const latRange = bounds.maxLat - bounds.minLat || 1
	const drawableWidth = Math.max(width - pad * 2, 1)
	const drawableHeight = Math.max(height - pad * 2, 1)
	const scale = Math.min(drawableWidth / lngRange, drawableHeight / latRange)
	const drawnW = lngRange * scale
	const drawnH = latRange * scale
	const offsetX = (width - drawnW) / 2
	const offsetY = (height - drawnH) / 2

	return (point: LngLatPoint): SvgPoint => ({
		x: offsetX + (point.lng - bounds.minLng) * scale,
		y: offsetY + (bounds.maxLat - point.lat) * scale
	})
}

export function pointsToAttribute(points: SvgPoint[]) {
	return points.map((point) => `${point.x},${point.y}`).join(' ')
}

export function polygonArea(points: SvgPoint[]): number {
	if (points.length < 3) return 0
	let area = 0
	for (let i = 0; i < points.length; i++) {
		const current = points[i]
		const next = points[(i + 1) % points.length]
		area += current.x * next.y - next.x * current.y
	}
	return Math.abs(area) / 2
}

export function pointBounds(points: SvgPoint[]): SvgBounds {
	const xs = points.map((point) => point.x)
	const ys = points.map((point) => point.y)
	const minX = Math.min(...xs)
	const maxX = Math.max(...xs)
	const minY = Math.min(...ys)
	const maxY = Math.max(...ys)
	return { minX, maxX, minY, maxY, w: maxX - minX, h: maxY - minY }
}

export function boundsDistance(a: LngLatBounds, b: LngLatBounds) {
	const lngGap = Math.max(0, a.minLng - b.maxLng, b.minLng - a.maxLng)
	const latGap = Math.max(0, a.minLat - b.maxLat, b.minLat - a.maxLat)
	return Math.hypot(lngGap, latGap)
}

export function boundsCenterDistance(a: LngLatBounds, b: LngLatBounds) {
	const aLng = (a.minLng + a.maxLng) / 2
	const aLat = (a.minLat + a.maxLat) / 2
	const bLng = (b.minLng + b.maxLng) / 2
	const bLat = (b.minLat + b.maxLat) / 2
	return Math.hypot(aLng - bLng, aLat - bLat)
}
