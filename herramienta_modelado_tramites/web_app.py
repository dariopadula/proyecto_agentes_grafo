from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs
from urllib.parse import urlencode
from urllib.parse import urlparse

from config import DEFAULT_ACTOR
from config import LINK_ROLE_LABELS
from config import PROJECTS_DIR
from core.html_utils import html_escape
from core.json_store import load_json
from workflows.human_review import save_link_decision
from workflows.auxiliary_link_group_review import save_auxiliary_group_decision
from workflows.pdf_analysis import mark_pdf_family_verification_queued
from workflows.pdf_analysis import mark_pdf_family_verification_failed
from workflows.pdf_analysis import verify_pdf_family
from workflows.pdf_group_review import save_pdf_family_decision
from workflows.pdf_group_review import save_pdf_partition_decision
from workflows.resource_review import save_resource_decision
from workflows.resource_filter_rules import load_or_create_resource_filter_rules
from workflows.resource_filter_rules import save_resource_filter_configuration
from workflows.resource_identity_review import save_resource_identity_decision
from workflows.effective_project_state import resolve_effective_project_state
from workflows.document_map import build_document_map
from workflows.lifecycle_review import node_lifecycle_impact
from workflows.lifecycle_review import save_node_lifecycle_status
from workflows.link_discovery import discover_candidate_links
from workflows.project_administration import delete_project_recoverably
from workflows.project_setup import create_project
from ui.document_map_page import render_document_map_body


HOST = "127.0.0.1"
PORT = 8000
PDF_VERIFICATION_EXECUTOR = ThreadPoolExecutor(max_workers=2)


class TramiteModelingHandler(BaseHTTPRequestHandler):
    """Servidor local minimo para que el funcionario revise links en navegador."""

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send_html(_projects_page(self.path))
            return

        if path == "/projects/new":
            self._send_html(_new_project_page(self.path))
            return

        delete_project_id = _project_id_from_delete_path(path)
        if delete_project_id:
            self._send_html(_delete_project_page(delete_project_id, self.path))
            return

        project_id = _project_id_from_review_path(path)
        if project_id:
            self._send_html(_review_links_page(project_id, self.path))
            return

        project_id = _project_id_from_resources_path(path)
        if project_id:
            self._send_html(_resources_page(project_id, self.path))
            return

        project_id = _project_id_from_resource_rules_path(path)
        if project_id:
            self._send_html(_resource_rules_page(project_id, self.path))
            return

        project_id = _project_id_from_pdf_groups_path(path)
        if project_id:
            self._send_html(_pdf_groups_page(project_id, self.path))
            return

        project_id = _project_id_from_auxiliary_links_path(path)
        if project_id:
            self._send_html(_auxiliary_links_page(project_id, self.path))
            return

        project_id = _project_id_from_effective_state_path(path)
        if project_id:
            self._send_html(_effective_state_page(project_id, self.path))
            return

        project_id = _project_id_from_document_map_path(path)
        if project_id:
            self._send_html(_document_map_page(project_id))
            return

        self._send_not_found()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/projects":
            form = self._read_form()
            try:
                create_project(
                    project_id=_single(form, "project_id"),
                    name=_single(form, "name"),
                    start_url=_single(form, "start_url"),
                    description=_single(form, "description"),
                    actor=_single(form, "actor", DEFAULT_ACTOR),
                )
            except (OSError, ValueError) as error:
                self._redirect(f"/projects/new?{urlencode({'error': str(error)})}")
                return
            project_id = _single(form, "project_id")
            self._redirect(
                f"/projects/{project_id}/review-links?created=1"
            )
            return

        discover_project_id = _project_id_from_discover_path(path)
        if discover_project_id:
            form = self._read_form()
            try:
                result = discover_candidate_links(
                    project_id=discover_project_id,
                    actor=_single(form, "actor", DEFAULT_ACTOR),
                )
            except Exception as error:
                self._redirect(
                    f"/?{urlencode({'error': f'No se pudieron buscar enlaces: {error}'})}"
                )
                return
            self._redirect(
                f"/projects/{discover_project_id}/review-links?"
                f"{urlencode({'discovered': result['links_count'], 'pages': result['pages_scanned'], 'page_errors': len(result['page_errors']), 'page_limit': int(result['page_limit_reached'])})}"
            )
            return

        delete_project_id = _project_id_from_delete_path(path)
        if delete_project_id:
            form = self._read_form()
            try:
                delete_project_recoverably(
                    project_id=delete_project_id,
                    confirmation=_single(form, "confirmation"),
                    actor=_single(form, "actor", DEFAULT_ACTOR),
                )
            except (OSError, ValueError) as error:
                self._redirect(
                    f"/projects/{delete_project_id}/delete?"
                    f"{urlencode({'error': str(error)})}"
                )
                return
            self._redirect(f"/?{urlencode({'deleted': delete_project_id})}")
            return

        document_resource_route = _document_map_resource_route(path)
        if document_resource_route:
            project_id, source_link_id, resource_id = document_resource_route
            form = self._read_form()
            try:
                save_resource_decision(
                    project_id=project_id,
                    source_link_id=source_link_id,
                    resource_id=resource_id,
                    use=_single(form, "use"),
                    scope="node_only",
                    notes=_single(form, "notes"),
                    actor=_single(form, "actor", DEFAULT_ACTOR),
                )
            except ValueError as error:
                self._redirect(
                    f"/projects/{project_id}/document-map?"
                    f"{urlencode({'error': str(error), 'node': source_link_id})}"
                )
                return
            self._redirect(
                f"/projects/{project_id}/document-map?"
                f"{urlencode({'saved': resource_id, 'node': source_link_id})}"
            )
            return

        lifecycle_route = _lifecycle_decision_route(path)
        if lifecycle_route:
            project_id, link_id = lifecycle_route
            form = self._read_form()
            try:
                save_node_lifecycle_status(
                    project_id=project_id,
                    link_id=link_id,
                    status=_single(form, "status"),
                    notes=_single(form, "notes"),
                    actor=_single(form, "actor", DEFAULT_ACTOR),
                )
            except ValueError as error:
                self._redirect(
                    f"/projects/{project_id}/effective-state?"
                    f"{urlencode({'error': str(error)})}"
                )
                return
            self._redirect(
                f"/projects/{project_id}/effective-state?saved={link_id}#{link_id}"
            )
            return

        identity_route = _resource_identity_route(path)
        if identity_route:
            project_id, source_link_id, resource_id = identity_route
            form = self._read_form()
            filters = _resource_filters_from_form(form)
            try:
                save_resource_identity_decision(
                    project_id=project_id,
                    appearance_id=f"{source_link_id}::{resource_id}",
                    action=_single(form, "identity_action"),
                    target_family_id=_single(form, "target_family_id"),
                    assignment_mode=_single(form, "assignment_mode"),
                    new_family_name=_single(form, "new_family_name"),
                    notes=_single(form, "identity_notes"),
                    actor=_single(form, "actor", DEFAULT_ACTOR),
                )
            except ValueError as error:
                self._redirect(
                    _resource_review_redirect(
                        project_id,
                        source_link_id,
                        resource_id,
                        {"error": str(error), **filters},
                    )
                )
                return
            self._redirect(
                _resource_review_redirect(
                    project_id,
                    source_link_id,
                    resource_id,
                    {
                        "saved_identity": f"{source_link_id}-{resource_id}",
                        **filters,
                    },
                )
            )
            return

        project_id = _project_id_from_resource_rules_path(path)
        if project_id:
            form = self._read_form()
            try:
                save_resource_filter_configuration(
                    project_id=project_id,
                    enabled_rule_ids=form.get("enabled_rule", []),
                    match_type=_single(form, "match_type", "url_contains"),
                    pattern=_single(form, "pattern"),
                    reason=_single(form, "reason"),
                )
            except ValueError as error:
                self._redirect(
                    f"/projects/{project_id}/resource-rules?error={html_escape(error)}"
                )
                return
            self._redirect(f"/projects/{project_id}/resource-rules?saved=1")
            return

        resource_route = _resource_decision_route(path)
        if resource_route:
            self._save_resource_review(resource_route)
            return

        pdf_group_route = _pdf_group_decision_route(path)
        if pdf_group_route:
            self._save_pdf_group_review(pdf_group_route)
            return

        pdf_family_decision_route = _pdf_family_decision_route(path)
        if pdf_family_decision_route:
            self._save_pdf_family_decision(pdf_family_decision_route)
            return

        pdf_verify_route = _pdf_family_verify_route(path)
        if pdf_verify_route:
            self._verify_pdf_family(pdf_verify_route)
            return

        auxiliary_group_route = _auxiliary_group_decision_route(path)
        if auxiliary_group_route:
            self._save_auxiliary_group_review(auxiliary_group_route)
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
        filters = _resource_filters_from_form(form)
        use = _single(form, "use")
        if not use:
            self._redirect(
                _resource_review_redirect(
                    project_id,
                    source_link_id,
                    resource_id,
                    {"error": "missing_use", **filters},
                )
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
                _resource_review_redirect(
                    project_id,
                    source_link_id,
                    resource_id,
                    {"error": str(error), **filters},
                )
            )
            return

        self._redirect(
            _resource_review_redirect(
                project_id,
                source_link_id,
                resource_id,
                {"saved": f"{source_link_id}-{resource_id}", **filters},
            )
        )

    def _save_pdf_group_review(self, route: tuple[str, str, str]) -> None:
        project_id, family_id, partition_id = route
        form = self._read_form()
        try:
            save_pdf_partition_decision(
                project_id=project_id,
                family_id=family_id,
                partition_id=partition_id,
                identity_decision=_single(form, "identity_decision"),
                default_use=_single(form, "default_use"),
                selected_canonical_url=_single(form, "selected_canonical_url"),
                display_name=_single(form, "display_name"),
                notes=_single(form, "notes"),
                actor=_single(form, "actor", DEFAULT_ACTOR),
            )
        except ValueError as error:
            self._redirect(
                f"/projects/{project_id}/pdf-groups?error={html_escape(error)}"
                f"#{family_id}"
            )
            return
        self._redirect(
            f"/projects/{project_id}/pdf-groups?saved={partition_id}#{family_id}"
        )

    def _verify_pdf_family(self, route: tuple[str, str]) -> None:
        project_id, family_id = route
        form = self._read_form()
        verify_pdf_family(
            project_id=project_id,
            family_id=family_id,
            actor=_single(form, "actor", DEFAULT_ACTOR),
            local_only=_single(form, "local_only") == "true",
        )
        self._redirect(
            f"/projects/{project_id}/pdf-groups?verified={family_id}#{family_id}"
        )

    def _save_pdf_family_decision(self, route: tuple[str, str]) -> None:
        project_id, family_id = route
        form = self._read_form()
        try:
            save_pdf_family_decision(
                project_id=project_id,
                family_id=family_id,
                default_use=_single(form, "default_use"),
                selected_canonical_url=_single(form, "selected_canonical_url"),
                display_name=_single(form, "display_name"),
                notes=_single(form, "notes"),
                actor=_single(form, "actor", DEFAULT_ACTOR),
            )
            mark_pdf_family_verification_queued(project_id, family_id)
            PDF_VERIFICATION_EXECUTOR.submit(
                _verify_pdf_family_background,
                project_id,
                family_id,
                _single(form, "actor", DEFAULT_ACTOR),
            )
        except ValueError as error:
            self._redirect(
                f"/projects/{project_id}/pdf-groups?error={html_escape(error)}"
                f"#{family_id}"
            )
            return
        self._redirect(
            f"/projects/{project_id}/pdf-groups?saved={family_id}#{family_id}"
        )

    def _save_auxiliary_group_review(
        self,
        route: tuple[str, str],
    ) -> None:
        project_id, group_id = route
        form = self._read_form()
        try:
            decision = save_auxiliary_group_decision(
                project_id=project_id,
                group_id=group_id,
                identity_decision=_single(form, "identity_decision"),
                default_use=_single(form, "default_use"),
                scope=_single(form, "scope", "shared"),
                selected_canonical_url=_single(
                    form,
                    "selected_canonical_url",
                ),
                display_name=_single(form, "display_name"),
                notes=_single(form, "notes"),
                actor=_single(form, "actor", DEFAULT_ACTOR),
            )
        except ValueError as error:
            self._redirect(
                f"/projects/{project_id}/auxiliary-links"
                f"?error={html_escape(error)}#{group_id}"
            )
            return
        applied = len(
            decision.get("materialization", {}).get(
                "applied_appearance_ids",
                [],
            )
        )
        exceptions = len(
            decision.get("materialization", {}).get(
                "preserved_individual_exception_ids",
                [],
            )
        )
        self._redirect(
            f"/projects/{project_id}/auxiliary-links?saved={group_id}"
            f"&applied={applied}&exceptions={exceptions}#{group_id}"
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


def _verify_pdf_family_background(
    project_id: str,
    family_id: str,
    actor: str,
) -> None:
    try:
        verify_pdf_family(project_id, family_id, actor, local_only=False)
    except Exception as error:
        mark_pdf_family_verification_failed(project_id, family_id, error)


def _projects_page(request_path: str = "/") -> str:
    projects = []
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        project_path = project_dir / "project.json"
        if project_path.exists():
            projects.append(load_json(project_path))

    query = parse_qs(urlparse(request_path).query)
    message = ""
    if "deleted" in query:
        message = (
            f'<p class="message ok">Proyecto {html_escape(query["deleted"][0])} '
            'eliminado de la lista activa. Se conserva una copia recuperable.</p>'
        )
    elif "error" in query:
        message = f'<p class="message error">{html_escape(query["error"][0])}</p>'

    heading = f"""
    <section class="panel">
      <div class="card-head">
        <div><p class="eyebrow">Administración</p><h2>Proyectos</h2></div>
        <a class="button" href="/projects/new">Nuevo proyecto</a>
      </div>
      {message}
    </section>
    """
    if not projects:
        body = heading + """
        <section class="panel">
          <h2>No hay proyectos creados</h2>
          <p>Usa <strong>Nuevo proyecto</strong> para comenzar.</p>
        </section>
        """
        return _page("Proyectos", body)

    cards = []
    for project in projects:
        project_id = project.get("project_id", "")
        candidate_links_path = PROJECTS_DIR / project_id / "candidate_links.json"
        candidate_links = (
            load_json(candidate_links_path).get("links", [])
            if candidate_links_path.exists()
            else []
        )
        primary_action = (
            f"""
              <a class="button" href="/projects/{html_escape(project_id)}/review-links">
                Revisar links
              </a>
            """
            if candidate_links
            else f"""
              <form method="post" action="/projects/{html_escape(project_id)}/discover-links">
                <button type="submit">Buscar enlaces</button>
              </form>
            """
        )
        cards.append(
            f"""
            <article class="card">
              <h2>{html_escape(project.get("name"))}</h2>
              <p class="muted">{html_escape(project.get("start_url"))}</p>
              <dl>
                <dt>Estado</dt><dd>{html_escape(project.get("status"))}</dd>
                <dt>Actualizado</dt><dd>{html_escape(project.get("updated_at"))}</dd>
              </dl>
              {primary_action}
              <a class="button secondary" href="/projects/{html_escape(project_id)}/resource-rules">
                Configurar exclusiones
              </a>
              <a class="button secondary" href="/projects/{html_escape(project_id)}/pdf-groups">
                Revisar grupos PDF
              </a>
              <a class="button secondary" href="/projects/{html_escape(project_id)}/auxiliary-links">
                Revisar enlaces auxiliares
              </a>
              <a class="button secondary" href="/projects/{html_escape(project_id)}/resources">
                Revisar casos individuales
              </a>
              <a class="button secondary" href="/projects/{html_escape(project_id)}/effective-state">
                Ver estado efectivo
              </a>
              <a class="button secondary" href="/projects/{html_escape(project_id)}/document-map">
                Ver mapa documental
              </a>
              <a class="button danger" href="/projects/{html_escape(project_id)}/delete">
                Eliminar proyecto
              </a>
            </article>
            """
        )

    return _page("Proyectos", heading + "<section class=\"grid\">" + "".join(cards) + "</section>")


def _new_project_page(request_path: str) -> str:
    query = parse_qs(urlparse(request_path).query)
    message = (
        f'<p class="message error">{html_escape(query["error"][0])}</p>'
        if "error" in query
        else ""
    )
    body = f"""
    <section class="panel">
      <p><a href="/">Volver a proyectos</a></p>
      <p class="eyebrow">Nuevo proyecto</p>
      <h2>Crear un proyecto de trámites</h2>
      <p class="muted">Después de crearlo podrás buscar los enlaces desde la aplicación.</p>
      {message}
    </section>
    <form class="panel" method="post" action="/projects" id="new-project-form">
      <div class="form-grid">
        <label>Nombre
          <input name="name" id="project-name" required placeholder="Ej.: Habilitaciones comerciales">
        </label>
        <label>URL inicial
          <input name="start_url" type="url" required placeholder="https://tramites.montevideo.gub.uy/…">
        </label>
        <label>Identificador
          <input name="project_id" id="project-id" required pattern="[a-z0-9]+(?:_[a-z0-9]+)*" placeholder="habilitaciones_comerciales">
          <small class="muted">Se genera desde el nombre y puede ajustarse antes de crear.</small>
        </label>
        <label>Descripción opcional
          <input name="description" placeholder="Alcance o propósito del proyecto">
        </label>
      </div>
      <div class="actions">
        <button type="submit">Crear proyecto</button>
        <a class="button secondary" href="/">Cancelar</a>
      </div>
    </form>
    <script>
      const nameInput = document.getElementById("project-name");
      const idInput = document.getElementById("project-id");
      let idWasEdited = false;
      idInput.addEventListener("input", () => {{ idWasEdited = true; }});
      nameInput.addEventListener("input", () => {{
        if (idWasEdited) return;
        idInput.value = nameInput.value.normalize("NFD")
          .replace(/[\u0300-\u036f]/g, "")
          .toLowerCase().replace(/[^a-z0-9]+/g, "_")
          .replace(/^_+|_+$/g, "");
      }});
    </script>
    """
    return _page("Nuevo proyecto", body)


def _delete_project_page(project_id: str, request_path: str) -> str:
    project_path = PROJECTS_DIR / project_id / "project.json"
    if not project_path.exists():
        return _page("Proyecto inexistente", '<p><a href="/">Volver a proyectos</a></p><p>El proyecto no existe.</p>')
    project = load_json(project_path)
    query = parse_qs(urlparse(request_path).query)
    message = (
        f'<p class="message error">{html_escape(query["error"][0])}</p>'
        if "error" in query
        else ""
    )
    body = f"""
    <section class="panel">
      <p><a href="/">Volver a proyectos</a></p>
      <p class="eyebrow">Eliminar proyecto</p>
      <h2>{html_escape(project.get('name'))}</h2>
      <p>El proyecto desaparecerá de la lista activa. Sus datos y salidas se conservarán en el área recuperable.</p>
      {message}
    </section>
    <form class="panel" method="post" action="/projects/{html_escape(project_id)}/delete">
      <label>Escribe <strong>{html_escape(project_id)}</strong> para confirmar
        <input name="confirmation" required autocomplete="off">
      </label>
      <div class="actions">
        <button class="danger" type="submit">Eliminar proyecto</button>
        <a class="button secondary" href="/">Cancelar</a>
      </div>
    </form>
    """
    return _page(f"Eliminar - {project.get('name')}", body)


def _resource_rules_page(project_id: str, request_path: str) -> str:
    project_dir = PROJECTS_DIR / project_id
    project = load_json(project_dir / "project.json")
    payload = load_or_create_resource_filter_rules(project_id)
    rows = "".join(
        f"""
        <div class="resource-row">
          <label class="checkbox">
            <input type="checkbox" name="enabled_rule" value="{html_escape(rule.get('rule_id'))}" {'checked' if rule.get('enabled', True) else ''}>
            <strong>{html_escape(rule.get('pattern'))}</strong>
          </label>
          <p class="muted">{html_escape(rule.get('match_type'))} · {html_escape(rule.get('reason'))}</p>
        </div>
        """
        for rule in payload.get("rules", [])
    )
    message = (
        '<p class="message ok">Reglas guardadas. Regenera los recursos y los agrupamientos para aplicarlas.</p>'
        if "saved=1" in request_path
        else ""
    )
    body = f"""
    <section class="panel">
      <p><a href="/">Volver a proyectos</a></p>
      <p class="eyebrow">Paso 2 de 5</p>
      <h2>Configurar exclusiones · {html_escape(project.get('name'))}</h2>
      <p class="muted">
        Estas reglas se aplican después del descubrimiento y antes de formar
        grupos. Los enlaces excluidos conservan la regla y el motivo en
        <code>node_resources.json</code>.
      </p>
      {message}
    </section>
    <form class="panel" method="post" action="/projects/{html_escape(project_id)}/resource-rules">
      <h3>Reglas existentes</h3>
      <div class="resource-list">{rows}</div>
      <h3>Agregar una regla del proyecto</h3>
      <div class="form-grid">
        <label>Característica
          <select name="match_type">
            <option value="url_contains">La URL contiene</option>
            <option value="text_contains">El texto o contexto contiene</option>
          </select>
        </label>
        <label>Patrón
          <input name="pattern" placeholder="Ejemplo: /contenido-no-relevante/">
        </label>
        <label>Motivo
          <input name="reason" placeholder="Por qué no se considera">
        </label>
      </div>
      <div class="actions">
        <button type="submit">Guardar configuración</button>
        <a class="button secondary" href="/projects/{html_escape(project_id)}/pdf-groups">Continuar a grupos PDF</a>
      </div>
    </form>
    """
    return _page(f"Exclusiones - {project.get('name')}", body)


def _effective_state_page(project_id: str, request_path: str) -> str:
    project_dir = PROJECTS_DIR / project_id
    project = load_json(project_dir / "project.json")
    state = resolve_effective_project_state(project_id)
    summary = state["summary"]
    confirmed_resources = sum(
        not item.get("canonical_resource_key", "").startswith("appearance:")
        for item in state["canonical_resources"]
    )
    provisional_resources = summary["canonical_resource_count"] - confirmed_resources
    query = parse_qs(urlparse(request_path).query)
    message = ""
    if "saved" in query:
        message = (
            f'<p class="message ok">Estado actualizado para '
            f'{html_escape(query["saved"][0])}. El trabajo anterior se conserva.</p>'
        )
    elif "error" in query:
        message = f'<p class="message error">{html_escape(query["error"][0])}</p>'

    cards = []
    relations_by_node: dict[str, int] = {}
    for relation in state["relations"]:
        link_id = relation.get("source_link_id")
        relations_by_node[link_id] = relations_by_node.get(link_id, 0) + 1
    for node in state["nodes"]:
        if not node.get("participates_in_model"):
            continue
        link_id = node.get("link_id", "")
        active = node.get("is_active")
        impact = node_lifecycle_impact(state, link_id)
        next_status = "inactive" if active else "active"
        action_label = "Desactivar del modelo" if active else "Reactivar en el modelo"
        status_label = "Activo" if active else "Inactivo"
        status_class = "ok" if active else "error"
        if active:
            impact_text = (
                f"Al desactivar: {impact['relation_count']} relaciones quedarán inactivas; "
                f"{impact['orphaned_resource_count']} recursos quedarán huérfanos; "
                f"{impact['still_used_resource_count']} seguirán usados por otros nodos."
            )
            confirmation = "¿Desactivar este nodo? No se borrará el trabajo realizado."
        else:
            relation_count = relations_by_node.get(link_id, 0)
            impact_text = (
                f"Al reactivar se recuperarán {relation_count} relaciones descubiertas "
                "y sus decisiones previas, sin repetir el descubrimiento."
            )
            confirmation = "¿Reactivar este nodo y recuperar sus relaciones anteriores?"
        search = " ".join(
            str(value or "")
            for value in [link_id, node.get("title"), node.get("url"), status_label]
        ).lower()
        cards.append(
            f"""
            <article class="card lifecycle-card" id="{html_escape(link_id)}"
                data-status="{'active' if active else 'inactive'}"
                data-search="{html_escape(search)}">
              <div class="card-head">
                <div>
                  <p class="eyebrow">{html_escape(link_id)} · {html_escape(node.get('primary_role'))}</p>
                  <h2>{html_escape(node.get('title'))}</h2>
                  <a class="url" href="{html_escape(node.get('url'))}" target="_blank" rel="noreferrer">
                    {html_escape(node.get('url'))}
                  </a>
                </div>
                <span class="pill {status_class}">{status_label}</span>
              </div>
              <p><strong>Impacto previsto:</strong> {html_escape(impact_text)}</p>
              <form method="post"
                  action="/projects/{html_escape(project_id)}/effective-state/{html_escape(link_id)}"
                  onsubmit="return confirm('{html_escape(confirmation)}')">
                <input type="hidden" name="status" value="{next_status}">
                <label>Motivo o nota
                  <input name="notes" placeholder="Opcional; queda registrado en el historial">
                </label>
                <div class="actions">
                  <button type="submit">{action_label}</button>
                </div>
              </form>
            </article>
            """
        )

    body = f"""
    <section class="panel">
      <p><a href="/">Volver a proyectos</a> |
        <a href="/projects/{html_escape(project_id)}/resources">Revisar casos individuales</a></p>
      <p class="eyebrow">Estado consolidado</p>
      <h2>Estado efectivo · {html_escape(project.get('name'))}</h2>
      <p class="muted">Esta vista se calcula desde la evidencia y las decisiones persistidas. Activar o desactivar no borra descubrimiento, grupos ni revisiones.</p>
      <div class="stats">
        <div><strong>{summary['active_node_count']}</strong><span>Nodos activos</span></div>
        <div><strong>{summary['active_relation_count']}</strong><span>Relaciones activas</span></div>
        <div><strong>{confirmed_resources}</strong><span>Recursos consolidados</span></div>
        <div><strong>{provisional_resources}</strong><span>Identidades provisionales</span></div>
        <div><strong>{summary['orphaned_resource_count']}</strong><span>Recursos huérfanos</span></div>
        <div><strong>{summary['inconsistency_count']}</strong><span>Inconsistencias</span></div>
      </div>
      {message}
    </section>
    <section class="toolbar">
      <input id="lifecycleSearch" type="search" placeholder="Buscar nodo">
      <select id="lifecycleStatus">
        <option value="">Todos</option>
        <option value="active">Activos</option>
        <option value="inactive">Inactivos</option>
      </select>
      <button type="button" onclick="clearLifecycleFilters()">Limpiar</button>
    </section>
    <section class="cards">{''.join(cards)}</section>
    <script>
      const lifecycleSearch = document.getElementById('lifecycleSearch');
      const lifecycleStatus = document.getElementById('lifecycleStatus');
      lifecycleSearch.addEventListener('input', applyLifecycleFilters);
      lifecycleStatus.addEventListener('change', applyLifecycleFilters);
      function applyLifecycleFilters() {{
        const query = lifecycleSearch.value.trim().toLowerCase();
        const status = lifecycleStatus.value;
        document.querySelectorAll('.lifecycle-card').forEach(card => {{
          const visible = (!query || card.dataset.search.includes(query)) &&
            (!status || card.dataset.status === status);
          card.classList.toggle('hidden', !visible);
        }});
      }}
      function clearLifecycleFilters() {{
        lifecycleSearch.value = '';
        lifecycleStatus.value = '';
        applyLifecycleFilters();
      }}
    </script>
    """
    return _page(f"Estado efectivo - {project.get('name')}", body)


def _legacy_document_map_page(project_id: str) -> str:
    project_dir = PROJECTS_DIR / project_id
    project = load_json(project_dir / "project.json")
    document_map = build_document_map(resolve_effective_project_state(project_id))
    payload = json.dumps(document_map, ensure_ascii=False).replace("</", "<\\/")
    body = f"""
    <style>
      .map-head {{ display: flex; justify-content: space-between; gap: 18px; align-items: flex-start; }}
      .map-tabs {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; }}
      .map-tabs button[aria-selected="false"] {{ color: var(--accent); background: #fff; }}
      .map-view[hidden] {{ display: none; }}
      .node-map {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }}
      .map-node {{ min-height: 125px; text-align: left; color: var(--text); background: var(--panel); border-color: var(--border); }}
      .map-node:hover, .map-node:focus-visible {{ border-color: var(--accent); }}
      .map-node strong {{ display: block; margin-bottom: 9px; line-height: 1.25; }}
      .map-node .pill {{ display: inline-block; margin: 2px 3px 2px 0; white-space: normal; }}
      .map-node.inactive-node {{ border-style: dashed; opacity: .75; }}
      .audit-layout {{ display: grid; grid-template-columns: 280px minmax(0, 1fr); gap: 16px; }}
      .terminal-summary {{ align-self: start; color: #fff; background: var(--accent); border-radius: 8px; padding: 16px; }}
      .terminal-summary h2 {{ margin-bottom: 8px; }}
      .terminal-summary p {{ color: #dcecff; }}
      .terminal-summary a {{ color: #fff; }}
      .resource-groups {{ display: grid; gap: 12px; }}
      .resource-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }}
      .map-resource {{ min-height: 105px; text-align: left; color: var(--text); background: #fbfcfe; border: 1px solid var(--border); border-radius: 6px; padding: 10px; }}
      button.map-resource {{ cursor: pointer; }}
      button.map-resource:hover, button.map-resource:focus-visible {{ border-color: var(--accent); background: #f5f9ff; }}
      .map-resource strong {{ display: block; margin-bottom: 6px; }}
      .map-resource p {{ margin: 5px 0; }}
      .coverage-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
      .coverage-list {{ display: grid; gap: 8px; }}
      .coverage-item {{ padding: 10px; border: 1px solid var(--border); border-radius: 6px; background: #fbfcfe; }}
      .coverage-item.inactive {{ border-style: dashed; background: #fff7ed; }}
      .source-list {{ margin: 8px 0 0; padding-left: 20px; }}
      .empty-state {{ padding: 12px; color: var(--muted); background: #f8fafc; border-radius: 6px; }}
      @media (max-width: 900px) {{
        .node-map, .resource-grid, .coverage-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
        .audit-layout {{ grid-template-columns: 1fr; }}
      }}
      @media (max-width: 650px) {{
        .map-head, .node-map, .resource-grid, .coverage-grid {{ display: grid; grid-template-columns: 1fr; }}
      }}
    </style>
    <section class="panel">
      <p><a href="/">Volver a proyectos</a> · <a href="/projects/{html_escape(project_id)}/effective-state">Ver estado efectivo</a></p>
      <div class="map-head">
        <div>
          <p class="eyebrow">Vista documental de solo lectura</p>
          <h2>{html_escape(project.get('name'))}</h2>
          <p class="muted">Orienta por los nodos terminales y permite auditar recursos y cobertura sin modificar decisiones.</p>
        </div>
        <span class="pill">Estado efectivo · datos vigentes</span>
      </div>
      <div class="stats">
        <div><strong>{document_map['summary']['terminal_node_count']}</strong><span>Nodos terminales</span></div>
        <div><strong>{document_map['summary']['resource_count']}</strong><span>Recursos efectivos</span></div>
        <div><strong>{document_map['summary']['shared_resource_count']}</strong><span>Recursos compartidos</span></div>
        <div><strong>{document_map['summary']['active_terminal_node_count']}</strong><span>Nodos activos</span></div>
      </div>
      <div class="map-tabs">
        <button type="button" data-map-view="overview" aria-selected="true">Mapa general</button>
        <button type="button" data-map-view="node" aria-selected="false">Auditoría del trámite</button>
        <button type="button" data-map-view="resource" aria-selected="false">Cobertura del recurso</button>
      </div>
    </section>

    <section class="map-view" id="map-overview-view">
      <section class="toolbar">
        <input id="map-search" type="search" placeholder="Buscar un nodo terminal">
        <select id="map-alert-filter">
          <option value="">Todos los nodos</option>
          <option value="attention">Solo con pendientes o provisionales</option>
          <option value="shared">Solo con recursos compartidos</option>
          <option value="inactive">Solo inactivos</option>
        </select>
      </section>
      <section class="node-map" id="document-node-map"></section>
    </section>

    <section class="map-view" id="map-node-view" hidden>
      <section class="audit-layout" id="node-audit"></section>
    </section>

    <section class="map-view" id="map-resource-view" hidden>
      <section id="resource-coverage"></section>
    </section>

    <script>
      const documentMap = {payload};
      const useLabels = {{
        process_as_context: "Contexto",
        show_as_link: "Solo link",
        discard: "Descartado",
        review_later: "Revisar después"
      }};
      const typeLabels = {{
        pdf: "PDF", formulario: "Formulario", agenda: "Agenda",
        normativa: "Normativa", link: "Link", tramite_relacionado: "Trámite relacionado"
      }};
      let selectedNodeId = documentMap.nodes[0]?.link_id || null;
      let selectedResourceKey = null;

      function escapeHtml(value) {{
        return String(value ?? "").replace(/[&<>\"']/g, character => ({{
          "&": "&amp;", "<": "&lt;", ">": "&gt;", '\"': "&quot;", "'": "&#039;"
        }})[character]);
      }}

      function showMapView(viewName) {{
        document.querySelectorAll(".map-view").forEach(view => {{
          view.hidden = view.id !== `map-${{viewName}}-view`;
        }});
        document.querySelectorAll("[data-map-view]").forEach(button => {{
          button.setAttribute("aria-selected", String(button.dataset.mapView === viewName));
        }});
      }}

      function renderOverview() {{
        const host = document.getElementById("document-node-map");
        host.innerHTML = documentMap.nodes.map(node => {{
          const summary = node.summary;
          const attention = summary.pending_count + summary.provisional_count;
          return `<button type="button" class="map-node ${{node.is_active ? "" : "inactive-node"}}"
              data-node-id="${{escapeHtml(node.link_id)}}"
              data-search="${{escapeHtml(node.title.toLowerCase())}}"
              data-attention="${{attention}}" data-shared="${{summary.shared_count}}"
              data-active="${{node.is_active}}">
            <strong>${{escapeHtml(node.title)}}</strong>
            <span class="pill">Contexto ${{summary.context_count}}</span>
            <span class="pill">Links ${{summary.link_count}}</span>
            <span class="pill">Compartidos ${{summary.shared_count}}</span>
            <span class="pill">Provisionales ${{summary.provisional_count}}</span>
            ${{summary.discarded_count ? `<span class="pill inactive">Descartados ${{summary.discarded_count}}</span>` : ""}}
          </button>`;
        }}).join("");
        host.querySelectorAll(".map-node").forEach(button => {{
          button.addEventListener("click", () => openNode(button.dataset.nodeId));
        }});
        applyMapFilters();
      }}

      function applyMapFilters() {{
        const query = document.getElementById("map-search").value.trim().toLowerCase();
        const filter = document.getElementById("map-alert-filter").value;
        document.querySelectorAll(".map-node").forEach(node => {{
          const matchesSearch = !query || node.dataset.search.includes(query);
          const matchesFilter = !filter
            || (filter === "attention" && Number(node.dataset.attention) > 0)
            || (filter === "shared" && Number(node.dataset.shared) > 0)
            || (filter === "inactive" && node.dataset.active === "false");
          node.classList.toggle("hidden", !(matchesSearch && matchesFilter));
        }});
      }}

      function openNode(nodeId) {{
        selectedNodeId = nodeId;
        const node = documentMap.nodes.find(item => item.link_id === nodeId);
        if (!node) return;
        const activeResources = node.resources.filter(item => item.relation_status === "active");
        const groups = [
          ["Contexto autorizado", activeResources.filter(item => item.effective_use === "process_as_context")],
          ["Links para mostrar", activeResources.filter(item => item.effective_use === "show_as_link")],
          ["Pendientes", activeResources.filter(item => !item.effective_use || item.effective_use === "review_later")],
          ["Descartados", activeResources.filter(item => item.effective_use === "discard")],
          ["Relaciones inactivas", node.resources.filter(item => item.relation_status === "inactive")]
        ];
        document.getElementById("node-audit").innerHTML = `
          <aside class="terminal-summary">
            <p class="eyebrow">${{escapeHtml(node.link_id)}}</p>
            <h2>${{escapeHtml(node.title)}}</h2>
            <p>${{node.is_active ? "Nodo terminal activo" : "Nodo terminal inactivo"}}</p>
            <p>${{node.summary.resource_count}} recursos · ${{node.summary.shared_count}} compartidos</p>
            <a href="${{escapeHtml(node.url)}}" target="_blank" rel="noreferrer">Abrir fuente oficial</a>
          </aside>
          <div class="resource-groups">
            ${{groups.filter(([, items]) => items.length).map(([label, items]) => resourceGroup(label, items)).join("") || '<p class="empty-state">No hay recursos asociados.</p>'}}
          </div>`;
        document.querySelectorAll("[data-resource-key]").forEach(button => {{
          button.addEventListener("click", () => openResource(button.dataset.resourceKey));
        }});
        showMapView("node");
      }}

      function resourceGroup(label, resources) {{
        return `<section class="panel"><h3>${{escapeHtml(label)}} · ${{resources.length}}</h3>
          <div class="resource-grid">${{resources.map(resourceCard).join("")}}</div></section>`;
      }}

      function resourceCard(resource) {{
        const shared = resource.active_source_nodes.length > 1;
        const buttonTag = resource.is_consolidated || shared ? "button" : "div";
        const attributes = buttonTag === "button"
          ? `type="button" data-resource-key="${{escapeHtml(resource.canonical_resource_key)}}"`
          : "";
        return `<${{buttonTag}} class="map-resource" ${{attributes}}>
          <strong>${{escapeHtml(resource.display_name)}}</strong>
          <span class="pill">${{escapeHtml(typeLabels[resource.resource_type] || resource.resource_type)}}</span>
          <span class="pill">${{resource.is_consolidated ? "Consolidado" : "Provisional"}}</span>
          ${{shared ? `<span class="pill">Compartido por ${{resource.active_source_nodes.length}}</span>` : ""}}
          <p class="muted">${{escapeHtml(useLabels[resource.effective_use] || "Sin decisión")}} · ${{resource.appearance_count}} apariciones</p>
          ${{buttonTag === "button" ? '<small>Seleccionar para auditar cobertura</small>' : ""}}
        </${{buttonTag}}>`;
      }}

      function openResource(resourceKey) {{
        selectedResourceKey = resourceKey;
        const resource = documentMap.resources[resourceKey];
        if (!resource) return;
        document.getElementById("resource-coverage").innerHTML = `
          <section class="panel">
            <p><button class="button secondary" type="button" id="back-to-node">Volver al trámite</button></p>
            <p class="eyebrow">${{resource.is_consolidated ? "Recurso canónico" : "Identidad provisional"}}</p>
            <h2>${{escapeHtml(resource.display_name)}}</h2>
            <p class="muted">${{escapeHtml(useLabels[resource.effective_use] || "Sin decisión")}} · ${{resource.appearance_count}} apariciones</p>
            ${{resource.canonical_url ? `<p><a href="${{escapeHtml(resource.canonical_url)}}" target="_blank" rel="noreferrer">Abrir recurso canónico</a></p>` : ""}}
          </section>
          <div class="coverage-grid">
            <section class="panel"><h3>Trámites vinculados actualmente · ${{resource.active_source_nodes.length}}</h3>
              <div class="coverage-list">${{coverageItems(resource.active_source_nodes, false)}}</div></section>
            <section class="panel"><h3>Relaciones inactivas · ${{resource.inactive_source_nodes.length}}</h3>
              <div class="coverage-list">${{coverageItems(resource.inactive_source_nodes, true)}}</div></section>
          </div>
          <section class="panel"><h3>Apariciones que sustentan el recurso · ${{resource.appearance_sources.length}}</h3>
            <ul class="source-list">${{resource.appearance_sources.map(item => `<li>${{escapeHtml(item.title || item.url || item.appearance_id)}} · ${{escapeHtml(item.source_link_id)}}</li>`).join("")}}</ul>
          </section>`;
        document.getElementById("back-to-node").addEventListener("click", () => openNode(selectedNodeId));
        showMapView("resource");
      }}

      function coverageItems(nodes, inactive) {{
        if (!nodes.length) return '<p class="empty-state">No hay relaciones en este estado.</p>';
        return nodes.map(node => `<button type="button" class="coverage-item ${{inactive ? "inactive" : ""}}" data-coverage-node="${{escapeHtml(node.link_id)}}">
          <strong>${{inactive ? "○" : "✓"}} ${{escapeHtml(node.title)}}</strong>
        </button>`).join("");
      }}

      document.querySelectorAll("[data-map-view]").forEach(button => {{
        button.addEventListener("click", () => {{
          if (button.dataset.mapView === "node" && selectedNodeId) openNode(selectedNodeId);
          else if (button.dataset.mapView === "resource" && selectedResourceKey) openResource(selectedResourceKey);
          else showMapView(button.dataset.mapView);
        }});
      }});
      document.getElementById("map-search").addEventListener("input", applyMapFilters);
      document.getElementById("map-alert-filter").addEventListener("change", applyMapFilters);
      document.addEventListener("click", event => {{
        const button = event.target.closest("[data-coverage-node]");
        if (button) openNode(button.dataset.coverageNode);
      }});
      renderOverview();
    </script>
    """
    return _page(f"Mapa documental - {project.get('name')}", body)


def _document_map_page(project_id: str) -> str:
    project_dir = PROJECTS_DIR / project_id
    project = load_json(project_dir / "project.json")
    document_map = build_document_map(resolve_effective_project_state(project_id))
    body = render_document_map_body(project, document_map)
    return _page(f"Mapa documental - {project.get('name')}", body)


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
    pdf_analysis_path = project_dir / "pdf_analysis.json"
    pdf_analysis = (
        load_json(pdf_analysis_path)
        if pdf_analysis_path.exists()
        else {"appearances": [], "proposed_groups": []}
    )
    pdf_families = pdf_analysis.get("proposed_groups", [])
    pdf_family_by_appearance = {
        appearance_id: family
        for family in pdf_families
        for appearance_id in family.get("appearance_ids", [])
    }
    identity_review_path = project_dir / "resource_identity_review.json"
    identity_review = (
        load_json(identity_review_path)
        if identity_review_path.exists()
        else {"decisions": []}
    )
    identity_by_appearance = {
        item.get("appearance_id"): item
        for item in identity_review.get("decisions", [])
    }
    effective_state = resolve_effective_project_state(project_id, PROJECTS_DIR)
    active_nodes = {
        item.get("link_id"): item.get("is_active", False)
        for item in effective_state.get("nodes", [])
    }
    pages = node_resources.get("pages", [])
    total_resources = node_resources.get("resources_count", 0)
    total_discarded = node_resources.get("discarded_resources_count", 0)
    reviewable_ids = {
        f"{page.get('link_id')}::{resource.get('resource_id')}"
        for page in pages
        for resource in page.get("resources", [])
    }
    reviewed_resources = sum(
        decision_id in reviewable_ids
        for decision_id in decisions_by_resource
    )
    inherited_resources = sum(
        decision_id in reviewable_ids
        and decision.get("decision_source") in {"auxiliary_group", "pdf_group"}
        for decision_id, decision in decisions_by_resource.items()
    )
    individual_resources = reviewed_resources - inherited_resources
    pending_resources = max(0, total_resources - reviewed_resources)
    message = _status_message(request_path)

    cards = "".join(
        _resource_page_card(
            project_id,
            page,
            decisions_by_resource,
            pdf_families,
            pdf_family_by_appearance,
            identity_by_appearance,
            active_nodes.get(page.get("link_id"), True),
        )
        for page in pages
    )
    body = f"""
    <section class="panel">
      <p>
        <a href="/">Volver a proyectos</a> |
        <a href="/projects/{html_escape(project_id)}/review-links">Revisar links principales</a>
      </p>
      <h2>{html_escape(project.get("name"))}</h2>
      <p class="eyebrow">Paso 5 de 5 · revisión final</p>
      <p class="muted">Solo corresponde ajustar pendientes, recursos no agrupados y excepciones individuales.</p>
      <div class="stats">
        <div><strong>{html_escape(node_resources.get("accepted_links_count"))}</strong><span>Nodos explorados</span></div>
        <div><strong>{html_escape(total_resources)}</strong><span>Recursos utiles</span></div>
        <div><strong>{html_escape(total_discarded)}</strong><span>Descartados por regla</span></div>
        <div><strong>{html_escape(pending_resources)}</strong><span>Pendientes</span></div>
        <div><strong>{html_escape(inherited_resources)}</strong><span>Decisiones de grupo</span></div>
        <div><strong>{html_escape(individual_resources)}</strong><span>Decisiones individuales</span></div>
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
      <select id="decisionFilter">
        <option value="">Todos los estados</option>
        <option value="pending">Pendientes</option>
        <option value="group">Decisión heredada de grupo</option>
        <option value="individual">Decisión individual</option>
      </select>
      <button type="button" onclick="clearResourceFilters()">Limpiar</button>
    </section>
    <section class="cards">
      {cards}
    </section>
    <p id="resourceNoResults" class="panel muted hidden">
      No hay recursos que coincidan con los filtros seleccionados.
    </p>
    <script>
      const search = document.getElementById("search");
      const typeFilter = document.getElementById("typeFilter");
      const discardFilter = document.getElementById("discardFilter");
      const decisionFilter = document.getElementById("decisionFilter");
      const resourceNoResults = document.getElementById("resourceNoResults");
      const initialFilters = new URLSearchParams(window.location.search);
      search.value = initialFilters.get("search_filter") || "";
      typeFilter.value = initialFilters.get("type_filter") || "";
      discardFilter.value = initialFilters.get("discard_filter") || "";
      decisionFilter.value = initialFilters.get("decision_filter") || "";
      const restoredScrollY = Number(initialFilters.get("scroll_y") || 0);
      search.addEventListener("input", applyResourceFilters);
      typeFilter.addEventListener("change", applyResourceFilters);
      discardFilter.addEventListener("change", applyResourceFilters);
      decisionFilter.addEventListener("change", applyResourceFilters);

      function applyResourceFilters() {{
        const query = search.value.trim().toLowerCase();
        const type = typeFilter.value;
        const discardState = discardFilter.value;
        const decisionState = decisionFilter.value;
        document.querySelectorAll(".resource-row").forEach(row => {{
          const matchesText = !query || row.dataset.search.includes(query);
          const matchesType = !type || row.dataset.type === type;
          const matchesDiscard = !discardState || row.dataset.discard === discardState;
          const matchesDecision = !decisionState || row.dataset.decision === decisionState;
          row.classList.toggle("hidden", !(matchesText && matchesType && matchesDiscard && matchesDecision));
        }});
        let visibleCards = 0;
        document.querySelectorAll(".cards > .card").forEach(card => {{
          const hasVisibleResource = Boolean(
            card.querySelector(".resource-row:not(.hidden)")
          );
          card.classList.toggle("hidden", !hasVisibleResource);
          if (hasVisibleResource) visibleCards += 1;
        }});
        resourceNoResults.classList.toggle("hidden", visibleCards > 0);
        persistResourceFilters();
      }}

      function persistResourceFilters() {{
        const url = new URL(window.location.href);
        const values = {{
          search_filter: search.value.trim(),
          type_filter: typeFilter.value,
          discard_filter: discardFilter.value,
          decision_filter: decisionFilter.value,
        }};
        Object.entries(values).forEach(([key, value]) => {{
          if (value) url.searchParams.set(key, value);
          else url.searchParams.delete(key);
        }});
        window.history.replaceState(null, "", url);
      }}

      document.querySelectorAll(".resource-review-form, .resource-identity-form").forEach(form => {{
        form.addEventListener("submit", () => {{
          form.elements.search_filter.value = search.value.trim();
          form.elements.type_filter.value = typeFilter.value;
          form.elements.discard_filter.value = discardFilter.value;
          form.elements.decision_filter.value = decisionFilter.value;
          form.elements.scroll_y.value = String(Math.round(window.scrollY));
        }});
      }});

      function clearResourceFilters() {{
        search.value = "";
        typeFilter.value = "";
        discardFilter.value = "";
        decisionFilter.value = "";
        applyResourceFilters();
      }}
      applyResourceFilters();
      const savedIdentity = initialFilters.get("saved_identity");
      if (savedIdentity) {{
        const savedRow = document.getElementById(savedIdentity);
        const identityDetails = savedRow && savedRow.querySelector(".identity-resolution");
        if (identityDetails) identityDetails.open = true;
      }}
      if (restoredScrollY > 0) {{
        window.requestAnimationFrame(() => window.scrollTo(0, restoredScrollY));
      }}
    </script>
    """
    return _page(f"Recursos internos - {project.get('name')}", body)


def _auxiliary_links_page(project_id: str, request_path: str) -> str:
    project_dir = PROJECTS_DIR / project_id
    project = load_json(project_dir / "project.json")
    analysis_path = project_dir / "auxiliary_link_analysis.json"
    if not analysis_path.exists():
        body = f"""
        <section class="panel">
          <p><a href="/">Volver a proyectos</a></p>
          <h2>{html_escape(project.get("name"))}</h2>
          <p>No existe <code>auxiliary_link_analysis.json</code>.</p>
          <p class="muted">Ejecuta <code>python app.py analyze-auxiliary-links --project-id {html_escape(project_id)}</code>.</p>
        </section>
        """
        return _page("Enlaces auxiliares", body)

    analysis = load_json(analysis_path)
    group_review_path = project_dir / "auxiliary_link_group_review.json"
    group_review = (
        load_json(group_review_path)
        if group_review_path.exists()
        else {"review_status": "not_started", "decisions": []}
    )
    decisions = {
        item.get("group_id"): item
        for item in group_review.get("decisions", [])
    }
    appearances = {
        item.get("appearance_id"): item
        for item in analysis.get("appearances", [])
    }
    summary = analysis.get("summary", {})
    agenda_groups = analysis.get("agenda_candidates", [])
    normalized_groups = analysis.get(
        "normalized_equivalence_candidates",
        [],
    )
    exact_groups = analysis.get("exact_url_groups", [])
    normalized_non_agenda = [
        group
        for group in normalized_groups
        if group.get("suggested_functional_kind") != "agenda"
    ]
    covered_by_normalized = {
        appearance_id
        for group in normalized_non_agenda
        for appearance_id in group.get("appearance_ids", [])
    }
    cards = "".join(
        _auxiliary_group_card(
            project_id,
            group,
            appearances,
            "agenda",
            decisions.get(group.get("group_id"), {}),
        )
        for group in agenda_groups
    )
    cards += "".join(
        _auxiliary_group_card(
            project_id,
            group,
            appearances,
            "normalized",
            decisions.get(group.get("group_id"), {}),
        )
        for group in normalized_non_agenda
    )
    cards += "".join(
        _auxiliary_group_card(
            project_id,
            group,
            appearances,
            "exact",
            decisions.get(group.get("group_id"), {}),
        )
        for group in exact_groups
        if group.get("suggested_functional_kind") != "agenda"
        and not (
            set(group.get("appearance_ids", []))
            & covered_by_normalized
        )
    )

    body = f"""
    <section class="panel">
      <p>
        <a href="/">Volver a proyectos</a> |
        <a href="/projects/{html_escape(project_id)}/resource-rules">Configurar exclusiones</a> |
        <a href="/projects/{html_escape(project_id)}/resources">Revisar casos individuales</a> |
        <a href="/projects/{html_escape(project_id)}/pdf-groups">Revisar PDF</a>
      </p>
      <p class="eyebrow">Paso 4 de 5 · grupos de enlaces</p>
      <h2>{html_escape(project.get("name"))}</h2>
      <p class="muted">
        Confirma el tratamiento una vez por grupo. La decisión se registra y se
        aplica a las apariciones sin decisión individual.
      </p>
      <div class="stats">
        <div><strong>{html_escape(summary.get("appearance_count", 0))}</strong><span>Apariciones no documentales</span></div>
        <div><strong>{html_escape(summary.get("exact_url_group_count", 0))}</strong><span>Grupos por URL exacta</span></div>
        <div><strong>{html_escape(summary.get("normalized_equivalence_candidate_count", 0))}</strong><span>Equivalencias fuertes</span></div>
        <div><strong>{html_escape(summary.get("agenda_candidate_count", 0))}</strong><span>Agendas candidatas</span></div>
      </div>
      {_auxiliary_status_message(request_path)}
    </section>
    <section class="toolbar">
      <input id="auxSearch" type="search" placeholder="Buscar agenda, recurso, nodo o URL">
      <select id="auxKind">
        <option value="">Todos los grupos</option>
        <option value="agenda">Agendas</option>
        <option value="normalized">Equivalencias normalizadas</option>
        <option value="exact">URLs exactas</option>
      </select>
      <button type="button" onclick="clearAuxFilters()">Limpiar</button>
    </section>
    <section class="cards">{cards}</section>
    <script>
      const auxSearch = document.getElementById("auxSearch");
      const auxKind = document.getElementById("auxKind");
      auxSearch.addEventListener("input", applyAuxFilters);
      auxKind.addEventListener("change", applyAuxFilters);

      function applyAuxFilters() {{
        const query = auxSearch.value.trim().toLowerCase();
        const kind = auxKind.value;
        document.querySelectorAll(".aux-group").forEach(card => {{
          const matchesText = !query || card.dataset.search.includes(query);
          const matchesKind = !kind || card.dataset.kind === kind;
          card.classList.toggle("hidden", !(matchesText && matchesKind));
        }});
      }}

      function clearAuxFilters() {{
        auxSearch.value = "";
        auxKind.value = "";
        applyAuxFilters();
      }}
    </script>
    """
    return _page(f"Enlaces auxiliares - {project.get('name')}", body)


def _auxiliary_group_card(
    project_id: str,
    group: dict[str, Any],
    appearances: dict[str, dict[str, Any]],
    section_kind: str,
    decision: dict[str, Any],
) -> str:
    items = [
        appearances[appearance_id]
        for appearance_id in group.get("appearance_ids", [])
        if appearance_id in appearances
    ]
    evidence = group.get("evidence", {})
    title = _auxiliary_group_title(group, items)
    search_text = " ".join(
        str(value or "")
        for value in [
            group.get("group_id"),
            title,
            evidence.get("value"),
            *group.get("source_node_ids", []),
            *group.get("detected_urls", []),
        ]
    ).lower()
    rows = "".join(_auxiliary_appearance_row(item) for item in items)
    review_form = _auxiliary_group_review_form(
        project_id,
        group,
        items,
        title,
        decision,
    )
    materialization = decision.get("materialization", {})
    decision_summary = ""
    if decision:
        decision_summary = f"""
        <p class="message ok">
          Decisión guardada: {html_escape(decision.get("identity_decision"))} /
          {html_escape(decision.get("default_use"))}.
          Aplicada a {len(materialization.get("applied_appearance_ids", []))}
          apariciones; {len(materialization.get("preserved_individual_exception_ids", []))}
          excepciones individuales conservadas.
        </p>
        """
    return f"""
    <article class="card aux-group"
        id="{html_escape(group.get("group_id"))}"
        data-kind="{html_escape(section_kind)}"
        data-search="{html_escape(search_text)}">
      <div class="card-head">
        <div>
          <p class="eyebrow">{html_escape(group.get("group_id"))}</p>
          <h2>{html_escape(title)}</h2>
          <p class="muted">{html_escape(_auxiliary_section_label(section_kind))}</p>
        </div>
        <span class="pill">{html_escape(_auxiliary_certainty_label(group.get("certainty")))}</span>
      </div>
      <dl>
        <dt>Apariciones</dt><dd>{html_escape(evidence.get("appearance_count", len(items)))}</dd>
        <dt>Nodos de origen</dt><dd>{html_escape(", ".join(group.get("source_node_ids", [])))}</dd>
        <dt>Clave candidata</dt><dd class="url">{html_escape(evidence.get("value"))}</dd>
        <dt>Usos existentes</dt><dd>{html_escape(", ".join(group.get("existing_uses", [])) or "Sin decisión")}</dd>
      </dl>
      {decision_summary}
      {review_form}
      <details {"open" if section_kind == "agenda" else ""}>
        <summary>Ver apariciones y evidencia</summary>
        <div class="resource-list">{rows}</div>
      </details>
    </article>
    """


def _auxiliary_group_review_form(
    project_id: str,
    group: dict[str, Any],
    items: list[dict[str, Any]],
    suggested_title: str,
    decision: dict[str, Any],
) -> str:
    canonical_urls = list(
        dict.fromkeys(
            item.get("candidate_canonical_url")
            or item.get("detected_url")
            for item in items
            if item.get("candidate_canonical_url")
            or item.get("detected_url")
        )
    )
    selected_url = (
        decision.get("selected_canonical_url")
        or (canonical_urls[0] if len(canonical_urls) == 1 else "")
    )
    return f"""
    <form method="post"
        action="/projects/{html_escape(project_id)}/auxiliary-links/{html_escape(group.get("group_id"))}/review">
      <div class="form-grid">
        <label>
          Identidad del grupo
          <select name="identity_decision" required>
            {_auxiliary_identity_options(decision.get("identity_decision", ""))}
          </select>
        </label>
        <label>
          Uso para el grupo
          <select name="default_use" required>
            <option value="">Seleccionar</option>
            {_resource_use_options(decision.get("default_use", ""))}
          </select>
        </label>
        <label>
          Alcance
          <select name="scope">
            {_resource_scope_options(decision.get("scope", "shared"))}
          </select>
        </label>
      </div>
      <div class="form-grid">
        <label>
          URL canónica
          <select name="selected_canonical_url">
            <option value="">Sin seleccionar</option>
            {_auxiliary_canonical_url_options(canonical_urls, selected_url)}
          </select>
        </label>
        <label>
          Nombre mantenible
          <input name="display_name"
              value="{html_escape(decision.get("display_name") or suggested_title)}">
        </label>
        <label>
          Revisor
          <input name="actor"
              value="{html_escape(decision.get("reviewed_by", DEFAULT_ACTOR))}">
        </label>
      </div>
      <label>
        Notas del grupo
        <textarea name="notes"
            placeholder="Criterio general o aclaraciones para las excepciones.">{html_escape(decision.get("notes", ""))}</textarea>
      </label>
      <div class="actions">
        <button type="submit">Guardar y aplicar al grupo</button>
        <span class="muted">
          Las decisiones individuales existentes se conservan como excepciones.
        </span>
      </div>
    </form>
    """


def _auxiliary_identity_options(selected: str) -> str:
    labels = {
        "confirmed_same": "Confirmar mismo recurso",
        "keep_separate": "Mantener recursos separados",
        "review_later": "Revisar identidad después",
    }
    options = '<option value="">Seleccionar</option>'
    return options + "".join(
        f"""
        <option value="{html_escape(code)}" {"selected" if code == selected else ""}>
          {html_escape(label)}
        </option>
        """
        for code, label in labels.items()
    )


def _auxiliary_canonical_url_options(
    urls: list[str],
    selected: str,
) -> str:
    return "".join(
        f"""
        <option value="{html_escape(url)}" {"selected" if url == selected else ""}>
          {html_escape(url)}
        </option>
        """
        for url in urls
    )


def _auxiliary_status_message(request_path: str) -> str:
    query = parse_qs(urlparse(request_path).query)
    if "saved" in query:
        applied = query.get("applied", ["0"])[0]
        exceptions = query.get("exceptions", ["0"])[0]
        return f"""
        <p class="message ok">
          Grupo {html_escape(query["saved"][0])} guardado.
          Se aplicó a {html_escape(applied)} apariciones y se conservaron
          {html_escape(exceptions)} excepciones individuales.
        </p>
        """
    if "error" in query:
        return f"""
        <p class="message error">
          No se pudo guardar: {html_escape(query["error"][0])}
        </p>
        """
    return ""


def _auxiliary_appearance_row(item: dict[str, Any]) -> str:
    detected_url = item.get("detected_url", "")
    canonical_url = item.get("candidate_canonical_url") or detected_url
    canonical = ""
    if canonical_url != detected_url:
        canonical = f"""
        <p><strong>Destino final propuesto:</strong>
          <a href="{html_escape(canonical_url)}" target="_blank" rel="noreferrer">
            {html_escape(canonical_url)}
          </a>
        </p>
        """
    resolution = item.get("redirect_resolution", {})
    redirect_evidence = ""
    if resolution.get("status") == "resolved":
        redirect_evidence = f"""
        <p class="message ok">
          Redirección resuelta: {html_escape(resolution.get("redirect_count"))}
          salto(s), sin recorrer enlaces de la página.
        </p>
        """
    elif resolution.get("status") not in {None, "not_needed"}:
        redirect_evidence = f"""
        <p class="message error">
          Redirección: {html_escape(resolution.get("status"))}.
          {html_escape(resolution.get("error"))}
        </p>
        """

    return f"""
    <div class="resource-row">
      <div class="resource-head">
        <span class="pill">{html_escape(item.get("appearance_id"))}</span>
        <strong>{html_escape(item.get("label") or item.get("detected_url"))}</strong>
      </div>
      <p><strong>Nodo:</strong> {html_escape(item.get("source_node_title"))}
        <span class="muted">({html_escape(item.get("source_node_id"))})</span>
      </p>
      <p><strong>URL detectada:</strong>
        <a href="{html_escape(detected_url)}" target="_blank" rel="noreferrer">
          {html_escape(detected_url)}
        </a>
      </p>
      {canonical}
      {redirect_evidence}
      <dl>
        <dt>Tipo</dt><dd>{html_escape(item.get("functional_kind"))}</dd>
        <dt>Uso actual</dt><dd>{html_escape(item.get("existing_use") or "Sin decisión")}</dd>
        <dt>Estado</dt><dd>{html_escape(item.get("filter_status"))}</dd>
        <dt>Contexto</dt><dd>{html_escape(item.get("source_context"))}</dd>
      </dl>
    </div>
    """


def _auxiliary_group_title(
    group: dict[str, Any],
    items: list[dict[str, Any]],
) -> str:
    if group.get("suggested_functional_kind") == "agenda" and items:
        parameters = items[0].get("identity_parameters", {})
        agenda = parameters.get("agenda")
        recurso = parameters.get("recurso")
        if agenda and recurso:
            return f"Agenda {agenda} / {recurso}"
    labels = [item.get("label") for item in items if item.get("label")]
    return labels[0] if labels else group.get("group_id", "Grupo")


def _auxiliary_section_label(section_kind: str) -> str:
    return {
        "agenda": "Agenda candidata",
        "normalized": "Equivalencia normalizada fuerte",
        "exact": "URL exactamente repetida",
    }.get(section_kind, section_kind)


def _auxiliary_certainty_label(certainty: str) -> str:
    return {
        "agenda_parameters_match": "Coinciden agenda y recurso",
        "strong_normalized_equivalent": "Equivalencia fuerte",
        "exact_url": "URL exacta",
    }.get(certainty, certainty)


def _pdf_groups_page(project_id: str, request_path: str) -> str:
    project_dir = PROJECTS_DIR / project_id
    project = load_json(project_dir / "project.json")
    analysis_path = project_dir / "pdf_analysis.json"
    if not analysis_path.exists():
        body = f"""
        <section class="panel">
          <p><a href="/">Volver a proyectos</a></p>
          <h2>{html_escape(project.get("name"))}</h2>
          <p>No existe <code>pdf_analysis.json</code>.</p>
          <p class="muted">Ejecuta <code>python app.py analyze-pdfs --project-id {html_escape(project_id)}</code>.</p>
        </section>
        """
        return _page("Revisión agrupada de PDF", body)

    analysis = load_json(analysis_path)
    review_path = project_dir / "pdf_group_review.json"
    review = (
        load_json(review_path)
        if review_path.exists()
        else {"review_status": "not_started", "decisions": []}
    )
    decisions = {
        item.get("partition_id"): item
        for item in review.get("decisions", [])
        if item.get("partition_id")
    }
    legacy_decision_count = sum(
        not item.get("partition_id")
        for item in review.get("decisions", [])
    )
    family_decisions = {
        item.get("family_id"): item
        for item in review.get("family_decisions", [])
    }
    appearances = {
        item.get("appearance_id"): item
        for item in analysis.get("appearances", [])
    }
    groups = analysis.get("proposed_groups", [])
    partition_count = sum(
        len(group.get("verification", {}).get("partitions", []))
        for group in groups
    )
    reviewed_count = len(decisions)
    cards = "".join(
        _pdf_group_card(
            project_id,
            group,
            appearances,
            decisions,
            family_decisions.get(group.get("group_id"), {}),
        )
        for group in groups
    )
    summary = analysis.get("summary", {})
    body = f"""
    <section class="panel">
      <p>
        <a href="/">Volver a proyectos</a> |
        <a href="/projects/{html_escape(project_id)}/resource-rules">Configurar exclusiones</a> |
        <a href="/projects/{html_escape(project_id)}/auxiliary-links">Revisar enlaces auxiliares</a> |
        <a href="/projects/{html_escape(project_id)}/resources">Revisar casos individuales</a>
      </p>
      <p class="eyebrow">Paso 3 de 5 · grupos PDF</p>
      <h2>{html_escape(project.get("name"))}</h2>
      <p class="muted">
        El funcionario puede confirmar una familia por su conocimiento. La
        verificación técnica se ejecuta después, con límites de seguridad.
      </p>
      <div class="stats">
        <div><strong>{len(groups)}</strong><span>Grupos propuestos</span></div>
        <div><strong>{reviewed_count}/{partition_count}</strong><span>Particiones revisadas</span></div>
        <div><strong>{html_escape(summary.get("analyzed_count", 0))}</strong><span>PDF analizados</span></div>
        <div><strong>{html_escape("requiere revisión" if legacy_decision_count else review.get("review_status"))}</strong><span>Estado</span></div>
      </div>
      {f'<p class="message">Se conservaron {legacy_decision_count} decisiones del modelo anterior. No se aplican automáticamente a las nuevas particiones.</p>' if legacy_decision_count else ""}
      {_status_message(request_path)}
    </section>
    <section class="toolbar">
      <input id="pdfSearch" type="search" placeholder="Buscar grupo, recurso, nodo o URL">
      <select id="verificationFilter">
        <option value="">Todos los estados de verificación</option>
        <option value="not_started">Sin verificar</option>
        <option value="queued">Verificación en curso</option>
        <option value="partial">Verificación parcial</option>
        <option value="complete">Verificación completa</option>
        <option value="error">Error técnico</option>
      </select>
      <select id="reviewFilter">
        <option value="">Revisados y pendientes</option>
        <option value="pending">Solo pendientes</option>
        <option value="reviewed">Solo revisados</option>
      </select>
      <button type="button" onclick="clearPdfFilters()">Limpiar</button>
    </section>
    <section class="cards">{cards}</section>
    <script>
      const pdfSearch = document.getElementById("pdfSearch");
      const verificationFilter = document.getElementById("verificationFilter");
      const reviewFilter = document.getElementById("reviewFilter");
      [pdfSearch, verificationFilter, reviewFilter].forEach(
        control => control.addEventListener("input", applyPdfFilters)
      );
      function applyPdfFilters() {{
        const query = pdfSearch.value.trim().toLowerCase();
        document.querySelectorAll(".pdf-group").forEach(card => {{
          const textOk = !query || card.dataset.search.includes(query);
          const certaintyOk = !verificationFilter.value ||
            card.dataset.verification === verificationFilter.value;
          const reviewOk = !reviewFilter.value ||
            card.dataset.review === reviewFilter.value;
          card.classList.toggle("hidden", !(textOk && certaintyOk && reviewOk));
        }});
      }}
      function clearPdfFilters() {{
        pdfSearch.value = "";
        verificationFilter.value = "";
        reviewFilter.value = "";
        applyPdfFilters();
      }}
    </script>
    """
    return _page(f"Revisión agrupada de PDF - {project.get('name')}", body)


def _pdf_group_card(
    project_id: str,
    group: dict[str, Any],
    appearances: dict[str, dict[str, Any]],
    decisions: dict[str, dict[str, Any]],
    family_decision: dict[str, Any],
) -> str:
    group_id = group.get("group_id", "")
    items = [
        appearances[item_id]
        for item_id in group.get("appearance_ids", [])
        if item_id in appearances
    ]
    proposed = group.get("proposed_canonical_resource", {})
    display_name = proposed.get("display_name") or ""
    verification = group.get("verification", {})
    partitions = verification.get("partitions", [])
    certainty = group.get("certainty", "")
    search_text = " ".join(
        [
            group_id,
            display_name,
            certainty,
            *[
                " ".join(
                    str(item.get(field, "") or "")
                    for field in (
                        "source_node_id",
                        "source_node_title",
                        "label",
                        "detected_url",
                    )
                )
                for item in items
            ],
        ]
    ).lower()
    family_decision_current = bool(family_decision) and set(
        family_decision.get("appearance_ids", [])
    ) == set(group.get("appearance_ids", []))
    return f"""
    <article class="card pdf-group" id="{html_escape(group_id)}"
        data-verification="{html_escape(verification.get("status"))}"
        data-review="{"reviewed" if family_decision_current or (partitions and all(part.get("partition_id") in decisions for part in partitions)) else "pending"}"
        data-search="{html_escape(search_text)}">
      <div class="card-head">
        <div>
          <p class="eyebrow">{html_escape(group_id)}</p>
          <h2>{html_escape(display_name)}</h2>
          <p class="muted">{len(items)} apariciones · familia propuesta por nombre de archivo</p>
        </div>
        <span class="pill">{html_escape(_verification_label(verification.get("status")))}</span>
      </div>
      {_pdf_evidence(group, items)}
      <h3>Links incluidos en la familia</h3>
      {_appearance_rows(items, set())}
      {'<p class="message">La familia incorporó o perdió apariciones desde la decisión anterior. Confirma nuevamente el conjunto actual.</p>' if family_decision and not family_decision_current else ''}
      {_manual_family_form(project_id, group, items, family_decision)}
      <form method="post" action="/projects/{html_escape(project_id)}/pdf-groups/{html_escape(group_id)}/verify">
        <input type="hidden" name="actor" value="{html_escape(DEFAULT_ACTOR)}">
        <label class="checkbox">
          <input type="checkbox" name="local_only" value="true">
          Usar solo PDF locales (no descargar)
        </label>
        <button type="submit">Verificar ahora</button>
      </form>
      {_verification_result(
          project_id,
          group,
          items,
          decisions,
          family_decision,
      )}
    </article>
    """


def _manual_family_form(
    project_id: str,
    family: dict[str, Any],
    items: list[dict[str, Any]],
    decision: dict[str, Any],
) -> str:
    proposed = family.get("proposed_canonical_resource", {})
    selected_url = (
        decision.get("selected_canonical_url")
        or proposed.get("proposed_canonical_url")
        or ""
    )
    default_use = (
        decision.get("default_use")
        or proposed.get("suggested_default_use")
        or "review_later"
    )
    display_name = (
        decision.get("display_name")
        or proposed.get("display_name")
        or ""
    )
    reconciliation = decision.get("verification_reconciliation")
    notice = {
        "consistent": '<p class="message ok">La verificación coincide con la decisión manual.</p>',
        "conflict": '<p class="message error">La verificación encontró contenidos distintos. Revisa las particiones.</p>',
        "verification_incomplete": '<p class="message">La decisión manual se conserva; la verificación quedó incompleta.</p>',
        "pending": '<p class="message">La verificación automática está pendiente.</p>',
    }.get(reconciliation, "")
    return f"""
    <section class="manual-decision">
      <h3>Decisión directa del funcionario</h3>
      <p class="muted">Confirma toda la familia como un mismo recurso. Al guardar, la verificación técnica comienza en segundo plano.</p>
      {notice}
      <form method="post"
          action="/projects/{html_escape(project_id)}/pdf-groups/{html_escape(family.get("group_id"))}/confirm">
        <div class="form-grid">
          <label>Uso
            <select name="default_use">{_resource_use_options(default_use)}</select>
          </label>
          <label>Nombre
            <input name="display_name" value="{html_escape(display_name)}">
          </label>
          <label>Revisor
            <input name="actor" value="{html_escape(decision.get("reviewed_by", DEFAULT_ACTOR))}">
          </label>
        </div>
        <label>URL canónica
          <select name="selected_canonical_url">
            {_canonical_url_options(items, selected_url)}
          </select>
        </label>
        <label>Notas
          <textarea name="notes">{html_escape(decision.get("notes"))}</textarea>
        </label>
        <div class="actions">
          <button type="submit">Confirmar toda la familia</button>
          <span class="muted">{_reviewed_at(decision)}</span>
        </div>
      </form>
    </section>
    """


def _verification_result(
    project_id: str,
    family: dict[str, Any],
    items: list[dict[str, Any]],
    decisions: dict[str, dict[str, Any]],
    family_decision: dict[str, Any],
) -> str:
    verification = family.get("verification", {})
    partitions = verification.get("partitions", [])
    if verification.get("status") == "not_started":
        return '<p class="message">Contenido todavía no verificado.</p>'
    if verification.get("status") == "queued":
        return '<p class="message">Verificación automática en curso. Recarga la página en unos momentos.</p>'
    if verification.get("status") == "error":
        return (
            '<p class="message error">La verificación no pudo completarse: '
            f'{html_escape(verification.get("error"))}</p>'
        )

    by_id = {item.get("appearance_id"): item for item in items}
    partition_cards = "".join(
        _pdf_partition_card(
            project_id,
            family,
            partition,
            [by_id[item_id] for item_id in partition.get("appearance_ids", [])],
            decisions.get(partition.get("partition_id"), {}),
        )
        for partition in partitions
    )
    unverified = [
        by_id[item_id]
        for item_id in verification.get("unverified_appearance_ids", [])
        if item_id in by_id
    ]
    all_same = verification.get("all_appearances_same")
    statuses = [
        item.get("analysis", {}).get("status", "pending")
        for item in items
    ]
    verified_count = statuses.count("analyzed")
    skipped_count = statuses.count("skipped_by_policy")
    download_error_count = statuses.count("download_error")
    analysis_error_count = sum(
        status in {"analysis_error", "error"} for status in statuses
    )
    pending_count = sum(
        status in {
            "not_verified",
            "pending",
            "not_attempted_local_only",
        }
        for status in statuses
    )
    partition_decided = all(
        partition.get("partition_id") in decisions
        for partition in partitions
    )
    clean_result = (
        verification.get("status") == "complete"
        and all_same
        and len(partitions) == 1
        and partition_decided
    )
    detail_open = "" if clean_result else " open"
    summary_lines = [
        f"<li><strong>{len(items)}</strong> PDF en la familia</li>",
        f"<li><strong>{verified_count}</strong> verificados</li>",
        f"<li><strong>{skipped_count}</strong> omitidos por límites</li>",
        f"<li><strong>{download_error_count}</strong> no pudieron descargarse</li>",
        f"<li><strong>{analysis_error_count}</strong> no pudieron analizarse</li>",
        f"<li><strong>{pending_count}</strong> pendientes</li>",
        (
            f"<li><strong>{len(partitions)}</strong> "
            f"{'documento diferente encontrado' if len(partitions) == 1 else 'documentos diferentes encontrados'}</li>"
        ),
    ]
    reconciliation = family_decision.get("verification_reconciliation")
    outcome = {
        "consistent": "La verificación coincide con la decisión del funcionario.",
        "conflict": "La verificación encontró varios contenidos y requiere revisión.",
        "verification_incomplete": "La decisión se conserva, pero la verificación fue incompleta.",
    }.get(reconciliation, "")
    return f"""
    <section class="verification-result">
      <h3>Resultado de la verificación</h3>
      <ul class="verification-summary">{"".join(summary_lines)}</ul>
      {f'<p class="message ok">{html_escape(outcome)}</p>' if reconciliation == "consistent" else f'<p class="message">{html_escape(outcome)}</p>' if outcome else ""}
      <details{detail_open}>
        <summary>Ver detalle del resultado</summary>
        {partition_cards}
        {"<h4>Sin verificar</h4>" + _appearance_rows(unverified, set()) if unverified else ""}
      </details>
    </section>
    """


def _pdf_partition_card(
    project_id: str,
    family: dict[str, Any],
    partition: dict[str, Any],
    items: list[dict[str, Any]],
    decision: dict[str, Any],
) -> str:
    family_id = family.get("group_id", "")
    partition_id = partition.get("partition_id", "")
    proposed = family.get("proposed_canonical_resource", {})
    certainty = partition.get("certainty", "")
    identity = decision.get(
        "identity_decision",
        "confirmed_same" if certainty == "exact_binary_duplicate" else "review_later",
    )
    default_use = (
        decision.get("default_use")
        or proposed.get("suggested_default_use")
        or "review_later"
    )
    display_name = decision.get("display_name") or proposed.get("display_name") or ""
    selected_url = decision.get("selected_canonical_url") or (
        items[0].get("detected_url") if items else ""
    )
    inherited = decision.get("decision_source") == "inherited_from_family"
    inherited_notice = (
        '<p class="message ok">Decisión aplicada automáticamente desde la '
        'confirmación de la familia. No necesitas volver a guardarla.</p>'
        if inherited
        else ""
    )
    button_label = (
        "Modificar decisión de esta partición"
        if inherited
        else "Guardar partición"
    )
    return f"""
    <div class="partition-card">
      <div class="resource-head">
        <strong>{html_escape(partition_id)}</strong>
        <span class="pill">{html_escape(_certainty_label(certainty))}</span>
        <span>{len(items)} aparición(es)</span>
      </div>
      {inherited_notice}
      {_appearance_rows(items, set())}
      <form method="post"
          action="/projects/{html_escape(project_id)}/pdf-groups/{html_escape(family_id)}/{html_escape(partition_id)}">
        <div class="form-grid">
          <label>Decisión
            <select name="identity_decision">{_identity_options(identity)}</select>
          </label>
          <label>Uso
            <select name="default_use">{_resource_use_options(default_use)}</select>
          </label>
          <label>Nombre
            <input name="display_name" value="{html_escape(display_name)}">
          </label>
        </div>
        <label>URL canónica
          <select name="selected_canonical_url">
            {_canonical_url_options(items, selected_url)}
          </select>
        </label>
        <label>Notas
          <textarea name="notes">{html_escape(decision.get("notes"))}</textarea>
        </label>
        <input type="hidden" name="actor"
            value="{html_escape(decision.get("reviewed_by", DEFAULT_ACTOR))}">
        <div class="actions">
          <button type="submit">{button_label}</button>
          <span class="muted">{_reviewed_at(decision)}</span>
        </div>
      </form>
    </div>
    """


def _pdf_evidence(
    group: dict[str, Any],
    items: list[dict[str, Any]],
) -> str:
    evidence = group.get("evidence", {})
    return f"""
    <dl>
      <dt>Agrupado por</dt><dd>Nombre normalizado obtenido de la URL</dd>
      <dt>Clave</dt><dd>{html_escape(evidence.get("value"))}</dd>
    </dl>
    """


def _appearance_rows(
    items: list[dict[str, Any]],
    excluded: set[str],
) -> str:
    rows = []
    for item in items:
        appearance_id = item.get("appearance_id", "")
        analysis = item.get("analysis", {})
        rows.append(
            f"""
            <div class="appearance-row">
              <div>
                <strong>{html_escape(item.get("label") or item.get("file_name"))}</strong>
                <p class="muted">
                  Nodo: {html_escape(item.get("source_node_title") or item.get("source_node_id"))}
                  · uso actual: {html_escape(item.get("existing_use"))}
                  · análisis: {html_escape(analysis.get("status"))}
                </p>
                {f'<p class="message error">{html_escape(_friendly_pdf_error(analysis))}</p>' if analysis.get("error") else ""}
                <a class="url" href="{html_escape(item.get("detected_url"))}"
                    target="_blank" rel="noreferrer">{html_escape(item.get("detected_url"))}</a>
              </div>
            </div>
            """
        )
    return "".join(rows)


def _friendly_pdf_error(analysis: dict[str, Any]) -> str:
    error = str(analysis.get("error", ""))
    if "WinError 10013" in error:
        return (
            "La aplicación no tuvo permiso de red para descargar este PDF. "
            "Reiníciala desde una terminal con acceso a Internet y vuelve a verificar."
        )
    if "403" in error or "Forbidden" in error:
        return (
            "El sitio oficial rechazó la descarga automática. "
            "Puedes abrir el enlace o volver a intentar la verificación."
        )
    if analysis.get("status") == "download_error":
        return "No se pudo descargar este PDF. Comprueba la conexión y vuelve a intentar."
    if analysis.get("status") == "analysis_error":
        return "El PDF se descargó, pero no pudo analizarse automáticamente."
    return "La verificación técnica no pudo completarse."


def _canonical_url_options(
    items: list[dict[str, Any]],
    selected: str,
) -> str:
    options = []
    seen = set()
    for item in items:
        url = item.get("detected_url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        label = item.get("file_name") or url
        is_selected = " selected" if url == selected else ""
        options.append(
            f'<option value="{html_escape(url)}"{is_selected}>'
            f'{html_escape(label)} — {html_escape(item.get("source_node_title"))}'
            "</option>"
        )
    return "".join(options)


def _identity_options(selected: str) -> str:
    labels = [
        ("review_later", "Revisar después"),
        ("confirmed_same", "Confirmar: son el mismo recurso"),
        ("keep_separate", "Mantener separados"),
    ]
    return "".join(
        f'<option value="{code}"{" selected" if code == selected else ""}>'
        f"{label}</option>"
        for code, label in labels
    )


def _certainty_label(certainty: str) -> str:
    return {
        "exact_binary_duplicate": "Duplicado exacto",
        "probable_same_content": "Mismo contenido probable",
        "similar_candidate": "Posible similitud",
        "unverified": "No verificado",
        "distinct_content": "Contenido distinto",
    }.get(certainty, certainty)


def _verification_label(status: str) -> str:
    return {
        "not_started": "Sin verificar",
        "queued": "Verificación en curso",
        "partial": "Verificación parcial",
        "complete": "Verificación completa",
        "error": "Error técnico",
    }.get(status, status)


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
      {f'''<form method="post" action="/projects/{html_escape(project_id)}/discover-links">
        <button type="submit">Buscar enlaces ahora</button>
      </form>''' if not links else ''}
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
            link.get("url_category"),
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
        <dt>Categoría de URL</dt><dd>{html_escape(link.get("url_category") or "No disponible")}</dd>
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
    pdf_families: list[dict[str, Any]],
    pdf_family_by_appearance: dict[str, dict[str, Any]],
    identity_by_appearance: dict[str, dict[str, Any]],
    node_is_active: bool = True,
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
            pdf_families,
            pdf_family_by_appearance.get(
                f"{page.get('link_id')}::{resource.get('resource_id')}"
            ),
            identity_by_appearance.get(
                f"{page.get('link_id')}::{resource.get('resource_id')}",
                {},
            ),
        )
        for resource in resources
    )
    discarded_rows = "".join(
        _resource_row(
            project_id,
            page.get("link_id", ""),
            resource,
            "discarded",
            decisions_by_resource.get(
                f"{page.get('link_id')}::{resource.get('resource_id')}",
                {},
            ),
            pdf_families,
            pdf_family_by_appearance.get(
                f"{page.get('link_id')}::{resource.get('resource_id')}"
            ),
            identity_by_appearance.get(
                f"{page.get('link_id')}::{resource.get('resource_id')}",
                {},
            ),
        )
        for resource in discarded
    )
    error = ""
    if page.get("status") == "error":
        error = f"""<p class="message error">{html_escape(page.get("error"))}</p>"""

    lifecycle_badge = (
        '<span class="pill">Nodo activo</span>'
        if node_is_active
        else '<span class="pill inactive">Nodo inactivo · solo referencia</span>'
    )
    inactive_notice = ""
    if not node_is_active:
        inactive_notice = """
        <p class="message inactive">
          Este nodo fue desactivado del modelo. Sus recursos y decisiones se
          muestran como referencia histórica y pueden recuperarse al reactivarlo.
        </p>
        """

    return f"""
    <article class="card {'inactive-node' if not node_is_active else ''}" data-node-status="{'active' if node_is_active else 'inactive'}">
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
        <div>
          {lifecycle_badge}
          <span class="pill">{len(resources)} utiles / {len(discarded)} descartados</span>
        </div>
      </div>
      {inactive_notice}
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
    pdf_families: list[dict[str, Any]],
    current_pdf_family: dict[str, Any] | None,
    identity_decision: dict[str, Any],
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
        if resource.get("resource_type") == "pdf":
            review_form = _resource_identity_form(
                project_id,
                source_link_id,
                resource,
                pdf_families,
                current_pdf_family,
                identity_decision,
            ) + review_form
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
    if not decision:
        decision_state = "pending"
        decision_badge = '<span class="pill">Pendiente</span>'
    elif decision.get("decision_source") in {"auxiliary_group", "pdf_group"}:
        decision_state = "group"
        decision_badge = (
            '<span class="pill">Heredada del grupo '
            f'{html_escape(decision.get("source_group_id"))}</span>'
        )
    else:
        decision_state = "individual"
        decision_badge = '<span class="pill">Decisión individual</span>'
    return f"""
    <div class="resource-row" id="{html_escape(source_link_id)}-{html_escape(resource.get("resource_id"))}"
        data-search="{html_escape(search_text)}"
        data-type="{html_escape(resource.get("resource_type"))}"
        data-discard="{html_escape(discard_state)}"
        data-decision="{html_escape(decision_state)}">
      <div class="resource-head">
        <span class="pill">{html_escape(resource.get("resource_type"))}</span>
        {decision_badge}
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


def _resource_identity_form(
    project_id: str,
    source_link_id: str,
    resource: dict[str, Any],
    families: list[dict[str, Any]],
    current_family: dict[str, Any] | None,
    identity_decision: dict[str, Any],
) -> str:
    current_id = (
        identity_decision.get("target_family_id")
        or (current_family.get("group_id", "") if current_family else "")
    )
    options = "".join(
        f'<option value="{html_escape(family.get("group_id"))}">'
        f'{html_escape(family.get("proposed_canonical_resource", {}).get("display_name") or family.get("group_id"))} '
        f'· {len(family.get("appearance_ids", []))} apariciones</option>'
        for family in sorted(
            families,
            key=lambda item: (
                item.get("group_id") != current_id,
                str(item.get("proposed_canonical_resource", {}).get("display_name", "")),
            ),
        )
    )
    saved_notice = ""
    if identity_decision:
        mode_label = (
            "pendiente de verificación"
            if identity_decision.get("assignment_mode") == "candidate_verify"
            else "confirmada directamente"
        )
        saved_notice = (
            '<p class="message ok">Pertenencia guardada: '
            f'{html_escape(identity_decision.get("target_family_id") or identity_decision.get("action"))} '
            f'· {html_escape(mode_label)}.</p>'
        )
    current_notice = (
        f'<p class="message">Actualmente es candidata de <strong>{html_escape(current_id)}</strong>. '
        'Puedes reconfirmarla, moverla o mantenerla individual.</p>'
        if current_id
        else '<p class="message">Identidad sin consolidar. Selecciona cómo resolverla.</p>'
    )
    return f"""
    <details class="identity-resolution">
      <summary>Resolver identidad: asignar grupo, crear uno nuevo o excluir</summary>
      {saved_notice}
      {current_notice}
      <form class="resource-identity-form" method="post" action="/projects/{html_escape(project_id)}/resources/{html_escape(source_link_id)}/{html_escape(resource.get('resource_id'))}/identity">
        <input type="hidden" name="search_filter" value="">
        <input type="hidden" name="type_filter" value="">
        <input type="hidden" name="discard_filter" value="">
        <input type="hidden" name="decision_filter" value="">
        <input type="hidden" name="scroll_y" value="0">
        <div class="form-grid">
          <label>Acción
            <select name="identity_action">
              <option value="assign_existing" {'selected' if identity_decision.get('action', 'assign_existing') == 'assign_existing' else ''}>Asignar a una familia existente</option>
              <option value="create_family" {'selected' if identity_decision.get('action') == 'create_family' else ''}>Crear una familia nueva</option>
              <option value="keep_individual" {'selected' if identity_decision.get('action') == 'keep_individual' else ''}>Mantener como recurso individual</option>
              <option value="exclude" {'selected' if identity_decision.get('action') == 'exclude' else ''}>Excluir este recurso</option>
            </select>
          </label>
          <label>Buscar familia existente
            <input name="target_family_id" list="families-{html_escape(source_link_id)}-{html_escape(resource.get('resource_id'))}" value="{html_escape(current_id)}" placeholder="Nombre o identificador">
            <datalist id="families-{html_escape(source_link_id)}-{html_escape(resource.get('resource_id'))}">{options}</datalist>
          </label>
          <label>Nombre de familia nueva
            <input name="new_family_name" value="{html_escape(identity_decision.get('new_family_name'))}" placeholder="Solo si creas una familia">
          </label>
        </div>
        <fieldset>
          <legend>Forma de incorporación</legend>
          <label class="checkbox"><input type="radio" name="assignment_mode" value="candidate_verify" {'checked' if identity_decision.get('assignment_mode', 'candidate_verify') == 'candidate_verify' else ''}> Agregar como candidata y verificar</label>
          <label class="checkbox"><input type="radio" name="assignment_mode" value="direct_confirm" {'checked' if identity_decision.get('assignment_mode') == 'direct_confirm' else ''}> Confirmar directamente como el mismo recurso</label>
        </fieldset>
        <label>Motivo o evidencia
          <textarea name="identity_notes" placeholder="Explica por qué pertenece al grupo, debe separarse o excluirse.">{html_escape(identity_decision.get('notes'))}</textarea>
        </label>
        <input type="hidden" name="actor" value="{html_escape(DEFAULT_ACTOR)}">
        <button type="submit">Guardar resolución de identidad</button>
      </form>
    </details>
    """


def _resource_review_form(
    project_id: str,
    source_link_id: str,
    resource: dict[str, Any],
    decision: dict[str, Any],
) -> str:
    return f"""
    <form class="resource-review-form" method="post" action="/projects/{html_escape(project_id)}/resources/{html_escape(source_link_id)}/{html_escape(resource.get("resource_id"))}">
      <input type="hidden" name="search_filter" value="">
      <input type="hidden" name="type_filter" value="">
      <input type="hidden" name="discard_filter" value="">
      <input type="hidden" name="decision_filter" value="">
      <input type="hidden" name="scroll_y" value="0">
      <div class="form-grid">
        <label>
          Que hacemos con este recurso
          <select name="use" required>
            <option value="">Seleccionar</option>
            {_resource_use_options(decision.get("use", ""))}
          </select>
        </label>
        <label>
          Alcance derivado
          <input type="hidden" name="scope" value="{html_escape(decision.get('scope', 'node_only'))}">
          <input value="{html_escape(_resource_scope_label(decision.get('scope', 'node_only')))}" disabled>
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


def _resource_scope_label(scope: str) -> str:
    return {
        "node_only": "Solo aparece en este nodo",
        "shared": "Compartido: derivado del recurso canónico",
    }.get(scope, "Pendiente de consolidación")


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


def _project_id_from_resource_rules_path(path: str) -> str | None:
    parts = path.strip("/").split("/")
    if len(parts) == 3 and parts[0] == "projects" and parts[2] == "resource-rules":
        return parts[1]
    return None


def _project_id_from_pdf_groups_path(path: str) -> str | None:
    parts = path.strip("/").split("/")
    if len(parts) == 3 and parts[0] == "projects" and parts[2] == "pdf-groups":
        return parts[1]
    return None


def _project_id_from_auxiliary_links_path(path: str) -> str | None:
    parts = path.strip("/").split("/")
    if (
        len(parts) == 3
        and parts[0] == "projects"
        and parts[2] == "auxiliary-links"
    ):
        return parts[1]
    return None


def _project_id_from_effective_state_path(path: str) -> str | None:
    parts = path.strip("/").split("/")
    if len(parts) == 3 and parts[0] == "projects" and parts[2] == "effective-state":
        return parts[1]
    return None


def _project_id_from_document_map_path(path: str) -> str | None:
    parts = path.strip("/").split("/")
    if len(parts) == 3 and parts[0] == "projects" and parts[2] == "document-map":
        return parts[1]
    return None


def _project_id_from_discover_path(path: str) -> str | None:
    parts = path.strip("/").split("/")
    if len(parts) == 3 and parts[0] == "projects" and parts[2] == "discover-links":
        return parts[1]
    return None


def _project_id_from_delete_path(path: str) -> str | None:
    parts = path.strip("/").split("/")
    if len(parts) == 3 and parts[0] == "projects" and parts[2] == "delete":
        return parts[1]
    return None


def _document_map_resource_route(path: str) -> tuple[str, str, str] | None:
    parts = path.strip("/").split("/")
    if (
        len(parts) == 6
        and parts[0] == "projects"
        and parts[2] == "document-map"
        and parts[3] == "resources"
    ):
        return parts[1], parts[4], parts[5]
    return None


def _lifecycle_decision_route(path: str) -> tuple[str, str] | None:
    parts = path.strip("/").split("/")
    if len(parts) == 4 and parts[0] == "projects" and parts[2] == "effective-state":
        return parts[1], parts[3]
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


def _resource_identity_route(path: str) -> tuple[str, str, str] | None:
    parts = path.strip("/").split("/")
    if (
        len(parts) == 6
        and parts[0] == "projects"
        and parts[2] == "resources"
        and parts[5] == "identity"
    ):
        return parts[1], parts[3], parts[4]
    return None


def _auxiliary_group_decision_route(
    path: str,
) -> tuple[str, str] | None:
    parts = path.strip("/").split("/")
    if (
        len(parts) == 5
        and parts[0] == "projects"
        and parts[2] == "auxiliary-links"
        and parts[4] == "review"
    ):
        return parts[1], parts[3]
    return None


def _pdf_group_decision_route(path: str) -> tuple[str, str, str] | None:
    parts = path.strip("/").split("/")
    if (
        len(parts) == 5
        and parts[0] == "projects"
        and parts[2] == "pdf-groups"
        and parts[4] not in {"verify", "confirm"}
    ):
        return parts[1], parts[3], parts[4]
    return None


def _pdf_family_verify_route(path: str) -> tuple[str, str] | None:
    parts = path.strip("/").split("/")
    if (
        len(parts) == 5
        and parts[0] == "projects"
        and parts[2] == "pdf-groups"
        and parts[4] == "verify"
    ):
        return parts[1], parts[3]
    return None


def _pdf_family_decision_route(path: str) -> tuple[str, str] | None:
    parts = path.strip("/").split("/")
    if (
        len(parts) == 5
        and parts[0] == "projects"
        and parts[2] == "pdf-groups"
        and parts[4] == "confirm"
    ):
        return parts[1], parts[3]
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


def _resource_filters_from_form(
    form: dict[str, list[str]],
) -> dict[str, str]:
    filters = {
        "search_filter": _single(form, "search_filter")[:200],
        "type_filter": _single(form, "type_filter")[:80],
        "discard_filter": _single(form, "discard_filter"),
        "decision_filter": _single(form, "decision_filter"),
        "scroll_y": _single(form, "scroll_y"),
    }
    if filters["discard_filter"] not in {"", "kept", "discarded"}:
        filters["discard_filter"] = ""
    if filters["decision_filter"] not in {
        "",
        "pending",
        "group",
        "individual",
    }:
        filters["decision_filter"] = ""
    try:
        scroll_y = int(filters["scroll_y"] or "0")
    except ValueError:
        scroll_y = 0
    filters["scroll_y"] = str(min(max(scroll_y, 0), 10_000_000))
    if filters["scroll_y"] == "0":
        filters["scroll_y"] = ""
    return {key: value for key, value in filters.items() if value}


def _resource_review_redirect(
    project_id: str,
    source_link_id: str,
    resource_id: str,
    parameters: dict[str, str],
) -> str:
    query = urlencode(parameters)
    fragment = f"{source_link_id}-{resource_id}"
    return f"/projects/{project_id}/resources?{query}#{fragment}"


def _status_message(request_path: str) -> str:
    query = parse_qs(urlparse(request_path).query)
    if "created" in query:
        return (
            '<p class="message ok">Proyecto creado. Ahora puedes volver a proyectos '
            'y usar Buscar enlaces.</p>'
        )
    if "discovered" in query:
        pages = query.get("pages", ["1"])[0]
        errors = query.get("page_errors", ["0"])[0]
        limit_reached = query.get("page_limit", ["0"])[0] == "1"
        warning = ""
        if errors != "0":
            warning += f" {html_escape(errors)} páginas no pudieron procesarse."
        if limit_reached:
            warning += " Se alcanzó el límite de páginas."
        return (
            f'<p class="message ok">Búsqueda terminada: '
            f'{html_escape(query["discovered"][0])} enlaces encontrados en '
            f'{html_escape(pages)} páginas.{warning}</p>'
        )
    if "saved_identity" in query:
        return (
            '<p class="message ok">Pertenencia al grupo guardada. '
            'Si se agregó como candidata, queda pendiente de verificación.</p>'
        )
    if "saved" in query:
        return f"""<p class="message ok">Decision guardada para {html_escape(query["saved"][0])}.</p>"""
    if "verified" in query:
        return f"""<p class="message ok">Verificación terminada para {html_escape(query["verified"][0])}.</p>"""
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
    .hidden {{ display: none !important; }}
    .card.inactive-node {{
      border-style: dashed;
      background: #f8fafc;
      opacity: .82;
    }}
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
    button.danger, .button.danger {{
      background: #a12b2b;
      border-color: #a12b2b;
      color: #fff;
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
    .pill.inactive {{
      color: #7a2e0e;
      border-color: #f0b58d;
      background: #fff7ed;
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
    .message.inactive {{
      color: #7a2e0e;
      background: #fff7ed;
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
    .identity-resolution {{
      margin: 12px 0;
      border: 1px solid var(--accent);
      border-radius: 6px;
      background: #f5f9ff;
    }}
    .identity-resolution > summary {{
      padding: 10px 12px;
      color: var(--accent);
      font-weight: 700;
      cursor: pointer;
    }}
    .identity-resolution[open] {{
      padding: 0 12px 12px;
    }}
    .resource-head {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .appearance-row {{
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 12px;
      align-items: start;
      padding: 10px 0;
      border-top: 1px solid var(--border);
    }}
    .appearance-row:first-of-type {{
      border-top: 0;
    }}
    .appearance-row p {{
      margin: 4px 0;
    }}
    .exclusion {{
      color: var(--error-text);
    }}
    .verification-result {{
      margin-top: 16px;
      border-top: 2px solid var(--border);
      padding-top: 8px;
    }}
    .partition-card {{
      margin: 12px 0;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 12px;
      background: #f8fafc;
    }}
    .verification-summary {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      padding: 0;
      list-style: none;
    }}
    .verification-summary li {{
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px;
      background: #f8fafc;
    }}
    details {{
      margin-top: 12px;
    }}
    summary {{
      color: var(--accent);
      cursor: pointer;
      font-weight: bold;
    }}
    @media (max-width: 760px) {{
      .card-head, .form-grid, .stats, dl, .appearance-row, .verification-summary {{
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
