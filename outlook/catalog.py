"""초기 연구 가설 목록. 자동으로 발견되거나 통계 검증된 AXIS가 아니다."""

CATALOG_VERSION = "us-gas-research-1"

METRICS = {
    "gas_production": ("Gas production", "Platts", "Bcf/d", "daily"),
    "gas_demand": ("Total gas demand", "Platts", "Bcf/d", "daily"),
    "lng_feedgas": ("LNG feedgas", "Platts", "Bcf/d", "daily"),
    "power_burn": ("Power sector gas demand", "Platts", "Bcf/d", "daily"),
    "res_comm": ("Residential & commercial demand", "Platts", "Bcf/d", "daily"),
    "industrial": ("Industrial gas demand", "Platts", "Bcf/d", "daily"),
    "gas_storage": ("Working gas storage", "EIA", "Bcf", "weekly"),
    "gas_rigs": ("Gas-directed rigs", "Baker Hughes", "rigs", "weekly"),
    "hdd_tx": ("Texas heating degree days", "NOAA", "HDD", "monthly"),
    "cdd_tx": ("Texas cooling degree days", "NOAA", "CDD", "monthly"),
    "eur_usd": ("Euro / US dollar", "ECB (Frankfurter)", "USD/EUR", "business_daily"),
}

AXES = [
    {
        "id": "supply", "number": "01", "title": "Supply responsiveness",
        "question": "Can domestic supply respond to a tighter gas balance?",
        "description": "Read production alongside drilling activity, then investigate productivity and the time needed for new supply.",
        "metrics": ["gas_production", "gas_rigs"],
        "path": ["Drilling & productivity", "Domestic production", "Available supply", "Storage & HH exposure"],
        "mechanism": "More drilling may support later production. Productivity, associated gas, decline rates and pipeline access can change or offset that response.",
        "missing": "The production series' dry/marketed definition still needs confirmation. Well completions, productivity, associated gas and pipeline constraints are not connected in this view.",
        "test": "Test whether rig changes add out-of-sample information about production after allowing for lags, productivity and changing regimes.",
    },
    {
        "id": "demand", "number": "02", "title": "Weather-sensitive demand",
        "question": "How much demand pressure comes from weather and power generation?",
        "description": "Separate heating and cooling exposure from underlying changes in electricity and gas consumption.",
        "metrics": ["power_burn", "res_comm", "hdd_tx", "cdd_tx"],
        "path": ["Heating / cooling needs", "Sector gas demand", "Net gas balance", "Storage & HH exposure"],
        "mechanism": "Weather can move heating and power demand. Fuel switching, renewable output and regional exposure also matter; a Texas weather series does not represent the whole US.",
        "missing": "Population- or demand-weighted US HDD/CDD, generation mix and weather forecasts are not connected in this view.",
        "test": "Evaluate HDD/CDD against seasonality-only demand baselines, with regional weights and holdout periods. Add other weather signals only if justified.",
    },
    {
        "id": "lng", "number": "03", "title": "LNG linkage",
        "question": "How strongly is overseas demand drawing on US gas?",
        "description": "Observe the domestic feedgas draw while keeping global capacity, outages and demand as separate uncertainties.",
        "metrics": ["lng_feedgas"],
        "path": ["Global demand & terminal availability", "US LNG feedgas", "Domestic gas balance", "Storage & HH exposure"],
        "mechanism": "Higher feedgas can tighten the domestic balance if other components do not offset it. Feedgas is an input to liquefaction, not a measure of delivered LNG exports.",
        "missing": "Global liquefaction schedules, terminal utilisation, destination demand and shipping constraints are not connected in this view.",
        "test": "Separate capacity additions from utilisation changes and outages; test their incremental contribution to domestic balances.",
    },
    {
        "id": "storage", "number": "04", "title": "Storage buffer",
        "question": "How much room does the market have to absorb a shock?",
        "description": "Treat inventories as a buffer and an outcome of the balance, with sensitivity that can vary by season.",
        "metrics": ["gas_storage", "gas_demand"],
        "path": ["Production minus total use", "Inventory change", "Seasonal storage buffer", "HH sensitivity"],
        "mechanism": "A smaller storage buffer may amplify price responses to a shock. Inventory levels alone do not establish scarcity or a causal price relationship.",
        "missing": "Regional deliverability, capacity-adjusted inventories and a verified multi-year seasonal reference are not connected in this view.",
        "test": "Test seasonal deviations and nonlinear responses rather than using the raw storage level as a universal price signal.",
    },
    {
        "id": "macro", "number": "05", "title": "Industrial & macro conditions",
        "question": "Are wider economic conditions changing gas demand?",
        "description": "Begin with industrial gas use and an exchange-rate observation, then establish the missing transmission channels.",
        "metrics": ["industrial", "eur_usd"],
        "path": ["Economic & financial conditions", "Industrial activity", "Industrial gas demand", "Domestic gas balance"],
        "mechanism": "Economic conditions may alter industrial consumption through several channels. EUR/USD is one currency pair, not a broad dollar index or evidence of a policy effect.",
        "missing": "Industrial output, broad dollar measures, rates and policy evidence are not connected in this view.",
        "test": "Test lagged demand responses with competing explanations. Correlation between a currency pair and demand is not sufficient for a causal link.",
    },
    {
        "id": "policy", "number": "06", "title": "Policy & project execution",
        "question": "Which decisions could change the structure of the market?",
        "description": "Keep policy and project uncertainties visible even when quantitative observations are not yet connected.",
        "metrics": [],
        "path": ["Policy / project decision", "Timing & operating constraints", "Future supply or demand", "Alternative market worlds"],
        "mechanism": "Permits, sanctions, investment decisions and construction delays may change available capacity. The direction and timing depend on the specific decision and its execution.",
        "missing": "Dated documents, project releases, event extraction and reviewed evidence links are not connected yet.",
        "test": "Reconstruct the documents available at each cutoff; assess whether the proposed axis was identifiable before the outcome became known.",
    },
]

AXIS_BY_ID = {axis["id"]: axis for axis in AXES}
