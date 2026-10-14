import io
import threading
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from clickwheel import pipeline
from clickwheel.api import create_app
from clickwheel.jobs import JobManager
from clickwheel.source import SourceError

from .fakes import FakeFetcher, probe_info, settings_for

URL = "https://youtu.be/abcdefghijk"
CANONICAL = "https://www.youtube.com/watch?v=abcdefghijk"


@pytest.fixture
def make_client(tmp_path, opus_source, thumbnail):
    def build(prober=None, fetcher=None, **overrides):
        settings = settings_for(tmp_path, **overrides)
        fetcher = fetcher or FakeFetcher(opus_source, thumbnail)
        manager = JobManager(settings, runner=lambda job: pipeline.run(job, settings, fetcher=fetcher))
        calls = []

        def default_prober(url):
            calls.append(url)
            return probe_info()

        app = create_app(settings, manager, prober=prober or default_prober)
        client = TestClient(app)
        client.probe_calls = calls
        return client

    return build


def poll_done(client, job_id, timeout=60):
    deadline = time.time() + timeout
    while True:
        snap = client.get(f"/api/jobs/{job_id}").json()
        if snap["state"] in {"done", "error", "cancelled"}:
            return snap
        assert time.time() < deadline, snap
        time.sleep(0.05)


def test_index_and_security_headers(make_client):
    response = make_client().get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    csp = response.headers["content-security-policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_health_is_minimal_and_info_has_versions(make_client):
    client = make_client()
    health = client.get("/api/health").json()
    assert health["ok"] is True and health["edition"] in {"full", "local"}
    body = client.get("/api/info").json()
    assert body["aac_encoder"] in {"aac_at", "aac"}
    assert body["genre"] == "Lo-Fi" and body["yt_dlp"] and body["ffmpeg"]


def test_analyze_preview(make_client):
    client = make_client()
    response = client.post("/api/analyze", json={"url": URL})
    assert response.status_code == 200, response.text
    body = response.json()
    assert client.probe_calls == [CANONICAL] and body["url"] == CANONICAL
    assert body["title"] == "lofi hip hop mix beats to relax/study to"
    assert body["channel"] == "Lofi Girl" and body["year"] == "2024"
    assert body["source"] == {"format_id": "251", "codec": "OPUS", "kbps": 141, "khz": 48.0}
    assert [t["artist"] for t in body["tracks"]] == ["No Spirit", "S N U G, Mondo Loops", "Yasumu"]
    assert body["single"]["artist"] == "Lofi Girl"
    assert body["estimate"] == {"aac": 384000, "alac": 1095000}
    assert body["thumbnail"].startswith("https://i.ytimg.com/")
    assert response.headers["cache-control"] == "no-store"


def test_analyze_drops_foreign_thumbnail(make_client):
    client = make_client(prober=lambda url: probe_info(thumbnail="https://evil.example/x.jpg"))
    assert client.post("/api/analyze", json={"url": URL}).json()["thumbnail"] is None


def test_analyze_rejects_non_youtube(make_client):
    client = make_client()
    response = client.post("/api/analyze", json={"url": "https://vimeo.com/123"})
    assert response.status_code == 400
    assert response.json()["error"]["title"] == "NOT A YOUTUBE LINK."
    assert client.probe_calls == []


@pytest.mark.parametrize(
    ("info", "title"),
    [
        (probe_info(live_status="is_live"), "LIVE STREAM."),
        (probe_info(live_status="is_upcoming"), "NOT AIRED YET."),
        (probe_info(duration=13 * 3600), "OVER 12 HOURS."),
    ],
)
def test_analyze_rejects_unplayable(make_client, info, title):
    response = make_client(prober=lambda url: info).post("/api/analyze", json={"url": URL})
    assert response.status_code == 422 and response.json()["error"]["title"] == title


def test_analyze_maps_source_errors(make_client):
    def refuse(url):
        raise SourceError("PRIVATE VIDEO.", "Only its owner can play it.")

    response = make_client(prober=refuse).post("/api/analyze", json={"url": URL})
    assert response.status_code == 422 and response.json()["error"]["title"] == "PRIVATE VIDEO."


def test_job_lifecycle_and_download(make_client):
    client = make_client()
    response = client.post("/api/jobs", json={"url": URL, "mode": "aac", "split": True})
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["url"] == CANONICAL and job["mode"] == "aac"

    snap = poll_done(client, job["id"])
    assert snap["state"] == "done", snap
    assert snap["result"]["tracks"] == 3 and snap["result"]["filename"].endswith(".zip")

    file = client.get(f"/api/jobs/{job['id']}/file")
    assert file.status_code == 200
    assert file.headers["content-type"] == "application/zip"
    assert file.headers["content-disposition"].startswith("attachment;")
    assert len(zipfile.ZipFile(io.BytesIO(file.content)).namelist()) == 3

    listed = client.get("/api/jobs").json()
    assert [j["id"] for j in listed] == [job["id"]]

    assert client.delete(f"/api/jobs/{job['id']}").status_code == 200
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404


def test_single_file_download_type(make_client):
    client = make_client()
    job = client.post("/api/jobs", json={"url": URL, "mode": "alac", "split": False}).json()
    assert poll_done(client, job["id"])["state"] == "done"
    file = client.get(f"/api/jobs/{job['id']}/file")
    assert file.headers["content-type"] == "audio/mp4"
    assert "Lofi%20Girl" in file.headers["content-disposition"] or "Lofi Girl" in file.headers["content-disposition"]


def test_file_before_done_and_cancel(make_client, opus_source):
    gate = threading.Event()
    client = make_client(fetcher=FakeFetcher(opus_source, None, gate=gate))
    job = client.post("/api/jobs", json={"url": URL}).json()
    assert client.get(f"/api/jobs/{job['id']}/file").status_code == 409
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 200
    assert poll_done(client, job["id"])["state"] == "cancelled"


def test_job_ids_are_validated(make_client):
    client = make_client()
    assert client.get("/api/jobs/../../etc/passwd").status_code == 404
    assert client.get("/api/jobs/not-a-job-id").status_code == 422
    assert client.get("/api/jobs/" + "0" * 32).status_code == 404


@pytest.mark.parametrize(
    "payload",
    [{"url": URL, "mode": "mp3"}, {"url": URL, "split": "maybe"}, {"mode": "aac"}, {"url": "x" * 5000}],
)
def test_bad_job_payloads(make_client, payload):
    response = make_client().post("/api/jobs", json=payload)
    assert response.status_code == 422 and response.json()["error"]["title"] == "BAD REQUEST."


def test_cross_site_writes_are_refused(make_client):
    client = make_client()
    evil = client.post("/api/jobs", json={"url": URL}, headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    fetch_meta = client.post("/api/jobs", json={"url": URL}, headers={"Sec-Fetch-Site": "cross-site"})
    assert fetch_meta.status_code == 403
    other_port = client.post("/api/jobs", json={"url": URL}, headers={"Origin": "http://testserver:3000"})
    assert other_port.status_code == 403
    same = client.post("/api/analyze", json={"url": URL}, headers={"Origin": "http://testserver"})
    assert same.status_code == 200


def test_simple_form_posts_are_not_parsed(make_client):
    response = make_client().post(
        "/api/jobs", content='{"url": "%s"}' % URL, headers={"Content-Type": "text/plain"}
    )
    assert response.status_code == 422


def test_unknown_host_header_is_refused(make_client):
    response = make_client().get("/api/health", headers={"Host": "rebind.evil.example"})
    assert response.status_code == 400
