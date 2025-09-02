import logging
import os
from bot.khoda_bot import KhodaBot
from bot.services import LLMService, PingService, ReportService, InlineService

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename="app.log",
    filemode="w",
)
logger = logging.getLogger(__name__)

def main():
    # Get bot token from environment variable
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
    
    # Initialize services
    services = [LLMService(), PingService(), ReportService(), InlineService()]
    
    # Create and start bot with services
    bot = KhodaBot(
        token=bot_token,
        services=services
    )
    
    logger.info("Starting bot...")
    bot.run()

if __name__ == "__main__":
    main()