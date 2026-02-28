# Discovery: Customizable Minecraft Agents with AutoGen
<div align="center">

[English](README.md) | [日本語](README-jp.md)

![MinecraftAI](https://github.com/Mega-Gorilla/Discovery/blob/main/images/MinecraftAI.png?raw=true)

# Demo

[![Discovery Demo](https://img.youtube.com/vi/vxqvB3isKn4/0.jpg)](https://youtube.com/live/vxqvB3isKn4?feature=share)

</div>

## About Discovery

Discovery is an autonomous Minecraft agent that combines Bot operation powered by [Mineflayer](https://github.com/PrismarineJS/mineflayer) with advanced task execution and customization provided by the [AutoGen](https://github.com/microsoft/autogen) framework. Multiple AI agents (planner, code execution, debugger, etc.) collaborate to autonomously act within Minecraft to achieve user-defined goals.

### Key Features

- **AutoGen Integration**: Multiple AI agents collaborate to plan, execute, and debug tasks.
- **Mineflayer Based**: Operates Minecraft Bots using the proven Mineflayer library.
- **Agent Customization**: Adjust agent behavior and roles by modifying each agent's prompt (located in `discovery/autoggen.py`).
- **Model Flexibility**: Supports various LLM models compatible with AutoGen, such as OpenAI and Google Gemini (configurable in settings).
- **Docker Support**: Easy setup and execution in a containerized environment.
- **Skill Extensibility**: Extend Bot capabilities by adding new Python functions to `discovery/skill/skills.py`.

## Installation with Docker

Discovery runs on Docker, providing a platform-independent setup.

### Prerequisites

- [Docker](https://www.docker.com/products/docker-desktop/) and Docker Compose
- Minecraft Java Edition (version 1.19.0 recommended)
- OpenAI API key or an API key from another supported LLM provider

### Setup Steps

1.  **Clone the repository**
    ```bash
    git clone https://github.com/Mega-Gorilla/Discovery.git
    cd Discovery
    ```

2.  **Configure environment variables**
    ```bash
    cp .env.example .env
    ```

    Edit the `.env` file and enter your API keys and Minecraft connection information.
    ```dotenv
    # LLM API Keys
    OPENAI_API_KEY=your_openai_api_key_here
    GOOGLE_API_KEY=your_google_api_key_here # if needed

    # Minecraft connection info (if running Minecraft on the host machine)
    MINECRAFT_PORT=25565 # Port used by Minecraft client when opened to LAN (will change later)
    MINECRAFT_HOST=host.docker.internal # To connect to Minecraft on the host machine from Docker
    MINECRAFT_VERSION=1.19 # Minecraft version

    # Bot Viewer & Web Inventory Ports (can be changed)
    PRISMARINE_VIEWER_PORT=3000
    WEB_INVENTORY_PORT=3001
    ```
    **Note:** `MINECRAFT_PORT` will need to be **edited again** to match the port number displayed when Minecraft is opened to LAN, as described later.

3.  **Install Minecraft Mods (optional but recommended)**

    Although not strictly necessary, installing the following mods will stabilize the Bot's operation and facilitate debugging.
    Refer to the following for installation instructions:
    [fabric_mods_install.ja.md](https://github.com/Mega-Gorilla/Discovery/blob/main/docs/fabric_mods_install.ja.md)

4.  **Build and start Docker containers**
    ```bash
    docker-compose up -d --build
    ```
    This will build the Docker images with the necessary dependencies and start the containers in the background.

5.  **Start Minecraft and open to LAN**
    - Start the Minecraft client on your host machine using a Fabric profile (if using mods) or vanilla.
    - Create a new world (or load an existing one) in Creative mode with Peaceful difficulty.
    - Press the Esc key and select "Open to LAN".
    - Enable Cheats and click "Start LAN World".
    - **Important:** Note the **port number** displayed in the chat (e.g., `Local game hosted on port 51234`).

6.  **Update port number in `.env` file**
    - Set the noted port number as the value for `MINECRAFT_PORT` in your `.env` file.
    - **A Docker container restart is required:**
      ```bash
      docker-compose restart discovery # 'discovery' is the service name defined in docker-compose.yml
      ```

## Customizing Agents

The behavior of AutoGen agents can be customized primarily by modifying their system messages (prompts).

1.  **Edit Prompts**:
    - Open the `discovery/autoggen.py` file.
    - Definitions for each agent (`MineCraftPlannerAgent`, `CodeExecutionAgent`, `CodeDebuggerAgent`, etc.) are located within the `load_agents` method.
    - By editing the content of each agent's `system_message` parameter, you can change its role, instructions, constraints, and more.

2.  **Add Skills**:
    - If you want to add new capabilities to the Bot, implement new Python methods (functions) in `discovery/skill/skills.py`.
    - Update prompts and tool definitions as necessary so that `CodeExecutionAgent` and `CodeDebuggerAgent` in `autoggen.py` recognize the new skills.

3.  **Rebuild Containers**:
    - If you modify Python code (`.py` files), you need to rebuild the Docker containers for the changes to take effect.
      ```bash
      docker-compose up -d --build
      ```

## Running Discovery

Once setup and customization are complete, you can run Discovery.

1.  **Enter the container in the terminal**:
    ```bash
    docker-compose exec discovery /bin/bash
    # Or docker exec -it <container_id_or_name> /bin/bash
    ```

2.  **Execute the AutoGen script**:
    Run the following command inside the container.
    ```bash
    python -m discovery.main # Or python discovery/main.py
    ```

    This will start the AutoGen framework, and each agent will begin tasks in cooperation.
    - First, a connection to the Minecraft server will be established.
    - Afterwards, based on the user-defined goals (currently likely defined within the `main` function of `autoggen.py`; interactive setup might be available in the future), the agents will begin the cycle of planning, code generation, execution, and debugging.
    - The console will display the utterances of each agent and the results of code execution.

3.  **Visual confirmation of the Bot (optional)**:
    The Prismarine Viewer will start on the port configured in the `.env` file (default: 3000). You can view the Bot's perspective by accessing `http://localhost:3000` (or the IP address of the machine running Docker) in your browser.

## Important Notes

- The Minecraft client must be run on the host machine and opened to LAN.
- Always start Minecraft, open it to LAN, update `MINECRAFT_PORT` in `.env`, and then run Discovery.
- If connection issues occur, check the following:
  - Firewall settings
  - That the `MINECRAFT_PORT` in the `.env` file matches Minecraft's LAN port
  - Docker network settings (whether `host.docker.internal` points to the host machine)
- If using mods, ensure that their versions are compatible with Minecraft itself and Fabric Loader.
- If you change the prompts of AutoGen agents, testing is required to ensure they behave as expected.

## License

This project is provided under the [Research and Development License - Non-Commercial Use Only](LICENSE).

**Disclaimer**: This project is for research purposes only and is not an official product.
