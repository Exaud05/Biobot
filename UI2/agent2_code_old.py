# agent_2.py

from typing import Dict, Any
import json
import os
from openai import OpenAI

client = OpenAI(
    api_key="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"
)

MODEL = "gpt-5"


def agent_2_plan_validation(
    robot_profile: Dict[str, Any],
    code_path: str
) -> Dict[str, Any]:
    """
    Agent 2:
    - Reads robot tooling profile (from Agent 1)
    - Reads generated code path
    - Produces an execution / validation plan following the robot tooling profile produced by Agent 1
    - Makes the link between the Agent 1 and the Agent 3
    - Does NOT run or install anything
    """

    system_prompt = """
You are Agent 2: Code Validation Planning Agent.

Your role:
- You receive:
  1. A robot tooling profile (JSON) describing available validation/simulation tools
  2. A path to a generated source code file

Your task:
- Decide HOW the code should be validated
- Select the best available tool from the profile
- Determine:
  - Whether installation is required
  - The exact command to run
  - What types of checks will be performed

Rules:
- You MUST NOT execute or install anything
- You MUST NOT generate or modify code
- You MUST NOT invent tools not present in the profile
- You MUST output exactly ONE valid JSON object
- No markdown, no explanations, no comments

OUTPUT JSON SCHEMA:

{
  "robot_platform": "",
  "code_path": "",
  "validation_tool": "",
  "install_required": true,
  "install_command": "",
  "execution_command": "",
  "checks_performed": [],
  "hardware_required": false,
  "notes": ""
}
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "robot_profile": robot_profile,
                    "code_path": code_path
                },
                indent=2
            )
        }
    ]

    response = client.responses.create(
        model=MODEL,
        input=messages
    )

    output_text = response.output_text
    return json.loads(output_text)


def load_robot_profile(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Robot profile not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_agent_2_output(agent_output: dict, directory="validation_plans"):
    os.makedirs(directory, exist_ok=True)

    robot_name = agent_output["robot_platform"].lower().replace(" ", "_")
    filename = f"{robot_name}_validation_plan.json"
    path = os.path.join(directory, filename)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(agent_output, f, indent=2)

    return path

"""
if __name__ == "__main__":
    # Example usage

    robot_profile_path = "robot_profiles/opentrons_ot_2.json"
    generated_code_path = "generated_code/generated_script.py"

    robot_profile = load_robot_profile(robot_profile_path)

    plan = agent_2_plan_validation(
        robot_profile=robot_profile,
        code_path=generated_code_path
    )

    output_path = save_agent_2_output(plan)

    print("Agent 2 validation plan saved to:", output_path)
"""