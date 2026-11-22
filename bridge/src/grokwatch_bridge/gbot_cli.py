import asyncio
import shutil
from contextlib import suppress

from .contract import BridgeCancelled, BridgeUnavailable, Health, ReplyChunk


class GbotCli:
    name = "gbot_cli"

    def __init__(self, executable, args, agent_id, timeout=60):
        self.executable = executable
        self.args = args
        self.agent_id = agent_id
        self.timeout = timeout
        self._active = {}

    async def health(self):
        return Health(shutil.which(self.executable) is not None)

    async def cancel(self, session):
        if task := self._active.get(session):
            task.cancel()
            with suppress(asyncio.CancelledError, BridgeUnavailable):
                await task

    async def send_utterance(self, text, session):
        executable = shutil.which(self.executable)
        if executable is None:
            raise BridgeUnavailable()
        args = [arg.replace("{agent_id}", self.agent_id) for arg in self.args]
        task = asyncio.create_task(self._run(executable, args, text))
        self._active[session] = task
        try:
            reply = await task
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                raise
            raise BridgeCancelled() from None
        finally:
            self._active.pop(session, None)
        yield ReplyChunk(reply)

    async def _run(self, executable, args, text):
        launch = asyncio.create_task(asyncio.create_subprocess_exec(
            executable, *args, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        ))
        process = None
        try:
            async with asyncio.timeout(self.timeout):
                process = await asyncio.shield(launch)
                stdout, _ = await process.communicate(text.encode("utf-8"))
                if process.returncode:
                    raise BridgeUnavailable()
                return stdout.decode("utf-8").strip()
        except (OSError, TimeoutError, ValueError):
            raise BridgeUnavailable() from None
        finally:
            if process is None:
                with suppress(OSError, ValueError):
                    process = await launch
            if process is not None and process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
                await process.communicate()
