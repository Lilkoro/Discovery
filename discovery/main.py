from discovery.discovery import Discovery
from discovery.autoggen import Auto_gen
import asyncio
import traceback # For getting tracebacks

class DiscoveryMain:
    def __init__(self):
        # Create Discovery instance
        self.discovery = Discovery()
        self.auto_gen = Auto_gen(self.discovery)
        self.skills = None

    async def run(self):
        """Main execution function"""
        # Check server connection and summon bot
        server_active = await self.discovery.check_server_and_join()
        
        if not server_active:
            print("Cannot connect to server, exiting")
            return
        await self.auto_gen.main(message="Your goal is to reach the Nether. Mine obsidian and create a Nether portal!")

        # Processing on exit (executed outside try)
        if self.discovery:
            self.discovery.disconnect_bot()
            print("Disconnected bot from server")

# Main process
if __name__ == "__main__":
    try:
        # Create and run DiscoveryMain instance
        discovery_main = DiscoveryMain()
        asyncio.run(discovery_main.run())
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
