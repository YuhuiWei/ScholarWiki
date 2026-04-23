# ScholarWiki User Manual

A step-by-step guide for researchers in any field. No programming experience beyond running terminal commands is required.

---

## Table of Contents

1. [What Is ScholarWiki?](#1-what-is-scholarwiki)
2. [What You Will Need](#2-what-you-will-need)
3. [Setting Up Prerequisites](#3-setting-up-prerequisites)
4. [Installing ScholarWiki](#4-installing-scholarwiki)
5. [Adding Papers](#5-adding-papers)
6. [Running the Pipeline](#6-running-the-pipeline)
7. [Browsing Your Wiki in Obsidian](#7-browsing-your-wiki-in-obsidian)
8. [Understanding the Wiki Pages](#8-understanding-the-wiki-pages)
9. [Using ScholarWiki with AI Assistants (MCP)](#9-using-scholarwiki-with-ai-assistants-mcp)
10. [Day-to-Day Workflow](#10-day-to-day-workflow)
11. [CLI Command Reference](#11-cli-command-reference)
12. [Configuration Reference](#12-configuration-reference)
13. [Running on a Compute Cluster (SLURM)](#13-running-on-a-compute-cluster-slurm)
14. [Cost Estimation](#14-cost-estimation)
15. [Troubleshooting](#15-troubleshooting)
16. [FAQ](#16-faq)

---

## 1. What Is ScholarWiki?

ScholarWiki takes a collection of academic papers (PDFs) and automatically builds an interlinked knowledge wiki. Think of it as a personal research Wikipedia that grows with your reading.

For each paper you add, the system:

- **Extracts** key concepts, methods, experimental designs, and writing patterns using AI (GPT-4.1)
- **Synthesizes** cross-paper concept pages that connect findings across your entire library using GPT-5
- **Links** everything together with bidirectional connections, so you can trace how ideas flow between papers
- **Produces** an Obsidian-compatible vault you can browse, search, and extend

The result looks like this:

```
wiki/
  index.md                    # Entry point listing all papers
  concepts/                   # Cross-paper knowledge pages
    transfer_learning.md      # "What we know about transfer learning across all papers"
    batch_correction.md
  patterns/                   # Experimental design templates
    visual_instruction_tuning.md
  writing/                    # Writing style guides per venue
    nature_methods_scrna.md
  sources/                    # One page per paper with summary and links
    lopez2018_scvi.md
  suggested_papers.md         # Papers referenced but not yet in your library
```

**Who is this for?** Any researcher who reads papers and wants to build a structured, searchable knowledge base. You do not need to know how to program. You do need to be comfortable running commands in a terminal (copying and pasting the commands in this guide is sufficient).

---

## 2. What You Will Need

Before installing ScholarWiki, you need four things set up on your computer:

| Prerequisite | What It Is | Why ScholarWiki Needs It |
|---|---|---|
| **Python 3.11+** | A programming language runtime | ScholarWiki is written in Python |
| **OpenAI API Key** | An access key to use GPT models | The AI that reads and synthesizes your papers |
| **Zotero + API Key** | A free reference manager | Stores clean bibliographic records; provides formatted citations |
| **Obsidian** | A free note-taking app | Where you browse and search your finished wiki |

The following sections walk through setting up each one.

---

## 3. Setting Up Prerequisites

### 3.1 Python

**Check if you already have it:**
```bash
python3 --version
```
If this prints `Python 3.11` or higher, you are ready. Skip to the next section.

**If you need to install Python:**

- **macOS:** Install [Homebrew](https://brew.sh) first, then run:
  ```bash
  brew install python@3.12
  ```
- **Windows:** Download from [python.org/downloads](https://www.python.org/downloads/). During installation, check the box that says "Add Python to PATH."
- **Linux (Ubuntu/Debian):**
  ```bash
  sudo apt update && sudo apt install python3.12 python3.12-venv python3-pip
  ```
- **Conda users:** If you use Anaconda or Miniconda (common in biology/neuroscience labs):
  ```bash
  conda create -n scholarwiki python=3.12
  conda activate scholarwiki
  ```

### 3.2 OpenAI API Key

ScholarWiki uses OpenAI's GPT models to read your papers and write wiki pages. You need an API key and some credit on your account.

1. Go to [platform.openai.com](https://platform.openai.com) and create an account (or sign in).
2. Navigate to **API Keys** in the left sidebar.
3. Click **Create new secret key**. Give it a name like "ScholarWiki."
4. Copy the key (it starts with `sk-`). You will not be able to see it again.
5. Add billing: go to **Settings > Billing** and add a payment method. Load at least $5 to start (this processes about 60 papers).

**Set the key in your terminal** (you will need to do this each time you open a new terminal, or add it to your shell profile):

```bash
# macOS/Linux — add to ~/.bashrc or ~/.zshrc for persistence
export OPENAI_API_KEY="sk-your-key-here"

# Windows PowerShell
$env:OPENAI_API_KEY = "sk-your-key-here"
```

### 3.3 Zotero

Zotero is a free, open-source reference manager used by researchers worldwide. ScholarWiki uses it to store clean bibliographic metadata and generate properly formatted citations.

#### Install Zotero

1. Download Zotero from [zotero.org/download](https://www.zotero.org/download/).
2. Install and open it.
3. Create a free Zotero account at [zotero.org/user/register](https://www.zotero.org/user/register) if you don't have one.
4. In Zotero, sign in via **Preferences > Sync > Link Account**.

#### Get Your Zotero API Key

1. Go to [zotero.org/settings/keys](https://www.zotero.org/settings/keys).
2. Click **Create new private key**.
3. Name it "ScholarWiki" and check these permissions:
   - **Library access:** Read/Write
   - **Notes access:** Read/Write
4. Click **Save Key** and copy the key.

#### Find Your Library ID

1. Go to [zotero.org/settings/keys](https://www.zotero.org/settings/keys).
2. Your **Library ID** (also called User ID) is shown at the top of the page — a numeric string like `20167090`.

**Set the keys in your terminal:**

```bash
export ZOTERO_API_KEY="your-zotero-key"
export ZOTERO_LIBRARY_ID="your-library-id"
```

### 3.4 Obsidian

Obsidian is a free note-taking app that displays Markdown files as linked pages with a graph view. ScholarWiki's output is an Obsidian vault.

1. Download from [obsidian.md](https://obsidian.md/).
2. Install and open it.
3. You do not need to create any vault yet — ScholarWiki will create the `wiki/` folder, and you will open it as a vault later.

---

## 4. Installing ScholarWiki

Open your terminal and run:

```bash
# Clone the repository
git clone https://github.com/YuhuiWei/ScholarWiki.git
cd ScholarWiki

# Install ScholarWiki and its dependencies
pip install -e .

# Verify the installation
scholarwiki --help
```

You should see a list of available commands (ingest, extract, link, etc.).

**Create your configuration file:**

```bash
cp config.yaml.example config.yaml
```

Edit `config.yaml` if needed (the defaults work for most users). The important settings:

```yaml
paths:
  wiki: "./wiki"          # Where the wiki vault is created

zotero:
  library_id: "${ZOTERO_LIBRARY_ID}"   # Reads from environment variable
  api_key: "${ZOTERO_API_KEY}"         # Reads from environment variable
```

**Make sure your API keys are set** (add to your `~/.bashrc` or `~/.zshrc`):

```bash
export OPENAI_API_KEY="sk-..."
export ZOTERO_API_KEY="..."
export ZOTERO_LIBRARY_ID="..."
```

Then reload: `source ~/.bashrc` (or `source ~/.zshrc`).

---

## 5. Adding Papers

There are two ways to add papers to ScholarWiki.

### Option A: Manual — Drop PDFs into a folder

1. Place PDF files into the `manual_inbox/` folder inside your ScholarWiki directory:
   ```bash
   cp ~/Downloads/my_paper.pdf manual_inbox/
   ```
2. ScholarWiki will extract metadata (title, authors, year, DOI) from each PDF automatically.

This is the simplest way. Just drag and drop.

### Option B: Automated — Use NEXUS paper fetcher

[NEXUS](https://github.com/YuhuiWei/nexus-paper-fetcher) is a companion tool that searches Semantic Scholar, downloads PDFs, and structures metadata. If you have NEXUS set up:

```bash
# In your NEXUS project:
nexus search "single-cell foundation models" --output-dir /path/to/ScholarWiki/nexus_inbox/
```

NEXUS deposits structured JSON + PDFs into `nexus_inbox/`. ScholarWiki picks these up automatically during ingest.

---

## 6. Running the Pipeline

### The one-command approach

After adding papers to either inbox:

```bash
scholarwiki process-batch --wait
```

This single command does everything:

1. **Ingests** papers from both inboxes (moves PDFs, creates registry entries, syncs to Zotero)
2. **Extracts** knowledge from each paper via GPT-4.1 (submitted as a batch job)
3. **Waits** for the batch to complete (typically 15–60 minutes)
4. **Synthesizes** cross-paper wiki pages via GPT-5
5. **Waits** for synthesis to complete
6. **Writes** all wiki pages

When it finishes, your `wiki/` folder is ready to open in Obsidian.

### Step-by-step approach

If you prefer more control:

```bash
# Step 1: Ingest papers
scholarwiki ingest

# Step 2: Check what's pending
scholarwiki status

# Step 3: Submit extraction batch
scholarwiki extract --submit

# Step 4: Check progress (run periodically)
scholarwiki extract --status

# Step 5: Collect results when done
scholarwiki extract --collect

# Step 6: Submit synthesis batch
scholarwiki link

# Step 7: Check synthesis progress
scholarwiki link --status

# Step 8: Collect synthesis results
scholarwiki link --collect
```

### Adding more papers later

Each time you add new papers, just run:

```bash
# Drop new PDFs into manual_inbox/, then:
scholarwiki process-batch --wait
```

The pipeline is incremental — it only processes new papers and rewrites concept pages to incorporate the new information. Your existing wiki pages get richer, not replaced.

---

## 7. Browsing Your Wiki in Obsidian

1. Open Obsidian.
2. Click **Open folder as vault**.
3. Navigate to your ScholarWiki `wiki/` folder and select it.
4. Start with `index.md` — it lists all your papers.

### Useful Obsidian features

- **Graph view** (Ctrl/Cmd+G): See how your concepts connect visually. Larger nodes have more connections.
- **Search** (Ctrl/Cmd+Shift+F): Full-text search across all pages.
- **Backlinks**: At the bottom of each page, see which other pages link to it.
- **Tags**: Filter by domain tags in the frontmatter.

### Recommended Obsidian settings

- **Settings > Files & Links > Default location for new notes**: Set to "Same folder as current file"
- **Settings > Files & Links > Detect all file extensions**: Enable
- Consider installing the **Dataview** community plugin for structured queries across your wiki.

---

## 8. Understanding the Wiki Pages

### Source pages (`wiki/sources/`)

One per paper. Contains:

- **Frontmatter**: Title, authors, year, venue, DOI, APA citation, Zotero key
- **Summary**: AI-generated summary of the paper's core contribution
- **Knowledge Contributions**: Which concept pages this paper contributed to
- **Research Relationships**: How this paper relates to others (compares against, extends, etc.)
- **Experimental Design**: The paper's experimental logic pattern
- **Writing Notes**: Venue-specific writing observations

### Concept pages (`wiki/concepts/`)

Synthesized across all papers that discuss the concept. Contains:

- **State of the field**: Where the research stands
- **Key findings**: Specific results with citations (e.g., "Model X achieved 93% accuracy on benchmark Y")
- **Contradictions**: Disagreements between papers
- **Research trajectory**: How the field evolved
- **Open questions**: Unanswered research questions
- **Connections**: Links to related concepts with explanations

### Pattern pages (`wiki/patterns/`)

Experimental design templates synthesized from papers that use similar methods:

- **What this methodology is**: Plain-language description
- **When researchers use this approach**: Typical use cases
- **How each paper implements it**: Specific implementation details per paper, including mathematical formulations
- **Practical considerations**: Data requirements, compute, typical scale
- **Known failure modes**: When and why this approach fails

### Writing style pages (`wiki/writing/`)

Guides for writing in the style of a particular venue:

- **Structure patterns**: How papers in this venue organize sections
- **Common phrases**: Typical language used in introductions, methods, results
- **Quantitative reporting**: How numbers and statistics are presented

### Suggested papers (`wiki/suggested_papers.md`)

Papers referenced by your library but not yet added. Ranked by how many concept pages would benefit from adding them. This helps you decide what to read next.

---

## 9. Using ScholarWiki with AI Assistants (MCP)

ScholarWiki can serve as a knowledge source for AI coding assistants via the Model Context Protocol (MCP). This means when you ask an AI assistant a research question, it can search your personal wiki for grounded answers.

### Setup with Claude Code

Create a file called `.claude/mcp.json` in your project directory:

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

Replace `/path/to/ScholarWiki/config.yaml` with the actual path to your config file.

### What the AI can do with your wiki

Once connected, your AI assistant gains these tools:

| Tool | What It Does |
|---|---|
| `wiki_search` | Search across all wiki pages by keyword |
| `wiki_concept` | Read a specific concept page |
| `wiki_pattern` | Read a design pattern page |
| `wiki_style` | Read a writing style guide for a given venue |
| `wiki_paper` | Read a paper's source page |
| `wiki_bibliography` | Generate a formatted bibliography from paper references |
| `wiki_suggest` | List papers you might want to add next |
| `wiki_stats` | Overview of your knowledge base |
| `wiki_source_pdf` | Read sections of the original PDF |

**Example interactions you can have:**

- "What do we know about transfer learning in single-cell models?"
- "Write a Related Work section citing papers from our wiki"
- "Design an experiment based on the methods in our pattern pages"
- "What papers should I read next to fill gaps in our knowledge base?"

The bibliography tool ensures citations are properly formatted (APA style with DOIs), so AI-generated text includes real, verifiable references from your library.

---

## 10. Day-to-Day Workflow

### Weekly literature review

```bash
# 1. Collect new papers (via NEXUS or manual download)
cp ~/Downloads/*.pdf manual_inbox/

# 2. Process everything
scholarwiki process-batch --wait

# 3. Check what's new
scholarwiki stats

# 4. Open Obsidian and browse updated concept pages
```

### Before writing a paper

```bash
# Check what your wiki knows about your topic
scholarwiki serve-mcp  # then use with your AI assistant

# Or browse concept pages directly in Obsidian
# Look at wiki/suggested_papers.md for gaps in coverage
```

### Maintenance

```bash
# Health check
scholarwiki lint

# Sync any papers that failed Zotero push
scholarwiki zotero-sync

# Fetch formatted citations for papers missing them
scholarwiki backfill-citations
```

---

## 11. CLI Command Reference

| Command | What It Does |
|---|---|
| `scholarwiki ingest` | Process papers from both inboxes |
| `scholarwiki status` | Show paper counts by pipeline stage |
| `scholarwiki queue` | List papers pending extraction |
| `scholarwiki queue --add <paper_id>` | Manually queue a paper |
| `scholarwiki extract --submit` | Submit papers to GPT-4.1 batch API |
| `scholarwiki extract --status` | Check extraction batch progress |
| `scholarwiki extract --collect` | Download completed extraction results |
| `scholarwiki extract --retry-failed` | Resubmit failed extraction modules |
| `scholarwiki link` | Submit synthesis batches (GPT-5 + GPT-4.1) |
| `scholarwiki link --status` | Check synthesis batch progress |
| `scholarwiki link --collect` | Collect synthesis results and write wiki pages |
| `scholarwiki process-batch --wait` | Full pipeline, polls until complete |
| `scholarwiki process-batch --continue` | Resume from where the pipeline stopped |
| `scholarwiki process-batch --dry-run` | Show next step without executing |
| `scholarwiki lint` | Health-check the wiki for structural issues |
| `scholarwiki stats` | Knowledge base statistics |
| `scholarwiki serve-mcp` | Start MCP server for AI assistant integration |
| `scholarwiki zotero-sync` | Retry failed Zotero pushes |
| `scholarwiki backfill-citations` | Fetch APA citations from Zotero for existing papers |

All commands accept `--config /path/to/config.yaml` (defaults to `./config.yaml`).

---

## 12. Configuration Reference

`config.yaml` controls all paths, models, and cost caps:

```yaml
paths:
  nexus_inbox: "./nexus_inbox"     # Where NEXUS deposits results
  manual_inbox: "./manual_inbox"   # Where you drop PDFs manually
  raw: "./raw"                     # Stored PDFs and registry.json
  staging: "./staging"             # Batch API intermediate outputs
  wiki: "./wiki"                   # Output wiki vault (open in Obsidian)

zotero:
  library_id: "${ZOTERO_LIBRARY_ID}"  # Your Zotero user ID (numeric)
  library_type: "user"                # "user" for personal library, "group" for shared
  api_key: "${ZOTERO_API_KEY}"        # Your Zotero API key

extraction:
  model: "gpt-4.1"                # Model for reading papers
  max_papers_per_batch: 50         # Max papers per OpenAI batch job
  max_tokens_per_request: 8192     # Max tokens per extraction request
  max_cost_usd: 5.0                # Cost cap per extraction run

linking:
  synthesis_model: "gpt-5"         # Model for concept/pattern synthesis
  style_model: "gpt-4.1"           # Model for writing style synthesis
  min_papers_for_concept: 2        # Min papers before creating a concept page
  min_papers_for_pattern: 1        # Min papers for a pattern page
  min_papers_for_style: 2          # Min papers for a writing style page
  max_cost_usd: 8.0                # Cost cap per linking run

sync:
  method: "rsync"                  # Sync method for remote wiki access
  local_path: "~/Obsidian/ScholarWiki/"  # Local Obsidian vault path
```

**Environment variables:** Values like `${ZOTERO_API_KEY}` are expanded from your shell environment. Set them with `export` in your terminal or `.bashrc`/`.zshrc` file.

---

## 13. Running on a Compute Cluster (SLURM)

If your institution uses SLURM for job scheduling (common in bioinformatics and computational labs), you can run ScholarWiki as a batch job:

```bash
#!/bin/bash
#SBATCH --job-name=scholarwiki
#SBATCH --time=08:00:00
#SBATCH --partition=your-partition
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1
#SBATCH --output=scholarwiki_%j.log

# Load your Python environment
source activate scholarwiki  # or: module load python/3.12

# Set API keys (or source from a secure file)
export OPENAI_API_KEY="sk-..."
export ZOTERO_API_KEY="..."
export ZOTERO_LIBRARY_ID="..."

cd /path/to/ScholarWiki
scholarwiki process-batch --wait --timeout 6h
```

Submit with `sbatch run_scholarwiki.sh`. When it completes, your wiki is updated.

**Security note:** Do not hardcode API keys in scripts that are version-controlled or shared. Use a separate `.env` file with restricted permissions:

```bash
# Create .env file (never commit this)
echo 'export OPENAI_API_KEY="sk-..."' > .env
chmod 600 .env

# In your SLURM script:
source .env
```

---

## 14. Cost Estimation

ScholarWiki uses OpenAI's Batch API, which runs at 50% discount compared to standard API pricing.

| Stage | Model | Approximate Cost |
|---|---|---|
| Extraction | GPT-4.1 | ~$0.08 per paper (5 modules) |
| Synthesis | GPT-5 + GPT-4.1 | ~$0.10–0.30 per concept page |

**Typical costs:**

- **10 papers:** ~$2–3 total
- **50 papers:** ~$8–12 total
- **100 papers:** ~$15–25 total

Cost caps in `config.yaml` prevent runaway spending. The pipeline stops with a clear message if a run would exceed the cap.

---

## 15. Troubleshooting

### "No papers pending extraction"

Your papers have already been processed. Check with `scholarwiki status`. If you want to reprocess, the paper states in `raw/registry.json` would need to be reset.

### "COST CAP" error

The estimated cost exceeds your configured limit. Either:
- Increase `max_cost_usd` in `config.yaml`
- Process fewer papers at once

### Zotero sync failures

```bash
scholarwiki zotero-sync
```

Common causes:
- Expired or invalid API key — regenerate at [zotero.org/settings/keys](https://www.zotero.org/settings/keys)
- Rate limiting — wait a few minutes and retry
- Check that `ZOTERO_API_KEY` and `ZOTERO_LIBRARY_ID` are set in your terminal

### Missing citations on source pages

If papers were ingested before the citation feature was added:
```bash
scholarwiki backfill-citations
```

This fetches formatted APA citations from Zotero for all existing papers.

### Batch job running too long

OpenAI Batch API jobs can take 15 minutes to several hours depending on queue depth. If you are on a cluster with time limits:

```bash
# Submit without waiting
scholarwiki process-batch --no-wait

# Check later
scholarwiki extract --status   # or: scholarwiki link --status

# Resume when ready
scholarwiki process-batch --continue
```

### PDF metadata extraction errors

For PDFs with unusual formatting (scanned images, non-standard layouts), the automatic metadata extraction may produce incorrect titles or author names. Solutions:
- Use NEXUS (which pulls metadata from Semantic Scholar) instead of manual inbox
- Correct metadata in Zotero after ingest — Zotero's "Retrieve Metadata" feature is excellent

### "No concept page found" in MCP

The concept may be named differently than you expect. Use `wiki_search` first to find the right page name:

```
wiki_search("batch correction")  # finds batch_correction.md or batch_effect_correction.md
```

---

## 16. FAQ

**Q: What research fields does ScholarWiki work with?**

Any field. The extraction and synthesis prompts are field-agnostic. The system has been tested with papers in computational biology, machine learning, neuroscience, and multimodal AI, but it works equally well with papers in chemistry, physics, social sciences, or any other domain.

**Q: Do I need to keep Zotero running?**

No. ScholarWiki communicates with Zotero through its web API, not the desktop app. You just need a Zotero account and API key. However, having Zotero desktop installed is useful for browsing and correcting your reference library.

**Q: Can I edit the wiki pages manually?**

Yes, but be aware that concept, pattern, and writing style pages are **fully rewritten** each time you run the linking step. Your manual edits to those pages will be overwritten. Source pages (in `wiki/sources/`) are safer to edit, as only the "Knowledge Contributions" and "Research Relationships" sections are updated.

If you want to add permanent notes, create new Markdown files in the `wiki/` directory. ScholarWiki will not touch files it did not create.

**Q: How do I remove a paper?**

Currently there is no `remove` command. To remove a paper:
1. Delete its source page from `wiki/sources/`
2. Remove its entry from `raw/registry.json`
3. Run `scholarwiki link --collect` to regenerate concept pages without it

**Q: Can multiple people share a wiki?**

Yes. The `wiki/` folder is plain Markdown files. You can:
- Put it in a shared Dropbox/Google Drive/OneDrive folder
- Use Obsidian Sync (paid feature)
- Use git to version-control the wiki folder
- Use the `sync` config option with rsync

**Q: What if I don't have a Zotero account?**

ScholarWiki will still work — Zotero integration is optional. Without Zotero:
- Papers will not have formatted citations (the `citation` field will be empty)
- Source pages will still have title, authors, year, venue, and DOI from PDF metadata extraction
- You can always add Zotero later and run `scholarwiki zotero-sync` followed by `scholarwiki backfill-citations`

**Q: Is my data sent to OpenAI?**

Yes. The text content of your papers is sent to OpenAI's API for processing. OpenAI's Batch API data retention policy applies. If your papers contain confidential or sensitive data, review OpenAI's data policies at [openai.com/policies](https://openai.com/policies) before proceeding. ScholarWiki uses the Batch API specifically because it offers better data handling terms than the real-time API.

**Q: How much disk space does the wiki use?**

Very little. Each paper produces roughly 5–20 KB of Markdown across source, concept, pattern, and style pages. A 100-paper wiki is typically under 5 MB. The PDFs themselves (stored in `raw/papers/`) are the main space consumers.

---

*ScholarWiki is developed by the [BDRL Lab](https://github.com/YuhuiWei). For bug reports and feature requests, open an issue on [GitHub](https://github.com/YuhuiWei/ScholarWiki/issues).*
