"""
Extract DMSP-OLS NTL for all 20 Gulf cities for year 2013.
Exports to Drive folder GEE_Gulf_NBS as gulf_ntl_dmsp_2013.csv.

DMSP-OLS NIGHTTIME_LIGHTS collection covers through 2013 (last satellite: F18).
This provides the calibration anchor year alongside the existing VIIRS 2013 data.
"""
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
YEAR      = 2013

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

# DMSP-OLS annual composites — F18 satellite covers 2010-2013
# Band 'stable_lights' is the annual stable lights DN (0-63)
dmsp_col = ee.ImageCollection('NOAA/DMSP-OLS/NIGHTTIME_LIGHTS')

# Filter to 2013 F18 image (most recent, least inter-satellite drift)
img_2013 = (dmsp_col
             .filter(ee.Filter.calendarRange(YEAR, YEAR, 'year'))
             .select('stable_lights')
             .mean())   # mean across satellites that observed 2013

def extract_ntl(feature):
    city_geom = feature.geometry()
    stats = img_2013.reduceRegion(
        reducer   = ee.Reducer.mean(),
        geometry  = city_geom,
        scale     = SCALE_M,
        maxPixels = 1e9
    )
    return feature.set({
        'ntl_mean':   stats.get('stable_lights'),
        'ntl_source': 'DMSP',
        'year':       YEAR,
    })

results_fc = city_fc.map(extract_ntl)

task = ee.batch.Export.table.toDrive(
    collection  = results_fc,
    description = 'gulf_ntl_dmsp_2013',
    folder      = DRIVE_DIR,
    fileNamePrefix = 'gulf_ntl_dmsp_2013',
    fileFormat  = 'CSV',
    selectors   = ['city', 'country', 'ntl_mean', 'ntl_source', 'year'],
)

task.start()
print(f'Task submitted: gulf_ntl_dmsp_2013')
print(f'Task ID: {task.id}')

# Poll until done
for _ in range(60):
    status = task.status()
    state  = status['state']
    print(f'  State: {state}')
    if state in ('COMPLETED', 'FAILED', 'CANCELLED'):
        break
    time.sleep(30)

if state == 'COMPLETED':
    print('Export complete. Download gulf_ntl_dmsp_2013.csv from Google Drive > GEE_Gulf_NBS/')
else:
    print(f'Task ended with state: {state}')
    print(status.get('error_message', ''))
