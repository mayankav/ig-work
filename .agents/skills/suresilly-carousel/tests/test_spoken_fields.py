"""Current When/Say labels must not bypass checks written for old labels."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import writer


SOURCE = "- **Source:** — Susan Nolen-Hoeksema, *Women Who Think Too Much* (2003)"


def test_supplied_researcher_explanation_is_not_speech():
    markdown = ("### Slide 3 · Source\n" + SOURCE + "\n### Slide 5 · Script\n"
        '- **Say:** "Say that out loud once the document has been closed, because '
        'Nolen-Hoeksema found that going over things keeps the mood low."\n')
    faults = writer.check_repeats(markdown)
    assert any("researcher is credited on slide 3" in f for f in faults)


@pytest.mark.parametrize("label", ["Say", "When", "✅ Regulated Response", "❌ Old Reaction"])
def test_repeated_line_uses_current_and_legacy_labels(label):
    line = "I can talk when I get home."
    markdown = (f"### Slide 5 · Script\n- **{label}:** {line}\n"
                f"### Slide 6 · Action\n- **{label}:** {line}\n")
    faults = writer.check_repeats(markdown)
    assert any("slide 5" in f and "slide 6" in f and "same line" in f for f in faults)


def test_source_credit_is_allowed_outside_spoken_line():
    markdown = ("### Slide 3 · Source\n" + SOURCE + "\n### Slide 5 · Script\n"
                '- **When:** The talk can wait until tomorrow.\n'
                '- **Say:** "I can talk when I get home."\n')
    assert writer.check_repeats(markdown) == []


def test_full_draft_check_includes_the_current_spoken_field():
    markdown = ("### Slide 3 · Source\n" + SOURCE + "\n### Slide 5 · Script\n"
                '- **Say:** "Nolen-Hoeksema found that going over things keeps the mood low."\n')
    assert any("researcher is credited on slide 3" in f for f in writer.verify_draft(markdown))


@pytest.mark.parametrize("line", [
    "Excuse me, could you tell me when my bike will be ready?",
    "Are you free to talk after dinner?",
    "Would you like me to call tomorrow?",
    "Can I ask what you meant by that?",
])
def test_questions_to_another_person_are_valid_speech(line):
    assert writer.check_spoken(f'### Slide 5 · Script\n- **Say:** "{line}"') == []


def test_known_coaching_prompt_still_fails():
    faults = writer.check_spoken('- **Say:** "What is the smallest action you can take?"')
    assert any("coaching" in fault for fault in faults)
