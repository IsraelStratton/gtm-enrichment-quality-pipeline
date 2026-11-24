# INIT-165 build guide: Ask the pipeline

A read-only MCP server over the run log (KB-140). An MCP client asks a question in plain words; the server answers from four fixed queries, signed in as a login that can only read. This guide is the order the build was done in. Notes and results: [init-165-notes.md](init-165-notes.md).

| Part | What | Who |
|---|---|---|
| A | The SQL, the read-only login, the token, and the write check | Code chat |
| B | Two n8n credentials, pasting the two values from `.env` | Israel |
| C | Publish, switch on, probe, the eight questions, the planted test, switch off | Code chat |
| D | Optional: connect the Claude desktop app | Israel |

## A. The database side (Code chat)

```bash
python scripts/ask_pipeline.py setup     # applies db/ask_pipeline.sql, makes gtm_v2_reader and the token, then checks
python scripts/ask_pipeline.py plant     # the planted-instruction test row, through the pipeline's add-only function
python scripts/ask_pipeline.py answers   # the eight answers by SQL, saved to init-165-evidence/sql-answers.json
python scripts/build_n8n_ask_pipeline.py # n8n/workflow-v2-ask-pipeline.json
```

`setup` writes `GTM_V2_READER_PASSWORD` and `ASK_PIPELINE_TOKEN` to `.env` and never prints them.

## B. Two n8n credentials (Israel)

Open n8n at http://localhost:5678, **Credentials**, **Create credential**. Each value is copied from `.env` by the command beside it, run in Terminal; nothing is shown on screen. Paste with Cmd+V.

**1. GTM v2 run log reader (read only)**, type **Postgres**

| Field | Value |
|---|---|
| Name (top left) | `GTM v2 run log reader (read only)` |
| Host | `host.docker.internal` |
| Database | `postgres` |
| User | `gtm_v2_reader` |
| Password | paste after running the command below |
| Port | `54322` |
| SSL | Disable |

```bash
cd ~/gtm-enrichment-quality-pipeline && grep '^GTM_V2_READER_PASSWORD=' .env | cut -d= -f2- | tr -d '\n' | pbcopy && echo "reader password copied"
```

Save. It should show "Connection tested successfully".

**2. GTM v2 ask the pipeline token**, type **Bearer Auth**

| Field | Value |
|---|---|
| Name (top left) | `GTM v2 ask the pipeline token` |
| Bearer Token | paste after running the command below |

```bash
cd ~/gtm-enrichment-quality-pipeline && grep '^ASK_PIPELINE_TOKEN=' .env | cut -d= -f2- | tr -d '\n' | pbcopy && echo "token copied"
```

Save. Then clear the clipboard by copying any other text.

## C. Publish and prove it (Code chat)

```bash
python scripts/ask_pipeline.py publish          # into n8n by its API, switched off; credentials found by name
python scripts/ask_pipeline.py on               # start the server
python scripts/ask_pipeline.py probe --save     # four read tools, typed; bad input refused; cut off at 50; token; network
python scripts/ask_pipeline_client.py --rounds 3   # the blind client: the eight questions and the planted test
python scripts/ask_pipeline.py off              # stop the server
python scripts/ask_pipeline.py publish --check  # the live copy matches the file
```

## D. Optional: the Claude desktop app (Israel)

The desktop app reaches a local server through a small program it starts itself. `scripts/ask_pipeline.py bridge` is that program: it forwards each message to the n8n server and adds the token from `.env`, so no token goes into the app's settings.

1. Start the server: `python scripts/ask_pipeline.py on`.
2. In the Claude desktop app: **Settings**, **Developer**, **Edit Config**. This opens `claude_desktop_config.json`. Add this inside `"mcpServers"` (keep any servers already there, with a comma between them):

```json
"ask-the-pipeline": {
  "command": "/Users/israelstratton/gtm-enrichment-quality-pipeline/.venv/bin/python",
  "args": ["/Users/israelstratton/gtm-enrichment-quality-pipeline/scripts/ask_pipeline.py", "bridge"]
}
```

3. Quit the app fully (Cmd+Q) and open it again. In a new chat, the tools menu lists **ask-the-pipeline** with four tools.
4. Ask, for example: "What did run n8n-8791 cost, and how many of its decisions did a person change?" The app asks before each tool call; allow it.
5. Afterwards: `python scripts/ask_pipeline.py off`. While the server is off, the app shows the tools but each call answers that the server is not reachable.

For a new Claude Code session instead of the desktop app:

```bash
claude mcp add ask-the-pipeline -- /Users/israelstratton/gtm-enrichment-quality-pipeline/.venv/bin/python /Users/israelstratton/gtm-enrichment-quality-pipeline/scripts/ask_pipeline.py bridge
```
