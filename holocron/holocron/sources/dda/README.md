# DDA Planning Layers

`dda_planning_layers` extracts Dubai Development Authority planning map layers
as raw CSV files. This is provider planning/GIS data, not real-estate market
data.

## Source Contract

- Provider: `dda`
- Dagster raw asset: `dda_planning_layers_raw`
- Checkpoint strategy: `full_refresh`
- Cadence: weekly raw + bronze full refresh schedule plus manual full refresh
- Bronze tables: `dda_*` planning tables

## Raw Files

Current CSV outputs:

- `dda_plots.csv`
- `dda_project_areas.csv`
- `dda_subproject_areas.csv`
- `dda_plot_building_limits.csv`
- `dda_plot_podium_limits.csv`
- `dda_plot_features.csv`
- `dda_frozen_plots.csv`
- `dda_landuse_symbols.csv`
- `dda_plot_built_to_lines.csv`
- `dda_plot_arcades.csv`
- `dda_plot_retail.csv`

Rows preserve provider layer attributes and geometry-related fields where
available.

## R2 Layout

```text
raw/source=dda_planning_layers/extract_date=<date>/run_id=<run_id>/*.csv
raw/source=dda_planning_layers/manifests/<run_id>.json
```

## Config Notes

Important knobs:

- `concurrency`: concurrent layer/plot requests.
- `max_plots`: optional cap for smoke tests.

## Operational Notes

DDA is a full refresh source and has been wired through raw and bronze. Bronze
replaces the current ClickHouse DDA tables atomically from each complete raw
release. It is a good candidate for repeatable backfills because it does not
depend on a limited paid API quota. The registered weekly schedule is stopped by
default.
