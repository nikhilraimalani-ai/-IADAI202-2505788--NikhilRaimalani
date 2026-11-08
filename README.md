# 🏥 Hospital Inpatient Discharges Dashboard

**Course:** Mathematics for AI-II · **CRS:** Artificial Intelligence · **Assessment:** Summative (individual)
**Student:** `<FULL NAME>` · **Student ID:** `<STUDENT ID>` · **Registration No.:** `<REG NUMBER>` · **School:** `<SCHOOL NAME>`

> 🔗 **Live dashboard:** `StreamLit Link: https://iadainikhilraimalani.streamlit.app/ '

An interactive Streamlit dashboard built for **MediScope Health Analytics** that helps hospital administrators, clinicians
and operations managers explore **2.1 million New York State inpatient discharges (SPARCS 2021)**: how long patients stay,
what care costs, which diagnoses, facilities and payers drive utilisation, and where operational efficiency can improve.


---

## 1. Project overview

| | |
|---|---|
| **Problem** | Hospitals need to understand length of stay, cost and utilisation patterns to plan capacity and control costs. |
| **Data** | NY SPARCS *Hospital Inpatient Discharges (De-Identified) 2021*: 2,101,588 records, 33 columns (~830 MB); 2,101,388 after cleaning, 400,000 in the app sample (scale factor 5.25). |
| **Users** | Hospital administrators, clinicians, operations managers. |
| **Approach** | Chunked cleaning in Python → feature engineering → validated random sample → interactive Plotly/Streamlit dashboard. |

### Research questions
1. Which diagnosis codes are linked to long stays?
2. Which age groups incur the highest charges (per patient and in total)?
3. How does illness severity affect total cost?
4. Are there counties with longer average stays?
5. How do payment types affect billing (charges, costs, charge-to-cost ratio)?
6. Does the route of admission (emergency / elective / urgent / newborn) change stay and cost?
7. Which facilities are high-utilisation, and how do their costs compare?

Full write-up with background research: [`docs/research_questions.md`](docs/research_questions.md)

## 2. Key features

- **Sidebar filters** (county, age, gender, severity, admission type, payer, diagnosis category, medical/surgical, ED, stay range) with one-click reset. Every KPI and chart updates instantly.
- **KPI cards:** estimated discharges, average stay, average charge/cost, charge-to-cost ratio, in-hospital mortality.
- **The five required visuals** (all interactive):

| # | Visual | Question answered | Tab |
|---|---|---|---|
| 1 | Bar chart: average stay per diagnosis code | Q1 | 🩺 Diagnoses |
| 2 | Box plot: total charges by severity | Q3 | 💰 Charges & Severity |
| 3 | Heatmap: average stay by facility × county (switchable to severity / age / admission) | Q4, Q7 | 🏥 Facilities & Counties |
| 4 | Donut/pie: patients by payment type | Q5 | 💳 Payers |
| 5 | Histogram: length-of-stay distribution (adjustable cap, log scale) | Overview | 📊 Overview |

- **Extra analysis:** age-group charges, county ranking, facility bubble chart, payer × severity mix, Spearman correlation matrix, log-log regression, Kruskal-Wallis test, descriptive statistics.
- **🧠 Insights tab:** answers to the research questions, recomputed live from the current filters.
- **📘 Data & Method tab:** the full cleaning report and sample-vs-full validation, plus a CSV download of the filtered data.

## 3. Data preprocessing and cleaning (`scripts/clean_data.py`)

| Step | What is done |
|---|---|
| Load | Read the 830 MB CSV in 250k-row chunks (fits free-tier RAM). |
| Types | `"27,606.16"` → float; Length of Stay incl. the `"120 +"` top-code → integer. |
| Invalid records | Rules remove non-positive/missing length of stay, charges and costs. **This release contained none (0 rows)**, which the report confirms, so the checks act as safeguards. |
| Standardise | Gender `F/M/U` → Female/Male/Unknown; ordered age groups, severity and mortality risk; ZIP `OOS` → Out of State; redacted facilities flagged. |
| Readable categories | CCSR diagnosis codes mapped to 22 clinical categories (Circulatory, Respiratory, Neoplasms ...). |
| Drop columns | Birth Weight (90.2% empty), Payment Typology 2/3 (kept as `n_payers`), identifier and constant columns. |
| Feature engineering | `charge_per_day`, `cost_per_day`, `charge_to_cost_ratio`, `los_band`, `n_payers`, `has_procedure`, outlier flags. |
| Outliers | Tukey fences on log10(charges) **within each severity level**: **200 extreme (3×IQR) charge outliers removed**, 24,085 mild ones flagged; 31,734 long-stay outliers flagged only. |
| Sampling | Reproducible random sample (seed 42, 400,000 rows) so the app fits GitHub (<100 MB) and Streamlit Cloud (~1 GB RAM). |
| Validation | Sample vs full cleaned data: every KPI within **0.2%** (avg stay 5.75 vs 5.74 days; avg charge $73,327 vs $73,270). |

## 4. Integration details

```
Raw CSV (830 MB, Google Drive)
        │  scripts/clean_data.py   (pandas, chunked)
        ▼
data/discharges_clean.parquet  +  data/cleaning_report.json   (committed to GitHub)
        │  app.py   (Streamlit + Plotly + SciPy)
        ▼
Streamlit Community Cloud  →  public live link
```

- **Libraries:** Streamlit, pandas, NumPy, Plotly, SciPy, PyArrow (see `requirements.txt`).
- **Performance:** `@st.cache_data` data loading, categorical dtypes, and server-side aggregation for box plots and histograms (the browser never receives hundreds of thousands of raw points).
- **Estimated counts:** discharge counts shown in the app are *sample × scale factor* so they approximate the full 2021 population; averages are unbiased estimates.

## 4b. Key findings (full-year 2021, from the validated sample)

- **Long stays:** schizophrenia-spectrum disorders average **16.65 days (2.9× the mean)**; septicemia is the biggest burden (~137k discharges, ~1.3M bed-days, $16.6 bn charges).
- **Age:** patients 50+ generate **69% of all charges**; 70+ is the largest total ($53.9 bn).
- **Severity:** median charge rises **4.7×** from Minor to Extreme; Extreme cases are 9.6% of discharges but **28.5% of charges**.
- **Payers:** Medicare + Medicaid cover **70% of patients**; hospitals bill **3.33× estimated cost** overall.
- **Admission:** emergency admissions are 66% of discharges and 67% of charges.
- **Facilities:** average charge varies **3.3×** between top hospitals despite similar stays.

Full analysis: [`docs/research_questions.md`](docs/research_questions.md)



## 5. Repository structure

```
├── app.py                    # Streamlit dashboard
├── requirements.txt
├── README.md
├── scripts/clean_data.py     # cleaning + feature engineering pipeline
├── notebooks/                # exploratory analysis notebook (Colab)
├── data/                     # cleaned sample + cleaning_report.json
├── docs/research_questions.md
└── screenshots/              # dashboard screenshots
```

## 6. Limitations

- Charges (billed) are not costs (estimated actual cost); the app reports both.
- Data is de-identified, so readmissions cannot be tracked.
- 2021 was shaped by COVID-19; patterns may differ in other years.
- The app uses a representative random sample; the Data & Method tab shows how closely it matches the full data.

## 7. Data source

New York State Department of Health, *Hospital Inpatient Discharges (SPARCS De-Identified): 2021*. Diagnosis categories use the AHRQ HCUP CCSR classification.
