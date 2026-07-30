import argparse

from config import DEFAULT_ACTOR
from config import LINK_ROLE_LABELS
from workflows.link_discovery import discover_candidate_links
from workflows.human_review import save_link_decision
from workflows.auxiliary_link_analysis import analyze_auxiliary_links
from workflows.node_resource_discovery import discover_node_resources
from workflows.pdf_analysis import analyze_project_pdfs
from workflows.project_setup import create_project
from workflows.review_links import build_review_links


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Herramienta asistida para modelar tramites."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init-project",
        help="Crea la estructura inicial de un proyecto de tramite.",
    )
    init_parser.add_argument("--id", required=True, help="ID estable del proyecto.")
    init_parser.add_argument("--name", required=True, help="Nombre visible.")
    init_parser.add_argument("--url", required=True, help="URL inicial del tramite.")
    init_parser.add_argument(
        "--actor",
        default=DEFAULT_ACTOR,
        help="Persona o rol que crea el proyecto.",
    )
    init_parser.add_argument(
        "--description",
        default="",
        help="Descripcion breve del proyecto.",
    )

    discover_parser = subparsers.add_parser(
        "discover-links",
        help="Detecta links candidatos desde la URL inicial de un proyecto.",
    )
    discover_parser.add_argument(
        "--project-id",
        required=True,
        help="ID del proyecto ya creado.",
    )
    discover_parser.add_argument(
        "--actor",
        default=DEFAULT_ACTOR,
        help="Persona o rol que ejecuta la deteccion.",
    )

    review_parser = subparsers.add_parser(
        "build-review-links",
        help="Genera una vista HTML para revisar links candidatos.",
    )
    review_parser.add_argument(
        "--project-id",
        required=True,
        help="ID del proyecto ya creado.",
    )

    decision_parser = subparsers.add_parser(
        "review-link",
        help="Guarda la decision humana sobre un link candidato.",
    )
    decision_parser.add_argument("--project-id", required=True)
    decision_parser.add_argument("--link-id", required=True)
    decision_parser.add_argument(
        "--primary-role",
        required=True,
        choices=sorted(LINK_ROLE_LABELS),
        help="Rol principal interno. Ejemplo: terminal_case.",
    )
    decision_parser.add_argument(
        "--secondary-role",
        action="append",
        default=[],
        choices=sorted(LINK_ROLE_LABELS),
        help="Rol secundario interno. Se puede repetir.",
    )
    decision_parser.add_argument(
        "--confidence",
        default="media",
        choices=["alta", "media", "baja"],
    )
    decision_parser.add_argument("--notes", default="")
    decision_parser.add_argument("--actor", default=DEFAULT_ACTOR)

    resources_parser = subparsers.add_parser(
        "discover-resources",
        help="Explora links aceptados y detecta recursos internos.",
    )
    resources_parser.add_argument(
        "--project-id",
        required=True,
        help="ID del proyecto ya revisado.",
    )
    resources_parser.add_argument(
        "--actor",
        default=DEFAULT_ACTOR,
        help="Persona o rol que ejecuta la exploracion.",
    )

    pdf_parser = subparsers.add_parser(
        "analyze-pdfs",
        help="Analiza PDF revisados y propone grupos determinísticos.",
    )
    pdf_parser.add_argument(
        "--project-id",
        required=True,
        help="ID del proyecto con recursos revisados.",
    )
    pdf_parser.add_argument(
        "--actor",
        default=DEFAULT_ACTOR,
        help="Persona o rol que ejecuta el analisis.",
    )

    auxiliary_links_parser = subparsers.add_parser(
        "analyze-auxiliary-links",
        help="Inventaria enlaces auxiliares no documentales.",
    )
    auxiliary_links_parser.add_argument(
        "--project-id",
        required=True,
        help="ID del proyecto con recursos descubiertos.",
    )
    auxiliary_links_parser.add_argument(
        "--actor",
        default=DEFAULT_ACTOR,
        help="Persona o rol que ejecuta el inventario.",
    )

    args = parser.parse_args()

    if args.command == "init-project":
        result = create_project(
            project_id=args.id,
            name=args.name,
            start_url=args.url,
            actor=args.actor,
            description=args.description,
        )
        print(f"Proyecto creado: {result['project_dir']}")
        print(f"Outputs: {result['output_dir']}")

    if args.command == "discover-links":
        result = discover_candidate_links(
            project_id=args.project_id,
            actor=args.actor,
        )
        print(f"Proyecto: {result['project_id']}")
        print(f"Links candidatos: {result['links_count']}")
        print(f"Archivo: {result['candidate_links_path']}")

    if args.command == "build-review-links":
        result = build_review_links(project_id=args.project_id)
        print(f"Proyecto: {result['project_id']}")
        print(f"Links en vista: {result['links_count']}")
        print(f"HTML: {result['output_path']}")

    if args.command == "review-link":
        result = save_link_decision(
            project_id=args.project_id,
            link_id=args.link_id,
            primary_role=args.primary_role,
            secondary_roles=args.secondary_role,
            confidence=args.confidence,
            notes=args.notes,
            actor=args.actor,
        )
        print(f"Proyecto: {result['project_id']}")
        print(f"Link revisado: {result['link_id']}")
        print(f"Rol principal: {result['primary_role']}")
        print(f"Roles secundarios: {result['secondary_roles']}")
        print(f"Estado revision: {result['review_status']}")
        print(f"Archivo: {result['human_review_path']}")

    if args.command == "discover-resources":
        result = discover_node_resources(
            project_id=args.project_id,
            actor=args.actor,
        )
        print(f"Proyecto: {result['project_id']}")
        print(f"Links aceptados explorados: {result['accepted_links_count']}")
        print(f"Recursos internos encontrados: {result['resources_count']}")
        print(f"Recursos descartados por reglas: {result['discarded_resources_count']}")
        print(f"Archivo: {result['node_resources_path']}")

    if args.command == "analyze-pdfs":
        result = analyze_project_pdfs(
            project_id=args.project_id,
            actor=args.actor,
        )
        print(f"Proyecto: {result['project_id']}")
        print(f"Apariciones PDF seleccionadas: {result['appearance_count']}")
        print(f"PDF analizados: {result['analyzed_count']}")
        print(f"Errores: {result['error_count']}")
        print(f"No intentados: {result['not_attempted_count']}")
        print(f"Grupos propuestos: {result['proposed_group_count']}")
        print(f"Archivo: {result['pdf_analysis_path']}")

    if args.command == "analyze-auxiliary-links":
        result = analyze_auxiliary_links(
            project_id=args.project_id,
            actor=args.actor,
        )
        print(f"Proyecto: {result['project_id']}")
        print(f"Apariciones no documentales: {result['appearance_count']}")
        print(f"Documentos excluidos: {result['excluded_document_count']}")
        print(f"Grupos por URL exacta: {result['exact_group_count']}")
        print(
            "Equivalencias normalizadas: "
            f"{result['normalized_group_count']}"
        )
        print(f"Agendas candidatas: {result['agenda_group_count']}")
        print(f"Archivo: {result['analysis_path']}")


if __name__ == "__main__":
    main()
