from re import match as re_match


def is_magnet(url):
    if not isinstance(url, str):
        return False
    return bool(
        re_match(
            r"^magnet:\?.*xt=urn:(btih|btmh):([a-zA-Z0-9]{32,40}|[a-z2-7]{32}).*",
            url,
        )
    )


def is_url(url):
    if not isinstance(url, str):
        return False
    return bool(
        re_match(
            r"^(?!\/)(rtmps?:\/\/|mms:\/\/|rtsp:\/\/|https?:\/\/|ftp:\/\/)?([^\/:]+:[^\/@]+@)?(www\.)?(?=[^\/:\s]+\.[^\/:\s]+)([^\/:\s]+\.[^\/:\s]+)(:\d+)?(\/[^#\s]*[\s\S]*)?(\?[^#\s]*)?(#.*)?$",
            url,
        ),
    )


def is_gdrive_link(url):
    if not isinstance(url, str):
        return False
    return "drive.google.com" in url or "drive.usercontent.google.com" in url


def is_telegram_link(url):
    if not isinstance(url, str):
        return False
    return url.startswith(("https://t.me/", "tg://openmessage?user_id="))


def is_mega_link(url):
    if not isinstance(url, str):
        return False
    return "mega.nz" in url or "mega.co.nz" in url


def get_mega_link_type(url):
    if not isinstance(url, str):
        return "file"  # Default to file if not a string
    return "folder" if "folder" in url or "/#F!" in url else "file"


def is_share_link(url):
    if not isinstance(url, str):
        return False
    return bool(
        re_match(
            r"https?:\/\/.+\.gdtot\.\S+|https?:\/\/(filepress|filebee|appdrive|gdflix)\.\S+",
            url,
        ),
    )


def is_rclone_path(path):
    # Handle integer inputs by returning False (integers are not valid rclone paths)
    if isinstance(path, int):
        return False

    # Convert to string if not already a string
    if not isinstance(path, str):
        try:
            path = str(path)
        except Exception:
            return False

    try:
        return bool(
            re_match(
                r"^(mrcc:)?(?!(magnet:|mtp:|sa:|tp:))(?![- ])[a-zA-Z0-9_\. -]+(?<! ):(?!.*\/\/).*$|^rcl$",
                path,
            ),
        )
    except Exception:
        return False


def is_gdrive_id(id_):
    # Handle integer inputs by returning False (integers are not valid Google Drive IDs)
    if isinstance(id_, int):
        return False

    # Convert to string if not already a string
    if not isinstance(id_, str):
        try:
            id_ = str(id_)
        except Exception:
            return False

    return bool(
        re_match(
            r"^(tp:|sa:|mtp:)?(?:[a-zA-Z0-9-_]{33}|[a-zA-Z0-9_-]{19})$|^gdl$|^(tp:|mtp:)?root$",
            id_,
        ),
    )
