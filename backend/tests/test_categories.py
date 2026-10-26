def create(client, name, kind="expense", parent_id=None):
    """Small helper so each test reads as one line per category."""
    return client.post("/api/categories", json={"name": name, "kind": kind, "parent_id": parent_id})


# ---- creating ----

def test_create_top_level_category(client):
    response = create(client, "Food")

    assert response.status_code == 201
    assert response.json() | {"id": 0} == {"id": 0, "name": "Food", "kind": "expense", "parent_id": None}


def test_create_subcategory(client):
    food = create(client, "Food").json()

    response = create(client, "Groceries", parent_id=food["id"])

    assert response.status_code == 201
    assert response.json()["parent_id"] == food["id"]


# ---- parent rules (check_parent) ----

def test_parent_must_exist(client):
    response = create(client, "Groceries", parent_id=999)

    assert response.status_code == 422


def test_only_one_level_of_subcategories(client):
    food = create(client, "Food").json()
    groceries = create(client, "Groceries", parent_id=food["id"]).json()

    response = create(client, "Organic", parent_id=groceries["id"])

    assert response.status_code == 422


def test_subcategory_kind_must_match_parent(client):
    food = create(client, "Food", kind="expense").json()

    response = create(client, "Bonus", kind="income", parent_id=food["id"])

    assert response.status_code == 422


def test_rejected_subcategory_is_not_saved(client):
    food = create(client, "Food", kind="expense").json()
    create(client, "Bonus", kind="income", parent_id=food["id"])

    tree = client.get("/api/categories").json()

    assert tree[0]["subcategories"] == []


# ---- name uniqueness ----

def test_duplicate_top_level_name_in_same_kind_is_a_conflict(client):
    create(client, "Food")

    response = create(client, "Food")

    assert response.status_code == 409
    assert "Food" in response.json()["detail"]


def test_same_top_level_name_is_fine_in_a_different_kind(client):
    create(client, "Other", kind="expense")

    response = create(client, "Other", kind="income")

    assert response.status_code == 201


def test_duplicate_subcategory_under_same_parent_is_a_conflict(client):
    food = create(client, "Food").json()
    create(client, "Other", parent_id=food["id"])

    response = create(client, "Other", parent_id=food["id"])

    assert response.status_code == 409


def test_same_subcategory_name_under_different_parents_is_fine(client):
    food = create(client, "Food").json()
    shopping = create(client, "Shopping").json()
    create(client, "Other", parent_id=food["id"])

    response = create(client, "Other", parent_id=shopping["id"])

    assert response.status_code == 201


# ---- listing ----

def test_list_returns_a_sorted_tree(client):
    food = create(client, "Food").json()
    create(client, "Bills")
    create(client, "Restaurants", parent_id=food["id"])
    create(client, "Groceries", parent_id=food["id"])

    tree = client.get("/api/categories").json()

    assert [c["name"] for c in tree] == ["Bills", "Food"]
    assert [s["name"] for s in tree[1]["subcategories"]] == ["Groceries", "Restaurants"]


def test_list_can_filter_by_kind(client):
    create(client, "Food", kind="expense")
    create(client, "Paycheck", kind="income")

    tree = client.get("/api/categories", params={"kind": "income"}).json()

    assert [c["name"] for c in tree] == ["Paycheck"]
