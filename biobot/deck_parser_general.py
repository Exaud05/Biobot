"""
deck_ai_parser.py — LLM-powered deck state extraction

Instead of regex-based parsing per platform, this module sends the generated
code to GPT-4o-mini and asks it to extract a structured deck layout JSON.

Works with ANY liquid handler because the LLM understands the code semantically.
"""

import json
import os
from openai import OpenAI
from config import get_api_key


EXTRACTION_PROMPT = """You are an expert in laboratory automation and liquid handling robots.

Given a protocol code or CSV picklist, extract the deck/instrument layout as a JSON object.

Return ONLY valid JSON with this exact structure (no markdown, no explanation):

{
  "platform": "<platform name, e.g. opentrons_ot2, echo_650, hamilton_star, tecan_fluent>",
  "platform_display": "<human readable name, e.g. Opentrons OT-2, Echo 650>",
  
  "deck": {
    "type": "<grid | dual_plate | linear | custom>",
    "rows": <number of rows in the grid, or null>,
    "cols": <number of columns in the grid, or null>,
    "positions": [
      {
        "id": "<slot/position identifier>",
        "row": <0-indexed row from bottom>,
        "col": <0-indexed column from left>,
        "labware": {
          "name": "<API/load name of the labware>",
          "display_name": "<human readable short name>",
          "type": "<plate | tiprack | reservoir | tuberack | trash | module | other>",
          "wells": <number of wells, or null>,
          "variable": "<variable name in the code>"
        },
        "fixed": <true if this position cannot be changed, e.g. fixed trash>,
        "module": "<module name if a module is loaded here, or null>"
      }
    ]
  },
  
  "instruments": [
    {
      "name": "<instrument API/model name>",
      "display_name": "<human readable name>",
      "mount": "<left | right | null for non-OT2>",
      "type": "<pipette | acoustic | channel_head | other>",
      "volume_range": "<e.g. 20-300 µL or null>",
      "variable": "<variable name in the code>",
      "tipracks": ["<position ids of associated tipracks>"]
    }
  ],
  
  "parameters": [
    {
      "name": "<variable name>",
      "display_name": "<human readable name>",
      "value": <numeric value>,
      "unit": "<µL, nL, ×, s, °C, etc.>",
      "category": "<volume | count | speed | temperature | other>",
      "description": "<brief description from code comments or context>"
    }
  ],
  
  "transfers": [
    {
      "action": "<transfer | aspirate | dispense | acoustic_transfer>",
      "volume": <volume as number>,
      "volume_unit": "<µL or nL>",
      "source": "<source description, e.g. 'reservoir A1' or 'source_plate wells'>",
      "destination": "<destination description>",
      "description": "<brief description of what this step does>"
    }
  ]
}

IMPORTANT RULES:
- For OT-2: deck is a 4x3 grid (rows 0-3, cols 0-2), slots 1-3 at row 0 (bottom), 10-12 at row 3 (top). Slot 12 is always fixed trash.
- For Echo: deck type is "dual_plate" with exactly 2 positions (source and destination plate).
- For Hamilton STAR: deck is "linear" with positions along the worktable.
- For unknown platforms: use "custom" deck type and describe positions as best as possible.
- Extract ALL named numeric parameters (volumes, counts, repetitions, speeds, temperatures).
- For parameters, use the variable name from the code, not a generic name.
- If the code uses variables for volumes (like `diluent_volume = 220`), extract those as parameters.
- If volumes are inline in function calls (like `.transfer(100, ...)`), still extract them as parameters.
- For transfers, summarize the protocol steps — don't list every single well-to-well transfer in a loop, describe the loop instead.
- Return ONLY the JSON object. No markdown fences, no explanation text.
"""


def extract_deck_state(code: str, api_key: str = None) -> dict:
    """
    Use GPT-4o-mini to extract a structured deck state from any protocol code.
    
    Args:
        code: The generated protocol code or CSV picklist
        api_key: OpenAI API key (uses default if not provided)
    
    Returns:
        dict: Structured deck state JSON
    """
    key = api_key or os.environ.get("API_KEY") or get_api_key()
    client = OpenAI(api_key=key)

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user", "content": f"Extract the deck layout from this code:\n\n{code}"}
            ],
        )

        result_text = response.output_text.strip()

        # Clean up — remove markdown fences if the LLM added them
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1] if "\n" in result_text else result_text[3:]
        if result_text.endswith("```"):
            result_text = result_text[:-3].strip()
        if result_text.startswith("json"):
            result_text = result_text[4:].strip()

        deck_state = json.loads(result_text)
        return deck_state

    except json.JSONDecodeError as e:
        print(f"Deck AI parser JSON error: {e}", flush=True)
        return {"error": f"Failed to parse LLM response as JSON: {str(e)}"}
    except Exception as e:
        print(f"Deck AI parser error: {e}", flush=True)
        return {"error": f"LLM extraction failed: {str(e)}"}


def update_code_with_changes(original_code: str, changes: dict, api_key: str = None) -> str:
    """
    Use GPT-4o-mini to update the protocol code based on user changes from the deck editor.
    
    Args:
        original_code: The current protocol code
        changes: Dict describing what changed, e.g.:
            {"type": "move_labware", "from_position": "1", "to_position": "5"}
            {"type": "change_labware", "position": "2", "old": "corning_96...", "new": "nest_96..."}
            {"type": "change_instrument", "mount": "right", "old": "p300...", "new": "p1000..."}
            {"type": "change_parameter", "name": "diluent_volume", "old_value": 220, "new_value": 150}
            {"type": "add_labware", "position": "5", "labware": "nest_12_reservoir_15ml"}
            {"type": "remove_labware", "position": "5"}
    
    Returns:
        str: Updated protocol code
    """
    key = api_key or os.environ.get("API_KEY") or get_api_key()
    client = OpenAI(api_key=key)

    update_prompt = f"""You are an expert in laboratory automation code.

Given a protocol code and a change description, update the code to reflect the change.

RULES:
- Keep ALL existing code structure, comments, variables, loops, and logic intact.
- Only modify the specific parts affected by the change.
- If changing a labware, update the load_labware call AND check if any well references need updating.
- If changing a pipette, update the load_instrument call AND update the tiprack to be compatible. Also check if transfer volumes are within the new pipette's range — if not, adjust them.
- If changing a volume parameter, update the variable assignment.
- If moving labware to a different slot, update only the slot number in load_labware.
- If adding labware, add a new load_labware line in the appropriate place.
- If removing labware, remove the load_labware line BUT keep any references to warn about breakage.
- Return ONLY the updated code. No explanation, no markdown fences."""

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=[
                {"role": "system", "content": update_prompt},
                {"role": "user", "content": f"Original code:\n```\n{original_code}\n```\n\nChange to apply:\n{json.dumps(changes, indent=2)}\n\nReturn the updated code:"}
            ],
        )

        result = response.output_text.strip()

        # Clean markdown fences
        if result.startswith("```"):
            lines = result.split("\n")
            result = "\n".join(lines[1:])
        if result.endswith("```"):
            result = result[:-3].strip()

        return result

    except Exception as e:
        print(f"Deck AI code update error: {e}", flush=True)
        return original_code  # Return unchanged code on error