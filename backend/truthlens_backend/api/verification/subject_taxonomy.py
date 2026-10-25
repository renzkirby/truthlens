"""TruthLens subject-taxonomy vocabulary and public grouping helpers.

The rubric remains a reviewable design artifact, not an active classifier,
source of verification authority, or partner-intake policy. Community feed
projection/filtering may use these public grouping helpers only with persisted
authoritative classifications; multi-domain rows are not assigned a guessed
primary topic. Existing classification and authorization contracts remain
unchanged.
"""

from dataclasses import dataclass


TAXONOMY_VERSION = "claim-subject-v1-draft"
CAMPUS_CONTEXT_CODE = "CAMPUS_AFFAIRS"  # Coverage context; never a subject code.
CAMPUS_CONTEXT_STATES = ("CONFIRMED", "NOT_APPLICABLE", "UNCERTAIN")


@dataclass(frozen=True)
class SubjectRule:
    definition: str
    include: tuple[str, ...]
    do_not_infer: tuple[str, ...]


@dataclass(frozen=True)
class PublicCategory:
    code: str
    label: str
    domains: tuple[str, ...]


# The existing 12 codes must be preserved until an independently reviewed
# migration and classification-rollout decision authorizes a change.
SUBJECT_RULES = {
    "CIVICS": SubjectRule(
        "Government decisions, public administration, policy implementation, and formal civic or student governance.",
        ("government program implementation", "public service administration", "student government policies"),
        ("a politician merely being mentioned", "routine school administration with no governance proposition"),
    ),
    "ELECTIONS": SubjectRule(
        "Electoral processes, voting, candidates, campaigns, and election results, including student elections.",
        ("voting dates and rules", "candidate eligibility", "election outcomes"),
        ("every decision by an elected official", "a general student-organization announcement"),
    ),
    "LAW": SubjectRule(
        "Laws, legal rights and duties, court proceedings, and legal judgments or enforcement.",
        ("court rulings", "statutory provisions", "criminal proceedings"),
        ("anything called unfair", "routine institutional policies with no legal claim"),
    ),
    "HEALTH": SubjectRule(
        "Healthcare, diseases, treatments, public health, and medical safety or services.",
        ("vaccine safety", "hospital services", "disease prevention"),
        ("every study produced by a university", "generic laboratory technology"),
    ),
    "SCIENCE": SubjectRule(
        "Scientific evidence, experiments, discoveries, and explanations of natural phenomena.",
        ("research findings", "scientific observations", "experimental results"),
        ("routine product releases", "technology marketing that merely cites science"),
    ),
    "TECHNOLOGY": SubjectRule(
        "Technology products and systems, software, AI, devices, cybersecurity, and digital infrastructure.",
        ("software security incidents", "AI system capabilities", "device features"),
        ("every online publication", "all scientific research"),
    ),
    "EDUCATION": SubjectRule(
        "Teaching, learning, schools, academic programs, student services, and education policy.",
        ("tuition changes", "curriculum requirements", "school admission rules"),
        ("all activities occurring at a university", "student elections solely because they are on campus"),
    ),
    "ECONOMY": SubjectRule(
        "Business, labor markets, trade, prices, financial activity, and economic policy.",
        ("inflation claims", "employment statistics", "business earnings"),
        ("every government funding announcement", "tuition policy simply because money is mentioned"),
    ),
    "ENVIRONMENT": SubjectRule(
        "Climate, ecosystems, natural resources, environmental pollution, and conservation.",
        ("air or water pollution", "climate trends", "wildlife conservation"),
        ("every natural disaster response", "any outdoor event"),
    ),
    "DISASTERS": SubjectRule(
        "Hazards, disasters, emergencies, disaster response, and public safety incidents.",
        ("earthquake response", "flood evacuations", "emergency safety advisories"),
        ("every climate policy", "routine sports safety rules"),
    ),
    "SPORTS": SubjectRule(
        "Sporting competitions, athletes, teams, results, and sports-specific rules.",
        ("tournament results", "athlete eligibility", "match schedules"),
        ("scholarship eligibility just because athletes are involved", "every school activity"),
    ),
    "CULTURE": SubjectRule(
        "Arts, entertainment, cultural events, traditions, and the cultural sector.",
        ("film and music releases", "cultural festivals", "arts institution announcements"),
        ("every statement by a celebrity", "all student activities"),
    ),
}


# Eight reader-friendly subject groups. Campus Affairs is an additional public
# browsing option backed by a separate context field, not a ninth subject group.
PUBLIC_CATEGORIES = (
    PublicCategory("POLITICS_GOVERNMENT_LAW", "Politics, Governance & Law", ("CIVICS", "ELECTIONS", "LAW")),
    PublicCategory("BUSINESS_ECONOMY", "Business & Economy", ("ECONOMY",)),
    PublicCategory("HEALTH_MEDICINE", "Health & Medicine", ("HEALTH",)),
    PublicCategory("SCIENCE_TECHNOLOGY", "Science & Technology", ("SCIENCE", "TECHNOLOGY")),
    PublicCategory("EDUCATION", "Education", ("EDUCATION",)),
    PublicCategory("ENVIRONMENT_SAFETY", "Environment & Public Safety", ("ENVIRONMENT", "DISASTERS")),
    PublicCategory("SPORTS", "Sports", ("SPORTS",)),
    PublicCategory("CULTURE_ENTERTAINMENT", "Culture & Entertainment", ("CULTURE",)),
)


_DOMAIN_TO_PUBLIC_CATEGORY = {
    domain: group for group in PUBLIC_CATEGORIES for domain in group.domains
}
_PUBLIC_CATEGORY_BY_CODE = {
    category.code: category for category in PUBLIC_CATEGORIES
}


def public_category_for_primary_subject(primary_subject):
    """Map an EXPLICIT primary subject to its public category, or return None.

    Never infer a primary subject from sorted multi-domain codes. The current
    authoritative classification records do not yet store a primary subject.
    """
    if not isinstance(primary_subject, str):
        return None
    return _DOMAIN_TO_PUBLIC_CATEGORY.get(primary_subject)


def public_category_for_domains(domains):
    """Return a public topic only when one authoritative subject is present.

    Current authoritative classification rows do not persist an explicit
    primary subject. Multi-domain rows therefore remain unresolved for public
    topic display/filtering until primary-subject persistence is introduced.
    """
    if not isinstance(domains, (list, tuple)) or len(domains) != 1:
        return None
    return public_category_for_primary_subject(domains[0])


def public_category_for_code(code):
    """Return a configured public category by stable API code, or None."""
    if not isinstance(code, str):
        return None
    return _PUBLIC_CATEGORY_BY_CODE.get(code)
