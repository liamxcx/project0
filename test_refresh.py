import refresh

# Un CronJob reducido a lo que miran las funciones, con el uid que pone Kubernetes
CRONJOB = {
    "metadata": {"name": "collector", "uid": "uid-del-cronjob"},
    "spec": {
        "jobTemplate": {
            "spec": {
                "backoffLimit": 1,
                "template": {
                    "spec": {
                        "restartPolicy": "Never",
                        "containers": [
                            {
                                "name": "collector",
                                "image": "ghcr.io/liamxcx/project0:abc1234",
                                "command": ["python", "collector.py"],
                            }
                        ],
                    }
                },
            }
        }
    },
}


def job(owner_uid, conditions=()):
    return {
        "metadata": {"ownerReferences": [{"kind": "CronJob", "uid": owner_uid}]},
        "status": {"conditions": [{"type": t, "status": "True"} for t in conditions]},
    }


def test_build_job_is_what_the_admission_policy_accepts():
    built = refresh.build_job(CRONJOB)
    owner = built["metadata"]["ownerReferences"][0]

    # Las dos condiciones de la política: el spec idéntico y el CronJob como dueño
    assert built["spec"] == CRONJOB["spec"]["jobTemplate"]["spec"]
    assert (owner["kind"], owner["name"], owner["uid"]) == (
        "CronJob",
        "collector",
        "uid-del-cronjob",
    )


def test_collector_running_ignores_finished_and_foreign_jobs(monkeypatch):
    jobs = [
        job("uid-del-cronjob", ["Complete"]),
        job("uid-del-cronjob", ["Failed"]),
        # Sin terminar, pero de otro dueño
        job("otro-uid"),
    ]
    monkeypatch.setattr(refresh, "kubernetes_request", lambda *args: {"items": jobs})
    monkeypatch.setattr(refresh, "read_service_account_file", lambda name: "project0")

    assert refresh.collector_running(CRONJOB) is False


def test_collector_running_finds_an_unfinished_job(monkeypatch):
    jobs = [job("uid-del-cronjob", ["Complete"]), job("uid-del-cronjob")]
    monkeypatch.setattr(refresh, "kubernetes_request", lambda *args: {"items": jobs})
    monkeypatch.setattr(refresh, "read_service_account_file", lambda name: "project0")

    assert refresh.collector_running(CRONJOB) is True
