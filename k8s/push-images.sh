#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

kubectl apply -f "$SCRIPT_DIR/registry-deployment.yml"
kubectl rollout status deployment/registry --timeout=180s

kubectl port-forward svc/registry 5000:5000 >/tmp/lib-registry-port-forward.log 2>&1 &
PF_PID=$!
trap 'kill $PF_PID' EXIT

for svc in prestito modifica worker frontend; do
  echo "Building $svc..."
  docker build -t "localhost:5000/lib-$svc:1.0" "$ROOT_DIR/$svc"
  docker push "localhost:5000/lib-$svc:1.0"
done

echo "Immagini pubblicate. Ora puoi applicare i manifest Kubernetes:"
echo "kubectl apply -f $SCRIPT_DIR"
