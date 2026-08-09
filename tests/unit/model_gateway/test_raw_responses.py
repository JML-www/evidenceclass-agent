import pytest

from packages.model_gateway.raw_responses import (
    DirectoryRawResponseSink,
    InMemoryRawResponseSink,
    ObjectStoreRawResponseSink,
)
from packages.object_storage import InMemoryObjectStore


def test_raw_response_sinks_return_references_instead_of_logging_bodies(tmp_path):
    payload = b'{"synthetic":true}'
    memory = InMemoryRawResponseSink()
    memory_ref = memory.put(payload)
    assert memory.objects[memory_ref] == payload

    directory = DirectoryRawResponseSink(tmp_path / "raw")
    directory_ref = directory.put(payload)
    assert directory_ref.endswith(".json")
    assert list((tmp_path / "raw").glob("*.tmp")) == []
    assert next((tmp_path / "raw").glob("*.json")).read_bytes() == payload

    store = InMemoryObjectStore()
    object_sink = ObjectStoreRawResponseSink(
        store,
        prefix="workspaces/synthetic/jobs/synthetic/model-responses",
    )
    object_ref = object_sink.put(payload)
    assert object_ref.startswith("object://workspaces/synthetic/")
    assert store.read(object_ref.removeprefix("object://")) == payload


def test_object_sink_rejects_unsafe_prefix():
    with pytest.raises(ValueError, match="safe relative"):
        ObjectStoreRawResponseSink(InMemoryObjectStore(), prefix="../escape")
