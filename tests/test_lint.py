from suresilly import lint


def test_an_instruction_without_its_words_is_caught_and_a_quoted_one_passes():
    assert lint.incomplete("YOUR MOVE", "Set a reminder for 3 days. Send one line.")
    assert lint.incomplete("SO", "Read the number before you sign. Ask if it can change.")
    assert not lint.incomplete("ASK THIS", "“Can the notice period be 30 days?”")
    assert not lint.incomplete("SAY THIS", "Please confirm the date my final wages will be paid. Section 17(2), Code on Wages.")
    assert not lint.incomplete("", "Ask the question: “What were my hours?”")


def test_vague_stand_ins_are_caught_anywhere():
    assert lint.incomplete("", "Then send one line and wait.")
    assert not lint.incomplete("", "You are not behind. You are new.")


def test_a_cover_must_leave_a_gap_and_must_not_print_the_payoff():
    assert lint.cover_problems("Resigned? Your wages are due in 2 working days.", ["2 working days"])
    assert lint.cover_problems("Let’s circle back. = no.", ["= no"])
    assert not lint.cover_problems("HR says your final pay takes 45 days. The law has a different number.", ["2 working days"])
    assert not lint.cover_problems("“We are like a family” is not in your offer letter. Here is what is.", [])
    assert lint.cover_problems("How to say no to a 10 pm message.", ["seen. i"])  # no gap: a how-to with its answer implied
    assert not lint.cover_problems("How to say no to a 10 pm message. Reply with: (typing)", ["seen. i"])
