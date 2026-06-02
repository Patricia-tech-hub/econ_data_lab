"""
NTL seam calibration: DMSP (2000-2012) -> VIIRS (2013-2023).

Approach: Elvidge-style single-year OLS calibration using 2013 as the
overlap year (DMSP F18 2013 vs VIIRS V21 2013), 20 city observations.

Inputs:
  data/raw/gulf_ntl_dmsp_2013.csv     <- from GEE script 01e
  data/raw/gulf_ntl_dmsp_2000_2012.csv
  data/raw/gulf_ntl_viirs_2013_2023.csv

Outputs:
  data/processed/ntl_calibrated_panel.csv
  outputs/figures/ntl_calibration_scatter.png
  outputs/figures/ntl_city_timeseries.png
  outputs/figures/ntl_distribution_comparison.png
  outputs/tables/ntl_calibration_diagnostics.txt
"""
import sys
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from scipy import stats

from pathlib import Path
_ROOT    = Path(__file__).resolve().parent.parent
RAW_DIR  = str(_ROOT / 'data' / 'raw') + '/'
PROC_DIR = str(_ROOT / 'data' / 'processed') + '/'
FIG_DIR  = str(_ROOT / 'outputs' / 'figures') + '/'
TBL_DIR  = str(_ROOT / 'outputs' / 'tables') + '/'

for d in [PROC_DIR, FIG_DIR, TBL_DIR]:
    os.makedirs(d, exist_ok=True)

# ── Guard: check DMSP 2013 file exists ───────────────────────────────────────
dmsp13_path = RAW_DIR + 'gulf_ntl_dmsp_2013.csv'
if not os.path.exists(dmsp13_path):
    print('ERROR: gulf_ntl_dmsp_2013.csv not found in data/raw/')
    print('Please run scripts/01e_gee_dmsp_2013.py in GEE and download the CSV.')
    sys.exit(1)

# ── Load data ─────────────────────────────────────────────────────────────────
print('Loading NTL data ...')
dmsp_all  = pd.read_csv(RAW_DIR + 'gulf_ntl_dmsp_2000_2012.csv')
viirs_all = pd.read_csv(RAW_DIR + 'gulf_ntl_viirs_2013_2023.csv')
dmsp_2013 = pd.read_csv(dmsp13_path)

# Standardise column names (GEE exports may have lowercase/uppercase variants)
for df in [dmsp_all, viirs_all, dmsp_2013]:
    df.columns = df.columns.str.strip()

# Keep only the columns we need
dmsp_all  = dmsp_all[['city', 'country', 'ntl_mean', 'year']].copy()
viirs_all = viirs_all[['city', 'country', 'ntl_mean', 'year']].copy()
dmsp_2013 = dmsp_2013[['city', 'country', 'ntl_mean']].copy()
dmsp_2013['year'] = 2013

print(f'  DMSP 2000-2012: {len(dmsp_all)} rows, {dmsp_all["city"].nunique()} cities')
print(f'  VIIRS 2013-2023: {len(viirs_all)} rows, {viirs_all["city"].nunique()} cities')
print(f'  DMSP 2013 (calibration anchor): {len(dmsp_2013)} rows')

# ── Step 1: Calibration OLS ───────────────────────────────────────────────────
print('\nStep 1: OLS calibration (DMSP_2013 -> VIIRS_2013) ...')

viirs_2013 = viirs_all[viirs_all['year'] == 2013][['city', 'ntl_mean']].rename(
    columns={'ntl_mean': 'viirs_2013'}
)
calib_df = dmsp_2013[['city', 'ntl_mean']].rename(columns={'ntl_mean': 'dmsp_2013'})
calib_df = calib_df.merge(viirs_2013, on='city', how='inner')

if len(calib_df) < 5:
    print(f'ERROR: only {len(calib_df)} city pairs for calibration (need >= 5).')
    sys.exit(1)

print(f'  N calibration pairs: {len(calib_df)}')

x = calib_df['dmsp_2013'].values
y = calib_df['viirs_2013'].values

slope, intercept, r_value, p_value, se_slope = stats.linregress(x, y)
r2 = r_value ** 2

print(f'  a (intercept) = {intercept:.4f}')
print(f'  b (slope)     = {slope:.4f}')
print(f'  R²            = {r2:.4f}')
print(f'  p-value (b)   = {p_value:.4e}')

if r2 < 0.5:
    r2_warning = (
        f'WARNING: R² = {r2:.3f} < 0.5. '
        'Calibration is unreliable. Consider alternative approaches:\n'
        '  - Using relative changes (ΔNTL) instead of levels\n'
        '  - City-specific scaling factors\n'
        '  - Dropping DMSP years entirely\n'
    )
    print(r2_warning)
else:
    r2_warning = None

# ── Step 2: Apply calibration to DMSP 2000-2012 ──────────────────────────────
print('\nStep 2: Applying calibration to DMSP 2000-2012 ...')
dmsp_calib = dmsp_all.copy()
dmsp_calib['ntl_raw']        = dmsp_calib['ntl_mean']
dmsp_calib['ntl_calibrated'] = intercept + slope * dmsp_calib['ntl_mean']
dmsp_calib['ntl_source']     = 'DMSP_calibrated'
dmsp_calib = dmsp_calib.drop(columns=['ntl_mean'])

# ── Step 3: Concatenate with VIIRS 2013-2023 ─────────────────────────────────
viirs_out = viirs_all.copy()
viirs_out['ntl_raw']        = viirs_out['ntl_mean']
viirs_out['ntl_calibrated'] = viirs_out['ntl_mean']
viirs_out['ntl_source']     = 'VIIRS'
viirs_out = viirs_out.drop(columns=['ntl_mean'])

panel = pd.concat([dmsp_calib, viirs_out], ignore_index=True)
panel = panel.sort_values(['city', 'year']).reset_index(drop=True)

print(f'  Combined panel: {len(panel)} rows, years {panel["year"].min()}-{panel["year"].max()}')

# ── Step 4a: Calibration scatter ─────────────────────────────────────────────
print('\nStep 4: Generating diagnostic plots ...')
fig, ax = plt.subplots(figsize=(7, 6))
ax.scatter(calib_df['dmsp_2013'], calib_df['viirs_2013'],
           color='steelblue', s=80, zorder=3, label='City observations')
x_line = np.linspace(x.min() * 0.9, x.max() * 1.1, 100)
ax.plot(x_line, intercept + slope * x_line,
        color='tomato', linewidth=2, label=f'OLS fit: VIIRS = {intercept:.2f} + {slope:.3f}×DMSP')

# Annotate a few cities
for _, row in calib_df.iterrows():
    ax.annotate(row['city'], (row['dmsp_2013'], row['viirs_2013']),
                fontsize=7, textcoords='offset points', xytext=(4, 3), color='#444')

ax.set_xlabel('DMSP NTL (2013)', fontsize=12)
ax.set_ylabel('VIIRS NTL (2013)', fontsize=12)
ax.set_title(f'NTL Calibration Anchor (2013)\nR² = {r2:.3f}  |  n = {len(calib_df)} cities',
             fontsize=13)
ax.legend(fontsize=10)
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(FIG_DIR + 'ntl_calibration_scatter.png', dpi=150)
plt.close(fig)
print('  Saved ntl_calibration_scatter.png')

# ── Step 4b: City time-series (6 representative cities) ──────────────────────
SHOWCASE = ['Kuwait City', 'Doha', 'Dubai', 'Riyadh', 'Muscat', 'Manama']
fig, axes = plt.subplots(2, 3, figsize=(15, 8), sharex=True)
axes = axes.flatten()

for ax, city in zip(axes, SHOWCASE):
    city_dmsp  = dmsp_all[dmsp_all['city'] == city].sort_values('year')
    city_viirs = viirs_all[viirs_all['city'] == city].sort_values('year')
    city_calib = panel[(panel['city'] == city) & (panel['ntl_source'] == 'DMSP_calibrated')].sort_values('year')

    ax.plot(city_dmsp['year'],  city_dmsp['ntl_mean'],   'o--', color='gray',
            linewidth=1.5, markersize=5, label='Raw DMSP', alpha=0.7)
    ax.plot(city_viirs['year'], city_viirs['ntl_mean'],  's-',  color='steelblue',
            linewidth=2, markersize=5, label='Raw VIIRS')
    ax.plot(city_calib['year'], city_calib['ntl_calibrated'], '^-', color='tomato',
            linewidth=2, markersize=5, label='Calibrated DMSP')
    ax.axvline(x=2012.5, color='black', linestyle=':', linewidth=1.5, label='2012/2013 seam')

    ax.set_title(city, fontsize=11)
    ax.set_xlabel('Year', fontsize=9)
    ax.set_ylabel('NTL mean', fontsize=9)
    ax.xaxis.set_major_locator(mticker.MultipleLocator(4))
    ax.tick_params(axis='x', labelsize=8)
    ax.grid(True, alpha=0.25)

handles, labels = axes[0].get_legend_handles_labels()
fig.legend(handles, labels, loc='lower center', ncol=4, fontsize=10,
           bbox_to_anchor=(0.5, -0.02))
fig.suptitle('NTL: Raw DMSP / Calibrated DMSP / Raw VIIRS (2000-2023)', fontsize=13)
fig.tight_layout(rect=[0, 0.05, 1, 1])
fig.savefig(FIG_DIR + 'ntl_city_timeseries.png', dpi=150)
plt.close(fig)
print('  Saved ntl_city_timeseries.png')

# ── Step 4c: Distribution comparison ─────────────────────────────────────────
calib_vals = panel[panel['ntl_source'] == 'DMSP_calibrated']['ntl_calibrated']
viirs_vals = panel[panel['ntl_source'] == 'VIIRS']['ntl_calibrated']

fig, ax = plt.subplots(figsize=(8, 5))
bins = np.linspace(
    min(calib_vals.min(), viirs_vals.min()),
    max(calib_vals.max(), viirs_vals.max()),
    30
)
ax.hist(calib_vals, bins=bins, alpha=0.6, color='tomato',    label='Calibrated DMSP (2000-2012)')
ax.hist(viirs_vals, bins=bins, alpha=0.6, color='steelblue', label='Raw VIIRS (2013-2023)')
ax.set_xlabel('NTL value', fontsize=12)
ax.set_ylabel('Count (city-years)', fontsize=12)
ax.set_title('NTL Distribution: Calibrated DMSP vs Raw VIIRS', fontsize=13)
ax.legend(fontsize=11)
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(FIG_DIR + 'ntl_distribution_comparison.png', dpi=150)
plt.close(fig)
print('  Saved ntl_distribution_comparison.png')

# ── Step 5: Save panel ────────────────────────────────────────────────────────
out_path = PROC_DIR + 'ntl_calibrated_panel.csv'
panel[['city', 'country', 'year', 'ntl_calibrated', 'ntl_source', 'ntl_raw']].to_csv(
    out_path, index=False
)
print(f'\nSaved {len(panel)} rows -> {out_path}')

# ── Step 6: Diagnostics text file ─────────────────────────────────────────────
diag_lines = [
    'NTL DMSP-VIIRS Calibration Diagnostics',
    '=' * 50,
    '',
    'Method: Elvidge-style single-year OLS calibration',
    'Calibration year: 2013',
    'N observations: {}'.format(len(calib_df)),
    '',
    'OLS: VIIRS_city = a + b x DMSP_city',
    '  a (intercept): {:.6f}'.format(intercept),
    '  b (slope):     {:.6f}'.format(slope),
    '  R²:            {:.4f}'.format(r2),
    '  p-value (b):   {:.4e}'.format(p_value),
    '  SE (slope):    {:.6f}'.format(se_slope),
    '',
    'Calibration pairs (city, DMSP_2013, VIIRS_2013, fitted):',
]
for _, row in calib_df.sort_values('city').iterrows():
    fitted = intercept + slope * row['dmsp_2013']
    diag_lines.append(
        '  {:20s}  DMSP={:6.2f}  VIIRS={:6.2f}  fitted={:6.2f}  resid={:+.2f}'.format(
            row['city'], row['dmsp_2013'], row['viirs_2013'], fitted,
            row['viirs_2013'] - fitted
        )
    )
diag_lines += [
    '',
    'Calibration applied to: DMSP 2000-2012 (formula: ntl_calibrated = a + b * ntl_dmsp_raw)',
    'VIIRS 2013-2023: passed through unchanged (ntl_calibrated = ntl_raw)',
    '',
    'LIMITATIONS:',
    '  - Single-year calibration on n=20 cities (small sample).',
    '  - DMSP and VIIRS have different spectral sensitivities and saturation thresholds.',
    '  - DMSP saturates at DN=63 in urban cores; VIIRS has no saturation.',
    '  - Calibration assumes linear relationship is stable across all DN ranges.',
    '  - Sohar NTL data uses CPD admin boundary; other cities use WUP functional city.',
]

if r2_warning:
    diag_lines += ['', 'QUALITY FLAG:', r2_warning]
else:
    diag_lines += ['', f'R² = {r2:.3f} >= 0.5: calibration accepted.']

diag_text = '\n'.join(diag_lines)
with open(TBL_DIR + 'ntl_calibration_diagnostics.txt', 'w', encoding='utf-8') as f:
    f.write(diag_text)
print(f'Diagnostics -> {TBL_DIR}ntl_calibration_diagnostics.txt')

print('\nTask 2 complete. Summary:')
print(f'  Calibration: VIIRS = {intercept:.3f} + {slope:.4f} x DMSP  (R²={r2:.3f})')
if r2_warning:
    print('  *** R² < 0.5 — review calibration before using in models ***')
