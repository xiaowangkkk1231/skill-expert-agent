from app.core.clusters import cluster
from app.core.preprocess import preprocess
from app.core.quote_check import mark_verified
from app.core.signals import extract_rule, normalize
from app.samples import DATA, HIRING, SUPPORT
from app.schemas import Signal, SignalType


def extract(text: str):
    doc = preprocess(text)
    return doc, mark_verified(extract_rule(doc), doc.text)


def test_support_scene_extracts_rules():
    _, sigs = extract(SUPPORT)
    assert len(sigs) >= 7
    texts = " ".join(s.text for s in sigs)
    assert "复述" in texts
    assert SignalType.CONSTRAINT in {s.type for s in sigs}


def test_data_scene_keeps_business_terms():
    _, sigs = extract(DATA)
    texts = " ".join(s.text for s in sigs)
    assert "GMV" in texts
    assert "口径" in texts


def test_hiring_scene_detects_red_line():
    _, sigs = extract(HIRING)
    texts = " ".join(s.text for s in sigs)
    assert "婚育" in texts
    assert "候选人" in texts


def test_workflow_sequence_detected():
    """先……再…… 这类顺序要求应归到工作流。"""
    _, sigs = extract(SUPPORT)
    assert any(s.type == SignalType.WORKFLOW for s in sigs)


def test_limit_wording_wins_over_example():
    """带"必须"的句子即使举了"比如"，本质仍是约束。"""
    doc = preprocess("我：结尾必须给一个下一步动作，比如我现在帮您提交工单")
    sigs = extract_rule(doc)
    assert sigs and sigs[0].type == SignalType.CONSTRAINT


def test_all_quotes_are_verifiable():
    for sample in (SUPPORT, DATA, HIRING):
        _, sigs = extract(sample)
        assert sigs, "至少要抽到一条"
        assert all(s.verified for s in sigs), [s.text for s in sigs if not s.verified]


def test_quote_is_substring_of_conversation():
    doc, sigs = extract(SUPPORT)
    for s in sigs:
        assert s.quote in doc.text


def test_chitchat_yields_nothing():
    doc = preprocess("我：好的\n我：明白了\n我：谢谢\nAI：不客气")
    assert extract_rule(doc) == []


def test_task_request_is_not_a_signal():
    doc = preprocess("我：帮我写一段回复，安抚一下这个客户")
    assert extract_rule(doc) == []


def test_dedupe_merges_similar():
    doc = preprocess("我：每段不要超过两句话\n我：每段不要超过 2 句话，太长了\n我：不要用亲")
    sigs = extract_rule(doc)
    assert len([s for s in sigs if "两句话" in s.text or "2 句话" in s.text]) == 1


def test_normalize_strips_filler():
    assert normalize("我觉得，每段不要超过两句话吧") == "每段不要超过两句话"
    assert normalize("还补充一条，回复里不要出现大概这种词") == "回复里不要出现大概这种词"


def test_cluster_has_no_duplicates():
    _, sigs = extract(SUPPORT)
    cl = cluster(sigs)
    assert cl.constraints
    all_items = cl.constraints + cl.preferences + cl.workflows + cl.examples
    assert len(all_items) == len(set(all_items))


def test_sid_is_stable():
    a = Signal.build(text="不要用亲", quote="不要用亲，我们用您", stype="constraint")
    b = Signal.build(text="一律用您", quote="不要用亲，我们用您", stype="constraint")
    assert a.sid == b.sid
