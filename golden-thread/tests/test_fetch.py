import hashlib
import socket
import urllib.request

import pytest

from goldthread.config import load_pack
from goldthread.fetch import OfflineError, fetch_pack, http_get
from goldthread.netguard import NetworkBlocked, no_network

HEADER = "doc_id,title,layout,revision,date,status,supersedes,url,sha256\n"


def write_register(pack_dir, sha="", url="https://example.invalid/a.pdf"):
    (pack_dir / "register.csv").write_text(
        HEADER + f"DOC-A,Doc A,regulatory_guide,r1,2025-01-01,issued,,{url},{sha}\n")


@pytest.fixture
def online_pack_dir(synthetic_pack_dir):
    p = synthetic_pack_dir / "pack.yaml"
    p.write_text(p.read_text().replace("offline: true", "offline: false"))
    write_register(synthetic_pack_dir)
    return synthetic_pack_dir


def load(pack_dir, tmp_path):
    return load_pack(pack_dir, data_root=tmp_path / "data")


def never(url):
    raise AssertionError(f"opener should not be called for {url}")


def test_fetch_downloads_and_records_checksum(online_pack_dir, tmp_path):
    pack = load(online_pack_dir, tmp_path)
    report = fetch_pack(pack, opener=lambda url: b"%PDF-1.4 a")
    assert report.downloaded == ["DOC-A@r1"] and report.recorded_checksums == ["DOC-A@r1"]
    assert load(online_pack_dir, tmp_path).register[0].sha256 == hashlib.sha256(b"%PDF-1.4 a").hexdigest()
    assert (pack.data_dir / "cache" / "DOC-A@r1.pdf").read_bytes() == b"%PDF-1.4 a"


def test_fetch_skips_present_file_with_matching_checksum(online_pack_dir, tmp_path):
    write_register(online_pack_dir, sha=hashlib.sha256(b"x").hexdigest())
    pack = load(online_pack_dir, tmp_path)
    (pack.data_dir / "cache").mkdir(parents=True)
    (pack.data_dir / "cache" / "DOC-A@r1.pdf").write_bytes(b"x")
    report = fetch_pack(pack, opener=never)
    assert report.already_present == ["DOC-A@r1"] and report.downloaded == []


def test_fetch_registers_uploaded_file(online_pack_dir, tmp_path):
    pack = load(online_pack_dir, tmp_path)
    (pack.data_dir / "cache").mkdir(parents=True)
    (pack.data_dir / "cache" / "DOC-A@r1.pdf").write_bytes(b"uploaded")
    report = fetch_pack(pack, opener=never)
    assert report.recorded_checksums == ["DOC-A@r1"] and report.already_present == ["DOC-A@r1"]
    assert load(online_pack_dir, tmp_path).register[0].sha256 == hashlib.sha256(b"uploaded").hexdigest()


def test_refetch_checksum_mismatch_quarantined(online_pack_dir, tmp_path):  # Review Focus 3
    old = hashlib.sha256(b"old").hexdigest()
    write_register(online_pack_dir, sha=old)
    pack = load(online_pack_dir, tmp_path)
    report = fetch_pack(pack, opener=lambda url: b"new")
    assert report.mismatched == ["DOC-A@r1"] and report.downloaded == []
    assert (pack.data_dir / "cache" / "quarantine" / "DOC-A@r1.pdf").read_bytes() == b"new"
    assert not (pack.data_dir / "cache" / "DOC-A@r1.pdf").exists()
    assert load(online_pack_dir, tmp_path).register[0].sha256 == old


def test_fetch_failure_reported_and_others_continue(online_pack_dir, tmp_path):
    write_register(online_pack_dir, url="")
    report = fetch_pack(load(online_pack_dir, tmp_path), opener=never)
    assert report.failed == ["DOC-A@r1: no url in register"]


def test_fetch_refused_for_offline_pack(synthetic_pack_dir, tmp_path):
    with pytest.raises(OfflineError, match="offline pack: fetch is disabled"):
        fetch_pack(load(synthetic_pack_dir, tmp_path), opener=never)


def test_no_network_blocks_and_restores():
    original = socket.create_connection
    with no_network():
        with pytest.raises(NetworkBlocked):
            socket.create_connection(("example.com", 80))
        with pytest.raises(NetworkBlocked):
            socket.getaddrinfo("example.com", 80)
        with pytest.raises(NetworkBlocked):
            socket.socket().connect(("127.0.0.1", 9))
    assert socket.create_connection is original


def test_http_get_sends_generic_user_agent(monkeypatch):
    seen = {}

    class Response:
        def read(self):
            return b"ok"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout):
        seen["ua"] = request.get_header("User-agent")
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert http_get("https://example.invalid/x") == b"ok"
    assert seen["ua"] == "golden-thread/0.1"
