import html
import re

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")
_BLOCK = re.compile(r"</?(p|div|br|li|ul|ol|h[1-6]|tr)[^>]*>", re.I)


def html_to_text(s: str | None) -> str:
    """Strip HTML (handles double-escaped content like Greenhouse) to plain text."""
    if not s:
        return ""
    s = html.unescape(s)
    if "&lt;" in s or "&amp;" in s:  # double-escaped
        s = html.unescape(s)
    s = _BLOCK.sub("\n", s)
    s = _TAG.sub("", s)
    s = html.unescape(s)
    s = _WS.sub(" ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()
