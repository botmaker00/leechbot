#!/usr/bin/env python3
"""
MEGA SDK Import Utility
Handles robust MEGA SDK imports with multiple fallback strategies
"""

import os
import sys
from pathlib import Path


def configure_mega_import():
    """
    Configure and import MEGA SDK with multiple fallback strategies.
    Returns the imported MEGA modules or raises ImportError.
    """
    # Configure library paths
    _configure_mega_library_path()

    # Try multiple import strategies
    return _import_mega_with_fallbacks()


def _configure_mega_library_path():
    """Configure library path for MEGA SDK imports"""
    # Primary installation paths (based on Aeon script)
    mega_paths = [
        "/usr/local/lib/python3.13/dist-packages/mega",
        "/usr/lib/python3/dist-packages/mega",
        "/usr/local/lib/python3.12/dist-packages/mega",
        "/usr/lib/python3.12/dist-packages/mega",
    ]

    # Set library path for all known locations
    lib_paths = [mega_path for mega_path in mega_paths if Path(mega_path).exists()]

    if lib_paths:
        current_ld_path = os.environ.get("LD_LIBRARY_PATH", "")
        new_ld_path = ":".join([*lib_paths, "/usr/local/lib", current_ld_path])
        os.environ["LD_LIBRARY_PATH"] = new_ld_path

        # Also set PYTHONPATH to ensure Python can find the module
        current_python_path = os.environ.get("PYTHONPATH", "")
        python_paths = [str(Path(p).parent) for p in lib_paths]
        new_python_path = ":".join([*python_paths, current_python_path])
        os.environ["PYTHONPATH"] = new_python_path


def _import_mega_with_fallbacks():
    """Try multiple import strategies for MEGA SDK"""

    # Strategy 1: Direct import
    try:
        from mega import MegaApi, MegaError, MegaListener, MegaRequest, MegaTransfer

        return MegaApi, MegaError, MegaListener, MegaRequest, MegaTransfer
    except ImportError:
        pass

    # Strategy 2: Add paths to sys.path and try again
    try:
        # Add MEGA SDK paths to sys.path
        mega_parent_paths = [
            "/usr/local/lib/python3.13/dist-packages",
            "/usr/lib/python3/dist-packages",
            "/usr/local/lib/python3.12/dist-packages",
            "/usr/lib/python3.12/dist-packages",
        ]

        for path in mega_parent_paths:
            if Path(path).exists() and path not in sys.path:
                sys.path.insert(0, path)

        from mega import MegaApi, MegaError, MegaListener, MegaRequest, MegaTransfer

        return MegaApi, MegaError, MegaListener, MegaRequest, MegaTransfer
    except ImportError:
        pass

    # Strategy 3: Dynamic discovery and import
    try:
        # Find MEGA SDK installation dynamically
        for search_path in ["/usr/local/lib", "/usr/lib"]:
            for python_dir in Path(search_path).glob("python*/dist-packages"):
                mega_path = python_dir / "mega"
                if mega_path.exists():
                    # Add to sys.path and set library path
                    if str(python_dir) not in sys.path:
                        sys.path.insert(0, str(python_dir))

                    current_ld_path = os.environ.get("LD_LIBRARY_PATH", "")
                    os.environ["LD_LIBRARY_PATH"] = (
                        f"{mega_path}:/usr/local/lib:{current_ld_path}"
                    )

                    try:
                        from mega import (
                            MegaApi,
                            MegaError,
                            MegaListener,
                            MegaRequest,
                            MegaTransfer,
                        )

                        return (
                            MegaApi,
                            MegaError,
                            MegaListener,
                            MegaRequest,
                            MegaTransfer,
                        )
                    except ImportError:
                        continue
    except Exception:
        pass

    # Final fallback: Raise informative error
    error_msg = (
        "MEGA SDK not found. Please ensure MEGA SDK v4.8.0 is installed. "
        "Expected locations: /usr/local/lib/python3.13/dist-packages/mega"
    )
    raise ImportError(error_msg)


# For direct import compatibility - lazy loading
def __getattr__(name):
    """Support direct imports like 'from mega_utils import MegaApi'"""
    if name in (
        "MegaApi",
        "MegaError",
        "MegaListener",
        "MegaRequest",
        "MegaTransfer",
    ):
        modules = configure_mega_import()
        module_map = {
            "MegaApi": modules[0],
            "MegaError": modules[1],
            "MegaListener": modules[2],
            "MegaRequest": modules[3],
            "MegaTransfer": modules[4],
        }
        return module_map[name]
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
