"""
Compatibility layer for aiofiles to handle different versions
Supports both aiofiles 0.7 (for streamrip) and newer versions (for other features)
"""

import asyncio
import os

# Check aiofiles version and available features
try:
    import aiofiles

    AIOFILES_AVAILABLE = True

    # Check if aiofiles.os module exists (not available in 0.7)
    try:
        import aiofiles.os as aiofiles_os

        AIOFILES_OS_AVAILABLE = True
    except ImportError:
        AIOFILES_OS_AVAILABLE = False

    # Check if aiofiles.os.path module exists (not available in 0.7 and some newer versions)
    try:
        import aiofiles.os.path as aiofiles_os_path

        AIOFILES_OS_PATH_AVAILABLE = True
    except ImportError:
        AIOFILES_OS_PATH_AVAILABLE = False

except ImportError:
    AIOFILES_AVAILABLE = False
    AIOFILES_OS_AVAILABLE = False
    AIOFILES_OS_PATH_AVAILABLE = False

# Feature detection for aiofiles.os functions (available in newer versions)
if AIOFILES_OS_AVAILABLE:
    try:
        from aiofiles.os import makedirs as aio_makedirs

        AIOFILES_HAS_MAKEDIRS = True
    except (ImportError, AttributeError):
        AIOFILES_HAS_MAKEDIRS = False

    try:
        from aiofiles.os import remove as aio_remove

        AIOFILES_HAS_REMOVE = True
    except (ImportError, AttributeError):
        AIOFILES_HAS_REMOVE = False

    try:
        from aiofiles.os import listdir as aio_listdir

        AIOFILES_HAS_LISTDIR = True
    except (ImportError, AttributeError):
        AIOFILES_HAS_LISTDIR = False

    try:
        from aiofiles.os import rename as aio_rename

        AIOFILES_HAS_RENAME = True
    except (ImportError, AttributeError):
        AIOFILES_HAS_RENAME = False

    try:
        from aiofiles.os import rmdir as aio_rmdir

        AIOFILES_HAS_RMDIR = True
    except (ImportError, AttributeError):
        AIOFILES_HAS_RMDIR = False

    try:
        from aiofiles.os import symlink as aio_symlink

        AIOFILES_HAS_SYMLINK = True
    except (ImportError, AttributeError):
        AIOFILES_HAS_SYMLINK = False

    try:
        from aiofiles.os import readlink as aio_readlink

        AIOFILES_HAS_READLINK = True
    except (ImportError, AttributeError):
        AIOFILES_HAS_READLINK = False
else:
    # aiofiles 0.7 doesn't have aiofiles.os module
    AIOFILES_HAS_MAKEDIRS = False
    AIOFILES_HAS_REMOVE = False
    AIOFILES_HAS_LISTDIR = False
    AIOFILES_HAS_RENAME = False
    AIOFILES_HAS_RMDIR = False
    AIOFILES_HAS_SYMLINK = False
    AIOFILES_HAS_READLINK = False

# Feature detection for aiofiles.os.path functions (available in some newer versions)
if AIOFILES_OS_PATH_AVAILABLE:
    try:
        from aiofiles.os.path import exists as aio_path_exists

        AIOFILES_HAS_PATH_EXISTS = True
    except (ImportError, AttributeError):
        AIOFILES_HAS_PATH_EXISTS = False

    try:
        from aiofiles.os.path import isfile as aio_path_isfile

        AIOFILES_HAS_PATH_ISFILE = True
    except (ImportError, AttributeError):
        AIOFILES_HAS_PATH_ISFILE = False

    try:
        from aiofiles.os.path import isdir as aio_path_isdir

        AIOFILES_HAS_PATH_ISDIR = True
    except (ImportError, AttributeError):
        AIOFILES_HAS_PATH_ISDIR = False

    try:
        from aiofiles.os.path import getsize as aio_path_getsize

        AIOFILES_HAS_PATH_GETSIZE = True
    except (ImportError, AttributeError):
        AIOFILES_HAS_PATH_GETSIZE = False

    try:
        from aiofiles.os.path import islink as aio_path_islink

        AIOFILES_HAS_PATH_ISLINK = True
    except (ImportError, AttributeError):
        AIOFILES_HAS_PATH_ISLINK = False

    try:
        from aiofiles.os.path import getmtime as aio_path_getmtime

        AIOFILES_HAS_PATH_GETMTIME = True
    except (ImportError, AttributeError):
        AIOFILES_HAS_PATH_GETMTIME = False
else:
    # aiofiles 0.7 and some newer versions don't have aiofiles.os.path
    AIOFILES_HAS_PATH_EXISTS = False
    AIOFILES_HAS_PATH_ISFILE = False
    AIOFILES_HAS_PATH_ISDIR = False
    AIOFILES_HAS_PATH_GETSIZE = False
    AIOFILES_HAS_PATH_ISLINK = False
    AIOFILES_HAS_PATH_GETMTIME = False


async def makedirs(path, mode=0o777, exist_ok=False):
    """
    Ultra-bulletproof async version of os.makedirs with multiple fallbacks
    """
    if AIOFILES_HAS_MAKEDIRS:
        try:
            return await aio_makedirs(path, mode=mode, exist_ok=exist_ok)
        except Exception:
            pass  # Fall through to other methods

    # Method 1: Try pathlib approach
    try:
        from pathlib import Path

        path_obj = Path(path)
        path_obj.mkdir(mode=mode, parents=True, exist_ok=exist_ok)
        return None
    except Exception:
        pass  # Fall through to next method

    # Method 2: Try direct os.makedirs in current thread
    try:
        import os

        return os.makedirs(path, mode, exist_ok)
    except Exception:
        pass  # Fall through to next method

    # Method 3: Try isolated function in thread pool
    try:

        def _isolated_makedirs():
            import os

            return os.makedirs(path, mode, exist_ok)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _isolated_makedirs)
    except Exception:
        pass  # Fall through to final method

    # Method 4: Final fallback using subprocess (most isolated)
    try:
        import subprocess
        import sys

        cmd = [
            sys.executable,
            "-c",
            f"import os; os.makedirs(r'{path}', mode={mode}, exist_ok={exist_ok})",
        ]

        subprocess.run(cmd, check=True, capture_output=True)
        return None
    except Exception:
        # If all methods fail, raise the original error
        raise OSError(f"Failed to create directory: {path}")


async def remove(path):
    """
    Async version of os.remove with fallback
    """
    if AIOFILES_HAS_REMOVE:
        return await aio_remove(path)

    # Completely isolated fallback to prevent any os module scoping issues
    def _isolated_remove():
        # Import os inside the function to ensure complete isolation
        import os
        return os.remove(path)

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _isolated_remove)


async def listdir(path):
    """
    Ultra-bulletproof async version of os.listdir with multiple fallbacks
    """
    if AIOFILES_HAS_LISTDIR:
        try:
            return await aio_listdir(path)
        except Exception:
            pass  # Fall through to other methods

    # Method 1: Try pathlib approach
    try:
        from pathlib import Path

        path_obj = Path(path)
        if path_obj.exists() and path_obj.is_dir():
            return [item.name for item in path_obj.iterdir()]
    except Exception:
        pass  # Fall through to next method

    # Method 2: Try direct os.listdir in current thread
    try:
        import os

        return os.listdir(path)
    except Exception:
        pass  # Fall through to next method

    # Method 3: Try isolated function in thread pool
    try:

        def _isolated_listdir():
            import os

            return os.listdir(path)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _isolated_listdir)
    except Exception:
        pass  # Fall through to final method

    # Method 4: Final fallback using subprocess (most isolated)
    try:
        import json
        import subprocess
        import sys

        cmd = [
            sys.executable,
            "-c",
            f"import os, json; print(json.dumps(os.listdir(r'{path}')))",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout.strip())
    except Exception:
        # If all methods fail, return empty list
        return []


async def rename(src, dst):
    """
    Async version of os.rename with fallback
    """
    import os

    try:
        if AIOFILES_HAS_RENAME:
            return await aio_rename(src, dst)
        # Fallback to sync version in thread pool
        import os as _os  # Local import to ensure availability in executor

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: _os.rename(src, dst))
    except OSError as e:
        if e.errno == 36:  # File name too long
            # Extract directory and filename
            dst_dir = os.path.dirname(dst)
            dst_filename = os.path.basename(dst)

            # Calculate maximum filename length (usually 255, but let's be safe with 240)
            max_filename_length = 240

            if len(dst_filename) > max_filename_length:
                # Extract prefix, suffix, and extension
                name, ext = os.path.splitext(dst_filename)

                # Try to identify prefix and suffix patterns
                prefix = ""
                suffix = ""
                core_name = name

                # Look for prefix pattern (starts with @hello or similar)
                if name.startswith("@"):
                    parts = name.split(" ", 1)
                    if len(parts) > 1:
                        prefix = parts[0] + " "
                        core_name = parts[1]

                # Look for suffix pattern (ends with @hello or similar)
                if " @" in core_name:
                    core_parts = core_name.rsplit(" @", 1)
                    if len(core_parts) > 1:
                        core_name = core_parts[0]
                        suffix = " @" + core_parts[1]

                # Calculate available space for core name
                reserved_length = len(prefix) + len(suffix) + len(ext)
                available_length = max_filename_length - reserved_length

                if (
                    available_length > 10
                ):  # Ensure we have reasonable space for core name
                    # Truncate core name
                    truncated_core = core_name[:available_length]
                    truncated_filename = f"{prefix}{truncated_core}{suffix}{ext}"
                    truncated_dst = os.path.join(dst_dir, truncated_filename)

                    # Try rename with truncated filename
                    try:
                        if AIOFILES_HAS_RENAME:
                            return await aio_rename(src, truncated_dst)
                        import os as _os

                        loop = asyncio.get_event_loop()
                        return await loop.run_in_executor(
                            None, lambda: _os.rename(src, truncated_dst)
                        )
                    except Exception:
                        raise e
                else:
                    raise e
            else:
                raise e
        else:
            raise e


async def rmdir(path):
    """
    Async version of os.rmdir with fallback
    """
    if AIOFILES_HAS_RMDIR:
        return await aio_rmdir(path)
    # Fallback to sync version in thread pool
    import os as _os  # Local import to ensure availability in executor

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: _os.rmdir(path))


async def symlink(src, dst, target_is_directory=False):
    """
    Async version of os.symlink with fallback
    """
    if AIOFILES_HAS_SYMLINK:
        return await aio_symlink(src, dst, target_is_directory=target_is_directory)
    # Fallback to sync version in thread pool
    import os as _os  # Local import to ensure availability in executor

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, lambda: _os.symlink(src, dst, target_is_directory)
    )


async def readlink(path):
    """
    Async version of os.readlink with fallback
    """
    if AIOFILES_HAS_READLINK:
        return await aio_readlink(path)
    # Fallback to sync version in thread pool
    import os as _os  # Local import to ensure availability in executor

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: _os.readlink(path))


class AsyncPath:
    """
    Async path operations with fallback support
    Uses native aiofiles.os.path functions when available, otherwise falls back to thread pool
    """

    @staticmethod
    async def exists(path):
        """Check if path exists"""
        if AIOFILES_HAS_PATH_EXISTS:
            return await aio_path_exists(path)

        # Ultra-safe fallback using pathlib
        from pathlib import Path

        try:
            # Use pathlib which is more reliable than os.path.exists
            path_obj = Path(path)
            return path_obj.exists()
        except Exception:
            # Final fallback: use the isolated function approach
            def _isolated_exists():
                # Import everything inside to ensure complete isolation
                import os

                return os.path.exists(path)

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _isolated_exists)

    @staticmethod
    async def isfile(path):
        """Check if path is a file"""
        if AIOFILES_HAS_PATH_ISFILE:
            return await aio_path_isfile(path)
        # Fallback to sync version in thread pool
        import os as _os  # Local import to ensure availability in executor

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: _os.path.isfile(path))

    @staticmethod
    async def isdir(path):
        """Check if path is a directory"""
        if AIOFILES_HAS_PATH_ISDIR:
            return await aio_path_isdir(path)
        # Fallback to sync version in thread pool
        import os as _os  # Local import to ensure availability in executor

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: _os.path.isdir(path))

    @staticmethod
    async def getsize(path):
        """Get file size"""
        if AIOFILES_HAS_PATH_GETSIZE:
            return await aio_path_getsize(path)
        # Fallback to sync version in thread pool
        import os as _os  # Local import to ensure availability in executor

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: _os.path.getsize(path))

    @staticmethod
    async def islink(path):
        """Check if path is a symbolic link"""
        if AIOFILES_HAS_PATH_ISLINK:
            return await aio_path_islink(path)
        # Fallback to sync version in thread pool
        import os as _os  # Local import to ensure availability in executor

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: _os.path.islink(path))

    @staticmethod
    async def getmtime(path):
        """Get file modification time"""
        if AIOFILES_HAS_PATH_GETMTIME:
            return await aio_path_getmtime(path)
        # Fallback to sync version in thread pool
        import os as _os  # Local import to ensure availability in executor

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: _os.path.getmtime(path))


# Create aliases for backward compatibility
aiopath = AsyncPath()
path = AsyncPath()  # Alias for direct import as 'path'


def get_aiofiles_info():
    """
    Get information about aiofiles compatibility
    """
    return {
        "aiofiles_available": AIOFILES_AVAILABLE,
        "aiofiles_os_available": AIOFILES_OS_AVAILABLE,
        "aiofiles_os_path_available": AIOFILES_OS_PATH_AVAILABLE,
        "makedirs": AIOFILES_HAS_MAKEDIRS,
        "remove": AIOFILES_HAS_REMOVE,
        "listdir": AIOFILES_HAS_LISTDIR,
        "rename": AIOFILES_HAS_RENAME,
        "rmdir": AIOFILES_HAS_RMDIR,
        "symlink": AIOFILES_HAS_SYMLINK,
        "readlink": AIOFILES_HAS_READLINK,
        "path_exists": AIOFILES_HAS_PATH_EXISTS,
        "path_isfile": AIOFILES_HAS_PATH_ISFILE,
        "path_isdir": AIOFILES_HAS_PATH_ISDIR,
        "path_getsize": AIOFILES_HAS_PATH_GETSIZE,
        "path_islink": AIOFILES_HAS_PATH_ISLINK,
        "path_getmtime": AIOFILES_HAS_PATH_GETMTIME,
    }
