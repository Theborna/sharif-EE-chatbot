import logging
from typing import List
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import Update
from .services.base_service import BaseService
from .config import Config
from .TelegramFormatter import TelegramFormatter

logger = logging.getLogger(__name__)

class KhodaBot:
    def __init__(self, token: str, services: List[BaseService] = None):
        self.services = services or []
        self.application = Application.builder().token(token).build()
        self._setup_handlers()

    def _setup_handlers(self):
        self.application.add_handler(CommandHandler(["start", "help", "hi"], self.start_handler))
        for service in self.services:
            for handler, _ in service.get_handlers():
                self.application.add_handler(handler)
                logger.info(f"Added handler for service: {service.name}")

    async def start_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        service_list = [f"• {s.description}" for s in self.services]
        services_text = "\n".join(service_list) if service_list else "• No additional services loaded"
        # msg = f"{Config.WELCOME_TEXT}\n\n🔧 **Loaded Services:**\n{services_text}"
        msg = Config.WELCOME_TEXT
        msg = TelegramFormatter.escape_special_for_telegram(msg)
        await update.message.reply_text(msg, parse_mode="HTML")

    def run(self):
        logger.info("Initializing and starting bot...")
        self.application.run_polling()
