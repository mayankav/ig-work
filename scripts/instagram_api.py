"""Shared Instagram identifiers; no generation code or optional dependencies."""
GRAPH_FACEBOOK = "https://graph.facebook.com/v20.0"
GRAPH_INSTAGRAM = "https://graph.instagram.com/v21.0"
PUBLISHED_FILENAME = "published.json"


def graph_base(token: str) -> str:
    return GRAPH_INSTAGRAM if token.startswith("IGAAP") else GRAPH_FACEBOOK
