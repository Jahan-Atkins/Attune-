from app.matching import has_overlap

TUESDAY = 1


def test_exact_overlap_matches_at_the_start():
    blocks = [(TUESDAY, "09:00", "11:00")]
    result = has_overlap(TUESDAY, "09:00", "11:00", 30, blocks)
    assert result == ("09:00", "09:30")


def test_partial_overlap_with_room_for_the_full_duration():
    # Customer wants 08:00-09:45, instructor's free 09:00-11:00 -> overlap is 09:00-09:45, room for 30 min.
    blocks = [(TUESDAY, "09:00", "11:00")]
    result = has_overlap(TUESDAY, "08:00", "09:45", 30, blocks)
    assert result == ("09:00", "09:30")


def test_overlap_too_short_for_the_full_duration_does_not_match():
    # Overlap is only 09:00-09:15 (15 min), less than the 30-minute lesson.
    blocks = [(TUESDAY, "09:00", "11:00")]
    result = has_overlap(TUESDAY, "08:00", "09:15", 30, blocks)
    assert result is None


def test_no_overlap_at_all_does_not_match():
    blocks = [(TUESDAY, "09:00", "11:00")]
    result = has_overlap(TUESDAY, "13:00", "15:00", 30, blocks)
    assert result is None


def test_adjacent_but_not_touching_windows_do_not_match():
    # Requested window ends exactly when the block starts -> zero-width overlap.
    blocks = [(TUESDAY, "11:00", "13:00")]
    result = has_overlap(TUESDAY, "09:00", "11:00", 30, blocks)
    assert result is None


def test_wrong_day_does_not_match():
    blocks = [(TUESDAY, "09:00", "11:00")]
    result = has_overlap(0, "09:00", "11:00", 30, blocks)  # requesting Monday
    assert result is None


def test_picks_the_first_qualifying_block_among_several():
    blocks = [(TUESDAY, "06:00", "06:20"), (TUESDAY, "09:00", "11:00")]
    result = has_overlap(TUESDAY, "05:00", "12:00", 30, blocks)
    assert result == ("09:00", "09:30")
