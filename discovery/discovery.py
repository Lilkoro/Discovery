from javascript import require, On, Once, AsyncTask, once, off
from dotenv import load_dotenv
import os
import asyncio
from discovery.skill.skills import Skills
import webbrowser
import sys
import math
import inspect
import ast
import textwrap
import io
import contextlib
import traceback
import collections
import base64
import time
from playwright.async_api import async_playwright

class Discovery:
    def __init__(self):
        load_dotenv()
        self.load_env()
        self.mineflayer = require("mineflayer")
        require('canvas') # Added because it causes an error
        self.viewer_module = require('prismarine-viewer')

        self.bot = None
        self.mcdata = None
        self.is_connected = False
        self.code_execution_history = collections.deque(maxlen=5)
        self.viewer = None
        self.opend_browser = None
    
    def load_env(self):
        self.minecraft_host = os.getenv("MINECRAFT_HOST", "host.docker.internal")
        self.minecraft_port = os.getenv("MINECRAFT_PORT")
        self.minecraft_version = os.getenv("MINECRAFT_VERSION")
        self.web_inventory_port = os.getenv("WEB_INVENTORY_PORT")
        self.prismarine_viewer_port = os.getenv("PRISMARINE_VIEWER_PORT", 3000)

    def load_plugins(self):
        # Set Node.js module path (refer to node_modules in mineflayer directory)
        os.environ['NODE_PATH'] = "/workspaces/Voyager/mineflayer/node_modules"
        # pathfinder
        self.pathfinder = require("mineflayer-pathfinder")
        self.web_inventory = require("mineflayer-web-inventory")
        self.mineflayer_tool = require("mineflayer-tool").plugin
        self.pvp = require("mineflayer-pvp").plugin
        self.bot.loadPlugin(self.pathfinder.pathfinder)
        self.bot.loadPlugin(self.web_inventory)
        self.bot.loadPlugin(self.mineflayer_tool)
        self.bot.loadPlugin(self.pvp)
        self.movements = self.pathfinder.Movements(self.bot, self.mcdata)
        
        # Enable Web Inventory
        self.web_inventory(self.bot,{"port":self.web_inventory_port})
    
    def bot_join(self):
        """Connect the bot to the server"""
        self.is_connected = False
        # Since createBot calls sometimes timed out, set the timeout long enough
        # (According to javascript.proxy specification, providing the keyword argument `timeout` extends the JS call wait time)
        self.bot = self.mineflayer.createBot({
            "host": self.minecraft_host,
            "port": self.minecraft_port,
            "username": "BOT",
            "version": self.minecraft_version
        }, timeout=10000)  # extended to 10 seconds
        
        # Processing on spawn
        def handle_spawn(*args):
            print("\033[92mBot spawned\033[0m")
            self.is_connected = True
        
        # Error handling
        def handle_error(err, *args):
            print(f"\033[91mBot connection error: {err}\033[0m")
            self.is_connected = False
            
        # Processing on disconnect
        def handle_end(*args):
            print("\033[91m\nBOT disconnected\033[0m")
            self.is_connected = False
        
        # Open viewer (first time only)
        if self.viewer is None and self.opend_browser is None:
            try:
                print(f"Starting Prismarine Viewer on port {self.prismarine_viewer_port}...")
                self.viewer = self.viewer_module.mineflayer(self.bot, {
                    "firstPerson": True,
                    "port": int(self.prismarine_viewer_port)
                })
                # Browser auto-start is commented out (uncomment if necessary)
                webbrowser.open(f'http://localhost:{self.prismarine_viewer_port}')
                # Open Web Inventory in browser
                webbrowser.open(f'http://localhost:{self.web_inventory_port}')
                print(f"Prismarine Viewer started successfully.")
                self.opend_browser = True
            except Exception as e:
                print(f"Failed to start Prismarine Viewer: {e}")
                self.viewer = None # Set to None if failed
        else:
            print("Prismarine Viewer already running.")
        
        # Set event listeners
        self.bot.once('spawn', handle_spawn)
        self.bot.on('error', handle_error)
        self.bot.on('end', handle_end)
        self.mcdata = require("minecraft-data")(self.bot.version)
        self.load_plugins()
        print(f"enableServerListing: {self.bot.settings.enableServerListing}")
        while not self.bot.settings.enableServerListing:
            print("Connecting to server...")
            time.sleep(1)

    async def check_server_active(self, timeout=10):
        """
        Checks if the server is active
        
        Args:
            timeout (int): Timeout in seconds
            
        Returns:
            bool: True if the server is active, False otherwise
        """
        if not self.bot:
            self.bot_join()
            
        start_time = asyncio.get_event_loop().time()
        while not self.is_connected:
            # Timeout check
            if asyncio.get_event_loop().time() - start_time > timeout:
                print(f"Server connection timeout ({timeout} seconds)")
                return False
            await asyncio.sleep(0.5)
            
        return True
        
    async def check_server_and_join(self, timeout=15):
        """
        Checks server connection status and summons the bot if connected
        
        Args:
            timeout (int): Timeout in seconds for connection check
            
        Returns:
            bool: True if connection and bot summoning are successful, False otherwise
        """
        print("Checking Minecraft server connection status...")
        
        # Server connection status check
        is_active = await self.check_server_active(timeout=timeout)
        
        if is_active:
            print(f"✅ Minecraft server is running! (Version: {self.bot.version})")
            
            # Create skill instances
            self.skills = Skills(self)
            print("Bot successfully summoned")
            return True
        else:
            print("❌ Could not connect to Minecraft server")
            print("Please check if the server is running")
            return False

    def is_server_active(self):
        """
        Checks the current server connection status (not asynchronous)
        
        Returns:
            bool: True if connected, False otherwise
        """
        if not self.bot:
            return False
            
        # Check connection status
        return self.is_connected
        
    def get_server_info(self):
        """
        Retrieves basic server information
        
        Returns:
            dict: Dictionary containing server information
        """
        if not self.is_server_active():
            return {"active": False}
            
        try:
            return {
                "active": True,
                "version": self.bot.version,
                "host": self.minecraft_host,
                "port": self.minecraft_port
            }
        except Exception as e:
            print(f"Server information acquisition error: {e}")
            return {"active": False, "error": str(e)}

    def disconnect_bot(self):
        """Disconnect the bot from the server and release related resources. Even if the bot does not respond, forcefully reset its state."""
        print("Disconnecting bot and releasing resources...")

        original_bot = self.bot
        original_viewer = self.viewer

        # First, reset the Python-side state
        self.bot = None
        self.is_connected = False
        self.viewer = None

        # --- Cleanup process (Continue even if it fails) ---
        # Attempt to close the original Viewer
        try:
            # Since hasattr can also time out, include it within the try block.
            if original_viewer and hasattr(original_viewer, 'close'):
                original_viewer.close()
        except Exception as e:
            print(f"\033[31mError closing original Prismarine Viewer (ignored): {e}\033[0m")

        # Attempt to close the viewer associated with the original bot object
        try:
            # Include hasattr and property access within the try block as well.
            if original_bot:
                bot_viewer = None
                # Attempting to access the viewer property also try-except
                try:
                    if hasattr(original_bot, 'viewer'):
                         bot_viewer = original_bot.viewer
                except Exception as e_getattr:
                    print(f"\033[31mError accessing original_bot.viewer (ignored): {e_getattr}\033[0m")

                # Attempting to close the viewer object also try-except
                try:
                    if bot_viewer and hasattr(bot_viewer, 'close'):
                        bot_viewer.close()
                except Exception as e_close:
                     print(f"\033[31mError closing bot_viewer (ignored): {e_close}\033[0m")
        except Exception as e:
            # If an unexpected error occurs during access to the bot object itself, etc.
            print(f"\033[31mError during bot.viewer cleanup (ignored): {e}\033[0m")

        # Attempt to disconnect the original bot
        try:
            # Since hasattr can also time out, include it within the try block.
            if original_bot and hasattr(original_bot, 'quit'):
                 original_bot.quit()
        except Exception as e:
            print(f"\033[31mError quitting original bot instance (ignored): {e}\033[0m")

    async def reconnect_bot(self, timeout=15):
        """
        Disconnect the bot from the server and attempt to reconnect.

        Args:
            timeout (int): Timeout in seconds during reconnection

        Returns:
            bool: True if reconnection succeeds, False if it fails
        """
        print("Reconnecting the bot...")
        self.disconnect_bot() # Execute synchronously
        print("Bot disconnected")

        # bot_join synchronously starts the bot's initialization.
        self.bot_join()
        print("Bot reconnected")
        # Wait for connection completion with check_server_active (use await)
        print("Checking server connection after reconnection...")
        return await self.check_server_active(timeout=timeout)

    async def get_bot_status(self, retry_count=0, max_retries=1):
        """Get bot status and surrounding information (biome, time, health, hunger, entities, inventory, block classification)"""
        await self.check_server_active()
        # Check connection status and the existence of the bot instance more reliably
        if not self.bot or not self.is_connected:
            print("Error: The bot is not connected or not initialized.")
            # Although it is possible to consider adding logic to attempt reconnection, None is returned here.
            # raise Exception("The bot is not connected or not initialized.")
            return None
        if not self.skills:
            print("Error: Skills are not initialized.")
            # raise Exception("Skills are not initialized.")
            return None

        try:
            # --- Get bot's basic information ---
            try:
                # Before accessing the entity, recheck the connection (just in case)
                if not self.is_connected:
                     print("Error: Connection was lost before entity access.")
                     raise Exception("Connection was lost before entity access.")
                bot_entity = self.bot.entity # A timeout may occur here.
            except Exception as e:
                if "Timed out accessing 'entity'" in str(e) and retry_count < max_retries:
                    print(f"\033[93mAccess to the entity timed out. Attempting to reconnect... (Attempt {retry_count + 1}/{max_retries})\033[0m")
                    reconnected = await self.reconnect_bot()
                    if reconnected:
                        print("\033[92mReconnection successful. Retrying status acquisition.\033[0m")
                        # Increase retry count with recursive call
                        return await self.get_bot_status(retry_count=retry_count + 1, max_retries=max_retries)
                    else:
                        print("\033[91mReconnection failed. Aborting status acquisition.\033[0m")
                        return None # Return None if reconnection fails
                else:
                    # Error other than timeout, or retry limit exceeded
                    print(f"\033[91mAn unrecoverable error occurred while getting the entity (other than retry limit exceeded or timeout): {e}\033[0m")
                    import traceback
                    traceback.print_exc()
                    return None # Return None on error

            # --- Subsequent processing using bot_entity ---
            bot_pos_raw = bot_entity.position # Y coordinate is entity-based
            bot_health = self.bot.health
            bot_food = self.bot.food
            bot_time = self.bot.time.timeOfDay

            # Get the block and biome where the bot is located
            center_block = self.bot.blockAt(bot_pos_raw)
            #bottom_block = self.discovery.bot.blockAt(bot_pos_raw.offset(0, -1, 0))
            bot_pos = center_block.position.offset(0, 1, 0)
            bot_biome_id = self.bot.world.getBiome(bot_pos)
            bot_biome_name = self.mcdata.biomes[str(bot_biome_id)]['name']
            bot_x = bot_pos.x
            bot_z = bot_pos.z
            bot_y = bot_pos.y # y-coordinate also added

            # --- Get & Classify Surrounding Blocks ---
            # Check if _get_surrounding_blocks requires await
            blocks = await self.skills._get_surrounding_blocks(
                position=bot_pos, # Match skill argument name
                x_distance=3,
                y_distance=2,
                z_distance=3
            )

            # Temporarily store block names by group
            temp_grouped_block_names = {"group1": [], "group2": [], "group3": [], "group4": [], "group0": []}

            if blocks:
                for block in blocks:
                    block_pos_dict = block.get('position')
                    block_name = block.get('name')
                    if not isinstance(block_pos_dict, dict) or block_name is None:
                        continue

                    block_x = block_pos_dict.get('x')
                    block_z = block_pos_dict.get('z')
                    if not isinstance(block_x, (int, float)) or not isinstance(block_z, (int, float)):
                        continue

                    dx = block_x - bot_x
                    dz = block_z - bot_z

                    if math.fabs(dx) < 1e-6 and math.fabs(dz) < 1e-6:
                        temp_grouped_block_names["group0"].append(block_name)
                    elif dz > 1e-6 and math.fabs(dx) <= dz + 1e-6:
                        temp_grouped_block_names["group1"].append(block_name)
                    elif dx > 1e-6 and math.fabs(dz) <= dx + 1e-6:
                        temp_grouped_block_names["group2"].append(block_name)
                    elif dz < -1e-6 and math.fabs(dx) <= math.fabs(dz) + 1e-6:
                        temp_grouped_block_names["group3"].append(block_name)
                    elif dx < -1e-6 and math.fabs(dz) <= math.fabs(dx) + 1e-6:
                        temp_grouped_block_names["group4"].append(block_name)

            # Block classification results (deduplicated and sorted)
            classified_blocks = {
                "front_blocks": sorted(list(set(temp_grouped_block_names["group1"]))),
                "right_blocks": sorted(list(set(temp_grouped_block_names["group2"]))),
                "back_blocks": sorted(list(set(temp_grouped_block_names["group3"]))),
                "left_blocks": sorted(list(set(temp_grouped_block_names["group4"]))),
                "center_blocks": sorted(list(set(temp_grouped_block_names["group0"])))
            }

            # --- Get Nearby Entity Information ---
            nearby_entities_info = []
            # _get_nearby_entities might be a synchronous method
            nearby_entities_raw = self.skills._get_nearby_entities(max_distance=16) # Adjust range as appropriate
            if nearby_entities_raw:
                for entity in nearby_entities_raw:
                    # Extract only valid entity information
                    if hasattr(entity, 'name') and hasattr(entity, 'position') and entity.position:
                        nearby_entities_info.append({
                            "name": entity.name,
                            "position": {
                                "x": round(entity.position.x, 1), # Round to one decimal place
                                "y": round(entity.position.y, 1), # Round to one decimal place
                                "z": round(entity.position.z, 1)  # Round to one decimal place
                            }
                        })

            # --- Get Inventory Information ---
            inventory_info = {}
            # get_inventory_counts is a synchronous method
            inventory_info = await self.skills.get_inventory_counts()

            # --- Create Final Response ---
            final_result = {
                "biome": bot_biome_name,
                "time_of_day": bot_time,
                "health": bot_health,
                "hunger": bot_food,
                "bot_position": f"x={bot_x:.1f}, y={bot_y:.1f}, z={bot_z:.1f}",
                "nearby_entities": nearby_entities_info,
                "inventory": inventory_info,
                **classified_blocks # Expand and combine block classification results
            }
            return final_result

        except Exception as e:
            print(f"An unexpected error occurred while getting bot status: {e}")
            import traceback
            traceback.print_exc()
            return None
        
    async def get_skills_list(self, skill_names: list[str] | None = None):
        """
        Retrieves a list of names, descriptions, and usages for specified functions (methods) available in the Skills class.
        If skill_names is None or empty, an empty list is returned.

        Args:
            skill_names (list[str] | None, optional): List of skill names for which to retrieve details. Defaults to None.

        Returns:
            list: A list of dictionaries, each containing skill information.
        """
        if self.skills is None:
            print("Error: Skills not initialized")
            return [] # Return an empty list

        # If skill_names is None or empty, return an empty list
        if not skill_names:
            return []

        skill_list = []
        # Get methods of the skills object using inspect.getmembers
        for name, method in inspect.getmembers(self.skills, inspect.ismethod):
            # Target only public methods that are in the specified list and do not start with an underscore
            if name in skill_names and not name.startswith('_'):
                # Get and format docstring
                docstring = inspect.cleandoc(method.__doc__) if method.__doc__ else ""
                description_lines = []
                usage_lines = []
                in_description = True
                section_headers = ("Args:", "Arguments:", "Parameters:", "Returns:", "Yields:", "Raises:", "Attributes:")

                if docstring:
                    lines = docstring.splitlines()
                    if lines:
                        description_lines.append(lines[0]) # The first line is always the description
                        # Process from the second line onwards
                        for i in range(1, len(lines)):
                            line = lines[i]
                            stripped_line = line.strip()
                            # Determine the separator between Description and Usage
                            if in_description and (not stripped_line or stripped_line.startswith(section_headers)):
                                in_description = False
                            
                            if in_description:
                                description_lines.append(line)
                            else:
                                usage_lines.append(line)

                description = "\n".join(description_lines).strip()
                usage = "\n".join(usage_lines).strip()
                if not description:
                    description = "No description available."
                if not usage:
                    usage = "-" # If Usage is not available, use a hyphen

                # --- Get Function Signature ---
                try:
                    source_lines = inspect.getsource(method).splitlines()
                    # Get the first 'def' or 'async def' line
                    signature_line = next((line for line in source_lines if line.strip().startswith(('def ', 'async def '))), None)
                    if signature_line:
                        # Remove trailing colon
                        signature = signature_line.strip().rstrip(':')
                    else:
                        # Fallback if not found
                        signature = name
                except (TypeError, OSError):
                    # Fallback if source code cannot be obtained
                    signature = name
                # --- End of additions/changes ---

                skill_list.append({
                    "name": signature, # Change name to signature (or include both)
                    "description": description, # Split description
                    "usage": usage           # Split usage
                })

        # Sort by name and return (also change sort key)
        return sorted(skill_list, key=lambda x: x['name'])
    
    async def get_skill_code(self, skill_names: list[str]):
        """Get source code corresponding to the list of specified skill function names (excluding docstring).

        Args:
            skill_names (list[str]): A list of skill names for which to retrieve source code.

        Returns:
            dict: A dictionary containing each skill name and its source code or error information.
                  例: {'skill_name': {'success': bool, 'message': str, 'code': str | None}}
        """
        results = {}
        if self.skills is None:
            # If skills is missing, return an error for all skill names
            for name in skill_names:
                results[name] = {
                    "success": False,
                    "message": "Error: Skills not initialized",
                    "code": None
                }
            return results

        # --- Transformer to remove Docstrings --- (defined within the function)
        class DocstringRemover(ast.NodeTransformer):
            def _remove_docstring(self, node):
                if not node.body:
                    return
                # Check if the first expression in a function/class definition is a docstring
                if isinstance(node.body[0], ast.Expr):
                    if isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
                        # Docstring (Python 3.8+)
                        node.body.pop(0)
                    elif isinstance(node.body[0].value, ast.Str):
                        # Docstring (Python 3.7 or earlier)
                        node.body.pop(0)

            def visit_FunctionDef(self, node):
                self._remove_docstring(node)
                self.generic_visit(node)
                return node

            def visit_AsyncFunctionDef(self, node):
                self._remove_docstring(node)
                self.generic_visit(node)
                return node

        for skill_name in skill_names:
            single_result = {
                "success": False,
                "message": "",
                "code": None
            }

            # Get the method corresponding to skill_name
            try:
                method = getattr(self.skills, skill_name)
            except AttributeError:
                single_result["message"] = f"Error: Skill function '{skill_name}' not found"
                results[skill_name] = single_result
                continue # To the next skill

            # Check if the method is callable and does not start with an underscore
            if not callable(method) or skill_name.startswith('_'):
                single_result["message"] = f"Error: Skill function '{skill_name}' not found or inaccessible"
                results[skill_name] = single_result
                continue # To the next skill

            # Get the method's source code and remove the docstring
            try:
                source_code = inspect.getsource(method)
                # Remove indentation from source code (dedent required before AST parsing)
                dedented_source_code = textwrap.dedent(source_code)

                # Parse into AST
                tree = ast.parse(dedented_source_code)

                # Apply the Transformer to remove Docstrings
                transformer = DocstringRemover()
                new_tree = transformer.visit(tree)
                ast.fix_missing_locations(new_tree) # Fix location information

                # Convert AST back to source code string (Python 3.9+)
                # ast.unparse reconstructs indentation
                code_without_docstring = ast.unparse(new_tree)
                single_result["success"] = True
                single_result["message"] = "Source code retrieved successfully."
                single_result["code"] = code_without_docstring

            except (TypeError, OSError) as e:
                # If source code cannot be retrieved
                single_result["message"] = f"Error: Could not retrieve source code for skill function '{skill_name}': {e}"
            except SyntaxError as e:
                # Error handling on AST parsing failure
                single_result["message"] = f"Error: Failed to parse source code for skill function '{skill_name}': {e}"
            except AttributeError as e:
                # Error if ast.unparse is missing (Python < 3.9)
                if "'module' object has no attribute 'unparse'" in str(e):
                    single_result["message"] = "Error: This feature requires Python 3.9 or higher (ast.unparse)."
                else:
                    single_result["message"] = f"Error: An unexpected error occurred: {e}"
            
            results[skill_name] = single_result

        return results

    async def execute_python_code(self, code_string: str, wrapper_func_name: str = "main"):
        """
        Executes the given Python code string within an asynchronous function of the specified name.
        The default function name is 'main'.
        """
        await self.check_server_active()
        # Check if bot and skills are initialized correctly and bot is connected
        if not self.bot or not self.skills or not self.is_connected:
            error_msg = "Error: Bot or skill is not initialized or not connected to the server."
            print(error_msg)
            return {"success": False, "error": error_msg, "traceback": "", "output": "", "error_output": ""}

        output_buffer = io.StringIO()
        error_buffer = io.StringIO()

        # Variables to pass to the execution context (add bot)
        bot = self.bot # Alias
        skills = self.skills # Alias
        discovery = self # Alias
        exec_globals = {
            "asyncio": asyncio,
            "skills": skills,
            "discovery": discovery,
            "bot": bot,
            "__builtins__": __builtins__ # The fact that this is included is important
        }

        # Properly indent user code
        indented_user_code = textwrap.indent(code_string, '    ')

        # Create the code string for the asynchronous wrapper function (use the specified function name)
        wrapper_code = f"""
import asyncio

async def {wrapper_func_name}():
{indented_user_code}
"""
        print(f"\033[32m{wrapper_code}\033[0m")

        try:
            # Define the wrapper function
            exec(wrapper_code, exec_globals)

            # Get the defined asynchronous function object (use the specified function name)
            async_func_to_run = exec_globals.get(wrapper_func_name)

            if async_func_to_run and inspect.iscoroutinefunction(async_func_to_run):
                with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(error_buffer):
                    await async_func_to_run()
            else:
                # Error if the function was not defined correctly
                error_message = f"Failed to define or find the async wrapper function '{wrapper_func_name}'.\\n\\n{wrapper_code}"
                raise RuntimeError(error_message)

            # Get the execution result
            output = output_buffer.getvalue()
            error_output = error_buffer.getvalue()
            print(f"\033[32mOutput:\n{output}\033[0m")
            if error_output:
                print(f"\033[31mError:\n{error_output}\033[0m")
            result = {
                "success": True,
                "output": output,
                "error_output": error_output
            }

        except Exception as e:
            # Capture errors during exec or await
            error_message = str(e)
            tb_str = traceback.format_exc()
            # Also get the error output before the error occurred
            error_output_before_exception = error_buffer.getvalue()

            print(f"\033[31mAn error occurred during code execution: {error_message}\nError details:{tb_str}\033[0m") # Also display error on console

            result = {
                "success": False,
                "error": error_message,
                "traceback": tb_str,
                "error_output": error_output_before_exception
            }
        finally:
            # Add to code execution history
            self.code_execution_history.append({"code": code_string, "result": result})
        
        return result

    async def get_screenshot_base64(self, direction: str | None = None, width: int = 960, height: int = 540) -> str | None:
        """
        Turn to the specified direction, then take a screenshot of the Prismarine Viewer, and
        return it as a Base64 encoded string.

        Args:
            direction (str | None, optional): The direction to face ('north', 'south', 'east', 'west', 'up', 'down' etc.). Defaults to None.
            width (int): Screenshot width.
            height (int): Screenshot height.

        Returns:
            str | None: Base64 encoded PNG image string. None on error.
        """
        await self.check_server_active() # Server connection check is done first
        self.bot.chat(f"Taking a screenshot. (Direction: {direction or 'current'})")
        print(f"\033[34mCapturing screenshot from Prismarine Viewer (Direction: {direction or 'current'})...\033[0m")
        if not self.is_server_active():
            print("Error: Bot is not connected. Cannot take a screenshot.")
            return None

        if direction:
            if self.skills: # Check if skills object is initialized
                try:
                    look_result = await self.skills.look_at_direction(direction)
                    if not look_result or not look_result.get("success", False):
                         print(f"\033[93mWarning: Failed to look towards {direction}. Proceeding with current view. Message: {look_result.get('message', 'N/A') if look_result else 'N/A'}\033[0m")
                    await asyncio.sleep(1) # Wait for the viewpoint change to be reflected
                except Exception as e:
                     print(f"\033[93mWarning: Error occurred while trying to look towards {direction}: {e}. Proceeding with current view.\033[0m")
            else:
                 print("\033[93mWarning: Skills object not initialized. Cannot change direction.\033[0m")

        url = f"http://localhost:{self.prismarine_viewer_port}"
        browser = None # Initialize so it can be referenced in the finally block
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": width, "height": height})

                await page.goto(url, wait_until="load", timeout=60000) # Extend timeout to 60 seconds
                await page.wait_for_selector('canvas', timeout=30000) # Wait up to 30 seconds for canvas to appear
                # Ensure sufficient waiting time for rendering stability
                await asyncio.sleep(5) # Adjust as needed

                screenshot_bytes = await page.screenshot(type="png")
                await browser.close() # Close the browser immediately after taking the screenshot
                browser = None # Indicate that it has been closed

                base64_image = base64.b64encode(screenshot_bytes).decode('utf-8')
                print("\033[34mScreenshot captured and encoded successfully.\033[0m")
                return base64_image

        except Exception as e:
            print(f"An error occurred while taking the screenshot: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            if browser: # Close the browser if it remains open due to an error, etc.
                 print("Closing the browser due to an error.")
                 await browser.close()

async def run_craft_example():
    """Example of using the craft_items method of the Skills class"""
    # Create a Discovery instance and initialize Skills
    discovery = Discovery()
    await discovery.check_server_and_join()
    skills = discovery.skills
    # Check if the server is active
    server_active = await discovery.check_server_active(timeout=15)
    if not server_active:
        print("Cannot connect to the server. Exiting.")
        return
    
    code = """
result = await skills.collect_block('oak_log', num=5)
print(result)
inventory = await skills.get_inventory_counts()
oak_logs = inventory.get('oak_log', 0)
print(f"Collected {oak_logs} oak_log.")
"""
    while True:
        try:
            print(input("Enter: "))
            #await discovery.get_screenshot_base64(direction='north')
            #print(await discovery.execute_python_code(code))
            result = await skills.collect_block('oak_log', num=5)
            #print(await skills.pickup_nearby_items())
            
        except Exception as e:
            print(f"An error occurred: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    
    # Mode to only check server connection
    if len(sys.argv) > 1 and sys.argv[1] == "--check-server":
        async def check_server_connection():
            discovery = Discovery()
            print("Checking Minecraft server connection status...")
            result = await discovery.check_server_active(timeout=15)
            if result:
                print("✅ Minecraft server is active!")
                # Display server version information
                print(f"Server version: {discovery.bot.version}")
            else:
                print("❌ Could not connect to Minecraft server")
            return result
        
        asyncio.run(check_server_connection())
    else:
        # Run in Skills mode
        print("Starting in Skills mode...")
        asyncio.run(run_craft_example())