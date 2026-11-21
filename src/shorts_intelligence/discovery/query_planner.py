"""Persistent, locale-aware query planning for short-form video discovery.

Search engines return ranked samples, not random samples of the platform. This
planner improves coverage by rotating topics, languages and regions across runs,
and by remembering the most recent use of each exact query/locale tuple.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True, slots=True)
class SearchQuery:
    platform: str
    query: str
    language: str
    region: str
    strategy: str

    @property
    def key(self) -> str:
        raw = "|".join(
            (
                self.platform,
                self.query.casefold().strip(),
                self.language.casefold(),
                self.region.casefold(),
                self.strategy,
            )
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


_YOUTUBE_LOCALE_TERMS: dict[tuple[str, str], tuple[str, ...]] = {
    ("en", "IN"): (
        "cricket", "comedy", "memes", "cooking", "technology", "education",
        "facts", "gaming", "dance", "music", "fitness", "travel", "beauty",
        "pets", "science", "motivation", "football", "storytelling",
    ),
    ("en", "US"): (
        "comedy", "gaming", "science", "diy", "cooking", "fitness", "pets",
        "technology", "music", "basketball", "football", "storytelling",
    ),
    ("en", "GB"): (
        "comedy", "football", "cooking", "gaming", "history", "science",
        "travel", "music", "fitness", "technology",
    ),
    ("hi", "IN"): (
        "हिंदी कॉमेडी", "क्रिकेट", "ज्ञान और रोचक तथ्य", "खाना बनाना",
        "टेक्नोलॉजी", "मोटिवेशन", "डांस", "गेमिंग", "शिक्षा", "कहानी",
        "फिटनेस", "फिल्म",
    ),
    ("mr", "IN"): (
        "मराठी कॉमेडी", "मराठी विनोद", "क्रिकेट", "मराठी माहिती",
        "मराठी पाककला", "मराठी प्रेरणा", "शिक्षण", "प्रवास",
    ),
    ("kn", "IN"): (
        "ಕನ್ನಡ ಹಾಸ್ಯ", "ಕನ್ನಡ ಕ್ರಿಕೆಟ್", "ಕನ್ನಡ ಮಾಹಿತಿ", "ಕನ್ನಡ ಅಡುಗೆ",
        "ಕನ್ನಡ ಶಿಕ್ಷಣ", "ಕನ್ನಡ ತಂತ್ರಜ್ಞಾನ", "ಕನ್ನಡ ಕಥೆಗಳು",
    ),
    ("ta", "IN"): (
        "தமிழ் நகைச்சுவை", "தமிழ் கிரிக்கெட்", "தமிழ் சமையல்",
        "தமிழ் தகவல்", "தமிழ் கல்வி", "தமிழ் தொழில்நுட்பம்",
        "தமிழ் நடனம்", "தமிழ் கதை",
    ),
    ("te", "IN"): (
        "తెలుగు కామెడీ", "తెలుగు క్రికెట్", "తెలుగు వంటలు",
        "తెలుగు సమాచారం", "తెలుగు విద్య", "తెలుగు టెక్నాలజీ",
        "తెలుగు డాన్స్",
    ),
    ("bn", "IN"): (
        "বাংলা কমেডি", "বাংলা ক্রিকেট", "বাংলা রান্না", "বাংলা তথ্য",
        "বাংলা শিক্ষা", "বাংলা প্রযুক্তি",
    ),
    ("es", "ES"): (
        "comedia", "futbol", "cocina", "videojuegos", "ciencia",
        "curiosidades", "baile", "viajes", "mascotas", "tecnologia",
    ),
    ("pt", "BR"): (
        "comedia", "futebol", "culinaria", "games", "curiosidades",
        "danca", "viagem", "animais", "tecnologia", "educacao",
    ),
    ("id", "ID"): (
        "komedi", "sepak bola", "memasak", "game", "fakta menarik",
        "tarian", "perjalanan", "teknologi", "pendidikan",
    ),
}


def build_youtube_query_pool(custom_queries: list[str] | None = None) -> list[SearchQuery]:
    """Build a diverse search pool spanning categories, scripts and locales."""
    if custom_queries:
        queries = [
            SearchQuery(
                platform="youtube",
                query=value.strip(),
                language="en",
                region="IN",
                strategy="user",
            )
            for value in custom_queries
            if value.strip()
        ]
        return _unique_queries(queries)

    queries: list[SearchQuery] = []
    for (language, region), topics in _YOUTUBE_LOCALE_TERMS.items():
        for topic in topics:
            phrase = f"{topic} shorts"
            queries.append(
                SearchQuery(
                    platform="youtube",
                    query=phrase,
                    language=language,
                    region=region,
                    strategy="localized_topic",
                )
            )
            # A second intent variant provides additional ranking diversity.
            if language in {"en", "hi"}:
                variant = f"viral {topic} shorts"
                queries.append(
                    SearchQuery(
                        platform="youtube",
                        query=variant,
                        language=language,
                        region=region,
                        strategy="viral_topic",
                    )
                )
    return _unique_queries(queries)


def build_instagram_query_pool(
    custom_queries: list[str] | None = None,
    *,
    default_region: str = "in-en",
) -> list[SearchQuery]:
    """Build region and language-aware public web searches for indexed Reels."""
    if custom_queries:
        return _unique_queries(
            [
                SearchQuery(
                    "instagram",
                    q.strip(),
                    default_region.split("-", maxsplit=1)[-1],
                    default_region,
                    "user",
                )
                for q in custom_queries
                if q.strip()
            ]
        )
    topics = {
        "in-en": (
            "cricket", "comedy", "education", "cooking", "technology", "gaming",
            "dance", "travel", "fitness", "facts", "beauty", "pets",
        ),
        "in-hi": (
            "हिंदी कॉमेडी", "क्रिकेट", "मोटिवेशन", "शिक्षा", "खाना",
            "टेक्नोलॉजी", "डांस", "रोचक तथ्य",
        ),
        "in-ta": (
            "தமிழ் நகைச்சுவை", "தமிழ் கிரிக்கெட்", "தமிழ் சமையல்",
            "தமிழ் கல்வி", "தமிழ் தகவல்",
        ),
        "in-te": (
            "తెలుగు కామెడీ", "తెలుగు క్రికెట్", "తెలుగు వంటలు",
            "తెలుగు విద్య",
        ),
        "in-mr": (
            "मराठी कॉमेडी", "मराठी क्रिकेट", "मराठी माहिती", "मराठी पाककला",
        ),
        "in-kn": (
            "ಕನ್ನಡ ಹಾಸ್ಯ", "ಕನ್ನಡ ಕ್ರಿಕೆಟ್", "ಕನ್ನಡ ಅಡುಗೆ", "ಕನ್ನಡ ಮಾಹಿತಿ",
        ),
        "us-en": (
            "comedy", "gaming", "science", "cooking", "fitness", "pets",
        ),
        "es-es": ("comedia", "futbol", "cocina", "viajes", "curiosidades"),
        "pt-br": ("comedia", "futebol", "culinaria", "viagem", "curiosidades"),
        "id-id": ("komedi", "sepak bola", "memasak", "fakta menarik", "game"),
    }
    result: list[SearchQuery] = []
    for region, terms in topics.items():
        language = region.split("-", maxsplit=1)[1]
        for term in terms:
            result.append(
                SearchQuery(
                    platform="instagram",
                    query=f"site:instagram.com/reel/ {term} reels",
                    language=language,
                    region=region,
                    strategy="localized_index",
                )
            )
    return _unique_queries(result)


def _unique_queries(queries: list[SearchQuery]) -> list[SearchQuery]:
    seen: set[str] = set()
    unique: list[SearchQuery] = []
    for query in queries:
        if not query.query or query.key in seen:
            continue
        seen.add(query.key)
        unique.append(query)
    return unique


def select_due_queries(
    queries: list[SearchQuery],
    history: dict[str, str],
    *,
    limit: int,
    cooldown_days: int,
    rng: random.Random | random.SystemRandom,
    now: datetime | None = None,
) -> list[SearchQuery]:
    """Prefer never-used or out-of-cooldown queries; rotate stale queries last."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=max(0, cooldown_days))
    never_used: list[SearchQuery] = []
    due: list[SearchQuery] = []
    stale: list[tuple[datetime, SearchQuery]] = []

    for query in queries:
        last_run = history.get(query.key)
        if last_run is None:
            never_used.append(query)
            continue
        try:
            parsed = datetime.fromisoformat(last_run)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
        except ValueError:
            never_used.append(query)
            continue
        if parsed <= cutoff:
            due.append(query)
        else:
            stale.append((parsed, query))

    rng.shuffle(never_used)
    rng.shuffle(due)
    stale.sort(key=lambda item: item[0])
    selected = never_used + due + [item[1] for item in stale]
    return selected[: max(0, limit)]
