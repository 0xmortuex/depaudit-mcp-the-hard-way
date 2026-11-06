# Break It: Dependency Paths

## Challenge 1: Remove the Visited Check

Delete `if nxt not in parent:` so every edge is pushed. Run the cycle test.

**Hint:** `a -> b -> a -> b ...` never ends. Real npm graphs contain cycles. The test with `cyc` hangs (kill it with Ctrl+C), which is exactly what a user's scan would do.

## Challenge 2: Depth-First by Accident

Change `queue.popleft()` to `queue.pop()` (a stack, which makes it depth-first). Run the diamond test.

**Hint:** It returns `a > b > c > x` instead of `a > d > x`. Depth-first finds a path, not the shortest. A longer path names a more distant, less actionable parent.

## Challenge 3: Print Every Path

Modify the search to list all shortest paths to `minimist` instead of one. In which real situation would you want that?

**Hint:** When two different direct dependencies both pull in a vulnerable package, upgrading just one leaves the problem in place. Keep a list of parents per node (only those at the same BFS depth) and expand them.

## Challenge 4: Wire Edges Naively

In `npm_graph`, make `resolve` look only at `node_modules/{dep}`. Compare the paths for the nested-`node_modules` example from module 01.

**Hint:** The graph silently connects packages to the wrong copy. Nothing crashes; the report is just wrong.
