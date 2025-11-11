import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from extractors.clutch_parser import parse_search_results
from extractors.helpers import fetch_url, load_settings, build_paged_url
from utils.json_formatter import save_json

def configure_logging(level: str) -> None:
    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }
    logging.basicConfig(
        level=level_map.get(level.lower(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clutch.co Search Results Scraper - Pay Per Results"
    )
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        default="data/inputs.sample.json",
        help="Path to input JSON containing search URLs and options.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="data/output.sample.json",
        help="Path to output JSON file for scraped results.",
    )
    parser.add_argument(
        "--settings",
        "-s",
        type=str,
        default="src/config/settings.example.json",
        help="Path to settings JSON file.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        help="Logging level: debug, info, warning, error.",
    )
    return parser.parse_args()

def load_input_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if "searchUrls" not in data or not isinstance(data["searchUrls"], list):
        raise ValueError("Input JSON must contain a 'searchUrls' array.")

    return data

def scrape_from_urls(
    search_urls: List[str],
    settings: Dict[str, Any],
    input_overrides: Dict[str, Any],
) -> List[Dict[str, Any]]:
    logger = logging.getLogger("scraper")
    results: List[Dict[str, Any]] = []

    max_pages_default = int(settings.get("maxPagesPerUrl", 1))
    input_max_pages = input_overrides.get("maxPagesPerUrl")
    if input_max_pages is not None:
        try:
            input_max_pages = int(input_max_pages)
        except (ValueError, TypeError):
            logger.warning(
                "Invalid 'maxPagesPerUrl' in input config; falling back to settings."
            )
            input_max_pages = None

    max_pages = input_max_pages or max_pages_default
    rate_limit_seconds = float(settings.get("rateLimitSeconds", 0.0))

    for url in search_urls:
        logger.info(f"Scraping URL: {url} (up to {max_pages} pages)")
        for page in range(1, max_pages + 1):
            page_url = build_paged_url(url, page)
            logger.info(f"Fetching page {page}: {page_url}")
            html = fetch_url(page_url, settings)

            if html is None:
                logger.warning(f"Stopping pagination for URL due to fetch failures: {url}")
                break

            page_results = parse_search_results(html, base_url=url)
            if not page_results:
                logger.info(
                    f"No company listings found on page {page}; "
                    f"stopping pagination for this URL."
                )
                break

            logger.info(f"Found {len(page_results)} companies on page {page}.")
            results.extend(page_results)

            if rate_limit_seconds > 0:
                logger.debug(f"Sleeping for {rate_limit_seconds} seconds (rate limit).")
                import time

                time.sleep(rate_limit_seconds)

    # Deduplicate by (name, clutchUrl) to avoid duplicates across pages
    seen = set()
    unique_results: List[Dict[str, Any]] = []
    for item in results:
        key = (item.get("name"), item.get("clutchUrl"))
        if key not in seen:
            seen.add(key)
            unique_results.append(item)

    logger.info(
        f"Scraping complete. Collected {len(unique_results)} unique companies "
        f"from {len(search_urls)} URLs."
    )
    return unique_results

def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)

    logger = logging.getLogger("main")

    # Ensure src directory is on sys.path so imports work when running as script
    src_dir = Path(__file__).resolve().parent
    if str(src_dir) not in os.sys.path:
        os.sys.path.append(str(src_dir))

    try:
        input_path = Path(args.input)
        output_path = Path(args.output)
        settings_path = Path(args.settings)

        logger.info(f"Using input file: {input_path}")
        logger.info(f"Using settings file: {settings_path}")
        logger.info(f"Output will be written to: {output_path}")

        input_config = load_input_config(input_path)
        settings = load_settings(settings_path)

        search_urls = input_config["searchUrls"]
        results = scrape_from_urls(search_urls, settings, input_config)

        save_json(results, output_path, pretty=True)

        logger.info("Done. Scraped data has been saved successfully.")
    except Exception as exc:
        logger.exception(f"Fatal error during execution: {exc}")
        raise SystemExit(1)

if __name__ == "__main__":
    main()