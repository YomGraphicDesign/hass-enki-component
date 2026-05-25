"""Constants for Enki integration."""
from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

# This is the internal name of the integration, it should also match the directory
# name for the integration.
DOMAIN = "enki"
NAME = "Enki"

DEFAULT_SCAN_INTERVAL = 10

ENKI_OIDC_URL = "https://keycloak-prod.iot.leroymerlin.fr/realms/enki/protocol/openid-connect/token"
ENKI_URL = "https://enki.api.devportal.adeo.cloud"
ENKI_HOME_API_KEY = "Etsvnd8susfaAXTZsDmeX2s3o7dhNAT2"
ENKI_BFF_API_KEY = "hTFx7uzWpn2JRpeylsZRRK00hd7lxH3V"
ENKI_NODE_API_KEY = "aMmVpSOOWjEGz7f99caaPdUPMNoAIabj"
ENKI_REFERENTIEL_API_KEY = "MiodFO5my5FR5U1aWHfiGMgFSuL6eOmB"
ENKI_LIGHTS_API_KEY = "9UO9gla4t7rJqkYgJNS0PzGFIWh9t9B5"
ENKI_TEMP_HUMIDITY_API_KEY = "V6mMQHQAGNNVwjhuBXlVhQNYzZOxARJ3"
ENKI_PRESENCE_API_KEY = "bHEwVewJI2aNUiDX6KXt9ErzazfkarYp"
ENKI_BATTERY_API_KEY = "WcydJ76nQUo8AiwkV05kn3kiNyM31b3M"
ENKI_LUMINOSITY_API_KEY = "xQQKZE073KDNdtYkgRSC2cnm3dPQlel4"
ENKI_POWER_API_KEY = "HaFUU0N7dDj1jIgMnrMAEdTWgKCH3Fhs"
ENKI_AIRFLOW_API_KEY = "6ex5WlshxPnnNsqHGoyN5u6dCIIdbFYG"
