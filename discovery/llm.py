import os
import openai
import google.generativeai as genai
from typing import Literal, Optional, List, Dict, Union
from langchain.memory import ConversationBufferMemory
import json
import traceback
import uuid # Required for generating Gemini tool call IDs

class LLMClient:
    """
    A client class to interact with different Large Language Models (LLMs)
    like OpenAI and Gemini, with conversation memory and tool/function calling support.
    """

    def __init__(self, openai_api_key: Optional[str] = None, google_api_key: Optional[str] = None):
        """
        Initializes the LLMClient and the conversation memory.

        Args:
            openai_api_key: OpenAI API key. Defaults to OS environment variable 'OPENAI_API_KEY'.
            google_api_key: Google API key. Defaults to OS environment variable 'GOOGLE_API_KEY'.
        """
        self._openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self._google_api_key = google_api_key or os.getenv("GOOGLE_API_KEY")

        if self._openai_api_key:
            openai.api_key = self._openai_api_key
        if self._google_api_key:
            genai.configure(api_key=self._google_api_key)

        # Initialize conversation memory
        self.memory = ConversationBufferMemory(return_messages=True)

    def _call_openai(self, messages: List[Dict], model: str, tools: Optional[List[Dict]]) -> Dict[str, Union[str, List[Dict], None]]:
        """ Internal method to call OpenAI API """
        if not self._openai_api_key:
            raise ValueError("OpenAI API key is not configured.")
        try:
            client = openai.OpenAI(api_key=self._openai_api_key)
            completion_args = {
                "model": model,
                "messages": messages,
            }
            if tools:
                completion_args["tools"] = tools
                completion_args["tool_choice"] = "auto"

            response = client.chat.completions.create(**completion_args)

            message = response.choices[0].message
            response_content = message.content
            response_tool_calls = None
            if message.tool_calls:
                response_tool_calls = [
                    {
                        'id': tc.id,
                        'type': tc.type,
                        'function': {'name': tc.function.name, 'arguments': tc.function.arguments}
                     } for tc in message.tool_calls
                ]
            return {'content': response_content, 'tool_calls': response_tool_calls}
        except Exception as e:
            print(f"Error calling OpenAI API: {e}")
            raise # Re-raise error to be handled by get_response

    def _call_gemini(self, full_prompt: str, model: str, tools: Optional[List[Dict]], thinking_budget: Optional[int]) -> Dict[str, Union[str, List[Dict], None]]:
        """ Internal method to call Gemini API """
        if not self._google_api_key:
            raise ValueError("Google API key is not configured.")
        try:
            gen_model = genai.GenerativeModel(model)

            generation_config = None
            if thinking_budget is not None:
                if not isinstance(thinking_budget, int) or thinking_budget < 0:
                     raise ValueError("thinking_budget must be a non-negative integer.")
                from google.generativeai import types
                generation_config = types.GenerationConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=thinking_budget)
                )

            gemini_response = gen_model.generate_content(
                full_prompt,
                generation_config=generation_config,
                tools=tools
            )

            response_content = None
            response_tool_calls = None
            candidate = gemini_response.candidates[0]
            if candidate.content and candidate.content.parts:
                text_parts = []
                tool_call_parts = []
                for part in candidate.content.parts:
                    if hasattr(part, 'text') and part.text:
                        text_parts.append(part.text)
                    elif hasattr(part, 'function_call') and part.function_call:
                        fc = part.function_call
                        tool_call_id = f"call_{uuid.uuid4()}"
                        tool_call_parts.append({
                            'id': tool_call_id,
                            'type': 'function',
                            'function': {
                                'name': fc.name,
                                'arguments': json.dumps(dict(fc.args)) if fc.args else "{}" # Convert to JSON string
                            }
                        })
                if text_parts:
                    response_content = "\n".join(text_parts)
                if tool_call_parts:
                    response_tool_calls = tool_call_parts

            return {'content': response_content, 'tool_calls': response_tool_calls}
        except Exception as e:
            print(f"Error calling Google Generative AI API: {e}")
            raise

    def get_response(
        self,
        system_prompt: str,
        user_prompt: str,
        service: Literal["openai", "gemini"],
        model: str,
        thinking_budget: Optional[int] = None,
        save_memory: bool = False,
        use_memory: bool = False,
        tools: Optional[List[Dict]] = None,
    ) -> Dict[str, Union[str, List[Dict], None]]:
        """
        Retrieves a response from the specified LLM service and model. Supports conversation memory and tool/Function Calling.
        Internally uses service-specific calling methods (_call_openai, _call_gemini).

        Args:
            system_prompt: System prompt to control the model's behavior.
            user_prompt: The user's query or instruction.
            service: LLM service to use ('openai' or 'gemini').
            model: Specific model name to use (e.g. 'gpt-4', 'gemini-pro').
            thinking_budget: Optional token budget for Gemini's thinking process.
                             Only applies to 'gemini' service.
                             Defaults to None (model's default behavior).
                             Set to 0 to disable thinking.
            save_memory: If True, saves text response to memory (not saved during tool calls).
            use_memory: If True, includes past conversation history in the prompt.
            tools: List of tool/function definitions provided to the LLM (OpenAI/Gemini format).

        Returns:
            A dictionary with the following keys:
            - 'content': Text response generated by the model (may be None during tool calls).
            - 'tool_calls': List of tool calls requested by the LLM (None if no tool calls).
                          Unified to OpenAI format ({'id': str, 'type': 'function', 'function': {'name': str, 'arguments': str}}).

        Raises:
            ValueError: If service is unsupported, API key is not configured,
                      or thinking_budget is invalid.
            Exception: Errors during API call.
        """
        history_messages: List[Dict[str, str]] = []
        history_text: str = ""

        if use_memory:
            # Retrieve past conversation history from memory
            # For ConversationBufferMemory(return_messages=True), .chat_memory.messages contains a list of BaseMessages
            # Convert this to a format usable by OpenAI/Gemini
            loaded_memory = self.memory.load_memory_variables({})
            # loaded_memory['history'] is a list of BaseMessages
            base_messages = loaded_memory.get('history', [])

            # Create message list in OpenAI format
            for msg in base_messages:
                if hasattr(msg, 'content'): # HumanMessage, AIMessage, etc.
                   role = "user" if msg.type == "human" else "assistant"
                   history_messages.append({"role": role, "content": msg.content})

            # Create text history in Gemini format (simple string concatenation)
            history_text = "\n".join([f"{'User' if msg.type == 'human' else 'AI'}: {msg.content}" for msg in base_messages])


        response_data = None
        try:
            if service == "openai":
                # Create message list for OpenAI
                messages = [{"role": "system", "content": system_prompt}]
                if use_memory:
                    messages.extend(history_messages)
                messages.append({"role": "user", "content": user_prompt})
                # OpenAI API call
                response_data = self._call_openai(messages=messages, model=model, tools=tools)

            elif service == "gemini":
                # Create prompt text for Gemini
                prompt_parts = [system_prompt]
                if use_memory and history_text:
                    prompt_parts.append("\n\n--- Conversation History ---\n" + history_text)
                prompt_parts.append("\n\n--- Current Prompt ---\n" + user_prompt)
                full_prompt = "\n".join(prompt_parts)
                # Gemini API call
                response_data = self._call_gemini(full_prompt=full_prompt, model=model, tools=tools, thinking_budget=thinking_budget)

            else:
                raise ValueError(f"Unsupported service: {service}. Choose 'openai' or 'gemini'.")

            # Save to memory (only if there is a text response and no tool calls)
            response_content = response_data.get('content')
            response_tool_calls = response_data.get('tool_calls')
            if save_memory and response_content and not response_tool_calls:
                self.memory.save_context({"input": user_prompt}, {"output": response_content})

            return response_data

        except Exception as e:
             # Capture errors during API call
             print(f"Error during get_response for service '{service}': {e}")
             # Return empty response in case of error (can consider re-raising)
             return {'content': None, 'tool_calls': None}

    # Method to clear memory (optional)
    def clear_memory(self):
        """Clears the conversation memory."""
        self.memory.clear()

    # Method to read memory content
    def get_memory_string(self) -> str:
        """Returns the current conversation memory content as a formatted string."""
        loaded_memory = self.memory.load_memory_variables({})
        base_messages = loaded_memory.get('history', [])
        if not base_messages:
            return "Memory is empty."

        history_string = "--- Conversation History ---\n"
        for msg in base_messages:
            if hasattr(msg, 'content'):
                role = "User" if msg.type == "human" else "AI"
                history_string += f"{role}: {msg.content}\n"
        return history_string.strip()

    async def handle_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        """
        Processes tool calls requested by the LLM and returns the results as a list of tool role messages
        """
        tool_results = []
        if not self._google_api_key:
            print("Error: Google API key is not initialized. Cannot execute tool.")
            # Can also return a tool result indicating an error
            for call in tool_calls:
                 tool_results.append({
                     "role": "tool",
                     "tool_call_id": call['id'],
                     "content": f"Error: Google API key not initialized. Cannot execute tool {call['function']['name']}."
                 })
            return tool_results

        for call in tool_calls:
            function_name = call['function']['name']
            function_args_str = call['function']['arguments']
            tool_call_id = call['id']
            result_content = "" # Tool execution result

            print(f"\n--- Handling Tool Call ---")
            print(f"ID: {tool_call_id}")
            print(f"Function: {function_name}")
            print(f"Arguments: {function_args_str}")

            try:
                # Parse arguments as JSON
                args = json.loads(function_args_str)

                if function_name == "get_skill_full_code":
                    skill_name = args.get("skill_name")
                    if skill_name:
                        # Note: get_skill_code excludes the docstring. If needed, implement separately.
                        # get_skill_code is async, so await it
                        genai_model = genai.GenerativeModel(self._google_api_key)
                        code = await self.get_skill_code(skill_name)
                        if code:
                            result_content = f"Source code for skill '{skill_name}':\n```python\n{code}\n```"
                        else:
                            result_content = f"Error: Could not retrieve source code for skill '{skill_name}'. It might not exist or is inaccessible."
                    else:
                        result_content = "Error: Missing required argument 'skill_name' for get_skill_full_code."

                # --- Add logic for other tools here ---
                # elif function_name == "other_tool":
                #    arg1 = args.get("arg1")
                #    result = await self.some_other_async_skill(arg1) # Example
                #    result_content = f"Result of other_tool: {result}"
                # ---------------------------------

                else:
                    result_content = f"Error: Unknown tool function '{function_name}'."

            except json.JSONDecodeError:
                result_content = f"Error: Invalid JSON arguments provided for tool '{function_name}': {function_args_str}"
            except Exception as e:
                # Unexpected errors during get_skill_code or other tool execution
                result_content = f"Error executing tool '{function_name}': {e}"
                print(f"Error details: {traceback.format_exc()}") # Detailed log

            print(f"Result Content: {result_content[:200]}...") # Omit if too long
            print("--------------------------\n")

            # Create tool role message to return to LLM
            tool_results.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": result_content,
            })

        return tool_results

    async def run_interactive_loop(self):
        """Interactive loop to communicate with LLM and handle tool calls (for demo)"""
        if not self._google_api_key:
            print("Error: Google API key is not initialized. Cannot execute tool.")
            return

        # Definition of get_skill_full_code tool
        tools_definition = [
            {
                "type": "function",
                "function": {
                    "name": "get_skill_full_code",
                    "description": "Retrieves the full source code of the specified Minecraft bot skill function.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "skill_name": {
                                "type": "string",
                                "description": "Name of the skill function to retrieve source code for (e.g., 'move_to_position', 'get_inventory_counts')."
                            }
                        },
                        "required": ["skill_name"]
                    }
                }
            }
            # Add other tools here if any
        ]

        # Conversation history (initialized with system prompt)
        messages = [
            {"role": "system", "content": "You are an assistant controlling a Minecraft bot. You can use provided tools to retrieve information or execute actions as needed."}
        ]
        self.clear_memory() # New conversation session

        print("\n--- Interactive LLM Loop (Type 'quit' to exit) ---")
        while True:
            user_input = input("You: ")
            if user_input.lower() == 'quit':
                break

            messages.append({"role": "user", "content": user_input})

            try:
                # Request response from LLM (pass tool definitions)
                response_data = self.get_response(
                    system_prompt="", # Empty since it's included in history
                    user_prompt="",   # Empty since it's included in history
                    service="gemini", # Or "openai" (Choose model supporting Tool Calling)
                    model="gemini-pro",  # Model suitable for Tool Calling
                    tools=tools_definition,
                    use_memory=False, # Alternatively, could set use_memory=True and let LLMClient manage history, but using manual management here
                    # It might be cleaner design to modify get_response to accept messages array directly
                    # Currently mimicking use_memory=True behavior with messages array
                )

                # ---- Alternative implementation if get_response cannot take messages directly ----
                # Aligning with current implementation, use latest user prompt and history
                current_user_prompt = messages[-1]["content"]
                # Consider using use_memory=True to reduce manual message appending
                # self.memory.chat_memory.add_user_message(current_user_prompt) # If adding to memory manually

                response_data = self.get_response(
                     system_prompt=messages[0]["content"], # Always pass system prompt
                     user_prompt=current_user_prompt, # Latest user prompt
                     service="gemini",
                     model="gemini-pro",
                     tools=tools_definition,
                     use_memory=True, # Use LLMClient's memory
                     save_memory=False # Decide whether to manage manually in loop or set True here
                 )
                # ------------------------------------------------------------

                ai_response_content = response_data.get('content')
                tool_calls = response_data.get('tool_calls')

                # Add AI's thinking process (tool call or text response) to history
                # In OpenAI it's common to append the whole message object
                # Here simplified to appending a dict with content / tool_calls
                response_message_for_history = {"role": "assistant"}
                if tool_calls:
                    response_message_for_history["tool_calls"] = tool_calls
                if ai_response_content:
                     response_message_for_history["content"] = ai_response_content
                messages.append(response_message_for_history)


                if tool_calls:
                    print("AI: (Requesting tool use...)")
                    # Handle tool call
                    tool_results_messages = await self.handle_tool_calls(tool_calls)
                    # Add tool execution result to history
                    messages.extend(tool_results_messages)

                    # Query LLM again with tool execution result
                    # ---- Second get_response ----
                    # Use latest history (including tool results)
                    # This part would also be cleaner if get_response accepted messages directly
                    latest_tool_result_content = tool_results_messages[0]["content"] # Simplified to first result only

                    response_data_after_tool = self.get_response(
                        system_prompt=messages[0]["content"],
                        user_prompt=latest_tool_result_content, # Passing tool result as user_prompt might be iffy
                        service="gemini",
                        model="gemini-pro",
                        tools=tools_definition,
                        use_memory=True, # Continue using memory
                        save_memory=True # Save final AI response
                    )
                    # -------------------------

                    final_content = response_data_after_tool.get('content')
                    if final_content:
                        print(f"AI: {final_content}")
                        messages.append({"role": "assistant", "content": final_content})
                        # If saving final response to LLMClient memory
                        # self.memory.save_context({"input": tool_results_messages[-1]["content"]}, {"output": final_content})
                    else:
                        print("AI: (Tool execution completed, but no further text response)")
                        # Even if no response, still log in history (if needed)
                        # messages.append({"role": "assistant", "content": None})


                elif ai_response_content:
                    # If there's no tool call and a text response is present
                    print(f"AI: {ai_response_content}")
                    # Response is already appended, but if save_memory=True to save on LLMClient side
                    if self.memory: # Check if LLMClient has memory
                       self.memory.save_context({"input": user_input}, {"output": ai_response_content})


            except Exception as e:
                print(f"An error occurred during interaction: {e}")
                traceback.print_exc()
                # Consider whether to continue loop on error

        # Cleanup after loop ends
        if self._google_api_key:
            genai.disconnect()
            print("Bot disconnected from server.")


    # Modify run method to call interactive loop (existing code is commented out)
    async def run(self):
        """Main execution function - Starts interactive loop"""
        await self.run_interactive_loop()

        # --- Existing run content (commented out) ---
        # # Check server connection and summon bot
        # server_active = await self.check_server_and_join()
        # if not server_active:
        #     print("Cannot connect to server, terminating")
        #     return
        # # ... (existing status display, skill list display etc.) ...
        # # Cleanup on exit (run outside try)
        # if self.discovery:
        #     self.discovery.disconnect_bot()
        #     print("Disconnected bot from server")
        # --- End of commented out section ---


# Example Usage (Optional - illustrating tool calling)
if __name__ == '__main__':
    # Make sure to set OPENAI_API_KEY and GOOGLE_API_KEY environment variables
    # and install langchain (`pip install langchain`)
    try:
        client = LLMClient()
        client.clear_memory() # Start with fresh memory for the example

        print("--- Tool Calling Example (OpenAI) ---")
        # Dummy tool definition
        tools_definition = [
            {
                "type": "function",
                "function": {
                    "name": "get_current_weather",
                    "description": "Get the current weather in a given location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city and state, e.g., San Francisco, CA",
                            },
                            "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                        },
                        "required": ["location"],
                    },
                }
            }
        ]

        user_prompt_tool = "What's the weather like in Boston?"
        print(f"User: {user_prompt_tool}")
        tool_response = client.get_response(
            system_prompt="You are a helpful assistant that can use tools.",
            user_prompt=user_prompt_tool,
            service="openai",
            model="gpt-3.5-turbo", # Or a model that supports tool calling well
            tools=tools_definition
            # save/use_memory remains False
        )

        print(f"AI Response: {tool_response}")

        # Example of handling a tool call (in reality you execute the tool and return the result)
        if tool_response.get('tool_calls'):
            print("\nLLM requested tool calls:")
            for call in tool_response['tool_calls']:
                print(f"  ID: {call['id']}, Function: {call['function']['name']}, Arguments: {call['function']['arguments']}")
            # Here you would actually call get_current_weather(location="Boston, MA")
            # and pass the result back with tool role in next get_response call

        # Review memory content
        print("\n--- Current Memory ---")
        print(client.get_memory_string())

        # Clear memory
        client.clear_memory()
        print("\n--- Memory After Clearing ---")
        print(client.get_memory_string())


    except (ImportError, ValueError) as e:
        print(f"Error: {e}")
        print("Please ensure LangChain is installed ('pip install langchain') and API keys are set.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
