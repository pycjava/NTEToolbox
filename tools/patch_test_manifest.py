#!/usr/bin/env python3
"""给 Rust 测试 exe 注入 comctl32 v6 manifest（sandbox stripped image 专用）。

背景见 tools/run_rust_tests.sh。原地改写 RT_MANIFEST/1 资源数据：
保留 comctl32 v6 依赖，去掉可选设置以适配现有资源大小。
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pefile

NEW_MANIFEST = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">'
    "<dependency><dependentAssembly>"
    '<assemblyIdentity type="win32" name="Microsoft.Windows.Common-Controls" '
    'version="6.0.0.0" processorArchitecture="*" '
    'publicKeyToken="6595b64144ccf1df" language="*"/>'
    "</dependentAssembly></dependency></assembly>\n"
)


def patch(exe_path: Path) -> None:
    pe = pefile.PE(str(exe_path))

    def walk(entries) -> None:
        for entry in entries:
            if hasattr(entry, "directory"):
                walk(entry.directory.entries)
            else:
                offset = pe.get_offset_from_rva(entry.data.struct.OffsetToData)
                size = entry.data.struct.Size
                if len(NEW_MANIFEST) > size:
                    raise SystemExit(
                        f"{exe_path}: manifest resource too small ({size} bytes)"
                    )
                with exe_path.open("r+b") as f:
                    f.seek(offset)
                    f.write(NEW_MANIFEST.encode("utf-8"))
                    f.write(b" " * (size - len(NEW_MANIFEST)))
                print(f"patched manifest: {exe_path}")

    walk(pe.DIRECTORY_ENTRY_RESOURCE.entries)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch_test_manifest.py <exe>", file=sys.stderr)
        return 2
    exe = Path(sys.argv[1])
    if not exe.is_file():
        print(f"not found: {exe}", file=sys.stderr)
        return 2
    patch(exe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
