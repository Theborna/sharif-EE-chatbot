import os
import logging
from datetime import datetime
from typing import List
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from .base_service import BaseService
from ..config import Config

logger = logging.getLogger(__name__)

class ReportService(BaseService):
    def __init__(self):
        Config.ensure_directories()

    @property
    def name(self) -> str:
        return "Report Service"

    @property
    def description(self) -> str:
        return "Allow users to send reports to administrators"

    def get_handlers(self) -> List[tuple]:
        return [
            (CommandHandler("report", self.report_command), self.report_command)
        ]

    async def report_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /report command"""
        if not context.args:
            await update.message.reply_text(
                "Please provide your report message after /report command.\n"
                "Example: /report I found a bug in the bot"
            )
            return

        # Get user info and message
        user = update.effective_user
        username = user.username or f"user_{user.id}"
        report_message = " ".join(context.args)

        # Get replied-to message text (if any)
        replied_msg_text = None
        if update.message.reply_to_message:
            replied_msg = update.message.reply_to_message
            # Use text or caption (for media) if available
            replied_msg_text = replied_msg.text or replied_msg.caption or "<non-text message>"

        # Create report text including replied-to message if present
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report_text = f"[{timestamp}] User: @{username} (ID: {user.id})\nReport: {report_message}\n"
        if replied_msg_text:
            report_text += f"Replied to message: {replied_msg_text}\n"
        report_text += "\n"

        try:
            # Save report to file
            report_file = os.path.join(
                Config.REPORTS_DIR,
                f"report_{datetime.now().strftime('%m-%d-%Y')}.txt"
            )

            with open(report_file, "a", encoding="utf-8") as f:
                f.write(report_text)

            await update.message.reply_text("✅ Report sent successfully! Thank you for your feedback.")
            logger.info(f"Report saved from user {username}: {report_message} (Replied to: {replied_msg_text})")

        except Exception as e:
            logger.error(f"Failed to save report: {e}")
            await update.message.reply_text("❌ Failed to save report. Please try again later.")
