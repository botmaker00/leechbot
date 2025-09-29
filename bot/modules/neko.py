"""
Cat API Module - Neko Command
Fetches adorable cat images from The Cat API with voting functionality
Designed with beautiful UI for cat lovers
"""

from typing import ClassVar

import aiohttp
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot import LOGGER
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.telegram_helper.message_utils import (
    delete_message,
    send_message,
)


class CatAPIHelper:
    """Helper class for The Cat API integration"""

    BASE_URL = "https://api.thecatapi.com/v1"

    # Cache for storing votes to prevent duplicate voting
    _user_votes: ClassVar[
        dict[str, dict[str, int]]
    ] = {}  # {user_id: {image_id: vote_value}}

    # Counter for tracking kitty numbers per user
    _user_kitty_counters: ClassVar[dict[str, int]] = {}  # {user_id: counter}

    @classmethod
    async def _make_request(
        cls, endpoint: str, method: str = "GET", data: dict | None = None
    ) -> dict | None:
        """Make HTTP request to Cat API"""
        url = f"{cls.BASE_URL}/{endpoint}"
        headers = {}

        # Add API key if available
        if Config.CAT_API_KEY:
            headers["x-api-key"] = Config.CAT_API_KEY

        try:
            async with aiohttp.ClientSession() as session:
                if method == "GET":
                    async with session.get(url, headers=headers) as response:
                        if response.status == 200:
                            return await response.json()
                        LOGGER.error(f"Cat API request failed: {response.status}")
                        return None
                elif method == "POST":
                    headers["Content-Type"] = "application/json"
                    async with session.post(
                        url, headers=headers, json=data
                    ) as response:
                        if response.status in [200, 201]:
                            return await response.json()
                        LOGGER.error(
                            f"Cat API POST request failed: {response.status}"
                        )
                        return None
        except Exception as e:
            LOGGER.error(f"Error making Cat API request: {e}")
            return None

    @classmethod
    async def get_random_cats(cls, limit: int = 1) -> list[dict] | None:
        """Get random cat images"""
        # Limit to max 10 images to prevent spam
        limit = min(limit, 10)

        if Config.CAT_API_KEY:
            # With API key, we can use all query parameters
            endpoint = f"images/search?limit={limit}&has_breeds=0&order=RAND"
        else:
            # Without API key, limit parameter works but other parameters don't
            # Request the maximum (10) and slice manually to ensure we get enough
            endpoint = "images/search?limit=10"

        result = await cls._make_request(endpoint)

        # If no API key, manually limit the results to the requested amount
        if result and not Config.CAT_API_KEY and len(result) > limit:
            result = result[:limit]

        return result

    @classmethod
    async def vote_on_image(
        cls, image_id: str, user_id: str, vote_value: int
    ) -> bool:
        """Vote on a cat image (1 for upvote, -1 for downvote)"""
        if not Config.CAT_API_KEY:
            # Store vote locally if no API key
            if str(user_id) not in cls._user_votes:
                cls._user_votes[str(user_id)] = {}
            cls._user_votes[str(user_id)][image_id] = vote_value
            return True

        # Submit vote to API
        data = {
            "image_id": image_id,
            "sub_id": f"user_{user_id}",
            "value": vote_value,
        }

        result = await cls._make_request("votes", method="POST", data=data)
        return result is not None

    @classmethod
    def get_user_vote(cls, image_id: str, user_id: str) -> int | None:
        """Get user's existing vote for an image"""
        user_votes = cls._user_votes.get(str(user_id), {})
        return user_votes.get(image_id)

    @classmethod
    def get_next_kitty_number(cls, user_id: str) -> int:
        """Get the next kitty number for a user"""
        user_id_str = str(user_id)
        if user_id_str not in cls._user_kitty_counters:
            cls._user_kitty_counters[user_id_str] = 1
        else:
            cls._user_kitty_counters[user_id_str] += 1
        return cls._user_kitty_counters[user_id_str]

    @classmethod
    def reset_kitty_counter(cls, user_id: str):
        """Reset kitty counter for a user (when they start a new /neko command)"""
        cls._user_kitty_counters[str(user_id)] = 0

    @classmethod
    async def get_cat_fact(cls) -> str | None:
        """Get a random cat fact from meowfacts API"""
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.get("https://meowfacts.herokuapp.com/") as response,
            ):
                if response.status == 200:
                    data = await response.json()
                    if data and "data" in data and len(data["data"]) > 0:
                        return data["data"][0]
        except Exception as e:
            LOGGER.error(f"Error fetching cat fact: {e}")
        return None


def create_cat_buttons(image_id: str, user_id: str) -> InlineKeyboardMarkup:
    """Create beautiful voting buttons for cat images"""
    # Check if user has already voted
    user_vote = CatAPIHelper.get_user_vote(image_id, user_id)

    # Create buttons with cute emojis and styling
    buttons = []

    # Upvote button
    if user_vote == 1:
        upvote_text = "💖 Loved! (You voted)"
        upvote_callback = f"neko_vote_{image_id}_{user_id}_1_voted"
    else:
        upvote_text = "💖 Love this kitty!"
        upvote_callback = f"neko_vote_{image_id}_{user_id}_1"

    # Downvote button
    if user_vote == -1:
        downvote_text = "💔 Not cute (You voted)"
        downvote_callback = f"neko_vote_{image_id}_{user_id}_-1_voted"
    else:
        downvote_text = "💔 Not my type"
        downvote_callback = f"neko_vote_{image_id}_{user_id}_-1"

    # First row: voting buttons
    buttons.append(
        [
            InlineKeyboardButton(upvote_text, callback_data=upvote_callback),
            InlineKeyboardButton(downvote_text, callback_data=downvote_callback),
        ]
    )

    # Second row: additional actions
    buttons.append(
        [
            InlineKeyboardButton(
                "🔄 Another kitty", callback_data=f"neko_new_{user_id}"
            ),
            InlineKeyboardButton("❌ Close", callback_data=f"neko_close_{user_id}"),
        ]
    )

    return InlineKeyboardMarkup(buttons)


@new_task
async def neko_command(_, message: Message):
    """Handle /neko command for cat images"""
    user_id = message.from_user.id

    # Parse command arguments
    args = message.text.split()[1:] if len(message.text.split()) > 1 else []

    # Determine number of images to fetch
    num_images = 1
    if args:
        try:
            num_images = int(args[0])
            if num_images < 1:
                num_images = 1
            elif num_images > 10:
                num_images = 10
        except ValueError:
            await send_message(
                message,
                "🐱 <b>Invalid number!</b>\n\n"
                "Usage: <code>/neko</code> or <code>/neko [number]</code>\n"
                "Number must be between 1 and 10.",
            )
            await delete_message(message)
            return

    # Show loading message
    loading_msg = await send_message(
        message, "🐱 <b>Fetching adorable kitties...</b> 💕"
    )

    try:
        # Reset kitty counter for this user when starting new /neko command
        CatAPIHelper.reset_kitty_counter(user_id)

        # Fetch cat images
        cats = await CatAPIHelper.get_random_cats(num_images)

        if not cats:
            await send_message(
                message,
                "😿 <b>Sorry!</b> Couldn't fetch cat images right now.\n"
                "Please try again later! 🐾",
            )
            await delete_message(loading_msg)
            await delete_message(message)
            return

        # Send cat images with voting buttons first
        messages_deleted = False
        for i, cat in enumerate(cats):
            image_url = cat.get("url")
            image_id = cat.get("id", f"unknown_{i}")

            if not image_url:
                continue

            # Get next kitty number for this user
            kitty_number = CatAPIHelper.get_next_kitty_number(user_id)

            # Create beautiful caption
            caption = (
                f"🐱 <b>Adorable Kitty #{kitty_number}</b> 💕\n\n"
                f"✨ <i>Rate this precious furball!</i>\n"
                f"🆔 <code>{image_id}</code>"
            )

            # Add breed information if available
            if cat.get("breeds") and len(cat["breeds"]) > 0:
                breed = cat["breeds"][0]
                breed_name = breed.get("name", "Unknown")
                temperament = breed.get("temperament", "")

                caption += f"\n\n🏷️ <b>Breed:</b> {breed_name}"
                if temperament:
                    caption += f"\n💭 <b>Personality:</b> {temperament}"

            # Add cat fact
            cat_fact = await CatAPIHelper.get_cat_fact()
            if cat_fact:
                caption += (
                    f"\n\n<blockquote>🧠 <b>Cat Fact:</b>\n{cat_fact}</blockquote>"
                )

            # Create voting buttons
            buttons = create_cat_buttons(image_id, user_id)

            try:
                await message._client.send_photo(
                    chat_id=message.chat.id,
                    photo=image_url,
                    caption=caption,
                    reply_markup=buttons,
                )

                # Delete loading message and command after first successful image
                if not messages_deleted:
                    await delete_message(loading_msg)
                    await delete_message(message)
                    messages_deleted = True

            except Exception as e:
                LOGGER.error(f"Failed to send cat image: {e}")
                # If we haven't deleted messages yet, we can still send error
                if not messages_deleted:
                    await send_message(
                        message,
                        f"😿 Failed to send cat image #{i + 1}. Please try again!",
                    )

    except Exception as e:
        LOGGER.error(f"Error in neko command: {e}")
        await send_message(
            message,
            "😿 <b>Oops!</b> Something went wrong while fetching kitties.\n"
            "Please try again later! 🐾",
        )
        await delete_message(loading_msg)
        await delete_message(message)


@new_task
async def neko_callback_handler(_, query: CallbackQuery):
    """Handle neko callback queries for voting and actions"""
    try:
        data = query.data.split("_")
        action = data[1]  # vote, new, close

        if action == "vote":
            # Handle voting
            image_id = data[2]
            user_id = int(data[3])
            vote_value = int(data[4])
            already_voted = len(data) > 5 and data[5] == "voted"

            # Check if user is authorized to vote on this image
            if query.from_user.id != user_id:
                await query.answer(
                    "❌ You can only vote on your own requests!", show_alert=True
                )
                return

            if already_voted:
                await query.answer(
                    "💕 You already voted on this kitty!", show_alert=True
                )
                return

            # Submit vote
            success = await CatAPIHelper.vote_on_image(image_id, user_id, vote_value)

            if success:
                vote_text = "💖 Loved!" if vote_value == 1 else "💔 Not cute"
                await query.answer(
                    f"✨ {vote_text} Thanks for rating this kitty! 🐾",
                    show_alert=True,
                )

                # Update buttons to show voted state
                new_buttons = create_cat_buttons(image_id, user_id)
                try:
                    await query.edit_message_reply_markup(reply_markup=new_buttons)
                except Exception:
                    pass  # Message might be too old to edit
            else:
                await query.answer(
                    "😿 Failed to submit vote. Please try again!", show_alert=True
                )

        elif action == "new":
            # Handle new cat request
            user_id = int(data[2])

            if query.from_user.id != user_id:
                await query.answer(
                    "❌ You can only request new cats for yourself!", show_alert=True
                )
                return

            await query.answer("🐱 Fetching a new kitty for you! 💕")

            # Fetch and send a new cat image directly
            try:
                cats = await CatAPIHelper.get_random_cats(1)

                if not cats:
                    await query.message._client.send_message(
                        chat_id=query.message.chat.id,
                        text="😿 <b>Sorry!</b> Couldn't fetch a new cat image right now.\nPlease try again later! 🐾",
                    )
                    return

                cat = cats[0]
                image_url = cat.get("url")
                image_id = cat.get("id", "unknown")

                if not image_url:
                    return

                # Get next kitty number for this user
                kitty_number = CatAPIHelper.get_next_kitty_number(user_id)

                # Create beautiful caption
                caption = (
                    f"🐱 <b>Adorable Kitty #{kitty_number}</b> 💕\n\n"
                    f"✨ <i>Rate this precious furball!</i>\n"
                    f"🆔 <code>{image_id}</code>"
                )

                # Add breed information if available
                if cat.get("breeds") and len(cat["breeds"]) > 0:
                    breed = cat["breeds"][0]
                    breed_name = breed.get("name", "Unknown")
                    temperament = breed.get("temperament", "")

                    caption += f"\n\n🏷️ <b>Breed:</b> {breed_name}"
                    if temperament:
                        caption += f"\n💭 <b>Personality:</b> {temperament}"

                # Add cat fact
                cat_fact = await CatAPIHelper.get_cat_fact()
                if cat_fact:
                    caption += f"\n\n<blockquote>🧠 <b>Cat Fact:</b>\n{cat_fact}</blockquote>"

                # Create voting buttons
                buttons = create_cat_buttons(image_id, user_id)

                await query.message._client.send_photo(
                    chat_id=query.message.chat.id,
                    photo=image_url,
                    caption=caption,
                    reply_markup=buttons,
                )

            except Exception as e:
                LOGGER.error(f"Error fetching new cat: {e}")
                await query.message._client.send_message(
                    chat_id=query.message.chat.id,
                    text="😿 <b>Oops!</b> Something went wrong while fetching a new kitty.\nPlease try again later! 🐾",
                )

        elif action == "close":
            # Handle close action
            user_id = int(data[2])

            if query.from_user.id != user_id:
                await query.answer(
                    "❌ Only the requester can close this!", show_alert=True
                )
                return

            await query.answer("🐾 Goodbye kitty! 💕")
            try:
                await query.message.delete()
            except Exception:
                pass  # Message might already be deleted

    except Exception as e:
        LOGGER.error(f"Error in neko callback handler: {e}")
        await query.answer(
            "😿 Something went wrong! Please try again.", show_alert=True
        )
