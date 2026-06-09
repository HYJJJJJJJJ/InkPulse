from inkpulse_hub.collectors.todos import TodoStore


def test_add_list_toggle_delete(tmp_path):
    store = TodoStore(str(tmp_path / "todos.json"))
    item = store.add("写固件")
    assert item.text == "写固件" and item.done is False
    assert [t.text for t in store.list()] == ["写固件"]

    store.toggle(item.id)
    assert store.list()[0].done is True

    store.delete(item.id)
    assert store.list() == []


def test_persistence_across_instances(tmp_path):
    path = str(tmp_path / "todos.json")
    TodoStore(path).add("持久化")
    assert [t.text for t in TodoStore(path).list()] == ["持久化"]
