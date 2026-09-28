from runtime.obsidian_exporter import ObsidianExporter


def test_write_note_success(tmp_path):
    exporter = ObsidianExporter(tmp_path)
    path = exporter.write_note("00-Inbox", "测试笔记", "正文内容", "test", ["demo"])

    assert path.exists()
    assert "正文内容" in path.read_text(encoding="utf-8")


def test_invalid_filename_is_cleaned(tmp_path):
    exporter = ObsidianExporter(tmp_path)
    path = exporter.write_note("00-Inbox", '非法/文件:名*?"<>|', "正文内容", "test", ["demo"])

    assert path.exists()
    assert "/" not in path.name
    assert ":" not in path.name
    assert "*" not in path.name


def test_frontmatter_exists(tmp_path):
    exporter = ObsidianExporter(tmp_path)
    path = exporter.write_note("00-Inbox", "frontmatter 测试", "正文内容", "test", ["demo"])
    text = path.read_text(encoding="utf-8")

    assert text.startswith("---\n")
    assert "type: test" in text
    assert "tags:" in text
