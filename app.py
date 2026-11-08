"""
Hospital Inpatient Discharges Dashboard (NY SPARCS 2021)
Built for hospital administrators, clinicians and operations managers.
Run locally:  streamlit run app.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from scipy import stats

# --------------------------------------------------------------------------
# Page setup
# --------------------------------------------------------------------------
st.set_page_config(page_title="Hospital Discharges Dashboard", page_icon="🏥",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
    <style>
    div[data-testid="stMetric"] {border: 1px solid rgba(128,128,128,.25);
        border-radius: 10px; padding: 10px 14px;}
    .block-container {padding-top: 1.6rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

DATA_DIR = Path(__file__).parent / "data"
SEVERITY_ORDER = ["Minor", "Moderate", "Major", "Extreme"]
AGE_ORDER = ["0 to 17", "18 to 29", "30 to 49", "50 to 69", "70 or Older"]
LOS_ORDER = ["1 day", "2-3 days", "4-7 days", "8-14 days", "15-30 days", "31+ days"]
SEV_COLORS = {"Minor": "#2a9d8f", "Moderate": "#e9c46a", "Major": "#f4a261", "Extreme": "#e63946"}


# --------------------------------------------------------------------------
# Data loading (cached)
# --------------------------------------------------------------------------
@st.cache_data(show_spinner="Loading hospital discharge data ...")
def load_data():
    report_path = DATA_DIR / "cleaning_report.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    parquet, csv = DATA_DIR / "discharges_clean.parquet", DATA_DIR / "discharges_clean.csv.gz"
    df = pd.read_parquet(parquet) if parquet.exists() else pd.read_csv(csv)
    for col in df.select_dtypes(include=["object", "string"]).columns:
        df[col] = df[col].astype("category")
    df["age_group"] = pd.Categorical(df["age_group"].astype(str), categories=AGE_ORDER, ordered=True)
    df["severity"] = pd.Categorical(df["severity"].astype(str), categories=SEVERITY_ORDER, ordered=True)
    df["los_band"] = pd.Categorical(df["los_band"].astype(str), categories=LOS_ORDER, ordered=True)
    return df, report


try:
    df_all, report = load_data()
except Exception as exc:  # friendly message instead of a stack trace
    st.error("Could not load the cleaned data file from the `data/` folder. "
             "Run `python scripts/clean_data.py` first (see README).")
    st.exception(exc)
    st.stop()

SCALE = float(report.get("sample_scale_factor", 1.0))


# --------------------------------------------------------------------------
# Sidebar filters
# --------------------------------------------------------------------------
def options(col):
    return sorted(df_all[col].dropna().astype(str).unique().tolist())


FILTER_KEYS = ["f_county", "f_age", "f_gender", "f_sev", "f_adm", "f_payer",
               "f_dxcat", "f_medsurg", "f_ed", "f_los"]

with st.sidebar:
    st.title("🏥 Filters")
    st.caption("Leave a filter empty to include everything.")
    f_county = st.multiselect("Hospital county", options("county"), key="f_county")
    f_age = st.multiselect("Age group", AGE_ORDER, key="f_age")
    f_gender = st.multiselect("Gender", options("gender"), key="f_gender")
    f_sev = st.multiselect("Severity of illness", SEVERITY_ORDER, key="f_sev")
    f_adm = st.multiselect("Type of admission", options("admission_type"), key="f_adm")
    f_payer = st.multiselect("Primary payment type", options("payer_primary"), key="f_payer")
    f_dxcat = st.multiselect("Diagnosis category", options("dx_category"), key="f_dxcat")
    f_medsurg = st.radio("Medical / surgical", ["All", "Medical", "Surgical"], horizontal=True, key="f_medsurg")
    f_ed = st.radio("Via emergency department", ["All", "Yes", "No"], horizontal=True, key="f_ed")
    los_max = int(df_all["los"].max())
    f_los = st.slider("Length of stay (days)", 1, los_max, (1, los_max), key="f_los")

    def reset_filters():
        for k in FILTER_KEYS:
            st.session_state.pop(k, None)

    st.button("↺ Reset all filters", on_click=reset_filters)


def apply_filters(d: pd.DataFrame) -> pd.DataFrame:
    for col, sel in [("county", f_county), ("age_group", f_age), ("gender", f_gender),
                     ("severity", f_sev), ("admission_type", f_adm),
                     ("payer_primary", f_payer), ("dx_category", f_dxcat)]:
        if sel:
            d = d[d[col].isin(sel)]
    if f_medsurg != "All":
        d = d[d["med_surg"] == f_medsurg]
    if f_ed != "All":
        d = d[d["ed_indicator"] == ("Y" if f_ed == "Yes" else "N")]
    return d[(d["los"] >= f_los[0]) & (d["los"] <= f_los[1])]


df = apply_filters(df_all)

st.title("🏥 Hospital Inpatient Discharges Dashboard")
st.caption("New York SPARCS de-identified inpatient discharges, 2021 · designed for hospital "
           "administrators, clinicians and operations managers")

if df.empty:
    st.warning("No discharges match the current filters. Widen the filters in the sidebar.")
    st.stop()

# --------------------------------------------------------------------------
# KPI row
# --------------------------------------------------------------------------
k = st.columns(6)
k[0].metric("Discharges (est. full data)", f"{len(df) * SCALE:,.0f}",
            help=f"{len(df):,} rows in the filtered sample × scale factor {SCALE:.2f}")
k[1].metric("Avg length of stay", f"{df['los'].mean():.2f} days", help=f"Median: {df['los'].median():.0f} days")
k[2].metric("Avg charge", f"${df['total_charges'].mean():,.0f}")
k[3].metric("Avg cost", f"${df['total_costs'].mean():,.0f}")
k[4].metric("Charge-to-cost ratio", f"{df['total_charges'].sum() / df['total_costs'].sum():.2f}×",
            help="Total charges divided by total costs: how far billing exceeds actual cost")
k[5].metric("In-hospital mortality", f"{(df['disposition'] == 'Expired').mean() * 100:.2f}%")

tabs = st.tabs(["📊 Overview", "🩺 Diagnoses", "💰 Charges & Severity", "🏥 Facilities & Counties",
                "💳 Payers", "📐 Statistics", "🧠 Insights", "📘 Data & Method"])


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def group_stats(d, by, min_n=1):
    g = (d.groupby(by, observed=True)
          .agg(discharges=("los", "size"), avg_los=("los", "mean"), median_los=("los", "median"),
               avg_charges=("total_charges", "mean"), median_charges=("total_charges", "median"),
               total_charges=("total_charges", "sum"), avg_costs=("total_costs", "mean"))
          .reset_index())
    return g[g["discharges"] >= min_n]


def style(fig, height=430):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=50, b=10), legend_title_text="")
    return fig


# --------------------------------------------------------------------------
# TAB 1 - Overview  (Chart 5: histogram of length of stay)
# --------------------------------------------------------------------------
with tabs[0]:
    c1, c2 = st.columns([3, 2])
    with c1:
        cap = st.slider("Show stays up to (days)", 10, 120, 30, key="hist_cap",
                        help="Longer stays are grouped into the last bar so the shape stays readable.")
        log_y = st.checkbox("Log scale (y-axis)", value=False, key="hist_log")
        los = df["los"].clip(upper=cap)
        counts = np.bincount(los.astype(int), minlength=cap + 1)[1:]
        days = np.arange(1, cap + 1)
        fig = go.Figure(go.Bar(x=days, y=counts * SCALE, marker_color="#457b9d",
                               hovertemplate="Stay: %{x} days<br>Est. discharges: %{y:,.0f}<extra></extra>"))
        fig.add_vline(x=min(df["los"].median(), cap), line_dash="dash", line_color="#e63946",
                      annotation_text=f"median {df['los'].median():.0f} d", annotation_position="top right")
        fig.update_layout(title=f"Distribution of length of stay (last bar = {cap}+ days)",
                          xaxis_title="Length of stay (days)", yaxis_title="Estimated discharges", bargap=0.05)
        if log_y:
            fig.update_yaxes(type="log")
        st.plotly_chart(style(fig))
        st.caption("Chart 5 · The distribution is strongly right-skewed: most patients leave within a few "
                   "days, but a long tail of extended stays drives bed occupancy and cost.")
    with c2:
        adm = group_stats(df, "admission_type")
        fig = px.bar(adm.sort_values("discharges"), x="discharges", y="admission_type", orientation="h",
                     color="avg_los", color_continuous_scale="Blues", title="Admission type: volume and average stay",
                     labels={"discharges": "Sample discharges", "admission_type": "", "avg_los": "Avg stay (d)"})
        st.plotly_chart(style(fig, 260))
        band = df["los_band"].value_counts().reindex(LOS_ORDER).reset_index()
        band.columns = ["band", "n"]
        fig = px.bar(band, x="band", y="n", title="Stays by length band",
                     labels={"band": "", "n": "Sample discharges"}, color_discrete_sequence=["#2a9d8f"])
        st.plotly_chart(style(fig, 260))


# --------------------------------------------------------------------------
# TAB 2 - Diagnoses  (Chart 1: bar of average stay per diagnosis code)
# --------------------------------------------------------------------------
with tabs[1]:
    c1, c2, c3 = st.columns(3)
    top_n = c1.slider("Number of diagnoses", 5, 40, 15, key="dx_top")
    min_cases = c2.slider("Minimum cases per diagnosis", 5, 500, 50, key="dx_min",
                          help="Hides rare diagnoses whose averages are unreliable.")
    label_mode = c3.radio("Label by", ["Diagnosis code", "Description"], horizontal=True, key="dx_label")
    dx = group_stats(df, ["dx_code", "dx_description", "dx_category"], min_n=min_cases)
    if dx.empty:
        st.info("No diagnosis has enough cases under these filters. Lower the minimum.")
    else:
        dx = dx.sort_values("avg_los", ascending=False).head(top_n)
        dx["label"] = dx["dx_code"].astype(str) if label_mode == "Diagnosis code" else dx["dx_description"].astype(str)
        fig = px.bar(dx.sort_values("avg_los"), x="avg_los", y="label", orientation="h", color="dx_category",
                     hover_data={"dx_description": True, "discharges": ":,", "median_los": ":.1f",
                                 "avg_los": ":.2f", "label": False},
                     title=f"Top {len(dx)} diagnoses by average length of stay (min {min_cases} cases)",
                     labels={"avg_los": "Average length of stay (days)", "label": "", "dx_category": "Category"})
        overall = df["los"].mean()
        fig.add_vline(x=overall, line_dash="dash", line_color="grey",
                      annotation_text=f"overall mean {overall:.1f} d")
        st.plotly_chart(style(fig, 140 + 26 * len(dx)))
        st.caption("Chart 1 · Diagnoses at the top consume the most bed-days per patient: priority targets "
                   "for discharge planning and length-of-stay reduction programmes.")
        with st.expander("Table: diagnosis details"):
            show = dx[["dx_code", "dx_description", "dx_category", "discharges", "avg_los", "median_los",
                       "avg_charges"]].round(2)
            st.dataframe(show, hide_index=True)


# --------------------------------------------------------------------------
# TAB 3 - Charges & severity  (Chart 2: box plot of charges by severity)
# --------------------------------------------------------------------------
with tabs[2]:
    use_log = st.checkbox("Log scale (recommended - charges are heavily skewed)", value=True, key="box_log")
    q = (df.groupby("severity", observed=True)["total_charges"]
           .quantile([0.05, 0.25, 0.5, 0.75, 0.95]).unstack().reindex(SEVERITY_ORDER).dropna())
    means = df.groupby("severity", observed=True)["total_charges"].mean().reindex(q.index)
    fig = go.Figure()
    for sev in q.index:
        fig.add_trace(go.Box(name=sev, x=[sev], q1=[q.loc[sev, 0.25]], median=[q.loc[sev, 0.5]],
                             q3=[q.loc[sev, 0.75]], lowerfence=[q.loc[sev, 0.05]],
                             upperfence=[q.loc[sev, 0.95]], marker_color=SEV_COLORS[sev]))
    fig.add_trace(go.Scatter(x=list(q.index), y=[float(means[x]) for x in q.index], mode="markers", name="Mean",
                             marker=dict(symbol="diamond", size=10, color="black")))
    fig.update_layout(title="Total charges by severity of illness (box = IQR, whiskers = 5th-95th percentile, "
                            "diamond = mean)", yaxis_title="Total charges ($)", showlegend=False)
    if use_log:
        fig.update_yaxes(type="log")
    st.plotly_chart(style(fig, 470))
    st.caption("Chart 2 · Severity is the strongest cost driver: both the typical charge and the spread widen "
               "sharply from Minor to Extreme.")
    c1, c2 = st.columns(2)
    with c1:
        sev = group_stats(df, "severity").set_index("severity").reindex(SEVERITY_ORDER).dropna()
        base = sev["median_charges"].iloc[0]
        sev["x_vs_minor"] = sev["median_charges"] / base
        st.markdown("**Severity cost ladder**")
        st.dataframe(sev[["discharges", "avg_los", "median_charges", "avg_charges", "x_vs_minor"]]
                     .rename(columns={"x_vs_minor": "median charge vs Minor (×)"}).round(2))
    with c2:
        age = group_stats(df, "age_group")
        metric = st.radio("Age-group metric", ["Average charge", "Total charges (est.)"], horizontal=True, key="age_metric")
        ycol, ylab = (("avg_charges", "Average charge ($)") if metric == "Average charge"
                      else ("total_charges", "Estimated total charges ($)"))
        age = age.assign(total_charges=age["total_charges"] * SCALE)
        fig = px.bar(age, x="age_group", y=ycol, color="age_group", color_discrete_sequence=px.colors.sequential.Teal,
                     title="Charges by age group", labels={"age_group": "", ycol: ylab})
        fig.update_layout(showlegend=False)
        st.plotly_chart(style(fig, 330))


# --------------------------------------------------------------------------
# TAB 4 - Facilities & counties  (Chart 3: heatmap)
# --------------------------------------------------------------------------
with tabs[3]:
    named = df[~df["facility_redacted"]]
    c1, c2, c3 = st.columns(3)
    top_fac = c1.slider("Number of facilities (by volume)", 5, 40, 20, key="hm_n")
    col_dim = c2.selectbox("Heatmap columns", ["county", "severity", "age_group", "admission_type"],
                           format_func=lambda x: {"county": "Hospital county", "severity": "Severity",
                                                  "age_group": "Age group", "admission_type": "Admission type"}[x],
                           key="hm_col")
    min_cell = c3.slider("Minimum cases per cell", 1, 100, 10, key="hm_min")
    fac_top = named["facility"].value_counts().head(top_fac).index
    sub = named[named["facility"].isin(fac_top)]
    agg = sub.groupby(["facility", col_dim], observed=True)["los"].agg(["mean", "size"])
    pivot = agg["mean"].where(agg["size"] >= min_cell).unstack(col_dim)
    order = sub.groupby("facility", observed=True)["los"].mean().reindex(pivot.index).sort_values().index
    pivot = pivot.loc[order]
    if pivot.dropna(how="all").empty:
        st.info("Not enough data for a heatmap under these filters. Lower the minimum cases per cell.")
    else:
        fig = px.imshow(pivot, aspect="auto", color_continuous_scale="YlOrRd", origin="lower",
                        labels=dict(color="Avg stay (d)", x="", y=""),
                        title="Average length of stay by facility and " + col_dim.replace("_", " "))
        fig.update_traces(hovertemplate="%{y}<br>%{x}<br>Avg stay: %{z:.2f} days<extra></extra>")
        st.plotly_chart(style(fig, 160 + 24 * len(pivot)))
        st.caption("Chart 3 · Each facility sits in one county, so the county view is naturally block-shaped. "
                   "Switch the columns to severity or age to compare facilities like-for-like. "
                   "Blank cells have too few cases.")

    c1, c2 = st.columns(2)
    with c1:
        cty = group_stats(df[df["county"] != "Unknown"], "county", min_n=30).sort_values("avg_los")
        fig = px.bar(cty, x="avg_los", y="county", orientation="h", color="avg_los", color_continuous_scale="Reds",
                     title="Average stay by county", labels={"avg_los": "Avg stay (days)", "county": ""},
                     hover_data={"discharges": ":,"})
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(style(fig, 140 + 22 * len(cty)))
    with c2:
        fac = group_stats(named, "facility", min_n=100)
        fac = fac.sort_values("discharges", ascending=False).head(30)
        fig = px.scatter(fac, x="avg_los", y="avg_costs", size="discharges", color="avg_charges",
                         hover_name="facility", color_continuous_scale="Viridis",
                         title="High-utilisation facilities (bubble = volume)",
                         labels={"avg_los": "Avg stay (days)", "avg_costs": "Avg cost ($)", "avg_charges": "Avg charge ($)"})
        st.plotly_chart(style(fig, 140 + 22 * len(cty)))


# --------------------------------------------------------------------------
# TAB 5 - Payers  (Chart 4: pie of payment type)
# --------------------------------------------------------------------------
with tabs[4]:
    c1, c2 = st.columns(2)
    pay = group_stats(df, "payer_primary")
    with c1:
        fig = px.pie(pay, names="payer_primary", values="discharges", hole=0.45,
                     title="Share of patients by primary payment type",
                     color_discrete_sequence=px.colors.qualitative.Set2)
        fig.update_traces(textposition="inside", textinfo="percent",
                          hovertemplate="%{label}<br>%{value:,} sample discharges (%{percent})<extra></extra>")
        st.plotly_chart(style(fig, 460))
        st.caption("Chart 4 · Government programmes (Medicare + Medicaid) typically cover the majority of "
                   "inpatient discharges, so payer mix is central to hospital finances.")
    with c2:
        measure = st.radio("Compare payers by", ["Average charge", "Average cost", "Charge-to-cost ratio"],
                           horizontal=True, key="pay_measure")
        pay["ratio"] = (df.groupby("payer_primary", observed=True)["total_charges"].sum()
                        / df.groupby("payer_primary", observed=True)["total_costs"].sum()).reindex(pay["payer_primary"]).values
        col = {"Average charge": "avg_charges", "Average cost": "avg_costs", "Charge-to-cost ratio": "ratio"}[measure]
        fig = px.bar(pay.sort_values(col), x=col, y="payer_primary", orientation="h", color=col,
                     color_continuous_scale="Purples", title=f"{measure} by primary payer",
                     labels={col: measure, "payer_primary": ""}, hover_data={"discharges": ":,"})
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(style(fig, 460))
    st.markdown("**Does the payer mix change who is treated and how long they stay?**")
    mix = pd.crosstab(df["payer_primary"], df["severity"], normalize="index").reindex(columns=SEVERITY_ORDER) * 100
    fig = px.bar(mix.reset_index().melt(id_vars="payer_primary", var_name="severity", value_name="pct"),
                 x="payer_primary", y="pct", color="severity", color_discrete_map=SEV_COLORS,
                 category_orders={"severity": SEVERITY_ORDER}, title="Severity mix within each payer (%)",
                 labels={"pct": "% of payer's discharges", "payer_primary": ""})
    st.plotly_chart(style(fig, 380))


# --------------------------------------------------------------------------
# TAB 6 - Statistics  (mathematical / statistical logic)
# --------------------------------------------------------------------------
with tabs[5]:
    st.subheader("Statistical analysis of the filtered discharges")
    stat_sample = df.sample(n=min(len(df), 60_000), random_state=1)
    num = stat_sample[["los", "total_charges", "total_costs", "severity_code", "n_payers"]].rename(
        columns={"los": "Length of stay", "total_charges": "Total charges", "total_costs": "Total costs",
                 "severity_code": "Severity (1-4)", "n_payers": "Number of payers"})
    corr = num.corr(method="spearman")
    c1, c2 = st.columns(2)
    with c1:
        fig = px.imshow(corr.round(2), text_auto=True, color_continuous_scale="RdBu_r", zmin=-1, zmax=1,
                        title="Spearman rank correlation matrix")
        st.plotly_chart(style(fig, 420))
        st.caption("Spearman is used because stay and charges are heavily skewed (it only needs a monotonic relationship).")
    with c2:
        pts = stat_sample.sample(n=min(len(stat_sample), 4000), random_state=2)
        fig = px.scatter(pts, x="los", y="total_charges", color="severity", opacity=0.45,
                         color_discrete_map=SEV_COLORS, category_orders={"severity": SEVERITY_ORDER},
                         log_x=True, log_y=True, title="Charges vs length of stay (log-log, 4,000-point sample)",
                         labels={"los": "Length of stay (days)", "total_charges": "Total charges ($)"})
        x, y = np.log10(stat_sample["los"].astype(float)), np.log10(stat_sample["total_charges"].astype(float))
        slope, intercept, r, p, se = stats.linregress(x, y)
        xs = np.linspace(x.min(), x.max(), 50)
        fig.add_trace(go.Scatter(x=10 ** xs, y=10 ** (intercept + slope * xs), mode="lines", name="Fit",
                                 line=dict(color="black", width=2)))
        st.plotly_chart(style(fig, 420))
        st.caption(f"Log-log fit: charges ∝ stay^{slope:.2f}, R² = {r ** 2:.2f}. "
                   f"Each 10% longer stay is associated with about {((1.1 ** slope) - 1) * 100:.1f}% higher charges.")

    groups = [g["total_charges"].values for _, g in stat_sample.groupby("severity", observed=True) if len(g) > 1]
    if len(groups) >= 2:
        h, p_kw = stats.kruskal(*groups)
        rho, p_rho = stats.spearmanr(stat_sample["los"], stat_sample["total_charges"])
        m1, m2, m3 = st.columns(3)
        m1.metric("Spearman ρ (stay vs charges)", f"{rho:.3f}", help=f"p-value = {p_rho:.2g}")
        m2.metric("Kruskal-Wallis H (charges by severity)", f"{h:,.0f}", help=f"p-value = {p_kw:.2g}")
        m3.metric("Skewness of charges", f"{stats.skew(stat_sample['total_charges']):.1f}",
                  help="Values far above 0 mean a long right tail")
        st.info("**Reading the tests:** a Kruskal-Wallis p-value near zero means charges differ significantly across "
                "severity levels. With tens of thousands of records almost any difference is significant, so look at "
                "the effect size (the cost ladder in the *Charges & Severity* tab) rather than the p-value alone.")
    with st.expander("Descriptive statistics (filtered data)"):
        desc = df[["los", "total_charges", "total_costs", "charge_per_day"]].describe(percentiles=[.25, .5, .75, .95]).T
        st.dataframe(desc.round(2))


# --------------------------------------------------------------------------
# TAB 7 - Insights (answers to the research questions, computed live)
# --------------------------------------------------------------------------
with tabs[6]:
    st.subheader("Research questions answered from the current selection")
    st.caption("These findings recalculate whenever you change the sidebar filters.")
    try:
        dxs = group_stats(df, ["dx_description"], min_n=50).sort_values("avg_los", ascending=False)
        age_s = group_stats(df, "age_group")
        sev_s = group_stats(df, "severity").set_index("severity").reindex(SEVERITY_ORDER).dropna()
        cty_s = group_stats(df[df["county"] != "Unknown"], "county", min_n=30).sort_values("avg_los", ascending=False)
        pay_s = group_stats(df, "payer_primary", min_n=30).sort_values("avg_charges", ascending=False)
        adm_s = group_stats(df, "admission_type")
        fac_s = group_stats(df[~df["facility_redacted"]], "facility", min_n=100).sort_values("discharges", ascending=False)

        if not dxs.empty:
            st.markdown(f"**Q1. Which diagnoses are linked to long stays?** "
                        f"*{dxs.iloc[0]['dx_description']}* averages **{dxs.iloc[0]['avg_los']:.1f} days** "
                        f"({dxs.iloc[0]['avg_los'] / df['los'].mean():.1f}× the overall mean of {df['los'].mean():.1f}), "
                        f"followed by *{dxs.iloc[1]['dx_description']}* ({dxs.iloc[1]['avg_los']:.1f} d)."
                        if len(dxs) > 1 else f"**Q1.** Longest-stay diagnosis: *{dxs.iloc[0]['dx_description']}*.")
        top_age = age_s.sort_values("avg_charges", ascending=False).iloc[0]
        top_age_tot = age_s.sort_values("total_charges", ascending=False).iloc[0]
        st.markdown(f"**Q2. Which age group incurs the highest charges?** Highest *per discharge*: "
                    f"**{top_age['age_group']}** (${top_age['avg_charges']:,.0f}). Highest *in total*: "
                    f"**{top_age_tot['age_group']}** (about ${top_age_tot['total_charges'] * SCALE / 1e9:,.2f} billion, estimated).")
        if len(sev_s) >= 2:
            st.markdown(f"**Q3. How does severity affect cost?** Median charge rises from "
                        f"**${sev_s['median_charges'].iloc[0]:,.0f}** ({sev_s.index[0]}) to "
                        f"**${sev_s['median_charges'].iloc[-1]:,.0f}** ({sev_s.index[-1]}), a "
                        f"**{sev_s['median_charges'].iloc[-1] / sev_s['median_charges'].iloc[0]:.1f}×** increase; "
                        f"average stay goes from {sev_s['avg_los'].iloc[0]:.1f} to {sev_s['avg_los'].iloc[-1]:.1f} days.")
        if len(cty_s) >= 2:
            st.markdown(f"**Q4. Are some counties slower?** Longest average stay: **{cty_s.iloc[0]['county']}** "
                        f"({cty_s.iloc[0]['avg_los']:.2f} d); shortest: **{cty_s.iloc[-1]['county']}** "
                        f"({cty_s.iloc[-1]['avg_los']:.2f} d). Gap: {cty_s.iloc[0]['avg_los'] - cty_s.iloc[-1]['avg_los']:.2f} days. "
                        f"Check the severity mix before concluding a county is inefficient.")
        if len(pay_s) >= 2:
            st.markdown(f"**Q5. How does payment type affect billing?** Highest average charge: "
                        f"**{pay_s.iloc[0]['payer_primary']}** (${pay_s.iloc[0]['avg_charges']:,.0f}); lowest: "
                        f"**{pay_s.iloc[-1]['payer_primary']}** (${pay_s.iloc[-1]['avg_charges']:,.0f}).")
        if len(adm_s) >= 2:
            longest = adm_s.sort_values("avg_los", ascending=False).iloc[0]
            st.markdown(f"**Q6. Does the route of admission matter?** **{longest['admission_type']}** admissions stay "
                        f"longest on average ({longest['avg_los']:.2f} d) and "
                        f"{(df['ed_indicator'] == 'Y').mean() * 100:.1f}% of discharges came through the emergency department.")
        if not fac_s.empty:
            top3 = ", ".join(fac_s.head(3)["facility"].astype(str))
            share = fac_s.head(3)["discharges"].sum() / len(df) * 100
            st.markdown(f"**Q7. Which facilities are high-utilisation?** Busiest: {top3} "
                        f"(together {share:.1f}% of the selected discharges).")
    except Exception as exc:  # never break the dashboard because of a thin filter selection
        st.info(f"Not enough data under the current filters to compute every insight ({exc}).")

    st.divider()
    st.markdown("""
**Why this matters to hospital administrators**
- **Capacity planning:** length of stay converts directly into bed-days, so shaving a day off long-stay diagnoses frees capacity.
- **Cost control:** severity-adjusted cost comparisons reveal real inefficiency versus unavoidable case-mix.
- **Payer strategy:** payer mix and the charge-to-cost ratio shape revenue expectations and contract negotiations.
- **Quality & safety:** mortality and disposition patterns highlight where discharge planning needs attention.
""")


# --------------------------------------------------------------------------
# TAB 8 - Data & method
# --------------------------------------------------------------------------
with tabs[7]:
    st.subheader("Data, cleaning and method")
    if report:
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Raw records", f"{report['raw_rows']:,}")
        r2.metric("After cleaning", f"{report['rows_clean_final']:,}")
        r3.metric("Rows in app sample", f"{report['rows_in_app_sample']:,}")
        r4.metric("Scale factor", f"{report['sample_scale_factor']:.2f}×")
        st.markdown("**Records removed**")
        st.dataframe(pd.DataFrame({"reason": [x.replace("_", " ") for x in report["dropped"]],
                                   "rows": list(report["dropped"].values())}),
                     hide_index=True)
        st.markdown(f"Also flagged (kept): **{report['charge_outliers_flagged_mild']:,}** mild charge outliers and "
                    f"**{report['los_outliers_flagged']:,}** long-stay outliers. Birth Weight was "
                    f"**{report['birth_weight_pct_null']:.1f}% empty** and was dropped.")
        val = pd.DataFrame(report["sample_validation"]).T.reset_index()
        val.columns = ["metric", "full cleaned data", "app sample", "% difference"]
        st.markdown("**Is the sample representative?** Sample vs full data:")
        st.dataframe(val, hide_index=True)
    st.markdown("""
**Pipeline:** raw CSV is read in chunks → money strings converted to floats → invalid stays/charges removed →
categories standardised → CCSR codes mapped to clinical categories → features engineered (charge/cost per day,
charge-to-cost ratio, stay band, number of payers) → extreme outliers (3×IQR on log charges within severity) removed →
a reproducible random sample is stored for fast, free hosting.

**Limitations:** costs and charges are *not* the same (charges are billed amounts, costs are estimated actual cost);
the data is de-identified, so readmissions cannot be tracked; 2021 was shaped by COVID-19, so patterns may differ in other years.
""")
    cap_rows = min(len(df), 100_000)
    st.download_button("⬇ Download filtered data (CSV, up to 100k rows)",
                       df.head(cap_rows).to_csv(index=False).encode("utf-8"),
                       file_name="filtered_discharges.csv", mime="text/csv")
