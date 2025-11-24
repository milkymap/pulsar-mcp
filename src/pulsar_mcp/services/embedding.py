from openai import AsyncOpenAI
from openai.types.create_embedding_response import CreateEmbeddingResponse
from openai.types.embedding import Embedding

from typing import List, Self
from ..log import logger

class EmbeddingService:
    def __init__(self, api_key: str, embedding_model_name:str, dimension:int):
        self.api_key = api_key
        self.embedding_model_name = embedding_model_name
        self.dimension = dimension

    async def __aenter__(self) -> Self:
        self.client = AsyncOpenAI(api_key=self.api_key)
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            logger.error(f"Exception in EmbeddingService context manager: {exc_value}")
            logger.exception(traceback)

    async def create_embedding(self, texts: list[str]) -> List[List[float]]:
        # must use tiktoken to estimate token per input... max token per input <= 8192
        # total input tokens per request <= 300_000 tokens 
        # a future implementation must handle chunking of inputs that exceed these limits
        # and batching of requests to stay within rate limits
        response:CreateEmbeddingResponse = await self.client.embeddings.create(
            input=texts,
            model=self.embedding_model_name,
            dimensions=self.dimension
        )
        embeddings = [item.embedding for item in response.data]
        return embeddings
    
    def inject_base_into_corpus(self, base_embedding:List[float], corpus_embeddings:List[List[float]], alpha:float=0.1) -> List[List[float]]:
        beta = 1.0 - alpha
        injected_corpus = []
        
        for corpus_vec in corpus_embeddings:
            # alpha * base + beta * corpus
            injected = [
                alpha * base_embedding[i] + beta * corpus_vec[i] 
                for i in range(len(base_embedding))
            ]
            injected_corpus.append(injected)
        
        return injected_corpus
