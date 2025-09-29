from pyrogram.types import Chat, User

from bot.core.config_manager import Config


class QuickInfoFormatter:
    """Handles formatting for QuickInfo responses"""

    @staticmethod
    def format_user_info(user: User, style: str = "detailed") -> str:
        """Format user information"""
        user_id = user.id
        first_name = user.first_name or "N/A"
        last_name = user.last_name or ""
        username = f"@{user.username}" if user.username else "No username"
        user_type = "Bot" if user.is_bot else "User"
        is_premium = getattr(user, "is_premium", False)

        premium_info = "\n🌟 <b>Premium:</b> <code>Yes</code>" if is_premium else ""
        return (
            f"👤 <b>{user_type} Information</b>\n\n"
            f"🏷 <b>Type:</b> <code>{user_type}</code>\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
            f"📝 <b>Name:</b> <code>{(first_name + ' ' + last_name).strip()}</code>\n"
            f"🔗 <b>Username:</b> <code>{username}</code>" + premium_info
        )

    @staticmethod
    def format_chat_info(
        chat: Chat, style: str = "detailed", limited_access: bool = False
    ) -> str:
        """Format chat information"""
        chat_id = chat.id
        chat_name = chat.title or "Unnamed Chat"
        chat_type = str(chat.type).replace("ChatType.", "").capitalize()
        username = f"@{chat.username}" if chat.username else "Private/No username"
        members_count = getattr(chat, "members_count", "Private/Unknown")

        # Add note for limited access
        access_note = ""
        if limited_access:
            access_note = (
                "\n\n🔒 <i>Limited info - Bot doesn't have access to this chat</i>"
            )

        return (
            f"💬 <b>{chat_type} Information</b>\n\n"
            f"🏷 <b>Type:</b> <code>{chat_type}</code>\n"
            f"🆔 <b>ID:</b> <code>{chat_id}</code>\n"
            f"📝 <b>Name:</b> <code>{chat_name}</code>\n"
            f"🔗 <b>Username:</b> <code>{username}</code>\n"
            f"👥 <b>Members:</b> <code>{members_count}</code>" + access_note
        )

    @staticmethod
    def format_media_info(message) -> str:
        """Format media information from a message"""
        media_info = []

        if message.photo:
            photo = message.photo
            media_info.append(f"📷 <b>Photo:</b> {photo.width}x{photo.height}")
            if photo.file_size:
                media_info.append(
                    f"📦 <b>Size:</b> {photo.file_size / 1024 / 1024:.2f} MB"
                )

        elif message.video:
            video = message.video
            media_info.append(f"🎥 <b>Video:</b> {video.width}x{video.height}")
            if video.duration:
                media_info.append(f"⏱ <b>Duration:</b> {video.duration}s")
            if video.file_size:
                media_info.append(
                    f"📦 <b>Size:</b> {video.file_size / 1024 / 1024:.2f} MB"
                )

        elif message.audio:
            audio = message.audio
            media_info.append(f"🎵 <b>Audio:</b> {audio.title or 'Unknown'}")
            if audio.performer:
                media_info.append(f"👤 <b>Artist:</b> {audio.performer}")
            if audio.duration:
                media_info.append(f"⏱ <b>Duration:</b> {audio.duration}s")
            if audio.file_size:
                media_info.append(
                    f"📦 <b>Size:</b> {audio.file_size / 1024 / 1024:.2f} MB"
                )

        elif message.voice:
            voice = message.voice
            media_info.append("🎤 <b>Voice Message</b>")
            if voice.duration:
                media_info.append(f"⏱ <b>Duration:</b> {voice.duration}s")
            if voice.file_size:
                media_info.append(f"📦 <b>Size:</b> {voice.file_size / 1024:.2f} KB")

        elif message.video_note:
            video_note = message.video_note
            media_info.append("📹 <b>Video Note</b>")
            if video_note.duration:
                media_info.append(f"⏱ <b>Duration:</b> {video_note.duration}s")
            if video_note.file_size:
                media_info.append(
                    f"📦 <b>Size:</b> {video_note.file_size / 1024 / 1024:.2f} MB"
                )

        elif message.document:
            document = message.document
            media_info.append(
                f"📄 <b>Document:</b> {document.file_name or 'Unknown'}"
            )
            if document.mime_type:
                media_info.append(f"🏷 <b>Type:</b> {document.mime_type}")
            if document.file_size:
                media_info.append(
                    f"📦 <b>Size:</b> {document.file_size / 1024 / 1024:.2f} MB"
                )

        elif message.sticker:
            sticker = message.sticker
            media_info.append(f"🎭 <b>Sticker:</b> {sticker.emoji or '❓'}")
            if sticker.set_name:
                media_info.append(f"📦 <b>Set:</b> {sticker.set_name}")

        elif message.animation:
            animation = message.animation
            media_info.append(f"🎬 <b>GIF:</b> {animation.width}x{animation.height}")
            if animation.duration:
                media_info.append(f"⏱ <b>Duration:</b> {animation.duration}s")
            if animation.file_size:
                media_info.append(
                    f"📦 <b>Size:</b> {animation.file_size / 1024 / 1024:.2f} MB"
                )

        return "\n".join(media_info) if media_info else ""


def is_quickinfo_enabled() -> bool:
    """Check if QuickInfo feature is enabled"""
    return getattr(Config, "QUICKINFO_ENABLED", True)


def get_quickinfo_help_text() -> str:
    """Get help text for QuickInfo"""
    return (
        "🚀 <b>QuickInfo Help Center</b> 🌟\n\n"
        "🔍 <b>Need to grab a chat ID? We've got you covered!</b>\n\n"
        "📋 <b>Commands &amp; Features:</b>\n"
        "👉 <code>/quickinfo</code> or <code>/qi</code> - Launch QuickInfo with interactive buttons! 🎮\n"
        "👉 <code>/quickinfo chat</code> - Get current chat information 📖\n"
        "👉 <b>Forward Messages</b> - Send any forwarded message to reveal its source ID! 🔎\n"
        "👉 <b>Buttons</b> - Pick from users, bots, groups, or channels to get IDs instantly ⚡\n\n"
        "💡 <b>Pro Tip:</b> Forward a message from any chat, and I'll dig up the details! 🕵️\n\n"
        "📩 <b>Support:</b> Contact administrators for help! 😎"
    )


# Global instances
formatter = QuickInfoFormatter()
