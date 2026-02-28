import asyncio
import base64
import os
import yaml
from discovery.discovery import Discovery
from dotenv import load_dotenv
from typing import List

import google.generativeai as genai
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import ExternalTermination, TextMentionTermination
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.ui import Console
from autogen_ext.models.gemini import GeminiChatCompletionClient
from autogen_core.model_context import UnboundedChatCompletionContext
from autogen_core.tools import FunctionTool
from autogen_core.models import AssistantMessage, LLMMessage, ModelFamily

class ReasoningModelContext(UnboundedChatCompletionContext):
    """A model context for reasoning models."""

    async def get_messages(self) -> List[LLMMessage]:
        messages = await super().get_messages()
        # Filter out thought field from AssistantMessage.
        messages_out: List[LLMMessage] = []
        for message in messages:
            if isinstance(message, AssistantMessage):
                message.thought = None
            messages_out.append(message)
        return messages_out

class Auto_gen:
    def __init__(self,discovery: Discovery) -> None:
        # Load environment variables from .env file
        load_dotenv()

        # Now os.getenv will work correctly if keys are in .env
        self.prompt_file_dir = "LLM/prompts"
        self.discovery = discovery
        self.bot_status = "Not retrieved"
        self.load_tool()
        self.load_agents()
    
    def deepseek_client(self, model_name: str = "deepseek-reasoner"):
        """Creates an OpenAIChatCompletionClient configured for DeepSeek models (deprecated)."""
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY environment variable is not set.")

        # Based on DeepSeek API documentation and common capabilities
        model_info = {
            "vision": False,            # Assuming standard chat model, adjust if vision model is used
            "function_calling": False,   # Supported according to DeepSeek docs
            "json_output": False,        # Supported according to DeepSeek docs (check specific model if needed)
            "structured_output": True, # Assuming not directly supported via Pydantic models in this client
            "family": ModelFamily.R1 # Add the required family field
        }

        client = OpenAIChatCompletionClient(
            model=model_name,
            api_key=api_key,
            base_url="https://api.deepseek.com", # From DeepSeek documentation
            model_info=model_info
        )
        return client
    
    def load_agents(self) -> None:
        # Gemini configuration (text + vision) using official Google API
        google_api_key = os.getenv("GOOGLE_API_KEY")
        if not google_api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set. Please configure your Gemini API key.")

        model_info = {
            "vision": True,
            "function_calling": True,
            "json_output": True,
            "structured_output": False,
            "multiple_system_messages": True,
            "family": ModelFamily.ANY,
        }

        # Use Gemini 2.5 Flash-Lite as the unified model backend for all agents.
        self.model_client = GeminiChatCompletionClient(
            model="gemini-2.5-flash-lite",
            api_key=google_api_key,
            model_info=model_info,
        )
        self.model_client_o1 = self.model_client
        self.model_client_4o = self.model_client
        self.model_client_deepseek = self.model_client
        self.model_client_o4_mini = self.model_client
        # Define the new consolidated agent
        self.BotInformationAgent = AssistantAgent(
            name="BotInformationAgent",
            tools=[self.get_bot_status_tool, self.capture_bot_view_tool], # Combine tools
            model_client=self.model_client_4o, # Use a capable model, like gpt-4o for potential image analysis
            description="An agent that retrieves and explains the Minecraft Bot's status (stats, inventory items, surroundings blocks, entities) and visual information.",
            system_message="""
            You are an agent specializing in gathering and reporting information about the Minecraft Bot's current state.

            Your primary responsibilities are:
            1.  **Retrieve Bot Status:** Use the `get_bot_status_tool` to fetch details like health, hunger, position, biome, time, inventory, nearby blocks, and entities when needed or requested.
            2.  **Capture Bot View:** Use the `capture_bot_view_tool` when visual information is required. You can specify a `direction` (e.g., 'north', 'east', 'up', 'down') and an `attention_hint` (e.g., "look for sheep", "analyze the cave entrance"). This tool returns a YAML description of the bot's view.
            3.  **Report Information:** Clearly summarize the gathered information (status and/or view) in **English**. When reporting view information from `capture_bot_view_tool`, present the YAML output directly as provided by the tool. Ensure all Minecraft item and block names remain in their original English format.
            4.  **Handle Tool Issues:** If a tool call fails or times out, report the issue and suggest that `CodeExecutionAgent` might need to execute `await skills.handle_connection_error()`.

            Available Tools:
            - `get_bot_status_tool`: Fetches the bot's numerical and environmental status.
            - `capture_bot_view_tool`: Captures and analyzes the bot's visual perspective, returning a YAML description.

            **You must always provide your answers and summaries in English.** Your goal is to provide accurate and timely information to assist other agents in their tasks.
            """
        )

        # Keep other agent definitions (MissionPlannerAgent, ProcessReviewerAgent, etc.)
        # Make sure self.bot_status update logic is handled appropriately if needed elsewhere,
        # or rely on this agent to provide the status.
        # For MissionPlannerAgent, you might adjust its prompt to explicitly ask BotInformationAgent.

        self.MissionPlannerAgent = AssistantAgent(
            name="MissionPlannerAgent",
            model_client=self.model_client,
            description="Agent that formulates tasks to achieve goals based on the Minecraft Bot's status.",
            system_message=f"""
            You are an advanced AI agent with deep knowledge of Minecraft, formulating **verifiable tasks** to achieve the ultimate goal.
            Your main role is to analyze the user's ultimate goal, the Minecraft Bot's current situation (**info from `BotInformationAgent`**), and **past execution history**, then propose a **single, concrete, and executable task based on a step-by-step thinking process** towards achieving the goal.

            **Task Planning Thinking Process (Mandatory):**
            Before proposing a task, you must go through the following thinking process and explicitly write down its contents.

            1.  **Current Status Analysis:**
                *   **Query `BotInformationAgent` to summarize the latest Bot status (position, health, hunger, time, key inventory items, important surrounding blocks/entities, visual info if needed).**
                Current Bot Status (If not retrieved, ask `BotInformationAgent` to provide the latest Status):
                    {self.bot_status}
                *   Clarify what is currently missing to achieve the ultimate goal and what the challenges are.
            2.  **Goal Decomposition and Strategy:**
                *   Break down the ultimate goal into smaller, achievable sub-goals (or identify the next sub-goal if already broken down).
                *   Consider several possible strategies to achieve the current sub-goal (e.g., gather necessary materials, move to a specific location, craft a specific tool).
                *   Evaluate the risks and prerequisites (required skills, tools, materials, etc.) of each strategy and select the one that seems most efficient and safe.
            3.  **Determination of Concrete Task:**
                *   Based on the selected strategy, determine a **single concrete action** to execute next.
                *   Briefly state the reasoning why this action is judged to be optimal at this time.
            4.  **Definition of Success Condition:**
                *   Set a clear and **verifiable** success condition to objectively judge when the determined concrete task is **completed**. The success condition must be something `TaskCompletionAgent` can judge from the Bot's status or execution results.

            **Handling Stagnation:**
            - **Identifying Stagnation:** If the "Current Status Analysis" reveals repeated failures on the same task or extremely slow progress based on execution history, judge it as **stagnant**.
            - **Revising Strategy:** In the "Goal Decomposition and Strategy" phase, acknowledge the stagnation and consider a **fundamentally different approach or strategy** rather than simply repeating the same task.
            - **Generating Alternatives:** Suggest alternatives such as:
                - **Task Decomposition:** Break the problematic task into even smaller steps.
                - **Different Approach:** Try different skills, lower-level APIs, locations, or materials.
                - **More Information Gathering:** Get more detailed info via `BotInformationAgent`.
                - **Suggesting Debugging:** If code errors are likely, suggest asking `CodeDebuggerAgent` for an investigation.

            **Output Format:**
            When proposing, you **must** output your **thinking process** and the **proposed task** in the following format.

            ```
            **Thinking Process:**
            1.  **Current Status Analysis:**
                *   Bot Status: [Summary of info from `BotInformationAgent`]
                *   Previous Task Result: [Result and impact of the previous task]
                *   Challenges: [Current challenges towards achieving the goal]
            2.  **Goal Decomposition and Strategy:**
                *   Current Sub-goal: [The sub-goal being targeted]
                *   Considered Strategies: [Strategy A, Strategy B, etc.]
                *   Selected Strategy: [The most appropriate strategy chosen]
                *   Reasoning: [Why this strategy was chosen]
            3.  **Determination of Concrete Task:**
                *   Concrete Action: [Single action to execute next]
                *   Reasoning for Action: [Why this action is optimal]
            4.  **Definition of Success Condition:**
                *   Success Condition: [Concrete and verifiable success condition]

            **Proposed Task:**
            [Concrete task description here. Example: Collect 3 oak logs]

            **Success Condition:**
            [Specific, verifiable success condition here. Same as defined in the thinking process. Example: At least 3 `oak_log` exist in the Bot's inventory.]
            ```

            **Team Members:**
            - **`BotInformationAgent`**: Provides current status and visual info.
            - `ProcessReviewerAgent`: Reviews task feasibility.
            - `CodeExecutionAgent`: Generates and executes code, and provides skill info.
            - `CodeDebuggerAgent`: Helps with debugging upon code execution errors.
            - `TaskCompletionAgent`: Judges task completion.

            **Notes:**
            - You only go through the thinking process to formulate tasks and define success conditions.
            - Execution, code generation, and completion judgment are done by other agents.
            - Write success conditions in a format that `TaskCompletionAgent` can verify.
            - **Please provide your answers only in English.**
            """
        )
        self.ProcessReviewerAgent = AssistantAgent(
            name="ProcessReviewerAgent",
            tools=[self.get_skill_summary_tool],
            model_client=self.model_client,
            description="Agent that reviews whether the proposed task is executable given available functions and current Bot status.",
            system_message="""
            You are an agent evaluating if a proposed task is executable by the Minecraft Bot.
            You receive tasks from other agents (primarily `MissionPlannerAgent`) and evaluate feasibility based on the Bot's capabilities (available functions) and current situation.

            **Available Tools:**
            - `get_skill_summary_tool`: Gets a list of available high-level skill (function) names and brief descriptions.

            **Evaluation Points:**
            1.  **Skill Check:** Consider what skills might be needed for the proposed task. If unsure or if you need to confirm specific skills exist, **first use `get_skill_summary_tool`**.
            2.  **Specificity:** Is the proposed task specific? Can it be implemented with existing skills?
            3.  **Prerequisites:** Are the items needed for the task (materials, tools, etc.) in the Bot's inventory, or obtainable given the current situation? (**Ask `BotInformationAgent` to check inventory if needed**)
            4.  **Feasibility:** Are there any ambiguities or impossible points given the current Bot capabilities, inventory, and confirmed skills?

            **Judgment Result:**
            - **Executable:** If the task is specific, required skills exist, and prerequisites are met, state this and briefly mention which skills could be used.
            - **Not Executable:** If inapplicable (too vague, skills not found, prerequisites unmet), state **specific reasons** (e.g., "Skill 'collect_specific_flower' was not found," "Not enough iron in inventory") and **propose concrete improvements on how to modify the task to make it executable**.

            Your role is to review and propose improvements. **You do not generate or execute specific code.** (That is CodeExecutionAgent's role.)
            """
        )
        self.TaskCompletionAgent = AssistantAgent(
            name="TaskCompletionAgent",
            model_client=self.model_client,
            description="Agent that verifies task completion based on Python code execution results.",
            system_message="""
            You are an AI agent making the ultimate judgment on whether an executed task has met the **initially defined success conditions**.

            Your main roles are:
            1.  **Understand Success Conditions:** Accurately grasp the "Success Conditions" presented by the `MissionPlannerAgent` from the conversation history.
            2.  **Check Execution Results:** Review the code execution results (success/failure, stdout, stderr) reported by `CodeExecutionAgent`.
            3.  **Get Latest Status:** **You MUST query `BotInformationAgent` to fetch the latest Bot status (inventory, health, position, etc.) required to evaluate the success condition.** The Bot's status likely changed after code execution, making this step mandatory.
            4.  **Compare with Conditions:** Compare the fetched **latest Bot status** and **execution results** against the **initially defined success conditions**.
            5.  **Completion Judgment:** Decide if the task is complete based on this comparison.
                 *   **Success:** If conditions are met, report this clearly. To end the conversation, you **MUST include the exact phrase "Task Completed" at the end of your report.**
                 *   **Failure:** If conditions are not met, specifically explain why (which conditions are missing, what the current status is).
            6.  **Propose Next Action (If Failed):** Suggest the next step to other agents (e.g., ask `MissionPlannerAgent` to revise the plan, ask `CodeDebuggerAgent` to check for errors, ask `CodeExecutionAgent` for a different code approach).

            You hold the critical role of issuing the final "Complete" or "Incomplete" verdict. **ALWAYS call `BotInformationAgent` to verify the latest status before judging,** and always evaluate based on the **success conditions** defined by the `MissionPlannerAgent`.
            """
        )
        self.CodeExecutionAgent = AssistantAgent(
            name="CodeExecutionAgent",
            tools=[ 
                self.execute_python_code_tool, 
                self.get_skill_summary_tool, 
                self.get_skills_list_tool
            ],
            model_client=self.model_client,
            description="Agent that generates Python code to execute proposed tasks, runs it immediately, and reports results.",
            system_message="""
            You are a specialized AI agent that generates Python code to automate Minecraft Bot actions, **executes it immediately, and objectively reports the results.**
            Your role is to analyze proposed tasks, combine available methods from the `skills` and `bot` objects to generate Python code, execute it via the `execute_python_code` tool, and report the outcome.

            **Execution Context:**
            - In the provided execution environment, `skills` and `bot` variables are globally accessible. You can use them directly in the code.
            - `skills`: High-level predefined skills (instance of the `Skills` class).
            - `bot`: Mineflayer Bot instance. Low-level operations are possible (e.g. `bot.chat()`, `bot.dig()`, `bot.entity.position`). No `await` is needed when calling `bot` methods directly unless documented.

            **Code Generation and Execution Rules:**
            1.  **Skill Check (Crucial):** **Before** generating code, you **MUST** use `get_skill_summary_tool` or `get_skills_list_tool` to check available high-level skills (methods of the `skills` object) to prevent utilizing non-existent functions.
                - `get_skill_summary_tool`: Use for a quick overview of skill names and brief descriptions.
                - `get_skills_list_tool`: Use to check detailed explanations and usage (arguments, return values).
            2.  **API Selection:** Properly balance using high-level `skills` functions and low-level `bot` APIs depending on the task.
            3.  **Reference Info:** If you want to see the internal implementation (low-level API usage) of a specific skill, **ask the `CodeDebuggerAgent`** to use `get_skill_code_tool`. (You cannot call this tool yourself).
            4.  **Prohibitions:**
                - **Do not use `from` or `import` for external libraries.**
                - **Do not define functions using `async def` or `def`.**
                - Do not use functions or libraries unrelated to the provided APIs.
                - Use of `while True` is prohibited to prevent infinite loops.
            5.  **Completion Report:** At the **very end of your code**, include a `print` statement containing information to help judge if the task was achieved (e.g. `print(f"Collected {target_count} {item_name}.")`).
            6.  **Code Execution:** Execute your generated code directly via the `execute_python_code` tool. Do not wrap it in a markdown code block inside a text message to user.
            
            **Result Reporting:**
            - **Objectively report the exact result** returned by the `execute_python_code` tool (success/failure, stdout, stderr, error info, traceback).
            - **Do not interpret the results or judge if the task is completed/incomplete.** That is `TaskCompletionAgent`'s job.

            **Handling Errors:**
            - If execution fails (`success: False`), report the error info (error message, traceback, stderr before the error occurs) **accurately and in detail**.
            - Then, suggest asking `CodeDebuggerAgent` for analysis or `MissionPlannerAgent` for a plan revision.

            **Available Main Skills (`skills` object) - Examples for Reference:**
            (You MUST check with `get_skill_summary_tool` or `get_skills_list_tool` before using)
            *   `await skills.move_to_position(x, y, z, min_distance=2)`
            *   `await skills.collect_block(block_name, num=1)`
            *   `await skills.place_block(block_name, x, y, z)`
            *   `await skills.craft_items(item_name, num=1)`
            *   `await skills.get_inventory_counts()`
            *   `await skills.get_nearest_block(block_name, max_distance=1000)`
            *   `await skills.get_bot_position()`
            *   `await skills.look_at_direction(direction)`
            *   `await skills.smelt_item(item_name, num=1)`
            *   `await skills.put_in_chest(item_name, num=-1)`
            *   `await skills.take_from_chest(item_name, num=-1)`

            **Code Example:**
            ```python
            block = await skills.get_nearest_block('oak_log')
            await skills.move_to_position(block.position.x, block.position.y, block.position.z, 0)
            await skills.collect_block('oak_log', 1)
            await skills.craft_items('oak_planks', 4)
            await skills.craft_items('crafting_table', 1)
            ```
            """
        )

        self.CodeDebuggerAgent = AssistantAgent(
            name="CodeDebuggerAgent",
            tools=[ 
                self.get_code_execution_history_tool,
                self.get_skills_list_tool,
                self.get_skill_code_tool
            ],
            model_client=self.model_client,
            description="Agent that analyzes code execution errors and proposes debugging and fixes while referencing execution history and skill info.",
            system_message="""
            You are a highly analytical AI assistant that helps debug and solve Python code issues.
            When an error during Python execution is reported by `CodeExecutionAgent`, lead the debugging process following these steps:

            **Available Tools:**
            - `get_code_execution_history_tool`: Retrieves the last 5 code execution histories (code, result, error).
            - `get_skills_list_tool`: Retrieves detailed information on available skills (high-level functions). You can pass a list of skill names to get info on specific skills.
            - `get_skill_code_tool`: Retrieves the source code (low-level API usage) for the specified **list** (`skill_names`: list[str]) of skill names.

            **Important:** Even if an error occurs, code preceding the error may have executed successfully. This means the task goal might have been unintentionally achieved, or the state might be closer to the goal.

            **Response Steps:**
            1.  **Propose Status Check:** First, point out the need to check the Bot's current status despite the error. Specifically, ask `CodeExecutionAgent` to use **`BotInformationAgent`** to check the current status (inventory, position, surroundings) and compare it against the original task goal set by `MissionPlannerAgent`.
            2.  **Delegate Completion Judgment:** Propose clearly that **the ultimate judgment on whether the task is complete should be left to `TaskCompletionAgent`** based on the status check. You do not make the completion judgment.
            3.  **Need for Debugging:** Only suggest proceeding to the debugging process below if `TaskCompletionAgent` judges the task incomplete.
            4.  **Error Analysis (If Task Incomplete):** Here begins the real debugging. Maximize your analytical skills and available tools.
                *   **Find Root Cause:** Read the provided error message and traceback carefully.
                *   **Use Execution History:** **You MUST use `get_code_execution_history_tool`** to check recent execution history, specifically looking for repeated similar errors or successful steps immediately preceding the error.
                *   **Use Skill Info:** If necessary, **use `get_skills_list_tool` or `get_skill_code_tool`** to check the detailed specs, arguments, and internal implementation of skills that might be related to the error. When using `get_skill_code_tool`, pass a **list** of skill names to investigate.
                *   **Step-by-step Thinking:** Comprehensively analyze where the error occurred, related data flows, Bot state transitions, and info from tools to pinpoint the core problem.
            5.  **Propose Fix/Investigation Steps (If Task Incomplete):** Based on the analysis, propose high-quality fixes or investigation steps.
                *   **Fundamental Resolution:** Rather than just avoiding the error, prioritize proposing a **more robust and fundamental solution** addressing the root cause.
                *   **Fix Instructions:** Explicitly provide concrete code fixes or investigation steps to try (e.g. code adding a condition, using a different skill, parsing variables with `print` near the error) and **instruct `CodeExecutionAgent` to execute it**. Your proposed fix should be easy for `CodeExecutionAgent` to interpret.
                *   **Multiple Options & Reasoning:** If possible, present **multiple fix/investigation approaches, explaining their pros/cons, and the reasoning behind why you think they are effective**.

            Caution:
            - Focus on analysis and instructions. Ask other agents to execute code or check Bot status.
            - Avoid instructions that would cause a loop of more than 3 code propositions.

            Your role is not to debug blindly when an error occurs, but to first consider the possibility of goal achievement, encourage the appropriate agent to judge, and then if necessary, **lead high-quality debugging in collaboration with `CodeExecutionAgent` based on deep analysis and logical deduction using available tools**.
            """
        )
    async def main(self,message:str) -> None:
        selector_prompt = """You are an excellent leader choosing an agent to execute a task.

        {roles}

        Current conversation context:
        {history}

        Read the conversation above and choose the agent from {participants} to execute the next task.
        Ensure the Planner Agent assigns the task before other agents start working.
        Choose exactly one agent.
        """
        termination = TextMentionTermination("Task Completed")
        team = SelectorGroupChat(
            participants= [
                self.BotInformationAgent,
                self.MissionPlannerAgent,
                self.ProcessReviewerAgent,
                self.CodeExecutionAgent,
                self.CodeDebuggerAgent,
                self.TaskCompletionAgent
            ],
            #termination_condition=termination,
            model_client=self.model_client,
            selector_prompt=selector_prompt,
            allow_repeated_speaker=True,
        )
        await Console(
            team.run_stream(task=message)
        )
    
    def load_prompt_template(self, prompt_name: str) -> str:
        """Loads a YAML file from the prompts directory and returns the PromptTemplate as a string."""
        prompt_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), self.prompt_file_dir)
        file_path = os.path.join(prompt_dir, f"{prompt_name}.yaml")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            # Check if required keys exist in the YAML file
            if not isinstance(data, dict) or "template" not in data or "input_variables" not in data:
                raise ValueError(f"YAML file '{file_path}' has an invalid format or is missing 'template' or 'input_variables' keys.")

            # Ensure input_variables is a list
            if not isinstance(data["input_variables"], list):
                 raise ValueError(f"'input_variables' in YAML file '{file_path}' must be a list.")

            return data["template"]
        except Exception as e:
            print(f"An unexpected error occurred while loading prompt '{prompt_name}': {e}")
            raise
    
    # ------- Tool -------
    def load_tool(self) -> None:
        self.get_bot_status_tool = FunctionTool(
            self.get_bot_status,
            description="Tool to get the state of the MineCraftBot. Returns a dictionary containing the BOT's current position, biome, health, hunger, time, nearby block info, nearby entity info, and inventory info."
        )
        self.capture_bot_view_tool = FunctionTool(
            self.capture_bot_view,
            description="Tool to get the visual info of the MineCraftBot after looking in a specified direction. Returns the BOT's perspective info as a YAML string. You can specify the direction with the `direction` argument (e.g. 'north', 'east', 'up'). Gets info including distant scenery."
        )
        self.get_skills_list_tool = FunctionTool(
            self.get_skills_list,
            description="Gets **detailed information** on available high-level skills (methods of the `skills` object). Provides a comprehensive usage guide including the **full signature, detailed description, arguments, and return values** for each skill. You can get info for a specific set of skills by providing the `skill_names` argument (list of strings). If not specified, returns all available skills."
        )
        self.get_skill_code_tool = FunctionTool(
            self._get_skill_code_wrapper,
            description="Tool to get the source code for a specified **list** of MineCraftBot skill functions (`skill_names`: list[str]) (excluding docstrings). Use this to check the detailed behavior or how low-level APIs are used within a skill function."
        )
        # Add the execute_python_code tool definition
        self.execute_python_code_tool = FunctionTool(
            self._execute_python_code_wrapper,
            description="Executes the provided Python code string. Used when executing code generated by CodeExecutionAgent. Pass the Python code to execute as a string argument."
        )
        # Add the new skill summary tool definition
        self.get_skill_summary_tool = FunctionTool(
            self._get_skill_summary_wrapper,
            description="Gets a **concise summary** of available high-level skills (methods of the `skills` object). Lists only the **name and a short (first line) description** for each skill. You can get a summary for a specific set of skills by providing the `skill_names` argument (list of strings). If not specified, returns a summary of all available skills. Use this to quickly grasp the **overall picture of the Bot's capabilities** or to find relevant candidate skills before requesting detailed info with `get_skills_list_tool`."
        )
        # Add the new execution history tool definition
        self.get_code_execution_history_tool = FunctionTool(
            self._get_code_execution_history_wrapper,
            description="Retrieves the last 5 code execution histories (executed code, success/failure, output, error) from newest to oldest. Useful for debugging and revising plans."
        )
    async def get_skills_list(self) -> str:
        """Get info of functions available in Skills class and return as an English string readable by LLM"""
        # If skill_names is not specified, pass None to discovery.get_skills_list
        # (Assuming discovery returns all skills if None. If not, call something like discovery.get_all_skill_names())
        # Currently, discovery.py returns an empty list if None, so to get all skills, do not pass None.
        # Check if discovery has a method to get all skill names. If not, get all methods here.
        # -> Use inspect here to get all method names and pass them to discovery.
        all_skill_names = []
        if self.discovery and self.discovery.skills:
            import inspect
            all_skill_names = [name for name, method in inspect.getmembers(self.discovery.skills, inspect.ismethod) if not name.startswith('_')]

        skills_list = await self.discovery.get_skills_list(skill_names=all_skill_names) # Pass all skill names

        if not skills_list:
            return "No available skills found or Skills object not initialized."

        output_parts = ["Available Skills:"]
        for skill in skills_list:
            skill_name = skill.get('name', 'Unknown Name')
            description = skill.get('description', 'No description provided.').strip()
            usage = skill.get('usage', '-').strip() # Get Usage

            skill_info = [
                f"{skill_name}",
                f"Description:",
                description,
                "", # Empty line between Description and Usage
                f"Usage/Details:",
                usage # Includes Args, Returns, etc.
            ]
            output_parts.append("\n".join(skill_info))

        # Separate each skill info with blank lines
        return "\n\n".join(output_parts)
    
    # Add the new wrapper method for skill summary
    async def _get_skill_summary_wrapper(self) -> str:
        """Retrieves only the names and descriptions of available skills, formatted concisely."""
        print("\033[34mTool:GetSkillSummary called\033[0m")
        # Get all skill names
        all_skill_names = []
        if self.discovery and self.discovery.skills:
            import inspect
            all_skill_names = [name for name, method in inspect.getmembers(self.discovery.skills, inspect.ismethod) if not name.startswith('_')]

        skills_list = await self.discovery.get_skills_list(skill_names=all_skill_names)

        if not skills_list:
            return "No available skills found or Skills object not initialized."

        output_lines = ["Available Skill Summaries:"]
        for skill in skills_list:
            skill_name = skill.get('name', 'Unknown Name')
            description = skill.get('description', 'No description provided.').strip()
            # Use only the first line of the description for brevity
            first_line_description = description.split('\n')[0]
            output_lines.append(f"- {skill_name}: {first_line_description}")

        return "\n".join(output_lines)
    
    async def _get_skill_code_wrapper(self, skill_names: list[str]) -> str:
        """Wrapper for discovery.get_skill_code. Returns a string formatted for the LLM."""
        print(f"\033[34mTool:GetSkillCode called for skills: {skill_names}\033[0m")
        results = await self.discovery.get_skill_code(skill_names) # Pass the list
        
        output_parts = []
        for skill_name, result in results.items():
            if result.get("success", False):
                code = result.get("code", "")
                output_parts.append(f"Source code for skill '{skill_name}':\n```python\n{code}\n```")
            else:
                error_message = result.get("message", "Unknown error")
                output_parts.append(f"Error getting source code for skill '{skill_name}': {error_message}")
        
        # Separate each result with blank lines
        return "\n\n".join(output_parts)
    
    # Add the wrapper method for execute_python_code
    async def _execute_python_code_wrapper(self, code_string: str) -> str:
        """Wrapper for discovery.execute_python_code. Executes the code and returns formatted results for the LLM."""
        print(f"\033[34mTool:ExecutePythonCode called. Executing code:\n```python\n{code_string}\n```\033[0m")
        result = await self.discovery.execute_python_code(code_string)

        output_parts = []
        if result.get("success", False):
            output_parts.append("Code execution successful.")
            output = result.get("output", "").strip()
            error_output = result.get("error_output", "").strip()
            if output:
                output_parts.append("Standard Output:")
                output_parts.append("---")
                output_parts.append(output)
                output_parts.append("---")
            if error_output:
                output_parts.append("Standard Error Output:")
                output_parts.append("---")
                output_parts.append(error_output)
                output_parts.append("---")
            if not output and not error_output:
                 output_parts.append("(No output on stdout or stderr)")

        else:
            output_parts.append("Code execution failed.")
            error_message = result.get("error", "Unknown error")
            traceback_str = result.get("traceback", "No traceback available")
            error_output_before = result.get("error_output", "").strip()
            
            output_parts.append(f"Error: {error_message}")
            output_parts.append("Traceback:")
            output_parts.append("---")
            output_parts.append(traceback_str)
            output_parts.append("---")
            if error_output_before:
                output_parts.append("Standard Error Output before exception:")
                output_parts.append("---")
                output_parts.append(error_output_before)
                output_parts.append("---")
        
        return "\n".join(output_parts)
    
    async def get_bot_status(self) -> str:
        """Retrieves the bot's status from discovery and returns it as a formatted string for the LLM."""
        print("\033[34mTool:GetBotStatus called (Retrieving BOT status)\033[0m")
        bot_status_dict = await self.discovery.get_bot_status()

        if bot_status_dict is None:
            return "Could not retrieve bot status."

        output_lines = ["Bot Status:"]
        output_lines.append(f"- Biome: {bot_status_dict.get('biome', 'N/A')}")
        # Time of Day with explanation
        time_of_day = bot_status_dict.get('time_of_day', 'N/A')
        time_explanation = "  (Dawn: 0, Noon: 6000, Dusk: 12000, Night: 13000, Midnight: 18000, Sunrise: 23000)"
        output_lines.append(f"- Time of Day: {time_of_day} / 23992")
        output_lines.append(time_explanation)
        # Health and Hunger with max values
        health = bot_status_dict.get('health', 'N/A')
        hunger = bot_status_dict.get('hunger', 'N/A')
        output_lines.append(f"- Health: {health} / 20")
        output_lines.append(f"- Hunger: {hunger} / 20")
        output_lines.append(f"- Position: {bot_status_dict.get('bot_position', 'N/A')}")

        output_lines.append("\nNearby Blocks:")
        for direction in ["front", "right", "back", "left", "center"]:
            blocks = bot_status_dict.get(f"{direction}_blocks", [])
            blocks_str = ", ".join(blocks) if blocks else "None"
            output_lines.append(f"- {direction.capitalize()}: {blocks_str}")

        output_lines.append("\nNearby Entities:")
        entities = bot_status_dict.get('nearby_entities', [])
        if entities:
            for entity in entities:
                pos = entity.get('position', {})
                pos_str = f"x={pos.get('x', '?')}, y={pos.get('y', '?')}, z={pos.get('z', '?')}"
                output_lines.append(f"- {entity.get('name', 'Unknown')} at ({pos_str})")
        else:
            output_lines.append("- None nearby")

        output_lines.append("\nInventory Items:")
        inventory = bot_status_dict.get('inventory', {})
        if inventory:
            for item, count in inventory.items():
                output_lines.append(f"- {item}: {count}")
        else:
            output_lines.append("- Empty")
        self.bot_status = "\n".join(output_lines)
        return self.bot_status

    # Add the wrapper method for capture_bot_view, including direction
    async def capture_bot_view(self, direction: str = 'north', attention_hint: str = None) -> str:
        """
        Looks in the specified direction, takes a screenshot from Prismarine Viewer,
        analyzes the content with Gemini 2.5 Flash-Lite, and returns a YAML formatted string.

        Args:
            direction (str, optional): Direction to look before screenshot. (e.g., 'north', 'south', 'east', 'west', 'up', 'down')
            attention_hint (str, optional): String describing points to pay special attention to. (e.g., 'surrounding scenery', 'MOB', 'threat info')

        Returns:
            str YAML formatted string representing image content. "None" on error.
        """
        print(f"\033[34mTool:CaptureBotView called (Direction: {direction or 'current'}, Hint: {attention_hint or 'None'})\033[0m")

        # --- Delegate screenshot fetching to Discovery (pass direction) ---
        base64_image = await self.discovery.get_screenshot_base64(direction=direction)
        if base64_image is None:
            print("Error: Failed to fetch screenshot.")
            return "None" # Return string indicating error
        # --- End of changes ---

        try:
            google_api_key = os.getenv("GOOGLE_API_KEY")
            if not google_api_key:
                print("Error: GOOGLE_API_KEY environment variable is not set. Cannot call Gemini vision model.")
                return "None"

            # Configure Gemini client (idempotent if called multiple times)
            genai.configure(api_key=google_api_key)
            vision_model = genai.GenerativeModel("gemini-2.5-flash-lite")

            prompt = "This is a Minecraft game screenshot. Analyze the image content in detail, and describe important objects, block types, MOBs, threat information, and other visual information in a hierarchical YAML format."
            if attention_hint is not None:
                prompt += f"\nPay special attention to [{attention_hint}] and describe it in detail."
            prompt += "\nNote: The visual information is obtained from an emulator's perspective, so weather and time are not reflected. Also, some entity textures might be bugged and appear purple."

            # Decode base64 image and send as inline data to Gemini (multimodal: text + image)
            try:
                image_bytes = base64.b64decode(base64_image)
            except Exception as e:
                print(f"Error: Failed to decode base64 screenshot: {e}")
                return "None"

            gemini_response = vision_model.generate_content(
                [
                    prompt,
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": image_bytes,
                        }
                    },
                ]
            )

            # Prefer the convenience .text property if available
            yaml_output = getattr(gemini_response, "text", None)
            if not yaml_output and getattr(gemini_response, "candidates", None):
                candidate = gemini_response.candidates[0]
                parts = getattr(candidate, "content", getattr(candidate, "parts", None))
                text_parts = []
                if parts and getattr(parts, "parts", None):
                    parts = parts.parts
                if parts:
                    for part in parts:
                        if hasattr(part, "text") and part.text:
                            text_parts.append(part.text)
                yaml_output = "\n".join(text_parts) if text_parts else ""

            if not yaml_output:
                print("Error: Gemini response did not contain any text.")
                return "None"
            
            # If YAML output is surrounded by ```yaml ... ```, extract the content
            if yaml_output.startswith("```yaml\n"):
                yaml_output = yaml_output[len("```yaml\n"):]
            if yaml_output.endswith("\n```"):
                yaml_output = yaml_output[:-len("\n```")]
            print("\033[34mScreenshot content analyzed with Gemini 2.5 Flash-Lite and described in YAML format.\033[0m")
            return yaml_output.strip()

        except Exception as e:
            print(f"Error occurred during screenshot capture or Gemini API call: {e}")
            import traceback
            traceback.print_exc()
            return "None"

    # Add the new wrapper method for execution history
    async def _get_code_execution_history_wrapper(self) -> str:
        """Retrieves the last 5 code execution history entries and formats them for the LLM."""
        print("\033[34mTool:GetCodeExecutionHistory called\033[0m")
        history = self.discovery.code_execution_history

        if not history:
            return "No code execution history available yet."

        output_parts = ["Code Execution History (most recent first):"]
        # Iterate in reverse to show newest first (deque stores oldest first)
        for i, entry in enumerate(reversed(history), 1):
            code = entry.get('code', 'N/A')
            result = entry.get('result', {})
            success = result.get('success', False)
            status = "Success" if success else "Failure"
            output = result.get('output', '').strip()
            error_output = result.get('error_output', '').strip()
            error_msg = result.get('error', '')
            traceback_str = result.get('traceback', '')

            entry_str = [
                f"--- Entry {i} ---",
                f"Status: {status}",
                "Executed Code:",
                "```python",
                code,
                "```"
            ]
            if output:
                entry_str.extend(["Standard Output:", "---", output, "---"])
            if error_output:
                entry_str.extend(["Standard Error Output:", "---", error_output, "---"])
            if not success:
                if error_msg:
                    entry_str.append(f"Error Message: {error_msg}")
                if traceback_str:
                    entry_str.extend(["Traceback:", "---", traceback_str, "---"])
            
            output_parts.append("\n".join(entry_str))

        # Join entries with double newline
        return "\n\n".join(output_parts)
        
        
