#!/usr/bin/env bash
set -euo pipefail

# Su Rancher Desktop (modalità containerd) nerdctl e k3s condividono lo stesso
# containerd. Costruendo le immagini direttamente nel namespace "k8s.io" il
# cluster le vede subito, senza bisogno di un registry intermedio.
# I deployment referenziano le immagini locali (es. lib-prestito:1.0) con
# imagePullPolicy: IfNotPresent.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
NAMESPACE="k8s.io"

for svc in prestito modifica worker frontend; do
  echo "Building lib-$svc:1.0 nel namespace containerd '$NAMESPACE'..."
  nerdctl --namespace "$NAMESPACE" build -t "lib-$svc:1.0" "$ROOT_DIR/$svc"
done

echo "Immagini costruite nel namespace k8s.io. Ora puoi applicare i manifest:"
echo "kubectl apply -f $SCRIPT_DIR"
