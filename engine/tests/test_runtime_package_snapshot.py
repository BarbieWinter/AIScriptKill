import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Executable

from engine.core.package_loader import load_package_directory
from engine.core.package_multiplayer import (
    PackageMultiplayerError,
    first_multiplayer_stage_from_package,
    multiplayer_package_playability,
    multiplayer_policy_from_package,
    multiplayer_stage_definition,
    multiplayer_stage_from_package,
    multiplayer_stages_from_package,
)
from engine.core.package_schema import (
    CharacterChapterRecord,
    EvidenceRecord,
    MediaRecord,
    ScriptPackageImport,
)
from engine.core.runtime_package_snapshot import (
    RuntimePackageSnapshotError,
    canonical_runtime_package_bytes,
    decode_runtime_package_snapshot,
    encode_runtime_package_snapshot,
    runtime_package_sha256,
)
from engine.repositories.runtime_package_repository import get_runtime_package
from engine.tests.stategraph_fixtures import state_graph_package

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "script-packages" / "mp1-two-player"


def _two_player_package() -> ScriptPackageImport:
    original = state_graph_package()
    config = dict(original.package.config)
    info = dict(config["info"])
    info["min_players"] = 2
    info["max_players"] = 2
    config["info"] = info
    config["multiplayer"] = {
        "min_players": 2,
        "max_players": 2,
        "character_assignment": "required",
        "start_policy": "all_players_ready",
        "duplicate_characters": False,
    }
    package_record = replace(original.package, config=config)
    return replace(
        original,
        package=package_record,
        characters=tuple(replace(character, is_playable=True) for character in original.characters),
        chapters=(
            CharacterChapterRecord(
                id="player-prologue",
                character_id="player",
                sort_order=0,
                title="玩家序章",
                visibility="character_only",
                release={"stage": "prologue"},
                stage_min="prologue",
                content="秘密章节",
            ),
        ),
        evidences=(
            EvidenceRecord(
                id="knife",
                name="刀",
                image_url=None,
                description_surface="一把刀",
                description_deep="有缺口",
                type="prop",
                metadata={"weight": 1.5},
            ),
        ),
        media_assets=original.media_assets
        + (
            MediaRecord(
                id="scene-image",
                type="image",
                file_url="/assets/场景.jpg",
                subtitle_url=None,
                duration_sec=None,
                metadata={"alt": "雪乡"},
            ),
        ),
        warnings=("import-only warning",),
    )


def test_snapshot_round_trip_is_canonical_and_excludes_import_only_fields() -> None:
    package = _two_player_package()

    snapshot = encode_runtime_package_snapshot(package)
    decoded = decode_runtime_package_snapshot(snapshot.payload, snapshot.sha256)

    assert decoded == replace(package, assets=(), warnings=())
    assert "assets" not in snapshot.payload
    assert "warnings" not in snapshot.payload
    assert snapshot.payload["snapshot_schema_version"] == 1
    assert canonical_runtime_package_bytes(package).decode("utf-8").startswith('{"chapters":[')
    assert b'": ' not in canonical_runtime_package_bytes(package)
    assert b', "' not in canonical_runtime_package_bytes(package)
    assert snapshot.sha256 == runtime_package_sha256(package)
    assert len(snapshot.sha256) == 64


def test_multiplayer_playability_is_identical_after_snapshot_round_trip() -> None:
    package = load_package_directory(PACKAGE_ROOT, publish=True)
    before = multiplayer_package_playability(package)

    snapshot = encode_runtime_package_snapshot(package)
    decoded = decode_runtime_package_snapshot(snapshot.payload, snapshot.sha256)

    assert multiplayer_package_playability(decoded) == before
    assert before.playable is True


def test_snapshot_encoding_is_stable_for_mapping_key_order_and_unicode() -> None:
    package = _two_player_package()
    reordered_config = dict(reversed(tuple(package.package.config.items())))
    reordered = replace(package, package=replace(package.package, config=reordered_config))

    assert canonical_runtime_package_bytes(reordered) == canonical_runtime_package_bytes(package)
    assert "雪乡" in canonical_runtime_package_bytes(package).decode("utf-8")


@pytest.mark.parametrize(
    ("mutation", "field"),
    [
        (lambda payload: payload.pop("stages"), "snapshot.stages"),
        (lambda payload: payload.__setitem__("unexpected", True), "snapshot"),
        (
            lambda payload: payload["package"].__setitem__("unexpected", True),
            "snapshot.package",
        ),
        (
            lambda payload: payload["stages"][0].__setitem__("sort_order", "0"),
            "snapshot.stages[0].sort_order",
        ),
    ],
)
def test_snapshot_decode_rejects_missing_unknown_and_malformed_fields(
    mutation: Callable[[dict[str, Any]], object], field: str
) -> None:
    snapshot = encode_runtime_package_snapshot(_two_player_package())
    mutation(snapshot.payload)
    digest = hashlib.sha256(
        json.dumps(
            snapshot.payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    with pytest.raises(RuntimePackageSnapshotError) as exc_info:
        decode_runtime_package_snapshot(snapshot.payload, digest)

    assert exc_info.value.field == field


def test_snapshot_decode_rejects_digest_mismatch_and_noncanonical_digest() -> None:
    snapshot = encode_runtime_package_snapshot(_two_player_package())

    with pytest.raises(RuntimePackageSnapshotError, match="sha256"):
        decode_runtime_package_snapshot(snapshot.payload, "0" * 64)
    with pytest.raises(RuntimePackageSnapshotError, match="sha256"):
        decode_runtime_package_snapshot(snapshot.payload, snapshot.sha256.upper())


def test_snapshot_decode_rejects_non_finite_json_numbers() -> None:
    snapshot = encode_runtime_package_snapshot(_two_player_package())
    snapshot.payload["package"]["config"]["bad"] = float("nan")

    with pytest.raises(RuntimePackageSnapshotError, match="json"):
        decode_runtime_package_snapshot(snapshot.payload, snapshot.sha256)


def test_two_player_policy_reuses_manifest_player_limits_and_playable_characters() -> None:
    policy = multiplayer_policy_from_package(_two_player_package())

    assert policy.min_players == 2
    assert policy.max_players == 2
    assert policy.character_assignment == "required"
    assert policy.start_policy == "all_players_ready"
    assert policy.duplicate_characters is False
    assert policy.playable_character_ids == ("player", "npc")


def test_multiplayer_stages_use_authoritative_stage_index_order() -> None:
    package = _two_player_package()
    reordered = replace(package, stages=tuple(reversed(package.stages)))

    stages = multiplayer_stages_from_package(reordered)

    assert tuple(stage.id for stage in stages) == ("prologue", "act1", "review")
    assert first_multiplayer_stage_from_package(reordered).id == "prologue"
    assert multiplayer_stage_from_package(reordered, "act1").id == "act1"
    assert multiplayer_stage_definition(reordered, "act1") == stages[1].definition
    assert multiplayer_stage_definition(reordered, "act1") is not stages[1].definition


def test_two_player_policy_rejects_non_exact_or_inconsistent_policy() -> None:
    package = _two_player_package()
    config = dict(package.package.config)
    multiplayer = dict(config["multiplayer"])
    multiplayer["max_players"] = 3
    config["multiplayer"] = multiplayer
    invalid = replace(package, package=replace(package.package, config=config))

    with pytest.raises(PackageMultiplayerError, match="multiplayer.max_players"):
        multiplayer_policy_from_package(invalid)


def test_multiplayer_stage_extraction_rejects_record_index_drift() -> None:
    package = _two_player_package()
    stages = (replace(package.stages[0], sort_order=99), *package.stages[1:])

    with pytest.raises(PackageMultiplayerError, match="stage.prologue.sort_order"):
        multiplayer_stages_from_package(replace(package, stages=stages))
    with pytest.raises(PackageMultiplayerError, match="stage.missing"):
        multiplayer_stage_from_package(package, "missing")


class _NoPackageResult:
    def mappings(self) -> "_NoPackageResult":
        return self

    def one_or_none(self) -> None:
        return None


class _CapturingDb:
    def __init__(self) -> None:
        self.statement: Executable | None = None

    async def execute(self, statement: Executable) -> _NoPackageResult:
        self.statement = statement
        return _NoPackageResult()


async def test_runtime_package_repository_can_lock_package_row_for_shared_read() -> None:
    fake_db = _CapturingDb()

    package = await get_runtime_package(
        cast(AsyncSession, cast(object, fake_db)),
        "minimal-case",
        lock_existing=True,
    )

    assert package is None
    assert fake_db.statement is not None
    sql = str(fake_db.statement.compile(dialect=postgresql.dialect()))
    assert "FOR SHARE" in sql
