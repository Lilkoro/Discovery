import asyncio
import os
from langchain.prompts import PromptTemplate
import yaml
from discovery import Discovery
from openai import AsyncOpenAI
from dotenv import load_dotenv
from typing import List

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import ExternalTermination, TextMentionTermination
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.ui import Console
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_core.model_context import UnboundedChatCompletionContext
from autogen_core.tools import FunctionTool
from autogen_core.models import ModelFamily
from autogen_core.models import AssistantMessage, LLMMessage, ModelFamily
from autogen_ext.models.ollama import OllamaChatCompletionClient


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
        self.bot_status = "Not acquired"
        self.load_tool()
        self.load_agents()
    
    def deepseek_client(self, model_name: str = "deepseek-reasoner") -> OpenAIChatCompletionClient:
        """Creates an OpenAIChatCompletionClient configured for DeepSeek models."""
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
        # Load Google API Key
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set. Please set it to use Gemini.")
    
        model_info = {
            "vision": True,
            "function_calling": True,
            "json_output": True,
            "structured_output": False,
            "multiple_system_messages": True,
            "family": ModelFamily.ANY
        }

        self.model_client = OpenAIChatCompletionClient(
            model="gemini-2.5-flash-lite",
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            model_info=model_info
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
            description="An agent that formulates tasks for goal achievement based on the Minecraft Bot's status",
            system_message=f"""
            You are an advanced AI agent highly knowledgeable in Minecraft, and an agent that formulates **verifiable tasks** for achieving the ultimate goal.
            Your primary role is to analyze the ultimate goal set by the user, the current status of the Minecraft Bot (**information from `BotInformationAgent`**), and **past execution history**, and to propose a **concrete and executable single task through a step-by-step thought process** aimed at achieving the goal.

            **Task Formulation Thought Process (Mandatory):**
            Before making a proposal, you must go through the following thought process and explicitly describe its contents.

            1.  **Current Situation Analysis:**
                *   **Query `BotInformationAgent` to summarize the latest Bot status (position, health, hunger level, time, key items in inventory, important blocks and entities in the vicinity, and visual information if necessary).**
                Current Bot Status (If not acquired, please request the latest Status from `BotInformationAgent`):
                    {self.bot_status}
                *   Clarify what is currently lacking and what kind of challenges exist towards achieving the ultimate goal.
            2.  **Goal Decomposition and Strategy:**
                *   Decompose the ultimate goal into smaller, achievable subgoals (if already decomposed, identify the next subgoal).
                *   Consider several possible strategies or approaches to achieve the current subgoal (e.g., gather necessary materials, move to a specific location, create a specific tool).
                *   Considering the risks and prerequisites (necessary skills, tools, materials, etc.) of each strategy, select the strategy deemed most efficient and safe.
            3.  **Concrete Task Determination:**
                *   Based on the selected strategy, determine the **single concrete action** to be executed next.
                *   Briefly state the grounds for why that action was judged optimal at this point.
            4.  **Definition of Success Conditions:**
                *   Set clear and **verifiable** success conditions that can objectively judge the determined concrete task as **completed**. Success conditions must be something that `TaskCompletionAgent` can judge from the Bot's status or execution results.

            **Handling Task Stagnation:**
            - **Judgment of Stagnation:** If repeated failures or lack of progress in the same task are confirmed from the execution history in the "Current Situation Analysis" of the thought process, it is judged to be **stagnant**.
            - **Strategy Review:** In the "Goal Decomposition and Strategy" of the thought process, recognize stagnation and, instead of simply repeating the same task, consider **fundamentally different approaches or strategies**.
            - **Generation of Alternatives:** To break the stagnation, consider the following alternatives and propose them as concrete tasks:
                - **Task Decomposition:** Decompose the problematic task into smaller steps.
                - **Different Approach:** Try different skills, low-level APIs, locations, materials, etc.
                - **Additional Information Gathering:** Obtain more detailed information with `BotInformationAgent`.
                - **Debugging Suggestion:** If code errors are highly likely, suggest a request for investigation to `CodeDebuggerAgent`.

            **Output Format:**
            When making a proposal, you **must** output the **thought process** and **proposed task** in the following format.

            ```
            **Thought Process:**
            1.  **Current Situation Analysis:**
                *   Bot Status: [Summary of information obtained from `BotInformationAgent`]
                *   Previous Task Result: [Here, the result and impact of the previous task]
                *   Challenges: [Here, the current challenges towards achieving the goal]
            2.  **Goal Decomposition and Strategy:**
                *   Current Subgoal: [The subgoal trying to be achieved]
                *   Strategies Considered: [Strategy A, Strategy B, etc.]
                *   Selected Strategy: [The strategy judged most appropriate]
                *   Reason for Selection: [Why that strategy was chosen]
            3.  **Concrete Task Determination:**
                *   Specific Action: [A single action to be performed next]
                *   Rationale for Action: [Why this action is optimal]
            4.  **Definition of Success Conditions:**
                *   Success Conditions: [Specific and verifiable success conditions]

            **Proposed Task:**
            [Describe the specific task content here. Example: Collect 3 oak logs]

            **Success Conditions:**
            [Describe verifiable success conditions specifically here. Same content as defined in the thought process. Example: The Bot's inventory contains 3 or more `oak_log`s.]
            ```

            **Team Members:**
            - **`BotInformationAgent`**: Provides the current state and visual information of the Minecraft Bot.
            - `ProcessReviewerAgent`: Reviews the feasibility of the task.
            - `CodeExecutionAgent`: Generates and executes code, and also provides skill information.
            - `CodeDebuggerAgent`: Provides debugging assistance in case of code execution errors, and also checks execution history and skill code.
            - `TaskCompletionAgent`: Determines task completion.

            **Notes:**
            - You only formulate tasks and define success conditions through a thought process.
            - Execution, code generation, and completion determination are performed by other agents.
            - Please describe the success conditions in a format that `TaskCompletionAgent` can verify.
            - Please provide the answer in Japanese.
            """
        )
        self.ProcessReviewerAgent = AssistantAgent(
            name="ProcessReviewerAgent",
            tools=[self.get_skill_summary_tool],
            model_client=self.model_client,
            description="An agent that reviews whether a proposed task is executable given the available functions and the current state of the Bot",
            system_message="""
            You are an agent that evaluates whether a proposed task is executable by the MineCraftBot.
            You receive tasks proposed by other agents (primarily `MissionPlannerAgent`) and evaluate whether those tasks are executable from the perspective of the Bot's capabilities (available functions) and current situation.

            **Available Tools:**
            - `get_skill_summary_tool`: Retrieves a list of names and brief descriptions of available high-level skills (functions).

            **Evaluation Points:**
            1.  **Skill Check:** Consider what skills might be needed to execute the proposed task. If there are any unclear points or you want to check if a specific skill exists, **first use `get_skill_summary_tool` to check the summary of available skills.**
            2.  **Specificity:** Is the proposed task specific? Is it achievable with existing skills (including confirmed skills)?
            3.  **Prerequisites:** Are the items necessary for task execution (materials, tools, etc.) present in the Bot's inventory, or can they be obtained from the current situation? (**If necessary, please request `BotInformationAgent` to check the state, including the inventory**)
            4.  **Feasibility:** Are there any ambiguous points, or aspects that are not feasible with the Bot's current capabilities, inventory, and confirmed skill set?

            **Judgment Result:**
            - **Executable:** If you determine that the task is specific, the necessary skills exist, and the prerequisites are met, state that fact and briefly mention which skills could be used.
            - **Not Executable:** If you determine that the proposed task is not executable due to reasons such as being too ambiguous, missing necessary skills, or unfulfilled prerequisites, you will specifically propose **concrete reasons** (e.g., "The skill 'collect_specific_flower' did not exist." or "Iron is insufficient in the inventory.") and **improvement suggestions on how to modify the task to make it executable.**

            You are responsible for reviewing proposed tasks and suggesting improvements. **You do not generate or execute concrete code.** (That role is performed by the CodeExecutionAgent)
            """
        )
        self.TaskCompletionAgent = AssistantAgent(
            name="TaskCompletionAgent",
            model_client=self.model_client,
            description="An agent that confirms task completion based on the execution result of Python code",
            system_message="""
            You are an AI agent that ultimately determines whether the executed task has met the **originally defined success conditions**.

            Your main roles are as follows:
            1.  **Understanding Success Conditions:** Accurately grasp the conversation history, especially the "**Success Conditions**" presented by `MissionPlannerAgent`.
            2.  **Checking Execution Results:** Check the code execution results reported by `CodeExecutionAgent` (success/failure, standard output, standard error output).
            3.  **Obtaining Latest State:** **Always query `BotInformationAgent` to obtain the Bot's latest state (inventory, health, position, and other information necessary for evaluating success conditions).** This step is essential because the Bot's state is highly likely to have changed after code execution.
            4.  **Matching with Success Conditions:** Match the obtained **latest Bot state** and the **execution results** from `CodeExecutionAgent` against the **originally defined success conditions**.
            5.  **Completion Judgment:** Based on the matching results, judge whether the task is complete.
                 *   **Success:** If you judge that the success conditions have been met, report that fact clearly, and **be sure to include the phrase "Task complete" at the end of the report to conclude the conversation.**
                 *   **Failure:** If you judge that the success conditions have not been met, explain the reason specifically (which conditions were not met, what the current state is).
            6.  **Next Action Proposal (on failure):** If the task fails, propose the next action to other agents (e.g., request `MissionPlannerAgent` to revise the plan, request `CodeDebuggerAgent` to check for errors, request `CodeExecutionAgent` to generate code using a different approach).

            You have an important role in making the final judgment of "completed (success conditions met)" or "uncompleted (success conditions not met)". **Before making a judgment, always call `BotInformationAgent` to confirm the latest status**, and always evaluate based on the **success conditions** defined by `MissionPlannerAgent`.
            """
        )
        self.CodeExecutionAgent = AssistantAgent(
            name="CodeExecutionAgent",
            tools=[ # Add necessary tools
                self.execute_python_code_tool, 
                self.get_skill_summary_tool, 
                self.get_skills_list_tool
            ],
            model_client=self.model_client,
            description="An agent that generates Python code to execute the proposed task, executes it immediately, and reports the results",
            system_message="""
            You are a specialized AI agent that generates Python code to automate Minecraft Bot operations, and **executes it immediately to objectively report the results**.
            Your role is to analyze proposed tasks and action steps, combine available methods from `skills` and `bot` objects to generate Python code, execute it with the `execute_python_code` tool, and report the results.

            **Execution Context:**
            - In the provided code execution environment, `skills` and `bot` variables are globally accessible. You can use them directly in your code.
            - `skills`: High-level predefined skills (an instance of the `Skills` class).
            - `bot`: A Mineflayer Bot instance. Low-level operations are possible (e.g., `bot.chat()`, `bot.dig()`, `bot.entity.position`). `await` is not necessary when calling `bot`.

            **Code Generation and Execution Rules:**
            1.  **Skill Confirmation (Important):** **Before** generating code, **always** use `get_skill_summary_tool` or `get_skills_list_tool` to check the available high-level skills (methods of the `skills` object). This prevents errors from calling non-existent functions by selecting the latest and most optimal skills.
                - `get_skill_summary_tool`: Used to quickly check a list of skill names and brief descriptions.
                - `get_skills_list_tool`: Used to check detailed descriptions and usage (arguments, return values, etc.) of each skill.
            2.  **API Selection:** Depending on the task, appropriately use high-level functions from `skills` and low-level APIs from `bot`.
            3.  **Information Reference:** If you want to check the internal implementation of a specific skill (e.g., low-level API usage), **ask `CodeDebuggerAgent`** to use `get_skill_code_tool` for you. (You cannot call this tool directly)
            4.  **Prohibitions:**
                - **Do not `from` or `import` external libraries.**
                - **Do not define functions using `async def` or `def`.**
                - Do not use functions or libraries unrelated to the provided API.
                - To prevent infinite loops, the use of `while True` is prohibited.
            5.  **Completion Report:** **Always include** code at the **end of the code** that `print`s information that will serve as a basis for judging whether the task has been achieved. (e.g., `print(f"Collected {target_count} {item_name}.")`)
            6.  **Code Execution:** Execute the generated code directly with the `execute_python_code` tool, without using Markdown code blocks.
            
            **Result Report:**
            - **Objectively report** the execution result of the `execute_python_code` tool (success/failure, standard output, standard error output, error information, traceback) **as is**.
            - **Do not make judgments about task completion/incompletion or interpret results.** That judgment is handled by `TaskCompletionAgent`.

            **Error Handling:**
            - If execution fails (`success: False`), report the error information (error message, traceback, standard error output before the error) **in detail and accurately**.
            - Afterwards, propose requesting `CodeDebuggerAgent` to analyze or `MissionPlannerAgent` to revise the plan.

            **Available Main Skills (`skills` object) - Example for Confirmation:**
            (Always confirm with `get_skill_summary_tool` or `get_skills_list_tool` before use)
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
            tools=[ # Add necessary tools
                self.get_code_execution_history_tool,
                self.get_skills_list_tool,
                self.get_skill_code_tool
            ],
            model_client=self.model_client,
            description="Analyzes code execution errors, and proposes debugging and修正案 while checking execution history and skill information with tools",
            system_message="""
            You are an AI assistant with **advanced analytical capabilities** that helps debug and solve problems with Python code.
            If `CodeExecutionAgent` reports an error during Python code execution, follow these steps to lead the debugging process.

            **Available Tools:**
            - `get_code_execution_history_tool`: Retrieves the last 5 code execution histories (code, results, errors).
            - `get_skills_list_tool`: Retrieves detailed information about available skills (high-level functions). By passing a list of skill names as an argument, information for only specific skills can be obtained.
            - `get_skill_code_tool`: Retrieves the source code (low-level API usage examples) corresponding to **a list of** specified skill names.

            **Important:** Even if an error occurs, the code before the error location might have been executed. This could result in the task goal being unintentionally achieved, or being close to completion.

            **Action Steps:**
            1.  **Suggest Current Status Check:** First, point out that even though an error occurred, the current status of the Bot needs to be checked. Specifically, ask `CodeExecutionAgent` to use **`BotInformationAgent`** to check the Bot's current state (inventory, position, surrounding conditions, etc.) and compare it with the original task goal (set by `MissionPlannerAgent`).
            2.  **Delegate Completion Judgment:** Next, based on the results of the status check, clearly suggest that **the final judgment on whether the task is complete should be delegated to `TaskCompletionAgent`**. You will not make the completion judgment.
            3.  **Necessity of Debugging:** Suggest proceeding to the following debugging process only if `TaskCompletionAgent` determines the task is incomplete.
            4.  **Error Analysis (When Task is Incomplete):** This is where the real debugging begins. Maximize your advanced analytical skills and available tools.
                *   **Root Cause Exploration:** Carefully read and interpret the provided error messages and tracebacks.
                *   **Utilizing Execution History:** **Always use `get_code_execution_history_tool` to** check the recent execution history and analyze previous trial-and-error attempts, especially whether similar errors are repeating, or what successful steps preceded the error.
                *   **Utilizing Skill Information:** If necessary, **use `get_skills_list_tool` or `get_skill_code_tool` to** check the detailed specifications, arguments, and internal implementation (low-level API usage examples) of skills that might be related to the error. When using `get_skill_code_tool`, pass **a list of** skill names you want to investigate as an argument. Analyze for API misuse or unexpected behavior.
                *   **Step-by-Step Thinking:** **Integratively analyze** the code location where the error occurred, related data flow, Bot state transitions, information obtained from tools, etc., to identify the core of the problem.
            5.  **Propose Fixes/Investigation Steps (When Task is Incomplete):** Based on the analysis, propose high-quality fixes and investigation steps.
                *   **Fundamental Solution:** Prioritize proposing **more robust and fundamental solutions** that address the identified root cause, rather than merely circumventing the error.
                *   **Correction/Investigation Instructions:** Clearly present concrete code fix proposals or investigation steps to try (e.g., code to test specific conditional branches, code to use a different skill, code to add `print` statements around the error location to check the values or states of specific variables), and **instruct `CodeExecutionAgent` to execute them**. The proposed fixes should be in a format easily interpretable by `CodeExecutionAgent`.
                *   **Multiple Proposals and Rationale:** If possible, **present multiple correction/investigation approaches, clearly explaining their respective pros and cons, and the rationale for why you believe they would be effective**.

            Note:
            - You should focus on analysis and instructions, and ask other agents to directly execute code or check Bot status.
            - Avoid giving instructions that would result in more than 3 loops for code suggestions.

            Your role is not to blindly debug when an error occurs, but to first consider the possibility of achieving the goal, prompt the appropriate agent for a decision, and then, if necessary, lead **high-quality debugging in cooperation with `CodeExecutionAgent`, based on deep analysis and logical reasoning utilizing available tools**.
            """
        )
    async def main(self,message:str) -> None:
        selector_prompt = """As an excellent leader, please select an agent to perform the task.

        {roles}

        Current conversation context:
        {history}

        Read the conversation above and select the agent to perform the next task from {participants}.
        Ensure that the planner agent has assigned the task before other agents start their work.
        Select only one agent.
        """
        termination = TextMentionTermination("Task complete")
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
    
    def load_prompt_template(self, prompt_name: str) -> PromptTemplate:
        """Reads the YAML file with the specified prompt name from the prompts directory and returns a PromptTemplate"""
        prompt_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), self.prompt_file_dir)
        file_path = os.path.join(prompt_dir, f"{prompt_name}.yaml")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            # Check if the necessary keys exist in the YAML file
            if not isinstance(data, dict) or "template" not in data or "input_variables" not in data:
                raise ValueError(f"YAML file '{file_path}' is malformed, or the 'template' or 'input_variables' keys are missing.")

            # Check that input_variables is a list (more strict check)
            if not isinstance(data["input_variables"], list):
                 raise ValueError(f"The 'input_variables' in YAML file '{file_path}' must be a list.")

            return PromptTemplate(
                template=data["template"],
                input_variables=data["input_variables"]
            )
        except Exception as e:
            print(f"An unexpected error occurred while loading prompt '{prompt_name}': {e}")
            raise
    
    # ------- Tool -------
    def load_tool(self) -> None:
        self.get_bot_status_tool = FunctionTool(
            self.get_bot_status,
            description="This tool retrieves the state of the MineCraftBot. It returns the BOT's current location, biome, health, hunger, time, nearby surrounding block information, surrounding entity information, and inventory information in dictionary format."
        )
        self.capture_bot_view_tool = FunctionTool(
            self.capture_bot_view,
            description="This tool obtains information about the MineCraftBot's field of view after facing a specified direction. It returns BOT's viewpoint information in YAML format. The direction (e.g., 'north', 'east', 'up') can be specified with the `direction` argument. It can retrieve information including distant scenery."
        )
        self.get_skills_list_tool = FunctionTool(
            self.get_skills_list,
            description="Retrieves **detailed information** about available high-level skills (methods of the `skills` object). For each skill, it provides **a complete signature, detailed description, and comprehensive usage instructions including arguments and return values**. By specifying the `skill_names` argument (a list of strings), information for only a specific set of skills can be obtained. If not specified, it returns all available skills."
        )
        self.get_skill_code_tool = FunctionTool(
            self._get_skill_code_wrapper,
            description="This tool can retrieve the source code (excluding docstrings) corresponding to **a list of** specified MineCraftBot skill function names (`skill_names`: list[str]). Use it when you want to check the detailed behavior of a skill function or how to use low-level APIs."
        )
        # Add the execute_python_code tool definition
        self.execute_python_code_tool = FunctionTool(
            self._execute_python_code_wrapper,
            description="Executes the specified Python code string. Used when executing code generated by CodeExecutionAgent. Pass the Python code you want to execute as a string argument."
        )
        # Add the new skill summary tool definition
        self.get_skill_summary_tool = FunctionTool(
            self._get_skill_summary_wrapper,
            description="Retrieves a **concise overview** of available high-level skills (methods of the `skills` object). For each skill, it lists only its **name and a short (first-line) description**. By specifying the `skill_names` argument (a list of strings), an overview of only a specific set of skills can be obtained. If not specified, it returns an overview of all available skills. Use this when you want to **quickly grasp the overall capabilities** of the Bot or find relevant skill candidates before requesting detailed information with `get_skills_list_tool`."
        )
        # Add the new execution history tool definition
        self.get_code_execution_history_tool = FunctionTool(
            self._get_code_execution_history_wrapper,
            description="Retrieves the last 5 code execution histories (executed code, success/failure, output, errors) in new order. Useful for debugging and reviewing plans."
        )
    async def get_skills_list(self) -> str:
        """Get information about functions available in the Skills class and return it as an English string in a format easily readable by LLM."""
        # If skill_names is not specified, pass None to discovery.get_skills_list.
        # (It is assumed that discovery is modified to return all skills if None is passed. If not, call something like discovery.get_all_skill_names()).
        # Currently, discovery.py returns an empty list if None is passed, so here we will not pass None, intending to get all skills by not passing an argument.
        # Check if there's a method in discovery to get all skill names. If not, implement it or get all methods here.
        # → It seems better to use inspect to get all method names here and pass them to discovery.
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
                usage # Including Args, Returns, etc.
            ]
            output_parts.append("\n".join(skill_info))

        # Separate each skill information with two empty lines
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
        """This is a wrapper for discovery.get_skill_code. It returns a string formatted for LLM."""
        print(f"\033[34mTool:GetSkillCode called for skills: {skill_names}\033[0m")
        results = await self.discovery.get_skill_code(skill_names) # Pass the list
        
        output_parts = []
        for skill_name, result in results.items():
            if result.get("success", False):
                code = result.get("code", "") # Use 'code' key instead of 'message'
                output_parts.append(f"Source code for skill '{skill_name}':\n```python\n{code}\n```")
            else:
                error_message = result.get("message", "Unknown error")
                output_parts.append(f"Error getting source code for skill '{skill_name}': {error_message}")
        
        # Separate each result with two empty lines
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
        Face the specified direction, then take a screenshot of Prismarine Viewer,
        analyze its content with GPT-4o, and return it as a YAML-formatted string.

        Args:
            direction (str, optional): The direction to face before taking a screenshot. (e.g.:'north', 'south', 'east', 'west', 'up', 'down')
            attention_hint (str, optional): A string describing points to pay special attention to during analysis. (e.g.:'surrounding scenery', 'MOB', 'threat information')

        Returns:
            str A YAML-formatted string representing the image content. "None" on error.
        """
        print(f"\033[34mTool:CaptureBotView was called (Direction: {direction or 'current'}, Hint: {attention_hint or 'None'})\033[0m")

        # --- Delegate screenshot acquisition process to Discovery (pass direction) ---
        base64_image = await self.discovery.get_screenshot_base64(direction=direction)
        if base64_image is None:
            print("Error: Failed to capture screenshot.")
            return "None" # Return a string indicating an error
        # --- End of changes ---

        # Initialize OpenAI client
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        

        try:
            data_url = f"data:image/png;base64,{base64_image}"

            prompt = "This is a screenshot of the Minecraft game. Analyze the image content in detail and describe important objects, block types, MOBs, threat information, and any other information obtained from the view in a hierarchical YAML format."
            # --- Restore logic to add attention_hint to the prompt ---
            if attention_hint is not None:
                prompt += f"\nSpecifically, please describe [{attention_hint}] in detail."
            prompt += "\nNote: The acquired view information is from an emulator's viewpoint, so weather and time are not reflected. Also, some entity textures may be buggy and appear purple."
            # --- End of restoration ---

            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": data_url},
                            },
                        ],
                    }
                ],
                max_tokens=1500, # Secure enough tokens for YAML output
            )
            yaml_output = response.choices[0].message.content
            # If YAML output is enclosed in ```yaml ... ```, extract only the content
            if yaml_output.startswith("```yaml\\n"):
                yaml_output = yaml_output[len("```yaml\\n"):]
            if yaml_output.endswith("\\n```"):
                yaml_output = yaml_output[:-len("\\n```")]
            print("\033[34mScreenshot content analyzed by GPT-4o and described in YAML format.\033[0m")
            return yaml_output.strip() # Remove leading/trailing whitespace

        except Exception as e:
            print(f"An error occurred during screenshot acquisition or GPT-4o API call: {e}")
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
        
        
