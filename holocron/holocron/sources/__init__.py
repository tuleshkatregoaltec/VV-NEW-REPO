from holocron.sources.registry import SourceRegistry
from holocron.sources.dda import SOURCE as DDA_SOURCE
from holocron.sources.bayut_listings import SOURCE as BAYUT_LISTINGS_SOURCE
from holocron.sources.dld_od_brokers import SOURCE as DLD_OD_BROKERS_SOURCE
from holocron.sources.dld_od_buildings import SOURCE as DLD_OD_BUILDINGS_SOURCE
from holocron.sources.dld_od_developers import SOURCE as DLD_OD_DEVELOPERS_SOURCE
from holocron.sources.dld_od_lands import SOURCE as DLD_OD_LANDS_SOURCE
from holocron.sources.dld_od_projects import SOURCE as DLD_OD_PROJECTS_SOURCE
from holocron.sources.dld_od_rents import SOURCE as DLD_OD_RENTS_SOURCE
from holocron.sources.dld_od_transactions import SOURCE as DLD_OD_TRANSACTIONS_SOURCE
from holocron.sources.dld_od_units import SOURCE as DLD_OD_UNITS_SOURCE
from holocron.sources.dld_od_valuations import SOURCE as DLD_OD_VALUATIONS_SOURCE
from holocron.sources.dld_mashrooi import SOURCE as DLD_MASHROOI_SOURCE
from holocron.sources.dld_pulse_historic import SOURCE as DLD_PULSE_HISTORIC_SOURCE
from holocron.sources.dxbi import SOURCE as DXBI_SOURCE
from holocron.sources.news_feeds import SOURCE as NEWS_FEEDS_SOURCE
from holocron.sources.pf_listings import SOURCE as PF_LISTINGS_SOURCE
from holocron.sources.pf_locations import SOURCE as PF_LOCATIONS_SOURCE
from holocron.sources.reelly_supply import SOURCE as REELLY_SUPPLY_SOURCE

registry = SourceRegistry()

for source in (
    DDA_SOURCE,
    BAYUT_LISTINGS_SOURCE,
    DLD_OD_TRANSACTIONS_SOURCE,
    DLD_OD_RENTS_SOURCE,
    DLD_OD_PROJECTS_SOURCE,
    DLD_OD_VALUATIONS_SOURCE,
    DLD_OD_LANDS_SOURCE,
    DLD_OD_BUILDINGS_SOURCE,
    DLD_OD_UNITS_SOURCE,
    DLD_OD_BROKERS_SOURCE,
    DLD_OD_DEVELOPERS_SOURCE,
    DLD_MASHROOI_SOURCE,
    DLD_PULSE_HISTORIC_SOURCE,
    DXBI_SOURCE,
    NEWS_FEEDS_SOURCE,
    PF_LOCATIONS_SOURCE,
    PF_LISTINGS_SOURCE,
    REELLY_SUPPLY_SOURCE,
):
    registry.register(source)

__all__ = [
    "DDA_SOURCE",
    "BAYUT_LISTINGS_SOURCE",
    "DLD_OD_BROKERS_SOURCE",
    "DLD_OD_BUILDINGS_SOURCE",
    "DLD_OD_DEVELOPERS_SOURCE",
    "DLD_OD_LANDS_SOURCE",
    "DLD_OD_PROJECTS_SOURCE",
    "DLD_OD_RENTS_SOURCE",
    "DLD_OD_TRANSACTIONS_SOURCE",
    "DLD_OD_UNITS_SOURCE",
    "DLD_OD_VALUATIONS_SOURCE",
    "DLD_MASHROOI_SOURCE",
    "DLD_PULSE_HISTORIC_SOURCE",
    "DXBI_SOURCE",
    "NEWS_FEEDS_SOURCE",
    "PF_LISTINGS_SOURCE",
    "PF_LOCATIONS_SOURCE",
    "REELLY_SUPPLY_SOURCE",
    "registry",
]
