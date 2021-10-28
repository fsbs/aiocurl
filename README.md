```python
handle = aiocurl.Curl()
handle.setopt(aiocurl.URL, 'https://example.com')

await handle.perform()
```


How?
----

Using libcurl's [socket interface](https://everything.curl.dev/libcurl/drive/multi-socket) to let asyncio's event loop do all the work of [waiting for I/O](https://curl.se/libcurl/c/CURLMOPT_SOCKETFUNCTION.html) and [scheduling of timeouts](https://curl.se/libcurl/c/CURLMOPT_TIMERFUNCTION.html).

> multi\_socket supports multiple parallel transfers — all done in the same single thread — and have been used to run several tens of thousands of transfers in a single application. It is usually the API that makes the most sense if you do a large number (>100 or so) of parallel transfers.
> 
> This setup allows clients to scale up the number of simultaneous transfers much higher than with other systems, and still maintain good performance. The "regular" APIs otherwise waste far too much time scanning through lists of all the sockets.


More examples?
--------------

### Awaiting multiple transfers ###

Use any of asyncio's functions:

```python
await asyncio.gather(
    handle1.perform(),
    handle2.perform(),
)
```

Even better:

```python
multi = aiocurl.CurlMulti()

await asyncio.gather(
    multi.perform(handle1),
    multi.perform(handle2),
)
```

Advantages of using a multi handle:

- connection reuse
- multiplexing
- shared SSL session and DNS cache


### Pausing and resuming a transfer ###

Simply use the existing pause method:

```python
handle.pause(aiocurl.PAUSE_ALL)
```

And to resume:

```python
handle.pause(aiocurl.PAUSE_CONT)
```

For more pause options see [libcurl's documention](https://curl.se/libcurl/c/curl_easy_pause.html).


### Stopping a tranfer ###

The opposite of perform:

```python
handle.stop()
```

And if the transfer is performed by a multi handle:

```python
multi.stop(handle)
```

A stopped perform will return `None` instead of the finished handle:

```python
if await handle.perform():
    print('finished')
else:
    print('stopped')
```


### Cancelling a transfer ###

This is just like stop(), except the corresponding perform() coroutine will be
cancelled instead:

```
try:
    await handle.perform()
except asyncio.CancelledError:
    print('cancelled')
```


Dependencies
------------

1. PycURL 7.43.0.4 or above. It has essential fixes that make event-driven transfers work. Older releases fail to relay libcurl's event messages.
2. *(optional)* Additional PycURL [event-related fixes](https://github.com/pycurl/pycurl/pull/708) that make pausing and resuming of transfers work.


License
-------

```
aiocurl - asyncio extension of PycURL
Copyright (C) 2021  fsbs

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
```
