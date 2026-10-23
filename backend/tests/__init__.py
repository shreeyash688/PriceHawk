import config

# Tests never call the live exchange-rate service: the built-in rates make results predictable.
config.FX_LIVE_RATES = False
config.HOME_CURRENCY = "INR"
