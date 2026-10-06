from datetime import date

from app.feasibility.assumption_defaults import (
    MARKET_ASSUMPTION_FIELDS,
    PROJECT_PHYSICAL_ASSUMPTION_FIELDS,
    deterministic_default_updates,
    sanitize_generated_assumptions,
)
from app.feasibility.hbu_agent import (
    _apply_bts_acquisition_cost_defaults,
    _bts_pricing_guidance,
    _construction_cost_guidance,
    _effective_storeys,
    _enforce_land_price_floor,
    _land_price_anchor_psqm,
    _normalize_bts_saleable_efficiency,
    build_assumptions_scaffold,
)
from app.feasibility.models import (
    BtrUnitConfig,
    FeasibilityAssumptions,
    FeasibilityPaymentPlan,
    FeasibilityUnitConfig,
    LandSaleEvidence,
    MarketPricingRow,
    OffPlanUnitPricingBenchmark,
    PlotDetails,
)


def _plot(
    max_height: str = "G+20",
    plot_area_sqm: float = 1000.0,
    max_gfa_sqm: float = 4000.0,
    max_coverage: str = "60%",
) -> PlotDetails:
    return PlotDetails.model_validate(
        {
            "plot_number": "L001",
            "community_name": "Business Bay",
            "project_name": "Business Bay Plot",
            "master_developer": None,
            "plot_area_sqm": plot_area_sqm,
            "max_gfa_sqm": max_gfa_sqm,
            "max_gfa_sqft": 43055.0,
            "max_height": max_height,
            "max_coverage": max_coverage,
            "gfa_type": "Residential",
            "far": 4.0,
            "inferred_usage": "residential",
            "site_plan_issue_date": None,
            "site_plan_expiry_date": None,
            "is_verified": True,
            "verify_comments": None,
            "land_use": [],
            "general_notes": [],
            "setbacks": {},
            "coordinates": [],
            "warnings": [],
        }
    )


def _scaffold(development_model="build_to_sell_residential"):
    return build_assumptions_scaffold(
        _plot(),
        "residential",
        land_price_anchor_psqm=12_000.0,
        development_model=development_model,
        generation_date=date(2026, 5, 3),
    )


def test_generated_defaults_preserve_market_fields_and_reset_deterministic_fields():
    scaffold = _scaffold()
    llm_assumptions = scaffold.model_copy(
        update={
            "landPricePsqm": 18_000.0,
            "landAcquisitionCostOverrideAed": 18_000_000.0,
            "constructionCostPsqmBua": 6_250.0,
            "unitConfigs": [
                FeasibilityUnitConfig(
                    id="onebr",
                    label="1BR",
                    units=80,
                    avgSizeSqm=72.0,
                    sellingRatePsqm=24_000.0,
                    parkingRatio=1.0,
                )
            ],
            "paymentPlan": FeasibilityPaymentPlan(
                depositPct=90.0, constructionPct=5.0, handoverPct=5.0
            ),
            "vatPct": 12.0,
            "landLoanSpreadBps": 999.0,
            "constructionLoanSpreadBps": 888.0,
            "debtSpreadPa": 0.0888,
            "acquisitionDebtLtv": 0.2,
            "constructionDebtLtc": 0.3,
            "landTransferFeePct": 0.12,
            "salesCommencementDate": "2040-01-01",
            "constructionDate": "2040-02-01",
            "handoverDate": "2045-01-01",
            "targetCoveragePct": 48.0,
            "targetBuildingCount": 2.0,
            "maxEfficientTowerFloorplateSqm": 1800.0,
            "minEfficientTowerFloorplateSqm": 800.0,
        }
    )

    sanitized = sanitize_generated_assumptions(
        llm_assumptions,
        scaffold=scaffold,
        generation_date=date(2026, 5, 3),
        development_model="build_to_sell_residential",
    )

    assert sanitized.landPricePsqm == 18_000.0
    assert sanitized.landAcquisitionCostOverrideAed == 18_000_000.0
    assert sanitized.constructionCostPsqmBua == 6_250.0
    assert sanitized.unitConfigs[0].sellingRatePsqm == 24_000.0
    assert sanitized.targetCoveragePct == scaffold.targetCoveragePct
    assert sanitized.targetBuildingCount == scaffold.targetBuildingCount
    assert sanitized.maxEfficientTowerFloorplateSqm == scaffold.maxEfficientTowerFloorplateSqm
    assert sanitized.minEfficientTowerFloorplateSqm == scaffold.minEfficientTowerFloorplateSqm
    assert sanitized.podiumFloors == scaffold.podiumFloors
    assert sanitized.residentialFloors == scaffold.residentialFloors
    assert sanitized.amenityRoofFloors == scaffold.amenityRoofFloors

    assert sanitized.paymentPlan == FeasibilityPaymentPlan(
        depositPct=10.0, constructionPct=30.0, handoverPct=60.0
    )
    assert sanitized.vatPct == 5.0
    assert sanitized.landLoanSpreadBps == 200.0
    assert sanitized.constructionLoanSpreadBps == 200.0
    assert sanitized.debtSpreadPa == 0.02
    assert sanitized.acquisitionDebtLtv == 0.7
    assert sanitized.constructionDebtLtc == 0.7
    assert sanitized.landTransferFeePct == 0.04
    assert sanitized.buaMultiplier == 1.5
    assert sanitized.designSupervisionPct == 6.0
    assert sanitized.marketingCostPct == 1.0
    assert sanitized.salesAgentFeePct == 5.0
    assert sanitized.contingencyPct == 5.0
    assert sanitized.midPointInflationPct == 4.0
    assert sanitized.infrastructureCostAed == 8_000_000.0
    assert sanitized.governmentFeesAed == 5_000_000.0
    assert sanitized.masterCommunityFeesAed == 3_500_000.0
    assert sanitized.landAcquisitionDate == "2026-05-03"
    assert sanitized.salesCommencementDate == "2026-08-03"
    assert sanitized.constructionDate == "2026-09-03"
    assert sanitized.preHandoverMilestoneDate == "2028-09-03"
    assert sanitized.handoverDate == "2029-03-03"


def test_bts_generation_cannot_set_finance_vat_payment_or_debt_sizing_defaults():
    scaffold = _scaffold()
    llm_assumptions = scaffold.model_copy(
        update={
            "paymentPlan": FeasibilityPaymentPlan(
                depositPct=25.0, constructionPct=50.0, handoverPct=25.0
            ),
            "vatPct": 0.0,
            "landLoanSpreadBps": 450.0,
            "constructionLoanSpreadBps": 550.0,
            "debtFundingAed": 999_000_000.0,
            "equityFundingAed": -20_000_000.0,
            "financingFeePct": 0.05,
            "exitFeePct": 0.04,
            "marketingCostPct": 0.0,
            "salesAgentFeePct": 0.0,
            "designSupervisionPct": 0.0,
            "contingencyPct": 0.0,
            "infrastructureCostAed": 0.0,
            "governmentFeesAed": 0.0,
            "masterCommunityFeesAed": 0.0,
        }
    )

    sanitized = sanitize_generated_assumptions(
        llm_assumptions,
        scaffold=scaffold,
        generation_date=date(2026, 5, 3),
        development_model="build_to_sell_residential",
    )

    assert sanitized.paymentPlan.depositPct == 10.0
    assert sanitized.paymentPlan.constructionPct == 30.0
    assert sanitized.paymentPlan.handoverPct == 60.0
    assert sanitized.vatPct == 5.0
    assert sanitized.landLoanSpreadBps == 200.0
    assert sanitized.constructionLoanSpreadBps == 200.0
    assert sanitized.debtFundingAed == 0.0
    assert sanitized.equityFundingAed == 0.0
    assert sanitized.financingFeePct == 0.01
    assert sanitized.exitFeePct == 0.01
    assert sanitized.marketingCostPct == 1.0
    assert sanitized.salesAgentFeePct == 5.0
    assert sanitized.designSupervisionPct == 6.0
    assert sanitized.contingencyPct == 5.0
    assert sanitized.infrastructureCostAed == 8_000_000.0
    assert sanitized.governmentFeesAed == 5_000_000.0
    assert sanitized.masterCommunityFeesAed == 3_500_000.0


def test_btr_generation_cannot_set_operating_exit_or_perm_debt_defaults():
    scaffold = _scaffold("build_to_rent_residential")
    btr_config = BtrUnitConfig(
        id="btr-1",
        label="1BR",
        units=120,
        avgSizeSqm=72.0,
        monthlyRentAed=8_500.0,
        parkingRatio=1.0,
    )
    llm_assumptions = scaffold.model_copy(
        update={
            "developmentModel": "build_to_rent_residential",
            "btrUnitConfigs": [btr_config],
            "btrHoldPeriodYears": 30.0,
            "btrPropertyManagementPct": 12.0,
            "btrRepairsMaintenancePsqm": 250.0,
            "btrExitCapRatePct": 4.5,
            "btrPermDebtSpreadBps": 500.0,
            "btrDscrMinimum": 0.95,
            "btrRefiCapRatePct": 5.0,
        }
    )

    sanitized = sanitize_generated_assumptions(
        llm_assumptions,
        scaffold=scaffold,
        generation_date=date(2026, 5, 3),
        development_model="build_to_rent_residential",
    )

    assert sanitized.btrUnitConfigs == [btr_config]
    assert sanitized.btrHoldPeriodYears == 10.0
    assert sanitized.btrStabilizedOccupancyPct == 97.0
    assert sanitized.btrFreeRentMonths == 0.0
    assert sanitized.btrAnnualRentGrowthPct == 5.0
    assert sanitized.btrMarketRentGrowthPct == 5.0
    assert sanitized.btrRenewalRentGrowthPct == 5.0
    assert sanitized.btrPropertyManagementPct == 5.0
    assert sanitized.btrRepairsMaintenancePsqm == 50.0
    assert sanitized.btrTerminalGrowthPct == 4.0
    assert sanitized.btrExitCapRatePct == 5.5
    assert sanitized.btrPermDebtSpreadBps == 165.0
    assert sanitized.btrDscrMinimum == 1.25
    assert sanitized.btrRefiCapRatePct == 5.5


def test_bts_acquisition_cost_defaults_are_set_from_final_land_cost():
    scaffold = _scaffold()
    assumptions = scaffold.model_copy(
        update={
            "landPricePsqm": 18_000.0,
            "landAcquisitionCostOverrideAed": 20_000_000.0,
            "brokerageFeeAed": 0.0,
            "legalDdCostAed": 0.0,
        }
    )

    updated = _apply_bts_acquisition_cost_defaults(assumptions)

    assert updated.brokerageFeeAed == 200_000.0
    assert updated.legalDdCostAed == 100_000.0


def test_land_cost_floor_still_applies_after_default_sanitization():
    scaffold = _scaffold()
    llm_assumptions = scaffold.model_copy(update={"landPricePsqm": 1_000.0})
    sanitized = sanitize_generated_assumptions(
        llm_assumptions,
        scaffold=scaffold,
        generation_date=date(2026, 5, 3),
        development_model="build_to_sell_residential",
    )
    land_sales = [
        LandSaleEvidence(
            transaction_id=f"tx-{index}",
            instance_date="2026-01-01",
            area_name="Business Bay",
            project_name="Land comp",
            procedure_name="Sale",
            property_usage="Residential",
            plot_area_sqm=1000.0,
            price_aed=price_sqm * 1000.0,
            price_sqm=price_sqm,
            price_per_gfa_sqm=price_sqm / 4.0,
        )
        for index, price_sqm in enumerate([8_000.0, 9_000.0, 10_000.0], start=1)
    ]

    bounded, warning = _enforce_land_price_floor(
        sanitized,
        land_sales,
        plot_area_sqm=1000.0,
        area_name="Business Bay",
        far=4.0,
    )

    assert bounded.landPricePsqm == 12_916.8
    assert bounded.landAcquisitionCostOverrideAed == 12_916_800.0
    assert warning is not None


def test_land_anchor_respects_gfa_market_floor_when_comps_are_low():
    scaffold = build_assumptions_scaffold(
        _plot(),
        "residential",
        land_price_anchor_psqm=0,
        development_model="build_to_sell_residential",
        generation_date=date(2026, 5, 3),
    )
    land_sales = [
        LandSaleEvidence(
            transaction_id=f"tx-{index}",
            instance_date="2026-01-01",
            area_name="Business Bay",
            project_name="Land comp",
            procedure_name="Sale",
            property_usage="Residential",
            plot_area_sqm=1000.0,
            price_aed=price_sqm * 1000.0,
            price_sqm=price_sqm,
            price_per_gfa_sqm=price_sqm / 4.0,
        )
        for index, price_sqm in enumerate([8_000.0, 9_000.0, 10_000.0], start=1)
    ]

    bounded, _ = _enforce_land_price_floor(
        scaffold,
        land_sales,
        plot_area_sqm=1000.0,
        area_name="Business Bay",
        far=4.0,
    )

    assert bounded.landPricePsqm == 12_916.8


def test_scaffold_uses_moderate_usage_and_storey_construction_seed():
    scaffold = build_assumptions_scaffold(
        _plot(max_height="G+30"),
        "residential",
        land_price_anchor_psqm=12_000.0,
        development_model="build_to_sell_residential",
        generation_date=date(2026, 5, 3),
    )

    assert scaffold.constructionCostPsqmBua == 5_200.0


def test_generated_construction_cost_is_not_forced_to_scaffold_seed():
    scaffold = build_assumptions_scaffold(
        _plot(max_height="G+30"),
        "residential",
        land_price_anchor_psqm=12_000.0,
        development_model="build_to_sell_residential",
        generation_date=date(2026, 5, 3),
    )
    generated = sanitize_generated_assumptions(
        scaffold.model_copy(update={"constructionCostPsqmBua": 4_700.0}),
        scaffold=scaffold,
        generation_date=date(2026, 5, 3),
        development_model="build_to_sell_residential",
    )

    assert generated.constructionCostPsqmBua == 4_700.0


def test_bts_unit_mix_above_saleable_efficiency_cap_is_scaled_to_target():
    scaffold = build_assumptions_scaffold(
        _plot(max_gfa_sqm=10_000.0),
        "residential",
        land_price_anchor_psqm=12_000.0,
        development_model="build_to_sell_residential",
        generation_date=date(2026, 5, 3),
    )
    assumptions = scaffold.model_copy(
        update={
            "unitConfigs": [
                FeasibilityUnitConfig(
                    id="studio",
                    label="Studio",
                    units=50,
                    avgSizeSqm=45.0,
                    sellingRatePsqm=25_000.0,
                    parkingRatio=1.0,
                ),
                FeasibilityUnitConfig(
                    id="onebr",
                    label="1BR",
                    units=50,
                    avgSizeSqm=75.0,
                    sellingRatePsqm=24_000.0,
                    parkingRatio=1.0,
                ),
                FeasibilityUnitConfig(
                    id="twobr",
                    label="2BR",
                    units=20,
                    avgSizeSqm=130.0,
                    sellingRatePsqm=23_000.0,
                    parkingRatio=1.0,
                ),
            ]
        }
    )

    normalized, warning = _normalize_bts_saleable_efficiency(assumptions)
    normalized_area = sum(row.units * row.avgSizeSqm for row in normalized.unitConfigs)

    assert normalized_area == 7990.0
    assert normalized_area / normalized.maxGfaSqm <= 0.82
    assert normalized_area / normalized.maxGfaSqm >= 0.79
    assert [row.label for row in normalized.unitConfigs] == ["Studio", "1BR", "2BR"]
    assert warning is not None
    assert "must not exceed 82%" in warning


def test_bts_unit_mix_inside_saleable_efficiency_cap_is_not_changed():
    scaffold = build_assumptions_scaffold(
        _plot(max_gfa_sqm=10_000.0),
        "residential",
        land_price_anchor_psqm=12_000.0,
        development_model="build_to_sell_residential",
        generation_date=date(2026, 5, 3),
    )
    assumptions = scaffold.model_copy(
        update={
            "unitConfigs": [
                FeasibilityUnitConfig(
                    id="onebr",
                    label="1BR",
                    units=108,
                    avgSizeSqm=75.0,
                    sellingRatePsqm=24_000.0,
                    parkingRatio=1.0,
                )
            ]
        }
    )

    normalized, warning = _normalize_bts_saleable_efficiency(assumptions)

    assert normalized.unitConfigs == assumptions.unitConfigs
    assert warning is None


def test_construction_cost_guidance_anchors_normal_tower_costs_without_area_rules():
    guidance = _construction_cost_guidance("residential", 30)

    assert "AED 5,200/sqm BUA scaffold benchmark" in guidance
    assert "AED 4,700-5,450/sqm BUA" in guidance
    assert "Business Bay" not in guidance


def test_bts_pricing_guidance_scales_to_high_far_scheme_size():
    plot = _plot(
        plot_area_sqm=5474.38,
        max_gfa_sqm=174657.7,
    ).model_copy(update={"far": 31.9})
    guidance = _bts_pricing_guidance(
        plot,
        [
            MarketPricingRow(
                unit_type="1br",
                transaction_count=919,
                median_price_sqm=20_377.0,
                avg_area_sqm=74.0,
            )
        ],
        [
            OffPlanUnitPricingBenchmark(
                unit_type="1br",
                selected_horizon_bucket="25-36m",
                avg_months_to_completion=32.3,
                transaction_count=1282,
                selected_price_sqm=25_752.0,
                confidence_score=85.0,
                confidence_label="high",
                sample_score=100.0,
                horizon_score=92.9,
                recency_score=37.5,
                note="Selected 25-36m for 1br with 1282 transactions.",
            )
        ],
    )

    assert "very large high-FAR" in guidance
    assert "10%-15%" in guidance
    assert "AED 21,889-23,177/sqm" in guidance


def test_unlimited_height_scaffold_infers_effective_storeys_from_gfa():
    plot = _plot(
        max_height="G+5P+UNLIMITED",
        plot_area_sqm=5474.38,
        max_gfa_sqm=174657.7,
        max_coverage="N/A",
    )
    scaffold = build_assumptions_scaffold(
        plot,
        "residential",
        land_price_anchor_psqm=70_000.0,
        development_model="build_to_sell_residential",
        generation_date=date(2026, 5, 3),
    )

    assert _effective_storeys(plot, "residential") == 77
    assert scaffold.maxStoreys == 77
    assert scaffold.numberOfFloors == 77
    assert scaffold.podiumFloors == 5.0
    assert scaffold.residentialFloors == 71.0
    assert scaffold.amenityRoofFloors == 1.0
    assert scaffold.constructionCostPsqmBua == 5_600.0
    assert scaffold.targetCoveragePct == 45.0
    assert scaffold.targetBuildingCount == 2.0
    assert scaffold.maxEfficientTowerFloorplateSqm == 2000.0


def test_generated_massing_fields_are_scaffold_owned():
    scaffold = build_assumptions_scaffold(
        _plot(max_height="G+30"),
        "residential",
        land_price_anchor_psqm=12_000.0,
        development_model="build_to_sell_residential",
        generation_date=date(2026, 5, 3),
    )
    sanitized = sanitize_generated_assumptions(
        scaffold.model_copy(
            update={
                "targetCoveragePct": 0.0,
                "targetBuildingCount": 0.0,
                "maxEfficientTowerFloorplateSqm": 0.0,
                "minEfficientTowerFloorplateSqm": 0.0,
                "podiumFloors": 0.0,
                "residentialFloors": 0.0,
                "amenityRoofFloors": 0.0,
            }
        ),
        scaffold=scaffold,
        generation_date=date(2026, 5, 3),
        development_model="build_to_sell_residential",
    )

    assert sanitized.targetCoveragePct == scaffold.targetCoveragePct
    assert sanitized.targetBuildingCount == scaffold.targetBuildingCount
    assert sanitized.maxEfficientTowerFloorplateSqm == scaffold.maxEfficientTowerFloorplateSqm
    assert sanitized.minEfficientTowerFloorplateSqm == scaffold.minEfficientTowerFloorplateSqm
    assert sanitized.podiumFloors == scaffold.podiumFloors
    assert sanitized.residentialFloors == scaffold.residentialFloors
    assert sanitized.amenityRoofFloors == scaffold.amenityRoofFloors


def test_generated_positive_massing_values_do_not_override_scaffold():
    scaffold = build_assumptions_scaffold(
        _plot(max_height="G+30"),
        "residential",
        land_price_anchor_psqm=12_000.0,
        development_model="build_to_sell_residential",
        generation_date=date(2026, 5, 3),
    )
    sanitized = sanitize_generated_assumptions(
        scaffold.model_copy(
            update={
                "targetCoveragePct": 0.45,
                "targetBuildingCount": 9.0,
                "maxEfficientTowerFloorplateSqm": 9999.0,
                "minEfficientTowerFloorplateSqm": 999.0,
                "podiumFloors": 1.0,
                "residentialFloors": 1.0,
                "amenityRoofFloors": 9.0,
            }
        ),
        scaffold=scaffold,
        generation_date=date(2026, 5, 3),
        development_model="build_to_sell_residential",
    )

    assert sanitized.targetCoveragePct == scaffold.targetCoveragePct
    assert sanitized.targetBuildingCount == scaffold.targetBuildingCount
    assert sanitized.maxEfficientTowerFloorplateSqm == scaffold.maxEfficientTowerFloorplateSqm
    assert sanitized.minEfficientTowerFloorplateSqm == scaffold.minEfficientTowerFloorplateSqm
    assert sanitized.podiumFloors == scaffold.podiumFloors
    assert sanitized.residentialFloors == scaffold.residentialFloors
    assert sanitized.amenityRoofFloors == scaffold.amenityRoofFloors


def test_land_anchor_uses_upper_gfa_band_for_very_high_far_plots():
    land_sales = [
        LandSaleEvidence(
            transaction_id="low-dev-reg",
            instance_date="2026-01-01",
            area_name="Business Bay",
            project_name="Land comp",
            procedure_name="Development Registration",
            property_usage="Residential",
            plot_area_sqm=5000.0,
            price_aed=45_000_000.0,
            price_sqm=9_000.0,
            price_per_gfa_sqm=282.0,
        )
    ]

    assert _land_price_anchor_psqm(land_sales, "Business Bay", 31.9) == 171_685.8


def test_generated_assumption_fields_are_classified_for_defaults_or_preservation():
    scaffold_fields = {
        "plotAreaSqm",
        "maxGfaSqm",
        "maxCoveragePct",
        "maxStoreys",
        "maxFar",
        "numberOfTowers",
        "numberOfFloors",
    }
    explicitly_updated_fields = {
        *deterministic_default_updates(date(2026, 5, 3)).keys(),
        *MARKET_ASSUMPTION_FIELDS,
        *PROJECT_PHYSICAL_ASSUMPTION_FIELDS,
        *scaffold_fields,
    }

    assert set(FeasibilityAssumptions.model_fields) - explicitly_updated_fields == set()
