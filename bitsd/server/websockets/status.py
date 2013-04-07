#
# Copyright (C) 2013 Stefano Sanfilippo
# Copyright (C) 2013 BITS development team
#
# This file is part of bitsd, which is released under the terms of
# GNU GPLv3. See COPYING at top level for more information.
#

import tornado.websocket

from .notifier import MessageNotifier

from bitsd.common import LOG

class StatusHandler(tornado.websocket.WebSocketHandler):
    """Handler for POuL status via websocket"""

    QUEUE = MessageNotifier('Status handler queue')

    def open(self):
        """Register new handler with MessageNotifier."""
        StatusHandler.QUEUE.register(self)

    def on_message(self, message):
        """Disconnect clients sending data (they should not)."""
        LOG.warning('Client dared to send a message: disconnected.')

    def on_close(self):
        """Unregister this handler when the connection is closed."""
        StatusHandler.QUEUE.unregister(self)


def broadcast(message):
    """Send a message to all connected clients."""
    StatusHandler.QUEUE.broadcast(message)