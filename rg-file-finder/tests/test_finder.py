import os
from pathlib import Path

import pytest

from finder import (
    MAX_KEYWORD_LENGTH,
    MAX_TOTAL_KEYWORDS,
    MAX_YAML_BYTES,
    ExportResult,
    FinderError,
    SearchResult,
    export_files,
    generate_markdown,
    load_config,
    validate_config,
)


def base_config(tmp_path: Path) -> dict:
    source_root = tmp_path / "source"
    source_root.mkdir(exist_ok=True)
    return {
        "sources": [{"name": "project-a", "path": str(source_root)}],
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
            "overwrite_files": False,
            "overwrite_report": True,
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


def test_validate_config_rejects_duplicate_source_names_case_insensitive(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    second_root = tmp_path / "source-b"
    second_root.mkdir()
    config["sources"].append({"name": "PROJECT-A", "path": str(second_root)})

    with pytest.raises(FinderError, match="source.name 必須唯一"):
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


def test_validate_config_rejects_non_boolean_overwrite_option(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    config["output"]["overwrite_report"] = "true"

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


def test_validate_config_rejects_output_inside_source(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    source_root = Path(config["sources"][0]["path"])
    config["output"]["folder"] = str(source_root / "generated")

    with pytest.raises(FinderError, match="不可互相包含"):
        validate_config(config)


def test_validate_config_rejects_source_inside_output(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    output_root = tmp_path / "output-root"
    source_root = output_root / "source"
    source_root.mkdir(parents=True)
    config["sources"][0]["path"] = str(source_root)
    config["output"]["folder"] = str(output_root)

    with pytest.raises(FinderError, match="不可互相包含"):
        validate_config(config)


def test_validate_config_rejects_same_source_and_output(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    config["output"]["folder"] = config["sources"][0]["path"]

    with pytest.raises(FinderError, match="不可互相包含"):
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


def test_load_config_rejects_oversized_yaml_before_parsing(tmp_path: Path) -> None:
    config_path = tmp_path / "large.yaml"
    config_path.write_bytes(b"#" * (MAX_YAML_BYTES + 1))

    with pytest.raises(FinderError, match="YAML 檔案過大"):
        load_config(config_path)


def test_export_files_rejects_source_outside_source_root(tmp_path: Path) -> None:
    source_root = tmp_path / "source-export"
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
        export_files(
            [result],
            {"folder": str(tmp_path / "out-export"), "overwrite_files": False},
        )


def test_export_files_rejects_symlink_destination_escape(tmp_path: Path) -> None:
    source_root = tmp_path / "source-export"
    source_root.mkdir()
    source_file = source_root / "Policy.sql"
    source_file.write_text("policy", encoding="utf-8")

    output_root = tmp_path / "out-export"
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
                "overwrite_files": True,
            },
        )

    assert not (outside / "Policy.sql").exists()


def test_export_files_respects_overwrite_files_false(tmp_path: Path) -> None:
    source_root = tmp_path / "source-export"
    source_root.mkdir()
    source_file = source_root / "Policy.sql"
    source_file.write_text("new", encoding="utf-8")
    output_root = tmp_path / "out-export"
    destination = output_root / "project-a" / "Policy.sql"
    destination.parent.mkdir(parents=True)
    destination.write_text("old", encoding="utf-8")

    result = SearchResult("project-a", source_root, source_file, ("policy",))
    exported = export_files(
        [result],
        {"folder": str(output_root), "preserve_structure": True, "overwrite_files": False},
    )

    assert exported[0].copied is False
    assert destination.read_text(encoding="utf-8") == "old"


def test_export_files_new_setting_overrides_legacy_overwrite(tmp_path: Path) -> None:
    source_root = tmp_path / "source-export"
    source_root.mkdir()
    source_file = source_root / "Policy.sql"
    source_file.write_text("new", encoding="utf-8")
    output_root = tmp_path / "out-export"
    destination = output_root / "project-a" / "Policy.sql"
    destination.parent.mkdir(parents=True)
    destination.write_text("old", encoding="utf-8")

    result = SearchResult("project-a", source_root, source_file, ("policy",))
    export_files(
        [result],
        {
            "folder": str(output_root),
            "preserve_structure": True,
            "overwrite": True,
            "overwrite_files": False,
        },
    )

    assert destination.read_text(encoding="utf-8") == "old"


def test_generate_markdown_creates_summary(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    source_root = Path(config["sources"][0]["path"])
    source_file = source_root / "PolicyService.java"
    source_file.write_text("policy", encoding="utf-8")

    result = SearchResult(
        source_name="project-a",
        source_root=source_root,
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


def test_generate_markdown_respects_overwrite_report_false(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    config["output"]["overwrite_report"] = False
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


def test_generate_markdown_defaults_to_report_overwrite_for_new_config(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    config["output"].pop("overwrite_report")
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


def test_generate_markdown_legacy_overwrite_false_remains_compatible(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    config["output"].pop("overwrite_files")
    config["output"].pop("overwrite_report")
    config["output"]["overwrite"] = False
    output = Path(config["output"]["folder"])
    output.mkdir(parents=True)
    md_path = output / "search_result.md"
    md_path.write_text("legacy", encoding="utf-8")

    with pytest.raises(FinderError):
        generate_markdown(
            config=config,
            yaml_path=tmp_path / "config.yaml",
            total_results=0,
            exported=[],
        )

    assert md_path.read_text(encoding="utf-8") == "legacy"


def test_generate_markdown_new_setting_overrides_legacy_overwrite(tmp_path: Path) -> None:
    config = base_config(tmp_path)
    config["output"]["overwrite"] = False
    config["output"]["overwrite_report"] = True
    output = Path(config["output"]["folder"])
    output.mkdir(parents=True)
    md_path = output / "search_result.md"
    md_path.write_text("old", encoding="utf-8")

    generate_markdown(
        config=config,
        yaml_path=tmp_path / "config.yaml",
        total_results=0,
        exported=[],
    )

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
