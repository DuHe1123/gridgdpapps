# Grid GDP Explorer

Streamlit app for spatial and non-spatial exploration of grid-level local GDP estimates from Rossi-Hansberg and Zhang.

The app uses only the `no_extra_adjust` CSV for each resolution:

```text
data/1deg_v2/final_GDPC_1deg_postadjust_pop_dens_no_extra_adjust.csv
data/0_5deg_v2/final_GDPC_0_5deg_postadjust_pop_dens_no_extra_adjust.csv
data/0_25deg_v2/final_GDPC_0_25deg_postadjust_pop_dens_no_extra_adjust.csv
```

Shapefiles are optional. Without shapefiles, the map uses `longitude` and `latitude` point locations from the CSVs.

## Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deployment Notes

The raw CSVs are large, so this repository is configured to track `data/**` with Git LFS. After cloning, run:

```bash
git lfs pull
```

For Streamlit Community Cloud, make sure Git LFS objects are available to the deployed app. If startup is slow, create smaller cloud extracts by year/resolution.
