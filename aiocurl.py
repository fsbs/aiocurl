# aiocurl - asyncio extension of PycURL
# Copyright (C) 2021  fsbs
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
import asyncio as _asyncio

from pycurl import Curl as CurlSync, CurlMulti as CurlMultiSync
from pycurl import *


version = 'aiocurl/0.0.3 %s' % version
error.__module__ = 'aiocurl'


class Curl:
    def __init__(self):
        self._handle = CurlSync()
        self._multi = CurlMulti()

    def __getattr__(self, name):
        return getattr(self._handle, name)

    async def perform(self):
        """
        Asynchronously perform a transfer.

        Returns finished handle if the transfer succeeds.
        Returns None if the transfer was stopped by stop() or close().
        Raises aiocurl.error if the transfer fails with libcurl error.
        """
        return await self._multi.perform(self)

    def stop(self):
        """
        Stop the running transfer.

        The perform() coroutine will return None instead of the finished handle.
        """
        self._multi.stop(self)

    def cancel(self, handle: Curl):
        """
        Cancel the running transfer.

        The perform() coroutine will raise asyncio.CancelledError.
        """
        self._multi.cancel(self)

    def close(self):
        "Stop the transfer if running and close this curl handle."
        self._multi.close()
        self._handle.close()


class CurlMulti:
    def __init__(self):
        self._multi = CurlMultiSync()

        # Set a callback for registering or unregistering socket events.
        self._multi.setopt(M_SOCKETFUNCTION, self._socket_callback)

        # Set a callback for scheduling or cancelling timeout actions.
        self._multi.setopt(M_TIMERFUNCTION, self._timer_callback)

        # asyncio.TimerHandle: a reference to a scheduled timeout action.
        self._timer = None

        # aiocurl.Curl handles mapped to asyncio.Future objects.
        self._transfers = {}

        # pycurl.Curl handles mapped to aiocurl.Curl handles
        self._handles = {}

    def setopt(self, option, value):
        if option in (M_SOCKETFUNCTION, M_TIMERFUNCTION):
            raise error('callback option reserved for the event loop')
        self._multi.setopt(option, value)

    def _socket_callback(self, ev_bitmask, sock_fd, multi, data):
        "libcurl socket callback: add/remove actions for socket events."
        loop = _asyncio.get_running_loop()

        if ev_bitmask & POLL_IN:
            loop.add_reader(sock_fd, self._socket_action, sock_fd, CSELECT_IN)

        if ev_bitmask & POLL_OUT:
            loop.add_writer(sock_fd, self._socket_action, sock_fd, CSELECT_OUT)

        if ev_bitmask & POLL_REMOVE:
            loop.remove_reader(sock_fd)
            loop.remove_writer(sock_fd)

    def _timer_callback(self, timeout_ms):
        "libcurl timer callback: schedule/cancel a timeout action."
        if self._timer:
            self._timer.cancel()
        if timeout_ms == -1:
            self._timer = None
        else:
            loop = _asyncio.get_running_loop()
            self._timer = loop.call_later(timeout_ms / 1000, self._socket_action, SOCKET_TIMEOUT, 0)

    def _socket_action(self, sock_fd, ev_bitmask):
        "Event loop callback: act on ready sockets or timeouts."
        status, handle_count = self._multi.socket_action(sock_fd, ev_bitmask)

        # Check if any handles have finished.
        if handle_count != len(self._transfers):
            self._update_transfers()

    def _update_transfers(self):
        "Remove finished handles and set their futures."
        more_info, succ_handles, fail_handles = self._multi.info_read()

        for handle in succ_handles:
            self._remove_handle(self._handles[handle], result=handle)

        for handle, errno, errmsg in fail_handles:
            self._remove_handle(self._handles[handle], exception=error(errno, errmsg))

        if more_info:
            self._update_transfers()

    def _add_handle(self, handle: Curl):
        "Add a handle and return its future."
        # This will call our timer_callback to schedule a kick-start.
        self._multi.add_handle(handle._handle)
        self._handles[handle._handle] = handle

        # Create a future for this transfer.
        loop = _asyncio.get_running_loop()
        future = loop.create_future()
        self._transfers[handle] = future
        return future

    def _remove_handle(self, handle: Curl, result=None, exception=None, cancel=False):
        "Remove a handle and set its future."
        # This can call our socket_callback to unregister socket events.
        self._multi.remove_handle(handle._handle)
        self._handles.pop(handle._handle)

        # Set the future for this transfer.
        future = self._transfers.pop(handle)
        if cancel:
            future.cancel()
        elif exception:
            future.set_exception(exception)
        else:
            future.set_result(result)

    # Wraps transfer's future in a coroutine.
    async def perform(self, handle: Curl):
        """
        Asynchronously perform a transfer.

        Returns finished handle if the transfer succeeds.
        Returns None if the transfer was stopped by stop() or close().
        Raises aiocurl.error if the transfer fails with libcurl error.
        """
        return await self._add_handle(handle)

    # Counterpart of perform().
    def stop(self, handle: Curl):
        """
        Stop a running transfer.

        The corresponding perform() coroutine will return None instead of the finished handle.
        """
        # This will make perform() return immediately when yielded to.
        self._remove_handle(handle, result=None)

    def cancel(self, handle: Curl):
        """
        Cancel a running transfer.

        The corresponding perform() coroutine will raise asyncio.CancelledError.
        """
        self._remove_handle(handle, cancel=True)

    # Closing mid-transfer: considered wrong, but this cleans up the event loop.
    def close(self):
        "Stop any running transfers and close this multi handle."
        for handle in tuple(self._transfers):
            self.stop(handle)
        self._multi.close()
