# Author: Nicholas Corrieri

from rawdog.drives import parse_user_path


def test_parse_user_path_accepts_pasted_backslash_separators() -> None:
    assert str(parse_user_path("/Volumes/WD_BLACK\\RAW_DEN")) == "/Volumes/WD_BLACK/RAW_DEN"
