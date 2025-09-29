# ruff: noqa
from base64 import b64decode, b64encode
from hashlib import sha256
from http.cookiejar import MozillaCookieJar
from json import loads
from os import path as ospath
from os.path import join as path_join
from re import findall, match, search
from time import sleep
from urllib.parse import parse_qs, urlparse, quote, unquote
from uuid import uuid4

from cloudscraper import create_scraper
from lxml.etree import HTML
from requests import RequestException, Session, get, post
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from bot.core.config_manager import Config
from bot.helper.ext_utils.exceptions import DirectDownloadLinkException
from bot.helper.ext_utils.help_messages import PASSWORD_ERROR_MESSAGE
from bot.helper.ext_utils.links_utils import is_share_link
from bot.helper.ext_utils.status_utils import speed_string_to_bytes

# Import logging
from logging import getLogger

LOGGER = getLogger(__name__)

user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0"

# Mega-Debrid supported sites - will be fetched dynamically from API
mega_debrid_supported_sites = []

debrid_link_supported_sites = [
    "1024tera.com",
    "1024terabox.com",
    "1dl.net",
    "1fichier.com",
    "24hd.club",
    "449unceremoniousnasoseptal.com",
    "4funbox.com",
    "4tube.com",
    "academicearth.org",
    "acast.com",
    "add-anime.net",
    "air.mozilla.org",
    "albavido.xyz",
    "alterupload.com",
    "alphaporno.com",
    "amazonaws.com",
    "anime789.com",
    "animalist.com",
    "animalplanet.com",
    "apkadmin.com",
    "aparat.com",
    "anysex.com",
    "audi-mediacenter.com",
    "audioboom.com",
    "audiomack.com",
    "bayfiles.com",
    "beeg.com",
    "camdemy.com",
    "chilloutzone.net",
    "cjoint.net",
    "cinema.arte.tv",
    "clickndownload.org",
    "clicknupload.cc",
    "clicknupload.club",
    "clicknupload.co",
    "clicknupload.download",
    "clicknupload.link",
    "clicknupload.org",
    "clubic.com",
    "clyp.it",
    "concert.arte.tv",
    "creative.arte.tv",
    "daclips.in",
    "dailyplanet.pw",
    "dailymail.co.uk",
    "dailymotion.com",
    "ddc.arte.tv",
    "ddownload.com",
    "ddl.to",
    "democracynow.org",
    "depositfiles.com",
    "desfichiers.com",
    "destinationamerica.com",
    "dfichiers.com",
    "diasfem.com",
    "dl4free.com",
    "dl.free.fr",
    "dood.cx",
    "dood.la",
    "dood.pm",
    "dood.re",
    "dood.sh",
    "dood.so",
    "dood.stream",
    "dood.video",
    "dood.watch",
    "dood.ws",
    "dood.yt",
    "dooood.com",
    "doods.pro",
    "doods.yt",
    "drop.download",
    "dropapk.to",
    "dropbox.com",
    "ds2play.com",
    "ds2video.com",
    "dutrag.com",
    "e.pcloud.link",
    "ebaumsworld.com",
    "easybytez.com",
    "easybytez.eu",
    "easybytez.me",
    "easyupload.io",
    "eitb.tv",
    "elfile.net",
    "elitefile.net",
    "emload.com",
    "embedwish.com",
    "embedsito.com",
    "fcdn.stream",
    "fastfile.cc",
    "feurl.com",
    "femax20.com",
    "fembed-hd.com",
    "fembed.com",
    "fembed9hd.com",
    "femoload.xyz",
    "file.al",
    "fileaxa.com",
    "filecat.net",
    "filedot.to",
    "filedot.xyz",
    "filefactory.com",
    "filelions.co",
    "filelions.live",
    "filelions.online",
    "filelions.site",
    "filelions.to",
    "filenext.com",
    "filer.net",
    "filerice.com",
    "filesfly.cc",
    "filespace.com",
    "filestore.me",
    "filextras.com",
    "fikper.com",
    "flashbit.cc",
    "flipagram.com",
    "footyroom.com",
    "formula1.com",
    "franceculture.fr",
    "free.fr",
    "freeterabox.com",
    "future.arte.tv",
    "gameinformer.com",
    "gamersyde.com",
    "gcloud.live",
    "gigapeta.com",
    "gibibox.com",
    "github.com",
    "gofile.io",
    "goloady.com",
    "goaibox.com",
    "gorillavid.in",
    "hellporno.com",
    "hentai.animestigma.com",
    "highload.to",
    "hitf.cc",
    "hitfile.net",
    "hornbunny.com",
    "hotfile.io",
    "html5-player.libsyn.com",
    "hulkshare.com",
    "hxfile.co",
    "icerbox.com",
    "imdb.com",
    "info.arte.tv",
    "instagram.com",
    "investigationdiscovery.com",
    "isra.cloud",
    "itar-tass.com",
    "jamendo.com",
    "jove.com",
    "jplayer.net",
    "jumploads.com",
    "k.to",
    "k2s.cc",
    "katfile.com",
    "keep2share.cc",
    "keep2share.com",
    "keek.com",
    "keezmovies.com",
    "khanacademy.org",
    "kickstarter.com",
    "kissmovies.net",
    "kitabmarkaz.xyz",
    "krasview.ru",
    "krakenfiles.com",
    "kshared.com",
    "la7.it",
    "lbx.to",
    "lci.fr",
    "libsyn.com",
    "linkbox.to",
    "load.to",
    "liveleak.com",
    "livestream.com",
    "lulacloud.com",
    "m6.fr",
    "mediafile.cc",
    "mediafire.com",
    "mediafirefolder.com",
    "mediashore.org",
    "megadl.fr",
    "megadl.org",
    "mega.co.nz",
    "mega.nz",
    "mesfichiers.fr",
    "mesfichiers.org",
    "metacritic.com",
    "mexa.sh",
    "mexashare.com",
    "mgoon.com",
    "mirrobox.com",
    "mixcloud.com",
    "mixdrop.club",
    "mixdrop.co",
    "mixdrop.sx",
    "mixdrop.to",
    "modsbase.com",
    "momerybox.com",
    "mojvideo.com",
    "moviemaniac.org",
    "movpod.in",
    "mrdhan.com",
    "mx-sh.net",
    "mycloudz.cc",
    "musicplayon.com",
    "myspass.de",
    "myfile.is",
    "nephobox.com",
    "nelion.me",
    "new.livestream.com",
    "news.yahoo.com",
    "nitro.download",
    "nitroflare.com",
    "noregx.debrid.link",
    "odatv.com",
    "onionstudios.com",
    "opvid.online",
    "opvid.org",
    "ora.tv",
    "osdn.net",
    "pcloud.com",
    "piecejointe.net",
    "pixeldrain.com",
    "play.fm",
    "play.lcp.fr",
    "player.vimeo.com",
    "player.vimeopro.com",
    "plays.tv",
    "playvid.com",
    "pjointe.com",
    "pornhd.com",
    "pornhub.com",
    "prefiles.com",
    "pyvideo.org",
    "racaty.com",
    "rapidgator.asia",
    "rapidgator.net",
    "reputationsheriffkennethsand.com",
    "reverbnation.com",
    "revision3.com",
    "rg.to",
    "rts.ch",
    "rtve.es",
    "salefiles.com",
    "sbs.com.au",
    "sciencechannel.com",
    "screen.yahoo.com",
    "scribd.com",
    "seeker.com",
    "send.cm",
    "sendspace.com",
    "sexhd.co",
    "shrdsk.me",
    "sharemods.com",
    "sharinglink.club",
    "sites.arte.tv",
    "skysports.com",
    "slmaxed.com",
    "sltube.org",
    "slwatch.co",
    "solidfiles.com",
    "soundcloud.com",
    "soundgasm.net",
    "steamcommunity.com",
    "steampowered.com",
    "store.steampowered.com",
    "stream.cz",
    "streamable.com",
    "streamcloud.eu",
    "streamhub.ink",
    "streamhub.to",
    "streamlare.com",
    "streamtape.cc",
    "streamtape.co",
    "streamtape.com",
    "streamtape.net",
    "streamtape.to",
    "streamtape.wf",
    "streamtape.xyz",
    "streamta.pe",
    "streamvid.net",
    "streamwish.to",
    "subyshare.com",
    "sunporno.com",
    "superplayxyz.club",
    "supervideo.tv",
    "swisstransfer.com",
    "suzihaza.com",
    "teachertube.com",
    "teamcoco.com",
    "ted.com",
    "tenvoi.com",
    "terabox.app",
    "terabox.com",
    "terabox.link",
    "teraboxapp.com",
    "teraboxlink.com",
    "teraboxshare.com",
    "terafileshare.com",
    "terasharelink.com",
    "terazilla.com",
    "tezfiles.com",
    "thescene.com",
    "thesixtyone.com",
    "there.to",
    "tfo.org",
    "tlc.com",
    "tmpsend.com",
    "tnaflix.com",
    "transfert.free.fr",
    "trubobit.com",
    "turb.cc",
    "turbabit.com",
    "turbobit.cc",
    "turbobit.live",
    "turbobit.net",
    "turbobit.online",
    "turbobit.pw",
    "turbobit.ru",
    "turbobitlt.co",
    "turboget.net",
    "turbo.fr",
    "turbo.to",
    "turb.pw",
    "turb.to",
    "tu.tv",
    "uloz.to",
    "ulozto.cz",
    "ulozto.net",
    "ulozto.sk",
    "up-4ever.com",
    "up-4ever.net",
    "upload-4ever.com",
    "uptobox.com",
    "uptobox.eu",
    "uptobox.fr",
    "uptobox.link",
    "uptostream.com",
    "uptostream.eu",
    "uptostream.fr",
    "uptostream.link",
    "upvid.biz",
    "upvid.cloud",
    "upvid.co",
    "upvid.host",
    "upvid.live",
    "upvid.pro",
    "uqload.co",
    "uqload.com",
    "uqload.io",
    "userload.co",
    "usersdrive.com",
    "vanfem.com",
    "vbox7.com",
    "vcdn.io",
    "vcdnplay.com",
    "veehd.com",
    "veoh.com",
    "vid.me",
    "vidohd.com",
    "vidoza.net",
    "vidsource.me",
    "vimeopro.com",
    "viplayer.cc",
    "voe-un-block.com",
    "voe-unblock.com",
    "voe.sx",
    "voeun-block.net",
    "voeunbl0ck.com",
    "voeunblck.com",
    "voeunblk.com",
    "voeunblock1.com",
    "voeunblock2.com",
    "voeunblock3.com",
    "votrefile.xyz",
    "votrefiles.club",
    "wat.tv",
    "wdupload.com",
    "wimp.com",
    "world-files.com",
    "worldbytez.com",
    "wupfile.com",
    "xstreamcdn.com",
    "yahoo.com",
    "yodbox.com",
    "youdbox.com",
    "youtube.com",
    "youtu.be",
    "zachowajto.pl",
    "zidiplay.com",
]


def direct_link_generator(link, user_id=None):
    """
    Direct links generator with optional user context for authenticated access

    Args:
        link: URL to generate direct link for
        user_id: Optional user ID for user-specific authentication (e.g., API tokens)

    Returns:
        Direct download link or details dictionary
    """
    domain = urlparse(link).hostname
    if not domain:
        raise DirectDownloadLinkException(
            "ERROR: Invalid URL - Unable to parse domain from the provided link"
        )
    if "yadi.sk" in link or "disk.yandex." in link:
        return yandex_disk(link)
    if Config.DEBRID_LINK_API and any(
        x in domain for x in debrid_link_supported_sites
    ):
        return debrid_link(link)
    # Mega-Debrid support for premium downloads (including torrents)
    if Config.MEGA_DEBRID_API_TOKEN or (
        Config.MEGA_DEBRID_LOGIN and Config.MEGA_DEBRID_PASSWORD
    ):
        # Check if it's a torrent/magnet link
        if link.startswith("magnet:") or link.endswith(".torrent"):
            return mega_debrid(link)
        # Check if domain is supported (will fetch supported sites dynamically)
        elif domain and _is_mega_debrid_supported(domain):
            return mega_debrid(link)
    # AllDebrid support for premium downloads (including torrents and magnets)
    if Config.ALLDEBRID_API_KEY and (
        link.startswith("magnet:")
        or link.endswith(".torrent")
        or (domain and _is_alldebrid_supported(domain))
    ):
        return alldebrid(link)
    # Real-Debrid support for premium downloads (including torrents and magnets)
    if (Config.REAL_DEBRID_API_KEY or Config.REAL_DEBRID_ACCESS_TOKEN) and (
        link.startswith("magnet:")
        or link.endswith(".torrent")
        or (domain and _is_real_debrid_supported(domain))
    ):
        return real_debrid(link)
    # TorBox support for premium downloads
    if Config.TORBOX_API_KEY and (
        link.startswith("magnet:")
        or link.endswith(".torrent")
        or link.endswith(".nzb")
        or any(
            x in domain for x in debrid_link_supported_sites
        )  # TorBox supports same sites as debrid-link
    ):
        return torbox(link)
    if "buzzheavier.com" in domain:
        return buzzheavier(link)
    if "devuploads" in domain:
        return devuploads(link)
    if "lulacloud.com" in domain:
        return lulacloud(link)
    if "uploadhaven" in domain:
        return uploadhaven(link)
    if "fuckingfast.co" in domain:
        return fuckingfast_dl(link)
    if "mediafile.cc" in domain:
        return mediafile(link)
    if "mediafire.com" in domain:
        return mediafire(link, user_id=user_id)
    if "osdn.net" in domain:
        return osdn(link)
    if "github.com" in domain:
        return github(link)
    if "hxfile.co" in domain:
        return hxfile(link)
    if "1drv.ms" in domain:
        return onedrive(link)
    if any(x in domain for x in ["pixeldrain.com", "pixeldra.in"]):
        return pixeldrain(link)
    if "racaty" in domain:
        return racaty(link)
    if "1fichier.com" in domain:
        return fichier(link)
    if "solidfiles.com" in domain:
        return solidfiles(link)
    if "krakenfiles.com" in domain:
        return krakenfiles(link)
    if "upload.ee" in domain:
        return uploadee(link)
    if "gofile.io" in domain:
        return gofile(link, user_id)
    if "send.cm" in domain:
        return send_cm(link)
    if "tmpsend.com" in domain:
        return tmpsend(link)
    if "easyupload.io" in domain:
        return easyupload(link)
    if "streamvid.net" in domain:
        return streamvid(link)
    if "shrdsk.me" in domain:
        return shrdsk(link)
    if "u.pcloud.link" in domain:
        return pcloud(link)
    if "qiwi.gg" in domain:
        return qiwi(link)
    if "mp4upload.com" in domain:
        return mp4upload(link)
    if "berkasdrive.com" in domain:
        return berkasdrive(link)
    if "swisstransfer.com" in domain:
        return swisstransfer(link)
    if "instagram.com" in domain:
        return instagram(link)
    if any(x in domain for x in ["akmfiles.com", "akmfls.xyz"]):
        return akmfiles(link)
    if any(
        x in domain
        for x in [
            "dood.watch",
            "doodstream.com",
            "dood.to",
            "dood.so",
            "dood.cx",
            "dood.la",
            "dood.ws",
            "dood.sh",
            "doodstream.co",
            "dood.pm",
            "dood.wf",
            "dood.re",
            "dood.video",
            "dooood.com",
            "dood.yt",
            "doods.yt",
            "dood.stream",
            "doods.pro",
            "ds2play.com",
            "d0o0d.com",
            "ds2video.com",
            "do0od.com",
            "d000d.com",
            "vide0.net",
        ]
    ):
        return doods(link)
    if any(
        x in domain
        for x in [
            "streamtape.com",
            "streamtape.co",
            "streamtape.cc",
            "streamtape.to",
            "streamtape.net",
            "streamta.pe",
            "streamtape.xyz",
        ]
    ):
        return streamtape(link, user_id)
    if any(x in domain for x in ["wetransfer.com", "we.tl"]):
        return wetransfer(link)
    if any(
        x in domain
        for x in [
            "terabox.com",
            "nephobox.com",
            "4funbox.com",
            "mirrobox.com",
            "momerybox.com",
            "teraboxapp.com",
            "1024tera.com",
            "terabox.app",
            "gibibox.com",
            "goaibox.com",
            "terasharelink.com",
            "teraboxlink.com",
            "freeterabox.com",
            "1024terabox.com",
            "teraboxshare.com",
            "terafileshare.com",
            "terabox.club",
        ]
    ):
        return terabox(link)
    if any(
        x in domain
        for x in [
            "filelions.co",
            "filelions.site",
            "filelions.live",
            "filelions.to",
            "mycloudz.cc",
            "cabecabean.lol",
            "filelions.online",
            "embedwish.com",
            "kitabmarkaz.xyz",
            "wishfast.top",
            "streamwish.to",
            "kissmovies.net",
        ]
    ):
        return filelions_and_streamwish(link)
    if any(x in domain for x in ["streamhub.ink", "streamhub.to"]):
        return streamhub(link)
    if any(
        x in domain
        for x in [
            "linkbox.to",
            "lbx.to",
            "teltobx.net",
            "telbx.net",
            "linkbox.cloud",
        ]
    ):
        return linkBox(link)
    elif is_share_link(link):
        if "filepress" in domain:
            return filepress(link)
        return sharer_scraper(link)
    if any(
        x in domain
        for x in [
            "anonfiles.com",
            "zippyshare.com",
            "letsupload.io",
            "hotfile.io",
            "bayfiles.com",
            "megaupload.nz",
            "letsupload.cc",
            "filechan.org",
            "myfile.is",
            "vshare.is",
            "rapidshare.nu",
            "lolabits.se",
            "openload.cc",
            "share-online.is",
            "upvid.cc",
            "uptobox.com",
            "uptobox.fr",
        ]
    ):
        raise DirectDownloadLinkException(f"ERROR: R.I.P {domain}")
    raise DirectDownloadLinkException(
        f"No direct link function found for {domain}. This site is not supported for direct link generation. Try using a different download method or check if the link is correct."
    )


def get_captcha_token(session, params):
    recaptcha_api = "https://www.google.com/recaptcha/api2"
    res = session.get(f"{recaptcha_api}/anchor", params=params)
    anchor_html = HTML(res.text)
    if not (
        anchor_token := anchor_html.xpath('//input[@id="recaptcha-token"]/@value')
    ):
        return None
    params["c"] = anchor_token[0]
    params["reason"] = "q"
    res = session.post(f"{recaptcha_api}/reload", params=params)
    if token := findall(r'"rresp","(.*?)"', res.text):
        return token[0]


def debrid_link(url):
    """
    Enhanced Debrid-Link downloader with OAuth2 support and fallback mechanisms.
    Supports both API key and OAuth2 token authentication methods.
    """
    try:
        # Primary method: Try OAuth2 Bearer token authentication (API v2 recommended)
        return _debrid_link_oauth2(url)
    except DirectDownloadLinkException as oauth_error:
        # Fallback method: Try legacy API key authentication
        try:
            return _debrid_link_api_key(url)
        except DirectDownloadLinkException as api_error:
            # If both methods fail, raise the most informative error
            if "badToken" in str(oauth_error) and Config.DEBRID_LINK_API:
                # OAuth token expired, suggest refresh
                raise DirectDownloadLinkException(
                    f"ERROR: Debrid-Link OAuth token expired. Please refresh your access token. "
                    f"OAuth error: {oauth_error}, API fallback error: {api_error}"
                )
            elif Config.DEBRID_LINK_API:
                # API key method failed
                raise DirectDownloadLinkException(
                    f"ERROR: Debrid-Link API authentication failed. "
                    f"OAuth error: {oauth_error}, API error: {api_error}"
                )
            else:
                # No credentials configured
                raise DirectDownloadLinkException(
                    "ERROR: No Debrid-Link credentials configured. "
                    "Please set DEBRID_LINK_API (API key) or configure OAuth2 tokens."
                )


def _debrid_link_oauth2(url):
    """
    Primary method: Use OAuth2 Bearer token authentication (API v2 recommended).
    Automatically handles token refresh if needed.
    Follows official Debrid-Link API v2 specification.
    """
    # Get valid access token (with automatic refresh if needed)
    try:
        access_token = _get_valid_debrid_token()
    except DirectDownloadLinkException as e:
        raise DirectDownloadLinkException(f"OAuth2 token error: {str(e)}")

    session = create_scraper()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": user_agent,
    }

    try:
        # API v2 specification: POST /downloader/add with JSON body
        # Request body should be sent in JSON format as per API guide
        resp = session.post(
            "https://debrid-link.com/api/v2/downloader/add",
            headers=headers,
            json={"url": url},  # JSON body as per API v2 specification
            timeout=30,
        )

        # Handle HTTP status codes as per API guide
        # Success: 200 range, Error: 400/500 range
        if resp.status_code >= 400:
            try:
                error_data = resp.json()
                error_code = error_data.get("error", f"HTTP_{resp.status_code}")
            except:
                error_code = f"HTTP_{resp.status_code}"
            raise DirectDownloadLinkException(f"OAuth2 API error: {error_code}")

        result = resp.json()

    except DirectDownloadLinkException:
        raise  # Re-raise our custom exceptions
    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException("ERROR: Debrid-Link API timeout")
        raise DirectDownloadLinkException(f"ERROR: OAuth2 request failed - {str(e)}")

    # Process API response according to v2 specification
    return _process_debrid_response(result, url)


def _debrid_link_api_key(url):
    """
    Fallback method: Use legacy API key authentication.
    Uses access_token as query parameter (legacy method that was working).
    """
    if not Config.DEBRID_LINK_API:
        raise DirectDownloadLinkException("No API key available")

    session = create_scraper()

    try:
        # Legacy method: access_token as query parameter (revert to original working method)
        resp = session.post(
            f"https://debrid-link.com/api/v2/downloader/add?access_token={Config.DEBRID_LINK_API}",
            data={
                "url": url
            },  # Form data for legacy compatibility (original working method)
            headers={"User-Agent": user_agent},
            timeout=30,
        )

        # Handle HTTP errors
        if resp.status_code >= 400:
            try:
                error_data = resp.json()
                error_code = error_data.get("error", f"HTTP_{resp.status_code}")
            except:
                error_code = f"HTTP_{resp.status_code}"
            raise DirectDownloadLinkException(f"API key error: {error_code}")

        result = resp.json()

    except DirectDownloadLinkException:
        raise  # Re-raise our custom exceptions
    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException("ERROR: Debrid-Link API timeout")
        raise DirectDownloadLinkException(
            f"ERROR: API key request failed - {str(e)}"
        )

    # Process API response
    return _process_debrid_response(result, url)


def _process_debrid_response(resp, original_url):
    """
    Process Debrid-Link API response according to API v2 specification.
    Handles both single file and multi-file responses.
    """
    # Check API success status
    if not resp.get("success", False):
        error_code = resp.get("error", "unknown_error")

        # Handle specific error codes according to API documentation
        error_messages = {
            "badToken": "Invalid or expired token. Please refresh your access token.",
            "notDebrid": "Unable to generate link, the host may be down.",
            "hostNotValid": "The file hoster is not supported.",
            "fileNotFound": "File not found on the host.",
            "fileNotAvailable": "File temporarily unavailable on host.",
            "badFileUrl": "Invalid link format.",
            "badFilePassword": "Invalid or missing password for protected link.",
            "notFreeHost": "This host is not available for free members.",
            "maintenanceHost": "The file hoster is under maintenance.",
            "noServerHost": "No server available for this host.",
            "maxLink": "Daily link limit reached.",
            "maxLinkHost": "Daily link limit for this host reached.",
            "maxData": "Daily data limit reached.",
            "maxDataHost": "Daily data limit for this host reached.",
            "floodDetected": "API rate limit reached. Please wait 1 hour.",
            "serverNotAllowed": "Server/VPN not allowed. Contact support.",
            "freeServerOverload": "No server available for free users.",
        }

        error_msg = error_messages.get(error_code, f"Unknown error: {error_code}")
        raise DirectDownloadLinkException(f"ERROR: {error_msg}")

    # Process successful response
    value = resp.get("value")
    if not value:
        raise DirectDownloadLinkException(
            "ERROR: Empty response from Debrid-Link API"
        )

    # Handle single file response (dict)
    if isinstance(value, dict):
        download_url = value.get("downloadUrl")
        if not download_url:
            raise DirectDownloadLinkException("ERROR: No download URL in response")
        return download_url

    # Handle multi-file response (list)
    elif isinstance(value, list):
        if not value:
            raise DirectDownloadLinkException("ERROR: Empty file list in response")

        details = {
            "contents": [],
            "title": unquote(original_url.rstrip("/").split("/")[-1]),
            "total_size": 0,
        }

        for dl in value:
            # Skip expired links
            if dl.get("expired", False):
                continue

            # Validate required fields
            if not dl.get("name") or not dl.get("downloadUrl"):
                continue

            item = {
                "path": details["title"],
                "filename": dl["name"],
                "url": dl["downloadUrl"],
            }

            # Add file size if available
            if "size" in dl and isinstance(dl["size"], (int, float)):
                details["total_size"] += dl["size"]

            details["contents"].append(item)

        # Check if we have any valid files
        if not details["contents"]:
            raise DirectDownloadLinkException("ERROR: No valid download links found")

        return details

    else:
        raise DirectDownloadLinkException(
            f"ERROR: Unexpected response format: {type(value)}"
        )


def _refresh_debrid_token():
    """
    Refresh Debrid-Link OAuth2 access token using refresh token.
    Updates Config with new tokens automatically.
    """
    if not Config.DEBRID_LINK_REFRESH_TOKEN or not Config.DEBRID_LINK_CLIENT_ID:
        raise DirectDownloadLinkException("No refresh token or client ID available")

    session = create_scraper()

    try:
        # Prepare refresh token request
        data = {
            "client_id": Config.DEBRID_LINK_CLIENT_ID,
            "refresh_token": Config.DEBRID_LINK_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        }

        # Add client secret if available (for server-side apps)
        if Config.DEBRID_LINK_CLIENT_SECRET:
            data["client_secret"] = Config.DEBRID_LINK_CLIENT_SECRET

        # Request new access token
        resp = session.post(
            "https://debrid-link.com/api/oauth/token",
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": user_agent,
            },
            timeout=30,
        )

        if resp.status_code >= 400:
            error_data = resp.json() if resp.content else {"error": "unknown_error"}
            error_msg = error_data.get("error", f"HTTP {resp.status_code}")
            raise DirectDownloadLinkException(f"Token refresh failed: {error_msg}")

        result = resp.json()

        # Update Config with new tokens
        new_access_token = result.get("access_token")
        expires_in = result.get("expires_in", 86400)  # Default 24 hours

        if new_access_token:
            Config.DEBRID_LINK_ACCESS_TOKEN = new_access_token
            Config.DEBRID_LINK_API = new_access_token  # Update legacy field too

            # Calculate expiration timestamp
            from time import time

            Config.DEBRID_LINK_TOKEN_EXPIRES = (
                int(time()) + expires_in - 300
            )  # 5 min buffer

            # Update refresh token if provided
            new_refresh_token = result.get("refresh_token")
            if new_refresh_token:
                Config.DEBRID_LINK_REFRESH_TOKEN = new_refresh_token

            return new_access_token
        else:
            raise DirectDownloadLinkException("No access token in refresh response")

    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException("Token refresh timeout")
        raise DirectDownloadLinkException(f"Token refresh error: {str(e)}")


def _is_debrid_token_expired():
    """
    Check if Debrid-Link OAuth2 token is expired or about to expire.
    Returns True if token needs refresh.
    """
    if not Config.DEBRID_LINK_TOKEN_EXPIRES:
        return False  # No expiration set, assume valid

    from time import time

    current_time = int(time())

    # Consider token expired if it expires within 5 minutes
    return current_time >= (Config.DEBRID_LINK_TOKEN_EXPIRES - 300)


def _get_valid_debrid_token():
    """
    Get a valid Debrid-Link access token, refreshing if necessary.
    Returns the access token or raises exception if unavailable.
    """
    # Check if we have an access token
    access_token = (
        getattr(Config, "DEBRID_LINK_ACCESS_TOKEN", "") or Config.DEBRID_LINK_API
    )

    if not access_token:
        raise DirectDownloadLinkException("No Debrid-Link access token configured")

    # Check if token is expired and refresh if needed
    if _is_debrid_token_expired() and Config.DEBRID_LINK_REFRESH_TOKEN:
        try:
            access_token = _refresh_debrid_token()
        except DirectDownloadLinkException:
            # If refresh fails, try using existing token anyway
            pass

    return access_token


def get_debrid_oauth_device_code(client_id, scope="get.post.downloader get.account"):
    """
    Helper function to get device code for OAuth2 device flow.
    Used for setting up Debrid-Link authentication on limited input devices.

    Args:
        client_id: Your Debrid-Link app client ID
        scope: OAuth2 scope (default includes downloader and account access)

    Returns:
        dict: Contains device_code, user_code, verification_url, expires_in, interval
    """
    session = create_scraper()

    try:
        data = {"client_id": client_id, "scope": scope}

        resp = session.post(
            "https://debrid-link.com/api/oauth/device/code",
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": user_agent,
            },
            timeout=30,
        )

        if resp.status_code >= 400:
            error_data = resp.json() if resp.content else {"error": "unknown_error"}
            error_msg = error_data.get("error", f"HTTP {resp.status_code}")
            raise DirectDownloadLinkException(
                f"Device code request failed: {error_msg}"
            )

        return resp.json()

    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException("Device code request timeout")
        raise DirectDownloadLinkException(f"Device code request error: {str(e)}")


def poll_debrid_oauth_token(client_id, device_code, interval=3):
    """
    Helper function to poll for OAuth2 tokens using device code.
    Call this repeatedly until you get tokens or an error.

    Args:
        client_id: Your Debrid-Link app client ID
        device_code: Device code from get_debrid_oauth_device_code()
        interval: Polling interval in seconds (from device code response)

    Returns:
        dict: Contains access_token, refresh_token, expires_in, type

    Raises:
        DirectDownloadLinkException: If authorization is still pending or failed
    """
    session = create_scraper()

    try:
        data = {
            "client_id": client_id,
            "code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        }

        resp = session.post(
            "https://debrid-link.com/api/oauth/token",
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": user_agent,
            },
            timeout=30,
        )

        if resp.status_code >= 400:
            error_data = resp.json() if resp.content else {"error": "unknown_error"}
            error_code = error_data.get("error", f"HTTP {resp.status_code}")

            if error_code == "authorization_pending":
                raise DirectDownloadLinkException("authorization_pending")
            else:
                raise DirectDownloadLinkException(
                    f"Token polling failed: {error_code}"
                )

        return resp.json()

    except Exception as e:
        if "authorization_pending" in str(e):
            raise e  # Re-raise authorization pending
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException("Token polling timeout")
        raise DirectDownloadLinkException(f"Token polling error: {str(e)}")


def setup_debrid_oauth_device_flow(client_id):
    """
    Complete OAuth2 device flow setup for Debrid-Link.
    This is a helper function for initial authentication setup.

    Args:
        client_id: Your Debrid-Link app client ID

    Returns:
        dict: Contains access_token, refresh_token, expires_in for Config setup
    """
    try:
        # Step 1: Get device code
        LOGGER.info("Getting Debrid-Link device code...")
        device_data = get_debrid_oauth_device_code(client_id)

        device_code = device_data["device_code"]
        user_code = device_data["user_code"]
        verification_url = device_data["verification_url"]
        expires_in = device_data["expires_in"]
        interval = device_data["interval"]

        LOGGER.info(f"Please visit: {verification_url}")
        LOGGER.info(f"Enter this code: {user_code}")
        LOGGER.info(
            f"You have {expires_in // 60} minutes to complete authorization."
        )
        LOGGER.info(f"Polling for authorization every {interval} seconds...")

        # Step 2: Poll for tokens
        import time

        start_time = time.time()

        while time.time() - start_time < expires_in:
            try:
                token_data = poll_debrid_oauth_token(
                    client_id, device_code, interval
                )
                LOGGER.info("Debrid-Link authorization successful!")
                return token_data

            except DirectDownloadLinkException as e:
                if "authorization_pending" in str(e):
                    time.sleep(interval)
                    continue
                else:
                    raise e

        raise DirectDownloadLinkException(
            "Authorization timeout - device code expired"
        )

    except Exception as e:
        raise DirectDownloadLinkException(f"OAuth setup failed: {str(e)}")


def mega_debrid(url):
    """
    Mega-Debrid API integration for premium downloads.
    Supports both direct links and torrents/magnets.
    Based on official API documentation from mega-debrid.eu

    Args:
        url: URL to download from supported hosts or torrent/magnet link

    Returns:
        Direct download link or details dictionary for torrents

    Raises:
        DirectDownloadLinkException: If API request fails or no credentials
    """
    if not (
        Config.MEGA_DEBRID_API_TOKEN
        or (Config.MEGA_DEBRID_LOGIN and Config.MEGA_DEBRID_PASSWORD)
    ):
        raise DirectDownloadLinkException(
            "ERROR: Mega-Debrid credentials not configured. Please set MEGA_DEBRID_API_TOKEN or MEGA_DEBRID_LOGIN/MEGA_DEBRID_PASSWORD in your config."
        )

    session = create_scraper()

    try:
        # Get or refresh API token
        token = _get_mega_debrid_token(session)

        # Check if it's a torrent/magnet link
        if url.startswith("magnet:") or url.endswith(".torrent"):
            return _mega_debrid_upload_torrent(session, token, url)
        else:
            # Regular debrid link
            return _mega_debrid_get_link(session, token, url)

    except DirectDownloadLinkException:
        raise  # Re-raise our custom exceptions
    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException(
                "ERROR: Mega-Debrid API timeout - request timed out"
            )
        raise DirectDownloadLinkException(
            f"ERROR: Mega-Debrid request failed - {str(e)}"
        )


def _get_mega_debrid_token(session):
    """
    Get or refresh Mega-Debrid API token.
    Uses existing token if available, otherwise authenticates with login/password.
    Based on API docs: https://www.mega-debrid.eu/api.php?action=connectUser&login=[user_login]&password=[user_password]

    Args:
        session: HTTP session

    Returns:
        str: Valid API token

    Raises:
        DirectDownloadLinkException: If authentication fails
    """
    # If we have a token, try to use it first
    if Config.MEGA_DEBRID_API_TOKEN:
        return Config.MEGA_DEBRID_API_TOKEN

    # Otherwise, authenticate with login/password
    if not (Config.MEGA_DEBRID_LOGIN and Config.MEGA_DEBRID_PASSWORD):
        raise DirectDownloadLinkException(
            "ERROR: No Mega-Debrid token or login credentials available"
        )

    try:
        # Connect user to get token - using exact API format from docs
        auth_url = "https://www.mega-debrid.eu/api.php"
        auth_params = {
            "action": "connectUser",
            "login": Config.MEGA_DEBRID_LOGIN,
            "password": Config.MEGA_DEBRID_PASSWORD,
        }

        resp = session.get(auth_url, params=auth_params, timeout=30)

        if resp.status_code >= 400:
            raise DirectDownloadLinkException(
                f"ERROR: Mega-Debrid authentication failed - HTTP {resp.status_code}"
            )

        result = resp.json()

        # Check response_code as per API docs
        if result.get("response_code") != "ok":
            error_msg = result.get("response_text", "Unknown authentication error")
            # Check for non-premium account (vip_end indicates premium status)
            if "vip_end" in result and result.get("response_code") == "vip_end":
                raise DirectDownloadLinkException(
                    "ERROR: Mega-Debrid account is not premium. Only premium members can use the API."
                )
            raise DirectDownloadLinkException(
                f"ERROR: Mega-Debrid authentication failed - {error_msg}"
            )

        # Get token from response
        token = result.get("token")
        if not token:
            raise DirectDownloadLinkException(
                "ERROR: No token received from Mega-Debrid"
            )

        # Cache the token for future use (valid until next connection attempt per docs)
        Config.MEGA_DEBRID_API_TOKEN = token

        return token

    except DirectDownloadLinkException:
        raise
    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException(
                "ERROR: Mega-Debrid authentication timeout"
            )
        raise DirectDownloadLinkException(
            f"ERROR: Mega-Debrid authentication failed - {str(e)}"
        )


def _mega_debrid_get_link(session, token, url, password=""):
    """
    Get debrid link from Mega-Debrid API.
    Based on API docs: https://www.mega-debrid.eu/api.php?action=getLink&token=[token]
    POST fields: 'link' : link to debrid, 'password' : if the link has a password (md5 encoded)

    Args:
        session: HTTP session
        token: Valid API token
        url: URL to debrid
        password: Optional password for protected links (will be MD5 encoded)

    Returns:
        str: Direct download link

    Raises:
        DirectDownloadLinkException: If API request fails
    """
    try:
        # Get debrid link using POST request as per API docs
        api_url = "https://www.mega-debrid.eu/api.php"
        params = {"action": "getLink", "token": token}

        # POST data with the link and optional password (md5 encoded as per docs)
        data = {"link": url}
        if password:
            import hashlib

            data["password"] = hashlib.md5(password.encode()).hexdigest()

        resp = session.post(api_url, params=params, data=data, timeout=30)

        if resp.status_code >= 400:
            raise DirectDownloadLinkException(
                f"ERROR: Mega-Debrid API request failed - HTTP {resp.status_code}"
            )

        result = resp.json()

        # Check response_code as per API docs
        if result.get("response_code") != "ok":
            error_msg = result.get("response_text", "Unknown error")

            # Handle specific error cases
            if "Token error" in error_msg:
                # Token expired, try to refresh if we have login credentials
                if Config.MEGA_DEBRID_LOGIN and Config.MEGA_DEBRID_PASSWORD:
                    # Clear cached token and retry
                    Config.MEGA_DEBRID_API_TOKEN = ""
                    new_token = _get_mega_debrid_token(session)
                    return _mega_debrid_get_link(session, new_token, url, password)
                else:
                    raise DirectDownloadLinkException(
                        "ERROR: Mega-Debrid token expired. Please update MEGA_DEBRID_API_TOKEN or set login credentials."
                    )

            raise DirectDownloadLinkException(f"ERROR: Mega-Debrid - {error_msg}")

        # Get debrid link from response
        debrid_link = result.get("debridLink")
        if not debrid_link:
            raise DirectDownloadLinkException(
                "ERROR: No debrid link received from Mega-Debrid"
            )

        return debrid_link

    except DirectDownloadLinkException:
        raise
    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException("ERROR: Mega-Debrid API timeout")
        raise DirectDownloadLinkException(
            f"ERROR: Mega-Debrid API request failed - {str(e)}"
        )


def _mega_debrid_upload_torrent(session, token, url):
    """
    Upload torrent to Mega-Debrid API.
    Based on API docs: https://www.mega-debrid.eu/api.php?action=uploadTorrent&token=[token]
    POST 'file' : Upload file directly OR POST 'magnet' : Magnet URL of the torrent

    Args:
        session: HTTP session
        token: Valid API token
        url: Magnet link or torrent file URL

    Returns:
        dict: Torrent details or direct link

    Raises:
        DirectDownloadLinkException: If API request fails
    """
    try:
        api_url = "https://www.mega-debrid.eu/api.php"
        params = {"action": "uploadTorrent", "token": token}

        if url.startswith("magnet:"):
            # For magnet links
            data = {"magnet": url}
            files = None
        else:
            # For torrent file URLs, download and upload the file
            try:
                torrent_resp = session.get(url, timeout=30)
                if torrent_resp.status_code == 200:
                    files = {
                        "file": (
                            "torrent.torrent",
                            torrent_resp.content,
                            "application/x-bittorrent",
                        )
                    }
                    data = {}
                else:
                    raise DirectDownloadLinkException(
                        f"ERROR: Could not download torrent file from {url}"
                    )
            except Exception as e:
                raise DirectDownloadLinkException(
                    f"ERROR: Failed to fetch torrent file: {str(e)}"
                )

        resp = session.post(
            api_url, params=params, data=data, files=files, timeout=30
        )

        if resp.status_code >= 400:
            raise DirectDownloadLinkException(
                f"ERROR: Mega-Debrid torrent upload failed - HTTP {resp.status_code}"
            )

        result = resp.json()

        # Check response_code as per API docs
        if result.get("response_code") != "ok":
            error_msg = result.get("response_text", "Unknown error")
            raise DirectDownloadLinkException(
                f"ERROR: Mega-Debrid torrent upload - {error_msg}"
            )

        # Get torrent info from response: { name, size, hash }
        torrent_info = result.get("newTorrent", {})
        if not torrent_info:
            raise DirectDownloadLinkException(
                "ERROR: No torrent info received from Mega-Debrid"
            )

        # Return torrent details - user can check status later with getTorrent API
        return {
            "title": torrent_info.get("name", "Mega-Debrid Torrent"),
            "hash": torrent_info.get("hash", ""),
            "size": torrent_info.get("size", 0),
            "message": f"Torrent uploaded to Mega-Debrid successfully. Hash: {torrent_info.get('hash', 'N/A')}",
        }

    except DirectDownloadLinkException:
        raise
    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException(
                "ERROR: Mega-Debrid torrent upload timeout"
            )
        raise DirectDownloadLinkException(
            f"ERROR: Mega-Debrid torrent upload failed - {str(e)}"
        )


def _is_mega_debrid_supported(domain):
    """
    Check if a domain is supported by Mega-Debrid by fetching the hosters list.
    Based on API docs: https://www.mega-debrid.eu/api.php?action=getHostersList

    Args:
        domain: Domain to check

    Returns:
        bool: True if domain is supported
    """
    global mega_debrid_supported_sites

    # If we already have the list cached and it's not empty, use it
    if mega_debrid_supported_sites:
        return any(domain in site for site in mega_debrid_supported_sites)

    # Otherwise, fetch the hosters list from API
    try:
        session = create_scraper()
        api_url = "https://www.mega-debrid.eu/api.php"
        params = {"action": "getHostersList"}

        resp = session.get(api_url, params=params, timeout=15)

        if resp.status_code >= 400:
            # If API call fails, return False (don't try mega-debrid)
            return False

        result = resp.json()

        if result.get("response_code") != "ok":
            return False

        # Extract domains from hosters list
        hosters = result.get("hosters", [])
        supported_domains = []

        for hoster in hosters:
            # Each hoster has: {name, status, img, domains (array), regexps (array)}
            if hoster.get("status") == "up":  # Only include active hosters
                domains = hoster.get("domains", [])
                supported_domains.extend(domains)

        # Cache the supported sites
        mega_debrid_supported_sites = supported_domains

        # Check if our domain is supported
        return any(domain in site for site in supported_domains)

    except Exception:
        # If anything fails, return False (don't try mega-debrid)
        return False


# AllDebrid supported sites - will be fetched dynamically from API
alldebrid_supported_sites = []

# Real-Debrid supported sites - will be fetched dynamically from API
real_debrid_supported_sites = []


def alldebrid(url):
    """
    AllDebrid API integration for premium downloads.
    Supports direct links, torrents/magnets, redirectors, and streaming links.
    Based on official API documentation from alldebrid.com

    Args:
        url: URL to download from supported hosts or torrent/magnet link

    Returns:
        Direct download link or details dictionary for torrents

    Raises:
        DirectDownloadLinkException: If API request fails or no credentials
    """
    if not Config.ALLDEBRID_API_KEY:
        raise DirectDownloadLinkException(
            "ERROR: AllDebrid API key not configured. Please set ALLDEBRID_API_KEY in your config."
        )

    session = create_scraper()

    try:
        # Check if it's a torrent/magnet link
        if url.startswith("magnet:") or url.endswith(".torrent"):
            return _alldebrid_upload_magnet(session, url)

        # Check if it's a redirector link (common redirector domains)
        domain = urlparse(url).hostname
        redirector_domains = [
            "adf.ly",
            "bit.ly",
            "tinyurl.com",
            "short.link",
            "dl-protect",
            "linkvertise.com",
            "ouo.io",
            "sh.st",
            "adfly.com",
        ]

        if domain and any(
            redirector_domain in domain for redirector_domain in redirector_domains
        ):
            try:
                # Try to extract links from redirector first
                extracted_links = _alldebrid_handle_redirector(session, url)
                if extracted_links:
                    # Use the first extracted link for unlocking
                    return _alldebrid_unlock_link(session, extracted_links[0])
            except DirectDownloadLinkException:
                # If redirector fails, try direct unlock
                pass

        # Regular debrid link unlock
        return _alldebrid_unlock_link(session, url)

    except DirectDownloadLinkException:
        raise  # Re-raise our custom exceptions
    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException(
                "ERROR: AllDebrid API timeout - request timed out"
            )
        raise DirectDownloadLinkException(
            f"ERROR: AllDebrid request failed - {str(e)}"
        )


def _alldebrid_unlock_link(session, url, password=""):
    """
    Unlock a link using AllDebrid API.
    Based on API docs: POST /v4/link/unlock

    Args:
        session: HTTP session
        url: URL to unlock
        password: Optional password for protected links

    Returns:
        str: Direct download link

    Raises:
        DirectDownloadLinkException: If API request fails
    """
    try:
        # Prepare headers with Bearer token authentication
        headers = {
            "Authorization": f"Bearer {Config.ALLDEBRID_API_KEY}",
            "User-Agent": user_agent,
        }

        # Prepare POST data
        data = {"link": url}
        if password:
            data["password"] = password

        # Unlock link using POST request as per API docs
        resp = session.post(
            "https://api.alldebrid.com/v4/link/unlock",
            headers=headers,
            data=data,
            timeout=30,
        )

        if resp.status_code >= 400:
            raise DirectDownloadLinkException(
                f"ERROR: AllDebrid API request failed - HTTP {resp.status_code}"
            )

        result = resp.json()

        # Check API success status
        if result.get("status") != "success":
            error_info = result.get("error", {})
            error_code = error_info.get("code", "unknown_error")
            error_message = error_info.get("message", "Unknown error")

            # Handle specific error codes according to API documentation
            error_messages = {
                "AUTH_MISSING_APIKEY": "API key was not sent",
                "AUTH_BAD_APIKEY": "Invalid API key",
                "AUTH_BLOCKED": "API key is geo-blocked or IP-blocked",
                "AUTH_USER_BANNED": "Account is banned",
                "LINK_HOST_NOT_SUPPORTED": "This host or link is not supported",
                "LINK_DOWN": "Link is not available on the file hoster website",
                "LINK_HOST_UNAVAILABLE": "Host under maintenance or not available",
                "LINK_TOO_MANY_DOWNLOADS": "Too many concurrent downloads",
                "LINK_HOST_FULL": "All servers are full for this host, please retry later",
                "LINK_HOST_LIMIT_REACHED": "Download limit reached for this host",
                "LINK_PASS_PROTECTED": "Link is password protected",
                "LINK_ERROR": "Generic unlocking error",
                "LINK_NOT_SUPPORTED": "The link is not supported for this host",
                "LINK_TEMPORARY_UNAVAILABLE": "Link is temporarily unavailable on hoster website",
                "MUST_BE_PREMIUM": "You must be premium to process this link",
                "FREE_TRIAL_LIMIT_REACHED": "Free trial limit reached (7 days // 25GB downloaded or host uneligible for free trial)",
                "NO_SERVER": "Server are not allowed to use this feature. Visit https://alldebrid.com/vpn if you're using a VPN",
            }

            detailed_error = error_messages.get(error_code, error_message)
            raise DirectDownloadLinkException(f"ERROR: AllDebrid - {detailed_error}")

        # Get data from successful response
        data = result.get("data", {})
        if not data:
            raise DirectDownloadLinkException(
                "ERROR: Empty response from AllDebrid API"
            )

        # Check if it's a delayed link
        if "delayed" in data:
            delayed_id = data["delayed"]
            return _alldebrid_handle_delayed_link(session, delayed_id)

        # Check if it's a streaming link with multiple qualities
        streams = data.get("streams", [])
        if streams:
            # For streaming links, return the best quality or let user choose
            # For now, return the first stream (usually best quality)
            stream_id = streams[0].get("id")
            generation_id = data.get("id")

            if stream_id and generation_id:
                return _alldebrid_get_streaming_link(
                    session, generation_id, stream_id
                )

        # Get direct download link
        download_url = data.get("link")
        if not download_url:
            raise DirectDownloadLinkException(
                "ERROR: No download URL in AllDebrid response"
            )

        return download_url

    except DirectDownloadLinkException:
        raise
    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException("ERROR: AllDebrid API timeout")
        raise DirectDownloadLinkException(
            f"ERROR: AllDebrid API request failed - {str(e)}"
        )


def _alldebrid_upload_magnet(session, url):
    """
    Upload magnet/torrent to AllDebrid API.
    Based on API docs: POST /v4/magnet/upload and POST /v4/magnet/upload/file

    Args:
        session: HTTP session
        url: Magnet link or torrent file URL

    Returns:
        dict: Magnet details or direct link

    Raises:
        DirectDownloadLinkException: If API request fails
    """
    try:
        # Prepare headers with Bearer token authentication
        headers = {
            "Authorization": f"Bearer {Config.ALLDEBRID_API_KEY}",
            "User-Agent": user_agent,
        }

        if url.startswith("magnet:"):
            # For magnet links - API expects magnets[] as array parameter
            data = {"magnets[]": [url]}  # Fixed: Pass as array
            files = None
        else:
            # For torrent file URLs, download and upload the file
            try:
                torrent_resp = session.get(url, timeout=30)
                if torrent_resp.status_code == 200:
                    files = {
                        "files[0]": (
                            "torrent.torrent",
                            torrent_resp.content,
                            "application/x-bittorrent",
                        )
                    }
                    data = {}
                else:
                    raise DirectDownloadLinkException(
                        f"ERROR: Could not download torrent file from {url}"
                    )
            except Exception as e:
                raise DirectDownloadLinkException(
                    f"ERROR: Failed to fetch torrent file: {str(e)}"
                )

        # Upload magnet/torrent
        if url.startswith("magnet:"):
            resp = session.post(
                "https://api.alldebrid.com/v4/magnet/upload",
                headers=headers,
                data=data,
                timeout=30,
            )
        else:
            resp = session.post(
                "https://api.alldebrid.com/v4/magnet/upload/file",
                headers=headers,
                data=data,
                files=files,
                timeout=30,
            )

        if resp.status_code >= 400:
            raise DirectDownloadLinkException(
                f"ERROR: AllDebrid magnet upload failed - HTTP {resp.status_code}"
            )

        result = resp.json()

        # Check API success status
        if result.get("status") != "success":
            error_info = result.get("error", {})
            error_code = error_info.get("code", "unknown_error")
            error_message = error_info.get("message", "Unknown error")

            # Handle specific error codes
            error_messages = {
                "MAGNET_NO_URI": "No magnet provided",
                "MAGNET_INVALID_URI": "Magnet is not valid",
                "MAGNET_MUST_BE_PREMIUM": "You must be premium to use this feature",
                "MAGNET_NO_SERVER": "Server are not allowed to use this feature. Visit https://alldebrid.com/vpn if you're using a VPN",
                "MAGNET_TOO_MANY_ACTIVE": "Already have maximum allowed active magnets (30)",
                "MAGNET_INVALID_FILE": "File is not a valid torrent",
                "MAGNET_FILE_UPLOAD_FAILED": "File upload failed",
            }

            detailed_error = error_messages.get(error_code, error_message)
            raise DirectDownloadLinkException(
                f"ERROR: AllDebrid magnet upload - {detailed_error}"
            )

        # Get magnet info from response
        data = result.get("data", {})
        if url.startswith("magnet:"):
            magnets = data.get("magnets", [])
            if not magnets:
                raise DirectDownloadLinkException(
                    "ERROR: No magnet info received from AllDebrid"
                )
            magnet_info = magnets[0]
        else:
            files = data.get("files", [])
            if not files:
                raise DirectDownloadLinkException(
                    "ERROR: No file info received from AllDebrid"
                )
            magnet_info = files[0]

        # Check for errors in magnet info
        if "error" in magnet_info:
            error_info = magnet_info["error"]
            error_code = error_info.get("code", "unknown_error")
            error_message = error_info.get("message", "Unknown error")
            raise DirectDownloadLinkException(
                f"ERROR: AllDebrid magnet - {error_message}"
            )

        # Return magnet details - user can check status later with magnet/status API
        return {
            "title": magnet_info.get("name", "AllDebrid Magnet"),
            "hash": magnet_info.get("hash", ""),
            "size": magnet_info.get("size", 0),
            "id": magnet_info.get("id", ""),
            "ready": magnet_info.get("ready", False),
            "message": f"Magnet uploaded to AllDebrid successfully. ID: {magnet_info.get('id', 'N/A')}",
        }

    except DirectDownloadLinkException:
        raise
    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException(
                "ERROR: AllDebrid magnet upload timeout"
            )
        raise DirectDownloadLinkException(
            f"ERROR: AllDebrid magnet upload failed - {str(e)}"
        )


def _alldebrid_handle_delayed_link(session, delayed_id):
    """
    Handle delayed links from AllDebrid API.
    Based on API docs: POST /v4/link/delayed

    Args:
        session: HTTP session
        delayed_id: Delayed link ID

    Returns:
        str: Direct download link when ready

    Raises:
        DirectDownloadLinkException: If API request fails
    """
    try:
        headers = {
            "Authorization": f"Bearer {Config.ALLDEBRID_API_KEY}",
            "User-Agent": user_agent,
        }

        # Poll for delayed link status (max 5 minutes)
        max_attempts = 60  # 5 minutes with 5-second intervals
        attempt = 0

        while attempt < max_attempts:
            data = {"id": delayed_id}

            resp = session.post(
                "https://api.alldebrid.com/v4/link/delayed",
                headers=headers,
                data=data,
                timeout=30,
            )

            if resp.status_code >= 400:
                raise DirectDownloadLinkException(
                    f"ERROR: AllDebrid delayed link check failed - HTTP {resp.status_code}"
                )

            result = resp.json()

            if result.get("status") != "success":
                error_info = result.get("error", {})
                error_message = error_info.get("message", "Unknown error")
                raise DirectDownloadLinkException(
                    f"ERROR: AllDebrid delayed link - {error_message}"
                )

            data = result.get("data", {})
            status = data.get("status")
            time_left = data.get("time_left", 0)

            if status == 2:  # Download link is available
                download_url = data.get("link")
                if download_url:
                    return download_url
                else:
                    raise DirectDownloadLinkException(
                        "ERROR: No download URL in delayed response"
                    )
            elif status == 3:  # Error, could not generate download link
                raise DirectDownloadLinkException(
                    "ERROR: AllDebrid could not generate download link"
                )
            elif status == 1:  # Still processing
                LOGGER.info(
                    f"AllDebrid delayed link still processing. Time left: {time_left}s"
                )
                sleep(5)  # Wait 5 seconds before next check
                attempt += 1
            else:
                raise DirectDownloadLinkException(
                    f"ERROR: Unknown delayed link status: {status}"
                )

        raise DirectDownloadLinkException(
            "ERROR: AllDebrid delayed link timeout - took too long to process"
        )

    except DirectDownloadLinkException:
        raise
    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException(
                "ERROR: AllDebrid delayed link timeout"
            )
        raise DirectDownloadLinkException(
            f"ERROR: AllDebrid delayed link failed - {str(e)}"
        )


def _is_alldebrid_supported(domain):
    """
    Check if a domain is supported by AllDebrid by fetching the hosts list.
    Uses both public /v4/hosts and authenticated /v4.1/user/hosts for comprehensive coverage.
    Based on API docs: GET /v4/hosts and GET /v4.1/user/hosts

    Args:
        domain: Domain to check

    Returns:
        bool: True if domain is supported
    """
    global alldebrid_supported_sites

    # If we already have the list cached and it's not empty, use it
    if alldebrid_supported_sites:
        return any(domain in site for site in alldebrid_supported_sites)

    # Otherwise, fetch the hosts list from API
    try:
        session = create_scraper()
        supported_domains = []

        # First, try the public hosts endpoint (includes streams and redirectors)
        try:
            resp = session.get("https://api.alldebrid.com/v4/hosts", timeout=15)
            if resp.status_code == 200:
                result = resp.json()
                if result.get("status") == "success":
                    data = result.get("data", {})

                    # Extract domains from hosts
                    hosts = data.get("hosts", {})
                    for _, host_info in hosts.items():
                        if host_info.get("status", True):
                            domains = host_info.get("domains", [])
                            supported_domains.extend(domains)

                    # Also check streams and redirectors
                    streams = data.get("streams", {})
                    for _, stream_info in streams.items():
                        domains = stream_info.get("domains", [])
                        supported_domains.extend(domains)

                    redirectors = data.get("redirectors", {})
                    for _, redirector_info in redirectors.items():
                        domains = redirector_info.get("domains", [])
                        supported_domains.extend(domains)
        except Exception:
            pass  # Continue with user hosts if public endpoint fails

        # If we have API key, also check user-specific hosts (v4.1 for better performance)
        if Config.ALLDEBRID_API_KEY:
            try:
                headers = {
                    "Authorization": f"Bearer {Config.ALLDEBRID_API_KEY}",
                    "User-Agent": user_agent,
                }
                resp = session.get(
                    "https://api.alldebrid.com/v4.1/user/hosts",
                    headers=headers,
                    timeout=15,
                )
                if resp.status_code == 200:
                    result = resp.json()
                    if result.get("status") == "success":
                        data = result.get("data", {})
                        hosts = data.get("hosts", {})
                        for _, host_info in hosts.items():
                            if host_info.get("status", True):
                                domains = host_info.get("domains", [])
                                supported_domains.extend(domains)
            except Exception:
                pass  # User hosts is optional

        # Remove duplicates and cache
        alldebrid_supported_sites = list(set(supported_domains))

        # Check if our domain is supported
        return any(domain in site for site in alldebrid_supported_sites)

    except Exception:
        # If everything fails, return False (don't try alldebrid)
        return False


def _alldebrid_handle_redirector(session, url):
    """
    Handle redirector links using AllDebrid API.
    Based on API docs: POST /v4/link/redirector

    Args:
        session: HTTP session
        url: Redirector URL to extract links from

    Returns:
        list: List of extracted links

    Raises:
        DirectDownloadLinkException: If API request fails
    """
    try:
        headers = {
            "Authorization": f"Bearer {Config.ALLDEBRID_API_KEY}",
            "User-Agent": user_agent,
        }

        data = {"link": url}

        resp = session.post(
            "https://api.alldebrid.com/v4/link/redirector",
            headers=headers,
            data=data,
            timeout=30,
        )

        if resp.status_code >= 400:
            raise DirectDownloadLinkException(
                f"ERROR: AllDebrid redirector request failed - HTTP {resp.status_code}"
            )

        result = resp.json()

        if result.get("status") != "success":
            error_info = result.get("error", {})
            error_code = error_info.get("code", "unknown_error")
            error_message = error_info.get("message", "Unknown error")

            # Handle specific error codes
            error_messages = {
                "REDIRECTOR_NOT_SUPPORTED": "Redirector not supported",
                "REDIRECTOR_ERROR": "Could not extract links",
            }

            detailed_error = error_messages.get(error_code, error_message)
            raise DirectDownloadLinkException(
                f"ERROR: AllDebrid redirector - {detailed_error}"
            )

        # Get extracted links
        data = result.get("data", {})
        links = data.get("links", [])

        if not links:
            raise DirectDownloadLinkException(
                "ERROR: No links extracted from redirector"
            )

        return links

    except DirectDownloadLinkException:
        raise
    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException("ERROR: AllDebrid redirector timeout")
        raise DirectDownloadLinkException(
            f"ERROR: AllDebrid redirector failed - {str(e)}"
        )


def _alldebrid_get_link_info(session, url, password=""):
    """
    Get link information using AllDebrid API.
    Based on API docs: POST /v4/link/infos

    Args:
        session: HTTP session
        url: URL to get information about
        password: Optional password for protected links

    Returns:
        dict: Link information

    Raises:
        DirectDownloadLinkException: If API request fails
    """
    try:
        headers = {
            "Authorization": f"Bearer {Config.ALLDEBRID_API_KEY}",
            "User-Agent": user_agent,
        }

        data = {"link[]": [url]}  # API expects array format
        if password:
            data["password"] = password

        resp = session.post(
            "https://api.alldebrid.com/v4/link/infos",
            headers=headers,
            data=data,
            timeout=30,
        )

        if resp.status_code >= 400:
            raise DirectDownloadLinkException(
                f"ERROR: AllDebrid link info request failed - HTTP {resp.status_code}"
            )

        result = resp.json()

        if result.get("status") != "success":
            error_info = result.get("error", {})
            error_message = error_info.get("message", "Unknown error")
            raise DirectDownloadLinkException(
                f"ERROR: AllDebrid link info - {error_message}"
            )

        # Get link info
        data = result.get("data", {})
        infos = data.get("infos", [])

        if not infos:
            raise DirectDownloadLinkException("ERROR: No link information received")

        link_info = infos[0]

        # Check for errors in link info
        if "error" in link_info:
            error_info = link_info["error"]
            error_code = error_info.get("code", "unknown_error")
            error_message = error_info.get("message", "Unknown error")

            # Handle specific error codes
            error_messages = {
                "LINK_IS_MISSING": "No link was sent",
                "LINK_HOST_NOT_SUPPORTED": "This host or link is not supported",
                "LINK_DOWN": "This link is not available on the file hoster website",
                "LINK_PASS_PROTECTED": "Link is password protected",
                "LINK_TEMPORARY_UNAVAILABLE": "Link is temporarily unavailable on hoster website",
            }

            detailed_error = error_messages.get(error_code, error_message)
            raise DirectDownloadLinkException(
                f"ERROR: AllDebrid link info - {detailed_error}"
            )

        return link_info

    except DirectDownloadLinkException:
        raise
    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException("ERROR: AllDebrid link info timeout")
        raise DirectDownloadLinkException(
            f"ERROR: AllDebrid link info failed - {str(e)}"
        )


def _alldebrid_get_streaming_link(session, generation_id, stream_id):
    """
    Get streaming link using AllDebrid API.
    Based on API docs: POST /v4/link/streaming

    Args:
        session: HTTP session
        generation_id: Generation ID from unlock response
        stream_id: Stream ID for the desired quality

    Returns:
        str: Direct streaming link

    Raises:
        DirectDownloadLinkException: If API request fails
    """
    try:
        headers = {
            "Authorization": f"Bearer {Config.ALLDEBRID_API_KEY}",
            "User-Agent": user_agent,
        }

        data = {
            "id": generation_id,
            "stream": stream_id,
        }

        resp = session.post(
            "https://api.alldebrid.com/v4/link/streaming",
            headers=headers,
            data=data,
            timeout=30,
        )

        if resp.status_code >= 400:
            raise DirectDownloadLinkException(
                f"ERROR: AllDebrid streaming request failed - HTTP {resp.status_code}"
            )

        result = resp.json()

        if result.get("status") != "success":
            error_info = result.get("error", {})
            error_code = error_info.get("code", "unknown_error")
            error_message = error_info.get("message", "Unknown error")

            # Handle specific error codes
            error_messages = {
                "STREAM_INVALID_GEN_ID": "Invalid generation ID",
                "STREAM_INVALID_STREAM_ID": "Invalid stream ID",
            }

            detailed_error = error_messages.get(error_code, error_message)
            raise DirectDownloadLinkException(
                f"ERROR: AllDebrid streaming - {detailed_error}"
            )

        # Get streaming data
        data = result.get("data", {})

        # Check if it's a delayed link
        if "delayed" in data:
            delayed_id = data["delayed"]
            return _alldebrid_handle_delayed_link(session, delayed_id)

        # Get direct streaming link
        streaming_url = data.get("link")
        if not streaming_url:
            raise DirectDownloadLinkException(
                "ERROR: No streaming URL in AllDebrid response"
            )

        return streaming_url

    except DirectDownloadLinkException:
        raise
    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException("ERROR: AllDebrid streaming timeout")
        raise DirectDownloadLinkException(
            f"ERROR: AllDebrid streaming failed - {str(e)}"
        )


def _alldebrid_check_magnet_status(session, magnet_id):
    """
    Check magnet status using AllDebrid API v4.1.
    Based on API docs: POST /v4.1/magnet/status

    Args:
        session: HTTP session
        magnet_id: Magnet ID to check

    Returns:
        dict: Magnet status information

    Raises:
        DirectDownloadLinkException: If API request fails
    """
    try:
        headers = {
            "Authorization": f"Bearer {Config.ALLDEBRID_API_KEY}",
            "User-Agent": user_agent,
        }

        data = {"id": magnet_id}

        resp = session.post(
            "https://api.alldebrid.com/v4.1/magnet/status",
            headers=headers,
            data=data,
            timeout=30,
        )

        if resp.status_code >= 400:
            raise DirectDownloadLinkException(
                f"ERROR: AllDebrid magnet status request failed - HTTP {resp.status_code}"
            )

        result = resp.json()

        if result.get("status") != "success":
            error_info = result.get("error", {})
            error_code = error_info.get("code", "unknown_error")
            error_message = error_info.get("message", "Unknown error")

            # Handle specific error codes
            error_messages = {
                "MAGNET_INVALID_ID": "Magnet ID is invalid",
            }

            detailed_error = error_messages.get(error_code, error_message)
            raise DirectDownloadLinkException(
                f"ERROR: AllDebrid magnet status - {detailed_error}"
            )

        # Get magnet status data
        data = result.get("data", {})
        magnets = data.get("magnets", [])

        if not magnets:
            raise DirectDownloadLinkException(
                "ERROR: No magnet status information received"
            )

        return magnets[0]  # Return first magnet info

    except DirectDownloadLinkException:
        raise
    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException(
                "ERROR: AllDebrid magnet status timeout"
            )
        raise DirectDownloadLinkException(
            f"ERROR: AllDebrid magnet status failed - {str(e)}"
        )


def real_debrid(url):
    """
    Real-Debrid API integration for premium downloads.
    Supports direct links, torrents/magnets, and 100+ file hosts.
    Based on official API documentation from real-debrid.com

    Args:
        url: URL to download from supported hosts or torrent/magnet link

    Returns:
        Direct download link or details dictionary for torrents

    Raises:
        DirectDownloadLinkException: If API request fails or no credentials
    """
    if not (Config.REAL_DEBRID_API_KEY or Config.REAL_DEBRID_ACCESS_TOKEN):
        raise DirectDownloadLinkException(
            "ERROR: Real-Debrid credentials not configured. Please set REAL_DEBRID_API_KEY or REAL_DEBRID_ACCESS_TOKEN in your config."
        )

    session = create_scraper()

    try:
        # Check if it's a torrent/magnet link
        if url.startswith("magnet:") or url.endswith(".torrent"):
            return _real_debrid_add_torrent(session, url)
        else:
            # Check if it might be a folder link first
            try:
                folder_result = _real_debrid_unrestrict_folder(session, url)
                if folder_result:
                    return folder_result
            except DirectDownloadLinkException:
                # If folder unrestrict fails, try regular link unrestrict
                pass

            # Regular debrid link
            return _real_debrid_unrestrict_link(session, url)

    except DirectDownloadLinkException:
        raise  # Re-raise our custom exceptions
    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException(
                "ERROR: Real-Debrid API timeout - request timed out"
            )
        raise DirectDownloadLinkException(
            f"ERROR: Real-Debrid request failed - {str(e)}"
        )


def _real_debrid_unrestrict_link(session, url, password=""):
    """
    Unrestrict a link using Real-Debrid API.
    Based on API docs: POST /unrestrict/link
    Supports both Bearer token and auth_token query parameter authentication.

    Args:
        session: HTTP session
        url: URL to unrestrict
        password: Optional password for protected links

    Returns:
        str: Direct download link

    Raises:
        DirectDownloadLinkException: If API request fails
    """
    try:
        # Get valid access token
        access_token = _get_valid_real_debrid_token()

        # Prepare POST data
        data = {"link": url}
        if password:
            data["password"] = password

        # Try Bearer token authentication first (recommended)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": user_agent,
        }

        # Unrestrict link using POST request as per API docs
        resp = session.post(
            "https://api.real-debrid.com/rest/1.0/unrestrict/link",
            headers=headers,
            data=data,
            timeout=30,
        )

        # If Bearer token fails, try auth_token query parameter as fallback
        if resp.status_code == 401 or resp.status_code == 403:
            headers_fallback = {"User-Agent": user_agent}
            resp = session.post(
                f"https://api.real-debrid.com/rest/1.0/unrestrict/link?auth_token={access_token}",
                headers=headers_fallback,
                data=data,
                timeout=30,
            )

        if resp.status_code >= 400:
            try:
                error_data = resp.json()
                error_code = error_data.get("error_code", resp.status_code)
                error_msg = error_data.get("error", f"HTTP {resp.status_code}")
            except:
                error_code = resp.status_code
                error_msg = f"HTTP {resp.status_code}"

            # Handle specific error codes based on API documentation
            error_messages = {
                -1: "Internal error",
                1: "Missing parameter",
                2: "Bad parameter value",
                3: "Unknown method",
                4: "Method not allowed",
                5: "Slow down - rate limit exceeded",
                6: "Resource unreachable",
                7: "Resource not found",
                8: "Bad token - invalid or expired",
                9: "Permission denied",
                10: "Two-Factor authentication needed",
                11: "Two-Factor authentication pending",
                12: "Invalid login",
                13: "Invalid password",
                14: "Account locked",
                15: "Account not activated",
                16: "Unsupported hoster",
                17: "Hoster in maintenance",
                18: "Hoster limit reached",
                19: "Hoster temporarily unavailable",
                20: "Hoster not available for free users",
                21: "Too many active downloads",
                22: "IP Address not allowed",
                23: "Traffic exhausted",
                24: "File unavailable",
                25: "Service unavailable",
                26: "Upload too big",
                27: "Upload error",
                28: "File not allowed",
                29: "Torrent too big",
                30: "Torrent file invalid",
                31: "Action already done",
                32: "Image resolution error",
                33: "Torrent already active",
                34: "Too many requests",
                35: "Infringing file",
                36: "Fair Usage Limit",
                37: "Disabled endpoint",
            }

            specific_msg = error_messages.get(error_code, error_msg)
            raise DirectDownloadLinkException(f"ERROR: Real-Debrid - {specific_msg}")

        result = resp.json()

        # Get download link from response
        download_url = result.get("download")
        if not download_url:
            raise DirectDownloadLinkException(
                "ERROR: No download URL received from Real-Debrid"
            )

        return download_url

    except DirectDownloadLinkException:
        raise
    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException("ERROR: Real-Debrid API timeout")
        raise DirectDownloadLinkException(
            f"ERROR: Real-Debrid API request failed - {str(e)}"
        )


def _real_debrid_add_torrent(session, url):
    """
    Add torrent to Real-Debrid API.
    Based on API docs: PUT /torrents/addTorrent (for files) or POST /torrents/addMagnet (for magnets)

    Args:
        session: HTTP session
        url: Magnet link or torrent file URL

    Returns:
        dict: Torrent details

    Raises:
        DirectDownloadLinkException: If API request fails
    """
    try:
        # Get valid access token
        access_token = _get_valid_real_debrid_token()

        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": user_agent,
        }

        if url.startswith("magnet:"):
            # For magnet links - POST /torrents/addMagnet
            data = {"magnet": url}
            resp = session.post(
                "https://api.real-debrid.com/rest/1.0/torrents/addMagnet",
                headers=headers,
                data=data,
                timeout=30,
            )
        else:
            # For torrent file URLs - PUT /torrents/addTorrent
            try:
                torrent_resp = session.get(url, timeout=30)
                if torrent_resp.status_code == 200:
                    files = {
                        "torrent": (
                            "torrent.torrent",
                            torrent_resp.content,
                            "application/x-bittorrent",
                        )
                    }
                    resp = session.put(
                        "https://api.real-debrid.com/rest/1.0/torrents/addTorrent",
                        headers=headers,
                        files=files,
                        timeout=30,
                    )
                else:
                    raise DirectDownloadLinkException(
                        f"ERROR: Could not download torrent file from {url}"
                    )
            except Exception as e:
                raise DirectDownloadLinkException(
                    f"ERROR: Failed to fetch torrent file: {str(e)}"
                )

        if resp.status_code >= 400:
            try:
                error_data = resp.json()
                error_code = error_data.get("error_code", resp.status_code)
                error_msg = error_data.get("error", f"HTTP {resp.status_code}")
            except:
                error_code = resp.status_code
                error_msg = f"HTTP {resp.status_code}"

            # Handle specific error codes based on API documentation
            error_messages = {
                -1: "Internal error",
                1: "Missing parameter",
                2: "Bad parameter value",
                3: "Unknown method",
                4: "Method not allowed",
                5: "Slow down - rate limit exceeded",
                6: "Resource unreachable",
                7: "Resource not found",
                8: "Bad token - invalid or expired",
                9: "Permission denied",
                10: "Two-Factor authentication needed",
                11: "Two-Factor authentication pending",
                12: "Invalid login",
                13: "Invalid password",
                14: "Account locked",
                15: "Account not activated",
                16: "Unsupported hoster",
                17: "Hoster in maintenance",
                18: "Hoster limit reached",
                19: "Hoster temporarily unavailable",
                20: "Hoster not available for free users",
                21: "Too many active downloads",
                22: "IP Address not allowed",
                23: "Traffic exhausted",
                24: "File unavailable",
                25: "Service unavailable",
                26: "Upload too big",
                27: "Upload error",
                28: "File not allowed",
                29: "Torrent too big",
                30: "Torrent file invalid",
                31: "Action already done",
                32: "Image resolution error",
                33: "Torrent already active",
                34: "Too many requests",
                35: "Infringing file",
                36: "Fair Usage Limit",
                37: "Disabled endpoint",
            }

            specific_msg = error_messages.get(error_code, error_msg)
            raise DirectDownloadLinkException(
                f"ERROR: Real-Debrid torrent - {specific_msg}"
            )

        result = resp.json()

        # Get torrent info from response
        torrent_id = result.get("id")
        if not torrent_id:
            raise DirectDownloadLinkException(
                "ERROR: No torrent ID received from Real-Debrid"
            )

        # Return torrent details - user can check status later
        return {
            "title": result.get("filename", "Real-Debrid Torrent"),
            "id": torrent_id,
            "uri": result.get("uri", ""),
            "message": f"Torrent added to Real-Debrid successfully. ID: {torrent_id}",
        }

    except DirectDownloadLinkException:
        raise
    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException(
                "ERROR: Real-Debrid torrent upload timeout"
            )
        raise DirectDownloadLinkException(
            f"ERROR: Real-Debrid torrent upload failed - {str(e)}"
        )


def _get_valid_real_debrid_token():
    """
    Get a valid Real-Debrid access token, refreshing if necessary.
    Returns the access token or raises exception if unavailable.
    """
    # Check if we have an access token
    access_token = (
        getattr(Config, "REAL_DEBRID_ACCESS_TOKEN", "") or Config.REAL_DEBRID_API_KEY
    )

    if not access_token:
        raise DirectDownloadLinkException("No Real-Debrid access token configured")

    # Check if token is expired and refresh if needed
    if _is_real_debrid_token_expired() and Config.REAL_DEBRID_REFRESH_TOKEN:
        try:
            access_token = _refresh_real_debrid_token()
        except DirectDownloadLinkException:
            # If refresh fails, try using existing token anyway
            pass

    return access_token


def _is_real_debrid_token_expired():
    """
    Check if Real-Debrid OAuth2 token is expired or about to expire.
    Returns True if token needs refresh.
    """
    if not Config.REAL_DEBRID_TOKEN_EXPIRES:
        return False  # No expiration set, assume valid

    from time import time

    current_time = int(time())

    # Consider token expired if it expires within 5 minutes
    return current_time >= (Config.REAL_DEBRID_TOKEN_EXPIRES - 300)


def _refresh_real_debrid_token():
    """
    Refresh Real-Debrid OAuth2 access token using refresh token.
    Updates Config with new tokens automatically.
    Based on API docs: POST /oauth/v2/token with grant_type=refresh_token
    """
    if not Config.REAL_DEBRID_REFRESH_TOKEN or not Config.REAL_DEBRID_CLIENT_ID:
        raise DirectDownloadLinkException("No refresh token or client ID available")

    session = create_scraper()

    try:
        # Prepare refresh token request - CORRECTED: use 'code' parameter with refresh_token value
        data = {
            "client_id": Config.REAL_DEBRID_CLIENT_ID,
            "code": Config.REAL_DEBRID_REFRESH_TOKEN,  # FIXED: use 'code' not 'refresh_token'
            "grant_type": "refresh_token",  # FIXED: use 'refresh_token' not device grant type
        }

        # Add client secret if available (for server-side apps)
        if Config.REAL_DEBRID_CLIENT_SECRET:
            data["client_secret"] = Config.REAL_DEBRID_CLIENT_SECRET

        # Request new access token
        resp = session.post(
            "https://api.real-debrid.com/oauth/v2/token",
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": user_agent,
            },
            timeout=30,
        )

        if resp.status_code >= 400:
            error_data = resp.json() if resp.content else {"error": "unknown_error"}
            error_msg = error_data.get("error", f"HTTP {resp.status_code}")
            raise DirectDownloadLinkException(f"Token refresh failed: {error_msg}")

        result = resp.json()

        # Update Config with new tokens
        new_access_token = result.get("access_token")
        expires_in = result.get("expires_in", 86400)  # Default 24 hours

        if new_access_token:
            Config.REAL_DEBRID_ACCESS_TOKEN = new_access_token
            Config.REAL_DEBRID_API_KEY = new_access_token  # Update legacy field too

            # Calculate expiration timestamp
            from time import time

            Config.REAL_DEBRID_TOKEN_EXPIRES = (
                int(time()) + expires_in - 300
            )  # 5 min buffer

            # Update refresh token if provided
            new_refresh_token = result.get("refresh_token")
            if new_refresh_token:
                Config.REAL_DEBRID_REFRESH_TOKEN = new_refresh_token

            return new_access_token
        else:
            raise DirectDownloadLinkException("No access token in refresh response")

    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException("Token refresh timeout")
        raise DirectDownloadLinkException(f"Token refresh error: {str(e)}")


def _is_real_debrid_supported(domain):
    """
    Check if a domain is supported by Real-Debrid by fetching the hosts list.
    Based on API docs: GET /hosts

    Args:
        domain: Domain to check

    Returns:
        bool: True if domain is supported
    """
    global real_debrid_supported_sites

    # If we already have the list cached and it's not empty, use it
    if real_debrid_supported_sites:
        return any(domain in site for site in real_debrid_supported_sites)

    # Otherwise, fetch the hosts list from API
    try:
        session = create_scraper()

        # Try to get access token for authenticated request (better rate limits)
        try:
            access_token = _get_valid_real_debrid_token()
            headers = {
                "Authorization": f"Bearer {access_token}",
                "User-Agent": user_agent,
            }
        except:
            # Fallback to unauthenticated request
            headers = {"User-Agent": user_agent}

        resp = session.get(
            "https://api.real-debrid.com/rest/1.0/hosts", headers=headers, timeout=15
        )

        if resp.status_code >= 400:
            # If API call fails, return False (don't try real-debrid)
            return False

        hosts = resp.json()

        # Extract domains from hosts list
        supported_domains = []
        for host in hosts:
            # Each host has: {id, name, image, image_big, domains (array)}
            domains = host.get("domains", [])
            supported_domains.extend(domains)

        # Cache the supported sites
        real_debrid_supported_sites = supported_domains

        # Check if our domain is supported
        return any(domain in site for site in supported_domains)

    except Exception:
        # If anything fails, return False (don't try real-debrid)
        return False


def get_real_debrid_oauth_device_code(
    client_id="X245A4XAIBGVM", new_credentials=False
):
    """
    Helper function to get device code for OAuth2 device flow.
    Used for setting up Real-Debrid authentication on limited input devices.
    Supports both regular device flow and opensource app flow with new credentials.

    Args:
        client_id: Your Real-Debrid app client ID (default: opensource client ID)
        new_credentials: If True, requests new user-bound credentials for opensource apps

    Returns:
        dict: Contains device_code, user_code, verification_url, expires_in, interval
    """
    session = create_scraper()

    try:
        params = {"client_id": client_id}

        # For opensource apps, add new_credentials=yes parameter
        if new_credentials:
            params["new_credentials"] = "yes"

        resp = session.get(
            "https://api.real-debrid.com/oauth/v2/device/code",
            params=params,
            headers={"User-Agent": user_agent},
            timeout=30,
        )

        if resp.status_code >= 400:
            error_data = resp.json() if resp.content else {"error": "unknown_error"}
            error_msg = error_data.get("error", f"HTTP {resp.status_code}")
            raise DirectDownloadLinkException(
                f"Device code request failed: {error_msg}"
            )

        return resp.json()

    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException("Device code request timeout")
        raise DirectDownloadLinkException(f"Device code request error: {str(e)}")


def get_real_debrid_oauth_credentials(client_id, device_code):
    """
    Helper function to get user-bound credentials for opensource apps.
    Based on API docs: GET /oauth/v2/device/credentials
    Used in the opensource app workflow after device authorization.

    Args:
        client_id: Your Real-Debrid app client ID
        device_code: Device code from get_real_debrid_oauth_device_code()

    Returns:
        dict: Contains client_id and client_secret bound to the user

    Raises:
        DirectDownloadLinkException: If credentials request fails or is pending
    """
    session = create_scraper()

    try:
        params = {
            "client_id": client_id,
            "code": device_code,
        }

        resp = session.get(
            "https://api.real-debrid.com/oauth/v2/device/credentials",
            params=params,
            headers={"User-Agent": user_agent},
            timeout=30,
        )

        if resp.status_code >= 400:
            error_data = resp.json() if resp.content else {"error": "unknown_error"}
            error_code = error_data.get("error", f"HTTP {resp.status_code}")

            if "authorization_pending" in error_code or "slow_down" in error_code:
                raise DirectDownloadLinkException("authorization_pending")
            else:
                raise DirectDownloadLinkException(
                    f"Credentials request failed: {error_code}"
                )

        return resp.json()

    except Exception as e:
        if "authorization_pending" in str(e):
            raise e  # Re-raise authorization pending
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException("Credentials request timeout")
        raise DirectDownloadLinkException(f"Credentials request error: {str(e)}")


def poll_real_debrid_oauth_token(client_id, device_code, client_secret=""):
    """
    Helper function to poll for OAuth2 tokens using device code.
    Call this repeatedly until you get tokens or an error.

    Args:
        client_id: Your Real-Debrid app client ID
        device_code: Device code from get_real_debrid_oauth_device_code()
        client_secret: Client secret (optional, not needed for opensource apps)

    Returns:
        dict: Contains access_token, refresh_token, expires_in, token_type

    Raises:
        DirectDownloadLinkException: If authorization is still pending or failed
    """
    session = create_scraper()

    try:
        data = {
            "client_id": client_id,
            "code": device_code,
            "grant_type": "http://oauth.net/grant_type/device/1.0",
        }

        if client_secret:
            data["client_secret"] = client_secret

        resp = session.post(
            "https://api.real-debrid.com/oauth/v2/token",
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": user_agent,
            },
            timeout=30,
        )

        if resp.status_code >= 400:
            error_data = resp.json() if resp.content else {"error": "unknown_error"}
            error_code = error_data.get("error", f"HTTP {resp.status_code}")

            if "authorization_pending" in error_code or "slow_down" in error_code:
                raise DirectDownloadLinkException("authorization_pending")
            else:
                raise DirectDownloadLinkException(
                    f"Token polling failed: {error_code}"
                )

        return resp.json()

    except Exception as e:
        if "authorization_pending" in str(e):
            raise e  # Re-raise authorization pending
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException("Token polling timeout")
        raise DirectDownloadLinkException(f"Token polling error: {str(e)}")


def setup_real_debrid_oauth_device_flow(
    client_id="X245A4XAIBGVM", client_secret="", opensource_app=True
):
    """
    Complete OAuth2 device flow setup for Real-Debrid.
    This is a helper function for initial authentication setup.
    Supports both regular apps and opensource apps with user-bound credentials.

    Args:
        client_id: Your Real-Debrid app client ID (default: opensource client ID)
        client_secret: Client secret (optional, not needed for opensource apps)
        opensource_app: If True, uses opensource app workflow with new credentials

    Returns:
        dict: Contains access_token, refresh_token, expires_in, and optionally client_id/client_secret for Config setup
    """
    try:
        # Step 1: Get device code (with new_credentials for opensource apps)
        LOGGER.info("Getting Real-Debrid device code...")
        device_data = get_real_debrid_oauth_device_code(
            client_id, new_credentials=opensource_app
        )

        device_code = device_data["device_code"]
        user_code = device_data["user_code"]
        verification_url = device_data["verification_url"]
        expires_in = device_data["expires_in"]
        interval = device_data["interval"]

        LOGGER.info(f"Please visit: {verification_url}")
        LOGGER.info(f"Enter this code: {user_code}")
        LOGGER.info(
            f"You have {expires_in // 60} minutes to complete authorization."
        )
        LOGGER.info(f"Polling for authorization every {interval} seconds...")

        # Step 2: For opensource apps, get user-bound credentials first
        user_credentials = None
        if opensource_app:
            LOGGER.info("Waiting for user authorization to get credentials...")
            import time

            start_time = time.time()

            while time.time() - start_time < expires_in:
                try:
                    user_credentials = get_real_debrid_oauth_credentials(
                        client_id, device_code
                    )
                    LOGGER.info("User-bound credentials obtained!")
                    # Update client_id and client_secret with user-bound values
                    client_id = user_credentials["client_id"]
                    client_secret = user_credentials["client_secret"]
                    break
                except DirectDownloadLinkException as e:
                    if "authorization_pending" in str(e):
                        time.sleep(interval)
                        continue
                    else:
                        raise e

            if not user_credentials:
                raise DirectDownloadLinkException(
                    "Failed to get user-bound credentials"
                )

        # Step 3: Poll for tokens using the (possibly updated) credentials
        LOGGER.info("Polling for access tokens...")
        import time

        start_time = time.time()

        while time.time() - start_time < expires_in:
            try:
                token_data = poll_real_debrid_oauth_token(
                    client_id, device_code, client_secret
                )
                LOGGER.info("Real-Debrid authorization successful!")

                # Add user-bound credentials to response for opensource apps
                if opensource_app and user_credentials:
                    token_data["user_client_id"] = client_id
                    token_data["user_client_secret"] = client_secret

                return token_data

            except DirectDownloadLinkException as e:
                if "authorization_pending" in str(e):
                    time.sleep(interval)
                    continue
                else:
                    raise e

        raise DirectDownloadLinkException(
            "Authorization timeout - device code expired"
        )

    except Exception as e:
        raise DirectDownloadLinkException(f"OAuth setup failed: {str(e)}")


def _real_debrid_check_link(session, url, password=""):
    """
    Check a link before unrestricting using Real-Debrid API.
    Based on API docs: POST /unrestrict/check
    This is optional but recommended to verify link availability.

    Args:
        session: HTTP session
        url: URL to check
        password: Optional password for protected links

    Returns:
        dict: Link information (host, filename, filesize, etc.)

    Raises:
        DirectDownloadLinkException: If API request fails
    """
    try:
        # Get valid access token
        access_token = _get_valid_real_debrid_token()

        # Prepare POST data
        data = {"link": url}
        if password:
            data["password"] = password

        # Try Bearer token authentication first
        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": user_agent,
        }

        # Check link using POST request as per API docs
        resp = session.post(
            "https://api.real-debrid.com/rest/1.0/unrestrict/check",
            headers=headers,
            data=data,
            timeout=30,
        )

        # If Bearer token fails, try auth_token query parameter as fallback
        if resp.status_code == 401 or resp.status_code == 403:
            headers_fallback = {"User-Agent": user_agent}
            resp = session.post(
                f"https://api.real-debrid.com/rest/1.0/unrestrict/check?auth_token={access_token}",
                headers=headers_fallback,
                data=data,
                timeout=30,
            )

        if resp.status_code >= 400:
            try:
                error_data = resp.json()
                error_code = error_data.get("error_code", resp.status_code)
                error_msg = error_data.get("error", f"HTTP {resp.status_code}")
            except:
                error_code = resp.status_code
                error_msg = f"HTTP {resp.status_code}"

            # Handle specific error codes based on API documentation
            error_messages = {
                -1: "Internal error",
                1: "Missing parameter",
                2: "Bad parameter value",
                3: "Unknown method",
                4: "Method not allowed",
                5: "Slow down - rate limit exceeded",
                6: "Resource unreachable",
                7: "Resource not found",
                8: "Bad token - invalid or expired",
                9: "Permission denied",
                16: "Unsupported hoster",
                17: "Hoster in maintenance",
                18: "Hoster limit reached",
                19: "Hoster temporarily unavailable",
                20: "Hoster not available for free users",
                24: "File unavailable",
                25: "Service unavailable",
                34: "Too many requests",
                37: "Disabled endpoint",
            }

            specific_msg = error_messages.get(error_code, error_msg)
            raise DirectDownloadLinkException(
                f"ERROR: Real-Debrid check - {specific_msg}"
            )

        result = resp.json()
        return result

    except DirectDownloadLinkException:
        raise
    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException("ERROR: Real-Debrid check timeout")
        raise DirectDownloadLinkException(
            f"ERROR: Real-Debrid check failed - {str(e)}"
        )


def _real_debrid_unrestrict_folder(session, url, password=""):
    """
    Unrestrict a folder link using Real-Debrid API.
    Based on API docs: POST /unrestrict/folder
    Returns multiple download links for folder contents.

    Args:
        session: HTTP session
        url: Folder URL to unrestrict
        password: Optional password for protected folders

    Returns:
        dict: Folder details with multiple download links

    Raises:
        DirectDownloadLinkException: If API request fails
    """
    try:
        # Get valid access token
        access_token = _get_valid_real_debrid_token()

        # Prepare POST data
        data = {"link": url}
        if password:
            data["password"] = password

        # Try Bearer token authentication first
        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": user_agent,
        }

        # Unrestrict folder using POST request as per API docs
        resp = session.post(
            "https://api.real-debrid.com/rest/1.0/unrestrict/folder",
            headers=headers,
            data=data,
            timeout=30,
        )

        # If Bearer token fails, try auth_token query parameter as fallback
        if resp.status_code == 401 or resp.status_code == 403:
            headers_fallback = {"User-Agent": user_agent}
            resp = session.post(
                f"https://api.real-debrid.com/rest/1.0/unrestrict/folder?auth_token={access_token}",
                headers=headers_fallback,
                data=data,
                timeout=30,
            )

        if resp.status_code >= 400:
            try:
                error_data = resp.json()
                error_code = error_data.get("error_code", resp.status_code)
                error_msg = error_data.get("error", f"HTTP {resp.status_code}")
            except:
                error_code = resp.status_code
                error_msg = f"HTTP {resp.status_code}"

            # Handle specific error codes based on API documentation
            error_messages = {
                -1: "Internal error",
                1: "Missing parameter",
                2: "Bad parameter value",
                3: "Unknown method",
                4: "Method not allowed",
                5: "Slow down - rate limit exceeded",
                6: "Resource unreachable",
                7: "Resource not found",
                8: "Bad token - invalid or expired",
                9: "Permission denied",
                16: "Unsupported hoster",
                17: "Hoster in maintenance",
                18: "Hoster limit reached",
                19: "Hoster temporarily unavailable",
                20: "Hoster not available for free users",
                23: "Traffic exhausted",
                24: "File unavailable",
                25: "Service unavailable",
                34: "Too many requests",
                37: "Disabled endpoint",
            }

            specific_msg = error_messages.get(error_code, error_msg)
            raise DirectDownloadLinkException(
                f"ERROR: Real-Debrid folder - {specific_msg}"
            )

        result = resp.json()

        # Process folder response - should contain array of files
        if not isinstance(result, list) or not result:
            raise DirectDownloadLinkException(
                "ERROR: No files found in folder or invalid folder link"
            )

        # Build folder details response
        details = {
            "contents": [],
            "title": unquote(url.rstrip("/").split("/")[-1]),
            "total_size": 0,
        }

        for file_info in result:
            # Each file should have: download, filename, filesize
            download_url = file_info.get("download")
            filename = file_info.get("filename")
            filesize = file_info.get("filesize", 0)

            if download_url and filename:
                item = {
                    "path": details["title"],
                    "filename": filename,
                    "url": download_url,
                }

                # Add file size if available
                if isinstance(filesize, (int, float)) and filesize > 0:
                    details["total_size"] += filesize

                details["contents"].append(item)

        # Check if we have any valid files
        if not details["contents"]:
            raise DirectDownloadLinkException(
                "ERROR: No valid download links found in folder"
            )

        return details

    except DirectDownloadLinkException:
        raise
    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException("ERROR: Real-Debrid folder timeout")
        raise DirectDownloadLinkException(
            f"ERROR: Real-Debrid folder failed - {str(e)}"
        )


def torbox(url):
    """
    TorBox API integration for premium downloads.
    Supports torrents, usenet downloads, and web downloads.

    Args:
        url: URL to download (magnet links, torrent files, usenet links, web links)

    Returns:
        Direct download link or details dictionary for multi-file downloads

    Raises:
        DirectDownloadLinkException: If API request fails or no credentials
    """
    if not Config.TORBOX_API_KEY:
        raise DirectDownloadLinkException(
            "ERROR: TorBox API key not configured. Please set TORBOX_API_KEY in your config."
        )

    session = create_scraper()
    # Prepare headers for Bearer token authentication (for form-data requests)
    # Note: Don't set Content-Type when using files parameter - requests will set it automatically
    headers = {
        "Authorization": f"Bearer {Config.TORBOX_API_KEY}",
        "User-Agent": user_agent,
    }

    try:
        # Determine the type of download based on URL
        download_type = _detect_torbox_download_type(url)

        if download_type == "torrent":
            return _torbox_create_torrent(session, headers, url)
        elif download_type == "usenet":
            return _torbox_create_usenet(session, headers, url)
        elif download_type == "webdl":
            return _torbox_create_webdl(session, headers, url)
        else:
            raise DirectDownloadLinkException(
                f"ERROR: Unsupported URL type for TorBox: {url}"
            )

    except DirectDownloadLinkException:
        raise  # Re-raise our custom exceptions
    except Exception as e:
        if "timeout" in str(e).lower():
            raise DirectDownloadLinkException(
                "ERROR: TorBox API timeout - request timed out"
            )
        raise DirectDownloadLinkException(f"ERROR: TorBox request failed - {str(e)}")


def _detect_torbox_download_type(url):
    """
    Detect the type of download based on URL pattern.

    Args:
        url: URL to analyze

    Returns:
        str: "torrent", "usenet", or "webdl"
    """
    url_lower = url.lower()

    # Torrent detection
    if (
        url_lower.startswith("magnet:")
        or url_lower.endswith(".torrent")
        or "torrent" in url_lower
    ):
        return "torrent"

    # Usenet detection (NZB files)
    if (
        url_lower.endswith(".nzb")
        or "nzb" in url_lower
        or any(x in url_lower for x in ["usenet", "newsgroup"])
    ):
        return "usenet"

    # Default to web download for everything else
    return "webdl"


def _torbox_create_torrent(session, headers, url):
    """
    Create a torrent download using TorBox API.

    Args:
        session: HTTP session
        headers: Request headers with authorization
        url: Magnet link or torrent file URL

    Returns:
        Direct download link or details dictionary
    """
    try:
        # Prepare form data according to API specification
        if url.startswith("magnet:"):
            # For magnet links, use form-data with magnet parameter
            data = {"magnet": url}
            files = None
        else:
            # For torrent file URLs, we need to download and upload the file
            # This is a limitation - we can't directly pass URLs for torrent files
            # TorBox expects actual file upload or magnet links
            try:
                torrent_resp = session.get(url, timeout=30)
                if torrent_resp.status_code == 200:
                    files = {
                        "file": (
                            "torrent.torrent",
                            torrent_resp.content,
                            "application/x-bittorrent",
                        )
                    }
                    data = {}
                else:
                    raise DirectDownloadLinkException(
                        f"ERROR: Could not download torrent file from {url}"
                    )
            except Exception as e:
                raise DirectDownloadLinkException(
                    f"ERROR: Failed to fetch torrent file: {str(e)}"
                )

        # Add optional parameters for better control
        data.update(
            {
                "seed": "1",  # Auto seed (default)
                "allow_zip": "true",  # Allow zipping for large torrents
            }
        )

        # Create torrent download using form-data (not JSON)
        resp = session.post(
            "https://api.torbox.app/v1/api/torrents/createtorrent",
            headers=headers,
            data=data,
            files=files,
            timeout=30,
        )

        if resp.status_code >= 400:
            error_data = resp.json() if resp.content else {"error": "unknown_error"}
            error_msg = error_data.get("detail", f"HTTP {resp.status_code}")
            raise DirectDownloadLinkException(
                f"TorBox torrent creation failed: {error_msg}"
            )

        result = resp.json()

        if not result.get("success", False):
            error_msg = result.get("detail", "Unknown error")
            raise DirectDownloadLinkException(f"ERROR: {error_msg}")

        # Get torrent ID from response data
        # According to API docs, response contains hash, torrent_id, auth_id
        torrent_data = result.get("data", {})
        torrent_id = torrent_data.get("torrent_id")

        if not torrent_id:
            raise DirectDownloadLinkException(
                "ERROR: No torrent ID returned from TorBox"
            )

        # Wait for torrent to be processed and get download links
        return _torbox_get_download_links(session, torrent_id, "torrent")

    except DirectDownloadLinkException:
        raise
    except Exception as e:
        raise DirectDownloadLinkException(
            f"ERROR: TorBox torrent creation failed - {str(e)}"
        )


def _torbox_create_usenet(session, headers, url):
    """
    Create a usenet download using TorBox API.

    Args:
        session: HTTP session
        headers: Request headers with authorization
        url: NZB file URL or link

    Returns:
        Direct download link or details dictionary
    """
    try:
        # Prepare form data according to API specification
        if url.endswith(".nzb"):
            # For NZB file URLs, download and upload the file
            try:
                nzb_resp = session.get(url, timeout=30)
                if nzb_resp.status_code == 200:
                    files = {
                        "file": (
                            "download.nzb",
                            nzb_resp.content,
                            "application/x-nzb",
                        )
                    }
                    data = {}
                else:
                    raise DirectDownloadLinkException(
                        f"ERROR: Could not download NZB file from {url}"
                    )
            except Exception as e:
                raise DirectDownloadLinkException(
                    f"ERROR: Failed to fetch NZB file: {str(e)}"
                )
        else:
            # For direct links to NZB content
            data = {"link": url}
            files = None

        # Add optional parameters according to API docs
        data.update(
            {
                "post_processing": "-1",  # Default processing (repair, extract, delete source)
                "as_queued": "false",  # Process immediately if possible
            }
        )

        # Create usenet download using form-data
        resp = session.post(
            "https://api.torbox.app/v1/api/usenet/createusenetdownload",
            headers=headers,
            data=data,
            files=files,
            timeout=30,
        )

        if resp.status_code >= 400:
            error_data = resp.json() if resp.content else {"error": "unknown_error"}
            error_msg = error_data.get("detail", f"HTTP {resp.status_code}")
            raise DirectDownloadLinkException(
                f"TorBox usenet creation failed: {error_msg}"
            )

        result = resp.json()

        if not result.get("success", False):
            error_msg = result.get("detail", "Unknown error")
            raise DirectDownloadLinkException(f"ERROR: {error_msg}")

        # Get usenet ID from response data
        # According to API docs, response contains hash, usenetdownload_id, auth_id
        usenet_data = result.get("data", {})
        usenet_id = usenet_data.get("usenetdownload_id")

        if not usenet_id:
            raise DirectDownloadLinkException(
                "ERROR: No usenet ID returned from TorBox"
            )

        # Wait for usenet download to be processed and get download links
        return _torbox_get_download_links(session, usenet_id, "usenet")

    except DirectDownloadLinkException:
        raise
    except Exception as e:
        raise DirectDownloadLinkException(
            f"ERROR: TorBox usenet creation failed - {str(e)}"
        )


def _torbox_create_webdl(session, headers, url):
    """
    Create a web download using TorBox API.

    Args:
        session: HTTP session
        headers: Request headers with authorization
        url: Web download URL

    Returns:
        Direct download link or details dictionary
    """
    try:
        # Prepare form data according to API specification
        data = {
            "link": url,
            "as_queued": "false",  # Process immediately if possible
        }

        # Create web download using form-data
        resp = session.post(
            "https://api.torbox.app/v1/api/webdl/createwebdownload",
            headers=headers,
            data=data,
            timeout=30,
        )

        if resp.status_code >= 400:
            error_data = resp.json() if resp.content else {"error": "unknown_error"}
            error_msg = error_data.get("detail", f"HTTP {resp.status_code}")
            raise DirectDownloadLinkException(
                f"TorBox web download creation failed: {error_msg}"
            )

        result = resp.json()

        if not result.get("success", False):
            error_msg = result.get("detail", "Unknown error")
            raise DirectDownloadLinkException(f"ERROR: {error_msg}")

        # Get web download ID from response data
        # According to API docs, response contains hash, webdownload_id, auth_id
        webdl_data = result.get("data", {})
        webdl_id = webdl_data.get("webdownload_id")

        if not webdl_id:
            raise DirectDownloadLinkException(
                "ERROR: No web download ID returned from TorBox"
            )

        # Wait for web download to be processed and get download links
        return _torbox_get_download_links(session, webdl_id, "webdl")

    except DirectDownloadLinkException:
        raise
    except Exception as e:
        raise DirectDownloadLinkException(
            f"ERROR: TorBox web download creation failed - {str(e)}"
        )


def _torbox_get_download_links(session, download_id, download_type):
    """
    Get download links from TorBox after processing is complete.

    Args:
        session: HTTP session
        download_id: ID of the download (torrent_id, usenet_id, or webdl_id)
        download_type: Type of download ("torrent", "usenet", or "webdl")

    Returns:
        Direct download link or details dictionary for multi-file downloads
    """
    import time

    try:
        # Prepare headers for Bearer token authentication (for status checks)
        headers = {
            "Authorization": f"Bearer {Config.TORBOX_API_KEY}",
            "User-Agent": user_agent,
        }

        # Wait for processing to complete (max 5 minutes)
        max_wait_time = 300  # 5 minutes
        check_interval = 10  # Check every 10 seconds
        start_time = time.time()

        while time.time() - start_time < max_wait_time:
            # Get download status using Bearer token
            if download_type == "torrent":
                list_url = (
                    f"https://api.torbox.app/v1/api/torrents/mylist?id={download_id}"
                )
            elif download_type == "usenet":
                list_url = (
                    f"https://api.torbox.app/v1/api/usenet/mylist?id={download_id}"
                )
            else:  # webdl
                list_url = (
                    f"https://api.torbox.app/v1/api/webdl/mylist?id={download_id}"
                )

            resp = session.get(list_url, headers=headers, timeout=30)

            if resp.status_code >= 400:
                error_data = (
                    resp.json() if resp.content else {"error": "unknown_error"}
                )
                error_msg = error_data.get("detail", f"HTTP {resp.status_code}")
                raise DirectDownloadLinkException(
                    f"TorBox status check failed: {error_msg}"
                )

            result = resp.json()

            if not result.get("success", False):
                error_msg = result.get("detail", "Unknown error")
                raise DirectDownloadLinkException(f"ERROR: {error_msg}")

            data = result.get("data")
            if not data:
                time.sleep(check_interval)
                continue

            # Handle both single item and list responses
            if isinstance(data, list):
                if not data:
                    time.sleep(check_interval)
                    continue
                download_info = data[0]
            else:
                download_info = data

            # Check if download is finished
            download_finished = download_info.get("download_finished", False)
            download_present = download_info.get("download_present", False)

            if download_finished and download_present:
                # Get files and generate download links
                files = download_info.get("files", [])
                if not files:
                    raise DirectDownloadLinkException(
                        "ERROR: No files found in TorBox download"
                    )

                # If single file, return direct link
                if len(files) == 1:
                    file_info = files[0]
                    file_id = file_info.get("id")
                    if not file_id:
                        raise DirectDownloadLinkException("ERROR: No file ID found")

                    # Request download link using query parameters (not Bearer header)
                    # According to API docs: "Requires an API key as a parameter for the token parameter"
                    # IMPORTANT: Usenet uses "torrent_id" parameter, not "usenet_id" (API inconsistency)
                    if download_type == "torrent":
                        dl_url = f"https://api.torbox.app/v1/api/torrents/requestdl?token={Config.TORBOX_API_KEY}&torrent_id={download_id}&file_id={file_id}"
                    elif download_type == "usenet":
                        dl_url = f"https://api.torbox.app/v1/api/usenet/requestdl?token={Config.TORBOX_API_KEY}&torrent_id={download_id}&file_id={file_id}"
                    else:  # webdl
                        dl_url = f"https://api.torbox.app/v1/api/webdl/requestdl?token={Config.TORBOX_API_KEY}&web_id={download_id}&file_id={file_id}"

                    # Get the actual download URL (no Bearer header needed for this endpoint)
                    dl_resp = session.get(dl_url, timeout=30)
                    if dl_resp.status_code >= 400:
                        raise DirectDownloadLinkException(
                            "ERROR: Failed to get download URL from TorBox"
                        )

                    dl_result = dl_resp.json()
                    if dl_result.get("success") and dl_result.get("data"):
                        return dl_result["data"]
                    else:
                        raise DirectDownloadLinkException(
                            "ERROR: Invalid download URL response from TorBox"
                        )

                # Multiple files - return details dictionary
                else:
                    details = {
                        "contents": [],
                        "title": download_info.get("name", "TorBox Download"),
                        "total_size": download_info.get("size", 0),
                    }

                    for file_info in files:
                        file_id = file_info.get("id")
                        if not file_id:
                            continue

                        # Request download link for each file using query parameters
                        # IMPORTANT: Usenet uses "torrent_id" parameter, not "usenet_id" (API inconsistency)
                        if download_type == "torrent":
                            dl_url = f"https://api.torbox.app/v1/api/torrents/requestdl?token={Config.TORBOX_API_KEY}&torrent_id={download_id}&file_id={file_id}"
                        elif download_type == "usenet":
                            dl_url = f"https://api.torbox.app/v1/api/usenet/requestdl?token={Config.TORBOX_API_KEY}&torrent_id={download_id}&file_id={file_id}"
                        else:  # webdl
                            dl_url = f"https://api.torbox.app/v1/api/webdl/requestdl?token={Config.TORBOX_API_KEY}&web_id={download_id}&file_id={file_id}"

                        try:
                            # No Bearer header needed for requestdl endpoint
                            dl_resp = session.get(dl_url, timeout=30)
                            if dl_resp.status_code >= 400:
                                continue

                            dl_result = dl_resp.json()
                            if dl_result.get("success") and dl_result.get("data"):
                                item = {
                                    "path": details["title"],
                                    "filename": file_info.get(
                                        "name", f"file_{file_id}"
                                    ),
                                    "url": dl_result["data"],
                                }
                                details["contents"].append(item)
                        except:
                            continue  # Skip failed files

                    if not details["contents"]:
                        raise DirectDownloadLinkException(
                            "ERROR: No valid download links found"
                        )

                    return details

            # Check for errors
            if download_info.get("download_state") == "error":
                error_msg = download_info.get("error", "Unknown download error")
                raise DirectDownloadLinkException(
                    f"ERROR: TorBox download failed - {error_msg}"
                )

            # Continue waiting
            time.sleep(check_interval)

        # Timeout reached
        raise DirectDownloadLinkException(
            "ERROR: TorBox download processing timeout (5 minutes)"
        )

    except DirectDownloadLinkException:
        raise
    except Exception as e:
        raise DirectDownloadLinkException(
            f"ERROR: TorBox download link retrieval failed - {str(e)}"
        )


def buzzheavier(url):
    """
    Generate a direct download link for buzzheavier URLs.
    @param link: URL from buzzheavier
    @return: Direct download link
    """
    pattern = r"^https?://buzzheavier\.com/[a-zA-Z0-9]+$"
    if not match(pattern, url):
        return url

    def _bhscraper(url, folder=False):
        session = Session()
        if "/download" not in url:
            url += "/download"
        url = url.strip()
        session.headers.update(
            {
                "referer": url.split("/download")[0],
                "hx-current-url": url.split("/download")[0],
                "hx-request": "true",
                "priority": "u=1, i",
            }
        )
        try:
            response = session.get(url)
            d_url = response.headers.get("Hx-Redirect")
            if not d_url:
                if not folder:
                    raise DirectDownloadLinkException(
                        f"ERROR: Gagal mendapatkan data"
                    )
                return
            return d_url
        except Exception as e:
            raise DirectDownloadLinkException(f"ERROR: {str(e)}") from e

    with Session() as session:
        tree = HTML(session.get(url).text)
        if link := tree.xpath(
            "//a[contains(@class, 'link-button') and contains(@class, 'gay-button')]/@hx-get"
        ):
            return _bhscraper("https://buzzheavier.com" + link[0])
        elif folders := tree.xpath("//tbody[@id='tbody']/tr"):
            details = {"contents": [], "title": "", "total_size": 0}
            for data in folders:
                try:
                    filename = data.xpath(".//a")[0].text.strip()
                    _id = data.xpath(".//a")[0].attrib.get("href", "").strip()
                    size = data.xpath(".//td[@class='text-center']/text()")[
                        0
                    ].strip()
                    url = _bhscraper(f"https://buzzheavier.com{_id}", True)
                    item = {
                        "path": "",
                        "filename": filename,
                        "url": url,
                    }
                    details["contents"].append(item)
                    size = speed_string_to_bytes(size)
                    details["total_size"] += size
                except:
                    continue
            details["title"] = tree.xpath("//span/text()")[0].strip()
            return details
        else:
            raise DirectDownloadLinkException("ERROR: No download link found")


def fuckingfast_dl(url):
    """
    Generate a direct download link for fuckingfast.co URLs.
    @param url: URL from fuckingfast.co
    @return: Direct download link
    """
    url = url.strip()

    try:
        response = get(url)
        content = response.text
        pattern = r'window\.open\((["\'])(https://fuckingfast\.co/dl/[^"\']+)\1'
        match = search(pattern, content)

        if not match:
            raise DirectDownloadLinkException(
                "ERROR: Could not find download link in page"
            )

        direct_url = match.group(2)
        return direct_url

    except Exception as e:
        raise DirectDownloadLinkException(f"ERROR: {str(e)}") from e


def lulacloud(url):
    """
    Generate a direct download link for www.lulacloud.com URLs.
    @param url: URL from www.lulacloud.com
    @return: Direct download link
    """
    try:
        res = post(url, headers={"Referer": url}, allow_redirects=False)
        return res.headers["location"]
    except Exception as e:
        raise DirectDownloadLinkException(f"ERROR: {str(e)}") from e


def devuploads(url):
    """
    Generate a direct download link for devuploads.com URLs.
    @param url: URL from devuploads.com
    @return: Direct download link
    """
    with Session() as session:
        res = session.get(url)
        html = HTML(res.text)
        if not html.xpath("//input[@name]"):
            raise DirectDownloadLinkException("ERROR: Unable to find link data")
        data = {i.get("name"): i.get("value") for i in html.xpath("//input[@name]")}
        res = session.post("https://gujjukhabar.in/", data=data)
        html = HTML(res.text)
        if not html.xpath("//input[@name]"):
            raise DirectDownloadLinkException("ERROR: Unable to find link data")
        data = {i.get("name"): i.get("value") for i in html.xpath("//input[@name]")}
        resp = session.get(
            "https://du2.devuploads.com/dlhash.php",
            headers={
                "Origin": "https://gujjukhabar.in",
                "Referer": "https://gujjukhabar.in/",
            },
        )
        if not resp.text:
            raise DirectDownloadLinkException("ERROR: Unable to find ipp value")
        data["ipp"] = resp.text.strip()
        if not data.get("rand"):
            raise DirectDownloadLinkException("ERROR: Unable to find rand value")
        randpost = session.post(
            "https://devuploads.com/token/token.php",
            data={"rand": data["rand"], "msg": ""},
            headers={
                "Origin": "https://gujjukhabar.in",
                "Referer": "https://gujjukhabar.in/",
            },
        )
        if not randpost:
            raise DirectDownloadLinkException("ERROR: Unable to find xd value")
        data["xd"] = randpost.text.strip()
        res = session.post(url, data=data)
        html = HTML(res.text)
        if not html.xpath("//input[@name='orilink']/@value"):
            raise DirectDownloadLinkException("ERROR: Unable to find Direct Link")
        direct_link = html.xpath("//input[@name='orilink']/@value")
        return direct_link[0]


def uploadhaven(url):
    """
    Generate a direct download link for uploadhaven.com URLs.
    @param url: URL from uploadhaven.com
    @return: Direct download link
    """
    try:
        res = get(url, headers={"Referer": "http://steamunlocked.net/"})
        html = HTML(res.text)
        if not html.xpath('//form[@method="POST"]//input'):
            raise DirectDownloadLinkException("ERROR: Unable to find link data")
        data = {
            i.get("name"): i.get("value")
            for i in html.xpath('//form[@method="POST"]//input')
        }
        sleep(15)
        res = post(url, data=data, headers={"Referer": url}, cookies=res.cookies)
        html = HTML(res.text)
        if not html.xpath('//div[@class="alert alert-success mb-0"]//a'):
            raise DirectDownloadLinkException("ERROR: Unable to find link data")
        a = html.xpath('//div[@class="alert alert-success mb-0"]//a')[0]
        return a.get("href")
    except Exception as e:
        raise DirectDownloadLinkException(f"ERROR: {str(e)}") from e


def mediafile(url):
    """
    Generate a direct download link for mediafile.cc URLs.
    @param url: URL from mediafile.cc
    @return: Direct download link
    """
    try:
        res = get(url, allow_redirects=True)
        match = search(r"href='([^']+)'", res.text)
        if not match:
            raise DirectDownloadLinkException("ERROR: Unable to find link data")
        download_url = match.group(1)
        sleep(60)
        res = get(download_url, headers={"Referer": url}, cookies=res.cookies)
        postvalue = search(r"showFileInformation(.*);", res.text)
        if not postvalue:
            raise DirectDownloadLinkException("ERROR: Unable to find post value")
        postid = postvalue.group(1).replace("(", "").replace(")", "")
        response = post(
            "https://mediafile.cc/account/ajax/file_details",
            data={"u": postid},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        html = response.json()["html"]
        return [
            i for i in findall(r'https://[^\s"\']+', html) if "download_token" in i
        ][1]
    except Exception as e:
        raise DirectDownloadLinkException(f"ERROR: {str(e)}") from e


def mediafireFolder(url, user_id=None):
    """
    Enhanced MediaFire folder download with API authentication support.
    Provides access to private folders and higher rate limits when credentials are available.
    """
    if "::" in url:
        _password = url.split("::")[-1]
        url = url.split("::")[-2]
    else:
        _password = ""

    try:
        raw = url.split("/", 4)[-1]
        folderkey = raw.split("/", 1)[0]
        folderkey = folderkey.split(",")
    except:
        raise DirectDownloadLinkException("ERROR: Could not parse ")

    if len(folderkey) == 1:
        folderkey = folderkey[0]

    details = {"contents": [], "title": "", "total_size": 0, "header": ""}

    # Try authenticated API first if credentials are available
    try:
        # Get MediaFire credentials with user priority
        mediafire_email, mediafire_password, mediafire_app_id = (
            _get_mediafire_credentials(user_id)
        )

        if mediafire_email and mediafire_password and mediafire_app_id:
            auth_result = _mediafire_authenticated_folder_download(
                folderkey, _password, user_id
            )
            if auth_result:
                return auth_result
    except Exception as e:
        LOGGER.warning(
            f"MediaFire authenticated folder download failed, using public API: {e}"
        )

    # Fallback to public API method (current implementation)

    session = create_scraper()
    adapter = HTTPAdapter(
        max_retries=Retry(total=10, read=10, connect=10, backoff_factor=0.3)
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session = create_scraper(
        browser={"browser": "firefox", "platform": "windows", "mobile": False},
        delay=10,
        sess=session,
    )
    folder_infos = []

    def __get_info(folderkey):
        try:
            if isinstance(folderkey, list):
                folderkey = ",".join(folderkey)
            _json = session.post(
                "https://www.mediafire.com/api/1.5/folder/get_info.php",
                data={
                    "recursive": "yes",
                    "folder_key": folderkey,
                    "response_format": "json",
                },
            ).json()
        except Exception as e:
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__} While getting info"
            )
        _res = _json["response"]
        if "folder_infos" in _res:
            folder_infos.extend(_res["folder_infos"])
        elif "folder_info" in _res:
            folder_infos.append(_res["folder_info"])
        elif "message" in _res:
            raise DirectDownloadLinkException(f"ERROR: {_res['message']}")
        else:
            raise DirectDownloadLinkException("ERROR: something went wrong!")

    try:
        __get_info(folderkey)
    except Exception as e:
        raise DirectDownloadLinkException(e)

    details["title"] = folder_infos[0]["name"]

    def __scraper(url):
        session = create_scraper()
        parsed_url = urlparse(url)
        url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"

        try:
            html = HTML(session.get(url).text)
        except:
            return None
        if html.xpath("//div[@class='passwordPrompt']"):
            if not _password:
                raise DirectDownloadLinkException(
                    f"ERROR: {PASSWORD_ERROR_MESSAGE}".format(url)
                )
            try:
                html = HTML(session.post(url, data={"downloadp": _password}).text)
            except:
                return None
            if html.xpath("//div[@class='passwordPrompt']"):
                return None
        try:
            final_link = __decode_url(html)
        except:
            return None
        return final_link

    def __decode_url(html):
        enc_url = html.xpath('//a[@id="downloadButton"]')
        if enc_url:
            final_link = enc_url[0].attrib.get("href")
            scrambled = enc_url[0].attrib.get("data-scrambled-url")
            if final_link and scrambled:
                try:
                    final_link = b64decode(scrambled).decode("utf-8")
                    return final_link
                except:
                    return None
            elif final_link.startswith("http"):
                return final_link
            elif final_link.startswith("//"):
                return __scraper(f"https:{final_link}")
            else:
                return None
        else:
            return None

    def __get_content(folderKey, folderPath="", content_type="folders"):
        try:
            params = {
                "content_type": content_type,
                "folder_key": folderKey,
                "response_format": "json",
            }
            _json = session.get(
                "https://www.mediafire.com/api/1.5/folder/get_content.php",
                params=params,
            ).json()
        except Exception as e:
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__} While getting content"
            )
        _res = _json["response"]
        if "message" in _res:
            raise DirectDownloadLinkException(f"ERROR: {_res['message']}")
        _folder_content = _res["folder_content"]
        if content_type == "folders":
            folders = _folder_content["folders"]
            for folder in folders:
                if folderPath:
                    newFolderPath = ospath.join(folderPath, folder["name"])
                else:
                    newFolderPath = ospath.join(folder["name"])
                __get_content(folder["folderkey"], newFolderPath)
            __get_content(folderKey, folderPath, "files")
        else:
            files = _folder_content["files"]
            for file in files:
                item = {}
                if not (_url := __scraper(file["links"]["normal_download"])):
                    continue
                item["filename"] = file["filename"]
                if not folderPath:
                    folderPath = details["title"]
                item["path"] = ospath.join(folderPath)
                item["url"] = _url
                if "size" in file:
                    size = file["size"]
                    if isinstance(size, str) and size.isdigit():
                        size = float(size)
                    details["total_size"] += size
                details["contents"].append(item)

    try:
        for folder in folder_infos:
            __get_content(folder["folderkey"], folder["name"])
    except Exception as e:
        raise DirectDownloadLinkException(e)
    finally:
        session.close()
    if len(details["contents"]) == 1:
        return (details["contents"][0]["url"], [details["header"]])
    return details


def mediafire(url, session=None, user_id=None):
    """
    Enhanced MediaFire download with API support as fallback.
    Supports both individual files and folders with credentials.
    """
    if "/folder/" in url:
        return mediafireFolder(url, user_id)

    # Extract password if present
    if "::" in url:
        _password = url.split("::")[-1]
        url = url.split("::")[-2]
    else:
        _password = ""

    # Check if already a direct download link
    if final_link := findall(
        r"https?:\/\/download\d+\.mediafire\.com\/\S+\/\S+\/\S+", url
    ):
        return final_link[0]

    # Try API-based download first if credentials are available
    try:
        # Get MediaFire credentials with user priority
        mediafire_email, mediafire_password, mediafire_app_id = (
            _get_mediafire_credentials(user_id)
        )

        if mediafire_email and mediafire_password and mediafire_app_id:
            api_result = _mediafire_api_download(url, _password, user_id)
            if api_result:
                return api_result
    except Exception as e:
        LOGGER.warning(
            f"MediaFire API download failed, falling back to scraping: {e}"
        )

    # Fallback to web scraping method
    return _mediafire_scraping_download(url, _password, session, user_id)


def _get_mediafire_credentials(user_id=None):
    """
    Get MediaFire credentials with user priority over owner settings.
    Returns tuple: (email, password, app_id)
    """
    from bot.core.config_manager import Config
    from bot import user_data

    # Get user settings with fallback to owner settings
    user_dict = user_data.get(user_id, {}) if user_id else {}

    def get_mediafire_setting(user_key, owner_attr, default_value=""):
        user_value = user_dict.get(user_key)
        if user_value is not None:
            return user_value
        return getattr(Config, owner_attr, default_value)

    # Get MediaFire credentials with user priority
    email = get_mediafire_setting("MEDIAFIRE_EMAIL", "MEDIAFIRE_EMAIL", "")
    password = get_mediafire_setting("MEDIAFIRE_PASSWORD", "MEDIAFIRE_PASSWORD", "")
    app_id = get_mediafire_setting("MEDIAFIRE_APP_ID", "MEDIAFIRE_APP_ID", "")

    return email, password, app_id


def _mediafire_api_download(url, password="", user_id=None):
    """
    Download MediaFire file using official API with authentication.
    Provides access to private files and higher rate limits.
    """

    try:
        # Extract quickkey from URL
        quickkey_match = findall(r"/file/([a-zA-Z0-9]+)/", url)
        if not quickkey_match:
            return None

        quickkey = quickkey_match[0]

        # Create session for API calls
        session = create_scraper()

        # Step 1: Get session token with user credentials
        session_token = _get_mediafire_session_token(session, user_id)
        if not session_token:
            return None

        # Step 2: Get file info to check if accessible
        file_info = _get_mediafire_file_info(session, quickkey, session_token)
        if not file_info:
            return None

        # Step 3: Handle password-protected files
        if file_info.get("password_protected") == "yes" and password:
            # For password-protected files, we still need to use web scraping
            # as the API doesn't provide direct password handling for downloads
            return None

        # Step 4: Get direct download link via API
        download_link = _get_mediafire_download_link(
            session, quickkey, session_token
        )
        if download_link:
            session.close()
            return download_link

    except Exception as e:
        LOGGER.warning(f"MediaFire API download error: {e}")

    return None


def _get_mediafire_session_token(session, user_id=None):
    """Get MediaFire session token using email/password authentication with user priority."""
    import hashlib

    try:
        # Get MediaFire credentials with user priority
        email, password, app_id = _get_mediafire_credentials(user_id)

        # Get API key with user priority
        from bot.core.config_manager import Config
        from bot import user_data

        user_dict = user_data.get(user_id, {}) if user_id else {}
        api_key = (
            user_dict.get("MEDIAFIRE_API_KEY")
            or getattr(Config, "MEDIAFIRE_API_KEY", "")
            or ""
        )

        # Create signature for authentication
        signature_string = f"{email}{password}{app_id}{api_key}"
        signature = hashlib.sha1(signature_string.encode()).hexdigest()

        # Request session token
        auth_url = "https://www.mediafire.com/api/1.5/user/get_session_token.php"
        auth_data = {
            "email": email,
            "password": password,
            "application_id": app_id,
            "signature": signature,
            "response_format": "json",
        }

        response = session.post(auth_url, data=auth_data)
        result = response.json()

        if result.get("response", {}).get("result") == "Success":
            return result["response"]["session_token"]
        else:
            LOGGER.warning(
                f"MediaFire authentication failed: {result.get('response', {}).get('message', 'Unknown error')}"
            )

    except Exception as e:
        LOGGER.warning(f"MediaFire session token error: {e}")

    return None


def _get_mediafire_file_info(session, quickkey, session_token):
    """Get file information using MediaFire API."""
    try:
        info_url = "https://www.mediafire.com/api/1.5/file/get_info.php"
        params = {
            "quick_key": quickkey,
            "session_token": session_token,
            "response_format": "json",
        }

        response = session.get(info_url, params=params)
        result = response.json()

        if result.get("response", {}).get("result") == "Success":
            file_info = result["response"]["file_info"]
            return file_info

    except Exception as e:
        print(f"MediaFire file info error: {e}")

    return None


def _get_mediafire_download_link(session, quickkey, session_token):
    """Get direct download link using MediaFire API."""
    try:
        download_url = "https://www.mediafire.com/api/1.5/file/get_links.php"
        params = {
            "quick_key": quickkey,
            "link_type": "direct_download",
            "session_token": session_token,
            "response_format": "json",
        }

        response = session.get(download_url, params=params)
        result = response.json()

        if result.get("response", {}).get("result") == "Success":
            links = result["response"]["links"]
            if links and len(links) > 0:
                return links[0]["direct_download"]

    except Exception as e:
        LOGGER.warning(f"MediaFire download link error: {e}")

    return None


def _mediafire_scraping_download(url, password="", session=None):
    """
    Original web scraping method for MediaFire downloads.
    Used as fallback when API method fails or for password-protected files.
    """

    def _decode_url(html, session):
        enc_url = html.xpath('//a[@id="downloadButton"]')
        if enc_url:
            final_link = enc_url[0].attrib.get("href")
            scrambled = enc_url[0].attrib.get("data-scrambled-url")

            if final_link and scrambled:
                try:
                    final_link = b64decode(scrambled).decode("utf-8")
                    return final_link
                except Exception as e:
                    raise ValueError(
                        f"Failed to decode final link. {e.__class__.__name__}"
                    ) from e
            elif final_link.startswith("http"):
                return final_link
            elif final_link.startswith("//"):
                return mediafire(f"https:{final_link}", session=session)
            else:
                raise ValueError(f"No download link found")
        else:
            raise ValueError(
                "Download button not found in the HTML content. It may have been blocked by Cloudflare's anti-bot protection."
            )

    if session is None:
        session = create_scraper()
        parsed_url = urlparse(url)
        url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"

    try:
        html = HTML(session.get(url).text)
    except Exception as e:
        session.close()
        raise DirectDownloadLinkException(f"ERROR: {e.__class__.__name__}") from e

    if error := html.xpath('//p[@class="notranslate"]/text()'):
        session.close()
        raise DirectDownloadLinkException(f"ERROR: {error[0]}")

    if html.xpath("//div[@class='passwordPrompt']"):
        if not password:
            session.close()
            raise DirectDownloadLinkException(
                f"ERROR: {PASSWORD_ERROR_MESSAGE}".format(url)
            )
        try:
            html = HTML(session.post(url, data={"downloadp": password}).text)
        except Exception as e:
            session.close()
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__}"
            ) from e
        if html.xpath("//div[@class='passwordPrompt']"):
            session.close()
            raise DirectDownloadLinkException("ERROR: Wrong password.")
    try:
        final_link = _decode_url(html, session)
    except Exception as e:
        raise DirectDownloadLinkException(f"ERROR: {str(e)}")
    session.close()
    return final_link


def _mediafire_authenticated_folder_download(folderkey, password="", user_id=None):
    """
    Download MediaFire folder using authenticated API for private folders and higher rate limits.
    """
    try:
        # Create session for API calls
        session = create_scraper()

        # Get session token with user credentials
        session_token = _get_mediafire_session_token(session, user_id)
        if not session_token:
            return None

        # Get folder info with authentication
        folder_info = _get_mediafire_authenticated_folder_info(
            session, folderkey, session_token
        )
        if not folder_info:
            return None

        # Get folder contents with authentication
        folder_contents = _get_mediafire_authenticated_folder_contents(
            session, folderkey, session_token
        )
        if not folder_contents:
            return None

        session.close()
        return folder_contents

    except Exception as e:
        LOGGER.warning(f"MediaFire authenticated folder download error: {e}")

    return None


def _get_mediafire_authenticated_folder_info(session, folderkey, session_token):
    """Get folder information using authenticated MediaFire API."""
    try:
        info_url = "https://www.mediafire.com/api/1.5/folder/get_info.php"
        params = {
            "folder_key": folderkey,
            "session_token": session_token,
            "recursive": "yes",
            "response_format": "json",
        }

        response = session.get(info_url, params=params)
        result = response.json()

        if result.get("response", {}).get("result") == "Success":
            return result["response"]

    except Exception as e:
        LOGGER.warning(f"MediaFire authenticated folder info error: {e}")

    return None


def _get_mediafire_authenticated_folder_contents(session, folderkey, session_token):
    """Get folder contents using authenticated MediaFire API with enhanced access."""
    try:
        details = {"contents": [], "title": "", "total_size": 0, "header": ""}

        # Get folder content
        content_url = "https://www.mediafire.com/api/1.5/folder/get_content.php"
        params = {
            "folder_key": folderkey,
            "session_token": session_token,
            "content_type": "files",
            "response_format": "json",
        }

        response = session.get(content_url, params=params)
        result = response.json()

        if result.get("response", {}).get("result") == "Success":
            folder_content = result["response"]["folder_content"]

            # Set folder details
            details["title"] = folder_content.get("name", "MediaFire Folder")
            details["header"] = f"MediaFire Folder: {details['title']}"

            # Process files
            if "files" in folder_content:
                for file in folder_content["files"]:
                    # Get direct download link for each file using authenticated API
                    download_link = _get_mediafire_download_link(
                        session, file["quickkey"], session_token
                    )
                    if download_link:
                        item = {
                            "filename": file["filename"],
                            "path": details["title"],
                            "url": download_link,
                        }

                        # Add file size if available
                        if "size" in file:
                            size = int(file["size"])
                            details["total_size"] += size

                        details["contents"].append(item)

            # Handle single file case
            if len(details["contents"]) == 1:
                return (details["contents"][0]["url"], [details["header"]])

            return details

    except Exception as e:
        LOGGER.warning(f"MediaFire authenticated folder contents error: {e}")

    return None


def osdn(url):
    with create_scraper() as session:
        try:
            html = HTML(session.get(url).text)
        except Exception as e:
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__}"
            ) from e
        if not (direct_link := html.xapth('//a[@class="mirror_link"]/@href')):
            raise DirectDownloadLinkException("ERROR: Direct link not found")
        return f"https://osdn.net{direct_link[0]}"


def yandex_disk(url: str) -> str:
    """Yandex.Disk direct link generator
    Based on https://github.com/wldhx/yadisk-direct"""
    try:
        link = findall(r"\b(https?://(yadi\.sk|disk\.yandex\.(com|ru))\S+)", url)[0][
            0
        ]
    except IndexError:
        return "No Yandex.Disk links found\n"
    api = "https://cloud-api.yandex.net/v1/disk/public/resources/download?public_key={}"
    try:
        return get(api.format(link)).json()["href"]
    except KeyError as e:
        raise DirectDownloadLinkException(
            "ERROR: File not found/Download limit reached"
        ) from e


def github(url):
    """GitHub direct links generator"""
    try:
        findall(r"\bhttps?://.*github\.com.*releases\S+", url)[0]
    except IndexError as e:
        raise DirectDownloadLinkException("No GitHub Releases links found") from e
    with create_scraper() as session:
        _res = session.get(url, stream=True, allow_redirects=False)
        if "location" in _res.headers:
            return _res.headers["location"]
        raise DirectDownloadLinkException("ERROR: Can't extract the link")


def hxfile(url):
    if not ospath.isfile("hxfile.txt"):
        raise DirectDownloadLinkException("ERROR: hxfile.txt (cookies) Not Found!")
    try:
        jar = MozillaCookieJar()
        jar.load("hxfile.txt")
    except Exception as e:
        raise DirectDownloadLinkException(f"ERROR: {e.__class__.__name__}") from e
    cookies = {cookie.name: cookie.value for cookie in jar}
    try:
        if url.strip().endswith(".html"):
            url = url[:-5]
        file_code = url.split("/")[-1]
        html = HTML(
            post(
                url,
                data={"op": "download2", "id": file_code},
                cookies=cookies,
            ).text
        )
    except Exception as e:
        raise DirectDownloadLinkException(f"ERROR: {e.__class__.__name__}") from e
    if direct_link := html.xpath("//a[@class='btn btn-dow']/@href"):
        header = [f"Referer: {url}"]
        return direct_link[0], header
    raise DirectDownloadLinkException("ERROR: Direct download link not found")


def onedrive(link):
    """Onedrive direct link generator
    By https://github.com/junedkh"""
    with create_scraper() as session:
        try:
            link = session.get(link).url
            parsed_link = urlparse(link)
            link_data = parse_qs(parsed_link.query)
        except Exception as e:
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__}"
            ) from e
        if not link_data:
            raise DirectDownloadLinkException("ERROR: Unable to find link_data")
        folder_id = link_data.get("resid")
        if not folder_id:
            raise DirectDownloadLinkException("ERROR: folder id not found")
        folder_id = folder_id[0]
        authkey = link_data.get("authkey")
        if not authkey:
            raise DirectDownloadLinkException("ERROR: authkey not found")
        authkey = authkey[0]
        boundary = uuid4()
        headers = {"content-type": f"multipart/form-data;boundary={boundary}"}
        data = f"--{boundary}\r\nContent-Disposition: form-data;name=data\r\nPrefer: Migration=EnableRedirect;FailOnMigratedFiles\r\nX-HTTP-Method-Override: GET\r\nContent-Type: application/json\r\n\r\n--{boundary}--"
        try:
            resp = session.get(
                f"https://api.onedrive.com/v1.0/drives/{folder_id.split('!', 1)[0]}/items/{folder_id}?$select=id,@content.downloadUrl&ump=1&authKey={authkey}",
                headers=headers,
                data=data,
            ).json()
        except Exception as e:
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__}"
            ) from e
    if "@content.downloadUrl" not in resp:
        raise DirectDownloadLinkException("ERROR: Direct link not found")
    return resp["@content.downloadUrl"]


def pixeldrain(url):
    try:
        url = url.rstrip("/")
        code = url.split("/")[-1].split("?", 1)[0]
        response = get("https://pd.cybar.xyz/", allow_redirects=True)
        return response.url + code
    except Exception as e:
        raise DirectDownloadLinkException("ERROR: Direct link not found")


def streamtape(url, user_id=None):
    """
    Generate direct download link using hybrid approach:
    1. Primary: HTML scraping (faster, no credentials needed)
    2. Fallback: Official API (requires credentials but more reliable)
    """
    # Primary method: HTML scraping
    try:
        return _streamtape_html_scraping(url)
    except DirectDownloadLinkException as e:
        # If HTML scraping fails, try API fallback
        try:
            return _streamtape_api_fallback(url, user_id)
        except DirectDownloadLinkException as api_error:
            # If both methods fail, raise the original HTML scraping error
            # since it's the primary method
            raise e from api_error


def _streamtape_html_scraping(url):
    """
    Primary method: Extract download link using HTML scraping
    Fast and doesn't require API credentials
    """
    splitted_url = url.split("/")
    _id = splitted_url[4] if len(splitted_url) >= 6 else splitted_url[-1]
    try:
        html = HTML(get(url).text)
    except Exception as e:
        raise DirectDownloadLinkException(f"ERROR: {e.__class__.__name__}") from e
    script = html.xpath(
        "//script[contains(text(),'ideoooolink')]/text()"
    ) or html.xpath("//script[contains(text(),'ideoolink')]/text()")
    if not script:
        raise DirectDownloadLinkException("ERROR: Required script not found")
    if not (link := findall(r"(&expires\S+)'", script[0])):
        raise DirectDownloadLinkException("ERROR: Download link not found")
    return f"https://streamtape.com/get_video?id={_id}{link[-1]}"


def _get_streamtape_credentials(user_id=None):
    """
    Get Streamtape credentials with user priority over owner settings.
    Returns tuple: (api_username, api_password)
    """
    from bot.core.config_manager import Config
    from bot import user_data

    # Get user settings with fallback to owner settings
    user_dict = user_data.get(user_id, {}) if user_id else {}

    def get_streamtape_setting(user_key, owner_attr, default_value=""):
        user_value = user_dict.get(user_key)
        if user_value is not None:
            return user_value
        return getattr(Config, owner_attr, default_value)

    # Get Streamtape credentials with user priority
    api_username = get_streamtape_setting(
        "STREAMTAPE_API_USERNAME", "STREAMTAPE_API_USERNAME", ""
    )
    api_password = get_streamtape_setting(
        "STREAMTAPE_API_PASSWORD", "STREAMTAPE_API_PASSWORD", ""
    )

    return api_username, api_password


def _streamtape_api_fallback(url, user_id=None):
    """
    Fallback method: Use official Streamtape API
    More reliable but requires API credentials
    Respects user credentials over owner credentials
    """
    # Extract file ID from URL
    file_id = _extract_streamtape_file_id(url)
    if not file_id:
        raise DirectDownloadLinkException("ERROR: Invalid Streamtape URL format")

    # Get API credentials with user priority
    api_username, api_password = _get_streamtape_credentials(user_id)

    if not api_username or not api_password:
        raise DirectDownloadLinkException(
            "ERROR: Streamtape API credentials not configured. "
            "Please set STREAMTAPE_API_USERNAME and STREAMTAPE_API_PASSWORD for fallback support"
        )

    try:
        # Step 1: Get download ticket
        ticket_url = f"https://api.streamtape.com/file/dlticket?file={file_id}&login={api_username}&key={api_password}"
        ticket_response = get(ticket_url, timeout=10)
        ticket_response.raise_for_status()
        ticket_data = ticket_response.json()

        if ticket_data.get("status") != 200:
            error_msg = ticket_data.get("msg", "Unknown error")
            raise DirectDownloadLinkException(
                f"ERROR: API fallback failed - {error_msg}"
            )

        ticket = ticket_data["result"]["ticket"]
        wait_time = ticket_data["result"].get("wait_time", 0)

        # Step 2: Wait if required by API
        if wait_time > 0:
            from time import sleep

            sleep(wait_time)

        # Step 3: Get download link
        download_url = (
            f"https://api.streamtape.com/file/dl?file={file_id}&ticket={ticket}"
        )
        download_response = get(download_url, timeout=10)
        download_response.raise_for_status()
        download_data = download_response.json()

        if download_data.get("status") != 200:
            error_msg = download_data.get("msg", "Unknown error")
            raise DirectDownloadLinkException(
                f"ERROR: API fallback failed - {error_msg}"
            )

        direct_link = download_data["result"]["url"]
        if not direct_link:
            raise DirectDownloadLinkException(
                "ERROR: Empty download URL from API fallback"
            )

        return direct_link

    except Exception as e:
        if isinstance(e, DirectDownloadLinkException):
            raise
        raise DirectDownloadLinkException(
            f"ERROR: API fallback failed - {e.__class__.__name__}: {str(e)}"
        ) from e


def _extract_streamtape_file_id(url):
    """
    Extract file ID from various Streamtape URL formats
    Supports: streamtape.com/v/ID, streamtape.com/e/ID, etc.
    """
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        path_parts = parsed.path.strip("/").split("/")

        # Handle different URL formats:
        # https://streamtape.com/v/file_id
        # https://streamtape.com/e/file_id
        # https://streamtape.com/get_video?id=file_id
        if len(path_parts) >= 2 and path_parts[0] in ["v", "e"]:
            # Extract file ID, handle cases with filename: /v/file_id/filename.mp4
            file_id = path_parts[1]
            # Remove any filename extension if present
            if "." in file_id:
                file_id = file_id.split(".")[0]
            return file_id
        elif parsed.path == "/get_video" and "id" in parsed.query:
            from urllib.parse import parse_qs

            query_params = parse_qs(parsed.query)
            return query_params.get("id", [None])[0]
        elif len(path_parts) >= 1:
            # Fallback: try last path component, clean it up
            file_id = path_parts[-1]
            # Remove any filename extension if present
            if "." in file_id:
                file_id = file_id.split(".")[0]
            return file_id

    except Exception:
        pass

    return None


def racaty(url):
    with create_scraper() as session:
        try:
            url = session.get(url).url
            json_data = {"op": "download2", "id": url.split("/")[-1]}
            html = HTML(session.post(url, data=json_data).text)
        except Exception as e:
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__}"
            ) from e
    if direct_link := html.xpath("//a[@id='uniqueExpirylink']/@href"):
        return direct_link[0]
    else:
        raise DirectDownloadLinkException("ERROR: Direct link not found")


def fichier(link):
    """1Fichier direct link generator
    Based on https://github.com/Maujar
    """
    regex = r"^([http:\/\/|https:\/\/]+)?.*1fichier\.com\/\?.+"
    gan = match(regex, link)
    if not gan:
        raise DirectDownloadLinkException("ERROR: The link you entered is wrong!")
    if "::" in link:
        pswd = link.split("::")[-1]
        url = link.split("::")[-2]
    else:
        pswd = None
        url = link
    cget = create_scraper().request
    try:
        if pswd is None:
            req = cget("post", url)
        else:
            pw = {"pass": pswd}
            req = cget("post", url, data=pw)
    except Exception as e:
        raise DirectDownloadLinkException(f"ERROR: {e.__class__.__name__}") from e
    if req.status_code == 404:
        raise DirectDownloadLinkException(
            "ERROR: File not found/The link you entered is wrong!"
        )
    html = HTML(req.text)
    if dl_url := html.xpath('//a[@class="ok btn-general btn-orange"]/@href'):
        return dl_url[0]
    if not (ct_warn := html.xpath('//div[@class="ct_warn"]')):
        raise DirectDownloadLinkException(
            "ERROR: Error trying to generate Direct Link from 1fichier!"
        )
    if len(ct_warn) == 3:
        str_2 = ct_warn[-1].text
        if "you must wait" in str_2.lower():
            if numbers := [int(word) for word in str_2.split() if word.isdigit()]:
                raise DirectDownloadLinkException(
                    f"ERROR: 1fichier is on a limit. Please wait {numbers[0]} minute."
                )
            else:
                raise DirectDownloadLinkException(
                    "ERROR: 1fichier is on a limit. Please wait a few minutes/hour."
                )
        elif "protect access" in str_2.lower():
            raise DirectDownloadLinkException(
                f"ERROR:\n{PASSWORD_ERROR_MESSAGE.format(link)}"
            )
        else:
            raise DirectDownloadLinkException(
                "ERROR: Failed to generate Direct Link from 1fichier!"
            )
    elif len(ct_warn) == 4:
        str_1 = ct_warn[-2].text
        str_3 = ct_warn[-1].text
        if "you must wait" in str_1.lower():
            if numbers := [int(word) for word in str_1.split() if word.isdigit()]:
                raise DirectDownloadLinkException(
                    f"ERROR: 1fichier is on a limit. Please wait {numbers[0]} minute."
                )
            else:
                raise DirectDownloadLinkException(
                    "ERROR: 1fichier is on a limit. Please wait a few minutes/hour."
                )
        elif "bad password" in str_3.lower():
            raise DirectDownloadLinkException(
                "ERROR: The password you entered is wrong!"
            )
    raise DirectDownloadLinkException(
        "ERROR: Error trying to generate Direct Link from 1fichier!"
    )


def solidfiles(url):
    """Solidfiles direct link generator
    Based on https://github.com/Xonshiz/SolidFiles-Downloader
    By https://github.com/Jusidama18"""
    with create_scraper() as session:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1985.125 Safari/537.36"
            }
            pageSource = session.get(url, headers=headers).text
            mainOptions = str(
                search(r"viewerOptions\'\,\ (.*?)\)\;", pageSource).group(1)
            )
            return loads(mainOptions)["downloadUrl"]
        except Exception as e:
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__}"
            ) from e


def krakenfiles(url):
    with Session() as session:
        try:
            _res = session.get(url)
        except Exception as e:
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__}"
            ) from e
        html = HTML(_res.text)
        if post_url := html.xpath('//form[@id="dl-form"]/@action'):
            post_url = f"https://krakenfiles.com{post_url[0]}"
        else:
            raise DirectDownloadLinkException("ERROR: Unable to find post link.")
        if token := html.xpath('//input[@id="dl-token"]/@value'):
            data = {"token": token[0]}
        else:
            raise DirectDownloadLinkException(
                "ERROR: Unable to find token for post."
            )
        try:
            _json = session.post(post_url, data=data).json()
        except Exception as e:
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__} While send post request"
            ) from e
    if _json["status"] != "ok":
        raise DirectDownloadLinkException(
            "ERROR: Unable to find download after post request"
        )
    return _json["url"]


def uploadee(url):
    with create_scraper() as session:
        try:
            html = HTML(session.get(url).text)
        except Exception as e:
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__}"
            ) from e
    if link := html.xpath("//a[@id='d_l']/@href"):
        return link[0]
    else:
        raise DirectDownloadLinkException("ERROR: Direct Link not found")


def terabox(url):
    if "/file/" in url:
        return url
    # Use configurable TERABOX_PROXY instead of hardcoded URL
    proxy_base = Config.TERABOX_PROXY.rstrip("/")
    api_url = f"{proxy_base}/api?url={quote(url)}"
    try:
        with Session() as session:
            req = session.get(api_url, headers={"User-Agent": user_agent}).json()
    except Exception as e:
        raise DirectDownloadLinkException(f"ERROR: {e.__class__.__name__}") from e

    details = {"contents": [], "title": "", "total_size": 0}
    if "✅ Status" in req:
        for data in req["📜 Extracted Info"]:
            item = {
                "path": "",
                "filename": data["📂 Title"],
                "url": data["🔽 Direct Download Link"],
            }
            details["contents"].append(item)
            size = (data["📏 Size"]).replace(" ", "")
            size = speed_string_to_bytes(size)
            details["total_size"] += size
        details["title"] = req["📜 Extracted Info"][0]["📂 Title"]
        if len(details["contents"]) == 1:
            return details["contents"][0]["url"]
        return details
    else:
        raise DirectDownloadLinkException("ERROR: File not found!")


def filepress(url):
    try:
        url = get(f"https://filebee.xyz/file/{url.split('/')[-1]}").url
        raw = urlparse(url)
        json_data = {
            "id": raw.path.split("/")[-1],
            "method": "publicDownlaod",
        }
        api = f"{raw.scheme}://{raw.hostname}/api/file/downlaod/"
        res2 = post(
            api,
            headers={"Referer": f"{raw.scheme}://{raw.hostname}"},
            json=json_data,
        ).json()
        json_data2 = {
            "id": res2["data"],
            "method": "publicDownlaod",
        }
        api2 = f"{raw.scheme}://{raw.hostname}/api/file/downlaod2/"
        res = post(
            api2,
            headers={"Referer": f"{raw.scheme}://{raw.hostname}"},
            json=json_data2,
        ).json()
    except Exception as e:
        raise DirectDownloadLinkException(f"ERROR: {e.__class__.__name__}") from e

    if "data" not in res:
        raise DirectDownloadLinkException(f"ERROR: {res['statusText']}")
    return f"https://drive.google.com/uc?id={res['data']}&export=download"


def sharer_scraper(url):
    cget = create_scraper().request
    try:
        url = cget("GET", url).url
        raw = urlparse(url)
        header = {
            "useragent": "Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US) AppleWebKit/534.10 (KHTML, like Gecko) Chrome/7.0.548.0 Safari/534.10"
        }
        res = cget("GET", url, headers=header)
    except Exception as e:
        raise DirectDownloadLinkException(f"ERROR: {e.__class__.__name__}") from e
    key = findall(r'"key",\s+"(.*?)"', res.text)
    if not key:
        raise DirectDownloadLinkException("ERROR: Key not found!")
    key = key[0]
    if not HTML(res.text).xpath("//button[@id='drc']"):
        raise DirectDownloadLinkException(
            "ERROR: This link don't have direct download button"
        )
    boundary = uuid4()
    headers = {
        "Content-Type": f"multipart/form-data; boundary=----WebKitFormBoundary{boundary}",
        "x-token": raw.hostname,
        "useragent": "Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US) AppleWebKit/534.10 (KHTML, like Gecko) Chrome/7.0.548.0 Safari/534.10",
    }

    data = (
        f'------WebKitFormBoundary{boundary}\r\nContent-Disposition: form-data; name="action"\r\n\r\ndirect\r\n'
        f'------WebKitFormBoundary{boundary}\r\nContent-Disposition: form-data; name="key"\r\n\r\n{key}\r\n'
        f'------WebKitFormBoundary{boundary}\r\nContent-Disposition: form-data; name="action_token"\r\n\r\n\r\n'
        f"------WebKitFormBoundary{boundary}--\r\n"
    )
    try:
        res = cget(
            "POST", url, cookies=res.cookies, headers=headers, data=data
        ).json()
    except Exception as e:
        raise DirectDownloadLinkException(f"ERROR: {e.__class__.__name__}") from e
    if "url" not in res:
        raise DirectDownloadLinkException(
            "ERROR: Drive Link not found, Try in your broswer"
        )
    if (
        "drive.google.com" in res["url"]
        or "drive.usercontent.google.com" in res["url"]
    ):
        return res["url"]
    try:
        res = cget("GET", res["url"])
    except Exception as e:
        raise DirectDownloadLinkException(f"ERROR: {e.__class__.__name__}") from e
    if (
        drive_link := HTML(res.text).xpath("//a[contains(@class,'btn')]/@href")
    ) and (
        "drive.google.com" in drive_link[0]
        or "drive.usercontent.google.com" in drive_link[0]
    ):
        return drive_link[0]
    else:
        raise DirectDownloadLinkException(
            "ERROR: Drive Link not found, Try in your broswer"
        )


def wetransfer(url):
    with create_scraper() as session:
        try:
            url = session.get(url).url
            splited_url = url.split("/")
            json_data = {
                "security_hash": splited_url[-1],
                "intent": "entire_transfer",
            }
            res = session.post(
                f"https://wetransfer.com/api/v4/transfers/{splited_url[-2]}/download",
                json=json_data,
            ).json()
        except Exception as e:
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__}"
            ) from e
    if "direct_link" in res:
        return res["direct_link"]
    elif "message" in res:
        raise DirectDownloadLinkException(f"ERROR: {res['message']}")
    elif "error" in res:
        raise DirectDownloadLinkException(f"ERROR: {res['error']}")
    else:
        raise DirectDownloadLinkException("ERROR: cannot find direct link")


def shrdsk(url):
    with create_scraper() as session:
        try:
            _json = session.get(
                f"https://us-central1-affiliate2apk.cloudfunctions.net/get_data?shortid={url.split('/')[-1]}",
            ).json()
        except Exception as e:
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__}"
            ) from e
        if "download_data" not in _json:
            raise DirectDownloadLinkException("ERROR: Download data not found")
        try:
            _res = session.get(
                f"https://shrdsk.me/download/{_json['download_data']}",
                allow_redirects=False,
            )
            if "Location" in _res.headers:
                return _res.headers["Location"]
        except Exception as e:
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__}"
            ) from e
    raise DirectDownloadLinkException("ERROR: cannot find direct link in headers")


def linkBox(url: str):
    parsed_url = urlparse(url)
    try:
        shareToken = parsed_url.path.split("/")[-1]
    except:
        raise DirectDownloadLinkException("ERROR: invalid URL")

    details = {"contents": [], "title": "", "total_size": 0}

    def __singleItem(session, itemId):
        try:
            _json = session.get(
                "https://www.linkbox.to/api/file/detail",
                params={"itemId": itemId},
            ).json()
        except Exception as e:
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__}"
            ) from e
        data = _json["data"]
        if not data:
            if "msg" in _json:
                raise DirectDownloadLinkException(f"ERROR: {_json['msg']}")
            raise DirectDownloadLinkException("ERROR: data not found")
        itemInfo = data["itemInfo"]
        if not itemInfo:
            raise DirectDownloadLinkException("ERROR: itemInfo not found")
        filename = itemInfo["name"]
        sub_type = itemInfo.get("sub_type")
        if sub_type and not filename.strip().endswith(sub_type):
            filename += f".{sub_type}"
        if not details["title"]:
            details["title"] = filename
        item = {
            "path": "",
            "filename": filename,
            "url": itemInfo["url"],
        }
        if "size" in itemInfo:
            size = itemInfo["size"]
            if isinstance(size, str) and size.isdigit():
                size = float(size)
            details["total_size"] += size
        details["contents"].append(item)

    def __fetch_links(session, _id=0, folderPath=""):
        params = {
            "shareToken": shareToken,
            "pageSize": 1000,
            "pid": _id,
        }
        try:
            _json = session.get(
                "https://www.linkbox.to/api/file/share_out_list",
                params=params,
            ).json()
        except Exception as e:
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__}"
            ) from e
        data = _json["data"]
        if not data:
            if "msg" in _json:
                raise DirectDownloadLinkException(f"ERROR: {_json['msg']}")
            raise DirectDownloadLinkException("ERROR: data not found")
        try:
            if data["shareType"] == "singleItem":
                return __singleItem(session, data["itemId"])
        except:
            pass
        if not details["title"]:
            details["title"] = data["dirName"]
        contents = data["list"]
        if not contents:
            return None
        for content in contents:
            if content["type"] == "dir" and "url" not in content:
                if not folderPath:
                    newFolderPath = ospath.join(details["title"], content["name"])
                else:
                    newFolderPath = ospath.join(folderPath, content["name"])
                if not details["title"]:
                    details["title"] = content["name"]
                __fetch_links(session, content["id"], newFolderPath)
            elif "url" in content:
                if not folderPath:
                    folderPath = details["title"]
                filename = content["name"]
                if (
                    sub_type := content.get("sub_type")
                ) and not filename.strip().endswith(sub_type):
                    filename += f".{sub_type}"
                item = {
                    "path": ospath.join(folderPath),
                    "filename": filename,
                    "url": content["url"],
                }
                if "size" in content:
                    size = content["size"]
                    if isinstance(size, str) and size.isdigit():
                        size = float(size)
                    details["total_size"] += size
                details["contents"].append(item)

    try:
        with Session() as session:
            __fetch_links(session)
    except DirectDownloadLinkException as e:
        raise e
    return details


def _get_gofile_credentials(user_id=None):
    """
    Get Gofile credentials with user priority over owner settings.
    Returns tuple: (api_key, folder_name)
    """
    from bot.core.config_manager import Config
    from bot import user_data

    # Get user settings with fallback to owner settings
    user_dict = user_data.get(user_id, {}) if user_id else {}

    def get_gofile_setting(user_key, owner_attr, default_value=""):
        user_value = user_dict.get(user_key)
        if user_value is not None:
            return user_value
        return getattr(Config, owner_attr, default_value)

    # Get Gofile credentials with user priority
    api_key = get_gofile_setting("GOFILE_API_KEY", "GOFILE_API_KEY", "")
    folder_name = get_gofile_setting("GOFILE_FOLDER_NAME", "GOFILE_FOLDER_NAME", "")

    return api_key, folder_name


def gofile(url, user_id=None):
    """
    Enhanced Gofile download with API fallback and credential management.
    Supports both guest accounts and authenticated API access.
    """
    try:
        if "::" in url:
            _password = url.split("::")[-1]
            _password = sha256(_password.encode("utf-8")).hexdigest()
            url = url.split("::")[-2]
        else:
            _password = ""
        _id = url.split("/")[-1]
    except Exception as e:
        raise DirectDownloadLinkException(f"ERROR: {e.__class__.__name__}")

    # Get user credentials for potential API fallback
    api_key, _ = _get_gofile_credentials(user_id)

    def __get_guest_token(session):
        """Get guest token (original method)"""
        headers = {
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "*/*",
            "Connection": "keep-alive",
        }
        __url = "https://api.gofile.io/accounts"
        try:
            __res = session.post(__url, headers=headers).json()
            if __res["status"] != "ok":
                raise DirectDownloadLinkException(
                    "ERROR: Failed to get guest token."
                )
            return __res["data"]["token"], False  # False = guest token
        except Exception as e:
            raise e

    def __get_authenticated_token(session, api_key):
        """Get authenticated token using API key"""
        headers = {
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "*/*",
            "Connection": "keep-alive",
            "Authorization": f"Bearer {api_key}",
        }
        __url = "https://api.gofile.io/accounts/getid"
        try:
            __res = session.get(__url, headers=headers).json()
            if __res["status"] != "ok":
                raise Exception("Invalid API key or account access failed")
            return api_key, True  # True = authenticated token
        except Exception as e:
            raise e

    def __fetch_links(
        session, _id, folderPath="", token=None, is_authenticated=False
    ):
        """Fetch links with enhanced error handling and fallback support"""
        _url = f"https://api.gofile.io/contents/{_id}?wt=4fd6sg89d7s6&cache=true"
        headers = {
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "*/*",
            "Connection": "keep-alive",
            "Authorization": f"Bearer {token}",
        }
        if _password:
            _url += f"&password={_password}"
        try:
            _json = session.get(_url, headers=headers).json()
        except Exception as e:
            raise DirectDownloadLinkException(f"ERROR: {e.__class__.__name__}")

        # Enhanced error handling
        if _json["status"] in "error-passwordRequired":
            raise DirectDownloadLinkException(
                f"ERROR:\n{PASSWORD_ERROR_MESSAGE.format(url)}",
            )
        if _json["status"] in "error-passwordWrong":
            raise DirectDownloadLinkException("ERROR: This password is wrong !")
        if _json["status"] in "error-notFound":
            raise DirectDownloadLinkException(
                "ERROR: File not found on gofile's server",
            )
        if _json["status"] in "error-notPublic":
            if is_authenticated:
                # With authenticated access, we might still be able to access private content
                pass  # Continue processing
            else:
                raise DirectDownloadLinkException("ERROR: This folder is not public")

        data = _json["data"]

        if not details["title"]:
            details["title"] = data["name"] if data["type"] == "folder" else _id

        contents = data["children"]
        for content in contents.values():
            if content["type"] == "folder":
                # With authenticated access, we can access more folders
                if not content["public"] and not is_authenticated:
                    continue
                if not folderPath:
                    newFolderPath = ospath.join(details["title"], content["name"])
                else:
                    newFolderPath = ospath.join(folderPath, content["name"])
                __fetch_links(
                    session, content["id"], newFolderPath, token, is_authenticated
                )
            else:
                if not folderPath:
                    folderPath = details["title"]
                item = {
                    "path": ospath.join(folderPath),
                    "filename": content["name"],
                    "url": content["link"],
                }
                if "size" in content:
                    size = content["size"]
                    if isinstance(size, str) and size.isdigit():
                        size = float(size)
                    details["total_size"] += size
                details["contents"].append(item)

    details = {"contents": [], "title": "", "total_size": 0}

    # Try authenticated access first if API key is available
    token = None
    is_authenticated = False

    with Session() as session:
        if api_key:
            try:
                token, is_authenticated = __get_authenticated_token(session, api_key)
                details["auth_method"] = "authenticated"
            except Exception as auth_error:
                # Log the authentication failure but continue with guest access
                try:
                    token, is_authenticated = __get_guest_token(session)
                    details["auth_method"] = "guest_fallback"
                except Exception as guest_error:
                    raise DirectDownloadLinkException(
                        f"ERROR: Both authenticated and guest access failed. Auth: {auth_error}, Guest: {guest_error}"
                    )
        else:
            try:
                token, is_authenticated = __get_guest_token(session)
                details["auth_method"] = "guest"
            except Exception as e:
                raise DirectDownloadLinkException(
                    f"ERROR: Failed to get access token: {e}"
                )

        details["header"] = f"Cookie: accountToken={token}"

        try:
            __fetch_links(
                session, _id, token=token, is_authenticated=is_authenticated
            )
        except Exception as e:
            # If authenticated access fails, try guest access as fallback
            if is_authenticated and api_key:
                try:
                    token, is_authenticated = __get_guest_token(session)
                    details["header"] = f"Cookie: accountToken={token}"
                    details["auth_method"] = "guest_fallback_after_auth_failure"
                    __fetch_links(
                        session, _id, token=token, is_authenticated=is_authenticated
                    )
                except Exception as fallback_error:
                    raise DirectDownloadLinkException(
                        f"ERROR: Both authenticated and guest access failed: {e}, Fallback: {fallback_error}"
                    )
            else:
                raise DirectDownloadLinkException(e)

    if len(details["contents"]) == 1:
        return (details["contents"][0]["url"], details["header"])
    return details


def cf_bypass(url):
    "DO NOT ABUSE THIS"
    try:
        data = {"cmd": "request.get", "url": url, "maxTimeout": 60000}
        _json = post(
            "https://cf.jmdkh.eu.org/v1",
            headers={"Content-Type": "application/json"},
            json=data,
        ).json()
        if _json["status"] == "ok":
            return _json["solution"]["response"]
    except Exception as e:
        e
    raise DirectDownloadLinkException("ERROR: Con't bypass cloudflare")


def send_cm_file(url, file_id=None):
    if "::" in url:
        _password = url.split("::")[-1]
        url = url.split("::")[-2]
    else:
        _password = ""
    _passwordNeed = False
    with create_scraper() as session:
        if file_id is None:
            try:
                html = HTML(session.get(url).text)
            except Exception as e:
                raise DirectDownloadLinkException(
                    f"ERROR: {e.__class__.__name__}"
                ) from e
            if html.xpath("//input[@name='password']"):
                _passwordNeed = True
            if not (file_id := html.xpath("//input[@name='id']/@value")):
                raise DirectDownloadLinkException("ERROR: file_id not found")
        try:
            data = {"op": "download2", "id": file_id}
            if _password and _passwordNeed:
                data["password"] = _password
            _res = session.post("https://send.cm/", data=data, allow_redirects=False)
            if "Location" in _res.headers:
                return (_res.headers["Location"], ["Referer: https://send.cm/"])
        except Exception as e:
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__}"
            ) from e
        if _passwordNeed:
            raise DirectDownloadLinkException(
                f"ERROR:\n{PASSWORD_ERROR_MESSAGE.format(url)}"
            )
        raise DirectDownloadLinkException("ERROR: Direct link not found")


def send_cm(url):
    if "/d/" in url:
        return send_cm_file(url)
    elif "/s/" not in url:
        file_id = url.split("/")[-1]
        return send_cm_file(url, file_id)
    splitted_url = url.split("/")
    details = {
        "contents": [],
        "title": "",
        "total_size": 0,
        "header": "Referer: https://send.cm/",
    }
    if len(splitted_url) == 5:
        url += "/"
        splitted_url = url.split("/")
    if len(splitted_url) >= 7:
        details["title"] = splitted_url[5]
    else:
        details["title"] = splitted_url[-1]
    session = Session()

    def __collectFolders(html):
        folders = []
        folders_urls = html.xpath("//h6/a/@href")
        folders_names = html.xpath("//h6/a/text()")
        for folders_url, folders_name in zip(folders_urls, folders_names):
            folders.append(
                {
                    "folder_link": folders_url.strip(),
                    "folder_name": folders_name.strip(),
                }
            )
        return folders

    def __getFile_link(file_id):
        try:
            _res = session.post(
                "https://send.cm/",
                data={"op": "download2", "id": file_id},
                allow_redirects=False,
            )
            if "Location" in _res.headers:
                return _res.headers["Location"]
        except:
            pass

    def __getFiles(html):
        files = []
        hrefs = html.xpath('//tr[@class="selectable"]//a/@href')
        file_names = html.xpath('//tr[@class="selectable"]//a/text()')
        sizes = html.xpath('//tr[@class="selectable"]//span/text()')
        for href, file_name, size_text in zip(hrefs, file_names, sizes):
            files.append(
                {
                    "file_id": href.split("/")[-1],
                    "file_name": file_name.strip(),
                    "size": speed_string_to_bytes(size_text.strip()),
                }
            )
        return files

    def __writeContents(html_text, folderPath=""):
        folders = __collectFolders(html_text)
        for folder in folders:
            _html = HTML(cf_bypass(folder["folder_link"]))
            __writeContents(_html, ospath.join(folderPath, folder["folder_name"]))
        files = __getFiles(html_text)
        for file in files:
            if not (link := __getFile_link(file["file_id"])):
                continue
            item = {"url": link, "filename": file["filename"], "path": folderPath}
            details["total_size"] += file["size"]
            details["contents"].append(item)

    try:
        mainHtml = HTML(cf_bypass(url))
    except DirectDownloadLinkException as e:
        raise e
    except Exception as e:
        raise DirectDownloadLinkException(
            f"ERROR: {e.__class__.__name__} While getting mainHtml"
        )

    try:
        __writeContents(mainHtml, details["title"])
    except DirectDownloadLinkException as e:
        raise e
    except Exception as e:
        raise DirectDownloadLinkException(
            f"ERROR: {e.__class__.__name__} While writing Contents"
        )
    finally:
        session.close()
    if len(details["contents"]) == 1:
        return (details["contents"][0]["url"], [details["header"]])
    return details


def doods(url):
    if "/e/" in url:
        url = url.replace("/e/", "/d/")
    parsed_url = urlparse(url)
    with create_scraper() as session:
        try:
            html = HTML(session.get(url).text)
        except Exception as e:
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__} While fetching token link"
            ) from e
        if not (link := html.xpath("//div[@class='download-content']//a/@href")):
            raise DirectDownloadLinkException(
                "ERROR: Token Link not found or maybe not allow to download! open in browser."
            )
        link = f"{parsed_url.scheme}://{parsed_url.hostname}{link[0]}"
        sleep(2)
        try:
            _res = session.get(link)
        except Exception as e:
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__} While fetching download link"
            ) from e
    if not (link := search(r"window\.open\('(\S+)'", _res.text)):
        raise DirectDownloadLinkException("ERROR: Download link not found try again")
    return (
        link.group(1),
        [f"Referer: {parsed_url.scheme}://{parsed_url.hostname}/"],
    )


def easyupload(url):
    if "::" in url:
        _password = url.split("::")[-1]
        url = url.split("::")[-2]
    else:
        _password = ""
    file_id = url.split("/")[-1]
    with create_scraper() as session:
        try:
            _res = session.get(url)
        except Exception as e:
            raise DirectDownloadLinkException(f"ERROR: {e.__class__.__name__}")
        first_page_html = HTML(_res.text)
        if (
            first_page_html.xpath("//h6[contains(text(),'Password Protected')]")
            and not _password
        ):
            raise DirectDownloadLinkException(
                f"ERROR:\n{PASSWORD_ERROR_MESSAGE.format(url)}"
            )
        if not (
            match := search(
                r"https://eu(?:[1-9][0-9]?|100)\.easyupload\.io/action\.php",
                _res.text,
            )
        ):
            raise DirectDownloadLinkException(
                "ERROR: Failed to get server for EasyUpload Link"
            )
        action_url = match.group()
        session.headers.update({"referer": "https://easyupload.io/"})
        recaptcha_params = {
            "k": "6LfWajMdAAAAAGLXz_nxz2tHnuqa-abQqC97DIZ3",
            "ar": "1",
            "co": "aHR0cHM6Ly9lYXN5dXBsb2FkLmlvOjQ0Mw..",
            "hl": "en",
            "v": "0hCdE87LyjzAkFO5Ff-v7Hj1",
            "size": "invisible",
            "cb": "c3o1vbaxbmwe",
        }
        if not (captcha_token := get_captcha_token(session, recaptcha_params)):
            raise DirectDownloadLinkException("ERROR: Captcha token not found")
        try:
            data = {
                "type": "download-token",
                "url": file_id,
                "value": _password,
                "captchatoken": captcha_token,
                "method": "regular",
            }
            json_resp = session.post(url=action_url, data=data).json()
        except Exception as e:
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__}"
            ) from e
    if "download_link" in json_resp:
        return json_resp["download_link"]
    elif "data" in json_resp:
        raise DirectDownloadLinkException(
            f"ERROR: Failed to generate direct link due to {json_resp['data']}"
        )
    raise DirectDownloadLinkException(
        "ERROR: Failed to generate direct link from EasyUpload."
    )


def filelions_and_streamwish(url):
    parsed_url = urlparse(url)
    hostname = parsed_url.hostname
    scheme = parsed_url.scheme
    if any(
        x in hostname
        for x in [
            "filelions.co",
            "filelions.live",
            "filelions.to",
            "filelions.site",
            "cabecabean.lol",
            "filelions.online",
            "mycloudz.cc",
        ]
    ):
        apiKey = Config.FILELION_API
        apiUrl = "https://vidhideapi.com"
    elif any(
        x in hostname
        for x in [
            "embedwish.com",
            "kissmovies.net",
            "kitabmarkaz.xyz",
            "wishfast.top",
            "streamwish.to",
        ]
    ):
        apiKey = Config.STREAMWISH_API
        apiUrl = "https://api.streamwish.com"
    if not apiKey:
        raise DirectDownloadLinkException(
            f"ERROR: API is not provided get it from {scheme}://{hostname}"
        )
    file_code = url.split("/")[-1]
    quality = ""
    if bool(file_code.strip().endswith(("_o", "_h", "_n", "_l"))):
        spited_file_code = file_code.rsplit("_", 1)
        quality = spited_file_code[1]
        file_code = spited_file_code[0]
    url = f"{scheme}://{hostname}/{file_code}"
    try:
        _res = get(
            f"{apiUrl}/api/file/direct_link",
            params={"key": apiKey, "file_code": file_code, "hls": "1"},
        ).json()
    except Exception as e:
        raise DirectDownloadLinkException(f"ERROR: {e.__class__.__name__}") from e
    if _res["status"] != 200:
        raise DirectDownloadLinkException(f"ERROR: {_res['msg']}")
    result = _res["result"]
    if not result["versions"]:
        raise DirectDownloadLinkException("ERROR: File Not Found")
    error = "\nProvide a quality to download the video\nAvailable Quality:"
    for version in result["versions"]:
        if quality == version["name"]:
            return version["url"]
        elif version["name"] == "l":
            error += "\nLow"
        elif version["name"] == "n":
            error += "\nNormal"
        elif version["name"] == "o":
            error += "\nOriginal"
        elif version["name"] == "h":
            error += "\nHD"
        error += f" <code>{url}_{version['name']}</code>"
    raise DirectDownloadLinkException(f"ERROR: {error}")


def streamvid(url: str):
    file_code = url.split("/")[-1]
    parsed_url = urlparse(url)
    url = f"{parsed_url.scheme}://{parsed_url.hostname}/d/{file_code}"
    quality_defined = bool(url.strip().endswith(("_o", "_h", "_n", "_l")))
    with create_scraper() as session:
        try:
            html = HTML(session.get(url).text)
        except Exception as e:
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__}"
            ) from e
        if quality_defined:
            data = {}
            if not (inputs := html.xpath('//form[@id="F1"]//input')):
                raise DirectDownloadLinkException("ERROR: No inputs found")
            for i in inputs:
                if key := i.get("name"):
                    data[key] = i.get("value")
            try:
                html = HTML(session.post(url, data=data).text)
            except Exception as e:
                raise DirectDownloadLinkException(
                    f"ERROR: {e.__class__.__name__}"
                ) from e
            if not (
                script := html.xpath(
                    '//script[contains(text(),"document.location.href")]/text()'
                )
            ):
                if error := html.xpath(
                    '//div[@class="alert alert-danger"][1]/text()[2]'
                ):
                    raise DirectDownloadLinkException(f"ERROR: {error[0]}")
                raise DirectDownloadLinkException(
                    "ERROR: direct link script not found!"
                )
            if directLink := findall(r'document\.location\.href="(.*)"', script[0]):
                return directLink[0]
            raise DirectDownloadLinkException(
                "ERROR: direct link not found! in the script"
            )
        elif (qualities_urls := html.xpath('//div[@id="dl_versions"]/a/@href')) and (
            qualities := html.xpath('//div[@id="dl_versions"]/a/text()[2]')
        ):
            error = "\nProvide a quality to download the video\nAvailable Quality:"
            for quality_url, quality in zip(qualities_urls, qualities):
                error += f"\n{quality.strip()} <code>{quality_url}</code>"
            raise DirectDownloadLinkException(f"ERROR: {error}")
        elif error := html.xpath('//div[@class="not-found-text"]/text()'):
            raise DirectDownloadLinkException(f"ERROR: {error[0]}")
        raise DirectDownloadLinkException("ERROR: Something went wrong")


def streamhub(url):
    file_code = url.split("/")[-1]
    parsed_url = urlparse(url)
    url = f"{parsed_url.scheme}://{parsed_url.hostname}/d/{file_code}"
    with create_scraper() as session:
        try:
            html = HTML(session.get(url).text)
        except Exception as e:
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__}"
            ) from e
        if not (inputs := html.xpath('//form[@name="F1"]//input')):
            raise DirectDownloadLinkException("ERROR: No inputs found")
        data = {}
        for i in inputs:
            if key := i.get("name"):
                data[key] = i.get("value")
        session.headers.update({"referer": url})
        sleep(1)
        try:
            html = HTML(session.post(url, data=data).text)
        except Exception as e:
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__}"
            ) from e
        if directLink := html.xpath(
            '//a[@class="btn btn-primary btn-go downloadbtn"]/@href'
        ):
            return directLink[0]
        if error := html.xpath('//div[@class="alert alert-danger"]/text()[2]'):
            raise DirectDownloadLinkException(f"ERROR: {error[0]}")
        raise DirectDownloadLinkException("ERROR: direct link not found!")


def pcloud(url):
    with create_scraper() as session:
        try:
            res = session.get(url)
        except Exception as e:
            raise DirectDownloadLinkException(
                f"ERROR: {e.__class__.__name__}"
            ) from e
    if link := findall(r".downloadlink.:..(https:.*)..", res.text):
        return link[0].replace(r"\/", "/")
    raise DirectDownloadLinkException("ERROR: Direct link not found")


def tmpsend(url):
    parsed_url = urlparse(url)
    if any(x in parsed_url.path for x in ["thank-you", "download"]):
        query_params = parse_qs(parsed_url.query)
        if file_id := query_params.get("d"):
            file_id = file_id[0]
    elif not (file_id := parsed_url.path.strip("/")):
        raise DirectDownloadLinkException("ERROR: Invalid URL format")
    referer_url = f"https://tmpsend.com/thank-you?d={file_id}"
    header = [f"Referer: {referer_url}"]
    download_link = f"https://tmpsend.com/download?d={file_id}"
    return download_link, header


def qiwi(url):
    """qiwi.gg link generator
    based on https://github.com/aenulrofik"""
    file_id = url.split("/")[-1]
    try:
        res = get(url).text
    except Exception as e:
        raise DirectDownloadLinkException(f"ERROR: {e.__class__.__name__}") from e
    tree = HTML(res)
    if name := tree.xpath('//h1[@class="page_TextHeading__VsM7r"]/text()'):
        ext = name[0].split(".")[-1]
        return f"https://spyderrock.com/{file_id}.{ext}"
    else:
        raise DirectDownloadLinkException("ERROR: File not found")


def mp4upload(url):
    with Session() as session:
        try:
            url = url.replace("embed-", "")
            req = session.get(url).text
            tree = HTML(req)
            inputs = tree.xpath("//input")
            header = ["Referer: https://www.mp4upload.com/"]
            data = {input.get("name"): input.get("value") for input in inputs}
            if not data:
                raise DirectDownloadLinkException("ERROR: File Not Found!")
            post = session.post(
                url,
                data=data,
                headers={
                    "User-Agent": user_agent,
                    "Referer": "https://www.mp4upload.com/",
                },
            ).text
            tree = HTML(post)
            inputs = tree.xpath('//form[@name="F1"]//input')
            data = {
                input.get("name"): input.get("value").replace(" ", "")
                for input in inputs
            }
            if not data:
                raise DirectDownloadLinkException("ERROR: File Not Found!")
            data["referer"] = url
            direct_link = session.post(url, data=data).url
            return direct_link, header
        except:
            raise DirectDownloadLinkException("ERROR: File Not Found!")


def berkasdrive(url):
    """berkasdrive.com link generator
    by https://github.com/aenulrofik"""
    try:
        sesi = get(url).text
    except Exception as e:
        raise DirectDownloadLinkException(f"ERROR: {e.__class__.__name__}") from e
    html = HTML(sesi)
    if link := html.xpath("//script")[0].text.split('"')[1]:
        return b64decode(link).decode("utf-8")
    else:
        raise DirectDownloadLinkException("ERROR: File Not Found!")


def swisstransfer(link):
    matched_link = match(
        r"https://www\.swisstransfer\.com/d/([\w-]+)(?:\:\:(\w+))?", link
    )
    if not matched_link:
        raise DirectDownloadLinkException(
            f"ERROR: Invalid SwissTransfer link format {link}"
        )

    transfer_id, password = matched_link.groups()
    password = password or ""

    def encode_password(password):
        return (
            b64encode(password.encode("utf-8")).decode("utf-8") if password else ""
        )

    def getfile(transfer_id, password):
        url = f"https://www.swisstransfer.com/api/links/{transfer_id}"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Authorization": encode_password(password) if password else "",
            "Content-Type": "" if password else "application/json",
        }
        response = get(url, headers=headers)

        if response.status_code == 200:
            try:
                return response.json(), [
                    f"{k}: {v}" for k, v in headers.items() if v
                ]
            except ValueError:
                raise DirectDownloadLinkException(
                    f"ERROR: Error parsing JSON response {response.text}"
                )
        raise DirectDownloadLinkException(
            f"ERROR: Error fetching file details {response.status_code}, {response.text}"
        )

    def gettoken(password, containerUUID, fileUUID):
        url = "https://www.swisstransfer.com/api/generateDownloadToken"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
        }
        body = {
            "password": password,
            "containerUUID": containerUUID,
            "fileUUID": fileUUID,
        }

        response = post(url, headers=headers, json=body)

        if response.status_code == 200:
            return response.text.strip().replace('"', "")
        raise DirectDownloadLinkException(
            f"ERROR: Error generating download token {response.status_code}, {response.text}"
        )

    data, _ = getfile(transfer_id, password)
    if not data:
        return None

    try:
        container_uuid = data["data"]["containerUUID"]
        download_host = data["data"]["downloadHost"]
        files = data["data"]["container"]["files"]
        folder_name = data["data"]["container"]["message"] or "unknown"
    except (KeyError, IndexError, TypeError) as e:
        raise DirectDownloadLinkException(f"ERROR: Error parsing file details {e}")

    total_size = sum(file["fileSizeInBytes"] for file in files)

    if len(files) == 1:
        file = files[0]
        file_uuid = file["UUID"]
        token = gettoken(password, container_uuid, file_uuid)
        download_url = f"https://{download_host}/api/download/{transfer_id}/{file_uuid}?token={token}"
        return download_url, ["User-Agent:Mozilla/5.0"]

    contents = []
    for file in files:
        file_uuid = file["UUID"]
        file_name = file["fileName"]
        file_size = file["fileSizeInBytes"]

        token = gettoken(password, container_uuid, file_uuid)
        if not token:
            continue

        download_url = f"https://{download_host}/api/download/{transfer_id}/{file_uuid}?token={token}"
        contents.append({"filename": file_name, "path": "", "url": download_url})

    return {
        "contents": contents,
        "title": folder_name,
        "total_size": total_size,
        "header": "User-Agent:Mozilla/5.0",
    }


def instagram(link: str) -> str:
    """
    Fetches the direct video download URL from an Instagram post.

    Args:
        link (str): The Instagram post URL.

    Returns:
        str: The direct video URL.

    Raises:
        DirectDownloadLinkException: If any error occurs during the process.
    """
    if not Config.INSTADL_API:
        raise DirectDownloadLinkException(
            f"ERROR: Instagram downloader API not added, Try ytdl commands"
        )
    full_url = f"{Config.INSTADL_API}/api/video?postUrl={link}"

    try:
        response = get(full_url)
        response.raise_for_status()

        data = response.json()

        if (
            data.get("status") == "success"
            and "data" in data
            and "videoUrl" in data["data"]
        ):
            return data["data"]["videoUrl"]

        raise DirectDownloadLinkException("ERROR: Failed to retrieve video URL.")

    except Exception as e:
        raise DirectDownloadLinkException(f"ERROR: {e}")
