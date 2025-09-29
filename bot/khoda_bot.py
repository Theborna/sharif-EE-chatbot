import logging
import json
import os
from datetime import datetime
from typing import List, Dict, Any
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram import Update
from .services.base_service import BaseService
from .config import Config
from .TelegramFormatter import TelegramFormatter
from .statistics import StatsTracker

logger = logging.getLogger(__name__)

class KhodaBot:
    def __init__(self, token: str, services: List[BaseService] = None, stats_file: str = "user_stats.json"):
        self.services = services or []
        self.application = Application.builder().token(token).build()
        self.stats_tracker = StatsTracker(stats_file)
        self._setup_handlers()

    def _setup_handlers(self):
        self.application.add_handler(CommandHandler(["start", "help", "hi"], self.start_handler))
        
        # Add message handler to track all activity in background
        self.application.add_handler(MessageHandler(filters.ALL, self._track_message), group=-1)
        
        for service in self.services:
            for handler, service_name in service.get_handlers():
                # Wrap service handlers to track usage
                wrapped_handler = self._wrap_handler(handler, service_name)
                self.application.add_handler(wrapped_handler)
                logger.info(f"Added handler for service: {service.name}")

    def _wrap_handler(self, original_handler, service_name: str):
        """Wrap handlers to track service usage"""
        from telegram.ext import CommandHandler, MessageHandler, InlineQueryHandler
        
        original_callback = original_handler.callback
        
        async def wrapped_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
            # Track service usage in background
            if update.effective_user:
                self.stats_tracker.track_user(
                    user_id=update.effective_user.id,
                    username=update.effective_user.username,
                    first_name=update.effective_user.first_name,
                    service_name=service_name
                )
            
            return await original_callback(update, context)
        
        # Create new handler with wrapped callback based on handler type
        if isinstance(original_handler, CommandHandler):
            return CommandHandler(original_handler.commands, wrapped_callback)
        elif isinstance(original_handler, MessageHandler):
            return MessageHandler(original_handler.filters, wrapped_callback)
        elif isinstance(original_handler, InlineQueryHandler):
            return InlineQueryHandler(wrapped_callback, pattern=original_handler.pattern)
        else:
            # For other handler types, modify callback directly
            original_handler.callback = wrapped_callback
            return original_handler

    async def _track_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Track all messages in background"""
        if update.effective_user:
            self.stats_tracker.track_user(
                user_id=update.effective_user.id,
                username=update.effective_user.username,
                first_name=update.effective_user.first_name
            )

    async def start_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        service_list = [f"• {s.description}" for s in self.services]
        services_text = "\n".join(service_list) if service_list else "• No additional services loaded"
        msg = Config.WELCOME_TEXT
        msg = TelegramFormatter.escape_special_for_telegram(msg)
        await update.message.reply_text(msg, parse_mode="HTML")

    def run(self):
        total_users = len(self.stats_tracker.stats)
        logger.info(f"Initializing bot with {total_users} tracked users...")
        logger.info("Starting bot...")
        self.application.run_polling()