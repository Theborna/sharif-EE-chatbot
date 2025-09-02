
# Khoda Bot - Modular Telegram Bot with Custom LLM

A modular Telegram bot built in Python that integrates with a custom LLM API.

## Features

- **Modular Architecture**: Easy to add new services and handlers
- **Custom LLM Integration**: Connects to your FastAPI LLM service
- **Session Management**: Handles API sessions automatically
- **Built-in Services**:
  - LLM Question Answering
  - Ping/Pong response time testing
  - User report system
- **Error Handling**: Robust error handling and logging
- **Async/Await**: Modern async Python for better performance

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment**:
   - Copy `.env.example` to `.env`
   - Add your Telegram bot token from @BotFather

3. **Update API Configuration**:
   - Edit `bot/config.py` to match your API settings
   - Update API credentials if needed

4. **Run the Bot**:
   ```bash
   python main.py
   ```

## Adding New Services

1. Create a new service class inheriting from `BaseService`
2. Implement required methods (`get_handlers`, `name`, `description`)
3. Add your service to the main.py services list

Example:
```python
from bot.services.base_service import BaseService

class MyCustomService(BaseService):
    @property
    def name(self) -> str:
        return "My Service"
    
    @property  
    def description(self) -> str:
        return "Does something awesome"
        
    def get_handlers(self) -> List[tuple]:
        return [
            (CommandHandler("mycmd", self.my_handler), self.my_handler)
        ]
    
    async def my_handler(self, update, context):
        await update.message.reply_text("Hello from my service!")
```

## Available Commands

- `/start`, `/help`, `/hi` - Show welcome message
- `/ping` - Test bot response time  
- `/ask <question>` - Ask the LLM a question
- `/report <message>` - Send a report to admins
- Send any text message to chat with the LLM

## Project Structure

```
├── main.py                 # Entry point
├── bot/
│   ├── __init__.py
│   ├── khoda_bot.py       # Main bot class
│   ├── config.py          # Configuration
│   ├── api_client.py      # LLM API client
│   └── services/          # Service modules
│       ├── __init__.py
│       ├── base_service.py
│       ├── llm_service.py
│       ├── ping_service.py
│       └── report_service.py
├── requirements.txt
├── .env.example
└── README.md
```