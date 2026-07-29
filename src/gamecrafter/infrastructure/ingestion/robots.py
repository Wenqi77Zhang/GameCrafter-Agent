"""robots.txt interpretation isolated from outbound fetching."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

GAMECRAFTER_USER_AGENT = "GameCrafter"


@dataclass(frozen=True, slots=True)
class RobotsRules:
    """Parsed rules for one already-authorized official origin."""

    origin: str
    text: str

    def can_fetch(self, url: str, *, user_agent: str = GAMECRAFTER_USER_AGENT) -> bool:
        """Return the standard-library parser's decision for one same-origin URL."""

        parsed_origin = urlsplit(self.origin)
        parsed_url = urlsplit(url)
        if (parsed_url.scheme, parsed_url.netloc) != (
            parsed_origin.scheme,
            parsed_origin.netloc,
        ):
            return False
        parser = RobotFileParser()
        parser.set_url(f"{self.origin.rstrip('/')}/robots.txt")
        parser.parse(self.text.splitlines())
        return parser.can_fetch(user_agent, url)
