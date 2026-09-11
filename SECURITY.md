# Security

This tool has a narrow job — fetch and parse public pages from
3830scores.com — and a narrow threat model to match. There are no
credentials anywhere in this project; the risks that matter here are
**unauthorized/excessive access to a third-party site** and **this tool
being turned into an open URL fetcher**, not injection or secret leakage.

---

## Guarantees

| # | Guarantee | How it's enforced |
|---|-----------|--------------------|
| 1 | Only fetches 3830scores.com | `Fetcher.get()` checks the URL's hostname against an allowlist before every request — see below |
| 2 | No credentials exist to leak | The site requires none; this project has none in code, config, or env |
| 3 | Requests are rate-limited | `Fetcher` enforces `MIN_INTERVAL` (default 1 req/sec) between requests |
| 4 | Access is identified, not disguised | Every request carries an `X-Requested-By` header with a real contact address — see [README](README.md#why-this-is-a-crawler-not-a-url-builder) |
| 5 | HTTPS only | `BASE` and every constructed URL are `https://` |
| 6 | No code-execution surface | No `subprocess`, `os.system`, `eval`, `exec`, or shell interpolation anywhere in this codebase |
| 7 | No injection surface | No database, no SQL, no templating of untrusted strings into commands |
| 8 | Fails loudly, not silently | An unmapped/off-domain URL raises `ValueError` immediately, before any network call |

---

## The actual threat model

**This is not a general-purpose scraper, and it must not become one.**
`get_scores(url)`, `get_rumor(url)`, and `list_editions(url)` all accept a
URL string from the caller — a CLI argument, a value an agent decided to
pass, a URL chained from a previous call's output. Without a check, handing
any of those functions an arbitrary URL turns this tool into an open fetch
of anything on the internet, using its own outbound network access and
identifying header — including internal/link-local addresses (SSRF), not
just other public sites.

`Fetcher.get()` guards against this directly:

```python
host = urlparse(url).hostname or ""
if not (host == "3830scores.com" or host.endswith(".3830scores.com")):
    raise ValueError(f"refusing to fetch non-3830scores.com URL: {url!r}")
```

This is checked against the **hostname only** (via `urlparse`), not a
substring/prefix test on the raw URL string — so lookalikes such as
`3830scores.com.evil.com` or `evil3830scores.com` are correctly rejected,
not just `evil.example.com`. See `tests/test_fetcher.py::TestHostAllowlist`
for the cases this is checked against.

Every legitimate code path only ever constructs 3830scores.com URLs itself
(`urljoin(BASE, ...)` from a link found on a previously-fetched page), so
this check should never fire during normal use — only when something has
gone wrong upstream of it.

---

## Forbidden patterns

None of the following appear in this codebase, and none should be added:

```python
# Command injection surface
import subprocess
os.system(...)
subprocess.run(..., shell=True)
eval(...)
exec(...)

# Fetching a URL without checking it against the host allowlist first
requests.get(user_supplied_url)          # bypasses Fetcher.get()'s guard
self.session.get(url)                    # only Fetcher.get() should ever do this

# Loosening the identification/rate-limit defaults without operator sign-off
MIN_INTERVAL = 0
del session.headers["X-Requested-By"]
```

---

## Reporting a concern

This is a small personal tool with no public user base and no package
release. If you find a way the host allowlist can be bypassed, or any
other issue that could turn this into something other than a polite,
identified, rate-limited reader of 3830scores.com, open an issue in this
repo or contact the maintainer directly rather than exploiting it.
