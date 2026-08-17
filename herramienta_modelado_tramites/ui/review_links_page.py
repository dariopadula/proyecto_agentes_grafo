import json
from pathlib import Path
from typing import Any

from config import LINK_ROLE_LABELS
from core.html_utils import html_escape


def save_review_links_html(
    project: dict[str, Any],
    candidate_links: dict[str, Any],
    human_review: dict[str, Any],
    output_path: Path,
) -> None:
    """Genera una vista HTML local para revisar links candidatos."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _build_html(project, candidate_links, human_review),
        encoding="utf-8",
    )


def _build_html(
    project: dict[str, Any],
    candidate_links: dict[str, Any],
    human_review: dict[str, Any],
) -> str:
    decisions_by_link = {
        decision.get("link_id"): decision
        for decision in human_review.get("decisions", [])
    }
    links = []
    for link in candidate_links.get("links", []):
        decision = decisions_by_link.get(link.get("link_id"), {})
        links.append(
            {
                **link,
                "primary_role": decision.get(
                    "primary_role",
                    decision.get("human_role", ""),
                ),
                "secondary_roles": decision.get("secondary_roles", []),
                "confidence": decision.get("confidence", ""),
                "notes": decision.get("notes", ""),
            }
        )

    payload = {
        "project": project,
        "links": links,
        "roles": [
            {
                "code": code,
                "label": label,
            }
            for code, label in sorted(LINK_ROLE_LABELS.items())
        ],
    }
    data_json = json.dumps(payload, ensure_ascii=False)

    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Revision de links - {html_escape(project.get("name"))}</title>
  <style>
    :root {{
      --bg: #f5f7fb;
      --panel: #ffffff;
      --text: #1f2328;
      --muted: #667085;
      --border: #d0d7de;
      --blue: #0969da;
      --green: #1a7f37;
      --orange: #9a6700;
      --red: #b42318;
    }}

    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      min-height: 100vh;
      font-family: Arial, Helvetica, sans-serif;
      color: var(--text);
      background: var(--bg);
    }}

    header {{
      position: sticky;
      top: 0;
      z-index: 2;
      border-bottom: 1px solid var(--border);
      background: var(--panel);
      padding: 14px 18px;
    }}

    h1 {{
      margin: 0 0 4px;
      font-size: 20px;
    }}

    .source {{
      margin: 0;
      color: var(--muted);
      font-size: 13px;
      overflow-wrap: anywhere;
    }}

    .toolbar {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 14px;
    }}

    input, select, button {{
      height: 34px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      font: inherit;
      font-size: 13px;
    }}

    input {{
      width: min(360px, 100%);
      padding: 0 10px;
    }}

    select {{
      min-width: 180px;
      padding: 0 8px;
    }}

    button {{
      padding: 0 12px;
      cursor: pointer;
    }}

    button:hover {{ background: #eef1f4; }}

    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 18px;
    }}

    .stats {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 16px;
    }}

    .stat {{
      padding: 12px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--panel);
    }}

    .stat strong {{
      display: block;
      font-size: 22px;
      line-height: 1;
    }}

    .stat span {{
      display: block;
      margin-top: 6px;
      color: var(--muted);
      font-size: 12px;
    }}

    .notice {{
      margin-bottom: 16px;
      padding: 12px;
      border: 1px solid #fedf89;
      border-radius: 6px;
      background: #fffaeb;
      color: #7a4d00;
      font-size: 13px;
      line-height: 1.45;
    }}

    .links {{
      display: grid;
      gap: 10px;
    }}

    .link-card {{
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--panel);
      padding: 14px;
    }}

    .link-card.hidden {{ display: none; }}

    .link-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: flex-start;
    }}

    .link-title {{
      margin: 0 0 6px;
      font-size: 16px;
      line-height: 1.25;
    }}

    .link-title a {{
      color: var(--blue);
      text-decoration: none;
    }}

    .link-title a:hover {{ text-decoration: underline; }}

    .badge {{
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 2px 8px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: #f6f8fa;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }}

    .meta {{
      display: grid;
      grid-template-columns: 140px minmax(0, 1fr);
      gap: 6px 10px;
      margin: 10px 0;
      font-size: 13px;
    }}

    .meta div:nth-child(odd) {{ color: var(--muted); }}

    .url {{
      overflow-wrap: anywhere;
      color: var(--muted);
    }}

    .review-row {{
      display: grid;
      grid-template-columns: minmax(180px, 240px) minmax(160px, 1fr);
      gap: 10px;
      margin-top: 12px;
      align-items: start;
    }}

    textarea {{
      width: 100%;
      min-height: 62px;
      resize: vertical;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px;
      font: inherit;
      font-size: 13px;
    }}

    .muted {{ color: var(--muted); }}

    .secondary-roles {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
      font-size: 13px;
    }}

    .secondary-roles label {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-height: 28px;
      padding: 3px 8px;
      border: 1px solid var(--border);
      border-radius: 999px;
      background: #f6f8fa;
    }}

    .secondary-roles input {{
      width: 14px;
      height: 14px;
    }}

    @media (max-width: 760px) {{
      .stats {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}

      .link-head,
      .review-row {{
        display: grid;
        grid-template-columns: 1fr;
      }}

      .meta {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Revision de links: {html_escape(project.get("name"))}</h1>
    <p class="source">{html_escape(project.get("start_url"))}</p>
    <div class="toolbar">
      <input id="search" type="search" placeholder="Buscar por titulo o URL">
      <select id="role-filter">
        <option value="">Todos los roles</option>
      </select>
      <select id="status-filter">
        <option value="">Todos los estados</option>
        <option value="pending_review">Pendientes</option>
      </select>
      <button type="button" id="clear">Limpiar filtros</button>
    </div>
  </header>
  <main>
    <section class="stats" id="stats"></section>
    <section class="notice">
      Esta vista es de diagnostico. Los selectores y notas ayudan a revisar,
      pero esta version todavia no guarda cambios automaticamente en
      <code>human_review.json</code>.
    </section>
    <section class="links" id="links"></section>
  </main>

  <script>
    const DATA = {data_json};
    const linksContainer = document.getElementById("links");
    const statsContainer = document.getElementById("stats");
    const searchInput = document.getElementById("search");
    const roleFilter = document.getElementById("role-filter");
    const statusFilter = document.getElementById("status-filter");

    for (const role of DATA.roles) {{
      const option = document.createElement("option");
      option.value = role.code;
      option.textContent = role.label;
      roleFilter.appendChild(option);
    }}

    renderStats();
    renderLinks();

    searchInput.addEventListener("input", applyFilters);
    roleFilter.addEventListener("change", applyFilters);
    statusFilter.addEventListener("change", applyFilters);
    document.getElementById("clear").addEventListener("click", () => {{
      searchInput.value = "";
      roleFilter.value = "";
      statusFilter.value = "";
      applyFilters();
    }});

    function renderStats() {{
      const total = DATA.links.length;
      const pending = DATA.links.filter(link => link.status === "pending_review").length;
      const reviewed = DATA.links.filter(link => link.primary_role).length;
      const unreviewed = total - reviewed;
      statsContainer.innerHTML = `
        <div class="stat"><strong>${{total}}</strong><span>Links candidatos</span></div>
        <div class="stat"><strong>${{pending}}</strong><span>Pendientes</span></div>
        <div class="stat"><strong>${{reviewed}}</strong><span>Con rol humano</span></div>
        <div class="stat"><strong>${{unreviewed}}</strong><span>Sin revisar</span></div>
      `;
    }}

    function renderLinks() {{
      linksContainer.innerHTML = DATA.links.map(link => cardHtml(link)).join("");
      applyFilters();
    }}

    function cardHtml(link) {{
      const selectedRole = link.primary_role || "";
      const roleOptions = [`<option value="">Sin clasificar</option>`]
        .concat(DATA.roles.map(role => (
          `<option value="${{escapeAttr(role.code)}}" ${{role.code === selectedRole ? "selected" : ""}}>${{escapeHtml(role.label)}}</option>`
        )))
        .join("");
      const secondaryRoles = Array.isArray(link.secondary_roles)
        ? link.secondary_roles
        : [];
      const secondaryRoleOptions = DATA.roles.map(role => `
        <label>
          <input type="checkbox" value="${{escapeAttr(role.code)}}" ${{secondaryRoles.includes(role.code) ? "checked" : ""}}>
          ${{escapeHtml(role.label)}}
        </label>
      `).join("");

      return `
        <article class="link-card" data-search="${{escapeAttr(searchText(link))}}" data-role="${{escapeAttr(selectedRole)}}" data-status="${{escapeAttr(link.status || "")}}">
          <div class="link-head">
            <div>
              <h2 class="link-title"><a href="${{escapeAttr(link.url)}}" target="_blank" rel="noreferrer">${{escapeHtml(link.title || link.url)}}</a></h2>
              <div class="url">${{escapeHtml(link.url)}}</div>
            </div>
            <span class="badge">${{escapeHtml(link.link_id)}}</span>
          </div>
          <div class="meta">
            <div>Texto link</div><div>${{escapeHtml(link.anchor_text || "")}}</div>
            <div>Contexto</div><div>${{escapeHtml(link.source_context || "")}}</div>
            <div>Categoría de URL</div><div>${{escapeHtml(link.url_category || "No disponible")}}</div>
            <div>Motivo</div><div>${{escapeHtml(link.detection_reason || "")}}</div>
            <div>Estado</div><div>${{escapeHtml(link.status || "")}}</div>
          </div>
          <div class="review-row">
            <label>
              <span class="muted">Rol principal</span><br>
              <select>${{roleOptions}}</select>
            </label>
            <label>
              <span class="muted">Notas</span><br>
              <textarea placeholder="Comentario de revision">${{escapeHtml(link.notes || "")}}</textarea>
            </label>
          </div>
          <div class="muted" style="margin-top: 12px;">Roles secundarios</div>
          <div class="secondary-roles">${{secondaryRoleOptions}}</div>
        </article>
      `;
    }}

    function applyFilters() {{
      const query = searchInput.value.trim().toLowerCase();
      const role = roleFilter.value;
      const status = statusFilter.value;

      document.querySelectorAll(".link-card").forEach(card => {{
        const matchesQuery = !query || card.dataset.search.includes(query);
        const matchesRole = !role || card.dataset.role === role;
        const matchesStatus = !status || card.dataset.status === status;
        card.classList.toggle("hidden", !(matchesQuery && matchesRole && matchesStatus));
      }});
    }}

    function searchText(link) {{
      return [link.link_id, link.title, link.url, link.anchor_text, link.source_context, link.url_category]
        .join(" ")
        .toLowerCase();
    }}

    function escapeHtml(value) {{
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }}

    function escapeAttr(value) {{
      return escapeHtml(value).replaceAll("`", "&#096;");
    }}

    function roleLabel(code) {{
      const role = DATA.roles.find(item => item.code === code);
      return role ? role.label : code;
    }}
  </script>
</body>
</html>
"""
