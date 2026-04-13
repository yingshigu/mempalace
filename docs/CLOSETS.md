# Closets — The Searchable Index Layer

## What closets are

Drawers hold your verbatim content. Closets are the index — compact pointers that tell the searcher which drawers to open.

```
CLOSET: "built auth system|Ben;Igor|→drawer_api_auth_a1b2c3"
         ↑ topic           ↑ entities  ↑ points to this drawer
```

An agent searching "who built the auth?" hits the closet first (fast scan of short text), then opens the referenced drawer to get the full verbatim content.

## Lifecycle

### When are closets created?

Closets are created during `mempalace mine`. For each file mined:
1. Content is chunked into drawers (verbatim, ~800 chars each)
2. Topics, entities, and quotes are extracted from the content
3. A closet is created with pointer lines to those drawers

### What's inside a closet?

Each line is one atomic topic pointer:
```
topic description|entity1;entity2|→drawer_id_1,drawer_id_2
"verbatim quote from the content"|entity1|→drawer_id_3
```

Topics are never split across closets. If adding a topic would exceed 1,500 characters, a new closet is created.

### When do closets update?

When a file is re-mined (content changed), its drawers are replaced and new closets are built from the fresh content. The old closet content is replaced via upsert.

### What about stale topics?

If a file's content changes and a topic no longer exists, the closet is rebuilt entirely from the new content — stale topics are gone. Closets are tied to source files, not to individual topics.

If you add content to an existing file (e.g., a daily diary growing throughout the day), new topics are appended to the existing closet until the 1,500-char limit, then a new closet is created.

### Do closets survive palace rebuilds?

Closets are stored in the `mempalace_closets` ChromaDB collection alongside `mempalace_drawers`. If you delete and rebuild the palace, closets are recreated during the next `mempalace mine`.

## How search uses closets

```
Query → search mempalace_closets (fast, small documents)
         ↓
    top closet hits → extract drawer IDs from pointer lines
         ↓
    fetch drawers from mempalace_drawers (full verbatim content)
         ↓
    BM25 hybrid re-rank (keyword match + vector similarity)
         ↓
    return results to user
```

If no closets exist (palace created before this feature), search falls back to direct drawer search. Closets are created on next mine.

## Limits

| Setting | Value | Reason |
|---------|-------|--------|
| Max closet size | 1,500 chars | Leaves buffer under ChromaDB's working limit |
| Max topics per file | 12 | Keeps closets focused |
| Max quotes per file | 3 | Most relevant only |
| Max entities per pointer | 5 | Top names by frequency |
| Max response chars | 10,000 | Prevents hydration blowup on large files |

## For developers

Closet functions live in `mempalace/palace.py`:
- `get_closets_collection()` — get the closets ChromaDB collection
- `build_closet_lines()` — extract topics/entities/quotes into pointer lines
- `upsert_closet_lines()` — write lines to closets respecting the char limit
- `CLOSET_CHAR_LIMIT` — the 1,500 char limit constant
