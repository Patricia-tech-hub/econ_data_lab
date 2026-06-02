"""
Build data/processed/master_panel.csv
480 rows: 20 cities x 24 years (2000-2023)
"""
import unicodedata
import numpy as np
import pandas as pd

from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
RAW   = str(_ROOT / 'data' / 'raw') + '/'
PROC  = str(_ROOT / 'data' / 'processed') + '/'

GULF_ISO3 = ['KWT', 'QAT', 'BHR', 'ARE', 'OMN', 'SAU']
YEARS     = list(range(2000, 2024))

CITY_ISO3 = {
    'Kuwait City': 'KWT', 'Doha': 'QAT',
    'Dubai': 'ARE', 'Abu Dhabi': 'ARE', 'Sharjah': 'ARE',
    'Al Ain': 'ARE', 'Ras Al Khaimah': 'ARE', 'Ajman': 'ARE',
    'Manama': 'BHR',
    'Muscat': 'OMN', 'Sohar': 'OMN',
    'Riyadh': 'SAU', 'Jeddah': 'SAU', 'Dammam': 'SAU',
    'Mecca': 'SAU', 'Medina': 'SAU', 'Khobar': 'SAU',
    'Taif': 'SAU', 'Buraydah': 'SAU', 'Al Mubarraz': 'SAU',
}

def _norm(s):
    return ''.join(c for c in unicodedata.normalize('NFD', str(s))
                   if unicodedata.category(c) != 'Mn').lower().strip()

# ── 1. Base skeleton ──────────────────────────────────────────────────────────
print('Building skeleton ...')
base = pd.DataFrame(
    [(city, iso3, yr)
     for city, iso3 in CITY_ISO3.items()
     for yr in YEARS],
    columns=['city', 'country', 'year']
)
print(f'  {len(base)} rows (should be 480)')

# ── 2. NDVI (GEE, city-level) ─────────────────────────────────────────────────
print('Merging NDVI ...')
ndvi = pd.read_csv(RAW + 'gulf_ndvi_2000_2023.csv')[['city', 'year', 'ndvi_mean']]
ndvi = ndvi.rename(columns={'ndvi_mean': 'ndvi'})
base = base.merge(ndvi, on=['city', 'year'], how='left')
print(f'  NDVI missing: {base["ndvi"].isna().sum()}')

# ── 3. NTL calibrated (city-level) ────────────────────────────────────────────
print('Merging NTL ...')
ntl = pd.read_csv(PROC + 'ntl_calibrated_panel.csv')[
    ['city', 'year', 'ntl_calibrated', 'ntl_source', 'ntl_raw']
]
base = base.merge(ntl, on=['city', 'year'], how='left')
base['ntl_log'] = np.log1p(base['ntl_calibrated'].clip(lower=0))
print(f'  NTL missing: {base["ntl_calibrated"].isna().sum()}')

# ── 4. City population (city-level) ───────────────────────────────────────────
print('Merging city populations ...')
pop = pd.read_csv(PROC + 'city_pop_panel.csv')[['city', 'year', 'pop_thousands', 'pop_source']]
pop = pop.rename(columns={'pop_thousands': 'city_pop_th', 'pop_source': 'pop_src'})
base = base.merge(pop, on=['city', 'year'], how='left')
print(f'  Pop missing: {base["city_pop_th"].isna().sum()}')

# ── 5. WDI variables (country-level, wide -> long) ────────────────────────────
def load_wdi(fname, colname):
    df = pd.read_csv(RAW + fname, skiprows=4, encoding='utf-8-sig')
    df = df.loc[:, ~df.columns.str.startswith('Unnamed')]
    df = df[df['Country Code'].isin(GULF_ISO3)].copy()
    yr_cols = [c for c in df.columns if c.isdigit() and 2000 <= int(c) <= 2023]
    long = df.melt(id_vars=['Country Code'], value_vars=yr_cols,
                   var_name='year', value_name=colname)
    long['year'] = long['year'].astype(int)
    long = long.rename(columns={'Country Code': 'country'})
    long[colname] = pd.to_numeric(long[colname], errors='coerce')
    return long[['country', 'year', colname]]

print('Merging WDI variables ...')
wdi_files = {
    'GDP per capita (constant 2015 US$).csv':               'gdp_pc',
    'Electric power consumption (kWh per capita).csv':      'elec_pc',
    'Industry (including construction), value added (% of GDP).csv': 'industry_va',
    'Foreign direct investment, net inflows (% of GDP).csv':'fdi_pct',
    'Urban population (% of total population).csv':         'urban_pct',
}
for fname, colname in wdi_files.items():
    wdi = load_wdi(fname, colname)
    base = base.merge(wdi, on=['country', 'year'], how='left')
    miss = base[colname].isna().sum()
    print(f'  {colname} missing: {miss}')

# ── 6. Oil price (annual mean Brent) ─────────────────────────────────────────
print('Merging oil price ...')
oil = pd.read_csv(RAW + 'Global price of brent crude.csv')
oil['year'] = pd.to_datetime(oil['observation_date']).dt.year
oil_ann = oil.groupby('year')['POILBREUSDM'].mean().reset_index()
oil_ann = oil_ann.rename(columns={'POILBREUSDM': 'oil_price'})
base = base.merge(oil_ann[['year', 'oil_price']], on='year', how='left')
print(f'  oil_price missing: {base["oil_price"].isna().sum()}')

# ── 7. Env expenditure (country-level, IMF, partial) ─────────────────────────
print('Merging env expenditure ...')
env = pd.read_csv(RAW + 'environmental_protection_expenditure.csv', encoding='utf-8-sig')
env = env[
    env['ISO3'].isin(GULF_ISO3) &
    (env['Indicator'] == 'Expenditure on environment protection') &
    (env['Unit'] == 'Percent of GDP')
].copy()
yr_cols = [c for c in env.columns if c.isdigit() and 2000 <= int(c) <= 2022]
env_long = env.melt(id_vars=['ISO3'], value_vars=yr_cols,
                    var_name='year', value_name='env_exp_pct_gdp')
env_long['year'] = env_long['year'].astype(int)
env_long = env_long.rename(columns={'ISO3': 'country'})
env_long['env_exp_pct_gdp'] = pd.to_numeric(env_long['env_exp_pct_gdp'], errors='coerce')
# Zero values in env expenditure are genuinely 0 (reported), keep them
base = base.merge(env_long[['country', 'year', 'env_exp_pct_gdp']],
                  on=['country', 'year'], how='left')
# SAU has no IMF data at all — stays NaN
print(f'  env_exp_pct_gdp missing: {base["env_exp_pct_gdp"].isna().sum()} '
      f'({100*base["env_exp_pct_gdp"].isna().mean():.1f}%)')

# ── 8. Harvard NDVI cross-validation (11 cities, 4 years) ────────────────────
print('Merging Harvard NDVI (cross-validation columns) ...')
harv = pd.read_csv(RAW + 'urban_NDVI.csv', index_col=0, encoding='latin1')
harv_cols = {
    'annual_avg_2010': 'ndvi_harvard_2010',
    'annual_avg_2015': 'ndvi_harvard_2015',
    'annual_avg_2020': 'ndvi_harvard_2020',
    'annual_avg_2021': 'ndvi_harvard_2021',
}
harv_sub = harv[['City'] + list(harv_cols.keys())].rename(columns={**harv_cols, 'City': 'city'})
# Map Harvard city names to our standard names (already matching for the 11 cities)
# Filter to Gulf cities only
harv_sub = harv_sub[harv_sub['city'].isin(CITY_ISO3.keys())].copy()
# Melt to long so we can merge on city-year
harv_long = harv_sub.melt(id_vars='city', var_name='harv_var', value_name='harv_val')
harv_long['year'] = harv_long['harv_var'].str.extract(r'(\d{4})').astype(int)
harv_long = harv_long.rename(columns={'harv_var': '_drop'}).drop(columns='_drop')
# Pivot back wide keyed on city x year
harv_wide = harv_long.pivot_table(index=['city', 'year'], values='harv_val').reset_index()
# Now we need each year as a separate column in the master panel
# Since Harvard years are only 2010/2015/2020/2021, merge each separately
for harv_yr, col_name in [(2010,'ndvi_harvard_2010'),(2015,'ndvi_harvard_2015'),
                           (2020,'ndvi_harvard_2020'),(2021,'ndvi_harvard_2021')]:
    h = harv_sub[['city', harv_cols[f'annual_avg_{harv_yr}']]].rename(
        columns={harv_cols[f'annual_avg_{harv_yr}']: col_name})
    # Add year key to join: these values apply only to that specific year row
    h['year'] = harv_yr
    base = base.merge(h, on=['city', 'year'], how='left')

harv_total = sum(base[f'ndvi_harvard_{y}'].notna().sum()
                 for y in [2010, 2015, 2020, 2021])
print(f'  Harvard NDVI cells filled: {harv_total}')

# ── 9. Final sort and save ────────────────────────────────────────────────────
col_order = [
    'city', 'country', 'year',
    # DVs
    'elec_pc', 'industry_va', 'fdi_pct',
    'ntl_calibrated', 'ntl_log', 'ntl_source', 'ntl_raw',
    # Primary IV
    'ndvi',
    # Controls
    'gdp_pc', 'city_pop_th', 'pop_src', 'urban_pct', 'oil_price',
    # Supplementary
    'env_exp_pct_gdp',
    # Validation
    'ndvi_harvard_2010', 'ndvi_harvard_2015', 'ndvi_harvard_2020', 'ndvi_harvard_2021',
]
base = base[col_order].sort_values(['city', 'year']).reset_index(drop=True)
base.to_csv(PROC + 'master_panel.csv', index=False)
print(f'\nSaved {len(base)} rows -> {PROC}master_panel.csv')

# ── 10. Completeness report ───────────────────────────────────────────────────
print('\n── Completeness report ─────────────────────────────────────────────────')
numeric_cols = [c for c in base.columns if base[c].dtype in [float, 'float64']]
for col in numeric_cols:
    n_obs  = base[col].notna().sum()
    n_miss = base[col].isna().sum()
    pct    = 100 * n_obs / len(base)
    print(f'  {col:25s}  {n_obs:4d}/{len(base)} ({pct:5.1f}%) complete')

print('\n── Missing by country (key WDI variables) ──────────────────────────────')
for col in ['industry_va', 'env_exp_pct_gdp']:
    print(f'\n  {col}:')
    for iso in GULF_ISO3:
        sub  = base[base['country'] == iso]
        miss = sub[col].isna().sum()
        print(f'    {iso}: {miss}/{len(sub)} missing')
