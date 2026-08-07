"""Tags through the HTTP surface: the four decisions in FRD §2.7 and the ``?tag=``/``?op=``
filter in §3.3, end to end against a real Postgres."""

from httpx import AsyncClient


async def _create(client: AsyncClient, title: str, *, tags: list[str] | None = None, priority: int = 3) -> str:
    body: dict[str, object] = {"title": title, "priority": priority}
    if tags is not None:
        body["tags"] = tags
    r = await client.post("/v1/tasks", json=body)
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def _titles(client: AsyncClient, query: str) -> set[str]:
    r = await client.get(f"/v1/tasks?{query}")
    assert r.status_code == 200, r.text
    return {item["title"] for item in r.json()["items"]}


class TestTaggingOnTheTaskBody:
    async def test_create_returns_the_tags_sorted(self, client: AsyncClient) -> None:
        r = await client.post("/v1/tasks", json={"title": "a", "priority": 3, "tags": ["urgent", "backend"]})

        assert r.status_code == 201, r.text
        assert r.json()["tags"] == ["backend", "urgent"]

    async def test_untagged_task_reports_an_empty_list_not_null(self, client: AsyncClient) -> None:
        r = await client.post("/v1/tasks", json={"title": "a", "priority": 3})

        assert r.json()["tags"] == []

    async def test_unknown_names_are_created_on_use(self, client: AsyncClient) -> None:
        await _create(client, "a", tags=["brand-new"])

        r = await client.get("/v1/tags")
        assert {t["name"] for t in r.json()["items"]} == {"brand-new"}

    async def test_get_and_list_both_carry_tags(self, client: AsyncClient) -> None:
        task_id = await _create(client, "a", tags=["x"])

        one = await client.get(f"/v1/tasks/{task_id}")
        listed = await client.get("/v1/tasks")

        assert one.json()["tags"] == ["x"]
        assert listed.json()["items"][0]["tags"] == ["x"]

    async def test_patch_replaces_the_whole_list(self, client: AsyncClient) -> None:
        task_id = await _create(client, "a", tags=["one", "two"])

        r = await client.patch(f"/v1/tasks/{task_id}", json={"tags": ["three"]})

        assert r.status_code == 200, r.text
        assert r.json()["tags"] == ["three"]

    async def test_patch_omitting_tags_leaves_them(self, client: AsyncClient) -> None:
        task_id = await _create(client, "a", tags=["keep"])

        r = await client.patch(f"/v1/tasks/{task_id}", json={"priority": 5})

        assert r.json()["tags"] == ["keep"]

    async def test_put_omitting_tags_clears_them(self, client: AsyncClient) -> None:
        task_id = await _create(client, "a", tags=["gone"])

        r = await client.put(f"/v1/tasks/{task_id}", json={"title": "a", "priority": 4})

        assert r.status_code == 200, r.text
        assert r.json()["tags"] == []

    async def test_case_variants_collapse_to_one_tag(self, client: AsyncClient) -> None:
        r = await client.post("/v1/tasks", json={"title": "a", "priority": 3, "tags": ["Urgent", "urgent", " URGENT "]})

        assert r.json()["tags"] == ["Urgent"]  # the first spelling is kept for display

    async def test_deleting_a_task_drops_its_links_and_frees_the_tag(self, client: AsyncClient) -> None:
        task_id = await _create(client, "a", tags=["orphan"])
        tag_id = (await client.get("/v1/tags")).json()["items"][0]["id"]

        assert (await client.delete(f"/v1/tasks/{task_id}")).status_code == 204
        # ON DELETE CASCADE means the tag is now unused, so it becomes deletable.
        assert (await client.delete(f"/v1/tags/{tag_id}")).status_code == 204


class TestTagFilter:
    async def test_repeated_tags_narrow_by_default(self, client: AsyncClient) -> None:
        await _create(client, "both", tags=["urgent", "backend"])
        await _create(client, "one", tags=["urgent"])
        await _create(client, "other", tags=["backend"])

        assert await _titles(client, "tag=urgent&tag=backend") == {"both"}

    async def test_op_or_widens(self, client: AsyncClient) -> None:
        await _create(client, "both", tags=["urgent", "backend"])
        await _create(client, "one", tags=["urgent"])
        await _create(client, "neither", tags=["docs"])

        assert await _titles(client, "tag=urgent&tag=backend&op=or") == {"both", "one"}

    async def test_op_and_is_the_default(self, client: AsyncClient) -> None:
        await _create(client, "both", tags=["a", "b"])
        await _create(client, "one", tags=["a"])

        assert await _titles(client, "tag=a&tag=b") == await _titles(client, "tag=a&tag=b&op=and")

    async def test_filter_is_case_insensitive(self, client: AsyncClient) -> None:
        await _create(client, "a", tags=["Urgent"])

        assert await _titles(client, "tag=URGENT") == {"a"}

    async def test_unknown_tag_matches_nothing(self, client: AsyncClient) -> None:
        await _create(client, "a", tags=["real"])

        r = await client.get("/v1/tasks?tag=nope")
        assert r.status_code == 200
        assert r.json()["items"] == []
        assert r.json()["total"] == 0

    async def test_op_without_any_tag_is_accepted_and_inert(self, client: AsyncClient) -> None:
        await _create(client, "a")

        assert await _titles(client, "op=or") == {"a"}

    async def test_status_filter_still_widens_alongside_op(self, client: AsyncClient) -> None:
        # ``op`` governs tags only: repeated statuses must keep returning the union, or every
        # existing multi-status caller would silently get an empty list (FRD §3.3).
        await _create(client, "a")
        await client.patch(f"/v1/tasks/{await _create(client, 'b')}", json={"status": "completed"})

        assert await _titles(client, "status=new&status=completed&op=and") == {"a", "b"}

    async def test_tag_and_status_filters_compose(self, client: AsyncClient) -> None:
        tagged_new = await _create(client, "keep", tags=["x"])
        await _create(client, "wrong-status", tags=["x"])
        await client.patch(f"/v1/tasks/{await _create(client, 'untagged')}", json={"status": "completed"})
        await client.patch(f"/v1/tasks/{tagged_new}", json={"priority": 1})

        assert await _titles(client, "tag=x&status=new") == {"keep", "wrong-status"}
