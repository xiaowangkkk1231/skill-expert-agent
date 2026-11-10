import asyncio
import json

from app import repo
from app.core import pipeline
from app.core.clusters import cluster
from app.core.compose import InsufficientSignals, compose, detect_domain
from app.samples import DATA, HIRING, SUPPORT
from app.schemas import Clusters


def test_detect_domain():
    assert detect_domain("公众号 文案 润色 标题")[0] == "content-writing"
    assert detect_domain("组件 重构 命名 提交")[0] == "code-review"
    assert detect_domain("完全无关的文本")[0] == ""


def test_compose_rejects_empty_clusters():
    try:
        compose(Clusters(), "随便一段话")
    except InsufficientSignals:
        return
    raise AssertionError("空 clusters 应该被拒绝")


def test_compose_builds_sections():
    cl = Clusters(
        constraints=["不要用赋能", "不要开场自我介绍"],
        preferences=["短句优先"],
        workflows=["先写钩子再展开"],
        examples=["我们用过 12 个工具，最后留下 3 个"],
    )
    skill = compose(cl, "公众号 写作 文案 段落 标题 润色")
    assert skill.name == "content-writing-rules"
    assert "适用于：" in skill.description
    assert "\n" not in skill.description
    for section in ("# Content Writing Rules", "## 必须避免", "## 风格要求",
                    "## 工作流", "## 示例对照"):
        assert section in skill.body


def _run(conversation: str, base_skill_id: str | None = None) -> str:
    run = repo.create_run(conversation, base_skill_id, "rule")
    asyncio.run(pipeline.execute(run.id, conversation, base_skill_id))
    return run.id


def test_pipeline_emits_full_event_sequence():
    run_id = _run(DATA)
    run = repo.get_run(run_id)
    assert run.status == "done"

    events = repo.events_since(run_id, 0)
    names = [e[1] for e in events]
    assert names[0] == "stage"
    assert "signal" in names
    assert "cluster" in names
    assert "field" in names
    assert "delta" in names
    assert "lint" in names
    assert names[-1] == "done"

    lens = [d for n, d in [(e[1], json.loads(e[2])) for e in events] if n == "lint"]
    assert lens[0]["level"] == "ok"


def test_pipeline_rejects_noise():
    run_id = _run("我：今天天气不错\n我：吃了么\nAI：吃了")
    assert repo.get_run(run_id).status == "failed"


def test_pipeline_accumulates_into_new_version():
    first = _run(SUPPORT)
    repo.update_run(first, status="done")
    payload = json.loads(repo.get_run(first).payload_json)
    skill_id = repo.save_version(
        skill_id=None, name=payload["skill"]["name"],
        description=payload["skill"]["description"], body=payload["skill"]["body"],
        clusters=payload["clusters"], signals=payload["signals"], diff=[],
        run_id=first,
    )
    ver = repo.get_version(skill_id)
    assert ver["version"] == 1

    second = _run(SUPPORT + "\n组长：话术里不要出现折扣两个字", base_skill_id=ver["skill_id"])
    events = repo.events_since(second, 0)
    assert any(e[1] == "diff" for e in events), "累积模式应该产出变化清单"

    payload2 = json.loads(repo.get_run(second).payload_json)
    assert len(payload2["signals"]) >= len(payload["signals"])


def test_save_creates_monotonic_versions():
    run_id = _run(HIRING)
    payload = json.loads(repo.get_run(run_id).payload_json)
    vid1 = repo.save_version(
        skill_id=None, name="demo-rules", description="演示用；适用于：测试。",
        body="# Demo\n\n## 必须避免\n- x\n", clusters={}, signals=[], diff=[], run_id=run_id,
    )
    v1 = repo.get_version(vid1)
    vid2 = repo.save_version(
        skill_id=v1["skill_id"], name="demo-rules", description="演示用；适用于：测试。",
        body="# Demo\n\n## 必须避免\n- x\n- y\n", clusters={}, signals=[], diff=[], run_id=run_id,
    )
    assert repo.get_version(vid2)["version"] == 2
    assert repo.get_skill(v1["skill_id"])["latest_v"] == 2


def test_signal_cluster_shape():
    run_id = _run(DATA)
    payload = json.loads(repo.get_run(run_id).payload_json)
    cl = cluster([])
    assert cl.is_empty()
    assert payload["clusters"]["constraints"]
    assert all(s["verified"] for s in payload["signals"])
