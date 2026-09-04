import random
import secrets
import time
from flask import request, jsonify, Response, stream_with_context
from pydantic import ValidationError

from model import CacheMessage, SubmitInput
from helpers import (
    cache,
    require_session_token,
    get_current_token1,
    TOKEN_1_ROTATION_SECONDS,
    TOKEN_2_LIFETIME_SECONDS,
    create_session_token,
    _is_valid_token1,
    _is_localhost,
    ALLOWED_SUBSCRIBE_IPS
)

def hydrate_thread_messages(t_id, start=0, end=-1):
    msg_ids = cache.lrange(f"thread:{t_id}", start, end)
    if not msg_ids:
        return []
    # Fetch from messages_hash
    jsons = cache.hmget('messages_hash', *msg_ids)
    
    msgs = []
    for j in jsons:
        if j:
            msgs.append(CacheMessage.model_validate_json(j))
    return msgs

def register_routes(app):
    @app.route('/token', methods=['GET'])
    def issue_token1():
        """Return the current 5-minute Token 1 (localhost only)."""
        if not _is_localhost():
            return jsonify({"error": "Forbidden"}), 403
        return jsonify({
            "token": get_current_token1(),
            "expires_in_seconds": TOKEN_1_ROTATION_SECONDS - (int(time.time()) % TOKEN_1_ROTATION_SECONDS),
        }), 200

    @app.route('/session', methods=['POST', 'GET'])
    def exchange_session_token():
        """Exchange 5-minute Token 1 for a 2-hour Token 2 session token."""
        token1 = None
        auth = request.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            token1 = auth.split(' ', 1)[1]
        elif request.args.get('token'):
            token1 = request.args.get('token')
        elif request.is_json and request.json and 'token' in request.json:
            token1 = request.json.get('token')

        if not token1 or not _is_valid_token1(token1):
            return jsonify({"error": "fehlerhafter Token 1"}), 401

        token2 = create_session_token()
        return jsonify({
            "session_token": token2,
            "expires_in_seconds": TOKEN_2_LIFETIME_SECONDS
        }), 200

    @app.route('/subscribe', methods=['GET'])
    def subscribe_messages():
        """Real-time Server-Sent Events (SSE) stream restricted by IP."""
        client_ip = request.remote_addr
        if '*' not in ALLOWED_SUBSCRIBE_IPS and client_ip not in ALLOWED_SUBSCRIBE_IPS:
            return jsonify({"error": f"Zugriff verweigert für IP {client_ip}"}), 403

        def event_stream():
            pubsub = cache.pubsub()
            pubsub.subscribe('global_messages_channel')
            try:
                while True:
                    message = pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
                    if message and message['type'] == 'message':
                        yield f"data: {message['data']}\n\n"
                    else:
                        # Yield a heartbeat comment to check if client disconnected
                        yield ": heartbeat\n\n"
            except GeneratorExit:
                pubsub.unsubscribe('global_messages_channel')

        return Response(
            stream_with_context(event_stream()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Access-Control-Allow-Origin': '*',
            }
        )

    @app.route('/submit', methods=['POST'])
    @app.route('/message', methods=['POST'])
    @require_session_token
    def save_message():
        try:
            data = request.json or {}
            input_data = SubmitInput(**data)
        except ValidationError as e:
            return jsonify(e.errors()), 400

        # Get a new unique ID for the message
        new_msg_id = cache.incr('next_msg_id')
        new_msg = CacheMessage(id=new_msg_id, msg=input_data.msg)
        
        # Save message node globally
        cache.hset('messages_hash', new_msg_id, new_msg.model_dump_json())

        if input_data.thread_id is None:
            # Create new thread (Super-node)
            thread_id = secrets.token_hex(8)
            
            # Ensure base messages are linked properly
            msg_ids_to_save = [str(m.id) for m in input_data.base_messages] + [str(new_msg_id)]
            
            # Store hierarchy metadata
            parents_str = ",".join(input_data.parent_thread_ids)
            meta = {
                "id": thread_id,
                "parent_thread_ids": parents_str,
                "created_at": str(time.time())
            }
            cache.hset(f"thread_meta:{thread_id}", mapping=meta)
            cache.sadd('threads_set', thread_id)
            
            if msg_ids_to_save:
                cache.rpush(f"thread:{thread_id}", *msg_ids_to_save)
                
            # Broadcast the thread state
            import json
            latest_msgs = hydrate_thread_messages(thread_id, 0, -1)
            event_payload = {
                "thread_id": thread_id,
                "parent_thread_ids": input_data.parent_thread_ids,
                "messages": [m.model_dump() for m in latest_msgs],
                "created_at": float(meta["created_at"])
            }
            cache.publish('global_messages_channel', json.dumps(event_payload))
            return jsonify({"status": "success", "thread_id": thread_id, "saved_id": new_msg_id}), 201
        else:
            # Push to existing thread (Super-node)
            thread_id = input_data.thread_id
            if not cache.sismember('threads_set', thread_id):
                cache.sadd('threads_set', thread_id)
                meta = {
                    "id": thread_id,
                    "parent_thread_ids": "",
                    "created_at": str(time.time())
                }
                cache.hset(f"thread_meta:{thread_id}", mapping=meta)
                
            cache.rpush(f"thread:{thread_id}", str(new_msg_id))
            
            import json
            latest_msgs = hydrate_thread_messages(thread_id, 0, -1)
            meta_raw = cache.hgetall(f"thread_meta:{thread_id}")
            parents = meta_raw.get("parent_thread_ids", "").split(",") if meta_raw.get("parent_thread_ids") else []
            event_payload = {
                "thread_id": thread_id,
                "parent_thread_ids": parents,
                "messages": [m.model_dump() for m in latest_msgs],
                "created_at": float(meta_raw.get("created_at", time.time()))
            }
            cache.publish('global_messages_channel', json.dumps(event_payload))
            return jsonify({"status": "success", "thread_id": thread_id, "saved_id": new_msg_id}), 201

    @app.route('/global-state', methods=['GET'])
    def get_global_state():
        thread_ids = cache.smembers('threads_set')
        threads = []
        for t_id in thread_ids:
            meta = cache.hgetall(f"thread_meta:{t_id}")
            parents = meta.get("parent_thread_ids", "").split(",") if meta.get("parent_thread_ids") else []
            created_at = float(meta.get("created_at", 0))
            msgs = hydrate_thread_messages(t_id, 0, -1)
            threads.append({
                "id": t_id,
                "parent_thread_ids": parents,
                "created_at": created_at,
                "messages": [m.model_dump() for m in msgs]
            })
        threads.sort(key=lambda x: x['created_at'], reverse=True)
        return jsonify({"threads": threads[:16]}), 200

    @app.route('/thread-stats', methods=['GET'])
    @require_session_token
    def get_thread_stats():
        thread_ids = cache.smembers('threads_set')
        return jsonify({"count": len(thread_ids)}), 200

    @app.route('/thread-merge', methods=['GET'])
    @require_session_token
    def get_thread_merge():
        thread_ids = cache.smembers('threads_set')
        if len(thread_ids) < 2:
            return jsonify({"error": "Not enough threads to merge"}), 400
        
        t1, t2 = random.sample(list(thread_ids), 2)
        
        msgs1 = hydrate_thread_messages(t1)
        msgs2 = hydrate_thread_messages(t2)
        
        n1 = random.choice([1, 2])
        n2 = 3 - n1
        if len(msgs1) < n1:
            n1 = len(msgs1)
            n2 = 3 - n1
        if len(msgs2) < n2:
            n2 = len(msgs2)
            n1 = 3 - n2
            if len(msgs1) < n1:
                n1 = len(msgs1)
                
        picked1 = random.sample(msgs1, n1) if n1 > 0 else []
        picked2 = random.sample(msgs2, n2) if n2 > 0 else []
        
        picked = picked1 + picked2
        random.shuffle(picked)
        
        return jsonify({
            "id": None,
            "parent_thread_ids": [t1, t2],
            "messages": [m.model_dump() for m in picked]
        })

    @app.route('/thread-push', methods=['GET'])
    @require_session_token
    def get_thread_push():
        thread_ids = cache.smembers('threads_set')
        if not thread_ids:
            return jsonify({"error": "No threads available"}), 400
            
        t_id = random.choice(list(thread_ids))
        msgs = hydrate_thread_messages(t_id, -3, -1)
        
        return jsonify({
            "id": t_id,
            "parent_thread_ids": [],
            "messages": [m.model_dump() for m in msgs]
        })

    @app.route('/thread-split', methods=['GET'])
    @require_session_token
    def get_thread_split():
        thread_ids = cache.smembers('threads_set')
        if not thread_ids:
            return jsonify({"error": "No threads available"}), 400
            
        t_id = random.choice(list(thread_ids))
        all_msgs = hydrate_thread_messages(t_id)
        
        k = min(3, len(all_msgs))
        picked = random.sample(all_msgs, k)
        
        return jsonify({
            "id": None,
            "parent_thread_ids": [t_id],
            "messages": [m.model_dump() for m in picked]
        })

    @app.route('/msgs', methods=['GET'])
    @require_session_token
    def get_messages():
        # Kept for backward compatibility
        return jsonify({}), 200
