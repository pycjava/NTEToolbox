"""炉石传说 AI 教练模块。

只读的构筑模式 AI 教练：读炉石 Power.log 拿到游戏状态，每回合把合法可见的
局势 + 卡牌效果喂给 LLM，给出"这回合怎么打"的建议。绝不代打（合规红线）。

设计文档：.scratch/hearthstone-coach/spec.md
任务票：.scratch/hearthstone-coach/issues/
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
