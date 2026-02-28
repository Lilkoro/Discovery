from discovery.discovery import Discovery
from discovery.autoggen import Auto_gen
import asyncio
import traceback # For fetching stacktraces

class DiscoveryMain:
    def __init__(self):
        # Create Discovery instance
        self.discovery = Discovery()
        self.auto_gen = Auto_gen(self.discovery)
        self.skills = None

    async def run(self):
        """Main execution function"""
        # Server connection check and bot summon
        server_active = await self.discovery.check_server_and_join()
        
        if not server_active:
            print("Impossible to connect to the server, shutting down")
            return
        await self.auto_gen.main(message="Your objective is to reach the Nether. Mine obsidian and create a Nether portal!")

        # Action on exit (executed outside try block)
        if self.discovery:
            self.discovery.disconnect_bot()
            print("Bot disconnected from the server")

# Main execution
if __name__ == "__main__":
    try:
        # Create and run DiscoveryMain instance
        discovery_main = DiscoveryMain()
        asyncio.run(discovery_main.run())
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
