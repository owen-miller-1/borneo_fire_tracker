# Live fire detection monitoring tool in Borneo, Indonesia
![Python](https://img.shields.io/badge/PYTHON-3776AB?style=for-the-badge&logo=python&logoColor=white)
![GeoPandas](https://img.shields.io/badge/GEOPANDAS-139C5A?style=for-the-badge)
![Folium](https://img.shields.io/badge/FOLIUM-77B829?style=for-the-badge&logo=leaflet&logoColor=white)

##  🌏 [View the live map](https://owen-miller-1.github.io/borneo_fire_tracker/)

## Overview
This tool was developed in response to a request from Orangutan Foundation International Canada to monitor the ongoing fire situation in Borneo, Indonesia. It pulls near real-time fire detections from NASA's Fire Information for Resource Management System (FIRMS) to display a rolling 3-day window of fire activity in extant Bornean orangutan range. The tracker integrates satellite-derived fire observations with species range and protected areas to highlight the extent of fire activity in areas important to orangutan conservation.

## Data sources
- **Fire activity**: [NASA Fire Information for Resource Management](https://firms.modaps.eosdis.nasa.gov/map/#d:24hrs;@0.0,0.0,3.0z), VIIRS (Visible Infrared Imaging Radiometer Suite) NOAA-20 and NOAA-21
- **Bornean orangutan range**: [IUCN Red List of Threatened Species](https://www.iucnredlist.org/resources/spatial-data-download), spatial data (2024 release)
- **Protected Planet's World Database on Protected Areas (WDPA)**: [Protected Planet World Database on Protected Areas (WDPA)](https://www.protectedplanet.net/en/thematic-areas/wdpa), UNEP-WCMC and IUCN (2026 release) 
