from pathlib import Path

DOC = (Path(__file__).resolve().parents[1] / "docs" / "manual-test-checklist.md").read_text(encoding="utf-8")


def test_the_checklist_covers_every_segment_and_the_cross_cutting_areas():
    for heading in ("## 1. Install", "## 2. Activation", "## 3. Onboarding", "## 4. Grocery", "## 5. Electronics",
                    "## 6. Languages", "## 7. Licence expiry", "## 8. Backup", "## 9. Hardware", "## 10. Upgrade",
                    "## 11. Sign-off"):
        assert heading in DOC, heading


def test_the_checklist_has_enough_checks_and_none_are_pre_ticked():
    assert len([l for l in DOC.splitlines() if l.startswith("- [ ]")]) >= 60
    assert "[x]" not in DOC.lower()
