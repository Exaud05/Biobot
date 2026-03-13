# executor.py

import json
import subprocess
from pathlib import Path


def call_executor(validation_plan_path: str) -> None:
    """
    Executes the validation plan produced by Agent 2.
    """

    # Load validation plan
    with open(validation_plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    code_path = plan.get("code_path")

    # Check that generated code exists
    if not code_path or not Path(code_path).exists():
        raise FileNotFoundError(f"Generated code not found: {code_path}")

    steps = plan.get("steps", [])
    if not steps:
        raise ValueError("Validation plan contains no steps")


    for step in steps:
        step_name = step.get("name", "unnamed_step")
        command = step.get("command")

        if not command:
            raise ValueError(f"Step '{step_name}' has no command")

        try:
            subprocess.run(
                command,
                shell=True,      
                check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"\n[EXECUTOR] ❌ Step '{step_name}' failed")
            print(f"[EXECUTOR] Return code: {e.returncode}")
            raise



if __name__ == "__main__":
    # Example manual run
    validation_plan_path = "validation_plans/opentrons_ot-2_validation_plan.json"
    call_executor(validation_plan_path)
