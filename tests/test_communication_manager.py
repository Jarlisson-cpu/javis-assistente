import pytest

from communication.manager import CommunicationManager


def test_email_draft_opens_encoded_mailto_without_sending():
    opened = []
    manager = CommunicationManager(opener=lambda url: opened.append(url) or True)

    assert manager.open_email_draft("person@example.com", "Olá & teste", "linha 1\nlinha 2")
    assert opened[0].startswith("mailto:person@example.com?")
    assert "%26" in opened[0]
    assert "%0A" in opened[0]


@pytest.mark.parametrize(
    "recipient,subject,body",
    [
        ("bad", "assunto", "corpo"),
        ("user@example.com\r\nBcc:attacker@example.com", "assunto", "corpo"),
        ("user@example.com", "linha\nBcc:attacker@example.com", "corpo"),
    ],
)
def test_email_draft_rejects_invalid_addresses_and_header_injection(recipient, subject, body):
    manager = CommunicationManager(opener=lambda url: True)

    with pytest.raises(ValueError):
        manager.open_email_draft(recipient, subject, body)