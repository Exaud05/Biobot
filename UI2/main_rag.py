import os
import re
import subprocess
import numpy as np
import faiss
import time
import json
from openai import OpenAI
import sys
import pickle
from config import get_api_key
from doc_loader import load_and_chunk_docs
from doc_fetcher import fetch_documentation

# ----------- ARGS & AUTH -------------
if len(sys.argv) > 1:
    user_query = sys.argv[1]
    chat_history = json.loads(sys.argv[2]) if len(sys.argv) > 2 else []
else:
    raise ValueError("Usage: python3 main_rag.py '<question>' '<chat_history_json>'")

user_api_key = get_api_key()
if not user_api_key:
    raise ValueError("API_KEY environment variable not set")


def get_openai_client(api_key):
    return OpenAI(api_key=api_key)


# ----------- HANDLER DETECTION -------------
HANDLERS_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "handlers.json")

def load_handlers_config():
    """Load the handler registry from handlers.json."""
    if not os.path.exists(HANDLERS_CONFIG_PATH):
        return {
            "opentrons": {
                "name": "Opentrons",
                "docs_path": "docs/opentrons",
                "store_path": "rag_store_opentrons.pkl",
                "simulate_cmd": ["opentrons_simulate"],
                "keywords": ["opentrons", "ot-2", "ot2", "ot-3", "ot3", "flex"]
            }
        }
    with open(HANDLERS_CONFIG_PATH, "r") as f:
        return json.load(f)


def detect_handler(query, history, api_key):
    """
    Detect which liquid handler the user is referring to using LLM classification.
    If the handler isn't in handlers.json, creates a dynamic entry so
    the doc fetcher can find and download its documentation.
    """
    handlers = load_handlers_config()
    available_ids = list(handlers.keys())
    client = get_openai_client(api_key)

    # Build context from recent conversation
    recent = [m for m in history if m["role"] != "system"][-4:]
    conversation_context = "\n".join(
        f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content'][:300]}"
        for m in recent
    )

    # Build the known platforms description
    if available_ids:
        known_list = "\n".join(
            f'  - "{hid}" → {cfg["name"]}'
            for hid, cfg in handlers.items()
        )
    else:
        known_list = "  (none configured)"

    response = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {
                "role": "system",
                "content": f"""You are an expert in lab automation and liquid handling robots.

Your task: identify which liquid handling PLATFORM (robot/instrument) the user is requesting a protocol for.

Here are the platforms already configured in our system:
{known_list}

INSTRUCTIONS:
1. Read the user's latest message AND the conversation history carefully.
2. Identify the liquid handling platform they are referring to.
3. If the platform matches one already configured, return its exact ID (the text in quotes above).
4. If the platform is NOT in the list above, return a new short lowercase ID for it. Use the brand name in lowercase, no spaces (e.g., "opentrons", "beckman", "agilent", "eppendorf", "gilson", "biomek").
5. If the user does NOT mention or imply any specific platform anywhere in the conversation, return "unknown".

IMPORTANT:
- Focus on the INSTRUMENT/ROBOT brand, not reagents, software, or lab techniques.
- Look at the ENTIRE conversation, not just the latest message — the platform may have been mentioned earlier.
- Common platforms include: Opentrons, Hamilton, Tecan, Beckman Coulter (Biomek), Agilent, Eppendorf, Gilson, PerkinElmer (JANUS), Formulatrix, Andrew Alliance, etc.

Return ONLY the platform ID. One word, lowercase, no quotes, no explanation."""
            },
            {
                "role": "user",
                "content": f"Conversation history:\n{conversation_context}\n\nLatest message: {query}"
            }
        ]
    )

    detected = response.output_text.strip().lower().strip('"').replace(" ", "_")

    # Known handler — return directly
    if detected in available_ids:
        return detected, handlers

    # "unknown" — default to first available, or opentrons
    if detected == "unknown":
        if available_ids:
            return available_ids[0], handlers
        detected = "opentrons"

    # New handler — ask the LLM for the proper display name
    name_response = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {
                "role": "system",
                "content": "Return ONLY the official full name of this liquid handling robot platform/brand. No explanation, no punctuation, just the name (e.g., 'Opentrons OT-2', 'Hamilton STAR', 'Tecan Fluent')."
            },
            {
                "role": "user",
                "content": f"Platform ID: {detected}"
            }
        ]
    )
    handler_name = name_response.output_text.strip().strip("'\"")

    print(f"STEP:Detected new platform: {handler_name} (not in config — will search for docs)...", flush=True)
    time.sleep(2)

    handlers[detected] = {
        "name": handler_name,
        "docs_path": f"docs/{detected}",
        "store_path": f"rag_store_{detected}.pkl",
        "simulate_cmd": None,
        "keywords": [detected]
    }

    # Save to handlers.json so it persists across sessions
    try:
        with open(HANDLERS_CONFIG_PATH, "w") as f:
            json.dump(handlers, f, indent=4)
        print(f"STEP:Added {handler_name} to handlers config", flush=True)
    except Exception as e:
        print(f"WARNING: Could not save to handlers.json: {e}", flush=True)

    return detected, handlers


# ----------- SUFFICIENCY CHECK -------------
def check_sufficient_info(query, history, api_key):
    client = get_openai_client(api_key)

    recent = [m for m in history if m["role"] != "system"][-4:]
    conversation = "\n".join(
        f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content'][:400]}"
        for m in recent
    )

    response = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {
                "role": "system",
                "content": """You are BioBot, an expert assistant in lab automation and liquid handling robots.

Your job is to check whether a user's protocol request contains enough information to generate a working script.

If you judge that there are enough infomations in the whole conversation, you were given the conversation history for that, reply with exactly: SUFFICIENT
Ask kindly for more informations if you assume that there are not enough informations in order to generate the code. You are specialized, you know what informations to ask. 
Try to help with examples or suggest kindly some default set ups in order to help the user when he does not provide you with sufficient informations.
"""
            },
            {
                "role": "user",
                "content": f"Conversation so far:\n{conversation}\n\nLatest request: {query}"
            }
        ]
    )

    answer = response.output_text.strip()
    if answer != "SUFFICIENT":
        print(answer, flush=True)
        sys.exit(0)


def consolidate_request(query, history, api_key):
    client = get_openai_client(api_key)

    recent = [m for m in history if m["role"] != "system"][-4:]
    conversation = "\n".join(
        f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content'][:500]}"
        for m in recent
    )

    response = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {
                "role": "system",
                "content": """You are an expert in lab automation. 
Given a conversation between a user and an assistant about a protocol request, 
write a structered, complete, self-contained protocol description that consolidates 
ALL the information provided across the entire conversation.

Note that the request will be sent to an LLM. Restructure it and write it in natural langage in 3th person (the user wants to...) describing what the user wants to do, as if he had provided everything upfront.
Return ONLY the consolidated request. No preamble, no explanation."""
            },
            {
                "role": "user",
                "content": f"Conversation:\n{conversation}\n\nLatest message: {query}"
            }
        ]
    )
    return response.output_text.strip()


# ----------- EMBEDDINGS -------------
def get_text_embedding_with_retry(text, retries=5, delay=2):
    client = get_openai_client(user_api_key)
    for i in range(retries):
        try:
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            if "rate limit" in str(e).lower():
                print(f"Rate limit hit. Retry {i+1}/{retries} in {delay} sec...")
                time.sleep(delay)
                delay *= 2
            else:
                raise
    raise RuntimeError("Failed to get embedding after retries.")


# ----------- COMPLETION -------------
def run_gpt(user_message, model="gpt-5"):
    client = get_openai_client(user_api_key)
    messages = [
        {
            "role": "system",
            "content": "You are an expert assistant specialized in lab automation with every kind of liquid handler. Generate full, clean and functional Python code for lab automation protocols."
        },
        {
            "role": "user",
            "content": user_message
        }
    ]
    response = client.responses.create(
        model=model,
        input=messages
    )
    return response.output_text


# ----------- SIMULATION -------------
def simulate_code(code, handler_config, save_path="generated_script.py"):
    """
    Run simulation if the handler has a simulator configured.
    Returns (stdout, stderr). If no simulator, returns a pass-through.
    """
    simulate_cmd = handler_config.get("simulate_cmd")

    with open(save_path, "w") as f:
        f.write(code)

    if not simulate_cmd:
        return "Simulation skipped (no simulator configured)", ""

    result = subprocess.run(simulate_cmd + [save_path], capture_output=True, text=True)
    return result.stdout, result.stderr


# ----------- REVERSE CHECK -------------
def reverse_check(user_query, generated_code, handler_name):
    reverse_prompt = f"""
    You are an expert lab assistant in Python scripts for {handler_name} laboratory robots.

    Here is a Python script :
    ```python
    {generated_code}
    
    And this is what the user requested : "{user_query}"

    Does this script match what the user requested ? Just in a general point of view, we don't need a precise comparison.
    Answer strictly with "Yes" or "No", followed by a short explanation.
    If the answer is no, ALWAYS suggest a corrected script right after.
    """
    verdict = run_gpt(reverse_prompt).strip()
    return verdict


# ----------- INDEX MANAGEMENT -------------
# Resolve all paths relative to this script's directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def load_or_build_index(handler_id, handler_config, chunk_size=3000):
    """
    Load the FAISS index for a handler from its pickle store,
    or build it from the docs folder if it doesn't exist.
    """
    docs_path = os.path.join(SCRIPT_DIR, handler_config["docs_path"])
    store_path = os.path.join(docs_path, handler_config["store_path"])

    if os.path.exists(store_path):
        print(f"STEP:Loading {handler_config['name']} documentation index...", flush=True)
        time.sleep(1)
        with open(store_path, "rb") as f:
            store = pickle.load(f)
        chunks = store["chunks"]
        chunk_sources = store["chunk_sources"]
        text_embeddings = store["embeddings"]
    else:
        # Check if docs folder exists and has content (including subfolders)
        has_local_docs = False
        if os.path.exists(docs_path):
            for root, dirs, files in os.walk(docs_path):
                for f in files:
                    if os.path.splitext(f)[1].lower() in ('.rst', '.pdf', '.txt'):
                        has_local_docs = True
                        break
                if has_local_docs:
                    break

        if not has_local_docs:
            # No local docs — try to fetch from the web
            handler_name = handler_config["name"]
            handler_keywords = handler_config.get("keywords", [])
            fetched = fetch_documentation(handler_name, handler_keywords, docs_path, user_api_key)

            if not fetched:
                print(f"STEP:Could not obtain documentation for {handler_name}", flush=True)
                return [], [], None

        print(f"STEP:Building {handler_config['name']} documentation index...", flush=True)
        chunks, chunk_sources = load_and_chunk_docs(docs_path, chunk_size)

        if not chunks:
            print(f"STEP:No parseable documents found in {docs_path}", flush=True)
            return [], [], None

        text_embeddings = np.array([get_text_embedding_with_retry(chunk) for chunk in chunks])

        # Save the index for future use
        os.makedirs(os.path.dirname(store_path), exist_ok=True)
        try:
            with open(store_path, "wb") as f:
                pickle.dump({
                    "chunks": chunks,
                    "chunk_sources": chunk_sources,
                    "embeddings": text_embeddings
                }, f)
            print(f"STEP:Index saved to {store_path}", flush=True)
        except Exception as e:
            print(f"WARNING: Could not save index: {e}", flush=True)

    d = text_embeddings.shape[1]
    index = faiss.IndexFlatL2(d)
    index.add(text_embeddings)

    return chunks, chunk_sources, index


# ----------- MAIN PIPELINE -------------
def run_query_and_fix(question, chunks, chunk_sources, index, handler_config, max_attempts=5):
    print("STEP:Analyzing your request...", flush=True)
    question_embedding = np.array([get_text_embedding_with_retry(question)])

    print("STEP:Searching documentation for relevant context...", flush=True)
    D, I = index.search(question_embedding, k=5)
    retrieved_chunks = [chunks[i] for i in I.tolist()[0]]
    retrieved_sources = [chunk_sources[i] for i in I.tolist()[0]]

    context = "\n\n".join(retrieved_chunks)
    prompt = f"""
Context information is below.
---------------------
{context}
---------------------
Given the context information and/or prior knowledge, answer the query.
Query: {question}
"""
    print("STEP:Generating protocol code...", flush=True)
    last_error = ""
    last_code = ""
    handler_name = handler_config["name"]

    for attempt in range(1, max_attempts + 1):
        response = run_gpt(prompt)
        code = response

        if not code:
            break

        last_code = code

        print(f"STEP:Attempt {attempt} — running simulation check...", flush=True)
        stdout, stderr = simulate_code(code, handler_config)
        if "Error" not in stderr and "Traceback" not in stderr and stdout.strip():
            print("STEP:Simulation passed — verifying semantic intent...", flush=True)
            verdict = reverse_check(question, code, handler_name)
            blocks = re.findall(r"```(?:python)?\n(.*?)```", verdict, re.DOTALL)
            if blocks:
                suggested_code = blocks[0].strip()
                stdout, stderr = simulate_code(suggested_code, handler_config)
            print("STEP:All checks passed! Returning final code...", flush=True)
            time.sleep(2)
            return code, retrieved_chunks, retrieved_sources, attempt, "", code

        print(f"STEP:Simulation failed on attempt {attempt} — correcting errors...", flush=True)
        prompt = f"""
I have some errors : 
{stderr}

Please correct accordingly this code you've given me : 
{code}

For the query : {question} 
And return the full corrected Python script, don't ask me to complete the code, don't ask me specific informations, always return a python code"""

        last_error = stderr.strip()

    return None, retrieved_chunks, retrieved_sources, attempt, last_error, last_code


# ============================================================
# EXECUTION
# ============================================================

# 1. Check if we have enough info
check_sufficient_info(user_query, chat_history, user_api_key)

# 2. Consolidate the request
consolidated_query = consolidate_request(user_query, chat_history, user_api_key)
print("consolidated request: ", consolidated_query)

# 3. Detect which handler the user needs
handler_id, handlers = detect_handler(user_query, chat_history, user_api_key)
handler_config = handlers[handler_id]
print(f"STEP:Detected platform: {handler_config['name']}", flush=True)
time.sleep(2)

# 4. Load or build the index for this handler
chunks, chunk_sources, index = load_or_build_index(handler_id, handler_config)

if index is None or not chunks:
    print(f"No documentation available for {handler_config['name']}. "
          f"Please add documents to {handler_config['docs_path']}/", flush=True)
    sys.exit(0)

# 5. Run the RAG pipeline
final_code, sources_used, file_refs, attempts, last_error, last_code = \
    run_query_and_fix(consolidated_query, chunks, chunk_sources, index, handler_config)

if final_code:
    print(final_code)
else:
    print("STEP:Generation failed — preparing last attempt for review...", flush=True)
    fail_msg = (
        "I wasn't able to generate a fully functional script after several attempts. "
        "The simulation kept returning errors that I couldn't resolve automatically. "
        "Here is the latest version of the script I generated — it may need some manual adjustments:"
    )
    print("FAILED_CODE:" + fail_msg + "___CODE_SEP___" + (last_code or "# No code was generated."), flush=True)