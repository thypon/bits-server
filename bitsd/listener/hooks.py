#
# Copyright (C) 2013 Stefano Sanfilippo
# Copyright (C) 2013 BITS development team
#
# This file is part of bitsd, which is released under the terms of
# GNU GPLv3. See COPYING at top level for more information.
#

"""
Hooks called by `.handlers` to handle specific commands.
"""

# NOTE: don't forget to register your handler in RemoteListener.ACTIONS
#     : and in __all__ below!!

import base64
from bitsd.listener import notifier

from bitsd.persistence.engine import session_scope
from bitsd.persistence.models import Status
import bitsd.persistence.query as query
from bitsd.common import LOG


#: This will be initialized by bitsd.listener.start()
broadcast = None


__all__ = [
    'handle_temperature_command',
    'handle_status_command',
    'handle_enter_command',
    'handle_leave_command',
    'handle_message_command',
    'handle_sound_command'
]


def handle_temperature_command(sensorid, value):
    """Receives and log data received from remote sensor."""
    LOG.info('Received temperature: sensorid={}, value={}'.format(sensorid, value))
    try:
        sensorid = int(sensorid)
        value = float(value)
    except ValueError:
        LOG.error('Wrong type for parameters in temperature command!')
        return

    with session_scope() as session:
        temp = query.log_temperature(session, value, sensorid, 'BITS')
        broadcast(temp.jsondict())


def handle_status_command(status):
    """Update status.
    Will reject two identical and consecutive updates
    (prevents opening when already open and vice-versa)."""
    LOG.info('Received status: {}'.format(status))
    try:
        status = int(status)
    except ValueError:
        LOG.error('Wrong type for parameters in temperature command')
        return
    if status not in (0, 1):
        LOG.error('Non existent status {}, ignoring.'.format(status))
        return

    textstatus = Status.OPEN if status == 1 else Status.CLOSED
    with session_scope() as session:
        curstatus = query.get_current_status(session)
        if curstatus is None or curstatus.value != textstatus:
            status = query.log_status(session, textstatus, 'BITS')
            broadcast(status.jsondict())
            notifier.send_status(textstatus)
        else:
            LOG.error('BITS already open/closed! Ignoring.')


def handle_enter_command(userid):
    """Handles signal triggered when a new user enters."""
    LOG.info('Received enter command: id={}'.format(userid))
    try:
        userid = int(userid)
    except ValueError:
        LOG.error('Wrong type for parameters in temperature command!')
        return

    LOG.error('handle_enter_command not implemented.')


def handle_leave_command(userid):
    """Handles signal triggered when a known user leaves."""
    LOG.info('Received leave command: id={}'.format(userid))
    try:
        userid = int(userid)
    except ValueError:
        LOG.error('Wrong type for parameters in temperature command!')
        return

    LOG.error('handle_leave_command not implemented.')


def handle_message_command(message):
    """Handles message broadcast requests."""
    LOG.info('Received message command: message={!r}'.format(message))
    try:
        decodedmex = base64.b64decode(message)
    except TypeError:
        LOG.error('Received message is not valid base64: {!r}'.format(message))
    else:
        text = decodedmex.decode('utf8')
        #FIXME maybe get author ID from message?
        user = "BITS"
        with session_scope() as session:
            user = query.get_user(session, user)
            if not user:
                LOG.error("Non-existent user {}, not logging message.".format(user))
                return
            message = query.log_message(session, user, text)
            broadcast(message.jsondict())
        notifier.send_message(text)


def handle_sound_command(soundid):
    """Handles requests to play a sound."""
    LOG.info('Received sound command: id={}'.format(soundid))
    try:
        soundid = int(soundid)
    except ValueError:
        LOG.error('Wrong type for parameters in temperature command!')
        return
    else:
        notifier.send_sound(soundid)
