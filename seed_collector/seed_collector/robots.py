from typing import Optional, Tuple
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from .fetcher import Fetcher, FetchError


async def check_robots(fetcher: Fetcher, url: str, user_agent: str) -> Tuple[bool, Optional[str]]:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return True, None

    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        response = await fetcher.fetch(robots_url)
    except FetchError as exc:
        return True, str(exc)

    if response.status_code >= 400:
        return True, None

    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    allowed = parser.can_fetch(user_agent, url)
    return allowed, None
