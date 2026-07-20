# -*- coding: utf-8 -*-
# flake8: noqa: E501
from __future__ import annotations

from models.media_transport import _upload_local_file_to_dashscope_temp_sync


def test_dashscope_temporary_upload_streams_file_handle_instead_of_loading_bytes(
    tmp_path,
    monkeypatch,
) -> None:
    video = tmp_path / "large-local-video.mp4"
    with video.open("wb") as stream:
        stream.seek(64 * 1024 * 1024 - 1)
        stream.write(b"\0")
    observed = {}

    class FakeResponse:
        def __init__(self, payload=None):
            self.payload = payload or {}

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class FakeClient:
        def __init__(self, **kwargs):
            observed["client_kwargs"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, url, *, params, headers):
            observed["policy_request"] = (url, params, headers)
            return FakeResponse(
                {
                    "data": {
                        "max_file_size_mb": 1024,
                        "upload_dir": "dashscope-instant/account/date/id",
                        "upload_host": "https://upload.example.test",
                        "oss_access_key_id": "temporary-access",
                        "signature": "temporary-signature",
                        "policy": "temporary-policy",
                        "x_oss_object_acl": "private",
                        "x_oss_forbid_overwrite": "true",
                    },
                },
            )

        def post(self, url, *, data, files):
            filename, file_handle, media_type = files["file"]
            observed["upload"] = {
                "url": url,
                "data": dict(data),
                "filename": filename,
                "media_type": media_type,
                "is_bytes": isinstance(file_handle, (bytes, bytearray)),
                "first_byte": file_handle.read(1),
            }
            return FakeResponse()

    monkeypatch.setattr("models.media_transport.httpx.Client", FakeClient)

    url = _upload_local_file_to_dashscope_temp_sync(
        video,
        api_key="test-api-key",
        model_name="qwen3.7-plus",
        media_type="video/mp4",
    )

    assert url.startswith("oss://dashscope-instant/account/date/id/")
    assert observed["upload"]["is_bytes"] is False
    assert observed["upload"]["first_byte"] == b"\0"
    assert observed["upload"]["filename"].endswith(".mp4")
    assert observed["upload"]["media_type"] == "video/mp4"
    assert observed["upload"]["data"]["success_action_status"] == "200"
