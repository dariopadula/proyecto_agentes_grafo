from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs
from urllib.parse import urlparse

from config import DEFAULT_ACTOR
from config import LINK_ROLE_LABELS
from config import PROJECTS_DIR
from core.html_utils import html_escape
from core.json_store import load_json
from workflows.human_review import save_link_decision
from workflows.resource_review import save_resource_decision


HOST = "127.0.0.1"
PORT = 8000


class TramiteModelingHandler(BaseHTTPRequestHandler):
    """Servidor local minimo para que el funcionario revise links en navegador."""

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send_html(_projects_page())
            return

        project_id = _project_id_from_review_path(path)
        if project_id:
            self._send_html(_review_links_page(project_id, self.path))
            return

        project_id = _project_id_from_resources_path(path)
        if project_id:
            self._send_html(_resources_page(project_id, self.path))
            return

        self._send_not_found()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        resource_route = _resource_decision_route(path)
        if resource_route:
            self._save_resource_review(resource_route)
            return

        route = _decision_route(path)
        if not route:
            self._send_not_found()
            return

        project_id, link_id = route
        form = self._read_form()
        primary_role = _single(form, "primary_role")
        if not primary_role:
            self._redirect(
                f"/projects/{project_id}/review-links?error=missing_role#{link_id}"
            )
            return

        try:
            save_link_decision(
                project_id=project_id,
                link_id=link_id,
                primary_role=primary_role,
                secondary_roles=form.get("secondary_role", []),
                confidence=_single(form, "confidence", "media"),
                notes=_single(form, "notes"),
                actor=_single(form, "actor", DEFAULT_ACTOR),
            )
        except ValueError as error:
            self._redirect(
                f"/projects/{project_id}/review-links?error={html_escape(error)}#{link_id}"
            )
            return

        self._redirect(f"/projects/{project_id}/review-links?saved={link_id}#{link_id}")

    def _save_resource_review(self, route: tuple[str, str, str]) -> None:
        project_id, source_link_id, resource_id = route
        form = self._read_form()
        use = _single(form, "use")
        if not use:
            self._redirect(
                f"/projects/{project_id}/resources?error=missing_use#{source_link_id}-{resource_id}"
            )
            return

        try:
            save_resource_decision(
                project_id=project_id,
                source_link_id=source_link_id,
                resource_id=resource_id,
                use=use,
                scope=_single(form, "scope", "node_only"),
                notes=_single(form, "notes"),
                actor=_single(form, "actor", DEFAULT_ACTOR),
            )
        except ValueError as error:
            self._redirect(
                f"/projects/{project_id}/resources?error={html_escape(error)}#{source_link_id}-{resource_id}"
            )
            return

        self._redirect(
            f"/projects/{project_id}/resources?saved={source_link_id}-{resource_id}"
            f"#{source_link_id}-{resource_id}"
        )

    def log_message(self, format: str, *args: Any) -> None:
        # Mantiene la consola limpia; los errores se informan en la pagina.
        return

    def _read_form(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8")
        return parse_qs(raw_body, keep_blank_values=True)

    def _send_html(self, html: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def _send_not_found(self) -> None:
        self._send_html(
            _page("No encontrado", "<p>No existe esa pantalla.</p>"),
            HTTPStatus.NOT_FOUND,
        )


def run() -> None:
    server = ThreadingHTTPServer((HOST, PORT), TramiteModelingHandler)
    print(f"App local: http://{HOST}:{PORT}/")
    print("Presiona Ctrl+C para detener.")
    server.serve_forever()


def _projects_page() -> str:
    projects = []
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        project_path = project_dir / "project.json"
        if project_path.exists():
            projects.append(load_json(project_path))

    if not projects:
        body = """
        <section class="panel">
          <h2>No hay proyectos creados</h2>
          <p>Primero crea un proyecto con <code>python app.py init-project</code>.</p>
        </section>
        """
        return _page("Proyectos", body)

    cards = []
    for project in projects:
        project_id = project.get("project_id", "")
        cards.append(
            f"""
            <article class="card">
              <h2>{html_escape(project.get("name"))}</h2>
              <p class="muted">{html_escape(project.get("start_url"))}</p>
              <dl>
                <dt>Estado</dt><dd>{html_escape(project.get("status"))}</dd>
                <dt>Actualizado</dt><dd>{html_escape(project.get("updated_at"))}</dd>
              </dl>
              <a class="button" href="/projects/{html_escape(project_id)}/review-links">
                Revisar links
              </a>
              <a class="button secondary" href="/projects/{html_escape(project_id)}/resources">
                Ver recursos internos
              </a>
            </article>
            """
        )

    return _page("Proyectos", "<section class=\"grid\">" + "".join(cards) + "</section>")


def _resources_page(project_id: str, request_path: str) -> str:
    project_dir = PROJECTS_DIR / project_id
    project = load_json(project_dir / "project.json")
    node_resources_path = project_dir / "node_resources.json"
    if not node_resources_path.exists():
        body = f"""
        <section class="panel">
          <p><a href="/">Volver a proyectos</a></p>
          <h2>{html_escape(project.get("name"))}</h2>
          <p>No existe <code>node_resources.json</code> para este proyecto.</p>
          <p class="muted">Primero ejecuta <code>python app.py discover-resources --project-id {html_escape(project_id)}</code>.</p>
        </section>
        """
        return _page(f"Recursos internos - {project.get('name')}", body)

    node_resources = load_json(node_resources_path)
    resource_review_path = project_dir / "resource_review.json"
    resource_review = (
        load_json(resource_review_path)
        if resource_review_path.exists()
        else {"decisions": [], "review_status": "not_started"}
    )
    decisions_by_resource = {
        decision.get("decision_id"): decision
        for decision in resource_review.get("decisions", [])
    }
    pages = node_resources.get("pages", [])
    total_resources = node_resources.get("resources_count", 0)
    total_discarded = node_resources.get("discarded_resources_count", 0)
    reviewed_resources = len(decisions_by_resource)
    message = _status_message(request_path)

    cards = "".join(
        _resource_page_card(project_id, page, decisions_by_resource)
        for page in pages
    )
    body = f"""
    <section class="panel">
      <p>
        <a href="/">Volver a proyectos</a> |
        <a href="/projects/{html_escape(project_id)}/review-links">Revisar links principales</a>
      </p>
      <h2>{html_escape(project.get("name"))}</h2>
      <p class="muted">Recursos internos detectados dentro de los links aceptados.</p>
      <div class="stats">
        <div><strong>{html_escape(node_resources.get("accepted_links_count"))}</strong><span>Nodos explorados</span></div>
        <div><strong>{html_escape(total_resources)}</strong><span>Recursos utiles</span></div>
        <div><strong>{html_escape(total_discarded)}</strong><span>Descartados por regla</span></div>
        <div><strong>{html_escape(reviewed_resources)}</strong><span>Recursos revisados</span></div>
      </div>
      {message}
    </section>
    <section class="toolbar">
      <input id="search" type="search" placeholder="Buscar por nodo, URL o recurso">
      <select id="typeFilter">
        <option value="">Todos los tipos</option>
        {_resource_type_options(pages)}
      </select>
      <select id="discardFilter">
        <option value="">Utiles y descartados</option>
        <option value="kept">Solo utiles</option>
        <option value="discarded">Solo descartados</option>
      </select>
      <button type="button" onclick="clearResourceFilters()">Limpiar</button>
    </section>
    <section class="cards">
      {cards}
    </section>
    <script>
      const search = document.getElementById("search");
      const typeFilter = document.getElementById("typeFilter");
      const discardFilter = document.getElementById("discardFilter");
      search.addEventListener("input", applyResourceFilters);
      typeFilter.addEventListener("change", applyResourceFilters);
      discardFilter.addEventListener("change", applyResourceFilters);

      function applyResourceFilters() {{
        const query = search.value.trim().toLowerCase();
        const type = typeFilter.value;
        const discardState = discardFilter.value;
        document.querySelectorAll(".resource-row").forEach(row => {{
          const matchesText = !query || row.dataset.search.includes(query);
          const matchesType = !type || row.dataset.type === type;
          const matchesDiscard = !discardState || row.dataset.discard === discardState;
          row.classList.toggle("hidden", !(matchesText && matchesType && matchesDiscard));
        }});
      }}

      function clearResourceFilters() {{
        search.value = "";
        typeFilter.value = "";
        discardFilter.value = "";
        applyResourceFilters();
      }}
    </script>
    """
    return _page(f"Recursos internos - {project.get('name')}", body)


def _review_links_page(project_id: str, request_path: str) -> str:
    project_dir = PROJECTS_DIR / project_id
    project = load_json(project_dir / "project.json")
    candidate_links = load_json(project_dir / "candidate_links.json")
    human_review = load_json(project_dir / "human_review.json")
    decisions_by_link = {
        decision.get("link_id"): decision
        for decision in human_review.get("decisions", [])
    }
    links = candidate_links.get("links", [])
    reviewed_count = sum(
        1
        for link in links
        if decisions_by_link.get(link.get("link_id"), {}).get("primary_role")
    )
    message = _status_message(request_path)

    cards = []
    for link in links:
        decision = decisions_by_link.get(link.get("link_id"), {})
        cards.append(_link_card(project_id, link, decision))

    body = f"""
    <section class="panel">
      <p><a href="/">Volver a proyectos</a></p>
      <h2>{html_escape(project.get("name"))}</h2>
      <p class="muted">{html_escape(project.get("start_url"))}</p>
      <div class="stats">
        <div><strong>{len(links)}</strong><span>Links candidatos</span></div>
        <div><strong>{reviewed_count}</strong><span>Revisados</span></div>
        <div><strong>{len(links) - reviewed_count}</strong><span>Pendientes</span></div>
        <div><strong>{html_escape(human_review.get("review_status"))}</strong><span>Estado</span></div>
      </div>
      {message}
    </section>
    <section class="toolbar">
      <input id="search" type="search" placeholder="Buscar por titulo, URL o notas">
      <select id="roleFilter">
        <option value="">Todos los roles</option>
        {_role_filter_options()}
      </select>
      <button type="button" onclick="clearFilters()">Limpiar</button>
    </section>
    <section class="cards">
      {"".join(cards)}
    </section>
    <script>
      const search = document.getElementById("search");
      const roleFilter = document.getElementById("roleFilter");
      search.addEventListener("input", applyFilters);
      roleFilter.addEventListener("change", applyFilters);

      function applyFilters() {{
        const query = search.value.trim().toLowerCase();
        const role = roleFilter.value;
        document.querySelectorAll(".card").forEach(card => {{
          const matchesText = !query || card.dataset.search.includes(query);
          const matchesRole = !role || card.dataset.role === role;
          card.classList.toggle("hidden", !(matchesText && matchesRole));
        }});
      }}

      function clearFilters() {{
        search.value = "";
        roleFilter.value = "";
        applyFilters();
      }}
    </script>
    """
    return _page(f"Revision de links - {project.get('name')}", body)


def _link_card(
    project_id: str,
    link: dict[str, Any],
    decision: dict[str, Any],
) -> str:
    link_id = link.get("link_id", "")
    primary_role = decision.get("primary_role", "")
    secondary_roles = set(decision.get("secondary_roles", []))
    confidence = decision.get("confidence", "media")
    notes = decision.get("notes", "")
    search_text = " ".join(
        str(value or "")
        for value in [
            link_id,
            link.get("title"),
            link.get("url"),
            link.get("anchor_text"),
            notes,
        ]
    ).lower()

    return f"""
    <article class="card" id="{html_escape(link_id)}"
        data-role="{html_escape(primary_role)}"
        data-search="{html_escape(search_text)}">
      <div class="card-head">
        <div>
          <p class="eyebrow">{html_escape(link_id)}</p>
          <h2>
            <a href="{html_escape(link.get("url"))}" target="_blank" rel="noreferrer">
              {html_escape(link.get("title") or link.get("url"))}
            </a>
          </h2>
          <p class="url">{html_escape(link.get("url"))}</p>
        </div>
        <span class="pill">{_role_label(primary_role) or "Sin clasificar"}</span>
      </div>
      <dl>
        <dt>Texto detectado</dt><dd>{html_escape(link.get("anchor_text"))}</dd>
        <dt>Contexto</dt><dd>{html_escape(link.get("source_context"))}</dd>
        <dt>Motivo</dt><dd>{html_escape(link.get("detection_reason"))}</dd>
      </dl>
      <form method="post" action="/projects/{html_escape(project_id)}/review-links/{html_escape(link_id)}">
        <div class="form-grid">
          <label>
            Rol principal
            <select name="primary_role" required>
              <option value="">Seleccionar</option>
              {_role_options(primary_role)}
            </select>
          </label>
          <label>
            Confianza
            <select name="confidence">
              {_confidence_options(confidence)}
            </select>
          </label>
          <label>
            Revisor
            <input name="actor" value="{html_escape(decision.get("reviewed_by", DEFAULT_ACTOR))}">
          </label>
        </div>
        <fieldset>
          <legend>Roles secundarios</legend>
          {_secondary_role_checkboxes(secondary_roles)}
        </fieldset>
        <label>
          Notas del funcionario
          <textarea name="notes" placeholder="Ejemplo: puede ser tramite propio y tambien informacion auxiliar para otros nodos.">{html_escape(notes)}</textarea>
        </label>
        <div class="actions">
          <button type="submit">Guardar decision</button>
          <span class="muted">{_reviewed_at(decision)}</span>
        </div>
      </form>
    </article>
    """


def _resource_page_card(
    project_id: str,
    page: dict[str, Any],
    decisions_by_resource: dict[str, dict[str, Any]],
) -> str:
    resources = page.get("resources", [])
    discarded = page.get("discarded_resources", [])
    rows = "".join(
        _resource_row(
            project_id,
            page.get("link_id", ""),
            resource,
            "kept",
            decisions_by_resource.get(
                f"{page.get('link_id')}::{resource.get('resource_id')}",
                {},
            ),
        )
        for resource in resources
    )
    discarded_rows = "".join(
        _resource_row(project_id, page.get("link_id", ""), resource, "discarded", {})
        for resource in discarded
    )
    error = ""
    if page.get("status") == "error":
        error = f"""<p class="message error">{html_escape(page.get("error"))}</p>"""

    return f"""
    <article class="card">
      <div class="card-head">
        <div>
          <p class="eyebrow">{html_escape(page.get("link_id"))}</p>
          <h2>
            <a href="{html_escape(page.get("url"))}" target="_blank" rel="noreferrer">
              {html_escape(page.get("title") or page.get("url"))}
            </a>
          </h2>
          <p class="url">{html_escape(page.get("url"))}</p>
        </div>
        <span class="pill">{len(resources)} utiles / {len(discarded)} descartados</span>
      </div>
      {error}
      <h3>Recursos utiles</h3>
      {_empty_message(resources, "No se detectaron recursos utiles.")}
      <div class="resource-list">{rows}</div>
      <h3>Descartados por regla</h3>
      {_empty_message(discarded, "No hubo descartes por regla.")}
      <div class="resource-list">{discarded_rows}</div>
    </article>
    """


def _resource_row(
    project_id: str,
    source_link_id: str,
    resource: dict[str, Any],
    discard_state: str,
    decision: dict[str, Any],
) -> str:
    reason = ""
    if discard_state == "discarded":
        reason = f"""
        <dl>
          <dt>Regla</dt><dd>{html_escape(resource.get("discard_rule_id"))}</dd>
          <dt>Motivo</dt><dd>{html_escape(resource.get("discard_reason"))}</dd>
        </dl>
        """
    review_form = ""
    if discard_state == "kept":
        review_form = _resource_review_form(
            project_id,
            source_link_id,
            resource,
            decision,
        )
    search_text = " ".join(
        str(value or "")
        for value in [
            resource.get("resource_id"),
            resource.get("title"),
            resource.get("url"),
            resource.get("anchor_text"),
            resource.get("source_context"),
            resource.get("discard_reason"),
        ]
    ).lower()
    return f"""
    <div class="resource-row" id="{html_escape(source_link_id)}-{html_escape(resource.get("resource_id"))}"
        data-search="{html_escape(search_text)}"
        data-type="{html_escape(resource.get("resource_type"))}"
        data-discard="{html_escape(discard_state)}">
      <div class="resource-head">
        <span class="pill">{html_escape(resource.get("resource_type"))}</span>
        <strong>
          <a href="{html_escape(resource.get("url"))}" target="_blank" rel="noreferrer">
            {html_escape(resource.get("title") or resource.get("url"))}
          </a>
        </strong>
      </div>
      <p class="url">{html_escape(resource.get("url"))}</p>
      <dl>
        <dt>Texto</dt><dd>{html_escape(resource.get("anchor_text"))}</dd>
        <dt>Contexto</dt><dd>{html_escape(resource.get("source_context"))}</dd>
      </dl>
      {reason}
      {review_form}
    </div>
    """


def _resource_review_form(
    project_id: str,
    source_link_id: str,
    resource: dict[str, Any],
    decision: dict[str, Any],
) -> str:
    return f"""
    <form method="post" action="/projects/{html_escape(project_id)}/resources/{html_escape(source_link_id)}/{html_escape(resource.get("resource_id"))}">
      <div class="form-grid">
        <label>
          Que hacemos con este recurso
          <select name="use" required>
            <option value="">Seleccionar</option>
            {_resource_use_options(decision.get("use", ""))}
          </select>
        </label>
        <label>
          Donde aplica
          <select name="scope">
            {_resource_scope_options(decision.get("scope", "node_only"))}
          </select>
        </label>
        <label>
          Revisor
          <input name="actor" value="{html_escape(decision.get("reviewed_by", DEFAULT_ACTOR))}">
        </label>
      </div>
      <label>
        Notas del funcionario
        <textarea name="notes" placeholder="Ejemplo: mostrar solo como enlace porque es una lista que el usuario debe consultar.">{html_escape(decision.get("notes", ""))}</textarea>
      </label>
      <div class="actions">
        <button type="submit">Guardar decision del recurso</button>
        <span class="muted">{_reviewed_at(decision)}</span>
      </div>
    </form>
    """


def _resource_use_options(selected: str) -> str:
    labels = {
        "process_as_context": "Procesar como contexto",
        "show_as_link": "Mostrar solo como enlace",
        "discard": "Descartar",
        "review_later": "Revisar despues",
    }
    return "".join(
        f"""
        <option value="{html_escape(code)}" {"selected" if code == selected else ""}>
          {html_escape(label)}
        </option>
        """
        for code, label in labels.items()
    )


def _resource_scope_options(selected: str) -> str:
    labels = {
        "node_only": "Solo este nodo",
        "shared": "Compartido con varios nodos",
    }
    return "".join(
        f"""
        <option value="{html_escape(code)}" {"selected" if code == selected else ""}>
          {html_escape(label)}
        </option>
        """
        for code, label in labels.items()
    )


def _empty_message(items: list[dict[str, Any]], message: str) -> str:
    if items:
        return ""
    return f"""<p class="muted">{html_escape(message)}</p>"""


def _resource_type_options(pages: list[dict[str, Any]]) -> str:
    types = set()
    for page in pages:
        for resource in page.get("resources", []):
            types.add(resource.get("resource_type", ""))
        for resource in page.get("discarded_resources", []):
            types.add(resource.get("resource_type", ""))
    return "".join(
        f"""<option value="{html_escape(resource_type)}">{html_escape(resource_type)}</option>"""
        for resource_type in sorted(types)
        if resource_type
    )


def _role_options(selected: str) -> str:
    return "".join(
        f"""
        <option value="{html_escape(code)}" {"selected" if code == selected else ""}>
          {html_escape(label)}
        </option>
        """
        for code, label in sorted(LINK_ROLE_LABELS.items(), key=lambda item: item[1])
    )


def _secondary_role_checkboxes(selected: set[str]) -> str:
    return "".join(
        f"""
        <label class="checkbox">
          <input type="checkbox" name="secondary_role" value="{html_escape(code)}"
              {"checked" if code in selected else ""}>
          {html_escape(label)}
        </label>
        """
        for code, label in sorted(LINK_ROLE_LABELS.items(), key=lambda item: item[1])
    )


def _confidence_options(selected: str) -> str:
    labels = ["alta", "media", "baja"]
    return "".join(
        f"""<option value="{value}" {"selected" if value == selected else ""}>{value}</option>"""
        for value in labels
    )


def _role_filter_options() -> str:
    return "".join(
        f"""<option value="{html_escape(code)}">{html_escape(label)}</option>"""
        for code, label in sorted(LINK_ROLE_LABELS.items(), key=lambda item: item[1])
    )


def _role_label(code: str) -> str:
    return html_escape(LINK_ROLE_LABELS.get(code, ""))


def _reviewed_at(decision: dict[str, Any]) -> str:
    reviewed_at = decision.get("reviewed_at")
    if not reviewed_at:
        return "Sin guardar"
    return f"Guardado: {html_escape(reviewed_at)}"


def _project_id_from_review_path(path: str) -> str | None:
    parts = path.strip("/").split("/")
    if len(parts) == 3 and parts[0] == "projects" and parts[2] == "review-links":
        return parts[1]
    return None


def _project_id_from_resources_path(path: str) -> str | None:
    parts = path.strip("/").split("/")
    if len(parts) == 3 and parts[0] == "projects" and parts[2] == "resources":
        return parts[1]
    return None


def _decision_route(path: str) -> tuple[str, str] | None:
    parts = path.strip("/").split("/")
    if len(parts) == 4 and parts[0] == "projects" and parts[2] == "review-links":
        return parts[1], parts[3]
    return None


def _resource_decision_route(path: str) -> tuple[str, str, str] | None:
    parts = path.strip("/").split("/")
    if len(parts) == 5 and parts[0] == "projects" and parts[2] == "resources":
        return parts[1], parts[3], parts[4]
    return None


def _single(
    form: dict[str, list[str]],
    key: str,
    default: str = "",
) -> str:
    values = form.get(key)
    if not values:
        return default
    return values[0]


def _status_message(request_path: str) -> str:
    query = parse_qs(urlparse(request_path).query)
    if "saved" in query:
        return f"""<p class="message ok">Decision guardada para {html_escape(query["saved"][0])}.</p>"""
    if "error" in query:
        return f"""<p class="message error">No se pudo guardar: {html_escape(query["error"][0])}</p>"""
    return ""


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html_escape(title)}</title>
  <style>
    :root {{
      --bg: #f4f6f8;
      --panel: #ffffff;
      --text: #20242a;
      --muted: #667085;
      --border: #d5dbe3;
      --accent: #0b5cad;
      --ok-bg: #ecfdf3;
      --ok-text: #027a48;
      --error-bg: #fff1f3;
      --error-text: #b42318;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--text);
      background: var(--bg);
      font-family: Arial, Helvetica, sans-serif;
    }}
    header {{
      background: var(--panel);
      border-bottom: 1px solid var(--border);
      padding: 18px 24px;
    }}
    header h1 {{
      margin: 0;
      font-size: 24px;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 20px;
    }}
    a {{ color: var(--accent); }}
    .grid, .cards {{
      display: grid;
      gap: 14px;
    }}
    .panel, .card {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
    }}
    .card.hidden {{ display: none; }}
    .card-head {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
    }}
    .card h2, .panel h2 {{
      margin: 0 0 8px;
      font-size: 18px;
      line-height: 1.3;
    }}
    .eyebrow {{
      margin: 0 0 4px;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
    }}
    .muted, .url {{
      color: var(--muted);
      overflow-wrap: anywhere;
    }}
    .button, button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 36px;
      margin-right: 8px;
      padding: 0 12px;
      border: 1px solid var(--accent);
      border-radius: 6px;
      color: #fff;
      background: var(--accent);
      text-decoration: none;
      font: inherit;
      cursor: pointer;
    }}
    .button.secondary {{
      color: var(--accent);
      background: #fff;
    }}
    .toolbar {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin: 14px 0;
    }}
    input, select, textarea {{
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px;
      font: inherit;
      background: #fff;
    }}
    .toolbar input {{ max-width: 430px; }}
    .toolbar select {{ max-width: 240px; }}
    textarea {{
      min-height: 84px;
      resize: vertical;
    }}
    dl {{
      display: grid;
      grid-template-columns: 150px minmax(0, 1fr);
      gap: 6px 12px;
      margin: 12px 0;
      font-size: 14px;
    }}
    dt {{ color: var(--muted); }}
    dd {{ margin: 0; }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-top: 14px;
    }}
    .stats div {{
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 10px;
    }}
    .stats strong {{
      display: block;
      font-size: 22px;
    }}
    .stats span {{
      color: var(--muted);
      font-size: 12px;
    }}
    .pill {{
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 4px 10px;
      color: var(--muted);
      background: #f8fafc;
      font-size: 13px;
      white-space: nowrap;
    }}
    .form-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin: 12px 0;
    }}
    label, legend {{
      color: var(--muted);
      font-size: 13px;
    }}
    fieldset {{
      border: 1px solid var(--border);
      border-radius: 6px;
      margin: 12px 0;
      padding: 10px;
    }}
    .checkbox {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      margin: 5px 12px 5px 0;
      color: var(--text);
    }}
    .checkbox input {{
      width: auto;
    }}
    .actions {{
      display: flex;
      align-items: center;
      gap: 12px;
      margin-top: 12px;
    }}
    .message {{
      border-radius: 6px;
      padding: 10px;
    }}
    .message.ok {{
      background: var(--ok-bg);
      color: var(--ok-text);
    }}
    .message.error {{
      background: var(--error-bg);
      color: var(--error-text);
    }}
    h3 {{
      margin: 18px 0 8px;
      font-size: 15px;
    }}
    .resource-list {{
      display: grid;
      gap: 8px;
    }}
    .resource-row {{
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 10px;
      background: #fbfcfe;
    }}
    .resource-row.hidden {{
      display: none;
    }}
    .resource-head {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }}
    @media (max-width: 760px) {{
      .card-head, .form-grid, .stats, dl {{
        display: grid;
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <header><h1>{html_escape(title)}</h1></header>
  <main>{body}</main>
</body>
</html>
"""


if __name__ == "__main__":
    run()
