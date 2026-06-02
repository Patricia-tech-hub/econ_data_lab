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

# ── VIIRS V21 covers 2013-2021 ───────────────────────────────────────────────
V21_YEARS = list(range(2013, 2022))   # 2013..2021 inclusive

def extract_v21_year(year):
    img = (ee.ImageCollection('NOAA/VIIRS/DNB/ANNUAL_V21')
             .filter(ee.Filter.calendarRange(year, year, 'year'))
             .select('average')
             .first())   # one image per year — use first(), not .mean()

    def reduce_city(feat):
        stats = img.reduceRegion(
            reducer   = ee.Reducer.mean(),
            geometry  = feat.geometry(),
            scale     = SCALE_M,
            maxPixels = 1e9
        )
        return feat.set('ntl_mean',   stats.get('average')) \
                   .set('year',       year) \
                   .set('ntl_source', 'VIIRS_V21')
    return city_fc.map(reduce_city)

# ── VIIRS V22 covers 2022+ ───────────────────────────────────────────────────
V22_YEARS = [2022, 2023]

def extract_v22_year(year):
    img = (ee.ImageCollection('NOAA/VIIRS/DNB/ANNUAL_V22')
             .filter(ee.Filter.calendarRange(year, year, 'year'))
             .select('average')
             .first())

    def reduce_city(feat):
        stats = img.reduceRegion(
            reducer   = ee.Reducer.mean(),
            geometry  = feat.geometry(),
            scale     = SCALE_M,
            maxPixels = 1e9
        )
        return feat.set('ntl_mean',   stats.get('average')) \
                   .set('year',       year) \
                   .set('ntl_source', 'VIIRS_V22')
    return city_fc.map(reduce_city)

# ── Build merged collection ──────────────────────────────────────────────────
print("Building VIIRS V21 (2013-2021) and V22 (2022-2023)...")
v21_cols = [extract_v21_year(y) for y in V21_YEARS]
v22_cols = [extract_v22_year(y) for y in V22_YEARS]
all_cols = v21_cols + v22_cols
merged   = ee.FeatureCollection(all_cols).flatten()

task = ee.batch.Export.table.toDrive(
    collection     = merged,
    description    = 'gulf_ntl_viirs_2013_2023',
    folder         = DRIVE_DIR,
    fileNamePrefix = 'gulf_ntl_viirs_2013_2023',
    fileFormat     = 'CSV'
)
task.start()
print(f"  Task submitted: {task.id}")

print("\nMonitoring (Ctrl+C to stop)...\n")
try:
    while True:
        s = task.status()
        print(f"  VIIRS 2013-2023: {s['state']}")
        if s['state'] in ('COMPLETED', 'FAILED', 'CANCELLED'):
            if s['state'] == 'FAILED':
                print("  Error:", s.get('error_message'))
            break
        print("  (waiting 30s...)\n")
        time.sleep(30)
except KeyboardInterrupt:
    print("\nStopped. Check: code.earthengine.google.com/tasks")