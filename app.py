from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    import folium
    from branca.colormap import LinearColormap, linear
    from streamlit_folium import st_folium
except Exception:  # pragma: no cover - optional interactive map stack.
    folium = None
    LinearColormap = None
    linear = None
    st_folium = None

try:
    import expdpy as ex
except Exception:  # pragma: no cover - the app has pandas/plotly fallbacks.
    ex = None


APP_DIR = Path(__file__).resolve().parent
DATA_PATH = APP_DIR / "data" / "ADM0_ALL.csv"
GRID_DATA_DIR = APP_DIR / "data"

ENTITY_COL = "iso3"
ENTITY_NAME_COL = "country"
TIME_COL = "year"
WEIGHT_COL = "pop"

INEQUALITY_LABELS = {
    "GINIW_gdppc": "Population-weighted Gini",
    "GE_m1W_gdppc": "GE alpha -1",
    "GE_0W_gdppc": "GE alpha 0",
    "GE_1W_gdppc": "GE alpha 1",
    "GE_2W_gdppc": "GE alpha 2",
    "COVW_gdppc": "Coefficient of variation",
}

CORE_COLUMNS = [
    ENTITY_COL,
    ENTITY_NAME_COL,
    TIME_COL,
    "gdp_per_capita",
    "gdp_total",
    WEIGHT_COL,
    *INEQUALITY_LABELS.keys(),
]

DEFAULT_RELATION_COLUMNS = [
    "gdp_per_capita",
    "pop",
    "gdp_total",
    "SP_URB_TOTL_IN_ZS",
    "SP_DYN_LE00_IN",
    "SE_ADT_LITR_ZS",
    "IT_NET_USER_ZS",
    "NE_TRD_GNFS_ZS",
    "VA_EST",
    "RQ_EST",
]

GRID_CONFIG = {
    "1 degree": {
        "folder": "1deg_v2",
        "csv": "final_GDPC_1deg_postadjust_pop_dens_no_extra_adjust.csv",
        "cloud_csv": "cloud_data/grid_1deg_2012_2022.csv.gz",
        "shp": "shapefile/geom_1deg.shp",
        "keys": ["cell_id", "iso"],
        "shape_keys": {"cell_id": "cell_id", "iso": "iso"},
    },
    "0.5 degree": {
        "folder": "0_5deg_v2",
        "csv": "final_GDPC_0_5deg_postadjust_pop_dens_no_extra_adjust.csv",
        "cloud_csv": "cloud_data/grid_0_5deg_2012_2022.csv.gz",
        "shp": "shapefile/geom_0_5deg.shp",
        "keys": ["cell_id", "subcell_id", "iso"],
        "shape_keys": {"cell_id": "cell_id", "subcell_id": "subcell_id", "iso": "iso"},
    },
    "0.25 degree": {
        "folder": "0_25deg_v2",
        "csv": "final_GDPC_0_25deg_postadjust_pop_dens_no_extra_adjust.csv",
        "cloud_csv": "cloud_data/grid_0_25deg_2012_2022.csv.gz",
        "shp": "shapefile/geom_0_25deg.shp",
        "keys": ["cell_id", "subcell_id", "subcell_id_0_25", "iso"],
        "shape_keys": {
            "cell_id": "cell_id",
            "subcell_id": "sbcll_d",
            "subcell_id_0_25": "s__0_25",
            "iso": "iso",
        },
    },
}

GRID_VARIABLE_LABELS = {
    "predicted_GCP_const_2021_USD": "Predicted cell GDP, constant 2021 USD, billion",
    "predicted_GCP_current_USD": "Predicted cell GDP, current USD, billion",
    "predicted_GCP_const_2021_PPP": "Predicted cell GDP, constant 2021 PPP, billion",
    "predicted_GCP_current_PPP": "Predicted cell GDP, current PPP, billion",
    "pop_cell": "Cell population",
    "cell_GDPC_const_2021_USD": "Cell GDP per capita, constant 2021 USD",
    "cell_GDPC_current_USD": "Cell GDP per capita, current USD",
    "cell_GDPC_const_2021_PPP": "Cell GDP per capita, constant 2021 PPP",
    "cell_GDPC_current_PPP": "Cell GDP per capita, current PPP",
    "GCP_sd_log_gdp": "Prediction uncertainty, SD of log GDP",
    "is_cell_censored": "Cell censored flag",
    "national_population": "National population",
}

GRID_DEFAULT_VARIABLE = "predicted_GCP_const_2021_PPP"
GRID_BASE_COLUMNS = [
    "iso",
    "year",
    "longitude",
    "latitude",
    "pop_cell",
    "cell_size",
    "method",
    "is_cell_censored",
    "national_population",
]


@dataclass(frozen=True)
class AppState:
    df: pd.DataFrame
    metric: str
    years: tuple[int, int]
    countries: list[str]
    treat_zero_as_missing: bool


@dataclass(frozen=True)
class GridState:
    resolution: str
    variable: str
    year: int
    countries: list[str]
    map_rows: int
    polygon_limit: int
    use_log_color: bool
    use_polygons: bool


def page_config() -> None:
    st.set_page_config(
        page_title="Global Inequality Explorer",
        page_icon=":bar_chart:",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(
        """
        <style>
        .block-container {padding-top: 1.4rem; padding-bottom: 2.5rem;}
        [data-testid="stMetricValue"] {font-size: 1.35rem;}
        div[data-testid="stExpander"] div[role="button"] p {font-size: 0.95rem;}
        [data-testid="stTabs"] div[role="tablist"] {
            gap: 0.35rem;
            overflow-x: auto;
            overflow-y: hidden;
            padding-bottom: 0.35rem;
            scrollbar-width: thin;
        }
        [data-testid="stTabs"] button[role="tab"] {
            min-width: max-content;
            min-height: 2.85rem;
            padding: 0.65rem 1rem 0.75rem 1rem;
            border-radius: 7px 7px 0 0;
            color: inherit;
        }
        [data-testid="stTabs"] button[role="tab"] p {
            font-size: 0.98rem;
            line-height: 1.25;
            white-space: nowrap;
            margin: 0;
        }
        [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            background: rgba(62, 177, 194, 0.16);
        }
        .small-note {color: #5b6472; font-size: 0.92rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def load_data() -> pd.DataFrame:
    if is_lfs_pointer(DATA_PATH):
        st.error("`data/ADM0_ALL.csv` is a Git LFS pointer file, not the real CSV data.")
        st.info("Run `git lfs pull` locally, or make sure Streamlit Cloud can fetch Git LFS objects.")
        st.stop()
    df = pd.read_csv(DATA_PATH)
    for col in df.columns:
        if col not in {ENTITY_COL, ENTITY_NAME_COL}:
            df[col] = pd.to_numeric(df[col], errors="ignore")
    df[TIME_COL] = pd.to_numeric(df[TIME_COL], errors="coerce").astype("Int64")
    df = df.dropna(subset=[ENTITY_COL, ENTITY_NAME_COL, TIME_COL]).copy()
    df[TIME_COL] = df[TIME_COL].astype(int)

    numeric_cols = df.select_dtypes(include=np.number).columns
    df[numeric_cols] = df[numeric_cols].replace([np.inf, -np.inf], np.nan)

    if ex is not None and hasattr(ex, "set_panel"):
        try:
            df = ex.set_panel(df, entity=ENTITY_COL, time=TIME_COL)
        except Exception:
            pass
    return df


def grid_csv_path(resolution: str) -> Path:
    cfg = GRID_CONFIG[resolution]
    return GRID_DATA_DIR / cfg["folder"] / cfg["csv"]


def grid_cloud_csv_path(resolution: str) -> Path:
    cfg = GRID_CONFIG[resolution]
    return APP_DIR / cfg["cloud_csv"]


def active_grid_csv_path(resolution: str) -> Path:
    cloud_path = grid_cloud_csv_path(resolution)
    if is_real_data_file(cloud_path):
        return cloud_path
    return grid_csv_path(resolution)


def grid_shp_path(resolution: str) -> Path:
    cfg = GRID_CONFIG[resolution]
    return GRID_DATA_DIR / cfg["folder"] / cfg["shp"]


def is_lfs_pointer(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    try:
        with path.open("rb") as f:
            head = f.read(128)
    except OSError:
        return False
    return head.startswith(b"version https://git-lfs.github.com/spec/v1")


def is_real_data_file(path: Path) -> bool:
    return path.exists() and path.is_file() and not is_lfs_pointer(path)


def available_grid_resolutions() -> list[str]:
    return [name for name in GRID_CONFIG if is_real_data_file(active_grid_csv_path(name))]


def using_compact_grid_data(resolution: str) -> bool:
    return active_grid_csv_path(resolution) == grid_cloud_csv_path(resolution)


def grid_zip_paths() -> list[Path]:
    return sorted(GRID_DATA_DIR.glob("*deg_v2.zip"))


def render_missing_grid_data_message() -> None:
    st.title("Grid-Level Local GDP Explorer")
    st.error("Grid GDP CSV files were not found as real data files in this deployed app.")

    expected = pd.DataFrame(
        {
            "resolution": list(GRID_CONFIG.keys()),
            "expected_csv": [
                f"{cfg['cloud_csv']} or {str(Path('data') / cfg['folder'] / cfg['csv'])}"
                for cfg in GRID_CONFIG.values()
            ],
        }
    )
    st.dataframe(expected, use_container_width=True, hide_index=True)

    pointer_paths = [
        str(Path("data") / cfg["folder"] / cfg["csv"])
        for cfg in GRID_CONFIG.values()
        if is_lfs_pointer(GRID_DATA_DIR / cfg["folder"] / cfg["csv"])
    ]
    zips = grid_zip_paths()
    if pointer_paths:
        st.warning(
            "The expected grid CSV paths exist, but they are Git LFS pointer files rather than downloaded CSV data."
        )
        st.code("\n".join(pointer_paths))
        st.info("Run `git lfs pull` before deploying, or configure a data-hosting path that provides the real files.")
    elif zips:
        st.info(
            "I found zipped grid folders in `data/`, but the app reads the extracted CSV files. "
            "Extract the zip files before running locally, or use a data-hosting/Git LFS approach for Streamlit Cloud."
        )
    else:
        st.info(
            "For Streamlit Cloud, this usually means the large grid data files were not pushed or were skipped because "
            "GitHub has a 100 MB normal-file limit. Use Git LFS, release assets, or external object storage for these files."
        )


@st.cache_data(show_spinner=False)
def load_grid_header(resolution: str) -> list[str]:
    path = active_grid_csv_path(resolution)
    return pd.read_csv(path, nrows=0).columns.tolist()


def grid_numeric_variables(columns: list[str]) -> list[str]:
    skip = {"cell_id", "subcell_id", "subcell_id_0_25", "iso", "year", "longitude", "latitude"}
    text_cols = {"method", "cell_size"}
    variables = [col for col in columns if col not in skip and col not in text_cols]
    preferred = [col for col in GRID_VARIABLE_LABELS if col in variables]
    return preferred + [col for col in variables if col not in preferred]


def grid_variable_label(variable: str) -> str:
    return GRID_VARIABLE_LABELS.get(variable, variable)


def uncertainty_columns(variable: str, columns: list[str]) -> list[str]:
    q05 = f"{variable}_q05"
    q95 = f"{variable}_q95"
    tree_sd = f"{variable}_tree_sd"
    return [col for col in [q05, q95, tree_sd] if col in columns]


@st.cache_data(show_spinner="Loading grid data. Large resolutions can take a moment.")
def load_grid_data(resolution: str, variable: str) -> pd.DataFrame:
    path = active_grid_csv_path(resolution)
    cfg = GRID_CONFIG[resolution]
    columns = load_grid_header(resolution)
    usecols = []
    for col in [*cfg["keys"], *GRID_BASE_COLUMNS, variable, *uncertainty_columns(variable, columns)]:
        if col in columns and col not in usecols:
            usecols.append(col)

    df = pd.read_csv(path, usecols=usecols)
    for col in df.columns:
        if col not in {"iso", "method", "cell_size"}:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["year"] = df["year"].astype(int)
    for key in cfg["keys"]:
        if key in df.columns and key != "iso":
            df[key] = df[key].astype("Int64").astype(str)
    df["iso"] = df["iso"].astype(str)
    return df


def make_grid_key(row: pd.Series, keys: list[str]) -> str:
    return "|".join(str(row[key]) for key in keys)


def filtered_grid_data(df: pd.DataFrame, state: GridState) -> pd.DataFrame:
    out = df[df["year"].eq(state.year)].copy()
    if state.countries:
        out = out[out["iso"].isin(state.countries)].copy()
    out = out.dropna(subset=[state.variable, "longitude", "latitude"])
    if state.use_log_color:
        color_col = f"log10_{state.variable}"
        out[color_col] = np.log10(out[state.variable].where(out[state.variable] > 0))
    return out


def grid_color_column(state: GridState) -> str:
    return f"log10_{state.variable}" if state.use_log_color else state.variable


def downsample_for_map(df: pd.DataFrame, limit: int) -> pd.DataFrame:
    if len(df) <= limit:
        return df
    if "pop_cell" in df.columns and df["pop_cell"].notna().any():
        return df.nlargest(limit, "pop_cell")
    return df.sample(limit, random_state=42)


def render_plotly_grid_map(df: pd.DataFrame, state: GridState) -> None:
    color_col = grid_color_column(state)
    map_df = downsample_for_map(df, state.map_rows)
    fig = px.scatter_geo(
        map_df,
        lon="longitude",
        lat="latitude",
        color=color_col,
        size="pop_cell" if "pop_cell" in map_df.columns else None,
        hover_name="iso",
        hover_data={
            "year": True,
            state.variable: ":.4g",
            "pop_cell": ":,.0f" if "pop_cell" in map_df.columns else False,
            "longitude": ":.2f",
            "latitude": ":.2f",
        },
        color_continuous_scale="Viridis",
        labels={color_col: grid_variable_label(state.variable)},
    )
    fig.update_geos(showland=True, landcolor="#f4f1e8", showocean=True, oceancolor="#dbeafe")
    fig.update_layout(height=620, margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True)


def shapefile_feature_collection(resolution: str, df: pd.DataFrame, variable: str, limit: int) -> dict | None:
    try:
        import shapefile  # type: ignore
    except Exception:
        return None

    cfg = GRID_CONFIG[resolution]
    shp_path = grid_shp_path(resolution)
    if not shp_path.exists():
        return None

    selected = downsample_for_map(df, limit).copy()
    selected["grid_key"] = selected.apply(lambda row: make_grid_key(row, cfg["keys"]), axis=1)
    values = selected.set_index("grid_key")[[variable, "iso", "year", "pop_cell", "longitude", "latitude"]].to_dict("index")
    wanted = set(values)
    features = []

    reader = shapefile.Reader(str(shp_path))
    shape_key_fields = cfg["shape_keys"]
    for shape_record in reader.iterShapeRecords():
        attrs = shape_record.record.as_dict()
        try:
            key = "|".join(str(attrs[shape_key_fields[col]]).split(".")[0] for col in cfg["keys"])
        except KeyError:
            continue
        if key not in wanted:
            continue
        props = values[key].copy()
        props["grid_key"] = key
        features.append(
            {
                "type": "Feature",
                "id": key,
                "properties": props,
                "geometry": shape_record.shape.__geo_interface__,
            }
        )
        if len(features) >= limit:
            break
    return {"type": "FeatureCollection", "features": features}


def make_folium_colormap(vmin: float, vmax: float):
    for name in ("YlOrRd_09", "YlOrRd_04", "OrRd_09", "YlGnBu_09"):
        candidate = getattr(linear, name, None)
        if candidate is not None:
            return candidate.scale(vmin, vmax)
    return LinearColormap(
        colors=["#fff7bc", "#fec44f", "#f03b20", "#7f0000"],
        vmin=vmin,
        vmax=vmax,
    )


def grid_degree_size(resolution: str) -> float:
    if resolution == "1 degree":
        return 1.0
    if resolution == "0.5 degree":
        return 0.5
    return 0.25


def render_folium_grid_map(df: pd.DataFrame, state: GridState) -> None:
    if folium is None or st_folium is None or linear is None or LinearColormap is None:
        st.info("Interactive tile map packages are not installed yet, so a Plotly map is shown instead.")
        render_plotly_grid_map(df, state)
        return

    color_col = grid_color_column(state)
    map_df = downsample_for_map(df.dropna(subset=[color_col]), state.map_rows)
    if map_df.empty:
        st.warning("No mappable rows for the current filters.")
        return

    center = [float(map_df["latitude"].median()), float(map_df["longitude"].median())]
    m = folium.Map(location=center, zoom_start=2, tiles=None, control_scale=True)
    folium.TileLayer("CartoDB positron", name="Light").add_to(m)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
    folium.TileLayer("CartoDB dark_matter", name="Dark").add_to(m)

    vmin = float(map_df[color_col].quantile(0.02))
    vmax = float(map_df[color_col].quantile(0.98))
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin == vmax:
        vmin = float(map_df[color_col].min())
        vmax = float(map_df[color_col].max())
    cmap = make_folium_colormap(vmin, vmax)
    low_high = "Low to high"
    cmap.caption = f"{grid_variable_label(state.variable)} ({low_high})"

    if state.use_polygons:
        geojson = shapefile_feature_collection(state.resolution, map_df, color_col, state.polygon_limit)
        if geojson and geojson["features"]:
            folium.GeoJson(
                geojson,
                name="Grid polygons",
                style_function=lambda feature: {
                    "fillColor": cmap(feature["properties"][color_col]),
                    "color": "#4b5563",
                    "weight": 0.2,
                    "fillOpacity": 0.72,
                },
                tooltip=folium.GeoJsonTooltip(
                    fields=["iso", "year", color_col, "pop_cell"],
                    aliases=["ISO", "Year", grid_variable_label(state.variable), "Population"],
                    localize=True,
                    sticky=False,
                ),
            ).add_to(m)
        else:
            st.info("Polygon rendering needs the pyshp package and matching shapefile records. Showing point cells instead.")
            state = GridState(
                state.resolution,
                state.variable,
                state.year,
                state.countries,
                state.map_rows,
                state.polygon_limit,
                state.use_log_color,
                False,
            )

    if not state.use_polygons:
        cell_size = grid_degree_size(state.resolution)
        for row in map_df.itertuples(index=False):
            value = getattr(row, color_col)
            lon = float(getattr(row, "longitude"))
            lat = float(getattr(row, "latitude"))
            popup = (
                f"<b>{getattr(row, 'iso')}</b><br>"
                f"Year: {getattr(row, 'year')}<br>"
                f"{grid_variable_label(state.variable)}: {getattr(row, state.variable):,.4g}<br>"
                f"Population: {getattr(row, 'pop_cell', float('nan')):,.0f}"
            )
            folium.Rectangle(
                bounds=[[lat, lon], [lat + cell_size, lon + cell_size]],
                color="#1f2937",
                weight=0.25,
                fill=True,
                fill_color=cmap(value),
                fill_opacity=0.62,
                popup=folium.Popup(popup, max_width=280),
            ).add_to(m)

    cmap.add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)
    st_folium(m, use_container_width=True, height=650, returned_objects=[])


def metric_label(metric: str) -> str:
    return INEQUALITY_LABELS.get(metric, metric)


def available_columns(df: pd.DataFrame, candidates: Iterable[str]) -> list[str]:
    return [col for col in candidates if col in df.columns]


def numeric_options(df: pd.DataFrame) -> list[str]:
    keep = []
    for col in df.select_dtypes(include=np.number).columns:
        if col != TIME_COL and df[col].notna().sum() > 10:
            keep.append(col)
    return keep


def filtered_data(raw: pd.DataFrame, state: AppState) -> pd.DataFrame:
    df = raw.loc[
        raw[TIME_COL].between(state.years[0], state.years[1])
        & raw[ENTITY_NAME_COL].isin(state.countries)
    ].copy()
    if state.treat_zero_as_missing:
        cols = available_columns(df, INEQUALITY_LABELS.keys())
        df[cols] = df[cols].replace(0, np.nan)
    return df


def weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    ok = values.notna() & weights.notna() & (weights > 0)
    if not ok.any():
        return float("nan")
    return float(np.average(values[ok], weights=weights[ok]))


def add_download(df: pd.DataFrame, label: str, file_name: str) -> None:
    st.download_button(
        label,
        df.to_csv(index=False).encode("utf-8"),
        file_name=file_name,
        mime="text/csv",
        use_container_width=True,
    )


def safe_expdpy_figure(func_name: str, *args, **kwargs):
    if ex is None or not hasattr(ex, func_name):
        return None
    try:
        result = getattr(ex, func_name)(*args, **kwargs)
        return getattr(result, "fig", None)
    except Exception:
        return None


def sidebar(raw: pd.DataFrame) -> tuple[str, AppState]:
    st.sidebar.title("Inequality Explorer")
    st.sidebar.caption("ADM0 country-year panel")

    section = st.sidebar.radio(
        "Section",
        [
            "Overview",
            "Descriptive statistics",
            "Within and between",
            "Trends",
            "Relationships",
            "Dynamics",
        ],
    )

    st.sidebar.divider()
    metric = st.sidebar.selectbox(
        "Inequality measure",
        available_columns(raw, INEQUALITY_LABELS.keys()),
        format_func=metric_label,
    )

    min_year, max_year = int(raw[TIME_COL].min()), int(raw[TIME_COL].max())
    years = st.sidebar.slider("Year range", min_year, max_year, (min_year, max_year))

    countries_all = sorted(raw[ENTITY_NAME_COL].dropna().unique().tolist())
    default_countries = countries_all
    countries = st.sidebar.multiselect(
        "Countries",
        options=countries_all,
        default=default_countries,
        help="Clear this field to temporarily hide all countries, or select a subset for focused analysis.",
    )
    if not countries:
        countries = countries_all

    treat_zero = st.sidebar.checkbox(
        "Treat zero inequality values as missing",
        value=False,
        help="Some countries report zeros for all inequality measures in early years. Turn this on for sensitivity checks.",
    )

    st.sidebar.divider()
    st.sidebar.caption("Package status")
    if ex is None:
        st.sidebar.warning("expdpy is not loaded; pandas/plotly fallbacks are active.")
    else:
        st.sidebar.success("expdpy loaded")

    return section, AppState(raw, metric, years, countries, treat_zero)


def render_header(df: pd.DataFrame, state: AppState) -> None:
    st.title("Global Inequality Explorer")
    st.caption(
        "Country-year exploration of population-weighted inequality measures from ADM0_ALL.csv."
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rows", f"{len(df):,}")
    c2.metric("Countries", f"{df[ENTITY_COL].nunique():,}")
    c3.metric("Years", f"{df[TIME_COL].min()}-{df[TIME_COL].max()}")
    c4.metric("Measure", metric_label(state.metric))


def overview_page(df: pd.DataFrame, state: AppState) -> None:
    render_header(df, state)

    with st.expander("Preview analysis sample"):
        st.dataframe(df[available_columns(df, CORE_COLUMNS)].head(200), use_container_width=True)
        add_download(df, "Download filtered sample", "adm0_filtered_sample.csv")

    left, right = st.columns([1.1, 1])
    with left:
        st.subheader("Panel coverage")
        coverage = (
            df.groupby(TIME_COL, as_index=False)
            .agg(countries=(ENTITY_COL, "nunique"), observations=(ENTITY_COL, "size"))
            .sort_values(TIME_COL)
        )
        fig = px.area(
            coverage,
            x=TIME_COL,
            y="countries",
            markers=True,
            labels={"countries": "Countries with observations", TIME_COL: "Year"},
        )
        fig.update_layout(height=390, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.subheader("Current-year map")
        selected_year = st.select_slider(
            "Map year",
            options=sorted(df[TIME_COL].unique()),
            value=int(df[TIME_COL].max()),
        )
        map_df = df[df[TIME_COL] == selected_year].dropna(subset=[state.metric])
        fig = px.choropleth(
            map_df,
            locations=ENTITY_COL,
            color=state.metric,
            hover_name=ENTITY_NAME_COL,
            hover_data={state.metric: ":.4f", "gdp_per_capita": ":,.0f", WEIGHT_COL: ":,.0f"},
            color_continuous_scale="Viridis",
            labels={state.metric: metric_label(state.metric)},
        )
        fig.update_geos(showframe=False, showcoastlines=True, projection_type="natural earth")
        fig.update_layout(height=390, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Missingness and zeros")
    cols = available_columns(df, [*INEQUALITY_LABELS.keys(), "gdp_per_capita", WEIGHT_COL])
    quality = pd.DataFrame(
        {
            "variable": cols,
            "missing_pct": [df[col].isna().mean() * 100 for col in cols],
            "zero_pct": [(df[col] == 0).mean() * 100 for col in cols],
        }
    )
    fig = px.bar(
        quality.melt("variable", var_name="status", value_name="percent"),
        x="variable",
        y="percent",
        color="status",
        barmode="group",
        labels={"percent": "Percent of filtered rows", "variable": ""},
    )
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=20, b=10), xaxis_tickangle=-35)
    st.plotly_chart(fig, use_container_width=True)


def describe_page(df: pd.DataFrame, state: AppState) -> None:
    render_header(df, state)

    st.subheader("Distribution")
    fig = safe_expdpy_figure("explore_histogram", df, state.metric, kde=True)
    if fig is None:
        fig = px.histogram(
            df,
            x=state.metric,
            nbins=45,
            marginal="box",
            color_discrete_sequence=["#2f6f73"],
            labels={state.metric: metric_label(state.metric)},
        )
    fig.update_layout(height=430, margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig, use_container_width=True)

    stats = (
        df.groupby(TIME_COL)[state.metric]
        .agg(["count", "mean", "median", "std", "min", "max"])
        .reset_index()
    )
    stats["weighted_mean"] = [
        weighted_mean(g[state.metric], g[WEIGHT_COL]) for _, g in df.groupby(TIME_COL)
    ]

    left, right = st.columns([1.2, 1])
    with left:
        st.subheader("Descriptive table by year")
        st.dataframe(stats.round(4), use_container_width=True, hide_index=True)
    with right:
        st.subheader("Top and bottom countries")
        year = st.select_slider(
            "Ranking year",
            options=sorted(df[TIME_COL].unique()),
            value=int(df[TIME_COL].max()),
        )
        n = st.slider("Countries per side", 5, 25, 10)
        ranked = (
            df[df[TIME_COL] == year]
            .dropna(subset=[state.metric])
            .sort_values(state.metric)
        )
        extremes = pd.concat([ranked.head(n), ranked.tail(n)])
        fig = px.bar(
            extremes,
            x=state.metric,
            y=ENTITY_NAME_COL,
            color=np.where(extremes.index.isin(ranked.head(n).index), "Lowest", "Highest"),
            orientation="h",
            labels={state.metric: metric_label(state.metric), ENTITY_NAME_COL: ""},
        )
        fig.update_layout(height=520, margin=dict(l=10, r=10, t=20, b=10), yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)


def within_between_page(df: pd.DataFrame, state: AppState) -> None:
    render_header(df, state)
    st.subheader("Within-country and between-country variation")

    panel = df[[ENTITY_COL, ENTITY_NAME_COL, TIME_COL, state.metric]].dropna().copy()
    country_stats = (
        panel.groupby([ENTITY_COL, ENTITY_NAME_COL])[state.metric]
        .agg(country_mean="mean", within_sd="std", observations="count")
        .reset_index()
    )
    between_sd = float(country_stats["country_mean"].std())
    within_sd = float(country_stats["within_sd"].mean())
    total_sd = float(panel[state.metric].std())

    c1, c2, c3 = st.columns(3)
    c1.metric("Total standard deviation", f"{total_sd:.4f}")
    c2.metric("Between-country SD", f"{between_sd:.4f}")
    c3.metric("Average within-country SD", f"{within_sd:.4f}")

    left, right = st.columns([1, 1])
    with left:
        fig = px.bar(
            pd.DataFrame(
                {
                    "component": ["Between countries", "Within countries"],
                    "standard_deviation": [between_sd, within_sd],
                }
            ),
            x="component",
            y="standard_deviation",
            color="component",
            labels={"standard_deviation": "Standard deviation", "component": ""},
        )
        fig.update_layout(height=390, showlegend=False, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)

    with right:
        fig = px.scatter(
            country_stats,
            x="country_mean",
            y="within_sd",
            size="observations",
            hover_name=ENTITY_NAME_COL,
            labels={
                "country_mean": f"Country mean: {metric_label(state.metric)}",
                "within_sd": "Within-country SD",
            },
        )
        fig.update_layout(height=390, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Country-year heatmap")
    top_n = st.slider("Countries to display", 10, 80, 35)
    order = country_stats.sort_values("country_mean", ascending=False).head(top_n)
    heat = panel[panel[ENTITY_COL].isin(order[ENTITY_COL])].pivot_table(
        index=ENTITY_NAME_COL, columns=TIME_COL, values=state.metric, aggfunc="mean"
    )
    heat = heat.reindex(order[ENTITY_NAME_COL])
    fig = px.imshow(
        heat,
        aspect="auto",
        color_continuous_scale="Viridis",
        labels=dict(color=metric_label(state.metric), x="Year", y="Country"),
    )
    fig.update_layout(height=max(450, 18 * len(heat)), margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, use_container_width=True)


def trends_page(df: pd.DataFrame, state: AppState) -> None:
    render_header(df, state)

    yearly = (
        df.groupby(TIME_COL)
        .agg(
            mean=(state.metric, "mean"),
            median=(state.metric, "median"),
            p10=(state.metric, lambda x: x.quantile(0.10)),
            p90=(state.metric, lambda x: x.quantile(0.90)),
        )
        .reset_index()
    )
    yearly["population_weighted_mean"] = [
        weighted_mean(g[state.metric], g[WEIGHT_COL]) for _, g in df.groupby(TIME_COL)
    ]

    st.subheader("Global trend")
    fig = go.Figure()
    for col, name in [
        ("mean", "Mean"),
        ("median", "Median"),
        ("population_weighted_mean", "Population-weighted mean"),
    ]:
        fig.add_trace(go.Scatter(x=yearly[TIME_COL], y=yearly[col], mode="lines+markers", name=name))
    fig.add_trace(
        go.Scatter(
            x=pd.concat([yearly[TIME_COL], yearly[TIME_COL][::-1]]),
            y=pd.concat([yearly["p90"], yearly["p10"][::-1]]),
            fill="toself",
            fillcolor="rgba(47,111,115,0.16)",
            line=dict(color="rgba(255,255,255,0)"),
            hoverinfo="skip",
            name="P10-P90 band",
        )
    )
    fig.update_layout(
        height=440,
        yaxis_title=metric_label(state.metric),
        xaxis_title="Year",
        margin=dict(l=10, r=10, t=30, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Country trajectories")
    max_lines = st.slider("Maximum country lines", 5, 80, 25)
    country_order = (
        df.groupby(ENTITY_NAME_COL)[state.metric]
        .mean()
        .sort_values(ascending=False)
        .head(max_lines)
        .index
    )
    line_df = df[df[ENTITY_NAME_COL].isin(country_order)].sort_values([ENTITY_NAME_COL, TIME_COL])
    fig = px.line(
        line_df,
        x=TIME_COL,
        y=state.metric,
        color=ENTITY_NAME_COL,
        labels={state.metric: metric_label(state.metric), TIME_COL: "Year"},
    )
    fig.update_layout(height=560, margin=dict(l=10, r=10, t=20, b=10), legend_title="")
    st.plotly_chart(fig, use_container_width=True)


def relationships_page(df: pd.DataFrame, state: AppState) -> None:
    render_header(df, state)

    relation_candidates = available_columns(df, DEFAULT_RELATION_COLUMNS)
    all_numeric = numeric_options(df)
    x_var = st.selectbox(
        "Relationship variable",
        options=relation_candidates + [c for c in all_numeric if c not in relation_candidates],
        index=0,
    )

    plot_df = df.dropna(subset=[x_var, state.metric]).copy()
    if x_var in {"gdp_per_capita", "gdp_total", "pop"}:
        plot_df[f"log_{x_var}"] = np.log10(plot_df[x_var].where(plot_df[x_var] > 0))
        use_log = st.checkbox(f"Use log10({x_var})", value=True)
        x_plot = f"log_{x_var}" if use_log else x_var
    else:
        x_plot = x_var

    st.subheader("Bivariate relationship")
    fig = px.scatter(
        plot_df,
        x=x_plot,
        y=state.metric,
        color=TIME_COL,
        hover_name=ENTITY_NAME_COL,
        hover_data={TIME_COL: True, state.metric: ":.4f", x_var: ":.4f"},
        labels={state.metric: metric_label(state.metric), x_plot: x_plot},
    )

    smooth = plot_df[[x_plot, state.metric]].dropna().sort_values(x_plot)
    if len(smooth) >= 5 and smooth[x_plot].nunique() >= 3:
        degree = 2 if smooth[x_plot].nunique() > 10 else 1
        coef = np.polyfit(smooth[x_plot], smooth[state.metric], degree)
        xs = np.linspace(smooth[x_plot].min(), smooth[x_plot].max(), 120)
        ys = np.polyval(coef, xs)
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name="Polynomial fit", line=dict(color="#d1495b", width=3)))

    fig.update_layout(height=500, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Correlation matrix")
    corr_vars = available_columns(df, [*INEQUALITY_LABELS.keys(), *DEFAULT_RELATION_COLUMNS])
    corr = df[corr_vars].corr(numeric_only=True)
    fig = px.imshow(
        corr,
        text_auto=".2f",
        color_continuous_scale="RdBu",
        zmin=-1,
        zmax=1,
        labels=dict(color="Correlation"),
    )
    fig.update_layout(height=620, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, use_container_width=True)


def dynamics_page(df: pd.DataFrame, state: AppState) -> None:
    render_header(df, state)

    panel = df.sort_values([ENTITY_COL, TIME_COL]).copy()
    panel["lag_metric"] = panel.groupby(ENTITY_COL)[state.metric].shift(1)
    panel["delta_metric"] = panel[state.metric] - panel["lag_metric"]
    dyn = panel.dropna(subset=[state.metric, "lag_metric", "delta_metric"])

    st.subheader("Persistence")
    left, right = st.columns([1, 1])
    with left:
        fig = px.scatter(
            dyn,
            x="lag_metric",
            y=state.metric,
            color=TIME_COL,
            hover_name=ENTITY_NAME_COL,
            labels={
                "lag_metric": f"Lagged {metric_label(state.metric)}",
                state.metric: f"Current {metric_label(state.metric)}",
            },
        )
        max_val = np.nanmax([dyn["lag_metric"].max(), dyn[state.metric].max()])
        min_val = np.nanmin([dyn["lag_metric"].min(), dyn[state.metric].min()])
        fig.add_trace(go.Scatter(x=[min_val, max_val], y=[min_val, max_val], mode="lines", name="No change"))
        fig.update_layout(height=450, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)

    with right:
        fig = px.histogram(
            dyn,
            x="delta_metric",
            nbins=50,
            marginal="box",
            labels={"delta_metric": f"Annual change in {metric_label(state.metric)}"},
        )
        fig.add_vline(x=0, line_dash="dash", line_color="#30343f")
        fig.update_layout(height=450, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Largest changes")
    year = st.select_slider(
        "Change ending in year",
        options=sorted(dyn[TIME_COL].unique()),
        value=int(dyn[TIME_COL].max()),
    )
    n = st.slider("Rows", 5, 30, 15)
    changes = dyn[dyn[TIME_COL] == year].copy()
    changes["abs_change"] = changes["delta_metric"].abs()
    changes = changes.sort_values("abs_change", ascending=False).head(n)
    fig = px.bar(
        changes.sort_values("delta_metric"),
        x="delta_metric",
        y=ENTITY_NAME_COL,
        orientation="h",
        color="delta_metric",
        color_continuous_scale="RdBu",
        labels={"delta_metric": f"Change since previous year", ENTITY_NAME_COL: ""},
    )
    fig.update_layout(height=max(420, 24 * n), margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Dynamics data"):
        st.dataframe(
            dyn[[ENTITY_COL, ENTITY_NAME_COL, TIME_COL, "lag_metric", state.metric, "delta_metric"]].round(5),
            use_container_width=True,
            hide_index=True,
        )


def grid_sidebar() -> GridState:
    st.sidebar.title("Grid GDP Explorer")
    st.sidebar.caption("Rossi-Hansberg and Zhang local GDP grids")

    available_resolutions = available_grid_resolutions()
    if not available_resolutions:
        render_missing_grid_data_message()
        st.stop()

    resolution = st.sidebar.selectbox("Grid resolution", available_resolutions, index=0)
    if using_compact_grid_data(resolution):
        st.sidebar.info("Using compact cloud data: 2012 and 2022 only.")
    columns = load_grid_header(resolution)
    variables = grid_numeric_variables(columns)
    default_index = variables.index(GRID_DEFAULT_VARIABLE) if GRID_DEFAULT_VARIABLE in variables else 0
    variable = st.sidebar.selectbox("Variable", variables, index=default_index, format_func=grid_variable_label)

    preview = load_grid_data(resolution, variable)
    years = sorted(preview["year"].dropna().unique().tolist())
    year = st.sidebar.select_slider("Year", options=years, value=max(years))

    countries = sorted(preview["iso"].dropna().unique().tolist())
    selected_countries = st.sidebar.multiselect(
        "ISO countries",
        options=countries,
        default=[],
        help="Leave empty for all countries. Selecting a few countries makes high-resolution maps faster.",
    )

    st.sidebar.divider()
    use_log_color = st.sidebar.checkbox(
        "Log color scale",
        value=variable.startswith("predicted_GCP") or variable.startswith("cell_GDPC") or variable == "pop_cell",
    )
    use_polygons = st.sidebar.checkbox(
        "Use shapefile polygons",
        value=False,
        help="Best for irregular boundary cells. If unavailable, the app draws regular grid rectangles from longitude/latitude.",
    )
    map_rows = st.sidebar.slider("Map cells", 500, 20000, 6000, step=500)
    polygon_limit = st.sidebar.slider("Polygon map cells", 250, 8000, 2500, step=250)

    return GridState(
        resolution=resolution,
        variable=variable,
        year=int(year),
        countries=selected_countries,
        map_rows=int(map_rows),
        polygon_limit=int(polygon_limit),
        use_log_color=use_log_color,
        use_polygons=use_polygons,
    )


def grid_header(df: pd.DataFrame, state: GridState) -> None:
    st.title("Grid-Level Local GDP Explorer")
    st.caption(
        "Spatial and non-spatial exploration of local GDP grids at 1 degree, 0.5 degree, and 0.25 degree resolution."
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Resolution", state.resolution)
    c2.metric("Year", str(state.year))
    c3.metric("Cells shown", f"{len(df):,}")
    c4.metric("Countries", f"{df['iso'].nunique():,}")
    st.markdown(
        '<p class="small-note">Note: predicted_GCP variables are cell GDP in billions. cell_GDPC variables are GDP per capita.</p>',
        unsafe_allow_html=True,
    )
    if using_compact_grid_data(state.resolution):
        st.info("This public/cloud dataset is a compact two-year extract containing 2012 and 2022.")


def grid_overview_tab(df_all: pd.DataFrame, df_year: pd.DataFrame, state: GridState) -> None:
    grid_header(df_year, state)

    left, right = st.columns([1.2, 1])
    with left:
        st.subheader("Interactive map")
        render_folium_grid_map(df_year, state)
    with right:
        st.subheader("Selected variable")
        values = df_year[state.variable].dropna()
        c1, c2 = st.columns(2)
        c1.metric("Mean", f"{values.mean():,.4g}")
        c2.metric("Median", f"{values.median():,.4g}")
        c3, c4 = st.columns(2)
        c3.metric("P05", f"{values.quantile(0.05):,.4g}")
        c4.metric("P95", f"{values.quantile(0.95):,.4g}")

        st.subheader("Top cells")
        show_cols = [
            col for col in ["iso", "year", state.variable, "pop_cell", "longitude", "latitude", "method"] if col in df_year.columns
        ]
        st.dataframe(
            df_year.nlargest(25, state.variable)[show_cols],
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("Filtered grid sample"):
        show_cols = [
            col
            for col in [
                *GRID_CONFIG[state.resolution]["keys"],
                "year",
                state.variable,
                "pop_cell",
                "cell_size",
                "is_cell_censored",
                "longitude",
                "latitude",
            ]
            if col in df_year.columns
        ]
        st.dataframe(df_year[show_cols].head(1000), use_container_width=True, hide_index=True)


def grid_distribution_tab(df_year: pd.DataFrame, state: GridState) -> None:
    st.subheader("Describe variable")
    plot_df = df_year.dropna(subset=[state.variable]).copy()
    x_col = grid_color_column(state)
    stats = plot_df[state.variable].describe(percentiles=[0.05, 0.25, 0.5, 0.75, 0.95]).to_frame("value")
    stats.loc["missing"] = df_year[state.variable].isna().sum()
    stats.loc["zeros"] = (df_year[state.variable] == 0).sum()
    st.dataframe(stats.round(5), use_container_width=True)

    fig = px.histogram(
        plot_df,
        x=x_col,
        nbins=60,
        marginal="box",
        labels={x_col: grid_variable_label(state.variable)},
    )
    fig.update_layout(height=430, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, use_container_width=True)


def grid_by_group_tab(df_year: pd.DataFrame, state: GridState) -> None:
    st.subheader("Country aggregation")
    group_options = [col for col in ["iso", "method", "is_cell_censored", "cell_size"] if col in df_year.columns]
    group_col = st.selectbox("Group by", group_options, index=0)
    agg = (
        df_year.groupby(group_col, as_index=False)
        .agg(
            cells=(group_col, "size"),
            total_value=(state.variable, "sum"),
            mean_value=(state.variable, "mean"),
            median_value=(state.variable, "median"),
            population=("pop_cell", "sum"),
        )
        .sort_values("total_value", ascending=False)
    )
    left, right = st.columns([1, 1])
    with left:
        plot_agg = agg.head(40)
        fig = px.bar(
            plot_agg,
            x="total_value",
            y=group_col,
            orientation="h",
            labels={"total_value": f"Total {grid_variable_label(state.variable)}", group_col: ""},
        )
        fig.update_layout(height=620, margin=dict(l=10, r=10, t=20, b=10), yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.dataframe(agg.round(4), use_container_width=True, hide_index=True)


def grid_within_between_tab(df_all: pd.DataFrame, state: GridState) -> None:
    st.subheader("Within and between country variation")
    panel = df_all.dropna(subset=[state.variable]).copy()
    if panel.empty:
        st.warning("No data available for variation decomposition.")
        return

    country_stats = (
        panel.groupby("iso", as_index=False)
        .agg(country_mean=(state.variable, "mean"), within_sd=(state.variable, "std"), observations=("iso", "size"))
        .fillna({"within_sd": 0})
    )
    total_sd = float(panel[state.variable].std())
    between_sd = float(country_stats["country_mean"].std())
    within_sd = float(country_stats["within_sd"].mean())

    c1, c2, c3 = st.columns(3)
    c1.metric("Total SD", f"{total_sd:,.4g}")
    c2.metric("Between-country SD", f"{between_sd:,.4g}")
    c3.metric("Average within-country SD", f"{within_sd:,.4g}")

    left, right = st.columns([1, 1])
    with left:
        fig = px.bar(
            pd.DataFrame(
                {
                    "component": ["Between countries", "Within countries"],
                    "standard_deviation": [between_sd, within_sd],
                }
            ),
            x="component",
            y="standard_deviation",
            color="component",
            labels={"standard_deviation": "Standard deviation", "component": ""},
        )
        fig.update_layout(height=430, showlegend=False, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)
    with right:
        fig = px.scatter(
            country_stats,
            x="country_mean",
            y="within_sd",
            size="observations",
            hover_name="iso",
            labels={
                "country_mean": f"Country mean: {grid_variable_label(state.variable)}",
                "within_sd": "Within-country SD",
            },
        )
        fig.update_layout(height=430, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(country_stats.sort_values("country_mean", ascending=False).round(5), use_container_width=True, hide_index=True)


def grid_trends_tab(df_all: pd.DataFrame, state: GridState) -> None:
    st.subheader("Trends over time")
    trend = (
        df_all.groupby("year", as_index=False)
        .agg(
            total_value=(state.variable, "sum"),
            mean_value=(state.variable, "mean"),
            median_value=(state.variable, "median"),
            cells=("iso", "size"),
            population=("pop_cell", "sum"),
        )
        .sort_values("year")
    )
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=trend["year"], y=trend["total_value"], mode="lines+markers", name="Total"))
    fig.add_trace(go.Scatter(x=trend["year"], y=trend["mean_value"], mode="lines+markers", name="Mean"))
    fig.add_trace(go.Scatter(x=trend["year"], y=trend["median_value"], mode="lines+markers", name="Median"))
    fig.update_layout(
        height=460,
        xaxis_title="Year",
        yaxis_title=grid_variable_label(state.variable),
        margin=dict(l=10, r=10, t=20, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Country trends")
    country_trend = (
        df_all.groupby(["iso", "year"], as_index=False)
        .agg(total_value=(state.variable, "sum"), mean_value=(state.variable, "mean"))
        .sort_values(["iso", "year"])
    )
    top_countries = (
        country_trend[country_trend["year"].eq(state.year)]
        .sort_values("total_value", ascending=False)
        .head(20)["iso"]
        .tolist()
    )
    fig = px.line(
        country_trend[country_trend["iso"].isin(top_countries)],
        x="year",
        y="total_value",
        color="iso",
        markers=True,
        labels={"total_value": f"Country total: {grid_variable_label(state.variable)}"},
    )
    fig.update_layout(height=540, margin=dict(l=10, r=10, t=20, b=10), legend_title="")
    st.plotly_chart(fig, use_container_width=True)


def grid_regression_tab(df_year: pd.DataFrame, state: GridState) -> None:
    st.subheader("Regression overview")
    candidates = [
        col
        for col in ["pop_cell", "national_population", "GCP_sd_log_gdp", "longitude", "latitude", "is_cell_censored"]
        if col in df_year.columns and col != state.variable
    ]
    if not candidates:
        st.info("No numeric covariates are available for this selected variable.")
        return

    x_var = st.selectbox("Explanatory variable", candidates)
    use_log_x = st.checkbox("Use log10(x)", value=x_var in {"pop_cell", "national_population"})
    use_log_y = st.checkbox("Use log10(y)", value=state.use_log_color)
    reg = df_year[[x_var, state.variable, "iso"]].dropna().copy()
    reg = reg[(reg[x_var] > 0) if use_log_x else reg[x_var].notna()]
    reg = reg[(reg[state.variable] > 0) if use_log_y else reg[state.variable].notna()]
    if use_log_x:
        reg[f"log10_{x_var}"] = np.log10(reg[x_var])
        x_plot = f"log10_{x_var}"
    else:
        x_plot = x_var
    if use_log_y:
        reg[f"log10_{state.variable}"] = np.log10(reg[state.variable])
        y_plot = f"log10_{state.variable}"
    else:
        y_plot = state.variable

    reg = downsample_for_map(reg, 15000)
    if len(reg) < 3:
        st.warning("Not enough rows for a regression overview.")
        return

    x = reg[x_plot].to_numpy(dtype=float)
    y = reg[y_plot].to_numpy(dtype=float)
    X = np.column_stack([np.ones(len(x)), x])
    intercept, slope = np.linalg.lstsq(X, y, rcond=None)[0]
    y_hat = intercept + slope * x
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot else np.nan

    c1, c2, c3 = st.columns(3)
    c1.metric("Slope", f"{slope:,.4g}")
    c2.metric("Intercept", f"{intercept:,.4g}")
    c3.metric("R squared", f"{r2:,.3f}")

    fig = px.scatter(
        reg,
        x=x_plot,
        y=y_plot,
        color="iso",
        hover_name="iso",
        labels={x_plot: x_plot, y_plot: grid_variable_label(state.variable)},
    )
    xs = np.linspace(np.nanmin(x), np.nanmax(x), 100)
    fig.add_trace(go.Scatter(x=xs, y=intercept + slope * xs, mode="lines", name="OLS fit", line=dict(color="#7f0000", width=3)))
    fig.update_layout(height=560, margin=dict(l=10, r=10, t=20, b=10), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)


def grid_uncertainty_tab(df_year: pd.DataFrame, state: GridState) -> None:
    st.subheader("Prediction uncertainty and censoring")
    cols = df_year.columns.tolist()
    qcols = uncertainty_columns(state.variable, cols)

    if len(qcols) >= 2:
        q05, q95 = qcols[0], qcols[1]
        tmp = df_year.dropna(subset=[state.variable, q05, q95]).copy()
        tmp["interval_width"] = tmp[q95] - tmp[q05]
        fig = px.scatter(
            downsample_for_map(tmp, 12000),
            x=state.variable,
            y="interval_width",
            color="GCP_sd_log_gdp" if "GCP_sd_log_gdp" in tmp.columns else None,
            hover_name="iso",
            labels={
                state.variable: grid_variable_label(state.variable),
                "interval_width": "Q95 - Q05",
            },
        )
        fig.update_layout(height=460, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Quantile uncertainty columns are not available for this variable.")

    if "is_cell_censored" in df_year.columns:
        censored = (
            df_year.groupby("iso", as_index=False)
            .agg(censored_share=("is_cell_censored", "mean"), cells=("iso", "size"))
            .sort_values("censored_share", ascending=False)
        )
        fig = px.bar(
            censored.head(30),
            x="censored_share",
            y="iso",
            orientation="h",
            labels={"censored_share": "Share of cells censored", "iso": ""},
        )
        fig.update_layout(height=560, margin=dict(l=10, r=10, t=20, b=10), yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)


def grid_explorer_main() -> None:
    state = grid_sidebar()
    df_all = load_grid_data(state.resolution, state.variable)
    if state.countries:
        df_all = df_all[df_all["iso"].isin(state.countries)].copy()
    if state.use_log_color:
        color_col = grid_color_column(state)
        df_all[color_col] = np.log10(df_all[state.variable].where(df_all[state.variable] > 0))
    df_year = filtered_grid_data(df_all, state)

    if df_year.empty:
        st.warning("No rows match the current grid filters.")
        return

    tabs = st.tabs([
        "Map and overview",
        "Describe",
        "Within-between",
        "Trends",
        "By group",
        "Regression",
        "Uncertainty",
    ])
    with tabs[0]:
        grid_overview_tab(df_all, df_year, state)
    with tabs[1]:
        grid_distribution_tab(df_year, state)
    with tabs[2]:
        grid_within_between_tab(df_all, state)
    with tabs[3]:
        grid_trends_tab(df_all, state)
    with tabs[4]:
        grid_by_group_tab(df_year, state)
    with tabs[5]:
        grid_regression_tab(df_year, state)
    with tabs[6]:
        grid_uncertainty_tab(df_year, state)


def main() -> None:
    page_config()
    grid_explorer_main()


if __name__ == "__main__":
    main()
