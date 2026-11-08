# Research Questions, Background and Findings

**Project:** Hospital Inpatient Discharges Dashboard (NY SPARCS 2021) · **Course:** Mathematics for AI-II

## 1. Background research: how administrators use discharge data

Hospital discharge databases such as New York's **SPARCS** (Statewide Planning and Research Cooperative System) record one row per inpatient stay with diagnosis, severity, payer, length of stay, charges and costs. Administrators and analysts use this kind of data for five recurring purposes:

| Use | Metric | Why it matters |
|---|---|---|
| **Capacity planning** | Average and median length of stay (LOS), bed-days | Bed-days = discharges × LOS; one day saved on a high-volume diagnosis frees real capacity. |
| **Cost control** | Cost per case, cost per day, case-mix adjusted cost | Comparing hospitals only makes sense after adjusting for severity (APR-DRG severity of illness). |
| **Revenue and payer strategy** | Payer mix, charge-to-cost ratio | Medicare and Medicaid pay set rates, so payer mix largely determines finances. |
| **Quality and safety** | Risk of mortality, disposition (home, nursing facility, expired) | Highlights where discharge planning or clinical pathways need attention. |
| **Population health** | Age and diagnosis category patterns | Guides service-line investment (e.g. geriatrics, behavioural health). |

Key concepts used in this project:
- **APR-DRG severity of illness** (Minor, Moderate, Major, Extreme): a 4-level clinical severity score assigned to each stay; the standard way to compare cases like-for-like.
- **CCSR (Clinical Classifications Software Refined):** AHRQ's grouping of thousands of ICD-10 diagnosis codes into ~530 clinical categories, with the first three letters indicating the body system (e.g. `RSP` = respiratory, `MBD` = mental and behavioural). This project maps those prefixes to 22 readable categories.
- **Charges vs costs:** *charges* are the amounts hospitals bill (list prices); *costs* are the estimated actual cost of care. The **charge-to-cost ratio** shows how far billing exceeds cost.
- **Skewness:** charges and length of stay are heavily right-skewed (a few very expensive or very long stays), so medians, log scales and rank-based statistics (Spearman, Kruskal-Wallis) are more appropriate than means and Pearson correlation.

*Suggested sources to cite in your submission (verify and read them before citing):* NY State Department of Health SPARCS documentation on health.data.ny.gov; AHRQ HCUP documentation for CCSR; the 3M/Solventum APR-DRG methodology overview; the Streamlit and Plotly documentation listed in the assignment brief.

## 2. Research questions and findings

All figures are from the 400,000-row representative sample (scaled ×5.25 where noted as "estimated"). The sample matches the full 2,101,388 cleaned records within 0.2% on every KPI.

**Q1. Which diagnosis codes are linked to long stays?**
Psychiatric and neurological conditions dominate. *Schizophrenia spectrum and other psychotic disorders* average **16.65 days (2.9× the overall mean of 5.74)**, followed by sequela of cerebral infarction (13.97 d), non-Hodgkin lymphoma (13.44 d), bipolar disorders (11.64 d) and acute hemorrhagic cerebrovascular disease (11.05 d). Four of the top eight are mental and behavioural diagnoses. By total burden, **septicemia** is the largest long-stay diagnosis: about 137,000 estimated discharges averaging 9.68 days, roughly 1.3 million bed-days and $16.6 billion in charges.

**Q2. Which age groups incur the highest charges?**
Per discharge, ages **50-69 ($89,905)** and **70+ ($86,811)** are highest. In total, **70+ ($53.9 bn)** and **50-69 ($52.5 bn)** together account for **69% of all charges** from 57% of discharges. Ages 0-17 have a low median ($15.6k) because most are newborns.

**Q3. How does severity affect cost?**
Cost rises steeply and non-linearly. Median charge climbs from **$24,391 (Minor) to $113,657 (Extreme), a 4.7× increase**; average stay rises 5.1× (2.86 to 14.65 days) and average charge 6.0× ($36.6k to $218.4k). **Extreme cases are 9.6% of discharges but 28.5% of total charges.**

**Q4. Are there counties with longer average stays?**
Yes. Among large counties (20,000+ sample discharges), **Westchester (6.64 d), Monroe (6.51 d), Bronx (6.18 d) and Kings (6.12 d)** are longest, while **Nassau (5.33 d) and Suffolk (5.24 d)** are shorter. Small rural counties vary widely (Columbia 6.89 d, Lewis 3.10 d) but rest on few cases. Notably, Manhattan's average stay (5.90 d) is mid-range while its average charge ($118k) is the highest of any large county: price, not stay, drives its cost. County differences should be read alongside severity mix.

**Q5. How do payment types affect billing?**
**Medicare (39.3% of patients) and Medicaid (30.8%)** cover 70% of discharges; Medicare alone accounts for 47% of charges ($72.8 bn) and has the longest stays (6.92 d), reflecting an older population. Average charge is highest for Medicare ($88.1k) among the large payers and lowest for Federal/State/Local/VA ($44.0k). Across all stays, hospitals bill **3.33× the estimated cost** ($73,270 average charge vs $21,983 average cost).

**Q6. Does route of admission matter?**
Emergency admissions are **66% of discharges and 67% of charges** (63% of the full dataset passes through the emergency department). Emergency stays average 6.28 d versus 4.59 d for elective, but elective cases have a *higher* average charge ($84.3k vs $74.7k), consistent with planned surgery. Trauma admissions have the highest average charge ($126k).

**Q7. Which facilities are high-utilisation?**
The busiest are North Shore University Hospital, Mount Sinai Hospital, NYU Langone Hospitals, NewYork-Presbyterian (Columbia and Weill Cornell) and Strong Memorial Hospital, each with roughly 40,000-50,000 estimated discharges. Their average charges differ **3.3×** ($50k at Strong Memorial to $165k at NYU Langone) even though stays are similar (5.1-7.0 days), pointing to large pricing and case-mix differences.

## 3. Recommendations for administrators

1. **Target psychiatric and sepsis pathways** for length-of-stay reduction: they combine long stays with high volume or high bed-day totals.
2. **Plan capacity for the 50+ population,** which drives roughly 69% of charges.
3. **Monitor Extreme-severity cases closely:** under 10% of patients generate over a quarter of charges, so small efficiency gains there have outsized effect.
4. **Compare facilities only after severity adjustment;** raw averages mix price, case-mix and efficiency.
5. **Review payer strategy:** with 70% of patients on Medicare or Medicaid, negotiated and regulated rates dominate revenue.

## 4. Limitations

Charges are billed amounts, not payments; the data is de-identified so readmissions cannot be measured; 2021 was affected by COVID-19; the dashboard uses a representative random sample (validated above) rather than all 2.1 million rows; comparisons across counties and facilities are not risk-adjusted.
