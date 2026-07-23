"""`manage.py seed_admin <email>` (Stage 5d, #46) — the operator-facing CLI
wrapper around `core.security.auth.stores.seed_admin`, THE real
admin-provisioning path for this block (see that function's own docstring
for why `POST /auth/register` can never be used to self-grant the
`"admin"` role instead: it has no `roles` field on the wire, by design).

Django's own `management command` convention is the natural place for a
one-off, operator-run, server-side provisioning action like this — no
FastAPI equivalent exists in this catalog because that track has no
management-command convention to reuse; `app/core/security/auth/
stores.py:seed_admin` there is only ever called from a script/test
directly, by hand. This command exists purely as a thin CLI shape over
the SAME function, not a second implementation of admin-seeding logic.

Usage:

    python manage.py seed_admin admin@example.com
    python manage.py seed_admin admin@example.com --password 'a real secret'

`--password` is optional — omitted, the command prompts interactively via
`getpass.getpass` (never echoed to the terminal, never left in shell
history the way passing it as a bare positional argument would be); this
mirrors the conventional `createsuperuser`-style UX Django operators
already expect."""

from __future__ import annotations

import getpass

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from core.security.auth.stores import seed_admin


class Command(BaseCommand):
    help = (
        "Creates an admin user (roles=['admin']) -- the real admin-provisioning "
        "path. See core/security/auth/stores.py:seed_admin for why POST "
        "/auth/register can never grant this role on its own."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("email", help="The new admin's email address.")
        parser.add_argument(
            "--password",
            default=None,
            help="The new admin's password. If omitted, prompts interactively (not echoed).",
        )

    def handle(self, *args, **options) -> None:
        email = options["email"]
        password = options["password"] or getpass.getpass("Password: ")
        if not password:
            # Mirrors AuthService/PasswordService's own "a password is
            # required" posture -- an empty password (blank interactive
            # entry, or an explicit `--password ""`) is rejected here,
            # before it ever reaches PasswordService.hash, rather than
            # silently seeding an admin account with no usable credential.
            raise CommandError("A password is required.")
        try:
            user = async_to_sync(seed_admin)(email, password)
        except IntegrityError as exc:
            # The DB-level unique constraint on User.email (core/models.py)
            # is what actually catches a duplicate here -- seed_admin
            # itself does no pre-check read, matching its FastAPI
            # counterpart exactly (see that function's own docstring).
            raise CommandError(f"Could not seed admin -- {email!r} already has an account.") from exc
        self.stdout.write(self.style.SUCCESS(f"Seeded admin user {user.email} ({user.id})"))
