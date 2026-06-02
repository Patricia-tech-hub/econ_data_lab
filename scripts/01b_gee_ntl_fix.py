import ee
import time

ee.Initialize(project='econdatalab')

CITIES = [
    {"city": "Kuwait City",    "country": "KWT", "lat": 29.37, "lon": 47.98},
    {"city": "Doha",           "country": "QAT", "lat": 25.29, "lon": 51.53},
    {"city": "Dubai",          "country": "ARE", "lat": 25.20, "lon": 55.27},
    {"city": "Abu Dhabi",      "country": "ARE", "lat": 24.45, "lon": 54.38},
    {"city": "Sharjah",        "country": "ARE", "lat": 25.34, "lon": 55.39},
    {"city": "Al Ain",         "country": "ARE", "lat": 24.21, "lon": 55.76},
    {"city": "Ras Al Khaimah", "country": "ARE", "lat": 25.79, "lon": 55.94},
    {"city": "Ajman",          "country": "ARE", "lat": 25.41, "lon": 55.44},
    {"city": "Manama",         "country": "BHR", "lat": 26.22, "lon": 50.59},
    {"city": "Muscat",         "country": "OMN", "lat": 23.61, "lon": 58.59},
    {"city": "Sohar",          "country": "OMN", "lat": 24.36, "lon": 56.75},
    {"city": "Riyadh",         "country": "SAU", "lat": 24.69, "lon": 46.72},
    {"city": "Jeddah",         "country": "SAU", "lat": 21.49, "lon": 39.19},
    {"city": "Dammam",         "country": "SAU", "lat": 26.43, "lon": 50.10},
    {"city": "Mecca",          "country": "SAU", "lat": 21.39, "lon": 39.86},
    {"city": "Medina",         "country": "SAU", "lat": 24.47, "lon": 39.61},
    {"city": "Khobar",         "country": "SAU", "lat": 26.28, "lon": 50.21},
    {"city": "Taif",           "country": "SAU", "lat": 21.27, "lon": 40.42},
    {"city": "Buraydah",       "country": "SAU", "lat": 26.33, "lon": 43.97},
    {"city": "Al Mubarraz",    "country": "SAU", "lat": 25.43, "lon": 49.59},
]

BUFFER_M  = 20000
SCALE_M   = 500
DRIVE_DIR = 'GEE_Gulf_NBS'

def make_city_fc(cities, buffer_m):
    features = []
    for c in cities:
        pt  = ee.Geometry.Point([c['lon'], c['lat']])
        buf = pt.buffer(buffer_m)
        features.append(ee.Feature(buf, {
            'city': c['city'], 'country': c['country']
        }))
    return ee.FeatureCollection(features)

city_fc = make_city_fc(CITIES, BUFFER_M)

# ── DMSP-OLS 2000–2012 ────────────────────────────────────────────────────────
# Each year in DMSP is a separate image, not a collection with dates
# We use the annual composites directly by filtering on system:index
DMSP_YEARS = list(range(2000, 2013))

def extract_dmsp_year(year):
    # DMSP annual composites: filter by year in the image properties
    col = (ee.ImageCollection('NOAA/DMSP-OLS/NIGHTTIME_LIGHTS')
             .filter(ee.Filter.calendarRange(year, year, 'year'))
             .select('stable_lights')
             .mean())

    def reduce_city(feat):
        stats = col.reduceRegion(
            reducer   = ee.Reducer.mean(),
            geometry  = feat.geometry(),
            scale     = SCALE_M,
            maxPixels = 1e9
        )
        return feat.set('ntl_mean',   stats.get('stable_lights')) \
                   .set('year',       year) \
                   .set('ntl_source', 'DMSP')

    return city_fc.map(reduce_city)

# ── VIIRS DNB 2013–2023 ───────────────────────────────────────────────────────
# Using VIIRS Stray Light Corrected Nighttime Day/Night Band Composites
VIIRS_YEARS = list(range(2013, 2024))

def extract_viirs_year(year):
    col = (ee.ImageCollection('NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG')
             .select('avg_rad')
             .filter(ee.Filter.calendarRange(year, year, 'year'))
             .mean())

    def reduce_city(feat):
        stats = col.reduceRegion(
            reducer   = ee.Reducer.mean(),
            geometry  = feat.geometry(),
            scale     = SCALE_M,
            maxPixels = 1e9
        )
        return feat.set('ntl_mean',   stats.get('avg_rad')) \
                   .set('year',       year) \
                   .set('ntl_source', 'VIIRS')

    return city_fc.map(reduce_city)

# ── Submit as two separate tasks ──────────────────────────────────────────────
print("Building DMSP collections (2000-2012)...")
dmsp_cols   = [extract_dmsp_year(y)  for y in DMSP_YEARS]
dmsp_merged = ee.FeatureCollection(dmsp_cols).flatten()
dmsp_task   = ee.batch.Export.table.toDrive(
    collection     = dmsp_merged,
    description    = 'gulf_ntl_dmsp_2000_2012',
    folder         = DRIVE_DIR,
    fileNamePrefix = 'gulf_ntl_dmsp_2000_2012',
    fileFormat     = 'CSV'
)
dmsp_task.start()
print(f"  DMSP task submitted: {dmsp_task.id}")

print("Building VIIRS collections (2013-2023)...")
viirs_cols   = [extract_viirs_year(y) for y in VIIRS_YEARS]
viirs_merged = ee.FeatureCollection(viirs_cols).flatten()
viirs_task   = ee.batch.Export.table.toDrive(
    collection     = viirs_merged,
    description    = 'gulf_ntl_viirs_2013_2023',
    folder         = DRIVE_DIR,
    fileNamePrefix = 'gulf_ntl_viirs_2013_2023',
    fileFormat     = 'CSV'
)
viirs_task.start()
print(f"  VIIRS task submitted: {viirs_task.id}")

# ── Monitor ───────────────────────────────────────────────────────────────────
print("\nMonitoring (Ctrl+C to stop — tasks keep running in GEE)...\n")
tasks = {'DMSP 2000-2012': dmsp_task, 'VIIRS 2013-2023': viirs_task}

try:
    while True:
        all_done = True
        for name, task in tasks.items():
            state = task.status()['state']
            print(f"  {name}: {state}")
            if state not in ('COMPLETED', 'FAILED', 'CANCELLED'):
                all_done = False
        if all_done:
            print("\nAll tasks finished.")
            break
        print("  (waiting 30s...)\n")
        time.sleep(30)
except KeyboardInterrupt:
    print("\nStopped monitoring. Check: code.earthengine.google.com/tasks")