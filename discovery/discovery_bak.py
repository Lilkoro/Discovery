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
        require('canvas') # ã‚¨ãƒ©ãƒ¼ãŒå‡ºã‚‹ã®ã§è¿½åŠ 
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
        # Node.jsã®ãƒ¢ã‚¸ãƒ¥ãƒ¼ãƒ«ãƒ‘ã‚¹ã‚’è¨­å®šï¼ˆmineflayerãƒ‡ã‚£ãƒ¬ã‚¯ãƒˆãƒªã®node_modulesã‚’å‚ç…§ï¼‰
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
        
        # Web Inventoryã‚’æœ‰åŠ¹åŒ–
        self.web_inventory(self.bot,{"port":self.web_inventory_port})
    
    def bot_join(self):
        """ãƒœãƒƒãƒˆã‚’ã‚µãƒ¼ãƒãƒ¼ã«æŽ¥ç¶šã—ã¾ã™"""
        self.is_connected = False
        # createBot å‘¼ã³å‡ºã—ãŒã‚¿ã‚¤ãƒ ã‚¢ã‚¦ãƒˆã™ã‚‹ã“ã¨ãŒã‚ã£ãŸãŸã‚ã€ã‚¿ã‚¤ãƒ ã‚¢ã‚¦ãƒˆã‚’ååˆ†é•·ãè¨­å®š
        # (javascript.proxy ã®ä»•æ§˜ã§ keyword å¼•æ•° `timeout` ã‚’ä¸Žãˆã‚‹ã¨ã€JS å‘¼ã³å‡ºã—å¾…ã¡æ™‚é–“ã‚’å»¶é•·ã§ãã‚‹)
        self.bot = self.mineflayer.createBot({
            "host": self.minecraft_host,
            "port": self.minecraft_port,
            "username": "BOT",
            "version": self.minecraft_version
        }, timeout=10000)  # 10 ç§’ã«å»¶é•·
        
        # ã‚¹ãƒãƒ¼ãƒ³æ™‚ã®å‡¦ç†
        def handle_spawn(*args):
            print("\033[92mBotãŒã‚¹ãƒãƒ¼ãƒ³ã—ã¾ã—ãŸ\033[0m")
            self.is_connected = True
        
        # ã‚¨ãƒ©ãƒ¼æ™‚ã®å‡¦ç†
        def handle_error(err, *args):
            print(f"\033[91mãƒœãƒƒãƒˆæŽ¥ç¶šã‚¨ãƒ©ãƒ¼: {err}\033[0m")
            self.is_connected = False
            
        # åˆ‡æ–­æ™‚ã®å‡¦ç†
        def handle_end(*args):
            print("\033[91m\nBOTã‚’åˆ‡æ–­ã—ã¾ã—ãŸ\033[0m")
            self.is_connected = False
        
        # ãƒ“ãƒ¥ãƒ¼ã‚¢ãƒ¼ã‚’é–‹ã (åˆå›žã®ã¿)
        if self.viewer is None and self.opend_browser is None:
            try:
                print(f"Starting Prismarine Viewer on port {self.prismarine_viewer_port}...")
                self.viewer = self.viewer_module.mineflayer(self.bot, {
                    "firstPerson": True,
                    "port": int(self.prismarine_viewer_port)
                })
                # ãƒ–ãƒ©ã‚¦ã‚¶è‡ªå‹•èµ·å‹•ã¯ã‚³ãƒ¡ãƒ³ãƒˆã‚¢ã‚¦ãƒˆ (å¿…è¦ãªã‚‰è§£é™¤)
                webbrowser.open(f'http://localhost:{self.prismarine_viewer_port}')
                # ãƒ–ãƒ©ã‚¦ã‚¶ã§Web Inventoryã‚’é–‹ã
                webbrowser.open(f'http://localhost:{self.web_inventory_port}')
                print(f"Prismarine Viewer started successfully.")
                self.opend_browser = True
            except Exception as e:
                print(f"Failed to start Prismarine Viewer: {e}")
                self.viewer = None # å¤±æ•—ã—ãŸã‚‰Noneã«æˆ»ã™
        else:
            print("Prismarine Viewer already running.")
        
        # ã‚¤ãƒ™ãƒ³ãƒˆãƒªã‚¹ãƒŠãƒ¼ã‚’è¨­å®š
        self.bot.once('spawn', handle_spawn)
        self.bot.on('error', handle_error)
        self.bot.on('end', handle_end)
        self.mcdata = require("minecraft-data")(self.bot.version)
        self.load_plugins()
        print(f"enableServerListing: {self.bot.settings.enableServerListing}")
        while not self.bot.settings.enableServerListing:
            print("ã‚µãƒ¼ãƒãƒ¼æŽ¥ç¶šä¸­...")
            time.sleep(1)

    async def check_server_active(self, timeout=10):
        """
        ã‚µãƒ¼ãƒãƒ¼ãŒã‚¢ã‚¯ãƒ†ã‚£ãƒ–ã‹ã©ã†ã‹ã‚’ç¢ºèªã—ã¾ã™
        
        Args:
            timeout (int): ã‚¿ã‚¤ãƒ ã‚¢ã‚¦ãƒˆç§’æ•°
            
        Returns:
            bool: ã‚µãƒ¼ãƒãƒ¼ãŒã‚¢ã‚¯ãƒ†ã‚£ãƒ–ã§ã‚ã‚Œã°Trueã€ãã‚Œä»¥å¤–ã¯False
        """
        if not self.bot:
            self.bot_join()
            
        start_time = asyncio.get_event_loop().time()
        while not self.is_connected:
            # ã‚¿ã‚¤ãƒ ã‚¢ã‚¦ãƒˆãƒã‚§ãƒƒã‚¯
            if asyncio.get_event_loop().time() - start_time > timeout:
                print(f"ã‚µãƒ¼ãƒãƒ¼æŽ¥ç¶šã‚¿ã‚¤ãƒ ã‚¢ã‚¦ãƒˆ ({timeout}ç§’)")
                return False
            await asyncio.sleep(0.5)
            
        return True
        
    async def check_server_and_join(self, timeout=15):
        """
        ã‚µãƒ¼ãƒãƒ¼æŽ¥ç¶šçŠ¶æ…‹ã‚’ç¢ºèªã—ã€æŽ¥ç¶šã§ãã¦ã„ã‚Œã°ãƒœãƒƒãƒˆã‚’å¬å–šã—ã¾ã™
        
        Args:
            timeout (int): æŽ¥ç¶šç¢ºèªã®ã‚¿ã‚¤ãƒ ã‚¢ã‚¦ãƒˆç§’æ•°
            
        Returns:
            bool: æŽ¥ç¶šã¨ãƒœãƒƒãƒˆå¬å–šãŒæˆåŠŸã—ãŸã‚‰Trueã€å¤±æ•—ã—ãŸã‚‰False
        """
        print("Minecraftã‚µãƒ¼ãƒãƒ¼ã®æŽ¥ç¶šçŠ¶æ…‹ã‚’ç¢ºèªã—ã¦ã„ã¾ã™...")
        
        # ã‚µãƒ¼ãƒãƒ¼æŽ¥ç¶šçŠ¶æ…‹ç¢ºèª
        is_active = await self.check_server_active(timeout=timeout)
        
        if is_active:
            print(f"âœ… Minecraftã‚µãƒ¼ãƒãƒ¼ã¯ç¨¼åƒä¸­ã§ã™ï¼(ãƒãƒ¼ã‚¸ãƒ§ãƒ³: {self.bot.version})")
            
            # ã‚¹ã‚­ãƒ«ã®ã‚¤ãƒ³ã‚¹ã‚¿ãƒ³ã‚¹ã‚’ä½œæˆ
            self.skills = Skills(self)
            print("ãƒœãƒƒãƒˆãŒæ­£å¸¸ã«å¬å–šã•ã‚Œã¾ã—ãŸ")
            return True
        else:
            print("âŒ Minecraftã‚µãƒ¼ãƒãƒ¼ã«æŽ¥ç¶šã§ãã¾ã›ã‚“ã§ã—ãŸ")
            print("ã‚µãƒ¼ãƒãƒ¼ãŒèµ·å‹•ã—ã¦ã„ã‚‹ã‹ç¢ºèªã—ã¦ãã ã•ã„")
            return False

    def is_server_active(self):
        """
        ç¾åœ¨ã®ã‚µãƒ¼ãƒãƒ¼æŽ¥ç¶šçŠ¶æ…‹ã‚’ç¢ºèªã—ã¾ã™ï¼ˆéžåŒæœŸã§ã¯ãªã„ï¼‰
        
        Returns:
            bool: æŽ¥ç¶šä¸­ã§ã‚ã‚Œã°Trueã€ãã‚Œä»¥å¤–ã¯False
        """
        if not self.bot:
            return False
            
        # æŽ¥ç¶šçŠ¶æ…‹ã‚’ç¢ºèª
        return self.is_connected
        
    def get_server_info(self):
        """
        ã‚µãƒ¼ãƒãƒ¼ã®åŸºæœ¬æƒ…å ±ã‚’å–å¾—ã—ã¾ã™
        
        Returns:
            dict: ã‚µãƒ¼ãƒãƒ¼æƒ…å ±ã‚’å«ã‚€è¾žæ›¸
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
            print(f"ã‚µãƒ¼ãƒãƒ¼æƒ…å ±å–å¾—ã‚¨ãƒ©ãƒ¼: {e}")
            return {"active": False, "error": str(e)}

    def disconnect_bot(self):
        """ãƒœãƒƒãƒˆã‚’ã‚µãƒ¼ãƒãƒ¼ã‹ã‚‰åˆ‡æ–­ã—ã€é–¢é€£ãƒªã‚½ãƒ¼ã‚¹ã‚’è§£æ”¾ã—ã¾ã™ã€‚ãƒœãƒƒãƒˆãŒå¿œç­”ã—ãªã„å ´åˆã§ã‚‚å¼·åˆ¶çš„ã«çŠ¶æ…‹ã‚’ãƒªã‚»ãƒƒãƒˆã—ã¾ã™ã€‚"""
        print("Disconnecting bot and releasing resources...")

        original_bot = self.bot
        original_viewer = self.viewer

        # æœ€åˆã«Pythonå´ã®çŠ¶æ…‹ã‚’ãƒªã‚»ãƒƒãƒˆ
        self.bot = None
        self.is_connected = False
        self.viewer = None

        # --- ã‚¯ãƒªãƒ¼ãƒ³ã‚¢ãƒƒãƒ—å‡¦ç† (å¤±æ•—ã—ã¦ã‚‚ç¶šè¡Œ) ---
        # å…ƒã®Viewerã‚’é–‰ã˜ã‚‹è©¦ã¿
        try:
            # hasattrã‚‚ã‚¿ã‚¤ãƒ ã‚¢ã‚¦ãƒˆã™ã‚‹å¯èƒ½æ€§ãŒã‚ã‚‹ãŸã‚tryãƒ–ãƒ­ãƒƒã‚¯å†…ã«å«ã‚ã‚‹
            if original_viewer and hasattr(original_viewer, 'close'):
                original_viewer.close()
        except Exception as e:
            print(f"\033[31mError closing original Prismarine Viewer (ignored): {e}\033[0m")

        # å…ƒã®botã‚ªãƒ–ã‚¸ã‚§ã‚¯ãƒˆã«é–¢é€£ä»˜ã‘ã‚‰ã‚ŒãŸviewerã‚’é–‰ã˜ã‚‹è©¦ã¿
        try:
            # hasattrã‚„ãƒ—ãƒ­ãƒ‘ãƒ†ã‚£ã‚¢ã‚¯ã‚»ã‚¹ã‚‚tryãƒ–ãƒ­ãƒƒã‚¯å†…ã«å«ã‚ã‚‹
            if original_bot:
                bot_viewer = None
                # viewerãƒ—ãƒ­ãƒ‘ãƒ†ã‚£ã¸ã®ã‚¢ã‚¯ã‚»ã‚¹è©¦è¡Œã‚‚try-except
                try:
                    if hasattr(original_bot, 'viewer'):
                         bot_viewer = original_bot.viewer
                except Exception as e_getattr:
                    print(f"\033[31mError accessing original_bot.viewer (ignored): {e_getattr}\033[0m")

                # viewerã‚ªãƒ–ã‚¸ã‚§ã‚¯ãƒˆã®closeè©¦è¡Œã‚‚try-except
                try:
                    if bot_viewer and hasattr(bot_viewer, 'close'):
                        bot_viewer.close()
                except Exception as e_close:
                     print(f"\033[31mError closing bot_viewer (ignored): {e_close}\033[0m")
        except Exception as e:
            # botã‚ªãƒ–ã‚¸ã‚§ã‚¯ãƒˆè‡ªä½“ã¸ã®ã‚¢ã‚¯ã‚»ã‚¹ç­‰ã§äºˆæœŸã›ã¬ã‚¨ãƒ©ãƒ¼ãŒå‡ºãŸå ´åˆ
            print(f"\033[31mError during bot.viewer cleanup (ignored): {e}\033[0m")

        # å…ƒã®ãƒœãƒƒãƒˆã‚’åˆ‡æ–­ã™ã‚‹è©¦ã¿
        try:
            # hasattrã‚‚ã‚¿ã‚¤ãƒ ã‚¢ã‚¦ãƒˆã™ã‚‹å¯èƒ½æ€§ãŒã‚ã‚‹ãŸã‚tryãƒ–ãƒ­ãƒƒã‚¯å†…ã«å«ã‚ã‚‹
            if original_bot and hasattr(original_bot, 'quit'):
                 original_bot.quit()
        except Exception as e:
            print(f"\033[31mError quitting original bot instance (ignored): {e}\033[0m")

    async def reconnect_bot(self, timeout=15):
        """
        ãƒœãƒƒãƒˆã‚’ã‚µãƒ¼ãƒãƒ¼ã‹ã‚‰åˆ‡æ–­ã—ã€å†æŽ¥ç¶šã‚’è©¦ã¿ã¾ã™ã€‚

        Args:
            timeout (int): å†æŽ¥ç¶šæ™‚ã®ã‚¿ã‚¤ãƒ ã‚¢ã‚¦ãƒˆç§’æ•°

        Returns:
            bool: å†æŽ¥ç¶šãŒæˆåŠŸã—ãŸã‚‰Trueã€å¤±æ•—ã—ãŸã‚‰False
        """
        print("ãƒœãƒƒãƒˆã‚’å†æŽ¥ç¶šã—ã¦ã„ã¾ã™...")
        self.disconnect_bot() # åŒæœŸçš„ã«å®Ÿè¡Œ
        print("ãƒœãƒƒãƒˆã‚’åˆ‡æ–­ã—ã¾ã—ãŸ")

        # bot_join ã¯åŒæœŸçš„ã«ãƒœãƒƒãƒˆã®åˆæœŸåŒ–ã‚’é–‹å§‹ã™ã‚‹
        self.bot_join()
        print("ãƒœãƒƒãƒˆã‚’å†æŽ¥ç¶šã—ã¾ã—ãŸ")
        # check_server_active ã§æŽ¥ç¶šå®Œäº†ã‚’å¾…ã¤ (awaitã‚’ä½¿ç”¨)
        print("å†æŽ¥ç¶šå¾Œã®ã‚µãƒ¼ãƒãƒ¼æŽ¥ç¶šã‚’ç¢ºèªã—ã¦ã„ã¾ã™...")
        return await self.check_server_active(timeout=timeout)

    async def get_bot_status(self, retry_count=0, max_retries=1):
        """ãƒœãƒƒãƒˆã®çŠ¶æ…‹ã¨å‘¨è¾ºæƒ…å ±ï¼ˆãƒã‚¤ã‚ªãƒ¼ãƒ ã€æ™‚é–“ã€ä½“åŠ›ã€ç©ºè…¹åº¦ã€ã‚¨ãƒ³ãƒ†ã‚£ãƒ†ã‚£ã€ã‚¤ãƒ³ãƒ™ãƒ³ãƒˆãƒªã€ãƒ–ãƒ­ãƒƒã‚¯åˆ†é¡žï¼‰ã‚’å–å¾—"""
        await self.check_server_active()
        # æŽ¥ç¶šçŠ¶æ…‹ã¨ãƒœãƒƒãƒˆã‚¤ãƒ³ã‚¹ã‚¿ãƒ³ã‚¹ã®å­˜åœ¨ã‚’ã‚ˆã‚Šç¢ºå®Ÿã«ãƒã‚§ãƒƒã‚¯
        if not self.bot or not self.is_connected:
            print("ã‚¨ãƒ©ãƒ¼: ãƒœãƒƒãƒˆãŒæŽ¥ç¶šã•ã‚Œã¦ã„ãªã„ã‹ã€åˆæœŸåŒ–ã•ã‚Œã¦ã„ã¾ã›ã‚“ã€‚")
            # å†æŽ¥ç¶šã‚’è©¦ã¿ã‚‹ãƒ­ã‚¸ãƒƒã‚¯ã‚’è¿½åŠ ã™ã‚‹ã“ã¨ã‚‚æ¤œè¨Žã§ãã‚‹ãŒã€ã“ã“ã§ã¯Noneã‚’è¿”ã™
            # raise Exception("ãƒœãƒƒãƒˆãŒæŽ¥ç¶šã•ã‚Œã¦ã„ãªã„ã‹ã€åˆæœŸåŒ–ã•ã‚Œã¦ã„ã¾ã›ã‚“ã€‚")
            return None
        if not self.skills:
            print("ã‚¨ãƒ©ãƒ¼: ã‚¹ã‚­ãƒ«ãŒåˆæœŸåŒ–ã•ã‚Œã¦ã„ã¾ã›ã‚“ã€‚")
            # raise Exception("ã‚¹ã‚­ãƒ«ãŒåˆæœŸåŒ–ã•ã‚Œã¦ã„ã¾ã›ã‚“ã€‚")
            return None

        try:
            # --- ãƒœãƒƒãƒˆã®åŸºæœ¬æƒ…å ±ã‚’å–å¾— --- 
            try:
                # entityã¸ã®ã‚¢ã‚¯ã‚»ã‚¹å‰ã«å†åº¦æŽ¥ç¶šã‚’ç¢ºèªã™ã‚‹ï¼ˆå¿µã®ãŸã‚ï¼‰
                if not self.is_connected:
                     print("ã‚¨ãƒ©ãƒ¼: entityã‚¢ã‚¯ã‚»ã‚¹å‰ã«æŽ¥ç¶šãŒåˆ‡æ–­ã•ã‚Œã¾ã—ãŸã€‚")
                     raise Exception("entityã‚¢ã‚¯ã‚»ã‚¹å‰ã«æŽ¥ç¶šãŒåˆ‡æ–­ã•ã‚Œã¾ã—ãŸã€‚")
                bot_entity = self.bot.entity # ã“ã“ã§ã‚¿ã‚¤ãƒ ã‚¢ã‚¦ãƒˆãŒç™ºç”Ÿã™ã‚‹å¯èƒ½æ€§ãŒã‚ã‚‹
            except Exception as e:
                if "Timed out accessing 'entity'" in str(e) and retry_count < max_retries:
                    print(f"\033[93mã‚¨ãƒ³ãƒ†ã‚£ãƒ†ã‚£ã¸ã®ã‚¢ã‚¯ã‚»ã‚¹ãŒã‚¿ã‚¤ãƒ ã‚¢ã‚¦ãƒˆã—ã¾ã—ãŸã€‚å†æŽ¥ç¶šã‚’è©¦ã¿ã¾ã™... (è©¦è¡Œ {retry_count + 1}/{max_retries})\033[0m")
                    reconnected = await self.reconnect_bot()
                    if reconnected:
                        print("\033[92må†æŽ¥ç¶šã«æˆåŠŸã—ã¾ã—ãŸã€‚ã‚¹ãƒ†ãƒ¼ã‚¿ã‚¹å–å¾—ã‚’å†è©¦è¡Œã—ã¾ã™ã€‚\033[0m")
                        # å†å¸°å‘¼ã³å‡ºã—ã§ãƒªãƒˆãƒ©ã‚¤ã‚«ã‚¦ãƒ³ãƒˆã‚’å¢—ã‚„ã™
                        return await self.get_bot_status(retry_count=retry_count + 1, max_retries=max_retries)
                    else:
                        print("\033[91må†æŽ¥ç¶šã«å¤±æ•—ã—ã¾ã—ãŸã€‚ã‚¹ãƒ†ãƒ¼ã‚¿ã‚¹å–å¾—ã‚’ä¸­æ­¢ã—ã¾ã™ã€‚\033[0m")
                        return None # å†æŽ¥ç¶šå¤±æ•—æ™‚ã¯Noneã‚’è¿”ã™
                else:
                    # ã‚¿ã‚¤ãƒ ã‚¢ã‚¦ãƒˆä»¥å¤–ã®ã‚¨ãƒ©ãƒ¼ã€ã¾ãŸã¯ãƒªãƒˆãƒ©ã‚¤ä¸Šé™è¶…éŽ
                    print(f"\033[91mã‚¨ãƒ³ãƒ†ã‚£ãƒ†ã‚£å–å¾—ä¸­ã«å›žå¾©ä¸èƒ½ãªã‚¨ãƒ©ãƒ¼ãŒç™ºç”Ÿã—ã¾ã—ãŸï¼ˆãƒªãƒˆãƒ©ã‚¤è¶…éŽã¾ãŸã¯ã‚¿ã‚¤ãƒ ã‚¢ã‚¦ãƒˆä»¥å¤–ï¼‰: {e}\033[0m")
                    import traceback
                    traceback.print_exc()
                    return None # ã‚¨ãƒ©ãƒ¼æ™‚ã¯Noneã‚’è¿”ã™

            # --- bot_entity ã‚’ä½¿ç”¨ã™ã‚‹ä»¥é™ã®å‡¦ç† --- 
            bot_pos_raw = bot_entity.position # Yåº§æ¨™ã¯ã‚¨ãƒ³ãƒ†ã‚£ãƒ†ã‚£åŸºæº–
            bot_health = self.bot.health
            bot_food = self.bot.food
            bot_time = self.bot.time.timeOfDay

            # ãƒœãƒƒãƒˆãŒã„ã‚‹ãƒ–ãƒ­ãƒƒã‚¯ã¨ãƒã‚¤ã‚ªãƒ¼ãƒ ã‚’å–å¾—
            center_block = self.bot.blockAt(bot_pos_raw)
            #bottom_block = self.discovery.bot.blockAt(bot_pos_raw.offset(0, -1, 0))
            bot_pos = center_block.position.offset(0, 1, 0)
            bot_biome_id = self.bot.world.getBiome(bot_pos)
            bot_biome_name = self.mcdata.biomes[str(bot_biome_id)]['name']
            bot_x = bot_pos.x
            bot_z = bot_pos.z
            bot_y = bot_pos.y # yåº§æ¨™ã‚‚è¿½åŠ 

            # --- å‘¨å›²ã®ãƒ–ãƒ­ãƒƒã‚¯ã‚’å–å¾— & åˆ†é¡ž ---
            # _get_surrounding_blocks ãŒ await ã‚’å¿…è¦ã¨ã™ã‚‹ã‹ç¢ºèª
            blocks = await self.skills._get_surrounding_blocks(
                position=bot_pos, # ã‚¹ã‚­ãƒ«ã®å¼•æ•°åã«åˆã‚ã›ã‚‹
                x_distance=3,
                y_distance=2,
                z_distance=3
            )

            # ãƒ–ãƒ­ãƒƒã‚¯åã‚’ã‚°ãƒ«ãƒ¼ãƒ—ã”ã¨ã«ä¸€æ™‚çš„ã«æ ¼ç´
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

            # ãƒ–ãƒ­ãƒƒã‚¯åˆ†é¡žçµæžœï¼ˆé‡è¤‡é™¤åŽ»ã¨ã‚½ãƒ¼ãƒˆï¼‰
            classified_blocks = {
                "front_blocks": sorted(list(set(temp_grouped_block_names["group1"]))),
                "right_blocks": sorted(list(set(temp_grouped_block_names["group2"]))),
                "back_blocks": sorted(list(set(temp_grouped_block_names["group3"]))),
                "left_blocks": sorted(list(set(temp_grouped_block_names["group4"]))),
                "center_blocks": sorted(list(set(temp_grouped_block_names["group0"])))
            }

            # --- è¿‘ãã®ã‚¨ãƒ³ãƒ†ã‚£ãƒ†ã‚£æƒ…å ±ã‚’å–å¾— ---
            nearby_entities_info = []
            # _get_nearby_entities ã¯åŒæœŸãƒ¡ã‚½ãƒƒãƒ‰ã®å¯èƒ½æ€§ã‚ã‚Š
            nearby_entities_raw = self.skills._get_nearby_entities(max_distance=16) # ç¯„å›²ã¯é©å®œèª¿æ•´
            if nearby_entities_raw:
                for entity in nearby_entities_raw:
                    # æœ‰åŠ¹ãªã‚¨ãƒ³ãƒ†ã‚£ãƒ†ã‚£æƒ…å ±ã®ã¿æŠ½å‡º
                    if hasattr(entity, 'name') and hasattr(entity, 'position') and entity.position:
                        nearby_entities_info.append({
                            "name": entity.name,
                            "position": {
                                "x": round(entity.position.x, 1), # å°æ•°ç‚¹ä»¥ä¸‹ç¬¬ä¸€ä½ã§å››æ¨äº”å…¥
                                "y": round(entity.position.y, 1), # å°æ•°ç‚¹ä»¥ä¸‹ç¬¬ä¸€ä½ã§å››æ¨äº”å…¥
                                "z": round(entity.position.z, 1)  # å°æ•°ç‚¹ä»¥ä¸‹ç¬¬ä¸€ä½ã§å››æ¨äº”å…¥
                            }
                        })

            # --- ã‚¤ãƒ³ãƒ™ãƒ³ãƒˆãƒªæƒ…å ±ã‚’å–å¾— ---
            inventory_info = {}
            # get_inventory_counts ã¯åŒæœŸãƒ¡ã‚½ãƒƒãƒ‰
            inventory_info = await self.skills.get_inventory_counts()

            # --- æœ€çµ‚çš„ãªãƒ¬ã‚¹ãƒãƒ³ã‚¹ã‚’ä½œæˆ ---
            final_result = {
                "biome": bot_biome_name,
                "time_of_day": bot_time,
                "health": bot_health,
                "hunger": bot_food,
                "bot_position": f"x={bot_x:.1f}, y={bot_y:.1f}, z={bot_z:.1f}",
                "nearby_entities": nearby_entities_info,
                "inventory": inventory_info,
                **classified_blocks # ãƒ–ãƒ­ãƒƒã‚¯åˆ†é¡žçµæžœã‚’å±•é–‹ã—ã¦çµåˆ
            }
            return final_result

        except Exception as e:
            print(f"ãƒœãƒƒãƒˆã‚¹ãƒ†ãƒ¼ã‚¿ã‚¹ã®å–å¾—ä¸­ã«äºˆæœŸã›ã¬ã‚¨ãƒ©ãƒ¼ãŒç™ºç”Ÿã—ã¾ã—ãŸ: {e}")
            import traceback
            traceback.print_exc()
            return None
        
    async def get_skills_list(self, skill_names: list[str] | None = None):
        """
        Skillsã‚¯ãƒ©ã‚¹ã§åˆ©ç”¨å¯èƒ½ãªæŒ‡å®šã•ã‚ŒãŸé–¢æ•°ï¼ˆãƒ¡ã‚½ãƒƒãƒ‰ï¼‰ã®åå‰ã€èª¬æ˜Žã€ä½¿ç”¨æ³•ã®ãƒªã‚¹ãƒˆã‚’å–å¾—ã—ã¾ã™ã€‚
        skill_namesãŒNoneã¾ãŸã¯ç©ºã®å ´åˆã€ç©ºã®ãƒªã‚¹ãƒˆã‚’è¿”ã—ã¾ã™ã€‚

        Args:
            skill_names (list[str] | None, optional): è©³ç´°ã‚’å–å¾—ã—ãŸã„ã‚¹ã‚­ãƒ«åã®ãƒªã‚¹ãƒˆã€‚ Defaults to None.

        Returns:
            list: å„ã‚¹ã‚­ãƒ«æƒ…å ±ã‚’å«ã‚€è¾žæ›¸ã®ãƒªã‚¹ãƒˆã€‚
        """
        if self.skills is None:
            print("ã‚¨ãƒ©ãƒ¼: SkillsãŒåˆæœŸåŒ–ã•ã‚Œã¦ã„ã¾ã›ã‚“")
            return [] # ç©ºã®ãƒªã‚¹ãƒˆã‚’è¿”ã™

        # skill_namesãŒNoneã¾ãŸã¯ç©ºãªã‚‰ç©ºãƒªã‚¹ãƒˆã‚’è¿”ã™
        if not skill_names:
            return []

        skill_list = []
        # inspect.getmembersã§skillsã‚ªãƒ–ã‚¸ã‚§ã‚¯ãƒˆã®ãƒ¡ã‚½ãƒƒãƒ‰ã‚’å–å¾—
        for name, method in inspect.getmembers(self.skills, inspect.ismethod):
            # æŒ‡å®šã•ã‚ŒãŸãƒªã‚¹ãƒˆã«å«ã¾ã‚Œã€ã‹ã¤ã‚¢ãƒ³ãƒ€ãƒ¼ã‚¹ã‚³ã‚¢ã§å§‹ã¾ã‚‰ãªã„å…¬é–‹ãƒ¡ã‚½ãƒƒãƒ‰ã®ã¿ã‚’å¯¾è±¡ã¨ã™ã‚‹
            if name in skill_names and not name.startswith('_'):
                # docstringã‚’å–å¾—ã—ã€æ•´å½¢
                docstring = inspect.cleandoc(method.__doc__) if method.__doc__ else ""
                description_lines = []
                usage_lines = []
                in_description = True
                section_headers = ("Args:", "Arguments:", "Parameters:", "Returns:", "Yields:", "Raises:", "Attributes:")

                if docstring:
                    lines = docstring.splitlines()
                    if lines:
                        description_lines.append(lines[0]) # æœ€åˆã®è¡Œã¯å¿…ãšdescription
                        # 2è¡Œç›®ä»¥é™ã‚’å‡¦ç†
                        for i in range(1, len(lines)):
                            line = lines[i]
                            stripped_line = line.strip()
                            # Descriptionã¨Usageã®åŒºåˆ‡ã‚Šã‚’åˆ¤å®š
                            if in_description and (not stripped_line or stripped_line.startswith(section_headers)):
                                in_description = False
                            
                            if in_description:
                                description_lines.append(line)
                            else:
                                usage_lines.append(line)

                description = "\n".join(description_lines).strip()
                usage = "\n".join(usage_lines).strip()
                if not description:
                    description = "èª¬æ˜ŽãŒã‚ã‚Šã¾ã›ã‚“ã€‚"
                if not usage:
                    usage = "-" # UsageãŒãªã„å ´åˆã¯ãƒã‚¤ãƒ•ãƒ³

                # --- é–¢æ•°ã‚·ã‚°ãƒãƒãƒ£ã®å–å¾— ---
                try:
                    source_lines = inspect.getsource(method).splitlines()
                    # æœ€åˆã® 'def' ã¾ãŸã¯ 'async def' ã®è¡Œã‚’å–å¾—
                    signature_line = next((line for line in source_lines if line.strip().startswith(('def ', 'async def '))), None)
                    if signature_line:
                        # æœ«å°¾ã®ã‚³ãƒ­ãƒ³ã‚’é™¤åŽ»
                        signature = signature_line.strip().rstrip(':')
                    else:
                        # è¦‹ã¤ã‹ã‚‰ãªã„å ´åˆã¯ãƒ•ã‚©ãƒ¼ãƒ«ãƒãƒƒã‚¯
                        signature = name
                except (TypeError, OSError):
                    # ã‚½ãƒ¼ã‚¹ã‚³ãƒ¼ãƒ‰ãŒå–å¾—ã§ããªã„å ´åˆã¯ãƒ•ã‚©ãƒ¼ãƒ«ãƒãƒƒã‚¯
                    signature = name
                # --- ã“ã“ã¾ã§è¿½åŠ ãƒ»å¤‰æ›´ ---

                skill_list.append({
                    "name": signature, # name ã‚’ signature ã«å¤‰æ›´ (ã¾ãŸã¯ä¸¡æ–¹å«ã‚ã‚‹)
                    "description": description, # åˆ†å‰²ã—ãŸèª¬æ˜Ž
                    "usage": usage           # åˆ†å‰²ã—ãŸä½¿ã„æ–¹
                })

        # åå‰é †ã«ã‚½ãƒ¼ãƒˆã—ã¦è¿”ã™ (ã‚½ãƒ¼ãƒˆã‚­ãƒ¼ã‚‚å¤‰æ›´)
        return sorted(skill_list, key=lambda x: x['name'])
    
    async def get_skill_code(self, skill_names: list[str]):
        """æŒ‡å®šã•ã‚ŒãŸã‚¹ã‚­ãƒ«é–¢æ•°åã®ãƒªã‚¹ãƒˆã«å¯¾å¿œã™ã‚‹ã‚½ãƒ¼ã‚¹ã‚³ãƒ¼ãƒ‰ã‚’å–å¾— (docstringé™¤å¤–)ã€‚

        Args:
            skill_names (list[str]): ã‚½ãƒ¼ã‚¹ã‚³ãƒ¼ãƒ‰ã‚’å–å¾—ã—ãŸã„ã‚¹ã‚­ãƒ«åã®ãƒªã‚¹ãƒˆã€‚

        Returns:
            dict: å„ã‚¹ã‚­ãƒ«åã¨ãã®ã‚½ãƒ¼ã‚¹ã‚³ãƒ¼ãƒ‰ã¾ãŸã¯ã‚¨ãƒ©ãƒ¼æƒ…å ±ã‚’å«ã‚€è¾žæ›¸ã€‚
                  ä¾‹: {'skill_name': {'success': bool, 'message': str, 'code': str | None}}
        """
        results = {}
        if self.skills is None:
            # skillsãŒãªã„å ´åˆã¯ã€ã™ã¹ã¦ã®ã‚¹ã‚­ãƒ«åã«å¯¾ã—ã¦ã‚¨ãƒ©ãƒ¼ã‚’è¿”ã™
            for name in skill_names:
                results[name] = {
                    "success": False,
                    "message": "ã‚¨ãƒ©ãƒ¼: SkillsãŒåˆæœŸåŒ–ã•ã‚Œã¦ã„ã¾ã›ã‚“",
                    "code": None
                }
            return results

        # --- Docstringã‚’é™¤åŽ»ã™ã‚‹Transformer --- (é–¢æ•°å†…ã«å®šç¾©)
        class DocstringRemover(ast.NodeTransformer):
            def _remove_docstring(self, node):
                if not node.body:
                    return
                # é–¢æ•°/ã‚¯ãƒ©ã‚¹å®šç¾©å†…ã®æœ€åˆã®å¼ãŒdocstringã§ã‚ã‚‹ã‹ç¢ºèª
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

            # skill_nameã«å¯¾å¿œã™ã‚‹ãƒ¡ã‚½ãƒƒãƒ‰ã‚’å–å¾—
            try:
                method = getattr(self.skills, skill_name)
            except AttributeError:
                single_result["message"] = f"ã‚¨ãƒ©ãƒ¼: ã‚¹ã‚­ãƒ«é–¢æ•° '{skill_name}' ãŒè¦‹ã¤ã‹ã‚Šã¾ã›ã‚“"
                results[skill_name] = single_result
                continue # æ¬¡ã®ã‚¹ã‚­ãƒ«ã¸

            # ãƒ¡ã‚½ãƒƒãƒ‰ãŒå‘¼ã³å‡ºã—å¯èƒ½ã§ã€ã‚¢ãƒ³ãƒ€ãƒ¼ã‚¹ã‚³ã‚¢ã§å§‹ã¾ã‚‰ãªã„ã“ã¨ã‚’ç¢ºèª
            if not callable(method) or skill_name.startswith('_'):
                single_result["message"] = f"ã‚¨ãƒ©ãƒ¼: ã‚¹ã‚­ãƒ«é–¢æ•° '{skill_name}' ãŒè¦‹ã¤ã‹ã‚Šã¾ã›ã‚“ã€ã¾ãŸã¯ã‚¢ã‚¯ã‚»ã‚¹ã§ãã¾ã›ã‚“"
                results[skill_name] = single_result
                continue # æ¬¡ã®ã‚¹ã‚­ãƒ«ã¸

            # ãƒ¡ã‚½ãƒƒãƒ‰ã®ã‚½ãƒ¼ã‚¹ã‚³ãƒ¼ãƒ‰ã‚’å–å¾—ã—ã€docstringã‚’é™¤åŽ»
            try:
                source_code = inspect.getsource(method)
                # ã‚½ãƒ¼ã‚¹ã‚³ãƒ¼ãƒ‰ã®ã‚¤ãƒ³ãƒ‡ãƒ³ãƒˆã‚’é™¤åŽ» (ASTãƒ‘ãƒ¼ã‚¹å‰ã«dedentãŒå¿…è¦)
                dedented_source_code = textwrap.dedent(source_code)

                # ASTã«ãƒ‘ãƒ¼ã‚¹
                tree = ast.parse(dedented_source_code)

                # Docstringã‚’å‰Šé™¤ã™ã‚‹Transformerã‚’é©ç”¨
                transformer = DocstringRemover()
                new_tree = transformer.visit(tree)
                ast.fix_missing_locations(new_tree) # Locationæƒ…å ±ã‚’ä¿®æ­£

                # ASTã‚’ã‚½ãƒ¼ã‚¹ã‚³ãƒ¼ãƒ‰æ–‡å­—åˆ—ã«æˆ»ã™ (Python 3.9+)
                # ast.unparse ã¯ã‚¤ãƒ³ãƒ‡ãƒ³ãƒˆã‚’å†æ§‹ç¯‰ã™ã‚‹
                code_without_docstring = ast.unparse(new_tree)
                single_result["success"] = True
                single_result["message"] = "ã‚½ãƒ¼ã‚¹ã‚³ãƒ¼ãƒ‰ã‚’æ­£å¸¸ã«å–å¾—ã—ã¾ã—ãŸã€‚"
                single_result["code"] = code_without_docstring

            except (TypeError, OSError) as e:
                # ã‚½ãƒ¼ã‚¹ã‚³ãƒ¼ãƒ‰ãŒå–å¾—ã§ããªã„å ´åˆ
                single_result["message"] = f"ã‚¨ãƒ©ãƒ¼: ã‚¹ã‚­ãƒ«é–¢æ•° '{skill_name}' ã®ã‚½ãƒ¼ã‚¹ã‚³ãƒ¼ãƒ‰ã‚’å–å¾—ã§ãã¾ã›ã‚“ã§ã—ãŸ: {e}"
            except SyntaxError as e:
                # AST ãƒ‘ãƒ¼ã‚¹å¤±æ•—æ™‚ã®ã‚¨ãƒ©ãƒ¼ãƒãƒ³ãƒ‰ãƒªãƒ³ã‚°
                single_result["message"] = f"ã‚¨ãƒ©ãƒ¼: ã‚¹ã‚­ãƒ«é–¢æ•° '{skill_name}' ã®ã‚½ãƒ¼ã‚¹ã‚³ãƒ¼ãƒ‰ã®è§£æžã«å¤±æ•—ã—ã¾ã—ãŸ: {e}"
            except AttributeError as e:
                # ast.unparse ãŒãªã„å ´åˆã®ã‚¨ãƒ©ãƒ¼ (Python 3.9æœªæº€)
                if "'module' object has no attribute 'unparse'" in str(e):
                    single_result["message"] = "ã‚¨ãƒ©ãƒ¼: ã“ã®æ©Ÿèƒ½ã«ã¯Python 3.9ä»¥ä¸ŠãŒå¿…è¦ã§ã™ (ast.unparse)ã€‚"
                else:
                    single_result["message"] = f"ã‚¨ãƒ©ãƒ¼: äºˆæœŸã›ã¬ã‚¨ãƒ©ãƒ¼ãŒç™ºç”Ÿã—ã¾ã—ãŸ: {e}"
            
            results[skill_name] = single_result

        return results

    async def execute_python_code(self, code_string: str, wrapper_func_name: str = "main"):
        """
        æ¸¡ã•ã‚ŒãŸPythonã‚³ãƒ¼ãƒ‰æ–‡å­—åˆ—ã‚’ã€æŒ‡å®šã•ã‚ŒãŸåå‰ã®éžåŒæœŸé–¢æ•°å†…ã§å®Ÿè¡Œã—ã¾ã™ã€‚
        ãƒ‡ãƒ•ã‚©ãƒ«ãƒˆã®é–¢æ•°åã¯ 'main' ã§ã™ã€‚
        """
        await self.check_server_active()
        # Check if bot and skills are initialized correctly and bot is connected
        if not self.bot or not self.skills or not self.is_connected:
            error_msg = "ã‚¨ãƒ©ãƒ¼: ãƒœãƒƒãƒˆã¾ãŸã¯ã‚¹ã‚­ãƒ«ãŒåˆæœŸåŒ–ã•ã‚Œã¦ã„ãªã„ã‹ã€ã‚µãƒ¼ãƒãƒ¼ã«æŽ¥ç¶šã•ã‚Œã¦ã„ã¾ã›ã‚“ã€‚"
            print(error_msg)
            return {"success": False, "error": error_msg, "traceback": "", "output": "", "error_output": ""}

        output_buffer = io.StringIO()
        error_buffer = io.StringIO()

        # å®Ÿè¡Œã‚³ãƒ³ãƒ†ã‚­ã‚¹ãƒˆã«æ¸¡ã™å¤‰æ•° (botã‚’è¿½åŠ )
        bot = self.bot # ã‚¨ã‚¤ãƒªã‚¢ã‚¹
        skills = self.skills # ã‚¨ã‚¤ãƒªã‚¢ã‚¹
        discovery = self # ã‚¨ã‚¤ãƒªã‚¢ã‚¹
        exec_globals = {
            "asyncio": asyncio,
            "skills": skills,
            "discovery": discovery,
            "bot": bot,
            "__builtins__": __builtins__ # ã“ã‚ŒãŒå«ã¾ã‚Œã¦ã„ã‚‹ç‚¹ãŒé‡è¦
        }

        # ãƒ¦ãƒ¼ã‚¶ãƒ¼ã‚³ãƒ¼ãƒ‰ã‚’é©åˆ‡ã«ã‚¤ãƒ³ãƒ‡ãƒ³ãƒˆ
        indented_user_code = textwrap.indent(code_string, '    ')

        # éžåŒæœŸãƒ©ãƒƒãƒ‘ãƒ¼é–¢æ•°ã®ã‚³ãƒ¼ãƒ‰æ–‡å­—åˆ—ã‚’ä½œæˆ (æŒ‡å®šã•ã‚ŒãŸé–¢æ•°åã‚’ä½¿ç”¨)
        wrapper_code = f"""
import asyncio

async def {wrapper_func_name}():
{indented_user_code}
"""
        print(f"\033[32m{wrapper_code}\033[0m")

        try:
            # ãƒ©ãƒƒãƒ‘ãƒ¼é–¢æ•°ã‚’å®šç¾©
            exec(wrapper_code, exec_globals)

            # å®šç¾©ã•ã‚ŒãŸéžåŒæœŸé–¢æ•°ã‚ªãƒ–ã‚¸ã‚§ã‚¯ãƒˆã‚’å–å¾— (æŒ‡å®šã•ã‚ŒãŸé–¢æ•°åã‚’ä½¿ç”¨)
            async_func_to_run = exec_globals.get(wrapper_func_name)

            if async_func_to_run and inspect.iscoroutinefunction(async_func_to_run):
                with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(error_buffer):
                    await async_func_to_run()
            else:
                # é–¢æ•°ãŒæ­£ã—ãå®šç¾©ã•ã‚Œãªã‹ã£ãŸå ´åˆã®ã‚¨ãƒ©ãƒ¼
                error_message = f"Failed to define or find the async wrapper function '{wrapper_func_name}'.\\n\\n{wrapper_code}"
                raise RuntimeError(error_message)

            # å®Ÿè¡Œçµæžœã‚’å–å¾—
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
            # exec ã¾ãŸã¯ await ä¸­ã®ã‚¨ãƒ©ãƒ¼ã‚’ã‚­ãƒ£ãƒ—ãƒãƒ£
            error_message = str(e)
            tb_str = traceback.format_exc()
            # ã‚¨ãƒ©ãƒ¼ç™ºç”Ÿå‰ã®ã‚¨ãƒ©ãƒ¼å‡ºåŠ›ã‚‚å–å¾—ã—ã¦ãŠã
            error_output_before_exception = error_buffer.getvalue()

            print(f"\033[31mã‚³ãƒ¼ãƒ‰å®Ÿè¡Œä¸­ã«ã‚¨ãƒ©ãƒ¼ãŒç™ºç”Ÿã—ã¾ã—ãŸ: {error_message}\nã‚¨ãƒ©ãƒ¼è©³ç´°:{tb_str}\033[0m") # ã‚³ãƒ³ã‚½ãƒ¼ãƒ«ã«ã‚‚ã‚¨ãƒ©ãƒ¼è¡¨ç¤º

            result = {
                "success": False,
                "error": error_message,
                "traceback": tb_str,
                "error_output": error_output_before_exception
            }
        finally:
            # ã‚³ãƒ¼ãƒ‰å®Ÿè¡Œå±¥æ­´ã«è¿½åŠ 
            self.code_execution_history.append({"code": code_string, "result": result})
        
        return result

    async def get_screenshot_base64(self, direction: str | None = None, width: int = 960, height: int = 540) -> str | None:
        """
        æŒ‡å®šã•ã‚ŒãŸæ–¹è§’ã‚’å‘ã„ã¦ã‹ã‚‰ Prismarine Viewer ã®ã‚¹ã‚¯ãƒªãƒ¼ãƒ³ã‚·ãƒ§ãƒƒãƒˆã‚’å–å¾—ã—ã€
        Base64ã‚¨ãƒ³ã‚³ãƒ¼ãƒ‰ã•ã‚ŒãŸæ–‡å­—åˆ—ã¨ã—ã¦è¿”ã—ã¾ã™ã€‚

        Args:
            direction (str | None, optional): å‘ããŸã„æ–¹è§’ ('north', 'south', 'east', 'west', 'up', 'down' ãªã©)ã€‚Defaults to None.
            width (int): ã‚¹ã‚¯ãƒªãƒ¼ãƒ³ã‚·ãƒ§ãƒƒãƒˆã®å¹…ã€‚
            height (int): ã‚¹ã‚¯ãƒªãƒ¼ãƒ³ã‚·ãƒ§ãƒƒãƒˆã®é«˜ã•ã€‚

        Returns:
            str | None: Base64ã‚¨ãƒ³ã‚³ãƒ¼ãƒ‰ã•ã‚ŒãŸPNGç”»åƒæ–‡å­—åˆ—ã€‚ã‚¨ãƒ©ãƒ¼æ™‚ã¯Noneã€‚
        """
        await self.check_server_active() # ã‚µãƒ¼ãƒãƒ¼æŽ¥ç¶šç¢ºèªã¯å…ˆã«è¡Œã†
        self.bot.chat(f"ã‚¹ã‚¯ãƒªãƒ¼ãƒ³ã‚·ãƒ§ãƒƒãƒˆã‚’å–å¾—ã—ã¾ã™ã€‚(Direction: {direction or 'current'})")
        print(f"\033[34mCapturing screenshot from Prismarine Viewer (Direction: {direction or 'current'})...\033[0m")
        if not self.is_server_active():
            print("ã‚¨ãƒ©ãƒ¼: ãƒœãƒƒãƒˆãŒæŽ¥ç¶šã•ã‚Œã¦ã„ã¾ã›ã‚“ã€‚ã‚¹ã‚¯ãƒªãƒ¼ãƒ³ã‚·ãƒ§ãƒƒãƒˆã‚’å–å¾—ã§ãã¾ã›ã‚“ã€‚")
            return None

        if direction:
            if self.skills: # skills ã‚ªãƒ–ã‚¸ã‚§ã‚¯ãƒˆãŒåˆæœŸåŒ–ã•ã‚Œã¦ã„ã‚‹ã‹ç¢ºèª
                try:
                    look_result = await self.skills.look_at_direction(direction)
                    if not look_result or not look_result.get("success", False):
                         print(f"\033[93mWarning: Failed to look towards {direction}. Proceeding with current view. Message: {look_result.get('message', 'N/A') if look_result else 'N/A'}\033[0m")
                    await asyncio.sleep(1) # è¦–ç‚¹å¤‰æ›´ãŒåæ˜ ã•ã‚Œã‚‹ã®ã‚’å¾…ã¤
                except Exception as e:
                     print(f"\033[93mWarning: Error occurred while trying to look towards {direction}: {e}. Proceeding with current view.\033[0m")
            else:
                 print("\033[93mWarning: Skills object not initialized. Cannot change direction.\033[0m")

        url = f"http://localhost:{self.prismarine_viewer_port}"
        browser = None # finallyãƒ–ãƒ­ãƒƒã‚¯ã§å‚ç…§ã§ãã‚‹ã‚ˆã†åˆæœŸåŒ–
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": width, "height": height})

                await page.goto(url, wait_until="load", timeout=60000) # ã‚¿ã‚¤ãƒ ã‚¢ã‚¦ãƒˆã‚’60ç§’ã«å»¶é•·
                await page.wait_for_selector('canvas', timeout=30000) # canvasãŒç¾ã‚Œã‚‹ã¾ã§æœ€å¤§30ç§’å¾…æ©Ÿ
                # æç”»å®‰å®šã®ãŸã‚ååˆ†ãªå¾…æ©Ÿæ™‚é–“ã‚’ç¢ºä¿
                await asyncio.sleep(5) # å¿…è¦ã«å¿œã˜ã¦èª¿æ•´

                screenshot_bytes = await page.screenshot(type="png")
                await browser.close() # ã‚¹ã‚¯ãƒªãƒ¼ãƒ³ã‚·ãƒ§ãƒƒãƒˆå–å¾—å¾Œã™ãã«ãƒ–ãƒ©ã‚¦ã‚¶ã‚’é–‰ã˜ã‚‹
                browser = None # ã‚¯ãƒ­ãƒ¼ã‚ºã—ãŸã“ã¨ã‚’ç¤ºã™

                base64_image = base64.b64encode(screenshot_bytes).decode('utf-8')
                print("\033[34mScreenshot captured and encoded successfully.\033[0m")
                return base64_image

        except Exception as e:
            print(f"ã‚¹ã‚¯ãƒªãƒ¼ãƒ³ã‚·ãƒ§ãƒƒãƒˆã®å–å¾—ä¸­ã«ã‚¨ãƒ©ãƒ¼ãŒç™ºç”Ÿã—ã¾ã—ãŸ: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            if browser: # ã‚¨ãƒ©ãƒ¼ç™ºç”Ÿæ™‚ãªã©ã§ãƒ–ãƒ©ã‚¦ã‚¶ãŒé–‹ã„ãŸã¾ã¾ã®å ´åˆã«é–‰ã˜ã‚‹
                 print("ã‚¨ãƒ©ãƒ¼ç™ºç”Ÿã®ãŸã‚ã€ãƒ–ãƒ©ã‚¦ã‚¶ã‚’ã‚¯ãƒ­ãƒ¼ã‚ºã—ã¾ã™ã€‚")
                 await browser.close()

async def run_craft_example():
    """Skillsã‚¯ãƒ©ã‚¹ã®craft_itemsãƒ¡ã‚½ãƒƒãƒ‰ã‚’ä½¿ç”¨ã™ã‚‹ä¾‹"""
    # Discoveryã‚¤ãƒ³ã‚¹ã‚¿ãƒ³ã‚¹ã‚’ä½œæˆã—ã€Skillsã‚’åˆæœŸåŒ–
    discovery = Discovery()
    await discovery.check_server_and_join()
    skills = discovery.skills
    # ã‚µãƒ¼ãƒãƒ¼ãŒã‚¢ã‚¯ãƒ†ã‚£ãƒ–ã‹ç¢ºèª
    server_active = await discovery.check_server_active(timeout=15)
    if not server_active:
        print("ã‚µãƒ¼ãƒãƒ¼ã«æŽ¥ç¶šã§ãã¾ã›ã‚“ã€‚çµ‚äº†ã—ã¾ã™ã€‚")
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
            print(f"ã‚¨ãƒ©ãƒ¼ãŒç™ºç”Ÿã—ã¾ã—ãŸ: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    
    # ã‚µãƒ¼ãƒãƒ¼æŽ¥ç¶šãƒã‚§ãƒƒã‚¯ã ã‘ã‚’è¡Œã†ãƒ¢ãƒ¼ãƒ‰
    if len(sys.argv) > 1 and sys.argv[1] == "--check-server":
        async def check_server_connection():
            discovery = Discovery()
            print("Minecraftã‚µãƒ¼ãƒãƒ¼ã®æŽ¥ç¶šçŠ¶æ…‹ã‚’ç¢ºèªã—ã¦ã„ã¾ã™...")
            result = await discovery.check_server_active(timeout=15)
            if result:
                print("âœ… Minecraftã‚µãƒ¼ãƒãƒ¼ã¯ã‚¢ã‚¯ãƒ†ã‚£ãƒ–ã§ã™ï¼")
                # ã‚µãƒ¼ãƒãƒ¼ã®ãƒãƒ¼ã‚¸ãƒ§ãƒ³æƒ…å ±è¡¨ç¤º
                print(f"ã‚µãƒ¼ãƒãƒ¼ãƒãƒ¼ã‚¸ãƒ§ãƒ³: {discovery.bot.version}")
            else:
                print("âŒ Minecraftã‚µãƒ¼ãƒãƒ¼ã«æŽ¥ç¶šã§ãã¾ã›ã‚“ã§ã—ãŸ")
            return result
        
        asyncio.run(check_server_connection())
    else:
        # Skillsãƒ¢ãƒ¼ãƒ‰ã§å®Ÿè¡Œ
        print("Skillsãƒ¢ãƒ¼ãƒ‰ã§èµ·å‹•ã—ã¾ã™...")
        asyncio.run(run_craft_example())
