#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REGISTRY_HOST="127.0.0.1"
REGISTRY_PORT="5000"
REGISTRY_URL="${REGISTRY_HOST}:${REGISTRY_PORT}"

cleanup_port_forward() {
  if [[ -n "${PF_PID:-}" ]] && kill -0 "$PF_PID" 2>/dev/null; then
    kill "$PF_PID" 2>/dev/null || true
    wait "$PF_PID" 2>/dev/null || true
  fi
}

kubectl apply -f "$SCRIPT_DIR/registry-deployment.yml"
kubectl rollout status deployment/registry --timeout=180s

kubectl port-forward svc/registry "$REGISTRY_PORT:$REGISTRY_PORT" >/tmp/lib-registry-port-forward.log 2>&1 &
PF_PID=$!
trap cleanup_port_forward EXIT

for i in $(seq 1 30); do
  if curl -fsS "http://${REGISTRY_URL}/v2/" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

for svc in prestito modifica worker frontend; do
  echo "Building $svc..."
  docker build -t "${REGISTRY_URL}/lib-$svc:1.0" "$ROOT_DIR/$svc"
  docker push "${REGISTRY_URL}/lib-$svc:1.0"
done

echo "Immagini pubblicate. Ora puoi applicare i manifest Kubernetes:"
echo "kubectl apply -f $SCRIPT_DIR"
