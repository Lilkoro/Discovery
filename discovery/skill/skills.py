from javascript import require, On, Once, AsyncTask, once, off
import asyncio
import math
from concurrent.futures import ThreadPoolExecutor

class Skills:
    def __init__(self, discovery):
        """
        Receives the Discovery instance and uses its properties.
        
        Args:
            discovery: Instance of the Discovery class
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
            tuple[float, float, float]: Tuple containing x, y, z coordinates of the bot's position. 

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
        Makes the BOT look in the specified direction. Useful in combination with BotViewAgent to check the BOT's field of view.

        Args:
            direction (str): Direction ('north', 'south', 'east', 'west', 'up', 'down')

        Returns:
            dict: Dictionary containing the result
                - success (bool): True if direction change was successful
                - message (str): Result message
        """
        result = {
            "success": False,
            "message": ""
        }

        try:
            # Get current yaw and pitch
            current_yaw = self.bot.entity.yaw
            current_pitch = self.bot.entity.pitch
            
            target_yaw = current_yaw # Default is current yaw
            target_pitch = 0.0 # Default is horizontal

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
                target_pitch = math.pi / 2  # Straight up
                target_yaw = current_yaw # Maintain yaw when looking up/down
            elif direction_lower == 'down':
                target_pitch = -math.pi / 2 # Straight down
                target_yaw = current_yaw # Maintain yaw when looking up/down
            else:
                result["message"] = f"Invalid direction specified: {direction}"
                self.bot.chat(result["message"])
                return result

            # bot.look is likely synchronous, but verify if it needs await
            # Mineflayer's bot.look is normally synchronous, but might be async via JS library
            # Treating as synchronous here (if error occurs, change to await self.bot.look(...))
            self.bot.look(target_yaw, target_pitch)
            
            result["success"] = True
            result["message"] = f"Looked {direction.capitalize()}."
            # self.bot.chat(result["message"]) # Omit chat as it may be called frequently
            return result

        except Exception as e:
            result["message"] = f"Error occurred while looking {direction}: {str(e)}"
            self.bot.chat(result["message"])
            import traceback
            traceback.print_exc()
            return result
        
    async def _get_surrounding_blocks(self, position=None, x_distance=10, y_distance=10, z_distance=10):
        """
        Gets blocks surrounding the specified position. Useful for acquiring block info over a wide area.

        Args:
            position (Vec3 or tuple): Center position for search (BOT position if unspecified). Tuple is also allowed.
            x_distance (int): Search distance in X direction (Default: 10)
            y_distance (int): Search distance in Y direction (Default: 10)
            z_distance (int): Search distance in Z direction (Default: 10)

        Returns:
            list: List of surrounding block information (each element is a dict {'name': block_name, 'position': position})

        Operation details:
            - Small range: Fetches all blocks
            - Large range: Optimized by dividing into 3 zones
              - Near distance (within 5 blocks radius): Fetch all blocks
              - Medium distance (5-10 blocks radius): Fetch every 2 blocks
              - Far distance (10+ blocks radius): Fetch every 3 blocks
            - Block fetching optimized via batching (500 blocks at a time)
            - Filtering sped up via parallel processing
        """
        Vec3 = require('vec3') # Make Vec3 available

        self.bot.chat(f"Fetching blocks within a {x_distance}x{y_distance}x{z_distance} area.")
        # Set default values
        if position is None:
            position = self.bot.entity.position

        # --- Add type checking and conversion --- 
        if isinstance(position, tuple) and len(position) == 3:
            try:
                position = Vec3(position[0], position[1], position[2])
            except Exception as e:
                self.bot.chat("Coordinate type conversion error occurred.")
                return [] # Return empty list on error
        elif not hasattr(position, 'offset'): # If no offset method (not Vec3)
            self.bot.chat("Invalid coordinate object type.")
            return [] # Return empty list on error
        # --- End addition --- 

        x_dist = x_distance
        y_dist = y_distance
        z_dist = z_distance
        
        # Set sampling rate based on distance
        coords = []
        total_vol = (2 * x_dist + 1) * (2 * y_dist + 1) * (2 * z_dist + 1)
        
        # Sampling based on distance (thinning out for large ranges)
        if total_vol > 8000:  # For large ranges
            # Dense close up, sparse far away
            near_dist = 5  # Near distance boundary
            
            # Near zone (Fetch complete)
            for x in range(-min(near_dist, x_dist), min(near_dist, x_dist) + 1):
                for y in range(-min(near_dist, y_dist), min(near_dist, y_dist) + 1):
                    for z in range(-min(near_dist, z_dist), min(near_dist, z_dist) + 1):
                        coords.append(position.offset(x, y, z))
            
            # Mid zone (Fetch every 2 blocks)
            mid_dist = 10
            if x_dist > near_dist or y_dist > near_dist or z_dist > near_dist:
                for x in range(-min(mid_dist, x_dist), min(mid_dist, x_dist) + 1, 2):
                    for y in range(-min(mid_dist, y_dist), min(mid_dist, y_dist) + 1, 2):
                        for z in range(-min(mid_dist, z_dist), min(mid_dist, z_dist) + 1, 2):
                            # Append blocks not in near zone
                            if abs(x) > near_dist or abs(y) > near_dist or abs(z) > near_dist:
                                coords.append(position.offset(x, y, z))
            
            # Far zone (Fetch every 3 blocks)
            if x_dist > mid_dist or y_dist > mid_dist or z_dist > mid_dist:
                for x in range(-x_dist, x_dist + 1, 3):
                    for y in range(-y_dist, y_dist + 1, 3):
                        for z in range(-z_dist, z_dist + 1, 3):
                            # Append blocks not in mid zone
                            if abs(x) > mid_dist or abs(y) > mid_dist or abs(z) > mid_dist:
                                coords.append(position.offset(x, y, z))
            
        else:
            # Fetch all blocks if range is small
            for x in range(-x_dist, x_dist + 1):
                for y in range(-y_dist, y_dist + 1):
                    for z in range(-z_dist, z_dist + 1):
                        coords.append(position.offset(x, y, z))

        # Determine batch size (split large requests)
        batch_size = 500
        all_blocks = []
        
        # Batch processing
        for i in range(0, len(coords), batch_size):
            batch_end = min(i + batch_size, len(coords))
            batch = coords[i:batch_end]
            
            async def _get_block_async(position):
                return self.bot.blockAt(position)
            
            # Run block fetching in parallel within batch
            batch_tasks = [_get_block_async(pos) for pos in batch]
            batch_results = await asyncio.gather(*batch_tasks)
            all_blocks.extend(batch_results)
        
        try:
            def chunks(lst, n):
                """Split list into n chunks"""
                for i in range(0, len(lst), n):
                    yield lst[i:i + n]
            
            def process_chunk(chunk):
                return [{'name': block.name, 'position': {'x': block.position.x, 'y': block.position.y, 'z': block.position.z}} 
                        for block in chunk if block and block.type != 0]
            
            # Calculate optimal chunk size based on CPU cores
            import os
            cpu_count = os.cpu_count() or 4
            chunk_size = max(100, len(all_blocks) // (cpu_count * 2))
            block_chunks = list(chunks(all_blocks, chunk_size))
            
            # Run filtering on multiple threads
            with ThreadPoolExecutor(max_workers=cpu_count) as executor:
                filtered_chunks = list(executor.map(process_chunk, block_chunks))
            
            # Combine results
            surrounding_blocks = []
            for chunk in filtered_chunks:
                surrounding_blocks.extend(chunk)
                
        except ImportError:
            # Use standard list comprehension if parallel processing library cannot be imported
            surrounding_blocks = [
                {'name': block.name, 'position': {'x': block.position.x, 'y': block.position.y, 'z': block.position.z}}
                for block in all_blocks
                if block and block.type != 0
            ]
        
        return surrounding_blocks
    
    
    async def get_inventory_counts(self):
        """
        Returns the name and count of each item in the bot's inventory in dictionary format.

        Returns:
            dict: Dictionary where key is item name and value is quantity
            
        Example:
            >>> get_inventory_counts()
            {'birch_planks': 1, 'dirt': 1}
        """
        print("Fetching items from inventory.")
        inventory_counts = {}
        
        # Loop over all items in inventory
        for item in self.bot.inventory.items():
            # Add to count if item name already exists, otherwise add new
            if item.name in inventory_counts:
                inventory_counts[item.name] += item.count
            else:
                inventory_counts[item.name] = item.count
        await asyncio.sleep(0.1)
        print(inventory_counts)
        return inventory_counts
    
    async def get_nearest_block(self, block_name, max_distance=1000):
        """
        Searches for a specified block near the BOT and returns info for the nearest block.
        
        Args:
            block_name (str): Block name to search for (e.g. "oak_log")
            max_distance (int): Max block distance to search (default 1000)
            canMove (bool): Return only reachable blocks. Default is True
        Returns:
            Block: Nearest block, or None if not found
        
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
            # Get Block ID
            block_id = None
            if hasattr(self.bot.registry, 'blocksByName') and block_name in self.bot.registry.blocksByName:
                block_id = self.bot.registry.blocksByName[block_name].id
            else:
                print(f"Executed get_nearest_block, but block '{str(block_name)}' was not found in minecraft block names")
                return None
                
            # Search for blocks
            blocks_pos = self.bot.findBlocks({
                'point': self.bot.entity.position,
                'matching': block_id,
                'maxDistance': max_distance,
                'count': 20
            })
            distance_min = None
            block_min = None
            # Are we actually calculating distance correctly?
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
            print(f"An error occurred while searching for blocks: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    async def get_nearest_free_space(self, X_size=1, Y_size=1, Z_size=1, distance=15, y_offset=0):
        """
        Finds empty space of the specified size (air above, solid block below) near the BOT.
        
        Args:
            X_size (int): X size of the free space to find. (Minecraft block width)
            Y_size (int): Y size of the free space to find. (Minecraft block height)
            Z_size (int): Z size of the free space to find. (Minecraft block width)
            distance (int): Max distance to search. Default is 8.
            y_offset (int): Y-coordinate offset to apply to the found free space. Default is 0.
            
        Returns:
            Vec3: South-west corner coordinates of the found free space. Returns the coordinates at bot's feet if none found.
        
        Example:
            >>> free_space = skills.get_nearest_free_space(2, 10)
            >>> print(f"Found free space: x={free_space.x}, y={free_space.y}, z={free_space.z}")
        """
        self.bot.chat("Searching for free space.")
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
            
            # Check for specified sized free space for each air block
            for pos in empty_pos:
                empty = True

                # Skip if same as bot's position
                bot_pos = self.bot.blockAt(self.bot.entity.position).position
                if (pos.x == bot_pos.x and pos.y == bot_pos.y and pos.z == bot_pos.z):
                    continue
                # Confirm free space
                for x_offset in range(X_size):
                    for y_offset in range(Y_size):
                        for z_offset in range(Z_size):
                            # Ensure top block is air
                            top = self.bot.blockAt(Vec3(
                                pos.x + x_offset,
                                pos.y + y_offset,
                                pos.z + z_offset
                            ))
                            
                            # Ensure bottom block is diggable solid block
                            bottom = self.bot.blockAt(Vec3(
                                pos.x + x_offset,
                                pos.y - 1,
                                pos.z + z_offset
                            ))
                            # Conditional checks
                            if (not top or top.name != 'air' or 
                                not bottom or not hasattr(bottom, 'drops') or not bottom.diggable):
                                empty = False
                                break
                        
                        if not empty:
                            break
                
                # Yield position if adequate space is found
                if empty:
                    result = pos
                    return result
            
            # Return None if no adequate space found
            return None
            
        except Exception as e:
            # Return default value if error occurs
            self.bot.chat(f"An error occurred while searching for free space: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # Output debug info
            position = self.bot.entity.position
            print(f"Debug: {position}")
            
            # Return bot's feet coordinates as default value
            return Vec3(int(position.x), int(position.y) + y_offset, int(position.z))
        
    async def craft_items(self, item_name, num=1):
        """
        Crafts the specified number of the specified item.
        
        This method performs the following operations:
        1. Searches for the recipe of the specified item.
        2. If the retrieved recipe requires a crafting table, placing a crafting table from inventory or finds a nearby one.
        3. Checks if the required materials are in the inventory.
        4. Executes crafting.
        5. Returns the results and details of the crafted item.
        
        Args:
            item_name (str): Name of the item to craft. Use Minecraft internal item names.
                             (e.g., "stick", "crafting_table", "wooden_pickaxe")
            num (int): Number to craft. Default is 1.
            
        Returns:
            dict: Dictionary containing the results
                - success (bool): True if crafting succeeds, False if it fails.
                - message (str): Result message.
                - error (str, optional): Error code if there is an error.
                - exception (str, optional): Exception message if an exception occurred.
                - item (str): Name of the item attempted to craft.
                - count (int): Number attempted to craft.
        """
        self.bot.chat(f"Crafting {str(num)} {str(item_name)}(s).")
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
                # Investigate required materials if there's a shortage
                required_materials = []
                # Fetch required materials from recipe
                recipe_data = self.get_item_crafting_recipes(item_name)
                if recipe_data and recipe_data[0]:
                    recipe_dict = recipe_data[0][0]
                    required_materials = [f"{key}: {value}" for key, value in recipe_dict.items()]
                else:
                    required_materials.append("Recipe not found")
                
                error_msg = f"Insufficient materials to craft {str(item_name)}"
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

            # If crafting table is needed
            if not any(True for _ in recipes) and any(True for _ in crafting_table_recipes):  # Proxy object empty check
                recipes = self.bot.recipesFor(item_id, None, num, True)
                if not recipes:
                    self.bot.chat(f"Recipe for {str(item_name)} not found")
                    error_msg = f"Recipe for {str(item_name)} not found"
                    self.bot.chat(error_msg)
                    result["message"] = error_msg
                    result["error"] = "recipe_not_found"
                    return result
                    
                # Search for crafting table
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
                        self.bot.chat(f"Crafting {str(item_name)} requires a crafting table, but none was found within 32 blocks and none in inventory.")
                        error_msg = f"Crafting {str(item_name)} requires a crafting table, but none was found within 32 blocks and none in inventory."
                        self.bot.chat(error_msg)
                        result["message"] = error_msg
                        result["error"] = "crafting_table_required"
                        return result
                else:
                    # If there's a crafting table nearby, fetch recipe
                    recipes = self.bot.recipesFor(item_id, None, 1, crafting_table)
                
            # Move to crafting table
            if crafting_table and self.bot.entity.position.distanceTo(crafting_table.position) > 4:
                move_result = await self.move_to_position(crafting_table.position.x, crafting_table.position.y, crafting_table.position.z)
                if not move_result:
                    error_msg = "Could not move to crafting table"
                    self.bot.chat(str(error_msg))
                    result["message"] = error_msg
                    result["error"] = "movement_failed"
                    return result
                
            recipe = recipes[0]
            try:

                # Check recipe validity
                if not recipe or not hasattr(recipe, 'result'):
                    error_msg = f"Could not find a valid recipe for {str(item_name)}"
                    self.bot.chat(str(error_msg))
                    result["message"] = error_msg
                    result["error"] = "invalid_recipe"
                    return result

                # Execute craft
                self.bot.craft(recipe, num, crafting_table)
                success_msg = f"Crafted {str(num)} {str(item_name)}(s)"
                self.bot.chat(success_msg)
                
                # Retrieve the placed crafting table
                if placed_table:
                    await self.collect_block('crafting_table', 1)
                
                result["success"] = True
                result["message"] = success_msg
                return result
                
            except Exception as e:
                error_msg = f"An error occurred while crafting: {str(e)}"
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
        Places a block at the specified coordinates. Places off an adjacent block.
        Fails if there is a block at the placement location or no placeable surface.
        
        Args:
            block_name (str): Name of the block to place
            x : Target X coordinate
            y : Target Y coordinate
            z : Target Z coordinate
            place_on (str): Preferred face direction for placement. Choose from 'top', 'bottom', 'north', 'south', 'east', 'west', 'side'. Default 'bottom'
            dont_cheat (bool): Whether to place in a non-cheaty way. Default is False
            
        Returns:
            dict: Dictionary containing results
                - success (bool): True if placed successfully, False otherwise
                - message (str): Result message
                - position (dict): Attempted placement position {x, y, z}
                - block_name (str): Block name attempted to place
                - error (str, optional): Error code if any
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
            
            # Fetch ID from block name
            block_id = self._get_item_id(block_name)
    
            if block_id is None:
                self.bot.chat(f"Invalid block name: {block_name}")
                result["message"] = f"Invalid block name: {block_name}"
                result["error"] = "invalid_block_name"
                self.bot.chat(result["message"])
                return result
        except Exception as e:
            self.bot.chat(f"Error validating block name: {str(e)}")
            result["message"] = f"Error validating block name: {str(e)}"
            result["error"] = "block_validation_error"
            self.bot.chat(result["message"])
            return result
            
        # Instantiate Vec3 object
        Vec3 = require('vec3')
        target_dest = Vec3(int(x), int(y), int(z))
        
        try:
            # Correct item names (some block names differ when placed)
            item_name = block_name
            if item_name == "redstone_wire":
                item_name = "redstone"
                
            # Search for block in inventory
            block_item = None
            for item in self.bot.inventory.items():
                if item.name == item_name:
                    block_item = item
                    break
            
            # Fail if block is missing
            if not block_item:
                result["message"] = f"{block_name} is not in your inventory"
                result["error"] = "item_not_in_inventory"
                self.bot.chat(result["message"])
                return result
                
            # Check the destination block
            target_block = self.bot.blockAt(target_dest)
            if target_block.name == block_name:
                result["message"] = f"{block_name} is already at coordinates ({target_block.position})"
                result["error"] = "block_already_exists"
                self.bot.chat(result["message"])
                return result
                
            # Check if space is placeable
            empty_blocks = ['air', 'water', 'lava', 'grass', 'short_grass', 'tall_grass', 'snow', 'dead_bush', 'fern']
            if target_block.name not in empty_blocks:
                result["message"] = f"Coordinates ({target_block.position}) is already occupied by {target_block.name}"
                
                # Try breaking it
                break_result = await self._break_block_at(x, y, z)
                if not break_result["success"]:
                    result["message"] = f"Failed to break {target_block.name} which occupied the placement location"
                    result["error"] = "space_occupied"
                    self.bot.chat(result["message"])
                    return result
                    
                # Wait slightly for the block to break
                await asyncio.sleep(0.2)
                
            # Map placement directions
            dir_map = {
            'top': Vec3(0, 1, 0),
            'bottom': Vec3(0, -1, 0),
            'north': Vec3(0, 0, -1),
            'south': Vec3(0, 0, 1),
            'east': Vec3(1, 0, 0),
            'west': Vec3(-1, 0, 0)
            }
        
            # Create a list of placement directions
            directions = []
            if place_on == 'side':
                # Prioritize side placement
                directions.extend([dir_map['north'], dir_map['south'], dir_map['east'], dir_map['west']])
            elif place_on in dir_map:
                # Prioritize specified direction
                directions.append(dir_map[place_on])
            else:
                # Default to bottom
                directions.append(dir_map['bottom'])
                result["message"] += f"\nUnknown placement direction '{place_on}'. Defaulting to 'bottom'."
                
            # Add other directions (lower priority)
            for direction in dir_map.values():
                if not any(d.x == direction.x and d.y == direction.y and d.z == direction.z for d in directions):
                    directions.append(direction)
                    
            # Search for block to build off of
            build_off_block = None
            face_vec = None
            
            for direction in directions:
                ref_pos = target_dest.plus(direction)
                ref_block = self.bot.blockAt(ref_pos)
                
                if ref_block and ref_block.name not in empty_blocks:
                    build_off_block = ref_block
                    # Invert direction (placement surface is on the opposite side)
                    face_vec = Vec3(-direction.x, -direction.y, -direction.z)
                    break
                    
            # Fail if no build-off block found
            if not build_off_block:
                result["message"] = f"No placeable block surfaces found at coordinates ({target_dest})"
                result["error"] = "no_adjacent_block"
                self.bot.chat(result["message"])
                return result
                
            # Check player and block position relation
            player_pos = self.bot.entity.position
            player_pos_above = player_pos.plus(Vec3(0, 1, 0))
            
            # Some blocks can be placed without moving
            dont_move_for = [
                'torch', 'redstone_torch', 'redstone_wire', 'lever', 'button', 
                'rail', 'detector_rail', 'powered_rail', 'activator_rail', 
                'tripwire_hook', 'tripwire', 'water_bucket'
            ]
            
            # Ensure the player doesn't intersect with the placed block
            if block_name not in dont_move_for and (
                player_pos.distanceTo(target_block.position) < 1 or 
                player_pos_above.distanceTo(target_block.position) < 1
            ):
                # Step away slightly if player is intersecting
                try:
                    goal = self.pathfinder.goals.GoalNear(target_block.position.x, target_block.position.y, target_block.position.z, 2)
                    inverted_goal = self.pathfinder.goals.GoalInvert(goal)
                    self.bot.pathfinder.goto(inverted_goal)
                except Exception as e:
                    result["message"] = f"Error stepping away from placement location: {str(e)}"
                    result["error"] = "movement_error"
                    self.bot.chat(result["message"])
                    return result
            
            # Move closer if block is too far
            if self.bot.entity.position.distanceTo(target_block.position) > 4.5:
                try:
                    await self.move_to_position(target_block.position.x, target_block.position.y, target_block.position.z, 4)
                except Exception as e:
                    result["message"] = f"Error trying to approach the block: {str(e)}"
                    result["error"] = "movement_error"
                    self.bot.chat(result["message"])
                    return result
                    
            # Hold the block
            self.bot.equip(block_item, 'hand')
            
            # Look at target block face
            self.bot.lookAt(build_off_block.position)
            
            # Place the block
            try:
                self.bot.placeBlock(build_off_block, face_vec)
                result["message"] = f"Placed {block_name} at coordinates ({target_dest})"
                result["success"] = True
                self.bot.chat(result["message"])
                
                # Wait briefly for completion
                await asyncio.sleep(0.2)
                return result
            except Exception as e:
                result["message"] = f"An error occurred while placing {block_name}: {str(e)}"
                result["error"] = "block_placement_error"
                self.bot.chat(result["message"])
                return result
                
        except Exception as e:
            result["message"] = f"An unexpected error occurred during block placement: {str(e)}"
            result["error"] = "unexpected_error"
            self.bot.chat(result["message"])
            import traceback
            traceback.print_exc()
            return result
    
    async def equip(self, item_name):
        """
        Equips the specified item to the appropriate equipment slot (tools, armor, etc.).
        
        Args:
            item_name (str): Name of the item or block to equip
            
        Returns:
            dict: Dictionary containing results
                - success (bool): True if equipped successfully, False otherwise
                - message (str): Result message
                - item (str): Item name attempted to equip
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
                result["message"] = f"Cannot equip {item_name}. It is not in your inventory."
                self.bot.chat(result["message"])
                return result
                
            # Determine equipment slot based on item type
            if "leggings" in item_name:
                self.bot.equip(item, "legs")
                slot_type = "legs"
            elif "boots" in item_name:
                self.bot.equip(item, "feet")
                slot_type = "feet"
            elif "helmet" in item_name:
                self.bot.equip(item, "head")
                slot_type = "head"
            elif "chestplate" in item_name or "elytra" in item_name:
                self.bot.equip(item, "torso")
                slot_type = "torso"
            elif "shield" in item_name:
                self.bot.equip(item, "off-hand")
                slot_type = "off-hand"
            else:
                self.bot.equip(item, "hand")
                slot_type = "main hand"
                
            result["success"] = True
            result["message"] = f"Equipped {item_name} to {slot_type}."
            self.bot.chat(result["message"])
            return result
            
        except Exception as e:
            result["message"] = f"Error occurred while equipping {item_name}: {str(e)}"
            self.bot.chat(result["message"])
            return result
            
    async def discard(self, item_name, num=-1):
        """
        Discards the specified item.
        
        Args:
            item_name (str): Name of the item or block to discard
            num (int): Number of items to discard. Default is -1, which discards all items of that name.
            
        Returns:
            dict: Dictionary containing results
                - success (bool): True if item discarded successfully, False otherwise
                - message (str): Result message
                - item (str): Item name attempted to discard
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
                
                # Stop if discarded specified amount
                if num != -1 and discarded >= num:
                    break
            
            if discarded == 0:
                result["message"] = f"Cannot discard {item_name}. It is not in your inventory."
                self.bot.chat(result["message"])
                return result
            
            result["success"] = True
            result["count"] = discarded
            result["message"] = f"Discarded {discarded} {item_name}(s)."
            self.bot.chat(result["message"])
            return result
            
        except Exception as e:
            result["message"] = f"Error occurred while discarding {item_name}: {str(e)}"
            self.bot.chat(result["message"])
            return result

    async def put_in_chest(self, item_name, num=-1):
        """
        Puts specified item into the nearest chest. Unstackable items like tools can only be inserted one at a time. Run multiple times in that case.

        Args:
            item_name (str): Name of the item or block to put in the chest
            num (int): Number of items to put in. Default is -1, which puts all in.
            
        Returns:
            dict: Dictionary containing results
                - success (bool): True if item put in chest successfully, False otherwise
                - message (str): Result message
                - item (str): Item name attempted to put in chest
                - count (int): Number of items put in chest
        """
        result = {
            "success": False,
            "message": "",
            "item": item_name,
            "count": 0
        }
        
        try:
            # Look for the nearest chest
            chest = await self.get_nearest_block("chest", 32)
            if not chest:
                result["message"] = "No chest found nearby."
                self.bot.chat(result["message"])
                return result
                
            # Search for item in inventory
            item = None
            for slot_item in self.bot.inventory.items():
                if slot_item and slot_item.name == item_name:
                    item = slot_item
                    break
                    
            if not item:
                result["message"] = f"Cannot put {item_name} in chest. It is not in your inventory."
                self.bot.chat(result["message"])
                return result
                
            # Calculate number to put in chest
            to_put = item.count if num == -1 else min(num, item.count)
            
            # Move to chest
            await self.move_to_position(chest.position.x, chest.position.y, chest.position.z, 2)
            
            # Open chest
            chest_container = self.bot.openContainer(chest)
            
            # Put items in chest
            chest_container.deposit(item.type, None, to_put)
            
            # Close chest
            chest_container.close()
            
            result["success"] = True
            result["count"] = to_put
            result["message"] = f"Put {to_put} {item_name}(s) in the chest."
            self.bot.chat(result["message"])
            return result
            
        except Exception as e:
            result["message"] = f"Error occurred while putting {item_name} in the chest: {str(e)}"
            self.bot.chat(result["message"])
            return result

    async def take_from_chest(self, item_name, num=-1):
        """
        Takes the specified item out of the nearest chest.
        
        Args:
            item_name (str): Name of the item or block to take out
            num (int): Number of items to take out. Default is -1, which takes all out.
            
        Returns:
            dict: Dictionary containing results
                - success (bool): True if item taken from chest successfully, False otherwise
                - message (str): Result message
                - item (str): Item name attempted to take out
                - count (int): Number of items taken out
        """
        result = {
            "success": False,
            "message": "",
            "item": item_name,
            "count": 0
        }
        
        try:
            # Look for nearest chest
            chest = await self.get_nearest_block("chest", 32)
            if not chest:
                result["message"] = "No chest found nearby."
                self.bot.chat(result["message"])
                return result
                
            # Move to chest
            await self.move_to_position(chest.position.x, chest.position.y, chest.position.z, 2)
            
            # Open chest
            chest_container = self.bot.openContainer(chest)
            
            # Look for item in chest
            item = None
            for container_item in chest_container.containerItems():
                if container_item and container_item.name == item_name:
                    item = container_item
                    break
                    
            if not item:
                result["message"] = f"{item_name} not found in the chest."
                chest_container.close()
                self.bot.chat(result["message"])
                return result
                
            # Calculate number to take out
            to_take = item.count if num == -1 else min(num, item.count)
            
            # Take item out of chest
            chest_container.withdraw(item.type, None, to_take)
            
            # Close chest
            chest_container.close()
            
            result["success"] = True
            result["count"] = to_take
            result["message"] = f"Took {to_take} {item_name}(s) from the chest."
            self.bot.chat(result["message"])
            return result
            
        except Exception as e:
            result["message"] = f"Error occurred while taking {item_name} from the chest: {str(e)}"
            self.bot.chat(result["message"])
            return result

    async def view_chest(self,maxDistance=32):
        """
        Moves to a nearby chest and shows its contents. If there are multiple chests, shows the contents of all of them.
        
        Returns:
            dict: Dictionary containing results
                - success (bool): True if chest contents could be displayed, False otherwise
                - message (str): Result message
                - result_list (list, optional): List of items in chest (only on success)

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
                            'items': 'Chest is empty'
                        }
                    ]
            }
        """
        result = {
            "success": False,
            "message": ""
        }
        
        try:
            # Look for the nearest chest
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
                # Move to chest
                move_result = await self.move_to_position(chest_pos.x, chest_pos.y, chest_pos.z, 2)
                if not move_result["success"]:
                    result["message"] = f"Failed to move to chest: {move_result.get('message', 'Unknown error')}"
                    self.bot.chat(result["message"])
                    return result
            
                # Open chest
                chest_block = self.bot.blockAt(chest_pos)
                chest_container = self.bot.openContainer(chest_block)
            
                # Get items in chest
                items = chest_container.containerItems()
            
                # Convert items to list
                item_list = []
                result_dict = {}
                if items:
                    for item in items:
                        if item:  # Only append non-None items
                            item_list.append({
                                "name": item.name,
                                "count": item.count
                            })
                if not item_list:
                    result_dict["position"] = {"x": chest_pos.x, "y": chest_pos.y, "z": chest_pos.z}
                    result_dict["items"] = "Chest is empty."
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
            result["message"] = f"Error occurred while displaying chest contents: {str(e)}"
            self.bot.chat(result["message"])
            return result

    async def consume(self, item_name=""):
        """
        Eats/drinks one of the specified item.
        Cannot consume if hunger is max.
        
        Args:
            item_name (str): Name of item to eat/drink. Default is empty string, which assumes holding item to consume.
        """
        result = {
            "success": False,
            "message": ""
        }
        
        try:
            # Check hunger
            if hasattr(self.bot, 'food') and self.bot.food >= 20:
                result["message"] = "Cannot consume more food, hunger is maximized."
                self.bot.chat(result["message"])
                return result

            item = None
            name = item_name
            
            # If item name is specified, search for it in inventory
            if item_name:
                for inv_item in self.bot.inventory.items():
                    if inv_item.name == item_name:
                        item = inv_item
                        break
            
            # If item not found
            if not item:
                result["message"] = f"Cannot consume {name if name else 'specified item'}. Item is not in inventory."
                self.bot.chat(result["message"])
                return result
                
            # Hold the item
            self.bot.equip(item, 'hand')
            
            # Consume item
            self.bot.consume()
            
            result["success"] = True
            result["item"] = item.name
            result["message"] = f"Consumed {item.name}."
            self.bot.chat(result["message"])
            return result
            
        except Exception as e:
            result["message"] = f"Error occurred while consuming item: {str(e)}"
            self.bot.chat(result["message"])
            return result

    async def go_to_nearest_block(self, block_name, min_distance=2, range=64):
        """
        Moves to the nearest block of the specified type.
        
        Args:
            block_name (str): Destination block name
            min_distance (int): Distance to keep from block. Default 2
            range (int): Max search range for the block. Default 64
            
        Returns:
            dict: Dictionary containing results
                - success (bool): True if reached the block successfully, False otherwise
                - message (str): Result message
                - block_name (str): Searched block name
                - position (dict, optional): Position of found block {x, y, z} (only on success)
        """
        result = {
            "success": False,
            "message": "",
            "block_name": block_name
        }
        
        try:
            # Enforce max search range
            MAX_RANGE = 512
            if range > MAX_RANGE:
                range = MAX_RANGE
                self.bot.chat(f"Limiting max search range to {MAX_RANGE} blocks.")
                
            # Find closest block
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
            
            # Move to block
            move_result = await self.move_to_position(position.x, position.y, position.z, min_distance)
            if not move_result["success"]:
                result["message"] = f"Error occurred moving to {block_name}: {move_result['message']}"
                self.bot.chat(result["message"])
                return result
                
            result["success"] = True
            result["message"] = f"Arrived at {block_name} (X:{position.x}, Y:{position.y}, Z:{position.z})."
            self.bot.chat(result["message"])
            return result
            
        except Exception as e:
            result["message"] = f"Unexpected error occurred moving to {block_name}: {str(e)}"
            self.bot.chat(result["message"])
            import traceback
            traceback.print_exc()
            return result

    async def go_to_nearest_entity(self, entity_type, min_distance=2, range=64):
        """
        Moves to the nearest entity of the specified type.
        
        Args:
            entity_type (str): The entity type to move to (e.g. "zombie", "sheep", "villager", etc)
            min_distance (int): Distance to keep from the entity after moving. Default 2
            range (int): Max search range for the entity. Default 64
            
        Returns:
            dict: Dictionary containing results
                - success (bool): True if reached the entity successfully, False otherwise
                - message (str): Result message
                - entity_type (str): Searched entity type
                - position (dict, optional): Position of found entity {x, y, z} (only on success)
                - distance (float, optional): Distance from original position to entity (only on success)
        """
        result = {
            "success": False,
            "message": "",
            "entity_type": entity_type
        }
        
        try:
            # Find the specified entity type
            entity = self._get_nearby_entity_of_type(entity_type, range)
            if not entity:
                result["message"] = f"No {entity_type} found within {range} blocks."
                self.bot.chat(result["message"])
                return result
                
            # Get entity position
            position = entity.position
            result["position"] = {
                "x": position.x,
                "y": position.y,
                "z": position.z
            }
            
            # Calculate distance to entity
            distance = self.bot.entity.position.distanceTo(position)
            result["distance"] = distance
            
            # Announce found entity
            self.bot.chat(f"Found {entity_type} {distance} blocks away.")
            
            # Move to entity
            move_result = await self.move_to_position(position.x, position.y, position.z, min_distance)
            if not move_result["success"]:
                result["message"] = f"Error occurred moving to {entity_type}: {move_result['message']}"
                self.bot.chat(result["message"])
                return result
                
            result["success"] = True
            result["message"] = f"Arrived at {entity_type}."
            self.bot.chat(result["message"])
            return result
            
        except Exception as e:
            result["message"] = f"Unexpected error occurred moving to {entity_type}: {str(e)}"
            self.bot.chat(result["message"])
            import traceback
            traceback.print_exc()
            return result

    async def go_to_bed(self):
        """
        Sleep in the nearest bed.
        
        Returns:
            dict: Dictionary containing results
                - success (bool): True if slept in bed successfully, False otherwise
                - message (str): Result message
                - bed_position (dict, optional): Bed position {x, y, z} (only on success)
        """
        result = {
            "success": False,
            "message": ""
        }
        
        try:
            # Check time and weather
            if not (self.bot.time.isNight or self.bot.isRaining):
                result["message"] = "It is not time to sleep yet. You can only sleep at night or during thunderstorms."
                self.bot.chat(result["message"])
                return result
            
            # Find a nearby bed
            # Search for bed using isABed method
            beds = self.bot.findBlocks({
                'matching': self.bot.isABed,
                'maxDistance': 32,
                'count': 1
            })
            
            if not beds or not any(True for _ in beds):
                result["message"] = "No bed found within 32 blocks."
                self.bot.chat(result["message"])
                return result
                
            # Get bed position
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
                result["message"] = f"Error sleeping in bed: {str(e)}"
                self.bot.chat(result["message"])
                
            return result
            
        except Exception as e:
            result["message"] = f"Error sleeping in bed: {str(e)}"
            self.bot.chat(result["message"])
            import traceback
            traceback.print_exc()
            return result

    async def move_away(self, distance):
        """
        Moves away from the current position by the specified distance in a random direction.
        
        Args:
            distance (int): Distance to move
            
        Returns:
            dict: Dictionary containing results
                - success (bool): True if moved successfully, False otherwise
                - message (str): Result message
                - start_position (dict): Starting position {x, y, z}
                - end_position (dict, optional): Position after moving {x, y, z} (only on success)
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
            
            # Use GoalNear and GoalInvert to set a goal to move away
            if hasattr(self.pathfinder.goals, 'GoalNear') and hasattr(self.pathfinder.goals, 'GoalInvert'):
                goal = self.pathfinder.goals.GoalNear(current_pos.x, current_pos.y, current_pos.z, distance)
                inverted_goal = self.pathfinder.goals.GoalInvert(goal)
                
                # Pathfinder config
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
                        # Try normal movement
                
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
                result["message"] = "Pathfinder goal functionality is unavailable."
                self.bot.chat(result["message"])
                return result
                
        except Exception as e:
            result["message"] = f"Unexpected error occurred during movement: {str(e)}"
            self.bot.chat(result["message"])
            import traceback
            traceback.print_exc()
            return result

    async def avoid_enemies(self, distance=16):
        """
        Escapes from nearby hostile entities.
        Looks for a location furthest away from all nearby hostile entities and moves there. Stops after reaching the destination.
        
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
        
        # Calculate repulsion vector from each enemy (direction moving player away from each enemy)
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
            
            # Use inverse distance as weight (escape stronger from closer enemies)
            weight = 1.0 / (dist + 0.1)  # Prevent division by zero
            
            # Normalize (convert to unit vector) and apply weight
            norm = (dx**2 + dz**2) ** 0.5  # Horizontal distance
            if norm > 0:
                escape_vector['x'] += (dx / norm) * weight
                escape_vector['z'] += (dz / norm) * weight
        
        # Calculate final move distance (vector normalization)
        magnitude = (escape_vector['x']**2 + escape_vector['z']**2) ** 0.5
        if magnitude > 0:
            escape_vector['x'] /= magnitude
            escape_vector['z'] /= magnitude
        else:
            # Escape in a random direction if enemies are balanced from all directions
            import random
            angle = random.uniform(0, 2 * 3.14159)
            escape_vector['x'] = math.cos(angle)
            escape_vector['z'] = math.sin(angle)
        
        # Calculate final target position (current pos + move dist * direction vector)
        target_x = player_pos.x + distance * escape_vector['x'] # Direction away from enemies
        target_z = player_pos.z + distance * escape_vector['z'] # Direction away from enemies
        
        # Move to destination
        self.bot.chat(f"Escaping in direction x:{target_x:.1f}, z:{target_z:.1f}.")
        await self.move_to_position(target_x, player_pos.y, target_z, min_distance=2,canDig=False)
        
        result["success"] = True
        result["message"] = "Escaped from hostile entities."
        self.bot.chat(result["message"])
        return result

    async def collect_block(self, block_name, num=1, exclude=None):
        """
        Mines and collects the specified number of the specified block name.
        Finds the nearest safely minable block, equips appropriate tool and attempts to collect it.
        Good for mining or collecting specific blocks where coordinates are unknown.
        Will fail if inventory is full or if lacking appropriate tools.

        Args:
            block_name (str): Name of the block to collect (e.g., "oak_log", "stone", "coal_ore").
                            For ores, specifying "coal" will search for both "coal_ore" and "deepslate_coal_ore".
                            Specifying "dirt" will also target "grass_block".
            num (int, optional): Target number of blocks to collect. Defaults to 1.
            exclude (list[Vec3], optional): List of block coordinates (Vec3 objects) to exclude from collection.
                                         Used to ignore blocks at specific locations. Defaults to None.

        Returns:
            dict: Dictionary with collection result details.
                - success (bool): True if at least 1 block collected successfully, False otherwise.
                - message (str): Message indicating processing result.
                - result (dict): Inventory info after collection.
                - block_name (str): Original block name attempted to collect.
                - error (str, optional): Error code if an error occurred.
        Example:
            >> await skills.collect_block('cobblestone', num=11)
            {
                "success": True,
                "message": "Collected 11 cobblestone.",
                "result": {'cobblestone': 11, 'stone_pickaxe': 1},
                "block_name": "cobblestone"
            }
            >> await skills.collect_block('Jungle Log', num=11)
            {
                'success': False,
                'message': 'Cannot find Jungle Log nearby.',
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
        print(f"Acquiring {block_name} block.")
        if num < 1:
            result["message"] = f"Invalid collect quantity: {num}"
            result["error"] = "invalid_number"
            print(result["message"])
            return result
        
        # Add equivalent block types to list
        blocktypes = [block_name]
        
        # Special handling: support for ore blocks
        ores = ['coal', 'diamond', 'emerald', 'iron', 'gold', 'lapis_lazuli', 'redstone']
        if block_name in ores:
            blocktypes.append(f"{block_name}_ore")
        # Deepslate ore support
        if block_name.endswith('ore'):
            blocktypes.append(f"deepslate_{block_name}")
        # Special handling for dirt
        if block_name == 'dirt':
            blocktypes.append('grass_block')
        
        for i in range(num):
            blocks = []
            for btype in blocktypes:
                found_block = await self.get_nearest_block(btype, 500)
                await asyncio.sleep(0.1)
                if found_block:
                    blocks.append(found_block)
            
            # Filter excluded locations
            if exclude and blocks:
                blocks = [block for block in blocks if not any(
                    block.position.x == pos.x and 
                    block.position.y == pos.y and 
                    block.position.z == pos.z 
                    for pos in exclude
                )]
            # Filter safely minable blocks
            movements = self.bot.pathfinder.movements
            movements.dontMineUnderFallingBlock = False
            blocks = [block for block in blocks if movements.safeToBreak(block)]
            if not blocks:
                result["message"] = f"Cannot find {block_name} nearby."
                result["error"] = "no_blocks_found"
                break
                
            block = blocks[0]
            # Equip appropriate tool
            self.bot.tool.equipForBlock(block)
            if self.bot.heldItem:
                held_item_id = self.bot.heldItem.type
            else:
                held_item_id = None
            if not block.canHarvest(held_item_id):
                self.bot.chat(f"No appropriate tool to mine {str(block_name)}.")
                result["message"] = f"No appropriate tool to mine {block_name}."
                result["error"] = "no_suitable_tool"
                print(result["message"])
                return result
            try:
                move_result = await self.move_to_position(block.position.x, block.position.y, block.position.z, min_distance=1,dontcreateflow=False)
                if not move_result["success"]:
                    result["message"] = f"Failed to collect {block_name}: {move_result['message']}"
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
                    result["message"] = f"Failed to collect {block_name}: Inventory is full and no storage space."
                    result["error"] = "inventory_full"
                    print(result["message"])
                    break
                else:
                    result["message"] = f"Failed to collect {block_name}: {str(e)}"
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
        Determines whether a torch should be placed based on presence of nearby torches and if there are torches in the inventory.
        
        Returns:
            bool: True if a torch should be placed, False otherwise
        """
        pos = self.bot.entity.position
        
        # Look for nearby torches
        nearest_torch =await self.get_nearest_block('torch', 6)
        if not nearest_torch:
            nearest_torch = await self.get_nearest_block('wall_torch', 6)
            
        # If no torches nearby
        if not nearest_torch:
            # Check current position block
            block = self.bot.blockAt(pos)
            
            # Check if there are torches in inventory
            has_torch = False
            if hasattr(self.bot, 'inventory') and hasattr(self.bot.inventory, 'items'):
                for item in self.bot.inventory.items():
                    if item and hasattr(item, 'name') and item.name == 'torch':
                        has_torch = True
                        break
                    
            # Placeable if current pos is air and holding a torch
            return has_torch and block and hasattr(block, 'name') and block.name == 'air'
            
        return False
        
    async def auto_light(self):
        """
        Places a torch if there are no torches nearby, if there are torches in the inventory, and if the current position is air.
        
        Returns:
            bool: True if placed a torch, False otherwise
        """
        try:
            if await self.should_place_torch():
                pos = self.bot.entity.position
                Vec3 = require('vec3')
                # Place torch at feet
                floor_pos = Vec3(
                    round(pos.x),
                    round(pos.y) - 1,  # Feet
                    round(pos.z)
                )
                
                # Place torch
                result = await self.place_block('torch', floor_pos.x, floor_pos.y + 1, floor_pos.z, 'bottom')
                
                if result:
                    # Record the position of the last placed torch
                    self._last_torch_pos = pos.clone()
                    return True
            return False
        except Exception as e:
            print(f"Error placing torch: {e}")
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
            print(f"Error getting block names: {e}")
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
        Moves to the specified position. If canDig=True, mines blocking blocks while moving.
        If movement is not completed within the specified time, or if unreachable, it will timeout.

        Args:
            x (float): Destination X coordinate
            y (float): Destination Y coordinate
            z (float): Destination Z coordinate
            min_distance (int): Minimum distance from target position. Default 2
            canDig (bool): Whether to destroy blocks obstructing movement. Default True
            canPlaceOn (bool): Whether to allow placing blocks during movement. Default True
            allow1by1towers (bool): Whether to allow building 1x1 towers to climb. Default False
            dontcreateflow (bool): Whether to avoid mining blocks touching liquid blocks that obstruct movement. Default True
            dontMineUnderFaillingBlock (bool): Whether to allow digging under falling blocks like sand. Default True
            dontMoveUnderLiquid (bool): Whether to return an error if the specified destination coordinate is a liquid block. Default True
            onlyCheckPath (bool): Check if it is possible to move to the destination. Default False
            move_timeout (int): Movement timeout time (seconds). Default 60

        Returns:
            dict: Dictionary containing movement results
                - success (bool): True if moved successfully, False otherwise
                - error (str): Error code on movement failure (path_not_found, path_timeout, move_timeout, liquid_block, unexpected_error, move_failed)
                - message (str): Movement result message
                - position (dict): Coordinates after movement (e.g. {"x": 10, "y": 20, "z": 30})
        """
        if not onlyCheckPath:
            print(f"Moving to {x}, {y}, {z}.")
        # Get current pos and target pos
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

        # Calculate distance between current pos and target pos
        distance_to_target = ((current_pos.x - x) ** 2 +
                              (current_pos.y - y) ** 2 +
                              (current_pos.z - z) ** 2) ** 0.5
        # Skip movement if already close enough to target pos
        if distance_to_target <= min_distance:
            result["success"] = True
            result["message"] = f"Skipping movement, already close enough to {x}, {y}, {z}."
            # Update position
            result["position"] = { "x": current_pos.x, "y": current_pos.y, "z": current_pos.z }
            print(result["message"])
            return result
        if dontMoveUnderLiquid:
            Vec3 = require('vec3')
            target_block = self.bot.blockAt(Vec3(x, y, z))
            if target_block and (target_block.name == 'water' or target_block.name == 'lava'):
                result["message"] = f"Target position {x}, {y}, {z} is a liquid block. Canceling movement to avoid drowning/burning."
                result["error"] = "liquid_block"
                print(result["message"])
                return result

        try:
            # Configure pathfinder movements
            movements = self.pathfinder.Movements(self.bot)
            movements.canDig = canDig
            movements.dontCreateFlow = dontcreateflow
            movements.dontMineUnderFaillingBlock = dontMineUnderFaillingBlock
            movements.canPlaceOn = canPlaceOn
            movements.allow1by1towers = allow1by1towers
            self.bot.pathfinder.setMovements(movements)
            # Set target pos
            goal = self.pathfinder.goals.GoalNear(x, y, z, min_distance)
            # Get path
            path = self.bot.pathfinder.getPathTo(movements,goal)
            if path.status == "error":
                result["message"] = f"Could not generate a path to the target location. The destination might be underwater/in lava, or blocked by blocks/spaces unminable with current equipment."
                result["error"] = "path_not_found"
                self.bot.chat(result["message"])
                return result
            elif path.status == "timeout":
                result["message"] = f"Path generation timed out. Target location might be too far."
                result["error"] = "path_timeout"
                self.bot.chat(result["message"])
                return result
            if onlyCheckPath:
                result["success"] = True
                result["message"] = f"Can move to target location {x}, {y}, {z}."
                return result
            # Move to target
            self.bot.pathfinder.setGoal(goal)
            await asyncio.sleep(1)

            last_position = None
            stuck_time = 0
            temp_free_space = None
            move_start_time = asyncio.get_event_loop().time() # Record start time
            while self.bot.pathfinder.isMoving() or self.bot.pathfinder.isMining() or self.bot.pathfinder.isBuilding():
                # --- Timeout check ---
                current_time = asyncio.get_event_loop().time()
                if (current_time - move_start_time) > move_timeout:
                    print(f"Timed out. Exceeded max movement time. Stopping action midway ({move_timeout}s).")
                    self.bot.pathfinder.setGoal(None) # Reset goal
                    await asyncio.sleep(1) # Wait for goal reset
                    result["success"] = False
                    result["message"] = f"Timed out. Exceeded max movement time. Stopping action midway ({move_timeout}s)."
                    result["error"] = "move_timeout"
                    # Record current pos
                    current_pos_timeout = await self.get_bot_position()
                    result["position"] = { "x": current_pos_timeout[0], "y": current_pos_timeout[1], "z": current_pos_timeout[2] }
                    return result
                # --- End timeout check ---
                
                mining = self.bot.pathfinder.isMining()
                building = self.bot.pathfinder.isBuilding()
                current_position = self.bot.entity.position
                # Stuck detection logic
                if not mining and not building:
                    if last_position and (
                        abs(current_position.x - last_position.x) < 0.01 and
                        abs(current_position.y - last_position.y) < 0.01 and
                        abs(current_position.z - last_position.z) < 0.01
                    ):
                        stuck_time += 1
                    else:
                        stuck_time = 0

                    # If stuck in same position for 2+ seconds
                    if stuck_time >= 2:
                        self.bot.chat("Stuck detected. Attempting to resolve.")
                        free_space = None
                        search_distance = 100
                        while free_space is None and search_distance < 500: # Prevent infinite loop
                            free_space = await self.get_nearest_free_space(X_size=1,Y_size=2,Z_size=1,distance=search_distance)
                            if free_space:
                                break
                            search_distance += 100

                        if free_space is None:
                            self.bot.chat("Cannot find a temporary safe space nearby. Aborting movement.")
                            self.bot.pathfinder.setGoal(None) # Reset goal
                            await asyncio.sleep(1)
                            result["success"] = False
                            result["message"] = "Could not find a safe space while resolving stuck issue, movement aborted."
                            result["error"] = "stuck_no_space"
                            current_pos_stuck = await self.get_bot_position()
                            result["position"] = { "x": current_pos_stuck[0], "y": current_pos_stuck[1], "z": current_pos_stuck[2] }
                            return result

                        if temp_free_space and temp_free_space.x == free_space.x and temp_free_space.y == free_space.y and temp_free_space.z == free_space.z:
                            # Warp if temporary movement cannot resolve (Depends on Bot abilities, normally not recommended)
                            # self.bot.chat(f"/tp bot {free_space.x} {free_space.y} {free_space.z}")
                            self.bot.chat("Attempted temporary escape but could not resolve stuck issue. Aborting movement.")
                            self.bot.pathfinder.setGoal(None)
                            await asyncio.sleep(1)
                            result["success"] = False
                            result["message"] = "Failed to resolve stuck issue. Movement aborted."
                            result["error"] = "stuck_unresolved"
                            current_pos_stuck_fail = await self.get_bot_position()
                            result["position"] = { "x": current_pos_stuck_fail[0], "y": current_pos_stuck_fail[1], "z": current_pos_stuck_fail[2] }
                            return result
                        else:
                            # Move to temporary target location
                            temp_goal = self.pathfinder.goals.GoalNear(free_space.x, free_space.y, free_space.z, 0)
                            self.bot.pathfinder.setGoal(temp_goal)
                            await asyncio.sleep(1)
                            temp_free_space = free_space
                            self.bot.chat(f"Temporarily moving to {free_space.x:.1f}, {free_space.y:.1f}, {free_space.z:.1f}.")
                            await asyncio.sleep(2) # Wait for move to temporary target

                        # Reset to original target location
                        self.bot.pathfinder.setGoal(goal)
                        await asyncio.sleep(1)
                        self.bot.chat("Resuming movement to original target.")
                        await asyncio.sleep(0.5)
                        stuck_time = 0
                        move_start_time = asyncio.get_event_loop().time() # Reset timer after resolving stuck

                last_position = current_position
                await asyncio.sleep(0.5) # Loop interval
            # Reset pathfinder goal after move completes
            self.bot.pathfinder.setGoal(None)
            await asyncio.sleep(1)
            # --- Post-move processing ---
            bot_x, bot_y, bot_z = await self.get_bot_position()
            # Calculate distance to target location (fixed indent)
            final_distance_xy = ((bot_x - x) ** 2 + (bot_z - z) ** 2) ** 0.5
            final_distance_y = abs(bot_y - y) - 2
            if final_distance_xy <= min_distance+1:
                result["success"] = True
                result["message"] = f" Arrived at {x}, {y}, {z}"
                
            else:
                print(f"final_distance_xy: {final_distance_xy}\nfinal_distance_y: {final_distance_y}\nmin_distance: {min_distance}\n")
                # If distance is far even with isMoving() being False (e.g. path end point is far from target)
                result["success"] = False
                result["message"] = f"Could not reach {x}, {y}, {z}. Current position is {bot_x:.1f}, {bot_y:.1f}, {bot_z:.1f}. This is a temporary error, trying again may succeed."
                result["error"] = "move_failed"
            result["position"] = {
                "x": bot_x,
                "y": bot_y,
                "z": bot_z
            }
            print(result["message"])

        except Exception as e:
            result["message"] = f"Unexpected error occurred during movement: {str(e)}"
            self.bot.chat(result["message"])
            import traceback
            traceback.print_exc()
            result["error"] = "unexpected_error"
            # Record pos at time of error
            try:
                error_pos = await self.get_bot_position()
                result["position"] = { "x": error_pos[0], "y": error_pos[1], "z": error_pos[2] }
            except: # get_bot_position might also fail
                 result["position"] = {"x": None, "y": None, "z": None}


        return result
        
    async def smelt_item(self, item_name, num=1):
        """
        Smelts items by putting them in a 'furnace' within 32 blocks, or in inventory. Coal, charcoal, and wood can be used as fuel.
        Waits for smelting to complete and collects the items.
        
        Args:
            item_name (str): Name of item to smelt (e.g. "raw_iron", "raw_copper", "beef", etc)
            num (int): Number of items to smelt. Default 1
            
        Returns:
            dict: Dictionary containing results
                - success (bool): True if smelted successfully, False otherwise
                - message (str): Result message
                - smelted (int): Number of smelted items
                - item_name (str): Smelted item name
                - error (str, optional): Error code if errors occurred
        """
        self.bot.chat(f"Smelting {item_name}.")
        result = {
            "success": False,
            "message": "",
            "smelted": 0,
            "item_name": item_name,
        }
        
        # Check if item is smeltable
        is_smeltable = self._is_smeltable(item_name)
        if not is_smeltable:
            result["message"] = f"Cannot smelt {item_name}. Specify raw ores starting with 'raw_ ' or foodstuff."
            result["error"] = "not_smeltable"
            self.bot.chat(result["message"])
            return result
            
        # Look for furnace
        placed_furnace = False
        furnace_block = await self.get_nearest_block('furnace', 32)
        if not furnace_block:
            # Check if own furnace
            if (await self.get_inventory_counts()).get('furnace', 0) > 0:
                # Place furnace
                pos = await self.get_nearest_free_space(X_size=1,Z_size=1,distance=15)
                place_result = await self.place_block('furnace', pos.x, pos.y, pos.z)
                await asyncio.sleep(1)
                if place_result["success"]:
                    furnace_block = await self.get_nearest_block('furnace', 32)
                    placed_furnace = True
                else:
                    result["message"] = "Failed to place furnace"
                    result["error"] = "furnace_placement_failed"
                    self.bot.chat(result["message"])
                    return result
            else:
                result["message"] = f"No furnace nearby and no furnace in inventory"
                result["error"] = "no_furnace"
                self.bot.chat(result["message"])
                return result
                
        # Move to furnace
        if self.bot.entity.position.distanceTo(furnace_block.position) > 4:
            await self.move_to_position(
                furnace_block.position.x, 
                furnace_block.position.y, 
                furnace_block.position.z, 
                2
            )
            
        # Open the furnace
        try:
            # Look at furnace
            self.bot.lookAt(furnace_block.position)
            
            # Open furnace
            furnace = self.bot.openFurnace(furnace_block)
            
            # Check if there is already an item smelting
            input_item = furnace.inputItem()
            if input_item and input_item.type and input_item.count > 0:
                if self._get_item_name(input_item.type) != item_name:
                    result["message"] = f"Furnace is already smelting {self._get_item_name(input_item.type)}"
                    result["error"] = "already_smelting"
                    furnace.close()
                    
                    # Collect placed furnace
                    if placed_furnace:
                        await self.collect_block('furnace', 1)
                        
                    self.bot.chat(result["message"])
                    return result
                    
            # Check if holding item to smelt
            inv_counts = await self.get_inventory_counts()
            if not inv_counts.get(item_name, 0) or inv_counts.get(item_name, 0) < num:
                result["message"] = f"Not enough {item_name} to smelt"
                result["error"] = "insufficient_items"
                furnace.close()
                
                # Collect placed furnace
                if placed_furnace:
                    await self.collect_block('furnace', 1)
                    
                self.bot.chat(result["message"])
                return result
                
            # Check and insert fuel
            if not furnace.fuelItem() or furnace.fuelItem().count <= 0:
                fuel = self._get_smelting_fuel()
                if not fuel:
                    result["message"] = f"No fuel (coal, charcoal, wood, etc) to smelt {item_name}"
                    result["error"] = "no_fuel"
                    furnace.close()
                    
                    # Collect placed furnace
                    if placed_furnace:
                        await self.collect_block('furnace', 1)
                        
                    self.bot.chat(result["message"])
                    print(result)
                    return result
                    
                # Insert fuel
                furnace.putFuel(fuel.type, None, fuel.count)
                self.bot.chat(f"Inserted {fuel.count} {fuel.name} into furnace as fuel")
                print(f"Inserted {fuel.count} {fuel.name} into furnace as fuel")
                
            # Place item to smelt into furnace
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
                        
                # If nothing could be obtained
                if not collected and not collected_last:
                    break  # End if nothing obtained last time and this time
                    
                collected_last = collected
                
            # Close furnace
            furnace.close()
            
            # Collect placed furnace
            if placed_furnace:
                await self.collect_block('furnace', 1)
                
            # Set results
            if total_smelted == 0:
                result["message"] = f"Failed to smelt {item_name}"
                result["error"] = "smelting_failed"
                self.bot.chat(result["message"])
                print(result)
                return result
                
            if total_smelted < num:
                result["message"] = f"Smelted {total_smelted} out of {num} {item_name}"
                result["success"] = True
                result["smelted"] = total_smelted
                
                if smelted_item:
                    result["smelted_item_name"] = self._get_item_name(smelted_item.type)
                    
                self.bot.chat(result["message"])
                print(result)
                return result
                
            result["message"] = f"Smelted {total_smelted} {item_name}"
            if smelted_item:
                result["smelted_item_name"] = self._get_item_name(smelted_item.type)
                result["message"] = f"Smelted {item_name} and obtained {total_smelted} {self._get_item_name(smelted_item.type)}"
                
            result["success"] = True
            result["smelted"] = total_smelted
            self.bot.chat(result["message"])
            print(result)
            return result
            
        except Exception as e:
            result["message"] = f"Error occurred during furnace operation: {str(e)}"
            result["error"] = "furnace_error"
            
            import traceback
            traceback.print_exc()
            print(result)
            self.bot.chat(result["message"])
            
            # Collect placed furnace
            if placed_furnace:
                try:
                    await self.collect_block('furnace', 1)
                except:
                    pass
                    
            return result
    
    async def clear_nearest_furnace(self):
        """
        Finds the nearest furnace and takes out all items inside.
        
        Returns:
            dict: Dictionary containing results
                - success (bool): True if operation successful, False otherwise
                - message (str): Result message
                - items (list): List of collected items
        """
        self.bot.chat("Taking items out of the nearest furnace")
        print("Taking items out of the nearest furnace")
        result = {
            "success": False,
            "message": "",
            "items": []
        }
        
        try:
            # Find the nearest furnace
            furnace_block = await self.get_nearest_block('furnace', 32)
            if not furnace_block:
                result["message"] = "Cannot find a furnace nearby"
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
            
            # Open furnace
            furnace = self.bot.openFurnace(furnace_block)
            
            # Take out items
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
                    
            # Close furnace
            furnace.close()
            
            # Group items by name and calculate total
            item_totals = {}
            
            for item in result["items"]:
                name = item["name"]
                count = item["count"]
                item_totals[name] = item_totals.get(name, 0) + count
                
            # Convert totals to new items list
            grouped_items = []
            for name, count in item_totals.items():
                grouped_items.append({
                    "name": name,
                    "count": count
                })
                
            # Update result
            result["items"] = grouped_items
            
            # Generate result text
            text = ""
            for item in grouped_items:
                text += f"{item['count']} {item['name']}, "
            text = text.rstrip(", ")
            if text=="" :
                result["message"] = "Attempted collection from furnace, but it was empty"
            else:
                result["message"] = f"Collected {text} from furnace"
            result["success"] = True
            
            return result
            
        except Exception as e:
            result["message"] = f"Error occurred while clearing furnace: {str(e)}"
            import traceback
            traceback.print_exc()
            return result
        
    async def attack_nearest(self, mob_type, kill=True,pickup_item=True):
        """
        Attacks a specified type of mob.
        
        Args:
            mob_type: The type of mob to attack
            kill: Whether to continue attacking until the mob dies (default True)
            pickup_item: Whether to pick up dropped items when the mob dies (default True)
        Returns:
            dict: Dictionary containing results
                - success (bool): True if attack successful, False otherwise 
                - message (str): Result message
                - mob_type (str): The type of mob attacked
        """
        self.bot.chat(f"Attacking {mob_type}.")
        print(f"Attacking {mob_type}.")
        result = {
            "success": False,
            "message": "",
            "mob_type": mob_type
        }
        
        # Get nearby entities
        nearby_entities = self._get_nearby_entities(24)
        # Search for entity matching the specified mob_type
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
        
        result["message"] = f'Could not find {mob_type}.'
        self.bot.chat(result["message"])
        print(result)
        return result

    async def attack_entity(self, entity, kill=True,pickup_item=True):
        """
        Attacks a specified entity.
        
        Args:
            entity: The entity to attack
            kill: Whether to continue attacking until the entity dies (default True)
            pickup_item: Whether to pick up dropped items when the entity dies (default True)
        Returns:
            dict: Dictionary containing results
                - success (bool): True if attack successful, False otherwise
                - message (str): Result message
                - entity_name (str): Name of the attacked entity
                - killed (bool, optional): Whether the entity was killed
        """
        self.bot.chat(f"Attacking {entity.name}.")
        print(f"Attacking {entity.name}.")
        result = {
            "success": False,
            "message": "",
            "entity_name": entity.name if hasattr(entity, 'name') else "Unknown Entity"
        }
        
        # Check if entity exists
        if not entity or not hasattr(entity, 'position') or not entity.position:
            result["message"] = "Invalid target entity"
            result["error"] = "invalid_entity"
            self.bot.chat(result["message"])
            print(result)
            return result
        
        # Equip highest attack weapon
        wepon = await self._equip_highest_attack()
        if not wepon:
            result["message"] = "No weapon in inventory."
            result["error"] = "no_weapon"
            self.bot.chat(result["message"])
            print(result)
            return result
        
        # Save entity position
        position = entity.position
        
        if not kill:
            # Move closer if entity is too far
            try:
                if self.bot.entity.position.distanceTo(position) > 5:
                    await self.move_to_position(position.x, position.y, position.z)
            except Exception as e:
                result["message"] = f"Error occurred moving to entity: {str(e)}"
                result["error"] = "movement_error"
                self.bot.chat(result["message"])
                print(result)
                return result
                
            # Attack once
            try:
                self.bot.attack(entity)
                result["success"] = True
                result["message"] = f"Attacked {entity.name} once"
                result["killed"] = False
                self.bot.chat(result["message"])
                print(result)
                return result
            except Exception as e:
                result["message"] = f"Error occurred during attack: {str(e)}"
                result["error"] = "attack_error"
                self.bot.chat(result["message"])
                print(result)
                return result
        else:
            # Use PVP module
            self.bot.pvp.attack(entity)
            
            # Wait until entity dies
            while self._is_entity_nearby(entity, 24):
                await asyncio.sleep(1)
                if hasattr(self.bot, 'interrupt_code') and self.bot.interrupt_code:
                    self.bot.pvp.stop()
                    result["message"] = "Attack interrupted"
                    self.bot.chat(result["message"])
                    print(result)
                    return result
            self.bot.pvp.stop()
            
            result["success"] = True
            result["message"] = f"Killed {entity.name}"
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
        Defends self against surrounding hostile mobs.
        Continues attacking until hostile mobs are gone.
        If no weapon is equipped, will escape from enemies.
        Args:
            range: The distance to look for mobs. Default 9
            
        Returns:
            dict: Dictionary containing results
                - success (bool): True if successfully defended, False if no enemies
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
            self.bot.chat("No weapons in inventory. Escaping from enemy.")
            result["message"] = await self.avoid_enemies()
            result["error"] = "no_weapon"
            self.bot.chat(result["message"])
            print(result)
            return result
        while enemy:
            # Actions depending on distance to enemy
            enemy_distance = self.bot.entity.position.distanceTo(enemy.position)
            
            # Move closer if enemies other than creepers & phantoms are far
            if enemy_distance >= 4 and enemy.name != 'creeper' and enemy.name != 'phantom':
                try:
                    self.bot.pathfinder.setMovements(self.pathfinder.Movements(self.bot))
                    await self.bot.pathfinder.goto(self.pathfinder.goals.GoalFollow(enemy, 3.5), True)
                except Exception:
                    # Ignore errors like if entity is already dead
                    pass
                    
            # Move away if enemy is too close
            if enemy_distance <= 2:
                try:
                    self.bot.pathfinder.setMovements(self.pathfinder.Movements(self.bot))
                    inverted_goal = self.pathfinder.goals.GoalInvert(self.pathfinder.goals.GoalFollow(enemy, 2))
                    await self.bot.pathfinder.goto(inverted_goal, True)
                except Exception:
                    # Ignore errors like if entity is already dead
                    pass
            
            # Begin attacking
            has_pvp = hasattr(self.bot, 'pvp') and self.bot.pvp is not None
            
            self.bot.pvp.attack(enemy)
                
            attacked = True
            
            # Wait briefly
            await asyncio.sleep(0.5)
            
            # Find next enemy
            previous_enemy = enemy
            enemy = self._get_nearest_hostile_entity(range)
            
            # Count if previous enemy is gone
            if enemy != previous_enemy and not self._is_entity_nearby(previous_enemy, range):
                enemies_killed += 1
            
            if hasattr(self.bot, 'interrupt_code') and self.bot.interrupt_code:
                if has_pvp:
                    self.bot.pvp.stop()
                result["message"] = "Defense interrupted"
                self.bot.chat(result["message"])
                print(result)
                return result
        
        # Stop PVP attack
        if hasattr(self.bot, 'pvp') and self.bot.pvp is not None:
            self.bot.pvp.stop()
        
        if attacked:
            result["success"] = True
            result["message"] = f"Successfully defended self. Killed {enemies_killed} enemies."
            result["enemies_killed"] = enemies_killed
        else:
            result["message"] = "No hostile mobs nearby."
        
        self.bot.chat(result["message"])
        print(result)
        return result
        
    async def pickup_nearby_items(self, item_name=None,distance=10):
        """
        Picks up surrounding dropped items.
        Args:
            item_name (str, optional): Name of item to pick up. If None, picks up all surrounding dropped items.
            distance (int, optional): Range to search for dropped items. Default 8
        Returns:
            dict: Dictionary containing results
                - success (bool): True if picked up items
                - message (str): Result message
                - picked_up (int): Number of items picked up
        """
        result = {
            "success": False,
            "message": ""
        }
        
        # Function to get nearest items
        def get_nearest_item():
            nearest_item_list = []
            
            # Assume bot.entities is a dictionary or list of entities
            for entity_id in self.bot.entities:
                entity = self.bot.entities[entity_id]
                if hasattr(entity, 'name') and entity.name == 'item':
                    drop_item_name = self._get_item_name(self._get_item_id_from_entity(entity))
                    if not item_name is None and item_name != drop_item_name:
                        continue
                    # Calculate distance
                    dx = self.bot.entity.position.x - entity.position.x
                    dy = self.bot.entity.position.y - entity.position.y
                    dz = self.bot.entity.position.z - entity.position.z
                    current_distance = (dx*dx + dy*dy + dz*dz) ** 0.5
                    
                    if current_distance < distance:
                        nearest_item_list.append(entity)
            return nearest_item_list

        # Get the closest items
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
            # Wait slightly to allow for pickup
            await asyncio.sleep(0.2)
                
        result["success"] = True
        item_str = ", ".join(item_list)
        result["message"] = f"Picked up {item_str}."
        self.bot.chat(result["message"])
        print(result)
        return result
        
    async def _break_block_at(self, x, y, z):
        """
        Breaks the block at the specified coordinate. Tool is selected automatically.
        _break_block_at should not be used to mine specific blocks like diamonds where 'coordinates are unknown'. (Use the collect_block function)
        
        Args:
            x (float): X coordinate of block to break
            y (float): Y coordinate of block to break
            z (float): Z coordinate of block to break
            
        Returns:
            dict: Dictionary containing results
                - success (bool): True if break successful, False otherwise
                - message (str): Result message
                - position (dict): Attempted block position {x, y, z}
                - block_name (str, optional): Name of the broken block
                - error (str, optional): Error code if an error occurred
        
        Example:
            >>> await skills._break_block_at(100, -61, 100)
        """
        self.bot.chat(f"Breaking block at {x}, {y}, {z}.")
        print(f"Breaking block at {x}, {y}, {z}.")
        result = {
            "success": False,
            "message": "",
            "position": {"x": x, "y": y, "z": z}
        }
        
        # Coordinate verification
        if x is None or y is None or z is None:
            result["message"] = "Invalid block coordinates"
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
        
        # Skip if air, water, or lava
        if block.name in ['air', 'water', 'lava']:
            result["message"] = f"Coordinates ({x}, {y}, {z}) point to {block.name}, bypassing block break"
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
                
                # Check if holding appropriate tool
                item_id = None
                if self.bot.heldItem:
                    item_id = self.bot.heldItem.type
                            
                # Check if block can be harvested
                if hasattr(block, 'canHarvest') and not block.canHarvest(item_id):
                    result["message"] = f"No suitable tool to mine {block.name}"
                    result["error"] = "no_suitable_tool"
                    self.bot.chat(result["message"])
                    print(result)
                    return result
            except Exception as e:
                result["message"] = f"Error occurred equipping tool: {str(e)}"
                result["error"] = "tool_equip_error"
                self.bot.chat(result["message"])
                print(result)
                return result
                
        # Break block
        try:
            self.bot.dig(block, True)  # Set second argument to True to wait until mining completes
            result["message"] = f"Broke {block.name} at coordinates ({x:.1f}, {y:.1f}, {z:.1f})"
            result["success"] = True
            self.bot.chat(result["message"])
            print(result)
            return result
        except Exception as e:
            result["message"] = f"Error occurred breaking block: {str(e)}"
            result["error"] = "dig_error"
            self.bot.chat(result["message"])
            print(result)
            return result
        
    async def use_door(self, door_pos=None):
        """
        Uses the door or fence gate at the specified position. If position is not specified, uses the nearest door or fence gate.
        Note: Cannot use iron_door or iron_trapdoor which do not open upon interaction.
        
        Args:
            door_pos (Vec3, optional): Position of door to use. If None, uses nearest door.
            
        Returns:
            dict: Dictionary containing results
                - success (bool): True if successfully used door, False otherwise
                - message (str): Result message
                - door_position (dict, optional): Position of used door {x, y, z} (only on success)
        """
        self.bot.chat(f"Using door at {door_pos}.")
        print(f"Using door at {door_pos}.")
        result = {
            "success": False,
            "message": ""
        }
        
        try:
            Vec3 = require('vec3')
            
            # If door position not specified, find nearest door
            if not door_pos:
                door_types = [
                    'oak_door', 'spruce_door', 'birch_door', 'jungle_door', 
                    'acacia_door', 'dark_oak_door', 'mangrove_door', 
                    'crimson_door', 'warped_door',

                    'oak_fence_gate', 'spruce_fence_gate', 'birch_fence_gate', 'jungle_fence_gate',
                    'acacia_fence_gate', 'dark_oak_fence_gate', 'mangrove_fence_gate',
                    'crimson_fence_gate', 'warped_fence_gate'
                ]
                # Trapdoors not implemented as they require ladders
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
                
            # If no door found
            if not door_pos:
                result["message"] = "Could not find a usable door."
                self.bot.chat(result["message"])
                print(result)
                return result
                
            # Record door position in results
            result["door_position"] = {
                "x": door_pos.x,
                "y": door_pos.y,
                "z": door_pos.z
            }
            
            # Move towards door
            await self.move_to_position(door_pos.x, door_pos.y, door_pos.z, 1,canDig=False)
                    
            # Get door block
            door_block = self.bot.blockAt(door_pos)
            
            # Look at door
            self.bot.lookAt(door_pos)
            
            # Open door if it is closed
            if not door_block._properties.open:
                self.bot.activateBlock(door_block)
                
            # Move forward
            self.bot.setControlState("forward", True)
            await asyncio.sleep(0.6)
            self.bot.setControlState("forward", False)
            
            # Close door
            self.bot.activateBlock(door_block)
            
            result["success"] = True
            result["message"] = f"Passed through door at ({door_pos.x}, {door_pos.y}, {door_pos.z}) and moved to ({self.bot.entity.position.x:.1f}, {self.bot.entity.position.y:.1f}, {self.bot.entity.position.z:.1f})."
            self.bot.chat(result["message"])
            print(result)
            return result
            
        except Exception as e:
            result["message"] = f"Unexpected error occurred using door: {str(e)}"
            self.bot.chat(result["message"])
            print(result)
            import traceback
            traceback.print_exc()
            return result        
        
    async def till_and_sow(self, x, y, z, seed_type=None):
        """
        Tills ground at specified coordinates and plants specified seed.
        
        Args:
            x (float): X coordinate to till
            y (float): Y coordinate to till
            z (float): Z coordinate to till
            seed_type (str, optional): Type of seed to plant. If not specified, will only till but not plant seed.
            
        Returns:
            dict: Dictionary containing results
                - success (bool): True if tilling ground is successful, False otherwise
                - message (str): Result message
                - position (dict): Tilled position {x, y, z}
                - tilled (bool): Whether ground was tilled
                - planted (bool, optional): Whether seed was planted (if seed_type is specified)
                - seed_type (str, optional): Type of seed planted (if seed_type is specified)
        """
        self.bot.chat(f"Tilling ground at ({x}, {y}, {z}) and planting {seed_type}.")
        print(f"Tilling ground at ({x}, {y}, {z}) and planting {seed_type}.")
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
            
            # Get target block
            block = self.bot.blockAt(Vec3(x, y, z))
            
            # Check if target block can be tilled
            if block.name not in ['grass_block', 'dirt', 'farmland']:
                result["message"] = f"Cannot till {block.name}. Must be dirt or grass block."
                self.bot.chat(result["message"])
                print(result)
                return result
                
            # Check if block above exists
            above = self.bot.blockAt(Vec3(x, y+1, z))
            if above.name != 'air':
                result["message"] = f"Cannot till because {above.name} is on top of block."
                self.bot.chat(result["message"])
                print(result)
                return result
            
            # Find hoe and equip
            hoe = None
            for item in self.bot.inventory.items():
                if 'hoe' in item.name:
                    hoe = item
                    break
            if not hoe:
                result["message"] = "Cannot till because no hoe is held."
                self.bot.chat(result["message"])
                print(result)
                return result
            else:
                self.bot.equip(hoe, 'hand')
                    
            # Move closer if block is too far
            if self.bot.entity.position.distanceTo(block.position) > 4.5:
                pos = block.position
                move_result = await self.move_to_position(pos.x, pos.y, pos.z, 4)
                if not move_result["success"]:
                    result["message"] = move_result["message"]
                    self.bot.chat(result["message"])
                    print(result)
                    return result
            
            # Till if not already farmland
            if block.name != 'farmland':
                
                # Till the block
                self.bot.activateBlock(block)
                
                result["tilled"] = True
                self.bot.chat(f"BOT tilled ({x}, {y}, {z}).")
                print(result)
            else:
                result["tilled"] = True
                
            # Plant seed
            if seed_type:
                # If ends with 'seed' but not 'seeds', add 's'
                if seed_type.endswith('seed') and not seed_type.endswith('seeds'):
                    seed_type += 's'  # Fix common mistake
                    
                # Find seeds
                seeds = None
                for item in self.bot.inventory.items():
                    if item.name == seed_type:
                        seeds = item
                        break
                if not seeds:
                    result["message"] = f"Cannot plant because no {seed_type} is held." + \
                                       (f" Tilled ({x}, {y}, {z})." if result["tilled"] else "")
                    self.bot.chat(result["message"])
                    print(result)
                    
                    # Considered somewhat successful if tilled
                    if result["tilled"]:
                        result["success"] = True
                    return result
                
                # Equip seeds
                self.bot.equip(seeds, 'hand')
                
                # Plant the seeds (place on farmland)
                # Use Vec3(0, -1, 0) as we are placing it on the top surface of the block below
                self.bot.placeBlock(block, Vec3(0, -1, 0))
                
                result["planted"] = True
                result["seed_type"] = seed_type
                self.bot.chat(f"Planted {seed_type} at ({x}, {y}, {z}).")
                print(f"Planted {seed_type} at ({x}, {y}, {z}).")
            
            result["success"] = True
            
            if seed_type and result["planted"]:
                result["message"] = f"Tilled ({x}, {y}, {z}) and planted {seed_type}."
            else:
                result["message"] = f"Tilled ({x}, {y}, {z})."
            print(result)
            self.bot.chat(result["message"])
            return result
            
        except Exception as e:
            already_tilled = "tilled" in result and result["tilled"]
            result["message"] = f"Unexpected error occurred during tilling/planting: {str(e)}" + \
                               (f" Successfully tilled ({x}, {y}, {z})." if already_tilled else "")
            
            # Partially successful if just tilling worked
            if already_tilled:
                result["success"] = True
                
            self.bot.chat(result["message"])
            print(result)
            import traceback
            traceback.print_exc()
            return result

    def get_item_crafting_recipes(self, item_name):
        """
        Retrieves crafting recipes for an item
        
        Args:
            item_name (str): Item name
            
        Returns:
            list: List of recipes. Each recipe is in the format [ingredients dict, result dict]

        Example:
            >>> recipes = get_item_crafting_recipes("crafting_table")
            [[{'oak_planks': 4}, {'craftedCount': 1}], [{'spruce_planks': 4}, {'craftedCount': 1}]...]
        """
        self.bot.chat(f"Retrieving recipes for {item_name}.")
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
        Collects water or lava within range with a bucket. Requires a bucket in inventory.

        Args:
            liquid_type (str): Type of liquid to collect. Either 'water' or 'lava'. Default 'water'.
            max_distance (int): Maximum search distance. Default 16.
            
        Returns:
            dict: Dictionary containing results
                - success (bool): True if liquid collection successful, False otherwise
                - message (str): Result message
                - position (dict, optional): Position of collected liquid {x, y, z}
                - liquid_type (str): Type of liquid collected
        """
        result = {
            "success": False,
            "message": "",
            "liquid_type": liquid_type
        }
        
        try:
            # Check liquid type
            if liquid_type not in ['water', 'lava']:
                result["message"] = f"Invalid liquid type: {liquid_type}. Specify 'water' or 'lava'."
                self.bot.chat(result["message"])
                print(result)
                return result
            
            # Find bucket
            bucket = None
            bucket_count = 0
            for item in self.bot.inventory.items():
                if item.name == 'bucket':
                    bucket = item
                elif item.name == f'{liquid_type}_bucket':
                    bucket_count += 1
            bucket_count += 1
            
            if not bucket:
                result["message"] = "Cannot collect liquid because no empty bucket is held."
                self.bot.chat(result["message"])
                print(result)
                return result
            
            # Find specified liquid block
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
                result["message"] = f"{liquid_type} not found within range."
                self.bot.chat(result["message"])
                print(result)
                return result
            
            # Move closer if block is too far
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

            # bot looks at liquid block
            self.bot.lookAt(liquid_block.position)
            
            # Use bucket to collect liquid
            self.bot.activateBlock(liquid_block)
            self.bot.activateItem()
            
            # Wait slightly for operation to finish
            await asyncio.sleep(1)

            # Deactivate bucket
            self.bot.deactivateItem()

            # Set results
            result["success"] = True
            result["position"] = {
                "x": liquid_block.position.x,
                "y": liquid_block.position.y,
                "z": liquid_block.position.z
            }
            
            # Verify if correct liquid was collected (check inventory)
            has_filled_bucket = False
            
            for item in self.bot.inventory.items():
                
                if item.name == f"{liquid_type}_bucket":
                    bucket_count -= 1
                    if bucket_count == 0:
                        has_filled_bucket = True
                        break
            
            if has_filled_bucket:
                result["message"] = f"Collected {liquid_type} at ({liquid_block.position.x}, {liquid_block.position.y}, {liquid_block.position.z}) with {bucket.name}."
            else:
                result["success"] = False
                result["message"] = f"Failed to collect {liquid_type}."
            
            self.bot.chat(result["message"])
            print(result)
            return result
            
        except Exception as e:
            result["message"] = f"Unexpected error occurred collecting liquid: {str(e)}"
            self.bot.chat(result["message"])
            print(result)
            import traceback
            traceback.print_exc()
            return result

    async def place_liquid(self, x, y, z, liquid_type='water'):
        """
        Places liquid (water or lava) from bucket at specified coordinates. Requires water_bucket or lava_bucket in inventory.
        
        Args:
            x (float): X coordinate to place liquid
            y (float): Y coordinate to place liquid
            z (float): Z coordinate to place liquid
            liquid_type (str): Type of liquid to place. Either 'water' or 'lava'. Default 'water'.
            
        Returns:
            dict: Dictionary containing results
                - success (bool): True if liquid placement successful, False otherwise
                - message (str): Result message
                - position (dict): Placed position {x, y, z}
                - liquid_type (str): Type of liquid placed
        """
        self.bot.chat(f"Placing {liquid_type} at ({x}, {y}, {z}).")
        print(f"Placing {liquid_type} at ({x}, {y}, {z}).")
        result = {
            "success": False,
            "message": "",
            "position": {"x": x, "y": y, "z": z},
            "liquid_type": liquid_type
        }
        
        try:
            # Check liquid type
            if liquid_type not in ['water', 'lava']:
                result["message"] = f"Invalid liquid type: {liquid_type}. Specify 'water' or 'lava'."
                self.bot.chat(result["message"])
                print(result)
                return result
            
            # Round coordinates to integers
            x = round(x)
            y = round(y)
            z = round(z)
            result["position"] = {"x": x, "y": y, "z": z}
            
            # Find filled bucket
            filled_bucket = None
            
            for item in self.bot.inventory.items():
                if item.name == f"{liquid_type}_bucket":
                    filled_bucket = item
            
            if not filled_bucket:
                result["message"] = f"Cannot place liquid because no {liquid_type}_bucket is held."
                self.bot.chat(result["message"])
                print(result)
                return result
            
            # Get target block
            Vec3 = require('vec3')
            target_position = Vec3(x, y, z)
            target_block = self.bot.blockAt(target_position)
            
            # Check if target is air or another placeable block
            if target_block.name != 'air' and target_block.name != 'cave_air':
                result["message"] = f"Cannot place liquid because {target_block.name} is already at ({x}, {y}, {z})."
                self.bot.chat(result["message"])
                print(result)
                return result
            
            # Move closer if block is too far
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
            
            # Wait slightly for operation to finish
            await asyncio.sleep(1)
            
            # Deactivate bucket
            self.bot.deactivateItem()
            
            # Verify placed block
            new_block = self.bot.blockAt(target_position)
            is_correct_liquid = new_block and new_block.name == liquid_type
            
            if is_correct_liquid:
                result["success"] = True
                result["message"] = f"Placed {liquid_type} from {filled_bucket.name} at ({x}, {y}, {z})."
            else:
                result["success"] = False
                result["message"] = f"Failed to place {liquid_type} at ({x}, {y}, {z})."
            
            self.bot.chat(result["message"])
            print(result)
            return result
            
        except Exception as e:
            result["message"] = f"Unexpected error occurred placing liquid: {str(e)}"
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
            print(f"Error creating item: {e}")
            
        # Return a basic object
        return {
            'name': item_name,
            'count': count
        }
    
            
    async def _equip_highest_attack(self):
        """
        Equips the weapon with the highest attack power.
        
        Returns:
            bool: True if equipped weapon, False if no suitable weapon
        """
        # Find swords and axes (excluding pickaxes)
        weapons = []
        for item in self.bot.inventory.items():
            if 'sword' in item.name or ('axe' in item.name and 'pickaxe' not in item.name):
                weapons.append(item)
                
        # If no weapons, find pickaxes or shovels
        if not weapons:
            for item in self.bot.inventory.items():
                if 'pickaxe' in item.name or 'shovel' in item.name:
                    weapons.append(item)
                    
        # Return if no weapons
        if not weapons:
            return False
            
        # Sort by attack damage
        try:
            # If attackDamage property is available
            weapons.sort(key=lambda item: getattr(item, 'attackDamage', 0), reverse=True)
        except:
            # If attackDamage info not available, sort by material and type
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
            
        # Equip best weapon
        best_weapon = weapons[0]
        self.bot.equip(best_weapon, 'hand')
        return True
        
    def _get_nearby_entity_of_type(self, entity_type, max_distance=24):
        """
        Gets the nearest entity of the specified type.
        
        Args:
            entity_type (str): Type of entity
            max_distance (int): Maximum search distance
            
        Returns:
            Entity: Nearest entity, None if not found
        """
        try:
            entities = self._get_nearby_entities(max_distance)
            for entity in entities:
                if hasattr(entity, 'name') and entity.name == entity_type:
                    return entity
        except Exception as e:
            print(f"Error searching entity: {e}")
            
        return None
        
    def _get_nearest_hostile_entity(self, max_distance=24):
        """
        Gets the nearest hostile entity within specified distance.
        
        Args:
            max_distance (int): Maximum search distance. Default 24
            
        Returns:
            Entity or None: Nearest hostile entity. None if not found
        """
        def calculate_distance(pos1, pos2):
            """Calculates Euclidean distance between 2 points"""
            return ((pos1.x - pos2.x) ** 2 + 
                   (pos1.y - pos2.y) ** 2 + 
                   (pos1.z - pos2.z) ** 2) ** 0.5

        # Filter hostile entities
        hostile_entities = [
            entity for entity in self._get_nearby_entities(max_distance)
            if self._is_hostile(entity)
        ]
        
        if not hostile_entities:
            return None
            
        # Sort by distance
        hostile_entities.sort(
            key=lambda e: calculate_distance(self.bot.entity.position, e.position)
        )
        
        return hostile_entities[0] if hostile_entities else None
        
    def _get_nearby_entities(self, max_distance=24):
        """
        Gets all entities within specified distance, sorted by distance.
        
        Args:
            max_distance (int): Maximum search distance. Default 24
            
        Returns:
            list: List of nearby entities sorted by distance
        """
        if not self.bot or not self.bot.entity or not hasattr(self.bot.entity, 'position'):
            return []
            
        def calculate_distance(pos1, pos2):
            """Calculates Euclidean distance between 2 points"""
            return ((pos1.x - pos2.x) ** 2 + 
                   (pos1.y - pos2.y) ** 2 + 
                   (pos1.z - pos2.z) ** 2) ** 0.5
            
        nearby_entities = []
        # Iterate over entities which are implemented as a Javascript object
        for entity_id in self.bot.entities:
            entity = self.bot.entities[entity_id]
            if not entity or not hasattr(entity, 'id'):  # Skip if entity is None
                continue
                
            if entity.id == self.bot.entity.id:  # Exclude self
                continue
                
            if hasattr(entity, 'position') and entity.position:
                distance = calculate_distance(self.bot.entity.position, entity.position)
                if distance <= max_distance:
                    nearby_entities.append(entity)
                
        # Sort by distance
        nearby_entities.sort(
            key=lambda e: calculate_distance(self.bot.entity.position, e.position)
        )
        
        return nearby_entities
        
    def _is_entity_nearby(self, entity, max_distance=24):
        """
        Checks if a specific entity is nearby.
        
        Args:
            entity: Entity to check
            max_distance (int): Maximum search distance
            
        Returns:
            bool: True if entity is nearby
        """
        # Check if entity is valid
        if not entity or not hasattr(entity, 'id'):
            return False
            
        entities = self._get_nearby_entities(max_distance)
        for e in entities:
            if hasattr(e, 'id') and e.id == entity.id:
                return True
        return False
    
    def _is_hostile(self, entity):
        """
        Determines if an entity is hostile.
        
        Args:
            entity: Entity to evaluate
            
        Returns:
            bool: True if hostile
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
        Determines if an item is smeltable.
        
        Args:
            item_name (str): Item name to evaluate
            
        Returns:
            bool: True if smeltable
        """
        # List of smeltable items
        smeltable_items = [
            # Ores
            'raw_iron', 'raw_gold', 'raw_copper', 
            'iron_ore', 'gold_ore', 'copper_ore',
            'ancient_debris', 'netherite_scrap',
            # Food
            'beef', 'chicken', 'cod', 'salmon', 'porkchop', 'potato', 'rabbit', 'mutton',
            # Other
            'sand', 'cobblestone', 'clay', 'clay_ball', 'cactus'
        ]
        
        # Assume items starting with 'raw_' are smeltable
        if item_name.startswith('raw_'):
            return True
            
        return item_name in smeltable_items
        
    def _get_smelting_fuel(self):
        """
        Searches inventory for fuel to use in smelting.
        
        Returns:
            Object: Fuel item object, None if not found
        """
        # Search for items usable as fuel in order of priority
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
        Gets item name corresponding to item ID.
        
        Args:
            item_id (int): Item ID
            
        Returns:
            str: Item name. None if ID not found
        """
        item = self.mcdata.items[item_id]
        
        if item:
            return item.name
        return None
        
    def _get_item_id(self, item_name):
        """
        Gets item ID from item name.
        
        Args:
            item_name (str): Item name
            
        Returns:
            int: Item ID
        """
        try:
            if hasattr(self.mcdata, 'itemsByName') and item_name in self.mcdata.itemsByName:
                return self.mcdata.itemsByName[item_name].id
            elif hasattr(self.bot.registry, 'itemsByName') and item_name in self.bot.registry.itemsByName:
                return self.bot.registry.itemsByName[item_name].id
        except:
            pass
            
        # Return None if item not found
        return None
    
    def _get_item_id_from_entity(self, entity):
        """
        Gets item ID from an entity.
        
        Args:
            entity: Entity object
            
        Returns:
            int: Item ID
        """
        # itemId is in the 8th element (index 7) of metadata
        if entity and hasattr(entity, 'metadata'):
            metadata_item = entity.metadata[8]
            return metadata_item.itemId
        
        # Return None if cannot be retrieved
        return None

    async def handle_connection_error(self, timeout=30):
        """
        Attempts to reconnect the bot if there's an API communication issue.
        Used when the API doesn't respond or times out.

        Args:
            timeout (int): Reconnect attempt timeout (seconds). Default 30s.

        Returns:
            dict: Reconnection results
                - success (bool): True if reconnection was successful
                - message (str): Result message
        """
        self.bot.chat("Attempting to reconnect to server due to communication error...")
        result = {
            "success": False,
            "message": ""
        }
        try:
            # Call reconnect_bot method of discovery instance
            # reconnect_bot should be changed to return a bool
            reconnect_success = await self.discovery.reconnect_bot(timeout=timeout)

            if reconnect_success:
                result["success"] = True
                result["message"] = "Successfully reconnected to server."
                self.bot.chat(result["message"])
                # After reconnecting, might need to update references inside Skills class
                self.bot = self.discovery.bot
                self.mcdata = self.discovery.mcdata
                self.pathfinder = self.discovery.pathfinder
                self.movements = self.discovery.movements
                self.mineflayer = self.discovery.mineflayer
                print("Updated references in Skills class.")
            else:
                result["message"] = f"Failed to reconnect to server (timeout: {timeout} seconds). Please check server status."
                # Avoid chat since bot instance might be None
                print(result["message"])

        except Exception as e:
            result["message"] = f"Unexpected error occurred during reconnection: {str(e)}"
            print(f"Reconnection error: {result['message']}")
            import traceback
            traceback.print_exc()

        return result

    async def create_nether_portal(self, check_space_only=False):
        """
        Places a Nether portal using obsidian and activates it with flint and steel.
        Places it with a minimum layout (10 obsidian blocks, no corners).

        Args:
            check_space_only (bool): If True, only checks if there is space to place it, without actually placing it.

        Returns:
            dict: Dictionary containing results
                - success (bool): True if portal placement and activation successful
                - message (str): Result message
                - portal_base_pos (dict, optional): Base coordinates of the placed portal {x, y, z}
                - error (str, optional): Error code (insufficient_materials, no_space, placement_failed, activation_failed, verification_failed)
        """
        self.bot.chat("Starting to create Nether portal.")
        result = {
            "success": False,
            "message": "",
        }
        Vec3 = require('vec3')

        # --- 1. Check materials ---
        inventory = await self.get_inventory_counts()
        obsidian_count = inventory.get('obsidian', 0)
        flint_and_steel_count = inventory.get('flint_and_steel', 0)

        if obsidian_count < 10:
            result["message"] = f"Not enough obsidian to create Nether portal (Need: 10, Have: {obsidian_count})"
            result["error"] = "insufficient_materials"
            self.bot.chat(result["message"])
            print(result)
            return result
        if flint_and_steel_count < 1 and not check_space_only:
            result["message"] = "Missing flint and steel needed to activate the Nether portal"
            result["error"] = "insufficient_materials"
            self.bot.chat(result["message"])
            print(result)
            return result

        # --- 2. Space search (height 5, width 4, depth 1) ---
        portal_width = 4
        portal_height = 5
        search_distance = 15
        base_pos = None
        orientation = 'z' # 'x' or 'z'

        base_pos = await self.get_nearest_free_space(portal_width, portal_height,1, search_distance)

        if not base_pos:
            result["message"] = f"Could not find enough space (Height: {portal_height}, Width: {portal_width}) to place the Nether portal."
            result["error"] = "no_space"
            self.bot.chat(result["message"])
            print(result)
            return result

        result["portal_base_pos"] = {"x": base_pos.x, "y": base_pos.y, "z": base_pos.z}

        if check_space_only:
            result["success"] = True
            result["message"] = f"Found space to place Nether portal. Coordinates: ({base_pos.x}, {base_pos.y}, {base_pos.z}), Orientation: {orientation}-axis"
            self.bot.chat(result["message"])
            print(result)
            return result

        # Move to space
        move_result = await self.move_to_position(base_pos.x, base_pos.y, base_pos.z, 2)
        if not move_result["success"]:
            result["message"] = f"Failed to move to Nether portal space: {move_result.get('message', 'Unknown')}"
            result["error"] = "movement_failed"
            self.bot.chat(result["message"])
            print(result)
            return result

        # --- 3. Place Nether portal frame (10 obsidian blocks) ---
        portal_frame_coords = []
        # Bottom side (y=0)
        portal_frame_coords.append(base_pos.offset(0, 0, 0))
        portal_frame_coords.append(base_pos.offset(1, 0, 0))
        portal_frame_coords.append(base_pos.offset(2, 0, 0))
        portal_frame_coords.append(base_pos.offset(3, 0, 0))
        # Pillars (x=0)
        portal_frame_coords.append(base_pos.offset(0, 1, 0))
        portal_frame_coords.append(base_pos.offset(0, 2, 0))
        portal_frame_coords.append(base_pos.offset(0, 3, 0))
        portal_frame_coords.append(base_pos.offset(3, 1, 0))
        portal_frame_coords.append(base_pos.offset(3, 2, 0))
        portal_frame_coords.append(base_pos.offset(3, 3, 0))
        # Top side (y=4)
        portal_frame_coords.append(base_pos.offset(0, 4, 0))
        portal_frame_coords.append(base_pos.offset(1, 4, 0))
        portal_frame_coords.append(base_pos.offset(2, 4, 0))
        portal_frame_coords.append(base_pos.offset(3, 4, 0))

        self.bot.chat("Beginning placement of Nether portal frame...")
        placed_count = 0
        for coord in portal_frame_coords:
            place_result = await self.place_block('obsidian', coord.x, coord.y, coord.z)
            if place_result["success"]:
                placed_count += 1
                await asyncio.sleep(0.1) # Brief pause between placements
            else:
                # Placement failure handling (might allow if block is already present)
                block_at_coord = self.bot.blockAt(coord)
                if block_at_coord and block_at_coord.name == 'obsidian':
                    self.bot.chat(f"Already an obsidian at ({coord.x}, {coord.y}, {coord.z}). Skipping.")
                    placed_count += 1 # Count if already present
                    continue
                else:
                    result["message"] = f"Error occurred during Nether portal frame placement ({coord.x}, {coord.y}, {coord.z}). Reason: {place_result.get('message', 'Unknown')}"
                    result["error"] = "placement_failed"
                    self.bot.chat(result["message"])
                    print(result)
                    # TODO: Consider adding logic to dismantle placed blocks
                    return result

        if placed_count < 10:
             # Should be covered by above error handling, but here as a failsafe
             result["message"] = "Failed to place Nether portal frame. Could not place the required amount of obsidian."
             result["error"] = "placement_failed"
             self.bot.chat(result["message"])
             print(result)
             return result

        self.bot.chat("Nether portal frame placement complete.")

        # --- 4. Activate Nether portal ---
        self.bot.chat("Attempting to activate Nether portal...")

        # Equip flint and steel
        equip_result = await self.equip('flint_and_steel')
        if not equip_result["success"]:
             result["message"] = "Failed to equip flint and steel."
             result["error"] = "activation_failed"
             self.bot.chat(result["message"])
             print(result)
             return result

        # Activation target block (inner obsidian at bottom of frame)
        activation_target_coord = None
        portal_check_coord = None # Validation coordinates for portal generation
        if orientation == 'z':
            activation_target_coord = base_pos.offset(1, 0, 0) # Left side of base
            portal_check_coord = base_pos.offset(1, 1, 0) # Inside bottom-left of portal
        elif orientation == 'x':
            activation_target_coord = base_pos.offset(0, 0, 1) # Front side of base
            portal_check_coord = base_pos.offset(0, 1, 1) # Inside bottom-front of portal

        activation_target_block = self.bot.blockAt(activation_target_coord)
        if not activation_target_block or activation_target_block.name != 'obsidian':
            result["message"] = f"Could not find target block (obsidian) for portal activation at ({activation_target_coord.x}, {activation_target_coord.y}, {activation_target_coord.z})"
            result["error"] = "activation_failed"
            self.bot.chat(result["message"])
            print(result)
            return result

        # Move to target block (if necessary)
        if self.bot.entity.position.distanceTo(activation_target_coord) > 4.5:
             move_result = await self.move_to_position(activation_target_coord.x, activation_target_coord.y, activation_target_coord.z, 3)
             if not move_result["success"]:
                 result["message"] = f"Failed to move to portal activation position: {move_result.get('message', 'Unknown')}"
                 result["error"] = "activation_failed"
                 self.bot.chat(result["message"])
                 print(result)
                 return result

        # Look at target block
        self.bot.lookAt(activation_target_coord.offset(0.5, 0.5, 0.5), True) # Look at center of block

        # Use flint and steel (might be activateItem rather than activateBlock)
        # Mineflayer's activateBlock interacts directly with the block. Flint and steel is used against blocks
        try:
            # Specify which face to use (assuming top side Vec3(0, 1, 0))
            # activateBlock arg 2 is referenceBlock, arg 3 is faceVector
            # faceVector dictates which face of the target block is clicked
            # Click top face of the bottom obsidian block to generate portal
            self.bot.activateBlock(activation_target_block, Vec3(0, 1, 0))
            self.bot.chat(f"Used flint and steel on obsidian at ({activation_target_block.position.x}, {activation_target_block.position.y}, {activation_target_block.position.z}).")
            await asyncio.sleep(1.0) # Wait for portal generation
        except Exception as e:
            result["message"] = f"Error occurred while using flint and steel: {str(e)}"
            result["error"] = "activation_failed"
            self.bot.chat(result["message"])
            print(result)
            import traceback
            traceback.print_exc()
            return result

        # --- 5. Verify activation ---
        portal_block = self.bot.blockAt(portal_check_coord)
        if portal_block and portal_block.name == 'nether_portal':
            result["success"] = True
            result["message"] = f"Nether portal successfully created and activated at ({base_pos.x}, {base_pos.y}, {base_pos.z})."
            self.bot.chat(result["message"])
            print(result)
        else:
            result["message"] = f"Failed to activate Nether portal. Portal block was not generated. Check coordinates: ({portal_check_coord.x}, {portal_check_coord.y}, {portal_check_coord.z}), Actual block: {portal_block.name if portal_block else 'None'}"
            result["error"] = "verification_failed"
            self.bot.chat(result["message"])
            print(result)
        return result