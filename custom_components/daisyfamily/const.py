"""Constants for the Daisy Family integration."""

from datetime import timedelta

DOMAIN = "daisyfamily"

DEFAULT_HOST = "janakkala.daisyfamily.fi"

UPDATE_INTERVAL = timedelta(minutes=15)

# Care time window that is polled: from N days back (at least the Monday of this week) to N days ahead.

# The JWT returned by the login endpoint is valid for 10 minutes. Log in again
# a little before that.
TOKEN_MAX_AGE_SECONDS = 8 * 60

# Profile pictures are re-fetched at most this often.
PICTURE_REFRESH_SECONDS = 60 * 60

# Daycare centre details (address, phones, opening hours) change rarely.
CENTRE_REFRESH_SECONDS = 24 * 60 * 60

# Holiday periods and public holidays change rarely: refresh a few times a day.
CALENDAR_REFRESH_SECONDS = 6 * 60 * 60
CALENDAR_DAYS_BACK = 60  # so that the real start of an ongoing holiday is included
CALENDAR_DAYS_AHEAD = 2 * 365

# Number of newest message threads exposed in the "All messages" sensor.
CONF_MAX_MESSAGES = "max_messages"
DEFAULT_MAX_MESSAGES = 10
MAX_MESSAGES_LIMIT = 100

# How many days ahead care times and absences are fetched.
CONF_CARE_DAYS = "care_days_ahead"
DEFAULT_CARE_DAYS = 77
MIN_CARE_DAYS = 7
MAX_CARE_DAYS = 365


# Number of newest bulletin board posts exposed in the "Bulletin board" sensor.
CONF_MAX_BULLETINS = "max_bulletins"
DEFAULT_MAX_BULLETINS = 20
MAX_BULLETINS_LIMIT = 100

# How many days back care times, actual times and absences are fetched.
CONF_CARE_DAYS_BACK = "care_days_back"
DEFAULT_CARE_DAYS_BACK = 14
MAX_CARE_DAYS_BACK = 365
