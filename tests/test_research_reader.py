from unittest.mock import Mock
import pytest
from src.research_reader import PageText, read_public_page


def test_page_text_excludes_executable_content():
    page = PageText()
    page.feed('<p>制作の話</p><script>secret instruction</script><style>hidden</style><p>言葉の間</p>')
    assert page.parts == ['制作の話', '言葉の間']


@pytest.mark.parametrize('url', ['file:///etc/passwd', 'http://127.0.0.1/', 'http://[::1]/', 'https://user:pass@example.org/', 'http://example.org:8765/'])
def test_reader_rejects_local_and_credential_urls(url, monkeypatch):
    network = Mock()
    monkeypatch.setattr('src.research_reader.http.client.HTTPConnection', network)
    assert read_public_page(url) is None
    network.assert_not_called()


def test_connection_uses_validated_address_without_resolving_again(monkeypatch):
    from src.research_reader import connect_resolved
    import socket
    sock = Mock()
    monkeypatch.setattr('src.research_reader.socket.socket', Mock(return_value=sock))
    resolver = Mock(side_effect=AssertionError('must not resolve again'))
    monkeypatch.setattr('src.research_reader.socket.getaddrinfo', resolver)
    addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]
    assert connect_resolved(addresses, 8) is sock
    sock.connect.assert_called_once_with(('93.184.216.34', 443))
    resolver.assert_not_called()


def test_reader_keeps_hostname_for_tls_and_closes_connection(monkeypatch):
    import socket
    addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]
    monkeypatch.setattr('src.research_reader.socket.getaddrinfo', lambda *args, **kw: addresses)
    connection = Mock()
    response = connection.getresponse.return_value
    response.status = 200
    response.getheader.return_value = 'text/html; charset=utf-8'
    response.read.return_value = ('<p>公開された記事の本文です。</p>' * 30).encode()
    factory = Mock(return_value=connection)
    monkeypatch.setattr('src.research_reader.http.client.HTTPSConnection', factory)
    assert '記事の本文' in read_public_page('https://example.org/article')
    factory.assert_called_once_with('example.org', 443, timeout=8)
    connection.close.assert_called_once()
    response.status = 302
    assert read_public_page('https://example.org/article') is None
