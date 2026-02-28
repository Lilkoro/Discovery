# Discovery: Customizable Minecraft Agent with AutoGen

<div align="center">

[English](README.md) | [Japanese](README-jp.md)

![MinecraftAI](https://github.com/Mega-Gorilla/Discovery/blob/main/images/MinecraftAI.png?raw=true)


# Demo

[![Discovery Demo](https://img.youtube.com/vi/vxqvB3isKn4/0.jpg)](https://youtube.com/live/vxqvB3isKn4?feature=share)

</div>

## About Discovery

Discovery is a Minecraft automation agent that combines Bot control through [Mineflayer](https://github.com/PrismarineJS/mineflayer) with advanced task execution and customizability through the [AutoGen](https://github.com/microsoft/autogen) framework. Multiple AI agents (planner, code executor, debugger, etc.) work together to autonomously act within Minecraft to achieve user-defined goals.

### Key Features

- **AutoGen Integration**: Multiple AI agents collaborate to plan, execute, and debug tasks.
- **Mineflayer Based**: Uses the proven Mineflayer library to control the Minecraft Bot.
- **Agent Customization**: Adjust behavior and roles by modifying agent prompts (in `discovery/autoggen.py`).
- **Model Flexibility**: Utilize various LLM models supported by AutoGen (OpenAI, Google Gemini, etc.) configurable in the settings file.
- **Docker Ready**: Easily set up and run in a containerized environment.
- **Skill Expandability**: Extend Bot capabilities by adding Python functions to `discovery/skill/skills.py`.

## Docker Installation

Discovery runs in Docker, providing a platform-independent setup.

### Prerequisites

- [Docker](https://www.docker.com/products/docker-desktop/) and Docker Compose
- Minecraft Java Edition (version 1.19.0 recommended)
- OpenAI API key or credentials for other supported LLM providers

### Setup Instructions

1. **Clone the repository**
   ```bash
   git clone https://github.com/Mega-Gorilla/Discovery.git
   cd Discovery
   ```

2. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   
   Edit the `.env` file with your API keys and Minecraft connection information:
   ```dotenv
   # LLM API Keys
   OPENAI_API_KEY=your_openai_api_key_here
   GOOGLE_API_KEY=your_google_api_key_here # if needed

   # Minecraft connection information (if running Minecraft on host machine)
   MINECRAFT_PORT=25565 # Port used by Minecraft client when open to LAN (change this later)
   MINECRAFT_HOST=host.docker.internal # Connect to Minecraft on host machine from Docker
   MINECRAFT_VERSION=1.19.0 # Minecraft version

   # Bot Viewer & Web Inventory Ports (can be changed)
   PRISMARINE_VIEWER_PORT=3000
   WEB_INVENTORY_PORT=3001
   ```
   **Note:** `MINECRAFT_PORT` will need to be **edited again later** to match the port number displayed when opening Minecraft to LAN.

3. **Install Minecraft Mods (optional but recommended)**

   While not required, installing these mods will make the Bot's operation more stable and easier to debug.
   Please refer to the following guide for installation instructions:
   [fabric_mods_install.md](docs/fabric_mods_install.md)

4. **Build and start the Docker container**
   ```bash
   docker-compose up -d --build
   ```
   
   This will build the Docker image with all necessary dependencies and start the container in the background.

5. **Start Minecraft and open to LAN**
   - Launch the Minecraft client on your host machine with the Fabric profile (if using mods) or vanilla.
   - Create a new world in Creative mode with Peaceful difficulty (or load an existing one).
   - Press Esc, select "Open to LAN".
   - Enable cheats and click "Start LAN World".
   - **Important**: Note the **port number** displayed in the chat (e.g., `Local game hosted on port 51234`).

6. **Update port number in `.env` file**
   - Set the noted port number as the value for `MINECRAFT_PORT` in your `.env` file.
   - **Restart the Docker container:**
     ```bash
     docker-compose restart discovery # where 'discovery' is the service name defined in docker-compose.yml
     ```

## Customizing Agents

You can customize the behavior of AutoGen agents primarily by modifying their system messages (prompts).

1. **Edit prompts**:
   - Open the `discovery/autoggen.py` file.
   - Find the `load_agents` method containing definitions for each agent (`MineCraftPlannerAgent`, `CodeExecutionAgent`, `CodeDebuggerAgent`, etc.)
   - Edit the content of the `system_message` parameter for each agent to modify its role, instructions, constraints, etc.

2. **Add skills**:
   - To add new capabilities to the Bot, implement new Python methods (functions) in `discovery/skill/skills.py`.
   - Update prompts or tool definitions in `autoggen.py` for `CodeExecutionAgent` or `CodeDebuggerAgent` as needed to recognize your new skills.

3. **Rebuild the container**:
   - After changing Python code (`.py` files), rebuild the Docker container to reflect the changes:
     ```bash
     docker-compose up -d --build
     ```

## Running Discovery

Once setup and customization are complete, you can run Discovery.

1. **Access the terminal inside the container**:
   ```bash
   docker-compose exec discovery /bin/bash
   # or docker exec -it <container_id_or_name> /bin/bash
   ```

2. **Run the AutoGen script**:
   Inside the container, run:
   ```bash
   python -m discovery.main # or python discovery/main.py
   ```

   This will start the AutoGen framework and initiate collaboration between agents:
   - First, a connection to the Minecraft server will be established.
   - Then, agents will begin a cycle of planning, code generation, execution, and debugging based on user-defined goals (currently defined in the `main` function of `autoggen.py`; may become interactively configurable in the future).
   - The console will display messages from each agent and the results of code execution.

3. **Visual verification of the Bot (optional)**:
   Prismarine Viewer will start on the port configured in your `.env` file (default: 3000). Access `http://localhost:3000` (or the IP of the machine running Docker) in your browser to see the Bot's perspective.

## Important Notes

- The Minecraft client must run on your host machine and be open to LAN.
- Always start Minecraft, open to LAN, and update `MINECRAFT_PORT` in `.env` before running Discovery.
- If connection issues occur, check:
  - Your firewall settings
  - That `MINECRAFT_PORT` in `.env` matches the LAN port Minecraft is using
  - Docker network settings (whether `host.docker.internal` points to your host machine)
- If using mods, ensure versions are compatible with your Minecraft client and Fabric Loader.
- After changing AutoGen agent prompts, test to ensure they behave as expected.

## License

This project is available under [Research and Development License - Non-Commercial Use Only](LICENSE).

**Disclaimer**: This project is strictly for research purposes and not an official product.
