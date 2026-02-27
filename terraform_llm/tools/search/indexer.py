"""Document indexer for Terraform provider documentation."""

import re
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


class DocumentIndexer:
    """
    Builds BM25 and semantic embeddings index from Terraform provider docs.

    The indexer parses markdown files, extracts structured information,
    and creates hybrid search indices (BM25 + embeddings).
    """

    def __init__(self, embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"):
        """
        Initialize indexer.

        Args:
            embedding_model: Sentence transformer model name
        """
        self.embedding_model_name = embedding_model
        self.embedding_model: Optional[SentenceTransformer] = None
        self.docs: list[TerraformDoc] = []

    def parse_markdown_file(self, file_path: Path, provider: str) -> Optional[TerraformDoc]:
        """
        Parse a single Terraform resource markdown file.

        Args:
            file_path: Path to markdown file
            provider: Provider name (e.g., "aws")

        Returns:
            TerraformDoc or None if parsing fails
        """
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to read {file_path}: {e}")
            return None

        # Extract resource ID from filename (e.g., "lambda_alias.html.markdown" -> "aws_lambda_alias")
        filename = file_path.stem.replace(".html", "")
        resource_id = f"{provider}_{filename}"

        # Parse frontmatter metadata
        subcategory = ""
        page_title = ""
        description = ""

        # Simple frontmatter parser
        lines = content.split("\n")
        if lines and lines[0].strip().startswith("---"):
            frontmatter_end = -1
            for i, line in enumerate(lines[1:], start=1):
                if line.strip() == "---":
                    frontmatter_end = i
                    break
                # Parse key: value
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip().lower()
                    value = value.strip().strip('"')
                    if key == "subcategory":
                        subcategory = value
                    elif key == "page_title":
                        page_title = value
                    elif key == "description":
                        description = value

            # Remove frontmatter from content
            if frontmatter_end > 0:
                content = "\n".join(lines[frontmatter_end + 1:])

        # Extract sections
        overview = self._extract_overview(content)
        examples = self._extract_examples(content)
        args_required, args_optional, arg_descriptions = self._extract_arguments(content)
        attributes, attr_descriptions = self._extract_attributes(content)

        return TerraformDoc(
            resource_id=resource_id,
            provider=provider,
            subcategory=subcategory,
            page_title=page_title or f"{provider.upper()}: {resource_id}",
            description=description,
            full_text=content,
            overview=overview,
            examples=examples,
            arguments_required=args_required,
            arguments_optional=args_optional,
            argument_descriptions=arg_descriptions,
            attributes=attributes,
            attribute_descriptions=attr_descriptions,
            source_file=str(file_path),
        )

    def _extract_overview(self, content: str) -> str:
        """Extract overview/introduction section."""
        # Find content between resource title and first major section
        lines = content.split("\n")
        overview_lines = []
        started = False

        for line in lines:
            # Start collecting after resource title
            if re.match(r"^#+ Resource:", line):
                started = True
                continue
            # Stop at next major section
            if started and re.match(r"^#+ ", line):
                break
            if started and line.strip():
                overview_lines.append(line)

        return "\n".join(overview_lines).strip()

    def _extract_examples(self, content: str) -> list[dict[str, str]]:
        """Extract example code blocks with titles."""
        examples = []
        lines = content.split("\n")
        current_title = None
        in_code_block = False
        code_lines = []

        for line in lines:
            # Detect example section headers
            if re.match(r"^##+ .*(Example|Usage)", line, re.IGNORECASE):
                current_title = line.lstrip("#").strip()
                continue

            # Code block start
            if line.strip().startswith("```"):
                if in_code_block:
                    # Code block end
                    if current_title and code_lines:
                        examples.append({
                            "title": current_title,
                            "code": "\n".join(code_lines),
                        })
                    code_lines = []
                    in_code_block = False
                else:
                    in_code_block = True
                continue

            if in_code_block:
                code_lines.append(line)

        return examples

    def _extract_arguments(self, content: str) -> tuple[list[str], list[str], dict[str, str]]:
        """
        Extract required/optional arguments and their descriptions.

        Returns:
            (required_args, optional_args, descriptions)
        """
        required = []
        optional = []
        descriptions = {}

        lines = content.split("\n")
        in_args_section = False

        for line in lines:
            # Detect argument reference section
            if re.match(r"^##+ Argument Reference", line, re.IGNORECASE):
                in_args_section = True
                continue
            # Stop at next major section
            if in_args_section and re.match(r"^##+ ", line):
                break

            if in_args_section:
                # Match patterns like: "- `name` - (Required) Description"
                match = re.match(r"^\s*[-*]\s*`?([a-z_]+)`?\s*-\s*\((Required|Optional)\)\s*(.+)", line, re.IGNORECASE)
                if match:
                    arg_name = match.group(1)
                    is_required = match.group(2).lower() == "required"
                    desc = match.group(3).strip()

                    if is_required:
                        required.append(arg_name)
                    else:
                        optional.append(arg_name)
                    descriptions[arg_name] = desc

        return required, optional, descriptions

    def _extract_attributes(self, content: str) -> tuple[list[str], dict[str, str]]:
        """
        Extract exported attributes and their descriptions.

        Returns:
            (attributes, descriptions)
        """
        attributes = []
        descriptions = {}

        lines = content.split("\n")
        in_attrs_section = False

        for line in lines:
            # Detect attributes section
            if re.match(r"^##+ Attribute Reference", line, re.IGNORECASE):
                in_attrs_section = True
                continue
            # Stop at next major section
            if in_attrs_section and re.match(r"^##+ ", line):
                break

            if in_attrs_section:
                # Match patterns like: "- `arn` - Description"
                match = re.match(r"^\s*[-*]\s*`?([a-z_]+)`?\s*-\s*(.+)", line, re.IGNORECASE)
                if match:
                    attr_name = match.group(1)
                    desc = match.group(2).strip()
                    attributes.append(attr_name)
                    descriptions[attr_name] = desc

        return attributes, descriptions

    def index_directory(self, docs_dir: Path, provider: str, file_pattern: str = "*.markdown") -> int:
        """
        Index all markdown files in a directory.

        Args:
            docs_dir: Directory containing markdown files
            provider: Provider name (e.g., "aws")
            file_pattern: Glob pattern for markdown files

        Returns:
            Number of documents indexed
        """
        logger.info(f"Indexing docs from {docs_dir} (provider={provider})")
        markdown_files = list(docs_dir.rglob(file_pattern))
        logger.info(f"Found {len(markdown_files)} markdown files")

        for file_path in markdown_files:
            doc = self.parse_markdown_file(file_path, provider)
            if doc:
                self.docs.append(doc)

        logger.info(f"Successfully indexed {len(self.docs)} documents")
        return len(self.docs)

    def build_indices(self, output_dir: Path):
        """
        Build BM25 and embedding indices from parsed documents.

        Args:
            output_dir: Directory to save indices
        """
        if not self.docs:
            raise ValueError("No documents to index. Call index_directory() first.")

        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Building BM25 index...")
        # Tokenize documents for BM25 (use full text + resource ID for better matching)
        tokenized_docs = []
        for doc in self.docs:
            # Combine resource ID and full text for comprehensive matching
            text = f"{doc.resource_id} {doc.subcategory} {doc.full_text}"
            tokens = text.lower().split()
            tokenized_docs.append(tokens)

        bm25 = BM25Okapi(tokenized_docs)

        # Save BM25 index
        with open(output_dir / "bm25.pkl", "wb") as f:
            pickle.dump(bm25, f)
        logger.info(f"Saved BM25 index to {output_dir / 'bm25.pkl'}")

        # Build embeddings
        logger.info(f"Loading embedding model: {self.embedding_model_name}")
        self.embedding_model = SentenceTransformer(self.embedding_model_name)

        # Generate embeddings for all document chunks
        all_chunks = []
        chunk_to_doc_idx = []  # Map chunk index to document index

        for doc_idx, doc in enumerate(self.docs):
            chunks = doc.get_searchable_chunks()
            for chunk in chunks:
                all_chunks.append(chunk["text"])
                chunk_to_doc_idx.append(doc_idx)

        logger.info(f"Encoding {len(all_chunks)} chunks...")
        embeddings = self.embedding_model.encode(all_chunks, show_progress_bar=True)

        # Save embeddings
        np.savez_compressed(
            output_dir / "embeddings.npz",
            embeddings=embeddings,
            chunk_to_doc_idx=chunk_to_doc_idx,
        )
        logger.info(f"Saved embeddings to {output_dir / 'embeddings.npz'}")

        # Save document metadata
        docs_data = [doc.to_dict() for doc in self.docs]
        with open(output_dir / "documents.json", "w") as f:
            json.dump(docs_data, f, indent=2)
        logger.info(f"Saved {len(docs_data)} documents to {output_dir / 'documents.json'}")

        # Save chunk metadata
        chunks_data = []
        for doc_idx, doc in enumerate(self.docs):
            for chunk in doc.get_searchable_chunks():
                chunks_data.append({
                    "doc_idx": doc_idx,
                    "resource_id": doc.resource_id,
                    "type": chunk["type"],
                    "title": chunk["title"],
                    "text": chunk["text"],
                })

        with open(output_dir / "chunks.json", "w") as f:
            json.dump(chunks_data, f, indent=2)
        logger.info(f"Saved {len(chunks_data)} chunks to {output_dir / 'chunks.json'}")

        # Save index metadata
        metadata = {
            "num_documents": len(self.docs),
            "num_chunks": len(all_chunks),
            "embedding_model": self.embedding_model_name,
            "provider": self.docs[0].provider if self.docs else "unknown",
        }
        with open(output_dir / "index_metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"Index build complete: {len(self.docs)} docs, {len(all_chunks)} chunks")
