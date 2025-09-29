"""
Client management for File2Link streaming
Integrates with existing client system
"""

from typing import Any

from pyrogram import Client

from bot import LOGGER


def get_tg_client():
    """Lazy import of TgClient to avoid startup delays"""
    from bot.core.aeon_client import TgClient

    return TgClient


class StreamClientManager:
    """Manages client selection and load balancing for streaming"""

    @staticmethod
    async def check_client_health(client, client_id):
        """Check if a client is healthy and authenticated"""
        try:
            # Try a simple API call to check authentication
            await client.get_me()
            return True
        except Exception as e:
            error_msg = str(e).lower()
            if "unauthorized" in error_msg or "auth" in error_msg:
                LOGGER.error(f"Client {client_id} authentication failed: {e}")
                return False
            LOGGER.warning(f"Client {client_id} health check failed: {e}")
            return False

    @staticmethod
    def get_optimal_client() -> tuple[Client, int]:
        """
        Select optimal client from client pool
        Returns: (client, client_id)
        """
        try:
            TgClient = get_tg_client()

            # Check if TgClient is properly initialized
            if not hasattr(TgClient, "bot") or TgClient.bot is None:
                LOGGER.warning(
                    "TgClient not initialized yet, streaming may not work"
                )
                return None, 0

            # Use helper bots if available
            if (
                hasattr(TgClient, "helper_bots")
                and TgClient.helper_bots
                and hasattr(TgClient, "helper_loads")
                and TgClient.helper_loads
            ):
                # Find client with minimum load
                min_load_client_id = min(
                    TgClient.helper_loads, key=TgClient.helper_loads.get
                )
                min_load = TgClient.helper_loads[min_load_client_id]

                # Check if any helper bot has reasonable load (< 8 concurrent streams)
                if min_load < 8:
                    return TgClient.helper_bots[
                        min_load_client_id
                    ], min_load_client_id
                # All helper bots are busy, use the least busy one
                return TgClient.helper_bots[min_load_client_id], min_load_client_id

            # Fallback to main bot if no helper bots available
            return TgClient.bot, 0

        except Exception as e:
            LOGGER.error(f"Error selecting optimal client: {e}")
            # Return None to indicate client not available
            return None, 0

    @staticmethod
    def increment_load(client_id: int) -> None:
        """Increment client workload"""
        try:
            TgClient = get_tg_client()

            if client_id == 0:
                # Main bot - we don't track its load in helper_loads
                pass
            elif client_id in TgClient.helper_loads:
                TgClient.helper_loads[client_id] += 1
        except Exception as e:
            LOGGER.error(f"Error incrementing load for client {client_id}: {e}")

    @staticmethod
    def decrement_load(client_id: int) -> None:
        """Decrement client workload"""
        try:
            TgClient = get_tg_client()

            if client_id == 0:
                # Main bot - we don't track its load in helper_loads
                pass
            elif client_id in TgClient.helper_loads:
                TgClient.helper_loads[client_id] = max(
                    0, TgClient.helper_loads[client_id] - 1
                )
        except Exception as e:
            LOGGER.error(f"Error decrementing load for client {client_id}: {e}")

    @staticmethod
    def get_client_workload() -> dict[int, int]:
        """Get current workload distribution"""
        try:
            TgClient = get_tg_client()

            workload = {}

            # Add main bot (always 0 load as we don't track it)
            workload[0] = 0

            # Add helper bots
            if TgClient.helper_loads:
                workload.update(TgClient.helper_loads)

            return workload
        except Exception as e:
            LOGGER.error(f"Error getting client workload: {e}")
            return {0: 0}

    @staticmethod
    def get_total_clients() -> int:
        """Get total number of available clients"""
        try:
            TgClient = get_tg_client()

            total = 1  # Main bot
            if TgClient.helper_bots:
                total += len(TgClient.helper_bots)
            return total
        except Exception as e:
            LOGGER.error(f"Error getting total clients: {e}")
            return 1

    @staticmethod
    def get_client_info() -> dict[str, Any]:
        """Get comprehensive client information"""
        try:
            TgClient = get_tg_client()

            return {
                "total_clients": StreamClientManager.get_total_clients(),
                "workload_distribution": StreamClientManager.get_client_workload(),
                "main_bot_id": TgClient.ID,
                "helper_bots_count": len(TgClient.helper_bots)
                if TgClient.helper_bots
                else 0,
            }
        except Exception as e:
            LOGGER.error(f"Error getting client info: {e}")
            TgClient = get_tg_client()
            return {
                "total_clients": 1,
                "workload_distribution": {0: 0},
                "main_bot_id": TgClient.ID,
                "helper_bots_count": 0,
            }
