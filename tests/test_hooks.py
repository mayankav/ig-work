from suresilly import hooks


def test_every_area_has_at_least_two_techniques():
    for area in hooks.AREAS:
        assert len([c for c in hooks.CARDS if area in c.areas]) >= 2, area


def test_card_ids_are_unique_and_areas_are_known():
    assert len({c.id for c in hooks.CARDS}) == len(hooks.CARDS)
    assert all(set(c.areas) <= set(hooks.AREAS) for c in hooks.CARDS)


def test_pick_skips_recent_techniques():
    pool = [c.id for c in hooks.CARDS if "saythis" in c.areas]
    recent = pool[:-1]
    assert all(hooks.pick("saythis", recent, day=n).id == pool[-1] for n in range(5))


def test_pick_rotates_with_the_day_and_falls_back_when_all_are_recent():
    pool = [c.id for c in hooks.CARDS if "rights" in c.areas]
    assert len({hooks.pick("rights", [], day=n).id for n in range(len(pool))}) == len(pool)
    assert hooks.pick("rights", pool).id in pool


def test_prompt_card_names_the_technique_and_gives_no_line_to_copy():
    text = hooks.prompt_card(hooks.BY_ID[8])
    assert "negation" in text and "Here is what is." not in text and "your own" in text
