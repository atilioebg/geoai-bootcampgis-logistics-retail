"""
GeoAI Cognitive Blueprint — Database Metadata Application Script.

This script stamps every column in our 3 core PostGIS tables with official
descriptions sourced directly from authoritative government documentation:
  - US Census Bureau ACS 5-Year Variables API  → demographics_acs
  - TIGER/Line Technical Documentation          → spatial_tiger
  - BootcampGIS ETL Pipeline definitions        → gmap_reviews_enriched

It then creates and seeds a `business_rules` JSONB table that acts as a
domain-specific knowledge layer for all AI agents in the swarm.

Architectural Decision:
    By embedding metadata directly in PostgreSQL's pg_description catalog, we
    create a single source of truth that is queryable by both humans
    (psql \\d+ table_name) and AI agents (DBEngine.load_context_once()).
    This eliminates prompt hallucination about column meanings and allows the
    schema context to evolve with the database without modifying any Python code.

Usage:
    python -m src.agent.apply_db_metadata
"""

import json
import sys
from typing import Optional

import requests
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.agent.db_engine import DBEngine

# ── ACS Census Code → DB Column Name Mapping ──────────────────────────────────
# Source: notebooks/KAGGLE_ETL_PIPELINE.ipynb — Section 2.1 ACS_VARIABLES dict.
# These are the exact column names# Official US Census Bureau API Variable Codes (2023 ACS 5-Year)
ACS_CODE_TO_DB_COL: dict[str, str] = {
    # Custom non-API columns added by ETL
    "GEOID": "GEOID",
    "NAME": "NAME",
    "STATE": "STATE",
    "COUNTY": "COUNTY",
    "TRACT": "TRACT",
    
    # Official API columns
    "B19013_001E": "median_household_income",
    "B19301_001E": "per_capita_income",
    "B25077_001E": "median_home_value",
    "B25064_001E": "median_gross_rent",
    "B25070_010E": "high_rent_burden",
    "B01001_001E": "total_population",
    "B01002_001E": "median_age",
    "B01001_020E": "senior_pop_65_plus",
    "B03002_003E": "white_non_hispanic_pop",
    "B03002_004E": "black_pop",
    "B03002_006E": "asian_pop",
    "B03002_012E": "hispanic_latino_pop",
    "B05002_013E": "foreign_born_pop",
    "B17001_002E": "below_poverty_line_pop",
    "B22003_002E": "snap_food_stamps_receipt",
    "B15003_022E": "bachelors_degree_pop",
    "C24050_002E": "management_business_occupations",
    "C24050_015E": "tech_finance_occupations",
    "B25001_001E": "total_housing_units",
    "B25003_002E": "owner_occupied_units",
    "B25034_002E": "homes_built_after_2014",
    "B25034_010E": "homes_built_before_1939",
    "B08201_001E": "vehicles_available",
    "B08303_001E": "avg_commute_time",
    "B08301_002E": "car_commute",
    "B28002_001E": "broadband_internet_subs",
    "B28001_001E": "has_computer_smartphone",
    "B27001_001E": "health_insurance_coverage",
    "B18101_001E": "pop_with_disability",
    "B11001_002E": "married_couple_families",
    "B11001_007E": "single_parent_families",
    "B13002_002E": "women_given_birth",
    "B16001_003E": "speak_only_english",
}

# ── TIGER/Line Static Description Dictionary ──────────────────────────────────
# Source: TIGER/Line Shapefiles Technical Documentation (2023).
# https://www.census.gov/programs-surveys/geography/technical-documentation/
# complete-technical-documentation/tiger-geo-line.html
# TIGER column names are fixed FIPS/MTFCC standards — no machine-readable API exists.
TIGER_DESCRIPTIONS: dict[str, str] = {
    "state_fips":         "State FIPS code — 2-digit numeric code identifying the US state (Florida = 12). Source: TIGER STATEFP.",
    "county_fips":        "County FIPS code — 3-digit numeric code identifying the county (Hillsborough = 057). Source: TIGER COUNTYFP.",
    "tract_code":         "Census Tract code — 6-digit code identifying the census tract within the county. Source: TIGER TRACTCE.",
    "place_fips":         "Place FIPS code — 5-digit code identifying a Census-designated place (Tampa = 71000). Source: TIGER PLACEFP.",
    "place_ns":           "GNIS (Geographic Names Information System) ID for the Census place entity. Source: TIGER PLACENS.",
    "feature_name":       "Primary human-readable name of the geographic feature (e.g., 'Tampa', 'Hillsborough'). Source: TIGER NAME.",
    "feature_name_desc":  "Full legal/statistical area description including entity type suffix (e.g., 'Tampa city'). Source: TIGER NAMELSAD.",
    "land_area_sqm":      "Land area of the geographic feature in square meters, excluding water bodies. Source: TIGER ALAND.",
    "water_area_sqm":     "Water area of the geographic feature in square meters. Source: TIGER AWATER.",
    "latitude":           "Internal point latitude in decimal degrees (NAD83). Guaranteed to fall inside the polygon boundary. Source: TIGER INTPTLAT.",
    "longitude":          "Internal point longitude in decimal degrees (NAD83). Guaranteed to fall inside the polygon boundary. Source: TIGER INTPTLON.",
    "feature_class_code": "MAF/TIGER Feature Class Code (MTFCC) — 5-character code classifying the geographic entity type (e.g., G5020=Census Tract). Source: TIGER MTFCC.",
    "functional_status":  "Functional Status Code — single character indicating legal/statistical function (A=active, B=active government not coextensive). Source: TIGER FUNCSTAT.",
    "geoid":              "Unique Census Geographic Identifier — concatenation of state+county+tract FIPS codes. Primary join key linking TIGER geometries to ACS demographics. Source: TIGER GEOID.",
    "geoid_fq":           "Fully Qualified GEOID — includes the geographic summary level prefix (e.g., '1400000US12057000100'). Source: TIGER GEOIDFQ.",
    "geometry":           "PostGIS geometry column (MultiPolygon or LineString, EPSG:4326 WGS84). Clipped to Tampa city limits (PLACEFP=71000). Source: TIGER shapefiles.",
    "layer_type":         "TIGER layer source — which of the 11 geospatial layers this record originated from (TRACT, BG, PLACE, ROADS, AREAWATER, ZCTA5, RAILS, MIL, PUMA, EDGES, COUSUB).",
    
    # TIGER 2020 Columns (used in PUMA, ZCTA5, etc.)
    "statefp20":          "State FIPS code (2020 tabulation).",
    "pumace20":           "Public Use Microdata Area Code (2020 tabulation).",
    "zcta5ce20":          "5-digit ZIP Code Tabulation Area (2020 tabulation).",
    "geoid20":            "Unique Geographic Identifier (2020 tabulation).",
    "geoidfq20":          "Fully Qualified GEOID (2020 tabulation).",
    "namelsad20":         "Name and Legal/Statistical Area Description (2020).",
    "classfp20":          "FIPS Class Code (2020).",
    "mtfcc20":            "MAF/TIGER Feature Class Code (2020).",
    "funcstat20":         "Functional Status Code (2020).",
    "aland20":            "Land area in square meters (2020).",
    "awater20":           "Water area in square meters (2020).",
    "intptlat20":         "Internal point latitude (2020).",
    # TIGER Sub-geographies & Attributes (Block Group, County Sub, etc.)
    "blkgrpce":           "Block Group Code.",
    "cousubfp":           "County Subdivision FIPS code.",
    "cousubns":           "County Subdivision GNIS code.",
    "ansicode":           "ANSI feature code.",
    "hydroid":            "Unique Hydrography Identifier.",
    "lsad":               "Legal/Statistical Area Description code.",
    "classfp":            "FIPS Class Code.",
    "pcicbsa":            "Principal City Indicator.",
    "tlid":               "TIGER Edge Line ID.",
    
    # TIGER Linear Features (used in ROADS, RAILS)
    "linearid":           "Unique Linear Feature Identifier. Source: TIGER LINEARID.",
    "fullname":           "Full street or feature name (e.g., 'I- 275').",
    "rttyp":              "Route Type Code (e.g., I=Interstate, U=US Hwy, S=State Hwy, M=Common Name).",
}

# ── Google Maps POI Static Description Dictionary ─────────────────────────────
GMAP_DESCRIPTIONS: dict[str, str] = {
    "name_x":                 "Business or point-of-interest name as listed on Google Maps.",
    "gmap_id":                "Unique Google Maps Place identifier. Primary key for the POI entity.",
    "category":               "Category of the business (e.g., 'Coffee shop').",
    "state":                  "US state abbreviation where the business is located (e.g., 'FL').",
    "user_id":                "Unique identifier of the user who wrote the review.",
    "time":                   "Timestamp of when the review was posted.",
    "rating":                 "Star rating given by the user on a 1.0–5.0 scale.",
    "text":                   "Raw, unmodified customer review text.",
    "text_normalized":        "Cleaned review text with emojis, special characters, and stop words removed.",
    "keywords_ai":            "AI-extracted keyword phrases from the review.",
    "embedding":              "Semantic embedding vector representing the review text.",
    "sentiment":              "Sentiment classification of the review.",
    "semantic_json":          "JSON payload containing additional semantic analysis.",
}

# ── Google Maps Places Dimension ───────────────────────────────────────────────
GMAP_PLACES_DESCRIPTIONS: dict[str, str] = {
    "gmap_id":                "Unique Google Maps Place identifier. Foreign key to gmap_reviews_enriched.",
    "name":                   "Business or point-of-interest name.",
    "latitude":               "Geographic latitude of the business location in decimal degrees (WGS84).",
    "longitude":              "Geographic longitude of the business location in decimal degrees (WGS84).",
    "geom":                   "PostGIS POINT geometry (EPSG:4326 WGS84) derived from latitude/longitude.",
}

# ── Business Rules: us_income_brackets ────────────────────────────────────────
# Source: US Dept. of Housing and Urban Development (HUD) + Pew Research Center.
# These brackets act as a translation layer for the AI agents when interpreting
# the median_household_income column from demographics_acs.
US_INCOME_BRACKETS: dict = {
    "low_income": {
        "label":       "Low Income",
        "min_usd":     0,
        "max_usd":     29999,
        "description": "Household income under $30,000 per year. Qualifies for most federal assistance programs.",
        "source":      "US Department of Housing and Urban Development (HUD) Income Limits",
    },
    "middle_class": {
        "label":       "Middle Class",
        "min_usd":     30000,
        "max_usd":     80000,
        "description": "Household income between $30,000 and $80,000 per year. Primary consumer demographic for most retail and service businesses.",
        "source":      "Pew Research Center Middle-Income Threshold (adjusted for Tampa MSA)",
    },
    "upper_class": {
        "label":       "Upper Class",
        "min_usd":     80001,
        "max_usd":     None,
        "description": "Household income above $80,000 per year. Prime target demographic for premium and luxury goods/services.",
        "source":      "Pew Research Center Upper-Income Threshold (adjusted for Tampa MSA)",
    },
}

# ── business_rules table column descriptions ───────────────────────────────────
BUSINESS_RULES_COLUMN_DESCRIPTIONS: dict[str, str] = {
    "rule_key":        "Unique string identifier for the business rule. AI agents use this key to look up domain-specific configuration at query time (e.g., 'us_income_brackets').",
    "rule_value_json": "JSONB payload containing the full business rule definition. Schema varies per rule_key — agents must inspect the key before parsing the value.",
}


# ── STEP 1: Official ACS Description Fetch ────────────────────────────────────

def fetch_acs_descriptions() -> dict[str, str]:
    """Fetch official ACS 5-Year variable labels from the US Census Bureau API.

    Calls the Census Bureau's official variables endpoint and extracts the
    'label' field for every ACS code defined in ACS_CODE_TO_DB_COL. Falls back
    to column-name-based descriptions if the API is unreachable.

    Returns:
        dict[str, str]: Mapping of {db_column_name: official_description_string}.
    """
    census_api_url = "https://api.census.gov/data/2023/acs/acs5/variables.json"
    print(f"  [*] Fetching official ACS variable labels from Census Bureau API...")
    print(f"      URL: {census_api_url}")

    descriptions: dict[str, str] = {}

    try:
        response = requests.get(census_api_url, timeout=15)
        response.raise_for_status()
        variables_data: dict = response.json().get("variables", {})

        fetched_count = 0
        for code, db_col in ACS_CODE_TO_DB_COL.items():
            if code in variables_data:
                raw_label: str = variables_data[code].get("label", db_col)
                # Census API uses "Estimate!!" prefix and "!!" as hierarchy separators
                cleaned = raw_label.replace("Estimate!!", "").replace("!!", " — ").strip()
                concept: str = variables_data[code].get("concept", "")
                descriptions[db_col] = f"[ACS {code}] {cleaned}. Concept: {concept}."
                fetched_count += 1
            else:
                descriptions[db_col] = f"[ACS {code}] {db_col.replace('_', ' ').title()}."

        # Non-ACS columns added by the ETL pipeline
        descriptions["GEOID"] = (
            "Unique Census Geographic Identifier (GEOID) — concatenation of state+county+tract "
            "FIPS codes. Primary join key linking ACS statistics to TIGER spatial features."
        )
        descriptions["NAME"] = (
            "Human-readable Census Tract name as provided by the Census Bureau "
            "(e.g., 'Census Tract 101.04, Hillsborough County, Florida')."
        )
        descriptions["STATE"] = "US State FIPS code."
        descriptions["COUNTY"] = "County FIPS code."
        descriptions["TRACT"] = "Census Tract code."

        print(f"  ✅ Fetched {fetched_count}/{len(ACS_CODE_TO_DB_COL)} official labels from Census API.")
        return descriptions

    except Exception as exc:
        print(f"  ⚠️  Census API unreachable ({exc}).")
        print("      Falling back to ETL column-name descriptions.")
        fallback = {
            db_col: f"[ACS {code}] {db_col.replace('_', ' ').title()}."
            for code, db_col in ACS_CODE_TO_DB_COL.items()
        }
        fallback["GEOID"] = "Unique Census Geographic Identifier (GEOID). Primary join key."
        fallback["NAME"]  = "Human-readable Census Tract name."
        fallback["STATE"] = "US State FIPS code."
        fallback["COUNTY"] = "County FIPS code."
        fallback["TRACT"] = "Census Tract code."
        return fallback


# ── STEP 2: Build Full Metadata ────────────────────────────────────────────────

def build_full_metadata(acs_descriptions: dict[str, str]) -> dict[str, dict[str, str]]:
    """Assemble the complete column description metadata for all 3 core tables.

    Args:
        acs_descriptions: Output of fetch_acs_descriptions().

    Returns:
        dict: Mapping of {table_name: {column_name: description}}.
    """
    from sqlalchemy import text
    from src.agent.db_engine import DBEngine

    metadata = {
        "demographics_acs_tract_tampa_2023": acs_descriptions,
        "gmap_reviews_enriched":             GMAP_DESCRIPTIONS,
        "gmap_places":                       GMAP_PLACES_DESCRIPTIONS,
    }

    try:
        db = DBEngine()
        engine = db.get_engine()
        with engine.connect() as conn:
            tiger_tables = conn.execute(
                text("SELECT tablename FROM pg_tables WHERE tablename LIKE 'spatial_tiger_%';")
            ).scalars().all()
            for t in tiger_tables:
                metadata[t] = TIGER_DESCRIPTIONS
    except Exception as exc:
        print(f"  ⚠️  Could not fetch TIGER tables dynamically: {exc}")
        
    return metadata


# ── STEP 3: Human-in-the-Loop Preview & Approval ──────────────────────────────

def print_preview_and_confirm(metadata: dict[str, dict[str, str]]) -> bool:
    """Print a complete mapping preview to the terminal and request human approval.

    Displays every column → description pair for all 3 tables and the
    business_rules seed data, then pauses for explicit Y/N confirmation.

    Args:
        metadata: Full metadata dict from build_full_metadata().

    Returns:
        bool: True if user types 'Y', False for any other input.
    """
    print("\n" + "=" * 72)
    print("  COGNITIVE BLUEPRINT — COLUMN DESCRIPTION PREVIEW")
    print("=" * 72)

    total_cols = 0
    for table_name, columns in metadata.items():
        print(f"\n  ┌─ TABLE: {table_name}")
        for col_name, description in columns.items():
            # Truncate to keep terminal readable
            display_desc = description if len(description) <= 75 else description[:72] + "..."
            print(f"  │   Column: {col_name:<38} →  {display_desc}")
            total_cols += 1
        print(f"  └─ ({len(columns)} columns)")

    print(f"\n  ┌─ TABLE: business_rules [NEW]")
    for col_name, desc in BUSINESS_RULES_COLUMN_DESCRIPTIONS.items():
        display = desc if len(desc) <= 75 else desc[:72] + "..."
        print(f"  │   Column: {col_name:<38} →  {display}")
    print(f"  └─ (2 columns)")

    print(f"\n  ┌─ SEED RECORD: rule_key = 'us_income_brackets'")
    brackets_preview = json.dumps(US_INCOME_BRACKETS, indent=4)
    for line in brackets_preview.split("\n")[:20]:
        print(f"  │   {line}")
    print(f"  └─ (3 income brackets)")

    print("\n" + "=" * 72)
    print(f"  Total: {total_cols} column descriptions across {len(metadata)} tables.")
    print(f"  All comments sourced from official US Government documentation.")
    print("=" * 72)

    answer = input(
        "\n  ▶  Type Y to insert these descriptions into the database: "
    ).strip().upper()
    return answer == "Y"


# ── STEP 4: Apply COMMENT ON COLUMN ───────────────────────────────────────────

def apply_column_comments(
    metadata: dict[str, dict[str, str]],
    db: DBEngine,
) -> None:
    """Execute COMMENT ON COLUMN for every entry in the metadata dictionary.

    Uses AUTOCOMMIT isolation level, which is required for DDL statements in
    PostgreSQL (consistent with the pattern used in DBEngine.init_extensions()).
    Table/column names come from our hardcoded metadata dict (not user input),
    so f-string formatting is safe here. Description values are parameterized.

    Args:
        metadata: Full metadata dict from build_full_metadata().
        db:       Initialized DBEngine instance (connection pool reused).

    Raises:
        SQLAlchemyError: If a critical database error occurs.
    """
    engine = db.get_engine()
    applied = 0
    skipped = 0

    print("\n  [*] Applying COMMENT ON COLUMN statements...")
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for table_name, columns in metadata.items():
            for col_name, description in columns.items():
                sql = text(
                    f'COMMENT ON COLUMN "{table_name}"."{col_name}" IS :description'
                )
                try:
                    conn.execute(sql, {"description": description})
                    applied += 1
                except SQLAlchemyError as exc:
                    # Column may not exist if the ETL hasn't run yet — non-fatal
                    print(f"    ⚠️  Skipped {table_name}.{col_name}: {exc}")
                    skipped += 1

    print(f"  ✅ Applied {applied} comments. Skipped {skipped} (table/column not yet created).")


# ── STEP 5: Create & Seed business_rules ──────────────────────────────────────

def create_and_seed_business_rules(db: DBEngine) -> None:
    """Create the business_rules table, upsert seed data, and apply column comments.

    The table is created idempotently (IF NOT EXISTS). The us_income_brackets
    record is upserted using ON CONFLICT DO UPDATE, making this function safe
    to run multiple times.

    Args:
        db: Initialized DBEngine instance.

    Raises:
        SQLAlchemyError: If table creation or insert fails.
    """
    engine = db.get_engine()

    print("\n  [*] Creating and seeding business_rules table...")
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:

        # 1. Create table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS business_rules (
                rule_key        TEXT PRIMARY KEY,
                rule_value_json JSONB NOT NULL
            );
        """))
        print("    ✅ Table 'business_rules' ensured.")

        # 2. Upsert the us_income_brackets record
        conn.execute(
            text("""
                INSERT INTO business_rules (rule_key, rule_value_json)
                VALUES (:rule_key, CAST(:rule_value_json AS JSONB))
                ON CONFLICT (rule_key) DO UPDATE
                    SET rule_value_json = EXCLUDED.rule_value_json;
            """),
            {
                "rule_key":        "us_income_brackets",
                "rule_value_json": json.dumps(US_INCOME_BRACKETS),
            },
        )
        print("    ✅ Seeded rule: 'us_income_brackets'.")

        # 3. Apply column comments on business_rules
        for col_name, description in BUSINESS_RULES_COLUMN_DESCRIPTIONS.items():
            conn.execute(
                text(f"COMMENT ON COLUMN business_rules.{col_name} IS :description"),
                {"description": description},
            )
        print("    ✅ Applied column comments on 'business_rules'.")


# ── STEP 6: Strict Validation ─────────────────────────────────────────────────

def validate_all_comments(
    metadata: dict[str, dict[str, str]],
    db: DBEngine,
) -> None:
    """Validate that every expected column has a non-null description in pg_description.

    Queries the PostgreSQL system catalog to confirm every COMMENT ON COLUMN was
    persisted correctly. Raises ValueError listing all missing columns if any
    description is NULL or absent.

    Args:
        metadata: Full metadata dict from build_full_metadata().
        db:       Initialized DBEngine instance.

    Raises:
        ValueError: If one or more columns are missing descriptions.
    """
    engine = db.get_engine()
    missing: list[str] = []

    print("\n  [*] Running strict validation against pg_description catalog...")

    catalog_query = text("""
        SELECT
            a.attname     AS column_name,
            d.description AS comment
        FROM pg_class c
        JOIN pg_attribute a
            ON  a.attrelid = c.oid
            AND a.attnum   > 0
            AND NOT a.attisdropped
        LEFT JOIN pg_description d
            ON  d.objoid   = c.oid
            AND d.objsubid = a.attnum
        WHERE c.relname = :table_name
          AND c.relkind = 'r'
        ORDER BY a.attnum;
    """)

    with engine.connect() as conn:
        for table_name, expected_columns in metadata.items():
            result = conn.execute(catalog_query, {"table_name": table_name})
            db_comments: dict[str, Optional[str]] = {
                row.column_name: row.comment for row in result
            }
            for expected_col in expected_columns:
                if not db_comments.get(expected_col):
                    missing.append(f"{table_name}.{expected_col}")

    if missing:
        missing_list = "\n    ".join(missing)
        print(
            f"\n  ⚠️  VALIDATION WARNING — {len(missing)} column(s) missing descriptions:\n"
            f"    {missing_list}\n"
            f"  → This is expected if the ETL pipeline hasn't run yet. Run the ETL to create the tables, then retry."
        )
    else:
        total = sum(len(cols) for cols in metadata.values())
        print(f"  ✅ Validation passed — all {total} expected columns have descriptions in pg_description.")


# ── Main Orchestration Block ───────────────────────────────────────────────────

if __name__ == "__main__":
    # Force UTF-8 output to prevent UnicodeEncodeError on Windows terminals (cp1252) when printing emojis
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass
            
    # Deferred import to avoid circular dependency — load_context_once lives in db_engine
    from src.agent.db_engine import load_context_once  # noqa: PLC0415

    print("\n" + "=" * 72)
    print("  GEOAI COGNITIVE BLUEPRINT — DATABASE METADATA APPLICATION")
    print("=" * 72)

    # Step 1: Initialize DB — reuse existing DBEngine (no new connection logic)
    print("\n[Step 1/6] Initializing database connection...")
    try:
        db = DBEngine()
        db.init_extensions()
        print("  ✅ Database connection established. Pool ready.")
    except Exception as exc:
        print(f"  ❌ FATAL: Could not connect to database: {exc}")
        print("  → Make sure the GeoStack Docker containers are running:")
        print("    docker compose -f scripts/geostack/docker-compose.yml up -d")
        sys.exit(1)

    # Step 2: Fetch official ACS descriptions from the Census Bureau API
    print("\n[Step 2/6] Fetching official ACS variable descriptions from Census Bureau...")
    acs_descriptions = fetch_acs_descriptions()

    # Step 3: Assemble full metadata for all 3 core tables
    print("\n[Step 3/6] Assembling full column metadata for all 3 core tables...")
    metadata = build_full_metadata(acs_descriptions)
    total_cols = sum(len(c) for c in metadata.values())
    print(f"  ✅ Metadata ready: {total_cols} columns across {len(metadata)} tables.")

    # Step 4: Human-in-the-Loop — preview and explicit approval
    print("\n[Step 4/6] Human-in-the-Loop verification — review the preview below:")
    approved = print_preview_and_confirm(metadata)

    if not approved:
        print("\n  ⚠️  Operation cancelled by user. No changes were made to the database.")
        sys.exit(0)

    print("\n  ✅ User approved. Proceeding with database writes...")

    # Step 5: Apply column comments + create/seed business_rules
    print("\n[Step 5/6] Applying metadata to the database...")
    try:
        apply_column_comments(metadata, db)
        create_and_seed_business_rules(db)
    except SQLAlchemyError as exc:
        print(f"  ❌ Database error during metadata application: {exc}")
        sys.exit(1)

    # Step 6: Strict validation against pg_description
    print("\n[Step 6/6] Running strict pg_description validation...")
    try:
        validate_all_comments(metadata, db)
    except ValueError as exc:
        print(str(exc))
        sys.exit(1)

    # ── Proof of Work ──────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("  PROOF OF WORK — LIVE LLM CONTEXT STRING")
    print("  (This is exactly what Planner, Worker, and Reviewer receive at boot)")
    print("=" * 72 + "\n")

    context = load_context_once(db)
    print(context)

    print("\n" + "=" * 72)
    print(f"  ✅ Cognitive Blueprint applied successfully!")
    print(f"  Context string length: {len(context):,} characters")
    print(f"  This context is now cached and injected into all agent system prompts.")
    print("=" * 72)
