<script lang="ts">
import { ArrowRight, Building2, Database, ShieldCheck, Sparkles, Workflow } from 'lucide-svelte'
import { onMount } from 'svelte'
import Footer from '$lib/components/layout/Footer.svelte'

type AudienceCard = {
	title: string
	description: string
	pill: string
	icon: typeof Building2
}

type Capability = {
	title: string
	description: string
	icon: typeof Database
}

type PreviewFeature = {
	tag: string
	title: string
	description: string
	bullets: string[]
	image: string
	imageAlt: string
}

const audienceCards: AudienceCard[] = [
	{
		title: 'Institutional Investors',
		description:
			'Deploy capital with greater clarity using transparent assumptions, comparable intelligence, and outputs your committee can challenge.',
		pill: 'Strategic market intelligence',
		icon: Building2
	},
	{
		title: 'Developers & Advisory Teams',
		description:
			'Track supply, pressure-test positioning, benchmark against live comps, and prepare sharper materials for internal and client-facing decisions.',
		pill: 'Research and positioning workflows',
		icon: Workflow
	}
]

const capabilities: Capability[] = [
	{
		title: 'Verified Data Layer',
		description:
			'Consolidate fragmented market records into one normalized intelligence layer your team can trust across investment, research, and reporting.',
		icon: Database
	},
	{
		title: 'Governed Intelligence',
		description:
			'Every generated output is tied to explicit assumptions, making reviews faster and internal review standards easier to enforce under pressure.',
		icon: ShieldCheck
	},
	{
		title: 'Execution Velocity',
		description:
			'Move from raw market noise to actionable investment narratives in hours, not weeks, while keeping discipline and quality controls intact.',
		icon: Workflow
	}
]

const previewFeatures: PreviewFeature[] = [
	{
		tag: 'AI Copilot',
		title: 'Query the market in plain language.',
		description:
			'Move from retrieval to interpretation quickly with guided responses grounded in platform context.',
		bullets: [
			'Narrative answers linked to measurable market signals',
			'Faster first-pass diligence on new targets',
			'Consistent framing across investment, development, and advisory teams'
		],
		image: '/images/chat.png',
		imageAlt: 'Vitevue chat interface'
	},
	{
		tag: 'Comparables & Analytics',
		title: 'Build evidence packs with institutional clarity.',
		description:
			'Compare projects, benchmark performance, and prepare outputs suited for partner, IC, and client-facing discussions.',
		bullets: [
			'Structured KPI comparisons across selected comps',
			'Scenario-ready charts for internal debate',
			'Clear outputs that travel across stakeholders'
		],
		image: '/images/analytics.png',
		imageAlt: 'Vitevue analytics interface'
	},
	{
		tag: 'Supply & Transactions',
		title: 'Operate with a live market radar.',
		description:
			'Monitor transaction flow and inventory pressure with a visual layer that helps teams respond earlier and size conviction better.',
		bullets: [
			'Coverage across transactions, projects, and submarkets',
			'Filters tuned for investment and development workflows',
			'One view for signal discovery and market communication'
		],
		image: '/images/transactions.png',
		imageAlt: 'Vitevue transactions interface'
	}
]

onMount(() => {
	document.documentElement.classList.add('motion-ready')
	const elements = Array.from(document.querySelectorAll<HTMLElement>('[data-reveal]'))
	const observer = new IntersectionObserver(
		(entries) => {
			for (const entry of entries) {
				entry.target.classList.toggle('is-visible', entry.isIntersecting)
			}
		},
		{ threshold: 0.18, rootMargin: '0px 0px -8% 0px' }
	)

	for (const element of elements) observer.observe(element)

	return () => {
		document.documentElement.classList.remove('motion-ready')
		observer.disconnect()
	}
})
</script>

<svelte:head>
	<title>Vitevue | Institutional-Grade Real Estate Intelligence</title>
	<meta
		name="description"
		content="Vitevue helps investors, developers, and advisory teams move from market data to conviction with comparables, analytics, transactions, and AI-assisted research."
	/>
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
	<link
		href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Space+Grotesk:wght@500;600;700&display=swap"
		rel="stylesheet"
	/>
</svelte:head>

<div class="theme-light landing-new">
	<div class="aurora" aria-hidden="true"></div>
	<header class="site-header">
		<a class="brand" href="/" aria-label="Vitevue home">
			<img src="/logos/vitevue-navbar-white.png" alt="Vitevue" />
		</a>
		<nav>
			<a href="/auth">Sign In</a>
			<a class="btn ghost" href="/auth">Request Access</a>
		</nav>
	</header>

	<main>
		<section class="hero is-visible" data-reveal data-variant="fade-up">
			<div class="hero-grid">
				<div class="hero-copy-block">
					<p class="eyebrow">Real Estate Intelligence Platform</p>
					<h1 class="is-visible" data-reveal data-variant="fly-right">
						Built for teams that deploy capital with precision.
					</h1>
					<p class="hero-copy">
						Vitevue gives investors and developers a sharper operating edge: pressure-test
						assumptions, focus on real signals, and move from research to conviction with
						discipline.
					</p>
					<div class="hero-actions">
						<a class="btn solid" href="/auth">
							Book a Platform Walkthrough
							<ArrowRight size={18} />
						</a>
						<a class="btn ghost" href="#platform-overview">See Platform Overview</a>
					</div>
					<div class="metrics">
						<div>
							<p>Market Coverage</p>
							<strong>10M+ Transactions</strong>
						</div>
						<div>
							<p>Tracked Inventory</p>
							<strong>3000+ Projects</strong>
						</div>
						<div>
							<p>Update Cadence</p>
							<strong>Live Market Signals</strong>
						</div>
					</div>
				</div>
				<div class="hero-side is-visible" data-reveal data-variant="fly-left" aria-hidden="true">
					<div class="hero-side-panel">
						<p class="side-kicker">Superior market intelligence</p>
						<h2>Operate with an edge.</h2>
						<div class="side-line"></div>
						<ul>
							<li>Shorter research cycles</li>
							<li>Sharper evidence packs</li>
							<li>Faster decisions under pressure</li>
						</ul>
						<div class="hero-side-tags">
							<span>Live radar</span>
							<span>Targeted comps</span>
							<span>Clear positioning</span>
						</div>
					</div>
				</div>
			</div>
			<div class="trust-strip">
				<span>Built for investment, advisory, and development workflows.</span>
				<div>
					<strong>Transactions</strong>
					<strong>Comparables</strong>
					<strong>Supply tracking</strong>
				</div>
			</div>
		</section>

		<section class="audiences">
			{#each audienceCards as card, i (card.title)}
				<article
					class="audience-card"
					data-reveal
					data-variant={i === 0 ? 'soft-right' : 'soft-scale'}
					style={`transition-delay: ${i * 80}ms`}
				>
					<div class="card-top">
						<svelte:component this={card.icon} size={20} />
						<span>{card.pill}</span>
					</div>
					<h2>{card.title}</h2>
					<p>{card.description}</p>
				</article>
			{/each}
		</section>

		<section class="capabilities">
			<div class="section-head" data-reveal data-variant="fade-up">
				<p class="eyebrow">Core Platform</p>
				<h2>Institutional clarity, built for decisive teams.</h2>
			</div>
			<div class="capability-grid">
				{#each capabilities as capability, i (capability.title)}
					<article
						class="capability"
						data-reveal
						data-variant={i === 1 ? 'soft-scale' : i === 0 ? 'soft-right' : 'soft-left'}
						style={`transition-delay: ${i * 90}ms`}
					>
						<svelte:component this={capability.icon} size={20} />
						<h3>{capability.title}</h3>
						<p>{capability.description}</p>
					</article>
				{/each}
			</div>
		</section>

		<section class="preview" id="platform-overview">
			<div class="section-head" data-reveal data-variant="fade-up">
				<p class="eyebrow">Platform Overview</p>
				<h2>A product surface built for speed, scrutiny, and positioning.</h2>
			</div>
			<div class="preview-stack">
				{#each previewFeatures as feature, i (feature.title)}
					<article
						class="preview-row"
						class:reverse={i % 2 === 1}
						data-reveal
						data-variant={i === 0 ? 'soft-right' : i === 1 ? 'soft-scale' : 'soft-left'}
					>
						<div class="preview-copy">
							<p class="feature-tag">{feature.tag}</p>
							<h3>{feature.title}</h3>
							<p class="feature-desc">{feature.description}</p>
							<ul>
								{#each feature.bullets as bullet (bullet)}
									<li>{bullet}</li>
								{/each}
							</ul>
						</div>
						<div class="preview-media">
							<div class="media-shell">
								<img src={feature.image} alt={feature.imageAlt} loading="lazy" />
								<div class="media-badge media-badge-a">Signal locked</div>
								<div class="media-badge media-badge-b">Live intel</div>
							</div>
						</div>
					</article>
				{/each}
			</div>
		</section>

		<section class="process">
			<div class="section-head" data-reveal data-variant="fade-up">
				<p class="eyebrow">How Teams Operate</p>
				<h2>One continuous workflow from target discovery to investment memo.</h2>
			</div>
			<ol>
				<li data-reveal data-variant="soft-right">
					<Sparkles size={17} />
					<div>
						<h3>Capture live market context</h3>
						<p>
							Ingest transaction, supply, and project-level signals into a coherent research
							baseline.
						</p>
					</div>
				</li>
				<li data-reveal data-variant="fade-up" style="transition-delay: 80ms">
					<Database size={17} />
					<div>
						<h3>Pressure-test the position</h3>
						<p>
							Stress-test assumptions using structured inputs and traceable outputs across teams.
						</p>
					</div>
				</li>
				<li data-reveal data-variant="soft-left" style="transition-delay: 140ms">
					<ShieldCheck size={17} />
					<div>
						<h3>Advance with confidence</h3>
						<p>
							Deliver recommendation packs aligned with institutional review and governance
							standards.
						</p>
					</div>
				</li>
			</ol>
		</section>

		<section class="closing" data-reveal data-variant="fade-up">
			<h2>Deploy sharper market conviction.</h2>
			<p>
				Whether you are allocating institutional capital or building developer strategy, Vitevue
				gives your team the signal edge to move first and communicate clearly.
			</p>
			<a class="btn solid" href="/auth">Get Early Access</a>
		</section>
	</main>

	<Footer />
</div>

<style>
	:global(body) {
		background: #050d1f;
	}

	.landing-new {
		--bg: #050d1f;
		--bg-soft: #0f1f3d;
		--line: rgba(146, 176, 235, 0.24);
		--card: rgba(14, 30, 61, 0.72);
		--text: #e8f0ff;
		--muted: #a8bddc;
		--accent: #4ad6c8;
		--accent-warm: #f9ba67;
		position: relative;
		min-height: 100vh;
		overflow: hidden;
		background:
			radial-gradient(circle at 82% 18%, rgba(74, 214, 200, 0.2), transparent 44%),
			radial-gradient(circle at 6% 28%, rgba(249, 186, 103, 0.14), transparent 38%),
			linear-gradient(170deg, #051029 0%, #081431 45%, #071126 100%);
		color: var(--text);
		font-family: 'IBM Plex Sans', sans-serif;
	}

	.aurora {
		position: absolute;
		inset: -20% -10% auto;
		height: 38rem;
		background: radial-gradient(circle, rgba(67, 124, 255, 0.2) 0%, rgba(7, 17, 38, 0) 65%);
		filter: blur(24px);
		pointer-events: none;
	}

	.site-header {
		position: sticky;
		top: 0;
		z-index: 10;
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.95rem 1.5rem;
		backdrop-filter: blur(12px);
		background: rgba(7, 17, 38, 0.56);
		border-bottom: 1px solid rgba(173, 199, 244, 0.14);
	}

	.brand {
		display: inline-flex;
		align-items: center;
		text-decoration: none;
	}

	.brand img {
		display: block;
		height: 1.65rem;
		width: auto;
	}

	nav {
		display: flex;
		align-items: center;
		gap: 0.7rem;
	}

	nav > a {
		text-decoration: none;
		color: var(--muted);
		font-size: 0.92rem;
	}

	main {
		width: min(1120px, calc(100% - 2.5rem));
		margin: 0 auto;
		padding: 2.2rem 0 4.5rem;
		display: grid;
		gap: 3.4rem;
	}

	.hero-grid {
		display: grid;
		grid-template-columns: minmax(0, 1.08fr) minmax(280px, 0.72fr);
		gap: 1.3rem;
		align-items: center;
	}

	.hero-copy-block {
		position: relative;
		z-index: 1;
	}

	.hero h1,
	.section-head h2,
	.closing h2,
	.audience-card h2,
	.process h3,
	.capability h3 {
		font-family: 'Space Grotesk', sans-serif;
	}

	.hero h1 {
		margin: 0.5rem 0 1rem;
		font-size: clamp(2.1rem, 6.2vw, 4.2rem);
		line-height: 1.06;
		letter-spacing: -0.03em;
		max-width: 12ch;
	}

	.hero-copy {
		margin: 0;
		max-width: 64ch;
		color: var(--muted);
		font-size: clamp(1rem, 2.4vw, 1.15rem);
		line-height: 1.65;
	}

	.eyebrow {
		margin: 0;
		text-transform: uppercase;
		letter-spacing: 0.16em;
		font-size: 0.73rem;
		font-weight: 600;
		color: #93f2e8;
	}

	.hero-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		margin-top: 1.6rem;
	}

	.hero-side {
		position: relative;
		min-height: 100%;
	}

	.hero-side-panel {
		position: relative;
		padding: 0.95rem 1rem;
		border-radius: 1.25rem;
		border: 1px solid rgba(150, 181, 232, 0.16);
		background:
			linear-gradient(180deg, rgba(12, 27, 55, 0.82), rgba(8, 18, 39, 0.78)),
			radial-gradient(circle at 90% 10%, rgba(74, 214, 200, 0.08), transparent 28%);
		box-shadow: 0 10px 24px rgba(4, 10, 24, 0.16);
		overflow: hidden;
	}

	.hero-side-panel::before {
		content: '';
		position: absolute;
		inset: 0;
		background:
			linear-gradient(rgba(128, 171, 244, 0.08) 1px, transparent 1px),
			linear-gradient(90deg, rgba(128, 171, 244, 0.08) 1px, transparent 1px);
		background-size: 2.6rem 2.6rem;
		opacity: 0.28;
		mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.16), rgba(0, 0, 0, 0.84));
	}

	.side-kicker,
	.hero-side-panel h2,
	.hero-side-panel ul,
	.hero-side-tags {
		position: relative;
		z-index: 1;
	}

	.side-kicker {
		margin: 0;
		font-size: 0.68rem;
		text-transform: uppercase;
		letter-spacing: 0.14em;
		color: #8fbeb9;
	}

	.hero-side-panel h2 {
		margin: 0.55rem 0 0;
		font-family: 'Space Grotesk', sans-serif;
		font-size: clamp(1.32rem, 2.4vw, 1.72rem);
		line-height: 1.12;
		max-width: 9ch;
	}

	.side-line {
		position: relative;
		z-index: 1;
		margin: 1rem 0 1rem;
		height: 1px;
		width: 100%;
		background: linear-gradient(90deg, rgba(74, 214, 200, 0.7), rgba(124, 168, 255, 0));
	}

	.hero-side-panel ul {
		margin: 0;
		padding: 0;
		list-style: none;
		display: grid;
		gap: 0.65rem;
	}

	.hero-side-panel li {
		padding-left: 1rem;
		position: relative;
		color: #c8daf5;
		font-size: 0.84rem;
		line-height: 1.45;
	}

	.hero-side-panel li::before {
		content: '';
		position: absolute;
		left: 0;
		top: 0.48rem;
		width: 0.42rem;
		height: 0.42rem;
		border-radius: 999px;
		background: linear-gradient(180deg, #4ad6c8, #7ca8ff);
	}

	.hero-side-tags {
		margin-top: 1.1rem;
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.hero-side-tags span {
		padding: 0.28rem 0.48rem;
		border-radius: 999px;
		border: 1px solid rgba(150, 181, 232, 0.16);
		color: #b8cef3;
		font-size: 0.66rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}

	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.45rem;
		border-radius: 999px;
		padding: 0.72rem 1.1rem;
		font-size: 0.92rem;
		font-weight: 600;
		text-decoration: none;
		transition:
			transform 0.22s ease,
			box-shadow 0.22s ease,
			border-color 0.22s ease;
	}

	.btn:hover {
		transform: translateY(-1px);
	}

	.btn.solid {
		background: linear-gradient(130deg, var(--accent) 0%, #75a4ff 100%);
		color: #04152e;
		box-shadow: 0 8px 24px rgba(117, 164, 255, 0.32);
	}

	.btn.ghost {
		border: 1px solid var(--line);
		color: var(--text);
		background: rgba(16, 33, 66, 0.45);
	}

	.metrics {
		margin-top: 1.8rem;
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 0.8rem;
	}

	.metrics div {
		border: 1px solid var(--line);
		background: linear-gradient(145deg, rgba(13, 30, 60, 0.86), rgba(9, 21, 43, 0.86));
		border-radius: 1rem;
		padding: 0.9rem 1rem;
	}

	.metrics p {
		margin: 0;
		font-size: 0.8rem;
		color: var(--muted);
	}

	.metrics strong {
		display: block;
		margin-top: 0.25rem;
		font-size: 1.04rem;
	}

	.trust-strip {
		margin-top: 1rem;
		padding: 0.78rem 1rem;
		border-radius: 0.9rem;
		border: 1px solid rgba(146, 176, 235, 0.18);
		background: rgba(7, 20, 42, 0.42);
		display: flex;
		flex-wrap: wrap;
		gap: 0.7rem 1.4rem;
		align-items: center;
		justify-content: space-between;
	}

	.trust-strip span {
		color: #c7d8f3;
		font-size: 0.86rem;
	}

	.trust-strip div {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.trust-strip strong {
		font-size: 0.74rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		padding: 0.3rem 0.48rem;
		border-radius: 999px;
		border: 1px solid rgba(145, 171, 219, 0.2);
		color: #aecdff;
		font-weight: 600;
	}

	.audiences {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 1rem;
	}

	.audience-card {
		border: 1px solid var(--line);
		background: linear-gradient(160deg, rgba(15, 32, 64, 0.76), rgba(9, 22, 47, 0.76));
		border-radius: 1.2rem;
		padding: 1.25rem;
	}

	.card-top {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		color: #b6c8e7;
		font-size: 0.8rem;
	}

	.audience-card h2 {
		margin: 0.7rem 0 0.45rem;
		font-size: 1.44rem;
	}

	.audience-card p {
		margin: 0;
		color: var(--muted);
		line-height: 1.62;
	}

	.section-head h2 {
		margin: 0.45rem 0 0;
		font-size: clamp(1.6rem, 4.8vw, 2.5rem);
		line-height: 1.2;
		max-width: 18ch;
	}

	.preview-stack {
		display: grid;
		gap: 1.1rem;
		margin-top: 0.9rem;
	}

	.preview-row {
		display: grid;
		grid-template-columns: 1fr 1.15fr;
		align-items: center;
		gap: 1rem;
		padding: 1rem;
		border-radius: 1.1rem;
		border: 1px solid var(--line);
		background: rgba(10, 24, 49, 0.62);
		transition:
			transform 180ms ease,
			border-color 180ms ease,
			background 180ms ease;
	}

	.preview-row:hover {
		transform: translateY(-1px);
		border-color: rgba(131, 174, 247, 0.36);
		background: rgba(10, 24, 49, 0.7);
	}

	.preview-row.reverse {
		grid-template-columns: 1.15fr 1fr;
	}

	.preview-row.reverse .preview-copy {
		order: 2;
	}

	.preview-row.reverse .preview-media {
		order: 1;
	}

	.feature-tag {
		margin: 0;
		display: inline-flex;
		padding: 0.26rem 0.5rem;
		border-radius: 999px;
		font-size: 0.74rem;
		border: 1px solid rgba(146, 176, 235, 0.26);
		color: #afc4ec;
	}

	.preview-copy h3 {
		margin: 0.68rem 0 0.45rem;
		font-family: 'Space Grotesk', sans-serif;
		font-size: clamp(1.26rem, 3.4vw, 1.78rem);
		line-height: 1.22;
	}

	.feature-desc {
		margin: 0;
		color: var(--muted);
		line-height: 1.58;
	}

	.preview-copy ul {
		margin: 0.82rem 0 0;
		padding: 0;
		list-style: none;
		display: grid;
		gap: 0.42rem;
	}

	.preview-copy li {
		color: #c5d8f7;
		font-size: 0.93rem;
		line-height: 1.45;
		padding-left: 1rem;
		position: relative;
	}

	.preview-copy li::before {
		content: '';
		position: absolute;
		left: 0;
		top: 0.5rem;
		width: 0.42rem;
		height: 0.42rem;
		border-radius: 999px;
		background: linear-gradient(180deg, #4ad6c8, #7ca8ff);
	}

	.preview-media .media-shell {
		position: relative;
		border-radius: 0.95rem;
		border: 1px solid rgba(176, 201, 246, 0.28);
		padding: 0.45rem;
		background: linear-gradient(160deg, rgba(11, 25, 48, 0.86), rgba(7, 16, 35, 0.92));
		box-shadow: 0 18px 36px rgba(3, 8, 21, 0.36);
	}

	.preview-media img {
		display: block;
		width: 100%;
		height: auto;
		border-radius: 0.65rem;
	}

	.media-badge {
		position: absolute;
		z-index: 1;
		padding: 0.32rem 0.52rem;
		border-radius: 999px;
		border: 1px solid rgba(176, 201, 246, 0.28);
		background: rgba(7, 18, 39, 0.82);
		backdrop-filter: blur(10px);
		font-size: 0.68rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: #d3e5ff;
		opacity: 0;
		transform: translateY(10px);
		transition:
			opacity 420ms ease,
			transform 420ms ease;
	}

	.media-badge-a {
		top: 0.9rem;
		right: 1rem;
		transition-delay: 90ms;
	}

	.media-badge-b {
		left: 1rem;
		bottom: 0.95rem;
		transition-delay: 150ms;
	}

	.capabilities {
		position: relative;
		padding: 1.2rem;
		border-radius: 1.35rem;
		background:
			linear-gradient(180deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0)),
			radial-gradient(circle at 12% 10%, rgba(249, 186, 103, 0.08), transparent 30%);
		border: 1px solid rgba(165, 187, 227, 0.1);
	}

	.capability-grid {
		margin-top: 1rem;
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 0.8rem;
	}

	.capability {
		border: 1px solid rgba(168, 191, 230, 0.18);
		background: linear-gradient(160deg, rgba(12, 27, 54, 0.64), rgba(9, 20, 42, 0.64));
		border-radius: 1rem;
		padding: 1.1rem;
	}

	.capability h3 {
		margin: 0.7rem 0 0.45rem;
		font-size: 1.1rem;
	}

	.capability p {
		margin: 0;
		color: var(--muted);
		line-height: 1.58;
	}

	.process ol {
		margin: 1rem 0 0;
		padding: 0;
		display: grid;
		gap: 0.72rem;
	}

	.process {
		position: relative;
		padding: 1.25rem;
		border-radius: 1.35rem;
		background: linear-gradient(180deg, rgba(10, 24, 49, 0.52), rgba(7, 17, 36, 0.36));
		border: 1px solid rgba(165, 187, 227, 0.1);
	}

	.process li {
		display: grid;
		grid-template-columns: auto 1fr;
		gap: 0.8rem;
		align-items: start;
		list-style: none;
		padding: 0.95rem 1rem;
		border: 1px solid var(--line);
		border-radius: 0.95rem;
		background: rgba(11, 24, 48, 0.66);
	}

	.process h3 {
		margin: 0;
		font-size: 1.03rem;
	}

	.process p {
		margin: 0.25rem 0 0;
		color: var(--muted);
		line-height: 1.56;
	}

	.closing {
		border: 1px solid rgba(176, 201, 246, 0.3);
		background:
			linear-gradient(140deg, rgba(10, 24, 50, 0.88), rgba(9, 26, 47, 0.78)),
			radial-gradient(circle at 90% 20%, rgba(74, 214, 200, 0.14), transparent 44%);
		border-radius: 1.2rem;
		padding: 1.6rem;
	}

	.closing h2 {
		margin: 0;
		font-size: clamp(1.5rem, 4vw, 2.2rem);
	}

	.closing p {
		margin: 0.7rem 0 1.2rem;
		color: var(--muted);
		max-width: 62ch;
		line-height: 1.62;
	}

	[data-reveal] {
		opacity: 1;
		transition:
			opacity 560ms cubic-bezier(0.2, 0.7, 0.2, 1),
			transform 560ms cubic-bezier(0.2, 0.7, 0.2, 1),
			filter 560ms cubic-bezier(0.2, 0.7, 0.2, 1);
		will-change: transform, opacity;
	}

	:global(html.motion-ready) [data-reveal]:not(.is-visible) {
		opacity: 0;
	}

	:global(html.motion-ready) [data-variant='fade-up']:not(.is-visible) {
		transform: translateY(18px);
		filter: blur(5px);
	}

	:global(html.motion-ready) [data-variant='fly-right']:not(.is-visible) {
		transform: translateX(-22px) translateY(8px);
		filter: blur(5px);
	}

	:global(html.motion-ready) [data-variant='fly-left']:not(.is-visible) {
		transform: translateX(22px) translateY(8px);
		filter: blur(5px);
	}

	:global(html.motion-ready) [data-variant='soft-right']:not(.is-visible) {
		transform: translateX(-12px) translateY(6px);
		filter: blur(3px);
	}

	:global(html.motion-ready) [data-variant='soft-left']:not(.is-visible) {
		transform: translateX(12px) translateY(6px);
		filter: blur(3px);
	}

	:global(html.motion-ready) [data-variant='soft-scale']:not(.is-visible) {
		transform: scale(0.985) translateY(10px);
		filter: blur(3px);
	}

	[data-reveal].is-visible {
		opacity: 1;
		transform: translateX(0) translateY(0);
		filter: blur(0);
	}

	@media (max-width: 900px) {
		.hero-grid,
		.metrics,
		.audiences,
		.capability-grid,
		.preview-row,
		.preview-row.reverse {
			grid-template-columns: 1fr;
		}

		.preview-row.reverse .preview-copy,
		.preview-row.reverse .preview-media {
			order: initial;
		}

		.site-header {
			padding: 0.85rem 1rem;
		}

		.brand img {
			height: 1.35rem;
		}

		main {
			width: min(1120px, calc(100% - 1.4rem));
			padding-top: 1.4rem;
			gap: 2.7rem;
		}

		.hero h1 {
			max-width: 10ch;
		}

		nav {
			gap: 0.38rem;
		}

		nav > a {
			font-size: 0.8rem;
		}

		.btn {
			padding: 0.58rem 0.82rem;
			font-size: 0.82rem;
		}
	}
</style>
