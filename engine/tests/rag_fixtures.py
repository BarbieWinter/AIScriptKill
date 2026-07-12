from engine.core.package_loader import load_package_archive
from engine.core.package_schema import ScriptPackageImport
from engine.tests.package_loader_fixtures import minimal_package_files, package_archive


def rag_package() -> ScriptPackageImport:
    files = minimal_package_files()
    files["endings.yml"] = files["endings.yml"].replace(
        'outcome_text: "真相已经揭开。"',
        'outcome_text: "真相已经揭开，NPC角色是凶手。"',
    )
    files["dm_guide/truth.yml"] = (
        'truth:\n  murderer: "npc"\n  case_summary: "NPC角色是凶手，最终答案只允许 DM 检索。"\n'
    )
    return load_package_archive(package_archive(files))
