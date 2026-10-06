import type { BackendUser } from '../../frontend/src/lib/api/auth';

export type TestPersona =
	| 'active-owner'
	| 'pending-owner'
	| 'past-due-owner'
	| 'active-member'
	| 'admin'
	| 'incomplete-profile'
	| 'no-organization';

const baseUser: BackendUser = {
	id: 'user-1',
	email: 'owner@example.com',
	first_name: 'Ada',
	last_name: 'Lovelace',
	organization_id: 'org-1',
	organization_name: 'Acme',
	role: 'owner',
	is_owner: true,
	subscription_status: 'active',
};

export const personas: Record<TestPersona, BackendUser> = {
	'active-owner': baseUser,
	'pending-owner': {
		...baseUser,
		subscription_status: 'pending',
	},
	'past-due-owner': {
		...baseUser,
		subscription_status: 'past_due',
	},
	'active-member': {
		...baseUser,
		email: 'member@example.com',
		role: 'member',
		is_owner: false,
	},
	admin: {
		...baseUser,
		email: 'admin@example.com',
		role: 'admin',
		is_owner: false,
	},
	'incomplete-profile': {
		...baseUser,
		first_name: '',
		last_name: '',
		subscription_status: 'pending',
		organization_id: null,
		organization_name: null,
	},
	'no-organization': {
		...baseUser,
		organization_id: null,
		organization_name: null,
		subscription_status: null,
	},
};
