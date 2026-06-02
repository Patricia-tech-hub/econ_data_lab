"""
Build city_pop_panel.csv (2000-2023) for 20 Gulf cities.

Sources:
  Primary  -- UN WUP 2025, File 21 (cities >= 50k inhabitants), units: thousands
  Fallback -- citypopulation.de for cities absent from WUP:
              Sharjah, Ajman, Khobar
              (Al Mubarraz resolved via WUP "Al Ahsa" agglomeration)

Output: data/processed/city_pop_panel.csv
Columns: city, country_iso3, year, pop_thousands, pop_source
"""
import re
import time
import unicodedata

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

from pathlib import Path
_ROOT    = Path(__file__).resolve().parent.parent
RAW_DIR  = str(_ROOT / 'data' / 'raw') + '/'
PROC_DIR = str(_ROOT / 'data' / 'processed') + '/'
WUP_FILE = RAW_DIR + 'un_wup2025_cities_50k.xlsx'

YEARS = list(range(2000, 2024))

ISO3_MAP = {
    'Kuwait City': 'KWT', 'Doha': 'QAT',
    'Dubai': 'ARE', 'Abu Dhabi': 'ARE', 'Sharjah': 'ARE',
    'Al Ain': 'ARE', 'Ras Al Khaimah': 'ARE', 'Ajman': 'ARE',
    'Manama': 'BHR', 'Muscat': 'OMN', 'Sohar': 'OMN',
    'Riyadh': 'SAU', 'Jeddah': 'SAU', 'Dammam': 'SAU',
    'Mecca': 'SAU', 'Medina': 'SAU', 'Khobar': 'SAU',
    'Taif': 'SAU', 'Buraydah': 'SAU', 'Al Mubarraz': 'SAU',
}

CITIES_NEEDED = set(ISO3_MAP.keys())

def _norm(s):
    return ''.join(
        c for c in unicodedata.normalize('NFD', str(s))
        if unicodedata.category(c) != 'Mn'
    ).lower().strip()

# Normalized WUP city name substring -> (our city name, iso3)
# Key is a distinctive fragment that appears in the normalized WUP City_Name.
# Using substrings so diacritic variants all collapse the same way.
WUP_SUBSTRINGS = [
    ('al kuwayt',          'Kuwait City',    'KWT'),
    ('kuwait city',        'Kuwait City',    'KWT'),
    ('ad-dawhah',          'Doha',           'QAT'),
    ('dawhah',             'Doha',           'QAT'),
    ('dubayy',             'Dubai',          'ARE'),
    # "dubai" plain string
    ('dubai',              'Dubai',          'ARE'),
    ('abu zabi',           'Abu Dhabi',      'ARE'),   # Abu Dhabi with diacritics stripped
    ('abu dhabi',          'Abu Dhabi',      'ARE'),
    ('ash-shariqah',       'Sharjah',        'ARE'),
    ('shariqah',           'Sharjah',        'ARE'),
    ("al-'ayn",            'Al Ain',         'ARE'),
    ('al ain',             'Al Ain',         'ARE'),
    ('ras al-khaymah',     'Ras Al Khaimah', 'ARE'),
    ('ras al khaimah',     'Ras Al Khaimah', 'ARE'),
    ("'ajman",             'Ajman',          'ARE'),
    ('ajman',              'Ajman',          'ARE'),
    ('al-manamah',         'Manama',         'BHR'),
    ('manamah',            'Manama',         'BHR'),
    ('masqat',             'Muscat',         'OMN'),
    ('muscat',             'Muscat',         'OMN'),
    ('sohar',              'Sohar',          'OMN'),
    ('ar-riyad',           'Riyadh',         'SAU'),   # diacritics stripped
    ('riyadh',             'Riyadh',         'SAU'),
    ('jiddah',             'Jeddah',         'SAU'),
    ('jeddah',             'Jeddah',         'SAU'),
    ('ad-dammam',          'Dammam',         'SAU'),
    ('dammam',             'Dammam',         'SAU'),
    ('makkah',             'Mecca',          'SAU'),
    ('mecca',              'Mecca',          'SAU'),
    ('al-madinah',         'Medina',         'SAU'),
    ('medina',             'Medina',         'SAU'),
    ("at ta'if",           'Taif',           'SAU'),
    ("at-ta'if",           'Taif',           'SAU'),
    ('taif',               'Taif',           'SAU'),
    ('buraydah',           'Buraydah',       'SAU'),
    # Al Ahsa agglomeration used as proxy for Al Mubarraz
    ('al ahsa',            'Al Mubarraz',    'SAU'),
]

def match_wup_name(city_name_raw):
    """Return (our_city, iso3) or None if no match."""
    normed = _norm(city_name_raw)
    for fragment, city, iso3 in WUP_SUBSTRINGS:
        if fragment in normed:
            return city, iso3
    return None


# ── Step 1: Load WUP 2025 ────────────────────────────────────────────────────
print('Loading UN WUP 2025 ...')
df_wup = pd.read_excel(WUP_FILE, sheet_name='Data', header=0)

gulf_iso3 = {'KWT', 'QAT', 'BHR', 'ARE', 'OMN', 'SAU'}
gulf_wup  = df_wup[df_wup['ISO3_Code'].isin(gulf_iso3)].copy()

rows_wup = []
matched  = set()

for _, row in gulf_wup.iterrows():
    city_name_raw = str(row['City_Name'])
    match = match_wup_name(city_name_raw)
    if match is None:
        continue
    our_city, iso3 = match
    if our_city in matched:
        continue  # keep first match only

    for y in YEARS:
        val = row.get(str(y), None)
        rows_wup.append({
            'city':          our_city,
            'country_iso3':  iso3,
            'year':          y,
            'pop_thousands': float(val) if pd.notna(val) else None,
            'pop_source':    'UN WUP 2025',
        })
    matched.add(our_city)

df_panel = pd.DataFrame(rows_wup)
missing  = CITIES_NEEDED - matched
print(f'Matched from WUP ({len(matched)}): {sorted(matched)}')
print(f'Still missing   ({len(missing)}): {sorted(missing)}')


# ── Step 2: citypopulation.de fallback ───────────────────────────────────────
# Sohar: WUP only has data from 2020 (city crossed WUP threshold late).
# CPD Oman uses the administrative wilayah boundary (different definition),
# but provides consistent intra-city time series (census: 2003, 2010, 2020).
CPD_CONFIG = {
    'Sharjah': ('uae',         'Sharjah'),
    'Ajman':   ('uae',         'Ajman'),
    'Khobar':  ('saudiarabia', 'Khobar'),
    'Sohar':   ('oman',        'Sohar'),
}

SCRAPE_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0 Safari/537.36'
    )
}
YEAR_RE = re.compile(r'(\d{4})-\d{2}-\d{2}')


def scrape_cpd(city_name, country_slug, search_alias):
    url = f'https://www.citypopulation.de/en/{country_slug}/cities/'
    print(f'  Scraping {url} for "{search_alias}" ...')
    try:
        r = requests.get(url, headers=SCRAPE_HEADERS, timeout=25)
        r.raise_for_status()
    except Exception as e:
        print(f'    Request failed: {e}')
        return {}

    soup = BeautifulSoup(r.text, 'lxml')
    alias_norm = _norm(search_alias)
    year_data  = {}

    for table in soup.find_all('table'):
        ths = [th.get_text(strip=True) for th in table.find_all('th')]
        yr_idx = {}
        for i, th in enumerate(ths):
            m = YEAR_RE.search(th)
            if m:
                yr_idx[int(m.group(1))] = i
        if not yr_idx:
            continue

        for tr in table.find_all('tr'):
            tds = tr.find_all('td')
            if not tds:
                continue
            # Some CPD tables put the city name in tds[0], others in tds[1]
            label_norm = ' '.join(_norm(td.get_text(strip=True)) for td in tds[:2])
            if alias_norm not in label_norm:
                continue

            for yr, idx in yr_idx.items():
                if 2000 <= yr <= 2023 and idx < len(tds):
                    raw = (tds[idx].get_text(strip=True)
                           .replace(',', '').replace('.', '').replace('\xa0', '').strip())
                    try:
                        year_data[yr] = int(raw) / 1000.0
                    except ValueError:
                        pass

        if year_data:
            break   # found our city in this table

    if not year_data:
        print(f'    No data found for {city_name}')
        return {}

    # Linear interpolation to fill all YEARS
    known_yrs = sorted(year_data.keys())
    all_data  = {}
    for y in YEARS:
        if y in year_data:
            all_data[y] = year_data[y]
        else:
            before = [k for k in known_yrs if k <= y]
            after  = [k for k in known_yrs if k >= y]
            if before and after:
                y0, y1 = before[-1], after[0]
                t = (y - y0) / (y1 - y0) if y1 != y0 else 0
                all_data[y] = year_data[y0] + t * (year_data[y1] - year_data[y0])
            elif before:
                all_data[y] = year_data[before[-1]]
            else:
                all_data[y] = year_data[after[0]]

    anchors = len([k for k in year_data if 2000 <= k <= 2023])
    print(f'    {anchors} anchor years -> {len(all_data)} interpolated rows')
    return all_data


# Force Sohar through CPD even though WUP matched it (WUP only has 2020-2023,
# CPD provides full 2003/2010/2020 census coverage for backfilling 2000-2019).
FORCE_CPD = {'Sohar'}
missing |= FORCE_CPD
df_panel = df_panel[~df_panel['city'].isin(FORCE_CPD)]  # drop partial WUP rows

fallback_rows = []
for city in sorted(missing):
    if city not in CPD_CONFIG:
        print(f'  WARNING: no fallback source configured for {city}')
        continue
    country_slug, search_alias = CPD_CONFIG[city]
    year_data = scrape_cpd(city, country_slug, search_alias)
    if not year_data:
        continue
    for y, pop in year_data.items():
        fallback_rows.append({
            'city':          city,
            'country_iso3':  ISO3_MAP[city],
            'year':          y,
            'pop_thousands': round(pop, 3),
            'pop_source':    'citypopulation.de',
        })
    time.sleep(2)

if fallback_rows:
    df_panel = pd.concat([df_panel, pd.DataFrame(fallback_rows)], ignore_index=True)
    scraped  = set(pd.DataFrame(fallback_rows)['city'].unique())
    missing -= scraped
    print(f'Scraped from citypopulation.de: {sorted(scraped)}')

if missing:
    print(f'WARNING: still missing after fallback: {sorted(missing)}')


# ── Step 3: Save ─────────────────────────────────────────────────────────────
df_panel = df_panel.sort_values(['city', 'year']).reset_index(drop=True)
out_path = PROC_DIR + 'city_pop_panel.csv'
df_panel.to_csv(out_path, index=False)
print(f'\nSaved {len(df_panel)} rows -> {out_path}')


# ── Step 4: Validation ────────────────────────────────────────────────────────
check_years = [2000, 2010, 2020, 2023]
pivot = (
    df_panel[df_panel['year'].isin(check_years)]
    .pivot_table(index=['city', 'country_iso3', 'pop_source'],
                 columns='year', values='pop_thousands', aggfunc='first')
    .reset_index()
)
pivot.columns.name = None
pivot.columns = [str(c) for c in pivot.columns]

# Sanity checks (expected approximate values)
SANITY = {
    'Riyadh':     {2010: 5000},
    'Dubai':      {2010: 2000},
    'Jeddah':     {2010: 3000},
    'Kuwait City':{2010: 2000},
}

with open(str(_ROOT / 'outputs' / 'validation.txt'), 'w', encoding='utf-8') as f:
    f.write('=== Validation: population (thousands) ===\n\n')
    f.write(pivot.to_string(index=False))
    f.write('\n\n=== Sanity checks ===\n')
    for city, yr_vals in SANITY.items():
        row = pivot[pivot['city'] == city]
        if row.empty:
            f.write(f'  {city}: NOT IN PANEL\n')
            continue
        for yr, expected in yr_vals.items():
            actual = row.iloc[0].get(str(yr), None)
            try:
                actual_f = float(actual)
                ok = 'OK' if 0.5 * expected <= actual_f <= 2.0 * expected else 'SUSPICIOUS'
                f.write(f'  {city} {yr}: {actual_f:.0f}k (expected ~{expected}k) [{ok}]\n')
            except Exception:
                f.write(f'  {city} {yr}: {actual}\n')

    # Cross-check vs old city_populations.csv
    f.write('\n=== Cross-check vs raw/city_populations.csv (should match to <1%) ===\n')
    old_file = pd.read_csv(RAW_DIR + 'city_populations.csv', sep=';', encoding='utf-8-sig')
    # Old file uses period as European thousands separator -> strip and treat as integer then /1000
    mapping = {
        'Al Kuwayt (Kuwait City)': 'Kuwait City',
        'Dubai':                   'Dubai',
        'Ad-Dawhah (Doha)':        'Doha',
    }
    for old_name, our_name in mapping.items():
        old_row = old_file[old_file['City_Name'] == old_name]
        if old_row.empty:
            continue
        new_row = pivot[pivot['city'] == our_name]
        if new_row.empty:
            continue
        f.write(f'\n  {our_name}:\n')
        for y in ['2000', '2010', '2020']:
            old_raw = str(old_row.iloc[0][y])
            # Strip period (thousands sep) to get integer, then divide by 1000
            try:
                old_k = float(old_raw.replace('.', '').replace(',', '.'))
            except Exception:
                old_k = None
            new_k = new_row.iloc[0].get(y, None)
            try:
                new_kf = float(new_k)
            except Exception:
                new_kf = None
            if old_k and new_kf:
                diff = abs(old_k - new_kf) / max(new_kf, 1) * 100
                flag = ' <- FLAG >1%' if diff > 1 else ''
                f.write(f'    {y}: old={old_k:.0f}k  new={new_kf:.1f}k  diff={diff:.2f}%{flag}\n')
            else:
                f.write(f'    {y}: old={old_raw}  new={new_k}\n')

print('\nValidation written to temp file.')