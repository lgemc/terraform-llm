"""Hybrid search combining BM25 and semantic embeddings."""

import json
import pickle
import logging
from pathlib import Path
from typing import Optional

import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from terraform_llm.tools.search.schema import TerraformDoc

logger = logging.getLogger(__name__)


class HybridSearch:
    """
    Hybrid search engine combining BM25 (keyword) and semantic (embedding) search.

    Uses Reciprocal Rank Fusion (RRF) to merge results from both retrieval methods.
    """

    def __init__(self, index_dir: Path):
        """
        Load pre-built search indices.

        Args:
            index_dir: Directory containing index files (bm25.pkl, embeddings.npz, etc.)
        """
        self.index_dir = Path(index_dir)

        # Load index metadata
        with open(self.index_dir / "index_metadata.json") as f:
            self.metadata = json.load(f)

        logger.info(f"Loading hybrid search index from {index_dir}")
        logger.info(f"Index: {self.metadata['num_documents']} docs, {self.metadata['num_chunks']} chunks")

        # Load BM25
        with open(self.index_dir / "bm25.pkl", "rb") as f:
            self.bm25: BM25Okapi = pickle.load(f)

        # Load embeddings
        embeddings_data = np.load(self.index_dir / "embeddings.npz")
        self.embeddings = embeddings_data["embeddings"]
        self.chunk_to_doc_idx = embeddings_data["chunk_to_doc_idx"]

        # Load documents
        with open(self.index_dir / "documents.json") as f:
            docs_data = json.load(f)
            self.documents = [TerraformDoc.from_dict(d) for d in docs_data]

        # Load chunks
        with open(self.index_dir / "chunks.json") as f:
            self.chunks = json.load(f)

        # Load embedding model
        embedding_model_name = self.metadata["embedding_model"]
        logger.info(f"Loading embedding model: {embedding_model_name}")
        self.embedding_model = SentenceTransformer(embedding_model_name)

        logger.info("Hybrid search index loaded successfully")

    def search(
        self,
        query: str,
        top_k: int = 5,
        bm25_weight: float = 0.5,
        semantic_weight: float = 0.5,
        provider_filter: Optional[str] = None,
    ) -> list[dict]:
        """
        Perform hybrid search combining BM25 and semantic search.

        Args:
            query: Search query
            top_k: Number of results to return
            bm25_weight: Weight for BM25 scores (default 0.5)
            semantic_weight: Weight for semantic scores (default 0.5)
            provider_filter: Optional provider filter (e.g., "aws")

        Returns:
            List of search results with metadata
        """
        logger.debug(f"Searching for: {query} (top_k={top_k}, provider={provider_filter})")

        # BM25 search
        bm25_scores = self._bm25_search(query)

        # Semantic search
        semantic_scores = self._semantic_search(query)

        # Apply provider filter
        if provider_filter:
            filtered_indices = [
                i for i in range(len(self.documents))
                if self.documents[i].provider == provider_filter
            ]
        else:
            filtered_indices = list(range(len(self.documents)))

        # Reciprocal Rank Fusion (RRF)
        rrf_scores = self._reciprocal_rank_fusion(
            bm25_scores,
            semantic_scores,
            filtered_indices,
            bm25_weight,
            semantic_weight,
        )

        # Get top-k results
        top_indices = np.argsort(rrf_scores)[::-1][:top_k]

        # Format results
        results = []
        for idx in top_indices:
            if rrf_scores[idx] == 0:
                continue  # Skip zero-score results

            doc = self.documents[idx]
            results.append({
                "resource_id": doc.resource_id,
                "provider": doc.provider,
                "subcategory": doc.subcategory,
                "title": doc.page_title,
                "description": doc.description,
                "overview": doc.overview,
                "examples": doc.examples[:2],  # Include top 2 examples
                "arguments_required": doc.arguments_required,
                "arguments_optional": doc.arguments_optional,
                "argument_descriptions": doc.argument_descriptions,
                "attributes": doc.attributes,
                "score": float(rrf_scores[idx]),
            })

        logger.debug(f"Found {len(results)} results")
        return results

    def _bm25_search(self, query: str) -> np.ndarray:
        """
        Perform BM25 keyword search.

        Returns:
            Array of BM25 scores for each document
        """
        tokenized_query = query.lower().split()
        doc_scores = self.bm25.get_scores(tokenized_query)
        return doc_scores

    def _semantic_search(self, query: str) -> np.ndarray:
        """
        Perform semantic search using embeddings.

        Returns:
            Array of semantic similarity scores for each document (aggregated from chunks)
        """
        # Encode query
        query_embedding = self.embedding_model.encode(query)

        # Compute cosine similarity with all chunks
        chunk_scores = np.dot(self.embeddings, query_embedding) / (
            np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(query_embedding)
        )

        # Aggregate chunk scores to document scores (use max score per document)
        doc_scores = np.zeros(len(self.documents))
        for chunk_idx, doc_idx in enumerate(self.chunk_to_doc_idx):
            doc_scores[doc_idx] = max(doc_scores[doc_idx], chunk_scores[chunk_idx])

        return doc_scores

    def _reciprocal_rank_fusion(
        self,
        bm25_scores: np.ndarray,
        semantic_scores: np.ndarray,
        filtered_indices: list[int],
        bm25_weight: float = 0.5,
        semantic_weight: float = 0.5,
        k: int = 60,
    ) -> np.ndarray:
        """
        Merge BM25 and semantic scores using Reciprocal Rank Fusion.

        RRF formula: score = Σ w_i / (k + rank_i)

        Args:
            bm25_scores: BM25 scores for all documents
            semantic_scores: Semantic scores for all documents
            filtered_indices: Indices of documents to consider
            bm25_weight: Weight for BM25 rankings
            semantic_weight: Weight for semantic rankings
            k: RRF constant (default 60)

        Returns:
            Array of fused scores for each document
        """
        num_docs = len(self.documents)
        rrf_scores = np.zeros(num_docs)

        # Filter scores
        filtered_bm25 = np.zeros(num_docs)
        filtered_semantic = np.zeros(num_docs)
        filtered_bm25[filtered_indices] = bm25_scores[filtered_indices]
        filtered_semantic[filtered_indices] = semantic_scores[filtered_indices]

        # Get rankings (argsort gives indices sorted by score, reversed for descending)
        bm25_ranks = np.argsort(filtered_bm25)[::-1]
        semantic_ranks = np.argsort(filtered_semantic)[::-1]

        # Build rank position maps
        bm25_rank_map = {doc_idx: rank for rank, doc_idx in enumerate(bm25_ranks)}
        semantic_rank_map = {doc_idx: rank for rank, doc_idx in enumerate(semantic_ranks)}

        # Compute RRF scores
        for doc_idx in filtered_indices:
            bm25_rank = bm25_rank_map[doc_idx]
            semantic_rank = semantic_rank_map[doc_idx]

            rrf_scores[doc_idx] = (
                bm25_weight / (k + bm25_rank) +
                semantic_weight / (k + semantic_rank)
            )

        return rrf_scores

    def format_result_for_llm(self, result: dict) -> str:
        """
        Format a search result for LLM consumption.

        Args:
            result: Search result dictionary

        Returns:
            Formatted string with resource documentation
        """
        lines = [
            f"Resource: {result['resource_id']}",
            f"Category: {result['subcategory']}",
            f"Description: {result['description']}",
            "",
        ]

        if result.get("overview"):
            lines.append(f"Overview:\n{result['overview']}")
            lines.append("")

        # Arguments
        if result.get("arguments_required"):
            lines.append("Required Arguments:")
            for arg in result["arguments_required"]:
                desc = result["argument_descriptions"].get(arg, "")
                lines.append(f"  - {arg}: {desc}")
            lines.append("")

        if result.get("arguments_optional"):
            lines.append("Optional Arguments:")
            for arg in result["arguments_optional"][:5]:  # Limit to 5 optional args
                desc = result["argument_descriptions"].get(arg, "")
                lines.append(f"  - {arg}: {desc}")
            lines.append("")

        # Examples
        if result.get("examples"):
            lines.append("Examples:")
            for example in result["examples"][:2]:  # Limit to 2 examples
                lines.append(f"\n{example.get('title', 'Example')}:")
                lines.append(example.get("code", ""))
            lines.append("")

        # Attributes
        if result.get("attributes"):
            lines.append("Exported Attributes:")
            for attr in result["attributes"][:5]:
                desc = result.get("attribute_descriptions", {}).get(attr, "")
                lines.append(f"  - {attr}: {desc}")

        return "\n".join(lines)
