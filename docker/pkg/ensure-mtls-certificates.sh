#!/bin/bash
# Generate mTLS material under /etc/mcp-terminal/mtls_certificates when missing.
#
# Idempotent: never overwrites existing files. Full bootstrap only when the CA
# is absent; partial trees are left for manual completion (postinst banner).
#
# Usage: ensure-mtls-certificates.sh MTLS_DIR [GROUP]

set -euo pipefail

MTLS_DIR="${1:?MTLS_DIR required}"
GROUP="${2:-mcp-terminal}"
VALIDITY_DAYS="${MCP_TERMINAL_MTLS_VALIDITY_DAYS:-3650}"
SERVICE_CN="${MCP_TERMINAL_MTLS_SERVER_CN:-mcp-terminal}"
CLIENT_CN="${MCP_TERMINAL_MTLS_CLIENT_CN:-mcp-proxy-client}"

required_paths() {
  printf '%s\n' \
    "${MTLS_DIR}/server/mcp-proxy.pem" \
    "${MTLS_DIR}/ca/ca.crt" \
    "${MTLS_DIR}/mtls_certificates/client/mcp-proxy.crt" \
    "${MTLS_DIR}/mtls_certificates/client/mcp-proxy.key" \
    "${MTLS_DIR}/mtls_certificates/ca/ca.crt"
}

all_present() {
  local path
  while IFS= read -r path; do
    [ -f "$path" ] || return 1
  done < <(required_paths)
  return 0
}

any_present() {
  local path
  while IFS= read -r path; do
    if [ -f "$path" ]; then
      return 0
    fi
  done < <(required_paths)
  return 1
}

ensure_layout() {
  if [ "$(id -u)" -eq 0 ]; then
    install -d -m 0750 -o root -g "$GROUP" "$MTLS_DIR"
    install -d -m 0750 -o root -g "$GROUP" "${MTLS_DIR}/ca"
    install -d -m 0750 -o root -g "$GROUP" "${MTLS_DIR}/server"
    install -d -m 0750 -o root -g "$GROUP" "${MTLS_DIR}/client"
    install -d -m 0750 -o root -g "$GROUP" "${MTLS_DIR}/mtls_certificates/client"
    install -d -m 0750 -o root -g "$GROUP" "${MTLS_DIR}/mtls_certificates/ca"
  else
    mkdir -p "${MTLS_DIR}/ca" "${MTLS_DIR}/server" "${MTLS_DIR}/client" \
      "${MTLS_DIR}/mtls_certificates/client" "${MTLS_DIR}/mtls_certificates/ca"
  fi
}

generate_ca() {
  echo "[mcp-terminal-docker] Generating install-time CA under ${MTLS_DIR}/ca/"
  openssl genrsa -out "${MTLS_DIR}/ca/ca.key" 4096
  chmod 600 "${MTLS_DIR}/ca/ca.key"
  openssl req -new -x509 -days "$VALIDITY_DAYS" \
    -key "${MTLS_DIR}/ca/ca.key" \
    -out "${MTLS_DIR}/ca/ca.crt" \
    -subj "/C=UA/ST=Kyiv/L=Kyiv/O=MCP-Terminal/OU=CA/CN=mcp-terminal-install-ca"
  chmod 644 "${MTLS_DIR}/ca/ca.crt"
}

generate_server() {
  local key="${MTLS_DIR}/server/mcp-proxy.key"
  local crt="${MTLS_DIR}/server/mcp-proxy.crt"
  local pem="${MTLS_DIR}/server/mcp-proxy.pem"
  echo "[mcp-terminal-docker] Generating server certificate (CN=${SERVICE_CN})"
  openssl genrsa -out "$key" 2048
  chmod 600 "$key"
  openssl req -new -key "$key" -out "${MTLS_DIR}/server/mcp-proxy.csr" \
    -subj "/C=UA/ST=Kyiv/L=Kyiv/O=MCP-Terminal/OU=Server/CN=${SERVICE_CN}"
  openssl x509 -req -in "${MTLS_DIR}/server/mcp-proxy.csr" \
    -CA "${MTLS_DIR}/ca/ca.crt" -CAkey "${MTLS_DIR}/ca/ca.key" \
    -CAcreateserial -out "$crt" -days "$VALIDITY_DAYS" \
    -extensions v3_server -extfile <(
      printf '%s\n' \
        '[v3_server]' \
        'basicConstraints = CA:FALSE' \
        'keyUsage = critical,digitalSignature,keyEncipherment' \
        'extendedKeyUsage = serverAuth' \
        'subjectAltName = @alt_names' \
        '[alt_names]' \
        "DNS.1 = ${SERVICE_CN}" \
        'DNS.2 = localhost' \
        'DNS.3 = mcp-terminal' \
        'IP.1 = 127.0.0.1' \
        'IP.2 = 172.18.0.1' \
        'IP.3 = 172.20.0.1'
    )
  rm -f "${MTLS_DIR}/server/mcp-proxy.csr"
  cat "$crt" "$key" >"$pem"
  chmod 644 "$crt" "$pem"
}

generate_client() {
  local flat_key="${MTLS_DIR}/client/mcp-proxy.key"
  local flat_crt="${MTLS_DIR}/client/mcp-proxy.crt"
  local nested_key="${MTLS_DIR}/mtls_certificates/client/mcp-proxy.key"
  local nested_crt="${MTLS_DIR}/mtls_certificates/client/mcp-proxy.crt"
  echo "[mcp-terminal-docker] Generating client certificate (CN=${CLIENT_CN})"
  openssl genrsa -out "$flat_key" 2048
  chmod 600 "$flat_key"
  openssl req -new -key "$flat_key" -out "${MTLS_DIR}/client/mcp-proxy.csr" \
    -subj "/C=UA/ST=Kyiv/L=Kyiv/O=MCP-Terminal/OU=Client/CN=${CLIENT_CN}"
  openssl x509 -req -in "${MTLS_DIR}/client/mcp-proxy.csr" \
    -CA "${MTLS_DIR}/ca/ca.crt" -CAkey "${MTLS_DIR}/ca/ca.key" \
    -CAcreateserial -out "$flat_crt" -days "$VALIDITY_DAYS" \
    -extensions v3_client -extfile <(
      printf '%s\n' \
        '[v3_client]' \
        'basicConstraints = CA:FALSE' \
        'keyUsage = critical,digitalSignature,keyEncipherment' \
        'extendedKeyUsage = clientAuth' \
        'subjectAltName = @alt_names' \
        '[alt_names]' \
        "DNS.1 = ${CLIENT_CN}" \
        'DNS.2 = localhost'
    )
  rm -f "${MTLS_DIR}/client/mcp-proxy.csr"
  install -m 644 "$flat_crt" "$nested_crt"
  install -m 600 "$flat_key" "$nested_key"
  ln -sf "../../ca/ca.crt" "${MTLS_DIR}/mtls_certificates/ca/ca.crt"
}

fix_permissions() {
  if [ "$(id -u)" -eq 0 ]; then
    chown -R root:"$GROUP" "$MTLS_DIR"
  fi
  find "$MTLS_DIR" -type d -exec chmod 0750 {} +
  find "$MTLS_DIR" -type f -name '*.key' -exec chmod 600 {} +
  find "$MTLS_DIR" -type f ! -name '*.key' -exec chmod 644 {} +
  [ -f "${MTLS_DIR}/ca/ca.key" ] && chmod 600 "${MTLS_DIR}/ca/ca.key"
}

main() {
  if ! command -v openssl >/dev/null 2>&1; then
    echo "[mcp-terminal-docker] openssl not found; skip mTLS generation" >&2
    return 0
  fi
  ensure_layout
  if all_present; then
    echo "[mcp-terminal-docker] mTLS material already present under ${MTLS_DIR}"
    return 0
  fi
  if any_present; then
    echo "[mcp-terminal-docker] Partial mTLS tree under ${MTLS_DIR}; not auto-generating" >&2
    return 0
  fi
  if [ ! -f "${MTLS_DIR}/ca/ca.crt" ]; then
    generate_ca
  fi
  generate_server
  generate_client
  fix_permissions
  echo "[mcp-terminal-docker] Install-time mTLS bootstrap complete under ${MTLS_DIR}"
}

main "$@"
