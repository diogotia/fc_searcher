from src.data.specialized_construction_hashtags import (
    SPECIALIZED_CONSTRUCTION_TAGS,
    merge_parent_in_group_with_additional,
    tag_strings,
    tag_to_in_group_search,
)


def test_merge_parent_in_group_with_additional():
    assert merge_parent_in_group_with_additional("ищу работу", "рабочий строительства") == (
        "ищу работу рабочий строительства"
    )
    assert merge_parent_in_group_with_additional("", "рабочий строительства") == "рабочий строительства"
    assert merge_parent_in_group_with_additional("ищу работу", "ищу работу в Берлине") == "ищу работу в Берлине"


def test_tag_to_in_group_search_strips_hash_and_underscores():
    assert tag_to_in_group_search("#рабочий_строительства") == "рабочий строительства"
    assert tag_to_in_group_search("  #мастер_по_ремонту ") == "мастер по ремонту"


def test_construction_tag_list_has_expected_entries():
    tags = tag_strings()
    assert "#строитель" in tags
    assert "#ремонт_квартир" in tags
    assert len(SPECIALIZED_CONSTRUCTION_TAGS) == 7
