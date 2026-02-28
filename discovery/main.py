from discovery.discovery import Discovery
from discovery.autoggen import Auto_gen
import asyncio
import traceback # For fetching stacktraces
import time

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
    print("\033[92mStarting Auto-Run Discovery Bot...\033[0m")
    while True:
        try:
            # Create and run DiscoveryMain instance
            discovery_main = DiscoveryMain()
            asyncio.run(discovery_main.run())
        except KeyboardInterrupt:
            # Clean exit when user presses Ctrl+C
            print("\n\033[93m[INTERRUPTED] Manual exit detected. Stopping auto-restart loop.\033[0m")
            break
        except Exception as e:
            # Auto-Recover from any other error (API 429, Minecraft disconnect, random crashes)
            print(f"\n\033[91m[CRASH DETECTED] An error occurred: {e}\033[0m")
            import traceback
            traceback.print_exc()
            
            # Wait before restarting to avoid spamming the server
            wait_seconds = 15
            print(f"\n\033[96m[AUTO-RESTART] Bot will attempt to reconnect and resume in {wait_seconds} seconds...\033[0m")
            time.sleep(wait_seconds)
            print("\033[92m[AUTO-RESTART] Restarting bot now...\033[0m\n")
