# ScholarWiki

A command-line tool that transforms a folder of academic PDFs into an Obsidian-compatible knowledge wiki — automatically. Papers flow through a tracked state machine: ingested from an inbox, structured information extracted via GPT-4.1 batch jobs, and cross-paper concepts synthesized into wiki pages by GPT-5. The result is a browsable, interlinked vault of concepts, design patterns, writing guides, and paper summaries that grows richer with every batch.

## What it produces

```
wiki/
├── index.md                    # browsable entry point
├── log.md                      # run history
├── sources/                    # one page per paper: metadata + AI summary
│   ├── lopez2018_scvi.md
│   └── ...
├── concepts/                   # synthesized across papers, rewritten each run
│   ├── batch_correction.md
│   ├── variational_autoencoder.md
│   └── ...
├── patterns/                   # experimental design templates
│   ├── benchmarking_integration_methods.md
│   └── ...
├── writing/                    # style guides per journal/venue
│   ├── nature_methods_scrna.md
│   └── ...
└── suggested_papers.md         # papers referenced but not yet in the vault
```

Open the `wiki/` folder as an Obsidian vault. Graph view shows concept connections. Links between pages are real wikilinks (`[[concept_name]]`).

## Requirements

- Python 3.11+
- OpenAI API key (GPT-4.1 for extraction, GPT-5 for synthesis)
- Zotero account + API key (optional, for reference management)
- Papers sourced via [NEXUS](https://github.com/BDRL/nexus-paper-fetcher) or dropped manually into `manual_inbox/`

## Setup

```bash
git clone <repo>
cd ScholarWiki
pip install -e ".[dev]"

# Copy and edit config
cp config.yaml.example config.yaml  # or edit config.yaml directly

# Set API keys
export OPENAI_API_KEY=sk-...
export ZOTERO_API_KEY=...           # optional
export ZOTERO_LIBRARY_ID=...        # optional
```

## Quick start

```bash
# 1. Drop papers into nexus_inbox/ (from NEXUS) or manual_inbox/ (PDFs)

# 2. Run the full pipeline and walk away
scholarwiki process-batch --wait

# 3. Open wiki/ in Obsidian
```

That's it. `process-batch --wait` handles ingest, extraction, and synthesis end to end, polling OpenAI until every batch completes.

## How it works

### Pipeline stages

```
nexus_inbox/  ─┐
               ├─→ ingest ─→ raw/papers/ + registry.json
manual_inbox/ ─┘                    │
                                    │
                            extract (GPT-4.1 batch)
                                    │
                          staging/<paper_id>/*.json
                                    │
                            link (GPT-5 batch)
                                    │
                           wiki/concepts/  wiki/patterns/
                           wiki/writing/   wiki/sources/ (L2)
```

**Ingest** moves PDFs from inboxes to `raw/papers/`, creates stub source pages in `wiki/sources/`, and optionally pushes metadata to Zotero.

**Extract** submits each paper to five GPT-4.1 modules in a single OpenAI Batch API job: knowledge graph, roadmap edges, experimental design, writing structure, and logical argument. Results land in `staging/`.

**Link** reads all staged extractions, groups contributions by concept, and submits two synthesis batches: GPT-5 rewrites concept and design pattern pages; GPT-4.1 synthesizes writing style guides. Pages are full rewrites — they get richer and more nuanced with each paper added.

### State machine

Each paper tracks its own state in `registry.json`:

```
pending → queued → submitted → extracted → linked
```

The pipeline resumes from wherever it stopped. If a batch is still running when you check, `--continue` picks up where it left off.

## CLI reference

### `ingest`
```bash
scholarwiki ingest
```
Processes `nexus_inbox/` and `manual_inbox/`. Moves PDFs, creates registry entries and L1 source pages, syncs to Zotero.

### `extract`
```bash
scholarwiki extract --submit    # submit pending papers to GPT-4.1 batch
scholarwiki extract --status    # check batch progress
scholarwiki extract --collect   # download results when complete
scholarwiki extract --retry-failed  # resubmit any failed modules
```

### `link`
```bash
scholarwiki link               # submit GPT-5 + GPT-4.1 synthesis batches
scholarwiki link --status      # check batch progress
scholarwiki link --collect     # download results and backfill source pages
```

### `process-batch` — full pipeline automation
```bash
scholarwiki process-batch --wait            # run everything, poll until done
scholarwiki process-batch --no-wait         # submit and exit
scholarwiki process-batch --continue        # resume from current state
scholarwiki process-batch --dry-run         # show next step without executing
scholarwiki process-batch --timeout 8h      # override poll timeout (default: 6h)
```

### `status`
```bash
scholarwiki status
```
Quick summary of paper counts by state.

### `lint`
```bash
scholarwiki lint
```
Health-check the wiki. Reports:
- Orphan concept pages (no inbound links from source pages)
- Broken wikilinks (`[[target]]` with no matching page)
- Weak design patterns (fewer than 2 source papers)
- Missing source pages (linked in registry but file absent)
- Index drift (pages on disk not listed in `index.md`)

Exits with code 1 if any errors found.

### `stats`
```bash
scholarwiki stats
```
Knowledge base summary: paper counts by stage, concept/pattern/style page counts, suggested paper count.

### `serve-mcp`
```bash
scholarwiki serve-mcp
```
Starts an MCP server (stdio transport) that exposes the wiki to Claude Code. See [MCP integration](#mcp-integration) below.

### `zotero-sync`
```bash
scholarwiki zotero-sync
```
Retry syncing papers that failed to push to Zotero during ingest.

## Configuration

`config.yaml` (all paths relative to working directory where you run `scholarwiki`):

```yaml
paths:
  nexus_inbox: "./nexus_inbox"    # NEXUS --output-dir target
  manual_inbox: "./manual_inbox"  # drop PDFs here for manual ingest
  raw: "./raw"                    # papers/ and registry.json live here
  staging: "./staging"            # batch API outputs
  wiki: "./wiki"                  # Obsidian vault root

zotero:
  library_id: "${ZOTERO_LIBRARY_ID}"
  library_type: "user"
  api_key: "${ZOTERO_API_KEY}"

extraction:
  model: "gpt-4.1"
  max_papers_per_batch: 50
  max_tokens_per_request: 4096

linking:
  synthesis_model: "gpt-5"       # for concept + pattern pages
  style_model: "gpt-4.1"         # for writing style guides

sync:
  method: "rsync"
  local_path: "~/Obsidian/ScholarWiki/"
```

## MCP integration

ScholarWiki can serve as an MCP server so Claude Code can search and read the wiki during research sessions. When you ask "what do we know about batch correction?" it searches your actual paper collection.

### Setup

Create `.claude/mcp.json` in any project that should have wiki access:

```json
{
  "mcpServers": {
    "scholarwiki": {
      "command": "scholarwiki",
      "args": ["serve-mcp", "--config", "/path/to/ScholarWiki/config.yaml"]
    }
  }
}
```

### Available tools

| Tool | What it does |
|------|-------------|
| `wiki_search` | Keyword + fuzzy search across all wiki pages |
| `wiki_concept` | Read a concept page by name or slug |
| `wiki_pattern` | Read a design pattern page |
| `wiki_style` | Read a writing style guide by venue + topic |
| `wiki_paper` | Read a paper's source page by slug |
| `wiki_suggest` | List papers referenced but not yet downloaded |
| `wiki_stats` | Quick knowledge base overview |

## SLURM automation

For unattended runs on a cluster:

```bash
#!/bin/bash
#SBATCH --job-name=scholarwiki
#SBATCH --time=08:00:00
#SBATCH --partition=exacloud
#SBATCH --output=scholarwiki_%j.log

cd /path/to/ScholarWiki
scholarwiki process-batch --wait --timeout 6h
```

Submit once after dropping new papers into `nexus_inbox/`. Come back to an updated wiki.

## Development

```bash
pip install -e ".[dev]"
pytest                          # 223 tests
pytest tests/test_pipeline.py   # specific module
pytest -m integration           # integration tests (requires API keys)
```

### Project layout

```
src/scholarwiki/
├── cli.py               # typer CLI commands
├── config.py            # load config.yaml, expand ${ENV_VAR}
├── models.py            # PaperEntry, Registry (pydantic)
├── registry.py          # load/save registry.json (atomic writes)
├── pipeline.py          # process-batch orchestration
├── l1_page.py           # render stub source pages
├── wiki.py              # index.md and log.md updates
├── zotero.py            # Zotero push
├── manual_queue.py      # raw/manual.md queue
├── ingest/
│   ├── nexus.py         # nexus_inbox/ processor
│   └── manual.py        # manual_inbox/ processor
├── extraction/
│   ├── batch.py         # GPT-4.1 batch submit/collect
│   ├── text_extractor.py
│   ├── l1_aggregator.py
│   ├── concept_mapping.py
│   └── prompts/         # per-module system prompts
├── linking/
│   ├── batch.py         # GPT-5/4.1 link batch submit/collect
│   ├── backfill.py      # populate L2 sections of source pages
│   ├── concept_match.py # rapidfuzz slug matching
│   ├── knowledge_hypergraph.py
│   ├── design_patterns.py
│   ├── writing_styles.py
│   ├── synthesis_prompts.py
│   └── suggested_papers.py
├── maintenance/
│   ├── lint.py          # wiki health checks
│   └── stats.py         # knowledge base summary
└── mcp/
    ├── tools.py          # wiki search and read functions
    └── server.py         # MCP server (stdio)
```
