import asyncio
import logging
import uuid
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

from telegram import (
    Update,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ContextTypes,
    InlineQueryHandler,
    CallbackQueryHandler,
)
from .base_service import BaseService
from ..api_client import LLMAPIClient
from ..config import Config
from ..TelegramFormatter import clean_llm_output

logger = logging.getLogger(__name__)


@dataclass
class QueryData:
    """Data structure to hold all information for a single query."""
    query_text: str
    task: Optional[asyncio.Task] = None
    edit_target: Optional[Dict[str, Any]] = None


class InlineService(BaseService):
    def __init__(self):
        self.api_client = None
        # Use a single dictionary to store all query data
        # Each result_id maps to a QueryData object containing all related info
        self.active_queries: Dict[str, QueryData] = {}
        # Lock to prevent race conditions when accessing active_queries
        self._queries_lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "Inline Query Service"

    @property
    def description(self) -> str:
        return "Answer questions directly in chats using @sharif_EE_chatbot"

    def get_handlers(self) -> List[tuple]:
        return [
            (InlineQueryHandler(self.inline_query), self.inline_query),
            (CallbackQueryHandler(self.callback_query), self.callback_query),
        ]

    # ---------------------------
    # Inline query handling
    # ---------------------------
    async def inline_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle inline queries from users.

        Important: we do NOT call LLM here. We instead present a single 'Ask question' result.
        """
        query = (update.inline_query.query or "").strip()
        results = []

        if not query:
            # show help / hint result
            results.append(
                InlineQueryResultArticle(
                    id=str(uuid.uuid4()),
                    title="🤖 Ask me anything!",
                    description="Type your question after @sharif_EE_chatbot to get an AI-powered answer",
                    input_message_content=InputTextMessageContent(
                        message_text=(
                            f"💡 **How to use:**\n"
                            f"Type `@{context.bot.username} your question` in any chat.\n\n"
                            f"**Example:** `@{context.bot.username} What is the capital of France?`"
                        ),
                        parse_mode="Markdown",
                    ),
                )
            )
        else:
            # Create a unique id for this inline result
            result_id = str(uuid.uuid4())
            
            # Store query data thread-safely
            async with self._queries_lock:
                self.active_queries[result_id] = QueryData(query_text=query)

            # Message content inserted when user selects this inline result.
            inserted_text = (
                f"❓ <b>Question:</b>\n {query}\n\n"
                f"🤖 <b>Answer:</b>\n (press the button below to send the question)"
            )

            # Inline keyboard: user must press this to actually run the query.
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text="Ask question (send query)",
                            callback_data=f"ask:{result_id}",
                        )
                    ]
                ]
            )

            results.append(
                InlineQueryResultArticle(
                    id=result_id,
                    title="💬 Ask question",
                    description=f"Send your question to the AI: {query[:60]}{'...' if len(query) > 60 else ''}",
                    input_message_content=InputTextMessageContent(
                        message_text=inserted_text, parse_mode="HTML"
                    ),
                    reply_markup=keyboard,
                )
            )

        try:
            await update.inline_query.answer(results, cache_time=1, is_personal=True)
        except Exception as e:
            logger.exception(f"Failed to answer inline query: {e}")

    # ---------------------------
    # Callback query handling
    # ---------------------------
    async def callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle callback queries from the inline message keyboard.

        Expected callback_data format: "ask:<result_id>"
        """
        query = update.callback_query
        if not query:
            return

        # Acknowledge quickly so user doesn't see a spinner for long
        await query.answer()

        data = query.data or ""
        if not data.startswith("ask:"):
            # ignore other callbacks
            return

        result_id = data.split(":", 1)[1]
        
        # Get query data thread-safely
        async with self._queries_lock:
            query_data = self.active_queries.get(result_id)
        
        if not query_data:
            # expired or missing
            try:
                await query.edit_message_text(text="⚠️ This query is no longer available. Please try again.")
            except Exception:
                await context.bot.send_message(
                    chat_id=query.from_user.id,
                    text="⚠️ This query is no longer available. Please open inline mode again and retry.",
                )
            return

        original_question = query_data.query_text

        # At this point we can edit the message via query.edit_message_text
        processing_text = f"❓ <b>Question:</b>\n {original_question}\n\n🤖 <b>Answer:</b>\n ⏳ Processing..."
        try:
            await query.edit_message_text(text=processing_text, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"query.edit_message_text failed: {e}")

            # Fallback editing logic
            if query.message:
                try:
                    await context.bot.edit_message_text(
                        text=processing_text,
                        chat_id=query.message.chat_id,
                        message_id=query.message.message_id,
                        parse_mode="HTML",
                    )
                except Exception as e2:
                    logger.exception(f"Fallback edit using chat_id/message_id also failed: {e2}")
                    await context.bot.send_message(
                        chat_id=query.from_user.id,
                        text="⚠️ Could not edit the message to show processing state. Please try directly with the bot.",
                    )
                    return
            elif query.inline_message_id:
                try:
                    await context.bot.edit_message_text(
                        text=processing_text,
                        inline_message_id=query.inline_message_id,
                        parse_mode="HTML",
                    )
                except Exception as e3:
                    logger.exception(f"Fallback edit using inline_message_id failed: {e3}")
                    await context.bot.send_message(
                        chat_id=query.from_user.id,
                        text="⚠️ Could not edit the message to show processing state. Please try directly with the bot.",
                    )
                    return
            else:
                await context.bot.send_message(
                    chat_id=query.from_user.id,
                    text="⚠️ Could not access the message to edit. Please try directly with the bot.",
                )
                return

        # Determine edit target for background task
        if query.message:
            target = {"chat_id": query.message.chat_id, "message_id": query.message.message_id}
        elif query.inline_message_id:
            target = {"inline_message_id": query.inline_message_id}
        else:
            await context.bot.send_message(
                chat_id=query.from_user.id,
                text="⚠️ Could not determine where to edit the message. Please try directly with the bot.",
            )
            return

        # Update query data with edit target and start background task
        task = asyncio.create_task(
            self._run_query_and_edit_message(result_id, original_question, target, context)
        )
        
        # Store task and target thread-safely
        async with self._queries_lock:
            if result_id in self.active_queries:  # Double-check it still exists
                self.active_queries[result_id].task = task
                self.active_queries[result_id].edit_target = target

    # ---------------------------
    # LLM runner + editor
    # ---------------------------
    async def _run_query_and_edit_message(
        self, 
        result_id: str, 
        question: str, 
        target: Dict[str, Any], 
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Run the LLM query and edit the message when the response arrives."""
        try:
            # Query LLM (longer timeout here)
            answer_data = None
            try:
                async with LLMAPIClient(Config.API_BASE_URL, Config.API_USERNAME, Config.API_PASSWORD) as client:
                    answer_data = await asyncio.wait_for(client.query(question), timeout=120)
            except asyncio.TimeoutError:
                raise
            except Exception as e:
                logger.exception(f"Error while querying LLM for question `{question[:80]}`: {e}")
                raise

            # Extract answer text
            answer_text = self._extract_answer_text(answer_data)
            answer_text = clean_llm_output(answer_text)

            # Format final message
            final_text = f"❓ <b>Question:</b>\n {question}\n\n🤖 <b>Answer:</b>\n {answer_text}"
            processing_time = self._extract_processing_time(answer_data)
            if processing_time:
                final_text += f"\n\n⚡ *Processed in {processing_time:.2f} seconds*"

            # Edit the message using the target
            try:
                if "inline_message_id" in target:
                    await context.bot.edit_message_text(
                        text=final_text, 
                        inline_message_id=target["inline_message_id"], 
                        parse_mode="HTML"
                    )
                else:
                    await context.bot.edit_message_text(
                        text=final_text,
                        chat_id=target.get("chat_id"),
                        message_id=target.get("message_id"),
                        parse_mode="HTML",
                    )
            except Exception as e:
                logger.exception(f"Failed to edit message with final answer: {e}")
                # Fallback: send a new message if editing failed
                chat_id = target.get("chat_id")
                if chat_id:
                    try:
                        await context.bot.send_message(chat_id=chat_id, text=final_text, parse_mode="HTML")
                    except Exception as e2:
                        logger.exception(f"Fallback message send also failed: {e2}")
                else:
                    logger.warning("No chat_id available to send fallback message with answer.")

        except asyncio.TimeoutError:
            timeout_text = f"❓ <b>Question:</b> {question}\n\n⏰ **Request timed out. Please try again.**"
            await self._safe_edit_message(target, timeout_text, context)
            
        except Exception as e:
            logger.exception(f"Unhandled exception in _run_query_and_edit_message: {e}")
            error_text = f"❓ <b>Question:</b> {question}\n\n❌ **An error occurred while processing your request.**"
            await self._safe_edit_message(target, error_text, context)
            
        finally:
            # Clean up this specific query data
            await self._cleanup_query(result_id)

    async def _safe_edit_message(self, target: Dict[str, Any], text: str, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Safely edit a message with fallback options."""
        try:
            if "inline_message_id" in target:
                await context.bot.edit_message_text(
                    text=text, 
                    inline_message_id=target["inline_message_id"], 
                    parse_mode="HTML"
                )
            else:
                await context.bot.edit_message_text(
                    text=text,
                    chat_id=target.get("chat_id"),
                    message_id=target.get("message_id"),
                    parse_mode="HTML",
                )
        except Exception as e:
            logger.warning(f"Failed to edit message: {e}")
            # Fallback: send new message if possible
            chat_id = target.get("chat_id")
            if chat_id:
                try:
                    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
                except Exception as e2:
                    logger.exception(f"Fallback message send failed: {e2}")

    async def _cleanup_query(self, result_id: str) -> None:
        """Clean up data for a specific query."""
        async with self._queries_lock:
            query_data = self.active_queries.pop(result_id, None)
            if query_data and query_data.task and query_data.task.done():
                try:
                    # Retrieve any exception from the task
                    _ = query_data.task.result()
                except Exception:
                    # Task completed with exception, but we don't need to handle it here
                    pass

    # ---------------------------
    # Helpers
    # ---------------------------
    def _extract_answer_text(self, response_data) -> str:
        """Extract the actual answer text from API response."""
        if isinstance(response_data, dict) and "response" in response_data:
            return response_data["response"]
        elif isinstance(response_data, str):
            return response_data
        else:
            return str(response_data)

    def _extract_processing_time(self, response_data) -> Optional[float]:
        """Extract processing time from API response."""
        if isinstance(response_data, dict) and "processingtime" in response_data:
            return response_data["processingtime"]
        return None