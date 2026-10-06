from unittest.mock import AsyncMock, patch

from app.filters.service import get_rental_filter_options, get_sales_filter_options


async def test_get_sales_filter_options_normalizes_and_applies_full_context():
    mock_query = AsyncMock(
        side_effect=[
            [{"property_type_en": " Unit "}, {"property_type_en": "Villa"}],
            [{"property_sub_type_en": " Apartment "}, {"property_sub_type_en": "Penthouse"}],
            [
                {"rooms_en": "2 B/R"},
                {"rooms_en": " Studio "},
                {"rooms_en": "1 B/R"},
                {"rooms_en": "Office"},
            ],
            [{"reg_type_en": " Freehold "}, {"reg_type_en": "Leasehold"}],
            [{"area_name_en": " Downtown "}, {"area_name_en": "Dubai Marina"}],
            [{"project_name_en": "Tower A"}, {"project_name_en": " Tower B "}],
            [{"building_name_en": " Building 2 "}, {"building_name_en": "Building 1"}],
        ]
    )

    with patch("app.filters.service.query", new=mock_query):
        result = await get_sales_filter_options(
            property_usage="Residential",
            project="Downtown Views",
            filter_type="master",
            property_type="Unit",
            property_sub_type="Apartment",
            rooms="2 B/R",
            registration_type="Freehold",
            area="Downtown",
            building="Tower A",
            timeframe_days=30,
            area_min=100,
            area_max=200,
            price_min=1_000_000,
            price_max=2_000_000,
            price_per_sqm_min=20_000,
            price_per_sqm_max=30_000,
        )

    assert result.property_types == ["Unit", "Villa"]
    assert result.property_sub_types == ["Apartment", "Penthouse"]
    assert result.rooms == ["Studio", "1 B/R", "2 B/R", "Office"]
    assert result.registration_types == ["Freehold", "Leasehold"]
    assert result.areas == ["Downtown", "Dubai Marina"]
    assert result.projects == ["Tower A", "Tower B"]
    assert result.buildings == ["Building 1", "Building 2"]

    sql, params = mock_query.await_args_list[0].args
    assert "trans_group_en = 'Sales'" in sql
    assert "property_sub_type_en = {property_sub_type:String}" in sql
    assert "rooms_en = {rooms:String}" in sql
    assert "reg_type_en = {registration_type:String}" in sql
    assert "building_name_en = {building:String}" in sql
    assert "actual_worth >= {price_min:Decimal64(2)}" in sql
    assert "meter_sale_price <= {price_per_sqm_max:Decimal64(2)}" in sql
    assert params == {
        "property_usage": "Residential",
        "project_name": "Downtown Views",
        "property_type": "Unit",
        "property_sub_type": "Apartment",
        "rooms": "2 B/R",
        "registration_type": "Freehold",
        "area": "Downtown",
        "timeframe_days": 30,
        "area_min": 100,
        "area_max": 200,
        "building": "Tower A",
        "price_min": 1_000_000,
        "price_max": 2_000_000,
        "price_per_sqm_min": 20_000,
        "price_per_sqm_max": 30_000,
    }


async def test_get_rental_filter_options_normalizes_and_applies_full_context():
    mock_query = AsyncMock(
        side_effect=[
            [{"ejari_property_type_en": " Studio "}, {"ejari_property_type_en": "Flat"}],
            [
                {"ejari_property_sub_type_en": " Furnished "},
                {"ejari_property_sub_type_en": "Unfurnished"},
            ],
            [{"tenant_type_en": " Individual "}, {"tenant_type_en": "Company"}],
            [{"contract_reg_type_en": " Ejari "}, {"contract_reg_type_en": "Lease"}],
            [{"area_name_en": " JVC "}, {"area_name_en": "Dubai Marina"}],
            [{"project_name_en": "Project A"}, {"project_name_en": " Project B "}],
        ]
    )

    with patch("app.filters.service.query", new=mock_query):
        result = await get_rental_filter_options(
            property_usage="Residential",
            project="Marina Gate",
            filter_type="project",
            property_type="Flat",
            property_sub_type="Furnished",
            tenant_type="Individual",
            contract_reg_type="Ejari",
            area="Dubai Marina",
            timeframe_days=180,
            area_min=50,
            area_max=100,
            rent_min=50_000,
            rent_max=100_000,
        )

    assert result.property_types == ["Flat", "Studio"]
    assert result.property_sub_types == ["Furnished", "Unfurnished"]
    assert result.tenant_types == ["Company", "Individual"]
    assert result.contract_reg_types == ["Ejari", "Lease"]
    assert result.areas == ["Dubai Marina", "JVC"]
    assert result.projects == ["Project A", "Project B"]
    assert result.buildings == []

    sql, params = mock_query.await_args_list[0].args
    assert "ejari_property_sub_type_en = {property_sub_type:String}" in sql
    assert "tenant_type_en = {tenant_type:String}" in sql
    assert "contract_reg_type_en = {contract_reg_type:String}" in sql
    assert "annual_amount >= {rent_min:Decimal64(2)}" in sql
    assert "annual_amount <= {rent_max:Decimal64(2)}" in sql
    assert params == {
        "property_usage": "Residential",
        "project_name": "Marina Gate",
        "property_type": "Flat",
        "property_sub_type": "Furnished",
        "tenant_type": "Individual",
        "contract_reg_type": "Ejari",
        "area": "Dubai Marina",
        "timeframe_days": 180,
        "area_min": 50,
        "area_max": 100,
        "rent_min": 50_000,
        "rent_max": 100_000,
    }
