# Selbst gehostet: Plane-MCP als eigener HTTP-Container

Ersetzt den STDIO-Eintrag in MetaMCP (`uvx --from git+…@legacy-relations plane-mcp-server stdio`).
Statt dass MetaMCP den Server selbst startet (und dabei per `uvx` von GitHub baut), läuft **ein**
langlebiger Prozess mit hartem CPU-/RAM-Limit. MetaMCP leitet nur noch per STREAMABLE_HTTP weiter.

Modus `http-header`: nur der Endpunkt `/http/api-key/mcp`, **kein OAuth** (der volle Modus `http`
bricht ohne `PLANE_OAUTH_PROVIDER_CLIENT_ID` beim Start ab und würde mit `restart: unless-stopped`
in einer Neustart-Schleife landen).

## Gemessen (lokal gegen Plane Community v1.4.2, 17.10.2026)

| | |
|---|---|
| Prozesse | 1, unabhängig von der Zahl der Sitzungen |
| Leerlauf | 0,2 % CPU, 161 MB RAM |
| 10 Sitzungen (initialize + tools/list + 1 Tool-Aufruf) | 1,3 s CPU gesamt, RAM unverändert |

Der Docker-Build selbst wurde dort nicht ausgeführt (Docker Hub gesperrt), nur dieselben
Installationsschritte in einer frischen Python-3.11-Umgebung.

## Einrichten in Coolify

1. Neue Ressource → **Docker Compose** aus Git: Repo `MarkArfis/plane-mcp-server`, Branch
   `legacy-relations`, Compose-Pfad `/deploy/docker-compose.yml`.
2. Env: `PLANE_BASE_URL=https://plane.markarfis.org` (oder die interne URL des Plane-Containers,
   dann zusätzlich `PLANE_INTERNAL_BASE_URL`). **Kein API-Key** im Container nötig.
3. **Keine Domain** vergeben — der Dienst soll nicht öffentlich erreichbar sein.
4. Netzwerk: MetaMCP muss den Container erreichen. In Coolify bei der Ressource
   „Connect to Predefined Network“ aktivieren (gemeinsames Netz `coolify`) und den Service-Namen
   notieren, den Coolify vergibt (Containername, z.B. `plane-mcp-<id>`).
5. Deploy. Healthcheck muss nach ~20 s `healthy` zeigen.

## Umstellen in MetaMCP

1. Neuer Server, Typ **STREAMABLE_HTTP**
   - URL: `http://<service-name>:8211/http/api-key/mcp`
   - Header: `Authorization: Bearer <Plane-PAT>` und `X-Workspace-slug: work`
2. Den neuen Server in den Namespace des Endpoints `plane-endpoint` aufnehmen, den alten
   STDIO-Server `plane` daraus entfernen bzw. deaktivieren.
3. In Claude Code `/mcp` → Reconnect (bzw. Konnektor neu anmelden).

## Hinweise

- Der Header-Modus prüft den Key bei **jeder** MCP-Nachricht gegen Plane (`/api/v1/users/me/`).
  Eine Sitzung kostet so 4 Plane-Aufrufe zusätzlich zu den eigentlichen Tool-Aufrufen. Plane
  begrenzt auf 60 Aufrufe/Minute pro Key — bei sehr vielen kurzen Sitzungen kann das `429` geben.
- Limits in `docker-compose.yml`: `cpus: 0.5`, `mem_limit: 384m`, `pids_limit: 128`.
- Basis-Image per Build-Argument `BASE_IMAGE` austauschbar (Default `python:3.11-slim`).
