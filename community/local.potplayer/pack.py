"""将本插件打成可上传安装的 zip。

用法 (在仓库根目录):
    uv run python community/local.potplayer/pack.py
"""

from __future__ import annotations

import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "local.potplayer.zip"
# 只打入运行所需文件; README / 参考文档留在源码树里.
INCLUDE = ("plugin.py",)


def main() -> None:
    OUT.unlink(missing_ok=True)
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in INCLUDE:
            archive.write(HERE / name, arcname=f"local.potplayer/{name}")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
