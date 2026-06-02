import ee
import time

# ── Initialise with your project ─────────────────────────────────────────────
ee.Initialize(project='econdatalab')

# ── 20-city definitions ───────────────────────────────────────────────────────
CITIES = [
    {"city": "Kuwait City",   "country": "KWT", "lat": 29.37, "lon": 47.98},
    {"city": "Doha",          "country": "QAT", "lat": 25.29, "lon": 51.53},
    {"city": "Dubai",         "country": "ARE", "lat": 25.20, "lon": 55.27},
    {"city": "Abu Dhabi",     "country": "ARE", "lat": 24.45, "lon": 54.38},
    {"city": "Sharjah",       "country": "ARE", "lat": 25.34, "lon": 55.39},
    {"city": "Al Ain",        "country": "ARE", "lat": 24.21, "lon": 55.76},
    {"city": "Ras Al Khaimah","country": "ARE", "lat": 25.79, "lon": 55.94},
    {"city": "Ajman",         "country": "ARE", "lat": 25.41, "lon": 55.44},
    {"city": "Manama",        "country": "BHR", "lat": 26.22, "lon": 50.59},
    {"city": "Muscat",        "country": "OMN", "lat": 23.61, "lon": 58.59},
    {"city": "Sohar",         "country": "OMN", "lat": 24.36, "lon": 56.75},
    {"city": "Riyadh",        "country": "SAU", "lat": 24.69, "lon": 46.72},
    {"city": "Jeddah",        "country": "SAU", "lat": 21.49, "lon": 39.19},
    {"city": "Dammam",        "country": "SAU", "lat": 26.43, "lon": 50.10},
    {"city": "Mecca",         "country": "SAU", "lat": 21.39, "lon": 39.86},
    {"city": "Medina",        "country": "SAU", "lat": 24.47, "lon": 39.61},
    {"city": "Khobar",        "country": "SAU", "lat": 26.28, "lon": 50.21},
    {"city": "Taif",          "country": "SAU", "lat": 21.27, "lon": 40.42},
    {"city": "Buraydah",      "country": "SAU", "lat": 26.33, "lon": 43.97},
    {"city": "Al Mubarraz",   "country": "SAU", "lat": 25.43, "lon": 49.59},
]

YEARS      = list(range(2000, 2024))
BUFFER_M   = 20000   # 20 km radius urban buffer
SCALE_M    = 1000    # 1 km resolution (MODIS native)
DRIVE_DIR  = 'GEE_Gulf_NBS'   # folder created automatically in your Google Drive

# ── Build city feature collection ─────────────────────────────────────────────
def make_city_fc(cities, buffer_m):
    features = []
    for c in cities:
        pt = ee.Geometry.Point([c['lon'], c['lat']])
        buf = pt.buffer(buffer_m)
        feat = ee.Feature(buf, {'city': c['city'], 'country': c['country']})
        features.append(feat)
    return ee.FeatureCollection(features)

city_fc = make_city_fc(CITIES, BUFFER_M)

# ── MODIS NDVI annual mean ─────────────────────────────────────────────────────
def extract_ndvi_year(year):
    start = f'{year}-01-01'
    end   = f'{year}-12-31'
    ndvi  = (ee.ImageCollection('MODIS/061/MOD13A2')
               .select('NDVI')
               .filterDate(start, end)
               .mean()
               .multiply(0.0001))          # apply MODIS scale factor

    def reduce_city(feat):
        stats = ndvi.reduceRegion(
            reducer   = ee.Reducer.mean(),
            geometry  = feat.geometry(),
            scale     = SCALE_M,
            maxPixels = 1e9
        )
        return feat.set('ndvi_mean', stats.get('NDVI')) \
                   .set('year', year)

    return city_fc.map(reduce_city)

# ── VIIRS nighttime lights annual mean ────────────────────────────────────────
# Black Marble VNL V21 monthly → annual mean (available 2012–present)
# For 2000–2011 we use DMSP-OLS harmonised (F-series) as a bridge
def extract_viirs_year(year):
    start = f'{year}-01-01'
    end   = f'{year}-12-31'

    if year >= 2012:
        ntl = (ee.ImageCollection('NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG')
                 .select('avg_rad')
                 .filterDate(start, end)
                 .mean())
        band = 'avg_rad'
    else:
        # DMSP-OLS stable lights (1992–2013) — use as pre-VIIRS bridge
        ntl = (ee.ImageCollection('NOAA/DMSP-OLS/NIGHTTIME_LIGHTS')
                 .select('stable_lights')
                 .filterDate(start, end)
                 .mean())
        band = 'stable_lights'

    def reduce_city(feat):
        stats = ntl.reduceRegion(
            reducer   = ee.Reducer.mean(),
            geometry  = feat.geometry(),
            scale     = SCALE_M,
            maxPixels = 1e9
        )
        return feat.set('ntl_mean', stats.get(band)) \
                   .set('year', year) \
                   .set('ntl_source', 'VIIRS' if year >= 2012 else 'DMSP')

    return city_fc.map(reduce_city)

# ── Submit export tasks ────────────────────────────────────────────────────────
def submit_export(fc, description, folder=DRIVE_DIR):
    task = ee.batch.Export.table.toDrive(
        collection       = fc,
        description      = description,
        folder           = folder,
        fileNamePrefix   = description,
        fileFormat       = 'CSV'
    )
    task.start()
    return task

print("Submitting NDVI extraction tasks...")
ndvi_collections = [extract_ndvi_year(y) for y in YEARS]
ndvi_merged      = ee.FeatureCollection(ndvi_collections).flatten()
ndvi_task        = submit_export(ndvi_merged, 'gulf_ndvi_2000_2023')
print(f"  NDVI task submitted: {ndvi_task.id}")

print("Submitting nighttime lights extraction tasks...")
ntl_collections = [extract_viirs_year(y) for y in YEARS]
ntl_merged      = ee.FeatureCollection(ntl_collections).flatten()
ntl_task        = submit_export(ntl_merged, 'gulf_ntl_2000_2023')
print(f"  NTL task submitted: {ntl_task.id}")

# ── Monitor task status ────────────────────────────────────────────────────────
print("\nMonitoring tasks (checks every 30 seconds, Ctrl+C to stop monitoring)...")
print("Tasks will continue running in GEE even if you stop monitoring.\n")

tasks = {'NDVI': ndvi_task, 'NTL': ntl_task}

try:
    while True:
        all_done = True
        for name, task in tasks.items():
            status = task.status()
            state  = status['state']
            print(f"  {name}: {state}")
            if state not in ('COMPLETED', 'FAILED', 'CANCELLED'):
                all_done = False
        if all_done:
            print("\nAll tasks finished.")
            break
        print("  (waiting 30 seconds...)\n")
        time.sleep(30)
except KeyboardInterrupt:
    print("\nMonitoring stopped. Check task status at code.earthengine.google.com/tasks")