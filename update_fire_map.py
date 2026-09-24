# Imports
import os
import datetime
import urllib.request

import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import Fullscreen

# --- Paths (relative to this script, so it works locally and in GitHub Actions) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUTPUT_PATH = os.path.join(BASE_DIR, 'index.html')

# --- Parameters ---
MAP_KEY = os.getenv('FIRMS_MAP_KEY')

if not MAP_KEY:
    raise RuntimeError("FIRMS_MAP_KEY environment variable is not set.")

AREA = '108.5,-4.5,119.5,7.5'   # Borneo bounding box: west,south,east,north
DAY_RANGE = 3
sources = ['VIIRS_NOAA20_NRT', 'VIIRS_NOAA21_NRT']

# --- Fetch and combine fire data from multiple sources ---
def fetch_firms(source):
    url = f'https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{source}/{AREA}/{DAY_RANGE}'
    # Timeout so a slow or unresponsive FIRMS server can't hang the automated run
    with urllib.request.urlopen(url, timeout=60) as resp:
        df = pd.read_csv(resp)
    required = {'latitude', 'longitude', 'frp', 'acq_date', 'confidence'}
    if not required.issubset(df.columns):
        raise RuntimeError(f"Unexpected FIRMS response for {source}: columns {list(df.columns)}")
    return df

all_fires = [fetch_firms(source) for source in sources]

# Combine into a single DataFrame and remove duplicates
fire_df = pd.concat(all_fires, ignore_index=True).drop_duplicates()

# Convert to GeoDataFrame
fire_gdf = gpd.GeoDataFrame(
    fire_df,
    geometry=gpd.points_from_xy(fire_df.longitude, fire_df.latitude),
    crs='EPSG:4326'
)

# Filter out low-confidence detections
fire_gdf = fire_gdf[fire_gdf['confidence'].isin(['n', 'h'])]

# --- Load range + PA data ---
orangutan_range = (
    gpd.read_file(os.path.join(DATA_DIR, 'Bornean_orangutan_range.shp'))
    .to_crs('EPSG:4326')
)

Indo_PAs = (
    gpd.read_file(os.path.join(DATA_DIR, 'Indo_PAs_borneo.shp'))
    .to_crs('EPSG:4326')
)

# Dissolve once: used for the spatial join (no duplicate matches from overlapping
# polygons) and for drawing the range layer
orangutan_range_dissolved = orangutan_range.dissolve()

# Spatial join: keep only fires within confirmed Bornean orangutan range
fires_in_range = gpd.sjoin(
    fire_gdf,
    orangutan_range_dissolved[['geometry']],
    predicate='within'
)

# Filter out invalid values
fires_in_range = fires_in_range.dropna(subset=['frp', 'acq_date']).copy()
fires_in_range['acq_date'] = pd.to_datetime(fires_in_range['acq_date'], errors='coerce')
fires_in_range = fires_in_range.dropna(subset=['acq_date'])
fires_in_range['acq_date'] = fires_in_range['acq_date'].dt.strftime('%Y-%m-%d')

if fires_in_range.empty:
    print("No fires found within the orangutan range. Map not updated.")
    raise SystemExit

# --- Recency colours ---
today_dt = datetime.datetime.strptime(fires_in_range['acq_date'].max(), '%Y-%m-%d')

def recency_color(acq_date):
    days_ago = (today_dt - datetime.datetime.strptime(str(acq_date), '%Y-%m-%d')).days
    if days_ago == 0:
        return '#7f0000'
    elif days_ago <= 1:
        return '#c1121f'
    elif days_ago <= 2:
        return '#e5533c'
    else:
        return '#f4a582'

# --- Sizing: uniform dots, with only high-intensity fires drawn larger ---
BASE_R = 3          # every fire
HIGH_R = 7          # fires above the threshold
HIGH_FRP = 30       # MW; fixed so the legend means the same thing every day

def scale_radius(frp):
    return HIGH_R if float(frp) > HIGH_FRP else BASE_R

# --- Map ---
m_fire_sized = folium.Map(
    location=[-1, 112],
    zoom_start=7,
    tiles=None,
    prefer_canvas=True,
    control_scale=True,
)

folium.TileLayer(
    tiles='https://{s}.basemaps.cartocdn.com/rastertiles/light_all/{z}/{x}/{y}.png?key=cb1_28oy_1_05571f4015c3314d60d78268',
    attr='&copy; OpenStreetMap, &copy; CARTO',
    subdomains='abcd', max_zoom=20, control=False
).add_to(m_fire_sized)

# Custom panes lock stacking order: fires always render above range/PA layers
folium.map.CustomPane('pa_pane', z_index=390).add_to(m_fire_sized)
folium.map.CustomPane('range_pane', z_index=395).add_to(m_fire_sized)
folium.map.CustomPane('fire_pane', z_index=650).add_to(m_fire_sized)

Fullscreen(
    position='topleft',
    title='Full-screen',
    title_cancel='Exit full-screen',
    force_separate_button=True
).add_to(m_fire_sized)

folium.GeoJson(
    orangutan_range_dissolved,
    style_function=lambda x: {
        'fillColor': '#006400', 'color': '#006400', 'weight': 0.2, 'fillOpacity': 0.2
    },
    name='Bornean orangutan range',
    pane='range_pane'
).add_to(m_fire_sized)

folium.GeoJson(
    Indo_PAs,
    style_function=lambda x: {
        'fillColor': '#00509d', 'color': '#00509d', 'weight': 0.6, 'fillOpacity': 0.1
    },
    name='Protected areas',
    pane='pa_pane'
).add_to(m_fire_sized)

# Draw lowest FRP first so the high-intensity fires end up on top
for row in fires_in_range.sort_values('frp', ascending=True).itertuples():
    popup_html = f"""
    <div style="font-family: Roboto, sans-serif; font-size: 12px;">
        <b>Fire Detection</b><br>
        <b>Date:</b> {row.acq_date}<br>
        <b>FRP:</b> {row.frp:.1f} MW<br>
        <b>Coordinates:</b> {row.latitude:.2f}, {row.longitude:.2f}
    </div>
    """
    base_r = scale_radius(row.frp)
    folium.CircleMarker(
        [row.latitude, row.longitude],
        radius=base_r,
        color='#450a0a',                          # thin dark outline (weight is set by the zoom script)
        weight=0.6,
        opacity=0.5,
        fill=True,
        fill_color=recency_color(row.acq_date),   # recency lives in the fill
        fill_opacity=0.6,
        popup=folium.Popup(popup_html, max_width=220),
        pane='fire_pane',
        baseRadius=base_r
    ).add_to(m_fire_sized)

folium.LayerControl(collapsed=False).add_to(m_fire_sized)

m_fire_sized.get_root().html.add_child(folium.Element("""
<style>
.leaflet-control-layers {
    top: 15px !important;
    right: 15px !important;
    padding: 10px 14px !important;
    font-size: 13px !important;
    border-radius: 6px !important;
}
.leaflet-control-layers-overlays label {
    margin-bottom: 4px !important;
    display: flex !important;
    align-items: center !important;
}
.leaflet-control-layers input[type="checkbox"] {
    transform: scale(1.1);
    margin-right: 4px !important;
}
.leaflet-control-layers-list::before {
    content: 'Layers';
    font-weight: bold;
    font-size: 13px;
    display: block;
    margin-bottom: 6px;
    padding-bottom: 4px;
    border-bottom: 1px solid #eeeeee;
}
.leaflet-control-layers-overlays label:nth-of-type(1)::after {
    content: '';
    display: inline-block;
    width: 12px;
    height: 12px;
    background-color: #006400;
    border-radius: 2px;
    margin-left: 6px;
    vertical-align: middle;
}
.leaflet-control-layers-overlays label:nth-of-type(2)::after {
    content: '';
    display: inline-block;
    width: 12px;
    height: 12px;
    background-color: #00509d;
    border-radius: 2px;
    margin-left: 6px;
    vertical-align: middle;
}
</style>
"""))

m_fire_sized.get_root().html.add_child(folium.Element("""
<style>
.leaflet-control-scale {
    bottom: 25px !important;
    left: 25px !important;
}
.leaflet-control-scale-line {
    background: white;
    border: 1px solid #000000 !important;
    color: #333 !important;
    font-family: Roboto, sans-serif !important;
    font-size: 12px !important;
    padding: 2px 6px !important;
    border-radius: 0 0 4px 4px !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.15);
}
</style>
"""))

legend_js = f'''
<script>
window.addEventListener('load', function() {{
    var legend = L.control({{position: 'bottomright'}});
    legend.onAdd = function (map) {{
        var div = L.DomUtil.create('div', 'info legend');
        div.style.background = 'white';
        div.style.padding = '10px 14px';
        div.style.borderRadius = '6px';
        div.style.fontFamily = 'Roboto';
        div.style.boxShadow = '0 1px 4px rgba(0,0,0,0.3)';
        div.style.marginRight = '15px';
        div.style.marginBottom = '15px';
        div.innerHTML = `
            <div style="font-size: 14px; margin-bottom: 4px;"><b>Recency</b></div>
            <div style="width: 100%; height: 8px; border-radius: 4px; margin-bottom: 3px;
                 background: linear-gradient(to right, #7f0000, #c1121f, #e5533c, #f4a582);"></div>
            <div style="display: flex; justify-content: space-between;
            font-size: 11px; width: 100%; margin-bottom: 8px;">
                 <span>Today</span><span>3 days ago</span>
            </div>
            <div style="display: flex; align-items: center; gap: 6px;">
                 <div class="frp-dot" data-r="{HIGH_R}"
                      style="border-radius: 50%; background-color: #c1121f; opacity: 0.8; flex-shrink: 0;"></div>
                 <span style="font-size: 12px;">High-intensity fire (&gt;{HIGH_FRP} MW)</span>
            </div>
            <div style="font-size: 10px; color: #555; margin-top: 6px;">
                 Click a fire for details.
            </div>
        `;
        return div;
    }};
    legend.addTo({m_fire_sized.get_name()});
}});
</script>
'''
m_fire_sized.get_root().html.add_child(folium.Element(legend_js))

# Zoom-responsive sizing. Must be added AFTER the legend script so the legend
# dot exists when adjustMarkers() first runs.
zoom_scale_js = f'''
<script>
window.addEventListener('load', function() {{
    var map = {m_fire_sized.get_name()};

    function scaleForZoom(zoom, minZoom, maxZoom, minVal, maxVal) {{
        var t = Math.max(0, Math.min(1, (zoom - minZoom) / (maxZoom - minZoom)));
        return minVal + t * (maxVal - minVal);
    }}

    function adjustMarkers() {{
        var zoom = map.getZoom();
        var t = Math.max(0, Math.min(1, (zoom - 5) / (12 - 5)));

        // Power curve: stays small when zoomed out, grows quickly once zoomed in
        var radiusScale = 0.2 + 1.6 * Math.pow(t, 1.5);
        var opacity = 0.5 + 0.3 * t;
        var outlineWeight = scaleForZoom(zoom, 7, 10, 0, 0.7);

        map.eachLayer(function(layer) {{
            if (layer instanceof L.CircleMarker && layer.options.baseRadius) {{
                layer.setRadius(Math.max(1.2, layer.options.baseRadius * radiusScale));
                layer.setStyle({{fillOpacity: opacity, weight: outlineWeight}});
            }}
        }});

        // Keep the legend dot the same size as the high-intensity markers (min 6px so it stays readable)
        document.querySelectorAll('.frp-dot').forEach(function(el) {{
            var d = Math.max(6, Math.min(2 * parseFloat(el.dataset.r) * radiusScale, 40));
            el.style.width = d + 'px';
            el.style.height = d + 'px';
        }});
    }}

    map.on('zoomend', adjustMarkers);
    adjustMarkers();
}});
</script>
'''
m_fire_sized.get_root().html.add_child(folium.Element(zoom_scale_js))

m_fire_sized.save(OUTPUT_PATH)
print(f"Map updated: {len(fires_in_range)} fires in range, "
      f"latest detection {fires_in_range['acq_date'].max()}, "
      f"{datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M} UTC")