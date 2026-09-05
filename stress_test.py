import asyncio
import aiohttp
import time
import statistics
import argparse

async def get_session_token(base_url):
    """Automatically logs into the API to get a Bearer token for submitting messages."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{base_url}/token", ssl=False) as res:
            if res.status != 200:
                raise Exception(f"Failed to get token1 (Status {res.status})")
            data = await res.json()
            token1 = data["token"]
            
        async with session.post(f"{base_url}/session", json={"token": token1}, ssl=False) as res:
            if res.status != 200:
                raise Exception(f"Failed to exchange token (Status {res.status})")
            data = await res.json()
            return data["session_token"]


async def fetch_endpoint(session, url, method="GET", headers=None, json_data=None):
    start_time = time.perf_counter()
    try:
        if method == "GET":
            async with session.get(url, headers=headers, timeout=15, ssl=False) as response:
                await response.text()
                status = response.status
        else:
            async with session.post(url, headers=headers, json=json_data, timeout=15, ssl=False) as response:
                await response.text()
                status = response.status
    except Exception as e:
        status = type(e).__name__
    end_time = time.perf_counter()
    return end_time - start_time, status

async def run_stress_test(base_url, concurrency, phase_name, method, endpoint, headers=None, payload_func=None):
    print(f"\n[{concurrency} PARALLEL] - {phase_name}")
    url = f"{base_url}{endpoint}"
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for i in range(concurrency):
            payload = payload_func(i) if payload_func else None
            tasks.append(fetch_endpoint(session, url, method, headers, payload))
            
        start_time = time.perf_counter()
        results = await asyncio.gather(*tasks)
        end_time = time.perf_counter()
        
    total_time = end_time - start_time
    
    response_times = []
    success_count = 0
    errors = {}
    
    for rt, status in results:
        response_times.append(rt)
        if status in (200, 201):
            success_count += 1
        else:
            errors[status] = errors.get(status, 0) + 1
            
    print(f"   Time elapsed: {total_time:.3f}s | Success: {success_count}/{concurrency} | Throughput: {concurrency/total_time:.1f} req/s")
    if errors:
        print(f"   Failures/Errors: {errors}")
    if response_times:
        print(f"   Avg Response: {statistics.mean(response_times)*1000:.1f} ms | Slowest: {max(response_times)*1000:.1f} ms")


async def main():
    parser = argparse.ArgumentParser(description="Terralog Full API Stress Tester")
    parser.add_argument("--url", default="https://localhost:8442/api", help="Base URL of API (e.g. https://localhost:8442/api)")
    args = parser.parse_args()
    
    base_url = args.url.rstrip('/')
    print("==================================================")
    print(" TERRALOG LOAD TESTER")
    print("==================================================")
    print(f"Targeting Base URL: {base_url}")
    
    print("\n[INIT] Authenticating to get a session token...")
    try:
        token = await get_session_token(base_url)
        print("       Success! Obtained session token for write tests.")
    except Exception as e:
        print(f"       FATAL ERROR: Could not authenticate: {e}")
        print("       (Did you remember to start your SSH tunnel?)")
        return
        
    auth_headers = {"Authorization": f"Bearer {token}"}
    
    def generate_payload(i):
        # Create a brand new thread with a message for each parallel request
        return {
            "thread_id": None,
            "parent_thread_ids": [],
            "base_messages": [],
            "msg": f"Stress test message {i} generated under high load"
        }
    
    levels = [30, 40, 50]
    
    print("\n==================================================")
    print(" PHASE 1: FETCHING GLOBAL GRAPH STATE (/global-state)")
    print("==================================================")
    for c in levels:
        await run_stress_test(base_url, c, "Fetch Messages", "GET", "/global-state")
        time.sleep(1.5)
        
    print("\n==================================================")
    print(" PHASE 2: CREATING & SAVING MESSAGES (/submit)")
    print("==================================================")
    for c in levels:
        await run_stress_test(base_url, c, "Save Messages", "POST", "/submit", auth_headers, generate_payload)
        time.sleep(1.5)
        
    print("\n==================================================")
    print(" TEST COMPLETE")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(main())
