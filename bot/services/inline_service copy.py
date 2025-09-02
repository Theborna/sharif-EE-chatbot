import asyncio
import logging
import uuid
from typing import List, Dict, Optional, Any

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

logger = logging.getLogger(__name__)


class InlineService(BaseService):
    def __init__(self):
        self.api_client = None
        # map temporary result_id -> original query text
        self.pending_queries: Dict[str, str] = {}
        # map result_id -> asyncio.Task (optional, to cancel if needed)
        self.running_tasks: Dict[str, asyncio.Task] = {}
        # map result_id -> edit target info (either {'inline_message_id': str} or {'chat_id': int, 'message_id': int})
        self.edit_targets: Dict[str, Dict[str, Any]] = {}

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
                        ,
                    ),
                )
            )
        else:
            # Create a short unique id for this inline result
            result_id = str(uuid.uuid4())
            # store the query so we can retrieve it later when callback is pressed
            self.pending_queries[result_id] = query

            # Message content inserted when user selects this inline result.
            inserted_text = (
                f"❓ **Question:**\n {query}\n\n"
                f"🤖 **Answer:**\n (press the button below to send the question)"
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
                        message_text=inserted_text, 
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
        original_question = self.pending_queries.get(result_id)
        if not original_question:
            # expired or missing
            # We can attempt to edit the message if possible, otherwise inform the user via a private message
            try:
                await query.edit_message_text(text="⚠️ This query is no longer available. Please try again.")
            except Exception:
                await context.bot.send_message(
                    chat_id=query.from_user.id,
                    text="⚠️ This query is no longer available. Please open inline mode again and retry.",
                )
            return

        # At this point we can edit the message via query.edit_message_text irrespective of message vs inline_message_id
        processing_text = f"❓ **Question:**\n {original_question}\n\n🤖 **Answer:**\n \"Processing\""
        try:
            # Use the convenience method on CallbackQuery to edit whichever message this callback came from.
            # This works whether it's a normal message (query.message) or an inline message (query.inline_message_id).
            await query.edit_message_text(text=processing_text, )
        except Exception as e:
            # If edit via query fails, attempt fallback to explicit edit by inline_message_id or chat/message_id.
            logger.warning(f"query.edit_message_text failed: {e}")

            # If we have a message object, try to use it
            if query.message:
                try:
                    await context.bot.edit_message_text(
                        text=processing_text,
                        chat_id=query.message.chat_id,
                        message_id=query.message.message_id,
                        ,
                    )
                except Exception as e2:
                    logger.exception(f"Fallback edit using chat_id/message_id also failed: {e2}")
                    # last-resort private message
                    await context.bot.send_message(
                        chat_id=query.from_user.id,
                        text="⚠️ Could not edit the message to show processing state. Please try directly with the bot.",
                    )
                    return
            # If inline_message_id exists, try that
            elif query.inline_message_id:
                try:
                    await context.bot.edit_message_text(
                        text=processing_text,
                        inline_message_id=query.inline_message_id,
                        ,
                    )
                except Exception as e3:
                    logger.exception(f"Fallback edit using inline_message_id failed: {e3}")
                    await context.bot.send_message(
                        chat_id=query.from_user.id,
                        text="⚠️ Could not edit the message to show processing state. Please try directly with the bot.",
                    )
                    return
            else:
                # no way to edit
                await context.bot.send_message(
                    chat_id=query.from_user.id,
                    text="⚠️ Could not access the message to edit. Please try directly with the bot.",
                )
                return

        # Determine edit target to use later in background task
        if query.message:
            target = {"chat_id": query.message.chat_id, "message_id": query.message.message_id}
        elif query.inline_message_id:
            target = {"inline_message_id": query.inline_message_id}
        else:
            # This should not happen because we edited above, but guard anyway
            await context.bot.send_message(
                chat_id=query.from_user.id,
                text="⚠️ Could not determine where to edit the message. Please try directly with the bot.",
            )
            return

        # Save target so background task can edit the same message
        self.edit_targets[result_id] = target

        # Run the LLM query in background and schedule edit when done
        task = asyncio.create_task(
            self._run_query_and_edit_message(result_id, original_question, context)
        )
        # keep track so it can be cancelled if desired
        self.running_tasks[result_id] = task

    # ---------------------------
    # LLM runner + editor
    # ---------------------------
    async def _run_query_and_edit_message(self, result_id: str, question: str, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Run the LLM query and edit the message when the response arrives."""
        target = self.edit_targets.get(result_id, {})
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

            # Format final message
            final_text = f"❓ **Question:**\n {question}\n\n🤖 **Answer:**\n {answer_text}"
            processing_time = self._extract_processing_time(answer_data)
            if processing_time:
                final_text += f"\n\n⚡ *Processed in {processing_time:.2f} seconds*"

            # Edit the message using the saved target
            try:
                if "inline_message_id" in target:
                    await context.bot.edit_message_text(
                        text=final_text, inline_message_id=target["inline_message_id"], 
                    )
                else:
                    await context.bot.edit_message_text(
                        text=final_text,
                        chat_id=target.get("chat_id"),
                        message_id=target.get("message_id"),
                        ,
                    )
            except Exception as e:
                logger.exception(f"Failed to edit message with final answer: {e}")
                # If editing failed, fallback: try to send a follow-up message to the user
                # If we have a chat_id, send there, otherwise send to the original query author via PM
                chat_id = target.get("chat_id")
                if chat_id:
                    await context.bot.send_message(chat_id=chat_id, text=final_text, )
                else:
                    # best-effort: send to bot author (can't be sure; use no parameters)
                    logger.warning("No chat_id available to send fallback message with answer.")

        except asyncio.TimeoutError:
            timeout_text = f"❓ **Question:** {question}\n\n⏰ **Request timed out. Please try again.**"
            try:
                if "inline_message_id" in target:
                    await context.bot.edit_message_text(text=timeout_text, inline_message_id=target["inline_message_id"], )
                else:
                    await context.bot.edit_message_text(text=timeout_text, chat_id=target.get("chat_id"), message_id=target.get("message_id"), )
            except Exception:
                if target.get("chat_id"):
                    await context.bot.send_message(chat_id=target.get("chat_id"), text=timeout_text, )
        except Exception as e:
            logger.exception(f"Unhandled exception in _run_query_and_edit_message: {e}")
            error_text = f"❓ **Question:** {question}\n\n❌ **An error occurred while processing your request.**"
            try:
                if "inline_message_id" in target:
                    await context.bot.edit_message_text(text=error_text, inline_message_id=target["inline_message_id"], )
                else:
                    await context.bot.edit_message_text(text=error_text, chat_id=target.get("chat_id"), message_id=target.get("message_id"), )
            except Exception:
                if target.get("chat_id"):
                    await context.bot.send_message(chat_id=target.get("chat_id"), text=error_text, )
        finally:
            # cleanup stored mappings & running task
            self.pending_queries.pop(result_id, None)
            self.edit_targets.pop(result_id, None)
            task = self.running_tasks.pop(result_id, None)
            if task and task.done():
                try:
                    _ = task.result()
                except Exception:
                    pass

    # ---------------------------
    # Helpers (copy from your previous code)
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
