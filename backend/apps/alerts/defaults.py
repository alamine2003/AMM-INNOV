"""Default alert rules (section 6.4 of the PRD), seeded by migration and `seed_alert_rules`."""

COUNTRY = "COUNTRY_REGULATORY"
HQ = "HQ_REGULATORY"
CEO = "CEO_ADMIN"

DEFAULT_RULES: list[dict] = [
    {
        "code": "J-365",
        "offset_days": 365,
        "severity": "INFO",
        "roles": [COUNTRY],
        "channels": ["IN_APP"],
        "only_if_not_filed": True,
    },
    {
        "code": "J-180",
        "offset_days": 180,
        "severity": "WARNING",
        "roles": [COUNTRY, HQ],
        "channels": ["IN_APP", "EMAIL"],
        "only_if_not_filed": True,
    },
    {
        "code": "J-90",
        "offset_days": 90,
        "severity": "CRITICAL",
        "roles": [COUNTRY, HQ],
        "channels": ["IN_APP", "EMAIL"],
        "only_if_not_filed": True,
    },
    {
        "code": "J-30",
        "offset_days": 30,
        "severity": "CRITICAL",
        "roles": [COUNTRY, HQ, CEO],
        "channels": ["IN_APP", "EMAIL"],
        "only_if_not_filed": True,
    },
    {
        "code": "J0",
        "offset_days": 0,
        "severity": "CRITICAL",
        "roles": [COUNTRY, HQ, CEO],
        "channels": ["IN_APP", "EMAIL"],
        "only_if_not_filed": False,
    },
    {
        "code": "DOSSIER",
        "offset_days": 270,
        "severity": "WARNING",
        "roles": [COUNTRY],
        "channels": ["IN_APP"],
        "only_if_not_filed": False,
    },
    {
        # PRD 6.4 : renouvellement déposé depuis plus de N jours sans décision (N = 120).
        "code": "DECISION",
        "offset_days": 120,
        "severity": "WARNING",
        "roles": [COUNTRY],
        "channels": ["IN_APP"],
        "only_if_not_filed": False,
    },
]


def seed_default_rules(rule_model) -> int:
    """Creates missing global rules; existing ones are left untouched. Returns created count."""
    created = 0
    for spec in DEFAULT_RULES:
        _, was_created = rule_model.objects.get_or_create(
            code=spec["code"], country=None, defaults=spec
        )
        created += int(was_created)
    return created
