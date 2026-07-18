# Google Earth Engine App

This folder contains the Earth Engine JavaScript version of the grid GDP explorer.

## Current Asset IDs

The script assumes these Earth Engine table assets:

```text
projects/ee-duheff14/assets/final_GDPC_1deg_postadjust_pop_dens_no_extra_adjust
projects/ee-duheff14/assets/final_GDPC_0_5deg_postadjust_pop_dens_no_extra_adjust
projects/ee-duheff14/assets/final_GDPC_0_25deg_postadjust_pop_dens_no_extra_adjust
```

The 1-degree asset is already set to the asset ID you provided. The 0.5-degree and
0.25-degree IDs are inferred from the same naming pattern. Update the `ASSETS`
object in `grid_gdp_gee_app.js` if Earth Engine gives them different IDs.

## Important

This version uses the `longitude` and `latitude` columns from the CSV files and
renders each grid cell as a point centroid. It does not require uploading the
shapefiles. A later polygon version can be made if you want true square grid cells
in Earth Engine.

## How To Use

1. Open the Earth Engine Code Editor.
2. Create a new script.
3. Paste the contents of `grid_gdp_gee_app.js`.
4. Click **Run**.
5. If the 0.5-degree or 0.25-degree uploads are still processing, test with
   `1 degree` first.
6. When it works, open **Apps** in the Code Editor and create a new app.
7. Make the app public only after the assets are shared publicly or with the app.

## Publishing Notes

For public apps, Earth Engine assets used by the app must be readable by the app.
If users see missing layers after publishing, check asset sharing first.

For very large layers, keep the displayed feature cap modest. The app can still
compute summary statistics over the filtered collection, but rendering too many
0.25-degree points at once can be slow.
