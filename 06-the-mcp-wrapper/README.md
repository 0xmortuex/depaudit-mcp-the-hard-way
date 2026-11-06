# Module 06: The MCP Wrapper

## The Concept

Modules 01-04 are a library. This module puts it behind MCP, and the lesson is how *little* MCP adds, and where that little bit matters.

```python
mcp = MCPServer("minidep", instructions="Audit a project's lockfiles ...")

@mcp.tool()
def scan_project(path: str) -> str:
    """Scan a project directory (or one lockfile) for known vulnerabilities. ..."""
```

- The function name is the tool name, the type hints become the JSON schema (`{'path': {'type': 'string'}}`), and the **docstring is what the model reads** to decide
  when to call it. Write it for a model: what it accepts, what comes back, that it is read-only, what it needs (internet).
- `instructions` goes to the client once at handshake: how the tools fit together.
- stdout is the protocol channel. **Never `print()` in `--serve` mode**; log to stderr.

## The one rule about errors

With `mcp` 2.x, a client sees the message of a `ToolError` and nothing else. Any other exception arrives as `Error executing tool scan_project`, with no cause, which is
a dead end for an agent. So expected failures are converted at the boundary:

```python
try:
    return scan(path)
except AuditError as e:
    raise ToolError(str(e)) from e
```

and the library raises `AuditError` with a message that says **what happened and what to do**:

| Situation | Message |
|---|---|
| no lockfile | `no requirements.txt or package-lock.json in X. Generate a lockfile first, e.g. npm install --package-lock-only.` |
| bad path | `X does not exist. Pass a project directory or a lockfile.` |
| rate limited | `... answered HTTP 429. It is rate limiting us; wait a minute and retry.` |
| offline | `could not reach ...: <reason>. Check the internet connection.` |

Only *expected* failures are listed. A genuine bug (a `KeyError` in your code) should stay loud, not be dressed up as a friendly message.

## What the pipeline adds

**Merging aliases (module 02's lesson).** Records that share any id or alias form one problem. `merge_aliases` merges groups whose id sets overlap, including chains
(A aliases B, B aliases C). One problem gets one line.

**Choosing the fix.** Advisories list one `fixed` per release branch. `fixed_in` keeps only fixes *above* the installed version and takes the smallest. For `minimist 0.0.8` the raw
list contains 0.2.4 and 1.2.6; naive "first fix" would say 1.2.6, a jump of a major version when 0.2.4 suffices.

**Severity order.** Worst first, with UNKNOWN last, so the first lines of output are the ones to act on. Compact output matters: the whole result goes into the model's context.

**Dependency paths** from module 04, printed as `via mkdirp 0.5.1 > minimist 0.0.8` under transitive findings.

## Testing the server like an agent does

`main.py` without flags starts **itself** with `--serve` as a subprocess and connects as an MCP client over stdio, the same way Claude Code does:

```python
params = StdioServerParameters(command=sys.executable, args=[__file__, "--serve"])
async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
    await session.initialize()
    tools = (await session.list_tools()).tools
    result = await session.call_tool("scan_project", {"path": ...})
```

It asserts the tool list, a real scan of the sample npm project (35 packages, lodash flagged, the `mkdirp > minimist` chain), and that a bad path comes back as
`is_error` with the actionable message. Testing only the Python function would miss everything about the wire: schemas, error conversion, stdout hygiene.

## Run It

```bash
pip install -r requirements.txt
python 06-the-mcp-wrapper/main.py
```

## Key Takeaways

- MCP adds a name, a schema and a description. The docstring is the product.
- Convert expected failures to `ToolError` with instructions; leave bugs loud.
- Test over real stdio, as a client.
- This tutorial server covers two formats and one tool; the full [depaudit-mcp](https://github.com/0xmortuex/depaudit-mcp) adds the other formats, `check_package`, `list_outdated`, `explain_vulnerability` and `suggest_fixes`, using the same pieces.
