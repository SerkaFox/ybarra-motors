from __future__ import annotations

import argparse

from .generator import generate_all_pages
from .importer import import_existing_site
from .storage import initialize_database, update_password


def main() -> None:
    parser = argparse.ArgumentParser(description="Ybarra Motor mini CMS utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Initialize DB and import the current site")
    subparsers.add_parser("build", help="Generate static pages from CMS data")
    subparsers.add_parser("reimport", help="Reimport current HTML files into the CMS DB")

    set_password = subparsers.add_parser("set-password", help="Change the admin password")
    set_password.add_argument("password", help="New password for admin")

    args = parser.parse_args()

    if args.command == "init":
        initialize_database()
        import_existing_site(force=False)
        generate_all_pages()
        return

    if args.command == "build":
        initialize_database()
        generate_all_pages()
        return

    if args.command == "reimport":
        initialize_database()
        import_existing_site(force=True)
        generate_all_pages()
        return

    if args.command == "set-password":
        initialize_database()
        update_password("admin", args.password)


if __name__ == "__main__":
    main()
