import json
import base64
from uuid import uuid4
from pathlib import Path
from typing import List, Dict, Any, Optional, Self

import tiktoken
from openai import AsyncOpenAI

from ..log import logger


class ContentManager:
    def __init__(
        self,
        storage_path: str,
        openai_api_key: str,
        max_tokens: int = 2000,
        describe_images: bool = True,
        vision_model: str = "gpt-4.1-mini"
    ):
        self.storage_path = Path(storage_path)
        self.max_tokens = max_tokens
        self.describe_images = describe_images
        self.vision_model = vision_model
        self.openai_api_key = openai_api_key
        self.encoder = tiktoken.get_encoding("cl100k_base")

    async def __aenter__(self) -> Self:
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.client = AsyncOpenAI(api_key=self.openai_api_key)
        logger.info(f"ContentManager initialized with storage at {self.storage_path}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.close()
        logger.info("ContentManager closed")

    async def process_content(self, content_blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        processed = []
        for block in content_blocks:
            block_type = block.get("type")
            match block_type:
                case "text":
                    processed.extend(await self._handle_text(block))
                case "image":
                    processed.extend(await self._handle_image(block))
                case "audio":
                    processed.extend(await self._handle_audio(block))
                case _:
                    processed.append(block)
        return processed

    async def _handle_text(self, block: Dict[str, Any]) -> List[Dict[str, Any]]:
        text = block.get("text", "")
        tokens = self.encoder.encode(text)

        if len(tokens) <= self.max_tokens:
            return [block]

        chunks = self._chunk_tokens(tokens)
        ref_id = self._store_content({
            "type": "text",
            "chunks": [self.encoder.decode(chunk) for chunk in chunks],
            "total_chunks": len(chunks),
            "total_tokens": len(tokens)
        })

        preview = self.encoder.decode(tokens[:self.max_tokens])
        return [{
            "type": "text",
            "text": (
                f"{preview}\n\n"
                f"---\n"
                f"[Content truncated: {len(chunks)} chunks, {len(tokens)} tokens total]\n"
                f"[Reference: {ref_id}]\n"
                f"[Use get_content(ref_id=\"{ref_id}\") to retrieve full content or specific chunks]"
            )
        }]

    async def _handle_image(self, block: Dict[str, Any]) -> List[Dict[str, Any]]:
        data = block.get("data", "")
        mime_type = block.get("mimeType", "image/png")

        ref_id = self._store_content({
            "type": "image",
            "data": data,
            "mimeType": mime_type
        })

        description = "Image stored"
        if self.describe_images:
            description = await self._describe_image(data, mime_type)

        return [{
            "type": "text",
            "text": (
                f"[Image: {description}]\n"
                f"[Reference: {ref_id}]\n"
                f"[Use get_content(ref_id=\"{ref_id}\") to retrieve the image]"
            )
        }]

    async def _handle_audio(self, block: Dict[str, Any]) -> List[Dict[str, Any]]:
        data = block.get("data", "")
        mime_type = block.get("mimeType", "audio/wav")

        ref_id = self._store_content({
            "type": "audio",
            "data": data,
            "mimeType": mime_type
        })

        return [{
            "type": "text",
            "text": (
                f"[Audio file stored]\n"
                f"[MimeType: {mime_type}]\n"
                f"[Reference: {ref_id}]\n"
                f"[Use get_content(ref_id=\"{ref_id}\") to retrieve the audio]"
            )
        }]

    def _chunk_tokens(self, tokens: List[int]) -> List[List[int]]:
        chunks = []
        for i in range(0, len(tokens), self.max_tokens):
            chunks.append(tokens[i:i + self.max_tokens])
        return chunks

    def _store_content(self, content: Dict[str, Any]) -> str:
        ref_id = str(uuid4())
        file_path = self.storage_path / f"{ref_id}.json"
        with open(file_path, "w") as f:
            json.dump(content, f)
        logger.info(f"Stored content with ref_id: {ref_id}")
        return ref_id

    async def _describe_image(self, base64_data: str, mime_type: str) -> str:
        try:
            data_url = f"data:{mime_type};base64,{base64_data}"
            response = await self.client.chat.completions.create(
                model=self.vision_model,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Describe this image concisely 5-10 sentences. Focus on key visual elements and purpose."
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url}
                        }
                    ]
                }],
                max_tokens=512
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Failed to describe image: {e}")
            return "Image (description unavailable)"

    def get_content(self, ref_id: str, chunk_index: Optional[int] = None) -> Dict[str, Any]:
        file_path = self.storage_path / f"{ref_id}.json"
        if not file_path.exists():
            raise FileNotFoundError(f"Content not found for ref_id: {ref_id}")

        with open(file_path, "r") as f:
            content = json.load(f)

        content_type = content.get("type")

        if content_type == "text":
            chunks = content.get("chunks", [])
            if chunk_index is not None:
                if chunk_index < 0 or chunk_index >= len(chunks):
                    raise IndexError(f"Chunk index {chunk_index} out of range (0-{len(chunks)-1})")
                return {
                    "type": "text",
                    "text": chunks[chunk_index],
                    "chunk_index": chunk_index,
                    "total_chunks": len(chunks)
                }
            return {
                "type": "text",
                "text": "".join(chunks),
                "total_chunks": len(chunks)
            }

        elif content_type == "image":
            return {
                "type": "image",
                "data": content.get("data"),
                "mimeType": content.get("mimeType", "image/png")
            }

        elif content_type == "audio":
            return {
                "type": "audio",
                "data": content.get("data"),
                "mimeType": content.get("mimeType", "audio/wav")
            }

        return content

    def list_refs(self) -> List[str]:
        return [f.stem for f in self.storage_path.glob("*.json")]

    def delete_content(self, ref_id: str) -> bool:
        file_path = self.storage_path / f"{ref_id}.json"
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Deleted content with ref_id: {ref_id}")
            return True
        return False

    def clear_storage(self) -> int:
        count = 0
        for f in self.storage_path.glob("*.json"):
            f.unlink()
            count += 1
        logger.info(f"Cleared {count} items from content storage")
        return count
