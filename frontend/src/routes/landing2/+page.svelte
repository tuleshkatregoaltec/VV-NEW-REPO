<script lang="ts">
import { onMount } from 'svelte'

onMount(() => {
	document.documentElement.classList.add('motion-ready')

	const revealEls = Array.from(document.querySelectorAll<HTMLElement>('[data-reveal]'))
	const revealObs = new IntersectionObserver(
		(entries) => {
			for (const e of entries) {
				if (e.isIntersecting) {
					e.target.classList.add('is-visible')
					revealObs.unobserve(e.target)
				}
			}
		},
		{ threshold: 0.05, rootMargin: '0px 0px -4% 0px' }
	)
	for (const el of revealEls) revealObs.observe(el)

	const countEls = Array.from(document.querySelectorAll<HTMLElement>('[data-count]'))
	const countObs = new IntersectionObserver(
		(entries) => {
			for (const e of entries) {
				if (e.isIntersecting) {
					animateCount(e.target as HTMLElement)
					countObs.unobserve(e.target)
				}
			}
		},
		{ threshold: 0.5 }
	)
	for (const el of countEls) countObs.observe(el)

	return () => {
		document.documentElement.classList.remove('motion-ready')
		revealObs.disconnect()
		countObs.disconnect()
	}
})

function animateCount(el: HTMLElement) {
	const target = Number(el.dataset.count)
	const final = el.dataset.final ?? String(target)
	const duration = 1800
	const start = performance.now()
	const tick = (now: number) => {
		const p = Math.min(1, (now - start) / duration)
		const eased = 1 - (1 - p) ** 3
		const v = Math.round(eased * target)
		if (target >= 1_000_000) el.textContent = `${Math.round(v / 1_000_000)}M+`
		else if (target >= 1_000) el.textContent = `${(v / 1_000).toFixed(0)},000+`
		else el.textContent = String(v)
		if (p < 1) requestAnimationFrame(tick)
		else el.textContent = final
	}
	requestAnimationFrame(tick)
}

const barHeights = [72, 80, 76, 85, 88, 79, 92, 100]
const barLabels = [
	'Bingh.',
	'Park R.',
	'JVC One',
	'Bloom',
	'Elara',
	'Genesis',
	'Plum T.',
	'Your Plot'
]

const marketRows = [
	{ sub: 'JVC', q4: '1,642', q1: '1,890', chg: '+15.1%' },
	{ sub: 'DIFC', q4: '3,240', q1: '3,580', chg: '+10.5%' },
	{ sub: 'Dubai Marina', q4: '2,450', q1: '2,710', chg: '+10.6%' },
	{ sub: 'Business Bay', q4: '1,820', q1: '2,040', chg: '+12.1%' },
	{ sub: 'Jumeirah', q4: '2,890', q1: '3,120', chg: '+8.0%' }
]
</script>

<svelte:head>
	<title>Vitevue — Dubai Real Estate Intelligence Platform</title>
	<meta name="description" content="Transaction analytics, feasibility studies, and market intelligence for Dubai real estate — backed by 10M+ live data points." />
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
	<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
</svelte:head>

<div class="theme-light page">

	<!-- ── NAVBAR ── -->
	<header class="navbar">
		<a href="/" class="logo" aria-label="Vitevue">
			<img src="/logos/vitevue-navbar-white.png" alt="Vitevue" />
		</a>
		<nav>
			<a href="/auth" class="nav-link">Sign in</a>
			<a href="/auth" class="cta-btn">Contact Sales</a>
		</nav>
	</header>

	<main>

		<!-- ── HERO ── -->
		<section class="hero">
			<div class="hero-bg" aria-hidden="true">
				<div class="hero-grid"></div>
				<div class="hero-glow"></div>
			</div>

			<div class="hero-content" data-reveal>
				<div class="badge">
					<span class="badge-dot" aria-hidden="true"></span>
					Dubai · Real Estate Intelligence
				</div>

				<h1>
					<span class="h1-light">The intelligence edge</span>
					<span class="h1-bold">for Dubai real estate.<span class="h1-cursor" aria-hidden="true"></span></span>
				</h1>

				<p class="hero-sub">
					Transaction analytics, feasibility studies, and market intelligence —<br />
					all backed by 10M+ live data points and powered by AI.
				</p>

				<div class="hero-actions">
					<a href="/auth" class="cta-btn large">Contact Sales</a>
					<a href="#preview" class="ghost-link">See the platform <span aria-hidden="true">↓</span></a>
				</div>

				<div class="hero-proof">
					<span class="mono proof-item"><span class="proof-num">10M+</span> transactions</span>
					<span class="proof-sep" aria-hidden="true">·</span>
					<span class="mono proof-item"><span class="proof-num">38</span> submarkets</span>
					<span class="proof-sep" aria-hidden="true">·</span>
					<span class="mono proof-item"><span class="proof-num">Real-time</span> data</span>
				</div>
			</div>

			<a href="#preview" class="scroll-hint" aria-label="Scroll to preview">
				<div class="scroll-track">
					<div class="scroll-thumb"></div>
				</div>
			</a>
		</section>

		<!-- ── PLATFORM PREVIEW (BENTO) ── -->
		<section class="preview" id="preview">
			<div class="preview-head" data-reveal>
				<p class="eyebrow">Platform</p>
				<h2>One platform.<br />Full picture.</h2>
				<p class="preview-sub">Three tools that turn raw market data into decisions.</p>
			</div>

			<div class="bento" data-reveal>

				<!-- Cell A: Feasibility Study -->
				<div class="bcell bcell-a">
					<div class="cell-top">
						<span class="live-dot"></span>
						<span class="mono cell-label">Feasibility Study</span>
						<span class="verdict mono">✓ Feasible</span>
					</div>
					<div class="feas-title">JVC Mixed-Use Development</div>
					<div class="feas-meta mono">Plot 456-789 · 50,000 sqft · 247 units · G+22</div>

					<div class="kpi-grid">
						<div class="kpi">
							<span class="kpi-l">GDV</span>
							<span class="kpi-v mono">AED 142.3M</span>
						</div>
						<div class="kpi">
							<span class="kpi-l">Dev Costs</span>
							<span class="kpi-v mono">AED 91.9M</span>
						</div>
						<div class="kpi kpi-hi">
							<span class="kpi-l">Net Profit</span>
							<span class="kpi-v mono teal">AED 50.4M</span>
						</div>
						<div class="kpi">
							<span class="kpi-l">IRR</span>
							<span class="kpi-v mono">18.2%</span>
						</div>
					</div>

					<div class="poc-row">
						<div class="poc-track"><div class="poc-fill"></div></div>
						<span class="mono muted" style="font-size:.62rem">Profit on cost: 21.4%</span>
					</div>

					<div class="feas-rows">
						<div class="frow"><span>Based on live comparables</span><strong class="mono">312 transactions</strong></div>
						<div class="frow"><span>Avg PSF (JVC residential)</span><strong class="mono">AED 1,890</strong></div>
						<div class="frow"><span>Study runtime</span><strong class="mono teal">2 min 14 sec</strong></div>
					</div>

					<div class="cell-tag">Agentic Feasibility Engine</div>
				</div>

				<!-- Cell B: PSF Bar Chart (top right) -->
				<div class="bcell bcell-b">
					<div class="cell-top">
						<span class="live-dot"></span>
						<span class="mono cell-label">Comparable PSF — JVC Residential Q1 2025</span>
					</div>
					<div class="bar-chart">
						{#each barHeights as h, i}
							<div class="bar-col" class:bar-hi={i === barHeights.length - 1}>
								<div class="bar-fill" style="height:{h}%"></div>
							</div>
						{/each}
					</div>
					<div class="bar-labels">
						{#each barLabels as l}<span>{l}</span>{/each}
					</div>
					<div class="bar-note mono">Avg PSF: AED 1,890 · Your plot at 98th percentile</div>
					<div class="cell-tag">Comparable Market Intelligence</div>
				</div>

				<!-- Cell C: Market Analytics Table (bottom right) -->
				<div class="bcell bcell-c">
					<div class="cell-top">
						<span class="live-dot indigo"></span>
						<span class="mono cell-label">Market Analytics — PSF by Submarket</span>
					</div>
					<div class="mkt-head mono">
						<span>Submarket</span><span>Q4 2024</span><span>Q1 2025</span><span>Δ</span>
					</div>
					{#each marketRows as row}
						<div class="mkt-row">
							<span class="mkt-sub">{row.sub}</span>
							<span class="mono muted">{row.q4}</span>
							<span class="mono">{row.q1}</span>
							<span class="mono chg">↑ {row.chg}</span>
						</div>
					{/each}
					<div class="cell-tag">Market Analytics</div>
				</div>

			</div>
		</section>

		<!-- ── NUMBERS ── -->
		<section class="numbers" data-reveal>
			<div class="num-row">
				<div class="num-item">
					<strong data-count="10000000" data-final="10M+">10M+</strong>
					<span>Market transactions indexed</span>
				</div>
				<div class="num-div" aria-hidden="true"></div>
				<div class="num-item">
					<strong data-count="3000" data-final="3,000+">3,000+</strong>
					<span>Reference projects</span>
				</div>
				<div class="num-div" aria-hidden="true"></div>
				<div class="num-item">
					<strong data-count="38" data-final="38">38</strong>
					<span>Submarkets tracked</span>
				</div>
				<div class="num-div" aria-hidden="true"></div>
				<div class="num-item">
					<strong class="num-rt">Real&#8209;time</strong>
					<span>Data updates</span>
				</div>
			</div>
		</section>

		<!-- ── WHO IT'S FOR ── -->
		<section class="for-section">
			<div class="for-head" data-reveal>
				<p class="eyebrow">Who It's For</p>
				<h2>Built for the teams<br />making the calls.</h2>
			</div>

			<div class="for-grid">
				<div class="for-card" data-reveal>
					<div class="for-n mono">01</div>
					<h3>Property Developers</h3>
					<p>Run feasibility studies on any plot in minutes. Model unit mixes, stress-test pricing, and generate IC-ready pro-formas — all backed by live market data.</p>
					<ul>
						<li>AI feasibility studies with traceable assumptions</li>
						<li>Live comparable data for GDV benchmarking</li>
						<li>Market trend analytics across 38 submarkets</li>
					</ul>
					<div class="for-accent" aria-hidden="true"></div>
				</div>

				<div class="for-card" data-reveal style="transition-delay:100ms">
					<div class="for-n mono">02</div>
					<h3>Investment Committees</h3>
					<p>Receive investment-grade reports backed by real market data — not consultant estimates. Every assumption is traceable, every number source-linked.</p>
					<ul>
						<li>Full audit trail from raw data to output</li>
						<li>Comparable benchmarking across all submarkets</li>
						<li>Formatted for board and LP presentation</li>
					</ul>
					<div class="for-accent" aria-hidden="true"></div>
				</div>
			</div>
		</section>

		<!-- ── WORKFLOW (horizontal) ── -->
		<section class="workflow">
			<div class="workflow-head" data-reveal>
				<p class="eyebrow">Workflow</p>
				<h2>From data to decisions.</h2>
			</div>

			<div class="steps">
				<div class="step" data-reveal>
					<div class="step-n mono">01</div>
					<h3>Explore the market</h3>
					<p>Browse 10M+ transactions. Filter by submarket, date, property type, and spec to find the signals that matter to your analysis.</p>
				</div>
				<div class="step-connector" aria-hidden="true">
					<div class="connector-line"></div>
					<svg width="8" height="12" viewBox="0 0 8 12" fill="none"><path d="M1 1l6 5-6 5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
				</div>
				<div class="step" data-reveal style="transition-delay:80ms">
					<div class="step-n mono">02</div>
					<h3>AI-powered analysis</h3>
					<p>Ask market questions or run full feasibility studies. The AI handles data retrieval, comparable matching, and financial modelling in minutes.</p>
				</div>
				<div class="step-connector" aria-hidden="true">
					<div class="connector-line"></div>
					<svg width="8" height="12" viewBox="0 0 8 12" fill="none"><path d="M1 1l6 5-6 5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
				</div>
				<div class="step" data-reveal style="transition-delay:160ms">
					<div class="step-n mono">03</div>
					<h3>Act on intelligence</h3>
					<p>Export reports, pro-formas, and comparable analyses — structured and source-linked, ready for IC submission or client presentation.</p>
				</div>
			</div>
		</section>

		<!-- ── CTA ── -->
		<section class="cta-section" data-reveal>
			<div class="cta-glow" aria-hidden="true"></div>
			<p class="eyebrow">Contact Sales</p>
			<h2>Better data.<br />Sharper decisions.</h2>
			<p class="cta-sub">Join the teams using Vitevue to move faster, win more sites, and back every decision with real market intelligence.</p>
			<a href="/auth" class="cta-btn large">Get in touch</a>
		</section>

	</main>

	<footer>
		&copy; {new Date().getFullYear()} Vitevue L.L.C-FZ. All rights reserved.
	</footer>

</div>

<style>
	/* ── Reset & globals ── */
	:global(body) { margin: 0; background: #070a12; }

	/* ── Design tokens ── */
	.page {
		--bg:        #07090f;
		--bg2:       #0c1120;
		--surface:   rgba(255,255,255,0.032);
		--border:    rgba(255,255,255,0.075);
		--border-hi: rgba(255,255,255,0.12);
		--text:      #e8edf5;
		--muted:     rgba(232,237,245,0.4);
		--teal:      #2cc9aa;
		--teal-dim:  rgba(44,201,170,0.07);
		--teal-glow: rgba(44,201,170,0.14);
		--teal-mid:  rgba(44,201,170,0.28);
		--indigo:    #818cf8;
		--indigo-dim:rgba(129,140,248,0.08);
		--ease:      cubic-bezier(0.16, 1, 0.3, 1);
		--r:         14px;

		position: relative;
		min-height: 100dvh;
		background: var(--bg);
		color: var(--text);
		font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
		overflow-x: clip;
	}

	.mono { font-family: 'JetBrains Mono', monospace; }
	.teal { color: var(--teal); }
	.muted { color: var(--muted); }

	/* ── Navbar ── */
	.navbar {
		position: sticky; top: 0; z-index: 50;
		display: flex; align-items: center; justify-content: space-between;
		padding: 0 clamp(1.5rem, 4vw, 4rem); height: 58px;
		background: rgba(7,10,18,0.85); backdrop-filter: blur(18px);
		border-bottom: 1px solid var(--border);
	}
	.logo { display: inline-flex; align-items: center; text-decoration: none; }
	.logo img { height: 1.5rem; width: auto; display: block; }
	nav { display: flex; align-items: center; gap: 1rem; }
	.nav-link {
		font-size: .875rem; color: var(--muted);
		text-decoration: none; transition: color .2s;
	}
	.nav-link:hover { color: var(--text); }

	/* ── CTA button ── */
	.cta-btn {
		display: inline-flex; align-items: center; gap: .4rem;
		padding: .5rem 1.1rem; border-radius: 8px;
		font-family: 'Plus Jakarta Sans', sans-serif;
		font-size: .875rem; font-weight: 700; letter-spacing: -.01em;
		text-decoration: none; border: none; cursor: pointer;
		background: var(--teal); color: #021a0e;
		transition: transform .2s var(--ease), box-shadow .2s var(--ease);
	}
	.cta-btn:hover { transform: translateY(-2px); box-shadow: 0 8px 28px var(--teal-glow); }
	.cta-btn.large { padding: .9rem 2.4rem; font-size: 1.05rem; border-radius: 10px; }

	.ghost-link {
		font-size: 1rem; font-weight: 500;
		color: var(--muted); text-decoration: none;
		transition: color .2s; display: inline-flex; align-items: center; gap: .3rem;
	}
	.ghost-link:hover { color: var(--text); }

	.eyebrow {
		font-family: 'Plus Jakarta Sans', sans-serif;
		font-size: .75rem; font-weight: 600;
		letter-spacing: .08em; text-transform: uppercase;
		color: rgba(44,201,170,.65); margin: 0 0 1rem;
	}

	/* ── HERO ── */
	.hero {
		position: relative;
		min-height: calc(100dvh - 58px);
		display: flex; flex-direction: column;
		align-items: center; justify-content: center;
		text-align: center;
		padding: clamp(3rem, 6vw, 6rem) clamp(1.5rem, 4vw, 4rem);
		overflow: hidden;
	}

	.hero-bg {
		position: absolute; inset: 0; pointer-events: none;
	}
	/* Subtle dot-grid pattern */
	.hero-grid {
		position: absolute; inset: 0;
		background-image: radial-gradient(rgba(255,255,255,0.045) 1px, transparent 1px);
		background-size: 40px 40px;
		mask-image: radial-gradient(ellipse 80% 70% at 50% 50%, black 20%, transparent 80%);
	}
	.hero-glow {
		position: absolute; top: 10%; left: 50%; transform: translateX(-50%);
		width: 70vw; height: 50vh;
		background: radial-gradient(ellipse, rgba(44,201,170,0.055) 0%, transparent 70%);
		pointer-events: none;
	}

	.hero-content { position: relative; z-index: 1; max-width: 900px; }

	/* Badge */
	.badge {
		display: inline-flex; align-items: center; gap: .5rem;
		font-family: 'Plus Jakarta Sans', sans-serif;
		font-size: .72rem; font-weight: 600;
		letter-spacing: .04em;
		color: rgba(44,201,170,.7);
		border: 1px solid rgba(44,201,170,.15);
		background: rgba(44,201,170,.04);
		padding: .32rem 1rem; border-radius: 999px;
		margin-bottom: 2.5rem;
	}
	.badge-dot {
		width: 5px; height: 5px; border-radius: 50%;
		background: var(--teal); flex-shrink: 0;
		animation: pulse 2.4s ease-in-out infinite;
	}
	@keyframes pulse {
		0%,100% { box-shadow: 0 0 0 2px rgba(52,211,153,.2); }
		50%      { box-shadow: 0 0 0 5px rgba(52,211,153,0); }
	}

	/* Hero headline — two-tier editorial style */
	h1 {
		margin: 0 0 1.8rem;
		display: flex; flex-direction: column; gap: .1em;
	}
	.h1-light {
		font-size: clamp(2.8rem, 6vw, 5.5rem);
		font-weight: 400; letter-spacing: -.03em; line-height: 1.1;
		color: rgba(232,237,245,0.55);
		font-style: italic;
	}
	.h1-bold {
		font-size: clamp(3.5rem, 7.5vw, 7rem);
		font-weight: 800; letter-spacing: -.045em; line-height: 1.05;
		color: var(--text);
	}
	.h1-cursor { display: none; }

	.hero-sub {
		font-size: clamp(1.05rem, 1.6vw, 1.2rem);
		line-height: 1.72; color: var(--muted);
		margin: 0 auto 2.5rem; max-width: 54ch;
	}

	.hero-actions {
		display: flex; align-items: center; gap: 1.5rem;
		justify-content: center; flex-wrap: wrap;
		margin-bottom: 3rem;
	}

	/* Small proof strip inside hero */
	.hero-proof {
		display: flex; align-items: center; gap: 1rem;
		justify-content: center; flex-wrap: wrap;
	}
	.proof-item {
		font-size: .72rem; color: var(--muted);
		letter-spacing: .04em;
	}
	.proof-num {
		color: rgba(232,237,245,.75); font-weight: 600;
	}
	.proof-sep { color: rgba(255,255,255,.15); }

	/* Scroll hint */
	.scroll-hint {
		position: absolute; bottom: 2rem; left: 50%; transform: translateX(-50%);
		display: flex; flex-direction: column; align-items: center; gap: .4rem;
		text-decoration: none; opacity: .35; transition: opacity .2s;
		z-index: 1;
	}
	.scroll-hint:hover { opacity: .7; }
	.scroll-track {
		width: 20px; height: 34px; border-radius: 999px;
		border: 1px solid rgba(255,255,255,.25);
		display: flex; justify-content: center; padding-top: 5px;
	}
	.scroll-thumb {
		width: 4px; height: 8px; border-radius: 999px;
		background: rgba(255,255,255,.5);
		animation: scrollDown 2s ease-in-out infinite;
	}
	@keyframes scrollDown {
		0%   { transform: translateY(0); opacity: 1; }
		80%  { transform: translateY(10px); opacity: 0; }
		81%  { transform: translateY(0); opacity: 0; }
		100% { opacity: 1; }
	}

	/* ── MAIN layout ── */
	main {
		position: relative; z-index: 1;
		width: min(1320px, calc(100% - clamp(1.5rem, 3.5vw, 5rem)));
		margin: 0 auto;
		display: grid; row-gap: clamp(5rem, 8vw, 9rem);
		padding-bottom: 6rem;
	}

	/* ── PREVIEW (bento) ── */
	.preview { display: grid; gap: 3rem; }

	.preview-head { max-width: 560px; }
	.preview-head h2 {
		font-size: clamp(2.2rem, 4vw, 3.4rem);
		font-weight: 800; letter-spacing: -.04em; line-height: 1.12;
		margin: 0 0 .75rem;
	}
	.preview-sub { font-size: 1.05rem; color: var(--muted); margin: 0; line-height: 1.6; }

	/* Bento grid: main (feasibility) left, chart + table stacked right */
	.bento {
		display: grid;
		grid-template-columns: 1.3fr 1fr;
		gap: .875rem;
	}
	/* Market table spans full width */
	.bcell-c { grid-column: 1 / -1; }

	.bcell {
		position: relative;
		border-radius: var(--r);
		border: 1px solid var(--border-hi);
		background: linear-gradient(160deg, rgba(11,17,29,.97) 0%, rgba(6,10,18,.99) 100%);
		padding: 1.4rem;
		overflow: hidden;
	}

	/* Top shine line */
	.bcell::before {
		content: ''; position: absolute;
		top: 0; left: 10%; right: 10%; height: 1px;
		background: linear-gradient(90deg, transparent, rgba(255,255,255,.08), transparent);
	}

	.cell-top {
		display: flex; align-items: center; gap: .5rem;
		margin-bottom: 1rem; position: relative; z-index: 1;
	}
	.cell-label {
		font-size: .72rem; font-weight: 500;
		color: var(--muted); letter-spacing: .02em; flex: 1;
	}

	.live-dot {
		width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
		background: var(--teal); box-shadow: 0 0 0 3px var(--teal-dim);
		animation: pulse 2.4s ease-in-out infinite;
	}
	.live-dot.indigo {
		background: var(--indigo);
		box-shadow: 0 0 0 3px var(--indigo-dim);
	}

	.verdict {
		font-size: .62rem; font-weight: 600; padding: .15rem .5rem;
		border-radius: 999px; background: rgba(52,211,153,.1);
		color: var(--teal); border: 1px solid rgba(52,211,153,.2);
	}

	/* Feasibility cell content */
	.feas-title {
		font-size: 1.05rem; font-weight: 700; letter-spacing: -.025em;
		color: var(--text); margin-bottom: .22rem; position: relative; z-index: 1;
	}
	.feas-meta { font-size: .62rem; color: var(--muted); margin-bottom: 1rem; position: relative; z-index: 1; }

	.kpi-grid {
		display: grid; grid-template-columns: 1fr 1fr;
		gap: .55rem; margin-bottom: .9rem; position: relative; z-index: 1;
	}
	.kpi {
		border-radius: 10px; border: 1px solid var(--border);
		background: rgba(255,255,255,.022); padding: .65rem .8rem;
		display: flex; flex-direction: column; gap: .15rem;
	}
	.kpi-hi { border-color: rgba(52,211,153,.16); background: rgba(52,211,153,.04); }
	.kpi-l { font-size: .63rem; color: var(--muted); }
	.kpi-v { font-size: 1.05rem; font-weight: 500; color: var(--text); letter-spacing: -.03em; }

	.poc-row {
		display: flex; align-items: center; gap: .75rem;
		margin-bottom: .9rem; position: relative; z-index: 1;
	}
	.poc-track { flex: 1; height: 3px; border-radius: 999px; background: rgba(255,255,255,.07); overflow: hidden; }
	.poc-fill {
		height: 100%; width: 0; border-radius: 999px;
		background: linear-gradient(90deg, var(--teal), rgba(44,201,170,.3));
		animation: fillBar 2.4s var(--ease) .6s forwards;
	}
	@keyframes fillBar { to { width: 78%; } }

	.feas-rows { display: grid; position: relative; z-index: 1; }
	.frow {
		display: flex; justify-content: space-between; align-items: center;
		padding: .4rem 0; font-size: .78rem; color: var(--muted);
		border-bottom: 1px solid rgba(255,255,255,.04);
	}
	.frow:last-child { border-bottom: none; }
	.frow strong { font-weight: 500; color: var(--text); }

	.cell-tag {
		margin-top: 1rem; font-family: 'Plus Jakarta Sans', sans-serif;
		font-size: .72rem; font-weight: 500; letter-spacing: .01em;
		color: rgba(232,237,245,.22); position: relative; z-index: 1;
	}

	/* PSF Bar chart cell */
	.bcell-b { display: flex; flex-direction: column; }
	.bar-chart {
		height: 160px; display: flex; align-items: flex-end; gap: 4px;
		padding: .75rem 0 .4rem;
	}
	.bar-col { flex: 1; height: 100%; display: flex; flex-direction: column; justify-content: flex-end; }
	.bar-fill {
		border-radius: 3px 3px 0 0;
		background: linear-gradient(180deg, rgba(44,201,170,.55), rgba(44,201,170,.18));
	}
	.bar-hi .bar-fill {
		background: linear-gradient(180deg, var(--teal), rgba(44,201,170,.3));
		box-shadow: 0 0 8px rgba(44,201,170,.15);
	}
	.bar-labels {
		display: flex; gap: 4px; padding-top: .3rem;
		border-top: 1px solid var(--border);
	}
	.bar-labels span {
		flex: 1; text-align: center;
		font-family: 'JetBrains Mono', monospace;
		font-size: .42rem; color: var(--muted);
		overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
	}
	.bar-note {
		font-size: .62rem; color: var(--teal); opacity: .75;
		padding-top: .5rem; text-align: center;
	}

	/* Market table cell */
	.bcell-c { display: flex; flex-direction: column; }
	.mkt-head {
		display: grid; grid-template-columns: 2fr 1fr 1fr 1fr;
		gap: 1rem; padding: .45rem 1rem;
		font-size: .58rem; letter-spacing: .08em; text-transform: uppercase;
		color: var(--muted); background: rgba(255,255,255,.02);
		border-bottom: 1px solid var(--border);
		border-radius: 6px 6px 0 0;
	}
	.mkt-row {
		display: grid; grid-template-columns: 2fr 1fr 1fr 1fr;
		gap: 1rem; padding: .6rem 1rem;
		border-bottom: 1px solid rgba(255,255,255,.04);
		font-size: .85rem; align-items: center;
	}
	.mkt-row:last-child { border-bottom: none; }
	.mkt-sub { font-weight: 600; font-size: .8rem; }
	.chg { color: var(--teal); font-size: .72rem; }

	/* ── NUMBERS ── */
	.numbers {
		border-top: 1px solid var(--border);
		border-bottom: 1px solid var(--border);
		padding: clamp(3rem, 5vw, 5rem) 0;
	}
	.num-row {
		display: flex; align-items: center;
		justify-content: space-between; gap: 0;
		flex-wrap: wrap;
	}
	.num-item {
		flex: 1; min-width: 180px;
		display: flex; flex-direction: column;
		align-items: center; gap: .6rem;
		padding: 1rem 1.5rem; text-align: center;
	}
	.num-item strong {
		font-size: clamp(2.8rem, 5vw, 5rem);
		font-weight: 800; letter-spacing: -.055em;
		color: var(--text); line-height: 1;
		font-variant-numeric: tabular-nums;
	}
	.num-rt { color: var(--text) !important; }
	.num-item span {
		font-size: .875rem; color: var(--muted);
		line-height: 1.4; max-width: 16ch; text-align: center;
	}
	.num-div { width: 1px; height: 3.5rem; background: var(--border); flex-shrink: 0; }

	/* ── WHO IT'S FOR ── */
	.for-section { display: grid; gap: 3rem; }
	.for-head h2 {
		font-size: clamp(2.2rem, 4vw, 3.4rem);
		font-weight: 800; letter-spacing: -.04em; line-height: 1.12;
		margin: 0;
	}
	.for-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
	.for-card {
		position: relative; overflow: hidden;
		border-radius: 18px; border: 1px solid var(--border-hi);
		background: linear-gradient(160deg, rgba(11,17,29,.97), rgba(6,10,18,.99));
		padding: 2.5rem;
	}
	.for-card::before {
		content: ''; position: absolute;
		top: 0; left: 12%; right: 12%; height: 1px;
		background: linear-gradient(90deg, transparent, rgba(52,211,153,.25), transparent);
	}
	/* Subtle teal glow in corner */
	.for-accent {
		position: absolute; top: -60px; right: -60px;
		width: 200px; height: 200px; border-radius: 50%;
		background: radial-gradient(circle, rgba(52,211,153,.07), transparent 70%);
		pointer-events: none;
	}
	.for-n {
		font-size: 3.5rem; font-weight: 500; letter-spacing: -.04em;
		color: rgba(255,255,255,.07); line-height: 1;
		margin-bottom: 1.2rem;
	}
	.for-card h3 {
		font-size: clamp(1.35rem, 2vw, 1.7rem); font-weight: 700;
		letter-spacing: -.03em; margin: 0 0 .9rem; position: relative; z-index: 1;
	}
	.for-card p {
		font-size: 1rem; line-height: 1.72; color: var(--muted);
		margin: 0 0 1.5rem; position: relative; z-index: 1;
	}
	.for-card ul {
		margin: 0; padding: 0; list-style: none;
		display: grid; gap: .5rem; position: relative; z-index: 1;
	}
	.for-card li {
		font-size: .94rem; color: rgba(232,237,245,.5);
		padding-left: 1.1rem; position: relative; line-height: 1.5;
	}
	.for-card li::before {
		content: ''; position: absolute; left: 0; top: .55rem;
		width: .35rem; height: .35rem; border-radius: 50%;
		background: var(--teal); opacity: .5;
	}

	/* ── WORKFLOW ── */
	.workflow { display: grid; gap: 3rem; }
	.workflow-head h2 {
		font-size: clamp(2.2rem, 4vw, 3.2rem);
		font-weight: 800; letter-spacing: -.04em; margin: 0;
	}

	.steps {
		display: grid;
		grid-template-columns: 1fr auto 1fr auto 1fr;
		gap: 0; align-items: start;
	}
	.step {
		padding: 2rem; border-radius: var(--r);
		border: 1px solid var(--border);
		background: var(--surface);
	}
	.step-n {
		font-size: 2.2rem; font-weight: 500; letter-spacing: -.04em;
		color: rgba(255,255,255,.1); line-height: 1; margin-bottom: .9rem;
	}
	.step h3 {
		font-size: 1.15rem; font-weight: 700; letter-spacing: -.025em;
		margin: 0 0 .65rem;
	}
	.step p { margin: 0; font-size: .94rem; line-height: 1.68; color: var(--muted); }

	.step-connector {
		display: flex; align-items: center; gap: .5rem;
		padding: 0 .75rem; padding-top: 2.5rem; color: rgba(255,255,255,.15);
	}
	.connector-line { flex: 1; height: 1px; background: var(--border); }

	/* ── CTA ── */
	.cta-section {
		position: relative; text-align: center;
		padding: clamp(4rem, 7vw, 7rem) 2rem;
		border-radius: 20px; border: 1px solid rgba(52,211,153,.15);
		background: linear-gradient(160deg, rgba(9,20,30,.98), rgba(5,10,16,.99));
		overflow: hidden;
	}
	.cta-section::before {
		content: ''; position: absolute;
		top: 0; left: 15%; right: 15%; height: 1px;
		background: linear-gradient(90deg, transparent, rgba(52,211,153,.55), transparent);
	}
	.cta-glow {
		position: absolute !important; top: -30%; left: 50%; transform: translateX(-50%);
		width: 60%; height: 60%;
		background: radial-gradient(ellipse, rgba(52,211,153,.1), transparent 70%);
		pointer-events: none; z-index: 0 !important;
	}
	.cta-section > *:not(.cta-glow) { position: relative; z-index: 1; }
	.cta-section h2 {
		font-size: clamp(2.4rem, 5vw, 4rem);
		font-weight: 800; letter-spacing: -.045em; line-height: 1.1;
		margin: 0 0 1.1rem;
	}
	.cta-sub {
		font-size: 1.1rem; color: var(--muted); line-height: 1.68;
		max-width: 48ch; margin: 0 auto 2.5rem;
	}

	/* ── Footer ── */
	footer {
		position: relative; z-index: 1;
		text-align: center; padding: 1.5rem 1rem 2.5rem;
		font-size: .75rem; color: rgba(232,237,245,.18);
		font-family: 'JetBrains Mono', monospace; letter-spacing: .04em;
	}

	/* ── Scroll reveal ── */
	:global([data-reveal]) {
		transition: opacity 700ms var(--ease), transform 700ms var(--ease);
		will-change: transform, opacity;
	}
	:global(html.motion-ready [data-reveal]:not(.is-visible)) {
		opacity: 0; transform: translateY(24px);
	}
	:global(html.motion-ready [data-reveal].is-visible) {
		opacity: 1; transform: none;
	}

	/* ── Responsive ── */
	@media (max-width: 1020px) {
		.bento { grid-template-columns: 1fr; }
		.bcell-c { grid-column: auto; }
		.for-grid { grid-template-columns: 1fr; }
		.steps { grid-template-columns: 1fr; gap: 1rem; }
		.step-connector { display: none; }
		.num-row { justify-content: center; }
		.num-div { display: none; }
		.num-item { min-width: 140px; flex: 0 0 45%; }
	}
	@media (max-width: 640px) {
		.hero { text-align: left; align-items: flex-start; }
		.badge, .hero-actions, .hero-proof { justify-content: flex-start; }
		.hero-sub { text-align: left; }
		.cta-section { padding: 3rem 1.25rem; }
		.for-card { padding: 1.75rem; }
		.num-item { flex: 0 0 100%; }
		.num-div { display: none; }
	}
	@media (prefers-reduced-motion: reduce) {
		.badge-dot, .live-dot, .h1-cursor, .scroll-thumb, .poc-fill { animation: none; }
		:global([data-reveal]) { transition: opacity 300ms ease; }
		:global(html.motion-ready [data-reveal]:not(.is-visible)) { transform: none; }
	}
</style>
