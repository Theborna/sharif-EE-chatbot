import time
import asyncio
from typing import List
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from .base_service import BaseService

class PingService(BaseService):
    @property
    def name(self) -> str:
        return "Ping Service"
    
    @property
    def description(self) -> str:
        return "Check bot response time"
    
    def get_handlers(self) -> List[tuple]:
        return [
            (CommandHandler("ping", self.ping_command), self.ping_command)
        ]
    
    async def ping_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /ping command"""
        start_time = time.time()
        
        # Send initial message
        message = await update.message.reply_text("Pinging...")
        
        # Calculate response time
        end_time = time.time()
        ping_time = round((end_time - start_time) * 1000, 2)  # Convert to milliseconds
        
        # Edit message with ping result
        await message.edit_text(f"🏓 PONG!!!\n⏱️ Response time: {ping_time}ms")