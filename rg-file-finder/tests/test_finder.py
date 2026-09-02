import os
from pathlib import Path

import pytest

from finder import (
    MAX_KEYWORD_LENGTH,
    MAX_TOTAL_KEYWORDS,
    ExportResult,
    FinderError,
    SearchResult,
    export_files,
    generate_markdown,
    validate_config,
)


def base_config(tmp_path: Path) -> dict:
    return {
        "sources": [{"name": "project-a", "path": str(tmp_path)}],
        "extensions": ["sql", "java"],
        "include_keywords": ["policy"],
        "exclude_keywords": [],
        "exclude_folders": [],
        "search": {
            "ignore_case": True,
            "include_hidden": False,
            "respect_gitignore": True,
        },
        "security": {
            "allow_network_paths": False,
        },
        "output": {
            "folder": str(tmp_path / "out"),
            "preserve_structure": True,
            "overwrite": False,
            "md_filename": "search_result.md",
        },
    }


def test_validate_config_accepts_valid_config(tmp_path: Path) -> None:
    validate_config(base_config(tmp_path))


def test_validate_config_rejects_unsafe_source_name(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    config["sources"][0]["name"] = "../outside"

    with pytest.raises(FinderError):
        validate_config(config)


def test_validate_config_rejects_windows_reserved_names(tmp_path: Path) -> None:
    for reserved in ("CON", "nul.txt", "COM1", "LPT9.log"):
        config = base_config(tmp_path)
        config["sources"][0]["name"] = reserved

        with pytest.raises(FinderError):
            validate_config(config)


def test_validate_config_rejects_unsafe_markdown_filename(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    config["output"]["md_filename"] = "../outside.md"

    with pytest.raises(FinderError):
        validate_config(config)


def test_validate_config_rejects_reserved_markdown_filename(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    config["output"]["md_filename"] = "NUL.md"

    with pytest.raises(FinderError):
        validate_config(config)


def test_validate_config_rejects_non_boolean_search_option(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    config["search"]["ignore_case"] = "true"

    with pytest.raises(FinderError):
        validate_config(config)


def test_validate_config_rejects_unc_source_by_default(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    config["sources"][0]["path"] = r"\\server\share\project"

    with pytest.raises(FinderError):
        validate_config(config)


def test_validate_config_rejects_unc_output_by_default(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    config["output"]["folder"] = r"\\server\share\output"

    with pytest.raises(FinderError):
        validate_config(config)


def test_validate_config_can_explicitly_allow_network_paths(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    config["security"]["allow_network_paths"] = True
    config["sources"][0]["path"] = r"\\server\share\project"
    config["output"]["folder"] = r"\\server\share\output"

    validate_config(config)


def test_validate_config_rejects_glob_extension(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    config["extensions"] = ["*"]

    with pytest.raises(FinderError):
        validate_config(config)


def test_validate_config_rejects_glob_exclude_folder(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    config["exclude_folders"] = ["*"]

    with pytest.raises(FinderError):
        validate_config(config)


def test_validate_config_limits_keyword_count(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    config["include_keywords"] = [f"keyword-{index}" for index in range(MAX_TOTAL_KEYWORDS + 1)]

    with pytest.raises(FinderError):
        validate_config(config)


def test_validate_config_limits_keyword_length(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    config["include_keywords"] = ["x" * (MAX_KEYWORD_LENGTH + 1)]

    with pytest.raises(FinderError):
        validate_config(config)


def test_export_files_rejects_source_outside_source_root(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    outside = tmp_path / "outside.sql"
    outside.write_text("policy", encoding="utf-8")

    result = SearchResult(
        source_name="project-a",
        source_root=source_root,
        file_path=outside,
        matched_keywords=("policy",),
    )

    with pytest.raises(FinderError):
        export_files([result], {"folder": str(tmp_path / "out"), "overwrite": False})


def test_export_files_rejects_symlink_destination_escape(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source_file = source_root / "Policy.sql"
    source_file.write_text("policy", encoding="utf-8")

    output_root = tmp_path / "out"
    output_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = output_root / "project-a"

    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("此執行環境不允許建立目錄 symlink。")

    result = SearchResult(
        source_name="project-a",
        source_root=source_root,
        file_path=source_file,
        matched_keywords=("policy",),
    )

    with pytest.raises(FinderError):
        export_files(
            [result],
            {
                "folder": str(output_root),
                "preserve_structure": True,
                "overwrite": True,
            },
        )

    assert not (outside / "Policy.sql").exists()


def test_generate_markdown_creates_summary(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    source_file = tmp_path / "PolicyService.java"
    source_file.write_text("policy", encoding="utf-8")

    result = SearchResult(
        source_name="project-a",
        source_root=tmp_path,
        file_path=source_file,
        matched_keywords=("policy",),
    )
    exported = [
        ExportResult(
            search_result=result,
            destination=tmp_path / "out" / "project-a" / "PolicyService.java",
            copied=True,
        )
    ]

    md_path = generate_markdown(
        config=config,
        yaml_path=tmp_path / "config.yaml",
        total_results=1,
        exported=exported,
    )

    content = md_path.read_text(encoding="utf-8")
    assert "Total Matched: 1" in content
    assert "Selected: 1" in content
    assert "Copied: 1" in content
    assert "PolicyService.java" in content


def test_generate_markdown_respects_overwrite_false(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    output = Path(config["output"]["folder"])
    output.mkdir(parents=True)
    md_path = output / "search_result.md"
    md_path.write_text("do not replace", encoding="utf-8")

    with pytest.raises(FinderError):
        generate_markdown(
            config=config,
            yaml_path=tmp_path / "config.yaml",
            total_results=0,
            exported=[],
        )

    assert md_path.read_text(encoding="utf-8") == "do not replace"


def test_generate_markdown_allows_overwrite_when_enabled(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    config["output"]["overwrite"] = True
    output = Path(config["output"]["folder"])
    output.mkdir(parents=True)
    md_path = output / "search_result.md"
    md_path.write_text("old", encoding="utf-8")

    generated = generate_markdown(
        config=config,
        yaml_path=tmp_path / "config.yaml",
        total_results=0,
        exported=[],
    )

    assert generated == md_path
    assert "Total Matched: 0" in md_path.read_text(encoding="utf-8")


def test_generate_markdown_escapes_untrusted_text(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    config["include_keywords"] = ["safe\n## injected-heading"]

    md_path = generate_markdown(
        config=config,
        yaml_path=tmp_path / "config.yaml",
        total_results=0,
        exported=[],
    )

    content = md_path.read_text(encoding="utf-8")
    assert "\n## injected-heading" not in content
    assert "\\n\\#\\# injected\\-heading" in content
