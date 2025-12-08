# Interactive LLM Test

Test the BioYoda LLM framework with function calling in an interactive CLI.

## Quick Start

```bash
# From project root
conda run -n bioyoda python modules/agent_system/tests/interactive_llm_test.py

# Or use the script
./modules/agent_system/tests/test_llm_interactive.sh
```

## Features

- **Interactive Chat**: Talk with the LLM in real-time
- **Function Calling**: See when the LLM decides to use tools
- **Tool Definitions**: Pre-configured with biobtree_query and bioyoda_search
- **Conversation History**: Maintains context across turns
- **Token Usage**: Shows token consumption for each turn

## Available Tools

### 1. biobtree_query
Query BioBTree database for deterministic mappings across biological databases.

**Example queries:**
- "Find proteins for BRCA1"
- "What is the UniProt ID for TP53?"
- "Map EGFR to ChEMBL targets"

### 2. bioyoda_search
Semantic search across PubMed and clinical trials.

**Example queries:**
- "Search PubMed for CRISPR gene editing"
- "Find clinical trials for immunotherapy"
- "What are recent papers on Alzheimer's disease?"

## Commands

- **quit / exit / q**: Exit the interactive session
- **reset**: Clear conversation history and start fresh
- **Ctrl+C**: Interrupt and exit

## Example Session

```
📝 You: Find proteins for BRCA1

🤖 Assistant: 
🔧 Calling tool: biobtree_query
   Arguments: {'chain_query': 'BRCA1 >> * >> hgnc >> uniprot'}
   Result: [Tool result...]
   
🤖 Assistant: I found the following proteins for BRCA1...

💰 Tokens: 145 (prompt: 132, completion: 13)

📝 You: Search PubMed for BRCA1 mutations

🤖 Assistant:
🔧 Calling tool: bioyoda_search
   Arguments: {'query': 'BRCA1 mutations', 'collection': 'pubmed', 'top_k': 10}
   Result: [Tool result...]
```

## Configuration

The test uses the configuration from:
- `config/agent_system.yaml` (agent-specific settings)
- `config/config.yaml` (main BioYoda config, merged automatically)

Current provider: **Google Gemini 2.0 Flash Lite** (from config.yaml -> rag.provider)

## Notes

- Function calls are **simulated** (tools aren't actually executed yet)
- In the real agent system, tools will execute and return real results
- Temperature is set to 0.0 for deterministic tool calling
- System prompt guides the LLM on when to use each tool

## Troubleshooting

### Error 429: Resource Exhausted

If you see `429 Resource exhausted`, the Gemini API free tier rate limit has been reached.

**Solutions:**
1. **Wait 1-5 minutes** for rate limit to reset
2. **Use a different API key** (set in `config/config.yaml`)
3. **Switch to a paid tier** for higher limits
4. **Use a different provider** (Anthropic Claude or OpenAI GPT-4) if you have API keys

The free Gemini tier has strict limits:
- 15 requests per minute
- 1500 requests per day
- May be shared across all users of the API key
