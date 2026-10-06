<script lang="ts">
import { page } from '$app/state'
</script>

<div class="flex min-h-screen bg-app px-4 pt-30 justify-center">
	<div class="flex flex-col items-center w-full max-w-xl">
		<h1 class="text-[10vw] font-black text-primary mb-4">{page.status}</h1>
		<div class="text-2xl text-gray-700 mb-8 text-center">
			{page.error?.message ?? 'Something went wrong'}
		</div>
		<a
			href="/"
			class="px-6 py-2 rounded bg-primary text-white font-semibold hover:bg-primary-dark transition"
			>Return to Home</a
		>
	</div>
</div>
