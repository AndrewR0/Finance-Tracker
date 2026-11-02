"""Renaming, moving, deleting and merging categories."""


def create(client, name, kind="expense", parent_id=None):
    response = client.post("/api/categories", json={"name": name, "kind": kind, "parent_id": parent_id})
    assert response.status_code == 201
    return response.json()["id"]


def edit(client, category_id, **changes):
    return client.patch(f"/api/categories/{category_id}", json=changes)


def account(client):
    return client.post("/api/accounts", json={"name": "Checking", "type": "checking"}).json()["id"]


def spend(client, account_id, category_id, cents=-1000):
    response = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": "2026-10-01", "amount_cents": cents, "category_id": category_id},
    )
    return response.json()["id"]


def category_of(client, transaction_id):
    return next(t["category_id"] for t in client.get("/api/transactions").json() if t["id"] == transaction_id)


def names(client, kind="expense"):
    """{"Food": ["Coffee", "Groceries"], ...}"""
    tree = client.get(f"/api/categories?kind={kind}").json()
    return {c["name"]: [s["name"] for s in c["subcategories"]] for c in tree}


# ---- rename ----

def test_rename(client):
    food = create(client, "Food")

    response = edit(client, food, name="Food & drink")

    assert response.status_code == 200
    assert names(client) == {"Food & drink": []}


def test_rename_to_a_taken_name_is_409(client):
    create(client, "Food")
    fun = create(client, "Fun")

    response = edit(client, fun, name="Food")

    assert response.status_code == 409
    assert names(client) == {"Food": [], "Fun": []}


def test_same_name_is_fine_in_another_kind(client):
    create(client, "Other", "income")
    other = create(client, "Misc")

    assert edit(client, other, name="Other").status_code == 200


def test_null_name_is_422(client):
    food = create(client, "Food")

    assert edit(client, food, name=None).status_code == 422


def test_kind_cant_change(client):
    food = create(client, "Food")

    assert edit(client, food, kind="income").status_code == 422


# ---- move ----

def test_move_a_subcategory_to_another_parent(client):
    food = create(client, "Food")
    fun = create(client, "Fun")
    coffee = create(client, "Coffee", parent_id=food)

    response = edit(client, coffee, parent_id=fun)

    assert response.status_code == 200
    assert names(client) == {"Food": [], "Fun": ["Coffee"]}


def test_promote_a_subcategory_to_top_level(client):
    food = create(client, "Food")
    coffee = create(client, "Coffee", parent_id=food)

    edit(client, coffee, parent_id=None)

    assert names(client) == {"Coffee": [], "Food": []}


def test_move_into_a_parent_with_the_same_name_is_409(client):
    food = create(client, "Food")
    fun = create(client, "Fun")
    create(client, "Snacks", parent_id=food)
    snacks_fun = create(client, "Snacks", parent_id=fun)

    assert edit(client, snacks_fun, parent_id=food).status_code == 409


def test_a_category_with_subcategories_cant_become_one(client):
    food = create(client, "Food")
    create(client, "Coffee", parent_id=food)
    fun = create(client, "Fun")

    response = edit(client, food, parent_id=fun)

    assert response.status_code == 422
    assert "one level" in response.json()["detail"]


def test_cant_go_under_itself(client):
    food = create(client, "Food")

    assert edit(client, food, parent_id=food).status_code == 422


def test_cant_go_under_a_subcategory(client):
    food = create(client, "Food")
    coffee = create(client, "Coffee", parent_id=food)
    fun = create(client, "Fun")

    assert edit(client, fun, parent_id=coffee).status_code == 422


def test_cant_move_under_another_kind(client):
    salary = create(client, "Salary", "income")
    food = create(client, "Food")
    coffee = create(client, "Coffee", parent_id=food)

    assert edit(client, coffee, parent_id=salary).status_code == 422


def test_spending_follows_a_moved_subcategory(client):
    checking = account(client)
    food = create(client, "Food")
    fun = create(client, "Fun")
    coffee = create(client, "Coffee", parent_id=food)
    spend(client, checking, coffee, -500)

    edit(client, coffee, parent_id=fun)

    report = client.get("/api/dashboard/spending-by-category?start=2026-10-01&end=2026-10-31").json()
    assert [(r["name"], r["spending_cents"]) for r in report] == [("Fun", 500)]


def test_edit_missing_category_is_404(client):
    assert edit(client, 999, name="X").status_code == 404


# ---- delete ----

def test_delete_makes_its_transactions_uncategorized(client):
    checking = account(client)
    food = create(client, "Food")
    tx = spend(client, checking, food)

    response = client.delete(f"/api/categories/{food}")

    assert response.status_code == 200
    assert response.json() == {"moved_transactions": 1}
    assert category_of(client, tx) is None
    assert names(client) == {}


def test_delete_with_move_to_merges(client):
    checking = account(client)
    dining = create(client, "Dining")
    food = create(client, "Food")
    tx = spend(client, checking, dining)

    client.delete(f"/api/categories/{dining}?move_to={food}")

    assert category_of(client, tx) == food
    assert names(client) == {"Food": []}


def test_deleting_a_parent_deletes_its_subcategories_and_moves_all_their_transactions(client):
    checking = account(client)
    food = create(client, "Food")
    coffee = create(client, "Coffee", parent_id=food)
    groceries = create(client, "Groceries", parent_id=food)
    misc = create(client, "Misc")
    txs = [spend(client, checking, food), spend(client, checking, coffee), spend(client, checking, groceries)]

    response = client.delete(f"/api/categories/{food}?move_to={misc}")

    assert response.json() == {"moved_transactions": 3}
    assert [category_of(client, tx) for tx in txs] == [misc, misc, misc]
    assert names(client) == {"Misc": []}


def test_delete_a_subcategory_into_its_parent(client):
    checking = account(client)
    food = create(client, "Food")
    coffee = create(client, "Coffee", parent_id=food)
    tx = spend(client, checking, coffee)

    client.delete(f"/api/categories/{coffee}?move_to={food}")

    assert category_of(client, tx) == food
    assert names(client) == {"Food": []}


def test_move_to_can_be_a_subcategory_elsewhere(client):
    checking = account(client)
    dining = create(client, "Dining")
    food = create(client, "Food")
    restaurants = create(client, "Restaurants", parent_id=food)
    tx = spend(client, checking, dining)

    client.delete(f"/api/categories/{dining}?move_to={restaurants}")

    assert category_of(client, tx) == restaurants


def test_cant_move_into_a_category_being_deleted(client):
    food = create(client, "Food")
    coffee = create(client, "Coffee", parent_id=food)

    for target in (food, coffee):
        response = client.delete(f"/api/categories/{food}?move_to={target}")
        assert response.status_code == 422
    assert names(client) == {"Food": ["Coffee"]}


def test_cant_move_into_another_kind(client):
    checking = account(client)
    food = create(client, "Food")
    salary = create(client, "Salary", "income")
    tx = spend(client, checking, food)

    response = client.delete(f"/api/categories/{food}?move_to={salary}")

    assert response.status_code == 422
    assert category_of(client, tx) == food  # nothing changed


def test_move_to_missing_category_is_422(client):
    food = create(client, "Food")

    assert client.delete(f"/api/categories/{food}?move_to=999").status_code == 422


def test_delete_missing_category_is_404(client):
    assert client.delete("/api/categories/999").status_code == 404


def test_delete_a_transfer_category_moves_both_legs(client):
    checking = account(client)
    savings = client.post("/api/accounts", json={"name": "Savings", "type": "savings"}).json()["id"]
    moves = create(client, "Moves", "transfer")
    other = create(client, "Savings moves", "transfer")
    client.post(
        "/api/transfers",
        json={"from_account_id": checking, "to_account_id": savings, "date": "2026-10-01",
              "amount_cents": 1000, "category_id": moves},
    )

    response = client.delete(f"/api/categories/{moves}?move_to={other}")

    assert response.json() == {"moved_transactions": 2}
    assert {t["category_id"] for t in client.get("/api/transactions").json()} == {other}
