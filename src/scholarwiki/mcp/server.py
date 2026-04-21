from __future__ import annotations
"""MCP server entry point using the mcp Python package (stdio transport)."""
import json
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from ..config import load_config
from ..registry import load_registry
from .tools import search_wiki, read_page, read_style_page, read_source_pdf_section


def create_server(config_path: str = "config.yaml") -> Server:
    cfg = load_config(Path(config_path))
    wiki_dir = cfg.paths.wiki

    server = Server("scholarwiki")

    @server.list_tools()
    async def list_tools():
        return [
            Tool(
                name="wiki_search",
                description=(
                    "Search the ScholarWiki knowledge base for relevant concept pages, "
                    "design patterns, and paper source pages."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "max_results": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="wiki_concept",
                description=(
                    "Read a concept page from the knowledge base. "
                    "Contains synthesized findings across multiple papers."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Concept name or slug"},
                    },
                    "required": ["name"],
                },
            ),
            Tool(
                name="wiki_pattern",
                description=(
                    "Read a research design pattern. "
                    "Contains experimental templates synthesized from multiple papers."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Pattern name or slug"},
                    },
                    "required": ["name"],
                },
            ),
            Tool(
                name="wiki_style",
                description=(
                    "Read a writing style guide for a specific venue and topic. "
                    "Helps write papers in the conventions of that journal."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "venue": {"type": "string", "description": "Journal or conference name"},
                        "topic": {"type": "string", "description": "Research topic area"},
                    },
                    "required": ["venue"],
                },
            ),
            Tool(
                name="wiki_paper",
                description=(
                    "Read a paper's source page with metadata, summary, "
                    "and links to concept/pattern/style pages."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string", "description": "Paper slug (e.g., lopez2018_scvi)"},
                    },
                    "required": ["slug"],
                },
            ),
            Tool(
                name="wiki_suggest",
                description=(
                    "List papers referenced in the knowledge base but not yet downloaded. "
                    "Prioritized by reference count."
                ),
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="wiki_stats",
                description="Quick overview of the knowledge base: paper counts, concept pages, patterns, styles.",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="wiki_source_pdf",
                description=(
                    "Read a section of a paper's source PDF (L3 access). "
                    "Use when the wiki summary is insufficient and you need the original text. "
                    "Sections: abstract, introduction, methods, results, discussion, full, "
                    "or a page number (e.g., '3')."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "paper_slug": {
                            "type": "string",
                            "description": "Paper slug (e.g., 'lopez2018_scvi') or paper_id",
                        },
                        "section": {
                            "type": "string",
                            "description": (
                                "Section to read: abstract, introduction, methods, results, "
                                "discussion, full, or a 1-based page number"
                            ),
                            "default": "abstract",
                        },
                        "max_chars": {
                            "type": "integer",
                            "description": "Maximum characters to return (default 8000)",
                            "default": 8000,
                        },
                    },
                    "required": ["paper_slug"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        if name == "wiki_search":
            results = search_wiki(
                arguments["query"], wiki_dir, arguments.get("max_results", 5)
            )
            return [TextContent(type="text", text=json.dumps(results, indent=2))]

        elif name == "wiki_concept":
            content = read_page(wiki_dir, "concepts", arguments["name"])
            return [TextContent(
                type="text",
                text=content or f"No concept page found for '{arguments['name']}'.",
            )]

        elif name == "wiki_pattern":
            content = read_page(wiki_dir, "patterns", arguments["name"])
            return [TextContent(
                type="text",
                text=content or f"No pattern page found for '{arguments['name']}'.",
            )]

        elif name == "wiki_style":
            content = read_style_page(
                wiki_dir, arguments["venue"], arguments.get("topic", "")
            )
            return [TextContent(
                type="text",
                text=content or f"No style page found for venue='{arguments['venue']}'.",
            )]

        elif name == "wiki_paper":
            content = read_page(wiki_dir, "sources", arguments["slug"])
            return [TextContent(
                type="text",
                text=content or f"No source page found for '{arguments['slug']}'.",
            )]

        elif name == "wiki_suggest":
            sf = wiki_dir / "suggested_papers.md"
            text = sf.read_text(encoding="utf-8") if sf.exists() else "No suggested papers yet."
            return [TextContent(type="text", text=text)]

        elif name == "wiki_stats":
            reg = load_registry(cfg.paths.raw)
            from ..maintenance.stats import generate_stats
            return [TextContent(type="text", text=generate_stats(wiki_dir, reg))]

        elif name == "wiki_source_pdf":
            reg = load_registry(cfg.paths.raw)
            text = read_source_pdf_section(
                paper_slug=arguments["paper_slug"],
                section=arguments.get("section", "abstract"),
                raw_dir=cfg.paths.raw,
                registry=reg,
                max_chars=arguments.get("max_chars", 8000),
            )
            return [TextContent(type="text", text=text)]

        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    return server


async def run_server(config_path: str = "config.yaml") -> None:
    server = create_server(config_path)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream)
