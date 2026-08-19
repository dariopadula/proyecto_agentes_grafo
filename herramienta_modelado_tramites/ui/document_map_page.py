import json
from typing import Any

from core.html_utils import html_escape


def render_document_map_body(
    project: dict[str, Any],
    document_map: dict[str, Any],
) -> str:
    """Renderiza la auditoría documental lateral con edición local de uso."""
    payload = json.dumps(document_map, ensure_ascii=False).replace("</", "<\\/")
    template = r"""
    <style>
      main { max-width: 1440px; padding: 0; }
      .document-shell { display: grid; grid-template-columns: minmax(560px, 1fr) 340px; height: calc(100vh - 66px); min-height: 560px; overflow: hidden; }
      .document-coverage { padding: 18px; background: var(--panel); }
      .document-coverage { min-height: 0; overflow-y: auto; border-left: 1px solid var(--border); }
      .document-workspace { min-height: 0; padding: 20px; overflow-y: auto; scroll-behavior: smooth; }
      .document-coverage h2 { margin-bottom: 6px; font-size: 18px; }
      .document-selector { position: sticky; top: -20px; z-index: 8; margin: -20px -20px 18px; padding: 16px 20px 14px; background: #f4f6f8; border-bottom: 1px solid var(--border); }
      .document-selector-row { position: relative; max-width: 920px; }
      .document-selector input { margin: 5px 0 0; padding-right: 38px; background: var(--panel); }
      .document-selector-toggle { position: absolute; right: 4px; bottom: 4px; width: 32px; min-height: 32px; margin: 0; padding: 0; color: var(--accent); background: transparent; border-color: transparent; }
      .document-suggestions { position: absolute; z-index: 20; top: calc(100% + 4px); left: 0; right: 0; display: grid; max-height: 340px; padding: 5px; overflow-y: auto; overscroll-behavior: contain; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 12px 28px rgba(16, 24, 40, .16); }
      .document-suggestions[hidden] { display: none; }
      .terminal-option { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; width: 100%; min-height: 0; margin: 0; padding: 10px 11px; color: var(--text); background: transparent; border-color: transparent; text-align: left; }
      .terminal-option:hover, .terminal-option:focus-visible, .terminal-option.selected { color: var(--text); background: #eef6ff; border-color: #a9cbea; }
      .terminal-option strong { line-height: 1.35; }
      .terminal-count { color: var(--muted); font-size: 11px; }
      .workspace-head { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
      .workspace-head h2 { margin-bottom: 6px; font-size: 21px; }
      .workspace-summary { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
      .workspace-navigation { display: flex; gap: 6px; margin-top: 10px; }
      .workspace-navigation button { min-height: 30px; margin: 0; padding: 0 9px; }
      .terminal-focus { margin: 18px 0; padding: 16px; color: #fff; background: var(--accent); border-radius: 8px; text-align: center; }
      .terminal-focus strong { display: block; margin-bottom: 5px; }
      .terminal-focus small { color: #dcecff; }
      .document-section { margin-top: 18px; }
      .document-section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
      .document-section-head h3 { margin: 0; font-size: 15px; }
      .document-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
      .document-item { display: block; width: 100%; min-height: 108px; margin: 0; padding: 11px; color: var(--text); background: var(--panel); border: 1px solid var(--border); border-radius: 7px; text-align: left; }
      .document-item.selected { background: #eef6ff; border-color: var(--accent); }
      .document-item strong { display: block; margin-bottom: 7px; }
      .document-item .pill { display: inline-block; margin: 2px 3px 2px 0; white-space: normal; }
      .document-item p { margin: 7px 0 0; color: var(--muted); font-size: 12px; }
      .document-resource-link { display: inline-block; margin-top: 8px; font-size: 12px; overflow-wrap: anywhere; }
      .document-item details { margin-top: 8px; color: var(--muted); font-size: 12px; }
      .document-item summary { font-weight: normal; }
      .document-edit { margin-top: 9px; padding-top: 8px; border-top: 1px solid var(--border); }
      .document-edit form { display: grid; gap: 7px; margin-top: 8px; }
      .document-edit select, .document-edit input { margin: 0; }
      .document-edit button { min-height: 32px; margin: 0; padding: 0 10px; }
      .document-local-note { color: var(--muted); font-size: 11px; }
      .document-message { margin: 0 0 14px; padding: 10px; border-radius: 6px; background: var(--ok-bg); color: var(--ok-text); }
      .document-coverage-action { min-height: 30px; margin: 9px 0 0; padding: 0 9px; }
      .document-empty { padding: 12px; color: var(--muted); background: #f8fafc; border-radius: 6px; }
      .coverage-empty { display: grid; place-content: center; min-height: 330px; color: var(--muted); text-align: center; }
      .coverage-list { display: grid; gap: 7px; margin-top: 13px; }
      .coverage-node { display: block; width: 100%; min-height: 0; margin: 0; padding: 9px; color: var(--text); background: #fafbfd; border: 1px solid var(--border); border-radius: 6px; text-align: left; }
      button.coverage-node { cursor: pointer; }
      button.coverage-node:hover, button.coverage-node:focus-visible { color: var(--text); background: #eef6ff; border-color: var(--accent); }
      .coverage-node.inactive { border-style: dashed; background: #fff7ed; }
      .coverage-node strong { display: block; font-size: 13px; }
      .coverage-node small { color: var(--muted); }
      .coverage-evidence { margin-top: 16px; border-top: 1px solid var(--border); padding-top: 4px; }
      .coverage-evidence ul { padding-left: 18px; }
      .coverage-evidence li { margin: 6px 0; overflow-wrap: anywhere; }
      @media (max-width: 1050px) {
        .document-shell { grid-template-columns: minmax(0, 1fr); height: auto; min-height: calc(100vh - 66px); overflow: visible; }
        .document-workspace, .document-coverage { overflow: visible; }
        .document-coverage { grid-column: 1 / -1; border-top: 1px solid var(--border); border-left: 0; }
      }
      @media (max-width: 700px) {
        .document-shell { display: block; }
        .document-sidebar { border-right: 0; border-bottom: 1px solid var(--border); }
        .workspace-head { display: block; }
        .workspace-summary { justify-content: flex-start; margin-top: 10px; }
        .document-grid { grid-template-columns: 1fr; }
      }
    </style>
    <section class="document-shell">
      <section class="document-workspace">
        <div class="document-selector">
          <p><a href="/">Volver a proyectos</a></p>
          <p class="eyebrow">Mapa documental editable · __TERMINAL_COUNT__ trámites</p>
          <div class="document-selector-row">
            <label for="document-terminal-search">Buscar o seleccionar trámite</label>
            <input id="document-terminal-search" type="search" role="combobox"
                aria-autocomplete="list" aria-expanded="false"
                aria-controls="document-terminal-suggestions"
                placeholder="Escribe parte del nombre del trámite">
            <button class="document-selector-toggle" id="document-selector-toggle"
                type="button" aria-label="Mostrar trámites">⌄</button>
            <div class="document-suggestions" id="document-terminal-suggestions"
                role="listbox" hidden></div>
          </div>
        </div>
        <div id="document-message" hidden></div>
        <div class="workspace-head">
          <div>
            <p class="eyebrow">Auditoría documental · __PROJECT_NAME__</p>
            <h2 id="document-node-title"></h2>
            <a id="document-node-source" href="#" target="_blank" rel="noreferrer">Abrir fuente oficial</a>
            <div class="workspace-navigation">
              <button id="document-previous-node" type="button">← Anterior</button>
              <button id="document-next-node" type="button">Siguiente →</button>
            </div>
          </div>
          <div class="workspace-summary" id="document-node-summary"></div>
        </div>
        <div class="terminal-focus">
          <strong id="document-focus-title"></strong>
          <small id="document-focus-status"></small>
        </div>
        <div id="document-resource-sections"></div>
      </section>

      <aside class="document-coverage" id="document-coverage-panel">
        <div class="coverage-empty">
          <div>
            <h2>Cobertura del recurso</h2>
            <p>Selecciona un recurso consolidado para ver todos los trámites que lo utilizan.</p>
          </div>
        </div>
      </aside>
    </section>

    <script>
      const documentMap = __DOCUMENT_MAP_JSON__;
      const useLabels = {
        process_as_context: "Contexto",
        show_as_link: "Solo link",
        discard: "Descartado",
        review_later: "Revisar después"
      };
      const typeLabels = {
        pdf: "PDF", formulario: "Formulario", agenda: "Agenda",
        normativa: "Normativa", link: "Link", tramite_relacionado: "Trámite relacionado"
      };
      const pageParameters = new URLSearchParams(window.location.search);
      let selectedNodeId = pageParameters.get("node") || documentMap.nodes[0]?.link_id || null;
      let selectedResourceKey = null;

      function escapeHtml(value) {
        return String(value ?? "").replace(/[&<>"']/g, character => ({
          "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
        })[character]);
      }

      function normalizedText(value) {
        return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
      }

      function renderTerminalSuggestions(query = "") {
        const host = document.getElementById("document-terminal-suggestions");
        const normalizedQuery = normalizedText(query.trim());
        const matches = documentMap.nodes.filter(node =>
          !normalizedQuery || normalizedText(node.title).includes(normalizedQuery)
        );
        host.innerHTML = matches.length ? matches.map(node => `
          <button type="button" role="option"
              class="terminal-option ${node.link_id === selectedNodeId ? "selected" : ""}"
              data-node-id="${escapeHtml(node.link_id)}">
            <strong>${escapeHtml(node.title)}</strong>
            <span class="terminal-count">${node.summary.resource_count} recursos</span>
          </button>`).join("") : '<p class="document-empty">No se encontraron trámites.</p>';
        host.querySelectorAll("[data-node-id]").forEach(button => {
          button.addEventListener("click", () => selectNode(button.dataset.nodeId));
        });
      }

      function openTerminalSuggestions() {
        const input = document.getElementById("document-terminal-search");
        renderTerminalSuggestions(input.dataset.editing === "true" ? input.value : "");
        document.getElementById("document-terminal-suggestions").hidden = false;
        input.setAttribute("aria-expanded", "true");
      }

      function closeTerminalSuggestions() {
        document.getElementById("document-terminal-suggestions").hidden = true;
        document.getElementById("document-terminal-search").setAttribute("aria-expanded", "false");
      }

      function selectNode(nodeId) {
        selectedNodeId = nodeId;
        selectedResourceKey = null;
        renderSelectedNode();
        clearCoverage();
        closeTerminalSuggestions();
        const selectedNode = documentMap.nodes.find(item => item.link_id === nodeId);
        const input = document.getElementById("document-terminal-search");
        input.value = selectedNode?.title || "";
        input.dataset.editing = "false";
        const url = new URL(window.location.href);
        url.searchParams.set("node", nodeId);
        url.searchParams.delete("saved");
        url.searchParams.delete("error");
        window.history.replaceState(null, "", url);
        document.querySelector(".document-workspace").scrollTo({ top: 0, behavior: "smooth" });
      }

      function selectAdjacentNode(offset) {
        const index = documentMap.nodes.findIndex(item => item.link_id === selectedNodeId);
        if (index < 0 || !documentMap.nodes.length) return;
        const nextIndex = (index + offset + documentMap.nodes.length) % documentMap.nodes.length;
        selectNode(documentMap.nodes[nextIndex].link_id);
      }

      function renderSelectedNode() {
        const node = documentMap.nodes.find(item => item.link_id === selectedNodeId);
        if (!node) return;
        document.getElementById("document-node-title").textContent = node.title;
        document.getElementById("document-focus-title").textContent = node.title;
        document.getElementById("document-focus-status").textContent = node.is_active
          ? "Nodo terminal activo" : "Nodo terminal inactivo · referencia histórica";
        const source = document.getElementById("document-node-source");
        source.href = node.url || "#";
        source.hidden = !node.url;
        const attention = node.summary.pending_count + node.summary.provisional_count;
        document.getElementById("document-node-summary").innerHTML = `
          <span class="pill">${node.summary.resource_count} recursos</span>
          <span class="pill">${node.summary.shared_count} compartidos</span>
          <span class="pill ${attention ? "inactive" : ""}">${attention ? `${attention} para revisar` : "Sin alertas"}</span>`;

        const active = node.resources.filter(item => item.relation_status === "active" && item.effective_use !== "discard");
        const review = active.filter(item => !item.effective_use || item.effective_use === "review_later" || item.has_conflicting_uses);
        const reviewed = active.filter(item => !review.includes(item));
        const shared = reviewed.filter(item => item.active_source_nodes.length > 1);
        const specificContext = reviewed.filter(item => item.active_source_nodes.length <= 1 && item.effective_use === "process_as_context");
        const links = reviewed.filter(item => item.active_source_nodes.length <= 1 && item.effective_use === "show_as_link");
        const discarded = node.resources.filter(item => item.relation_status === "active" && item.effective_use === "discard");
        const inactive = node.resources.filter(item => item.relation_status === "inactive");
        const sections = [
          ["Documentación compartida", shared],
          ["Documentación específica", specificContext],
          ["Enlaces para el ciudadano", links],
          ["Requiere revisión", review],
          ["Descartados", discarded],
          ["Relaciones inactivas", inactive]
        ].filter(([, resources]) => resources.length);
        document.getElementById("document-resource-sections").innerHTML = sections.length
          ? sections.map(([title, resources]) => resourceSection(title, resources)).join("")
          : '<p class="document-empty">No hay recursos asociados a este nodo.</p>';
        document.querySelectorAll("[data-resource-key]").forEach(button => {
          button.addEventListener("click", () => selectResource(button.dataset.resourceKey));
        });
      }

      function resourceSection(title, resources) {
        return `<section class="document-section">
          <div class="document-section-head"><h3>${escapeHtml(title)}</h3><span class="terminal-count">${resources.length}</span></div>
          <div class="document-grid">${resources.map(resourceCard).join("")}</div>
        </section>`;
      }

      function resourceCard(resource) {
        const coverageNodeCount = resource.active_source_nodes.length + resource.inactive_source_nodes.length;
        const selectable = resource.is_consolidated && coverageNodeCount > 1;
        return `<div class="document-item ${resource.canonical_resource_key === selectedResourceKey ? "selected" : ""}">
          <strong>${escapeHtml(resource.display_name)}</strong>
          <span class="pill">${escapeHtml(typeLabels[resource.resource_type] || resource.resource_type)}</span>
          <span class="pill">${escapeHtml(useLabels[resource.effective_use] || "Sin decisión")}</span>
          <span class="pill">${resource.is_consolidated ? "Consolidado" : "Provisional"}</span>
          ${resource.active_source_nodes.length > 1 ? `<p>Compartido por ${resource.active_source_nodes.length} trámites</p>` : ""}
          ${resource.canonical_url ? `<a class="document-resource-link" href="${escapeHtml(resource.canonical_url)}" target="_blank" rel="noreferrer">Abrir recurso</a>` : '<p>Sin URL disponible</p>'}
          ${selectable ? `<button class="document-coverage-action" type="button" data-resource-key="${escapeHtml(resource.canonical_resource_key)}">Ver cobertura</button>` : ""}
          ${resourceEdit(resource.node_appearances)}
          <details><summary>Ver evidencia</summary>
            ${resource.appearance_count} apariciones · clave ${escapeHtml(resource.canonical_resource_key)}
          </details>
        </div>`;
      }

      function resourceEdit(appearances) {
        if (!appearances.length) return "";
        const appearance = appearances[0];
        const action = `/projects/${encodeURIComponent(documentMap.project_id)}/document-map/resources/${encodeURIComponent(appearance.source_link_id)}/${encodeURIComponent(appearance.resource_id)}`;
        const options = [
          ["process_as_context", "Usar como contexto"],
          ["show_as_link", "Mostrar solo como enlace"],
          ["review_later", "Revisar después"],
          ["discard", "Descartar de este trámite"]
        ].map(([value, label]) => `<option value="${value}" ${appearance.effective_use === value ? "selected" : ""}>${label}</option>`).join("");
        return `<details class="document-edit"><summary>Editar clasificación</summary>
          <form method="post" action="${escapeHtml(action)}">
            <span class="document-local-note">El cambio afecta solo a este trámite. No elimina ni modifica el recurso compartido.</span>
            ${appearances.map(item => `<input type="hidden" name="resource_id" value="${escapeHtml(item.resource_id)}">`).join("")}
            ${appearances.length > 1 ? `<span class="document-local-note">Se aplicará a ${appearances.length} apariciones equivalentes de este recurso en el trámite.</span>` : ""}
            <select name="use" aria-label="Clasificación del recurso">${options}</select>
            <input name="notes" type="text" placeholder="Nota opcional sobre el cambio">
            <button type="submit">Guardar cambio</button>
          </form>
        </details>`;
      }

      function selectResource(resourceKey) {
        selectedResourceKey = resourceKey;
        renderSelectedNode();
        renderCoverage(documentMap.resources[resourceKey]);
      }

      function renderCoverage(resource) {
        if (!resource) return clearCoverage();
        const panel = document.getElementById("document-coverage-panel");
        panel.innerHTML = `
          <p class="eyebrow">${resource.is_consolidated ? "Recurso canónico" : "Identidad provisional"}</p>
          <h2>${escapeHtml(resource.display_name)}</h2>
          <p class="muted">${escapeHtml(useLabels[resource.effective_use] || "Sin decisión")} · ${resource.appearance_count} apariciones</p>
          ${resource.canonical_url ? `<p><a href="${escapeHtml(resource.canonical_url)}" target="_blank" rel="noreferrer">Abrir recurso</a></p>` : ""}
          <h3>Trámites vinculados · ${resource.active_source_nodes.length}</h3>
          <div class="coverage-list">${coverageNodes(resource.active_source_nodes, false)}</div>
          ${resource.inactive_source_nodes.length ? `<h3>Relaciones inactivas · ${resource.inactive_source_nodes.length}</h3><div class="coverage-list">${coverageNodes(resource.inactive_source_nodes, true)}</div>` : ""}
          <details class="coverage-evidence"><summary>Ver apariciones que sustentan el recurso</summary>
            <ul>${resource.appearance_sources.map(source => `<li>${escapeHtml(source.title || source.url || source.appearance_id)} · ${escapeHtml(source.source_link_id)}</li>`).join("")}</ul>
          </details>`;
        panel.querySelectorAll("[data-coverage-node]").forEach(button => {
          button.addEventListener("click", () => selectNode(button.dataset.coverageNode));
        });
      }

      function coverageNodes(nodes, inactive) {
        if (!nodes.length) return '<p class="document-empty">No hay trámites en este estado.</p>';
        return nodes.map(node => `<button type="button" class="coverage-node ${inactive ? "inactive" : ""}" data-coverage-node="${escapeHtml(node.link_id)}">
          <strong>${inactive ? "○" : "✓"} ${escapeHtml(node.title)}</strong>
          <small>${inactive ? "Relación inactiva" : "Relación activa"}</small>
        </button>`).join("");
      }

      function clearCoverage() {
        document.getElementById("document-coverage-panel").innerHTML = `
          <div class="coverage-empty"><div><h2>Cobertura del recurso</h2>
          <p>Selecciona un recurso consolidado para ver todos los trámites que lo utilizan.</p></div></div>`;
      }

      const terminalSearch = document.getElementById("document-terminal-search");
      terminalSearch.addEventListener("focus", () => {
        terminalSearch.dataset.editing = "true";
        terminalSearch.select();
        openTerminalSuggestions();
      });
      terminalSearch.addEventListener("input", () => {
        terminalSearch.dataset.editing = "true";
        openTerminalSuggestions();
      });
      terminalSearch.addEventListener("keydown", event => {
        const options = [...document.querySelectorAll(".terminal-option")];
        const focused = document.activeElement.closest?.(".terminal-option");
        if (event.key === "Escape") closeTerminalSuggestions();
        if (event.key === "ArrowDown" && options.length) {
          event.preventDefault();
          (focused ? options[(options.indexOf(focused) + 1) % options.length] : options[0]).focus();
        }
        if (event.key === "Enter" && options.length) {
          event.preventDefault();
          options[0].click();
        }
      });
      document.getElementById("document-selector-toggle").addEventListener("click", () => {
        terminalSearch.dataset.editing = "true";
        terminalSearch.focus();
        openTerminalSuggestions();
      });
      document.addEventListener("click", event => {
        if (!event.target.closest(".document-selector-row")) closeTerminalSuggestions();
      });
      document.getElementById("document-previous-node").addEventListener("click", () => selectAdjacentNode(-1));
      document.getElementById("document-next-node").addEventListener("click", () => selectAdjacentNode(1));
      const message = document.getElementById("document-message");
      if (pageParameters.has("saved")) {
        message.className = "document-message";
        message.textContent = "Cambio guardado únicamente para este trámite.";
        message.hidden = false;
      } else if (pageParameters.has("error")) {
        message.className = "document-message error";
        message.textContent = `No se pudo guardar: ${pageParameters.get("error")}`;
        message.hidden = false;
      }
      const initialNode = documentMap.nodes.find(item => item.link_id === selectedNodeId);
      terminalSearch.value = initialNode?.title || "";
      terminalSearch.dataset.editing = "false";
      renderTerminalSuggestions();
      renderSelectedNode();
    </script>
    """
    return (
        template.replace("__DOCUMENT_MAP_JSON__", payload)
        .replace("__PROJECT_NAME__", html_escape(project.get("name")))
        .replace(
            "__TERMINAL_COUNT__",
            str(document_map.get("summary", {}).get("terminal_node_count", 0)),
        )
    )
