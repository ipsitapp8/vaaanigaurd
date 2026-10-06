"""Demo scenarios (SPEC section M): audio path, synthetic call metadata + transaction context,
expected tiers, and a sidecar transcript used only when ASR is unavailable."""
import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from app.config import REPO_ROOT
from app.models.schemas import CallMetadata, Tier, TransactionContext

SCENARIO_DIR = Path(__file__).resolve().parents[1] / "data" / "scenarios"
AUDIO_DIR = REPO_ROOT / "demo_audio"


class ScenarioSegment(BaseModel):
    text: str
    tts: str | None = None
    start: float = 0.0
    end: float = 0.0


class Scenario(BaseModel):
    id: str
    title: str
    persona: str
    description: str
    expected_tiers: list[Tier]
    audio: str
    language: str
    metadata: CallMetadata
    context: TransactionContext | None = None
    segments: list[ScenarioSegment]
    demo_verification: dict | None = None

    @property
    def audio_path(self) -> Path:
        return AUDIO_DIR / self.audio


class ScenarioSummary(BaseModel):
    id: str
    title: str
    persona: str
    description: str
    expected_tier: str  # e.g. "CRITICAL" or "HIGH/CRITICAL"
    duration_s: float


@lru_cache
def load_scenarios() -> dict[str, Scenario]:
    out: dict[str, Scenario] = {}
    for p in sorted(SCENARIO_DIR.glob("s*.json")):
        sc = Scenario(**json.loads(p.read_text(encoding="utf-8")))
        out[sc.id] = sc
    return out


def get_scenario(scenario_id: str) -> Scenario | None:
    return load_scenarios().get(scenario_id)


def summaries() -> list[ScenarioSummary]:
    return [
        ScenarioSummary(
            id=s.id,
            title=s.title,
            persona=s.persona,
            description=s.description,
            expected_tier="/".join(s.expected_tiers),
            duration_s=s.segments[-1].end if s.segments else 0.0,
        )
        for s in load_scenarios().values()
    ]
