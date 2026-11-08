"""
clean_data.py - Cleaning and feature-engineering pipeline
=========================================================
Project : Hospital Inpatient Discharges Dashboard (NY SPARCS 2021)

What this script does
---------------------
1. Reads the raw 2.1M-row SPARCS CSV in chunks (so it fits in free-tier RAM).
2. Cleans every chunk:
     - strips/renames columns to readable snake_case names
     - converts money strings such as "27,606.16" to floats
     - converts Length of Stay (including the "120 +" top-code) to integers
     - removes invalid records (non-positive stay, charges or costs)
     - standardises categorical fields (gender, age group, severity, ZIP ...)
     - maps CCSR diagnosis codes to readable body-system categories
     - drops irrelevant / null-heavy columns (e.g. Birth Weight, ~80+% empty)
3. Engineers features (charge per day, cost per day, charge-to-cost ratio,
   length-of-stay band, number of payers, procedure flag ...).
4. Handles outliers with Tukey fences on log10(charges) within each severity
   level: extreme outliers (3 x IQR) are removed, mild ones (1.5 x IQR) flagged.
5. Draws a reproducible random sample (default 400,000 rows) that is small
   enough for GitHub (<100 MB) and Streamlit Cloud's free tier (~1 GB RAM).
6. Validates the sample against the full cleaned data and writes a JSON
   cleaning report that the dashboard displays in its "Data & Method" tab.

Usage
-----
    python scripts/clean_data.py --input "/path/to/raw.csv" --outdir data
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
RENAME = {
    "Hospital Service Area": "service_area",
    "Hospital County": "county",
    "Facility Name": "facility",
    "Age Group": "age_group",
    "Zip Code - 3 digits": "zip3",
    "Gender": "gender",
    "Race": "race",
    "Ethnicity": "ethnicity",
    "Length of Stay": "los",
    "Type of Admission": "admission_type",
    "Patient Disposition": "disposition",
    "CCSR Diagnosis Code": "dx_code",
    "CCSR Diagnosis Description": "dx_description",
    "CCSR Procedure Code": "proc_code",
    "CCSR Procedure Description": "proc_description",
    "APR MDC Description": "mdc_description",
    "APR Severity of Illness Code": "severity_code",
    "APR Severity of Illness Description": "severity",
    "APR Risk of Mortality": "mortality_risk",
    "APR Medical Surgical Description": "med_surg",
    "Payment Typology 1": "payer_primary",
    "Payment Typology 2": "payer_2",
    "Payment Typology 3": "payer_3",
    "Birth Weight": "birth_weight",
    "Emergency Department Indicator": "ed_indicator",
    "Total Charges": "total_charges",
    "Total Costs": "total_costs",
}
# Raw columns that are intentionally ignored (identifiers / constants / duplicates)
IGNORED_RAW = [
    "Operating Certificate Number", "Permanent Facility Id", "Discharge Year",
    "APR DRG Code", "APR DRG Description", "APR MDC Code",
]

# CCSR diagnosis prefix -> readable clinical category
DX_CATEGORY = {
    "BLD": "Blood & Immune", "CIR": "Circulatory", "DEN": "Dental",
    "DIG": "Digestive", "EAR": "Ear", "END": "Endocrine & Metabolic",
    "EXT": "External Causes", "EYE": "Eye", "FAC": "Health Service Factors",
    "GEN": "Genitourinary", "INF": "Infectious Disease",
    "INJ": "Injury & Poisoning", "MAL": "Congenital Anomalies",
    "MBD": "Mental & Behavioural", "MUS": "Musculoskeletal",
    "NEO": "Neoplasms (Cancer)", "NVS": "Nervous System",
    "PNL": "Perinatal / Newborn", "PRG": "Pregnancy & Childbirth",
    "RSP": "Respiratory", "SKN": "Skin", "SYM": "Symptoms & Signs",
}
GENDER_MAP = {"F": "Female", "M": "Male", "U": "Unknown"}
AGE_ORDER = ["0 to 17", "18 to 29", "30 to 49", "50 to 69", "70 or Older"]
SEVERITY_ORDER = ["Minor", "Moderate", "Major", "Extreme"]
LOS_BINS = [0, 1, 3, 7, 14, 30, np.inf]
LOS_LABELS = ["1 day", "2-3 days", "4-7 days", "8-14 days", "15-30 days", "31+ days"]

KEEP_COLS = [
    "service_area", "county", "facility", "age_group", "zip3", "gender", "race",
    "ethnicity", "admission_type", "disposition", "dx_code", "dx_description",
    "dx_category", "proc_description", "has_procedure", "mdc_description",
    "severity_code", "severity", "mortality_risk", "med_surg", "payer_primary",
    "n_payers", "ed_indicator", "los", "los_band", "total_charges", "total_costs",
    "charge_per_day", "cost_per_day", "charge_to_cost_ratio",
    "charge_outlier", "los_outlier", "facility_redacted",
]
CATEGORICAL_COLS = [
    "service_area", "county", "facility", "age_group", "zip3", "gender", "race",
    "ethnicity", "admission_type", "disposition", "dx_code", "dx_description",
    "dx_category", "proc_description", "mdc_description", "severity",
    "mortality_risk", "med_surg", "payer_primary", "ed_indicator",
]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def to_number(series: pd.Series) -> pd.Series:
    """'27,606.16' -> 27606.16 ; '120 +' -> 120 ; junk -> NaN."""
    cleaned = series.astype(str).str.replace(r"[^0-9.\-]", "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce")


def clean_chunk(raw: pd.DataFrame, stats: dict) -> pd.DataFrame:
    """Clean and enrich one chunk of the raw file."""
    raw = raw.rename(columns=lambda c: c.strip())
    df = raw[[c for c in RENAME if c in raw.columns]].rename(columns=RENAME)
    stats["rows_read"] += len(df)

    # ---- numeric conversions --------------------------------------------
    df["los"] = to_number(df["los"])
    df["total_charges"] = to_number(df["total_charges"])
    df["total_costs"] = to_number(df["total_costs"])
    df["severity_code"] = pd.to_numeric(df["severity_code"], errors="coerce")

    # ---- remove invalid records (sequential, so counts do not overlap) ----
    rules = [
        ("invalid_length_of_stay", lambda d: d["los"].isna() | (d["los"] <= 0)),
        ("invalid_total_charges", lambda d: d["total_charges"].isna() | (d["total_charges"] <= 0)),
        ("invalid_total_costs", lambda d: d["total_costs"].isna() | (d["total_costs"] <= 0)),
    ]
    for reason, rule in rules:
        bad = rule(df)                      # evaluated on the current (already filtered) frame
        stats["dropped"][reason] += int(bad.sum())
        df = df[~bad]
    df["los"] = df["los"].astype("int32")

    # ---- standardise text fields ------------------------------------------
    for col in ["service_area", "county", "facility", "age_group", "gender", "race",
                "ethnicity", "admission_type", "disposition", "dx_code",
                "dx_description", "proc_description", "mdc_description",
                "severity", "mortality_risk", "med_surg", "payer_primary",
                "ed_indicator", "zip3"]:
        df[col] = df[col].astype("string").str.strip()

    df["gender"] = df["gender"].map(GENDER_MAP).fillna("Unknown")
    df["service_area"] = df["service_area"].fillna("Unknown")
    df["county"] = df["county"].fillna("Unknown")
    df["zip3"] = df["zip3"].replace({"OOS": "Out of State"}).fillna("Unknown")
    df["facility_redacted"] = df["facility"].str.contains("Redacted", case=False, na=False)
    df.loc[df["facility_redacted"], "facility"] = "Redacted (confidential)"
    df["facility"] = df["facility"].fillna("Redacted (confidential)")

    # readable diagnosis / procedure text + clinical category
    df["dx_description"] = df["dx_description"].str.capitalize()
    df["proc_description"] = df["proc_description"].str.capitalize()
    df["mdc_description"] = df["mdc_description"].str.capitalize()
    df["dx_category"] = df["dx_code"].str[:3].map(DX_CATEGORY).fillna("Other")

    # ---- feature engineering ------------------------------------------------
    df["has_procedure"] = df["proc_description"].notna()
    df["n_payers"] = df[["payer_primary", "payer_2", "payer_3"]].notna().sum(axis=1).astype("int8")
    df["los_band"] = pd.cut(df["los"], bins=LOS_BINS, labels=LOS_LABELS)
    df["charge_per_day"] = df["total_charges"] / df["los"]
    df["cost_per_day"] = df["total_costs"] / df["los"]
    df["charge_to_cost_ratio"] = df["total_charges"] / df["total_costs"]
    df["proc_description"] = df["proc_description"].fillna("No procedure recorded")
    return df


def flag_and_remove_outliers(df: pd.DataFrame, stats: dict) -> pd.DataFrame:
    """Tukey fences on log10(charges) and log10(LOS) within each severity level."""
    log_ch = np.log10(df["total_charges"])
    log_los = np.log10(df["los"])
    sev = df["severity"]

    def fences(values: pd.Series, k: float):
        q1 = values.groupby(sev).transform(lambda s: s.quantile(0.25))
        q3 = values.groupby(sev).transform(lambda s: s.quantile(0.75))
        iqr = q3 - q1
        return (values < q1 - k * iqr) | (values > q3 + k * iqr)

    df["charge_outlier"] = fences(log_ch, 1.5)      # mild + extreme (flagged)
    df["los_outlier"] = fences(log_los, 1.5)        # flagged only
    extreme = fences(log_ch, 3.0)                   # extreme (removed)

    stats["charge_outliers_flagged_mild"] = int((df["charge_outlier"] & ~extreme).sum())
    stats["dropped"]["extreme_charge_outliers_3xIQR"] = int(extreme.sum())
    stats["los_outliers_flagged"] = int(df["los_outlier"].sum())
    return df[~extreme].copy()


def finalise_types(df: pd.DataFrame) -> pd.DataFrame:
    """Compact dtypes (category / float32) so the app loads quickly."""
    df = df[KEEP_COLS].copy()
    for col in CATEGORICAL_COLS:
        df[col] = df[col].astype("string").astype("category")
    df["age_group"] = pd.Categorical(df["age_group"].astype(str), categories=AGE_ORDER, ordered=True)
    df["severity"] = pd.Categorical(df["severity"].astype(str), categories=SEVERITY_ORDER, ordered=True)
    df["mortality_risk"] = pd.Categorical(df["mortality_risk"].astype(str), categories=SEVERITY_ORDER, ordered=True)
    df["severity_code"] = df["severity_code"].astype("int8")
    for col in ["total_charges", "total_costs", "charge_per_day", "cost_per_day", "charge_to_cost_ratio"]:
        df[col] = df[col].astype("float32")
    return df.reset_index(drop=True)


def kpis(df: pd.DataFrame) -> dict:
    return {
        "rows": int(len(df)),
        "avg_los": round(float(df["los"].mean()), 3),
        "median_los": float(df["los"].median()),
        "avg_charges": round(float(df["total_charges"].mean()), 2),
        "avg_costs": round(float(df["total_costs"].mean()), 2),
        "pct_emergency_dept": round(float((df["ed_indicator"] == "Y").mean() * 100), 3),
        "pct_expired": round(float((df["disposition"] == "Expired").mean() * 100), 3),
    }


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="Path to the raw SPARCS CSV")
    ap.add_argument("--outdir", default="data", help="Output folder")
    ap.add_argument("--sample-size", type=int, default=400_000)
    ap.add_argument("--chunksize", type=int, default=250_000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    stats = {"rows_read": 0, "dropped": {"invalid_length_of_stay": 0, "invalid_total_charges": 0,
                                         "invalid_total_costs": 0}}
    null_counts, parts = None, []

    print("Step 1/5  Reading and cleaning in chunks ...")
    for i, chunk in enumerate(pd.read_csv(args.input, dtype=str, chunksize=args.chunksize,
                                          keep_default_na=True, encoding_errors="replace")):
        chunk.columns = [c.strip() for c in chunk.columns]
        nc = chunk.isna().sum()
        null_counts = nc if null_counts is None else null_counts.add(nc, fill_value=0)
        parts.append(clean_chunk(chunk, stats))
        print(f"   chunk {i + 1}: {stats['rows_read']:,} rows read")

    print("Step 2/5  Combining chunks and handling outliers ...")
    df = pd.concat(parts, ignore_index=True)
    del parts
    stats["rows_after_basic_cleaning"] = int(len(df))
    df = flag_and_remove_outliers(df, stats)

    print("Step 3/5  Optimising data types ...")
    df = finalise_types(df)
    stats["rows_clean_final"] = int(len(df))

    print("Step 4/5  Sampling and validating ...")
    n = min(args.sample_size, len(df))
    sample = df.sample(n=n, random_state=args.seed).reset_index(drop=True)
    full_k, samp_k = kpis(df), kpis(sample)
    validation = {
        key: {"full": full_k[key], "sample": samp_k[key],
              "pct_diff": round(abs(samp_k[key] - full_k[key]) / full_k[key] * 100, 3) if full_k[key] else 0.0}
        for key in full_k if key != "rows"
    }

    print("Step 5/5  Saving ...")
    try:
        sample.to_parquet(out / "discharges_clean.parquet", compression="zstd", index=False)
        data_file = "discharges_clean.parquet"
    except ImportError:                              # pyarrow not installed
        sample.to_csv(out / "discharges_clean.csv.gz", index=False, compression="gzip")
        data_file = "discharges_clean.csv.gz"

    birth_weight_null = float(null_counts.get("Birth Weight", 0) / max(stats["rows_read"], 1) * 100)
    report = {
        "source": "NY SPARCS Hospital Inpatient Discharges (De-Identified) 2021",
        "data_file": data_file,
        "raw_rows": stats["rows_read"],
        "rows_after_basic_cleaning": stats["rows_after_basic_cleaning"],
        "rows_clean_final": stats["rows_clean_final"],
        "rows_in_app_sample": int(n),
        "sample_scale_factor": round(stats["rows_clean_final"] / n, 4),
        "dropped": stats["dropped"],
        "charge_outliers_flagged_mild": stats["charge_outliers_flagged_mild"],
        "los_outliers_flagged": stats["los_outliers_flagged"],
        "birth_weight_pct_null": round(birth_weight_null, 2),
        "columns_dropped": ["Birth Weight (null-heavy)", "Payment Typology 2/3 (kept only as n_payers)"] + IGNORED_RAW,
        "kpis_full_clean_data": full_k,
        "sample_validation": validation,
        "random_seed": args.seed,
    }
    (out / "cleaning_report.json").write_text(json.dumps(report, indent=2))
    size_mb = (out / data_file).stat().st_size / 1e6
    print(f"\nDone. {data_file}: {size_mb:.1f} MB | rows: {len(df):,} cleaned -> {n:,} in sample")
    print(json.dumps(report["dropped"], indent=2))


if __name__ == "__main__":
    main()
