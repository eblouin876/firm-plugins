<!-- fragment: block:components/security/cors-lockdown -->

## Setup
Copy the `cors-lockdown/` directory into
`app/core/security/cors_lockdown/`. FastAPI: build a `CORSPolicy` per
environment and call `add_cors(app, policy)` once at app construction.
Django: `pip install django-cors-headers`, add `"corsheaders"` to
`INSTALLED_APPS`, add `django.CORS_MIDDLEWARE_CLASSPATH` to `MIDDLEWARE`
before `CommonMiddleware`, and merge `cors_settings(policy)` into
`settings.py`.

## Maintenance
Review every project's `allow_origins` list at the same cadence as a
dependency allowlist change — an added origin is a trust decision. Never
add `"*"` to work around a `CORSPolicy` construction error; that error is
this component doing its job.
