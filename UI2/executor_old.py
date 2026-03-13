import json
import subprocess
import sys
import shutil
from pathlib import Path

def call_executor(validation_plan_path: str):
    """
    Automatically installs required tool (if missing) and runs the
    validation/simulation command from the plan JSON.
    Returns the stdout and stderr output.
    """
    # Load the plan JSON
    with open(validation_plan_path, "r") as f:
        plan = json.load(f)

    validation_tool = plan.get("validation_tool")
    install_required = plan.get("install_required", False)
    install_command = plan.get("install_command")
    execution_command = plan.get("execution_command")
    code_path = plan.get("code_path")

    # Ensure code file exists
    if not Path(code_path).exists():
        print(f"[ERROR] Code file not found: {code_path}")
        return {"success": False, "error": f"Code file not found: {code_path}"}

    # Check if the tool exists
    tool_found = shutil.which(validation_tool) is not None

    # Install the tool if required and missing
    if install_required and not tool_found:
        print(f"[INFO] Tool '{validation_tool}' not found. Installing...")
        try:
            subprocess.check_call(install_command.split())
            print(f"[INFO] Installation complete.")
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Failed to install {validation_tool}: {e}")
            return {"success": False, "error": f"Failed to install {validation_tool}: {e}"}
    else:
        print(f"[INFO] Tool '{validation_tool}' already installed.")

    # Run the simulation command
    print(f"[INFO] Running simulation command:\n{execution_command}\n")
    try:
        # This sends stdout/stderr directly to terminal
        subprocess.run(execution_command.split(), check=True)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Command failed with return code {e.returncode}")

if __name__ == "__main__":
    # Example usage
    validation_plan_path = "validation_plans/opentrons_ot-2_validation_plan.json"
    call_executor(validation_plan_path)