import requests

# Kubernetes monta aquí, en cada pod, el token de su ServiceAccount, el
# certificado del clúster y el namespace en el que corre
SERVICE_ACCOUNT_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"

# Dentro del clúster, la API de Kubernetes siempre se encuentra con este nombre
KUBERNETES_API_URL = "https://kubernetes.default.svc"

CRONJOB_NAME = "collector"


def read_service_account_file(name):
    with open(f"{SERVICE_ACCOUNT_DIR}/{name}") as f:
        return f.read().strip()


def kubernetes_request(method, path, body=None):
    # El token se lee en cada petición porque Kubernetes lo renueva cada hora
    token = read_service_account_file("token")
    response = requests.request(
        method,
        f"{KUBERNETES_API_URL}{path}",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
        verify=f"{SERVICE_ACCOUNT_DIR}/ca.crt",
        timeout=5,
    )
    response.raise_for_status()
    return response.json()


def jobs_path():
    namespace = read_service_account_file("namespace")
    return f"/apis/batch/v1/namespaces/{namespace}/jobs"


def get_cronjob():
    namespace = read_service_account_file("namespace")
    return kubernetes_request(
        "GET", f"/apis/batch/v1/namespaces/{namespace}/cronjobs/{CRONJOB_NAME}"
    )


def is_finished(job):
    conditions = job.get("status", {}).get("conditions", [])
    return any(
        c["type"] in ("Complete", "Failed") and c["status"] == "True"
        for c in conditions
    )


def collector_running(cronjob):
    """Dice si hay algún Job del CronJob sin terminar, programado o lanzado a mano."""
    jobs = kubernetes_request("GET", jobs_path())["items"]
    uid = cronjob["metadata"]["uid"]
    return any(
        any(ref["uid"] == uid for ref in job["metadata"].get("ownerReferences", []))
        and not is_finished(job)
        for job in jobs
    )


def build_job(cronjob):
    """Arma un Job a partir de la plantilla del CronJob, como kubectl create job --from.

    El spec se copia tal cual. La política de admisión exige que el pod sea
    idéntico al de la plantilla, así que no se puede tocar nada de ahí.
    """
    template = cronjob["spec"]["jobTemplate"]
    template_metadata = template.get("metadata", {})
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "generateName": f"{CRONJOB_NAME}-refresh-",
            # Lo que traiga la plantilla, más lo que marca el Job como del botón
            "labels": {**template_metadata.get("labels", {}), "trigger": "refresh"},
            "annotations": {
                **template_metadata.get("annotations", {}),
                "cronjob.kubernetes.io/instantiate": "manual",
            },
            "ownerReferences": [
                {
                    "apiVersion": "batch/v1",
                    "kind": "CronJob",
                    "name": cronjob["metadata"]["name"],
                    "uid": cronjob["metadata"]["uid"],
                    "controller": True,
                }
            ],
        },
        "spec": template["spec"],
    }


def create_job(cronjob):
    return kubernetes_request("POST", jobs_path(), body=build_job(cronjob))
