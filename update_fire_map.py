# update_fire_map.py
import pandas as pd
import geopandas as gpd
import folium
from folium import GeoJson
import datetime
import numpy as np
import os

MAP_KEY = os.environ['FIRMS_MAP_KEY']  # from GitHub Actions secret, not hardcoded
SOURCE = 'VIIRS_NOAA20_NRT'
AREA = '108.5,-4.5,119.5,7.5'
DAY_RANGE = 5

# --- Fetch fire data ---
area_url = f'https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{SOURCE}/{AREA}/{DAY_RANGE}'
fire_df = pd.read_csv(area_url)
fire_gdf = gpd.GeoDataFrame(
    fire_df, geometry=gpd.points_from_xy(fire_df.longitude, fire_df.latitude), crs='EPSG:4326'
)
fire_gdf = fire_gdf[fire_gdf['confidence'].isin(['n', 'h'])]

# --- Load range + PA data (committed to the repo alongside the script) ---
ape_ranges = gpd.read_file('data/Ape_ranges.shp')
orangutan_range = ape_ranges[(ape_ranges['sci_name'] == 'Pongo pygmaeus') & (ape_ranges['presence'] == 1)]
orangutan_range_dissolved = orangutan_range.dissolve()

Indo_PAs_borneo = gpd.read_file('data/Indo_PAs_borneo.shp')  # pre-clipped, saved once

fires_in_range = gpd.sjoin(fire_gdf, orangutan_range, predicate='within')

# --- Build the map 
m_fire_sized = folium.Map(location=[-1, 112], zoom_start=7, tiles=None)

folium.TileLayer(
    tiles='https://{s}.basemaps.cartocdn.com/rastertiles/light_all/{z}/{x}/{y}.png?key=cb1_28oy_1_05571f4015c3314d60d78268',
    attr='&copy; OpenStreetMap, &copy; CARTO',
    subdomains='abcd', max_zoom=20, control=False
).add_to(m_fire_sized)

# Custom panes to lock stacking order, fires always render above range/PA layers,
# regardless of add order or LayerControl toggling
folium.map.CustomPane('pa_pane', z_index=390).add_to(m_fire_sized)
folium.map.CustomPane('range_pane', z_index=395).add_to(m_fire_sized)
folium.map.CustomPane('fire_pane', z_index=650).add_to(m_fire_sized)

from folium.plugins import Fullscreen

Fullscreen(
    position='topleft',
    title='Full-screen',
    title_cancel='Exit full-screen',
    force_separate_button=True
).add_to(m_fire_sized)

orangutan_range_dissolved = orangutan_range.dissolve()
folium.GeoJson(
    orangutan_range_dissolved,
    style_function=lambda x: {
        'fillColor': '#006400',
        'color': '#006400',
        'weight': 0.2,
        'fillOpacity': 0.2
    },
    name='Bornean orangutan range',
    pane='range_pane'
).add_to(m_fire_sized)

folium.GeoJson(
    Indo_PAs_borneo,
    style_function=lambda x: {
        'fillColor': '#00509d',
        'color': '#00509d',
        'weight': 0.6,
        'fillOpacity': 0.1
    },
    name='Protected areas',
    pane='pa_pane'
).add_to(m_fire_sized)

today = fires_in_range['acq_date'].max()
today_dt = datetime.datetime.strptime(today, '%Y-%m-%d')

def recency_color(acq_date):
    days_ago = (today_dt - datetime.datetime.strptime(acq_date, '%Y-%m-%d')).days
    if days_ago == 0:
        return '#7f0000'
    elif days_ago <= 1:
        return '#c1121f'
    elif days_ago <= 2:
        return '#e5533c'
    else:
        return '#f4a582'

frp_max = fires_in_range['frp'].max()

def scale_radius_log(frp, min_r=2, max_r=10):
    log_frp = np.log1p(frp)
    log_max = np.log1p(frp_max)
    return min_r + (log_frp / log_max) * (max_r - min_r)

for row in fires_in_range.itertuples():
    popup_html = f"""
    <div style="font-family: Roboto, sans-serif; font-size: 12px;">
        <b>Fire Detection</b><br>
        <b>Date:</b> {row.acq_date}<br>
        <b>FRP:</b> {row.frp:.1f} MW<br>
        <b>Coordinates:</b> {row.latitude:.2f}, {row.longitude:.2f}
    </div>
    """
    folium.CircleMarker(
        [row.latitude, row.longitude],
        radius=scale_radius_log(row.frp),
        color=recency_color(row.acq_date),
        fill=True,
        fill_opacity=0.8,
        weight=0,
        popup=folium.Popup(popup_html, max_width=220),
        pane='fire_pane'
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

legend_frp_values = [3, 15, 100]  # MW

low_r = scale_radius_log(3)
mid_r = scale_radius_log(15)
high_r = scale_radius_log(100)

legend_js = f'''
<script>
window.addEventListener('load', function() {{
    var legend = L.control({{position: 'bottomleft'}});
    legend.onAdd = function (map) {{
        var div = L.DomUtil.create('div', 'info legend');
        div.style.background = 'white';
        div.style.padding = '10px 14px';
        div.style.borderRadius = '6px';
        div.style.fontFamily = 'Roboto';
        div.style.boxShadow = '0 1px 4px rgba(0,0,0,0.3)';
        div.innerHTML = `
            <div style="font-size: 12px; margin-bottom: 4px;"><b>Recency</b></div>
            <div style="width: 130px; height: 8px; border-radius: 4px; margin-bottom: 3px;
                 background: linear-gradient(to right, #7f0000, #c1121f, #e5533c, #f4a582);"></div>
            <div style="display: flex; justify-content: space-between; font-size: 9px; width: 130px; margin-bottom: 8px;">
                 <span>Today</span><span>5 days ago</span>
            </div>
            <div style="font-size: 12px; margin-bottom: 4px;"><b>Fire intensity (FRP, MW)</b></div>
            <div style="display: flex; align-items: center; gap: 8px;">
                 <div style="display: flex; align-items: center;">
                     <div style="width: {low_r*1.2}px; height: {low_r*1.2}px; border-radius: 50%; background-color: #c1121f;"></div>
                     <span style="font-size: 9px; margin-left: 3px;">3</span>
                 </div>
                 <div style="display: flex; align-items: center;">
                     <div style="width: {mid_r*1.2}px; height: {mid_r*1.2}px; border-radius: 50%; background-color: #c1121f;"></div>
                     <span style="font-size: 9px; margin-left: 3px;">15</span>
                 </div>
                 <div style="display: flex; align-items: center;">
                     <div style="width: {high_r*1.2}px; height: {high_r*1.2}px; border-radius: 50%; background-color: #c1121f;"></div>
                     <span style="font-size: 9px; margin-left: 3px;">100</span>
                 </div>
            </div>
        `;
        return div;
    }};
    legend.addTo({m_fire_sized.get_name()});
}});
</script>
'''
m_fire_sized.get_root().html.add_child(folium.Element(legend_js))


m_fire_sized.save('index.html')
print(f"Map updated: {len(fires_in_range)} fires in range, {datetime.datetime.now()}")