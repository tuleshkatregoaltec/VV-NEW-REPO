from typing import List

from pydantic import BaseModel


class FilterOptionsResponse(BaseModel):
    """Filter options for transactions and rentals - dynamically narrowed by selections."""

    projects: List[str] = []
    buildings: List[str] = []  # Dynamic - filtered by project if selected
    property_types: List[str] = []
    property_sub_types: List[str] = []
    rooms: List[str] = []  # Only for sales
    registration_types: List[str] = []  # Only for sales
    tenant_types: List[str] = []  # Only for rentals
    contract_reg_types: List[str] = []  # Only for rentals
    areas: List[str] = []  # Geographic areas
