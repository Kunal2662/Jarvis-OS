"""Local model tiers and recommendation -- M22 Task Group A.

**Recommendation only. This module downloads nothing** and knows no
download URL -- provisioning is a later task group, and a module that
could start a multi-gigabyte transfer is a module somebody eventually
calls by accident.

The user never sees a model name unless they ask for it. The tier is
what the installer shows ("Standard"); the concrete model id is carried
alongside for the Administrator view and for whatever actually fetches
it later. That split is `ARCHITECTURE.md` §22.11's "normal users never
see provider information", applied to models.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

#: **Decimal** GB, deliberately, and this is load-bearing.
#:
#: RAM is sold and described in decimal GB: a "16 GB" machine has
#: 16e9 bytes, which is only 15.7 *GiB*. Comparing that against a
#: binary 16 GiB threshold means a genuine 16 GB machine misses the
#: 16 GB tier and is offered the 8 GB one instead -- and every 16 GB
#: machine on earth would, since none of them ever reports 16.0 GiB.
#:
#: Found by running detection on a real 16 GB laptop, which came back
#: 15.7 and was recommended Small. The tier thresholds are written in
#: the same units the user's machine is advertised in.
_BYTES_PER_GB_DECIMAL = 1_000_000_000

#: Binary GiB, for figures conventionally shown that way (VRAM, download
#: sizes as reported by model registries).
_BYTES_PER_GIB = 1024**3


@dataclass(frozen=True, slots=True)
class ModelTier:
    key: str
    """Stable identifier -- `tiny`, `small`, `standard`, `advanced`."""
    label: str
    """What the installer shows a personal user."""
    minimum_ram_gb: int
    """Inclusive floor. A machine at exactly this figure qualifies."""
    approximate_download_gb: float
    """So the Summary step can state what installation will cost in
    bandwidth and disk before anyone commits to it."""
    model_id: str
    """The concrete model. Administrator-facing only."""
    description: str


# Ordered smallest-first; `recommend_model` relies on the ordering.
#
# The thresholds are the ones the milestone brief fixes (4 / 8 / 16 /
# 32 GB). They are deliberately conservative: the figure is *total system
# RAM*, and a model also needs room for the OS, the browser the user is
# reading this in, and JARVIS itself.
MODEL_TIERS: tuple[ModelTier, ...] = (
    ModelTier(
        key="tiny",
        label="Tiny",
        minimum_ram_gb=4,
        approximate_download_gb=0.7,
        model_id="qwen2.5:0.5b",
        description="Runs comfortably on modest hardware. Best for short questions and commands.",
    ),
    ModelTier(
        key="small",
        label="Small",
        minimum_ram_gb=8,
        approximate_download_gb=1.9,
        model_id="llama3.2:3b",
        description="A good everyday balance of speed and quality.",
    ),
    ModelTier(
        key="standard",
        label="Standard",
        minimum_ram_gb=16,
        approximate_download_gb=4.7,
        model_id="llama3.1:8b",
        description="Stronger reasoning and longer context. The default for most machines.",
    ),
    ModelTier(
        key="advanced",
        label="Advanced",
        minimum_ram_gb=32,
        approximate_download_gb=9.0,
        model_id="qwen2.5:14b",
        description="Highest local quality. Best with a dedicated GPU.",
    ),
)

_BY_KEY = {tier.key: tier for tier in MODEL_TIERS}


class InsufficientMemoryError(Exception):
    """Raised when the machine is below even the smallest tier."""


def recommend_model(total_ram_bytes: int, *, vram_bytes: int | None = None) -> ModelTier:
    """The largest tier this machine can hold.

    RAM is the primary input because it is the one figure that is
    reliably measurable on every platform (see
    :mod:`jarvis.installer.hardware` on why VRAM often is not).

    VRAM only ever *promotes*, never demotes: a machine with 16 GB RAM
    and a 12 GB GPU can run the Advanced tier that RAM alone would deny
    it, but a machine with plenty of RAM and no measurable GPU is not
    punished for a probe that could not answer. Promotion is capped at
    one tier -- a large GPU does not make up for a system that will swap.
    """
    # Decimal, matching how the machine's RAM is advertised -- see the
    # constant's own note for why this is not a detail.
    ram_gb = total_ram_bytes / _BYTES_PER_GB_DECIMAL

    eligible = [tier for tier in MODEL_TIERS if ram_gb >= tier.minimum_ram_gb]
    if not eligible:
        raise InsufficientMemoryError(
            f"{ram_gb:.1f} GB of RAM is below the {MODEL_TIERS[0].minimum_ram_gb} GB "
            f"minimum for the smallest local model."
        )

    chosen = eligible[-1]

    if vram_bytes is not None:
        # VRAM stays binary: it is reported in MiB by every vendor tool
        # this project reads, and compared against download sizes that
        # are likewise GiB.
        vram_gb = vram_bytes / _BYTES_PER_GIB
        # A GPU that can hold the next tier's weights *plus working
        # memory* earns the promotion. The 1.2 multiplier is the KV
        # cache and runtime overhead on top of the weights; a stricter
        # 1.4 would deny a 12 GB card the 9 GB Advanced model, which is
        # precisely the pairing that should qualify.
        index = MODEL_TIERS.index(chosen)
        if index + 1 < len(MODEL_TIERS):
            next_tier = MODEL_TIERS[index + 1]
            if vram_gb >= next_tier.approximate_download_gb * 1.2:
                chosen = next_tier

    return chosen


def tier_by_key(key: str) -> ModelTier:
    """Look up a tier an Administrator overrode to."""
    try:
        return _BY_KEY[key]
    except KeyError as err:
        raise KeyError(f"Unknown model tier {key!r}. Known: {sorted(_BY_KEY)}") from err


def tier_to_dict(tier: ModelTier, *, include_model_id: bool) -> dict[str, Any]:
    """*include_model_id* is ``False`` for a personal user.

    Not cosmetic: §22.11 says normal users never see provider or model
    detail, and the cleanest way to honour that is for the payload the
    personal installer receives to genuinely not contain it.
    """
    data = asdict(tier)
    if not include_model_id:
        data.pop("model_id")
    return data
