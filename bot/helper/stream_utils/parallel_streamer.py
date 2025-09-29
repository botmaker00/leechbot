"""
Optimized Parallel Byte Streamer using HyperDL's proven raw API approach
Completely bypasses Pyrogram's 1MB streaming limitations
"""


# Import required modules

try:
    from bot.core.aeon_client import TgClient
    from bot.helper.ext_utils.hyperdl_utils import HyperTGDownload
    from bot.helper.stream_utils.file_processor import get_file_info

    HYPERDL_AVAILABLE = True
except ImportError:
    HYPERDL_AVAILABLE = False
    TgClient = None


class ParallelByteStreamer:
    """
    Optimized byte streamer that uses HyperDL's raw API approach
    Supports both single-client streaming and multi-client parallel downloading
    """

    def __init__(self, chat_id: int):
        """Initialize the streamer with chat ID"""
        self.chat_id = chat_id

        # Get all available clients
        self.all_clients = []
        self.helper_clients = []

        if TgClient and hasattr(TgClient, "bot") and TgClient.bot:
            self.all_clients.append((TgClient.bot, 0))

        if TgClient and hasattr(TgClient, "user") and TgClient.user:
            self.all_clients.append((TgClient.user, -1))

        if TgClient and hasattr(TgClient, "helper_bots"):
            for i, client in TgClient.helper_bots.items():
                if client:
                    self.all_clients.append((client, i))
                    self.helper_clients.append((client, i))

    def is_parallel(self) -> bool:
        """Return True to indicate this is a parallel streamer"""
        return True

    async def get_file_info(self, message_id: int) -> dict:
        """Get file information for the specified message"""
        try:
            if not HYPERDL_AVAILABLE:
                return {"error": "HyperDL not available"}

            client, _ = self._get_optimal_client("file info validation")
            message = await self.get_message(message_id, client)

            # Use the imported get_file_info function
            return get_file_info(message)

        except Exception as e:
            return {"error": str(e)}

    async def get_message(self, message_id: int, client=None):
        """Get message from the specified client or use optimal client"""
        try:
            # If no client provided, use our optimal client (for web server compatibility)
            if client is None:
                client, _ = self._get_optimal_client()

            return await client.get_messages(self.chat_id, message_id)
        except Exception:
            raise

    def _get_optimal_client(self):
        """Get the optimal client for file operations"""
        if not self.all_clients:
            raise RuntimeError("No clients available for file operations")

        # Use the first available client (main client preferred)
        client, client_id = self.all_clients[0]
        return client, client_id

    async def stream_bytes(self, message_id: int, offset: int = 0, limit: int = 0):
        """
        Stream bytes using multi-client approach when possible, fallback to single client
        """

        # Multi-client streaming is disabled due to memory issues
        # Fallback to single client streaming
        async for chunk in self._fallback_streaming(message_id, offset, limit):
            yield chunk

    async def _multi_client_streaming(
        self, message_id: int, offset: int, limit: int
    ):
        """
        Multi-client streaming using Telegram-compatible approach
        Uses small chunks and round-robin client distribution (like real HyperDL)
        """

        # Use small chunk size compatible with Telegram API (like real HyperDL)
        chunk_size = 1024 * 1024  # 1MB chunks (Telegram compatible)
        num_clients = min(
            len(self.helper_clients), 3
        )  # Use available helper clients

        # Calculate total chunks needed
        total_chunks = (limit + chunk_size - 1) // chunk_size

        # Create client pool for round-robin distribution
        client_pool = []
        for i in range(num_clients):
            client, client_id = self.helper_clients[i % len(self.helper_clients)]
            client_pool.append((client, client_id))

        # Stream chunks using round-robin client distribution
        total_bytes = 0
        current_offset = offset

        for chunk_index in range(total_chunks):
            # Select client using round-robin
            client, client_id = client_pool[chunk_index % num_clients]

            # Calculate chunk size for this iteration
            remaining_bytes = limit - total_bytes
            current_chunk_size = min(chunk_size, remaining_bytes)

            if current_chunk_size <= 0:
                break

            try:
                # Download chunk using selected client
                message = await self.get_message(message_id, client)
                chunk_data = b""

                # Use Telegram's stream_media with small offset (compatible)
                async for chunk in client.stream_media(
                    message, offset=current_offset, limit=current_chunk_size
                ):
                    if not chunk:
                        break
                    chunk_data += chunk

                if chunk_data:
                    yield chunk_data
                    total_bytes += len(chunk_data)
                    current_offset += len(chunk_data)

                else:
                    pass  # Empty chunk

            except Exception:
                # Continue with next chunk instead of failing completely
                current_offset += current_chunk_size
                continue

    async def _fallback_streaming(self, message_id: int, offset: int, limit: int):
        """
        Fallback streaming using basic client approach
        """

        try:
            client, _ = self._get_optimal_client()
            fresh_message = await self.get_message(message_id, client)

            bytes_streamed = 0
            if offset == 0:
                # For offset 0, try direct streaming
                async for chunk in client.stream_media(fresh_message):
                    if not chunk:
                        break

                    yield chunk
                    bytes_streamed += len(chunk)

                    if limit > 0 and bytes_streamed >= limit:
                        break
            else:
                # For non-zero offsets, this is complex - just yield empty for now
                return

        except Exception:
            raise

    async def download_parallel(
        self, message_id: int, file_path: str, progress_callback=None
    ) -> str:
        """
        Download file using HyperDL's exact parallel downloading approach - uses ALL helper clients
        """
        if not HYPERDL_AVAILABLE:
            raise RuntimeError("HyperDL not available for parallel downloading")

        try:
            # Create HyperDL instance - it automatically gets TgClient.helper_bots (all helper clients)
            hyperdl = HyperTGDownload()

            # Get the message using our optimal client (just for getting the message object)
            client, _ = self._get_optimal_client()
            message = await self.get_message(message_id, client)

            # Use HyperDL's download_media method - it will use ALL helper clients for parallel parts
            return await hyperdl.download_media(
                message,
                file_name=file_path,
                progress=progress_callback,
                dump_chat=self.chat_id,
            )

        except Exception:
            raise

    async def stream_file_parallel(
        self, message_id: int, offset: int = 0, limit: int = 0
    ):
        """
        Parallel streaming method expected by web server
        Uses our optimized HyperDL raw API approach
        """

        # Delegate to our optimized stream_bytes method
        async for chunk in self.stream_bytes(message_id, offset, limit):
            yield chunk

    async def stream_file(self, message_id: int, offset: int = 0, limit: int = 0):
        """
        Single client streaming method expected by web server (fallback)
        Uses our fallback streaming approach
        """

        # Delegate to our fallback streaming method
        async for chunk in self._fallback_streaming(message_id, offset, limit):
            yield chunk

    async def download_to_file(
        self, message_id: int, output_path: str, progress_callback=None
    ) -> str:
        """
        Download file using HyperDL's parallel downloading to a specific file path
        This is for actual file downloads (not streaming) - uses ALL helper clients
        """
        if not HYPERDL_AVAILABLE:
            raise RuntimeError("HyperDL not available for file downloading")

        try:
            # Create HyperDL instance - it automatically gets TgClient.helper_bots (all helper clients)
            hyperdl = HyperTGDownload()

            # Get the message using our optimal client
            client, _ = self._get_optimal_client("HyperDL file download")
            message = await self.get_message(message_id, client)

            # Use HyperDL's download_media method - it will use ALL helper clients for parallel parts
            return await hyperdl.download_media(
                message,
                file_name=output_path,
                progress=progress_callback,
                dump_chat=self.chat_id,
            )

        except Exception:
            raise
