# Break It: Lockfile Formats

## Challenge 1: Forget Nested node_modules

In `parse_package_lock`, replace `resolve(key, dep)` with a lookup of only `node_modules/{dep}`. Run `main.py`.
Which assertion fails? Then think about what it would do to a real report.

**Hint:** The nested test expects package `a` to depend on `b 2.0.0`. Without the walk up from `a`'s own folder,
it is wired to the hoisted `b 1.0.0` instead, so an audit would test the wrong version of `b` and a dependency path would name the wrong parent.

## Challenge 2: Case and Separators

Add `Flask_Login==0.6.3` to `samples/requirements.txt` and remove `pypi_name`. What name goes to the database? Put it back and add `flask.login==0.6.3` on another line.

**Hint:** PyPI treats `Flask_Login`, `flask-login` and `flask.login` as one project. Un-normalized names produce duplicates in your report
and, for registries that are strict, lookups that 404.

## Challenge 3: A Wildcard Is Not a Pin

Change the requirement `numpy==1.*` handling so it is accepted as version `1.*` (remove the `"*" not in` check). What would you send to OSV?

**Hint:** `1.*` is a range, not a version. A database answers "is 1.* vulnerable?" with nonsense or an error. Skipping is right, *telling the user* is better.

## Challenge 4: A Format You Have Not Seen

Write `parse_cargo_lock` (it is TOML again: `[[package]]` with `name`, `version`, `source` and `dependencies = ["name", "name 1.2.3"]`).
Packages without `source` are the project's own crates, and what they depend on is the direct set.

**Hint:** This is the same shape as `parse_uv_lock`. A dependency string with two words (`"time 0.1.43"`) names a version because two versions of `time` are locked.
