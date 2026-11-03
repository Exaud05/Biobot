"""
deck_visualizer.py — LLM-generated deck visualizations

Instead of hardcoded renderers, the LLM generates a complete interactive
HTML/CSS/JS visualization for any liquid handler protocol. The visualization
runs in a sandboxed iframe and communicates changes via postMessage.
"""

import json
import os
from openai import OpenAI
from config import get_api_key


VISUALIZATION_PROMPT = """You are an expert in laboratory automation AND web development.

Your job: generate a COMPLETE, self-contained HTML page that visualizes a liquid handler deck/setup for the given protocol code. The visualization runs inside an iframe.

REQUIREMENTS:

1. OUTPUT: Return ONLY the raw HTML. No markdown fences, no explanation. Just the HTML starting with <!DOCTYPE html>.

2. VISUAL DESIGN:
   - Dark theme: background #1a1a1a, text #e0e0e0, accent #00ff99
   - Use modern CSS (flexbox, grid, transitions, animations)
   - Font: system-ui, -apple-system, sans-serif
   - Rounded corners, subtle borders (#333), smooth hover effects
   - Make it look professional and clean

3. DECK VISUALIZATION:
   - Show the robot's deck layout accurately for the specific platform
   - Display all labware in their correct positions with clear labels
   - Show instruments/pipettes with their mount positions
   - Color-code different types: plates (green), tipracks (blue), reservoirs (purple), trash (red)
   - Show slot/position numbers

4. INTERACTIVITY:
   - Make labware DRAGGABLE between positions (HTML5 drag-and-drop)
   - Click a position to show details (labware name, variable, wells)
   - Double-click to change labware (show a dropdown/modal with options)
   - Editable parameter fields for volumes, counts, etc. extracted from the code
   - Visual feedback: hover highlights, drag ghosts, drop targets glow

5. PARAMETER PANEL:
   - Below the deck, show all editable parameters from the code
   - Group by category (Volumes, Counts, etc.)
   - Each parameter has a number input with the correct unit label
   - Show the variable name and any code comment as description

6. COMMUNICATION (critical):
   When the user makes ANY change, send it to the parent window:
   
   window.parent.postMessage({
     type: 'deck_change',
     change: {
       type: '<move_labware|change_labware|add_labware|remove_labware|change_instrument|change_parameter>',
       // Include relevant details for the change type:
       // For move: from_position, to_position
       // For change_labware: position, old_name, new_name
       // For change_parameter: param_name, old_value, new_value
       // For change_instrument: mount, old_name, new_name
     }
   }, '*');

7. PROTOCOL STEPS:
   - Show a summary of the protocol steps at the bottom
   - Each step shows the action, volume, and a brief description
   
8. SIZE: The page should fit within a 600px wide panel with vertical scrolling if needed.

9. FUTURE ANIMATION SUPPORT:
   - Structure the deck elements with data attributes (data-slot, data-labware, data-well) so they can be targeted for animation later
   - Each well/position should be individually addressable in the DOM

REMEMBER: Return ONLY the HTML. No explanation text. No markdown.
"""


ANIMATION_PROMPT = """You are an expert in laboratory automation AND web animation.

Given a protocol code and the current deck visualization HTML, generate an UPDATED HTML page that includes a step-by-step animation of the protocol execution.

The animation should:
1. Show the protocol steps sequentially with a play/pause button
2. Highlight the active wells/positions during each step
3. Animate liquid movement (colored dots/lines moving from source to destination)
4. Show a progress bar and step counter
5. Allow stepping forward/backward through the protocol
6. Use smooth CSS transitions and requestAnimationFrame for fluid motion

Keep all the existing deck visualization and interactivity. ADD the animation layer on top.

Return ONLY the complete HTML. No markdown, no explanation.
"""


def generate_visualization(code: str, api_key: str = None) -> str:
    """
    Ask the LLM to generate a complete interactive HTML visualization
    for the given protocol code.
    
    Returns: HTML string ready to be rendered in an iframe
    """
    key = api_key or os.environ.get("API_KEY") or get_api_key()
    client = OpenAI(api_key=key)

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=[
                {"role": "system", "content": VISUALIZATION_PROMPT},
                {"role": "user", "content": f"Generate an interactive deck visualization for this protocol:\n\n{code}"}
            ],
        )

        html = response.output_text.strip()

        # Clean markdown fences if present
        if html.startswith("```"):
            lines = html.split("\n")
            html = "\n".join(lines[1:])
        if html.endswith("```"):
            html = html[:-3].strip()
        if html.startswith("html"):
            html = html[4:].strip()

        # Ensure it starts with DOCTYPE or html tag
        if not html.lower().startswith("<!doctype") and not html.lower().startswith("<html"):
            html = "<!DOCTYPE html>\n<html><head><meta charset='UTF-8'></head><body>" + html + "</body></html>"

        return html

    except Exception as e:
        print(f"Visualization generation error: {e}", flush=True)
        # Return a minimal error page
        return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>body{{background:#1a1a1a;color:#ff4d4d;font-family:system-ui;padding:20px;}}</style>
</head><body><h3>Visualization Error</h3><p>{str(e)}</p></body></html>"""


def update_visualization(code: str, current_html: str, change: dict, api_key: str = None) -> dict:
    """
    Ask the LLM to update both the code and the visualization based on a user change.
    
    Returns: {"code": updated_code, "html": updated_html}
    """
    key = api_key or os.environ.get("API_KEY") or get_api_key()
    client = OpenAI(api_key=key)

    update_prompt = """You are an expert in laboratory automation code and web development.

The user made a change in the deck visualization. You need to:
1. Update the protocol CODE to reflect the change (keep all logic, comments, structure)
2. Update the visualization HTML to reflect the new state

CRITICAL COHERENCE RULES:
- If changing a pipette: also change the tiprack to be compatible, and adjust any volumes that exceed the new pipette's range
- If changing labware: update any well references if the format changes (96 vs 384)
- If moving labware: only change the slot/position number, keep everything else
- If changing a volume parameter: update the variable assignment in the code
- Keep ALL protocol logic (loops, conditions, steps) intact

Return a JSON object with two fields:
{"code": "<the complete updated protocol code>", "html": "<the complete updated visualization HTML>"}

Return ONLY the JSON. No markdown fences, no explanation."""

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=[
                {"role": "system", "content": update_prompt},
                {"role": "user", "content": f"Protocol code:\n```\n{code}\n```\n\nChange:\n{json.dumps(change)}\n\nReturn the updated code and HTML:"}
            ],
        )

        result = response.output_text.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[1] if "\n" in result else result[3:]
        if result.endswith("```"):
            result = result[:-3].strip()
        if result.startswith("json"):
            result = result[4:].strip()

        parsed = json.loads(result)
        return {
            "code": parsed.get("code", code),
            "html": parsed.get("html", current_html),
        }

    except Exception as e:
        print(f"Visualization update error: {e}", flush=True)
        return {"code": code, "html": current_html, "error": str(e)}


def generate_animation(code: str, current_html: str, api_key: str = None) -> str:
    """
    Ask the LLM to add protocol execution animation to the visualization.
    This is for future use — Phase 3 of the visualizer.
    """
    key = api_key or os.environ.get("API_KEY") or get_api_key()
    client = OpenAI(api_key=key)

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=[
                {"role": "system", "content": ANIMATION_PROMPT},
                {"role": "user", "content": f"Protocol code:\n```\n{code}\n```\n\nCurrent visualization:\n```html\n{current_html}\n```\n\nAdd step-by-step protocol animation:"}
            ],
        )

        html = response.output_text.strip()
        if html.startswith("```"):
            html = html.split("\n", 1)[1] if "\n" in html else html[3:]
        if html.endswith("```"):
            html = html[:-3].strip()

        return html

    except Exception as e:
        print(f"Animation generation error: {e}", flush=True)
        return current_html