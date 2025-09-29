from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import LOGGER
from bot.helper.ext_utils.links_utils import is_url


class ButtonMaker:
    def __init__(self):
        self._button = []
        self._header_button = []
        self._footer_button = []
        self._page_button = []

    def url_button(self, key, link, position=None):
        # Validate and convert URL to string
        if link is None or link == "":
            LOGGER.error(f"Invalid URL button: '{link}' is empty")
            return self

        # Auto-convert non-string values to strings (for backward compatibility)
        if not isinstance(link, str):
            try:
                link = str(link)
            except Exception as e:
                LOGGER.error(f"Failed to convert URL '{link}' to string: {e}")
                return self

        # Validate and convert button text to string
        if key is None or key == "":
            LOGGER.error(f"Invalid URL button text: '{key}' is empty")
            return self

        # Auto-convert non-string values to strings (for backward compatibility)
        if not isinstance(key, str):
            try:
                key = str(key)
            except Exception as e:
                LOGGER.error(
                    f"Failed to convert URL button text '{key}' to string: {e}"
                )
                return self

        # Ensure URL has a protocol (http:// or https://)
        if not link.startswith(("http://", "https://", "tg://")):
            if link.startswith("t.me/"):
                link = "https://" + link
            else:
                LOGGER.error(
                    f"Invalid URL button: '{link}' missing protocol (http:// or https://)"
                )
                return self

        # Validate URL format
        if not is_url(link) and not link.startswith("tg://"):
            LOGGER.error(f"Invalid URL button: '{link}' has invalid format")
            return self

        # Create button with validated URL
        if not position:
            self._button.append(InlineKeyboardButton(text=key, url=link))
        elif position == "header":
            self._header_button.append(InlineKeyboardButton(text=key, url=link))
        elif position == "footer":
            self._footer_button.append(InlineKeyboardButton(text=key, url=link))

        return self

    def data_button(self, key, data, position=None):
        # Validate and convert callback_data to string
        if data is None or data == "":
            LOGGER.error(f"Invalid callback data: '{data}' is empty")
            return self

        # Auto-convert non-string values to strings (for backward compatibility)
        if not isinstance(data, str):
            try:
                data = str(data)
            except Exception as e:
                LOGGER.error(
                    f"Failed to convert callback data '{data}' to string: {e}"
                )
                return self

        # Ensure callback_data doesn't exceed Telegram's limit (64 bytes)
        if len(data.encode("utf-8")) > 64:
            LOGGER.error(f"Callback data too long: '{data}' exceeds 64 bytes")
            # Truncate data to fit within limits
            data = data[:60] + "..."

        # Validate and convert button text to string
        if key is None or key == "":
            LOGGER.error(f"Invalid button text: '{key}' is empty")
            return self

        # Auto-convert non-string values to strings (for backward compatibility)
        if not isinstance(key, str):
            try:
                key = str(key)
            except Exception as e:
                LOGGER.error(f"Failed to convert button text '{key}' to string: {e}")
                return self

        if not position:
            self._button.append(InlineKeyboardButton(text=key, callback_data=data))
        elif position == "header":
            self._header_button.append(
                InlineKeyboardButton(text=key, callback_data=data),
            )
        elif position == "footer":
            self._footer_button.append(
                InlineKeyboardButton(text=key, callback_data=data),
            )
        elif position == "page":
            self._page_button.append(
                InlineKeyboardButton(text=key, callback_data=data),
            )
        return self

    def build_menu(self, b_cols=1, h_cols=8, f_cols=8, p_cols=8):
        # Validate column parameters
        b_cols = max(1, min(8, b_cols))  # Ensure between 1 and 8
        h_cols = max(1, min(8, h_cols))
        f_cols = max(1, min(8, f_cols))
        p_cols = max(1, min(8, p_cols))

        # Telegram has a limit of 100 buttons per message
        max_buttons = 100
        current_button_count = 0

        # Create menu with main buttons
        menu = []
        if self._button:
            for i in range(0, len(self._button), b_cols):
                row = self._button[i : i + b_cols]
                current_button_count += len(row)
                if current_button_count <= max_buttons:
                    menu.append(row)
                else:
                    LOGGER.warning(
                        f"Truncating buttons: exceeded Telegram's limit of {max_buttons} buttons"
                    )
                    break

        # Add header buttons
        if self._header_button and current_button_count < max_buttons:
            h_cnt = len(self._header_button)
            if h_cnt > h_cols:
                header_buttons = []
                for i in range(0, len(self._header_button), h_cols):
                    row = self._header_button[i : i + h_cols]
                    current_button_count += len(row)
                    if current_button_count <= max_buttons:
                        header_buttons.append(row)
                    else:
                        LOGGER.warning(
                            f"Truncating header buttons: exceeded Telegram's limit of {max_buttons} buttons"
                        )
                        break
                menu = header_buttons + menu
            else:
                current_button_count += len(self._header_button)
                if current_button_count <= max_buttons:
                    menu.insert(0, self._header_button)
                else:
                    LOGGER.warning(
                        f"Skipping header buttons: would exceed Telegram's limit of {max_buttons} buttons"
                    )

        # Add page buttons
        if self._page_button and current_button_count < max_buttons:
            if len(self._page_button) > p_cols:
                for i in range(0, len(self._page_button), p_cols):
                    row = self._page_button[i : i + p_cols]
                    current_button_count += len(row)
                    if current_button_count <= max_buttons:
                        menu.append(row)
                    else:
                        LOGGER.warning(
                            f"Truncating page buttons: exceeded Telegram's limit of {max_buttons} buttons"
                        )
                        break
            else:
                current_button_count += len(self._page_button)
                if current_button_count <= max_buttons:
                    menu.append(self._page_button)
                else:
                    LOGGER.warning(
                        f"Skipping page buttons: would exceed Telegram's limit of {max_buttons} buttons"
                    )

        # Add footer buttons
        if self._footer_button and current_button_count < max_buttons:
            if len(self._footer_button) > f_cols:
                for i in range(0, len(self._footer_button), f_cols):
                    row = self._footer_button[i : i + f_cols]
                    current_button_count += len(row)
                    if current_button_count <= max_buttons:
                        menu.append(row)
                    else:
                        LOGGER.warning(
                            f"Truncating footer buttons: exceeded Telegram's limit of {max_buttons} buttons"
                        )
                        break
            else:
                current_button_count += len(self._footer_button)
                if current_button_count <= max_buttons:
                    menu.append(self._footer_button)
                else:
                    LOGGER.warning(
                        f"Skipping footer buttons: would exceed Telegram's limit of {max_buttons} buttons"
                    )

        # Ensure we have at least one button
        if not menu:
            LOGGER.warning("No valid buttons to display")
            return None

        try:
            return InlineKeyboardMarkup(menu)
        except Exception as e:
            LOGGER.error(f"Error creating InlineKeyboardMarkup: {e}")
            # Return a simplified markup as fallback
            return None

    def reset(self):
        self._button = []
        self._header_button = []
        self._footer_button = []
        self._page_button = []
        return self
