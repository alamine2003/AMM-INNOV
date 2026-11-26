"""1.3.9 : agent de livraison du serveur (scripts/serveur/livrer.sh).

Le script tourne pour de vrai, dans un dépôt git d'essai avec ses étiquettes. GitHub et Docker
sont remplacés par deux petits programmes qui notent ce qu'on leur demande : un faux `curl`
(l'API des déploiements) et un faux `compose.sh` (sauvegarde, images, démarrage, santé).
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "serveur" / "livrer.sh"
CONFIGURER = ROOT / "scripts" / "serveur" / "configurer.sh"
BOT = "github-actions[bot]"

pytestmark = pytest.mark.skipif(
    not (shutil.which("git") and shutil.which("flock")), reason="git et flock sont nécessaires"
)

FAKE_CURL = r'''#!/usr/bin/env python3
"""Faux curl : l'API GitHub des déploiements, d'après github.json."""
import json, os, re, sys
state_path = os.environ["FAUX_GITHUB"]
state = json.load(open(state_path))
args = sys.argv[1:]
method = args[args.index("-X") + 1] if "-X" in args else "GET"
url = next(a for a in args if a.startswith("http"))
if state.get("offline"):
    sys.exit(7)
path = re.sub(r"^https?://[^/]+", "", url).split("?")[0]
state.setdefault("calls", []).append(f"{method} {path}")
match = re.match(r"^/repos/[^/]+/[^/]+/deployments/(\d+)/statuses$", path)
if method == "GET" and path.endswith("/deployments"):
    out = state["deployments"][:1]
elif match and method == "GET":
    out = state["statuses"].get(match[1], [])[:1]
elif match and method == "POST":
    body = json.loads(sys.stdin.read())
    state["statuses"].setdefault(match[1], []).insert(0, body)
    state.setdefault("posted", []).append(body)
    out = body
else:
    sys.exit(22)
json.dump(state, open(state_path, "w"))
print(json.dumps(out))
'''

FAKE_COMPOSE = r'''#!/usr/bin/env python3
"""Faux scripts/serveur/compose.sh : note les appels, simule sauvegarde, images et santé."""
import json, os, re, sys
state_path = os.environ["FAUX_DOCKER"]
state = json.load(open(state_path))
args = sys.argv[1:]
state.setdefault("calls", []).append(" ".join(args))

def tag():
    text = open(".env").read()
    return re.findall(r"^TAG='?([^'\n]*)'?$", text, re.M)[-1]

code = 0
idle = "UID PID CMD\nroot 1 celery -A config worker\nroot 2 daphne config.asgi"
if args[0] == "top":
    print(state.get("top", idle))
elif args[:3] == ["exec", "-T", "backup"]:
    code = 1 if state.get("backup_fails") else 0
elif args[0] == "pull":
    wanted = os.environ.get("TAG") or tag()
    state.setdefault("pulled", []).append([wanted, os.environ.get("DOCKER_CONFIG", "")])
    code = 1 if wanted in state.get("pull_fails", []) else 0
elif args[:2] == ["up", "-d"]:
    state["running"] = tag()
elif args[:3] == ["exec", "-T", "frontend"]:
    running = state.get("running", "")
    broken = running in state.get("broken", [])
    print(json.dumps({"status": "error" if broken else "ok", "database": True,
                      "redis": True, "version": running}))
json.dump(state, open(state_path, "w"))
sys.exit(code)
'''


def git(cwd, *args):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "essai",
        "GIT_AUTHOR_EMAIL": "essai@example.org",
        "GIT_COMMITTER_NAME": "essai",
        "GIT_COMMITTER_EMAIL": "essai@example.org",
    }
    return subprocess.run(
        ["git", "-c", "init.defaultBranch=main", *args],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def commit_version(repo, version):
    (repo / "backend").mkdir(exist_ok=True)
    (repo / "backend" / "VERSION").write_text(f"{version}\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", f"Version {version}")
    git(repo, "tag", f"v{version}")
    return git(repo, "rev-parse", "HEAD")


class Server:
    """Un serveur d'essai : le dépôt installé sur v1.0.0, son .env et les faux GitHub et Docker."""

    def __init__(self, tmp_path):
        self.tmp = tmp_path
        work = tmp_path / "travail"
        work.mkdir()
        git(work, "init", "-q")
        self.sha = {v: commit_version(work, v) for v in ("1.0.0", "1.1.0")}
        origin = tmp_path / "origin.git"
        git(tmp_path, "init", "-q", "--bare", str(origin))
        git(work, "remote", "add", "origin", str(origin))
        git(work, "push", "-q", "origin", "main", "--tags")
        # Une étiquette posée sur une branche qui n'a jamais été fusionnée.
        git(work, "checkout", "-qb", "essai")
        self.sha["1.2.0"] = commit_version(work, "1.2.0")
        git(work, "push", "-q", "origin", "v1.2.0")

        self.dir = tmp_path / "amm-gh"
        git(tmp_path, "clone", "-q", str(origin), str(self.dir))
        git(self.dir, "checkout", "-q", "v1.0.0")
        (self.dir / ".env").write_text("DJANGO_SECRET_KEY='x'\nTAG='1.0.0'\n")
        (self.dir / ".env").chmod(0o600)
        (self.dir / ".env.livraison").write_text("GITHUB_DEPLOY_TOKEN='jeton-essai'\n")

        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "curl").write_text(FAKE_CURL)
        (bin_dir / "compose").write_text(FAKE_COMPOSE)
        for name in ("curl", "compose"):
            (bin_dir / name).chmod(0o755)
        self.bin = bin_dir
        self.github_file = tmp_path / "github.json"
        self.docker_file = tmp_path / "docker.json"
        self.github = {"deployments": [], "statuses": {}}
        self.docker = {"running": "1.0.0"}

    def approve(self, version, *, sha=None, creator=BOT, ref=None):
        """Ce que fait le workflow après l'approbation : un déploiement en attente du serveur."""
        number = str(100 + len(self.github["deployments"]))
        self.github["deployments"].insert(
            0,
            {
                "id": int(number),
                "ref": ref or f"v{version}",
                "payload": {"sha": sha or self.sha[version]},
                "creator": {"login": creator},
            },
        )
        self.github["statuses"][number] = [
            {"state": "queued", "description": "En attente du serveur"}
        ]
        return number

    def run(self):
        self.github_file.write_text(json.dumps(self.github))
        self.docker_file.write_text(json.dumps(self.docker))
        env = {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "AMM_DIR": str(self.dir),
            "LIVRAISON_API": "https://api.github.test",
            "LIVRAISON_COMPOSE": str(self.bin / "compose"),
            "LIVRAISON_DOCKER": "true",
            "LIVRAISON_ESSAIS": "2",
            "LIVRAISON_PAUSE": "0",
            "FAUX_GITHUB": str(self.github_file),
            "FAUX_DOCKER": str(self.docker_file),
        }
        result = subprocess.run(
            ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60
        )
        self.github = json.loads(self.github_file.read_text())
        self.docker = json.loads(self.docker_file.read_text())
        return result

    @property
    def posted(self):
        return [(s["state"], s["description"]) for s in self.github.get("posted", [])]

    @property
    def compose_calls(self):
        return self.docker.get("calls", [])

    @property
    def installed(self):
        version = (self.dir / "backend" / "VERSION").read_text().strip()
        tag = (self.dir / ".env").read_text().split("TAG=")[-1].strip().strip("'")
        return version, tag


@pytest.fixture
def server(tmp_path):
    return Server(tmp_path)


def test_nothing_waiting_means_nothing_touched(server):
    result = server.run()

    assert result.returncode == 0, result.stderr
    assert server.compose_calls == []
    assert server.posted == []
    assert server.installed == ("1.0.0", "1.0.0")


def test_an_approved_version_is_saved_installed_and_checked(server):
    server.approve("1.1.0")

    result = server.run()

    assert result.returncode == 0, result.stderr
    assert server.installed == ("1.1.0", "1.1.0")
    calls = server.compose_calls
    backup = calls.index("exec -T backup /scripts/serveur/sauvegarder.sh")
    pull = calls.index("pull --quiet backend worker beat frontend")
    assert backup < pull < calls.index("up -d")
    assert server.posted[-1][0] == "success"
    assert "1.1.0 en service" in server.posted[-1][1]
    assert [state for state, _ in server.posted] == [
        "in_progress",
        "in_progress",
        "in_progress",
        "success",
    ]
    # Les images de la version sont téléchargées avant que le code ne change.
    assert server.docker["pulled"][0][0] == "1.1.0"
    # Le reste de .env est gardé, ses droits aussi.
    assert "DJANGO_SECRET_KEY='x'" in (server.dir / ".env").read_text()
    assert oct((server.dir / ".env").stat().st_mode & 0o777) == "0o600"
    assert "OK v1.1.0 en service" in (server.dir / "livraisons" / "journal.log").read_text()


def test_a_version_already_answered_is_not_installed_again(server):
    number = server.approve("1.1.0")
    server.github["statuses"][number].insert(0, {"state": "success", "description": "fait"})

    server.run()

    assert server.compose_calls == []


def test_a_failed_backup_installs_nothing(server):
    server.approve("1.1.0")
    server.docker["backup_fails"] = True

    result = server.run()

    assert result.returncode == 1
    assert server.installed == ("1.0.0", "1.0.0")
    assert not any(call.startswith(("pull", "up")) for call in server.compose_calls)
    assert server.posted[-1][0] == "failure"
    assert "Sauvegarde" in server.posted[-1][1]


def test_a_version_that_starts_badly_is_rolled_back(server):
    server.approve("1.1.0")
    server.docker["broken"] = ["1.1.0"]

    result = server.run()

    assert result.returncode == 1
    assert server.installed == ("1.0.0", "1.0.0")
    assert server.docker["running"] == "1.0.0"
    state, description = server.posted[-1]
    assert state == "failure"
    assert "retour à 1.0.0 réussi" in description
    assert git(server.dir, "describe", "--tags", "--exact-match", "HEAD") == "v1.0.0"


def test_images_that_cannot_be_pulled_change_nothing(server):
    """Livraison de la 1.3.9 (26/11/2026) : GHCR refusait les images, l'agent avait déjà
    changé le code et tentait un retour en arrière qui retéléchargeait, lui aussi refusé."""
    server.approve("1.1.0")
    server.docker["pull_fails"] = ["1.1.0"]

    result = server.run()

    assert result.returncode == 1
    assert server.installed == ("1.0.0", "1.0.0")
    assert not any(call.startswith("up") for call in server.compose_calls)
    assert git(server.dir, "describe", "--tags", "--exact-match", "HEAD") == "v1.0.0"
    state, description = server.posted[-1]
    assert state == "failure"
    assert "Images 1.1.0 inaccessibles" in description
    assert "rien n'a été changé" in description


def test_docker_settings_of_the_agent_are_its_own_and_empty(server):
    """Les images sont publiques : une connexion ghcr.io périmée de root ne doit pas servir."""
    server.approve("1.1.0")

    server.run()

    _, docker_config = server.docker["pulled"][0]
    assert docker_config == str(server.dir / "livraisons" / "docker")
    assert list(Path(docker_config).iterdir()) == []


def test_rolling_back_does_not_download_again(server):
    server.approve("1.1.0")
    server.docker["broken"] = ["1.1.0"]

    server.run()

    assert [tag for tag, _ in server.docker["pulled"]] == ["1.1.0"]
    assert server.installed == ("1.0.0", "1.0.0")
    assert "retour à 1.0.0 réussi" in server.posted[-1][1]


def test_a_running_admin_command_postpones_the_installation(server):
    server.approve("1.1.0")
    server.docker["top"] = (
        "UID PID CMD\nroot 1 celery -A config worker\n"
        "root 9 python manage.py relire_congo --rapport /tmp/relecture-congo.json"
    )

    result = server.run()
    server.run()  # minute suivante : toujours en cours, pas de second message

    assert result.returncode == 0
    assert server.installed == ("1.0.0", "1.0.0")
    assert server.posted == [
        (
            "queued",
            "En attente : une commande tourne sur le serveur (manage.py relire_congo), "
            "reprise dès sa fin",
        )
    ]

    server.docker["top"] = "UID PID CMD\nroot 1 celery -A config worker"
    server.run()  # la commande est finie : l'installation part

    assert server.installed == ("1.1.0", "1.1.0")
    assert server.posted[-1][0] == "success"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"creator": "quelqu-un"}, "pas par le workflow"),
        ({"ref": "main"}, "n'est pas une étiquette"),
        ({"sha": "0" * 40}, "le workflow annonçait"),
    ],
)
def test_a_deployment_that_did_not_come_from_the_workflow_is_refused(server, change, reason):
    server.approve("1.1.0", **change)

    result = server.run()

    assert result.returncode == 1
    assert server.installed == ("1.0.0", "1.0.0")
    assert server.compose_calls == []
    assert server.posted[-1][0] == "error"
    assert reason in server.posted[-1][1]


def test_a_tag_that_is_not_on_main_is_refused(server):
    server.approve("1.2.0")

    server.run()

    assert server.installed == ("1.0.0", "1.0.0")
    assert "n'est pas sur main" in server.posted[-1][1]


def test_files_changed_by_hand_on_the_server_are_never_overwritten(server):
    server.approve("1.1.0")
    (server.dir / "backend" / "VERSION").write_text("modifié à la main\n")

    server.run()

    assert (server.dir / "backend" / "VERSION").read_text() == "modifié à la main\n"
    assert "modifiés à la main" in server.posted[-1][1]


def test_without_token_github_is_not_even_asked(server):
    (server.dir / ".env.livraison").unlink()
    server.approve("1.1.0")

    result = server.run()

    assert result.returncode == 0
    assert "jeton absent" in result.stderr
    assert server.github.get("calls") is None


def test_github_unreachable_is_not_an_error(server):
    server.approve("1.1.0")
    server.github["offline"] = True

    result = server.run()

    assert result.returncode == 0
    assert server.installed == ("1.0.0", "1.0.0")


def test_the_token_is_never_on_the_command_line():
    text = SCRIPT.read_text()
    assert '-K <(printf \'header = "Authorization: Bearer %s"' in text
    assert '-H "Authorization' not in text


def test_configurer_keeps_the_token_out_of_the_application_env(tmp_path):
    install = tmp_path / "amm-gh"
    (install / "scripts" / "serveur").mkdir(parents=True)
    shutil.copy(CONFIGURER, install / "scripts" / "serveur" / "configurer.sh")
    (install / ".env").write_text("TAG='1.0.0'\n")
    typed = "valeur-essai\nvaleur-essai\n"

    subprocess.run(
        ["bash", str(install / "scripts" / "serveur" / "configurer.sh"), "GITHUB_DEPLOY_TOKEN"],
        input=typed,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "GITHUB_DEPLOY_TOKEN" not in (install / ".env").read_text()
    assert (install / ".env.livraison").read_text() == "GITHUB_DEPLOY_TOKEN='valeur-essai'\n"
    assert oct((install / ".env.livraison").stat().st_mode & 0o777) == "0o600"


def test_installer_writes_a_timer_that_runs_a_copy_of_the_agent(tmp_path):
    install = tmp_path / "amm-gh"
    (install / "scripts" / "serveur").mkdir(parents=True)
    for name in ("installer_livraison.sh", "livrer.sh"):
        shutil.copy(ROOT / "scripts" / "serveur" / name, install / "scripts" / "serveur" / name)
    (install / ".env").write_text("TAG='1.0.0'\n")
    bin_dir, units = tmp_path / "bin", tmp_path / "systemd"
    bin_dir.mkdir()
    units.mkdir()
    fakes = {"id": "echo 0", "docker": "true", "systemctl": f'echo "$*" >> {tmp_path}/systemctl'}
    for name, body in fakes.items():
        (bin_dir / name).write_text(f"#!/bin/sh\n{body}\n")
        (bin_dir / name).chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "LIVRAISON_SYSTEMD": str(units),
    }
    script = install / "scripts" / "serveur" / "installer_livraison.sh"

    result = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    service = (units / "amm-gh-livraison.service").read_text()
    keep = "/var/lib/amm-gh-livraison/livrer.sh"
    assert f"install -m 700 {install}/scripts/serveur/livrer.sh {keep}" in service
    assert f"install -m 700 {keep} /run/amm-gh-livraison.sh" in service
    assert "$" not in service.split("ExecStart=")[1]  # systemd remplacerait les $ lui-même
    assert "OnUnitInactiveSec=1min" in (units / "amm-gh-livraison.timer").read_text()
    assert "enable --now amm-gh-livraison.timer" in (tmp_path / "systemctl").read_text()
    assert "configurer.sh GITHUB_DEPLOY_TOKEN" in result.stderr

    subprocess.run(["bash", str(script), "--retirer"], env=env, check=True, capture_output=True)
    assert not (units / "amm-gh-livraison.timer").exists()
