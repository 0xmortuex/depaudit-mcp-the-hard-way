# Module 01: Lockfile Formats

## The Concept

A manifest (`package.json`, `pyproject.toml`) says what you **asked** for: `requests>=2`.
A lockfile says what you **got**: `requests 2.19.1`, `urllib3 1.23`, `idna 2.7`, and which
package pulled in which. A vulnerability database can only answer questions about exact versions,
so the lockfile is the only honest input. It is also the only place transitive dependencies show up.

Every format answers the same three questions differently:

1. **Which packages are installed?** (name + exact version)
2. **Which did the project ask for directly?**
3. **Which package depends on which?**

We turn each format into the same shape so the rest of the course never cares which one it came from:

```python
@dataclass
class Lock:
    packages: set[Pkg]               # Pkg = (ecosystem, name, version)
    direct:   set[Pkg]               # what the project asked for
    edges:    dict[Pkg, set[Pkg]]    # package -> what it depends on
```

`Pkg` is a `NamedTuple`: immutable and hashable, so it works in sets and as a dict key.

## requirements.txt: pins and nothing else

```
requests==2.19.1 \
    --hash=sha256:abc
PyYAML[extra]==5.3 ; python_version >= "3.6"
flask>=1.0
```

Only `name==version` is auditable. `flask>=1.0` does not say what is installed, so the parser skips it
(a real tool should *tell* you it skipped it: see the server's `notes`). Details that bite:

- a trailing `\` continues the line (`pip-compile` puts `--hash` options there);
- `[extra]` and `; marker` are part of the line but not the name or version;
- names must be normalized (PEP 503): `PyYAML`, `pyyaml` and `py_yaml` all differ from the registry's point of view only by case and separators.

There is no graph, so every pin counts as direct. That is a limitation to state, not hide.

## package-lock.json: install paths

npm lockfile v2/v3 has a flat `packages` map keyed by **where the package is installed**:

```json
"node_modules/mkdirp":                    { "version": "0.5.1", "dependencies": { "minimist": "0.0.8" } },
"node_modules/minimist":                  { "version": "0.0.8" },
"node_modules/a/node_modules/b":          { "version": "2.0.0" }
```

Two things to get right:

- **The name is whatever follows the last `node_modules/`.** `a/node_modules/b` is package `b`, installed inside `a`.
- **Edges need Node's resolution rule.** `mkdirp` says it needs `minimist`; *which* minimist? The one found by looking in
  `<mkdirp's path>/node_modules/minimist`, then in each parent directory up to the top. `resolve()` implements that loop. Skip it and
  a package that needs `b@2` gets wired to the hoisted `b@1`, and your dependency paths (module 04) lie.

The key `""` is the project itself. What it depends on is the direct set. Workspace members (keys not under `node_modules/`) work the same way.
Version 1 lockfiles nest dependencies instead; they are rejected with a message, not guessed at.

## uv.lock: TOML with names

```toml
[[package]]
name = "requests"
version = "2.19.1"
source = { registry = "https://pypi.org/simple" }
dependencies = [ { name = "urllib3" }, ... ]

[[package]]
name = "demo"                       # the project itself
source = { virtual = "." }
dependencies = [ { name = "requests" } ]
```

`tomllib` (standard library, Python 3.11+) does the parsing. The logic is about interpretation:

- Only `source = { registry = ... }` packages exist in PyPI. The project is `virtual` or `editable`: it is the **root**, and its dependencies
  (plus its dev groups) are the direct set.
- A dependency is normally just a name. When the same name is locked at two versions (here: `pytest` for old and new Pythons), uv adds `version = ...`
  to disambiguate, and `resolve()` honours it.

## Run It

```bash
python 01-lockfile-formats/main.py
```

It parses the real files in `samples/` and asserts, among other things, that `mkdirp 0.5.1` depends on `minimist 0.0.8`
(a vulnerable transitive dependency we will find in module 03 and explain in module 04), and that a nested `node_modules` resolves to the nested copy.

## Key Takeaways

- Parse into one model; let every later stage ignore the format.
- "Direct" means something different in each format; decide where it comes from and say so when it cannot be known.
- Skipping input silently (an unpinned requirement, a git source) is how audits go quietly wrong. Record what you skipped.
