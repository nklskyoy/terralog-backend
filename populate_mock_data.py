import os
import time
import json
import redis

def populate():
    redis_host = os.environ.get("REDIS_HOST", "localhost")
    print(f"Connecting to Redis at {redis_host}:6379...")
    
    r = redis.Redis(host=redis_host, port=6379, decode_responses=True)
    r.flushdb() # Clear existing data

    # 1. Populate messages globally
    messages = [
        {"id": 101, "msg": "soil moisture at 42% (sensor A)"},
        {"id": 205, "msg": "temp is 22C (sensor B)"},
        {"id": 301, "msg": "anomaly detected in field-north"},
        {"id": 302, "msg": "investigation pending..."},
        {"id": 401, "msg": "battery level low on drone 3"},
        {"id": 405, "msg": "returning to base"},
        {"id": 102, "msg": "drone deployed to sector 4"},
        {"id": 999, "msg": "Merge complete. Monitoring sector 4."}
    ]

    for m in messages:
        r.hset("messages_hash", str(m["id"]), json.dumps(m))

    # 2. Populate thread structures
    threads = [
        {
            "id": "mock-thread-a",
            "parents": [],
            "created_at": time.time() - 10000,
            "msg_ids": [101]
        },
        {
            "id": "mock-thread-b",
            "parents": [],
            "created_at": time.time() - 8000,
            "msg_ids": [205]
        },
        {
            "id": "mock-thread-c",
            "parents": [],
            "created_at": time.time() - 5000,
            "msg_ids": [301, 302]
        },
        {
            "id": "mock-thread-d",
            "parents": ["mock-thread-c"],
            "created_at": time.time() - 2000,
            "msg_ids": [401, 405]
        },
        {
            "id": "mock-thread-merge",
            "parents": ["mock-thread-a", "mock-thread-b"],
            "created_at": time.time(),
            "msg_ids": [101, 205, 102, 999]
        }
    ]

    for t in threads:
        tid = t["id"]
        # Add to global set
        r.sadd("threads_set", tid)
        
        # Save metadata
        meta = {
            "id": tid,
            "parent_thread_ids": ",".join(t["parents"]),
            "created_at": str(t["created_at"])
        }
        r.hset(f"thread_meta:{tid}", mapping=meta)
        
        # Save message IDs to the thread list
        if t["msg_ids"]:
            r.rpush(f"thread:{tid}", *[str(mid) for mid in t["msg_ids"]])

    # Ensure new messages don't collide with mock IDs
    r.set("next_msg_id", 1000)
    print("Redis mock data populated successfully!")

if __name__ == "__main__":
    populate()
