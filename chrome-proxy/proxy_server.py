"""
Chrome DevTools MCP Proxy Server

对外暴露与 chrome-devtools-mcp 相同的工具集，但每个工具多一个 session_id 参数。
每个 session_id 对应一个独立的 chrome-devtools-mcp 子进程和 Chrome 实例。

用法（在 .mcp.json 里）：
  "chrome-devtools": {
    "command": "uv",
    "args": ["run", "--project", ".../chrome-proxy", "python", "proxy_server.py"]
  }
"""

import asyncio
import json
import logging
import os
import sys
import time
from typing import Any

logger = logging.getLogger(__name__)

# 每个工具的原始参数列表（从 chrome-devtools-mcp 直接获取）
TOOL_PARAMS: dict[str, dict] = {
    "click": {
        "type": "object",
        "properties": {
            "uid": {"type": "string", "description": "Element uid from snapshot"},
            "dblClick": {"type": "boolean"},
            "includeSnapshot": {"type": "boolean"},
        },
        "required": ["uid"],
    },
    "close_page": {
        "type": "object",
        "properties": {
            "pageId": {"type": "string"},
        },
    },
    "drag": {
        "type": "object",
        "properties": {
            "from_uid": {"type": "string"},
            "to_uid": {"type": "string"},
            "includeSnapshot": {"type": "boolean"},
        },
        "required": ["from_uid", "to_uid"],
    },
    "emulate": {
        "type": "object",
        "properties": {
            "networkConditions": {"type": "string"},
            "cpuThrottlingRate": {"type": "number"},
            "geolocation": {"type": "object"},
            "userAgent": {"type": "string"},
            "colorScheme": {"type": "string"},
            "viewport": {"type": "object"},
        },
    },
    "evaluate_script": {
        "type": "object",
        "properties": {
            "function": {"type": "string"},
            "args": {"type": "array", "items": {"type": "string"}},
            "filePath": {"type": "string"},
            "dialogAction": {"type": "string"},
        },
        "required": ["function"],
    },
    "fill": {
        "type": "object",
        "properties": {
            "uid": {"type": "string"},
            "value": {"type": "string"},
            "includeSnapshot": {"type": "boolean"},
        },
        "required": ["uid", "value"],
    },
    "fill_form": {
        "type": "object",
        "properties": {
            "elements": {"type": "array"},
            "includeSnapshot": {"type": "boolean"},
        },
        "required": ["elements"],
    },
    "get_console_message": {
        "type": "object",
        "properties": {"msgid": {"type": "string"}},
        "required": ["msgid"],
    },
    "get_network_request": {
        "type": "object",
        "properties": {
            "reqid": {"type": "string"},
            "requestFilePath": {"type": "string"},
            "responseFilePath": {"type": "string"},
        },
        "required": ["reqid"],
    },
    "handle_dialog": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["accept", "dismiss"]},
            "promptText": {"type": "string"},
        },
        "required": ["action"],
    },
    "hover": {
        "type": "object",
        "properties": {
            "uid": {"type": "string"},
            "includeSnapshot": {"type": "boolean"},
        },
        "required": ["uid"],
    },
    "lighthouse_audit": {
        "type": "object",
        "properties": {
            "mode": {"type": "string"},
            "device": {"type": "string"},
            "outputDirPath": {"type": "string"},
        },
    },
    "list_console_messages": {
        "type": "object",
        "properties": {
            "pageSize": {"type": "integer"},
            "pageIdx": {"type": "integer"},
            "types": {"type": "array"},
            "includePreservedMessages": {"type": "boolean"},
        },
    },
    "list_network_requests": {
        "type": "object",
        "properties": {
            "pageSize": {"type": "integer"},
            "pageIdx": {"type": "integer"},
            "resourceTypes": {"type": "array"},
            "includePreservedRequests": {"type": "boolean"},
        },
    },
    "list_pages": {"type": "object", "properties": {}},
    "navigate_page": {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["url", "back", "forward", "reload"]},
            "url": {"type": "string"},
            "ignoreCache": {"type": "boolean"},
            "handleBeforeUnload": {"type": "boolean"},
            "initScript": {"type": "string"},
            "timeout": {"type": "number"},
        },
    },
    "new_page": {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "background": {"type": "boolean"},
            "isolatedContext": {"type": "string"},
            "timeout": {"type": "number"},
        },
        "required": ["url"],
    },
    "performance_analyze_insight": {
        "type": "object",
        "properties": {
            "insightSetId": {"type": "string"},
            "insightName": {"type": "string"},
        },
        "required": ["insightSetId", "insightName"],
    },
    "performance_start_trace": {
        "type": "object",
        "properties": {
            "reload": {"type": "boolean"},
            "autoStop": {"type": "boolean"},
            "filePath": {"type": "string"},
        },
    },
    "performance_stop_trace": {
        "type": "object",
        "properties": {"filePath": {"type": "string"}},
    },
    "press_key": {
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "includeSnapshot": {"type": "boolean"},
        },
        "required": ["key"],
    },
    "resize_page": {
        "type": "object",
        "properties": {
            "width": {"type": "integer"},
            "height": {"type": "integer"},
        },
        "required": ["width", "height"],
    },
    "select_page": {
        "type": "object",
        "properties": {
            "pageId": {"type": "string"},
            "bringToFront": {"type": "boolean"},
        },
        "required": ["pageId"],
    },
    "take_memory_snapshot": {
        "type": "object",
        "properties": {"filePath": {"type": "string"}},
    },
    "take_screenshot": {
        "type": "object",
        "properties": {
            "format": {"type": "string", "enum": ["png", "jpeg", "webp"]},
            "quality": {"type": "number"},
            "uid": {"type": "string"},
            "fullPage": {"type": "boolean"},
            "filePath": {"type": "string"},
        },
    },
    "take_snapshot": {
        "type": "object",
        "properties": {
            "verbose": {"type": "boolean"},
            "filePath": {"type": "string"},
        },
    },
    "type_text": {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "submitKey": {"type": "string"},
        },
        "required": ["text"],
    },
    "upload_file": {
        "type": "object",
        "properties": {
            "uid": {"type": "string"},
            "filePath": {"type": "string"},
            "includeSnapshot": {"type": "boolean"},
        },
        "required": ["uid", "filePath"],
    },
    "wait_for": {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "timeout": {"type": "number"},
        },
        "required": ["text"],
    },
}

# session_id を追加したツールスキーマを生成
def _proxy_schema(name: str, original: dict) -> dict:
    schema = json.loads(json.dumps(original))  # deep copy
    props = schema.setdefault("properties", {})
    props["session_id"] = {
        "type": "string",
        "description": (
            "Identifies which Chrome session to use. "
            "Each session_id gets its own isolated Chrome instance. "
            "Use a consistent id per test run (e.g. 'run-SUP-7693'). "
            "Omit or use 'default' for single-session usage."
        ),
    }
    return schema


TOOLS_LIST = [
    {
        "name": name,
        "description": f"[proxied] chrome-devtools {name}",
        "inputSchema": _proxy_schema(name, schema),
    }
    for name, schema in TOOL_PARAMS.items()
]


class ChildSession:
    """单个 chrome-devtools-mcp 子进程的封装。"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.proc: asyncio.subprocess.Process | None = None
        self._responses: dict[int, dict] = {}
        self._req_id = 0
        self._pump_task: asyncio.Task | None = None
        self._initialized = False
        self._lock = asyncio.Lock()
        self.last_used = time.time()

    async def start(self):
        profile_dir = f"/tmp/chrome-proxy-profile-{self.session_id}"
        self.proc = await asyncio.create_subprocess_exec(
            "npx", "-y", "chrome-devtools-mcp@latest",
            f"--userDataDir={profile_dir}",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._pump_task = asyncio.create_task(self._pump())
        await self._initialize()
        logger.info(f"[session:{self.session_id}] started (pid={self.proc.pid})")

    async def _pump(self):
        buffer = b""
        while self.proc and self.proc.stdout:
            try:
                chunk = await asyncio.wait_for(self.proc.stdout.read(4096), timeout=0.5)
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line.decode())
                        if msg.get("id") is not None:
                            self._responses[msg["id"]] = msg
                    except json.JSONDecodeError:
                        pass
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

    async def _wait_id(self, req_id: int, timeout: float = 30.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if req_id in self._responses:
                return self._responses.pop(req_id)
            await asyncio.sleep(0.02)
        raise TimeoutError(f"[session:{self.session_id}] no response for id={req_id}")

    async def _send(self, msg: dict):
        data = (json.dumps(msg) + "\n").encode()
        self.proc.stdin.write(data)
        await self.proc.stdin.drain()

    async def _initialize(self):
        self._req_id += 1
        await self._send({
            "jsonrpc": "2.0", "id": self._req_id, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "chrome-proxy", "version": "0.1"},
            },
        })
        await self._wait_id(self._req_id, timeout=30)
        await self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        self._initialized = True

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        async with self._lock:
            self._req_id += 1
            req_id = self._req_id
        self.last_used = time.time()
        await self._send({
            "jsonrpc": "2.0", "id": req_id, "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        })
        return await self._wait_id(req_id, timeout=60)

    async def stop(self):
        if self._pump_task:
            self._pump_task.cancel()
        # Kill the Chrome browser process first — it is a grandchild spawned by the
        # chrome-devtools-mcp node process and won't be reaped when the node process
        # is terminated. Scoped to this session's profile dir to avoid killing Chrome
        # instances belonging to other concurrent sessions.
        await asyncio.create_subprocess_exec(
            "pkill", "-f", f"chrome-proxy-profile-{self.session_id}",
            stderr=asyncio.subprocess.DEVNULL,
        )
        if self.proc:
            try:
                self.proc.terminate()
                await asyncio.wait_for(self.proc.wait(), timeout=5)
            except Exception:
                self.proc.kill()
        logger.info(f"[session:{self.session_id}] stopped")


class SessionManager:
    def __init__(self, idle_timeout: int = 300):
        self._sessions: dict[str, ChildSession] = {}
        self._lock = asyncio.Lock()
        self._idle_timeout = idle_timeout

    async def get_or_create(self, session_id: str) -> ChildSession:
        async with self._lock:
            if session_id not in self._sessions:
                session = ChildSession(session_id)
                await session.start()
                self._sessions[session_id] = session
            return self._sessions[session_id]

    async def cleanup_idle(self):
        while True:
            await asyncio.sleep(60)
            now = time.time()
            async with self._lock:
                stale = [
                    sid for sid, s in self._sessions.items()
                    if now - s.last_used > self._idle_timeout
                ]
            for sid in stale:
                async with self._lock:
                    session = self._sessions.pop(sid, None)
                if session:
                    await session.stop()

    async def stop_all(self):
        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for s in sessions:
            await s.stop()


class ProxyServer:
    def __init__(self):
        self.manager = SessionManager()
        self._req_id = 0

    def _make_response(self, req_id: Any, result: Any) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _make_error(self, req_id: Any, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    async def handle_initialize(self, req_id: Any, params: dict) -> dict:
        return self._make_response(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "chrome-devtools-proxy", "version": "0.1.0"},
        })

    async def handle_tools_list(self, req_id: Any) -> dict:
        return self._make_response(req_id, {"tools": TOOLS_LIST})

    async def handle_tools_call(self, req_id: Any, params: dict) -> dict:
        tool_name = params.get("name", "")
        arguments = dict(params.get("arguments") or {})

        session_id = arguments.pop("session_id", "default") or "default"

        if tool_name not in TOOL_PARAMS:
            return self._make_error(req_id, -32601, f"Unknown tool: {tool_name}")

        try:
            session = await self.manager.get_or_create(session_id)
            result = await session.call_tool(tool_name, arguments)
            # 透传子进程的 result 或 error
            if "result" in result:
                return self._make_response(req_id, result["result"])
            elif "error" in result:
                return self._make_error(req_id, result["error"].get("code", -1), result["error"].get("message", "child error"))
            else:
                return self._make_error(req_id, -1, "unexpected child response shape")
        except TimeoutError as e:
            return self._make_error(req_id, -32000, str(e))
        except Exception as e:
            return self._make_error(req_id, -32000, f"proxy error: {e}")

    async def run(self):
        asyncio.create_task(self.manager.cleanup_idle())
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        loop = asyncio.get_event_loop()
        await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)

        write_transport, _ = await loop.connect_write_pipe(
            asyncio.BaseProtocol, sys.stdout.buffer
        )

        async def write_msg(msg: dict):
            data = (json.dumps(msg) + "\n").encode()
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()

        try:
            buffer = b""
            while True:
                try:
                    chunk = await asyncio.wait_for(reader.read(4096), timeout=1.0)
                    if not chunk:
                        break
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            msg = json.loads(line.decode())
                        except json.JSONDecodeError:
                            continue

                        method = msg.get("method", "")
                        req_id = msg.get("id")
                        params = msg.get("params") or {}

                        if method == "initialize":
                            resp = await self.handle_initialize(req_id, params)
                            await write_msg(resp)
                        elif method == "notifications/initialized":
                            pass  # no response needed
                        elif method == "tools/list":
                            resp = await self.handle_tools_list(req_id)
                            await write_msg(resp)
                        elif method == "tools/call":
                            # 并发处理：不 await，直接 create_task
                            asyncio.create_task(
                                self._handle_and_write(req_id, params, write_msg)
                            )
                        elif req_id is not None:
                            await write_msg(self._make_error(req_id, -32601, f"Method not found: {method}"))
                except asyncio.TimeoutError:
                    continue
        finally:
            await self.manager.stop_all()

    async def _handle_and_write(self, req_id: Any, params: dict, write_fn):
        resp = await self.handle_tools_call(req_id, params)
        await write_fn(resp)

    async def run_http_sidecar(self, port: int = 9223):
        """
        Local HTTP sidecar — allows scripts (ts-node, etc.) to call proxy tools
        without going through the stdio MCP channel.

        POST http://localhost:9223/call
        Body: {"tool": "evaluate_script", "arguments": {...}, "session_id": "default"}
        Response: {"result": ...} or {"error": ...}

        The stdio MCP path is completely unaffected — this is an additive sidecar.
        """
        from aiohttp import web

        async def handle_call(request: web.Request) -> web.Response:
            try:
                body = await request.json()
            except Exception:
                return web.json_response({"error": "invalid JSON"}, status=400)

            tool = body.get("tool", "")
            arguments = dict(body.get("arguments") or {})
            session_id = body.get("session_id", "default") or "default"

            if not tool:
                return web.json_response({"error": "missing 'tool'"}, status=400)

            params = {"name": tool, "arguments": {**arguments, "session_id": session_id}}
            resp = await self.handle_tools_call(req_id=1, params=params)

            if "result" in resp:
                return web.json_response({"result": resp["result"]})
            else:
                return web.json_response({"error": resp.get("error", {}).get("message", "unknown error")}, status=500)

        app = web.Application()
        app.router.add_post("/call", handle_call)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "localhost", port)
        await site.start()
        logger.info(f"HTTP sidecar listening on http://localhost:{port}/call")
        # run forever alongside the stdio loop
        while True:
            await asyncio.sleep(3600)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )

    async def main():
        proxy = ProxyServer()
        await asyncio.gather(
            proxy.run(),
            proxy.run_http_sidecar(),
        )

    asyncio.run(main())
