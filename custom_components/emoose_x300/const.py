"""Constants for the emoose X300 integration."""

DOMAIN = "emoose_x300"

CONF_TOPIC_PREFIX = "topic_prefix"

# The topic the station itself uses is "$oc/devices/<device id>/...". The default matches
# the unit this integration was developed on; change it to your own device id, or to the
# prefix you mapped it to if you bridge the traffic into a local broker.
DEFAULT_TOPIC_PREFIX = "$oc/devices/3768"

REPORT_SUFFIX = "report/request"
COMMAND_SUFFIX = "command/request"

# The station reports roughly every 6 seconds; treat it as offline after this long.
AVAILABILITY_TIMEOUT = 30
