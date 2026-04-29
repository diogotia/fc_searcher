from src.services.contact_extract import extract_emails, extract_phones, normalize_email_key, normalize_phone_key


def test_extract_emails_dedupes_case():
    text = "Reach me at Jane.Doe@Example.com or jane.doe@example.com"
    got = extract_emails(text)
    assert len(got) == 1
    assert normalize_email_key(got[0]) == "jane.doe@example.com"


def test_extract_phones_finds_us_style():
    text = "Call 415-555-0100 or +1 (415) 555-0199"
    got = extract_phones(text)
    assert len(got) == 2
    assert normalize_phone_key(got[0]) == normalize_phone_key("415-555-0100")
