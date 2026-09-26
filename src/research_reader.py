"""Read bounded public HTML/text excerpts; never execute page instructions."""
import ipaddress
import socket
import http.client
from email.message import Message
from html.parser import HTMLParser
from urllib.parse import urlsplit


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript', 'svg'):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'svg'):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


def connect_resolved(addresses, timeout):
    """Connect only to the public socket addresses validated by the caller."""
    last_error = None
    for family, kind, proto, _, sockaddr in addresses:
        sock = socket.socket(family, kind, proto)
        try:
            sock.settimeout(timeout)
            sock.connect(sockaddr)
            return sock
        except OSError as exc:
            last_error = exc
            sock.close()
    raise last_error or OSError('No public address')


def read_public_page(url):
    """Return an excerpt, or None for inaccessible/unsupported resources.

    Redirects are not followed. Video/audio/PDF require a separate reader.
    DNS validation avoids fetching local services from search-supplied links.
    """
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            return None
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        if port not in (80, 443):
            return None
        addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            return None
        connection_type = http.client.HTTPSConnection if parsed.scheme == 'https' else http.client.HTTPConnection
        connection = connection_type(parsed.hostname, port, timeout=8)
        # HTTPSConnection still verifies the certificate and uses the original
        # hostname for TLS SNI; only its TCP connection is pinned to these IPs.
        connection._create_connection = lambda address, timeout, source_address=None: connect_resolved(addresses, timeout)
        try:
            target = parsed.path or '/'
            if parsed.query:
                target += '?' + parsed.query
            connection.request('GET', target, headers={'User-Agent': 'NoahResearch/1.0'})
            response = connection.getresponse()
            if response.status != 200:
                return None
            headers = Message()
            headers['Content-Type'] = response.getheader('Content-Type', '')
            kind = headers.get_content_type()
            if kind not in ('text/html', 'text/plain', 'application/xhtml+xml'):
                return None
            raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                return None
            content = raw.decode(headers.get_content_charset() or 'utf-8', errors='replace')
        finally:
            connection.close()
        if kind != 'text/plain':
            parser = PageText()
            parser.feed(content)
            content = '\n'.join(parser.parts)
        content = content.strip()[:10000]
        return content if len(content) >= 200 else None
    except (OSError, ValueError, LookupError, http.client.HTTPException):
        return None
