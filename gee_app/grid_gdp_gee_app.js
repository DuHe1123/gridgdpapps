// Grid-Level Local GDP Explorer for Google Earth Engine Apps.
// Paste this script into the Earth Engine Code Editor, update asset IDs if needed,
// then publish from the Apps panel.

var ASSETS = {
  '1 degree': {
    id: 'projects/ee-duheff14/assets/final_GDPC_1deg_postadjust_pop_dens_no_extra_adjust',
    keys: ['cell_id', 'iso'],
    cellSizeDeg: 1.0
  },
  '0.5 degree': {
    id: 'projects/ee-duheff14/assets/final_GDPC_0_5deg_postadjust_pop_dens_no_extra_adjust',
    keys: ['cell_id', 'subcell_id', 'iso'],
    cellSizeDeg: 0.5
  },
  '0.25 degree': {
    id: 'projects/ee-duheff14/assets/final_GDPC_0_25deg_postadjust_pop_dens_no_extra_adjust',
    keys: ['cell_id', 'subcell_id', 'subcell_id_0_25', 'iso'],
    cellSizeDeg: 0.25
  }
};

var VARIABLES = {
  'predicted_GCP_const_2021_PPP': 'Predicted cell GDP, constant 2021 PPP, billion',
  'predicted_GCP_const_2021_USD': 'Predicted cell GDP, constant 2021 USD, billion',
  'predicted_GCP_current_PPP': 'Predicted cell GDP, current PPP, billion',
  'predicted_GCP_current_USD': 'Predicted cell GDP, current USD, billion',
  'cell_GDPC_const_2021_PPP': 'Cell GDP per capita, constant 2021 PPP',
  'cell_GDPC_const_2021_USD': 'Cell GDP per capita, constant 2021 USD',
  'cell_GDPC_current_PPP': 'Cell GDP per capita, current PPP',
  'cell_GDPC_current_USD': 'Cell GDP per capita, current USD',
  'pop_cell': 'Cell population',
  'GCP_sd_log_gdp': 'Prediction uncertainty, SD of log GDP',
  'national_population': 'National population'
};

var YEARS = [
  2012, 2013, 2014, 2015, 2016, 2017,
  2018, 2019, 2020, 2021, 2022
];

var PALETTE = [
  '#ffffcc', '#ffeda0', '#fed976', '#feb24c',
  '#fd8d3c', '#f03b20', '#bd0026', '#800026'
];

var state = {
  resolution: '1 degree',
  variable: 'predicted_GCP_const_2021_PPP',
  year: 2022,
  countries: '',
  maxFeatures: 50000,
  useLog: true,
  activePointCollection: null,
  activeCollection: null,
  activeDisplay: null
};

Map.setOptions('HYBRID');
Map.setCenter(15, 15, 2);
Map.style().set('cursor', 'crosshair');

var controlPanel = ui.Panel({
  style: {
    width: '390px',
    padding: '12px',
    backgroundColor: 'rgba(255, 255, 255, 0.95)'
  }
});

var title = ui.Label('Grid-Level Local GDP Explorer', {
  fontSize: '22px',
  fontWeight: 'bold',
  margin: '0 0 4px 0'
});

var subtitle = ui.Label(
  'Rossi-Hansberg and Zhang grid GDP estimates. CSV points are expanded to resolution-sized grid cells.',
  {fontSize: '12px', color: '#4b5563', margin: '0 0 12px 0'}
);

var resolutionSelect = ui.Select({
  items: Object.keys(ASSETS),
  value: state.resolution,
  onChange: function(value) {
    state.resolution = value;
    refreshApp();
  },
  style: {stretch: 'horizontal'}
});

var yearSelect = ui.Select({
  items: YEARS.map(function(year) { return String(year); }),
  value: String(state.year),
  onChange: function(value) {
    state.year = Number(value);
    refreshApp();
  },
  style: {stretch: 'horizontal'}
});

var variableSelect = ui.Select({
  items: Object.keys(VARIABLES),
  value: state.variable,
  onChange: function(value) {
    state.variable = value;
    refreshApp();
  },
  style: {stretch: 'horizontal'}
});

var countryBox = ui.Textbox({
  placeholder: 'Optional ISO3 filter, e.g. USA,CHN,IND',
  value: '',
  onChange: function(value) {
    state.countries = value;
    refreshApp();
  },
  style: {stretch: 'horizontal'}
});

var maxFeatureSelect = ui.Select({
  items: ['10000', '25000', '50000', '100000', '250000'],
  value: String(state.maxFeatures),
  onChange: function(value) {
    state.maxFeatures = Number(value);
    refreshApp();
  },
  style: {stretch: 'horizontal'}
});

var logCheck = ui.Checkbox({
  label: 'Use log10 color scale',
  value: state.useLog,
  onChange: function(value) {
    state.useLog = value;
    refreshApp();
  }
});

var statusLabel = ui.Label('Loading...', {color: '#4b5563'});
var legendPanel = ui.Panel({style: {margin: '10px 0 0 0'}});
var summaryPanel = ui.Panel({style: {margin: '10px 0 0 0'}});
var inspectorPanel = ui.Panel({style: {margin: '10px 0 0 0'}});

function labeledControl(label, widget) {
  return ui.Panel([
    ui.Label(label, {fontWeight: 'bold', margin: '8px 0 3px 0'}),
    widget
  ]);
}

controlPanel.add(title);
controlPanel.add(subtitle);
controlPanel.add(labeledControl('Grid resolution', resolutionSelect));
controlPanel.add(labeledControl('Year', yearSelect));
controlPanel.add(labeledControl('Variable', variableSelect));
controlPanel.add(labeledControl('Country filter', countryBox));
controlPanel.add(labeledControl('Maximum displayed cells', maxFeatureSelect));
controlPanel.add(logCheck);
controlPanel.add(statusLabel);
controlPanel.add(legendPanel);
controlPanel.add(summaryPanel);
controlPanel.add(inspectorPanel);

ui.root.insert(0, controlPanel);

function parseCountryFilter(text) {
  if (!text) {
    return [];
  }
  return text.split(',')
    .map(function(item) { return item.trim().toUpperCase(); })
    .filter(function(item) { return item.length > 0; });
}

function assetCollection(resolution) {
  return ee.FeatureCollection(ASSETS[resolution].id);
}

function yearFilter(year) {
  return ee.Filter.or(
    ee.Filter.eq('year', year),
    ee.Filter.eq('year', String(year)),
    ee.Filter.eq('year', year + '.0')
  );
}

function numericProperty(feature, property) {
  return ee.Number.parse(feature.get(property));
}

function cellRectangle(feature) {
  var size = ee.Number(ASSETS[state.resolution].cellSizeDeg);
  var coords = ee.List(feature.geometry().coordinates());
  var lon = ee.Number(coords.get(0));
  var lat = ee.Number(coords.get(1));
  var rect = ee.Geometry.Rectangle(
    [lon, lat, lon.add(size), lat.add(size)],
    null,
    false
  );
  return feature
    .setGeometry(rect)
    .set('_cell_lon', lon)
    .set('_cell_lat', lat);
}

function validValueFilter(property) {
  return ee.Filter.and(
    ee.Filter.notNull([property]),
    ee.Filter.neq(property, 'NA'),
    ee.Filter.neq(property, ''),
    ee.Filter.neq(property, 'NaN'),
    ee.Filter.neq(property, 'null')
  );
}

function filteredCollection() {
  return filteredPointCollection().map(cellRectangle);
}

function filteredPointCollection() {
  var countries = parseCountryFilter(state.countries);
  var fc = assetCollection(state.resolution)
    .filter(yearFilter(state.year))
    .filter(validValueFilter(state.variable));

  if (countries.length > 0) {
    fc = fc.filter(ee.Filter.inList('iso', countries));
  }
  return fc;
}

function transformedValue(feature, variable, useLog) {
  var raw = numericProperty(feature, variable);
  return ee.Number(ee.Algorithms.If(useLog, raw.max(0).add(1).log10(), raw));
}

function makeBreaks(minValue, maxValue, bins) {
  var breaks = [];
  var span = maxValue - minValue;
  if (!isFinite(span) || span <= 0) {
    span = Math.max(Math.abs(maxValue), 1);
    minValue = maxValue - span * 0.5;
    maxValue = maxValue + span * 0.5;
  }
  for (var i = 0; i <= bins; i++) {
    breaks.push(minValue + span * i / bins);
  }
  return breaks;
}

function styleByBreaks(fc, breaks) {
  var variable = state.variable;
  var useLog = state.useLog;

  return fc.map(function(feature) {
    var value = transformedValue(feature, variable, useLog);
    var color = ee.String(PALETTE[0]);
    for (var i = 1; i < PALETTE.length; i++) {
      color = ee.String(ee.Algorithms.If(value.gte(breaks[i]), PALETTE[i], color));
    }
    var style = ee.Dictionary({
      color: '#2f2f2f',
      fillColor: color.cat('B8'),
      width: 0.4,
    });
    return feature.set('style', style);
  });
}

function displayValue(value) {
  if (value === null || value === undefined) {
    return 'NA';
  }
  value = Number(value);
  if (!isFinite(value)) {
    return 'NA';
  }
  if (Math.abs(value) >= 1000000) {
    return value.toExponential(2);
  }
  if (Math.abs(value) >= 1000) {
    return value.toLocaleString(undefined, {maximumFractionDigits: 0});
  }
  if (Math.abs(value) >= 1) {
    return value.toLocaleString(undefined, {maximumFractionDigits: 2});
  }
  return value.toPrecision(3);
}

function inverseLogValue(value) {
  return Math.pow(10, value) - 1;
}

function updateLegend(breaks) {
  legendPanel.clear();
  legendPanel.add(ui.Label('Color scale', {fontWeight: 'bold', margin: '0 0 4px 0'}));
  legendPanel.add(ui.Label(VARIABLES[state.variable], {fontSize: '11px', color: '#4b5563'}));

  for (var i = PALETTE.length - 1; i >= 0; i--) {
    var lower = breaks[i];
    var upper = breaks[i + 1];
    if (state.useLog) {
      lower = inverseLogValue(lower);
      upper = inverseLogValue(upper);
    }
    var swatch = ui.Label('', {
      backgroundColor: PALETTE[i],
      padding: '8px',
      margin: '0 6px 0 0'
    });
    var label = ui.Label(displayValue(lower) + ' - ' + displayValue(upper), {
      fontSize: '11px',
      margin: '0'
    });
    legendPanel.add(ui.Panel([swatch, label], ui.Panel.Layout.Flow('horizontal')));
  }
}

function updateSummary(fc) {
  summaryPanel.clear();
  summaryPanel.add(ui.Label('Summary', {fontWeight: 'bold'}));

  var numericFc = fc.map(function(feature) {
    return feature.set('_numeric_summary', numericProperty(feature, state.variable));
  });

  var reducer = ee.Reducer.count()
    .combine({reducer2: ee.Reducer.mean(), sharedInputs: true})
    .combine({reducer2: ee.Reducer.percentile([50]), sharedInputs: true})
    .combine({reducer2: ee.Reducer.minMax(), sharedInputs: true});

  numericFc.reduceColumns({
    reducer: reducer,
    selectors: ['_numeric_summary']
  }).evaluate(function(stats) {
    if (!stats) {
      summaryPanel.add(ui.Label('No summary available.'));
      return;
    }
    summaryPanel.add(ui.Label('Cells: ' + displayValue(stats.count)));
    summaryPanel.add(ui.Label('Mean: ' + displayValue(stats.mean)));
    summaryPanel.add(ui.Label('Median: ' + displayValue(stats.p50)));
    summaryPanel.add(ui.Label('Min: ' + displayValue(stats.min)));
    summaryPanel.add(ui.Label('Max: ' + displayValue(stats.max)));
  });
}

function renderMap() {
  statusLabel.setValue('Loading layer...');
  legendPanel.clear();
  summaryPanel.clear();
  inspectorPanel.clear();
  Map.layers().reset();

  var fc = filteredCollection();
  state.activePointCollection = filteredPointCollection();
  state.activeCollection = fc;
  state.activeDisplay = fc.limit(state.maxFeatures);

  fc.size().evaluate(function(total) {
    if (!total) {
      statusLabel.setValue(
        'No rows match this selection. Check the selected year, variable, and country filter.'
      );
    }
  });

  var transformed = state.activeDisplay.map(function(feature) {
    return feature.set('_color_value', transformedValue(feature, state.variable, state.useLog));
  });

  transformed.reduceColumns({
    reducer: ee.Reducer.percentile([2, 98]),
    selectors: ['_color_value']
  }).evaluate(function(stats) {
    if (!stats || stats.p2 === null || stats.p98 === null) {
      statusLabel.setValue('No data for this selection.');
      return;
    }

    var breaks = makeBreaks(stats.p2, stats.p98, PALETTE.length);
    var styled = styleByBreaks(state.activeDisplay, breaks).style({styleProperty: 'style'});
    Map.addLayer(styled, {}, state.resolution + ' ' + state.year + ' ' + state.variable);
    updateLegend(breaks);
    updateSummary(fc);

    fc.size().evaluate(function(total) {
      var shown = Math.min(total || 0, state.maxFeatures);
      statusLabel.setValue(
        'Showing ' + shown.toLocaleString() + ' of ' +
        (total || 0).toLocaleString() + ' cells. Click a grid cell to inspect it.'
      );
    });
  });
}

function selectedCellFilter(featureProps) {
  var cfg = ASSETS[state.resolution];
  var filters = cfg.keys.map(function(key) {
    return ee.Filter.eq(key, featureProps[key]);
  });
  return ee.Filter.and.apply(null, filters);
}

function renderTimeSeries(featureProps) {
  var fc = assetCollection(state.resolution)
    .filter(selectedCellFilter(featureProps))
    .filter(validValueFilter(state.variable))
    .sort('year')
    .map(function(feature) {
      return feature.set('_chart_value', numericProperty(feature, state.variable));
    });

  var chart = ui.Chart.feature.byFeature(fc, 'year', ['_chart_value'])
    .setChartType('LineChart')
    .setOptions({
      title: VARIABLES[state.variable],
      hAxis: {title: 'Year'},
      vAxis: {title: state.variable},
      lineWidth: 2,
      pointSize: 4,
      legend: {position: 'none'}
    });
  inspectorPanel.add(chart);
}

function inspectAtPoint(coords) {
  if (!state.activePointCollection) {
    return;
  }

  inspectorPanel.clear();
  inspectorPanel.add(ui.Label('Inspecting...', {fontWeight: 'bold'}));

  var point = ee.Geometry.Point([coords.lon, coords.lat]);
  var searchMeters = ASSETS[state.resolution].cellSizeDeg * 180000;
  var nearest = state.activePointCollection
    .filterBounds(point.buffer(searchMeters))
    .map(function(feature) {
      return feature.set('_distance_m', feature.geometry().distance(point));
    })
    .sort('_distance_m')
    .first();

  nearest.evaluate(function(feature) {
    inspectorPanel.clear();
    if (!feature || !feature.properties) {
      inspectorPanel.add(ui.Label('No nearby grid cell found near ' + coords.lon.toFixed(3) + ', ' + coords.lat.toFixed(3) + '.'));
      return;
    }

    var p = feature.properties;
    var origin = feature.geometry.coordinates;
    inspectorPanel.add(ui.Label('Selected cell', {fontWeight: 'bold'}));
    inspectorPanel.add(ui.Label('ISO: ' + p.iso));
    inspectorPanel.add(ui.Label('Year: ' + p.year));
    inspectorPanel.add(ui.Label('Cell ID: ' + p.cell_id));
    if (p.subcell_id !== undefined) {
      inspectorPanel.add(ui.Label('Subcell ID: ' + p.subcell_id));
    }
    if (p.subcell_id_0_25 !== undefined) {
      inspectorPanel.add(ui.Label('0.25 Subcell ID: ' + p.subcell_id_0_25));
    }
    inspectorPanel.add(ui.Label(VARIABLES[state.variable] + ': ' + displayValue(p[state.variable])));
    inspectorPanel.add(ui.Label('Population: ' + displayValue(p.pop_cell)));
    inspectorPanel.add(ui.Label('Cell origin longitude/latitude: ' + origin[0] + ', ' + origin[1]));
    renderTimeSeries(p);
  });
}

function refreshApp() {
  renderMap();
}

Map.onClick(inspectAtPoint);
refreshApp();
