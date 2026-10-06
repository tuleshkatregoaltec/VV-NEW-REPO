import { feasibility } from '$lib/api/feasibility'
import type { FeasibilitySavedStudyResponse, Plot } from '$lib/api/generated/hey-api/types.gen'
import { createAssumptionsFromPlot, hydrateAssumptions } from '$lib/feasibility/workbook/defaults'
import type {
	DevelopmentModel,
	FeasibilityAssumptions,
	FeasibilityChatState,
	FeasibilityStudy,
	UsageType
} from '$lib/feasibility/workbook/models'
import { feasibilityWorkspace } from '$lib/stores/feasibilityWorkspace.svelte'

type StudyPhase = 'search' | 'generating' | 'ready' | 'error'
type SaveState = 'saved' | 'saving' | 'unsaved' | 'failed'
export interface DevelopmentModelOption {
	id: DevelopmentModel
	label: string
	descriptor: string
	description: string
	available: boolean
}

const phase = $state({ value: 'search' as StudyPhase })
const selectedPlot = $state({ value: null as Plot | null })
const study = $state({ value: null as FeasibilityStudy | null })
const savedStudyId = $state({ value: null as number | null })
const savedStudyName = $state({ value: '' })
const saveState = $state({ value: 'saved' as SaveState })
const error = $state({ value: '' })
let workbookSaveSequence = 0
let auxSaveSequence = 0
let dirtyVersion = 0
let savedVersion = 0

function developmentModelOptions(usage: UsageType): DevelopmentModelOption[] {
	if (usage === 'residential') {
		return [
			{
				id: 'build_to_sell_residential',
				label: 'Build to sell',
				descriptor: 'Residential',
				description: 'For-sale residential underwriting. This is the active generation path today.',
				available: true
			},
			{
				id: 'build_to_rent_residential',
				label: 'Build to rent',
				descriptor: 'Residential',
				description:
					'Held rental residential product with operating P&L, exit valuation, and permanent debt sizing.',
				available: true
			}
		]
	}

	if (usage === 'mixed_use') {
		return [
			{
				id: 'build_to_sell_residential',
				label: 'Build to sell',
				descriptor: 'Residential',
				description: 'For-sale residential stack inside the mixed-use zoning envelope.',
				available: true
			},
			{
				id: 'build_to_rent_residential',
				label: 'Build to rent',
				descriptor: 'Residential',
				description:
					'Held rental residential product with operating P&L, exit valuation, and permanent debt sizing.',
				available: true
			},
			{
				id: 'build_to_lease_commercial',
				label: 'Build to lease',
				descriptor: 'Commercial',
				description:
					'Commercial lease-up path for the mixed-use commercial component. Visible in UX only for now.',
				available: false
			}
		]
	}

	return []
}

function emptyChatState(): FeasibilityChatState {
	return { messages: [], history_json: null }
}

function normalizeChatState(raw: unknown): FeasibilityChatState {
	if (!raw || typeof raw !== 'object') return emptyChatState()
	const candidate = raw as Partial<FeasibilityChatState>
	return {
		messages: Array.isArray(candidate.messages) ? candidate.messages : [],
		history_json: typeof candidate.history_json === 'string' ? candidate.history_json : null
	}
}

function cloneAssumptions(assumptions: FeasibilityAssumptions): FeasibilityAssumptions {
	return JSON.parse(JSON.stringify(assumptions)) as FeasibilityAssumptions
}

function resetSaveTracking() {
	workbookSaveSequence = 0
	auxSaveSequence = 0
	dirtyVersion = 0
	savedVersion = 0
	saveState.value = 'saved'
}

function settleSaveState() {
	saveState.value = dirtyVersion === savedVersion ? 'saved' : 'unsaved'
}

function createBaseStudy(plot_data: NonNullable<FeasibilityStudy['plot_data']>): FeasibilityStudy {
	const assumptions = createAssumptionsFromPlot(plot_data)

	const study_context = {
		headline: plot_data.project_name,
		project_tier: 'premium',
		positioning: 'Seeded study pending generation',
		summary_points: [],
		unit_mix_rationale: '',
		pricing_rationale: '',
		cost_rationale: '',
		timing_rationale: '',
		financing_rationale: '',
		market_summary: ''
	}

	const research = {
		plot_number: plot_data.plot_number,
		usage: plot_data.inferred_usage ?? 'unknown',
		market_area: plot_data.community_name,
		headline: plot_data.project_name,
		summary: [],
		constraints: [],
		warnings: [],
		pricing_evidence: [],
		competition_evidence: [],
		land_sales_evidence: [],
		market_pricing: [],
		off_plan_market_pricing: [],
		off_plan_pricing_confidence: null,
		off_plan_unit_benchmarks: [],
		rental_market_summary: null,
		rental_comparables: [],
		assumptions: assumptions as never,
		land_cost_estimate_aed_low: null,
		land_cost_estimate_aed_mid: null,
		land_cost_estimate_aed_high: null
	}

	return {
		status: 'ready' as const,
		plot_data,
		assumptions,
		study_context,
		research,
		chat: { history: [] }
	}
}

function adaptBackendStudy(
	raw: Record<string, unknown>,
	selectedDevelopmentModel?: DevelopmentModel,
	hydrationMode: 'saved' | 'generated' = 'saved'
): FeasibilityStudy {
	const plot_data = raw.plot_data as FeasibilityStudy['plot_data']
	const research = raw.research as FeasibilityStudy['research']
	const study_context = raw.study_context as FeasibilityStudy['study_context']
	const chatState = normalizeChatState(raw.chat_state)
	const assumptions = hydrateAssumptions(
		raw.assumptions as Partial<FeasibilityAssumptions>,
		plot_data,
		research,
		selectedDevelopmentModel,
		{ mode: hydrationMode }
	)
	return {
		status: 'ready',
		plot_data,
		assumptions: selectedDevelopmentModel
			? { ...assumptions, developmentModel: selectedDevelopmentModel }
			: assumptions,
		study_context,
		research,
		chat: { history: chatState.messages }
	}
}

function mergeStudy(
	raw: Record<string, unknown>,
	selectedDevelopmentModel?: DevelopmentModel,
	hydrationMode: 'saved' | 'generated' = 'saved'
) {
	study.value = adaptBackendStudy(raw, selectedDevelopmentModel, hydrationMode)
	phase.value = 'ready'
	error.value = ''
}

function hydrateSavedStudyRecord(saved: FeasibilitySavedStudyResponse) {
	savedStudyId.value = saved.id
	savedStudyName.value = saved.name
	resetSaveTracking()
	feasibilityWorkspace.hydrate(
		normalizeChatState((saved as unknown as Record<string, unknown>).chat_state)
	)
	mergeStudy(saved as unknown as Record<string, unknown>, saved.development_model, 'saved')
	return saved
}

export const feasibilityStudy = {
	get phase() {
		return phase.value
	},
	get selectedPlot() {
		return selectedPlot.value
	},
	get study() {
		return study.value
	},
	get savedStudyId() {
		return savedStudyId.value
	},
	get savedStudyName() {
		return savedStudyName.value
	},
	get saveState() {
		return saveState.value
	},
	get error() {
		return error.value
	},
	get plotData() {
		return study.value?.plot_data ?? null
	},
	get developmentModelOptions() {
		const usage =
			study.value?.assumptions.usage ?? study.value?.plot_data.inferred_usage ?? 'unknown'
		return developmentModelOptions(usage)
	},
	get developmentModel() {
		return study.value?.assumptions.developmentModel
	},
	get developmentModelSelectorVisible() {
		const usage =
			study.value?.assumptions.usage ?? study.value?.plot_data.inferred_usage ?? 'unknown'
		return developmentModelOptions(usage).length > 0
	},
	get canGenerateSelectedModel() {
		const usage =
			study.value?.assumptions.usage ?? study.value?.plot_data.inferred_usage ?? 'unknown'
		const options = developmentModelOptions(usage)
		if (options.length === 0) return true
		const current = study.value?.assumptions.developmentModel
		if (!current) return false
		return options.some((option) => option.id === current && option.available)
	},
	get developmentModelMessage() {
		const usage =
			study.value?.assumptions.usage ?? study.value?.plot_data.inferred_usage ?? 'unknown'
		const options = developmentModelOptions(usage)
		if (options.length === 0) return ''
		if (!study.value?.assumptions.developmentModel) {
			return 'Select the intended development model before generation.'
		}
		const current = study.value.assumptions.developmentModel
		const canGenerate = options.some((option) => option.id === current && option.available)
		if (!canGenerate) {
			return 'This model type is not yet available. Select an active model to proceed.'
		}
		const modelLabel = options.find((o) => o.id === current)?.label ?? current
		return `${modelLabel} model is active and ready for generation.`
	},
	async selectPlot(plot: Plot) {
		selectedPlot.value = plot
		error.value = ''
		phase.value = 'search'
		const response = await feasibility.getPlotData(plot.plot_number)
		study.value = createBaseStudy(response.plot_data)
	},
	openEmptyWorkbookForDev() {
		if (!study.value?.plot_data) return
		study.value = createBaseStudy(study.value.plot_data)
		phase.value = 'ready'
		error.value = ''
	},
	async generateStudy() {
		const plot = selectedPlot.value
		if (!plot) return
		const usage =
			study.value?.assumptions.usage ?? study.value?.plot_data.inferred_usage ?? 'unknown'
		const options = developmentModelOptions(usage)
		const current = study.value?.assumptions.developmentModel
		const canGenerate =
			options.length === 0 ||
			!!(current && options.some((option) => option.id === current && option.available))
		if (!canGenerate) {
			error.value =
				'This development model is not yet available. Select an active model to proceed.'
			return
		}
		phase.value = 'generating'
		error.value = ''
		try {
			const next = await feasibility.generateStudy({
				plot_number: plot.plot_number,
				usage_override: study.value?.assumptions.usage,
				development_model: current
			})
			mergeStudy(next as unknown as Record<string, unknown>, current, 'generated')
		} catch (err) {
			phase.value = 'error'
			error.value = err instanceof Error ? err.message : 'Failed to generate feasibility study.'
		}
	},
	async createSavedStudy(params: {
		name: string
		plot_number: string
		usage_override?: UsageType
		development_model: DevelopmentModel
	}) {
		phase.value = 'generating'
		error.value = ''
		try {
			const saved = await feasibility.createStudy(params)
			return hydrateSavedStudyRecord(saved)
		} catch (err) {
			phase.value = 'error'
			error.value = err instanceof Error ? err.message : 'Failed to create feasibility study.'
			throw err
		}
	},
	hydrateSavedStudy(saved: FeasibilitySavedStudyResponse) {
		return hydrateSavedStudyRecord(saved)
	},
	async loadSavedStudy(studyId: number) {
		phase.value = 'generating'
		error.value = ''
		try {
			const saved = await feasibility.getStudy(studyId)
			return hydrateSavedStudyRecord(saved)
		} catch (err) {
			phase.value = 'error'
			error.value = err instanceof Error ? err.message : 'Failed to load feasibility study.'
			throw err
		}
	},
	async renameSavedStudy(name: string) {
		if (!savedStudyId.value) return
		const trimmed = name.trim()
		if (!trimmed) return
		const sequence = ++auxSaveSequence
		const wasClean = dirtyVersion === savedVersion
		if (wasClean) saveState.value = 'saving'
		try {
			const saved = await feasibility.updateStudy(savedStudyId.value, { name: trimmed })
			savedStudyName.value = saved.name
			if (sequence === auxSaveSequence) settleSaveState()
		} catch (err) {
			if (sequence === auxSaveSequence) saveState.value = 'failed'
			error.value = err instanceof Error ? err.message : 'Failed to rename feasibility study.'
		}
	},
	async autosaveAssumptions(
		assumptions: FeasibilityAssumptions,
		options: { chatState?: FeasibilityChatState } = {}
	) {
		if (!savedStudyId.value) return
		const sequence = ++workbookSaveSequence
		const versionAtSave = dirtyVersion
		const savedAssumptions = cloneAssumptions(assumptions)
		saveState.value = 'saving'
		try {
			await feasibility.autosaveStudy(savedStudyId.value, {
				assumptions: savedAssumptions,
				development_model: savedAssumptions.developmentModel,
				chat_state: options.chatState
			})
			if (sequence !== workbookSaveSequence) return
			if (versionAtSave === dirtyVersion) {
				savedVersion = versionAtSave
				if (study.value) {
					study.value = { ...study.value, assumptions: savedAssumptions }
				}
			}
			settleSaveState()
		} catch (err) {
			if (sequence === workbookSaveSequence) saveState.value = 'failed'
			error.value = err instanceof Error ? err.message : 'Failed to save feasibility study.'
		}
	},
	async saveCurrentWorkbook(
		assumptions: FeasibilityAssumptions | null | undefined,
		options: { chatState?: FeasibilityChatState } = {}
	) {
		if (!assumptions) return
		await feasibilityStudy.autosaveAssumptions(assumptions, options)
	},
	async persistChatState(chatState: FeasibilityChatState) {
		if (!savedStudyId.value) return
		const sequence = ++auxSaveSequence
		saveState.value = 'saving'
		try {
			await feasibility.autosaveStudy(savedStudyId.value, { chat_state: chatState })
			if (sequence === auxSaveSequence) settleSaveState()
		} catch (err) {
			if (sequence === auxSaveSequence) saveState.value = 'failed'
			error.value = err instanceof Error ? err.message : 'Failed to save feasibility chat.'
		}
	},
	markUnsaved() {
		if (!savedStudyId.value) return
		dirtyVersion += 1
		saveState.value = 'unsaved'
	},
	setDevelopmentModel(model: DevelopmentModel) {
		if (!study.value) return
		study.value = {
			...study.value,
			assumptions: {
				...study.value.assumptions,
				developmentModel: model
			}
		}
	},
	reset() {
		phase.value = 'search'
		selectedPlot.value = null
		study.value = null
		savedStudyId.value = null
		savedStudyName.value = ''
		resetSaveTracking()
		feasibilityWorkspace.reset()
		error.value = ''
	}
}
