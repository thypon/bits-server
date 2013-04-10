#
# Copyright (C) 2013 Stefano Sanfilippo
# Copyright (C) 2013 BITS development team
#
# This file is part of bitsd, which is released under the terms of
# GNU GPLv3. See COPYING at top level for more information.
#

"""
Persists data from sensors to DB and offers an abstraction level over
DBMS internals.
"""

from tornado.options import options

from .. import persist, query_by_timestamp
from .model import TemperatureSample, Status


def log_temperature(value, sensor, modified_by):
    """Add a temperature sample to the DB."""
    persist(TemperatureSample(value, sensor, modified_by))

def log_status(status, modified_by):
    """Persist status to the DB."""
    persist(Status(status, modified_by))

def get_current_status():
    return query_by_timestamp(Status, limit=1)

def get_current_temperature():
    return query_by_timestamp(TemperatureSample, limit=1)

def get_latest_temperature_samples():
    """Query 100 TemperatureSample by timestamp."""
    return query_by_timestamp(TemperatureSample, limit=100)

def get_latest_statuses():
    """Query last 20 Status by timestamp.""" #TODO
    return query_by_timestamp(Status, limit=20)


def get_latest_data():
    """Get recent data."""
    status = get_current_status()
    temp = get_current_temperature()
    latest_temp_samples = get_latest_temperature_samples()
    return {
        "status": status.jsondict(),
        "tempint": temp.jsondict(),
        "version": options.jsonver,
        #"msg": TODO,
        "tempinthist": [sample.jsondict() for sample in latest_temp_samples]
    }