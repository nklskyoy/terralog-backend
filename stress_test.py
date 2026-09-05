import asyncio
import aiohttp
import time
import statistics
import argparse

async def fetch(session, url, request_id):
    start_time = time.perf_counter()
    try:
        async with session.get(url, timeout=10, ssl=False) as response:
            await response.text()  # Wait for full response body
            status = response.status
    except Exception as e:
        status = type(e).__name__
    end_time = time.perf_counter()
    return end_time - start_time, status

async def run_stress_test(url, concurrency):
    print(f"\n[{concurrency} PARALLEL REQUESTS]")
    print(f"Launching {concurrency} concurrent requests to {url}...")
    
    async with aiohttp.ClientSession() as session:
        tasks = [fetch(session, url, i) for i in range(concurrency)]
        start_time = time.perf_counter()
        results = await asyncio.gather(*tasks)
        end_time = time.perf_counter()
        
    total_time = end_time - start_time
    
    response_times = []
    success_count = 0
    errors = {}
    
    for rt, status in results:
        response_times.append(rt)
        if status == 200:
            success_count += 1
        else:
            errors[status] = errors.get(status, 0) + 1
            
    print(f"Total time elapsed: {total_time:.3f} seconds")
    print(f"Successful (HTTP 200): {success_count}/{concurrency}")
    if errors:
        print(f"Failures/Errors: {errors}")
        
    if response_times:
        print(f"Fastest response: {min(response_times) * 1000:.2f} ms")
        print(f"Slowest response: {max(response_times) * 1000:.2f} ms")
        print(f"Average response: {statistics.mean(response_times) * 1000:.2f} ms")
        print(f"Median response:  {statistics.median(response_times) * 1000:.2f} ms")
        print(f"Throughput:       {concurrency / total_time:.2f} requests/sec")


async def main():
    parser = argparse.ArgumentParser(description="Terralog Stress Tester")
    parser.add_argument("--url", default="https://localhost:8443/api/global-state", help="The URL to stress test")
    args = parser.parse_args()
    
    print("==================================================")
    print(" TERRALOG LOAD TESTER")
    print("==================================================")
    print("Target URL:", args.url)
    print("Note: To run against production securely, make sure you forwarded the port:")
    print("      ssh -L 8443:localhost:443 root@217.154.89.127")
    
    levels = [30, 40, 50]
    for concurrency in levels:
        await run_stress_test(args.url, concurrency)
        if concurrency != levels[-1]:
            print("\nCooling down for 2 seconds...")
            time.sleep(2)
            
    print("\n==================================================")
    print(" TEST COMPLETE")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(main())
