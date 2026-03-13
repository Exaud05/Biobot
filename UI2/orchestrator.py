from agent1_informator import agent_1_discover_tools, save_agent_1_output
from UI2.agent2_code_old import agent_2_plan_validation, load_robot_profile, save_agent_2_output
from agent2bis import run_agent_2bis, save_agent_2bis_output, get_script_content
from executor import call_executor

def run_pipeline(user_request: str, generated_code_path: str):
    # 1. Agent 1
    agent1_output = agent_1_discover_tools(user_request)
    robot_profile_path = save_agent_1_output(agent1_output)

    simulation_supported = agent1_output["simulation_validation"]["supported"]
    robot_name = agent1_output["robot_platform"]

    # 2. Branch logic
    if simulation_supported:
        print("Simulation supported → running Agent 2")
        robot_profile = load_robot_profile(robot_profile_path)
        validation_plan = agent_2_plan_validation(
            robot_profile_path=robot_profile,
            generated_code_path=generated_code_path
        )
        agent2_output_path = save_agent_2_output(validation_plan)
        call_executor(agent2_output_path)
        

    else:
        print("No simulation tool → running Agent 2 bis")
        generated_script = get_script_content(generated_code_path)
        web_report = run_agent_2bis(
            robot_platform=robot_name,
            user_request=user_request,
            generated_script = generated_script
        )
        agent2bis_output = save_agent_2bis_output(web_report,robot_name)
        return agent2bis_output


if __name__ == "__main__":
    user_request = "I need a serial dilution protocol for Opentrons OT-2"
    generated_code_path = "generated_code/generated_script.py"

    result = run_pipeline(user_request, generated_code_path)
    print(result)
