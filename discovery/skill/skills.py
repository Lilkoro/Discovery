from javascript import require, On, Once, AsyncTask, once, off
import asyncio
import math
from concurrent.futures import ThreadPoolExecutor

class Skills:
    def __init__(self, discovery):
        """
        Receives a Discovery instance and uses its properties
        
        Args:
            discovery: An instance of the Discovery class
        """
        self.discovery = discovery
        self.bot = discovery.bot
        self.mcdata = discovery.mcdata
        self.pathfinder = discovery.pathfinder
        self.movements = discovery.movements
        self.mineflayer = discovery.mineflayer

    async def get_bot_position(self):
        """
        Gets the current position of the bot. Coordinates are returned as tuple[float, float, float].

        Returns:
            tuple[float, float, float]: A tuple containing the x, y, and z coordinates of the bot's position.

        Example:
            >>>result = get_bot_position()
            >>>print(result)
            (100, 50, 200)
            >>>print(result[0])
            100
        """
        bot_pos = self.bot.blockAt(self.bot.entity.position).position
        return bot_pos.x, bot_pos.y, bot_pos.z
    
    async def look_at_direction(self, direction):
        """
        The BOT faces the specified direction. This is effective when combined with BotViewAgent to check the BOT's surrounding view.

        Args:
            direction (str): The cardinal direction ('north', 'south', 'east', 'west', 'up', 'down')

        Returns:
            dict: A dictionary containing the result
                - success (bool): True if the direction change was successful
                - message (str): The result message
        """
        result = {
            "success": False,
            "message": ""
        }

        try:
            # Get current yaw and pitch
            current_yaw = self.bot.entity.yaw
            current_pitch = self.bot.entity.pitch
            
            target_yaw = current_yaw # Default to current yaw
            target_pitch = 0.0 # Default to horizontal

            direction_lower = direction.lower()

            if direction_lower == 'north':
                target_yaw = 0
            elif direction_lower == 'east':
                target_yaw = math.pi / 2
            elif direction_lower == 'south':
                target_yaw = math.pi
            elif direction_lower == 'west':
                target_yaw = -math.pi / 2
            elif direction_lower == 'up':
                target_pitch = math.pi / 2  # Directly upwards
                target_yaw = current_yaw # Maintain yaw when looking up/down
            elif direction_lower == 'down':
                target_pitch = -math.pi / 2 # Directly downwards
                target_yaw = current_yaw # Maintain yaw when looking up/down
            else:
                result["message"] = f"Invalid direction specified: {direction}"
                self.bot.chat(result["message"])
                return result

            # bot.look is likely a synchronous method, but check if it needs await just in case
            # Mineflayer's bot.look is usually synchronous, but can be asynchronous via JavaScript libraries.
            # Treat it as synchronous here (if an error occurs, change to await self.bot.look(...))
            self.bot.look(target_yaw, target_pitch)
            
            result["success"] = True
            result["message"] = f"Faced {direction.capitalize()}."
            # self.bot.chat(result["message"]) # Chat omitted as it may be called frequently
            return result

        except Exception as e:
            result["message"] = f"An error occurred while facing {direction}: {str(e)}"
            self.bot.chat(result["message"])
            import traceback
            traceback.print_exc()
            return result
        
    async def _get_surrounding_blocks(self, position=None, x_distance=10, y_distance=10, z_distance=10):
        """
        Gets blocks around the specified position. This is effective when acquiring block information over a wide range.

        Args:
            position (Vec3 or tuple): The center position for exploration (BOT's position if unspecified). Can also be a tuple.
            x_distance (int): Exploration distance in the X direction (default: 10)
            y_distance (int): Exploration distance in the Y direction (default: 10)
            z_distance (int): Exploration distance in the Z direction (default: 10)

        Returns:
            list: A list of surrounding block information (each element is a dictionary {'name': block_name, 'position': position})

        Operation details:
            - Small range: Acquire all blocks
            - Large range: Optimized by dividing into 3 zones
              - Close range (within 5 block radius): Acquire all blocks
              - Mid range (5-10 block radius): Acquire every 2nd block
              - Far range (over 10 block radius): Acquire every 3rd block
            - Optimize block acquisition with batch processing (500 blocks at a time)
            - Speed up filtering with parallel processing
        """
        Vec3 = require('vec3') # Make Vec3 available

        self.bot.chat(f"Acquiring blocks in a {x_distance}x{y_distance}x{z_distance} range.")
        # Setting default values
        if position is None:
            position = self.bot.entity.position

        # --- Add type check and conversion ---
        if isinstance(position, tuple) and len(position) == 3:
            try:
                position = Vec3(position[0], position[1], position[2])
            except Exception as e:
                self.bot.chat("A coordinate type conversion error occurred.")
                return [] # Return an empty list on error
        elif not hasattr(position, 'offset'): # If there is no offset method (not Vec3)
            self.bot.chat("Invalid coordinate object type.")
            return [] # Return an empty list on error
        # --- End of addition ---

        x_dist = x_distance
        y_dist = y_distance
        z_dist = z_distance
        
        # Set sampling rate according to distance
        coords = []
        total_vol = (2 * x_dist + 1) * (2 * y_dist + 1) * (2 * z_dist + 1)
        
        # Sampling based on distance (thin out for larger ranges)
        if total_vol > 8000:  # If the range is large
            # Dense for short distances, sparse for long distances
            near_dist = 5  # Boundary for short distances
            
            # Near-distance zone (complete acquisition)
            for x in range(-min(near_dist, x_dist), min(near_dist, x_dist) + 1):
                for y in range(-min(near_dist, y_dist), min(near_dist, y_dist) + 1):
                    for z in range(-min(near_dist, z_dist), min(near_dist, z_dist) + 1):
                        coords.append(position.offset(x, y, z))
            
            # Middle zone (acquire every 2 blocks)
            mid_dist = 10
            if x_dist > near_dist or y_dist > near_dist or z_dist > near_dist:
                for x in range(-min(mid_dist, x_dist), min(mid_dist, x_dist) + 1, 2):
                    for y in range(-min(mid_dist, y_dist), min(mid_dist, y_dist) + 1, 2):
                        for z in range(-min(mid_dist, z_dist), min(mid_dist, z_dist) + 1, 2):
                            # Only add blocks not included in the near-distance zone
                            if abs(x) > near_dist or abs(y) > near_dist or abs(z) > near_dist:
                                coords.append(position.offset(x, y, z))
            
            # Far-distance zone (acquire every 3 blocks)
            if x_dist > mid_dist or y_dist > mid_dist or z_dist > mid_dist:
                for x in range(-x_dist, x_dist + 1, 3):
                    for y in range(-y_dist, y_dist + 1, 3):
                        for z in range(-z_dist, z_dist + 1, 3):
                            # Only add blocks not included in the middle zone
                            if abs(x) > mid_dist or abs(y) > mid_dist or abs(z) > mid_dist:
                                coords.append(position.offset(x, y, z))
            
        else:
            # If the range is small, acquire all blocks
            for x in range(-x_dist, x_dist + 1):
                for y in range(-y_dist, y_dist + 1):
                    for z in range(-z_dist, z_dist + 1):
                        coords.append(position.offset(x, y, z))

        # Determine batch size (process large requests by splitting them)
        batch_size = 500
        all_blocks = []
        
        # Batch processing
        for i in range(0, len(coords), batch_size):
            batch_end = min(i + batch_size, len(coords))
            batch = coords[i:batch_end]
            
            async def _get_block_async(position):
                return self.bot.blockAt(position)
            
            # Execute block acquisition within a batch in parallel
            batch_tasks = [_get_block_async(pos) for pos in batch]
            batch_results = await asyncio.gather(*batch_tasks)
            all_blocks.extend(batch_results)
        
        try:
            def chunks(lst, n):
                """Splits a list into n chunks"""
                for i in range(0, len(lst), n):
                    yield lst[i:i + n]
            
            def process_chunk(chunk):
                return [{'name': block.name, 'position': {'x': block.position.x, 'y': block.position.y, 'z': block.position.z}} 
                        for block in chunk if block and block.type != 0]
            
            # Calculate optimal chunk size based on CPU core count
            import os
            cpu_count = os.cpu_count() or 4
            chunk_size = max(100, len(all_blocks) // (cpu_count * 2))
            block_chunks = list(chunks(all_blocks, chunk_size))
            
            # Execute filtering with multi-threading
            with ThreadPoolExecutor(max_workers=cpu_count) as executor:
                filtered_chunks = list(executor.map(process_chunk, block_chunks))
            
            # Combine results
            surrounding_blocks = []
            for chunk in filtered_chunks:
                surrounding_blocks.extend(chunk)
                
        except ImportError:
            # If parallel processing library cannot be imported, use standard list comprehension
            surrounding_blocks = [
                {'name': block.name, 'position': {'x': block.position.x, 'y': block.position.y, 'z': block.position.z}}
                for block in all_blocks
                if block and block.type != 0
            ]
        
        return surrounding_blocks
    
    
    async def get_inventory_counts(self):
        """
        Returns the name and count of each item in the bot's inventory as a dictionary.

        Returns:
            dict: A dictionary where keys are item names and values are their quantities.
            
        Example:
            >>> get_inventory_counts()
            {'birch_planks': 1, 'dirt': 1}
        """
        print("Retrieving items in inventory.")
        inventory_counts = {}
        
        # Loop through all items in the inventory
        for item in self.bot.inventory.items():
            # If the item name is already in the dictionary, add to the count; otherwise, add new.
            if item.name in inventory_counts:
                inventory_counts[item.name] += item.count
            else:
                inventory_counts[item.name] = item.count
        await asyncio.sleep(0.1)
        print(inventory_counts)
        return inventory_counts
    
    async def get_nearest_block(self, block_name, max_distance=1000):
        """
        Searches for a block with the specified block name around the BOT and returns information about the closest block.
        
        Args:
            block_name (str): The name of the block to search for (e.g., "oak_log")
            max_distance (int): Maximum number of blocks to search (default is 1000)
            canMove (bool): Whether to return only reachable blocks. Default is True.
        Returns:
            Block: The closest block, or None if not found.
        
        Example:
            >>> get_nearest_block('oak_log')
            Block {
            type: 40,
            metadata: 1,
            light: 0,
            skyLight: 15,
            biome: {
                color: 0,
                height: null,
                name: '',
                rainfall: 0,
                temperature: 0,
                id: 1
            },
            position: Vec3 { x: -83, y: 73, z: 52 },
            name: 'oak_log',
            displayName: 'Oak Log',
            shapes: [ [ 0, 0, 0, 1, 1, 1 ] ],
            boundingBox: 'block',
            transparent: false,
            diggable: true,
            harvestTools: undefined,
            drops: [ 104 ]
            }
            >>> print(get_nearest_block('oak_log').position.x)
            -83
        """
        try:
            # Get block ID
            block_id = None
            if hasattr(self.bot.registry, 'blocksByName') and block_name in self.bot.registry.blocksByName:
                block_id = self.bot.registry.blocksByName[block_name].id
            else:
                print(f"get_nearest_block was executed, but block '{str(block_name)}' was not found as a minecraft block name")
                return None
                
            # Search for block
            blocks_pos = self.bot.findBlocks({
                'point': self.bot.entity.position,
                'matching': block_id,
                'maxDistance': max_distance,
                'count': 20
            })
            distance_min = None
            block_min = None
            # Is the distance calculation really working?
            for block_pos in blocks_pos:
                block = self.bot.blockAt(block_pos)
                distance = self.bot.entity.position.distanceTo(block_pos)
                if distance_min is None or distance < distance_min:
                    distance_min = distance
                    block_min = block
            if distance_min is None:
                return None
            return block_min
            
        except Exception as e:
            print(f"An error occurred during block search: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    async def get_nearest_free_space(self, X_size=1, Y_size=1, Z_size=1, distance=15, y_offset=0):
        """
        Finds an empty space of a specified size around the BOT (with air at the top and solid blocks at the bottom).
        
        Args:
            X_size (int): X size of the empty space to look for. (Minecraft block width)
            Y_size (int): Y size of the empty space to look for. (Minecraft block height)
            Z_size (int): Z size of the empty space to look for. (Minecraft block width)
            distance (int): Maximum distance to search. Default is 8.
            y_offset (int): Y coordinate offset to apply to the found empty space. Default is 0.
            
        Returns:
            Vec3: Coordinates of the southwest corner of the found empty space. If not found, returns the coordinates at the bot's feet.
        
        Example:
            >>> free_space = skills.get_nearest_free_space(2, 10)
            >>> print(f"Found empty space: x={free_space.x}, y={free_space.y}, z={free_space.z}")
        """
        self.bot.chat("Searching for empty space.")
        try:
            Vec3 = require('vec3')
            result = None
        
            # Search for air blocks
            empty_pos = self.bot.findBlocks({
                'point': self.bot.entity.position,
                'matching': self.mcdata.blocksByName['air'].id,
                'maxDistance': distance,
                'count': 1000
            })
            
            # For each air block, check for an empty space of the specified size
            for pos in empty_pos:
                empty = True

                # Skip if it's the same as the bot's position
                bot_pos = self.bot.blockAt(self.bot.entity.position).position
                if (pos.x == bot_pos.x and pos.y == bot_pos.y and pos.z == bot_pos.z):
                    continue
                # Check for empty space
                for x_offset in range(X_size):
                    for y_offset in range(Y_size):
                        for z_offset in range(Z_size):
                            # Check that the top blocks are air
                            top = self.bot.blockAt(Vec3(
                                pos.x + x_offset,
                                pos.y + y_offset,
                                pos.z + z_offset
                            ))
                            
                            # Check that the bottom blocks are diggable solid blocks
                            bottom = self.bot.blockAt(Vec3(
                                pos.x + x_offset,
                                pos.y - 1,
                                pos.z + z_offset
                            ))
                            # Condition check
                            if (not top or top.name != 'air' or 
                                not bottom or not hasattr(bottom, 'drops') or not bottom.diggable):
                                empty = False
                                break
                        
                        if not empty:
                            break
                
                # If a suitable space is found, return its position
                if empty:
                    result = pos
                    return result
            
            # If no suitable space is found, return None
            return None
            
        except Exception as e:
            # If an error occurs, return the default value
            self.bot.chat(f"An error occurred while searching for empty space: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # Output debug information
            position = self.bot.entity.position
            print(f"Debug: {position}")
            
            # Return the bot's foot coordinates as the default value
            return Vec3(int(position.x), int(position.y) + y_offset, int(position.z))
        
    async def craft_items(self, item_name, num=1):
        """
        Crafts the specified number of items.
        
        This method performs the following operations:
        1. Searches for the recipe of the specified item
        2. If the obtained recipe requires a crafting table, it places a crafting table from the inventory or searches for a nearby crafting table
        3. Checks if the necessary materials are in the inventory
        4. Executes crafting
        5. Returns the result and details of the crafted item
        
        Args:
            item_name (str): Name of the item to craft. Uses Minecraft internal item names
                             (e.g.: "stick", "crafting_table", "wooden_pickaxe")
            num (int): Quantity to craft. Default is 1
            
        Returns:
            dict: Dictionary containing the result
                - success (bool): True if creation was successful, False if failed
                - message (str): Result message
                - error (str, optional): Error code if an error occurred
                - exception (str, optional): Exception message if an exception occurred
                - item (str): Name of the item that was attempted to be crafted
                - count (int): Quantity that was attempted to be crafted
        """
        self.bot.chat(f"Will create {str(num)} {str(item_name)}.")
        result = {
            "success": False,
            "message": "",
            "item": item_name,
            "count": num
        }
        
        try:
            placed_table = False
            
            # Check if recipe exists
            item_id = self._get_item_id(item_name)
            
            recipes = self.bot.recipesFor(item_id, None, num, None)
            crafting_table_recipes = self.bot.recipesFor(item_id, None, num, True)
            if not any(True for _ in recipes) and not any(True for _ in crafting_table_recipes):
                # If materials are insufficient, check required materials
                required_materials = []
                # Get required materials from recipe
                recipe_data = self.get_item_crafting_recipes(item_name)
                if recipe_data and recipe_data[0]:
                    recipe_dict = recipe_data[0][0]
                    required_materials = [f"{key}: {value}" for key, value in recipe_dict.items()]
                else:
                    required_materials.append("Recipe not found")
                
                error_msg = f"Insufficient materials to create {str(item_name)}"
                if required_materials:
                    error_msg += f". Required materials: {', '.join(required_materials)}"
                    
                self.bot.chat(error_msg)
                result["message"] = error_msg
                result["error"] = "insufficient_materials"
                
                if placed_table:
                    await self.collect_block('crafting_table', 1)
                return result

            crafting_table = None
            crafting_table_range = 32

            # If a crafting table is needed
            if not any(True for _ in recipes) and any(True for _ in crafting_table_recipes):  # Proxy object empty check
                recipes = self.bot.recipesFor(item_id, None, num, True)
                if not recipes:
                    self.bot.chat(f"Recipe for {str(item_name)} not found")
                    error_msg = f"Recipe for {str(item_name)} not found"
                    self.bot.chat(error_msg)
                    result["message"] = error_msg
                    result["error"] = "recipe_not_found"
                    return result
                    
                # Search for a crafting table
                crafting_table = await self.get_nearest_block('crafting_table', crafting_table_range)
                if not crafting_table:
                    # Check if there is a crafting table in inventory
                    if (await self.get_inventory_counts()).get('crafting_table', 0) > 0:
                        # Place crafting table
                        pos = await self.get_nearest_free_space(X_size=1,Z_size=1,distance=6)
                        place_result =await self.place_block('crafting_table', pos.x, pos.y, pos.z)
                        if not place_result["success"]:
                            result["message"] = place_result["message"]
                            result["error"] = "crafting_table_placement_failed"
                            self.bot.chat(place_result["message"])
                            print(result)
                            return result

                        crafting_table = await self.get_nearest_block('crafting_table', crafting_table_range)
                        if crafting_table:
                            recipes = self.bot.recipesFor(item_id, None, 1, crafting_table)
                            placed_table = True
                    else:
                        self.bot.chat(f"A crafting table is required to create {str(item_name)}, but no crafting table was found within 32 blocks and there is no crafting table in the inventory, so it cannot be created")
                        error_msg = f"A crafting table is required to create {str(item_name)}, but no crafting table was found within 32 blocks and there is no crafting table in the inventory, so it cannot be created"
                        self.bot.chat(error_msg)
                        result["message"] = error_msg
                        result["error"] = "crafting_table_required"
                        return result
                else:
                    # If there is a crafting table nearby, get the recipe
                    recipes = self.bot.recipesFor(item_id, None, 1, crafting_table)
                
            # Move to crafting table
            if crafting_table and self.bot.entity.position.distanceTo(crafting_table.position) > 4:
                move_result = await self.move_to_position(crafting_table.position.x, crafting_table.position.y, crafting_table.position.z)
                if not move_result:
                    error_msg = "Cannot move to crafting table"
                    self.bot.chat(str(error_msg))
                    result["message"] = error_msg
                    result["error"] = "movement_failed"
                    return result
                
            recipe = recipes[0]
            try:

                # Recipe validity check
                if not recipe or not hasattr(recipe, 'result'):
                    error_msg = f"No valid recipe found for {str(item_name)}"
                    self.bot.chat(str(error_msg))
                    result["message"] = error_msg
                    result["error"] = "invalid_recipe"
                    return result

                # Execute craft
                self.bot.craft(recipe, num, crafting_table)
                success_msg = f"Created {str(num)} {str(item_name)}"
                self.bot.chat(success_msg)
                
                # Collect placed crafting table
                if placed_table:
                    await self.collect_block('crafting_table', 1)
                
                result["success"] = True
                result["message"] = success_msg
                return result
                
            except Exception as e:
                error_msg = f"An error occurred during crafting: {str(e)}"
                self.bot.chat(str(error_msg))
                result["message"] = error_msg
                result["error"] = "crafting_error"
                result["exception"] = str(e)
                
                if placed_table:
                    await self.collect_block('crafting_table', 1)
                return result
                
        except Exception as e:
            error_msg = f"An unexpected error occurred: {str(e)}"
            self.bot.chat(str(error_msg))
            result["message"] = error_msg
            result["error"] = "unexpected_error"
            result["exception"] = str(e)
            import traceback
            traceback.print_exc()
            return result
        
    async def place_block(self, block_name, x, y, z, place_on='bottom'):
        """
        Places a block at the specified coordinates. Places from an adjacent block.
        Fails if there is a block at the placement location or no place to install.
        
        Args:
            block_name (str): The name of the block to place
            x : X coordinate to place
            y : Y coordinate to place
            z : Z coordinate to place
            place_on (str): The preferred direction of the face to place on. Select from 'top', 'bottom', 'north', 'south', 'east', 'west', 'side'. Default is 'bottom'
            dont_cheat (bool): Whether to place blocks in the normal way even in cheat mode. Default is False
            
        Returns:
            dict: Dictionary containing the results
                - success (bool): True if placed successfully, False if failed
                - message (str): Result message
                - position (dict): Position attempted to place {x, y, z}
                - block_name (str): Name of the block attempted to place
                - error (str, optional): Error code if there is an error
        """
        self.bot.chat(f"Placing {block_name} at coordinates ({x}, {y}, {z}).")
        result = {
            "success": False,
            "message": "",
            "position": {"x": x, "y": y, "z": z},
            "block_name": block_name
        }
        
        # Validate Block ID
        try:
            block_id = None
            
            # Get ID from block name
            block_id = self._get_item_id(block_name)
    
            if block_id is None:
                self.bot.chat(f"Invalid block name: {block_name}")
                result["message"] = f"Invalid block name: {block_name}"
                result["error"] = "invalid_block_name"
                self.bot.chat(result["message"])
                return result
        except Exception as e:
            self.bot.chat(f"An error occurred during block name validation: {str(e)}")
            result["message"] = f"An error occurred during block name validation: {str(e)}"
            result["error"] = "block_validation_error"
            self.bot.chat(result["message"])
            return result
            
        # Create Vec3 object
        Vec3 = require('vec3')
        target_dest = Vec3(int(x), int(y), int(z))
        
        try:
            # Fix item name (some blocks change names when placed)
            item_name = block_name
            if item_name == "redstone_wire":
                item_name = "redstone"
                
            # Find block in inventory
            block_item = None
            for item in self.bot.inventory.items():
                if item.name == item_name:
                    block_item = item
                    break
            
            # Fail if block is not found
            if not block_item:
                result["message"] = f"You do not have {block_name} in your inventory"
                result["error"] = "item_not_in_inventory"
                self.bot.chat(result["message"])
                return result
                
            # Check the block at the target location
            target_block = self.bot.blockAt(target_dest)
            if target_block.name == block_name:
                result["message"] = f"{block_name} is already at coordinates ({target_block.position})"
                result["error"] = "block_already_exists"
                self.bot.chat(result["message"])
                return result
                
            # Check if the space is placeable
            empty_blocks = ['air', 'water', 'lava', 'grass', 'short_grass', 'tall_grass', 'snow', 'dead_bush', 'fern']
            if target_block.name not in empty_blocks:
                result["message"] = f"At coordinates ({target_block.position}) there is already {target_block.name}"
                
                # Attempt to break
                break_result = await self._break_block_at(x, y, z)
                if not break_result["success"]:
                    result["message"] = f"There is {target_block.name} at the block placement location, and it could not be broken"
                    result["error"] = "space_occupied"
                    self.bot.chat(result["message"])
                    return result
                    
                # Wait a bit until the block is broken
                await asyncio.sleep(0.2)
                
            # Create map of placement directions
            dir_map = {
            'top': Vec3(0, 1, 0),
            'bottom': Vec3(0, -1, 0),
            'north': Vec3(0, 0, -1),
            'south': Vec3(0, 0, 1),
            'east': Vec3(1, 0, 0),
            'west': Vec3(-1, 0, 0)
            }
        
            # Create list of placement directions
            directions = []
            if place_on == 'side':
                # Prioritize placement on the side
                directions.extend([dir_map['north'], dir_map['south'], dir_map['east'], dir_map['west']])
            elif place_on in dir_map:
                # Prioritize specified direction
                directions.append(dir_map[place_on])
            else:
                # Default is bottom face
                directions.append(dir_map['bottom'])
                result["message"] += f"\nUnknown placement direction '{place_on}' was specified. Using default 'bottom'."
                
            # Add other directions (low priority)
            for direction in dir_map.values():
                if not any(d.x == direction.x and d.y == direction.y and d.z == direction.z for d in directions):
                    directions.append(direction)
                    
            # Find a placeable block
            build_off_block = None
            face_vec = None
            
            for direction in directions:
                ref_pos = target_dest.plus(direction)
                ref_block = self.bot.blockAt(ref_pos)
                
                if ref_block and ref_block.name not in empty_blocks:
                    build_off_block = ref_block
                    # Reverse direction (placement face is opposite side)
                    face_vec = Vec3(-direction.x, -direction.y, -direction.z)
                    break
                    
            # If no placeable block
            if not build_off_block:
                result["message"] = f"At coordinates ({target_dest}) there is no placeable block face"
                result["error"] = "no_adjacent_block"
                self.bot.chat(result["message"])
                return result
                
            # Check the positional relationship between player and block
            player_pos = self.bot.entity.position
            player_pos_above = player_pos.plus(Vec3(0, 1, 0))
            
            # Some blocks can be placed without moving
            dont_move_for = [
                'torch', 'redstone_torch', 'redstone_wire', 'lever', 'button', 
                'rail', 'detector_rail', 'powered_rail', 'activator_rail', 
                'tripwire_hook', 'tripwire', 'water_bucket'
            ]
            
            # Check if the block's placement position and player are not overlapping
            if block_name not in dont_move_for and (
                player_pos.distanceTo(target_block.position) < 1 or 
                player_pos_above.distanceTo(target_block.position) < 1
            ):
                # If the player is overlapping with the placement position, move away slightly
                try:
                    goal = self.pathfinder.goals.GoalNear(target_block.position.x, target_block.position.y, target_block.position.z, 2)
                    inverted_goal = self.pathfinder.goals.GoalInvert(goal)
                    self.bot.pathfinder.goto(inverted_goal)
                except Exception as e:
                    result["message"] = f"An error occurred when moving away from the placement position: {str(e)}"
                    result["error"] = "movement_error"
                    self.bot.chat(result["message"])
                    return result
            
            # If the block is too far, approach it
            if self.bot.entity.position.distanceTo(target_block.position) > 4.5:
                try:
                    await self.move_to_position(target_block.position.x, target_block.position.y, target_block.position.z, 4)
                except Exception as e:
                    result["message"] = f"An error occurred when approaching the block: {str(e)}"
                    result["error"] = "movement_error"
                    self.bot.chat(result["message"])
                    return result
                    
            # Hold the block in hand
            self.bot.equip(block_item, 'hand')
            
            # Look at the target block for placement
            self.bot.lookAt(build_off_block.position)
            
            # Place the block
            try:
                self.bot.placeBlock(build_off_block, face_vec)
                result["message"] = f"{block_name} was placed at coordinates({target_dest})"
                result["success"] = True
                self.bot.chat(result["message"])
                
                # Wait a little for placement to complete
                await asyncio.sleep(0.2)
                return result
            except Exception as e:
                result["message"] = f"An error occurred during the placement of {block_name}: {str(e)}"
                result["error"] = "block_placement_error"
                self.bot.chat(result["message"])
                return result
                
        except Exception as e:
            result["message"] = f"An unexpected error occurred during block placement processing: {str(e)}"
            result["error"] = "unexpected_error"
            self.bot.chat(result["message"])
            import traceback
            traceback.print_exc()
            return result
    
    async def equip(self, item_name):
        """
        Equips the specified item into the appropriate equipment slot (e.g., tools, armor).
        
        Args:
            item_name (str): Name of the item or block to equip
            
        Returns:
            dict: Dictionary containing the result
                - success (bool): True if equipped successfully, False if it failed
                - message (str): Result message
                - item (str): Name of the item attempted to be equipped
        """
        result = {
            "success": False,
            "message": "",
            "item": item_name
        }
        
        try:
            # Search for item in inventory
            item = None
            for slot in self.bot.inventory.slots:
                if slot and slot.name == item_name:
                    item = slot
                    break
                    
            if not item:
                result["message"] = f"{item_name} cannot be equipped. It is not in your inventory."
                self.bot.chat(result["message"])
                return result
                
            # Determine equipment slot based on item type
            if "leggings" in item_name:
                self.bot.equip(item, "legs")
                slot_type = "Legs"
            elif "boots" in item_name:
                self.bot.equip(item, "feet")
                slot_type = "Feet"
            elif "helmet" in item_name:
                self.bot.equip(item, "head")
                slot_type = "Head"
            elif "chestplate" in item_name or "elytra" in item_name:
                self.bot.equip(item, "torso")
                slot_type = "Torso"
            elif "shield" in item_name:
                self.bot.equip(item, "off-hand")
                slot_type = "Off-hand"
            else:
                self.bot.equip(item, "hand")
                slot_type = "Main hand"
                
            result["success"] = True
            result["message"] = f"{item_name} was equipped to the {slot_type}."
            self.bot.chat(result["message"])
            return result
            
        except Exception as e:
            result["message"] = f"An error occurred while equipping {item_name}: {str(e)}"
            self.bot.chat(result["message"])
            return result
            
    async def discard(self, item_name, num=-1):
        """
        Discards the specified item.
        
        Args:
            item_name (str): Name of the item or block to discard
            num (int): Number of items to discard. Default is -1, which discards all items.
            
        Returns:
            dict: Dictionary containing the result
                - success (bool): True if item was discarded successfully, False if it failed
                - message (str): Result message
                - item (str): Name of the item attempted to be discarded
                - count (int): Number of items discarded
        """
        result = {
            "success": False,
            "message": "",
            "item": item_name,
            "count": 0
        }
        
        try:
            discarded = 0
            
            while True:
                # Search for item in inventory
                item = None
                for slot_item in self.bot.inventory.items():
                    if slot_item and slot_item.name == item_name:
                        item = slot_item
                        break
                
                if not item:
                    break
                
                # Calculate number to discard
                to_discard = item.count if num == -1 else min(num - discarded, item.count)
                
                # Discard item
                self.bot.toss(item.type, None, to_discard)
                discarded += to_discard
                
                # Exit after discarding the specified number
                if num != -1 and discarded >= num:
                    break
            
            if discarded == 0:
                result["message"] = f"{item_name} cannot be discarded. It is not in your inventory."
                self.bot.chat(result["message"])
                return result
            
            result["success"] = True
            result["count"] = discarded
            result["message"] = f"{discarded} of {item_name} was discarded."
            self.bot.chat(result["message"])
            return result
            
        except Exception as e:
            result["message"] = f"An error occurred while discarding {item_name}: {str(e)}"
            self.bot.chat(result["message"])
            return result

    async def put_in_chest(self, item_name, num=-1):
        """
        Puts the specified item into the nearest chest. Tools with a stack count of 1, etc., can only be put in one at a time. In that case, please execute multiple times.

        Args:
            item_name (str): Name of the item or block to put into the chest
            num (int): Number of items to put into the chest. Default is -1, which puts all items.
            
        Returns:
            dict: Dictionary containing the result
                - success (bool): True if item was successfully placed in chest, False if failed
                - message (str): Result message
                - item (str): Name of item attempted to place in chest
                - count (int): Number of items placed in chest
        """
        result = {
            "success": False,
            "message": "",
            "item": item_name,
            "count": 0
        }
        
        try:
            # Find the closest chest
            chest = await self.get_nearest_block("chest", 32)
            if not chest:
                result["message"] = "No chest was found nearby."
                self.bot.chat(result["message"])
                return result
                
            # Search for item in inventory
            item = None
            for slot_item in self.bot.inventory.items():
                if slot_item and slot_item.name == item_name:
                    item = slot_item
                    break
                    
            if not item:
                result["message"] = f"{item_name} cannot be put into the chest. It's not in the inventory."
                self.bot.chat(result["message"])
                return result
                
            # Calculate the number to put into the chest
            to_put = item.count if num == -1 else min(num, item.count)
            
            # Move to the chest
            await self.move_to_position(chest.position.x, chest.position.y, chest.position.z, 2)
            
            # Open the chest
            chest_container = self.bot.openContainer(chest)
            
            # Put items into the chest
            chest_container.deposit(item.type, None, to_put)
            
            # Close the chest
            chest_container.close()
            
            result["success"] = True
            result["count"] = to_put
            result["message"] = f"{to_put} {item_name}s were placed in the chest."
            self.bot.chat(result["message"])
            return result
            
        except Exception as e:
            result["message"] = f"An error occurred when putting {item_name} into the chest: {str(e)}"
            self.bot.chat(result["message"])
            return result

    async def take_from_chest(self, item_name, num=-1):
        """
        Retrieves the specified item from the closest chest.
        
        Args:
            item_name (str): Name of the item or block to retrieve from the chest
            num (int): Number of items to retrieve from the chest. Default is -1 to retrieve all items.
            
        Returns:
            dict: Dictionary containing the result
                - success (bool): True if item was successfully retrieved from chest, False if failed
                - message (str): Result message
                - item (str): Name of item attempted to retrieve from chest
                - count (int): Number of items retrieved from chest
        """
        result = {
            "success": False,
            "message": "",
            "item": item_name,
            "count": 0
        }
        
        try:
            # Find the closest chest
            chest = await self.get_nearest_block("chest", 32)
            if not chest:
                result["message"] = "No chest was found nearby."
                self.bot.chat(result["message"])
                return result
                
            # Move to the chest
            await self.move_to_position(chest.position.x, chest.position.y, chest.position.z, 2)
            
            # Open the chest
            chest_container = self.bot.openContainer(chest)
            
            # Search for items in the chest
            item = None
            for container_item in chest_container.containerItems():
                if container_item and container_item.name == item_name:
                    item = container_item
                    break
                    
            if not item:
                result["message"] = f"{item_name} was not found in the chest."
                chest_container.close()
                self.bot.chat(result["message"])
                return result
                
            # Calculate the number to retrieve
            to_take = item.count if num == -1 else min(num, item.count)
            
            # Retrieve items from the chest
            chest_container.withdraw(item.type, None, to_take)
            
            # Close the chest
            chest_container.close()
            
            result["success"] = True
            result["count"] = to_take
            result["message"] = f"{to_take} {item_name}s were retrieved from the chest."
            self.bot.chat(result["message"])
            return result
            
        except Exception as e:
            result["message"] = f"An error occurred when retrieving {item_name} from the chest: {str(e)}"
            self.bot.chat(result["message"])
            return result

    async def view_chest(self,maxDistance=32):
        """
        Moves to a nearby chest and displays its contents. If there are multiple chests, the contents of all chests will be displayed.
        
        Returns:
            dict: Dictionary containing the result
                - success (bool): True if chest contents were displayed successfully, False if failed
                - message (str): Result message
                - result_list (list, optional): List of items in the chest (only on success)

        Example:
            >>> view_chest()
            {
                'success': True, 
                'message': 'Found 2 chests.',
                'result_list':
                    [
                        {
                            'position': {'x': 1, 'y': -60, 'z': 4}, 
                            'items': [{'name': 'wooden_pickaxe', 'count': 1}, {'name': 'wooden_pickaxe', 'count': 1}, {'name': 'wooden_pickaxe', 'count': 1}, {'name': 'wooden_pickaxe', 'count': 1}]
                        }, 
                        {
                            'position': {'x': -2, 'y': -60, 'z': 0}, 
                            'items': 'The chest is empty.'
                        }
                    ]
            }
        """
        result = {
            "success": False,
            "message": ""
        }
        
        try:
            # Find the nearest chest
            chest = self.bot.findBlocks({
                'matching':self.mcdata.blocksByName['chest'].id,
                'maxDistance': maxDistance,
                'count': 10
            })
            if not any(True for _ in chest):
                result["message"] = "No chest found nearby."
                self.bot.chat(result["message"])
                return result
            
            result_list = []
            for chest_pos in chest:
                # Move to the chest
                move_result = await self.move_to_position(chest_pos.x, chest_pos.y, chest_pos.z, 2)
                if not move_result["success"]:
                    result["message"] = f"Failed to move to the chest: {move_result.get('message', 'Unknown error')}"
                    self.bot.chat(result["message"])
                    return result
            
                # Open the chest
                chest_block = self.bot.blockAt(chest_pos)
                chest_container = self.bot.openContainer(chest_block)
            
                # Get items inside the chest
                items = chest_container.containerItems()
            
                # Convert items to a list
                item_list = []
                result_dict = {}
                if items:
                    for item in items:
                        if item:  # Add only non-None items
                            item_list.append({
                                "name": item.name,
                                "count": item.count
                            })
                if not item_list:
                    result_dict["position"] = {"x": chest_pos.x, "y": chest_pos.y, "z": chest_pos.z}
                    result_dict["items"] = "The chest is empty."
                else:
                    result_dict["position"] = {"x": chest_pos.x, "y": chest_pos.y, "z": chest_pos.z}
                    result_dict["items"] = item_list
                result_list.append(result_dict)
                
                chest_container.close()
            
            result["success"] = True
            result["message"] = f"Found {len(result_list)} chests."
            result["result_list"] = result_list
            return result
            
        except Exception as e:
            result["message"] = f"An error occurred while displaying the chest: {str(e)}"
            self.bot.chat(result["message"])
            return result

    async def consume(self, item_name=""):
        """
        Eats/drinks one of the specified items.
        Cannot consume if hunger is at maximum.
        
        Args:
            item_name (str): The name of the item to eat/drink. Defaults to an empty string, in which case the item held in hand is consumed.
        """
        result = {
            "success": False,
            "message": ""
        }
        
        try:
            # Hunger check
            if hasattr(self.bot, 'food') and self.bot.food >= 20:
                result["message"] = "Hunger is at maximum, cannot consume more food."
                self.bot.chat(result["message"])
                return result

            item = None
            name = item_name
            
            # If item name is specified, search from inventory
            if item_name:
                for inv_item in self.bot.inventory.items():
                    if inv_item.name == item_name:
                        item = inv_item
                        break
            
            # If item not found
            if not item:
                result["message"] = f"Cannot consume {name if name else 'the specified item'}. Item not in inventory."
                self.bot.chat(result["message"])
                return result
                
            # Hold the item in hand
            self.bot.equip(item, 'hand')
            
            # Consume the item
            self.bot.consume()
            
            result["success"] = True
            result["item"] = item.name
            result["message"] = f"Consumed {item.name}."
            self.bot.chat(result["message"])
            return result
            
        except Exception as e:
            result["message"] = f"An error occurred while consuming the item: {str(e)}"
            self.bot.chat(result["message"])
            return result

    async def go_to_nearest_block(self, block_name, min_distance=2, range=64):
        """
        Moves to the nearest block of the specified type.
        
        Args:
            block_name (str): The name of the block to move to
            min_distance (int): Distance to keep from the block. Defaults to 2
            range (int): Maximum range to search for blocks. Defaults to 64
            
        Returns:
            dict: Dictionary containing the results
                - success (bool): True if moved to the block, False if failed
                - message (str): Result message
                - block_name (str): The name of the block searched for
                - position (dict, optional): Position of the found block {x, y, z} (only on success)
        """
        result = {
            "success": False,
            "message": "",
            "block_name": block_name
        }
        
        try:
            # Limit maximum search range
            MAX_RANGE = 512
            if range > MAX_RANGE:
                range = MAX_RANGE
                self.bot.chat(f"Limiting maximum search range to {MAX_RANGE} blocks.")
                
            # Find the nearest block
            block = await self.get_nearest_block(self._get_item_id(block_name), range)
            if not block:
                result["message"] = f"No {block_name} found within {range} blocks."
                self.bot.chat(result["message"])
                return result
                
            # Get block position
            position = block.position
            result["position"] = {
                "x": position.x,
                "y": position.y,
                "z": position.z
            }
            
            # Move to the block
            move_result = await self.move_to_position(position.x, position.y, position.z, min_distance)
            if not move_result["success"]:
                result["message"] = f"An error occurred while moving to {block_name}: {move_result['message']}"
                self.bot.chat(result["message"])
                return result
                
            result["success"] = True
            result["message"] = f"Reached {block_name}(X:{position.x}, Y:{position.y}, Z:{position.z})."
            self.bot.chat(result["message"])
            return result
            
        except Exception as e:
            result["message"] = f"An unexpected error occurred while moving to {block_name}: {str(e)}"
            self.bot.chat(result["message"])
            import traceback
            traceback.print_exc()
            return result

    async def go_to_nearest_entity(self, entity_type, min_distance=2, range=64):
        """
        Moves to the nearest entity of the specified type.
        
        Args:
            entity_type (str): The entity type to move to (e.g., "zombie", "sheep", "villager", etc.)
            min_distance (int): The distance to maintain from the entity after moving. Default is 2
            range (int): The maximum range to search for the entity. Default is 64
            
        Returns:
            dict: Dictionary containing the result
                - success (bool): True if moved to the entity successfully, False otherwise
                - message (str): Result message
                - entity_type (str): The entity type searched for
                - position (dict, optional): Entity's position {x, y, z} (only on success)
                - distance (float, optional): Distance from original position to entity (only on success)
        """
        result = {
            "success": False,
            "message": "",
            "entity_type": entity_type
        }
        
        try:
            # Search for an entity of the specified type
            entity = self._get_nearby_entity_of_type(entity_type, range)
            if not entity:
                result["message"] = f"No {entity_type} found within {range} blocks."
                self.bot.chat(result["message"])
                return result
                
            # Get entity's position
            position = entity.position
            result["position"] = {
                "x": position.x,
                "y": position.y,
                "z": position.z
            }
            
            # Calculate distance to entity
            distance = self.bot.entity.position.distanceTo(position)
            result["distance"] = distance
            
            # Notify that an entity was found
            self.bot.chat(f"{entity_type} found {distance} blocks away.")
            
            # Move to entity
            move_result = await self.move_to_position(position.x, position.y, position.z, min_distance)
            if not move_result["success"]:
                result["message"] = f"An error occurred while moving to {entity_type}: {move_result['message']}"
                self.bot.chat(result["message"])
                return result
                
            result["success"] = True
            result["message"] = f"Reached {entity_type}."
            self.bot.chat(result["message"])
            return result
            
        except Exception as e:
            result["message"] = f"An unexpected error occurred while moving to {entity_type}: {str(e)}"
            self.bot.chat(result["message"])
            import traceback
            traceback.print_exc()
            return result

    async def go_to_bed(self):
        """
        Sleeps in the nearest bed.
        
        Returns:
            dict: Dictionary containing the result
                - success (bool): True if able to sleep in the bed, False otherwise
                - message (str): Result message
                - bed_position (dict, optional): Bed's position {x, y, z} (only on success)
        """
        result = {
            "success": False,
            "message": ""
        }
        
        try:
            # Check time and weather
            if not (self.bot.time.isNight or self.bot.isRaining):
                result["message"] = "It is not yet time to sleep. You can only sleep at night or during a thunderstorm."
                self.bot.chat(result["message"])
                return result
            
            # Search for a nearby bed
            # Search for beds using the isABed method
            beds = self.bot.findBlocks({
                'matching': self.bot.isABed,
                'maxDistance': 32,
                'count': 1
            })
            
            if not beds or not any(True for _ in beds):
                result["message"] = "No bed to sleep in found within 32 blocks."
                self.bot.chat(result["message"])
                return result
                
            # Get bed's position
            bed_pos = beds[0]
            result["bed_position"] = {
                "x": bed_pos.x,
                "y": bed_pos.y,
                "z": bed_pos.z
            }
            
            # Move to bed
            await self.move_to_position(bed_pos.x, bed_pos.y, bed_pos.z)
            
            # Get bed block
            bed = self.bot.blockAt(bed_pos)
            
            try:
                # Sleep in the bed
                await self.bot.sleep(bed)
                result["success"] = True
                result["message"] = "Successfully slept in the bed."
                self.bot.chat(result["message"])
                
            except Exception as e:
                result["message"] = f"An error occurred while sleeping in the bed: {str(e)}"
                self.bot.chat(result["message"])
                
            return result
            
        except Exception as e:
            result["message"] = f"An error occurred while sleeping in the bed: {str(e)}"
            self.bot.chat(result["message"])
            import traceback
            traceback.print_exc()
            return result

    async def move_away(self, distance):
        """
        Moves a specified distance in any direction from the current position.
        
        Args:
            distance (int): The distance to move
            
        Returns:
            dict: Dictionary containing the result
                - success (bool): If movement is successful, True; if it fails, False
                - message (str): Result message
                - start_position (dict): Start position {x, y, z}
                - end_position (dict, optional): Position after movement {x, y, z} (only on success)
        """
        result = {
            "success": False,
            "message": "",
            "start_position": {
                "x": self.bot.entity.position.x,
                "y": self.bot.entity.position.y,
                "z": self.bot.entity.position.z
            }
        }
        
        try:
            # Get current position
            current_pos = self.bot.entity.position
            
            # Set a goal to move away from the current position using GoalNear and GoalInvert
            if hasattr(self.pathfinder.goals, 'GoalNear') and hasattr(self.pathfinder.goals, 'GoalInvert'):
                goal = self.pathfinder.goals.GoalNear(current_pos.x, current_pos.y, current_pos.z, distance)
                inverted_goal = self.pathfinder.goals.GoalInvert(goal)
                
                # Pathfinder settings
                self.bot.pathfinder.setMovements(self.pathfinder.Movements(self.bot))
                
                # Teleport if in cheat mode
                if hasattr(self.bot.modes, 'isOn') and self.bot.modes.isOn('cheat'):
                    try:
                        move = self.pathfinder.Movements(self.bot)
                        path = self.bot.pathfinder.getPathTo(move, inverted_goal, 10000)
                        
                        if path and path.path and len(path.path) > 0:
                            last_move = path.path[len(path.path) - 1]
                            
                            if last_move:
                                x = int(last_move.x)
                                y = int(last_move.y)
                                z = int(last_move.z)
                                
                                self.bot.chat(f"/tp @s {x} {y} {z}")
                                result["success"] = True
                                result["message"] = f"Teleported to coordinates ({x}, {y}, {z}), {distance} blocks away from the current position."
                                result["end_position"] = {"x": x, "y": y, "z": z}
                                self.bot.chat(result["message"])
                                return result
                    except Exception as e:
                        print(f"Movement calculation error in cheat mode: {e}")
                        # Attempt normal movement
                
                # Move using pathfinder
                self.bot.pathfinder.goto(inverted_goal)
                
                # Get new position
                new_pos = self.bot.entity.position
                result["end_position"] = {
                    "x": new_pos.x,
                    "y": new_pos.y,
                    "z": new_pos.z
                }
                
                result["success"] = True
                result["message"] = f"Moved to coordinates ({new_pos.x:.1f}, {new_pos.y:.1f}, {new_pos.z:.1f}), {distance} blocks away from the current position."
                self.bot.chat(result["message"])
                return result
            else:
                result["message"] = "Pathfinder goal function is not available."
                self.bot.chat(result["message"])
                return result
                
        except Exception as e:
            result["message"] = f"An unexpected error occurred during movement: {str(e)}"
            self.bot.chat(result["message"])
            import traceback
            traceback.print_exc()
            return result

    async def avoid_enemies(self, distance=16):
        """
        Escape from hostile entities in the vicinity.
        Find and move to the furthest place from all nearby hostile entities. Stop after reaching the destination.
        
        Args:
            distance (int): Maximum escape distance
            
        Returns:
            dict: Dictionary containing results
        """
        result = {
            "success": False,
            "message": ""
        }
        
        # Get all nearby entities
        nearby_entities = self._get_nearby_entities(distance)
        
        # Filter hostile entities
        hostile_entities = [entity for entity in nearby_entities if self._is_hostile(entity)]
        
        if not hostile_entities:
            result["message"] = "No hostile entities nearby."
            self.bot.chat(result["message"])
            return result
            
        self.bot.chat(f"Escaping from {len(hostile_entities)} hostile entities.")
        
        # Current player position
        player_pos = self.bot.entity.position
        
        # Calculate repulsion vector from each enemy (direction to move player away from each enemy)
        escape_vector = {'x': 0, 'y': 0, 'z': 0}
        
        for entity in hostile_entities:
            # Direction vector from entity to player
            dx = player_pos.x - entity.position.x
            dy = player_pos.y - entity.position.y
            dz = player_pos.z - entity.position.z
            
            # Distance to entity
            dist = (dx**2 + dy**2 + dz**2) ** 0.5
            
            if dist < 0.1:  # If extremely close, escape in a slightly random direction
                import random
                dx = random.uniform(-1, 1)
                dz = random.uniform(-1, 1)
                dist = (dx**2 + dz**2) ** 0.5
            
            # Use inverse of distance as weight (flee more strongly from closer enemies)
            weight = 1.0 / (dist + 0.1)  # Prevent division by zero
            
            # Normalize (unit vector) and weight
            norm = (dx**2 + dz**2) ** 0.5  # Horizontal distance
            if norm > 0:
                escape_vector['x'] += (dx / norm) * weight
                escape_vector['z'] += (dz / norm) * weight
        
        # Calculate final movement distance (vector normalization)
        magnitude = (escape_vector['x']**2 + escape_vector['z']**2) ** 0.5
        if magnitude > 0:
            escape_vector['x'] /= magnitude
            escape_vector['z'] /= magnitude
        else:
            # If enemies are equally distributed in all directions, escape in a random direction
            import random
            angle = random.uniform(0, 2 * 3.14159)
            escape_vector['x'] = math.cos(angle)
            escape_vector['z'] = math.sin(angle)
        
        # Calculate final target position (current position + movement distance * direction vector)
        target_x = player_pos.x + distance * escape_vector['x'] # Direction away from enemy
        target_z = player_pos.z + distance * escape_vector['z'] # Direction away from enemy
        
        # Move to destination
        self.bot.chat(f"Escaping in the direction of x:{target_x:.1f}, z:{target_z:.1f}.")
        await self.move_to_position(target_x, player_pos.y, target_z, min_distance=2,canDig=False)
        
        result["success"] = True
        result["message"] = "Escaped from hostile entity."
        self.bot.chat(result["message"])
        return result

    async def collect_block(self, block_name, num=1, exclude=None):
        """
        Mines and collects the specified number of blocks with the given name.
        最も近くにある安全に採掘可能なブロックを探し、適切なツールを装備して収集を試みます。
        座標がわからない特定のブロックの採掘や収集に向いてます。
        インベントリがいっぱいの場合や適切なツールがない場合などは失敗します。

        Args:
            block_name (str): 収集するブロックの名前 (例: "oak_log", "stone", "coal_ore")。
                            鉱石の場合、"coal" のように指定しても "coal_ore" や "deepslate_coal_ore" を探します。
                            "dirt" を指定すると "grass_block" も対象になります。
            num (int, optional): 収集する目標のブロック数。Defaults to 1.
            exclude (list[Vec3], optional): 収集対象から除外するブロックの座標 (Vec3オブジェクト) のリスト。
                                         特定の場所にあるブロックを無視したい場合に使用します。Defaults to None.

        Returns:
            dict: 収集結果の詳細を含む辞書。
                - success (bool): 1つ以上のブロック収集に成功した場合 True、そうでなければ False。
                - message (str): 処理結果を示すメッセージ。
                - result (dict): 収集後のインベントリ情報。
                - block_name (str): 収集しようとした元のブロック名。
                - error (str, optional): エラーが発生した場合のエラーコード。
        Example:
            >> await skills.collect_block('cobblestone', num=11)
            {
                "success": True,
                "message": "11個のcobblestoneを収集しました。",
                "result": {'cobblestone': 11, 'stone_pickaxe': 1},
                "block_name": "cobblestone"
            }
            >> await skills.collect_block('Jungle Log', num=11)
            {
                'success': False,
                'message': '近くにJungle Logが見つかりません。',
                'result': {'oak_log': 12, 'wooden_pickaxe': 1}
                'block_name': 'Jungle Log',
                'error': 'no_blocks_found'
            }
        """
        result = {
            "success": False,
            "message": "",
            "result": {},
            "block_name": block_name
        }
        print(f"{block_name}のブロックを取得します。")
        if num < 1:
            result["message"] = f"無効な収集数量: {num}"
            result["error"] = "invalid_number"
            print(result["message"])
            return result
        
        # 同等のブロックタイプをリストに追加
        blocktypes = [block_name]
        
        # 特殊処理: 鉱石ブロックの対応を追加
        ores = ['coal', 'diamond', 'emerald', 'iron', 'gold', 'lapis_lazuli', 'redstone']
        if block_name in ores:
            blocktypes.append(f"{block_name}_ore")
        # 深層岩鉱石の対応
        if block_name.endswith('ore'):
            blocktypes.append(f"deepslate_{block_name}")
        # dirtの特殊処理
        if block_name == 'dirt':
            blocktypes.append('grass_block')
        
        for i in range(num):
            blocks = []
            for btype in blocktypes:
                found_block = await self.get_nearest_block(btype, 500)
                await asyncio.sleep(0.1)
                if found_block:
                    blocks.append(found_block)
            
            # 除外位置のフィルタリング
            if exclude and blocks:
                blocks = [block for block in blocks if not any(
                    block.position.x == pos.x and 
                    block.position.y == pos.y and 
                    block.position.z == pos.z 
                    for pos in exclude
                )]
            # 安全に採掘可能なブロックのフィルタリング
            movements = self.bot.pathfinder.movements
            movements.dontMineUnderFallingBlock = False
            blocks = [block for block in blocks if movements.safeToBreak(block)]
            if not blocks:
                result["message"] = f"近くに{block_name}が見つかりません。"
                result["error"] = "no_blocks_found"
                break
                
            block = blocks[0]
            # 適切なツールを装備a
            self.bot.tool.equipForBlock(block)
            if self.bot.heldItem:
                held_item_id = self.bot.heldItem.type
            else:
                held_item_id = None
            if not block.canHarvest(held_item_id):
                self.bot.chat(f"{str(block_name)}を採掘するための適切なツールがありません。")
                result["message"] = f"{block_name}を採掘するための適切なツールがありません。"
                result["error"] = "no_suitable_tool"
                print(result["message"])
                return result
            try:
                move_result = await self.move_to_position(block.position.x, block.position.y, block.position.z, min_distance=1,dontcreateflow=False)
                if not move_result["success"]:
                    result["message"] = f"{block_name}の収集に失敗: {move_result['message']}"
                    result["error"] = "move_failed"
                    print(result["message"])
                    return result
                else:
                    self.bot.dig(block)
                    await asyncio.sleep(0.3)
                    await self.pickup_nearby_items()
                    await self.auto_light()
            except Exception as e:
                if str(e) == 'NoChests':
                    result["message"] = f"{block_name}の収集に失敗: インベントリが一杯で、保管場所がありません。"
                    result["error"] = "inventory_full"
                    print(result["message"])
                    break
                else:
                    result["message"] = f"{block_name}の収集に失敗: {str(e)}"
                    result["error"] = "collection_failed"
                    print(result["message"])
                    continue
                    
        result["result"] = await self.get_inventory_counts()
        result["success"] = True
        if not result["message"]:
            result["message"] = f"Collected {block_name}."
        
        print(result)
        return result
        
    async def should_place_torch(self):
        """
        Determines whether to place a torch based on the presence of torches nearby and whether torches are in the inventory.
        
        Returns:
            bool: True if a torch should be placed, False otherwise.
        """
        pos = self.bot.entity.position
        
        # Look for nearby torches
        nearest_torch =await self.get_nearest_block('torch', 6)
        if not nearest_torch:
            nearest_torch = await self.get_nearest_block('wall_torch', 6)
            
        # If no torches are nearby
        if not nearest_torch:
            # Check the block at the current position
            block = self.bot.blockAt(pos)
            
            # Check if there is a torch in the inventory
            has_torch = False
            if hasattr(self.bot, 'inventory') and hasattr(self.bot.inventory, 'items'):
                for item in self.bot.inventory.items():
                    if item and hasattr(item, 'name') and item.name == 'torch':
                        has_torch = True
                        break
                    
            # Can be placed if current position is air and has a torch
            return has_torch and block and hasattr(block, 'name') and block.name == 'air'
            
        return False
        
    async def auto_light(self):
        """
        If there are no torches around, if there is a torch in the inventory, and if the current position is air, place a torch.
        
        Returns:
            bool: True if a torch was placed, False otherwise
        """
        try:
            if await self.should_place_torch():
                pos = self.bot.entity.position
                Vec3 = require('vec3')
                # Place a torch at your feet
                floor_pos = Vec3(
                    round(pos.x),
                    round(pos.y) - 1,  # At your feet
                    round(pos.z)
                )
                
                # Place a torch
                result = await self.place_block('torch', floor_pos.x, floor_pos.y + 1, floor_pos.z, 'bottom')
                
                if result:
                    # Record the last position where a torch was placed
                    self._last_torch_pos = pos.clone()
                    return True
            return False
        except Exception as e:
            print(f"Torch placement error: {e}")
            return False
            
    def get_all_registry_blocks(self):
        """
        Gets all block names registered in the registry.
        Used for debugging purposes.
        
        Returns:
            list: List of block names
        """
        block_names = []
        try:
            if hasattr(self.bot.registry, 'blocksByName'):
                for block_name in self.bot.registry.blocksByName:
                    block_names.append(block_name)
                    
            return sorted(block_names)
        except Exception as e:
            print(f"Error getting block name: {e}")
            return []
        
    async def move_to_position(self, x, y, z, min_distance=2,
                               canDig=True,
                               canPlaceOn=True,
                               allow1by1towers=False,
                               dontcreateflow=True,
                               dontMineUnderFaillingBlock=True,
                               dontMoveUnderLiquid=True,
                               onlyCheckPath=False,
                               move_timeout=180): # Added timeout argument
        """
        Moves to the specified position. If canDig=True, it mines obstacles while moving.
        If movement is not completed or reachable within the specified time, it times out.

        Args:
            x (float): X coordinate of the destination
            y (float): Y coordinate of the destination
            z (float): Z coordinate of the destination
            min_distance (int): Minimum distance from the target position. Default is 2
            canDig (bool): Whether to break blocks that are obstacles to movement. Default is True
            canPlaceOn (bool): Whether to allow placing blocks during movement. Default is True
            allow1by1towers (bool): Whether to allow building and climbing 1x1 towers. Default is False
            dontcreateflow (bool): Whether or not to dig blocks touching liquid blocks that are obstacles to movement. Default is True
            dontMineUnderFaillingBlock (bool): Whether to allow digging under falling blocks like sand. Default is True
            dontMoveUnderLiquid (bool): If the coordinate specified as the destination is a liquid block, whether to return an error. Default is True
            onlyCheckPath (bool): Check if it is possible to move to the destination. Default is False
            move_timeout (int): Timeout duration for movement (seconds). Default is 60

        Returns:
            dict: Dictionary containing movement results
                - success (bool): True if movement was successful, False otherwise
                - error (str): Error code if movement failed (path_not_found, path_timeout, move_timeout, liquid_block, unexpected_error, move_failed)
                - message (str): Message of the movement result
                - position (dict): Coordinates after movement (e.g., {"x": 10, "y": 20, "z": 30})
        """
        if not onlyCheckPath:
            print(f"Moving to {x}, {y}, {z}.")
        # Get current and target positions
        current_pos = self.bot.entity.position

        result = {
            "success": False,
            "error": "",
            "message": "",
            "position": {
                "x": current_pos.x,
                "y": current_pos.y,
                "z": current_pos.z
            }
        }

        # Calculate the distance between the current position and the target position
        distance_to_target = ((current_pos.x - x) ** 2 +
                              (current_pos.y - y) ** 2 +
                              (current_pos.z - z) ** 2) ** 0.5
        # Skip movement if already close enough to the target position
        if distance_to_target <= min_distance:
            result["success"] = True
            result["message"] = f"Skipping movement because it's close enough to {x}, {y}, {z}."
            # Update position
            result["position"] = { "x": current_pos.x, "y": current_pos.y, "z": current_pos.z }
            print(result["message"])
            return result
        if dontMoveUnderLiquid:
            Vec3 = require('vec3')
            target_block = self.bot.blockAt(Vec3(x, y, z))
            if target_block and (target_block.name == 'water' or target_block.name == 'lava'):
                result["message"] = f"Target position {x}, {y}, {z} is a liquid block. Aborting movement as there's a risk of drowning or burning to death."
                result["error"] = "liquid_block"
                print(result["message"])
                return result

        try:
            # Set pathfinder movement
            movements = self.pathfinder.Movements(self.bot)
            movements.canDig = canDig
            movements.dontCreateFlow = dontcreateflow
            movements.dontMineUnderFaillingBlock = dontMineUnderFaillingBlock
            movements.canPlaceOn = canPlaceOn
            movements.allow1by1towers = allow1by1towers
            self.bot.pathfinder.setMovements(movements)
            # Set target position
            goal = self.pathfinder.goals.GoalNear(x, y, z, min_distance)
            # Get path
            path = self.bot.pathfinder.getPathTo(movements,goal)
            if path.status == "error":
                result["message"] = f"Could not generate a path to the target location. The destination may be in water/lava, or blocked by unmineable blocks/spaces with current equipment"
                result["error"] = "path_not_found"
                self.bot.chat(result["message"])
                return result
            elif path.status == "timeout":
                result["message"] = f"Path generation timed out. The target location may be too far away"
                result["error"] = "path_timeout"
                self.bot.chat(result["message"])
                return result
            if onlyCheckPath:
                result["success"] = True
                result["message"] = f"Target position {x}, {y}, {z} is reachable."
                return result
            # Move towards target
            self.bot.pathfinder.setGoal(goal)
            await asyncio.sleep(1)

            last_position = None
            stuck_time = 0
            temp_free_space = None
            move_start_time = asyncio.get_event_loop().time() # Record movement start time
            while self.bot.pathfinder.isMoving() or self.bot.pathfinder.isMining() or self.bot.pathfinder.isBuilding():
                # --- Timeout check ---
                current_time = asyncio.get_event_loop().time()
                if (current_time - move_start_time) > move_timeout:
                    print(f"Timed out. Exceeded maximum allowed movement time. Stopping operation midway ({move_timeout} seconds).")
                    self.bot.pathfinder.setGoal(None) # Reset destination
                    await asyncio.sleep(1) # Wait for goal reset to take effect
                    result["success"] = False
                    result["message"] = f"Timed out. Exceeded maximum allowed movement time. Stopping operation midway ({move_timeout} seconds)."
                    result["error"] = "move_timeout"
                    # Record current position
                    current_pos_timeout = await self.get_bot_position()
                    result["position"] = { "x": current_pos_timeout[0], "y": current_pos_timeout[1], "z": current_pos_timeout[2] }
                    return result
                # --- End of added section ---
                
                mining = self.bot.pathfinder.isMining()
                building = self.bot.pathfinder.isBuilding()
                current_position = self.bot.entity.position
                # Stack detection logic
                if not mining and not building:
                    if last_position and (
                        abs(current_position.x - last_position.x) < 0.01 and
                        abs(current_position.y - last_position.y) < 0.01 and
                        abs(current_position.z - last_position.z) < 0.01
                    ):
                        stuck_time += 1
                    else:
                        stuck_time = 0

                    # If stuck in the same position for more than 2 seconds
                    if stuck_time >= 2:
                        self.bot.chat("Detected a stack. Attempting to resolve.")
                        free_space = None
                        search_distance = 100
                        while free_space is None and search_distance < 500: # Prevent infinite loop
                            free_space = await self.get_nearest_free_space(X_size=1,Y_size=2,Z_size=1,distance=search_distance)
                            if free_space:
                                break
                            search_distance += 100

                        if free_space is None:
                            self.bot.chat("No temporary safe space found nearby. Aborting movement.")
                            self.bot.pathfinder.setGoal(None) # Reset destination
                            await asyncio.sleep(1)
                            result["success"] = False
                            result["message"] = "Failed to find a safe space during stack resolution, movement aborted."
                            result["error"] = "stuck_no_space"
                            current_pos_stuck = await self.get_bot_position()
                            result["position"] = { "x": current_pos_stuck[0], "y": current_pos_stuck[1], "z": current_pos_stuck[2] }
                            return result

                        if temp_free_space and temp_free_space.x == free_space.x and temp_free_space.y == free_space.y and temp_free_space.z == free_space.z:
                            # Warp if temporary movement cannot resolve it (This depends on Bot's capabilities, usually not recommended)
                            # self.bot.chat(f"/tp bot {free_space.x} {free_space.y} {free_space.z}")
                            self.bot.chat("Attempted temporary retreat but could not resolve the stack. Aborting movement.")
                            self.bot.pathfinder.setGoal(None)
                            await asyncio.sleep(1)
                            result["success"] = False
                            result["message"] = "Failed to resolve stack. Aborting movement."
                            result["error"] = "stuck_unresolved"
                            current_pos_stuck_fail = await self.get_bot_position()
                            result["position"] = { "x": current_pos_stuck_fail[0], "y": current_pos_stuck_fail[1], "z": current_pos_stuck_fail[2] }
                            return result
                        else:
                            # Move to temporary target point
                            temp_goal = self.pathfinder.goals.GoalNear(free_space.x, free_space.y, free_space.z, 0)
                            self.bot.pathfinder.setGoal(temp_goal)
                            await asyncio.sleep(1)
                            temp_free_space = free_space
                            self.bot.chat(f"Temporarily moving to {free_space.x:.1f}, {free_space.y:.1f}, {free_space.z:.1f}.")
                            await asyncio.sleep(2) # Wait for movement to temporary target

                        # Reset to original target location
                        self.bot.pathfinder.setGoal(goal)
                        await asyncio.sleep(1)
                        self.bot.chat("Resuming movement to the original target.")
                        await asyncio.sleep(0.5)
                        stuck_time = 0
                        move_start_time = asyncio.get_event_loop().time() # After stack resolution, reset timer

                last_position = current_position
                await asyncio.sleep(0.5) # Loop interval
            # After movement completion, reset pathfinder's goal
            self.bot.pathfinder.setGoal(None)
            await asyncio.sleep(1)
            # --- Post-movement processing ---
            bot_x, bot_y, bot_z = await self.get_bot_position()
            # Calculate distance to target position (indentation correction)
            final_distance_xy = ((bot_x - x) ** 2 + (bot_z - z) ** 2) ** 0.5
            final_distance_y = abs(bot_y - y) - 2
            if final_distance_xy <= min_distance+1:
                result["success"] = True
                result["message"] = f" {x}, {y}, {z} reached"
                
            else:
                print(f"final_distance_xy: {final_distance_xy}\nfinal_distance_y: {final_distance_y}\nmin_distance: {min_distance}\n")
                # If distance is far even if isMoving() is False (e.g., path end point is far from target)
                result["success"] = False
                result["message"] = f"{x}, {y}, {z} could not be reached. Current position is {bot_x:.1f}, {bot_y:.1f}, {bot_z:.1f}. This is a temporary error, and it may be possible to reach the destination by retrying"
                result["error"] = "move_failed"
            result["position"] = {
                "x": bot_x,
                "y": bot_y,
                "z": bot_z
            }
            print(result["message"])

        except Exception as e:
            result["message"] = f"An unexpected error occurred during movement: {str(e)}"
            self.bot.chat(result["message"])
            import traceback
            traceback.print_exc()
            result["error"] = "unexpected_error"
            # Record position at time of error
            try:
                error_pos = await self.get_bot_position()
                result["position"] = { "x": error_pos[0], "y": error_pos[1], "z": error_pos[2] }
            except: # get_bot_position may also fail
                 result["position"] = {"x": None, "y": None, "z": None}


        return result
        
    async def smelt_item(self, item_name, num=1):
        """
        If there is a "furnace" within 32 blocks, or if there is a "furnace" in the inventory, put items into the "furnace" and smelt them. Coal, charcoal, and wood are used as fuel.
        Wait until smelting is complete and retrieve the completed items.
        
        Args:
            item_name (str): Name of the item to be smelted (e.g., "raw_iron", "raw_copper", "beef", etc.)
            num (int): Number of items to smelt. Default is 1
            
        Returns:
            dict: A dictionary containing the results
                - success (bool): True if smelting succeeded, False if it failed
                - message (str): Result message
                - smelted (int): Number of items smelted
                - item_name (str): Name of the item smelted
                - error (str, optional): Error code if there is an error
        """
        self.bot.chat(f"Smelting {item_name}.")
        result = {
            "success": False,
            "message": "",
            "smelted": 0,
            "item_name": item_name,
        }
        
        # Check if the item can be smelted
        is_smeltable = self._is_smeltable(item_name)
        if not is_smeltable:
            result["message"] = f"{item_name} cannot be smelted. Please specify raw ores or food items starting with 'raw_'."
            result["error"] = "not_smeltable"
            self.bot.chat(result["message"])
            return result
            
        # Find a furnace
        placed_furnace = False
        furnace_block = await self.get_nearest_block('furnace', 32)
        if not furnace_block:
            # Check if a furnace is held
            if (await self.get_inventory_counts()).get('furnace', 0) > 0:
                # Place a furnace
                pos = await self.get_nearest_free_space(X_size=1,Z_size=1,distance=15)
                place_result = await self.place_block('furnace', pos.x, pos.y, pos.z)
                await asyncio.sleep(1)
                if place_result["success"]:
                    furnace_block = await self.get_nearest_block('furnace', 32)
                    placed_furnace = True
                else:
                    result["message"] = "Failed to place the furnace"
                    result["error"] = "furnace_placement_failed"
                    self.bot.chat(result["message"])
                    return result
            else:
                result["message"] = f"There is no furnace nearby, and no furnace in the inventory"
                result["error"] = "no_furnace"
                self.bot.chat(result["message"])
                return result
                
        # Move to the furnace
        if self.bot.entity.position.distanceTo(furnace_block.position) > 4:
            await self.move_to_position(
                furnace_block.position.x, 
                furnace_block.position.y, 
                furnace_block.position.z, 
                2
            )
            
        # Open the furnace
        try:
            # Look at the furnace
            self.bot.lookAt(furnace_block.position)
            
            # Open the furnace
            furnace = self.bot.openFurnace(furnace_block)
            
            # Check if there is already an item being smelted
            input_item = furnace.inputItem()
            if input_item and input_item.type and input_item.count > 0:
                if self._get_item_name(input_item.type) != item_name:
                    result["message"] = f"The furnace is already smelting {self._get_item_name(input_item.type)}"
                    result["error"] = "already_smelting"
                    furnace.close()
                    
                    # Retrieve the placed furnace
                    if placed_furnace:
                        await self.collect_block('furnace', 1)
                        
                    self.bot.chat(result["message"])
                    return result
                    
            # Check if the item to be smelted is held
            inv_counts = await self.get_inventory_counts()
            if not inv_counts.get(item_name, 0) or inv_counts.get(item_name, 0) < num:
                result["message"] = f"Not enough {item_name} to smelt"
                result["error"] = "insufficient_items"
                furnace.close()
                
                # Retrieve the placed furnace
                if placed_furnace:
                    await self.collect_block('furnace', 1)
                    
                self.bot.chat(result["message"])
                return result
                
            # Check and load fuel
            if not furnace.fuelItem() or furnace.fuelItem().count <= 0:
                fuel = self._get_smelting_fuel()
                if not fuel:
                    result["message"] = f"No fuel (coal, charcoal, wood, etc.) to smelt {item_name}"
                    result["error"] = "no_fuel"
                    furnace.close()
                    
                    # Retrieve the placed furnace
                    if placed_furnace:
                        await self.collect_block('furnace', 1)
                        
                    self.bot.chat(result["message"])
                    print(result)
                    return result
                    
                # Load fuel
                furnace.putFuel(fuel.type, None, fuel.count)
                self.bot.chat(f"Loaded {fuel.count} {fuel.name} into the furnace as fuel")
                print(f"Loaded {fuel.count} {fuel.name} into the furnace as fuel")
                
            # Put the item to be smelted into the furnace
            item_id = self._get_item_id(item_name)
            furnace.putInput(item_id, None, num)
            
            # Wait until smelting is complete and collect results
            total_smelted = 0
            collected_last = True
            smelted_item = None
            
            # Wait a little for smelting to begin
            await asyncio.sleep(0.2)
            
            while total_smelted < num:
                # Check every 10 seconds
                await asyncio.sleep(10)
                
                # Check results
                collected = False
                if furnace.outputItem():
                    smelted_item = furnace.takeOutput()
                    if smelted_item:
                        total_smelted += smelted_item.count
                        collected = True
                        
                # If nothing was obtained
                if not collected and not collected_last:
                    break  # If nothing was obtained last time and this time, exit
                    
                collected_last = collected
                
            # Close the furnace
            furnace.close()
            
            # Recover the placed furnace
            if placed_furnace:
                await self.collect_block('furnace', 1)
                
            # Set the result
            if total_smelted == 0:
                result["message"] = f"Failed to smelt {item_name}"
                result["error"] = "smelting_failed"
                self.bot.chat(result["message"])
                print(result)
                return result
                
            if total_smelted < num:
                result["message"] = f"Smelted {total_smelted} out of {num} {item_name}s"
                result["success"] = True
                result["smelted"] = total_smelted
                
                if smelted_item:
                    result["smelted_item_name"] = self._get_item_name(smelted_item.type)
                    
                self.bot.chat(result["message"])
                print(result)
                return result
                
            result["message"] = f"Smelted {total_smelted} {item_name}s"
            if smelted_item:
                result["smelted_item_name"] = self._get_item_name(smelted_item.type)
                result["message"] = f"Smelted {item_name} and obtained {total_smelted} {self._get_item_name(smelted_item.type)}s"
                
            result["success"] = True
            result["smelted"] = total_smelted
            self.bot.chat(result["message"])
            print(result)
            return result
            
        except Exception as e:
            result["message"] = f"An error occurred during furnace operation: {str(e)}"
            result["error"] = "furnace_error"
            
            import traceback
            traceback.print_exc()
            print(result)
            self.bot.chat(result["message"])
            
            # Recover the placed furnace
            if placed_furnace:
                try:
                    await self.collect_block('furnace', 1)
                except:
                    pass
                    
            return result
    
    async def clear_nearest_furnace(self):
        """
        Find the closest furnace and retrieve all items from it.
        
        Returns:
            dict: Dictionary containing the results
                - success (bool): True if the operation was successful, False otherwise
                - message (str): Result message
                - items (list): List of retrieved items
        """
        self.bot.chat("Retrieving items from the nearest furnace")
        print("Retrieving items from the nearest furnace")
        result = {
            "success": False,
            "message": "",
            "items": []
        }
        
        try:
            # Find the nearest furnace
            furnace_block = await self.get_nearest_block('furnace', 32)
            if not furnace_block:
                result["message"] = "No furnace found nearby"
                result["error"] = "no_furnace"
                return result
                
            # Check distance to furnace
            if self.bot.entity.position.distanceTo(furnace_block.position) > 4:
                move_result = await self.move_to_position(
                    furnace_block.position.x,
                    furnace_block.position.y,
                    furnace_block.position.z,
                    2
                )
                if not move_result["success"]:
                    result["message"] = "Could not reach the furnace"
                    result["error"] = "cannot_reach"
                    return result
            
            # Open the furnace
            furnace = self.bot.openFurnace(furnace_block)
            
            # Retrieve items
            smelted_item = None
            input_item = None 
            fuel_item = None
            
            if furnace.outputItem():
                smelted_item = furnace.takeOutput()
                if smelted_item:
                    result["items"].append({
                        "name": self._get_item_name(smelted_item.type),
                        "count": smelted_item.count
                    })
                    
            if furnace.inputItem():
                input_item = furnace.takeInput()
                if input_item:
                    result["items"].append({
                        "name": self._get_item_name(input_item.type),
                        "count": input_item.count
                    })
                    
            if furnace.fuelItem():
                fuel_item = furnace.takeFuel()
                if fuel_item:
                    result["items"].append({
                        "name": self._get_item_name(fuel_item.type),
                        "count": fuel_item.count
                    })
                    
            # Close the furnace
            furnace.close()
            
            # Group items by name and calculate total
            item_totals = {}
            
            for item in result["items"]:
                name = item["name"]
                count = item["count"]
                item_totals[name] = item_totals.get(name, 0) + count
                
            # Convert totals to a new items list
            grouped_items = []
            for name, count in item_totals.items():
                grouped_items.append({
                    "name": name,
                    "count": count
                })
                
            # Update results
            result["items"] = grouped_items
            
            # Generate result text
            text = ""
            for item in grouped_items:
                text += f"{item['count']} {item['name']}s, "
            text = text.rstrip("、")
            if text=="" :
                result["message"] = "Retrieved from the furnace, but the furnace was empty"
            else:
                result["message"] = f"Retrieved {text} from the furnace"
            result["success"] = True
            
            return result
            
        except Exception as e:
            result["message"] = f"An error occurred while clearing the furnace: {str(e)}"
            import traceback
            traceback.print_exc()
            return result
        
    async def attack_nearest(self, mob_type, kill=True,pickup_item=True):
        """
        Attacks a mob of the specified type.
        
        Args:
            mob_type: The type of mob to attack
            kill: Whether to keep attacking until the mob dies (default is True)
            pickup_item: Whether to pick up dropped items when the mob dies (default is True)
        Returns:
            dict: A dictionary containing the results
                - success (bool): True if the attack was successful, False otherwise
                - message (str): Result message
                - mob_type (str): Type of mob attacked
        """
        self.bot.chat(f"{mob_type} attacking.")
        print(f"{mob_type} attacking.")
        result = {
            "success": False,
            "message": "",
            "mob_type": mob_type
        }
        
        # Get nearby entities
        nearby_entities = self._get_nearby_entities(24)
        # Search for entities matching the specified mob_type
        mob = None
        for entity in nearby_entities:
            if hasattr(entity, 'name') and entity.name == mob_type:
                mob = entity
                break
        
        if mob and hasattr(mob, 'position') and mob.position:
            attack_result = await self.attack_entity(mob, kill,pickup_item)
            result.update(attack_result)
            result["mob_type"] = mob_type
            return result
        
        result["message"] = f'{mob_type} was not found.'
        self.bot.chat(result["message"])
        print(result)
        return result

    async def attack_entity(self, entity, kill=True,pickup_item=True):
        """
        Attacks the specified entity.
        
        Args:
            entity: Entity to attack
            kill: Whether to continue attacking until the entity dies (default is True)
            pickup_item: Whether to pick up dropped items when the entity dies (default is True)
        Returns:
            dict: Dictionary containing the result
                - success (bool): True if the attack was successful, False if it failed
                - message (str): Result message
                - entity_name (str): Name of the attacked entity
                - killed (bool, optional): Whether the entity was killed
        """
        self.bot.chat(f"{entity.name} attacking.")
        print(f"{entity.name} attacking.")
        result = {
            "success": False,
            "message": "",
            "entity_name": entity.name if hasattr(entity, 'name') else "Unknown entity"
        }
        
        # Check entity existence
        if not entity or not hasattr(entity, 'position') or not entity.position:
            result["message"] = "The target entity for attack is invalid"
            result["error"] = "invalid_entity"
            self.bot.chat(result["message"])
            print(result)
            return result
        
        # Equip the weapon with the highest attack power
        wepon = await self._equip_highest_attack()
        if not wepon:
            result["message"] = "There is nothing in the inventory that can be a weapon."
            result["error"] = "no_weapon"
            self.bot.chat(result["message"])
            print(result)
            return result
        
        # Save entity position
        position = entity.position
        
        if not kill:
            # If the entity is too far, approach it
            try:
                if self.bot.entity.position.distanceTo(position) > 5:
                    await self.move_to_position(position.x, position.y, position.z)
            except Exception as e:
                result["message"] = f"An error occurred while moving to the entity: {str(e)}"
                result["error"] = "movement_error"
                self.bot.chat(result["message"])
                print(result)
                return result
                
            # Attack only once
            try:
                self.bot.attack(entity)
                result["success"] = True
                result["message"] = f"{entity.name} attacked once"
                result["killed"] = False
                self.bot.chat(result["message"])
                print(result)
                return result
            except Exception as e:
                result["message"] = f"An error occurred during the attack: {str(e)}"
                result["error"] = "attack_error"
                self.bot.chat(result["message"])
                print(result)
                return result
        else:
            # Use PVP module
            self.bot.pvp.attack(entity)
            
            # Wait until the entity dies
            while self._is_entity_nearby(entity, 24):
                await asyncio.sleep(1)
                if hasattr(self.bot, 'interrupt_code') and self.bot.interrupt_code:
                    self.bot.pvp.stop()
                    result["message"] = "Attack was interrupted"
                    self.bot.chat(result["message"])
                    print(result)
                    return result
            self.bot.pvp.stop()
            
            result["success"] = True
            result["message"] = f"{entity.name} defeated"
            result["killed"] = True
            self.bot.chat(result["message"])
            print(result)
            # Pick up surrounding items
            if pickup_item:
                pickup_result = await self.pickup_nearby_items()
                result["message"] += " "+ pickup_result["message"]
                self.bot.chat(result["message"])
                print(result)
            return result

    async def defend_self(self, range=9):
        """
        Defends itself from hostile mobs in the surroundings.
        Continues to attack until there are no more hostile mobs.
        If not equipped with a weapon, flees from enemies.
        Args:
            range: Range to search for mobs. Default is 9
            
        Returns:
            dict: Dictionary containing the result
                - success (bool): True if defense was successful, False if there are no enemies
                - message (str): Result message
                - enemies_killed (int): Number of enemies killed
        """
        result = {
            "success": False,
            "message": "",
            "enemies_killed": 0
        }
        
        attacked = False
        enemies_killed = 0
        wepon = await self._equip_highest_attack()
        enemy = self._get_nearest_hostile_entity(range)
        if not wepon:
            self.bot.chat("There is nothing in inventory that can be a weapon. Flee from enemies.")
            result["message"] = await self.avoid_enemies()
            result["error"] = "no_weapon"
            self.bot.chat(result["message"])
            print(result)
            return result
        while enemy:
            # Actions based on distance to enemy
            enemy_distance = self.bot.entity.position.distanceTo(enemy.position)
            
            # If enemies other than Creepers and Phantoms are far away, approach
            if enemy_distance >= 4 and enemy.name != 'creeper' and enemy.name != 'phantom':
                try:
                    self.bot.pathfinder.setMovements(self.pathfinder.Movements(self.bot))
                    await self.bot.pathfinder.goto(self.pathfinder.goals.GoalFollow(enemy, 3.5), True)
                except Exception:
                    # Ignore errors if entity is dead, etc.
                    pass
                    
            # If enemy is too close, create distance
            if enemy_distance <= 2:
                try:
                    self.bot.pathfinder.setMovements(self.pathfinder.Movements(self.bot))
                    inverted_goal = self.pathfinder.goals.GoalInvert(self.pathfinder.goals.GoalFollow(enemy, 2))
                    await self.bot.pathfinder.goto(inverted_goal, True)
                except Exception:
                    # Ignore errors if entity is dead, etc.
                    pass
            
            # Start attacking
            has_pvp = hasattr(self.bot, 'pvp') and self.bot.pvp is not None
            
            self.bot.pvp.attack(enemy)
                
            attacked = True
            
            # Wait a little
            await asyncio.sleep(0.5)
            
            # Look for the next enemy
            previous_enemy = enemy
            enemy = self._get_nearest_hostile_entity(range)
            
            # Count if previous enemy is gone
            if enemy != previous_enemy and not self._is_entity_nearby(previous_enemy, range):
                enemies_killed += 1
            
            if hasattr(self.bot, 'interrupt_code') and self.bot.interrupt_code:
                if has_pvp:
                    self.bot.pvp.stop()
                result["message"] = "Defense was interrupted"
                self.bot.chat(result["message"])
                print(result)
                return result
        
        # Stop PVP attack
        if hasattr(self.bot, 'pvp') and self.bot.pvp is not None:
            self.bot.pvp.stop()
        
        if attacked:
            result["success"] = True
            result["message"] = f"Self-defense successful. Killed {enemies_killed} enemies."
            result["enemies_killed"] = enemies_killed
        else:
            result["message"] = "No hostile mobs nearby."
        
        self.bot.chat(result["message"])
        print(result)
        return result
        
    async def pickup_nearby_items(self, item_name=None,distance=10):
        """
        Picks up nearby dropped items.
        Args:
            item_name (str, optional): Name of the item to pick up. If None, picks up all nearby dropped items.
            distance (int, optional): Range to search for dropped items. Default is 8
        Returns:
            dict: Dictionary containing the result
                - success (bool): True if item was picked up
                - message (str): Result message
                - picked_up (int): Number of items picked up
        """
        result = {
            "success": False,
            "message": ""
        }
        
        # Function to get the closest item
        def get_nearest_item():
            nearest_item_list = []
            
            # Assume bot.entities is a dictionary or list of entities
            for entity_id in self.bot.entities:
                entity = self.bot.entities[entity_id]
                if hasattr(entity, 'name') and entity.name == 'item':
                    drop_item_name = self._get_item_name(self._get_item_id_from_entity(entity))
                    if not item_name is None and item_name != drop_item_name:
                        continue
                    # Distance calculation
                    dx = self.bot.entity.position.x - entity.position.x
                    dy = self.bot.entity.position.y - entity.position.y
                    dz = self.bot.entity.position.z - entity.position.z
                    current_distance = (dx*dx + dy*dy + dz*dz) ** 0.5
                    
                    if current_distance < distance:
                        nearest_item_list.append(entity)
            return nearest_item_list

        # Get the closest item
        nearest_item_list = get_nearest_item()
        if nearest_item_list == []:
            result["message"] = "No dropped items nearby."
            return result
        
        item_list = []
        for nearest_item in nearest_item_list:
            # Approach the item
            block_pos = self.bot.blockAt(nearest_item.position)
            if block_pos:
                move_result = await self.move_to_position(block_pos.position.x, block_pos.position.y, block_pos.position.z, 0.5)
                if not move_result["success"]:
                    break

            # Get item ID
            item_id = self._get_item_id_from_entity(nearest_item)
            item_name = self._get_item_name(item_id)
            item_list.append(item_name)
            # Wait a little for the item to be picked up
            await asyncio.sleep(0.2)
                
        result["success"] = True
        item_str = ", ".join(item_list)
        result["message"] = f"{item_str} picked up."
        self.bot.chat(result["message"])
        print(result)
        return result
        
    async def _break_block_at(self, x, y, z):
        """
        Destroys the block at the specified coordinates. Tools are automatically selected.
        Do not use _break_block_at to mine specific blocks like diamonds, etc., where 'coordinates are unknown'. (Please use the collect_block function)
        
        Args:
            x (float): X coordinate of the block to be destroyed
            y (float): Y coordinate of the block to be destroyed
            z (float): Z coordinate of the block to be destroyed
            
        Returns:
            dict: Dictionary containing the result
                - success (bool): True if destruction succeeded, False if it failed
                - message (str): Result message
                - position (dict): Position where destruction was attempted {x, y, z}
                - block_name (str, optional): Name of the destroyed block
                - error (str, optional): Error code if there is an error
        
        Example:
            >>> await skills._break_block_at(100, -61, 100)
        """
        self.bot.chat(f"{x}, {y}, {z}'s block will be destroyed.")
        print(f"{x}, {y}, {z}'s block will be destroyed.")
        result = {
            "success": False,
            "message": "",
            "position": {"x": x, "y": y, "z": z}
        }
        
        # Coordinate validation
        if x is None or y is None or z is None:
            result["message"] = "Coordinates of the block to destroy are invalid"
            result["error"] = "invalid_coordinates"
            self.bot.chat(result["message"])
            print(result)
            return result
            
        # Create Vec3 object
        Vec3 = require('vec3')
        block_pos = Vec3(x, y, z)
        
        # Get block
        block = self.bot.blockAt(block_pos)
        if not block:
            result["message"] = f"No block found at coordinates ({x}, {y}, {z})"
            result["error"] = "no_block_found"
            self.bot.chat(result["message"])
            print(result)
            return result
            
        result["block_name"] = block.name
        
        # Skip if it's air, water, or lava
        if block.name in ['air', 'water', 'lava']:
            result["message"] = f"Coordinates ({x}, {y}, {z}) are {block.name}, so destruction is skipped"
            self.bot.chat(result["message"])
            print(result)
            return result
            
        # Check distance to block
        move_result = await self.move_to_position(x, y, z, 4,canPlaceOn=False,allow1by1towers=False)
        if not move_result["success"]:
            return move_result

        # Equip appropriate tool if not in creative mode
        if self.bot.game.gameMode != 'creative':
            try:
                # Equip appropriate tool
                self.bot.tool.equipForBlock(block)
                
                # Check if the appropriate tool is held
                item_id = None
                if self.bot.heldItem:
                    item_id = self.bot.heldItem.type
                            
                # Check if the block can be mined
                if hasattr(block, 'canHarvest') and not block.canHarvest(item_id):
                    result["message"] = f"Do not have the appropriate tool to mine {block.name}"
                    result["error"] = "no_suitable_tool"
                    self.bot.chat(result["message"])
                    print(result)
                    return result
            except Exception as e:
                result["message"] = f"An error occurred while equipping the tool: {str(e)}"
                result["error"] = "tool_equip_error"
                self.bot.chat(result["message"])
                print(result)
                return result
                
        # Destroy block
        try:
            self.bot.dig(block, True)  # By setting the 2nd argument to True, wait until mining is complete
            result["message"] = f"Destroyed {block.name} at coordinates ({x:.1f}, {y:.1f}, {z:.1f})"
            result["success"] = True
            self.bot.chat(result["message"])
            print(result)
            return result
        except Exception as e:
            result["message"] = f"An error occurred while destroying the block: {str(e)}"
            result["error"] = "dig_error"
            self.bot.chat(result["message"])
            print(result)
            return result
        
    async def use_door(self, door_pos=None):
        """
        Uses the door/fence gate at the specified position. If no position is specified, uses the nearest door/fence gate.
        Note that iron_door and iron_trapdoor, which do not open when interacted with, cannot be used.
        
        Args:
            door_pos (Vec3, optional): Position of the door to use. If None, the nearest door is used.
            
        Returns:
            dict: Dictionary containing the result
                - success (bool): True if door use was successful, False otherwise
                - message (str): Result message
                - door_position (dict, optional): Position of the door used {x, y, z} (only on success)
        """
        self.bot.chat(f"{door_pos}'s door will be used.")
        print(f"{door_pos}'s door will be used.")
        result = {
            "success": False,
            "message": ""
        }
        
        try:
            Vec3 = require('vec3')
            
            # If the door position is not specified, search for the nearest door
            if not door_pos:
                door_types = [
                    'oak_door', 'spruce_door', 'birch_door', 'jungle_door', 
                    'acacia_door', 'dark_oak_door', 'mangrove_door', 
                    'crimson_door', 'warped_door',

                    'oak_fence_gate', 'spruce_fence_gate', 'birch_fence_gate', 'jungle_fence_gate',
                    'acacia_fence_gate', 'dark_oak_fence_gate', 'mangrove_fence_gate',
                    'crimson_fence_gate', 'warped_fence_gate'
                ]
                # Trapdoors are not yet implemented as they require ladder support
                trapdoor_types = [
                    'oak_trapdoor', 'spruce_trapdoor', 'birch_trapdoor', 'jungle_trapdoor',
                    'acacia_trapdoor', 'dark_oak_trapdoor', 'mangrove_trapdoor'
                ]
                
                for door_type in door_types:
                    door_block = await self.get_nearest_block(door_type, 16)
                    if door_block:
                        door_pos = door_block.position
                        break
            else:
                # Convert existing coordinates to Vec3 object
                door_pos = Vec3(door_pos.x, door_pos.y, door_pos.z)
                
            # If no door is found
            if not door_pos:
                result["message"] = "No usable door found."
                self.bot.chat(result["message"])
                print(result)
                return result
                
            # Record door position in result
            result["door_position"] = {
                "x": door_pos.x,
                "y": door_pos.y,
                "z": door_pos.z
            }
            
            # Approach the door
            await self.move_to_position(door_pos.x, door_pos.y, door_pos.z, 1,canDig=False)
                    
            # Get door block
            door_block = self.bot.blockAt(door_pos)
            
            # Look at the door
            self.bot.lookAt(door_pos)
            
            # If the door is closed, open it
            if not door_block._properties.open:
                self.bot.activateBlock(door_block)
                
            # Move forward
            self.bot.setControlState("forward", True)
            await asyncio.sleep(0.6)
            self.bot.setControlState("forward", False)
            
            # Close the door
            self.bot.activateBlock(door_block)
            
            result["success"] = True
            result["message"] = f"Passed through the door at coordinates ({door_pos.x}, {door_pos.y}, {door_pos.z}) and moved to coordinates ({self.bot.entity.position.x:.1f}, {self.bot.entity.position.y:.1f}, {self.bot.entity.position.z:.1f})."
            self.bot.chat(result["message"])
            print(result)
            return result
            
        except Exception as e:
            result["message"] = f"An unexpected error occurred while using the door: {str(e)}"
            self.bot.chat(result["message"])
            print(result)
            import traceback
            traceback.print_exc()
            return result        
        
    async def till_and_sow(self, x, y, z, seed_type=None):
        """
        Tills the ground at the specified coordinates and plants the specified seed.
        
        Args:
            x (float): X coordinate of the point to till
            y (float): Y coordinate of the point to till
            z (float): Z coordinate of the point to till
            seed_type (str, optional): Type of seed to plant. If not specified, only tills and does not plant seeds.
            
        Returns:
            dict: Dictionary containing the results
                - success (bool): True if tilling the ground was successful, False if it failed
                - message (str): Result message
                - position (dict): Tilled position {x, y, z}
                - tilled (bool): Whether the ground was tilled
                - planted (bool, optional): Whether seeds were planted (if seed_type is specified)
                - seed_type (str, optional): Type of seed planted (if seed_type is specified)
        """
        self.bot.chat(f"Tilling the ground at coordinates ({x}, {y}, {z}) and planting {seed_type}.")
        print(f"Tilling the ground at coordinates ({x}, {y}, {z}) and planting {seed_type}.")
        result = {
            "success": False,
            "message": "",
            "position": {"x": x, "y": y, "z": z},
            "tilled": False
        }
        
        try:
            Vec3 = require('vec3')
            
            # Round coordinates to integers
            x = round(x)
            y = round(y)
            z = round(z)
            result["position"] = {"x": x, "y": y, "z": z}
            
            # Get the target block
            block = self.bot.blockAt(Vec3(x, y, z))
            
            # Check if the target block can be tilled
            if block.name not in ['grass_block', 'dirt', 'farmland']:
                result["message"] = f"{block.name} cannot be tilled. It must be a dirt or grass block."
                self.bot.chat(result["message"])
                print(result)
                return result
                
            # Check for block above
            above = self.bot.blockAt(Vec3(x, y+1, z))
            if above.name != 'air':
                result["message"] = f"Cannot till because there is {above.name} on top of the block."
                self.bot.chat(result["message"])
                print(result)
                return result
            
            # Find and equip a hoe
            hoe = None
            for item in self.bot.inventory.items():
                if 'hoe' in item.name:
                    hoe = item
                    break
            if not hoe:
                result["message"] = "Cannot till because you do not have a hoe."
                self.bot.chat(result["message"])
                print(result)
                return result
            else:
                self.bot.equip(hoe, 'hand')
                    
            # If the distance to the block is far, get closer
            if self.bot.entity.position.distanceTo(block.position) > 4.5:
                pos = block.position
                move_result = await self.move_to_position(pos.x, pos.y, pos.z, 4)
                if not move_result["success"]:
                    result["message"] = move_result["message"]
                    self.bot.chat(result["message"])
                    print(result)
                    return result
            
            # Till if it's not already farmland
            if block.name != 'farmland':
                
                # Till the block
                self.bot.activateBlock(block)
                
                result["tilled"] = True
                self.bot.chat(f"The BOT tilled coordinates ({x}, {y}, {z}).")
                print(result)
            else:
                result["tilled"] = True
                
            # Plant seeds
            if seed_type:
                # If it ends with "seed" but not "seeds", add an "s"
                if seed_type.endswith('seed') and not seed_type.endswith('seeds'):
                    seed_type += 's'  # Fix common mistake
                    
                # Find the seeds
                seeds = None
                for item in self.bot.inventory.items():
                    if item.name == seed_type:
                        seeds = item
                        break
                if not seeds:
                    result["message"] = f"Cannot plant because you do not have {seed_type}." + \
                                       (f"Coordinates ({x}, {y}, {z}) were tilled." if result["tilled"] else "")
                    self.bot.chat(result["message"])
                    print(result)
                    
                    # If it was tilled, it's somewhat successful
                    if result["tilled"]:
                        result["success"] = True
                    return result
                
                # Equip seeds
                self.bot.equip(seeds, 'hand')
                
                # Plant seeds (place on farmland)
                # Because it is placed on the bottom surface, Vec3(0, -1, 0) is used
                self.bot.placeBlock(block, Vec3(0, -1, 0))
                
                result["planted"] = True
                result["seed_type"] = seed_type
                self.bot.chat(f"Planted {seed_type} at Coordinates({x}, {y}, {z}).")
                print(f"Planted {seed_type} at Coordinates({x}, {y}, {z}).")
            
            result["success"] = True
            
            if seed_type and result["planted"]:
                result["message"] = f"Tilled Coordinates({x}, {y}, {z}) and planted {seed_type}."
            else:
                result["message"] = f"Tilled Coordinates({x}, {y}, {z})."
            print(result)
            self.bot.chat(result["message"])
            return result
            
        except Exception as e:
            already_tilled = "tilled" in result and result["tilled"]
            result["message"] = f"An unexpected error occurred while tilling and planting: {str(e)}" + \
                               (f"Coordinates({x}, {y}, {z}) could be tilled." if already_tilled else "")
            
            # If only tilling was successful, partially successful
            if already_tilled:
                result["success"] = True
                
            self.bot.chat(result["message"])
            print(result)
            import traceback
            traceback.print_exc()
            return result

    def get_item_crafting_recipes(self, item_name):
        """
        Retrieves crafting recipes for items
        
        Args:
            item_name (str): Item name
            
        Returns:
            list: List of recipes. Each recipe is in the format of [materials dictionary, result dictionary]

        Example:
            >>> recipes = get_item_crafting_recipes("crafting_table")
            [[{'oak_planks': 4}, {'craftedCount': 1}], [{'spruce_planks': 4}, {'craftedCount': 1}]...]
        """
        self.bot.chat(f"Retrieving {item_name}'s crafting recipe.")
        item_id = self.mcdata.itemsByName[item_name].id
        if item_id not in self.mcdata.recipes:
            return None
            
        recipes = []
        for r in self.mcdata.recipes[item_id]:
            recipe = {}
            ingredients = []
            if hasattr(r, 'ingredients') and r.ingredients:
                ingredients = r.ingredients
            elif hasattr(r, 'inShape') and r.inShape:
                ingredients = [item for sublist in r.inShape for item in sublist if item]
                
            for ingredient in ingredients:
                if not ingredient:
                    continue
                ingredient_name = self.mcdata.items[ingredient].name
                if ingredient_name not in recipe:
                    recipe[ingredient_name] = 0
                recipe[ingredient_name] += 1
                
            recipes.append([
                recipe,
                {"craftedCount": r.result.count}
            ])
            
        return recipes

    async def collect_liquid(self, liquid_type='water', max_distance=16):
        """
        Scoops up water or lava within the specified range with a bucket. Execution of this method requires a bucket.

        Args:
            liquid_type (str): Type of liquid to scoop up. Specify 'water' or 'lava'. Default is 'water'.
            max_distance (int): Maximum distance to search. Default is 16.
            
        Returns:
            dict: Dictionary containing results
                - success (bool): True if scooping up liquid was successful, False if failed
                - message (str): Result message
                - position (dict, optional): Position of the scooped up liquid {x, y, z}
                - liquid_type (str): Type of liquid scooped up
        """
        result = {
            "success": False,
            "message": "",
            "liquid_type": liquid_type
        }
        
        try:
            # Check liquid type
            if liquid_type not in ['water', 'lava']:
                result["message"] = f"Invalid liquid type: {liquid_type}. Please specify 'water' or 'lava'."
                self.bot.chat(result["message"])
                print(result)
                return result
            
            # Search for bucket
            bucket = None
            bucket_count = 0
            for item in self.bot.inventory.items():
                if item.name == 'bucket':
                    bucket = item
                elif item.name == f'{liquid_type}_bucket':
                    bucket_count += 1
            bucket_count += 1
            
            if not bucket:
                result["message"] = "Cannot scoop up liquid because a bucket is not held."
                self.bot.chat(result["message"])
                print(result)
                return result
            
            # Search for specified liquid block
            block_id = self.mcdata.blocksByName[liquid_type].id
            blocks = self.bot.findBlocks({
                'matching': block_id,
                'maxDistance': max_distance,
                'count': 10
            })
            liquid_block = None
            for block in blocks:
                block_info = self.bot.blockAt(block)
                if block_info.metadata == 0:
                    liquid_block = block_info
                    break
            
            if not liquid_block:
                result["message"] = f"Within range, {liquid_type} was not found."
                self.bot.chat(result["message"])
                print(result)
                return result
            
            # If the distance to the block is far, approach
            if self.bot.entity.position.distanceTo(liquid_block.position) > 2:
                pos = liquid_block.position
                move_result = await self.move_to_position(pos.x, pos.y, pos.z, 2)
                if not move_result["success"]:
                    result["message"] = move_result["message"]
                    self.bot.chat(result["message"])
                    print(result)
                    return result
            
            # Equip bucket
            self.bot.equip(bucket, 'hand')

            # Bot looks at liquid block
            self.bot.lookAt(liquid_block.position)
            
            # Using the bucket, scoop up liquid
            self.bot.activateBlock(liquid_block)
            self.bot.activateItem()
            
            # Wait a bit for the operation to complete
            await asyncio.sleep(1)

            # Deactivate bucket
            self.bot.deactivateItem()

            # Set result
            result["success"] = True
            result["position"] = {
                "x": liquid_block.position.x,
                "y": liquid_block.position.y,
                "z": liquid_block.position.z
            }
            
            # Check if the correct liquid was scooped up (check inventory)
            has_filled_bucket = False
            
            for item in self.bot.inventory.items():
                
                if item.name == f"{liquid_type}_bucket":
                    bucket_count -= 1
                    if bucket_count == 0:
                        has_filled_bucket = True
                        break
            
            if has_filled_bucket:
                result["message"] = f"Scooped up {liquid_type} at Coordinates({liquid_block.position.x}, {liquid_block.position.y}, {liquid_block.position.z}) with {bucket.name}."
            else:
                result["success"] = False
                result["message"] = f"Scooping up {liquid_type} failed."
            
            self.bot.chat(result["message"])
            print(result)
            return result
            
        except Exception as e:
            result["message"] = f"An unexpected error occurred while scooping up liquid: {str(e)}"
            self.bot.chat(result["message"])
            print(result)
            import traceback
            traceback.print_exc()
            return result

    async def place_liquid(self, x, y, z, liquid_type='water'):
        """
        At the specified coordinates, liquid (water or lava) is placed from a bucket. Execution of this method requires a water_bucket or lava_bucket.
        
        Args:
            x (float): X coordinate to place liquid
            y (float): Y coordinate to place liquid
            z (float): Z coordinate to place the liquid
            liquid_type (str): Type of liquid to place. Specify 'water' or 'lava'. Default is 'water'.
            
        Returns:
            dict: Dictionary containing the result
                - success (bool): True if liquid placement was successful, False if failed
                - message (str): Result message
                - position (dict): Position where the liquid was placed {x, y, z}
                - liquid_type (str): Type of liquid placed
        """
        self.bot.chat(f"Placing {liquid_type} at coordinates ({x}, {y}, {z}).")
        print(f"Placing {liquid_type} at coordinates ({x}, {y}, {z}).")
        result = {
            "success": False,
            "message": "",
            "position": {"x": x, "y": y, "z": z},
            "liquid_type": liquid_type
        }
        
        try:
            # Check liquid type
            if liquid_type not in ['water', 'lava']:
                result["message"] = f"Invalid liquid type: {liquid_type}. Please specify 'water' or 'lava'."
                self.bot.chat(result["message"])
                print(result)
                return result
            
            # Round coordinates to integers
            x = round(x)
            y = round(y)
            z = round(z)
            result["position"] = {"x": x, "y": y, "z": z}
            
            # Look for a filled bucket
            filled_bucket = None
            
            for item in self.bot.inventory.items():
                if item.name == f"{liquid_type}_bucket":
                    filled_bucket = item
            
            if not filled_bucket:
                result["message"] = f"Cannot place liquid because you don't have a {liquid_type}_bucket."
                self.bot.chat(result["message"])
                print(result)
                return result
            
            # Get target block
            Vec3 = require('vec3')
            target_position = Vec3(x, y, z)
            target_block = self.bot.blockAt(target_position)
            
            # Check if destination is air or another placable block
            if target_block.name != 'air' and target_block.name != 'cave_air':
                result["message"] = f"Cannot place liquid at coordinates ({x}, {y}, {z}) because {target_block.name} is already there."
                self.bot.chat(result["message"])
                print(result)
                return result
            
            # If distance to block is far, get closer
            if self.bot.entity.position.distanceTo(target_position) > 2:
                move_result = await self.move_to_position(x, y, z, 2)
                if not move_result["success"]:
                    result["message"] = move_result["message"]
                    self.bot.chat(result["message"])
                    print(result)
                    return result
            
            # Equip filled bucket
            self.bot.equip(filled_bucket, 'hand')
            
            # Look at target block
            self.bot.lookAt(target_position)
            
            # Use bucket to place liquid
            self.bot.activateBlock(target_block)
            self.bot.activateItem()
            
            # Wait a moment for the operation to complete
            await asyncio.sleep(1)
            
            # Deactivate bucket
            self.bot.deactivateItem()
            
            # Check placed block
            new_block = self.bot.blockAt(target_position)
            is_correct_liquid = new_block and new_block.name == liquid_type
            
            if is_correct_liquid:
                result["success"] = True
                result["message"] = f"Placed {liquid_type} at ({x}, {y}, {z}) from {filled_bucket.name}."
            else:
                result["success"] = False
                result["message"] = f"Failed to place {liquid_type} at ({x}, {y}, {z})."
            
            self.bot.chat(result["message"])
            print(result)
            return result
            
        except Exception as e:
            result["message"] = f"An unexpected error occurred during liquid placement: {str(e)}"
            self.bot.chat(result["message"])
            print(result)
            import traceback
            traceback.print_exc()
            return result

    def _make_item(self, item_name, count=1):
        """
        Creates an item object with the specified name and count.
        Used for adding items in creative mode.
        Note: Only works in creative mode
        
        Args:
            item_name (str): Item name
            count (int): Item count
            
        Returns:
            Object: Item object
        """
        try:
            if hasattr(self.mcdata, 'makeItem'):
                return self.mcdata.makeItem(item_name, count)
            elif hasattr(self.mcdata, 'itemsByName') and item_name in self.mcdata.itemsByName:
                item_id = self.mcdata.itemsByName[item_name].id
                return {
                    'type': item_id,
                    'count': count,
                    'metadata': 0
                }
        except Exception as e:
            print(f"Item creation error: {e}")
            
        # Return basic object
        return {
            'name': item_name,
            'count': count
        }
    
            
    async def _equip_highest_attack(self):
        """
        Equips the weapon with the highest attack power.
        
        Returns:
            bool: True if a weapon was equipped, False if no suitable weapon is available
        """
        # Look for swords and axes (but exclude pickaxes)
        weapons = []
        for item in self.bot.inventory.items():
            if 'sword' in item.name or ('axe' in item.name and 'pickaxe' not in item.name):
                weapons.append(item)
                
        # If no weapon, look for pickaxes or shovels
        if not weapons:
            for item in self.bot.inventory.items():
                if 'pickaxe' in item.name or 'shovel' in item.name:
                    weapons.append(item)
                    
        # If no weapon, exit
        if not weapons:
            return False
            
        # Sort by attack power
        try:
            # If the attackDamage property is available
            weapons.sort(key=lambda item: getattr(item, 'attackDamage', 0), reverse=True)
        except:
            # If there is no attack power information, sort by material and type
            material_order = ['netherite', 'diamond', 'iron', 'stone', 'golden', 'wooden']
            weapon_type_order = ['sword', 'axe', 'pickaxe', 'shovel']
            
            def get_attack_score(item):
                # Material score
                material_score = 0
                for i, material in enumerate(material_order):
                    if material in item.name:
                        material_score = len(material_order) - i
                        break
                
                # Weapon type score
                type_score = 0
                for i, weapon_type in enumerate(weapon_type_order):
                    if weapon_type in item.name:
                        type_score = len(weapon_type_order) - i
                        break
                        
                return material_score * 10 + type_score
                
            weapons.sort(key=get_attack_score, reverse=True)
            
        # 最高の武器を装備
        best_weapon = weapons[0]
        self.bot.equip(best_weapon, 'hand')
        return True
        
    def _get_nearby_entity_of_type(self, entity_type, max_distance=24):
        """
        指定された種類の最も近いエンティティを取得します。
        
        Args:
            entity_type (str): エンティティの種類
            max_distance (int): 検索する最大距離
            
        Returns:
            Entity: 最も近いエンティティ、見つからない場合はNone
        """
        try:
            entities = self._get_nearby_entities(max_distance)
            for entity in entities:
                if hasattr(entity, 'name') and entity.name == entity_type:
                    return entity
        except Exception as e:
            print(f"エンティティ検索エラー: {e}")
            
        return None
        
    def _get_nearest_hostile_entity(self, max_distance=24):
        """
        指定した距離以内で最も近い敵対的なエンティティを取得します。
        
        Args:
            max_distance (int): 検索する最大距離。デフォルトは24
            
        Returns:
            Entity or None: 最も近い敵対的なエンティティ。見つからない場合はNone
        """
        def calculate_distance(pos1, pos2):
            """2点間のユークリッド距離を計算"""
            return ((pos1.x - pos2.x) ** 2 + 
                   (pos1.y - pos2.y) ** 2 + 
                   (pos1.z - pos2.z) ** 2) ** 0.5

        # 敵対的なエンティティをフィルタリング
        hostile_entities = [
            entity for entity in self._get_nearby_entities(max_distance)
            if self._is_hostile(entity)
        ]
        
        if not hostile_entities:
            return None
            
        # 距離でソート
        hostile_entities.sort(
            key=lambda e: calculate_distance(self.bot.entity.position, e.position)
        )
        
        return hostile_entities[0] if hostile_entities else None
        
    def _get_nearby_entities(self, max_distance=24):
        """
        指定した距離以内にある全てのエンティティを取得し、距離順にソートして返します。
        
        Args:
            max_distance (int): 検索する最大距離。デフォルトは24
            
        Returns:
            list: 距離順にソートされた近くのエンティティのリスト
        """
        if not self.bot or not self.bot.entity or not hasattr(self.bot.entity, 'position'):
            return []
            
        def calculate_distance(pos1, pos2):
            """2点間のユークリッド距離を計算"""
            return ((pos1.x - pos2.x) ** 2 + 
                   (pos1.y - pos2.y) ** 2 + 
                   (pos1.z - pos2.z) ** 2) ** 0.5
            
        nearby_entities = []
        # JavaScriptのオブジェクトとして実装されているentitiesをキーで反復処理
        for entity_id in self.bot.entities:
            entity = self.bot.entities[entity_id]
            if not entity or not hasattr(entity, 'id'):  # エンティティがNoneの場合はスキップ
                continue
                
            if entity.id == self.bot.entity.id:  # 自分自身は除外
                continue
                
            if hasattr(entity, 'position') and entity.position:
                distance = calculate_distance(self.bot.entity.position, entity.position)
                if distance <= max_distance:
                    nearby_entities.append(entity)
                
        # 距離でソート
        nearby_entities.sort(
            key=lambda e: calculate_distance(self.bot.entity.position, e.position)
        )
        
        return nearby_entities
        
    def _is_entity_nearby(self, entity, max_distance=24):
        """
        特定のエンティティが近くにいるか確認します。
        
        Args:
            entity: 確認するエンティティ
            max_distance (int): 検索する最大距離
            
        Returns:
            bool: エンティティが近くにいる場合はTrue
        """
        # エンティティが有効かチェック
        if not entity or not hasattr(entity, 'id'):
            return False
            
        entities = self._get_nearby_entities(max_distance)
        for e in entities:
            if hasattr(e, 'id') and e.id == entity.id:
                return True
        return False
    
    def _is_hostile(self, entity):
        """
        エンティティが敵対的かどうかを判断します。
        
        Args:
            entity: 判断するエンティティ
            
        Returns:
            bool: 敵対的な場合はTrue
        """
        hostile_mobs = [
            'zombie', 'skeleton', 'creeper', 'spider', 'enderman', 
            'witch', 'slime', 'silverfish', 'cave_spider', 'ghast',
            'zombie_pigman', 'blaze', 'magma_cube', 'wither_skeleton',
            'guardian', 'elder_guardian', 'shulker', 'husk', 'stray',
            'phantom', 'drowned', 'pillager', 'ravager', 'vex',
            'evoker', 'vindicator', 'hoglin', 'zoglin', 'piglin_brute'
        ]
        
        try:
            return entity.name in hostile_mobs
        except:
            return False
        
    def _is_smeltable(self, item_name):
        """
        アイテムが精錬可能かどうかを判断します。
        
        Args:
            item_name (str): 判断するアイテム名
            
        Returns:
            bool: 精錬可能な場合はTrue
        """
        # 精錬可能なアイテムのリスト
        smeltable_items = [
            # 鉱石
            'raw_iron', 'raw_gold', 'raw_copper', 
            'iron_ore', 'gold_ore', 'copper_ore',
            'ancient_debris', 'netherite_scrap',
            # 食材
            'beef', 'chicken', 'cod', 'salmon', 'porkchop', 'potato', 'rabbit', 'mutton',
            # その他
            'sand', 'cobblestone', 'clay', 'clay_ball', 'cactus'
        ]
        
        # Items starting with 'raw_' are basically judged as smeltable
        if item_name.startswith('raw_'):
            return True
            
        return item_name in smeltable_items
        
    def _get_smelting_fuel(self):
        """
        Searches for fuel that can be used for smelting from the inventory.
        
        Returns:
            Object: Fuel item object, None if not found
        """
        # Search for items that can be used as fuel in priority order
        fuel_types = ['coal', 'charcoal', 'coal_block', 'lava_bucket', 'blaze_rod', 'oak_planks', 'spruce_planks', 
                     'birch_planks', 'jungle_planks', 'acacia_planks', 'dark_oak_planks', 
                     'oak_log', 'spruce_log', 'birch_log', 'jungle_log', 'acacia_log', 'dark_oak_log']
                     
        for fuel_type in fuel_types:
            for item in self.bot.inventory.items():
                if item.name == fuel_type:
                    return item
                    
        return None
        
    def _get_item_name(self, item_id):
        """
        Gets the corresponding item name from the item ID.
        
        Args:
            item_id (int): ID of the item
            
        Returns:
            str: Item name. None if ID is not found
        # Equip the best weapon
        item = self.mcdata.items[item_id]
        
        if item:
            return item.name
        return None
        
        Gets the nearest entity of the specified type.
        """
        Gets the item ID from the item name.
            entity_type (str): The type of entity
            max_distance (int): Maximum distance to search
            item_name (str): Item name
            
            Entity: The nearest entity, or None if not found
            int: Item ID
        """
        try:
            if hasattr(self.mcdata, 'itemsByName') and item_name in self.mcdata.itemsByName:
                return self.mcdata.itemsByName[item_name].id
            elif hasattr(self.bot.registry, 'itemsByName') and item_name in self.bot.registry.itemsByName:
                return self.bot.registry.itemsByName[item_name].id
            print(f"Entity search error: {e}")
            pass
            
        # Error if item is not found
        return None
    
        Gets the nearest hostile entity within a specified distance.
        """
        Gets the item ID from the entity.
            max_distance (int): Maximum distance to search. Default is 24
        Args:
            entity: Entity object
            Entity or None: The nearest hostile entity, or None if not found
        Returns:
            int: Item ID
            """Calculates the Euclidean distance between two points"""
        # itemId is included in the 8th element (index 7) of metadata
        if entity and hasattr(entity, 'metadata'):
            metadata_item = entity.metadata[8]
            return metadata_item.itemId
        # Filter hostile entities
        # Returns None if it cannot be obtained
        return None

    async def handle_connection_error(self, timeout=30):
        """
        Attempts to reconnect the bot if an API communication problem occurs.
        Used when the API does not respond or times out.

        # Sort by distance
            timeout (int): Timeout duration for reconnection attempts (seconds). Default is 30 seconds.

        Returns:
            dict: Reconnection result
                - success (bool): True if reconnection was successful
                - message (str): Result message
        """
        self.bot.chat("A communication error occurred, attempting to reconnect to the server...")
        Gets all entities within a specified distance, sorts them by distance, and returns them.
            "success": False,
            "message": ""
            max_distance (int): Maximum distance to search. Default is 24
        try:
            # Call the reconnect_bot method of the discovery instance
            # reconnect_bot should have been changed to return bool
            reconnect_success = await self.discovery.reconnect_bot(timeout=timeout)

            if reconnect_success:
                result["success"] = True
                result["message"] = "Successfully reconnected to the server."
            """Calculates the Euclidean distance between two points"""
                # After reconnection, it might be necessary to update references within the Skills class
                self.bot = self.discovery.bot
                self.mcdata = self.discovery.mcdata
                self.pathfinder = self.discovery.pathfinder
                self.movements = self.discovery.movements
        # Iterate through entities implemented as JavaScript objects by key
                print("Updated references within the Skills class.")
            else:
                result["message"] = f"Failed to reconnect to the server (timeout: {timeout} seconds). Please check the server status."
                # Avoid chatting as the bot instance might be None
                print(result["message"])
            if entity.id == self.bot.entity.id:  # Exclude self
        except Exception as e:
            result["message"] = f"An unexpected error occurred during the reconnection process: {str(e)}"
            print(f"Reconnection error: {result['message']}")
            import traceback
            traceback.print_exc()

        return result
        # Sort by distance
    async def create_nether_portal(self, check_space_only=False):
        """
        Places a Nether portal using obsidian and activates it with flint and steel.
        Installs with a minimum configuration (10 obsidian blocks, no corners).

        Args:
            check_space_only (bool): If True, only checks if there is available space to place it, without actually placing it.

        Checks if a specific entity is nearby.
            dict: Dictionary containing the result
                - success (bool): True if the gate was successfully placed and activated
                - message (str): Result message
                - portal_base_pos (dict, optional): Base coordinates of the placed gate {x, y, z}
                - error (str, optional): Error code (insufficient_materials, no_space, placement_failed, activation_failed, verification_failed)
        """
        self.bot.chat("Start creating Nether portal.")
        result = {
        # Check if entity is valid
            "message": "",
        }
        Vec3 = require('vec3')

        # --- 1. Material check ---
        inventory = await self.get_inventory_counts()
        obsidian_count = inventory.get('obsidian', 0)
        flint_and_steel_count = inventory.get('flint_and_steel', 0)

        if obsidian_count < 10:
            result["message"] = f"Not enough obsidian to create Nether portal (Required: 10, Held: {obsidian_count})"
        Determines if an entity is hostile.
            self.bot.chat(result["message"])
            print(result)
            entity: The entity to judge
        if flint_and_steel_count < 1 and not check_space_only:
            result["message"] = "No flint and steel needed to activate Nether portal"
            bool: True if hostile
            self.bot.chat(result["message"])
            print(result)
            return result

        # --- 2. Space search (Height 5, Width 4, Depth 1) ---
        portal_width = 4
        portal_height = 5
        search_distance = 15
        base_pos = None
        orientation = 'z' # 'x' or 'z'

        base_pos = await self.get_nearest_free_space(portal_width, portal_height,1, search_distance)

        if not base_pos:
            result["message"] = f"Insufficient space (Height {portal_height}, Width {portal_width}) found to place Nether portal."
            result["error"] = "no_space"
            self.bot.chat(result["message"])
        Determines if an item is smeltable.
            return result

            item_name (str): The name of the item to judge

        if check_space_only:
            bool: True if smeltable
            result["message"] = f"Suitable space for Nether portal found. Coordinates: ({base_pos.x}, {base_pos.y}, {base_pos.z}), Orientation: {orientation}-axis direction"
        # List of smeltable items
            print(result)
            # Ores

        # Move to space
        move_result = await self.move_to_position(base_pos.x, base_pos.y, base_pos.z, 2)
            # Food ingredients
            result["message"] = f"Failed to move to Nether portal placement space: {move_result.get('message', 'Unknown')}"
            # Others
            self.bot.chat(result["message"])
            print(result)
            return result

        # --- 3. Nether portal frame placement (10 obsidian) ---
        portal_frame_coords = []
        # Base (y=0)
        portal_frame_coords.append(base_pos.offset(0, 0, 0))
        portal_frame_coords.append(base_pos.offset(1, 0, 0))
        portal_frame_coords.append(base_pos.offset(2, 0, 0))
        portal_frame_coords.append(base_pos.offset(3, 0, 0))
        # Pillar (x=0)
        portal_frame_coords.append(base_pos.offset(0, 1, 0))
        portal_frame_coords.append(base_pos.offset(0, 2, 0))
        portal_frame_coords.append(base_pos.offset(0, 3, 0))
        portal_frame_coords.append(base_pos.offset(3, 1, 0))
        portal_frame_coords.append(base_pos.offset(3, 2, 0))
        portal_frame_coords.append(base_pos.offset(3, 3, 0))
        # Top (y=4)
        portal_frame_coords.append(base_pos.offset(0, 4, 0))
        portal_frame_coords.append(base_pos.offset(1, 4, 0))
        portal_frame_coords.append(base_pos.offset(2, 4, 0))
        portal_frame_coords.append(base_pos.offset(3, 4, 0))

        self.bot.chat("Starting Nether portal frame placement...")
        placed_count = 0
        for coord in portal_frame_coords:
            place_result = await self.place_block('obsidian', coord.x, coord.y, coord.z)
            if place_result["success"]:
                placed_count += 1
                await asyncio.sleep(0.1) # Leave a small interval between placements
            else:
                # Handling failure during placement (may tolerate cases where a block already exists)
                block_at_coord = self.bot.blockAt(coord)
                if block_at_coord and block_at_coord.name == 'obsidian':
                    self.bot.chat(f"Obsidian already exists at coordinates ({coord.x}, {coord.y}, {coord.z}). Skipping.")
                    placed_count += 1 # Count even if already exists
                    continue
                else:
                    result["message"] = f"An error occurred during Nether portal frame placement ({coord.x}, {coord.y}, {coord.z}). Reason: {place_result.get('message', 'Unknown')}"
                    result["error"] = "placement_failed"
                    self.bot.chat(result["message"])
                    print(result)
                    # TODO: Consider adding a process to remove placed blocks
                    return result

        if placed_count < 10:
             # This case should be covered by the error handling above, but just in case
             result["message"] = "Failed to place Nether portal frame. Could not place the required number of obsidian."
             result["error"] = "placement_failed"
             self.bot.chat(result["message"])
             print(result)
             return result

        self.bot.chat("Nether portal frame placement completed.")

        # --- 4. Nether portal activation ---
        self.bot.chat("Attempting to activate Nether portal...")

        # Equip flint and steel
        equip_result = await self.equip('flint_and_steel')
        if not equip_result["success"]:
             result["message"] = "Failed to equip flint and steel."
             result["error"] = "activation_failed"
             self.bot.chat(result["message"])
             print(result)
             return result

        # Activation target block (inner obsidian at the bottom of the frame)
        activation_target_coord = None
        portal_check_coord = None # Coordinates for portal generation confirmation
        if orientation == 'z':
            activation_target_coord = base_pos.offset(1, 0, 0) # Left side of the base
            portal_check_coord = base_pos.offset(1, 1, 0) # Bottom left inside the gate
        elif orientation == 'x':
            activation_target_coord = base_pos.offset(0, 0, 1) # Front side of the base
            portal_check_coord = base_pos.offset(0, 1, 1) # Bottom front inside the gate

        activation_target_block = self.bot.blockAt(activation_target_coord)
        if not activation_target_block or activation_target_block.name != 'obsidian':
            result["message"] = f"Activation target block (obsidian) not found ({activation_target_coord.x}, {activation_target_coord.y}, {activation_target_coord.z})"
            result["error"] = "activation_failed"
            self.bot.chat(result["message"])
            print(result)
            return result

        # Approach target block (if necessary)
        if self.bot.entity.position.distanceTo(activation_target_coord) > 4.5:
             move_result = await self.move_to_position(activation_target_coord.x, activation_target_coord.y, activation_target_coord.z, 3)
             if not move_result["success"]:
                 result["message"] = f"Failed to move to gate activation position: {move_result.get('message', 'Unknown')}"
                 result["error"] = "activation_failed"
                 self.bot.chat(result["message"])
                 print(result)
                 return result

        # Look at target block
        self.bot.lookAt(activation_target_coord.offset(0.5, 0.5, 0.5), True) # Look at the center of the block

        # Use flint and steel (may be activateItem instead of activateBlock)
        # Mineflayer's activateBlock interacts with the block itself. Flint and steel are used on a block.
        try:
            # Specify which face to use (here assuming the top face Vec3(0, 1, 0))
            # The second argument of activateBlock is referenceBlock, and the third argument is faceVector
            # faceVector specifies which face of the target block to click
            # Click the top face of the obsidian at the bottom of the frame to generate the gate
            self.bot.activateBlock(activation_target_block, Vec3(0, 1, 0))
            self.bot.chat(f"Used flint and steel on the obsidian at coordinates ({activation_target_block.position.x}, {activation_target_block.position.y}, {activation_target_block.position.z}).")
            await asyncio.sleep(1.0) # Wait for portal generation
        except Exception as e:
            result["message"] = f"An error occurred while using flint and steel: {str(e)}"
            result["error"] = "activation_failed"
            self.bot.chat(result["message"])
            print(result)
            import traceback
            traceback.print_exc()
            return result

        # --- 5. Activation check ---
        portal_block = self.bot.blockAt(portal_check_coord)
        if portal_block and portal_block.name == 'nether_portal':
            result["success"] = True
            result["message"] = f"Nether portal was successfully created and activated at coordinates ({base_pos.x}, {base_pos.y}, {base_pos.z})."
            self.bot.chat(result["message"])
            print(result)
        else:
            result["message"] = f"Failed to activate the Nether portal. Portal blocks were not generated. Check coordinates: ({portal_check_coord.x}, {portal_check_coord.y}, {portal_check_coord.z}), Actual block: {portal_block.name if portal_block else 'None'}"
            result["error"] = "verification_failed"
            self.bot.chat(result["message"])
            print(result)
        return result