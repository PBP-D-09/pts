# AGENTS.md — SustainaBowl (pts + pas)

Instructions for any AI coding agent (Claude Code, Cursor, Copilot, Aider,
etc.) working on either SustainaBowl repository. This exact file is kept
identical in both repos — `pts/` (Django web) and `pas/` (Flutter mobile) —
so whichever one you're cloned into, you have full context on both sides of
the integration. If your harness also reads a tool-specific file
(`CLAUDE.md`, `.cursorrules`, ...), these rules take precedence over your
harness's defaults.

You are currently in **`pts/`** (the Django web repo). See the "pts/" section
below for repo-specific rules; the "pas/" section describes the sibling repo
for context only — you won't find those files here.

## Git — non-negotiable, applies in both repos

- **Never run a state-changing git command on your own initiative**: no
  `git commit`, `git add -A`/`git add .`, `git push`, `git merge`,
  `git rebase`, `git reset --hard`, `git checkout --`, `git clean -f`, or
  branch deletion. Prepare the diff, explain it, and stop — the human
  developer reviews and commits it themselves.
- Only commit/push if the developer's message in that specific turn
  explicitly asks you to — approval from an earlier turn doesn't carry
  forward.
- Stay on the current feature branch. Never push directly to `main` (or
  `staging`, in `pts/`) unless explicitly told to. Never force-push, never
  amend a commit that's already pushed — create a new commit instead.
- In `pts/` specifically: pushes to `main`/`staging` trigger
  `.github/workflows/deploy.yml` and `pws.yml` (auto-deploy), and `ci.yml`
  runs on every push to those branches. An unreviewed auto-commit can ship
  straight to the live site.
- Never commit secrets or generated artifacts: in `pts/` that means `.env`,
  `db.sqlite3`, `media/`; in `pas/` that means build output, keystores,
  `.env`-style secrets, and the release APK itself. Check `git status` after
  any broad `git add` before handing off.

## How the two repos fit together

- `pts/` is the Django 5.2 web app "SustainaBowl" (Proyek Tengah Semester).
  It owns all the data and is the single source of truth.
- `pas/` is the Flutter mobile client (Proyek Akhir Semester). It never
  holds its own data — it's a pure client over Django REST Framework
  endpoints exposed by `pts/`. Never add static/mock data in `pas/` as a
  stand-in for a real API call.
- Integration contract: `pas/` calls `pts/` over HTTP through endpoints
  mounted under `api/v1/` in `pts/config/urls.py`. Current live endpoints and
  their status are tracked in `pas/README.md` under "Integrasi Data" — check
  there rather than assuming a module's endpoint exists.
- Testing `pas/` against a local `pts/` dev server from an Android emulator:
  use `API_BASE_URL=http://10.0.2.2:8000`, not `localhost` (which resolves
  to the emulator itself).

## Module ownership (same split in both repos)

| Modul    | Anggota                      |
| -------- | ----------------------------- |
| accounts | Joachim Susatiyo               |
| catalog  | Muhammad Zaky Robbani           |
| orders   | Anantha Kamal Eirian             |
| map      | Awiddy Munaya Rajanadoli          |
| reviews  | I Komang Arka Darma Laksana        |

Don't edit another person's module/feature folder in either repo unless they
ask you to, or the change is explicitly shared infra (see each repo's
section below for what counts as infra there).

---

## `pts/` (Django web) — you are here

One Django app under `apps/` per teammate (table above). Shared infra apps
(`designsystem`, `landing`, `theme`) and `config/` files aren't owned by one
person.

### Django REST Framework convention

DRF was added specifically to serve the Flutter app. Follow the pattern
already fully built out in `apps/accounts/` when adding your module's
endpoints:

- New files per app: `serializers.py`, `api_views.py`, `api_urls.py`, and
  (if you need role/ownership checks) `permissions.py`. **Do not** add DRF
  code into the existing `views.py`/`urls.py` — those still serve the
  hand-rolled `JsonResponse` endpoints the web frontend depends on, and must
  keep working unmodified.
- Mount each app's `api_urls.py` under the single
  `path("api/v1/", include("apps.<app>.api_urls"))` line in `config/urls.py`
  — each app's own `api_urls.py` prefixes its paths with its own module name
  internally (see `apps/accounts/api_urls.py`: every path starts with
  `accounts/...`, so the full path ends up `/api/v1/accounts/...`).
- Views are **function-based `@api_view`**, not class-based
  generics/ViewSets — matches the style already used in `portfolio/`'s
  `apps/home/api_views.py`. Every view explicitly declares
  `@authentication_classes([TokenAuthentication])` and `@permission_classes([...])`
  rather than relying only on the global default.
- Authentication is **Token-based**
  (`rest_framework.authtoken.TokenAuthentication`) — login/register return a
  `token` string, every subsequent request sends
  `Authorization: Token <key>`. No session cookies, no CSRF handling needed
  on API routes.
- `REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]` is `IsAuthenticated` in
  `settings.py` — this is the safe default now that real endpoints exist.
  Endpoints that must be public (register, login) mark themselves
  explicitly with `@permission_classes([AllowAny])`; don't rely on changing
  the global default again.
- Role-scoped endpoints (customer-only / tenant-only) use custom permission
  classes in `apps/accounts/permissions.py` (`IsCustomer`, `IsTenant`) —
  reuse that pattern (and `CustomUser.is_customer`/`is_tenant`) instead of
  writing ad-hoc `if request.user.account_type == ...` checks inline.
- Reuse the existing `selectors.py`/`services.py` layer for business logic —
  API views should stay thin (validate input via a serializer, call a
  selector/service, return a `Response`). Don't duplicate query or mutation
  logic that already exists there.
- Only serialize fields that are safe to expose publicly (never `password`
  or other sensitive fields) — see `CustomUserSerializer` for the pattern.

### Running / verifying

```bash
devenv shell                                   # Python 3.14 + uv env
uv sync                                        # after touching pyproject.toml
python manage.py makemigrations --check --dry-run   # before calling a models.py change done
python manage.py runserver
curl -s http://localhost:8000/api/v1/<module>/<path>/   # sanity-check new endpoints
```

---

## `pas/` (Flutter mobile) — sibling repo, context only

Each `lib/features/<module>/` folder is owned by one teammate (table above).
Don't edit another person's feature folder unless they ask you to, or the
change is explicitly shared infra (`lib/core/`, `lib/app.dart`).

### Architecture conventions already in place

- Clean Architecture per feature:
  `data/{datasources,models,repositories}`, `domain/{entities,repositories,usecases}`,
  `presentation/{pages,providers,widgets}`. Keep new code for your module
  inside your own feature folder, in the matching layer.
- Navigation: `lib/core/navigation/home_shell.dart` is the single
  `BottomNavigationBar` shell wiring Landing + the 5 module pages via
  `IndexedStack`. It's shared infra — if a module needs a new top-level tab
  or a different icon/order, coordinate with the group instead of editing it
  unilaterally.
- Networking: `lib/core/network/api_client.dart` is the abstract `ApiClient`
  contract; `http_api_client.dart` is the concrete `package:http`
  implementation; `lib/core/config/app_config.dart` holds `apiBaseUrl`
  (override via `--dart-define=API_BASE_URL=...`). Call the Django API
  through these, not by calling `package:http` directly from a page/provider.
- Platforms: Android, iOS, Web, Windows, Linux are all scaffolded
  (`flutter create --platforms=...`). Don't hand-edit generated platform
  runner code (`android/`, `ios/`, `windows/`, `linux/`, `web/`) beyond
  cosmetic branding (app name/title/icon) unless you know exactly what
  you're changing — regenerate via `flutter create` instead of patching by
  hand where possible.
- Building `linux` desktop requires `pkgs.gtk3` + `pkgs.pkg-config` in
  `devenv.nix` (already added) — without them `flutter build linux` fails at
  the CMake configure step.

### Running / verifying

```bash
devenv shell
flutter pub get
flutter analyze      # must stay clean
flutter test         # must stay green
flutter run
```

Testing against the Django dev server from an Android emulator: use
`API_BASE_URL=http://10.0.2.2:8000`, not `localhost` (which resolves to the
emulator itself).

---

## Scope discipline

Don't add features, refactors, or abstractions beyond what's asked, in
either repo. This is a graded group assignment with per-module ownership
and checkpoint deadlines — unscoped changes create merge conflicts and
confuse grading of individual contribution.

## AI disclosure

The team discloses AI-assisted development in `pts/README.md` ("AI
Disclosure"); the same standard applies to work in `pas/`. Any AI-authored
code must be reviewed, understood, and tested by the module owner before
it's relied on — don't treat agent output as finished work.
