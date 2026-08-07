# Tags feature

Owns the tag vocabulary and the task↔tag join. Contract: FRD §2.6–2.7 (entity, relationship), §3.1 (endpoints), §3.3 (`?tag=` filter), §4 (errors). Code shape: TIS §5.1.

## What this feature owns

| Table       | Row        | Notes                                                                 |
| ----------- | ---------- | --------------------------------------------------------------------- |
| `tags`      | `Tag`      | `id`, `name` (verbatim), `name_key` UNIQUE, `created_at`               |
| `task_tags` | `TaskTag`  | `(task_id, tag_id)` composite PK; `ON DELETE CASCADE` from both sides |

Both live here, not split with the tasks feature: the join is meaningless without the vocabulary, and separating them would put a foreign key across a feature boundary neither side could enforce alone.

## Invariants

- **`name_key = name.strip().casefold()`** is the only comparison key. `name` is display-only. Identical to `Task.title_key` (FRD §2.5) and for the same reason — case must never create a second tag. `["a", "A", " a "]` in one request is *one* tag.
- **Replacement, never merge.** `set_for_task` writes the whole set. A caller sending `["a"]` to a task tagged `["a","b"]` ends up with `["a"]`.
- **Created on use.** `resolve()` inserts names it does not find, in the caller's transaction. There is no tag-creation endpoint — a tag exists because a task wears it.
- **Deletion is guarded.** A tag any task still holds cannot be deleted: 409 `tag_in_use`, with `details.task_count`. Mirrors the workflow strand guard, so the service tells one story about destructive changes.

## Cross-feature seam

`TaskService` receives `TagRepositoryInterface` in its constructor, never the concrete class. Only `tasks/dependencies.py` may import `SQLModelTagRepository`, and it must build it **from the same request session** — a task write and its tag rows have to land in one transaction, or the outbox's all-or-nothing guarantee is quietly false for tags.

## Events

| Event             | Fired when                                       | Payload                                             |
| ----------------- | ------------------------------------------------ | --------------------------------------------------- |
| `TaskTagsChanged` | A create or update leaves the tag set different. | `task_id`, `tags`, `added`, `removed`               |
| `TagDeleted`      | A tag is removed from the vocabulary.            | `tag_id`, `name`                                    |

`TaskTagsChanged` is independent of `TaskUpdated`: a tags-only change fires this alone, because no `Task` column moved. It carries `task_id` rather than a `Task` snapshot — a detached `Task` has no tag attribute, and adding one purely to fill an event payload would push tag state into the tasks feature.

There is no `TagCreated`: creation is a side effect of tagging, already reported by `TaskTagsChanged.added`.

## Query shapes that matter

- `names_for_tasks(task_ids)` is **batch by design**. A per-task lookup would make `GET /v1/tasks` N+1 — one extra query per row returned.
- `task_ids_with_all(name_keys)` does the AND in SQL (`GROUP BY task_id HAVING COUNT(DISTINCT tag_id) = :n`), not by intersecting sets in Python.

## Errors

| Exception          | HTTP | `code`         |
| ------------------ | ---- | -------------- |
| `TagNotFoundError` | 404  | `tag_not_found` |
| `TagInUseError`    | 409  | `tag_in_use`    |

Both inherit the `AppError` bases in `app/core/errors.py` — never plain `Exception`, which would bypass the global handler and return 500.
