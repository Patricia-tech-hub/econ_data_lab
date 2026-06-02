# Raw Data — Download Instructions

Raw data files are **not tracked in this repository** to keep the repo lightweight and to respect the terms of service of each data provider. Download the files listed below and place them directly in this folder (`data/raw/`) before running any scripts.

---

## Required files

| Filename | Source | Download URL / Notes |
|---|---|---|
| `Electric power consumption (kWh per capita).csv` | World Bank WDI | [WDI DataBank](https://databank.worldbank.org/source/world-development-indicators) — indicator `EG.USE.ELEC.KH.PC` |
| `Foreign direct investment, net inflows (% of GDP).csv` | World Bank WDI | [WDI DataBank](https://databank.worldbank.org/source/world-development-indicators) — indicator `BX.KLT.DINV.WD.GD.ZS` |
| `GDP per capita (constant 2015 US$).csv` | World Bank WDI | [WDI DataBank](https://databank.worldbank.org/source/world-development-indicators) — indicator `NY.GDP.PCAP.KD` |
| `Urban population (% of total population).csv` | World Bank WDI | [WDI DataBank](https://databank.worldbank.org/source/world-development-indicators) — indicator `SP.URB.TOTL.IN.ZS` |
| `Industry (including construction), value added (% of GDP).csv` | World Bank WDI | [WDI DataBank](https://databank.worldbank.org/source/world-development-indicators) — indicator `NV.IND.TOTL.ZS` |
| `Global price of brent crude.csv` | FRED | [POILBREUSDM](https://fred.stlouisfed.org/series/POILBREUSDM) — download as CSV; column name must be `POILBREUSDM` |
| `un_wup2025_cities_50k.xlsx` | UN World Urbanization Prospects 2025 | [UN WUP 2025 data](https://population.un.org/wup/downloads/) — download **File 21** (cities ≥ 50,000 inhabitants). Use the **`Data`** sheet. Save as `un_wup2025_cities_50k.xlsx` |
| `urban_NDVI.csv` | Harvard Dataverse — Stowell et al. (2023) | [Global Greenspace Indicator Dataset](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/VMZSLN) — download the city-level annual average NDVI file |
| `environmental_protection_expenditure.csv` | IMF Climate Data | [IMF Climate Change Dashboard](https://climatedata.imf.org/) — search for "Expenditure on environment protection", download CSV for BHR, KWT, OMN, QAT, SAU, UAE |
| `gulf_ndvi_2000_2023.csv` | **Produced by GEE script** | Run `scripts/01_gee_extraction.py` after authenticating Google Earth Engine — output written here automatically |
| `gulf_ntl_dmsp_2000_2012.csv` | **Produced by GEE script** | Run `scripts/01b_gee_ntl_fix.py` — DMSP-OLS nighttime lights, 2000–2012 |
| `gulf_ntl_viirs_2013_2023.csv` | **Produced by GEE script** | Run `scripts/01d_gee_viirs_final.py` — VIIRS DNB nighttime lights, 2013–2023 |

### WDI download tips

1. Go to [WDI DataBank](https://databank.worldbank.org/source/world-development-indicators).
2. Select **Countries**: Bahrain, Kuwait, Oman, Qatar, Saudi Arabia, United Arab Emirates.
3. Select **Series**: the indicator code listed above.
4. Select **Time**: 2000–2023.
5. Click **Download → CSV**. The file will be named after the indicator — keep that name exactly as shown in the table above.

---

## Google Earth Engine authentication

The three GEE output files must be generated before running the merge pipeline. Authenticate once with:

```bash
earthengine authenticate
```

Then run the extraction scripts from the project root:

```bash
python scripts/01_gee_extraction.py    # NDVI
python scripts/01b_gee_ntl_fix.py      # DMSP NTL 2000-2012
python scripts/01d_gee_viirs_final.py  # VIIRS NTL 2013-2023
```

---

## Folder contents after download

Once all files are in place, the folder should contain exactly these files (plus this README):

```
data/raw/
├── Electric power consumption (kWh per capita).csv
├── environmental_protection_expenditure.csv
├── Foreign direct investment, net inflows (% of GDP).csv
├── GDP per capita (constant 2015 US$).csv
├── Global price of brent crude.csv
├── gulf_ndvi_2000_2023.csv
├── gulf_ntl_dmsp_2000_2012.csv
├── gulf_ntl_viirs_2013_2023.csv
├── Industry (including construction), value added (% of GDP).csv
├── un_wup2025_cities_50k.xlsx
├── Urban population (% of total population).csv
└── urban_NDVI.csv
```

> `city_populations.csv` and `gulf_ntl_dmsp_2013.csv` are small auxiliary files generated internally by the pipeline and do not need to be downloaded separately.
