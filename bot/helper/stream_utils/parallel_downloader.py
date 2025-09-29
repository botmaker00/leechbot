"""
Parallel downloader for regular file downloads
Uses multiple helper bots for faster downloads like HyperDL
"""

import asyncio
import contextlib
import os
import tempfile

from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.types import Message

from bot import LOGGER
from bot.core.config_manager import Config


class ParallelDownloader:
    """
    Parallel file downloader using multiple helper bots
    Based on HyperDL architecture for regular file downloads
    """

    def __init__(self, max_workers: int | None = None):
        self.max_workers = max_workers or min(8, len(self._get_available_clients()))
        self.chunk_size = 1024 * 1024  # 1MB chunks

    def _get_available_clients(self) -> list[tuple[Client, int]]:
        """Get all available clients for parallel downloading"""
        from bot.core.aeon_client import TgClient

        clients = []

        # Add main bot
        if hasattr(TgClient, "bot") and TgClient.bot:
            clients.append((TgClient.bot, 0))

        # Add helper bots
        if hasattr(TgClient, "helper_bots") and TgClient.helper_bots:
            for bot_id, bot in TgClient.helper_bots.items():
                clients.append((bot, bot_id))

        return clients

    def _calculate_chunks(self, file_size: int) -> list[dict]:
        """Calculate optimal chunk distribution across available clients"""
        clients = self._get_available_clients()
        if not clients:
            raise ValueError("No clients available for parallel downloading")

        # Calculate optimal number of chunks
        num_chunks = min(
            self.max_workers, len(clients), max(1, file_size // self.chunk_size)
        )

        if file_size < self.chunk_size:
            num_chunks = 1

        chunk_size = file_size // num_chunks
        chunks = []

        for i in range(num_chunks):
            chunk_start = i * chunk_size
            if i == num_chunks - 1:
                # Last chunk gets any remaining bytes
                chunk_end = file_size - 1
            else:
                chunk_end = chunk_start + chunk_size - 1

            # Assign client using round-robin
            client, client_id = clients[i % len(clients)]

            chunks.append(
                {
                    "index": i,
                    "start": chunk_start,
                    "end": chunk_end,
                    "size": chunk_end - chunk_start + 1,
                    "client_id": client_id,
                    "client": client,
                }
            )

        return chunks

    async def _download_chunk(
        self, message: Message, chunk: dict, temp_dir: str
    ) -> str:
        """Download a single chunk to a temporary file"""
        try:
            # Increment load for this client
            from bot.helper.stream_utils.client_manager import StreamClientManager

            StreamClientManager.increment_load(chunk["client_id"])

            chunk_file = os.path.join(temp_dir, f"chunk_{chunk['index']:03d}")

            with open(chunk_file, "wb") as f:
                current_offset = chunk["start"]

                while current_offset <= chunk["end"]:
                    try:
                        remaining = chunk["end"] - current_offset + 1
                        limit = min(self.chunk_size, remaining)

                        async for data in chunk["client"].stream_media(
                            message, offset=current_offset, limit=limit
                        ):
                            f.write(data)
                            current_offset += len(data)

                            if current_offset > chunk["end"]:
                                # Trim excess data
                                excess = current_offset - chunk["end"] - 1
                                if excess > 0:
                                    f.seek(-excess, 2)  # Seek back from end
                                    f.truncate()
                                break

                        break  # Success

                    except FloodWait as e:
                        await asyncio.sleep(e.value)
                    except Exception as e:
                        error_msg = str(e).lower()
                        if "unauthorized" in error_msg or "auth" in error_msg:
                            LOGGER.error(
                                f"Authentication error in chunk {chunk['index']}: {e}"
                            )
                            raise ConnectionError(
                                f"Telegram authentication failed: {e}"
                            )
                        LOGGER.error(
                            f"Error downloading chunk {chunk['index']}: {e}"
                        )
                        raise

            return chunk_file

        finally:
            # Decrement load for this client
            StreamClientManager.decrement_load(chunk["client_id"])

    async def _combine_chunks(
        self, chunk_files: list[str], output_path: str
    ) -> None:
        """Combine downloaded chunks into final file"""
        try:
            with open(output_path, "wb") as output_file:
                for chunk_file in sorted(chunk_files):
                    if os.path.exists(chunk_file):
                        with open(chunk_file, "rb") as f:
                            while True:
                                data = f.read(64 * 1024)  # 64KB buffer
                                if not data:
                                    break
                                output_file.write(data)

                        # Clean up chunk file
                        with contextlib.suppress(OSError):
                            os.remove(chunk_file)

        except Exception as e:
            LOGGER.error(f"Error combining chunks: {e}")
            raise

    async def download_file_parallel(
        self,
        message: Message,
        output_path: str,
        progress_callback=None,
    ) -> bool:
        """Download file using parallel chunk downloading"""
        try:
            from bot.helper.stream_utils.file_processor import get_fsize, get_media

            media = get_media(message)
            if not media:
                raise ValueError("Message has no media")

            file_size = get_fsize(message)
            if file_size == 0:
                raise ValueError("File size is 0")

            # Check if parallel download is beneficial
            clients = self._get_available_clients()
            if len(clients) <= 1 or file_size < self.chunk_size:
                # Fallback to regular download
                await message.download(file_name=output_path)
                return True

            # Calculate chunks for parallel download
            chunks = self._calculate_chunks(file_size)

            # Create temporary directory for chunks
            temp_dir = tempfile.mkdtemp(prefix="parallel_dl_")

            try:
                # Download chunks in parallel

                tasks = []
                for chunk in chunks:
                    task = asyncio.create_task(
                        self._download_chunk(message, chunk, temp_dir)
                    )
                    tasks.append(task)

                # Wait for all chunks to complete
                chunk_files = await asyncio.gather(*tasks)

                # Combine chunks into final file
                await self._combine_chunks(chunk_files, output_path)

                # Verify file size
                if os.path.exists(output_path):
                    actual_size = os.path.getsize(output_path)
                    if actual_size == file_size:
                        return True
                    LOGGER.error(
                        f"File size mismatch: expected {file_size}, got {actual_size}"
                    )
                    return False
                LOGGER.error("Output file was not created")
                return False

            finally:
                # Clean up temporary directory
                try:
                    import shutil

                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception as e:
                    LOGGER.warning(
                        f"Failed to clean up temp directory {temp_dir}: {e}"
                    )

        except Exception as e:
            LOGGER.error(f"Error in parallel download: {e}")
            # Fallback to regular download
            try:
                await message.download(file_name=output_path)
                return True
            except Exception as fallback_error:
                LOGGER.error(f"Fallback download also failed: {fallback_error}")
                return False

    def should_use_parallel(self, file_size: int) -> bool:
        """Determine if parallel download should be used"""
        clients = self._get_available_clients()
        return (
            len(clients) > 1
            and file_size > self.chunk_size
            and Config.HYPER_THREADS  # Only if hyper threading is enabled
        )
