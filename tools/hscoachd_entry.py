"""hscoachd 打包入口：炉石教练 headless 后端（客户端内置进程）。

与独立版 HsCoach 共用全部逻辑模块，只是不启动 tkinter UI：
客户端通过 `--no-overlay --publish-dir <目录>` 拉起它，消费 advice.json。
"""

from hscoach.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
