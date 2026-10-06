## Vitevue

Vitevue is a real estate intelligence platform for teams that need to move from raw market data to investment, development, and advisory decisions with more structure and confidence.

The platform brings together:

- transaction and rental market data
- project and supply tracking
- analytics and comparable research
- feasibility workflows and structured assumption modeling
- AI-assisted research and market interrogation
- organization, billing, and admin controls for team-based access

The current product surface is oriented around Dubai real estate workflows, with features for:

- investors evaluating opportunities and market positioning
- developers pressure-testing projects, pricing, and supply context
- advisory teams building evidence packs, research outputs, and client-facing narratives

At a repo level, the codebase is organized into:

- `backend/`: the FastAPI application, business logic, models, migrations, and backend tests
- `frontend/`: the SvelteKit application, shared UI code, and frontend tests
- `e2e/`: Playwright browser tests for cross-app flows and guard coverage

## Development

See [development.md](/home/vitevue/repos/vitevue-platform/development.md) for setup, local commands, environment configuration, git hooks, and the day-to-day development workflow.

For a new primary development Mac, including Tailscale, the scrape/data
workflow, and local CRM data loading, see [docs/new-mac-setup.md](docs/new-mac-setup.md).

---:::---