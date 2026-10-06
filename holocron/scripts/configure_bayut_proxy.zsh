#!/bin/zsh
# Prompt locally; shell-quote values so credentials cannot execute when sourced.
unsetopt XTRACE VERBOSE
set -eu
umask 077

bayut_credentials_file="${0:A:h:h}/.env.bayut.local"

read -rs 'bayut_login?Proxy login (base login only; hidden): '
printf '\n'
read -rs 'bayut_password?Proxy password (hidden): '
printf '\n'
read -r 'bayut_host?Proxy host [gw.dataimpulse.com]: '
read -r 'bayut_port?Proxy port [823]: '

if [[ -z "$bayut_login" || -z "$bayut_password" ]]; then
    printf '%s\n' 'Login and password are required. The file was not changed.' >&2
    exit 1
fi

bayut_host="${bayut_host:-gw.dataimpulse.com}"
bayut_port="${bayut_port:-823}"
bayut_server="http://${bayut_host}:${bayut_port}"
bayut_username="${bayut_login}__cr.ae;sessid.{session}"

printf 'export BAYUT_PROXY_SERVER=%q\nexport BAYUT_PROXY_USERNAME=%q\nexport BAYUT_PROXY_PASSWORD=%q\n' \
    "$bayut_server" "$bayut_username" "$bayut_password" > "$bayut_credentials_file"
chmod 600 "$bayut_credentials_file"
printf 'Credentials saved to %s\n' "$bayut_credentials_file"
