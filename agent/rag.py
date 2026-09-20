"""
RAG knowledge base: 5 governance documents embedded via Gemini and
stored in an in-memory ChromaDB collection. Ported from the MASTER CELL.
"""
import chromadb
from google import genai

from agent.config import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)

documents = [
    {"id": "doc1", "content": """Agent Governance Principles: Autonomous AI agents must operate within
    clearly defined boundaries. Key governance principles include bounded autonomy (agents
    should have explicit limits on actions they can take), audit trails (every agent decision
    must be logged and traceable), human oversight (high-stakes decisions must escalate to
    humans), and cost controls (token spend per agent run must be monitored and capped)."""},
    {"id": "doc2", "content": """Risks of Autonomous Agents: The primary risks include runaway loops
    (agents calling tools repeatedly without progress), prompt injection (malicious content
    in tool results hijacking agent behavior), cost explosion (unbounded token consumption),
    hallucination (agents confidently producing wrong outputs), and scope creep (agents
    taking actions beyond their intended purpose)."""},
    {"id": "doc3", "content": """Agent Observability Best Practices: Production agent systems require
    comprehensive observability including per-run cost tracking, tool call logging with
    inputs and outputs, latency measurement per agent step, error rate monitoring, and
    anomaly detection for unusual patterns. Without observability, debugging agent failures
    in production is nearly impossible."""},
    {"id": "doc4", "content": """Multi-Agent Coordination Patterns: Common patterns include the coordinator
    pattern (one agent delegates to specialists), the pipeline pattern (agents pass work
    sequentially), and the debate pattern (multiple agents propose solutions and vote).
    The coordinator pattern is most common in enterprise settings due to its clear
    accountability and auditability."""},
    {"id": "doc5", "content": """Token Cost Management for Agents: LLM token costs compound in agent
    systems because each tool call requires at least one API call. A 5-step agent task
    can cost 5-10x more than a single LLM call. Best practices include caching repeated
    tool results, using smaller models for routing decisions, implementing token budgets
    per run, and monitoring thought token consumption separately from response tokens."""}
]


def embed_texts(texts):
    embeddings = []
    for text in texts:
        result = client.models.embed_content(model="gemini-embedding-001", contents=text)
        embeddings.append(result.embeddings[0].values)
    return embeddings


class GeminiEmbeddingFunction(chromadb.EmbeddingFunction):
    def __call__(self, input):
        return embed_texts(input)


def build_knowledge_base():
    gemini_ef = GeminiEmbeddingFunction()
    chroma_client = chromadb.Client()
    collection = chroma_client.get_or_create_collection(name="governance_knowledge_base", embedding_function=gemini_ef)
    collection.add(ids=[d["id"] for d in documents], documents=[d["content"] for d in documents])
    print(f"Ingested {collection.count()} documents into ChromaDB")
    return collection


collection = build_knowledge_base()
