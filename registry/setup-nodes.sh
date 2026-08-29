#!/usr/bin/env bash
# Configura containerd en los 3 nodos para confiar en el registry local (HTTP, sin TLS).
# Uso: bash registry/setup-nodes.sh
set -euo pipefail
REGISTRY="${REGISTRY:-192.168.0.20:30500}"
USER_SSH="${USER_SSH:-kubernet}"

for N in 192.168.0.20 192.168.0.21 192.168.0.22; do
  echo "== $N =="
  ssh -t "$USER_SSH@$N" "
    sudo mkdir -p /etc/containerd/certs.d/${REGISTRY}
    printf 'server = \"http://${REGISTRY}\"\n\n[host.\"http://${REGISTRY}\"]\n  capabilities = [\"pull\", \"resolve\", \"push\"]\n  skip_verify = true\n' \
      | sudo tee /etc/containerd/certs.d/${REGISTRY}/hosts.toml >/dev/null
    if grep -q 'config_path' /etc/containerd/config.toml; then
      sudo sed -i 's#config_path = .*#config_path = \"/etc/containerd/certs.d\"#' /etc/containerd/config.toml
    else
      sudo sed -i '/\[plugins\.\"io\.containerd\.grpc\.v1\.cri\"\.registry\]/a\\    config_path = \"/etc/containerd/certs.d\"' /etc/containerd/config.toml
    fi
    sudo systemctl restart containerd
    sleep 2
    sudo crictl info | grep -q RuntimeReady && echo '  containerd OK'
  "
done
echo "Listo. Prueba: docker pull hello-world && docker tag hello-world ${REGISTRY}/hello-world && docker push ${REGISTRY}/hello-world"
