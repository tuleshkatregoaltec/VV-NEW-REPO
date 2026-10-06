<script lang="ts">
let {
	value,
	oncommit,
	class: cls = '',
	placeholder = ''
}: {
	value: number
	oncommit: (v: number) => void
	class?: string
	placeholder?: string
} = $props()

let focused = $state(false)

function display(n: number): string {
	if (!n && n !== 0) return ''
	return Math.round(n).toLocaleString('en-AE')
}

function handleFocus(e: FocusEvent) {
	focused = true
	const el = e.currentTarget as HTMLInputElement
	el.value = value ? String(Math.round(value)) : ''
	el.select()
}

function handleBlur(e: FocusEvent) {
	focused = false
	const raw = (e.currentTarget as HTMLInputElement).value.replace(/,/g, '').trim()
	const v = Number(raw)
	oncommit(Number.isFinite(v) ? v : 0)
}
</script>

<input
	type="text"
	inputmode="numeric"
	class={cls}
	{placeholder}
	value={focused ? undefined : display(value)}
	onfocus={handleFocus}
	onblur={handleBlur}
/>
