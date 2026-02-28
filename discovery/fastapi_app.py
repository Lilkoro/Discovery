from fastapi import FastAPI, HTTPException, Depends, Query, Path, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uvicorn
import asyncio
from discovery import Discovery
from contextlib import asynccontextmanager
import math # import to use math.fabs
from javascript import require # in case of using Vec3 (skills.py dependency)
import inspect # for getting methods and docstrings
import io # for capturing stdout/stderr
import contextlib # for redirect_stdout/stderr
import traceback # for getting traceback
import textwrap # for adjusting indentation
import os # import os module
from dotenv import load_dotenv # import load_dotenv from python-dotenv
import ast # import ast module

# Initialize Discovery instance
discovery = Discovery()
skills = None
current_goal: Optional[str] = None # ★ Added: Variable to store the current goal

# Define lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Processing when the application starts
    global skills
    discovery.bot_join()
    skills = discovery.create_skills()
    # Server connection check (executed asynchronously)
    asyncio.create_task(check_server_connection())
    
    yield
    
    # Processing when the application ends
    # Implement bot disconnection processing etc. as needed
    if discovery:
        discovery.disconnect_bot()

# Create FastAPI instance
app = FastAPI(
    title="MineCraft Bot API",
    description="Minecraft Bot API is a control API for Minecraft bots using MineFlayer.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Server connection check
async def check_server_connection():
    server_active = await discovery.check_server_active(timeout=15)
    if not server_active:
        raise HTTPException(status_code=503, detail="Cannot connect to Minecraft server. Please check the port")

# Root endpoint
@app.get("/")
async def root():
    return {"message": "MineCraft Bot API is running..."}

# Get server information
@app.get("/server/info", tags=["server"])
async def get_server_info():
    return discovery.get_server_info()

# Check bot connection status -> Changed to area classification of blocks around the bot
@app.get("/bot/status", tags=["bot"], summary="Get bot status and surrounding information (biome, time, health, hunger, entities, inventory, block classification)")
async def get_bot_status():
    # --- Get basic bot information ---
    try:
        bot_entity = discovery.bot.entity
        bot_pos_raw = bot_entity.position # Y coordinate is entity-based
        bot_health = discovery.bot.health
        bot_food = discovery.bot.food
        bot_time = discovery.bot.time.timeOfDay

        # Get the block and biome where the bot is located
        center_block = discovery.bot.blockAt(bot_pos_raw)
        bottom_block = discovery.bot.blockAt(bot_pos_raw.offset(0, -1, 0))
        bot_pos = center_block.position.offset(0, 1, 0)
        bot_biome_id = discovery.bot.world.getBiome(bot_pos)
        bot_biome_name = discovery.mcdata.biomes[str(bot_biome_id)]['name']
        bot_x = bot_pos.x
        bot_z = bot_pos.z

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get basic bot information: {e}")

    # --- Get & classify surrounding blocks ---
    try:
        blocks = await skills.get_surrounding_blocks(
            position=bot_pos, # Match skill argument name
            x_distance=3,
            y_distance=2,
            z_distance=3
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get surrounding block information: {e}")

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

    # Block classification results (duplicate removal and sorting)
    classified_blocks = {
        "front_blocks": sorted(list(set(temp_grouped_block_names["group1"]))),
        "right_blocks": sorted(list(set(temp_grouped_block_names["group2"]))),
        "back_blocks": sorted(list(set(temp_grouped_block_names["group3"]))),
        "left_blocks": sorted(list(set(temp_grouped_block_names["group4"]))),
        "center_blocks": sorted(list(set(temp_grouped_block_names["group0"])))
    }

    # --- Get nearby entity information ---
    nearby_entities_info = []
    try:
        # _get_nearby_entities might be a synchronous method
        nearby_entities_raw = skills._get_nearby_entities(max_distance=16) # Adjust range as appropriate
        if nearby_entities_raw:
            for entity in nearby_entities_raw:
                # Extract only valid entity information
                if hasattr(entity, 'name') and hasattr(entity, 'position') and entity.position:
                    nearby_entities_info.append({
                        "name": entity.name,
                        "position": {
                            "x": round(entity.position.x, 1), # round to one decimal place
                            "y": round(entity.position.y, 1), # Round to the first decimal place
                            "z": round(entity.position.z, 1)  # Round to the first decimal place
                        }
                    })
    except Exception as e:
        print(f"Warning: Failed to get nearby entities ({e})")
        # Processing continues even if an error occurs

    # --- Get inventory information ---
    inventory_info = {}
    try:
        # get_inventory_counts is a synchronous method
        inventory_info = skills.get_inventory_counts()
    except Exception as e:
        print(f"Warning: Failed to get inventory counts ({e})")
        # Processing continues even if an error occurs

    # --- Create final response ---
    final_result = {
        "biome": bot_biome_name,
        "time_of_day": bot_time,
        "health": bot_health,
        "hunger": bot_food,
        "bot_position": f"x = {center_block.position.x}, y = {center_block.position.y}, z = {center_block.position.z}",
        "nearby_entities": nearby_entities_info,
        "inventory": inventory_info,
        **classified_blocks # Expand and combine block classification results
    }

    return final_result

# Endpoint to get the function list of Skills class
@app.get("/skills/list", tags=["skills"], summary="Get a list of names, descriptions, and async flags of functions (methods) available in the Skills class")
async def get_skills_list():
    global skills # Use the skills instance initialized in lifespan
    if skills is None:
        raise HTTPException(status_code=503, detail="Skills are not initialized")

    skill_list = []
    # Get methods of the skills object with inspect.getmembers
    for name, method in inspect.getmembers(skills, inspect.ismethod):
        # Target only public methods that do not start with an underscore
        if not name.startswith('_'):
            # Get docstring and format it
            docstring = inspect.cleandoc(method.__doc__) if method.__doc__ else "No description available."
            # Check if the method is an async function
            is_async = inspect.iscoroutinefunction(method)

            skill_list.append({
                "name": name,
                "description": docstring,
                "is_async": is_async # Add async flag
            })

    # Sort by name and return
    return sorted(skill_list, key=lambda x: x['name'])

# New endpoint: Get source code for a specific skill function
@app.get("/skills/code/{skill_name}", tags=["skills"], summary="Get the source code of the specified skill function (excluding docstring)")
async def get_skill_code(skill_name: str = Path(..., title="Name of the skill function to retrieve")):
    global skills
    if skills is None:
        raise HTTPException(status_code=503, detail="Skills are not initialized")

    # Get the method corresponding to skill_name
    try:
        method = getattr(skills, skill_name)
    except AttributeError:
        raise HTTPException(status_code=404, detail=f"Skill function '{skill_name}' not found")

    # Verify that the method is callable and does not start with an underscore
    if not callable(method) or skill_name.startswith('_'):
        raise HTTPException(status_code=404, detail=f"Skill function '{skill_name}' not found or inaccessible")

    # --- Transformer to remove Docstrings ---
    class DocstringRemover(ast.NodeTransformer):
        def _remove_docstring(self, node):
            if not node.body:
                return
            # Check if the first expression within a function/class definition is a docstring
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

        def visit_ClassDef(self, node): # If removing docstrings from class definitions as well
            self._remove_docstring(node)
            self.generic_visit(node)
            return node

    # Get the method's source code and remove the docstring
    try:
        source_code = inspect.getsource(method)
        # Remove source code indentation (dedent required before AST parsing)
        dedented_source_code = textwrap.dedent(source_code)

        # Parse to AST
        tree = ast.parse(dedented_source_code)

        # Apply Transformer to remove Docstring
        transformer = DocstringRemover()
        new_tree = transformer.visit(tree)
        ast.fix_missing_locations(new_tree) # Fix location information

        # Convert AST back to source code string (Python 3.9+)
        # ast.unparse reconstructs indentation
        code_without_docstring = ast.unparse(new_tree)

        return {"skill_name": skill_name, "source_code": code_without_docstring}

    except (TypeError, OSError) as e:
        # If source code cannot be retrieved
        raise HTTPException(status_code=500, detail=f"Could not retrieve source code for skill function '{skill_name}': {e}")
    except SyntaxError as e:
        # Error handling for AST parsing failure
        raise HTTPException(status_code=500, detail=f"Failed to parse source code of skill function '{skill_name}': {e}")
    except AttributeError as e:
        # Error when ast.unparse is not available (Python < 3.9)
        if "'module' object has no attribute 'unparse'" in str(e):
             raise HTTPException(status_code=501, detail="This feature requires Python 3.9 or higher (ast.unparse).")
        else:
             raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

# --- Pydantic Model Definition ---
class CodeExecutionRequest(BaseModel):
    code: str

class TeleportRequest(BaseModel):
    position_x: float
    position_y: float
    position_z: float

# --- Python Code Execution Endpoint ---
@app.post("/execute/python_code", tags=["execute"], summary="Executes Python code string (async compatible) [SECURITY WARNING]")
async def execute_python_code(request: CodeExecutionRequest):
    global skills, discovery, bot
    # Get bot instance from discovery and set it in global scope (to make it accessible within the function)
    # Assumes it is initialized in lifespan
    if discovery and hasattr(discovery, 'bot'):
        bot = discovery.bot
    else:
        # Error handling if discovery or bot is not initialized
        raise HTTPException(status_code=503, detail="Bot is not initialized")

    output_buffer = io.StringIO()
    error_buffer = io.StringIO()

    # Name of the dynamically generated async wrapper function
    dynamic_async_func_name = "__dynamic_exec_async_code__"

    # Properly indent code generated by LLM
    # Add spaces to the beginning of each line using textwrap.indent
    indented_user_code = textwrap.indent(request.code, '    ') # Indent with 4 spaces

    # Create the code string for the async wrapper function
    # Make skills, discovery, bot, asyncio available within the function
    # Assumed to be accessed as global variables
    wrapper_code = f"""
import asyncio # Make asyncio available within the wrapper function

async def {dynamic_async_func_name}():
    # Reference global variables skills, discovery, bot
    global skills, discovery, bot
    # --- User Code Start ---
{indented_user_code}
    # --- User Code End ---

"""
    # Execution context for exec (global scope)
    # Include current global variables so the wrapper function can reference them
    exec_globals = globals().copy()
    # Additional variables can be passed if needed
    # exec_globals.update({"some_other_var": some_value})

    try:
        # Define the wrapper function
        # By passing exec_globals, the wrapper function can reference global variables like skills
        exec(wrapper_code, exec_globals)

        # Get the defined async function object
        async_func_to_run = exec_globals.get(dynamic_async_func_name)

        if async_func_to_run and inspect.iscoroutinefunction(async_func_to_run):
            # Execute the dynamically defined async function while capturing stdout and stderr
            with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(error_buffer):
                await async_func_to_run()
        else:
            # Error if the function was not defined correctly
            # A fallback to run as synchronous code could be considered, but here it is an an error
            raise RuntimeError(f"Failed to define the internal async wrapper function '{dynamic_async_func_name}'.")

        # Get execution results
        output = output_buffer.getvalue()
        error_output = error_buffer.getvalue()

        return {
            "success": True,
            "output": output,
            "error_output": error_output
        }

    except Exception as e:
        # Capture errors during exec or await
        error_message = str(e)
        tb_str = traceback.format_exc()
        # Also retrieve error output before the error occurred
        error_output_before_exception = error_buffer.getvalue()

        return {
            "success": False,
            "error": error_message,
            "traceback": tb_str,
            # Also return stderr output before the error occurred
            "error_output": error_output_before_exception
        }

# --- Teleport Endpoint (/bot/teleport) ---
@app.post("/bot/teleport", tags=["bot"])
async def teleport_bot(request: TeleportRequest):
    discovery.bot.chat(f"/tp bot {request.position_x} {request.position_y} {request.position_z}")
    return {"message": "Bot teleported"}

# --- Goal Setting/Retrieval Endpoint ---
class GoalRequest(BaseModel):
    goal: str

# Sets the bot's current objective (goal)
@app.post("/bot/goal", tags=["bot"], summary="Sets the bot's current objective (goal)")
async def set_bot_goal(request: GoalRequest):
    global current_goal
    current_goal = request.goal
    discovery.bot.chat(f"Goal set to '{current_goal}'")
    return {"message": f"Goal set: {current_goal}"}

# Retrieves the bot's currently set objective (goal)
@app.get("/bot/goal", tags=["bot"], summary="Get the goal currently set for the bot")
async def get_bot_goal():
    global current_goal
    if current_goal is None:
        # raise HTTPException(status_code=404, detail="No goal has been set yet")
        # Changed to return None instead of 404 (to match other APIs)
        return {"goal": None}
    return {"goal": current_goal}

# Server startup code
if __name__ == "__main__":
    load_dotenv() # Load environment variables from .env file
    port = int(os.getenv("PORT", 8000)) # Load environment variable PORT, or 8000 if not found
    uvicorn.run("fastapi_app:app", host="0.0.0.0", port=port, reload=True) 