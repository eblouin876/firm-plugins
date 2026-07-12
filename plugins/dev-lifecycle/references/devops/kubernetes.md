<!--
library: kubernetes
versions-covered: "Kubernetes 1.3x"   # verified current stable minor: 1.36 (1.36.2, three-release window 1.34–1.36)
last-verified: 2026-07-12
provenance: auto-generated (pending review)
sources:
  - https://kubernetes.io/releases/
  - https://kubernetes.io/docs/reference/using-api/deprecation-guide/
  - https://kubernetes.io/docs/setup/release/version-skew-policy/
  - https://kubernetes.io/docs/concepts/security/pod-security-admission/
  - https://kubernetes.io/docs/concepts/security/pod-security-standards/
  - https://kubernetes.io/docs/concepts/services-networking/network-policies/
  - https://pypi.org/project/kubernetes/
-->

# Kubernetes conventions

Writing correct, secure, production-grade K8s manifests and the deploy workflow. Load when you detect a `k8s/` dir, `*.yaml` with `apiVersion`/`kind`, Helm charts, or the `kubernetes` Python client. This is the orchestration target for a multi-tenant app — isolation is the driving concern. Project conventions and the cluster's actual version override anything here.

## Contents
- Version check (do this first)
- Workload objects (Deployment / StatefulSet / Job / CronJob)
- Pod essentials (always required in prod)
- Config & secrets
- Networking & multi-tenant isolation
- Namespaces, RBAC, ServiceAccounts
- Storage
- Rollouts, PDB, autoscaling
- Managing manifests (Kustomize / Helm / GitOps)
- The Python `kubernetes` client
- Observability & debugging
- Security baseline (Pod Security Admission)

## Version check (do this first)
- Current stable is **1.36**; upstream supports the latest three minors (~1.34–1.36). Pin manifests to **GA API groups**, never removed betas.
- GA groups to use: `apps/v1` (workloads), `batch/v1` (Job/CronJob), `networking.k8s.io/v1` (Ingress, NetworkPolicy), `policy/v1` (PodDisruptionBudget), `autoscaling/v2` (HPA), `rbac.authorization.k8s.io/v1`, `v1` (Pod/Service/ConfigMap/Secret/PVC).
- Removed betas that still appear in stale manifests: `extensions/v1beta1` + `apps/v1beta*` (workloads/Ingress), `batch/v1beta1` CronJob, `policy/v1beta1` PDB, `autoscaling/v2beta*`, and `PodSecurityPolicy` (gone since 1.25 → use Pod Security Admission). `kubectl explain <kind>` shows the served version; `kubectl api-resources` lists what the cluster serves.
- Respect the **version skew policy**: kubelet may trail kube-apiserver by up to 3 minors, `kubectl` within ±1 minor; upgrade one minor at a time, never skip.

## Workload objects
- **Deployment** — stateless, interchangeable pods: the web/API app and worker containers. Default choice.
- **StatefulSet** — stable identity + per-pod storage: Postgres, Redis. Gives ordered `name-0..n` pods and per-pod PVCs via `volumeClaimTemplates`. In practice prefer a managed DB/cache; self-hosting stateful data in-cluster is a real operational burden.
- **Job** — run-to-completion batch (migrations, backfills). **CronJob** — scheduled Jobs; set `concurrencyPolicy: Forbid` for non-overlapping runs and `startingDeadlineSeconds`.
- Anti-pattern: bare `Pod` manifests in prod (no rescheduling/rollout), or a Deployment for something that needs stable identity/storage.

## Pod essentials (always required in prod)
Every container spec MUST have all of these — a manifest missing any is not production-ready:
- **`resources.requests` AND `resources.limits`** (cpu+memory). Requests drive scheduling; memory limit prevents a tenant OOMing the node. Set memory request == limit to avoid overcommit surprises.
- **Probes**: `readinessProbe` (gates traffic — remove from Service on failure), `livenessProbe` (restart if wedged), `startupProbe` (protects slow starters from the liveness probe). Don't point liveness at a deep dependency check — it causes restart storms.
- **`securityContext`**: `runAsNonRoot: true`, `runAsUser`/`runAsGroup` non-zero, `readOnlyRootFilesystem: true` (mount an `emptyDir` for scratch), `allowPrivilegeEscalation: false`, `capabilities.drop: ["ALL"]`, `seccompProfile.type: RuntimeDefault`.
- **Pinned images**: reference by digest (`repo@sha256:…`) or an immutable tag, never `:latest`. Set `imagePullPolicy: IfNotPresent` with a real tag. Ties to containers.md image hygiene.
- Also: `terminationGracePeriodSeconds` long enough to drain, and handle SIGTERM in the app.

## Config & secrets
- **ConfigMap** for non-sensitive config; **Secret** for credentials — but a Secret is only **base64, not encrypted**. Anyone with `get secret` RBAC or etcd access reads it.
- Do not commit raw Secret manifests. Use **Sealed Secrets** or **External Secrets Operator** (pulling from Vault/AWS Secrets Manager/SSM) so git holds only ciphertext or a reference. Enable etcd encryption-at-rest on the cluster. See the infra secrets reference for the canonical secret-management story.
- Mount config as env or files; roll pods on change (checksum annotation, or a tool like Reloader) since env/volume updates aren't picked up live for env vars.

## Networking & multi-tenant isolation
- **Service** types: `ClusterIP` (internal, default), `NodePort` (rarely direct), `LoadBalancer` (cloud LB), plus **Ingress** (`networking.k8s.io/v1`) for HTTP routing/TLS via an ingress controller.
- **NetworkPolicy is mandatory for multi-tenant isolation.** Apply a **default-deny** ingress (and egress) policy per tenant namespace, then explicitly allow required flows (app→db, app→redis, ingress-controller→app). Without a policy, all pods can reach all pods cluster-wide. Requires a CNI that enforces NetworkPolicy (Calico/Cilium — flannel does not).

## Namespaces, RBAC, ServiceAccounts
- **One namespace per tenant** is the primary isolation boundary — scopes NetworkPolicy, RBAC, quotas, and PSA labels. Add `ResourceQuota` + `LimitRange` per namespace so one tenant can't starve others.
- **RBAC least-privilege**: prefer namespaced `Role`/`RoleBinding` over `ClusterRole`; grant only the verbs/resources needed. Never bind `cluster-admin` to app identities.
- Give each workload its **own ServiceAccount** (`automountServiceAccountToken: false` unless the pod calls the API). The default SA should have zero permissions.

## Storage
- `PersistentVolumeClaim` requests storage from a `StorageClass` (dynamic provisioning). Set `storageClassName` explicitly rather than relying on the cluster default.
- StatefulSet `volumeClaimTemplates` gives each replica its own PVC. Choose `reclaimPolicy: Retain` for data you can't lose. Know your access mode (`ReadWriteOnce` is single-node) and default `Delete` behavior.

## Rollouts, PDB, autoscaling
- Deployments do a **RollingUpdate** by default (tune `maxSurge`/`maxUnavailable`). Roll back with `kubectl rollout undo deployment/<name>`; watch with `kubectl rollout status`.
- **PodDisruptionBudget** (`policy/v1`, `minAvailable`/`maxUnavailable`) keeps a quorum up during node drains/upgrades — set one for every user-facing Deployment and for StatefulSets.
- **HorizontalPodAutoscaler** (`autoscaling/v2`) scales replicas on CPU/memory or custom metrics; requires resource **requests** to be set. Don't set an HPA and a fixed `replicas` that fight each other.

## Managing manifests
- Pick ONE templating layer; never hand-edit per-environment YAML. **Kustomize** (built into `kubectl`) — a `base/` plus `overlays/{dev,staging,prod}` patching replicas/resources/images — fits a manifests-in-`k8s/` repo well. **Helm** if you need real templating/packaging/releases. Don't mix both haphazardly.
- **GitOps**: git is the source of truth; a controller (Argo CD/Flux) reconciles the cluster to the repo. Prefer this over `kubectl apply` from laptops/CI for prod.

## The Python `kubernetes` client
- PyPI `kubernetes` current major is **36** (tracks the 1.x server minor, so `kubernetes==36.x` ↔ server 1.36); pin the major to your cluster. The app declares `kubernetes>=29` — bump toward the cluster's minor.
- In-cluster: `config.load_incluster_config()` (uses the pod's mounted ServiceAccount token); off-cluster: `config.load_kube_config()`.
- Use the **watch** API (`watch.Watch().stream(...)`) for event-driven orchestration rather than polling; handle `410 Gone` by re-listing to refresh the resourceVersion.
- The app's ServiceAccount needs a **tightly scoped Role** for exactly the objects it manages (e.g. create/list/delete tenant Deployments in specific namespaces) — a programmatic orchestrator is a prime privilege-escalation target, so no wildcard verbs.

## Observability & debugging
- Triage order: `kubectl get pods` → `kubectl describe pod <p>` (events, probe failures, scheduling) → `kubectl logs <p> [-p] [-c <container>]` → `kubectl get events --sort-by=.lastTimestamp`.
- **CrashLoopBackOff** — app exits/probe fails on start; read logs + `-p` (previous). **ImagePullBackOff** — bad tag/digest, private registry needs an `imagePullSecret`. **OOMKilled** (in `describe`) — memory limit too low or a leak. **Pending** — unschedulable: insufficient resources, unbound PVC, or unsatisfiable affinity/taints.

## Security baseline (Pod Security Admission)
- PSA is GA and built in; enforce standards with **namespace labels** — for tenant workloads use `pod-security.kubernetes.io/enforce: restricted` (plus `audit`/`warn`). Restricted requires exactly the pod securityContext above (non-root, drop ALL caps, no privilege escalation, RuntimeDefault seccomp).
- Cluster-wide default via the `pod-security.admission.config.k8s.io/v1` AdmissionConfiguration. `baseline` blocks obvious escapes (hostNetwork/PID/IPC, privileged); `restricted` is the target for untrusted multi-tenant pods. `privileged` = no enforcement, avoid.
