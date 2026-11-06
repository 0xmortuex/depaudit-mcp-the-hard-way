# Module 04: Dependency Paths

## The Concept

"`minimist 0.0.8` has a critical prototype-pollution bug" is true and nearly useless. You never typed `minimist`. What can you change?
Only your *direct* dependencies. The report needs the chain from one of them:

```
minimist 0.0.8   <-   mkdirp 0.5.1   <-   (your package.json)
```

so the fix reads "upgrade `mkdirp`, or override `minimist`", not "edit a file you do not own".

## The algorithm: multi-source breadth-first search

We have `direct` (the roots) and `edges` (package -> what it depends on). We want, for any package, the shortest chain from some root.

```python
parent = {p: None for p in direct}          # None = "I am a root"
queue = deque(direct)
while queue:
    cur = queue.popleft()
    for nxt in edges.get(cur, ()):
        if nxt not in parent:               # first time reached = shortest way (BFS)
            parent[nxt] = cur
            queue.append(nxt)
```

Then walk `parent` back from the target and reverse. One pass answers every package, which matters because a report asks about dozens of them.

Why this shape:

- **BFS, not depth-first.** BFS reaches each node by a shortest path first. A depth-first walk returns whatever path it stumbles on, often a long, misleading one.
- **All roots at once.** Starting the queue with every direct dependency means "shortest from *any* root", with no per-root search.
- **`parent` doubles as `seen`.** Dependency graphs have **diamonds** (two packages need the same library) and **cycles** (npm allows them). The `not in parent` check visits each node once, so cycles terminate and diamonds do not multiply paths.
- **Sorted iteration** (`sorted(...)`) makes the chosen path deterministic when several shortest ones exist. Reports that change between runs erode trust.

If a package is not in `parent`, no direct dependency reaches it: an optional or platform-specific package the lockfile lists but the root does not need. The tool says "unknown path" rather than inventing one.

## Where the edges come from

Module 01. The npm parser resolves each dependency name to the right *installed copy* (nested `node_modules` first), so the chain names the version that is really installed.
If you had wired every `minimist` to the top-level copy, a path through a package that has its own nested `minimist@1` would point at the wrong parent.

## Run It

```bash
python 04-dependency-paths/main.py
```

On the real sample lockfile it prints `mkdirp 0.5.1 > minimist 0.0.8` and `@babel/core 7.0.0 > json5 0.5.1`, and checks all 35 packages are reachable. It also tests a diamond (the shorter side wins), a cycle (terminates) and an unreachable package (no chain).

## Limits

- A lockfile like `requirements.txt` has no edges, so there is nothing to search; the report must say "unknown" (it does, in the full server).
- The shortest path is *a* reason the package is installed, not the only one. For upgrades, the first hop (the direct dependency) is what you act on.

## Key Takeaways

- Turn "what is broken" into "what do I change" with a graph search.
- `parent` pointers from a multi-source BFS answer every "why is this here?" in one pass.
- Cycles and diamonds are normal; guard with a visited set.
