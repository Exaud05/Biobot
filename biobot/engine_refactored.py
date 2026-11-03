"""
engine_refactored.py — Provider-agnostic version of engine.py

This shows how the existing engine.py functions migrate to use the
LLMProvider abstraction instead of hardcoded OpenAI calls.

Every function that previously did:
    client = OpenAI(api_key=...)
    response = client.responses.create(model=..., input=...)
    result = response.output_text

Now does:
    llm = get_provider(api_key=...)
    result = llm.complete(messages, model=...)

The logic stays identical — only the API call changes.
"""

import subprocess
import json
import os
from llm_provider import get_provider


def classify_prompt(prompt, chat_history=None, api_key=None):
    """Classify user prompt as 'code', 'general', or 'out'."""
    llm = get_provider(api_key=api_key)

    # Build context from recent messages
    context_block = ""
    if chat_history:
        recent = [m for m in chat_history if m["role"] != "system"][-6:]
        if recent:
            lines = []
            for m in recent:
                role_label = "User" if m["role"] == "user" else "Assistant"
                content = m["content"][:300] + "..." if len(m["content"]) > 300 else m["content"]
                lines.append(f"{role_label}: {content}")
            context_block = "\n\nRecent conversation:\n" + "\n".join(lines)

    messages = [
        {
            "role": "system",
            "content": """You are a classifier assistant. Classify the user message:
1. "code" : requesting code generation or a protocol script
2. "general" : lab automation question without requesting a script
3. "out" : unrelated to lab automation
Return ONLY one word: code, general, or out."""
        },
        {
            "role": "user",
            "content": f"Latest message: {prompt}{context_block}"
        }
    ]

    # Use the fast/cheap model for classification
    result = llm.complete(messages, model=llm.fast_model)
    return result.strip().lower()


def run_gpt(chat_history, model=None, api_key=None):
    """Standard (non-streaming) completion."""
    llm = get_provider(api_key=api_key)

    system_msg = next((m for m in chat_history if m["role"] == "system"), None)
    non_system = [m for m in chat_history if m["role"] != "system"][-9:]
    messages = [system_msg] + non_system if system_msg else non_system

    reply = llm.complete(messages, model=model or llm.default_model)
    chat_history.append({"role": "assistant", "content": reply})
    return reply


def run_gpt_stream(chat_history, model=None, api_key=None):
    """Streaming completion — yields tokens."""
    llm = get_provider(api_key=api_key)

    system_msg = next((m for m in chat_history if m["role"] == "system"), None)
    non_system = [m for m in chat_history if m["role"] != "system"][-9:]
    messages = [system_msg] + non_system if system_msg else non_system

    full_text = ""
    for token in llm.stream(messages, model=model or llm.default_model):
        full_text += token
        yield token

    chat_history.append({"role": "assistant", "content": full_text})


# ============================================================
# The rest of process_user_query stays exactly the same.
# The RAG pipeline (main_rag.py) would receive the provider
# name via environment variable alongside the API key.
# ============================================================

RAG_STATUS_PREFIX = "__RAG_STATUS__:"
RAG_STEP_PREFIX = "STEP:"

def process_user_query(user_query, chat_history, model, api_key=None):
    history = [msg for msg in chat_history]
    classification = classify_prompt(user_query, chat_history=history, api_key=api_key)

    if classification == "code":
        def _rag_generator():
            env = os.environ.copy()
            env["API_KEY"] = api_key or ""
            # Pass the detected provider so main_rag.py uses the same one
            env["LLM_PROVIDER"] = get_provider(api_key=api_key).name

            proc = subprocess.Popen(
                ["python3", "main_rag.py", user_query, json.dumps(history)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1, env=env
            )

            final_code_lines = []
            for raw_line in proc.stdout:
                for line_stripped in raw_line.split("\n"):
                    line_stripped = line_stripped.strip()
                    if not line_stripped:
                        continue
                    if line_stripped.startswith(RAG_STEP_PREFIX):
                        yield RAG_STATUS_PREFIX + line_stripped[len(RAG_STEP_PREFIX):]
                    else:
                        final_code_lines.append(line_stripped + "\n")

            proc.wait()
            if proc.returncode != 0:
                stderr_out = proc.stderr.read()
                print("main_rag.py error:", stderr_out)

            yield "".join(final_code_lines).strip()

        return _rag_generator()

    elif classification in {"general", "out"}:
        return run_gpt_stream(history, model, api_key=api_key)
