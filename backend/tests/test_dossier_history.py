"""Historique des imports de dossiers : onglets (à traiter, en cours, rangés) et recherche."""

from apps.imports.models import DossierImport


def make(user, name, status):
    return DossierImport.objects.create(root_name=name, status=status, created_by=user)


def test_groups_counts_and_search(hq_client, users):
    hq = users["hq"]
    make(hq, "SENEGAL - AMLOR 5MG", DossierImport.Status.QUESTION)
    make(hq, "SENEGAL - BISOGEN", DossierImport.Status.FAILED)
    make(hq, "MALI - LOLIP", DossierImport.Status.RUNNING)
    make(hq, "MALI - AMLOR 10MG", DossierImport.Status.APPLIED)
    make(hq, "GABON - OMEPRAL", DossierImport.Status.APPLIED)

    counts = hq_client.get("/api/v1/dossier-imports/counts").json()
    assert counts == {"a_traiter": 2, "en_cours": 1, "ranges": 2, "tous": 5}

    todo = hq_client.get("/api/v1/dossier-imports", {"group": "a_traiter"}).json()
    assert sorted(b["root_name"] for b in todo["results"]) == [
        "SENEGAL - AMLOR 5MG",
        "SENEGAL - BISOGEN",
    ]

    found = hq_client.get("/api/v1/dossier-imports", {"search": "amlor"}).json()
    assert found["count"] == 2
    both = hq_client.get("/api/v1/dossier-imports", {"search": "amlor", "group": "ranges"}).json()
    assert [b["root_name"] for b in both["results"]] == ["MALI - AMLOR 10MG"]


def test_country_user_counts_only_their_imports(country_client, users):
    make(users["hq"], "SENEGAL - AMLOR", DossierImport.Status.QUESTION)
    make(users["country"], "SENEGAL - LOLIP", DossierImport.Status.APPLIED)
    counts = country_client.get("/api/v1/dossier-imports/counts").json()
    assert counts["tous"] == 1 and counts["ranges"] == 1
