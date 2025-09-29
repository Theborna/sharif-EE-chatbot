# gpu_server_polling.py (patch)
import asyncio
import aiohttp

UBUNTU_HANDSHAKE_URL = "https://api.mydevtool.xyz/handshake_gpu"
UBUNTU_POLL_TASKS_URL = "https://api.mydevtool.xyz/poll_tasks"
UBUNTU_SEND_RESULT_URL = "https://api.mydevtool.xyz/send_task_result"

API_TOKEN = "7477344775:AAELH985LUveNVZ3pVJFrIG5-7lAmoJXX3I"
POLL_INTERVAL = 2  # seconds between polling


async def handshake(session: aiohttp.ClientSession) -> bool:
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    try:
        async with session.post(UBUNTU_HANDSHAKE_URL, headers=headers, ssl=True) as resp:
            text = await resp.text()
            ctype = resp.headers.get("Content-Type", "")
            if resp.status != 200:
                print(f"[GPU] Handshake returned status {resp.status}: {text}")
                return False
            if "application/json" in ctype:
                try:
                    data = await resp.json()
                except Exception as e:
                    print(f"[GPU] Failed to decode JSON handshake response: {e}; raw: {text}")
                    return False
                if data.get("status") == "ok":
                    print(f"[GPU] Handshake success: {data}")
                    return True
                print(f"[GPU] Handshake unexpected JSON response: {data}")
                return False
            else:
                print(f"[GPU] Handshake non-JSON response (status {resp.status}): {text}")
                return False
    except Exception as e:
        print(f"[GPU] Handshake failed (exception): {e}")
        return False


async def poll_tasks(session: aiohttp.ClientSession):
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    while True:
        try:
            async with session.get(UBUNTU_POLL_TASKS_URL, headers=headers, ssl=True) as resp:
                text = await resp.text()
                if resp.status == 200:
                    ctype = resp.headers.get("Content-Type", "")
                    if "application/json" in ctype:
                        data = await resp.json()
                        tasks = data.get("tasks", [])
                        if tasks:
                            print(f"[GPU] Received {len(tasks)} tasks")
                            for task in tasks:
                                asyncio.create_task(process_task(task, session))
                    else:
                        print(f"[GPU] poll_tasks non-JSON response: {text}")
                else:
                    print(f"[GPU] poll_tasks returned status {resp.status}: {text}")
        except Exception as e:
            print(f"[GPU] Polling failed: {e}")

        await asyncio.sleep(POLL_INTERVAL)


async def process_task(task: dict, session: aiohttp.ClientSession):
    print(task)
    chat_id = task.get("chat_id")
    user_id = task.get("user_id")
    input_text = task.get("text", "")
    output_text = input_text

    payload = {"chat_id": chat_id, "user_id": user_id, "text": output_text}
    try:
        headers = {"Authorization": f"Bearer {API_TOKEN}"}
        async with session.post(UBUNTU_SEND_RESULT_URL, json=payload, headers=headers, ssl=True) as resp:
            text = await resp.text()
            try:
                data = await resp.json()
                print(f"[GPU] Sent result for {chat_id}/{user_id}: {data}")
            except Exception:
                print(f"[GPU] send_task_result non-JSON response (status {resp.status}): {text}")
    except Exception as e:
        print(f"[GPU] Sending result failed: {e}")


async def main():
    async with aiohttp.ClientSession() as session:
        ok = await handshake(session)
        if not ok:
            print(
                "[GPU] Handshake did not succeed — the server may reject polling, continuing to poll for debug purposes")
        print("[GPU] Starting polling loop...")
        await poll_tasks(session)


if __name__ == "__main__":
    asyncio.run(main())