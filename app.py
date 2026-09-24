# -*- coding: ascii -*-
# Novatrix arende backend (V37 Utokad).
# Receives a support ticket from the web form and stores it in Blob Storage
# using the web VM's system-assigned managed identity. No account key is used.
#
# Students change STORAGE_ACCOUNT below to their own globally unique account
# name (the same account the provisioning script created). BLOB_LAYOUT and
# FLOW_URL are optional and control what happens with the ticket next.

import json
import uuid
import urllib.request
from datetime import datetime, timezone

from flask import Flask, request, Response
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

# --- Settings students may change -------------------------------------------
# Your globally unique storage account name (no https, no .blob..., just name).
STORAGE_ACCOUNT = "stnovatrixXXXX"
# Container that receives the tickets (created by the provisioning script).
CONTAINER = "arenden"
# Where the ticket lands in the container:
#   "root"   -> arende-<id>.json flat in the container root. Needed for the
#               Power Automate Blob trigger, which only sees the root.
#   "folder" -> <id>/arende.json in a folder per ticket. Tidier, but the
#               Blob trigger does not see subfolders.
BLOB_LAYOUT = "root"
# Optional Power Automate HTTP trigger URL. Leave empty to skip. When set, the
# app POSTs the ticket JSON to this URL right after writing the blob.
FLOW_URL = ""
# ----------------------------------------------------------------------------

ACCOUNT_URL = "https://{0}.blob.core.windows.net".format(STORAGE_ACCOUNT)

app = Flask(__name__)

# One credential and one client for the whole app.
# DefaultAzureCredential automatically picks up the VM's system-assigned
# managed identity through IMDS, so there is no secret anywhere in the code.
_credential = DefaultAzureCredential()
_blob_service = BlobServiceClient(account_url=ACCOUNT_URL, credential=_credential)


def _container():
    return _blob_service.get_container_client(CONTAINER)


def _blob_names(ticket_id, image_filename):
    # Returns (ticket_blob_name, image_blob_name) for the chosen layout.
    # image_blob_name is None when no image was attached.
    if BLOB_LAYOUT == "folder":
        ticket_name = "{0}/arende.json".format(ticket_id)
        image_name = "{0}/{1}".format(ticket_id, image_filename) if image_filename else None
    else:
        ticket_name = "arende-{0}.json".format(ticket_id)
        image_name = "{0}-{1}".format(ticket_id, image_filename) if image_filename else None
    return ticket_name, image_name


def _notify_flow(ticket):
    # If a flow URL is configured, POST the ticket JSON to it. Wrapped in
    # try/except so a broken or missing flow never stops the ticket from
    # being saved. The form must always work even if the flow is down.
    if not FLOW_URL:
        return
    try:
        data = json.dumps(ticket, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            FLOW_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


@app.post("/submit")
def submit():
    # Read the fields from the form. The names here must match index.html.
    name = request.form.get("name", "").strip()
    mail = request.form.get("mail", "").strip()
    msg = request.form.get("msg", "").strip()
    image = request.files.get("bild")

    # A unique id per ticket: UTC timestamp plus a short random suffix.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ticket_id = "{0}-{1}".format(stamp, uuid.uuid4().hex[:8])

    ticket = {
        "id": ticket_id,
        "name": name,
        "mail": mail,
        "message": msg,
        "created": stamp,
    }

    container = _container()
    image_filename = image.filename if (image is not None and image.filename) else None
    ticket_name, image_name = _blob_names(ticket_id, image_filename)
    ticket["image"] = image_name or ""

    # 1) Store the ticket itself as a JSON blob.
    container.upload_blob(
        name=ticket_name,
        data=json.dumps(ticket, ensure_ascii=False).encode("utf-8"),
        overwrite=True,
        content_settings=ContentSettings(content_type="application/json"),
    )

    # 2) Store the attached image next to it, if the user sent one.
    if image_name is not None:
        container.upload_blob(
            name=image_name,
            data=image.stream,
            overwrite=True,
        )

    # 3) Optionally notify a Power Automate HTTP flow. Never blocks the save.
    _notify_flow(ticket)

    # A plain confirmation page. ASCII only, so the file survives cloud-init.
    body = (
        "<!DOCTYPE html><html lang='sv'><head><meta charset='UTF-8'>"
        "<title>Tack</title></head>"
        "<body style='font-family:Arial;max-width:640px;margin:40px auto'>"
        "<h1>Tack!</h1>"
        "<p>Ditt arende ar sparat med id <code>{0}</code>.</p>"
        "<p><a href='/'>Skicka in ett till</a></p>"
        "</body></html>"
    ).format(ticket_id)
    return Response(body, mimetype="text/html")


@app.get("/health")
def health():
    # Handy for a quick check that the backend is up and reading its config.
    return {
        "status": "ok",
        "account": STORAGE_ACCOUNT,
        "container": CONTAINER,
        "blob_layout": BLOB_LAYOUT,
        "flow_configured": bool(FLOW_URL),
    }


if __name__ == "__main__":
    # Bind to localhost only. nginx sits in front and proxies /submit to here.
    app.run(host="127.0.0.1", port=5000)
