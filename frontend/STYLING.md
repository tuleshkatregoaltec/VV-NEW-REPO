# Frontend Styling

App UI should use semantic Tailwind utilities backed by `src/app.css` tokens. Prefer `bg-app`, `bg-panel`, `bg-card`, `bg-elevated`, `text-fg-1` through `text-fg-5`, `text-on-navy`, `text-on-navy-muted`, `border-border`, `border-strong`, `border-focus`, `ring-focus`, and status tokens such as `text-error` and `bg-error-bg`.

Use `.ui-*` primitives for repeated controls and surfaces:

- `.ui-button` with `data-variant="primary|secondary|ghost|danger"` and optional `data-size="sm|md|icon"`.
- `.ui-surface`, `.ui-panel`, `.ui-menu`, and `.ui-page-header` for app chrome.
- `.ui-table-row` with `data-selected="true"` for selected rows.
- `.ui-field` for inputs, textareas, and selects.

Avoid raw palette utilities such as `bg-white`, `bg-slate-*`, `text-slate-*`, `border-slate-*`, `bg-blue-*`, and `text-blue-*` in app UI. Avoid arbitrary CSS-variable utility classes when a semantic token exists. Keep radii at `rounded-lg` or below for normal app surfaces, and avoid large shadows and gradients in app chrome.

Allowed exceptions:

- `.theme-light` workbook sheets can keep spreadsheet-like white/slate styling.
- Landing and prototype routes can keep page-scoped styling while they are outside app chrome.
- Data visualizations can use chart/map/mark tokens and SVG custom properties.

To add a token, define the light value, dark override, and any `.theme-light` override in `src/app.css`, then expose it in the `@theme inline` block with a semantic utility name. Tokens should describe role, not raw color.

Run `bun run style:audit` before merging styling changes. Use `bun run style:audit -- --all` to inspect the broader legacy backlog.
