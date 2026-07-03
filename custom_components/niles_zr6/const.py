"""Constants for the Niles ZR-6 integration."""

DOMAIN = "niles_zr6"

CONF_NUM_ZONES = "num_zones"
CONF_ZONE_NAMES = "zone_names"
CONF_SOURCES = "sources"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_CONNECTION_MODE = "connection_mode"

MODE_SHARED = "shared"
MODE_EXCLUSIVE = "exclusive"
DEFAULT_CONNECTION_MODE = MODE_SHARED

DEFAULT_PORT = 23
DEFAULT_NUM_ZONES = 6
MAX_ZONES = 18
NUM_SOURCES = 6

DEFAULT_SCAN_INTERVAL = 30
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 600

SERVICE_ALL_ZONES_SOURCE = "all_zones_source"
SERVICE_ALL_ZONES_OFF = "all_zones_off"
SERVICE_TUNE = "tune"
SERVICE_SEND_COMMAND = "send_command"

ATTR_SOURCE = "source"
ATTR_FREQUENCY = "frequency"
ATTR_COMMAND = "command"
