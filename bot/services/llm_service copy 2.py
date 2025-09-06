import logging
import asyncio
from typing import List, Dict, Optional
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from .base_service import BaseService
from ..api_client import LLMAPIClient
from ..config import Config
from ..TelegramFormatter import TelegramFormatter, get_sanitizer, clean_llm_output

logger = logging.getLogger(__name__)

class RateLimiter:
    """Simple token bucket rate limiter"""
    
    def __init__(self, max_tokens: int = 10, refill_rate: float = 1.0, refill_period: float = 60.0):
        """
        Args:
            max_tokens: Maximum tokens in bucket
            refill_rate: Tokens added per refill_period
            refill_period: Time in seconds between refills
        """
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        self.refill_period = refill_period
        self.tokens = max_tokens
        self.last_refill = time.time()
        self.lock = asyncio.Lock()
        
    
    async def try_consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if successful, False if rate limited."""
        async with self.lock:
            now = time.time()
            
            # Refill tokens based on time passed
            time_passed = now - self.last_refill
            tokens_to_add = (time_passed / self.refill_period) * self.refill_rate
            self.tokens = min(self.max_tokens, self.tokens + tokens_to_add)
            self.last_refill = now
            
            # Try to consume
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False
    
    async def get_retry_after(self) -> float:
        """Get seconds until next token is available"""
        async with self.lock:
            if self.tokens >= 1:
                return 0
            tokens_needed = 1 - self.tokens
            return (tokens_needed / self.refill_rate) * self.refill_period

class LLMService(BaseService):
    def __init__(self):
        self.api_client = None
        self.chat_sessions: Dict[int, str] = {}
        
        # Locks for thread-safe session management
        self._session_locks: Dict[int, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

        # Memory control
        self.disable_memory: Dict[int, bool] = {}
        self.enable_memory: Dict[int, bool] = {} 
        
        # Global defaults
        self.has_history = True
        self.has_history_in_groups = False

    @property
    def name(self) -> str:
        return "LLM Service"

    @property
    def description(self) -> str:
        return "Custom LLM integration for answering questions"

    def get_handlers(self) -> List[tuple]:
        return [
            (CommandHandler("ask", self.ask_command), self.ask_command),
            (CommandHandler("new_chat", self.new_chat_command), self.new_chat_command),
            (CommandHandler("end_chat", self.end_chat_command), self.end_chat_command),
            (CommandHandler("disable_memory", self.disable_memory_command), self.disable_memory_command),
            (CommandHandler("enable_memory", self.enable_memory_command), self.enable_memory_command),
            (MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message), self.handle_message),
        ]

    async def _get_chat_lock(self, chat_id: int) -> asyncio.Lock:
        """Get or create a lock for a specific chat"""
        async with self._global_lock:
            if chat_id not in self._session_locks:
                self._session_locks[chat_id] = asyncio.Lock()
            return self._session_locks[chat_id]

    # ---------------------------
    # Commands
    # ---------------------------

    async def new_chat_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /new_chat command to start a fresh conversation"""
        chat_id = update.effective_chat.id
        is_private = self._is_private_chat(update)

        # Use chat-specific lock for session operations
        chat_lock = await self._get_chat_lock(chat_id)
        async with chat_lock:
            try:
                # If memory is not enabled for this chat, inform and bail early
                if not self._memory_enabled_for_chat(chat_id, is_private):
                    # If there is an existing session, try to end it to avoid leaks
                    if chat_id in self.chat_sessions:
                        async with LLMAPIClient(Config.API_BASE_URL, Config.API_USERNAME, Config.API_PASSWORD) as client:
                            await client.delete_session(self.chat_sessions[chat_id])
                        del self.chat_sessions[chat_id]
                    await update.message.reply_text(
                        "ℹ️ Memory is disabled for this chat by current settings. "
                        "Use /enable_memory to re-enable (if allowed by global defaults)."
                    )
                    return

                async with LLMAPIClient(Config.API_BASE_URL, Config.API_USERNAME, Config.API_PASSWORD) as client:
                    # Delete old session if exists
                    if chat_id in self.chat_sessions:
                        await client.delete_session(self.chat_sessions[chat_id])
                        logger.info(f"Deleted old session for chat {chat_id}")

                    # Create new session
                    new_session_id = await client.create_session()
                    if new_session_id:
                        self.chat_sessions[chat_id] = new_session_id
                        await update.message.reply_text(
                            "✅ Started a new chat session! Your conversation history has been cleared."
                        )
                        logger.info(f"Created new session {new_session_id} for chat {chat_id}")
                    else:
                        await update.message.reply_text("❌ Failed to create a new chat session. Please try again.")
            except Exception as e:
                logger.error(f"Error creating new chat session: {e}")
                await update.message.reply_text("❌ Error creating new chat session. Please try again.")

    async def end_chat_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /end_chat command to end the current conversation"""
        chat_id = update.effective_chat.id

        # Use chat-specific lock for session operations
        chat_lock = await self._get_chat_lock(chat_id)
        async with chat_lock:
            if chat_id not in self.chat_sessions:
                await update.message.reply_text("ℹ️ No active chat session to end.")
                return

            try:
                async with LLMAPIClient(Config.API_BASE_URL, Config.API_USERNAME, Config.API_PASSWORD) as client:
                    session_id = self.chat_sessions[chat_id]
                    success = await client.delete_session(session_id)

                    if success:
                        del self.chat_sessions[chat_id]
                        await update.message.reply_text(
                            "✅ Chat session ended. Your conversation history has been cleared."
                        )
                        logger.info(f"Ended session {session_id} for chat {chat_id}")
                    else:
                        await update.message.reply_text(
                            "⚠️ Session ended locally, but there might have been an issue on the server."
                        )
            except Exception as e:
                logger.error(f"Error ending chat session: {e}")
                # Remove from local storage even if server deletion failed
                if chat_id in self.chat_sessions:
                    del self.chat_sessions[chat_id]
                await update.message.reply_text("✅ Chat session ended locally.")

    async def disable_memory_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Disable memory for this specific chat."""
        chat_id = update.effective_chat.id
        
        # Use chat-specific lock for session operations
        chat_lock = await self._get_chat_lock(chat_id)
        async with chat_lock:
            self.disable_memory[chat_id] = True
            self.enable_memory.pop(chat_id, None)

            # Clean up existing session
            if chat_id in self.chat_sessions:
                try:
                    async with LLMAPIClient(Config.API_BASE_URL, Config.API_USERNAME, Config.API_PASSWORD) as client:
                        await client.delete_session(self.chat_sessions[chat_id])
                    del self.chat_sessions[chat_id]
                except Exception as e:
                    logger.warning(f"Failed to clean up session on disable_memory for chat {chat_id}: {e}")

            await update.message.reply_text("🚫 Memory has been disabled for this chat (sessionless mode).")

    async def enable_memory_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Re-enable memory for this chat (overrides group/global restrictions)."""
        chat_id = update.effective_chat.id
        if chat_id in self.disable_memory:
            del self.disable_memory[chat_id]
        self.enable_memory[chat_id] = True 
        await update.message.reply_text(
            "✅ Memory is now enabled for this chat (overrides default restrictions)."
        )

    async def ask_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /ask command"""
        if not context.args:
            await update.message.reply_text(
                "Please provide a question after the /ask command.\nExample: /ask What is the capital of France?"
            )
            return

        question = " ".join(context.args)

        # If this is a reply to another message, extract context
        context_message = None
        if update.message.reply_to_message:
            replied_message = update.message.reply_to_message
            context_message = self._extract_message_content(replied_message)

        # Process question asynchronously without blocking other requests
        asyncio.create_task(self._process_question(update, question, context_message))

    # ---------------------------
    # Message handler
    # ---------------------------

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle regular text messages"""
        question = update.message.text

        # Ignore free-form messages in groups (avoid spam); commands still work in groups.
        if not self._is_private_chat(update):
            return

        # Context if replying to a message
        context_message = None
        if update.message.reply_to_message and self._is_private_chat(update):
            replied_message = update.message.reply_to_message
            context_message = self._extract_message_content(replied_message)

        # Process question asynchronously without blocking other requests
        asyncio.create_task(self._process_question(update, question, context_message))

    # ---------------------------
    # Helpers
    # ---------------------------

    def _is_private_chat(self, update: Update) -> bool:
        """Check if the chat is a private chat (not a group or channel)"""
        return update.effective_chat.type == "private"

    def _extract_message_content(self, message) -> str:
        """Extract content from a replied-to message"""
        content_parts = []

        # Add sender information (if available)
        sender_info = ""
        if message.from_user:
            if message.from_user.username:
                sender_info = f"@{message.from_user.username}"
            else:
                sender_info = message.from_user.first_name or "Unknown User"

        if sender_info:
            content_parts.append(f"[Message from {sender_info}]")

        # Add text content
        if message.text:
            content_parts.append(message.text)

        # Add caption if it's a media message with caption
        elif message.caption:
            media_type = "media"
            if message.photo:
                media_type = "photo"
            elif message.video:
                media_type = "video"
            elif message.document:
                media_type = "document"
            elif message.audio:
                media_type = "audio"

            content_parts.append(f"[{media_type.title()} with caption: {message.caption}]")

        # Handle media without caption
        elif message.photo:
            content_parts.append("[Photo message]")
        elif message.video:
            content_parts.append("[Video message]")
        elif message.document:
            doc_name = message.document.file_name or "Unknown document"
            content_parts.append(f"[Document: {doc_name}]")
        elif message.audio:
            content_parts.append("[Audio message]")
        elif message.voice:
            content_parts.append("[Voice message]")
        elif message.sticker:
            content_parts.append("[Sticker message]")
        else:
            content_parts.append("[Message content not available]")

        return " ".join(content_parts)

    def _memory_enabled_for_chat(self, chat_id: int, is_private: bool) -> bool:
        """Determine if memory should be used for this chat based on all rules."""
        # Per-chat disable always wins
        if self.disable_memory.get(chat_id, False):
            return False
        # Global off switch
        if not self.has_history:
            return False
        # Per-chat force-enable overrides group restriction
        if self.enable_memory.get(chat_id, False):
            return True
        # Otherwise, fall back to defaults
        if not is_private and not self.has_history_in_groups:
            return False
        return True

    async def _get_or_create_session(self, chat_id: int, is_private: bool) -> Optional[str]:
        """Get existing session or create a new one for the chat, if memory is enabled."""
        # If memory shouldn't be used for this chat, return None (sessionless)
        if not self._memory_enabled_for_chat(chat_id, is_private):
            return None

        # Use chat-specific lock only for session creation, not for reading
        if chat_id in self.chat_sessions:
            return self.chat_sessions[chat_id]

        # Need to create a new session - use lock to prevent race conditions
        chat_lock = await self._get_chat_lock(chat_id)
        async with chat_lock:
            # Double-check after acquiring lock (another coroutine might have created it)
            if chat_id in self.chat_sessions:
                return self.chat_sessions[chat_id]

            try:
                async with LLMAPIClient(Config.API_BASE_URL, Config.API_USERNAME, Config.API_PASSWORD) as client:
                    session_id = await client.create_session()
                    if session_id:
                        self.chat_sessions[chat_id] = session_id
                        logger.info(f"Created new session {session_id} for chat {chat_id}")
                        return session_id
            except Exception as e:
                logger.error(f"Error creating session for chat {chat_id}: {e}")

        return None

    async def _process_question(self, update: Update, question: str, context_message: str = None) -> None:
        """Process a question using the LLM API"""
        try:
            await update.message.chat.send_action(action="typing")
            chat_id = update.effective_chat.id
            is_private = self._is_private_chat(update)

            # Determine session ID based on rules (this handles locking internally)
            session_id = await self._get_or_create_session(chat_id, is_private)

            # If memory is enabled for this chat but no session could be created, inform the user
            if self._memory_enabled_for_chat(chat_id, is_private) and not session_id:
                await update.message.reply_text(
                    "❌ Failed to initialize chat session. Please try /new_chat command."
                )
                return

            # Construct the full query with context if available
            full_query = question
            if context_message:
                full_query = f"Context from previous message:\n{context_message}\n\nQuestion: {question}"
                logger.info(f"Processing question with context. Context: {context_message[:100]}...")

            async with LLMAPIClient(Config.API_BASE_URL, Config.API_USERNAME, Config.API_PASSWORD) as client:
                response = await asyncio.wait_for(
                    client.query(full_query, session_id=session_id),
                    timeout=120,
                )

                if response:
                    answer = response.get("answer", response.get("response", str(response)))
                    if isinstance(answer, dict):
                        answer = str(answer)
                    answer = clean_llm_output(answer)

                    await update.message.reply_text(answer, parse_mode="HTML")
                else:
                    await update.message.reply_text(
                        "Sorry, no response received from the model. Please try again shortly."
                    )

        except asyncio.TimeoutError:
            logger.warning("Timeout during LLM API query")
            await update.message.reply_text("The server took too long to respond. Please try again in a moment.")

        except Exception as e:
            logger.error(f"Error processing question: {e}")
            await update.message.reply_text(
                "An unexpected error occurred while processing your request. Please try again later."
            )