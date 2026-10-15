"""Regression checks for the landing-page canvas startup path."""
from pathlib import Path
import server


def main():
    # README/启动脚本约定默认只统计当前 Work space，防止范围悄悄回到全部目录。
    assert server.collectors.ALL_AGENTS is False

    html = Path(__file__).with_name("index.html").read_text(encoding="utf-8")

    # addPath belongs to Path2D, not CanvasRenderingContext2D. Calling the
    # latter aborts the animation's first frame and leaves the landing page blank.
    assert "ctx.addPath(" not in html
    # Landing canvas must bootstrap: canvas element -> 2d context -> animation loop
    assert "const canvas = document.getElementById('eirdisCanvas');" in html
    assert "const ctx = canvas.getContext('2d');" in html
    assert "requestAnimationFrame(renderEirdis);" in html
    assert "renderEirdis();" in html

    print("FRONTEND RUNTIME CHECK PASSED")


if __name__ == "__main__":
    main()
