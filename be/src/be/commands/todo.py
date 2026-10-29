"""`be todo`: todos kept as markdown files in todo.dir."""

from __future__ import annotations

import click

from be import config, todo

EMPTY = "no todos"


def dir_option():
    return config.option("todo.dir", "--dir", "root", help="Directory that holds the todos.")


@click.group(name="todo")
def todo_group() -> None:
    """Todos kept as markdown files."""


def todo_rows(todos: list[dict]) -> list[str]:
    """One aligned line per todo: id, due (! when overdue, x when done), priority, jira, tags, then title;
    a column no todo fills is left out."""
    cells = [
        (
            t["id"],
            ("x " if t["status"] == "done" else "! " if t["overdue"] else "  ") + (t["due"] or ""),
            t["priority"] or "",
            t["jira"] or "",
            " ".join(f"#{tag}" for tag in t["tags"]),
            t["title"],
        )
        for t in todos
    ]
    widths = [max(len(row[n].strip()) and len(row[n]) for row in cells) for n in range(5)]
    return [
        "  ".join([*(cell.ljust(w) for cell, w in zip(row, widths) if w), row[5]])
        for row in cells
    ]


@todo_group.command()
@click.argument("title", nargs=-1, required=True)
@click.option("-d", "--due", help="Due date: YYYY-MM-DD, today, tomorrow, +Nd or +Nw.")
@click.option("-p", "--priority", type=click.Choice(todo.PRIORITIES, case_sensitive=False))
@click.option("-t", "--tag", "tags", multiple=True, help="A tag; repeat for more.")
@click.option("-j", "--jira", "key", help="Jira issue key it's for.")
@click.option("-n", "--note", default="", help="Notes, the file's body.")
@dir_option()
def add(title: tuple[str, ...], due, priority, tags, key, note, root) -> None:
    """Add a todo titled TITLE and print its id."""
    added = todo.add(todo.todo_dir(root), " ".join(title), due, priority, tags, key, note)
    click.echo(added["id"])


@todo_group.command(name="list")
@click.option("--done", "only_done", is_flag=True, help="Only done todos.")
@click.option("-a", "--all", "show_all", is_flag=True, help="Include done todos.")
@click.option("-t", "--tag", help="Only todos with this tag.")
@click.option("-j", "--jira", "key", help="Only todos for this Jira issue.")
@dir_option()
def list_todos(only_done: bool, show_all: bool, tag, key, root) -> None:
    """List open todos, overdue then by due date and priority. Also available as ls."""
    todos = todo.list_todos(todo.todo_dir(root), show_all, only_done, tag, key)
    if not todos:
        click.echo(EMPTY)
        return
    for row in todo_rows(todos):
        click.echo(row)


@todo_group.command()
@click.argument("ref")
@dir_option()
def show(ref: str, root) -> None:
    """Print the todo's file. REF is its id or the start of one."""
    click.echo(todo.find(todo.todo_dir(root), ref).read_text(), nl=False)


@todo_group.command()
@click.argument("refs", nargs=-1, required=True)
@dir_option()
def done(refs: tuple[str, ...], root) -> None:
    """Mark todos done, moving them to done/."""
    for ref in refs:
        click.echo(f"done {todo.set_done(todo.todo_dir(root), ref)['id']}")


@todo_group.command()
@click.argument("ref")
@dir_option()
def reopen(ref: str, root) -> None:
    """Mark a done todo open again."""
    click.echo(f"reopened {todo.set_done(todo.todo_dir(root), ref, False)['id']}")


@todo_group.command()
@click.argument("ref")
@dir_option()
def edit(ref: str, root) -> None:
    """Open the todo's file in $EDITOR."""
    click.edit(filename=str(todo.find(todo.todo_dir(root), ref)))


@todo_group.command(name="rm")
@click.argument("ref")
@click.option("-y", "--yes", is_flag=True, help="Don't ask first.")
@dir_option()
def remove(ref: str, yes: bool, root) -> None:
    """Delete a todo's file."""
    path = todo.find(todo.todo_dir(root), ref)
    if not yes:
        click.confirm(f"Delete {path.stem}?", abort=True)
    click.echo(f"deleted {todo.remove(todo.todo_dir(root), path.stem)}")


@todo_group.command()
@dir_option()
def path(root) -> None:
    """Print the todo directory."""
    click.echo(todo.todo_dir(root))


todo_group.add_command(list_todos, name="ls")
