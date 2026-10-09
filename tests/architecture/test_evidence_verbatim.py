"""Every rule's evidence is a verbatim sentence of its policy document (T015, FR-018, SC-005)."""

import re

from expense_validator.adapters.config_files import rules_version
from expense_validator.domain.engine.registry import REGISTRY
from expense_validator.paths import POLICY_DIR

IN_SCOPE = {
    "MEAL-01", "MEAL-02", "ALC-01", "ALC-02", "ALC-03", "ENT-01", "ENT-02",
    "TECH-01", "TECH-02", "TECH-03", "TECH-04",
    "GIFT-01", "GIFT-02", "GIFT-03", "GIFT-04",
    "PERS-01", "PERS-02", "PERS-03", "HOUSE-01", "HEALTH-01", "LAUNDRY-01",
    "MCC-01", "MCC-02", "MCC-03",
    "DOC-01", "DOC-02", "DOC-03", "DOC-04",
    "REG-01", "REG-02", "REG-03", "REG-04", "REG-05",
    "EXC-01", "EXC-02", "EXC-03", "EXC-04",
}  # fmt: skip


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("**", "")).strip()


def test_registry_holds_exactly_the_37_in_scope_rules() -> None:
    assert set(REGISTRY) == IN_SCOPE
    assert not any(rule_id.startswith("TIME-") for rule_id in REGISTRY)


def test_every_evidence_is_verbatim() -> None:
    missing = []
    for spec in REGISTRY.values():
        doc = _flat((POLICY_DIR / spec.policy_doc).read_text(encoding="utf-8"))
        for key, sentence in {"default": spec.evidence, **spec.evidence_variants}.items():
            if _flat(sentence) not in doc:
                missing.append(f"{spec.rule_id}:{key}")
    assert missing == []


def test_exception_rules_have_a_severity_and_others_do_not() -> None:
    for spec in REGISTRY.values():
        assert (spec.kind == "exception") == (spec.severity is not None), spec.rule_id


def test_rule_ids_match_their_documents() -> None:
    for spec in REGISTRY.values():
        doc = (POLICY_DIR / spec.policy_doc).read_text(encoding="utf-8")
        assert spec.rule_id in doc


def test_rules_version_is_stable_and_short() -> None:
    first = rules_version()
    assert first == rules_version()
    assert re.fullmatch(r"[0-9a-f]{12}", first)
