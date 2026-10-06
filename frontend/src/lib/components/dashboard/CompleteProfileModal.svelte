<script lang="ts">
import { AuthClient } from '@supabase/auth-js'
import { env } from '$env/dynamic/public'
import TextInput from '$lib/components/auth/TextInput.svelte'
import { currentUser } from '$lib/stores/user.svelte'

const client = new AuthClient({
	url: `${env.PUBLIC_AUTH_BASE_URL}`,
	storageKey: 'authentication',
	detectSessionInUrl: true,
	persistSession: true
})

let firstName = $state('')
let lastName = $state('')
let loading = $state(false)
let error = $state('')

let fieldErrors = $state({
	firstName: '',
	lastName: ''
})

async function handleSubmit() {
	fieldErrors.firstName = ''
	fieldErrors.lastName = ''

	if (!firstName.trim()) {
		fieldErrors.firstName = 'First name is required'
		return
	}
	if (!lastName.trim()) {
		fieldErrors.lastName = 'Last name is required'
		return
	}

	loading = true
	error = ''

	try {
		const result = await client.updateUser({
			data: {
				first_name: firstName,
				last_name: lastName
			}
		})

		if (result.error) {
			error = result.error.message || 'Failed to update profile'
			return
		}

		if (currentUser.data) {
			currentUser.data = {
				...currentUser.data,
				first_name: firstName,
				last_name: lastName
			}
		}
	} catch (e) {
		error = 'Failed to update profile. Please try again.'
		console.error('Profile update error:', e)
	} finally {
		loading = false
	}
}
</script>

<!-- Blocking modal overlay -->
<div class="fixed inset-0 bg-black/50  z-50 flex items-center justify-center p-4">
	<div class="bg-white rounded-lg shadow-2xl max-w-md w-full p-8">
		<!-- Header -->
		<div class="mb-6 text-center">
			<div
				class="w-16 h-16 bg-primary rounded-full flex items-center justify-center mx-auto mb-4"
			>
				<svg class="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
					/>
				</svg>
			</div>
			<h2 class="text-3xl font-bold text-slate-900 mb-2">Complete Your Profile</h2>
			<p class="text-slate-600">We need your name to personalize your experience</p>
		</div>

		{#if error}
			<div class="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">
				{error}
			</div>
		{/if}

		<!-- Form -->
		<form
			onsubmit={(e) => {
				e.preventDefault();
				handleSubmit();
			}}
			class="space-y-4"
		>
			<TextInput
				label="First Name"
				bind:value={firstName}
				placeholder="John"
				error={fieldErrors.firstName}
				required
				autocomplete="given-name"
			/>

			<TextInput
				label="Last Name"
				bind:value={lastName}
				placeholder="Doe"
				error={fieldErrors.lastName}
				required
				autocomplete="family-name"
			/>

			<button
				type="submit"
				disabled={loading}
				class="w-full bg-primary hover:bg-primary-light text-white rounded-lg px-4 py-3
                       transition-all disabled:opacity-50 disabled:cursor-not-allowed font-medium shadow-lg hover:shadow-xl"
			>
				{loading ? 'Saving...' : 'Continue'}
			</button>
		</form>
	</div>
</div>
