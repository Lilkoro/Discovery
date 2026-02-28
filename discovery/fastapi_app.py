from fastapi import FastAPI, HTTPException, Depends, Query, Path, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uvicorn
import asyncio
from discovery.discovery import Discovery
from contextlib import asynccontextmanager
import math # Import for math.fabs
import inspect # For method and docstring extraction
import io # For standard output/error capture
import contextlib # For redirect_stdout/stderr
import traceback # For traceback extraction
import textwrap # For indentation adjustment
import os # Import os module
from dotenv import load_dotenv # Import load_dotenv from python-dotenv
import ast # Import ast module

# Initialize Discovery instance
discovery = Discovery()
skills = None
current_goal: Optional[str] = None # Added: Variable to store the current goal

# Define lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Operations on application startup
    global skills
    discovery.bot_join()
    skills = discovery.create_skills()
    # Check server connection (execute asynchronously)
    asyncio.create_task(check_server_connection())
    
    yield
    
    # Operations on application shutdown
    # Implement bot disconnection etc. if necessary
    if discovery:
        discovery.disconnect_bot()

# Create FastAPI instance
app = FastAPI(
    title="MineCraft Bot API",
    description="Minecraft Bot API is a control API for Minecraft bots using MineFlayer.",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Check server connection
async def check_server_connection():
    server_active = await discovery.check_server_active(timeout=15)
    if not server_active:
        raise HTTPException(status_code=503, detail="Cannot connect to Minecraft server. Please check the port.")

# Root endpoint
@app.get("/")
async def root():
    return {"message": "MineCraft Bot API is running..."}

# Get server info
@app.get("/server/info", tags=["server"])
async def get_server_info():
    return discovery.get_server_info()

# Check bot connection status -> Changed to regional classification of surrounding blocks
@app.get("/bot/status", tags=["bot"], summary="Retrieve bot status and surrounding information (biome, time, health, hunger, entities, inventory, block classification)")
async def get_bot_status():
    # --- Get basic bot info ---
    try:
        bot_entity = discovery.bot.entity
        bot_pos_raw = bot_entity.position # Y coordinate based on entity
        bot_health = discovery.bot.health
        bot_food = discovery.bot.food
        bot_time = discovery.bot.time.timeOfDay

        # Get block where the bot is standing and the biome
        center_block = discovery.bot.blockAt(bot_pos_raw)
        bottom_block = discovery.bot.blockAt(bot_pos_raw.offset(0, -1, 0))
        bot_pos = center_block.position.offset(0, 1, 0)
        bot_biome_id = discovery.bot.world.getBiome(bot_pos)
        bot_biome_name = discovery.mcdata.biomes[str(bot_biome_id)]['name']
        bot_x = bot_pos.x
        bot_z = bot_pos.z

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get basic bot info: {e}")

    # --- Retrieve & Classify surrounding blocks ---
    try:
        blocks = await skills.get_surrounding_blocks(
            position=bot_pos, # Match skill argument name
            x_distance=3,
            y_distance=2,
            z_distance=3
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch surrounding block info: {e}")

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

    # Block classification result (remove duplicates and sort)
    classified_blocks = {
        "front_blocks": sorted(list(set(temp_grouped_block_names["group1"]))),
        "right_blocks": sorted(list(set(temp_grouped_block_names["group2"]))),
        "back_blocks": sorted(list(set(temp_grouped_block_names["group3"]))),
        "left_blocks": sorted(list(set(temp_grouped_block_names["group4"]))),
        "center_blocks": sorted(list(set(temp_grouped_block_names["group0"])))
    }

    # --- Retrieve nearby entity info ---
    nearby_entities_info = []
    try:
        # _get_nearby_entities might be a synchronous method
        nearby_entities_raw = skills._get_nearby_entities(max_distance=16) # Adjust range accordingly
        if nearby_entities_raw:
            for entity in nearby_entities_raw:
                # Extract only valid entity info
                if hasattr(entity, 'name') and hasattr(entity, 'position') and entity.position:
                    nearby_entities_info.append({
                        "name": entity.name,
                        "position": {
                            "x": round(entity.position.x, 1), # Round to nearest tenth
                            "y": round(entity.position.y, 1), # Round to nearest tenth
                            "z": round(entity.position.z, 1)  # Round to nearest tenth
                        }
                    })
    except Exception as e:
        print(f"Warning: Failed to get nearby entities ({e})")
        # Continue execution even if an error occurs

    # --- Retrieve inventory info ---
    inventory_info = {}
    try:
        # get_inventory_counts is synchronous
        inventory_info = skills.get_inventory_counts()
    except Exception as e:
        print(f"Warning: Failed to get inventory counts ({e})")
        # Continue execution even if an error occurs

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

# Endpoint to get the list of functions in Skills class
@app.get("/skills/list", tags=["skills"], summary="Retrieve a list of available function (method) names, descriptions, and async flags from the Skills class")
async def get_skills_list():
    global skills # Use the skills instance initialized in lifespan
    if skills is None:
        raise HTTPException(status_code=503, detail="Skills has not been initialized")

    skill_list = []
    # Get methods of skills object using inspect.getmembers
    for name, method in inspect.getmembers(skills, inspect.ismethod):
        # Target only public methods (those not starting with an underscore)
        if not name.startswith('_'):
            # Fetch and format docstring
            docstring = inspect.cleandoc(method.__doc__) if method.__doc__ else "No description available."
            # Check if method is an async function
            is_async = inspect.iscoroutinefunction(method)

            skill_list.append({
                "name": name,
                "description": docstring,
                "is_async": is_async # Include async flag
            })

    # Return sorted alphabetically by name
    return sorted(skill_list, key=lambda x: x['name'])

# New endpoint: Get source code of a specific skill function
@app.get("/skills/code/{skill_name}", tags=["skills"], summary="Get source code of a specific skill function (excluding docstring)")
async def get_skill_code(skill_name: str = Path(..., title="Name of the skill function to retrieve")):
    global skills
    if skills is None:
        raise HTTPException(status_code=503, detail="Skills has not been initialized")

    # Get the method corresponding to skill_name
    try:
        method = getattr(skills, skill_name)
    except AttributeError:
        raise HTTPException(status_code=404, detail=f"Skill function '{skill_name}' not found")

    # Ensure the method is callable and does not start with an underscore
    if not callable(method) or skill_name.startswith('_'):
        raise HTTPException(status_code=404, detail=f"Skill function '{skill_name}' not found or cannot be accessed")

    # --- Transformer to remove Docstrings ---
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

        def visit_ClassDef(self, node): # Optional: Remove class docstrings too
            self._remove_docstring(node)
            self.generic_visit(node)
            return node

    # Get the source code of the method and remove the docstring
    try:
        source_code = inspect.getsource(method)
        # Remove indentation from the source code (dedent is required before AST parsing)
        dedented_source_code = textwrap.dedent(source_code)

        # Parse into AST
        tree = ast.parse(dedented_source_code)

        # Apply the Transformer to remove docstrings
        transformer = DocstringRemover()
        new_tree = transformer.visit(tree)
        ast.fix_missing_locations(new_tree) # Fix location info

        # Convert AST back to source code string (Python 3.9+)
        # ast.unparse reconstructs the indentation
        code_without_docstring = ast.unparse(new_tree)

        return {"skill_name": skill_name, "source_code": code_without_docstring}

    except (TypeError, OSError) as e:
        # If source code cannot be retrieved
        raise HTTPException(status_code=500, detail=f"Could not retrieve source code for skill function '{skill_name}': {e}")
    except SyntaxError as e:
        # Error handling for AST parsing failures
        raise HTTPException(status_code=500, detail=f"Failed to parse source code for skill function '{skill_name}': {e}")
    except AttributeError as e:
        # Error if ast.unparse is missing (Python < 3.9)
        if "'module' object has no attribute 'unparse'" in str(e):
             raise HTTPException(status_code=501, detail="This feature requires Python 3.9 or higher (ast.unparse).")
        else:
             raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

# --- Pydantic model definitions ---
class CodeExecutionRequest(BaseModel):
    code: str

class TeleportRequest(BaseModel):
    position_x: float
    position_y: float
    position_z: float

# --- Python code execution endpoint ---
@app.post("/execute/python_code", tags=["execute"], summary="Executes python code string (async supported) [Security Warning]")
async def execute_python_code(request: CodeExecutionRequest):
    global skills, discovery, bot
    # Set bot instance to global scope from discovery (to make it accessible in the function)
    # Assumes it has been initialized in lifespan
    if discovery and hasattr(discovery, 'bot'):
        bot = discovery.bot
    else:
        # Error handling when discovery or bot is uninitialized
        raise HTTPException(status_code=503, detail="Bot is not initialized")

    output_buffer = io.StringIO()
    error_buffer = io.StringIO()

    # Name of the dynamically generated async wrapper function
    dynamic_async_func_name = "__dynamic_exec_async_code__"

    # Properly indent code generated by LLM
    # Use textwrap.indent to add spaces at the beginning of each line
    indented_user_code = textwrap.indent(request.code, '    ') # Indent with 4 spaces

    # Create code string for async wrapper function
    # Make skills, discovery, bot, asyncio available in the function
    # Expected to be accessed as global variables
    wrapper_code = f"""
import asyncio # Enable asyncio in wrapper function

async def {dynamic_async_func_name}():
    # Referencing global variables skills, discovery, bot
    global skills, discovery, bot
    # --- User Code Start ---
{indented_user_code}
    # --- User Code End ---

"""
    # Execution context for exec (global scope)
    # Include current global variables so the wrapper function can reference them
    exec_globals = globals().copy()
    # It is also possible to pass additional variables if necessary
    # exec_globals.update({"some_other_var": some_value})

    try:
        # Define wrapper function
        # By passing exec_globals, the wrapper function can reference global variables like skills
        exec(wrapper_code, exec_globals)

        # Retrieve the defined async function object
        async_func_to_run = exec_globals.get(dynamic_async_func_name)

        if async_func_to_run and inspect.iscoroutinefunction(async_func_to_run):
            # Execute the dynamically defined async function while capturing standard input and output
            with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(error_buffer):
                await async_func_to_run()
        else:
            # Error if function was not defined properly
            # Could fall back to executing as sync code, but treating it as an error here
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
        # Also capture error output before the exception occurs
        error_output_before_exception = error_buffer.getvalue()

        return {
            "success": False,
            "error": error_message,
            "traceback": tb_str,
            # Also return standard error output from before the error
            "error_output": error_output_before_exception
        }

# --- Teleport endpoint (/bot/teleport) ---
@app.post("/bot/teleport", tags=["bot"])
async def teleport_bot(request: TeleportRequest):
    discovery.bot.chat(f"/tp bot {request.position_x} {request.position_y} {request.position_z}")
    return {"message": "Teleported the bot"}

# --- Goal setting/getting endpoints ---
class GoalRequest(BaseModel):
    goal: str

# Sets the bot's current objective (goal)
@app.post("/bot/goal", tags=["bot"], summary="Sets the bot's current objective (goal)")
async def set_bot_goal(request: GoalRequest):
    global current_goal
    current_goal = request.goal
    discovery.bot.chat(f"Goal set to: '{current_goal}'")
    return {"message": f"Set goal: {current_goal}"}

# Retrieves the bot's currently set objective (goal)
@app.get("/bot/goal", tags=["bot"], summary="Retrieves the bot's currently set objective (goal)")
async def get_bot_goal():
    global current_goal
    if current_goal is None:
        # raise HTTPException(status_code=404, detail="Goal not yet set")
        # Change to return None instead of 404 (to match other APIs)
        return {"goal": None}
    return {"goal": current_goal}

# Server startup code
if __name__ == "__main__":
    load_dotenv() # Load env vars from .env file
    port = int(os.getenv("PORT", 8000)) # Read PORT env var, default 8000 if not found
    uvicorn.run("fastapi_app:app", host="0.0.0.0", port=port, reload=True) 