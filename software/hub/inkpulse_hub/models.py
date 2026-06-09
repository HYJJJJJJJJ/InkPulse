# inkpulse_hub/models.py
from dataclasses import dataclass
from typing import Optional

ATTENTION_STATES = {"waiting_for_input", "error"}
VALID_STATES = {"idle", "working", "waiting_for_input", "done", "error"}


@dataclass
class ClaudeStatus:
    state: str = "idle"
    project: Optional[str] = None
    since: Optional[float] = None  # epoch 秒

    def needs_attention(self) -> bool:
        return self.state in ATTENTION_STATES


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_tokens: int = 0
    cost_usd: float = 0.0
    session_count: int = 0
    window_used_ratio: Optional[float] = None  # 0..1，None 表示 n/a

    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class TodoItem:
    id: str
    text: str
    done: bool = False


@dataclass
class Photo:
    path: str
