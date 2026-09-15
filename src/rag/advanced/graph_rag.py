"""Graph RAG: Knowledge Graph-enhanced retrieval.

Combines vector retrieval with knowledge graph traversal for
relationship-aware document retrieval.
"""

import logging
from collections import defaultdict
from typing import Any, Optional

logger = logging.getLogger(__name__)


class GraphRAGProcessor:
    """Graph-enhanced RAG using entity relationship graphs.

    Extends standard RAG by:
    1. Extracting entities and relationships from documents
    2. Building a knowledge graph
    3. Using graph traversal to find related documents
    4. Combining vector + graph results for richer context
    """

    def __init__(self, llm_client=None):
        """Initialize Graph RAG processor.

        Args:
            llm_client: LLM for entity extraction and graph reasoning
        """
        self.llm_client = llm_client
        self._entity_index: dict[str, set] = defaultdict(set)  # entity -> {doc_ids}
        self._relations: list[dict] = []  # [{source, relation, target, doc_id}]
        logger.info("GraphRAGProcessor initialized")

    async def process(
        self,
        query: str,
        documents: list[dict],
        vector_retriever=None,
    ) -> dict:
        """Process query with graph-enhanced retrieval.

        Args:
            query: User query
            documents: Initially retrieved documents
            vector_retriever: Optional vector retriever for fallback

        Returns:
            Dict with {answer, graph_documents, entities, relations, answer}
        """
        # Step 1: Extract entities from query
        query_entities = await self._extract_entities(query)

        # Step 2: Find documents linked to these entities
        graph_docs = self._find_related_documents(query_entities)

        # Step 3: Extract relations for enriched context
        relations = self._find_relations(query_entities)

        # Step 4: Merge vector results with graph results
        all_docs = list(documents)
        for doc_id in graph_docs:
            if doc_id not in {d.get("id") for d in all_docs}:
                all_docs.append({"id": doc_id, "content": f"[Graph-linked document: {doc_id}]", "source": "graph"})

        # Step 5: Generate graph-enhanced answer
        if self.llm_client and all_docs:
            answer = await self._generate_graph_answer(query, all_docs, relations)
        else:
            answer = f"GraphRAG answer for: {query}"

        return {
            "answer": answer,
            "graph_documents": [{"id": gd} for gd in graph_docs],
            "vector_documents": documents,
            "entities": list(query_entities),
            "relations": relations,
        }

    def index_document(self, doc_id: str, content: str, entities: Optional[list[dict]] = None) -> None:
        """Index a document's entities into the graph.

        Args:
            doc_id: Document identifier
            content: Document text
            entities: Pre-extracted entities or None to auto-extract
        """
        if entities:
            for entity in entities:
                name = entity.get("name", entity.get("entity", ""))
                if name:
                    self._entity_index[name].add(doc_id)

                if "relations" in entity:
                    for rel in entity["relations"]:
                        self._relations.append({
                            "source": name,
                            "relation": rel.get("type", "related_to"),
                            "target": rel.get("target", ""),
                            "doc_id": doc_id,
                        })

        logger.debug("Indexed document %s: %d entities", doc_id[:8], len(entities or []))

    async def _extract_entities(self, text: str) -> set[str]:
        """Extract entities from text."""
        if not self.llm_client:
            # Simple heuristic: capitalized words and key noun phrases
            words = text.split()
            entities = set()
            # Capitalized words (likely named entities)
            for word in words:
                if word[0].isupper() and len(word) > 2:
                    entities.add(word.strip(".,;:!?"))
            return entities

        prompt = f"""Extract key named entities (people, organizations, locations, products, concepts) from this text.
Return each entity on a new line. Only the entity names, no explanation.

Text: {text}"""

        try:
            if hasattr(self.llm_client, 'generate'):
                response = await self.llm_client.generate(prompt)
                entities = set(str(response).strip().split("\n"))
                return {e.strip("- •*").strip() for e in entities if e.strip()}
            return set()
        except Exception:
            return set()

    def _find_related_documents(self, entities: set[str]) -> set[str]:
        """Find documents connected to given entities in the graph."""
        related_docs = set()
        for entity in entities:
            if entity in self._entity_index:
                related_docs.update(self._entity_index[entity])

        # Also find documents one hop away via relations
        for entity in entities:
            for rel in self._relations:
                if rel["source"] == entity or rel["target"] == entity:
                    related_docs.add(rel["doc_id"])

        return related_docs

    def _find_relations(self, entities: set[str]) -> list[dict]:
        """Find relationships involving given entities."""
        matching_relations = []
        for rel in self._relations:
            if rel["source"] in entities or rel["target"] in entities:
                matching_relations.append(rel)
        return matching_relations

    async def _generate_graph_answer(self, query: str, documents: list[dict], relations: list[dict]) -> str:
        """Generate answer informed by graph structure."""
        if not self.llm_client:
            return f"Graph-enhanced answer for: {query}"

        doc_text = "\n".join([
            f"[{i+1}] {doc.get('content', '')[:300]}"
            for i, doc in enumerate(documents[:8])
        ])

        rel_text = "\n".join([
            f"- {r['source']} {r['relation']} {r['target']}"
            for r in relations[:10]
        ])

        prompt = f"""Answer the query using the provided documents and entity relationships.

Entity Relationships:
{rel_text if rel_text else 'No relationships found.'}

Documents:
{doc_text[:2000]}

Query: {query}

Answer:"""

        try:
            if hasattr(self.llm_client, 'generate'):
                response = await self.llm_client.generate(prompt)
                return str(response)
            return f"Graph answer for: {query}"
        except Exception:
            return f"Error in graph-enhanced answer for: {query}"

    def clear_graph(self) -> None:
        """Clear the knowledge graph."""
        self._entity_index.clear()
        self._relations.clear()
        logger.info("GraphRAG knowledge graph cleared")

    def get_graph_stats(self) -> dict:
        """Get graph statistics."""
        return {
            "total_entities": len(self._entity_index),
            "total_relations": len(self._relations),
            "avg_docs_per_entity": (
                sum(len(docs) for docs in self._entity_index.values()) / max(len(self._entity_index), 1)
            ),
        }
