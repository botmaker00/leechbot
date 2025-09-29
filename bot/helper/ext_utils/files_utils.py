import gc
import math
import re
import shlex
from asyncio import create_subprocess_exec, sleep, wait_for
from asyncio.subprocess import PIPE
from glob import escape as glob_escape
from glob import glob
from os import path as ospath
from os import readlink, walk
from pathlib import Path
from re import IGNORECASE, escape
from re import search as re_search
from re import split as re_split
from urllib.parse import unquote

from aioshutil import rmtree as aiormtree
from magic import Magic

from bot import DOWNLOAD_DIR, LOGGER
from bot.core.torrent_manager import TorrentManager
from bot.helper.ext_utils.aiofiles_compat import listdir, remove, rmdir, symlink
from bot.helper.ext_utils.aiofiles_compat import makedirs as aiomakedirs
from bot.helper.ext_utils.aiofiles_compat import path as aiopath
from bot.helper.ext_utils.aiofiles_compat import readlink as aioreadlink

from .bot_utils import cmd_exec, sync_to_async
from .exceptions import NotSupportedExtractionArchive
from .gc_utils import smart_garbage_collection

ARCH_EXT = [
    ".tar.bz2",
    ".tar.gz",
    ".bz2",
    ".gz",
    ".tar.xz",
    ".tar",
    ".tbz2",
    ".tgz",
    ".lzma2",
    ".zip",
    ".7z",
    ".z",
    ".rar",
    ".iso",
    ".wim",
    ".cab",
    ".apm",
    ".arj",
    ".chm",
    ".cpio",
    ".cramfs",
    ".deb",
    ".dmg",
    ".fat",
    ".hfs",
    ".lzh",
    ".lzma",
    ".mbr",
    ".msi",
    ".mslz",
    ".nsis",
    ".ntfs",
    ".rpm",
    ".squashfs",
    ".udf",
    ".vhd",
    ".xar",
    ".zst",
    ".zstd",
    ".cbz",
    ".apfs",
    ".ar",
    ".qcow",
    ".macho",
    ".exe",
    ".dll",
    ".sys",
    ".pmd",
    ".swf",
    ".swfc",
    ".simg",
    ".vdi",
    ".vhdx",
    ".vmdk",
    ".gzip",
    ".lzma86",
    ".sha256",
    ".sha512",
    ".sha224",
    ".sha384",
    ".sha1",
    ".md5",
    ".crc32",
    ".crc64",
]

FIRST_SPLIT_REGEX = (
    r"\.part0*1\.rar$|\.7z\.0*1$|\.zip\.0*1$|^(?!.*\.part\d+\.rar$).*\.rar$"
)

SPLIT_REGEX = r"\.r\d+$|\.7z\.\d+$|\.z\d+$|\.zip\.\d+$|\.part\d+\.rar$"


def is_first_archive_split(file):
    return bool(re_search(FIRST_SPLIT_REGEX, file.lower(), IGNORECASE))


def is_archive(file):
    return file.strip().lower().endswith(tuple(ARCH_EXT))


def is_archive_split(file):
    return bool(re_search(SPLIT_REGEX, file.lower(), IGNORECASE))


async def sanitize_file_path(file_path):
    """
    Sanitize file path to handle special characters and spaces.
    Returns a list of potential fixed paths to try.

    Args:
        file_path (str): Original file path

    Returns:
        list: List of sanitized file paths to try
    """
    if not file_path:
        return []

    fixed_paths = []

    # Method 1: Replace spaces with underscores
    if " " in file_path:
        fixed_paths.append(file_path.replace(" ", "_"))

    # Method 2: Quote the path for shell safety
    quoted_path = shlex.quote(file_path)
    if quoted_path != file_path:
        fixed_paths.append(quoted_path.strip("'\""))

    # Method 3: Use pathlib for normalization
    try:
        normalized_path = str(Path(file_path).resolve())
        if normalized_path != file_path:
            fixed_paths.append(normalized_path)
    except Exception:
        pass  # Skip if path normalization fails

    # Method 4: Handle special characters by escaping
    escaped_path = re.sub(r"([()[\]{}])", r"\\\1", file_path)
    if escaped_path != file_path:
        fixed_paths.append(escaped_path)

    # Method 5: URL decode if path contains encoded characters
    decoded_path = unquote(file_path)
    if decoded_path != file_path:
        fixed_paths.append(decoded_path)

    return fixed_paths


async def clean_target(path):
    if await aiopath.exists(path):
        LOGGER.info(f"Cleaning Target: {path}")
        try:
            if await aiopath.isdir(path):
                await aiormtree(path, ignore_errors=True)
            else:
                await remove(path)
        except Exception as e:
            LOGGER.error(str(e))


async def clean_download(path):
    if await aiopath.exists(path):
        LOGGER.info(f"Cleaning Download: {path}")
        try:
            await aiormtree(path, ignore_errors=True)
        except Exception as e:
            LOGGER.error(str(e))


async def clean_all():
    await TorrentManager.remove_all()
    try:
        LOGGER.info("Cleaning Download Directory")
        await aiormtree(DOWNLOAD_DIR, ignore_errors=True)
    except Exception as e:
        LOGGER.error(f"Error cleaning download directory: {e}")
        # Fallback to using rm command if aiormtree fails
        LOGGER.info("Falling back to rm command")
        await (await create_subprocess_exec("rm", "-rf", DOWNLOAD_DIR)).wait()

    # Ensure the download directory exists
    await aiomakedirs(DOWNLOAD_DIR, exist_ok=True)

    # Force garbage collection after cleaning
    smart_garbage_collection(aggressive=True)


async def clean_unwanted(opath):
    LOGGER.info(f"Cleaning unwanted files/folders: {opath}")
    for dirpath, _, files in await sync_to_async(walk, opath, topdown=False):
        for filee in files:
            f_path = ospath.join(dirpath, filee)
            if filee.strip().endswith(".parts") and filee.startswith("."):
                await remove(f_path)
        if dirpath.strip().endswith(".unwanted"):
            await aiormtree(dirpath, ignore_errors=True)
    for dirpath, _, __ in await sync_to_async(walk, opath, topdown=False):
        if not await listdir(dirpath):
            await rmdir(dirpath)


async def get_path_size(opath):
    total_size = 0
    if await aiopath.isfile(opath):
        if await aiopath.islink(opath):
            opath = await aioreadlink(opath)
        return await aiopath.getsize(opath)
    for root, _, files in await sync_to_async(walk, opath):
        for f in files:
            abs_path = ospath.join(root, f)
            if await aiopath.islink(abs_path):
                abs_path = await aioreadlink(abs_path)
            total_size += await aiopath.getsize(abs_path)
    return total_size


async def count_files_and_folders(opath):
    total_files = 0
    total_folders = 0
    for _, dirs, files in await sync_to_async(walk, opath):
        total_files += len(files)
        total_folders += len(dirs)
    return total_folders, total_files


def get_base_name(orig_path):
    extension = next(
        (ext for ext in ARCH_EXT if orig_path.strip().lower().endswith(ext)),
        "",
    )
    if extension != "":
        return re_split(f"{extension}$", orig_path, maxsplit=1, flags=IGNORECASE)[0]
    raise NotSupportedExtractionArchive("File format not supported for extraction")


async def create_recursive_symlink(source, destination):
    if ospath.isdir(source):
        await aiomakedirs(destination, exist_ok=True)
        for item in await listdir(source):
            item_source = ospath.join(source, item)
            item_dest = ospath.join(destination, item)
            await create_recursive_symlink(item_source, item_dest)
    elif ospath.isfile(source):
        try:
            await symlink(source, destination)
        except FileExistsError:
            LOGGER.error(f"Shortcut already exists: {destination}")
        except Exception as e:
            LOGGER.error(f"Error creating shortcut for {source}: {e}")


async def get_mime_type(file_path):
    if ospath.islink(file_path):
        file_path = readlink(file_path)
    try:
        mime = Magic(mime=True)
        mime_type = mime.from_file(file_path)
        return mime_type or "text/plain"
    except Exception as e:
        LOGGER.error(f"Error getting mime type for {file_path}: {e}")
        return "text/plain"
    finally:
        # Explicitly delete the Magic object to free resources
        del mime
        # Force garbage collection after handling large files
        if ospath.getsize(file_path) > 100 * 1024 * 1024:  # 100MB
            smart_garbage_collection(aggressive=False)


# Non-async version for backward compatibility
def get_mime_type_sync(file_path):
    if ospath.islink(file_path):
        file_path = readlink(file_path)
    mime = None
    try:
        mime = Magic(mime=True)
        mime_type = mime.from_file(file_path)
        return mime_type or "text/plain"
    except Exception as e:
        LOGGER.error(f"Error getting mime type for {file_path}: {e}")
        return "text/plain"
    finally:
        # Explicitly delete the Magic object to free resources
        if mime:
            del mime
        # Optimized garbage collection only for very large files
        if (
            ospath.getsize(file_path) > 500 * 1024 * 1024
        ):  # Increased threshold to 500MB
            gc.collect(0)  # Only collect generation 0 for better performance


async def remove_excluded_files(fpath, ee):
    for root, _, files in await sync_to_async(walk, fpath):
        for f in files:
            if f.strip().lower().endswith(tuple(ee)):
                await remove(ospath.join(root, f))


async def join_files(opath):
    files = await listdir(opath)
    results = []
    exists = False
    for file_ in files:
        if re_search(r"\.0+2$", file_) and await get_mime_type(
            f"{opath}/{file_}"
        ) not in ["application/x-7z-compressed", "application/zip"]:
            exists = True
            final_name = file_.rsplit(".", 1)[0]
            fpath = f"{opath}/{final_name}"

            # Execute the command
            cmd = f'cat "{fpath}."* > "{fpath}"'
            _, stderr, code = await cmd_exec(
                cmd,
                shell=True,
            )
            if code != 0:
                LOGGER.error(f"Failed to join {final_name}, stderr: {stderr}")
                if await aiopath.isfile(fpath):
                    await remove(fpath)
            else:
                results.append(final_name)

    if not exists:
        pass
    elif results:
        LOGGER.info("Join Completed!")
        for res in results:
            for file_ in files:
                if re_search(rf"{escape(res)}\.0[0-9]+$", file_):
                    await remove(f"{opath}/{file_}")


async def split_file(f_path, split_size, listener):
    """
    Split a file into multiple parts using the Linux split command.

    Args:
        f_path: Path to the file to split
        split_size: Size of each split in bytes
        listener: Listener object for tracking progress and cancellation

    Returns:
        bool: True if splitting was successful, False otherwise
    """
    if listener.is_cancelled:
        return False

    # Check if input file exists
    if not await aiopath.exists(f_path):
        LOGGER.error(f"Split input file does not exist: {f_path}")
        return False

    # Get file size for logging (Old Aeon-MLTB logic - simple and clean)
    try:
        file_size = await aiopath.getsize(f_path)
        file_size_gb = file_size / (1024 * 1024 * 1024)
        parts = math.ceil(file_size / split_size)

        # Log detailed information about the splitting operation
        LOGGER.info(f"Splitting file: {f_path}")
        LOGGER.info(f"File size: {file_size_gb:.2f} GiB")
        LOGGER.info(f"Split size: {split_size / (1024 * 1024 * 1024):.2f} GiB")
        LOGGER.info(f"Expected parts: {parts}")
    except Exception as e:
        LOGGER.error(f"Error calculating file size: {e}")
        # Continue with the split operation anyway

    # Create the command (Old Aeon-MLTB logic - trust the split_size passed from proceed_split)
    # The split_size has already been validated in proceed_split and get_user_split_size
    split_size_bytes = int(split_size)

    # Set the working directory to the file's directory to avoid path issues
    cwd = ospath.dirname(f_path)
    file_name = ospath.basename(f_path)
    out_name = f"{file_name}."

    # Use relative paths when working directory is set
    cmd = [
        "split",
        "--numeric-suffixes=1",
        "--suffix-length=3",
        f"--bytes={split_size_bytes}",
        file_name,
        out_name,
    ]

    # Execute the command
    try:
        listener.subproc = await create_subprocess_exec(
            *cmd,
            stderr=PIPE,
            cwd=cwd,
        )

        _, stderr = await listener.subproc.communicate()
        code = listener.subproc.returncode

        if listener.is_cancelled:
            return False
        if code == -9:
            listener.is_cancelled = True
            return False
        if code != 0:
            try:
                stderr = stderr.decode().strip()
            except Exception:
                stderr = "Unable to decode the error!"
            LOGGER.error(
                f"Split command failed with code {code}: {stderr}. File: {f_path}"
            )
            LOGGER.error(f"Split command was: {' '.join(cmd)}")
            return False

        # Log successful command execution
        LOGGER.info(f"Split command executed successfully for: {f_path}")

        # Verify the split was successful by checking if at least one split file exists
        # Use the working directory and relative paths for pattern matching
        # Need to escape special characters in filenames for glob patterns

        escaped_out_name = glob_escape(out_name)
        escaped_file_name = glob_escape(file_name)

        split_patterns = [
            ospath.join(
                cwd, f"{escaped_out_name}*"
            ),  # Standard pattern: filename.001, filename.002, etc.
            ospath.join(
                cwd, f"{escaped_file_name}.*"
            ),  # Alternative pattern: original_file.001, original_file.002, etc.
            ospath.join(
                cwd, "*.0[0-9][0-9]"
            ),  # Fallback pattern: any file ending with .001, .002, etc.
        ]

        split_files = []
        for pattern in split_patterns:
            files = glob(pattern)
            if files:
                # Filter to only include files that start with our filename
                # This is needed for the fallback pattern
                filtered_files = [
                    f for f in files if ospath.basename(f).startswith(file_name)
                ]
                if filtered_files:
                    split_files = filtered_files
                    break

        if not split_files:
            # Additional debugging: check what files exist in the directory
            try:
                all_files = await listdir(cwd)
                # Filter files that might be split files
                potential_split_files = [
                    f for f in all_files if file_name in f and "." in f
                ]
                LOGGER.error(
                    f"Split command completed but no split files were created: {f_path}. "
                    f"Files in directory: {len(all_files)} total. "
                    f"Potential split files: {potential_split_files[:5]}..."
                )
                LOGGER.error(f"Searched patterns: {split_patterns}")
            except Exception as e:
                LOGGER.error(
                    f"Split command completed but no split files were created: {f_path}. "
                    f"Could not list directory: {e}"
                )
            return False

        # Simple validation - just log the split files created (Old Aeon-MLTB approach)
        LOGGER.info(f"Successfully split {f_path} into {len(split_files)} parts")

        # Log the first few split file names for debugging
        if len(split_files) <= 5:
            LOGGER.info(
                f"Split files created: {[ospath.basename(f) for f in split_files]}"
            )
        else:
            LOGGER.info(
                f"Split files created: {[ospath.basename(f) for f in split_files[:3]]} ... {[ospath.basename(f) for f in split_files[-2:]]}"
            )

        return True
    except Exception as e:
        LOGGER.error(f"Error during file splitting: {e}")
        return False


class SevenZ:
    def __init__(self, listener):
        self._listener = listener
        self._processed_bytes = 0
        self._percentage = "0%"

    @property
    def processed_bytes(self):
        return self._processed_bytes

    @property
    def progress(self):
        return self._percentage

    async def _sevenz_progress(self):
        pattern = r"(\d+)\s+bytes|Total Physical Size\s*=\s*(\d+)"
        while not (
            self._listener.subproc.returncode is not None
            or self._listener.is_cancelled
            or self._listener.subproc.stdout.at_eof()
        ):
            try:
                line = await wait_for(self._listener.subproc.stdout.readline(), 2)
            except Exception:
                break
            line = line.decode().strip()
            if match := re_search(pattern, line):
                self._listener.subsize = int(match[1] or match[2])
            await sleep(0.05)
        s = b""
        while not (
            self._listener.is_cancelled
            or self._listener.subproc.returncode is not None
            or self._listener.subproc.stdout.at_eof()
        ):
            try:
                char = await wait_for(self._listener.subproc.stdout.read(1), 60)
            except Exception:
                break
            if not char:
                break
            s += char
            if char == b"%":
                try:
                    self._percentage = s.decode().rsplit(" ", 1)[-1].strip()
                    self._processed_bytes = (
                        int(self._percentage.strip("%")) / 100
                    ) * self._listener.subsize
                except Exception:
                    self._processed_bytes = 0
                    self._percentage = "0%"
                s = b""
            await sleep(0.05)

        self._processed_bytes = 0
        self._percentage = "0%"

    async def extract(self, f_path, t_path, pswd):
        cmd = [
            "7z",
            "x",
            f"-p{pswd}",
            f_path,
            f"-o{t_path}",
            "-aot",
            "-xr!@PaxHeader",
            "-bsp1",
            "-bse1",
            "-bb3",
        ]
        if not pswd:
            del cmd[2]
        if self._listener.is_cancelled:
            return False

        # Execute the command
        self._listener.subproc = await create_subprocess_exec(
            *cmd,
            stdout=PIPE,
            stderr=PIPE,
        )
        await self._sevenz_progress()
        _, stderr = await self._listener.subproc.communicate()
        code = self._listener.subproc.returncode

        if self._listener.is_cancelled:
            return False
        if code == -9:
            self._listener.is_cancelled = True
            return False
        if code != 0:
            try:
                stderr = stderr.decode().strip()
            except Exception:
                stderr = "Unable to decode the error!"
            LOGGER.error(f"{stderr}. Unable to extract archive!. Path: {f_path}")

            # Clean up any partially extracted files to prevent zero-size file issues
            try:
                if await aiopath.exists(t_path):
                    extracted_files = await listdir(t_path)
                    if extracted_files:
                        LOGGER.warning(
                            f"Cleaning up {len(extracted_files)} partially extracted files from failed extraction"
                        )
                        await aiormtree(t_path, ignore_errors=True)
                        await aiomakedirs(t_path, exist_ok=True)
            except Exception as cleanup_error:
                LOGGER.error(f"Error during extraction cleanup: {cleanup_error}")

        return code

    async def zip(self, dl_path, up_path, pswd):
        size = await get_path_size(dl_path)
        split_size = self._listener.split_size
        cmd = [
            "7z",
            f"-v{split_size}b",
            "a",
            "-mx=0",
            f"-p{pswd}",
            up_path,
            dl_path,
            "-bsp1",
            "-bse1",
            "-bb3",
        ]
        if self._listener.is_leech and int(size) > self._listener.split_size:
            if not pswd:
                del cmd[4]
            LOGGER.info(f"Zip: orig_path: {dl_path}, zip_path: {up_path}.0*")
        else:
            del cmd[1]
            if not pswd:
                del cmd[3]
            LOGGER.info(f"Zip: orig_path: {dl_path}, zip_path: {up_path}")
        if self._listener.is_cancelled:
            return False

        # Execute the command
        self._listener.subproc = await create_subprocess_exec(
            *cmd,
            stdout=PIPE,
            stderr=PIPE,
        )
        await self._sevenz_progress()
        _, stderr = await self._listener.subproc.communicate()
        code = self._listener.subproc.returncode

        if self._listener.is_cancelled:
            return False
        if code == -9:
            self._listener.is_cancelled = True
            return False
        if code == 0:
            await clean_target(dl_path)
            return up_path
        if await aiopath.exists(up_path):
            await remove(up_path)
        try:
            stderr = stderr.decode().strip()
        except Exception:
            stderr = "Unable to decode the error!"
        LOGGER.error(f"{stderr}. Unable to zip this path: {dl_path}")
        return dl_path
