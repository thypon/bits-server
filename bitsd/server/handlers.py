# -*- coding: utf-8 -*-
#
# Copyright (C) 2013 Stefano Sanfilippo
# Copyright (C) 2013 BITS development team
#
# This file is part of bitsd, which is released under the terms of
# GNU GPLv3. See COPYING at top level for more information.
#

"""
HTTP requests handlers.
"""

import markdown
import datetime
from sqlalchemy.exc import IntegrityError
from tornado.escape import xhtml_escape

import tornado.web
import tornado.websocket
import tornado.auth

from tornado.options import options

from sockjs.tornado import SockJSConnection

import bitsd.listener.notifier as notifier
from bitsd.persistence.engine import session_scope
from bitsd.persistence.models import Status

from .auth import verify
from .presence import PresenceForecaster
from .notifier import MessageNotifier

import bitsd.persistence.query as query

from bitsd.common import LOG


def cache(seconds):
    """
    Caching decorator for handlers. Will set `Expires` and `Cache-Control`
    headers appropriately.

    Example: to cache resource for 10 days, use::

        class FooHandler(BaseHandler):
            @cache(3600 * 24 * 10)
            def get(self):
                return render_something_great()

    Parameters:
        `seconds`: TTL of the cached resource, in seconds.
    """
    def set_cacheable(get_function):
        def wrapper(self, *args, **kwargs):
            self.set_header("Expires", datetime.datetime.utcnow() +
                datetime.timedelta(seconds=seconds))
            self.set_header("Cache-Control", "max-age=" + str(seconds))
            return get_function(self, *args, **kwargs)
        return wrapper
    return set_cacheable


def broadcast(message):
    """Broadcast given message to all clients. `message`
    may be either a string, which is directly broadcasted, or a dictionay
    that is JSON-serialized automagically before sending."""
    StatusConnection.CLIENTS.broadcast(message)


class BaseHandler(tornado.web.RequestHandler):
    """Base requests handler"""
    USER_COOKIE_NAME = "usertoken"

    def get_current_user(self):
        """Retrieve current user name from secure cookie."""
        return self.get_secure_cookie(
            self.USER_COOKIE_NAME,
            max_age_days=options.cookie_max_age_days
        )

    def get_login_url(self):
        return '/login'


class HomePageHandler(BaseHandler):
    """Display homepage."""
    @cache(86400*10)
    def get(self):
        self.render('templates/homepage.html')


class LogPageHandler(BaseHandler):
    """Handle historical data browser requests."""
    LINES_PER_PAGE = 20

    def get(self):
        """Display and paginate log."""
        wants_json = self.get_argument("format", "html") == "json"
        offset = self.get_integer_or_400("offset", 0)
        limit = self.get_integer_or_400("limit", self.LINES_PER_PAGE)

        with session_scope() as session:
            latest_statuses = query.get_latest_statuses(
                session,
                offset=offset,
                limit=limit
            )

            # Handle limit = 1 case (result is not a list)
            if type(latest_statuses) == Status:
                latest_statuses = [latest_statuses]

            if wants_json:
                self.write(self.jsonize(latest_statuses))
                self.finish()
            else:
                self.render('templates/log.html',
                    latest_statuses=latest_statuses,
                    # Used by the paginator
                    offset=offset,
                    limit=self.LINES_PER_PAGE,
                    count=query.get_number_of_statuses(session),
                )

    @staticmethod
    def jsonize(latest_statuses):
        """Turn an array of Status objects into a JSON-serializable dict"""
        data = [s.jsondict(wrap=False) for s in latest_statuses]
        return {"log": data}

    def get_integer_or_400(self, name, default):
        """Try to get the parameter by name (and default), then convert it to
        integer. In case of failure, raise a HTTP error 400"""
        try:
            return int(self.get_argument(name, default))
        except ValueError:
            raise tornado.web.HTTPError(400)


class StatusPageHandler(BaseHandler):
    """Get a single digit, indicating BITS status (open/closed)"""
    def get(self):
        with session_scope() as session:
            status = query.get_current_status(session)
            answer = '1' if status is not None and status.value == Status.OPEN else '0'
        self.write(answer)
        self.finish()


class MarkdownPageHandler(BaseHandler):
    """Renders page from markdown source."""
    @cache(86400*10)
    def get(self, slug):
        with session_scope() as session:
            page = query.get_page(session, slug)

            if page is None:
                raise tornado.web.HTTPError(404)

            self.render('templates/mdpage.html',
                body=markdown.markdown(
                    page.body,
                    safe_mode='escape' if options.mdescape else False,
                ),
                title=page.title,
            )

class StatusConnection(SockJSConnection):
    """Handler for POuL status via websocket"""

    CLIENTS = MessageNotifier('Status handler queue')

    def on_open(self, info):
        """Register new handler with MessageNotifier."""
        StatusConnection.CLIENTS.register(self)
        with session_scope() as session:
            latest = query.get_latest_data(session)
        self.send(latest)
        LOG.debug('Registered client')

    def on_message(self, message):
        """Disconnect clients sending data (they should not)."""
        LOG.warning('Client sent a message: disconnected.')

    def on_close(self):
        """Unregister this handler when the connection is closed."""
        StatusConnection.CLIENTS.unregister(self)
        LOG.debug('Unregistered client.')

class LoginPageHandler(BaseHandler):
    """Handle login browser requests for reserved area."""
    def get(self):
        next = self.get_argument("next", "/")
        if self.get_current_user():
            self.redirect(next)
        else:
            self.render(
                'templates/login.html',
                next=next,
                message=None
            )

    def post(self):
        username = self.get_argument("username", None)
        password = self.get_argument("password", None)
        next = self.get_argument("next", "/")

        with session_scope() as session:
            authenticated = verify(session, username, password)

        if authenticated:
            self.set_secure_cookie(
                self.USER_COOKIE_NAME,
                username,
                expires_days=options.cookie_max_age_days
            )
            LOG.info("Authenticating user `{}`".format(username))
            self.redirect(next)
        else:
            LOG.warning("Wrong authentication for user `{}`".format(username))
            self.render(
                'templates/login.html',
                next=next,
                message="Password/username sbagliati!"
            )


class LogoutPageHandler(BaseHandler):
    """Handle login browser requests for logout from reserved area."""

    def get(self):
        """Display the logout page."""
        self.clear_cookie("usertoken")
        self.redirect("/")


class AdminPageHandler(BaseHandler):
    """Handle browser requests for admin area."""

    @tornado.web.authenticated
    def get(self):
        """Display the admin page."""
        self.render('templates/admin.html',
                    page_message='Very secret information here')

    @tornado.web.authenticated
    def post(self):
        """Issue admin commands."""
        status = self.get_argument('changestatus', default=None)
        if status: self.change_status()

    def change_status(self):
        """Manually change the status of the BITS system"""

        with session_scope() as session:
            curstatus = query.get_current_status(session)

            if curstatus is None:
                textstatus = Status.CLOSED
            else:
                textstatus = Status.OPEN if curstatus.value == Status.CLOSED else Status.CLOSED

            LOG.info('Change of BITS to status={}'.format(textstatus) +
                     ' from web interface.')
            message = ''
            try:
                status = query.log_status(session, textstatus, 'web')
                broadcast(status.jsondict())
                notifier.send_status(textstatus)
                message = "Ora la sede è {}.".format(textstatus)
            except IntegrityError:
                LOG.error("Status changed too quickly, not logged.")
                message = "Errore: modifica troppo veloce!"
                raise
            finally:
                self.render('templates/admin.html', page_message=message)


class PresenceForecastHandler(BaseHandler):
    """Handler for presence stats.
    Upon GET, it will render JSON-encoded probabilities,
    as a 2D array (forecast for each weekday, at 30min granularity)."""
    FORECASTER = PresenceForecaster()

    @cache(86400)
    def get(self):
        data = self.FORECASTER.forecast()
        self.write({"forecast": data})
        self.finish()


class MessagePageHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render('templates/message.html', message=None, text='')

    @tornado.web.authenticated
    def post(self):
        text = self.get_argument('msgtext')
        username = self.get_current_user()

        text = xhtml_escape(text)

        LOG.info("{} sent message {!r} from web".format(username, text))

        with session_scope() as session:
            user = query.get_user(session, username)
            message = query.log_message(session, user, text)
            LOG.info("Broadcasting to clients")
            broadcast(message.jsondict())
            LOG.info("Notifying Fonera")
            notifier.send_message(text)

        self.render(
            'templates/message.html',
            message='Messaggio inviato correttamente!',
            text=text
        )


class RTCHandler(BaseHandler):
    def get(self):
        now = datetime.datetime.now()
        self.write(now.strftime("%Y-%m-%d %H:%M:%S"))
        self.finish()

