import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

logger = logging.getLogger("clutch_parser")

def _text_or_none(element) -> Optional[str]:
    if element is None:
        return None
    text = element.get_text(strip=True)
    return text or None

def _extract_clutch_relative_url(href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    parsed = urlparse(href)
    # If link is absolute and points to Clutch, return its path; otherwise keep as-is
    if parsed.netloc and "clutch.co" in parsed.netloc:
        return parsed.path or "/"
    if not parsed.netloc:
        # Already relative
        return parsed.path or href
    return href

def _find_website(card) -> Optional[str]:
    # Prefer explicit "Visit website" links
    link = card.select_one('a[href^="http"][target="_blank"]')
    if link and "website" in (link.get_text() or "").lower():
        return link.get("href")

    # Fallback: any http(s) link that is not the clutch profile itself
    for a in card.select('a[href^="http"]'):
        href = a.get("href")
        if not href:
            continue
        if "clutch.co" in href:
            continue
        return href

    return None

def _find_rating(card) -> Optional[str]:
    rating = card.select_one('[itemprop="ratingValue"]')
    if rating:
        return _text_or_none(rating)

    rating = card.select_one(".rating .rating-number, .rating span")
    return _text_or_none(rating)

def _find_review_count(card) -> Optional[str]:
    el = card.select_one(".reviews-link, .rating-reviews, a[href*='#reviews']")
    if el:
        return _text_or_none(el)

    # Fallback: look for something like "12 reviews"
    for span in card.select("span, a"):
        text = span.get_text(strip=True)
        if "review" in text.lower():
            return text

    return None

def _find_tag_with_keyword(card, keyword: str) -> Optional[str]:
    keyword_lower = keyword.lower()
    for el in card.select("li, div, span, p"):
        text = el.get_text(" ", strip=True)
        if keyword_lower in text.lower():
            return text
    return None

def _find_hourly_rate(card) -> Optional[str]:
    # Clutch often shows something like "$25 - $49 / hr"
    for el in card.select("li, div, span"):
        text = el.get_text(" ", strip=True)
        if "/ hr" in text or "/hr" in text.replace(" ", ""):
            return text
    return None

def _find_min_project_size(card) -> Optional[str]:
    text = _find_tag_with_keyword(card, "Min. project size")
    if text:
        return text

    # Fallback: look for something that starts with "$" and ends with "+"
    for el in card.select("li, div, span"):
        t = el.get_text(" ", strip=True)
        if t.startswith("$") and t.endswith("+"):
            return t
    return None

def _find_employee_count(card) -> Optional[str]:
    text = _find_tag_with_keyword(card, "employees")
    if text:
        return text

    for el in card.select("li, div, span"):
        t = el.get_text(" ", strip=True)
        if "employees" in t.lower():
            return t
    return None

def _find_location(card) -> Optional[str]:
    el = card.select_one(".locality, .location, .provider-location")
    if el:
        return _text_or_none(el)

    # Fallback: often inside address or span tags
    for el in card.select("span, div"):
        t = el.get_text(" ", strip=True)
        if "," in t and any(c.isalpha() for c in t):
            # Heuristic: looks like "City, Country"
            if 3 <= len(t.split(",")) <= 3:
                return t
    return None

def _find_description(card) -> Optional[str]:
    el = card.select_one(".company_info, .provider-short-description, p")
    return _text_or_none(el)

def _find_logo_url(card, base_url: str) -> Optional[str]:
    img = card.select_one("img")
    if not img:
        return None

    src = img.get("data-src") or img.get("src")
    if not src:
        return None

    return urljoin(base_url, src)

def _is_verified(card) -> bool:
    el = card.select_one(".verified, .clutch-verified, .verification-badge")
    if el:
        return True

    text = card.get_text(" ", strip=True).lower()
    return "verified" in text or "clutch verified" in text

def parse_company_card(card, base_url: str) -> Dict[str, Any]:
    name_el = card.select_one("h3 a, h2 a, .company_title a, .company-name a")
    if not name_el:
        name_el = card.select_one("h3, h2, .company_title, .company-name")

    name = _text_or_none(name_el)

    clutch_href = None
    if name_el and name_el.name == "a":
        clutch_href = name_el.get("href")
    else:
        link = card.select_one('a[href*="clutch.co/profile"]')
        if link:
            clutch_href = link.get("href")

    clutch_relative = _extract_clutch_relative_url(clutch_href)

    website = _find_website(card)
    rating = _find_rating(card)
    review_count = _find_review_count(card)
    hourly_rate = _find_hourly_rate(card)
    min_project_size = _find_min_project_size(card)
    employee_count = _find_employee_count(card)
    location = _find_location(card)
    description = _find_description(card)
    logo_url = _find_logo_url(card, base_url)
    is_verified = _is_verified(card)

    company = {
        "name": name,
        "clutchUrl": clutch_relative,
        "website": website,
        "rating": rating,
        "reviewCount": review_count,
        "hourlyRate": hourly_rate,
        "minProjectSize": min_project_size,
        "employeeCount": employee_count,
        "location": location,
        "description": description,
        "logoUrl": logo_url,
        "isVerified": is_verified,
    }

    # Filter out entries that are clearly incomplete
    if not company["name"] or not company["clutchUrl"]:
        logger.debug("Skipping card due to missing name or clutchUrl.")
        return {}

    return company

def parse_search_results(html: str, base_url: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")

    # Clutch uses different layouts depending on category and viewport
    cards = soup.select("div.provider-card, div.provider-row, li.provider-row")
    if not cards:
        # Fallback to a more generic selector
        cards = soup.select("div.directory-listing, li.directory-listing")

    if not cards:
        logger.warning("No company cards found in the provided HTML.")
        return []

    results: List[Dict[str, Any]] = []
    for card in cards:
        company = parse_company_card(card, base_url=base_url)
        if company:
            results.append(company)

    logger.info(f"Parsed {len(results)} company listings from search results HTML.")
    return results