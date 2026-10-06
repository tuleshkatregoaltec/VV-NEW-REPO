-- ClickHouse schema for active Holocron sources
-- This file contains bronze tables for active Holocron sources.

CREATE TABLE IF NOT EXISTS dda_land_plots (
    plot_number           String,
    old_numbers           String DEFAULT '',
    project_name          String DEFAULT '',
    community_name        LowCardinality(String) DEFAULT '',
    master_developer      String DEFAULT '',
    plot_area_sqm         Float64 DEFAULT 0,
    plot_area_sqft        Float64 DEFAULT 0,
    max_gfa_sqm           Float64 DEFAULT 0,
    max_gfa_sqft          Float64 DEFAULT 0,
    max_height            String DEFAULT '',
    max_coverage          String DEFAULT '',
    site_plan_issue_date  Nullable(Date),
    site_plan_expiry_date Nullable(Date),
    side1_building        String DEFAULT '',
    side1_podium          String DEFAULT '',
    side2_building        String DEFAULT '',
    side2_podium          String DEFAULT '',
    side3_building        String DEFAULT '',
    side3_podium          String DEFAULT '',
    side4_building        String DEFAULT '',
    side4_podium          String DEFAULT '',
    land_use              String DEFAULT '',
    general_notes         String DEFAULT '',
    coordinates           String DEFAULT '',
    landuse_symbols       String DEFAULT '',
    gfa_type              LowCardinality(String) DEFAULT '',
    is_verified           UInt8 DEFAULT 0,
    verify_comments       String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY plot_number;

CREATE TABLE IF NOT EXISTS dda_project_areas (
    object_id    Int32,
    project_name String DEFAULT '',
    rings        String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY object_id;

CREATE TABLE IF NOT EXISTS dda_subproject_areas (
    object_id            Int32,
    project_id           String DEFAULT '',
    project_name         String DEFAULT '',
    entity_name          String DEFAULT '',
    developer_name       String DEFAULT '',
    master_project_name  String DEFAULT '',
    original_plot_number String DEFAULT '',
    project_logo         String DEFAULT '',
    rings                String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY object_id;

CREATE TABLE IF NOT EXISTS dda_plot_building_limits (
    object_id   Int32,
    plot_number String,
    rings       String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (plot_number, object_id);

CREATE TABLE IF NOT EXISTS dda_plot_podium_limits (
    object_id   Int32,
    plot_number String,
    max_height  String DEFAULT '',
    rings       String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (plot_number, object_id);

CREATE TABLE IF NOT EXISTS dda_plot_features (
    object_id           Int32,
    plot_number         String,
    feature_type_code   Int32 DEFAULT 0,
    feature_type_label  LowCardinality(String) DEFAULT '',
    feature_area_sqm    Float64 DEFAULT 0,
    feature_perimeter_m Float64 DEFAULT 0,
    rings               String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (plot_number, object_id);

CREATE TABLE IF NOT EXISTS dda_frozen_plots (
    object_id        Int32,
    plot_number      String,
    old_plot_numbers String DEFAULT '',
    is_frozen        UInt8 DEFAULT 0,
    plot_area_sqm    Float64 DEFAULT 0,
    plot_perimeter_m Float64 DEFAULT 0,
    gfa_type         LowCardinality(String) DEFAULT '',
    gfa_sqm_t        String DEFAULT '',
    gfa_sqft_t       String DEFAULT '',
    rings            String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (plot_number, object_id);

CREATE TABLE IF NOT EXISTS dda_landuse_symbols (
    object_id         Int32,
    landuse           String DEFAULT '',
    landuse_character String DEFAULT '',
    landuse_id        String DEFAULT '',
    lat               Float64 DEFAULT 0,
    lng               Float64 DEFAULT 0
) ENGINE = MergeTree()
ORDER BY object_id;

CREATE TABLE IF NOT EXISTS dda_plot_built_to_lines (
    object_id   Int32,
    plot_number String,
    paths       String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (plot_number, object_id);

CREATE TABLE IF NOT EXISTS dda_plot_arcades (
    object_id   Int32,
    plot_number String,
    rings       String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (plot_number, object_id);

CREATE TABLE IF NOT EXISTS dda_plot_retail (
    object_id   Int32,
    plot_number String,
    rings       String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (plot_number, object_id);

CREATE TABLE IF NOT EXISTS dxbi_transactions_bronze (
    transaction_key String,
    source_table    LowCardinality(String),
    cells_json      String DEFAULT '',
    cells_count     UInt16 DEFAULT 0,
    run_id          String,
    scraped_at      String DEFAULT '',
    slice_start_date Date,
    slice_end_date   Date,
    source_url      String DEFAULT '',
    page_number     UInt32 DEFAULT 0,
    row_number      UInt32 DEFAULT 0
) ENGINE = MergeTree()
ORDER BY (slice_start_date, source_table, transaction_key);

CREATE TABLE IF NOT EXISTS dxbi_rental_events (
    event_key          String,
    unit_candidate_key String,
    unit_cohort_key    String,
    location_name      String DEFAULT '',
    building_name      String DEFAULT '',
    project_name       String DEFAULT '',
    area_name          LowCardinality(String) DEFAULT '',
    property_type      LowCardinality(String) DEFAULT '',
    bedrooms           LowCardinality(String) DEFAULT '',
    size_sqft          Float64 DEFAULT 0,
    contract_amount_aed UInt64 DEFAULT 0,
    contract_term_days UInt32 DEFAULT 0,
    contract_term_months Float32 DEFAULT 0,
    annual_rent_aed    UInt64 DEFAULT 0,
    rent_normalization_version UInt8 DEFAULT 1,
    address_normalization_version UInt8 DEFAULT 3,
    purchase_price_aed UInt64 DEFAULT 0,
    lease_start        Date,
    lease_end          Date,
    contract_state     LowCardinality(String) DEFAULT '',
    source_account     LowCardinality(String) DEFAULT '',
    source_shard_date  Date,
    source_file        String DEFAULT '',
    scraped_at         DateTime64(3, 'UTC'),
    loaded_at          DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(loaded_at)
ORDER BY (lease_start, unit_candidate_key, event_key);

CREATE TABLE IF NOT EXISTS dxbi_rental_unit_candidates (
    unit_candidate_key String,
    event_key          String,
    unit_cohort_key    String,
    location_name      String DEFAULT '',
    building_name      String DEFAULT '',
    project_name       String DEFAULT '',
    area_name          LowCardinality(String) DEFAULT '',
    property_type      LowCardinality(String) DEFAULT '',
    bedrooms           LowCardinality(String) DEFAULT '',
    size_sqft          Float64 DEFAULT 0,
    contract_amount_aed UInt64 DEFAULT 0,
    contract_term_days UInt32 DEFAULT 0,
    contract_term_months Float32 DEFAULT 0,
    annual_rent_aed    UInt64 DEFAULT 0,
    rent_normalization_version UInt8 DEFAULT 1,
    address_normalization_version UInt8 DEFAULT 3,
    purchase_price_aed UInt64 DEFAULT 0,
    lease_start        Date,
    lease_end          Date,
    contract_state     LowCardinality(String) DEFAULT '',
    observed_contracts UInt32 DEFAULT 0,
    last_scraped_at    DateTime64(3, 'UTC'),
    loaded_at          DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(loaded_at)
ORDER BY unit_candidate_key;

-- Shadow rental tables retain source identity and true row multiplicity. The
-- event_key alias preserves the current backend contract for the v2 cutover.
CREATE TABLE IF NOT EXISTS dxbi_rental_events_v2 (
    contract_key       String,
    event_key          String ALIAS contract_key,
    source_contract_id String DEFAULT '',
    unit_number        String DEFAULT '',
    occurrence_index   UInt16 DEFAULT 1,
    source_cohort_size  UInt32 DEFAULT 0,
    unit_candidate_key String,
    unit_cohort_key    String,
    location_name      String DEFAULT '',
    building_name      String DEFAULT '',
    project_name       String DEFAULT '',
    area_name          LowCardinality(String) DEFAULT '',
    property_type      LowCardinality(String) DEFAULT '',
    bedrooms           LowCardinality(String) DEFAULT '',
    size_sqft          Float64 DEFAULT 0,
    contract_amount_aed UInt64 DEFAULT 0,
    contract_term_days UInt32 DEFAULT 0,
    contract_term_months Float32 DEFAULT 0,
    annual_rent_aed    UInt64 DEFAULT 0,
    rent_normalization_version UInt8 DEFAULT 2,
    address_normalization_version UInt8 DEFAULT 5,
    purchase_price_aed UInt64 DEFAULT 0,
    lease_start        Date,
    lease_end          Date,
    contract_state     LowCardinality(String) DEFAULT '',
    source_account     LowCardinality(String),
    source_run_id      String,
    report_type        LowCardinality(String) DEFAULT 'rentals',
    filter_profile_id  LowCardinality(String),
    source_location_id String,
    source_location_text String DEFAULT '',
    source_location_slug String DEFAULT '',
    configuration_hash FixedString(20),
    raw_row_fingerprint FixedString(64),
    raw_attributes_json String DEFAULT '{}',
    source_shard_date  Date,
    source_file        String DEFAULT '',
    scraped_at         DateTime64(3, 'UTC'),
    loaded_at          DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(loaded_at)
ORDER BY (lease_start, contract_key);

CREATE TABLE IF NOT EXISTS dxbi_rental_unit_candidates_v2 (
    contract_key       String,
    event_key          String ALIAS contract_key,
    unit_candidate_key String,
    unit_cohort_key    String,
    source_contract_id String DEFAULT '',
    unit_number        String DEFAULT '',
    location_name      String DEFAULT '',
    building_name      String DEFAULT '',
    project_name       String DEFAULT '',
    area_name          LowCardinality(String) DEFAULT '',
    property_type      LowCardinality(String) DEFAULT '',
    bedrooms           LowCardinality(String) DEFAULT '',
    size_sqft          Float64 DEFAULT 0,
    contract_amount_aed UInt64 DEFAULT 0,
    contract_term_days UInt32 DEFAULT 0,
    contract_term_months Float32 DEFAULT 0,
    annual_rent_aed    UInt64 DEFAULT 0,
    rent_normalization_version UInt8 DEFAULT 2,
    address_normalization_version UInt8 DEFAULT 5,
    purchase_price_aed UInt64 DEFAULT 0,
    lease_start        Date,
    lease_end          Date,
    contract_state     LowCardinality(String) DEFAULT '',
    observed_contracts UInt32 DEFAULT 0,
    last_scraped_at    DateTime64(3, 'UTC'),
    loaded_at          DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(loaded_at)
ORDER BY (contract_key, unit_candidate_key);

CREATE TABLE IF NOT EXISTS dxbi_rental_run_reconciliation (
    run_id               String,
    report_type          LowCardinality(String),
    status               LowCardinality(String),
    raw_rows             UInt64,
    unique_source_rows   UInt64,
    normalized_rows      UInt64,
    quarantined_rows     UInt64,
    profile_overlap_rows UInt64,
    loaded_contracts     UInt64,
    out_of_scope_rows    UInt64,
    expected_partitions  UInt32,
    completed_partitions UInt32,
    failed_partitions    UInt32,
    manifest_hash        String DEFAULT '',
    details_json         String DEFAULT '{}',
    started_at           DateTime64(3, 'UTC'),
    finished_at          DateTime64(3, 'UTC'),
    loaded_at            DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(loaded_at)
ORDER BY (report_type, run_id);

CREATE OR REPLACE VIEW dxbi_rental_ingestion_health AS
SELECT
    latest_run_id,
    latest_status,
    latest_finished_at,
    dateDiff('hour', latest_finished_at, now64(3)) AS age_hours,
    latest_quarantined_rows,
    latest_expected_partitions,
    latest_completed_partitions,
    toUInt8(
        latest_status = 'success'
        AND latest_quarantined_rows = 0
        AND latest_completed_partitions = latest_expected_partitions
        AND dateDiff('hour', latest_finished_at, now64(3)) <= 36
    ) AS healthy
FROM (
    SELECT
        argMax(run_id, finished_at) AS latest_run_id,
        argMax(status, finished_at) AS latest_status,
        max(finished_at) AS latest_finished_at,
        argMax(quarantined_rows, finished_at) AS latest_quarantined_rows,
        argMax(expected_partitions, finished_at) AS latest_expected_partitions,
        argMax(completed_partitions, finished_at) AS latest_completed_partitions
    FROM dxbi_rental_run_reconciliation FINAL
    WHERE report_type = 'rentals'
);

CREATE TABLE IF NOT EXISTS dxbi_sales_unit_events (
    sale_key           String,
    transaction_date   Date,
    unit_number        String,
    building_name      String DEFAULT '',
    building_key       String DEFAULT '',
    project_name       String DEFAULT '',
    area_name          LowCardinality(String) DEFAULT '',
    area_key           String DEFAULT '',
    address_normalization_version UInt8 DEFAULT 3,
    property_type      LowCardinality(String) DEFAULT '',
    market_status      LowCardinality(String) DEFAULT '',
    bedrooms           LowCardinality(String) DEFAULT '',
    size_sqft          Float64 DEFAULT 0,
    size_key           UInt32 DEFAULT 0,
    built_up_area_sqft Nullable(Float64),
    balcony_sqft       Nullable(Float64),
    sale_amount_aed    UInt64 DEFAULT 0,
    price_per_sqft_aed Nullable(Float64),
    capital_gain_pct   Nullable(Float64),
    ltv_pct            Nullable(Float64),
    seller_type        LowCardinality(String) DEFAULT '',
    seller_transaction_count Nullable(UInt16),
    agent_side         LowCardinality(String) DEFAULT '',
    detail_url         String DEFAULT '',
    source_file        String DEFAULT '',
    loaded_at          DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(loaded_at)
ORDER BY (building_key, bedrooms, size_key, transaction_date, sale_key);

CREATE TABLE IF NOT EXISTS dxbi_rental_sale_matches (
    unit_candidate_key             String,
    unit_number                    String DEFAULT '',
    identity_sale_date             Nullable(Date),
    identity_sale_price            Nullable(UInt64),
    last_purchase_date             Date,
    matched_sale_price             UInt64 DEFAULT 0,
    latest_property_type           LowCardinality(String) DEFAULT '',
    latest_price_per_sqft_aed      Nullable(Float64),
    latest_capital_gain_pct        Nullable(Float64),
    latest_ltv_pct                 Nullable(Float64),
    latest_seller_type             LowCardinality(String) DEFAULT '',
    latest_seller_transaction_count Nullable(UInt16),
    latest_market_status           LowCardinality(String) DEFAULT '',
    latest_detail_url              String DEFAULT '',
    matching_sales                 UInt32 DEFAULT 0,
    matching_units                 UInt32 DEFAULT 0,
    match_status                   LowCardinality(String) DEFAULT '',
    loaded_at                      DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(loaded_at)
ORDER BY unit_candidate_key;

CREATE TABLE IF NOT EXISTS dxbi_heatmap_rental_buildings_bronze (
    rental_key    String,
    run_id        String,
    scraped_at    String DEFAULT '',
    location_id   String DEFAULT '',
    property_type LowCardinality(String) DEFAULT '',
    bedrooms      LowCardinality(String) DEFAULT '',
    query_json    String DEFAULT '',
    raw_json      String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (location_id, property_type, bedrooms, rental_key);

CREATE TABLE IF NOT EXISTS dxbi_heatmap_buildings_bronze (
    response_key String,
    run_id       String,
    scraped_at   String DEFAULT '',
    location_id  String DEFAULT '',
    endpoint     LowCardinality(String) DEFAULT '',
    status       UInt16 DEFAULT 0,
    request_url  String DEFAULT '',
    content_type String DEFAULT '',
    seed_json    String DEFAULT '',
    payload_json String DEFAULT '',
    text         String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (location_id, endpoint, response_key);

CREATE TABLE IF NOT EXISTS dxbi_heatmap_building_statuses_bronze (
    response_key String,
    run_id       String,
    scraped_at   String DEFAULT '',
    location_id  String DEFAULT '',
    endpoint     LowCardinality(String) DEFAULT '',
    status       UInt16 DEFAULT 0,
    request_url  String DEFAULT '',
    content_type String DEFAULT '',
    seed_json    String DEFAULT '',
    payload_json String DEFAULT '',
    text         String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (location_id, endpoint, response_key);

CREATE TABLE IF NOT EXISTS dxbi_heatmap_chessboards_bronze (
    response_key String,
    run_id       String,
    scraped_at   String DEFAULT '',
    location_id  String DEFAULT '',
    endpoint     LowCardinality(String) DEFAULT '',
    status       UInt16 DEFAULT 0,
    request_url  String DEFAULT '',
    content_type String DEFAULT '',
    seed_json    String DEFAULT '',
    payload_json String DEFAULT '',
    text         String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (location_id, endpoint, response_key);

CREATE TABLE IF NOT EXISTS dxbi_fam_map_buildings_bronze (
    response_key String,
    run_id       String,
    scraped_at   String DEFAULT '',
    location_id  String DEFAULT '',
    endpoint     LowCardinality(String) DEFAULT '',
    status       UInt16 DEFAULT 0,
    request_url  String DEFAULT '',
    content_type String DEFAULT '',
    seed_json    String DEFAULT '',
    payload_json String DEFAULT '',
    text         String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (location_id, endpoint, response_key);

CREATE TABLE IF NOT EXISTS dxbi_heatmap_errors_bronze (
    error_key         String,
    run_id            String,
    scraped_at        String DEFAULT '',
    location_id       String DEFAULT '',
    endpoint          LowCardinality(String) DEFAULT '',
    status            UInt16 DEFAULT 0,
    request_url       String DEFAULT '',
    request_body_json String DEFAULT '',
    content_type      String DEFAULT '',
    payload_json      String DEFAULT '',
    text              String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (endpoint, location_id, error_key);

CREATE TABLE IF NOT EXISTS dld_od_transactions_bronze (
    row_key              String,
    run_id               String,
    scraped_at           String DEFAULT '',
    mode                 LowCardinality(String) DEFAULT '',
    date_window_start    Nullable(Date),
    date_window_end      Nullable(Date),
    page_index           UInt32 DEFAULT 0,
    row_index            UInt64 DEFAULT 0,
    transaction_number   String DEFAULT '',
    instance_date        DateTime DEFAULT toDateTime(0),
    group_id             UInt32 DEFAULT 0,
    group_en             LowCardinality(String) DEFAULT '',
    group_ar             String DEFAULT '',
    procedure_id         UInt32 DEFAULT 0,
    procedure_en         LowCardinality(String) DEFAULT '',
    procedure_ar         String DEFAULT '',
    procedure_area       Float64 DEFAULT 0,
    actual_area          Float64 DEFAULT 0,
    trans_value          Int64 DEFAULT 0,
    total_buyer          UInt32 DEFAULT 0,
    total_seller         UInt32 DEFAULT 0,
    property_id          UInt32 DEFAULT 0,
    property_type_id     UInt32 DEFAULT 0,
    prop_type_en         LowCardinality(String) DEFAULT '',
    prop_type_ar         String DEFAULT '',
    property_sub_type_id UInt32 DEFAULT 0,
    prop_sb_type_en      LowCardinality(String) DEFAULT '',
    prop_sb_type_ar      String DEFAULT '',
    usage_id             UInt32 DEFAULT 0,
    usage_en             LowCardinality(String) DEFAULT '',
    usage_ar             String DEFAULT '',
    rooms_en             LowCardinality(String) DEFAULT '',
    rooms_ar             String DEFAULT '',
    parking              String DEFAULT '',
    building_age         UInt32 DEFAULT 0,
    parcel_id            String DEFAULT '',
    area_id              UInt32 DEFAULT 0,
    area_en              LowCardinality(String) DEFAULT '',
    area_ar              String DEFAULT '',
    project_en           String DEFAULT '',
    project_ar           String DEFAULT '',
    master_project_en    String DEFAULT '',
    master_project_ar    String DEFAULT '',
    is_free_hold         UInt8 DEFAULT 0,
    is_free_hold_en      LowCardinality(String) DEFAULT '',
    is_free_hold_ar      String DEFAULT '',
    is_offplan           UInt8 DEFAULT 0,
    is_offplan_en        LowCardinality(String) DEFAULT '',
    is_offplan_ar        String DEFAULT '',
    nearest_metro_en     String DEFAULT '',
    nearest_metro_ar     String DEFAULT '',
    nearest_mall_en      String DEFAULT '',
    nearest_mall_ar      String DEFAULT '',
    nearest_landmark_en  String DEFAULT '',
    nearest_landmark_ar  String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (instance_date, transaction_number);

CREATE TABLE IF NOT EXISTS dld_od_rents_bronze (
    row_key                    String,
    run_id                     String,
    scraped_at                 String DEFAULT '',
    mode                       LowCardinality(String) DEFAULT '',
    date_window_start          Nullable(Date),
    date_window_end            Nullable(Date),
    page_index                 UInt32 DEFAULT 0,
    row_index                  UInt64 DEFAULT 0,
    contract_number            String DEFAULT '',
    registration_date          DateTime DEFAULT toDateTime(0),
    start_date                 DateTime DEFAULT toDateTime(0),
    end_date                   DateTime DEFAULT toDateTime(0),
    property_id                UInt32 DEFAULT 0,
    land_property_id           UInt32 DEFAULT 0,
    ejari_property_type_id     UInt32 DEFAULT 0,
    ejari_property_sub_type_id UInt32 DEFAULT 0,
    prop_type_en               LowCardinality(String) DEFAULT '',
    prop_type_ar               String DEFAULT '',
    prop_sub_type_en           LowCardinality(String) DEFAULT '',
    prop_sub_type_ar           String DEFAULT '',
    property_usage_id          UInt32 DEFAULT 0,
    usage_en                   LowCardinality(String) DEFAULT '',
    usage_ar                   String DEFAULT '',
    rooms                      String DEFAULT '',
    parking                    String DEFAULT '',
    actual_area                Float64 DEFAULT 0,
    annual_amount              Int64 DEFAULT 0,
    contract_amount            Int64 DEFAULT 0,
    total_properties           UInt32 DEFAULT 0,
    version_number             UInt32 DEFAULT 0,
    version_en                 LowCardinality(String) DEFAULT '',
    version_ar                 String DEFAULT '',
    parcel_id                  String DEFAULT '',
    area_id                    UInt32 DEFAULT 0,
    area_en                    LowCardinality(String) DEFAULT '',
    area_ar                    String DEFAULT '',
    project_en                 String DEFAULT '',
    project_ar                 String DEFAULT '',
    master_project_en          String DEFAULT '',
    master_project_ar          String DEFAULT '',
    is_free_hold               UInt8 DEFAULT 0,
    is_free_hold_en            LowCardinality(String) DEFAULT '',
    is_free_hold_ar            String DEFAULT '',
    nearest_metro_en           String DEFAULT '',
    nearest_metro_ar           String DEFAULT '',
    nearest_mall_en            String DEFAULT '',
    nearest_mall_ar            String DEFAULT '',
    nearest_landmark_en        String DEFAULT '',
    nearest_landmark_ar        String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (registration_date, contract_number);

CREATE TABLE IF NOT EXISTS dld_od_projects_bronze (
    row_key               String,
    run_id                String,
    scraped_at            String DEFAULT '',
    mode                  LowCardinality(String) DEFAULT '',
    date_window_start     Nullable(Date),
    date_window_end       Nullable(Date),
    page_index            UInt32 DEFAULT 0,
    row_index             UInt64 DEFAULT 0,
    project_number        UInt32 DEFAULT 0,
    project_en            String DEFAULT '',
    project_ar            String DEFAULT '',
    adoption_date         DateTime DEFAULT toDateTime(0),
    start_date            Nullable(DateTime),
    end_date              Nullable(DateTime),
    completion_date       Nullable(DateTime),
    inspection_date       Nullable(DateTime),
    project_status        LowCardinality(String) DEFAULT '',
    prj_type_en           LowCardinality(String) DEFAULT '',
    prj_type_ar           String DEFAULT '',
    percent_completed     Float64 DEFAULT 0,
    project_value         Int64 DEFAULT 0,
    escrow_account_number String DEFAULT '',
    cnt_total             UInt32 DEFAULT 0,
    cnt_unit              UInt32 DEFAULT 0,
    cnt_building          UInt32 DEFAULT 0,
    cnt_villa             UInt32 DEFAULT 0,
    cnt_land              UInt32 DEFAULT 0,
    developer_number      UInt32 DEFAULT 0,
    developer_en          String DEFAULT '',
    developer_ar          String DEFAULT '',
    area_en               LowCardinality(String) DEFAULT '',
    area_ar               String DEFAULT '',
    zone_en               LowCardinality(String) DEFAULT '',
    zone_ar               String DEFAULT '',
    master_project_en     String DEFAULT '',
    master_project_ar     String DEFAULT '',
    description_en        String DEFAULT '',
    description_ar        String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (project_number);

CREATE TABLE IF NOT EXISTS dld_od_valuations_bronze (
    row_key              String,
    run_id               String,
    scraped_at           String DEFAULT '',
    mode                 LowCardinality(String) DEFAULT '',
    date_window_start    Nullable(Date),
    date_window_end      Nullable(Date),
    page_index           UInt32 DEFAULT 0,
    row_index            UInt64 DEFAULT 0,
    procedure_number     UInt32 DEFAULT 0,
    procedure_year       UInt32 DEFAULT 0,
    instance_date        DateTime DEFAULT toDateTime(0),
    property_id          UInt32 DEFAULT 0,
    property_type_id     UInt32 DEFAULT 0,
    property_type_en     LowCardinality(String) DEFAULT '',
    property_type_ar     String DEFAULT '',
    property_sub_type_id UInt32 DEFAULT 0,
    prop_sub_type_en     LowCardinality(String) DEFAULT '',
    prop_sub_type_ar     String DEFAULT '',
    actual_area          Float64 DEFAULT 0,
    procedure_area       Float64 DEFAULT 0,
    actual_worth         Int64 DEFAULT 0,
    property_total_value Int64 DEFAULT 0,
    row_status_code      LowCardinality(String) DEFAULT '',
    area_id              UInt32 DEFAULT 0,
    area_en              LowCardinality(String) DEFAULT '',
    area_ar              String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (instance_date, procedure_year, procedure_number);

CREATE TABLE IF NOT EXISTS dld_od_lands_bronze (
    row_key                 String,
    run_id                  String,
    scraped_at              String DEFAULT '',
    mode                    LowCardinality(String) DEFAULT '',
    date_window_start       Nullable(Date),
    date_window_end         Nullable(Date),
    page_index              UInt32 DEFAULT 0,
    row_index               UInt64 DEFAULT 0,
    land_number             String DEFAULT '',
    land_sub_number         String DEFAULT '',
    parcel_id               String DEFAULT '',
    municipality_number     String DEFAULT '',
    dm_zip_code             String DEFAULT '',
    land_type_id            UInt32 DEFAULT 0,
    land_type_en            LowCardinality(String) DEFAULT '',
    land_type_ar            String DEFAULT '',
    actual_area             Float64 DEFAULT 0,
    is_free_hold            UInt8 DEFAULT 0,
    is_free_hold_en         LowCardinality(String) DEFAULT '',
    is_free_hold_ar         String DEFAULT '',
    is_offplan_en           LowCardinality(String) DEFAULT '',
    is_offplan_ar           String DEFAULT '',
    is_registered           UInt8 DEFAULT 0,
    prop_sub_type_en        LowCardinality(String) DEFAULT '',
    prop_sub_type_ar        String DEFAULT '',
    area_id                 UInt32 DEFAULT 0,
    area_en                 LowCardinality(String) DEFAULT '',
    area_ar                 String DEFAULT '',
    zone_id                 UInt32 DEFAULT 0,
    zone_en                 LowCardinality(String) DEFAULT '',
    zone_ar                 String DEFAULT '',
    master_project_id       UInt32 DEFAULT 0,
    master_project_en       String DEFAULT '',
    master_project_ar       String DEFAULT '',
    project_number          String DEFAULT '',
    project_en              String DEFAULT '',
    project_ar              String DEFAULT '',
    pre_registration_number String DEFAULT '',
    separated_from          String DEFAULT '',
    separated_reference     String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (land_number);

CREATE TABLE IF NOT EXISTS dld_od_buildings_bronze (
    row_key                 String,
    run_id                  String,
    scraped_at              String DEFAULT '',
    mode                    LowCardinality(String) DEFAULT '',
    date_window_start       Nullable(Date),
    date_window_end         Nullable(Date),
    page_index              UInt32 DEFAULT 0,
    row_index               UInt64 DEFAULT 0,
    building_number         String DEFAULT '',
    parent_property_id      UInt32 DEFAULT 0,
    parcel_id               String DEFAULT '',
    creation_date           DateTime DEFAULT toDateTime(0),
    land_number             String DEFAULT '',
    land_sub_number         UInt32 DEFAULT 0,
    land_type_id            UInt32 DEFAULT 0,
    land_type_en            LowCardinality(String) DEFAULT '',
    land_type_ar            String DEFAULT '',
    prop_sub_type_id        UInt32 DEFAULT 0,
    prop_sub_type_en        LowCardinality(String) DEFAULT '',
    prop_sub_type_ar        String DEFAULT '',
    actual_area             Float64 DEFAULT 0,
    built_up_area           Float64 DEFAULT 0,
    common_area             Float64 DEFAULT 0,
    actual_common_area      Float64 DEFAULT 0,
    floors                  UInt32 DEFAULT 0,
    bld_levels              UInt32 DEFAULT 0,
    flats                   UInt32 DEFAULT 0,
    rooms                   UInt32 DEFAULT 0,
    rooms_en                LowCardinality(String) DEFAULT '',
    rooms_ar                String DEFAULT '',
    offices                 UInt32 DEFAULT 0,
    shops                   UInt32 DEFAULT 0,
    car_parks               UInt32 DEFAULT 0,
    elevators               UInt32 DEFAULT 0,
    swimming_pools          UInt32 DEFAULT 0,
    is_free_hold            UInt8 DEFAULT 0,
    is_free_hold_en         LowCardinality(String) DEFAULT '',
    is_free_hold_ar         String DEFAULT '',
    is_lease_hold           UInt8 DEFAULT 0,
    is_lease_hold_en        LowCardinality(String) DEFAULT '',
    is_lease_hold_ar        String DEFAULT '',
    is_offplan_en           LowCardinality(String) DEFAULT '',
    is_offplan_ar           String DEFAULT '',
    is_registered           UInt8 DEFAULT 0,
    pre_registration_number String DEFAULT '',
    area_id                 UInt32 DEFAULT 0,
    area_en                 LowCardinality(String) DEFAULT '',
    area_ar                 String DEFAULT '',
    zone_id                 UInt32 DEFAULT 0,
    zone_en                 LowCardinality(String) DEFAULT '',
    zone_ar                 String DEFAULT '',
    master_project_id       UInt32 DEFAULT 0,
    master_project_en       String DEFAULT '',
    master_project_ar       String DEFAULT '',
    project_number          String DEFAULT '',
    project_en              String DEFAULT '',
    project_ar              String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (building_number);

CREATE TABLE IF NOT EXISTS dld_od_units_bronze (
    row_key                 String,
    run_id                  String,
    scraped_at              String DEFAULT '',
    mode                    LowCardinality(String) DEFAULT '',
    category                LowCardinality(String) DEFAULT '',
    endpoint                LowCardinality(String) DEFAULT '',
    date_window_start       Nullable(Date),
    date_window_end         Nullable(Date),
    page_index              UInt32 DEFAULT 0,
    row_index               UInt64 DEFAULT 0,
    raw_json                String DEFAULT '',
    source_system           LowCardinality(String) DEFAULT 'dld_open_data',
    source_file             String DEFAULT '',
    source_row_index        UInt64 DEFAULT 0,
    property_id             UInt64 DEFAULT 0,
    area_id                 UInt32 DEFAULT 0,
    zone_id                 UInt32 DEFAULT 0,
    area_en                 LowCardinality(String) DEFAULT '',
    area_ar                 String DEFAULT '',
    land_number             String DEFAULT '',
    land_sub_number         String DEFAULT '',
    building_number         String DEFAULT '',
    unit_number             String DEFAULT '',
    unit_balcony_area       Float64 DEFAULT 0,
    unit_parking_number     String DEFAULT '',
    parking_allocation_type String DEFAULT '',
    parking_allocation_type_en LowCardinality(String) DEFAULT '',
    parking_allocation_type_ar String DEFAULT '',
    common_area             Float64 DEFAULT 0,
    actual_common_area      Float64 DEFAULT 0,
    floor                   String DEFAULT '',
    rooms                   String DEFAULT '',
    rooms_en                LowCardinality(String) DEFAULT '',
    rooms_ar                String DEFAULT '',
    actual_area             Float64 DEFAULT 0,
    property_type_id        UInt32 DEFAULT 0,
    property_type_en        LowCardinality(String) DEFAULT '',
    property_type_ar        String DEFAULT '',
    property_sub_type_id    UInt32 DEFAULT 0,
    prop_sub_type_en        LowCardinality(String) DEFAULT '',
    prop_sub_type_ar        String DEFAULT '',
    parent_property_id      UInt64 DEFAULT 0,
    grandparent_property_id UInt64 DEFAULT 0,
    creation_date           DateTime DEFAULT toDateTime(0),
    municipality_zip_code   String DEFAULT '',
    municipality_number     String DEFAULT '',
    parcel_id               String DEFAULT '',
    is_free_hold            UInt8 DEFAULT 0,
    is_lease_hold           UInt8 DEFAULT 0,
    is_registered           UInt8 DEFAULT 0,
    pre_registration_number String DEFAULT '',
    master_project_id       UInt64 DEFAULT 0,
    master_project_en       String DEFAULT '',
    master_project_ar       String DEFAULT '',
    project_id              UInt64 DEFAULT 0,
    project_en              String DEFAULT '',
    project_ar              String DEFAULT '',
    land_type_id            UInt32 DEFAULT 0,
    land_type_en            LowCardinality(String) DEFAULT '',
    land_type_ar            String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (run_id, row_key);

CREATE TABLE IF NOT EXISTS dld_od_brokers_bronze (
    row_key               String,
    run_id                String,
    scraped_at            String DEFAULT '',
    mode                  LowCardinality(String) DEFAULT '',
    date_window_start     Nullable(Date),
    date_window_end       Nullable(Date),
    page_index            UInt32 DEFAULT 0,
    row_index             UInt64 DEFAULT 0,
    broker_number         UInt32 DEFAULT 0,
    broker_id             UInt32 DEFAULT 0,
    broker_en             String DEFAULT '',
    broker_ar             String DEFAULT '',
    gender_type_id        UInt32 DEFAULT 0,
    gender_en             LowCardinality(String) DEFAULT '',
    gender_ar             String DEFAULT '',
    license_start_date    DateTime DEFAULT toDateTime(0),
    license_end_date      DateTime DEFAULT toDateTime(0),
    real_estate_id        UInt32 DEFAULT 0,
    real_estate_number    UInt32 DEFAULT 0,
    real_estate_en        String DEFAULT '',
    real_estate_ar        String DEFAULT '',
    real_estate_broker_id UInt32 DEFAULT 0,
    phone                 String DEFAULT '',
    fax                   String DEFAULT '',
    webpage               String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (broker_number);

CREATE TABLE IF NOT EXISTS dld_od_developers_bronze (
    row_key                String,
    run_id                 String,
    scraped_at             String DEFAULT '',
    mode                   LowCardinality(String) DEFAULT '',
    date_window_start      Nullable(Date),
    date_window_end        Nullable(Date),
    page_index             UInt32 DEFAULT 0,
    row_index              UInt64 DEFAULT 0,
    developer_number       UInt32 DEFAULT 0,
    developer_id           UInt32 DEFAULT 0,
    developer_en           String DEFAULT '',
    developer_ar           String DEFAULT '',
    registration_date      DateTime DEFAULT toDateTime(0),
    license_number         String DEFAULT '',
    license_issue_date     DateTime DEFAULT toDateTime(0),
    license_expiry_date    DateTime DEFAULT toDateTime(0),
    license_source_id      UInt32 DEFAULT 0,
    license_source_en      String DEFAULT '',
    license_source_ar      String DEFAULT '',
    license_type_id        UInt32 DEFAULT 0,
    license_type_en        String DEFAULT '',
    license_type_ar        String DEFAULT '',
    legal_status           String DEFAULT '',
    legal_status_en        String DEFAULT '',
    legal_status_ar        String DEFAULT '',
    chamber_of_commerce_no String DEFAULT '',
    participant_id         UInt32 DEFAULT 0,
    phone                  String DEFAULT '',
    fax                    String DEFAULT '',
    webpage                String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (developer_number);

ALTER TABLE dld_od_transactions_bronze ADD COLUMN IF NOT EXISTS source_system LowCardinality(String) DEFAULT 'dld_open_data';
ALTER TABLE dld_od_transactions_bronze ADD COLUMN IF NOT EXISTS source_file String DEFAULT '';
ALTER TABLE dld_od_transactions_bronze ADD COLUMN IF NOT EXISTS source_row_index UInt64 DEFAULT 0;
ALTER TABLE dld_od_transactions_bronze ADD COLUMN IF NOT EXISTS raw_json String DEFAULT '';
ALTER TABLE dld_od_transactions_bronze ADD COLUMN IF NOT EXISTS raw_manifest_s3_key String DEFAULT '';
ALTER TABLE dld_od_transactions_bronze ADD COLUMN IF NOT EXISTS project_number String DEFAULT '';
ALTER TABLE dld_od_transactions_bronze ADD COLUMN IF NOT EXISTS building_name_en String DEFAULT '';
ALTER TABLE dld_od_transactions_bronze ADD COLUMN IF NOT EXISTS building_name_ar String DEFAULT '';
ALTER TABLE dld_od_transactions_bronze ADD COLUMN IF NOT EXISTS reg_type_id UInt32 DEFAULT 0;
ALTER TABLE dld_od_transactions_bronze ADD COLUMN IF NOT EXISTS reg_type_en LowCardinality(String) DEFAULT '';
ALTER TABLE dld_od_transactions_bronze ADD COLUMN IF NOT EXISTS reg_type_ar String DEFAULT '';
ALTER TABLE dld_od_transactions_bronze ADD COLUMN IF NOT EXISTS meter_sale_price Float64 DEFAULT 0;
ALTER TABLE dld_od_transactions_bronze ADD COLUMN IF NOT EXISTS rent_value Float64 DEFAULT 0;
ALTER TABLE dld_od_transactions_bronze ADD COLUMN IF NOT EXISTS meter_rent_price Float64 DEFAULT 0;
ALTER TABLE dld_od_transactions_bronze ADD COLUMN IF NOT EXISTS no_of_parties_role_1 UInt32 DEFAULT 0;
ALTER TABLE dld_od_transactions_bronze ADD COLUMN IF NOT EXISTS no_of_parties_role_2 UInt32 DEFAULT 0;
ALTER TABLE dld_od_transactions_bronze ADD COLUMN IF NOT EXISTS no_of_parties_role_3 UInt32 DEFAULT 0;

ALTER TABLE dld_od_rents_bronze ADD COLUMN IF NOT EXISTS source_system LowCardinality(String) DEFAULT 'dld_open_data';
ALTER TABLE dld_od_rents_bronze ADD COLUMN IF NOT EXISTS source_file String DEFAULT '';
ALTER TABLE dld_od_rents_bronze ADD COLUMN IF NOT EXISTS source_row_index UInt64 DEFAULT 0;
ALTER TABLE dld_od_rents_bronze ADD COLUMN IF NOT EXISTS raw_json String DEFAULT '';
ALTER TABLE dld_od_rents_bronze ADD COLUMN IF NOT EXISTS raw_manifest_s3_key String DEFAULT '';
ALTER TABLE dld_od_rents_bronze ADD COLUMN IF NOT EXISTS line_number UInt32 DEFAULT 0;
ALTER TABLE dld_od_rents_bronze ADD COLUMN IF NOT EXISTS project_number String DEFAULT '';
ALTER TABLE dld_od_rents_bronze ADD COLUMN IF NOT EXISTS tenant_type_id UInt32 DEFAULT 0;
ALTER TABLE dld_od_rents_bronze ADD COLUMN IF NOT EXISTS tenant_type_en LowCardinality(String) DEFAULT '';
ALTER TABLE dld_od_rents_bronze ADD COLUMN IF NOT EXISTS tenant_type_ar String DEFAULT '';
ALTER TABLE dld_od_rents_bronze ADD COLUMN IF NOT EXISTS contract_reg_type_id UInt32 DEFAULT 0;
ALTER TABLE dld_od_rents_bronze ADD COLUMN IF NOT EXISTS contract_reg_type_en LowCardinality(String) DEFAULT '';
ALTER TABLE dld_od_rents_bronze ADD COLUMN IF NOT EXISTS contract_reg_type_ar String DEFAULT '';
ALTER TABLE dld_od_rents_bronze ADD COLUMN IF NOT EXISTS ejari_bus_property_type_id UInt32 DEFAULT 0;
ALTER TABLE dld_od_rents_bronze ADD COLUMN IF NOT EXISTS ejari_bus_property_type_en LowCardinality(String) DEFAULT '';
ALTER TABLE dld_od_rents_bronze ADD COLUMN IF NOT EXISTS ejari_bus_property_type_ar String DEFAULT '';

ALTER TABLE dld_od_projects_bronze ADD COLUMN IF NOT EXISTS source_system LowCardinality(String) DEFAULT 'dld_open_data';
ALTER TABLE dld_od_projects_bronze ADD COLUMN IF NOT EXISTS source_file String DEFAULT '';
ALTER TABLE dld_od_projects_bronze ADD COLUMN IF NOT EXISTS source_row_index UInt64 DEFAULT 0;
ALTER TABLE dld_od_projects_bronze ADD COLUMN IF NOT EXISTS raw_json String DEFAULT '';
ALTER TABLE dld_od_projects_bronze ADD COLUMN IF NOT EXISTS raw_manifest_s3_key String DEFAULT '';
ALTER TABLE dld_od_projects_bronze ADD COLUMN IF NOT EXISTS project_id UInt64 DEFAULT 0;
ALTER TABLE dld_od_projects_bronze ADD COLUMN IF NOT EXISTS developer_id UInt64 DEFAULT 0;
ALTER TABLE dld_od_projects_bronze ADD COLUMN IF NOT EXISTS developer_name String DEFAULT '';
ALTER TABLE dld_od_projects_bronze ADD COLUMN IF NOT EXISTS master_developer_id UInt64 DEFAULT 0;
ALTER TABLE dld_od_projects_bronze ADD COLUMN IF NOT EXISTS master_developer_number UInt64 DEFAULT 0;
ALTER TABLE dld_od_projects_bronze ADD COLUMN IF NOT EXISTS master_developer_name String DEFAULT '';
ALTER TABLE dld_od_projects_bronze ADD COLUMN IF NOT EXISTS project_type_id UInt32 DEFAULT 0;
ALTER TABLE dld_od_projects_bronze ADD COLUMN IF NOT EXISTS project_classification_id UInt32 DEFAULT 0;
ALTER TABLE dld_od_projects_bronze ADD COLUMN IF NOT EXISTS project_classification_ar String DEFAULT '';
ALTER TABLE dld_od_projects_bronze ADD COLUMN IF NOT EXISTS escrow_agent_id UInt64 DEFAULT 0;
ALTER TABLE dld_od_projects_bronze ADD COLUMN IF NOT EXISTS escrow_agent_name String DEFAULT '';
ALTER TABLE dld_od_projects_bronze ADD COLUMN IF NOT EXISTS cancellation_date Nullable(DateTime);
ALTER TABLE dld_od_projects_bronze ADD COLUMN IF NOT EXISTS property_id UInt64 DEFAULT 0;
ALTER TABLE dld_od_projects_bronze ADD COLUMN IF NOT EXISTS area_id UInt32 DEFAULT 0;
ALTER TABLE dld_od_projects_bronze ADD COLUMN IF NOT EXISTS zoning_authority_id UInt32 DEFAULT 0;
ALTER TABLE dld_od_projects_bronze ADD COLUMN IF NOT EXISTS zoning_authority_en String DEFAULT '';
ALTER TABLE dld_od_projects_bronze ADD COLUMN IF NOT EXISTS zoning_authority_ar String DEFAULT '';

ALTER TABLE dld_od_valuations_bronze ADD COLUMN IF NOT EXISTS source_system LowCardinality(String) DEFAULT 'dld_open_data';
ALTER TABLE dld_od_valuations_bronze ADD COLUMN IF NOT EXISTS source_file String DEFAULT '';
ALTER TABLE dld_od_valuations_bronze ADD COLUMN IF NOT EXISTS source_row_index UInt64 DEFAULT 0;
ALTER TABLE dld_od_valuations_bronze ADD COLUMN IF NOT EXISTS raw_json String DEFAULT '';
ALTER TABLE dld_od_valuations_bronze ADD COLUMN IF NOT EXISTS raw_manifest_s3_key String DEFAULT '';

ALTER TABLE dld_od_lands_bronze ADD COLUMN IF NOT EXISTS source_system LowCardinality(String) DEFAULT 'dld_open_data';
ALTER TABLE dld_od_lands_bronze ADD COLUMN IF NOT EXISTS source_file String DEFAULT '';
ALTER TABLE dld_od_lands_bronze ADD COLUMN IF NOT EXISTS source_row_index UInt64 DEFAULT 0;
ALTER TABLE dld_od_lands_bronze ADD COLUMN IF NOT EXISTS raw_json String DEFAULT '';
ALTER TABLE dld_od_lands_bronze ADD COLUMN IF NOT EXISTS raw_manifest_s3_key String DEFAULT '';
ALTER TABLE dld_od_lands_bronze ADD COLUMN IF NOT EXISTS property_id UInt64 DEFAULT 0;
ALTER TABLE dld_od_lands_bronze ADD COLUMN IF NOT EXISTS property_type_id UInt32 DEFAULT 0;
ALTER TABLE dld_od_lands_bronze ADD COLUMN IF NOT EXISTS property_type_en LowCardinality(String) DEFAULT '';
ALTER TABLE dld_od_lands_bronze ADD COLUMN IF NOT EXISTS property_type_ar String DEFAULT '';
ALTER TABLE dld_od_lands_bronze ADD COLUMN IF NOT EXISTS property_sub_type_id UInt32 DEFAULT 0;
ALTER TABLE dld_od_lands_bronze ADD COLUMN IF NOT EXISTS project_id UInt64 DEFAULT 0;

ALTER TABLE dld_od_buildings_bronze ADD COLUMN IF NOT EXISTS source_system LowCardinality(String) DEFAULT 'dld_open_data';
ALTER TABLE dld_od_buildings_bronze ADD COLUMN IF NOT EXISTS source_file String DEFAULT '';
ALTER TABLE dld_od_buildings_bronze ADD COLUMN IF NOT EXISTS source_row_index UInt64 DEFAULT 0;
ALTER TABLE dld_od_buildings_bronze ADD COLUMN IF NOT EXISTS raw_json String DEFAULT '';
ALTER TABLE dld_od_buildings_bronze ADD COLUMN IF NOT EXISTS raw_manifest_s3_key String DEFAULT '';
ALTER TABLE dld_od_buildings_bronze ADD COLUMN IF NOT EXISTS property_id UInt64 DEFAULT 0;
ALTER TABLE dld_od_buildings_bronze ADD COLUMN IF NOT EXISTS property_type_id UInt32 DEFAULT 0;
ALTER TABLE dld_od_buildings_bronze ADD COLUMN IF NOT EXISTS property_type_en LowCardinality(String) DEFAULT '';
ALTER TABLE dld_od_buildings_bronze ADD COLUMN IF NOT EXISTS property_type_ar String DEFAULT '';
ALTER TABLE dld_od_buildings_bronze ADD COLUMN IF NOT EXISTS project_id UInt64 DEFAULT 0;

ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS source_system LowCardinality(String) DEFAULT 'dld_open_data';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS source_file String DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS source_row_index UInt64 DEFAULT 0;
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS raw_manifest_s3_key String DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS property_id UInt64 DEFAULT 0;
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS area_id UInt32 DEFAULT 0;
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS zone_id UInt32 DEFAULT 0;
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS area_en LowCardinality(String) DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS area_ar String DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS land_number String DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS land_sub_number String DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS building_number String DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS unit_number String DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS unit_balcony_area Float64 DEFAULT 0;
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS unit_parking_number String DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS parking_allocation_type String DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS parking_allocation_type_en LowCardinality(String) DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS parking_allocation_type_ar String DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS common_area Float64 DEFAULT 0;
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS actual_common_area Float64 DEFAULT 0;
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS floor String DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS rooms String DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS rooms_en LowCardinality(String) DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS rooms_ar String DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS actual_area Float64 DEFAULT 0;
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS property_type_id UInt32 DEFAULT 0;
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS property_type_en LowCardinality(String) DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS property_type_ar String DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS property_sub_type_id UInt32 DEFAULT 0;
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS prop_sub_type_en LowCardinality(String) DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS prop_sub_type_ar String DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS parent_property_id UInt64 DEFAULT 0;
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS grandparent_property_id UInt64 DEFAULT 0;
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS creation_date DateTime DEFAULT toDateTime(0);
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS municipality_zip_code String DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS municipality_number String DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS parcel_id String DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS is_free_hold UInt8 DEFAULT 0;
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS is_lease_hold UInt8 DEFAULT 0;
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS is_registered UInt8 DEFAULT 0;
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS pre_registration_number String DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS master_project_id UInt64 DEFAULT 0;
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS master_project_en String DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS master_project_ar String DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS project_id UInt64 DEFAULT 0;
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS project_en String DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS project_ar String DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS land_type_id UInt32 DEFAULT 0;
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS land_type_en LowCardinality(String) DEFAULT '';
ALTER TABLE dld_od_units_bronze ADD COLUMN IF NOT EXISTS land_type_ar String DEFAULT '';

ALTER TABLE dld_od_brokers_bronze ADD COLUMN IF NOT EXISTS source_system LowCardinality(String) DEFAULT 'dld_open_data';
ALTER TABLE dld_od_brokers_bronze ADD COLUMN IF NOT EXISTS source_file String DEFAULT '';
ALTER TABLE dld_od_brokers_bronze ADD COLUMN IF NOT EXISTS source_row_index UInt64 DEFAULT 0;
ALTER TABLE dld_od_brokers_bronze ADD COLUMN IF NOT EXISTS raw_json String DEFAULT '';
ALTER TABLE dld_od_brokers_bronze ADD COLUMN IF NOT EXISTS raw_manifest_s3_key String DEFAULT '';

ALTER TABLE dld_od_developers_bronze ADD COLUMN IF NOT EXISTS source_system LowCardinality(String) DEFAULT 'dld_open_data';
ALTER TABLE dld_od_developers_bronze ADD COLUMN IF NOT EXISTS source_file String DEFAULT '';
ALTER TABLE dld_od_developers_bronze ADD COLUMN IF NOT EXISTS source_row_index UInt64 DEFAULT 0;
ALTER TABLE dld_od_developers_bronze ADD COLUMN IF NOT EXISTS raw_json String DEFAULT '';
ALTER TABLE dld_od_developers_bronze ADD COLUMN IF NOT EXISTS raw_manifest_s3_key String DEFAULT '';
ALTER TABLE dld_od_developers_bronze ADD COLUMN IF NOT EXISTS developer_name_en String DEFAULT '';
ALTER TABLE dld_od_developers_bronze ADD COLUMN IF NOT EXISTS developer_name_ar String DEFAULT '';

CREATE TABLE IF NOT EXISTS pf_locations_bronze (
    location_id        String,
    parent_location_id Nullable(String),
    scraped_at         String DEFAULT '',
    locale             LowCardinality(String) DEFAULT '',
    path               String DEFAULT '',
    path_ids_json      String DEFAULT '',
    path_name          String DEFAULT '',
    name               String DEFAULT '',
    level              Int32 DEFAULT 0,
    location_type      LowCardinality(String) DEFAULT '',
    url_slug           String DEFAULT '',
    url_city_slug      String DEFAULT '',
    lat                Nullable(Float64),
    lng                Nullable(Float64),
    children_count     UInt32 DEFAULT 0,
    top_location_id    String DEFAULT '',
    published          UInt8 DEFAULT 0,
    is_dubai           UInt8 DEFAULT 0,
    raw_json           String DEFAULT '',
    run_id             String
) ENGINE = MergeTree()
ORDER BY location_id;

CREATE TABLE IF NOT EXISTS pf_listings_bronze (
    property_key                String,
    run_id                      String,
    scraped_at                  String DEFAULT '',
    query_signature             String DEFAULT '',
    category_id                 UInt16 DEFAULT 0,
    location_id                 String DEFAULT '',
    property_type_id            Nullable(Int64),
    bedroom                     Nullable(Int64),
    min_price                   Nullable(Int64),
    max_price                   Nullable(Int64),
    page                        UInt32 DEFAULT 0,
    wrapper_index               UInt32 DEFAULT 0,
    listing_id                  String DEFAULT '',
    property_id                 String DEFAULT '',
    reference                   String DEFAULT '',
    details_path                String DEFAULT '',
    share_url                   String DEFAULT '',
    title                       String DEFAULT '',
    property_type_json          String DEFAULT '',
    price_json                  String DEFAULT '',
    size_json                   String DEFAULT '',
    bedrooms                    String DEFAULT '',
    bathrooms                   String DEFAULT '',
    listing_location_ids_json   String DEFAULT '',
    listing_location_names_json String DEFAULT '',
    city_location_id            String DEFAULT '',
    community_location_id       String DEFAULT '',
    subcommunity_location_id    String DEFAULT '',
    building_location_id        String DEFAULT '',
    leaf_location_id            String DEFAULT '',
    lat                         Nullable(Float64),
    lng                         Nullable(Float64),
    is_available                UInt8 DEFAULT 0,
    is_verified                 UInt8 DEFAULT 0,
    is_featured                 UInt8 DEFAULT 0,
    is_premium                  UInt8 DEFAULT 0,
    delta_reason                LowCardinality(String) DEFAULT '',
    selected_for_detail         UInt8 DEFAULT 0,
    property_fingerprint        String DEFAULT '',
    agent_json                  String DEFAULT '',
    broker_json                 String DEFAULT '',
    client_json                 String DEFAULT '',
    images_json                 String DEFAULT '',
    raw_property_json           String DEFAULT '',
    raw_wrapper_json            String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (run_id, property_key);

CREATE TABLE IF NOT EXISTS pf_listing_details_bronze (
    detail_key           String,
    run_id               String,
    scraped_at           String DEFAULT '',
    listing_id           String DEFAULT '',
    property_id          String DEFAULT '',
    property_key         String DEFAULT '',
    details_path         String DEFAULT '',
    category_id          UInt16 DEFAULT 0,
    location_id          String DEFAULT '',
    status               LowCardinality(String) DEFAULT '',
    error                String DEFAULT '',
    detail_property_json String DEFAULT '',
    raw_json             String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (run_id, detail_key);

CREATE TABLE IF NOT EXISTS reelly_projects_bronze (
    project_key    String,
    run_id         String,
    scraped_at     String DEFAULT '',
    project_id     String DEFAULT '',
    delta_reason   LowCardinality(String) DEFAULT '',
    list_item_json String DEFAULT '',
    raw_json       String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (run_id, project_key);

CREATE TABLE IF NOT EXISTS reelly_documents_bronze (
    document_key    String,
    run_id          String,
    scraped_at      String DEFAULT '',
    project_id      String DEFAULT '',
    source_endpoint LowCardinality(String) DEFAULT '',
    field_path      String DEFAULT '',
    name            String DEFAULT '',
    url             String DEFAULT '',
    normalized_url  String DEFAULT '',
    status          LowCardinality(String) DEFAULT '',
    error           String DEFAULT '',
    downloaded_path String DEFAULT '',
    final_url       String DEFAULT '',
    content_type    String DEFAULT '',
    sha256          String DEFAULT '',
    size_bytes      UInt64 DEFAULT 0,
    raw_json        String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (run_id, document_key);

CREATE TABLE IF NOT EXISTS reelly_matrix_availability_bronze (
    availability_key String,
    run_id           String,
    scraped_at       String DEFAULT '',
    project_id       String DEFAULT '',
    endpoint         String DEFAULT '',
    candidate        String DEFAULT '',
    status           LowCardinality(String) DEFAULT '',
    error            String DEFAULT '',
    raw_json         String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (run_id, availability_key);

CREATE TABLE IF NOT EXISTS bronze_load_ledger (
    source          LowCardinality(String),
    dataset_version String,
    manifest_key    String,
    run_id          String,
    table_name      String,
    row_count       UInt64,
    loaded_at       DateTime64(3, 'UTC'),
    status          LowCardinality(String),
    error           String DEFAULT ''
) ENGINE = MergeTree()
ORDER BY (source, dataset_version, manifest_key, table_name, loaded_at);

CREATE TABLE IF NOT EXISTS silver_reelly_projects (
    project_id          String,
    project_key         String,
    project_name        String DEFAULT '',
    area_name           String DEFAULT '',
    developer_name      String DEFAULT '',
    region              LowCardinality(String) DEFAULT '',
    latitude            Nullable(Float64),
    longitude           Nullable(Float64),
    sale_status         LowCardinality(String) DEFAULT '',
    completion_time     Nullable(DateTime64(3, 'UTC')),
    units_in_sale       UInt32 DEFAULT 0,
    readiness_progress  Float64 DEFAULT 0,
    updated_at          DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (project_id, project_key);

-- Silver layer: cleaned, normalised, analytics-ready tables derived from bronze.
-- Field naming conventions:
--   - Free-text entity names use initcap(trim()) applied at build time.
--   - Arabic variants are preserved alongside English.
--   - Bronze ingestion envelope (run_id, mode, page_index, etc.) is dropped.
--   - Numeric-only ID fields (group_id, procedure_id, usage_id) are dropped.
--     area_id and property_id are kept as stable cross-source identifiers.
--   - Redundant string flags (is_free_hold_en/ar, is_offplan_en/ar) are dropped.

CREATE TABLE IF NOT EXISTS silver_transactions (
    row_key                  String,
    transaction_number       String               DEFAULT '',
    transaction_date         Date                 DEFAULT toDate(0),
    trans_group              LowCardinality(String) DEFAULT '',
    trans_group_ar           String               DEFAULT '',
    procedure_name           LowCardinality(String) DEFAULT '',
    procedure_name_ar        String               DEFAULT '',
    procedure_area           Float64              DEFAULT 0,
    property_type            LowCardinality(String) DEFAULT '',
    property_type_ar         String               DEFAULT '',
    property_sub_type        LowCardinality(String) DEFAULT '',
    property_sub_type_ar     String               DEFAULT '',
    property_usage           LowCardinality(String) DEFAULT '',
    property_usage_ar        String               DEFAULT '',
    reg_type                 LowCardinality(String) DEFAULT '',
    reg_type_ar              String               DEFAULT '',
    rooms_en                 LowCardinality(String) DEFAULT '',
    rooms_ar                 String               DEFAULT '',
    parking                  String               DEFAULT '',
    building_age             UInt32               DEFAULT 0,
    parcel_id                String               DEFAULT '',
    area_id                  UInt32               DEFAULT 0,
    area_name_en             LowCardinality(String) DEFAULT '',
    area_name_ar             String               DEFAULT '',
    project_name_en          String               DEFAULT '',
    project_name_ar          String               DEFAULT '',
    master_project_en        String               DEFAULT '',
    master_project_ar        String               DEFAULT '',
    building_name_en         String               DEFAULT '',
    building_name_ar         String               DEFAULT '',
    project_number           String               DEFAULT '',
    property_id              UInt32               DEFAULT 0,
    actual_area_sqm          Float64              DEFAULT 0,
    sale_price_aed           Int64                DEFAULT 0,
    price_per_sqm_aed        Float64              DEFAULT 0,
    is_free_hold             UInt8                DEFAULT 0,
    is_off_plan              UInt8                DEFAULT 0,
    total_buyers             UInt32               DEFAULT 0,
    total_sellers            UInt32               DEFAULT 0,
    nearest_metro_en         String               DEFAULT '',
    nearest_metro_ar         String               DEFAULT '',
    nearest_mall_en          String               DEFAULT '',
    nearest_mall_ar          String               DEFAULT '',
    nearest_landmark_en      String               DEFAULT '',
    nearest_landmark_ar      String               DEFAULT '',
    no_of_parties_role_1     UInt32               DEFAULT 0,
    no_of_parties_role_2     UInt32               DEFAULT 0,
    no_of_parties_role_3     UInt32               DEFAULT 0
) ENGINE = ReplacingMergeTree()
ORDER BY (transaction_date, transaction_number);

CREATE TABLE IF NOT EXISTS silver_rent_contracts (
    row_key                      String,
    contract_id                  String               DEFAULT '',
    contract_number              String               DEFAULT '',
    line_number                  UInt32               DEFAULT 0,
    registration_date            Date                 DEFAULT toDate(0),
    contract_start_date          Date                 DEFAULT toDate(0),
    contract_end_date            Date                 DEFAULT toDate(0),
    property_type                LowCardinality(String) DEFAULT '',
    property_type_ar             String               DEFAULT '',
    property_sub_type            LowCardinality(String) DEFAULT '',
    property_sub_type_ar         String               DEFAULT '',
    property_usage               LowCardinality(String) DEFAULT '',
    property_usage_ar            String               DEFAULT '',
    rooms                        LowCardinality(String) DEFAULT '',
    parking                      String               DEFAULT '',
    actual_area_sqm              Float64              DEFAULT 0,
    annual_amount_aed            Int64                DEFAULT 0,
    contract_amount_aed          Int64                DEFAULT 0,
    rent_per_sqm_aed             Float64              DEFAULT 0,
    total_properties             UInt32               DEFAULT 0,
    version_number               UInt32               DEFAULT 0,
    contract_version             LowCardinality(String) DEFAULT '',
    contract_version_ar          String               DEFAULT '',
    parcel_id                    String               DEFAULT '',
    area_id                      UInt32               DEFAULT 0,
    area_name_en                 LowCardinality(String) DEFAULT '',
    area_name_ar                 String               DEFAULT '',
    project_name_en              String               DEFAULT '',
    project_name_ar              String               DEFAULT '',
    master_project_en            String               DEFAULT '',
    master_project_ar            String               DEFAULT '',
    project_number               String               DEFAULT '',
    property_id                  UInt32               DEFAULT 0,
    land_property_id             UInt32               DEFAULT 0,
    is_free_hold                 UInt8                DEFAULT 0,
    tenant_type                  LowCardinality(String) DEFAULT '',
    tenant_type_ar               String               DEFAULT '',
    contract_reg_type            LowCardinality(String) DEFAULT '',
    contract_reg_type_ar         String               DEFAULT '',
    ejari_property_type_id       UInt32               DEFAULT 0,
    ejari_property_sub_type_id   UInt32               DEFAULT 0,
    ejari_business_property_type LowCardinality(String) DEFAULT '',
    ejari_business_property_type_ar String            DEFAULT '',
    nearest_metro_en             String               DEFAULT '',
    nearest_metro_ar             String               DEFAULT '',
    nearest_mall_en              String               DEFAULT '',
    nearest_mall_ar              String               DEFAULT '',
    nearest_landmark_en          String               DEFAULT '',
    nearest_landmark_ar          String               DEFAULT '',
    annual_amount_per_property_aed Float64            DEFAULT 0,
    property_category            LowCardinality(String) DEFAULT '',
    market_scope                 LowCardinality(String) DEFAULT '',
    is_residential_home          UInt8                DEFAULT 0,
    is_single_property_contract  UInt8                DEFAULT 0,
    is_rent_per_sqm_valid        UInt8                DEFAULT 0,
    is_yield_eligible             UInt8                DEFAULT 0
) ENGINE = ReplacingMergeTree()
ORDER BY (registration_date, contract_id);

ALTER TABLE silver_rent_contracts
    ADD COLUMN IF NOT EXISTS annual_amount_per_property_aed Float64 DEFAULT 0;
ALTER TABLE silver_rent_contracts
    ADD COLUMN IF NOT EXISTS property_category LowCardinality(String) DEFAULT '';
ALTER TABLE silver_rent_contracts
    ADD COLUMN IF NOT EXISTS market_scope LowCardinality(String) DEFAULT '';
ALTER TABLE silver_rent_contracts
    ADD COLUMN IF NOT EXISTS is_residential_home UInt8 DEFAULT 0;
ALTER TABLE silver_rent_contracts
    ADD COLUMN IF NOT EXISTS is_single_property_contract UInt8 DEFAULT 0;
ALTER TABLE silver_rent_contracts
    ADD COLUMN IF NOT EXISTS is_rent_per_sqm_valid UInt8 DEFAULT 0;
ALTER TABLE silver_rent_contracts
    ADD COLUMN IF NOT EXISTS is_yield_eligible UInt8 DEFAULT 0;

-- Canonical geography derived from Property Finder's typed location hierarchy.
-- Source labels remain untouched. The crosswalk is additive and may deliberately
-- leave a source signature unmapped when the available evidence is ambiguous.

CREATE TABLE IF NOT EXISTS geo_location_nodes (
    canonical_location_id        String,
    source_location_id           String,
    parent_canonical_location_id Nullable(String),
    snapshot_id                  String,
    scraped_at                   Nullable(DateTime64(3, 'UTC')),
    location_type                LowCardinality(String),
    level                        Int32,
    name                         String,
    normalized_name              String,
    path_name                    String,
    path_ids_json                String,
    latitude                     Nullable(Float64),
    longitude                    Nullable(Float64),
    coordinate_status            LowCardinality(String),
    published                    UInt8,
    materialized_at              DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(materialized_at)
ORDER BY canonical_location_id;

CREATE TABLE IF NOT EXISTS geo_location_closure (
    ancestor_location_id   String,
    descendant_location_id String,
    depth                  UInt16,
    snapshot_id            String,
    materialized_at        DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(materialized_at)
ORDER BY (ancestor_location_id, descendant_location_id);

CREATE TABLE IF NOT EXISTS geo_source_signatures (
    source_system             LowCardinality(String),
    source_key                String,
    source_grain              LowCardinality(String),
    property_type             LowCardinality(String) DEFAULT '',
    market_status             LowCardinality(String) DEFAULT '',
    source_entity_class       LowCardinality(String) DEFAULT '',
    raw_area_name             String,
    raw_master_project_name   String,
    raw_project_name          String,
    raw_building_name         String,
    normalized_area_name      String,
    normalized_master_project String,
    normalized_project_name   String,
    normalized_building_name  String,
    row_count                 UInt64,
    represented_value_aed     Int64,
    first_observed            Nullable(Date),
    last_observed             Nullable(Date),
    normalization_version     UInt16,
    build_id                  String,
    materialized_at           DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(materialized_at)
ORDER BY (source_system, source_key);

ALTER TABLE geo_source_signatures
    ADD COLUMN IF NOT EXISTS property_type LowCardinality(String) DEFAULT '' AFTER source_grain;
ALTER TABLE geo_source_signatures
    ADD COLUMN IF NOT EXISTS market_status LowCardinality(String) DEFAULT '' AFTER property_type;
ALTER TABLE geo_source_signatures
    ADD COLUMN IF NOT EXISTS source_entity_class LowCardinality(String) DEFAULT '' AFTER market_status;

CREATE TABLE IF NOT EXISTS geo_entity_links (
    source_system         LowCardinality(String),
    source_key            String,
    canonical_location_id Nullable(String),
    target_grain          LowCardinality(String),
    relation              LowCardinality(String),
    status                LowCardinality(String),
    match_method          LowCardinality(String),
    confidence            LowCardinality(String),
    candidate_count       UInt16,
    evidence_json         String,
    normalization_version UInt16,
    pf_snapshot_id        String,
    build_id              String,
    reviewed_by           String DEFAULT '',
    reviewed_at           Nullable(DateTime64(3, 'UTC')),
    materialized_at       DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(materialized_at)
ORDER BY (source_system, source_key);

-- Human review decisions live separately from generated links so refreshes cannot
-- overwrite them. An active approval must target a current canonical node, and an
-- active rejection deliberately leaves the source signature unmapped.
CREATE TABLE IF NOT EXISTS geo_entity_link_overrides (
    source_system         LowCardinality(String),
    source_key            String,
    canonical_location_id Nullable(String),
    decision              LowCardinality(String),
    relation              LowCardinality(String) DEFAULT 'equivalent',
    review_note           String,
    reviewed_by           String,
    reviewed_at           DateTime64(3, 'UTC') DEFAULT now64(3),
    active                UInt8 DEFAULT 1
) ENGINE = ReplacingMergeTree(reviewed_at)
ORDER BY (source_system, source_key);

CREATE TABLE IF NOT EXISTS geo_tower_aliases (
    canonical_location_id String,
    alias_name            String,
    normalized_alias      String,
    source_system         LowCardinality(String),
    evidence_json         String,
    status                LowCardinality(String),
    reviewed_by           String DEFAULT '',
    reviewed_at           Nullable(DateTime64(3, 'UTC')),
    active                UInt8 DEFAULT 1,
    materialized_at       DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(materialized_at)
ORDER BY (canonical_location_id, normalized_alias, source_system);

CREATE TABLE IF NOT EXISTS geo_entity_link_candidates (
    source_system         LowCardinality(String),
    source_key            String,
    candidate_rank        UInt8,
    canonical_location_id String,
    target_name           String,
    score                 UInt8,
    context_supported     UInt8,
    identity_compatible   UInt8,
    match_method          LowCardinality(String),
    source_variant        String,
    target_variant        String,
    build_id              String,
    materialized_at       DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(materialized_at)
ORDER BY (source_system, source_key, candidate_rank);

-- Reelly is a project catalogue, not a geographic hierarchy. Keep this crosswalk
-- separate from PF geography so a project/phase link cannot be mistaken for a
-- physical tower. Every off-plan signature receives a row, including unresolved
-- and catalogue-absent records.
CREATE TABLE IF NOT EXISTS offplan_reelly_project_links (
    source_system         LowCardinality(String),
    source_key            String,
    reelly_project_id     Nullable(String),
    relation              LowCardinality(String),
    status                LowCardinality(String),
    match_method          LowCardinality(String),
    confidence            LowCardinality(String),
    candidate_count       UInt16,
    evidence_json         String,
    normalization_version UInt16,
    catalog_build_id      String,
    source_build_id       String,
    reviewed_by           String DEFAULT '',
    reviewed_at           Nullable(DateTime64(3, 'UTC')),
    materialized_at       DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(materialized_at)
ORDER BY (source_system, source_key);

CREATE TABLE IF NOT EXISTS offplan_reelly_project_link_overrides (
    source_system     LowCardinality(String),
    source_key        String,
    reelly_project_id Nullable(String),
    decision          LowCardinality(String),
    relation          LowCardinality(String) DEFAULT 'equivalent',
    review_note       String,
    reviewed_by       String,
    reviewed_at       DateTime64(3, 'UTC') DEFAULT now64(3),
    active            UInt8 DEFAULT 1
) ENGINE = ReplacingMergeTree(reviewed_at)
ORDER BY (source_system, source_key);

CREATE TABLE IF NOT EXISTS offplan_reelly_project_link_candidates (
    source_system      LowCardinality(String),
    source_key         String,
    candidate_rank     UInt8,
    reelly_project_id  String,
    project_name       String,
    area_name          String,
    score              UInt8,
    context_supported  UInt8,
    identity_compatible UInt8,
    match_method       LowCardinality(String),
    relation           LowCardinality(String),
    source_field       LowCardinality(String),
    source_variant     String,
    target_variant     String,
    catalog_build_id   String,
    source_build_id    String,
    materialized_at    DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(materialized_at)
ORDER BY (source_system, source_key, candidate_rank);

CREATE OR REPLACE VIEW offplan_reelly_mapped_source_facts AS
SELECT
    s.source_system AS source_system,
    s.source_key AS source_key,
    s.property_type AS property_type,
    s.raw_area_name AS raw_area_name,
    s.raw_master_project_name AS raw_master_project_name,
    s.raw_project_name AS raw_project_name,
    s.raw_building_name AS raw_building_name,
    s.row_count AS row_count,
    s.represented_value_aed AS represented_value_aed,
    s.first_observed AS first_observed,
    s.last_observed AS last_observed,
    l.reelly_project_id AS reelly_project_id,
    l.relation AS relation,
    l.status AS match_status,
    l.match_method AS match_method,
    l.confidence AS match_confidence,
    l.candidate_count AS candidate_count,
    l.evidence_json AS evidence_json,
    r.project_key AS reelly_project_key,
    r.project_name AS reelly_project_name,
    replaceRegexpAll(lowerUTF8(r.project_name), '[^a-z0-9]', '')
        AS normalized_reelly_project_name,
    r.area_name AS reelly_area_name,
    r.developer_name AS reelly_developer_name,
    r.latitude AS latitude,
    r.longitude AS longitude,
    r.completion_time AS completion_time,
    r.readiness_progress AS readiness_progress
FROM geo_source_signatures AS s
INNER JOIN offplan_reelly_project_links AS l USING (source_system, source_key)
LEFT JOIN silver_reelly_projects AS r FINAL
    ON r.project_id = l.reelly_project_id
WHERE s.market_status = 'Offplan';

CREATE OR REPLACE VIEW geo_mapped_source_facts AS
SELECT
    s.source_system AS source_system,
    s.source_key AS source_key,
    s.source_grain AS source_grain,
    s.property_type AS property_type,
    s.market_status AS market_status,
    s.source_entity_class AS source_entity_class,
    s.raw_area_name AS raw_area_name,
    s.raw_master_project_name AS raw_master_project_name,
    s.raw_project_name AS raw_project_name,
    s.raw_building_name AS raw_building_name,
    s.normalized_area_name AS normalized_area_name,
    s.normalized_master_project AS normalized_master_project,
    s.normalized_project_name AS normalized_project_name,
    s.normalized_building_name AS normalized_building_name,
    s.row_count AS row_count,
    s.represented_value_aed AS represented_value_aed,
    s.first_observed AS first_observed,
    s.last_observed AS last_observed,
    s.normalization_version AS normalization_version,
    s.build_id AS build_id,
    l.canonical_location_id AS canonical_location_id,
    l.target_grain,
    l.relation,
    l.status AS match_status,
    l.match_method,
    l.confidence AS match_confidence,
    l.candidate_count,
    l.evidence_json,
    n.name AS canonical_location_name,
    n.location_type AS canonical_location_type,
    n.path_name AS canonical_path_name,
    n.latitude,
    n.longitude,
    n.coordinate_status
FROM geo_source_signatures AS s
INNER JOIN geo_entity_links AS l USING (source_system, source_key)
LEFT JOIN geo_location_nodes AS n
    ON n.canonical_location_id = l.canonical_location_id;

-- One display hierarchy per distinct CRM rental address. Canonical PF names are
-- published only for approved crosswalks; registry labels remain available for
-- auditing and as the fallback for unresolved signatures.
CREATE OR REPLACE VIEW geo_crm_rental_hierarchy AS
WITH canonical_ancestors AS (
    SELECT
        c.descendant_location_id AS canonical_location_id,
        argMinIf(n.name, c.depth, n.location_type = 'COMMUNITY') AS community_name,
        argMinIf(n.name, c.depth, n.location_type = 'SUBCOMMUNITY')
            AS nearest_subcommunity_name,
        argMinIf(
            n.name,
            c.depth,
            n.location_type = 'SUBCOMMUNITY' AND c.depth > 0
        ) AS parent_subcommunity_name
    FROM geo_location_closure AS c
    INNER JOIN geo_location_nodes AS n
        ON n.canonical_location_id = c.ancestor_location_id
    GROUP BY c.descendant_location_id
)
SELECT
    m.source_key,
    m.source_grain,
    m.row_count,
    m.raw_area_name AS registry_area_name,
    m.raw_project_name AS registry_project_name,
    m.raw_building_name AS registry_building_name,
    transform(
        if(
            m.match_status IN ('auto_approved', 'manual_approved')
                AND a.community_name != '',
            a.community_name,
            m.raw_area_name
        ),
        [
            'Al Barshaa South 1', 'Al Barshaa South 3',
            'Al Goze Industrial 1', 'Al Goze Industrial 3', 'Al Goze Industrial 4',
            'Al Saffa 1', 'Al Saffa 2', 'Al Safouh 1', 'Al Safouh 2',
            'Al Thanayah 4', 'Dubai Creek Harbour (The Lagoons)',
            'Dubai Investment Park (DIP)', 'Dubai Production City (IMPZ)',
            'Dubai South (Dubai World Central)', 'Dubai Maritime City',
            'Festival City', 'The Greens', 'Hessayan 1',
            'Um Suqaim 1', 'Um Suqaim 2', 'Um Suqaim 3',
            'Za''Abeel 1', 'Zaabeel 1', 'Zaabeel 2'
        ],
        [
            'Al Barsha South 1', 'Al Barsha South 3',
            'Al Quoz Industrial 1', 'Al Quoz Industrial 3', 'Al Quoz Industrial 4',
            'Al Safa 1', 'Al Safa 2', 'Al Sufouh 1', 'Al Sufouh 2',
            'Al Thanyah 4', 'Dubai Creek Harbour',
            'Dubai Investment Park', 'Dubai Production City',
            'Dubai South', 'Maritime City',
            'Dubai Festival City', 'Greens', 'Hessyan 1',
            'Umm Suqeim 1', 'Umm Suqeim 2', 'Umm Suqeim 3',
            'Zabeel 1', 'Zabeel 1', 'Zabeel 2'
        ],
        if(
            m.match_status IN ('auto_approved', 'manual_approved')
                AND a.community_name != '',
            a.community_name,
            m.raw_area_name
        )
    ) AS display_area_name,
    multiIf(
        m.source_grain = 'landed_phase'
            AND m.match_status IN ('auto_approved', 'manual_approved')
            AND m.canonical_location_type = 'SUBCOMMUNITY',
            m.canonical_location_name,
        m.source_grain = 'project'
            AND m.match_status IN ('auto_approved', 'manual_approved')
            AND m.canonical_location_type IN ('SUBCOMMUNITY', 'TOWER'),
            m.canonical_location_name,
        m.source_grain = 'building'
            AND m.match_status IN ('auto_approved', 'manual_approved')
            AND a.parent_subcommunity_name != '',
            a.parent_subcommunity_name,
        m.raw_project_name
    ) AS display_project_name,
    multiIf(
        m.source_grain = 'landed_phase', '',
        m.source_grain = 'building'
            AND m.match_status IN ('auto_approved', 'manual_approved')
            AND JSONExtractString(m.evidence_json, 'source_field') = 'building',
            m.canonical_location_name,
        m.raw_building_name
    ) AS display_building_name,
    m.canonical_location_id,
    m.target_grain AS canonical_grain,
    m.match_status,
    m.match_method,
    m.match_confidence,
    m.latitude,
    m.longitude,
    m.coordinate_status,
    multiIf(
        m.latitude IS NULL OR m.longitude IS NULL, 'missing',
        JSONExtractString(m.evidence_json, 'source_field') IN ('building', 'building_aggregate'),
            'exact_location',
        m.source_grain = 'landed_phase', 'phase_location',
        m.source_grain = 'project', 'project_location',
        'community_location'
    ) AS coordinate_precision
FROM geo_mapped_source_facts AS m
LEFT JOIN canonical_ancestors AS a USING (canonical_location_id)
WHERE m.source_system = 'dxbi_rentals';

CREATE OR REPLACE VIEW geo_crosswalk_review_queue AS
SELECT
    s.source_system,
    s.source_key,
    s.source_grain,
    s.property_type,
    s.market_status,
    s.source_entity_class,
    s.raw_area_name,
    s.raw_master_project_name,
    s.raw_project_name,
    s.raw_building_name,
    s.row_count,
    s.represented_value_aed,
    s.first_observed,
    s.last_observed,
    l.status,
    l.match_method,
    l.candidate_count,
    l.evidence_json,
    s.build_id
FROM geo_source_signatures AS s
INNER JOIN geo_entity_links AS l USING (source_system, source_key)
WHERE l.status NOT IN ('auto_approved', 'manual_approved');

CREATE OR REPLACE VIEW geo_stale_link_overrides AS
SELECT
    o.source_system,
    o.source_key,
    o.canonical_location_id,
    o.decision,
    o.relation,
    o.review_note,
    o.reviewed_by,
    o.reviewed_at
FROM (
    SELECT * FROM geo_entity_link_overrides FINAL WHERE active = 1
) AS o
LEFT JOIN geo_source_signatures AS s USING (source_system, source_key)
WHERE s.source_key IS NULL;
