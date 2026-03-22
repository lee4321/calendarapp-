from shared.wbs_filter import WBSFilter


def test_no_filter_allows_all():
    assert WBSFilter.parse("") is None
    assert WBSFilter.parse(None) is None


def test_missing_wbs_includes_event():
    filt = WBSFilter.parse("A.B")
    assert filt is not None
    assert filt.matches(None)
    assert filt.matches("")


def test_prefix_match_implicit_double_star():
    filt = WBSFilter.parse("A.B")
    assert filt is not None
    assert filt.matches("A.B")
    assert filt.matches("A.B.1")
    assert filt.matches("A.B.C.D")
    assert not filt.matches("A.C")


def test_single_segment_wildcard():
    filt = WBSFilter.parse("A.*.C")
    assert filt is not None
    assert filt.matches("A.X.C")
    assert not filt.matches("A.X.Y.C")


def test_exclude_tokens_win():
    filt = WBSFilter.parse("A.B,!A.B.3")
    assert filt is not None
    assert filt.matches("A.B.2")
    assert not filt.matches("A.B.3")
    assert not filt.matches("A.B.3.1")
