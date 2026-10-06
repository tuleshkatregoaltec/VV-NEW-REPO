<script lang="ts">
	import { onMount } from 'svelte';
	import { ArrowDownRight, Mail } from 'lucide-svelte';

	const accessHref = 'mailto:contact@vitevue.com?subject=Vitevue%20access';
	const contactHref =
		"mailto:contact@vitevue.com?subject=Vitevue%20access&body=Tell%20us%20about%20your%20team%20and%20what%20you're%20working%20on.";

	let root: HTMLElement;
	let isNavScrolled = $state(false);

	function scrollToPageSection(event: MouseEvent) {
		const link = event.currentTarget as HTMLAnchorElement;
		const sectionId = link.hash ? decodeURIComponent(link.hash.slice(1)) : '';
		const target = sectionId ? document.getElementById(sectionId) : null;
		if (!target) return;

		event.preventDefault();
		const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
		target.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
	}

	const personas = [
		{
			number: '/ 01',
			title: 'Brokers',
			accent: '& agents',
			body: 'Verify pricing with ease, generate leads, automate listing descriptions and stand out to clients with commercial-grade analysis.'
		},
		{
			number: '/ 02',
			title: 'Developers',
			body: 'Pressure-test projects against live supply, pricing dynamics and configuration opportunities well before the feasibility study lands.'
		},
		{
			number: '/ 03',
			title: 'Investors',
			accent: '& advisory',
			body: 'Build evidence packs, run sub-market screens and ship client-ready narratives without rebuilding the comp set every time.'
		}
	];

	onMount(() => {
		if (!root) return;

		const cleanups: Array<() => void> = [];
		const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
		const motion = 1;

		function addWindowListener(
			event: 'scroll' | 'resize' | 'load',
			handler: EventListener,
			options?: AddEventListenerOptions
		) {
			window.addEventListener(event, handler, options);
			cleanups.push(() => window.removeEventListener(event, handler));
		}

		function fireCount(el: HTMLElement) {
			if (!el.dataset.count || el.dataset.counted === 'true') return;

			el.dataset.counted = 'true';
			const target = Number.parseFloat(el.dataset.count);
			const decimals = Number.parseInt(el.dataset.countDecimals || '0', 10);
			const suffix = el.dataset.countSuffix || '';
			const prefix = el.dataset.countPrefix || '';
			const duration = reduced ? 0 : 1100;
			const start = performance.now();

			function format(value: number) {
				return (
					prefix +
					value.toLocaleString('en-US', {
						minimumFractionDigits: decimals,
						maximumFractionDigits: decimals
					}) +
					suffix
				);
			}

			if (duration === 0) {
				el.textContent = format(target);
				return;
			}

			function tick(now: number) {
				const progress = Math.min(1, (now - start) / duration);
				const eased = 1 - Math.pow(1 - progress, 3);
				el.textContent = format(target * eased);

				if (progress < 1) {
					requestAnimationFrame(tick);
				} else {
					el.textContent = format(target);
				}
			}

			requestAnimationFrame(tick);
		}

		function initReveals() {
			const elements = Array.from(root.querySelectorAll<HTMLElement>('[data-reveal]'));

			root.querySelectorAll<HTMLElement>('[data-reveal-group]').forEach((group) => {
				const step = Number.parseInt(group.dataset.revealStep || '90', 10);
				Array.from(group.children).forEach((child, index) => {
					const element = child as HTMLElement;
					if (!element.dataset.reveal) element.dataset.reveal = 'up';
					if (!element.dataset.revealDelay) element.dataset.revealDelay = String(index * step);
					if (!elements.includes(element)) elements.push(element);
				});
			});

			elements.forEach((element) => {
				const delay = Number.parseInt(element.dataset.revealDelay || '0', 10);
				element.style.transitionDelay = `${delay * motion}ms`;
				element.classList.add('rv');
			});

			if (reduced) {
				elements.forEach((element) => {
					element.classList.add('rv-in');
					fireCount(element);
				});
				return;
			}

			function check() {
				const viewportHeight = window.innerHeight;

				elements.forEach((element) => {
					const rect = element.getBoundingClientRect();
					const inView = rect.top < viewportHeight * 0.9 && rect.bottom > viewportHeight * 0.04;

					if (inView) {
						element.classList.add('rv-in');
					} else if (element.dataset.revealRepeat !== undefined && rect.top >= viewportHeight) {
						element.classList.remove('rv-in');
					}
				});
			}

			let ticking = false;
			const onScroll = () => {
				if (ticking) return;
				ticking = true;
				requestAnimationFrame(() => {
					check();
					ticking = false;
				});
			};

			addWindowListener('scroll', onScroll, { passive: true });
			addWindowListener('resize', check);
			addWindowListener('load', check);
			check();
			setTimeout(check, 400);
		}

		function initCounts() {
			const nodes = Array.from(root.querySelectorAll<HTMLElement>('[data-count]'));
			if (!nodes.length) return;

			if (reduced) {
				nodes.forEach(fireCount);
				return;
			}

			function check() {
				const viewportHeight = window.innerHeight;

				nodes.forEach((node) => {
					const rect = node.getBoundingClientRect();
					const inView = rect.top < viewportHeight * 0.98 && rect.bottom > 0;

					if (inView) {
						fireCount(node);
					} else if (rect.top >= viewportHeight && node.dataset.revealRepeat !== undefined) {
						delete node.dataset.counted;
						node.textContent = '0';
					}
				});
			}

			let ticking = false;
			const onScroll = () => {
				if (ticking) return;
				ticking = true;
				requestAnimationFrame(() => {
					check();
					ticking = false;
				});
			};

			addWindowListener('scroll', onScroll, { passive: true });
			addWindowListener('resize', check);
			check();
		}

		function initParallax() {
			if (reduced) return;

			const nodes = Array.from(root.querySelectorAll<HTMLElement>('[data-parallax]'));
			if (!nodes.length) return;

			function update() {
				const viewportHeight = window.innerHeight;

				nodes.forEach((node) => {
					const rect = node.getBoundingClientRect();
					const center = rect.top + rect.height / 2;
					const offset = (center - viewportHeight / 2) / viewportHeight;
					const factor = Number.parseFloat(node.dataset.parallax || '0.1');
					node.style.transform = `translate3d(0,${(-offset * factor * 100 * motion).toFixed(2)}px,0)`;
				});
			}

			let ticking = false;
			const onScroll = () => {
				if (ticking) return;
				ticking = true;
				requestAnimationFrame(() => {
					update();
					ticking = false;
				});
			};

			addWindowListener('scroll', onScroll, { passive: true });
			update();
		}

		function initNav() {
			function onScroll() {
				isNavScrolled = window.scrollY > 12;
			}

			addWindowListener('scroll', onScroll, { passive: true });
			onScroll();
		}

		initReveals();
		initCounts();
		initParallax();
		initNav();

		return () => {
			cleanups.forEach((cleanup) => cleanup());
		};
	});
</script>

{#snippet BrandLogo(variant: 'dark' | 'light' = 'dark')}
	<span
		class={`inline-flex items-center gap-2.5 ${variant === 'light' ? 'text-bone-50' : 'text-navy-950'}`}
	>
		<img
			class="h-[25px] w-auto shrink-0"
			src={variant === 'light'
				? '/landing/logos/vitevue-mark-bone.svg'
				: '/landing/logos/vitevue-mark-navy.svg'}
			alt=""
			aria-hidden="true"
		/>
		<span class="font-display text-[30px] leading-none font-normal tracking-normal">Vitevue</span>
	</span>
{/snippet}

<div
	bind:this={root}
	class="landing-motion min-h-screen overflow-x-clip bg-bone-50 font-landing text-ink-1 antialiased"
>
	<nav
		class={`fixed inset-x-0 top-0 z-40 border-b backdrop-blur-xl transition-colors duration-200 ${isNavScrolled ? 'border-bone-200 bg-bone-50/95' : 'border-transparent bg-bone-50/80'}`}
	>
		<div
			class="mx-auto flex h-[68px] w-full max-w-[1220px] items-center justify-between px-5 sm:px-8"
		>
			<a href="/" aria-label="Vitevue home">
				{@render BrandLogo('dark')}
			</a>
			<div class="flex items-center gap-8">
				<div class="hidden items-center gap-8 text-sm font-medium text-ink-3 md:flex">
					<a
						class="transition-colors hover:text-ink-1"
						href="#workflow"
						onclick={scrollToPageSection}>Workflows</a
					>
					<a
						class="transition-colors hover:text-ink-1"
						href="#platform"
						onclick={scrollToPageSection}>Market data</a
					>
					<a class="transition-colors hover:text-ink-1" href="#radar" onclick={scrollToPageSection}
						>Radar</a
					>
					<a class="transition-colors hover:text-ink-1" href="#who" onclick={scrollToPageSection}
						>Who it's for</a
					>
				</div>
				<a
					class="inline-flex min-h-10 items-center justify-center rounded-md bg-navy-900 px-4 text-sm font-semibold text-bone-50 transition hover:-translate-y-px hover:bg-navy-800 active:translate-y-px"
					href="#contact"
					onclick={scrollToPageSection}
				>
					Contact us
				</a>
			</div>
		</div>
	</nav>

	<header
		class="relative px-5 pt-[88px] pb-14 sm:px-8 sm:pb-16 lg:flex lg:min-h-[88dvh] lg:items-center lg:pt-[92px] lg:pb-16"
	>
		<div
			class="pointer-events-none absolute inset-0 opacity-50 [background-image:linear-gradient(#ddd2bc_1px,transparent_1px),linear-gradient(90deg,#ddd2bc_1px,transparent_1px)] [background-size:66px_66px] [mask-image:radial-gradient(ellipse_80%_70%_at_70%_30%,#050d18,transparent_75%)]"
		></div>
		<div
			class="relative mx-auto grid w-full max-w-[1380px] items-center gap-6 lg:grid-cols-[0.82fr_1.18fr] lg:gap-12 xl:gap-14"
		>
			<div>
				<h1
					data-reveal="up"
					data-reveal-delay="80"
					class="max-w-[13.5ch] font-display text-[clamp(2.25rem,10.3vw,4.625rem)] leading-[1.08] font-normal tracking-normal text-ink-1"
				>
					The AI workspace for Dubai real estate teams.
				</h1>
				<p
					data-reveal="up"
					data-reveal-delay="150"
					class="mt-4 max-w-[50ch] text-[17px] leading-relaxed text-ink-3 sm:mt-5 sm:text-lg"
				>
					Vitevue brings market data, analysis and agentic workflows into one workspace, so real
					estate teams can move from evidence to decision-ready work faster.
				</p>
				<div
					data-reveal="up"
					data-reveal-delay="220"
					class="mt-4 flex flex-col gap-3 sm:mt-5 sm:flex-row sm:flex-wrap"
				>
					<a
						class="inline-flex min-h-[46px] items-center justify-center gap-2 rounded-md bg-navy-900 px-6 text-[15px] font-semibold text-bone-50 transition hover:-translate-y-0.5 hover:bg-navy-800 active:translate-y-px"
						href={accessHref}
					>
						<Mail size={17} />
						Contact us
					</a>
					<a
						class="inline-flex min-h-[46px] items-center justify-center gap-2 rounded-md border border-slate-300 px-6 text-[15px] font-semibold text-ink-1 transition hover:-translate-y-0.5 hover:border-ink-2 active:translate-y-px"
						href="#workflow"
						onclick={scrollToPageSection}
					>
						<ArrowDownRight size={17} />
						See the workflow
					</a>
				</div>
			</div>

			<div class="relative mt-2 sm:mt-10 lg:mt-0" data-reveal="scale" data-reveal-delay="120">
				<div class="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-landing-lg">
					<img
						class="w-full"
						src="/landing/shots/dashboard.png"
						alt="Vitevue dashboard with market data and Vitevue AI"
					/>
				</div>
				<div
					data-parallax="0.1"
					class="hidden overflow-hidden rounded-lg border border-slate-200 shadow-landing-xl sm:absolute sm:bottom-[-44px] sm:left-[-50px] sm:block sm:w-[62%]"
				>
					<img
						class="w-full"
						src="/landing/shots/workflows.png"
						alt="Vitevue agentic workflows dashboard"
					/>
				</div>
			</div>
		</div>
	</header>

	<section
		id="workflow"
		class="scroll-mt-[68px] border-y border-bone-200 bg-bone-100 px-5 py-24 sm:px-8 lg:py-[120px]"
	>
		<div class="mx-auto w-full max-w-[1320px]">
			<div class="mx-auto max-w-[780px] text-center" data-reveal="up">
				<h2
					class="mx-auto max-w-[24ch] font-display text-[clamp(2.125rem,4.4vw,3.625rem)] leading-tight font-normal text-ink-1"
				>
					Agentic workflows for industry-grade deliverables.
				</h2>
				<p class="mx-auto mt-5 max-w-[54ch] text-lg leading-relaxed text-ink-3">
					Vitevue gathers the evidence, tests assumptions, explains trade-offs and returns concrete
					deliverables your team can use.
				</p>
			</div>

			<div class="mt-14" data-reveal="scale" data-reveal-delay="100">
				<div class="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-landing-xl">
					<img
						class="w-full"
						src="/landing/shots/workflows.png"
						alt="Agentic workflows dashboard with customizable workflow cards"
					/>
				</div>
			</div>
		</div>
	</section>

	<section id="platform" class="scroll-mt-[68px] px-5 py-24 sm:px-8 lg:py-[120px]">
		<div class="mx-auto w-full max-w-[1320px]">
			<div class="mx-auto max-w-[760px] text-center" data-reveal="up">
				<h2
					class="font-display text-[clamp(2rem,4.2vw,3.375rem)] leading-tight font-normal text-ink-1"
				>
					Find and export the market data you need.
				</h2>
			</div>

			<div class="mt-20 grid items-center gap-10 lg:grid-cols-[0.36fr_0.64fr] lg:gap-14">
				<div data-reveal="up">
					<h3
						class="font-display text-[clamp(1.75rem,3.2vw,2.625rem)] leading-tight font-normal text-ink-1"
					>
						Build the comp set from DLD and Ejari records.
					</h3>
					<p class="mt-4 max-w-[38ch] text-[17px] leading-relaxed text-ink-3">
						Scope DLD sales and Ejari rental contracts down to the evidence set behind a memo,
						valuation note or client pack.
					</p>
				</div>
				<div
					data-reveal="scale"
					data-reveal-delay="80"
					class="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-landing-lg"
				>
					<img
						class="-mt-[4.2%] w-full"
						src="/landing/shots/transactions.png"
						alt="Transactions view filtered to residential sales records"
					/>
				</div>
			</div>

			<div class="mt-[120px] grid items-center gap-10 lg:grid-cols-[0.64fr_0.36fr] lg:gap-14">
				<div class="lg:order-2" data-reveal="up">
					<h3
						class="font-display text-[clamp(1.75rem,3.2vw,2.625rem)] leading-tight font-normal text-ink-1"
					>
						Compare sub-markets by price, yield, mix and more.
					</h3>
					<p class="mt-4 max-w-[38ch] text-[17px] leading-relaxed text-ink-3">
						Review pricing, yield, configuration trends and other market signals against the full
						Dubai market.
					</p>
				</div>
				<div
					data-reveal="scale"
					data-reveal-delay="80"
					class="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-landing-lg"
				>
					<img
						class="-mt-[4.2%] w-full"
						src="/landing/shots/analytics.png"
						alt="Analytics comparing Dubai against Business Bay"
					/>
				</div>
			</div>
		</div>
	</section>

	<section
		id="radar"
		class="relative scroll-mt-[68px] overflow-hidden bg-navy-950 px-5 py-24 text-bone-50 sm:px-8 lg:py-32"
	>
		<div class="absolute inset-0 opacity-[0.34]" data-parallax="0.05">
			<img
				class="h-full w-full object-cover"
				src="/landing/shots/radar.png"
				alt="Projects radar map"
			/>
			<div
				class="absolute inset-0 bg-[linear-gradient(90deg,#050d18_8%,rgba(5,13,24,0.5)_60%,rgba(5,13,24,0.85))]"
			></div>
		</div>
		<div class="relative z-10 mx-auto w-full max-w-[1220px]">
			<div class="max-w-[58ch]" data-reveal="up">
				<span class="text-xs font-medium tracking-[0.18em] text-mark-mid uppercase">Radar</span>
				<h2 class="mt-4 font-display text-[clamp(2rem,4.4vw,3.5rem)] leading-tight font-normal">
					The supply context, mapped before it moves the market.
				</h2>
				<p class="mt-5 text-[19px] leading-relaxed text-bone-50/80">
					Radar shows where Dubai's active and upcoming supply is concentrated, from projects and
					pipeline units to delivery timing and nearby competition. Use it to understand the supply
					picture around a site, sub-market or portfolio before making decisions.
				</p>
				<div class="mt-10 grid grid-cols-3 gap-x-4 gap-y-8 sm:flex sm:flex-wrap sm:gap-10">
					<div class="min-w-0">
						<div class="font-display text-[40px] leading-none text-mark-mid tabular-nums">
							<span class="inline-block min-w-[4ch]" data-count="3" data-count-suffix="K" data-reveal-repeat
								>0</span
							>
						</div>
						<div class="mt-2 text-sm text-slate-400">Projects mapped</div>
					</div>
					<div class="min-w-0">
						<div class="font-display text-[40px] leading-none text-mark-mid tabular-nums">
							<span class="inline-block min-w-[4ch]" data-count="383" data-count-suffix="K" data-reveal-repeat
								>0</span
							>
						</div>
						<div class="mt-2 text-sm text-slate-400">Pipeline units</div>
					</div>
					<div class="min-w-0">
						<div class="font-display text-[40px] leading-none text-mark-mid tabular-nums">
							<span class="inline-block min-w-[4ch]" data-count="99" data-count-suffix="K" data-reveal-repeat
								>0</span
							>
						</div>
						<div class="mt-2 text-sm text-slate-400">Land plots</div>
					</div>
				</div>
			</div>
		</div>
	</section>

	<section
		id="who"
		class="scroll-mt-[68px] border-t border-bone-200 bg-bone-100 px-5 py-24 sm:px-8 lg:py-[120px]"
	>
		<div class="mx-auto w-full max-w-[1220px]">
			<div class="max-w-[62ch]" data-reveal="up">
				<h2
					class="max-w-[18ch] font-display text-[clamp(2rem,4.2vw,3.375rem)] leading-tight font-normal text-ink-1"
				>
					For teams turning evidence into action.
				</h2>
			</div>
			<div data-reveal-group data-reveal-step="80" class="mt-16 grid gap-6 md:grid-cols-3">
				{#each personas as persona}
					<article
						class="flex min-h-[260px] flex-col gap-4 rounded-lg border border-bone-200 bg-[#fbf7ee] p-8 transition-colors duration-200 hover:border-bone-300"
					>
						<span class="font-mono text-[11px] font-medium tracking-[0.06em] text-ink-4">
							{persona.number}
						</span>
						<h3
							class="font-display text-[clamp(1.875rem,3vw,2.625rem)] leading-[1.05] font-normal text-ink-1"
						>
							{persona.title}
							{#if persona.accent}
								<em class="text-navy-700">{persona.accent}</em>
							{/if}
						</h3>
						<p class="text-[15px] leading-relaxed text-ink-3">{persona.body}</p>
					</article>
				{/each}
			</div>
		</div>
	</section>

	<section id="contact" class="scroll-mt-[68px] px-5 py-24 sm:px-8">
		<div class="mx-auto w-full max-w-[1220px]">
			<div
				data-reveal="up"
				class="relative flex flex-wrap items-center justify-between gap-10 overflow-hidden rounded-xl bg-navy-950 px-7 py-10 text-bone-50 sm:px-14 sm:py-[60px]"
			>
				<div
					class="pointer-events-none absolute top-[-50%] right-[-10%] h-[200%] w-[48%] rounded-full bg-navy-700 opacity-50 blur-[70px]"
				></div>
				<div class="relative z-10">
					<span class="text-xs font-medium tracking-[0.18em] text-mark-mid uppercase"
						>Early access</span
					>
					<h2
						class="mt-3 max-w-[22ch] font-display text-[clamp(1.625rem,3vw,2.5rem)] leading-tight font-normal"
					>
						Vitevue is rolling out to a first group of Dubai teams.
					</h2>
					<p class="mt-3 max-w-[52ch] text-slate-400">
						We are inviting a small group of Dubai real estate teams to pilot Vitevue across market
						data, analysis and decision-ready deliverables.
					</p>
				</div>
				<div class="relative z-10">
					<a
						class="inline-flex min-h-[46px] items-center justify-center gap-2 rounded-md bg-bone-50 px-6 text-[15px] font-semibold text-navy-900 transition hover:-translate-y-0.5 hover:bg-white active:translate-y-px"
						href={contactHref}
					>
						<Mail size={17} />
						Contact us
					</a>
					<span class="mt-3.5 block font-mono text-sm text-slate-400">contact@vitevue.com</span>
				</div>
			</div>
		</div>
	</section>

	<footer class="bg-navy-950 px-5 py-10 text-bone-50 sm:px-8 lg:pt-20">
		<div class="mx-auto w-full max-w-[1220px]">
			<div class="flex flex-wrap justify-between gap-12 border-b border-white/10 pb-12">
				<div class="max-w-[36ch]">
					<div class="mb-5">
						{@render BrandLogo('light')}
					</div>
					<p class="text-[15px] leading-relaxed text-slate-400">
						Powering real estate decisions with AI-native intelligence
					</p>
				</div>
				<div class="flex flex-wrap gap-16">
					<div>
						<h3 class="mb-4 text-xs tracking-[0.18em] text-slate-400 uppercase">Platform</h3>
						<a
							class="mb-2.5 block text-[15px] text-bone-50/85 hover:text-bone-50"
							href="#workflow"
							onclick={scrollToPageSection}>Workflows</a
						>
						<a
							class="mb-2.5 block text-[15px] text-bone-50/85 hover:text-bone-50"
							href="#platform"
							onclick={scrollToPageSection}>Market data</a
						>
						<a
							class="mb-2.5 block text-[15px] text-bone-50/85 hover:text-bone-50"
							href="#radar"
							onclick={scrollToPageSection}>Radar</a
						>
					</div>
					<div>
						<h3 class="mb-4 text-xs tracking-[0.18em] text-slate-400 uppercase">Company</h3>
						<a
							class="mb-2.5 block text-[15px] text-bone-50/85 hover:text-bone-50"
							href="#who"
							onclick={scrollToPageSection}>Who it's for</a
						>
						<a
							class="mb-2.5 block text-[15px] text-bone-50/85 hover:text-bone-50"
							href="#contact"
							onclick={scrollToPageSection}>Early access</a
						>
						<a
							class="mb-2.5 block text-[15px] text-bone-50/85 hover:text-bone-50"
							href="mailto:contact@vitevue.com">Contact</a
						>
					</div>
				</div>
			</div>
			<div class="flex flex-wrap justify-between gap-5 pt-7 text-sm text-slate-400">
				<span>&copy; 2026 Vitevue L.L.C-FZ.</span>
				<span>contact@vitevue.com</span>
			</div>
		</div>
	</footer>
</div>

<style>
	.landing-motion :global([data-reveal].rv) {
		opacity: 0;
		transition:
			opacity 620ms cubic-bezier(0.33, 1, 0.68, 1),
			transform 680ms cubic-bezier(0.33, 1, 0.68, 1),
			filter 680ms cubic-bezier(0.33, 1, 0.68, 1);
		will-change: opacity, transform;
	}

	.landing-motion :global([data-reveal='up'].rv) {
		transform: translateY(34px);
	}

	.landing-motion :global([data-reveal='fade'].rv) {
		transform: none;
	}

	.landing-motion :global([data-reveal='scale'].rv) {
		transform: scale(0.94);
	}

	.landing-motion :global([data-reveal='left'].rv) {
		transform: translateX(-40px);
	}

	.landing-motion :global([data-reveal='right'].rv) {
		transform: translateX(40px);
	}

	.landing-motion :global([data-reveal='blur'].rv) {
		filter: blur(10px);
		transform: translateY(24px);
	}

	.landing-motion :global([data-reveal].rv-in) {
		opacity: 1;
		filter: none;
		transform: none;
	}

	@media (prefers-reduced-motion: reduce) {
		.landing-motion :global([data-reveal].rv) {
			opacity: 1;
			filter: none;
			transform: none;
			transition: none;
		}
	}
</style>
