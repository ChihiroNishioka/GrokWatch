
from aiohttp import ClientConnectionError

from support import Device


BACKOFF = (1, 2, 4, 8, 16, 30)


async def reconnect(client, base, token, pause, scale=0.01):
    attempt = 0
    while True:
        try:
            ws = await client.ws_connect(base + "/v1/ws")
        except ClientConnectionError:
            await pause(BACKOFF[min(attempt, len(BACKOFF) - 1)] * scale)
            attempt += 1
            continue
        device = Device(ws)
        try:
            await device.hello(token)
            assert await device.receive() == {"type": "hello_ok", "v": 1}
        except BaseException:
            await ws.close()
            raise
        return device
