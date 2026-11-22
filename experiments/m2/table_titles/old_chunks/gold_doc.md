# Q105 search test: chunks, gold_doc

Value columns: the gold number is in a top-k chunk on the evidence page (find-number questions only).

| Group | n | Hit@1 | Hit@5 | Hit@10 | MRR | Value n | Value@5 | Value@10 |
|---|---|---|---|---|---|---|---|---|
| all | 50 | 0.52 | 0.7 | 0.74 | 0.586 | 20 | 0.65 | 0.7 |
| answer_source=table | 28 | 0.393 | 0.607 | 0.643 | 0.477 | 10 | 0.6 | 0.6 |
| answer_source=text | 22 | 0.682 | 0.818 | 0.864 | 0.725 | 10 | 0.7 | 0.8 |
| category=calculate | 10 | 0.6 | 0.7 | 0.7 | 0.65 |  |  |  |
| category=compare_companies | 4 | 0.0 | 0.25 | 0.25 | 0.125 |  |  |  |
| category=compare_years | 6 | 0.333 | 0.5 | 0.667 | 0.399 |  |  |  |
| category=explain_why | 10 | 0.8 | 0.9 | 0.9 | 0.833 |  |  |  |
| category=find_number | 20 | 0.5 | 0.75 | 0.8 | 0.578 | 20 | 0.65 | 0.7 |

| ID | Category | Source | Rank | Value rank | Evidence |
|---|---|---|---|---|---|
| dev_0001 | find_number | table | 4 | - | 3M_2019_10K p91 |
| dev_0002 | find_number | table | 1 | 5 | JPMORGAN_2021Q2_10Q p119 |
| dev_0003 | find_number | table | 2 | 2 | MGMRESORTS_2017_10K p66 |
| dev_0004 | find_number | table | - | - | APPLE_2019_10K p32 |
| dev_0005 | find_number | table | 1 | - | APPLE_2023Q3_10Q p5 |
| dev_0006 | find_number | table | 1 | 1 | WALMART_2023_annualreport p46 |
| dev_0007 | find_number | table | 5 | 5 | FEDEX_2023_annualreport p102 |
| dev_0008 | find_number | table | 1 | 1 | AMCOR_2022_8K_dated-2022-04-26 p12 |
| dev_0009 | find_number | table | - | - | JOHNSON_JOHNSON_2023Q1_EARNINGS p8 |
| dev_0010 | find_number | table | 1 | 1 | COSTCO_2019_10K p56 |
| dev_0011 | find_number | text | 1 | 1 | INTEL_2019_10K p24 |
| dev_0012 | find_number | text | 4 | 4 | 3M_2019_10K p142 |
| dev_0013 | find_number | text | 1 | 2 | COSTCO_2019_10K p70 |
| dev_0014 | find_number | text | 6 | 6 | PG_E_2023_EARNINGS-dated-2023-06-01 p69 |
| dev_0015 | find_number | text | 5 | 5 | ULTABEAUTY_2024Q1_EARNINGS p3 |
| dev_0016 | find_number | text | - | - | LOCKHEEDMARTIN_2023Q2_10Q p7 |
| dev_0017 | find_number | text | 1 | 1 | JPMORGAN_2021Q2_10Q p8 |
| dev_0018 | find_number | text | 1 | 2 | APPLE_2019_10K p43 |
| dev_0019 | find_number | text | - | - | INTEL_2023_8K_dated-2023-02-10 p85 |
| dev_0020 | find_number | text | 1 | 1 | APPLE_2023Q3_10Q p22 |
| dev_0021 | explain_why | text | 1 | n/a | FEDEX_2023_annualreport p28 |
| dev_0022 | explain_why | text | 1 | n/a | MCDONALDS_2023Q1_EARNINGS p3 |
| dev_0023 | explain_why | text | 1 | n/a | JPMORGAN_2021Q2_10Q p191 |
| dev_0024 | explain_why | text | 1 | n/a | WALMART_2023_annualreport p66 |
| dev_0025 | explain_why | text | 1 | n/a | MGMRESORTS_2017_10K p46 |
| dev_0026 | explain_why | text | 3 | n/a | INTEL_2019_10K p62 |
| dev_0027 | explain_why | text | 1 | n/a | EBAY_2023Q1_8K p2 |
| dev_0028 | explain_why | text | 1 | n/a | APPLE_2019_10K p8 |
| dev_0029 | explain_why | text | - | n/a | 3M_2019_10K p10 |
| dev_0030 | explain_why | text | 1 | n/a | COSTCO_2019_10K p8 |
| dev_0031 | calculate | table | 1 | n/a | ULTABEAUTY_2024Q1_EARNINGS p1 |
| dev_0032 | calculate | table | 2 | n/a | MCDONALDS_2023Q1_EARNINGS p2 |
| dev_0033 | calculate | text | 1 | n/a | ADOBE_2018_10K p86 |
| dev_0034 | calculate | table | 1 | n/a | INTEL_2019_10K p88 |
| dev_0035 | calculate | table | - | n/a | LOCKHEEDMARTIN_2023Q2_10Q p2 |
| dev_0036 | calculate | text | 1 | n/a | MGMRESORTS_2017_10K p99 |
| dev_0037 | calculate | table | - | n/a | APPLE_2019_10K p36 |
| dev_0038 | calculate | table | 1 | n/a | APPLE_2023Q3_10Q p8 |
| dev_0039 | calculate | table | - | n/a | WALMART_2023_annualreport p56 |
| dev_0040 | calculate | table | 1 | n/a | FEDEX_2023_annualreport p98 |
| dev_0041 | compare_years | table | - | n/a | CVSHEALTH_2017_10K p59 |
| dev_0042 | compare_years | table | 1 | n/a | ORACLE_2020_10K p37 |
| dev_0043 | compare_years | table | 4 | n/a | ULTABEAUTY_2024Q1_EARNINGS p7 |
| dev_0044 | compare_years | table | 7 | n/a | MCDONALDS_2023Q1_EARNINGS p4 |
| dev_0045 | compare_years | table | - | n/a | ADOBE_2018_10K p47 |
| dev_0046 | compare_years | table | 1 | n/a | INTEL_2019_10K p86 |
| dev_0047 | compare_companies | table | - | n/a | COSTCO_2019_10K p36; VERIZON_2018_10K p111 |
| dev_0048 | compare_companies | table | - | n/a | INTEL_2019_10K p71; COSTCO_2019_10K p36 |
| dev_0049 | compare_companies | table | - | n/a | 3M_2019_10K p60; COSTCO_2019_10K p39 |
| dev_0050 | compare_companies | table | 2 | n/a | CVSHEALTH_2017_10K p80; MGMRESORTS_2017_10K p30 |
