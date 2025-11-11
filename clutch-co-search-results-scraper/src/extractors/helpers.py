import json
import logging
import random
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

import requests

logger = logging.getLogger("helpers")

DEFAULT_SETTINGS: Dict[str, Any] = {
    "userAgent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/127.0.0.1 Safari/537.36"
    ),
    "timeoutSeconds": 20,
    "maxRetries": 3,
    "retryBackoffSeconds": 2,
    "maxPagesPerUrl": 1,
    "rateLimitSeconds": 0.0,
}

def load_settings(path: Path) -> Dict[str, Any]:
    """
    Load scraper settings from a JSON file, falling back to sane defaults.
    """
    merged = DEFAULT_SETTINGS.copy()

    if not path.exists():
        logger.warning(
            f"Settings file not found at {path}. Using default settings instead."
        )
        return merged

    try:
        with path.open("r", encoding="utf-8") as f:
            user_settings = json.load(f)
        if not isinstance(user_settings, dict):
            raise ValueError("Settings file must contain a JSON object.")
        merged.update(user_settings)
        logger.info(f"Loaded settings from {path}.")
    except Exception as exc:
        logger.exception(
            f"Failed to load settings from {path}. "
            f"Using default settings. Error: {exc}"
        )

    return merged

def _build_headers(settings: Dict[str, Any]) -> Dict[str, str]:
    ua = settings.get("userAgent") or DEFAULT_SETTINGS["userAgent"]
    return {
        "User-Agent": ua,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }

def fetch_url(url: str, settings: Dict[str, Any]) -> Optional[str]:
    """
    Fetch a URL with retry logic and basic error handling.

    Returns the response text on success, or None on repeated failure.
    """
    timeout = float(settings.get("timeoutSeconds", DEFAULT_SETTINGS["timeoutSeconds"]))
    max_retries = int(settings.get("maxRetries", DEFAULT_SETTINGS["maxRetries"]))
    base_backoff = float(
        settings.get("retryBackoffSeconds", DEFAULT_SETTINGS["retryBackoffSeconds"])
    )

    headers = _build_headers(settings)

    for attempt in range(1, max_retries + 1):
        try:
            logger.debug(f"Requesting URL (attempt {attempt}/{max_retries}): {url}")
            response = requests.get(url, headers=headers, timeout=timeout)
            if response.status_code >= 400:
                logger.warning(
                    f"Received HTTP {response.status_code} for {url}. "
                    f"Body snippet: {response.text[:200]!r}"
                )
                # For hard errors, no point in retrying too many times
                if 400 <= response.status_code < 500 and attempt == 1:
                    return None
            response.raise_for_status()
            return response.text
        except Exception as exc:
            logger.warning(
                f"Error fetching {url} on attempt {attempt}/{max_retries}: {exc}"
            )
            if attempt == max_retries:
                logger.error(f"Giving up on {url} after {max_retries} attempts.")
                return None
            # Exponential backoff with jitter
            backoff = base_backoff * (2 ** (attempt - 1))
            backoff += random.uniform(0, 0.5)
            logger.debug(f"Sleeping for {backoff:.2f} seconds before retry.")
            time.sleep(backoff)

    return None

def build_paged_url(base_url: str, page_number: int) -> str:
    """
    Build a URL for the given page number.

    On Clutch, pagination typically uses a `page` query parameter (0-based or 1-based
    depending on the section). Here we use a simple `?page=N` scheme.
    """
    if page_number <= 1:
        return base_url

    parsed = urlparse(base_url)
    query = parse_qs(parsed.query)
    # Use 1-based page index (page=2, page=3, etc.)
    query["page"] = [str(page_number)]
    new_query = urlencode(query, doseq=True)
    new_parsed = parsed._replace(query=new_query)
    paged_url = urlunparse(new_parsed)

    logger.debug(f"Built paged URL: {paged_url} from base {base_url} page {page_number}")
    return paged_url