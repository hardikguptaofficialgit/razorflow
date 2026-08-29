"""Tests for generic entity extraction."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent_runtime.task.entities import extract_entity_phrase, extract_entity_phrases


def test_wireless_earbuds_preserved() -> None:
    assert extract_entity_phrase("find wireless earbuds") == "wireless earbuds"
    assert extract_entity_phrase("find me good wireless earbuds under ₹6000") == "wireless earbuds"


def test_search_for_does_not_keep_the_preposition() -> None:
    assert extract_entity_phrase("search for wireless earbuds") == "wireless earbuds"


def test_smartwatch_preserved() -> None:
    assert extract_entity_phrase("find the cheapest smartwatch") == "smartwatch"
    assert extract_entity_phrase("find smart watches") == "smart watches"


def test_compound_phrases() -> None:
    assert extract_entity_phrase("noise cancelling headphones") == "noise cancelling headphones"
    assert extract_entity_phrase("gaming laptop under ₹50000") == "gaming laptop"


def test_brand_phrase() -> None:
    assert extract_entity_phrase("add Amul butter to my cart") == "Amul butter"


def test_polite_imperative_phrase() -> None:
    assert extract_entity_phrase("see add NovaTrack watch please") == "NovaTrack watch"


def test_vague_snacks_normalized() -> None:
    assert extract_entity_phrase("add me some good snacks under ₹200") == "snacks"


def test_multi_item_list() -> None:
    phrases = extract_entity_phrases("add amul butter, chips and cooker to my cart")
    assert "butter" in phrases[0].lower() or "amul" in phrases[0].lower()
    assert len(phrases) == 3
