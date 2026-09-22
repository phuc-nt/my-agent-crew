from pathlib import Path

from my_agent_crew.agents.profile_write import (
    create_agent_dir,
    read_raw,
    trash_agent,
    write_raw,
)
from my_agent_crew.agents.profile_yaml import load_yaml_profiles
from my_agent_crew.config import load_settings

HAND_WRITTEN = """\
# Trợ lý chính
name: Trợ lý
# giữ mức này cho tới khi thấy đủ
cost_cap_usd: 2.0
delegates:
  - coder
"""


def test_editing_one_key_keeps_the_comments_and_the_rest(tmp_path: Path) -> None:
    manifest = tmp_path / "agent.yaml"
    manifest.write_text(HAND_WRITTEN, encoding="utf-8")

    data = read_raw(manifest)
    data["cost_cap_usd"] = 5.0
    write_raw(manifest, data)

    written = manifest.read_text(encoding="utf-8")
    assert "cost_cap_usd: 5.0" in written
    assert "# Trợ lý chính" in written
    assert "# giữ mức này cho tới khi thấy đủ" in written
    assert "- coder" in written


def test_a_key_this_version_does_not_know_survives_a_write(tmp_path: Path) -> None:
    # Someone on a newer build, or a key added by hand ahead of the code, must not be
    # silently dropped by an edit made from an older web UI.
    manifest = tmp_path / "agent.yaml"
    manifest.write_text("name: Trợ lý\nexperimental_thing: yes\n", encoding="utf-8")

    data = read_raw(manifest)
    data["name"] = "Thư ký"
    write_raw(manifest, data)

    assert "experimental_thing" in manifest.read_text(encoding="utf-8")


def test_writing_leaves_no_partial_file_behind(tmp_path: Path) -> None:
    manifest = tmp_path / "agent.yaml"
    write_raw(manifest, {"name": "Trợ lý"})

    assert manifest.read_text(encoding="utf-8") == "name: Trợ lý\n"
    # The temp file the write goes through is moved, not copied, so nothing is left in
    # the folder that a directory scan would later mistake for a manifest.
    assert [p.name for p in tmp_path.iterdir()] == ["agent.yaml"]


def test_an_absent_manifest_reads_as_an_empty_mapping(tmp_path: Path) -> None:
    assert dict(read_raw(tmp_path / "nope.yaml")) == {}


def test_a_new_agent_gets_a_workspace_to_run_in(tmp_path: Path) -> None:
    directory = create_agent_dir(tmp_path, "coder")

    assert directory == tmp_path / "agents" / "coder"
    assert (directory / "workspace").is_dir()


def test_removing_an_agent_keeps_its_files_and_hides_it_from_the_crew(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    directory = create_agent_dir(home, "coder")
    write_raw(directory / "agent.yaml", {"name": "Coder"})
    (directory / "AGENTS.md").write_text("ghi chú tay", encoding="utf-8")
    settings = load_settings(env={"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"})
    assert [p.id for p in load_yaml_profiles(settings)] == ["default", "coder"]

    trashed = trash_agent(home, "coder")

    assert not directory.exists()
    assert (trashed / "AGENTS.md").read_text(encoding="utf-8") == "ghi chú tay"
    # The folder still holds an agent.yaml, so the crew has to skip it by location.
    assert [p.id for p in load_yaml_profiles(settings)] == ["default"]


def test_removing_the_same_id_twice_does_not_overwrite_the_first(tmp_path: Path) -> None:
    home = tmp_path / "home"
    for body in ("lần một", "lần hai"):
        directory = create_agent_dir(home, "coder")
        (directory / "AGENTS.md").write_text(body, encoding="utf-8")
        trash_agent(home, "coder")

    saved = sorted(
        p.read_text(encoding="utf-8")
        for p in (home / "agents" / ".trash").glob("coder-*/AGENTS.md")
    )
    assert saved == ["lần hai", "lần một"]
