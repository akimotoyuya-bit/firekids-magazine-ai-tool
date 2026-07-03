"""AWS Bedrock クライアント（Phase 2 リファクタリングで app.py から分離）。"""
import json
import os


# ─── AWS Bedrock ──────────────────────────────────────────────────────────────

def get_bedrock_client():
    import boto3
    return boto3.client(
        "bedrock-runtime",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


def invoke_claude_messages(messages: list[dict], max_tokens: int = 8000) -> tuple[str, str]:
    """複数ターンの messages を渡して呼び出す。戻り値: (テキスト, stop_reason)。

    stop_reason が "max_tokens" の場合、max_tokens 上限に達して本文が途中で
    打ち切られたことを意味する（呼び出し側で継続生成の要否を判断できるようにする）。
    """
    model_id = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
    client = get_bedrock_client()
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": messages,
    }
    resp = client.invoke_model(
        modelId=model_id,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )
    data = json.loads(resp["body"].read())
    text = data["content"][0]["text"] if data.get("content") else ""
    return text, data.get("stop_reason", "") or ""


def invoke_claude_messages_stream(messages: list[dict], on_chunk, max_tokens: int = 8000) -> tuple[str, str]:
    """複数ターンの messages をストリーミングで呼び出す。戻り値: (テキスト, stop_reason)。"""
    model_id = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
    client = get_bedrock_client()
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": messages,
    }
    try:
        resp = client.invoke_model_with_response_stream(
            modelId=model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
    except Exception:
        full, stop_reason = invoke_claude_messages(messages, max_tokens=max_tokens)
        if on_chunk and full:
            on_chunk(full)
        return full, stop_reason

    parts: list[str] = []
    stop_reason = ""
    for event in resp["body"]:
        chunk = event.get("chunk")
        if not chunk:
            continue
        data = json.loads(chunk["bytes"].decode("utf-8"))
        dtype = data.get("type")
        if dtype == "content_block_delta":
            text = data.get("delta", {}).get("text", "")
            if text:
                parts.append(text)
                if on_chunk:
                    on_chunk(text)
        elif dtype == "message_delta":
            stop_reason = data.get("delta", {}).get("stop_reason") or stop_reason
    return "".join(parts), stop_reason


def invoke_claude(prompt: str, max_tokens: int = 8000) -> str:
    text, _ = invoke_claude_messages([{"role": "user", "content": prompt}], max_tokens=max_tokens)
    return text


def invoke_claude_stream(prompt: str, on_chunk, max_tokens: int = 8000) -> str:
    """Bedrock のレスポンスストリーミングで本文を生成し、
    テキスト断片が届くたびに on_chunk(delta_text) を呼ぶ。完成テキストを返す。

    リアルタイムの「生成中」プレビュー用。ストリーミング非対応エラー時は
    通常の invoke_claude にフォールバックする。
    """
    text, _ = invoke_claude_messages_stream([{"role": "user", "content": prompt}], on_chunk, max_tokens=max_tokens)
    return text
