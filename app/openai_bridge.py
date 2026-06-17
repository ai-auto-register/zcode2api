import json
import time
import uuid

from fastapi.responses import StreamingResponse
import httpx

def _generate_id():
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"

def _map_stop_reason(reason: str) -> str:
    if reason == "end_turn" or reason == "stop_sequence":
        return "stop"
    if reason == "max_tokens":
        return "length"
    if reason == "tool_use":
        return "tool_calls"
    return "stop"

def _map_usage(u: dict) -> dict:
    if not u:
        return {}
    prompt_tokens = u.get("input_tokens", 0)
    completion_tokens = u.get("output_tokens", 0)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens
    }

def convert_openai_to_anthropic(body: dict) -> dict:
    """把 OpenAI 的请求体转换为 Anthropic 的请求体。"""
    out = {"model": body.get("model")}
    
    system_parts = []
    dialogue = []
    messages = body.get("messages", [])
    
    for m in messages:
        if not isinstance(m, dict):
            continue
        if m.get("role") == "system":
            content = m.get("content")
            if isinstance(content, str):
                system_parts.append(content)
            elif content:
                system_parts.append(json.dumps(content))
            continue
        
        content = m.get("content", "")
        if isinstance(content, str):
            anthropic_content = [{"type": "text", "text": content}]
        elif isinstance(content, list):
            anthropic_content = []
            for part in content:
                if isinstance(part, str):
                    anthropic_content.append({"type": "text", "text": part})
                elif isinstance(part, dict) and part.get("type") == "text":
                    anthropic_content.append({"type": "text", "text": part.get("text", "")})
        else:
            anthropic_content = [{"type": "text", "text": str(content)}]
            
        dialogue.append({
            "role": "assistant" if m.get("role") == "assistant" else "user",
            "content": anthropic_content
        })
        
    if system_parts:
        out["system"] = "\n\n".join(system_parts)
    out["messages"] = dialogue
    
    max_tokens = body.get("max_tokens") or body.get("max_completion_tokens")
    out["max_tokens"] = max_tokens if isinstance(max_tokens, int) else 4096
    
    if "temperature" in body:
        out["temperature"] = body["temperature"]
    if "top_p" in body:
        out["top_p"] = body["top_p"]
    if "stop" in body:
        stop = body["stop"]
        out["stop_sequences"] = stop if isinstance(stop, list) else [stop]
    if body.get("stream"):
        out["stream"] = True
        
    return out

def convert_anthropic_to_openai(response: dict, model: str) -> dict:
    """非流式：把 Anthropic 的响应转换为 OpenAI 格式。"""
    content_blocks = response.get("content", [])
    text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
    
    return {
        "id": response.get("id") or _generate_id(),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": text
            },
            "finish_reason": _map_stop_reason(response.get("stop_reason"))
        }],
        "usage": _map_usage(response.get("usage"))
    }

async def openai_streaming_response(anthropic_stream, model: str) -> StreamingResponse:
    """流式：将 Anthropic SSE 帧转为 OpenAI SSE 帧并返回。"""
    
    async def _stream_generator():
        msg_id = _generate_id()
        created = int(time.time())
        sent_head = False
        finish_reason = "stop"
        usage = {}
        
        def sse_frame(obj: dict) -> bytes:
            return f"data: {json.dumps(obj, separators=(',', ':'))}\n\n".encode("utf-8")
            
        def head_chunk() -> bytes:
            return sse_frame({
                "id": msg_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]
            })
            
        buffer = b""
        async for chunk in anthropic_stream:
            buffer += chunk
            while b"\n\n" in buffer:
                frame_bytes, buffer = buffer.split(b"\n\n", 1)
                frame = frame_bytes.decode("utf-8")
                
                # Extract the last data: line
                data_lines = [line[5:].strip() for line in frame.split("\n") if line.startswith("data:")]
                if not data_lines:
                    continue
                data_str = data_lines[-1]
                
                try:
                    obj = json.loads(data_str)
                except Exception:
                    continue
                
                event_type = obj.get("type")
                if event_type == "message_start":
                    if not sent_head:
                        yield head_chunk()
                        sent_head = True
                elif event_type == "content_block_delta":
                    delta = obj.get("delta", {})
                    if delta.get("type") == "text_delta" and "text" in delta:
                        yield sse_frame({
                            "id": msg_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": model,
                            "choices": [{"index": 0, "delta": {"content": delta["text"]}, "finish_reason": None}]
                        })
                elif event_type == "message_delta":
                    delta = obj.get("delta", {})
                    if "stop_reason" in delta and delta["stop_reason"]:
                        finish_reason = _map_stop_reason(delta["stop_reason"])
                    if "usage" in obj:
                        usage = obj["usage"]
                elif event_type == "message_stop":
                    yield sse_frame({
                        "id": msg_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
                        "usage": _map_usage(usage)
                    })
                    
        if not sent_head:
            yield head_chunk()
        yield b"data: [DONE]\n\n"
        
    return StreamingResponse(_stream_generator(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})