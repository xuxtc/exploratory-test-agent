"""
验证 chrome-devtools-mcp 是否支持并发工具调用。

测试方法：
- 先开两个 tab，再同时对两个 tab 各发一个 navigate_page
- 测量总耗时 vs 基准单次耗时，判断串行还是并发

预期：
- 并发：总耗时 ≈ 1x 基准
- 串行：总耗时 ≈ 2x 基准
"""

import asyncio
import json
import time


READ_BUFFER = {}
READ_LOCK = asyncio.Lock()


async def pump_reader(reader, responses: dict):
    """持续读取 stdout，按 id 存入 responses dict。"""
    buffer = b""
    while True:
        try:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=0.5)
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
                    msg_id = msg.get("id")
                    if msg_id is not None:
                        responses[msg_id] = msg
                except json.JSONDecodeError:
                    pass
        except asyncio.TimeoutError:
            continue
        except Exception:
            break


async def wait_for_id(responses: dict, req_id: int, timeout: float = 30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if req_id in responses:
            return responses.pop(req_id)
        await asyncio.sleep(0.05)
    raise TimeoutError(f"No response for id={req_id} within {timeout}s")


async def send(writer, request: dict):
    writer.write((json.dumps(request) + "\n").encode())
    await writer.drain()


async def main():
    print("Starting chrome-devtools-mcp (headless + isolated)...")
    proc = await asyncio.create_subprocess_exec(
        "npx", "-y", "chrome-devtools-mcp@latest",
        "--headless", "--isolated",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )

    responses = {}
    pump_task = asyncio.create_task(pump_reader(proc.stdout, responses))

    # initialize
    await send(proc.stdin, {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "concurrency-test", "version": "0.1"}
        }
    })
    resp = await wait_for_id(responses, 1)
    print(f"Connected: {resp['result']['serverInfo']['name']} v{resp['result']['serverInfo']['version']}")

    await send(proc.stdin, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    # 开两个 tab
    print("\nOpening two tabs...")
    await send(proc.stdin, {
        "jsonrpc": "2.0", "id": 10, "method": "tools/call",
        "params": {"name": "new_page", "arguments": {"url": "about:blank"}}
    })
    await send(proc.stdin, {
        "jsonrpc": "2.0", "id": 11, "method": "tools/call",
        "params": {"name": "new_page", "arguments": {"url": "about:blank"}}
    })
    r10 = await wait_for_id(responses, 10)
    r11 = await wait_for_id(responses, 11)
    print(f"Tab 1 opened: {str(r10.get('result',''))[:80]}")
    print(f"Tab 2 opened: {str(r11.get('result',''))[:80]}")

    # 列出 pages 确认有两个
    await send(proc.stdin, {
        "jsonrpc": "2.0", "id": 12, "method": "tools/call",
        "params": {"name": "list_pages", "arguments": {}}
    })
    r12 = await wait_for_id(responses, 12)
    pages_text = str(r12.get("result", ""))
    print(f"Pages: {pages_text[:200]}")

    # 基准：单次导航
    print("\n--- 基准：单次 navigate_page ---")
    t0 = time.time()
    await send(proc.stdin, {
        "jsonrpc": "2.0", "id": 20, "method": "tools/call",
        "params": {"name": "navigate_page", "arguments": {"url": "https://example.com"}}
    })
    await wait_for_id(responses, 20, timeout=30)
    baseline = time.time() - t0
    print(f"基准耗时: {baseline:.2f}s")

    # 核心测试：同时发两个 navigate_page
    print("\n--- 并发测试：同时发两个 navigate_page ---")
    t_start = time.time()

    # 同时写入两个请求（不 await 之间）
    await send(proc.stdin, {
        "jsonrpc": "2.0", "id": 30, "method": "tools/call",
        "params": {"name": "navigate_page", "arguments": {"url": "https://example.com"}}
    })
    t_s1 = time.time() - t_start
    await send(proc.stdin, {
        "jsonrpc": "2.0", "id": 31, "method": "tools/call",
        "params": {"name": "navigate_page", "arguments": {"url": "https://example.org"}}
    })
    t_s2 = time.time() - t_start
    print(f"  req#30 sent at t+{t_s1:.3f}s")
    print(f"  req#31 sent at t+{t_s2:.3f}s")

    r30, r31 = await asyncio.gather(
        wait_for_id(responses, 30, timeout=30),
        wait_for_id(responses, 31, timeout=30),
    )
    t_e1 = time.time() - t_start
    print(f"  Both done at t+{t_e1:.2f}s")
    t_total = time.time() - t_start

    print(f"\n=== 结果 ===")
    print(f"总耗时:       {t_total:.2f}s")
    print(f"基准单次:     {baseline:.2f}s")
    print(f"预期串行:     {baseline * 2:.2f}s")
    ratio = t_total / baseline

    print(f"耗时倍数:     {ratio:.2f}x")
    if ratio < 1.4:
        print("\n✅ 并发：MCP server 可同时处理多个工具调用")
    elif ratio > 1.7:
        print("\n❌ 串行：MCP server 单线程，工具调用排队")
    else:
        print("\n⚠️  结果模糊，建议重跑（可能受网络抖动影响）")

    pump_task.cancel()
    proc.terminate()
    await proc.wait()


if __name__ == "__main__":
    asyncio.run(main())
