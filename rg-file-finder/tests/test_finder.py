from pathlib import Path

import pytest

from finder import ExportResult, FinderError, SearchResult, generate_markdown, validate_config


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


def test_validate_config_rejects_unsafe_markdown_filename(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    config["output"]["md_filename"] = "../outside.md"

    with pytest.raises(FinderError):
        validate_config(config)


def test_validate_config_rejects_non_boolean_search_option(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    config["search"]["ignore_case"] = "true"

    with pytest.raises(FinderError):
        validate_config(config)


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
