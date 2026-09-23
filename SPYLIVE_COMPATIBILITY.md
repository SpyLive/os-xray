# SpyLive os-xray compatibility fork

## Target matrix

- OPNsense: 26.7.x
- FreeBSD: 15.1 amd64
- Xray-core production default: 26.3.27 (pinned/tested production release)
- Xray-core compatibility candidate: 26.9.9 (newer upstream prerelease; bundled by 3x-ui 3.8.5)
- tun2socks: 2.7.0

## Confirmed compatibility fixes

1. tun2socks 2.7.0 uses pflag; runtime invocation is `--config`, not legacy `-config`.
2. New VLESS imports use Xray's simplified flat outbound (`address`, `port`, `id`, `encryption`, `flow`).
3. Existing legacy `settings.vnext[]` remains readable for migration, GUI and diagnostics.
4. Existing file imports preserve the complete proxy outbound in `outbound_config`.
5. Legacy config.xml instances without `outbound_config` are migrated before runtime.
6. Xray validation uses explicit `xray run -test -c`.
7. Installer pins and SHA-256 verifies tested FreeBSD amd64 artifacts and backs up binaries before replacement.
8. Live OPNsense migration handles the observed mixed layout `<instances></instances>` + legacy `<instance>` without skipping migration.
9. Orphaned legacy profiles with no explicit enabled flag migrate disabled, preventing an obsolete endpoint from being resurrected automatically.
10. Runtime, boot hook and syshook reject malformed instance UUIDs before using them in file/lock paths.
11. tun2socks YAML values are encoded as safe scalars when they contain YAML-significant characters.

## Version policy

The fork does not silently follow GitHub `latest` on a production firewall.

Xray v26.3.27 is the fork's pinned/tested production release. Xray v26.9.9 is newer but marked prerelease; 3x-ui v3.8.5 bundles it. The protocol/config features used by this patch (flat VLESS outbound and REALITY `password` / `publicKey` compatibility) already exist in v26.3.27, so the firewall defaults to the stable release until v26.9.9 is validated on OPNsense 26.7.

Tested hashes:

- Xray-freebsd-64.zip v26.3.27: `c0fcd6962fc8a382e14441370ddbdb6a56e7108c73e817938c626770ac4a1358`
- tun2socks-freebsd-amd64.zip v2.7.0: `3ebb747aa83ee3157330beb324bbeaf9a742db6a8d24b9bbc96a4125aaeeeaea`

## Deliberately deferred

- FreeBSD tun2socks normally destroys its cloned TUN on graceful close; the plugin now also removes a stale TUN after stop. OPNsense assignment/gateway/PF behavior still requires live 26.7 validation.
- The watchdog still distinguishes process liveness from path health. A later HA patch should add debounced end-to-end probes instead of restarting on a single transient HTTP failure.
- FreeBSD 15.1 interface/statistics behavior must be verified on the target OPNsense host before changing gateway lifecycle semantics.
