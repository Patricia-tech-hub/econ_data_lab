# Econ Data Lab — Gulf NBS Urban Resilience

This repository contains the data pipeline, exploratory analysis, and regression code for a 20-city panel study examining whether urban nature-based solutions (NBS) reduce economic vulnerability to extreme heat in Gulf cities over the period 2000–2023. The analysis combines satellite-derived greenness indices (MODIS NDVI via Google Earth Engine), calibrated nighttime lights (DMSP-OLS + VIIRS), and country-level economic indicators (World Bank WDI) to test whether increases in urban green cover are associated with improvements in electricity consumption efficiency, industrial value added, FDI inflows, and nighttime economic activity.

---

## Research question

> Do investments in urban nature-based solutions reduce economic vulnerability to extreme heat in Gulf cities?

---

## Repository structure

```
gulf_nbs_project/
├── data/
│   ├── raw/                          (download instructions — data not tracked in repo)
│   │   └── README.md                 (source URLs and download steps for all inputs)
│   └── processed/                    (pipeline outputs — small files committed for convenience)
│       ├── master_panel.csv          (480 rows: 20 cities × 24 years, all variables merged)
│       ├── ntl_calibrated_panel.csv  (DMSP→VIIRS calibrated NTL series)
│       └── city_pop_panel.csv        (city-level population panel from UN WUP + fallback)
├── notebooks/
│   └── 02_eda.ipynb                  (exploratory analysis, data coverage, §8 summary statistics)
├── scripts/
│   ├── 01_gee_extraction.py          (annual mean NDVI extraction from MODIS Terra via GEE)
│   ├── 01b_gee_ntl_fix.py            (DMSP-OLS NTL extraction for 20 cities, 2000–2012)
│   ├── 01c_gee_viirs_fix.py          (VIIRS DNB NTL extraction, intermediate version)
│   ├── 01d_gee_viirs_final.py        (VIIRS DNB NTL extraction, final version, 2013–2023)
│   ├── 01e_gee_dmsp_2013.py          (DMSP NTL for 2013 only — calibration anchor year)
│   ├── 02_city_populations.py        (builds city population panel from UN WUP 2025 + web scrape fallback)
│   ├── 03_ntl_calibration.py         (Elvidge-style OLS calibration of DMSP→VIIRS at the 2013 seam)
│   ├── 04_master_panel_merge.py      (merges all sources into the 480-row master panel)
│   ├── 05_regressions.R              (two-way FE regressions, robustness checks, and output tables)
│   └── install_r_packages.R          (installs required R packages from CRAN)
├── outputs/
│   ├── figures/                      (all generated charts — PNGs committed)
│   └── tables/                       (regression tables and summary statistics)
├── environment.yml                   (conda environment spec — recommended)
├── requirements.txt                  (pip fallback for users without conda)
└── README.md
```

---

## Setup instructions

### Conda (recommended)

```bash
git clone https://github.com/Patricia-tech-hub/econ_data_lab.git
cd econ_data_lab
conda env create -f environment.yml
conda activate gulf_nbs
Rscript scripts/install_r_packages.R
```

### Pip (fallback — for users without conda or a configured R installation)

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

> Note: the pip path installs Python dependencies only. R packages required by `scripts/05_regressions.R` (`fixest`, `modelsummary`, `flextable`, etc.) must be installed separately. See `scripts/install_r_packages.R`.
>
> `rpy2` is excluded from `requirements.txt` because it requires a pre-existing, correctly configured R installation. Conda users get this automatically via `environment.yml`.

---

## Reproducing the analysis

**Option A — skip the pipeline (recommended for most teammates)**

The three processed data files are committed to the repo. Clone, set up the environment per the Setup instructions above, then open `notebooks/02_eda.ipynb` directly or run `scripts/05_regressions.R` to reproduce the regression tables.

```bash
git clone https://github.com/Patricia-tech-hub/econ_data_lab.git
cd econ_data_lab
conda env create -f environment.yml && conda activate gulf_nbs
```

**Option B — run the full pipeline from raw data**

1. Download all raw data files following `data/raw/README.md`.

2. Authenticate Google Earth Engine:
   ```bash
   earthengine authenticate
   ```

3. Run GEE extraction scripts:
   ```bash
   python scripts/01_gee_extraction.py    # NDVI
   python scripts/01b_gee_ntl_fix.py      # DMSP NTL 2000-2012
   python scripts/01e_gee_dmsp_2013.py    # DMSP NTL 2013 (calibration anchor)
   python scripts/01d_gee_viirs_final.py  # VIIRS NTL 2013-2023
   ```

4. Build processed files:
   ```bash
   python scripts/02_city_populations.py
   python scripts/03_ntl_calibration.py
   python scripts/04_master_panel_merge.py
   ```

5. Explore the panel:
   ```bash
   jupyter lab notebooks/02_eda.ipynb
   ```

6. Run all regression tables:
   ```bash
   Rscript scripts/05_regressions.R
   ```
   Output tables are written to `outputs/tables/`.

---

## Data sources & citations

- **World Bank World Development Indicators (WDI).** Electricity consumption, FDI net inflows, GDP per capita, urban population share, industry value added. <https://databank.worldbank.org/source/world-development-indicators>

- **NASA MODIS Terra MOD13A2 v061** (16-day NDVI composites at 1 km, aggregated to annual means) via Google Earth Engine. Didan, K. (2021). *MOD13A2 MODIS/Terra Vegetation Indices 16-Day L3 Global 1km SIN Grid V061*. NASA EOSDIS Land Processes DAAC. <https://doi.org/10.5067/MODIS/MOD13A2.061>

- **NOAA DMSP-OLS Nighttime Lights** and **NASA/NOAA VIIRS Day/Night Band** via Google Earth Engine. Defense Meteorological Satellite Program — Operational Linescan System; Suomi-NPP VIIRS DNB monthly composites.

- **United Nations World Urbanization Prospects 2025.** File 21: Cities with 50,000+ inhabitants. United Nations, Department of Economic and Social Affairs, Population Division (2025). <https://population.un.org/wup/>

- **FRED — Federal Reserve Bank of St. Louis.** Global price of Brent crude (POILBREUSDM). <https://fred.stlouisfed.org/series/POILBREUSDM>

- **IMF Climate Change Dashboard.** Expenditure on environmental protection (% GDP). International Monetary Fund. <https://climatedata.imf.org/>

- **Stowell, J.D. et al. (2023).** Global Greenspace Indicator Dataset. *Harvard Dataverse*. <https://doi.org/10.7910/DVN/VMZSLN>

---

## Methodology summary

**Two-way fixed effects model.** The core specification regresses each economic outcome (electricity per capita, industry value added, FDI net inflows, nighttime lights) on NDVI, controlling for GDP per capita, city population, urban population share, and the Brent crude oil price. City and year fixed effects absorb time-invariant city characteristics and common shocks. See `outputs/tables/main_results.docx` for the full coefficient table.

**Inference strategy.** Standard errors are clustered at the city level (G=20 clusters) to account for within-city serial correlation. Robustness checks include wild cluster bootstrap (B=9999, Rademacher weights), leave-one-country-out jackknife, 1-year and 2-year lagged NDVI specifications, VIIRS-only subsample (2013–2023), and an environmental-expenditure subsample. Results are in `outputs/tables/robustness_*.docx`.

**Known limitations.** With only 20 city clusters across 6 countries the asymptotic justification for cluster-robust SEs is weak, and jackknife diagnostics reveal fragility to individual city exclusions. Economic outcomes are measured at the country level (WDI) and assigned to all cities in a country, creating a scale mismatch with the city-level NDVI. These limitations are discussed in the project presentation in `outputs/`.

---

## License

Code in this repository is released under the [MIT License](https://opensource.org/licenses/MIT).

Data downloaded from third-party sources retains its original license.

---

## Acknowledgements

This project was developed as part of the Econ Data Lab programme in partnership with UNDP.
