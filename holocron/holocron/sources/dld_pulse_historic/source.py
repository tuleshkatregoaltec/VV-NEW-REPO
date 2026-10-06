from holocron.contracts import SourceSpec
from holocron.sources.dld_pulse_historic.extract import extract_release

SOURCE = SourceSpec(
    name="dld_pulse_historic",
    provider="dld",
    extractor=extract_release,
    checkpoint_strategy="manual",
    description="One-time Dubai Pulse historic CSV/KML archive.",
)
