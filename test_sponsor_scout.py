from scripts.sponsor_scout import (
    candidate_from_repo,
    deduplicate_candidates,
    load_sponsor_ask_template,
    render_markdown,
    score_repository,
)


def repo_payload(**overrides):
    payload = {
        "name": "local-ai-agent",
        "html_url": "https://github.com/example/local-ai-agent",
        "description": "Privacy-first local AI assistant for macOS with Ollama",
        "stargazers_count": 320,
        "topics": ["ai", "privacy", "ollama", "macos"],
        "language": "Python",
        "has_sponsors_listing": False,
        "archived": False,
        "owner": {"login": "example"},
    }
    payload.update(overrides)
    return payload


def test_score_repository_prefers_relevant_privacy_ai_repo():
    score, reasons = score_repository(repo_payload())

    assert score > 40
    assert "match op 'privacy'" in reasons
    assert "sterke open-source tractie" in reasons


def test_archived_irrelevant_repo_scores_lower():
    relevant_score, _ = score_repository(repo_payload())
    weak_score, weak_reasons = score_repository(
        repo_payload(
            name="casino-nft",
            description="Archived crypto casino NFT experiment",
            stargazers_count=5,
            topics=["crypto", "casino", "nft"],
            archived=True,
        )
    )

    assert weak_score < relevant_score
    assert "repository is gearchiveerd" in weak_reasons


def test_deduplicate_candidates_keeps_highest_score():
    first = candidate_from_repo(repo_payload(stargazers_count=50))
    second = candidate_from_repo(repo_payload(stargazers_count=1000))

    deduped = deduplicate_candidates([first, second])

    assert len(deduped) == 1
    assert deduped[0].stars == 1000


def test_render_markdown_contains_human_review_warning_and_ask():
    candidate = candidate_from_repo(repo_payload())
    markdown = render_markdown([candidate], ["privacy first AI assistant stars:>20"])

    assert "verstuurt niets automatisch" in markdown
    assert "€250 per maand" in markdown
    assert "example/local-ai-agent" in markdown


def test_load_sponsor_ask_template_from_file(tmp_path):
    template = tmp_path / "ask.txt"
    template.write_text("Hallo {owner}, sponsor WintripAI?", encoding="utf-8")

    loaded = load_sponsor_ask_template(str(template))

    assert loaded == "Hallo {owner}, sponsor WintripAI?"
