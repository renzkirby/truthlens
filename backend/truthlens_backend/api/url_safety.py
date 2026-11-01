"""URL reputation normalization and SSRF-resistant metadata preview fetching."""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
import http.client
import ipaddress
import socket
import ssl
from urllib.parse import quote, urljoin, urlsplit

from .services import validate_public_url


NO_KNOWN_THREATS = "NO_KNOWN_THREATS"
KNOWN_THREAT = "KNOWN_THREAT"
CHECK_UNAVAILABLE = "CHECK_UNAVAILABLE"

PREVIEW_MAX_BYTES = 256 * 1024
PREVIEW_MAX_REDIRECTS = 3
PREVIEW_CONNECT_TIMEOUT_SEC = 3
PREVIEW_READ_TIMEOUT_SEC = 5
_ALLOWED_PREVIEW_PORTS = {80, 443}
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}


class UrlPreviewFetchError(RuntimeError):
    """Bounded, safe preview failure with no remote response content."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class UrlPreviewMetadata:
    final_url: str
    title: str
    description: str
    site_name: str


def normalize_url_safety_result(result: dict | None) -> dict:
    """Map legacy provider states to user-facing, non-guarantee semantics."""
    payload = result if isinstance(result, dict) else {}
    raw_status = str(payload.get("status") or "").upper()
    if raw_status in {"UNSAFE", KNOWN_THREAT}:
        status = KNOWN_THREAT
    elif raw_status in {"SAFE", NO_KNOWN_THREATS}:
        status = NO_KNOWN_THREATS
    else:
        status = CHECK_UNAVAILABLE

    threat_types = payload.get("threat_types")
    if not isinstance(threat_types, list):
        threat_types = []
    threat_types = [
        str(item)[:64]
        for item in threat_types
        if isinstance(item, (str, int, float)) and str(item).strip()
    ][:20]

    raw_reason = str(payload.get("reason") or "")
    if raw_reason == "SAFE_BROWSING_API_KEY not configured":
        reason = "PROVIDER_NOT_CONFIGURED"
    elif raw_reason == "provider_unreachable":
        reason = "PROVIDER_UNREACHABLE"
    elif raw_reason.startswith("provider_error_"):
        reason = "PROVIDER_ERROR"
    elif raw_reason:
        reason = "CHECK_UNAVAILABLE"
    else:
        reason = ""

    return {
        "status": status,
        "provider": str(payload.get("provider") or "")[:64],
        "reason": reason,
        "threat_types": threat_types,
    }


def url_safety_is_known_threat(result: dict | None) -> bool:
    return normalize_url_safety_result(result)["status"] == KNOWN_THREAT


def _public_address_records(hostname: str, port: int):
    try:
        ascii_hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise UrlPreviewFetchError("INVALID_HOSTNAME") from exc

    try:
        records = socket.getaddrinfo(
            ascii_hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise UrlPreviewFetchError("DNS_UNAVAILABLE") from exc

    unique = []
    seen = set()
    for family, socktype, proto, _canonname, sockaddr in records:
        address = sockaddr[0]
        try:
            parsed_ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise UrlPreviewFetchError("DNS_INVALID_ADDRESS") from exc
        if not parsed_ip.is_global:
            raise UrlPreviewFetchError("NON_PUBLIC_ADDRESS")
        key = (family, proto, sockaddr)
        if key not in seen:
            seen.add(key)
            unique.append((family, socktype, proto, sockaddr))

    if not unique:
        raise UrlPreviewFetchError("DNS_UNAVAILABLE")
    return ascii_hostname, unique


def _request_target(parts) -> str:
    path = quote(
        parts.path or "/",
        safe="/%:@!$&'()*+,;=-._~",
    )
    if not parts.query:
        return path
    query = quote(
        parts.query,
        safe="=&?/:;+,%@!$'()*-._~",
    )
    return f"{path}?{query}"


def _host_header(hostname: str, port: int, scheme: str) -> str:
    display_host = f"[{hostname}]" if ":" in hostname else hostname
    default_port = 443 if scheme == "https" else 80
    if port == default_port:
        return display_host
    return f"{display_host}:{port}"


def _open_pinned_socket(record, *, hostname: str, scheme: str):
    family, socktype, proto, sockaddr = record
    raw_socket = socket.socket(family, socktype, proto)
    raw_socket.settimeout(PREVIEW_CONNECT_TIMEOUT_SEC)
    try:
        raw_socket.connect(sockaddr)
        raw_socket.settimeout(PREVIEW_READ_TIMEOUT_SEC)
        if scheme == "https":
            context = ssl.create_default_context()
            return context.wrap_socket(
                raw_socket,
                server_hostname=hostname,
            )
        return raw_socket
    except Exception:
        raw_socket.close()
        raise


def _fetch_once(url: str):
    safe_url, error = validate_public_url(url)
    if error:
        raise UrlPreviewFetchError("INVALID_URL")

    parts = urlsplit(safe_url)
    scheme = parts.scheme.lower()
    hostname = parts.hostname
    if not hostname:
        raise UrlPreviewFetchError("INVALID_URL")

    try:
        port = parts.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise UrlPreviewFetchError("INVALID_PORT") from exc
    expected_port = 443 if scheme == "https" else 80
    if port not in _ALLOWED_PREVIEW_PORTS or port != expected_port:
        raise UrlPreviewFetchError("UNSUPPORTED_PORT")

    ascii_hostname, records = _public_address_records(hostname, port)
    last_error = None
    for record in records:
        sock = None
        response = None
        try:
            sock = _open_pinned_socket(
                record,
                hostname=ascii_hostname,
                scheme=scheme,
            )
            request = (
                f"GET {_request_target(parts)} HTTP/1.1\r\n"
                f"Host: {_host_header(ascii_hostname, port, scheme)}\r\n"
                "User-Agent: TruthLens-SourcePreview/1.0\r\n"
                "Accept: text/html,application/xhtml+xml;q=0.9\r\n"
                "Accept-Encoding: identity\r\n"
                "Connection: close\r\n"
                "\r\n"
            )
            sock.sendall(request.encode("ascii"))
            response = http.client.HTTPResponse(sock)
            response.begin()
            return safe_url, response, sock
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            last_error = exc
            if response is not None:
                response.close()
            if sock is not None:
                sock.close()

    raise UrlPreviewFetchError("CONNECT_FAILED") from last_error


class _MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title_parts = []
        self.description = ""
        self.og_title = ""
        self.site_name = ""

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "title":
            self.in_title = True
            return
        if tag != "meta":
            return
        values = {
            str(key).lower(): value
            for key, value in attrs
            if key and value is not None
        }
        key = str(values.get("property") or values.get("name") or "").lower()
        content = str(values.get("content") or "")
        if not content:
            return
        if key == "og:title" and not self.og_title:
            self.og_title = content
        elif key in {"description", "og:description"} and not self.description:
            self.description = content
        elif key == "og:site_name" and not self.site_name:
            self.site_name = content

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title and len("".join(self.title_parts)) < 500:
            self.title_parts.append(data)


def _clean_metadata(value: str, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = " ".join(unescape(value).split())
    return cleaned[:limit]


def fetch_url_preview_metadata(url: str) -> UrlPreviewMetadata:
    """Fetch bounded HTML metadata without proxies, cookies, JS, or auto-redirects."""
    current_url = url
    for redirect_index in range(PREVIEW_MAX_REDIRECTS + 1):
        response = None
        sock = None
        try:
            current_url, response, sock = _fetch_once(current_url)
            status = response.status
            if status in _REDIRECT_STATUSES:
                location = response.getheader("Location")
                if not location:
                    raise UrlPreviewFetchError("REDIRECT_MISSING_LOCATION")
                if redirect_index >= PREVIEW_MAX_REDIRECTS:
                    raise UrlPreviewFetchError("TOO_MANY_REDIRECTS")
                current_url = urljoin(current_url, location)
                continue

            if status != 200:
                raise UrlPreviewFetchError("HTTP_STATUS_UNSUPPORTED")

            content_type = str(response.getheader("Content-Type") or "")
            mime_type = content_type.split(";", 1)[0].strip().lower()
            if mime_type not in _HTML_CONTENT_TYPES:
                raise UrlPreviewFetchError("CONTENT_TYPE_UNSUPPORTED")

            content_length = response.getheader("Content-Length")
            if content_length:
                try:
                    if int(content_length) > PREVIEW_MAX_BYTES:
                        raise UrlPreviewFetchError("RESPONSE_TOO_LARGE")
                except ValueError:
                    pass

            body = response.read(PREVIEW_MAX_BYTES + 1)
            if len(body) > PREVIEW_MAX_BYTES:
                raise UrlPreviewFetchError("RESPONSE_TOO_LARGE")

            charset = response.headers.get_content_charset() or "utf-8"
            try:
                html_text = body.decode(charset, errors="replace")
            except LookupError:
                html_text = body.decode("utf-8", errors="replace")

            parser = _MetadataParser()
            try:
                parser.feed(html_text)
            except Exception as exc:
                raise UrlPreviewFetchError("HTML_PARSE_FAILED") from exc

            title = _clean_metadata(
                parser.og_title or "".join(parser.title_parts),
                300,
            )
            description = _clean_metadata(parser.description, 500)
            site_name = _clean_metadata(parser.site_name, 120)
            return UrlPreviewMetadata(
                final_url=current_url,
                title=title,
                description=description,
                site_name=site_name,
            )
        finally:
            if response is not None:
                response.close()
            if sock is not None:
                sock.close()

    raise UrlPreviewFetchError("TOO_MANY_REDIRECTS")
