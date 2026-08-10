# coding: utf-8
import base64
import json
import re
from typing import Any
from urllib.parse import quote, unquote, urljoin, urlparse

from app.models.music import LyricLine

AUDIO_CONTENT_TYPES = ("audio/", "application/octet-stream")
AUDIO_EXTENSIONS = {"aac", "flac", "m4a", "mp3", "ogg", "opus", "wav"}


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def extract_ext(url: str, fallback: str = "mp3") -> str:
    clean_url = url.split("?", 1)[0]
    suffix = clean_url.rsplit(".", 1)
    return suffix[1] if len(suffix) > 1 and suffix[1] else fallback


def absolute_url(value: str | None, base_url: str) -> str | None:
    if not value:
        return None
    return urljoin(base_url, value)


def is_http_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("http")


def validate_audio_url(
    http_client: Any,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 15,
    verify: bool = True,
) -> str:
    request_headers = {"Range": "bytes=0-1", **(headers or {})}
    response = http_client.get_response(
        url,
        headers=request_headers,
        timeout=timeout,
        verify=verify,
        stream=True,
    )
    try:
        content_type = str(response.headers.get("content-type") or "").lower()
        if content_type and not content_type.startswith(AUDIO_CONTENT_TYPES):
            raise ValueError(f"Non-audio content type: {content_type}")
        final_url = response.url
        if not content_type and extract_ext(final_url).lower() not in AUDIO_EXTENSIONS:
            raise ValueError("Audio response has no recognizable content type or extension")
        return final_url
    finally:
        response.close()


def safe_json_loads(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


def decode_js_string_literal(value: str) -> str:
    escaped_value = value.replace("\"", "\\\"")
    return json.loads("\"" + escaped_value + "\"")


def quote_id(value: str) -> str:
    return quote(value, safe="")


def unquote_repeated(value: str) -> str:
    decoded = value.strip()
    for _ in range(2):
        if "%" not in decoded:
            break
        decoded = unquote(decoded)
    return decoded


def decode_base64_url(value: str, replacement: tuple[str, str] | None = None) -> str:
    source = value.replace(replacement[0], replacement[1]) if replacement else value
    try:
        padding = "=" * (-len(source) % 4)
        return base64.b64decode(source + padding).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return ""


def strip_url_query(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(query="", fragment="").geturl()


def clean_lyric(value: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", value.replace("\r\n", "\n")).strip()


def parse_lrc_lines(lyric: str) -> list[LyricLine]:
    lines: list[LyricLine] = []
    time_pattern = re.compile(r"\[(\d{1,2}):(\d{1,2})(?:\.(\d{1,3}))?]")
    word_time_pattern = re.compile(r"<\d+,-?\d+>")

    for raw_line in lyric.splitlines():
        matches = list(time_pattern.finditer(raw_line))
        if not matches:
            continue
        text = word_time_pattern.sub("", time_pattern.sub("", raw_line)).strip()
        if not text:
            continue
        for match in matches:
            lines.append(LyricLine(time=_parse_lrc_time(match), text=text))

    return sorted(lines, key=lambda line: line.time)


def _parse_lrc_time(match: re.Match[str]) -> float:
    minutes = int(match.group(1))
    seconds = int(match.group(2))
    fraction_text = (match.group(3) or "").ljust(3, "0")[:3]
    fraction = int(fraction_text or "0") / 1000
    return minutes * 60 + seconds + fraction
