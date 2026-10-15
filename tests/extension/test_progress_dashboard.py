from pathlib import Path

ROOT = Path(__file__).parents[2]
DASHBOARD = ROOT / "docs" / "progress" / "v0.1.6-alpha.html"


def test_visual_progress_dashboard_tracks_release_and_global_roadmap() -> None:
    assert DASHBOARD.is_file()
    source = DASHBOARD.read_text(encoding="utf-8")
    assert "AluDIY Designer" in source
    assert "v0.1.6-alpha" in source
    assert "精确修改与尺寸" in source
    assert "节点坐标" in source
    assert "固定起端" in source
    assert "临时参考尺寸" in source
    assert "远程更新" in source
    assert "已完成" in source
    assert "开发中" in source
    assert "待开发" in source
    assert "v0.1.7" in source
    assert "完整工程吸附" in source
    assert "v0.2.0" in source
    assert "节点与自动退让" in source
    assert "v0.3.0" in source
    assert "板材与家居构件" in source
    assert "v0.4.0" in source
    assert "BOM、加工与安装" in source
