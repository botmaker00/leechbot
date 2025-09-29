from asyncio import create_task
from logging import getLogger

from pyrogram import Client, filters
from pyrogram.errors import (
    ApiIdInvalid,
    PasswordHashInvalid,
    PhoneCodeExpired,
    PhoneCodeInvalid,
    PhoneNumberInvalid,
    SessionPasswordNeeded,
)
from pyrogram.handlers import MessageHandler

from bot.core.aeon_client import TgClient
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    send_message,
)

LOGGER = getLogger(__name__)

# Dictionary to store user conversation state
session_state = {}

# Flag to track if session input handler is registered
_session_input_handler_registered = False


def register_session_input_handler():
    """Register session input handler for private messages"""
    global _session_input_handler_registered
    if _session_input_handler_registered:
        return

    # Register session input handler for private messages
    # Use a more permissive filter to catch all text messages in private chats
    TgClient.bot.add_handler(
        MessageHandler(handle_session_input, filters=filters.private & filters.text),
        group=2,  # Higher group to process after command handlers
    )

    _session_input_handler_registered = True


@new_task
async def handle_command(_, message):
    """
    Command handler for /gensession or /gs
    Initiates the session generation process
    """

    # Register session input handler if not already done
    register_session_input_handler()

    # Delete the command message immediately for security
    try:
        await message.delete()
    except Exception as e:
        LOGGER.error(f"Error deleting command message: {e!s}")

    await gen_session(_, message=message)


@new_task
async def handle_group_gensession(_, message):
    """
    Handler for /gensession or /gs command in groups
    Checks authorization and informs the user to use the command in private chat
    """
    # Check if user is authorized to use the bot in groups

    # Check authorization using the same logic as other commands
    is_authorized = await CustomFilters.authorized_user(CustomFilters, _, message)

    if not is_authorized:
        # User is not authorized, send unauthorized message
        try:
            await message.delete()
        except Exception as e:
            LOGGER.error(f"Error deleting unauthorized command message: {e!s}")

        msg = await send_message(
            message,
            "❌ <b>Unauthorized Access</b>\n\n"
            "You are not authorized to use this bot in groups.\n"
            "Please contact the bot administrator for access.",
        )
        create_task(auto_delete_message(msg, time=60))
        return

    # User is authorized, but still need to redirect to PM for security
    # Delete the command message immediately for security
    try:
        await message.delete()
    except Exception as e:
        LOGGER.error(f"Error deleting command message: {e!s}")
        # If we can't delete, we'll auto-delete it after 5 minutes
        create_task(auto_delete_message(message, time=300))

    # Create a button to redirect to bot PM
    buttons = ButtonMaker()
    buttons.url_button(
        "Generate Session",
        f"https://t.me/{(await TgClient.bot.get_me()).username}?start=gensession",
    )

    msg = await send_message(
        message.chat.id,  # Use chat.id instead of message since we might have deleted it
        "⚠️ <b>Security Notice:</b>\n\n"
        "The session generation command can only be used in private chat with the bot for security reasons.\n\n"
        "🔒 <b>SECURITY GUARANTEE:</b>\n"
        "• Your credentials are <b>NOT stored</b> anywhere\n"
        "• Credentials are immediately deleted after use\n"
        "• All messages will auto-delete for your privacy\n\n"
        "Please click the button below to start a private conversation with me and generate your session string securely.",
        buttons.build_menu(1),
    )
    create_task(auto_delete_message(msg, time=300))  # Delete after 5 minutes


async def handle_session_input(_, message):
    """
    Handles user input for session generation process
    """
    user_id = message.from_user.id

    # Check if user is in session generation process
    if user_id not in session_state:
        # This message is not for us, ignore it
        return

    # Check if the message is a command (starts with /) - ignore commands during session generation
    if message.text and message.text.startswith("/"):
        return

    # Delete user's message immediately to keep chat clean and secure
    try:
        await message.delete()
    except Exception as e:
        LOGGER.error(f"Error deleting user credential message: {e!s}")

    # Get current step
    current_step = session_state[user_id]["step"]

    # Handle input based on current step
    try:
        if current_step == "api_id":
            await handle_api_id(_, message, user_id)
        elif current_step == "api_hash":
            await handle_api_hash(_, message, user_id)
        elif current_step == "phone_or_bot":
            await handle_phone_or_bot(_, message, user_id)
        elif current_step == "verification_code":
            await handle_verification_code(_, message, user_id)
        elif current_step == "2fa_password":
            await handle_2fa_password(_, message, user_id)
        else:
            LOGGER.warning(
                f"Unknown session step: {current_step} for user {user_id}"
            )
    except Exception as e:
        LOGGER.error(f"Error in session generation for user {user_id}: {e!s}")
        error_msg = await send_message(
            message.chat.id,
            f"❌ <b>Error:</b> {e!s}\n\n"
            "<b>Session generation process has been cancelled.</b>\n\n"
            "You can use /gensession or /gs command again when you're ready to generate a session.",
        )
        create_task(auto_delete_message(error_msg, time=300))

        # Clean up
        await cleanup_session(user_id)


async def handle_api_id(_, message, user_id):
    """Handle API ID input"""
    try:
        api_id = int(message.text.strip())
        session_state[user_id]["api_id"] = api_id
        session_state[user_id]["step"] = "api_hash"

        # Delete previous message
        if session_state[user_id]["last_msg"]:
            await session_state[user_id]["last_msg"].delete()

        # Create cancel button
        buttons = ButtonMaker()
        buttons.data_button("Cancel", "gensession_cancel")

        # Send next instruction
        msg = await send_message(
            message.chat.id,
            "✅ API ID received.\n\n"
            "🔒 <b>Remember:</b> Your API ID is not stored and will be deleted after use.\n\n"
            "Now please enter your <b>API HASH</b>.\n\n"
            "<i>Click the button below to cancel the process</i>",
            buttons.build_menu(1),
        )
        session_state[user_id]["last_msg"] = msg

        # Auto-delete the message after 10 minutes for security
        create_task(auto_delete_message(msg, time=600))  # 10 minutes
    except ValueError:
        # Create cancel button
        buttons = ButtonMaker()
        buttons.data_button("Cancel", "gensession_cancel")

        error_msg = await send_message(
            message.chat.id,
            "❌ <b>Error:</b> Invalid API ID. Please enter a valid numeric value.\n\n"
            "<i>Click the button below to cancel the process</i>",
            buttons.build_menu(1),
        )
        create_task(
            auto_delete_message(error_msg, time=300)
        )  # Delete after 5 minutes


async def handle_api_hash(_, message, user_id):
    """Handle API Hash input"""
    api_hash = message.text.strip()
    session_state[user_id]["api_hash"] = api_hash
    session_state[user_id]["step"] = "phone_or_bot"

    # Delete previous message
    if session_state[user_id]["last_msg"]:
        await session_state[user_id]["last_msg"].delete()

    # Create cancel button
    buttons = ButtonMaker()
    buttons.data_button("Cancel", "gensession_cancel")

    # Send next instruction
    msg = await send_message(
        message.chat.id,
        "✅ API HASH received.\n\n"
        "🔒 <b>Security:</b> Your API HASH is not stored and will be deleted after use.\n\n"
        "Now please enter your <b>Phone Number</b> (with country code) or <b>Bot Token</b>.\n\n"
        "Examples:\n"
        "• Phone: +1234567890\n"
        "• Bot Token: 123456789:ABCdefGhIJklmNoPQRstUVwxyz\n\n"
        "<i>Click the button below to cancel the process</i>",
        buttons.build_menu(1),
    )
    session_state[user_id]["last_msg"] = msg

    # Auto-delete the message after 10 minutes for security
    create_task(auto_delete_message(msg, time=600))  # 10 minutes


async def handle_phone_or_bot(_, message, user_id):
    """Handle phone number or bot token input"""
    input_text = message.text.strip()

    # Delete previous message
    if session_state[user_id]["last_msg"]:
        await session_state[user_id]["last_msg"].delete()

    # Check if input is a bot token
    is_bot = ":" in input_text and len(input_text) > 25

    try:
        # Create client instance
        client_instance = Client(
            name=f"session_{user_id}",
            api_id=session_state[user_id]["api_id"],
            api_hash=session_state[user_id]["api_hash"],
            in_memory=True,
        )

        session_state[user_id]["client"] = client_instance
        session_state[user_id]["is_bot"] = is_bot

        # Send status message
        status_msg = await send_message(
            message.chat.id,
            "🔄 Connecting to Telegram...",
        )

        # Auto-delete the status message after 10 minutes for security
        create_task(auto_delete_message(status_msg, time=600))  # 10 minutes

        if is_bot:
            # Bot login
            session_state[user_id]["bot_token"] = input_text
            await client_instance.start(bot_token=input_text)

            # For bot tokens, we can't send to Saved Messages (no user account)
            # So we'll send directly in the bot PM
            session_string = await client_instance.export_session_string()

            # Create buttons
            buttons = ButtonMaker()
            buttons.data_button("Generate Again", "gensession")

            # Update message with session string
            await status_msg.delete()
            bot_success_msg = await send_message(
                message.chat.id,
                "✅ <b>Bot Session generated successfully!</b>\n\n"
                "🔒 <b>SECURITY GUARANTEE:</b> All your credentials have been deleted and were never stored.\n\n"
                "<b>Your Bot Session String:</b>\n"
                f"<code>{session_string}</code>\n\n"
                "⚠️ <b>IMPORTANT:</b>\n"
                "• Keep this string secure and do not share it with anyone.\n"
                "• This session string can be used to access your bot.\n"
                "• If you think someone got your session string, generate a new one.",
                buttons.build_menu(1),
            )

            # Auto-delete the bot success message after 10 minutes for security
            create_task(auto_delete_message(bot_success_msg, time=600))  # 10 minutes

            # Clean up
            await cleanup_session(user_id)
        else:
            # User login
            session_state[user_id]["phone"] = input_text
            await client_instance.connect()

            try:
                code = await client_instance.send_code(input_text)
                session_state[user_id]["phone_code_hash"] = code.phone_code_hash
                session_state[user_id]["step"] = "verification_code"

                # Create cancel button
                buttons = ButtonMaker()
                buttons.data_button("Cancel", "gensession_cancel")

                # Update message
                msg = await send_message(
                    message.chat.id,
                    "✅ Code sent successfully.\n\n"
                    "🔒 <b>Security:</b> Your phone number is not stored and will be deleted after use.\n\n"
                    "Please enter the verification code you received from Telegram.\n\n"
                    "<b>Accepted formats:</b>\n"
                    "• With spaces: <code>1 2 3 4 5</code>\n"
                    "• Without spaces: <code>12345</code>\n"
                    "• With any separator: <code>1-2-3-4-5</code> or <code>1.2.3.4.5</code>\n\n"
                    "<i>Only the digits will be used, so don't worry about the format.</i>\n\n"
                    "<i>Click the button below to cancel the process</i>",
                    buttons.build_menu(1),
                )
                session_state[user_id]["last_msg"] = msg

                # Auto-delete the message after 10 minutes for security
                create_task(auto_delete_message(msg, time=600))  # 10 minutes

                # Delete status message
                await status_msg.delete()

            except (ApiIdInvalid, PhoneNumberInvalid) as e:
                # Create cancel button
                buttons = ButtonMaker()
                buttons.data_button("Generate Again", "gensession")

                error_msg = await send_message(
                    message.chat.id,
                    f"❌ <b>Error:</b> {e!s}\n\n"
                    "<b>Session generation process has been cancelled.</b>\n\n"
                    "You can use /gensession or /gs command again when you're ready to generate a session.",
                    buttons.build_menu(1),
                )
                create_task(auto_delete_message(error_msg, time=300))
                await cleanup_session(user_id)

    except Exception as e:
        # Create cancel button
        buttons = ButtonMaker()
        buttons.data_button("Generate Again", "gensession")

        error_msg = await send_message(
            message.chat.id,
            f"❌ <b>Error:</b> {e!s}\n\n"
            "<b>Session generation process has been cancelled.</b>\n\n"
            "You can use /gensession or /gs command again when you're ready to generate a session.",
            buttons.build_menu(1),
        )
        create_task(auto_delete_message(error_msg, time=300))
        await cleanup_session(user_id)


async def handle_verification_code(_, message, user_id):
    """Handle verification code input"""
    # Clean up the code - remove spaces, dashes, and any other non-digit characters
    raw_code = message.text.strip()
    code = "".join(c for c in raw_code if c.isdigit())

    # Check if we have a valid code
    if not code or len(code) < 5:
        # Create cancel button
        buttons = ButtonMaker()
        buttons.data_button("Cancel", "gensession_cancel")

        error_msg = await send_message(
            message.chat.id,
            "❌ <b>Error:</b> Invalid verification code format.\n\n"
            "Please enter a valid verification code (5 digits).\n\n"
            "<i>Click the button below to cancel the process</i>",
            buttons.build_menu(1),
        )
        create_task(auto_delete_message(error_msg, time=300))
        return

    # Delete previous message
    if session_state[user_id]["last_msg"]:
        await session_state[user_id]["last_msg"].delete()

    # Send status message
    status_msg = await send_message(
        message.chat.id,
        "🔄 Verifying code...",
    )

    # Auto-delete the status message after 10 minutes for security
    create_task(auto_delete_message(status_msg, time=600))  # 10 minutes

    try:
        client_instance = session_state[user_id]["client"]
        phone = session_state[user_id]["phone"]
        phone_code_hash = session_state[user_id]["phone_code_hash"]

        try:
            await client_instance.sign_in(
                phone_number=phone,
                phone_code_hash=phone_code_hash,
                phone_code=code,
            )

            # Generate and send session string
            await generate_session_string(None, status_msg, user_id)

        except SessionPasswordNeeded:
            # 2FA is enabled
            session_state[user_id]["step"] = "2fa_password"

            # Create cancel button
            buttons = ButtonMaker()
            buttons.data_button("Cancel", "gensession_cancel")

            # Update message
            await status_msg.delete()
            msg = await send_message(
                message.chat.id,
                "🔐 Two-Step Verification is enabled.\n\n"
                "🔒 <b>Security:</b> Your verification code is not stored and will be deleted after use.\n\n"
                "Please enter your password.\n\n"
                "<i>Click the button below to cancel the process</i>",
                buttons.build_menu(1),
            )
            session_state[user_id]["last_msg"] = msg

            # Auto-delete the message after 10 minutes for security
            create_task(auto_delete_message(msg, time=600))  # 10 minutes

        except (PhoneCodeInvalid, PhoneCodeExpired) as e:
            await status_msg.delete()

            # Provide a more helpful error message
            error_message = str(e)
            if isinstance(e, PhoneCodeInvalid):
                error_message = "The verification code you entered is invalid. Please check the code and try again."
            elif isinstance(e, PhoneCodeExpired):
                error_message = "The verification code has expired. Please request a new code by starting the process again."

            # Create cancel button
            buttons = ButtonMaker()
            buttons.data_button("Generate Again", "gensession")

            error_msg = await send_message(
                message.chat.id,
                f"❌ <b>Error:</b> {error_message}\n\n"
                "<b>Session generation process has been cancelled.</b>\n\n"
                "You can use /gensession or /gs command again when you're ready to generate a session.",
                buttons.build_menu(1),
            )
            create_task(auto_delete_message(error_msg, time=300))
            await cleanup_session(user_id)

    except Exception as e:
        await status_msg.delete()

        # Create cancel button
        buttons = ButtonMaker()
        buttons.data_button("Generate Again", "gensession")

        error_msg = await send_message(
            message.chat.id,
            f"❌ <b>Error:</b> {e!s}\n\n"
            "<b>Session generation process has been cancelled.</b>\n\n"
            "You can use /gensession or /gs command again when you're ready to generate a session.",
            buttons.build_menu(1),
        )
        create_task(auto_delete_message(error_msg, time=300))
        await cleanup_session(user_id)


async def handle_2fa_password(_, message, user_id):
    """Handle 2FA password input"""
    password = message.text.strip()

    # Delete previous message
    if session_state[user_id]["last_msg"]:
        await session_state[user_id]["last_msg"].delete()

    # Send status message
    status_msg = await send_message(
        message.chat.id,
        "🔄 Verifying password...",
    )

    # Auto-delete the status message after 10 minutes for security
    create_task(auto_delete_message(status_msg, time=600))  # 10 minutes

    try:
        client_instance = session_state[user_id]["client"]

        try:
            await client_instance.check_password(password)

            # Generate and send session string
            await generate_session_string(None, status_msg, user_id)

        except PasswordHashInvalid:
            await status_msg.delete()

            # Create cancel button
            buttons = ButtonMaker()
            buttons.data_button("Generate Again", "gensession")

            error_msg = await send_message(
                message.chat.id,
                "❌ <b>Error:</b> Invalid password.\n\n"
                "<b>Session generation process has been cancelled.</b>\n\n"
                "You can use /gensession or /gs command again when you're ready to generate a session.",
                buttons.build_menu(1),
            )
            create_task(auto_delete_message(error_msg, time=300))
            await cleanup_session(user_id)

    except Exception as e:
        await status_msg.delete()

        # Create cancel button
        buttons = ButtonMaker()
        buttons.data_button("Generate Again", "gensession")

        error_msg = await send_message(
            message.chat.id,
            f"❌ <b>Error:</b> {e!s}\n\n"
            "<b>Session generation process has been cancelled.</b>\n\n"
            "You can use /gensession or /gs command again when you're ready to generate a session.",
            buttons.build_menu(1),
        )
        create_task(auto_delete_message(error_msg, time=300))
        await cleanup_session(user_id)


async def generate_session_string(_, status_msg, user_id):
    """Generate and send session string to user's Saved Messages"""
    try:
        client_instance = session_state[user_id]["client"]

        # Get session string
        session_string = await client_instance.export_session_string()

        # Create buttons
        buttons = ButtonMaker()
        buttons.data_button("Generate Again", "gensession")

        # First, try to send to Saved Messages
        try:
            # Send session string to user's Saved Messages
            await client_instance.send_message(
                "me",  # 'me' refers to Saved Messages
                "<b>Your Pyrogram Session String</b>\n\n"
                f"<code>{session_string}</code>\n\n"
                "⚠️ <b>IMPORTANT:</b>\n"
                "• Keep this string secure and do not share it with anyone.\n"
                "• This session string can be used to access your account.\n"
                "• If you think someone got your session string, generate a new one or revoke the session from Telegram settings.",
            )
            saved_msg_sent = True
        except Exception as e:
            LOGGER.error(f"Failed to send to Saved Messages: {e!s}")
            saved_msg_sent = False

        # Update status message
        await status_msg.delete()

        if saved_msg_sent:
            # Inform user that session was sent to Saved Messages
            success_msg = await send_message(
                status_msg.chat.id,
                "✅ <b>Session generated successfully!</b>\n\n"
                "🔒 <b>SECURITY GUARANTEE:</b> All your credentials have been deleted and were never stored.\n\n"
                "Your session string has been sent to your <b>Saved Messages</b>.\n"
                "Please check your Saved Messages for the session string.\n\n"
                "⚠️ <b>IMPORTANT:</b> Keep this string secure and do not share it with anyone.",
                buttons.build_menu(1),
            )

            # Auto-delete the success message after 10 minutes for security
            create_task(auto_delete_message(success_msg, time=600))  # 10 minutes
        else:
            # Fallback to sending in bot PM if Saved Messages fails
            fallback_msg = await send_message(
                status_msg.chat.id,
                "✅ <b>Session generated successfully!</b>\n\n"
                "🔒 <b>SECURITY GUARANTEE:</b> All your credentials have been deleted and were never stored.\n\n"
                "<b>Your Session String:</b>\n"
                f"<code>{session_string}</code>\n\n"
                "⚠️ <b>IMPORTANT:</b>\n"
                "• Keep this string secure and do not share it with anyone.\n"
                "• This session string can be used to access your account.\n"
                "• If you think someone got your session string, generate a new one or revoke the session from Telegram settings.",
                buttons.build_menu(1),
            )

            # Auto-delete the fallback message after 10 minutes for security
            create_task(auto_delete_message(fallback_msg, time=600))  # 10 minutes

        # Clean up
        await cleanup_session(user_id)

    except Exception as e:
        # Create cancel button
        buttons = ButtonMaker()
        buttons.data_button("Generate Again", "gensession")

        error_msg = await send_message(
            status_msg.chat.id,
            f"❌ <b>Error:</b> {e!s}\n\n"
            "<b>Session generation process has been cancelled.</b>\n\n"
            "You can use /gensession or /gs command again when you're ready to generate a session.",
            buttons.build_menu(1),
        )
        create_task(auto_delete_message(error_msg, time=300))
        await cleanup_session(user_id)


@new_task
async def handle_cancel_button(_, callback_query):
    """Handle cancel button click for session generation"""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    # Answer the callback immediately to provide feedback
    await callback_query.answer("Cancelling session generation...")

    # Check if user is in session generation process
    if user_id in session_state:
        # Get the message to delete before cleaning up session state
        message_to_delete = None
        if (
            "last_msg" in session_state[user_id]
            and session_state[user_id]["last_msg"]
        ):
            message_to_delete = session_state[user_id]["last_msg"]

        # Clean up the session state
        await cleanup_session(user_id)

        # Delete the message with the cancel button if it exists
        if message_to_delete:
            try:
                await message_to_delete.delete()
            except Exception as e:
                LOGGER.error(f"Error deleting message with cancel button: {e!s}")

        # Create button to generate again
        buttons = ButtonMaker()
        buttons.data_button("Generate Again", "gensession")

        # Send cancellation message
        cancel_msg = await send_message(
            chat_id,
            "❌ <b>Session generation process has been cancelled.</b>\n\n"
            "You can use /gensession or /gs command again when you're ready to generate a session.",
            buttons.build_menu(1),
        )

        # Auto-delete the message after 5 minutes
        create_task(auto_delete_message(cancel_msg, time=300))
    else:
        # Try to delete the message with the cancel button
        try:
            await callback_query.message.delete()
        except Exception as e:
            LOGGER.error(f"Error deleting message: {e!s}")

        # Create button to generate a session
        buttons = ButtonMaker()
        buttons.data_button("Generate Session", "gensession")

        # Send message that there's no active session to cancel
        msg = await send_message(
            chat_id,
            "ℹ️ <b>Info:</b> You don't have an active session generation process to cancel.",
            buttons.build_menu(1),
        )

        # Auto-delete the message after 1 minute
        create_task(auto_delete_message(msg, time=60))


async def cleanup_session(user_id):
    """Clean up session generation resources and securely remove sensitive data"""
    if user_id in session_state:
        # Stop client if it exists and is connected
        if session_state[user_id].get("client"):
            try:
                client_instance = session_state[user_id]["client"]
                if client_instance.is_connected:
                    await client_instance.disconnect()
            except Exception as e:
                LOGGER.error(f"Error disconnecting client: {e!s}")

        # Securely clear sensitive data before removing
        sensitive_fields = [
            "api_id",
            "api_hash",
            "phone",
            "bot_token",
            "phone_code_hash",
        ]
        for field in sensitive_fields:
            if field in session_state[user_id]:
                # Overwrite with None to help with garbage collection
                session_state[user_id][field] = None

        # Remove user from session state
        del session_state[user_id]


async def gen_session(_, callback_query=None, message=None):
    """Handle both command and callback for session generation"""
    # Register session input handler if not already done
    register_session_input_handler()

    # If called from callback query
    if callback_query:
        await callback_query.answer()
        user_id = callback_query.from_user.id
        chat_id = callback_query.message.chat.id

        # Delete the previous message with session string
        try:
            await delete_message(callback_query.message)
        except Exception as e:
            LOGGER.error(f"Error deleting callback message: {e!s}")

        # Create a new message object for sending
        class FakeMessage:
            def __init__(self, chat_id):
                self.chat = type(
                    "obj", (object,), {"id": chat_id, "type": "private"}
                )
                self.message_id = None
                self.from_user = None
                self.date = None
                self.text = None
                self.id = None  # Add id attribute

            async def reply(self, text, reply_markup=None, quote=None, **kwargs):
                """Fake reply method that sends to chat"""
                # Remove parameters that send_message doesn't accept
                kwargs.pop("quote", None)
                kwargs.pop("disable_web_page_preview", None)
                kwargs.pop("disable_notification", None)
                kwargs.pop("parse_mode", None)

                from bot.helper.telegram_helper.message_utils import send_message

                return await send_message(self.chat.id, text, reply_markup)

        message = FakeMessage(chat_id)
    elif not message:
        LOGGER.warning("gen_session called without message or callback_query")
        return
    else:
        user_id = message.from_user.id

    # This function should only be called in private chats now
    # The group handler is separate

    # Clean up any existing session for this user
    if user_id in session_state:
        await cleanup_session(user_id)

    # Initialize user state
    session_state[user_id] = {
        "step": "api_id",
        "api_id": None,
        "api_hash": None,
        "phone_or_bot": None,
        "client": None,
        "last_msg": None,
    }

    # Create cancel button
    buttons = ButtonMaker()
    buttons.data_button("Cancel", "gensession_cancel")

    # Send initial message asking for API ID
    msg = await send_message(
        message,
        "📱 <b>Pyrogram Session Generator</b>\n\n"
        "🔒 <b>SECURITY GUARANTEE:</b>\n"
        "• Your credentials are <b>NOT stored</b> anywhere\n"
        "• Credentials are immediately deleted after use\n"
        "• All messages will auto-delete for your privacy\n\n"
        "Please enter your <b>API ID</b> (numeric value).\n\n"
        "<i>You can get API ID and API HASH from https://my.telegram.org</i>\n\n"
        "<i>Click the button below to cancel the process</i>",
        buttons.build_menu(1),
    )

    # Store the message ID for later deletion
    session_state[user_id]["last_msg"] = msg

    # Auto-delete the message after 10 minutes for security
    # We don't need to store the task reference as it will be garbage collected properly
    create_task(auto_delete_message(msg, time=600))  # 10 minutes
