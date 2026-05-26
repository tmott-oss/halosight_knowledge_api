"""
Halosight Knowledge MCP Server

Connects Claude Desktop to the Halosight Knowledge API via FastMCP.
Runs locally — Claude calls the tools, which query the Cloud Run API.

Usage:
    python3 mcp_server.py
"""

import os
import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

API_BASE_URL = os.environ.get(
    "HALOSIGHT_API_URL",
    "https://halosight-knowledge-api-691841119073.us-central1.run.app"
)
API_KEY = os.environ.get("HALOSIGHT_API_KEY", "")

mcp = FastMCP("Halosight Knowledge")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }


@mcp.tool()
def search_knowledge(query: str, top_k: int = 5) -> str:
    """
    Search the Halosight knowledge base using a plain-text question or topic.

    Use this tool whenever the user asks about:
    - Halosight's product, platform, or features
    - Sales methodology, discovery, objection handling, or qualification
    - ICP, personas, or target customers
    - Competitive positioning or competitors
    - Pricing, packaging, or implementation
    - Company context, messaging, or positioning
    - Case studies, customer examples, or use cases
    - Any internal Halosight knowledge

    Args:
        query: The question or topic to search for
        top_k: Number of results to return (default 5, max 20)

    Returns:
        Relevant knowledge base content ranked by similarity
    """
    with httpx.Client(timeout=30) as client:
        response = client.post(
            f"{API_BASE_URL}/search",
            headers=_headers(),
            json={"query": query, "top_k": top_k},
        )
        response.raise_for_status()
        data = response.json()

    results = data.get("results", [])
    if not results:
        return "No relevant content found in the knowledge base for that query."

    output = []
    for i, r in enumerate(results, 1):
        output.append(
            f"[{i}] {r['title']} ({r['folder']})\n"
            f"Similarity: {r['similarity']:.2f}\n\n"
            f"{r['content']}\n"
            f"{'─' * 60}"
        )

    return "\n\n".join(output)


@mcp.tool()
def list_knowledge_folders() -> str:
    """
    List all folders in the Halosight knowledge base.
    Use this to understand what topics are covered before searching.
    """
    with httpx.Client(timeout=30) as client:
        response = client.get(
            f"{API_BASE_URL}/documents",
            headers=_headers(),
        )
        response.raise_for_status()
        docs = response.json()

    from collections import Counter
    folders = Counter(d["folder"] for d in docs)

    lines = ["Halosight Knowledge Base — Folders:\n"]
    for folder, count in sorted(folders.items()):
        lines.append(f"  {folder} ({count} documents)")

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
