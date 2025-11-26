import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.omnimcp.services.content_manager import ContentManager


@pytest.fixture
def temp_storage():
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def content_manager(temp_storage):
    return ContentManager(
        storage_path=temp_storage,
        openai_api_key="test-key",
        max_tokens=50,
        describe_images=False,
        vision_model="gpt-4.1-mini"
    )


class TestContentManagerText:
    @pytest.mark.asyncio
    async def test_small_text_passthrough(self, content_manager):
        async with content_manager:
            blocks = [{"type": "text", "text": "Hello world"}]
            result = await content_manager.process_content(blocks)
            assert len(result) == 1
            assert result[0]["type"] == "text"
            assert result[0]["text"] == "Hello world"

    @pytest.mark.asyncio
    async def test_large_text_chunking(self, content_manager):
        async with content_manager:
            long_text = "Hello world. " * 100
            blocks = [{"type": "text", "text": long_text}]
            result = await content_manager.process_content(blocks)

            assert len(result) == 1
            assert "truncated" in result[0]["text"].lower()
            assert "Reference:" in result[0]["text"]
            assert "get_content" in result[0]["text"]

    @pytest.mark.asyncio
    async def test_chunked_text_retrieval(self, content_manager):
        async with content_manager:
            long_text = "Word " * 200
            blocks = [{"type": "text", "text": long_text}]
            result = await content_manager.process_content(blocks)

            import re
            match = re.search(r'Reference: ([a-f0-9-]+)', result[0]["text"])
            assert match is not None
            ref_id = match.group(1)

            chunk_0 = content_manager.get_content(ref_id, chunk_index=0)
            assert chunk_0["type"] == "text"
            assert chunk_0["chunk_index"] == 0
            assert chunk_0["total_chunks"] > 1

            full_content = content_manager.get_content(ref_id)
            assert full_content["type"] == "text"
            assert "Word" in full_content["text"]


class TestContentManagerImage:
    @pytest.mark.asyncio
    async def test_image_offload_no_description(self, content_manager):
        async with content_manager:
            blocks = [{
                "type": "image",
                "data": "aGVsbG8gd29ybGQ=",
                "mimeType": "image/png"
            }]
            result = await content_manager.process_content(blocks)

            assert len(result) == 1
            assert result[0]["type"] == "text"
            assert "Reference:" in result[0]["text"]
            assert "image/png" not in result[0]["text"] or "MimeType" not in result[0]["text"]

    @pytest.mark.asyncio
    async def test_image_retrieval(self, content_manager):
        async with content_manager:
            blocks = [{
                "type": "image",
                "data": "aGVsbG8gd29ybGQ=",
                "mimeType": "image/png"
            }]
            result = await content_manager.process_content(blocks)

            import re
            match = re.search(r'Reference: ([a-f0-9-]+)', result[0]["text"])
            ref_id = match.group(1)

            retrieved = content_manager.get_content(ref_id)
            assert retrieved["type"] == "image"
            assert retrieved["data"] == "aGVsbG8gd29ybGQ="
            assert retrieved["mimeType"] == "image/png"

    @pytest.mark.asyncio
    async def test_image_with_vision_description(self, temp_storage):
        cm = ContentManager(
            storage_path=temp_storage,
            openai_api_key="test-key",
            max_tokens=50,
            describe_images=True,
            vision_model="gpt-4.1-mini"
        )

        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock()]
        mock_response.choices[0].message.content = "A test image description"

        async with cm:
            with patch.object(cm.client.chat.completions, 'create', new_callable=AsyncMock, return_value=mock_response):
                blocks = [{
                    "type": "image",
                    "data": "aGVsbG8=",
                    "mimeType": "image/jpeg"
                }]
                result = await cm.process_content(blocks)
                assert "A test image description" in result[0]["text"]


class TestContentManagerAudio:
    @pytest.mark.asyncio
    async def test_audio_offload(self, content_manager):
        async with content_manager:
            blocks = [{
                "type": "audio",
                "data": "YXVkaW9kYXRh",
                "mimeType": "audio/wav"
            }]
            result = await content_manager.process_content(blocks)

            assert len(result) == 1
            assert result[0]["type"] == "text"
            assert "Audio" in result[0]["text"]
            assert "Reference:" in result[0]["text"]

    @pytest.mark.asyncio
    async def test_audio_retrieval(self, content_manager):
        async with content_manager:
            blocks = [{
                "type": "audio",
                "data": "YXVkaW9kYXRh",
                "mimeType": "audio/mp3"
            }]
            result = await content_manager.process_content(blocks)

            import re
            match = re.search(r'Reference: ([a-f0-9-]+)', result[0]["text"])
            ref_id = match.group(1)

            retrieved = content_manager.get_content(ref_id)
            assert retrieved["type"] == "audio"
            assert retrieved["data"] == "YXVkaW9kYXRh"
            assert retrieved["mimeType"] == "audio/mp3"


class TestContentManagerStorage:
    @pytest.mark.asyncio
    async def test_list_refs(self, content_manager):
        async with content_manager:
            blocks = [
                {"type": "audio", "data": "YQ==", "mimeType": "audio/wav"},
                {"type": "audio", "data": "Yg==", "mimeType": "audio/wav"},
            ]
            await content_manager.process_content(blocks)

            refs = content_manager.list_refs()
            assert len(refs) == 2

    @pytest.mark.asyncio
    async def test_delete_content(self, content_manager):
        async with content_manager:
            blocks = [{"type": "audio", "data": "YQ==", "mimeType": "audio/wav"}]
            result = await content_manager.process_content(blocks)

            import re
            match = re.search(r'Reference: ([a-f0-9-]+)', result[0]["text"])
            ref_id = match.group(1)

            assert content_manager.delete_content(ref_id) is True
            assert content_manager.delete_content(ref_id) is False

    @pytest.mark.asyncio
    async def test_clear_storage(self, content_manager):
        async with content_manager:
            blocks = [
                {"type": "audio", "data": "YQ==", "mimeType": "audio/wav"},
                {"type": "audio", "data": "Yg==", "mimeType": "audio/wav"},
            ]
            await content_manager.process_content(blocks)

            count = content_manager.clear_storage()
            assert count == 2
            assert len(content_manager.list_refs()) == 0

    @pytest.mark.asyncio
    async def test_get_nonexistent_content(self, content_manager):
        async with content_manager:
            with pytest.raises(FileNotFoundError):
                content_manager.get_content("nonexistent-ref-id")

    @pytest.mark.asyncio
    async def test_invalid_chunk_index(self, content_manager):
        async with content_manager:
            long_text = "Word " * 200
            blocks = [{"type": "text", "text": long_text}]
            result = await content_manager.process_content(blocks)

            import re
            match = re.search(r'Reference: ([a-f0-9-]+)', result[0]["text"])
            ref_id = match.group(1)

            with pytest.raises(IndexError):
                content_manager.get_content(ref_id, chunk_index=999)


class TestContentManagerPassthrough:
    @pytest.mark.asyncio
    async def test_unknown_type_passthrough(self, content_manager):
        async with content_manager:
            blocks = [{"type": "custom", "data": "something"}]
            result = await content_manager.process_content(blocks)
            assert result == blocks

    @pytest.mark.asyncio
    async def test_mixed_content(self, content_manager):
        async with content_manager:
            blocks = [
                {"type": "text", "text": "Short text"},
                {"type": "image", "data": "aW1n", "mimeType": "image/png"},
                {"type": "resource_link", "uri": "file:///test"},
            ]
            result = await content_manager.process_content(blocks)

            assert len(result) == 3
            assert result[0]["text"] == "Short text"
            assert "Reference:" in result[1]["text"]
            assert result[2]["type"] == "resource_link"
